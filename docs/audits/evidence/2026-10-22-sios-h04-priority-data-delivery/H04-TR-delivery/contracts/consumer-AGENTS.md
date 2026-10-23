
## Phase and Release Governance

### 1. Frozen scope

The Owner-approved version design, implementation plan,
non-goals, and acceptance criteria are authoritative.

Do not silently expand scope, redefine success, or introduce
new architecture solely because it may be useful in the future.

Propose out-of-scope improvements separately as Change Requests.

### 2. Gate discipline

Implementation completion is not equivalent to Gate acceptance.

A phase may advance only when all mandatory acceptance criteria
have supporting evidence and the Owner has authorized advancement.

If a Gate fails, investigate or fix the blocker.
If evidence is insufficient, report INSUFFICIENT_EVIDENCE.

Do not automatically implement the next phase.

### 3. Evidence over agent claims

Verify conclusions against actual code, tests, logs,
repository state, and frozen contracts.

An implementation agent's PASS claim is not independent evidence.

Classify findings as:
- CONFIRMED_DEFECT
- UNRESOLVED_RISK
- SPECULATIVE_CONCERN
- FUTURE_ENHANCEMENT

Do not silently change acceptance criteria or introduce
additional engineering to resolve speculative concerns.

### 4. Context recovery

If task history or context appears incomplete, reconstruct
the current state from the repository, authoritative documents,
diffs, tests, and audit evidence before continuing.

Do not infer phase completion from a conversation summary alone.

## ChatGPT Handoff

At the end of each milestone or implementation step,
include a concise handoff summary containing:

- Current phase and step
- Commit SHA and working tree status
- Gate verdict and supporting evidence
- Unresolved blockers and scope changes
- Recommended next action

Do not claim that the next phase is authorized.

The summary must be sufficient for an independent
ChatGPT planning/review session to reconstruct the state.
## Research Assumptions and Investment Evidence

### 5. Authority and inference boundary

For M1+ product direction, read the v0.9 flight-test-driven product
architecture; retain Owner-approved frozen M0 semantics and current M1
contracts. A newer discussion or implementation does not silently amend
them. Record any actual conflict for Owner review.

Distinguish:
- NON_NEGOTIABLE_CORRECTNESS: PIT/no-lookahead, T-close versus T+1,
  real costs/tradability, explicit target/cash, immutable failed runs,
  exposure/holdout protection and research/production separation.
- FIRST_FLIGHT_CHOICE: the initial four ETFs, first candidate families,
  cadence, parameter grids, benchmark, capital and gate thresholds.
- KNOWN_LIMITATION: a documented data, instrument-identity or execution
  qualification gap.
- OPEN_RESEARCH_QUESTION: economic exposure, mechanism, attribution,
  portfolio risk or account suitability not yet established by evidence.

Passing M0 qualification proves a defined data/execution capability,
not investment merit. Passing M1 acceptance proves its research pipeline,
not that a strategy or asset pool is profitable or product-ready.

### 6. Research before implementation

Start with the investment question and a falsifiable mechanism, not with
a convenient existing strategy module or the historical winner. Separate
asset-class economics from the actual tradable fund and its eligibility.
Do not treat the M1 first four ETFs as the permanent or optimal universe.

For each new hypothesis, explicitly review its time horizon, PIT inputs,
universe selection, executable vehicle, realistic costs, adverse case,
predeclared comparator/benchmark, attribution and fastest falsification.
Source claims, backtest curves and AI interpretations are discovery leads,
not independent project validation. Count research questions, independent
economic mechanisms, formal candidates and Survivors separately.

The approved portfolio objectives (long-term 10–15% annual return and
desired maximum drawdown <=10%) are not Basic thresholds, a tuning target,
or a promise. Candidate-local Basic gates, costs, capital and benchmark
must be declared before testing. Never retrofit them after results.

Macro/geopolitical news may inform source-dated scenarios and risk
hypotheses; it must not generate discretionary production signals or
be retroactively used to claim a clean historical OOS result.

### 7. Scope, evidence and promotion

