import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from audit_common import OUT, ROOT, save, sha

def git(root, *args):
    r = subprocess.run(['git','-c',f'safe.directory={root.as_posix()}','-C',str(root),*args],capture_output=True,encoding='utf-8',errors='replace')
    assert r.returncode == 0, (args,r.stderr)
    return r.stdout

repos = {}
for name in ('chstockdata','mishi-radar','systematic-investing-os'):
    root = ROOT.parent/name
    tracked = [x for x in git(root,'ls-files','-z').split('\0') if x]
    untracked = [x for x in git(root,'ls-files','--others','--exclude-standard','-z').split('\0') if x]
    snapshots = {}
    # Preserve all untracked names/status without opening unrelated research data.
    # Necessary prior untracked originals are content-verified by their manifests below.
    for rel in tracked:
        p = root/rel
        if not p.is_file() or (name == 'chstockdata' and p.is_relative_to(OUT)):
            continue
        s = p.stat()
        snapshots[rel] = {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'tracked':rel in tracked,'sha256':sha(p) if s.st_size <= 20_000_000 or rel in tracked else None}
    repos[name] = {'root':str(root),'head':git(root,'rev-parse','HEAD').strip(),'branch':git(root,'branch','--show-current').strip(),'status':git(root,'status','--porcelain=v1','--untracked-files=all'), 'files':snapshots, 'untracked_paths':untracked}
save('before.json',{'at_utc':datetime.now(timezone.utc).isoformat(),'repos':repos})

checks = []
for name in ('2026-10-19-w5h','2026-10-20-w5h-r2','2026-10-20-w5h-r3'):
    base = OUT.parent/name
    p = base/'manifest.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    records = data.get('artifacts') or data.get('files')
    for r in records:
        target = ROOT/r['path'] if 'artifacts' in data else base/r['path']
        actual = sha(target) if target.is_file() else None
        checks.append({'path':str(target),'expected_sha256':r['sha256'],'actual_sha256':actual,'matches':actual==r['sha256'] and target.stat().st_size==r['bytes']})
    if 'report' in data:
        r=data['report'];target=Path(r['path'])
        checks.append({'path':str(target),'expected_sha256':r['sha256'],'actual_sha256':sha(target),'matches':sha(target)==r['sha256']})
save('prior_manifest_checks.json',{'files':checks,'all_match':all(x['matches'] for x in checks)})
assert all(x['matches'] for x in checks)
save('budget.json', {'direct_requests':16,'web_batches':8,'single_body_bytes':20_000_000,'total_saved_network_bytes':60_000_000,'timeout_seconds':15,'same_host_after_finish_seconds':3,'automatic_retries':0,'redirects':False,'fixed_security':'SH:600518','financial_period':'2017-01-01/2017-12-31','latest_allowed_disclosure_date':'2019-05-06','old_originals_redownload':'FORBIDDEN','xbrl_not_required_if_official_pdf_or_html_sufficient':True})
print(json.dumps({'heads':{n:r['head'] for n,r in repos.items()},'protected_files':{n:len(r['files']) for n,r in repos.items()},'prior_manifest_files':len(checks),'all_prior_hashes_match':True},ensure_ascii=False))
