"""Finite, row/column-constrained OCR crops; no financial values in the plan."""
from common import HERE, OLD, read, save, sha


def main():
    from PIL import Image, ImageOps
    candidates = read(HERE / "scan_geometry_candidates.json")
    # Reviewed geometric overrides resolve damaged labels or skewed rules.
    # Coordinates localize source pixels only and never supply numeric values.
    overrides = {
        ("1216741269",208): (1375,[548,752,954,1153,1353]),
        ("1216741269",209): (1195,[685,850,1015,1180,1345]),
        ("1216741269",210): (650,[665,835,1005,1175,1345]),
        ("1216869640",13): (1260,[800,1055,1315]),
        ("1216869640",16): (718,[800,1055,1315]),
        ("1216869640",201): (1472,[780,1045,1310]),
        ("1216869640",203): (1311,[790,1056,1320]),
        ("1216869640",206): (760,[790,1056,1320]),
        ("1217078313",12): (716,[652,820,990,1159,1328]),
        ("1217949874",12): (716,[652,820,990,1159,1328]),
        ("1217078313",210): (696,[840,1100,1350]),
    }
    plan=[]
    for p in candidates:
        key=(p["id"],p["physical_page"])
        if key in overrides:
            y,edges=overrides[key]
        else:
            row=p["row_candidates"][0]
            y=sum(row["y"])/2
            rules=p["vertical_rules"]
            if p["physical_page"]<20 and p["id"]!="1216869640":
                edges=rules[1:]
                if len(edges)<5:
                    step=edges[-1]-edges[-2]
                    while len(edges)<5:
                        edges.append(edges[-1]+step)
            elif p["id"]=="1216869640":
                edges=[824,1085,1345]
            else:
                edges=rules[-3:]
        p.update(selected_row_y=y, selected_column_edges=edges)
        image=Image.open(OLD/'images'/f"{p['id']}-p{p['physical_page']}.png").convert('RGB')
        w,h=image.size
        parts=[("header",(int(w*.08),int(h*.08),int(w*.94),int(h*.195))),
               ("label",(int(w*.08),int(y-19),int(edges[0]-3),int(y+19)))]
        for i,(x0,x1) in enumerate(zip(edges,edges[1:])):
            parts.append((f"col{i}",(int(x0+3),int(y-16),int(x1-3),int(y+16))))
        for kind,box in parts:
            crop=image.crop(box)
            # Remove colored seals, then enlarge the actual bounded cell.
            crop=ImageOps.grayscale(crop.getchannel('R'))
            crop=ImageOps.autocontrast(crop).resize((crop.width*3,crop.height*3))
            target=HERE/'cells'/f"{p['id']}-p{p['physical_page']}-{kind}.png"
            target.parent.mkdir(exist_ok=True)
            crop.save(target)
            for lang in (['zh','en'] if kind.startswith('col') else ['zh']):
                out=HERE/'cell-ocr'/f"{target.stem}-{lang}.json"
                out.parent.mkdir(exist_ok=True)
                plan.append({'id':p['id'],'physical_page':p['physical_page'],'field':p['field'],
                             'kind':kind,'bbox_in_saved_page_image':box,'language':lang,
                             'image':str(target),'output':str(out),'source_sha256':sha(OLD/'originals'/f"{p['id']}.pdf")})
    save('reviewed_scan_geometry.json',candidates)
    save('cell_ocr_plan.json',plan)
    for lang in ['zh','en']:
        save(f'cell_ocr_plan_{lang}.json',[p for p in plan if p['language']==lang])
    print({'bounded_crops':len({p['image'] for p in plan}),'engine_calls':len(plan),'unconditional_full_page_reruns':0})


if __name__=='__main__':
    main()
