"""Contract tests for the isolated Free Eastmoney block-trade adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _row(**overrides):
    row = {
        "ID": "trade-1",
        "TRADE_DATE": "2026-08-31 00:00:00",
        "SECURITY_CODE": "000001",
        "SECURITY_NAME_ABBR": "平安银行",
        "DEAL_PRICE": 10.0,
        "DEAL_VOLUME": 200.0,
        "DEAL_AMT": 2000.0,
        "PREMIUM_RATIO": -5.0,
        "BUYER_NAME": "买方营业部",
        "SELLER_NAME": "卖方营业部",
    }
    row.update(overrides)
    return row


def _payload(rows, *, pages=1):
    return {"success": True, "result": {"data": rows, "pages": pages, "count": len(rows)}}


def _fetch(monkeypatch, payloads, **kwargs):
    from chstockdata import block_trades

    calls = []

    def fake_em_get(url, *, params, **request_kwargs):
        calls.append((url, params, request_kwargs))
        item = payloads.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Response(item)

    monkeypatch.setattr(block_trades, "_em_get", fake_em_get)
    result = block_trades.fetch_free_block_trades(
        "000001", "2026-08-01", "2026-08-31", **kwargs
    )
    return result, calls


def test_uses_the_existing_eastmoney_throttled_request_helper():
    from chstockdata import a_stock, block_trades

    assert block_trades._em_get is a_stock._em_get


def test_request_avoids_an_unverified_source_id_column(monkeypatch):
    _result, calls = _fetch(monkeypatch, [_payload([], pages=1)])

    params = calls[0][1]
    assert "ID" not in params["columns"].split(",")
    # Pagination needs a deterministic total order: TRADE_DATE alone leaves many
    # rows tied within one date, and the report has no stable record ID, so a
    # page boundary could duplicate or skip a row undetectably.
    assert params["sortColumns"] == "TRADE_DATE,DAILY_RANK"
    assert params["sortTypes"] == "-1,1"


def test_normalizes_verified_eastmoney_share_yuan_units_and_keeps_raw_unit_evidence(monkeypatch):
    result, _calls = _fetch(monkeypatch, [_payload([_row()])])

    trade = result.records[0]
    assert trade["deal_quantity_shares"] == 200
    assert trade["deal_amount_cny"] == 2_000
    assert trade["raw_values"] == {"deal_volume": 200.0, "deal_amount": 2000.0}
    assert trade["raw_units"] == {
        "deal_volume": "股",
        "deal_amount": "元",
        "deal_price": "元/股",
        "premium_ratio": "小数比率",
    }
    assert trade["amount_check"] == {
        "price_times_quantity_cny": 2_000.0,
        "reported_amount_cny": 2_000.0,
        "difference_cny": 0.0,
        "comparison": "within_source_rounding_tolerance",
    }


def test_amount_mismatch_is_retained_not_adjusted_to_force_an_equation(monkeypatch):
    result, _calls = _fetch(
        monkeypatch, [_payload([_row(DEAL_AMT=1800.0)])]
    )

    check = result.records[0]["amount_check"]
    assert check["reported_amount_cny"] == 1_800.0
    assert check["price_times_quantity_cny"] == 2_000.0
    assert check["difference_cny"] == 200.0
    assert check["comparison"] == "outside_source_rounding_tolerance"


def test_source_premium_ratio_preserves_source_definition_and_sign(monkeypatch):
    result, _calls = _fetch(monkeypatch, [_payload([_row(PREMIUM_RATIO=-0.05)])])

    premium = result.records[0]["premium"]
    assert premium == {
        "ratio_pct": pytest.approx(-5.0),
        "source": "eastmoney_PREMIUM_RATIO",
        "definition": "Eastmoney source field; the provider decimal fraction is converted to percentage points. Source sign convention retained (positive premium, negative discount).",
        "reference_price": None,
        "reference_date": None,
        "formula": "eastmoney_PREMIUM_RATIO * 100",
    }


def test_live_calibrated_source_premium_fraction_is_converted_to_percent(monkeypatch):
    # Live field probe 2026-09-11: 301358 traded at 45.43 against a 53.45
    # close and Eastmoney returned PREMIUM_RATIO=-0.150046772685 (-15.00%).
    result, _calls = _fetch(
        monkeypatch,
        [_payload([_row(DEAL_PRICE=45.43, PREMIUM_RATIO=-0.150046772685)])],
    )

    premium = result.records[0]["premium"]
    assert premium["ratio_pct"] == pytest.approx(-15.0046772685, abs=1e-9)
    assert premium["source"] == "eastmoney_PREMIUM_RATIO"
    assert premium["formula"] == "eastmoney_PREMIUM_RATIO * 100"


def test_missing_source_premium_uses_same_day_unadjusted_reference_only(monkeypatch):
    calls = []

    def reference_price(ticker, trade_date):
        calls.append((ticker, trade_date))
        return 12.0, "2026-08-31"

    result, _calls = _fetch(
        monkeypatch,
        [_payload([_row(PREMIUM_RATIO=None)])],
        reference_price_lookup=reference_price,
    )

    premium = result.records[0]["premium"]
    assert calls == [("000001", "2026-08-31")]
    assert premium["ratio_pct"] == pytest.approx((10 / 12 - 1) * 100)
    assert premium["source"] == "calculated_same_day_unadjusted_reference"
    assert premium["reference_price"] == 12.0
    assert premium["reference_date"] == "2026-08-31"
    assert premium["formula"] == "(deal_price / unadjusted_reference_price - 1) * 100"


def test_missing_reference_keeps_premium_missing_without_realtime_substitution(monkeypatch):
    result, _calls = _fetch(
        monkeypatch,
        [_payload([_row(PREMIUM_RATIO=None)])],
        reference_price_lookup=lambda *_args: None,
    )

    assert result.records[0]["premium"]["ratio_pct"] is None
    assert result.records[0]["premium"]["source"] == "unavailable"
    assert result.records[0]["premium"]["reference_price"] is None


def test_filters_window_and_future_rows_without_fabricating_time_precision(monkeypatch):
    result, _calls = _fetch(
        monkeypatch,
        [_payload([
            _row(ID="before", TRADE_DATE="2026-07-31 00:00:00"),
            _row(ID="future", TRADE_DATE="2026-09-01 00:00:00"),
            _row(ID="valid", TRADE_DATE="2026-08-31 15:30:00"),
        ])],
        now=datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc),
    )

    assert [trade["source_record_id"] for trade in result.records] == ["valid"]
    assert result.records[0]["trade_date"] == "2026-08-31"
    assert "trade_time" not in result.records[0]
    assert result.evidence.completeness == "partial"
    assert any("out-of-window or future" in item for item in result.evidence.limitations)


def test_paginates_deduplicates_only_stable_ids_and_preserves_same_valued_rows(monkeypatch):
    first = _row(ID="stable-1")
    same_values_no_id = _row(ID=None, BUYER_NAME=None, SELLER_NAME=None)
    result, calls = _fetch(
        monkeypatch,
        [_payload([first, same_values_no_id], pages=2), _payload([first, same_values_no_id], pages=2)],
    )

    assert len(calls) == 2
    assert [call[1]["pageNumber"] for call in calls] == ["1", "2"]
    assert [trade["source_record_id"] for trade in result.records] == ["stable-1", None, None]
    assert result.records[1]["buyer_name"] is None
    assert result.records[1]["seller_name"] is None
    assert any("stable source ID" in item for item in result.evidence.limitations)


def test_max_page_truncation_is_partial_not_full(monkeypatch):
    result, _calls = _fetch(
        monkeypatch, [_payload([_row()], pages=3)], max_pages=1
    )

    assert result.evidence.completeness == "partial"
    assert result.evidence.final_status == "success"
    assert any("max_pages" in item for item in result.evidence.limitations)


def test_mid_pagination_network_failure_retains_partial_rows_and_failure_attempt(monkeypatch):
    result, _calls = _fetch(
        monkeypatch,
        [_payload([_row()], pages=2), ConnectionError("offline")],
    )

    assert len(result.records) == 1
    assert result.evidence.completeness == "partial"
    # EvidenceEnvelope derives its terminal provider from the last successful
    # page, while the failed second page remains explicit degradation evidence.
    assert result.evidence.final_status == "success"
    assert result.evidence.is_degraded is True
    assert result.evidence.attempts[-1].status == "failed_network"


def test_complete_confirmed_empty_window_is_normal_empty(monkeypatch):
    result, calls = _fetch(monkeypatch, [_payload([], pages=1)])

    assert result.records == ()
    assert result.evidence.completeness == "full"
    assert result.evidence.final_status == "normal_empty"
    assert result.evidence.attempts[-1].record_count == 0
    assert calls[0][1]["reportName"] == "RPT_DATA_BLOCKTRADE"
    assert "SECURITY_CODE=\"000001\"" in calls[0][1]["filter"]
    assert "TRADE_DATE>='2026-08-01'" in calls[0][1]["filter"]
    assert "TRADE_DATE<='2026-08-31'" in calls[0][1]["filter"]


def test_eastmoney_code_9201_no_data_response_is_a_confirmed_normal_empty(monkeypatch):
    # Field probe: datacenter returns this shape for a completed query with no
    # matching rows, rather than result.data=[]; code=9201 plus the exact
    # message is the current source confirmation.
    result, _calls = _fetch(
        monkeypatch,
        [{"code": 9201, "success": False, "message": "返回数据为空", "result": None}],
    )

    assert result.records == ()
    assert result.evidence.completeness == "full"
    assert result.evidence.final_status == "normal_empty"


def test_nonempty_success_false_response_is_structure_failure(monkeypatch):
    result, _calls = _fetch(
        monkeypatch,
        [{"success": False, "result": {"data": [], "pages": 1, "count": 0}}],
    )
    assert result.evidence.final_status == "recoverable_failure"


def test_enforces_bounded_window_and_pagination_inputs():
    from chstockdata import block_trades

    with pytest.raises(ValueError):
        block_trades.fetch_free_block_trades("000001", "2025-01-01", "2026-02-01")
    with pytest.raises(ValueError):
        block_trades.fetch_free_block_trades("000001", "2026-08-01", "2026-08-31", page_size=501)
    with pytest.raises(ValueError):
        block_trades.fetch_free_block_trades("000001", "2026-08-01", "2026-08-31", max_pages=11)


def test_count_mismatch_and_missing_core_numbers_are_partial(monkeypatch):
    result, _calls = _fetch(
        monkeypatch,
        [{"success": True, "result": {"data": [_row(DEAL_AMT=None)], "pages": 1, "count": 2}}],
    )
    assert result.records == ()
    assert result.evidence.completeness == "partial"


def test_future_window_cannot_be_claimed_as_a_complete_normal_empty(monkeypatch):
    from chstockdata import block_trades

    monkeypatch.setattr(
        block_trades,
        "_em_get",
        lambda *_args, **_kwargs: _Response(
            {"code": 9201, "success": False, "message": "返回数据为空", "result": None}
        ),
    )
    result = block_trades.fetch_free_block_trades(
        "000001",
        "2026-08-01",
        "2026-09-01",
        now=datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc),
    )

    assert result.records == ()
    assert result.evidence.completeness == "partial"
    assert result.evidence.final_status != "normal_empty"
    assert any("future" in item for item in result.evidence.limitations)


@pytest.mark.parametrize(
    "payload,error_status",
    [
        ({}, "failed_structure"),
        ({"result": {}}, "failed_structure"),
        ({"result": {"data": "not-a-list", "pages": 1}}, "failed_structure"),
    ],
)
def test_empty_or_malformed_payload_is_structure_failure_not_normal_empty(
    monkeypatch, payload, error_status
):
    result, _calls = _fetch(monkeypatch, [payload])

    assert result.records == ()
    assert result.evidence.final_status == "recoverable_failure"
    assert result.evidence.attempts[-1].status == error_status


def test_invalid_json_is_structure_failure_not_network_failure(monkeypatch):
    from chstockdata import block_trades

    class BrokenJsonResponse:
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(block_trades, "_em_get", lambda *_args, **_kwargs: BrokenJsonResponse())
    result = block_trades.fetch_free_block_trades("000001", "2026-08-01", "2026-08-31")

    assert result.evidence.final_status == "recoverable_failure"
    assert result.evidence.attempts[-1].status == "failed_structure"


def test_network_failure_is_not_cached_or_misreported_as_empty(monkeypatch):
    result, _calls = _fetch(monkeypatch, [ConnectionError("offline")])

    assert result.records == ()
    assert result.evidence.final_status == "recoverable_failure"
    assert result.evidence.attempts[-1].status == "failed_network"
    assert result.cacheable is False


def test_records_include_source_fetch_time_and_full_coverage_metadata(monkeypatch):
    fetched_at = datetime(2026, 9, 1, 1, 2, 3, tzinfo=timezone.utc)
    result, _calls = _fetch(
        monkeypatch, [_payload([_row()])], now=fetched_at
    )

    trade = result.records[0]
    assert trade["source"] == "eastmoney_datacenter:RPT_DATA_BLOCKTRADE"
    assert trade["fetched_at"] == "2026-09-01T01:02:03+00:00"
    assert trade["coverage_status"] == "full"
    assert result.cacheable is True
