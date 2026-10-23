"""Architecture tests: the vendor boundary stays inside the adapter.

Static import analysis proves that only the ``chstockdata`` adapter package
touches the optional vendor library, that the vendor import stays lazy inside
adapter construction, and that canonical records never carry vendor types.
"""

import ast
import dataclasses
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from systematic_investing.adapters.chstockdata.provider import (
    ChStockDataProvider,
    RawVendorResponse,
)
from systematic_investing.data.contracts import ProviderSuccess
from systematic_investing.data.ports import DailyBarRequest
from systematic_investing.domain.identifiers import Exchange, InstrumentId
from systematic_investing.domain.market import DailyBar

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "systematic_investing"
ADAPTER_PATH = SRC_ROOT / "adapters" / "chstockdata" / "provider.py"

VENDOR_ROOT = "chstockdata"
CORE_PACKAGES = (
    "domain",
    "data",
    "instrument_master",
    "portfolio",
    "risk",
    "backtest",
    "metrics",
    "boundaries",
)


def python_files() -> list[Path]:
    return sorted(path for path in SRC_ROOT.rglob("*.py") if path.is_file())


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def module_level_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


class TestVendorImportBoundary:
    def test_only_the_adapter_imports_the_vendor_library(self) -> None:
        offenders = sorted(
            str(path.relative_to(SRC_ROOT))
            for path in python_files()
            if path != ADAPTER_PATH
            and any(
                module == VENDOR_ROOT or module.startswith(f"{VENDOR_ROOT}.")
                for module in imported_modules(path)
            )
        )

        assert offenders == []

    def test_vendor_import_is_lazy_inside_adapter_construction(self) -> None:
        top_level = [
            module
            for module in module_level_imports(ADAPTER_PATH)
            if module == VENDOR_ROOT or module.startswith(f"{VENDOR_ROOT}.")
        ]
        nested = [
            module
            for module in imported_modules(ADAPTER_PATH)
            if module == VENDOR_ROOT or module.startswith(f"{VENDOR_ROOT}.")
        ]

        assert top_level == []
        assert nested, "the adapter must contain the single vendor import site"

    def test_core_packages_never_import_the_adapter(self) -> None:
        offenders: list[str] = []
        for package in CORE_PACKAGES:
            for path in sorted((SRC_ROOT / package).rglob("*.py")):
                if any(
                    module == "systematic_investing.adapters"
                    or module.startswith("systematic_investing.adapters.")
                    for module in imported_modules(path)
                ):
                    offenders.append(str(path.relative_to(SRC_ROOT)))

        assert offenders == []


class TestCanonicalRecordsCarryNoVendorTypes:
    def test_mapped_bars_expose_only_canonical_and_standard_types(self) -> None:
        instrument_id = InstrumentId(exchange=Exchange.XSHG, symbol="510300")
        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "chstockdata"
            / "daily_bars_vipdoc_xshg_510300.json"
        )
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        response = RawVendorResponse(
            capability=raw["capability"],
            payload=raw["payload"],
            upstream_source=raw["upstream_source"],
        )

        class FixedClient:
            def provider_version(self) -> str:
                return "0.2.1"

            def daily_bars(self, **kwargs: object) -> RawVendorResponse:
                del kwargs
                return response

        provider = ChStockDataProvider(
            client=FixedClient(),
            clock=lambda: datetime(2026, 9, 11, 18, 5, tzinfo=timezone(timedelta(hours=8))),
        )
        result = provider.fetch_daily_bars(
            DailyBarRequest(
                instrument_ids=(instrument_id,),
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 11),
            )
        )

        assert isinstance(result, ProviderSuccess)
        for record in result.records:
            assert isinstance(record, DailyBar)
            for field_info in dataclasses.fields(record):
                value = getattr(record, field_info.name)
                value_type = type(value)
                assert value_type.__module__.split(".")[0] not in {
                    "pandas",
                    "numpy",
                    "chstockdata",
                }


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_core_package_has_no_vendor_import_text(package: str) -> None:
    for path in sorted((SRC_ROOT / package).rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "import chstockdata" not in source
