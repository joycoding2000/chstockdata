# chstockdata 资产保留与清理决策方案

日期：2026-10-24，Asia/Shanghai。**CLEANUP_AUTHORIZED = NO**。这是一份供 Owner 批准的候选清单，本轮没有删除原始成果、Git 引用、worktree、stash，也没有执行 gc/prune/reset/clean、改写 main 或推进研究。其他两个项目不在范围内。

## 结论及统计口径

优先减少重复冻结副本、历史安装环境和已结束任务的实体工作区。长期保留正式结论、现行代码/合同/测试、关键反证、原始来源版本及交付身份。完成任务的运行底稿按既有引用冷归档；没有足够恢复证据的消费者改动和候选工件先 REVIEW。

| 类别 | 文件数 | 逻辑字节 | 主要内容 |
|---|---:|---:|---|
| KEEP | 18,345 | 1,948,202,703 | VIPDOC、现行代码/测试/合同、关键 PIT/价格反证、H01/H04/DR03 等关键证据、DR03 待审实体工作区 |
| ARCHIVE | 21,153 | 746,800,260 | 已结束资格/发行底稿、早期调查、保留的一份冻结 var、历史源归档及辅助脚本 |
| DELETE_CANDIDATE | 41,537 | 1,304,980,207 | 五个历史安装环境、两份大 var 副本、三组重复源、明确的生成缓存/字节码、两个旧 worktree |
| REVIEW | 5,766 | 137,963,812 | 可能独有的消费者资格源改动/工件、非标准 pytest 内容、不能保证精确再生的候选包、W0 实体工作区 |
| **合计** | **86,801** | **4,137,946,982** | 五个登记工作区；不含 `.git`、本轮报告、外部资料库和未登记冻结 checkout |

主工作区单独为 **82,705 文件 / 3,675,010,832 B**：KEEP 16,358 / 1,526,786,659 B；ARCHIVE 21,153 / 746,800,260 B；DELETE_CANDIDATE 40,348 / 1,278,562,463 B；REVIEW 4,846 / 122,861,450 B。另两个候选 worktree 合计 1,189 文件 / 26,417,744 B，已包含在上表候选总量中，不能再加一次；W0 的 920 文件 / 15,102,362 B 计入 REVIEW。

容量依据每个工作区一次文件元数据遍历；本任务中因沙箱阻断而中止的外部状态检查，已通过限定只读权限完成。主工作区沿用第一次成功遍历的元数据，不反复全盘哈希；只对有明确收益的重复集合和旧工作区作局部内容比较。符号链接/junction 不递归，Git 管理元数据单列。按文件身份去重后的五工作区总量仍为 **4,137,946,982 B**，本次计数未发现跨工作区硬链接重复占用。

**可回收空间估计为约 1.30 GB（1.22 GiB）的文件逻辑字节；当前实际回收为 0。** 未测卷分配簇、压缩/稀疏和删除时打开句柄，因此不是释放物理空间的保证值。Git 对象库另由 `git count-objects -v` 报告 loose 391,833 KiB、pack 2,386 KiB，合计约 403,680,256 B，未含全部管理文件；不计入候选回收量，不预测删分支释放对象空间。

## 可复核证据与精确目标

