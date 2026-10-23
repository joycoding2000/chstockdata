# DR03-S1 CAPCO 历史行业成员有界资格验证

日期：2026-10-23，Asia/Shanghai。性质：**READ_ONLY / QUALIFICATION_ONLY**。本报告不建设数据库、不增加公共 API、不修改运行时、不发布版本、不改变 Mishi 原始目标、时间语义、全池分母及验收条件。

## 1. 基线与边界

| 项目 | 实际值 |
|---|---|
| 本地 HEAD | `a2072d0c722d7f7935309a15cef945bc8ecbef08` |
| origin/main | `5584f5fcacccef9a9531a7a32b8463ea6771d312` |
| 工作区 | tracked/staged 无修改；仅新增本报告和 `docs/audits/evidence/2026-10-23-dr03-s1-capco/verification.json` |
| 本轮网络 | **0 次新请求**；只读 S0A 已保存原件和仓库内 DR01/DR03 原始清单 |
| 本轮未执行 | 全池历史回放、策略、生产解析器、数据库、接口、runtime、版本发布、Git commit/push |
| 输入 | Mishi R3.2、DR01–DR06 消费者请求、S07 真实窗口准入报告、S0A 证据、DR01 2026-10-16 原始清单、DR03 2026-10-22 原始清单 |

## 2. 冻结合同恢复

### 2.1 DR03 原始消费语义

`MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md` 与 `MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md` 对 DR03 的要求是：

- **CURRENT_SCAN**：选定一个一致的行业分类；当前**完整**股票→行业 ID 和行业→成员矩阵；**未分类分母**；分类**版本与时点**；S06 广度和 S07 行业内排名必须可计算。
- **HISTORICAL_REPLAY**：**对应历史日生效**的行业归属、成分及**分类修订信息**，尤其是股票迁移、退市及当时无分类；无法提供须明确起止与覆盖。
- 合同没有指定门类/大类/次类的具体层级，只要求选定一个一致分类并能支持 S06/S07 同业比较。CAPCO 的门类（19）和大类（83）覆盖全市场，次类（10）只覆盖制造业；任何层级选择都会影响分母和排名，必须由 Owner/消费者在合同中冻结，本轮不替其选择。
- 历史语义是“对应历史日真正已知的证券资格、行业、财务、资金与价量”，禁止后见之明；不能用今日股票池回填过去。

### 2.2 目标市场与完整分母

S07 真实窗口准入报告恢复了 A4 §3 的范围：每个 D 的沪深主板/创业板/科创板普通 A 股 `U(D)`，排除 B 股/CDR/北交所/ETF/基金/指数，包含当时存在而后来退市的证券；`security_id=exchange:ticker`。因此 CAPCO PDF 的原始 5,413/5,463/5,521 行**不是**合同分母，必须先按代码族过滤 B 股、北交所、CDR 和 `302132`。

### 2.3 时间窗口与预热

- 冻结合同要求最近约 **252 个已完成市场交易日**净值日，另加 **65 个共同技术收盘**预热；S07 自身 AVG_A20 最早只需 `s-20…s-1` 的真实成交额；财务按 `q(T)` 闭包另行向前延伸。
- 具体 `s/e` 尚未绑定。S07 报告给出的诊断锚为 `2025-09-09…2026-09-22`（252 净值日），首个信号日 `2025-09-08`，共同 65 日预热 `2025-06-10…2025-09-08`，S07 首次 AVG_A20 为 `2025-08-12…2025-09-08`。S0A 另引用 `2025-10-09…2026-10-22` 候选窗口。
- 无论采用哪个候选，冻结合同都要求**每个 T 的当日/当时已知行业**，不是半年快照的区间插值。

### 2.4 语义裁决

**CAPCO 是半年度发布快照，不是逐日或逐事件成员档案。** 三个版本没有生效日、没有 known_at、没有迁移生效日、没有未分类分母。即使按对 CAPCO 最宽松的“当时最新公开状态”解释，2025H1 的 known_at 与窗口首尾仍不能满足；按严格解释则直接失败。因此：

```ini
CONTRACT_SEMANTICS_MATCH = NO__SOURCE_SEMANTICS_MISMATCH_FOR_HISTORICAL_REPLAY
SOURCE_SEMANTICS_MISMATCH = YES__HISTORICAL_REPLAY
```

历史方向到此停止，不再扩大验证。

## 3. 官方来源身份与证据完整性

