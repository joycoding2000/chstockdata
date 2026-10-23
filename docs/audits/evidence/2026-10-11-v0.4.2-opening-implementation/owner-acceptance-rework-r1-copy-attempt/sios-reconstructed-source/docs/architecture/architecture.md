# Systematic Investing OS — M0 Architecture

## 1. Status and authority

This document translates `docs/personal-systematic-investing-os-v0.2-final-architecture-decision-rev2.md` into an M0 architecture. The source document is authoritative. Items recorded in `OPEN_QUESTIONS.md` remain undecided and must not be silently fixed in implementation.

M0 is a foundation milestone: domain contracts, provider-neutral data ingestion, deterministic daily-bar backtesting, portfolio/risk semantics, reproducibility, and correctness tests. It does not implement an investment strategy, Web UI, AI agent, notification adapter, paper trading workflow, or automated execution.

## 2. Product objective

The product is a personal, medium/low-frequency systematic investing decision system for China exchange-listed ETFs and A-shares. Its durable output is a versioned, auditable `TargetPortfolio`; BUY/SELL/HOLD/CASH/NO ACTION are derived execution views, not the decision model. Backtests and paper accounts start with CNY 100,000 and must model lot constraints, costs, residual cash, and competition for capital.

The intended production path is:

```text
canonical market data
  -> quality gate
  -> approved deterministic strategy outputs
  -> portfolio construction
  -> risk transformation
  -> locked target portfolio
  -> execution confirmation/action plan
  -> manual execution
  -> fill reconciliation
```

## 3. Architectural style

Use a modular monolith with ports and adapters. This is the smallest design that keeps correctness-sensitive domain code independent of vendors and later permits Research and Production to run as separately controlled processes/artifacts. M0 must not add microservices, a message broker, Kubernetes, Redis, an agent swarm, or an orchestration platform.

Dependencies point inward:

```text
Adapters / CLI / persistence
             |
             v
Application use cases and run orchestration
             |
             v
Domain contracts and deterministic policies
```

The domain must not import `chstockdata`, database clients, HTTP clients, schedulers, LLM libraries, or notification SDKs.

## 4. Module boundaries

| Module | Owns | May depend on | Must not own |
|---|---|---|---|
| `domain` | instruments, money, bars, portfolio sleeves, target portfolios, orders/fills, positions, portfolios, rule profiles, identifiers | standard library only, narrowly justified validation types | vendor frames, persistence, scheduling |
| `instrument_master` | approved instrument classification, ETF subtype, effective-dated lot/settlement/price-limit and market fee/tax profiles, authoritative-source provenance | `domain`, approved reference-data input | OHLCV acquisition, broker-account commission settings |
| `data_contracts` | provider port, canonical datasets, snapshot manifest, provider evidence, quality reports | `domain` | strategy logic, fallback vendor scraping |
| `data_adapters` | `ChStockDataProvider`, raw-to-canonical translation | `domain`, `data_contracts`, pinned `chstockdata` API | leaked vendor return types, portfolio rules |
| `calendar` | exchange sessions and next-trade-date resolution | `domain`, canonical reference data | wall-clock scheduling |
| `backtest` | event ordering, order simulation, settlement, valuation, ledger | domain contracts and deterministic policies | strategy parameters, live-provider calls |
| `portfolio` | theoretical target validation, capital competition, discrete executable targets | `domain` | signal generation, vendor access |
| `risk` | deterministic constraints and target transformation/veto decisions | `domain`, portfolio snapshots | LLM text, notification state |
| `metrics` | performance metrics from immutable ledgers/NAV series | canonical backtest outputs | execution mutation |
| `production` | future EOD/pre-open state machines, locking, idempotency, reconciliation boundaries | application ports and domain | Alpha experimentation, mutable strategy definitions |
| `research` | future experiments, hypothesis/evidence lifecycle | approved shared kernel APIs | write access to Production records or configuration |
| `provenance` | third-party intake records and validation | repository metadata | implicit/unrecorded code intake |

