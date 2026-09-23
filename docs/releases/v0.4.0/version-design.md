# chstockdata v0.4.0 — 版本设计基准（追溯重建）

> **状态：RETROSPECTIVE DESIGN RECONSTRUCTION / OWNER REVIEW REQUIRED。**
> 本文件于 2026-09-23 补建，不是声称 2026-09-21 已存在、已经冻结的原始设计文档。它将当时的三仓迁移决定、后来逐阶段批准的演进以及当前验收边界分开记录。不得为了证明现有实现正确而倒改历史目标。
>
> 审查基准：chstockdata main = 18939fa902661e6a7da78155431de60fc1a9d742（RH2.1）。RH3-A 尚未在此基准中验收；没有 v0.4.0 tag / PyPI 发布证据。

## 1. 来源、版本决策的沿革与证据等级

### 1.1 原始协调资料（2026-09-21）

最初讨论沉淀为三个仓库的跨仓迁移方案：chstockdata-cross-repo-migration-plan.md、其 v2 和 v3。它们原本是会话交付物，不是此仓库中已经冻结的 v0.4.0 version-design.md。v2 取代 v1 的时序，v3 又取代 v2 的版本与消费者状态。不能把三份文件中相互矛盾的建议拼成一个“原始承诺”。

- v1 在误以为 chstockdata 尚为 v0.2.1 时，建议 0.3.x 引入 structured API、0.4.x 再拆 a_stock.py；同时提出过 vipdoc → Tencent Kline → Sina 的日线替代建议。
- v2 根据 TradingAgents 已进入 Phase 1、systematic-investing-os M0 已冻结的事实，取消了消费者等待 provider 重构和回写 M0 的路线；mootdx 是否退出行情主链改为由真实能力证据决定。
- v3 明确 v0.3.0 已是消费基线，因此将 additive structured API / capability health / provider-routing separation 放到 v0.4.0；全面拆分 a_stock.py 推迟到 v0.5+。

**历史 provenance 更正：**早期 v3 文本曾引用不存在于当前远端的 143eb5a3c0e02a95b1c11a2e7c61e8ac470b5f77。当前实际发布提交、chstockdata 静态门禁基线及 systematic-investing-os 的 third_party/SOURCES.yaml 均指向 **143eb5a61e11003a4b29461eeb78deec0ab8d8e5**（release: v0.3.0 ETF actions and data contracts）。不能继续传播旧的错误全 SHA，也不能修改冻结 M0 的历史含义。

### 1.2 本仓库实施与后续审核

- 0.3.0 frozen compatibility source: 143eb5a61e11003a4b29461eeb78deec0ab8d8e5。
- Phase 1–8: additive contracts、quote/daily bars/calendar、provider observation、suspension/delisting/tradability 及 PIT date guard；以各阶段提交和测试为实际记录。
- Readiness / Gap Audit: docs/audits/2026-09-22-v0.4.0-readiness-gap-audit.md，结论为可进入 release hardening，不等于已可发布。
- RH1 / RH2 / RH2.1: 对应 docs/audits 中的 close-out；远端基准 18939fa 为 RH2.1。它们是后来的实施及门禁记录，不得冒充初始设计。
- RH3-A / RH3-B: 仍需独立完成及授权。

**证据顺序：**冻结的消费者契约与实际源码/commit/test > 当时经确认的设计变更 > 后续审计 > 早期建议。后续范围变动必须注明由来及 gate，不以“现在已经做出来”为理由倒推为原始目标。

## 2. 背景及产品问题

chstockdata 已经是两个第一方项目实际使用的数据底座，不是一份可任意重写的爬虫实验代码：

1. TradingAgents-AStock-Private 通过兼容 shim/现有数据接口使用行情与研究材料；其 ResearchSnapshot、Evidence、DataHealth、ResultStore、41-tool 产品目录属于 TradingAgents 自己。
2. systematic-investing-os 的 M0/研究证据基于 frozen chstockdata 0.3.0，唯一合规导入边界是 ChStockDataProvider/anti-corruption adapter；Instrument Master、canonical market contract、snapshot/backtest/strategy 语义属于该消费方。其实际依赖包括 local vipdoc、日历、历史停牌和股票/ETF 公司行为；不能因 provider 重构改变其历史研究证据。

v0.3.0 已提供 ETF/fund corporate actions、完整分页的历史停牌快照和 local vipdoc pre_close 等被消费方使用的契约。痛点不是“所有旧接口不可用”，而是巨大 a_stock.py 同时承担数据源/路由/缓存/格式化，返回类型有 DataFrame、dict 和字符串；mootdx bars canary 可能被误作整个 provider 的健康结论；真实源失败可能被最终 fallback 成功掩盖，数据来源/缺失/时间语义难以供下游安全消费。

**核心目标：consumer-aware platform evolution —— 先新增可信事实与 provenance 边界，保留既有契约，分别验证两个消费者，然后才逐步移除 legacy。**

