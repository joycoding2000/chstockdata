"""Deterministic registry and routing rules for official policy sources."""

from __future__ import annotations

import re
from typing import Iterable

from .policy_news_models import Exchange, PolicySource, PolicyTargetContext


CORE_AUTHORITY_IDS = ("govcn", "ndrc", "mof", "pboc", "csrc")
EXCHANGE_AUTHORITY_IDS = ("sse", "szse", "bse")
INDUSTRY_AUTHORITY_IDS = (
    "miit",
    "nea",
    "nmpa",
    "nhsa",
    "nfra",
    "safe",
    "cac",
    "nda",
    "mohurd",
    "sasac",
    "mee",
)

_DEFAULT_BUDGET = {
    "pages": 2,
    "items": 20,
    "timeout": 15,
    "retries": 1,
    "min_interval": 0.25,
}


def _source(
    authority_id: str,
    authority_name: str,
    scope: str,
    endpoint: str | None,
    parser_id: str,
    *,
    fallback: bool,
    predicates: Iterable[str] = (),
    health_state: str = "enabled",
) -> PolicySource:
    return PolicySource(
        authority_id=authority_id,
        authority_name=authority_name,
        scope=scope,
        direct_official_endpoint=endpoint,
        govcn_fallback=fallback,
        route_predicates=tuple(predicates),
        request_budget=dict(_DEFAULT_BUDGET),
        parser_id=parser_id,
        health_state=health_state,
    )


_CORE_SOURCES = {
    "govcn": _source(
        "govcn",
        "中国政府网",
        "core",
        "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json",
        "govcn_json",
        fallback=False,
        predicates=("核心源",),
    ),
    "ndrc": _source(
        "ndrc",
        "国家发展改革委",
        "core",
        # 2026-09-11 实测：/xxgk/zcfb/ 已变为 54 字节 JS 跳转壳（跳 ./fzggwl/），
        # 原端点解析恒 failed_structure。fzggwl/ 为服务端渲染的政策发布库列表
        # （<li> + YYYY/MM/DD 日期，2026-09-11 实测 68 li / 25 日期）。
        "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/",
        "ndrc_html",
        fallback=True,
        predicates=("核心源", "产业规划", "投资价格"),
    ),
    "mof": _source(
        "mof",
        "财政部",
        "core",
        "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/",
        "mof_html",
        fallback=True,
        predicates=("核心源", "财政税收"),
    ),
    "pboc": _source(
        "pboc",
        "中国人民银行",
        "core",
        "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        "pboc_html",
        fallback=True,
        predicates=("核心源", "货币流动性"),
    ),
    # 2026-09-11 端点考古：common_list.shtml 是 SPA 壳（列表由 JS 渲染），且原注册
    # 频道 c101972 实为“市场禁入决定”（2026-09 前后已并停，最新记录停在 2024-04）。
    # 站点真实取数口为 searchList JSON 服务（common_list.js 的 table_ajax 暴露）。
    # 频道改挂“证监会令”（c101953，部门规章，政策性最强，实测最新 2026-05-15），
    # 其余可换频道：证监会公告 625a2f95cc104c1d8b646f98d9f87470。
    "csrc": _source(
        "csrc",
        "中国证监会",
        "core",
        "https://www.csrc.gov.cn/searchList/cd11df89f5894c1eac37ae37cc11e369"
        "?_isAgg=false&_isJson=true&_pageSize=18&_template=index"
        "&_rangeTimeGte=&_channelName=&page=1",
        "csrc_json",
        fallback=True,
        predicates=("核心源", "资本市场监管"),
    ),
}

_EXCHANGE_SOURCES = {
    "sse": _source(
        "sse",
        "上海证券交易所",
        "exchange",
        "https://www.sse.com.cn/regulation/supervision/dynamic/",
        "sse_html",
        fallback=False,
        predicates=("沪市交易场所监管",),
    ),
    "szse": _source(
        "szse",
        "深圳证券交易所",
        "exchange",
        "https://www.szse.cn/api/search/content",
        "szse_json",
        fallback=False,
        predicates=("深市交易场所监管",),
    ),
    "bse": _source(
        "bse",
        "北京证券交易所",
        "exchange",
        "https://www.bse.cn/regulation_rules.html",
        "bse_html",
        fallback=False,
        predicates=("北交所交易场所监管",),
    ),
}

