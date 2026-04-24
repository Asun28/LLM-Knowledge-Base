# Cycle 28 — Brainstorm (Step 3)

**Date:** 2026-04-24
**Step:** feature-dev Step 3 (Opus main + superpowers:brainstorming)
**Inputs:**
- Step 1 requirements: `docs/superpowers/decisions/2026-04-24-cycle28-requirements.md`
- Step 2 threat model: `docs/superpowers/decisions/2026-04-24-cycle28-threat-model.md`
- CVE baseline: `.data/cycle-28/cve-baseline.json` (2 CVEs, both no-upstream-fix, identical to cycle-26)

---

## Core question

How should cycle 28 add perf-counter observability to the two remaining first-query latency sources — `VectorIndex._ensure_conn` (sqlite-vec extension load) and `BM25Index.__init__` (corpus indexing) — while respecting the existing cycle-25 `_dim_mismatches_seen` (lock-free, approximate) and cycle-26 `_vector_model_cold_loads_seen` (locked, exact) precedents without disturbing either?

Secondary question: do the AC7–AC9 BACKLOG-hygiene + CHANGELOG-format + CVE-re-verify items route through the same design or are they pure bookkeeping that skips design eval? (Pure bookkeeping — AC7-AC9 are doc-only edits with no open design question.)

## Approaches

### Approach A — Precedent-mirror (recommended)

Copy the cycle-26 AC3/AC4 pattern line-for-line for each new observability site:

- `_ensure_conn`: `perf_counter()` brackets the extension-load block. On success, emit INFO log; above `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS = 0.3`, also emit WARNING. Increment module-level `_sqlite_vec_loads_seen` INSIDE the existing `_conn_lock` (already held for the extension-load path) — exact counts, matches cycle-26 precedent for locked low-rate events.
- `BM25Index.__init__`: `perf_counter()` brackets the corpus loop. Emit INFO log with `n_docs` and elapsed. Increment module-level `_bm25_builds_seen` LOCK-FREE — matches cycle-25 `_dim_mismatches_seen` precedent for unlocked approximate counts (no caller-side lock wraps the constructor, cache lock released before rebuild per `engine.py:110` / `engine.py:794`).
- Getters: `get_sqlite_vec_load_count() -> int` in embeddings.py, `get_bm25_build_count() -> int` in bm25.py. Each docstring cross-references the cycle that established the lock-choice rationale.
- No threshold for BM25 — corpus indexing is expected to scale with wiki size, so a WARN pollutes logs on large wikis. INFO-only gives operators the raw signal without a false alarm.

**Pros:**
- Narrow diff (~50 lines across `embeddings.py` + `bm25.py` + one new test file).
- Zero migration risk — existing cycle-25/26 counters + getters stay untouched.
- Test pattern is already established (`test_cycle26_cold_load_observability.py` 7 tests — cycle 28 clones the structure with s/`_model_lock`/`_conn_lock`/g substitutions for the locked variant and s/warm_load/build/g for the BM25 variant).
- Reviewers (R1 Codex + R1 Sonnet) recognise the pattern; saves explanation overhead in PR body.
- Follows cycle-20 L3 same-class MCP-peer rule in reverse: we do NOT expose the counters through MCP or CLI, matching cycle-26 Q14 decision that observability counters are diagnostic-only library surface.

**Cons:**
- DRY-adjacent duplication: four module-level counter patterns now exist (`_dim_mismatches_seen`, `_vector_model_cold_loads_seen`, `_sqlite_vec_loads_seen`, `_bm25_builds_seen`). A future fifth would justify factoring but cycle 28 is the wrong time.
- Two separate WARN-threshold constants if a future cycle adds a BM25 threshold — treat that as a future-cycle question.

### Approach B — Unified `kb.query.perf` observability module

Create a new `src/kb/query/perf.py` with an `ObservabilityCounter` registry: each counter name maps to a lock (optional) + int. Refactor all four existing + new counters onto it.

**Pros:**
- Single abstraction for the counter pattern; future observability work becomes trivial (register new counter name).
- Natural home for the latency-log helpers (`_time_and_log(name, threshold)`).

**Cons:**
- Migration risk on cycle-25/26 counters. Cycle-26 L2 (count-site drift) warns about multi-site changes — this approach multiplies that risk.
- `get_dim_mismatch_count()` and `get_vector_model_cold_load_count()` are public (exported from `kb.query.embeddings` and documented in CLAUDE.md). A refactor must preserve their exact signatures or we break external callers + docs.
- Larger diff (~200 lines including migration + new module + tests for the registry itself).
- Scope creep from "close HIGH-Deferred (b)" to "refactor observability plumbing" — exceeds the batch-by-file convention and the requirements doc's non-goals.

### Approach C — Context-manager-based timing

Add a `_time_perf("name", threshold_secs)` context manager in `kb.utils` (or `kb.query.perf`) that brackets perf-counter + log + counter update in one call. Call sites become:

```python
with _time_perf("sqlite-vec-load", threshold_secs=0.3):
    sqlite_vec.load(conn)
```

**Pros:**
- Call-site readability — less boilerplate at each instrumented location.
- Centralised log format — a future format-guide change touches one place.

