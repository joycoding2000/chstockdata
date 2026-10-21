import json,urllib.parse
from acquire import request
f={'pageNum':'2','pageSize':'30','column':'sse','tabName':'fulltext','plate':'','stock':'600518,gssh0600518','searchkey':'','secid':'','category':'','trade':'','seDate':'2018-04-24~2019-05-06','sortName':'time','sortType':'asc','isHLtitle':'true'}
u='https://www.cninfo.com.cn/new/hisAnnouncement/query?'+urllib.parse.urlencode(f)
b=request('index/600518-get-page2.json',u)
j=json.loads(b);print(json.dumps({'total':j.get('totalAnnouncement'),'count':len(j.get('announcements') or []),'first':[r['announcementId'] for r in j.get('announcements') or []][:3]}))
