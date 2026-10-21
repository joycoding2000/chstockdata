"""Frozen first-pass detector on saved, known cases. No ID/issuer rule exceptions."""
import html
import itertools
import json
import re
import time
from decimal import Decimal
from access import OUT, R5, RULES, read, save, sha, now

LABELS={
 'NP':['归属于上市公司股东的净利润','归属于母公司股东的净利润','归属于母公司所有者的净利润'],
 'OCF':['经营活动产生的现金流量净额'],
 'EQ':['归属于上市公司股东的净资产','归属于母公司股东的净资产','归属于上市公司股东的所有者权益','归属于母公司股东的所有者权益','归属于母公司所有者权益合计'],
}

def clean(t):
    return re.sub(r'\s+','',html.unescape(re.sub('<[^>]*>','',t)))

def period(title):
    m=re.search(r'(20\d{2})年?(年度|第一季度|一季度|半年度|第三季度|三季度)报告',clean(title))
    if not m:
        return None
    return m[1]+'-'+{'年度':'12-31','第一季度':'03-31','一季度':'03-31','半年度':'06-30','第三季度':'09-30','三季度':'09-30'}[m[2]]

def catalogs():
    rows={}
    for code in RULES['scope']['securities']:
        for kind in ['periodic','correction','supplement']:
            obj=json.loads((R5/(code+'_'+kind+'_index.json')).read_text(encoding='utf-8'))
            for a in obj.get('announcements') or []:
                key=a['announcementId']
                prior=rows.get(key,{})
                rows[key]={'code':code,'id':key,'title':clean(a['announcementTitle']),'period':period(a['announcementTitle']),'date':a['adjunctUrl'].split('/')[1],'url':'https://static.cninfo.com.cn/'+a['adjunctUrl'],'queried_kinds':sorted(set(prior.get('queried_kinds',[])+[kind]))}
    return list(rows.values())

def extract_summary(pages,p):
    selected=next((r for r in pages[:30] if '主要会计数据和财务指标' in clean(r['text'])),None)
    if not selected:
        return {'status':'NO_SUMMARY_MATCH_UNKNOWN','fields':{},'summary_page':None}
    t=clean(selected['text'])
    fields={}
    for field,labels in LABELS.items():
        label=next((l for l in labels if l in t),None)
        if not label:
            fields[field]={'status':'LABEL_MISSING_UNKNOWN'}
            continue
        pos=t.index(label)+len(label)
        tail=t[pos:pos+400]
        match=re.search(r'\(?[-−－]?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\)?',tail)
        if not match:
            fields[field]={'status':'AMOUNT_MISSING_UNKNOWN'}
            continue
        unit_context=tail[:match.start()]
        if '万元' in unit_context:
            multiplier=10000
        elif '（元）' in unit_context or '(元)' in unit_context:
            multiplier=1
        elif re.search(r'单位[：:]万元',t):
            multiplier=10000
        elif re.search(r'单位[：:]元',t):
            multiplier=1
        else:
            fields[field]={'status':'UNIT_UNKNOWN','label':label}
            continue
        numbers=re.findall(r'\(?[-−－]?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\)?',tail)[:3]
        values=[]
        for v in numbers:
            v=v.replace(',','').replace('−','-').replace('－','-')
            if v.startswith('(') and v.endswith(')'):
                v='-'+v[1:-1]
            values.append(str(Decimal(v)*multiplier))
        # Header ordering is evidence only; no hardcoded issuer column direction.
        order=re.findall(r'调整[前后]',t[:t.index(label)])[:2]
        prior={order[i]:values[i+1] for i in range(2)} if len(order)==2 and len(set(order))==2 and len(values)>=3 and p and p.endswith('12-31') else None
        fields[field]={'status':'EXTRACTED_CANDIDATE_NEEDS_SOURCE_VALIDATION','label':label,'current_CNY':values[0],'multiplier':multiplier,'raw_amounts':numbers,'comparative_order':order,'prior_year_adjusted_columns_CNY':prior,'excerpt':tail[:300]}
    return {'status':'SUMMARY_CANDIDATE','fields':fields,'summary_page':selected['page']}

