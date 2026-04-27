# Cycle 43 — Threat model + dep-CVE baseline

**Date:** 2026-04-27
**Branch:** `cycle-43-test-folds`

## Step 2 skip rationale

Cycle 43 is a **pure test-only refactor** — relocates `test_cycleNN_*.py` files into canonical homes (`test_<module>.py`). No production code changes, no I/O surface change, no trust boundary modification. Per skill:

> Step 2 — skip when: pure internal refactor, no I/O or trust boundary changes

Threat-model items 1-5 captured in `2026-04-27-cycle-43-requirements.md` cover the test-infrastructure-specific risks (test ordering, vacuous-fold, doc count drift, cycle-42 collision, reload-leak).

## Dep-CVE baseline (captured 2026-04-27)

### Dependabot alerts (`gh api ... dependabot/alerts`)

```
4 open alerts: 3 high (litellm GHSA-v4p8 / GHSA-r75f / GHSA-xqmj), 1 critical (litellm GHSA-r75f), 1 low (ragas GHSA-95ww)
```

**File:** `.data/cycle-43/alerts-baseline.json`

| # | Severity | Package | Advisory | First-patched |
|---|----------|---------|----------|---------------|
| 15 | high | litellm | GHSA-v4p8-mg3p-g94g | 1.83.7 |
| 14 | critical | litellm | GHSA-r75f-5x8p-qvmc | 1.83.7 |
| 13 | high | litellm | GHSA-xqmj-j6mv-4862 | 1.83.7 |
| 12 | low | ragas | GHSA-95ww-475f-pr4f | (no upstream fix) |

### pip-audit (`.venv/Scripts/python.exe -m pip_audit --format json`)

```
Audited 319 deps, 4 vulnerable: diskcache CVE-2025-69872 (no fix), litellm GHSA-xqmj-j6mv-4862 (fix 1.83.7 — blocked by click<8.2 transitive), pip CVE-2026-3219 (no confirmed fix), ragas CVE-2026-6587 (no fix)
```

**File:** `.data/cycle-43/cve-baseline.json`

### State (identical to cycle 41/42 baseline)

All 4 advisories carried over; all have established narrow-role mitigations per BACKLOG.md Phase 4.5 MEDIUM:

- **litellm 1.83.0 → 1.83.7** — fix BLOCKED by `click==8.1.8` transitive constraint vs our `click==8.3.2` (cycle-32+). Dev-eval-only dep; zero `src/kb` imports. Cycle-43 re-confirmed `pip index versions litellm` shows 1.83.14 still pins click==8.1.8.
- **diskcache 5.6.3** — no upstream patch. Trafilatura robots.txt cache only; zero `src/kb` imports. Same posture.
- **pip 26.0.1** — pip-audit reports empty `fix_versions`; pip 26.1 published 2026-04-27 cycle-40 but advisory `patched_versions` still null. Per cycle-22 L4 conservative posture: do NOT bump until advisory confirms. Tooling-only, not runtime.
- **ragas 0.4.3** — no upstream patch. Dev-eval-only; zero `src/kb` imports.

### Step 11 expectation

Cycle-43 **adds zero dependencies and modifies zero requirements pins** (test-only refactor). Step-11 PR-CVE diff `INTRODUCED = comm -23 branch baseline` should be empty.

### Step 11.5 plan

No new patchable advisories since cycle 41 baseline 2026-04-27. Skip the existing-CVE patch step (no actionable bumps).
