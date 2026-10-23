"""Architecture tests for M0 Research/Production boundaries."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from systematic_investing.boundaries.import_rules import scan_import_boundaries
from systematic_investing.domain import runs

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "systematic_investing"


def test_repository_obeys_import_boundaries() -> None:
    assert scan_import_boundaries(SRC_ROOT) == ()


def test_vendor_import_is_allowed_only_in_chstockdata_adapter(tmp_path: Path) -> None:
    package_root = tmp_path / "systematic_investing"
    allowed = package_root / "adapters" / "chstockdata" / "provider.py"
    forbidden = package_root / "domain" / "prices.py"
    allowed.parent.mkdir(parents=True)
    forbidden.parent.mkdir(parents=True)
    allowed.write_text("import chstockdata\n", encoding="utf-8")
    forbidden.write_text("from chstockdata import daily\n", encoding="utf-8")

    violations = scan_import_boundaries(package_root)

    assert [(item.code, item.module) for item in violations] == [
        ("VENDOR_IMPORT_OUTSIDE_ADAPTER", "chstockdata")
    ]


def test_core_and_production_cannot_import_research_llm_or_adapters(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "systematic_investing"
    files = {
        "domain/model.py": "import openai\n",
        "production/runtime.py": "from systematic_investing.research import experiment\n",
        "instrument_master/repository.py": (
            "from systematic_investing.adapters.chstockdata import provider\n"
        ),
    }
    for relative, source in files.items():
        path = package_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    violations = scan_import_boundaries(package_root)

    assert {(item.code, item.module) for item in violations} == {
        ("LLM_IMPORT_IN_TRUSTED_NAMESPACE", "openai"),
        (
            "RESEARCH_IMPORT_IN_TRUSTED_NAMESPACE",
            "systematic_investing.research",
        ),
        (
            "PROVIDER_ADAPTER_IMPORT_IN_CORE",
            "systematic_investing.adapters.chstockdata",
        ),
    }


def test_promoted_bundle_requires_owner_audit_and_matching_immutable_digest() -> None:
    payload = b"approved deterministic bundle"
    content_digest = "sha256:" + sha256(payload).hexdigest()
    record = runs.PromotionAuditRecord(
        audit_id="promotion-audit-001",
        bundle_id="etf-core",
        bundle_version="1.0.0",
        content_digest=content_digest,
        owner_approval_id="owner-approval-001",
        approved_by="owner",
        approved_at=datetime(2026, 9, 16, 14, 0, tzinfo=UTC),
        source_authority="RESEARCH",
        destination_authority="PRODUCTION",
        reason="owner-approved evidence bundle",
    )
    bundle = runs.ApprovedBundle(audit_record=record)

    bundle.verify_content(payload)
    with pytest.raises(runs.BundleDigestMismatchError):
        bundle.verify_content(b"modified bundle")
    with pytest.raises(FrozenInstanceError):
        record.reason = "rewritten history"  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_approval_id": ""},
        {
            "source_authority": "PRODUCTION",
            "destination_authority": "PRODUCTION",
        },
    ],
)
def test_invalid_promotion_controls_fail_closed(changes: dict[str, str]) -> None:
    values = {
        "audit_id": "promotion-audit-001",
        "bundle_id": "etf-core",
        "bundle_version": "1.0.0",
        "content_digest": "sha256:" + "a" * 64,
        "owner_approval_id": "owner-approval-001",
        "approved_by": "owner",
        "approved_at": datetime(2026, 9, 16, 14, 0, tzinfo=UTC),
        "source_authority": "RESEARCH",
        "destination_authority": "PRODUCTION",
        "reason": "owner-approved evidence bundle",
    }
    values.update(changes)

    with pytest.raises(runs.InvalidPromotionRecordError):
        runs.PromotionAuditRecord(**values)
