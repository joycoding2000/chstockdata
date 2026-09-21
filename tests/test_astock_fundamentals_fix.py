"""回归测试：关键财务数据缺失的 3 个 bug 修复。

覆盖：
- bug1: get_fundamentals 从 mootdx 拼音字段正确提取并推算 EPS/ROE
- bug2: _get_financial_report_sina 从 report_list 正确解析三表
- bug3: _ths_eps_forecast 用 io.StringIO 兼容 pandas 3.0 read_html
"""
import pandas as pd


def _fake_mootdx_finance_row():
    return pd.DataFrame([{
        "zongguben": 1_250_000_000.0,
        "liutongguben": 1_250_000_000.0,
        "zhuyingshouru": 539_000_000_000.0,
        "jinglirun": 272_000_000_000.0,
        "yingyelirun": 375_000_000_000.0,
        "meigujingzichan": 216.0,
        "jingyingxianjinliu": 269_000_000_000.0,
        "zongzichan": 3_199_000_000_000.0,
        "jingzichan": 2_700_000_000_000.0,
        "updated_date": 20260425.0,
        "ipo_date": 20010827.0,
    }])


def _fake_sina_income_frame():
    """F10 快照期参考用的离线新浪利润表（最新报告期 2026-03-31）。"""
    return pd.DataFrame([{
        "报告日": pd.Timestamp("2026-03-31"),
        "公告日": pd.Timestamp("2026-04-25"),
        "营业收入": "53909252220.51",
    }])


class _FakeMootdxClient:
    def finance(self, symbol):
        return _fake_mootdx_finance_row()


class _FakeResp:
    """模拟 requests.Response：json() 与 text。"""

    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.encoding = "gbk"

    def json(self):
        return self._payload


def test_get_fundamentals_derives_eps_roe_from_pinyin_fields(monkeypatch):
    """bug1: mootdx 字段为拼音缩写，应提取净利润/营收并推算 EPS/ROE。"""
    from chstockdata import a_stock

    monkeypatch.setattr(a_stock, "_get_mootdx_client", lambda *args, **kwargs: _FakeMootdxClient())
    monkeypatch.setattr(a_stock, "_tencent_quote", lambda codes, **_kwargs: {})
    monkeypatch.setattr(a_stock, "_ths_eps_forecast", lambda code: pd.DataFrame())
    monkeypatch.setattr(a_stock, "_today", lambda: pd.Timestamp("2026-07-14").date())
    monkeypatch.setattr(
        a_stock, "_get_financial_report_sina", lambda *a, **k: _fake_sina_income_frame()
    )

    out = a_stock.get_fundamentals("600519", "2026-07-14")

    # C3 修复：TDX 协议金额字段以 0.1 元计，渲染前 ÷10（600519/000858 实测
    # 与新浪三表一致）；股本/每股字段单位正确，不缩放。
    assert "Net Profit (净利润): 27200000000.0" in out
    assert "Revenue (主营收入): 53900000000.0" in out
    assert "Total Assets (总资产): 319900000000.0" in out
    assert "EPS (derived): 21.7600" in out        # (272e9 / 10) / 1.25e9
    assert "ROE (%) (derived): 10.07" in out      # 272e9 / 2.7e12 * 100（比例不随缩放变化）
    assert "Book Value Per Share (每股净资产): 216.0" in out
    assert "Total Shares (总股本): 1250000000.0" in out
    # T2: 快照绝对值读数必须带期（参考新浪三表最新报告期）并披露 updated_date
    assert "F10 Snapshot Report Period (快照期参考): 2026-03-31" in out
    assert "F10 Snapshot Update Date (TDX updated_date): 2026-04-25" in out


def test_get_financial_report_sina_parses_report_list(monkeypatch):
    """bug2: 新浪数据在 result.data.report_list[日期]['data']，应解析为 DataFrame。"""
    from chstockdata import a_stock

    fake_json = {
        "result": {
            "data": {
                "report_list": {
                    "20260331": {"data": [
                        {"item_title": "营业收入", "item_value": "53909252220.51"},
                        {"item_title": "营业成本", "item_value": "10000000000.00"},
                    ]},
                    "20251231": {"data": [
                        {"item_title": "营业收入", "item_value": "50000000000.00"},
                    ]},
                }
            }
        }
    }
    monkeypatch.setattr(a_stock._requests, "get", lambda *a, **k: _FakeResp(fake_json))

    df = a_stock._get_financial_report_sina("600519", "利润表", "quarterly", None)

    assert not df.empty
    assert "报告日" in df.columns
    assert "营业收入" in df.columns
    assert len(df) == 2
    # 降序：最新报告期在前
    assert df.iloc[0]["报告日"] == pd.Timestamp("2026-03-31")
    assert df.iloc[0]["营业收入"] == "53909252220.51"


def test_get_financial_report_sina_annual_filter(monkeypatch):
    """bug2: annual 频率应只保留 12 月末年报。"""
    from chstockdata import a_stock

    fake_json = {
        "result": {
            "data": {
                "report_list": {
                    "20260331": {"data": [{"item_title": "营业收入", "item_value": "1"}]},
                    "20251231": {"data": [{"item_title": "营业收入", "item_value": "2"}]},
                    "20250930": {"data": [{"item_title": "营业收入", "item_value": "3"}]},
                }
            }
        }
    }
    monkeypatch.setattr(a_stock._requests, "get", lambda *a, **k: _FakeResp(fake_json))

    df = a_stock._get_financial_report_sina("600519", "利润表", "annual", None)
    assert len(df) == 1
    assert df.iloc[0]["报告日"] == pd.Timestamp("2025-12-31")


def test_get_financial_report_sina_empty_report_list(monkeypatch):
    """bug2: report_list 为空时应返回空 DataFrame（不抛异常）。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock._requests, "get", lambda *a, **k: _FakeResp({"result": {"data": {}}})
    )
    df = a_stock._get_financial_report_sina("600519", "利润表", "quarterly", None)
    assert df.empty


def test_get_financial_report_sina_normalizes_item_yoy_to_percent(monkeypatch):
    """新浪 item_tongbi 是小数比例（0.125 = +12.5%），解析层统一换算为百分数。"""
    from chstockdata import a_stock

    fake_json = {
        "result": {"data": {"report_list": {
            "20251231": {
                "publish_date": "20260420",
                "data": [{
                    "item_title": "营业收入",
                    "item_value": "100",
                    "item_tongbi": "0.125",
                }],
            },
        }}},
    }
    monkeypatch.setattr(a_stock._requests, "get", lambda *a, **k: _FakeResp(fake_json))

    df = a_stock._get_financial_report_sina("600519", "利润表", "quarterly", None)

    assert df.iloc[0]["公告日"] == pd.Timestamp("2026-04-20")
    assert df.iloc[0]["营业收入同比"] == "12.5"


def test_ths_eps_forecast_stringio_compat(monkeypatch):
    """bug3: pandas 3.0 read_html 不再接受裸 HTML 字符串，应用 io.StringIO 包装。"""
    from chstockdata import a_stock

    html = (
        "<html><body><table>"
        "<tr><th>年度</th><th>机构数</th><th>最小</th><th>均值</th><th>最大</th></tr>"
        "<tr><td>2026</td><td>46</td><td>66.27</td><td>68.83</td><td>77.85</td></tr>"
        "</table></body></html>"
    )
    monkeypatch.setattr(a_stock._requests, "get", lambda *a, **k: _FakeResp(text=html))

    df = a_stock._ths_eps_forecast("600519")
    assert not df.empty
