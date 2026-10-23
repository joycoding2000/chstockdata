# DR03-S0A CAPCO 官方历史行业分类档案最小证据复核

日期：2026-10-23，Asia/Shanghai。性质：只读来源调查与 Owner Review；**未进入实现、未修改 runtime、未建解析器或数据库、未改 Mishi 范围**。

## 1. 基线与边界

| 项目 | 实际值 |
|---|---|
| 本地 HEAD | `a2072d0c722d7f7935309a15cef945bc8ecbef08` |
| origin/main | `5584f5fcacccef9a9531a7a32b8463ea6771d312` |
| 关系 | 本地领先 1、落后 0；tracked 工作区干净；94 个 untracked 条目 |
| 本轮网络范围 | 仅 `capco.org.cn` / `sp.capco.org.cn` 官方页面与文件；无镜像、无第三方搜索、无付费源 |
| 本轮产物 | 本报告与 `docs/audits/evidence/2026-10-23-dr03-s0a-capco/` 原始证据 |
| 未执行 | 全池历史回放、Mishi 策略、生产解析器、数据库、接口或 runtime 修改 |

复用的上位证据：S07 免费供给决定性筛查、DR01 当前来源资格报告、DR01 原始官方导出与 DR02–DR06 差距报告。DR01 原始文件位于 `D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18/evidence/reused/`，本轮只读。

## 2. CAPCO 发布页与实际取得路径

提供的 URL：

`https://www.capco.org.cn/pub/zgssgsxh/xhgg/hyfl/hyfljg/202509/20250930/j_2025093014371200017592143530187679.html`

实际响应为 **SPA 外壳**（HTTP 200，2,371 字节，SHA-256 `0d21e9c9d7553350c41b06a9770bed8e475c6f72eff784791651b71fb88992e0`），不直接含正文。正文数据由同一官方站点提供：

- 2025 年上半年文章数据：`https://www.capco.org.cn/dataFile/zsxfb/hyfl/hyfljg/29adc9e66d844d6fba0001bb2cdc529c.js`
- 文章 `date=2025-09-30`，标题 `2025年上半年上市公司行业分类结果`，1,857 字节，SHA-256 `b408b41fd2c932c74e9704211ad82117458035483c933f722fca3ba85d0e1b8b`。
- 该数据文件由同一官方“行业分类结果”栏目菜单定位；其 `date`/`title` 与提供页面一致，页面本身未直接内嵌 PDF 链接。
- 文章正文含三个 PDF 链接：按股票代码排序、按行业排序、北交所新旧代码对照表。

由此确认：**具名官方来源存在，且不是只有文档描述；已取得真实 PDF 原件。** 这不是 Qualified，只是可进入下一次有界验证的正向实物证据。

## 3. 已取得原件

| 报告期 | 页面发布日 | PDF 文件 | 字节 | SHA-256 | PDF 创建时间（元数据） | HTTP Last-Modified | 页数 | 唯一证券代码 |
|---|---:|---|---:|---|---|---|---:|---:|
| 2025H1 | 2025-09-30 | `capco-pdf-by-code.pdf` | 4,626,417 | `b622b76b96d59611db36b01888cf6afd8cd711c5753a19ab8547e74bb0bb8228` | 2025-09-29 08:23:17 +08 | 2026-03-27 12:14:12 GMT | 114 | 5,413 |
| 2025H2 | 2026-04-03 | `capco-pdf-2025H2-by-code.pdf` | 772,144 | `b1d0140572b20de11cd62ca478edb4da6e229928b216116df6345b3c2e461f58` | 2026-03-31 09:54:43 +08 | 2026-04-03 06:49:48 GMT | 158 | 5,463 |
| 2026H1 | 2026-09-30 | `capco-pdf-2026H1-by-code.pdf` | 782,339 | `1f1862ae2199a82a3a35c62f16a7d576120bca97f3de608989c8897df9b6c8a6` | 2026-09-28 11:21:41 +08 | 2026-09-30 06:19:30 GMT | 160 | 5,521 |

另取得：

- 2025H1 按行业排序 PDF：`capco-pdf-by-industry.pdf`，129 页，1,935,787 字节，SHA-256 `caa7d96b05ff9ec2165aa3b4cb69edd69c8b1a1a0f99198c4cfcf85727f1d7bc`。
- 北交所新旧代码对照表：`capco-pdf-bse-code-map.pdf`，6 页，190,213 字节，SHA-256 `f85a6691a74a8c7e4d2bb838277161b9d0496f52cc66ddde4ba0211153401c3d`。
- 官方分类指引文章数据：`capco-taxonomy-guide.js`，1,948 字节，SHA-256 `b7ad99d947fad5b71b3464d55d19530012bd91ad5465574d82846ee519b4f584`。

