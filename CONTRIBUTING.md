# Contributing

Thanks for wanting to help. The single most useful contribution is **a profile for a device
nobody has covered**, plus the audit report that proves it works.

## Development setup

```bash
git clone https://github.com/OWNER/tvkit
cd tvkit
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a PR

```bash
python -m unittest discover -s tests -v   # 48 tests, no device needed
tvkit selftest                            # 27 end-to-end checks on a simulated TV
tvkit profiles                            # profile lint (exit 0 required)
ruff check .                              # optional, style
```

CI runs the same three commands on Linux, macOS and Windows.

## Adding a profile

1. Capture the device:

   ```bash
   tvkit probe --host <ip> --json > probe.json
   tvkit audit --host <ip> --out audit-<device>.md
   ```

2. Create `tvkit/profiles/<vendor>-<codename>.json`. Start from
   `tvkit/profiles/generic-androidtv.json`; see [docs/PROFILES.md](docs/PROFILES.md) for the schema.

3. Match on `ro.product.device` (stable codename), not on the marketing model:

   ```json
   "match": { "ro.product.device": "^x1$" },
   "priority": 100
   ```

4. Put anything the household actually uses in `keep` — the verification gates assert those
   stay enabled.

5. Set `verified_on` to the exact build you tested:

   ```json
   "verified_on": ["Acme X1 / x1 / RTMA.250416.097 / SDK 30 — 2026-10-20"]
   ```

6. Verify locally:

   ```bash
   tvkit profiles
   tvkit plan --host <ip> --profile <name> --tier safe
   tvkit apply --host <ip> --profile <name> --tier safe --yes
   tvkit probe --host <ip>            # before/after numbers for the PR
   ```

7. Open the PR with the audit report (redact MAC/IP if you care) and the numbers.

## Rules of the road

* **Never** add a package to a profile that you have not seen actually exist on that device.
  Packages that do not exist are skipped, but an unverified guess makes the profile untrustworthy.
* **Never** put vendor telemetry or anything vendor-named into `safe` without evidence. If it
  is risky, leave it out and document why in `notes` — that is a valid contribution too.
* **Never** suggest uninstalling. tvkit is `disable-user` only, by design.
* Keep profiles minimal and honest. “I only verified 5 packages” beats a 40-line guess.
* No new runtime dependencies without discussion. Currently: `adb-shell`, `rsa`, `cryptography`.

## Code layout

| file | responsibility |
|---|---|
| `tvkit/adb.py` | transport (adb-shell), no policy |
| `tvkit/discover.py` | LAN scan + Cast metadata |
| `tvkit/snapshot.py` | read-only device state |
| `tvkit/profiles.py` | profile schema/loading/matching |
| `tvkit/safety.py` | deny-list, launcher rule, verification gates |
| `tvkit/apply.py` | plan/apply/rollback + journals |
| `tvkit/report.py` | markdown + JSON output |
| `tvkit/cli.py` | argparse wiring only |
| `tvkit/selftest.py` | offline simulated device used by `tvkit selftest` and tests |

Policy must not leak into `adb.py`; anything that decides *what* to change belongs in
`safety.py` or a profile.

## Bug reports

Include:

* `tvkit --version`, OS, Python version
* `tvkit probe --host <ip> --json` (redact MAC/IP)
* the journal from the failing run (`<state>/journal/*.json`)
* what you expected vs what happened

## Code of conduct

Be decent. People run this on the TV their family watches.
