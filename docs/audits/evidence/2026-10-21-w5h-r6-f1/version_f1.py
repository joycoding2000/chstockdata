"""Known-document version ordering, never a claim of complete announcement recall."""
import html
import hashlib
import json
import re
import struct
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from parser_f1 import compact, unique_value

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
R5 = OUT.parent / '2026-10-20-w5h-r5'
R4 = OUT.parent / '2026-10-20-w5h-r4'
RULE = 'DATE_ONLY_NEXT_OBSERVED_SH_INDEX_SESSION_CLOSE_NOT_OWNER_FROZEN'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def report_period(title):
    t = compact(html.unescape(re.sub('<[^>]*>', '', title)))
    m = re.search(r'(20\d{2})年?(年度|第一季度|一季度|半年度|第三季度|三季度)报告', t)
    if not m or any(x in t for x in ['摘要', '英文', 'H股', '督导', '核查']):
        return None
    return m[1] + {'年度': '-12-31', '第一季度': '-03-31', '一季度': '-03-31',
                   '半年度': '-06-30', '第三季度': '-09-30', '三季度': '-09-30'}[m[2]]


def catalog(documents):
    rows = {}
    for code in sorted({d['code'] for d in documents}):
        if not (R5 / f'{code}_periodic_index.json').is_file():
            queries = [x['records'] for x in read(R4 / 'cninfo_index_summary.json').values()]
        else:
            queries = [read(R5 / f'{code}_{k}_index.json').get('announcements') or []
                       for k in ['periodic', 'correction', 'supplement']]
        for result in queries:
            for row in result:
                if row.get('secCode', code) != code:
                    continue
                title = html.unescape(re.sub('<[^>]*>', '', row['announcementTitle']))
                rows[row['announcementId']] = {'id': row['announcementId'], 'code': code,
                    'title': title, 'date': row['adjunctUrl'].split('/')[1],
                    'period': report_period(title), 'body_obtained': row['announcementId'] in
                        {d['id'] for d in documents}}
    return list(rows.values())


def calendar():
    b = (ROOT / '.rh3a2-vipdoc/sh/lday/sh000001.day').read_bytes()
    return sorted({f'{v//10000:04d}-{v//100%100:02d}-{v%100:02d}'
                   for i in range(0, len(b), 32)
                   if (v := struct.unpack_from('<I', b, i)[0]) >= 19900101})


def available(date, sessions):
    return next((s for s in sessions if s > date), None)


def build_ledger(facts, documents, sessions):
    docs = {d['id']: d for d in documents}
    ledger = []
    for f in facts:
        # "Before adjustment" in a future document is evidence of a difference,
        # never a separately obtained original version at an earlier historical T.
        if f['scope'] != 'consolidated' or f['mode'] != 'summary' or f['column'] == 'unadjusted':
            continue
        d = docs[f['id']]
        ledger.append({**f, 'source_report_period': d['period'],
                       'available_on': available(d['date'], sessions),
                       'version_identity': f"{f['id']}:{f['source_sha256']}:{f['period']}:{f['column']}",
                       'complete_historical_pit_qualified': False})
    return sorted(ledger, key=lambda f: (f['code'], f['period'], f['announcement_date'], f['id'], f['field']))


