# Cycle 24 — Requirements + Acceptance Criteria

**Date:** 2026-04-23
**Scope:** Phase 4.5 backlog-by-file cycle (M3 file_lock poll, M11 evidence-trail pairing, HIGH-Deferred vector-index atomic rebuild + dim-validation, doc-only BACKLOG maintenance).

## Problem

Four bounded Phase 4.5 gaps remain after cycle 23:

1. **Evidence-trail two-write race (M11).** `_write_wiki_page` (new page) writes rendered body with `atomic_text_write`, then calls `append_evidence_trail` which opens the file under `file_lock`, reads, inserts sentinel + entry, and re-writes. A crash between the two writes leaves a page on disk with NO evidence trail — violating Phase 4's provenance invariant ("every ingested wiki page has ≥1 evidence trail entry"). `_update_existing_page` has the same two-write shape; if `append_evidence_trail` raises `OSError` (disk-full, permission flap, lock contention), the body write is on disk but the evidence-append failure becomes a partial-state `OSError` far from the caller. The failure is not explicitly coded as `IngestError(kind="evidence_trail_append_failure")`, so downstream handlers (compile_wiki per-source loop, ingest telemetry) can't reliably distinguish body-write-failed from evidence-append-failed.

2. **Vector-index rebuild is not crash-safe (HIGH-Deferred sub-item 1).** `rebuild_vector_index` calls `VectorIndex(vec_path).build(entries)` which opens `sqlite3.connect(str(self.db_path))` directly on the production DB path, drops the old tables, recreates them, and inserts rows. A crash mid-`build()` leaves the DB with partial tables — subsequent queries return empty or malformed results. Recovery requires the operator to notice a `kb_query` silently degraded to BM25 and invoke `kb rebuild-indexes`.

3. **`file_lock` polling floor (M3 narrow).** `utils/io.LOCK_POLL_INTERVAL = 0.05` (50ms fixed). Every contested `file_lock` acquisition pays a minimum 50ms wait per retry iteration. Under moderate contention this amplifies 10x or more for chained RMW sequences. An exponential-backoff schedule (start 10ms, double per iter, cap 100ms) preserves throughput under high contention while eliminating the low-contention floor. (The broader M3 ask — append-only JSONL with native locking — is too large for this cycle and is explicitly deferred.)

4. **Stale BACKLOG entries after cycle 23.** The HIGH-Deferred `tests/ multiprocessing tests` item shipped in cycle 23 (file_lock_multiprocessing regression test). The diskcache + ragas CVE entries carry 2026-04-21 / 2026-04-23 re-check dates that need updating per cycle-22 L4 "advisories can arrive mid-cycle". Keeping stale entries violates BACKLOG.md lifecycle rule ("resolved items are deleted").

## Non-goals

- **Full M3 JSONL migration.** `atomic_json_write` → append-only JSONL with `msvcrt.locking` / `fcntl` is a multi-file architectural refactor affecting feedback, verdicts, manifest, augment manifest, etc. Out of scope; file as its own future cycle.
- **Dim-mismatch auto-rebuild.** The HIGH-Deferred sub-item (3) asks for auto-rebuild on dim mismatch. Current code at `VectorIndex.query` already warns + returns `[]` on mismatch. Auto-rebuild inside `_ensure_conn` risks cold-load during query hot path. Surface the mismatch via telemetry in a future cycle.
- **Index-lifecycle sub-item (2) cold-load.** Warm-load on MCP startup is a new feature, not a bug fix; defer.
- **Index-lifecycle sub-item (4) `_index_cache` cross-thread lock symmetry.** Cycle 3 H8 already shipped `_index_cache_lock` + double-checked locking. Remains in BACKLOG as closed; cleanup under AC12.
- **M2 per-source rollback receipt-file mechanism.** Substantially covered by cycle 18 AC4/AC5 ingest JSONL telemetry + cycle 19 AC13 manifest reservation. Leave BACKLOG entry untouched; full receipt-file design is its own feature.
- **M10 full IndexWriter for all 5 writes.** Cycle 18 AC14 shipped the _sources/index helper. Extending to manifest+log+contradictions is its own refactor; leave BACKLOG entry untouched with narrowed text.
- **HIGH structural items** (naming inversion, state-store fan-out, shared graph cache, async MCP, tests freeze-and-fold, conftest leak surface). All are multi-module structural refactors; defer to dedicated cycles.
- **Phase 5 pre-merge items** (`capture.py` two-pass write, `_PROMPT_TEMPLATE` relocation, `CAPTURES_DIR` architectural contradiction). Per user instruction, skip Phase 5 items this cycle.

## Acceptance Criteria

### Cluster A — evidence-trail reliability (`src/kb/ingest/pipeline.py` + `src/kb/ingest/evidence.py`)

