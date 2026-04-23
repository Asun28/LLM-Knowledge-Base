# Cycle 25 — Requirements + Acceptance Criteria

**Date:** 2026-04-24
**Scope:** Narrowed from cycle-24's 15 ACs to ~10 ACs covering follow-ups surfaced by cycle-24 + remaining tractable Phase 4.5 items. HIGH-Deferred vector-index lifecycle sub-item 3 (dim-mismatch observability, NOT auto-rebuild per risk), compile_wiki per-source rollback (M2), rebuild_indexes `.tmp` awareness (cycle-24 R2 surfaced), BACKLOG + CVE maintenance.

## Problem

Four Phase 4.5 gaps remain tractable after cycle 24:

1. **`rebuild_indexes` leaves `<vec_db>.tmp` untouched.** Cycle 24 AC5 introduced the tmp-then-replace pattern for `rebuild_vector_index`. Cycle 24 AC6 cleans stale `.tmp` on the next rebuild's entry. But `rebuild_indexes` (cycle-23 operator-scoped "clean-slate" helper) only unlinks `<vec_db>`, not `<vec_db>.tmp`. If an operator runs `kb rebuild-indexes` while a `.tmp` from a crashed rebuild exists, the `.tmp` survives until the next `rebuild_vector_index` call — not a correctness bug (AC6 covers it belt-and-suspenders) but a hygiene gap that confuses operators.

2. **Vector-index dim-mismatch produces a silent empty result with only a `logger.warning`.** `VectorIndex.query` at `embeddings.py:466-478` logs once on mismatch (`_dim_warned` sticky flag) and returns `[]`. The hybrid search code at `query/engine.py` treats this empty return as "no vector hits" and silently falls back to BM25-only. Operators debugging silent search degradation see the warning in logs but get no concrete remediation path in the message. The HIGH-Deferred sub-item (3) originally asked for auto-rebuild on dim-mismatch; a lighter alternative is to improve the warning message with operator action + add a process-level counter for observability.

3. **`compile_wiki` per-source failure leaves inconsistent state.** `compile/compiler.py:425-471` iterates `for source in sources_to_process` and calls `ingest_source` inside a try. On exception, it records `failed:{hash}` in the manifest but does NOT mark the source as "partially complete" vs "never started". If `ingest_source` wrote a summary page + some entity pages then raised partway through, compile_wiki reports `error` but the partial wiki writes persist with no marker. Next `kb compile --incremental` treats `failed:{hash}` as "try again"; next re-ingest may duplicate entries in `index.md` / `_sources.md` because the partial writes weren't tracked. The BACKLOG fix (per-source in-progress marker) is the documented remedy.

4. **diskcache + ragas CVEs need 24-hour re-verification.** Per cycle-22 L4, advisories can drop mid-cycle. Cycle 24 verified both CVEs on 2026-04-23; cycle 25 runs ~1 day later, so re-running `pip-audit` + `pip index versions` catches any new upstream patch. Expected result: unchanged (neither has an upstream fix yet).

## Non-goals

- **Vector dim-mismatch AUTO-rebuild.** The HIGH-Deferred sub-item (3) originally asked for this. Deferred to a future cycle: auto-rebuild inside `VectorIndex.query()` requires threading `wiki_dir` into the VectorIndex instance or reverse-deriving it from `db_path`, both of which widen the class's coupling surface. Cycle 25 scope: improve the warning message + add observability counter; the operator runs `kb rebuild-indexes` to remediate.
- **`_update_existing_page` single-write consolidation.** Cycle 24 AC2 shipped error-surfacing; full consolidation needs to buffer existing Evidence Trail bytes across the body-write + evidence-append boundary, which is a substantive refactor touching the sentinel-anchor logic. Defer.
- **`utils/io.py` fair-queue lock.** Cycle 24 AC9 added exponential backoff. Fair queueing requires either POSIX `fcntl.flock` (not cross-platform) or a waiter-position protocol. Defer.
- **`config.py` god-module split.** Multi-file structural refactor; defer.
- **All cycle-24 scope (evidence-trail, vector-atomic rebuild, file_lock backoff, sentinel-anchor).** Shipped in cycle 24.

