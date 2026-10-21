"""Read-only, bounded W5-H-R3 inventory; writes only beside this script."""
import ctypes
import hashlib
import importlib.metadata
import json
import os
import socket
import struct
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPOS = [Path('D:/Dev/Projects') / n for n in ('chstockdata', 'mishi-radar', 'systematic-investing-os')]

def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def git(p, *args):
    r = subprocess.run(['git', '-c', f'safe.directory={p.as_posix()}', '-C', str(p), *args], capture_output=True, encoding='utf-8', errors='replace')
    return {'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}

def baseline():
    repos = {}
    for p in REPOS:
        tracked = git(p, 'ls-files', '-z')['stdout'].split('\0')
        fingerprints = {n: sha(p / n) for n in tracked if n and (p / n).is_file()}
        repos[p.name] = {'path': str(p), 'head': git(p, 'rev-parse', 'HEAD'), 'branch': git(p, 'branch', '--show-current'), 'status': git(p, 'status', '--porcelain=v1', '--untracked-files=all'), 'tracked_sha256': fingerprints}
    inputs = [Path('AGENTS.md'), *Path('docs').glob('*R3_2*'), *Path('docs').glob('*DR01_DR06*'), Path('docs/plans/2026-10-19-dual-consumer-supply-plan.md'), Path('docs/audits/2026-10-19-w5h-historical-financial-pit-feasibility.md'), Path('docs/audits/2026-10-20-w5h-r2-alternative-source-qualification.md')]
    save('before.json', {'at_utc': datetime.now(timezone.utc).isoformat(), 'repos': repos, 'inputs': {str(p): sha(p) for p in inputs}})
    print('baseline', {n: r['head']['stdout'].strip() for n, r in repos.items()})

def details(p):
    s = p.stat()
    return {'path': str(p), 'bytes': s.st_size, 'mtime_utc': datetime.fromtimestamp(s.st_mtime, timezone.utc).isoformat(), 'ctime_utc': datetime.fromtimestamp(s.st_ctime, timezone.utc).isoformat()}

def summarize(p, pattern='*'):
    if not p.exists():
        return {'path': str(p), 'status': 'MISSING'}
    try:
        fs = sorted(x for x in p.glob(pattern) if x.is_file())
        times = [x.stat().st_mtime for x in fs]
        return {'path': str(p), 'status': 'PRESENT' if fs else 'EMPTY', 'file_count': len(fs), 'total_bytes': sum(x.stat().st_size for x in fs), 'mtime_min_utc': datetime.fromtimestamp(min(times), timezone.utc).isoformat() if times else None, 'mtime_max_utc': datetime.fromtimestamp(max(times), timezone.utc).isoformat() if times else None, 'samples': [details(x) for x in (fs[:3] + fs[-3:] if len(fs) > 6 else fs)]}
    except OSError as e:
        return {'path': str(p), 'status': 'READ_FAILED', 'error': type(e).__name__}

def discover():
    start = time.monotonic()
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    drives = [f'{chr(65+i)}:/' for i in range(26) if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(f'{chr(65+i)}:/') == 3]
    seeds = [(Path(d), 0) for d in drives]
    # Explicit user data paths get a bounded deeper search even if root BFS hits budget.
    seeds += [(Path('C:/Users/Administrator') / n, 0) for n in ('Desktop', 'Documents', 'Downloads', 'OneDrive')]
    skip = {'.git', '.venv', 'node_modules', '__pycache__', '.codegraph', 'windows', '$recycle.bin', 'system volume information', 'programdata', '.codex', '.cache', 'appdata', '.ssh', '.aws', '.azure', '.config', '.vscode', 'winsxs', 'recovery'}
    q = deque(seeds)
    seen = set()
    found = []
    errors = []
    daydirs = {}
    visited = 0
    while q and visited < 22000 and time.monotonic() - start < 90:
        p, depth = q.popleft()
        key = str(p).lower()
        if key in seen or not p.exists():
            continue
        seen.add(key)
        visited += 1
        try:
            with os.scandir(p) as it:
                for x in it:
                    name = x.name.lower()
                    if x.is_dir(follow_symlinks=False):
                        if name == 'vipdoc':
                            found.append({'kind': 'vipdoc', 'path': x.path})
                        if depth < 6 and name not in skip and not x.is_symlink():
                            q.append((Path(x.path), depth + 1))
                    elif x.is_file(follow_symlinks=False):
                        if name.startswith('gpcw') and name.endswith(('.dat', '.zip')):
                            found.append({'kind': 'gpcw', **details(Path(x.path))})
                        elif name.endswith('.day'):
                            rec = daydirs.setdefault(str(p), {'count': 0, 'samples': []})
                            rec['count'] += 1
                            if len(rec['samples']) < 3:
                                rec['samples'].append(x.name)
        except OSError as e:
            errors.append({'path': str(p), 'error': type(e).__name__})
    save('discovery.json', {'drives': drives, 'max_depth_per_seed': 6, 'max_directories': 22000, 'max_seconds': 90, 'visited': visited, 'elapsed_seconds': time.monotonic()-start, 'pending_directories': len(q), 'queue_exhausted': not q, 'skipped_names': sorted(skip), 'found': found, 'day_directories': daydirs, 'errors': errors})
    return found, daydirs

def inventory(found, daydirs):
    roots = {Path('C:/new_hxzq_hc'), Path('C:/zd_zxzq_gm'), Path('.rh3a2-vipdoc').resolve()}
    roots.update(Path(x['path']).parent for x in found if x['kind'] == 'vipdoc')
    result = []
    for root in sorted(roots):
        base = root if (root / 'sh').exists() else root / 'vipdoc'
        rec = {'root': str(root), 'vipdoc_root': str(base), 'directories': [summarize(base / m / t) for m in ('sh', 'sz', 'bj') for t in ('lday', 'minline')], 'cw': summarize(base / 'cw'), 'gbbq': details(root / 'T0002/hq_cache/gbbq') if (root / 'T0002/hq_cache/gbbq').is_file() else {'status': 'MISSING'}}
        samples = []
        for market, code in [('sh', '600518'), ('sh', '600519'), ('sh', '000001'), ('sz', '000001')]:
            p = base / market / 'lday' / f'{market}{code}.day'
            if not p.is_file():
                continue
            b = p.read_bytes()
            if len(b) % 32 == 0 and b:
                first = struct.unpack('<IIIIIfII', b[:32])
                last = struct.unpack('<IIIIIfII', b[-32:])
                samples.append({**details(p), 'sha256': hashlib.sha256(b).hexdigest(), 'records': len(b)//32, 'first_raw': first, 'last_raw': last})
        rec['fixed_daily_samples'] = samples
        rec['client_executables'] = [details(p) for p in root.glob('*.exe') if any(n in p.name.lower() for n in ('tdx', 'tq', 'tdxw'))]
        result.append(rec)
    save('local_inventory.json', result)
    print('inventory', [(x['root'], [(d['path'], d.get('file_count')) for d in x['directories']], x['cw'].get('file_count')) for x in result])

def capabilities():
    modules = {}
    for n in ('mootdx', 'pytdx', 'chstockdata'):
        try:
            d = importlib.metadata.distribution(n)
            modules[n] = {'version': d.version, 'location': str(d.locate_file(''))}
        except importlib.metadata.PackageNotFoundError:
            modules[n] = {'installed': False}
    at = datetime.now(timezone.utc).isoformat()
    try:
        with socket.create_connection(('127.0.0.1', 17709), timeout=1):
            tq = {'status': 'TCP_CONNECTED', 'attempts': 1, 'at_utc': at}
    except OSError as e:
        tq = {'status': 'TCP_UNREACHABLE', 'attempts': 1, 'at_utc': at, 'error': type(e).__name__, 'errno': e.errno, 'winerror': getattr(e, 'winerror', None)}
    env = {k: v for k, v in os.environ.items() if ('VIPDOC' in k.upper() or k.upper().startswith(('TDX_', 'MOOTDX_'))) and not any(s in k.upper() for s in ('TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'CREDENTIAL'))}
    save('local_capabilities.json', {'packages': modules, 'tq': tq, 'path_environment': env})
    print('capabilities', modules, tq)

if __name__ == '__main__':
    baseline()
    found, daydirs = discover()
    inventory(found, daydirs)
    capabilities()
