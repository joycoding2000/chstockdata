"""Offline acceptance evidence and negative controls; never contacts a vendor."""
from __future__ import annotations

from collections import Counter
import configparser
import contextlib
import csv
from datetime import datetime, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

import analyze
import screen
from screen import BASE, ROOT, LIMITS, digest, git, load, now, save


class ScreenEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="_verify_runtime_", dir=BASE)
        self.path = Path(self.temp.name).resolve()
        self.assertEqual(self.path.parent, BASE.resolve())

    def tearDown(self):
        self.assertEqual(self.path.parent, BASE.resolve())
        self.temp.cleanup()

    def fake_probe(self, ledger):
        probe = screen.Probe.__new__(screen.Probe)
        probe.ledger = ledger
        class NeverNetwork:
            def request(self, *args, **kwargs):
                raise AssertionError("Budget guard must reject before a request")
        probe.session = NeverNetwork()
        return probe

    def test_request_budget_before_network(self):
        p = self.fake_probe({"requests": [{}] * LIMITS["requests"], "blocked_hosts": [], "bytes_read": 0})
        with patch.object(screen, "BASE", self.path), self.assertRaisesRegex(AssertionError, "Request budget"):
            p.get("negative", "https://example.invalid")
        self.assertEqual(list(self.path.iterdir()), [])

    def test_byte_budget_before_network(self):
        p = self.fake_probe({"requests": [], "blocked_hosts": [], "bytes_read": LIMITS["total_bytes"] - 1})
        with patch.object(screen, "BASE", self.path), self.assertRaisesRegex(AssertionError, "byte reservation"):
            p.get("negative", "https://example.invalid", max_bytes=2)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_retry_limit_before_network(self):
        original = {"id": "original", "url": "https://example.invalid", "params": None,
                    "status": "REQUEST_FAILED", "retry_of": None}
        prior_retry = dict(original, id="retry", retry_of="original")
        p = self.fake_probe({"requests": [original, prior_retry], "blocked_hosts": [], "bytes_read": 0})
        with patch.object(screen, "BASE", self.path), self.assertRaises(AssertionError):
            p.get("retry-again", "https://example.invalid", retry_of="original")
        self.assertEqual(len(p.ledger["requests"]), 2)

    def test_access_restriction_stops_source(self):
        p = self.fake_probe({"requests": [], "blocked_hosts": ["example.invalid"], "bytes_read": 0})
        with patch.object(screen, "BASE", self.path):
            self.assertIsNone(p.get("no-bypass", "https://example.invalid/other-parameters"))
        self.assertEqual(p.ledger["requests"], [])
        self.assertEqual(json.loads((self.path / "skipped-routes.json").read_text(encoding="utf-8"))[0]["reason"], "STOPPED_ACCESS_RESTRICTION")

    def test_no_stale_calendar_substitution(self):
        ledger = load("requests.json")
        for symbol in ("sh000001", "sz399001"):
            label = "calendar-" + symbol + "-retry"
            row = next(x for x in ledger["requests"] if x["id"] == label)
            row["finished_at"] = (datetime.fromisoformat(row["finished_at"]) + timedelta(days=1)).isoformat()
            shutil.copyfile(BASE / row["file"], self.path / row["file"])
        (self.path / "requests.json").write_text(json.dumps(ledger), encoding="utf-8")
        with patch.object(screen, "BASE", self.path), patch.object(analyze, "BASE", self.path):
            with self.assertRaisesRegex(ValueError, "stale product date"):
                analyze.read_calendar()
        self.assertFalse(json.loads((self.path / "calendar.json").read_text(encoding="utf-8"))["qualified"])

    def test_real_window_and_warmup(self):
        c = load("calendar.json")
        self.assertEqual((c["s"], c["e"], c["s_minus_1"], c["s_minus_65"]),
                         ("2025-10-09", "2026-10-22", "2025-09-30", "2025-07-02"))
        self.assertEqual([len(c[k]) for k in ("nav_dates", "technical_warmup_dates", "first_amount20_dates", "signal_dates")], [252, 65, 20, 253])
        self.assertEqual(c["first_amount20_dates"][0], "2025-09-03")
        self.assertEqual(c["local_lag_market_days"], 16)
        self.assertEqual(len(set(c["nav_dates"])), 252)

    def test_every_response_identity_and_budget(self):
        ledger = load("requests.json")
        self.assertLessEqual(len(ledger["requests"]), LIMITS["requests"])
        self.assertEqual(len({x["id"] for x in ledger["requests"]}), len(ledger["requests"]))
        retries = Counter(x["retry_of"] for x in ledger["requests"] if x["retry_of"])
        self.assertTrue(all(n <= 1 for n in retries.values()))
        for row in ledger["requests"]:
            plan = load("plan-" + row["id"] + ".json")
            self.assertTrue(all(plan[k] == row[k] for k in plan))
            self.assertLessEqual(row["bytes"], LIMITS["single_bytes"])
            if row.get("file"):
                data = (BASE / row["file"]).read_bytes()
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(digest(data), row["sha256"])
        self.assertEqual(sum(x["bytes"] for x in ledger["requests"]), ledger["bytes_read"])
        self.assertLessEqual(ledger["bytes_read"], LIMITS["total_bytes"])

    def test_controls_not_replaced_and_never_promoted(self):
        registered = load("pe-controls.json")
        results = load("pe-analysis.json")
        reqs = load("requests.json")["requests"]
        self.assertEqual([x["security"] for x in registered["cases"]], ["SH:600519", "SZ:000002"])
        self.assertLess(registered["registered_at"], min(x["registered_at"] for x in reqs if x["id"].startswith("pe-em-")))
        for original, actual in zip(registered["cases"], results["controls"], strict=True):
            self.assertEqual(set(original["dates"]), {r["date"] for r in actual["fixed_cases"]})
            self.assertTrue(all(not r["PIT_qualified"] for r in actual["fixed_cases"]))
            self.assertEqual(actual["EM_date_coverage"], "253/253")
            self.assertEqual(actual["baidu_overlap"], 243)
            self.assertEqual(len(actual["baidu_required_missing_days"]), 10)
            self.assertTrue(all(x["strict_prior_market_close"] < x["announcement_date"] for x in actual["strict_pre_announcement_diagnostics"]))
        self.assertEqual(results["controls"][1]["negative_pe_rows"], 253)

    def test_old_regression_is_separate_and_limited(self):
        r = load("pe-analysis.json")["old_regression_control"]
        self.assertEqual(r["fixed_trade_date"], "2020-01-09")
        self.assertEqual(Decimal(r["recalculated_ttm"]), Decimal("479203728.07"))
        self.assertGreater(Decimal(r["recalculated_pe"]), 0)
        self.assertLess(Decimal(r["baidu_ttm_pe"]), 0)
        self.assertIn("not a stored original", r["annual_2018_evidence_limitation"]["kind"])
        from lxml import html
        original = html.fromstring((ROOT / "docs/audits/evidence/2026-10-20-w5h-r2/sina_600518_2019q3_original.raw").read_bytes()).text_content()
        self.assertIn("公告日期:2019-10-30", original)
        self.assertIn("33,173,948.69", original)
        self.assertIn("689,158,719.06", original)
        for row in r["reused_files"]:
            self.assertEqual(digest((ROOT / row["path"]).read_bytes()), row["sha256"])

    def test_universe_denominators_do_not_hide_unknowns(self):
        u = load("universe.json")
        with (BASE / "daily-coverage.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 253)
        self.assertEqual(sum(r["role"] == "NAV" for r in rows), 252)
        self.assertEqual(u["window_relevant_distinct_ids"], 5248)
        self.assertEqual(len(u["window_relevant_terminated_ids"]), 25)
        self.assertEqual(rows[1]["observed_candidate_distinct_ids"], "5157")
        self.assertEqual(rows[-1]["observed_candidate_distinct_ids"], "5223")
        self.assertTrue(all(r["certified_U_size"] == "UNKNOWN" and r["certified_complete_U_day"] == "0" for r in rows))
        self.assertTrue(all(r["historical_industry_qualified_rows"] == "0" for r in rows))
        boundary = load("boundary-controls.json")
        self.assertEqual(boundary["listing"]["security"], "SH:601026")
        self.assertEqual(boundary["exit"]["security"], "SZ:300280")
        self.assertFalse(boundary["industry_migration"]["not_applicable_claimed"])

    def test_offline_replay_matches_saved_analysis(self):
        names = ("pe-analysis.json", "universe.json", "boundary-controls.json", "daily-coverage.csv")
        before = {name: digest((BASE / name).read_bytes()) for name in names}
        with contextlib.redirect_stdout(io.StringIO()):
            analyze.pe()
            analyze.universe()
        self.assertEqual(before, {name: digest((BASE / name).read_bytes()) for name in names})

    def test_authorities_and_tracked_tree_preserved(self):
        for row in load("authority-identities.json"):
            self.assertEqual(digest(Path(row["path"]).read_bytes()), row["sha256"])
        before = load("before.json")
        self.assertEqual(git("rev-parse", "HEAD").decode().strip(), before["head"])
        self.assertEqual(digest(git("diff", "HEAD", "--binary")), before["tracked_diff_sha256"])
        self.assertEqual(digest(git("diff", "--cached", "--binary")), before["index_diff_sha256"])

    def test_report_decisions_match_actual_evidence(self):
        report = (ROOT / "docs/audits/2026-10-22-s07-free-supply-decisive-screen.md").read_text(encoding="utf-8")
        blocks = [s.split("```", 1)[0] for s in report.split("```ini\n")[1:]]
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string("[screen]\n" + "\n".join(blocks))
        values = parser["screen"]
        c, ledger = load("calendar.json"), load("requests.json")
        self.assertEqual(values["REAL_S07_E"], c["e"])
        self.assertEqual(values["REAL_S07_S"], c["s"])
        self.assertEqual(values["FREE_PE_TTM_PIT_VERDICT"], load("pe-analysis.json")["verdict"])
        self.assertIn(str(len(ledger["requests"])) + "_OF_120", values["REQUEST_BUDGET_USED"])
        self.assertIn(str(ledger["bytes_read"]) + "_OF_100000000", values["REQUEST_BUDGET_USED"])
        for key in ("PRODUCTION_IMPLEMENTATION_AUTHORIZED", "PRODUCT_SCOPE_CHANGED", "GIT_COMMIT", "GIT_PUSH"):
            self.assertEqual(values[key], "NO")
        self.assertEqual(values["MISHI_S07_HISTORICAL_GATE"], "NOT_PASSED")
        self.assertEqual(values["OWNER_REVIEW_REQUIRED"], "YES")
        self.assertIn("CURRENT_DECISION", values)
        self.assertEqual(values["CURRENT_DECISION"], "INVESTIGATE")


if __name__ == "__main__":
    transcript = io.StringIO()
    with patch.object(socket.socket, "connect", side_effect=AssertionError("OFFLINE_NETWORK_DISABLED")), \
         patch.object(socket, "create_connection", side_effect=AssertionError("OFFLINE_NETWORK_DISABLED")):
        result = unittest.TextTestRunner(stream=transcript, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScreenEvidence))
    ledger = load("requests.json")
    summary = {"verified_at": now(), "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "passed": result.wasSuccessful(), "network_disabled_for_verification": True,
        "request_attempts": len(ledger["requests"]), "body_bytes": ledger["bytes_read"],
        "largest_response_bytes": max(x["bytes"] for x in ledger["requests"]),
        "explicit_retries": sum(bool(x["retry_of"]) for x in ledger["requests"]),
        "outcomes": dict(Counter(x["status"] for x in ledger["requests"])),
        "head": git("rev-parse", "HEAD").decode().strip(),
        "tracked_status": git("status", "--porcelain=v1", "--untracked-files=no").decode("utf-8"),
        "temporary_test_runtime_cleaned": not list(BASE.glob("_verify_runtime_*")),
        "production_gate": "NOT_PASSED"}
    (BASE / "verification.txt").write_text(transcript.getvalue(), encoding="utf-8")
    save("verification.json", summary)
    report = ROOT / "docs/audits/2026-10-22-s07-free-supply-decisive-screen.md"
    files = [p for p in sorted(BASE.iterdir()) if p.is_file() and p.name != "manifest.json"]
    save("manifest.json", {"created_at": now(), "head": summary["head"],
        "report": {"path": str(report.relative_to(ROOT)), "sha256": digest(report.read_bytes())},
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in files],
        "excluded": ["manifest.json itself", "temporary verification runtime", "Python bytecode cache"],
        "status": git("status", "--porcelain=v1", "--untracked-files=normal").decode("utf-8"),
        "offline_inspection_failure_preserved": {"type": "SyntaxError", "cause": "Assignment expression in a one-off comprehension iterable",
            "effect": "Inspection command only; no network or evidence mutation; replaced by explicit offline analyzer"}})
    print(transcript.getvalue())
    print(json.dumps(summary, ensure_ascii=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