**Cons:**
- Hides the pattern inside an abstraction. Reviewers have to jump to the context manager to understand what gets logged where. For cycle 28's two sites this is net-negative.
- Counter registry requires a lookup contract (by name) which is hard to audit — typo in `"sqlite-vec-load"` vs `"sqlite_vec_load"` silently creates two counters.
- Getter signatures still need per-counter wrappers for documentation (we can't expose a generic `get_counter(name)` because CLAUDE.md cross-references specific getter names).
- Breaks the "grep for `_ensure_conn` → see instrumentation" discoverability. Operators debugging "why is my first query slow" benefit from instrumentation that lives AT the call site.

## Recommendation

**Approach A.** The cycle-26 precedent is freshly codified and still structurally correct. Approach B's abstraction has a place AFTER the counter count grows past ~5 (cycle 29+ candidate). Approach C's context-manager pattern is seductive but the call-site clarity loss is real — reviewers value grep-able instrumentation at the actual latency source.

Cycle 28 ships Approach A with one refinement: getter docstrings MUST name-check both precedents (lock-free cycle-25 dim-mismatch vs locked cycle-26 cold-load) and pick a side with explicit rationale. This is the cycle-26 L3 CONDITION-call-shape prompt addition applied to design reasoning — future maintainers see WHY the asymmetry exists without spelunking three decision docs.

## AC7-AC9 design decisions (bookkeeping, no approach tree)

- **AC7 — BACKLOG hygiene:** Three independent deletions + one narrow edit. No design surface. Follow cycle-26 AC8 precedent (BACKLOG narrow + delete stale entries).
- **AC8 — Commit-count convention doc:** Single HTML-comment line inside `CHANGELOG.md`'s existing entry-rule comment block. Formalises cycle-26 L1 feature-dev skill patch into the repo itself so future cycles don't need to re-discover the rule. No competing approach.
- **AC9 — CVE re-verify:** Cycle-22 L1 pip-audit baseline already captured (2 CVEs, identical to cycle-26). Skip-on-no-diff per cycle-27 AC7 pattern. CHANGELOG notes "no-op re-verify, matches cycle-26 baseline". No design surface.

## Open questions for Step 5 design decision gate

1. **Q1 — BM25Index WARN threshold?** Should `BM25Index.__init__` emit WARNING above some threshold (analogous to `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS`), or stay INFO-only? Bias: INFO-only. Wiki size varies (100 pages → 5K pages); a single threshold value is either too low (spammy on large wikis) or too high (useless on small wikis). WARN threshold is a cycle 29+ decision if operator feedback surfaces a canonical corpus size.

2. **Q2 — Counter exact vs approximate for BM25?** Should `_bm25_builds_seen` use a dedicated `threading.Lock` for exact counts (cycle-26 `_model_lock` style) or stay lock-free (cycle-25 `_dim_mismatches_seen` style)? Bias: lock-free. BM25 builds have no existing lock to piggy-back on (the cache lock is released before rebuild), so exact counts require a NEW lock. Lock-free matches the query-hot-path precedent where counter accuracy is not billing-grade.

3. **Q3 — INFO log severity for extension-load failure path?** T1 threat model says the failure path's existing WARNING stays unchanged. Should the new success-path INFO log ALSO fire at DEBUG on the failure path to capture the attempted-load latency? Bias: no — failure path is already WARNING with the exception message; adding a DEBUG adds noise without diagnostic value.

4. **Q4 — Per-instance vs module-level counters?** Threat T8 raised the reload-leak risk. Should counters live on the `VectorIndex` / `BM25Index` instance (per-instance) or module level (current precedent)? Bias: module level. Per-instance breaks the "process-level observability" contract operators expect; `importlib.reload` poisoning is mitigated by the test-side monotonic-delta pattern (cycle-26 AC5 precedent).

5. **Q5 — Cycle-28 scope-out list from same-class peer scan (T-row 6 candidates)?** Step 2 threat model enumerated 6 candidate observability sites (rebuild_vector_index total duration, model.encode per-batch, VectorIndex.query end-to-end, tokenize() cost, _evict_vector_index_cache_entry close latency, HF cache-hit discrimination). Which (if any) should cycle 28 include? Bias: NONE — all six are explicitly out-of-scope for "close HIGH-Deferred (b)". Document the scope-out reasoning in the Step 5 design gate so cycle 29 inherits the enumeration.

6. **Q6 — Test file location?** `tests/test_cycle28_first_query_observability.py` (new file, cycle-26 style) vs. extending `tests/test_cycle26_cold_load_observability.py` (co-locate similar observability tests)? Bias: new file. Cycle-per-file test convention is established (cycle-25 had 3 new files; cycle-26 had 1; cycle-27 had 1). New file keeps diff ownership clean and mirrors the cycle-per-decision-doc pattern.

7. **Q7 — Path redaction for INFO logs?** Threat T2 noted cycle-20's `<path_hidden>` pattern for `StorageError`. Should AC1's INFO log emit `db=<path_hidden>` instead of the literal `self.db_path`? Bias: no — cycle-20 established the redaction applies to ERROR-boundary exceptions that may propagate to log aggregators. INFO logs are parity with existing `_get_model()` cold-load INFO which also logs operator-configured paths unredacted. Maintain parity; revisit as a blanket INFO-log redaction policy in a dedicated future cycle.

8. **Q8 — Test-fixture concurrency on `_ensure_conn` counter?** If a test creates multiple `VectorIndex` instances (each with own `_conn_lock`), do we need a counter-level lock? Bias: no — each instance serialises its own `_conn_lock`; between instances, the counter `+=` is approximate (like cycle-25). But inside the `_conn_lock` itself, the increment is exact per-instance. Document the "exact per-instance, approximate across-instances" semantics in the getter docstring.

## Verdict

Approach A + 8 open questions for Step 5. Approach A's diff footprint (~50 lines + 7 regression tests) fits the batch-by-file cycle convention and respects cycle-26 L2 (grep-all-sites before counter-count drift).
