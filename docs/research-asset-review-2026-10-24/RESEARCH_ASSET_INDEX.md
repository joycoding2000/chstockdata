# chstockdata 历史研究成果索引

日期：2026-10-24，Asia/Shanghai。范围仅 chstockdata；SIOS、Mishi 的独立资产审查由各自会话负责。本轮是资产盘点和决策整理，没有执行来源请求、资格实验、开发、发布或清理，也没有重判 Owner Acceptance。

## 阅读入口与权威状态

- 本地 main：`a2072d0c722d7f7935309a15cef945bc8ecbef08`；实查远端 main：`5584f5fcacccef9a9531a7a32b8463ea6771d312`。两者差一项 H01 Acceptance 归档提交，不能把本地领先当成 main 整合授权。
- 正式 `v0.4.3`：tag object `08f9eb11e1dd1181cb50d754c4d973196a4fe4b5`，peeled commit `30cc7c50e3971fe79bfd903a412b2b76a0338caa`。本轮只核实引用及既有发行记录，不重跑历史发布 Gate。
- 综合恢复说明：[SSD-MIGRATION-RECOVERY](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/SSD-MIGRATION-RECOVERY-2026-10-23.md)。它是入口，具体决策以较新的具名附录为准。
- 未跟踪研究/文档已保存于 `codex/ssd-migration-main-2026-10-23` → `db972cbbaf43688dd6fff2024e4c08cfdc8423d4`。本地旧候选的工作区字节由 `codex/ssd-migration-rh3b5-worktree-2026-10-23` → `aa53736009b2a8a1f69db1b900ca305c80fdd8a0` 保存；旧审计独立提交由 `codex/ssd-migration-orphan-141c0ad-2026-10-23` → `141c0ad592be74b1a1a7b57252cccf6918d5ae4f` 保存。
- DR03 独立归档：`codex/dr03-capco-archive-2026-10-23` → `88e0ac6f56cbe95d838d3621418b84c8af476743`；v0.4.2 发行收口独立提交：`codex/v042-release-audit` → `a34c8c25b78a4b3a9f2263a69e54977a618cfbbd`。它们各有 main/三个 SSD 快照以外的独有提交，继续保留。

研究状态与证据状态分列。这里的 TESTED 只表示既有材料含有界实测及其日志/身份记录，**不表示本轮重跑通过，更不表示产品 Gate 已通过**。所有资产保留分类和精确清理目标见 [清理方案](ASSET_RETENTION_AND_CLEANUP_PLAN.md)；待决事项见 [决策队列](RESEARCH_DECISION_QUEUE.md)。

## 13 个研究主题

