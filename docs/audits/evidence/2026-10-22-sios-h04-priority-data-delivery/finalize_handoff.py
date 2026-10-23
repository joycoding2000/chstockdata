"""Write the requested audit and final read-only repository handoff."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
SIOS=Path("D:/Dev/Projects/systematic-investing-os")
PACKAGE=ROOT/"H04-TR-delivery"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(repo,*args):
    return subprocess.check_output(["git","-C",str(repo),*args]).decode("utf-8")


def main():
    completion=read(ROOT/"completion.json")
    assert completion["independent_receipt"]["integrity_and_economic_accounting_pass"]
    baseline=read(ROOT/"context.json")["repositories"]
    current={}
    for label,repo in (("producer",REPO),("consumer",SIOS)):
        current[label]={"head":git(repo,"rev-parse","HEAD").strip(),"status":git(repo,"status","--porcelain"),"diff_sha256":hashlib.sha256(git(repo,"diff","HEAD").encode("utf-8")).hexdigest()}
        assert current[label]["diff_sha256"]==baseline[label]["diff_sha256"]
        current[label]["capture_baseline_head"]=baseline[label]["head"]
        current[label]["head_changed_during_task"]=current[label]["head"]!=baseline[label]["head"]
        current[label]["latest_commit_subject"]=git(repo,"log","-1","--format=%s").strip()
        current[label]["committed_paths_since_capture"]=git(repo,"diff","--name-only",baseline[label]["head"],"HEAD").splitlines()
    consumer_status_unchanged=current["consumer"]["status"]==baseline["consumer"]["status"]
    h01=REPO/"docs/audits/evidence/2026-10-22-sios-h01-final-repair/H01-delivery-repaired/manifest.json"
    assert hashlib.sha256(h01.read_bytes()).hexdigest()=="8d2f2400b011891f17f6e9c9e2950c6608ab12d1759044cc06e04040e02be79a"
    for source in ROOT.rglob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"),filename=str(source))
    assert ROOT.resolve()==(REPO/"docs/audits/evidence/2026-10-22-sios-h04-priority-data-delivery").resolve()
    removed=[]
    for cache in ROOT.rglob("__pycache__"):
        assert ROOT.resolve() in cache.resolve().parents
        for path in cache.iterdir():
            if path.is_file() and path.suffix==".pyc":
                removed.append(path.relative_to(ROOT).as_posix()); path.unlink()
        if not any(cache.iterdir()):
            cache.rmdir()
    evidence="evidence/2026-10-22-sios-h04-priority-data-delivery/"
    data=evidence+"H04-TR-delivery/"
    events=read(PACKAGE/"fund_actions.json")["events"]
    snapshots=read(PACKAGE/"H04-attribution-delivery/fund_holdings_snapshots.json")
    event_table="\n".join(f"| {e['announcement_date']} | {e['equity_record_date']} | {e['ex_dividend_date']} | {e['payment_date']} | {e['cash_per_share_cny']} |" for e in events)
    snapshot_table="\n".join(f"| {x['instrument_id']} | {x['observation_date']} | {x['publication_date']} | {x['canonical_hk_securities']} | {x['top_3_industries_nav_weight_percent']}% |" for x in snapshots)
    report=f"""# SIOS H04 优先免费数据交付：总回报就绪，归因仍阻断

执行日期：2026-10-23，Asia/Shanghai。按 Owner 指定的 2026-10-22 文件路径交付。
结论：**H04_TR_READY_ATTRIBUTION_BLOCKED**。总回报输入为 `PASS_FOR_CONSUMER_REVIEW`；归因为 `PARTIAL_WITH_NAMED_GAPS`。这是生产者离线交付裁决，SIOS 独立消费者接收尚未发生，原机制实例继续 `STOP_CURRENT_INSTANCE`。

交付：[数据 ZIP]({evidence}H04-TR-delivery.zip)、[包内说明]({data}README.md)、[manifest]({data}manifest.json)、[独立接收结果]({data}validation_report.json)。ZIP 为 {completion['zip_bytes']:,} 字节、{completion['zip_file_count']} 个文件；ZIP SHA256 `{completion['zip_sha256']}`；manifest SHA256 `{completion['manifest_sha256']}`。

