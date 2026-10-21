"""Explicit exploratory revision, never overwrites the frozen first run."""
import itertools
import json
import time
from decimal import Decimal
import experiment_v1 as v1
from access import OUT, R5, read, save, now, sha

def main():
    assert not (OUT/'exploratory_v2.json').exists()
    rules=read('exploratory_rules_v2.json')
    start=time.perf_counter()
    v1.LABELS['EQ'].append('归属于上市公司股东的股东权益')
    first=read('first_run_v1.json')
    results=[]
    for d in first['bodies']:
        pages_file=(OUT if (OUT/(d['id']+'.pdf.pages.json')).exists() else R5)/(d['id']+'.pdf.pages.json' if (OUT/(d['id']+'.pdf.pages.json')).exists() else __import__('pathlib').Path(d['source_file']).name+'.pages.json')
        pages=json.loads(pages_file.read_text(encoding='utf-8'))
        primary=next((i for i,p in enumerate(pages[:30]) if '主要会计数据和财务指标' in v1.clean(p['text'])),None)
        if primary is None:
            results.append({'id':d['id'],'code':d['code'],'period':d['period'],'is_periodic_report':False,'status':'NOTICE_REQUIRES_SCOPE_TRIAGE_NO_AUTO_CLEAR'})
            continue
        selection=pages[primary:primary+2]
        result=v1.extract_summary([{'page':pages[primary]['page'],'text':'\n'.join(p['text'] for p in selection)}],d['period'])
        for f,r in result['fields'].items():
            if r.get('label'):
                r['label_source_page']=next((p['page'] for p in selection if r['label'] in v1.clean(p['text'])),None)
        results.append({'id':d['id'],'code':d['code'],'period':d['period'],'is_periodic_report':True,'source_pages':[p['page'] for p in selection],'extraction':result,'source_sha256':d['source_sha256'],'date':d['date']})
    comparisons=[]
    for a,b in itertools.combinations([r for r in results if r['is_periodic_report']],2):
        if a['code']!=b['code'] or a['period']!=b['period']:
            continue
        comparisons.append({'ids':[a['id'],b['id']],'fields':{f:{'first':a['extraction']['fields'].get(f,{}).get('current_CNY'),'second':b['extraction']['fields'].get(f,{}).get('current_CNY'),'changed':a['extraction']['fields'].get(f,{}).get('current_CNY')!=b['extraction']['fields'].get(f,{}).get('current_CNY')} for f in v1.LABELS}})
    comparecols=[]
    for d in results:
        if not d['is_periodic_report']:
            continue
        for f,r in d['extraction']['fields'].items():
            cols=r.get('prior_year_adjusted_columns_CNY')
            if cols:
                comparecols.append({'code':d['code'],'source_id':d['id'],'comparison_period':str(int(d['period'][:4])-1)+'-12-31','field':f,'before':cols.get('调整前'),'after':cols.get('调整后'),'changed':Decimal(cols['调整前'])!=Decimal(cols['调整后'])})
    denominator=sum(r['is_periodic_report'] for r in results)*3
    extracted=sum(bool(r['extraction']['fields'].get(f,{}).get('current_CNY')) for r in results if r['is_periodic_report'] for f in v1.LABELS)
    save('exploratory_v2.json',{'id':rules['id'],'rules_sha256':sha(OUT/'exploratory_rules_v2.json'),'executed_at_utc':now(),'results':results,'current_field_denominator':denominator,'extracted_current_fields':extracted,'same_period_comparisons':comparisons,'comparative_column_candidates':comparecols,'machine_seconds':time.perf_counter()-start,'validation_boundary':'Exploratory observed-case improvement only. Notices retain UNKNOWN triage until agent semantic review; no issuer/ID extraction override.'})
    print(json.dumps({'extracted':extracted,'denominator':denominator,'comparative_candidates':len(comparecols),'changed_comparatives':sum(c['changed'] for c in comparecols)},ensure_ascii=False))

if __name__=='__main__':
    main()
