"""Bounded original statement and reply context diagnostic, not a scorer."""
import re
from common import ROOT, OLD, F2, read, save, compact


def main():
    import pdfplumber
    docs = read(F2 / "dataset_legacy.json")["documents"] + read(F2 / "new_documents.json")
    plans = {"1216561621": [77, 78, 79, 80], "1216273938": [132, 135, 138, 139, 140],
             "1216696970": [6, 7, 8], "1217710575": [52, 55, 56, 58, 59]}
    result = []
    for d in docs:
        if d["id"] not in plans:
            continue
        with pdfplumber.open(ROOT / d["path"]) as pdf:
            for n in plans[d["id"]]:
                p = pdf.pages[n-1]
                tabs = p.find_tables()
                result.append({"id": d["id"], "page": n, "width": p.width, "height": p.height,
                               "text": p.extract_text(),
                               "tables": [{"bbox": t.bbox, "rows": t.extract()} for t in tabs]})
                print(d["id"], n, "tables", len(tabs), "rows", [len(t.rows) for t in tabs], flush=True)
    save("original_statement_tables.json", result)
    contexts = []
    for d in read(OLD / "documents.json"):
        if d["id"] not in read(__import__("common").HERE / "bounded_contract.json")["replies"]:
            continue
        pages = read(OLD / "text" / (d["id"] + ".json"))["pages"]
        for p in pages:
            t = compact(p["text"])
            if "现金流量表简要" in t or "1,677,198.08万元" in t or "财务数据" in t[:500]:
                contexts.append({"id": d["id"], "page": p["physical_page"], "text": p["text"]})
    save("reply_contexts.json", contexts)


if __name__ == "__main__":
    main()
