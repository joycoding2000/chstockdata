"""Connect field/period dispositions to the preserved source-aware PIT selector."""
import copy
import sys
from collections import Counter
from decimal import Decimal
from common import HERE, ROOT, OLD, F2, SCANS, REPLIES, read, save
from qualification_rules import conflict_affects_query

sys.path.insert(0,str(OLD))
import replay_closure as previous


def reviews_for_query(reviews, records, query):
    out=copy.deepcopy(reviews)
    for row in out:
        if row['id'] not in SCANS+REPLIES:continue
        if row['id']=='1218110511':row['resolved']=True;continue
        relevant=[r for r in records if r['document_id']==row['id'] and
                  r['affected_period']==query['period'] and r['affected_field']==query['field'] and
                  r['accounting_scope']=='consolidated']
        row['resolved']=not any(r['qualification_status'] in ('UNRESOLVED_MATERIAL','UNRESOLVED_NON_MATERIAL_FOR_FIXED_T') for r in relevant)
        row['period_scoped_resolution']=True
    return out


def select(ledger,reviews,records,conflicts,discovery,notices,sessions,query,windows):
    blocked=[c for c in conflicts if conflict_affects_query(c,query)]
    if blocked:
        return {**query,'status':'UNKNOWN','value_CNY':None,'reason':'UNRESOLVED_REQUIRED_FY2021_OCF_SOURCE_CONFLICT',
                'conflict_documents':[c['id']for c in blocked],'historical_pit_qualified':False}
    scoped_reviews=reviews_for_query(reviews,records,query)
    got=previous.select(ledger,scoped_reviews,discovery,notices,sessions,query,windows)
    if got['status']=='UNKNOWN' and got.get('reason')=='INTERVAL_OUTSIDE_FIXED_INDEX_COVERAGE':
        # An independent coverage refusal must not hide simultaneous named
        # material evidence gaps. Add diagnosis without changing refusal/value.
        known=previous.previous.select(ledger,discovery,notices,sessions,{**query,'mode':'known_documents'},windows)
        if known['status']=='SELECTED_KNOWN_SOURCE':
            gaps=previous.blockers(scoped_reviews,query,known['announcement_date'],known['source_id'],sessions)
            got['gaps']=[r['id']for r in gaps]
            got['additional_gap_reason']='NAMED_SOURCE_GAPS_RETAINED_ALONGSIDE_INDEX_COVERAGE_REFUSAL'
    got['qualification_basis']='PER_DOCUMENT_FIELD_PERIOD_DISPOSITIONS; NOT_WHOLE_DOCUMENT_BLANKET_CLEARANCE'
    return got


