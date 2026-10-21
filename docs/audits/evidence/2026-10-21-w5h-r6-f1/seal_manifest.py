"""Seal deliverable byte identities; do not normalize audit evidence newlines."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPORT = OUT.parents[1]/'2026-10-21-w5h-r6-f1-parser-correction.md'


def identity(path, relative):
    b = path.read_bytes()
    return {'path': relative, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def main():
    files = [identity(p, p.relative_to(OUT).as_posix())
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json']
    payload = {'report': identity(REPORT, str(REPORT)), 'files': files,
               'manifest_self_hash_excluded': True, 'source_PDFs_referenced_not_copied': True}
    (OUT/'manifest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'files': len(files), 'evidence_bytes_excluding_manifest': sum(f['bytes'] for f in files)}))


if __name__ == '__main__':
    main()
