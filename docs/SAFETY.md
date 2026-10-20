# Safety model

tvkit changes a device you cannot easily re-flash. This document explains exactly how far it
goes and how it protects you.

## What tvkit does

| operation | command | reversible? |
|---|---|---|
| disable an app for user 0 | `pm disable-user --user 0 <pkg>` | yes — `pm enable` |
| write a journal | local JSON | n/a |
| read everything else | `getprop`, `dumpsys`, `pm list`, `logcat`, `df` | n/a |

## What tvkit never does

* `pm uninstall` — no app is removed, no storage is freed this way (so a mistake costs nothing)
* `rm`, `mount`, `setprop` of persistent props
* root, `su`, `fastboot`, flashing, OTA manipulation
* reboots
* changing the resolved launcher
* changing system settings (animation scale, Bluetooth) — documented in USAGE, done by you
* touching packages that match the deny-list

## The deny-list

`tvkit/safety.py::PROTECTED_PATTERNS` — enforced twice (profile lint + pre-flight check):

```
Cast            com.google.android.apps.mediashell, com.google.android.gms.cast*
Setup           *setupwizard*, com.google.android.tungsten.*, com.android.provision*
Core            android, systemui, settings, tv.settings, shell, packageinstaller,
                permissioncontroller, gms, gsf, webview, tts
Live TV         com.mediatek.wwtv.*, com.mediatek.tv*, com.mstar.tv*, com.realtek.tv*,
                com.amlogic.tv*, com.hisense.tv.*input*
Factory         com.cvte.tv.fac*, com.at.factory*, *factorymenu*
OTA             *ota*, com.*.*update*
DRM / media     com.google.android.drm*, com.widevine*, com.android.media*
Remote / BT     com.android.bluetooth, com.google.android.tv.remote*
```

Rationale, from real failures:

* **Setup wizard** — disabling it puts Home in a crash loop on several Hisense/CVTE builds:
  the launcher waits for provisioning to finish.
* **Vendor engineering / factory menus** — one documented case dropped a Hisense Android TV
  into `Android Recovery` with “Can’t load Android system”. Recovery → *Try again* boots fine;
  *Factory data reset* erases the TV.
* **`mediashell`** — Cast stops working; the TV still looks fine until someone tries to cast.
* **Live TV / tuner services** — the panel loses HDMI inputs and the channel list.
* **DRM packages** — playback silently drops to a lower resolution or fails.
* **OTA** — users need security patches; disabling update services is not a performance win.

## The launcher rule

The most common way to brick the *experience* is disabling the current Home before a
replacement is installed and verified. tvkit checks the **resolved Home activity at runtime**
(`cmd package resolve-activity … HOME`) and refuses to disable whatever package provides it.
Because it checks at runtime, it also works if you use a third-party launcher.

## Verification gates

After every `apply`:

1. Home resolves (and is not “No activity found”),
2. every package in the profile's `keep` list that exists on the device is **enabled**,
3. every package the run disabled is actually reported disabled,
4. `logcat -b crash` contains **no new crash lines** compared with the before snapshot.

Any failure → all packages disabled in that run are re-enabled, the run is marked failed,
exit code 3, and the journal records `rolled_back`.

The `keep` list is your contract: “whatever else happens, these keep working”. Profiles for
operator boxes and consoles put the streaming apps there.

## Journals

`<state>/journal/<timestamp>-<host>.json`:

```json
{
  "tvkit": "0.1.0",
  "host": "192.168.1.50",
  "profile": "toshiba-hayward",
  "tier": "safe",
  "ok": true,
  "applied": ["com.google.android.tvrecommendations", "..."],
  "rolled_back": [],
  "failures": [],
  "before_disabled": ["com.google.android.marvin.talkback"],
  "after_disabled": ["...", "com.google.android.tvrecommendations"]
}
```

Keep them next to your backup of the TV's package list. To undo on another machine, copy the
journal over and run `tvkit restore --journal <file>`.

## If something goes wrong

**Home is black / boots into a launcher crash loop**
1. Wait 60 s — Android usually falls back to the other launcher.
2. `tvkit restore --host <ip> --last` (ADB still works — the framework is up).
3. Still stuck? `tvkit restore --host <ip> --stock-home`.

**TV shows “Can’t load Android system” (Recovery)**
1. Choose **Try again** — this boots normally and keeps your data.
2. If it comes back, boot to recovery again and clear cache partition.
3. **Do not choose “Factory data reset”** until you have the package list backed up.
4. `tvkit restore --last` as soon as ADB is reachable again.

**ADB stopped working**
1. Developer options → revoke USB debugging authorizations, re-enable network debugging.
2. Reboot the TV, accept the dialog.
3. `tvkit discover` must show 5555 again.

## Threat model (what tvkit does *not* protect you from)

* A profile that disables something **nobody has tested** but that is not on the deny-list.
  Mitigation: tiers, dry run, keep list, verification gates — and starting with `safe`.
* Vendor firmware updates that change package names. Mitigation: packages that no longer
  exist are skipped, never fatal.
* Someone else on your LAN with ADB access. tvkit does not enable ADB; if it is on, the TV is
  open to anyone who accepts the key prompt on screen.
* Electricity, warranty, service terms. Rented ISP boxes may not allow any modification.

If you are unsure, `tvkit plan` costs nothing and changes nothing. Read it.