**AC1** — `_write_wiki_page` (new-page path) renders body + inline evidence trail section in a SINGLE `atomic_text_write` call. After `_write_wiki_page` returns, the page file on disk contains `## Evidence Trail\n<!-- evidence-trail:begin -->\n- YYYY-MM-DD | <source> | Initial extraction: <page_type> page created\n`. NO subsequent `append_evidence_trail` call happens in the new-page branch. Verified by: behavioral test that writes a new page and reads back; assert the evidence trail section is present in the first-write output.

**AC2** — `_update_existing_page` — when `append_evidence_trail` raises `OSError`, the call site re-raises as `StorageError(kind="evidence_trail_append_failure", path=page_path)` so the outer ingest handler can distinguish body-write success vs evidence-append failure. (Chose `StorageError` over `IngestError` to match cycle-20 storage-failure taxonomy.) Verified by: unit test that monkey-patches `append_evidence_trail` to raise `OSError`, calls `_update_existing_page`, asserts `StorageError` with correct `kind` field.

**AC3** — Regression test (new-page behavioral): ingest a new source; verify the written page contains `## Evidence Trail` + sentinel + initial entry in a single `atomic_text_write` call (spy on `atomic_text_write` OR read page content after ingest and assert section presence). The test MUST divergently-fail on revert (if AC1 is reverted, the test fails) — no vacuous shape.

**AC4** — Regression test (existing-page error surfacing): `_update_existing_page` with `append_evidence_trail` monkeypatched to raise `OSError` must raise `StorageError(kind="evidence_trail_append_failure")`. Test late-binds `StorageError` via `pipeline_mod.StorageError` to avoid cycle-20 L1 reload-leak.

### Cluster B — vector-index atomic rebuild (`src/kb/query/embeddings.py`)

**AC5** — `rebuild_vector_index` writes to `<vec_db>.tmp` first, then calls `os.replace(tmp_path, vec_path)` for the atomic swap. On crash mid-build, the production `vec_path` retains its pre-rebuild state (valid old index OR absent). Verified by: spy on `os.replace` after calling `rebuild_vector_index(force=True)`; assert called with `(tmp_path, vec_path)`.

**AC6** — `rebuild_vector_index` unconditionally unlinks any stale `<vec_db>.tmp` at entry (before building) so a crash-leftover `.tmp` from a prior run doesn't contaminate the new build. Verified by: seed a dummy `<vec_db>.tmp` file, call `rebuild_vector_index(force=True)`, assert the stale tmp was replaced by a valid index and the stale bytes do not appear in the final DB.

**AC7** — `VectorIndex.build(entries)` migrated to accept a `db_path` kwarg override so `rebuild_vector_index` can drive it against `<tmp_path>` instead of hard-coding `self.db_path`. Default behavior (no kwarg) unchanged — all existing callers (none outside `rebuild_vector_index` per grep) continue to work. Verified by: signature test (`inspect.signature(VectorIndex.build).parameters['db_path'].default`) + behavioral test that `build(entries, db_path=other)` writes to the override path.

**AC8** — Regression test — atomic rebuild crash simulation: monkey-patch `VectorIndex.build` to raise after partial row insertion; call `rebuild_vector_index(force=True)`; assert the production `vec_path` is EITHER untouched (if existed before) OR absent (if did not); assert `<vec_db>.tmp` does not exist after the failure OR contains only the partial state (whichever the chosen cleanup strategy produces). Test must divergently-fail if AC5 is reverted to direct in-place write.

### Cluster C — `file_lock` exponential backoff (`src/kb/utils/io.py`)

**AC9** — `file_lock` uses exponential backoff for retry polling: initial 10ms, doubles each iter, capped at 100ms. The 50ms `LOCK_POLL_INTERVAL` constant stays as a compatibility alias pointing at the cap OR is deprecated (design-gate decision) but existing module-level monkeypatches on the symbol continue to work. The `file_lock` implementation MUST read `LOCK_POLL_INTERVAL` at call time (not import time) so test monkeypatches on the module attribute still steer timing.

**AC10** — Regression test: `time.sleep` spy asserts the sleep sequence during a contested acquire matches the exponential schedule. Use `multiprocessing.Event` or a seeded lock file so the test doesn't introduce race conditions. Test late-binds `file_lock` via `kb.utils.io.file_lock` to avoid import-time drift.

### Cluster D — BACKLOG maintenance (`BACKLOG.md` + docs)

**AC11** — Delete the HIGH-Deferred `tests/ multiprocessing tests for cross-process file_lock semantics` entry from `BACKLOG.md` — shipped in cycle 23. Add brief one-line entry to `CHANGELOG.md [Unreleased]` Quick Reference noting backlog cleanup.

