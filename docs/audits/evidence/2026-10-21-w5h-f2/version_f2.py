"""Offline fixed-source version ledger and fail-closed replay; no expected amounts."""
import hashlib
from collections import defaultdict
from decimal import Decimal
from acquire import OUT, ROOT, read, save
from parser_f2 import unique_value
from version_legacy import calendar, available, RULE


def valid_fact(f, docs):
    d = docs.get(f.get('id'))
    return bool(d and f.get('code') == d['code'] and f.get('source_sha256') == d['sha256']
        and f.get('announcement_date') == d['date'] and f.get('source_path') == d['path']
        and f.get('scope') == 'consolidated' and f.get('mode') in ('summary','notice_adjustment')
        and f.get('field') in ('NP','OCF','EQ') and f.get('period') and d.get('period','9999') is not None
        and (not d.get('period') or f['period'] <= d['period']) and f.get('raw_text')
        and f.get('unit_evidence') and f.get('physical_page')
        and f.get('multiplier') == f['unit_evidence'].get('multiplier'))


def build_ledger(facts, documents, sessions):
    docs = {d['id']:d for d in documents}
    groups = defaultdict(list)
    rejected = []
    for f in facts:
        if not valid_fact(f,docs):
            rejected.append({'id':f.get('id'),'field':f.get('field'),'reason':'UNQUALIFIED_IDENTITY_SCOPE_UNIT_OR_PERIOD'})
            continue
        if f['column'] == 'unadjusted' or f['duration'] in ('SINGLE_QUARTER','INSTANT_START'):
            continue
        groups[(f['id'],f['period'],f['field'],f['duration'])].append(f)
    ledger = []
    for key, values in groups.items():
        got = unique_value(values)
        if got['status'] == 'UNKNOWN':
            rejected.append({'identity':key,'reason':got['reason']})
            continue
        d = docs[got['id']]
        ledger.append({**got,'available_on':available(d['date'],sessions),
            'version_identity':f"{got['id']}:{got['source_sha256']}:{got['period']}:{got['column']}",
            'source_report_period':d.get('period'), 'historical_pit_qualified':False})
    return sorted(ledger,key=lambda f:(f['code'],f['period'],f['announcement_date'],f['id'],f['field'])),rejected


def select(ledger, discovery, notices, sessions, query, windows=None):
    base = {**query,'availability_rule':RULE,'unknown_revision_recall':'NOT_ESTABLISHED',
            'historical_pit_qualified':False}
    eligible = [f for f in ledger if all(f[k]==query[k] for k in ('code','period','field'))
                and f['available_on'] and f['available_on'] <= query['T']]
    if not eligible:
        return {**base,'status':'UNKNOWN','value_CNY':None,'reason':'NO_ELIGIBLE_ORIGINAL_OR_VERSION'}
    date = max(f['announcement_date'] for f in eligible)
    latest = [f for f in eligible if f['announcement_date']==date]
    got = unique_value(latest)
    if got['status'] == 'UNKNOWN':
        return {**base,'status':'UNKNOWN','value_CNY':None,'reason':'SOURCE_VERSION_CONFLICT','candidates':latest}
    if windows is not None and query.get('mode','strict_index')=='strict_index':
        w = next(w for w in windows if w['code']==query['code'])
        point = query['T']==got['available_on']
        if not point and (query['T']<w['start'] or query['T']>w['end'] or date<w['start']):
            return {**base,'status':'UNKNOWN','value_CNY':None,'reason':'INTERVAL_OUTSIDE_FIXED_INDEX_COVERAGE'}
    gaps = [r for r in discovery if r['code']==query['code'] and r['required_candidate']
        and not r['body_obtained'] and date < r['date'] and available(r['date'],sessions)
        and available(r['date'],sessions) <= query['T']]
    unresolved = [r for r in notices if r['code']==query['code'] and date < r['date']
        and available(r['date'],sessions) and available(r['date'],sessions)<=query['T']
        and r['status'] not in ('GOVERNANCE_NO_NUMERIC_REPLACEMENT',
                               'LIMITED_NARRATIVE_UPDATE_NO_NUMERIC_REPLACEMENT',
                               'REGULATORY_REQUEST_NO_ISSUER_LEVEL_REPLACEMENT')]
    if query.get('mode','strict_index') == 'strict_index' and (gaps or unresolved):
        return {**base,'status':'UNKNOWN','value_CNY':None,
                'reason':'UNREAD_FINANCIAL_VERSION_CANDIDATE' if gaps else 'UNRESOLVED_NOTICE_SCOPE',
                'gaps':[r['id'] for r in gaps], 'unresolved_notices':[r['id'] for r in unresolved],
                'excluded_known_source':got['id']}
    return {**base,'status':'SELECTED_KNOWN_SOURCE','value_CNY':got['value_CNY'],
            'source_id':got['id'],'source_sha256':got['source_sha256'],'physical_page':got['physical_page'],
            'raw_text':got['raw_text'],'unit':got['unit'],'multiplier':got['multiplier'],
            'column':got['column'],'duration':got['duration'],'available_on':got['available_on'],
            'announcement_date':got['announcement_date'],'version_identity':got['version_identity'],
            'known_source_gaps':[r['id'] for r in gaps],
            'reason':'KNOWN_DOCUMENTS_DEMONSTRATION' if query.get('mode')=='known_documents' else
                     'POSITIVE_ANCHOR_WITH_NO_LATER_FLAGGED_GAP_WITHIN_SAVED_WINDOW',
            'scope_limit':'Index snapshot, bounded front tables and classified notices; not complete semantic or full-market PIT qualification'}


