"""投资者互动问答（巨潮互动易）— 提问 + 公司回复。

来源与坑（2026-09-14 实测，移植自上游 a-stock-data v3.7.1 §10.1）：

- 两步查询：先 ``queryKeyboardInfo``（POST body ``keyWord=code``）拿到
  ``data[0].secid`` 作为 ``orgId``；再查 ``company/question``。
- **第二步的参数必须放 query string（POST 但 body 为空）**，否则 HTTP 400；
  本模块按该口径实现并在测试里锁死。
- ``orgId`` 前缀可能是 ``gshk``（港股/跨市场 ID），靠 ``stockcode`` 过滤照样
  返回该 A 股问答，不要因为前缀不是 ``gssz``/``gssh`` 就跳过。
- 最新提问常未回复（``attachedContent`` 为 None），回复率因公司而异；
  未回复条目必须原样保留，不得从计数里剔除。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import a_stock
from .vendor_errors import (
    DeadlineExceeded,
    VendorError,
    VendorNetworkError,
    VendorNoDataError,
)

_CST = timezone(timedelta(hours=8))

_IRM_KEYWORD_URL = "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo"
_IRM_QUESTION_URL = "https://irm.cninfo.com.cn/newircs/company/question"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _format_ms(value: Any) -> str | None:
    """毫秒时间戳 → 北京时间 ``YYYY-MM-DD HH:MM``；无效返回 None。"""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    try:
        return datetime.fromtimestamp(number / 1000.0, tz=_CST).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return None


def _post(source_id: str, url: str, **kwargs):
    try:
        return a_stock._source_http_post(source_id, url, **kwargs)
    except DeadlineExceeded:
        raise
    except VendorError:
        raise
    except Exception as exc:
        raise VendorNetworkError(
            f"巨潮互动易请求失败：{type(exc).__name__}",
            vendor="cninfo_irm",
            method="http_post",
        ) from exc


def _json_payload(response, method: str) -> Any:
    status_code = getattr(response, "status_code", None)
    if status_code is not None and int(status_code) >= 400:
        raise VendorNoDataError(
            f"巨潮互动易返回 HTTP {status_code}",
            vendor="cninfo_irm",
            method=method,
            http_status=int(status_code),
        )
    try:
        return response.json()
    except Exception as exc:
        raise VendorNoDataError(
            f"巨潮互动易载荷不是合法 JSON：{type(exc).__name__}",
            vendor="cninfo_irm",
            method=method,
        ) from exc


def get_investor_qa(
    ticker: str, page_size: int = 30, page_num: int = 1
) -> dict[str, Any]:
    """投资者互动问答（深沪统一走巨潮互动易）。

    Returns:
        ``{ticker, org_id, page_size, page_num, count, answered_count, items,
        empty_reason, source, observed_at}``。每条含 ``question``（提问）、
        ``answer``（公司回复，未回复为 None）、``answerer``、``asked_at``、
        ``answered_at``。
    """
    try:
        code = a_stock._normalize_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"非法 ticker: {ticker!r} ({type(exc).__name__})") from exc
    if not 1 <= int(page_size) <= 100:
        raise ValueError(f"page_size 需在 1~100 之间，收到 {page_size}")
    if int(page_num) < 1:
        raise ValueError(f"page_num 从 1 开始，收到 {page_num}")

    keyword_response = _post(
        "cninfo",
        _IRM_KEYWORD_URL,
        data={"keyWord": code},
        headers={"User-Agent": a_stock._UA},
        timeout=10,
    )
    keyword_payload = _json_payload(keyword_response, "queryKeyboardInfo")
    records = keyword_payload.get("data") if isinstance(keyword_payload, dict) else None
    if not isinstance(records, list):
        raise VendorNoDataError(
            "巨潮互动易关键词载荷结构异常：data 不是列表",
            vendor="cninfo_irm",
            method="queryKeyboardInfo",
        )
    org_id = None
    for record in records:
        if isinstance(record, dict) and _text(record.get("secid")):
            org_id = _text(record.get("secid"))
            break
    if not org_id:
        raise VendorNoDataError(
            f"巨潮互动易未找到 {code} 的机构 ID（该代码可能无互动易记录）",
            vendor="cninfo_irm",
            method="queryKeyboardInfo",
        )

    # ⚠️ 第二步参数必须放 query string（POST body 为空），否则 400。
    question_response = _post(
        "cninfo",
        _IRM_QUESTION_URL,
        params={
            "_t": 1,
            "stockcode": code,
            "orgId": org_id,
            "pageSize": int(page_size),
            "pageNum": int(page_num),
            "keyWord": "",
            "startDay": "",
            "endDay": "",
        },
        headers={"User-Agent": a_stock._UA},
        timeout=10,
    )
    question_payload = _json_payload(question_response, "company/question")
    rows = question_payload.get("rows") if isinstance(question_payload, dict) else None
    if not isinstance(rows, list):
        raise VendorNoDataError(
            "巨潮互动易问答载荷结构异常：rows 不是列表",
            vendor="cninfo_irm",
            method="company/question",
        )

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        answer = row.get("attachedContent")
        items.append(
            {
                "question_id": _text(row.get("indexId")) or None,
                "company": _text(row.get("companyShortName")),
                "question": _text(row.get("mainContent")),
                "answer": _text(answer) if answer else None,
                "answerer": _text(row.get("attachedAuthor")) or None,
                "asked_at": _format_ms(row.get("pubDate")),
                "answered_at": _format_ms(row.get("attachedPubDate")),
                "status": "answered" if answer else "unanswered",
                "attachment_url": _text(row.get("attachmentUrl")) or None,
            }
        )

    answered = sum(1 for item in items if item["status"] == "answered")
    return {
        "ticker": code,
        "org_id": org_id,
        "page_size": int(page_size),
        "page_num": int(page_num),
        "count": len(items),
        "answered_count": answered,
        "items": items,
        "empty_reason": (
            None
            if items
            else f"该页无问答记录（第 {page_num} 页无数据或公司暂无互动记录）"
        ),
        "source": "cninfo irm (互动易)",
        "observed_at": datetime.now(_CST).isoformat(timespec="seconds"),
        "note": "回复率为公司行为差异；未回复条目原样保留（answer=None）。",
    }


__all__ = ["get_investor_qa"]
