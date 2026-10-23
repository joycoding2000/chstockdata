# SIOS H01 Owner Acceptance 与受控归档收口

日期：2026-10-23（Asia/Shanghai）。阶段/步骤：H01 数据供给 / Owner Acceptance 收口与本地归档。
授权依据：Owner 在本次 `H01_CONTROLLED_ARCHIVE` 任务中正式批准 `PASS_BOUNDED`、关闭 H01 数据供给，仅允许两仓库各一个最小归档提交。该决定是在独立接收完成后作出的新决策；旧报告、失败结果及历史 Gate 保持原件。

```ini
CURRENT_DECISION = CONTINUE
OWNER_ACCEPTANCE = PASS_BOUNDED
H01_OWNER_ACCEPTANCE = PASS_BOUNDED
H01_DATA_SUPPLY = CLOSED
H01_DATA_SUPPLY_CLOSEOUT = CLOSED
H01_RESEARCH_DATA_GATE = CLOSED
H01_STRATEGY_EXPERIMENT_AUTHORIZED = NO
H01_EXPERIMENT_AUTHORIZED = NO
H04_DATA_SUPPLY_NEXT = YES
H04_DATA_READY = NO
P2 = QUEUED
P2_DATA_READY = NO
NEXT_PHASE_RELEASE_AUTHORIZED = NO
TASK = H01_CONTROLLED_ARCHIVE
GIT_COMMIT = AUTHORIZED_ARCHIVE_ONLY
GIT_PUSH = NO
GITHUB_RELEASE = NO
```

## 固定交付身份与验收范围

- chstockdata 原基线：`5584f5fcacccef9a9531a7a32b8463ea6771d312`；SIOS 原基线：`a46500441ff29c9c7807fdfef155c22cedb72b88`。归档前实际 HEAD 均一致，tracked diff 和暂存区为空。
- [最终修复报告](2026-10-22-sios-h01-final-repair.md)及其原 `Owner Acceptance Pending` 结论保留原字节。本记录承接其后发生的正式接受，不回写历史。
- [最终完整 ZIP](evidence/2026-10-22-sios-h01-final-repair/H01-delivery-repaired.zip)：8,971,030 字节，SHA256=`82dd2f7258a410285f6be27be7232d35fa31b1fba32ad0bd0a31f7d903873c19`。
- [manifest 原字节副本](evidence/2026-10-22-sios-h01-final-repair/manifest.json)及 [sidecar](evidence/2026-10-22-sios-h01-final-repair/manifest.sha256)：manifest SHA256=`8d2f2400b011891f17f6e9c9e2950c6608ab12d1759044cc06e04040e02be79a`；与 ZIP 内字节完全相同。
- Owner 请求中的 ZIP 摘要 `82dd2f7258a410285f6be27be7232d35fa31f7d903873c19` 仅 48 位，不能作为完整 SHA256。以上 64 位值由原 ZIP 实算，并与原修复报告、completion.json、SIOS 独立 receipt.json 三方一致；manifest 符合 Owner 给定的完整摘要。没有修改 ZIP 或用新包替换原件。

有界接受仅覆盖 513500、513030、513520 的冻结研究输入：预热 2023-03-09—2023-12-29，观察期 2024-01-02—2025-09-30。独立接收报告为相邻 SIOS 仓库 `docs/m1-r2/R2-H01-independent-consumer-receipt-2026-10-22.md`，脚本和原始收据在 `research/h01-independent-receipt-2026-10-22/`；正式关闭记录为 `docs/m1-r2/R2-H01-owner-acceptance-closeout-2026-10-23.md`。

本次只复核归档身份：123 个 ZIP 成员 CRC、120 项 manifest 摘要/字节数，与独立接收的完整成员清单逐项一致；6 份消费者合同及独立脚本身份一致；197 份修复前受保护原件摘要一致。原 87 项与新增 14 项测试的 JUnit 原件无 failure/error。本次没有重跑 H01 数据构建、接收全流程、研究或策略实验。

## 旧失败链、代码与复现

