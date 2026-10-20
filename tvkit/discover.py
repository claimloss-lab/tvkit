"""LAN discovery for Android TV devices.

Two independent signals are combined:

* **Port scan** — 5555 (ADB), 6466 (Android TV Remote), 8008 (Cast / DIAL),
  9000 (TLS). Any TV on the network answers at least remote/cast.
* **Cast handshake** — ``GET http://<ip>:8008/setup/eureka_info?options=detail``
  returns the user-visible device name, Cast build and whether it is on Ethernet.
  This works without any credentials and is how a device gets a friendly label
  before ADB is even enabled.

The result is metadata only; no device is modified here.
"""

from __future__ import annotations

import concurrent.futures as futures
import ipaddress
import json
import socket
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

ADB_PORT = 5555
REMOTE_PORT = 6466
CAST_PORT = 8008
TLS_PORT = 9000

TV_PORTS = (ADB_PORT, REMOTE_PORT, CAST_PORT, TLS_PORT)


@dataclass
class Candidate:
    host: str
    ports: List[int] = field(default_factory=list)
    name: Optional[str] = None
    cast_version: Optional[str] = None
    ethernet: Optional[bool] = None

    @property
    def adb_ready(self) -> bool:
        return ADB_PORT in self.ports

    @property
    def label(self) -> str:
        return self.name or "(unnamed TV)"

    def as_dict(self) -> dict:
        return {
            "host": self.host,
            "ports": self.ports,
            "name": self.name,
            "cast_version": self.cast_version,
            "ethernet": self.ethernet,
            "adb_ready": self.adb_ready,
        }


def default_subnet() -> str:
    """Best-effort /24 for the primary interface, without extra dependencies."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))  # no packet is sent
            local_ip = sock.getsockname()[0]
        return ".".join(local_ip.split(".")[:3])
    except OSError:
        return "192.168.1"


def expand_targets(spec: Sequence[str]) -> List[str]:
    """Turn user input into a list of hosts.

    Accepts ``192.168.1``, ``192.168.1.0/24``, ``192.168.1.10-40`` or explicit
    host/IP strings.
    """
    hosts: List[str] = []
    for item in spec:
        item = item.strip()
        if not item:
            continue
        if "/" in item:
            net = ipaddress.ip_network(item, strict=False)
            hosts.extend(str(ip) for ip in net.hosts())
        elif "-" in item and item.rsplit(".", 1)[-1].count("-") == 1:
            base, rng = item.rsplit(".", 1)
            first, last = rng.split("-")
            hosts.extend(f"{base}.{i}" for i in range(int(first), int(last) + 1))
        elif item.count(".") == 2 and all(p.isdigit() for p in item.split(".")):
            hosts.extend(f"{item}.{i}" for i in range(1, 255))
        else:
            hosts.append(item)
    # de-duplicate, keep order
    return list(dict.fromkeys(hosts))


def _scan_port(host: str, port: int, timeout: float) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def _cast_info(host: str, timeout: float = 4.0) -> dict:
    url = f"http://{host}:{CAST_PORT}/setup/eureka_info?options=detail"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tvkit"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return {}


def probe_host(host: str, timeout: float = 0.5) -> Optional[Candidate]:
    open_ports = [p for p in TV_PORTS if _scan_port(host, p, timeout)]
    if not open_ports:
        return None
    cand = Candidate(host=host, ports=open_ports)
    if CAST_PORT in open_ports:
        info = _cast_info(host)
        if info:
            cand.name = info.get("name")
            cand.cast_version = str(info.get("version") or "") or None
            eth = info.get("ethernet_connected")
            cand.ethernet = bool(eth) if eth is not None else None
    return cand


def discover(
    targets: Optional[Iterable[str]] = None,
    workers: int = 200,
    timeout: float = 0.5,
) -> List[Candidate]:
    """Scan `targets` (default: local /24) and return every TV-ish host found."""
    hosts = expand_targets(list(targets)) if targets else expand_targets([default_subnet()])
    found: List[Candidate] = []
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for cand in pool.map(lambda h: probe_host(h, timeout), hosts):
            if cand:
                found.append(cand)
    return sorted(found, key=lambda c: tuple(int(x) for x in c.host.split(".")))
