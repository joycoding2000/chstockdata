"""Finite EPS control and notice-content evidence; monetary facts stay separate."""
import hashlib
import json
import time
from pathlib import Path
from acquire import OUT, ROOT, read, save
from parser_f2 import compact
from offline_extras import eps_columns


def main():
    from pypdf import PdfReader
    docs = read(OUT/'dataset_legacy.json')['documents']+read(OUT/'new_documents.json')
    chosen = read(OUT/'auxiliary_manifest.json')
    eps, notices = [], []
    for d in docs:
        if d['id'] in chosen['eps_document_ids']:
            t = time.perf_counter()
            eps.append({'id':d['id'],'facts':eps_columns(ROOT,d),'machine_seconds':time.perf_counter()-t})
        if d['kind'] != 'notice':
            continue
        t = time.perf_counter()
        pages = [{'physical_page':i+1,'raw_text':p.extract_text() or ''}
                 for i,p in enumerate(PdfReader(ROOT/d['path']).pages)]
        text = compact(''.join(p['raw_text'] for p in pages))
        if not text:
            status = 'UNKNOWN_NO_TEXT_LAYER_IMAGE_COMPANION'
        elif '监管工作函' in text and '全文公告' in text and '收到' in text:
            status = 'REGULATORY_REQUEST_NO_ISSUER_LEVEL_REPLACEMENT'
        elif '董事' in text and ('简历' in text or '任职资格' in text):
            status = 'GOVERNANCE_NO_NUMERIC_REPLACEMENT'
        elif '处罚及整改' in text and ('其他' in text or '其余' in text) and '不变' in text:
            status = 'LIMITED_NARRATIVE_UPDATE_NO_NUMERIC_REPLACEMENT'
        elif '更正' in text and '前期' in text and '会计差错' in text:
            status = 'MATERIAL_CORRECTION_NO_TARGET_LEVELS_AUTOMATICALLY_DERIVED'
        elif '单位均为元' in text and '调整前' in text and '调整后' in text:
            status = 'EXPLICIT_MONETARY_ADJUSTMENT_COLUMNS'
        elif '会计政策变更' in text and '当期及可比期间' in text and '不产生影响' in text:
            status = 'PRESENTATION_POLICY_NO_NP_EQ_IMPACT_STATED_OCF_NOT_CERTIFIED_BY_TEXT'
        else:
            status = 'FINANCIAL_OR_OTHER_SCOPE_UNRESOLVED_NO_REPLACEMENT'
        notices.append({'id':d['id'],'code':d['code'],'date':d['date'],
            'source_sha256':d['sha256'],'status':status,'pages':pages,
            'machine_seconds':time.perf_counter()-t,
            'no_replacement_is_not_general_semantic_clearance':True})
    save('auxiliary_evidence.json',{'eps':eps,'notices':notices,
        'code_sha256':hashlib.sha256((OUT/'offline_extras.py').read_bytes()).hexdigest()})
    print({'eps_facts':sum(len(d['facts']) for d in eps),'notices':len(notices)})


if __name__ == '__main__':
    main()
