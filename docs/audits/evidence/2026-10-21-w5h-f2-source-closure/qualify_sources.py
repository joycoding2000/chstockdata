"""Source qualification scorer; parser/replay never consume expected amounts."""
import hashlib,re,time
from collections import Counter,defaultdict
from decimal import Decimal
from fetch_named import OUT,ROOT,F2,read,save
from extract_facts import extract_all,base


def main():
    t=time.perf_counter()
    docs={d['id']:d for d in read(OUT/'documents.json')}
    parsed=read(OUT/'parsed_source_facts.json')
    assert parsed['code_sha256']==hashlib.sha256((OUT/'extract_facts.py').read_bytes()).hexdigest()
    facts=extract_all()
    references=[]
    for name in ['certified_facts.json','certified_new_facts.json']:
        c=read(F2/name)
        assert c['whole_batch_has_zero_incorrect_accepted_values']
        references+=c['facts']
    scored=[]
    for filename in ['expected_source_fields.json','expected_summary_columns.json','expected_dated_narrative.json','expected_annual_quote.json','expected_split_row.json']:
        for c in read(OUT/filename)['cases']:
            xs=[f for f in facts if all(f[k]==c[k] for k in ['id','field','period','physical_page'])]
            same=[f for f in xs if f['scope']==c['scope']]
            accepted=bool(same)
            ok=accepted and all(Decimal(f['value_CNY'])==Decimal(c['value_CNY']) and f['multiplier']==c['multiplier'] for f in same)
            scored.append({'expected':c,'actual':xs,'status':'PASS' if ok else 'FAIL' if accepted else 'UNKNOWN',
                           'reason':None if ok else 'AMBIGUOUS_SCOPE_FAIL_CLOSED' if xs else 'NO_PARSED_CANDIDATE'})
    save('source_value_validation.json',{'denominator':len(scored),'counts':dict(Counter(r['status'] for r in scored)),
         'cases':scored,'parser_reads_truth':False,'not_a_blind_test':True})
    assert not any(r['status']=='FAIL' for r in scored), 'Wrong accepted value blocks entire batch'
    comparisons=[]
    for i,f in enumerate(facts):
        basic=(f['scope']=='consolidated' and f['period']<=f['announcement_date'] and f['duration']!='DURATION_UNKNOWN' and f['raw_text'] and f['period_evidence'] and
               f['multiplier']==f['unit_evidence']['multiplier'] and f['source_sha256']==docs[f['id']]['sha256'])
        refs=[r for r in references if all(r[k]==f[k] for k in ['code','period','field','scope'])
              and r.get('duration')!='INSTANT_START' and r['announcement_date']<=f['announcement_date']]
        matches=[r for r in refs if abs(Decimal(f['value_CNY'])-Decimal(r['value_CNY']))<=
                 (Decimal(f['quantum_CNY'])+Decimal(r.get('quantum_CNY','0.01')))/2]
        matches=matches if basic else []
        comparisons.append({'candidate_index':i,'id':f['id'],'physical_page':f['physical_page'],
           'field':f['field'],'period':f['period'],'scope':f['scope'],'value_CNY':f['value_CNY'],
           'unit':f['unit'],'quantum_CNY':f['quantum_CNY'],
           'status':'VERIFIED_PRIOR_FACT_CORROBORATION' if matches else
                    'DIFFERENT_SUBJECT_EXCLUDED' if f['scope']=='parent' else
                    'UNKNOWN_SCOPE' if f['scope']=='unknown' else 'UNVERIFIED_NOT_ACCEPTED',
           'references':[{'id':r['id'],'physical_page':r['physical_page'],'value_CNY':r['value_CNY'],
                         'source_sha256':r['source_sha256'],'column':r['column']} for r in matches],
           'creates_new_revision':False,'whole_document_equivalence':False})
    reviews=read(OUT/'source_reviews.json')['reviews']
    assert {r['id'] for r in reviews}==set(docs)=={r['id'] for r in read(OUT/'preregistration.json')['sources']}
    outputs=[]
    for review in reviews:
        d=docs[review['id']]
        assert hashlib.sha256((ROOT/d['path']).read_bytes()).hexdigest()==d['sha256']==review['source_sha256']
        text=read(OUT/'text'/f"{d['id']}.json")
        proof=[p for p in text['pages'] if p['physical_page'] in review['source_pages']]
        c=[v for v in comparisons if v['id']==d['id']]
        known={v['field'] for v in c if v['status']=='VERIFIED_PRIOR_FACT_CORROBORATION' and v['period']==review['primary_target_period']}
        if review['status'] in ('VERIFIED_DUPLICATE_OF_EXISTING_DISCLOSURE','DIFFERENT_ACCOUNTING_BASIS'):
            assert set(review['fields_compared'])<=known, (d['id'],known)
        ocr=[]
        for p in text['pages']:
            fn=OUT/'ocr'/f"{d['id']}-p{p['physical_page']}.json"
            if fn.exists():
                o=read(fn);ocr.append({'page':p['physical_page'],'text':o['text'],'image_sha256':o['image_sha256']})
        if review['status']=='VERIFIED_NO_TARGET_FIELD_EFFECT':
            all_text=base.compact(''.join(p['text'] for p in text['pages'])+''.join(o['text'] for o in ocr))
            assert '问题1' in all_text and all(s in all_text for s in ['债务','预售资金','教育','产业政策'])
            assert not re.search(r'问题[2-9]|归属于母公司|归属于上市公司|经营活动产生的现金流量净额',all_text)
            assert not c
        outputs.append({**review,'path':d['path'],'bytes':d['bytes'],'page_count':len(text['pages']),
           'whole_pdf_text_scanned':True,'ocr_pages':ocr,'source_page_text':proof,'money_comparisons':c,
           'classification_origin':'Bounded body-scope review + executable identity/field/period/unit comparisons; not title-only classification',
           'resolved':review['status']!='UNRESOLVED_REQUIRES_EVIDENCE'})
    # Keep genuine source-internal inconsistency distinct from parser errors.
    inconsistencies=[]
    for sid in docs:
        p=read(OUT/'text'/f'{sid}.json')['pages']
        variants=[]
        for page in p:
            tx=base.compact(page['text'])
            if '1,677,198.08万元' in tx:
                at=tx.index('1,677,198.08万元')
                variants.append({'physical_page':page['physical_page'],'context':tx[max(0,at-100):at+80]})
        if variants:inconsistencies.append({'id':sid,'period':'2021-12-31','field':'OCF','source_contexts':variants,
              'comparison':'Other table/prospectus says 1,677,198.05 万元; 300 CNY difference. No silent correction or inferred restatement.',
              'status':'UNRESOLVED_SOURCE_INTERNAL_TEXT_INCONSISTENCY','not_auto_revision_event':True})
    counts=dict(Counter(r['status'] for r in outputs))
    save('source_qualification.json',{'denominator':23,'counts':counts,'resolved':sum(r['resolved'] for r in outputs),
        'reviews':outputs,'facts':comparisons,'candidate_denominator':len(facts),
        'candidate_counts':dict(Counter(c['status'] for c in comparisons)),
        'source_internal_inconsistencies':inconsistencies,'new_verified_revision_events':[],
        'known_revision_events_unchanged':True,'unknown_revision_recall':'NOT_ESTABLISHED',
        'machine_seconds':time.perf_counter()-t})
    print({'file_counts':counts,'facts':len(facts),'fact_counts':dict(Counter(c['status'] for c in comparisons)),
           'truth_counts':dict(Counter(c['status'] for c in scored))})

if __name__=='__main__':main()