- `inventory.json`、`retention-groups.csv`：不重叠的工作区/任务/目录分组，含数量、字节及分类；不是几万条 Markdown 文件审批。
- `classification.json`：**执行清单的唯一机器入口**。`primary_cleanup_targets` 中 DIRECTORY 是精确目录；SELECTED_FILES 仅允许 `selected_paths` 中的文件，不能删除其整个父目录。`worktree_cleanup_candidates` 和 `branch_cleanup_candidates` 单列目标、SHA、保留引用及条件。
- `backup-coverage.json`：原有 **15,205** 个未跟踪文件 / **531,318,625 B** 全部在 `db972cbb…` 有同路径、同尺寸；**53/53** 代表性 Git blob 与当前字节一致。较恢复说明的 15,204 多出恢复说明本身 7,803 B。没有声称全部 15,205 个文件当前字节都重新核对过；对未抽样原件，冷移除前必须做本组身份核对。
- `collection-verification.json`：两份各 6,007 文件 / 314,603,626 B 的 var 副本，以及三组消费者源，已按相对路径、尺寸、内容 SHA-256 的有序集合摘要比较；全部相等。旧 detached worktree 的 **758/758** 当前文件逐字节等于 `aa537360…` 的 Git blob，缺失和不匹配均为 0。
- `git-refs.json`、`remote-refs.txt`：历史引用、相对 main/备份的可达性和独立 GitHub SHA 查询。tag object 与 peeled commit 区分保存。
- `process-usage.json`：五个历史环境、四个外部工作区均未发现命令行/可执行路径匹配的运行进程。它是一次快照，不保证没有仅以 cwd/文件句柄依赖的进程；执行前仍须确认任务已结束。

## KEEP / ARCHIVE / REVIEW 的处理边界

**KEEP**：`.rh3a2-vipdoc` 12,427 文件 / 952,292,279 B 必须保留；官方包再次可下载不意味着旧版本可精确重建。当前 `.venv` 和 `.codegraph` 仍供开发使用；不为了本次清理关闭当前环境或索引。`src`、`tests/fixtures`、已批准合同、Owner 记录及重要反证均保留；正式测试资产不按历史缓存处理。

**ARCHIVE**：优先保留现有 GitHub 引用，不新复制一份“全部历史”。历史 Markdown 决策/索引留在日常可发现路径，具体底稿通过本索引和固定 commit 链接访问；本轮不把未跟踪历史证据合并 main。`build/v042-qualification/sios/var` 是两份重复 var 的恢复锚，314,603,626 B，GitHub 备份不包含它，必须继续保留。若未来要把这唯一锚迁到冷盘，先有一次可核对的归档和恢复收据，再移除原位置；不同时无限维护多份。**ARCHIVE 类本轮没有获准直接删除，也不并入 1.30 GB 回收估计。**

**REVIEW**：`build/v042-qualification` 中剩余 sios/ta 改动、`build/v042-unified` 的非重复部分及 `dist` 的非环境部分，可能含资格补丁、冻结消费者输入、旧 wheel/sdist；缺少“精确版本可还原”的证明。最小补证是已存源归档/commit 与工作副本的差异和具名工件身份，不是重跑所有历史测试。`.pytest_cache` 的非标准内容含调查脚本、Git/落地收据和测试副本，不能整目录删除。外部 F 盘完成情况和未登记 frozen checkout 也仍 REVIEW，未混入已量化总量。

## 分批清理建议

下列仅为下一轮候选顺序。任何一批都需要 Owner 对其精确集合明确批准；临执行若出现新差异、新文件、活跃依赖或恢复引用改变，停止该目标，不自动扩大清理。

### 批次 A：无独立研究语义的运行环境与生成物

精确目录为 `build/v042-qualification/core`、`build/v042-qualification/gate`、`build/w0-v043/dev`、`dist/recovery-v0.4.1/wheel-env`、`dist/recovery-v0.4.1/sdist-env`；它们的 `pyvenv.cfg`、来源解释器及 dist-info 版本目录已导出。是独立安装环境，不包含本轮新建环境，也不包括当前根 `.venv`。另含根 `.ruff_cache`、标准 pytest 缓存的具名文件，以及有对应当前 `.py` 源的具名字节码。

恢复保障：源码/候选 wheel、历史环境来源、包版本、安装与资格日志继续保留；重新安装不保证历史解析器依赖或环境字节完全一致。清理前确认没有手工修改或新增原始证据、没有嵌套 Git 仓库、没有活跃使用；若需要保留旧环境进行逐字节取证，则将该环境退回 REVIEW。严禁将规则推广为清理 `.pytest_cache` 或 `build` 整体。

### 批次 B：已证实等价的重复集合

