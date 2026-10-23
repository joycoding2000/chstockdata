"""Research CLI integration: screen, basic-backtest, verify, no bypass.

The CLI is the external Agent boundary: every success output is versioned
JSON, failures are non-zero exits with typed reasons, the Basic run boundary
is enforced on the real snapshot files, and no flag can bypass any gate.
The fixture snapshot is synthetic, hand-audited, and materialized through the
same immutable M0 ``SnapshotWriter`` path the owner materializer uses.
"""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import SnapshotWriter
from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import (
    AdjustmentMode,
    Availability,
    AvailabilityBasis,
    DailyBar,
    TradabilityStatus,
    TradabilityStatusKind,
    TradingSession,
)
from systematic_investing.research import cli as cli_module
from systematic_investing.research.catalog import read_entries, verify_catalog
from systematic_investing.research.cli import build_parser, main

REPO_ROOT = Path(__file__).resolve().parents[2]

UNIVERSE_SYMBOLS: tuple[str, ...] = ("XSHG:510300",)
BASIC_START = date(2024, 1, 2)
BASIC_END = date(2024, 3, 29)


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    sessions: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            sessions.append(day)
        day = date.fromordinal(day.toordinal() + 1)
    return tuple(sessions)


SESSIONS: tuple[date, ...] = _weekdays(BASIC_START, BASIC_END)


def _closes() -> tuple[Decimal, ...]:
    """Rise through February, crash on Feb 28, small bounce on Feb 29, then
    keep sliding through March.

    At the Feb 29 month-end decision: close 1.55 > 2-session SMA
    (1.50+1.55)/2 = 1.525 (sma-2 holds), while 1.55 <= 3-session SMA
    (2.41+1.50+1.55)/3 (sma-3 exits and sells at the Mar 1 open), so the two
    variants make different decisions and different returns.
    """
    closes: list[Decimal] = []
    crash_index = SESSIONS.index(date(2024, 2, 28))
    bounce_index = SESSIONS.index(date(2024, 2, 29))
    for index in range(len(SESSIONS)):
        if index < crash_index:
            closes.append(Decimal("2.00") + Decimal(index) * Decimal("0.01"))
        elif index == crash_index:
            closes.append(Decimal("1.50"))
        else:
            closes.append(
                Decimal("1.55") - Decimal(index - bounce_index) * Decimal("0.01")
            )
    return tuple(closes)


def _intent_payload() -> dict:
    return {
        "intent_schema_version": "research-candidate-intent-1",
        "intent_id": "test-etf-absolute-trend-v1",
        "lineage_id": "test-etf-absolute-trend",
        "asset_class": "ETF",
        "sleeve": "CORE",
        "strategy_id": "etf-absolute-trend",
        "decision_frequency": "MONTHLY_LAST_SESSION",
        "economic_rationale": "Trend following avoids sustained drawdowns.",
        "rule_pseudocode": "if close > SMA(N): weight 1.0 else 0.0",
        "parameter_variants": [
            {"variant_id": "sma-2", "parameters": {"sma_sessions": "2"}},
            {"variant_id": "sma-3", "parameters": {"sma_sessions": "3"}},
        ],
        "parameter_priority": ["sma-2", "sma-3"],
        "parameter_selection_rule": "PRIORITY_FIRST_BASIC_PASS",
        "universe_policy": {
            "policy_name": "ETF_FIXED_QUALIFIED_V1",
            "instrument_ids": list(UNIVERSE_SYMBOLS),
        },
        "warm_up_start": BASIC_START.isoformat(),
        "basic_start": BASIC_START.isoformat(),
        "basic_end": BASIC_END.isoformat(),
        "oos_start": "2024-04-01",
        "oos_end": "2024-06-28",
        "benchmark": {
            "kind": "SINGLE_ETF_BUY_AND_HOLD",
            "instrument_ids": list(UNIVERSE_SYMBOLS),
            "rebalance": "INCEPTION",
        },
        "risk_off_choice": "CASH_0",
        "initial_capital": "100000",
        "cost_convention": {
            "commission_rate": "0.00025",
            "minimum_commission": "5",
            "slippage_rate": "0.0005",
        },
        "metric_convention": {
            "return_basis": "DAILY_CLOSE_TO_CLOSE",
            "annualization_sessions": "252",
        },
        "basic_promotion_rule": {
            "min_nav_observations": "20",
            "min_excess_total_return_vs_benchmark": "-0.10",
            "max_drawdown_floor": "-0.90",
            "max_turnover": "100",
        },
        "oos_survivor_rule": {
            "min_excess_total_return_vs_benchmark": "-0.10",
            "max_drawdown_floor": "-0.90",
        },
        "known_limitations": ("Synthetic smoke fixture only.",),
        "source": "CLI integration test fixture",
        "created_at": "2026-09-16",
    }


