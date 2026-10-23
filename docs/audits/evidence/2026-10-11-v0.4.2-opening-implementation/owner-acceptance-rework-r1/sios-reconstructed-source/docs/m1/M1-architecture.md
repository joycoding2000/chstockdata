# M1 第一策略试飞架构

## 1. 状态、权威与设计前提

本文只设计 M1，不修改已经批准的 M0 语义，也不设计 M2/M3 的完整实现。

权威顺序如下：

1. `docs/personal-systematic-investing-os-v0.9-flight-test-driven-product-architecture.md`：M1+ 产品与执行总纲；
2. `docs/architecture/*.md` 与 `docs/plans/M0-implementation-plan.md`：冻结的 M0 金融、数据与执行语义；
3. 本文与 `docs/m1/` 其余文档：M1 的局部细化。

仓库实际路径为 `docs/architecture/architecture.md` 等，而不是 `docs/architecture.md`。这是路径差异，不是设计冲突。

### 1.1 M0 就绪状态结论

M0 已达到开始 M1 设计的条件，且本轮不修改 M0 范围：

- M0 任务 1–12 均有实现提交，当前 HEAD 为 `322ce48`；
- 2026-09-16 复跑离线主套件：`553 passed`；
- 复跑资格验证/一致性对比：`25 passed, 5 skipped`，5 个跳过项均为显式选择启用的仅在线实盘检查；
- Ruff：通过；
- 任务 12 的三个源文件严格模式 mypy：通过；
- 全仓严格模式 mypy 仍有验收报告已披露的 `90 errors in 11 files`；这是已知的类型债务，不是 M1 开工前扩充 M0 的理由；
- M0 的录制式 ETF 资格验证、9 个一致性用例、21 个黄金场景与可复现性摘要均存在，且被当前测试覆盖。

仅在线实盘的 ETF 资格验证尚未在本机执行，这不阻止 M1 设计或离线开发；但在使用真实历史数据生成 M1 的 ETF 结论之前，相关的数据提供方/版本/范围必须重新通过受控资格验证。

## 2. M1 唯一目标与退出条件

M1 的唯一目标是把 ETF 与股票候选都跑通：

```text
Idea
  -> Cheap Screening
  -> Strategy Implementation
  -> Basic Backtest
  -> fixed OOS
  -> Survivor | Rejected
```

M1 完成必须同时满足：

1. ETF 与股票都各有一批预注册候选完成初步筛选与真实数据基础回测；
2. 只有对通过基础回测关卡的候选，才执行物理隔离的固定样本外；若某资产类别无人通过，`NO_OOS_ELIGIBLE_CANDIDATE` 是合法的 M1 结论，不会为了“必须有赢家”而继续搜索；
3. 每个结果都有不可混淆的策略版本/摘要、参数、标的池、数据快照、数据切分、基准、成本与 M0 内核身份标识；
4. 写代码前否决、基础回测否决、样本外否决、受污染与失败运行全部保留；
5. 相同清单重跑得到相同的规范化摘要；
6. 研究者或外部强智能体已能通过本项目 CLI/pytest 重复该循环，而不需要项目内的智能体运行时；
7. 至少完成一次“真实外部来源 -> 假设 -> 初步筛选”的 AI 助手来源试飞；筛选否决也属于成功的流程证据。

M1 的 `SURVIVOR` 只表示“值得进入 M2 的更昂贵验证”，不表示可上线、不表示可进入模拟盘、不表示获利保证。

## 3. 第一性原理裁剪

对每个候选子系统使用这个问题：

> 没有它，能否仍然让第一个真实策略更快进入可信的样本外？

保留的最小能力只有：

- 策略合约：否则真实策略无法进入 M0 内核；
- 冻结的 ETF 视图/年度时点信息股票时间表：否则结果可能包含生存偏差、过期标的池或未来信息；
- 不可变运行目录 + 只增不改的登记目录：否则不能保留失败、统计尝试次数或判断样本外污染；
- 精确的策略/运行摘要：否则结果不可复现；
- 初步筛选/基础回测/样本外验证器：否则漏斗可被智能体或人工绕过；
- 研究 CLI：否则现有智能体没有稳定的工具接口；
- 基准、成本、年度/子区间报告：否则无法判断策略是否只是市场暴露或只在单一阶段有效。

不建设数据库服务、工作流引擎、模型托管、Notebook 平台、Web UI、通用策略 SDK、自动调参平台或智能体编排。

