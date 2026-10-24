# 2026-10-24 chstockdata 历史资产审查交付

先读 [保留与清理方案](ASSET_RETENTION_AND_CLEANUP_PLAN.md)，再按 [成果索引](RESEARCH_ASSET_INDEX.md) 和 [决策队列](RESEARCH_DECISION_QUEUE.md) 定位原件。本轮清理授权为 NO，实际删除/回收为 0。研究整理分支以 `5584f5fcacccef9a9531a7a32b8463ea6771d312` 为父基线，不整合本地 H01 或 DR03 归档到 main。

## 证据分工

| 文件 | 用途 |
|---|---|
| `inventory.json` | 五个登记工作区的目录/研究批次统计、文件身份去重、Git 状态计数；不含 `.git` 和本交付目录 |
| `retention-groups.csv` | 不重叠分类统计，按工作区、任务/目录、保留类别分组 |
| `classification.json` | 精确候选目录、选定文件、worktree、分支、保留锚和依赖；没有批准就不能执行 |
| `backup-coverage.json` | 原有未跟踪文件的路径/尺寸覆盖及 53 个当前字节样本；不是全量当前字节认证 |
| `collection-verification.json` | 具名重复集合的有序 SHA-256、旧工作区与备份的逐 blob 对照、历史环境版本来源 |
| `git-refs.json`、`remote-refs.txt` | 本地引用图、独有提交计数、对象库统计及只读 GitHub 引用查询 |
| `process-usage.json` | 指定历史环境/工作区的进程路径匹配快照；不保存命令行，不证明没有所有形式的运行依赖 |
| `baseline-summary.json` | main、原 untracked 路径集合摘要和初始普查范围；避免另存几万行路径 |
| `review-verification.json` | 清单求和、原工作区保护、证据链接、分支可达性、已发布工件身份等核验结果 |
| `DELIVERY_MANIFEST.json` | 本轮提交载荷的 SHA-256/字节；不自覆盖，提交/远端 SHA 由最终交接另列 |

五个辅助脚本仅用于本轮盘点，不是新平台、正式开发 Gate 或来源资格测试：`collect_inventory.py` 做元数据普查和 Git 查询；`analyze_assets.py` 做备份树覆盖和代表性 blob 比对；`verify_collections.py` 只比较具名重复集合；`classify_inventory.py` 做非重叠分组；`verify_report.py` 校验报告和状态保护。

若未来需要复算，先运行 collect（Python 3.12+；本轮使用已有 Python 3.14.5），再 analyze、verify_collections、classify、verify_report。`collect --resume` 仅供同一普查失败后的显式恢复，不能用于已变化的现场。远端清单需另以只读 `git ls-remote --heads --tags origin` 保存；这些脚本不自动拉来源数据、安装依赖、创建环境、提交、推送或清理。外部 worktree 的 Git 查询需要当前用户可读取其目录；safe.directory 仅对该子进程的精确路径设置，不改全局 Git 配置。

普查产生的 `main-files.json`、`baseline-status.json`、`opening-subgroups.json` 和两个 inspect 辅助脚本是本任务中间文件；目录级证据、初始路径集合摘要和最终核验导出并校验后，按精确白名单移除这些本任务中间件，不触及任何任务前已存在的文件。没有新建 venv、工具缓存、临时 worktree 或 visualization 环境。

## 限制与执行记录

- 普通沙箱无法在外部 worktree 中执行部分 Git 操作；核验改用经批准的受控只读访问。SSH 命名对象创建受限的一次远端查询失败，之后受控查询成功；没有将失败当成空分支列表。
- 核验脚本初版去掉了 porcelain 首行前导空格，造成状态计数误报；改为保留前导空格后重新核验。原工作区未改动。
- 元数据遍历和局部重复哈希不是逐文件语义审批。未重跑发布、资格、策略或生产功能测试；历史 PASS 的适用范围以原报告为准。
- 物理分配空间、外部冷盘完成收据、未登记 checkout 和外部原始库不在已量化总量中。候选执行前必须重新核对状态、成员、恢复引用和任务使用情况。

当前阶段：有界盘点/清理决策整理完成，供 Owner Review。提交 SHA、推送后远端 SHA 与 main/工作区状态由最终交接给出；本交付不声称下一阶段已获授权。
