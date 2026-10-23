# DR03 — Owner Decision Addendum：时间语义纠正与归档收口

Owner 决定及记录日期：2026-10-23（Asia/Shanghai）。前轮语义方向批准后，Owner 又以《chstockdata — DR03 时间语义修正与 CAPCO 归档最终收口》明确授权最小合同修订、两仓库同步、受控提交及不夹带 H01 的 GitHub 备份。本附录据此更新当前文档/Git 授权；`IMPLEMENTATION_AUTHORIZED=NO`，不授予来源资格、代码或下一阶段授权。

## 1. 当前裁决

```ini
CURRENT_DECISION = CHANGE_REQUEST
OWNER_SEMANTIC_DIRECTION = APPROVED
CONSUMER_CONTRACT_CLARIFICATION = APPROVED_DOCUMENTED__MISHI_SYNCED
CAPCO_OLD_STOP_RECORD = PRESERVED
CAPCO_REQUALIFICATION = NOT_STARTED
CAPCO_SOURCE_STATUS = OFFICIAL_SOURCE_AVAILABLE__REQUALIFICATION_PENDING
DR03_CURRENT_GATE = NOT_PASSED
DR03_HISTORICAL_GATE = NOT_PASSED
SOURCE_QUALIFICATION = PARTIAL
IMPLEMENTATION_AUTHORIZED = NO
GIT_COMMIT = AUTHORIZED_EXACT_WHITELISTS__SHA_IN_FINAL_HANDOFF
GIT_PUSH = AUTHORIZED_SAFE_BACKUP__REMOTE_SHA_IN_FINAL_HANDOFF
SCOPE_DEVIATION = NONE
NEXT_MINIMAL_ACTION = COMPLETE_CONTROLLED_ARCHIVE_AND_BACKUP_THEN_OWNER_REVIEW
```

## 2. 对原 STOP 的限定及保留

原件全部保留：[S0A](2026-10-23-dr03-s0a-capco-historical-source-review.md)、[S1](2026-10-23-dr03-s1-capco-historical-membership-qualification.md)、[旧 close-out](2026-10-23-dr03-s1-closeout.md)、S0A 的 33 个证据文件及 S1 的 `verification.json`。原 `STOP_CURRENT_CAPCO_INSTANCE`、失败、派生缺陷及历史 Gate 不回写、不删改。本附录按时间顺序接续旧记录。

1. **原 STOP 只对旧资格解释成立。** 其中把“无逐日/逐事件成员档案、生效/首次可知链不精确”一概判为来源结构性不匹配的理由，不再是新语义下排除 CAPCO 的充分依据。旧 close-out §5.2/5.3 的逐事件条件及 §5.6 的合同变更前提，应结合本次决定重新解释；不是继续把全部旧条件列为新方向硬门槛。独立存在的当前覆盖缺口、内容版本风险等仍然有效。
2. **CAPCO 已有半年度版本具备重新评价价值。** S0A/S1 保存的 2025H1、2025H2、2026H1 三个官方版本及相应文件身份，足以成为未来有界重新评价的候选；这是设计可行性方向，不是资格 PASS 或重新评价启动。
3. **修订原则是 published-version as-of。** 交易日 T 仅用 T 之前最新已公开的官方版本；仅发布日期则从下一交易日开始使用，两个公布版本之间沿用上一版本；禁止未来发布或后续修订倒填。不要再强制逐日迁移档案或秒级成员生效时间。与既有 U1 的次交易日收盘使用、OD-2/X01 的后续开盘执行，以及 S06/S07 受影响条款的关系，见[合同修订记录](2026-10-23-dr03-consumer-contract-clarification.md) §3–§4。
4. **2025H1 历史内容修订风险仍未解决。** 保存文章日期为 2025-09-30，PDF 创建时间为 2025-09-29，但当前对象路径含 `/file/202603/`、HTTP Last-Modified 为 2026-03-27 12:14:12 GMT。现有文件不能证明当前字节就是 2025-09-30 公布字节；也不能仅凭对象日期断言一定发生实质修订。状态为 UNRESOLVED_RISK，不能把页面日期直接赋给当前内容。H2/2026H1 的页面/对象时间较一致，也不自动取得资格。
5. **全池、taxonomy、未分类问题仍存在。** 保存的 2026H1 与 DR03 2026-10-22 合同候选交集为 5,192/5,223，31 只缺行业，快照另含两只已退市证券；taxonomy 正式版本/层级与金融分类绑定、未分类分母及新上市未收录处置未解决。这些是既存证据事实，本轮未重算成员或重新认证。不能将已公开版本允许沿用误写为“当前全池已满足”。
6. **两个 DR03 Gate 继续 NOT_PASSED。** 撤销过严解释不等于补齐真实窗口、分类身份或完整性证据，不把半年度版本存在性当作全市场历史资格。具体 s/e、早期公布版本和必要预热覆盖仍须按原范围回答；已有版本最早可用日以前不得倒填，也不得静默缩窗。
7. **不自动启动新资格验证或数据实现。** 本轮仅文档差异确认、合同同步、决策附录和受控 Git 归档；没有抓取 CAPCO/其它来源、重新跑资格程序、回测、改 runtime、增加 API、建库或进入下一阶段。未来若开展重新评价，须另行明确范围与授权。

