"""结构化 Evidence/provenance 数据模型 — ProviderAttempt[] 是来源追溯的唯一事实来源。

Extracted from TradingAgents-astock ``dataflows/evidence.py`` (pure core); the
host-side capability registry integration is injectable, see
``set_capability_resolver``. 源仓库架构依据: docs/releases/v0.4.0/architecture-design.md §9.2

安全约束（Phase 3 审查修复）:
  - ProviderAttempt 构造时校验 status 枚举、duration_ms >= 0、provider 非空
  - validate_envelope() 供 Ledger 在信任 Evidence 前进行 schema + 语义校验
  - to_dict() 输出的派生字段（final_provider 等）仅用于序列化；
    Ledger 消费方应从 attempts 自行派生，不信任序列化值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# ── ProviderAttempt status ──────────────────────────────────────────────────
# 与 quality_ledger.py 的工具状态保持语义一致，但更细粒度地表达 Provider 层失败原因。
ATTEMPT_SUCCESS = "success"
ATTEMPT_NORMAL_EMPTY = "normal_empty"
ATTEMPT_FAILED_NETWORK = "failed_network"
ATTEMPT_FAILED_AUTH = "failed_auth"
ATTEMPT_FAILED_RATE_LIMIT = "failed_rate_limit"
ATTEMPT_FAILED_STRUCTURE = "failed_structure"
ATTEMPT_SKIPPED = "skipped"
ATTEMPT_SKIPPED_DUE_TO_RUN_CIRCUIT = "skipped_due_to_run_circuit"

_VALID_ATTEMPT_STATUSES: frozenset[str] = frozenset({
    ATTEMPT_SUCCESS,
    ATTEMPT_NORMAL_EMPTY,
    ATTEMPT_FAILED_NETWORK,
    ATTEMPT_FAILED_AUTH,
    ATTEMPT_FAILED_RATE_LIMIT,
    ATTEMPT_FAILED_STRUCTURE,
    ATTEMPT_SKIPPED,
    ATTEMPT_SKIPPED_DUE_TO_RUN_CIRCUIT,
})

# Final status — 派生值，不持久化为独立字段
FINAL_SUCCESS = "success"
FINAL_NORMAL_EMPTY = "normal_empty"
FINAL_RECOVERABLE_FAILURE = "recoverable_failure"
FINAL_INVALID_INPUT = "invalid_input"
FINAL_UNAVAILABLE = "unavailable"
FINAL_PIT_UNAVAILABLE = "pit_unavailable"

# 完整性枚举
COMPLETENESS_FULL = "full"
COMPLETENESS_PARTIAL = "partial"
COMPLETENESS_MINIMAL = "minimal"
_VALID_COMPLETENESS: frozenset[str] = frozenset({
    COMPLETENESS_FULL, COMPLETENESS_PARTIAL, COMPLETENESS_MINIMAL,
})

# 最大错误摘要长度（防止注入/溢出）
_MAX_ERROR_SUMMARY_LENGTH = 500


def _sanitize_error_summary(raw: str | None) -> str | None:
    """Truncate and strip error summaries to prevent injection or overflow."""
    if raw is None:
        return None
    return raw.strip()[: _MAX_ERROR_SUMMARY_LENGTH]


@dataclass
class ProviderAttempt:
    """单次 Provider 调用尝试的记录。

    ``attempts`` 是唯一事实来源。
    ``final_provider``、降级状态、降级原因均从 ``attempts`` 派生。

    构造时自动校验 status 枚举和 duration_ms 非负。
    """

    provider: str  # tushare / a_stock_mootdx / a_stock_sina / ...
    method: str | None  # Provider 方法名（如 income_vip）
    status: str  # success / normal_empty / failed_network / failed_auth / ...
    attempted_at: str  # ISO 8601 尝试时间
    duration_ms: int  # 耗时（毫秒），必须 >= 0
    error_summary: str | None = None  # 失败时的错误摘要（自动截断）
    record_count: int | None = None  # 返回记录数（成功时）

    def __post_init__(self):
        if not self.provider:
            raise ValueError("provider must not be empty")
        if self.status not in _VALID_ATTEMPT_STATUSES:
            raise ValueError(
                f"Invalid attempt status {self.status!r}; "
                f"must be one of {sorted(_VALID_ATTEMPT_STATUSES)}"
            )
        if self.duration_ms < 0:
            raise ValueError(f"duration_ms must be >= 0, got {self.duration_ms}")
        # Sanitize error_summary
        object.__setattr__(self, "error_summary", _sanitize_error_summary(self.error_summary))

    def is_terminal(self) -> bool:
        """该尝试是否为终端结果（不触发降级）。"""
        return self.status in (ATTEMPT_SUCCESS, ATTEMPT_NORMAL_EMPTY)

    def is_failed(self) -> bool:
        """该尝试是否失败（触发降级或跳过）。"""
        return self.status not in (ATTEMPT_SUCCESS, ATTEMPT_NORMAL_EMPTY, ATTEMPT_SKIPPED)


@dataclass
class EvidenceEnvelope:
    """一次工具调用的最终证据，含完整尝试链。"""

    capability_id: str  # 关联的 Capability
    evidence_category: str  # 证据类别（技术/基本面/资金/筹码/两融/估值/业绩/...）
    evidence_domain: str  # 领域（行情与技术/公司经营/新闻与政策/资金与杠杆/...）
    original_tool: str  # 原始工具名

    # 完整尝试链（按优先级顺序）
    attempts: list[ProviderAttempt] = field(default_factory=list)

    # 时间
    analysis_date: str | None = None  # 分析日期
    observation_date: str | None = None  # 数据观察日期/交易日
    report_period_end: str | None = None  # 报告期结束日（财务数据）
    announcement_date: str | None = None  # 公告日期
    data_cutoff_date: str | None = None  # 数据截止日期

    # 点时效
    pit_satisfied: bool = False
    pit_exclusion_reason: str | None = None

    # 质量
    completeness: str = COMPLETENESS_FULL  # full / partial / minimal
    limitations: list[str] = field(default_factory=list)

    # 报告关联
    referenced_by: list[str] = field(default_factory=list)

    # ── 派生属性（不持久化，从 attempts 计算）────────────────────────────

    @property
    def final_provider(self) -> str | None:
        """最终提供数据的 Provider；全部失败时为 None。"""
        # Fallback chains may deliberately continue after a normal-empty or
        # partial source (for example Phase 4 Pro statements seeking a usable
        # Free equivalent).  The final provider is therefore the last terminal
        # attempt, while the complete earlier facts remain in ``attempts``.
        for attempt in reversed(self.attempts):
            if attempt.is_terminal():
                return attempt.provider
        return None

    @property
    def final_status(self) -> str:
        """从 attempts 派生的最终状态。"""
        if not self.attempts:
            return FINAL_UNAVAILABLE
        for attempt in reversed(self.attempts):
            if attempt.is_terminal():
                return FINAL_SUCCESS if attempt.status == ATTEMPT_SUCCESS else FINAL_NORMAL_EMPTY
        return FINAL_RECOVERABLE_FAILURE

    @property
    def is_degraded(self) -> bool:
        """是否存在非正常完成（non-terminal）的 attempt。"""
        return any(a.is_failed() for a in self.attempts)

    @property
    def primary_degradation_reason(self) -> str | None:
        """第一个失败 attempt 的 error_summary。"""
        for attempt in self.attempts:
            if attempt.is_failed():
                return attempt.error_summary
        return None

    @property
    def is_normal_empty(self) -> bool:
        """正常空结果（数据合理不存在，非故障）。"""
        return self.final_status == FINAL_NORMAL_EMPTY

    @property
    def degradation_chain(self) -> list[str]:
        """前端可消费的降级链描述。"""
        return [
            f"{a.provider}({a.status})" + (
                f": {a.error_summary}" if a.error_summary else ""
            )
            for a in self.attempts
        ]

    # ── 序列化 ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """序列化为可 JSON 序列化的 dict（供 ledger 持久化）。

        注意：派生字段（final_provider 等）包含在输出中仅供人类可读；
        Ledger 消费方必须从 attempts 自行派生，不得信任序列化值。
        """
        return {
            "capability_id": self.capability_id,
            "evidence_category": self.evidence_category,
            "evidence_domain": self.evidence_domain,
            "original_tool": self.original_tool,
            "attempts": [
                {
                    "provider": a.provider,
                    "method": a.method,
                    "status": a.status,
                    "attempted_at": a.attempted_at,
                    "duration_ms": a.duration_ms,
                    "error_summary": a.error_summary,
                    "record_count": a.record_count,
                }
                for a in self.attempts
            ],
            "final_provider": self.final_provider,
            "final_status": self.final_status,
            "is_degraded": self.is_degraded,
            "is_normal_empty": self.is_normal_empty,
            "degradation_chain": self.degradation_chain,
            "primary_degradation_reason": self.primary_degradation_reason,
            "analysis_date": self.analysis_date,
            "observation_date": self.observation_date,
            "report_period_end": self.report_period_end,
            "announcement_date": self.announcement_date,
            "data_cutoff_date": self.data_cutoff_date,
            "pit_satisfied": self.pit_satisfied,
            "pit_exclusion_reason": self.pit_exclusion_reason,
            "completeness": self.completeness,
            "limitations": self.limitations,
            "referenced_by": self.referenced_by,
        }


# ── Evidence 校验 ──────────────────────────────────────────────────────────

def validate_envelope(
    raw: dict,
    *,
    expected_tool: str | None = None,
) -> EvidenceEnvelope | None:
    """将不可信 dict 校验并重建为 EvidenceEnvelope。

    用于 Ledger 从工具正文提取 EVIDENCE 块后的安全边界：
      - 校验 attempts 结构
      - 校验 capability_id、original_tool 存在且非空
      - 如提供 expected_tool，校验 original_tool 匹配且 capability_id 与
        正式 tool→capability 映射一致（拒绝伪造 capability_id）
      - 从 attempts 派生 final_provider/final_status/is_degraded（不信任序列化值）
      - 校验失败返回 None

    返回的 EvidenceEnvelope 中派生属性均从 attempts 计算，
    不受序列化 dict 中可能被伪造的同名字段影响。
    """
    if not isinstance(raw, dict):
        return None
    if not raw.get("capability_id") or not raw.get("original_tool"):
        return None
    if expected_tool is not None and raw["original_tool"] != expected_tool:
        return None

    # G02-07: 校验 capability_id 与正式映射一致，拒绝伪造
    if expected_tool is not None:
        mapped_cap_id, _, _ = capability_for_tool(expected_tool)
        if mapped_cap_id != "unknown_capability" and raw["capability_id"] != mapped_cap_id:
            return None

    raw_attempts = raw.get("attempts")
    if not isinstance(raw_attempts, list) or len(raw_attempts) == 0:
        return None

    attempts: list[ProviderAttempt] = []
    for a in raw_attempts:
        if not isinstance(a, dict):
            return None
        try:
            attempt = ProviderAttempt(
                provider=str(a.get("provider", "")),
                method=a.get("method"),
                status=str(a.get("status", "")),
                attempted_at=str(a.get("attempted_at", "")),
                duration_ms=int(a.get("duration_ms", 0)),
                error_summary=a.get("error_summary"),
                record_count=a.get("record_count"),
            )
        except (ValueError, TypeError):
            return None
        attempts.append(attempt)

    completeness = raw.get("completeness", COMPLETENESS_FULL)
    if completeness not in _VALID_COMPLETENESS:
        return None

    limitations = raw.get("limitations", [])
    if not isinstance(limitations, list):
        return None
    referenced_by = raw.get("referenced_by", [])
    if not isinstance(referenced_by, list):
        return None

    return EvidenceEnvelope(
        capability_id=str(raw["capability_id"]),
        evidence_category=str(raw.get("evidence_category", "通用")),
        evidence_domain=str(raw.get("evidence_domain", "通用")),
        original_tool=str(raw["original_tool"]),
        attempts=attempts,
        analysis_date=raw.get("analysis_date"),
        observation_date=raw.get("observation_date"),
        report_period_end=raw.get("report_period_end"),
        announcement_date=raw.get("announcement_date"),
        data_cutoff_date=raw.get("data_cutoff_date"),
        pit_satisfied=bool(raw.get("pit_satisfied", False)),
        pit_exclusion_reason=raw.get("pit_exclusion_reason"),
        completeness=completeness,
        limitations=limitations,
        referenced_by=referenced_by,
    )


# ── 辅助：从工具结果文本中提取/构建 Evidence ─────────────────────────────

def make_attempt(
    provider: str,
    status: str,
    *,
    method: str | None = None,
    duration_ms: int = 0,
    error_summary: str | None = None,
    record_count: int | None = None,
    attempted_at: str | None = None,
) -> ProviderAttempt:
    """便捷构造 ProviderAttempt。"""
    return ProviderAttempt(
        provider=provider,
        method=method,
        status=status,
        attempted_at=attempted_at or datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        error_summary=error_summary,
        record_count=record_count,
    )


def make_envelope(
    capability_id: str,
    evidence_category: str,
    original_tool: str,
    attempts: list[ProviderAttempt],
    *,
    evidence_domain: str = "通用",
    completeness: str = COMPLETENESS_FULL,
    limitations: list[str] | None = None,
    **kwargs,
) -> EvidenceEnvelope:
    """便捷构造 EvidenceEnvelope。"""
    return EvidenceEnvelope(
        capability_id=capability_id,
        evidence_category=evidence_category,
        evidence_domain=evidence_domain,
        original_tool=original_tool,
        attempts=attempts,
        completeness=completeness,
        limitations=limitations or [],
        **kwargs,
    )


# ── Capability 解析（可注入） ────────────────────────────────────────────────
# 独立使用时没有宿主能力注册表，返回 unknown_capability；宿主（如 TradingAgents）
# 在启动时通过 set_capability_resolver 安装自己的映射，以恢复
# validate_envelope 的 G02-07 tool→capability 防伪校验。
_capability_resolver = None


def set_capability_resolver(resolver) -> None:
    """Install a host resolver: ``tool_name -> (capability_id, category, domain)``."""
    global _capability_resolver
    _capability_resolver = resolver


def capability_for_tool(tool_name: str) -> tuple[str, str, str]:
    """返回 (capability_id, evidence_category, evidence_domain)。

    无宿主 resolver 时返回 ``unknown_capability``（validate_envelope 的
    G02-07 防伪分支随之放行——独立包没有可对照的正式映射）。
    """
    if _capability_resolver is None:
        return ("unknown_capability", "通用", "通用")
    return _capability_resolver(tool_name)
