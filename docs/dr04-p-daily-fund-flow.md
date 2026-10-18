# DR04-P 新浪日度资金公共数值合同

实施依据：Owner 在本会话批准的 DR04-P、2026-10-17《DR04 最小日度资金消费者合同与验收方案》及两项后续限定。原合同 SHA-256：`1c7c37b1514032ef08d9714fe8cfa4f722c0f730af1e58608dbc6b45eaffeba1`。P01–P12 的原始表格为验收依据；本文件不替换它。

## 实施步骤

1. 只读核验原合同、70 项证据清单与43份请求原文哈希；将 P 测试需要的30份响应及日历复制为 fixture，记录原请求时间及哈希。已完成，无联网。
2. 先写公共入口 P01–P12 确定性测试并确认缺失入口导致失败，再新增独立 `daily_fund_flow.py` 及包级公开导出。金额使用 Decimal 解析并以字符串跨 JSON 边界。
3. 执行12组合同测试、相关既有回归、实际 diff 检查，记录证据。通过只形成 PASS_CANDIDATE；停在 Owner Review，不提交。

## 接口设计

`get_sina_daily_fund_flow(exchange, ticker, *, target_date=..., calendar=...)` 请求目标日及此前四个已完成市场交易日；或用 `start_date=..., end_date=...` 请求闭区间。

调用方提供 `FundFlowCalendar`（完整交易日集合、覆盖区间、已完成截止日、来源、版本、qualified），本入口不隐式访问其他源生成日历。资格是调用方提供的证据声明，不由类名自动认证；日历缺失/不合格时返回 UNKNOWN，不能推断工作日或最近五条。证券适用性保持 UNKNOWN。目标日不能超过日历已完成截止日或当前本地日期。

`FundFlowBudget` 明确页数、请求次数、重试次数、墙钟与单次超时上限。每个 HTTP 尝试（包括最终第一页锚复核）计入请求预算，禁止重定向和隐藏重试。多页完成须额外复核第一页内容锚；仅表示两次观测一致，源端冻结快照保证仍 UNKNOWN。异常保留部分行、缺口及停止原因，不缩短目标窗。

结果含目标日期逐日 `records`、区间外 `extra_records`、非法日期等 `anomalies`、请求尝试及原文证据、覆盖汇总、UTC获取时间、观测ID和哈希。原始数值零计入数值完整，经济语义 UNKNOWN，不计入语义可用数；非零的语义可用仅指本供应商字段可解释，不证明策略适用性、终局或 PIT。

不建立缓存或数据库。可显式传入同请求、同日历的 `previous_observation`，只附带先前观测证据，供调用方审计旧缓存和新失败；不会将旧值提升为本次成功。两次结果及其原文分别保留，原文哈希变化不推断源端修订；源端首次可知、修订时间及终局状态均 UNKNOWN。

现有 `get_fund_flow(...)->str` 与通用 FetchResult 不修改。没有 M 阶段、全市场、S08 或历史回测资格结论。

## 消费示例

以下日历仅用于演示已保存 fixture 的五日窗；实际消费须传入消费者已核验、覆盖整个请求区间的市场日历。

```python
from decimal import Decimal
from chstockdata import FundFlowCalendar, FundFlowBudget, get_sina_daily_fund_flow

calendar = FundFlowCalendar(
    trading_days=('2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16'),
    source='Owner-reviewed DR04 calendar fixture',
    version='e1d23576ebbb8ac60e79cc9f321330c844bad4e2e43305fb48389bf602ff86cf',
    covered_start='2026-10-12', covered_end='2026-10-16',
    completed_through='2026-10-16', qualified=True,
)
result = get_sina_daily_fund_flow(
    'SH', '600000', target_date='2026-10-16', calendar=calendar,
    budget=FundFlowBudget(max_pages=16, max_requests=20, max_seconds=30, retries=1),
)
for row in result.records:
    amount = Decimal(row['amount']) if row['amount'] is not None else None
    print(row['business_date'], row['status'], amount)
payload = result.to_dict()  # 可直接 JSON 序列化，金额仍是十进制字符串
```

历史模式改用 `start_date`、`end_date`，两者与 `target_date` 互斥；日历须覆盖完整请求区间。输入证券格式/日期/预算错误抛 `ValueError`，源故障返回结构化部分结果。

`records` 按目标日升序，每日主要状态互斥，`coverage.counts` 之和等于分母。`COMPLETE` 只代表该窗数值完整及所需分页检查通过，原始零依然语义 UNKNOWN。无合格日历为 `UNKNOWN`，分母为 null。缺日/缺值/冲突/失败为 `PARTIAL`；详情见 `pagination.stop_reason`、`attempts` 和 `anomalies`。HTTP 成功、数值完整、日期新鲜度与语义可用是独立维度。

每份响应通过 `responses[index]` 关联页码、字节 SHA-256、base64 原文及获取时间；行出处给出 response_index 和零起始 row_index。原始 JSON 数值 token 以字符串保留并标 `raw_type=number`，raw_record 中用 `{json_number: token}` 保持原类型；字符串保持原字符串。`value_sha256` 只识别目标日规范状态/金额变化；不是源端修订证明。每次调用使用新 observation_id。

请求预算包含失败重试与锚复核；页数只计数据页（包括观察到的空页），`source_row_count` 不计锚复核。超时设置不超过剩余墙钟；每次 HTTP 返回、分页处理后均检查墙钟，超时不报完整。底层同步网络调用遵循 requests 的连接/读超时，墙钟是接收结果及新增请求的截止预算，不是操作系统调用的硬实时抢占保证。

`previous_observation` 仅接受完全相同证券、源/字段/合同、模式/日期集合及日历身份的结果，否则输入报错。旧数据只在该字段中交付，保留原 fetched_at、质量、业务日、原文和观测身份；本次失败及 REQUEST_UNRESOLVED 不被抹去。本模块不读取或写入任何持久缓存。