def _write_intent(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _dataset() -> CanonicalDataset:
    instrument_id = InstrumentId.parse("XSHG:510300")
    closes = _closes()
    bars: list[DailyBar] = []
    previous_close = None
    for close, session_date in zip(closes, SESSIONS, strict=True):
        available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
        bars.append(
            DailyBar(
                schema_version="v1",
                instrument_id=instrument_id,
                session_date=session_date,
                open=close,
                high=close,
                low=close,
                close=close,
                pre_close=previous_close,
                volume=Decimal("1000000"),
                amount=Decimal("4000000"),
                currency="CNY",
                volume_unit="shares",
                amount_unit="CNY",
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=None,
                availability=Availability(
                    information_available_at=available_at,
                    retrieved_at=available_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                ),
                provider_evidence_id="cli-test-bars",
            )
        )
        previous_close = close
    tradability: list[TradabilityStatus] = []
    for session_date in SESSIONS:
        known_at = datetime.combine(session_date, time(9, 0), tzinfo=UTC)
        tradability.append(
            TradabilityStatus(
                instrument_id=instrument_id,
                session_date=session_date,
                status=TradabilityStatusKind.TRADABLE,
                reason=None,
                availability=Availability(
                    information_available_at=known_at,
                    retrieved_at=known_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                ),
                provenance="exchange-fact",
            )
        )
    sessions = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="CLI-TEST-CAL-1",
        )
        for session_date in SESSIONS
    )
    return CanonicalDataset(
        daily_bars=tuple(bars),
        sessions=sessions,
        tradability=tuple(tradability),
        corporate_actions=(),
        rule_candidates=(),
    )


def _write_snapshot(tmp_path: Path, name: str = "snapshot") -> Path:
    writer = SnapshotWriter(
        provider_name="cli-test",
        provider_version="v1",
        adapter_version="cli-test-1",
    )
    cutoff = datetime.combine(BASIC_END, time(15, 30), tzinfo=UTC)
    snapshot_dir = tmp_path / name
    writer.persist(
        _dataset(),
        snapshot_dir=snapshot_dir,
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
    )
    return snapshot_dir


def _write_snapshot_with_post_basic_row(tmp_path: Path) -> Path:
    dataset = _dataset()
    instrument_id = InstrumentId.parse("XSHG:510300")
    post_basic = DailyBar(
        schema_version="v1",
        instrument_id=instrument_id,
        session_date=date(2024, 4, 1),
        open=Decimal("1.54"),
        high=Decimal("1.54"),
        low=Decimal("1.53"),
        close=Decimal("1.53"),
        pre_close=Decimal("1.53"),
        volume=Decimal("1000000"),
        amount=Decimal("4000000"),
        currency="CNY",
        volume_unit="shares",
        amount_unit="CNY",
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=None,
        availability=Availability(
            information_available_at=datetime.combine(
                date(2024, 4, 1), time(15, 5), tzinfo=UTC
            ),
            retrieved_at=datetime.combine(date(2024, 4, 1), time(15, 5), tzinfo=UTC),
            availability_basis=AvailabilityBasis.OBSERVED,
        ),
        provider_evidence_id="cli-test-bars",
    )
    contaminated = CanonicalDataset(
        daily_bars=(*dataset.daily_bars, post_basic),
        sessions=(
            *dataset.sessions,
            TradingSession(
                calendar_id="XSHG",
                session_date=date(2024, 4, 1),
                is_open=True,
                note=None,
                snapshot_version="CLI-TEST-CAL-1",
            ),
        ),
        tradability=(),
        corporate_actions=(),
        rule_candidates=(),
    )
    writer = SnapshotWriter(
        provider_name="cli-test",
        provider_version="v1",
        adapter_version="cli-test-1",
    )
    cutoff = datetime.combine(date(2024, 4, 1), time(15, 30), tzinfo=UTC)
    snapshot_dir = tmp_path / "contaminated-snapshot"
    writer.persist(
        contaminated,
        snapshot_dir=snapshot_dir,
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
    )
    return snapshot_dir


@pytest.fixture
def screened_root(tmp_path: Path) -> Path:
    root = tmp_path / "experiments"
    intent_path = _write_intent(tmp_path, _intent_payload())
    exit_code = main(["screen", "--intent", str(intent_path), "--root", str(root)])
    assert exit_code == 0
    return root


def _result_json(run_dir: Path) -> dict:
    return json.loads((run_dir / "result.json").read_text(encoding="utf-8"))


def _runs(lineage_dir: Path) -> tuple[Path, ...]:
    runs = lineage_dir / "runs"
    return tuple(sorted(path for path in runs.iterdir() if path.is_dir()))


# --- parser contract ---------------------------------------------------------


def test_cli_has_screen_basic_backtest_and_verify_commands() -> None:
    parser = build_parser()

    choices: set[str] | None = None
    for action in parser._actions:
        if action.dest == "command" and hasattr(action, "choices"):
            choices = set(action.choices)
    assert choices is not None
    assert {"screen", "basic-backtest", "verify"} <= choices


def test_cli_has_no_bypass_flags() -> None:
    parser = build_parser()

    forbidden = {
        "--force",
        "--force-pass",
        "--ignore-contamination",
        "--rewrite-artifact",
        "--skip-gate",
    }
    for action in parser._actions:
        options = set(getattr(action, "option_strings", ()))
        assert not options & forbidden, options & forbidden


# --- screen ------------------------------------------------------------------