完整请求账本：`evidence/2026-10-23-dr03-s0a-capco/requests.json`。共 21 次官方请求，全部 HTTP 200，0 显式重试，累计读取 10,191,206 字节；其中 9 次返回 SPA 外壳（含发布页本身，其余为路径探测），不是数据失败，也未使用镜像。

## 4. 文件内实际字段与成员分母

按股票代码排序 PDF 的列：

`上市公司代码 | 上市公司简称 | 门类代码 | 门类简称 | 次类代码 | 次类简称 | 大类代码 | 大类简称`

2025H1 实测：

- **5,413 个唯一 6 位证券代码**，按代码行逐行计数无重复。
- 按行业排序 PDF 也是 **5,413 个唯一代码**，与按代码排序 PDF 的集合完全相等（`code_only=0`、`industry_only=0`）。
- 每行都有门类代码和大类代码；未发现无门类/无大类的“未分类”行。次类为空在部分门类中是合法层级缺失，不等同未分类。
- 代码前缀构成：`60` 1,688、`00` 1,483、`30` 1,380、`68` 587、`83` 173、`87` 54、`92` 25、`43` 15、`20` 5、`90` 3。即包含沪、深、北交所及少量 B 股；**PDF 没有显式“交易所”列**，交易所只能由代码号段推断，不能当作文件字段。
- **没有显式“合计 5,413 家”字样**；5,413 是由逐行代码去重并与按行业 PDF 交叉核验得到，证明两份 PDF 内部一致，不是经交易所全量对账的外部完整性证明。
- PDF 没有显式“未分类”组；每一条被收录行都有门类。若存在未分类上市公司，无法仅凭 PDF 判断其被归入其他类别还是被排除，需与交易所全量清单对账。

2025H2、2026H1 按代码 PDF 的结构相同，唯一代码分别为 5,463、5,521。三者均包含北交所代码；2025H1 同时包含旧北交所代码（43/83/87）和 25 个 `92xxxx`，2025H2/2026H1 以 `92xxxx` 为主，因此不能直接做原始集合差。

## 5. Taxonomy 身份

- 同一官方“行业分类”栏目有《中国上市公司协会上市公司行业统计分类指引》，页面日期 **2023-05-21**。
- PDF 使用 **门类 / 次类 / 大类** 三级代码；2025H1 实测 83 个不同大类代码。
- **PDF 本身没有印出标准名称、标准年份或版本号**；指引文章页也只保存了总则前三条，没有完整分类表或版本声明。因此 taxonomy 身份目前是“CAPCO 指引 + PDF 代码形态”的候选证据，不是已冻结的标准版本。

## 6. 发布时间、生效时间与首次可知时间

2025H1 的关键时间事实：

| 时间 | 值 | 能证明什么 |
|---|---|---|
| 页面文章日期 | 2025-09-30 | 官方发布页标注日 |
| PDF CreationDate | 2025-09-29 08:23:17 +08 | 文档内容生成时间早于页面日期 |
| 报告期（页脚） | 2025 年上半年 | 统计期间，不是成员生效日 |
| HTTP Last-Modified | 2026-03-27 12:14:12 GMT | 当前服务器对象最后修改时间 |
| PDF URL 路径 | `/file/202603/...` | 当前文件所在批次为 2026-03 |

结论：**发布日、PDF 创建时间、报告统计期间、成员实际生效时间、首次可知时间不是同一概念。** 2025H1 当前字节的 HTTP 对象最后修改于 2026-03-27，不能证明这些字节在 2025-09-30 已可取得；`effective date` 与 `known_at` 均未明示。2025H2 与 2026H1 的 PDF 创建时间、页面日期和 HTTP Last-Modified 基本对齐，但同样没有成员生效/首次可知声明。

## 7. 版本链与可观察变化

同一官方“行业分类结果”栏目确认了三个连续半年度版本：

- 2025H1：发布 2025-09-30
- 2025H2：发布 2026-04-03
- 2026H1：发布 2026-09-30

使用 2025H1 页面附带的官方北交所新旧代码对照表（246 行）归一化后：

| 对比 | 原始集合差 | 归一化后集合差 | 门类变化（共同代码） | 同门类下大类变化 |
|---|---:|---:|---:|---:|
| 2025H1 → 2025H2 | +301 / −251 | +61 / −11 | 3 | 3 |
| 2025H2 → 2026H1 | +75 / −17 | +75 / −17 | 19 | 26 |
| 2025H1 → 2026H1 | +375 / −267 | +135 / −27 | 22 | 29 |

