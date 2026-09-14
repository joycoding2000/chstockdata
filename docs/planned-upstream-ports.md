# chstockdata 反向移植上游 a-stock-data 独有端点 — 实施方案

- **状态**: 已实施（2026-09-14 当日完成 P0/A/B1–B4 与集成，见 CHANGELOG 0.2.0）
- **目标版本**: chstockdata 0.2.0（tag `v0.2.0` → publish.yml）
- **上游基线**: `simonlin1212/a-stock-data` v3.7.1（commit `f90d678`，十一层 / 54 端点 / 19 源）
- **背景**: 私仓 CR `CR-EXTRACT-FREE-DATA-LAYER.md` §14 后续候选"反向移植上游
  a-stock-data 独有端点（ETF 期权、涨跌停池、CYQ 筹码等）"
- **已确认范围（2026-09-14 用户决策）**: A 档 + B1–B4；CYQ 换手率输入采用
  `baostock` optional extra；本文档落 chstockdata 仓库

---

## 1. 范围

### 1.1 本轮实施

| 编号 | 端点 | 上游来源 | 新模块/函数 |
|---|---|---|---|
| A1 | ETF 期权：合约清单 / T 型报价 / 希腊字母+IV | 新浪 hq.sinajs.cn | `etf_options.py` |
| A2 | 涨停池明细：昨日涨停池 + ZT/ZB/DT 个股级明细 + 同花顺涨停质量 | push2ex + 同花顺 | `limit_up.py` |
| A3 | CYQ 筹码分布（获利比例/平均成本/成本区间/筹码峰） | 本地算法 + baostock 换手率 | `chips.py` |
| B1 | 全市场龙虎榜（当日全量 + 净买额排名） | 东财 datacenter | `a_stock.py` 增函数 |
| B2 | 板块资金流（行业/概念/地域 × 今日/5日/10日，主力净额版） | 东财 bkzj（非 push2） | `board_flow.py` |
| B3 | 互动易问答（投资者提问 + 公司回复） | 巨潮 | `investor_qa.py` |
| B4 | 同花顺热榜 + 东财人气榜 + 个股概念命中 | 同花顺 + 东财 emappdata | `hot_rank.py` |

### 1.2 明确不做（附裁决/技术理由）

| 端点 | 理由 |
|---|---|
| 东财日内异动池（`em_price_anomaly` / `count`） | 私仓 roadmap-checklist「勿重评清单」已裁决为**产品硬边界**；且引入新域名风控面 |
| 申万行业变迁史 | DEC-P1-23 已驳回（唯一消费者随历史复盘消失）；需 xlrd 新依赖 |
| 分钟/分时/逐笔/集合竞价 | 产品硬边界 |
| push2/push2his 依赖项（分钟资金流、120 日 push2 版、四档完整字段、人气榜 push2 hydration） | 违背 2026-08-17 push2/push2his 解耦铁律与源码扫描守卫（`tests/test_astock_push2_source_scan.py`） |
| 百度 K 线、新浪复权因子 | 本仓已有等价或更优实现（`adjusted_bars.py` 新浪 hfq.js 因子） |
| baostock 估值历史 / 上市退市日独立端点 | 东财估值序列（`get_valuation_history`）与交易所退市名单（`get_delisting_info`）已覆盖；baostock 仅作为 A3 输入依赖 |
| 社融（人民银行）、五档盘口、官方备用源（B5–B7） | 延后，见 §9 |

---

## 2. 调查证据（2026-09-14）

### 2.1 活体探测（串行；东财请求间隔 ≥1.6s，共 11 个请求）