The plan may map these logical boundaries to fewer physical packages initially. A package is warranted only when it enforces a dependency or semantic boundary.

## 5. Research and Production separation

“Separate planes” means more than different folders:

- Production loads only an immutable, explicitly approved strategy/configuration bundle identified by version and digest.
- Research may call the same public backtest/domain libraries, but cannot write Production decisions, approvals, run records, or secrets.
- Production never imports research notebooks, experimental modules, or LLM components.
- Promotion is an explicit owner-controlled operation that creates a new immutable approved bundle and audit record; no runtime self-modification is allowed. M0 does not add multi-person approval, external signing services, or PKI.
- Production inputs and outputs are append-only or superseded by explicit records; history is never edited in place.
- Separate credentials, storage namespaces, entry points, and configuration schemas are required before Production deployment.

M0 designs and tests import boundaries and artifact contracts; later milestones implement promotion and operational access control. The exact workflow is milestone-gated, but its minimum controls are fixed: explicit owner approval, immutable content digest, audit record, and separate Research/Production authority without enterprise signing infrastructure.

## 6. Data boundary

`DataProviderPort` exposes market-data capabilities, not a mirror of `chstockdata`. The first adapter calls the pinned `chstockdata` Python package directly and converts results into canonical, validated contracts. Quant, portfolio, and risk modules only consume these contracts.

`chstockdata` is not the Instrument Master authority. It supplies market data, calendar/suspension/corporate-action facts and candidate reference information. Production classification and trading-rule truth comes from this system's versioned Instrument Master, backed by exchange/regulator/tax sources and effective-date provenance. Account-specific broker commissions belong to a separate account fee configuration.

Data flows through two distinct gates:

1. **Contract conversion:** types, identifiers, units, timezone/date meaning, adjustment mode, and provenance are explicit.
2. **Quality decision:** freshness, completeness, duplicates, calendar alignment, OHLC consistency, pre-close consistency, tradability/reference coherence, and snapshot reproducibility produce a persisted report.

A snapshot is an immutable manifest that binds canonical files/partitions to checksums, provider/version, request scope, adjustment policy, information cutoff, retrieval time, and quality report. Every historical fact separates `information_available_at` from `retrieved_at` and declares an `availability_basis` of `OBSERVED`, `EXCHANGE_RULE`, `INFERRED`, or `UNKNOWN`. PIT/no-lookahead logic and `knowledge_cutoff` use information availability, never download time. A provider response or mutable cache directory is not a snapshot.

ETF capability is qualified separately by subtype. M0 may claim only domestic broad-based equity ETFs, gold ETFs, and bond ETFs that pass the capability-scoped gate. Cross-border/QDII, money-market, and all other unverified subtypes are unsupported and fail closed. Golden edge events use manually frozen public exchange rules/data; independent parity may use JoinQuant or another legally usable source in validation-only research, with source, access date, semantics, and tolerance recorded.

## 7. Decision and execution boundary

The domain distinguishes:

- `Signal` or strategy intent: evidence-bearing input to portfolio construction.
- `TheoreticalTargetPortfolio`: ideal normalized weights before market/microstructure constraints.
- `ExecutableTargetPortfolio`: whole-lot, cash- and tradability-aware desired holdings sized from finalized T-close prices.
- `ActionPlan`: the delta between reconciled current holdings and the executable target.
- `Order` and `Fill`: simulated or manually reported execution facts.

This distinction prevents BUY/SELL labels from becoming strategy state and preserves why a target differs from what can actually be executed.

`SleeveId` is a strong domain concept with initial values `CORE` and `SATELLITE`; it is never inferred from strategy names or instrument types. Aggregation retains strategy, sleeve, and contribution so sleeve risk budgets can be enforced directly.

