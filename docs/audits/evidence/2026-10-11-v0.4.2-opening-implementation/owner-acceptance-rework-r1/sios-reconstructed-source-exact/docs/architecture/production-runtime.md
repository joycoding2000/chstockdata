# Production Runtime Design

## 1. Scope and milestone placement

This document defines the eventual deterministic runtime boundary so M0 contracts do not make Production unsafe. M0 does not implement the scheduler, signal product, ServerChan delivery, paper account, or manual reconciliation workflow; those belong to later milestones.

Production is a conservative application over approved artifacts. It cannot execute AI-generated code, alter strategy/risk parameters, route broker orders, or rely on notifications as truth.

## 2. Required controls

- one local deployment may remain a modular monolith, but Production uses a distinct entry point, config, credentials, and storage namespace from Research;
- only immutable owner-approved bundles identified by version/digest and audit record are loadable; no enterprise multi-approver/PKI service is required;
- runs use a stable business key and acquire a single-run lease/lock;
- all state transitions and outputs are durable before notification;
- retries are idempotent and produce attempts, not duplicate decisions;
- clock and calendar semantics are Asia/Shanghai plus canonical exchange sessions;
- secrets are injected via environment/local secret store and redacted from logs;
- LLM services have no write path to target, approval, rule, or runtime configuration stores.

## 3. EOD Decision Run

### Preconditions

- intended session T is an open trading session;
- finalized T data is available after a provider-independent completeness/freshness cutoff evaluated from `information_available_at`, not `retrieved_at`;
- required canonical snapshot and Data Quality/ETF qualification gates pass;
- approved Instrument Master profiles—not provider candidates—cover every instrument and effective trade date;
- all strategy, portfolio, risk, and rule versions are approved and their digests match the bundle;
- no conflicting locked decision exists for the next session unless running an authorized supersession workflow.

### State machine

```text
PLANNED -> ACQUIRING_DATA -> DATA_VALIDATED -> COMPUTED
        -> PERSISTED -> LOCKED -> NOTIFICATION_PENDING -> COMPLETED
```

Any state can transition to `FAILED` with a durable reason; a retry resumes/recomputes according to idempotency policy and never mutates a locked payload.

### Processing

1. Resolve T and `decision_for_trade_date = next_session(T)` from the frozen calendar.
2. Freeze/identify canonical inputs and persist the quality report.
3. Run approved deterministic base daily strategies.
4. Construct the theoretical target with explicit strategy/sleeve contributions; apply approved portfolio/sleeve/risk rules and size it on finalized T-close reference prices.
5. Persist evidence links, sleeve aggregates, and a candidate target.
6. Atomically persist and lock a `DecisionSnapshot` with content digest.
7. Commit run manifest/audit event.
8. Enqueue/persist an EOD summary delivery intent downstream.

The locked payload includes decision/revision IDs, trade date, generated-at and information-based knowledge cutoff, snapshot and quality IDs, strategy/portfolio/risk/Instrument Master versions, market regime, explicit CORE/SATELLITE/CASH aggregates, theoretical targets, T-close sizing prices, risk state, evidence IDs, and digest.

## 4. Pre-open Execution Confirmation Run

### Preconditions

- today matches a locked decision’s `decision_for_trade_date`;
- current holdings/cash have a reconciled source and cutoff;
- current calendar/reference/tradability/corporate-action and data-health checks are available;
- no unresolved earlier manual fills make the account state ambiguous.

### State machine

```text
PLANNED -> TARGET_LOADED -> POSITION_RECONCILED -> CHECKED
        -> EXECUTABLE_TARGET_DERIVED -> ACTION_PLAN_LOCKED
        -> NOTIFICATION_PENDING -> COMPLETED
```

### Permitted computation

1. Load and verify the EOD target digest.
2. Reconcile actual holdings, cash, sellable lots, and unresolved fills.
3. Verify trading date, current reference/corporate-action facts, provider health, and strategy/risk kill switches.
4. Apply only approved pre-open execution/risk constraints.
5. Convert the unchanged theoretical target into T-close-sized planned whole quantities and notionals using finalized T-close sizing prices. Pre-open does not observe `NEXT_SESSION_OPEN`.
6. Derive planned BUY/SELL/HOLD/CASH/NO ACTION deltas and declare the intended later execution model without claiming a realized price.
7. Persist/lock the Action Plan before delivery.

