"""Markdown / JSON reporting.

Everything tvkit prints is also available as a file so it can be pasted into a
GitHub issue or a Discord message.
"""

from __future__ import annotations

import json
from typing import List

from .apply import Plan, Result
from .snapshot import Snapshot, compare


def snapshot_table(snap: Snapshot) -> str:
    rows = [
        ("Model", snap.label),
        ("Device / codename", snap.device_codename),
        ("Android", f"{snap.props.get('ro.build.version.release', '?')} (SDK {snap.sdk})"),
        ("Build", snap.props.get("ro.build.display.id", "?")),
        ("Platform", snap.props.get("ro.board.platform", snap.props.get("ro.hardware", "?"))),
        ("Android TV", "yes" if snap.android_tv else "no/unclear"),
        ("RAM", f"{snap.ram_mb} MB"),
        ("RAM available", f"{snap.memory.available_kb // 1024} MB"),
        ("Swap used", f"{snap.memory.used_swap_kb // 1024} MB"),
        ("Storage /data", f"{snap.storage.use_pct}% used · {snap.storage.avail} free"),
        ("Load average", snap.load_avg),
        ("Uptime", f"{snap.uptime_s / 3600:.1f} h"),
        ("Home", snap.home),
        ("Packages enabled", str(len(snap.packages_enabled))),
        ("Packages disabled", str(len(snap.packages_disabled))),
        ("Third-party", str(len(snap.packages_third_party))),
        ("Resolution", snap.resolution),
    ]
    out = ["| Item | Value |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(out)


def health_notes(snap: Snapshot) -> List[str]:
    notes: List[str] = []
    if snap.ram_mb and snap.ram_mb <= 1024:
        notes.append(
            f"RAM is only {snap.ram_mb} MB — below the ~1.5 GB Android TV really needs. "
            "Software tuning helps, but this is the hardware ceiling."
        )
    if snap.memory.swap_total_kb and snap.memory.used_swap_kb > snap.memory.swap_total_kb * 0.4:
        notes.append(f"Swap is {snap.memory.used_swap_kb // 1024} MB used — the system is paging to flash, which is why taps feel laggy.")
    if snap.storage.use_pct >= 80:
        notes.append(f"Storage is {snap.storage.use_pct}% full — Android needs headroom for cache and swap.")
    if snap.uptime_s > 7 * 86400:
        notes.append(f"No reboot for {snap.uptime_s / 86400:.0f} days — a reboot clears leaked swap and stale processes.")
    try:
        if float(snap.load_avg) > 8 and snap.memory.available_kb > 200 * 1024:
            notes.append("Load average is high while RAM looks okay — that is usually kswapd/I-O wait, not CPU.")
    except (TypeError, ValueError):
        pass
    if not notes:
        notes.append("No red flags found in this snapshot.")
    return notes


def profile_report(snap: Snapshot, profile, problems: List[str]) -> str:
    out = [f"### Profile match: `{profile.name}`", "", f"_{profile.title}_", ""]
    for tier, packages in profile.tiers.items():
        if not packages:
            continue
        out.append(f"**{tier}** ({len(packages)})")
        for pkg in packages:
            mark = "enabled" if pkg in snap.packages_enabled else ("already off" if pkg in snap.packages_disabled else "not installed")
            out.append(f"- `{pkg}` {mark}")
        out.append("")
    if problems:
        out.append("**Lint problems**")
        out += [f"- {p}" for p in problems]
    return "\n".join(out)


def plan_report(plan: Plan) -> str:
    out = [f"### Plan — {plan.summary()}", ""]
    if plan.steps:
        out.append("| # | package | tier | note |")
        out.append("|---|---|---|---|")
        for i, step in enumerate(plan.steps, 1):
            out.append(f"| {i} | `{step.package}` | {step.tier} | {step.note} |")
    else:
        out.append("_Nothing to do for this tier._")
    if plan.warnings:
        out += ["", "**Side effects**"] + [f"- {w}" for w in plan.warnings]
    if plan.skipped:
        out += ["", "**Skipped**"] + [f"- `{s.package}` — {s.note}" for s in plan.skipped[:25]]
        if len(plan.skipped) > 25:
            out.append(f"- … and {len(plan.skipped) - 25} more")
    return "\n".join(out)


def result_report(result: Result) -> str:
    out = [f"### Result - {'OK' if result.ok else 'ROLLED BACK'}", ""]
    out.append(f"Disabled: {len(result.applied)} · rolled back: {len(result.rolled_back)}")
    if result.before and result.after:
        out += ["", "| Metric | Before | After | Change |", "|---|---|---|---|"]
        for metric, before, after, delta in compare(result.before, result.after):
            out.append(f"| {metric} | {before} | {after} | {delta} |")
    if result.failures:
        out += ["", "**Verification failures**"] + [f"- {f}" for f in result.failures]
    if result.journal:
        out += ["", f"Journal: `{result.journal}`"]
    return "\n".join(out)


def as_json(obj) -> str:
    if isinstance(obj, Snapshot):
        return json.dumps(obj.as_dict(), ensure_ascii=False, indent=2)
    if isinstance(obj, Plan):
        return json.dumps(
            {
                "host": obj.host,
                "profile": obj.profile,
                "tier": obj.tier,
                "steps": [s.as_dict() for s in obj.steps],
                "skipped": [s.as_dict() for s in obj.skipped],
                "warnings": obj.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    if isinstance(obj, Result):
        return json.dumps(
            {
                "ok": obj.ok,
                "applied": [s.package for s in obj.applied],
                "rolled_back": [s.package for s in obj.rolled_back],
                "failures": obj.failures,
                "journal": str(obj.journal) if obj.journal else None,
                "before": obj.before.as_dict() if obj.before else None,
                "after": obj.after.as_dict() if obj.after else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
