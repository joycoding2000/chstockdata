"""Persist source page text with deterministic one-based PDF locators."""
import json
import re
from extract_reports import report_text_blocks
from acquire import ROOT, save

out = ROOT / "extracted"
out.mkdir(exist_ok=True)
for path in sorted((ROOT / "sources").glob("*.raw")):
    if not path.read_bytes().startswith(b"%PDF-"):
        continue
    dest = out / (path.stem + ".json")
    if not dest.exists():
        kind, blocks = report_text_blocks(path.read_bytes())
        save(dest, {"source_file": path.name, "locator_kind": kind, "blocks": blocks})
    blocks = json.loads(dest.read_text(encoding="utf-8"))["blocks"]
    print(path.name, len(blocks), flush=True)
    if "dividend" in path.name or "method" in path.name:
        print("\n".join(blocks)[:7000])
    else:
        for i, block in enumerate(blocks):
            compact = re.sub(r"\s+", "", block)
            hits = [compact[max(0,compact.find(x)-30):compact.find(x)+450] for x in ("基金主代码", "利润分配情况", "本报告期内本基金未", "基金拆分", "8.3期末", "7.4.13.4", "上证港股通指数") if x in compact]
            if hits:
                print(i + 1, " | ".join(hits)[:1200])
