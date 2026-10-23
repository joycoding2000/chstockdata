"""Issuer-level cash-flow table identity via non-target rows and parent exclusion.

The OCF amount being qualified is deliberately excluded from the fingerprint.
The reference is an identified original's complete cash-flow matrix, not truth
fixtures or today's structured numbers. All source differences remain recorded.
"""
import re
import sys
from decimal import Decimal
from common import HERE, ROOT, OLD, F2, REPLIES, read, save, sha, compact
from qualification_rules import fingerprint_qualified


def number(text):
    t=compact(text or '').replace(',','').replace('，','')
    return Decimal(t) if re.fullmatch(r'-?\d+\.\d{2}',t) else None


def main():
    import pdfplumber
    sys.path.insert(0,str(OLD))
    import extract_facts as previous
    def table_rows(page,table):
        return [[c['text'] for c in r['cells']] for r in
                previous.complete_open_edges(page,previous.base.grid_rows(table),table)]
    def table_text(rows):
        return compact(''.join(c or '' for r in rows for c in r))
    originals=read(HERE/'original_statement_tables.json')
    ref=next(p for p in originals if p['id']=='1216561621' and p['page']==80)
    original_doc=next(d for d in read(F2/'dataset_legacy.json')['documents'] if d['id']==ref['id'])
    assert sha(ROOT/original_doc['path'])==original_doc['sha256']
    reference={}
    for row in ref['tables'][0]['rows']:
        label=compact(row[0] or '')
        if any(s in label for s in ('现金流入小计','现金流出小计','现金流量净额')) and len(row)>=6:
            reference[label]={'2022-12-31':{'consolidated':number(row[2]),'parent':number(row[3])},
                              '2021-12-31':{'consolidated':number(row[4]),'parent':number(row[5])}}
    results=[]
    for d in read(OLD/'documents.json'):
        if d['id'] not in REPLIES:continue
        assert sha(ROOT/d['path'])==d['sha256']
        pages=read(OLD/'text'/f"{d['id']}.json")['pages']
        cover=''.join(compact(p['text']) for p in pages[:3])
        issuer_anchor='江苏中南建设集团股份有限公司' in cover
        plan=[p['physical_page'] for p in pages if '现金流量表简要情况如下' in compact(p['text'])]
        for n in plan:
            with pdfplumber.open(ROOT/d['path']) as pdf:
                page=pdf.pages[n-1]
                tables=page.find_tables()
                target=next(t for t in tables if '经营活动现金流入小计' in table_text(table_rows(page,t)))
                rows=table_rows(page,target)
                bounds=target.bbox
                header=rows[0]
                periods=[]
                for c in header[1:]:
                    m=re.search(r'(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})',compact(c or ''))
                    periods.append(f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}' if m else None)
                continued=[]
                # Accept only the old parser's independently checked label continuation.
                oldfacts=read(OLD/'parsed_source_facts.json')['facts']
                carry=next((f for f in oldfacts if f['id']==d['id'] and f['physical_page']==n and
                            f.get('label_continuation',{}).get('physical_page')==n+1),None)
                if carry or '经营活动产生的现金流量净额' not in table_text(rows) or len(rows)<8:
                    nextpage=pdf.pages[n]
                    following=[t for t in nextpage.find_tables() if '投资活动现金流入小计' in table_text(table_rows(nextpage,t))]
                    assert len(following)==1
                    nexttable=following[0]
                    nextrows=table_rows(nextpage,nexttable)
                    assert compact(str(nextrows[0]))==compact(str(header))
                    assert abs(nexttable.bbox[0]-target.bbox[0])<3 and nexttable.bbox[1]<nextpage.height*.2
                    continued=nextrows[1:]
                    if carry:
                        assert compact(nextrows[1][0])=='净额'
                        rows[-1][0]+='净额'
                        continued=continued[1:]
                evidence=[];parent_matches=[];ocf=[]
                for row in rows[1:]+continued:
                    label=compact(row[0] or '')
                    if label not in reference:continue
                    for per,raw in zip(periods,row[1:]):
                        if per not in reference[label]:continue
                        val=number(raw)
                        if val is None:continue
                        r=reference[label][per]
                        matches=r['consolidated'] is not None and abs(val*10000-r['consolidated'])<=Decimal('50.005')
                        parent_match=r['parent'] is not None and abs(val*10000-r['parent'])<=Decimal('50.005')
                        item={'label':label,'period':per,'raw_text':raw,'value_CNY':str(val*10000),
                              'unit':'万元','multiplier':10000,'reference_consolidated_CNY':str(r['consolidated']),
                              'reference_parent_CNY':str(r['parent']),'matches':matches,'parent_matches':parent_match}
                        if label=='经营活动产生的现金流量净额':ocf.append(item)
                        else:evidence.append(item)
                        if parent_match:parent_matches.append(item)
                context=compact(pages[n-1]['text'])
                table_unit='单位：万元' in context
                caption='报告期内，公司的现金流量表简要情况如下' in context
                # Scope comes from a multi-row, multi-period identity under an
                # issuer financial-statement caption, with a parent counterfactual.
                parent_excluded=bool(evidence) and not parent_matches
                accepted=fingerprint_qualified(evidence,issuer_anchor and table_unit and caption,parent_excluded)
                result={'id':d['id'],'code':d['code'],'date':d['date'],'source_sha256':d['sha256'],
                        'source_path':d['path'],'evidence_page':n,'continued_page':n+1 if continued else None,
                        'bbox':list(bounds),'header':header,'periods':periods,'issuer_anchor':issuer_anchor,
                        'caption':caption,'table_unit_verified':table_unit,'parent_excluded':parent_excluded,
                        'scope':'consolidated' if accepted else 'unknown',
                        'method':'ISSUER_CAPTION_PLUS_MULTI_ROW_MULTI_PERIOD_CF_IDENTITY_EXCLUDING_OCF_AND_PARENT_COUNTERFACTUAL',
                        'independent_reference':{**original_doc,'physical_page':80,'title':'合并及公司现金流量表'},
                        'fingerprint_rows':evidence,'ocf_rows':ocf,'not_a_direct_audit_id_quote':True,
                        'continuity_proof':carry.get('proof') if carry else
                           {'same_header':True,'same_left_column_within_3pt':True,'adjacent_page_top':True} if continued else None,
                        'status':'VERIFIED_EXISTING_VERSION' if accepted else 'UNRESOLVED_MATERIAL'}
                results.append(result)
                print(d['id'],n,result['scope'],'non-OCF rows',len(evidence),'matches',sum(x['matches'] for x in evidence),flush=True)
    conflicts=[]
    for d in read(OLD/'documents.json'):
        if d['id'] not in REPLIES:continue
        pages=read(OLD/'text'/f"{d['id']}.json")['pages']
        variants=[]
        for p in pages:
            t=compact(p['text'])
            if '1,677,198.08万元' in t:
                at=t.index('1,677,198.08万元')
                variants.append({'physical_page':p['physical_page'],'raw_context':t[max(0,at-110):at+90]})
        sc=next(r for r in results if r['id']==d['id'])
        table=next((r for r in sc['ocf_rows'] if r['period']=='2021-12-31'),None)
        conflicts.append({'id':d['id'],'code':d['code'],'field':'OCF','period':'2021-12-31',
                          'date':d['date'],'text_occurrences':variants,'table_page':sc['evidence_page'],'table':table,
                          'text_value_CNY':'16771980800','table_value_CNY':'16771980500',
                          'printed_difference_CNY':'300','original_exact_CNY':str(reference['经营活动产生的现金流量净额']['2021-12-31']['consolidated']),
                          'same_printed_unit_and_precision':True,'rounding_explains_difference':False,
                          'classification':'SOURCE_INTERNAL_INCONSISTENCY_CAUSE_UNDETERMINED',
                          'different_scope_supported':False,'auto_corrected':False,'not_auto_revision':True})
    assert len(results)==6 and len(conflicts)==6 and all(len(c['text_occurrences'])==1 for c in conflicts)
    save('reply_scope_qualification.json',{'denominator':6,'rows':results,
         'scopes_verified':sum(r['scope']=='consolidated' for r in results),'conflicts':conflicts,
         'numeric_patches':0,'reference_original_verified':True})


if __name__=='__main__':main()