## 4. 逻辑架构

```text
External researcher / ChatGPT / Codex / GLM
                    |
                    v
              Research CLI
                    |
          +---------+----------+
          |                    |
          v                    v
  Experiment verifier     Immutable artifact writer
          |                    |
          v                    v
  StrategyContract       run directories + catalog
          |
  StrategyTargetSource adapter
          |
          v
  M0 DecisionContext -> DailyBarEngine -> ledger/NAV/metrics
          ^                    |
          |                    v
 physically split PIT data Basic/OOS report
 universe/split/cost      + benchmark/year slices
```

研究模块可以依赖 M0 公共内核；M0 核心、未来的生产环境不得反向导入 `systematic_investing.research`。

建议新增的最小包边界：

```text
src/systematic_investing/research/
  contracts.py       # CandidateIntent、StrategyContract、StrategyEvaluation
  runner.py          # Strategy -> M0 TargetSource adapter 与单次运行
  universe.py        # ETF view 与 annual PIT Stock schedules
  artifacts.py       # immutable run directories、canonical JSON 与 digests
  catalog.py         # thin append-only catalog
  benchmarks.py      # candidate-local benchmark specs
  intake.py          # validates materialized canonical snapshots
  oos.py             # freeze、physical exposure 与 contamination verifier
  materializer.py    # owner-controlled physical Basic/OOS materialization
  reporting.py       # Basic/OOS/yearly/subperiod 输出
  cli.py             # 无网络、机器可读命令
  strategies/
    etf_absolute_trend.py
    etf_relative_momentum.py
    stock_relative_strength.py
    stock_breakout.py
```

这些是逻辑职责；实施时只有被当前任务用到的文件才创建。

## 5. 最薄策略合约

M1 的策略接口只负责把 `DecisionContext` 转成目标贡献，不拥有执行、费用、组合会计、数据下载或样本外状态：

```python
class StrategyContract(Protocol):
    @property
    def identity(self) -> StrategyIdentity: ...

    def evaluate(
        self,
        context: DecisionContext,
        universe: UniverseView,
    ) -> StrategyEvaluation: ...
```

`StrategyEvaluation` 是薄的带类型结果：

```python
@dataclass(frozen=True)
class StrategyEvaluation:
    status: StrategyEvaluationStatus  # TARGETS | NO_DECISION
    contributions: tuple[TargetContribution, ...]
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
```

`NO_DECISION` 必须有原因，例如 `INSUFFICIENT_HISTORY` 或 `NOT_DECISION_SESSION`；它与“有效策略决定 100% 现金”不同。无效输入、未来数据访问或违反合约是运行失败，不得伪装成 `NO_DECISION`。

`StrategyIdentity` 至少包含：

- `strategy_id`：稳定的语义名称；
- `strategy_version`：任何规则、参数、标的池语义变化都必须升级；
- `implementation_digest`：参与实现的 Python 文件按相对路径与字节的规范化哈希；
- `parameters` 与 `parameters_digest`；
- `sleeve`：ETF 初始为 `CORE`，股票初始为 `SATELLITE`；
- `required_history_sessions`；
- `decision_frequency`。

策略不得：

- 接收完整的未来数据表；
- 访问数据提供方、文件系统、网络或系统时钟；
- 自己撮合、扣费、维护持仓或计算成交；
- 改写实验状态；
- 返回“买入/卖出”文本作为投资决策。

`StrategyTargetSource` 是唯一的适配层，把当期 `UniverseView` 注入策略并实现现有 M0 的 `TargetSource`。它把 `TARGETS` 映射为目标贡献，把带类型的 `NO_DECISION` 映射为 M0 的 `None`，同时把完整评估写入研究运行产物；原因语义不会丢失。M0 的 `DailyBarEngine`、`DecisionContext`、T 日收盘/T+1 开盘、费用、最小交易单位、交收、可交易性与会计记账不重写。

## 6. 候选生命周期、标的池与数据范围

### 6.1 候选意图与研究运行清单

生命周期明确拆成两个对象。

`CandidateIntent` 在写代码前冻结研究问题，至少包含：

- 假设/谱系编号；
- 资产类别与子组合；
- 经济逻辑依据；
- 策略编号与规则伪代码；
- 参数变体、明确的 `parameter_selection_rule` 与经济理由；
- 标的池构建/重构政策；
- 基础回测区间、样本外区间与预热期区间；
- 基准；
- 执行/成本/指标口径约定；
- 基础回测晋级规则与样本外幸存规则；
- 已知局限；
- 创建时间、来源与父实验。

