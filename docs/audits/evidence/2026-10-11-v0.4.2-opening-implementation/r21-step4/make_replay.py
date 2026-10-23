from pathlib import Path
e=Path(__file__).resolve().parent
s=(e.parent/'r21-step1/replay_final.py').read_text(encoding='utf-8')
s=s.replace("sys.path.insert(0,str(root/'src'))","import chstockdata\nimport run_gate\nrun_gate.installed_identity('sios-candidate')")
s=s.replace("sys.path.append('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages')",'')
s=s.replace("live=here/'live'","live=here.parent/'r21-step1/live'")
s=s.replace("root/'src/chstockdata/opening_evidence.py',root/'src/chstockdata/opening_known_events.json'","Path(chstockdata.__file__).parent/'opening_evidence.py',Path(chstockdata.__file__).parent/'opening_known_events.json'")
s=s.replace('str(p.relative_to(root))','str(p)')
s=s.replace("'purpose':'final source replay","'wheel_sha256':run_gate.sha(run_gate.WHEEL.read_bytes()),'installed_import':chstockdata.__file__,'purpose':'final installed-wheel replay")
(e/'run_replay.py').write_text(s,encoding='utf-8')
