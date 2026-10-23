# DR01-CURRENT 免费数据能力可行性调查与候选设计

日期：2026-10-19（北京时间）。阶段：**调查完成，停在 Owner Review；来源资格未通过，实施未授权**。

## 1. 结论与版本基线

**现有架构能够容纳这项增量能力；免费来源存在明确的候选技术路径，但本轮不能证明它已经能够满足 DR01-CURRENT。** 唯一尚未解决的来源事实仍是深市指定完成交易日 D 的完整、可追溯停复牌状态。不能据此启动实现或承诺下一版本交付。

本轮发现的关键候选是 BaoStock 官方的指定日全证券状态接口，而非逐股推断成交活动。官方还提供每日全 A 股日线批量接口。两者在文档和已安装 SDK 中均可定位，但本轮两次免费公共节点登录均在接收响应时超时，未取得任何证券状态行。因此结论是 **INSUFFICIENT_EVIDENCE**，不是“免费数据已合格”，也不是“免费来源在技术上绝对不可能”。

| 状态字段 | 结果 |
|---|---|
| CURRENT_VERDICT | INSUFFICIENT_EVIDENCE / BLOCKED_FOR_IMPLEMENTATION；本调查交付可供 Owner Review，DR01 能力尚非验收候选。 |
| CHSTOCKDATA_BASELINE | 正式发行 v0.4.2，提交 17af23fe8183f740150dc01dd877473afe3911b7；远端 main 与本地 HEAD 均为 9543d03310b25be9963227a2a226366de04276ec。 |
| EXISTING_CAPABILITY_COVERAGE | 交易日历、FetchResult/元数据可复用；单股停牌和退市查询部分支持；没有公开的完整 DR01 证券资格快照 API。 |
| DR01_GAPS | 公共全池合同及聚合实现尚缺；唯一剩余来源阻断为深市 D 日全量停复牌事实，含持续停牌及复牌状态。 |
| FREE_SOURCE_FEASIBILITY | BaoStock 有官方明确的批量候选路径，实际完整性、日期准确性和免费节点可用性未通过验证；既有其他来源不能独立补齐。 |
| RECOMMENDED_SOLUTION | 先补足免费 BaoStock 来源资格；通过后才考虑“官方身份/风险/生命周期 + 沪官方状态 + 深 BaoStock 全量状态”的最小组合。当前推荐动作是保持实施阻断。 |
| PROPOSED_RELEASE_SCOPE | 仅列条件性能力边界，不形成已批准发行范围；不指定版本号。 |
| EVIDENCE_LIMITATIONS | 新增行情/状态数据行 0；两次登录超时；无真实吞吐或最新日终验收；文档语义不等于来源资格。 |
| DOCUMENT_PATH | D:/Dev/Projects/chstockdata/docs/audits/DR01-current-free-data-feasibility-2026-10-19.md |
| NEXT_PHASE_AUTHORIZED | NO；Owner Review。未实施、未提交、未推送、未发布。 |

### 1.1 已发布与 main 的区分

2026-10-19 15:48 左右直接读取 GitHub main、最新正式 Release、PyPI JSON，三者均 HTTP 200：

