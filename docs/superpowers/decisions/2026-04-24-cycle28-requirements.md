# Cycle 28 — Requirements + Acceptance Criteria

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle28`
**Step:** feature-dev Step 1 (Opus main)
**Batch theme:** First-query observability completion (HIGH-Deferred b, cycle-26 Q16 follow-up) + batch-by-file BACKLOG hygiene.

---

## Problem

Cycle 26 shipped the vector-model cold-load observability track (AC1-AC5) addressing the `_get_model()` latency source. The HIGH-Deferred "vector-index lifecycle" entry in BACKLOG.md narrows to two remaining sub-items:

- **(a)** Dim-mismatch AUTO-rebuild (design-heavy — requires `VectorIndex` to hold `wiki_dir` or callback + concurrent-rebuild idempotency) → stays deferred for a dedicated cycle.
- **(b)** First-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load latency and `BM25Index` build latency remain uninstrumented. An operator who sees a slow first query today cannot discriminate "sqlite-vec extension load took 400ms" from "BM25 corpus indexing took 350ms" from "the model cold-loaded despite cycle-26's warm-load hook" without attaching a profiler. Cycle-26 Q16 explicitly noted (b) as a follow-up.

Secondary items surfaced alongside: stale LOW BACKLOG entry for cycle-27 commit-tally (entry is obsolete — CHANGELOG now reflects the +1 self-referential rule from cycle-26 L1 but the rule itself is not documented in the repo), stale MEDIUM rationale-only line about `_post_ingest_quality` AC17-drop (belongs in CHANGELOG-history, not BACKLOG), and the routine CVE re-verify that each cycle re-confirms for diskcache + ragas.

## Non-goals

- **No dim-mismatch AUTO-rebuild** — HIGH-Deferred (a) stays deferred. Scope-out preserves cycle 28 as a narrow observability batch.
- **No warm-load hook for sqlite-vec / BM25** — cycle-26 shipped warm-load ONLY for the model; extending warm-load to sqlite-vec would require `_ensure_conn` to take a `wiki_dir` argument (it derives DB path from `self.db_path` already set at instantiation). Observability first; warm-load later if data supports it.
- **No env-override for new thresholds** — matches cycle-26 Q4 decision: module-level constants only, no `KB_*` env vars. Operator diagnostic use only.
- **No `threading.Lock` around the BM25 counter** — matches cycle-25 Q8 decision: approximate counts are adequate for diagnostic observation. The `_ensure_conn` counter DOES sit inside the existing `_conn_lock` (lock is already held for the extension-load path) — exact counts are free.
- **No changes to `kb.mcp.__init__.main()`** — cycle-26 wired `maybe_warm_load_vector_model(WIKI_DIR)` there; no additional hook this cycle.
- **No CHANGELOG entry format overhaul** — AC8 documents ONE rule (commit-count convention). Don't scope-creep into ALL format-guide rules.

## Acceptance criteria

Each testable as pass/fail.

### Observability — `VectorIndex._ensure_conn` (sqlite-vec extension load)

**AC1** `VectorIndex._ensure_conn` brackets the sqlite_vec extension load with `time.perf_counter()`. On the SUCCESS path (extension loaded, `self._conn = conn`), emit `logger.info("sqlite-vec extension loaded in %.3fs (db=%s)", elapsed, self.db_path)` BEFORE returning the connection. On the FAILURE path (extension unavailable, `_disabled = True`), NO perf log fires (existing `logger.warning` for extension-load failure is retained unchanged).
- Test: mock sqlite_vec.load to succeed quickly, call `_ensure_conn`, capture `caplog` — exactly one INFO record matches the format with floating-point elapsed > 0.
- Test: mock sqlite_vec.load to raise ImportError / Exception, call `_ensure_conn`, capture `caplog` — zero INFO records matching the perf pattern, existing WARNING path fires.

**AC2** Module-level constant `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS: float = 0.3` in `kb.query.embeddings`. On successful extension load with `elapsed >= SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS`, emit `logger.warning("sqlite-vec extension load took %.3fs (threshold=%.2fs); consider warm-loading", elapsed, SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS)`. Warning is IN ADDITION to the AC1 INFO record (not a replacement).
- Test: monkeypatch `time.perf_counter` so elapsed > 0.3s; assert both INFO + WARNING in caplog.
- Test: monkeypatch `time.perf_counter` so elapsed < 0.3s; assert INFO present, WARNING absent.

**AC3** Module-level `_sqlite_vec_loads_seen: int = 0` counter in `kb.query.embeddings`, incremented exactly once per successful `_ensure_conn()` transition from `_conn is None` to `_conn is not None`. Increment occurs INSIDE `_conn_lock` (the lock is already held across the extension-load path), giving exact counts — intentional asymmetry vs. cycle-25 `_dim_mismatches_seen` (lock-free, approximate), same rationale as cycle-26 `_vector_model_cold_loads_seen`. Public getter `get_sqlite_vec_load_count() -> int`. No reset helper.
- Test: fresh VectorIndex instance, call `_ensure_conn` against a valid DB, assert counter incremented by exactly 1.
- Test: call `_ensure_conn` twice on same instance (second call hits fast-path `self._conn is not None`), assert counter unchanged (still +1 from first call).
- Test: failed `sqlite_vec.load` → `_disabled=True`; counter unchanged.

### Observability — `BM25Index.__init__`

**AC4** `BM25Index.__init__` brackets the corpus indexing loop with `time.perf_counter()`. Immediately before returning, emit `logger.info("BM25 index built in %.3fs (n_docs=%d)", elapsed, self.n_docs)`. Log fires unconditionally on every `__init__` call (including empty-corpus case, `n_docs=0`).
- Test: build `BM25Index([["foo", "bar"], ["baz"]])`, capture caplog, assert exactly one INFO with matching format and `n_docs=2`.
- Test: build `BM25Index([])`, caplog shows INFO with `n_docs=0` (still fires — diagnostic floor).

**AC5** Module-level `_bm25_builds_seen: int = 0` counter in `kb.query.bm25`, incremented once per `__init__` call (at end, after corpus loop). Lock-FREE — matches cycle-25 `_dim_mismatches_seen` reasoning: `BM25Index` construction is not locked by callers (cache hit/miss is locked, but the construction call itself happens outside the cache lock in `engine.py`), and operator diagnostic counts tolerate under-counting by ≤N under N concurrent rebuilds. Public getter `get_bm25_build_count() -> int`. No reset helper. Getter docstring explicitly cross-references cycle-25 Q8 and cycle-26 AC4 contrasting approach.
- Test: fresh process; construct two BM25Index instances; assert counter increased by exactly 2.
- Test: empty-corpus `BM25Index([])` still increments the counter.

### Regression tests

**AC6** Seven regression tests land in a new file `tests/test_cycle28_first_query_observability.py` covering all AC1-AC5 branches. Tests monkeypatch `time.perf_counter` for deterministic elapsed values (match cycle-26 AC5 style). Tests use `caplog` fixture at INFO level. `VectorIndex` tests build a minimal DB via existing `build()` method into a `tmp_path`.

Test names (match cycle 26/27 test-function naming convention):
1. `test_sqlite_vec_load_emits_info_on_success`
2. `test_sqlite_vec_load_emits_warning_above_threshold`
3. `test_sqlite_vec_load_no_warning_below_threshold`
4. `test_sqlite_vec_load_count_increments_exactly_once`
5. `test_sqlite_vec_load_count_stable_on_fast_path`
6. `test_bm25_build_emits_info_with_n_docs`
7. `test_bm25_build_count_monotonic_across_instances`

### BACKLOG hygiene + docs (no test changes)

**AC7** BACKLOG.md mutations (three independent edits):
- Narrow HIGH-Deferred "vector-index lifecycle" entry: remove sub-item (b) (cycle-28 shipped), keep (a) (dim-mismatch AUTO-rebuild). Update prose to reference cycle 28 AC1-AC5 as the landing point.
- Delete MEDIUM line `src/kb/lint/augment.py::_post_ingest_quality — AC17-drop rationale for future reference: cache-invalidation work was reconsidered and DROPPED...`. The rationale is duplicated in CHANGELOG-history cycle-13 AC2; the BACKLOG entry adds no open work.
- Delete LOW entry `CHANGELOG.md cycle-27 quick-reference commit tally ...`. CHANGELOG currently says "3 commits" which IS the correct value under the +1 self-referential rule from cycle-26 L1; the BACKLOG entry's claim "CHANGELOG says 2 commits" is stale.

**AC8** Document the commit-count convention in CHANGELOG.md's hidden format-guide comment (lines 10-17 area). Add a one-liner: `<!-- commits: on feature-branch squash-merge flow, the cycle commit count equals pre-merge branch commits + 1 for the landing doc-update that contains this changelog line (self-referential per cycle-26 L1). -->` Place inside the existing entry-rule HTML comment block.

### CVE re-verify

**AC9** Run `pip-audit --format=json` against the installed venv (per cycle-22 L1: drop `-r requirements.txt` to avoid ResolutionImpossible). Compare against cycle-26 baseline (`.data/cycle-26/cve-baseline.json` if still present, else the cycle-25 baseline). If the advisory set is identical (same 2 CVEs on diskcache + ragas, identical `fix_versions=[]`), the cycle 28 changelog notes "no-op CVE re-verify, matches cycle-26 baseline" (cycle-27 AC7 skip-on-no-diff pattern). If ANY new advisory appears, routes to Step 11 as a Class B (PR-introduced) OR Step 11.5 (Class A if existing-on-main) per normal feature-dev skill flow.

## Blast radius

**Files modified:**
- `src/kb/query/embeddings.py` — add perf_counter wrap in `_ensure_conn`, module constants + counter + getter (+~30 lines).
- `src/kb/query/bm25.py` — add perf_counter wrap in `BM25Index.__init__`, module counter + getter (+~20 lines).
- `tests/test_cycle28_first_query_observability.py` — new file, 7 tests (~150 lines).
- `BACKLOG.md` — 3 edits (one narrow, two delete).
- `CHANGELOG.md` — new cycle 28 Quick Reference entry + 1-line format-guide addition.
- `CHANGELOG-history.md` — full cycle 28 detail entry.
- `CLAUDE.md` — bump test count (2801 → 2808), update `_ensure_conn` docstring cross-ref in "Key APIs" block, add BM25 counter cross-ref.

**Modules NOT touched:**
- `src/kb/mcp/__init__.py` — no new warm-load hooks.
- `src/kb/cli.py` — no new CLI subcommands; cycle-27 cli additions stay unchanged.
- `src/kb/query/engine.py` — BM25Index CALL sites (lines 110, 794) remain unchanged; instrumentation is inside the class, not at call sites.

**Existing callers of modified functions:**
- `_ensure_conn` is called by `VectorIndex.query` only (line ~580) — unchanged contract (returns connection or None).
- `BM25Index(...)` is called from `engine.py:110` (`search_pages` wiki-side cache rebuild) and `engine.py:794` (raw-side cache rebuild). Neither call site reads the counter directly. No breaking changes.

**Security posture:**
- Logs: new INFO + conditional WARNING records. Format strings are module-local; no user-controlled content reaches the format args (`self.db_path` is operator-configured; `elapsed` is a float; `n_docs` is int).
- Counters: process-local integers. Not exposed via MCP or CLI (intentional — matches cycle-26 Q14 decision to keep observability counters diagnostic-only, not operator API surface).
- Threading: `_ensure_conn` counter inside existing `_conn_lock` (no new lock). `BM25Index` counter lock-free (intentional per cycle-25 Q8).

## Cross-cycle references

- **Cycle 25 AC4** — `_dim_mismatches_seen` lock-free counter precedent (query-hot-path, approximate).
- **Cycle 26 AC3/AC4** — `_get_model()` perf_counter + WARN threshold + exact-count counter inside `_model_lock` (the canonical pattern for cycle 28's `_ensure_conn` path).
- **Cycle 26 Q16** — explicit "first-query observability" follow-up that cycle 28 closes (sub-item b of HIGH-Deferred).
- **Cycle 26 L1** — commit-count self-referential rule; AC8 codifies it in CHANGELOG.md format guide.
- **Cycle 22 L1** — pip-audit without `-r requirements.txt` to avoid ResolutionImpossible on Windows + complex deps.
- **Cycle 27 AC7** — skip-on-no-diff CVE re-verify pattern that AC9 inherits.
- **Cycle 13 AC2** — the `_post_ingest_quality` explanatory rationale whose duplicate BACKLOG line AC7 removes.