它不包含尚不存在的实现摘要、代码提交或实际数据快照摘要。

`ResearchRunManifest` 在每次实际运行前绑定：候选意图摘要、策略实现/版本/参数摘要、代码提交、依赖/内核身份标识、实际基础回测或样本外数据快照摘要、实际标的池时间表摘要、基准/成本/指标身份标识与输出范围。修改任一字段都产生新的运行身份标识，不覆盖历史。

多个参数变体同时通过基础回测时，按照 `CandidateIntent.parameter_selection_rule` 选择唯一的样本外候选。M1 默认使用预先声明的变体优先级列表，取第一个通过者；不得按基础回测收益最高者事后挑选。

### 6.2 ETF 标的池

M1 第一批 ETF 标的池只使用 M0 已批准子类型的代表范围：

- `XSHG:510300`、`XSHE:159915`：宽基股票；
- `XSHG:518880`：黄金；
- `XSHG:511010`：债券。

实际候选可以使用其子集，但不得加入跨境/QDII、货币市场或未通过资格验证的 ETF。现金不是 `XSHG:511010` 等防御性资产；现金在 M1 中明确定义为零收益账户现金。黄金/债券 ETF 是可交易头寸，经过同样的费用、最小交易单位与执行语义。

### 6.3 股票标的池

M1 不建设完整的时点信息成分股/基本面数据平台，但一次形成后冻结七年会产生不可接受的过期标的池。第一批股票使用简单的年度时点信息重构：

1. 每年最后一个开市交易日收盘后，仅用该截止时点之前可知的信息形成下一年度股票组；
2. 标准的沪深 A 股，上市至少 250 个开市交易日；
3. 非 ST、非退市整理、身份/规则已被证券主数据覆盖；
4. 构建交易日不处于停牌/未知状态；
5. 过去 60 个交易日的成交额中位数完整且可知；
6. 按成交额中位数降序、以标的编号作为并列裁决，取前 50；合格标的少于 20 个则当年度失败即拒绝；
7. 每个年度股票组在下一年度内固定，不用未来年度或今天的成分回填历史。

这足以研究趋势、突破、动量、相对强度、流动性，同时避免提前建设全量的时点信息基本面/因子平台。动态指数成分、行业中性、多因子与财务数据留到证据真正需要时。

## 7. 第一批策略切片

ETF 与股票同步研究，但先用少量可解释规则：

| 资产 | 候选 | 初始规则 | 目的 |
|---|---|---|---|
| ETF | 绝对趋势 | 收盘价与 200 个交易日简单移动平均线；月末决策；风险资产或现金 | 最快验证策略合约与内核 |
| ETF | 相对动量 | 126/252 个交易日收益的小网格；月末选择前 1 名；可加正绝对趋势关卡 | 检验轮动，不建设优化器 |
| 股票 | 相对强度 + 流动性 | 年度时点信息股票组；126 个交易日收益；前 N 名等权重；月度 | 低数据复杂度的横截面候选 |
| 股票 | 突破 + 流动性 | 过去 60 个交易日最高价；年度时点信息股票组；等权重上限 | 第二种独立、可证伪的候选 |

具体参数变体与选择顺序必须在实现前写入候选意图。M1 只允许小型、经济含义明确的离散网格；不得用目标收益/最大回撤反向搜索参数。

## 8. 实验保留与谱系

M1 使用不可变运行目录加一个薄的只增不改登记目录，不引入事件溯源框架或数据库：

```text
var/research/experiments/<lineage_id>/
  intent.json
  runs/<run_id>/{manifest,result,report}.json
  oos/<freeze_id>/{freeze,reveal,result}.json
var/research/catalog/
  000001.json
  000002.json
```

每个产物有规范化摘要，目录和登记条目使用新建加原子重命名的方式，已有路径不覆盖。登记条目只索引谱系/运行/类型/状态/摘要；状态由不可变产物重建。无需 `previous_event_digest` 或通用回放框架。测试使用临时目录。真实运行目录默认不进入 git；M1 验收只提交去敏摘要与摘要。

失败运行也创建不可变结果/登记条目：

