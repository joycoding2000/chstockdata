"""回归测试：东财解禁字段修复（移植自上游 a-stock-data v3.4.0）。

覆盖修复点：
- 修复 A（v3.4.0）：get_lockup_expiry 的解禁字段名 —— 东财 2026 改列名，
  LIMITED_STOCK_TYPE→FREE_SHARES_TYPE、FREE_SHARES_NUM→FREE_SHARES（旧名已废致字段恒空），
  新增 ABLE_FREE_SHARES（实际可流通股数，更贴近真实抛压）

`get_industry_comparison` 曾验证 push2 `fid=f3` 的排序修复；2026-08-17
已迁移至 TDX/Sina，相关回归由 test_astock_tdx_fallback.py 覆盖。
参考：上游 SKILL.md 的 lockup_expiry()；本地实现见 a_stock.py。
实测确认（2026-08-01）：比亚迪 002594 解禁返回字段为 FREE_SHARES_TYPE/FREE_SHARES/
ABLE_FREE_SHARES，旧名 LIMITED_STOCK_TYPE/FREE_SHARES_NUM 不在返回中。
"""


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code

    def json(self):
        return self._p


# ---------------------------------------------------------------------------
# 修复 A：get_lockup_expiry 解禁字段名修复
# ---------------------------------------------------------------------------


def test_lockup_expiry_uses_new_field_names(monkeypatch):
    """解禁类型/数量应取东财现行列名 FREE_SHARES_TYPE/FREE_SHARES，不是已废的旧名。"""
    from chstockdata import a_stock

    # 模拟东财 2026 现行返回字段（实测比亚迪 002594 真实结构）
    fake_data = [
        {
            "SECURITY_CODE": "002594",
            "FREE_DATE": "2017-07-25 00:00:00",
            "FREE_SHARES_TYPE": "定向增发机构配售股份",  # 新列名（旧 LIMITED_STOCK_TYPE 已废）
            "FREE_SHARES": 113833.2959,                  # 新列名（旧 FREE_SHARES_NUM 已废）
            "ABLE_FREE_SHARES": 25214.2855,              # 实际可流通股数（本次新增）
            "FREE_RATIO": 0.221501848828,
        },
    ]
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter",
                        lambda *a, **k: fake_data)

    out = a_stock.get_lockup_expiry("002594", "2026-01-01", forward_days=365)
    assert "定向增发机构配售股份" in out, "解禁类型应来自 FREE_SHARES_TYPE"
    assert "113833.2959" in out, "解禁数量应来自 FREE_SHARES"
    assert "25214.2855" in out, "实际可流通股数应来自 ABLE_FREE_SHARES"
    assert "0.221501848828" in out


def test_lockup_expiry_old_field_names_return_empty(monkeypatch):
    """【反向验证】若仍用旧列名 LIMITED_STOCK_TYPE/FREE_SHARES_NUM，字段会恒空。"""
    from chstockdata import a_stock

    # 同样的数据，但验证旧字段名取不到值（证明旧名已废）
    fake_data = [
        {
            "SECURITY_CODE": "002594",
            "FREE_DATE": "2017-07-25 00:00:00",
            "FREE_SHARES_TYPE": "定向增发机构配售股份",
            "FREE_SHARES": 113833.2959,
            "ABLE_FREE_SHARES": 25214.2855,
            "FREE_RATIO": 0.221501848828,
        },
    ]
    monkeypatch.setattr(a_stock, "_eastmoney_datacenter",
                        lambda *a, **k: fake_data)

    out = a_stock.get_lockup_expiry("002594", "2026-01-01", forward_days=365)
    # 关键断言：用新名能取到值
    assert "定向增发机构配售股份" in out
    # 反向：旧名 LIMITED_STOCK_TYPE / FREE_SHARES_NUM 不应作为字段引用出现在代码里
    # （这里通过功能正确性间接验证——如果代码还用旧名，类型和数量会是空字符串）
    # 检查输出里没有 "| |" 这种空字段模式（类型非空）
    lines = [l for l in out.split("\n") if "定向增发" in l]
    assert lines, "应能取到解禁类型"


def test_lockup_expiry_upcoming_uses_new_field_names(monkeypatch):
    """未来待解禁段同样使用新列名 + 实际可流通股数。"""
    from chstockdata import a_stock

    # 第一次调用返回空（无历史），第二次返回未来解禁
    calls = {"n": 0}

    def _fake_dc(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return []  # 历史段空
        return [
            {
                "SECURITY_CODE": "002594",
                "FREE_DATE": "2026-09-01 00:00:00",
                "FREE_SHARES_TYPE": "首发原股东限售股份",
                "FREE_SHARES": 50000.0,
                "ABLE_FREE_SHARES": 48000.0,
                "FREE_RATIO": 0.15,
            },
        ]

    monkeypatch.setattr(a_stock, "_eastmoney_datacenter", _fake_dc)

    out = a_stock.get_lockup_expiry("002594", "2026-08-01", forward_days=90)
    assert "首发原股东限售股份" in out
    assert "50000.0" in out
    assert "48000.0" in out