It must not load a new daily Alpha dataset or run a base strategy. Any future `OvernightRiskOverlay` is independently versioned, tested, approved, and recorded; it can only exercise its declared authority.

If a quantity-changing corporate action is effective between the T-close decision and T+1 activation/execution, invalidate the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED` and require a controlled replan/manual review. Do not mutate the locked theoretical target.

Any actual gap-driven quantity reduction happens only during later manual execution or a separately approved execution-time confirmation after an executable price exists. It uses the actual price/cost basis, preserves non-negative cash, and is captured by actual fill quantity/reconciliation; Pre-open does not perform this reduction.

## 5. Decision locking and amendments

Locked records are immutable. An authorized correction creates a new revision that references the superseded decision, reason, actor, and prior/new digests. The system must decide whether a correction is allowed after pre-open begins or notification is delivered; this authority/cutoff is an open question.

Duplicate EOD/pre-open triggers with identical business key and input digest return the existing result. Changed inputs cannot overwrite the result; they require a valid supersession path.

## 6. Position source and reconciliation

Because there is no automated broker integration, actual holdings are imported or entered by the user through a later controlled interface. A prior reconciled portfolio state carries forward automatically when there are no unresolved fills, external/manual trades, deposits/withdrawals, or detected mismatches. Human reconciliation is required only after one of those events. Each snapshot records source, as-of time, input digest, and reconciliation status; ambiguous or unbalanced state blocks the normal action plan.

Manual fills append to orders/action plans and generate a new actual portfolio. The notification does not count as execution, and unconfirmed planned quantities never become holdings.

## 7. Notification boundary

Later milestones define:

```text
persisted delivery intent -> NotificationPort -> ServerChanAdapter -> delivery receipt
```

The stable dedupe key includes trade date, run type, decision/action-plan ID, revision, and message type. Retries retain the same key. Credentials never enter message payloads, audit records, or ordinary logs. Failure/retry exhaustion changes delivery status only, not the decision/action plan.

Normal notifications are Pre-open Action Plan and EOD Decision Summary; exceptional alerts are separate typed events. Message format and severity policy remain a later-milestone decision.

## 8. Failure matrix

| Failure | Durable outcome | Trading posture |
|---|---|---|
| provider unavailable/schema drift | failed data evidence and run | no newly generated target |
| stale/incomplete critical decision data | failed gate | block new target; pre-open blocks risk increase |
| ETF qualification absent | failed capability gate | exclude/block affected ETF scope |
| approved-bundle digest mismatch | security/config failure | no Production calculation |
| existing locked conflicting decision | conflict/audit event | do not overwrite |
| stale/ambiguous positions | failed reconciliation | no normal Action Plan |
| risk kill switch | scoped gate result/action plan | policy-defined exposure reduction/block |
| notification failure | retryable delivery record | decision remains queryable and valid |
| persistence failure | run failed | never claim success/send normal plan |

A risk-reducing action under a failure proceeds only with independently reliable identity, holdings, sellability, tradability, and conservative price/cost facts; otherwise no order is emitted and urgent manual review is required.

## 9. Observability and audit

Every run records correlation/run ID, state transitions, input/output IDs and digests, data/strategy/portfolio/risk/notification status, counts, timings, typed errors, and runtime/dependency versions. Logs avoid full sensitive payloads and credentials. Metrics and logs assist operation; persisted domain/run records remain ground truth.

Required operational alerts are missed expected run, prolonged run, failed data/risk gate, bundle mismatch, lock conflict, notification retry exhaustion, and storage integrity failure. Alerting implementation is deferred.

## 10. Recovery and replay

- A run can be replayed from its immutable manifest in a non-Production verification context.
- Replay output is compared by normalized digests and cannot replace Production history.
- Backups must include transactional records, manifests, approval artifacts, and encryption/secret recovery instructions; market data may be reconstructed only when exact snapshot identity remains verifiable.
- Clock skew, process crash between persistence and delivery, and duplicate scheduler invocation are explicit integration tests before M3/M4 go live.

## 11. Production readiness gate

Before真钱 operation, require successful paper-forward observation, restore drill, idempotency/crash tests, provider outage exercise, stale-data exercise, target-lock audit, position reconciliation checks, notification failure drill, secret/log redaction check, and human runbook approval. M0 correctness alone is necessary but not sufficient for Production.
