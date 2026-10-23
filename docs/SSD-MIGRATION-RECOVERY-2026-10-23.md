# 系统盘更换前恢复说明（2026-10-23）

范围：仅盘点与 GitHub 备份；未开发、未运行测试、未修改研究结论、Gate 或 Owner Acceptance。GitHub 备份分支仅用于恢复，不代表合并授权。Owner 负责将整个 `C:\Users\Administrator\.codex` 备份到 F 盘，本任务未复制或整理该目录。

## 项目事实与当前裁决

- 项目：`chstockdata`；远端：[`joycoding2000/chstockdata`](https://github.com/joycoding2000/chstockdata)。当前 `main` 工作区基线为 `a2072d0c722d7f7935309a15cef945bc8ecbef08`，`origin/main` 为 `5584f5fcacccef9a9531a7a32b8463ea6771d312`。本地唯一 `main` 提交是 H01 有界 Owner Acceptance 归档；它通过单独备份分支保存，未推送到 `main`。
- 项目版本为 `0.4.3`；GitHub `v0.4.3` tag 指向 `30cc7c50e3971fe79bfd903a412b2b76a0338caa`。历史 v0.4.2 的发布阻断记录保持为历史记录。
- H01：Owner 已批准 `PASS_BOUNDED`，供数关闭；仅覆盖冻结输入，不授权策略实验。见 [H01 Owner Acceptance 收口](audits/2026-10-23-sios-h01-owner-acceptance-closeout.md)。
- DR04-P：Owner Acceptance `PASS`；该结论不覆盖 DR04-M、全市场供应、历史 PIT 或策略资格。DR04-M 仍 `NOT_AUTHORIZED`。见 [DR04-P Acceptance](audits/2026-10-18-dr04-p-owner-acceptance.md)。
- H04：总回报输入为 `PASS_FOR_CONSUMER_REVIEW`，归因为 `PARTIAL_WITH_NAMED_GAPS`；SIOS 独立消费者 Acceptance 待完成，P2 仍 `QUEUED`。见 [H04 交付裁决](audits/2026-10-22-sios-h04-priority-data-delivery.md)。
- W5-H-F2：固定窗口为 `FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS`；Mishi S07 历史 Gate `NOT_PASSED`。见 [W5-H-F2 资格裁决](audits/2026-10-22-w5h-f2-final-evidence-qualification.md)。

### 已批准决策

- 2026-10-23 DR03 Owner Addendum 批准并同步了 `published-version as-of` 消费语义方向：交易日只使用该日之前最新公开的官方版本，发布日从下一交易日起适用；旧 STOP 记录原样保留。该决定没有授权来源重新资格、代码实现或下一阶段。见 [DR03 Owner Decision Addendum](audits/2026-10-23-dr03-owner-decision-addendum.md)。

### 待 Owner Review / 未授权事项

- DR03 当前及历史 Gate 均 `NOT_PASSED`，来源资格为 `PARTIAL`，CAPCO 重新资格尚未开始；分类版本、覆盖缺口和内容版本等具名风险仍待解决。旧 S1 close-out 保留为历史记录，并须与较新的 Owner Addendum 一起阅读。
- H04 归因仍有具名缺口，消费者 Acceptance 待处理；S07 免费来源屏查的后续决策待 Owner Review。DR04-M、任何新研究/数据供给/策略实验及产品实现均未获本轮授权。

## Git 与备份位置

核验到的远端是 `git@github.com:joycoding2000/chstockdata.git`。本次将使用以下独立备份分支；它们不更新或合并到 `main`：

| 分支 | 内容 |
|---|---|
| `codex/ssd-migration-main-2026-10-23` | 本地 `main` 基线 `a2072d0c722d7f7935309a15cef945bc8ecbef08`、当前未跟踪的文档/研究证据，以及本恢复说明；另包含经文本检查的 11 个小型资格/发布辅助脚本。 |
| `codex/ssd-migration-rh3b5-worktree-2026-10-23` | 保留 detached HEAD `42bd44ef4d695aa3e88cfab4ebc3417660d0437a` 的工作区快照；快照提交为 `aa53736009b2a8a1f69db1b900ca305c80fdd8a0`，包括 366 个新增文件和 205 个内容/字节变化路径。此分支仅存档，勿据此推断 Gate 或合并授权。 |
| `codex/ssd-migration-orphan-141c0ad-2026-10-23` | 将此前未被分支引用的旧审计提交 `141c0ad592be74b1a1a7b57252cccf6918d5ae4f` 固定为可恢复引用。 |

本地 `codex/rh3-b5-candidate-freeze-preflight` 为 `42bd44ef4d695aa3e88cfab4ebc3417660d0437a`，相对远端 `88f9b6677ade4a6ed280c865e6cf1edaf625a49f` 领先 2 个提交；两者均包含于 worktree 备份分支的祖先链。其余已登记分支头与对应 GitHub 引用一致。`git stash list` 为空。

备份前主工作区有 15,204 个未跟踪文档/证据文件，合计 531,310,822 字节；工作树原件留在 `docs/`，并会在备份分支保存。最大的单文件约 20.98 MB，未超过 GitHub 单文件 100 MB 限制。备份分支 SHA 以 GitHub 引用及本轮最终交接核验为准；本说明避免写入包含自身的提交 SHA。

## GitHub 与 Codex 备份之外的本机资产

以下路径被 `.gitignore` 排除，不会随 GitHub 分支恢复；它们也不属于 Owner 备份的 `.codex` 目录。若需从 GitHub 和 `.codex` 独立重建这些原件，请 Owner 另行备份到 F 盘。若 D 盘在系统盘更换期间保持不变，这些目录仍留在 D 盘，但不构成第二份备份。

| 本机路径 | 盘点 | 恢复依赖 / 用途 |
|---|---:|---|
| `D:\Dev\Projects\chstockdata\.rh3a2-vipdoc` | 12,427 个文件；952,292,279 字节（约 908 MiB） | 本地通达信 VIPDOC 日线历史数据，供本地日线读取和交易日历使用。恢复至原位置，或设置 `CHSTOCKDATA_VIPDOC_HISTORY_DIR` / `vipdoc_history_dir`。可尝试用项目刷新工具重新取得官方包，但远端可用性与字节版本不保证。 |
| `D:\Dev\Projects\chstockdata\build\v042-qualification` | 29,635 个文件；1,066,666,123 字节 | v0.4.2 资格验证快照，含冻结的 SIOS/TA 输入及验证产物；精确复现依赖这些本地副本与当时环境。 |
| `D:\Dev\Projects\chstockdata\build\v042-unified` | 9,098 个文件；384,743,611 字节 | v0.4.2 综合验证及消费者快照/运行产物。 |
| `D:\Dev\Projects\chstockdata\build\w0-v043` | 9,633 个文件；233,846,296 字节 | W0/v0.4.3 本地资格与发布验证快照。 |
| `D:\Dev\Projects\chstockdata\dist` | 2,262 个文件；44,043,087 字节 | 历史 wheel/sdist 和安装验证副本；源码可重建一般包，无法保证逐字节重建未发布候选产物。 |

上述三份 `build` 快照、`dist` 与 VIPDOC 合计约 2.50 GiB。根目录 `.venv`、构建缓存、pytest/ruff 缓存及 `.codegraph` 索引属于可重建环境/索引，不是唯一研究原件。忽略的构建目录内未发现额外独立 Git 仓库。

本次把 `build/w0-v043-*.py` 的 9 个发布辅助脚本和 `build/v042-qualification/provider.py`、`test_chstockdata_etf_gate.py` 两个小型验证脚本纳入主备份分支；其余构建快照仍需额外本机备份才能保留原貌。

## 新系统最小恢复步骤

1. 从 GitHub 克隆仓库并 `git fetch origin`；先查看 `codex/ssd-migration-main-2026-10-23`，不要自动合并到 `main`。按需从 `codex/ssd-migration-rh3b5-worktree-2026-10-23` 另建 worktree 审阅历史候选状态。
2. Owner 将 `.codex` 备份恢复到原位置。已登记的 4 个 Codex worktree 位于该目录，但每个 `.git` 链接都指向 `D:\Dev\Projects\chstockdata\.git\worktrees\...`；worktree 依赖主仓库的 `.git` 元数据，单独复制 `.codex\worktrees` 不会成为独立仓库。若主仓库元数据不可用，应从本说明列出的 GitHub 分支重新创建 worktree。
3. 安装 Python `>=3.10`（项目近期资格记录使用 Python 3.12），按 `pyproject.toml` 安装项目依赖；按需要单独安装 `mootdx` 或 `mcp` extra，README 记录这两个 extra 不能在同一干净环境解析。
4. 如需本地无网络 VIPDOC 能力，恢复 `.rh3a2-vipdoc` 并设置对应目录配置；缺少该数据时部分路径可走线上 fallback，但本地完整历史/离线交易日历不再可用。
5. 恢复后先由 Owner Review 本文件及对应审计记录，再决定后续工作。备份分支不授权合并、研究、供数、实验或实现。

最后核验状态、各备份引用 SHA、远端 `ls-remote` 结果及额外本机备份清单见本轮交接；新会话应优先依据这些仓库文件、远端分支和 SHA 重建现场。
