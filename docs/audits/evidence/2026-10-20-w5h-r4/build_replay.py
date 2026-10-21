"""Evidence-driven offline demonstration, not a provider response or production API."""
import io
import json
import re
import struct
import zipfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from audit_common import OUT, ROOT, read, save, sha

MONEY=re.compile(r'[-−－]?\d{1,3}(?:,\d{3})+\.\d{2}')
RULE='DATE_ONLY_NEXT_OBSERVED_SH_INDEX_SESSION_CLOSE_DIAGNOSTIC_NOT_OWNER_FROZEN'
FIELDS={'revenue':'营业收入','net_profit_attributable_to_parent':'归属于上市公司股东的净利润','net_operating_cashflow':'经营活动产生的现金流量净额','equity_attributable_to_parent':'归属于上市公司股东的净资产'}

def pages(name):
    return read(name+'.pages.json')

def row(pages_obj, selected_pages, label):
    text='\n'.join(pages_obj[i-1]['text'] for i in selected_pages)
    pattern=r'\s*'.join(re.escape(c) for c in label)
    m=re.search(pattern,text)
    assert m, (selected_pages,label)
    # Short, explicit row region. Values are read from actual PDF text, not supplied anchors.
    tail=text[m.end():m.end()+380]
    found=list(MONEY.finditer(tail))
    assert found,(selected_pages,label)
    return {'values':[x.group().replace(',','').replace('−','-').replace('－','-') for x in found], 'label':label,'pages':selected_pages,'excerpt':text[max(0,m.start()-25):m.end()+250]}

def q32(v):
    return struct.unpack('<f',struct.pack('<f',float(v)))[0]

def ulp32(v):
    x=abs(float(v));i=struct.unpack('<I',struct.pack('<f',x))[0]
    return Decimal(str(struct.unpack('<f',struct.pack('<I',i+1))[0]-x))

