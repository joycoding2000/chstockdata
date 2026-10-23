"""Whole-page pixel identity and positive bounded non-target reply scope."""
import hashlib
import re
from common import HERE, ROOT, OLD, read, save, sha, compact
from qualification_rules import page_equivalent


def main():
    import pypdfium2 as pdfium
    from PIL import Image
    docs={d['id']:d for d in read(OLD/'documents.json')}
    identities=[]
    for n in [8,9,10,11,12,13,14,15,16,202,203,204,205,206]:
        pixels=[]
        for sid in ['1217078313','1217949874']:
            with pdfium.PdfDocument(ROOT/docs[sid]['path']) as pdf:
                page=pdf[n-1];bitmap=page.render(scale=1)
                image=bitmap.to_pil().convert('RGB')
                pixels.append({'document_id':sid,'physical_page':n,'size':list(image.size),
                               'pixel_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
                               'source_sha256':docs[sid]['sha256'],'render_scale':1})
        identities.append({'pages':pixels,'whole_page_pixels_identical':page_equivalent(*pixels),
                           'does_not_cover_Q1_H1':True})
    sid='1218110511';d=docs[sid]
    assert sha(ROOT/d['path'])==d['sha256']
    pages=[]
    for n in range(1,23):
        o=read(OLD/'ocr'/f'{sid}-p{n}.json')
        path=OLD/'images'/f'{sid}-p{n}.png'
        assert o['source_sha256']==d['sha256'] and o['image_sha256']==sha(path)
        t=compact(o['text'])
        hits=re.findall(r'归属于.{0,6}(?:净利润|权益合计)|经营活动.{0,8}现金流量净额|前期差错|追溯调整|更正财务',t)
        pages.append({'physical_page':n,'image_sha256':o['image_sha256'],'text':o['text'],
                      'target_or_revision_hits':hits,'character_count':len(t),
                      'image':path.relative_to(ROOT).as_posix()})
    alltext=''.join(compact(p['text'])for p in pages)
    assert all(not p['target_or_revision_hits'] for p in pages)
    assert '问题1' in compact(pages[2]['text']) and not re.search(r'问题[2-9]',alltext)
    assert all(s in alltext for s in ['债务','预售资金','教育','产业政策','核查意见'])
    assert min(p['character_count']for p in pages[3:21])>500
    assert '仅供中南建设公司本次' in compact(pages[-1]['text'])
    save('image_identity_and_reply_scope.json',{'duplicate_page_denominator':14,'whole_page_tests':identities,
         'identical_whole_pages':sum(r['whole_page_pixels_identical']for r in identities),
         'reply':{'document_id':sid,'source_sha256':d['sha256'],'source_path':d['path'],'disclosure_date':d['date'],
                  'page_denominator':22,'pages':pages,'qualification_status':'VERIFIED_NO_TARGET_EFFECT',
                  'positive_scope':'One question: debt restructuring, project presale funds, education investments and industrial policy; full body and final four audit conclusions checked',
                  'scope_review':'Saved OCR reused plus agent image overview/cover/question/conclusion/end-page review; not universal OCR semantic automation',
                  'new_ocr_calls':0,'reference_reply':'1217170564 is contextual support only, not assumed duplicate',
                  'does_not_certify_all_debt_or_project_amounts':True}})
    print({'identical_page_pairs':sum(r['whole_page_pixels_identical']for r in identities),'auditor_reply':'VERIFIED_NO_TARGET_EFFECT'})


if __name__=='__main__':main()
