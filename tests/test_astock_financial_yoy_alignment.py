"""财务报告期口径对齐回归测试（T1/T2/T3，离线 fixture）。

对应交接文档 docs/pending-financial-period-alignment.md：
- T1: 自算同期累计同比（基期=上一报告年度同一期末），不再采信 item_tongbi
  透传；仅在上年同期行缺失时回退（解析层已把比例换算为百分数）。
- T2: TDX F10 快照绝对值读数带报告期参考 + updated_date 披露。
- T3: 同比输出携带基期语义（如「2026H1累计，较2025H1」）。
"""

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# 300452 山河药辅 2026H1 真实数据（来源：新浪三表 / 东财业绩报表，
# 见 docs/pending-financial-period-alignment.md 附录）
# ---------------------------------------------------------------------------

_SAMPLE_INCOME_2026H1 = {
    "报告日": pd.Timestamp("2026-06-30"),
    "公告日": pd.Timestamp("2026-08-22"),
    "营业收入": "521648673.91",
    "营业成本": "300000000.00",
    "净利润": "97095867.82",
    "归属于母公司所有者的净利润": "96189158.31",
    # 旧的透传列（小数比例）故意留错值：自算命中时不得被采信
    "营业收入同比": "0.11",
    "净利润同比": "0.04",
}

_SAMPLE_INCOME_2025H1 = {
    "报告日": pd.Timestamp("2025-06-30"),
    "公告日": pd.Timestamp("2025-08-23"),
    "营业收入": "470839549.60",
    "营业成本": "270000000.00",
    "净利润": "93234763.55",
    "归属于母公司所有者的净利润": "93035152.04",
}


def _statements(income_rows, balance_rows=None, cashflow_rows=None):
    balance_rows = balance_rows or [
        {
            "报告日": pd.Timestamp("2026-06-30"),
            "公告日": pd.Timestamp("2026-08-22"),
            "资产总计": "1200000000",
            "负债合计": "400000000",
            "归属于母公司股东权益合计": "700000000",
        },
        {
            "报告日": pd.Timestamp("2025-06-30"),
            "公告日": pd.Timestamp("2025-08-23"),
            "归属于母公司股东权益合计": "600000000",
        },
    ]
    cashflow_rows = cashflow_rows or [
        {
            "报告日": pd.Timestamp("2026-06-30"),
            "公告日": pd.Timestamp("2026-08-22"),
            "经营活动产生的现金流量净额": "80000000",
        }
    ]
    return {
        "利润表": pd.DataFrame(income_rows),
        "资产负债表": pd.DataFrame(balance_rows),
        "现金流量表": pd.DataFrame(cashflow_rows),
    }


@pytest.fixture
def stub_reports(monkeypatch):
    from chstockdata import a_stock

    def _install(income_rows, balance_rows=None, cashflow_rows=None):
        reports = _statements(income_rows, balance_rows, cashflow_rows)
        monkeypatch.setattr(
            a_stock,
            "_get_financial_report_sina",
            lambda _code, report_type, *_args, **_kwargs: reports[report_type],
        )

    return _install


def test_yoy_is_self_computed_same_period_cumulative(stub_reports):
    """300452 2026H1：营收 +10.79%、归母净利 +3.39%（对齐官方口径）。"""
    from chstockdata import a_stock

    stub_reports([_SAMPLE_INCOME_2026H1, _SAMPLE_INCOME_2025H1])

    text = a_stock.get_free_financial_indicators("300452", "2026-09-05")

    assert "- 营收同比增长率: 10.79%（2026H1累计，较2025H1）" in text
    assert "- 净利润同比增长率: 3.39%（2026H1累计，较2025H1）" in text
    # 旧透传列（0.11 / 0.04）不得被采信
    assert "0.11%" not in text
    assert "0.04%" not in text


def test_yoy_negative_base_uses_absolute_value(stub_reports):
    """基期为负时方向不翻转（(本期-基期)/|基期|，与 Tushare 口径一致）。"""
    from chstockdata import a_stock

    stub_reports([
        {
            "报告日": pd.Timestamp("2026-06-30"),
            "公告日": pd.Timestamp("2026-08-22"),
            "营业收入": "1000",
            "净利润": "600",
        },
        {
            "报告日": pd.Timestamp("2025-06-30"),
            "公告日": pd.Timestamp("2025-08-23"),
            "营业收入": "900",
            "净利润": "-100",
        },
    ])

    text = a_stock.get_free_financial_indicators("000001", "2026-09-05")

    assert "- 净利润同比增长率: 700.00%（2026H1累计，较2025H1）" in text


def test_yoy_falls_back_to_normalized_tongbi_without_prior_year(stub_reports):
    """上年同期行缺失时回退解析层归一化后的同比列（百分数语义）。"""
    from chstockdata import a_stock

    period = pd.Timestamp("2025-12-31")
    announcement = pd.Timestamp("2026-04-20")
    stub_reports(
        [
            {
                "报告日": period,
                "公告日": announcement,
                "营业收入": "1000",
                "营业收入同比": "10",
                "净利润": "120",
                "净利润同比": "20",
            },
        ],
        balance_rows=[{
            "报告日": period,
            "公告日": announcement,
            "资产总计": "1000",
            "负债合计": "400",
            "归属于母公司股东权益合计": "600",
        }],
        cashflow_rows=[{
            "报告日": period,
            "公告日": announcement,
            "经营活动产生的现金流量净额": "120",
        }],
    )

    text = a_stock.get_free_financial_indicators("600519", "2026-05-01")

    assert "- 营收同比增长率: 10.00%（2025年报，较2024年报）" in text
    assert "- 净利润同比增长率: 20.00%（2025年报，较2024年报）" in text


