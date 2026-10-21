from audit_common import request

for name,url in [
    ('official_original_2017.pdf','https://static.cninfo.com.cn/finalpage/2018-04-26/1204793690.PDF'),
    ('official_annual_2018.pdf','https://static.cninfo.com.cn/finalpage/2019-04-30/1206168292.PDF'),
    ('official_regulatory_letter_20190501.pdf','https://static.cninfo.com.cn/finalpage/2019-05-01/1206201352.PDF'),
    ('sse_xbrl_page.html','https://english.sse.com.cn/markets/dataservice/xbrl/'),
]:
    b=request(name,url,max_bytes=10_000_000)
    print(name,len(b) if b else None,flush=True)
    if b and name.endswith('.html'):
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(b,'html.parser')
        print('scripts',[x.get('src') for x in soup.find_all('script') if x.get('src')])
