# Cycle 34 — Step 6 Context7 Verification

**Date:** 2026-04-25 · **Cycle:** 34 · **Mode:** primary (Sonnet-equivalent lookup, not judgment).

## Libraries verified

### `actions/setup-python`
- **Live latest:** `@v6` (per Context7 `/actions/setup-python` README + advanced-usage docs).
- **Design doc said:** `@v5`.
- **Decision:** Use `@v6`. Cycle 34's CI workflow is greenfield; bump to current latest.
- **Bonus:** Add `cache: 'pip'` and `cache-dependency-path: 'requirements.txt'` for CI speed (auto-detects `requirements.txt`; saves 30-60s per run).

### `actions/checkout`
- **Live latest:** `@v6` (parallel version bump alongside `setup-python`).
- **Design doc said:** `@v4`.
- **Decision:** Use `@v6`.

### `pip-audit`
- **Verified flags (live + Context7 `/pypa/pip-audit`):**
  - `--ignore-vuln ID` is repeatable (`action="append"` per parser; R2 verified live).
  - `-r REQUIREMENT` audits a requirements file; can be used multiple times.
  - `-S, --strict` fails the entire audit on any dependency-collection failure.
  - `-f FORMAT` choices include `columns` (default), `json`, `cyclonedx-json`, `cyclonedx-xml`, `markdown`.
- **Decision:** AC14 invocation is `pip-audit -r requirements.txt --ignore-vuln=CVE-2025-69872 --ignore-vuln=GHSA-xqmj-j6mv-4862 --ignore-vuln=CVE-2026-3219 --ignore-vuln=CVE-2026-6587` (per Step-5 NEW-Q17 + verified syntax).

### `python -m build` and `twine`
- Standard PyPI tooling. No version-specific gotchas. Installed via the dedicated `pip install build twine pip-audit` step (per AC50).

### `[project.optional-dependencies]` PEP 621
- Stable PEP 621 syntax. `dev = ["pkg>=X"]` form is correct. No version-pin gotchas for cycle 34.

## Net amendment to design doc

Update AC9 wording: `actions/checkout@v4` → `@v6`, `actions/setup-python@v5` → `@v6`, ADD `cache: 'pip'` keyword to setup-python step.

Threat-model row 4 (T2 tag-pin verification) updated: `grep -E 'uses: actions/(checkout|setup-python)@v[0-9]+$' .github/workflows/ci.yml` will match `@v6` instead of `@v4`/`@v5`.

## Verdict

**OK with minor amendments (action version bumps).** Cycle 34 design proceeds to Step 7 with the @v6 version + cache: 'pip' addition.
