"""Governed HTTP and source-neutral parsing primitives for policy news.

This module intentionally contains no proxy support and no media/search-engine
fallback.  Source-specific adapters build on these primitives in later layers;
all records still pass through the same official-host and date validation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from dataclasses import replace
from html.parser import HTMLParser
import logging
import re
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

import requests

from .policy_news_models import PolicyNewsItem, PolicySource, SourceFetchResult


logger = logging.getLogger(__name__)

_POLICY_SESSION = requests.Session()
_POLICY_SESSION.trust_env = False
_POLICY_SESSION.headers.update(
    {"User-Agent": "TradingAgents-PolicyNews/1.0 (+official-source-retrieval)"}
)

_HOST_LOCKS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
_HOST_NEXT_ALLOWED: dict[str, float] = {}
_HOST_TIMING_LOCK = threading.Lock()

_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_ISSUER_LABEL_RE = re.compile(r"(?:来源|发布机关|发布单位|发文机关)\s*[:：]\s*")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _official_host_root(host: str) -> str:
    """Return the registered authority root for common official host aliases."""

    return host[4:] if host.startswith("www.") else host


def _validate_official_host(source: PolicySource, url: str) -> None:
    if not source.direct_official_endpoint:
        raise ValueError(
            f"source {source.authority_id!r} has no registered official host"
        )
    source_host = _host(source.direct_official_endpoint)
    requested = urlsplit(url)
    requested_host = _host(url)
    if requested.scheme not in {"http", "https"} or not requested_host:
        raise ValueError("policy request must use an official HTTP(S) host")
    official_root = _official_host_root(source_host)
    if requested_host not in {source_host, official_root} and not requested_host.endswith(
        f".{official_root}"
    ):
        raise ValueError(
            f"policy request URL is outside the registered official host: {requested_host}"
        )


def _timeout_for(source: PolicySource) -> tuple[float, float]:
    configured = float(source.request_budget.get("timeout", 15))
    if configured <= 0:
        configured = 15.0
    return min(5.0, configured), min(15.0, configured)


def _wait_for_host_budget(
    source: PolicySource,
    url: str,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    host = _host(url)
    minimum_interval = float(source.request_budget.get("min_interval", 0.25))
    if minimum_interval < 0:
        minimum_interval = 0.0
    now = monotonic()
    with _HOST_TIMING_LOCK:
        next_allowed = _HOST_NEXT_ALLOWED.get(host, now)
        delay = max(0.0, next_allowed - now)
        _HOST_NEXT_ALLOWED[host] = max(next_allowed, now) + minimum_interval
    if delay:
        sleep(delay)


def _request_with_one_retry(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, Any] | None,
    headers: Mapping[str, str] | None,
    timeout: tuple[float, float],
    retries: int,
) -> requests.Response:
    attempts = 1 + min(1, max(0, int(retries)))
    last_response: requests.Response | None = None
    for attempt in range(attempts):
        try:
            response = session.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            last_response = response
            if response.status_code >= 500 and attempt + 1 < attempts:
                continue
            return response
        except (requests.Timeout, requests.ConnectionError):
            if attempt + 1 >= attempts:
                raise
    if last_response is None:  # pragma: no cover - defensive loop guard
        raise requests.RequestException("policy request did not return a response")
    return last_response


def _request_post_with_one_retry(
    session: requests.Session,
    url: str,
    *,
    data: Mapping[str, Any] | None,
    headers: Mapping[str, str] | None,
    timeout: tuple[float, float],
    retries: int,
) -> requests.Response:
    attempts = 1 + min(1, max(0, int(retries)))
    last_response: requests.Response | None = None
    for attempt in range(attempts):
        try:
            response = session.post(
                url,
                data=data,
                headers=headers,
                timeout=timeout,
            )
            last_response = response
            if response.status_code >= 500 and attempt + 1 < attempts:
                continue
            return response
        except (requests.Timeout, requests.ConnectionError):
            if attempt + 1 >= attempts:
                raise
    if last_response is None:  # pragma: no cover - defensive loop guard
        raise requests.RequestException("policy request did not return a response")
    return last_response


class PolicyHttpClient:
    """Official-host HTTP client with per-host serialization and bounded retry."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or _POLICY_SESSION
        self.monotonic = monotonic
        self.sleep = sleep

    def get(
        self,
        source: PolicySource,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        _validate_official_host(source, url)
        host_lock = _HOST_LOCKS[_host(url)]
        with host_lock:
            _wait_for_host_budget(source, url, self.monotonic, self.sleep)
            return _request_with_one_retry(
                self.session,
                url,
                params=params,
                headers=headers,
                timeout=_timeout_for(source),
                retries=int(source.request_budget.get("retries", 1)),
            )

    def post(
        self,
        source: PolicySource,
        url: str,
        *,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        _validate_official_host(source, url)
        host_lock = _HOST_LOCKS[_host(url)]
        with host_lock:
            _wait_for_host_budget(source, url, self.monotonic, self.sleep)
            return _request_post_with_one_retry(
                self.session,
                url,
                data=data,
                headers=headers,
                timeout=_timeout_for(source),
                retries=int(source.request_budget.get("retries", 1)),
            )


def _first(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def _extract_json_records(parser_id: str, payload: object) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, Mapping):
        if parser_id == "csrc_json":
            # 2026-09-11 实测 searchList 载荷：{"data": {"total": .., "results": [..]}}
            data = payload.get("data")
            if not isinstance(data, Mapping):
                raise ValueError("CSRC searchList data key is missing")
            records = data.get("results")
            if not isinstance(records, list):
                raise ValueError("CSRC searchList results key is missing")
            if any(not isinstance(record, Mapping) for record in records):
                raise ValueError("official JSON records contain a malformed entry")
            return list(records)
        records = None
        candidate_keys = (
            "records",
            "data",
            "items",
            "rows",
            "list",
            "result",
            "datasource",
        )
        for key in candidate_keys:
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
            if isinstance(candidate, Mapping):
                for nested_key in ("records", "items", "rows", "list"):
                    nested = candidate.get(nested_key)
                    if isinstance(nested, list):
                        records = nested
                        break
                if records is not None:
                    break
        if records is None:
            raise ValueError("expected official records key is missing")
    else:
        raise ValueError("official JSON payload is not a record list")
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("official JSON records contain a malformed entry")
    return list(records)


class _OfficialListHTMLParser(HTMLParser):
    """Small parser that extracts links and nearby list/table text."""

    _STANDALONE_CLOSE_TAGS = frozenset(
        {"div", "p", "section", "nav", "dl", "dd", "dt", "td", "th"}
    )
    _LIST_ITEM_TAGS = frozenset({"li", "tr", "article", "dd"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[dict[str, str]] = []
        self._block: dict[str, Any] | None = None
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self._block_depth = 0

    def _finalize_block(self) -> None:
        if self._block is None:
            return
        href = str(self._block.get("href", ""))
        title = str(self._block.get("title", ""))
        text = " ".join(str(x) for x in self._block.get("parts", []))
        if href:
            self.records.append({"url": href, "title": title, "text": text})
        self._block = None
        self._block_depth = 0

    def close(self) -> None:
        super().close()
        if self._block is not None and self._block_depth == 0:
            self._finalize_block()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if (
            self._block is not None
            and self._block_depth == 0
            and self._anchor_href is None
            and tag in self._LIST_ITEM_TAGS
        ):
            self._finalize_block()
        if tag in self._LIST_ITEM_TAGS and self._block is None:
            self._block = {"href": "", "title": "", "parts": []}
            self._block_depth = 1
        elif self._block is not None and tag in self._LIST_ITEM_TAGS:
            self._block_depth += 1
        if tag == "a":
            self._anchor_href = attrs_dict.get("href")
            self._anchor_parts = []
            if self._block is None:
                self._block = {"href": "", "title": "", "parts": []}
                self._block_depth = 0

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._anchor_href is not None:
            title = " ".join("".join(self._anchor_parts).split())
            if self._block is not None:
                self._block["href"] = self._anchor_href or ""
                self._block["title"] = title
            self._anchor_href = None
            self._anchor_parts = []
            if self._block_depth == 0:
                return
        if tag in self._LIST_ITEM_TAGS and self._block is not None:
            if self._block_depth > 1:
                self._block_depth -= 1
            else:
                self._finalize_block()
        elif (
            self._block is not None
            and self._block_depth == 0
            and self._anchor_href is None
            and tag in self._STANDALONE_CLOSE_TAGS
        ):
            self._finalize_block()

    def handle_data(self, data: str) -> None:
        if self._block is not None:
            self._block["parts"].append(data)
        if self._anchor_href is not None:
            self._anchor_parts.append(data)


def _extract_html_records(parser_id: str, html: str) -> list[Mapping[str, Any]]:
    if not isinstance(html, str) or not html.strip():
        raise ValueError("official HTML payload is empty")
    parser = _OfficialListHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise ValueError("official HTML payload could not be parsed") from exc
    if not parser.records:
        if "<ul" in html.lower() or "<table" in html.lower():
            return []
        raise ValueError("official HTML list structure is missing")
    records: list[Mapping[str, Any]] = []
    for record in parser.records:
        combined = " ".join(
            part for part in (record.get("title", ""), record.get("text", "")) if part
        )
        match = _DATE_RE.search(combined)
        records.append(
            {
                "title": record.get("title", ""),
                "url": record.get("url", ""),
                "published_at": match.group(0) if match else "",
                "summary": record.get("text", ""),
            }
        )
    return records


def _response_text(response: requests.Response) -> str:
    """Decode official HTML using its declared or detected charset.

    Several official list pages omit a charset while ``requests`` defaults to
    ISO-8859-1.  Prefer the response bytes plus the detected UTF-8 encoding so
    issuer labels and Chinese titles remain auditable.  Test doubles that only
    expose ``text`` continue to use that field.
    """

    content = getattr(response, "content", None)
    if isinstance(content, bytes) and content:
        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("Content-Type", ""))
        charset_match = re.search(r"charset\s*=\s*([^;\s]+)", content_type, re.I)
        encoding = charset_match.group(1).strip('"\'') if charset_match else ""
        if not encoding:
            encoding = str(getattr(response, "apparent_encoding", "") or "")
        if not encoding:
            encoding = str(getattr(response, "encoding", "") or "utf-8")
        try:
            return content.decode(encoding, errors="replace")
        except (LookupError, UnicodeError):
            return content.decode("utf-8", errors="replace")
    return str(getattr(response, "text", "") or "")


class _InlineTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _clean_record_text(value: object) -> str:
    text = str(value or "").strip()
    if "<" not in text or ">" not in text:
        return " ".join(text.split())
    parser = _InlineTextParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return " ".join(text.split())
    return " ".join("".join(parser.parts).split())


def _normalize_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) >= 10:
        try:
            timestamp = float(text)
            if len(text) >= 13:
                timestamp /= 1000.0
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    match = _DATE_RE.search(text)
    if match:
        try:
            return date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).isoformat()
        except ValueError:
            return None
    try:
        if "T" in text or " " in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _normalize_source_records(
    records: list[Mapping[str, Any]],
    source: PolicySource,
    start_date: str,
    end_date: str,
    *,
    retrieval_mode: str = "direct",
) -> SourceFetchResult:
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except ValueError:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_date_window",
            limitation="日期窗口不可解析",
        )
    if start > end:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_date_window",
            limitation="日期窗口起止顺序无效",
        )
    if not records:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="normal_empty",
            retrieval_mode=retrieval_mode,
        )

    valid_record_count = 0
    items: list[PolicyNewsItem] = []
    for record in records:
        try:
            title = _clean_record_text(
                _first(
                    record,
                    "title",
                    "TITLE",
                    "docTitle",
                    "articleTitle",
                    "noticeTitle",
                    "doctitle",
                    "showTitle",
                )
            )
            raw_url = _first(
                record,
                "url",
                "URL",
                "link",
                "pdfFileUrl",
                "docFileUrl",
                "articleUrl",
                "urlPath",
                "docpuburl",
                "publishUrl",
            )
            published = _normalize_date(
                _first(
                    record,
                    "published_at",
                    "publishedTimeStr",
                    "publishDate",
                    "publishTime",
                    "pubDate",
                    "date",
                    "time",
                    "showTime",
                    "DOCRELPUBTIME",
                    "docpubtime",
                )
            )
            if not title or not isinstance(raw_url, str) or not published:
                continue
            url = urljoin(source.direct_official_endpoint or "", raw_url)
            _validate_official_host(source, url)
            valid_record_count += 1
            published_date = date.fromisoformat(published)
            if not (start <= published_date <= end):
                continue
            item = PolicyNewsItem(
                source_id=source.authority_id,
                source_name=source.authority_name,
                issuer=str(_first(record, "issuer", "ISSUER") or source.authority_name),
                scope=source.scope,
                title=title,
                summary=_clean_record_text(
                    _first(
                        record,
                        "summary",
                        "SUMMARY",
                        "description",
                        "docSummary",
                        "subTitle",
                        "SUB_TITLE",
                        "doccontent",
                        "subtitle",
                    )
                )[:300],
                url=url,
                published_at=published,
                policy_type=str(_first(record, "policy_type", "type") or "policy"),
                document_number=str(
                    _first(record, "document_number", "docNumber", "文号") or ""
                ),
                route_reason=source.route_predicates[0]
                if source.route_predicates
                else source.scope,
                retrieval_mode=retrieval_mode,
            )
            items.append(item)
        except (TypeError, ValueError):
            continue

    if items:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="success",
            items=tuple(items),
            retrieval_mode=retrieval_mode,
        )
    if valid_record_count:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="normal_empty",
            retrieval_mode=retrieval_mode,
        )
    return SourceFetchResult(
        source_id=source.authority_id,
        status="failed",
        reason_code="failed_structure",
        limitation="官方记录字段无法通过结构校验",
        retrieval_mode=retrieval_mode,
    )


