"""Explicitly map each source disposition to actual tested historical T results."""
from collections import Counter
from common import HERE, read, save
from replay_final import previous


def main():
    qual=read(HERE/'final_source_qualification.json')
    outputs=read(HERE/'final_replay_results.json');sessions=previous.calendar()
    rows=[]
    for i,r in enumerate(qual['records']):
        fields=r['affected_field']if isinstance(r['affected_field'],list)else[r['affected_field']]
        available=previous.available(r['disclosure_date'],sessions)
        matches=[]
        if r['accounting_scope']!='parent':
            for q in outputs:
                if q['code']!=r['affected_security']or q['field']not in fields:continue
                if r['affected_period']!='NO_TARGET_FINANCIAL_PERIOD'and q['period']!=r['affected_period']:continue
                if q['T']<available:continue
                matches.append({'query_id':q['query_id'],'T':q['T'],'field':q['field'],'period':q['period'],
                                'status':q['status'],'value_CNY':q.get('value_CNY'),
                                'this_source_listed_as_blocker':r['document_id']in q.get('gaps',[]),
                                'source_id':q.get('source_id'),'reason':q.get('reason')})
        if r['qualification_status']=='UNRESOLVED_NON_MATERIAL_FOR_FIXED_T':assert not matches
        rows.append({'record_index':i,**{k:r[k]for k in ['document_id','affected_security','affected_period','affected_field',
                      'accounting_scope','source_version','disclosure_date','evidence_page','qualification_status','historical_T_impact']},
                     'candidate_available_on':available,'actual_matching_tested_T':matches,
                     'matching_tested_T_count':len(matches),
                     'no_matching_test_does_not_clear_product_warmup':True})
    save('field_T_impact.json',{'source_record_denominator':len(rows),'tested_output_denominator':len(outputs),
         'rows':rows,'all_output_status_counts':dict(Counter(q['status']for q in outputs)),
         'availability_rule':previous.RULE,'no_product_timing_policy_approval':True})
    print({'source_records':len(rows),'actual_outputs':len(outputs),'statuses':dict(Counter(q['status']for q in outputs))})


if __name__=='__main__':main()
