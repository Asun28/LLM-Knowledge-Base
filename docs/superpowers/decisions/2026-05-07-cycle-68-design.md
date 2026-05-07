# Cycle 68 — Step 5 Design Decision

**Date:** 2026-05-08 (NZT)
**Pipeline step:** 5 (Design decision gate)
**Owner:** Opus 4.7 subagent (consolidation per `feedback_auto_approve`; no human gate)
**Inputs:**
- Requirements: `2026-05-07-cycle-68-requirements.md` (15 ACs)
- Brainstorm: `2026-05-07-cycle-68-brainstorm.md` (alternatives for AC07-AC10 + AC14-AC15)
- Threat model: `2026-05-07-cycle-68-threat-model.md` (7 STRIDE threats; T1/T2/T3 inherited from cycle-67 T3/T7/T12; T4-T7 NEW)
- R1 review: `2026-05-07-cycle-68-design-eval-R1-opus.md` (Opus 4.7, 0 BLOCKER + 4 MAJOR + 3 MINOR + 5 conditions)
- R2 review: `2026-05-07-cycle-68-design-eval-R2-deepseek.md` (DeepSeek V4 Pro, 3 BLOCKER + 5 MAJOR + 4 MINOR + 12 conditions)
- Cycle-67 design (inherited): `2026-05-07-cycle-67-design.md` (19 binding CONDITIONS — carry-overs)

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS.**

All 24 raw findings (R1: 4M+3m+5c; R2: 3B+5M+4m+12c) resolvable inline. After dedup with R1↔R2 overlap merging, **15 NEW cycle-68 CONDITIONS** bind on top of cycle-67's 19 inherited CONDITIONS (effective 34). Zero re-architecture, zero new ACs, zero Tier-3 escalation.

## Tier reaffirmation

**Tier 2 stays.** Cycle-68 NEW items (graph cache migration AC07/AC08, httpx pin AC09, BACKLOG cleanup AC10, regression tests AC14/AC15) do NOT introduce auth/IAM/crypto/secrets/PII/migration/signing-key/deploy-pipeline surfaces. Carry-overs (Popen, YAML safe_load) inherit cycle-67's design lock — no new trust boundaries to explore.

## Inline resolutions

### R1 findings (Opus)

