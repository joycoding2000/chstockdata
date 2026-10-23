"""Offline-only helpers for the final bounded F2 qualification."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / "2026-10-21-w5h-f2-source-closure"
F2 = HERE.parent / "2026-10-21-w5h-f2"
SCANS = ("1216741269", "1216869640", "1217078313", "1217949874", "1218110511")
REPLIES = ("1216741268", "1216741273", "1217078312", "1217078316", "1217949872", "1217949876")


def deny_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
        raise RuntimeError("NEW_NETWORK_REQUESTS=NO: " + event)


sys.addaudithook(deny_network)
sys.dont_write_bytecode = True


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def compact(text):
    return "".join(text.split())


def statement_periods(plan):
    """Retain an explicit opening date instead of converting it to prior year end."""
    sid,n,field=plan['id'],plan['physical_page'],plan['field']
    annual=n<20 or sid=='1216741269'
    current='2022-12-31' if annual else '2023-06-30' if sid=='1217949874' else '2023-03-31'
    prior='2021-12-31' if annual else '2022-12-31' if field=='EQ' else '2022'+current[4:]
    header=compact(read(HERE/'cell-ocr'/f'{sid}-p{n}-header-zh.json')['text'])
    if field=='EQ' and not annual and current[:4]+'年1月1日' in header:
        prior=current[:4]+'-01-01'
    return annual,current,prior