_INDUSTRY_ENDPOINTS = {
    "miit": (
        "工业和信息化部",
        "https://www.miit.gov.cn/zwgk/zcwj/wjfb/index.html",
    ),
    "nea": (
        "国家能源局",
        "https://www.nea.gov.cn/policy/ds_40d365c13659452aa06cdb7268d6192e.json",
    ),
    "nmpa": ("国家药品监督管理局", "https://www.nmpa.gov.cn/xxgk/fgwj/"),
    "nhsa": ("国家医疗保障局", "https://www.nhsa.gov.cn/col/col14/index.html"),
    # 2026-09-11 端点考古：ItemList.html 是 Angular 壳；站点经 /cn/static/data/
    # 静态 JSON（Script.js 的 apiUrl_cdn 模式）取数。ItemId=926 为
    # 政务信息 > 政策法规 栏目（getWebMenuItem 栏目树实测），动态备用口：
    # /cbircweb/DocInfo/SelectDocByItemIdAndChild?itemId=926&pageIndex=1&pageSize=18
    "nfra": (
        "国家金融监督管理总局",
        "https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild"
        "/data_itemId=926,pageIndex=1,pageSize=18.json",
    ),
    "safe": ("国家外汇管理局", "https://www.safe.gov.cn/safe/whxw/index.html"),
    "cac": ("国家互联网信息办公室", "https://www.cac.gov.cn/"),
    "nda": ("国家数据局", "https://www.nda.gov.cn/sjj/zwgk/zcwj/index.html"),
    "mohurd": ("住房和城乡建设部", "https://www.mohurd.gov.cn/gongkai/zhengce/"),
    "sasac": ("国务院国资委", "https://www.sasac.gov.cn/n2588030/n2588325/index.html"),
    "mee": ("生态环境部", "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/"),
}

# The MIIT page currently returns an anti-bot shell rather than a
# fixture-qualified policy list.  Keep its official URL for auditability,
# fail closed, and use only the authorized gov.cn fallback path.  NEA's
# current official "latest documents" list is fixture-qualified below.
_INDUSTRY_DIRECT_UNAVAILABLE = {"miit"}

_INDUSTRY_SOURCES = {
    authority_id: _source(
        authority_id,
        authority_name,
        "industry",
        endpoint,
        f"{authority_id}_json"
        if authority_id in {"nea", "nfra"}
        else f"{authority_id}_html",
        fallback=True,
        predicates=("行业主管部门",),
        health_state=(
            "direct_unavailable"
            if authority_id in _INDUSTRY_DIRECT_UNAVAILABLE
            else "enabled"
        ),
    )
    for authority_id, (authority_name, endpoint) in _INDUSTRY_ENDPOINTS.items()
}


_PROVINCE_NAMES = (
    "北京市",
    "天津市",
    "河北省",
    "山西省",
    "内蒙古自治区",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "上海市",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "广西壮族自治区",
    "海南省",
    "重庆市",
    "四川省",
    "贵州省",
    "云南省",
    "西藏自治区",
    "陕西省",
    "甘肃省",
    "青海省",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
)

_PROVINCE_SLUGS = {
    "北京市": "beijing",
    "天津市": "tianjin",
    "河北省": "hebei",
    "山西省": "shanxi",
    "内蒙古自治区": "inner_mongolia",
    "辽宁省": "liaoning",
    "吉林省": "jilin",
    "黑龙江省": "heilongjiang",
    "上海市": "shanghai",
    "江苏省": "jiangsu",
    "浙江省": "zhejiang",
    "安徽省": "anhui",
    "福建省": "fujian",
    "江西省": "jiangxi",
    "山东省": "shandong",
    "河南省": "henan",
    "湖北省": "hubei",
    "湖南省": "hunan",
    "广东省": "guangdong",
    "广西壮族自治区": "guangxi",
    "海南省": "hainan",
    "重庆市": "chongqing",
    "四川省": "sichuan",
    "贵州省": "guizhou",
    "云南省": "yunnan",
    "西藏自治区": "tibet",
    "陕西省": "shaanxi",
    "甘肃省": "gansu",
    "青海省": "qinghai",
    "宁夏回族自治区": "ningxia",
    "新疆维吾尔自治区": "xinjiang",
}


def _province_aliases(name: str) -> tuple[str, ...]:
    aliases = {name, f"{name}板块"}
    for suffix in ("省", "市", "自治区"):
        if name.endswith(suffix):
            short = name[: -len(suffix)]
            aliases.update({short, f"{short}板块"})
    if name.endswith("壮族自治区"):
        short = name[: -len("壮族自治区")]
        aliases.update({short, f"{short}板块"})
    if name.endswith("维吾尔自治区"):
        short = name[: -len("维吾尔自治区")]
        aliases.update({short, f"{short}板块"})
    return tuple(sorted(alias for alias in aliases if alias))


PROVINCE_ALIAS_TO_NAME: dict[str, str] = {
    alias: name
    for name in _PROVINCE_NAMES
    for alias in _province_aliases(name)
}

_SHANDONG_ENDPOINT = "https://www.shandong.gov.cn/col/col94091/index.html"

