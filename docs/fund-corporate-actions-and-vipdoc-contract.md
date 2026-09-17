# ETF 分红、停牌快照与 `pre_close` 口径

## Phase 0 探测结论（2026-09-17）

- `https://api.fund.eastmoney.com/f10/lsfh` 当前返回 `ErrCode=4` / `404`，不作为实现端点。
- 采用东财基金 F10 的两个公开端点：
  - `fundf10.eastmoney.com/fhsp_{code}.html`：历史分红表，提供权益登记日、除息日、每 10 份（或每份）金额、发放日；
  - `api.fund.eastmoney.com/f10/FHGG`：分红公告列表，提供公告日和公告 ID。
- 实测窗口 `2015-01-01` 至 `2022-12-31`：510300 有 8 条、511010 有 1 条；159915 与 518880 的 F10 分红表返回“暂无分红信息”，映射为 `normal_empty`，不是请求故障。

## 分红契约

`get_fund_corporate_actions` 将上游金额统一为 `cash_dividend.unit =
"per_10_shares"`；若页面字段是每份金额，vendor 内先乘 10。FHSP 与 FHGG
无法匹配时保留记录但将 `coverage` 标记为 `partial`，公告日保持缺失，不推断。

## 停牌快照契约

`RPT_CUSTOM_SUSPEND_DATA_INTERFACE` 硬性按 500 行分页。vendor 读取
`ceil(result.count / 500)` 页，最多 12 页；聚合后少于 `count` 时返回显式
`failed_structure/snapshot_truncated`。同一进程内以快照日缓存完整聚合结果，
所以同日多个 ETF 查询不会重复下载市场快照。

## `pre_close` 语义

`load_vipdoc_daily` 先读取完整 `.day` 文件，再按请求窗口过滤；`pre_close` 是
文件内前一交易日的原始 `Close`。它不是除息日当天交易所口径的“前收盘价”，
除息日两者可以不同。文件没有更早记录时保留缺失，绝不 fabricate；当前质量门
需要该字段，但 M0 kernel 不消费它。
