"""Regression tests for provider failures surfaced by free fundamentals."""

import pandas as pd


class _EmptyMootdxClient:
    def finance(self, symbol):
        return None


class _EmptyEastmoneyResponse:
    def json(self):
        return {"data": {}}


def test_get_fundamentals_marks_tencent_failure_without_leaking_request_details(
    monkeypatch,
):
    from chstockdata import a_stock

    def _raise_tencent_failure(_codes):
        raise RuntimeError("https://private.example/quote?token=secret-token")

    monkeypatch.setattr(a_stock, "_get_realtime_quotes", _raise_tencent_failure)
    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda: _EmptyMootdxClient())
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *args, **kwargs: _EmptyEastmoneyResponse()
    )
    monkeypatch.setattr(a_stock, "_ths_eps_forecast", lambda _code: None)

    result = a_stock.get_fundamentals(
        "600519", "2026-08-04", historical_review=False
    )

    assert "实时行情降级链源失败：RuntimeError" in result
    assert "RuntimeError" in result
    assert "private.example" not in result
    assert "secret-token" not in result


def test_get_fundamentals_marks_tencent_failure_during_forward_pe_calculation(
    monkeypatch,
):
    from chstockdata import a_stock

    quote = {
        "600519": {
            "name": "贵州茅台",
            "price": 1500.0,
            "pe_ttm": 20.0,
            "pe_static": 20.0,
            "pb": 8.0,
            "mcap_yi": 18000.0,
            "float_mcap_yi": 18000.0,
            "turnover_pct": 0.5,
            "change_pct": 0.1,
            "limit_up": 1650.0,
            "limit_down": 1350.0,
        }
    }
    calls = 0

    def _get_realtime_quotes(_codes):
        nonlocal calls
        calls += 1
        if calls == 1:
            return quote
        raise RuntimeError("https://private.example/quote?token=secret-token")

    monkeypatch.setattr(a_stock, "_get_realtime_quotes", _get_realtime_quotes)
    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda: _EmptyMootdxClient())
    monkeypatch.setattr(
        a_stock, "_em_get", lambda *args, **kwargs: _EmptyEastmoneyResponse()
    )
    monkeypatch.setattr(
        a_stock,
        "_ths_eps_forecast",
        lambda _code: pd.DataFrame([["2026", 5, 70.0, 75.0, 80.0]]),
    )

    result = a_stock.get_fundamentals(
        "600519", "2026-08-04", historical_review=False
    )

    assert "实时行情（前瞻估值降级链）源失败：RuntimeError" in result
    assert "private.example" not in result
    assert "secret-token" not in result


def test_dragon_tiger_board_marks_seat_provider_failure(monkeypatch):
    from chstockdata import a_stock

    calls = 0

    def _datacenter(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{
                "TRADE_DATE": "2026-08-04",
                "BILLBOARD_NET_AMT": 0,
                "TURNOVERRATE": 0,
                "EXPLANATION": "test",
            }]
        raise RuntimeError("https://private.example/seats?token=secret-token")

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _datacenter)

    result = a_stock.get_dragon_tiger_board("600519", "2026-08-04")

    assert "龙虎榜买卖席位数据" in result
    assert "数据缺失" in result
    assert "龙虎榜机构动向数据" not in result
    assert "private.example" not in result
    assert "secret-token" not in result


def test_dragon_tiger_board_does_not_report_institution_failure_when_no_board_data(
    monkeypatch,
):
    from chstockdata import a_stock

    calls = 0

    def _datacenter(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _datacenter)

    result = a_stock.get_dragon_tiger_board("600519", "2026-08-04")

    assert calls == 1
    assert "近30日未上龙虎榜" in result
    assert "龙虎榜买卖席位数据" not in result
    assert "龙虎榜机构动向数据" not in result


def test_get_news_marks_all_provider_failures_without_leaking_details(monkeypatch):
    from chstockdata import a_stock

    def _raise_news_failure(*_args, **_kwargs):
        raise RuntimeError("https://private.example/news?token=secret-token")

    monkeypatch.setattr(a_stock, "_fetch_news_eastmoney", _raise_news_failure)
    monkeypatch.setattr(a_stock, "_fetch_news_sina", _raise_news_failure)

    result = a_stock.get_news("600519", "2026-08-01", "2026-08-04")

    assert "东方财富新闻源失败：RuntimeError" in result
    assert "新浪财经新闻源失败：RuntimeError" in result
    assert "private.example" not in result
    assert "secret-token" not in result