def main():
    assert not (OUT/'first_run_v1.json').exists(),'Preserve first result; no overwrite'
    start=time.perf_counter()
    rows=catalogs()
    groups={}
    for r in rows:
        if r['period'] and 'periodic' in r['queried_kinds'] and not any(x in r['title'] for x in ['摘要','英文','H股']):
            groups.setdefault((r['code'],r['period']),[]).append(r)
    metadata=[]
    for r in rows:
        reasons=[]
        if re.search(r'更正|修订|更新前|更新后',r['title']):
            reasons.append('M1')
        if '补充' in r['title'] and re.search(r'年度|报告|财务|会计',r['title']):
            reasons.append('M2')
        if r['period'] and 'periodic' in r['queried_kinds'] and len(groups.get((r['code'],r['period']),[]))>1 and not any(x in r['title'] for x in ['摘要','英文','H股']):
            reasons.append('M3')
        metadata.append({**r,'title_only_B0':'更正' in r['title'],'candidate_reasons':reasons})
    metadata_s=time.perf_counter()-start
    bodies=[]
    catalog_by_id={r['id']:r for r in rows}
    docs=[{**r,'pages_path':OUT/(r['file']+'.pages.json'),'source_path':OUT/r['file']} for r in read('new_document_inventory.json')]
    saved=json.loads((R5/'documents.json').read_text(encoding='utf-8'))
    for name in RULES['scope']['reused_body_files']:
        d=next(d for d in saved if d['file']==name)
        docs.append({'id':d['id'],'code':d['code'],'file':name,'pages_path':R5/(name+'.pages.json'),'source_path':R5/name})
    for d in docs:
        t0=time.perf_counter()
        cat=catalog_by_id[d['id']]
        pages=json.loads(d['pages_path'].read_text(encoding='utf-8'))
        joined=clean(''.join(p['text'] for p in pages))
        flags=sorted(set(re.findall(r'追溯|重述|会计政策变更|比较期间|调整前|调整后|补充修订',joined)))
        result=extract_summary(pages,cat['period'])
        bodies.append({**cat,'source_file':str(d['source_path']),'source_sha256':sha(d['source_path']),'body_candidate_B1':bool(flags),'body_flags':flags,'extraction':result,'body_detection_seconds':time.perf_counter()-t0,'classification':'CANDIDATE_ONLY_NOT_A_PROVEN_CHANGE'})
    comparisons=[]
    for a,b in itertools.combinations(sorted(bodies,key=lambda r:r['date']),2):
        if not a['period'] or a['code']!=b['code'] or a['period']!=b['period']:
            continue
        fields=[]
        for f in LABELS:
            av=a['extraction']['fields'].get(f,{}).get('current_CNY')
            bv=b['extraction']['fields'].get(f,{}).get('current_CNY')
            fields.append({'field':f,'first':av,'second':bv,'result':'UNKNOWN' if av is None or bv is None else 'DIFFERENT_NUMERIC_CANDIDATE' if Decimal(av)!=Decimal(bv) else 'EQUAL_SELECTED_NUMERIC_CANDIDATE'})
        comparisons.append({'first_id':a['id'],'second_id':b['id'],'same_issuer_and_period':True,'file_sha_differs':a['source_sha256']!=b['source_sha256'],'fields':fields})
    elapsed=time.perf_counter()-start
    save('first_run_v1.json',{'rule_id':RULES['id'],'rules_sha256':sha(OUT/'discovery_rules_v1.json'),'executed_at_utc':now(),'metadata_denominator':len(rows),'metadata':metadata,'body_denominator':len(bodies),'bodies':bodies,'same_period_comparisons':comparisons,'timing':{'metadata_detection_seconds':metadata_s,'total_offline_detection_seconds':elapsed},'warning':'Known-case test only. No IDs used as detection predicates; known IDs retrieve fixed documents and later score truth, not independent discovery. Candidate classifications deliberately not field truth.'})
    print(json.dumps({'metadata':len(rows),'body_documents':len(bodies),'candidate_metadata':sum(bool(x['candidate_reasons']) for x in metadata),'timing_s':elapsed,'unknown_current_fields':sum(not b['extraction']['fields'].get(f,{}).get('current_CNY') for b in bodies if b['period'] for f in LABELS)},ensure_ascii=False))

if __name__=='__main__':
    main()