### 3.1 已取得原件

S0A `manifest.json` 的 31 个文件已逐件复核：**31/31 字节数和 SHA-256 一致，0 不一致**。三份按代码 PDF 的独立复核结果：

| 报告期 | 页面日期 | 页数 | 字节 | 唯一代码 | SHA-256 | PDF 创建时间 | HTTP Last-Modified |
|---|---:|---:|---:|---:|---|---|---|
| 2025H1 | 2025-09-30 | 114 | 4,626,417 | 5,413 | `b622b76b96d59611db36b01888cf6afd8cd711c5753a19ab8547e74bb0bb8228` | 2025-09-29 08:23:17 +08 | 2026-03-27 12:14:12 GMT |
| 2025H2 | 2026-04-03 | 158 | 772,144 | 5,463 | `b1d0140572b20de11cd62ca478edb4da6e229928b216116df6345b3c2e461f58` | 2026-03-31 09:54:43 +08 | 2026-04-03 06:49:48 GMT |
| 2026H1 | 2026-09-30 | 160 | 782,339 | 5,521 | `1f1862ae2199a82a3a35c62f16a7d576120bca97f3de608989c8897df9b6c8a6` | 2026-09-28 11:21:41 +08 | 2026-09-30 06:19:30 GMT |

另：

- 2025H1 按行业 PDF：129 页，1,935,787 字节，5,413 个唯一代码；与按代码 PDF 的集合**完全相等**（双向差 0）。
- 北交所新旧代码对照表：6 页，190,213 字节，PDF 文本 **248 行**；保存的 `capco-bse-code-map.json` 只有 **246 行**，缺少 seq 174（`*ST 广道` 839680→920680）和 seq 187（`*ST 云创` 835305→920305）。这是 S0A 证据的解析遗漏，不是官方映射缺失。
- 三份 PDF 每期内部均无重复代码；每行都有门类和大类；所有制造业行都有次类，所有非制造业行次类为空；19 个门类、10 个次类、83 个大类的代码集合和代码→名称映射在三期间**完全一致**。

### 3.2 身份结论

**三个 PDF 内部一致、跨版本代码体系一致；但这只是系列内一致性，不是正式 taxonomy 版本证明。**

## 4. Taxonomy 身份与版本

### 4.1 2023 指引

- 保存的 `capco-taxonomy-guide.js` 日期 `2023-05-21`，标题《中国上市公司协会上市公司行业统计分类指引》，来源中国上市公司协会。
- **保存正文只有第一章总则第 1–3 条**；没有完整分类表、没有标准编号、没有版本年份。第一条引用《国民经济行业分类》，但未写明采用哪一版。
- 保存的 2023 指引正文没有出现“门类/次类/大类”的字段定义或完整分类表，因此**无法核对 PDF 字段与 2023 指引的正式一致性**；只能确认 PDF 内部三级字段自洽。
- PDF 使用“门类/次类/大类”三级字段；代码形状与大类名称在观察范围内与《国民经济行业分类》2017 版的大类体系相容，但 **PDF 本身没有印出标准名称、年份或版本号**，不能据此宣称正式一致。

### 4.2 2024 标准线索

保存的站点 bundle 中存在 2024-11-22 中国证监会文章条目《中国证监会发布〈上市公司行业统计分类与代码〉等 8 项金融行业标准》（`xhdt/jgyw/76d7c0c0e45d420b823b093ca3ec63c9.js`），但**文章正文未保存**。因此无法判断：

- 该 2024 标准是否替代或补充 2023 CAPCO 指引；
- 2025H1/2025H2/2026H1 PDF 使用的是 2023 指引还是 2024 标准；
- 次类 CA–CJ 的正式定义和版本归属。

### 4.3 结论

```ini
TAXONOMY_VERSION_STATUS = UNRESOLVED__PDF_NO_STANDARD_NAME_OR_YEAR; 2023_GUIDE_SAVED_AS_CHAPTER_1_ARTICLES_1_3_ONLY; 3_PDFS_IDENTICAL_CODE_SYSTEM; 2024_CSRC_STANDARD_ANNOUNCEMENT_BODY_NOT_SAVED; LEVEL_NOT_FROZEN_BY_CONTRACT
```

**不能仅凭 PDF 排版相似或代码集合相同就认定版本一致。** 目前只能说“三份 CAPCO PDF 使用同一套可观察代码体系”，不能说“已证明为 Mishi 合同要求的正式 taxonomy/version”。

