"""mootdx capability health wiring tests — per-method health recording.

Proves ``_mootdx_call`` records ``mootdx:<method>`` capability health, and
that a bars failure never marks finance/xdxr unhealthy. All offline: the
client and its methods are fakes.
"""

import pandas as pd
import pytest

from chstockdata import a_stock
from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    reset_capability_health()
    monkeypatch.setattr(a_stock, "_mootdx_unavailable_until", 0.0)
    monkeypatch.setattr(a_stock, "_mootdx_outage_rounds", 0)
    monkeypatch.setattr(a_stock, "_TDX_PROBE_GAP_S", 0.0)
    yield
    reset_capability_health()


class _Client:
    def __init__(self, *, bars_empty=False, bars_error=None, finance_ok=True):
        self.bars_empty = bars_empty
        self.bars_error = bars_error
        self.finance_ok = finance_ok

    def bars(self, **_kwargs):
        if self.bars_error:
            raise self.bars_error
        if self.bars_empty:
            return pd.DataFrame()
        return pd.DataFrame([{"close": 1500.0}])

    def finance(self, **_kwargs):
        if not self.finance_ok:
            raise ConnectionError("finance endpoint down")
        return pd.DataFrame([{"zongguben": 1}])

    def xdxr(self, **_kwargs):
        return pd.DataFrame([{"category": 1}])


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(a_stock, "_mootdx_client", client)
    monkeypatch.setattr(
        a_stock, "_get_mootdx_client", lambda *args, **kwargs: client
    )
    monkeypatch.setattr(a_stock, "_tdx_min_interval", lambda: 0.0)


def test_successful_bars_records_mootdx_bars_success(monkeypatch):
    _patch_client(monkeypatch, _Client())
    df = a_stock._mootdx_call("bars", symbol="600519", category=4, offset=1)
    assert not df.empty
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "success"
    assert snapshot["mootdx:bars"].is_healthy
    # 其它能力未被本次成功/失败触碰。
    assert "mootdx:finance" not in snapshot


def test_suppressed_call_leaves_health_to_its_structured_owner(monkeypatch):
    _patch_client(monkeypatch, _Client())

    a_stock._mootdx_call(
        "bars",
        symbol="600519",
        _observe_capability_health=False,
    )

    assert "mootdx:bars" not in capability_health_snapshot()


def test_bars_failure_does_not_poison_finance_or_xdxr(monkeypatch):
    client = _Client(bars_error=ConnectionError("bars endpoint down"))
    _patch_client(monkeypatch, client)

    with pytest.raises(ConnectionError):
        a_stock._mootdx_call("bars", symbol="600519")
    assert capability_health_snapshot()["mootdx:bars"].status == "failed"

    # finance 与 xdxr 各自独立：bars 挂不代表它们挂。
    finance = a_stock._mootdx_call("finance", symbol="600519")
    assert not finance.empty
    xdxr = a_stock._mootdx_call("xdxr", symbol="600519")
    assert not xdxr.empty
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    assert snapshot["mootdx:finance"].status == "success"
    assert snapshot["mootdx:xdxr"].status == "success"


def test_empty_result_records_normal_empty_not_failed(monkeypatch):
    _patch_client(monkeypatch, _Client(bars_empty=True))
    result = a_stock._mootdx_call("bars", symbol="000001", category=4, offset=1)
    assert isinstance(result, pd.DataFrame) and result.empty
    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "normal_empty"
    assert snapshot["mootdx:bars"].is_healthy


def test_client_selection_failure_records_only_requested_capability(monkeypatch):
    """选服失败只记录本次请求的 capability；其它能力由自己的调用各自观察。"""
    monkeypatch.setattr(a_stock, "_mootdx_client", None)
    monkeypatch.setattr(
        a_stock, "_get_mootdx_client", lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("mootdx 通达信服务器不可用")
        )
    )

    with pytest.raises(RuntimeError):
        a_stock._mootdx_call("bars", symbol="600519")

    snapshot = capability_health_snapshot()
    assert snapshot["mootdx:bars"].status == "failed"
    # 不再代写其它 capability 的结论。
    assert "mootdx:finance" not in snapshot
    assert "mootdx:xdxr" not in snapshot

    # 随后服务器恢复：能力健康自然翻正（无永久黑名单）。
    _patch_client(monkeypatch, _Client())
    a_stock._mootdx_call("bars", symbol="600519")
    assert capability_health_snapshot()["mootdx:bars"].status == "success"


def test_capability_mapping_is_stable_and_consumer_neutral():
    cap = a_stock._mootdx_capability_for_method("bars")
    assert cap.id() == "mootdx:bars"
    assert a_stock._mootdx_capability_for_method("quotes").id() == "mootdx:quote"
    assert a_stock._mootdx_capability_for_method("finance").id() == "mootdx:finance"
    assert a_stock._mootdx_capability_for_method("xdxr").id() == "mootdx:xdxr"
    # 未知方法按原名归档，不报错。
    assert a_stock._mootdx_capability_for_method("minutes").id() == "mootdx:minutes"
