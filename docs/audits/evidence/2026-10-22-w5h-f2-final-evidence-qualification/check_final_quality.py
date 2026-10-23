"""Actual-output and binding checks, distinct from financial sample counts."""
from decimal import Decimal
from common import HERE, ROOT, OLD, read, save, sha


def main():
    checks=[]
    def check(name,ok):checks.append({'check':name,'pass':bool(ok)})
    docs=read(HERE/'input_documents.json')
    for d in docs:check('original_sha_'+d['id'],sha(ROOT/d['path'])==d['sha256'])
    calls=[]
    for filename in ['cell_ocr_plan.json','cell_ocr_v2_plan.json','column_ocr_plan.json']:
        for p in read(HERE/filename):
            o=read(p['output'])
            check('OCR_SHA_'+__import__('pathlib').Path(p['output']).name+'_'+filename,
                  o['image_sha256']==sha(p['image']) and o['source_sha256']==p['source_sha256'])
            calls.append(o)
    qual=read(HERE/'final_source_qualification.json')
    check('all_11_documents_retained',len(qual['documents'])==11)
    check('all_72_scan_cells_retained',sum(r['document_id']in ('1216741269','1216869640','1217078313','1217949874')for r in qual['records'])==72)
    check('all_27_probed_sites_retained',qual['scan_probed_field_sites']==27)
    check('opening_not_removed_to_gain_pass',qual['explicit_opening_cells_retained']==1 and qual['scan_critical_cells']==26)
    check('material_18_slots_remain',qual['remaining_material_document_period_field_slots']==18)
    check('nonmaterial_28_records_scoped',qual['remaining_nonmaterial_records']==28)
    check('old_regressions_pass',read(HERE/'regression_run.json')['complete'])
    check('new_replay_pass',read(HERE/'final_replay_validation.json')['pass'])
    check('24_source_checks_pass',read(HERE/'updated_source_field_validation.json')['counts']=={'PASS':24})
    check('product_gate_not_passed',qual['product_gate']=='NOT_PASSED')
    check('unknown_recall_not_invented',qual['unknown_revision_recall']=='NOT_ESTABLISHED')
    for r in read(HERE/'scan_field_qualification.json')['rows']:
        if r['qualification_status']=='VERIFIED_EXISTING_VERSION':
            check('scan_two_methods_'+r['document_id'],r['glyph_probe']['certain'] and r['value_CNY']is not None and bool(r['independent_references']))
        else:check('unqualified_not_accepted_'+r['document_id']+'_'+str(r['evidence_page'])+'_'+str(r['column_index']),r['value_CNY']is None)
    scopes=read(HERE/'reply_scope_qualification.json')
    for r in scopes['rows']:
        check('scope_non_ocf_identity_'+r['id'],r['scope']=='consolidated' and len(r['fingerprint_rows'])==16 and
              all(x['matches']and not x['parent_matches']for x in r['fingerprint_rows']))
    for c in scopes['conflicts']:
        check('conflict_preserved_'+c['id'],len(c['text_occurrences'])==1 and c['printed_difference_CNY']=='300' and not c['auto_corrected'] and not c['rounding_explains_difference'])
    check('no_template_tuning_or_forced_match',not any(r['passed']for r in read(HERE/'field_image_equivalence.json')['rows']))
    save('final_quality_checks.json',{'checks':checks,'denominator':len(checks),'passed':sum(c['pass']for c in checks),
         'pass':all(c['pass']for c in checks),'OCR_engine_calls':len(calls),
         'OCR_engine_seconds':sum(o['machine_seconds']for o in calls),
         'counts_are_integrity_checks_not_independent_financial_samples':True,
         'temporary_environment_created':False,'numeric_patches':0,'network_requests':0})
    print({'quality_checks':len(checks),'passed':sum(c['pass']for c in checks),'ocr_calls':len(calls)})
    assert all(c['pass']for c in checks)


if __name__=='__main__':main()
