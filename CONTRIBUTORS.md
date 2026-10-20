# Contributors

`tvkit` exists because one TV was too slow to watch Netflix on. Everything here was built,
measured and un-broken on real hardware first.

## Maintainers

| who | role | device coverage |
|---|---|---|
| [@claimloss-lab](https://github.com/claimloss-lab) | author, maintainer | Toshiba `hayward` (Hisense/CVTE, Android TV 11, 912 MB RAM) — the reference device |

## How to be added

You do not need to write code. The most valuable contribution is **field data** — a profile
plus a `tvkit audit` report from a TV nobody has tested.

| contribution | credit line |
|---|---|
| a new profile with a `verified_on` entry | listed under *Device reports* with your handle and the model |
| a bug report with a journal + probe JSON that led to a fix | listed under *Bug reports* |
| code, docs, tests | listed under *Code* |

Open a PR adding yourself to the relevant table. That is the whole process — the PR is the
recognition, and CI keeps it honest.

## Device reports

Profiles that are backed by an actual run (before/after numbers attached to the PR):

| device | profile | reported by |
|---|---|---|
| Toshiba `TT_Fitness TV` — `huashan_emT` / `hayward`, MT5867, 912 MB RAM, SDK 30 | `toshiba-hayward` | [@claimloss-lab](https://github.com/claimloss-lab) |

## Code and docs

| who | what |
|---|---|
| [@claimloss-lab](https://github.com/claimloss-lab) | everything in v0.1.0: transport, discovery, snapshot, profiles, safety model, apply/rollback, journals, CLI, reports, tests, docs |

## Bug reports

| who | what |
|---|---|
| — | be the first; a `tvkit probe --json` + journal is worth more than a paragraph |

## Acknowledgements

- **[Gathin23/tv-vibehack](https://github.com/Gathin23/tv-vibehack)** — the project that showed
  how far a pure-Python ADB client plus a launcher can go on a stock Android TV, and whose
  Hisense recovery incident is the reason `tvkit` refuses to touch vendor telemetry packages.
  `tvkit` is an independent implementation and shares no code with it.
- **The `pm disable-user` crowd** — every forum thread that documented which package breaks
  which TV input. The deny-list in `tvkit/safety.py` is a distillation of those reports.
- **[adb-shell](https://github.com/JeffLIrion/adb_shell)** — pure-Python ADB, which is why
  `tvkit` needs neither a cable nor the `adb` binary.

## Not listed but not forgotten

If you sent a package list, a screenshot of a recovery screen, or a “this package broke my
HDMI input” message and are not in the tables above, open a PR and add yourself — the credit
was earned.
