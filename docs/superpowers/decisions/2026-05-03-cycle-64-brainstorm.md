# Cycle 64 — Brainstorming (Step 3)

**Date:** 2026-05-03
**Author:** Opus 4.7 primary session
**Inputs:** `2026-05-03-cycle-64-requirements.md` (21 ACs, Tier 2) + `2026-05-03-cycle-64-threat-model.md` (18 threats, 4 material).
**Mode:** Auto-approve per `feedback_auto_approve` memory; design eval R1+R2 (Step 4) + design-decision-gate Opus subagent (Step 5) carry the approval load.

This document presents 2–3 design alternatives per AC cluster, each with tradeoffs + a recommended path. Step 4 design-eval (Opus R1, DeepSeek V4 Pro R2) will challenge these recommendations adversarially.

---

## Cluster A — `tests/conftest.py` HIGH fixture leak surface (AC1–AC4)

**Sub-question:** how do we redirect `WIKI_*` / `RAW_*` / `PROJECT_ROOT` constants for tests by default while still supporting the small minority of tests that need real paths?

### A1 — Autouse monkeypatch (broad redirect, opt-out via CLI flag) — RECOMMENDED

Add an `autouse` fixture that, on every test, monkeypatches every `kb.config.WIKI_*` and `RAW_*` constant to subdirectories of `tmp_path`. The opt-out is a global `--use-real-paths` CLI flag exposed via `pytest_addoption`. The fallback `real_project_root` fixture raises a `RuntimeError` when invoked without the flag.

**Pros**: simple mental model (one global gate); single CLI flag is easier to scan in CI logs than scattered `@pytest.mark.allow_real_paths` markers; matches the existing `tmp_kb_env` fixture's "redirect HASH_MANIFEST" precedent (cycle 7).

**Cons**: enumerating ALL `WIKI_*` and `RAW_*` constants is fragile — the threat-model M1 / T2 finding showed that AC1's first draft missed 5 subdir constants (`WIKI_ENTITIES`, `WIKI_CONCEPTS`, `WIKI_COMPARISONS`, `WIKI_SUMMARIES`, `WIKI_SYNTHESIS`). Mitigation: AC1's enumeration runs a `grep "kb\.config\.(WIKI_|RAW_|PROJECT_ROOT)"` over `src/kb/` and AC4 includes a positive-redirect regression for one of the previously-missed constants.

### A2 — Marker-opt-in per-test (`@pytest.mark.allow_real_paths`)

Tests that need real paths get a marker; the autouse fixture skips redirect when the marker is present. No CLI flag.

**Pros**: per-test granularity; survives `--use-real-paths` accidents (no global escape hatch).

**Cons**: discovery surface increases (every reviewer must check whether a new test SHOULD have the marker); the marker proliferates to dozens of legacy tests during migration AC3 — same effort as A1 but with longer rebase risk. Less obvious in CI logs.

### A3 — Two-tier: redirect `WIKI_DIR` only, assume subdir constants are lazy

Redirect only `WIKI_DIR` (and `RAW_DIR`, `PROJECT_ROOT`); leave subdir constants alone on the assumption that the codebase reads them lazily from `WIKI_DIR / "entities"`.

**Pros**: minimal surface area (3 monkeypatch lines instead of 13).

**Cons**: assumption is unverified — in practice `kb/config.py:62-66` defines explicit `WIKI_ENTITIES = WIKI_DIR / "entities"` constants that bind at MODULE import time, so monkeypatching `WIKI_DIR` AFTER import does NOT propagate. This option silently fails the threat (M1 / T2). Reject.

**Decision:** A1 with M1 / T2 mitigation baked into AC1's enumeration step.

---

## Cluster B — `src/kb/query/embeddings.py` dim-mismatch AUTO-rebuild (AC5–AC8)

**Sub-question:** when `VectorIndex.query()` detects dim-mismatch, should the rebuild fire synchronously (block the current call) or asynchronously (fire-and-forget)?

### B1 — Synchronous rebuild on first detection — RECOMMENDED

`VectorIndex.query()` detects mismatch → call `rebuild_vector_index(self._derive_wiki_dir())` synchronously → return `[]` (the rebuild result is not yet visible because `_index_cache` still holds the old VectorIndex). The NEXT query call rebuilds the cache entry from disk and returns real results.

**Pros**: no new threads, simple control flow; `rebuild_vector_index` already has double-checked locking (`_conn_lock` + `_is_rebuild_needed`) so concurrent dim-mismatch storms only do ONE rebuild. The "first call returns `[]`, second call returns real" contract is consistent with the cycle-25 observability variant's behavior.

**Cons**: the FIRST query after a model upgrade pays the rebuild latency (load_all_pages + encode + sqlite_vec build — typically ~10–30 seconds on a small KB). Operators may see one slow query.

### B2 — Async background-thread rebuild

Fire `threading.Thread(target=rebuild_vector_index, args=(wiki_dir,), daemon=True).start()` and return `[]` immediately.

