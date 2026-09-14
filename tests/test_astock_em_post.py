"""Eastmoney POST helper（_em_post）节流/失败语义直测。"""

from __future__ import annotations

import pytest

from chstockdata import a_stock
from chstockdata.vendor_errors import VendorNetworkError


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code


def test_em_post_returns_response_and_passes_payload(monkeypatch):
    monkeypatch.setattr(a_stock, "_EM_MIN_INTERVAL", 0.0)
    calls: list[dict] = []

    def _fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _Resp(200)

    monkeypatch.setattr(a_stock._EM_SESSION, "post", _fake_post)
    response = a_stock._em_post(
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
        json={"pageSize": 10},
        headers={"User-Agent": "test"},
    )
    assert response.status_code == 200
    assert calls[0]["json"] == {"pageSize": 10}
    assert calls[0]["headers"] == {"User-Agent": "test"}


def test_em_post_403_fails_closed_as_vendor_error(monkeypatch):
    monkeypatch.setattr(a_stock, "_EM_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(
        a_stock._EM_SESSION, "post", lambda url, **kwargs: _Resp(403)
    )
    with pytest.raises(VendorNetworkError):
        a_stock._em_post("https://emappdata.eastmoney.com/x", json={})


def test_em_post_retries_5xx_once(monkeypatch):
    monkeypatch.setattr(a_stock, "_EM_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(a_stock.time, "sleep", lambda seconds: None)
    responses = iter([_Resp(500), _Resp(200)])
    monkeypatch.setattr(
        a_stock._EM_SESSION, "post", lambda url, **kwargs: next(responses)
    )
    response = a_stock._em_post("https://emappdata.eastmoney.com/x", json={})
    assert response.status_code == 200