[旧部分交付报告](2026-10-22-sios-h01-priority-delivery.md)和 [旧完整失败 ZIP](evidence/2026-10-22-sios-h01-priority-delivery/H01-delivery.zip)同时落库。旧 ZIP 为 8,607,260 字节，SHA256=`18b3025a7380f4d1f7e510b41af435f08b5e8788314e1278c99c2429c4df7877`；旧 manifest SHA256=`68ca0d4facc72b03f4828aae1b254fbd10beec4b456d7aa1ff80cea0e89f1dd0`。99 项 CRC、96 项 manifest 文件身份重新核验通过。旧包零 PIT 合格行和 BLOCKED 结论保留；它是已确认资格实现缺陷的历史证据，不是机制经济失败，也不被本次接受改写成当时已通过。

根因与原接收器失败记录见 [root_cause.json](evidence/2026-10-22-sios-h01-final-repair/root_cause.json)、`original-receiver-original-package.json` 和 `original-receiver-new-package.json`。新 ZIP 中的 `parent_evidence/`、`parent_identity.json` 继续连接旧 manifest 和失败结果。

新旧 ZIP 均直接保存为完整 Git blob，未使用 LFS 指针或外部下载替代数据。完整行情、官方原件、提取文本、冻结合同及新旧复现工具包含在 ZIP 内；必要研究脚本、两份原始回归测试、测试命令/JUnit/日志一并归档。生产 `src/`、消费者策略、版本 pin 和历史 Gate 均未改变。

不重复提交完整解压目录。旧报告中解压目录链接指向当时工作副本；在独立的受控复现目录中，按各 ZIP 内的根目录名解压即可恢复。包内 `tools/rebuild_delivery.py --package .` 和 `tools/receive_repaired.py . --report validation_report.json` 为原离线复现入口，详见包内 README；本归档任务未执行它们。若复现仓库原测试，应将 ZIP 解压到各 evidence 父目录，并从旧包恢复父目录的 `extracted/`、从新包恢复父目录的 `contracts/`。原测试脚本字节不改。历史 `verify_repair.py` 含修复时 HEAD/状态的冻结断言，不把归档后 HEAD 的变化伪装为该历史断言通过。

## 限制、学习与交接

`PASS_BOUNDED` 证明固定窗口研究输入被接受，不证明投资机制、净收益、成本、完整执行资格、QDII 适配或未来独立 OOS。历史 RAW observed-vintage、全历史预案/取消索引及停牌公告盘前可知性等限制按独立收据继续保留。没有新增正确性 blocker；没有范围扩张。

- ORIGINAL_QUESTION：将已批准 H01 数据接受决定与原件、独立收据一起持久归档。
- OBSERVED_RESULT：原 ZIP、manifest、原件及收据身份一致；Owner 已正式 PASS_BOUNDED，H01 数据供给关闭。
- LESSON：数据接受与机制实验授权分别记录；旧失败证据和旧 pending 结论保留时间顺序。
- REMAINING_UNKNOWN：H01 经济有效性与执行资格仍未验证；H04、P2 数据尚未就绪。
- NEXT_DECISION：CONTINUE，仅完成本次受控归档。
- NEXT_MINIMUM_ACTION：下一项数据供给为 H04，P2 排队；本任务不启动两者，不授权 H01 机制实验或下一 Phase/Release。

归档提交以本文件所在提交为准（`git log -1 --format=%H -- docs/audits/2026-10-23-sios-h01-owner-acceptance-closeout.md`）。完整白名单及暂存 blob 核验记录保存在 SIOS 的 `research/h01-independent-receipt-2026-10-22/archive-integrity.json`；最终交接列出两提交 SHA。既有无关未跟踪文件保留，归档后工作区不承诺全局 clean。

归档保全核验另发现 H04 `network_ledger.json` 在本任务期间发生外部并发写入；本任务未触碰、未恢复、未暂存该文件。其余起始未跟踪文件逐一保持原摘要；该并发材料不影响 H01 身份或接受决定，详见归档校验记录。
