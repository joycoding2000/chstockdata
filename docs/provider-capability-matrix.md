# Provider × Capability Matrix（v0.4.0 Phase 1.1，持续维护）

健康判定按 **provider + capability** 粒度记录。**同一 provider 的各
capability 不视为整体一致健康**——尤其 mootdx：bars 失败不代表 finance /
xdxr 失败，反之亦然。该保证自 Phase 1.1 起是**运行行为**（真实
`_get_mootdx_client()` 路径回归测试），不再只是 health store 的记录粒度。

三层概念不可混淆：

1. **transport/server readiness** —— TCP + 协议握手（mootdx 所有
   capability 共享；transport 级失败对所有 capability 一致生效）；
2. **provider capability health** —— 逐能力最近一次观察；
3. **routing health** —— fallback 链最终结论（`FetchMetadata.final_status`）。

| Provider | Capability (id) | Role | Health probe | Fallback role | Status |
| --- | --- | --- | --- | --- | --- |
| tencent | `tencent:quote` | 实时快照主源（含 PE/PB/市值） | `probe_quote_provider("tencent")` + quote chain attempt | 链首；失败降级 mootdx | active |
| mootdx | `mootdx:quote` | 实时快照备源（TCP） | `probe_quote_provider("mootdx")` + attempt 埋点；client 接受标准 = factory-only（transport 层） | 第 2 级；失败降级 sina | active |
| mootdx | `mootdx:bars` | 日线 K 线主源（TCP） | `_mootdx_call("bars")` 埋点；服务器选择用 bars readiness canary（结论**仅约束 bars**，落盘 `transport_ok` 层级标注） | K 线链主源；失败降级新浪 K 线 | active |
| mootdx | `mootdx:finance` | F10 财务快照 | `_mootdx_call("finance")` 埋点；client 接受标准 = factory-only；**bars canary 全失败时仍可经 bounded bypass 成功** | 独立能力，不随 bars/quote 失败判死（运行级，测试锁定） | active |
| mootdx | `mootdx:xdxr` | 除权除息 | `_mootdx_call("xdxr")` 埋点；同 finance（factory-only + bypass） | 独立能力，不随 bars/quote 失败判死 | active |
| mootdx | `mootdx:stock_list` | 全市场名称表（名称→代码解析） | `_mootdx_call("stocks")` 埋点；factory-only | 磁盘日缓存优先，失败仅影响名称解析 | active |
| sina | `sina:quote` | 实时快照兜底源 | `probe_quote_provider("sina")` + attempt 埋点 | 链尾兜底 | active |
| sina | `sina:bars` | K 线兜底源（+ 三表） | 待埋点（本轮未迁移） | K 线链尾兜底 | active |
| eastmoney | `eastmoney:datacenter` | 龙虎榜/解禁/资金流等 | 待埋点（刻意不进 live gate：封禁 IDC IP） | 独立能力 | active |
| tdx_vipdoc | `tdx_vipdoc:daily_bars` | 本地官方日线包 | 待埋点 | K 线链本地首选 | active |
| tdx_bridge | `easy_tdx:fund_flow` | L1 资金流/行业排名 | `test_tdx_bridge_health.py` | 独立能力 | active |

## 已埋点 vs 待埋点

- **已埋点（v0.4.0 本轮）**：实时行情链三个 provider capability
  （`tencent:quote` / `mootdx:quote` / `sina:quote`，经
  `quote_chain.fetch_realtime_quotes` + `probe_quote_provider`）+ mootdx 各
  method capability（经 `_mootdx_call` → `capabilities.record_capability_health`）。
- **待埋点（后续轮次）**：daily-bars 链、财务/事件/资金流等 40+ API。
  原实现继续工作；`Status` 列在迁移时逐行更新。

## Live gate 分工

- `tests/test_data_layer_live_smoke.py` —— **routing-chain smoke**（gate）：
  链上有任意一源存活即 green；
- `tests/test_live_capability_probes.py` —— **逐 capability probe**
  （报告，非阻塞）：走 `probe_quote_provider` 单 provider 执行路径，
  单个 probe 只更新自己的 capability health；单个非关键 provider 单点
  失败不 fail 整个 routing gate，但必须在 job 输出中单独可见，禁止被
  fallback 成功掩盖；summary 打印真实最后观察（无 `not_configured` 污染）。

## 历史语义修正记录

- v0.4.0 Phase 1 之前：`_tdx_client_works()`（bars canary）的结论隐含
  "整个 mootdx 健康/不健康"；
- v0.4.0 Phase 1：health store 逐能力记录（但 runtime gating 仍是
  provider-global——bars canary 全失败 → 全局负缓存 → finance/xdxr 被
  禁止）；
- v0.4.0 Phase 1.1：**运行级隔离**——bars canary 推导的负缓存只约束
  bars；其它 capability 在 transport 层可用时走 bounded bypass（factory-only
  选 client，不重扫、不做 canary）。transport 级失败仍全局生效。