## 5. 历史时间语义账本

| 版本 | 统计期间 | 页面发布日 | PDF 创建时间 | HTTP Last-Modified | 当前 SHA-256 | 最早可佐证的公开日期（非独立证明） | 已证实分类生效时间 |
|---|---|---|---|---:|---:|---|---:|---|
| 2025H1 | 2025 年上半年 | 2025-09-30 | 2025-09-29 08:23:17 +08 | **2026-03-27 12:14:12 GMT** | `b622…8228` | **无；当前字节对象时间 2026-03-27，页面日不适用于当前字节** | 未声明 |
| 2025H2 | 2025 年下半年 | 2026-04-03 | 2026-03-31 09:54:43 +08 | 2026-04-03 06:49:48 GMT | `b1d0…1f58` | 2026-04-03（页面日与对象时间相符；无独立存档） | 未声明 |
| 2026H1 | 2026 年上半年 | 2026-09-30 | 2026-09-28 11:21:41 +08 | 2026-09-30 06:19:30 GMT | `1f18…c8a6` | 2026-09-30（页面日与对象时间相符；无独立存档） | 未声明 |

### 5.1 2025H1 后续修改风险（重点）

2025H1 的当前 PDF：

- 页面日期是 2025-09-30，PDF CreationDate 是 2025-09-29 08:23:17 +08；
- **HTTP Last-Modified 是 2026-03-27 12:14:12 GMT**；
- 当前 PDF URL 路径是 `/file/202603/...`，文章数据中的链接也指向 2026-03 路径；
- 同页按行业 PDF 和北交所对照表的 Last-Modified 同为 2026-03-27；
- PDF 内部 ModDate 仍为 2025-09-29 08:23:17 +08，HTTP 对象时间却是 2026-03-27；二者不一致，不能证明文件内容变过，也不能证明没变过，只能说明当前对象不能作为 2025-09-30 的直接时间证据；
- 2025H1 PDF 的 Producer 是 Microsoft Excel 2016，2025H2/2026H1 是 iText Core 8.0.0；生成链不同，这不是内容变更的证明，但进一步说明不能把 2025H1 的创建元数据当作当前字节的首次公开时间；
- HTTP Last-Modified 只给出最后一次对象修改时间，没有历史版本链；不能排除 2026-03-27 之前还有更早的修改；
- 没有 2025-09-30 原始字节、旧 SHA-256 或独立归档。

因此：**页面日期、PDF 创建时间、HTTP 修改时间不能互相替代。** 当前字节不能证明在 2025-09-30 已可取得；也不能以当前 PDF 的内容反推其在 2025-09-30 已经可知。当前内容的对象时间是 2026-03-27，但这仍不能证明该日已公开。2025H1 的原始字节版本 **不能证明**，这是已确认的证据限制。

### 5.2 2025H2/2026H1

2025H2 和 2026H1 的页面日期、PDF 创建时间、HTTP Last-Modified 基本对齐；这提高了“当前字节就是发布版本”的可信度，但仍没有独立存档或第三方时间戳，**first-known 仍未被独立证明**。

### 5.3 生效时间

三份 PDF 和文章数据均**未声明分类生效日**。标题中的“2025 年上半年/下半年/2026 年上半年”是统计期间，不是成员生效日；页面日期是发布日，也不是生效日。分类可能在期末生效，也可能在发布日生效，或按迁移事件分批生效；来源没有说明。

```ini
KNOWN_AT_QUALIFICATION = NOT_PROVEN__2025H1_CURRENT_BYTES_OBJECT_TIME_2026-03-27_NO_ARCHIVE; 2025H2_2026H1_PAGE_DATE_AND_OBJECT_TIME_CORROBORATED_ONLY
EFFECTIVE_DATE_QUALIFICATION = NOT_STATED__ALL_THREE_VERSIONS
HISTORICAL_WINDOW_COVERAGE = SEMIANNUAL_BRACKET_ONLY__NO_DAILY_EFFECTIVE_OR_KNOWN_AT
```

## 6. 成员身份与完整性

### 6.1 每期数量与合同子集

