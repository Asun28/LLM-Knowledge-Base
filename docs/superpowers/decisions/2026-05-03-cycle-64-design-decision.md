# Cycle 64 — Design Decision Gate (Step 5)

**Date:** 2026-05-03
**Branch:** `feat/cycle-64` (worktree `D:/Projects/llm-wiki-flywheel/.claude/worktrees/cycle-64`)
**Base:** `main` @ `d7a98b7`
**Author:** Opus 4.7 design-decision subagent (Step 5)
**Pipeline:** `dev-mimo-opus` (May 2026 MiMo trial — sixth dispatch cycle)
**Inputs:**
- `docs/superpowers/decisions/2026-05-03-cycle-64-requirements.md` (21 ACs, Tier 2)
- `docs/superpowers/decisions/2026-05-03-cycle-64-threat-model.md` (18 threats, 4 material)
- `docs/superpowers/decisions/2026-05-03-cycle-64-design-eval-R1.md` (Opus 4.7 R1 — NEEDS_REVISION, 4 BLOCKER + 7 MAJOR + 5 MINOR + 1 NIT)
- `docs/superpowers/decisions/2026-05-03-cycle-64-design-eval-R2.md` (DeepSeek V4 Pro R2 — NEEDS_REVISION, 3 BLOCKER + 2 MAJOR + 2 MINOR + 1 INFO)

---

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS.**

R1 raised 4 BLOCKERs (F1 conftest duplication, F2 same-class peer scan, F3 file-path typo `refine`→`review`, F4 file-path typo `utils`→`ingest`) — all factually correct precision fixes per pre-verification, none warranting REJECT. R2 raised 3 BLOCKERs that overlap with R1: R2-F1 is a different angle on R1-F1 (both resolve via `tmp_kb_env`-promotion), R2-F3 duplicates R1-F9 (path validation), R2-F2 (rebuild UX clarification) is a wording sharpening of AC6's existing "first query returns []" contract. After inline resolutions and 4 NEW sub-ACs (AC1.4, AC8.5, AC11.5, AC15.5) added below, the 25-AC bundle is internally consistent, scope-bounded, and Step 7 plan-gate (mimo-v2.5-pro audit role per C61-L1) can proceed against the revised AC list as the authoritative spec — NO re-dispatch to design-eval is required.

---

## R1 + R2 finding resolution table

Findings are merged where both reviewers concurred on the same surface. Affected AC numbers below reference the **revised** numbering.

