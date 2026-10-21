"""New-document parsing and run identities, never reads reference amounts."""
import hashlib
import json
import time
import sys
from datetime import datetime, timezone
from acquire import OUT, ROOT, read, save
from parser_f2 import extract_document
from offline_extras import notice_levels


def main():
    code = hashlib.sha256((OUT/'parser_f2.py').read_bytes()).hexdigest()
    extra_code = hashlib.sha256((OUT/'offline_extras.py').read_bytes()).hexdigest()
    cached = {}
    if '--reuse-base' in sys.argv:
        old = read(OUT/'new_base_parsed.json')
        assert old['code_sha256_start'] == old['code_sha256_end'] == code
        cached = {r['id']: r for r in old['results']}
    results = []
    for d in read(OUT/'new_documents.json'):
        t = time.perf_counter()
        result = cached.get(d['id']) or extract_document(ROOT, d)
        if d['id'] in cached:
            assert result['source_sha256'] == d['sha256'] == hashlib.sha256((ROOT/d['path']).read_bytes()).hexdigest()
            result['base_machine_seconds_cached'] = result['machine_seconds']
        if d['kind'] == 'notice':
            result['facts'].extend(notice_levels(ROOT, d))
        result['machine_seconds'] = time.perf_counter()-t
        results.append(result)
        print(json.dumps({'id': d['id'], 'kind': d['kind'], 'facts': len(result['facts']),
                          'seconds': result['machine_seconds']}), flush=True)
    save('new_parsed.json', {'code_sha256_start': code,
                            'code_sha256_end': hashlib.sha256((OUT/'parser_f2.py').read_bytes()).hexdigest(),
                            'extra_code_sha256_start': extra_code,
                            'extra_code_sha256_end': hashlib.sha256((OUT/'offline_extras.py').read_bytes()).hexdigest(),
                            'reused_base_parse': bool(cached),
                            'at_utc': datetime.now(timezone.utc).isoformat(), 'results': results})


if __name__ == '__main__':
    main()
