# tvkit

[![ci](https://github.com/claimloss-lab/tvkit/actions/workflows/ci.yml/badge.svg)](https://github.com/claimloss-lab/tvkit/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)]()

**Debloat, inspect and speed up Android TV / Google TV over ADB — reversibly, and without hard-coding a single device.**

Most Android TV "debloat scripts" you find online are a list of `pm disable-user` lines
written for one specific TV. Run them on a different box and you can lose Cast, Live TV,
or end up in a recovery screen. `tvkit` is the opposite:

| | typical script | **tvkit** |
|---|---|---|
| Device targeting | hard-coded IP / model | LAN scan → identify by build properties → pick a profile |
| What gets disabled | whatever is in the file | only packages that **exist**, are **not protected**, and are **not the running launcher** |
| Verification | none | every run takes a before/after snapshot and checks gates |
| Failure handling | hope | automatic rollback of the packages it just changed |
| Undo | manual `pm enable` | `tvkit restore --last` (journals are JSON) |
| Reuse | copy-paste | `tvkit/profiles/*.json` are declarative and PR-friendly |

---

## Why it exists

A 1 GB-RAM Android TV out of the box often has ~20 MB of free RAM, 60 % of swap in use and
the Play Store + Assistant + a recommendation feed eating half of memory before you open
anything. That is why the remote feels sticky. You *can* fix most of it in software — but
only if you can measure it and undo it. `tvkit` does both.

It contains **only** `pm disable-user` (never `uninstall`, never root, never a firmware flash).
Anything it can do, `tvkit restore` can undo.

---

## Install

```bash
git clone https://github.com/claimloss-lab/tvkit
cd tvkit
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e .
tvkit --help
```

Python 3.9+. No `adb` binary, no USB cable, no Android Studio.

## Prepare the TV (once)

1. **Settings → About → tap “Build” 7×** → Developer options appear.
2. Enable **USB debugging** *and* **Network debugging / ADB over network**.
3. Reboot the TV, then accept the **“Allow USB debugging?”** dialog (tick *Always allow*).
   The prompt only appears while the TV is showing a picture — wake it first.

## Quickstart

```bash
# 1. find every TV-ish device on the LAN (no IP needed)
tvkit discover
#   HOST            PORTS               NAME                      CAST  ETH
#   192.168.1.50    5555,6466,8008,9000 Living Room TV            12    False

# 2. look at one device — identity, memory, storage, matched profile, health notes
tvkit probe --host 192.168.1.50

# 3. see exactly what would change (writes nothing)
tvkit plan --host 192.168.1.50 --tier safe

# 4. do it (verifies, and rolls back on its own if a gate fails)
tvkit apply --host 192.168.1.50 --tier safe --yes

# 5. something looks wrong? undo the last run
tvkit restore --host 192.168.1.50 --last
```

`tvkit probe` also stores the device in a local registry keyed by MAC address, so later
you can use its name instead of the IP:

```bash
tvkit devices
tvkit apply --device "Living Room" --tier balanced --yes
```

### Tiers

Tiers are **cumulative** — `balanced` = `safe` + balanced.

| tier | what it does | typical win | cost |
|---|---|---|---|
| `safe` | ads / sponsored rows, Play Movies, Play Games, YouTube Music TV, ambient screensaver, regional preloads | 100–300 MB RAM, less Home clutter | none for most people |
| `balanced` | + Play Store | another 150–300 MB on 1 GB devices | cannot install/update apps until re-enabled |
| `aggressive` | + Google Assistant | another 100–200 MB | remote mic / “Ok Google” stop working |

Start at `safe`. Measure. Only move up if you need the RAM.

---

## What it will never touch

The deny-list lives in one place (`tvkit/safety.py`) and is applied **twice**: when a profile
is linted, and again immediately before a package is disabled.

* Cast (`com.google.android.apps.mediashell`) — phones stop casting
* Setup / provisioning wizards — Home can crash-loop
* Live TV, tuner, HDMI and panel services — inputs disappear
* Factory menus and vendor engineering apps — can drop a device into recovery
* OTA / firmware update services
* DRM / media framework packages
* GMS, WebView, Settings, SystemUI, the shell itself
* **the launcher that is currently running Home** (checked at runtime, not by name)

You can add your own patterns per profile with `"protected_extra": ["com.vendor.*"]`.

## Nothing to lose: the safety net

Every `apply` run:

1. takes a **before** snapshot (props, RAM/swap, storage, Home, package lists, recent crashes),
2. disables package by package and parses the reply,
3. takes an **after** snapshot and checks gates:
   - Home still resolves,
   - every `keep` package is still enabled,
   - every package it just disabled really is disabled,
   - no *new* crash appeared in `logcat -b crash`,
4. on any failure → **re-enables everything it disabled in that run** and reports ❌,
5. writes a **journal** to `tvkit/journal/<timestamp>-<host>.json` (applied, rolled back, skipped,
   before/after disabled lists, Python version, tvkit version).

`tvkit restore --last` replays that journal in reverse. Journals are plain JSON — keep them,
commit them, attach them to a bug report.

---

## Profiles

A profile is a small JSON file; there is no DSL to learn.

```json
{
  "name": "toshiba-hayward",
  "title": "Toshiba / Hisense-CVTE 'hayward' (Android TV 11, MT5867, 1 GB RAM)",
  "match": { "ro.product.device": "^hayward$" },
  "priority": 100,
  "tiers": {
    "safe":       ["com.google.android.tvrecommendations", "..."],
    "balanced":   ["com.android.vending"],
    "aggressive": ["com.google.android.katniss"]
  },
  "keep": ["com.ais.mimo.aisplay.tv", "com.netflix.ninja"],
  "protected_extra": ["com.cvte.tv.*"],
  "notes": { "com.android.vending": "frees ~250 MB but blocks app installs" }
}
```

* `match` values are regexes tested against `getprop` values; a profile with an empty
  `match` is the generic fallback and must have the lowest priority.
* `keep` packages are asserted **enabled** after every apply — that is how a profile
  guarantees “don’t break Netflix / AIS Play / my operator box”.
* `notes` show up as side-effect warnings in `tvkit plan`.

Shipped profiles:

| profile | for |
|---|---|
| `generic-androidtv` | any Android TV / Google TV (fallback) |
| `toshiba-hayward` | Toshiba/Hisense-CVTE `hayward`, Android TV 11, MT5867 (field-verified) |
| `hisense-mt` | Hisense / CVTE MediaTek sets — vendor telemetry deliberately excluded |
| `xiaomi-mitv` | Mi TV / Mi Box / TV Box S |
| `google-chromecast` | Chromecast with Google TV, Google TV dongles |
| `operator-box` | ISP boxes (AIS Playbox / SDMC / S905X4) — deliberately conservative |

```bash
tvkit profiles          # list + lint (fails if a profile lists a protected package)
```

### Adding your device

```bash
tvkit probe --host <ip> --json > /tmp/probe.json   # send this in an issue, or:
cp profiles/generic-androidtv.json profiles/acme-x1.json
# edit name/title/match/tiers, then:
tvkit profiles && tvkit plan --host <ip> --profile acme-x1 --tier safe
```

Please include `verified_on` so the next person knows how far to trust it.

---

## Commands

| command | what it does |
|---|---|
| `discover` | scan subnet / range / CIDR for 5555, 6466, 8008, 9000 and read Cast names |
| `probe` | identity, RAM, storage, Home, package counts, matched profile, health notes |
| `audit` | the same as a markdown report (`--out report.md`) |
| `plan` | dry run: what would be disabled / skipped / warned |
| `apply` | disable with verification + auto-rollback (`--dry-run`, `--only`, `--yes`) |
| `restore` | `--last`, `--journal`, `--package`, `--stock-home`, `--animations`, `--bluetooth` |
| `screenshot` | save a PNG of the screen — use it for a *before* shot before your first apply |
| `devices` | local registry (MAC-keyed, survives DHCP) |
| `profiles` | list + lint profile files |
| `selftest` | 27 offline checks against a simulated TV — no device needed |

Global: `--profile-dir`, `--json`, `--port`, `--timeout`.

### Non-ADB extras

`apply` deliberately does not touch system settings. Two settings are worth doing by hand
(or via `tvkit restore` to undo):

```bash
# make the UI feel snappier on slow boxes (undo: value 1.0)
adb shell settings put global window_animation_scale 0.5
adb shell settings put global transition_animation_scale 0.5
adb shell settings put global animator_duration_scale 0.5

# free ~80 MB if you never use a Bluetooth remote
adb shell svc bluetooth disable
```

## Measured result (reference device)

Toshiba `hayward`, Android TV 11, **912 MB RAM**, 4 GB storage, 78 days uptime:

| metric | before | after `safe` + `balanced` + `aggressive` |
|---|---|---|
| RAM free | 20 MB | **162 MB** |
| Swap in use | 307 MB | 254 MB |
| Storage | 86 % used | **72 % used** |
| Processes | 1,872 | 1,538 |
| Feel | remote lag ~1 s | noticeably snappier (animation 0.5) |

That device is still limited by its 912 MB of RAM — `tvkit` says so in the report instead of
pretending software fixed the hardware. If a 1 GB TV still feels slow after this, the honest
answer is a 2 GB+ Google TV box (the report tells you the same thing).

---

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `cannot reach <ip>:5555` | debugging off, TV asleep, or wrong subnet. `tvkit discover` must show 5555. |
| connects, then `unauthorized` | accept the on-screen dialog; if it never appears, revoke USB debugging authorizations in Developer options and retry. |
| `no profile matches` | use `--profile generic-androidtv`, then contribute a profile. |
| Home disappears / crash loop | `tvkit restore --last`; then check what the journal lists. |
| Netflix/Prime drops to SD after a hardware change | that device lacks Widevine L1 — unrelated to tvkit. |
| Play Store says “can’t install” | you applied `balanced`; `tvkit restore --package com.android.vending`. |

## FAQ

**Does it void my warranty / break OTA?**
It only disables apps for user 0; nothing is flashed, no root. OTA packages are on the
deny-list, so updates keep working. Still: a vendor may refuse service on modified devices.

**Will it work on Fire TV / Samsung Tizen / LG webOS?**
No — Fire OS needs its own profile and is untested; Tizen and webOS do not use Android
packages at all.

**Is disabling packages the same as uninstalling?**
No. `disable-user` keeps the APK, frees no storage, and is reversible with `pm enable`.
tvkit never uninstalls anything.

**Why JSON profiles and not YAML?**
Zero dependencies, and the file can be reviewed in a PR without a parser.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most valuable contribution is a **profile plus a
`tvkit audit` report** from a device nobody has covered yet.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Release process: [docs/RELEASING.md](docs/RELEASING.md).

## License

MIT. `tvkit` is an independent implementation; it was inspired by the idea of scripted
Android TV debloating (e.g. `Gathin23/tv-vibehack`) but shares no code with it.
