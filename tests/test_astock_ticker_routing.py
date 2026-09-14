"""Ticker 路由加固回归（上游 a-stock-data v3.7.1 错票修复移植 + 5x ETF 路由）。

背景：`_normalize_ticker` 此前先剥后缀再剥前缀，`SH000001.SZ` 这类自相矛盾
写法被静默接受；`000016.SH` 被归一化为 `000016` 后按号段路由到深市
（实为深康佳A，上证50 为 `000016.SH`）；`tdx_bridge.market_for_code` 缺
`5x→SH`，沪市 ETF 的腾讯/新浪行情路径会拼出 `sz510050` 静默取不到数。
"""

from __future__ import annotations

import pytest

from chstockdata import a_stock
from chstockdata.tdx_bridge import market_for_code


def test_normalize_accepts_supported_forms():
    for raw, expected in (
        ("688017", "688017"),
        ("SH688017", "688017"),
        ("sh688017", "688017"),
        ("688017.SH", "688017"),
        ("688017.sh", "688017"),
        ("SZ000001", "000001"),
        ("000001.SZ", "000001"),
        ("BJ920982", "920982"),
        ("920982.BJ", "920982"),
        ("600519", "600519"),
        ("600016.SH", "600016"),
    ):
        assert a_stock._normalize_ticker(raw) == expected, raw


def test_normalize_rejects_prefix_and_suffix_together():
    """前缀与后缀二选一；同时出现是自相矛盾写法，必须报错而不是吞掉其一。"""
    with pytest.raises(ValueError, match="不是 A 股代码"):
        a_stock._normalize_ticker("SH000001.SZ")
    with pytest.raises(ValueError, match="不是 A 股代码"):
        a_stock._normalize_ticker("600519.SH.SZ")


def test_normalize_rejects_market_section_conflicts():
    """显式市场标识与号段矛盾时不得静默丢标识（否则会查到另一只票）。"""
    for raw in ("600519.SZ", "SZ600519", "688017.BJ", "BJ600519"):
        with pytest.raises(ValueError, match="矛盾"):
            a_stock._normalize_ticker(raw)


def test_normalize_rejects_shanghai_index_notation():
    """沪市无 000xxx 个股：sh+000xxx 必然指向沪市指数，本包只服务个股。"""
    for raw in ("sh000001", "000001.SH", "sh000016", "000016.SH", "SH000300"):
        with pytest.raises(ValueError, match="沪市指数"):
            a_stock._normalize_ticker(raw)


def test_normalize_keeps_shenzhen_000xxx_stocks():
    """同号段的深市个股不受影响：sz 显式标识与裸码继续按深市处理。"""
    assert a_stock._normalize_ticker("sz000001") == "000001"
    assert a_stock._normalize_ticker("000001.SZ") == "000001"
    assert a_stock._normalize_ticker("000016.SZ") == "000016"
    assert a_stock._normalize_ticker("000016") == "000016"


def test_normalize_preserves_hk_us_errors():
    """港股/美股的既有报错分类不因正则改造而改变。"""
    with pytest.raises(ValueError, match="港股"):
        a_stock._normalize_ticker("00700")
    with pytest.raises(ValueError, match="港股"):
        a_stock._normalize_ticker("0700.HK")
    with pytest.raises(ValueError, match="不是 A 股代码"):
        a_stock._normalize_ticker("AAPL")


def test_resolve_ticker_rejects_index_forms_without_name_map_lookup():
    with pytest.raises(ValueError, match="沪市指数"):
        a_stock.resolve_ticker("000016.SH")
    with pytest.raises(ValueError, match="沪市指数"):
        a_stock.resolve_ticker("SH000001")
    assert a_stock.resolve_ticker("000016") == "000016"


def test_market_for_code_routes_sh_etf_and_keeps_existing_rules():
    assert market_for_code("510050") == "SH"
    assert market_for_code("510300") == "SH"
    assert market_for_code("588000") == "SH"
    assert market_for_code("510500") == "SH"
    assert market_for_code("920982") == "BJ"
    assert market_for_code("430047") == "BJ"
    assert market_for_code("830799") == "BJ"
    assert market_for_code("600519") == "SH"
    assert market_for_code("900901") == "SH"
    assert market_for_code("000001") == "SZ"
    assert market_for_code("300750") == "SZ"
    assert market_for_code("159915") == "SZ"


def test_get_prefix_follows_market_for_code():
    assert a_stock._get_prefix("510050") == "sh"
    assert a_stock._get_prefix("600519") == "sh"
    assert a_stock._get_prefix("920982") == "bj"
    assert a_stock._get_prefix("000001") == "sz"
