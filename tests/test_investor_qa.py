"""互动易问答（get_investor_qa）离线回归。"""

from __future__ import annotations

import pytest

from chstockdata import investor_qa
from chstockdata.vendor_errors import VendorNetworkError, VendorNoDataError


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


_KEYWORD = {"data": [{"secid": "gshk0001211", "stockCode": "002594"}]}
_QUESTIONS = {
    "rows": [
        {
            "indexId": "123456",
            "companyShortName": "比亚迪",
            "mainContent": "公司在固态电池方面有何进展？",
            "attachedContent": "感谢您的关注，公司持续推进相关技术研发。",
            "attachedAuthor": "比亚迪",
            "pubDate": 1757826000000,
            "attachedPubDate": 1757833200000,
            "attachmentUrl": None,
        },
        {
            "indexId": "123457",
            "companyShortName": "比亚迪",
            "mainContent": "最新股东人数是多少？",
            "attachedContent": None,
            "attachedAuthor": None,
            "pubDate": 1757912400000,
            "attachedPubDate": None,
            "attachmentUrl": None,
        },
    ]
}


def test_investor_qa_two_step_and_query_string_params(monkeypatch):
    calls: list[dict] = []

    def _fake(source_id, url, **kwargs):
        calls.append({"source_id": source_id, "url": url, **kwargs})
        return _FakeResponse(_KEYWORD if len(calls) == 1 else _QUESTIONS)

    monkeypatch.setattr(investor_qa.a_stock, "_source_http_post", _fake)
    result = investor_qa.get_investor_qa("002594", page_size=10)
    assert calls[0]["url"].endswith("queryKeyboardInfo")
    assert calls[0]["data"] == {"keyWord": "002594"}
    assert calls[1]["url"].endswith("company/question")
    # 第二步：参数在 query string（params），body 为空——否则源端 400。
    assert calls[1].get("data") is None
    assert calls[1]["params"]["orgId"] == "gshk0001211"
    assert calls[1]["params"]["stockcode"] == "002594"
    assert calls[1]["params"]["pageSize"] == 10

    assert result["ticker"] == "002594"
    assert result["org_id"] == "gshk0001211"
    assert result["count"] == 2
    assert result["answered_count"] == 1
    answered, unanswered = result["items"]
    assert answered["status"] == "answered"
    assert answered["asked_at"] == "2025-09-14 13:00"
    assert answered["answered_at"] == "2025-09-14 15:00"
    assert unanswered["status"] == "unanswered"
    assert unanswered["answer"] is None


def test_investor_qa_rejects_bad_inputs():
    with pytest.raises(ValueError, match="非法 ticker"):
        investor_qa.get_investor_qa("AAPL")
    with pytest.raises(ValueError, match="page_size"):
        investor_qa.get_investor_qa("002594", page_size=0)
    with pytest.raises(ValueError, match="page_num"):
        investor_qa.get_investor_qa("002594", page_num=0)


def test_investor_qa_missing_org_id_fails_loud(monkeypatch):
    monkeypatch.setattr(
        investor_qa.a_stock,
        "_source_http_post",
        lambda *a, **kw: _FakeResponse({"data": []}),
    )
    with pytest.raises(VendorNoDataError, match="未找到"):
        investor_qa.get_investor_qa("002594")


def test_investor_qa_structure_and_network_failures(monkeypatch):
    responses = iter(
        [_FakeResponse(_KEYWORD), _FakeResponse({"rows": None})]
    )
    monkeypatch.setattr(
        investor_qa.a_stock, "_source_http_post", lambda *a, **kw: next(responses)
    )
    with pytest.raises(VendorNoDataError, match="结构异常"):
        investor_qa.get_investor_qa("002594")

    def _boom(*args, **kwargs):
        raise OSError("reset")

    monkeypatch.setattr(investor_qa.a_stock, "_source_http_post", _boom)
    with pytest.raises(VendorNetworkError, match="请求失败"):
        investor_qa.get_investor_qa("002594")
