# chstockdata 架构（v0.4.0 development）

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

## 2. Providers 与 Capabilities

健康判断的最小单位从 **provider 整体** 升级为 **provider + capability**：

- `ProviderCapability(provider, capability)`（`capabilities.py`），稳定
  id 形如 `mootdx:bars`、`tencent:quote`；
- 命名描述数据操作（quote / bars / finance / xdxr ...），**不绑定**
  任何下游 tool name；
- 同一 provider 的各 capability **互不代表**：`mootdx.bars` 失败不会把
  `mootdx.finance` / `mootdx.xdxr` 判死（有隔离回归测试保证）；
- 逐能力健康观察记录在进程内 store（`record_capability_health` /
  `capability_health_snapshot`），供 live gate 与诊断分项报告。

历史语义澄清：`a_stock._tdx_client_works()`（bars canary）是**服务器
选择连通性验证**，不是 mootdx 能力健康判定；mootdx 各能力的健康按
`mootdx:<method>` 在 `_mootdx_call` 内逐能力记录。

## 3. Provider Health 与 Routing Health

两个正交概念，分别落在两处：

| 概念 | 回答的问题 | 载体 |
| --- | --- | --- |
| Provider Health | 某个 provider 的某个 capability 现在是否正常？ | `capabilities.CapabilityHealth` + `FetchAttempt.status` |
| Routing Health | 用户请求经完整 fallback 链最终是否成功？ | `FetchMetadata.final_status`（从 attempts 派生） |

例：腾讯 quote 挂、新浪 quote 成功 →
`tencent:quote = failed`（provider 级，可见、不隐藏），
同时 `routing = success, final_provider = sina`（路由级）。

## 4. Structured Result（fetch_result.py）

```python
FetchAttempt   # 一次 provider 调用：provider / capability / status /
               # started_at / elapsed_ms / record_count / error_type
FetchMetadata  # capability / final_provider / retrieved_at /
               # observed_at / data_as_of / stale / partial / limitations /
               # attempts（派生：final_status / degraded / failed_providers）
FetchResult[T] # data + metadata，generic
```

关键语义：

- **status 枚举**：`success` / `normal_empty` / `failed_network` /
  `failed_rate_limit` / `failed_structure` / `not_configured` / `skipped`。
  `normal_empty`（源正常返回但无可用数据）与网络/结构失败严格区分，
  前者是终端健康观察、后者触发降级；
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
- 每次 provider 调用产出 `FetchAttempt` 并同步逐能力健康观察；
- `a_stock._get_realtime_quotes` 是其上的兼容 wrapper（保持历史返回
  形状与 `_RealtimeQuoteUnavailable` 异常契约）；
- `get_realtime_snapshot` 输出不变。

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
  被当作 truthy 接受，非法调用不部分污染全局配置）。