| 探测项 | 结果 | 对方案的含义 |
|---|---|---|
| 东财 `RPT_VALUEANALYSIS_DET` | 200；`600519` 2112 行；列为 PE/PB/PS/PCF/PEG、市值、股本；**无换手率/ST/停牌** | CYQ 的 `turn` 无法复用估值链路；采用 baostock extra（上游路径），不用 `FREE_SHARES_A` 推算 |
| `push2ex getYesterdayZTPool` | 200；`date=20260911` 返回 35 行；字段 `c/m/n/p/ztp/zdp/amount/ltsz/tshare/hs/zf/zs/yfbt/ylbc/hybk/zttj` | A2 昨日涨停池可 1:1 移植，与 `market_breadth.py` 现有 push2ex 通道同源 |
| `data.eastmoney.com/dataapi/bkzj/getbkzj` | 200；`key=f62/f164/f174` 均可用（行业/概念/地域，496~504 行）；**仅返回 `f12/f13/f14` + 所查 key 单字段**，`fields` 参数被忽略 | B2 可做「主力净额 today/5d/10d」版；四档/净占比/领涨股不可得，须在返回中明示 |
| 新浪期权月列表（cate=50ETF） | 200；`["2026-09","2026-09","2026-10","2026-12","2027-03"]`（首条重复当月） | 上游"丢首个"逻辑改为**按返回去重**实现 |
| 新浪 T 型报价 `CON_OP_10010974` | 200（GBK）；51 字段，与上游索引逐位吻合（`v[37]`=名称、`v[41]`=成交量、`v[42]`=成交额） | A1 可 1:1 移植 |
| 新浪希腊字母 `CON_SO_10010974` | 200；17 字段；`raw[1:4]` 确为 3 个空串；`v=[raw[0]]+raw[4:]` 正确；IV=0.1484 | 坑与上游记录一致，须编码进解析器 |
| 同花顺热榜 `dq.10jqka.com.cn` | 200；100 行；字段 `order/code/name/rate/rise_and_fall/hot_rank_chg/tag/topic` | B4 可移植 |
| 巨潮互动易两步 | 均 200；`orgId=gshk0001211`，返回 5 行问答（`mainContent/attachedContent/attachedAuthor/pubDate`） | B3 可移植 |
| 人民银行社融索引页 | 200；1999–2026 年份链接可解析（重复两遍） | 延后项 B5 的技术可行性已确认 |

### 2.2 源码比对发现的既有缺陷（本方案 P0 一并修）

1. **ticker 路由静默错票（上游 v3.7.1 同源修复未移植）**：
   `_normalize_ticker`（`src/chstockdata/a_stock.py:121`）先剥后缀再剥前缀，
   `SH000001.SZ` 这类自相矛盾写法被静默接受；`000016.SH` 被归一化为 `000016`
   后按号段路由到深市（实为深康佳 A，上证 50 为 `000016.SH`）。
2. **`tdx_bridge.market_for_code` 缺 `5x→SH`**（`src/chstockdata/tdx_bridge.py:168`）：
   沪市 ETF/LOF（510050/510300/588000/510500）会落入深市分支，导致腾讯/新浪
   实时行情路径失败（有 mootdx 时才兜住）。这是 A1 展示标的行情的前置。
3. **`live-data-gate.yml` 引用的 `tests/test_data_layer_live_smoke.py`
   在本仓不存在**（该文件留在私仓且 import 框架路径），live gate 目前必然失败。

---

## 3. 模块设计

### P0 前置修复（0.5d）

- `_normalize_ticker` / `_get_prefix` 对齐上游 v3.7.1 语义：
  - 显式前后缀与号段矛盾（如 `SH000001.SZ`、`SH600519` 与号段不符）→ fail loud；
  - `5x` → 沪市（ETF/LOF）；
  - `sh` + `000xxx`：本包不支持指数，明确报错"沪市指数非个股"，不再静默查深康佳 A；
  - `sz` + `000xxx` 保持深市个股（平安银行）。
- `live-data-gate.yml`：重建 `tests/test_data_layer_live_smoke.py`
  （import 改 `chstockdata`，补新端点 smoke）。
- `tests/test_astock_push2_source_scan.py`：`_SCANNED` 扩展至全部新模块
  （允许 `push2ex.eastmoney.com` 字面量，禁止 `push2.eastmoney.com` /
  `push2his.eastmoney.com`）。

