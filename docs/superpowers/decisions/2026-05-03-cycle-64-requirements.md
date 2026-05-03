# Cycle 64 — Requirements + Acceptance Criteria

**Date:** 2026-05-03
**Branch:** `feat/cycle-64` (worktree `D:/Projects/llm-wiki-flywheel/.claude/worktrees/cycle-64`)
**Base:** `main` @ `d7a98b7`
**Author:** Opus 4.7 primary session
**Pipeline:** `dev-mimo-opus` (May 2026 MiMo trial — sixth dispatch cycle on this skill)
**Cycle 61 follow-up posture:** Per `project_cycle61_mimo_failure` memory, treat `mimo-v2.5-pro` as **failed-by-default for implementer role** (Step 7 plan, Step 9 impl) on this codebase; mimo audit role (Step 8 plan-gate) confirmed working in cycle 61 — retain it. Primary-session implements all ACs; mimo-v2.5-pro audits the plan.

---

## Tier

**Tier 2 — standard feature batch.**

Justification (per `dev-mimo-opus` SKILL.md tier classifier):
- Multi-AC fold (21 ACs across 6 file domains)
- Behaviour change (auto-publish hook, dim-mismatch auto-rebuild, conftest sandbox enforcement, graph cache)
- Public API addition (`kb.graph.cache` module; new conftest fixtures)
- **NOT** Tier 3: no auth/authz changes, no crypto, no PII boundary, no irreversible migration, no signing-key change, no deploy-pipeline change. The conftest sandbox-enforcement work has a *security-adjacent* flavour (preventing test leakage to production paths) but operates entirely within the test process's `tmp_path` boundary — it doesn't touch any trust boundary at runtime.

Steps: full pipeline 1–24. Mandatory human gates: none (Tier 2 default). Auto-merge: yes after Step 21.

