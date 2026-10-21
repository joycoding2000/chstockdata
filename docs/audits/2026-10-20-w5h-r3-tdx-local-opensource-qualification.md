# W5-H-R3：通达信本机恢复、开源实现与真实来源资格

日期：2026-10-20，Asia/Shanghai。任务：`W5_H_R3_TDX_LOCAL_AND_OPEN_SOURCE`。决策保持 `INVESTIGATE`；本轮调查完成，等待 Owner Review，不批准实施或阶段推进。

## 1. 可直接决策的结论

1. **VIPDOC 已找回，而且有多个真实库。** 中信客户端 `C:/zd_zxzq_gm/vipdoc` 有沪深日线 **9,038** 个文件，另有北交所 326 个；SDK 默认缓存 `C:/Users/Administrator/.chstockdata/cache/vipdoc` 有沪深 **11,806** 个，项目 `.rh3a2-vipdoc` 有沪深 **11,815** 个，另有 frozen checkout 中的同类副本。文件数包含指数、基金等，不能当作 A 股股票池分母。华鑫目录的日线为空。两个客户端 `cw` 为空仍属实，但**本机没有 VIPDOC/专业财务文件的推论不成立**。
2. **免费取得和解析财务数值已经有实物证据。** 发现 `easy_tdx` 旧下载中的真实 2026 一季报 ZIP/DAT；另以一次普通匿名 GET 从通达信域名取得 **2017-12-31 固定 ZIP**，长度、官方旧目录 MD5、ZIP CRC、DAT 报告期/证券索引均通过，已装 mootdx 与独立 struct 解析一致。无需新增生产依赖、登录或付费。这个成功只认证所测文件的本次访问，不承诺所有版本免费、持续访问或商业再分发权。
3. **该免费包不能直接供应 S07 历史 PIT，当前财务完整性也不能因“能解析”而通过。** 康美 600518/2017 行的收入、归母利润、归母权益匹配更正披露，OCF 却匹配原报；`FN314=180426` 仍是原公告日。它是**混合修订字段**，既非完整原版，也非一致的更正版。报告期数值、历史版本、估值三项资格必须拆开。

`W5_H_R3_VERDICT = FREE_RAW_ACCESS_PROVEN_BUT_S07_NOT_QUALIFIED`。不再需要一轮类似“找 VIPDOC/能否免费下载”的调查；缺口已经从访问未知推进到具体的字段一致性、旧版本及历史估值证据不足。

## 2. 权威恢复与工作树身份

已读取根 AGENTS、双消费者供给计划、W5-H、R2、Mishi R3.2/DR01–DR06 中的 S07/DR05 历史要求，并核对旧披露实物、旧目录和当前源码。历史底线仍为最近约一交易年度另含预热、当时版本、全池资格；本轮不冻结 PE/ROE 算法、不取消 S07、不修改行业或消费者范围。

| 仓库 | 本轮起始 HEAD / 分支 | 起始状态及保护 |
| --- | --- | --- |
| chstockdata | `69957a58bcfd258f011c9c80250b58704fe0d784` / main | tracked diff 空；大量既有未跟踪审计材料保留。全文件展开的 porcelain 为 13,639 行，不能与目录合并状态条数混用；起始时已含本轮首个调查脚本。 |
| mishi-radar | `76012c0db977d21832378c473638c271d8c1a554` / main | 起始 porcelain 空；未写入。 |
| systematic-investing-os | `f06e7d8e342133a02beb20a4b310580a633ba9cb` / codex/v010-owner-product-clarification | 起始 porcelain 6 行既有状态；不同于 R2 的旧 HEAD，采用实际状态，未写入。 |

[before.json](evidence/2026-10-20-w5h-r3/before.json)保存三仓库 HEAD、分支、全部状态、tracked 文件 SHA 及权威输入 SHA；[final_verification.json](evidence/2026-10-20-w5h-r3/final_verification.json)保存终检。`v0.4.3` 指向 `30cc7c50e3971fe79bfd903a412b2b76a0338caa`，当前 describe 为 `v0.4.3-1-g69957a5`。遵从 Owner：W0/v0.4.3 已完成，**未重跑发行 Gate**。

终检另观察到 SIOS 在本轮期间并行新增未跟踪研究文件，位于 `research/static-economic-falsification-2026-10-20/`；本任务没有对消费者执行写命令，既有状态和新增文件均原样保留。三仓库 HEAD/已跟踪内容核验与这项并行工作树变化分开报告，**不声称消费者工作树始终静止**；精确增量见 final_verification.json。

代码定位先使用 CodeGraph，随后用当前源码 AST 核对位置；索引展示的旧位置不作为行号权威。当前 `load_vipdoc_daily` 在 `src/chstockdata/vipdoc_history.py:171`，根目录选择在 :81，F10 快照在 `a_stock.py:3120` 附近；见 [runtime_symbols.json](evidence/2026-10-20-w5h-r3/runtime_symbols.json)。

## 3. 本机数据恢复

### 3.1 实际目录、数量与大小