| 版本 | 唯一代码 | 合同普通 A 股 | 沪 A | 深 A | B 股 | 北交所 | CDR 689009 | 302132 | 制造业行 | 空次类 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025H1 | 5,413 | 5,136 | 2,274 | 2,862 | 8 | 267 | 1 | 1 | 3,686 | 1,727 |
| 2025H2 | 5,463 | 5,169 | 2,294 | 2,875 | 7 | 285 | 1 | 1 | 3,735 | 1,728 |
| 2026H1 | 5,521 | 5,194 | 2,306 | 2,888 | 7 | 318 | 1 | 1 | 3,801 | 1,720 |

- 每期无重复代码；合同普通 A 股、B 股、北交所、CDR、302132 的分解相加等于该期唯一代码总数。
- 每期都有门类和大类；**PDF 内没有“无行业/未分类”行**，也没有未分类分母。无法判断未被收录的公司是被归入其他类别还是被排除。
- 制造业 3,686/3,735/3,801 行全部有次类；非制造业行全部无次类；这是层级一致性，不是未分类。

### 6.2 北交所代码映射（S0A 更正）

- 官方对照表文本 248 行；保存 JSON 246 行，漏掉 seq 174/187。
- 2025H1 PDF 中 242 个旧北交所代码（43/83/87 前缀）**242/242 均可映射**；S0A 的“240/242、2 个未映射”是 JSON 解析遗漏造成的，不是来源缺陷。
- 2025H1 另有 25 个 `92xxxx` 新代码；其中 6 个映射表新代码也在 2025H1 出现，19 个不在该对照表新代码集合中，因而没有可用的旧→新映射记录。它们可能是直接以 920 代码上市的证券，但原因未逐一证明；不应直接称为“无法识别”。
- 6 个映射表旧代码（430489、830799、831445、833819、834682、839167）在 2025H1 已使用对应的新代码，属于正常换码。
- 因此修正后的 2025H1→2025H2 归一化集合差是 **+60/−10**，不是 S0A 的 +61/−11；差异正是 835305→920305 被正确匹配、839680→920680 仍退出。

### 6.3 三期间的新增、退出和分类变化

使用修正后的 248 行映射归一化：

| 对比 | 新增 | 退出 | 共同 | 完全一致 | 门类变化 | 大类变化（含门类变化） | 同门类下大类变化 | 次类变化 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025H1→2025H2 | 60 | 10 | 5,403 | 5,397 | 3 | 6 | 3 | 4 |
| 2025H2→2026H1 | 75 | 17 | 5,446 | 5,401 | 19 | 45 | 26 | 28 |
| 2025H1→2026H1 | 135 | 27 | 5,386 | 5,335 | 22 | 51 | 29 | 32 |

可核示例（均为版本间实际行差异，不是由今日成员反推）：

- `002310`：2025H1 `N 水利、环境和公共设施管理业/77` → 2025H2、2026H1 `D 电力、热力、燃气及水生产和供应业/44`。
- `600052`：2025H1 `R 文化、体育和娱乐业/87` → 2025H2、2026H1 `L 租赁和商务服务业/72`。
- `603007`：2025H1、2025H2 `E 建筑业/48` → 2026H1 `C 制造业/CG/36`。
- `600575`：2025H1、2025H2 `G 交通运输、仓储和邮政业/55` → 2026H1 `D 电力、热力、燃气及水生产和供应业/44`。

这些差异证明“版本间发生了什么”，但**没有迁移生效日、没有首次可知时间、没有修订公告链**，不能据此重建任意历史日的成员集合，也不能证明变更在某一日生效。

### 6.4 独立证券清单对账

可用的独立官方清单只有 DR01 2026-10-16 和 DR03 2026-10-22；它们**不是** CAPCO 三个报告期的同日分母，不能用于证明 2025H1/2025H2/2026H1 的完整性。可用于身份/生命周期核对的有限结论：

