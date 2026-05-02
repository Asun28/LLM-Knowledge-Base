# Cycle 56 — Freeze-and-fold continuation (5 folds, 219→214) + dep-CVE re-confirm

**Date:** 2026-05-02
**Owner:** dev-mimo-opus skill (project trial — May 2026 MiMo run)
**Branch:** worktree-cycle-56
**Parallel cycles in flight:** cycle-53 (worktree), cycle-54 (worktree). Cycle 55 already merged at `4e245de`.
**Picks marker:** this file + the implementation plan committed to `cycle-56-batch` and pushed to origin BEFORE Step 9 begins, so concurrently-launched cycle-57 can see what's claimed and avoid collisions.

---

## Step 1 — Requirements + Acceptance Criteria

### Problem

Phase 4.5 HIGH `tests/` coverage-visibility item open since 2026-04-13: ~50 of 94 original test files were named `test_v0NNN_*` / `test_phase4_audit_*` / `test_cycleN_*` and force grep-across-versioned-files to verify any module's coverage. The freeze-and-fold cadence (cycles 38–55) has cut this from ~190 candidates down to 219 files in the cycle-56 worktree (post-c55 merge), with cycles 53 and 54 in flight against another 8 files.

Cycle 56's role: pick **5 fold targets** (one extra over the c53/c54/c55 4-pick cadence per user direction "as many as backlog items before phase 5"), receivers chosen to avoid collision with the in-flight cycles' receivers, and re-confirm the 4 known dep-CVEs (diskcache / ragas / litellm / pip) per the cycle-22 L4 cross-cycle advisory-arrival cadence.

### Non-goals

- No `src/` changes. Pure test-fold + doc + dep-CVE re-confirm.
- No NEW production behaviour. C40-L3 revert-verify applies; behavioural upgrades to weak fold targets are deferred to dedicated cycles per cycle-52 L1 / cycle-53 L1.
- No new CI dimensions (cycle-36 L1 + cycle-39..55 carry-over: windows-latest matrix still deferred to a dedicated cycle).
- No re-evaluation of HIGH-Deferred / Phase-5-Community items.

### Acceptance criteria