1. `build/v042-qualification/sios-baseline/var` 和 `build/v042-unified/sios/var`：保留 `build/v042-qualification/sios/var`，两候选共 **12,014 文件 / 629,207,252 B**。实际路径、数量、集合摘要均已比较；不能改为清理消费者原始仓库的 var。
2. `docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation/owner-acceptance-rework-r1-copy-attempt/` 下的 **sios-frozen-source、sios-reconstructed-source、sios-reconstructed-source-exact**：共 **750 文件 / 8,399,304 B**，保留同批 `owner-acceptance-rework-r1/` 下对应集合。失败过程、README、不同 gate 输出及旧尝试身份仍归档，不能删 copy-attempt 整体。

恢复保障：保持 `collection-verification.json` 的保留锚及集合摘要。若以后需要按历史命令重现旧 cwd，可从保留集合或现有 SSD Git blob 恢复具名路径；不改写原失败记录。执行时检查成员集合和摘要仍一致，不能仅凭同尺寸或文件名判断。

### 批次 C：已结束任务的工作区

| 精确工作区 | 现状及保留锚 | 数量 / B | 建议 |
|---|---|---:|---|
| `C:/Users/Administrator/.codex/worktrees/v042-controlled-release/chstockdata` | HEAD `a34c8c25…`；tracked/untracked 干净，10 个 ignored 为 Ruff/egg-info；远端 `codex/v042-release-audit` 保留独有正式发行收口提交 | 431 / 6,356,663 | DELETE_CANDIDATE，仅移除实体工作区，保留归档分支 |
| `C:/Users/Administrator/.codex/worktrees/v042-opening-cr/chstockdata` | detached `42bd44ef…`，180 个 Git 可见修改、366 个 untracked；**不能当干净 worktree**。全部 758 个当前文件已与备份 `aa537360…` 精确匹配 | 758 / 20,061,081 | DELETE_CANDIDATE，须先确认候选审阅已关闭，且无新差异；保留带差异的备份引用 |
| `C:/Users/Administrator/.codex/worktrees/w0-v043-release/chstockdata` | HEAD `69957a58…`，已在 main/SSD main 祖先链；tracked/untracked 干净但有 232 个 ignored。两本地工件与正式发布包不同，现有 local-artifacts.json 只能证明身份，未证明另有相同字节副本 | 920 / 15,102,362 | REVIEW，未计入候选；先判断本地候选工件独立价值或精确恢复保障，不动 v0.4.3 tag |
| `C:/Users/Administrator/.codex/worktrees/dr03-capco-archive/chstockdata` | HEAD `88e0ac6f…`，1,987 文件 / 421,416,044 B，无未提交/忽略文件；独有归档提交、Owner Review/main 整合待定 | 不计候选 | KEEP_ACTIVE，等待 Owner 对当前研究及审阅便利性决定 |

这不是 `.codex` 会话/全目录清理授权。Owner 明确批准后才采用受控 worktree 生命周期操作，先保全当前引用/差异；若工具要求强制丢弃新变化，停止并重新报告，不自动 force。

### 批次 D：冗余历史分支引用

共 **8 个不同历史分支名**：对应 **7 个本地引用、8 个真实远端分支引用**；不是 15 个不同研究成果。逐引用 SHA 和保留链见 `classification.json` 与 `git-refs.json`，每个候选的所有提交均已在 main/保留 SSD main 的祖先链中。

| 分支名 | 本地 / GitHub | 先决条件 |
|---|---|---|
| `codex/cached-ohlcv-compatibility-hardening` | 有 / 有 | 保留 main、SSD main 引用及本索引映射 |
| `codex/phase41-routing-observation` | 有 / 有 | 同上 |
| `codex/rh3-b4-live-qualification-evidence` | 有 / 有 | 历史报告从固定 commit/归档引用继续可达 |
| `codex/rh3-b5-candidate-freeze-preflight` | 有 / 有 | 本地 `42bd44ef…` 与远端 `88f9b667…` 不相等，但两者均可达；含未提交差异的 `aa537360…` 另保留，不可只保留旧远端头 |
| `codex/trading-calendar-structured` | 有 / 有 | VIPDOC 原件继续保留；删引用不授权删除日历原件 |
| `codex/v042-controlled-release` | 有 / 有 | `v0.4.2` tag → 同一 release commit；保留 tag 和独立 `v042-release-audit` |
| `docs/v0.4.2-post-release-closeout` | 有 / 有 | 版本级收口文档在保留祖先链 |
| `docs/v0.4.0-retrospective-design-audit` | 无 / 有 | 追溯设计/缺口解释在保留祖先链；不能把追溯文件改写成事前冻结 |

