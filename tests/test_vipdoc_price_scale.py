"""v0.4.2 price-scale acceptance: real raw bytes, independent price literals."""

import hashlib
import io
import json
import struct
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from chstockdata import vipdoc_history as vh

GOLDEN = json.loads(
    (Path(__file__).parent / 'fixtures/vipdoc/price_scale_20221230.json').read_text(
        encoding='utf-8'
    )
)["fixtures"]
OHLC = ["Open", "High", "Low", "Close"]


@pytest.fixture(params=GOLDEN, ids=lambda item: item["code"])
def golden(request, tmp_path):
    item = request.param
    path = tmp_path / item["market"] / "lday" / f'{item["market"]}{item["code"]}.day'
    path.parent.mkdir(parents=True)
    raw = bytes.fromhex(item["raw_hex"])
    assert hashlib.sha256(raw).hexdigest() == item["raw_sha256"]
    path.write_bytes(raw)
    return item, path, tmp_path


def _assert_target(frame, item):
    row = frame.loc[frame["Date"] == pd.Timestamp("2022-12-30")].iloc[0]
    assert row[OHLC].tolist() == pytest.approx(item["expected_ohlc"], abs=1e-10, rel=0)
    assert row["pre_close"] == pytest.approx(item["expected_pre_close"], abs=1e-10, rel=0)
    assert row["Volume"] == item["expected_volume"]
    if "Amount" in frame:
        assert row["Amount"] == item["expected_amount"]


def test_real_raw_parse_and_filtered_pre_close(golden):
    item, path, root = golden
    full = vh.parse_day_file(path)
    assert len(full) == 2
    assert pd.isna(full.iloc[0]["pre_close"])
    _assert_target(full, item)
    window = vh.load_vipdoc_daily(item["code"], "2022-12-30", "2022-12-30", root=root)
    assert len(window) == 1
    _assert_target(window, item)


def test_real_raw_prices_match_exact_decimal_contract(golden):
    item, _, root = golden
    frame = vh.load_vipdoc_daily(item["code"], "2022-12-30", "2022-12-30", root=root)
    row = frame.iloc[0]
    actual = [Decimal(str(row[column])) for column in [*OHLC, "pre_close"]]
    expected = [Decimal(str(value)) for value in [*item["expected_ohlc"], item["expected_pre_close"]]]
    assert actual == expected


@pytest.mark.parametrize("filename, denominator", [
    ("sh600519.day", 100), ("sh688001.day", 100),
    ("sz000001.day", 100), ("sz300001.day", 100),
    ("sh500001.day", 1000), ("sh510300.day", 1000),
    ("sz159915.day", 1000), ("sz160001.day", 1000),
])
def test_qualified_ohlc_and_pre_close_have_no_reciprocal_tail(tmp_path, filename, denominator):
    path = tmp_path / filename
    path.write_bytes(b"".join(
        struct.pack("<IIIIIfII", session, 3937, 3937, 3937, 3937, 25.0, 10, 0)
        for session in (20221229, 20221230)
    ))
    frame = vh.parse_day_file(path)
    row = frame.iloc[1]
    expected = Decimal(3937) / Decimal(denominator)
    assert [Decimal(str(row[column])) for column in [*OHLC, "pre_close"]] == [expected] * 5
    assert all(frame[column].dtype.kind == "f" for column in [*OHLC, "pre_close"])
    assert row["Volume"] == 10 and row["Amount"] == 25.0


