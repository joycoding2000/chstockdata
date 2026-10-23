"""Check all pre-existing files, output scope, HEAD and the final audit manifest."""
import subprocess
from datetime import datetime,timezone
from common import HERE, ROOT, read, save, sha


def main():
    before=read(HERE/'before.json')
    changed=[];missing=[]
    for rel,digest in before['files'].items():
        p=ROOT/rel
        if not p.exists():missing.append(rel)
        elif sha(p)!=digest:changed.append(rel)
    report=ROOT/'docs/audits/2026-10-22-w5h-f2-final-evidence-qualification.md'
    assert report.exists()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked_diff=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=ROOT,text=True).splitlines()
    new=[]
    for folder in ('docs','src','tests','scripts','examples'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file()and '__pycache__'not in p.parts and not p.is_relative_to(HERE) and p!=report and p.relative_to(ROOT).as_posix()not in before['files']:
                new.append(p.relative_to(ROOT).as_posix())
    checks={'head_unchanged':head==before['head'],'original_files_preserved':not changed and not missing,
            'new_outputs_only_in_authorized_paths':not new,'tracked_diff_empty':not tracked_diff,
            'fresh_package_complete':read(HERE/'package_run.json')['complete'],
            'regression_complete':read(HERE/'regression_run.json')['complete'],
            'new_quality_pass':read(HERE/'final_quality_checks.json')['pass']}
    save('final_integrity.json',{'utc':datetime.now(timezone.utc).isoformat(),'head':head,
         'checks':checks,'pass':all(checks.values()),'preserved_file_denominator':len(before['files']),
         'changed_existing_files':changed,'missing_existing_files':missing,'unexpected_new_outputs':new,
         'tracked_diff':tracked_diff,'commit':False,'push':False,'temporary_environment_created':False,
         'archive_or_source_cleanup_performed':False})
    manifest=[]
    for p in sorted(HERE.rglob('*')):
        if p.is_file()and p.name!='manifest.json':manifest.append({'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    manifest.append({'path':report.relative_to(ROOT).as_posix(),'bytes':report.stat().st_size,'sha256':sha(report)})
    save('manifest.json',{'files':manifest,'file_denominator':len(manifest),'bytes':sum(p['bytes']for p in manifest),
                         'manifest_excludes_itself':True,'pass':all(checks.values())})
    print({'integrity':checks,'preserved_files':len(before['files']),'evidence_files':len(manifest)})
    assert all(checks.values())


if __name__=='__main__':main()
