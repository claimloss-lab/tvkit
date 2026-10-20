# Supported devices

tvkit is device-agnostic: it identifies a TV from its build properties and picks a profile.
This page tracks what has actually been verified and what is only “should work”.

## Verified

| device | platform / SoC | Android | profile | result |
|---|---|---|---|---|
| Toshiba `TT_Fitness TV` (Hisense/CVTE ODM) | `huashan_emT` / `hayward`, MediaTek MT5867, 912 MB RAM, 4 GB storage | 11 (SDK 30) | `toshiba-hayward` | `safe` + `balanced` + `aggressive`: RAM free 20 → 162 MB, storage 86 % → 72 %, processes 1,872 → 1,538 |

Notes from that device that generalise:

* `com.google.android.tvrecommendations` **comes back after every reboot** (normal GMS
  behaviour) — re-apply, or accept the sponsored row.
* The Play Store was the single biggest consumer (~266 MB across app + background process) on
  a 1 GB device.
* High `loadavg` with high CPU idle is `kswapd`/`kverityd` I/O wait, not CPU. Fixing RAM and
  storage is what actually helps.
* 912 MB is below what Android TV 11 wants (~1.5 GB). Software tuning helps but is not a cure;
  the report says so instead of overselling.

## Should work (profile shipped, not field-verified)

| family | profile | caveat |
|---|---|---|
| Hisense / CVTE MediaTek sets | `hisense-mt` | only Google-side packages; vendor telemetry deliberately excluded (recovery risk) |
| Xiaomi Mi TV / Mi Box / TV Box S | `xiaomi-mitv` | vendor home tabs (`michannel`) are in `safe` — check you do not use PatchWall |
| Chromecast with Google TV / Google TV dongles | `google-chromecast` | never swap Home on a dongle; Play Store kept on purpose |
| ISP / operator boxes (AIS Playbox, SDMC, S905X4) | `operator-box` | rented hardware — Google extras only |

## Known-unsupported

| device | why |
|---|---|
| Samsung Tizen, LG webOS | not Android; no `pm`, no ADB packages |
| Amazon Fire TV / Fire OS | Android fork with Amazon's own launcher protection; `pm disable-user` is refused for launcher packages and `cmd package set-home-activity` is ignored. Debloat-only, needs its own profile and care. |
| Apple TV | tvOS, unrelated |
| Android phones / tablets | tvkit assumes a TV Home and would need a different keep list |

## Identifying a device

```bash
tvkit probe --host <ip> --json | python -c "import json,sys;d=json.load(sys.stdin);print(json.dumps(d['props'],indent=2))"
```

The two properties that matter most for profile matching:

* `ro.product.device` — the codename (`hayward`, `sabrina`, `machuca`, …), stable per model
* `ro.board.platform` — the SoC family (`mt5867`, `amlogic`, `s905x4`, …)

`ro.product.model` is the marketing name and is often localised or duplicated across models —
use it as a hint, not a key.

## Adding your device

1. `tvkit probe --host <ip> --json > probe.json`
2. copy `tvkit/profiles/generic-androidtv.json` → `tvkit/profiles/<vendor>-<codename>.json`
3. set `match` from `ro.product.device` (regex, e.g. `"^hayward$"`), raise `priority` to ~100
4. fill `tiers` with what exists on your box (`probe` lists enabled packages)
5. add a `keep` list: everything the household actually uses (streaming apps, operator apps,
   the launcher you run)
6. `tvkit plan`, then `tvkit apply --tier safe`, then `tvkit probe` for before/after
7. PR with the audit report and `verified_on`

## Not covered by profiles: hardware

If a TV has **1 GB RAM**, no amount of debloating makes it smooth. tvkit reports the ceiling
rather than hiding it. Practical upgrade paths, for reference:

| option | RAM | notes |
|---|---|---|
| Xiaomi TV Box S (3rd Gen) | 2 GB / 32 GB | 6 nm A55, GPU +130 % vs 2nd Gen, Wi-Fi 6, Google TV, Dolby Vision |
| Xiaomi TV Box S (2nd Gen) | 2 GB / 8 GB | cheaper, older, storage is tight |
| Chromecast with Google TV (HD) | 1.5 GB | smallest/cheapest Google TV option |

Avoid no-name `RK3528` boxes: Cortex-A53 + Mali-450 (older than many TVs' internal SoCs), AOSP
instead of Android TV, and typically no Widevine L1 — Netflix plays in SD.
