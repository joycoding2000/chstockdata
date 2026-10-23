"""Bounded final verification, offline reproduction and consumer archive."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "H04-TR-delivery"


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def run(label, script, *args):
    # A fresh process with actual outbound sockets disabled for each check.
    wrapper = "import runpy,socket,sys; from pathlib import Path; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('OFFLINE_VERIFICATION_NETWORK_FORBIDDEN')); sys.argv=sys.argv[1:]; sys.path.insert(0,str(Path(sys.argv[0]).resolve().parent)); runpy.run_path(sys.argv[0],run_name='__main__')"
    command = [sys.executable,"-B","-c",wrapper,str(ROOT/script),*map(str,args)]
    env = dict(os.environ,PYTHONIOENCODING="utf-8",PYTHONDONTWRITEBYTECODE="1")
    start=time.monotonic()
    result=subprocess.run(command,cwd=ROOT.parents[3],env=env,capture_output=True)
    (ROOT/(label+".stdout.txt")).write_bytes(result.stdout)
    (ROOT/(label+".stderr.txt")).write_bytes(result.stderr)
    save(ROOT/(label+".command.json"),{"command":command,"cwd":str(ROOT.parents[3]),"exit_code":result.returncode,"elapsed_seconds":round(time.monotonic()-start,3),"outbound_sockets_disabled":True})
    print(label,result.returncode,flush=True)
    if result.returncode:
        print(result.stdout.decode("utf-8",errors="replace")[-2000:]); print(result.stderr.decode("utf-8",errors="replace")[-3000:])
        raise SystemExit(result.returncode)


def main():
    ledger=json.loads((ROOT/"network_ledger.json").read_text(encoding="utf-8"))
    ledger["closed"]=True
    ledger["closure_reason"]="STOP_SOURCE_EXPANSION; offline delivery and Owner Review"
    ledger["opaque_tools"]={"web_search_queries":1,"web_search_evidence":"index-search-result.json","failed_firecrawl_status_calls":1,"internal_transport_bytes":None,"reserved_total_request_slots":6,"reserved_total_bytes":3000000}
    save(ROOT/"network_ledger.json",ledger)
    run("economic-tests","test_h04_offline.py")
    run("build-final","build_delivery.py")
    run("initial-independent-receipt","receive_delivery.py",PACKAGE,"--report",ROOT/"candidate_validation.json")
    shutil.copyfile(ROOT/"candidate_validation.json",PACKAGE/"validation_report.json")
    run("build-with-receipt","build_delivery.py")
    run("final-independent-receipt","receive_delivery.py",PACKAGE,"--report",ROOT/"independent_validation.json")
    assert (ROOT/"independent_validation.json").read_bytes()==(PACKAGE/"validation_report.json").read_bytes()
    run("financial-mutation-tests","test_receiver_mutations.py")
    before=(PACKAGE/"manifest.json").read_bytes()
    run("offline-reproduction","build_delivery.py","--root",PACKAGE,"--output",PACKAGE)
    assert (PACKAGE/"manifest.json").read_bytes()==before,"offline manifest not byte-identical"
    zip_path=ROOT/"H04-TR-delivery.zip"
    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path,path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        assert z.read("H04-TR-delivery/manifest.json")==before
        zip_files=len(z.namelist())
    report=json.loads((ROOT/"independent_validation.json").read_text(encoding="utf-8"))
    summary={"phase":"SIOS_H04_PRIORITY_FREE_DATA_DELIVERY", "step":"OFFLINE_DELIVERY_COMPLETE_STOP_AT_OWNER_REVIEW", "verdict":"H04_TR_READY_ATTRIBUTION_BLOCKED",
        "manifest_sha256":hashlib.sha256(before).hexdigest(),"zip_sha256":hashlib.sha256(zip_path.read_bytes()).hexdigest(),"zip_bytes":zip_path.stat().st_size,"zip_file_count":zip_files,
        "unit_tests":7,"financial_mutation_tests":5,"independent_receipt":report,"offline_reproduction_manifest_byte_identical":True,"zip_crc_pass":True,
        "no_strategy_execution":True,"no_production_change":True,"no_commit":True,"no_push":True,"SIOS_consumer_acceptance_pending":True,
        "temporary_environment_created":False,"temporary_environment_cleanup":"No new venv/build/cache runtime; only task-owned Python bytecode may be removed after artifact export."}
    save(ROOT/"completion.json",summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
