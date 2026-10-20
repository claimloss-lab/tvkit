"""ADB transport layer.

A thin wrapper over `adb_shell` so the rest of tvkit only needs `shell()`.
No `adb` binary required, no USB, works over the network (ADB over Wi-Fi).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

DEFAULT_PORT = 5555
CONNECT_TIMEOUT = 12.0
SHELL_TIMEOUT = 60.0


class AdbError(RuntimeError):
    """Raised when the device cannot be reached or a shell command fails to run."""


def _key_dir() -> Path:
    override = os.environ.get("TVKIT_KEYDIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.environ.get("APPDATA") or "~/.config"
    return Path(base).expanduser() / "tvkit" / "keys"


def _signer():
    """Return an RSA signer, reusing the platform-tools key when present.

    Reusing ``~/.android/adbkey`` means the TV does not pop a second
    "Allow USB debugging?" dialog for people who already use platform-tools
    or Android Studio.
    """
    from adb_shell.auth.keygen import keygen
    from adb_shell.auth.sign_pythonrsa import PythonRSASigner

    trusted = Path.home() / ".android" / "adbkey"
    if trusted.exists() and Path(str(trusted) + ".pub").exists():
        key = trusted
    else:
        keydir = _key_dir()
        keydir.mkdir(parents=True, exist_ok=True)
        key = keydir / "adbkey"
        if not key.exists():
            keygen(str(key))
    return PythonRSASigner(
        Path(str(key) + ".pub").read_text(encoding="utf-8"),
        key.read_text(encoding="utf-8"),
    )


class Device:
    """One Android TV reached over TCP."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = CONNECT_TIMEOUT):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._dev = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> "Device":
        try:
            from adb_shell.adb_device import AdbDeviceTcp
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AdbError(
                "adb-shell is not installed. Run: pip install -e . "
                "(or: pip install adb-shell rsa cryptography)"
            ) from exc

        dev = AdbDeviceTcp(self.host, self.port, default_transport_timeout_s=self.timeout)
        try:
            dev.connect(
                rsa_keys=[_signer()],
                transport_timeout_s=self.timeout,
                auth_timeout_s=self.timeout + 8,
            )
        except Exception as exc:  # adb_shell raises a zoo of exception types
            raise AdbError(
                f"cannot reach {self.host}:{self.port} — {type(exc).__name__}: {exc}"
            ) from exc
        self._dev = dev
        return self

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc_info):
        self.close()

    # -- commands ----------------------------------------------------------
    def shell(self, command: str, timeout: float = SHELL_TIMEOUT) -> str:
        """Run one shell command, return stdout+stderr as text."""
        if self._dev is None:
            raise AdbError("not connected")
        try:
            out = self._dev.shell(command, read_timeout_s=timeout, timeout=timeout)
        except Exception as exc:
            raise AdbError(f"`{command}` failed — {type(exc).__name__}: {exc}") from exc
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return (out or "").replace("\r\n", "\n")

    def getprop(self, name: str) -> str:
        return self.shell(f"getprop {name}").strip()

    def pull(self, remote: str, local: str, timeout: float = 300.0) -> None:
        if self._dev is None:
            raise AdbError("not connected")
        self._dev.pull(remote, local, transport_timeout_s=timeout, read_timeout_s=timeout)

    def push(self, local: str, remote: str, timeout: float = 300.0) -> None:
        if self._dev is None:
            raise AdbError("not connected")
        self._dev.push(local, remote, transport_timeout_s=timeout, read_timeout_s=timeout)

    # -- convenience -------------------------------------------------------
    def is_screen_on(self) -> Optional[bool]:
        for line in self.shell("dumpsys power | grep -m1 mWakefulness").splitlines():
            if "mWakefulness=" in line:
                state = line.split("mWakefulness=", 1)[1].strip()
                return state.lower() in ("awake", "dreaming")
        return None

    def wait_for_boot(self, timeout: float = 120.0, interval: float = 3.0) -> bool:
        """Poll until the framework reports boot completed."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.getprop("sys.boot_completed") == "1":
                    return True
            except AdbError:
                pass
            time.sleep(interval)
        return False


def probe_port(host: str, port: int = DEFAULT_PORT, timeout: float = 0.6) -> bool:
    """True when a TCP port accepts a connection (used by the discovery scanner)."""
    import socket

    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        sock.close()