## 3. 版本目标与明确不承诺的内容

### 3.1 v0.4.0 必达目标（最初路线确定的内核）

- 保留 v0.3.0 legacy public API 的签名、返回 envelope、关键缓存和失败行为；新增 API 为 additive。0.3.x 仅用于兼容的关键 correctness 修复。
- 建立 FetchAttempt / FetchMetadata / FetchResult，区分一次 provider observation、路由最终结果和 request-level outcome；来源、数据业务日期、获取日期、stale/partial/limitations 不伪造。
- provider + operation/capability 粒度的 health；mootdx bars 失效不能直接判 finance/xdxr 整体失效。相同 observation 不允许被 primitive + structured 边界重复记账。
- quote / daily-bars 首批真实 structured vertical slices，legacy renderer 委托 structured acquisition；保留 route-specific fallback 与原业务语义。
- live routing-chain smoke 与单 provider capability probe 分开报告；fallback-green 不得掩盖单源红灯。外部免费数据源当前在线状况不能替代确定性合同测试。
- 修复与上述演进直接相关的配置值验证、warmup retry 等可靠性问题，守住 legacy regressions。
- 无须两个消费者同步迁移，更不能为数据层改造返工 TradingAgents Phase 1 或 systematic-investing-os 已冻结 M0/M1。

### 3.2 实施中纳入的有限增量（不是最初即冻结的完整需求）

后来按真实依赖与 correctness 证据，逐阶段加上：

- Phase 2.x：daily-bar canonical schema、source contribution truth、请求空窗 outcome、volume unit 不猜、cached OHLCV acquisition 收敛与原 800-bar/PIT 行为。
- Phase 3 / 3.1：structured trading calendar；partial calendar 不能把未列出日期当作闭市证据。
- Phase 4.1：只抽通用 attempt/health observation kernel，不抽包含不同政策的 GenericFallbackRouter。
- Phase 5 / 5.1：完整分页的停牌快照结构化，只有命中 ticker 的坏行影响对应结果；缓存命中不伪造访问。
- Phase 6 / 6.1：calendar + suspension 的保守 derived tradability。
- Phase 7：SSE/SZSE 官方终止上市名单的结构化状态；BSE 未覆盖必须 unknown。
- Phase 8：只有查询日达到官方 delist_date 才能由退市事实阻断历史 tradability，避免今天所知未来退市污染此前日期。

以上是 **approved-by-phase evolution**；因未预先维护本总设计，存在版本级 change-control 文档缺口，但不能仅因新增了阶段就认定未经授权的 scope creep。

### 3.3 v0.4.0 明确不承诺

- 不重写全部 a_stock.py，不强行合并所有 provider 为一个 GenericFallbackRouter，不迁移所有 40+ legacy API。
- 不删除 TradingAgents compatibility shims / 旧 provenance / source-context hooks；也不将 TA 的 Evidence、DataHealth、ResearchSnapshot、catalog 或 systematic-investing-os 的 Instrument Master、研究/回测语义下推到数据包。
- 不提供完整 IPO/listing lifecycle、退市整理期/复牌历史制度、BSE 官方退市覆盖；covered-market miss 仅表示当前已覆盖官方终止上市名单未命中。
- 不声称完整 historical availability/PIT snapshot database；date guard 仅防退市生效状态反向泄漏，不能证明历史时点当时已知的信息集。
- 不在没有真实数据源能力证据时强迫 Tencent Kline 取代 mootdx，也不宣称 mootdx Volume 绝对单位已获实测证明。
- 不承诺 mootdx+mcp 可在同一 Python 环境安装；当前上游 httpx 约束冲突，按独立 extras/独立环境支持。
- 不把 consumer 全面迁到 structured API 作为 v0.4.0 的既成事实。未来拆分 legacy/decomposition 默认 v0.5+，删除旧接口须待第一方消费者真正迁移并另行评审。

## 4. 架构边界与关键不变量

~~~text
Provider / local vipdoc + transport
                ↓
Operation-scoped health + truthful FetchAttempt
                ↓
Structured factual routes:
quote / daily bars / trading calendar / suspension / delisting
                ↓
Derived tradability (calendar → delisting-date guard → suspension)
                ↓
Legacy compatibility renderers  /  consumer-owned adapters
~~~

