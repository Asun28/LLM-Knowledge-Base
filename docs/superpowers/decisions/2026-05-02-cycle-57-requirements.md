# Cycle 57 — Requirements + Threat Model + Design + Plan + Decision Gate

**Date:** 2026-05-02
**Branch:** `cycle-57-batch`
**Worktree:** `D:\Projects\llm-wiki-flywheel\.claude\worktrees\cycle-57`
**Pipeline owner:** Opus 4.7 main session (per cycle-37 L5 primary-session default for ≤15 ACs / ≤5 src files / fold-only cycles)
**Trial context:** May 2026 MiMo trial (cycle 55 = first dev-mimo-opus cycle; cycle 56 = second; cycle 57 = third). MiMo Coding remains preferred for build-path steps when scope warrants — fold-only cycle qualifies for primary-session default per C37-L5.
**Parallel context:** worktree-cycle-53 (4 folds, branch `worktree-cycle-53`) and worktree-cycle-54 (Phase 4 cycle, branch `worktree-cycle-54`) are in flight. Cycle 57 explicitly avoids their receivers.

---

## Step 1 — Problem + Acceptance Criteria

**Problem.** Per Phase 4.5 HIGH `tests/` coverage-visibility entry, ~190 versioned `test_v0NNN_*.py` and `test_cycleNN_*.py` files remain unfolded. Cycles 38-56 have folded ~30 files into canonical receivers under the freeze-and-fold cadence. Cycle 57 continues that cadence with 5 small folds + 1 in-place test-quality upgrade.

**Non-goals.**
- No production source changes (`src/kb/` untouched).
- No new tests beyond what the folded files already contain (test count preserved).
- No CI strictness changes (windows-latest matrix still deferred per cycle-36 L1).
- No dependency bumps (CVE baseline unchanged from main).
- No coverage of items already deferred to specific later cycles (POSIX investigation, GHA-windows reproducer, pyreadline3 root-cause).

**Acceptance criteria (6 ACs).**

| # | AC | Verify |
|---|-----|--------|
| AC1 | `tests/test_v0916_task07.py` (159 LOC, 9 tests across 9 classes) folded into `tests/test_mcp_core.py` under a new section `# ── Phase 3.97 Task 07 — MCP server fixes (cycle 57 fold) ─`; source file deleted | `git diff --stat` shows -1 source / +1 destination touched; pytest collection unchanged at 3022 |
| AC2 | `tests/test_v0916_task08.py` (143 LOC, 4 tests across 4 classes) folded into `tests/test_review.py` under a new section `# ── Phase 3.97 Task 08 — Feedback store fixes (cycle 57 fold) ─`; source file deleted | Same as AC1 |
| AC3 | `tests/test_v0915_task10.py` (195 LOC, 8 tests across 3 classes) folded into `tests/test_cli.py` under a new section `# ── Phase 3.96 Task 10 — CLI fixes (cycle 57 fold) ─`; source file deleted | Same as AC1 |
| AC4 | `tests/test_cycle17_lazy_imports.py` (176 LOC, 8 tests across 5 classes) folded into `tests/test_v070.py` under a new section `# ── Cycle 17 AC4-AC7 — MCP cold-boot lazy imports (cycle 57 fold) ─`; source file deleted; module-level helper `_module_level_imports` and `_REPO_ROOT` / `_SRC_KB_MCP` constants moved to function-local scope OR retained as module-private constants prefixed `_CYCLE17_` per cycle-52 L4 helper-name uniqueness | Same as AC1 + verify constants don't collide with existing test_v070.py symbols |
| AC5 | `tests/test_v0p5_purpose.py` (184 LOC, 7 tests as bare functions) folded into `tests/test_utils.py` under a new section `# ── load_purpose + extraction-prompt purpose threading (cycle 57 fold) ─`; source file deleted | Same as AC1 |
| AC6 | `tests/test_review.py::test_embedding_dim_resolved` triple-escape-hatch upgrade (per cycle-56+ BACKLOG entry): replace the C11-L1 `inspect.getsource(VectorIndex); assert "EMBEDDING_DIM" in src` with a behavioural pin OR delete entirely if `EMBEDDING_DIM` is genuinely unused | Pre-revert proof: replace the production assertion site's logic with an obviously-broken alternative; new test FAILS divergently per C40-L3 |

**Blast radius.** `tests/` only. Affected receivers: `test_mcp_core.py` (AC1), `test_review.py` (AC2 + AC6), `test_cli.py` (AC3), `test_v070.py` (AC4), `test_utils.py` (AC5). Five sources deleted: `test_v0916_task07.py`, `test_v0916_task08.py`, `test_v0915_task10.py`, `test_cycle17_lazy_imports.py`, `test_v0p5_purpose.py`. Net file-count delta: 213 → 208 (-5).

