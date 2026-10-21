import re,json
from acquire import request
b=request('index/cninfo-disclosure-page.html','https://www.cninfo.com.cn/new/disclosure/stock?stockCode=600518&orgId=gssh0600518',maximum=5000000)
t=b.decode('utf-8',errors='replace')
print(json.dumps(re.findall(r'<script[^>]+src=[\"\']([^\"\']+)',t)))
