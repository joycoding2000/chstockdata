# chstockdata 架构（v0.4.0 Phase 2）

> 基线：v0.3.0（commit `143eb5a`）已被 `TradingAgents-AStock-Private` 与
> `systematic-investing-os` 作为冻结 provider baseline 消费。本文档描述
> v0.4.0 在该基线上的**增量架构**——全部新增为 additive，不改变现有
> public API。

## 1. 分层总览

```text
┌─────────────────────────────────────────────────────────────┐
│ Consumers（不修改）：TradingAgents / systematic-investing-os │
└──────────────────────────┬──────────────────────────────────┘
                           │ 现有 public API（get_stock_data /
                           │ get_realtime_snapshot / ...）
┌──────────────────────────▼──────────────────────────────────┐
│ Legacy compatibility layer                                   │
│  a_stock.get_realtime_snapshot → _get_realtime_quotes        │
│  a_stock.get_stock_data (raw/D) → daily_bars.fetch_daily_bars│
│  （wrapper / renderer，行为契约不变）                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Structured core（v0.4.0 新增，additive）                      │
│  quote_chain.fetch_realtime_quotes → FetchResult[T]          │
│  daily_bars.fetch_daily_bars → FetchResult[pd.DataFrame]     │
│  fetch_result: FetchAttempt / FetchMetadata / FetchResult[T] │
├──────────────────────────────────────────────────────────────┤
│ Capability health（v0.4.0 新增）                              │
│  capabilities: ProviderCapability / 逐能力健康观察            │
├──────────────────────────────────────────────────────────────┤
│ Provider adapters（既有实现，未迁移部分保持原样）             │
│  a_stock: _tencent_quote / _mootdx_* / _sina_* / ...         │
└──────────────────────────────────────────────────────────────┘
```

## 2. Providers 与 Capabilities（三层 readiness/health 模型）

v0.4.0 Phase 1.1 起，以下三个概念**分别建模**、不可混淆：

```text
① transport / server readiness —— TCP 可连 + Quotes.factory 协议握手可建
   （mootdx 内部：全表扫描的两级结论；所有 capability 共享这一层）
② provider capability health —— 某个 provider 的某个 capability 最近一次
   观察结果（capabilities.py 逐能力 store；mootdx:bars 失败不代表
   mootdx:finance 失败——运行级隔离见 §2.1）
③ routing health —— 用户请求经完整 fallback 链的最终结论
   （FetchMetadata.final_status，从 attempts 派生）
```

- `ProviderCapability(provider, capability)`（`capabilities.py`），稳定
  id 为**冒号分隔**的复合标识 `"<provider>:<capability>"`（如
  `mootdx:bars`、`tencent:quote`）；
- 命名描述数据操作（quote / bars / finance / xdxr ...），**不绑定**
  任何下游 tool name；
- 同一 provider 的各 capability **互不代表**：`mootdx.bars` 失败不会把
  `mootdx.finance` / `mootdx.xdxr` 判死（运行行为级隔离，有真实
  `_get_mootdx_client()` 路径的回归测试保证，见 §2.1）；
- attempt status（fetch 层）与 capability health status（health 层）经
  **唯一映射** `fetch_status_to_health_status()` 对齐——同一次观察在
  两层不得冲突（如 `VendorNoDataError` → attempt `normal_empty` +
  health `normal_empty`，而不是 health `failed`）。

### 2.1 mootdx readiness 分层（运行级隔离）

Phase 1 曾存在"观测隔离但运行未隔离"：bars canary 全失败 → 全局负缓存 →
finance/xdxr 从未被尝试。Phase 1.1 修复（`a_stock._get_mootdx_client`）：

```text
bars canary 全失败
    ↓（旧）全局负缓存 → 所有 capability 被禁止
    ↓（新）结论分层落盘：transport_ok=True 的 canary 推导结论
          → bars 类请求快速失败（保留防重扫保护）
          → 其它 capability 走 bounded bypass：
            仅在已确认 transport 可达的候选表上 factory-only 选 client
            （不重扫 TCP、不做 bars canary），由真实 capability 调用
            自我验证
```

保留的历史可靠性约束（全部不变）：工具上下文探测预算
（`TDX_TOOL_PROBE_BUDGET_SECONDS`）、磁盘负缓存 + 指数退避、有界扫描、
候选重选、BESTIP 保护、`_mootdx_call_lock`、`TDX_MIN_INTERVAL`。
transport 级失败（无一台能建 client）仍然对所有 capability 一致生效。

`_tdx_client_works()`（bars canary）语义：**服务器选择连通性验证** +
bars readiness canary，不是 mootdx 能力健康判定。

## 3. Provider Health 与 Routing Health

两个正交概念，分别落在两处：

| 概念 | 回答的问题 | 载体 |
| --- | --- | --- |
| Provider Health | 某个 provider 的某个 capability 现在是否正常？ | `capabilities.CapabilityHealth`（经 `fetch_status_to_health_status` 与 attempt 状态对齐） |
| Routing Health | 用户请求经完整 fallback 链最终是否成功？ | `FetchMetadata.final_status`（整个请求的结论，从 attempts 按优先级派生，而非机械取最后一条 attempt） |

