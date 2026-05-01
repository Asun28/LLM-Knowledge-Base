# Cycle 55 — Design Decision Gate

**Date:** 2026-05-02
**Branch:** `cycle-55-batch` (worktree: `.claude/worktrees/cycle-55`)
**Pipeline:** `dev-mimo-opus` (project trial)
**Baseline:** `origin/main` @ `b3132e3` (post-PR-#75 docs(mimocoding) carry-overs not yet pushed)

---

## Step 1 — Requirements

### Problem
Phase 4.5 HIGH `tests/` coverage-visibility — ~50 of 94 files are version-tagged
(`test_v0NNN_*.py` / `test_phase4_audit_*.py`) and obscure canonical-receiver coverage.
Cycles 38-54 fold these into the receivers (`test_compile.py`, `test_query.py`, etc.) at
4 folds per cycle. Cycles 53 + 54 are running in parallel worktrees; this is the
first real-cycle exercise of the `dev-mimo-opus` trial skill (May 2026 trial).

### Acceptance Criteria

| AC | Statement | Verification |
|----|-----------|--------------|
| AC1 | Fold `tests/test_v01003_graph_fixes.py` (3 tests) into `tests/test_graph.py`; upgrade vacuous `inspect.getsource` half of `test_graph_stats_uses_precomputed_out_degrees` per C11-L1 | `pytest tests/test_graph.py -v` shows new tests; revert-verify per C40-L3 |
| AC2 | Fold `tests/test_v01007_evolve_fixes.py` (3 tests) into `tests/test_evolve.py` under new section header | `pytest tests/test_evolve.py -v`; revert-verify |
| AC3 | Fold `tests/test_v01009_ingest_aux_fixes.py` (3 tests) into `tests/test_ingest.py` under new section header | `pytest tests/test_ingest.py -v`; revert-verify |
| AC4 | Fold `tests/test_v01011_review_feedback_fixes.py` (3 tests) into `tests/test_review.py` under new section header. The third test (`test_embedding_dim_resolved`) joins despite touching config/embeddings — host-shape preservation per C40-L5 | `pytest tests/test_review.py -v`; revert-verify |
| AC5 | Each moved test passes the C40-L3 revert-verify (`assert False` → pytest -x FAIL on the moved method, then restored) | log per-fold revert-verify in commit message |
| AC6 | Per-fold isolation pytest passes per C51-L1 (run the receiver file in isolation after each fold to catch full-suite ordering issues) | `pytest tests/test_<receiver>.py -q` in isolation per fold |
| AC7 | Test count preserved at 3025 (3014 passed + 11 skipped); test file count drops 225 → 221 (4 deletes) — assuming sequential merge after cycles 53 + 54 are NOT yet merged. **If 53 or 54 lands first, rebase + bump end-state before merge.** | `pytest --collect-only -q \| tail -1` shows `3025 tests collected`; `find tests -maxdepth 1 -name 'test_*.py' \| wc -l` shows 221 |
| AC8 | BACKLOG.md HIGH freeze-and-fold parenthetical updated with cycle-55 progress note | grep `cycle 55` in BACKLOG.md after Step 17 |
| AC9 | dep-CVE re-confirm: pip-audit baseline at Step 2 captured as `.data/cycle-55/cve-baseline.json`; Step 14 PR-introduced diff = empty; Step 15 opportunistic patch only on `first_patched_version != null` | `pip-audit -r requirements.txt` on branch HEAD vs baseline; ID diff = ∅ |
| AC10 | Marker artifact: this design doc + the plan doc at `docs/superpowers/decisions/2026-05-02-cycle-55-batch-{design,plan}.md` are the cycle-55 picked-items declaration. Branch `cycle-55-batch` will be pushed to origin AFTER Step 5 commit so cycles 56+ see the picks via `git branch -r --list 'origin/cycle-*'` | `git ls-remote origin cycle-55-batch` returns the SHA |

### Non-goals
- **No production source changes.** `src/kb/*` untouched. Cycle 54 holds `src/kb/utils/io.py` (Windows file_lock fix) and `src/kb/compile/compiler.py` (canonical_rel_path fix); cycle 55 must not collide.
- **No CI/dependency files.** Only an opportunistic dep-CVE patch (Step 15) if `first_patched_version` is non-null.
- **No receivers held by cycle 53 or 54.** Avoid `test_compile.py`, `test_config.py`, `test_query.py` (cycle 53) and `test_lint.py`, `test_mcp_browse_health.py`, `test_models.py`, `test_utils_io.py`, `test_compile.py` (cycle 54). My receivers — `test_graph.py`, `test_evolve.py`, `test_ingest.py`, `test_review.py` — are disjoint.
- **No new feature work.** Pure test-fold + dep-CVE re-confirm; same shape as cycles 47-54.

### Blast radius
`tests/` directory only. 4 deletes + 4 receiver expansions. ~360 LoC of test moves total. No production impact.

---

## Step 2 — Threat model

**SKIPPED** per skill rule "pure internal refactor, no I/O or trust boundary changes". Test moves are signature-preserving and never reach a trust boundary. Step 14 security verify is therefore also skipped.

### Dep-CVE baseline (still required at Step 2)

```bash
mkdir -p .data/cycle-55
gh api "repos/Asun28/llm-wiki-flywheel/dependabot/alerts" --paginate \
  --jq '[.[] | select(.state=="open") | {id:.number, severity:.security_vulnerability.severity, package:.dependency.package.name, ghsa:.security_advisory.ghsa_id, first_patched:.security_vulnerability.first_patched_version.identifier}]' \
  > .data/cycle-55/alerts-baseline.json
# Per C34-L1: audit the LIVE venv (pip-audit without -r) to avoid silent
# ResolutionImpossible failures that produce empty baselines. Project has a
# diskcache pin tied to crawl4ai that would trip pip-audit -r requirements.txt.
.venv/Scripts/pip-audit.exe --format json \
  > .data/cycle-55/cve-baseline.json 2>.data/cycle-55/cve-baseline.stderr.txt || true
```

To run as Step 2 first action of the cycle. Capture summary in CHANGELOG-history.md.

---

## Step 3 — Brainstorming

**SKIPPED.** Approach is fixed by 7 prior cycles (47-54): pick 4 small versioned-test files, fold into canonical receivers, preserve behavior + revert-verify, isolation pytest per fold, dep-CVE re-confirm, then standard PR pipeline.

---

## Step 4 — Design eval (2 rounds)

**SKIPPED.** Trivial folds — no novel design surface. Cycle-13 L2 sizing heuristic applies (each fold ~3 tests, ~50-80 LoC; primary session is faster + safer than dispatch overhead).

---

## Step 5 — Decisions

### Q1 — How to handle vacuous `inspect.getsource` half of `test_graph_stats_uses_precomputed_out_degrees`?

Source file (line 17-20):
```python
src = inspect.getsource(graph_stats)
assert "out_degrees" in src, "graph_stats must precompute out_degrees dict"
assert "graph.degree(n)" not in src, "graph_stats must not call graph.degree(n) per-node"
```

Per **C11-L1** (no source-file string reads as test assertions, regardless of API), this fails the cycle-44 vacuous-test class. Two options:

**(a) DELETE the getsource half, keep the behavioral half** (graph orphan-count assertion). The test name then misrepresents what it asserts — should rename.

**(b) UPGRADE to behavioral spy-based assertion.** Replace getsource with a spy on `nx.DiGraph.degree` that counts per-node calls; assert call count is 0 (out_degrees dict precomputed). True behavioral signal.

**DECIDED: (b) UPGRADE during fold.** Behavioral spy preserves the original intent (no per-node `graph.degree(n)` calls) without violating C11-L1. Rename test to `test_graph_stats_avoids_per_node_degree_calls` to match what it asserts. Add the orphan-count assertion as a separate test `test_graph_stats_orphan_detection_with_isolated_node` (test_graph.py already has `test_graph_stats_orphan_detection` at line 109 — disambiguate via the `_with_isolated_node` suffix).

**Why:** C40-L3 mandates revert-verify after each fold; an upgrade with a behavioral assertion gives revert-verify real teeth. Renaming away from the misleading `_uses_precomputed_out_degrees` removes future-maintainer confusion.

**Risk:** the spy depends on `nx.DiGraph.degree` being the actual code path. Pre-implementation grep at Step 9 confirms `kb.graph.builder.graph_stats` reads `out_degrees` directly without falling back to `graph.degree(n)`.

### Q2 — Where does `test_embedding_dim_resolved` (from test_v01011) land?

Source touches `kb.config.EMBEDDING_DIM` and `kb.query.embeddings.VectorIndex`. Two options:

**(a)** Split — 2 refine_page tests to `test_review.py`, 1 embedding test to `test_query.py`.

**(b)** All 3 to `test_review.py` per host-shape preservation (C40-L5).

**DECIDED: (b).** `test_query.py` is being modified by cycle 53 (test_v0917_raw_fallback + test_v0917_rewriter folds) — adding to it from this cycle creates an unnecessary merge surface. The source file groups all 3 under "Phase 4 review/feedback/config fixes" — host-shape preservation says fold them together under a section header that names the original grouping.

**Section name:** `# ── Phase 4 review/feedback/config fixes (cycle 55 fold) ─` placed at end-of-file in `test_review.py`.

### Q3 — Helper-name uniqueness across receivers?

None of the 4 source files define module-level helpers. All 4 keep test bodies self-contained with function-local imports. No rename needed.

### Q4 — Section-header placement in each receiver?

| Receiver | Convention | Cycle 55 placement |
|----------|------------|--------------------|
| test_graph.py | NO existing section headers (8 bare functions) | end-of-file, NEW section `# ── Phase 4 graph fixes (cycle 55 fold) ─` |
| test_evolve.py | sectioned (`# ── Coverage analysis ──`, etc.) + cycle-48 fold section | end-of-file, NEW section `# ── Phase 4 evolve fixes (cycle 55 fold) ─` |
| test_ingest.py | sectioned + cycle-43 fold, cycle-11 fold sections | end-of-file, NEW section `# ── Phase 4 ingest aux fixes (cycle 55 fold) ─` |
| test_review.py | sectioned (`# ── refine_page ──`, etc.) | end-of-file, NEW section `# ── Phase 4 review/feedback/config fixes (cycle 55 fold) ─` |

End-of-file placement is the cycle-50 / cycle-51 / cycle-52 convention. Inserting into existing sections breaks AC6 isolation testing because the moved tests then depend on receiver-local helpers / fixtures that may shift across pre-fold runs.

### Q5 — Function-local imports required?

Yes. Per **C19-L2** (reload-leak hazard via sibling-module `importlib.reload`), all moved test functions import `kb.*` symbols inside the function body, not at the test-module top. Each source file already uses function-local imports — preserve verbatim.

### Q6 — Coordination with parallel cycles 53 + 54

| Cycle | Worktree | Status | Picks | Receivers touched |
|-------|----------|--------|-------|-------------------|
| 53 | `.claude/worktrees/cycle-53` | 4/4 folds done, no PR yet | test_v01006_compile_fixes, test_v01002_consolidated_constants, test_v0917_raw_fallback, test_v0917_rewriter | test_compile.py, test_config.py, test_query.py |
| 54 | `.claude/worktrees/cycle-54` | mid-cycle (design + plan + impl WIP) | test_cycle15_lint_status_mature, test_cycle45_package_constants_propagate_to_submodules, test_cycle8_health_wiki_dir, test_cycle8_models_validation | test_lint.py, test_mcp_browse_health.py, test_models.py + src/kb/{compile/compiler,utils/io}.py |
| 55 (this) | `.claude/worktrees/cycle-55` | starting | test_v01003_graph_fixes, test_v01007_evolve_fixes, test_v01009_ingest_aux_fixes, test_v01011_review_feedback_fixes | test_graph.py, test_evolve.py, test_ingest.py, test_review.py |

**Receiver disjointness verified.** No overlap with cycle 53 or 54.

**Source-file disjointness verified.** No overlap on tests/test_v* or tests/test_cycle* picks.

**End-state count caveat (AC7):** my doc updates target 225 → 221 from MY baseline. If cycle 53 (225 → 221) merges first, my baseline shifts to 221, and my end-state becomes 221 → 217. Same for cycle 54. The Step 21 merge may need a rebase + count-bump in CHANGELOG / CHANGELOG-history / CLAUDE.md / docs/reference/testing.md / docs/reference/implementation-status.md / BACKLOG.md HIGH parenthetical. Defer to Step 21 — write counts against my baseline at Step 17.

---

## CONDITIONS (Step 9 must satisfy)

1. **Revert-verify per fold (C40-L3):** after writing each moved test in the receiver, replace its body with `assert False` → run `pytest tests/test_<receiver>.py::<TestClass-or-method> -x` → confirm FAIL → restore the body. Log the revert-verify line in the per-fold commit message.
2. **Isolation pytest per fold (C51-L1):** after each fold's commit, run `pytest tests/test_<receiver>.py -q` in isolation. Must show the new tests passing alongside existing tests.
3. **Function-local imports (C19-L2):** every moved test keeps `from kb.*` imports inside the function body, not at module top.
4. **Q1 upgrade (C11-L1):** the `test_graph_stats_uses_precomputed_out_degrees` source test must NOT be folded verbatim. The vacuous `inspect.getsource` half is replaced by a behavioral spy on `nx.DiGraph.degree` that asserts call count == 0. Test renamed to `test_graph_stats_avoids_per_node_degree_calls`. Add separate `test_graph_stats_orphan_detection_with_isolated_node` for the orphan-count half.
5. **Function-name disambiguation:** before each fold, grep the receiver for the moved test's function name. If a test of the same name already exists, append `_<source_module>` to the moved test's name (e.g. `test_load_template_v01009`).
6. **Source file deletion:** after each fold's revert-verify passes and isolation pytest passes, `git rm tests/test_v0NNNN_*.py` in the SAME commit as the receiver-add. Per cycle-50 / 51 convention.

---

## VERDICT — PROCEED

All 6 questions resolved autonomously. No ESCALATE. Confidence: high (7th cycle of the same fold pattern; only novelty is the trial-skill dispatch attempts at Step 7 + Step 17).

---

## Final decided design

**Picks:**
- AC1: `test_v01003_graph_fixes.py` → `test_graph.py` (with C11-L1 upgrade on test 1)
- AC2: `test_v01007_evolve_fixes.py` → `test_evolve.py`
- AC3: `test_v01009_ingest_aux_fixes.py` → `test_ingest.py`
- AC4: `test_v01011_review_feedback_fixes.py` → `test_review.py`

**Receivers (no collision with cycles 53/54):** test_graph.py, test_evolve.py, test_ingest.py, test_review.py.

**Trial-skill dispatch attempts:**
- Step 7 (plan): `Agent(subagent_type="mimocoding-rescue", model="mimo-v2.5-pro")`. On `subagent_type not found` → fall back to primary session per cycle-13 L2 sizing heuristic (small mechanical work).
- Step 17 (doc update): `Agent(subagent_type="mimochat-rescue", model="mimo-v2-flash")`. On failure → primary session.
- Step 20 R1: DeepSeek + Sonnet. Step 20 R2: Codex + Sonnet. Independent of MiMo per skill spec.

**Trial data captured at Step 24:** dispatch attempt success/fail, time-to-completion vs primary-session estimate, output quality vs primary-session estimate. First data point for the 2026-05-31 trial writeup.