| ID | Severity | Resolution | Sub-AC pin |
|----|----------|------------|------------|
| R1-F1 — Site count off-by-one (6 sites, not 5; 3 migratable) | MAJOR | **ACCEPT** — Step 7 must enumerate exactly: migrate `evolve/analyzer.py:127`, `graph/export.py:83`, `mcp/browse.py:345` (pages-None); leave `evolve/analyzer.py:28`, `evolve/analyzer.py:358`, `query/engine.py:408` (pages-supplying) on `build_graph`. | C-AC07-sites |
| R1-F2 — AST guard cannot blanket-forbid; needs pages-supplied predicate | MAJOR | **ACCEPT** — bind brainstorm formulation lines 144-155 (predicate: `kw.value.value is None` literal-check). Tolerates `build_graph(wd, pages=...)`; flags pages-None or missing `pages=`. | C-AC07-ast-guard-shape |
| R1-F3 — Cache invalidation responsibility verified read-only | MINOR | **ACCEPT** — all 4 migrated files are read-only consumers; no `invalidate(wiki_dir)` needed. Document in Step-5; mutator list (`ingest_source`, `refine_page`, `compile_wiki`) unchanged. | C-AC07-no-invalidate |
| R1-F4 — httpx pin verified safe (no transitive `<0.28` clamp) | MINOR | **ACCEPT** pin formulation `httpx>=0.28,<0.29`. Note brainstorm's `AssertionError` typo at line 64 — actual guard at `lint/fetcher.py:54` raises `RuntimeError`. | (verification only) |
| R1-F5 — BACKLOG cleanup completeness + cycle-68-self-reference defer | MAJOR | **ACCEPT** — defer 3 cycle-68 carry-over entries (BACKLOG lines 55-59) to Step 17 doc-update; verify `compile/compiler.py:645` validator-drift entry exists before listing for deletion. | C-AC10-current-cycle-deferred |
| R1-F6 — AST guard test name precision | MAJOR | **ACCEPT** — bind brainstorm name `test_no_direct_build_graph_pages_none_calls_in_migrated_files` (NOT requirements doc's over-broad name). | C-AC07-ast-guard-shape (merged) |
| R1-F7 — AC15 parsed-structure rigor | MINOR | **ACCEPT** — `tomllib` for pyproject.toml; markdown structure-aware iteration scoped to `### HIGH/MEDIUM/LOW` bullets, skipping HTML comments. | C-AC15-parsed-structure |

### R2 findings (DeepSeek)

| ID | Severity | Resolution | Sub-AC pin |
|----|----------|------------|------------|
| R2-F1 — AC08 unexamined; rolled into AC14 without per-file breakdown | BLOCKER | **MERGE with R1-F1/F2** — AC14 enumerates the 4 migrated files AND uses the pages-supplied predicate. Step 7 splits AC07/AC08 work by file. | C-AC07-sites + C-AC07-ast-guard-shape |
| R2-F2 — AC09 transitive httpx constraint may become unreachable | BLOCKER | **ACCEPT** — promote dry-run install verification to AC15. Step 11 also runs `pip-audit --format=json` post-impl. | C-AC09-resolver-compat |
| R2-F3 — AC14 cache-hit spy needs negative-control + cache-store mock | BLOCKER | **ACCEPT (partial)** — bind divergent-fail negative control (revert get_graph body, prove RED). REJECT internal `_GLOBAL_CACHE` mock — implementation detail; behavioural spy is sufficient per cycle-23 L2 / `feedback_test_behavior_over_signature`. | C-AC14-negative-control |
| R2-F4 — AC15 substring match vs exact tomllib parse | MAJOR | **ACCEPT** — merge with R1-F7. Use tomllib parse, assert constraint string contains `>=0.28` AND `<0.29` AND no other ceiling (e.g., not `<0.30`). | C-AC15-parsed-structure (merged) |
| R2-F5 — AC10 BACKLOG test doesn't verify source side fixed | MAJOR | **ACCEPT** — AC15 verifies a sample of actual source-side fixes (e.g., GitPython ceiling in requirements.txt, `KB_PROJECT_ROOT` accessor exists in config.py). | C-AC15-source-verify |
| R2-F6 — AC09 `lint/fetcher.py` error message outdated | MAJOR | **MODIFY** — small clarification update to error message. Add to AC09 task scope; not a separate AC. | C-AC09-error-message |
| R2-F7 — AC14 doesn't enforce attribute-lookup form | MAJOR | **ACCEPT** — AC14 AST guard asserts NEW `get_graph` call sites use attribute-lookup chain (`kb.graph.cache.get_graph(...)`), aligning with cycle-18 L1. | C-AC14-attr-form |
| R2-F8 — `generate_evolution_report` double-builds | MAJOR | **ACCEPT design** — intentional per cycle-64 cache-bypass contract. Add inline comment in `evolve/analyzer.py` documenting double-build overhead. | C-AC07-double-build-doc |
| R2-F9 — AC15/AC10 commit atomicity hazard | MAJOR | **ACCEPT** — Step 7 task ordering: commit AC15 test FIRST (with absence-list), THEN AC10 BACKLOG delete. AC10 revert alone leaves AC15 test failing RED. | C-AC15-commit-order (FW-10) |
| R2-F10 — AC14 pages-supplied calls don't pollute pages=None cache | MINOR | **ACCEPT** — add `test_pages_supplied_bypasses_cache_isolation` pin. | C-AC14-pages-supplied-isolation |
| R2-F11 — AC09 missing happy-path httpx version test | MINOR | **ACCEPT** — add `test_httpx_version_check_succeeds_on_0_28_x`. | C-AC09-happy-path |
| R2-F12 — AC14 AST walk misses aliased ImportFrom | MINOR | **MODIFY** — cycle-67 AC02 AST walker already covers `from kb.graph.cache import get_graph` (with alias). REJECT scope expansion in cycle-68 AC14. ACCEPT positive smoke: AC14 verifies new imports added by AC07/AC08 are attribute-form (not from-import) — covered by C-AC14-attr-form. | (merged into C-AC14-attr-form) |

## CONDITIONS list (final, locked — 15 NEW cycle-68; 19 INHERITED from cycle-67 = 34 effective)

| # | ID | AC | Source | Test pin |
|---|-----|-----|--------|----------|
| 1 | C-AC07-sites | AC07/AC08 | R1-F1, R2-F1 | Step-7 enumerates: migrate `analyzer.py:127`, `export.py:83`, `browse.py:345` (pages-None); leave `analyzer.py:28`, `analyzer.py:358`, `engine.py:408` on `build_graph` (pages-supplying). |
| 2 | C-AC07-ast-guard-shape | AC14 | R1-F2, R1-F6, R2-F1 | `test_no_direct_build_graph_pages_none_calls_in_migrated_files` — uses pages-supplied predicate (`kw.value.value is None` literal-check); brainstorm formulation lines 144-155. |
| 3 | C-AC07-no-invalidate | AC07/AC08 | R1-F3 | All 4 migrated files verified read-only; no `invalidate()` call needed. Step-5 documents. |
| 4 | C-AC07-double-build-doc | AC07 | R2-F8 | Inline comment in `evolve/analyzer.py` documenting intentional double-build overhead per cycle-64 cache-bypass contract. |
| 5 | C-AC09-resolver-compat | AC09/AC15 | R2-F2 | `test_pyproject_httpx_compatible_install` — runs `pip install --dry-run` (or equivalent resolver-only check) and asserts no conflict with transitive deps. |
| 6 | C-AC09-error-message | AC09 | R2-F6 | `lint/fetcher.py:54` `RuntimeError` message updated to indicate version-mismatch context (not "pin in requirements.txt" since both files now pin). Test pin in AC15. |
| 7 | C-AC09-happy-path | AC09 | R2-F11 | `test_httpx_version_check_succeeds_on_0_28_x` — monkeypatch `httpx.__version__` = "0.28.1"; assert no `RuntimeError` raised. |
| 8 | C-AC10-current-cycle-deferred | AC10 | R1-F5 | 3 cycle-68 carry-over entries (BACKLOG lines 55-59) deferred to Step 17 doc-update. Verify `compile/compiler.py:645` entry exists in BACKLOG before listing for AC10 deletion. |
| 9 | C-AC14-negative-control | AC14 | R2-F3 | `test_get_graph_cache_hit_on_repeat_call` — behavioural spy on `kb.graph.builder.build_graph` with `call_count==1` after two `get_graph(wiki)` calls. Step-14 verifier reverts `get_graph` body to direct `build_graph` and confirms test fails RED (divergent-fail per cycle-23 L2). |
| 10 | C-AC14-attr-form | AC14 | R2-F7, R2-F12 | AST guard asserts NEW `get_graph` call sites in 4 migrated files use attribute-lookup chain (e.g., `kb.graph.cache.get_graph(...)` — Attribute > Attribute > Attribute > Name). NOT plain `get_graph(...)`. |
| 11 | C-AC14-pages-supplied-isolation | AC14 | R2-F10 | `test_pages_supplied_bypasses_cache_isolation` — call `get_graph(wiki, pages=list_a)`, then `get_graph(wiki, pages=None)`; assert call_count==2; repeat pages=None call; assert call_count==2 (cache hit). |
| 12 | C-AC15-parsed-structure | AC15 | R1-F7, R2-F4 | Both AC15 tests use parsed structure: `tomllib.loads` for pyproject.toml; markdown structure-aware iteration scoped to `### HIGH/MEDIUM/LOW` bullets only (skip HTML comments / audit-receipt blocks). Constraint string asserts both `>=0.28` AND `<0.29` AND no `<0.30`/`<1.0` weaker ceiling. |
| 13 | C-AC15-source-verify | AC15 | R2-F5 | AC15 includes a sample of source-side fix verifications (e.g., parse `requirements.txt` for GitPython ceiling; AST-parse `config.py` for `get_project_root` accessor; AST-parse `kb/graph/cache.py` for `_GLOBAL_CACHE` symbol). 3-5 sample entries, not exhaustive. |
| 14 | C-AC15-commit-order | AC15/AC10 | R2-F9 | Step 7 task ordering: COMMIT AC15 test (BACKLOG absence-list) BEFORE AC10 BACKLOG delete commit. AC10 revert alone leaves AC15 RED. |
| 15 | C-tier-2-affirm | (cycle) | task brief | Tier 2 reaffirmed: NEW items add no auth/IAM/crypto/secrets/PII/migration surfaces; carry-overs design-locked from cycle 67. |

## Inherited carry-over CONDITIONS (cycle-67 → cycle-68 mapping)

Per cycle-68 requirements doc § "Carry-over inheritance":

| Cycle-67 condition | Cycle-68 ACs receiving | Test pin (cycle-68 file) |
|--------------------|------------------------|--------------------------|
| C-AC03-stdin (R1-C1, R2-F6) | AC01 + AC11 | `test_cli_backend_popen_large_stdin_plus_large_stdout` |
| C-AC03-platform (R1-C2, R2-F7) | AC01 + AC11 | `test_cli_backend_popen_platform_kill_branch` |
| C-AC03-stderr (R1-C6) | AC02 + AC11 | `test_cli_backend_popen_stderr_capped` |
| C-AC03-error-kinds (R2-F9) | AC01 + AC11 | `test_cli_backend_popen_preserves_error_kinds` |
| FW-1 (cycle-67) | AC01 | (split stdin from daemon readers) |
| C-AC07-safe (R2-F11) | AC03 + AC04 + AC12 | `test_lint_yaml_rejects_malicious_payload` |
| C-AC07-fallback (R2-F12) | AC03 + AC04 + AC12 | `test_lint_yaml_{file_missing,parse_error,io_error}_falls_through` |
| C-AC07-schema (R2-F13) | AC03 + AC12 | `test_lint_yaml_schema_mixed_type_warning` |
| FW-2 (cycle-67) | AC03 | (yaml.safe_load ONLY) |
| C-AC12-generator (R2-F16) | AC05 + AC13 | `test_audit_docstrings_generator_with_raise_requires_raises_section` |
| FW-4 (cycle-67) | AC05 | (generators with `raise` need `Raises:`) |
| R1-F4 (cycle-67) | AC05 + AC06 | warn-only transition path; BACKLOG entry if N>0 offenders |

Cycle-67 conditions C-AC01-* (MODEL_TIERS), C-AC02-alias (graph-cache import-form), C-AC04-truthy (KB_STRICT_PUBLISH), C-AC05-mcp (sqlite-vec sanitization), C-AC09-dual (snapshots), C-AC11-allowlist (sk-ant-dummy doc allowlist), C-AC14-multilink (docs/reference INDEX) are CLOSED in cycle 67 and DO NOT carry over (already shipped at cycle-67 HEAD `b64ed82`).

## Step 7 plan-dispatch instructions (forward-looking risks)

Mimo audit unlikely to catch without explicit guidance per `project_cycle61_mimo_failure`. Step 7 plan dispatch prompt MUST quote each FW item verbatim:

**FW-1 (INHERITED): AC01 Popen reference implementation.** MUST split stdin write from stdout/stderr reads — do NOT use `proc.communicate(input=...)` with daemon readers (cycle-67 R1-F1).

**FW-2 (INHERITED): AC03 YAML safe_load specificity.** MUST use `yaml.safe_load` ONLY; never `yaml.load` (cycle-67 R2-F11).

**FW-3 (N/A — cycle-67-only):** AC11 dummy-key grep — closed in cycle 67. Does NOT apply to cycle 68.

**FW-4 (INHERITED): AC05 generator + yield + raise.** Generators with `raise` in body need `Raises:` (cycle-67 R2-F16).

**FW-5 (N/A — cycle-67-only):** AC01 (cycle-67) Mapping ABC — closed in cycle 67. Does NOT apply to cycle 68.

**FW-6 (INHERITED, REVISED): Step-7 task ordering.** Cycle-68 ordering per requirements doc line 114 + R2-F9 amendment: AC15 (BACKLOG absence-list test) → AC10 (BACKLOG delete) → AC09 (httpx pin) → AC07 → AC08 → AC02 (config constant) → AC11 → AC01 (Popen) → AC03 → AC04 → AC12 → AC05 → AC06 → AC13 → AC14 (graph cache AST guard). Workflow + dep changes BEFORE security-class src per cycle-67 R1-C10.

**FW-7 (NEW): AC14 AST guard pages-supplied predicate.** AST guard MUST use `kw.value.value is None` literal-check predicate, NOT blanket-forbid `build_graph`. Brainstorm formulation lines 144-155. The 3 pages-supplying call sites (`analyzer.py:28`, `analyzer.py:358`, `engine.py:408`) must pass the guard; only pages-None or missing-`pages=` calls fail (R1-F2, R2-F1).

**FW-8 (NEW): AC09 resolver compatibility check.** AC15 MUST add `pip install --dry-run`-style resolver test verifying `httpx>=0.28,<0.29` is installable with all current direct + transitive deps. Step 11 also runs `pip-audit --format=json` post-impl (R2-F2).

**FW-9 (NEW): AC10 cycle-68-self-reference deferred.** AC10 cleanup deletes the 17 verifiable shipped entries (the 18 listed minus the 3 cycle-68 carry-over entries — net 15 enumerated + 2 conditional, accounting for `compile/compiler.py:645` requiring pre-flight verification). The 3 cycle-68 carry-over entries (BACKLOG lines 55-59) are deleted at Step 17 doc-update by the doc subagent AFTER carry-over ACs ship (R1-F5).

**FW-10 (NEW): AC15/AC10 commit atomicity.** Step 7 MUST commit AC15 test (BACKLOG absence-list) FIRST in a separate commit, THEN AC10 BACKLOG delete in a second commit. This way an AC10 revert alone leaves AC15 RED — closes the false-negative class where same-commit revert reverts the test too (R2-F9).

## R3-trigger reaffirmation

Cycle-17 L4 risk-profile triggers (any one fires R3 below 25-AC line):

- **(a)** NEW filesystem-write surface: NO — `wiki/_lint.yml` is read-only.
- **(b)** Defensive check whose input is hard to reach: YES — AC01 platform-kill branch on Windows is hard to exercise in CI (R2-F8 cycle-67 documented scope).
- **(c)** NEW security enforcement point: YES — AC03 `yaml.safe_load` boundary (carry-over but new in this cycle's CI surface), AC05 docstring audit gate (warn-only but new gate), AC14 AST guard for graph-cache caller migration (NEW).
- **(d)** Step-5 design gate resolved ≥10 open questions: YES — 24 raw findings (R1: 12; R2: 12) consolidated to 15 NEW conditions.

**Step 20 R3 REQUIRED** (Sonnet edge-case role per cycle-17 L4). Document trigger in PR body at Step 18.

## Step 14 verifier checklist

Inherited from threat-model.md `## Step 14 verifier checklist` (lines 170-194). Step 14 subagent (mimocoding-rescue per audit-role works) reads BOTH the threat model checklist AND the 15 NEW + 19 INHERITED CONDITIONS above. Cross-AC verifications:

- Full pytest green (3248+ baseline + ~75 new ≈ 3320+ post-cycle).
- Coverage delta: touched-file ≥90%, repo-total regression ≤0.5pp.
- Commit ordering per FW-6 + FW-10 (workflow/dep BEFORE security-class src; AC15 BEFORE AC10).
- `pip-audit --format=json` against final HEAD: ≤baseline + 0 NEW advisories.
- `git ls-files BACKLOG.md` line-count strictly DECREASED vs `origin/main` HEAD (positive-shape delta per T7 mitigation).
- `pip install --dry-run` resolver compatibility check (FW-8).

Step 14 must NOT verify cycle-67 OOS-1 through OOS-16 (closed by cycles ≤67).

## Step 6 (Context7) — SKIP

All 15 ACs use stdlib (subprocess, ast, sqlite3, urllib.parse, importlib, re, pathlib, json, os, sys, tomllib, threading, selectors, collections.abc) plus already-installed PyYAML. AC09 only TIGHTENS an existing dep constraint (httpx); does not add a new package. No new library APIs to research. Step 4 R1 absorbed pre-check (verified pyproject.toml + requirements.txt + lint/fetcher.py compatibility). Cycle-67 precedent confirms SKIP appropriate.

## Step-5 verdict summary

- **15 ACs** locked (9 cycle-67 carry-overs + 6 NEW)
- **15 NEW CONDITIONS** + **19 INHERITED** = **34 effective conditions**
- **0 BLOCKER** unresolved (R2's 3 BLOCKERs all merged + accepted)
- **0 architecture changes**, no new trust boundaries
- **10 forward-looking risks** for Step 7 dispatch (FW-1, FW-2, FW-4, FW-6 inherited; FW-3, FW-5 N/A; FW-7, FW-8, FW-9, FW-10 NEW)
- **R3 review REQUIRED** at Step 20 (cycle-17 L4 triggers (b)+(c)+(d) all fire)
- **Tier 2 reaffirmed** (no new auth/IAM/crypto/secrets/PII/migration surfaces)

Step 7 implementation plan (mimocoding-rescue @ mimo-v2.5-pro per cycle-67 telemetry) can lock against this consolidated spec. Mimo Coding subagent dispatch prompt at Step 7 MUST include FW-1, FW-2, FW-4, FW-6, FW-7, FW-8, FW-9, FW-10 verbatim per `project_cycle61_mimo_failure` (treat mimo Step 7/9 as failed-by-default; security-class src AC01/AC03 routes to primary Opus).
