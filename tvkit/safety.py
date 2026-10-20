"""Safety rules — the single place that decides what may never be disabled.

Every profile is linted against these patterns at load time, and every package
is re-checked immediately before it is touched, so a bad profile cannot brick a
TV even if someone writes one by hand.

The lists below encode real breakage observed in the field:

* ``tungsten.setupwraith`` / vendor setup wizards — disabling them puts Home in
  a crash loop on some Hisense/CVTE builds.
* ``mediashell`` — kills Cast from phones.
* Live-TV / HDMI / tuner services — the panel loses its inputs.
* factory-menu packages — can drop a device into a vendor recovery screen.
* OTA/update services — leave them alone; users need security patches.
* The *current* launcher — never disable the Home app you are running before a
  replacement is verified. tvkit does this by checking the resolved Home at
  runtime rather than by package name.
"""

from __future__ import annotations

import fnmatch
from typing import Iterable, List

# Glob patterns. `fnmatch` semantics: * and ? only.
PROTECTED_PATTERNS: tuple = (
    # Cast / casting
    "com.google.android.apps.mediashell",
    "com.google.android.gms.cast*",
    # Setup, provisioning, accounts
    "com.google.android.tungsten.*",
    "com.google.android.setupwizard*",
    "com.android.provision*",
    "*setupwizard*",
    # Core Android / telephony-ish services that vendors wire into TV UI
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.tv.settings",
    "com.android.shell",
    "com.android.packageinstaller",
    "com.android.permissioncontroller",
    "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.webview*",
    "com.android.webview",
    "com.google.android.tts",
    # Live TV / tuner / HDMI / panel
    "com.mediatek.wwtv.*",
    "com.mediatek.tv*",
    "com.mstar.tv*",
    "com.hisense.tv.*input*",
    "com.realtek.tv*",
    "com.amlogic.tv*",
    # Factory menus / recovery hooks
    "com.cvte.tv.fac*",
    "com.at.factory*",
    "mediatek.factorymenu*",
    "*factorymenu*",
    "com.android.factory*",
    # OTA / firmware update
    "*ota*",
    "com.google.android.gms.*update*",
    "com.hisense.*update*",
    "com.tcl.*update*",
    # DRM / media framework — removing these silently breaks playback
    "com.google.android.drm*",
    "com.widevine*",
    "com.android.media*",
    # Bluetooth / remote services the remote itself depends on
    "com.android.bluetooth",
    "com.google.android.tv.remote*",
    "com.google.android.tvremoteservice*",
)

# Anything matching these must also stay enabled even if a profile lists it.
ESSENTIAL_HINTS = (
    "launcher",
    "tvlauncher",
    "mediashell",
    "playback",
)

# Packages that are *usually* safe but whose removal has visible side effects.
# tvkit prints these as warnings instead of blocking them.
WARN_LIST = {
    "com.google.android.katniss": "Google Assistant — the remote's mic / 'Ok Google' stops working",
    "com.android.vending": "Play Store — cannot install or update apps until re-enabled",
    "com.google.android.apps.youtube.tv": "YouTube TV app",
    "com.google.android.youtube.tv": "YouTube",
    "com.netflix.ninja": "Netflix",
    "com.google.android.backdrop": "Ambient screensaver (safe, but screen saver stops)",
    "com.google.android.tvlauncher": "Stock Google TV Home — only safe AFTER a replacement launcher is verified",
}


def is_protected(package: str, extra: Iterable[str] = ()) -> bool:
    """True when `package` must never be disabled."""
    for pattern in (*PROTECTED_PATTERNS, *extra):
        if fnmatch.fnmatch(package, pattern):
            return True
    return False


def protected_reason(package: str, extra: Iterable[str] = ()) -> str:
    for pattern in (*PROTECTED_PATTERNS, *extra):
        if fnmatch.fnmatch(package, pattern):
            return f"matches protected pattern `{pattern}`"
    return ""


def warnings_for(package: str) -> List[str]:
    note = WARN_LIST.get(package)
    return [note] if note else []


def is_launcher(package: str, home_activity: str) -> bool:
    """True if `package` is the currently resolved Home app."""
    if not home_activity or home_activity == "?":
        return False
    return home_activity.startswith(package + "/") or home_activity.startswith(package + ".")


def lint_profile(profile, packages_enabled: Iterable[str] = ()) -> List[str]:
    """Return a list of problems in a profile; empty list = clean."""
    problems: List[str] = []
    enabled = set(packages_enabled)

    seen = {}
    for tier, names in profile.tiers.items():
        for name in names:
            if name in seen:
                problems.append(f"{name}: listed in both `{seen[name]}` and `{tier}`")
            seen[name] = tier
            if is_protected(name, profile.protected_extra):
                problems.append(f"{name}: PROTECTED — {protected_reason(name, profile.protected_extra)}")
            if not name.count(".") >= 1:
                problems.append(f"{name}: does not look like a package name")

    keep = set(profile.keep)
    for name in profile.all_packages():
        if name in keep:
            problems.append(f"{name}: listed in `keep` and also in a disable tier")

    if enabled:
        missing = [p for p in profile.keep if p not in enabled]
        # informational only: a keep entry may simply not exist on this device
        for name in missing:
            problems.append(f"{name}: in `keep` but not installed on this device (info)")
    return problems


def gate_failures(
    profile,
    snapshot,
    expected_disabled: Iterable[str],
) -> List[str]:
    """Post-apply verification. Any entry here means 'roll back now'."""
    failures: List[str] = []
    home = snapshot.home or "?"

    if home == "?" or "No activity found" in home:
        failures.append("Home activity does not resolve — the device has no launcher")

    for pkg in profile.keep:
        installed = (
            pkg in snapshot.packages_enabled
            or pkg in snapshot.packages_disabled
            or pkg in snapshot.packages_third_party
        )
        if installed and pkg not in snapshot.packages_enabled:
            failures.append(f"keep-list package is not enabled: {pkg}")

    for pkg in expected_disabled:
        if pkg in snapshot.packages_enabled:
            failures.append(f"still enabled after apply: {pkg}")

    return failures