下表大小为目录内文件字节总和；完整首尾文件 mtime、有限文件名/大小样本及固定日线 SHA 分别见 [local_inventory.json](evidence/2026-10-20-w5h-r3/local_inventory.json)、[default_cache_inventory.json](evidence/2026-10-20-w5h-r3/default_cache_inventory.json)、[supplement.json](evidence/2026-10-20-w5h-r3/supplement.json)。mtime 是文件系统时间，不是报告公告日或历史首次可得时间。

| 实际 VIPDOC 根 | sh/lday 文件 / 字节 | sz/lday 文件 / 字节 | bj/lday 文件 / 字节 | 固定股票内容日期 |
| --- | --- | --- | --- | --- |
| `C:/new_hxzq_hc/vipdoc` | 0 / 0 | 0 / 0 | 0 / 0 | 无日线样本 |
| `C:/zd_zxzq_gm/vipdoc` | 4,766 / 156,238,048 | 4,272 / 137,362,368 | 326 / 7,758,176 | 600518：2021-08-02—2026-06-29；600519 同起止，行数略异 |
| `C:/Users/Administrator/.chstockdata/cache/vipdoc` | 5,948 / 485,588,672 | 5,858 / 450,149,376 | 610 / 14,959,040 | 600518：2001-03-19—2026-09-16；600519：2001-08-27—2026-09-16 |
| `D:/Dev/Projects/chstockdata/.rh3a2-vipdoc` | 5,951 / 486,210,592 | 5,864 / 450,723,584 | 611 / 15,003,360 | 600518：2001-03-19—2026-09-22；600519：2001-08-27—2026-09-22 |
| `D:/Dev/Projects/chstockdata-frozen-v042/.rh3a2-vipdoc` | 5,951 / 486,210,592 | 5,864 / 450,723,584 | 611 / 15,003,360 | 两只固定股票 SHA 与上一库相同；没有逐文件认证全库相同 |

中信日线文件 mtime 分布为 2026-06-26—06-29 UTC；默认缓存为 09-16 UTC；项目库为 09-23 UTC。后两库 manifest 分别自报 09-16/09-23 下载，源为官方 `hsjday.zip`；原 manifest SHA 已保存，**不以自报下载时间认证旧版 PIT**。截至本轮 10-20，样本均非最新完整交易日，不能标当前扫描新鲜。

两个客户端的 `sh/minline`、`sz/minline` 均存在但文件数 0；三个缓存库相应分钟目录缺失。两个客户端 `vipdoc/cw` 均存在且 0 文件；默认及项目缓存 `cw` 缺失。日线格式为 32 字节 `<IIIIIfII>`：日期、OHLC、float32 Amount、Volume、末尾保留字段；四个实际股票/根组合使用**现有公开 reader**核对 Close/Amount/Volume 与原始末条一致。原始价量额可复用，末尾保留字段未认证为 PE/股本，不自行解读。

### 3.2 专业财务与股本变迁实物

| 文件 | 实际状态 |
| --- | --- |
| `D:/Dev/Projects/easy_tdx/examples/09_file_download/downloads/gpcw20260331.zip` | **5,034,901 B**，mtime 2026-08-25 10:04:51 UTC；PK ZIP，CRC 通过；内部 DAT **12,948,419 B**。同目录 `gpcw20260331/gpcw20260331.dat` 已存在，逐字节等于 ZIP 成员。没有复制/解压到原目录。 |
| 上述 ZIP / DAT SHA-256 | ZIP `470e1ca0fa309def0f55ae6681c08f576752d0b0e359f31cd67194568209e30d`；DAT `0329efd487c2faabc611e483e25e663a8fdb3c2efd5d9fcdde9bfc121a1fd007`。 |
| `C:/new_hxzq_hc/T0002/hq_cache/gbbq` | **5,458,152 B**，mtime 2026-07-01 09:11:26 UTC；188,212 条，文件头条数与 `4+29×count` 一致。 |
| `C:/zd_zxzq_gm/T0002/hq_cache/gbbq` | **5,473,261 B**，mtime 2026-07-04 01:13:53 UTC；188,733 条，同样结构一致。 |

2026 ZIP 是早已存在的实际文件，原下载会话/付费状态 UNKNOWN；旁边 `easy_tdx` 示例说明使用计算服务器下载，但示例中的打印样例含占位散列，**不能当本文件下载日志**。本轮以实际 ZIP/DAT、CRC、内容 SHA 和解析值证明存在。

[corporate_action_sample.json](evidence/2026-10-20-w5h-r3/corporate_action_sample.json)保存两个 gbbq 的 SHA、纯解析器身份和两只股票记录。复用已存在的 `easy_tdx/offline/gbbq.py` 纯解析逻辑，跳过包初始化；仅将缺文件异常的相对导入替换为内建异常，未改算法/源文件。两个库均读到 600518 的 50 条（2001-05-25—2025-07-09）与 600519 的 45 条（2002-07-25—2026-06-26）。它们含股本变动/分红事件日期和分类，但**没有认证公告时间、全部类别语义、历次文件版本或每日全覆盖**。

### 3.3 发现边界与对旧“空”的纠正

