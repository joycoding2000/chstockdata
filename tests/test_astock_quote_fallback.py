"""实时行情替代源回归测试。

实时行情的降级链必须独立于东财 push2：腾讯 → mootdx/通达信 → 新浪。
这些测试只验证可替换的价格/成交字段；PE、PB、市值等非所有源都提供的字段
不得由 fallback 伪造。
"""

import pandas as pd
import pytest


def _quote(code="600519", *, price=1500.0, source="mootdx", **overrides):
    value = {
        "name": "贵州茅台",
        "price": price,
        "last_close": 1490.0,
        "open": 1495.0,
        "high": 1510.0,
        "low": 1488.0,
        "amount_wan": 12345.0,
        "change_pct": 0.67,
        "pe_ttm": None,
        "pe_static": None,
        "pb": None,
        "mcap_yi": None,
        "float_mcap_yi": None,
        "turnover_pct": None,
        "limit_up": None,
        "limit_down": None,
        "is_stale": False,
        "source": source,
    }
    value.update(overrides)
    return {code: value}


def test_realtime_quote_stops_at_tencent(monkeypatch):
    from chstockdata import a_stock

    expected = _quote(source="tencent", pe_ttm=25.0, pb=8.0, mcap_yi=18000.0)
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes, **_kwargs: expected)
    monkeypatch.setattr(
        a_stock,
        "_mootdx_realtime_quote",
        lambda codes, **_kwargs: pytest.fail("腾讯成功时不应调用 mootdx"),
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_realtime_quote",
        lambda codes, **_kwargs: pytest.fail("腾讯成功时不应调用新浪"),
    )

    result = a_stock._get_realtime_quotes(["600519"])

    assert result["600519"]["source"] == "tencent"
    assert result["600519"]["pe_ttm"] == 25.0


def test_realtime_quote_falls_back_to_mootdx_after_tencent_proxy_error(monkeypatch):
    from chstockdata import a_stock

    def _raise(_codes, **_kwargs):
        raise RuntimeError("proxy token must not be exposed")

    monkeypatch.setattr(a_stock, "_tencent_quote", _raise)
    monkeypatch.setattr(
        a_stock, "_mootdx_realtime_quote", lambda codes, **_kwargs: _quote(source="mootdx")
    )
    monkeypatch.setattr(
        a_stock,
        "_sina_realtime_quote",
        lambda codes, **_kwargs: pytest.fail("mootdx 成功时不应调用新浪"),
    )

    result = a_stock._get_realtime_quotes(["600519"])

    assert result["600519"]["source"] == "mootdx"
    assert result["600519"]["price"] == 1500.0
    assert result["600519"]["pe_ttm"] is None


def test_realtime_quote_falls_back_to_sina_after_tencent_and_mootdx_fail(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_tencent_quote",
        lambda codes, **_kwargs: (_ for _ in ()).throw(ConnectionError("tencent down")),
    )
    monkeypatch.setattr(
        a_stock,
        "_mootdx_realtime_quote",
        lambda codes, **_kwargs: (_ for _ in ()).throw(TimeoutError("tdx down")),
    )
    monkeypatch.setattr(
        a_stock, "_sina_realtime_quote", lambda codes, **_kwargs: _quote(source="sina")
    )

    result = a_stock._get_realtime_quotes(["600519"])

    assert result["600519"]["source"] == "sina"
    assert result["600519"]["price"] == 1500.0
    assert result["600519"]["mcap_yi"] is None


def test_realtime_quote_rejects_stale_tencent_quote_and_uses_next_source(monkeypatch):
    from chstockdata import a_stock

    stale = _quote(source="tencent", price=112.60, is_stale=True)
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes, **_kwargs: stale)
    monkeypatch.setattr(
        a_stock, "_mootdx_realtime_quote", lambda codes, **_kwargs: _quote(source="mootdx")
    )

    result = a_stock._get_realtime_quotes(["600519"])

    assert result["600519"]["source"] == "mootdx"


def test_realtime_quote_keeps_stale_last_resort_when_all_sources_are_stale(monkeypatch):
    """非交易时段三源都只有昨收时，不把合法快照误报成网络失败。"""
    from chstockdata import a_stock

    stale_tencent = _quote(source="tencent", price=1500.0, is_stale=True)
    stale_mootdx = _quote(source="mootdx", price=1500.0, is_stale=True)
    stale_sina = _quote(source="sina", price=1500.0, is_stale=True)
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes, **_kwargs: stale_tencent)
    monkeypatch.setattr(a_stock, "_mootdx_realtime_quote", lambda codes, **_kwargs: stale_mootdx)
    monkeypatch.setattr(a_stock, "_sina_realtime_quote", lambda codes, **_kwargs: stale_sina)

    result = a_stock._get_realtime_quotes(["600519"])

    assert result["600519"]["source"] == "tencent"
    assert result["600519"]["is_stale"] is True
    assert result["600519"]["quote_status"] == "stale_last_resort"


