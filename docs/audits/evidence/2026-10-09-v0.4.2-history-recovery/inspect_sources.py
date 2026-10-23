"""Extract primary disclosure pages and retain bounded adaptive requests."""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

from probe import OUT, save, sha


if sys.argv[1] == "extract":
    from pypdf import PdfReader
    pages = []
    for name in ("vanke-issuer-history", "vanke-fund-disclosure", "sse-suspend", "sse-resume", "issuer-suspend-mirror", "issuer-resume-mirror"):
        path = OUT / (name + ".pdf")
        if not path.exists():
            continue
        doc = PdfReader(path)
        for i, page in enumerate(doc.pages):
                text = page.extract_text() or ""
                compact = "".join(text.split())
                relevant = (name.startswith("sse-") or name.startswith("issuer-") or
                            (name == "vanke-issuer-history" and i in (12, 112)) or
                            (name == "vanke-fund-disclosure" and "000002" in compact and "2016年7月4日" in compact))
                if relevant:
                    pages.append({"file": path.name, "sha256": sha(path.read_bytes()), "page_index": i, "text": text})
                    print(name, "page", i, text[:160].replace("\n", " "))
    save("disclosure-pages.json", pages)
    for name in ("tdx-official-vipdata", "tdx-official-realtime"):
        source = OUT / (name + ".txt")
        class TextParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
            def handle_data(self, value):
                if value.strip():
                    self.text.append(value.strip())
        parser = TextParser()
        parser.feed(source.read_text(encoding="utf-8"))
        (OUT / (name + "-text.txt")).write_text("\n".join(parser.text), encoding="utf-8")
elif sys.argv[1] == "adaptive":
    import requests
    session = requests.Session()
    session.trust_env = False
    params = {"isPagination": "true", "SECURITY_CODE": "688432", "START_DATE": "2026-09-11", "END_DATE": "2026-09-14", "pageHelp.pageSize": "100", "pageHelp.pageNo": "1"}
    url = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
    response = session.get(url, params=params, headers={"Referer": "https://www.sse.com.cn/"}, timeout=20)
    payload = response.json()
    save("sse-resume-adaptive.json", {"url": url, "params": params, "http_status": response.status_code, "sha256": sha(response.content), "response": payload})
    print("SSE accepted filters result", len(payload.get("result", [])))
    # Issuer-authored PDFs hosted on a distributor are labelled as mirrors.
    # They do not certify the distributor's historical status endpoint.
    mirrors = [("issuer-resume-mirror", "https://pdf.dfcfw.com/pdf/H2_AN202609111829278590_1.pdf")]
    for name, url in mirrors:
        response = session.get(url, timeout=20)
        (OUT / (name + (".pdf" if response.content.startswith(b"%PDF") else ".txt"))).write_bytes(response.content)
        save(name + "-request.json", {"url": url, "http_status": response.status_code, "sha256": sha(response.content), "content_type": response.headers.get("Content-Type"), "issuer_authored_distributor_mirror": True})
        print(name, response.status_code, len(response.content))