## 3. Findings 分类

| 分类 | 当前记录 |
|---|---|
| CONFIRMED_DEFECT | 原 S0A 北交所映射 JSON 246/官方文本 248 行的解析遗漏，以及 S1 两个退市证券组合布尔标注不自洽，按旧 close-out §3.3 保留；本轮不修原件、不改变其历史结论 |
| UNRESOLVED_RISK | 2025H1 内容版本与发布日期的关系；taxonomy/金融分类和未分类分母；31 只当前缺口、早期版本/真实窗口及覆盖；来源重新资格尚未执行，消费者文档修订不等于运行实现验收 |
| SPECULATIVE_CONCERN | 所有半年度分类都必然泄漏未来；必须有逐日迁移或秒级生效时间才能满足产品目标；当前 2025H1 PDF 必然被实质修订。这些推断没有充分证据，不据此扩大工程或重开研究 |
| FUTURE_ENHANCEMENT | 新重新资格包、生产解析/数据库/API、来源补抓、历史回填及消费者实现均不在本轮范围；必要后续由独立授权决定 |

## 4. 归档预审更新

旧预审的 **37/37 哈希、38 个拟归档文件**是历史基线，旧 close-out 不改写。原 archive manifest 是可更新的归档控制清单，已按本轮最终文件重算；旧 manifest 的原始字节数/SHA 及原 37 项身份保存在[本轮核验记录](evidence/2026-10-23-dr03-owner-semantics-closeout/verification.json)的 `baseline`，不把旧哈希当作更新后控制文件身份。

| 范围 | 数量 | 本轮处理 |
|---|---:|---|
| 原 37 项载荷/控制文件 | 37 | 逐一核对旧清单 SHA-256/字节；原件不修改，包括旧 close-out |
| 合同修订记录 | 1 | 本轮更新为已批准/已同步身份 |
| 本 Owner Decision Addendum | 1 | 本轮新增 |
| 本轮核验 JSON | 1 | 保留前轮核验，追加本轮变更身份、授权及精确白名单 |
| DR03 消费者合同副本 | 2 | 与 Mishi 的 R3.2/DR 请求中本次最小修订同步 |
| 更新后的 archive manifest | 1 | 不自覆盖；其摘要在最终交接中单列 |
| **准确白名单总计** | **43** | manifest 覆盖 **42** 项，另加 manifest 自身 |

完整精确路径、角色、字节数、SHA-256 和 **43 项白名单**见 [archive manifest](2026-10-23-dr03-s1-archive-manifest.json)。前轮 41 项增加两份本次直接同步的消费者合同副本，不纳入其它无关材料。白名单逐文件列出，无目录通配、无 git add -A。原 94 个未跟踪条目全部保留，其中两份合同副本获本次明确授权作 DR03 最小同步，其余 92 项不修改、不暂存。

**字节保留条件**：前轮已验证默认 core.autocrlf=true 会转换 21 项原件。暂存仅临时使用 git -c core.autocrlf=false add -- <精确白名单路径>，并逐一验证暂存 Git blob 的原始字节 SHA-256 与 manifest 一致；不修改原件以适应 Git，不改变全局配置或 .gitattributes。

### 4.1 Git 实况与授权边界