def differences(facts,ledger):
    columns = defaultdict(dict)
    for f in facts:
        if f['scope']=='consolidated' and f['mode'] in ('summary','notice_adjustment'):
            columns[(f['id'],f['period'],f['field'],f['duration'])][f['column']]=f
    paired = []
    for (id_,period,field,duration),cols in columns.items():
        if 'adjusted' in cols and 'unadjusted' in cols:
            a,b = cols['unadjusted'],cols['adjusted']
            paired.append({'id':id_,'code':a['code'],'period':period,'field':field,'duration':duration,
                'before':a['value_CNY'],'after':b['value_CNY'],
                'changed':Decimal(a['value_CNY'])!=Decimal(b['value_CNY']),
                'source_pages':[a['physical_page'],b['physical_page']]})
    groups = defaultdict(list)
    for f in ledger:
        groups[(f['code'],f['period'],f['field'],f['duration'])].append(f)
    transitions = []
    for key, versions in groups.items():
        versions.sort(key=lambda f:(f['announcement_date'],f['id']))
        for a,b in zip(versions,versions[1:]):
            transitions.append({'code':key[0],'period':key[1],'field':key[2],'duration':key[3],
                'first_id':a['id'],'second_id':b['id'],'first_date':a['announcement_date'],
                'second_date':b['announcement_date'],'before':a['value_CNY'],'after':b['value_CNY'],
                'changed':Decimal(a['value_CNY'])!=Decimal(b['value_CNY']),
                'earliest_revision_date_established':False})
    return paired,transitions


def main():
    documents = read(OUT/'dataset_legacy.json')['documents']+read(OUT/'new_documents.json')
    facts = []
    for certificate,parsed in [('certified_facts.json','parsed.json'),('certified_new_facts.json','new_parsed.json')]:
        c = read(OUT/certificate)
        assert c['whole_batch_has_zero_incorrect_accepted_values']
        assert c['parsed_sha256']==hashlib.sha256((OUT/parsed).read_bytes()).hexdigest()
        facts += c['facts']
    for d in documents:
        assert hashlib.sha256((ROOT/d['path']).read_bytes()).hexdigest()==d['sha256']
    sessions = calendar()
    assert read(OUT/'index_inventory.json')['all_windows_closed'], 'Incomplete metadata pagination cannot qualify replay'
    rows = read(OUT/'discovery_classification.json')['rows']
    notice_rows = read(OUT/'auxiliary_evidence.json')['notices']
    ledger,rejected = build_ledger(facts,documents,sessions)
    paired,transitions = differences(facts,ledger)
    ids = {r['id']:r for r in rows}
    windows = read(OUT/'preregistration.json')['windows']
    identities = []
    for d in documents:
        window = next(w for w in windows if w['code']==d['code'])
        in_window = window['start']<=d['date']<=window['end']
        row = ids.get(d['id'])
        ok = bool(row and all(row[k]==d[k] for k in ('code','date'))
                  and (not d.get('url') or row['url']==d['url']))
        identities.append({'id':d['id'],'in_window':in_window,'index_match':ok,
            'official_index_url':row['url'] if row else d.get('url'),
            'url_binding':'NEW_MANIFEST_URL_CHECKED' if d.get('url') else 'ARCHIVED_ID_CODE_DATE_SHA_REBOUND_TO_INDEX',
            'status':'PASS' if ok or not in_window else 'FAIL',
            'outside_window':'INDEPENDENT_BASE_POINT_ANCHOR_ONLY' if not in_window else None})
    assert all(i['status']=='PASS' for i in identities)
    output = [select(ledger,rows,notice_rows,sessions,q,windows) for q in read(OUT/'replay_queries_f2.json')]
    save('version_evidence_f2.json',{'ledger':ledger,'rejected_non_target_facts':rejected,
        'paired_columns':paired,'cross_document_transitions':transitions,
        'identity_checks':identities,'availability_rule':RULE,
        'calendar_sha256':hashlib.sha256((ROOT/'.rh3a2-vipdoc/sh/lday/sh000001.day').read_bytes()).hexdigest(),
        'unknown_revision_recall':'NOT_ESTABLISHED','full_market_pit_qualified':False})
    save('replay_results_f2.json',output)
    print({'ledger':len(ledger),'paired':len(paired),'transitions':len(transitions),'queries':len(output)})


if __name__ == '__main__':
    main()
