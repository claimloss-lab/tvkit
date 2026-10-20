"""Device snapshot: everything tvkit reads (never writes) from a TV.

The snapshot is the input for profile matching, the audit report and the
before/after comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

PROPS = (
    "ro.product.model",
    "ro.product.manufacturer",
    "ro.product.brand",
    "ro.product.device",
    "ro.product.board",
    "ro.product.name",
    "ro.build.version.release",
    "ro.build.version.sdk",
    "ro.build.display.id",
    "ro.build.date",
    "ro.build.fingerprint",
    "ro.hardware",
    "ro.board.platform",
    "ro.config.low_ram",
    "ro.sf.lcd_density",
    "net.hostname",
)

HOME_QUERY = (
    "cmd package resolve-activity --brief -a android.intent.action.MAIN "
    "-c android.intent.category.HOME"
)


@dataclass
class Memory:
    total_kb: int = 0
    free_kb: int = 0
    available_kb: int = 0
    swap_total_kb: int = 0
    swap_free_kb: int = 0

    @property
    def used_swap_kb(self) -> int:
        return max(0, self.swap_total_kb - self.swap_free_kb)


@dataclass
class Storage:
    size: str = "?"
    used: str = "?"
    avail: str = "?"
    use_pct: int = 0


@dataclass
class Snapshot:
    host: str
    props: Dict[str, str] = field(default_factory=dict)
    memory: Memory = field(default_factory=Memory)
    storage: Storage = field(default_factory=Storage)
    load_avg: str = "?"
    uptime_s: float = 0.0
    home: str = "?"
    packages_enabled: List[str] = field(default_factory=list)
    packages_disabled: List[str] = field(default_factory=list)
    packages_third_party: List[str] = field(default_factory=list)
    crashes: List[str] = field(default_factory=list)
    resolution: str = "?"
    android_tv: bool = False
    profile: Optional[str] = None

    # -- identity helpers --------------------------------------------------
    @property
    def model(self) -> str:
        return self.props.get("ro.product.model", "?")

    @property
    def manufacturer(self) -> str:
        return self.props.get("ro.product.manufacturer", "?")

    @property
    def device_codename(self) -> str:
        return self.props.get("ro.product.device", "?")

    @property
    def sdk(self) -> int:
        try:
            return int(self.props.get("ro.build.version.sdk", "0"))
        except ValueError:
            return 0

    @property
    def ram_mb(self) -> int:
        return round(self.memory.total_kb / 1024)

    @property
    def label(self) -> str:
        return f"{self.manufacturer} {self.model}".strip()

    def as_dict(self) -> dict:
        data = asdict(self)
        data["label"] = self.label
        data["ram_mb"] = self.ram_mb
        return data


def _parse_packages(text: str) -> List[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            out.append(line.split(":", 1)[1].strip())
    return sorted(set(out))


def _parse_meminfo(text: str) -> Memory:
    def grab(key: str) -> int:
        match = re.search(rf"^{key}:\s+(\d+)", text, re.M)
        return int(match.group(1)) if match else 0

    return Memory(
        total_kb=grab("MemTotal"),
        free_kb=grab("MemFree"),
        available_kb=grab("MemAvailable"),
        swap_total_kb=grab("SwapTotal"),
        swap_free_kb=grab("SwapFree"),
    )


def _parse_df(text: str) -> Storage:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[-1].endswith("/data"):
            size, used, avail, pct = parts[-5], parts[-4], parts[-3], parts[-2]
            try:
                pct_i = int(pct.rstrip("%"))
            except ValueError:
                pct_i = 0
            return Storage(size=size, used=used, avail=avail, use_pct=pct_i)
    return Storage()


def _parse_size(text: str) -> Optional[str]:
    match = re.search(r"(\d+x\d+)", text)
    return match.group(1) if match else None


def take(device, include_packages: bool = True) -> Snapshot:
    """Read a full snapshot from a connected :class:`tvkit.adb.Device`."""
    snap = Snapshot(host=device.host)

    raw = device.shell(
        "getprop " + " ".join(PROPS) + " 2>/dev/null; "
        + " ; ".join(f'echo "@@{p}=$(getprop {p})"' for p in PROPS)
    )
    for line in raw.splitlines():
        if line.startswith("@@") and "=" in line:
            key, value = line[2:].split("=", 1)
            snap.props[key] = value.strip()

    snap.memory = _parse_meminfo(device.shell("cat /proc/meminfo"))
    snap.storage = _parse_df(device.shell("df -h /data 2>/dev/null || df -h /data/user/0"))
    snap.load_avg = device.shell("cat /proc/loadavg").strip().split(" ")[0] or "?"
    try:
        snap.uptime_s = float(device.shell("cat /proc/uptime").split()[0])
    except (ValueError, IndexError):
        snap.uptime_s = 0.0
    snap.home = next(
        (ln.strip() for ln in device.shell(HOME_QUERY).splitlines() if ln.strip()),
        "?",
    )
    snap.resolution = _parse_size(device.shell("wm size")) or "?"

    if include_packages:
        snap.packages_enabled = _parse_packages(device.shell("pm list packages -e"))
        snap.packages_disabled = _parse_packages(device.shell("pm list packages -d"))
        snap.packages_third_party = _parse_packages(device.shell("pm list packages -3"))

    crash_log = device.shell("logcat -d -b crash -t 60 2>/dev/null")
    snap.crashes = [
        ln.strip()
        for ln in crash_log.splitlines()
        if "FATAL EXCEPTION" in ln or "beginning of crash" in ln
    ][:10]

    snap.android_tv = (
        "television" in snap.props.get("ro.build.fingerprint", "").lower()
        or "tv" in snap.props.get("ro.product.name", "").lower()
        or "leanback" in snap.home.lower()
        or any(p.endswith(".tvlauncher") or "tvlauncher" in p for p in snap.packages_enabled)
        or "atv" in snap.props.get("ro.product.brand", "").lower()
    )
    return snap


def compare(before: Snapshot, after: Snapshot) -> List[tuple]:
    """Rows of (metric, before, after, delta) for the before/after table."""
    rows = []
    rows.append(
        (
            "RAM available",
            f"{before.memory.available_kb // 1024} MB",
            f"{after.memory.available_kb // 1024} MB",
            f"{(after.memory.available_kb - before.memory.available_kb) // 1024:+d} MB",
        )
    )
    rows.append(
        (
            "RAM free",
            f"{before.memory.free_kb // 1024} MB",
            f"{after.memory.free_kb // 1024} MB",
            f"{(after.memory.free_kb - before.memory.free_kb) // 1024:+d} MB",
        )
    )
    rows.append(
        (
            "Swap used",
            f"{before.memory.used_swap_kb // 1024} MB",
            f"{after.memory.used_swap_kb // 1024} MB",
            f"{(after.memory.used_swap_kb - before.memory.used_swap_kb) // 1024:+d} MB",
        )
    )
    rows.append(
        (
            "Storage use",
            f"{before.storage.use_pct}% ({before.storage.avail} free)",
            f"{after.storage.use_pct}% ({after.storage.avail} free)",
            f"{after.storage.use_pct - before.storage.use_pct:+d} pt",
        )
    )
    rows.append(("Load avg", before.load_avg, after.load_avg, "-"))
    rows.append(
        (
            "Disabled packages",
            str(len(before.packages_disabled)),
            str(len(after.packages_disabled)),
            f"{len(after.packages_disabled) - len(before.packages_disabled):+d}",
        )
    )
    return rows