- [GitHub main](https://api.github.com/repos/joycoding2000/chstockdata/commits/main) 返回上述 HEAD，提交时间为 2026-10-18 16:08:10 +08:00。
- [最新正式 Release](https://api.github.com/repos/joycoding2000/chstockdata/releases/latest) 为 v0.4.2，非草稿、非预发布，target_commitish 为上述发行提交，发布时间为 2026-10-14 12:07:58 +08:00。
- [PyPI 元数据](https://pypi.org/pypi/chstockdata/json) 的当前版本为 0.4.2；wheel SHA-256 为 a7f2f04f4ff46be4c428e2f0224ab8ea11efa357c66e500cbba7ff9599cea7a2。
- main 新增的 get_sina_daily_fund_flow / DR04-P 已取得该项 Owner Acceptance，但尚未发布，不能说它属于 PyPI v0.4.2。DR01 相关核心文件未因该增量发生变化。参见 [README](D:/Dev/Projects/chstockdata/README.md)、[发行记录](D:/Dev/Projects/chstockdata/docs/releases/v0.4.2.md)、[DR04-P 合同](D:/Dev/Projects/chstockdata/docs/dr04-p-daily-fund-flow.md)。

本地读取的 [能力矩阵](D:/Dev/Projects/chstockdata/docs/provider-capability-matrix.md)、[架构与 API 入口说明](D:/Dev/Projects/chstockdata/docs/architecture.md) 及 [顶层导出](D:/Dev/Projects/chstockdata/src/chstockdata/__init__.py) 是公开能力基线。矩阵中 suspension 的“指定日期全市场快照”行标题不能覆盖 README 和实现明确的“仅请求当天”限制；不能由标题推导出指定已完成日资格。

## 2. 冻结消费者需求与差距矩阵

依据：

- [R3.2 范围冻结文档](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md)。
- [DR01–DR06 冻结消费者问询](D:/Dev/Projects/mishi-radar/docs/MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md)。
- [早期供应能力应答](D:/Dev/Projects/mishi-radar/outputs/v0.1-owner-review-2026-10-16/consumer-data-requirements.md)，仅复用其中源码定位与能力边界；旧测试数字不是本轮运行结果。

DR01 CURRENT_SCAN 要求沪深主板、创业板、科创板的完整普通股票身份集合，以及目标日上市、ST/风险警示、退市整理、停复牌事实，附证券池分母、缺失/未知数和时间。DR02 价量、DR03 行业、DR04 资金、DR05 财务估值与 DR06 历史交易规则/成交约束分别有独立契约；本轮不将它们并入 DR01，也不以 DR06 为理由移除 DR01 当前停复牌要求。

分类：A＝已有公开支持，可直接复用；B＝部分支持，需有限扩展；C＝缺少公开能力，但免费原始来源已有可行证据；D＝当前无法证明满足。C 不表示已完成适配或验收。

| DR01 必要事实/输出 | 当前公开能力与真实边界 | 分类 | 下一步最小差距 |
|---|---|---|---|
| 目标 D 与交易日历 | fetch_trading_calendar(*, root=None, today=None, adapters=None, clock=...) 提供结构化交易日；本地指数/在线回落及陈旧限制已有实现 | A | 复用日期校验；调用方明确 D，不把当天日期、周末或源尚未更新的日期自动当作可交付日 |
| 沪深完整普通股票集合、名称、上市日 | resolve_ticker(user_input)、名称预热仅用于解析，不是证券主表；内部 mootdx stocks 表会混入非目标证券且名称表使用裸代码映射 | C | 将已核的官方全导出及日期快照接入一个独立、保留市场身份的公共事实接口；不改名称解析器 |
| 交易所、板块、证券类型、排除 CDR/B 股 | 无 DR01 公共合同；官方字段及 689009 公司概况已有证据 | C | 使用官方类型/板块与白名单范围；身份固定 exchange + code；不单靠号段或 STOCK_TYPE=8 判普通 A 股 |
| D 日上市/退市事实 | fetch_delisting_status(ticker) 返回终止上市参考；未命中不证明在市，亦不证明可交易 | B | 主表、上市日、真实退市生效日共同判断；不能将未来退市日期提前应用 |
| D 日 ST/风险警示、退市整理 | 原有文本/当前信息不形成完整池合同；此前官方全名单及日期桥接已取得 | C | 复用已核来源与分类，新增规范字段和质量记录；退市整理与已终止上市分开 |
| 沪市 D 日含持续停牌的状态 | fetch_suspension_info(ticker, curr_date) 为东财最新事件的当天视图；官方沪 D 日期区间查询与日终快照已另行证明可用 | C | 新能力直接适配已合格官方路径；不能用旧接口请求过去日期冒充复用 |
| 深市 D 日完整停复牌事实 | 旧 suspension 接口不认证过去日期；既有深日行情无状态字段；BaoStock 尚无本轮数据响应 | D | 唯一来源阻断：取得全目标集合逐证券明确状态及日期、完整传输证据，并验证持续停牌/复牌 |
| 来源、业务日期、采集时点、失败原因 | FetchAttempt / FetchMetadata / FetchResult 已区分这些概念 | A | 复用模型，来源与质量清单放在新 payload；不改现有全局状态枚举或冻结 EvidenceEnvelope |
| 全市场分母、缺失/UNKNOWN、市场级完整性 | 现有单股返回不提供该聚合合同 | B | 为声明的全目标集合保留记录，报告缺失集合及计数；未知不能静默剔除或当作未停牌 |
| 历史 PIT 股票池及状态有效区间 | 当天停牌接口及 R2.1 开盘活动证据均不提供完整历史资格 | D，且非本轮目标 | 不通过扩建历史证券数据库解决 CURRENT，不将本轮结论外推至 HISTORICAL_REPLAY |

直接源码：[名称缓存与构建](D:/Dev/Projects/chstockdata/src/chstockdata/a_stock.py:324)、[停牌入口与限制](D:/Dev/Projects/chstockdata/src/chstockdata/suspension.py:193)、[终止上市语义](D:/Dev/Projects/chstockdata/src/chstockdata/delisting.py:422)、[派生可交易性](D:/Dev/Projects/chstockdata/src/chstockdata/tradability.py:107)、[FetchMetadata](D:/Dev/Projects/chstockdata/src/chstockdata/fetch_result.py:145)。已有架构中 tradability 是派生事实，不是一个可为全池资格背书的独立 provider。

## 3. 三轮既有证据与唯一剩余阻断

三轮按证据链重建，不重新采集其全市场名单或风险名单：

1. **初始全市场枚举包**：原始官方沪主板/科创板/深 A 导出、official-requests.json、offline-audit.json，已由后轮原样保留于 [reused](D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18/evidence/reused/official-requests.json)。本轮使用的是该原始包，不凭空假定另有一份独立 PASS 报告。
2. **DR01-CURRENT 来源资格轮**：[报告](D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18/DR01-CURRENT-report.md)、[qualification.json](D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18/evidence/qualification.json)，补齐官方数量、类型、风险名单；当时还有沪日期及停牌证据缺口。
3. **最终补链轮**：[报告](D:/Dev/Projects/mishi-radar/outputs/dr01-current-unblock-2026-10-18/DR01-CURRENT-report.md)、[delta-qualification.json](D:/Dev/Projects/mishi-radar/outputs/dr01-current-unblock-2026-10-18/evidence/delta-qualification.json)，解决沪日期和持续停牌；准上市补链后仍只剩深市全量状态事实。

已取得且本轮继续有效的事实：

| 证据 | 事实及使用边界 |
|---|---|
| 官方证券全导出 | 5,226 条：沪主板 1,702、科创板 618、深主板 1,495、创业板 1,411；689009 为科创 CDR，排除后观察到普通股票 5,225。该数是观察集合，不是已通过全部资格的可筛选分母 |
| 沪带日期完整快照 | D=2026-10-16，源时点 16:29:04；2,361 条全证券中 ASH/KSH 2,320，与主表代码、名称、产品状态完整对齐；排除 CDR 后普通股票 2,319 |
| 风险及生命周期 | 沪 A 风险 83、深 A 风险 115；深退市整理 301139 一条；B 股单独排除；601059/601198 的退市生效日为 10月19日，不能提前用于 D |
| 沪 D 停牌 | 官方区间查询包含跨日持续停牌；普通股票停牌为 600293、601059、601198、688496，和完整日终快照 P 状态一致；600825 有 D15 停牌、D16 恢复的对照 |
| 深 D 日行情 | 2,945 条均带 D，完整覆盖 2,906 条 A 股；无停复牌事实字段。零成交六只为 000016、002388、002717、002731、300773、301314，只能作为核验样本 |
| 深闭市阶段码 | 正常 000001 和持续停牌 000016 均为 00；不能由闭市阶段码区分停牌 |
| 东财与准上市 | 过滤后的六只深股相符；准上市展示明确包含持续停牌，但缺该表的具体上游及全量完成凭证，也未证明与东财独立。列表一致不是未列证券均正常的证据 |

直接原始文件均位于 [补链证据目录](D:/Dev/Projects/mishi-radar/outputs/dr01-current-unblock-2026-10-18/evidence/requests.json)：004/007/008 为沪日期停牌；014/016/017 为沪完整快照；019/020 为深 D 行情；040/041/042 为闭市码语义；045–048 为准上市停牌、复牌、汇总和来源说明。风险及证券类型证据见 [前轮请求账本](D:/Dev/Projects/mishi-radar/outputs/dr01-current-2026-10-18/evidence/requests.json)。

本轮离线逐文件验证两份既有 SHA-256 清单，**48 + 76 = 124 个条目全部匹配**；冻结 R3.2 与 DR01–DR06 文档散列也与前轮记录相同。前轮的 89 / 176 项断言是当时证据审计结果，本轮没有重新执行会写回输出的审计脚本，更未将这些数字称为 DR01 功能测试。

## 4. BaoStock：现有集成、免费来源合同及实测限制

### 4.1 现有集成可以复用什么

[pyproject.toml](D:/Dev/Projects/chstockdata/pyproject.toml) 已有可选 baostock>=0.8.9，本机既有环境实际装有 0.9.3；本轮没有安装或升级依赖。

[chips.py](D:/Dev/Projects/chstockdata/src/chstockdata/chips.py:195) 已有惰性加载、全局会话串行锁、login→query→logout 与 finally 清理。它为筹码查询前复权 OHLC、turn、tradestatus，随后计数并**剔除 tradestatus=0 的行**。因此：

- 可复用可选依赖及串行会话的设计模式。
- 不可将 _fetch_turnover_frame 的输出当作证券资格输入；它没有保留停牌记录，也未请求 isST。
- 现有 chip 测试证明可选依赖缺失处理和算法装配，不证明某日全市场状态质量。参见 [既有测试](D:/Dev/Projects/chstockdata/tests/test_chip_distribution.py:94)。

### 4.2 官方文档实际确认的接口

本轮从官方首页实际引用的脚本找到只读帮助文档端点，再读取现行文档；没有依赖搜索结果中的第三方教程。文档响应身份见附录 B。

| 来源接口 | 官方合同确认的候选能力 | 仍未证实的内容 |
|---|---|---|
| query_all_stock(day=D) | 按指定日返回沪深证券及 code、tradeStatus、code_name；1 为正常交易，0 为停牌；当前自然日数据要等日线更新后才有，更新前可为空 | D 全量实返集合、缺失数、所有状态值、实际更新延迟、持续停牌覆盖及数据准确性 |
| query_history_k_data_plus(code, fields, start_date=D, end_date=D, frequency="d", adjustflag="3") | 日线含 date、tradestatus、isST；文档明确包含停牌证券，停牌日价格平移、量额为零 | 逐股实返覆盖与日期；isST 不能区分完整风险类别或退市整理；零量说明不能反向代替状态字段 |
| query_daily_history_k_AStock(date=D) | 0.9.3 新增的每日全 A 股批量日线，字段含逐行 date、code、tradestatus、isST | 本轮未调用成功；完整性、停牌覆盖、异常处理与生产成本均未知。旧最低 extra 版本不能被默认认为有此函数 |

官方入口：[证券元信息](https://www.baostock.com/mainContent?file=StockBasicInfoAPI.md)、[A股日线](https://www.baostock.com/mainContent?file=stockKData.md)、[每日更新](https://www.baostock.com/mainContent?file=DailyUpdates.md)。由这些合同推断：**不必通过 N 次单股请求才能获得 D 日状态**。这个推断只证明存在批量路线，不证明该路线本轮已交付合格数据。

[官方平台说明](https://www.baostock.com/mainContent?file=home.md) 声明免费公共服务，公布日线预期于交易日 17:30 入库。证券元信息说明当天更新前返回空，因此“收盘后马上空结果”不能解释为全市场正常或无证券。17:30 是发布说明，不是已经测得的 SLA。

该说明同时列出 0.9.4 对带 API_KEY 的 vip 节点支持。本调查只使用既有 0.9.3 的公共节点，不配置 key，不访问 vip 节点，不将其纳入免费方案。

### 4.3 SDK 的日期、分页与失败机制

本机原始 SDK 位置为 D:/Dev/Projects/chstockdata/.venv/Lib/site-packages/baostock/：

- metadata/stock_metadata.py:79：query_all_stock 把显式 day 发送到服务器；返回解析保存 data.day、字段、页号。不能将本机采集日期冒充源业务日。
- common/contants.py:187：本安装每页 P=2,000，不能写死“一次 API 调用等于一条网络请求”。
- data/resultset.py:54：next() 可能继续请求分页。后续网络接收空时会返回 False，而未必设置新的错误码；单看循环正常退出或 error_code=="0" 不足以证明全部页成功。将来必须记录每次传输的完整响应和页边界，并与官方目标集合做精确集合对账。
- security/history.py 中的 query_daily_history_k_AStock 当前 SDK 以单批结果处理，字段逐行含 date；不能把该实现形态当成实测吞吐保证。
- util/socketutil.py:34/55：连接和收发使用进程全局 socket，无生产级显式截止时间；异常会打印并返回空。新能力若获准实现，必须有有界超时和失败分类，不能照搬无限等待，也不能以进程全局 socket.setdefaulttimeout 干扰其他现有能力。本轮仅在一次性调查进程设置超时。

### 4.4 两次有界实测

固定核验日期为 D=2026-10-16，复用此前官方快照；计划查询 D 与前一交易日 10月15日全表，再用 sz.000016 连续停牌和 sh.600825 复牌作小样本日期对照。计划不含风险警示重抓、历史回填或 mootdx 全表。

| 尝试 | 北京时间开始 | 实际执行 | 原始结果 |
|---|---|---|---|
| 1 | 2026-10-19 15:49:08 | 1 次 TCP 连接尝试、1 条 login 消息，8 秒接收超时 | SDK error_code=10002007，网络接收错误；无响应正文 |
| 2，唯一一次显式复核 | 2026-10-19 15:50:33 | 1 次 TCP 连接尝试、1 条 login 消息，15 秒接收超时 | 同上；未进入任何数据查询 |

每个进程预设最多 14 条协议消息、单连接串行、无隐式重试、结果行硬上限；登录失败即停止查询并关闭 socket。实际总计 **2 条登录消息、2 次连接尝试、数据查询 0、状态行 0**。本机错误码不是服务端“不支持 D”的答复；不能由此推定 BaoStock 数据本身错误，也不能宣称连接恢复后完整性必然成立。附录 A 保留完整的新增失败输出。

这两次发生于日线预计入库前，但请求计划的 D 是已过去的 10月16日；失败发生在登录阶段，不能用“10月19日尚未更新”解释或掩盖。10月19日已收盘，并不表示其所有来源日终数据已经就绪；本轮也没有认证 10月19日为最新可交付日。

## 5. 其他免费来源与最小组合判断

| 路线 | 复用判断 | 本轮处理 |
|---|---|---|
| 沪官方完整日终快照 + 日期区间停牌 | 已证实能提供沪 D 状态，并可核持续停牌和恢复 | 直接复用，不重抓 |
| 深官方日行情/闭市码 | 能支持身份和 D 对齐，不能提供全状态否定证据 | 已有反例，停止重复探测 |
| 东财最新停复牌事件 | 完整返回最新事件不等于 D 全市场状态；可含未来或已结束事件 | 仅核验已有样本/冲突，不将其作为深 D 正常证券的默认来源 |
| mootdx stocks / quote / bar | 名称枚举和正交易活动没有完整 D 日停复牌字段合同；裸代码跨市场碰撞已有证据 | 不重新全量枚举，不将名称表或无 bar 推断停牌 |
| 本地 VIPDOC | 价量可作校验，缺行/零成交有多种原因；现有包还存在日期陈旧边界 | 不刷新历史包或推断全市场停牌 |
| 准上市 | 展示语义及六只深股一致已核，但表级血缘及全量完成凭证未补齐 | 不重复查询；只有取得本表具体凭证才可重开资格判断 |
| BaoStock 指定日全表 | 有明确业务日及逐证券状态合同，最值得继续的免费候选 | 本轮实测不可用；尚未成为合格来源 |

没有发现已获证明的其他免费最小组合可以绕过深市状态阻断。备选技术路径只有：在可达的免费公共 BaoStock 环境完成同一有界资格验证；或取得深交所 D 日完整状态文件/准上市该表的可追溯全量凭证。均不得以付费接口、商业订阅、零量代理或可能同源的列表交集替代。

## 6. 资格通过后的最小候选设计（当前不可进入实施）

本节记录接口与架构边界，便于 Owner 判断是否值得补证；**不是建立在已通过来源资格之上的实施方案**。如果第 8 节来源验收不能满足，本节不得转成开发计划或发行承诺。当前实际建议是暂停实现。

### 6.1 一个新增事实 API

建议候选签名，名称可在后续获授权设计中冻结：

~~~python
fetch_security_qualification_snapshot(
    trade_date: str,
    *,
    root: Path | None = None,
    refresh: bool = False,
) -> FetchResult[SecurityQualificationSnapshot]
~~~

- trade_date 必填 ISO 日期，声明为已完成交易日。root 仅控制新快照缓存根目录，遵循现有配置优先级；refresh 只刷新该 D，不触发历史回填。
- 初期只认证“当前最近已完成交易日”的完整快照；为核复牌可有界读取前一交易日。旧 D=10月16日是本调查资格样本，不自动授权任意历史日期查询或历史库。
- 固定市场范围 SH/SZ、普通 A 股四板；不由调用方传入一个小名单却返回“全市场通过”。不增加第二套 Mishi 专用 API、策略阈值或通用数据平台。
- 返回全声明集合的事实及质量，不内置未冻结的“上市满 120 日”、ST 策略取舍、成交额阈值或策略级可选池。消费者依据自己的冻结筛选规则派生候选池。

| payload 层级 | 必要字段 |
|---|---|
| 批次身份 | schema_version、snapshot_id、trade_date、scope（市场/板块/普通股票定义）、ready_for_current_scan |
| 证券身份 | security_id（SH:600000 等）、exchange、六位 code、name、board、security_type |
| 生命周期事实 | listing_date、delisting_date（可空，附含义）、listing_state；delisting_period 独立三态字段 |
| 风险与停牌事实 | risk_warning（明确真/假/未知）、risk_warning_type（有据才细分）、suspended（真/假/未知）、session_state；无法获证的事件起止时间保留空 |
| 复牌语义 | 如返回 resumed_since_previous_close，只能来自 D-1 明确停牌→D 明确正常的对照；它不是日内事件日志，也不是精确复牌时刻。对照缺失即 UNKNOWN，不伪造事件日期 |
| 逐字段证据 | effective_date、source_refs、field_quality / unknown_reasons；来源可以按批次引用，保留接口、参数、SDK版本、页号、原始响应哈希及取数时点 |
| 集合与质量 | declared_universe_count、identity_complete_count、required_state_complete_count、unknown_security_count、unknown_field_counts、missing_source_codes、duplicate/conflict_codes、excluded_type_counts、market_completeness |
| 来源清单 | source_id、provider、capability_id、business_date、source_observed_at（可空）、retrieved_at、raw_sha256、响应页数/行数、传输结束依据、上游说明/限制 |

risk_warning、delisting_period、suspended 必须允许 UNKNOWN；不能依靠名称字符串单独形成风险状态。最终“可筛选股票数”由消费者已冻结规则计算；供应方必须同时提供原始证券集合分母及未知数，不能把“已知状态的股票数”改称完整池分母。

### 6.2 来源组合、完整性与 fail-closed

1. **官方身份与状态**：复用此前官方沪深全名单、类型分类、风险警示/退市整理及日期桥接方案；沪停牌优先使用已合格官方日期区间与完整快照。每个生产 D 均重新验证自己的日期，不能把调查日快照当成永久资格。
2. **深状态候选**：若来源验收通过，用 query_all_stock(day=D) 完整结果与官方深 A 集合逐身份左连接，保留每只的明确 0/1。BaoStock 全表内的指数等不能进入股票分母；缺证券保持 UNKNOWN，不能当未停牌。
3. **日期实证**：验证响应 day==D、分页一致，配合带逐行 date 的日线/批量日线核对日期语义；源没有发布时刻可填空，不能从 HTTP Date 补造。接口若返回旧日、空表或部分表，批次不 ready。
4. **集合完整性**：按市场验证目标代码无缺失、无冲突/重复，必需字段都有明确值；官方总数/导出分页完整，快照之间日期一致。不能只检查 returned_count==source_self_reported_count，也不能只查六只停牌候选。
5. **冲突处理**：已认证官方状态与 BaoStock 明确冲突时保留双方原始值，冲突项 UNKNOWN，批次不 ready；不通过多数表决、价格活动或“官方优先所以忽略差异”掩盖质量问题。
6. **批次失败**：沪成功深失败仍返回诊断事实和原始分母，但 ready_for_current_scan=false，metadata.partial=true；强制失败的 request_status 与 limitations 明确阻断，不能因一个 provider 成功使整池伪成功。使用既有 outcome_status 机制表达，勿扩改 FetchMetadata 枚举。
7. **未知统计**：同一证券多字段未知，unknown_security_count 仅计一次；unknown_field_counts 逐字段计。全部是正常交易也必须具有完整明确记录，不能把来源失败包装成“正常空名单”。
8. **正常空区别**：合格官方“停牌事件为空”可表示没有停牌事件；“证券全表为空”不能证明沪深证券总数为零。输入 D 非交易日、尚未更新、传输失败、结构失败须分别披露。

5,225 / 2,906 等只用于复核本次 D 的固定证据，不能硬编码为未来每日总数，也不能在未知状态仍存在时发布合格 CURRENT_SCAN 分母。

### 6.3 复用关系、更新与失败恢复

- **交易日历**：复用 fetch_trading_calendar 的结构化输出并检查新鲜度。仅有交易日历不能证明状态来源已完成当天更新。
- **既有停牌/退市 API**：不改变 fetch_suspension_info 的当天限定、fetch_delisting_status 的参考语义或 fetch_tradability 的派生边界。共享已存在的传输/解析帮助与缓存配置，不能逐股调用这些 API 组成一个未经认证的“全量池”。
- **缓存**：新命名空间，以 scope + D + schema/source版本为键；保存原始取数时点、质量和哈希。完整校验后原子写入，失败不覆盖上一个完整快照。旧 D 可展示为陈旧诊断，但不得按新 D 交付；同一合格 D 缓存命中零网络，不伪造新 provider attempt/health。
- **更新**：每个完成交易日按需生成一次全量事实；BaoStock 的候选开始窗口为官方说明的 17:30 后。实际可用时点需要实测；源延迟时返回未就绪，不静默回退日期或切到东财未认证路径。
- **失败恢复**：单批显式总截止时间/页数预算，串行访问；短暂失败可在后续显式刷新重取不完整来源，最多一次受控复核，记录新快照身份。每次重取仍须重新做完整性判断。不能复用未来事件推算过去状态。
- **会话安全**：可复用 chips 的惰性加载/串行锁模式；如两个功能共享同进程，最小抽取一个内部会话帮助模块让两路共用锁，筹码过滤算法不变。若 SDK 阻塞不能安全局部限时，应采用标准库的一次性有截止时间工作进程；不新增队列、常驻服务或全局 socket 改写。
- **可选依赖**：核心环境不安装 BaoStock 时，新能力返回 not_configured/UNKNOWN 并 fail-closed；现有能力继续工作。不得悄悄把 extra 变成必装依赖。
- **每日批量日线备选**：0.9.3+ 的 query_daily_history_k_AStock 可在独立验收后取代分多页状态路径或用于日期校验。旧 extra 最低版本不具备此能力时，明确 not_configured 或使用已认证的 query_all_stock 路线；不可自动升级依赖或降级成几千次单股请求。

### 6.4 预期请求成本：仅公式，不作实测承诺

设官方必需来源合计 Q_official(D) 次 HTTP；BaoStock 全证券响应含 M(D) 行，本机每页 P=2,000。M 包括接口返回的非目标证券，不能以普通股票 N 代替。

| 场景 | 预期协议成本 |
|---|---|
| 合格 D 快照缓存命中 | 0 次网络 |
| query_all_stock 单 D | 1 login + ceil(M(D)/P) 数据消息 + 1 logout；如最后一页恰好满 P，可能额外 1 次空页终止查询 |
| 需核 D-1→D 复牌且无缓存 | 同一会话再加 ceil(M(D-1)/P)，并计可能的终止空页；不是逐只证券查询 |
| 只验证深正常/持续停牌/恢复的小样本 | 额外 K 个日线查询及其分页，K 事先固定；本轮计划 K=2，实际 K=0 |
| 每日批量日线备选 | 按本机 SDK 设计每个日期 1 个数据请求，加登录/登出；真实传输及完整性尚未验收 |
| 单批失败 | 只允许一次显式有界复核；失败不能按正常成本乘一个未经实测的“重试率”冒充已知耗时 |

总体为 Q_official(D) + BaoStock 上述成本；此前沪完整快照需 3 段，其他官方导出/风险页按已有账本和实际分页计算，不另作全市场请求。采集时长、免费节点限流阈值、稳定吞吐与失败恢复时间均 UNKNOWN；没有新实测数据就不能承诺“几秒完成”或 SLA。

### 6.5 若获准，最小代码与文档改动范围

仅作为未来设计输入：

- 一个 security_qualification.py（名称候选），负责事实装配、日期/集合校验和新快照缓存；避免改动 a_stock.py 名称解析。
- 必要时一个小型内部 BaoStock 会话帮助模块，承接已有惰性加载/锁；chips 仅调整对共享帮助的引用，不改筹码结果合同。
- 顶层新增一个导出；按现有规范登记实际 provider capability（如 baostock:security_status），复用 routing_observation。派生聚合本身不新建 provider 健康身份。
- 一份新 API 合同与 README/能力矩阵准确边界说明；新增离线 fixture/测试及显式可选网络验收入口。
- 不修改现有 FetchResult、EvidenceEnvelope、停复牌、退市、DR04-P 或其他消费者合同。具体文件拆分和代码行数需在来源通过、Owner 另行授权后制定，当前不提交实现计划。

## 7. 当前资格与历史 PIT 的严格边界

指定 D 日状态，是 DR01-CURRENT 必需事实；使用前一交易日少量对照不等于建立完整历史 PIT 能力。BaoStock 可以查询过去业务日，也不等于保存了当时首次可知的数据版本。

本候选不包含：

- 一年及以上历史真实证券池、已退市证券全历史纳入、任意历史日上市/ST/停牌有效区间或首次可知版本。
- 财报修订库、行业 PIT、DR02/DR04 数据补齐、DR06 历史交易制度与涨跌停/排队成交保证。
- 日内停复牌事件完整日志、分钟级停牌区间或任何订单可成交承诺。D 日二元状态只能用于本次冻结的日终资格场景。
- 北交所、B 股、CDR、基金、指数、港股；非目标证券仅记录排除原因。
- 大型证券数据库、统一数据平台、分布式采集框架、全量 mootdx 双源 Gate。
- 付费 Tushare、商业订阅、BaoStock vip/key 节点或付费回退。
- 本轮新接口、依赖安装、数据合同变更、Git 提交、推送、版本号确定与发布。

## 8. 后续来源验收、测试与停止条件

### 8.1 来源资格：任何实现计划之前

后续若 Owner 另行授权补证，只需沿用下列定向计划，无需重新调查已合格名单/风险来源：

1. 在可用的免费公共环境固定 D 及 D-1，记录 SDK 版本、连接/消息预算、分页原文和哈希；登录仍不可用则停止，不能切 vip/key。
2. 完整取 query_all_stock(D)，对本次官方深 A **2,906 个身份全部**逐一检查明确状态；未来 D 用该 D 官方实际集合。附缺失、重复、冲突、错误码、全部页完成依据及响应 day。
3. 明确核验六只持续停牌候选的 D 行，不仅查询这六只；正常股票同样必须有明确状态。用沪已认证的四只停牌、600825 D15→D16 复牌校验来源日期和状态解释。任何不一致保留原文并阻断。
4. 如果采用每日批量日线，另外验证逐行 date==D、目标代码集合完整、停牌行未被过滤，且和全证券 tradeStatus 对照一致；不能借由该接口存在自动免验。
5. 另选一个最新实际完成交易日，在文档更新窗口后形成全池快照，验证实际更新和跨日恢复。不需长期回填或无限稳定性测试；应至少观察一次真实发布窗口/日期切换并如实记录其局限。
6. 说明数据直接来自哪个 BaoStock 公共接口，保留可复现参数/原文。不可把其内部上游血缘写成“交易所官方”而无证据。免费可取与对外商业展示/再分发授权不同，后者交 Owner 按实际用途确认，不声称本轮已审结许可。

以上不是新增消费者标准，而是证明已有“全市场、D 日、可信、可追溯”标准所需的具体证据。缺任一必需事实仍为 INSUFFICIENT_EVIDENCE；普通 source_observed_at 未公开本身不是新增阻断。

### 8.2 若来源通过且另行授权实现，必要测试

- 原始 fixture：跨市场同代码、指数/B/CDR 排除、未来退市日、退市整理和风险状态分离。
- 全表与分页：少一只证券、重复冲突、非法 tradeStatus、字段缺失、尾页丢失/网络失败但 error_code 未变、日期错位、源未更新空表。
- 状态：持续停牌、正常交易、D-1→D 复牌、未来停牌事件不可提前应用；日线零量不能替代状态。
- 故障注入：沪成功深失败、依赖缺失、超时/限流、陈旧缓存、刷新失败保留旧完整快照但不伪装新 D。
- 元数据：不混淆业务日与获取日，cache hit 不增加 provider attempt，未知证券去重计数；partial/ready/request_status 一致。
- 兼容性：旧名称解析、筹码、停牌/退市/tradability 合同与当前 main 的 DR04-P 回归保持；已有 [停牌语义测试](D:/Dev/Projects/chstockdata/tests/test_suspension_source_semantics.py)、[退市测试](D:/Dev/Projects/chstockdata/tests/test_delisting_structured.py)、[交易日历测试](D:/Dev/Projects/chstockdata/tests/test_trading_calendar_structured.py) 可复用测试模式。

本轮仅新增调查 Markdown，未运行生产接口功能测试或重跑全套回归；没有代码变更，且既有测试不可能补足缺失的真实来源证据。

### 8.3 Owner 决策及停止点

Owner 当前可决策的是：

- 是否接受“免费批量路线明确、真实来源资格未证”的调查结论，并另行授权在可达免费环境做上述有限补证。
- 若来源合格，是否采用“官方主表/风险/沪状态 + BaoStock 深状态”的窄范围增量；是否有必要另外验收每日批量日线备选。
- 可接受的实际日终可用窗口、失败时的不可用呈现、缓存保留期限与实际商业使用许可；这些不是对冻结字段和完整性标准的豁免。
- 若免费来源仍不能通过，选择暂不交付该能力、延后交付，或另行提出消费者变更请求。任何代理替代/降低资格都需要独立 CHANGE_REQUEST，本轮未修改标准。

停止条件：免费节点有界复核后仍不可用；任何必需证券状态无法明确/追溯；日期或集合无法对齐；必须付费才能取得；预算内无法完成分页。命中后报告真实失败并停止，不能继续同类搜索、扩大全市场抓取、建立历史库、创建空壳接口或自动转入实现。

当前已命中“免费公共节点两次有界登录均无响应”。**来源 Gate 未通过；本调查文档可提交 Owner Review，下一阶段未授权。**

## 附录 A. 本轮新增状态来源探测原始输出

以下为一次性探测进程输出，原样保留字段；无服务端响应正文，因此没有可伪称的原始状态数据。10002007 为 SDK 生成的接收错误，不是服务端拒绝理由。

~~~json
{
  "probe_1": {
    "started_at": "2026-10-19T07:49:08.138732+00:00",
    "budget_messages": 14,
    "messages": 1,
    "connections": 1,
    "implicit_retries": 0,
    "elapsed_ms": 8056,
    "results": [
      {
        "label": "login",
        "error_code": "10002007",
        "error_msg": "网络接收错误。"
      }
    ],
    "wire": [
      {
        "number": 1,
        "label": "login",
        "started_at": "2026-10-19T07:49:08.138732+00:00",
        "elapsed_ms": 8004,
        "response_present": false
      }
    ],
    "sdk_stdout": "timed out\n接收数据异常，请稍后再试。\n"
  },
  "probe_2": {
    "messages": 1,
    "connections": 1,
    "implicit_retries": 0,
    "socket_timeout_seconds": 15,
    "results": [
      {
        "label": "login",
        "error_code": "10002007",
        "error_msg": "网络接收错误。"
      }
    ],
    "wire": [
      {
        "number": 1,
        "label": "login",
        "started_at": "2026-10-19T07:50:33.803549+00:00",
        "elapsed_ms": 15007,
        "response_present": false
      }
    ],
    "elapsed_ms": 15071,
    "sdk_stdout": "timed out\n接收数据异常，请稍后再试。\n"
  }
}
~~~

## 附录 B. 新增外部基线与文档请求记录

以下记录直接请求的公开来源身份和原始响应 SHA-256。基线记录保留关键返回值；文档为来源合同证据，不是市场数据。未将整份官网文档或大型前端 bundle 复制进本仓库。

~~~json
{
  "baseline_sandbox_attempts": [
    {
      "id": "github_main",
      "url": "https://api.github.com/repos/joycoding2000/chstockdata/commits/main",
      "started_at": "2026-10-19T07:47:46.026907+00:00",
      "redirects": 0,
      "retries": 0,
      "error_type": "ConnectionError",
      "elapsed_ms": 16
    },
    {
      "id": "github_release",
      "url": "https://api.github.com/repos/joycoding2000/chstockdata/releases/latest",
      "started_at": "2026-10-19T07:47:46.042462+00:00",
      "redirects": 0,
      "retries": 0,
      "error_type": "ConnectionError",
      "elapsed_ms": 8
    },
    {
      "id": "pypi",
      "url": "https://pypi.org/pypi/chstockdata/json",
      "started_at": "2026-10-19T07:47:46.050740+00:00",
      "redirects": 0,
      "retries": 0,
      "error_type": "ConnectionError",
      "elapsed_ms": 58
    }
  ],
  "baseline_public_responses": [
    {
      "id": "github_main",
      "url": "https://api.github.com/repos/joycoding2000/chstockdata/commits/main",
      "started_at": "2026-10-19T07:48:22.142335+00:00",
      "redirects": 0,
      "retries": 0,
      "status": 200,
      "bytes": 467118,
      "sha256": "06a80bbd05a1dd7e5b7f374410203bd9282d0d7c067be21f013bf7f6215615d8",
      "sha": "9543d03310b25be9963227a2a226366de04276ec",
      "commit_date": "2026-10-18T08:08:10Z",
      "elapsed_ms": 3454
    },
    {
      "id": "github_release",
      "url": "https://api.github.com/repos/joycoding2000/chstockdata/releases/latest",
      "started_at": "2026-10-19T07:48:25.596191+00:00",
      "redirects": 0,
      "retries": 0,
      "status": 200,
      "bytes": 8478,
      "sha256": "8476ceff0cb81539aad3230617275a371ab2da0c88022aabc656d551cfea8b83",
      "tag": "v0.4.2",
      "target": "17af23fe8183f740150dc01dd877473afe3911b7",
      "published_at": "2026-10-14T04:07:58Z",
      "prerelease": false,
      "draft": false,
      "elapsed_ms": 398
    },
    {
      "id": "pypi",
      "url": "https://pypi.org/pypi/chstockdata/json",
      "started_at": "2026-10-19T07:48:25.994216+00:00",
      "redirects": 0,
      "retries": 0,
      "status": 200,
      "bytes": 33527,
      "sha256": "58c6f7059cfdf78b1fc9b0c823d1ab11e8138b4bc25ff874f72063ce4379b3fa",
      "version": "0.4.2",
      "releases": [
        "0.1.0",
        "0.2.0",
        "0.4.1",
        "0.4.2"
      ],
      "files": [
        {
          "filename": "chstockdata-0.4.2-py3-none-any.whl",
          "upload_time_iso_8601": "2026-10-14T04:02:21.213485Z",
          "digests": {
            "blake2b_256": "785a38808941c9c3bc9be37a53ea9ffb38b20dc143605699888ad1b068eb7604",
            "md5": "b7bbe5b8184c7a7736c02a2d339bc3f3",
            "sha256": "a7f2f04f4ff46be4c428e2f0224ab8ea11efa357c66e500cbba7ff9599cea7a2"
          }
        },
        {
          "filename": "chstockdata-0.4.2.tar.gz",
          "upload_time_iso_8601": "2026-10-14T04:02:22.991505Z",
          "digests": {
            "blake2b_256": "4161492e3a34b7ee6028f98e71f6423e3c78299b08544454bf85044044ea247a",
            "md5": "51240797331788b0309a8bd6ff3c116c",
            "sha256": "302632c96dc1f17b38b8fa2dd872e3d7b034e21c89ccabee75b46fbf57b0ce56"
          }
        }
      ],
      "elapsed_ms": 8116
    }
  ],
  "official_document_responses": [
    {
      "url": "https://www.baostock.com/",
      "method": "GET",
      "started_at": "2026-10-19T07:51:37.224018+00:00",
      "status": 200,
      "bytes": 8086,
      "sha256": "8806d51df625bdc24066e2e6b2659615ed3d6eeb5fe29dafc434bd938f4c8674",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/assets/index-DUQ-MKvt.js",
      "method": "GET",
      "started_at": "2026-10-19T07:51:50.364131+00:00",
      "status": 200,
      "bytes": 2315869,
      "sha256": "32ae863323aceaa6632364e18d62906e38ed427641f69339bc1558f55819d47c",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/helpdocs/api/menu",
      "method": "POST",
      "started_at": "2026-10-19T07:52:14.625727+00:00",
      "status": 200,
      "bytes": 4279,
      "sha256": "aaa1f04f22f23b18bda9e3d7cb267013d1dfccfdb9da72dbde5047e0427d8dd5",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/helpdocs/api/markdown/home.md",
      "method": "POST",
      "started_at": "2026-10-19T07:52:15.080632+00:00",
      "status": 200,
      "bytes": 10167,
      "sha256": "6a931ebea4ff858c46cf89e6c8f448b755cceab10071a35265b576ff09545884",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/helpdocs/api/markdown/StockBasicInfoAPI.md",
      "method": "POST",
      "started_at": "2026-10-19T07:52:33.576110+00:00",
      "status": 200,
      "bytes": 3149,
      "sha256": "91776c0baa6cb59c1d597f08d46e63c38c2365f2d68b05b63437963e7c6612c3",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/helpdocs/api/markdown/stockKData.md",
      "method": "POST",
      "started_at": "2026-10-19T07:52:34.011499+00:00",
      "status": 200,
      "bytes": 12485,
      "sha256": "2a6db3b24ab21a199aa17bd949dfbe545d3279007bea1664854f9b7c20542aac",
      "retries": 0,
      "redirects": 0
    },
    {
      "url": "https://www.baostock.com/helpdocs/api/markdown/DailyUpdates.md",
      "method": "POST",
      "started_at": "2026-10-19T07:52:34.055539+00:00",
      "status": 200,
      "bytes": 15120,
      "sha256": "ddb5f1e153c44ab0e76cebd4506ff0075def6d8884c7fd1d2cd523e2f75a70c8",
      "retries": 0,
      "redirects": 0
    }
  ]
}
~~~

请求量核算：

- 直接 HTTP 尝试 13 次：3 次沙箱内基线连接失败；获准外网读取后基线 3 次成功；BaoStock 官网文档定位及读取 7 次成功。显式禁用自动重定向，requests 未配置隐式重试。
- BaoStock TCP：两个一次性进程，各一次连接尝试及一条 login；共 2 条协议消息；数据查询 0。第二次为唯一一次显式复核，不是隐式重试。
- 内置网页工具共 3 次调用，含 4 个 search_query 动作与 10 个 open 动作；初步定位包含不可访问/缓存失败结果。其内部实际 HTTP 次数不可观测，故不与上述直接请求相加伪造精确网络总量。第三方搜索摘要未用于供应能力证明。
- 本轮交易所名单、风险名单、mootdx 全量采集为 0；Firecrawl 账户预检 0，未重复前轮已记录的失败预检；没有消耗完预算后继续找 PASS。
- 探测与文档读取均在一次性进程完成，没有写新脚本、下载数据包或安装依赖。公共主机和文档链接不含用户凭证。

## 附录 C. 本地证据、散列与交付边界

~~~json
{
  "manifests": [
    {
      "folder": "dr01-current-2026-10-18",
      "entries": 48,
      "mismatches": [],
      "manifest_sha256": "4aeb4d218cf3994998b24e6ab47f5ca818bb35bf93470fcda8ed1346c96a2f2b"
    },
    {
      "folder": "dr01-current-unblock-2026-10-18",
      "entries": 76,
      "mismatches": [],
      "manifest_sha256": "925317d16efdddda498c600cdee8435a31e07fbec057492807df7f63e43d968d"
    }
  ],
  "references": [
    {
      "path": "D:\\Dev\\Projects\\mishi-radar\\docs\\MISHI_RADAR_V0_1_SPEC_R3_2_SCOPE_APPROVED_DATA_PENDING_2026-10-16.md",
      "bytes": 20372,
      "sha256": "9b98641d4602fcd2a35c28520f9160a3fbf935ce1c43e89d466a473419e5bd62"
    },
    {
      "path": "D:\\Dev\\Projects\\mishi-radar\\docs\\MISHI_RADAR_TO_CHSTOCKDATA_DR01_DR06_CONSUMER_REQUEST_2026-10-16.md",
      "bytes": 7000,
      "sha256": "35609c8cbf823dbb86a681ea15c27f7f598892b7ea73f46ecde5025e85ff8866"
    },
    {
      "path": "D:\\Dev\\Projects\\mishi-radar\\outputs\\dr01-current-2026-10-18\\DR01-CURRENT-report.md",
      "bytes": 7814,
      "sha256": "fb09e57701396cab1d963524a3e4a277f2e6a895019eda7248b00c1480326491"
    },
    {
      "path": "D:\\Dev\\Projects\\mishi-radar\\outputs\\dr01-current-unblock-2026-10-18\\DR01-CURRENT-report.md",
      "bytes": 6849,
      "sha256": "7e2ac2a5f56fda1b9926103efcd6fa671f1f150a1e3fccd87eb4d04f57da4fee"
    },
    {
      "path": "D:\\Dev\\Projects\\mishi-radar\\outputs\\dr01-current-2026-10-18\\evidence\\reused\\offline-audit.json",
      "bytes": 124916,
      "sha256": "bfa6b7e2abc9f06b966c59139a900c440525b1e41153a13956a21f689e9aede7"
    }
  ],
  "supplier_before": {
    "head": "9543d03310b25be9963227a2a226366de04276ec",
    "status_lines": 13515,
    "status_sha256": "d7e973e115b79535f4a046ae3ca2af45200f9533adc3bec3a3e048ae4ed6113a",
    "tracked_diff_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "tracked_diff_lines": 0
  },
  "mishi_before": {
    "head": "678872568c7425b773a0059ae551adc55b3040a3",
    "status_lines": 228,
    "status_sha256": "c8faa4c96eb58c110cb679f09ff2160689125c602cd15cefe103b6ffc3df5ef2",
    "tracked_diff_sha256": "723c71fbab17b873d30c3c229612e23ccc6cdd778e04c90dc8b70b53d9baa7f8",
    "tracked_diff_lines": 93
  },
  "source_test_files_hashed": 156,
  "verification_kind": "evidence integrity and read-only boundary; not functional qualification"
}
~~~

实际引用的 SDK 源码散列：

~~~text
metadata/stock_metadata.py  f24ff4fd6586d1063ac5feeb0ebf8210705a0f139eb15dba1d871e8dd585a5da
security/history.py       fe653aa09c0f07e9f9479407c8f2f5455b4ec60c3a9571c652cd9343f7d0094f
data/resultset.py         70882a035bc9c20991255d5495c31f68fabc923d313cd35652c33563141797a6
util/socketutil.py        248591168ad087fb9c91b64e8c909608082528ecbecf25541dcbce0fe9cfcd25
common/contants.py        fe7574dbdd2ca6087e58ce374948f6e7d9b7398dc64b3f4404ab88a2d7ee3792
~~~

检索遵循项目 CodeGraph 优先规则，首次 explore 返回 unable to open database file；随后定向读取源码，未修复/重建索引。供应仓库唯一适用 AGENTS.md 为根目录文件，docs 无更深规则；其冻结范围、证据优先与 Owner Gate 均保留。

写入前供应 tracked diff 为空，Mishi 存在用户既有修改；本任务不覆盖它们。最终交付只允许本文件新增，原始证据留在原目录引用；所有源码、测试及消费者合同只读。已对供应 src/tests 共 156 个文件建立内容散列用于落库后比较。


交付验证已完成：文档为 UTF-8（无 BOM），27 个本地引用全部存在，无残留占位；供应 src/tests 的 156 个文件内容散列逐一保持一致。排除本新增文件后，供应 Git 状态散列与写入前相同且 tracked diff 为空；Mishi 的状态散列及已有 tracked diff 散列均与写入前相同，两仓库 HEAD 未变。Git 对供应既有部分超长路径和用户全局 ignore 文件有枚举警告，因此不声称审计了这些未跟踪深层目录的全部内容；未为本任务修复环境或改写既有文件。

本文件既不是 DR01 Source Qualification PASS，也不是 chstockdata 新版本设计批准、实施授权或发布授权。

