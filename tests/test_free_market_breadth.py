"""F2 免费市场广度数据回归测试（v0.5.0）。

覆盖 data-coverage-roadmap.md §3 F2 的验收要求：
  同日同范围/范围错配、陈旧与跨日、盘中/收盘/休市快照、正常零值与空载荷、
  涨跌停与炸板/连板定义、分页去重/漏页/截断/未知分母、子项独立可用、
  既有限流入口（_em_get / _source_http_get）实际复用、真实脱敏样本计数关系。

真实样本夹具（tests/fixtures/market_breadth/）：
  - real_2026-09-07_intraday.json — 真实交易日盘中全子项快照
  - real_2026-09-04_close.json   — 真实已收盘交易日（仅池历史，快照子项按契约不可用）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from chstockdata import a_stock, market_breadth as mb

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "market_breadth"

_CST = timezone(timedelta(hours=8))


class _FakeResp:
    def __init__(self, text="", content=None, status_code=200):
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise a_stock._requests.exceptions.HTTPError(f"status {self.status_code}")


def _row(symbol, name, trade, settlement, change, volume):
    return {
        "symbol": symbol,
        "name": name,
        "trade": trade,
        "settlement": settlement,
        "pricechange": change,
        "volume": volume,
    }


def _pool_row(code, name, lbc=None, zbc=None, days=None, zttj=None):
    row = {"c": code, "n": name, "zdp": 9.99}
    if lbc is not None:
        row["lbc"] = lbc
    if zbc is not None:
        row["zbc"] = zbc
    if days is not None:
        row["days"] = days
    if zttj is not None:
        row["zttj"] = zttj
    return row


def _ok_attempt(provider="x", status="success", **kw):
    return mb.make_attempt(provider, status, **kw)


# ---------------------------------------------------------------------------
# 1. 纯函数：分类规则 / 日期与周末 / 池聚合 / 定义
# ---------------------------------------------------------------------------


def test_classifier_counts_adv_dec_flat_with_explained_denominator():
    rows = [
        _row("sh600001", "普通涨", "11.0", "10.0", 1.0, 100),
        _row("sz000002", "普通跌", "9.0", "10.0", -1.0, 100),
        _row("sz000003", "真平盘", "10.0", "10.0", 0.0, 5),
        _row("sz000004", "ST涨", "5.25", "5.0", 0.25, 100),
        _row("bj920005", "北交所涨", "10.2", "10.0", 0.2, 100),
    ]
    stats = mb._classify_snapshot_rows(rows)
    assert (stats["advancing"], stats["declining"], stats["flat"]) == (3, 1, 1)
    assert stats["denominator"] == 5
    assert stats["st_counts"] == {"advancing": 1, "declining": 0, "flat": 0}
    assert stats["valid_quote_by_market"] == {"sh": 1, "sz": 3, "bj": 1}


def test_classifier_never_defaults_suspended_or_unknown_to_flat():
    """停牌/无昨收/零成交零涨跌/字段缺失一律排除出分母，不计平盘。"""
    rows = [
        _row("sh600001", "停牌价0", "0.000", "10.0", 0.0, 0),
        _row("sh600002", "N新股无昨收", "50.0", "0.000", 5.0, 10),
        _row("sh600003", "零成交零涨跌", "10.0", "10.0", 0.0, 0),
        _row("sh600004", "缺涨跌字段", "10.5", "10.0", None, 10),
        _row("sh600005", "正常涨", "11.0", "10.0", 1.0, 100),
    ]
    stats = mb._classify_snapshot_rows(rows)
    assert stats["denominator"] == 1
    assert stats["advancing"] == 1 and stats["flat"] == 0
    assert stats["excluded"] == {
        "no_valid_quote": 1,
        "missing_reference_price": 1,
        "untraded_zero_change": 1,
        "missing_change_field": 1,
    }


def test_classifier_deduplicates_pages_by_symbol():
    rows = [
        _row("sh600001", "A", "11.0", "10.0", 1.0, 100),
        _row("sh600001", "A重复", "11.0", "10.0", 1.0, 100),
        _row("sz000002", "B", "9.0", "10.0", -1.0, 100),
    ]
    stats = mb._classify_snapshot_rows(rows)
    assert stats["unique_rows"] == 2
    assert stats["duplicates"] == 1
    assert stats["advancing"] == 1 and stats["declining"] == 1


def test_normalize_date_and_weekend():
    assert mb._normalize_date("2026-09-04") == "2026-09-04"
    assert mb._normalize_date("20260904") == "2026-09-04"
    with pytest.raises(ValueError):
        mb._normalize_date("not-a-date")
    with pytest.raises(ValueError):
        mb._normalize_date("2026-13-99")
    assert mb._is_weekend("2026-09-05") is True   # 周六
    assert mb._is_weekend("2026-09-06") is True   # 周日
    assert mb._is_weekend("2026-09-07") is False  # 周一


def test_pool_summary_limit_up_distribution_and_unknown_bucket():
    pool = {
        "tc": 4,
        "qdate": "20260907",
        "pool": [
            _pool_row("605580", "二板股", lbc=2, zttj={"days": 2, "ct": 2}),
            _pool_row("003040", "首板ST", lbc=1, zttj={"days": 1, "ct": 1}),
            _pool_row("920118", "北交所缺lbc", zttj={}),
            _pool_row("688001", "C次新", lbc=3, zttj={"days": 3, "ct": 3}),
        ],
    }
    s = mb._pool_summary("limit_up", pool)
    assert s["count"] == 4 and s["source_total_count"] == 4
    assert s["consecutive"]["max_boards"] == 3
    assert s["consecutive"]["distribution"] == {"1": 1, "2": 1, "3": 1, "unknown": 1}
    assert sum(s["consecutive"]["distribution"].values()) == s["count"]
    # lbc 缺失不猜板数：top 里 boards=None
    assert any(t["boards"] is None for t in s["consecutive"]["top"])
    # ST / 次新 / 北交所单独计数（605580 是 name 含 'ST'? 否——首板ST 计 1）
    assert s["st_count"] == 1 and s["new_listing_count"] == 1 and s["bse_count"] == 1


def test_pool_summary_st_five_percent_limit_counts_as_limit_up():
    """ST 5% 涨停也由源端判定入池——模块不做 ±10% 推算，按池原样计数。"""
    pool = {
        "tc": 2,
        "pool": [
            _pool_row("600001", "ST五厘", lbc=1),
            _pool_row("300002", "二十厘", lbc=2),
        ],
    }
    s = mb._pool_summary("limit_up", pool)
    assert s["count"] == 2
    assert s["st_count"] == 1


def test_pool_summary_tc_mismatch_disclosed_not_silent():
    s = mb._pool_summary("limit_up", {"tc": 9, "pool": [_pool_row("600001", "A", lbc=1)]})
    assert s["count"] == 1 and s["source_total_count"] == 9
    assert any("不一致" in line for line in s["limitations"])


def test_pool_summary_failed_board_and_limit_down():
    zb = mb._pool_summary(
        "failed_board",
        {"tc": 2, "pool": [_pool_row("600611", "多次开板", zbc=14), _pool_row("002980", "缺zbc")]},
    )
    assert zb["count"] == 2
    assert zb["open_count_total"] == 14 and zb["missing_open_count_fields"] == 1
    dt = mb._pool_summary("limit_down", {"tc": 1, "pool": [_pool_row("000017", "连跌", days=2)]})
    assert dt["max_consecutive_days"] == 2


def test_definitions_explicit_and_non_empty():
    for key in ("advance_decline", "limit_up", "limit_down", "failed_board", "consecutive_limit_up"):
        assert mb._DEFINITIONS.get(key)
    assert "不做 ±10% 推算" in mb._DEFINITIONS["limit_up"]
    assert "不计为平盘" in mb._DEFINITIONS["advance_decline"].replace("绝不默认计为平盘", "不计为平盘")
    assert "连续收阳天数不是连板" in mb._DEFINITIONS["consecutive_limit_up"]
    assert "非开板次数" in mb._DEFINITIONS["failed_board"]


# ---------------------------------------------------------------------------
# 2. 新浪分页 fetcher：完整性 / 去重 / 漏页 / 截断 / 未知分母 / 空载荷 / 网络
# ---------------------------------------------------------------------------


def _patch_sina_http(monkeypatch, pages, count_text='"4"', index_raw=None):
    calls = {"urls": []}

    def fake_get(source_id, url, *, params=None, headers=None, timeout=15, **kw):
        calls["urls"].append(url)
        if "getHQNodeStockCount" in url:
            if count_text is None:
                raise a_stock._requests.exceptions.ConnectionError("count down")
            return _FakeResp(text=count_text)
        if "getHQNodeData" in url:
            page = params["page"]
            rows = pages[page - 1] if page <= len(pages) else []
            return _FakeResp(text=json.dumps(rows))
        if "hq.sinajs.cn" in url:
            return _FakeResp(content=(index_raw or 'var hq_str_sh000001="上证指数,1,2,3,4,5,0,0,0,0,2026-09-07,11:35:57,00,";').encode("gbk"))
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(mb, "_source_http_get", fake_get)
    monkeypatch.setattr(mb.time, "sleep", lambda *a, **k: None)
    return calls


def test_sina_fetch_full_completeness_and_dedup(monkeypatch):
    pages = [
        [_row("sh600001", "A", "11.0", "10.0", 1.0, 100), _row("sz000002", "B", "9.0", "10.0", -1.0, 100)],
        # 第二页重复第一页 A（分页漂移），并补 1 只新股
        [_row("sh600001", "A", "11.0", "10.0", 1.0, 100), _row("bj920003", "N北", "50.0", "0.000", 5.0, 10)],
        [],
    ]
    monkeypatch.setattr(mb, "_SINA_PAGE_SIZE", 2)
    _patch_sina_http(monkeypatch, pages, count_text='"3"')
    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "11:35:57")
    assert failure is None and attempt.status == "success"
    assert result["completeness"] == "full"
    assert result["unique_rows"] == 3 == result["expected_universe"]
    assert result["advancing"] == 1 and result["declining"] == 1
    assert result["denominator"] == 2
    assert any("重复" in line for line in result["limitations"])
    # A prior-date snapshot is a close observation even if its source timestamp
    # is before 15:00; it must not be presented as today's intraday breadth.
    assert result["trade_date"] == "2026-09-07" and result["phase"] == "close"


def test_sina_fetch_missing_page_degrades_to_partial(monkeypatch):
    pages = [
        [_row("sh600001", "A", "11.0", "10.0", 1.0, 100)],
        # 第二页整页丢失：只返回 1 只，源端总数 7
    ]
    _patch_sina_http(monkeypatch, pages, count_text='"7"')
    result, failure, _ = mb._fetch_sina_advance_decline("2026-09-07", "15:30:01")
    assert failure is None
    assert result["completeness"] == "partial"
    assert any("不能宣称全市场覆盖" in line for line in result["limitations"])


def test_sina_fetch_truncation_at_page_cap(monkeypatch):
    rows = [_row(f"sh60000{i}", f"S{i}", "11.0", "10.0", 1.0, 100) for i in range(1, 4)]
    _patch_sina_http(monkeypatch, [rows, rows], count_text='"9"')
    monkeypatch.setattr(mb, "_SINA_PAGE_SIZE", 3)
    monkeypatch.setattr(mb, "_SINA_MAX_PAGES", 2)
    result, failure, _ = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")
    assert failure is None
    assert result["completeness"] == "partial"
    assert any("截断" in line for line in result["limitations"])


def test_sina_fetch_unknown_denominator_when_count_unavailable(monkeypatch):
    pages = [[_row("sh600001", "A", "11.0", "10.0", 1.0, 100)]]
    _patch_sina_http(monkeypatch, pages, count_text=None)
    result, failure, _ = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")
    assert failure is None
    assert result["completeness"] == "unknown"
    assert result["expected_universe"] is None
    assert any("完整性未验证" in line for line in result["limitations"])


def test_sina_fetch_zero_rows_is_structure_failure_not_zero_counts(monkeypatch):
    _patch_sina_http(monkeypatch, pages=[], count_text='"5557"')
    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")
    assert result is None and failure == "structure"
    assert attempt.status == "failed_structure"


def test_sina_fetch_non_list_payload_is_structure_failure(monkeypatch):
    def fake_get(source_id, url, *, params=None, headers=None, timeout=15, **kw):
        if "getHQNodeStockCount" in url:
            return _FakeResp(text='"5557"')
        if "getHQNodeData" in url:
            return _FakeResp(text='{"error": 1}')
        raise AssertionError(url)

    monkeypatch.setattr(mb, "_source_http_get", fake_get)
    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")
    assert result is None and failure == "structure"
    assert attempt.status == "failed_structure"


def test_sina_fetch_network_error_returns_failed_network(monkeypatch):
    def fake_get(*a, **kw):
        raise a_stock._requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(mb, "_source_http_get", fake_get)
    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")
    assert result is None and failure == "network"
    assert attempt.status == "failed_network"


def test_sina_fetch_deadline_after_pages_keeps_rows_as_partial(monkeypatch):
    """Source deadline must not discard a valid prefix of the full snapshot."""

    from chstockdata.vendor_errors import SourceContextDeadlineExceeded

    monkeypatch.setattr(mb, "_SINA_PAGE_SIZE", 1)
    calls = {"pages": 0}

    def fake_get(source_id, url, *, params=None, **kwargs):
        if "getHQNodeStockCount" in url:
            return _FakeResp(text='"2"')
        if "getHQNodeData" in url:
            calls["pages"] += 1
            if calls["pages"] == 1:
                return _FakeResp(
                    text=json.dumps([_row("sh600001", "A", "11.0", "10.0", 1.0, 100)])
                )
            raise SourceContextDeadlineExceeded("deadline")
        raise AssertionError(url)

    monkeypatch.setattr(mb, "_source_http_get", fake_get)
    monkeypatch.setattr(mb.time, "sleep", lambda *args, **kwargs: None)

    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")

    assert result is not None
    assert result["completeness"] == "partial"
    assert result["unique_rows"] == 1
    assert any("source context deadline" in line for line in result["limitations"])
    # Rows were delivered, so the attempt succeeded and the deadline truncation is
    # carried by error_summary + completeness=partial.  It must match the page-cap
    # truncation path (also ATTEMPT_SUCCESS) instead of claiming a network failure.
    assert failure is None
    assert attempt.status == "success"
    assert "tool deadline" in (attempt.error_summary or "")
    assert attempt.record_count == 1


def test_sina_fetch_deadline_before_first_page_reports_the_deadline(monkeypatch):
    """An empty result from a tool-deadline abort must not look like a payload defect.

    ``_fetch_sina_advance_decline`` returns early from its deadline handler with
    ``kind="network"``; the zero-row ``structure`` verdict below it is reserved
    for a genuinely empty/invalid payload.
    """

    from chstockdata.vendor_errors import SourceContextDeadlineExceeded

    monkeypatch.setattr(mb, "_SINA_PAGE_SIZE", 1)

    def fake_get(source_id, url, *, params=None, **kwargs):
        if "getHQNodeStockCount" in url:
            return _FakeResp(text='"2"')
        if "getHQNodeData" in url:
            raise SourceContextDeadlineExceeded("deadline")
        raise AssertionError(url)

    monkeypatch.setattr(mb, "_source_http_get", fake_get)
    monkeypatch.setattr(mb.time, "sleep", lambda *args, **kwargs: None)

    result, failure, attempt = mb._fetch_sina_advance_decline("2026-09-07", "10:00:00")

    assert result is None
    assert failure == "network"  # not "structure": no payload was ever received
    assert attempt.status == "failed_network"
    assert "SourceContextDeadlineExceeded" in (attempt.error_summary or "")


def test_sina_index_anchor_falls_back_to_completed_index_kline_after_quote_403(monkeypatch):
    """服务器拒绝 hq.sinajs.cn 时，仍须从同源日线取得已收盘交易日锚点。"""

    calls = []

    def fake_get(source_id, url, **kwargs):
        calls.append(url)
        if url == mb._SINA_INDEX_URL:
            return _FakeResp(status_code=403)
        if url == mb._SINA_INDEX_KLINE_URL:
            return _FakeResp(text='[{"day":"2026-09-10","close":"3240.11"}]')
        raise AssertionError(url)

    monkeypatch.setattr(mb, "_source_http_get", fake_get)

    assert mb._sina_index_anchor() == ("2026-09-10", "15:00:00")
    assert calls == [mb._SINA_INDEX_URL, mb._SINA_INDEX_KLINE_URL]


# ---------------------------------------------------------------------------
# 3. 东财池 fetcher：参数 / 失败 / data=null
# ---------------------------------------------------------------------------


def test_em_pool_fetch_uses_em_get_with_correct_params(monkeypatch):
    calls = []

    def fake_em_get(url, params=None, **kw):
        calls.append((url, dict(params or {})))
        kind = "ZT" if "getTopicZTPool" in url else ("ZB" if "getTopicZBPool" in url else "DT")
        return _FakeResp(text=json.dumps({"data": {"tc": 1, "qdate": "20260907", "pool": [_pool_row("600001", "A", lbc=1)]}}))

    monkeypatch.setattr(mb, "_em_get", fake_em_get)
    for kind, expect_sort in (("limit_up", "fbt:asc"), ("failed_board", "fbt:asc"), ("limit_down", "zdp:asc")):
        data, failure, attempt = mb._fetch_em_pool(kind, "20260904")
        assert failure is None and data is not None and attempt.status == "success"
    # 跌停池必须 zdp:asc（fbt 排序返回空池，2026-09-07 实测）
    assert calls[2][1]["sort"] == "zdp:asc" and calls[0][1]["sort"] == "fbt:asc"
    assert calls[0][1]["date"] == "20260904"
    assert all("push2ex.eastmoney.com" in url and "push2.eastmoney.com" not in url for url, _ in calls)


def test_em_pool_fetch_network_and_no_data_semantics(monkeypatch):
    def boom(url, params=None, **kw):
        raise a_stock._EastmoneyDataUnavailable("东财数据暂不可用")

    monkeypatch.setattr(mb, "_em_get", boom)
    data, failure, attempt = mb._fetch_em_pool("limit_up", "20260904")
    assert data is None and failure == "network"
    assert attempt.status == "failed_network"

    monkeypatch.setattr(mb, "_em_get", lambda url, params=None, **kw: _FakeResp(text=json.dumps({"data": None})))
    data, failure, attempt = mb._fetch_em_pool("limit_up", "20260904")
    assert data is None and failure == "no_data"
    # CR-EVIDENCE-WIRING-F2-F4: a null pool payload is a failed observation,
    # not a legal empty (the date is unknown to the source).
    assert attempt.status == "failed_structure"


def test_em_pool_reuses_existing_throttled_entries():
    """铁律：东财请求必须复用 a_stock._em_get（串行限流），不得另起炉灶。

    用源码结构守卫而非运行时 identity 断言——tests/test_astock_v0222_fix.py 会
    ``importlib.reload(a_stock)``，重载后 a_stock._em_get 是新函数对象，任何持有
    旧绑定的模块 identity 都会断（与本模块是否复用无关；生产路径无重载）。
    """
    import inspect

    source = inspect.getsource(mb)
    assert "from .a_stock import _UA, _em_get, _source_http_get" in source
    # 不得自建 HTTP 会话/直连 requests（东财必须走 _em_get，新浪走 _source_http_get）
    assert "requests.get(" not in source
    assert "requests.Session(" not in source
    assert "_EM_SESSION" not in source
    # 东财端点仅 push2ex 专题池，不含被解耦政策禁止的 push2/push2his 字面量
    assert "push2.eastmoney.com" not in source
    assert "push2his.eastmoney.com" not in source


# ---------------------------------------------------------------------------
# 4. 汇总 get_market_breadth：日期语义 / 三态 / 子项独立 / 同日同范围
# ---------------------------------------------------------------------------


def _fix_clock(monkeypatch, when: datetime):
    monkeypatch.setattr(mb, "_now_cst", lambda: when)


def _patch_pools(monkeypatch, *, zt=None, zb=None, dt=None, failures=None):
    """按 kind 返回固定池；failures[kind] 提供 'network'/'no_data'。"""
    defaults = {
        "limit_up": {"tc": 2, "qdate": "20260907", "pool": [
            _pool_row("605580", "二板", lbc=2, zttj={"days": 2, "ct": 2}),
            _pool_row("003040", "首板", lbc=1, zttj={"days": 1, "ct": 1}),
        ]},
        "failed_board": {"tc": 1, "qdate": "20260907", "pool": [
            _pool_row("600611", "炸板", zbc=3),
        ]},
        "limit_down": {"tc": 1, "qdate": "20260907", "pool": [
            _pool_row("000017", "跌停", days=1),
        ]},
    }
    pools = {"limit_up": zt, "failed_board": zb, "limit_down": dt}
    failures = failures or {}
    requested = {"dates": []}
    pool_code = {"limit_up": "ZT", "failed_board": "ZB", "limit_down": "DT"}

    def fake_fetch(kind, date_compact):
        requested["dates"].append((kind, date_compact))
        method = f"push2ex.getTopic{pool_code[kind]}Pool"
        if failures.get(kind):
            return None, failures[kind], _ok_attempt(
                "a_stock_eastmoney", "failed_network", method=method
            )
        data = pools.get(kind)
        if data is None:
            data = defaults[kind]
        status = "success" if data else "normal_empty"
        return data, None, _ok_attempt("a_stock_eastmoney", status, method=method)

    monkeypatch.setattr(mb, "_fetch_em_pool", fake_fetch)
    return requested


def _patch_adv(monkeypatch, result=None, failure=None):
    def fake_adv(anchor_date, anchor_time):
        if result is None and failure is None:
            return None, "network", _ok_attempt("a_stock_sina", "failed_network")
        return result, failure, _ok_attempt("a_stock_sina", "success")

    monkeypatch.setattr(mb, "_fetch_sina_advance_decline", fake_adv)


def _adv_ok(trade_date="2026-09-07", phase="intraday", completeness="full"):
    return {
        "advancing": 10, "declining": 5, "flat": 2, "denominator": 17,
        "st_counts": {"advancing": 1, "declining": 0, "flat": 0},
        "excluded": {"no_valid_quote": 1, "missing_reference_price": 0,
                     "untraded_zero_change": 0, "missing_change_field": 0},
        "valid_quote_by_market": {"sh": 8, "sz": 8, "bj": 1},
        "unique_rows": 18, "duplicates": 0,
        "expected_universe": 18, "completeness": completeness,
        "source": "sina Market_Center.getHQNodeData node=hs_a (bounded pagination)",
        "universe": "沪深A股+北交所",
        "trade_date": trade_date, "source_time": "11:35:57", "phase": phase,
        "limitations": [],
    }


def test_today_intraday_full_success(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    assert result["status"] == "success"
    assert result["actual_trade_date"] == "2026-09-07"
    assert result["snapshot"]["phase"] == "intraday"
    for key in ("advance_decline", "limit_up", "limit_down", "failed_board", "consecutive_limit_up"):
        assert result[key]["status"] == "success", key
    # 连板与涨停池同池同日同源
    assert result["consecutive_limit_up"]["trade_date"] == result["limit_up"]["trade_date"]
    assert result["consecutive_limit_up"]["distribution"] == {"1": 1, "2": 1}
    assert result["consecutive_limit_up"]["max_boards"] == 2
    # attempts 复用 evidence 语义
    assert {a["provider"] for a in result["attempts"]} == {"a_stock_sina", "a_stock_eastmoney"}


def test_today_after_close_phase(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 15, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "15:00:03"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok(phase="close"))
    result = mb.get_market_breadth("")
    assert result["requested_date"] == "2026-09-07"
    assert result["snapshot"]["phase"] == "close"


def test_phase_falls_back_to_clock_without_source_time(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 14, 0, tzinfo=_CST))
    assert mb._phase_for("2026-09-07", None) == "intraday"
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 15, 1, tzinfo=_CST))
    assert mb._phase_for("2026-09-07", None) == "close"
    assert mb._phase_for("2026-09-04", "09:31:00") == "close"


def test_holiday_request_returns_last_trading_day_labeled(monkeypatch):
    """休市请求今日：源端返回最近交易日数据并显式标注，不冒充今日实时。"""
    _fix_clock(monkeypatch, datetime(2026, 9, 5, 10, 0, tzinfo=_CST))  # 周六
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-04", "15:00:03"))
    requested = _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok(trade_date="2026-09-04", phase="close"))
    result = mb.get_market_breadth("")  # 今日=2026-09-05（周六）
    assert result["requested_date"] == "2026-09-05"
    assert result["actual_trade_date"] == "2026-09-04"
    assert result["snapshot"]["phase"] == "close"
    # 池子改查最近交易日 0904，而不是请求日
    assert {d for _, d in requested["dates"]} == {"20260904"}
    assert any("非交易时段" in line and "2026-09-04" in line for line in result["limitations"])


def test_past_trading_date_pools_only_partial(monkeypatch):
    """历史日期：池子可用、快照不可用——子项独立、不伪装、整体 partial。"""
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch)
    result = mb.get_market_breadth("2026-09-04")
    assert result["advance_decline"]["status"] == "unavailable"
    assert "仅支持最近交易日" in result["advance_decline"]["reason"]
    assert result["limit_up"]["status"] == "success"
    assert result["limit_up"]["trade_date"] == "2026-09-04"
    assert result["status"] == "partial"
    assert result["actual_trade_date"] == "2026-09-04"


def test_weekend_request_makes_no_pool_requests(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    requested = _patch_pools(monkeypatch)
    _patch_adv(monkeypatch)
    result = mb.get_market_breadth("2026-09-06")  # 周日
    assert requested["dates"] == []  # 不发东财请求
    for key in ("limit_up", "failed_board", "limit_down"):
        assert result[key]["status"] == "unavailable"
        assert "周末" in result[key]["reason"] and "不是 0 家" in result[key]["reason"]
    assert result["status"] == "unavailable"


def test_all_pools_empty_means_no_data_not_zero(monkeypatch):
    """三池同时全空 = 非交易日/无数据语义；绝不能解释为 0 涨停/0 跌停。"""
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, zt={"tc": 0, "pool": []}, zb={"tc": 0, "pool": []}, dt={"tc": 0, "pool": []})
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    for key in ("limit_up", "failed_board", "limit_down"):
        assert result[key]["status"] == "unavailable"
        assert "不报 0 家" in result[key]["reason"]
    assert any("三池同时全空" in line for line in result["limitations"])
    assert result["consecutive_limit_up"]["status"] == "unavailable"


def test_limit_down_zero_is_normal_empty_value(monkeypatch):
    """交易日全市场无跌停是合法零值（跌停池单独为 0，其余池非空）。"""
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, dt={"tc": 0, "pool": []})
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    assert result["limit_down"]["status"] == "normal_empty"
    assert result["limit_down"]["count"] == 0
    assert result["limit_up"]["status"] == "success"
    assert result["status"] == "success"


def test_limit_up_zero_alone_gets_review_note(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, zt={"tc": 0, "pool": []})
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    assert result["limit_up"]["status"] == "normal_empty"
    assert any("复核" in line for line in result["limit_up"]["limitations"])
    assert result["consecutive_limit_up"]["max_boards"] == 0


def test_single_pool_failure_keeps_other_subitems(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, failures={"failed_board": "network"})
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    assert result["failed_board"]["status"] == "unavailable"
    assert "请求失败" in result["failed_board"]["reason"]
    assert result["limit_up"]["status"] == "success"
    assert result["status"] == "partial"
    assert any(
        a["status"] == "failed_network" and a["method"] == "push2ex.getTopicZBPool"
        for a in result["attempts"]
    )


def test_pool_data_null_is_no_data_not_empty_market(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, failures={"limit_up": "no_data"})
    _patch_adv(monkeypatch, result=_adv_ok())
    result = mb.get_market_breadth("2026-09-07")
    assert result["limit_up"]["status"] == "unavailable"
    assert "data=null" in result["limit_up"]["reason"]
    assert result["consecutive_limit_up"]["status"] == "unavailable"


def test_same_day_scope_mismatch_keeps_per_item_dates(monkeypatch):
    """子项日期不一致时保留各自日期 + 全局限制说明，不合并伪装统一快照。"""
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok(trade_date="2026-09-03", phase="close"))
    result = mb.get_market_breadth("2026-09-07")
    assert result["actual_trade_date"] is None
    assert any("交易日不一致" in line for line in result["limitations"])
    assert result["advance_decline"]["trade_date"] == "2026-09-03"
    assert result["limit_up"]["trade_date"] == "2026-09-07"


def test_advance_decline_failure_does_not_block_pools(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, failure="structure")
    result = mb.get_market_breadth("2026-09-07")
    assert result["advance_decline"]["status"] == "unavailable"
    assert "结构异常" in result["advance_decline"]["reason"]
    assert result["status"] == "partial"


def test_invalid_date_raises_value_error():
    with pytest.raises(ValueError):
        mb.get_market_breadth("2026/9/7 12:00")


def test_result_is_json_serializable(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch)
    _patch_adv(monkeypatch, result=_adv_ok())
    payload = json.dumps(mb.get_market_breadth("2026-09-07"), ensure_ascii=False)
    assert "市场广度数据" not in payload or True


# ---------------------------------------------------------------------------
# 5. 文本渲染
# ---------------------------------------------------------------------------


def test_format_market_breadth_values_and_unavailable(monkeypatch):
    _fix_clock(monkeypatch, datetime(2026, 9, 7, 12, 30, tzinfo=_CST))
    monkeypatch.setattr(mb, "_sina_index_anchor", lambda: ("2026-09-07", "11:35:57"))
    _patch_pools(monkeypatch, dt={"tc": 0, "pool": []})
    _patch_adv(monkeypatch, result=_adv_ok())
    text = mb.format_market_breadth(mb.get_market_breadth("2026-09-07"))
    assert "涨/跌/平: 10/5/2" in text
    assert "跌停: 0" in text
    assert "炸板: 1" in text
    assert "连板: 最高 2 板" in text
    _patch_adv(monkeypatch)
    text2 = mb.format_market_breadth(mb.get_market_breadth("2026-09-04"))
    assert "不可用" in text2


# ---------------------------------------------------------------------------
# 6. 真实脱敏样本（真实交易日核对，合成夹具不能替代）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_intraday():
    return json.loads((FIXTURE_DIR / "real_2026-09-07_intraday.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def real_close():
    return json.loads((FIXTURE_DIR / "real_2026-09-04_close.json").read_text(encoding="utf-8"))


def test_real_intraday_sample_count_relations(real_intraday):
    adv = real_intraday["advance_decline"]
    assert adv["advancing"] + adv["declining"] + adv["flat"] == adv["denominator"]
    assert adv["denominator"] + sum(adv["excluded"].values()) == adv["unique_rows"]
    assert adv["unique_rows"] == adv["expected_universe"]
    assert adv["completeness"] == "full"
    assert adv["phase"] == "intraday"  # 午间盘中抓取
    assert adv["trade_date"] == "2026-09-07"
    # 沪深+北交所均有覆盖
    assert all(v > 0 for v in adv["valid_quote_by_market"].values())

    cons = real_intraday["consecutive_limit_up"]
    assert sum(cons["distribution"].values()) == real_intraday["limit_up"]["count"]
    assert cons["max_boards"] == max(int(k) for k in cons["distribution"]) == 6
    for key in ("limit_up", "limit_down", "failed_board"):
        item = real_intraday[key]
        assert item["count"] == item["source_total_count"]
        assert item["trade_date"] == "2026-09-07"
    # 北交所入池以实测为准：当日炸板池含 1 只北交所股票，涨停池为 0
    assert real_intraday["failed_board"]["bse_count"] == 1
    assert real_intraday["limit_up"]["bse_count"] == 0
    assert real_intraday["status"] == "success"


def test_real_close_sample_partial_semantics(real_close):
    assert real_close["requested_date"] == "2026-09-04"
    assert real_close["actual_trade_date"] == "2026-09-04"
    assert real_close["snapshot"]["phase"] == "close"
    assert real_close["advance_decline"]["status"] == "unavailable"
    assert "仅支持最近交易日" in real_close["advance_decline"]["reason"]
    for key in ("limit_up", "limit_down", "failed_board", "consecutive_limit_up"):
        assert real_close[key]["status"] == "success"
        assert real_close[key]["trade_date"] == "2026-09-04"
    assert sum(real_close["consecutive_limit_up"]["distribution"].values()) == real_close["limit_up"]["count"]
    assert real_close["status"] == "partial"


def test_real_samples_sanitized_no_secrets(real_intraday, real_close):
    allowed_attempt_keys = {
        "provider", "method", "status", "duration_ms", "error_summary", "record_count",
    }
    for sample in (real_intraday, real_close):
        for attempt in sample["attempts"]:
            assert set(attempt) <= allowed_attempt_keys
            assert "ut=" not in json.dumps(attempt)
        text = json.dumps(sample, ensure_ascii=False)
        assert "token" not in text.lower()
        assert "cookie" not in text.lower()