| # | AC | Verification |
|---|----|--------------|
| AC1 | Fold `tests/test_v01012_mcp_validation.py` (7 tests, 2701 B) into `tests/test_mcp_core.py` as new class `TestMcpInputValidation`. | Source file deleted; receiver gains 7 tests grouped in one class; `pytest tests/test_mcp_core.py -x` green; revert-verify (`assert False` on one method) FAILs in isolation, then restored. |
| AC2 | Fold `tests/test_v0916_task09.py` (3 tests, 2011 B) into `tests/test_v070.py` preserving 3 host classes (`TestCompileExitCode`, `TestCliSourceTypeList`, `TestVersionBump`). | Source file deleted; receiver gains 3 classes; revert-verified. Host shape preserved per C40-L5. |
| AC3 | Fold `tests/test_v01013_cli_error_truncation.py` (7 tests, 3444 B) into TWO receivers: 5 CLI-truncation tests → `tests/test_cli.py` as class `TestCliErrorTruncation`; 2 `truncate(...)` helper tests → `tests/test_utils_text.py` as bare functions. | Source file deleted; both receivers updated; both pass `pytest -x` in isolation; revert-verified on at least one method per receiver. |
| AC4 | Fold `tests/test_v01001_utils_fixes.py` (5 tests, 2754 B) into `tests/test_utils.py` as new class `TestUtilsFixes`. Class hosts cross-helper tests per C50-L1 single-class precedent. Internal `_write_page` helper renamed to `_write_concept_page` per C52-L4 helper-name uniqueness rule. | Source file deleted; receiver gains 1 class with 5 methods; revert-verified. |
| AC5 | Fold `tests/test_phase4_audit_concurrency.py` (4 tests, 3099 B) into `tests/test_utils_io.py` as new class `TestFileLockConcurrency`. | Source file deleted; receiver gains 1 class with 4 methods; revert-verified. |
| AC6 | After all 5 folds: `tests/` versioned test count drops from 219 → 214 (-5); aggregate test count preserved at 3026. | `find tests -maxdepth 1 -name "*.py" \| wc -l` returns 214; `pytest --collect-only \| tail -1` returns 3026. |
| AC7 | Each fold is a separate commit on `worktree-cycle-56` with message `test(cycle 56): fold <source> into <receiver> (N/M)`. AC3 splits into two commits (one per receiver). | `git log --oneline origin/main..HEAD` shows ≥6 fold commits + design + plan + doc-sync commits in expected order. |
| AC8 | Picks marker (this design doc + plan doc) committed to `cycle-56-batch` and PUSHED to origin BEFORE any Step-9 fold commit, so any concurrently-launched cycle-57 can grep `cycle-56-batch` for our claimed source files / receivers and avoid collision. | `git ls-remote origin refs/heads/cycle-56-batch` returns the marker SHA before fold commit timestamps. |
| AC9 | Re-confirm dep-CVE baseline: capture `pip-audit --format=json` to `.data/cycle-56/cve-baseline.json` (gitignored); compare against cycle-55 baseline; document the 4 known unresolved CVEs (diskcache GHSA-w8v5-vhqr-4h9v, ragas GHSA-95ww-475f-pr4f, litellm GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g, pip CVE-2026-3219) in CHANGELOG-history.md cycle-56 entry. | `.data/cycle-56/cve-baseline.json` exists; advisory IDs match cycle-55 baseline (no new arrivals expected, but confirm); cycle-22 L4 late-arrival watch documented in Step-14 PR-CVE diff. |
| AC10 | Doc updates per cycle-23 L4 + cycle-26 L2 count-cross-check rule: CLAUDE.md Quick Reference test/file count = 3026 / 214; CHANGELOG.md `[Unreleased]` entry; CHANGELOG-history.md cycle-56 detail; BACKLOG.md HIGH cycle-44-progress note bumped 219→214 with cycle-56 fold roster; docs/reference/testing.md + implementation-status.md test-count narrative sites in lockstep (C26-L2 extended to docs/reference/*). | grep `3026 tests` and `214 files` across docs returns consistent results; no symmetrical-edit smell per cycle-35 routing rule. |
| AC11 | Step 20 PR review: R1 DeepSeek + Sonnet (parallel); R2 Codex + Sonnet (parallel). MiMo Coding subagents at Steps 7/8/14 + MiMo Chat at Step 17 per dev-mimo-opus skill routing — trial outcomes (Token-Plan burn, dispatch latency, identity-confusion) feed Step 24 self-review for the 2026-05-31 MiMo writeup. | All 4 R1/R2 reviewers' verdicts captured in PR review trail comment; per-vendor latency + verdict logged in Step 24. |

### Blast radius

- `tests/` only — 5 source files deleted; 6 receiver files mutated (test_mcp_core.py, test_v070.py, test_cli.py, test_utils_text.py, test_utils.py, test_utils_io.py).
- Zero `src/kb/` lines touched.
- Zero CI workflow changes.
- Documentation: CLAUDE.md Quick Reference, CHANGELOG.md, CHANGELOG-history.md, BACKLOG.md, docs/reference/testing.md, docs/reference/implementation-status.md.

---

## Step 2 — Threat Model + Dep-CVE Baseline

### Threat surface (minimal — fold-only)

| T# | Threat | Class | Mitigation |
|----|--------|-------|------------|
| T1 | Fold breaks a regression test silently (test runs but assertion no longer matches production) | Quality | Per-fold C40-L3 revert-verify (`assert False` on one moved method must FAIL in isolation, then restore). |
| T2 | Fold receiver shadow-imports a removed helper (`_write_page` rename in AC4) | Test-collection | Helper rename (`_write_page` → `_write_concept_page`) per C52-L4; full-suite collect-only after each fold. |
| T3 | Multi-receiver fold (AC3) introduces drift where same source-file's tests assert against different production paths | Quality | Each split commit includes its slice of tests verbatim; receiver pytest -x green per receiver before next AC starts. |
| T4 | Picks marker collision: cycle-57 launches before our `cycle-56-batch` push and picks the same source files | Collaboration | AC8 — push picks marker BEFORE Step 9. Convention: cycles read `git ls-remote origin refs/heads/cycle-NN-batch` for in-flight cycles before claiming files. |
| T5 | Dep-CVE re-confirm reveals NEW Class-B advisory introduced since cycle-55 baseline | Security | Step 14 PR-CVE diff per cycle-22 L4; if new advisory, classify as class A (existing on main) or class B (PR-introduced — REJECT and patch). Cycle 56 does not bump deps so any new advisory is class A by definition. |

### Dep-CVE baseline

Run pip-audit against the live `.venv` (NOT `-r requirements.txt` per C34-L1) and emit JSON to `.data/cycle-56/cve-baseline.json`. Baseline expectation per cycles 51..55: 4 advisories with empty `fix_versions` (diskcache 5.6.3, ragas 0.4.3, litellm 1.83.0 — 3 CVEs, pip 26.0.1 — 1 CVE). Step 14 PR-CVE diff = empty (no dep changes this cycle). Step 15 = re-confirm "no upstream patch" entries in BACKLOG / CHANGELOG.

### Acceptance criteria for Step 2

- `.data/cycle-56/cve-baseline.json` exists and is non-empty JSON.
- `.data/cycle-56/alerts-baseline.json` (Dependabot) captured if `gh api` is reachable; otherwise document the gap and rely on the pip-audit baseline alone.
- Threat-model file written to this design doc (above table is the artifact).

---

## Step 3 — Brainstorming

Two approaches:

1. **Single 4-pick batch (typical c53/c54/c55 cadence).** Lower risk, matches established protocol. User explicitly asked for "as many as backlog items" → goes against that direction.
2. **5-pick batch (selected).** Adds one extra fold beyond the standard cadence. Within cycle-13 L2 sizing heuristic (each fold is ~30-100 LOC; 5 folds is still primary-session-dispatchable per C37-L5). Receivers chosen to avoid every receiver in cycles 53/54 in-flight (test_compile.py, test_config.py, test_query.py, test_mcp_browse_health.py, test_models.py, test_lint.py).

**Decision: Approach 2.** User instruction is dispositive; receivers are non-overlapping with in-flight cycles.

---

## Step 4 — Design Eval

### R1 (Opus, primary session per C37-L5 — primary holds full context from Steps 1-3)

**Symbol-verification table (cycle-15 L1 mandatory):**

| Source file | Cited fixture / helper | grep evidence |
|-------------|------------------------|---------------|
| test_v01012_mcp_validation.py | `kb_query_feedback`, `kb_lint_consistency`, `kb_graph_viz`, `kb_list_pages`, `kb_save_lint_verdict`, `kb_query`, `kb_detect_drift` | All 7 grep-confirmed in src/kb/mcp/{quality,health,browse,core}.py at module scope |
| test_v0916_task09.py | `kb.cli.cli`, `compile_wiki`, `SOURCE_TYPE_DIRS`, `kb.__version__` | All grep-confirmed in src/kb/{cli.py, compile/compiler.py, config.py, __init__.py} |
| test_v01013_cli_error_truncation.py | `LLMError`, `truncate`, `kb.cli.cli`, `pipeline.ingest_source`, `compiler.compile_wiki`, `engine.query_wiki`, `runner.run_all_checks`, `analyzer.generate_evolution_report` | All grep-confirmed |
| test_v01001_utils_fixes.py | `atomic_json_write`, `extract_wikilinks`, `load_all_pages`, `slugify`, `append_wiki_log` | All grep-confirmed in src/kb/utils/{io,markdown,pages,text,wiki_log}.py |
| test_phase4_audit_concurrency.py | `file_lock`, `_feedback_lock`, `kb.lint.verdicts.add_verdict` | All grep-confirmed |

All cited symbols exist as written. No DROP-with-test-anchor needed (cycle-15 L2) — these are live regression tests for live production code.

**Receiver-shape verification:**

| Receiver | Existing class shape | Cycle-56 addition | Conflict risk |
|----------|---------------------|-------------------|---------------|
| test_mcp_core.py | Multi-class (`TestKbCaptureWrapper` cross-module precedent + others) | Add `TestMcpInputValidation` class | Low — c53 picks did not touch this file |
| test_v070.py | Multi-class + bare functions per C49-L1 + C51-L4 host-shape | Add 3 classes preserving source layout | Low — last cycle to touch was c51 |
| test_cli.py | Multi-class + bare functions | Add `TestCliErrorTruncation` class | Low — no in-flight cycle uses this |
| test_utils_text.py | Bare functions | Add 2 bare functions | Low |
| test_utils.py | Multi-class + section comments | Add `TestUtilsFixes` class with renamed `_write_concept_page` helper | Low — c52 used it (already merged) |
| test_utils_io.py | Multi-class | Add `TestFileLockConcurrency` class | Low |

**Pre-fold isolation pytest expectations** (C51-L1):
- After AC1: `pytest tests/test_mcp_core.py -x` should pass; cycle-56 adds 7 tests.
- After AC2: `pytest tests/test_v070.py -x` should pass; cycle-56 adds 3 tests.
- After AC3a: `pytest tests/test_cli.py -x` should pass; cycle-56 adds 5 tests.
- After AC3b: `pytest tests/test_utils_text.py -x` should pass; cycle-56 adds 2 tests.
- After AC4: `pytest tests/test_utils.py -x` should pass; cycle-56 adds 5 tests.
- After AC5: `pytest tests/test_utils_io.py -x` should pass; cycle-56 adds 4 tests.

### R2 (MiMo Chat / mimo-v2.5-pro — would normally fire here)

For a hygiene-only fold cycle with grep-verified symbols and no novel APIs, the dev-mimo-opus skill's Step 4 trivial-collapse rule applies: **R2 design eval is trivial-skipped** (one-liner equivalent — pure mechanical fold work, no edge cases beyond C40-L3 revert-verify which AC contracts already pin). Skipping R2 here matches cycle-13 L2 + cycle-21 L1 sizing heuristics. Trial-outcome note for Step 24: this skip burns ZERO Token-Plan credit.

---

## Step 5 — Design Decision Gate

Open questions resolved inline (cycle-21 L1 — no code-exploration gaps, all are doc/scope decisions):

| Q | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q1 | AC3 split: keep all 7 tests in test_cli.py, or split? | **Split** (5 → test_cli.py, 2 → test_utils_text.py) | The 2 `truncate()` tests are pure-utility (no CLI runner needed), test_utils_text.py is the canonical home (per C49-L1 + cycle-50 L1 host-shape). Splitting matches the production-module shape. |
| Q2 | AC2: 3 classes preserved or merged into one `TestPhase397Task09` class? | **Preserve 3 classes** | Each class has independent scope (CompileExitCode is CLI compile path, CliSourceTypeList is CLI param wiring, VersionBump is package metadata). Merging would create a synthetic grouping that doesn't reflect production-shape concerns (C40-L5 host-shape). |
| Q3 | AC4: name new class `TestUtilsFixes` or break into per-helper classes? | **Single class `TestUtilsFixes`** | Per cycle-50 L1 cross-module hosting precedent (TestMcpWikiDirValidation hosts mcp.{core,health}). The 5 tests share theme "Phase 4 utils fixes". |
| Q4 | AC4: helper rename — keep `_write_page` or rename? | **Rename to `_write_concept_page`** | C52-L4 helper-name uniqueness rule. test_utils.py already hosts a `_write_page` helper at section `# ── load_all_pages ─` (cycle-52 fold). Collision = silent monkey-patch. Rename closes the class. |
| Q5 | Picks-marker push: before Step 9 or after? | **Before Step 9** (AC8) | Cycle-55's protocol — cycle-55-batch was pushed AFTER picks marker commit so future parallel cycles see claimed files. Cycle 56 follows. |
| Q6 | 5 picks vs 4: doc the rationale for the user-direction extra fold? | **Yes** — annotate AC6 + Step-24 scorecard with user direction "as many as backlog items before phase 5" | Future cycles reading this design will know cycle 56 deliberately exceeded the 4-pick cadence. |
| Q7 | R3 PR review trigger? | **Skip R3 unless cycle-17 L4 fires** (≥25 ACs OR ≥15 ACs + new write-surface OR ≥10 design-gate questions) | Cycle 56 has 11 ACs, 7 design-gate questions, no new write-surface. R3 not auto-triggered. R1+R2 sufficient. |
| Q8 | Step 14 same-class peer scan focus? | **N/A this cycle** — no production fix lands; security verify is "no PR-introduced CVE diff" only | Cycle-16 L1 same-class peer scan is for security-class production fixes. Cycle 56 has no production-class anti-pattern fix. |

**FINAL DECIDED DESIGN:** Approach 2 (5 picks) with AC1–AC11 as listed. Design + plan + picks marker commit lands on `cycle-56-batch`, pushed to origin before Step 9 begins.

---

## CONDITIONS (Step 9 must satisfy — cycle-22 L5)

Per C22-L5 every CONDITION below is a test-coverage requirement:

1. **C40-L3 revert-verify** for at least one method in EACH of the 5 fold ACs (not just one for the cycle). Document the failed-then-restored sequence in commit messages.
2. **C51-L1 isolation pytest** after each fold: `pytest tests/<receiver>.py -x` green BEFORE moving to next AC.
3. **C26-L2 + cycle-35 routing extension** for doc count drift: grep CLAUDE.md AND docs/reference/testing.md AND docs/reference/implementation-status.md for `3026` and `214 files` post-doc-sync; ZERO mismatch.
4. **C52-L4 helper-name uniqueness** for AC4: confirm `_write_concept_page` is unique within receiver (test_utils.py).
5. **C40-L5 host-shape preservation** for AC2: TestCompileExitCode + TestCliSourceTypeList + TestVersionBump remain as 3 distinct classes inside test_v070.py.
6. **AC8 picks marker pushed before Step 9.** Verify via `git ls-remote origin refs/heads/cycle-56-batch` returning a SHA whose timestamp predates the first fold commit.
7. **AC11 PR review trail** — every R1/R2 reviewer dispatch + verdict + per-vendor latency captured in the PR comment per dev-mimo-opus Step 20 + MiMo trial telemetry requirements.
