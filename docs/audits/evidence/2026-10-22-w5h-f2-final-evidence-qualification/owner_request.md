# chstockdata — W5-H-F2 最终自动化缺口修复与来源资格收口

## 一、Owner 决策

```ini
CURRENT_DECISION = FIX_ONLY
TASK = W5_H_F2_FINAL_AUTOMATED_EVIDENCE_CLOSURE

DATA_SOURCE_POLICY = FREE_ONLY
PAID_SOURCE = PROHIBITED

USE_EXISTING_ORIGINALS = YES
NEW_NETWORK_REQUESTS = NO
OFFLINE_PARSER_FIX = AUTHORIZED
IMAGE_TABLE_EXTRACTION = AUTHORIZED
FIELD_SCOPE_QUALIFICATION = AUTHORIZED
VERSION_REPLAY_REGRESSION = AUTHORIZED

PRODUCTION_RUNTIME = NO
NEW_PROVIDER = NO
NEW_DATABASE = NO
CONSUMER_CHANGES = NO
PRODUCT_SCOPE_CHANGE = NO

GIT_COMMIT = NO
GIT_PUSH = NO
RELEASE = NO
```

Owner 已明确要求：同一已授权工作包内的程序缺陷连续修复，不得每修复一个字段就中途停止申请批准。

本任务目标是对 F2 Source Closure 尚未认证的 11 份原件完成一次充分、有界、可复核的程序化处理。

不以 UNKNOWN 数量必须为零为唯一成功标准，也不允许因为程序目前无法处理就默认这些原件永远需要人工。

## 二、恢复权威证据

读取：

- `AGENTS.md`
- Mishi R3.2 已批准范围
- DR05 历史数据要求
- R4、R5、R6、F1、F2 审计结论
- `docs/audits/2026-10-21-w5h-f2-source-closure.md`
- 上述来源对应的离线程序、实物、OCR 证据、字段检验和版本账本

当前远端基线：

`5584f5fcacccef9a9531a7a32b8463ea6771d312`

实际 HEAD 与工作区先核对；保留全部原有 tracked/untracked 内容。

不得改写旧失败结果、已归档源文件或原始证据。

## 三、工作 A：扫描财务原件的程序化认证

固定五份：

```text
1216741269
1216869640
1217078313
1217949874
1218110511
```

已经执行过普通中文/英文整页 OCR 与局部放大 OCR，本轮不得无条件重复同样的处理流程。

按顺序使用以下方法：

### A1. 检查原件内部图像结构

检查是否存在：

- 可直接提取的嵌入图像对象；
- 可证明相同内容的重复扫描页；
- 与此前保存的官方原报相对应的财务报表页；
- 可以恢复的表格边界与字段行列；
- 可靠的财务期间、单位、合并/母公司列头。

先做 PDF 图像对象身份及表格结构调查，再决定是否需要重新识别数字。

### A2. 有约束的行列恢复

针对必要页面：

- 资产负债表：NP 不适用，重点识别 EQ；
- 利润表：识别归母净利润 NP；
- 现金流量表：识别经营现金流 OCF。

明确财务表格类型、实际报表主体、金额单位、当前期间及比较期间。

允许在现有离线研究环境中改进图像预处理、表格网格定位、列关联及局部 OCR。

不能因为识别出一个金额与已知值相同，就认为整张表已经认证。

对于需要比较原报版本的字段，要保存扫描图像中的原始位置及独立比对依据。

### A3. 重复披露识别

如果某个扫描包只是既有原始财务报告的重复副本，允许使用可复核的内容身份或目标字段级等价证据解除对应字段阻断。

需要明确区分：

- 页面或字节级相同；
- 目标字段、单位、期间和主体完全对应；
- 仅部分金额相同；
- 只是审计报告编号相同；
- 无法确认等价。

后两种情况不能直接放行。

如存在 Q1/H1 附表，其版本资格须独立判断，不能因为 FY2022 年报相同就自动覆盖这些附表。

## 四、工作 B：六份回复 OCF 主体归属修复

固定：

```text
1216741268
1216741273
1217078312
1217078316
1217949872
1217949876
```

重点不再是金额提取本身，而是证明：

- 数值属于合并报表还是母公司报表；
- 对应 2021 或 2022 哪一财务期间；
- 是实际披露值、比较值还是引用的审计值；
- 报告期间与单位是否一致；
- 所引用的既有财务原件身份是否能够确定。

优先利用同一文档的章节、表标题、列头、审计引用及明确的文本关系。

不得以“数值恰好等于已知合并 OCF”为唯一理由推定主体。

特别处理：

- `1216741273` 第 88 物理页；
- `1217078312` 第 97—98 物理页。

这是此前 24 项检查中两项 UNKNOWN 的具体位置。

程序修复必须适用于相同结构类型，不允许为证券代码或公告 ID 编写数值硬补丁。

### 2021 年 OCF 300 元差异

保留六处文字与表格差异的完整清单。

通过单位、舍入、原始财报引用和表格主体检查，判断该差异究竟属于：

- 不同报表口径；
- 有限精度表达；
- 源文件内部笔误或不一致；
- 无法确定原因。

