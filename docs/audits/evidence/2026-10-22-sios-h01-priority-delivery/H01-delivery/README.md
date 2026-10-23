# SIOS H01 研究数据交付（部分交付，等待 Owner Review）

`H01_PARTIAL_DELIVERY_WITH_NAMED_GAPS`。接收门为 `BLOCKED_WITH_NAMED_GAPS`，
不是完整 H01 输入 PASS，也不是策略实验或生产 adapter 集成。

## 实物及口径

- 固定 513500、513030、513520。观察期 2024-01-02 至 2025-09-30，共 425 个本地交易日。
- 每只另有此前 200 日预热：2023-03-09 至 2023-12-29。原始行情共 1,875 行，无缺日、无重复日期。
- `raw_market_data.csv`：RAW OHLC，基金原整数除以 1000，单位元/份；原始 Volume 股/份；Amount 为源 float32 的精确人民币元数值。保留原整数、源字节索引和 SHA。
- `raw_sources/`：三只原始 `.day` 文件，以及仅用于交易日历的上证指数文件。指数不增加 H01 证券池。
- `fund_actions.json`：三基金已实施现金分红及拆分为经官方年报交叉核实的 `normal_empty`；九份 2023–2025 年报的原文、定位和披露日期齐备。空事件集不表示已认证历史预案、取消公告或逐日版本索引。
- `total_return_observations.jsonl`：1,875 条真实原始价对应的事后无事件指数及输入窗口。126 指的是 126 个观察值、125 个间隔；SMA200 为含当日的 200 个观察值算术平均。未运行排序、目标仓位或收益实验。
- 原始价与事后指数分文件保存。指数以首个预热观察归一化为 100；无已实施现金/份额事件，所以调整项分别为 0 和 1。没有使用 QFQ/HFQ。

## 必要缺口与使用限制

1. 三基金当前 F10 和事后年报能核实历史实施事实，但未提供逐历史 cutoff 的权益索引覆盖/历史版本证明。**不声称存在漏处理的具体分红；缺的是历史可得性认证。** 九份年报均仅用于事后核对，绝不将其内容倒填到历史信号。
2. 513030 的 2025-01-23 原记录 OHLC=1.815、Volume=0、Amount=0。保留 `NO_TRADE_RECORDED`、停牌状态 `UNKNOWN`；未认证停牌原因及此类无成交观察是否纳入消费者信号。受影响的 126 和 SMA200 窗口日期逐项列于 `coverage_and_unknowns.json`。

因此 `pit_total_return_index`、`pit_return_126`、`pit_sma_200`、TR
`information_available_at` 均为 JSON null，`pit_signal_qualified=false`。
**禁止以 retrospective 字段替代已合格 PIT 信号。** 原始日线沿用消费者既有
`EXCHANGE_RULE`（境内 15:00 收盘）可得时点，抓取时间另存；这条既有规则没有被扩展为对事后权益索引的认证。

无已实施分红意味着经济权益、现金支付、回测现金可用时间均
`NOT_APPLICABLE_NO_IMPLEMENTED_CASH_EVENT`；没有把三个不同时间设为同一天。
不存在真实事件转换样本，已用九份真实年报和无事件链对账；未来/UNKNOWN
事件拒绝用明确标注的回归 payload 验证，不添加虚构基金事件。

本地指数无记录日期标为 `CLOSED_IN_LOCAL_INDEX_CALENDAR`，这是本地来源推导，
不冒称官方历史日历版本。正成交只排除全日无成交，不认证日内停牌/委托可成交。

## 离线复现与接收

在本目录运行，Python 3.10+、标准库即可复算导出及接收；无需网络、chstockdata
安装、SIOS 执行、收益回测或新依赖。PDF 文本重新抽取才需要可选 pypdf，
OOXML 使用标准 XML 解析；提取结果和原文都已附带。

```powershell
python tools/build_delivery.py --package .
python tools/receive_delivery.py . --report validation_report.json
```

接收程序不导入导出程序或 SIOS：独立读取原始字节、核对单位、日历、预热、
权益定位、指数、126/SMA200 输入、未来信息和 SHA。退出码：0=完整接收，
2=实物与复算完整但必要缺口仍阻断，1=结构/完整性失败。本次预期为 **2**。

`manifest.json` 登记源文件、导出、schema、工具和合同的 SHA；`manifest.sha256`
单独校验 manifest。避免自引用，验证报告不计入 manifest；报告明确绑定被检验
的 manifest SHA，其自身 SHA 在外部审计报告记录。重跑验证只更新该报告的检查时间。

## 边界及交接

已完成：消费者合同恢复 → 原始文件复核 → 有界免费获取 → 九份管理人原文核对
→ 离线格式修复及回归 → 部分数据导出 → 独立只读接收。
停止条件：保留必要 UNKNOWN，不继续无界换源或放宽 PIT。

两仓库 HEAD 及已有未提交文件受保护；未修改生产 Provider、公共 API、SIOS
或策略。未 commit/push。H04/P2 维持 deferred，策略实验未授权。
下一动作是 Owner Review 本包及四项具名缺口，决定最小补证/修复或维持阻断。