例：腾讯 quote 挂、新浪 quote 成功 →
`tencent:quote = failed`（provider 级，可见、不隐藏），
同时 `routing = success, final_provider = sina`（路由级）。

## 4. Structured Result（fetch_result.py）

```python
FetchAttempt   # 一次 provider 调用：provider / capability / status /
               # started_at / elapsed_ms / record_count / error_type
FetchMetadata  # capability / final_provider / providers_used /
               # retrieved_at / observed_at / data_as_of / stale / partial /
               # limitations / attempts（派生：final_status / degraded /
               # failed_providers）
FetchResult[T] # data + metadata，generic
```

关键语义：

- **status 枚举**：`success` / `normal_empty` / `failed_network` /
  `failed_rate_limit` / `failed_structure` / `not_configured` / `skipped`。
  `normal_empty`（源正常返回但无可用数据）与网络/结构失败严格区分；
- **normal_empty 是事实，不是策略**：generic `FetchAttempt` 只描述
  "provider 应答了但没有可用数据"；**是否因此停止路由由各 capability 的
  routing engine 决定**（quote 链空了继续 fallback；停牌快照/公司行为的
  空结果可能就是合法终端答案）。模型不提供 `is_terminal()` /
  "no fallback needed" 之类的路由判断 API；
- **multi-provider 结果**：per-code fallback 可混合多源。
  `providers_used` 按首次贡献顺序列出所有贡献 provider；
  `final_provider` 仅在**恰好一个** provider 贡献时等于它，混合/为空时
  为 `None`（不变量由 `FetchMetadata.__post_init__` 强制，序列化包含
  两字段）——`final_provider="tencent"` 永不暗示整个结果来自腾讯；
- **partial**：请求的一部分 code 未满足时 `partial=True` 并附
  `missing_quotes:<code>` limitations；路由结论仍可为 success；
- **时间分离**：`retrieved_at`（我们何时抓到）与 `observed_at` /
  `data_as_of`（数据本身何时有效）是两个独立字段，永不混淆；
- **consumer-neutral**：不含 `original_tool` / `referenced_by` /
  `evidence_domain` / research 域语义。TradingAgents 专用模型
  （`provenance.EvidenceEnvelope`、`provenance.ProviderAttempt`）原样
  保留，两者互不绑死（attempt 类型刻意命名 `FetchAttempt` 以免混淆）。

## 5. Routing（structured vertical slices）

v0.4.0 目前有两条真实数据路径迁入 structured core：

### 5.1 实时行情（Phase 1，quote）

实时行情链（Tencent → mootdx → Sina）：

- 编排逻辑位于 `quote_chain.fetch_realtime_quotes`，per-code fallback、
  stale 候选、stale last-resort 语义逐字保留；
- 每次 provider 调用产出 `FetchAttempt` 并经唯一映射同步逐能力健康观察；
- `a_stock._get_realtime_quotes` 是其上的兼容 wrapper（保持历史返回
  形状与 `_RealtimeQuoteUnavailable` 异常契约）；
- `get_realtime_snapshot` 输出不变；
- **隔离单 provider 探针**：`quote_chain.probe_quote_provider(provider, ...)`
  只调用一个 provider、只更新该 capability 的 health；未参与 probe 的
  provider **不会**被写成 `not_configured`、不会覆盖已有观察。live gate
  的 `tests/test_live_capability_probes.py` 使用该路径。

### 5.2 历史日线（Phase 2，daily bars）

raw/D 历史日线链（本地 vipdoc 包 → mootdx TCP → 新浪 HTTP）是第二条
structured vertical slice：

```text
tdx_vipdoc:daily_bars ──► mootdx:bars ──► sina:bars
        │                     │               │
        ▼                     ▼               ▼
        daily_bars.fetch_daily_bars()   （唯一权威 provider 编排）
        │  FetchAttempt + capability health（每次真实调用）
        ▼
        FetchResult[pd.DataFrame]       （canonical bars schema）
        ▼
        a_stock.get_stock_data()        （兼容 renderer，输出契约逐字冻结）
```

- **canonical schema**（测试锁死，`tests/test_daily_bars_schema.py`）：
  必需列 `Date/Open/High/Low/Close/Volume`（`Date` 归一化到日粒度、
  双端闭区间窗口）；可选列 `pre_close`（仅当贡献 provider 真实提供——
  现为 vipdoc `.day` 文件语义"完整文件内前一交易日原始 Close"，
  **引擎绝不派生**，不提供即缺列/NaN）；`Amount` 不进 canonical bars
  （legacy raw/D 输出从未暴露该列）；