不得未经证据直接消除差异。

如果相关 2021 基期确实进入 S07 所需信息集合，未解决的数值冲突必须继续 fail-closed。

如果该事实不属于受检字段/期间或特定历史 T 的必要依赖，也应证明其不影响范围，而不是要求整个历史数据系统为无关差异停摆。

## 五、工作 C：把剩余来源证据与历史 PIT 回放连接

读取并复用现有 F2 的认证账本和时序测试。

对 11 份来源分别输出：

```text
document_id
affected_security
affected_period
affected_field
accounting_scope
source_version
disclosure_date
evidence_page
qualification_status
historical_T_impact
```

判定状态至少包括：

- `VERIFIED_EXISTING_VERSION`
- `VERIFIED_NEW_FINANCIAL_FACT`
- `VERIFIED_NO_TARGET_EFFECT`
- `DIFFERENT_ACCOUNTING_BASIS`
- `UNRESOLVED_MATERIAL`
- `UNRESOLVED_NON_MATERIAL_FOR_FIXED_T`

`UNRESOLVED_NON_MATERIAL_FOR_FIXED_T` 必须有确切的字段、期间及依赖分析支持，不等于原件所有未知事项已经解决。

如果发现真实更早版本，更新相应最早可用证据和历史 T 回放。

如果没有发现新版本，不能把“本轮 0 个新增修订”自动称为未知修订召回率 100%。

仍未认证的必要中间版本，继续按原有 fail-closed 规则拒绝。

## 六、连续修复，不制造额外阶段

执行：

```text
现有扫描及正文证据
→ 结构识别
→ 单位/主体/列认证
→ 与原始披露比较
→ 历史版本资格
→ 历史 T 回放
→ 全部既有回归
→ 如遇程序 Bug，在本工作包内继续修复
```

不得因首次 OCR 失败、单个字段 UNKNOWN 或一次回归失败而立即退出。

但也不允许无止境调参。若已经有具体证据证明当前材料质量不足、存在无法认证的真实源冲突，或下一步需要新生产架构，应明确记录停止原因。

所有已解决和未解决事项必须保留原件与测试分母。

## 七、必须保留的回归

至少保留：

- F1 原有 89 项；
- F2 70 项；
- F2 EPS 3 项；
- F2 46/46 和 118/118 历史回放；
- Source Closure 新增 23 项时序断言；
- 既有 36 项安全/身份/目录测试和新增 10 项测试；
- 已有实际质量检查；
- 所有已确认万科单位污染、茅台权益、康美 OCF 正负修订、历史 T 未来值拒绝测试。

不得减少检查项来取得 PASS。

对于新增扫描读取，额外测试错误的列归属、金额倍率、错误主体及伪重复判定。

## 八、这次真正的完成条件

完成时必须把两个问题分别裁决。

### A. 固定历史窗口来源资格

能否对 11 份原件的受检影响形成可复核判断？

如果全部必要字段闭合，返回：

`FIXED_WINDOW_FINANCIAL_SOURCE_QUALIFIED_BOUNDED`

如果仍有客观无法认证的必要证据：

`FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS`

不得因为 UNKNOWN 未清零就继续无限扩大工程，也不得因为某些 UNKNOWN 无关就掩盖真正影响历史 T 的缺口。

### B. 产品级 PIT 资格

保持：

`MISHI_S07_HISTORICAL_GATE = NOT_PASSED`

除非另有针对实际产品范围的独立完整 Gate 证据及 Owner 验收，本任务不得更改。

完成 A 后应停止重复研究旧的六证券案例，转向准备实际 S07 目标窗口、全市场历史财务覆盖和估值资格的准入评估。

本次不启动生产 Provider、数据库或全市场获取。

## 九、交付

仅新增：

`docs/audits/2026-10-22-w5h-f2-final-evidence-qualification.md`

和对应有限证据目录。

结束时输出：

```ini
CURRENT_DECISION =
FINAL_SOURCE_QUALIFICATION_VERDICT =

SCANNED_DOCUMENTS = 5
SCANNED_FIELD_QUALIFICATION =
OCF_SCOPE_DOCUMENTS = 6
OCF_SCOPE_QUALIFICATION =
FY2021_OCF_CONFLICT =

REMAINING_MATERIAL_UNKNOWN =
REMAINING_NON_MATERIAL_UNKNOWN =
FIXED_WINDOW_FINANCIAL_SOURCE_GATE =
FIXED_CASE_ASOF_REPLAY =
ACCEPTED_INCORRECT_VALUES =
FULL_REGRESSION =

FREE_SOURCE_POLICY = ENFORCED
NEW_NETWORK_REQUESTS = 0

NEXT_MINIMUM_ACTION =
S07_REAL_WINDOW_QUALIFICATION_READY =

MISHI_S07_HISTORICAL_GATE = NOT_PASSED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
PRODUCT_SCOPE_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```

这是当前 F2 工作包剩余原件的最后一次集中自动化资格处理，不是新数据平台的实施授权。

不得退回付费数据路线，不得默认人工抄数，也不得通过提高 UNKNOWN 数量或放松历史真实性标准制造通过。

完成后一次性提交 Owner Review。