## 原合同、范围和已有状态

已读取两个仓库 AGENTS.md、原准入合同 H04 §4/§6、2026-10-20 交接、H01 修复包和离线资格/接收程序，以及基金公司行动实现。当前 SIOS checkout 不含两份历史合同，分别从 `d75867d3f4c297452d6ff4777aac631bb66edc8c` 和 `6d47fd2e98c5ba3efcdd7ff0a6e9add8eabff9b9` 恢复到本包 contracts；没有改消费者 checkout。来源身份和基线在 context.json。

H04 原合同只给已暴露的 2024–2025 共同历史，未冻结 H01 的 2025-09-30 截止。本次调查边界仍为 2024-01-01..2025-12-31，实际交易记录为 **2024-01-02..2025-12-31，每 ETF 485 日**，未将取数边界提升为策略实验冻结窗口。每只另给 2023-03-09..2023-12-29 的 200 条预热参考；H04 静态问题没有因此新增 126/SMA200 规则。没有换 ETF、指数或按成功日期缩窗。

H01 维持 CLOSED_PASS_BOUNDED，原修复包 manifest 与既有 SHA 一致。P2 维持 QUEUED。没有运行任何 H04 策略收益、排名、成本实验、回测或消费者策略代码。

## 第一交付：真实 ETF 总回报输入

两只原 .day 文件分别 1,073/1,480 条，首日为 2022-04-25/2020-08-18，尾日均 2026-09-22；完整源文件与原消费者记录 SHA 相同。导出每 ETF 685 条、共 **1,370 条**，其中调查段 970 条，预热参考 400 条。独立上证综指缓存仅提供境内日期序列；两基金相对该日历无缺行、无零成交行。

价格保留原 uint32 和÷1000 元/份值，Volume 为份额股数 SHARE，Amount 为人民币元，保留 float32 位编码和完整精确十进制值。接收器逐行核对源字节偏移、日期、整数、float32 位值、OHLC 和 amount/volume 位于交易价格区间；没有改生产读取器。

513530 的三份独立官方年报确认 2023/2024 无收益分配、2025 合计每10份0.9000元。七份管理人原始公告与年报/F10交叉一致，合计 **0.09元/份**。513990 的三份独立官方年报支持各报告期间无收益分配；两只基金的份额变动披露均支持范围内无持有人单位折算/拆分。没有借用 H01 的无事件结论。

513530 的真实现金事件如下，所有金额单位均为 CNY/份：

| 公告 | 登记 | 除息 | 发放/领取日 | 每份现金 |
| --- | --- | --- | --- | ---: |
{event_table}

公告只披露日期，保守可知时刻标注当日23:59:59；不是伪造的历史实际抓取时刻。官方公告明确指定交易投资者的领取日，现金按该日23:59:59后、下一合格交易时段才可使用。除息生效时先记应收，发放日收盘仍不提前计可用现金；支付转账不再产生第二次收益。真实券商入账时刻、未办理指定交易者的可用时刻保持 null。RAW 的 T15:00 可用时刻沿用交易所规则推定，历史下载版本未认证。

每日经济总回报因子为 `(P_t + D_ex,t) / P_t-1`。链接指数是标准毛总回报恒等式，含除息再投资的数学口径，**不能作支付前可执行再投资策略**。同时交付实际一份连续持有、股息留现的财富账 `价格+应收+保守可用现金`；消费者须独立审阅再投资、税费和执行定义。全程不使用最新复权因子，2026年分红不进入历史输入，后发年报只作完整性审计。

真实首例：2025-06-16 前收1.652、当日收1.642、每份分红0.02；价格因子0.9939467312，经济因子1.0060532688。此为数据对账，不是策略表现。七个事件均在 [event_reconciliation.json]({data}event_reconciliation.json) 留有除息与支付样本。

现有 `get_fund_corporate_actions` 对捕获响应离线重放：513530 success/complete/7条，513990 normal_empty/complete/0条；没有网络回退。2026-10-19 两次 request_error 仍按合同记录保留为真实访问失败；原任务未存供应商响应的事实亦保留，未伪造旧原件。当前成功/空结果不会改写旧失败。

