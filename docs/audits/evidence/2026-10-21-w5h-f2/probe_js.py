from acquire import request
for name,url in [('person-stock-news.js','https://static.cninfo.com.cn/new/js/app/data/person-stock-news.js?v=20260710082532'),('common.js','https://static.cninfo.com.cn/new/assets/js/common.js?v=20260826101926')]:
 b=request('index/'+name,url,maximum=5000000)
 t=b.decode('utf-8',errors='replace')
 for key in ['hisAnnouncement','pageNum','pageSize']:
  start=0
  for _ in range(4):
   pos=t.find(key,start)
   if pos<0:break
   print(name,key,t[max(0,pos-180):pos+250])
   start=pos+len(key)