**Strict-audit ratio target (per C59-L4 tier-aware denominator):** Tier-2 binding-owner steps in this cycle = 7, 8, 9 (impl), 9 (bg reviewer), 14, 17, 18, 20-R1, 20-R2 = 9 steps. Goal = ≥6/9 honoured strictly (≈67%, recovering from cycle-61's 33%).

---

## Goals

1. Close 5 long-deferred BACKLOG.md items grouped by file:
   - `tests/conftest.py` HIGH fixture leak surface (R3 audit, cycle 7 only added autouse embeddings reset).
   - `src/kb/query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild (final remaining piece; observability variant shipped cycle 25).
   - `src/kb/graph/builder.py` HIGH no-shared-cache contract (R2 audit, partial work cycle 6).
   - `src/kb/compile/publish.py` MEDIUM compile-time auto-publish hook + manifest-based incremental sibling cleanup.
   - `tests/` MEDIUM no golden-file / snapshot tests (R3 audit; foundational infrastructure).
2. Demonstrate cycle-64 parallel-cycle audit per cycle-61 R2 Finding 8 — explicit collision matrix vs all 4 active worktrees (cycle-53, 59, 61, 62).
3. Recover trial strict-audit ratio toward ≥67% by primary-session-implementing while keeping mimo-v2.5-pro audit role active (Step 8) and DeepSeek V4 Pro audit role active (Step 4 R2, Step 9 bg reviewer, Step 17 docs, Step 20 R1).

## Non-goals

- No test-fold work (cycles 53/59/62 own that surface; cycle-64 strictly avoids the 7 canonical fold receivers `test_compile/query/lint/mcp_core/config/cli/ingest`).
- No `src/kb/config.py` changes (cycles 53/59/61 own that surface).
- No `src/kb/utils/cli_backend.py` changes (cycles 53/59/61 own).
- No `src/kb/utils/io.py` changes (cycle-53 owns).
- No `src/kb/lint/checks/duplicate_slug.py` changes (cycles 53/61 own).
- No `src/kb/utils/wiki_log.py` / `src/kb/mcp/health.py` / `src/kb/query/engine.py` / `src/kb/query/hybrid.py` / `src/kb/compile/compiler.py` (cycle-61 owns those — public API would conflict on rebase).
- No CLI ↔ MCP write-path parity additions (BACKLOG MEDIUM, defer to cycle-65+ — adding 4-7 new CLI commands explodes the diff and overlaps cycle-61's `kb_rebuild_indexes` MCP tool wiring).
- No `kb.graph.cache` cross-process persistence (in-process keyed-dict cache only; cross-process is overkill for the documented win).
- No deletion of the 5 cycle-56+ BACKLOG-flagged `inspect.getsource` C11-L1 sites — **cycle-61 already touches all 5 of these test files** (verified via `git diff main..feat/cycle-61 --name-only` shows test_lint_query_fixes_v092, test_v0911_phase392, test_v0915_task01, test_v0915_task08). Cycle-61 commit `fa749d0 refactor(cycle 61): test suite — replace inspect.getsource with behavioral assertions (AC5,AC14-AC18)` consumes that batch. Cycle-64 explicitly defers the remaining sites until after cycle-61 lands so the diff is legible.

---

## Files Touched — Collision audit (per cycle-61 R2 Finding 8)

Verified via `git diff --name-only main..<ref>` for each parallel branch:

| File | Cycle 64 | Cycle 53 | Cycle 59 | Cycle 61 | Cycle 62 | Resolution |
|---|---|---|---|---|---|---|
| `tests/conftest.py` | NEW edits | — | — | — | — | clean |
| `src/kb/query/embeddings.py` | edits | — | — | — | — | clean |
| `src/kb/graph/builder.py` | edits | — | — | — | — | clean |
| `src/kb/graph/cache.py` (NEW) | NEW file | — | — | — | — | clean |
| `src/kb/lint/runner.py` | edits | — | — | — | — | clean |
| `src/kb/lint/semantic.py` | edits | — | — | — | — | clean |
| `src/kb/lint/checks/cycles.py` | edits | — | — | — | — | clean |
| `src/kb/lint/checks/orphan.py` | edits | — | — | — | — | clean |
| `src/kb/lint/augment/collector.py` | edits | — | — | — | — | clean |
| `src/kb/ingest/pipeline.py` | invalidation hook only | — | — | — | — | clean |
| `src/kb/refine/refiner.py` | invalidation hook only | — | — | — | — | clean |
| `src/kb/compile/publish.py` | edits | — | — | — | — | clean |
| `src/kb/compile/compiler.py` | small edit (auto-publish hook call) | — | — | edits | — | **rebase risk** — small additive insert at end of `compile_wiki` body; cycle-61 modifies `rebuild_indexes` signature but not the `compile_wiki` body's tail. Mitigation: cycle-64 inserts ONLY at `compile_wiki` post-success, not within the rebuild_indexes path. |
| `requirements-dev.txt` | append `syrupy>=4.6.0` | edits | — | — | — | trivial — append-only line |
| `tests/test_cycle64_conftest_leak.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/test_cycle64_dim_mismatch_autorebuild.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/test_cycle64_graph_cache.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/test_cycle64_auto_publish.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/test_cycle64_publish_manifest.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/test_cycle64_snapshots.py` (NEW) | NEW file | — | — | — | — | clean |
| `tests/__snapshots__/test_cycle64_snapshots/` (NEW dir) | NEW | — | — | — | — | clean |
| `CHANGELOG.md` | append `[Unreleased]` cycle-64 entry | edits | edits | edits | edits | rebase mechanical (per-cycle entries by date) |
| `CHANGELOG-history.md` | append cycle-64 entry | edits | edits | edits | edits | rebase mechanical |
| `BACKLOG.md` | delete 5 resolved items | edits | edits | edits | edits | rebase risk — narrow per-item delete; cycle-65 cleanup if conflict |
| `CLAUDE.md` | Quick Reference test count | edits | edits | edits | edits | rebase mechanical |
| `docs/reference/architecture.md` | graph-cache contract section | edits | edits | edits | edits | rebase mechanical |
| `docs/reference/testing.md` | conftest sandbox + snapshot section | edits | edits | edits | edits | rebase mechanical |

**Net rebase risk: LOW.** Source-code targets (rows 2-9, 11-13) have ZERO collision with any active parallel cycle. Doc files always rebase mechanically per the project's per-cycle append pattern. Single rebase concern is `compile/compiler.py`'s auto-publish hook insertion vs cycle-61's `rebuild_indexes` signature — mitigated by inserting at a different code path tail.

---

## Acceptance Criteria

ACs grouped by file per `feedback_batch_by_file`. HIGH+MED+LOW within a file land together.

### Cluster A — `tests/conftest.py` HIGH fixture leak surface (4 ACs)

**Context:** Phase 4.5 R3 finding. Existing `project_root` / `raw_dir` / `wiki_dir` fixtures point at REAL `PROJECT_ROOT` and are documented as "read-only use" but nothing enforces it. `test_cli.py:61-63` proves global-escape paths exist. Phase 5 will add `wiki/hot.md`, `wiki/overview.md`, `wiki/_schema.md`, `raw/captures/` — one more leak surface each.

**AC1.** Add an autouse fixture `_isolate_wiki_constants_per_test(monkeypatch, tmp_path)` to `tests/conftest.py` that, on every test by default, monkeypatches the following `kb.config` constants to point at per-test `tmp_path` subdirs: `WIKI_DIR`, `WIKI_LOG`, `WIKI_CONTRADICTIONS`, `RAW_DIR`, `PROJECT_ROOT`, `WIKI_PURPOSE`, `WIKI_INDEX`, `WIKI_SOURCES`. Implementation note: subdirs are created lazily on first `Path.mkdir(parents=True, exist_ok=True)` to keep cold-start cost minimal.

**AC2.** Add an opt-in fixture `real_project_root(request)` that yields the actual `kb.config.PROJECT_ROOT` ONLY when invoked under `pytest --use-real-paths`. Without the flag, the fixture raises `RuntimeError("real_project_root requires --use-real-paths to opt out of conftest sandboxing; see tests/conftest.py")`. Add `pytest_addoption(--use-real-paths, action='store_true')` to `conftest.py`.

**AC3.** Migrate the 3 known leak sites identified in cycle 7 + Phase 4.5 R3 audit to use the new opt-in pattern OR rely on AC1's autouse redirect:
- `test_cli.py:61-63` multi-global monkeypatch — confirm autouse redirect makes the existing test still pass; if test relies on real paths, mark with `pytest.mark.usefixtures("real_project_root")` and document why.
- `WIKI_CONTRADICTIONS` write-paths in `test_pipeline.py` / `test_compile.py` (if any escape AC1) — same migration.
- `load_purpose()` real-file reads in any test — same migration.

**AC4.** New regression test `tests/test_cycle64_conftest_leak.py` with 3 behavioural cases:
- `test_default_isolation_redirects_wiki_constants_to_tmp` — assert that under default-pytest-invocation, `kb.config.WIKI_DIR != PROJECT_ROOT_at_module_import_time`, AND a `Path.write_text` to `kb.config.WIKI_CONTRADICTIONS` lands inside `tmp_path` (not the real wiki).
- `test_real_project_root_fixture_raises_without_flag` — assert that `request.getfixturevalue("real_project_root")` raises `RuntimeError` matching `"--use-real-paths"` substring.
- `test_real_project_root_fixture_yields_real_path_with_flag` — invoke a sub-pytest via `subprocess.run([sys.executable, "-m", "pytest", "--use-real-paths", "-x", "<this_test_file>::test_under_flag"])` to verify the flag-gated path resolves.

### Cluster B — `src/kb/query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild (4 ACs)

**Context:** BACKLOG `query/embeddings.py` HIGH-Deferred — only sub-item (a) "dim-mismatch AUTO-rebuild" remains from the original cycle-25/26/28 observability cluster. The blocking design constraint was "needs `VectorIndex` to hold `wiki_dir` or callback + concurrent-rebuild idempotency design". **Concurrent-rebuild idempotency already exists** (`embeddings.py:28` `_conn_lock` serializes; `rebuild_vector_index` line 302–307 has double-checked locking). The only missing piece is "wiki_dir on VectorIndex". The codebase already derives `wiki_dir_hint = self.db_path.parent.parent` at embeddings.py:678 (inverse of `_vec_db_path`) — cycle-64 promotes that derivation to a primary code path under a documented contract.

**AC5.** Extract the existing `wiki_dir_hint = self.db_path.parent.parent` derivation into a `VectorIndex._derive_wiki_dir() -> Path | None` method with explicit contract:
- Returns `self.db_path.parent.parent` when `self.db_path` matches the canonical layout `<wiki_dir>/.data/vector_index.db` (i.e., the parent's parent is the wiki dir).
- Returns `None` when `self.db_path` is `None`, when it points at a `.tmp` rebuild artifact (suffix `.tmp`), or when `parent.parent` doesn't pass a basic `<dir>/.data/<file>` heuristic.
- Replace the inline derivation at line 678 with the new method (so the auto-rebuild path and the existing log-message path share one source of truth per cycle-19 L2 reload-leak hazard).

**AC6.** In `VectorIndex.query()`, when the existing dim-mismatch detection fires (the branch that currently returns `[]` and bumps `_dim_mismatches_seen`), also schedule an automatic rebuild via:
```python
wiki_dir = self._derive_wiki_dir()
if wiki_dir is not None and not _AUTO_REBUILD_DISABLED:
    rebuild_vector_index(wiki_dir)  # double-checked-locking inside, idempotent
```
Add a module-level `_AUTO_REBUILD_DISABLED = bool(os.environ.get("KB_DISABLE_VECTOR_AUTO_REBUILD"))` kill-switch (cycle-19 L2 + cycle-34 deferred-flag pattern; defaults to `False`). Document the kill-switch in `docs/reference/error-handling.md`. **Behavioural contract:** the FIRST query that detects mismatch still returns `[]` (auto-rebuild is fire-and-forget for that call); the SECOND query (after rebuild commits) returns real results.

**AC7.** Add `get_dim_mismatch_auto_rebuild_count() -> int` getter exposing a new module-level `_dim_mismatch_auto_rebuilds_seen` counter, mirroring the `get_dim_mismatch_count()` cycle-25 contract. Counter increments AFTER `rebuild_vector_index` returns (so a failed rebuild doesn't inflate the count). Telemetry parity with the cold-load + sqlite-vec-load + bm25-build counters per cycle-25/26/28 patterns.

**AC8.** New regression test `tests/test_cycle64_dim_mismatch_autorebuild.py` with 4 behavioural cases per C40-L3 revert-verification rule (each fails when AC6 is reverted):
- `test_dim_mismatch_triggers_rebuild` — write a vector DB with stored dim D1; monkeypatch the model to emit dim D2; query → assert `rebuild_vector_index` was called (spy) AND `get_dim_mismatch_auto_rebuild_count()` returned 1.
- `test_kill_switch_env_disables_auto_rebuild` — set `KB_DISABLE_VECTOR_AUTO_REBUILD=1`; same setup; assert `rebuild_vector_index` NOT called AND counter stays 0.
- `test_concurrent_query_during_rebuild_idempotent` — N=4 threads each calling `idx.query(...)` after planting dim-mismatch; assert `rebuild_vector_index`'s outermost body executed AT MOST ONCE (count `_is_rebuild_needed` calls under lock; the second-thread's check inside the lock should see the new dim and short-circuit).
- `test_auto_rebuild_disabled_when_db_path_is_tmp_suffix` — construct `VectorIndex(Path("/tmp/foo/.data/vector_index.db.tmp"))`; assert `_derive_wiki_dir()` returns `None` AND auto-rebuild path is skipped (this is the rebuild-in-progress sentinel — must not recurse).

### Cluster C — `src/kb/graph/cache.py` HIGH shared-cache contract (4 ACs)

**Context:** BACKLOG R2: "no reusable cache/invalidation contract". Cycle 6 added a query-side PageRank cache; cycle 7 threaded page bundles. Current state: `lint/runner.py:59` builds `shared_graph` per-call and threads it; `lint/checks/cycles.py:20`, `lint/checks/orphan.py:27`, `lint/semantic.py:140`, `lint/augment/collector.py:49` all call `build_graph(wiki_dir)` as a fallback when no shared graph is passed. The fallbacks are the contract gap.

**AC9.** New module `src/kb/graph/cache.py` exposing:
- `_GLOBAL_CACHE: dict[tuple[str, float], nx.DiGraph]` — keyed on `(wiki_dir.resolve().as_posix(), max_mtime_of_wiki_subdirs)`.
- `_CACHE_LOCK: threading.RLock` — guards reads + writes.
- `get_graph(wiki_dir: Path, *, pages: list[dict] | None = None) -> nx.DiGraph` — under `_CACHE_LOCK`, compute `current_mtime = max((p.stat().st_mtime for p in (wiki_dir / sub).rglob("*.md")), default=0.0)` over the WIKI_SUBDIRS canonical list; on cache hit return the cached graph; on miss call `build_graph(wiki_dir, pages=pages)`, store, return. Cache size bounded to `_MAX_CACHE_SIZE = 4` entries (LRU-style eviction by oldest-mtime); the bound prevents unbounded memory growth across long-lived processes (e.g. the MCP server) without imposing a per-call hot-path cost.
- `invalidate(wiki_dir: Path | None = None) -> int` — under `_CACHE_LOCK`, drop all cache entries whose `wiki_dir` matches; if `None`, drop everything; returns number of entries dropped.
- `get_cache_stats() -> dict` — `{"hits": int, "misses": int, "invalidations": int, "size": int}` for telemetry; counters approximate per cycle-25 Q8 precedent (no per-counter lock).

**AC10.** Wire `kb.graph.cache.get_graph` into the 5 fallback call sites identified above:
- `src/kb/lint/checks/cycles.py:20` — replace `graph = build_graph(wiki_dir)` with `graph = get_graph(wiki_dir)`.
- `src/kb/lint/checks/orphan.py:27` — same.
- `src/kb/lint/semantic.py:140` — `graph = get_graph(wiki_dir, pages=pages)`.
- `src/kb/lint/augment/collector.py:49` — `graph = get_graph(wiki_dir)`.
- `src/kb/lint/runner.py:59,96` — keep the existing per-call `build_graph` (top-level orchestrator pre-built graph); update to `get_graph(wiki_dir)` so threading from runner ↔ checks remains coherent. **Behavioural contract preserved**: `runner._run_all_checks` still threads `shared_graph` to checks; the change is that the FALLBACK path inside checks (when shared_graph is `None`) now hits the cache instead of always rebuilding.

**AC11.** Wire `kb.graph.cache.invalidate(wiki_dir)` at the END of two mutator code paths:
- `src/kb/ingest/pipeline.py::ingest_source` — single call right before the function returns the `IngestResult` (one line, no error-handling complication needed since the cache is best-effort).
- `src/kb/refine/refiner.py::refine_page` — single call right before its return.
- Document the contract in a new section in `docs/reference/architecture.md` titled "Graph cache contract" alongside the existing "Manifest contract" section per the BACKLOG fix recommendation. Section content: when graphs are built, when cached, when invalidated, and the consequences of skipping invalidation.

**AC12.** New regression test `tests/test_cycle64_graph_cache.py` with 5 behavioural cases (each fails when AC9–AC11 reverted):
- `test_get_graph_caches_within_one_lint_pass` — call `get_graph(wiki_dir)` twice in succession (no mutation between); assert `build_graph` was called exactly ONCE (spy via `monkeypatch.setattr(kb.graph.cache, "build_graph", spy)`).
- `test_get_graph_invalidated_by_mtime_bump` — call `get_graph`, write a new `.md` page, call `get_graph` again; assert `build_graph` was called TWICE.
- `test_invalidate_drops_entries_for_wiki_dir` — call `get_graph(wiki_dir_a)` + `get_graph(wiki_dir_b)`, then `invalidate(wiki_dir_a)`; assert size==1 and the surviving key matches `wiki_dir_b`.
- `test_ingest_source_invalidates_graph_cache` — call `get_graph(wiki_dir)`, then call `ingest_source(...)` against a fixture, then call `get_graph(wiki_dir)` again; assert the second `get_graph` triggered a rebuild (spy on `build_graph`).
- `test_cache_size_bound_lru_eviction` — load 5 distinct wiki_dirs into the cache; assert `get_cache_stats()["size"] == 4` AND the OLDEST entry was evicted (not a random one).

### Cluster D — `src/kb/compile/publish.py` MEDIUM compile-time auto-publish hook + manifest cleanup (5 ACs)

**Context:** Two BACKLOG MEDIUM items in publish.py:
1. "compile-time auto-publish hook — deferred: hook `kb publish` into `compile_wiki` so every compile auto-emits the Tier-1 + sibling + sitemap outputs."
2. "manifest-based incremental sibling cleanup — when N(retracted) exceeds ~1000 a `.data/publish-siblings-manifest.json` atomic-state approach becomes preferable."

**AC13.** Add a new function `auto_publish_after_compile(wiki_dir: Path, *, mode: str = "all", incremental: bool = True) -> dict[str, Path]` to `src/kb/compile/publish.py`. Signature mirrors the existing `kb publish` CLI handler. Body invokes the existing builders (`build_llms_txt`, `build_llms_full_txt`, `build_graph_jsonld`, `build_sitemap_xml`, `build_per_page_siblings`) using a default `out_dir = wiki_dir.parent / "_publish"` (NOT inside `wiki_dir` itself — keep publish artifacts out of the page-walk surface). Returns dict mapping format-name → output path. Errors during a single builder are logged at WARNING but don't fail the function (best-effort; `compile_wiki` should not regress on a publish hiccup).

**AC14.** In `src/kb/compile/compiler.py::compile_wiki`, AFTER the function's existing success path (manifest save + post-processing) and BEFORE the function returns, call `auto_publish_after_compile(effective_wiki_dir, incremental=(mode != "full"))` wrapped in a `try/except Exception as exc: logger.warning("auto-publish skipped: %s", exc)`. Add a kill-switch env var `KB_DISABLE_COMPILE_AUTO_PUBLISH` (defaults False) that short-circuits the call. The kill-switch is the cycle-64 mitigation for any compile-time regression that surfaces post-merge — operators can disable the hook without redeploying.

**AC15.** New regression test `tests/test_cycle64_auto_publish.py` with 4 cases:
- `test_compile_wiki_emits_llms_txt_and_graph_jsonld` — invoke `compile_wiki` against a `tmp_wiki` fixture with 3 fixture pages; assert `_publish/llms.txt`, `_publish/llms-full.txt`, `_publish/graph.jsonld`, `_publish/sitemap.xml` all exist post-compile.
- `test_kill_switch_env_disables_auto_publish` — set `KB_DISABLE_COMPILE_AUTO_PUBLISH=1`; same fixture; assert no `_publish/` directory created.
- `test_publish_failure_does_not_fail_compile` — monkeypatch one of the builders to raise `OSError`; invoke `compile_wiki`; assert it returns success AND `logger.warning` fired with `"auto-publish skipped"`.
- `test_publish_artifacts_outside_wiki_dir_walk` — assert the `_publish` directory is at `wiki_dir.parent / "_publish"`, NOT inside `wiki_dir` (would otherwise be ingested on the next pass).

**AC16.** Implement manifest-based incremental sibling cleanup in `src/kb/compile/publish.py::build_per_page_siblings`:
- Load `<wiki_dir>.parent / ".data" / "publish-siblings-manifest.json"` (empty dict if missing) — keys are page_id strings, values are list of sibling paths emitted on the previous publish.
- Compute the CURRENT publish's sibling-paths-by-page-id dict.
- For each previously-emitted sibling path NOT in the current dict → unlink (only if file exists; log INFO).
- Save the current dict to the manifest atomically via `atomic_json_write`.
- Behavioural change vs cycle-16 baseline: previously, every publish unlinked all `excluded` siblings unconditionally (O(|excluded|) syscalls per publish). Now the unlink set is bounded to `|previous - current|` (only siblings NEWLY excluded since the last publish).

**AC17.** New regression test `tests/test_cycle64_publish_manifest.py` with 3 cases:
- `test_first_publish_creates_manifest_no_unlinks` — fresh wiki_dir, no manifest; invoke `build_per_page_siblings`; assert manifest file written AND zero `Path.unlink` calls.
- `test_second_publish_only_unlinks_newly_excluded_siblings` — invoke once with 3 retracted pages, then again with 5 retracted pages (3 carry over + 2 new); assert manifest contents updated AND only the diff (2 newly-excluded paths) was unlinked, NOT all 5.
- `test_manifest_corrupted_falls_back_to_full_cleanup` — write a manifest with invalid JSON; invoke; assert function falls back to cycle-16 unconditional behaviour (no crash) AND logs WARNING about manifest corruption.

### Cluster E — `tests/` MEDIUM snapshot infrastructure foundation (3 ACs)

**Context:** BACKLOG R3: "no golden-file / snapshot tests; grep for snapshot/golden/syrupy/inline_snapshot/approvaltests returns zero hits. Wiki rendering is verified only by `assert "X" in output`."

**AC18.** Append `syrupy>=4.6.0` to `requirements-dev.txt` (single new line; cycle-53's edits to this file are doc/dep additions per its diff — `git diff main..worktree-cycle-53 -- requirements-dev.txt` is line-distinct from this addition so rebase is mechanical). Run `pip install -r requirements-dev.txt` to install in the cycle-64 worktree's `.venv` (verify install succeeds without resolver conflicts, especially against the existing `litellm==1.83.0` pin per BACKLOG known-conflicts list). If a resolver conflict surfaces, switch to `pytest-snapshot>=0.9.0` as the secondary fallback; document the choice in `docs/reference/testing.md`.

**AC19.** New file `tests/test_cycle64_snapshots.py` with 3 snapshot subjects (each is the canonical rendering surface for an open Phase 5 risk per BACKLOG):
- `test_evidence_trail_format_snapshot` — call `kb.utils.evidence.append_evidence_trail` against a fixture page with 3 entries spanning 2026-04-01 / 2026-04-15 / 2026-05-03; serialise the resulting page body; compare via `snapshot`.
- `test_mermaid_export_format_snapshot` — call `kb.graph.export.export_mermaid` against a fixture wiki with 3 pages and 2 wikilinks; compare the Mermaid output.
- `test_lint_report_format_snapshot` — call `kb.lint.runner.run_all_checks` against a fixture wiki with KNOWN issues (1 broken wikilink + 1 frontmatter validation error); compare the rendered report text.

**AC20.** Commit `tests/__snapshots__/test_cycle64_snapshots/` directory with the 3 initial snapshots (canonical fixture text). The directory is created by `syrupy` on first run with `--snapshot-update`. Verify via `pytest tests/test_cycle64_snapshots.py` that all 3 snapshots match WITHOUT `--snapshot-update` after commit (idempotency check). Document the snapshot-update workflow (`pytest tests/test_cycle64_snapshots.py --snapshot-update` after a deliberate format change) in `docs/reference/testing.md`.

### Cluster F — Doc sync (3 ACs, mandatory per project automation rules)

**AC21.** Append cycle-64 entry under `[Unreleased]` in `CHANGELOG.md` (Quick Reference compact format: Items / Tests / Scope / Detail). Items count = 21 ACs across 6 file domains. Append cycle-64 detailed bullet-level entry to `CHANGELOG-history.md` (newest first). Delete the 5 resolved BACKLOG.md items: (a) `tests/conftest.py` HIGH leak surface, (b) `query/embeddings.py` HIGH-Deferred dim-mismatch AUTO-rebuild, (c) `graph/builder.py` HIGH no-shared-cache contract, (d) `compile/publish.py` MEDIUM compile-time auto-publish hook, (e) `compile/publish.py` MEDIUM manifest-based sibling cleanup. Update `tests/` MEDIUM no-golden-file item to reflect cycle-64 partial coverage (3 snapshot subjects shipped; broader subjects deferred). Update `CLAUDE.md` Quick Reference test count (+ ~12 new tests from cycle-64). Update `docs/reference/architecture.md` (graph cache contract section) and `docs/reference/testing.md` (conftest sandbox section + snapshot-update workflow). All updates per the project's `Doc update checklist on push`.

---

## Risks

1. **Cycle-19 L2 reload-leak hazard** — `kb.graph.cache._GLOBAL_CACHE` is a module-level mutable. Tests that `importlib.reload(kb.graph.cache)` will re-init the cache, and parallel tests using `monkeypatch.setattr` on `kb.graph.cache._CACHE_LOCK` may dead-lock. **Mitigation**: AC9 cache module uses `threading.RLock` (re-entrant), and the regression test in AC12 explicitly invalidates between tests via an autouse fixture in `tests/test_cycle64_graph_cache.py`.
2. **Cycle-18 L1 snapshot-binding hazard** — AC10 wires `from kb.graph.cache import get_graph` at top of 5 caller modules. If a test does `monkeypatch.setattr("kb.graph.cache.get_graph", spy)` it will NOT affect the callers' bound name. **Mitigation**: callers use `import kb.graph.cache` + `kb.graph.cache.get_graph(...)` (attribute lookup) per cycle-18 L1 rule, OR each caller's regression test patches `kb.graph.cache.get_graph` AND each caller's local-import spelling.
3. **Cycle-20 L3 audit-tag scope** — AC15 `tests/test_cycle64_auto_publish.py` only tests the `kb_compile`/`kb_compile_scan` MCP tools indirectly via `compile_wiki`. **Mitigation**: AC15 case `test_publish_artifacts_outside_wiki_dir_walk` enumerates the 4 emitted formats; if a future MCP tool wraps the same publish path, that tool's tests inherit the wikitree-walk safety.
4. **Cycle-22 L4 late-arrival CVE hazard** — `syrupy>=4.6.0` (AC18) is a NEW dep. Step 11 PR-CVE diff must check for advisories on this version. **Mitigation**: Step 11 SCA artifact triage covers `syrupy` advisory check; if surfaced, downgrade or substitute `pytest-snapshot`.
5. **Cycle-40 L3 revert-verification** — AC4, AC8, AC12, AC15, AC17 each contain a divergent-fail clause ("each fails when ACx is reverted"). **Mitigation**: Step 9 self-check spy-replaces production calls with `lambda *a: None` per regression test and confirms test FAILs (not green-by-vacuum).
6. **Compile-time hook regression risk** — AC14 wires `auto_publish_after_compile` into `compile_wiki`. A latent bug in publish.py's incremental skip (cycle-15 L1) could cause compile_wiki to spend time on every pass. **Mitigation**: AC14's `KB_DISABLE_COMPILE_AUTO_PUBLISH` kill-switch is the immediate operator escape hatch; AC15's `test_publish_failure_does_not_fail_compile` proves compile-time errors are isolated. Step 13 coverage-delta should also confirm the new code path is exercised in tests, not silently skipped.
7. **Auto-rebuild on dim-mismatch under contention** — AC6 calls `rebuild_vector_index` synchronously from `VectorIndex.query()`. Under FastMCP's 40-thread pool, a dim-mismatch storm (all 40 threads see mismatch) could see N concurrent rebuild attempts. **Mitigation**: `rebuild_vector_index` already has double-checked locking via `_conn_lock` (embeddings.py:28, 302–307); only the FIRST thread does the rebuild work. AC8 case `test_concurrent_query_during_rebuild_idempotent` proves this.
8. **Parallel-cycle merge-window collision on `compile/compiler.py`** — cycle-61 modifies `compile_wiki`'s `rebuild_indexes` signature; cycle-64 inserts `auto_publish_after_compile` at the function tail. **Mitigation**: AC14's insertion is an additive single-line call at the body's tail, NOT inside the rebuild_indexes path. If cycle-61 lands first, cycle-64 rebases trivially; if cycle-64 lands first, cycle-61's signature change applies independently. Both orderings tested via `git rebase --onto` simulation in Step 9 (planned check).

---

## Step-5 open questions (to resolve at design decision gate)

1. **Q1 (AC9)**: cache size bound `_MAX_CACHE_SIZE = 4` or different? Justification welcome — most workloads use 1 wiki_dir; 4 covers test fixtures + dev local + CI multi-fixture without unbounded growth.
2. **Q2 (AC10)**: should `lint/runner.py:59` ALSO migrate to `get_graph` (not just the fallbacks), making the cache the single canonical entry point? Trade-off: simpler contract vs. losing the explicit "orchestrator pre-builds and threads" semantics.
3. **Q3 (AC11)**: invalidate `kb.graph.cache` from `compile_wiki` post-success too (cycle-64 leaks the invalidation through `ingest_source` per-call inside the loop, but a final coarse invalidation post-loop is cheap insurance)?
4. **Q4 (AC13)**: `auto_publish_after_compile` `out_dir` default — `wiki_dir.parent / "_publish"` (proposed) vs. project-root-relative `.data/publish/` vs. user-configurable via `kb.config.PUBLISH_DIR` constant? Lean: proposed for Phase 5 forward-compat (publish artifacts shouldn't pollute `.data/`).
5. **Q5 (AC18)**: `syrupy` vs `pytest-snapshot` — syrupy is more featured (string + JSON + custom serializer support) but adds a new dep; pytest-snapshot is plain-text only. Lean: syrupy.
6. **Q6 (AC19)**: snapshot subject coverage — the proposed 3 (evidence-trail / Mermaid / lint-report) cover Phase 5's biggest output-format-drift risks per BACKLOG R3. Add a 4th for `_build_summary_content` (page-rendering pipeline) or defer? Lean: defer to cycle-65+ (3 subjects = adequate foundation; over-shipping increases snapshot maintenance churn).
7. **Q7 (AC1)**: should the autouse fixture be opt-out via a marker (`@pytest.mark.allow_real_paths`) rather than the explicit `--use-real-paths` CLI flag? Trade-off: marker is more explicit per-test but adds discovery surface; CLI flag is a single global escape hatch. Lean: CLI flag (cleaner; cycle-64 has zero tests that genuinely need real paths once AC3 migrations land).

---

## References

- BACKLOG.md (lines 78-196 actionable section) — Phase 4.5 HIGH/MEDIUM/LOW + Phase 5 follow-up items.
- `dev-mimo-opus` SKILL.md (this run) — Tier classifier + 24-step pipeline.
- `project_cycle61_mimo_failure` memory (2026-05-03) — mimo-v2.5-pro implementer-role failure mode; primary-session implementation directive.
- `feedback_batch_by_file` memory — batch HIGH+MED+LOW per-file.
- `feedback_3_round_pr_review` memory — R3 trigger threshold (≥25 ACs OR risk-profile-driven).
- Cycle 61 self-review `docs/superpowers/decisions/2026-05-03-cycle-61-self-review.md` — trial-failure-record state, 33% strict-audit ratio, recovery target 67%.
- Cycle 19 L2 (snapshot-binding), cycle 20 L3 (audit-tag scope), cycle 22 L4 (late-arrival CVE), cycle 40 L3 (revert-verification) — applied to risks list above.
