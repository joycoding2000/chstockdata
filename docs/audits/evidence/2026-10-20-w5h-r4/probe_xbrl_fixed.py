import json
import urllib.parse
from audit_common import request

queries=[
    ('sse_xbrl_2017_index.json','https://query.sse.com.cn/commonSoaQuery.do',{'isPagination':'true','sqlId':'COMMON_SSE_PL_XBRL_YJGL','stockId':'600518','startYear':'2017','endYear':'2017','reportPeriodId':'5000','type':'inParams','isMax':'','pageHelp.pageSize':'25','pageHelp.pageNo':'1','pageHelp.beginPage':'1','pageHelp.cacheSize':'1','pageHelp.endPage':'1'}),
    ('sse_xbrl_2017_cashflow.json','https://query.sse.com.cn/commonQuery.do',{'isPagination':'false','sqlId':'COMMON_MAP_CASHFLOW_C','type':'inParams','REPORT_YEAR':'2017','STOCK_ID':'600518','REPORT_PERIOD_ID':'5000'}),
]
for name,base,params in queries:
    b=request(name,base+'?'+urllib.parse.urlencode(params),headers={'Referer':'https://english.sse.com.cn/markets/dataservice/xbrl/'},max_bytes=1_000_000)
    if b:
        print(name,b[:5000].decode('utf-8',errors='replace').encode('ascii',errors='backslashreplace').decode())
