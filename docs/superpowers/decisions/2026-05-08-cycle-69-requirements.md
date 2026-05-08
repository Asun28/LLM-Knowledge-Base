# Cycle 69 — Requirements + Acceptance Criteria

**Date:** 2026-05-08
**Tier:** 2 (standard feature — multi-AC fold; full pipeline 1–24; no mandatory human gates; auto-merge after Step 21)
**Branch:** `feat/cycle-69` (from `origin/main` at `ad17c03`)
**Worktree:** `D:/Projects/llm-wiki-flywheel/.claude/worktrees/feat+cycle-67`

## Tier classification

Per dev-mimo-opus **Tier classifier** (run BEFORE Step 1):

- **Tier 2 — standard feature.** Multi-AC fold (21 ACs); pure tests / docs / BACKLOG hygiene with **zero `src/kb/` changes**. Auto-merge per user directive (`feedback_auto_approve`). Not Tier 3 because no `src/kb/security/`, `auth*`, `crypto*`, env-var handling, file-path validation, or deployment artifact CHANGES — the path-validation BACKLOG entry is a *deletion* of a stale entry against already-shipped code (line 291 already segment-aware), and the corresponding lock-in test only *pins existing behaviour*.
- Strict-audit denominator: tier-aware (C59-L4) — full pipeline 1–24 binding-owner steps.

## Cycle theme

**Backlog hygiene + test-quality + folds + snapshots.**

A 21-AC backlog-cleanup cycle with three orthogonal threads:

1. **BACKLOG hygiene (4 ACs):** delete cycle-68 self-reference markers (Step-17 carry-over); delete two BACKLOG entries verified-stale against current source.
2. **C11-L1 inspect.getsource batch upgrade (6 ACs):** convert 6 vacuous source-string-read assertions in 4 versioned test files to behavioural assertions per cycle-11 L1.
3. **Snapshot subjects (3 ACs) + folds (4 ACs) + lock-in tests (2 ACs) + docs (2 ACs).**

## Verified-stale BACKLOG entries (deletion targets)

Each entry below was grep-verified against `src/` HEAD before drafting this requirements doc.

| BACKLOG section | Entry | Verified-stale evidence |
|---|---|---|
| Phase 6 — Cross-LLM cycle-64 audit / LOW | `mcp/app.py:254 _validate_page_id` `..` substring match | `mcp/app.py:291` already uses `any(seg == ".." for seg in page_id.replace("\\", "/").split("/"))` (segment-aware) |
| Phase 4.5 — multi-agent post-v0.10.0 audit / HIGH | `graph/builder.py` non-lint `build_graph` callers (5 remaining) | Cycle-68 AC07/AC08a/AC08b migrated 3 of 5; the remaining 2 (`query/engine.py:408`, `evolve/analyzer.py:29,360`) all supply `pages=` and per FW-7 (Cache Bypass) intentionally bypass the cache. No remaining migration candidates. |
| BACKLOG cycle-68 carry-over section (CYCLE 68 carry-over heading + AC03/AC07/AC12 self-ref markers) | self-reference lock-in (cycle-68 AC15b) | Per the test's own docstring: *"Step 17 doc-update deletes AC03/AC07/AC12 markers post-merge"* — deferred from cycle 68 to cycle 69 |

## Acceptance Criteria

### Group A — BACKLOG cleanup + cycle-68 lock-in retirement (4 ACs)

- **AC01.** Revise `tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_preserves_cycle68_self_reference_entries` to assert ABSENCE of cycle-68 self-ref entries (lock-in inversion). The first test (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) is preserved unchanged.
- **AC02.** Delete BACKLOG.md cycle-68 carry-over section + AC03/AC07/AC12 markers (the entire `### CYCLE 68 carry-over` block).
- **AC03.** Delete stale Phase 6 LOW `mcp/app.py:254 _validate_page_id` `..` substring entry (verified-shipped at line 291 — segment-aware).
- **AC04.** Delete stale Phase 4.5 HIGH `graph/builder.py` non-lint callers entry (verified shipped via cycle-68 AC07/AC08a/AC08b; remaining 2 sites are intentional FW-7 pages-supplying bypasses).

### Group B — Lock-in regression tests (2 ACs)