Sizing and filling are also separate. M0 sizes `planned_quantity` from finalized T close using only T-known information. Pre-open may publish that planned quantity, target, and notional but cannot observe the future open. In Backtest, T+1 activation prices all simultaneous candidates with next-session open plus side-aware slippage, tick rounding, and applicable fees, then applies the approved global sleeve/priority allocation to derive `submitted_quantity`. In future Production, any gap-driven reduction belongs to manual execution or a separately approved execution-time confirmation. Neither path may change the locked theoretical target.

## 8. Runtime boundaries

The future EOD run uses a complete T-session snapshot and resolves the next exchange session T+1 before producing and locking one decision revision. The pre-open run loads that locked decision and may reconcile positions, refresh execution-only reference/tradability/corporate-action facts, apply deterministic risk/kill-switch checks, and emit the T-close-sized planned quantity/target/notional. It neither observes `NEXT_SESSION_OPEN` nor recomputes base daily Alpha.

Any future overnight information is a separately versioned overlay with explicit inputs and authority. It cannot be smuggled into pre-open logic as an ad hoc Alpha recalculation.

Notifications are downstream delivery receipts. Failure to send through `NotificationPort -> ServerChanAdapter` never changes or erases the locked decision. No notification implementation belongs in M0.

## 9. Persistence ownership

M0 designs the following durable record classes without prematurely choosing multiple databases:

- immutable canonical snapshot manifests and data files;
- append-only experiment/run manifests;
- backtest ledger, NAV, orders, fills, rejects, and metrics;
- instrument/rule profile versions with effective dates;
- future locked decisions, action-plan revisions, approval records, and reconciliation facts;
- audit events and redacted operational logs.

Use local files/Parquet for immutable analytical data and a single embedded transactional store only where atomic state transitions are needed. PostgreSQL, an API service, and a Web application are deferred until their operational need exists.

## 10. Failure posture

- Missing, stale, inconsistent, or unqualified critical decision data blocks creation of a new target. A critical pre-open failure blocks all risk-increasing orders.
- A risk-reducing order may continue only when instrument identity, current holding, sellable quantity, current tradability, and a conservative price/cost basis are independently reliable; otherwise produce no order and an urgent manual-review alert.
- Every rejected or skipped action has a reason code and retains the prior target/current holdings context.
- Re-runs are idempotent by stable business keys and content digests.
- Unknown instrument rules fail closed for new exposure; no generic “all ETF equals stock” fallback exists.
- A quantity-changing corporate action effective between T-close decision and T+1 activation invalidates the affected pending execution with `CORPORATE_ACTION_REPLAN_REQUIRED`; it does not mutate the locked theoretical target.
- Monetary and quantity arithmetic uses explicit rounding policies; binary floating point must not decide cash sufficiency or fees. Buy allocation honors approved sleeve/risk budgets, then descending absolute target-weight deficit with canonical InstrumentId as tie-breaker.
- A run never reports success when required output persistence fails.

## 11. M0 non-goals

- No ETF or stock Alpha strategy.
- No parameter search, optimization, OOS workflow, or evidence promotion engine.
- No live/paper daily scheduler or ServerChan call.
- No browser UI, FastAPI service, or user-account system.
- No broker/order-routing integration.
- No bulk import of external repositories.
- No attempt to model every exchange rule; implement only versioned rule profiles proven by M0 fixtures and qualification evidence.

## 12. M0 acceptance boundary

M0 is complete only when the canonical contracts and event semantics are documented and encoded, the first provider adapter passes contract tests, the three approved ETF subtype scopes pass qualification, deterministic backtests reproduce from a snapshot manifest, and golden tests demonstrate T-close sizing versus next-open filling, global gap affordability, pending-execution invalidation for quantity-changing corporate actions, PIT availability, Instrument Master authority, sleeves, cash/lot/cost rules, stale valuation, tradability rejections, mark-to-market termination, and metric correctness. Until OQ-22 is decided, every M0 `RunManifest` declares benchmark `NONE` or `SYNTHETIC_TEST_BENCHMARK`. Any parity difference against an external reference must be recorded and explained rather than normalized away.
