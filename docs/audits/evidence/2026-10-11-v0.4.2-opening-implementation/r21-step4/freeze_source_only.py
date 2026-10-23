"""Separate complete source bytes from copied/generated artifact envelope."""
import json
import run_gate as g
envelope=json.loads((g.OUT/'candidate-source.json').read_text(encoding='utf-8'))
current=g.source_identity()['working_tree_files']
cache_changes={n:{'prebuild_sha256':d,'current_sha256':current.get(n)} for n,d in envelope['working_tree_files'].items() if n.startswith('.ruff_cache/') and current.get(n)!=d}
excluded={n:d for n,d in envelope['working_tree_files'].items() if n.startswith('.ruff_cache/') or n.startswith('dist/') or n.endswith(('.whl','.tar.gz'))}
files={n:d for n,d in envelope['working_tree_files'].items() if n not in excluded}
assert all(current.get(n)==d for n,d in files.items()),'frozen source bytes changed'
assert all(n in envelope['working_tree_files'] or n.startswith('.ruff_cache/') for n in current),'unexpected source addition'
source={**envelope,'working_tree_files':files,'working_tree_manifest_sha256':g.sha(json.dumps(files,sort_keys=True).encode())}
source.update({'excluded_non_source_files':excluded,'excluded_reason':'Ruff cache and archived build/consumer artifacts are retained as evidence envelope, not candidate source','frozen_envelope_sha256':envelope['working_tree_manifest_sha256'],'source_bytes_changed_since_wheel_build':False,'generated_cache_drift':cache_changes,'all_source_only_files_equal_prebuild_envelope':True})
g.save('source-only-identity.json',source)
print(json.dumps({'source_only_sha256':source['working_tree_manifest_sha256'],'envelope_sha256':source['frozen_envelope_sha256'],'source_files':len(files),'excluded_non_source_files':len(excluded),'wheel_sha256':g.sha(g.WHEEL.read_bytes()),'status':'PASS'},indent=2))