- **units**：provider 原生透传，provider boundary 不做任何 ×100/÷100
  换算（regression test 锁死）。记录口径：vipdoc Volume=股、新浪
  Volume=股；mootdx 保持 TDX wire `vol`（沿用 `adjusted_bars` 口径红线：
  跨源绝对值不作横向比较）；
- **行序**：单源 base 帧保持 provider 原生行序（vipdoc/新浪升序；mootdx
  为 wire 序，未做库内排序）；合并（supplement）帧按 legacy
  `_merge_ohlcv` 语义去重 keep-last + 升序。renderer 不重排；
- **routing policy（bars engine 内，不污染 generic core）**：
  - `not_configured`（vipdoc 被配置禁用 / 本地包或文件缺失）是事实，
    不是硬失败——不构成 degraded，路由继续；
  - vipdoc 文件损坏/不可读 → `failed_structure`（local 源不套网络语义）；
  - vipdoc 空窗口 / 超过 `vipdoc_history_max_staleness_days`（交易日历
    无法确认市场无更新 session，DEC-P1-27）→ `normal_empty`，路由继续；
  - 首个可用帧即 base（单一数据源事实层；唯一例外是 legacy 本就存在的
    **尾部补齐 contract**：base 末根落后请求截止时新浪整窗拉取并合并、
    重叠日新浪行胜出；补齐失败保留 base 并标记 `degraded`）；
  - 全部 provider `normal_empty` → routing `normal_empty`；全部硬失败 →
    `DailyBarsRoutingError`（脱敏，不带 vendor 细节）；
- **stale policy**：覆盖缺口超过 `_OHLCV_MAX_STALENESS_DAYS`（14 天）
  仍作为成功结果返回（`metadata.stale=True` + limitation），由 legacy
  renderer 输出 `historical_ohlcv_stale` 标记——沿用既有行为，不改宽
  也不改严；
- **时间分离**：`data_as_of` = 返回 bars 在请求窗口内的最后业务日期
  （bars 自身的 business date，可可靠派生，本轮实化）；`observed_at`
  保持 None（该链无 provider 观察时间戳，不伪造）；
- **`get_stock_data`（raw/D）** 委托 structured engine，自身退化为兼容
  renderer：signature、列顺序、`# Data source` 标注（含
  `+ sina HTTP supplement` 后缀规则）、空结果/双源失败/stale 文案逐字
  冻结（`tests/test_daily_bars_legacy_compat.py`）。非 raw / 非 D
  （qfq/hfq/W/M）本轮仍走既有 mootdx→sina 直连链；
- **`_get_close_on_date`** 直接读 structured bars（同链、同窗口、同
  round(2) 值），不再解析 formatted 文本；
- **隔离单 provider 探针**：`daily_bars.probe_daily_bars_provider` 与
  quote 探针同分工——live gate 里 `sina:bars` / `mootdx:bars` 为观测性
  非阻塞项，单个失败必须真实显示、不得被 routing green 掩盖；
  `tdx_vipdoc` 是本地数据路径，不进 CI live probe。

其余 40+ API 路径（财务、事件、日历、停牌……）仍走原实现，按后续
轮次逐条迁移。`get_ohlcv_frame_cached`（`_load_ohlcv_astock`：CSV 日缓存
+ mootdx→sina）仍是**第二套独立 OHLCV orchestration**（含独立缓存语义），
记录为 Phase 2.x/Phase 3 debt，本轮不合并。

## 6. Consumer Boundary（消费边界）

chstockdata 只描述：provider / capability / attempt / retrieval / source
/ timing / partial / stale / error / limitations。

以下语义**永远不进入** generic core，由消费方自行建模：
ResearchDomain、DataHealth、ResearchFact/Material/Snapshot、coverage
disposition、analyst、bull、bear、research confidence、portfolio、
backtest、strategy；以及 TradingAgents-specific 的 `original_tool`、
`referenced_by`、`evidence_domain`、consumer capability_id。

## 7. 兼容性承诺

- v0.3.0 public API 不删除、不改名、不改签名；
- `TradingAgents` 与 `systematic-investing-os` 无需任何修改；
- `provenance`（EvidenceEnvelope / capability resolver 注入）作为
  compatibility layer 原样保留；
- 配置层 `configure()` 收紧为 type/value 校验 + 原子提交（非法值不再
  被当作 truthy 接受，非法调用不部分污染全局配置）；
- Phase 1.1 语义修正（`FetchAttempt.is_terminal` → 仅 `is_success` /
  `is_failure`；`FetchMetadata.final_provider` 不变量 + `providers_used`）
  仅触及 Phase 1 新增且未发布（未 release）的 structured core API，
  对 v0.3.0 消费面零影响。

## 8. 明确不做（Phase 1.1 范围外）

- capability health 持久化（health 观察有时效性，持久化需先定义 TTL /
  过期 / 冷启动 / 跨进程优先级；趋势走 GitHub Actions 日志）；
- `data_as_of` vendor 实化（quote vendor 时间戳映射留给单独任务）；
- daily bars / calendar / corporate actions 的 structured 迁移。