- **AC05.** New `tests/test_cycle69_app_segment_aware_lockin.py` — **behavioural** lock-in (NOT inspect.getsource): import `_validate_page_id` from `kb.mcp.app`; assert that `_validate_page_id("notes..draft", check_exists=False)` returns `None` (legitimate-with-double-dot case) AND that `_validate_page_id("foo/../bar", check_exists=False)` returns an error string containing `parent-directory segment`. Per C11-L1: a mutant that reverts to substring `".." in page_id` would BLOCK the legitimate case → test fails.
- **AC06.** New `tests/test_cycle69_graph_builder_intentional_bypasses.py` — AST guard: parse `query/engine.py` + `evolve/analyzer.py`, walk all `Call(func=Name("build_graph"))` AND `Call(func=Attribute(...,attr="get_graph"))` nodes, assert each call site under those modules either supplies `pages=` (bare `build_graph` allowed per FW-7) or is the lint-pass entry (already migrated). Lock-in for the AC04 deletion.

### Group C — C11-L1 inspect.getsource batch upgrade (6 ACs)

For each site below, replace the `inspect.getsource(...) + "X" in src` pattern with a behavioural assertion that exercises the production call site (per cycle-11 L1). Use late-bind via the production module attribute when needed (cycle-20 L1).

- **AC07.** `tests/test_lint_query_fixes_v092.py:279` — currently inspects `kb_lint` source for a string. Upgrade: monkeypatch the underlying call (e.g., `kb.lint.runner.run_all_checks`) and invoke `kb_lint(...)` to verify the wired behaviour.
- **AC08.** `tests/test_lint_query_fixes_v092.py:286` — same pattern for `kb_evolve`. Upgrade: invoke via the MCP entry point with monkeypatched `kb.evolve.analyzer.analyze_evolution`.
- **AC09.** `tests/test_v0911_phase392.py:245` — currently inspects `trends_module` source. Upgrade: import the relevant function (e.g., `compute_verdict_trends`) and assert behavioural output for a known-input fixture.
- **AC10.** `tests/test_v0915_task01.py:320` — currently asserts `"WIKI_SUBDIRS" in inspect.getsource(builder)`. Upgrade: import `builder` directly and assert `WIKI_SUBDIRS` is referenced in the actual call path (e.g., spy on `iterdir` or assert that `build_graph` skips files outside `WIKI_SUBDIRS`).
- **AC11.** `tests/test_v0915_task01.py:331` — analyzer inspect.getsource. Upgrade: invoke `analyze_evolution` with a controlled input and assert behavioural output.
- **AC12.** `tests/test_v0915_task08.py:363` — analyzer inspect.getsource. Upgrade per AC11.

### Group D — Snapshot subjects (cycle-64 deferred follow-up, 3 ACs)

Continues the cycle-64 snapshot foundation. Each new snapshot test in **`tests/test_cycle69_snapshots.py`** (T15/T16 mitigations preserved — controlled inputs only; default invocations FAIL on drift). Each snapshot includes a paired non-vacuous negative-control per cycle-67 AC09.

- **AC13.** `test_build_extraction_prompt_snapshot` — pins `kb.ingest.extractors.build_extraction_prompt(content, template, purpose)` for a fixed (content, template) pair so prompt-template drift is caught.
- **AC14.** `test_contradictions_append_snapshot` — pins the format produced by the contradictions append code path (in `ingest/pipeline.py`) for a fixed pair of contradictory extractions.
- **AC15.** `test_lint_semantic_render_sources_snapshot` — pins `kb.lint.semantic._render_sources(sources, lines)` for a fixed `sources` list so the `## Sources` block format is stable.

### Group E — Freeze-and-fold (4 small versioned tests, 4 ACs)

Each fold deletes the source file and folds tests into a canonical receiver. Per Step-5 host-shape rule (C40-L5): the receiver shape (bare-function vs class) is preserved. Each fold revert-checked per C40-L3 (`assert False` insertion → pytest -x FAIL → restored).