### P1-A1 `etf_options.py`（1.5d）

```python
def list_etf_option_contracts(underlying: str = "510050", call: bool = True) -> dict[str, list[str]]
def get_etf_option_tquote(code: str) -> dict[str, Any]
def get_etf_option_greeks(code: str) -> dict[str, Any]
def get_etf_option_chain(underlying: str = "510050", month: str | None = None) -> dict[str, Any]  # 复合，可选
```

- 来源：
  - 月列表 `https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName?exchange=null&cate={50ETF|300ETF|科创50ETF|500ETF}`
  - 合约链 `https://hq.sinajs.cn/list=OP_UP_{underlying}{YYMM}` / `OP_DOWN_...`
  - 报价 `https://hq.sinajs.cn/list=CON_OP_{id}`（51 字段）
  - 希腊字母 `https://hq.sinajs.cn/list=CON_SO_{id}`（17 字段，`raw[1:4]` 必须跳过）
- 关键坑（全部要写成守卫/测试）：
  - 响应 GBK，去 `var hq_str_XXX="..."` 壳；必带
    `Referer: https://stock.finance.sina.com.cn/`（否则 403）；
  - 字段数不足（tquote <43、greeks <16）→ `VendorNoDataError`，不得返回半截 dict；
  - underlying 白名单 `{510050, 510300, 588000, 510500}`，合约代码 `^\d{8}$`；
  - 月份列表按返回去重（探测确认首条重复）；
  - `iv` 是小数（0.1484 = 14.84%）；
  - 合约代码统一剥离 `CON_OP_` 前缀后再入参。
- 测试：fixture 解析测试（45 个字段映射断言）、空壳/字段缺失失败闭合、
  月列表去重、未知 underlying 报错。

### P1-A2 `limit_up.py`（1.5d）

```python
def get_limit_up_pool(curr_date: str = "", kind: str = "zt") -> dict[str, Any]
    # kind ∈ {"zt", "zb", "dt", "yzt"}；返回 {date, query_date, kind, label,
    # count, source_total_count, rows, empty_reason, source, observed_at}
    # （实施修订：计划原为 list[dict]，落地带元数据 dict 以区分
    #   data=null 非交易日与合法空池）
def get_limit_up_reasons(curr_date: str = "") -> dict[str, Any]
    # 返回 {date, query_date, count, rows, empty_reason, source, observed_at}
```

- 来源：
  - 四池 `https://push2ex.eastmoney.com/getTopic{ZT|ZB|DT}Pool` +
    `getYesterdayZTPool`，参数 `ut/dpt=wz.ztzt/Pageindex/pagesize=10000/sort/date`；
    sort：ZT/ZB `fbt:asc`、DT 沿用本仓 `zdp:asc` 实测结论、YZT `zs:desc`；
  - 同花顺 `https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool`
    （`field` 串照抄，`filter=HS,GEM2STAR`）。
- 关键坑：价格 `p/ztp` ÷1000；`date` 必须传交易日（非交易日 `data=null`）；
  `yfbt/ylbc` 为昨日封板时间/昨日连板；同花顺
  `first_limit_up_time` 是 Unix 秒；`is_again_limit` 0/1；金额单位均为元。
- 与既有 `get_market_breadth` 的关系：**不改其冻结契约**（聚合统计、top5），
  新函数输出个股级明细与昨日池；两者共享 push2ex 常量与 `_em_get` 限流。
- 测试：四池 fixture（含 `zt_stat`/`break_times`/`seal_fund` 映射）、
  非交易日空语义、时间格式化（`92500→09:25:00`）、THS unix 秒转换。

### P1-A3 `chips.py`（1.5–2d）

```python
def chip_distribution(df: pd.DataFrame, grid_size: int = 300, decay: float = 1.0) -> dict[str, Any]  # 纯函数
def get_chip_distribution(ticker: str, start_date: str, end_date: str,
                          decay: float = 1.0) -> dict[str, Any]  # 装配 baostock 输入
```