def select(ledger, rows, sessions, code, period, field, T, mode='strict_saved_catalog'):
    eligible = [f for f in ledger if f['code'] == code and f['period'] == period and
                f['field'] == field and f.get('available_on') and f['available_on'] <= T]
    base = {'code': code, 'period': period, 'field': field, 'T': T, 'mode': mode,
            'availability_rule': RULE, 'unknown_revision_recall': 'NOT_ESTABLISHED',
            'complete_historical_pit_qualified': False}
    if not eligible:
        return {**base, 'status': 'UNKNOWN', 'value_CNY': None, 'reason': 'NO_ELIGIBLE_ORIGINAL_OR_VERSION'}
    date = max(f['announcement_date'] for f in eligible)
    latest = [f for f in eligible if f['announcement_date'] == date]
    chosen = unique_value(latest)
    if chosen['status'] == 'UNKNOWN':
        return {**base, 'status': 'UNKNOWN', 'value_CNY': None,
                'reason': 'SOURCE_VERSION_CONFLICT', 'conflicting_candidates': latest}
    # A later same-period document update does not close an intervening newer
    # financial report. A later financial period provides a new positive anchor,
    # but never proves the first date on which that revision became known.
    gaps = [r for r in rows if r['code'] == code and r['period'] and not r['body_obtained'] and
            available(r['date'], sessions) and available(r['date'], sessions) <= T and
            (r['period'] > chosen['source_report_period'] or
             r['period'] == chosen['source_report_period'] and r['date'] > chosen['announcement_date'])]
    if gaps and mode == 'strict_saved_catalog':
        return {**base, 'status': 'UNKNOWN', 'value_CNY': None,
                'reason': 'KNOWN_MISSING_INTERVENING_REPORT', 'gaps': gaps,
                'excluded_known_candidate_id': chosen['id']}
    return {**base, 'status': 'SELECTED_BOUNDED', 'value_CNY': chosen['value_CNY'],
            'source_id': chosen['id'], 'source_sha256': chosen['source_sha256'],
            'physical_page': chosen['physical_page'], 'raw_text': chosen['raw_text'],
            'unit': chosen['unit'], 'multiplier': chosen['multiplier'],
            'announcement_date': chosen['announcement_date'], 'available_on': chosen['available_on'],
            'version_identity': chosen['version_identity'], 'known_catalog_gaps': gaps,
            'reason': 'KNOWN_LEDGER_DEMONSTRATION_ONLY' if mode == 'known_ledger_only' else
                      'POSITIVE_SOURCE_ANCHOR_CONDITIONAL_ON_SAVED_CATALOGS'}


def differences(facts, documents):
    groups = defaultdict(dict)
    for f in facts:
        if f['mode'] == 'summary' and f['scope'] == 'consolidated':
            groups[(f['id'], f['period'], f['field'])][f['column']] = f
    comparisons = []
    for (id_, period, field), cols in groups.items():
        if 'adjusted' in cols and 'unadjusted' in cols:
            a, b = cols['unadjusted'], cols['adjusted']
            comparisons.append({'id': id_, 'code': a['code'], 'period': period, 'field': field,
                'before': a['value_CNY'], 'after': b['value_CNY'],
                'changed': Decimal(a['value_CNY']) != Decimal(b['value_CNY']),
                'from_actual_columns_not_title': True})
    pairs = []
    by_period = defaultdict(list)
    for d in documents:
        if d['kind'] == 'periodic':
            by_period[(d['code'], d['period'])].append(d)
    for (code, period), docs in by_period.items():
        ordered = sorted(docs, key=lambda d: (d['date'], d['id']))
        for a, b in zip(ordered, ordered[1:]):
            checks = []
            for f in ['NP', 'OCF', 'EQ']:
                av = groups.get((a['id'], period, f), {}).get('current')
                bv = groups.get((b['id'], period, f), {}).get('current')
                checks.append({'field': f, 'before': av['value_CNY'] if av else None,
                               'after': bv['value_CNY'] if bv else None,
                               'status': 'UNKNOWN' if not av or not bv else
                               'CHANGED' if Decimal(av['value_CNY']) != Decimal(bv['value_CNY']) else 'UNCHANGED'})
            pairs.append({'code': code, 'period': period, 'first': a['id'], 'second': b['id'],
                          'different_document_sha': a['sha256'] != b['sha256'], 'fields': checks})
    changes = []
    by_fact = defaultdict(list)
    for f in facts:
        if f['mode'] == 'summary' and f['scope'] == 'consolidated' and f['column'] != 'unadjusted':
            by_fact[(f['code'], f['period'], f['field'])].append(f)
    for (code, period, field), versions in by_fact.items():
        versions.sort(key=lambda f: (f['announcement_date'], f['id']))
        for a, b in zip(versions, versions[1:]):
            if a['id'] == b['id']:
                continue
            changes.append({'code': code, 'period': period, 'field': field,
                            'first_id': a['id'], 'second_id': b['id'],
                            'before': a['value_CNY'], 'after': b['value_CNY'],
                            'changed': Decimal(a['value_CNY']) != Decimal(b['value_CNY']),
                            'earliest_revision_date_established': False})
    return comparisons, pairs, changes


