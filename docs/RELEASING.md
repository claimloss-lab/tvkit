# Releasing

Checklist used for each tagged release. Keep it short enough to actually follow.

## 1. Pre-flight (must all be green)

```bash
python -m unittest discover -s tests -v     # unit tests
python -m tvkit selftest                     # offline end-to-end, no device
python -m tvkit profiles                     # profile lint
ruff check .                                 # style
```

Then sanity-check the packaged artifact, because a repo can be green while the **wheel** is
broken (profiles missing, entry point missing):

```bash
python -m build --wheel --outdir /tmp/tvkit-dist
python -m venv /tmp/wheelcheck
/tmp/wheelcheck/bin/pip install /tmp/tvkit-dist/tvkit-*.whl
/tmp/wheelcheck/bin/tvkit --version
/tmp/wheelcheck/bin/tvkit profiles      # must load profiles from site-packages
/tmp/wheelcheck/bin/tvkit selftest
```

## 2. Update the changelog

In `CHANGELOG.md`:

- move everything from `## [Unreleased]` into a new `## [x.y.z] — YYYY-MM-DD` section,
- add the two link references at the bottom
  (`[Unreleased]: .../compare/vX.Y.Z...HEAD`, `[x.y.z]: .../releases/tag/vX.Y.Z`),
- bump `version` in `pyproject.toml` and `__version__` in `tvkit/__init__.py` **in the same
  commit** — they must never disagree.

## 3. Release notes

Write `.github/RELEASE_NOTES_v<x.y.z>.md`. Structure that works:

1. one-line what-it-is,
2. **why you might care** — a concrete before/after table beats adjectives,
3. install + 60-second quickstart,
4. highlights (the 3–5 things that are actually different),
5. **known limitations** — say what is *not* verified. This is the section people trust,
6. contributing ask + license.

## 4. Tag and publish

```bash
git add -A
git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "tvkit vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

With the GitHub CLI:

```bash
gh release create vX.Y.Z \
  --title "tvkit vX.Y.Z" \
  --notes-file .github/RELEASE_NOTES_vX.Y.Z.md
```

Without `gh`: repo → **Releases** → **Draft a new release** → choose the tag → paste the
contents of the release-notes file → **Publish**.

## 5. After publishing

- confirm the CI badge on the tag commit is green,
- confirm the release page renders the notes (Markdown tables are the usual casualty),
- if a wheel was attached, `pip install <url>.whl` in a fresh venv and run `tvkit selftest`,
- update the README “Measured result” only with numbers you re-measured — never copy old ones
  forward without checking.

## Versioning

Semantic versioning, with this reading of “breaking”:

| change | bump |
|---|---|
| a profile starts disabling something it did not before, or the CLI/JSON shape changes | **major** |
| new command, new profile, new tier entry that is additive and safe | **minor** |
| bug fix, doc, encoding fix, test | **patch** |

`0.x` is pre-1.0: minor bumps may still adjust defaults, but never silently widen what gets
disabled — that always needs a major.