def test_realtime_quote_all_sources_fail_is_explicit_and_sanitized(monkeypatch):
    from chstockdata import a_stock

    def _fail(_codes, **_kwargs):
        raise RuntimeError("https://private.example/token=secret")

    monkeypatch.setattr(a_stock, "_tencent_quote", _fail)
    monkeypatch.setattr(a_stock, "_mootdx_realtime_quote", _fail)
    monkeypatch.setattr(a_stock, "_sina_realtime_quote", _fail)

    with pytest.raises(a_stock._RealtimeQuoteUnavailable) as exc_info:
        a_stock._get_realtime_quotes(["600519"])

    message = str(exc_info.value)
    assert "实时行情不可用" in message
    assert "private.example" not in message
    assert "secret" not in message


def test_sina_realtime_quote_parses_gbk_snapshot(monkeypatch):
    from chstockdata import a_stock

    class _Response:
        text = (
            'var hq_str_sh600519="贵州茅台,1495.00,1490.00,1500.00,'
            '1510.00,1488.00,1499.00,1500.00,123456,67890000,'
            '1499.00,100,1498.00,200,1497.00,300,1496.00,400,'
            '1495.00,500,1500.00,100,1501.00,200,1502.00,300,'
            '1503.00,400,1504.00,500,2026-08-17,15:00:00,00,";'
        )
        encoding = None

        def raise_for_status(self):
            return None

    monkeypatch.setattr(a_stock._requests, "get", lambda *args, **kwargs: _Response())

    result = a_stock._sina_realtime_quote(["600519"])

    assert result["600519"]["source"] == "sina"
    assert result["600519"]["price"] == 1500.0
    assert result["600519"]["last_close"] == 1490.0
    assert result["600519"]["amount_wan"] == 6789.0


def test_mootdx_realtime_quote_normalizes_dataframe_fields(monkeypatch):
    from chstockdata import a_stock

    class _Client:
        def quotes(self, symbol):
            return pd.DataFrame(
                [{
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1500.0,
                    "last_close": 1490.0,
                    "open": 1495.0,
                    "high": 1510.0,
                    "low": 1488.0,
                    "vol": 123456,
                    "amount": 67890000.0,
                }]
            )

    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda *args, **kwargs: _Client())

    result = a_stock._mootdx_realtime_quote(["600519"])

    assert result["600519"]["source"] == "mootdx"
    assert result["600519"]["price"] == 1500.0
    assert result["600519"]["amount_wan"] == 6789.0
    assert result["600519"]["pe_ttm"] is None


def test_fundamentals_consumes_fallback_quote_and_reports_actual_source(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_realtime_quotes",
        lambda codes: _quote(source="mootdx"),
    )
    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda *args, **kwargs: type(
        "_Client", (), {"finance": lambda self, symbol: pd.DataFrame([{
            "zongguben": 1_000_000_000,
            "jinglirun": 10_000_000,
            "jingzichan": 100_000_000,
        }])}
    )())
    monkeypatch.setattr(a_stock, "_em_get", lambda *args, **kwargs: type(
        "_Response", (), {"json": lambda self: {"data": {}}}
    )())
    monkeypatch.setattr(a_stock, "_ths_eps_forecast", lambda code: pd.DataFrame())
    monkeypatch.setattr(
        a_stock,
        "_get_financial_report_sina",
        lambda *args, **kwargs: pd.DataFrame([{
            "报告日": pd.Timestamp("2026-03-31"),
            "公告日": pd.Timestamp("2026-04-25"),
            "营业收入": "53909252220.51",
        }]),
    )

    result = a_stock.get_fundamentals("600519", "2026-08-17", historical_review=False)

    assert "Quote source: mootdx" in result
    assert "Price: 1500.0" in result
    assert "PE (TTM): None" not in result
    assert "Market Cap (100M CNY): None" not in result


def test_get_realtime_snapshot_exposes_display_safe_fields(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_realtime_quotes",
        lambda codes: {
            "002594": {
                "name": "比亚迪",
                "price": 300.0,
                "change_pct": 1.25,
                "high": 303.0,
                "low": 296.0,
                "amount_wan": 123456.0,
                "turnover_pct": 2.5,
                "pe_ttm": 25.0,
                "pb": 4.2,
                "mcap_yi": 8765.0,
                "float_mcap_yi": 7000.0,
                "source": "tencent",
                "is_stale": False,
            }
        },
    )

    result = a_stock.get_realtime_snapshot("002594")

    assert result["status"] == "ready"
    assert result["ticker"] == "002594"
    assert result["name"] == "比亚迪"
    assert result["price"] == 300.0
    assert result["change_pct"] == 1.25
    assert result["source"] == "tencent"
    assert result["data_group"] == "实时行情"
    assert result["observed_at"]


def test_get_realtime_snapshot_preserves_sanitized_unavailable_error(monkeypatch):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_realtime_quotes",
        lambda codes: (_ for _ in ()).throw(
            a_stock._RealtimeQuoteUnavailable({"002594": ["ConnectionError"]})
        ),
    )

    with pytest.raises(a_stock._RealtimeQuoteUnavailable) as exc_info:
        a_stock.get_realtime_snapshot("002594")

    assert "实时行情不可用" in str(exc_info.value)
    assert "ConnectionError" not in str(exc_info.value)