从实际 SDK 根目录规则、环境变量、桌面/开始菜单快捷方式、已知客户端及项目数据目录恢复路径。没有相关 VIPDOC/TDX 路径环境变量；默认配置会选 `~/.chstockdata/cache/vipdoc`。快捷方式真实指向中信 `TdxW.exe`；根目录有可执行文件，版本资源仅为通用 `1,0,0,1`，不能认证支持 TQ 的构建版本。华鑫根目录没有找到 exe，仅保留数据目录；不把它称为已可运行增强终端。未观察到匹配 TDX/TQ 的运行进程。见 [client-state.json](evidence/2026-10-20-w5h-r3/client-state.json)、[client-shortcuts.json](evidence/2026-10-20-w5h-r3/client-shortcuts.json)。

另进行**一次**本地盘有界文件名发现：C/D/F，单种子最多 6 层、22,000 目录/90 秒上限；实际约 39.5 秒到目录上限，尚有 28,308 个排队目录，60 项访问错误已跳过。未读系统敏感内容、不跟随链接、不整盘哈希；大量命中是测试 fixture，已与真实库区分。默认缓存和已知 ZIP 下的 DAT 随后按配置/明确路径定向补查，没有第二轮整盘搜索。[discovery.json](evidence/2026-10-20-w5h-r3/discovery.json)保留边界；**不能据此声称其他位置绝无财务文件**。

六种状态分别是：日线真实存在＝中信/默认缓存/项目库；财务 cw 存在且有值＝受检客户端无；有目录无落地日线＝华鑫；财务实际另址＝easy_tdx 的 ZIP/DAT；“曾存在但迁移”＝无证据；其他未覆盖位置＝仍未定位。R2 的两个 cw 空这一观察没有被推翻，其观察范围不能外推成全机无数据。

## 4. 四个 GitHub 项目的实际审查

公开源码均按 commit 固定下载、只读保存于 [upstream](evidence/2026-10-20-w5h-r3/upstream/)，未安装或直接运行其更新脚本。版本及请求账本见 [upstream_summary.json](evidence/2026-10-20-w5h-r3/upstream_summary.json)、`github_requests_initial/more/final.json`；46 项定向 GitHub 请求另加 1 次初始匿名连通性元数据请求。Firecrawl scrape 返回 Invalid token，未修凭据，转用匿名公开源；网页工具四批定向读页，底层 HTTP/缓存次数不可观测。

### 4.1 tdx_quant：确有 FN 数值通路的源码/测试证据，但不是本机实测