可核示例（均为官方版本间实际行差异，不是由今日成员反推）：

- `002310`：2025H1 东方园林 `N 水利、环境和公共设施管理业 / 77`；2025H2、2026H1 东方新能 `D 电力、热力、燃气及水生产和供应业 / 44`。
- `600052`：2025H1 东望时代 `R 文化、体育和娱乐业 / 87`；2025H2、2026H1 `L 租赁和商务服务业 / 72`。
- `603007`：2025H1 `*ST花王 E 建筑业 / 48`；2026H1 `顺景科技 C 制造业 / 36`。
- `600575`：2025H1、2025H2 淮河能源 `G 交通运输、仓储和邮政业 / 55`；2026H1 `D 电力、热力、燃气及水生产和供应业 / 44`。

限制：

- 北交所对照表 246 行中，240/242 个 2025H1 旧代码可匹配；`835305`、`839680` 两个旧代码没有对照行且未出现在后续版本，不能推断其原因。
- 三个版本是**半年度快照**，不是逐日或逐事件变更档案；没有分类修订生效日、没有首次可知时间、没有成员迁移公告链。
- 因此可以观察“版本间发生了什么”，但不能据此重建任意历史日的成员集合，也不能证明变更在某一日生效。

## 8. Mishi 目标窗口覆盖

Mishi S07 目标窗口为 2025-10-09 至 2026-10-22（含 2025-09-30 首次信号及更早预热）。CAPCO 三个半年度版本的时间位置是：

- 2025H1 发布 2025-09-30：窗口起点前的基线候选。
- 2025H2 发布 2026-04-03：窗口中间版本。
- 2026H1 发布 2026-09-30：窗口末端前约 3 周版本。

结论：**可形成半年度包围，但不是窗口内逐日/逐事件成员档案。** 若消费者需要每个交易日或每次迁移的准确成员，CAPCO 现有版本链不足；若 Owner 接受半年度快照加明确区间语义，仍需先解决生效日与首次可知时间。

## 9. DR01 与 DR03 集合差异复核

这不是 CAPCO 的来源资格，而是本轮附带的身份复核。仅比较总数会误判。

| 集合 | 沪 | 深 | 说明 |
|---|---:|---:|---|
| DR01 原始导出（2026-10-16） | 2,320 | 2,906 | 沪含 CDR `689009`；深含 `302132` |
| DR01 排除 CDR 后 | 2,319 | 2,906 | 合计 5,225 |
| DR03 原始当前清单（2026-10-22） | 2,318 | 2,907 | 沪含 `689009`；深含 `302132` |
| DR03 排除 `689009` / `302132` 后 | 2,317 | 2,906 | 候选合计 5,223 |

精确集合差：

- 沪：**DR01 独有 `601059`、`601198`**；DR03 无独有沪代码。两者均在 2026-10-19 终止上市，DR03 已将其放入 `sse-delisted`。
- 深：**DR03 独有 `301718`**；DR01 无独有深代码。该证券上市日为 2026-10-22，名称为 `N通则康威`。
- `689009`、`302132` 在两边原始清单中都存在，只是排除规则不同。
- 因此“两边都是 5,225”是不同排除口径和不同日期的数量巧合；**不能据此认定集合相等**。若按同一排除口径比较，DR01 为 5,224，DR03 为 5,223，差异正是上述三只证券的真实生命周期变化。

## 10. 裁决

**CAPCO 提供了真实、完整、可复核的半年度成员 PDF，且同栏目存在连续三个版本和官方北交所代码对照表。** 这足以提交 Owner 审批一次有界 DR03 资格验证；但不足以免除生效日、首次可知时间、taxonomy 版本和半年度粒度缺口。

