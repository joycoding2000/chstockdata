"""Run the bounded parser without loading the expected-value fixture."""
import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from parser_f1 import extract_document

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def main():
    dataset = json.loads((OUT / 'dataset.json').read_text(encoding='utf-8'))
    code_path = OUT / 'parser_f1.py'
    code_sha = hashlib.sha256(code_path.read_bytes()).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    results = []
    for source in dataset['documents']:
        t = time.perf_counter()
        result = extract_document(ROOT, source)
        result['machine_seconds'] = time.perf_counter() - t
        results.append(result)
        print(json.dumps({'id': source['id'], 'facts': len(result['facts']),
                          'seconds': result['machine_seconds']}, ensure_ascii=True), flush=True)
    (OUT / 'parsed.json').write_text(json.dumps({
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'started_at_utc': started,
        'parser_sha256_at_start': code_sha,
        'parser_sha256_at_end': hashlib.sha256(code_path.read_bytes()).hexdigest(),
        'network_requests': 0, 'truth_read_by_parser': False,
        'machine_seconds': time.perf_counter() - start, 'results': results,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