**必须继续保留的 6 个既有不同分支名**：main、三个 SSD 备份、`codex/dr03-capco-archive-2026-10-23`、`codex/v042-release-audit`。加本轮研究整理分支后为 7 个保留分支名。三个 SSD 快照各自相对其他保留头仍有独有提交，当前没有可靠的减量替代方案；不为少三个名称另造标签层或合并 main。

另有 **1 个 REVIEW 分支名 `codex/w0-v043-release`（仅本地）**：提交本身已在 main，但登记工作区的本地工件仍 REVIEW；本轮不通过拆离/强制删除分支绕过其资产问题。

引用前置检查包括：SHA 未变、所有重要提交仍可达、无待保全工作区变化、恢复文档中的旧名字可由本索引映射到固定 SHA/保留锚、没有需要原候选分支作对比的未结束 Review。删除引用不意味着 Git 对象释放，本批收益是减少分支选择/搜索干扰；不安排 gc/prune。

### 批次 E：冷归档和 REVIEW 补证，按需要开展

约 746.8 MB 的 ARCHIVE 是保留等级，不是额外立即回收额。先使用现有 GitHub 快照和上述索引；仅对当前不再依赖的整个任务集合，在身份核对后再决定移除热副本。对约 138.0 MB 的 REVIEW，优先核对可能独有的源补丁、W0 本地候选工件及非标准 pytest 调查收据；不能为了扩大收益做全盘去重、重跑历史资格或复制全部资料。外部原件的责任和位置见 [成果索引](RESEARCH_ASSET_INDEX.md) 的外部材料表。

## 效益与保留风险

批准并完成 A–D，理论可减少 **41,537 个本地文件、约 1.30 GB 文件逻辑容量、8 个历史分支名和 2 个工作区**，不把 ARCHIVE 或 GitHub 分支容量重复算入。约 12,014 个重复研究文件和 750 个重复源文件的移除尤其能降低误检和 Codex 上下文噪声；三份文档提供统一入口，保留关键反证的可发现性。

不可替代风险主要是 VIPDOC 的历史字节、官方财务/分类来源版本、H01/H04 原包与收据、唯一冻结 var、独有消费者资格差异和未取得冷备份回执的外部材料。本轮没有证明这些可以删除，也没有把失败实验等同于无价值。未量化范围包括未登记 checkout、外部缓存/客户端资料、F 盘副本和 Git 全部管理空间，不能声称已覆盖全机资产。

## 交接与验收边界

当前阶段/步骤：有界研究资产整理的清单、索引、决策队列和引用证据。**这不是正式开发 Gate**；清单可提交 Owner Review，但实际研究 Gate/Acceptance 全部保持原状态。核验包括分组求和、精确重复集合、旧工作区快照、Git 可达性/远端 SHA、文档证据链接及 main/原工作区保护；不执行功能回归或历史资格实验。

审查分支从已核对的 `origin/main=5584f5fc…` 产生，只提交本轮审查文件；使用独立 Git index/commit，保留当前 checkout、真实 index 和本地 H01 领先状态。提交 SHA 和推送后的独立远端 SHA 见最终交接，不能将报告自身 SHA 写成循环自证。未解决的范围已列 REVIEW 和决策队列；未发生范围扩张。下一步是 Owner 审阅并明确批准一批精确候选，**不声称下一轮清理、研究或 main 整合已授权**。