- DR01 原始 5,226（沪 2,320 + 深 2,906）；排除 CDR 689009 后 5,225。
- DR03 原始 5,225（沪 2,318 + 深 2,907）；排除 689009 和 302132 后 5,223。
- DR01 独有 `601059`、`601198`（均于 2026-10-19 终止上市）；DR03 独有 `301718`（2026-10-22 上市）；`689009`、`302132` 在两边原始清单都存在，只是排除规则不同。
- 2026H1 CAPCO 合同普通 A 股 5,194；与 DR03 2026-10-22 当前候选 5,223 的交集 5,192，覆盖率 99.41%，但**不等于完整性**。
- DR03 当前独有 31 只：29 只上市日 > 2026-06-30；**2 只上市日在 H1 结束前**却不在 CAPCO 2026H1：`001399` 惠科股份（2026-06-26）、`688797` 臻宝科技（2026-06-24）。CAPCO 的收录截止日未声明，原因 UNKNOWN。
- CAPCO 2026H1 独有 2 只：`601059`、`601198`，均于 2026-10-19 退市。当前消费必须按生命周期剔除，不能仅凭 CAPCO 行业表判断当前成员。
- `689009` 九号公司-WD（CDR）和 `302132` 中航成飞（DR03 划为普通 A 股代码族之外）在 CAPCO 和两边原始清单中都存在；CAPCO 不标注 CDR/板块类型，消费方必须用代码族规则排除。PDF 没有交易所/板块列，`security_id=exchange:ticker` 只能由代码族推断。

因此，2025H1/2025H2/2026H1 的历史完整性证据状态为 `INCOMPLETE_EVIDENCE`，不得声明 `FULL_COVERAGE`。

### 6.5 边界样本

| 代码 | CAPCO 三版本 | DR01 2026-10-16 | DR03 2026-10-22 | 结论 |
|---|---|---|---|---|
| `601059` 信达证券 | J/67 三版一致 | 在 | 当前不在；退市清单在（2026-10-19） | 版本间行业无变化；当前成员身份需生命周期剔除 |
| `601198` 东兴证券 | J/67 三版一致 | 在 | 当前不在；退市清单在（2026-10-19） | 同上 |
| `301718` N通则康威 | 三版都无 | 不在 | 在（2026-10-22 上市） | 上市日差异，不是 CAPCO 分类错误 |
| `689009` 九号公司-WD | C/CH/39→C/CH/39→C/CG/37 | 在（STAR） | 原始在，候选排除（CDR） | 合同排除；CAPCO 不标注 CDR |
| `302132` 中航成飞 | C/CH/39→C/CH/39→C/CG/37 | 在（深） | 原始在，候选排除（普通 A 股代码族外） | 合同口径差异；CAPCO 不标注板块 |
| `001399` 惠科股份 | 三版都无 | 在（2026-06-26 上市） | 在 | **H1 结束前上市却未收录；收录截止日 UNKNOWN** |
| `688797` 臻宝科技 | 三版都无 | 在（2026-06-24 上市） | 在 | **同上** |

```ini
UNIVERSE_IDENTITY_STATUS = BOUNDED_IDENTITY_OK__UNIQUE_6_DIGIT_CODES; NO_DUPLICATES; EXCHANGE_INFERRED_BY_CODE_FAMILY; BSE_MAP_248_TEXT_ROWS_246_JSON_ROWS_CORRECTED; 242/242_2025H1_OLD_CODES_MAPPED; 19_920_CODES_NOT_IN_MAP_NEW_SET; SAME_DAY_COMPLETENESS_UNPROVEN
CURRENT_MEMBERSHIP_COVERAGE = PARTIAL__2026H1_5194_CONTRACT_A; 5192/5223_DR03_2026-10-22_COMMON; 31_DR03_ONLY (29_POST_H1, 001399_688797_PRE_H1_END); 2_CAPCO_ONLY_DELISTED; NO_UNCLASSIFIED_DENOMINATOR
HISTORICAL_MEMBERSHIP_COVERAGE = NOT_QUALIFIED__3_SEMIANNUAL_SNAPSHOTS_BRACKET_ONLY; NOT_DAILY_PIT; 2025H1_FIRST_KNOWN_UNPROVEN_OBJECT_TIME_2026-03-27; NO_EFFECTIVE_OR_MIGRATION_DATES
```

## 7. 按消费场景分别裁决

### A. 当前全市场扫描

**不合格（PARTIAL / NOT_PASSED）。** 2026H1 是任务日之前最新的半年快照，但：

- 合同普通 A 股 5,194；DR03 2026-10-22 当前候选 5,223；交集 5,192，31 只当前证券没有 CAPCO 行业；其中 2 只在 H1 结束前已上市（001399、688797），证明 CAPCO 2026H1 不是“截至 H1 结束的全部上市证券”。
- 2 只已退市证券（601059、601198）仍在 CAPCO 2026H1；当前消费必须另行剔除。
- 没有未分类分母、没有显式总数、没有交易所/板块列；taxonomy 版本、生效日和 known_at 均未解决。
- 按现有半年节奏，下一次预计在 2027 年 4 月（2026H2）；当前快照会在数月内持续滞后于新上市证券。若合同要求“当前完整行业成员”，CAPCO 不能单独满足。