- 纯算法 1:1 移植上游，并测试其全部不变量：
  - 必须含 `date/high/low/close/turn` 列，内部按时间**升序**重排（防倒序静默错算）；
  - 首日分布 = 期初全部流通筹码（不从零播种）；
  - 三角分布权重 + 网格落空兜底（映射到最近网格点）；
  - 硬约束：`profit_ratio ∈ [0,1]`、`avg_cost` 落在网格内、`cost_90 ⊇ cost_70`、
    `concentration_90 > concentration_70`；
  - 启发式不得当断言：`price<avg_cost ⇔ profit_ratio<50%`（右偏分布会相反）、
    `peak_price` 可在 `cost_90` 外（窄尖峰）。
- `get_chip_distribution` 输入装配（已确认决策：baostock optional extra）：
  - `pip install "chstockdata[baostock]"`（`baostock>=0.8.9`）；
  - `bs_session()` 上下文管理器保证异常路径 logout；模块级锁（baostock 全局登录态）；
  - `_bs_code` **登录前**拒绝北交所 4/8/92/920 号段并抛 `ValueError`；
  - `adjustflag="2"`（前复权，筹码成本必须复权口径）、`tradestatus=="1"` 过滤停牌日；
  - 未安装 extra → `VendorNotConfiguredError` + 安装提示，绝不静默降级。
- 输出须携带 `input_quality` / `methodology`（本地推演非实测持仓、前复权输入、
  窗口累计换手率），并在 docstring 声明绝对数值不保证与券商软件一致，只看形态与相对变化。

### P2-B1 全市场龙虎榜（0.5d）

```python
# a_stock.py
def get_daily_dragon_tiger(trade_date: str = "", min_net_buy: float | None = None) -> dict[str, Any]
```

- 复用 `_eastmoney_datacenter("RPT_DAILYBILLBOARD_DETAILSNEW", page_size=500)`，
  按 `BILLBOARD_NET_AMT` 降序；返回 `{date, total_records, stocks:[...]}`；
  `date` 以返回行 `TRADE_DATE` 为准；非交易日/未更新返回空并明示。
- 测试：datacenter fixture、`min_net_buy` 过滤、空语义。

### P2-B2 `board_flow.py`（0.5d）

```python
def get_board_fund_flow(board_type: str = "industry", period: str = "today",
                        top_n: int = 20) -> dict[str, Any]
```

- 来源 `https://data.eastmoney.com/dataapi/bkzj/getbkzj`：
  `board_type` → `{industry: m:90+t:2, concept: m:90+t:3, region: m:90+t:1}`；
  `period` → `{today: f62, 5d: f164, 10d: f174}`；字段仅 `f12/f14` + key。
- **明示差异**：无四档/净占比/领涨股（上游 push2 版才有的字段），
  返回 metadata 固定写入 `limitations`；**禁止回退 push2**。
- 与既有 `_eastmoney_board_flow_rows`（首页概念示例）可统一到同一 helper，
  但不得改变其现有行为。

### P2-B3 `investor_qa.py`（0.5d）

```python
def get_investor_qa(ticker: str, page_size: int = 30, page_num: int = 1) -> list[dict[str, Any]]
```

- 两步：`POST .../newircs/index/queryKeyboardInfo`（body `keyWord=code`）
  → `data[0].secid` 作 `orgId`；`POST .../newircs/company/question`
  （**参数必须放 query string，body 空**，否则 400）。
- 字段：`mainContent`（提问）/`attachedContent`（回复，未回复为 None）/
  `attachedAuthor`/`pubDate`（毫秒时间戳）。
- 测试：两步 fixture、无 `secid` 失败闭合、未回复条目原样保留。

### P2-B4 `hot_rank.py`（0.5d）

```python
def get_hot_rank(period: str = "hour") -> list[dict[str, Any]]          # 同花顺热榜
def get_em_hot_rank(top: int = 50) -> list[dict[str, Any]]              # 东财人气榜（腾讯补名称/价格）
def get_hot_concepts(ticker: str) -> list[dict[str, Any]]               # 东财个股概念命中
```

