# Example audit output

What `tvkit audit --host 192.168.1.50 --out audit.md` produces (real run, Toshiba `hayward`,
1 GB RAM). Use this shape when attaching a report to an issue.

---

# tvkit audit — Toshiba TT_Fitness TV

| Item | Value |
|---|---|
| Model | Toshiba TT_Fitness TV |
| Device / codename | hayward |
| Android | 11 (SDK 30) |
| Build | RTMA.250416.097 |
| Platform | mt5867 |
| Android TV | yes |
| RAM | 912 MB |
| RAM available | 446 MB |
| Swap used | 300 MB |
| Storage /data | 86% used · 594M free |
| Load average | 57.15 |
| Uptime | 1872.0 h |
| Home | com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity |
| Packages enabled | 125 |
| Packages disabled | 2 |
| Third-party | 13 |
| Resolution | 1920x1080 |

### Health

- RAM is only 912 MB — below the ~1.5 GB Android TV really needs. Software tuning helps, but this is the hardware ceiling.
- Swap is 300 MB used — the system is paging to flash, which is why taps feel laggy.
- Storage is 86% full — Android needs headroom for cache and swap.
- No reboot for 78 days — a reboot clears leaked swap and stale processes.
- Load average is high while RAM looks okay — that is usually kswapd/I-O wait, not CPU.

### Profile match: `toshiba-hayward`

_Toshiba / Hisense-CVTE 'hayward' (Android TV 11, MediaTek MT5867, 1 GB RAM)_

**safe** (11)
- `com.google.android.tvrecommendations` ✅
- `com.google.android.videos` ✅
- `com.google.android.play.games` ✅
- `com.google.android.youtube.tvmusic` ✅
- `com.google.android.backdrop` ✅
- `com.tcl.browser` ✅
- `com.tencent.qqlivei18n` ✅
- `com.iqiyi.i18n.tv` ✅
- `in.startv.hotstar.dplus.tv` ✅
- `com.esaba.downloader` ✅
- `com.ionitech.airscreen` ✅

**balanced** (1)
- `com.android.vending` ✅

**aggressive** (1)
- `com.google.android.katniss` ✅

### Plan — 13 to disable · 0 skipped · 1 warning(s)

| # | package | tier | note |
|---|---|---|---|
| 1 | `com.google.android.tvrecommendations` | safe | the sponsored row on the stock Home screen (often ~100 MB RAM) |
| 2 | `com.google.android.videos` | safe |  |
| 3 | `com.google.android.play.games` | safe |  |
| 4 | `com.google.android.youtube.tvmusic` | safe |  |
| 5 | `com.google.android.backdrop` | safe | ambient screensaver — no functional loss |
| 6 | `com.tcl.browser` | safe | preloaded browser, unused on this model |
| … |  |  |  |

**Side effects**
- com.android.vending: Play Store: frees a lot of RAM on 1 GB devices, but you cannot install/update apps until it is re-enabled

_tvkit 0.1.0 · registry key `66:d7:16:98:31:58`_

---

## After applying

```
### Result — OK ✅

Disabled: 13 · rolled back: 0

| Metric | Before | After | Δ |
|---|---|---|---|
| RAM available | 446 MB | 458 MB | +12 MB |
| RAM free | 20 MB | 162 MB | +142 MB |
| Swap used | 300 MB | 254 MB | -46 MB |
| Storage use | 86% (594M free) | 72% (1.1G free) | -14 pt |
| Load avg | 57.15 | 54.77 | - |
| Disabled packages | 2 | 15 | +13 |

Journal: C:\Users\me\AppData\Roaming\tvkit\journal\20261020-104100-192.168.1.50.json
```
