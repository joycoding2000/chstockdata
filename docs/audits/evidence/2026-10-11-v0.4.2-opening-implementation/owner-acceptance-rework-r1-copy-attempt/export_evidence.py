"""Record the three-file rework diff and limited offline evidence identity."""
import difflib
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = WORK / 'chstockdata-owner-rework'
OLD = WORK / 'chstockdata'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
old_files = baseline['old_source_files']
assert all(sha((OLD / name).read_bytes()) == digest for name, digest in old_files.items())
new_files = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(ROOT.rglob('*')) if p.is_file()}
assert new_files.keys() == old_files.keys()
changed = [name for name, digest in new_files.items() if digest != old_files[name]]
assert changed == sorted(['src/chstockdata/opening_evidence.py', 'src/chstockdata/opening_known_events.json',
                          'tests/test_historical_opening_evidence.py'])
patch = ''.join(''.join(difflib.unified_diff(
    (OLD / name).read_text(encoding='utf-8').splitlines(keepends=True),
    (ROOT / name).read_text(encoding='utf-8').splitlines(keepends=True),
    fromfile='a/' + name, tofile='b/' + name)) for name in changed)
(OUT / 'source-relative-old-rework.patch').write_text(patch, encoding='utf-8')
save('rework-source-manifest.json', {'source_files': new_files,
     'canonical_files_sha256': sha(json.dumps(new_files, sort_keys=True).encode('utf-8'))})
wheel = WORK / 'dist/r21-qualified/chstockdata-0.4.2-py3-none-any.whl'
assert sha(wheel.read_bytes()) == baseline['old_wheel_sha256']
results = []
for name in ('old-wheel-owner-repro', 'owner-red', 'owner-green', 'focused-green', 'rh1-static'):
    command = json.loads((OUT / (name + '.command.json')).read_text(encoding='utf-8'))
    entry = {k: v for k, v in command.items() if k != 'argv'}
    if 'junit' in command:
        suite = ET.parse(OUT / command['junit']).getroot().find('testsuite')
        entry['test_counts'] = {key: int(suite.get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')}
    results.append(entry)
head = subprocess.check_output(['git', '-c', 'safe.directory=D:/Dev/Projects/chstockdata',
    '-C', 'D:/Dev/Projects/chstockdata', 'rev-parse', 'HEAD'], text=True).strip()
summary = {
    'phase_step': 'R2.1 Owner Acceptance interval-defect rework r1; implementation + limited offline verification',
    'classification': 'CONFIRMED_DEFECT',
    'root_cause': 'effective_end=None was treated as an infinite halt despite authenticated date-only resume evidence',
    'changes': changed,
    'trust_boundary': 'Only exact object identities loaded from the controlled packaged asset carry resume-date applicability; caller/current self-asserted dates, SHA strings and verification markers cannot acquire it',
    'behavior': 'Resume date remains UNKNOWN with no fabricated clock; later dates no longer inherit this old halt veto, and still require all unchanged R2.1 TDX/current-official qualifications',
    'provenance': 'All original effective_start/effective_end=None, source URLs/SHA and raw fields retained; resolved/expired events remain in official_events',
    'qualification': 'Deterministic injected transport and frozen-fixture regression only; no new live qualification',
    'limited_verdict': 'PASS', 'full_gate_verdict': 'INSUFFICIENT_EVIDENCE',
    'tests': results, 'original_tests_retained': 128, 'new_regressions': 22,
    'static': {'ruff_version': '0.16.10', 'structured_paths_pass': 24, 'visible_legacy_findings': 287,
               'added_lines_pass': True, 'real_baseline_commit': '143eb5a61e11003a4b29461eeb78deec0ab8d8e5',
               'production_static_script_changed': False},
    'original_repository_head': head, 'rework_snapshot_git': False, 'rework_committed': False,
    'working_tree': 'Isolated source differs in exactly 3 files; no .git; original source manifest 765 files unchanged',
    'source_manifest_sha256': sha((OUT / 'rework-source-manifest.json').read_bytes()),
    'patch_sha256': sha((OUT / 'source-relative-old-rework.patch').read_bytes()),
    'old_wheel_sha256': sha(wheel.read_bytes()), 'old_source_765_files_unchanged': True,
    'blockers': [], 'scope_changes': [], 'build_performed': False, 'publication_performed': False,
    'next_action': 'Root independently verifies this frozen rework and obtains fresh spec then quality review; no next-phase authorization claimed',
}
save('implementation-summary.json', summary)
(OUT / 'handoff.md').write_text(
    '# Owner Acceptance 区间缺陷重做 r1 交接\n\n'
    '- 阶段/步骤：R2.1 Owner Acceptance 缺陷最小修复及有限离线验证。\n'
    f'- 原仓库 HEAD：`{head}`；新快照无 `.git`、未提交，恰好修改 3 个文件。\n'
    '- 根因：`effective_end=None` 无限期适用，忽略受控缓存中认证的复牌日期。\n'
    '- 修复：只有受控 packaged 对象身份获得日期适用资格；复牌日未知 clock 保守 UNKNOWN，之后仅撤销对应旧 halt。caller/current 任意 date、SHA 或 verified 标记不能解除阻断。\n'
    '- 原始事实：保留 start、end=None、源 SHA、完整 raw fields/provenance；过期或已解析事件仍出现在 official_events。\n'
    '- 证据：旧 wheel 原样独立离线注入复现 exit 0；RED 13 failed/9 passed；GREEN 22 passed；指定四文件 150 passed（原128+新增22）；RH1 静态 exit 0，24路径、真实 baseline 新增行通过，287项历史债务继续可见。\n'
    '- verdict：有限实现验证 PASS；新统一 Gate 尚未运行，整体 Gate 为 INSUFFICIENT_EVIDENCE，未宣称 Owner 接受。\n'
    '- 阻塞/范围：无实现阻塞，无范围扩张；未改旧源码、旧 wheel、旧证据、SIOS，未 build/commit/push/tag/publish/推进阶段。\n'
    '- 下一步：root 独立有限验证，fresh spec→quality 审核后再按授权处理新 wheel 与统一 Gate；不代表下一阶段已获授权。\n\n'
    '完整命令、exit/log/JUnit/hash 见各 `.command.json` 和 `implementation-summary.json`；全量三文件 diff 见 `source-relative-old-rework.patch`。所有新增日期运输数据均是确定性注入，不是新 live 资格证据。\n', encoding='utf-8')
print(json.dumps({'changed_files': changed, 'summary_sha256': sha((OUT / 'implementation-summary.json').read_bytes()),
                  'patch_sha256': summary['patch_sha256'], 'old_source_unchanged': True, 'old_wheel_unchanged': True}))