- `REJECTED_BEFORE_IMPLEMENTATION`；
- `RUN_FAILED_DATA`；
- `RUN_FAILED_KERNEL`；
- `REJECTED_BASIC`；
- `OOS_REVEALED`；
- `REJECTED_OOS`；
- `SURVIVOR`；
- `OOS_CONTAMINATED`。

删除失败实验、重用登记序号、覆盖报告或把数据提供方故障记录成空结果成功，都是测试失败。

## 9. 基础回测与基准

基础回测只在候选意图的基础回测区间上运行。物理基础回测数据快照的最大交易日必须等于基础回测结束日；预热期数据行可来自更早区间，但不进入绩效统计。报告至少包含：

- 复合年增长率、最大回撤、换手率、交易笔数、成本拖累；
- 基准总收益/超额收益；
- 年度分解；
- 数据/关卡失败与约束/拒单次数；
- 策略/运行/数据快照/标的池/规格/输出摘要。

OQ-22 在 M1 采用候选专属基准，而不建设全局基准服务：

- 单一 ETF 趋势：同一 ETF 的买入持有；
- ETF 轮动：同一冻结 ETF 标的池的成立以来等权重买入持有；
- 股票：同一年度时点信息标的池时间表的等权重基准；
- 所有报告另列 `CASH_0` 对照项。

基准使用同一规范化数据快照、M0 执行/成本/会计记账语义；不得看完结果后更换基准。M0 的 `RunManifest` 不被改写为“曾经支持真实基准”；M1 使用组合式 `ResearchRunManifest` 引用 M0 内核身份标识和单独的 `BenchmarkSpec`。

## 10. 固定样本外、物理数据暴露与污染控制

样本外验证器必须控制数据暴露，而不只是裁决结果：

1. 基础回测数据快照在文件系统上只到基础回测结束日；研究智能体在冻结前不能访问数据提供方原始目录树、缓存或包含样本外数据行的文件；
2. 基础回测关卡通过后写入 `OOS_FREEZE`，冻结候选意图、策略/版本/参数、样本外请求范围、标的池政策、基准/成本/指标/内核摘要；此时实际的样本外数据快照摘要尚不存在；
3. 验证器确认该谱系从未揭示过重叠区间；
4. 只有所有者控制/隔离的数据物化器可以在冻结后获取样本外数据行，并写入冻结专属、只读的样本外目录；
5. 物化生成后产生 `OOSRunManifest`，绑定实际样本外数据快照与标的池时间表摘要，并验证它们严格符合冻结请求；
6. 样本外运行器组合只读的基础回测预热期数据快照与新的已物化样本外数据快照，绩效只从样本外起始日开始计算；
7. 揭示意图在运行器打开样本外产物之前持久化；
8. 按预注册关卡写入 `SURVIVOR` 或 `REJECTED_OOS`。

如果研究者/智能体在冻结前已经可以读取同一区间的原始数据/数据提供方数据，该区间只能标记 `HISTORICAL_VALIDATION`，不能宣称受控样本外。哈希/登记关卡无法修复已经发生的数据暴露。

一旦样本外被揭示：

- 同一候选版本不得再次以新参数运行；
- 修改实现、参数、标的池、基准、成本或数据切分必须新建版本；
- 新版本若复用已揭示区间，只能标记 `RESEARCH_REUSE`/`OOS_CONTAMINATED`，不得宣称真实样本外；
- 新的真实样本外必须使用不重叠、尚未揭示的后续区间。

M1 不做滚动前推、稳健性、最终留出验证或模拟盘。这些属于 M2 的幸存者验证。

## 11. 市场状态后置边界

M1 不建设正式的 `BULL/SIDEWAYS/BEAR` 标签子系统；年度/子区间分解已足够做第一轮证伪。若已有外部的、预注册且符合时点信息的标签产物，可以附加仅用于分析的分解，但它不是 M1 的退出条件。

市场状态不进入策略合约，不改变目标持仓，不选择策略。正式的标签语义、策略 × 市场状态报告与任何路由切换都在幸存者出现后进入 M2 设计。

## 12. AI 助手工作流

M1 的助手是“外部强智能体 + 本项目工具”，不是项目内智能体：

```text
Agent reads authority docs and a real external source
  -> writes source record + CandidateIntent
  -> research screen
  -> implements one StrategyContract
  -> runs focused pytest
  -> research basic-backtest
  -> reads machine-readable report
  -> either records rejection or requests oos-freeze
  -> research oos-run
```

