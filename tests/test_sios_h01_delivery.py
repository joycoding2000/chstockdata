"""Research-only H01 export regressions, with no network or SIOS execution."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/audits/evidence/2026-10-22-sios-h01-priority-delivery"


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_official_download_zip_is_read_as_single_pdf_without_extracting():
    extractor = load_script(EVIDENCE / "extract_reports.py")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("report.pdf", b"%PDF-1.7\ncontent")
    assert extractor.report_pdf_bytes(stream.getvalue()) == b"%PDF-1.7\ncontent"


def test_report_download_rejects_html_even_with_pdf_mime():
    extractor = load_script(EVIDENCE / "extract_reports.py")
    with pytest.raises(ValueError, match="not a PDF"):
        extractor.report_pdf_bytes(b"<script>document.cookie='challenge';</script>")


def test_report_download_rejects_ambiguous_archive():
    extractor = load_script(EVIDENCE / "extract_reports.py")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("first.pdf", b"%PDF-1.7\nfirst")
        archive.writestr("second.pdf", b"%PDF-1.7\nsecond")
    with pytest.raises(ValueError, match="exactly one"):
        extractor.report_pdf_bytes(stream.getvalue())


def test_official_word_attachment_preserves_table_cell_order():
    extractor = load_script(EVIDENCE / "extract_reports.py")
    stream = io.BytesIO()
    document = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body><w:p><w:r><w:t>Annual report</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Split</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>0</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document)
    kind, blocks = extractor.report_text_blocks(stream.getvalue())
    assert kind == "ooxml_body_block"
    assert blocks == ["Annual report", "Split\t0"]


def test_raw_fund_units_and_zero_turnover_are_lossless(tmp_path):
    builder = load_script(EVIDENCE / "build_delivery.py")
    path = tmp_path / "sh513030.day"
    path.write_bytes(struct.pack("<IIIIIfII", 20250123, 1815, 1815, 1815, 1815, 0, 0, 0))
    row = builder.read_day(path, "513030")[0]
    assert row["close"] == "1.815"
    assert row["volume"] == 0 and row["amount"] == "0"
    assert row["trade_status"] == "NO_TRADE_RECORDED"
    assert row["suspension_status"] == "UNKNOWN"


def test_export_rejects_duplicate_or_truncated_raw_records(tmp_path):
    builder = load_script(EVIDENCE / "build_delivery.py")
    path = tmp_path / "sh513500.day"
    bar = struct.pack("<IIIIIfII", 20240102, 1000, 1000, 1000, 1000, 100, 100, 0)
    path.write_bytes(bar * 2)
    with pytest.raises(ValueError, match="date order"):
        builder.read_day(path, "513500")
    path.write_bytes(bar + b"x")
    with pytest.raises(ValueError, match="alignment"):
        builder.read_day(path, "513500")


def test_calendar_reference_uses_dates_without_qualifying_unused_index_prices(tmp_path):
    builder = load_script(EVIDENCE / "build_delivery.py")
    path = tmp_path / "sh000001.day"
    path.write_bytes(struct.pack("<IIIIIfII", 19901219, 0, 0, 0, 0, 0, 0, 0))
    assert builder.read_day(path, "000001")[0]["date"] == "1990-12-19"


def test_frozen_126_observations_use_125_intervals_and_sma_uses_200():
    builder = load_script(EVIDENCE / "build_delivery.py")
    values = list(map(str, range(1, 202)))
    result = builder.window_inputs(values)
    assert result["return_126"] == str((builder.D(201) / builder.D(76)) - 1)
    assert result["sma_200"] == "101.5"
    assert builder.window_inputs(values[:125])["return_126"] is None
    assert builder.window_inputs(values[:199])["sma_200"] is None


def test_future_and_unknown_events_fail_closed():
    builder = load_script(EVIDENCE / "build_delivery.py")
    future = {"announcement_date": "2025-01-24", "status": "implemented"}
    with pytest.raises(ValueError, match="FUTURE_INFORMATION"):
        builder.guard_no_event_input([future], "2025-01-23")
    with pytest.raises(ValueError, match="REQUIRES_EVENT_QUALIFICATION"):
        builder.guard_no_event_input([{"status": "unknown"}], "2025-01-23")


def test_actual_issuer_reports_have_cash_and_split_negative_evidence():
    builder = load_script(EVIDENCE / "build_delivery.py")
    records = []
    for path in (EVIDENCE / "extracted").glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        records.append(builder.negative_evidence(report))
    assert len(records) == 9
    assert all(record["cash_status"] == "normal_empty" for record in records)
    assert all(record["split_status"] == "normal_empty" for record in records)
    assert all(record["cash_evidence"] and record["split_evidence"] for record in records)


@pytest.mark.parametrize("event,expected", [
    ({"instrument_id": "XSHG:513500", "status": "implemented", "announcement_date": "2025-01-24", "ex_dividend_date": "2025-01-23"}, "future announcement rejection"),
    ({"instrument_id": "XSHG:513500", "status": "unknown"}, "unknown event rejection"),
])
def test_receiver_rejects_future_announcement_in_an_actual_export(tmp_path, event, expected):
    receiver = load_script(EVIDENCE / "receive_delivery.py")
    package = tmp_path / "H01-delivery"
    shutil.copytree(EVIDENCE / "H01-delivery", package)
    actions_path = package / "fund_actions.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8"))
    actions["events"] = [event]
    actions_path.write_text(json.dumps(actions), encoding="utf-8")
    report = receiver.receive(package)
    assert report["integrity_and_recomputation"] == "FAIL"
    assert expected in report["errors"]