orig=pages('official_original_2017.pdf');rev=pages('official_annual_2018.pdf')
index=read('cninfo_index_summary.json')
catalog={r['announcementId']:r for q in index.values() for r in q['records']}
requests=read('requests.json')['requests']
documents={}
for doc_id,name,period in [
    ('1204793690','official_original_2017.pdf','2017-01-01/2017-12-31'),
    ('1206168292','official_annual_2018.pdf','2018-01-01/2018-12-31; adjusted comparative 2017'),
    ('1206168283','correction_audit_20190430.pdf','2017 affected statements; title says 2018 correction audit'),
    ('1206201352','official_regulatory_letter_20190501.pdf','2017 restatement inquiry; no replacement numerical statements'),
]:
    item=catalog[doc_id]
    date=datetime.fromtimestamp(item['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
    req=next(x for x in requests if x['id']==name and x.get('status')=='RESPONSE_SAVED')
    documents[doc_id]={'disclosure_id':'CNINFO:'+doc_id,'title':re.sub('<[^>]+>','',item['announcementTitle']),'issuer':'康美药业股份有限公司','security_id':'SH:600518','financial_period':period,'disclosure_date':date,'time_granularity':'DATE_ONLY; announcementTime is catalog date, not proven release clock time','original_url':req['url'],'retrieved_at_utc':req['finished_at'],'file':name,'sha256':sha(OUT/name),'complete_original':True,'catalog_file':'original_2017_index.json' if doc_id=='1204793690' else ('annual_2018_index.json' if doc_id=='1206168292' else 'correction_chain_index.json'),'catalog_raw_timestamp':item['announcementTime']}

original_rows={};revised_rows={};events=[]
for field,label in FIELDS.items():
    o=row(orig,[7] if field=='equity_attributable_to_parent' else [6],label)
    r=row(rev,[6],label)
    o['selected_value']=o['values'][0]
    r['selected_value']=r['values'][1] # 2018 current, 2017 adjusted, 2017 unadjusted, 2016...
    assert Decimal(r['values'][2]) == Decimal(o['selected_value'])
    original_rows[field]=o;revised_rows[field]=r

CF={98:'销售商品、提供劳务收到的现金',100:'收到其他与经营活动有关的现金',101:'经营活动现金流入小计',102:'购买商品、接受劳务支付的现金',103:'支付给职工以及为职工支付的现金',104:'支付的各项税费',105:'支付其他与经营活动有关的现金',106:'经营活动现金流出小计',107:'经营活动产生的现金流量净额'}
tdx=read('tdx_reconciliation.json');fn=tdx['fields'];matrix=[]
core=[]
for field,slot in [('revenue',74),('net_profit_attributable_to_parent',96),('net_operating_cashflow',107),('equity_attributable_to_parent',271)]:
    ov=original_rows[field]['selected_value'];rv=revised_rows[field]['selected_value'];actual=fn[f'FN{slot}']
    core.append({'field_name':field,'tdx_field':f'FN{slot}','original_direct_value':ov,'revised_direct_value':rv,'tdx_value':actual,'matches_original_float32':actual==q32(ov),'matches_revised_float32':actual==q32(rv)})
assert all(r['matches_revised_float32'] for r in core if r['tdx_field']!='FN107')
assert next(r for r in core if r['tdx_field']=='FN107')['matches_original_float32']
for k,label in CF.items():
    o=row(orig,[106,107],label)
    r=row(rev,[115,116],label)
    ov,rv=o['values'][0],r['values'][1]
    actual=fn[f'FN{k}']
    matrix.append({'field':f'FN{k}','definition':label,'unit':'CNY yuan','basis':'CONSOLIDATED; cumulative 2017-01-01/2017-12-31','original_direct_value':ov,'revised_comparative_direct_value':rv,'tdx_float32_value':actual,'matches_original_float32':actual==q32(ov),'matches_revised_float32':actual==q32(rv),'original_locator':o,'revision_locator':r})

diagnostics={}
for name,positive,negative in [('stored_totals_net',[101],[106,107]),('inflow_components_to_subtotal',[98,99,100],[101]),('outflow_components_to_subtotal',[102,103,104,105],[106])]:
    residual=sum((Decimal(str(fn[f'FN{k}'])) for k in positive),Decimal(0))-sum((Decimal(str(fn[f'FN{k}'])) for k in negative),Decimal(0))
    bound=sum((ulp32(fn[f'FN{k}'])/2 for k in positive+negative),Decimal(0))
    diagnostics[name]={'residual_yuan':str(residual),'sum_half_ulp_bound_yuan':str(bound),'within_float32_bound':abs(residual)<=bound}
computed=sum((Decimal(str(fn[f'FN{k}'])) for k in (98,99,100)),Decimal(0))-sum((Decimal(str(fn[f'FN{k}'])) for k in (102,103,104,105)),Decimal(0))
direct_revised=Decimal(revised_rows['net_operating_cashflow']['selected_value'])
diagnostics['ocf_from_tdx_components']={'value_yuan':str(computed),'kind':'DETERMINISTIC_DIAGNOSTIC_CALCULATION_NOT_A_SOURCE_DISCLOSURE','difference_from_official_revised_yuan':str(computed-direct_revised),'not_used_in_pit_replay':True}

# Independent installed parser: constructor bypass prevents setup/download/config mutation.
from mootdx.financial.financial import Financial
zip_path=OUT.parent/'2026-10-20-w5h-r3/http_gpcw20171231.response'
with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as z:dat=z.read('gpcw20171231.dat')
stream=io.BytesIO(dat);stream.name='gpcw20171231.dat'
decoded=next(x for x in Financial.__new__(Financial).parse(stream) if x[0]=='600518')
assert all(decoded[k+1]==fn[f'FN{k}'] for k in range(98,108))

calendar=ROOT/'.rh3a2-vipdoc/sh/lday/sh000001.day'
cb=calendar.read_bytes();days=sorted({struct.unpack_from('<I',cb,i)[0] for i in range(0,len(cb),32)})
def next_session(date):
    n=int(date.replace('-',''))
    d=next(x for x in days if x>n)
    return f'{d//10000:04d}-{d//100%100:02d}-{d%100:02d}'

for doc_id,rows,logical_version in [('1204793690',original_rows,'ORIGINAL_2018_04_26'),('1206168292',revised_rows,'COMPARATIVE_RESTATEMENT_2019_04_30')]:
    doc=documents[doc_id]
    events.append({'disclosure_id':doc['disclosure_id'],'disclosure_date':doc['disclosure_date'],'available_on_session_close':next_session(doc['disclosure_date']),'version_identity':f'SH600518:FY2017:{logical_version}:{doc["sha256"]}','fields':{k:r['selected_value'] for k,r in rows.items()},'provenance':{k:{'origin_kind':'OFFICIAL_PDF_DIRECT_VALUE','original_url':doc['original_url'],'file':doc['file'],'source_sha256':doc['sha256'],'locator_pages':r['pages'],'excerpt':r['excerpt'],'column_semantics':'2017 current-year original' if doc_id=='1204793690' else '2017 adjusted comparative, not 2018 current-year'} for k,r in rows.items()}})

def replay(T):
    eligible=[e for e in events if e['available_on_session_close']<=T]
    chosen=max(eligible,key=lambda x:x['disclosure_date']) if eligible else None
    output=[]
    for field in FIELDS:
        output.append({'security_id':'SH:600518','financial_period':'2017-01-01/2017-12-31','field_name':field,'value':chosen['fields'][field] if chosen else 'UNKNOWN','unit':'CNY yuan','accounting_basis':'CONSOLIDATED; FY cumulative for revenue/profit/OCF; period-end attributable-parent equity','disclosure_id':chosen['disclosure_id'] if chosen else 'NONE_ALLOWED_AT_T','disclosure_date':chosen['disclosure_date'] if chosen else 'UNKNOWN','version_identity':chosen['version_identity'] if chosen else 'NONE_ALLOWED_AT_T','decision_date':T,'availability_rule':RULE,'provenance':chosen['provenance'][field] if chosen else {'origin_kind':'NO_ELIGIBLE_REPORT','excluded_later_disclosures':[{'id':e['disclosure_id'],'date':e['disclosure_date']} for e in events]},'quality_status':'VERIFIED_SELECTED_FIELD; DATE_RULE_CONDITIONAL; CHAIN_COMPLETENESS_UNKNOWN' if chosen else 'UNKNOWN_NOT_DISCLOSED_THIS_ANNUAL_REPORT_YET'})
    return output

states={T:replay(T) for T in ('2018-04-24','2018-04-27','2019-05-06')}
assert next_session('2018-04-26')=='2018-04-27'
assert next_session('2019-04-30')=='2019-05-06'
assert all(r['value']=='UNKNOWN' for r in states['2018-04-24'])
assert all(r['disclosure_id']=='CNINFO:1204793690' for r in states['2018-04-27'])
assert all(r['disclosure_id']=='CNINFO:1206168292' for r in states['2019-05-06'])
assert next(r['value'] for r in states['2019-05-06'] if r['field_name']=='net_operating_cashflow')=='-4840052606.46'
assert next(r['value'] for r in states['2018-04-27'] if r['field_name']=='net_operating_cashflow')=='1842794237.84'
assert all(r['provenance']['origin_kind']=='OFFICIAL_PDF_DIRECT_VALUE' for T,rs in states.items() if T!='2018-04-24' for r in rs)
assert all(r['disclosure_date']<=T for T,rs in states.items() if T!='2018-04-24' for r in rs)
assert not diagnostics['inflow_components_to_subtotal']['within_float32_bound']
assert not diagnostics['outflow_components_to_subtotal']['within_float32_bound']
assert diagnostics['stored_totals_net']['within_float32_bound']

# A stale TDX OCF would be rejected even though the top-level subtotal identity holds.
stale_ocf=Decimal(str(fn['FN107']))
assert stale_ocf != Decimal(next(r['value'] for r in states['2019-05-06'] if r['field_name']=='net_operating_cashflow'))

warmup={'2016_equity_comparative_in_original_2017':original_rows['equity_attributable_to_parent']['values'][1],'2016_equity_adjusted_comparative_in_2018_report':revised_rows['equity_attributable_to_parent']['values'][3],'source_dates':['2018-04-26','2019-04-30'],'kind':'DIRECT_COMPARATIVES_AS_DISCLOSED; NOT_TODAYS_STRUCTURED_VALUES','independent_2016_original_report_verified':False,'full_financial_warmup':'NOT_QUALIFIED; required formula/quarter coverage not frozen or demonstrated','computed_roe':'UNKNOWN_NOT_COMPUTED'}
save('official_document_identities.json',documents)
save('financial_core_comparison.json',{'source':'fresh extraction from the two official PDFs; not hardcoded R3 values','fields':core})
save('cashflow_comparison.json',{'matrix':matrix,'fn99':'TDX=0; issuer PDF row blank; blank not silently converted into economic zero','diagnostics':diagnostics,'independent_installed_parser_all_fn98_to_fn107_match':True,'parent_company_original_ocf':row(orig,[108],'经营活动产生的现金流量净额')['values'][0],'accounting_scope':'Consolidated FY2017; mother-company and current-year 2018 columns explicitly excluded'})
save('disclosure_events.json',{'identity':'AUDIT_DERIVED_OFFICIAL_DISCLOSURE_LEDGER_NOT_VENDOR_RESPONSE','events':events,'version_chain_completeness':'UNKNOWN; finite title-index and referenced-document checks only','availability_rule':RULE,'calendar_path':str(calendar),'calendar_sha256':sha(calendar),'calendar_purpose':'fixed-date diagnostic session selection, not full-market calendar qualification'})
save('three_date_information_sets.json',{'identity':'OFFLINE_AUDIT_DEMONSTRATION_NOT_PRODUCTION_API_OR_NEW_SOURCE','states':states,'financial_warmup':warmup,'roe_algorithm_and_pe_type':'NOT_FROZEN_BY_THIS_TASK'})
save('offline_assertions.json',{'status':'PASS_BOUNDED_SELECTED_FOUR_FIELDS','T0_future_original_excluded':True,'T1_future_restatement_excluded':True,'T2_negative_revised_ocf_selected':True,'stale_tdx_ocf_rejected':True,'all_populated_values_from_official_pdf_direct_cells':True,'no_today_structured_value_injected':True,'no_post_T2_disclosure_injected':True,'date_only_rule':'CANDIDATE_NOT_OWNER_FROZEN','version_chain_completeness':'UNKNOWN','full_s07_gate':'NOT_PASSED','network_requests':0})
print(json.dumps({'matrix':[{k:r[k] for k in ('field','original_direct_value','revised_comparative_direct_value','tdx_float32_value','matches_original_float32','matches_revised_float32')} for r in matrix],'diagnostics':diagnostics,'states':{T:{r['field_name']:r['value'] for r in rs} for T,rs in states.items()},'warmup':warmup},ensure_ascii=True))