CLI 的所有成功输出都是带版本号的 JSON，失败使用非零退出码与带类型的原因。验证器位于 CLI 内部；智能体不能用 `--force` 跳过初步筛选、基础回测关卡、冻结或污染检查。

现阶段不需要 `AIModelPort` 生产代码，因为项目不主动调用模型；CLI/JSON 就是外部智能体边界。若未来项目自身发起 LLM 请求，再引入薄的 `AIModelPort`，不得提前引入供应商 SDK、记忆模块或编排。

## 13. 错误与失败即拒绝规则

- 数据快照/关卡/证券主数据/资格验证缺失：不运行并记录失败；
- 基础回测数据快照包含基础回测结束日之后的数据行，或样本外在冻结前可读：拒绝受控样本外声明；
- 策略请求未来/未知事实：测试与运行失败，不降级为空目标持仓；
- 回看窗口不足：返回带类型的 `INSUFFICIENT_HISTORY`，不把现金当作策略判断；
- 空标的池、股票组少于 20、未知可交易性：失败即拒绝；
- 报告持久化失败：运行不得标记为完成；
- 基础回测关卡失败：保留结果并停止，不进入样本外；
- 样本外重叠/揭示/物理暴露冲突：标记污染并拒绝真实样本外声明；
- LLM/人工解释与数值产物冲突：以产物为准，解释不得改写结果。

## 14. M1 明确不做

- 知识管理平台、论断图谱、向量数据库；
- 完整策略 SDK、插件市场、Notebook 托管；
- 市场状态路由器或自动策略切换；
- 智能体运行时、规划器、记忆模块、任务队列；
- 私人投资记忆库、AI 投资者；
- Web UI、生产调度器、ServerChan、券商接口；
- 主动策略包、组合资金竞争优化；
- 滚动前推、稳健性、最终留出验证、模拟盘；
- 回测过拟合概率、收缩夏普比率、错误发现率等复杂的多重检验统计；
- 全量时点信息基本面数据、因子库、机器学习/深度学习；
- M2/M3 生产实现。

## 15. 设计冲突

`NO_DESIGN_CONFLICT`

v0.9 把股票候选研究从旧路线图的 M6 提前到 M1，这是 M1+ 路线图的显式更新，不改变任何已批准的 M0 交易、数据、组合或运行语义。M1 通过 M0 现有的核心/卫星子组合、时点信息、T 日收盘/T+1 开盘、费用、最小交易单位、交收、目标组合与回放契约接入，不重开 M0。

## 16. 范围审计

### M1 必须做

- 薄策略合约与 M0 适配器；
- ETF/股票候选意图与时点信息标的池政策/时间表；
- 初步筛选、真实数据基础回测；对符合基础回测条件的候选执行物理隔离把关的固定样本外；
- 不可变运行目录、薄登记目录、谱系与失败保留；
- 策略/规格/运行摘要与确定性回放；
- 无未来信息/样本外污染验证器；
- 候选专属基准、年度/子区间报告；
- 研究 CLI 与现有强智能体工作流；
- AI 助手来源试飞；
- 每个资产类别得到规范化的样本外裁决或 `NO_OOS_ELIGIBLE_CANDIDATE`。

### 明确后置 M2

- 幸存者稳健性、参数邻域、成本压力测试；
- 滚动前推、最终留出验证、模拟盘前推；
- 正式的 `BULL/SIDEWAYS/BEAR` 标签与策略 × 市场状态分析；
- 幸存者组合/相关性与主动策略包候选；
- 运维层面的研究到生产晋级。

### 明确后置 M3

- 每日日终/盘前运行时、调度器；
- 持仓/现金对账、操作计划、手工成交录入；
- ServerChan 与最小真实用户界面；
- 生产备份/漏跑处理。

### 长期后置

- 完整知识平面、AI 投资者、私人记忆库；
- 完整 5 页 UI、通用策略 SDK；
- 市场状态路由器、复杂因子/机器学习平台、券商自动化；
- 复杂的多重检验研究平台。

### 过度设计检查

当前设计没有独立服务、数据库、Web、智能体框架或调度系统。最可能膨胀的点是实验保留、标的池与样本外隔离；它们被限制为不可变目录 + 薄登记目录、年度时点信息重构与一次所有者控制的物化生成。若实现扩展为事件溯源框架、通用数据权限平台或编排服务，应暂停并重新应用第一性原理问题。