可以将 2026H1 视为**有界滞后快照**：5,192 只共同证券有 CAPCO 行业；31 只当前证券必须标 UNKNOWN 或剔除，2 只退市证券必须剔除。但这是对合同分母的改变，需 Owner 明确接受，不能由执行 Agent 自行决定。

### B. 历史回放

**SOURCE_SEMANTICS_MISMATCH / NOT_PASSED。** 半年度快照不是历史日有效成员档案：

- 没有生效日、没有 known_at、没有迁移/修订生效日；不能用半年快照插值出逐日行业归属。
- 诊断窗口起点 2025-09-09 早于 2025H1 发布日 2025-09-30；窗口终点 2026-09-22 早于 2026H1 发布日 2026-09-30；2025H1 当前字节对象时间是 2026-03-27，仍不能证明更早公开。窗口首尾都没有可证明的当日/当时已知快照。
- 即使接受“最新已发布快照”这种宽松语义，2025H1 在 2025-10-09…2026-03-26 的已知性仍不能证明；严格语义下则直接失败。
- 2025H1 的 PIT 缺口、半年度粒度、缺少迁移日期、缺少同日独立分母，均为结构性或已确认的阻断，不是再取一份 PDF 就能修复。

### C. 哪些日期、证券及字段得到有界证明

- **日期**：2025H1 页面日 2025-09-30、2025H2 页面日 2026-04-03、2026H1 页面日 2026-09-30；三者是发布页日期，不是生效日或 known_at。2025H1 当前字节对象时间 2026-03-27，仍不能证明其更早公开；2025H2/2026H1 只有页面日与对象时间相符的佐证。
- **证券**：5,413/5,463/5,521 个唯一 6 位代码；合同普通 A 股 5,136/5,169/5,194；每期无重复；B 股、北交所、CDR、302132 的边界可分解。
- **字段**：代码、简称、门类代码/简称、次类代码/简称（制造业可选）、大类代码/简称。没有交易所、板块、上市/退市状态、生效日、known_at、未分类分母、总数。
- **跨版本**：三份 PDF 使用同一套 19/10/83 代码体系；代码→名称映射一致；新增/退出/分类变化可按版本观察，但不能指定生效日。
- **当前对账**：2026H1 与 DR03 2026-10-22 的 5,192 只交集、31 只 DR03 独有、2 只 CAPCO 独有，已逐只核对生命周期日期；这是有界身份证据，不是完整分母证明。

### D. 来源自身的结构性限制

1. **半年度快照**，不是逐日/逐事件成员档案；下一个版本要等约半年。
2. **无生效日、无 known_at、无迁移生效日、无修订公告链**。
3. **无未分类分母、无显式总数、无交易所/板块列**；A/B/北交所/CDR 只能靠代码族推断。
4. 新上市证券在下一个半年报告前可能没有 CAPCO 行业；001399/688797 证明即使 H1 结束前上市也可能未收录。
5. 2025H1 当前字节被 2026-03 路径和 Last-Modified 覆盖，原始 2025-09-30 字节不可证明。
6. 退市证券不会在 CAPCO 表中标记退市日；当前消费必须依赖另一个生命周期源。

### E. 只是证据尚未取得的缺口

1. 2023 指引完整分类表、标准编号和版本年份；2024-11-22《上市公司行业统计分类与代码》正文及其与 2023 指引的关系。
2. 2025H1 在 2025-09-30 的原始字节或独立归档；当前字节与原始版本是否相同。
3. 三个报告期的官方收录截止日、成员生效日、known_at、分类修订/迁移公告。
4. 2025H1/2025H2/2026H1 各自同日的独立官方证券分母。
5. 001399、688797 未收录的具体原因；920680/920305 的退市/换码时间链；19 个直接 920 代码的身份清单。
6. 2025H2/2026H1 的按行业 PDF（本轮只保存了 2025H1 的按行业 PDF），无法做同版本双向核对。
7. 最终 S07 `s/e` 绑定；诊断窗口不是 Owner 已批准的商品窗口。

这些缺口中有一些可以通过更多官方材料补齐；但在半年度语义、无生效日/known_at、无未分类分母这三项结构性限制下，即使补齐也不能把 CAPCO 变成逐日 PIT 来源。

