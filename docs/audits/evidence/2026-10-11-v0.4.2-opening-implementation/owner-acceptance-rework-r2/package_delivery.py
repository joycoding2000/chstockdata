"""Package only the r2 delta, new evidence and updated audit; verify every member."""
import hashlib
import json
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
AUDIT = REPO / 'docs/audits/2026-10-11-v0.4.2-opening-implementation.md'
text = AUDIT.read_text(encoding='utf-8')
section = text.split('## Owner Acceptance REWORK r2 — 2026-10-14', 1)[1]
status = section.split('```ini\n', 1)[1].split('```', 1)[0]
(OUT / 'owner-review-status.ini').write_text(status, encoding='utf-8')
(OUT / 'handoff.md').write_text('## Owner Acceptance REWORK r2 — 2026-10-14\n' + section, encoding='utf-8')
(OUT / 'README.md').write_text('''# Owner Acceptance REWORK r2

Apply `sios-source-vs-r1.patch` to the previously byte-verified 256-file SIOS r1 source. The prior frozen-to-r1 patch and unchanged chstockdata wheel remain in the r1 delivery. The r2 patch adds the complete new regression file and changes only domain/historical_opening.py. `delta-verification.json` proves the 257-file reconstruction. `sios-source-manifest.json` records the full tested identity; this is not a Git commit.

`independent-verification.json` checks byte identities, JUnit counts, 54 live capabilities and 129 new raw outputs. `red*` and all intermediate failed GREEN attempts remain visible. Offline transports are deterministic tests, not live certification of those historical dates. `live/` contains the five freshly executed mandatory tests against the changed SIOS and unchanged real r1 wheel.

The complete canonical event hash is a narrow trust anchor for the already authenticated r1 fact. No caller verification flags or source labels are trusted, no interval end is synthesized, and new null-ended events retain veto. Snapshot replay requires no vendor imports or network. Tests intentionally use synthetic stock rules/calendar to isolate eligibility; they do not qualify historical exchange rules.

Old package and TradingAgents evidence is reused only because the actual wheel, 765 CH source files and r1 delivery identity are unchanged. No phase/release authorization, merge, push, tag or publication was performed. See handoff.md and owner-review-status.ini.
''', encoding='utf-8')
assert json.loads((OUT / 'independent-verification.json').read_text(encoding='utf-8'))['verdict'] == 'PASS_CANDIDATE_OWNER_PENDING'
files = {p.relative_to(OUT).as_posix(): p for p in sorted(OUT.rglob('*')) if p.is_file() and not any(part in {'live-temp', '__pycache__', '.pytest_cache'} for part in p.relative_to(OUT).parts)}
assert not any(p.is_symlink() for p in files.values())
digests = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in files.items() if n != 'SHA256SUMS.json'}
(OUT / 'SHA256SUMS.json').write_text(json.dumps(digests, indent=2), encoding='utf-8')
files['SHA256SUMS.json'] = OUT / 'SHA256SUMS.json'
archive = OUT.parent / 'owner-acceptance-rework-r2-delta-evidence.zip'
members = {'evidence/' + n: p.read_bytes() for n, p in files.items()}
members['implementation-audit-updated.md'] = AUDIT.read_bytes()
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for n, data in members.items():
        z.writestr(n, data)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist()) == set(members)
    assert all(z.read(n) == data for n, data in members.items())
receipt = {'zip_path': str(archive), 'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'zip_bytes': archive.stat().st_size,
    'files': len(members), 'crc_and_every_member_verified': True, 'sios_source_sha256': json.loads((OUT / 'sios-source-manifest.json').read_text(encoding='utf-8'))['source_manifest_sha256'],
    'includes_prior_14_mib_zip': False, 'includes_chstockdata_wheel': False, 'scope': 'r2 two-file SIOS delta, new evidence, updated audit'}
(OUT.parent / 'owner-acceptance-rework-r2-delivery-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
