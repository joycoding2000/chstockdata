"""Recover numeric columns with ruled-line removal and retained row coordinates."""
from common import HERE, OLD, read, save, sha


def main():
    import numpy as np
    from PIL import Image, ImageOps
    plan=[]
    for p in read(HERE/'repaired_scan_geometry.json'):
        sid,n=p['id'],p['physical_page']
        image=Image.open(OLD/'images'/f'{sid}-p{n}.png').convert('L')
        w,h=image.size
        for i,(x0,x1) in enumerate(zip(p['repaired_edges'],p['repaired_edges'][1:])):
            box=(int(x0+1),int(h*.19),int(x1-1),int(h*.86))
            a=np.array(image.crop(box))
            # Grid strokes cross most of a column; glyph strokes do not.
            ruled=np.flatnonzero((a<170).mean(axis=1)>.60)
            for y in ruled:
                a[max(0,y-1):min(len(a),y+2),:]=255
            crop=Image.fromarray(a)
            crop=ImageOps.autocontrast(crop).resize((crop.width*2,crop.height*2))
            crop=ImageOps.expand(crop,border=40,fill=255)
            target=HERE/'columns'/f'{sid}-p{n}-col{i}.png'
            target.parent.mkdir(exist_ok=True);crop.save(target)
            for lang in ['zh','en']:
                out=HERE/'column-ocr'/f'{target.stem}-{lang}.json'
                out.parent.mkdir(exist_ok=True)
                plan.append({'id':sid,'physical_page':n,'field':p['field'],'column_index':i,
                             'bbox_in_saved_page_image':box,'scale':2,'padding':40,
                             'target_y_in_original_image':p['repaired_row_y'],
                             'removed_rule_y_offsets':list(map(int,ruled)), 'language':lang,
                             'image':str(target),'output':str(out),'source_sha256':sha(OLD/'originals'/f'{sid}.pdf')})
    save('column_ocr_plan.json',plan)
    for lang in ['zh','en']:save(f'column_ocr_plan_{lang}.json',[p for p in plan if p['language']==lang])
    print({'columns':len(plan)//2,'calls':len(plan)})


if __name__=='__main__':main()
