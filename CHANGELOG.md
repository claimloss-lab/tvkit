# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. Candidate ideas are tracked in the issue tracker.

## [0.1.0] — 2026-10-20

First public release. `tvkit` is a device-agnostic replacement for the usual
"one TV, one hard-coded `pm disable-user` script" approach.

### Added

**Discovery and identification**

- `tvkit discover` — scans a subnet, range, CIDR or explicit host list for
  Android TV devices by probing 5555 (ADB), 6466 (Remote), 8008 (Cast) and
  9000 (TLS), and reads the unauthenticated Cast endpoint
  `/setup/eureka_info` to show the device's user-visible name. Passive: nothing
  is modified.
- `tvkit probe` — one-shot identity + health report: build properties, RAM
  total/free/available, swap total/used, `/data` usage, load average, uptime,
  resolved Home activity, enabled/disabled/third-party package lists and recent
  `logcat -b crash` entries. Ends with plain-language health notes.
- `tvkit audit` — the same data as a Markdown report (`--out report.md`), plus
  the matched profile and the plan; meant to be pasted into an issue.
- `tvkit devices` — a local registry keyed by **MAC address**, so DHCP changes do
  not matter; later commands accept `--device "Living Room"` instead of an IP.

**Profiles**

- Declarative JSON profiles (`tvkit/profiles/*.json`): regex `match` against
  build properties, three cumulative tiers (`safe` → `balanced` →
  `aggressive`), a `keep` list that is asserted enabled after every apply, and
  per-package `notes` that surface as side-effect warnings.
- Six shipped profiles: `generic-androidtv` (fallback), `toshiba-hayward`
  (field-verified), `hisense-mt`, `xiaomi-mitv`, `google-chromecast`,
  `operator-box`.
- `tvkit profiles` — lists and **lints** every profile (duplicate packages,
  keep/disable overlap, protected packages); non-zero exit code, so CI can gate
  a pull request.

**Safety**

- One central deny-list (`tvkit/safety.py`) enforced twice: at profile lint time
  and again immediately before each package is disabled. Covers Cast, setup
  wizards, Live TV/tuner/HDMI services, factory menus, OTA/update services, DRM
  and media framework, GMS/WebView/Settings/SystemUI.
- Runtime launcher rule: never disable the package that currently resolves as
  Home, whatever it is called.
- Verification gates after every apply: Home still resolves, every `keep`
  package is still enabled, every targeted package really is disabled, and no
  *new* crash appeared in `logcat -b crash`.
- Automatic rollback: if any gate fails, everything disabled in that run is
  re-enabled immediately and the command exits `3`.
- Journals: every run writes a JSON record (applied / rolled back / skipped /
  failures / before & after disabled lists) so `tvkit restore --last` can undo
  it later — including from another machine.
- `pm disable-user` only. Nothing is ever uninstalled, no root, no flashing, no
  reboot, and no system settings are changed behind your back.

**Commands**

- `tvkit plan` — dry run; shows what would be disabled, what is skipped (already
  off / not installed / protected / is the running launcher) and which packages
  carry side effects.
- `tvkit apply` — applies a tier with verification and auto-rollback;
  `--dry-run`, `--only <pkg>`, `--yes` for scripting.
- `tvkit restore` — `--last`, `--journal <file>`, `--package <pkg>`,
  `--stock-home`, `--animations`, `--bluetooth`.
- `tvkit screenshot` — pulls a PNG of the current screen; use it for a *before*
  picture so the improvement is provable.
- `tvkit selftest` — 27 offline end-to-end checks against a simulated Android TV,
  no hardware required.

**Portability**

- Pure Python over `adb-shell` — no `adb` binary, no USB cable, no Android
  Studio. Windows, macOS and Linux.
- `--json` on every command; documented exit codes (`0` ok, `1` nothing found,
  `2` bad args/profile, `3` rolled back, `4` ADB error).
- Console output is encoding-safe: on a legacy code page (Windows cp1252/cp437)
  symbols degrade to ASCII instead of raising `UnicodeEncodeError`.

**Docs and packaging**

- `README` (why it exists, quickstart, tiers, safety net, FAQ),
  `docs/USAGE.md` (every command + recipes), `docs/SAFETY.md` (what is touched,
  the deny-list and its rationale, recovery steps), `docs/PROFILES.md` (schema
  and how to add a device), `docs/DEVICES.md` (verified vs expected),
  `docs/report-example.md`.
- `pip install -e .` installs the `tvkit` console script; the wheel ships the
  profiles; `MANIFEST.in` keeps sdist complete.
- GitHub Actions CI: unit tests + offline selftest + profile lint on
  Windows, macOS and Linux × Python 3.9, 3.11, 3.12, plus a ruff job.
- MIT license.

### Verified

| device | platform | Android | result |
|---|---|---|---|
| Toshiba `TT_Fitness TV` (Hisense/CVTE ODM) | `huashan_emT` / `hayward`, MediaTek MT5867, 912 MB RAM, 4 GB storage | 11 (SDK 30) | all three tiers: RAM free 20 → 162 MB, swap in use 307 → 254 MB, storage 86 % → 72 %, processes 1,872 → 1,538, UI noticeably snappier with 0.5 animation scales |

71 unit tests, 27 offline selftest checks, 6 profiles lint-clean, CI green on
all nine OS/Python combinations.

### Known limitations

- `apply` has only been exercised end-to-end on the device above. Other profiles
  ship with the Google-side packages only and are marked as not field-verified.
- Amazon Fire OS is unsupported: it refuses `pm disable-user` for launcher
  packages and ignores `cmd package set-home-activity`. Samsung Tizen and LG
  webOS are not Android at all.
- A TV with 1 GB of RAM cannot be made smooth by software. `tvkit` reports that
  ceiling instead of hiding it; the honest fix is a 2 GB+ Google TV box.
- `tvkit` does not enable ADB. If network debugging is on, anyone on the LAN who
  can accept the on-screen key prompt has access.
- No automatic launcher replacement yet — `tvkit` will not disable the stock
  Home for you. Install and verify your launcher first, then use
  `restore --stock-home` to go back.

### Security

- No credentials are read, stored or transmitted. The only key involved is the
  standard ADB RSA key, reused from `~/.android/adbkey` when it already exists
  so the TV does not prompt twice.
- Device registry and journals live in the user config directory
  (`%APPDATA%\tvkit`, `$XDG_CONFIG_HOME/tvkit`) and are gitignored, so IP and MAC
  addresses never end up in a commit.

[Unreleased]: https://github.com/claimloss-lab/tvkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/claimloss-lab/tvkit/releases/tag/v0.1.0
