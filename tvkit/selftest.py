"""Offline self-test used by `tvkit selftest` and CI.

Nothing here touches a real device: everything is validated against a simulated
Android TV defined below, so `python -m tvkit selftest` works on any machine.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from . import profiles as profiles_mod
from . import safety
from .apply import make_plan
from .discover import expand_targets
from .snapshot import Snapshot, _parse_df, _parse_meminfo, take

from .profiles import default_profile_dir

PROFILE_DIR = default_profile_dir()


class FakeDevice:
    """A tiny Android TV good enough to exercise every code path."""

    def __init__(self, props: Dict[str, str], enabled: List[str], disabled=None):
        self.host = "10.0.0.9"
        self.port = 5555
        self.props = dict(props)
        self.enabled = set(enabled)
        self.disabled = set(disabled or [])
        self.calls: List[str] = []

    def shell(self, command: str, timeout: float = 60) -> str:
        self.calls.append(command)
        if command.startswith("getprop"):
            return self._getprop(command)
        if command.startswith("cat /proc/meminfo"):
            return "MemTotal:        934540 kB\nMemFree:          21052 kB\nMemAvailable:    446668 kB\nSwapTotal:       524284 kB\nSwapFree:        217088 kB\n"
        if command.startswith("df -h"):
            return "Filesystem Size Used Avail Use% Mounted on\n/dev/block/dm-16 4.0G 2.7G 1.1G 72% /data\n"
        if command.startswith("cat /proc/loadavg"):
            return "54.77 55.10 56.00 3/1200 9999\n"
        if command.startswith("cat /proc/uptime"):
            return "6740000.00 12345.00\n"
        if command.startswith("cmd package resolve-activity"):
            return f"{self.home}\n"
        if command.startswith("wm size"):
            return "Physical size: 1920x1080\n"
        if command.startswith("pm list packages -e"):
            return "".join(f"package:{p}\n" for p in sorted(self.enabled))
        if command.startswith("pm list packages -d"):
            return "".join(f"package:{p}\n" for p in sorted(self.disabled))
        if command.startswith("pm list packages -3"):
            return "".join(f"package:{p}\n" for p in sorted(self.enabled)[:5])
        if command.startswith("logcat"):
            return ""
        if command.startswith("pm disable-user"):
            pkg = command.split()[-1]
            if pkg in self.enabled:
                self.enabled.discard(pkg)
                self.disabled.add(pkg)
                return f"Package {pkg} new state: disabled-user\n"
            return f"Package {pkg} new state: disabled-user\n"
        if command.startswith("pm enable"):
            pkg = command.split()[-1]
            if pkg in self.disabled:
                self.disabled.discard(pkg)
                self.enabled.add(pkg)
                return f"Package {pkg} new state: enabled\n"
            return f"Package {pkg} new state: enabled\n"
        return ""

    # -- helpers -----------------------------------------------------------
    def connect(self):
        return self

    def close(self) -> None:
        pass

    def getprop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    @property
    def home(self) -> str:
        for pkg in ("com.gathin.tvhome", "com.google.android.tvlauncher"):
            if pkg in self.enabled:
                return f"{pkg}/.MainActivity"
        return "No activity found"

    def _getprop(self, command: str) -> str:
        if "@@" in command:
            return "".join(f"@@{k}={v}\n" for k, v in self.props.items())
        parts = command.split()
        if len(parts) >= 2 and parts[1] in self.props:
            return self.props[parts[1]] + "\n"
        return "\n"


def _fake_android_tv() -> FakeDevice:
    packages = [
        "com.google.android.tvlauncher",
        "com.google.android.tvrecommendations",
        "com.google.android.videos",
        "com.google.android.play.games",
        "com.google.android.youtube.tvmusic",
        "com.android.vending",
        "com.google.android.katniss",
        "com.google.android.apps.mediashell",
        "com.google.android.tungsten.setupwraith",
        "com.google.android.gms",
        "com.mediatek.wwtv.tvcenter",
        "com.netflix.ninja",
        "com.ais.mimo.aisplay.tv",
        "com.tcl.browser",
        "com.tencent.qqlivei18n",
    ]
    props = {
        "ro.product.model": "TT_Fitness TV",
        "ro.product.manufacturer": "Toshiba",
        "ro.product.device": "hayward",
        "ro.product.name": "huashan_emT",
        "ro.board.platform": "mt5867",
        "ro.build.version.release": "11",
        "ro.build.version.sdk": "30",
        "ro.build.display.id": "RTMA.250416.097",
        "ro.build.fingerprint": "Toshiba/huashan_emT/hayward:11/RTMA/eng:user/release-keys",
    }
    return FakeDevice(props, packages)


CHECKS: List[str] = []


def _check(name: str, condition: bool, detail: str = "") -> bool:
    CHECKS.append(("PASS" if condition else "FAIL", name, detail))
    return condition


def run(verbose: bool = True) -> int:
    CHECKS.clear()

    # 1) discovery target parsing
    _check("expand_targets /24", len(expand_targets(["192.168.1"])) == 254)
    _check("expand_targets range", expand_targets(["10.0.0.5-7"]) == ["10.0.0.5", "10.0.0.6", "10.0.0.7"])
    _check("expand_targets cidr", len(expand_targets(["10.0.0.0/29"])) == 6)

    # 2) parsers
    mem = _parse_meminfo("MemTotal:  934540 kB\nMemFree: 21052 kB\nMemAvailable: 446668 kB\nSwapTotal: 524284 kB\nSwapFree: 217088 kB\n")
    _check("meminfo parse", mem.total_kb == 934540 and mem.used_swap_kb == 307196, f"{mem}")
    disk = _parse_df("/dev/block/dm-16 4.0G 2.7G 1.1G 72% /data\n")
    _check("df parse", disk.use_pct == 72 and disk.avail == "1.1G", f"{disk}")

    # 3) profiles load + lint
    loaded = profiles_mod.load_all(PROFILE_DIR)
    _check("profiles load", len(loaded) >= 3, f"{len(loaded)} profiles")
    lint_errors = []
    for profile in loaded:
        problems = [p for p in safety.lint_profile(profile) if "(info)" not in p]
        lint_errors.extend(problems)
    _check("all profiles lint clean", not lint_errors, "; ".join(lint_errors[:3]))

    # 4) protected patterns
    for pkg in (
        "com.google.android.tungsten.setupwraith",
        "com.google.android.apps.mediashell",
        "com.mediatek.wwtv.tvcenter",
        "com.cvte.tv.fac.menu",
        "android",
        "com.google.android.gms",
    ):
        _check(f"protected: {pkg}", safety.is_protected(pkg))
    for pkg in ("com.google.android.videos", "com.android.vending"):
        _check(f"not protected: {pkg}", not safety.is_protected(pkg))

    # 5) snapshot + selection + plan + apply on the simulated device
    fake = _fake_android_tv()
    snap = take(fake, include_packages=True)
    _check("snapshot props", snap.device_codename == "hayward" and snap.sdk == 30)
    _check("snapshot ram", snap.ram_mb == 913, f"{snap.ram_mb} MB")
    _check("snapshot android_tv", snap.android_tv)

    profile = profiles_mod.select(loaded, snap.props)
    _check("profile auto-match", profile.name == "toshiba-hayward", profile.name)

    plan = make_plan(profile, snap, tier="safe")
    _check("plan has steps", len(plan.steps) > 0, plan.summary())
    protected_in_plan = [s.package for s in plan.steps if safety.is_protected(s.package, profile.protected_extra)]
    _check("plan never contains protected packages", not protected_in_plan, ",".join(protected_in_plan))

    from .apply import apply as do_apply

    result = do_apply(fake, profile, tier="safe", journal_dir=Path(_tmpdir()))
    _check("apply ok", result.ok, ",".join(result.failures))
    _check("packages disabled", all(p in fake.disabled for p in [s.package for s in result.applied]))
    installed_keep = [p for p in profile.keep if p in fake.enabled or p in fake.disabled]
    _check(
        "keep list still enabled",
        all(p in fake.enabled for p in installed_keep),
        ", ".join(p for p in installed_keep if p not in fake.enabled),
    )

    # 6) rollback path: force a keep-list package off, gates must fire
    if profile.keep:
        victim = profile.keep[0]
        fake.enabled.discard(victim)
        fake.disabled.add(victim)
        bad = Snapshot(host=fake.host, packages_enabled=sorted(fake.enabled),
                       packages_disabled=sorted(fake.disabled), home=fake.home)
        failures = safety.gate_failures(profile, bad, [])
        _check("gate catches disabled keep package", any(victim in f for f in failures), "; ".join(failures))

    # 7) launcher protection
    launcher_snap = take(fake)
    launcher_plan = make_plan(
        profiles_mod.from_dict(
            {"name": "t", "tiers": {"safe": [launcher_snap.home.split("/")[0]]}, "keep": []}
        ),
        launcher_snap,
        tier="safe",
    )
    _check("never disables current Home", not launcher_plan.steps)

    # 8) cli wires up
    from .cli import build_parser

    parser = build_parser()
    ns = parser.parse_args(["apply", "--host", "1.2.3.4", "--tier", "balanced", "--yes"])
    _check("cli parses apply", ns.tier == "balanced" and ns.yes)

    failed = [c for c in CHECKS if c[0] == "FAIL"]
    if verbose:
        for status, name, detail in CHECKS:
            mark = "✅" if status == "PASS" else "❌"
            print(f"{mark} {name}" + (f"  ({detail})" if detail and status == "FAIL" else ""))
        print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 0 if not failed else 1


def _tmpdir() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="tvkit-selftest-")