- **AC16.** Fold `tests/test_v0917_rewriter.py` (4 tests, 30 lines) → `tests/test_query.py` as bare functions (test_query.py has both class and bare-function shape; pick bare for 4-test set).
- **AC17.** Fold `tests/test_v0917_raw_fallback.py` (3 tests, 32 lines) → `tests/test_query.py` as a `TestSearchRawSources` class (3 tests around one function; class-based hosting matches receiver convention).
- **AC18.** Fold `tests/test_v01002_consolidated_constants.py` (~44 lines) → `tests/test_config.py` (cycle-47 AC1 created `test_config.py` with `TestConfigConstants` class; fold extends that class).
- **AC19.** Fold `tests/test_v0917_hybrid.py` (47 lines) → `tests/test_query.py` as a `TestHybridQuery` class.

### Group F — Documentation (2 ACs)

- **AC20.** CHANGELOG.md / CHANGELOG-history.md / BACKLOG.md / CLAUDE.md sync per CLAUDE.md doc-checklist. Per `feedback_deepseek_doc_disambiguation` memory: pre-emptively disambiguate in-project modules vs PyPI libraries when DeepSeek dispatches the doc-update.
- **AC21.** docs/superpowers/decisions/2026-05-08-cycle-69-* artifacts: requirements (this file) + threat-model + brainstorm + design-eval-R1-opus + design-eval-R2-deepseek + design + plan + plan-gate + step24-self-review.

## Out of scope (deferred to cycle-70+)

Per Step-5 design gate convention — name same-class peers explicitly:

