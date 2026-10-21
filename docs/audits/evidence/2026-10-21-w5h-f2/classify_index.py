"""Full fixed-window metadata denominator; uncertain financial bodies block recall."""
import re
from collections import Counter
from acquire import OUT, read, save
from version_legacy import report_period


def classify(row, obtained):
    title = row['title']
    duplicate = bool(re.search(r'摘要|英文|English|H股公告', title, re.I))
    period = report_period(title)
    periodic = bool(period) and not re.search(r'问询|回复|说明|意见|核查|审计|提示|预约|披露时间|披露日期|董事会|监事会|公告|^关于',title)
    financial = bool(re.search(r'募集说明书|财务会计|审核问询.*回复|会计师.*(?:函|回复)|'
        r'年报问询|年度报告问询|会计政策|会计差错|追溯调整|财务报告.*更正|'
        r'财务报表|审计报告|审阅报告|非标准.*审计|审计意见|'
        r'(?:年度|季度|半年|半年度)报告.*(?:更正|更新|补充)|'
        r'关于.*更正|监管.*函.*回复', title))
    auxiliary = bool(re.search(r'内部控制|内控审计|关联方资金占用|增持公司股份计划|'
                              r'(?<!股份)有限公司.*审计报告',title))
    audit_companion = bool(re.search(r'审计报告$|审计意见|保留意见审计报告',title))
    # A bundled "recent statements" filing is still a potential new version;
    # a same-day annual audit companion has no positive update signal by title.
    if auxiliary:
        category, reason = 'AUXILIARY_METADATA', 'Control, capital transactions or other-entity audit topic; no issuer consolidated replacement is inferred'
    elif duplicate:
        category, reason = 'DUPLICATE_OR_SUMMARY', 'Separate full statement/filing is the primary candidate; no independent certification from summary'
    elif periodic:
        category, reason = 'FULL_PERIODIC', 'Positive report identity, not a correction-keyword search'
    elif audit_companion and not re.search(r'更正|更新|修订|补充|最近', title):
        category, reason = 'AUDIT_COMPANION_UNVERIFIED', 'Annual/audit companion body equality not checked; does not supply a numeric replacement'
    elif financial:
        category, reason = 'FINANCIAL_VERSION_CANDIDATE', 'Potential historical financial evidence; title alone cannot certify or dismiss amount impact'
    elif row['id'] in obtained:
        category, reason = 'OBTAINED_NOTICE', 'Previously selected notice, retains content checks'
    else:
        category, reason = 'OTHER_METADATA', 'No positive report/financial-version title signal; body not semantically certified'
    body = row['id'] in obtained
    needed = category in ('FULL_PERIODIC','FINANCIAL_VERSION_CANDIDATE','OBTAINED_NOTICE')
    return {**row, 'period':period if periodic else None, 'category':category,
            'reason':reason, 'body_obtained':body, 'required_candidate':needed,
            'state':'BODY_OBTAINED' if body else 'UNREAD_SOURCE_CAP' if needed else 'METADATA_ONLY',
            'complete_semantic_clearance':False}


def main():
    docs = read(OUT/'dataset_legacy.json')['documents']+read(OUT/'new_documents.json')
    obtained = {d['id'] for d in docs}
    inventory = read(OUT/'index_inventory.json')
    rows = [classify(r,obtained) for r in inventory['rows']]
    gaps = [r for r in rows if r['required_candidate'] and not r['body_obtained']]
    save('discovery_classification.json',{'denominator':len(rows),
        'all_official_metadata_windows_closed':inventory['all_windows_closed'],
        'counts':dict(Counter(r['category'] for r in rows)),
        'required_candidate_count':sum(r['required_candidate'] for r in rows),
        'required_candidate_bodies_obtained':sum(r['required_candidate'] and r['body_obtained'] for r in rows),
        'unread_required_candidate_count':len(gaps), 'unread':gaps, 'rows':rows,
        'full_market_discovery_completeness':'NOT_ESTABLISHED',
        'title_rule_limit':'Other metadata is not proof of no undisclosed revision; complete semantic recall is not claimed.'})
    print({'metadata':len(rows),'unread_financial_candidates':len(gaps),
           'counts':dict(Counter(r['code'] for r in gaps))})


if __name__ == '__main__':
    main()
