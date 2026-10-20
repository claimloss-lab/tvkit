import unittest

from tvkit import safety
from tvkit.apply import make_plan, restore_packages
from tvkit.profiles import from_dict, load_file
from tvkit.selftest import FakeDevice, _fake_android_tv
from tvkit.snapshot import Snapshot, compare, take

from tvkit.profiles import default_profile_dir

PROFILE_DIR = default_profile_dir()


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.device = _fake_android_tv()
        self.snap = take(self.device)
        self.profile = load_file(PROFILE_DIR / "toshiba-hayward.json")

    def test_plan_skips_uninstalled_packages(self):
        plan = make_plan(self.profile, self.snap, tier="safe")
        listed = {s.package for s in plan.steps}
        skipped = {s.package for s in plan.skipped}
        # installed on the fake device -> planned
        self.assertIn("com.google.android.tvrecommendations", listed)
        # not installed on the fake device -> skipped, never planned
        self.assertIn("com.iqiyi.i18n.tv", skipped)
        self.assertNotIn("com.iqiyi.i18n.tv", listed)

    def test_plan_never_contains_protected(self):
        plan = make_plan(self.profile, self.snap, tier="aggressive")
        for step in plan.steps:
            self.assertFalse(safety.is_protected(step.package, self.profile.protected_extra))

    def test_plan_skips_already_disabled(self):
        device = _fake_android_tv()
        device.disabled.add("com.google.android.videos")
        device.enabled.discard("com.google.android.videos")
        snap = take(device)
        plan = make_plan(self.profile, snap, tier="safe")
        self.assertIn(
            "already disabled",
            next(s.note for s in plan.skipped if s.package == "com.google.android.videos"),
        )

    def test_plan_only_filter(self):
        plan = make_plan(
            self.profile, self.snap, tier="aggressive", only=["com.android.vending"]
        )
        self.assertEqual([s.package for s in plan.steps], ["com.android.vending"])

    def test_plan_warns_about_side_effects(self):
        plan = make_plan(self.profile, self.snap, tier="balanced")
        self.assertTrue(any("Play Store" in w for w in plan.warnings))

    def test_tier_is_cumulative_in_plan(self):
        safe = {s.package for s in make_plan(self.profile, self.snap, tier="safe").steps}
        balanced = {s.package for s in make_plan(self.profile, self.snap, tier="balanced").steps}
        self.assertTrue(safe.issubset(balanced))
        self.assertIn("com.android.vending", balanced - safe)


class ApplyRollbackTests(unittest.TestCase):
    def test_apply_disables_and_reports(self):
        device = _fake_android_tv()
        profile = load_file(PROFILE_DIR / "toshiba-hayward.json")
        snap = take(device)
        plan = make_plan(profile, snap, tier="safe")
        for step in plan.steps:
            device.shell(f"pm disable-user --user 0 {step.package}")
        after = take(device)
        self.assertTrue(all(p in device.disabled for p in [s.package for s in plan.steps]))
        self.assertTrue(after.memory.total_kb > 0)

    def test_keep_package_disabled_is_a_gate_failure(self):
        device = _fake_android_tv()
        profile = load_file(PROFILE_DIR / "toshiba-hayward.json")
        victim = "com.ais.mimo.aisplay.tv"
        device.enabled.discard(victim)
        device.disabled.add(victim)
        snap = take(device)
        failures = safety.gate_failures(profile, snap, [])
        self.assertTrue(any(victim in f for f in failures))

    def test_no_home_is_a_gate_failure(self):
        device = FakeDevice({"ro.product.device": "x"}, [])
        profile = from_dict({"name": "t", "tiers": {"safe": []}})
        snap = take(device, include_packages=False)
        failures = safety.gate_failures(profile, snap, [])
        self.assertTrue(any("Home" in f for f in failures))

    def test_expected_disabled_but_still_enabled(self):
        device = _fake_android_tv()
        profile = from_dict({"name": "t", "tiers": {"safe": ["com.google.android.videos"]}, "keep": []})
        snap = take(device)
        failures = safety.gate_failures(profile, snap, ["com.google.android.videos"])
        self.assertTrue(any("still enabled" in f for f in failures))

    def test_restore_reenables(self):
        device = _fake_android_tv()
        device.enabled.discard("com.google.android.videos")
        device.disabled.add("com.google.android.videos")
        steps = restore_packages(device, ["com.google.android.videos"])
        self.assertEqual(steps[0].status, "ok")
        self.assertIn("com.google.android.videos", device.enabled)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_fields(self):
        snap = take(_fake_android_tv())
        self.assertEqual(snap.device_codename, "hayward")
        self.assertEqual(snap.sdk, 30)
        self.assertEqual(snap.storage.use_pct, 72)
        self.assertTrue(snap.android_tv)
        self.assertGreater(len(snap.packages_enabled), 5)

    def test_compare_rows(self):
        before = Snapshot(host="x")
        after = Snapshot(host="x")
        before.memory.available_kb = 100 * 1024
        after.memory.available_kb = 180 * 1024
        before.storage.use_pct = 86
        after.storage.use_pct = 72
        rows = dict((r[0], r) for r in compare(before, after))
        self.assertEqual(rows["RAM available"][3], "+80 MB")
        self.assertEqual(rows["Storage use"][3], "-14 pt")

    def test_fast_snapshot_skips_packages(self):
        snap = take(_fake_android_tv(), include_packages=False)
        self.assertEqual(snap.packages_enabled, [])


if __name__ == "__main__":
    unittest.main()