- 两仓库均已重新 fetch origin/main。chstockdata 原工作区 main 仍为 a2072d0c722d7f7935309a15cef945bc8ecbef08，远端 main 为 5584f5fcacccef9a9531a7a32b8463ea6771d312；H01 仍是本地唯一待推祖先，未获得本次推送授权。
- 因此从最新 origin/main 创建隔离工作区/分支 codex/dr03-capco-archive-2026-10-23，只复制本次 43 项 DR03 白名单。归档提交父链不含 H01；普通推送仅面向该新远端分支，不修改远端 main，不 rebase/合并、force push 或覆盖既有分支。
- Mishi main=origin/main=9f83a2e03fef771b03d0eea919e0dbd99763cec4，原工作区干净、无额外待推提交。只提交 R3.2、DR01–DR06 请求、产品运行规格、Owner 决策四份文档；正式 OD-1/OD-2 接受及 X01/U1–U3 原件不改，普通快进推送 main 前后独立核对远端。
- 旧 close-out 的 NOT_AUTHORIZED 仍是历史事实。新的 Git 授权仅来自本轮 Owner 指令，既不转用 H01 的授权，也不通过本次归档推送 H01。实际提交/备份结果及精确 SHA 由最终交接记录，避免提交自引用。
- 原 chstockdata 工作区 HEAD 不变、tracked/staged 差异保持为空；全部既有 untracked 文件留在原处。隔离归档工作区在受控提交后应干净。消费者文档同步与归档完成不提升数据 Gate，也不等于 chstockdata main 已整合。

### 4.2 完整性及限制

- 复用前轮原 archive 37 项、S0A manifest 31 项及六份引用输入的已通过核验；本轮没有改动这些原件。只对两份审计记录、核验控制文件及两份消费者副本重算摘要，原 37 项摘要不变；Mishi 四份新合同身份和提交白名单单独记录。随后检查新暂存 blob 与最终清单的原始 SHA-256，不重新执行来源资格。
- 前轮不变输入的已通过核验直接复用；本轮仅重算修改文档/控制文件的哈希，检查新差异、JSON/白名单及新暂存 blob 身份；仅文档/归档身份验证，未运行 runtime 或策略测试。
- DR01 原始输入仍在消费者仓库；DR03 证券原始清单仍在先前 S07 evidence 中，均是有哈希的外部依赖，**不纳入本次 43 项白名单**。归档不是自包含研究数据包，不静默加入无关 untracked 文件。
- 既存派生证据缺陷按原报告披露，完整性 PASS 只证明文件身份与保留，不背书派生字段正确或来源资格。最终独立的 42/42 暂存 blob 核对结果和 manifest 自身哈希由交接给出，避免自引用哈希循环。
- 未创建临时 venv、缓存或构建目录；使用既有工具，仅内存核验及写持久文档证据；隔离工作区是本轮 Git 归档产物，保留供审阅，不自动清理其它任务文件。

## 5. 独立接续交接

- **阶段/步骤**：Owner 已批准的 DR03 最小合同修订与两仓库同步、受控归档/备份；完成后停在 Owner Review，不进入重新资格或实现。
- **提交/工作区**：chstockdata 原 main 保持 a2072d0c722d7f7935309a15cef945bc8ecbef08；隔离归档以远端 5584f5f 为父基线，不含 H01。Mishi 仅四份文档，以 9f83a2e 为父基线。最终提交和独立远端查询 SHA 见本轮最终交接，原工作区未跟踪资料全部保留。
- **Gate/证据**：当前、历史均 NOT_PASSED；原来源资格 PARTIAL 保留；CAPCO 为 OFFICIAL_SOURCE_AVAILABLE__REQUALIFICATION_PENDING。原 S0A/S1/STOP、BSE 映射修正和派生缺陷均保留，42/42 blob 身份核对仅证明归档完整。
- **未解决/范围**：2025H1 内容身份、31 只当前缺口、taxonomy/version、未分类分母、历史全池及 S06/S07 排名影响仍未验证。无八策略、窗口、全市场或 runtime 范围偏移；没有新增工程 Gate。
- **下一最小动作**：Owner 查看已完成的合同修订及远端备份；chstockdata 归档为 ARCHIVE_CLOSED / MAIN_LANDING_NOT_AUTHORIZED（以推送及独立 SHA 核对成功为准），main 整合或新资格任务均须另行授权。
