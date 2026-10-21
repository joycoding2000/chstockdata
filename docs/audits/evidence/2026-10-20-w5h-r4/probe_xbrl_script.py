from audit_common import request
b=request('sse_search_xbrl.js','https://english.sse.com.cn/xhtml/js/search/search_xbrl.js',max_bytes=1_000_000)
if b:
    print(b.decode('utf-8',errors='replace')[:26000])