def test_yoy_unavailable_is_disclosed_with_basis(stub_reports):
    """既无上年同期行也无透传列时显式披露不可用 + 基期。"""
    from chstockdata import a_stock

    period = pd.Timestamp("2025-12-31")
    announcement = pd.Timestamp("2026-04-20")
    stub_reports(
        [{
            "报告日": period,
            "公告日": announcement,
            "营业收入": "1000",
            "净利润": "120",
        }],
        balance_rows=[{
            "报告日": period,
            "公告日": announcement,
            "资产总计": "1000",
            "负债合计": "400",
            "归属于母公司股东权益合计": "600",
        }],
        cashflow_rows=[{
            "报告日": period,
            "公告日": announcement,
            "经营活动产生的现金流量净额": "120",
        }],
    )

    text = a_stock.get_free_financial_indicators("600519", "2026-05-01")

    assert "- 营收同比增长率: 不可用（2025年报，较2024年报）" in text
    assert "- 净利润同比增长率: 不可用（2025年报，较2024年报）" in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.10791", "10.791"),
        ("-0.00248", "-0.248"),
        ("2.9272", "292.72"),
        ("0", "0"),
        (None, None),
        ("abc", None),
        ("nan", None),
    ],
)
def test_sina_tongbi_to_percent_conversion(raw, expected):
    """新浪原始比例如实换算为百分数；不可解析值不出列。"""
    from chstockdata import a_stock

    assert a_stock._sina_tongbi_to_percent(raw) == expected


# ---------------------------------------------------------------------------
# T2: TDX F10 快照报告期标注
# ---------------------------------------------------------------------------


def _stub_fundamentals(monkeypatch, advice_frame):
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock,
        "_get_mootdx_client",
        lambda *args, **kwargs: type(
            "_Client",
            (),
            {"finance": lambda self, symbol: advice_frame},
        )(),
    )
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes, **_kwargs: {})
    monkeypatch.setattr(a_stock, "_ths_eps_forecast", lambda code: pd.DataFrame())
    monkeypatch.setattr(a_stock, "_today", lambda: pd.Timestamp("2026-09-15").date())


def _f10_row(updated_date=None):
    row = {
        "zongguben": 1_250_000_000.0,
        "zhuyingshouru": 907_032_640_000.0,
        "jinglirun": 445_168_800_000.0,
        "jingzichan": 2_700_000_000_000.0,
    }
    if updated_date is not None:
        row["updated_date"] = updated_date
    return pd.DataFrame([row])


def _sina_income(period="2026-06-30", announcement="2026-08-15"):
    return pd.DataFrame([{
        "报告日": pd.Timestamp(period),
        "公告日": pd.Timestamp(announcement),
        "营业收入": "90703260964.48",
    }])


def test_f10_snapshot_reference_period_matches_updated_date(monkeypatch):
    """updated_date 与新浪公告日一致时给出高置信参考期标注。"""
    from chstockdata import a_stock

    _stub_fundamentals(monkeypatch, _f10_row(updated_date=20260815.0))
    monkeypatch.setattr(
        a_stock, "_get_financial_report_sina", lambda *a, **k: _sina_income()
    )

    out = a_stock.get_fundamentals("600519", "2026-09-15")

    assert "F10 Snapshot Report Period (快照期参考): 2026-06-30" in out
    assert "公告日 2026-08-15（与 TDX updated_date 一致）" in out
    assert "F10 Snapshot Update Date (TDX updated_date): 2026-08-15" in out


def test_f10_snapshot_reference_period_unaffected_by_updated_date_mismatch(monkeypatch):
    """updated_date 与公告日不一致时仍给出参考期，但不声称一致。"""
    from chstockdata import a_stock

    _stub_fundamentals(monkeypatch, _f10_row(updated_date=20260820.0))
    monkeypatch.setattr(
        a_stock, "_get_financial_report_sina", lambda *a, **k: _sina_income()
    )

    out = a_stock.get_fundamentals("600519", "2026-09-15")

    assert "F10 Snapshot Report Period (快照期参考): 2026-06-30" in out
    assert "与 TDX updated_date 一致" not in out


def test_f10_snapshot_without_updated_date_still_labels_period(monkeypatch):
    """mootdx 未返回 updated_date 时，参考期与金额读数仍然带期。"""
    from chstockdata import a_stock

    _stub_fundamentals(monkeypatch, _f10_row(updated_date=None))
    monkeypatch.setattr(
        a_stock, "_get_financial_report_sina", lambda *a, **k: _sina_income()
    )

    out = a_stock.get_fundamentals("600519", "2026-09-15")

    assert "F10 Snapshot Report Period (快照期参考): 2026-06-30" in out
    assert "F10 Snapshot Update Date" not in out


def test_f10_snapshot_discloses_missing_period_when_reference_fails(monkeypatch):
    """新浪参考失败时显式披露「报告期不可用」，绝对值读数不裸奔。"""
    from chstockdata import a_stock

    _stub_fundamentals(monkeypatch, _f10_row(updated_date=20260815.0))

    def _boom(*_args, **_kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(a_stock, "_get_financial_report_sina", _boom)

    out = a_stock.get_fundamentals("600519", "2026-09-15")

    assert "F10 Snapshot Report Period (快照期参考): 不可用" in out
    assert "Revenue (主营收入): 90703264000.0" in out
    assert "F10 Snapshot Update Date (TDX updated_date): 2026-08-15" in out
