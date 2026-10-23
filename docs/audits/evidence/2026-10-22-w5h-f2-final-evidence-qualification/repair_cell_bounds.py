"""One bounded repair for demonstrated clipped/marginless OCR cells."""
from common import HERE, OLD, read, save, sha


def main():
    from PIL import Image, ImageOps
    geometry=read(HERE/'reviewed_scan_geometry.json')
    plan=[]
    for p in geometry:
        sid,n=p['id'],p['physical_page']
        edges=p['selected_column_edges']
        y=p['selected_row_y']
        if n==11 and sid!='1216869640': y=1126
        if sid=='1216741269' and n==209: y=1210
        if sid=='1217949874' and n==209: y=1031
        if sid=='1216869640' and n==201: edges=[816,1077,1337]
        if sid=='1216741269' and n==209: edges=[726,890,1055,1218,1383]
        if sid=='1216741269' and n==210: edges=[644,840,1037,1231,1418]
        p.update(repaired_row_y=y,repaired_edges=edges)
        image=Image.open(OLD/'images'/f'{sid}-p{n}.png').convert('L')
        for i,(x0,x1) in enumerate(zip(edges,edges[1:])):
            # Full character bounds plus whitespace are essential for single-line OCR.
            box=(int(x0+1),int(y-14),int(x1-1),int(y+18))
            crop=image.crop(box)
            crop=ImageOps.autocontrast(crop).resize((crop.width*2,crop.height*2))
            crop=ImageOps.expand(crop,border=30,fill=255)
            target=HERE/'cells-v2'/f'{sid}-p{n}-col{i}.png'
            target.parent.mkdir(exist_ok=True);crop.save(target)
            for lang in ['zh','en']:
                out=HERE/'cell-ocr-v2'/f'{target.stem}-{lang}.json'
                out.parent.mkdir(exist_ok=True)
                plan.append({'id':sid,'physical_page':n,'field':p['field'],'kind':f'col{i}',
                             'bbox_in_saved_page_image':box,'language':lang,
                             'image':str(target),'output':str(out),'source_sha256':sha(OLD/'originals'/f'{sid}.pdf')})
    save('repaired_scan_geometry.json',geometry)
    save('cell_ocr_v2_plan.json',plan)
    for lang in ['zh','en']: save(f'cell_ocr_v2_plan_{lang}.json',[p for p in plan if p['language']==lang])
    print({'cell_crops':len(plan)//2,'engine_calls':len(plan),'reason':'Proven clipping / numeric cells lacking white margins; separate preserved second attempt'})


if __name__=='__main__':main()
