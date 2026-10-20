# Usage

Every command accepts `--json`, so tvkit can sit inside a script or a cron job.

```
tvkit [--profile-dir DIR] <command> [options]
```

## Exit codes

| code | meaning |
|---|---|
| 0 | success (gates passed) |
| 1 | nothing found / user cancelled |
| 2 | bad arguments or profile error |
| 3 | apply finished but a gate failed → **rolled back** |
| 4 | ADB transport error |

That makes `apply` safe to use in automation:

```bash
tvkit apply --host "$TV" --tier safe --yes || echo "tvkit refused or rolled back"
```

---

## 1. Find devices

```bash
tvkit discover                      # scan the local /24
tvkit discover --target 10.0.0      # a different /24
tvkit discover --target 10.0.0.20-40
tvkit discover --target 10.0.0.0/22
tvkit discover --json
```

Discovery is passive: it opens TCP connections to 5555 (ADB), 6466 (Remote), 8008 (Cast),
9000 (TLS) and — when 8008 answers — reads the unauthenticated Cast endpoint
`/setup/eureka_info` for the device **name**. A device with `5555` is ready for tvkit;
the others are listed so you know what is on the network and what still needs
network debugging enabled.

## 2. Understand a device

```bash
tvkit probe --host 192.168.1.50
tvkit probe --host 192.168.1.50 --json > probe.json
tvkit probe --device "Living Room"          # from the registry
tvkit audit --host 192.168.1.50 --out audit.md
```

`probe` reads (never writes):

* build properties — model, manufacturer, codename, platform, Android/SDK, build id
* memory — total / free / available, swap total / used
* storage — size, used, free, % on `/data`
* load average, uptime
* resolved Home activity
* enabled / disabled / third-party package lists
* recent `logcat -b crash` entries

and then prints *health notes* — for example “RAM is only 912 MB, software tuning helps but
this is the hardware ceiling”, or “swap is 307 MB used, the system is paging to flash”.

`audit` is the same data as a Markdown report plus the matched profile and its plan; paste it
into a GitHub issue when you want a profile for your device.

## 3. Dry run

```bash
tvkit plan --host 192.168.1.50 --tier safe
tvkit plan --host 192.168.1.50 --tier aggressive --json
tvkit plan --host 192.168.1.50 --tier safe --all      # include packages not installed
```

The plan marks each package `pending`, `skipped` (already disabled / not installed /
protected / is the running launcher) and lists **side effects** (e.g. “Play Store: frees a lot
of RAM but you cannot install apps until re-enabled”).

## 4. Apply

```bash
tvkit apply --host 192.168.1.50 --tier safe            # asks for confirmation
tvkit apply --host 192.168.1.50 --tier safe --yes      # no prompt (for scripts)
tvkit apply --host 192.168.1.50 --tier safe --dry-run  # same as `plan`
tvkit apply --host 192.168.1.50 --only com.android.vending --yes
```

Workflow that keeps you out of trouble:

1. `apply --tier safe` → check that Home, Cast and your streaming apps still work,
2. wait a day, live with it,
3. only then consider `--tier balanced` (Play Store) or `--tier aggressive` (Assistant).

Each run prints a before/after table and writes a journal. If anything fails, the affected
packages are re-enabled automatically and the exit code is `3`.

## 4.1 Take a screenshot before you start

```bash
tvkit screenshot --host 192.168.1.50 --out ./evidence     # saves toshiba-tt-fitness-tv-<ts>.png
```

Use it for a **before** picture, then again after `apply`. Photos of “before: ads everywhere /
after: clean dock” are the easiest proof when you file an issue or show someone what changed.

## 5. Restore

```bash
tvkit restore --host 192.168.1.50 --last                     # newest journal for this host
tvkit restore --host 192.168.1.50 --journal 20261020-...json
tvkit restore --host 192.168.1.50 --package com.android.vending
tvkit restore --host 192.168.1.50 --animations               # 0.5 -> 1.0
tvkit restore --host 192.168.1.50 --bluetooth                # svc bluetooth enable
tvkit restore --host 192.168.1.50 --stock-home               # Android TV Launcher back
```

`--stock-home` re-enables `com.google.android.tvlauncher` and points Home at it. Your
replacement launcher is **not** uninstalled, so you can switch back the same way.

## 6. Registry

```bash
tvkit devices
tvkit devices --json
```

Stored at:

| OS | path |
|---|---|
| Windows | `%APPDATA%\tvkit\devices.json` |
| macOS / Linux | `$XDG_CONFIG_HOME/tvkit/devices.json` (or `~/.config/tvkit/`) |

Keyed by MAC address, so DHCP does not matter. Override the whole state directory with
`TVKIT_HOME`, keys with `TVKIT_KEYDIR`, profiles with `TVKIT_PROFILE_DIR`.

Nothing in the state directory is ever committed to git.

---

## Recipes

### Night shift (don't wake anyone)

```bash
adb -s <ip>:5555 shell cmd media_session volume --stream 3 --set 0   # mute first
adb -s <ip>:5555 shell input keyevent 223                            # KEYCODE_SLEEP
tvkit apply --host <ip> --tier safe --yes                            # no reboot involved
```

tvkit never reboots a device. If you need a reboot to clear swap, do it in the morning —
a boot logo lights up the whole room.

### Batch several TVs

```bash
for host in $(tvkit discover --json | python -c "import json,sys;print(' '.join(d['host'] for d in json.load(sys.stdin) if d['adb_ready']))"); do
  echo "== $host"
  tvkit apply --host "$host" --tier safe --yes --json | tail -n +1
done
```

### Nightly health check (cron / Task Scheduler)

```bash
0 9 * * *  tvkit probe --host 192.168.1.50 --json > /var/log/tvkit/livingroom.json
```

Get alerted when `memory.free_kb` collapses or `storage.use_pct` crosses 80.

### Compare two snapshots

```bash
tvkit probe --host $TV --json > before.json
tvkit apply  --host $TV --tier balanced --yes
tvkit probe --host $TV --json > after.json
python - <<'PY'
import json
b, a = (json.load(open(f)) for f in ("before.json", "after.json"))
for key in ("ram_mb",):
    print(key, b[key], "->", a[key])
print("free MB", b["memory"]["free_kb"]//1024, "->", a["memory"]["free_kb"]//1024)
print("storage %", b["storage"]["use_pct"], "->", a["storage"]["use_pct"])
PY
```
