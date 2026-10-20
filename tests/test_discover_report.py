import unittest
from unittest import mock

from tvkit import discover
from tvkit.apply import Plan, Result, Step
from tvkit import report
from tvkit.snapshot import Snapshot


class TargetExpansion(unittest.TestCase):
    def test_slash_24(self):
        hosts = discover.expand_targets(["192.168.1"])
        self.assertEqual(len(hosts), 254)
        self.assertEqual(hosts[0], "192.168.1.1")
        self.assertEqual(hosts[-1], "192.168.1.254")

    def test_range(self):
        self.assertEqual(discover.expand_targets(["10.0.0.5-7"]), ["10.0.0.5", "10.0.0.6", "10.0.0.7"])

    def test_cidr(self):
        self.assertEqual(len(discover.expand_targets(["10.0.0.0/29"])), 6)

    def test_single_host(self):
        self.assertEqual(discover.expand_targets(["10.1.1.1"]), ["10.1.1.1"])

    def test_dedupe(self):
        self.assertEqual(discover.expand_targets(["10.1.1.1", "10.1.1.1"]), ["10.1.1.1"])

    def test_blank_ignored(self):
        self.assertEqual(discover.expand_targets(["", "  "]), [])


class CandidateModel(unittest.TestCase):
    def test_adb_ready_flag(self):
        self.assertTrue(discover.Candidate("1.2.3.4", [5555, 8008]).adb_ready)
        self.assertFalse(discover.Candidate("1.2.3.4", [8008]).adb_ready)

    def test_label_falls_back(self):
        self.assertEqual(discover.Candidate("1.2.3.4", [8008]).label, "(unnamed TV)")

    def test_as_dict(self):
        data = discover.Candidate("1.2.3.4", [5555], name="TV", cast_version="12").as_dict()
        self.assertEqual(data["name"], "TV")
        self.assertTrue(data["adb_ready"])


class DiscoveryScan(unittest.TestCase):
    def test_probe_host_returns_none_when_all_ports_closed(self):
        with mock.patch.object(discover, "_scan_port", return_value=False):
            self.assertIsNone(discover.probe_host("10.0.0.1"))

    def test_probe_host_reads_cast_name(self):
        with mock.patch.object(discover, "_scan_port", side_effect=lambda h, p, t: p in (8008, 5555)):
            with mock.patch.object(discover, "_cast_info", return_value={"name": "Living Room", "version": 12}):
                cand = discover.probe_host("10.0.0.1")
        self.assertEqual(cand.name, "Living Room")
        self.assertTrue(cand.adb_ready)


class Reports(unittest.TestCase):
    def test_plan_report_lists_packages(self):
        plan = Plan(host="1.2.3.4", profile="p", tier="safe")
        plan.steps.append(Step("com.example.a", "disable", "safe"))
        plan.warnings.append("com.example.a: side effect")
        text = report.plan_report(plan)
        self.assertIn("com.example.a", text)
        self.assertIn("side effect", text)

    def test_result_report_marks_rollback(self):
        snap = Snapshot(host="h")
        result = Result(ok=False, plan=Plan("h", "p", "safe"), failures=["boom"], before=snap, after=snap)
        self.assertIn("ROLLED BACK", report.result_report(result))

    def test_json_shapes(self):
        snap = Snapshot(host="h")
        self.assertIn('"host": "h"', report.as_json(snap))
        plan = Plan(host="h", profile="p", tier="safe")
        self.assertIn('"tier": "safe"', report.as_json(plan))

    def test_health_notes_flag_low_ram(self):
        snap = Snapshot(host="h")
        snap.memory.total_kb = 900 * 1024
        snap.memory.swap_total_kb = 500 * 1024
        snap.memory.swap_free_kb = 100 * 1024
        notes = " ".join(report.health_notes(snap))
        self.assertIn("RAM", notes)
        self.assertIn("Swap", notes)


if __name__ == "__main__":
    unittest.main()
