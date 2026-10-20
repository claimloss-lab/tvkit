# tvkit v0.1.0

**Debloat, inspect and speed up Android TV / Google TV over ADB — reversibly, and without
hard-coding a single device.**

Most debloat scripts on the internet are a list of `pm disable-user` lines written for one
specific TV. Run them on a different box and you can lose Cast, lose Live TV, or end up in a
recovery screen. `tvkit` is the opposite: it finds your TV, identifies it from its build
properties, picks a declarative profile, and **verifies + rolls back automatically** if
something goes wrong.

## Why you might care

A 1 GB Android TV out of the box often has ~20 MB of free RAM, 60 % of swap in use, and the
Play Store + Assistant + a recommendation feed eating half of memory before you open anything.
That is why the remote feels sticky. You *can* fix most of that in software — but only if you
can measure it and undo it.

Real result from the reference device (Toshiba `hayward`, 912 MB RAM, 78 days uptime):

| metric | before | after |
|---|---|---|
| RAM free | 20 MB | **162 MB** |
| Swap in use | 307 MB | 254 MB |
| Storage `/data` | 86 % | **72 %** |
| Processes | 1,872 | 1,538 |
| Feel | ~1 s remote lag | noticeably snappier (animation 0.5) |

## Install

```bash
git clone https://github.com/claimloss-lab/tvkit
cd tvkit
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -e .
tvkit --help
```

Python 3.9+. No `adb` binary, no USB cable, no Android Studio. Windows, macOS, Linux.

## 60-second quickstart

```bash
tvkit discover                                  # find TVs on the LAN — no IP needed
tvkit probe  --host 192.168.1.50                # identity, RAM, storage, matched profile
tvkit plan   --host 192.168.1.50 --tier safe    # dry run; changes nothing
tvkit apply  --host 192.168.1.50 --tier safe --yes
tvkit restore --host 192.168.1.50 --last        # undo everything from that run
```

Prerequisite on the TV (once): Settings → About → tap **Build** 7× → Developer options →
enable **USB debugging** *and* **Network debugging**, then accept the “Allow USB debugging?”
dialog while the TV is showing a picture.

## Highlights

**No hard-coded devices.** `discover` probes 5555/6466/8008/9000 and reads the Cast endpoint
for the device name. Profiles match on `getprop` values (regex) — six ship today, including a
generic fallback, so an unknown TV still gets the safe Google-side cleanup.

**Cumulative tiers.** `safe` (ads, sponsored rows, unused Google apps, regional preloads) →
`balanced` (+ Play Store, 150–300 MB on 1 GB devices) → `aggressive` (+ Assistant, kills the
remote mic). Start at `safe`, measure, only then move up.

**Safety is the feature, not the disclaimer.**

- a central deny-list (Cast, setup wizards, Live TV/tuner/HDMI, factory menus, OTA, DRM)
  enforced twice — at profile lint and again right before each package is touched;
- never disables the package that currently resolves as **Home** (checked at runtime);
- every apply takes before/after snapshots and gates on: Home resolves, `keep` packages still
  enabled, targets really disabled, **no new crash** in `logcat -b crash`;
- any failure → everything from that run is re-enabled automatically, exit code `3`;
- `disable-user` only. Nothing is uninstalled, no root, no flashing, no reboots, and system
  settings are never changed behind your back;
- a JSON journal per run, so `restore --last` (or a journal copied from another machine)
  undoes it.

**Evidence built in.** `tvkit screenshot` for a before picture, `tvkit audit --out report.md`
for a shareable report, `--json` on every command, documented exit codes for scripting.

## What's in the box

| | |
|---|---|
| commands | `discover` `probe` `audit` `plan` `apply` `restore` `screenshot` `devices` `profiles` `selftest` |
| profiles | `generic-androidtv` · `toshiba-hayward` · `hisense-mt` · `xiaomi-mitv` · `google-chromecast` · `operator-box` |
| docs | `README` · `docs/USAGE.md` · `docs/SAFETY.md` · `docs/PROFILES.md` · `docs/DEVICES.md` · `docs/report-example.md` |
| tests | 71 unit tests · 27-check offline selftest · CI on Windows/macOS/Linux × Python 3.9/3.11/3.12 |

## Known limitations

- `apply` is field-verified on **one** device (Toshiba `hayward`). Every other profile ships
  with the Google-side packages only and is marked as not field-verified — that is deliberate
  honesty, not a gap to paper over.
- Amazon Fire OS is unsupported (it refuses `pm disable-user` on launcher packages and ignores
  `set-home-activity`). Tizen and webOS are not Android.
- A 1 GB TV cannot be made smooth by software. The report says so; the honest fix is a 2 GB+
  Google TV box.
- `tvkit` does not enable ADB, and does not replace your launcher for you.

## Contributing

The most valuable contribution is **a profile plus a `tvkit audit` report** for a device nobody
has covered. `tvkit profiles` lints profile files and CI runs it, so a bad profile cannot land.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/PROFILES.md](docs/PROFILES.md).

## License

MIT.

---

Full details: [CHANGELOG.md](CHANGELOG.md).
