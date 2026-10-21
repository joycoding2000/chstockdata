"""Fetch a fixed set of public upstream source files; never execute them."""
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
LEDGER = []

def fetch(url, path, limit=2_000_000):
    time.sleep(0.3)
    row = {'url': url, 'file': path.relative_to(OUT).as_posix(), 'at_utc': datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'chstockdata-readonly-source-audit'})
        with urllib.request.urlopen(req, timeout=15) as response:
            b = response.read(limit + 1)
            row.update(http_status=response.status, content_type=response.headers.get('Content-Type'))
        if len(b) > limit:
            raise ValueError('body_limit')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b)
        row.update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest(), status='SAVED')
        return b
    except Exception as e:
        row.update(status='FAILED', error=type(e).__name__, detail=str(e)[:180])
        return None
    finally:
        LEDGER.append(row)
        (OUT / 'github_requests.json').write_text(json.dumps(LEDGER, ensure_ascii=False, indent=2), encoding='utf-8')

PROJECTS = {
    'zxtzlyt/tdx_quant': ['docs/LOCAL_NOTES.md', 'tdx_local/gpcw.py', 'tdx_local/cw_fields.py', 'tdx_local/tq_client.py', 'tests/test_offline.py', 'tests/test_live.py', 'LICENSE', 'README.md'],
    'wkingnet/stock-analysis': ['readTDX_cw.py', 'readTDX_lday.py', 'func_TDX.py', 'user_config.py', 'README.md'],
    'mootdx/mootdx': ['mootdx/reader.py', 'mootdx/affair.py', 'LICENSE', 'pyproject.toml'],
    'rainx/pytdx': ['pytdx/reader/history_financial_reader.py', 'pytdx/crawler/history_financial_crawler.py', 'pytdx/hq.py', 'pytdx/parser/get_finance_info.py', 'LICENSE', 'setup.py'],
}

def main():
    summary = {}
    for repo, files in PROJECTS.items():
        root = OUT / 'upstream' / repo.replace('/', '__')
        meta_bytes = fetch(f'https://api.github.com/repos/{repo}', root / 'repo.json')
        if not meta_bytes:
            continue
        meta = json.loads(meta_bytes)
        commit_bytes = fetch(f'https://api.github.com/repos/{repo}/commits/{meta["default_branch"]}', root / 'head.json')
        if not commit_bytes:
            continue
        commit = json.loads(commit_bytes)
        sha = commit['sha']
        tree_bytes = fetch(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1', root / 'tree.json')
        tree = json.loads(tree_bytes)['tree'] if tree_bytes else []
        available = {x['path'] for x in tree if x['type'] == 'blob'}
        # Find the actual license / installed-reader source paths when filenames differ.
        extra = [x for x in available if ('license' in x.lower() or 'copying' in x.lower()) and '/' not in x]
        if repo == 'mootdx/mootdx':
            extra += [x for x in available if x.startswith('mootdx/') and any(s in x for s in ('affair', 'history_financial', '/reader/')) and x.endswith('.py')]
        if repo == 'wkingnet/stock-analysis':
            extra += [x for x in available if any(s in x.lower() for s in ('财务', 'cw_field')) and x.endswith(('.txt', '.md', '.csv', '.py'))]
        chosen = list(dict.fromkeys(files + sorted(extra)))
        existing = []
        missing = []
        for f in chosen:
            if tree_bytes and f not in available:
                missing.append(f)
                continue
            if fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/{f}', root / f):
                existing.append(f)
        summary[repo] = {'sha': sha, 'committed_at': commit['commit']['committer']['date'], 'default_branch': meta['default_branch'], 'archived': meta['archived'], 'license': meta.get('license'), 'files_saved': existing, 'paths_absent': missing, 'tree_truncated': json.loads(tree_bytes).get('truncated') if tree_bytes else None}
        (OUT / 'upstream_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(repo, sha, len(existing), 'files', flush=True)

if __name__ == '__main__':
    main()