### 7.1 本轮实际执行的只读验证

- 使用 `.venv\Scripts\python.exe -X utf8 -B`，`pypdf 6.16.2` 读取三份 PDF 全部页，`openpyxl 3.1.5` 读取 DR01/DR03 XLSX；未安装新依赖、未联网、未修改生产代码。
- S0A `manifest.json` 31 个文件逐件 SHA-256 与字节数复核：31/31 一致，0 不一致。
- 三份按代码 PDF 逐页提取，唯一代码 5,413/5,463/5,521；2025H1 按行业 PDF 与按代码 PDF 双向集合差 0。
- 三份 PDF 字段/层级一致性：19 门类、10 次类、83 大类；制造业行全部有次类，非制造业行全部无次类；代码→名称映射跨三版一致。
- 北交所对照表文本 248 行；修正保存 JSON 的 246 行遗漏；2025H1 旧代码 242/242 映射。
- DR01 2026-10-16 SH JSON + SZ XLSX、DR03 2026-10-22 原始 JSON/XLSX 逐只集合比较；601059/601198/301718/689009/302132/688797/001399 逐只核对。
- `verification.json` 通过 JSON 解析；报告 INI 块与 JSON 决策字段逐项一致。

### 7.2 Findings 分类

| 分类 | 本轮判定 |
|---|---|
| `CONFIRMED_DEFECT` | S0A `capco-bse-code-map.json` 只有 246 行，官方 PDF 文本 248 行，漏 seq 174/187；由此 S0A 的“240/242 映射”和“2025H1→2025H2 +61/−11”应更正为 242/242 和 +60/−10。 |
| `UNRESOLVED_RISK` | taxonomy 正式版本、2025H1 原始字节、三版本生效日/known_at、同日独立分母、001399/688797 收录截止日、920680/920305 生命周期、2025H2/2026H1 按行业 PDF 未保存、S07 精确 s/e 未绑定。 |
| `SPECULATIVE_CONCERN` | 不能仅凭“CAPCO 是官方来源”或“代码集合相同”推断满足冻结 taxonomy/PIT 合同；也不能仅凭 99.41% 覆盖率推断完整。 |
| `FUTURE_ENHANCEMENT` | 本轮不建设解析器、数据库、公共 API、历史回填、付费源或下一阶段；任何此类工作须另行授权。 |

## 8. 最终输出