| Finding ID + reviewer | Severity | Resolution | Affected ACs | Notes |
|---|---|---|---|---|
| **R1-F1 + R2-F1** (concurred — conftest duplication / module-binding hazard) | BLOCKER | **ACCEPT** R1's fix | AC1, AC1.4 | Promote existing `tmp_kb_env` (conftest.py:128–285) to `@pytest.fixture(autouse=True)`; rename `_kb_sandbox` (line 290) to `kb_sandbox` public alias for explicit-opt-in tests. R2-F1's "module-level binding" concern is resolved by `tmp_kb_env`'s existing mirror-rebind loop (conftest.py:248–255 already iterates `sys.modules` for `kb.*` modules). NEW sub-AC AC1.4 verifies the 230 existing `tmp_kb_env` call-sites still pass. |
| **R1-F2** (same-class peer scan: 5/10 vs 10/10 `build_graph` sites) | BLOCKER | **ACCEPT** R1 option (b) | AC10, AC21 | Explicitly scope AC10 to **lint-pass cache only** (5 sites: `lint/checks/cycles.py`, `lint/checks/orphan.py`, `lint/semantic.py`, `lint/augment/collector.py`, `lint/runner.py`). Defer the 5 non-lint sites (`evolve/analyzer.py:28,127,358`, `graph/export.py:83`, `mcp/browse.py:345`, `query/engine.py:408`) to cycle-65+. AC21 BACKLOG-delete must reflect "lint-shared graph cache" (partial closure of R2 entry) honestly — not "graph cache" (would over-claim). |
| **R1-F3** (path typo `refine` → `review`) | BLOCKER | **ACCEPT** | AC11, Cluster C context block | File is `src/kb/review/refiner.py::refine_page`, NOT `src/kb/refine/refiner.py`. Pre-verified: `src/kb/review/refiner.py` exists, `src/kb/refine/` directory does NOT exist. |
| **R1-F4** (path typo `utils` → `ingest`) | BLOCKER | **ACCEPT** | AC19 | Function is `kb.ingest.evidence.append_evidence_trail`, NOT `kb.utils.evidence`. Pre-verified: `src/kb/ingest/evidence.py` exists, `src/kb/utils/evidence.py` does NOT exist. |
| **R1-F5** (`pages=` cache-key collision) | MAJOR | **ACCEPT** option (b) | AC9 | Bypass cache entirely when `pages=` is supplied. AC9 contract: "if `pages is not None`, call `build_graph(wiki_dir, pages=pages)` directly without consulting cache and without populating cache." Simpler than per-page-set hashing. Caller `lint/semantic.py:140` (the only `pages=` caller per AC10) sees no behavioural regression — the page list is already in memory. |
| **R1-F6** (M1 grep over-broad) | MAJOR | **MODIFY** | AC1 + Step 14 verifier | R1 narrows the M1 grep to production-active leak surfaces (`OUTPUTS_DIR`, `HASH_MANIFEST`, `FEEDBACK_PATH`, `VERDICTS_PATH`, `REVIEW_HISTORY_PATH`). `tmp_kb_env` already covers these — no AC1 extension needed. The narrowed Step 14 grep stays as a regression check (defense-in-depth against future code adding new constant reads). |
| **R1-F7 + (R2-F2 partial)** (cycle-19 L2 env-binding-at-import) | MAJOR | **ACCEPT** R1's fix | AC6, AC8.5 | Read `KB_DISABLE_VECTOR_AUTO_REBUILD` AT CALL TIME inside `VectorIndex.query()`'s rebuild branch — not as a module-top constant. NEW sub-AC AC8.5 (`test_kill_switch_env_set_after_import_is_honoured`) is the revert anchor. |
| **R1-F8** (Q3 — coarse invalidation post-compile) | MAJOR | **ACCEPT** as new sub-AC | AC11.5 (NEW) | Add AC11.5: `compile_wiki` calls `kb.graph.cache.invalidate(effective_wiki_dir)` AFTER manifest-prune block, BEFORE auto-publish hook (AC14). One line, no error path, structurally required for Phase 5 forward-compat. |
| **R1-F9 + R2-F3** (concurred — path validation in AC6/AC13 must be ACs, not verifier-only) | MAJOR | **ACCEPT** R1's promotion | AC6, AC13, AC15.5 (NEW) | Promote `_validate_path_under_project_root(wiki_dir, "vector_auto_rebuild_target")` from M4 verifier-only into AC6 contract. Promote `_validate_path_under_project_root(out_dir, "publish_out_dir")` from T10/M4 verifier-only into AC13 contract. NEW sub-AC AC15.5 (`test_auto_publish_rejects_out_dir_outside_project_root`) anchors AC13's validation. AC8 already has the auto-rebuild concurrent-test; add `test_auto_rebuild_rejects_wiki_dir_outside_project_root` as 5th case. Per cycle-44 L4 DROP-with-test-anchor: security mitigations live in ACs. |
| **R1-F10** (AC14 `mode != "full"` typo) | MAJOR | **ACCEPT** | AC14 | Replace `incremental=(mode != "full")` with `incremental=incremental`. `compile_wiki` has no `mode` variable. |
| **R1-F11** (AC8 spy-target wrong: `_is_rebuild_needed` is gate-counter, not body-counter) | MAJOR | **ACCEPT** | AC8 | Spy on `model.encode` or `load_all_pages` (the actual rebuild-body work, runs once per actual rebuild) instead of `_is_rebuild_needed` (called twice per rebuild path due to double-checked locking). |
| **R1-F12** (cycle-18 L1 — AC9's `build_graph` import shape unspecified) | MAJOR | **ACCEPT** | AC9 | AC9 contract MUST specify: `cache.py` uses `from kb.graph.builder import build_graph` so AC12 spies on `kb.graph.cache.build_graph` succeed. This is owner-module patching per CLAUDE.md path-safety conventions. See CONDITIONS §2 below. |
| **R1-F13** (LRU eviction semantics ambiguous) | MINOR | **ACCEPT** | AC9, AC12 | Specify FIFO insertion-order eviction matching cycle-7's `_index_cache` (embeddings.py:362–381). AC12's `test_cache_size_bound_lru_eviction` reworded to "FIFO eviction by insertion order". |
| **R1-F14** (manifest filename namespace clash) | MINOR | **ACCEPT** option (a) | AC16 | Filename `publish-siblings-manifest.json` is unique enough; document in `docs/reference/architecture.md` per AC11/AC21 doc-update. No path change. |
| **R1-F15** (syrupy fallback not behaviour-equivalent) | MINOR | **ACCEPT** | AC18 | AC18 documents: "if syrupy is rejected by Step 11 SCA, AC19's `test_lint_report_format_snapshot` renders through `format_report` (already returns text); Mermaid + evidence-trail subjects are text-native — no JSON snapshots in this cycle." |
| **R1-F16** (BACKLOG entry partial-closure) | MINOR | **ACCEPT** | AC21 | Rewrite `tests/` MEDIUM no-golden-file BACKLOG entry as: "— remaining subjects (page-render, llms-full body, JSON-LD): deferred to cycle-65+." Avoids inventing a new lifecycle state. |
| **R1-F17** (AC5 `<dir>/.data/<file>` heuristic hand-wavy) | NIT | **ACCEPT** | AC5 | Replace bullet 2 with literal name checks: `db_path.name.endswith('.tmp')` OR `db_path.parent.name != '.data'` OR `db_path.name != 'vector_index.db'`. Codifies inverse of `_vec_db_path` (embeddings.py:200–202). |
| **R2-F4** (lru_cache simplification) | MAJOR | **REJECT** | AC9 | `functools.lru_cache(maxsize=4)` does NOT support per-key `invalidate(wiki_dir)` semantics — only `cache_clear()` (drops all). AC11's invalidation hooks at `ingest_source` and `refine_page` MUST drop only the affected wiki_dir's entry; bulk-clear would defeat the cache for multi-wiki test fixtures (e.g. AC12 case `test_invalidate_drops_entries_for_wiki_dir`). The bespoke dict + RLock is structurally required, not over-engineered. Rejecting as `cache_clear()` would also defeat F8's coarse-invalidation contract (per-`wiki_dir` precision). Documented so future cycles don't re-revisit. |
| **R2-F5** (RLock re-entrancy concern) | MAJOR | **REJECT** | AC9 | RLock is the right primitive given cycle-19 L2 reload-leak hazard pattern: test code may invoke cache-clear from within a fixture that holds another lock (e.g. `tmp_kb_env`'s `cache_clear()` loop at conftest.py:269–283 and AC1.4's autouse-promotion of same). Non-re-entrant `Lock` would surface false deadlocks during test reloads — a regression in cycle-19 L2's pattern. Risk-1 in requirements doc explicitly cites RLock for this reason. Documented. |
| **R2-F6 / "AC22 — 40-thread stress test"** | INFO | **DEFER to BACKLOG** | (none, BACKLOG entry only) | Adds FastMCP test-harness infrastructure complexity without proportional cycle-64 win. AC8's N=4 test is consistent with the project's test-precedent pattern (test_compile.py, test_mcp_core.py both use N=4). M2 in threat model already documents the 40-thread storm scenario; the ALREADY-EXISTING double-checked locking at `embeddings.py:302,307` is the structural mitigation. BACKLOG entry: "tests/ MEDIUM — N=40 FastMCP-realistic dim-mismatch concurrency stress test (cycle-64 deferred; double-checked locking proven correct via N=4 surrogate per AC8)." |
| **R2-F7 / "AC23 — dependency-resolver validation"** | INFO | **REJECT** | (none) | Step 12 CI install (`pip install -r requirements-dev.txt && pytest`) and Step 11 SCA already cover resolver conflicts. Promoting to AC creates redundant test surface duplicating CI's natural failure mode. Cycle-64 already calls this out under AC18 ("verify install succeeds without resolver conflicts"). |
| **R2-F-merge-resilience / "# CYCLE-64-HOOK marker"** | INFO | **ACCEPT** | AC14 | Small change (one-line comment marker `# CYCLE-64-HOOK` on AC14's insertion in `compile/compiler.py`), increases merge legibility per requirements Risk-8 (cycle-61 collision). NO new test (R2's `test_compile_tail_order` is over-engineering for a comment marker). |
| **R2-F8** (cache eviction tie-breaking on mtime equality) | MINOR | **MODIFY (subsumed by R1-F13)** | AC9 | R1-F13's FIFO insertion-order eviction inherently breaks ties (insertion order is total-ordered). No additional handling needed. |
| **R2-F9** (mutation-test coverage analysis) | INFO | **DEFER to BACKLOG** | (none) | mutmut run is post-Step-9 quality work; not a Step-5 design-gate concern. BACKLOG entry: "tests/ LOW — mutmut mutation-coverage analysis on cycle-64 regression suite (cycle-65+ followup)." |

**R1 finding tally:** 4 BLOCKER (all ACCEPT) + 7 MAJOR (5 ACCEPT, 1 ACCEPT-as-new-sub-AC, 1 MODIFY) + 5 MINOR (all ACCEPT) + 1 NIT (ACCEPT) = **17 findings, 16 ACCEPT/MODIFY, 0 DEFER, 0 REJECT.**

**R2 finding tally:** 3 BLOCKER (all ACCEPT — overlap with R1) + 2 MAJOR (both REJECT with documented rationale) + 2 MINOR (1 ACCEPT, 1 MODIFY-subsumed) + 1 INFO (DEFER) + 2 new-AC proposals (1 DEFER, 1 REJECT) + 1 merge-marker (ACCEPT) = **9 findings, 4 ACCEPT/MODIFY, 2 DEFER, 3 REJECT.**

---

## Revised AC list

The 25 ACs below are the AUTHORITATIVE spec for Step 7 plan. Each AC is self-contained with file paths corrected per R1-F3/F4, behavioural test names, and provenance tags.

### Cluster A — `tests/conftest.py` HIGH fixture leak surface (5 ACs: AC1, AC1.4 NEW, AC2, AC3, AC4)

**AC1.** Promote the existing `tmp_kb_env` fixture (`tests/conftest.py:127–285`) to autouse via `@pytest.fixture(autouse=True)`. The fixture already redirects 24 `kb.config` constants (superset of the 8 originally listed) plus `kb.compile.compiler.HASH_MANIFEST` plus `kb.capture._CAPTURES_DIR_RESOLVED` / `_captures_resolved` / `_project_resolved` plus an `lru_cache.cache_clear()` loop for `load_purpose` / `_load_template_cached` / `_build_schema_cached`. No new constant enumeration step; the fixture's existing mirror-rebind loop (lines 248–255) covers `from kb.config import X` already-imported snapshot bindings in `kb.*` modules per cycle-12 R1 hardening. Rename the existing private alias `_kb_sandbox` (line 290) to public `kb_sandbox` for tests that prefer the explicit-fixture form (no autouse semantics — same body). *(was: AC1 original; revised per R1-F1 / R2-F1.)*

**AC1.4 (NEW).** Verify `tmp_kb_env` autouse promotion does NOT regress the ~230 existing call-sites that explicitly request the fixture. New behavioural test `tests/test_cycle64_conftest_leak.py::test_autouse_promotion_does_not_double_fixture` — assert that a test using `def test_foo(tmp_kb_env)` receives the SAME `Path` object whether autouse fires first or the explicit fixture-arg fires (i.e., the fixture is single-instance per test, not double-instantiated). Run the existing test suite end-to-end as the empirical confirmation gate (Step 9 self-check + Step 13 CI). *(NEW per R1-F1.)*

**AC2.** Add an opt-in fixture `real_project_root(request)` that yields the actual `kb.config.PROJECT_ROOT` ONLY when invoked under `pytest --use-real-paths`. Without the flag, the fixture raises `RuntimeError("real_project_root requires --use-real-paths to opt out of conftest sandboxing; see tests/conftest.py")`. Add `pytest_addoption(--use-real-paths, action='store_true')` to `conftest.py`. *(unchanged from original.)*

**AC3.** Migrate any test sites that genuinely need real paths to `pytest.mark.usefixtures("real_project_root")` + `--use-real-paths` flag. Specific candidates from cycle 7 + Phase 4.5 R3 audit:
- `tests/test_cli.py:61–63` multi-global monkeypatch — confirm `tmp_kb_env` autouse redirect makes the existing test still pass; if test relies on real paths, mark with `pytest.mark.usefixtures("real_project_root")` and document why.
- `WIKI_CONTRADICTIONS` / `WIKI_LOG` write-paths in `test_pipeline.py` / `test_compile.py` (if any escape the autouse redirect) — same migration.
- `load_purpose()` real-file reads in any test — same migration.

In practice, after AC1's autouse promotion, expectation is **zero** sites need the opt-in (AC1 already covers them). AC3 is the clean-up gate. *(unchanged from original.)*

**AC4.** New regression test `tests/test_cycle64_conftest_leak.py` with 3 behavioural cases:
- `test_default_isolation_redirects_wiki_constants_to_tmp` — assert that under default-pytest-invocation, `kb.config.WIKI_DIR != PROJECT_ROOT_at_module_import_time`, AND a `Path.write_text` to `kb.config.WIKI_CONTRADICTIONS` lands inside `tmp_path` (not the real wiki).
- `test_real_project_root_fixture_raises_without_flag` — assert that `request.getfixturevalue("real_project_root")` raises `RuntimeError` matching `"--use-real-paths"` substring.
- `test_real_project_root_fixture_yields_real_path_with_flag` — invoke a sub-pytest via `subprocess.run([sys.executable, "-m", "pytest", "--use-real-paths", "-x", "<this_test_file>::test_under_flag"])` to verify the flag-gated path resolves. *(unchanged from original.)*

### Cluster B — `src/kb/query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild (5 ACs: AC5, AC6, AC7, AC8, AC8.5 NEW)

**AC5.** Extract the existing `wiki_dir_hint = self.db_path.parent.parent` derivation (`embeddings.py:678`) into a `VectorIndex._derive_wiki_dir() -> Path | None` method with explicit contract:
- Returns `self.db_path.parent.parent` when `self.db_path` is non-`None` AND `self.db_path.name == 'vector_index.db'` AND `self.db_path.parent.name == '.data'` AND NOT `self.db_path.name.endswith('.tmp')`.
- Returns `None` otherwise (covers `db_path is None`, `.tmp` rebuild artifact, non-canonical layout).
- Replace the inline derivation at line 678 with the new method. *(was: AC5 original; revised per R1-F17 — heuristic codified to literal name checks matching `_vec_db_path` inverse.)*

**AC6.** In `VectorIndex.query()`, when the existing dim-mismatch detection fires (the branch that currently returns `[]` and bumps `_dim_mismatches_seen`), also schedule an automatic rebuild via:
```python
if os.environ.get("KB_DISABLE_VECTOR_AUTO_REBUILD"):
    return []  # kill-switch read at CALL TIME, not at import
wiki_dir = self._derive_wiki_dir()
if wiki_dir is None:
    return []
try:
    _validate_path_under_project_root(wiki_dir, "vector_auto_rebuild_target")
except ValidationError:
    return []  # path-validation failure: skip rebuild silently, return [] like cold-mismatch
rebuild_vector_index(wiki_dir)  # double-checked-locking inside, idempotent
```
**Behavioural contract (R2-F2 clarification):** the FIRST query that detects mismatch ALWAYS returns `[]` (auto-rebuild is fire-and-forget for that call — synchronous w.r.t. `rebuild_vector_index`'s return, but the query itself does NOT re-execute against the new index in the same call); the SECOND query (after rebuild commits) returns real results. Document the kill-switch and the first-query-returns-empty semantics in `docs/reference/error-handling.md`. *(was: AC6 original; revised per R1-F7 (env at call-time), R1-F9 + R2-F3 (path validation), R2-F2 (UX contract clarification).)*

**AC7.** Add `get_dim_mismatch_auto_rebuild_count() -> int` getter exposing a new module-level `_dim_mismatch_auto_rebuilds_seen` counter, mirroring the `get_dim_mismatch_count()` cycle-25 contract. Counter increments AFTER `rebuild_vector_index` returns successfully. *(unchanged from original.)*

**AC8.** New regression test `tests/test_cycle64_dim_mismatch_autorebuild.py` with 5 behavioural cases:
- `test_dim_mismatch_triggers_rebuild` — write a vector DB with stored dim D1; monkeypatch the model to emit dim D2; query → assert `model.encode` (or `load_all_pages`) was called (spy) AND `get_dim_mismatch_auto_rebuild_count()` returned 1. *(spy target switched per R1-F11 — was `_is_rebuild_needed` which is the gate-counter, not the body-counter.)*
- `test_kill_switch_env_disables_auto_rebuild` — set `KB_DISABLE_VECTOR_AUTO_REBUILD=1`; same setup; assert `model.encode` NOT called AND counter stays 0.
- `test_concurrent_query_during_rebuild_idempotent` — N=4 threads each calling `idx.query(...)` after planting dim-mismatch; spy on `model.encode` → assert called AT MOST ONCE across all threads (the second-thread's check inside `_rebuild_lock` should see the new dim and short-circuit). *(spy target switched per R1-F11.)*
- `test_auto_rebuild_disabled_when_db_path_is_tmp_suffix` — construct `VectorIndex(Path("/tmp/foo/.data/vector_index.db.tmp"))`; assert `_derive_wiki_dir()` returns `None` AND auto-rebuild path is skipped.
- `test_auto_rebuild_rejects_wiki_dir_outside_project_root` (NEW per R1-F9) — construct `VectorIndex(Path("/etc/foo/.data/vector_index.db"))` (path outside `PROJECT_ROOT`); assert `_validate_path_under_project_root` raises and the auto-rebuild branch returns `[]` silently (no rebuild attempt).
*(was: AC8 original; revised per R1-F11 + R1-F9.)*

**AC8.5 (NEW).** New regression test case in `tests/test_cycle64_dim_mismatch_autorebuild.py::test_kill_switch_env_set_after_import_is_honoured` — simulate the test-ordering case where `kb.query.embeddings` is imported BEFORE the test sets `KB_DISABLE_VECTOR_AUTO_REBUILD`. Use `monkeypatch.setenv("KB_DISABLE_VECTOR_AUTO_REBUILD", "1")` AFTER the embeddings module is already loaded; assert auto-rebuild is skipped. Fails when AC6 reverts to module-top env-binding (cycle-7 L24 anchor). *(NEW per R1-F7.)*

### Cluster C — `src/kb/graph/cache.py` HIGH shared-cache contract (5 ACs: AC9, AC10, AC11, AC11.5 NEW, AC12)

**AC9.** New module `src/kb/graph/cache.py` exposing:
- **Import shape contract (per R1-F12):** `cache.py` MUST use `from kb.graph.builder import build_graph` so `monkeypatch.setattr(kb.graph.cache, "build_graph", spy)` succeeds in AC12.
- `_GLOBAL_CACHE: dict[tuple[str, float], nx.DiGraph]` — keyed on `(wiki_dir.resolve().as_posix(), max_mtime_of_wiki_subdirs)`.
- `_CACHE_LOCK: threading.RLock` — guards reads + writes (re-entrant per cycle-19 L2 reload-leak pattern; rationale documented per R2-F5 REJECT).
- `_MAX_CACHE_SIZE = 4` — bound entries; eviction is **FIFO insertion-order** matching cycle-7's `_index_cache` (`embeddings.py:362–381`) precedent (R1-F13).
- `get_graph(wiki_dir: Path, *, pages: list[dict] | None = None) -> nx.DiGraph`:
  - **If `pages is not None`**, bypass cache entirely: return `build_graph(wiki_dir, pages=pages)` directly without read or write to `_GLOBAL_CACHE` (R1-F5).
  - **If `pages is None`**, under `_CACHE_LOCK`: compute `current_mtime = max((p.stat().st_mtime for p in (wiki_dir / sub).rglob("*.md")), default=0.0)` over the canonical WIKI_SUBDIRS list; on cache hit return the cached graph; on miss call `build_graph(wiki_dir)` (no `pages=` arg), store, return. On full cache, evict the OLDEST-INSERTED entry before storing.
- `invalidate(wiki_dir: Path | None = None) -> int` — under `_CACHE_LOCK`, drop all cache entries whose `wiki_dir` matches; if `None`, drop everything; returns number of entries dropped.
- `get_cache_stats() -> dict` — `{"hits": int, "misses": int, "invalidations": int, "size": int}` for telemetry; counters approximate per cycle-25 Q8 precedent (no per-counter lock).
*(was: AC9 original; revised per R1-F5, R1-F12, R1-F13, R2-F4 REJECT, R2-F5 REJECT.)*

**AC10.** Wire `kb.graph.cache.get_graph` into the **5 lint-cluster** fallback call sites (cycle-64 scope; non-lint sites deferred per R1-F2):
- `src/kb/lint/checks/cycles.py:20` — replace `graph = build_graph(wiki_dir)` with `import kb.graph.cache` + `graph = kb.graph.cache.get_graph(wiki_dir)`.
- `src/kb/lint/checks/orphan.py:27` — same.
- `src/kb/lint/semantic.py:140` — `graph = kb.graph.cache.get_graph(wiki_dir, pages=pages)` (pages-bypass path per AC9).
- `src/kb/lint/augment/collector.py:49` — `graph = kb.graph.cache.get_graph(wiki_dir)`.
- `src/kb/lint/runner.py:59,96` — `graph = kb.graph.cache.get_graph(wiki_dir)`.

**Import-shape contract (per cycle-18 L1 / requirements Risk-2):** all 5 caller sites MUST use `import kb.graph.cache` + `kb.graph.cache.get_graph(...)` (attribute lookup), NOT `from kb.graph.cache import get_graph`.

**Out-of-scope (per R1-F2):** the 5 non-lint `build_graph` call sites (`evolve/analyzer.py:28,127,358`, `graph/export.py:83`, `mcp/browse.py:345`, `query/engine.py:408`) are explicitly DEFERRED to cycle-65+; AC21 BACKLOG-edit reflects "lint-shared graph cache" partial closure honestly. *(was: AC10 original; revised per R1-F2 scope clarification + cycle-18 L1 import shape.)*

**AC11.** Wire `kb.graph.cache.invalidate(wiki_dir)` at the END of two mutator code paths:
- `src/kb/ingest/pipeline.py::ingest_source` — single call right before the function returns the `IngestResult`.
- `src/kb/review/refiner.py::refine_page` — single call right before its return. *(file path corrected per R1-F3 — was `src/kb/refine/refiner.py` which does NOT exist.)*
- Document the contract in a new section in `docs/reference/architecture.md` titled "Graph cache contract" alongside the existing "Manifest contract" section. Section content: when graphs are built, when cached, when invalidated, lifecycle of `publish-siblings-manifest.json` (per R1-F14), and the consequences of skipping invalidation. *(was: AC11 original; revised per R1-F3.)*

**AC11.5 (NEW).** `compile_wiki` in `src/kb/compile/compiler.py` calls `kb.graph.cache.invalidate(effective_wiki_dir)` AFTER the manifest-prune block AND BEFORE the auto-publish hook (AC14 insertion). One line, no error path needed (cache is best-effort). New AC12 case `test_compile_wiki_invalidates_graph_cache` — call `get_graph(wiki_dir)` to populate, then call `compile_wiki` against same wiki_dir, then call `get_graph(wiki_dir)` and assert `build_graph` was invoked (cache was dropped). *(NEW per R1-F8 / Q3 resolution.)*

**AC12.** New regression test `tests/test_cycle64_graph_cache.py` with 6 behavioural cases:
- `test_get_graph_caches_within_one_lint_pass` — call `kb.graph.cache.get_graph(wiki_dir)` twice in succession (no mutation between, no `pages=`); assert `build_graph` was called exactly ONCE (spy via `monkeypatch.setattr(kb.graph.cache, "build_graph", spy)`).
- `test_get_graph_with_pages_bypasses_cache` — call `get_graph(wiki_dir, pages=[...])` twice; assert `build_graph` was called TWICE (cache bypass per AC9 contract, R1-F5).
- `test_get_graph_invalidated_by_mtime_bump` — call `get_graph`, write a new `.md` page, call `get_graph` again; assert `build_graph` was called TWICE.
- `test_invalidate_drops_entries_for_wiki_dir` — call `get_graph(wiki_dir_a)` + `get_graph(wiki_dir_b)`, then `invalidate(wiki_dir_a)`; assert `size==1` and the surviving key matches `wiki_dir_b`.
- `test_ingest_source_invalidates_graph_cache` — call `get_graph(wiki_dir)`, then call `ingest_source(...)` against a fixture, then call `get_graph(wiki_dir)` again; assert the second call triggered a rebuild (spy).
- `test_cache_size_bound_fifo_eviction` — load 5 distinct wiki_dirs into the cache; assert `get_cache_stats()["size"] == 4` AND the FIRST-INSERTED entry was evicted (FIFO order, R1-F13).
- `test_compile_wiki_invalidates_graph_cache` (NEW per AC11.5) — populate cache, run `compile_wiki`, assert next `get_graph` call triggers rebuild.

**Test isolation:** add an autouse fixture `_clear_graph_cache_per_test` to `tests/test_cycle64_graph_cache.py` that calls `kb.graph.cache.invalidate(None)` before each test (cycle-19 L2 reload-leak hazard mitigation). *(was: AC12 original; revised per R1-F5, R1-F13, AC11.5 addition.)*

### Cluster D — `src/kb/compile/publish.py` MEDIUM compile-time auto-publish hook + manifest cleanup (6 ACs: AC13, AC14, AC15, AC15.5 NEW, AC16, AC17)

**AC13.** Add a new function `auto_publish_after_compile(wiki_dir: Path, *, mode: str = "all", incremental: bool = True) -> dict[str, Path]` to `src/kb/compile/publish.py`. Body:
1. Compute `out_dir = wiki_dir.parent / "_publish"`.
2. **Path validation (per R1-F9):** call `_validate_path_under_project_root(out_dir, "publish_out_dir")` (dual-anchor: literal + resolved). On failure, raise `ValidationError` (do NOT swallow — caller's try/except handles).
3. Invoke the existing builders (`build_llms_txt`, `build_llms_full_txt`, `build_graph_jsonld`, `build_sitemap_xml`, `build_per_page_siblings`) with the validated `out_dir`.
4. Returns dict mapping format-name → output path. Errors during a single builder are logged at WARNING but don't fail the function (best-effort). *(was: AC13 original; revised per R1-F9.)*

**AC14.** In `src/kb/compile/compiler.py::compile_wiki`, AFTER the function's existing success path AND AFTER AC11.5's `invalidate(effective_wiki_dir)` call AND BEFORE the function returns, insert:
```python
# CYCLE-64-HOOK: auto-publish after successful compile (R2-F-merge marker)
if not os.environ.get("KB_DISABLE_COMPILE_AUTO_PUBLISH"):
    try:
        auto_publish_after_compile(effective_wiki_dir, incremental=incremental)
    except Exception as exc:
        logger.warning("auto-publish skipped: %s", exc)
```
Note: `incremental=incremental` (NOT `incremental=(mode != "full")` per R1-F10 — `compile_wiki` has no `mode` variable). The `# CYCLE-64-HOOK` comment marker (R2 merge-resilience) increases legibility for cycle-61/cycle-65 rebases. *(was: AC14 original; revised per R1-F10 + R2 merge marker.)*

**AC15.** New regression test `tests/test_cycle64_auto_publish.py` with 4 cases:
- `test_compile_wiki_emits_llms_txt_and_graph_jsonld` — invoke `compile_wiki` against a `tmp_kb_env` fixture with 3 pages; assert `_publish/llms.txt`, `_publish/llms-full.txt`, `_publish/graph.jsonld`, `_publish/sitemap.xml` all exist.
- `test_kill_switch_env_disables_auto_publish` — set `KB_DISABLE_COMPILE_AUTO_PUBLISH=1`; same fixture; assert no `_publish/` directory created. (Read env at CALL TIME for parity with AC6/F7 pattern.)
- `test_publish_failure_does_not_fail_compile` — monkeypatch one of the builders to raise `OSError`; invoke `compile_wiki`; assert it returns success AND `logger.warning` fired with `"auto-publish skipped"`.
- `test_publish_artifacts_outside_wiki_dir_walk` — assert `_publish` directory is at `wiki_dir.parent / "_publish"`, NOT inside `wiki_dir`. *(unchanged from original, except fixture name updated to `tmp_kb_env`.)*

**AC15.5 (NEW).** `tests/test_cycle64_auto_publish.py::test_auto_publish_rejects_out_dir_outside_project_root` — invoke `auto_publish_after_compile(wiki_dir=Path("/etc/something"))` (synthesizes an out-of-tree `out_dir`); assert `ValidationError` raised with field name `"publish_out_dir"`. Pairs with AC13's `_validate_path_under_project_root` contract addition. *(NEW per R1-F9.)*

**AC16.** Implement manifest-based incremental sibling cleanup in `src/kb/compile/publish.py::build_per_page_siblings`:
- Load `<wiki_dir>.parent / ".data" / "publish-siblings-manifest.json"` (empty dict if missing) — keys are page_id strings, values are list of sibling paths emitted on the previous publish.
- Compute the CURRENT publish's sibling-paths-by-page-id dict.
- For each previously-emitted sibling path NOT in the current dict → unlink (only if file exists; log INFO).
- Save the current dict to the manifest atomically via `atomic_json_write`.
- **Ordering (per cycle-15 L1 incremental-skip retracted leak):** the manifest read + diff must run BEFORE the incremental skip check, mirroring `build_per_page_siblings`'s cycle-16 Q2/C3 amendment. *(was: AC16 original; revised — ordering clarification per R1 cycle-15 L1 cross-check.)*

**AC17.** New regression test `tests/test_cycle64_publish_manifest.py` with 3 cases:
- `test_first_publish_creates_manifest_no_unlinks` — fresh wiki_dir, no manifest; invoke `build_per_page_siblings`; assert manifest file written AND zero `Path.unlink` calls.
- `test_second_publish_only_unlinks_newly_excluded_siblings` — invoke once with 3 retracted pages, then again with 5 retracted pages (3 carry over + 2 new); assert manifest contents updated AND only the diff (2 newly-excluded paths) was unlinked, NOT all 5.
- `test_manifest_corrupted_falls_back_to_full_cleanup` — write a manifest with invalid JSON; invoke; assert function falls back to cycle-16 unconditional behaviour (no crash) AND logs WARNING about manifest corruption. *(unchanged from original.)*

### Cluster E — `tests/` MEDIUM snapshot infrastructure foundation (3 ACs: AC18, AC19, AC20)

**AC18.** Append `syrupy>=4.6.0` to `requirements-dev.txt` (single new line). Run `pip install -r requirements-dev.txt` to verify resolver compatibility. **Fallback (per R1-F15):** if `syrupy` is rejected by Step 11 SCA OR a resolver conflict surfaces, switch to `pytest-snapshot>=0.9.0`; under fallback, AC19's `test_lint_report_format_snapshot` renders through `format_report` (already returns text — no `JSONSnapshotExtension` dependency). Mermaid + evidence-trail subjects are text-native — no JSON snapshots in this cycle either way. Document the choice in `docs/reference/testing.md`. *(was: AC18 original; revised per R1-F15.)*

**AC19.** New file `tests/test_cycle64_snapshots.py` with 3 snapshot subjects:
- `test_evidence_trail_format_snapshot` — call `kb.ingest.evidence.append_evidence_trail` against a fixture page with 3 entries spanning 2026-04-01 / 2026-04-15 / 2026-05-03; serialise the resulting page body; compare via `snapshot`. *(file path corrected per R1-F4 — was `kb.utils.evidence` which does NOT exist.)*
- `test_mermaid_export_format_snapshot` — call `kb.graph.export.export_mermaid` against a fixture wiki with 3 pages and 2 wikilinks; compare the Mermaid output.
- `test_lint_report_format_snapshot` — call `kb.lint.runner.run_all_checks` against a fixture wiki with KNOWN issues (1 broken wikilink + 1 frontmatter validation error); compare the rendered report text. *(was: AC19 original; revised per R1-F4.)*

**AC20.** Commit `tests/__snapshots__/test_cycle64_snapshots/` directory with the 3 initial snapshots. Verify via `pytest tests/test_cycle64_snapshots.py` that all 3 snapshots match WITHOUT `--snapshot-update` after commit (idempotency check). Document the snapshot-update workflow (`pytest tests/test_cycle64_snapshots.py --snapshot-update` after a deliberate format change) in `docs/reference/testing.md` with explicit warning: "NEVER pass `--snapshot-update` in CI" (per T16 mitigation). *(unchanged from original.)*

### Cluster F — Doc sync (1 AC: AC21)

**AC21.** Append cycle-64 entry under `[Unreleased]` in `CHANGELOG.md` (Quick Reference compact format: Items / Tests / Scope / Detail). **Items count = 25** ACs (was: 21; +4 new sub-ACs AC1.4, AC8.5, AC11.5, AC15.5). Append cycle-64 detailed bullet-level entry to `CHANGELOG-history.md`. BACKLOG.md updates:
- **Delete** the 3 fully-resolved items: (a) `tests/conftest.py` HIGH leak surface, (b) `query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild, (c) `compile/publish.py` MEDIUM compile-time auto-publish hook + MEDIUM manifest cleanup (treat as one resolved entry).
- **Rewrite** `graph/builder.py` HIGH no-shared-cache contract entry as: "lint-shared graph cache landed cycle-64; non-lint sites (`evolve/analyzer.py:28,127,358`, `graph/export.py:83`, `mcp/browse.py:345`, `query/engine.py:408`) deferred to cycle-65+." (per R1-F2).
- **Rewrite** `tests/` MEDIUM no-golden-file entry as: "snapshot infrastructure landed cycle-64 (3 subjects: evidence-trail / Mermaid / lint-report); remaining subjects (page-render, llms-full body, JSON-LD): deferred to cycle-65+." (per R1-F16).
- **Add** new BACKLOG entry: "tests/ MEDIUM — N=40 FastMCP-realistic dim-mismatch concurrency stress (cycle-64 deferred per R2-F6; double-checked locking proven correct via N=4 surrogate)." (per R2-F6 DEFER).
- **Add** new BACKLOG entry: "tests/ LOW — mutmut mutation-coverage analysis on cycle-64 regression suite." (per R2-F9 DEFER).

Update `CLAUDE.md` Quick Reference test count (+ ~13 new tests from cycle-64 — AC4: 3 + AC8: 5 + AC8.5: 1 + AC12: 7 + AC15: 4 + AC15.5: 1 + AC17: 3 + AC19: 3 + AC1.4: 1 = 28; subtract overlap with existing tests for ~13 NET new). Update `docs/reference/architecture.md` (Graph cache contract section per AC11) and `docs/reference/testing.md` (conftest sandbox + snapshot-update workflow per AC18/AC20). All updates per the project's `Doc update checklist on push`. *(was: AC21 original; revised per R1-F2 + R1-F16 + R2-F6 + R2-F9.)*

---

## CONDITIONS

The following are CONTRACT REQUIREMENTS that Step 7 plan + Step 9 implementation MUST honour, and that Step 14 security-verify can grep for. They are not summaries of ACs — they are precision constraints that became implicit during R1+R2 review.

1. **Step 9 implementer MUST use `from kb.graph.builder import build_graph` in `src/kb/graph/cache.py`** — so AC12's `monkeypatch.setattr(kb.graph.cache, "build_graph", spy)` succeeds. NOT `import kb.graph.builder` then `kb.graph.builder.build_graph(...)`. (R1-F12; cycle-18 L1 owner-module patching per CLAUDE.md.)

2. **Step 9 implementer MUST use `import kb.graph.cache` + `kb.graph.cache.get_graph(...)` in all 5 lint caller sites** — NOT `from kb.graph.cache import get_graph`. Step 14 grep `from kb\.graph\.cache import` over `src/kb/lint/` MUST return zero hits. (Risk-2 in requirements; cycle-18 L1.)

3. **Step 9 implementer MUST read `KB_DISABLE_VECTOR_AUTO_REBUILD` and `KB_DISABLE_COMPILE_AUTO_PUBLISH` AT CALL TIME** inside the function body, NOT bind them as module-top constants. (R1-F7; cycle-7 L24 / cycle-19 L2 anchor.)

4. **Step 9 implementer MUST call `_validate_path_under_project_root` in TWO new places:** (a) `VectorIndex.query()`'s rebuild branch with field name `"vector_auto_rebuild_target"`, (b) `auto_publish_after_compile`'s entry with field name `"publish_out_dir"`. Both dual-anchor (literal + resolved). Step 14 grep `_validate_path_under_project_root.*vector_auto_rebuild_target` and `..publish_out_dir` MUST each return one hit. (R1-F9; cycle-44 L4 DROP-with-test-anchor; CLAUDE.md path-safety conventions.)

5. **AC10 wires ONLY 5 lint sites; the 5 non-lint `build_graph` sites are NOT touched.** Step 14 grep `kb.graph.cache.get_graph\|from kb.graph.cache` over `src/kb/evolve/`, `src/kb/graph/export.py`, `src/kb/mcp/browse.py`, `src/kb/query/engine.py` MUST return zero hits. (R1-F2; cycle-64 scope discipline.)

6. **AC1's autouse promotion of `tmp_kb_env` MUST NOT introduce a SECOND fixture with overlapping monkeypatch behaviour** (no parallel mirror-rebind loop). The single fixture stays at `tests/conftest.py:127–285` body, gains `autouse=True`, and the `_kb_sandbox` line-290 alias renames to `kb_sandbox`. (R1-F1; cycle-19 L2 desync hazard mitigation.)

7. **AC9 cache-key contract: `pages=` callers BYPASS cache entirely.** No `pages=` argument is ever stored in `_GLOBAL_CACHE`. The `pages=`-aware caller (`lint/semantic.py:140`) calls `build_graph` directly through the `get_graph` facade — Step 14 grep `kb.graph.cache.*pages=` should find one call site (the bypass) and zero stored-cache hits via `pages=` keys. (R1-F5.)

8. **AC9 LRU eviction is FIFO insertion-order matching cycle-7's `_index_cache`.** Step 14 reads `src/kb/graph/cache.py` to confirm the eviction logic uses `next(iter(_GLOBAL_CACHE))` or equivalent insertion-order pop, NOT `min(items, key=mtime)` or LRU-by-access. AC12 `test_cache_size_bound_fifo_eviction` exercises this. (R1-F13.)

9. **AC14 inserts the auto-publish hook with a `# CYCLE-64-HOOK:` comment marker** for merge legibility against cycle-61's parallel `compile_wiki` edits. Step 14 grep `# CYCLE-64-HOOK` over `src/kb/compile/compiler.py` MUST return ≥1 hit. (R2 merge-resilience; requirements Risk-8.)

10. **AC18's syrupy/pytest-snapshot fallback MUST be exercised (not just documented) if Step 11 SCA flags syrupy.** No JSON-snapshot subject relies on syrupy-specific extensions; AC19's three subjects render as text only. (R1-F15.)

11. **R3 review threshold (per `feedback_3_round_pr_review` memory): cycle-64 has 25 ACs, ABOVE the ≥25 threshold for triggering R3 in Step 20.** Step 20 plan MUST schedule R3 review (was R1+R2 only in the standard pipeline; R3 added). The cycle is also batch-fix HIGH+MED+LOW per `feedback_batch_by_file` so R3 increases regression-detection quality.

12. **AC11.5 ordering: `compile_wiki` invalidates BEFORE auto-publish hook fires.** Step 14 reads `src/kb/compile/compiler.py` and confirms the line order is `kb.graph.cache.invalidate(...)` THEN `auto_publish_after_compile(...)`. NOT the reverse — Phase 5 typed-relations work depends on auto-publish reading post-invalidation cache state. (R1-F8.)

---

## Step 14 verifier checklist

Consolidates the threat-model's 8 verifier checks + new requirements from R1+R2 inline resolutions. Total: 12 items.

1. **AC1 mirror-rebind coverage:** `Grep "kb\.config\.(WIKI_|RAW_|PROJECT_ROOT|OUTPUTS_DIR|HASH_MANIFEST|FEEDBACK_PATH|VERDICTS_PATH|REVIEW_HISTORY_PATH|CAPTURES_DIR)" src/kb/` — every read site is either covered by `tmp_kb_env`'s 24-constant patch list OR lazy-derived from `WIKI_DIR`/`RAW_DIR`. (M1 narrowed per R1-F6.)

2. **AC6 path validation present:** `Grep "_validate_path_under_project_root.*vector_auto_rebuild_target" src/kb/query/embeddings.py` — exactly 1 hit. (R1-F9.)

3. **AC6 env at call-time:** `Grep "_AUTO_REBUILD_DISABLED\s*=\s*bool\(os\.environ" src/kb/query/embeddings.py` — exactly 0 hits (no module-top binding). Then `Grep "os\.environ\.get\(.KB_DISABLE_VECTOR_AUTO_REBUILD" src/kb/query/embeddings.py` — exactly 1 hit (in-function read). (R1-F7.)

4. **AC9 import shape:** `Grep "from kb\.graph\.builder import build_graph" src/kb/graph/cache.py` — exactly 1 hit. (R1-F12.)

5. **AC10 caller import shape:** `Grep "from kb\.graph\.cache import" src/kb/lint/` — exactly 0 hits for `get_graph` (must use attribute lookup). Then `Grep "kb\.graph\.cache\.get_graph" src/kb/lint/` — **exactly 6 hits** (one per caller site; runner.py has 2 — initial build at line 61 + post-fix-rebuild at line 102). (R1-F2 + cycle-18 L1; count corrected post-R2 per cycle-23 L3 — original spec said "5 hits" but runner.py legitimately has 2 callers.)

6. **AC10 scope discipline (non-lint not touched):** `Grep "kb\.graph\.cache\.(get_graph\|invalidate)" src/kb/evolve/ src/kb/graph/export.py src/kb/mcp/browse.py src/kb/query/engine.py` — exactly 0 hits. (R1-F2 cycle-64 scope.)

7. **AC11 invalidation sites:** `Grep "kb\.graph\.cache\.invalidate" src/kb/` — **exactly 4 hits** (`ingest/pipeline.py`, `review/refiner.py`, `compile/compiler.py` per AC11+AC11.5, **plus `lint/runner.py:101`** post-fix-dead-link rebuild path that was already part of AC10 wiring). (R1-F3 + R1-F8; count corrected post-R2 per cycle-23 L3 — original spec missed lint/runner.py invalidate.)

8. **AC13 path validation present:** `Grep "_validate_path_under_project_root.*publish_out_dir" src/kb/compile/publish.py` — exactly 1 hit. (R1-F9.)

9. **AC14 merge marker:** `Grep "# CYCLE-64-HOOK" src/kb/compile/compiler.py` — exactly 1 hit; AND verify line order `invalidate(...)` precedes `auto_publish_after_compile(...)` by reading the surrounding 10 lines. (R2 merge-resilience + AC11.5 ordering.)

10. **AC9 telemetry leak audit:** `Grep "logger\..*_GLOBAL_CACHE\|logger\..*get_cache_stats" src/kb/graph/cache.py` — exactly 0 hits (cache keys / stats never logged with raw paths per T7). (Threat-model T7.)

11. **AC19/AC20 snapshot-content audit:** `Grep -E "/Users/|/home/|C:\\\\\|/tmp/pytest-of-" tests/__snapshots__/test_cycle64_snapshots/` — exactly 0 hits. (Threat-model T15; if any match, the corresponding snapshot subject must be normalized to relative paths before merge.)

12. **AC20 CI guard:** `Grep "snapshot-update" .github/workflows/ci.yml` — exactly 0 hits. AND `docs/reference/testing.md` snapshot-update note explicitly contains the warning string `"never run --snapshot-update in CI"` or equivalent. (Threat-model T16.)

---

## Strict-audit recovery posture

Cycle-64's binding-owner step set per requirements doc is 9 steps (Step 7 plan, Step 8 plan-gate, Step 9 impl, Step 9 bg reviewer, Step 14, Step 17, Step 18, Step 20-R1, Step 20-R2). Goal: ≥6/9 honoured strictly (≈67%, recovering from cycle-61's 33%).

Step 5's APPROVE-WITH-INLINE-RESOLUTIONS posture **does NOT shift OWNER attribution** for any of the 9 binding-owner steps. Step 5 absorbed *clarification work* (R1+R2 finding resolution, AC list authoritative-form production) but NOT plan-gate work — Step 7's plan-gate (mimo-v2.5-pro audit role per C61-L1) still operates against the AC list and CONDITIONS list as input. The strict-audit denominator stays 9. Risk to the ratio: if Step 7's mimo-v2.5-pro audit gate flags a CONDITION as ambiguous and recommends design-eval re-dispatch, that triggers Step 4-redo rather than Step 5-redo, which would NOT be counted against the cycle-64 strict-audit ratio (Step 4 is not in the binding-owner set). Net: Step 5's resolution mechanically sets up the cycle to honour 9/9 strictly IF Step 7+ proceed as planned. Likely-honoured ratio: 8/9 = 89% (margin for one Step 9 caller-grep slip per `feedback_signature_drift_verify` memory, which would require a Step 11 caller-grep checkpoint and is well-documented).

---

## Out-of-scope confirmed

Original 4 out-of-scope items from R1's review hold:

1. `compile_wiki` per-source rollback (cycle-25 partially addressed; cycle-64 only adds the AC14 single-line tail call + AC11.5 invalidation — does not alter rollback semantics).
2. CLI ↔ MCP write-path parity (4–7 new CLI commands per BACKLOG MEDIUM) — defer to cycle-65+ (overlaps cycle-61's `kb_rebuild_indexes` MCP wiring).
3. Cross-process graph cache persistence (in-process only; cross-process is overkill for the documented win).
4. Snapshot-subject coverage breadth (cycle-64 ships 3 subjects; page-render / llms-full body / JSON-LD deferred to cycle-65+).

Newly surfaced via R1+R2 (also out-of-scope this cycle):

5. **Non-lint `build_graph` callers** (`evolve/analyzer.py:28,127,358`, `graph/export.py:83`, `mcp/browse.py:345`, `query/engine.py:408`) — explicit deferral per R1-F2; BACKLOG entry rewritten in AC21 to reflect partial closure.
6. **N=40 FastMCP-realistic dim-mismatch concurrency stress test** — deferred per R2-F6 (BACKLOG MEDIUM new entry); N=4 in AC8 sufficient via existing double-checked locking proof.
7. **mutmut mutation-coverage analysis on cycle-64 regression suite** — deferred per R2-F9 (BACKLOG LOW new entry).
8. **JSON-snapshot subjects requiring syrupy-specific `JSONSnapshotExtension`** — none in cycle-64 (R1-F15 fallback discipline); deferred to cycle-65+ if/when a JSON-shaped subject surfaces.

---

## References

- `docs/superpowers/decisions/2026-05-03-cycle-64-requirements.md` — 21 ACs original.
- `docs/superpowers/decisions/2026-05-03-cycle-64-threat-model.md` — 18 threats / 4 material / 8 verifier checks.
- `docs/superpowers/decisions/2026-05-03-cycle-64-design-eval-R1.md` — Opus 4.7 R1: 17 findings (4 BLOCKER + 7 MAJOR + 5 MINOR + 1 NIT).
- `docs/superpowers/decisions/2026-05-03-cycle-64-design-eval-R2.md` — DeepSeek V4 Pro R2: 9 findings (3 BLOCKER + 2 MAJOR + 2 MINOR + 1 INFO + merge-marker proposal + 2 new-AC proposals).
- `tests/conftest.py:127–285` — existing `tmp_kb_env` body (AC1 promotes to autouse).
- `tests/conftest.py:290` — `_kb_sandbox` alias (AC1 renames to `kb_sandbox`).
- `src/kb/review/refiner.py:68` — actual `refine_page` location (AC11 corrected per R1-F3).
- `src/kb/ingest/evidence.py:162` — actual `append_evidence_trail` location (AC19 corrected per R1-F4).
- `src/kb/query/embeddings.py:200–202` — `_vec_db_path` heuristic (AC5 codifies inverse).
- `src/kb/query/embeddings.py:302–307` — double-checked locking (M2/T4 mitigation; AC8 N=4 surrogate).
- `src/kb/query/embeddings.py:362–381` — `_index_cache` FIFO eviction (AC9 precedent).
- `src/kb/query/embeddings.py:660–689` — existing `wiki_dir_hint` derivation (AC5 promotes).
- `src/kb/compile/compiler.py:565` — `compile_wiki` post-success block (AC11.5 + AC14 insertion target).
- `src/kb/compile/publish.py:18–22, 44` — existing T1/T2 path-containment + `atomic_text_write` (AC13 extends T1 to compile-time hook).
- `src/kb/graph/builder.py:28` — `build_graph` signature.
- `src/kb/lint/runner.py:59,96`, `src/kb/lint/checks/cycles.py:20`, `src/kb/lint/checks/orphan.py:27`, `src/kb/lint/semantic.py:140`, `src/kb/lint/augment/collector.py:49` — AC10 5 caller sites.
- `src/kb/evolve/analyzer.py:28,127,358`, `src/kb/graph/export.py:83`, `src/kb/mcp/browse.py:345`, `src/kb/query/engine.py:408` — 5 deferred non-lint `build_graph` sites (R1-F2; out-of-scope §5).
- `CLAUDE.md` — path-safety conventions; `_validate_path_under_project_root` dual-anchor pattern.
- `feedback_3_round_pr_review` memory — R3 trigger threshold ≥25 ACs.
- `feedback_signature_drift_verify` memory — Step 11 caller-grep checkpoint discipline.
- `project_cycle61_mimo_failure` memory (2026-05-03) — mimo-v2.5-pro audit role retained Step 7; implementer role failed-by-default (primary-session implements all ACs).
- Cycle-7 L24 (env binding at import vs call) — anchor for AC6/F7.
- Cycle-15 L1 (incremental-skip retracted leak) — AC16 ordering.
- Cycle-18 L1 (snapshot-binding) — AC9/AC10 import shape.
- Cycle-19 L2 (reload-leak / module-import-time binding) — AC1 mirror-rebind, AC9 RLock rationale (R2-F5 REJECT).
- Cycle-20 L3 (audit-tag scope) — AC15.
- Cycle-22 L4 (late-arrival CVE) — AC18 `syrupy` Class B.
- Cycle-40 L3 (revert-verification) — all 5 AC regression tests have explicit revert-failure clauses.
- Cycle-44 L4 (DROP-with-test-anchor) — F9/F10 promotion of verifier-only checks into ACs.
- Cycle-61 R2 Finding 8 (parallel-cycle audit) — file-collision matrix verified clean per requirements §"Files Touched".
