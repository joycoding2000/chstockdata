"""Automatic labels from actual parsed version differences, independent of titles."""
from collections import defaultdict
from decimal import Decimal
from acquire import OUT, read, save


def main():
    ev = read(OUT/'version_evidence_f2.json')
    docs = read(OUT/'dataset_legacy.json')['documents']+read(OUT/'new_documents.json')
    by_id = {d['id']:d for d in docs}
    groups = defaultdict(list)
    for r in ev['paired_columns']:
        groups[(r['id'],r['period'])].append(r)
    eps = [f for d in read(OUT/'auxiliary_evidence.json')['eps'] for f in d['facts']]
    labels = []
    for (id_,period),rows in groups.items():
        fields = {r['field']:r for r in rows}
        e = {f['column']:f for f in eps if f['id']==id_ and f['period']==period}
        eps_changed = ('adjusted' in e and 'unadjusted' in e and
                       Decimal(e['adjusted']['value_per_share'])!=Decimal(e['unadjusted']['value_per_share']))
        full = set(fields)=={'NP','OCF','EQ'}
        monetary_changed = any(r['changed'] for r in rows)
        labels.append({'id':id_,'code':by_id[id_]['code'],'period':period,
            'monetary_fields_checked':sorted(fields),'monetary_changed':monetary_changed,
            'eps_changed':eps_changed,'classification':
                'EPS_ONLY_IN_THREE_TESTED_MONETARY_FIELDS' if full and eps_changed and not monetary_changed else
                'MONETARY_COMPARATIVE_REVISION' if monetary_changed else 'PARTIAL_OR_UNCHANGED_COMPARATIVES',
            'earliest_revision_date_established':False})
    updates = []
    for code,period in sorted({(d['code'],d['period']) for d in docs if d['kind']=='periodic'}):
        versions = sorted([d for d in docs if d['kind']=='periodic' and d['code']==code and d['period']==period],
                          key=lambda d:(d['date'],d['id']))
        for a,b in zip(versions,versions[1:]):
            # An intervening quarter's comparative may sit between these two
            # files in the chronological ledger. Compare the actual pair directly.
            rows = []
            for field in ['NP','OCF','EQ']:
                left = next((f for f in ev['ledger'] if f['id']==a['id'] and f['period']==period and f['field']==field),None)
                right = next((f for f in ev['ledger'] if f['id']==b['id'] and f['period']==period and f['field']==field),None)
                if left and right:
                    rows.append({'field':field,'before':left['value_CNY'],'after':right['value_CNY'],
                        'source_pages':[left['physical_page'],right['physical_page']],
                        'changed':Decimal(left['value_CNY'])!=Decimal(right['value_CNY'])})
            updates.append({'code':code,'period':period,'original':a['id'],'updated':b['id'],
                'different_sha':a['sha256']!=b['sha256'],
                'fields':rows,'classification':'NO_CHANGE_IN_THREE_TESTED_MONETARY_FIELDS'
                if {r['field'] for r in rows}=={'NP','OCF','EQ'} and not any(r['changed'] for r in rows)
                else 'MONETARY_CHANGE_OR_INCOMPLETE_FIELDS'})
    ordinary = [r for r in ev['cross_document_transitions'] if r['changed'] and
                not any(t in by_id[r['second_id']]['title'] for t in ['更正','修订','更新'])]
    save('event_qualification.json',{'comparative_events':labels,'document_updates':updates,
        'changes_in_ordinary_report_titles':ordinary,'unknown_revision_recall':'NOT_ESTABLISHED'})
    assert any(r['classification']=='EPS_ONLY_IN_THREE_TESTED_MONETARY_FIELDS' for r in labels)
    assert any(r['classification']=='NO_CHANGE_IN_THREE_TESTED_MONETARY_FIELDS' for r in updates)
    assert ordinary
    print({'comparative_events':len(labels),'document_updates':len(updates),
           'changed_transitions_without_correction_title':len(ordinary)})


if __name__ == '__main__':
    main()
