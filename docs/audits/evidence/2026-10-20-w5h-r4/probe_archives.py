import json
import urllib.parse
from audit_common import request

# Explicit first-layer public discovery, fixed issuer only.
body=urllib.parse.urlencode({'keyWord':'600518','maxNum':'10'}).encode('utf-8')
b=request('cninfo_issuer_search.json','https://www.cninfo.com.cn/new/information/topSearch/query',data=body,headers={'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.cninfo.com.cn/'},max_bytes=200000)
if b:
    print('cninfo issuer',b[:1200].decode('utf-8',errors='replace'))
b=request('sse_announcement_page.html','https://www.sse.com.cn/disclosure/listedinfo/announcement/',max_bytes=1_000_000)
if b:
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(b,'html.parser')
    print('sse script sources', [x.get('src') for x in soup.find_all('script') if x.get('src')][-18:])
b=request('correction_audit_20190430.pdf','https://static.cninfo.com.cn/finalpage/2019-04-30/1206168283.PDF')
print('new audit PDF',len(b) if b else None)
