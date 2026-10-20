"""tvkit — debloat, inspect and speed up Android TV / Google TV devices over ADB.

Design goals
------------
* **No hard-coded IPs or models.** Devices are discovered by scanning the LAN and
  identified by their build properties; the right profile is picked by matching
  those properties.
* **Nothing is guessed.** Every package that will be touched is listed, checked
  against a safety deny-list, and verified afterwards. A failed verification
  triggers an automatic rollback of the batch that failed.
* **Reversible.** `pm disable-user` only (never `pm uninstall`), every run writes a
  snapshot + journal, and `tvkit restore` replays the journal in reverse.
* **Portable.** Windows / macOS / Linux, pure Python + `adb-shell`, no adb binary.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
