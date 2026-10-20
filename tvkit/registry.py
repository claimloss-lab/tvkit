"""Local device registry — remembers what each TV is, so nobody re-types IPs.

Stored as JSON under tvkit's state dir, **never** inside the repo:

    {
      "devices": {
        "aa:bb:cc:dd:ee:ff": {
          "label": "Toshiba TT_Fitness TV",
          "host": "192.168.1.146",
          "port": 5555,
          "profile": "toshiba-hayward",
          "sdk": 30,
          "last_seen": "2026-10-20T13:00:00"
        }
      }
    }

Keyed by MAC when available (stable across DHCP), otherwise by a slug of the
model name.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, Optional

from .apply import state_root


def registry_path() -> Path:
    return state_root() / "devices.json"


def load() -> Dict[str, dict]:
    path = registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("devices", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save(devices: Dict[str, dict]) -> Path:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"devices": devices}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_mac(device) -> Optional[str]:
    """Best-effort MAC address of the active network interface."""
    for iface in ("wlan0", "eth0", "wlan1"):
        try:
            raw = device.shell(f"cat /sys/class/net/{iface}/address 2>/dev/null").strip()
        except Exception:
            raw = ""
        if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", raw.lower()):
            return raw.lower()
    return None


def key_for(mac: Optional[str], label: str) -> str:
    if mac:
        return mac
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "unknown-device"


def remember(device, snapshot, profile_name: Optional[str] = None) -> str:
    devices = load()
    mac = read_mac(device)
    key = key_for(mac, snapshot.label)
    entry = devices.get(key, {})
    entry.update(
        {
            "label": snapshot.label,
            "host": device.host,
            "port": device.port,
            "sdk": snapshot.sdk,
            "device": snapshot.device_codename,
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    if profile_name:
        entry["profile"] = profile_name
    devices[key] = entry
    save(devices)
    return key


def find(key_or_label: str) -> Optional[dict]:
    devices = load()
    if key_or_label in devices:
        return devices[key_or_label]
    needle = key_or_label.lower()
    for key, entry in devices.items():
        haystack = f"{key} {entry.get('label','')} {entry.get('host','')}".lower()
        if needle in haystack:
            return entry
    return None