An expanded ETF/fund subtype, data dependency, execution model or
platform capability needs a stated current-version necessity, narrow
qualification and separate Owner Change Request before implementation.
Keep prior frozen intents, experiment roots, rejected outcomes and
exposure history intact. A new candidate ID, root or universe name
does not reset project-level OOS disclosure.

Do not convert Basic PASS, an implementation report, a Cheap Screen
PASS or a research-control comparison into a Survivor or next-Phase
authorization. When no Survivor exists, continue narrowly scoped M1
hypothesis research; do not pre-build M2 ActiveStrategyPack/Paper.

For source of current status and the assumption/universe decision,
read docs/m1-r2/R2-product-assumption-and-universe-decision.md together
with the latest immutable evidence. The decision record is research
governance, not a new executable gate or retroactive contract change.

### 8. Decision and handoff discipline

Before material next steps, report:
- CURRENT_VERDICT: CONTINUE / INVESTIGATE / FIX_ONLY / CHANGE_REQUEST
- original goal and confirmed facts
- missing evidence and confirmed versus speculative problems
- scope deviation and minimum necessary next action
- whether the next Phase/Release Gate is authorized

If missing evidence can materially change the pending decision,
prefer the smallest read-only verification task.

Every investigation must name the decision it supports,
the minimum sufficient evidence, and its stopping condition.

Do not recursively investigate unrelated uncertainties.
When available evidence cannot resolve the decision, report
the remaining limitation and return the options to the Owner.

If a blocker is confirmed, prefer the smallest authorized fix. Do not
create work just to increase review coverage. Recover known phase,
commit, tests and Gate evidence from repository state before asking the
Owner to repeat them.


### 9. Critical Path and Investigation Exit

The v0.9 goal is to shorten the path from investment idea
to credible validation, Paper, and a usable ActionPlan.

Before proposing work, identify:
- The nearest unachieved, verifiable objective.
- The specific blocker or uncertainty preventing it.
- The smallest action that could change the decision.
- What will be deferred or explicitly left unresolved.

A task is complete when its approved objective and required
evidence are satisfied, not when every related uncertainty
has been eliminated.

Keep validation depth proportional to the stage:
- Stage 0: plausible mechanism, feasibility, fastest falsification.
- Basic: qualified inputs, frozen rules, reliable backtest.
- OOS: independent data, precommitted rules, exposure control.
- Paper/Production: forward evidence and operational safety.

Do not require future-stage infrastructure as a prerequisite
for earlier research unless a frozen contract explicitly
requires it.

When a correctness defect is confirmed:
- Identify affected data, artifacts, decisions and consumers.
- Stop only work that depends on the affected evidence.
- Preserve historical artifacts and disclose invalid evidence.
- Restore the minimum required contract and requalify evidence.
- Do not silently rewrite past Gate decisions.
- Keep independent, unaffected research eligible to proceed.

If repeated investigations produce no decision-changing
evidence, stop the loop and present the remaining options
to the Owner. No new engineering is authorized by default.

### 10. Evidence-to-Learning Loop

After each meaningful experiment, repair, investigation
or Gate review, produce a brief learning summary:

- ORIGINAL_QUESTION: What were we trying to establish?
- OBSERVED_RESULT: What does actual evidence establish?
- LESSON: Which assumption was supported or disproved?
- REMAINING_UNKNOWN: What materially remains unresolved?
- NEXT_DECISION: Continue, fix, investigate, change scope,
  close the hypothesis, or defer?
- NEXT_MINIMUM_ACTION: One bounded, justified next action.

Distinguish:
- Engineering acceptance from investment validity.
- Invalid evidence from a failed economic hypothesis.
- Rejected historical experiments from new hypotheses.
- Completion of a task from authorization of the next phase.

A failed hypothesis is useful evidence, not a reason to
weaken frozen gates or automatically expand the platform.

When no Survivor exists, return to the M1 research funnel,
subject to required data and correctness qualification.
Do not enter M2 or construct M2 capabilities prematurely.

Avoid recurring review loops that only produce more
documents without changing an experiment or decision.

Reuse the existing handoff and audit records.
Do not create a new governance subsystem or document
for each lesson. Amend AGENTS.md only when a lesson
demonstrates a reusable process weakness.
