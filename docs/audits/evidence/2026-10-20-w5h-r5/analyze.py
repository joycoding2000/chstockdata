"""Fixed-case offline measurements; case/page choices are deliberately explicit."""
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from measure import OUT, ROOT, REG, read, save, sha

NP='归属于上市公司股东的净利润'
OCF='经营活动产生的现金流量净额'
EQ='归属于上市公司股东的净资产'
# pages are physical 1-based PDF pages, not printed-page labels.
PLANS={
 '600519':{'multiplier':1,'annual':[(5,NP),(5,OCF),(5,EQ)],'quarter':[(9,'归属于母公司股东的净利润'),(11,OCF),(2,'归属于上市公司股东的所有者权益')],'prior_order':['adjusted','unadjusted']},
 '000002':{'multiplier':1,'annual':[(10,NP),(10,OCF),(11,EQ)],'quarter':[(2,NP),(2,OCF),(2,'归属于上市公司股东的所有者权益')],'prior_order':['unadjusted','adjusted']},
 '300750':{'multiplier':10000,'annual':[(7,NP),(7,OCF),(7,EQ)],'quarter':[(9,'归属于母公司所有者的净利润'),(11,OCF),(2,'归属于上市公司股东的所有者权益')],'prior_order':['unadjusted','adjusted']},
 '601398':{'multiplier':1000000,'annual':[(14,'归属于母公司股东的净利润'),(14,OCF),(15,'归属于母公司股东的权益')],'quarter':[(1,'归属于母公司股东的净利润'),(13,OCF),(2,'归属于母公司股东的权益')],'prior_order':['unadjusted','adjusted']},
 '000961':{'multiplier':1,'annual':[(6,'归属于母公司股东的净利润'),(6,OCF),(6,EQ)],'quarter':[(1,'归属于母公司股东的净利润'),(1,OCF),(1,'归属于母公司股东的所有者权益')],'prior_order':['unadjusted','adjusted']},
}

def extract(file,page,label,count):
    t=read(file+'.pages.json')[page-1]['text']
    pattern=r'\s*'.join(re.escape(c) for c in label)
    m=re.search(pattern,t)
    assert m,(file,page,label)
    tail=t[m.end():m.end()+400]
    money=r'\(?\s*[-−－]?\s*\d{1,3}(?:,\d{3})+(?:\.\d{2})?\s*\)?'
    raw=re.findall(money,tail)[:count]
    assert len(raw)==count,(file,label,raw)
    vals=[]
    for v in raw:
        v=re.sub(r'\s+','',v).replace(',','').replace('−','-').replace('－','-')
        if v.startswith('(') and v.endswith(')'):
            v='-'+v[1:-1]
        vals.append(str(Decimal(v)))
    return {'page':page,'label':label,'excerpt':t[max(0,m.start()-100):m.end()+400],'raw_numbers':raw,'source_values':vals}

def fields():
    start=time.perf_counter()
    facts=[]
    for code,p in PLANS.items():
        for per,slot in [('FY2023','annual'),('Q12024','quarter')]:
            file=code+'_'+per+'.pdf'
            doc=next(d for d in read('documents.json') if d['file']==file)
            for field,(page,label) in zip(['NP_parent','OCF_consolidated','EQ_parent'],p[slot]):
                row=extract(file,page,label,3 if slot=='annual' else 2)
                n=row['source_values']
                current_period='2023-12-31' if slot=='annual' else '2024-03-31'
                periods=[current_period,'2022-12-31','2022-12-31'] if slot=='annual' else [current_period,'2023-12-31' if field=='EQ_parent' else '2023-03-31']
                versions=['current']+p['prior_order'] if slot=='annual' else ['current','comparative_as_printed_in_2024_Q1']
                for i,v in enumerate(n):
                    facts.append({'code':code,'file':file,'official_id':doc['id'],'announcement_date':doc['catalog_date'],'disclosure_time_granularity':'DATE_ONLY_NOT_PROVEN_CLOCK','field':field,'financial_period_end':periods[i],'duration':'instant' if field=='EQ_parent' else 'FY_YTD_12M' if slot=='annual' else 'YTD_3M_SAME_AS_Q1','consolidation':'consolidated_parent_attributable' if field!='OCF_consolidated' else 'consolidated','column':versions[i],'source_value':v,'multiplier_to_CNY':p['multiplier'],'CNY_value':str(Decimal(v)*p['multiplier']),'source_rounding_quantum_CNY':1000000 if code=='601398' else 100 if code=='300750' else 0.01,'extraction':'machine_numeric_from_manually_located_page_label_and_column_plan','numeric_transcription_corrections':0,'semantic_review_required':True,**{k:row[k] for k in ['page','label','excerpt','raw_numbers']}})
    save('financial_facts.json',{'facts':facts,'current_fact_denominator':30,'current_facts_extracted':sum(x['column']=='current' for x in facts),'comparative_occurrences':sum(x['column']!='current' for x in facts),'independent_prior_originals_downloaded':0,'Q1_2023_equity_originals_downloaded':0,'formula_calculated':False,'machine_field_extraction_wall_seconds':time.perf_counter()-start})
    print(json.dumps({'facts':len(facts),'current':sum(x['column']=='current' for x in facts)},ensure_ascii=False))

