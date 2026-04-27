# Cycle 47 — Threat Model + Dep-CVE Baseline

**Date:** 2026-04-28
**Branch:** cycle-47-batch
**Skip-status:** Step 2 threat-model dispatch SKIPPED per skip-when ("pure
internal refactor, no I/O or trust boundary changes"). Cycle 47 only does:
(a) BACKLOG.md text refresh, (b) test-fold restructuring, (c) dep-CVE
re-verification with NO bumps, (d) optional CI workflow skipif marker.
None of these introduce new trust boundaries, data classifications, authn/
authz, or audit surfaces. Dep-CVE baseline IS captured to enable the Step
11 PR-CVE diff per cycle-22 L1.

## Threat surface assessment (one-pass)

| Surface | Cycle 47 change | Threat delta |
|---|---|---|
| Trust boundaries | None | None |
| Data classification | None | None |
| Authn/authz | None | None |
| Logging/audit | None | None |
| Filesystem writes | Only `BACKLOG.md`, `CHANGELOG*.md`, `docs/`, `tests/test_cycle*.py` deletions, `tests/test_<canonical>.py` additions, OPTIONAL `.github/workflows/ci.yml` skipif marker | LOW — all developer-controlled paths inside repo |
| External calls | None added; `pip-audit`, `gh api`, `pip download --no-deps` are read-only verification calls | None |
| Dependencies | NO new pins, NO bumps; verification only | None — Step 11 PR-CVE diff will confirm `INTRODUCED` empty |

If an unexpected production-code change surfaces during a fold (an AC9
triggers), file BACKLOG and SKIP — do NOT inline-fix at risk of expanding
scope past the threat-model skip-when justification.

## Dep-CVE baseline (captured 2026-04-28 for cycle-47-batch)

Captured to project-relative paths per cycle-22 L1 + cycle-40 L4:

- `.data/cycle-47/cve-baseline.json` (pip-audit live venv, 21 KB, 4 vulns)
- `.data/cycle-47/alerts-baseline.json` (Dependabot open alerts, 4 entries)

### Pip-audit summary

| Package | Version | Advisory | Fix Available | Cycle-46 → Cycle-47 |
|---|---|---|---|---|
| diskcache | 5.6.3 | CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v) | `[]` | UNCHANGED |
| litellm | 1.83.0 | GHSA-xqmj-j6mv-4862 | `['1.83.7']` BLOCKED | UNCHANGED |
| pip | 26.0.1 | CVE-2026-3219 | `[]` | UNCHANGED |
| ragas | 0.4.3 | CVE-2026-6587 (GHSA-95ww-475f-pr4f) | `[]` | UNCHANGED |

### Dependabot summary

| Package | GHSA | Severity | First Patched | Pip-audit drift |
|---|---|---|---|---|
| litellm | GHSA-v4p8-mg3p-g94g | high | 1.83.7 | DRIFT (pip-audit silent) — UNCHANGED |
| litellm | GHSA-r75f-5x8p-qvmc | critical | 1.83.7 | DRIFT (pip-audit silent) — UNCHANGED |
| litellm | GHSA-xqmj-j6mv-4862 | high | 1.83.7 | EMITTED — UNCHANGED |
| ragas | GHSA-95ww-475f-pr4f | low | null | EMITTED (CVE-2026-6587) — UNCHANGED |

### Live verification calls (2026-04-28 cycle-47)

```
pip index versions litellm  → LATEST=1.83.14 (was 1.83.14 cycle-46)
pip index versions pip      → LATEST=26.1     (was 26.1     cycle-46)
pip index versions diskcache → LATEST=5.6.3   (was 5.6.3   cycle-46)
pip index versions ragas    → LATEST=0.4.3    (was 0.4.3    cycle-46)
gh api advisories/GHSA-58qw-9mgm-455v → patched_versions=null, vulnerable_version_range=null
pip download --no-deps litellm==1.83.14 → wheel METADATA: Requires-Dist: click==8.1.8
```

**Outcomes:**
- AC1 (diskcache): no upstream patch — refresh timestamp ✓
- AC2 (ragas): no upstream patch — refresh timestamp ✓
- AC3 (litellm): 1.83.14 still pins click==8.1.8 — narrow-role exception persists; refresh timestamp ✓
- AC4 (pip): GHSA-58qw advisory still has `patched_versions:null` + `vulnerable_version_range:null` — cycle-22 L4 conservative posture: do NOT bump 26.0.1 → 26.1. Refresh timestamp ✓
- AC5 (litellm GHSA-r75f drift): pip-audit baseline does NOT emit this ID despite Dependabot listing it as open — drift persists. Refresh timestamp ✓
- AC6 (litellm GHSA-v4p8 drift): same shape as AC5 — drift persists. Refresh timestamp ✓

## Class A vs Class B reminders

- **Class A** (existing on `main`): all 4 pip-audit findings + 2 Dependabot
  drift entries. Step 11.5 opportunistic patch CANNOT proceed — every entry
  has either (a) empty `fix_versions`, (b) blocked transitive constraint
  (litellm/click), or (c) cycle-22 L4 conservative posture (pip 26.1
  unconfirmed by advisory). No bumps this cycle.
- **Class B** (PR-introduced): expected EMPTY at Step 11. Cycle 47 introduces
  no new pins or transitive bumps. If Step 11 surfaces a new CVE ID, it must
  be an across-cycle late arrival (cycle-22 L4); evaluate per the case.

## Late-arrival monitoring (Step 15 post-merge)

Standard `comm -13` diff between `alerts-baseline.json` (Step 2) and the
post-merge alerts pull. Any new IDs → informational only; file BACKLOG entry.