def main():
    qual=read(HERE/'final_source_qualification.json');records=qual['records']
    frozen=read(OLD/'source_aware_ledger.json');ledger=frozen['ledger']
    assert len(ledger)==127 and not qual['new_financial_facts']
    reviews=read(OLD/'source_qualification.json')['reviews']
    discovery=read(F2/'discovery_classification.json')['rows'];notices=read(F2/'auxiliary_evidence.json')['notices']
    sessions=previous.calendar();windows=read(F2/'preregistration.json')['windows']
    scopes=read(HERE/'reply_scope_qualification.json')
    conflicts=[{**c,'available_on':previous.available(c['date'],sessions)}for c in scopes['conflicts']]
    queries=read(F2/'replay_queries_f2.json')+read(OLD/'closure_queries.json')
    run=lambda q:select(ledger,reviews,records,conflicts,discovery,notices,sessions,q,windows)
    outputs=[run(q)for q in queries]
    old={q['query_id']:q for q in read(OLD/'closure_replay_results.json')}
    deltas=[]
    for out in outputs:
        was=old[out['query_id']]
        if (was['status'],was.get('value_CNY'))!=(out['status'],out.get('value_CNY')):
            deltas.append({'query_id':out['query_id'],'before':was,'after':out})
        if out['status']=='SELECTED_KNOWN_SOURCE':
            assert previous.available(out['announcement_date'],sessions)<=out['T']
            assert any(r['id']==out['source_id'] and r['code']==out['code'] and r['period']==out['period'] and
                       r['field']==out['field'] and Decimal(r['value_CNY'])==Decimal(out['value_CNY']) for r in ledger)
    # Explicit expected values live in the test fixture, never in selection.
    expected={'scan_V_Q1_NP':'1445811341.87','scan_Z_Q1_NP':'-665649652.02','scan_Z_H1_NP':'-798112292.31'}
    new=[]
    for qid,code,per,T in [('scan_V_Q1_NP','000002','2023-03-31','2023-05-23'),
                           ('scan_Z_Q1_NP','000961','2023-03-31','2023-06-19'),
                           ('scan_Z_H1_NP','000961','2023-06-30','2023-09-27')]:
        q={'query_id':qid,'code':code,'period':per,'field':'NP','T':T,'mode':'strict_index'}
        got=run(q);ok=got['status']=='SELECTED_KNOWN_SOURCE' and Decimal(got['value_CNY'])==Decimal(expected[qid])
        new.append({'query':q,'expected_status':'SELECTED_KNOWN_SOURCE','expected_value_CNY':expected[qid],'actual':got,'pass':ok})
    unique={}
    for r in records:
        if r['qualification_status']=='UNRESOLVED_MATERIAL':
            unique[(r['document_id'],r['affected_period'],r['affected_field'])]=r
    for (sid,per,field),r in unique.items():
        q={'query_id':'gap_'+sid+'_'+per+'_'+field,'code':r['affected_security'],'period':per,'field':field,
           'T':previous.available(r['disclosure_date'],sessions),'mode':'strict_index'}
        got=run(q)
        new.append({'query':q,'expected_status':'UNKNOWN','expected_named_gap':sid,'actual':got,
                    'pass':got['status']=='UNKNOWN' and sid in got.get('gaps',[])})
    dependency=[]
    for c in conflicts:
        q={'query_id':'dep_'+c['id'],'code':c['code'],'field':'OCF','period':'2022-12-31',
           'T':c['available_on'],'required_dependencies':[{'field':'OCF','period':'2021-12-31'}]}
        got=run(q)
        dependency.append({'id':c['id'],'query':q,'pass':got['status']=='UNKNOWN' and c['id']in got.get('conflict_documents',[]),
                           'actual':got,'expected':'UNKNOWN_IF_REQUIRED_BASE_DEPENDENCY'})
        q2={k:v for k,v in q.items()if k!='required_dependencies'}
        dependency.append({'id':c['id'],'query':q2,'pass':not conflict_affects_query(c,q2),
                           'expected':'NO_BLOCK_FROM_UNREQUESTED_2021_OCF_DEPENDENCY; OTHER_GAPS_STILL_APPLY'})
    allpass=all(r['pass']for r in new+dependency)
    save('source_aware_ledger_final.json',{'ledger':ledger,'ledger_denominator':127,
         'existing_ledger_byte_values_and_vintage_dates_preserved':ledger==frozen['ledger'],
         'new_financial_facts':[],'source_field_dispositions':records,
         'source_conflicts':conflicts,'no_backdated_corroborations':True,'unknown_revision_recall':'NOT_ESTABLISHED',
         'historical_pit_qualified':False})
    save('final_replay_results.json',outputs+[r['actual']for r in new])
    save('final_replay_validation.json',{'preserved_query_denominator':len(queries),'status_counts':dict(Counter(r['status']for r in outputs)),
         'query_status_or_value_changes':deltas,'new_real_source_assertions':new,'dependency_assertions':dependency,
         'new_assertion_denominator':len(new)+len(dependency),'new_assertions_passed':sum(r['pass']for r in new+dependency),
         'pass':allpass,'date_rule':previous.RULE,'product_date_rule_owner_frozen':False,
         'legacy_23_assertions_reexecuted_independently':'regression/closure/closure_replay_validation.json',
         'unknown_revision_recall':'NOT_ESTABLISHED','no_new_versions_is_not_100_percent_recall':True})
    print({'preserved_outputs':len(outputs),'counts':dict(Counter(r['status']for r in outputs)),
           'deltas':len(deltas),'new_assertions':len(new)+len(dependency),'pass':allpass})
    assert allpass


if __name__=='__main__':main()