## 第二交付：历史归因部分输入

对照指数已确认为 **H50069 上证港股通指数**。其母池是上交所公布的港股通证券；930914 的母池为中证香港300中符合港股通条件者，二者不同。早期猜测的000159（沪股通）及H11054（装备产业）方法原件已按身份不符排除，不参与合格数据。

已交付 [930914官方方法V1.2](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/930914_Index_Methodology_cn.pdf)（2024-11标注）、[H50069官方V1.1](https://www.sse.com.cn/market/sseindex/indexlist/indexdetails/indexmethods/c1/H50069_H50069hbook_CN.pdf)（2020-12更新）、H50069旧方法及两基金各两份2023/2025历史招募说明书。文件标注年月、内容截止、披露及本次抓取时点不能混为生效区间；完整修订/生效链未认证。

**具体版本冲突**：930914 V1.2 包含过去三年平均及最近一年支付率均大于0、小于1的条件；513530 的2025招募说明书仍描述旧的连续正现金股息率筛选，没有同一支付率条件。因此不得用当前 V1.2 倒填2024全年，也不能擅自把基金招募描述当作指数完整修订链。

从四个共同半年度日期恢复 **8份真实基金截面、868条证券×截面、88条行业×截面**。HG/HK 两通道按同一港股代码归并，保留金额与通道，避免把同一证券算两次；各截面证券公允价值合计与行业合计精确到分一致。原行业名和彭博来源保留，归一到11个大类；历史分类发布版本仍未知，金额权重不强行归一成100%。这些是实际基金持仓，**真实历史指数权重截面仍为0**。

| 基金 | 观察截面 | 实际披露日期 | 证券数 | 前三行业占基金净值 |
| --- | --- | --- | ---: | ---: |
{snapshot_table}

以上只描述具名产品风险暴露，不输出红利机制净价值。2025-12-31截面于2026年披露，只可事后归因，不回填2025历史决策。原件还保留市场/外汇/利率会计敏感性披露；不将“未持有债券”推成“股票利率暴露为零”。价值、质量及股权利率风险的解释序列仍未知。

华泰柏瑞中英双语跨页持仓中的数量/名称未作合格结构化解析，数量保留 null；可用的证券身份、金额及权重均保留，原件完整。招商2024-06-30另有 HK:09930 主动残余持仓506.54元，已保留，未当指数成分。它也是基金持仓不能冒充指数权重的实证边界。

六项强制具名缺口：

1. `H04-INDEX-VERSION-EFFECTIVE-CHAIN`：两指数完整方法生效链，尤其930914冲突的实际变更日期。
2. `H04-HISTORICAL-PARENT-UNIVERSE`：历史母池成员与调整版本，无法分离不同可投资母池的影响。
3. `H04-TRUE-INDEX-CONSTITUENTS-WEIGHTS`：真实指数历史成分、权重、进入退出及发布时间；基金持仓不能替代。既定通用权重路径返回HTTP404，未取得历史文件。
4. `H04-INDUSTRY-CONTINUOUS-HISTORY`：四对截面之间的行业漂移、历史分类版本及连续行业对照。
5. `H04-VALUE-QUALITY-RATE-EXPLANATORY-SERIES`：价值、质量与股票利率敏感性序列，风险贡献不能记零。
6. `H04-HISTORICAL-INDEX-MARKET-CONTROL`：独立合格的连续历史市场/行业指数回报控制输入。

免费管理人资料已补齐权益及总回报数据，并提供上述低成本历史暴露截面；本次既定路径未补齐连续真实指数/母池和风格解释。不能据有限调查声称所有免费来源永远无解，也不为全历史自动建设港股平台。建议维持STOP并由SIOS独立接收TR、记录归因缺口；任何扩大调查或改变研究问题均另待Owner决定。

## 验证、来源预算及环境

7项经济语义/真实源解析测试通过，5项独立接收篡改拒绝测试通过；包含真实每10份单位、未来公告拒绝、支付日收盘现金资格、跨页HG/HK归并、主动残余持仓，以及十倍分红、提前现金、复权回填、提前持仓披露和乐观归因Gate的拒绝。初始失败与支付截止红阶段证据保留。

独立接收器不导入导出程序或SIOS，以Fraction独立复算1,370条经济回报/财富记录，重新提取24份原始PDF，errors=[]。全套最终验证在新进程禁用出站socket；包内离线再重建manifest逐字节一致，ZIP CRC及包内manifest一致。消费者身份仍为生产者独立程序，**不是SIOS已完成独立验收**。具体命令、退出码及stdout/stderr均在evidence。

精确捕获 **61次直接HTTP，37,415,572字节响应体**，无自动重试，单体最大3,689,170字节；另有1次官方域名网页搜索工具查询和1次失败的Firecrawl状态工具调用，其内部传输字节不可见。已明确保留6请求槽/3,000,000字节作为这两次工具的保守预留，合计预算占用按67槽/40,415,572字节控制；不声称精确全栈流量。每项直接请求的URL、时刻、HTTP状态、字节和SHA在network_ledger.json，源码保存没有下载令牌或请求签名。来源路径已关闭。

HTTP200不等于数据成功：伪PDF挑战、错误参数、公开请求协议错误、错误指数身份均被识别并保留；没有当正常空结果。使用原.venv，没有创建新运行环境、数据库或构建目录。归档和验证后仅清理本任务拥有的.pyc/空__pycache__，未清理其他任务、研究证据、源缓存或worktree。

## 裁决和完整交接

```ini
CURRENT_DECISION = OWNER_REVIEW
H04_SECURITIES = 513530,513990
H04_TOTAL_RETURN_DATA_GATE = PASS_FOR_CONSUMER_REVIEW
H04_ATTRIBUTION_DATA_GATE = PARTIAL_WITH_NAMED_GAPS
H04_DELIVERY_VERDICT = H04_TR_READY_ATTRIBUTION_BLOCKED
RAW_ETF_COVERAGE = 485_INVESTIGATION_PLUS_200_WARMUP_PER_FUND; NO_MISSING_SESSIONS
FUND_DISTRIBUTION_EVIDENCE = SIX_INDEPENDENT_OFFICIAL_ANNUALS; SEVEN_513530_CASH_NOTICES; 513990_NO_EVENT_IN_SCOPE
TOTAL_RETURN_QUALIFIED_ROWS = 1370; INVESTIGATION_970; WARMUP_REFERENCE_400
PIT_QUALIFICATION = BOUNDED_ECONOMIC_INPUT; RAW_EXCHANGE_RULE; DATE_END_ANNOUNCEMENT_AND_CASH; OBSERVED_VINTAGE_NOT_ATTESTED
INDEX_METHOD_VERSIONS = 930914_2024_11_V1.2; H50069_2020_12_V1.1; EFFECTIVE_CHAIN_UNRESOLVED
HISTORICAL_CONSTITUENTS_COVERAGE = EIGHT_ACTUAL_FUND_PROXIES; 868_SECURITY_SNAPSHOT_ROWS; TRUE_INDEX_HISTORY_NOT_QUALIFIED
HISTORICAL_WEIGHTS_COVERAGE = FUND_SNAPSHOTS_ONLY; TRUE_INDEX_WEIGHT_SNAPSHOTS_0
INDUSTRY_ATTRIBUTION_COVERAGE = FOUR_PAIRED_DATES; 88_SECTOR_OBSERVATIONS; CONTINUOUS_ATTRIBUTION_UNRESOLVED
OTHER_RISK_ATTRIBUTION_EVIDENCE = ISSUER_MARKET_FX_RATE_DISCLOSURES; VALUE_QUALITY_EQUITY_RATE_SERIES_MISSING_NOT_ZERO
ACTUAL_NETWORK_BUDGET_USED = 61_CAPTURED_HTTP; 37415572_BODY_BYTES; PLUS_1_WEB_QUERY_1_FAILED_STATUS; OPAQUE_TOOL_TRANSPORT_NOT_EXPOSED; RESERVED_TOTAL_67_SLOTS_40415572_BYTES
INDEPENDENT_VALIDATION = 7_ECONOMIC_TESTS_5_MUTATION_TESTS_PASS; 24_ORIGINAL_PDFS_REEXTRACTED; 1370_ROWS_RECOMPUTED; SIOS_RECEIPT_PENDING
DELIVERY_PATH = docs/audits/evidence/2026-10-22-sios-h04-priority-data-delivery/H04-TR-delivery
MANIFEST_SHA256 = {completion['manifest_sha256']}
REMAINING_NAMED_GAPS = SIX_ATTRIBUTION_GAPS_LISTED_ABOVE; BROKER_ACTUAL_CREDIT_AND_VINTAGE_REMAIN_UNKNOWN_USE_CONDITIONS
SIOS_CONSUMER_ACCEPTANCE_READY = TR_PACKAGE_YES; ATTRIBUTION_PARTIAL_ONLY; ACTUAL_ACCEPTANCE_PENDING
H04_RESEARCH_RESUMPTION_AUTHORIZED = NO
H01_DATA_SUPPLY = CLOSED_PASS_BOUNDED
P2 = QUEUED
PRODUCTION_IMPLEMENTATION_AUTHORIZED = NO
GIT_COMMIT = NO
GIT_PUSH = NO
OWNER_REVIEW_REQUIRED = YES
```

当前阶段/步骤：SIOS H04 独立供数，离线交付及生产者独立接收结束，停止于Owner Review。交付时chstockdata HEAD `{current['producer']['head']}`；SIOS HEAD `{current['consumer']['head']}`。取证起点分别为 `{baseline['producer']['head']}` / `{baseline['consumer']['head']}`，包内context保留起点身份。任务期间出现会话外H01归档提交，提交主题分别为“{current['producer']['latest_commit_subject']}”和“{current['consumer']['latest_commit_subject']}”；已记录并保留，未回滚或改写。本任务没有执行commit/push，也没有修改SIOS；两仓库当前tracked diff为空。本任务仅新增本报告和本轮evidence，最终工作树、会话外提交路径及起点对照见final_handoff.json。没有范围变更，下一阶段未获授权。

发现分类：本轮离线日历价格误检、跨页代码/现金截止及主动持仓遗漏是已修复的 `CONFIRMED_DEFECT`；真实历史指数/母池/风格及方法生效链为 `UNRESOLVED_RISK`；“差异一定全部来自行业/价值”等仍为 `SPECULATIVE_CONCERN`；通用港股因子平台为未授权 `FUTURE_ENHANCEMENT`。

学习与下一决定：原问题是免费现成范围能否交付验证红利机制的两类数据；实际已取得真实总回报与若干可审历史风险事实，但不同母池和遗漏风格仍阻止纯股息识别。可核数据存在不等于机制独立或净投资价值已成立。下一最小动作是SIOS独立接收本包并将具名归因限制提交Owner，研究实例继续STOP，不启动P2。
"""
    report_path=REPO/"docs/audits/2026-10-22-sios-h04-priority-data-delivery.md"
    report_path.write_text(report,encoding="utf-8")
    handoff={"current_phase":completion["phase"],"current_step":completion["step"],"repositories":current,"gates":completion["independent_receipt"],"manifest_sha256":completion["manifest_sha256"],"zip_sha256":completion["zip_sha256"],"report_sha256":hashlib.sha256(report_path.read_bytes()).hexdigest(),"h01_original_manifest_preserved":True,"owned_bytecode_removed":removed,"AST_parse_pass":True,"scope_changes":[],"next_action":"SIOS independent consumer receipt and Owner Review; H04 STOP remains; no P2 or research authorization"}
    (ROOT/"final_handoff.json").write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"report":str(report_path),"manifest_sha256":completion["manifest_sha256"],"heads":{k:v["head"] for k,v in current.items()},"tracked_diff_unchanged":True,"SIOS_status_unchanged":consumer_status_unchanged,"concurrent_H01_archival_commits_preserved":True,"owned_bytecode_removed":len(removed)},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
