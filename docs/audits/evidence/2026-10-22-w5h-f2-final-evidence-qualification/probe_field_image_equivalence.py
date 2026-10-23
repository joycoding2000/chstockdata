"""Final bounded image equivalence probe against prior original field renderings.

This is NOT an amount extractor and NEVER inserts a reference into OCR output.
It asks whether a complete source field image distinguishes a prior literal
from every single-digit/sign/scale mutation. All unsuccessful probes remain.
Thresholds are fixed here before execution, not tuned to achieve qualification.
"""
import re
from decimal import Decimal
from common import HERE, OLD, F2, read, save


def source_mask(image):
    import numpy as np
    a=np.array(image.convert('L'))<160
    a[a.mean(axis=1)>.60,:]=False
    # Reject grid strokes at the border; never erase inner character strokes.
    for x in list(range(min(5,a.shape[1])))+list(range(max(0,a.shape[1]-5),a.shape[1])):
        if a[:,x].mean()>.60:a[:,x]=False
    ys,xs=np.where(a)
    if len(xs)<30:return None
    return a[ys.min():ys.max()+1,xs.min():xs.max()+1]


def literal(value):
    return format(Decimal(value),',.2f')


def mutations(value):
    s=literal(value);out=set()
    for i,ch in enumerate(s):
        if ch.isdigit():
            for digit in '0123456789':
                if ch!=digit:out.add(s[:i]+digit+s[i+1:])
    for v in (-Decimal(value),Decimal(value)*10000,Decimal(value)/10000):out.add(literal(v))
    out.discard(s)
    return sorted(out)


def score(mask,text,fonts):
    import numpy as np
    from PIL import Image,ImageDraw
    best=(1.0,None)
    for name,font in fonts:
        canvas=Image.new('L',(2400,180),255)
        ImageDraw.Draw(canvas).text((10,10),text,font=font,fill=0)
        a=np.array(canvas)<160;ys,xs=np.where(a)
        if not len(xs):continue
        tile=Image.fromarray((a[ys.min():ys.max()+1,xs.min():xs.max()+1]*255).astype('uint8'))
        tile=tile.resize((mask.shape[1],mask.shape[0]))
        target=np.array(tile,dtype=float)/255
        error=min(float(np.mean((mask-np.roll(target,(dy,dx),(0,1)))**2))
                  for dy,dx in ((0,0),(0,-1),(0,1),(-1,0),(1,0)))
        if error<best[0]:best=(error,name)
    return best


def main():
    from pathlib import Path
    from PIL import Image,ImageFont
    fonts=[(f,ImageFont.truetype('C:/Windows/Fonts/'+f,100)) for f in
           ('times.ttf','timesbd.ttf','arial.ttf','arialbd.ttf','arialn.ttf','arialnb.ttf','calibri.ttf','calibrib.ttf','simsun.ttc')
           if (Path('C:/Windows/Fonts')/f).exists()]
    refs=[]
    for name in ['certified_facts.json','certified_new_facts.json']:refs+=read(F2/name)['facts']
    results=[]
    for site in read(HERE/'scan_field_qualification.json')['rows']:
        image=Image.open(OLD/'images'/f"{site['document_id']}-p{site['evidence_page']}.png")
        mask=source_mask(image.crop(tuple(site['bbox_in_saved_page_image'])))
        matches=[r for r in refs if r['code']==site['affected_security'] and r['period']==site['affected_period'] and
                 r['field']==site['affected_field'] and r['scope']=='consolidated' and r.get('duration')!='INSTANT_START' and
                 r['announcement_date']<=site['disclosure_date']]
        values=sorted({r['value_CNY'] for r in matches})
        for value in values:
            actual,font=score(mask,literal(value),fonts) if mask is not None else (1,None)
            controls=[{'TEST_ONLY_literal':s,'error':score(mask,s,fonts)[0]} for s in mutations(value)] if mask is not None else []
            closest=min(controls,key=lambda x:x['error']) if controls else None
            margin=closest['error']-actual if closest else -1
            # Conservative fixed thresholds; failure does not trigger tuning.
            passed=actual<.12 and margin>.006
            row={k:site[k] for k in ['document_id','affected_security','affected_period','affected_field','accounting_scope','evidence_page','column_index','bbox_in_saved_page_image']}
            row.update(reference_value_CNY=value,reference_literal=literal(value),template_font=font,
                       image_error=actual,closest_counterfactual=closest,margin=margin,
                       all_negative_controls=controls,negative_controls_count=len(controls),passed=passed,
                       original_reference_ids=sorted({r['id'] for r in matches if r['value_CNY']==value}),
                       qualification='IMAGE_EQUIVALENCE_ONLY_IF_HEADER_UNIT_SUBJECT_AND_POSITION_VERIFIED' if passed else 'UNRESOLVED_IMAGE_EQUIVALENCE')
            results.append(row)
        print(site['document_id'],site['evidence_page'],site['affected_field'],[(r['image_error'],r['margin'],r['passed']) for r in results[-len(values):]],flush=True)
    save('field_image_equivalence.json',{'fixed_thresholds':{'maximum_image_error':.12,'minimum_counterfactual_margin':.006},
         'rows':results,'all_reference_values_from_existing_prior_qualified_originals':True,
         'no_new_financial_value_extraction':True,'thresholds_not_tuned_after_execution':True,
         'stop_after_this_probe':True})


if __name__=='__main__':main()