固定 [85a00f1b160638e6a0f6d7ce6d7382915b78039e](https://github.com/zxtzlyt/tdx_quant/tree/85a00f1b160638e6a0f6d7ce6d7382915b78039e)，commit 时间 2026-09-29 17:00:43 UTC＝上海 **09-30 01:00:43**，与笔记“2026-09-30”无矛盾。读过六个指定路径及 LICENSE：

- [LOCAL_NOTES.md](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/docs/LOCAL_NOTES.md)保留了“数值通道空”的早期观察及文末更正，不能只摘旧段落。新结论要求 `table_list=field_list`，`[]` 的语义是不选择数值表。
- [tests/test_live.py](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/tests/test_live.py#L235)同时有空表日历控制与数值通道测试；数值测试直接 `TQ.call`，显式 fields/table_list、`report_type='tag_time'`、YYYYMMDD 起止，校验茅台 2024 FN96=86,228,148,224 及 20260630 报告期。不是仅有 README 声明，但**未提供本机相同构建的原始响应**。
- [tq_client.py](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/tdx_local/tq_client.py#L37)是 JSON-RPC 通用 `.call(method, **params)`，没有替用户自动补 financial 参数的专门 wrapper；空 params 也需对象。作者笔记引用 tqcenter **1.2.0** 的 table_list 序列化，但测试未固定客户端产品构建，不能扩大到所有券商版。
- [gpcw.py](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/tdx_local/gpcw.py)、[cw_fields.py](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/tdx_local/cw_fields.py)提供索引解析、占位/越界检查、累计与单季分离、float32 容差。注册表 verified 是作者锚定结果，不能替代本轮字段认证；FN74/96/107/271/238 均已实际读取。
- [test_offline.py](https://github.com/zxtzlyt/tdx_quant/blob/85a00f1b160638e6a0f6d7ce6d7382915b78039e/tests/test_offline.py)中真实文件用例依赖作者路径、可能 skip；live 组在服务不可达时整组 skip。本轮只审查测试，**没有把跳过当通过**。

`approx_announce_date` 按法定截止日估计，并非真实公告日，更不保存修订链；不得用于本任务 PIT 认证。作者记录同大小财务文件仍有 38 条不同值，说明“大小相同即最新”的同步判断不能认证内容或版本。`sync_cw`/`sync_lday`、refresh/open-in-client 都可能复制、覆盖或触发下载，本轮未调用。头部 `[3]` 在实物中为 720896，而首记录实际从索引后开始，**不照搬注释将它认作数据区起始偏移**；以每个索引 offset 为准。

许可证实际文件为 **MIT（代码）**；API 因附加 scope note 标 NOASSERTION，不能只信 API 标签。镜像官方文档明确不在该代码许可范围。免费文件/HTTP 能力是作者环境的证据；本机资格分别由下节的文件与连接结果决定。

### 4.2 stock-analysis：本地日线/财务/gbbq 链路真实，更新和回填不能照搬

固定 [814f1d4db3a7ecac0b21f61e6ea6214a9ea73742](https://github.com/wkingnet/stock-analysis/tree/814f1d4db3a7ecac0b21f61e6ea6214a9ea73742)。读过 `readTDX_cw.py`、`readTDX_lday.py`、`func_TDX.py`、`user_config.py`，并沿实际调用补读 `func.py` 和 `util_docs/专业财务文件字段含义对照表.txt`。

实际方案为 `.day→CSV`、gpcw 索引/float32→DataFrame、gbbq→事件/流通股本→复权、流通市值/换手率。`func_TDX.py` 不是财务解析器，关键函数在 [func.py](https://github.com/wkingnet/stock-analysis/blob/814f1d4db3a7ecac0b21f61e6ea6214a9ea73742/func.py)。字段表明确 FN74/96/107/238/271/281/314，与本轮索引映射互证；字段表本身没有证明各历史版本正确。

[readTDX_cw.py](https://github.com/wkingnet/stock-analysis/blob/814f1d4db3a7ecac0b21f61e6ea6214a9ea73742/readTDX_cw.py#L32)提供 `http://down.tdx.com.cn:8001/tdxfin/` 的目录/文件路径，成为本次单文件 GET 的具体方法线索。其顶层会下载、删旧 ZIP、extractall 覆盖真实 cw；**未 import/执行该脚本**。自算方法也不能直接通过历史资格：`func.py:590` 后按报告期 `cw_date` 向后填充股本，不等于公告时可知；另有 `bfill`，存在把后值带向更早日期的明确用法。市值示例使用复权 close，不能自动当当时未复权总市值；所读路径没有形成经验证的逐日 PE 合同，README“可自算”不能代替实现和分母证据。

许可证 **MPL-2.0**；复用覆盖文件须遵循对应源码许可义务。代码许可与通达信/交易所数据使用许可分别核定。

### 4.3 mootdx：已有依赖足以解析，当前 chstockdata 尚未暴露专业财务历史

上游固定 [e99ae34382d970c68654c6d17c45512e728f130d](https://github.com/mootdx/mootdx/tree/e99ae34382d970c68654c6d17c45512e728f130d)，许可证 **MIT**。本机已有 **mootdx 0.11.7 / tdxpy**，未装 pytdx；实际安装目录与版本见 local_capabilities。解释器另报安装分发 chstockdata 0.1.0，不能将其与当前仓库/正式 v0.4.3 混淆；日线验证显式加载当前仓库模块，财务验证使用已装 mootdx 的解析器。

- [Reader](https://github.com/mootdx/mootdx/blob/e99ae34382d970c68654c6d17c45512e728f130d/mootdx/reader.py)提供本地日线/分钟/板块读取，没有 `Reader.finance()` 历史财务出口；部分板块方法可写，未调用。
- [Affair.files/fetch/parse](https://github.com/mootdx/mootdx/blob/e99ae34382d970c68654c6d17c45512e728f130d/mootdx/affair.py)管理目录与下载。`fetch(filename=None)` 会批量下载；`parse` 遇文件缺失会自动 fetch。`BaseFinancial` 初始化可能读/生成配置及选服，不适合直接对真实目录做本轮探针。
- [financial/financial.py](https://github.com/mootdx/mootdx/blob/e99ae34382d970c68654c6d17c45512e728f130d/mootdx/financial/financial.py)的 DAT parse 可复用。本轮只调用已装类的无配置初始化纯 DAT 分支，输入内存 stream，未用其 ZIP 临时解压或自动下载分支，两个证券/两个报告期与 struct 一致。
- 当前 chstockdata 有 RAW 日线 reader 和 `finance()` F10 快照；源码中没有 gpcw/Affair/HistoryFinancialReader 接入。现有 F10 金额快照还具有 0.1 元协议尺度，**不能把它的除 10 规则套在 gpcw 的元值上**。财务公共三表的日期过滤也不能创造缺失旧版。

本次已有依赖足够完成读文件验证；生产窄出口即便将来需要，也须另经 Owner 授权，本轮不实现。

### 4.4 pytdx：归档格式参考，不是建议新增依赖

仓库实际 archived=true，默认 `archive` 分支 HEAD `14b1ad3534593952d1d698ffa706f4f13a4ed156` 只有 README；所需源码须固定旧 [master 2857fdad08534533610bd2aeca387f760c4baa42](https://github.com/rainx/pytdx/tree/2857fdad08534533610bd2aeca387f760c4baa42)。读取 `reader/history_financial_reader.py`、`crawler/history_financial_crawler.py`、`hq.py`、`parser/get_finance_info.py`。

`HistoryFinancialReader` 只是 crawler parse 的包装；20B 头、11B 索引、float32 记录，与实物相符。crawler 静态 URL 含第三方镜像，实际 content 实现另用 TDX 计算协议，不能把镜像域名当官方免费权利证明。`get_finance_info` 是某证券快照，与期间文件不同；没有可回放历史修订的承诺。ZIP 分支会写临时目录/解压，未运行。

本次 API license=null，旧 master 树根未见 LICENSE/COPYING，setup.py 也无 license 声明；**不擅自标 MIT，也不据此授权商业复制**。仅作格式/协议溯源；复用当前已装 mootdx/tdxpy 能力，无新增 pytdx。

## 5. 三条真实路线的执行账本

### A：已有文件——成功

20260331 ZIP/DAT 头为 `[1,20260331,5517,720896,2336,0]`：5,517 记录，584 个 float32 字段；全部索引边界合法。只输出 600518/600519 固定证券，不做全市场质量扫描。[local_financial_sample.json](evidence/2026-10-20-w5h-r3/local_financial_sample.json)保存数值；[supplement.json](evidence/2026-10-20-w5h-r3/supplement.json)与 R2 **已保存** THS 600518/2026Q1 的收入、归母利润、OCF、归母权益、股本逐项对账，**5/5 恰等于相同数值的 float32 舍入**。未重新请求 THS。

例如该期收入 1,079,786,624、归母利润 -16,563,882、OCF -54,755,348、归母权益 7,273,519,616 元；FN238=13,828,896,768 股。它们证明数值/单位具有实际用途；不证明每期、每股或所有指标正确。

### B：本机 TQ——未建立可用连接，停止

[local_capabilities.json](evidence/2026-10-20-w5h-r3/local_capabilities.json)记录 2026-10-20 14:48:08 上海时间，对 `127.0.0.1:17709` 一次 1 秒 TCP 检查：TimeoutError。**没有发 financial RPC**，未主动启动服务、打开客户端、改配置、登录或读取认证信息。结论是本轮可达性未成立，不断言所有券商版不支持或接口数值为空。

官方 [get_financial_data 文档](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html)区分 announce_time/tag_time，且签名默认 report_time、参数表 bool 类型等存在表述不一致；作者样例只能为支持 TQ 且已具本地专业数据的对应版本提供调用线索。没有现场服务版本，不能认证这些参数在本机生效。

### C：固定期间获取——HTTP 成功；旧默认计算线路失败

先审查已装 mootdx 财务线路实现，仅对 `GP_HOSTS[0]=120.76.152.87:7709` 一次连接，3 秒上限，关闭 setup/重试/心跳，没有成功完成协议请求。探针 disconnect 在未连接 socket 上又报 WinError 10057，遮蔽初始连接原因，故原因记 UNKNOWN，不能事后补写为确定超时。清理代码已修正，**没有重跑网络**；[gp_probe.json](evidence/2026-10-20-w5h-r3/gp_probe.json)明示为命令观察恢复账本，非成功原始响应。

随后按已审查的 HTTP 文件方法做**唯一一次**固定报告期 GET，区别于上述计算线路，无换股票/年份/镜像循环：

| 项目 | 真实结果 |
| --- | --- |
| 地址 | `http://down.tdx.com.cn:8001/tdxfin/gpcw20171231.zip`，来源于 stock-analysis 指定实现；官方 tdx.com.cn 子域 |
| 时间/方式 | 2026-10-20 **14:53:57** 上海时间；普通 GET，无账号/token/登录；15 秒、6 MB 上限；不重试、不追重定向、不执行脚本 |
| 响应 | HTTP 200，application/zip，**4,206,396 B**，开头 `50 4b 03 04` |
| 身份 | MD5 `5face3f599d2f19db9e37fbb065c7523`，与 R2 保存的官方 `gpcw.txt` 同名条目及长度一致；MD5 仅作目录一致性检查，另保留 SHA-256 |
| ZIP SHA-256 | `e393c139a78eef736e8fa25a9226ad73480c8393afdffdd1fbf5a33033065086` |
| 内容 | 唯一成员 `gpcw20171231.dat`，**10,784,485 B**，CRC 通过；DAT SHA `b95f860bcb129d17eac7d02e240aa732000958071b22c8122485c45d426c0513` |
| DAT 结构 | 头 `[1,20171231,4595,720896,2336,0]`；4,595 条/584 字段；索引范围合法；固定两证券与已装 mootdx 解析一致 |

原始字节只保存为证据目录内的 [http_gpcw20171231.response](evidence/2026-10-20-w5h-r3/http_gpcw20171231.response)，未解压覆盖客户端、未下载全套包。见 [http_probe.json](evidence/2026-10-20-w5h-r3/http_probe.json)、[fixed_2017_qualification.json](evidence/2026-10-20-w5h-r3/fixed_2017_qualification.json)。R2 的另一个 HTTPS 入口返回 HTML 的事实保留；现在有不同具体官方地址的成功实物，不能把旧失败升级成收费/全路线失败结论。

## 6. S07 字段和历史版本：康美固定反例

### 6.1 数值、单位、口径和精度

下表 gpcw 为存储的真实 float32 解码值，金额按人民币元。原报来自已保存 2018-04-26 原文；修订收入由已保存更正公告双列支持，其他修订汇总沿用 W5-H 保存的 2019-04-30 年报摘要网页观察及 R2 THS 交叉证据。**网页观察不是新增完整原件**；源 SHA、原文数值命中及观察血缘见 [disclosure_anchor_checks.json](evidence/2026-10-20-w5h-r3/disclosure_anchor_checks.json)、supplement.json。

| 字段 | 原报值 | 2019 更正值 | 本次 2017 gpcw | 判定（按 float32 精确舍入） |
| --- | ---: | ---: | ---: | --- |
| FN74 营业收入 | 26,476,970,977.57 | 17,578,618,640.06 | **17,578,618,880** | 更正值；与原值相差约 88.98 亿 |
| FN96 归母利润 | 4,100,926,148.57 | 2,149,836,281.41 | **2,149,836,288** | 更正值 |
| FN107 OCF | 1,842,794,237.84 | **-4,840,052,606.46** | **+1,842,794,240** | **原报值，符号与更正值相反** |
| FN271 归母权益 | 32,032,959,807.76 | 28,413,344,515.00 | **28,413,343,744** | 更正值 |

收入相对更正值的约 239.94 元、利润 6.59 元、权益 -771 元偏差符合对应 float32 舍入；OCF 的约 **66.83 亿元**修订差不是精度噪声。纯 struct 与已装 mootdx 结果一致，不能归因于一套解析器的列名错位。**CONFIRMED_DEFECT：受检包的四个所需字段不属于一致披露版本**；这不是本轮新发现的 chstockdata runtime 缺陷，也不泛化为全部 TDX 文件均混合。

字段分别判断：

| 所需输入 | 已取得的证据 | 尚未合格的部分 |
| --- | --- | --- |
| 利润/OCF/权益 | FN96/FN107/FN271；官方 FN107/271 名称、社区字段表、两期实物/已保存源值锚定，元单位有数值互证 | 康美 2017 跨字段版本不一致；未取得预热权益/完整更正链 |
| 收入 | FN74 与原/更正锚及社区字段表一致；是营业收入，不保证所有金融类/营业总收入等同 | 不能将 FN230 替作累计收入；金融股范围另由消费者冻结 |
| 股本 | FN238，报告期时点股数；2026 样本与 THS 股本按 float32 舍入一致；gbbq 有变化事件 | 非无损整数，非逐日完整股本合同，不能最新股本倒推历史 |
| ROE | FN6/FN281 可解码；2017 分别约 **5.254% / 4.81%** | 不匹配既有披露锚 14.02%、7.20%/7.68%，口径/重算原因 UNKNOWN；不能静默用任一值通过 S07 |
| 公告/报告期 | 头报告期=20171231；FN314=**180426**，按官方 YYMMDD 为 2018-04-26 | 不是三项已更正数值的修订公告日，也无 first_available_at/修订 ID |

FN230/232/234 单季陷阱有作者跨季测试证据，本轮 2017 年末三值与累计槽显著不同；2026Q1 单季/累计相同本身不能独立证明全部季度语义。官方若仅声明字段 double，也不改变落盘 float32 的精度上限。600519 两期作为正常解析控制保留，但本轮未新增其完整披露锚定，不能据它宣称全字段已认证。

### 6.2 三个历史 T 的独立裁决

| T | 2017 年报允许的信息状态 | 本次包实际能力 / 资格 |
| --- | --- | --- |
| **2018-04-24** | 原报 04-26 尚未披露；本次原报/更正版均不可用 | FN314 过滤可排除这一行；仅此一项排除不证明 PIT 完整 |
| **2018-04-27** | 应能使用 04-26 原版，不能使用 2019 更正数值 | 源行 FN314 已满足截止条件，但收入/利润/权益已经是更正值；若直接按该日期放行会回填未来值；原版四项不能同时交付，**FAIL** |
| **2019-05-06** | 已有 04-30 更正披露，应标明该版本 | 三项匹配更正，OCF 仍原值；没有一致更正版及其源端当时可得证明，**FAIL / INSUFFICIENT_EVIDENCE** |

受检文件中每证券的索引记录不是不同历史版本接口；文件没有三历史 T/as-of 选择机制。只对当前所获实物裁决，**未证明源的所有其他档案永久不保留旧版**。本包标签必须为 `HISTORICAL_PERIOD_VALUES_ONLY / MIXED_REVISION_FIELDS`，禁止 `ASOF_VERIFIED`，也不能称“每期完整最新修订值”。原 OCF 单项留存不等于原版年报留存。

## 7. 历史估值、全池和使用边界

| 层面 | 本轮实际能力 | 资格 |
| --- | --- | --- |
| 指定日价格/Amount/Volume | 本地真实日线；既有 reader 验证成功，覆盖早于目标年度但尾部已旧 | 可作受限原始输入；非完整当前扫描/交易资格 |
| 历史股本/公司行为 | 两个真实 gbbq 解码；例如 600518 的 2017-12-22 类别5后总股本 raw=497425.375，按社区万股解释约49.7425亿，与期间 FN238 量级相符 | **PARTIAL**；单位转换有实现/量级证据，公告时点、事件完备性、版本、全部类别语义未逐项认证 |
| 历史市值 | [官方 GP16](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10muc82r55k.html)文档为总市值（万元），作者有返回样例；[by_date](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h2pci5gh6h7k.html)支持 year/mmdd，要求预先下载股票包 | 本机 TQ 不可达，未取得 GP16 实物；**NOT_VERIFIED** |
| 指定日历史 PE | 已有日线/gpcw 中没有本轮认证的逐日 PE 列；作者 BK5 是板块估值，不是个股历史 PE；GO33 为最新股本快照 | **NOT_QUALIFIED**；不能把名称/自算说明当可交付序列 |
| 自算 PE/市值 | 技术上可结合未复权价格、当日有效股本、选定口径利润，但利润历史版本当前有反例 | 不计算/冻结 S07 PE，不用最新股本回推；不拿复权 close×股本认证当时总市值 |
| 历史报告期/预热/退市 | 只取得 20171231、20260331 两期实物；目录条目不证明内容资格；4,595/5,517 是包索引条数 | 全目标年度逐期、必要基期、退市证券与历史分母 **INSUFFICIENT_EVIDENCE**；不将包条数当当时上市全池 |

**当前数值供给与完整 S07 分开：**2026Q1 固定五字段已证有用；本次不证明最新期/全市场覆盖或吞吐，不授予 DR05 CURRENT_SCAN PASS。历史旧版、估值、行业有效区间/历史证券池也不因找到日线而解除。没有新增生产依赖；不提出统一 TDX 平台。

[通达信官方适用说明](https://www.tdx.com.cn/article/stockfin.html)仍限定增强券商版本/个人收费版本的应用场景，并建议解压覆盖 cw。本轮遵守禁止覆盖，实际采用隔离保存和内存解析。该说明不等于本机某账号有增强功能，也不表示匿名成功文件获取自动赋予商业分发权。**推论边界：**四项目代码许可证均不转让通达信、交易所或发行人数据权利；本轮未取得再分发授权、商业 SLA 或全库长期免费承诺，商业产品使用边界记 UNKNOWN，须独立确认，不据此要求购买。

## 8. 最小供给建议、证据与停止

**建议复用路径：**已有 `load_vipdoc_daily` 供应其认证范围内 RAW 日线；已有 mootdx 的纯 DAT 解析能力可作为未来财务原值候选；已有 gbbq 作为公司行为/历史股本候选。两份真实财务包和本轮源值对账保留，具有独立价值。**不启动 Provider/API，不以日期过滤修补缺失版本，不批量下载更多包。**

**唯一最小下一动作：Owner 对本报告裁决，确认 TDX 定位为原始数值/公司行为候选，S07 历史供应必须要求现成可交付的一致原版、更正版、修订可知时间及所选逐日估值证据。** 本轮无 ASOF 合格来源候选，不能授权实施。若 Owner 仍选择 TDX 作为 S07 历史主源，需要的是已有版本档案/供应证据，不是再搜同一 VIPDOC、重新取同一当前 2017 包或安装更新脚本；没有新版本实物不重开类似调查。

| 分类 | 结果 |
| --- | --- |
| CONFIRMED_DEFECT | 受检 600518/2017 文件混合原/更正字段，原公告日不足以约束当前修订数值；stock-analysis 所读回填方法不能直接用于本任务 PIT。均不在本轮修改。 |
| UNRESOLVED_RISK | 客户端增强/TQ 权限与版本、全部历史版本/预热/退市覆盖、ROE口径、逐日估值及商业使用边界。 |
| SPECULATIVE_CONCERN | “所有 TDX 文件均混合”“任何免费通达信都无旧版”均未证实，不作为追加工程理由。 |
| FUTURE_ENHANCEMENT | 若 Owner 另行授权且输入合格，才审议窄财务数值出口；当前不是已接受方案或下一阶段授权。 |

有界证据的复核程序为 [verify_delivery.py](evidence/2026-10-20-w5h-r3/verify_delivery.py)，终检及完整文件长度/SHA 见 final_verification.json、[manifest.json](evidence/2026-10-20-w5h-r3/manifest.json)。验证只包含真实文件结构/CRC、两套解析、已保存披露/THS 对账、四个现有日线 reader 案例及 Git/原文件保护；不运行策略、收益回测、全池采集或发行测试。临时调查脚本的模块加载/编码问题已在证据目录内修正；计算线路清理异常按原失败保留，没有用重试掩盖。

```ini
CURRENT_DECISION = INVESTIGATE
W5_H_R3_VERDICT = FREE_RAW_ACCESS_PROVEN_BUT_S07_NOT_QUALIFIED

LOCAL_VIPDOC_FOUND = YES
LOCAL_VIPDOC_PATHS = C:/zd_zxzq_gm/vipdoc; C:/Users/Administrator/.chstockdata/cache/vipdoc; D:/Dev/Projects/chstockdata/.rh3a2-vipdoc; D:/Dev/Projects/chstockdata-frozen-v042/.rh3a2-vipdoc
LOCAL_DAILY_DATA_STATUS = REAL_FILES_READABLE_BUT_STALE_AND_SCOPE_BOUNDED
LOCAL_CW_FINANCIAL_STATUS = BOTH_CLIENT_CW_EMPTY; REAL_FINANCIAL_FILES_FOUND_ELSEWHERE
LOCAL_GPCW_FILES = EXISTING_20260331_ZIP_AND_IDENTICAL_DAT; ISOLATED_OFFICIAL_20171231_ZIP_OBTAINED
LOCAL_CORPORATE_ACTION_DATA = TWO_GBBQ_FILES_DECODED_FIXED_CASES; HISTORICAL_CONTRACT_PARTIAL

TDX_CLIENT_CAPABILITY = ZX_CLIENT_AND_DAILY_FILES_PRESENT; HX_DATA_REMNANTS; ENHANCED_TQ_VERSION_UNKNOWN
TDX_TQ_LOCAL_ACCESS = TCP_UNREACHABLE_ONE_ATTEMPT; NO_FINANCIAL_RPC
TDX_FINANCIAL_RAW_SAMPLE = YES_600518_AND_600519_20171231_AND_20260331
TDX_FREE_ACCESS_EVIDENCE = ONE_ANONYMOUS_OFFICIAL_HTTP_ZIP_WITH_LENGTH_MD5_CRC_DAT_AND_FIXED_ROWS_VERIFIED

GITHUB_REFERENCE_PROJECTS = tdx_quant; stock-analysis; mootdx; pytdx_archived_master
REUSABLE_EXISTING_CODE = chstockdata.load_vipdoc_daily; installed_mootdx_DAT_parser; existing_local_gbbq_parser_as_research_reference
NEW_DEPENDENCY_NEEDED = NO

FINANCIAL_FIELD_VERIFICATION = PARTIAL; 2026Q1_FIVE_FIELDS_MATCH; 2017_MIXED_REVISION_FIELDS; ROE_NOT_QUALIFIED
FINANCIAL_ORIGINAL_VERSION = NOT_DELIVERED_AS_CONSISTENT_2017_VERSION
FINANCIAL_REVISION_VERSION = THREE_FIELDS_MATCH_BUT_OCF_OLD; CONSISTENT_VERSION_NOT_DELIVERED
FINANCIAL_ASOF_QUALIFICATION = HISTORICAL_PERIOD_VALUES_ONLY; MIXED_REVISION_FIELDS; NOT_ASOF_VERIFIED
HISTORICAL_PE_QUALIFICATION = NOT_QUALIFIED
FULL_UNIVERSE_FEASIBILITY = BULK_FORMAT_REAL; FULL_SCOPE_WARMUP_DELISTED_AND_CURRENT_COVERAGE_NOT_QUALIFIED

S07_HISTORICAL_GATE = NOT_PASSED
RECOMMENDED_SUPPLY_PATH = REUSE_BOUNDED_RAW_DAILY; KEEP_FINANCIAL_AND_ACTION_VALUES_AS_CANDIDATES; REQUIRE_VERSIONED_ARCHIVE_AND_VALUATION_FOR_S07
NEXT_MINIMUM_ACTION = OWNER_DECIDE_SOURCE_BOUNDARY_FROM_THIS_REPORT; NO_REPEAT_LOCAL_OR_CURRENT_PACKAGE_SEARCH

SCOPE_DEVIATION = NO_PRODUCT_OR_IMPLEMENTATION_SCOPE_CHANGE; BOUNDED_READ_ONLY_EXISTING_EASY_TDX_PARSER_REFERENCE
RUNTIME_CHANGED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```

## 9. ChatGPT handoff

- 当前阶段/步骤：W5-H-R3 调查与来源资格核验完成，等待 Owner Review；不是实施阶段。
- 提交/工作树：chstockdata `69957a58bcfd258f011c9c80250b58704fe0d784`；本任务仅新增本报告及 `evidence/2026-10-20-w5h-r3/`。原有工作保留，三仓库 HEAD/已跟踪内容未变，无 commit/push；SIOS 并行新增未跟踪研究文件已保留，完整状态比较见终检。
- Gate：文件可获取/可解析的窄事实 **PASS**；完整财务字段一致性 **NOT_PASSED**；历史 as-of、历史 PE、完整 S07 **NOT_PASSED**。决定性证据是 fixed_2017_qualification.json 的三修订字段＋原 OCF＋原公告日，以及 local_financial_sample/supplement 的 2026 数值对账。
- 阻断/范围变化：缺一致旧版/修订链、ROE/估值口径及完整目标覆盖；没有产品范围变化或 runtime 修改。只读借用既有 easy_tdx 纯 gbbq 解析器是为落实本机公司行为调查，没有安装依赖或改该仓库。
- 推荐下一动作：Owner 裁决上述来源边界与所需现成历史版本/估值输入；不再要求同类本机查找，不默认批准新 Provider、下一阶段或发行。
