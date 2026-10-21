import json
from acquire import request
f={'stock':'600518,gssh0600518','tabName':'fulltext','pageSize':'30','pageNum':'2','column':'sse','category':'','plate':'sh','seDate':'2018-04-26~2018-04-26','searchkey':'','secid':'','sortName':'','sortType':'','isHLtitle':'true'}
j=json.loads(request('index/600518-official-form-day-page2.json','https://www.cninfo.com.cn/new/hisAnnouncement/query',f));print(json.dumps({'total':j.get('totalAnnouncement'),'count':len(j.get('announcements') or []),'first':[r['announcementId'] for r in j.get('announcements') or []][:3]}))
