from pathlib import Path
from PIL import Image, ImageDraw

OUT=Path(__file__).resolve().parent
paths=sorted((OUT/'renders').glob('correction-scan-*.jpg'))
cols=3;tw=440;th=650
sheet=Image.new('RGB',(cols*tw,((len(paths)+cols-1)//cols)*th),'white')
draw=ImageDraw.Draw(sheet)
for i,p in enumerate(paths):
    im=Image.open(p);im.thumbnail((tw-12,th-28))
    x=(i%cols)*tw;y=(i//cols)*th
    draw.text((x+6,y+3),p.stem,fill='black')
    sheet.paste(im,(x+6,y+23))
sheet.save(OUT/'renders/correction-contact.png')