**AC12** — Update the diskcache CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v) re-check date in BACKLOG.md to 2026-04-23. Re-verify `pip index versions diskcache` still shows 5.6.3 as latest and `pip-audit` reports empty `fix_versions`. If either changes, bump `requirements.txt` under a Step-11.5 fix(deps) commit.

**AC13** — Update the ragas CVE-2026-6587 (GHSA-95ww-475f-pr4f) re-check date in BACKLOG.md to 2026-04-23. Re-verify `pip-audit` reports empty `fix_versions`. Same action contingency as AC12.

### Cluster E — sentinel-anchor hardening (new, surfaced by Step-2 threat model T5)

**AC14** — `append_evidence_trail` sentinel search is anchored within the FIRST `## Evidence Trail` section header (regex-based: find `## Evidence Trail` header FIRST, then search for sentinel only within the bytes following that header). An attacker-planted `<!-- evidence-trail:begin -->` substring inside the wiki page body BEFORE the `## Evidence Trail` header is ignored. Current code (`evidence.py:86-88`) uses `content.index(SENTINEL)` which takes FIRST occurrence — vulnerable to body-planted sentinel. Cycle-24 AC1 makes this more likely since the sentinel is now inserted at first-write.

**AC15** — Regression test `test_cycle24_evidence_sentinel_anchored`: seed a page body containing `<!-- evidence-trail:begin -->` as plain text BEFORE a real `## Evidence Trail\n<!-- evidence-trail:begin -->\n...` block; call `append_evidence_trail`; assert the new entry lands AFTER the real `## Evidence Trail` header, not the body-planted sentinel. Must divergently-fail when AC14 is reverted.

### Conditions (Step-9 must satisfy — cycle-22 L5 load-bearing)

1. **AC1 applies to BOTH branches of `_write_wiki_page`.** The `exclusive=True` branch (cycle-20 AC8 — `O_EXCL` + `O_NOFOLLOW` + poison-unlink) and the non-exclusive branch must both render body + evidence trail inline. If the exclusive branch continues to call `append_evidence_trail` separately, the two-write race survives under summary-collision retries — negating AC1's contract.
2. **AC5 ordering: `_index_cache.pop(str(vec_path), None)` is called BEFORE `os.replace(tmp, vec_path)`.** On Windows, any cached `VectorIndex._conn` holds a read lock on `vec_path` that blocks `os.replace` with `PermissionError [WinError 5]`. Popping the cache entry closes (or abandons) the cached connection first. On POSIX the ordering doesn't matter for correctness but matters for consistency with Windows.
3. **AC9 LOCK_POLL_INTERVAL semantics.** Design-gate must decide (a) `LOCK_POLL_INTERVAL` becomes the CAP (monkeypatching to 0.001 clamps ALL sleeps to 0.001), OR (b) `LOCK_POLL_INTERVAL` is the fallback when exponential-backoff would otherwise exceed it. The regression test must pin the chosen semantic so future refactors cannot silently drift.

## Blast radius

- `src/kb/ingest/evidence.py` — `append_evidence_trail` sentinel search changes to section-anchored (AC14).
- `src/kb/ingest/pipeline.py` — `_write_wiki_page` (both branches: exclusive + non-exclusive); `_update_existing_page` + `_update_existing_page_body` (error-surfacing wrapper).
- `src/kb/query/embeddings.py` — `rebuild_vector_index` (atomic-rename pathway + cache-pop ordering); `VectorIndex.build` (db_path override kwarg).
- `src/kb/utils/io.py` — `file_lock` retry loop (exponential backoff); `LOCK_POLL_INTERVAL` semantics per design-gate.
- `BACKLOG.md` — HIGH-Deferred section pruned; CVE re-check dates bumped.
- `CHANGELOG.md` + `CHANGELOG-history.md` — Quick Reference + detail entries.
- `CLAUDE.md` — test count, any API doc for `VectorIndex.build(db_path=)`, evidence-trail sentinel-anchor note.

**Estimated test delta:** +13 to +18 new tests (4 Cluster A + 4 Cluster B + 2 Cluster C + 2 Cluster E + 1-2 sanity). Current count: 2743.

## References

- BACKLOG.md §Phase 4.5 HIGH (`ingest/pipeline.py` state-store fan-out, R2), HIGH-Deferred (`query/embeddings.py` vector-index lifecycle, `tests/` multiprocessing), MEDIUM (`utils/io.py` atomic_json_write + file_lock, `ingest/pipeline.py` + `ingest/evidence.py` page write vs evidence append).
- Cycle 23 merge: `acc859d` (PR #37) — closed HIGH-Deferred multiprocessing test coverage, shipped rebuild_indexes helper + `kb rebuild-indexes` CLI.
- Cycle 20 errors taxonomy: `kb.errors` module introduces `StorageError(msg, *, kind=None, path=None)` for filesystem-failure surfacing.
- Cycle 18 AC14: `_write_index_files` helper (partial for M10).