**Collision avoidance with parallel cycles.**
- cycle-53 worktree: folds into `test_compile.py`, `test_config.py`, `test_query.py` — cycle 57 receivers do NOT include any of these.
- cycle-54 worktree: folds into `test_compile.py`, `test_lint.py`, `test_mcp_browse_health.py`, `test_models.py`, `test_utils_io.py` — cycle 57 receivers do NOT include any of these.
- Final landed file count depends on merge ordering (cycle-53 and cycle-54 each net -3 to -4); per cycle-55 precedent, document the count "at branch HEAD; subject to Step 21 rebase".

---

## Step 2 — Threat Model + Dep-CVE Baseline

**Threat surface.** Pure test refactor — no trust boundaries, no data flow, no production-code change. Threats are limited to test-quality regressions:

| ID | Threat | Mitigation | Verify at |
|----|--------|-----------|-----------|
| T1 | Pre-import drift (cycle-18 L1) — folded test relies on a `from kb.X import Y` snapshot that desyncs with sibling `monkeypatch.setattr(X, "Y", ...)` under different test ordering | Use `import kb.X` then reference `kb.X.Y` at call time when the test depends on the module's mutable state | Step 9, per-fold isolation pytest |
| T2 | Reload-leak on exception classes (cycle-20 L1) — `pytest.raises(kb.errors.X)` misfires after another test triggers `importlib.reload(kb.errors)` | Late-bind exception classes via `Y = production_module.X` inside the test function before `pytest.raises` | Step 9, full-suite pytest |
| T3 | Helper-name collision (cycle-52 L4) — fold introduces `_write_page` / `_install_client` / `_FakeMessages` colliding with prior fold helpers in the same receiver | Rename helpers with disambiguating prefixes (`_lazy_imports_module_level_imports`, `_purpose_write_page`, etc.) | Step 9, per-fold isolation pytest |
| T4 | Docstring orphan (cycle-23 L1) — folded function-local imports placed BEFORE docstring closing `"""` orphan `function.__doc__` to None | Receivers in this cycle are TEST modules — no production docstring contract; tests don't introspect `.__doc__`. NOT applicable. | N/A |
| T5 | Vacuous test pass after revert (cycle-11 L2 / cycle-15 L2 / cycle-24 L4) | All folded tests are existing tests being moved verbatim — already passing. AC6 upgrade requires explicit revert-proof per C40-L3 | Step 9 AC6 |
| T6 | Module-level reload leak (cycle-19 L2) — tests that touch `_module_level_imports` (the AST-walker helper from `test_cycle17_lazy_imports.py`) read source files at module load via `Path(__file__).resolve().parent.parent` | Helper is per-call (no module-top side effects); `_REPO_ROOT` / `_SRC_KB_MCP` are module-level Path constants but pure-data (no I/O). Safe. | Step 9 AC4 |
| T7 | Same-class peer scan (cycle-16 L1) — receiver test files may contain semantically identical anti-patterns to anything we add | Pure fold (no new logic introduced); applied during AC6 upgrade only | Step 9 AC6 |

**Dep-CVE baseline (captured 2026-05-02).** `pip-audit` reports 4 vulnerabilities, all class-A pre-existing on main:

| Package | Version | Advisory | Class | Status |
|---------|---------|----------|-------|--------|
| diskcache | 5.6.3 | CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v) | A | No upstream fix; narrow-role (trafilatura robots cache, no `src/kb/` import). BACKLOG-tracked. |
| litellm | 1.83.0 | GHSA-xqmj-j6mv-4862 | A | Fix 1.83.7 BLOCKED by click pin per cycle-55 attempted patch + revert. BACKLOG-tracked. |
| pip | 26.0.1 | CVE-2026-3219 (GHSA-58qw-9mgm-455v) | A | No upstream fix; tooling-only. BACKLOG-tracked. |
| ragas | 0.4.3 | CVE-2026-6587 (GHSA-95ww-475f-pr4f) | A | No upstream fix; dev-eval-only (zero `src/kb/` import). BACKLOG-tracked. |

Cycle 57 introduces zero `requirements.txt` changes → zero PR-introduced (class-B) advisories. Step 14(b) PR-CVE diff and Step 15 patch are skipped per their respective skip-when conditions.

---

## Step 3 — Brainstorming (skipped per skill: trivial established pattern)

Cycles 38-56 have shipped this exact freeze-and-fold pattern 30+ times. No design exploration warranted. The relevant priors:

