"""Bounded read-only source/consumer audit; never alters product or contracts."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
OLD = ROOT / "docs/audits/evidence/2026-10-09-v0.4.2-unified-gate"
DATA = ROOT / ".rh3a2-vipdoc"
WHEEL = ROOT / "dist/v042-unified/chstockdata-0.4.2-py3-none-any.whl"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def identity():
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    excluded = OUT.relative_to(ROOT).as_posix() + "/"
    files = {n: sha((ROOT / n).read_bytes()) for n in names if n and (ROOT / n).is_file() and not n.startswith(excluded)}
    with zipfile.ZipFile(WHEEL) as archive:
        members = {n: sha(archive.read(n)) for n in archive.namelist() if n.startswith("chstockdata/") and not n.endswith("/")}
    matches = {n: sha((ROOT / "src" / n).read_bytes()) == h for n, h in members.items()}
    assert all(matches.values())
    assert sha(WHEEL.read_bytes()) == "b76b065a06cd1d91868880a7b57584f598b6fd4cb42931e9a33700bc99a88c7a"
    result = {"at": datetime.now(timezone.utc).isoformat(), "head": git("rev-parse", "HEAD"),
              "branch": git("branch", "--show-current"), "status": git("status", "--short"),
              "existing_files": files, "wheel_sha256": sha(WHEEL.read_bytes()), "runtime_matches": matches}
    if (OUT / "initial-identity.json").exists():
        before = json.loads((OUT / "initial-identity.json").read_text(encoding="utf-8"))
        changed = [n for n, h in before["existing_files"].items() if files.get(n) != h]
        result["previous_file_changes"] = changed
        assert not changed, changed
        save("final-identity.json", result)
    else:
        save("initial-identity.json", result)
    print("wheel/source matched", len(matches), "preserved existing files", len(files))


def local():
    sys.path.insert(0, str(ROOT / "src"))
    from chstockdata.vipdoc_history import load_vipdoc_daily
    from chstockdata.trading_calendar import local_is_trading_day
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    queries = [("sh", c, "2026-09-11") for c in ("510300", "518880", "511010")]
    queries += [("sz", "159915", "2026-09-11"), ("sh", "688432", "2026-08-31"),
                ("sh", "688432", "2026-09-11"), ("sh", "688432", "2026-09-14"),
                ("sz", "000002", "2016-01-04"), ("sz", "000002", "2016-07-04"),
                ("sz", "000002", "2015-12-18"), ("sh", "510300", "2026-09-13"),
                ("sh", "510300", "2000-01-03"), ("sh", "510300", "2000-01-04"),
                ("sz", "999990", "2026-09-11")]
    results = []
    for market, code, day in queries:
        path = DATA / market / "lday" / f"{market}{code}.day"
        raw = path.read_bytes() if path.is_file() else b""
        rows = list(struct.iter_unpack("<IIIIIfII", raw)) if raw else []
        target = int(day.replace("-", ""))
        hits = [r for r in rows if r[0] == target]
        previous = [r for r in rows if r[0] < target]
        following = [r for r in rows if r[0] > target]
        frame = load_vipdoc_daily(code, day, day, market=market, root=DATA)
        valid = len(hits) == 1 and all(hits[0][i] > 0 for i in (1, 2, 3, 4, 5, 6)) and hits[0][2] >= max(hits[0][1], hits[0][4]) and hits[0][3] <= min(hits[0][1], hits[0][4])
        results.append({"market": market, "code": code, "date": day, "file_exists": path.is_file(),
                        "file_sha256": sha(raw) if raw else None, "file_records": len(rows),
                        "record_fields": ["date", "open", "high", "low", "close", "amount", "volume", "reserved_unqualified"],
                        "raw_rows": hits, "parsed_rows": [] if frame is None else json.loads(frame.to_json(orient="records", date_format="iso")),
                        "previous_record_date": previous[-1][0] if previous else None,
                        "next_record_date": following[0][0] if following else None,
                        "market_open": local_is_trading_day(day, root=DATA),
                        "trade_occurred": True if valid else None,
                        "suspension_from_bar": "UNKNOWN (positive volume does not exclude intraday suspension)",
                        "pit_preopen": "UNPROVEN", "local_read_at": datetime.now(timezone.utc).isoformat()})
    save("tdx-facts.json", {"manifest": {k: manifest.get(k) for k in ("schema_version", "source_url", "source_last_modified", "downloaded_at", "zip_sha256")}, "queries": results})
    for r in results:
        print(r["code"], r["date"], "bar", bool(r["raw_rows"]), "trade_occurred", r["trade_occurred"], "market_open", r["market_open"])


def sources():
    import requests
    session = requests.Session()
    session.trust_env = False
    requests_to_make = [
        ("tdx-official-vipdata", "https://www.tdx.com.cn/article/vipdata.html", None),
        ("tdx-official-realtime", "https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hjbidnohpjn4/mindoc-1hlir5r0t9hgc.html", None),
        ("sse-suspend", "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-08-29/688432_20260829_8CDF.pdf", None),
        ("vanke-issuer-history", "https://static.cninfo.com.cn/finalpage/2016-07-02/1202445845.PDF", None),
        ("vanke-fund-disclosure", "https://static.cninfo.com.cn/finalpage/2016-08-29/1202629464.PDF", None),
        ("sse-resume-query", "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do",
         {"isPagination": "true", "productId": "688432", "beginDate": "2026-09-11", "endDate": "2026-09-14", "pageHelp.pageSize": "100", "pageHelp.pageNo": "1"}),
    ]
    journal = []
    for name, url, params in requests_to_make:
        item = {"name": name, "url": url, "params": params, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        try:
            response = session.get(url, params=params, headers={"Referer": "https://www.sse.com.cn/", "User-Agent": "Mozilla/5.0"}, timeout=20)
            item.update(http_status=response.status_code, content_type=response.headers.get("Content-Type"), bytes=len(response.content), sha256=sha(response.content))
            suffix = ".pdf" if response.content.startswith(b"%PDF") else ".txt"
            (OUT / (name + suffix)).write_bytes(response.content)
            if name == "sse-resume-query" and response.status_code == 200:
                payload = response.json()
                save("sse-resume-response.json", payload)
                item["matching_announcements"] = [r for r in payload.get("result", []) if "复牌" in str(r)]
        except Exception as exc:
            item["error_type"] = type(exc).__name__
        journal.append(item)
        save("source-requests.json", journal)
        print(name, item.get("http_status", item.get("error_type")), item.get("bytes"), flush=True)


def consumer():
    sys.path.insert(0, str(ROOT / "build/v042-unified/sios/src"))
    import chstockdata
    from systematic_investing.adapters.chstockdata.provider import ChStockDataProvider, LibraryChStockDataClient
    from systematic_investing.data.ports import TradabilityRequest
    from systematic_investing.domain.identifiers import InstrumentId
    with zipfile.ZipFile(WHEEL) as archive:
        installed = Path(chstockdata.__file__).parent
        names = [n for n in archive.namelist() if n.startswith("chstockdata/") and not n.endswith("/")]
        assert all((installed / Path(n).relative_to("chstockdata")).read_bytes() == archive.read(n) for n in names)
    provider = ChStockDataProvider(client=LibraryChStockDataClient(), clock=lambda: datetime.now(timezone.utc))
    results = []
    for instrument, day in [("XSHG:510300", "2026-09-11"), ("XSHE:159915", "2026-09-11"),
                            ("XSHG:518880", "2026-09-11"), ("XSHG:511010", "2026-09-11"),
                            ("XSHG:688432", "2026-08-31"), ("XSHG:688432", "2026-09-14"),
                            ("XSHE:000002", "2016-01-04"), ("XSHE:000002", "2016-07-04")]:
        result = provider.fetch_tradability(TradabilityRequest(instrument_ids=(InstrumentId.parse(instrument),), session_date=date.fromisoformat(day)))
        results.append({"instrument": instrument, "date": day, "is_success": result.is_success, "result": repr(result)})
        print(instrument, day, result.is_success, getattr(result, "message", ""), flush=True)
    # A diagnostic of the frozen mapper only: these payloads are NOT source data.
    # Even explicit close-time or later observed time is ignored for old sessions.
    probes = []
    for observed in (None, "2026-09-11T15:05:00+08:00", "2026-10-09T12:00:00+08:00"):
        payload = {"observed_at": observed, "information_available_at": "2026-09-11T15:05:00+08:00"}
        availability = provider._tradability_availability(payload=payload, session_date=date(2026, 9, 11), retrieved_at=datetime.now(timezone.utc))
        probes.append({"input": payload, "output": repr(availability), "diagnostic_only": True})
    save("sios-history-and-pit.json", {"wheel_sha256": sha(WHEEL.read_bytes()), "version": chstockdata.__version__, "import": chstockdata.__file__, "matched_runtime_members": len(names), "real_requests": results, "mapper_diagnostics": probes})


if __name__ == "__main__":
    {"identity": identity, "local": local, "sources": sources, "consumer": consumer}[sys.argv[1]]()
