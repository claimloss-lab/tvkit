"""Profiles: declarative, shareable descriptions of what to disable on a device.

A profile is a plain JSON file so that (a) it needs no extra dependency and
(b) it can be reviewed in a pull request without a YAML parser in your head.

Schema
------
```json
{
  "name": "toshiba-hayward",
  "title": "Toshiba / Hisense CVTE (Android TV 11, MT5867)",
  "match": {
    "ro.product.device": "hayward",
    "ro.board.platform": "huashan.*"
  },
  "tiers": {
    "safe":       ["com.google.android.videos"],
    "balanced":   ["com.android.vending"],
    "aggressive": ["com.google.android.katniss"]
  },
  "keep": ["com.ais.mimo.aisplay.tv"],
  "protected_extra": [],
  "notes": {"com.android.vending": "frees ~250 MB on 1 GB devices"},
  "min_ram_mb": 512,
  "verified_on": ["Toshiba TT_Fitness TV / hayward / SDK 30"]
}
```

* `match` values are regular expressions tested against build properties.
  A profile with an empty `match` is a generic fallback and must have the lowest
  priority (see `priority`, higher wins).
* `tiers` are cumulative: `safe` applies first, then `balanced`, then
  `aggressive`. Each tier is verified separately and rolled back on its own.
* `keep` packages are asserted *enabled* after every apply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

TIER_ORDER = ("safe", "balanced", "aggressive")


def default_profile_dir() -> Path:
    """Locate the shipped profiles.

    Search order so that plain checkouts, editable installs and a copy of the
    package all work:

    1. ``$TVKIT_PROFILE_DIR``
    2. ``<repo>/profiles``   (running from a clone, or `pip install -e .`)
    3. ``<site-packages>/tvkit/profiles`` (packaged copy)
    4. ``./profiles`` in the current directory
    """
    import os

    env = os.environ.get("TVKIT_PROFILE_DIR")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "profiles", here / "profiles", Path.cwd() / "profiles"):
        if candidate.exists():
            return candidate
    return here.parent / "profiles"


class ProfileError(ValueError):
    pass


@dataclass
class Profile:
    name: str
    title: str = ""
    match: Dict[str, str] = field(default_factory=dict)
    tiers: Dict[str, List[str]] = field(default_factory=dict)
    keep: List[str] = field(default_factory=list)
    protected_extra: List[str] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)
    min_ram_mb: int = 0
    priority: int = 0
    verified_on: List[str] = field(default_factory=list)
    source: Optional[Path] = None

    # -- accessors ---------------------------------------------------------
    def all_packages(self) -> List[str]:
        out: List[str] = []
        for tier in TIER_ORDER:
            out.extend(self.tiers.get(tier, []))
        return out

    def packages_for(self, tier: str) -> List[str]:
        """Cumulative package list for a tier: safe + balanced + ... + tier."""
        if tier not in TIER_ORDER:
            raise ProfileError(f"unknown tier `{tier}` (choose from {', '.join(TIER_ORDER)})")
        out: List[str] = []
        for name in TIER_ORDER:
            out.extend(self.tiers.get(name, []))
            if name == tier:
                break
        return out

    def matches(self, props: Dict[str, str]) -> bool:
        for key, pattern in self.match.items():
            value = props.get(key, "")
            if not re.search(pattern, value or "", re.I):
                return False
        return True

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "match": self.match,
            "tiers": self.tiers,
            "keep": self.keep,
            "protected_extra": self.protected_extra,
            "notes": self.notes,
            "min_ram_mb": self.min_ram_mb,
            "priority": self.priority,
            "verified_on": self.verified_on,
        }


def from_dict(data: dict, source: Optional[Path] = None) -> Profile:
    if not isinstance(data, dict):
        raise ProfileError("profile must be a JSON object")
    name = data.get("name")
    if not name:
        raise ProfileError("profile is missing `name`")
    tiers_raw = data.get("tiers") or {}
    unknown = set(tiers_raw) - set(TIER_ORDER)
    if unknown:
        raise ProfileError(f"{name}: unknown tier(s) {sorted(unknown)}")
    tiers = {tier: list(tiers_raw.get(tier, [])) for tier in TIER_ORDER}
    return Profile(
        name=name,
        title=data.get("title", ""),
        match=dict(data.get("match") or {}),
        tiers=tiers,
        keep=list(data.get("keep") or []),
        protected_extra=list(data.get("protected_extra") or []),
        notes=dict(data.get("notes") or {}),
        min_ram_mb=int(data.get("min_ram_mb") or 0),
        priority=int(data.get("priority") or 0),
        verified_on=list(data.get("verified_on") or []),
        source=source,
    )


def load_file(path: Path) -> Profile:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{path}: invalid JSON — {exc}") from exc
    return from_dict(data, source=Path(path))


def load_all(directory: Path) -> List[Profile]:
    profiles = [load_file(p) for p in sorted(Path(directory).glob("*.json"))]
    if not profiles:
        raise ProfileError(f"no profiles found in {directory}")
    return sorted(profiles, key=lambda p: (-p.priority, p.name))


def select(profiles: List[Profile], props: Dict[str, str], name: Optional[str] = None) -> Profile:
    """Pick a profile: explicit name wins, otherwise best match by priority."""
    if name:
        for profile in profiles:
            if profile.name == name:
                return profile
        raise ProfileError(f"unknown profile `{name}` — available: {', '.join(p.name for p in profiles)}")

    matches = [p for p in profiles if p.matches(props)]
    if not matches:
        generic = [p for p in profiles if not p.match]
        if generic:
            return generic[0]
        raise ProfileError(
            "no profile matches this device. Run `tvkit probe` and open an issue with the "
            "build properties, or copy profiles/generic-androidtv.json and add a match block."
        )
    return matches[0]


def describe(profile: Profile) -> str:
    lines = [f"{profile.name} — {profile.title}"]
    if profile.match:
        for key, pattern in profile.match.items():
            lines.append(f"  match  {key} =~ /{pattern}/")
    else:
        lines.append("  match  (generic fallback)")
    for tier in TIER_ORDER:
        pkgs = profile.tiers.get(tier, [])
        lines.append(f"  {tier:<11}{len(pkgs):>3} package(s)")
    if profile.keep:
        lines.append(f"  keep        {', '.join(profile.keep)}")
    return "\n".join(lines)
