"""Plan / apply / rollback.

The applier is deliberately boring:

1. take a snapshot,
2. for every package in the plan, run ``pm disable-user`` and check the reply,
3. take a second snapshot and run the safety gates,
4. if any gate fails, re-enable everything this run disabled and report.

Each run writes a journal file so ``tvkit restore`` can undo it later even from
another machine (the journal is plain JSON — commit it, mail it, whatever).
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from . import __version__
from . import safety
from .profiles import Profile
from .snapshot import Snapshot

DISABLE_CMD = "pm disable-user --user 0 {pkg}"
ENABLE_CMD = "pm enable {pkg}"


def state_root() -> Path:
    """Where tvkit keeps journals/keys. Override with TVKIT_HOME."""
    import os

    override = os.environ.get("TVKIT_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.environ.get("APPDATA") or "~/.config"
    return Path(base).expanduser() / "tvkit"


@dataclass
class Step:
    package: str
    action: str  # "disable" | "enable"
    tier: str
    status: str = "pending"  # pending | ok | failed | skipped
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "package": self.package,
            "action": self.action,
            "tier": self.tier,
            "status": self.status,
            "note": self.note,
        }


@dataclass
class Plan:
    host: str
    profile: str
    tier: str
    steps: List[Step] = field(default_factory=list)
    skipped: List[Step] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)

    @property
    def actionable(self) -> List[Step]:
        return [s for s in self.steps if s.status == "pending"]

    def summary(self) -> str:
        return (
            f"{len(self.actionable)} to disable · {len(self.skipped)} skipped · "
            f"{len(self.warnings)} warning(s)"
        )


@dataclass
class Result:
    ok: bool
    plan: Plan
    applied: List[Step] = field(default_factory=list)
    rolled_back: List[Step] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    journal: Optional[Path] = None
    before: Optional[Snapshot] = None
    after: Optional[Snapshot] = None


def make_plan(
    profile: Profile,
    snapshot: Snapshot,
    tier: str = "safe",
    only: Optional[Iterable[str]] = None,
    include_uninstalled: bool = False,
) -> Plan:
    plan = Plan(host=snapshot.host, profile=profile.name, tier=tier, keep=list(profile.keep))
    wanted = set(only) if only else None
    enabled = set(snapshot.packages_enabled)
    disabled = set(snapshot.packages_disabled)

    for pkg in profile.packages_for(tier):
        if wanted is not None and pkg not in wanted:
            continue
        if safety.is_protected(pkg, profile.protected_extra):
            plan.skipped.append(
                Step(pkg, "disable", tier, "skipped", safety.protected_reason(pkg, profile.protected_extra))
            )
            continue
        if safety.is_launcher(pkg, snapshot.home):
            plan.skipped.append(
                Step(pkg, "disable", tier, "skipped", "is the launcher currently running Home")
            )
            continue
        if pkg in disabled:
            plan.skipped.append(Step(pkg, "disable", tier, "skipped", "already disabled"))
            continue
        if pkg not in enabled:
            if include_uninstalled:
                for warning in safety.warnings_for(pkg):
                    plan.warnings.append(f"{pkg}: {warning}")
                plan.steps.append(Step(pkg, "disable", tier, "pending", "not installed (will be skipped)"))
            else:
                plan.skipped.append(Step(pkg, "disable", tier, "skipped", "not installed on this device"))
            continue
        for warning in safety.warnings_for(pkg):
            plan.warnings.append(f"{pkg}: {warning}")
        note = profile.notes.get(pkg, "")
        plan.steps.append(Step(pkg, "disable", tier, "pending", note))
    return plan


def _disable(device, step: Step) -> None:
    out = device.shell(DISABLE_CMD.format(pkg=step.package), timeout=40)
    if "new state: disabled" in out or "disabled-user" in out:
        step.status = "ok"
        step.note = (step.note + " · " if step.note else "") + "disabled"
    elif "Unknown package" in out or "not installed" in out:
        step.status = "skipped"
        step.note = "unknown package"
    else:
        step.status = "failed"
        step.note = out.strip().splitlines()[-1][:160] if out.strip() else "unknown error"


def _enable(device, package: str, tier: str = "rollback") -> Step:
    step = Step(package, "enable", tier)
    out = device.shell(ENABLE_CMD.format(pkg=package), timeout=40)
    step.status = "ok" if ("new state: enabled" in out or "enabled" in out) else "failed"
    step.note = out.strip().splitlines()[-1][:160] if out.strip() else ""
    return step


def apply(
    device,
    profile: Profile,
    tier: str = "safe",
    only: Optional[Iterable[str]] = None,
    journal_dir: Optional[Path] = None,
    verify: bool = True,
) -> Result:
    """Apply a profile tier with verification and automatic rollback."""
    from .snapshot import take

    before = take(device)
    before.profile = profile.name
    plan = make_plan(profile, before, tier=tier, only=only)
    result = Result(ok=True, plan=plan, before=before)

    for step in plan.steps:
        _disable(device, step)
        if step.status == "ok":
            result.applied.append(step)
        elif step.status == "failed":
            result.failures.append(f"{step.package}: {step.note}")

    after = take(device)
    after.profile = profile.name
    result.after = after

    if verify:
        failures = safety.gate_failures(profile, after, [s.package for s in result.applied])
        # A crash in logcat that was not there before is also a red flag.
        new_crashes = [c for c in after.crashes if c not in before.crashes]
        if new_crashes:
            failures.append(f"new crash in logcat: {new_crashes[0][:120]}")
        if failures:
            result.failures.extend(failures)
            result.ok = False
            for pkg in [s.package for s in result.applied]:
                result.rolled_back.append(_enable(device, pkg))
            result.after = take(device)

    journal_root = Path(journal_dir) if journal_dir else state_root() / "journal"
    journal_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    journal_path = journal_root / f"{stamp}-{device.host.replace(':', '_')}.json"
    journal_path.write_text(
        json.dumps(
            {
                "tvkit": __version__,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "host": device.host,
                "profile": profile.name,
                "tier": tier,
                "ok": result.ok,
                "applied": [s.package for s in result.applied],
                "rolled_back": [s.package for s in result.rolled_back],
                "skipped": [s.as_dict() for s in plan.skipped],
                "failures": result.failures,
                "before_disabled": before.packages_disabled,
                "after_disabled": after.packages_disabled,
                "python": platform.python_version(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    result.journal = journal_path
    result.ok = result.ok and not any(s.status == "failed" for s in plan.steps)
    return result


def restore_journal(device, journal_path: Path) -> List[Step]:
    """Re-enable everything a journal says was disabled."""
    data = json.loads(Path(journal_path).read_text(encoding="utf-8"))
    steps: List[Step] = []
    for pkg in reversed(data.get("applied") or []):
        steps.append(_enable(device, pkg))
    return steps


def restore_packages(device, packages: Iterable[str]) -> List[Step]:
    return [_enable(device, pkg) for pkg in packages]


def latest_journal(host: Optional[str] = None) -> Optional[Path]:
    root = state_root() / "journal"
    if not root.exists():
        return None
    files = sorted(root.glob("*.json"))
    if host:
        files = [f for f in files if host in f.name]
    return files[-1] if files else None