**Pros**: zero added latency on the user-facing query path.

**Cons**: introduces a new thread lifecycle to reason about (cycle-26 already shipped `maybe_warm_load_vector_model` as a daemon thread; adding another doubles the warm-load surface). Under a query storm, multiple background rebuilds may queue (the `_conn_lock` serialises but the fan-out is now N rebuild attempts vs. B1's 1). Also: if the calling thread is part of FastMCP's pool, the daemon thread outliving the FastMCP request boundary is a subtle leak.

### B3 — Explicit kill-switch only, NO auto-rebuild

Keep the cycle-25 observability variant unchanged; require operators to run `kb rebuild-indexes --wiki-dir <path>` manually after a model upgrade.

**Pros**: zero new behaviour; the operator-actionable remediation log message (`embeddings.py:678–686`) already tells operators what to do.

**Cons**: this is the CURRENT state — closing the BACKLOG HIGH-Deferred entry requires SOMETHING to fire automatically. The `KB_DISABLE_VECTOR_AUTO_REBUILD` kill-switch in B1 already preserves this option for operators who need it.

**Decision:** B1 with `KB_DISABLE_VECTOR_AUTO_REBUILD` kill-switch + double-checked-locking inheritance. The "first query returns `[]`" contract is documented in AC6 and is consistent with cycle-25's observability variant.

---

## Cluster C — `src/kb/graph/cache.py` shared cache (AC9–AC12)

**Sub-question:** is the cache a new module with explicit invalidation, or should we just tighten the existing `shared_graph` threading?

### C1 — New `kb.graph.cache` module with mtime-keyed dict + invalidation hooks — RECOMMENDED

New module owning `_GLOBAL_CACHE`, `_CACHE_LOCK`, `get_graph(wiki_dir, *, pages=None)`, `invalidate(wiki_dir)`, `get_cache_stats()`. The 5 fallback `build_graph` call sites in `lint/checks/cycles.py`, `lint/checks/orphan.py`, `lint/semantic.py`, `lint/augment/collector.py`, `lint/runner.py` migrate to `get_graph`. Invalidation hooks at the END of `ingest_source` and `refine_page`.

**Pros**: explicit contract (queryable via `get_cache_stats()`); the cache survives across CLI calls within ONE process (e.g. test fixtures invoking `lint.run_all_checks` multiple times); formalises the "graph cache" concept in `docs/reference/architecture.md` per the BACKLOG fix recommendation. Independently testable (AC12).

**Cons**: introduces a new module-level mutable, so cycle-19 L2 reload-leak hazard applies (mitigated by `RLock` and AC12's autouse-invalidate fixture).

### C2 — Tighten existing `shared_graph` threading (no new module)

Audit all `build_graph` call sites; ensure `lint/runner.py` threads `shared_graph` through to every check. No cross-call cache.

**Pros**: zero new state; smallest diff.

**Cons**: doesn't formalize the contract — a future Phase 5 feature can still call `build_graph(wiki_dir)` directly. Doesn't enable cross-CLI-call caching (every `kb lint` rebuilds from scratch). Doesn't satisfy the BACKLOG entry's `kb.graph.cache keyed on (wiki_dir, max_mtime)` design directive.

### C3 — Extend cycle-6 PageRank cache to whole-graph cache

Cycle 6 added a query-side PageRank cache; reuse that infrastructure for the full graph object.

**Pros**: extends an existing cache pattern.

**Cons**: cycle-6's PageRank cache is query-scoped (lifetime ≈ one `kb_query` call). Promoting it to a process-wide cache changes its design. Same complexity as C1 with less coherent boundaries.

**Decision:** C1. `_MAX_CACHE_SIZE = 4` is the LRU bound (Q1 in requirements doc Step-5 questions); it fits a typical workload (1 wiki_dir for users, 2–4 for test fixtures + dev local + CI), and unbounded growth is the only cost worth bounding.

---

## Cluster D — `src/kb/compile/publish.py` auto-publish hook (AC13–AC15)

**Sub-question:** should compile auto-publish happen unconditionally on every `compile_wiki` success, or behind an explicit opt-in?

### D1 — Auto-hook on every successful compile, with kill-switch — RECOMMENDED

`compile_wiki` post-success calls `auto_publish_after_compile(wiki_dir, incremental=...)`; behaviour is gated by `KB_DISABLE_COMPILE_AUTO_PUBLISH=1` env var. Errors are caught at the `compile_wiki` level (try/except + WARNING log) so a publish failure doesn't fail the compile.

**Pros**: aligns with Karpathy's "wiki retrievable by other agents" goal (Tier 1 #1 in BACKLOG Phase 5); operators don't need to remember to run `kb publish` after `kb compile`; existing `_publish_skip_if_unchanged` heuristics in `publish.py:55` make repeated publishes cheap.

**Cons**: introduces a new behaviour on every `kb compile` invocation — operators who explicitly DON'T want publish artifacts now need the kill-switch. Mitigation: `KB_DISABLE_COMPILE_AUTO_PUBLISH=1` is the documented escape hatch, and the kill-switch documentation lives in AC14's `docs/reference/error-handling.md` update.

### D2 — Explicit CLI opt-in flag `kb compile --publish`

Add `--publish` flag to the `kb compile` CLI subcommand; only when present, run the publish step.

**Pros**: zero behaviour change for default `kb compile` users.

**Cons**: doesn't satisfy the BACKLOG goal ("hook `kb publish` into `compile_wiki` so EVERY compile auto-emits"); operators still need to remember the flag. Phase 5 ambient-capture features (`SessionStart` hook, `raw/` watcher) would silently skip publish unless they pass the flag.

### D3 — Watch-mode daemon `kb watch`

Add a long-running `kb watch` command that monitors `raw/` for changes and triggers compile + publish.

**Pros**: best UX for steady-state usage.

**Cons**: massive scope expansion; explicitly out of cycle-64's non-goals; deferred to Phase 5 Tier 3 ambient-capture cluster per BACKLOG.

**Decision:** D1 with `KB_DISABLE_COMPILE_AUTO_PUBLISH` kill-switch and try/except isolation. M4 / T6 mitigation (path-validate `out_dir`) is bundled into AC13's contract.

---

## Cluster D' — `compile/publish.py` manifest-based incremental cleanup (AC16–AC17)

**Sub-question:** how do we track previously-emitted siblings so we only unlink newly-excluded ones?

### D'1 — JSON manifest at `<wiki>.parent/.data/publish-siblings-manifest.json` — RECOMMENDED

Atomic-state manifest mapping `page_id → list[sibling_path]` from the previous publish. On corruption (JSONDecodeError), fall back to cycle-16's unconditional unlink semantics (AC17 case `test_manifest_corrupted_falls_back_to_full_cleanup`).

**Pros**: human-readable for debugging; `atomic_json_write` already exists in `kb.utils.io`; corruption-fallback preserves correctness.

**Cons**: adds a new on-disk state file. Mitigation: it lives under `.data/` (gitignored).

### D'2 — SQLite manifest with WAL

Use a sqlite DB to track sibling state.

**Pros**: durable, supports concurrent access.

**Cons**: overkill for the scale (publish runs once per compile; no concurrent-write surface). Adds a new sqlite_vec/sqlite_lite dependency.

### D'3 — Last-publish pageset file (no per-page sibling tracking)

Just write a `<wiki>.parent/_publish/.last_publish_pageset.txt` listing all published page-ids; on next publish, unlink any sibling whose page-id is in the file but not in the current set.

**Pros**: simplest possible.

**Cons**: doesn't track sibling PATHS; if `_sibling_paths_for(page_id)` changes (e.g. cycle-65 changes the sibling layout), the cleanup misses orphans.

**Decision:** D'1.

---

## Cluster E — `tests/` snapshot infrastructure (AC18–AC20)

**Sub-question:** which snapshot library?

### E1 — `syrupy>=4.6.0` — RECOMMENDED

Mature pytest-native snapshot library; supports custom serializers, JSON, raw text; broad fixture support.

**Pros**: most feature-rich; established ecosystem; idiomatic pytest integration.

**Cons**: new dep (Class B for Step 11 SCA per T17). If a CVE surfaces, fallback is E2.

### E2 — `pytest-snapshot>=0.9.0` (fallback)

Plain-text only; minimal feature surface.

**Pros**: minimal dep; minimal SCA surface.

**Cons**: text-only — for AC19's `lint_report` snapshot subject (which includes structured data) we'd need to render to text manually. More boilerplate per snapshot.

### E3 — `inline-snapshot`

Modern; snapshots inline with the test source code.

**Pros**: snapshots co-located with tests (no `__snapshots__/` directory).

**Cons**: newer ecosystem; less precedent in the project's existing test pattern.

**Decision:** E1, fallback to E2 if Step 11 SCA flags `syrupy`.

---

## Aggregate decision

Recommendations: A1, B1, C1, D1, D'1, E1.

These align with the requirements doc's 21 ACs verbatim — the brainstorming surfaced no need to re-scope. The 4 material threats from the threat model (M1 / M2 / M3 / M4) are addressed by:
- M1 (T2): A1 + AC1 enumeration grep + AC4 4th case (extension).
- M2 (T4): B1 + double-checked locking inheritance + AC8 N=4 concurrent-rebuild test.
- M3 (T18): C1 + cycle-18 L1 attribute-lookup callers (covered by AC10 implementation note + AC12 spy on owner module).
- M4 (T6): B1 + AC6 `_validate_path_under_project_root` Step-14 verifier check.

8 Step-14 verifier-only checks queued from the threat model (no AC owns them; security-verify must add).

**Next step:** Step 4 design eval — Opus R1 + DeepSeek V4 Pro R2 dispatched in parallel against the requirements + threat model + this brainstorming doc. Step 5 design-decision-gate Opus subagent resolves any R1/R2 NEEDS_REVISION verdicts before Step 7 implementation plan begins.
