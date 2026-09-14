"""Point-in-time visibility rules for financial observations.

Financial period end dates describe what a report measures, not when the market
could have known it.  Historical analysis therefore requires a source supplied
announcement date.  Sources that expose only a current snapshot are excluded
instead of being presented as historical facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping


POINT_IN_TIME_LIMITED_MARKER = "[点时数据已过滤]"
POINT_IN_TIME_UNAVAILABLE_MARKER = "[点时数据不可用]"

_ANNOUNCEMENT_KEYS = (
    "ann_date",
    "f_ann_date",
    "announcement_date",
    "publish_date",
    "notice_date",
)
_PERIOD_KEYS = ("end_date", "period_end", "报告日")


def _parse_date(value: Any) -> date | None:
    """Parse provider dates in ISO, compact ISO, or pandas-compatible form."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10:
        text = text[:10]
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text)
    except ValueError:
        return None


def is_historical_analysis(analysis_date: str | date | None, *, as_of_date: date | None = None) -> bool:
    """Legacy date fallback for callers without an explicit temporal context."""
    parsed = _parse_date(analysis_date)
    return bool(parsed and parsed < (as_of_date or date.today()))


@dataclass(frozen=True)
class FinancialObservation:
    """A value plus the dates required to audit historical visibility."""

    value: Mapping[str, Any]
    source: str
    period_end: date | None = None
    announcement_date: date | None = None
    observed_at: datetime | None = None
    point_in_time_safe: bool = False
    exclusion_reason: str | None = None


def _record_date(record: Mapping[str, Any], keys: tuple[str, ...]) -> date | None:
    for key in keys:
        parsed = _parse_date(record.get(key))
        if parsed is not None:
            return parsed
    return None


def filter_financial_records(
    records: Iterable[Mapping[str, Any]],
    analysis_date: str | date | None,
    *,
    source: str,
    as_of_date: date | None = None,
    historical_review: bool | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Select the latest announced revision visible on ``analysis_date``.

    Current analyses retain provider records.  Historical analyses reject a
    record without a reliable announcement date, reject future announcements,
    and choose the most recently announced visible revision per report period.
    """
    copied = [dict(record) for record in records]
    requires_point_in_time = (
        is_historical_analysis(analysis_date, as_of_date=as_of_date)
        if historical_review is None
        else historical_review
    )
    if not requires_point_in_time:
        return copied, 0

    cutoff = _parse_date(analysis_date)
    assert cutoff is not None
    visible_by_period: dict[str, tuple[date, dict[str, Any]]] = {}
    excluded = 0
    for record in copied:
        announcement_date = _record_date(record, _ANNOUNCEMENT_KEYS)
        period_end = _record_date(record, _PERIOD_KEYS)
        observation = FinancialObservation(
            value=record,
            source=source,
            period_end=period_end,
            announcement_date=announcement_date,
            point_in_time_safe=bool(announcement_date and announcement_date <= cutoff),
            exclusion_reason=(
                None
                if announcement_date and announcement_date <= cutoff
                else "missing announcement date" if announcement_date is None
                else "announcement date after analysis date"
            ),
        )
        if not observation.point_in_time_safe:
            excluded += 1
            continue
        period_key = period_end.isoformat() if period_end else str(record)
        previous = visible_by_period.get(period_key)
        if previous is None or announcement_date >= previous[0]:
            visible_by_period[period_key] = (announcement_date, record)

    visible = [entry[1] for entry in visible_by_period.values()]
    visible.sort(
        key=lambda record: (_record_date(record, _PERIOD_KEYS) or date.min), reverse=True
    )
    return visible, excluded


def point_in_time_unavailable_message(source: str) -> str:
    """A stable tool-facing marker for a source unavailable in a past run."""
    return (
        f"{POINT_IN_TIME_UNAVAILABLE_MARKER} {source} 未提供可核验公告日；"
        "当前快照不适用于历史日期，已排除以避免前视偏差。"
    )