| ID / 原始问题 | 实际工作、结论与有效边界 | 状态 / 证据 | 来源、后续关系与保留价值 |
|---|---|---|---|
| T01 早期结构化能力、日历与消费者资格 | RH1–RH3-A 验证包、真实消费者、VIPDOC 长历史、Eastmoney 路由及 extras。早期 BLOCKED 后有有界修复；不倒改早期失败。mootdx 与 MCP 的依赖冲突是具体环境约束。 | CLOSED_WITH_EVIDENCE / TESTED | [RH3-A 最终记录](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-09-23-v0.4.0-rh3a-final-closeout.md)。旧审计 `141c0ad…` 保留；VIPDOC 输入仍有运行和复现价值。报告 KEEP，历史运行证据 ARCHIVE；不重开已关闭资格。 |
| T02 RH3-B 恢复候选及历史执行可行性 | 保存 v0.4.1 候选、live qualification、RH3-B5 差异；随后调查 v0.4.2 的长历史与盘前执行证据。技术资格失败说明当时输入/执行事实不足，不是投资机制失败。 | CLOSED_WITH_EVIDENCE / TESTED | [历史恢复结论](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-09-v0.4.2-history-recovery-conclusion.md)、[TDX 执行调查](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-10-v0.4.2-tdx-historical-execution-feasibility.md)。后续正式发行覆盖旧候选的开发用途；反证、差异和精确候选包仍有追溯价值。 |
| T03 v0.4.2 开盘执行实现与正式落地 | R2.1 实现、红绿测试、消费者冻结源、拒绝例、Owner rework 及受控发行。旧 10-09 阻断与后来的 10-14 正式发行是不同时间事实。 | DECIDED / TESTED | [实现记录](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-11-v0.4.2-opening-implementation.md)、[正式发行](https://github.com/joycoding2000/chstockdata/blob/a34c8c25b78a4b3a9f2263a69e54977a618cfbbd/docs/audits/2026-10-14-v0.4.2-controlled-release.md)。13,118 个 opening evidence 文件混合报告、源快照、测试副本与生成输出；不能整组按缓存删除。 |
| T04 DR04-P 与 W0/v0.4.3 | 日频资金流合同、type identity/回归修复、Owner PASS 及后续正式发行。 | DECIDED / TESTED | [Owner Acceptance](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-18-dr04-p-owner-acceptance.md)、[W0 closeout](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-19-v0.4.3-release-closeout.md)。正式代码/测试/合同 KEEP；旧环境可再生。DR04-M 仍 NOT_AUTHORIZED，PASS 不覆盖全市场或历史 PIT。 |
| T05 双消费者合同与 DR01–DR06 缺口 | 形成需求、范围批准、供给差距及优先级；它们不是所有来源已合格的证明。 | ACTIONABLE / INSUFFICIENT_EVIDENCE | [综合缺口](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/DR02-DR06-consolidated-gap-report.md)、[双消费者计划](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/plans/2026-10-19-dual-consumer-supply-plan.md)。KEEP；作为研究导航使用，实际优先级/授权以较新的 Owner 记录为准。 |
| T06 DR01-CURRENT 免费全池来源 | 复用沪深官方枚举/风险材料，调查 BaoStock 指定日全证券状态；既有实测登录超时，未取得合格深市 D 日完整状态。 | INVESTIGATE / INSUFFICIENT_EVIDENCE | [DR01 调查](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/DR01-current-free-data-feasibility-2026-10-19.md)。技术路线明确但实施仍阻断；“未取得”不能改写为免费来源必然无解。主要原始包在 Mishi outputs，本仓未保存其完整副本。 |
| T07 W5-H/R2–R4：免费原始访问、TDX 混合修订与原件恢复 | 找到本机 VIPDOC、财务包并解析；TDX 同一 DAT 行中部分字段为修订值、部分仍为原值，公告日期未能证明字段 vintage。官方原报/更正材料可恢复具名四字段及三历史 T。 | CLOSED_WITH_EVIDENCE / TESTED | [R3](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-20-w5h-r3-tdx-local-opensource-qualification.md)、[R4](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-20-w5h-r4-tdx-revision-root-cause-and-archival-pit.md)。KEEP 核心反证和历史版本。可访问、可解析、字段一致、PIT 是不同资格；无需重复“能否免费下载”调查。 |
| T08 W5-H R5/R6/F1/F2 与最终字段资格 | 从规模屏查推进到解析修复、版本选择和 23 份来源闭合；F1 纠正 R6 单位污染并撤回“因此免费路线应停止”的推论。最终 11 份原件的四个扫描包仍有 18 个必要字段槽缺口；固定集合 84 SELECTED/57 UNKNOWN 保留。 | INVESTIGATE / INSUFFICIENT_EVIDENCE | [F1](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-21-w5h-r6-f1-parser-correction.md)、[source closure](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-21-w5h-f2-source-closure.md)、[最终资格](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-22-w5h-f2-final-evidence-qualification.md)。当前固定窗 PARTIAL_WITH_PROVEN_GAPS，S07 NOT_PASSED；不等于文档自动化不可能。原件、列/期间/单位证据、失败负控 KEEP；已结束阶段底稿可 ARCHIVE。 |
| T09 S07 真实窗口、历史 PE 与 U | 绑定 e=2026-10-22、s=2025-10-09，另有 65 日预热；两股 506/506 日估值数值槽取得，但原控制无 PIT 认证，完整历史池与行业仍缺证。 | INVESTIGATE / INSUFFICIENT_EVIDENCE | [决定性屏查](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-22-s07-free-supply-decisive-screen.md)、同目录 calendar/PE/universe 台账。KEEP；数值覆盖不能替代来源版本资格，本地 VIPDOC 库存数量也不是历史 U 分母。 |
| T10 DR03 CAPCO 行业成员与时间语义 | 三个官方半年版本存在；2026H1 交集 5,192/5,223，缺 31 只，另有两只已退市成员。Owner 后续批准 published-version as-of；旧“必须逐日迁移档案”的排除逻辑不再充分。 | ACTIONABLE / INSUFFICIENT_EVIDENCE | [Owner Addendum](https://github.com/joycoding2000/chstockdata/blob/88e0ac6f56cbe95d838d3621418b84c8af476743/docs/audits/2026-10-23-dr03-owner-decision-addendum.md)、[42 项载荷＋清单](https://github.com/joycoding2000/chstockdata/blob/88e0ac6f56cbe95d838d3621418b84c8af476743/docs/audits/2026-10-23-dr03-s1-archive-manifest.json)。旧 STOP/解析缺陷原件仍保留；2025H1 原公布字节、taxonomy、分母与窗口风险未解。重新资格 NOT_STARTED，两个 Gate NOT_PASSED；不是重评已获授权。 |
| T11 SIOS H01 固定输入交付与接受 | 从零 PIT 合格行的旧失败包推进到修复、独立接收及 Owner PASS_BOUNDED；供数关闭。 | DECIDED / TESTED | [Acceptance closeout](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-23-sios-h01-owner-acceptance-closeout.md)。新旧 ZIP、manifest、收据、复现代码与失败链 KEEP；本地 main 唯一领先提交保存此收口。不得将供数接受外推成机制、成本、执行或 OOS 通过。 |
| T12 SIOS H04 总回报与归因 | 两基金 1,370 条经济回报/财富输入；8 个真实基金截面、868 条证券截面和 88 条行业截面。930914 方法版本与基金招募描述存在具名冲突；基金持仓不能充当真实指数历史权重。 | ACTIONABLE / INSUFFICIENT_EVIDENCE | [H04 交付](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-22-sios-h04-priority-data-delivery.md)。TR 为 PASS_FOR_CONSUMER_REVIEW，归因为 PARTIAL_WITH_NAMED_GAPS；SIOS Acceptance 待完成。官方 PDF、交付包及来源身份 KEEP；不把解释序列缺失记零。 |
| T13 SIOS P2 五品种期货历史供应 | 对 RB/BU/C/CS/PP 2020–2025 的入口、公共样本和外部导出成本作调查；无已验收完整文件。 | PARKED / INSUFFICIENT_EVIDENCE | [生产者响应](https://github.com/joycoding2000/chstockdata/blob/db972cbbaf43688dd6fff2024e4c08cfdc8423d4/docs/audits/2026-10-19-sios-p2-producer-response.md)。EXTERNAL_SOURCE_PREFERRED、非 READY_TO_DELIVER，P2 QUEUED；调查样本 ARCHIVE，合同 KEEP。推荐是当时成本判断，本轮未重新认证服务能力、价格或权限。 |

## 值得显式索引的 8 项发现

1. **R6 路线判断已有实质后续修正**：F1/F2 解除具体解析缺陷，但保留具名缺口。只读 R6 会错误推动采购或否定免费路线；最终 FREE_ONLY/FIX_ONLY 边界不变。
2. **TDX 的反证在字段内容层**：可下载与顶层勾稽通过仍可能混合修订；它是数据资格反证，不是财务因子或策略经济价值反证。
3. **Source Closure 的“8 个重复”是目标事实粒度**：不证明 PDF 全字节、所有期间或研究版本等价，不能据该数字删除八份原件。
4. **CAPCO 候选仍有价值**：Owner 已放宽到公开版本 as-of；2025H1 当前字节与原发布日期关系是 UNRESOLVED_RISK，不是已证明实质修订，也不是旧逐日生效要求继续有效。
5. **H04 有可复用的历史暴露切片**：真实基金截面及方法版本冲突可帮助后续归因审查，但不能代替连续指数/风格输入或证明红利机制收益。
6. **H01 的接受与旧失败同时成立**：保留旧失败包可以区分资格实现缺陷与机制结果，避免下一会话把旧 BLOCKED 或修复后的 PASS 推广出界。
7. **冻结消费者副本中的大批研究文件是重复实例**：清理优先考虑经集合级比较证实等价的副本，以及独立安装环境；不要用目录名 var/build 推断原始研究没有价值。具体比较结果在 `collection-verification.json`。
8. **W0 本地工件与正式发布工件不同**：两个本地 SHA 与既有 `local-artifacts.json` 相符，但不等于正式 PyPI 包，也未证明有独立字节副本。工作区不能仅因 W0 已结束和提交已在 main 就删除，现归 REVIEW；不因此改判 v0.4.3 发布状态。

## 外部原始材料索引与恢复边界

| 材料/位置 | 已有索引和用途 | 本轮处理 |
|---|---|---|
| `D:/Dev/Projects/chstockdata/.rh3a2-vipdoc` | 12,427 文件，952,292,279 B；manifest 与 RH3-A.2/R3 记录价格尺度、历史日历和版本 | KEEP。GitHub 不含这组原件；刷新不保证当时字节。F 盘独立备份是否完成未证。 |
| `C:/Users/Administrator/.chstockdata/cache/vipdoc`、`C:/zd_zxzq_gm/vipdoc` | R3 `before.json`、来源调查和文件索引记录了历史库；存在其他库不证明与本项目快照等价 | REVIEW 外部依赖，只引用已有索引，不再全盘扫描或重复累计容量。 |
| `D:/Dev/Projects/easy_tdx` 旧财务下载 | R3 evidence 内有旧 ZIP/DAT 身份；下载本身不能证明 vintage | 外部原件保留责任未转移；项目内已保存的反证输入 KEEP。本轮不清理该仓库。 |
| `D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18` 等 DR01 原始包 | DR01 调查、DR03 verification/归档清单引用官方枚举与证券原始清单 | 跨项目依赖，未证明独立冷备份。不能删本项目指针后称归档自包含。 |
| `D:/Dev/Projects/systematic-investing-os` H01 receipt / 冻结 M0/M1 | H01 Acceptance 与交付 manifest 提供身份关联；资格快照内另有冻结研究 var | 只承认已存收据和引用，不审核或推进 SIOS 研究；本轮保留一份本地冻结 var 作为副本清理的恢复锚。 |
| `D:/Dev/Projects/chstockdata-frozen-v042`、既往仓库外 qualification 环境 | 恢复说明/R3/发行记录提及的历史副本 | REVIEW，未纳入“五个登记工作区”总量；不是已证明可删除的重复副本。 |
| Owner 的 F 盘迁移备份、`.codex` 原会话 | SSD 恢复说明声明 Owner 负责复制，未给出完成收据 | 不将计划当成完成证据；本轮不扫描或清理会话，也不把 GitHub 分支当作 VIPDOC/build 的完整备份。 |

## 交接

当前阶段/步骤：历史资产盘点与清理决策整理，停止在 Owner Review；不是正式开发新 Gate。研究状态依据上述原件和已保存输出，未以本轮重跑证明历史 PASS。提交身份由审查分支及最终交接记录给出，避免提交自引用。当前 main、已登记工作区和原始研究文件保持原状；下一步是 Owner 审阅队列与精确清理清单，任何清理、main 整合或研究续作均不因本索引获得授权。
