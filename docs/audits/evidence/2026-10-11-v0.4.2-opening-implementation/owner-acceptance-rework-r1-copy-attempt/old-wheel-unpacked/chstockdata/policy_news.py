"""Bounded aggregation and rendering for independently sourced policy news."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
import logging
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from .policy_news_models import (
    PolicyAggregateResult,
    PolicyNewsItem,
    PolicySource,
    PolicyTargetContext,
    SourceFetchResult,
)
from .policy_news_registry import PROVINCE_BY_NAME, select_policy_sources
from .policy_news_sources import (
    PolicyHttpClient,
    fetch_source_with_fallback,
)


logger = logging.getLogger(__name__)

_POLICY_HTTP_CLIENT = PolicyHttpClient()
_MAX_WORKERS = 3
_PER_AUTHORITY_LIMIT = 5
_TOTAL_LIMIT = 40


def _failed_result(source: PolicySource, exc: Exception) -> SourceFetchResult:
    logger.warning(
        "policy source fetcher failed source=%s error=%s",
        source.authority_id,
        type(exc).__name__,
    )
    return SourceFetchResult(
        source_id=source.authority_id,
        status="failed",
        reason_code="fetcher_exception",
        limitation=type(exc).__name__,
    )


def _fetch_one(
    fetcher: Callable[..., SourceFetchResult],
    source: PolicySource,
    start_date: str,
    end_date: str,
) -> SourceFetchResult:
    try:
        result = fetcher(
            source,
            start_date=start_date,
            end_date=end_date,
            client=_POLICY_HTTP_CLIENT,
        )
        if not isinstance(result, SourceFetchResult):
            raise TypeError("source fetcher returned an invalid result")
        return result
    except Exception as exc:  # source isolation is part of the public contract
        return _failed_result(source, exc)


def _date_sort_key(item: PolicyNewsItem) -> datetime:
    text = item.published_at.replace("Z", "+00:00")
    try:
        if "T" in text or " " in text:
            return datetime.fromisoformat(text).replace(tzinfo=None)
        return datetime.fromisoformat(text + "T00:00:00")
    except ValueError:
        return datetime.min


def _normalized_url_key(url: str) -> str:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path.rstrip("/") or "/", parsed.query, "")
    )


def _item_dedup_keys(item: PolicyNewsItem) -> tuple[tuple[str, str], ...]:
    keys: list[tuple[str, str]] = [("url", _normalized_url_key(item.url))]
    if item.issuer and item.document_number:
        keys.append(("issuer_document", f"{item.issuer}\x1f{item.document_number}"))
    keys.append(
        (
            "issuer_date_title",
            f"{item.issuer}\x1f{item.published_at}\x1f{item.title}",
        )
    )
    return tuple(keys)


def _deduplicate_and_limit(
    source_pairs: tuple[tuple[str, SourceFetchResult], ...],
    *,
    per_authority: int = _PER_AUTHORITY_LIMIT,
    total: int = _TOTAL_LIMIT,
) -> tuple[tuple[PolicyNewsItem, ...], dict[str, int]]:
    seen: set[tuple[str, str]] = set()
    kept_by_source: dict[str, int] = {source_id: 0 for source_id, _ in source_pairs}
    candidates: list[tuple[str, PolicyNewsItem]] = []
    for source_id, result in source_pairs:
        if result.status != "success":
            continue
        for item in result.items:
            if kept_by_source[source_id] >= per_authority:
                break
            keys = _item_dedup_keys(item)
            if any(key in seen for key in keys):
                continue
            seen.update(keys)
            candidates.append((source_id, item))
            kept_by_source[source_id] += 1

    candidates.sort(key=lambda pair: _date_sort_key(pair[1]), reverse=True)
    limited = candidates[:total]
    counts = {source_id: 0 for source_id, _ in source_pairs}
    for source_id, _ in limited:
        counts[source_id] = counts.get(source_id, 0) + 1
    return tuple(item for _, item in limited), counts


def _not_routed_reasons(context: PolicyTargetContext) -> tuple[str, ...]:
    reasons = list(context.limitations)
    if not context.province or context.province not in PROVINCE_BY_NAME:
        if "province_context_unavailable" not in reasons:
            reasons.append("province_context_unavailable")
    if not context.selected_industry_authorities:
        reason = (
            "industry_context_unavailable"
            if not context.industry
            else "industry_authority_unavailable"
        )
        if reason not in reasons:
            reasons.append(reason)
    return tuple(dict.fromkeys(reasons))


def aggregate_policy_news(
    context: PolicyTargetContext,
    start_date: str,
    end_date: str,
    *,
    fetcher: Callable[..., SourceFetchResult] = fetch_source_with_fallback,
) -> PolicyAggregateResult:
    """Fetch selected authorities concurrently while preserving registry order."""

    selected = select_policy_sources(context)
    futures: dict[str, Future[SourceFetchResult]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        for source in selected:
            futures[source.authority_id] = executor.submit(
                _fetch_one,
                fetcher,
                source,
                start_date,
                end_date,
            )
        results = tuple(
            futures[source.authority_id].result() for source in selected
        )

    source_pairs = tuple(
        (source.authority_id, result) for source, result in zip(selected, results)
    )
    items, counts = _deduplicate_and_limit(source_pairs)
    core_selected = sum(source.scope in {"core", "exchange"} for source in selected)
    province_selected = sum(source.scope == "province" for source in selected)
    industry_selected = sum(source.scope == "industry" for source in selected)
    return PolicyAggregateResult(
        context=context,
        items=items,
        source_results=results,
        core_selected=core_selected,
        province_selected=province_selected,
        industry_selected=industry_selected,
        item_counts_by_authority=counts,
        not_routed=_not_routed_reasons(context),
        start_date=start_date,
        end_date=end_date,
    )


def _status_label(status: str) -> str:
    return {
        "success": "成功",
        "normal_empty": "正常空",
        "failed": "失败",
        "not_routed": "未路由",
    }.get(status, status)


def _mode_label(mode: str) -> str:
    return "中国政府网回退" if mode == "govcn_fallback" else "直接官网"


def _aggregate_status_prefix(result: PolicyAggregateResult) -> str:
    statuses = tuple(source_result.status for source_result in result.source_results)
    if result.items:
        degraded = bool(result.not_routed) or any(
            status in {"failed", "normal_empty", "not_routed"} for status in statuses
        )
        return "[部分成功]" if degraded else "[成功]"
    if statuses and all(status == "normal_empty" for status in statuses):
        return "[正常空]"
    return "[数据缺失]"


def _render_coverage(result: PolicyAggregateResult) -> list[str]:
    selected = select_policy_sources(result.context)
    lines = [
        f"检索日期: {result.start_date} 至 {result.end_date}",
        f"核心来源覆盖: {result.core_selected}/6",
        f"条件源路由: 省级 {result.province_selected}/1，行业 {result.industry_selected}/2",
        "来源状态:",
    ]
    for source, source_result in zip(selected, result.source_results):
        actual_name = source.authority_name
        if source_result.retrieval_mode == "govcn_fallback":
            actual_name = "中国政府网"
        detail = (
            f"- {source.authority_name}: {_status_label(source_result.status)}；"
            f"{_mode_label(source_result.retrieval_mode)}；实际来源={actual_name}"
        )
        if source_result.reason_code:
            detail += f"；reason_code={source_result.reason_code}"
        if source_result.limitation:
            detail += f"；限制={source_result.limitation}"
        lines.append(detail)

    empty_sources = [
        source.authority_name
        for source, source_result in zip(selected, result.source_results)
        if source_result.status == "normal_empty"
    ]
    failed_sources = [
        f"{source.authority_name}({source_result.reason_code or 'failed'})"
        for source, source_result in zip(selected, result.source_results)
        if source_result.status == "failed"
    ]
    if empty_sources:
        lines.append("已验证正常空: " + "、".join(empty_sources))
    if failed_sources:
        lines.append("失败来源: " + "、".join(failed_sources))
    if result.not_routed:
        lines.append("未路由限制: " + "、".join(result.not_routed))
    return lines


def _render_items(items: tuple[PolicyNewsItem, ...]) -> list[str]:
    lines: list[str] = []
    if not items:
        return lines
    lines.append("政策/监管记录:")
    for item in items:
        lines.extend(
            [
                f"### {item.title}",
                f"发布机关: {item.issuer or '未确认'}",
                f"发布日期: {item.published_at}",
                f"路由原因: {item.route_reason}",
                f"检索方式: {_mode_label(item.retrieval_mode)}",
                f"官方链接: {item.url}",
            ]
        )
        if item.document_number:
            lines.append(f"文号: {item.document_number}")
        if item.summary:
            lines.append(f"摘要: {item.summary[:300]}")
        lines.append("")
    return lines


def render_policy_news(result: PolicyAggregateResult) -> str:
    """Render coverage and evidence without hiding source degradation."""

    lines = [_aggregate_status_prefix(result)]
    lines.extend(_render_coverage(result))
    if result.items and _aggregate_status_prefix(result) == "[部分成功]":
        lines.append("降级说明: 部分来源为空、失败、回退或未路由；请勿将未成功来源视为事实。")
    lines.extend(_render_items(result.items))
    return "\n".join(lines).rstrip()


def get_policy_news_for_context(
    context: PolicyTargetContext,
    start_date: str,
    end_date: str,
    *,
    fetcher: Callable[..., SourceFetchResult] = fetch_source_with_fallback,
) -> str:
    return render_policy_news(
        aggregate_policy_news(context, start_date, end_date, fetcher=fetcher)
    )


__all__ = [
    "aggregate_policy_news",
    "get_policy_news_for_context",
    "render_policy_news",
]