def compare():
    start=time.perf_counter()
    facts=read('financial_facts.json')['facts']
    pairs=[]
    cols={'benefit':('NP_parent','parent_holder_net_profit'),'cash':('OCF_consolidated','act_cash_flow_net'),'debt':('EQ_parent','parent_holder_equity_total')}
    for code in ['600519','000961']:
        for table,(field,key) in cols.items():
            obj=read(code+'_ths_'+table+'.json')
            assert obj['status_code']==0
            records=obj['data']['data']
            for date in ['2023-12-31','2024-03-31','2022-12-31']:
                r=next((r for r in records if r['date']==date),None)
                value=r['index_list'][key]['value'] if r else None
                value=value if value not in ('',None,'--') else None
                matched=[f for f in facts if f['code']==code and f['field']==field and f['financial_period_end']==date and (date=='2022-12-31' or f['column']=='current')]
                pairs.append({'code':code,'table':table,'key':key,'date':date,'structured_value':value,'structured_single':r['index_list'][key].get('single') if r else None,'matched_official_columns':[f['column'] for f in matched if value is not None and Decimal(value)==Decimal(f['CNY_value'])],'official_values':{f['column']:f['CNY_value'] for f in matched},'has_disclosure_id_or_vintage':any(k in r for k in ['announcementId','available_at','vintage_id']) if r else False})
    save('structured_comparison.json',{'comparisons':pairs,'target_current_denominator':12,'current_value_matches':sum(bool(x['matched_official_columns']) for x in pairs if x['date']!='2022-12-31'),'base_checks':6,'machine_json_and_compare_wall_seconds':time.perf_counter()-start,'asof_qualification':'NOT_PASSED_CURRENT_STRUCTURED_ROWS_DO_NOT_ENCODE_OLD_VINTAGES'})
    print(json.dumps(read('structured_comparison.json'),ensure_ascii=False))

def inventory():
    rows=[]
    period_patterns=[r'2022年?年度报告',r'2023年第?一季度报告',r'2023年?半年度报告',r'2023年第?三季度报告',r'2023年?年度报告',r'2024年第?一季度报告',r'2024年?半年度报告',r'2024年第?三季度报告']
    for code in PLANS:
        anns=read(code+'_periodic_index.json')['announcements']
        matches=[]
        for per,pat in zip(REG['full_year_period_inventory'],period_patterns):
            hits=[a for a in anns if re.search(pat,re.sub(r'\s+','',html.unescape(a['announcementTitle']))) and not any(k in a['announcementTitle'] for k in ['摘要','英文','H股'])]
            matches.append({'financial_period_end':per,'files':[{'id':a['announcementId'],'title':a['announcementTitle'],'url':'https://static.cninfo.com.cn/'+a['adjunctUrl']} for a in hits],'status':'INDEX_FOUND_NOT_ALL_DOWNLOADED' if hits else 'NORMAL_EMPTY_IN_BOUNDED_INDEX_POST_DELISTING_OBLIGATION_NOT_DECIDED' if code=='000961' and per>'2024-03-31' else 'NOT_FOUND'})
        docs=[d for d in read('documents.json') if d['code']==code]
        metrics=[m for m in read('pdf_measurements.json') if m['code']==code]
        reqs=[r for r in read('requests.json')['requests'] if r['file'].startswith(code)]
        rows.append({'code':code,'period_inventory':matches,'selected_download_targets':2,'downloaded_targets':sum(d['status']=='PDF_OBTAINED' for d in docs),'PDF_bytes':sum(m['bytes'] for m in metrics),'PDF_pages':sum(m['pages'] for m in metrics),'PDF_download_wall_seconds':sum(r['http_wall_seconds'] for r in reqs if r['file'].endswith('.pdf') and 'identity' not in r['file']),'index_and_identity_wall_seconds':sum(r['http_wall_seconds'] for r in reqs if '_index.' in r['file'] or '_issuer.' in r['file']),'structured_http_wall_seconds':sum(r['http_wall_seconds'] for r in reqs if '_ths_' in r['file']),'machine_parse_wall_seconds':sum(m['machine_parse_wall_seconds'] for m in metrics),'empty_text_pages':sum(m['empty_text_pages'] for m in metrics),'manual_required':'Page/label plans; units; period/column/version interpretation. Not independent human reviewed.'})
    save('case_costs_and_denominators.json',{'cases':rows,'inventory_denominator':40,'inventory_found':sum(bool(p['files']) for r in rows for p in r['period_inventory']),'target_file_denominator':10,'downloaded':sum(r['downloaded_targets'] for r in rows),'unfetched_periods_are_not_successes':True})
    print(json.dumps(read('case_costs_and_denominators.json'),ensure_ascii=False))

def render():
    binary=Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    rows=[]
    for code,page,per in [('600519',5,'FY2023'),('000002',10,'FY2023'),('300750',7,'FY2023'),('601398',14,'FY2023'),('000961',6,'FY2023'),('000002',2,'Q12024')]:
        name=f'{code}_{per}'
        args=[str(binary),'-f',str(page),'-l',str(page),'-r','100','-scale-to','1800','-jpeg','-jpegopt','quality=85',str(OUT/(name+'.pdf')),str(OUT/(name+'_qa'))]
        start=time.perf_counter()
        r=subprocess.run(args,capture_output=True,encoding='utf-8',errors='replace')
        rows.append({'file':name+'.pdf','page':page,'returncode':r.returncode,'wall_seconds':time.perf_counter()-start,'stderr':r.stderr,'images':[p.name for p in OUT.glob(name+'_qa-*.jpg')]})
        assert r.returncode==0
    save('render_log.json',rows)
    print(json.dumps(rows,ensure_ascii=False))

if __name__=='__main__':
    {'fields':fields,'compare':compare,'inventory':inventory,'render':render}[sys.argv[1]]()
