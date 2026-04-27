# Cycle 46 — Threat Model + Dep-CVE Baseline

**Date:** 2026-04-28
**Cycle scope:** Phase 4.6 LOW closeout (lint shim deletion) + dep-CVE re-verify + BACKLOG hygiene
**Owner:** primary session (hygiene cycle, minimal trust-boundary changes)

## Trust boundaries

No new trust boundaries are introduced. Cycle 46 is a pure deletion + migration cycle:

- **Public API surface:** unchanged. `kb.lint.augment.{manifest,rate}.*` already exist as the canonical surface since cycle 44; the `_augment_*` shims being deleted were re-exports of those same symbols.
- **MCP tool surface:** unchanged (28 tools from cycle 45 remain).
- **CLI surface:** unchanged.
- **Filesystem reads/writes:** unchanged.
- **Network egress:** unchanged.
- **Subprocess invocations:** unchanged.

## Data classification

No data flows are added or removed. The deleted shim files contained no data — only re-export bindings.

## Authn/authz

No authentication or authorization paths are touched.

## Logging / audit

No logging changes.

## Threat-model items (T1–T5)

### T1 — PR-introduced CVE diff (Class B)

**Verdict at Step 2 (baseline):** Cycle 46 changes ZERO dependencies. Expected `INTRODUCED` set at Step 11 = empty.

Baseline snapshot saved:
- `.data/cycle-46/pip-audit-baseline.json` — 21 089 bytes, 4 known vulns enumerated (carry-overs)
- `.data/cycle-46/dependabot-baseline.json` — 4 open alerts (3 litellm + 1 ragas)

### T2 — Same-class peer scan on lint shim removal

**Verdict at Step 2:** N/A. Cycle 46 deletes shims rather than introducing new validation, sanitization, or path-containment logic. There is no anti-pattern class to peer-grep for.

Step-11 Codex security verify will confirm:
- No new function definitions whose name pattern matches `_for_legacy|bypass|unsafe_` (cycle-10 L1 hazard).
- No new `str.startswith` containment patterns (cycle-16 L1 hazard).
- No new regex emanating from user input (cycle-21 L4 hazard).

### T3 — Test contract preservation under shim path migration

**Verdict at Step 2:** Each of the 38 patch sites being migrated from `kb.lint._augment_manifest.X` → `kb.lint.augment.manifest.X` (and `_augment_rate` → `augment.rate`) MUST preserve test semantics. Risk: a test relying on the shim's fall-through-to-package mirroring (`_sync_legacy_shim`) might fail if the migration drops the `_sync_legacy_shim` function before the test is updated.

**Mitigation strategy:**
- Order of operations in Step 9: (1) migrate ALL 38 test patch sites FIRST, (2) drop `_sync_legacy_shim` calls in src/, (3) delete shim files LAST.
- After each test-patch AC commits, run that single test file via `pytest -x -q tests/test_<name>.py` to confirm green.
- After AC3+AC4+AC5 (drop sync_legacy_shim), run full suite to confirm no test still depends on the legacy shim path.
- Do NOT rely on the shims' `__setattr__` mirroring during the migration window — every test that currently uses `monkeypatch.setattr("kb.lint._augment_manifest.X", ...)` MUST be updated to point at `kb.lint.augment.manifest.X` BEFORE the shim file is deleted.

### T4 — Deferred-promise BACKLOG sync (cycle-23 L3)

**Verdict at Step 2:** Cycle 46 deletes 2 BACKLOG entries:

1. **Phase 4.6 LOW** (`lint/_augment_manifest.py` + `lint/_augment_rate.py` shim) — resolved in-cycle by AC6+AC7 deletion.
2. **Phase 4.6 MEDIUM** (`mcp/core.py` 1149 LOC split) — resolved by cycle 45 PR #65 (M3 split). Entry was stale documentation only; cycle 45 self-review at `docs/superpowers/decisions/2026-04-27-cycle-45-self-review.md` and CHANGELOG cycle-45 entry both confirm shipped state.

**Step-11 verification check:**
- For each deleted BACKLOG entry, `git log --grep "<entry topic>" --oneline | head -10` must show a corresponding ship commit.
- For Phase 4.6 LOW: this cycle's commits will be the ship commits.
- For Phase 4.6 MEDIUM: cycle-45 commits `40332fc` + `2ee0238` are the ship commits.

