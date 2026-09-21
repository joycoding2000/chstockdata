# Phase 2 实施前审计：daily bars 真实行为（改造前基线）

> 审计对象：`f37f6fd`（v0.4.0 Phase 1.1.1）上的 `get_stock_data()` raw/D daily-bars
> 真实链路。本文是 Phase 2 动工前的行为快照，用于约束"保持真实行为"，不描述
> 改造后架构。

## 1. 改造前真实 route（`a_stock.get_stock_data`，adjust="raw" & period="D"）

```text
_load_vipdoc_ohlcv_frame(code, start, end)            # 本地 vipdoc，零网络
    ├─ vipdoc_history_enabled=False            → None（继续在线链）
    ├─ 文件缺失 / 读取异常 / 区间无记录         → None（继续在线链）
    ├─ 末根 bar 落后 end_date > max_staleness(5d)
    │   └─ 交易日历确认本地已到市场最新 session → 保留本地（DEC-P1-27）
    │   └─ 日历无法确认                        → None（继续在线链）
    └─ 命中 → 6 列帧（Date/Open/High/Low/Close/Volume；Amount 刻意丢弃）
_fetch_mootdx_bars(code, offset=800)                  # 无窗口过滤，取最近 800 根
    └─ 失败 → _sina_kline_fallback(code, start, end, fallback_from="mootdx")
              └─ 空结果/异常 → 「K线数据获取失败：mootdx和新浪备用源均不可用…」
_supplement_stale_ohlcv_with_sina(code, df, end, start)   # 无条件执行
    └─ base 末根 < end_date 时：新浪整窗拉取 [start,end] 并 _merge_ohlcv
       （concat + 日期去重 keep="last"（新浪行覆盖重叠日）+ 升序排序）
df[(Date>=start) & (Date<=end)]                        # 双端闭区间过滤
df.empty → 「No data found for A-stock …」
_ohlcv_coverage 超过 14 天 → 「[数据缺失] historical_ohlcv_stale: …」
adjust!=raw 或 period!=D → get_adjusted_bars（不走 vipdoc）
```

关键事实：

1. **stitching contract 已存在**：base 未到 end_date 时，新浪按整窗
   `[start,end]` 拉取并与 base 合并，重叠日期 **新浪行胜出**
   （`_merge_ohlcv` keep="last"）。这不是"只补尾部缺口"，是全窗覆盖。
2. **`_fetch_mootdx_bars` 不做日期过滤**（最近 800 根），窗口过滤发生在
   supplement 之后、renderer 内。
3. 空 mootdx 结果会以异常形式进入新浪 fallback（`_normalize_mootdx_bars_frame`
   对空输入 raise）。
4. legacy label：`"vipdoc local (TDX official hsjday package)"` /
   `"mootdx (TCP)"` / `"sina HTTP (fallback)"`；supplement 实际推进了末根
   日期才追加 `" + sina HTTP supplement"`。
5. raw/D 主路径（`_fetch_mootdx_bars`）调用 `_get_mootdx_client()`（无显式
   request_capability → 保守按 bars readiness 语义）+ `_mootdx_call("bars")`，
   后者已写 `mootdx:bars` capability health（Phase 1.1 语义）。

## 2. Provider 数据形状

| provider | 列 | Date 语义 | Volume 单位 | Amount | pre_close |
| --- | --- | --- | --- | --- | --- |
| tdx_vipdoc | Date/Open/High/Low/Close/pre_close/Volume/Amount（`load_vipdoc_daily`），raw/D 路径丢弃 Amount | `.day` 文件 uint32 YYYYMMDD → 本地时区业务日；文件内升序、去重 keep-last | 股（`vipdoc_history.parse_day_file` 文档：volume uint32 股） | 元（float32，raw/D 路径丢弃） | **有**：完整文件内前一交易日原始 Close（文件语义，非除息调整前收盘，非引擎派生） |
| mootdx bars | Date/Open/High/Low/Close/Volume（`_normalize_mootdx_bars_frame` 只保留 6 列） | wire datetime → normalize 到日粒度；**wire 行序未在库内排序/翻转**（mootdx 0.11.7 `to_data`、tdxpy parser 均不排序） | TDX wire vol（`get_volume` 浮点解码）；项目红线（`adjusted_bars.py`）：跨源绝对值不作横向比较 | 归一化时丢弃 | 无 |
| sina bars | Date/Open/High/Low/Close/Volume（`_sina_kline_fallback`） | API `day` 字符串 → to_datetime；窗口过滤在 provider 内做 | 股（int） | 无 | 无 |

