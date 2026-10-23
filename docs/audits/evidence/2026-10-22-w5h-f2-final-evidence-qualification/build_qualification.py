"""Build per-document/period/field dispositions without discarding any probe cell."""
from collections import Counter
from decimal import Decimal
from common import HERE, OLD, F2, SCANS, REPLIES, read, save, statement_periods


def main():
    scans=read(HERE/'scan_field_qualification.json')['rows']
    scopes=read(HERE/'reply_scope_qualification.json')
    image=read(HERE/'image_identity_and_reply_scope.json')
    docs={d['id']:d for d in read(HERE/'input_documents.json')}
    fixed=read(F2/'replay_queries_f2.json')+read(OLD/'closure_queries.json')
    required={(q['code'],q['period'],q['field'])for q in fixed}
    records=[]
    for p in read(HERE/'repaired_scan_geometry.json'):
        sid,n,field=p['id'],p['physical_page'],p['field'];d=docs[sid]
        annual,current,prior=statement_periods(p)
        mixed=annual and sid!='1216869640'
        columns=[('consolidated',current),('parent',current),('consolidated',prior),('parent',prior)] if mixed else [('consolidated',current),('consolidated',prior)]
        for col,(scope,period) in enumerate(columns):
            existing=next((r for r in scans if r['document_id']==sid and r['evidence_page']==n and r['column_index']==col),None)
            base={'document_id':sid,'affected_security':d['code'],'affected_period':period,'affected_field':field,
                  'accounting_scope':scope,'source_version':sid+':'+('FY2022_AUDITED' if annual else 'H1_2023_UNAUDITED' if current.endswith('06-30') else 'Q1_2023_UNAUDITED'),
                  'disclosure_date':d['date'],'evidence_page':n,'column_index':col,
                  'source_sha256':d['sha256'],'unit':'元','multiplier':1}
            if existing:
                records.append({**base,**existing,'historical_T_impact':
                   'CORROBORATES_EXISTING_VERSION_FROM_OWN_DISCLOSURE_DATE_ONLY' if existing['qualification_status']=='VERIFIED_EXISTING_VERSION' else
                   'BLOCKS_THIS_FIELD_PERIOD_UNTIL_LATER_INDEPENDENT_POSITIVE_ANCHOR'})
                if existing['qualification_status']=='UNRESOLVED_NON_MATERIAL_FOR_FIXED_T':
                    assert (d['code'],period,field)not in required
                    records[-1].update(historical_T_impact='EXPLICIT_2023_OPENING_COLUMN; NOT_FY2022_ENDING; PRODUCT_ROE_DEPENDENCY_NOT_QUALIFIED',
                        dependency_proof={'matching_fixed_queries':0,'fixed_queries_checked':len(fixed),
                                          'no_derived_metrics_in_fixed_queries':True,'does_not_clear_product_TTM_ROE_dependencies':True})
            elif scope=='parent':
                records.append({**base,'qualification_status':'DIFFERENT_ACCOUNTING_BASIS',
                                'historical_T_impact':'EXCLUDED_FROM_CONSOLIDATED_LEDGER',
                                'NP_not_applicable_in_standalone_company_column':field=='NP'})
            else:
                assert (d['code'],period,field) not in required
                records.append({**base,'qualification_status':'UNRESOLVED_NON_MATERIAL_FOR_FIXED_T',
                                'historical_T_impact':'NO_FIXED_DIRECT_QUERY_DEPENDENCY; PRODUCT_WARMUP_NOT_QUALIFIED',
                                'dependency_proof':{'matching_fixed_queries':0,'fixed_queries_checked':len(fixed),
                                                   'no_derived_metrics_in_fixed_queries':True,
                                                   'does_not_clear_product_TTM_ROE_dependencies':True}})
    assert len(records)==72
    refs=[]
    for name in ['certified_facts.json','certified_new_facts.json']:refs+=read(F2/name)['facts']
    facts=read(OLD/'parsed_source_facts.json')['facts']
    updated=[];value_cases=[]
    for f in facts:
        anchor=next((r for r in scopes['rows'] if r['id']==f['id'] and r['evidence_page']==f['physical_page'] and r['scope']=='consolidated'),None)
        updated.append({**f,'scope':'consolidated','new_scope_proof':anchor['method']} if anchor and f['field']=='OCF' else f)
    for filename in ['expected_source_fields.json','expected_summary_columns.json','expected_dated_narrative.json','expected_annual_quote.json','expected_split_row.json']:
        for c in read(OLD/filename)['cases']:
            xs=[f for f in updated if all(f[k]==c[k]for k in ['id','field','period','physical_page'])]
            accepted=[f for f in xs if f['scope']==c['scope']]
            ok=bool(accepted) and all(Decimal(f['value_CNY'])==Decimal(c['value_CNY']) and f['multiplier']==c['multiplier']for f in accepted)
            value_cases.append({'expected':c,'actual':xs,'status':'PASS' if ok else 'UNKNOWN' if not accepted else 'FAIL'})
    assert len(value_cases)==24 and all(c['status']=='PASS'for c in value_cases)
    save('updated_source_field_validation.json',{'denominator':24,'counts':dict(Counter(c['status']for c in value_cases)),
         'cases':value_cases,'original_22_pass_2_unknown_result_preserved':True,'newly_closed_fields':2})
    for scope in scopes['rows']:
        sid=scope['id'];d=docs[sid]
        for field in ['NP','OCF']:
            xs=[f for f in updated if f['id']==sid and f['field']==field and f['period']=='2022-12-31' and f['scope']=='consolidated']
            assert xs
            if field=='OCF':assert len(xs)==1 and xs[0]['physical_page']==scope['evidence_page']
            references=[r for r in refs if r['code']==d['code'] and r['period']=='2022-12-31' and r['field']==field and
                        r['scope']=='consolidated' and r['announcement_date']<=d['date'] and
                        all(abs(Decimal(r['value_CNY'])-Decimal(f['value_CNY']))<=Decimal(f['quantum_CNY'])/2 for f in xs)]
            assert references
            records.append({'document_id':sid,'affected_security':d['code'],'affected_period':'2022-12-31',
                 'affected_field':field,'accounting_scope':'consolidated','source_version':sid+':REPLY_OF_EXISTING_FY2022',
                 'disclosure_date':d['date'],'evidence_page':sorted({f['physical_page']for f in xs}),
                 'qualification_status':'VERIFIED_EXISTING_VERSION','source_sha256':d['sha256'],
                 'historical_T_impact':'NO_NEW_VERSION_OR_BACKDATE; FY2022_FIELD_GAP_CLEARED_ONLY',
                 'reference_ids':sorted({r['id']for r in references}),
                 'source_values_CNY':sorted({f['value_CNY']for f in xs}),'source_precision_CNY':sorted({f['quantum_CNY']for f in xs}),
                 'scope_evidence':scope['method'] if field=='OCF' else 'EXPLICIT_ATTRIBUTABLE_TO_PARENT_NET_PROFIT_LABEL',
                 'audit_reference_identity':'NO_DIRECT_AUDIT_ID_QUOTE; INDEPENDENT_ORIGINAL_MATRIX_IDENTITY_FOR_OCF'})
        conflict=next(c for c in scopes['conflicts']if c['id']==sid)
        records.append({'document_id':sid,'affected_security':d['code'],'affected_period':'2021-12-31','affected_field':'OCF',
                        'accounting_scope':'consolidated','source_version':sid+':INTERNAL_TEXT_TABLE_CONFLICT',
                        'disclosure_date':d['date'],'evidence_page':[conflict['table_page'],conflict['text_occurrences'][0]['physical_page']],
                        'qualification_status':'UNRESOLVED_NON_MATERIAL_FOR_FIXED_T',
                        'historical_T_impact':'FAIL_CLOSED_IF_2021_OCF_IS_DIRECT_OR_DERIVED_DEPENDENCY; NO_MATCH_IN_141_FIXED_QUERIES',
                        'dependency_proof':{'matching_fixed_queries':sum(q['code']==d['code']and q['field']=='OCF'and q['period']=='2021-12-31'for q in fixed),
                                            'product_formula_and_warmup_dependencies_not_frozen':True},
                        'conflict_evidence':'reply_scope_qualification.json','not_resolved_globally':True})
    reply=image['reply'];sid=reply['document_id'];d=docs[sid]
    records.append({'document_id':sid,'affected_security':d['code'],'affected_period':'NO_TARGET_FINANCIAL_PERIOD',
         'affected_field':['NP','OCF','EQ'],'accounting_scope':'ISSUER_REPLY_NO_TARGET_FACT',
         'source_version':sid+':SECOND_ROUND_REPLY','disclosure_date':d['date'],'evidence_page':list(range(1,23)),
         'qualification_status':'VERIFIED_NO_TARGET_EFFECT','historical_T_impact':'REMOVES_THIS_COMPANION_ONLY; DOES_NOT_CLEAR_SEPTEMBER_STATEMENT_GAPS',
         'source_sha256':d['sha256']})
    material={(r['document_id'],r['affected_period'],r['affected_field'])for r in records if r['qualification_status']=='UNRESOLVED_MATERIAL'}
    nonmaterial=[r for r in records if r['qualification_status']=='UNRESOLVED_NON_MATERIAL_FOR_FIXED_T']
    documents=[]
    for sid,d in docs.items():
        rows=[r for r in records if r['document_id']==sid]
        documents.append({'document_id':sid,'affected_security':d['code'],'disclosure_date':d['date'],
             'status':'UNRESOLVED_MATERIAL' if any(r['qualification_status']=='UNRESOLVED_MATERIAL'for r in rows) else
                      'VERIFIED_NO_TARGET_EFFECT' if sid=='1218110511' else 'VERIFIED_EXISTING_VERSION',
             'material_field_period_gaps':sorted([list(k[1:])for k in material if k[0]==sid]),
             'nonmaterial_qualifications_do_not_clear_entire_document':True})
    save('final_source_qualification.json',{'document_denominator':11,'documents':documents,'records':records,
         'supported_qualification_statuses':['VERIFIED_EXISTING_VERSION','VERIFIED_NEW_FINANCIAL_FACT','VERIFIED_NO_TARGET_EFFECT',
            'DIFFERENT_ACCOUNTING_BASIS','UNRESOLVED_MATERIAL','UNRESOLVED_NON_MATERIAL_FOR_FIXED_T'],
         'record_denominator':len(records),'record_counts':dict(Counter(r['qualification_status']for r in records)),
         'scan_probed_field_sites':27,'scan_critical_cells':26,'scan_critical_accepted':3,'scan_critical_unresolved_cells':23,
         'explicit_opening_cells_retained':1,'no_probe_or_test_denominator_removed':True,
         'remaining_material_document_period_field_slots':len(material),'remaining_nonmaterial_records':len(nonmaterial),
         'nonmaterial_scan_comparative_cells':22,'nonmaterial_reply_conflicts':6,'parent_columns_excluded':24,
         'new_financial_facts':[],'earlier_versions_discovered':[],'unknown_revision_recall':'NOT_ESTABLISHED',
         'verdict':'FIXED_WINDOW_PARTIAL_WITH_PROVEN_GAPS','product_gate':'NOT_PASSED',
         'recognition_stop':'No further tuning after the finite image-equivalence counterfactual probe; current exact evidence is insufficient. No claim that saved originals are inherently unreadable or permanently manual.'})
    print({'records':len(records),'material_slots':len(material),'nonmaterial_records':len(nonmaterial),'document_counts':dict(Counter(d['status']for d in documents))})


if __name__=='__main__':main()
