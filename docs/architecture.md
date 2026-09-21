# chstockdata 架构（v0.4.0 Phase 1.1）

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
│  （wrapper，行为契约不变）                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ Structured core（v0.4.0 新增，additive）                      │
│  quote_chain.fetch_realtime_quotes → FetchResult[T]          │
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

## 5. Routing（实时行情 vertical slice）

实时行情链（Tencent → mootdx → Sina）是 v0.4.0 迁入 structured core 的
第一条真实路径：

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

其余 40+ API 路径（daily bars、财务、事件……）仍走原实现，按后续
轮次逐条迁移；`get_stock_data` 的 daily-bars 链本轮未迁移。

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
