# Profiles

A profile is a JSON file in `tvkit/profiles/`. Nothing else is needed: no Python, no schema server.
`tvkit profiles` loads and lints every one of them.

## Schema

```json
{
  "name": "acme-x1",
  "title": "Acme X1 (Android TV 12, Amlogic S905X4)",
  "match": {
    "ro.product.device": "^x1$",
    "ro.product.manufacturer": "acme"
  },
  "priority": 70,
  "min_ram_mb": 1024,
  "tiers": {
    "safe":       ["com.google.android.tvrecommendations"],
    "balanced":   ["com.android.vending"],
    "aggressive": ["com.google.android.katniss"]
  },
  "keep": ["com.netflix.ninja", "com.google.android.apps.mediashell"],
  "protected_extra": ["com.acme.engineer.*"],
  "notes": {
    "com.android.vending": "frees ~250 MB but blocks app installs until re-enabled"
  },
  "verified_on": ["Acme X1 / x1 / SDK 31 — 2026-10-20"]
}
```

| field | required | meaning |
|---|---|---|
| `name` | ✅ | unique id, used by `--profile` |
| `title` | | human description |
| `match` | | map of `getprop` name → **regex** (case-insensitive). Empty/absent = generic fallback |
| `priority` | | higher wins when several profiles match (default 0) |
| `min_ram_mb` | | informational; shown in reports |
| `tiers.safe` | | packages that are safe for anyone on this device |
| `tiers.balanced` | | + packages with a usability cost (Play Store) |
| `tiers.aggressive` | | + packages with a clear feature loss (Assistant) |
| `keep` | | packages asserted **enabled** after every apply |
| `protected_extra` | | extra deny-list globs for this device family |
| `notes` | package → side effect shown in `tvkit plan` |
| `verified_on` | | where/how it was tested — please fill this in |

Tiers are **cumulative**: `balanced` = `safe` + `balanced`.

## Rules the linter enforces

* every tier name must be one of `safe`, `balanced`, `aggressive`
* no package may appear twice, or in both a tier and `keep`
* no package may match the global deny-list or `protected_extra`
* package names must look like package names (contain a dot)

`tvkit profiles` exits non-zero if any profile breaks a rule, which is what CI runs.

## Choosing packages safely

A useful order of attack, by risk:

**Almost always safe (Google bloat)**
`com.google.android.tvrecommendations` (sponsored Home row), `com.google.android.videos`,
`com.google.android.play.games`, `com.google.android.youtube.tvmusic`,
`com.google.android.backdrop` (ambient screensaver).

**Safe but check region**
Regional preloads: `com.tencent.qqlivei18n`, `com.iqiyi.i18n.tv`,
`in.startv.hotstar.dplus.tv`, `com.tcl.browser`, `com.esaba.downloader`,
`com.ionitech.airscreen`. Harmless in most countries; verify the user does not watch them.

**Costs RAM back, costs convenience**
`com.android.vending` (Play Store) — 150–300 MB on 1 GB devices. Put it in `balanced` and say
so in `notes`.

**Feature loss**
`com.google.android.katniss` (Google Assistant) — 100–200 MB, kills the remote mic.
`aggressive` tier only.

**Do not touch without a very good reason**
Anything vendor-named (`com.hisense.*`, `com.tcl.*`, `com.xiaomi.*`, `com.skyworth.*`).
Telemetry apps on TV vendors are frequently wired into the launcher or the panel firmware.
A documented Hisense case ended in Android Recovery after `com.hisense.tv.smartsense`,
`com.vt.tv.smartsense.ui` and `com.vt.tv.aiot` were disabled. `hisense-mt.json` therefore
lists them under `protected_extra` and keeps them out of every tier.

## How to find package names

The label on the home screen is **not** the package name. To resolve it:

```bash
adb shell pm list packages -3            # third-party packages
adb shell pm path com.example.app        # where the APK lives
adb pull <path> app.apk
aapt2 dump badging app.apk | grep -E "^package:|^application-label"
```

Example from the field: an app shown as **GODTV** was `com.iptv.newiptvapplication`, and
**Monomax** is `com.doonung.dtv`.

## Test a new profile without risk

```bash
tvkit profiles                                   # lint
tvkit plan --host <ip> --profile acme-x1 --tier safe
tvkit apply --host <ip> --profile acme-x1 --tier safe --yes
tvkit probe --host <ip>                          # before/after numbers
```

If you want to trial a single package: `--only com.example.a`.

## Submitting a profile

1. `tvkit probe --host <ip> --json > probe.json` (or `tvkit audit --out audit.md`)
2. add `tvkit/profiles/<vendor>-<codename>.json`
3. `tvkit profiles && python -m unittest discover -s tests`
4. open a PR with the audit report attached and `verified_on` filled in.

A profile that only lists the Google packages is still useful — it is the honest baseline for
that device family.