- **OOS-1:** `tests/test_compile.py:211,221` `inspect.getsource(compiler)` — the docstring at line 211 explicitly states *"uses inspect.getsource because the test's purpose is to LINT the shipped pattern"* — **intentional, NOT a C11-L1 candidate**.
- **OOS-2:** `tests/test_cycle65_mcp_error_boundary.py:107` and `tests/test_cycle67_sqlite_vec_error_sanitization.py:121` `inspect.getsource` — these are recent cycle-65/67 anchors with current behavioural coverage elsewhere; cycle-69 does not re-litigate cycle-65/67 design decisions (deferred to a dedicated cycle if/when needed).
- **OOS-3:** `compile/compiler.py` naming inversion (Phase 4.5 HIGH) — architecture refactor, not a hygiene cycle item.
- **OOS-4:** `ingest/pipeline.py` state-store fan-out + per-source rollback — new module + receipt-file design; out-of-scope for hygiene cycle.
- **OOS-5:** All 25 sync `def` MCP tools async refactor (Phase 4.5 HIGH) — concurrency model change; high-risk; deferred indefinitely.
- **OOS-6:** `compile_wiki` two-phase pipeline (Phase 4.5 MEDIUM) — design churn.
- **OOS-7:** `IndexWriter` consolidation (Phase 4.5 MEDIUM) — defer until 4th caller (architectural threshold not yet met).
- **OOS-8:** `KB_DISABLE_VECTORS=1` runtime kill-switch (Phase 4.5 MEDIUM) — already SHIPPED cycle 67 AC06 (BACKLOG entry verified-stale; deletion deferred to a dedicated mass-cleanup cycle).
- **OOS-9:** `KB_STRICT_PUBLISH=1` (Phase 4.5 MEDIUM) — already SHIPPED cycle 67 AC04 (similar deferral).
- **OOS-10:** Phase 5 community proposals (Karpathy followup) — feature work, not hygiene.
- **OOS-11:** Phase 6/7/8 candidates — strategic items.
- **OOS-12:** Snapshot subjects beyond AC13–AC15 (`_build_summary_content` page-rendering, `kb publish --format graph` JSON-LD, `auto_publish_after_compile`'s `_publish/llms-full.txt` body) — deferred to cycle-70+ (3 subjects this cycle is the established cycle-64 cadence).
- **OOS-13:** windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX off-by-one — N/A prerequisites unavailable; bumped cycle-69+ → cycle-70+ tag.

## Counts target

- **ACs:** 21 (matches `feedback_3_round_pr_review` 25-AC R3-trigger threshold; per cycle-16 L4 R3 also fires when ≥15 ACs AND new lock-in test surface — this cycle ships 2 new lock-in tests + 1 new snapshot file, so **R3 will run**).
- **Files modified:** ~18 (within `feedback_batch_by_file` 15-20 target).
- **Tests:** 3274 → ~3290 (+~16 net: +6 lock-in, +3 snapshots, +6 negative controls, +4 fold-receivers add tests; -4 fold-source files net 0 tests; +ruff/format).
- **src/kb/ changes:** 0 (pure hygiene cycle — Step 06 + Step 10 + Step 11 + Step 13 + Step 14 + Step 16 will all skip per skip-eligibility).

## Risk surface

- **Path-validation BACKLOG entry deletion (AC03):** the deletion is paired with AC05 lock-in test pinning the segment-aware behaviour → mutation-resistant. R1 should grep the lock-in test for vacuousness (cycle-11 L1 / cycle-16 L2 patterns).
- **Build-graph migration entry deletion (AC04):** paired with AC06 AST guard → revert-resistant. R1 should verify the AST walk covers all current `build_graph` call sites in those two modules.
- **C11-L1 batch upgrades:** revert-check each (per cycle-21 L4) — replace production fix with no-op; assert test FAILS. Without that, the upgrade is C11-L1 in disguise.
- **Folds:** each fold revert-checked per C40-L3.

## Skip-eligibility per pipeline step

| Step | Skip? | Reason |
|---|---|---|
| 02 threat-model | NO (CVE baseline only) | Pure-test cycle; only baseline snapshot needed. Step 02 baseline already captured: 1 vuln (diskcache 5.6.3 CVE-2025-69872, accepted). |
| 06 Context7 | YES | No new lib references; pure stdlib + internal imports. |
| 09.5 simplify | YES | No `src/kb/` diff. |
| 11 SAST + secrets | YES | No `src/kb/` diff (gitleaks still runs per Tier 0/1/2 lane). |
| 11 existing-CVE patch | YES | Step 02 baseline shows 0 NEW open Dependabot alerts; diskcache unchanged (no fix published). |
| 13 coverage delta | YES | No `src/kb/` diff means no touched-file coverage threshold to enforce. |
| 14 security verify | NO | AC03/AC04 deletions are security-adjacent; Step 14 must verify the corresponding lock-ins (AC05/AC06) are mutation-resistant. |
| 16 IaC + container + SBOM | YES | No `*.tf` / `Dockerfile` / dep-manifest diff. |
| 19 signed commits | NO | repo requires signed commits per cycle-43 (run `git log --show-signature` count). |
| 22 deploy gate + 23 smoke | YES | No deployable artifact. |

## Telemetry hooks for the 2026-05-31 trial writeup

- Step 7 plan owner: `mimocoding-rescue @ mimo-v2.5-pro` (binding).
- Step 8 plan-gate owner: `mimocoding-rescue @ mimo-v2.5-pro` (binding).
- Step 9 background reviewer: `deepseek-rescue @ deepseek-v4-pro` (cross-family — cycle 67 L4 lock-in: same-family `mimochat-cli` review on `mimocoding`-implemented code is lint, not review).
- Step 17 doc-update owner: `deepseek-rescue @ deepseek-v4-pro`. Pre-emptive disambiguation per cycle-68 L (DeepSeek doc-update name-collision vulnerability) — the dispatch prompt MUST explicitly call out: this cycle migrates ZERO modules, so any "migrated to LIB" wording is forbidden.
- Step 18 PR-finalise owner: `mimocoding-rescue @ mimo-v2.5`.
- Step 20 R1: `deepseek-rescue @ deepseek-v4-pro` + Sonnet (cross-vendor diversity preserved per `feedback_r2_codex_static_analysis_value` and Step-20 cross-vendor lock-in).
- Step 20 R2: `codex:codex-rescue` + Sonnet.
- Step 20 R3: primary-session synthesis (cycle-16 L4 — fires on ≥15 ACs + new lock-in test surface).

## Tier-aware strict-audit denominator (C59-L4)

Tier 2 binding-owner subset (Steps 4-R2 / 7 / 8 / 9 / 14 / 17 / 18 / 20-R1 / 20-R2): 9 binding-owner steps.

Trial-skill enforcement: 9/9 strict-audit only if all 9 land on the prescribed owner with no fallback. C58-L4 (full-pipeline denominator) is annotated *(superseded by C59-L4 for cycle 59+)*; this cycle reports under C59-L4 semantics.
