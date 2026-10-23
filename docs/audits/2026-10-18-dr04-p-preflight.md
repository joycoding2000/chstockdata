# DR04-P preflight — INSUFFICIENT_EVIDENCE

Historical preflight judgment: the Owner subsequently supplied the sibling-repository contract and evidence paths. They were readable and verified; the missing-contract blocker is resolved. See [implementation evidence](2026-10-18-dr04-p-implementation.md) for the later state. The original preflight findings below are retained as judged at that step.

## State and scope

- Phase/step: DR04-P, prerequisite contract recovery; implementation has not started.
- HEAD: `0dc85e3e43588c5781771486a3c6f80c4be7714f`.
- Published v0.4.2 tag commit: `17af23fe8183f740150dc01dd877473afe3911b7`.
- HEAD differs from that tag only in `README.md` and `docs/releases/v0.4.2.md`; no shipped code difference. The current release record identifies the published commit above and states that subsequent product phases are not authorized by that release.
- Initial working tree: no tracked modifications or staged changes; existing untracked audit documents and evidence were preserved.
- This step adds only this report and `evidence/2026-10-18-dr04-p-preflight/regression.txt`. No implementation, exports, dependencies, version changes, commits, pushes, releases or M-stage work.

## Required evidence missing

`UNRESOLVED_RISK`: the referenced reviewed document, 《DR04 最小日度资金消费者合同与验收方案》, and its individual frozen P01–P12 definitions were not found in the repository searches. The current request lists acceptance categories but does not provide the twelve individual groups. Creating a substitute numbering would not establish acceptance against the reviewed contract.

Searches performed after CodeGraph exploration:

```powershell
rg -n --glob '*.md' 'DR04|P01|最小日度|资金消费者' docs README.md
rg -l 'ssl_qsfx_zjlrqs|r0_net' docs tests src
```

The P01 matches were unrelated archived SIOS/M1 plans. The source-field matches were the current `a_stock.py` and archived copies of that file, rather than saved DR04 response fixtures. No market data was requested. The Owner has been asked for the reviewed contract path or full frozen definitions and, if held outside the repository, the saved response paths.

## Existing API observations

- Public `get_fund_flow` remains a text API, exported by `chstockdata.__init__`.
- Existing private `_sina_daily_fund_flow` requests page 1 with at most 20 records and converts `r0_net` through `float`. It is not sufficient evidence of the new lossless historical public contract.
- No implementation decision or DR04-P acceptance is inferred from these observations.

## Verification

Initial command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_astock_tdx_fallback.py tests/test_fetch_result_core.py tests/test_release_version.py -q
```

Result: 31 passed, 3 setup errors caused by inability to create the sandbox default pytest temporary directory. These were environment errors before test assertions, not a diagnosed product defect.

One rerun with a previously absent workspace-local temporary directory:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_astock_tdx_fallback.py tests/test_fetch_result_core.py tests/test_release_version.py -q --basetemp=D:\Dev\Projects\chstockdata\.pytest_cache\dr04-p-preflight-20261018 --tb=short
```

Result: **34 passed in 3.12s**, exit code 0. Output: [regression.txt](evidence/2026-10-18-dr04-p-preflight/regression.txt).

P01–P12: **NOT_RUN**. No PASS_CANDIDATE or Owner Acceptance claim.

## Handoff

- Gate verdict: **INSUFFICIENT_EVIDENCE** at contract recovery.
- Blocking item: missing reviewed contract/P01–P12 definitions; no expanded scope proposed.
- Working tree: Owner's existing untracked materials retained; this preflight report and regression log added, no tracked code modifications.
- Recommended next action: Owner provides the frozen contract path/content; resume DR04-P implementation and exact offline acceptance mapping against it. Stop at Owner Review afterward. DR04-M is not authorized.
