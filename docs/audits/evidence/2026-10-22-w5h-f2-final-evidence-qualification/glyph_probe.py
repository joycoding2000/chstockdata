"""Bounded offline digit-shape probe, independent of any financial amounts.

System font raster templates contain digits/punctuation only. This probe cannot
read reference values or choose a value because it resembles expected money.
Low margins, merged glyphs and malformed groups are retained, not repaired.
"""
from common import HERE, OLD, read, save


def normalize(mask):
    import numpy as np
    from PIL import Image
    ys,xs=np.where(mask)
    if not len(xs):return None
    a=mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
    h,w=a.shape
    scale=min(28/h,24/w)
    resized=Image.fromarray((a*255).astype('uint8')).resize((max(1,round(w*scale)),max(1,round(h*scale))))
    canvas=Image.new('L',(28,32));canvas.paste(resized,((28-resized.width)//2,(32-resized.height)//2))
    return np.array(canvas,dtype=float)/255


def templates():
    import numpy as np
    from pathlib import Path
    from PIL import Image, ImageDraw, ImageFont
    fonts=[f for f in ('times.ttf','timesbd.ttf','arial.ttf','arialbd.ttf','arialn.ttf','arialnb.ttf',
                       'calibri.ttf','calibrib.ttf','simsun.ttc') if (Path('C:/Windows/Fonts')/f).exists()]
    out=[]
    for f in fonts:
        font=ImageFont.truetype('C:/Windows/Fonts/'+f,100)
        for digit in '0123456789':
            im=Image.new('L',(180,160),255);ImageDraw.Draw(im).text((20,10),digit,font=font,fill=0)
            out.append((digit,f,normalize(np.array(im)<160)))
    return out,fonts


def decode(image,bank):
    import numpy as np
    a=np.array(image.convert('L'))
    mask=a<160
    # Reject grid strokes, not arbitrary characters.
    mask[mask.mean(axis=1)>.65,:]=False
    for x in list(range(min(3,mask.shape[1])))+list(range(max(0,mask.shape[1]-3),mask.shape[1])):
        if mask[:,x].mean()>.75:mask[:,x]=False
    cols=np.flatnonzero(mask.any(axis=0));segments=[]
    for x in cols:
        if segments and x==segments[-1][-1]+1:segments[-1].append(int(x))
        else:segments.append([int(x)])
    boxes=[]
    for s in segments:
        ys=np.flatnonzero(mask[:,s[0]:s[-1]+1].any(axis=1))
        if len(ys):boxes.append((s[0],int(ys.min()),s[-1]+1,int(ys.max())+1))
    heights=[y1-y0 for x0,y0,x1,y1 in boxes if y1-y0>=8]
    if not heights:return '',[],False
    median=float(np.median(heights));baseline=float(np.median([b[3]for b in boxes if b[3]-b[1]>=median*.7]))
    chars=[];details=[];certain=True
    for box in boxes:
        x0,y0,x1,y1=box;h=y1-y0;w=x1-x0
        if h<median*.42:
            char='-' if w>h*2.3 and y0<baseline-median*.3 else ',' if h>median*.20 else '.'
            chars.append(char);details.append({'bbox':box,'character':char,'punctuation_geometry':True});continue
        norm=normalize(mask[y0:y1,x0:x1]);scores={}
        for digit,font,temp in bank:
            # Small shifts tolerate raster scan alignment without inventing glyphs.
            distance=min(float(np.mean((norm-np.roll(temp,(dy,dx),(0,1)))**2))
                         for dy,dx in ((0,0),(0,-1),(0,1),(-1,0),(1,0)))
            if digit not in scores or distance<scores[digit][0]:scores[digit]=(distance,font)
        ranking=sorted(scores.items(),key=lambda x:x[1][0]);digit,(distance,font)=ranking[0]
        margin=ranking[1][1][0]-distance
        good=distance<.18 and margin>.008 and h>median*.65
        certain&=good;chars.append(digit)
        details.append({'bbox':box,'character':digit,'distance':round(distance,5),
                        'margin':round(margin,5),'font':font,'certain':good})
    return ''.join(chars),details,certain


def main():
    from PIL import Image
    bank,fonts=templates();results=[]
    for p in read(HERE/'repaired_scan_geometry.json'):
        image=Image.open(OLD/'images'/f"{p['id']}-p{p['physical_page']}.png")
        y=p['repaired_row_y']
        for i,(x0,x1) in enumerate(zip(p['repaired_edges'],p['repaired_edges'][1:])):
            box=(int(x0+1),int(y-14),int(x1-1),int(y+18))
            text,glyphs,certain=decode(image.crop(box),bank)
            results.append({'id':p['id'],'physical_page':p['physical_page'],'field':p['field'],
                            'column_index':i,'bbox':box,'text':text,'certain':certain,'glyphs':glyphs})
        print(p['id'],p['physical_page'],[(r['text'],r['certain'])for r in results[-(len(p['repaired_edges'])-1):]],flush=True)
    save('glyph_probe.json',{'rows':results,'font_templates':fonts,'financial_values_read':False,
         'qualification':'PROBE_ONLY_REQUIRES_INDEPENDENT_COLUMN_HEADER_UNIT_AND_VALUE_VALIDATION'})


if __name__=='__main__':main()
