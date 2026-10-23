"""Immutable contracts for routed official policy-news evidence.

The policy-news pipeline deliberately keeps routing metadata, retrieval state,
and normalized records separate from the company-news contract.  These small
dataclasses are the boundary between source adapters and the aggregation/data
plane layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from re import fullmatch
from typing import Literal, Mapping
from urllib.parse import urlsplit


PolicyScope = Literal["core", "exchange", "province", "industry"]
SourceStatus = Literal["success", "normal_empty", "failed", "not_routed"]
RetrievalMode = Literal["direct", "govcn_fallback"]
HealthState = Literal["enabled", "direct_unavailable", "disabled"]
Exchange = Literal["sse", "szse", "bse"]

_POLICY_SCOPES = {"core", "exchange", "province", "industry"}
_SOURCE_STATUSES = {"success", "normal_empty", "failed", "not_routed"}
_RETRIEVAL_MODES = {"direct", "govcn_fallback"}
_HEALTH_STATES = {"enabled", "direct_unavailable", "disabled"}
_EXCHANGES = {"sse", "szse", "bse"}


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _validate_http_url(url: object, field_name: str) -> str:
    if not isinstance(url, str):
        raise ValueError(f"{field_name} must be an official HTTP(S) URL")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an official HTTP(S) URL")
    return url


def _validate_iso_date(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("published_at must be an ISO date or datetime")
    text = value.strip()
    try:
        if "T" in text or " " in text:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("published_at must be an ISO date or datetime") from exc
    return value


@dataclass(frozen=True)
class PolicyTargetContext:
    """Structured company context used to select conditional authorities."""

    ticker: str
    exchange: Exchange
    province: str | None
    industry: str | None
    concepts: tuple[str, ...]
    selected_industry_authorities: tuple[str, ...]
    routing_source: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not fullmatch(r"\d{6}", self.ticker):
            raise ValueError("ticker must be a six-digit A-stock code")
        if self.exchange not in _EXCHANGES:
            raise ValueError(f"unsupported exchange: {self.exchange!r}")
        if len(self.selected_industry_authorities) > 2:
            raise ValueError("selected_industry_authorities supports at most two authorities")
        if not isinstance(self.concepts, tuple):
            object.__setattr__(self, "concepts", tuple(self.concepts))
        if not isinstance(self.selected_industry_authorities, tuple):
            object.__setattr__(
                self,
                "selected_industry_authorities",
                tuple(self.selected_industry_authorities),
            )
        if not isinstance(self.limitations, tuple):
            object.__setattr__(self, "limitations", tuple(self.limitations))
        _require_text(self.routing_source, "routing_source")


@dataclass(frozen=True)
class PolicySource:
    """Registered authority and the endpoint contract used to access it."""

    authority_id: str
    authority_name: str
    scope: PolicyScope
    direct_official_endpoint: str | None
    govcn_fallback: bool
    route_predicates: tuple[str, ...]
    request_budget: Mapping[str, int | float]
    parser_id: str
    health_state: HealthState

    def __post_init__(self) -> None:
        _require_text(self.authority_id, "authority_id")
        _require_text(self.authority_name, "authority_name")
        _require_text(self.parser_id, "parser_id")
        if self.scope not in _POLICY_SCOPES:
            raise ValueError(f"unsupported scope: {self.scope!r}")
        if self.health_state not in _HEALTH_STATES:
            raise ValueError(f"unsupported health_state: {self.health_state!r}")
        if self.direct_official_endpoint is not None:
            _validate_http_url(self.direct_official_endpoint, "direct_official_endpoint")
        if not isinstance(self.govcn_fallback, bool):
            raise ValueError("govcn_fallback must be bool")
        if not isinstance(self.route_predicates, tuple):
            object.__setattr__(self, "route_predicates", tuple(self.route_predicates))
        if not isinstance(self.request_budget, Mapping):
            raise ValueError("request_budget must be a mapping")


@dataclass(frozen=True)
class PolicyNewsItem:
    """One normalized policy or regulatory record from an official page."""

    source_id: str
    source_name: str
    issuer: str
    scope: PolicyScope
    title: str
    summary: str
    url: str
    published_at: str
    policy_type: str
    document_number: str
    route_reason: str
    retrieval_mode: RetrievalMode

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.source_name, "source_name")
        _require_text(self.title, "title")
        _require_text(self.policy_type, "policy_type")
        _require_text(self.route_reason, "route_reason")
        if self.scope not in _POLICY_SCOPES:
            raise ValueError(f"unsupported scope: {self.scope!r}")
        if self.retrieval_mode not in _RETRIEVAL_MODES:
            raise ValueError(f"unsupported retrieval_mode: {self.retrieval_mode!r}")
        _validate_http_url(self.url, "url")
        _validate_iso_date(self.published_at)


@dataclass(frozen=True)
class SourceFetchResult:
    """Per-authority result with explicit failure and empty-result semantics."""

    source_id: str
    status: SourceStatus
    items: tuple[PolicyNewsItem, ...] = ()
    reason_code: str = ""
    limitation: str = ""
    retrieval_mode: RetrievalMode = "direct"

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        if self.status not in _SOURCE_STATUSES:
            raise ValueError(f"unsupported status: {self.status!r}")
        if self.retrieval_mode not in _RETRIEVAL_MODES:
            raise ValueError(f"unsupported retrieval_mode: {self.retrieval_mode!r}")
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        if any(not isinstance(item, PolicyNewsItem) for item in self.items):
            raise ValueError("items must contain PolicyNewsItem values")
        if self.status == "success" and not self.items:
            raise ValueError("success result requires items")
        if self.status == "normal_empty" and self.items:
            raise ValueError("normal_empty result must not contain items")
        if self.status in {"failed", "not_routed"}:
            _require_text(self.reason_code, "reason_code")
            if self.items:
                raise ValueError(f"{self.status} result must not contain items")


@dataclass(frozen=True)
class PolicyAggregateResult:
    """Stable aggregate passed to the policy renderer and Evidence projection."""

    context: PolicyTargetContext
    items: tuple[PolicyNewsItem, ...]
    source_results: tuple[SourceFetchResult, ...]
    core_selected: int
    province_selected: int
    industry_selected: int
    item_counts_by_authority: Mapping[str, int]
    not_routed: tuple[str, ...]
    start_date: str = ""
    end_date: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        if not isinstance(self.source_results, tuple):
            object.__setattr__(self, "source_results", tuple(self.source_results))
        if not isinstance(self.not_routed, tuple):
            object.__setattr__(self, "not_routed", tuple(self.not_routed))


__all__ = [
    "Exchange",
    "HealthState",
    "PolicyNewsItem",
    "PolicyAggregateResult",
    "PolicyScope",
    "PolicySource",
    "PolicyTargetContext",
    "RetrievalMode",
    "SourceFetchResult",
    "SourceStatus",
]