- cycle-13 L2 sizing heuristic: small mechanical work primary-session.
- cycle-37 L5 primary-session default for ≤15 ACs / ≤5 src files / primary-holds-context.
- cycle-40 L3 revert-proof per fold.
- cycle-40 L5 host-shape preservation (don't restructure receiver during fold).
- cycle-51 L1 per-fold isolation pytest.
- cycle-52 L4 helper-name uniqueness.
- cycle-55 L1 single-AC-with-multi-fold pattern.

---

## Step 4 — Design Eval (R1 inline; R2 skipped per "trivial one-liner")

**R1 grep verification.** Each cited file/symbol verified to exist:

```
tests/test_v0916_task07.py — 159 LOC, 9 classes, 10 tests (one class has 2 tests)
tests/test_v0916_task08.py — 143 LOC, 4 classes, 4 tests
tests/test_v0915_task10.py — 195 LOC, 3 classes, 8 tests
tests/test_cycle17_lazy_imports.py — 176 LOC, 5 classes, 8 tests + 1 helper + 2 module constants
tests/test_v0p5_purpose.py — 184 LOC, 0 classes, 7 bare functions
```

Receivers verified to exist + cycle-50/51/55/56 fold targets:

```
tests/test_mcp_core.py — 869 LOC (cycle-50 fold target)
tests/test_review.py — 437 LOC (cycle-55 fold target)
tests/test_cli.py — 445 LOC (cycle-56 fold target)
tests/test_v070.py — 813 LOC (cycle-49+50+51 fold target)
tests/test_utils.py — cycle-52 fold target (load_all_pages section already present)
```

**Same-class peer scan (cycle-16 L1).** Cycle 57 introduces no new security-class anti-patterns (pure fold). AC6 upgrade is in `kb.config.EMBEDDING_DIM` / `kb.query.embeddings.VectorIndex`; same-class peer scan: `grep -rn "EMBEDDING_DIM" src/kb` — confirms only `config.py` (definition) and `query/embeddings.py::VectorIndex.build` (consumer). No additional sites.

**Symbol-verification per AC (cycle-15 L1).**

- AC1 — verified: `kb.mcp.core.kb_query`, `kb.mcp.quality.kb_reliability_map`, `kb.mcp.quality.kb_create_page`, `kb.mcp.browse.kb_read_page`, `kb.mcp.browse.kb_list_sources`, `kb.mcp.app._validate_page_id`, `kb.mcp.quality.kb_save_lint_verdict`, `kb.config.MAX_NOTES_LEN`, `kb.feedback.reliability.compute_trust_scores`, `kb.query.engine.search_pages`, `kb.query.engine.query_wiki`, `kb.feedback.reliability.compute_trust_scores`. All present.
- AC2 — verified: `kb.feedback.store.load_feedback`, `kb.feedback.store.add_feedback_entry`, `kb.feedback.store._feedback_lock`, `kb.feedback.reliability.get_coverage_gaps`. All present.
- AC3 — verified: `kb.cli.ingest`, `kb.cli.lint`, `kb.ingest.pipeline.ingest_source`, `kb.lint.runner.run_all_checks`, `kb.lint.runner.format_report`. All present.
- AC4 — verified: `src/kb/mcp/core.py`, `src/kb/mcp/health.py`, `src/kb/mcp/browse.py`, `src/kb/mcp/quality.py` all exist. The AST helper inspects file contents — pure file-read.
- AC5 — verified: `kb.utils.pages.load_purpose`, `kb.ingest.extractors.build_extraction_prompt`, `kb.query.engine.query_wiki`, `kb.query.engine.call_llm`. All present.
- AC6 — verified: `kb.config.EMBEDDING_DIM` exists; `kb.query.embeddings.VectorIndex` exists and references `EMBEDDING_DIM` in `build`. The current vacuous test imports both and asserts `"EMBEDDING_DIM" in inspect.getsource(VectorIndex)`.

**Monkeypatch-target enumeration (cycle-17 L1).** AC1's TestKbQueryMaxResultsForwarding patches `kb.query.engine.query_wiki` (NOT `kb.mcp.core.query_wiki`) — patch the OWNER MODULE per CLAUDE.md core convention. Confirmed correct.

---

## Step 5 — Decision Gate

**Q1: Where do test_v0916_task07.py's 9 classes go — single receiver or split by mcp/ submodule?**

OPTIONS: (a) single receiver `test_mcp_core.py` (all 9 classes); (b) split by submodule (test_mcp_core.py for core/quality/app, test_mcp_browse_health.py for browse).

ARGUE: Option (b) collides with cycle-54 worktree's pending changes to `test_mcp_browse_health.py`. Option (a) consolidates per cycle-50 precedent (`test_v01012_mcp_validation.py` → `test_mcp_core.py` cross-module hosting via `TestMcpWikiDirValidation` class spanning `kb.mcp.{core,health}`). The cross-module hosting is established convention.

DECIDE: **Option (a)** — fold all 9 classes into `test_mcp_core.py`. Confidence: high.

RATIONALE: Avoids cycle-54 collision + matches cycle-50 precedent. Future cycle can split if cross-module hosting becomes unwieldy (not currently — receiver is at 869 LOC).

**Q2: AC4 helper `_module_level_imports` — keep at module level or move to nested fixture?**

OPTIONS: (a) Keep as module-level helper with disambiguating rename (`_cycle17_module_level_imports`); (b) move inside the receiver class as `@staticmethod`; (c) inline into each test method.

ARGUE: Option (c) violates DRY (used by 7 of 8 tests in the cycle 17 file). Option (b) loses bare-function tests' callability — but AC4 tests are organized in 5 classes already, so nesting works. Option (a) preserves the existing structure verbatim per host-shape preservation (cycle-40 L5).

DECIDE: **Option (a)** — keep as module-level helper, rename to `_cycle17_module_level_imports`. Same for `_REPO_ROOT` → `_CYCLE17_REPO_ROOT` if it collides; `_SRC_KB_MCP` → `_CYCLE17_SRC_KB_MCP`.

RATIONALE: Host-shape preservation per cycle-40 L5 + helper-name uniqueness per cycle-52 L4. Confidence: high.

**Q3: AC5 — test_v0p5_purpose has tests spanning utils.pages + ingest.extractors + query.engine. Receiver split or single?**

OPTIONS: (a) single receiver `test_utils.py` (`load_purpose` is the canonical anchor); (b) split between test_utils.py (load_purpose), test_ingest.py (build_extraction_prompt), test_query.py (AC14 query path).

ARGUE: Option (b) hits collision with cycle-53's `test_query.py` work. Option (a) keeps the feature's tests together — the wiki/purpose.md feature touches all three layers as a coherent capability, and the file's section-comment structure already groups by call site. Single receiver matches the cycle-55 fold of `test_v01011_review_feedback_fixes.py` which kept config + embeddings tests in a single receiver per Q2 host-shape preservation (C40-L5).

DECIDE: **Option (a)** — single receiver `test_utils.py`. Section header captures the cross-layer scope.

RATIONALE: Avoids cycle-53 collision. Feature-coherence over module-coherence. Confidence: high.

**Q4: AC6 — upgrade or delete?**

OPTIONS: (a) delete the test entirely if `EMBEDDING_DIM` is unused; (b) replace with behavioural pin via `VectorIndex(EMBEDDING_DIM=999, …).build()` raises typed error.

ARGUE: `grep -rnE "EMBEDDING_DIM" src/kb` shows config.py (definition) + query/embeddings.py::VectorIndex.build (consumer). EMBEDDING_DIM is USED — option (a) would orphan a real config constant. Option (b) needs an actual contract: what does VectorIndex do when EMBEDDING_DIM mismatches? Per cycle-25 AC3-AC5, dim-mismatch is logged and the query returns BM25-only fallback; it doesn't raise.

DECIDE: **Option (b modified)** — replace the inspect.getsource pattern with a behavioural assertion that the resolved EMBEDDING_DIM is the value the production VectorIndex sees AT BUILD TIME. Specifically: monkeypatch `kb.config.EMBEDDING_DIM` to a sentinel value, instantiate VectorIndex.build with a small corpus, and assert the persisted vec_db schema reflects the sentinel dim. Falls back to documenting why a true behavioural test is infeasible if sqlite-vec extension load fails (cycle-28 SQLITE_VEC_LOAD_WARN context).

RATIONALE: Eliminates C11-L1 vacuous source-grep while preserving the integration anchor. Revert-proof per C40-L3 (replace `EMBEDDING_DIM` reference with a literal in build → test sees wrong dim → fails).

ESCALATION: None of the questions hit "no principle constrains it AND both options are irreversible AND wrong choice costs more than asking".

---

## Step 6 — Context7 (skipped — pure stdlib + project internal)

Cycle uses no third-party library APIs beyond what existing tests already use (`unittest.mock`, `click.testing`, `pytest` fixtures). No Context7 lookup warranted.

---

## Step 7 — Implementation Plan

| Task | Files | Change | Test contract | AC | Threat |
|------|-------|--------|---------------|----|----|
| T1 | tests/test_v0916_task07.py (delete) + tests/test_mcp_core.py (extend) | Append new section `# ── Phase 3.97 Task 07 — MCP server fixes (cycle 57 fold) ─` at EOF; copy 9 classes verbatim | per-fold pytest passes 10 tests + isolation pytest (-s -p no:cacheprovider) on receiver passes | AC1 | T2/T3 (no new helpers; classes already disambiguated) |
| T2 | tests/test_v0916_task08.py (delete) + tests/test_review.py (extend) | Append new section `# ── Phase 3.97 Task 08 — Feedback store fixes (cycle 57 fold) ─` at EOF; copy 4 classes verbatim | per-fold pytest passes 4 tests + isolation pytest passes | AC2 | T3 (no new helpers) |
| T3 | tests/test_v0915_task10.py (delete) + tests/test_cli.py (extend) | Append new section `# ── Phase 3.96 Task 10 — CLI fixes (cycle 57 fold) ─` at EOF; copy 3 classes verbatim | per-fold pytest passes 8 tests + isolation pytest passes | AC3 | T3 |
| T4 | tests/test_cycle17_lazy_imports.py (delete) + tests/test_v070.py (extend) | Append new section `# ── Cycle 17 AC4-AC7 — MCP cold-boot lazy imports (cycle 57 fold) ─` at EOF; copy 5 classes + helper `_module_level_imports` (rename to `_cycle17_module_level_imports`) + module constants `_REPO_ROOT` (rename `_CYCLE17_REPO_ROOT`) and `_SRC_KB_MCP` (rename `_CYCLE17_SRC_KB_MCP`); update all 8 references in the 5 classes | per-fold pytest passes 8 tests + isolation pytest passes; grep test_v070.py for `_REPO_ROOT` collision check (none expected) | AC4 | T3, T6 |
| T5 | tests/test_v0p5_purpose.py (delete) + tests/test_utils.py (extend) | Append new section `# ── load_purpose + extraction-prompt purpose threading (cycle 57 fold) ─` at EOF; copy 7 bare functions verbatim | per-fold pytest passes 7 tests + isolation pytest passes | AC5 | T1, T6 |
| T6 | tests/test_review.py (in-place upgrade) | Locate `test_embedding_dim_resolved` (folded in cycle-55); replace `inspect.getsource(VectorIndex)` + `assert "EMBEDDING_DIM" in src` with behavioural pin: monkeypatch `kb.config.EMBEDDING_DIM` to a sentinel int; build a small VectorIndex; assert the constructed index sees the sentinel via `index._dim` or schema introspection. Fallback: keep the test if behavioural pin is infeasible due to sqlite-vec load — but document the keep-with-justification | revert-proof: replace `kb.query.embeddings.VectorIndex.build` to ignore EMBEDDING_DIM → test fails | AC6 | T5, T7 |

**Per-task commit shape:** one commit per task. Commit messages follow cycle-56 precedent: `test(cycle 57): fold test_X into test_Y.py (N/6)` for T1-T5; `test(cycle 57): upgrade test_embedding_dim_resolved C11-L1 vacuous to behavioural pin (6/6)` for T6.

**Per-fold validation:** after each task's Edit, run `python -m pytest tests/<receiver> -q` to confirm the new tests pass IN ISOLATION on the receiver. Revert-proof check per C40-L3: temporarily insert `assert False` at the top of one moved method; confirm `pytest -x` FAILS at that method; restore.

---

## Step 8 — Plan Gate

**Coverage check:**
- Every AC has a corresponding TASK ✓ (AC1=T1, AC2=T2, AC3=T3, AC4=T4, AC5=T5, AC6=T6).
- Every threat-model item has a mitigation pinned in TASK rows ✓.
- Every TASK has an explicit test expectation ✓.

**PLAN-AMENDS-DESIGN check:** no contradictions between plan and design.

**Same-class peer scan:** AC6 is the only security-adjacent change; same-class peer scan completed at Step 4 (only sites are config + embeddings).

**Verdict: APPROVE.** Ready for Step 9 implementation.

---

## Step 5/8 final decision summary

| Decision | Resolution |
|----------|-----------|
| Q1 (AC1 receiver split) | Single receiver test_mcp_core.py per cycle-50 cross-module precedent |
| Q2 (AC4 helper placement) | Module-level with cycle-prefix rename per cycle-40 L5 + cycle-52 L4 |
| Q3 (AC5 receiver split) | Single receiver test_utils.py per cycle-55 feature-coherence precedent |
| Q4 (AC6 upgrade vs delete) | Behavioural pin (option b modified) per cycle-56+ BACKLOG entry option (2) |

No questions ESCALATEd.