PROVINCE_BY_NAME = {
    name: f"province_{_PROVINCE_SLUGS[name]}" for name in _PROVINCE_NAMES
}

PROVINCE_AUTHORITIES = {
    name: _source(
        PROVINCE_BY_NAME[name],
        f"{name}人民政府",
        "province",
        _SHANDONG_ENDPOINT if name == "山东省" else None,
        "shandong_html" if name == "山东省" else "govcn_html",
        fallback=True,
        predicates=(name, *_province_aliases(name)),
        health_state="enabled" if name == "山东省" else "direct_unavailable",
    )
    for name in _PROVINCE_NAMES
}


SOURCES: dict[str, PolicySource] = {
    **_CORE_SOURCES,
    **_EXCHANGE_SOURCES,
    **_INDUSTRY_SOURCES,
    **{source.authority_id: source for source in PROVINCE_AUTHORITIES.values()},
}


# Ordered from the most specific company/industry labels to broader labels.
# The order of this tuple is part of the deterministic routing contract.
INDUSTRY_RULES = (
    ("通信", "miit"),
    ("半导体", "miit"),
    ("芯片", "miit"),
    ("软件", "miit"),
    ("制造", "miit"),
    ("工业", "miit"),
    ("电池", "miit"),
    ("新能源", "nea"),
    ("能源", "nea"),
    ("电力", "nea"),
    ("煤炭", "nea"),
    ("油气", "nea"),
    ("医药", "nmpa"),
    ("医疗器械", "nmpa"),
    ("医疗", "nhsa"),
    ("银行", "nfra"),
    ("保险", "nfra"),
    ("非银金融", "nfra"),
    ("外汇", "safe"),
    ("人工智能", "cac"),
    ("互联网", "cac"),
    ("平台", "cac"),
    ("数据", "nda"),
    ("房地产", "mohurd"),
    ("建筑", "mohurd"),
    ("公用设施", "mohurd"),
    ("中央国企", "sasac"),
    ("地方国企", "sasac"),
    ("国有企业", "sasac"),
    ("国企", "sasac"),
    ("化工", "mee"),
    ("钢铁", "mee"),
    ("有色", "mee"),
    ("高排放", "mee"),
    ("高耗能", "mee"),
)


def exchange_for_ticker(ticker: str) -> Exchange:
    """Return the one trading venue implied by a six-digit A-share code."""

    if not isinstance(ticker, str) or not re.fullmatch(r"\d{6}", ticker):
        raise ValueError(f"unsupported A-stock code: {ticker!r}")
    if ticker.startswith(("92", "4", "8")):
        return "bse"
    if ticker.startswith(("5", "6", "9")):
        return "sse"
    if ticker.startswith(("0", "1", "2", "3")):
        return "szse"
    raise ValueError(f"unsupported A-stock code: {ticker!r}")


def normalize_province(board_names: Iterable[str]) -> str | None:
    """Map an ordered list of board labels to one province, if reliable."""

    for board_name in board_names:
        normalized = PROVINCE_ALIAS_TO_NAME.get(str(board_name).strip())
        if normalized:
            return normalized
    return None


def route_industry_authorities(
    *,
    industry: str | None,
    company_attributes: Iterable[str],
    concepts: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return selected and deterministically omitted industry authorities."""

    ordered_labels = ((industry,) if industry else ()) + tuple(company_attributes) + tuple(concepts)
    candidates = tuple(
        dict.fromkeys(
            authority_id
            for label in ordered_labels
            for keyword, authority_id in INDUSTRY_RULES
            if keyword in str(label or "") and authority_id not in CORE_AUTHORITY_IDS
        )
    )
    return candidates[:2], candidates[2:]


def select_policy_sources(context: PolicyTargetContext) -> tuple[PolicySource, ...]:
    """Select core, exchange, and conditional sources in stable registry order."""

    source_ids = CORE_AUTHORITY_IDS + (context.exchange,)
    if context.province and context.province in PROVINCE_BY_NAME:
        source_ids += (PROVINCE_BY_NAME[context.province],)
    source_ids += tuple(context.selected_industry_authorities[:2])
    return tuple(
        SOURCES[source_id]
        for source_id in dict.fromkeys(source_ids)
        if source_id in SOURCES
    )


__all__ = [
    "CORE_AUTHORITY_IDS",
    "EXCHANGE_AUTHORITY_IDS",
    "INDUSTRY_AUTHORITY_IDS",
    "INDUSTRY_RULES",
    "PROVINCE_ALIAS_TO_NAME",
    "PROVINCE_AUTHORITIES",
    "PROVINCE_BY_NAME",
    "SOURCES",
    "exchange_for_ticker",
    "normalize_province",
    "route_industry_authorities",
    "select_policy_sources",
]