def parse_json_records(
    payload: object,
    *,
    source: PolicySource,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    try:
        records = _extract_json_records(source.parser_id, payload)
    except ValueError:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_structure",
            limitation="官方 JSON 记录结构不符合注册契约",
        )
    return _normalize_source_records(records, source, start_date, end_date)


def parse_html_records(
    html: str,
    *,
    source: PolicySource,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    try:
        records = _extract_html_records(source.parser_id, html)
    except ValueError:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_structure",
            limitation="官方 HTML 列表结构不符合注册契约",
        )
    return _normalize_source_records(records, source, start_date, end_date)


def _network_reason(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "connection_error"
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", 0) or 0
        if 400 <= status < 500:
            return "http_4xx"
        if status >= 500:
            return "http_5xx"
        return "http_error"
    return "request_error"


def _parse_response(
    response: requests.Response,
    *,
    source: PolicySource,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    if source.parser_id.endswith("_json"):
        return parse_json_records(
            response.json(), source=source, start_date=start_date, end_date=end_date
        )
    return parse_html_records(
        _response_text(response), source=source, start_date=start_date, end_date=end_date
    )


_EXCHANGE_ALLOWED_PATHS = {
    "sse": ("/regulation/", "/lawandrules/"),
    "szse": ("/lawrules/",),
    "bse": ("/regulation",),
}
_EXCHANGE_ROUTE_REASONS = {
    "sse": "沪市交易场所监管",
    "szse": "深市交易场所监管",
    "bse": "北交所交易场所监管",
}
_COMPANY_DISCLOSURE_MARKERS = (
    "年度报告",
    "定期报告",
    "公司公告",
    "临时公告",
    "招股说明书",
)
_COMPANY_DISCLOSURE_PATH_MARKERS = (
    "/disclosure/",
    "/announcement/",
    "/company/",
)
_SZSE_SEARCH_FORM = {
    "keyword": "",
    "time": "0",
    "range": "title",
    "channelCode[]": "szserulesAllRulesBuss",
    "currentPage": "1",
    "pageSize": "20",
}


def parse_exchange_payload(
    source_id: str,
    payload: object,
    *,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    """Parse one exchange's rules/regulatory section with strict URL bounds."""

    from .policy_news_registry import SOURCES

    if source_id not in _EXCHANGE_ALLOWED_PATHS:
        raise ValueError(f"unsupported exchange source: {source_id!r}")
    source = SOURCES[source_id]
    try:
        if isinstance(payload, (list, Mapping)):
            records = _extract_json_records(source.parser_id, payload)
        else:
            records = _extract_html_records(source.parser_id, str(payload))
    except ValueError:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_structure",
            limitation="交易所官方栏目结构不符合注册契约",
        )

    accepted: list[Mapping[str, Any]] = []
    for record in records:
        raw_url = _first(
            record,
            "url",
            "URL",
            "link",
            "articleUrl",
            "urlPath",
            "docpuburl",
        )
        title = str(
            _first(
                record,
                "title",
                "TITLE",
                "articleTitle",
                "noticeTitle",
                "doctitle",
            )
            or ""
        )
        if not isinstance(raw_url, str) or not title:
            continue
        url = urljoin(source.direct_official_endpoint or "", raw_url)
        parsed = urlsplit(url)
        path = (parsed.path or "").lower()
        if not any(token in path for token in _EXCHANGE_ALLOWED_PATHS[source_id]):
            continue
        if any(marker in path for marker in _COMPANY_DISCLOSURE_PATH_MARKERS):
            continue
        if any(marker in title for marker in _COMPANY_DISCLOSURE_MARKERS):
            continue
        normalized = dict(record)
        normalized["url"] = url
        normalized["title"] = title
        normalized["route_reason"] = _EXCHANGE_ROUTE_REASONS[source_id]
        accepted.append(normalized)
    return _normalize_source_records(accepted, source, start_date, end_date)


def _parse_sse_response(response, **kwargs) -> SourceFetchResult:
    kwargs.pop("source", None)
    return parse_exchange_payload("sse", _response_text(response), **kwargs)


def _parse_szse_response(response, **kwargs) -> SourceFetchResult:
    kwargs.pop("source", None)
    return parse_exchange_payload("szse", _response_text(response), **kwargs)


def _parse_szse_json_response(response, **kwargs) -> SourceFetchResult:
    kwargs.pop("source", None)
    return parse_exchange_payload("szse", response.json(), **kwargs)


def _parse_bse_response(response, **kwargs) -> SourceFetchResult:
    kwargs.pop("source", None)
    return parse_exchange_payload("bse", _response_text(response), **kwargs)


def _parse_govcn_response(response, **kwargs) -> SourceFetchResult:
    return parse_html_records(_response_text(response), **kwargs)


def _parse_govcn_json_response(response, **kwargs) -> SourceFetchResult:
    return parse_json_records(response.json(), **kwargs)


def _parse_ndrc_response(response, **kwargs) -> SourceFetchResult:
    return parse_html_records(_response_text(response), **kwargs)


def _parse_mof_response(response, **kwargs) -> SourceFetchResult:
    return parse_html_records(_response_text(response), **kwargs)


def _parse_pboc_response(response, **kwargs) -> SourceFetchResult:
    return parse_html_records(_response_text(response), **kwargs)


PARSERS: dict[str, Callable[..., SourceFetchResult]] = {
    "govcn_html": _parse_govcn_response,
    "govcn_json": _parse_govcn_json_response,
    "ndrc_html": _parse_ndrc_response,
    "mof_html": _parse_mof_response,
    "pboc_html": _parse_pboc_response,
    "sse_html": _parse_sse_response,
    "szse_html": _parse_szse_response,
    "szse_json": _parse_szse_json_response,
    "bse_html": _parse_bse_response,
}
for _parser_id in (
    "miit_html",
    "nea_html",
    "nmpa_html",
    "nhsa_html",
    "safe_html",
    "cac_html",
    "nda_html",
    "mohurd_html",
    "sasac_html",
    "mee_html",
    "shandong_html",
):
    PARSERS[_parser_id] = _parse_response
# JSON 源统一走 _parse_response（按 parser_id 后缀分发到 parse_json_records）。
PARSERS["nea_json"] = _parse_response
PARSERS["nfra_json"] = _parse_response
PARSERS["csrc_json"] = _parse_response


def parse_source_payload(
    source_id: str,
    payload: object,
    *,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    """Parse a sanitized fixture using the registered source adapter."""

    from .policy_news_registry import SOURCES

    source = SOURCES[source_id]
    if source.scope == "exchange":
        return parse_exchange_payload(
            source_id,
            payload,
            start_date=start_date,
            end_date=end_date,
        )
    if source.parser_id.endswith("_json"):
        return parse_json_records(
            payload, source=source, start_date=start_date, end_date=end_date
        )
    return parse_html_records(
        str(payload), source=source, start_date=start_date, end_date=end_date
    )


def fetch_source(
    source: PolicySource,
    *,
    start_date: str,
    end_date: str,
    client: PolicyHttpClient,
) -> SourceFetchResult:
    if source.health_state != "enabled" or not source.direct_official_endpoint:
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="direct_unavailable",
            limitation="官方直接端点未启用",
        )
    try:
        if source.parser_id == "szse_json":
            response = client.post(
                source,
                source.direct_official_endpoint,
                data=_SZSE_SEARCH_FORM,
                headers={
                    "Referer": "https://www.szse.cn/lawrules/rule/new/index.html",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        else:
            response = client.get(
                source,
                source.direct_official_endpoint,
                headers={"Referer": source.direct_official_endpoint},
            )
        response.raise_for_status()
        parser = PARSERS.get(source.parser_id, _parse_response)
        return parser(
            response,
            source=source,
            start_date=start_date,
            end_date=end_date,
        )
    except requests.RequestException as exc:
        logger.warning(
            "policy source request failed source=%s stage=request error=%s",
            source.authority_id,
            type(exc).__name__,
        )
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code=_network_reason(exc),
            limitation=type(exc).__name__,
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "policy source parse failed source=%s stage=parse error=%s",
            source.authority_id,
            type(exc).__name__,
        )
        return SourceFetchResult(
            source_id=source.authority_id,
            status="failed",
            reason_code="failed_structure",
            limitation=type(exc).__name__,
        )


def _issuer_matches(source: PolicySource, issuer: str) -> bool:
    normalized = str(issuer or "").strip()
    if not normalized:
        return False
    aliases = (source.authority_name, *source.route_predicates)
    return any(alias and (alias in normalized or normalized in alias) for alias in aliases)


def _fallback_issuer(item: PolicyNewsItem, source: PolicySource) -> str | None:
    """Resolve an issuer only when the gov.cn record names it explicitly."""

    if _issuer_matches(source, item.issuer):
        return item.issuer
    record_text = " ".join((item.title, item.summary))
    if source.authority_name:
        for match in _ISSUER_LABEL_RE.finditer(record_text):
            if source.authority_name in record_text[match.end() : match.end() + 80]:
                return source.authority_name
    return None


def _fallback_item(item: PolicyNewsItem, source: PolicySource) -> PolicyNewsItem:
    return replace(
        item,
        source_id="govcn",
        source_name="中国政府网",
        scope=source.scope,
        route_reason=source.route_predicates[0]
        if source.route_predicates
        else source.scope,
        retrieval_mode="govcn_fallback",
    )


def fetch_govcn_for_authority(
    source: PolicySource,
    *,
    start_date: str,
    end_date: str,
    client: PolicyHttpClient,
) -> SourceFetchResult:
    """Fetch gov.cn records and retain only the registered issuing authority."""

    from .policy_news_registry import SOURCES

    govcn_source = SOURCES["govcn"]
    try:
        response = client.get(
            govcn_source,
            govcn_source.direct_official_endpoint,
            params={
                "keyword": source.authority_name,
                "start_date": start_date,
                "end_date": end_date,
            },
            headers={"Referer": govcn_source.direct_official_endpoint},
        )
        response.raise_for_status()
        parsed: SourceFetchResult | None = None
        try:
            parsed = parse_json_records(
                response.json(),
                source=govcn_source,
                start_date=start_date,
                end_date=end_date,
            )
        except (ValueError, TypeError, requests.JSONDecodeError):
            parsed = parse_html_records(
                response.text,
                source=govcn_source,
                start_date=start_date,
                end_date=end_date,
            )
    except requests.RequestException as exc:
        return SourceFetchResult(
            source_id="govcn",
            status="failed",
            reason_code=_network_reason(exc),
            limitation=type(exc).__name__,
            retrieval_mode="govcn_fallback",
        )
    except (ValueError, TypeError, KeyError) as exc:
        return SourceFetchResult(
            source_id="govcn",
            status="failed",
            reason_code="failed_structure",
            limitation=type(exc).__name__,
            retrieval_mode="govcn_fallback",
        )

    if parsed.status == "normal_empty":
        return SourceFetchResult(
            source_id="govcn",
            status="normal_empty",
            retrieval_mode="govcn_fallback",
        )
    if parsed.status != "success":
        return SourceFetchResult(
            source_id="govcn",
            status="failed",
            reason_code=parsed.reason_code or "fallback_failed",
            limitation=parsed.limitation or "中国政府网回退结果不可用",
            retrieval_mode="govcn_fallback",
        )

    matched_items: list[PolicyNewsItem] = []
    for item in parsed.items:
        issuer = _fallback_issuer(item, source)
        if issuer is None:
            continue
        matched_items.append(_fallback_item(replace(item, issuer=issuer), source))
    matched = tuple(matched_items)
    if not matched:
        return SourceFetchResult(
            source_id="govcn",
            status="failed",
            reason_code="failed_structure",
            limitation="中国政府网记录未通过发布机关/地域校验",
            retrieval_mode="govcn_fallback",
        )
    return SourceFetchResult(
        source_id="govcn",
        status="success",
        items=matched,
        retrieval_mode="govcn_fallback",
    )


def fetch_source_with_fallback(
    source: PolicySource,
    *,
    start_date: str,
    end_date: str,
    client: PolicyHttpClient,
) -> SourceFetchResult:
    """Try a direct authority endpoint, then only its registered gov.cn route."""

    direct = fetch_source(
        source,
        start_date=start_date,
        end_date=end_date,
        client=client,
    )
    if direct.status in {"success", "normal_empty"} or not source.govcn_fallback:
        return direct
    return fetch_govcn_for_authority(
        source,
        start_date=start_date,
        end_date=end_date,
        client=client,
    )


__all__ = [
    "PARSERS",
    "PolicyHttpClient",
    "_POLICY_SESSION",
    "fetch_source",
    "fetch_govcn_for_authority",
    "fetch_source_with_fallback",
    "parse_exchange_payload",
    "parse_html_records",
    "parse_json_records",
    "parse_source_payload",
]