```ini
CAPCO_SOURCE_EXISTS = YES
HISTORICAL_DOCUMENT_RETRIEVED = YES
PUBLICATION_AND_EFFECTIVE_TIME = PAGE_DATE_2025-09-30; PDF_CREATED_2025-09-29; HTTP_LAST_MODIFIED_2026-03-27; EFFECTIVE_NOT_STATED; KNOWN_AT_NOT_PROVEN
TAXONOMY_IDENTITY = CAPCO_GUIDE_2023-05-21; PDF_MENLEI_CILEI_DAJIA_CODES; NO_VERSION_YEAR_IN_PDF
HISTORICAL_WINDOW_COVERAGE = SEMIANNUAL_2025H1_2025H2_2026H1_BRACKET; NOT_DAILY; NO_EFFECTIVE_KNOWN_AT
FULL_MEMBERSHIP_EVIDENCE = 5413_UNIQUE_BY_CODE_EQUALS_BY_INDUSTRY; INTERNAL_CONSISTENCY_ONLY; NO_EXPLICIT_TOTAL; UNCLASSIFIED_OMISSION_UNKNOWN; INCLUDES_BSE_AND_B_SHARES
VERSION_CHAIN_EVIDENCE = 3_SEMIANNUAL_FULL_PDFS_PLUS_OFFICIAL_BSE_CODE_MAP; OBSERVED_DIFFS; NO_COMPLETE_CHANGE_ARCHIVE
UNIVERSE_DIFFERENCE = TOTAL_5225_NOT_SET_EQUAL; DR01_ONLY_601059_601198; DR03_ONLY_301718; 689009_302132_IN_BOTH
READY_FOR_BOUNDED_QUALIFICATION = YES
REMAINING_BLOCKERS = EFFECTIVE_KNOWN_AT; TAXONOMY_VERSION; SEMIANNUAL_ONLY; NO_EXPLICIT_TOTAL_OR_EXCHANGE_COLUMN; UNCLASSIFIED_OMISSION_UNKNOWN; 2025H1_BYTES_LAST_MODIFIED_2026-03-27; BSE_2_UNMAPPED_OLD_CODES
NEXT_MINIMAL_ACTION = OWNER_REVIEW_ONE_BOUNDED_CAPCO_QUALIFICATION_ON_3_SEMIANNUAL_PDFS_PLUS_BSE_MAP; REQUIRE_TAXONOMY_VERSION_AND_EFFECTIVE_KNOWN_AT_EVIDENCE; NO_IMPLEMENTATION
DR03_CURRENT_GATE = NOT_PASSED
DR03_HISTORICAL_GATE = NOT_PASSED
IMPLEMENTATION_AUTHORIZED = NO
PUSH_AUTHORIZED = NO
OWNER_REVIEW_REQUIRED = YES
```

## 11. 建议的有界资格验证（仅建议，未执行）

建议 Owner 只批准一次最小验证，不进入实现：

1. 冻结已取得的 2025H1/2025H2/2026H1 按代码 PDF、2025H1 按行业 PDF、北交所对照表；需要时再取两份相邻按行业 PDF。
2. 要求 CAPCO 官方材料明确：taxonomy 名称/版本、报告统计截止日、成员生效日、首次可知时间，以及 2025H1 当前字节与 2025-09-30 发布版本的关系。
3. 以官方北交所对照表归一化后，逐版本核对全量成员、新增/退出/迁移和未分类分母；两只未匹配旧代码单独列为 UNKNOWN。
4. 用同一排除口径复核 DR01/DR03 的集合差异；不得以总数相等替代集合对账。
5. 评估半年度快照是否满足 Mishi 目标窗口；若必须逐日/逐事件，明确记录来源不足并回 Owner CR，不自行回填。
6. 请求上限建议：新的官方 CAPCO 请求不超过 10 次、正文不超过 20 MB、重试不超过 1 次；遇到访问限制即停止，不使用镜像。

## 12. 证据与交接

证据目录：`docs/audits/evidence/2026-10-23-dr03-s0a-capco/`

- `requests.json`：21 次请求的 URL、时间、状态、字节、SHA-256、headers、重定向。
- `summary.json`：三版本计数、集合差、taxonomy/时间事实、请求账本。
- `universe-difference.json`：DR01/DR03 精确集合差与来源。
- `manifest.json`：31 个证据文件的字节与 SHA-256；本地复核 0 不一致。
- `verification.txt`：页数、唯一代码数、按代码/按行业集合一致性和 BSE 映射说明。

交接摘要：

- 当前阶段/步骤：DR03-S0A CAPCO 官方历史分类档案最小证据复核。
- HEAD：`a2072d0c722d7f7935309a15cef945bc8ecbef08`；origin/main：`5584f5fcacccef9a9531a7a32b8463ea6771d312`；tracked 工作树干净，94 个 untracked 条目。
- Gate 裁决：DR03 当前与历史均 `NOT_PASSED`；来源证据 `READY_FOR_BOUNDED_QUALIFICATION=YES`，不是 Qualified。
- 未解决阻断：effective/known_at、taxonomy 版本、半年度粒度、2025H1 当前字节的首次可知、无显式总数/交易所列、2 个未映射北交所旧代码。
- 建议下一动作：Owner 审批一次有界 CAPCO 资格验证；不得自动开始实现或进入下一阶段。