- FetchMetadata.final_status 是 attempts 派生的 provider/route 观察结论；outcome_status/request_status 为 request-level 结论。缓存-only 可以 attempts=[]、final_status=skipped、request_status=success 或 normal_empty；consumer 必须用 request_status 判断请求结果。未来显式 cache-serving 状态属于后续契约设计。
- Canonical validation 先于 success/health；normal_empty 与 hard failure 有别；unknown 不能转为 false 或 true；stale/partial 只描述最终有效 payload 而不是落选源污染。
- Calendar complete closed → false、partial negative → unknown；delisting own-market failure / BSE uncovered → unknown；仅有效退市日达到查询日才会 block；suspension failure → unknown。
- 日线的 Volume 保持来源原生值并显示单位/未知口径，不擅自将 mootdx vol 乘除 100；systematic-investing-os 对未 qualification 的在线来源继续 fail-closed。
- 具有不同商业语义的 provider route 不应为抽象统一而丢失既有 fallback、stale、supplement、分页或 matched-row 规则。

## 5. Gates 与退出条件（追溯汇总；不伪称最初已编号冻结）

| Gate | 要求 | 截至 18939fa 的可用证据 / 状态 |
| --- | --- | --- |
| G0 source identity | v0.3.0 实际可达 full SHA，consumer provenance 对齐 | chstockdata commit 和 systematic SOURCES.yaml 均为 143eb5a61...；早期 v3 文本 SHA 错误须留痕 |
| G1 backward compatibility | old signatures/envelopes、CSV/cache/PIT/800 bars、legacy 异常契约回归 | 阶段测试及 Readiness Audit 记录通过；不能用包 import 代替跨仓 canary |
| G2 observation truth | one attempt/one health；source failure 不被 fallback 改写；request_status 明确 | Phase 1–8 回归；cache-only nuance 已显式文档化 |
| G3 factual safety | canonical before success、unknown/partial/PIT/date guard、单位不猜 | 各 vertical slice deterministic regressions；非完整 PIT 能力不得夸大 |
| G4 controlled scope | 每一阶段有停止条件，Phase 9/Generic Router/IPO lifecycle 不偷渡 | Phase 8 后 Readiness Audit 停止 feature development；版本级 change log 由本文件补建 |
| G5 release quality | lint 新增行 gate、全量 pytest、build/twine、wheel/sdist clean install、extras policy | RH1/RH2/RH2.1 close-out 记录通过；287 条 Ruff 存量债务仍可见 |
| G6 consumer canary | 实际 v0.4 wheel + 实际 consumer code + source-path/pin 证据，保留冻结主线 | **未在 RH2.1 基准验收**；RH3-A 要求逐 consumer 真实证据 |
| G7 publish authorization | version/tag/installed metadata/runtime 一致，GitHub trusted publish 环境、Owner 授权 | RH2.1 仅本地 workflow preflight PASS；未执行 tag-triggered GitHub/PyPI 发布 |

发布门禁和使用门禁分开：chstockdata package readiness 不等于任何一个 consumer 已安全升级；consumer canary 不等于批准修改其已冻结的研究证据。

## 6. Consumer adoption policy

### systematic-investing-os

保留 M0 source pin 及 historical evidence；仅在里程碑安全点进行独立 provider upgrade review。新 wheel 必须在临时 worktree/venv 里加载真实 adapter 和真实测试；现有 adapter 对 version != 0.3.0 会 fail closed，因此 v0.4.0 canary 必须明确临时调整 version-qualification seam、证明实际使用 candidate wheel、重跑 frozen M0 contracts/ETF/golden/relevant M1 tests，并单独审核 provenance，不能把旧 pin 直接覆盖或把 import smoke 冒充 canary。不能顺便更改 canonical DailyBar、Instrument Master、snapshot/strategy/backtest semantics。

### TradingAgents-AStock-Private

保留其产品层 ResearchSnapshot/Evidence/DataHealth/41-tool catalog。实际分支、依赖声明及 shim 必须先核对；不能假设其每个分支都已允许 0.4.0。候选轮次仅在隔离副本修整必要安装约束并回放 legacy/真实消费合同，不改生产 main、Phase 1/2 运行语义或产品目录。不强求本轮将全部工具迁入 structured API。

## 7. Release contract

v0.4.0 RC 在版本 bump 后验证：tag 模拟值与 pyproject、installed wheel/sdist metadata、runtime __version__ 严格一致；确定性 pytest、RH1 static gate、compile、twine、clean wheel/sdist install、core/mootdx/baostock/mcp 独立 profiles、console scripts、实际 consumer canaries 有证据。live 单源探针报告保留为 observability，不让 IDC IP/免费源偶发故障成为确定性质量结论。

**RH3-A PASS 只表示发布候选通过；RH3-B 必须另行 Owner 明确授权。** 任何人不得把创建/推送 v0.4.0 tag 当作无副作用验证；tag 会触发 PyPI Trusted Publishing workflow。

## 8. 后续设计与文档变更规则

本文件是追溯设计，不是补签的原始 freeze。后续若需修改必须写明 proposed change、依据、影响的消费方、是否改变公开 contract、受影响 gate 与独立 owner decision；不得因某一阶段已经有测试就删去历史缺口。实现符合性与 gate 审计另见 docs/audits/2026-09-23-v0.4.0-design-conformance-audit.md。
