import json
from pathlib import Path
from research_sources import OUT, fetch

def main():
    summary = json.loads((OUT / 'upstream_summary.json').read_text(encoding='utf-8'))
    for repo, paths in {
        'mootdx/mootdx': ['mootdx/financial/financial.py', 'mootdx/financial/base.py', 'mootdx/financial/columns.py', 'mootdx/config.py'],
        'wkingnet/stock-analysis': ['func.py'],
        'zxtzlyt/tdx_quant': ['docs/tdx-quant-docs/03-tqcenter-财务/get_financial_data.md'],
    }.items():
        import urllib.parse
        sha = summary[repo]['sha']
        for path in paths:
            fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/' + urllib.parse.quote(path), OUT / 'upstream' / repo.replace('/', '__') / path)
    repo = 'rainx/pytdx'
    root = OUT / 'upstream' / 'rainx__pytdx'
    b = fetch(f'https://api.github.com/repos/{repo}/commits/master', root / 'master-head.json')
    if b:
        commit = json.loads(b)
        sha = commit['sha']
        for path in ['pytdx/reader/history_financial_reader.py', 'pytdx/crawler/history_financial_crawler.py', 'pytdx/hq.py', 'pytdx/parser/get_finance_info.py', 'LICENSE', 'setup.py']:
            fetch(f'https://raw.githubusercontent.com/{repo}/{sha}/{path}', root / path)
        summary[repo]['source_master_sha'] = sha
        summary[repo]['source_master_committed_at'] = commit['commit']['committer']['date']
    (OUT / 'upstream_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'github_requests_more.json').write_text((OUT / 'github_requests.json').read_text(encoding='utf-8'), encoding='utf-8')

if __name__ == '__main__':
    # Preserve the first batch's ledger before the shared fetch helper writes its own batch.
    (OUT / 'github_requests_initial.json').write_text((OUT / 'github_requests.json').read_text(encoding='utf-8'), encoding='utf-8')
    main()