- 同花顺 `https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock`
  （`stock_type=a&type=hour|day&list_type=normal`）。
- 东财 `emappdata.eastmoney.com/stockrank/getAllCurrentList` +
  `getHotStockRankList`（H5 固定 body `appId01` / `globalId`）；
  名称/价格 hydration **改用本仓腾讯批量 `_get_realtime_quotes`**，
  不使用 push2 `ulist.np`；概念命中的 `srcSecurityCode` 用大写 `SH/SZ/BJ` 前缀。
- 测试：两个 fixture、代码前缀归一化、批量 hydration 失败时保留榜单裸数据。

---

## 4. 集成与发布（1d）

| 项 | 内容 |
|---|---|
| `__init__.py` | 导出 9 个新公开函数 + `__all__` 分组注释 |
| `mcp_server.py` | `_TOOL_FUNCTIONS` 追加新函数名 |
| `pyproject.toml` | `version = "0.2.0"`；extras 增 `baostock = ["baostock>=0.8.9"]` |
| `README.md` | 公开函数清单同步新增（约 12–14 个，含可选复合函数）；数据源表增新浪期权/同花顺热榜/巨潮互动易/东财 bkzj；「与上游差异」段更新（非超集表述改为列出移植后的差异与仍缺项） |
| `CHANGELOG.md` | `## [0.2.0] - 2026-09-14`，按 Added / Notes 组织，注明上游移植与范围 |
| `examples/` | 新增 `etf_options.py`、`chip_distribution.py` 示例（离线可说明前置条件） |
| CI | 默认套件（新测试离线）；`live-data-gate` 增新浪期权 smoke；THS/巨潮/东财不入 runner gate（防 IP 策略），走手动验收 |

**框架侧不在本方案内**：私仓 pin `chstockdata>=0.1.0,<0.2` 无需立即变更
（新函数纯增量）；待产品决定消费后另立 CR 处理 pin 升级与
capability registry / evidence / tool_plan 接线。

---

## 5. 测试与验收门

| 阶段 | 内容 | 验收门 | 估时 |
|---|---|---|---|
| P0 | ticker 路由修复 + live smoke 重建 + 扫描守卫扩展 | 新增回归全绿；默认套件 323+ 全绿 | 0.5d |
| P1 | A1/A2/A3 模块 + 测试 | 离线用例全绿；交易时段实拉各 1 次（期权链/四池/CYQ）并留输出记录 | 4.5–5d |
| P2 | B1–B4 + 测试 | 同上；bkzj 三周期 × 三板块实测 1 次 | 2d |
| P3 | 集成、文档、发布 | README/CHANGELOG/pyproject 一致；无 extra 环境下 `import chstockdata` 正常（baostock 惰性）；tag `v0.2.0` 触发 publish | 1d |

合计约 **8–8.5 个工作日**。

验证命令：

```bash
python -m pytest tests/ -q --no-header          # 默认套件（排除 network）
python -m pytest tests/ -m network -v           # 交易时段 live smoke（手动/gate）
python -m ruff check src tests                   # dev 依赖内
```

---

## 6. 风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 新浪期权/同花顺/巨潮接口结构漂移，mock 测试无法覆盖 | 字段数守卫 fail loud；live gate + 手动实拉；解析器集中小函数便于热修 |
| R2 | baostock 依赖问题（不支持北交所、全局登录态、License/维护状态、pandas 兼容） | optional extra + 惰性导入 + 模块锁 + 上下文 logout；北交所登录前拒绝；实施前复核 License 与 pandas 兼容 |
| R3 | 东财封 IP | 新请求全部走 `_em_get`；池只走 push2ex；bkzj 保持串行；live gate 排除东财 |
| R4 | CYQ 数值被误读为实测持仓 | 输出携带 methodology/`input_quality`；docstring 与 README 双处声明"推演、看形态不看绝对值" |
| R5 | B2 字段缩水被误用 | 返回 metadata 固定 `limitations`，文档明示无四档/净占比/领涨股 |
| R6 | 新函数改变既有行为 | 全部纯增量；不改 `get_market_breadth`/`get_realtime_snapshot` 等冻结契约；框架 pin 不变 |
| R7 | 上游后续版本新增修正未跟进 | 本文档记录基线 commit `f90d678`；后续按私仓既有"上游修复移植"节奏复查 |

