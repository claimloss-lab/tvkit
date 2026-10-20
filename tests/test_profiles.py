import json
import unittest

from tvkit import profiles as P
from tvkit import safety

from tvkit.profiles import default_profile_dir

PROFILE_DIR = default_profile_dir()


class ProfileLoading(unittest.TestCase):
    def test_every_shipped_profile_loads(self):
        loaded = P.load_all(PROFILE_DIR)
        self.assertGreaterEqual(len(loaded), 5)
        for profile in loaded:
            self.assertTrue(profile.name)
            self.assertEqual(set(profile.tiers), set(P.TIER_ORDER))

    def test_tiers_are_cumulative(self):
        profile = P.load_file(PROFILE_DIR / "generic-androidtv.json")
        self.assertEqual(profile.packages_for("safe"), profile.tiers["safe"])
        self.assertEqual(
            profile.packages_for("balanced"),
            profile.tiers["safe"] + profile.tiers["balanced"],
        )
        self.assertEqual(len(profile.packages_for("aggressive")), len(profile.all_packages()))

    def test_unknown_tier_rejected(self):
        profile = P.load_file(PROFILE_DIR / "generic-androidtv.json")
        with self.assertRaises(P.ProfileError):
            profile.packages_for("insane")

    def test_unknown_tier_key_rejected_at_load(self):
        with self.assertRaises(P.ProfileError):
            P.from_dict({"name": "x", "tiers": {"yolo": ["a.b"]}})

    def test_matching_picks_specific_over_generic(self):
        loaded = P.load_all(PROFILE_DIR)
        props = {"ro.product.device": "hayward", "ro.product.manufacturer": "Toshiba"}
        self.assertEqual(P.select(loaded, props).name, "toshiba-hayward")
        self.assertEqual(P.select(loaded, {"ro.product.device": "unknownbox"}).name, "generic-androidtv")

    def test_explicit_name_wins(self):
        loaded = P.load_all(PROFILE_DIR)
        self.assertEqual(P.select(loaded, {}, "operator-box").name, "operator-box")

    def test_unknown_name_raises(self):
        loaded = P.load_all(PROFILE_DIR)
        with self.assertRaises(P.ProfileError):
            P.select(loaded, {}, "does-not-exist")


class ProfileLint(unittest.TestCase):
    def test_all_shipped_profiles_are_lint_clean(self):
        for profile in P.load_all(PROFILE_DIR):
            problems = [p for p in safety.lint_profile(profile) if "(info)" not in p]
            self.assertEqual(problems, [], f"{profile.name}: {problems}")

    def test_protected_package_is_flagged(self):
        bad = P.from_dict({"name": "bad", "tiers": {"safe": ["com.google.android.apps.mediashell"]}})
        problems = safety.lint_profile(bad)
        self.assertTrue(any("PROTECTED" in p for p in problems))

    def test_duplicate_package_flagged(self):
        dup = P.from_dict({
            "name": "dup",
            "tiers": {"safe": ["com.example.a"], "balanced": ["com.example.a"]},
        })
        problems = safety.lint_profile(dup)
        self.assertTrue(any("both" in p for p in problems))

    def test_keep_and_disable_overlap_flagged(self):
        overlap = P.from_dict({
            "name": "overlap",
            "tiers": {"safe": ["com.example.a"]},
            "keep": ["com.example.a"],
        })
        problems = safety.lint_profile(overlap)
        self.assertTrue(any("keep" in p for p in problems))


class SafetyRules(unittest.TestCase):
    def test_protected_globs(self):
        for pkg in (
            "com.google.android.tungsten.setupwraith",
            "com.google.android.apps.mediashell",
            "com.mediatek.wwtv.tvcenter",
            "com.cvte.tv.fac.engineer",
            "com.at.factory.something",
            "mediatek.factorymenu.ui",
            "com.google.android.gms",
            "android",
        ):
            self.assertTrue(safety.is_protected(pkg), pkg)

    def test_ordinary_apps_are_not_protected(self):
        for pkg in ("com.google.android.videos", "com.android.vending", "com.tcl.browser"):
            self.assertFalse(safety.is_protected(pkg), pkg)

    def test_protected_extra_is_honoured(self):
        self.assertTrue(safety.is_protected("com.vt.tv.aiot", ["com.vt.tv.aiot"]))
        self.assertTrue(safety.is_protected("com.vendor.anything", ["com.vendor.*"]))

    def test_warnings_exist_for_risky_but_allowed_packages(self):
        self.assertTrue(safety.warnings_for("com.android.vending"))
        self.assertEqual(safety.warnings_for("com.google.android.videos"), [])

    def test_is_launcher(self):
        self.assertTrue(safety.is_launcher("com.gathin.tvhome", "com.gathin.tvhome/.MainActivity"))
        self.assertFalse(safety.is_launcher("com.google.android.tvlauncher", "com.gathin.tvhome/.MainActivity"))


class ShippedProfileContent(unittest.TestCase):
    def test_hisense_vendor_telemetry_is_protected(self):
        profile = P.load_file(PROFILE_DIR / "hisense-mt.json")
        for pkg in ("com.hisense.tv.smartsense", "com.vt.tv.smartsense.ui", "com.vt.tv.aiot"):
            self.assertTrue(safety.is_protected(pkg, profile.protected_extra), pkg)
            self.assertNotIn(pkg, profile.all_packages())

    def test_profiles_never_disable_cast_or_live_tv(self):
        for profile in P.load_all(PROFILE_DIR):
            for pkg in profile.all_packages():
                self.assertFalse(
                    safety.is_protected(pkg, profile.protected_extra),
                    f"{profile.name} lists protected {pkg}",
                )

    def test_json_round_trip(self):
        profile = P.load_file(PROFILE_DIR / "toshiba-hayward.json")
        again = P.from_dict(json.loads(json.dumps(profile.as_dict())))
        self.assertEqual(profile.tiers, again.tiers)
        self.assertEqual(profile.keep, again.keep)


if __name__ == "__main__":
    unittest.main()
