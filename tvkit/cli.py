"""Command line interface.

    tvkit discover
    tvkit probe    --host 192.168.1.50
    tvkit audit    --host 192.168.1.50
    tvkit plan     --host 192.168.1.50 --tier safe
    tvkit apply    --host 192.168.1.50 --tier balanced --yes
    tvkit restore  --host 192.168.1.50 --last
    tvkit devices
    tvkit profiles
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __version__, discover as discovery, registry, report, safety
from .adb import AdbError, Device
from .apply import apply as apply_plan
from .apply import latest_journal, make_plan, restore_journal, restore_packages, state_root
from .profiles import ProfileError, default_profile_dir, describe, load_all, select
from .snapshot import take

DEFAULT_PROFILE_DIR = default_profile_dir()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _profiles(args):
    directory = Path(args.profile_dir).expanduser() if args.profile_dir else DEFAULT_PROFILE_DIR
    if not directory.exists():
        raise ProfileError(f"profile directory not found: {directory}")
    return load_all(directory)


def _resolve_host(args) -> str:
    if getattr(args, "host", None):
        return args.host
    if getattr(args, "device", None):
        entry = registry.find(args.device)
        if not entry:
            raise SystemExit(
                f"no known device matches `{args.device}` — run `tvkit devices` "
                "or pass --host"
            )
        return entry["host"]
    raise SystemExit("pass --host <ip> (or --device <name> from `tvkit devices`)")


def _connect(args) -> Device:
    dev = Device(_resolve_host(args), port=getattr(args, "port", 5555), timeout=args.timeout)
    try:
        dev.connect()
    except AdbError as exc:
        raise SystemExit(
            f"{exc}\n\nChecklist:\n"
            "  1. TV → Settings → About → tap Build 7× → Developer options\n"
            "  2. enable USB debugging / Network debugging (ADB over Wi-Fi)\n"
            "  3. accept the 'Allow USB debugging?' dialog on the TV\n"
            "  4. `tvkit discover` must list the device on port 5555"
        )
    return dev


def _emit(text: str, args, path: Optional[str] = None) -> None:
    print(text)
    if path:
        Path(path).expanduser().write_text(text, encoding="utf-8")
        print(f"\nwritten to {path}")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_discover(args) -> int:
    targets = args.target or None
    found = discovery.discover(targets, workers=args.workers, timeout=args.scan_timeout)
    if args.json:
        print(json.dumps([c.as_dict() for c in found], ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("No Android TV-ish hosts found.")
        print("Tips: same subnet? TV awake? Remote/Cast services enabled?")
        return 1
    print(f"{'HOST':<16}{'PORTS':<24}{'NAME':<30}{'CAST':<6}ETH")
    print("-" * 82)
    for cand in found:
        ports = ",".join(str(p) for p in cand.ports)
        print(f"{cand.host:<16}{ports:<24}{cand.label:<30}{cand.cast_version or '-':<6}{cand.ethernet}")
    adb_ready = [c.host for c in found if c.adb_ready]
    print()
    if adb_ready:
        print("ADB reachable: " + ", ".join(adb_ready))
    else:
        print("No host exposes 5555 yet — enable network debugging on the TV.")
    return 0


def cmd_probe(args) -> int:
    dev = _connect(args)
    try:
        snap = take(dev, include_packages=not args.fast)
        profiles = _profiles(args)
        try:
            profile = select(profiles, snap.props, args.profile)
            snap.profile = profile.name
        except ProfileError as exc:
            profile = None
            if not args.fast:
                print(f"! {exc}", file=sys.stderr)
        key = registry.remember(dev, snap, snap.profile)
    finally:
        dev.close()

    if args.json:
        print(report.as_json(snap))
        return 0
    print(report.snapshot_table(snap))
    print()
    if profile:
        print(f"Detected profile: {profile.name} — {profile.title}")
        print(f"Registered as  : {key}")
        problems = safety.lint_profile(profile, snap.packages_enabled)
        if problems:
            print("\nProfile lint:")
            for problem in problems:
                print(f"  - {problem}")
    else:
        print(f"Registered as: {key} (no profile matched)")
    print()
    for note in report.health_notes(snap):
        print(f"• {note}")
    return 0


def cmd_audit(args) -> int:
    dev = _connect(args)
    try:
        snap = take(dev)
        profiles = _profiles(args)
        try:
            profile = select(profiles, snap.props, args.profile)
        except ProfileError as exc:
            profile = None
            print(f"! {exc}", file=sys.stderr)
        key = registry.remember(dev, snap, profile.name if profile else None)
    finally:
        dev.close()

    parts = [f"# tvkit audit — {snap.label}", "", report.snapshot_table(snap), "", "### Health"]
    parts += [f"- {note}" for note in report.health_notes(snap)]
    if profile:
        problems = safety.lint_profile(profile, snap.packages_enabled)
        parts += ["", report.profile_report(snap, profile, problems)]
        plan = make_plan(profile, snap, tier=args.tier)
        parts += ["", report.plan_report(plan)]
    parts += ["", f"_tvkit {__version__} · registry key `{key}`_"]
    _emit("\n".join(parts), args, args.out)
    return 0


def cmd_plan(args) -> int:
    dev = _connect(args)
    try:
        snap = take(dev)
        profile = select(_profiles(args), snap.props, args.profile)
    finally:
        dev.close()
    plan = make_plan(profile, snap, tier=args.tier, include_uninstalled=args.all)
    print(report.as_json(plan) if args.json else report.plan_report(plan))
    return 0


def cmd_apply(args) -> int:
    dev = _connect(args)
    try:
        snap = take(dev)
        profile = select(_profiles(args), snap.props, args.profile)
        plan = make_plan(profile, snap, tier=args.tier)
        if args.dry_run:
            print(report.plan_report(plan))
            print("\n(dry run — nothing changed)")
            return 0
        if not plan.steps:
            print(report.plan_report(plan))
            print("\nNothing to disable.")
            return 0
        if not args.yes:
            print(report.plan_report(plan))
            if not sys.stdin.isatty():
                print("\nRefusing to change the device without --yes.")
                return 2
            answer = input(f"\nDisable {len(plan.steps)} package(s) on {snap.label}? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print("cancelled")
                return 1
        result = apply_plan(dev, profile, tier=args.tier, only=args.only)
        registry.remember(dev, snap, profile.name)
    finally:
        dev.close()
    print(report.as_json(result) if args.json else report.result_report(result))
    return 0 if result.ok else 3


def cmd_restore(args) -> int:
    packages = list(args.package or [])
    journal = None
    if args.last or args.journal:
        journal = Path(args.journal).expanduser() if args.journal else latest_journal(args.host)
        if not journal or not Path(journal).exists():
            raise SystemExit("no journal found — pass --journal or use --package")

    dev = _connect(args)
    steps = []
    try:
        if journal:
            steps += restore_journal(dev, Path(journal))
            print(f"journal: {journal}")
        if packages:
            steps += restore_packages(dev, packages)
        if args.stock_home:
            steps.append(restore_packages(dev, ["com.google.android.tvlauncher"])[0])
            out = dev.shell(
                "cmd package set-home-activity --user 0 "
                "com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity"
            )
            print(f"stock home: {out.strip() or 'ok'}")
        if args.animations:
            for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
                dev.shell(f"settings put global {key} 1.0")
            print("animations reset to 1.0")
        if args.bluetooth:
            print(dev.shell("svc bluetooth enable").strip() or "bluetooth on")
    finally:
        dev.close()

    ok = sum(1 for s in steps if s.status == "ok")
    print(f"\nre-enabled {ok}/{len(steps)} package(s)")
    for step in steps:
        if step.status != "ok":
            print(f"  ! {step.package}: {step.note}")
    return 0 if ok == len(steps) else 3


def cmd_screenshot(args) -> int:
    """Capture the screen (before/after evidence, great for issue reports)."""
    import re
    import time

    dev = _connect(args)
    try:
        snap = take(dev, include_packages=False)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", snap.label.lower()).strip("-") or "tv"
        out_dir = Path(args.out or ".").expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        local = out_dir / f"{slug}-{stamp}.png"
        remote = f"/sdcard/tvkit-{stamp}.png"
        res = dev.shell(f"screencap -p {remote}").strip()
        if "error" in res.lower() or "failed" in res.lower():
            print(f"capture failed: {res}", file=sys.stderr)
            return 3
        dev.pull(remote, str(local))
        dev.shell(f"rm -f {remote}")
    finally:
        dev.close()
    print(f"{local}  ({snap.label} · {snap.resolution})")
    return 0


def cmd_devices(args) -> int:
    devices = registry.load()
    if args.json:
        print(json.dumps(devices, ensure_ascii=False, indent=2))
        return 0
    if not devices:
        print("No devices recorded yet — run `tvkit probe --host <ip>` once.")
        return 0
    print(f"{'KEY':<20}{'LABEL':<32}{'HOST':<16}{'PROFILE':<24}LAST SEEN")
    print("-" * 110)
    for key, entry in sorted(devices.items()):
        print(
            f"{key:<20}{entry.get('label','?')[:31]:<32}{entry.get('host','?'):<16}"
            f"{entry.get('profile','-')[:23]:<24}{entry.get('last_seen','-')}"
        )
    print(f"\nregistry: {registry.registry_path()}")
    return 0


def cmd_profiles(args) -> int:
    profiles = _profiles(args)
    if args.json:
        print(json.dumps([p.as_dict() for p in profiles], ensure_ascii=False, indent=2))
        return 0
    bad = 0
    for profile in profiles:
        print(describe(profile))
        problems = [p for p in safety.lint_profile(profile) if "(info)" not in p]
        for problem in problems:
            bad += 1
            print(f"  ❌ {problem}")
        print()
    print(f"{len(profiles)} profile(s) loaded from {DEFAULT_PROFILE_DIR}{' — LINT ERRORS' if bad else ' — lint clean'}")
    return 1 if bad else 0


def cmd_selftest(args) -> int:
    """Offline checks — no device needed. Used by CI."""
    from . import selftest

    return selftest.run(verbose=True)


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tvkit",
        description="Debloat, inspect and speed up Android TV / Google TV over ADB — reversibly.",
    )
    parser.add_argument("--version", action="version", version=f"tvkit {__version__}")
    parser.add_argument("--profile-dir", help="directory of profile JSON files")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_host(p, required_host=True):
        p.add_argument("--host", help="device IP (e.g. 192.168.1.50)")
        p.add_argument("--device", help="device name/MAC/key from `tvkit devices`")
        p.add_argument("--port", type=int, default=5555)
        p.add_argument("--timeout", type=float, default=12.0)
        p.add_argument("--json", action="store_true", help="machine-readable output")

    p_disc = sub.add_parser("discover", help="scan the LAN for TVs")
    p_disc.add_argument("--target", action="append", help="subnet / range / host (repeatable)")
    p_disc.add_argument("--workers", type=int, default=200)
    p_disc.add_argument("--scan-timeout", type=float, default=0.5, dest="scan_timeout")
    p_disc.add_argument("--json", action="store_true")
    p_disc.set_defaults(func=cmd_discover)

    p_probe = sub.add_parser("probe", help="identity + health of one device")
    add_host(p_probe)
    p_probe.add_argument("--profile", help="force a profile by name")
    p_probe.add_argument("--fast", action="store_true", help="skip package lists")
    p_probe.set_defaults(func=cmd_probe)

    p_audit = sub.add_parser("audit", help="full markdown report (before snapshot)")
    add_host(p_audit)
    p_audit.add_argument("--profile")
    p_audit.add_argument("--tier", default="safe", choices=("safe", "balanced", "aggressive"))
    p_audit.add_argument("--out", help="write the report to this file")
    p_audit.set_defaults(func=cmd_audit)

    p_plan = sub.add_parser("plan", help="show what would change (no writes)")
    add_host(p_plan)
    p_plan.add_argument("--profile")
    p_plan.add_argument("--tier", default="safe", choices=("safe", "balanced", "aggressive"))
    p_plan.add_argument("--all", action="store_true", help="also list packages not installed")
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="disable packages (verified, auto-rollback)")
    add_host(p_apply)
    p_apply.add_argument("--profile")
    p_apply.add_argument("--tier", default="safe", choices=("safe", "balanced", "aggressive"))
    p_apply.add_argument("--only", action="append", help="limit to specific package(s)")
    p_apply.add_argument("--yes", action="store_true", help="no confirmation prompt")
    p_apply.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_apply.set_defaults(func=cmd_apply)

    p_restore = sub.add_parser("restore", help="undo (journal, package list, stock Home)")
    add_host(p_restore)
    p_restore.add_argument("--last", action="store_true", help="replay the newest journal for this host")
    p_restore.add_argument("--journal", help="path to a specific journal json")
    p_restore.add_argument("--package", action="append", help="re-enable one package (repeatable)")
    p_restore.add_argument("--stock-home", action="store_true", dest="stock_home",
                           help="re-enable and switch back to the stock Google TV Home")
    p_restore.add_argument("--animations", action="store_true", help="reset animation scales to 1.0")
    p_restore.add_argument("--bluetooth", action="store_true", help="turn Bluetooth back on")
    p_restore.set_defaults(func=cmd_restore)

    p_shot = sub.add_parser("screenshot", help="save a PNG of the current screen (evidence)")
    add_host(p_shot)
    p_shot.add_argument("--out", help="directory to save into (default: current dir)")
    p_shot.set_defaults(func=cmd_screenshot)

    p_devices = sub.add_parser("devices", help="list the local device registry")
    p_devices.add_argument("--json", action="store_true")
    p_devices.set_defaults(func=cmd_devices)

    p_profiles = sub.add_parser("profiles", help="list and lint the shipped profiles")
    p_profiles.add_argument("--json", action="store_true")
    p_profiles.set_defaults(func=cmd_profiles)

    p_selftest = sub.add_parser("selftest", help="offline checks (CI friendly)")
    p_selftest.set_defaults(func=cmd_selftest)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "profile_dir", None):
        args.profile_dir = None
    try:
        return args.func(args)
    except ProfileError as exc:
        print(f"profile error: {exc}", file=sys.stderr)
        return 2
    except AdbError as exc:
        print(f"adb error: {exc}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
