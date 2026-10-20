import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tvkit import cli, registry
from tvkit.selftest import _fake_android_tv


class CliEndToEnd(unittest.TestCase):
    """Drive the real CLI against the simulated TV (no hardware needed)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tvkit-test-")
        self.env = mock.patch.dict(os.environ, {"TVKIT_HOME": self.tmp}, clear=False)
        self.env.start()
        self.device = _fake_android_tv()
        self.patch = mock.patch.object(cli, "_connect", lambda args: self.device)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.env.stop()

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_probe(self):
        code, out = self.run_cli(["probe", "--host", "10.0.0.9"])
        self.assertEqual(code, 0)
        self.assertIn("Toshiba TT_Fitness TV", out)
        self.assertIn("Detected profile: toshiba-hayward", out)

    def test_probe_registers_device(self):
        self.run_cli(["probe", "--host", "10.0.0.9"])
        devices = registry.load()
        self.assertTrue(devices)
        entry = next(iter(devices.values()))
        self.assertEqual(entry["host"], "10.0.0.9")
        self.assertEqual(entry["profile"], "toshiba-hayward")

    def test_probe_json(self):
        code, out = self.run_cli(["probe", "--host", "10.0.0.9", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["props"]["ro.product.device"], "hayward")
        self.assertTrue(data["android_tv"])

    def test_plan_writes_nothing(self):
        before = set(self.device.disabled)
        code, out = self.run_cli(["plan", "--host", "10.0.0.9", "--tier", "safe"])
        self.assertEqual(code, 0)
        self.assertIn("com.google.android.tvrecommendations", out)
        self.assertEqual(set(self.device.disabled), before)

    def test_apply_changes_and_journals(self):
        code, out = self.run_cli(["apply", "--host", "10.0.0.9", "--tier", "safe", "--yes"])
        self.assertEqual(code, 0, out)
        self.assertIn("Result - OK", out)
        self.assertIn("com.google.android.videos", self.device.disabled)
        journals = list((Path(self.tmp) / "journal").glob("*.json"))
        self.assertEqual(len(journals), 1)
        data = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertTrue(data["ok"])
        self.assertIn("com.google.android.videos", data["applied"])

    def test_apply_dry_run(self):
        before = set(self.device.disabled)
        code, out = self.run_cli(["apply", "--host", "10.0.0.9", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertEqual(set(self.device.disabled), before)

    def test_apply_requires_yes_when_not_a_tty(self):
        with mock.patch("sys.stdin") as fake_stdin:
            fake_stdin.isatty.return_value = False
            code, out = self.run_cli(["apply", "--host", "10.0.0.9", "--tier", "safe"])
        self.assertEqual(code, 2)
        self.assertIn("--yes", out)

    def test_restore_last(self):
        self.run_cli(["apply", "--host", "10.0.0.9", "--tier", "safe", "--yes"])
        code, out = self.run_cli(["restore", "--host", "10.0.0.9", "--last"])
        self.assertEqual(code, 0, out)
        self.assertIn("com.google.android.videos", self.device.enabled)

    def test_restore_single_package(self):
        self.device.enabled.discard("com.android.vending")
        self.device.disabled.add("com.android.vending")
        code, _ = self.run_cli(
            ["restore", "--host", "10.0.0.9", "--package", "com.android.vending"]
        )
        self.assertEqual(code, 0)
        self.assertIn("com.android.vending", self.device.enabled)

    def test_audit_report_file(self):
        out_file = Path(self.tmp) / "audit.md"
        code, _ = self.run_cli(["audit", "--host", "10.0.0.9", "--out", str(out_file)])
        self.assertEqual(code, 0)
        text = out_file.read_text(encoding="utf-8")
        self.assertIn("# tvkit audit", text)
        self.assertIn("Profile match", text)

    def test_profiles_lint_command(self):
        code, out = self.run_cli(["profiles"])
        self.assertEqual(code, 0, out)
        self.assertIn("lint clean", out)

    def test_profile_dir_override(self):
        alt = Path(self.tmp) / "profiles"
        alt.mkdir()
        (alt / "only.json").write_text(
            json.dumps({"name": "only", "tiers": {"safe": ["com.example.a"]}}), encoding="utf-8"
        )
        code, out = self.run_cli(["--profile-dir", str(alt), "profiles"])
        self.assertEqual(code, 0)
        self.assertIn("1 profile(s)", out)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tvkit-reg-")
        self.env = mock.patch.dict(os.environ, {"TVKIT_HOME": self.tmp}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_remember_and_find(self):
        device = _fake_android_tv()
        from tvkit.snapshot import take

        snap = take(device)
        key = registry.remember(device, snap, "toshiba-hayward")
        self.assertTrue(registry.find(key))
        self.assertTrue(registry.find("toshiba"))
        self.assertIsNone(registry.find("nope"))

    def test_key_without_mac_is_slug(self):
        self.assertEqual(registry.key_for(None, "Toshiba TT_Fitness TV"), "toshiba-tt-fitness-tv")


if __name__ == "__main__":
    unittest.main()


class ScreenshotCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tvkit-shot-")
        self.env = mock.patch.dict(os.environ, {"TVKIT_HOME": self.tmp}, clear=False)
        self.env.start()
        self.device = _fake_android_tv()
        self.patch = mock.patch.object(cli, "_connect", lambda args: self.device)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.env.stop()

    def test_screenshot_saves_png(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["screenshot", "--host", "10.0.0.9", "--out", self.tmp])
        self.assertEqual(code, 0, buf.getvalue())
        files = list(Path(self.tmp).glob("*.png"))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].read_bytes().startswith(b"\x89PNG"))