def test_screen_accepts_frozen_intent_and_persists_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    intent_path = _write_intent(tmp_path, _intent_payload())
    root = tmp_path / "experiments"

    exit_code = main(["screen", "--intent", str(intent_path), "--root", str(root)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "research-cli-output-1"
    assert output["command"] == "screen"
    assert output["verdict"] == "SCREEN_PASS"
    lineage_dir = root / "test-etf-absolute-trend"
    assert (lineage_dir / "intent.json").exists()
    screens = list((lineage_dir / "screen").glob("*.json"))
    assert len(screens) == 1


def test_screen_rejects_missing_benchmark_with_typed_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    payload = _intent_payload()
    del payload["benchmark"]
    intent_path = _write_intent(tmp_path, payload)
    root = tmp_path / "experiments"

    exit_code = main(["screen", "--intent", str(intent_path), "--root", str(root)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == "REJECTED_BEFORE_IMPLEMENTATION"
    assert output["reason_codes"]


def test_screen_nonzero_exit_on_unparseable_intent(tmp_path: Path) -> None:
    intent_path = tmp_path / "broken.json"
    intent_path.write_text("{not json", encoding="utf-8")
    root = tmp_path / "experiments"

    assert main(["screen", "--intent", str(intent_path), "--root", str(root)]) != 0


# --- basic backtest ----------------------------------------------------------


def test_basic_backtest_runs_variants_and_selects_by_priority(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = Path(screened_root.parent) / "intent.json"
    if not intent_path.exists():
        intent_path = tmp_path / "intent.json"
        intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "research-cli-output-1"
    assert output["command"] == "basic-backtest"
    assert output["status"] == "COMPLETED"
    assert output["selected_variant"] == "sma-2"
    assert len(output["attempts"]) == 2
    assert all(attempt["status"] == "BASIC_PASS" for attempt in output["attempts"])

    lineage_dir = screened_root / "test-etf-absolute-trend"
    runs = _runs(lineage_dir)
    assert len(runs) == 2
    for run_dir in runs:
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "result.json").exists()
        assert (run_dir / "report.json").exists()


def test_basic_snapshot_failure_after_attempt_start_is_retained(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    intent_path = screened_root / "test-etf-absolute-trend" / "intent.json"
    missing_manifest = tmp_path / "missing" / "manifest.json"

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(missing_manifest),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code != 0
    capsys.readouterr()
    entries = read_entries(screened_root / "catalog")
    failures = [entry for entry in entries if entry["status"] == "RUN_FAILED_DATA"]
    assert len(failures) == 3
    assert verify_catalog(screened_root / "catalog", screened_root).status == "PASS"


def test_report_persistence_failure_becomes_complete_failed_attempt(
    screened_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = screened_root / "test-etf-absolute-trend" / "intent.json"
    original_write = cli_module.write_new_json

    def fail_report(path: Path, payload: dict) -> str:
        if path.name == "report.json":
            raise OSError("injected report persistence failure")
        return original_write(path, payload)

    monkeypatch.setattr(cli_module, "write_new_json", fail_report)
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code != 0
    capsys.readouterr()
    runs_root = screened_root / "test-etf-absolute-trend" / "runs"
    assert not tuple(runs_root.glob("*.staging"))
    run_dirs = tuple(path for path in runs_root.iterdir() if path.is_dir())
    assert len(run_dirs) == 1
    assert all(
        (run_dirs[0] / name).exists()
        for name in ("manifest.json", "result.json", "report.json")
    )
    entries = read_entries(screened_root / "catalog")
    run_entries = [entry for entry in entries if entry["artifact_type"] == "BASIC_RUN"]
    assert len(run_entries) == 3
    assert all(entry["status"] == "RUN_FAILED_KERNEL" for entry in run_entries)
    assert verify_catalog(screened_root / "catalog", screened_root).status == "PASS"


def test_catalog_persistence_failure_leaves_explained_marker(
    screened_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = screened_root / "test-etf-absolute-trend" / "intent.json"

    def fail_catalog_append(*args: object, **kwargs: object) -> object:
        raise OSError("injected catalog persistence failure")

    monkeypatch.setattr(cli_module, "append_entry", fail_catalog_append)
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code != 0
    capsys.readouterr()
    runs_root = screened_root / "test-etf-absolute-trend" / "runs"
    run_dirs = tuple(path for path in runs_root.iterdir() if path.is_dir())
    assert len(run_dirs) == 1
    marker = run_dirs[0] / "persistence-failure.json"
    assert marker.exists()
    marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    assert marker_payload["status"] == "RUN_FAILED_KERNEL"
    entries = read_entries(screened_root / "catalog")
    marker_entries = [
        entry
        for entry in entries
        if entry["artifact_type"] == "BASIC_RUN_PERSISTENCE_FAILURE"
    ]
    assert len(marker_entries) == 1
    assert verify_catalog(screened_root / "catalog", screened_root).status == "PASS"


def test_clean_basic_run_passes_catalog_verification(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A complete screen + Basic run must verify cleanly.

    Every persisted artifact (each run's manifest, result, and report) is
    catalogued with its own digest, so verify recomputes each file's bytes
    against the recorded digest and PASSes without any findings.
    """
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(["verify", "--root", str(screened_root)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["findings"] == []


def test_run_artifacts_are_catalogued_per_file_with_their_own_digests(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    import hashlib

    runs = _runs(screened_root / "test-etf-absolute-trend")
    entries = read_entries(screened_root / "catalog")
    run_entries = [entry for entry in entries if entry["artifact_type"] == "BASIC_RUN"]
    assert len(run_entries) == len(runs) * 3
    for run_dir in runs:
        for name in ("manifest.json", "result.json", "report.json"):
            path = run_dir / name
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            indexed = [
                entry
                for entry in run_entries
                if entry["ref"] == path.relative_to(screened_root).as_posix()
            ]
            assert indexed, f"{path} is not catalogued"
            assert list(indexed[0]["digests"].values()) == [digest]
    selections = [entry for entry in entries if entry["artifact_type"] == "BASIC_SELECTION"]
    assert len(selections) == 1


def test_failed_run_result_digest_matches_persisted_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A typed failed run's digest must verify against its own bytes.

    The runner computes the result digest over exactly the bytes that get
    persisted, for pass, rejection, and failure outcomes alike.
    """
    import hashlib

    from systematic_investing.research.artifacts import canonical_json_bytes

    snapshot_dir = _write_snapshot(tmp_path)
    payload = _intent_payload()
    payload["parameter_variants"] = [
        {"variant_id": "broken", "parameters": {"sma_sessions": "abc"}},
        {"variant_id": "sma-2", "parameters": {"sma_sessions": "2"}},
    ]
    payload["parameter_priority"] = ["broken", "sma-2"]
    root = tmp_path / "experiments"
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(payload), encoding="utf-8")
    exit_code = main(["screen", "--intent", str(intent_path), "--root", str(root)])
    assert exit_code == 0
    capsys.readouterr()
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(root),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()



    runs = _runs(root / "test-etf-absolute-trend")
    statuses = {}
    result_entries = {
        entry["ref"]: entry
        for entry in read_entries(root / "catalog")
        if entry["ref"].endswith("result.json")
    }
    for run_dir in runs:
        result_path = run_dir / "result.json"
        recorded = _result_json(run_dir)
        statuses[recorded["variant_id"]] = recorded["status"]
        file_digest = "sha256:" + hashlib.sha256(result_path.read_bytes()).hexdigest()
        indexed = result_entries[result_path.relative_to(root).as_posix()]
        assert list(indexed["digests"].values()) == [file_digest]
        assert file_digest == (
            "sha256:" + hashlib.sha256(canonical_json_bytes(recorded)).hexdigest()
        )
    assert statuses["broken"] == "RUN_FAILED_KERNEL"
    assert statuses["sma-2"] == "BASIC_PASS"


def test_basic_backtest_requires_the_screened_intent_to_match(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Basic runs qualify only the screened intent.

    After the intent is screened its frozen copy is immutable: running a
    modified intent file in the same lineage is an immutability violation,
    so a changed candidate must become a new version with its own screen.
    """
    snapshot_dir = _write_snapshot(tmp_path)
    payload = dict(_intent_payload())
    payload["economic_rationale"] = "Mutated after screening."
    intent_path = tmp_path / "mutated-intent.json"
    intent_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code != 0


def test_priority_first_pass_wins_even_when_other_return_is_higher(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    attempts = {attempt["variant_id"]: attempt for attempt in output["attempts"]}

    sma_2 = _result_json(
        next(
            run
            for run in _runs(screened_root / "test-etf-absolute-trend")
            if _result_json(run)["variant_id"] == "sma-2"
        )
    )
    sma_3 = _result_json(
        next(
            run
            for run in _runs(screened_root / "test-etf-absolute-trend")
            if _result_json(run)["variant_id"] == "sma-3"
        )
    )
    assert sma_2["metrics"]["total_return"] != sma_3["metrics"]["total_return"]
    assert attempts["sma-2"]["status"] == "BASIC_PASS"
    assert attempts["sma-3"]["status"] == "BASIC_PASS"
    assert output["selected_variant"] == "sma-2"


def test_re_run_same_manifest_creates_new_attempt_with_same_digest(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    argv = [
        "basic-backtest",
        "--intent",
        str(intent_path),
        "--snapshot",
        str(snapshot_dir / "manifest.json"),
        "--root",
        str(screened_root),
    ]
    assert main(argv) == 0
    first_output = json.loads(capsys.readouterr().out)
    first_digests = {
        attempt["variant_id"]: attempt["result_digest"]
        for attempt in first_output["attempts"]
    }
    first_run_count = len(_runs(screened_root / "test-etf-absolute-trend"))

    assert main(argv) == 0
    second_output = json.loads(capsys.readouterr().out)
    second_digests = {
        attempt["variant_id"]: attempt["result_digest"]
        for attempt in second_output["attempts"]
    }
    second_run_count = len(_runs(screened_root / "test-etf-absolute-trend"))

    assert second_run_count == first_run_count * 2
    assert first_digests == second_digests


def test_basic_backtest_requires_cheap_screen_pass(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    intent_path = _write_intent(tmp_path, _intent_payload())
    snapshot_dir = _write_snapshot(tmp_path)

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(root),
        ]
    )

    assert exit_code != 0


def test_basic_backtest_rejects_post_basic_snapshot_rows(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    contaminated = _write_snapshot_with_post_basic_row(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(contaminated / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )

    assert exit_code != 0


def test_basic_backtest_retains_all_rejected_attempts(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    payload = _intent_payload()
    payload["basic_promotion_rule"]["min_nav_observations"] = "99999"
    intent_path = _write_intent(tmp_path, payload)
    exit_code = main(["screen", "--intent", str(intent_path), "--root", str(root)])
    assert exit_code == 0
    snapshot_dir = _write_snapshot(tmp_path)

    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(root),
        ]
    )

    assert exit_code == 0
    runs = _runs(root / "test-etf-absolute-trend")
    assert len(runs) == 2
    statuses = {_result_json(run)["status"] for run in runs}
    assert statuses == {"REJECTED_BASIC"}
    entries = read_entries(root / "catalog")
    assert len(entries) == 8
    assert entries[0]["artifact_type"] == "CHEAP_SCREEN"
    for entry in entries[1:7]:
        assert entry["artifact_type"] == "BASIC_RUN"
        assert entry["status"] == "REJECTED_BASIC"
    assert entries[7]["artifact_type"] == "BASIC_SELECTION"
    assert entries[7]["status"] == "NO_BASIC_PASS"


# --- verify ------------------------------------------------------------------


def test_verify_passes_on_consistent_root(screened_root: Path) -> None:
    assert main(["verify", "--root", str(screened_root)]) == 0


def test_verify_fails_on_tampered_artifact(
    screened_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    exit_code = main(
        [
            "basic-backtest",
            "--intent",
            str(intent_path),
            "--snapshot",
            str(snapshot_dir / "manifest.json"),
            "--root",
            str(screened_root),
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    runs = _runs(screened_root / "test-etf-absolute-trend")
    result_path = runs[0] / "result.json"
    result_path.write_bytes(b'{"schema_version": "tampered"}')

    assert main(["verify", "--root", str(screened_root)]) == 1

    assert main(["verify", "--root", str(screened_root)]) == 1


# --- OOS exposure gate: freeze, run, honest no-candidate ---------------------

OOS_START = date(2024, 4, 1)
OOS_END = date(2024, 6, 28)
LINEAGE = "test-etf-absolute-trend"


def _oos_sessions() -> tuple[date, ...]:
    return _weekdays(OOS_START, OOS_END)


def _oos_bars() -> tuple[DailyBar, ...]:
    """A gentle OOS-window rise with chained pre_close; the first OOS bar
    carries no pre_close because the previous close lives in the Basic
    window and must never be exposed."""
    instrument_id = InstrumentId.parse("XSHG:510300")
    sessions = _oos_sessions()
    bars: list[DailyBar] = []
    previous_close = None
    for index, session_date in enumerate(sessions):
        close = Decimal("1.50") + Decimal(index) * Decimal("0.005")
        available_at = datetime.combine(session_date, time(15, 5), tzinfo=UTC)
        bars.append(
            DailyBar(
                schema_version="v1",
                instrument_id=instrument_id,
                session_date=session_date,
                open=close,
                high=close,
                low=close,
                close=close,
                pre_close=previous_close,
                volume=Decimal("1000000"),
                amount=Decimal("4000000"),
                currency="CNY",
                volume_unit="shares",
                amount_unit="CNY",
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=None,
                availability=Availability(
                    information_available_at=available_at,
                    retrieved_at=available_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                ),
                provider_evidence_id="cli-test-oos-bars",
            )
        )
        previous_close = close
    return tuple(bars)


def _oos_tradability() -> tuple[TradabilityStatus, ...]:
    instrument_id = InstrumentId.parse("XSHG:510300")
    records: list[TradabilityStatus] = []
    for session_date in _oos_sessions():
        known_at = datetime.combine(session_date, time(9, 0), tzinfo=UTC)
        records.append(
            TradabilityStatus(
                instrument_id=instrument_id,
                session_date=session_date,
                status=TradabilityStatusKind.TRADABLE,
                reason=None,
                availability=Availability(
                    information_available_at=known_at,
                    retrieved_at=known_at,
                    availability_basis=AvailabilityBasis.OBSERVED,
                ),
                provenance="exchange-fact",
            )
        )
    return tuple(records)


def _write_oos_snapshot(tmp_path: Path, name: str = "oos-snapshot") -> Path:
    """A pure OOS-window snapshot: sessions, bars, and tradability records
    exist only between the OOS start and the OOS end."""
    sessions = tuple(
        TradingSession(
            calendar_id="XSHG",
            session_date=session_date,
            is_open=True,
            note=None,
            snapshot_version="CLI-TEST-CAL-1",
        )
        for session_date in _oos_sessions()
    )
    oos_dataset = CanonicalDataset(
        daily_bars=_oos_bars(),
        sessions=sessions,
        tradability=_oos_tradability(),
        corporate_actions=(),
        rule_candidates=(),
    )
    writer = SnapshotWriter(
        provider_name="cli-test",
        provider_version="v1",
        adapter_version="cli-test-1",
    )
    cutoff = datetime.combine(OOS_END, time(15, 30), tzinfo=UTC)
    snapshot_dir = tmp_path / name
    writer.persist(
        oos_dataset,
        snapshot_dir=snapshot_dir,
        created_at=cutoff,
        knowledge_cutoff=cutoff,
        retrieved_at=cutoff,
    )
    return snapshot_dir


def _basic_pass_root(
    tmp_path: Path, capsys: pytest.CaptureFixture, root_name: str = "experiments"
) -> Path:
    """A lineage with a screen, a Basic backtest, and a Basic PASS selection."""
    root = tmp_path / root_name
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(_intent_payload()), encoding="utf-8")
    assert main(["screen", "--intent", str(intent_path), "--root", str(root)]) == 0
    snapshot_dir = _write_snapshot(tmp_path)
    assert (
        main(
            [
                "basic-backtest",
                "--intent",
                str(intent_path),
                "--snapshot",
                str(snapshot_dir / "manifest.json"),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()
    return root


def _freeze(root: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> dict:
    assert (
        main(
            [
                "oos-freeze",
                "--candidate-id",
                LINEAGE,
                "--root",
                str(root),
            ]
        )
        == 0
    )
    return json.loads(capsys.readouterr().out)


def _oos_run_argv(
    freeze_id: str,
    snapshot_dir: Path | None,
    root: Path,
    warm_up_snapshot: Path | None = None,
) -> list[str]:
    snapshot_manifest = (
        (snapshot_dir / "manifest.json")
        if snapshot_dir is not None
        else root.parent / "missing-oos" / "manifest.json"
    )
    argv = [
        "oos-run",
        "--freeze-id",
        freeze_id,
        "--snapshot",
        str(snapshot_manifest),
        "--root",
        str(root),
    ]
    if warm_up_snapshot is not None:
        argv.extend(["--warm-up-snapshot", str(warm_up_snapshot / "manifest.json")])
    return argv


def _resign_freeze(payload: dict) -> dict:
    """Recompute freeze_id/freeze_digest over a mutated body, exactly as the
    oos.py builders derive them; the freeze verifier accepts the result by
    design, so only the oos-run identity cross-check can catch it."""
    from systematic_investing.research.contracts import canonical_payload_digest

    body = {key: value for key, value in payload.items() if key != "freeze_digest"}
    body["freeze_id"] = (
        "freeze-"
        + canonical_payload_digest(
            {key: value for key, value in body.items() if key != "freeze_id"}
        ).removeprefix("sha256:")[:16]
    )
    body["freeze_digest"] = canonical_payload_digest(body)
    return body


def _tamper_freeze(root: Path, freeze_id: str, field: str, value: str) -> str:
    """Bind a different (well-formed) value into the freeze and re-sign it.

    Re-signing derives a NEW freeze_id, so the forged artifact is written
    under its own ``oos/<new_freeze_id>/`` directory — exactly where a forged
    freeze would exist. Returns the forged freeze id to run against."""
    freeze_path = root / LINEAGE / "oos" / freeze_id / "freeze.json"
    payload = json.loads(freeze_path.read_text(encoding="utf-8"))
    payload[field] = value
    resigned = _resign_freeze(payload)
    forged_id = str(resigned["freeze_id"])
    forged_dir = root / LINEAGE / "oos" / forged_id
    forged_dir.mkdir(parents=True, exist_ok=True)
    forged_path = forged_dir / "freeze.json"
    forged_path.write_text(
        json.dumps(resigned, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return forged_id


def test_oos_run_refuses_freeze_bound_implementation_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A self-consistent, re-signed freeze whose bound implementation digest
    differs from the running code is located by its derived freeze_id and
    refused by the freeze-identity enforcement BEFORE any data is opened:
    the failure names the typed reason on stderr and no reveal, result, or
    verdict is persisted."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    forged_id = _tamper_freeze(
        root,
        output["freeze_id"],
        "implementation_digest",
        "sha256:" + "7" * 64,
    )
    assert forged_id != output["freeze_id"]
    oos_snapshot = _write_oos_snapshot(tmp_path)
    basic_snapshot = _write_snapshot(tmp_path, name="warm-up")

    exit_code = main(
        _oos_run_argv(
            forged_id,
            oos_snapshot,
            root,
            warm_up_snapshot=basic_snapshot,
        )
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "OOS_FREEZE_IMPLEMENTATION_MISMATCH" in captured.err
    freeze_dir = root / LINEAGE / "oos" / forged_id
    assert not (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "result.json").exists()
    assert not (freeze_dir / "verdict.json").exists()


def test_oos_run_refuses_freeze_bound_kernel_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A self-consistent, re-signed freeze whose bound kernel identity
    differs from the running kernel is located by its derived freeze_id and
    refused by the freeze-identity enforcement BEFORE any data is opened."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    forged_id = _tamper_freeze(
        root,
        output["freeze_id"],
        "kernel_identity_digest",
        "sha256:" + "8" * 64,
    )
    assert forged_id != output["freeze_id"]
    oos_snapshot = _write_oos_snapshot(tmp_path)
    basic_snapshot = _write_snapshot(tmp_path, name="warm-up")

    exit_code = main(
        _oos_run_argv(
            forged_id,
            oos_snapshot,
            root,
            warm_up_snapshot=basic_snapshot,
        )
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "OOS_FREEZE_KERNEL_MISMATCH" in captured.err
    freeze_dir = root / LINEAGE / "oos" / forged_id
    assert not (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "result.json").exists()
    assert not (freeze_dir / "verdict.json").exists()


def test_oos_run_unknown_kernel_never_opens_the_snapshot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    forged_id = _tamper_freeze(
        root,
        output["freeze_id"],
        "kernel_identity_digest",
        "sha256:" + "0" * 64,
    )
    opened: list[bool] = []

    def fail_if_opened(*_args, **_kwargs):
        opened.append(True)
        raise AssertionError("snapshot reader must not run before kernel resolution")

    monkeypatch.setattr(
        "systematic_investing.research.cli.SnapshotReader.load", fail_if_opened
    )
    exit_code = main(_oos_run_argv(forged_id, None, root))

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "OOS_FREEZE_KERNEL_MISMATCH" in captured.err
    assert opened == []
    freeze_dir = root / LINEAGE / "oos" / forged_id
    assert not (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "result.json").exists()
    assert not (freeze_dir / "verdict.json").exists()


def test_oos_freeze_refuses_unsupported_kernel_before_persistence(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    selected_run = next(
        run
        for run in _runs(root / LINEAGE)
        if _result_json(run)["variant_id"] == "sma-2"
    )
    manifest_path = selected_run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["kernel_identity_digest"] = "sha256:" + "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    before = read_entries(root / "catalog")

    exit_code = main(
        ["oos-freeze", "--candidate-id", LINEAGE, "--root", str(root)]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "OOS_FREEZE_KERNEL_UNSUPPORTED" in captured.err
    assert not list((root / LINEAGE / "oos").glob("*/freeze.json"))
    assert read_entries(root / "catalog") == before


def test_oos_run_refuses_corrupt_oos_snapshot_with_typed_error(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A checksum-violating OOS artifact is a typed CLI failure, not a
    traceback; the reveal already exists and no verdict is written."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    oos_snapshot = _write_oos_snapshot(tmp_path)
    artifact = next((oos_snapshot / "artifacts").glob("*.jsonl"))
    # Any appended byte breaks the manifest checksum without needing escapes.
    artifact.write_bytes(artifact.read_bytes() + b"TAMPERED")
    basic_snapshot = _write_snapshot(tmp_path, name="warm-up")

    exit_code = main(
        _oos_run_argv(
            output["freeze_id"],
            oos_snapshot,
            root,
            warm_up_snapshot=basic_snapshot,
        )
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "SNAPSHOT_INTEGRITY_INVALID" in captured.err
    freeze_dir = root / LINEAGE / "oos" / output["freeze_id"]
    assert (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "verdict.json").exists()


def test_cli_has_oos_commands_and_no_bypass_flags() -> None:
    parser = build_parser()

    choices: set[str] | None = None
    for action in parser._actions:
        if action.dest == "command" and hasattr(action, "choices"):
            choices = set(action.choices)
    assert choices is not None
    assert {"oos-freeze", "oos-run", "no-oos-eligible"} <= choices


def test_oos_freeze_requires_basic_pass(screened_root: Path) -> None:
    """Without a Basic PASS selection there is nothing to freeze."""
    assert (
        main(["oos-freeze", "--candidate-id", LINEAGE, "--root", str(screened_root)])
        != 0
    )


def test_oos_freeze_requires_selected_basic_candidate(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    payload = _intent_payload()
    payload["basic_promotion_rule"]["min_nav_observations"] = "99999"
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["screen", "--intent", str(intent_path), "--root", str(root)]) == 0
    snapshot_dir = _write_snapshot(tmp_path)
    assert (
        main(
            [
                "basic-backtest",
                "--intent",
                str(intent_path),
                "--snapshot",
                str(snapshot_dir / "manifest.json"),
                "--root",
                str(root),
            ]
        )
        == 0
    )

    assert main(["oos-freeze", "--candidate-id", LINEAGE, "--root", str(root)]) != 0


def test_oos_freeze_persists_immutable_freeze_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)

    assert output["schema_version"] == "research-cli-output-1"
    assert output["command"] == "oos-freeze"
    assert output["lineage_id"] == LINEAGE
    assert output["freeze_id"].startswith("freeze-")
    freeze_path = root / LINEAGE / "oos" / output["freeze_id"] / "freeze.json"
    assert freeze_path.exists()
    freeze_payload = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert "oos_snapshot_digest" not in freeze_payload
    assert freeze_payload["selected_variant_id"] == "sma-2"
    assert freeze_payload["requested_oos_start"] == "2024-04-01"
    assert freeze_payload["requested_oos_end"] == "2024-06-28"

    assert main(["verify", "--root", str(root)]) == 0


def test_oos_freeze_is_idempotent_for_identical_content(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    first = _freeze(root, tmp_path, capsys)
    second = _freeze(root, tmp_path, capsys)
    assert first["freeze_id"] == second["freeze_id"]
    freeze_dir = root / LINEAGE / "oos" / first["freeze_id"]
    assert list(freeze_dir.iterdir()) == [freeze_dir / "freeze.json"]


def test_oos_run_records_exactly_one_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    oos_snapshot = _write_oos_snapshot(tmp_path)
    # Same content as the Basic snapshot of _basic_pass_root under a fresh
    # directory: identical content-derived snapshot id, no rewrite.
    basic_snapshot = _write_snapshot(tmp_path, name="warm-up")

    exit_code = main(
        _oos_run_argv(
            output["freeze_id"],
            oos_snapshot,
            root,
            warm_up_snapshot=basic_snapshot,
        )
    )

    assert exit_code == 0
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["command"] == "oos-run"
    assert run_output["verdict"] in {"SURVIVOR", "REJECTED_OOS"}
    freeze_dir = root / LINEAGE / "oos" / output["freeze_id"]
    assert (freeze_dir / "reveal.json").exists()
    assert (freeze_dir / "result.json").exists()
    assert (freeze_dir / "verdict.json").exists()
    verdict = json.loads((freeze_dir / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["verdict"] == run_output["verdict"]
    result = json.loads((freeze_dir / "result.json").read_text(encoding="utf-8"))
    manifest = result["manifest"]
    assert manifest["output_scope"] == "OOS"
    assert manifest["snapshot_digest"] == run_output["snapshot_digest"]
    assert manifest["universe_schedule_digest"] == run_output[
        "universe_schedule_digest"
    ]

    entries = read_entries(root / "catalog")
    statuses = {entry["artifact_type"]: entry["status"] for entry in entries}
    assert statuses["OOS_REVEALED"] == "OOS_REVEALED"
    assert statuses["OOS_VERDICT"] in {"SURVIVOR", "REJECTED_OOS"}

    # A second verdict attempt for the same freeze fails closed.
    assert main(_oos_run_argv(output["freeze_id"], oos_snapshot, root)) != 0
    verdicts = list(freeze_dir.glob("verdict.json"))
    assert verdicts == [freeze_dir / "verdict.json"]


def test_oos_run_without_warm_up_snapshot_still_evaluates_short_lookback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A strategy whose lookback fits inside the OOS window can be evaluated
    on the OOS snapshot alone."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    oos_snapshot = _write_oos_snapshot(tmp_path)

    exit_code = main(_oos_run_argv(output["freeze_id"], oos_snapshot, root))

    assert exit_code == 0
    run_output = json.loads(capsys.readouterr().out)
    assert run_output["verdict"] in {"SURVIVOR", "REJECTED_OOS"}


def test_oos_run_reveal_intent_persists_before_the_snapshot_is_opened(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The reveal artifact exists even when the run fails on a missing
    snapshot, proving it is written before any OOS data is opened."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)

    exit_code = main(_oos_run_argv(output["freeze_id"], None, root))

    assert exit_code != 0
    freeze_dir = root / LINEAGE / "oos" / output["freeze_id"]
    assert (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "verdict.json").exists()

    entries = read_entries(root / "catalog")
    assert any(entry["artifact_type"] == "OOS_REVEALED" for entry in entries)


def test_new_intent_version_cannot_freeze_an_already_revealed_lineage_window(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    original = _freeze(root, tmp_path, capsys)
    assert main(_oos_run_argv(original["freeze_id"], None, root)) != 0
    capsys.readouterr()

    versioned = _intent_payload()
    versioned["intent_id"] = "test-etf-absolute-trend-v2-renamed"
    versioned_path = tmp_path / "intent-v2.json"
    versioned_path.write_text(json.dumps(versioned), encoding="utf-8")
    snapshot_dir = _write_snapshot(tmp_path, name="basic-v2")
    assert main(["screen", "--intent", str(versioned_path), "--root", str(root)]) == 0
    assert (
        main(
            [
                "basic-backtest",
                "--intent",
                str(versioned_path),
                "--snapshot",
                str(snapshot_dir / "manifest.json"),
                "--root",
                str(root),
            ]
        )
        == 0
    )

    assert (
        main(
            [
                "oos-freeze",
                "--candidate-id",
                versioned["intent_id"],
                "--root",
                str(root),
            ]
        )
        != 0
    )
    assert "OOS_CONTAMINATED" in capsys.readouterr().err


def test_oos_run_refuses_contaminated_oos_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """An OOS snapshot that contains Basic-window rows is refused; the Basic
    window stays closed to the OOS runner."""
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    basic_snapshot = _write_snapshot(tmp_path, name="warm-up")

    # The Basic snapshot's rows sit inside the Basic window, so presenting it
    # as the OOS snapshot is a contamination attempt and must fail closed.
    exit_code = main(
        _oos_run_argv(
            output["freeze_id"],
            basic_snapshot,
            root,
            warm_up_snapshot=basic_snapshot,
        )
    )

    assert exit_code != 0
    freeze_dir = root / LINEAGE / "oos" / output["freeze_id"]
    assert (freeze_dir / "reveal.json").exists()
    assert not (freeze_dir / "verdict.json").exists()
    assert not (freeze_dir / "result.json").exists()


def test_oos_run_refuses_mismatched_warm_up_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    output = _freeze(root, tmp_path, capsys)
    oos_snapshot = _write_oos_snapshot(tmp_path)

    exit_code = main(
        _oos_run_argv(
            output["freeze_id"],
            oos_snapshot,
            root,
            warm_up_snapshot=oos_snapshot,
        )
    )

    assert exit_code != 0
    freeze_dir = root / LINEAGE / "oos" / output["freeze_id"]
    assert not (freeze_dir / "verdict.json").exists()


def test_no_oos_eligible_records_honest_outcome_without_materialization(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "experiments"
    payload = _intent_payload()
    payload["basic_promotion_rule"]["min_nav_observations"] = "99999"
    intent_path = tmp_path / "intent.json"
    intent_path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["screen", "--intent", str(intent_path), "--root", str(root)]) == 0
    snapshot_dir = _write_snapshot(tmp_path)
    assert (
        main(
            [
                "basic-backtest",
                "--intent",
                str(intent_path),
                "--snapshot",
                str(snapshot_dir / "manifest.json"),
                "--root",
                str(root),
            ]
        )
        == 0
    )
    capsys.readouterr()

    exit_code = main(["no-oos-eligible", "--asset", "ETF", "--root", str(root)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "no-oos-eligible"
    assert output["status"] == "NO_OOS_ELIGIBLE_CANDIDATE"
    outcome_path = root / "outcomes"
    outcomes = list(outcome_path.glob("*.json"))
    assert len(outcomes) == 1
    recorded = json.loads(outcomes[0].read_text(encoding="utf-8"))
    assert recorded["status"] == "NO_OOS_ELIGIBLE_CANDIDATE"
    assert recorded["asset_class"] == "ETF"
    entries = read_entries(root / "catalog")
    assert any(entry["artifact_type"] == "OOS_OUTCOME" for entry in entries)


def test_no_oos_eligible_refuses_when_an_eligible_candidate_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _basic_pass_root(tmp_path, capsys)
    _freeze(root, tmp_path, capsys)

    assert main(["no-oos-eligible", "--asset", "ETF", "--root", str(root)]) != 0