```ini
CURRENT_DECISION = STOP
SOURCE_QUALIFICATION = PARTIAL
CONTRACT_SEMANTICS_MATCH = NO__SOURCE_SEMANTICS_MISMATCH_FOR_HISTORICAL_REPLAY; CURRENT_SCAN_PARTIAL_ONLY
SOURCE_SEMANTICS_MISMATCH = YES__HISTORICAL_REPLAY
CURRENT_SCAN = PARTIAL_NOT_PASSED__5192/5223_COMMON_31_MISSING_NO_UNCLASSIFIED_DENOMINATOR
HISTORICAL_REPLAY = SOURCE_SEMANTICS_MISMATCH__NOT_PASSED
TAXONOMY_VERSION_STATUS = UNRESOLVED__PDF_NO_STANDARD_NAME_OR_YEAR; 2023_GUIDE_SAVED_AS_CHAPTER_1_ARTICLES_1_3_ONLY; 3_PDFS_IDENTICAL_CODE_SYSTEM; 2024_CSRC_STANDARD_ANNOUNCEMENT_BODY_NOT_SAVED; LEVEL_NOT_FROZEN_BY_CONTRACT
KNOWN_AT_QUALIFICATION = NOT_PROVEN__2025H1_CURRENT_BYTES_OBJECT_TIME_2026-03-27_NO_ARCHIVE; 2025H2_2026H1_PAGE_DATE_AND_OBJECT_TIME_CORROBORATED_ONLY
EFFECTIVE_DATE_QUALIFICATION = NOT_STATED__ALL_THREE_VERSIONS
CURRENT_MEMBERSHIP_COVERAGE = PARTIAL__2026H1_5194_CONTRACT_A; 5192/5223_DR03_2026-10-22_COMMON; 31_DR03_ONLY (29_POST_H1, 001399_688797_PRE_H1_END); 2_CAPCO_ONLY_DELISTED; NO_UNCLASSIFIED_DENOMINATOR
HISTORICAL_MEMBERSHIP_COVERAGE = NOT_QUALIFIED__3_SEMIANNUAL_SNAPSHOTS_BRACKET_ONLY; NOT_DAILY_PIT; 2025H1_FIRST_KNOWN_UNPROVEN_OBJECT_TIME_2026-03-27; NO_EFFECTIVE_OR_MIGRATION_DATES
UNIVERSE_IDENTITY_STATUS = BOUNDED_IDENTITY_OK__UNIQUE_6_DIGIT_CODES; NO_DUPLICATES; EXCHANGE_INFERRED_BY_CODE_FAMILY; BSE_MAP_248_TEXT_ROWS_246_JSON_ROWS_CORRECTED; 242/242_2025H1_OLD_CODES_MAPPED; 19_920_CODES_NOT_IN_MAP_NEW_SET; SAME_DAY_COMPLETENESS_UNPROVEN
HISTORICAL_UNIVERSE_EVIDENCE = INCOMPLETE_EVIDENCE__NO_SAME_DAY_INDEPENDENT_DENOMINATOR
CURRENT_UNIVERSE_EVIDENCE = INCOMPLETE_EVIDENCE__NO_SAME_DAY_DENOMINATOR_FOR_2026H1
CONFIRMED_BLOCKERS = SEMIANNUAL_ONLY_VS_DAILY_EFFECTIVE_KNOWN_AT; NO_EFFECTIVE_DATE; NO_KNOWN_AT; 2025H1_CURRENT_BYTES_OBJECT_TIME_2026-03-27_ORIGINAL_ARCHIVE_MISSING; NO_UNCLASSIFIED_DENOMINATOR; NO_EXPLICIT_TOTAL_OR_EXCHANGE_COLUMN; CURRENT_2026H1_MISSING_31_DR03_CODES; 001399_688797_PRE_H1_END_UNEXPLAINED; TAXONOMY_VERSION_UNRESOLVED; NO_SAME_DAY_INDEPENDENT_UNIVERSE
UNRESOLVED_EVIDENCE = 2023_GUIDE_FULL_TABLE_AND_VERSION; 2024_CSRC_STANDARD_BODY_AND_RELATION; 2025H1_ORIGINAL_2025-09_BYTES_OR_ARCHIVE; OFFICIAL_CUTOFF_EFFECTIVE_AND_KNOWN_AT; SAME_DAY_UNIVERSES_FOR_3_SNAPSHOTS; 001399_688797_INCLUSION_REASON; 920680_920305_LIFECYCLE; 2025H2_2026H1_BY_INDUSTRY_PDFS; EXACT_S07_S_E_BINDING
SCOPE_DEVIATION = NONE
NEXT_MINIMAL_ACTION = OWNER_REVIEW_OF_SOURCE_SEMANTICS_MISMATCH_AND_CURRENT_GAP__REQUIRE_CONTRACT_CHANGE_OR_ARCHIVAL_EFFECTIVE_KNOWN_AT_EVIDENCE__NO_IMPLEMENTATION
OWNER_ACCEPTANCE_REQUIRED = YES

DR03_CURRENT_GATE = NOT_PASSED
DR03_HISTORICAL_GATE = NOT_PASSED
IMPLEMENTATION_AUTHORIZED = NO
RELEASE_AUTHORIZED = NO
```

## 9. 交接摘要

- 当前阶段/步骤：DR03-S1 CAPCO 历史行业成员有界资格验证完成，等待 Owner Review。
- HEAD：`a2072d0c722d7f7935309a15cef945bc8ecbef08`；origin/main：`5584f5fcacccef9a9531a7a32b8463ea6771d312`；tracked/staged 无修改；本轮只新增本报告和 `verification.json`。
- Gate 裁决：DR03 当前与历史均 `NOT_PASSED`；`SOURCE_SEMANTICS_MISMATCH=YES`（历史）；当前仅为 `PARTIAL`，5,192/5,223，31 只缺失。
- 未解决阻断：半年度 vs 逐日/事件语义、无生效日/known_at、2025H1 当前字节对象时间 2026-03-27 且原始归档缺失、无未分类分母、无显式总数/交易所列、2026H1 缺 31 只当前证券、001399/688797 收录截止日未知、taxonomy 版本未定、无同日独立分母。
- 建议下一动作：Owner 审阅并决定是否接受“有界滞后半年快照”合同变更，或要求归档/生效/known_at 证据；不进入实现、不开始下一阶段。
- 本报告不声称下一阶段已授权。

