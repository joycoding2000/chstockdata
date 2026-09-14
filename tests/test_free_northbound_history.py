"""F5 独立北向公开数据、SQLite 迁移与失败语义回归。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chstockdata.northbound_data import (
    NorthboundRecord,
    fetch_hkex_quarterly_holdings,
    fetch_sse_northbound_turnover,
    fetch_szse_northbound_turnover,
    northbound_availability_catalog,
)
from chstockdata.northbound_store import (
    NorthboundArchiveError,
    NorthboundStore,
)


class _Response:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _sse_payload(date: str = "2026-09-08") -> str:
    return "cb(" + json.dumps(
        {
            "quatationInfo": "success",
            "result": [
                {
                    "TRADE_DATE": date,
                    "TOTAL_AMOUNT": "585.99",
                    "TOTAL_VOLUME": "123.34",
                    "ETF_TOTAL_AMOUNT": "6.11",
                    # 旧接口仍可能回传，不得写入北向结果。
                    "BUY_AMOUNT": "310.28",
                    "SELL_AMOUNT": "275.71",
                }
            ],
        },
        ensure_ascii=False,
    ) + ")"


def _hkex_page(date: str = "2026/06/30") -> str:
    return f"""
    <input name="__VIEWSTATE" value="state" />
    <input name="__VIEWSTATEGENERATOR" value="generator" />
    <input name="originalShareholdingDate" value="2026/09/07" />
    <h3>Shareholding Date: {date}</h3>
    <table>
      <tr><th>Stock Code</th><th>Name</th><th>Shareholding in CCASS</th><th>%</th></tr>
      <tr><td>Stock Code: 10000</td><td>Name: TEST CO (A #600519)</td>
          <td>Shareholding in CCASS: 12,345</td><td>1.23%</td></tr>
    </table>
    """


def _szse_payload(date: str = "2026-09-09") -> str:
    return json.dumps(
        [
            {
                "metadata": {
                    "catalogid": "SGT_SGTJYRB",
                    "name": "深股通交易日报",
                    "subname": date,
                    "tabkey": "tab1",
                },
                "data": [
                    {"label": "当日交易总额（亿元人民币）", "total": "1,315.95"},
                    {"label": "当日交易总笔数（万笔）", "total": "635.07"},
                    {"label": "当日ETF交易总额（亿元人民币）", "total": "20.07"},
                ],
                "error": None,
            }
        ],
        ensure_ascii=False,
    )


def _szse_records(date: str = "2026-09-09") -> list[NorthboundRecord]:
    result = fetch_szse_northbound_turnover(
        date,
        date,
        http_get=lambda *_args, **_kwargs: _Response(_szse_payload(date)),
        observed_at="2026-09-10T01:02:03+00:00",
    )
    return result.records


def _turnover_records() -> list[NorthboundRecord]:
    result = fetch_sse_northbound_turnover(
        "2026-09-08",
        "2026-09-08",
        http_get=lambda *_args, **_kwargs: _Response(_sse_payload()),
        observed_at="2026-09-09T01:02:03+00:00",
    )
    return result.records


def _holding_records() -> list[NorthboundRecord]:
    result = fetch_hkex_quarterly_holdings(
        "northbound_sh",
        shareholding_date="2026-06-30",
        http_get=lambda *_args, **_kwargs: _Response(_hkex_page()),
        http_post=lambda *_args, **_kwargs: _Response(_hkex_page()),
        observed_at="2026-09-09T01:02:03+00:00",
    )
    return result.records


def test_catalog_states_disclosure_frequency_and_unavailable_metrics():
    catalog = {item["metric"]: item for item in northbound_availability_catalog()}
    assert catalog["turnover_total"]["frequency"] == "trading_day"
    assert catalog["turnover_total"]["market_scope"] == "northbound_sh,northbound_sz"
    assert catalog["holding_shares"]["frequency"] == "quarterly"
    assert catalog["net_buy"]["availability"] == "unavailable"
    assert catalog["quota_balance"]["availability"] == "unavailable"
    assert catalog["holding_shares"]["backfill"] == "bounded_12_months"


def test_turnover_keeps_trade_date_observation_and_metric_definitions_separate():
    records = _turnover_records()
    assert {(r.metric, r.unit, r.market_scope) for r in records} == {
        ("turnover_total", "CNY_100M", "northbound_sh"),
        ("turnover_trade_count", "COUNT_10000_TRADES", "northbound_sh"),
        ("turnover_etf", "CNY_100M", "northbound_sh"),
    }
    total = next(record for record in records if record.metric == "turnover_total")
    assert total.as_of_date == "2026-09-08"
    assert total.disclosed_at is None
    assert total.disclosure_time_precision == "date"
    assert total.observed_at == "2026-09-09T01:02:03+00:00"
    assert total.value == 585.99
    assert all(record.metric not in {"net_buy", "buy_amount", "sell_amount"} for record in records)


def test_holding_snapshot_has_quarterly_as_of_date_and_unknown_time_precision():
    records = _holding_records()
    shares = next(record for record in records if record.metric == "holding_shares")
    percent = next(record for record in records if record.metric == "holding_percent")
    assert shares.security_id == "600519"
    assert shares.as_of_date == "2026-06-30"
    assert shares.value == 12345
    assert shares.market_scope == "northbound_sh"
    assert shares.coverage == "ccass_participants_aggregate_sse_a_shares"
    assert shares.disclosure_time_precision == "unknown"
    assert percent.value == pytest.approx(1.23)
    assert percent.unit == "PERCENT"


def test_hkex_history_request_preserves_requested_date_but_rejects_source_date_mismatch():
    result = fetch_hkex_quarterly_holdings(
        "northbound_sh",
        shareholding_date="2025-12-31",
        http_get=lambda *_args, **_kwargs: _Response(_hkex_page("2026/06/30")),
        http_post=lambda *_args, **_kwargs: _Response(_hkex_page("2026/06/30")),
    )
    assert result.status == "failed"
    assert result.records == []
    assert result.errors[0]["kind"] == "source_date_mismatch"


def test_turnover_distinguishes_normal_empty_network_failure_malformed_and_partial_pages():
    empty = fetch_sse_northbound_turnover(
        "2026-09-08", "2026-09-08",
        http_get=lambda *_args, **_kwargs: _Response('cb({"result": []})'),
    )
    assert empty.status == "normal_empty"

    failed = fetch_sse_northbound_turnover(
        "2026-09-08", "2026-09-08",
        http_get=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    assert failed.status == "failed"
    assert failed.errors[0]["kind"] == "network_failure"

    malformed = fetch_sse_northbound_turnover(
        "2026-09-08", "2026-09-08",
        http_get=lambda *_args, **_kwargs: _Response("not jsonp"),
    )
    assert malformed.status == "failed"
    assert malformed.errors[0]["kind"] == "structure_error"

    pages = iter([_Response(_sse_payload("2026-09-08")), OSError("offline")])

    def partly_failing_get(*_args, **_kwargs):
        value = next(pages)
        if isinstance(value, Exception):
            raise value
        return value

    partial = fetch_sse_northbound_turnover(
        "2026-09-08", "2026-09-09",
        http_get=partly_failing_get,
    )
    assert partial.status == "partial"
    assert len(partial.records) == 3
    assert partial.complete is False


def test_sse_exchange_holiday_null_row_is_confirmed_empty_not_structure_error():
    # 2026-10-01 is a weekday exchange holiday; live SSE answers with
    # result: [null] rather than [] (live-verified shape on 2026-09-12).
    result = fetch_sse_northbound_turnover(
        "2026-10-01", "2026-10-01",
        http_get=lambda *_args, **_kwargs: _Response('cb({"result": [null]})'),
    )
    assert result.status == "normal_empty"
    assert result.records == []
    assert result.errors == []


def test_turnover_skips_weekends_without_a_request_and_reports_success():
    calls = []

    def get(source_id, url, **kwargs):
        calls.append(kwargs["params"]["tradeDate"])
        return _Response(_sse_payload("2026-09-11"))

    result = fetch_sse_northbound_turnover("2026-09-11", "2026-09-12", http_get=get)
    assert calls == ["20260911"], "2026-09-12 是周六，不得发起请求"
    assert result.status == "success"
    assert result.errors == []
    assert {record.as_of_date for record in result.records} == {"2026-09-11"}


def test_szse_turnover_skips_weekends_without_a_request():
    calls = []

    def get(source_id, url, **kwargs):
        calls.append(kwargs["params"]["txtDate"])
        return _Response(_szse_payload("2026-09-11"))

    result = fetch_szse_northbound_turnover("2026-09-11", "2026-09-13", http_get=get)
    assert calls == ["2026-09-11"], "周六/周日不得发起请求"
    assert result.status == "success"
    assert result.errors == []


def test_pure_weekend_range_is_normal_empty_without_network_calls():
    def get(*_args, **_kwargs):
        raise AssertionError("closed days must not produce a request")

    sse = fetch_sse_northbound_turnover("2026-09-12", "2026-09-13", http_get=get)
    assert sse.status == "normal_empty"
    assert sse.records == []
    assert sse.errors == []

    szse = fetch_szse_northbound_turnover("2026-09-12", "2026-09-13", http_get=get)
    assert szse.status == "normal_empty"
    assert szse.records == []
    assert szse.errors == []


def test_turnover_reuses_injected_existing_http_limiter_entrypoint():
    calls = []
    fetch_sse_northbound_turnover(
        "2026-09-08", "2026-09-08",
        http_get=lambda source_id, url, **kwargs: calls.append((source_id, url, kwargs)) or _Response(_sse_payload()),
    )
    assert calls[0][0] == "sse"
    assert calls[0][2]["params"]["tradeDate"] == "20260908"


def test_szse_turnover_parses_labels_commas_and_sz_scope():
    records = _szse_records()
    assert {(r.metric, r.unit, r.market_scope) for r in records} == {
        ("turnover_total", "CNY_100M", "northbound_sz"),
        ("turnover_trade_count", "COUNT_10000_TRADES", "northbound_sz"),
        ("turnover_etf", "CNY_100M", "northbound_sz"),
    }
    total = next(record for record in records if record.metric == "turnover_total")
    assert total.value == 1315.95
    assert total.as_of_date == "2026-09-09"
    assert total.source_id == "szse_sgt_turnover"
    assert total.source_url.startswith("https://www.szse.cn/")
    assert total.observed_at == "2026-09-10T01:02:03+00:00"
    assert total.disclosure_time_precision == "date"


def test_szse_turnover_reuses_injected_limiter_with_szse_source_and_date_param():
    calls = []
    fetch_szse_northbound_turnover(
        "2026-09-09", "2026-09-09",
        http_get=lambda source_id, url, **kwargs: calls.append((source_id, url, kwargs)) or _Response(_szse_payload()),
    )
    assert calls[0][0] == "szse"
    assert calls[0][1].endswith("/api/report/ShowReport/data")
    assert calls[0][2]["params"]["txtDate"] == "2026-09-09"
    assert calls[0][2]["params"]["CATALOGID"] == "SGT_SGTJYRB"


def test_szse_turnover_distinguishes_empty_mismatch_and_label_drift():
    empty = fetch_szse_northbound_turnover(
        "2026-09-07", "2026-09-07",
        http_get=lambda *_a, **_k: _Response(
            json.dumps([{"metadata": {"tabkey": "tab1", "subname": "2026-09-07"}, "data": [], "error": None}])
        ),
    )
    assert empty.status == "normal_empty"

    mismatch = fetch_szse_northbound_turnover(
        "2026-09-07", "2026-09-07",
        http_get=lambda *_a, **_k: _Response(_szse_payload("2026-09-09")),
    )
    assert mismatch.status == "failed"
    assert mismatch.errors[0]["kind"] == "structure_error"

    drifted = json.loads(_szse_payload())
    drifted[0]["data"].append({"label": "新增神秘指标（亿件）", "total": "1.00"})
    unknown = fetch_szse_northbound_turnover(
        "2026-09-09", "2026-09-09",
        http_get=lambda *_a, **_k: _Response(json.dumps(drifted, ensure_ascii=False)),
    )
    assert unknown.status == "failed"
    assert unknown.errors[0]["kind"] == "structure_error"

    missing = json.loads(_szse_payload())
    missing[0]["data"] = missing[0]["data"][:2]
    absent = fetch_szse_northbound_turnover(
        "2026-09-09", "2026-09-09",
        http_get=lambda *_a, **_k: _Response(json.dumps(missing, ensure_ascii=False)),
    )
    assert absent.status == "failed"
    assert absent.errors[0]["kind"] == "structure_error"


def test_store_keeps_sh_and_sz_turnover_side_by_side_without_collision(tmp_path: Path):
    db = NorthboundStore(tmp_path / "northbound.sqlite3")
    records = _turnover_records() + _szse_records()
    assert db.write(records) == {"inserted": 6, "revised": 0, "unchanged": 0}
    assert db.write(records) == {"inserted": 0, "revised": 0, "unchanged": 6}
    scopes = {
        (row["metric"], row["market_scope"])
        for row in db.query(metric="turnover_total")
    }
    assert scopes == {
        ("turnover_total", "northbound_sh"),
        ("turnover_total", "northbound_sz"),
    }


def test_record_rejects_unknown_metrics_and_missing_observation_time():
    with pytest.raises(ValueError, match="metric"):
        NorthboundRecord(
            metric="net_buy", value=1, unit="CNY_100M", market_scope="northbound_sh",
            as_of_date="2026-09-08", observed_at="2026-09-09T00:00:00+00:00",
            source_id="x", source_url="https://example.invalid", source_fields={},
            coverage="all", disclosure_time_precision="date",
        )
    with pytest.raises(ValueError, match="observed_at"):
        NorthboundRecord(
            metric="turnover_total", value=1, unit="CNY_100M", market_scope="northbound_sh",
            as_of_date="2026-09-08", observed_at="", source_id="x",
            source_url="https://example.invalid", source_fields={}, coverage="all",
            disclosure_time_precision="date",
        )

    # 旧 CSV 缓存只有一个日期/数值对时不得被本模块猜测为今天的可信历史。
    with pytest.raises(ValueError, match="as_of_date"):
        NorthboundRecord(
            metric="turnover_total", value=1, unit="CNY_100M", market_scope="northbound_sh",
            as_of_date="", observed_at="2026-09-09T00:00:00+00:00", source_id="legacy",
            source_url="https://example.invalid", source_fields={"legacy": "unknown"}, coverage="unknown",
            disclosure_time_precision="unknown",
        )


def test_store_is_idempotent_keeps_revisions_and_never_collides_metrics_or_securities(tmp_path: Path):
    db = NorthboundStore(tmp_path / "northbound.sqlite3")
    records = _turnover_records() + _holding_records()
    assert db.write(records) == {"inserted": 5, "revised": 0, "unchanged": 0}
    assert db.write(records) == {"inserted": 0, "revised": 0, "unchanged": 5}
    observed_again = records[0].replace(observed_at="2026-09-09T02:00:00+00:00")
    assert db.write([observed_again]) == {"inserted": 0, "revised": 0, "unchanged": 1}
    revised = records[0].replace(value=600.0, observed_at="2026-09-10T00:00:00+00:00")
    assert db.write([revised]) == {"inserted": 0, "revised": 1, "unchanged": 0}
    current = db.query(metric="turnover_total", market_scope="northbound_sh")
    assert current[0]["value"] == 600.0
    assert current[0]["revision"] == 2
    assert len(db.revisions(current[0]["business_key"])) == 2
    assert len(db.query(metric="holding_shares")) == 1
    assert len(db.query(metric="holding_percent")) == 1


def test_store_validates_before_transaction_and_rolls_back_failed_batch(tmp_path: Path):
    db = NorthboundStore(tmp_path / "northbound.sqlite3")
    valid = _turnover_records()[0]
    with pytest.raises(ValueError):
        db.write([valid, object()])
    assert db.query() == []


def test_export_import_version_checksum_idempotence_and_two_directory_backup_migration(tmp_path: Path):
    directory_a = tmp_path / "a"
    directory_b = tmp_path / "b"
    directory_a.mkdir()
    directory_b.mkdir()
    source = NorthboundStore(directory_a / "northbound.sqlite3")
    source.write(_turnover_records() + _holding_records())
    archive = directory_a / "northbound-export.json"
    backup = directory_a / "northbound-backup.sqlite3"
    source.export_archive(archive)
    source.backup_to(backup)
    assert backup.exists()

    restored = NorthboundStore(directory_b / "northbound.sqlite3")
    assert restored.import_archive(archive) == {"inserted": 5, "revised": 0, "unchanged": 0}
    assert restored.import_archive(archive) == {"inserted": 0, "revised": 0, "unchanged": 5}
    assert restored.query() == source.query()

    payload = json.loads(archive.read_text(encoding="utf-8"))
    payload["format_version"] = 99
    archive.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NorthboundArchiveError, match="format_version"):
        restored.import_archive(archive)
    archive.write_text("{not-json", encoding="utf-8")
    with pytest.raises(NorthboundArchiveError, match="invalid JSON"):
        restored.import_archive(archive)


def test_offline_query_never_fetches_and_keeps_staleness_limit(tmp_path: Path):
    db = NorthboundStore(tmp_path / "northbound.sqlite3")
    db.write(_holding_records())
    rows = db.query(as_of_before="2026-07-01")
    assert rows[0]["as_of_date"] == "2026-06-30"
    assert rows[0]["limitations"]
    assert all("network" not in row for row in rows)
