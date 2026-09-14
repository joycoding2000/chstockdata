"""回归测试：腾讯行情源 + 前缀路由三修复（移植自上游 a-stock-data v3.5.1 / v3.6.0）。

覆盖三个修复点：
- 修复1（v3.5.1）：_tencent_quote 的 44/45 市值字段标反 —— 44=流通市值、45=总市值
- 修复2（v3.5.1）：_get_prefix 把北交所 920xxx 误判为沪市 —— 920 号段应走 bj
- 修复3（v3.6.0）：_tencent_quote 加 is_stale 僵尸报价检测 —— 防止北交所老码/停牌股的定格报价

参考：上游 SKILL.md 的 tencent_quote() / get_prefix()；本地实现见 a_stock.py。
"""
import pytest


# ---------------------------------------------------------------------------
# 辅助：构造腾讯行情原始返回字符串
# ---------------------------------------------------------------------------
# 腾讯格式：v_sh600519="1~贵州茅台~600519~1689.00~..."; 多条用 ; 分隔，gbk 编码。
# vals 字段速查（实测校准）：
#   1=名称 3=最新价 4=昨收 5=开 32=涨跌幅 33=高 34=低 37=成交额(万)
#   38=换手率 39=PE_TTM 43=振幅 44=流通市值(亿) 45=总市值(亿) 46=PB
#   47=涨停价 48=跌停价 49=量比 52=市盈率(动) 53=市盈率(静)
# len(vals) < 53 的行会被跳过，因此构造时必须凑足 53 个字段。


def _build_tencent_line(
    prefix: str,
    code: str,
    name: str,
    price: str,
    last_close: str,
    amount_wan: str,
    mcap_float: str,
    mcap_total: str,
) -> str:
    """构造单条腾讯行情返回。其余字段填占位值，保证 len(vals) >= 53。"""
    vals = [""] * 60  # 多填几个防止边界
    vals[1] = name
    vals[3] = price
    vals[4] = last_close
    vals[5] = price  # open 用 price 占位
    vals[32] = "1.23"
    vals[33] = price  # high
    vals[34] = last_close  # low
    vals[37] = amount_wan
    vals[38] = "0.50"
    vals[39] = "30.5"  # PE_TTM
    vals[43] = "2.10"
    vals[44] = mcap_float
    vals[45] = mcap_total
    vals[46] = "7.8"  # PB
    vals[47] = "100.0"  # 涨停价
    vals[48] = "80.0"  # 跌停价
    vals[49] = "1.1"  # 量比
    vals[52] = "28.0"  # 市盈率(动)
    vals[53] = "35.0"  # 市盈率(静)
    return f'v_{prefix}{code}="' + "~".join(vals) + '"'


def _build_tencent_resp(lines: list[str]):
    """构造一个 mock 的 requests 响应对象，content 返回 gbk 编码的拼接行。"""
    raw = ";".join(lines)

    class _Resp:
        def __init__(self):
            self.content = raw.encode("gbk")

        def raise_for_status(self):
            return None

    return _Resp()


def _mock_tencent(monkeypatch, lines: list[str]) -> None:
    """把腾讯源改为返回构造行；v0.4.0 起 _tencent_quote 用 requests 而非 urllib。"""
    from chstockdata import a_stock

    monkeypatch.setattr(
        a_stock._requests,
        "get",
        lambda url, timeout=10, headers=None: _build_tencent_resp(lines),
    )


# ---------------------------------------------------------------------------
# 修复1：_tencent_quote 市值字段对调（44=流通、45=总）
# ---------------------------------------------------------------------------


def test_tencent_quote_mcap_uses_index_45(monkeypatch):
    """mcap_yi（总市值）应取 vals[45]，不是 vals[44]。"""
    from chstockdata import a_stock

    line = _build_tencent_line(
        "sh", "600519", "贵州茅台", "1689.00", "1680.00",
        amount_wan="100000", mcap_float="6000", mcap_total="20000",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["600519"])["600519"]
    assert q["mcap_yi"] == 20000, f"mcap_yi 应为 vals[45]=20000（总市值），实际 {q['mcap_yi']}"
    assert q["float_mcap_yi"] == 6000, f"float_mcap_yi 应为 vals[44]=6000（流通市值），实际 {q['float_mcap_yi']}"


def test_tencent_quote_mcap_when_total_ne_float(monkeypatch):
    """总股本≠流通股本时，总市值与流通市值差数倍，两者不得混淆（上游 v3.5.1 核心场景）。"""
    from chstockdata import a_stock

    # 中船特气 688146 实测：流通 356 亿 vs 总市值 1300 亿（3.65×）
    line = _build_tencent_line(
        "sh", "688146", "中船特气", "67.00", "66.00",
        amount_wan="50000", mcap_float="356.15", mcap_total="1300.61",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["688146"])["688146"]
    assert q["mcap_yi"] == pytest.approx(1300.61, rel=1e-3)
    assert q["float_mcap_yi"] == pytest.approx(356.15, rel=1e-3)
    # 关键：两者差 3.65 倍，标反会让大市值公司被误判成小盘股
    assert q["mcap_yi"] > q["float_mcap_yi"] * 3