def notice_scopes(documents):
    import pdfplumber
    results = []
    for d in documents:
        if d['kind'] != 'notice':
            continue
        with pdfplumber.open(ROOT / d['path']) as doc:
            texts = [p.extract_text() or '' for p in doc.pages]
        text = compact(''.join(texts))
        if not text:
            status = 'UNKNOWN_NO_TEXT_LAYER'
        elif '董事' in text and ('简历' in text or '任职资格' in text):
            status = 'GOVERNANCE_CANDIDATE_NO_TARGET_AMOUNT_REPLACEMENT'
        elif '处罚及整改' in text and ('其他' in text or '其余' in text) and '不变' in text:
            status = 'LIMITED_NARRATIVE_UPDATE_NO_TARGET_AMOUNT_REPLACEMENT'
        else:
            status = 'SCOPE_UNKNOWN_NO_AUTOMATIC_REPLACEMENT'
        results.append({'id': d['id'], 'source_sha256': d['sha256'], 'status': status,
                        'pages': [{'physical_page': i+1, 'raw_text': t} for i, t in enumerate(texts)],
                        'new_monetary_events': 0, 'no_monetary_event_is_not_complete_semantic_clearance': True})
    return results


def main():
    documents = read(OUT / 'dataset.json')['documents']
    certified = read(OUT / 'certified_facts.json')
    assert certified['parsed_sha256'] == hashlib.sha256((OUT/'parsed.json').read_bytes()).hexdigest()
    assert certified['whole_batch_has_zero_incorrect_accepted_values']
    facts = certified['facts']
    sessions = calendar()
    rows = catalog(documents)
    id_rows = {r['id']: r for r in rows}
    identity_checks = [{'id': d['id'], 'matches': d['id'] in id_rows and
                        id_rows[d['id']]['code'] == d['code'] and
                        id_rows[d['id']]['date'] == d['date']}
                       for d in documents]
    assert all(c['matches'] for c in identity_checks)
    ledger = build_ledger(facts, documents, sessions)
    comp, pairs, changes = differences(facts, documents)
    payload = {'availability_rule': RULE, 'catalog_denominator': len(rows), 'catalog': rows,
               'identity_checks': identity_checks, 'ledger': ledger,
               'comparative_differences': comp, 'same_period_versions': pairs,
               'cross_document_versions': changes,
               'notice_scopes': notice_scopes(documents), 'unknown_revision_recall': 'NOT_ESTABLISHED',
               'full_history_gate': 'NOT_PASSED'}
    (OUT / 'version_evidence.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    # Test expectations are read only after the actual ledger has been generated.
    tests = read(OUT / 'replay_expected.json')['cases']
    values = {(v['test'], v['field']): v for v in read(OUT / 'replay_value_truth.json')['cases']}
    results = []
    for c in tests:
        for field in c.get('fields', ['NP', 'OCF', 'EQ']):
            got = select(ledger, rows, sessions, c['code'], c['period'], field, c['T'], c['mode'])
            ok = got['status'] == c['expected_status'] and (
                'expected_id' not in c or got.get('source_id') == c['expected_id'])
            expected_value = values[(c['name'], field)]['expected_value_CNY']
            ok = ok and (got['value_CNY'] is None if expected_value is None else
                         got['value_CNY'] is not None and Decimal(got['value_CNY']) == Decimal(expected_value))
            results.append({'test': c['name'], 'field': field, 'expected': c, 'actual': got,
                            'independent_expected_value_CNY': expected_value,
                            'assertion': 'PASS' if ok else 'FAIL'})
    (OUT / 'replay_validation.json').write_text(json.dumps({
        'case_denominator': len(tests), 'field_output_denominator': len(results),
        'assertion_pass': sum(r['assertion'] == 'PASS' for r in results), 'results': results,
        'complete_historical_pit_qualified': False,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ledger_facts': len(ledger), 'catalog': len(rows), 'paired_comparatives': len(comp),
                      'changed_fields': sum(r['changed'] for r in comp),
                      'replay_pass': sum(r['assertion'] == 'PASS' for r in results),
                      'replay_denominator': len(results)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
