"""Observed file/processing ledger, not a population throughput estimate."""
import hashlib
import json
import platform
from pathlib import Path
import pdfplumber
import pypdf

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def main():
    docs = read('dataset.json')['documents']
    parsed = read('parsed.json')
    results = {r['id']: r for r in parsed['results']}
    scored = read('value_validation.json')['cases']
    files = []
    for d in docs:
        path = ROOT/d['path']
        b = path.read_bytes()
        pages = len(pypdf.PdfReader(path).pages)
        files.append({**d, 'bytes': len(b), 'pages': pages,
                      'sha_matches': hashlib.sha256(b).hexdigest() == d['sha256'],
                      'parser_text_pages': min(30, pages) if d['kind'] == 'periodic' else 0,
                      'machine_parse_seconds': results[d['id']]['machine_seconds'],
                      'field_results': {s: sum(c['id'] == d['id'] and c['result'] == s for c in scored)
                                        for s in ['PASS', 'FAIL', 'UNKNOWN']}})
    payload = {'files': files, 'file_count': len(files),
               'source_bytes_reused': sum(f['bytes'] for f in files),
               'source_pages_present': sum(f['pages'] for f in files),
               'parser_text_pages': sum(f['parser_text_pages'] for f in files),
               'notice_text_pages_in_version_triage': sum(f['pages'] for f in files if f['kind'] == 'notice'),
               'parser_machine_seconds': parsed['machine_seconds'],
               'first_repair_trial_seconds': read('first_parse.json')['machine_seconds'],
               'download_requests': 0, 'download_bytes': 0, 'download_seconds': 0,
               'network_retries': 0, 'manual_numeric_corrections': 0,
               'independent_human_review_time': 'NOT_MEASURED',
               'agent_work_wall_time_is_not_human_labor': True,
               'whole_market_error_rate_or_manual_share': 'NOT_ESTIMATED',
               'runtime': {'python': platform.python_version(), 'pdfplumber': pdfplumber.__version__,
                           'pypdf': pypdf.__version__, 'new_dependencies_installed': False}}
    (OUT/'cost_ledger.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in payload.items() if k not in ['files']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
