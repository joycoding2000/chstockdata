
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