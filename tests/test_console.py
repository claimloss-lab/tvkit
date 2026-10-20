"""Regression tests for the Windows CI failure: cp1252 stdout must never raise."""

import io
import unittest

from tvkit import console, report
from tvkit.apply import Plan, Result, Step
from tvkit.snapshot import Snapshot


def cp1252_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")


class ConsoleSafety(unittest.TestCase):
    def test_sanitize_rewrites_symbols_for_cp1252(self):
        stream = cp1252_stream()
        out = console.sanitize("\u2705 ok \u274c bad \u0394", stream)
        self.assertEqual(out, "[ok] ok [x] bad delta")

    def test_sanitize_is_identity_on_utf8(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        self.assertEqual(console.sanitize("\u2705", stream), "\u2705")

    def test_sym_picks_ascii_fallback(self):
        self.assertEqual(console.sym("\u2705", "[ok]", cp1252_stream()), "[ok]")
        self.assertEqual(console.sym("\u2705", "[ok]", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")), "\u2705")

    def test_write_never_raises_on_cp1252(self):
        stream = cp1252_stream()
        console.write("\u2705 done \u03a9", stream)  # Ω is also outside cp1252
        stream.flush()

    def test_can_encode(self):
        self.assertTrue(console.can_encode(cp1252_stream(), "plain ascii"))
        self.assertFalse(console.can_encode(cp1252_stream(), "\u2705"))


class ReportsAreAsciiSafe(unittest.TestCase):
    """Every report we print must survive a cp1252 console."""

    def test_result_report_cp1252(self):
        snap = Snapshot(host="h")
        result = Result(ok=True, plan=Plan("h", "p", "safe"), before=snap, after=snap)
        result.applied.append(Step("com.example.a", "disable", "safe", "ok"))
        text = report.result_report(result)
        cp1252_stream().write(text)  # raises if any character is unencodable

    def test_result_report_rollback_cp1252(self):
        snap = Snapshot(host="h")
        result = Result(ok=False, plan=Plan("h", "p", "safe"), failures=["boom"], before=snap, after=snap)
        text = report.result_report(result)
        cp1252_stream().write(text)
        self.assertIn("ROLLED BACK", text)

    def test_plan_report_cp1252(self):
        plan = Plan(host="h", profile="p", tier="safe")
        plan.steps.append(Step("com.example.a", "disable", "safe", "note"))
        plan.warnings.append("com.android.vending: side effect")
        plan.skipped.append(Step("com.example.b", "disable", "safe", "skipped", "not installed"))
        cp1252_stream().write(report.plan_report(plan))


if __name__ == "__main__":
    unittest.main()
