# SIOS H01 修订研究数据包

本包修复原交付“0 条合格 PIT 信号”的确定性资格缺陷。
`H01_DATA_PACKAGE_READY_FOR_CONSUMER_ACCEPTANCE` 表示研究输入已准备好交 Owner/消费者接收；
不表示生产 adapter 已集成、Owner 已接收或策略实验已授权。

## 固定输入与数学

证券为 513500、513030、513520；观察段为 2024-01-02 至 2025-09-30，
每只 425 日；另有 2023-03-09 至 2023-12-29 的 200 个观察预热。
原始 1,875 条记录完整保留，源 `.day` 文件和原包 raw CSV 可逐字节比对。
修订 CSV 仅增加/订正停牌及资格说明，原日期、身份、OHLC、量额、单位和来源值不变。

九份官方报告核实目标区间没有影响持有人单位权益的实施事件后，
总回报指数可为 `100 × RAW Close / 首个预热 RAW Close`。
这不是无条件把 Close 叫作总回报：无事件区间认证、身份、完整期间与原价资格缺一不可。
普通 ETF 申购赎回使基金总份额变化，没有改变存量持有人每份单位，未作为拆分。
既有算法和数值不变：126 个已知观察值对应 125 个间隔；SMA200 含当日 200 个值。
没有最新 QFQ/HFQ、排名、过滤决策、仓位或收益实验。

## 两种证据角色

- `HISTORICAL_SIGNAL_INPUT`：原始价格，按消费者既有 `EXCHANGE_RULE` 在境内收盘可得；实际权益事件账本为空。
- `EX_POST_COMPLETENESS_AUDIT`：2023、2024、2025 三年各三只基金的官方报告，以及已有 F10 核对。它们覆盖 2023-01-01 至 2025-12-31，足够覆盖全部目标日期；只认证有没有漏掉实施事件，不提供 T 的交易数值。

报告发布于 T 之后，并不使历史 T 的零事件市价回报自动含有未来信息。
报告的发布日期/抓取时间从未成为历史价格可得时间；不要求逐日另有官方“无分红证明”。
`fund_actions.json` 保留每份来源的身份、年度、精确证据边界及段落/页码。
年报的零拆分变动、折算披露和 F10 共同支持此固定区间的无持有人单位调整结论；
不将其扩大为历史全部取消/预案公告索引完整、永久无分红或首次抓取版本证明。

资格状态明确区分 `CONFIRMED_NO_EVENT_IN_SCOPE`、`QUALIFIED_POSITIVE_EVENT`、
`SOURCE_COVERAGE_INCOMPLETE`、`EVENT_IDENTITY_AMBIGUOUS`、`SOURCE_ACCESS_FAILED`。
后三项保持 fail-closed；发现真实正事件也不能套用本包的无事件算法。

## 513030：2025-01-23 全天停牌

上交所官方 PDF 证实开市起停牌至收市，SHA256：
`be01b505d9c05cf5c7bc58a231849379321d519d154f789b2ad3c5ae5bd81c28`。
原记录量额为 0，OHLC 均为 1.815，与前日收盘相同；原记录存在，属于
`VERIFIED_FULL_DAY_SUSPENSION`，不属于缺数据，也不产生虚构成交。

现有消费者 `DailyBar` 允许真实零量额；`_known_bars_through` 仅按日期和
信息可得性筛选，`bars_for` 返回全部已知日线，126/SMA200 使用该序列，
没有按成交量或停牌排除已报告日线。本包沿用这一已有规则：该已知记录占一个观察位，
估值保留已有 1.815，成交资格为 false。完整静态调用路径和源码 SHA 在
`observation_policy.json`，未执行或修改 SIOS。

公告只给出日期：`published_at=null`、`source_time_precision=date`。
既有消费者的日期粒度公告规则可保守推导当日末可得，但这不是实测秒级发布时间；
包内单列 derived 字段，不声称盘前已知该公告。历史全天停牌事实、T 收盘价格观察和
盘前信息资格各自独立；没有据未来公告生成 T 的信号。

## 结果与复现

1,875 个总回报观察合格；每只 200 个独立预热观察合格；
观察段全部 1,275 个证券日同时具备 126 和 SMA200 输入。
初始预热中不足 126/200 个值时，对应指标仍为 null，未制造更早历史。
`pit_signal_qualified` 表示当日 TR 观察合格，两个独立 readiness 标记表示指标输入已完整。

```powershell
python tools/rebuild_delivery.py --package .
python tools/receive_repaired.py . --report validation_report.json
```

接收工具使用标准库，不导入生产者或 SIOS；独立核对原始字节、单位、年度覆盖、
无事件证明、停牌、不泄漏、200 日预热及 126/SMA200 数学。
退出码 0 为研究包可接收，2 为仍有具名缺口，1 为结构/身份/复算失败。
重建官方 PDF 审计需要已存在的可选 pypdf；原文与提取结果均附带，普通读取不需要 pypdf。

`parent_evidence/`、`tools/legacy/` 保留原包的 manifest、原始导出与原接收脚本。
原 ZIP 和审计报告仍在原路径，没有覆盖。旧接收程序因强制“所有 PIT 字段必须为空、
必须有四项缺口”而拒收合格输入，其独立失败记录在外部修复审计证据中；
修订接收程序只替换这些错误条件，原有原价/单位/日期/数学和未来/UNKNOWN 拒绝仍保留。

manifest 登记所有输入、导出、工具、合同和源文件 SHA；校验报告不计入 manifest
以避免自引用，报告绑定所检查的 manifest SHA。
当前 RAW 快照没有历史 observed-vintage 证明这一限制仍记录，没有更改既有 RAW 可得规则。
H04/P2 deferred；生产 API、Provider、SIOS、策略均未改；未提交或推送。
