import json;from PIL import Image;from fetch_named import OUT,read,save
plan=[]
for n in [9,10,11,12]:
 src=OUT/'images'/f'1216741269-p{n}.png'
 image=Image.open(src)
 for y in range(0,image.height,420):
  p=OUT/'crop-probe'/f'p{n}-y{y}.png';p.parent.mkdir(exist_ok=True)
  image.crop((0,y,image.width,min(image.height,y+540))).resize((image.width*2,min(540,image.height-y)*2)).save(p)
  target=OUT/'crop-ocr'/f'p{n}-y{y}.json';target.parent.mkdir(exist_ok=True)
  plan.append({'id':'1216741269','physical_page':n,'image':str(p),'output':str(target),'source_sha256':next(d['sha256']for d in read(OUT/'documents.json')if d['id']=='1216741269')})
save('crop_probe_plan.json',plan)
print(len(plan))