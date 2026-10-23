"""Append Owner rework closeout and export a new, verified evidence ZIP."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

OUT = Path(__file__).resolve().parent
WORK = OUT.parents[1]
ROOT = Path('D:/Dev/Projects/chstockdata')
AUDIT = ROOT/'docs/audits/2026-10-11-v0.4.2-opening-implementation.md'
DELIVERY_ROOT = ROOT/'docs/audits/evidence/2026-10-11-v0.4.2-opening-implementation'
DELIVERY = DELIVERY_ROOT/'owner-acceptance-rework-r1'
ZIP = DELIVERY_ROOT/'owner-acceptance-rework-r1-evidence.zip'
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
sha = lambda data: hashlib.sha256(data).hexdigest()
def save(name, data):
    (OUT/name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
summary = read(OUT/'gate/summary.json')
proof = read(OUT/'independent-new-gate-verification.json')
protection = read(OUT/'original-protection-final.json')
assert summary['gate_verdict'] == 'PASS_CANDIDATE'
assert proof['exit_code'] == protection['exit_code'] == 0
assert 'APPROVED' in (OUT/'gate-spec-review.md').read_text(encoding='utf-8')
assert 'APPROVED' in (OUT/'gate-quality-review.md').read_text(encoding='utf-8')
assert not DELIVERY.exists() and not ZIP.exists()
wheel_sha = summary['candidate_wheel_sha256']
source_sha = summary['candidate_source_sha256']
flag_names = {'PACKAGE': 'PACKAGE_TESTS', 'LIVE': 'SIOS_MANDATORY_LIVE',
              'TA': 'TRADINGAGENTS_RELATIVE_COMPAT', 'RELEASE': 'RELEASE_AUTHORIZED',
              'PUBLISH': 'PUBLISH_AUTHORIZED', 'NEXT_PHASE': 'NEXT_PHASE_AUTHORIZED'}
flags = {flag_names.get(key, key): value for key, value in summary['flags'].items()}
assert flags['READY_FOR_OWNER_REVIEW'] == 'YES'
ini = '\n'.join(f'{key} = {value}' for key, value in flags.items())+'\n'
(OUT/'owner-review-status.ini').write_text(ini, encoding='utf-8')
for stem, report, script in (
    ('independent-new-gate-verification', proof, 'verify_new_gate_independent.py'),
    ('original-protection-final', protection, 'verify_original_protection.py'),
):
    (OUT/(stem+'.exit')).write_text('0\n', encoding='utf-8')
    (OUT/(stem+'.log')).write_text(json.dumps(report)+'\n', encoding='utf-8')
    save(stem+'.command.json', {
        'argv': ['C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe', str(OUT/script)],
        'cwd': str(ROOT), 'exit': 0, 'mode': 'authorized read-only elevated verification',
        'script_sha256': sha((OUT/script).read_bytes()),
        'log': stem+'.log', 'result': stem+'.json',
        'note': 'Actual command results independently returned exit 0; saved report also retained as stdout log.'})
save('root-verification-retained-attempts.json', {
    'production_test_results_modified': False,
    'attempts': [
        {'checker': 'verify_new_gate_independent.py', 'exit': 1,
         'finding': 'Initial checker assumed all commands bind wheel; environment inventory precedes wheel generation. Checker corrected to permit only environment empty wheel identity.'},
        {'checker': 'verify_new_gate_independent.py', 'exit': 1,
         'finding': 'Initial checker expected ZIP members without systematic-investing-os/ prefix. Checker adapted to actual exporter prefix; all 256 bytes match.'},
        {'checker': 'verify_original_protection.py', 'exit': 1,
         'finding': 'Early original SIOS baseline differs by one modified decision document and one new research document. Current state retained and explicitly recorded; no original SIOS write issued by this rework.'},
    ],
    'final_checkers_exit': 0,
})
artifact_dir = OUT/'artifacts'
artifact_dir.mkdir()
for key in ('wheel', 'sdist'):
    artifact = read(OUT/'gate/artifacts.json')[key]
    src = Path(artifact['path'])
    assert sha(src.read_bytes()) == artifact['sha256']
    target = artifact_dir/src.name
    shutil.copyfile(src, target)
    assert target.read_bytes() == src.read_bytes()
files = read(OUT/'rework-source-manifest.json')['source_files']
with zipfile.ZipFile(OUT/'chstockdata-tested-source.zip', 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name, digest in sorted(files.items()):
        data = (WORK/'chstockdata-owner-rework'/name).read_bytes()
        assert sha(data) == digest
        archive.writestr('chstockdata/'+name, data)
with zipfile.ZipFile(OUT/'chstockdata-tested-source.zip') as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == 765
    assert all(sha(archive.read('chstockdata/'+name)) == digest for name, digest in files.items())
manifest_file_sha = sha((OUT/'rework-source-manifest.json').read_bytes())
marker = '### Owner REWORK r1 final candidate and evidence closeout — 2026-10-13'
text = AUDIT.read_text(encoding='utf-8')
assert marker not in text
append = f'''

{marker}

CURRENT_DECISION 保持 FIX_ONLY。Owner 指出的持续区间缺陷已确认并作最小修复；此前 Step4 PASS_CANDIDATE、旧 source/wheel/live/ZIP 历史保留。本节为本次独立新候选的实际验证结果，Owner Acceptance 仍 PENDING。

仅修改隔离候选的 `src/chstockdata/opening_evidence.py`、`src/chstockdata/opening_known_events.json`、`tests/test_historical_opening_evidence.py`。对内部加载的认证事件，2016-07-04 之后不再沿用旧停牌否决；复牌日精确时刻未知，仍返回 UNKNOWN。未合成 effective_end 或开盘时间；原始事件、来源 SHA、完整 provenance 保留。调用方自称的 resume_date/verified/来源字段不能自行解除官方阻断。后续日期仍逐项经过原当前官方查询、有效分页/来源语义、真实合格 TDX 开盘活动及其它门禁；复牌日期本身不能证明正常交易。

新增22项确定性回归先 RED（13 failed / 9 passed）再 GREEN（22 passed），根代理直接相关150项独立回归 PASS，保留原19项历史停牌 fail-closed 与 ETF十倍价格/VIPDOC 精度回归。RH1 24项结构约束/新增行检查 PASS，287项既有债务保留。未改变 R1–R5、R2.1、策略 PIT、日线 NEXT_SESSION_OPEN 的 [09:30:00,09:31:00) Asia/Shanghai 分钟近似或交易算术；该窗口证明实际交易活动，不承诺09:30:00整点/具体订单成交。旧完整历史 PIT 停牌查询仍 UNKNOWN/fail-closed，R5仍为 Owner批准的验收合同调整。

独立新 wheel/sdist 已实际构建并通过原 package Gate、SIOS offline/Golden/ETF、原五项 mandatory live、冻结 TA相对兼容矩阵及 A1–A11 原定证据映射。结果如下：

| 本轮验证 | 实际结果 |
| --- | --- |
| package | 796 PASS，1原 optional MCP skip，15原 network deselect |
| SIOS provider | 67 PASS |
| SIOS Golden/ETF parity | 165 PASS，5默认 live opt-in skip |
| SIOS offline | 973 PASS，5默认 live opt-in skip |
| 五项原 mandatory live | 5 PASS，0 skip/xfail/deselect；54能力 PASS；129份本轮新 raw |
| 新安装 wheel 区间回归 / ETF Decimal exact | 22 PASS / 4 PASS |
| TradingAgents 相对冻结基线 | 123 PASS + 7 FAIL；失败节点与 message 同基线，legacy 5 PASS |
| 12点/74 raw 保存数据回放 | 新安装 wheel offline PASS，不能作为本轮新增 live 资格 |

73条实际命令保留，65条 mandatory 零退出；TA实际exit1及工具/换行/沙箱失败尝试保留，未隐藏。构建/twine、compile、静态、core/sdist/MCP/baostock/SIOS profiles、两 CLI、MCP server 等原检查通过。TA既有七项失败及正式依赖限制保留，未修改 TA 源码或依赖，TA pip check 为原非mandatory项，本轮未重跑。`gate/A1-A11-evidence-map.json`绑定同一工件与原测试，未扩张范围或改变成功标准。

本轮根代理独立只读复核：765文件源码、6 profiles各41个包成员、sdist 9 fixtures、六组JUnit/73命令与日志/退出/引用文件 SHA、129份实际live raw长度/哈希、source-before/after均一致。新的Gate规格与质量审查均 APPROVED，仅支持 PASS_CANDIDATE。旧live PASS未用于新候选PASS。原6007文件冻结var不变。

SIOS完整 `sios-source-vs-frozen.patch` 相对冻结commit `84fd54fae0740bc06b1d250afa4578be29556956`，31变化文件含18新增文件全文。真实 frozen 238文件 + 补丁可重建全部256个实际受测 source/config/test/docs 文件；patch apply/check均exit0，完整manifest、实际源码、重建目录和 `sios-tested-source.zip` 逐字节一致。source canonical SHA `573c8540e094e2c2c1d82788541a65d42424c707fa307a06c73d330483c75eb5`，runtime SHA `73376752616edc41b1560e0cea40a7cdb6190d2795c83dab34d19fdcffd4186f`，patch SHA `cbf403397631eed42fe542364587c3f75eb6150b88017c7390da2828644d4873`。本轮未修改 SIOS；实际组合受测身份已绑定，未用原GitHub HEAD或冻结源码替代。

新 CH canonical source SHA256（765文件映射）为 `{source_sha}`；`rework-source-manifest.json` 文件本身SHA `{manifest_file_sha}`，两者范围不同，NEW_SOURCE_SHA256使用前者。新 wheel SHA `{wheel_sha}`；新 sdist SHA `{summary['candidate_sdist_sha256']}`。新工件位于 `dist/owner-rework-r1`，六环境位于 `profiles/owner-rework-r1`，均独立于旧候选。交付 ZIP 包含新 wheel/sdist、完整765文件CH源码快照、SIOS完整快照/补丁/重建、全部实际证据及本审计副本。

保护复核：原CH HEAD `{protection['original_chstockdata_head']}`，早期758基线文件仅既有CR追加不同；用户预存产品修改保留。原SIOS HEAD `{protection['original_sios_head']}`未变；同期原仓一份决策文档修改及一份新增research文档与早期基线不同，本轮未写入原SIOS，已保留并如实记录，隔离受测256文件不变。原TA HEAD `{protection['original_ta_head']}`，986文件及原工作树状态未变。旧765文件source、旧wheel `3fd4f0b7334e310851495b8b13d4c7c55d21cde719acf9e00ff880ccb822f42e`、旧Step4 ZIP `a94de2c4ce72a4e98ffad9b0fa2dfdb93833623832078dcb5d2373b23d7e8b8d`未变。

```ini
{ini.rstrip()}
```

交接：v0.4.2 / R2.1，Owner minimum REWORK r1，新统一Gate PASS_CANDIDATE。原CH基线commit不变，工作树有原用户修改及本轮审计/证据追加；候选为无.git的隔离源码快照，无新commit。已确认缺陷修复、完整SIOS差异、新候选重新验证全部完成，mandatory批准范围无残留阻断，scope expansion NO；TA基线失败/依赖限制和来源能力边界保持可见。推荐下一动作仅Owner独立验收；到此停止，不merge、push、tag、PyPI或进入下一Phase。
'''
AUDIT.write_text(text+append, encoding='utf-8')
shutil.copyfile(AUDIT, OUT/'implementation-audit-final.md')
(OUT/'README.md').write_text(f'''# Owner Acceptance minimal REWORK r1

FIX_ONLY / PASS_CANDIDATE，Owner Acceptance PENDING；未授权发布、合并或下一 Phase。

先读 `owner-review-status.ini`、`implementation-audit-final.md`、`gate/A1-A11-evidence-map.json`。`gate/summary.json`、`gate/commands.json`及原始日志/JUnit/live raw为实际新候选证据；73条命令、65条mandatory零退出。

- 新wheel/sdist在 `artifacts/`，CH实际765文件完整源码在 `chstockdata-tested-source.zip`。
- `source-relative-old-rework.patch`仅为本轮3文件差异；765文件 canonical source SHA `{source_sha}`。manifest JSON 文件SHA另为 `{manifest_file_sha}`。
- `sios-source-vs-frozen.patch`含全部新增文件全文；冻结238文件在 `sios-frozen-source/`；准确重建256文件在 `sios-reconstructed-source-exact/`；`sios-source-manifest.json`和 `sios-tested-source.zip`绑定真实受测身份。
- `sios-reconstructed-source/`是首次受autocrlf影响的失败尝试，仅历史留证，不能作为正确源码。所有失败/RED/沙箱或检查器适配尝试均保留。
- `gate/live/`是本轮实际129响应/5mandatory/54能力；12点74raw replay仅offline。TA123 PASS+7同基线FAIL，不能声称全绿。
- `independent-new-gate-verification.json`、`original-protection-final.json`及 fresh Gate规格/质量审查为独立核验。原SIOS同期文档变化如实记录并保留。

日志中的绝对路径保留原执行身份，指向隔离工作根 `{WORK}`；ZIP内工件和完整源码快照可独立审查。SHA256SUMS覆盖全部交付文件（不自包含该清单）；ZIP另有SHA256侧车与交付receipt。
''', encoding='utf-8')
save('owner-rework-final-handoff.json', {
    'phase': 'v0.4.2 R1-R5 + R2.1', 'step': 'Owner minimum REWORK r1 complete, waiting independent acceptance',
    'flags': flags, 'original_ch_commit': protection['original_chstockdata_head'],
    'candidate_is_gitless_snapshot': True, 'new_commit': None,
    'candidate_source_sha256': source_sha, 'candidate_wheel_sha256': wheel_sha,
    'sios_complete_diff_and_reconstruction': True,
    'unresolved_mandatory_blockers': [], 'known_limits': summary['limitations'],
    'recommended_next_action': 'Owner independent acceptance only',
    'finished_at_utc': datetime.now(timezone.utc).isoformat(),
})
inventory = {p.relative_to(OUT).as_posix(): sha(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file()}
(OUT/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
shutil.copytree(OUT, DELIVERY)
delivered = {p.relative_to(DELIVERY).as_posix(): sha(p.read_bytes()) for p in sorted(DELIVERY.rglob('*')) if p.is_file()}
assert delivered == {**inventory, 'SHA256SUMS': sha((OUT/'SHA256SUMS').read_bytes())}
with zipfile.ZipFile(ZIP, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name in delivered:
        archive.write(DELIVERY/name, DELIVERY.name+'/'+name)
with zipfile.ZipFile(ZIP) as archive:
    assert archive.testzip() is None
    assert sorted(archive.namelist()) == sorted(DELIVERY.name+'/'+name for name in delivered)
    assert all(sha(archive.read(DELIVERY.name+'/'+name)) == digest for name, digest in delivered.items())
zip_sha = sha(ZIP.read_bytes())
ZIP.with_name(ZIP.name+'.sha256').write_text(f'{zip_sha}  {ZIP.name}\n', encoding='utf-8')
git = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-C', str(ROOT), 'rev-parse', 'HEAD'], stderr=subprocess.PIPE).decode('utf-8').strip()
assert git == protection['original_chstockdata_head']
receipt = dict(zip_path=str(ZIP), zip_sha256=zip_sha, zip_bytes=ZIP.stat().st_size,
               files=len(delivered), crc_and_every_member_sha_verified=True,
               copied_evidence_equal_origin=True, audit_path=str(AUDIT),
               source_sha256=source_sha, wheel_sha256=wheel_sha,
               source_snapshot_files=765, sios_snapshot_files=256,
               gate_verdict='PASS_CANDIDATE', flags=flags,
               commit_sha=git, no_new_commit=True, scope_expansion='NO',
               owner_acceptance='PENDING', next_phase_authorized='NO',
               created_at_utc=datetime.now(timezone.utc).isoformat())
receipt_path = DELIVERY_ROOT/'owner-acceptance-rework-r1-delivery-receipt.json'
receipt_path.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt))