---

## 7. 后续候选（本轮不做）

- B5 社融（人民银行三级跳，2021+，需 `xlrd` extra）与官方 PMI（与现有东财 PMI 重复，默认不移植）。
- B6 五档盘口（腾讯 5 档即可覆盖，低优先）。
- B7 官方备用源（SSE/SZSE 龙虎榜、深交所公告）作为内部 fallback。
- 上游 `norm_ticker(stock_only=True)` 的指数拒绝语义完整对齐（当前只做矛盾拦截）。
- 框架侧消费接线 CR（pin 升级、capability/evidence/tool plan）。

---

## 8. 实施记录（2026-09-14）

- 交付：chstockdata 0.2.0，14 个新公开函数（详见 CHANGELOG `[0.2.0]`）。
- 测试：默认套件 **384 passed**（迁移前 323，新增 61 例）；`ruff` 扫描新模块仅剩
  3 条与仓内既有风格一致的提示（DTZ007×2 为 date-only 解析、BLE001×1 为有意的
  补齐失败兜底）。
- Live smoke（交易时段实跑）：**5/5 通过**，含 510050 沪市 ETF 路由（P0 修复
  的实网验证）与新浪 ETF 期权链（T 型报价 + 希腊字母字段级断言）。
- 端点实拉（2026-09-14 盘后）：

| 端点 | 结果 |
|---|---|
| 涨停池 zt | 55 只（源端 tc=55 一致），首行封板 09:25:00、封板资金 4.54 亿、`1天1板` |
| 昨日涨停池 yzt（09-11） | 35 只，920268 中航泰达 `y_first_seal=10:07:27` |
| 同花顺涨停揭秘 | 55 条，含 reason / 板型 / 封板成功率 / 几天几板 / 首次时间 |
| 全市场龙虎榜（min_net_buy=1000 万） | 23 条，首行净买 8.89 亿、涨幅 20% |
| 板块资金流（行业今日 top5） | total=496，医药商业 28.98 亿居首 |
| 互动易（002594） | 5 条问答、org_id=gshk0001211（未回复条目原样保留） |
| 同花顺热榜 | 100 条，榜首 000636 风华高科含概念标签 |
| 东财人气榜 top10 | 腾讯补齐成功（hydration_error=None），榜首 000636 价格 58.9 |
| 个股概念命中（600519） | 7 条（白酒 8484 热度居首） |

- 计划偏差（已同步 CHANGELOG/README）：
  1. 模块 `chip_distribution.py` 更名为 `chips.py`——公开函数 `chip_distribution`
     与同名模块互相遮蔽（`from chstockdata import chip_distribution` 会绑定函数），
     更名后模块可从 `chstockdata.chips` 正常导入；
  2. `get_limit_up_pool` / `get_limit_up_reasons` 返回带元数据的 dict 而非
     `list[dict]`（区分 `data=null` 非交易日与合法空池，`empty_reason` 显式披露）；
  3. 新增 `a_stock._em_post`：与 `_em_get` 共用同一把串行限流锁，供 emappdata
     POST 端点使用。
- 未验证项：**CYQ 的 baostock 实拉**。本机未安装该 optional extra，按环境规范未
  全局安装；需在 venv 中 `pip install "chstockdata[baostock]"` 后运行
  `examples/chip_distribution.py 600519` 验证（离线算法与装配已有 10 例覆盖）。
- 未提交：全部改动留在工作区（按规范未自动提交）。
