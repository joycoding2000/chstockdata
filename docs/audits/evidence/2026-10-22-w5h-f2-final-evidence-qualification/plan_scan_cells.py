"""Derive candidate row positions from saved OCR and column rules from pixels.

This generates evidence/crops, never amounts or financial acceptance decisions.
"""
import re
from difflib import SequenceMatcher
from common import HERE, OLD, read, save, compact

PAGES = {"1216741269": [(10,"EQ"),(11,"NP"),(12,"OCF"),(208,"EQ"),(209,"NP"),(210,"OCF")],
         "1216869640": [(10,"EQ"),(13,"NP"),(16,"OCF"),(201,"EQ"),(203,"NP"),(206,"OCF")],
         "1217078313": [(10,"EQ"),(11,"NP"),(12,"OCF"),(208,"EQ"),(209,"NP"),(210,"OCF")],
         "1217949874": [(10,"EQ"),(11,"NP"),(12,"OCF"),(208,"EQ"),(209,"NP"),(210,"OCF")]}
LABELS = {"EQ": ["归属于母公司股东权益合计", "归属于母公司所有者权益合计"],
          "NP": ["其中归属于母公司股东的净利润净亏损以号填列", "归属于母公司所有者的净利润"],
          "OCF": ["经营活动产生的现金流量净额"]}


def groups(values):
    out = []
    for v in values:
        if out and v <= out[-1][-1] + 2:
            out[-1].append(int(v))
        else:
            out.append([int(v)])
    return [sum(g)/len(g) for g in out]


def main():
    from PIL import Image
    import numpy as np
    records = []
    for sid, targets in PAGES.items():
        for n, field in targets:
            image = Image.open(OLD / "images" / f"{sid}-p{n}.png").convert("RGB")
            ocr = read(OLD / "ocr" / f"{sid}-p{n}.json")
            w,h = image.size
            ink = np.array(image.convert("L")) < 160
            vertical = ink[int(h*.19):int(h*.75)].mean(axis=0)
            xs = groups(np.flatnonzero(vertical > .40))
            candidates=[]
            for line in ocr["lines"]:
                words=line["words"]
                if not words or min(v["x"] for v in words)>w*.48:
                    continue
                t=re.sub(r"[^\u4e00-\u9fff]", "", compact(line["text"]))
                score=max(SequenceMatcher(None,t,label).ratio() for label in LABELS[field])
                y0=min(v["y"] for v in words);y1=max(v["y"]+v["height"] for v in words)
                if h*.2<y0<h*.85:
                    candidates.append({"text":line["text"],"score":round(score,4),"y":[y0,y1]})
            candidates.sort(key=lambda x:x["score"],reverse=True)
            record={"id":sid,"physical_page":n,"field":field,"width":w,"height":h,
                    "vertical_rules":xs,"row_candidates":candidates[:4]}
            records.append(record)
            print(sid,n,field,"rules",[round(x) for x in xs],"rows",candidates[:2],flush=True)
    save("scan_geometry_candidates.json",records)


if __name__ == "__main__":
    main()