def test_tencent_quote_mcap_equal_when_all_float(monkeypatch):
    """全流通股票两者相等，对调后行为不变（回归保护，防止过度修正）。"""
    from chstockdata import a_stock

    line = _build_tencent_line(
        "sh", "600519", "贵州茅台", "1689.00", "1680.00",
        amount_wan="100000", mcap_float="20000", mcap_total="20000",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["600519"])["600519"]
    assert q["mcap_yi"] == q["float_mcap_yi"] == 20000


def test_tencent_quote_pe_static_uses_index_53(monkeypatch):
    """pe_static（静态市盈率）应取 vals[53]，曾误取 vals[52]（动态，成长股差约 2×）。"""
    from chstockdata import a_stock

    # 实盘校准 300308：pos52=39.95（动）vs pos53=101.02（静）；构造器固定
    # vals[52]=28.0 / vals[53]=35.0，改回 52 时该断言必失败。
    line = _build_tencent_line(
        "sz", "300308", "中际旭创", "926.00", "890.10",
        amount_wan="100000", mcap_float="10278.02", mcap_total="10907.44",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["300308"])["300308"]
    assert q["pe_static"] == pytest.approx(35.0), (
        f"pe_static 应为 vals[53]=35.0（静态），实际 {q['pe_static']}（疑似取到 52 动态）"
    )


# ---------------------------------------------------------------------------
# 修复2：_get_prefix 920 号段北交所路由（纯函数，无需 mock）
# ---------------------------------------------------------------------------


def test_get_prefix_sh_for_600xxx():
    """沪市 6 开头 + 900xxx B 股 → sh。"""
    from chstockdata import a_stock

    assert a_stock._get_prefix("600519") == "sh"  # 贵州茅台
    assert a_stock._get_prefix("601318") == "sh"  # 中国平安
    assert a_stock._get_prefix("688017") == "sh"  # 科创板
    assert a_stock._get_prefix("900901") == "sh"  # 沪 B 股


def test_get_prefix_sz_for_000xxx_300xxx():
    """深市 000/002/300 开头 → sz。"""
    from chstockdata import a_stock

    assert a_stock._get_prefix("000001") == "sz"  # 平安银行
    assert a_stock._get_prefix("002594") == "sz"  # 比亚迪
    assert a_stock._get_prefix("300308") == "sz"  # 中际旭创


def test_get_prefix_bj_for_920xxx():
    """【核心修复】北交所 920xxx 新号段 → bj（曾误判为 sh）。"""
    from chstockdata import a_stock

    assert a_stock._get_prefix("920088") == "bj"  # 北交所新股
    assert a_stock._get_prefix("920185") == "bj"  # 贝特瑞（已从 835185 迁入）
    assert a_stock._get_prefix("920982") == "bj"  # 锦波生物（已从 832982 迁入）


def test_get_prefix_bj_for_old_8xxx_4xxx():
    """北交所老号段 43/83/87/88 + 4x → bj（回归保护）。"""
    from chstockdata import a_stock

    assert a_stock._get_prefix("830799") == "bj"  # 老北交所
    assert a_stock._get_prefix("832982") == "bj"  # 锦波生物老码
    assert a_stock._get_prefix("835185") == "bj"  # 贝特瑞老码
    assert a_stock._get_prefix("430047") == "bj"  # 老新三板/北交所


# ---------------------------------------------------------------------------
# 修复3：_tencent_quote is_stale 僵尸报价检测 + _resolve_price 守卫
# ---------------------------------------------------------------------------


def test_tencent_quote_marks_stale_when_zero_amount(monkeypatch):
    """成交额为 0 且价格==昨收 → is_stale=True（僵尸报价：北交所老码/停牌股的定格报价）。"""
    from chstockdata import a_stock

    # 模拟锦波生物老码 832982：返回定格在迁移日的报价（成交量 0、价格==昨收）
    line = _build_tencent_line(
        "bj", "832982", "锦波生物", "112.60", "112.60",
        amount_wan="0", mcap_float="50", mcap_total="60",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["832982"])["832982"]
    assert q["is_stale"] is True, (
        f"成交额0 + 价格{q['price']}==昨收{q['last_close']} 应判定为僵尸报价"
    )
    assert q["amount_wan"] == 0


def test_tencent_quote_not_stale_on_normal_quote(monkeypatch):
    """正常成交（成交额>0）→ is_stale=False（防止误判）。"""
    from chstockdata import a_stock

    line = _build_tencent_line(
        "bj", "920982", "锦波生物", "131.74", "130.00",
        amount_wan="50000", mcap_float="50", mcap_total="60",
    )
    _mock_tencent(monkeypatch, [line])
    q = a_stock._tencent_quote(["920982"])["920982"]
    assert q["is_stale"] is False, "正常成交不应标记为僵尸报价"


def test_resolve_price_rejects_zero_realtime():
    """实时价为 0 / None 时，_resolve_price 不应返回它当作真实价（守卫兜底）。"""
    from chstockdata import a_stock

    # 实时分析场景（curr_date=None → 非 historical）
    price, src = a_stock._resolve_price("600519", None, 0)
    assert price is None, "实时价为 0 不得冒充真实价"
    assert "unavailable" in src

    price, src = a_stock._resolve_price("600519", None, None)
    assert price is None
    assert "unavailable" in src