单位结论（按项目既有约定，不引入新换算）：**provider-native passthrough**。
`adjusted_bars.py` 口径红线明确"Volume/Amount 不随价格因子缩放、跨源绝对值
不作横向比较"。Phase 2 canonical path 不引入任何 ×100/÷100 换算，只锁死
"值不被改变"（unit regression test）。mootdx wire vol 的绝对单位（股/手）
本机 TDX 不可达无法实测，列为遗留验证项。

行序结论：vipdoc 升序（文件序）、sina 升序（API 序）、merge 后升序
（`_merge_ohlcv`）；mootdx 单独成 base 时行序 = wire 序（库内无排序）。
canonical 引擎**不重排单源 base 帧**（合同冻结优先），merge 语义保持
`_merge_ohlcv` 原样。

## 3. Cache 语义

- raw/D structured 目标路径本身无缓存（vipdoc 即本地包；mootdx/sina 每次实拉）。
- `_load_ohlcv_astock`（CSV 日缓存，mootdx→sina）是**另一条独立
  orchestration**（`get_ohlcv_frame_cached` / 指标 fallback 用），Phase 2
  不合并、不改动 → 记为 Phase 2.x/3 debt。
- vipdoc manifest/新鲜度（`vipdoc_history_status`）与本链路只通过
  `vipdoc_history_max_staleness_days`（默认 5）交互。

## 4. 解析 `get_stock_data()` 文本的内部函数

- `_get_close_on_date()`（a_stock.py）——confirmed：调 `get_stock_data(code,
  d, d)` 后从 CSV 行 `parts[4]` 解析 Close（renderer 已 round(2)）。
  Phase 2 尾部 follow-up 候选：直接改用 structured bars（同窗口、raw、
  round(2) 对齐），配 regression test。
- 其它内部函数未发现解析 `get_stock_data` 文本的路径。

## 5. Status 语义映射（structured 层）

| 真实状态 | FetchAttempt status | 说明 |
| --- | --- | --- |
| vipdoc 被配置禁用 / 本地包或文件缺失 | not_configured | local 源"未就绪"，非网络 |
| vipdoc 文件损坏 / 读取异常 | failed_structure | OSError 在 adapter 边界包装 |
| vipdoc 区间无记录 / 超过 staleness policy | normal_empty | 事实；路由继续 |
| mootdx transport/取数失败 | failed_network | 复用 Phase 1.1 readiness |
| mootdx 空结果 | normal_empty | `_normalize_mootdx_bars_frame` 空输入 raise 改映射 VendorNoDataError（最小修改） |
| mootdx 列缺失/坏日期 | failed_structure | ValueError 保持 |
| sina HTTP 失败 | failed_network | |
| sina 空结果 | normal_empty | adapter 包装 raise |

normal_empty routing policy（bars engine 内）：vipdoc/mootdx normal_empty →
继续下一 provider；base 确立后 supplement 的 normal_empty 只是不补，不影响
成功结论。

## 6. 已确认不动的外围

- 非 raw / 非 D（qfq/hfq/W/M）路径继续直连 mootdx→sina（本 Phase 不迁移）。
- `_load_ohlcv_astock` / `get_ohlcv_frame_cached` 保持原样。
- `mootdx:finance` / `xdxr` 等 capability 隔离不受影响（engine 只写
  被尝试 provider 的 capability health）。