## Acceptance Criteria

### Cluster A — `rebuild_indexes` `.tmp` awareness (`src/kb/compile/compiler.py`)

**AC1** — `rebuild_indexes` also unlinks `<vec_db>.tmp` (the sibling `.tmp` path used by cycle-24 `rebuild_vector_index`) inside the vector-DB cleanup block (`compiler.py:620-628`). Uses the same helper `_vec_db_path(wiki_dir)` to derive `tmp_path = vec_path.parent / (vec_path.name + ".tmp")`. `unlink(missing_ok=True)` — tolerant of tmp not existing. On `OSError`, adds the error to `result["vector"]["error"]` as a compound message (`"vec_path: <err_a>; tmp_path: <err_b>"`).

**AC2** — Regression test `test_cycle25_rebuild_indexes_cleans_tmp`: seed a dummy `<vec_db>.tmp` file, call `rebuild_indexes(wiki_dir=...)`, assert the tmp file no longer exists. Divergent-fail under AC1 revert.

### Cluster B — Vector dim-mismatch operator guidance (`src/kb/query/embeddings.py`)

**AC3** — `VectorIndex.query()`'s `logger.warning` on dim mismatch now includes operator action text: the existing message already names the stored vs query dims; extend it to suggest `kb rebuild-indexes` and note the path to the vector DB. Format: `"Vector index dim mismatch: query=%d vs stored=%d at %s. Run 'kb rebuild-indexes --wiki-dir %s' to realign, OR ignore if BM25-only search is intended."`

