# Third-Party Intake Policy

## 1. Policy

This is a new project, not a fork. External repositories may inform design or provide narrowly scoped, independently testable code only after provenance, license, security, maintenance, and semantic review. Large-project wholesale import is prohibited.

The safest default is clean-room reimplementation of a documented idea using our contracts and tests. “Public on GitHub” is not permission to copy.

## 2. Intake classes

| Class | Meaning | Core inclusion |
|---|---|---|
| `inspiration` | learn concepts/behavior; no source copied or close translation | allowed with source note |
| `clean_room_rewrite` | implement from public specification/observed semantics with independent wording/code | allowed after provenance/tests |
| `adaptation` | modify a small identifiable code fragment | permissive license only, obligations retained |
| `cherry_pick` | preserve a specific upstream commit/patch | exceptional; permissive license and focused review required |
| `runtime_dependency` | call an external package/API | explicit dependency/capability/security review and version pin |
| `validation_only` | use outside core to compare behavior/results | allowed under its license/data terms; output provenance required |
| `prohibited` | GPL/AGPL/non-commercial/unknown/private/paid code copied into core | not allowed |

“Rewrite” must not be used to disguise line-by-line translation from a prohibited source.

## 3. Mandatory gate

Before copying, adapting, cherry-picking, or adding a runtime dependency:

1. identify repository URL, exact commit/tag, source path, authors/copyright notices;
2. read repository and file-level licenses/NOTICE at that commit and check dependency/data/content terms;
3. classify use and commercial-distribution implications; escalate ambiguity for legal review;
4. justify why local reimplementation or standard library is insufficient;
5. bound the exact files/lines or package API; reject large imports;
6. review security, transitive dependencies, network/file side effects, maintenance, and API stability;
7. design canonical adapter/interface and failure isolation;
8. add unit/contract/golden tests before acceptance;
9. record the intake in `third_party/SOURCES.yaml` in the same change;
10. retain required license/copyright/NOTICE text and obtain reviewer approval.

No provenance record means no merge.

## 4. `third_party/SOURCES.yaml` minimum record

Each entry needs a stable ID and:

```yaml
id: unique-source-id
source:
  repo: https://...
  commit: full-sha
  path: exact/upstream/path
  author: ...
  license_spdx: MIT
  license_files: [LICENSE]
  reviewed_at: YYYY-MM-DD
integration:
  destination: exact/local/path
  method: inspiration | clean_room_rewrite | adaptation | cherry_pick | runtime_dependency | validation_only
  modified: true
  scope: concise bounded description
  tests_added: [tests/...]
  notices_retained: [third_party/notices/...]
reason: why this source/use is necessary
review:
  provenance_reviewer: ...
  license_status: approved | rejected | legal_review_required
  security_status: approved | rejected
```

For inspiration without copied code, record the source when it materially shaped a design/algorithm. For dependencies, also record the resolved version/hash and transitive-license report location.

## 5. License rules

- MIT, Apache-2.0, and BSD-family code may be evaluated, but attribution, LICENSE/NOTICE, patent clauses, and file-specific exceptions still apply.
- GPL/AGPL code is not copied or adapted into the core under this project policy.
- Non-commercial, source-available, custom-restricted, paid/private, or unclear code is not copied into the core.
- Validation use does not grant a right to redistribute code or data.
- Repository-level license does not automatically cover third-party assets, notebooks, data, model weights, vendored files, posts, or screenshots.
- License status must be rechecked at the exact commit even when a current default branch appears permissive.

This policy is an engineering gate, not legal advice.

## 6. Data and content rights

Market-data access, caching, derived works, and redistribution rights are reviewed separately from software licenses. A technically callable endpoint is not automatically licensed for product redistribution.

For forum posts, papers, and research reports, retain URL/author/publication/knowledge-available dates, our summary/claim, and only necessary short quotations. Do not bulk republish full content. Paid strategy code requires valid purchase and explicit source-use permission; strategy ideas may be researched without copying implementation.

## 7. Recommended reference map

These are study targets, not blanket approval to copy:

| Project | Recommended use | Intake posture |
|---|---|---|
| `joycoding2000/chstockdata` | first data-provider package, capabilities, provenance; adapter contract and ETF qualification | runtime dependency only, exact pin; license/package/API review required before M0 implementation |
| HKUDS/Vibe-Trading | causality/lookahead tests, evidence/gate concepts | inspiration first; current default-branch license appears MIT, reverify commit before any small adaptation |
| simonlin1212/Vibe-Research | data-failure distinctions and research/evidence workflow | inspiration; reverify exact commit/file even though README currently declares MIT |
| ricequant/RQAlpha | A-share/ETF event, fee, suspension, and parity scenarios | validation only; current license imposes non-commercial/commercial authorization conditions, no core copying |
| mementum/backtrader | broker/order/position/commission abstractions and edge-case questions | architecture inspiration only; GPLv3 code must not enter core |
| vnpy/vnpy | later manual/paper/execution lifecycle and reconciliation concepts | defer to later milestone; current MIT still requires exact-commit review |
| microsoft/qlib | later large-scale research/dataset/experiment ideas | defer; too heavy for M0; current MIT does not justify runtime adoption |
| letianzj/QuantResearch, quanttrader | TAA examples and event-driven test scenarios | hypothesis/architecture inspiration; verify each exact license before any code use |
| KHunter, InStock, ABu, quant-trading | later Stock Satellite hypothesis seeds and cookbook comparisons | ideas only by default; no trust in reported returns; license and provenance review required |

Licenses noted above were checked only as an initial design-stage signal on 2026-09-14. The merge gate always uses the selected full SHA and its complete license tree.

## 8. Review evidence

An intake PR/change must show:

- source record diff;
- exact upstream diff or independent design reference;
- license/NOTICE retention;
- tests proving local semantics and failure handling;
- security/dependency scan where applicable;
- explanation of why the scope is small and separable;
- confirmation that no unrelated upstream history/assets/data entered the repository.

Upstream upgrades repeat the gate. A compatible version number does not waive contract, ETF qualification, golden, or Production smoke tests.

## 9. Immediate M0 posture

No external code is introduced during this architecture round. M0 implementation should first build hand-calculated golden cases and canonical interfaces. `chstockdata` is the only planned runtime dependency specific to the domain; all other projects are references or validation tools unless a later, separately approved intake record says otherwise.

