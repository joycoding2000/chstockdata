"""Finite source-aware replay. No expected amounts or network access."""
import hashlib,sys
from collections import Counter
from fetch_named import OUT,ROOT,F2,read,save
sys.path.insert(0,str(F2))
import version_f2 as previous
from version_legacy import calendar,available,RULE

CLEAR_NOTICES={'GOVERNANCE_NO_NUMERIC_REPLACEMENT','LIMITED_NARRATIVE_UPDATE_NO_NUMERIC_REPLACEMENT','REGULATORY_REQUEST_NO_ISSUER_LEVEL_REPLACEMENT'}


def blockers(reviews,query,date,source_id,sessions):
    # Same-date unresolved companion is not cleared merely by a positive file.
    return [r for r in reviews if not r['resolved'] and r['code']==query['code'] and
        query['field'] in r['blocked_fields'] and r['date']>=date and r['id']!=source_id and
        available(r['date'],sessions) and available(r['date'],sessions)<=query['T']]


def select(ledger,reviews,discovery,notices,sessions,query,windows):
    got=previous.select(ledger,discovery,notices,sessions,{**query,'mode':'known_documents'},windows)
    got['mode']=query.get('mode','strict_index')
    got['scope_limit']='Fixed saved index and qualified field-level dispositions; no complete discovery claim'
    if got['status']=='UNKNOWN':return got
    date=got['announcement_date']
    gaps=blockers(reviews,query,date,got['source_id'],sessions)
    unlisted=[r for r in discovery if r['required_candidate'] and not r['body_obtained'] and
              r['id'] not in {v['id'] for v in reviews} and r['code']==query['code'] and date<r['date'] and
              available(r['date'],sessions) and available(r['date'],sessions)<=query['T']]
    legacy=[r for r in notices if r['code']==query['code'] and date<r['date'] and
              available(r['date'],sessions) and available(r['date'],sessions)<=query['T'] and r['status'] not in CLEAR_NOTICES]
    got['named_source_gaps']=[r['id'] for r in gaps]
    got['known_source_gaps']=[r['id'] for r in gaps+unlisted]
    if got['mode']=='strict_index':
        w=next(w for w in windows if w['code']==query['code'])
        if query['T']!=got['available_on'] and (query['T']<w['start'] or query['T']>w['end'] or date<w['start']):
            return {**query,'status':'UNKNOWN','value_CNY':None,'reason':'INTERVAL_OUTSIDE_FIXED_INDEX_COVERAGE','historical_pit_qualified':False}
        if gaps or unlisted or legacy:
            return {**query,'status':'UNKNOWN','value_CNY':None,'reason':'UNQUALIFIED_SOURCE_OR_INHERITED_NOTICE',
                'blocked_fields':query['field'],'gaps':[r['id'] for r in gaps+unlisted],
                'inherited_notices':[r['id'] for r in legacy],'excluded_known_source':got['source_id'],
                'historical_pit_qualified':False,'availability_rule':RULE,'unknown_revision_recall':'NOT_ESTABLISHED'}
    got['reason']='POSITIVE_CERTIFIED_VERSION_WITH_NAMED_SOURCE_DISPOSITIONS' if got['mode']=='strict_index' else 'KNOWN_DOCUMENTS_ONLY_NOT_COMPLETE_PIT'
    return got


def main():
    qual=read(OUT/'source_qualification.json')
    frozen=read(F2/'version_evidence_f2.json')
    ledger=frozen['ledger']
    # New material provides corroborations or exclusions, not a certified new
    # monetary revision. Do not timestamp old-audit quotations as new revisions.
    assert not qual['new_verified_revision_events']
    for r in qual['reviews']:
        assert hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['source_sha256']
    save('source_aware_ledger.json',{'ledger':ledger,'ledger_denominator':len(ledger),
        'source_corroborations':[c for c in qual['facts'] if c['status']=='VERIFIED_PRIOR_FACT_CORROBORATION'],
        'rejected_unqualified_candidates':[c for c in qual['facts'] if c['status']!='VERIFIED_PRIOR_FACT_CORROBORATION'],
        'new_monetary_revision_events':[],'duplicate_quotes_do_not_change_existing_vintage_dates':True,
        'earliest_unknown_revision_date':'NOT_ESTABLISHED','historical_pit_qualified':False})
    discovery=read(F2/'discovery_classification.json')['rows']
    notices=read(F2/'auxiliary_evidence.json')['notices']
    sessions=calendar();windows=read(F2/'preregistration.json')['windows']
    queries=read(F2/'replay_queries_f2.json')
    # The expected fixture is only used below after program results exist.
    new_queries=read(OUT/'closure_queries.json')
    outputs=[select(ledger,qual['reviews'],discovery,notices,sessions,q,windows) for q in queries+new_queries]
    save('closure_replay_results.json',outputs)
    by_id={r['query_id']:r for r in outputs}
    scored=[]
    from decimal import Decimal
    for c in read(OUT/'expected_closure_replay.json')['cases']:
        r=by_id[c['query_id']]
        ok=r['status']==c['status'] and (r['value_CNY'] is None and c['value_CNY'] is None or
            r['value_CNY'] is not None and c['value_CNY'] is not None and Decimal(r['value_CNY'])==Decimal(c['value_CNY']))
        scored.append({'query_id':c['query_id'],'status':'PASS' if ok else 'FAIL','expected':c,'actual':r})
    old={r['query_id']:r for r in read(F2/'replay_results_f2.json')}
    changes=[]
    for q in queries:
        before,after=old[q['query_id']],by_id[q['query_id']]
        changed=before['status']!=after['status'] or before.get('value_CNY')!=after.get('value_CNY')
        if changed:changes.append({'query_id':q['query_id'],'before':before,'after':after})
        if before['status']==after['status']=='SELECTED_KNOWN_SOURCE':
            assert Decimal(before['value_CNY'])==Decimal(after['value_CNY']), 'Corroboration changed a certified version'
    save('closure_replay_validation.json',{'new_assertion_denominator':len(scored),'counts':dict(Counter(c['status'] for c in scored)),
        'cases':scored,'existing_query_denominator':len(queries),'existing_query_status_changes':changes,
        'all_output_denominator':len(outputs),'status_counts':dict(Counter(r['status'] for r in outputs)),
        'unknown_revision_recall':'NOT_ESTABLISHED','frozen_f2_regression_denominators_unchanged':True})
    print({'new_assertions':len(scored),'counts':dict(Counter(c['status'] for c in scored)),
           'old_status_changes':len(changes),'all_outputs':dict(Counter(r['status'] for r in outputs))})
    assert all(c['status']=='PASS' for c in scored)

if __name__=='__main__':main()
