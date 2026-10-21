import json
import urllib.parse
from audit_common import OUT, request, save

issuer=json.loads((OUT/'cninfo_issuer_search.json').read_text(encoding='utf-8'))[0]
assert issuer['code']=='600518'
summary={}
for name, keyword, dates in [
    ('original_2017_index','2017年年度报告','2018-04-01~2018-05-01'),
    ('correction_chain_index','更正','2018-04-26~2019-05-06'),
    ('annual_2018_index','2018年年度报告','2019-04-01~2019-05-06'),
]:
    params={'pageNum':'1','pageSize':'100','column':'sse','tabName':'fulltext','plate':'','stock':f'600518,{issuer["orgId"]}','searchkey':keyword,'secid':'','category':'','trade':'','seDate':dates,'sortName':'time','sortType':'asc','isHLtitle':'true'}
    b=request(name+'.json','https://www.cninfo.com.cn/new/hisAnnouncement/query',data=urllib.parse.urlencode(params).encode('utf-8'),headers={'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.cninfo.com.cn/'},max_bytes=1_000_000)
    if not b:continue
    obj=json.loads(b)
    records=[{k:r.get(k) for k in ('secCode','secName','orgId','announcementId','announcementTitle','announcementTime','adjunctUrl','adjunctType','adjunctSize')} for r in obj.get('announcements') or []]
    summary[name]={'totalAnnouncement':obj.get('totalAnnouncement'),'totalpages':obj.get('totalpages'),'hasMore':obj.get('hasMore'),'records':records}
save('cninfo_index_summary.json',summary)
print(json.dumps(summary,ensure_ascii=True))