### T5 — Doc-text drift on test count (C26-L2 + C39-L3)

**Verdict at Step 2:** AC2 deletes 1 test from `tests/test_lint_augment_split.py` (`test_augment_compat_shims_resolve_to_new_package`). Expected delta: 3027 → 3026.

**Step-12 verification:**
- `python -m pytest --collect-only | tail -1` — authoritative count.
- `git ls-files tests/test_*.py | wc -l` — file count (expected 244 unchanged; no test files added/deleted this cycle).
- Multi-site grep for the count `3027` and `244` in: `CLAUDE.md`, `docs/reference/testing.md`, `docs/reference/implementation-status.md`, `README.md`. Update each to new count.
- After any R1/R2 PR-review fix commits add new tests, re-verify the collected count (cycle-15 L4).

## Dep-CVE baseline summary

### pip-audit (4 known vulns, all carry-overs since cycle 32 / 41)

| Package | Version | Advisory | Fix versions |
|---|---|---|---|
| diskcache | 5.6.3 | CVE-2025-69872 | `[]` (no upstream patch) |
| litellm | 1.83.0 | GHSA-xqmj-j6mv-4862 | `['1.83.7']` (BLOCKED — `click==8.1.8` transitive in 1.83.7..1.83.14) |
| pip | 26.0.1 | CVE-2026-3219 | `[]` (advisory `firstPatchedVersion: null`; pip 26.1 published but advisory not refreshed) |
| ragas | 0.4.3 | CVE-2026-6587 | `[]` (no upstream patch) |

**Confirmation greps:**
- `pip index versions diskcache` → 5.6.3 LATEST (no new release; matches cycle-41)
- `pip index versions ragas` → 0.4.3 LATEST (no new release; matches cycle-41)
- `pip index versions litellm` → 1.83.14 LATEST (matches cycle-41)
- `pip index versions pip` → 26.1 LATEST (matches cycle-40 — new release; advisory not yet refreshed)
- `gh api graphql ... GHSA-58qw-9mgm-455v` → `vulnerableVersionRange: <= 26.0.1`, `firstPatchedVersion: null` (matches cycle-41)
- litellm 1.83.14 wheel METADATA → `Requires-Dist: click==8.1.8` (still pinned; matches cycle-41 verification)

### Resolver conflicts (3, all carry-overs)

```
arxiv 2.4.1 has requirement requests~=2.32.0, but you have requests 2.33.0.
crawl4ai 0.8.6 has requirement lxml~=5.3, but you have lxml 6.1.0.
instructor 1.15.1 has requirement rich<15.0.0,>=13.7.0, but you have rich 15.0.0.
```

CI accepts via `continue-on-error: true` on the `pip check` step (cycle 34 AC52). State unchanged from cycle 41.

### Dependabot drift (2 carry-overs)

| ID | Severity | GHSA | Pip-audit emits? |
|---|---|---|---|
| 14 | critical | GHSA-r75f-5x8p-qvmc | No (drift) |
| 15 | high | GHSA-v4p8-mg3p-g94g | No (drift) |
| 13 | high | GHSA-xqmj-j6mv-4862 | Yes |
| 12 | low | GHSA-95ww-475f-pr4f | Yes |

CI workflow `--ignore-vuln` does NOT include the drifted IDs (intentionally — pip-audit can't see them, so CI doesn't fail on them). Monitor for pip-audit data refresh.

## Step 11.5 Class A opportunistic patch decision

**Verdict:** SKIP Step 11.5 patch this cycle. Conservative posture per cycle-22 L4:
- All 4 advisories have NO confirmed upstream patch.
- All 3 resolver conflicts persist with no upstream relaxation.
- pip 26.1 advisory is NOT yet refreshed to confirm 26.1 patches the CVE.

Track all 9 items for cycle-47+ with re-confirmation timestamps.

## Step 11 PR-introduced CVE diff prediction

**Predicted INTRODUCED set:** empty.

Cycle 46 modifies:
- `requirements.txt`: NO CHANGE
- `pyproject.toml [project.optional-dependencies]`: NO CHANGE
- 3 src files (drop dead `_sync_legacy_shim` functions): NO new imports
- 9 test files (replace import paths): NO new dependencies

Step 11 PR-introduced CVE diff `comm -23 branch.txt main.txt` should be empty. If non-empty (cross-cycle advisory arrival per cycle-22 L4), treat as Class A and patch in-cycle.