@pytest.mark.allow_vipdoc_history
def test_real_raw_structured_and_legacy_apis(golden, monkeypatch):
    from chstockdata import a_stock, config, daily_bars

    item, _, root = golden
    monkeypatch.setattr(config, "get_config", lambda: {
        "vipdoc_history_enabled": True,
        "vipdoc_history_dir": str(root),
        "vipdoc_history_max_staleness_days": 5,
    })

    def unexpected(*args, **kwargs):
        pytest.fail("golden local coverage must not invoke online providers")

    monkeypatch.setattr(a_stock, "_fetch_mootdx_bars", unexpected)
    monkeypatch.setattr(a_stock, "_sina_kline_fallback", unexpected)
    result = daily_bars.fetch_daily_bars(item["code"], "2022-12-30", "2022-12-30")
    assert result.succeeded
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.data.attrs["volume_unit"] == "shares"
    _assert_target(result.data, item)
    text = a_stock.get_stock_data(item["code"], "2022-12-30", "2022-12-30")
    assert "# Data source: vipdoc local (TDX official hsjday package)" in text
    csv = pd.read_csv(io.StringIO(text), comment="#")
    assert list(csv.columns) == ["Date", *OHLC, "Volume"]
    assert csv.iloc[0][OHLC].tolist() == pytest.approx(
        pd.Series(item["expected_ohlc"]).round(2).tolist(), abs=1e-10, rel=0
    )
    assert csv.iloc[0]["Volume"] == item["expected_volume"]


@pytest.mark.parametrize("filename, multiplier", [
    ("sh600519.day", 0.01), ("sh688001.day", 0.01),
    ("sz000001.day", 0.01), ("sz300001.day", 0.01),
    ("sh500001.day", 0.001), ("sh510300.day", 0.001),
    ("sz159915.day", 0.001), ("sz160001.day", 0.001),
    ("SH510300.day", 0.001),
    ("bj920185.day", None), ("bj430001.day", None), ("bj830001.day", None),
    ("sh580001.day", None), ("sz180001.day", None), ("sh000001.day", None),
    ("sz399001.day", None), ("sh900001.day", None), ("sz200001.day", None),
    ("sz510300.day", None), ("sh159915.day", None), ("bj510300.day", None),
    ("xx510300.day", None), ("510300.day", None), ("sh51030.day", None),
    ("sh5103000.day", None), ("sh51abcd.day", None), ("sh５１０３００.day", None),
    ("sh510300.extra.day", None), ("sh510300.dat", None),
])
def test_qualified_boundary_and_legacy_scale(tmp_path, filename, multiplier):
    path = tmp_path / filename
    path.write_bytes(struct.pack("<IIIIIfII", 20221230, 128947, 129292, 128900, 129104, 25.0, 10, 0))
    assert vh._qualified_price_multiplier(path) == multiplier
    frame = vh.parse_day_file(path)
    expected = [128.947, 129.292, 128.900, 129.104] if multiplier == 0.001 else [1289.47, 1292.92, 1289.0, 1291.04]
    assert frame.iloc[0][OHLC].tolist() == pytest.approx(expected, abs=1e-10, rel=0)
    assert frame.iloc[0]["Volume"] == 10
    assert frame.iloc[0]["Amount"] == 25.0


@pytest.mark.parametrize("market, code", [
    ("bj", "920185"), ("bj", "430001"), ("bj", "830001"),
    ("sh", "580001"), ("sz", "180001"), ("sh", "000001"),
])
def test_legacy_loader_retains_ohlc_and_pre_close(tmp_path, market, code):
    path = tmp_path / market / "lday" / f"{market}{code}.day"
    path.parent.mkdir(parents=True)
    path.write_bytes(bytes.fromhex(GOLDEN[-1]["raw_hex"]))
    frame = vh.load_vipdoc_daily(code, "2022-12-30", "2022-12-30", root=tmp_path, market=market)
    assert len(frame) == 1
    assert frame.iloc[0][OHLC].tolist() == pytest.approx([1289.47, 1292.92, 1289.0, 1291.04])
    assert frame.iloc[0]["pre_close"] == pytest.approx(1288.97)


def test_etf_sort_deduplicate_invalid_records_and_window(tmp_path, caplog):
    path = tmp_path / "sh" / "lday" / "sh510300.day"
    path.parent.mkdir(parents=True)
    raw = bytes.fromhex(GOLDEN[1]["raw_hex"])
    path.write_bytes(raw[32:] + bytes(32) + raw[:32] + raw[32:] + bytes(8))
    full = vh.parse_day_file(path)
    assert full["Date"].tolist() == list(pd.to_datetime(["2022-12-29", "2022-12-30"]))
    assert "skipped 2 invalid records" in caplog.text
    _assert_target(full, GOLDEN[1])
    assert vh.load_vipdoc_daily("510300", "2023-01-01", root=tmp_path).empty