**AC4** — Module-level counter `_dim_mismatches_seen: int = 0` + helper `get_dim_mismatch_count() -> int` for observability/testing. Incremented on every query that detects a mismatch (NOT once-per-instance — operators watching the counter over time need event counts, not instance counts). The `_dim_warned` sticky flag stays per-instance (don't spam the log).

**AC5** — Regression test `test_cycle25_dim_mismatch_warning_includes_remediation`: build a VectorIndex, seed a DB with mismatched dim, run query, assert the logger.warning message contains `"kb rebuild-indexes"` AND the counter increments by 1. Divergent-fail if the message is reverted to the pre-cycle-25 form.

### Cluster C — `compile_wiki` per-source in-progress marker (`src/kb/compile/compiler.py`)

**AC6** — Inside `compile_wiki`'s per-source loop (`compiler.py:425-471`), write an `in_progress:{hash}` marker to the manifest under `file_lock(manifest_path)` BEFORE calling `ingest_source`. On success, `ingest_source`'s own manifest write (via `manifest_key=rel_path` contract from cycle 19 AC13) overwrites the `in_progress:` entry with the real hash. On failure, the existing `except Exception` block replaces the `in_progress:` with `failed:{pre_hash}`. The `in_progress:` marker therefore CANNOT persist through a normal Python-level exception — it only survives on hard kill (SIGKILL, power-loss) or if the whole `compile_wiki` process aborts between the pre-marker and `ingest_source`.

**AC7** — `compile_wiki` checks for stale `in_progress:` markers in the manifest at loop entry. If any are found, log a `logger.warning` naming each source path. Do NOT auto-delete the markers: the operator decides whether to `kb rebuild-indexes` or investigate. The check only runs ONCE per `compile_wiki` invocation (at the top of the function, before processing starts).

**AC8** — Regression test `test_cycle25_compile_wiki_in_progress_marker_on_hard_kill`: seed manifest with a stale `in_progress:hash_xyz` marker from a prior (simulated) hard-kill; call `compile_wiki`; assert `logger.warning` was emitted naming the source. Second test: monkey-patch `ingest_source` to raise RuntimeError mid-loop; assert the manifest AFTER the exception contains `failed:{pre_hash}` (NOT `in_progress:...`) for that source. Both divergent-fail under AC6/AC7 revert.

### Cluster D — BACKLOG maintenance + CVE re-verify (`BACKLOG.md` + non-code)

**AC9** — Step 11.5 re-verification (date 2026-04-24): run `pip-audit --format=json` AND `pip index versions diskcache` AND `pip index versions ragas`. Expected: both CVEs unchanged, both packages still LATEST INSTALLED. Update BACKLOG.md lines 134 + 137 date stamps to 2026-04-24 IF and ONLY IF re-audit confirms `fix_versions: []`. If either shows a fix, run Step-11.5 `fix(deps)` commit bumping `requirements.txt`.

**AC10** — Remove the `rebuild_indexes .tmp awareness` BACKLOG entry (line 111) AFTER AC1 ships — resolved this cycle.

## Conditions (Step 09 must satisfy — cycle-22 L5 load-bearing)

1. **AC1 ordering:** the `.tmp` unlink MUST run AFTER the `vec_path.unlink` inside the same try/except OR in a separate try/except (so a `.tmp` unlink failure does NOT blank the `result["vector"]["cleared"] = True` status when the main unlink succeeded). Use compound error message if both fail.
2. **AC3 message exactness:** the regression test's assertion about `"kb rebuild-indexes"` must anchor on the literal command text, not just "rebuild" — ensures future refactors don't silently drop the actionable command.
3. **AC4 counter semantics:** counter increments per-query-with-mismatch (not per-instance). Test must call query multiple times and assert counter increments N times. Reset helper is NOT required for cycle 25 — leave as-is for tests to observe monotonicity.
4. **AC6 marker format:** `in_progress:{pre_hash}` — same `pre_hash` the failure branch uses at line 469. Reuses the cycle-19 AC13 `manifest_key=rel_path` contract. The marker is placed into the SAME `manifest[rel_path]` slot that `ingest_source` will overwrite; no new key format.
5. **AC6 lock scope:** the pre-marker write + `ingest_source` call together are NOT wrapped in `file_lock` — `ingest_source` acquires its own manifest lock per cycle-19 AC13. The pre-marker write takes `file_lock(manifest_path, timeout=...)` briefly, releases, then calls `ingest_source`. Nested lock would self-deadlock (cycle-20 L1).
6. **AC8 divergent-fail:** the hard-kill test must not actually SIGKILL (too flaky); simulate by seeding a manifest entry. The exception-mid-loop test must assert the FINAL manifest state (not intermediate) to avoid observing the in-progress marker before the exception handler overwrites it.
7. **AC9 command ordering:** run `pip-audit` FIRST to establish the CVE state, THEN `pip index` to confirm latest version. The BACKLOG date stamp edit happens only after BOTH commands confirm no change.
8. **AC10 lifecycle:** BACKLOG deletion + CHANGELOG entry happen together in one commit per cycle-20 L2 "resolved items are deleted" rule.

## Blast radius

- `src/kb/compile/compiler.py` — `rebuild_indexes` (+~5 lines); `compile_wiki` (+~20 lines for AC6/AC7).
- `src/kb/query/embeddings.py` — `VectorIndex.query` (+~3 lines for message); module-level counter + getter (+~5 lines).
- `tests/test_cycle25_*.py` — 4 new tests (1 per cluster).
- `BACKLOG.md` — delete 1 entry, update 2 date stamps.
- `CHANGELOG.md` + `CHANGELOG-history.md` + `CLAUDE.md` — cycle 25 index entry + per-cluster detail + test count.

**Estimated test delta:** +5 to +8 tests (4 new test functions, some parametrized). Current count: 2768.

## References

- BACKLOG.md §Phase 4.5 HIGH-Deferred `rebuild_indexes .tmp` + `vector-index lifecycle` (sub-item 3).
- BACKLOG.md §Phase 4.5 MEDIUM M2 `compile/compiler.py` per-source rollback.
- Cycle 24 merge (`9e5e8e7`) — baseline for AC1, AC3 (vector atomic rebuild already shipped).
- Cycle 19 AC13 — `manifest_key=rel_path` contract that AC6 inherits.
- Cycle 23 AC2 — `rebuild_indexes` helper that AC1 extends.
