# Cycle 26 — Requirements + Acceptance Criteria

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle26` (branched from `main` @ `17f8e72`)
**Scope:** Vector-index cold-load observability (HIGH-Deferred sub-items 1+2) + BACKLOG hygiene.

## Problem

Cycle 25 shipped the **dim-mismatch** observability sub-item of the HIGH-Deferred "vector-index lifecycle" entry (`query/embeddings.py`). Two remaining deferred sub-items feed the same operator pain:

1. **Cold-load latency invisibility.** `_get_model()` (embeddings.py:270) does a 0.8s + ~67 MB RSS singleton load on first vector use. No latency logging; no warm-up path. The first user query after server boot that touches vector search pays the full load on the user's critical path. Operators cannot distinguish "MCP slow" from "vector model loading".
2. **No warm-load hook at MCP startup.** `kb.mcp.__init__.main()` calls `_register_all_tools()` → `_mcp.run()`. The embedding model is never touched until a query fires. A warm-load background thread guarded on `vec_path.exists()` would let the server boot lean (no model when index absent) while eliminating cold-load penalty when the index is present.

Additionally, three BACKLOG entries are **stale relative to shipped code** (cycle-17 L1 BACKLOG-drift): the multiprocessing file_lock test item was shipped by cycle 23 AC7 (`test_cycle23_file_lock_multiprocessing.py`), but the BACKLOG entry at line 160-161 still reads as "open". Two CVE entries have date stamps from 2026-04-24 (cycle 25) that warrant today-dated re-verification per the bundled re-check cadence established in prior cycles.

## Non-goals

- **No auto-rebuild on dim-mismatch.** That sub-item requires `VectorIndex` to hold a `wiki_dir` reference or callback to call `rebuild_vector_index`; the design surface is bigger than this cycle's budget and involves decisions about idempotency under concurrent rebuild requests.
- **No ingest-side lock refactor.** The HIGH `ingest/pipeline.py` lock acquisition order risk item is deferred to a dedicated cycle.
- **No CVE patching of diskcache / ragas** — upstream has no fix released yet (re-verify only; no pin bumps).
- **No IndexWriter helper** (the `ingest/pipeline.py` index-file write order MEDIUM item) — separate cycle.
- **No `_update_existing_page` two-write consolidation** — separate cycle; requires deeper evidence-trail refactor.
- **No new security-enforcement surface** — this cycle adds a module-level counter, an info-level log line, a daemon background thread, and BACKLOG edits. No filesystem-write contracts, no trust-boundary changes.

## Acceptance Criteria

### Cluster A — Vector-index cold-load observability (5 ACs)

**AC1 — `maybe_warm_load_vector_model(wiki_dir)` helper.** New function in `kb.query.embeddings`:

```python
def maybe_warm_load_vector_model(wiki_dir: Path) -> threading.Thread | None: ...
```

- Returns `None` when `_hybrid_available is False` (model2vec / sqlite-vec not installed).
- Returns `None` when `_vec_db_path(wiki_dir).exists() is False` (no index to warm for).
- Returns `None` when `_model is not None` (already loaded — idempotent no-op).
- Otherwise starts a `threading.Thread(daemon=True)` calling `_get_model()`; returns the thread so tests can `.join(timeout=...)` and production can ignore it.
- Logs `logger.info("Warm-loading vector model in background (vec_db=%s)", vec_path)` on thread-start.

**Contract regression:** absent `vec_path` → `None` return; present `vec_path` → Thread object; double-call after first load returns None (idempotent).

**AC2 — Wire warm-load hook into MCP startup.** Update `kb.mcp.__init__.main()` to call `maybe_warm_load_vector_model(WIKI_DIR)` AFTER `_register_all_tools()` and BEFORE `_mcp.run()`. Import must be function-local (preserves cycle-23 AC4 boot-lean contract — bare `import kb.mcp` must not load embeddings module).

**Contract regression:** `import kb.mcp` leaves `kb.query.embeddings` out of `sys.modules`; `kb.mcp.main()` invocation imports embeddings and schedules the warm-load (mock `threading.Thread` to assert).

**AC3 — Cold-load latency instrumentation.** Extend `_get_model()` to measure elapsed time (`time.perf_counter`) of the `StaticModel.from_pretrained` call. On success:

- Always: `logger.info("Vector model cold-loaded in %.2fs", elapsed)`
- If `elapsed >= VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS` (new constant = `0.3`): also `logger.warning("Vector model cold-load exceeded %.2fs threshold (%.2fs actual). Consider warm-load on startup via maybe_warm_load_vector_model(wiki_dir).", THRESHOLD, elapsed)`.

Threshold is a module-level constant (not env-overridable in this cycle — KISS; env override is a future add).

**Contract regression:** monkeypatch `StaticModel.from_pretrained` with a stub that sleeps 0.5s; call `_get_model()`; assert both the info-level AND warning-level log messages fired (both pattern-matched from caplog).

**AC4 — Cold-load counter.** New module-level counter `_vector_model_cold_loads_seen: int` + public getter `get_vector_model_cold_load_count() -> int`. Mirror of cycle-25 `get_dim_mismatch_count()` pattern: incremented exactly once per successful `StaticModel.from_pretrained` return inside `_get_model()`. Approximate under concurrency (Q8 style — the double-checked lock already serialises cold-loads so realistically the counter is exact, but we don't assert strict equality in multi-thread tests).

**Contract regression:** `get_vector_model_cold_load_count()` starts at 0 (process boot); after `_get_model()` + `_reset_model()` + `_get_model()` the delta is 2.

**AC5 — Regression test file `tests/test_cycle26_cold_load_observability.py`.** Five tests minimum:

1. `test_maybe_warm_load_returns_none_when_vec_path_missing` — no vec DB on disk → `None` return, no thread spawned.
2. `test_maybe_warm_load_returns_thread_when_vec_path_exists` — seed vec DB → Thread returned; `.join(timeout=5)` succeeds.
3. `test_maybe_warm_load_idempotent_when_model_already_loaded` — force `_model = <sentinel>` → `None` return even with vec_path present.
4. `test_cold_load_logs_latency_info_and_warning` — monkeypatch `StaticModel.from_pretrained` with a 0.5s-sleeping stub; assert info log with "cold-loaded" AND warning log with "exceeded" both fire.
5. `test_cold_load_counter_increments_per_load` — counter delta equals number of `_reset_model()` + `_get_model()` cycles.

### Cluster B — BACKLOG + CVE hygiene (2 ACs)

**AC6 — Delete stale multiprocessing file_lock BACKLOG entry.** The `tests/test_phase4_audit_concurrency.py single-process file_lock coverage` MEDIUM entry (BACKLOG.md:160-161) is RESOLVED by `tests/test_cycle23_file_lock_multiprocessing.py` (shipped cycle 23 AC7). Grep confirms the test exercises `multiprocessing.Process` spawn, Event-based parent/child handshake, PID-file assertion, and is marked `@pytest.mark.integration`. Delete the BACKLOG entry; add brief closure note to CHANGELOG-history.md under the cycle 26 section (pointing back at cycle 23 AC7 as the actual ship).

**AC7 — CVE date-stamp re-verification.** Run `pip-audit --format=json 2>&1` against the installed venv; for `diskcache` (GHSA-w8v5-vhqr-4h9v) and `ragas` (GHSA-95ww-475f-pr4f), confirm `fix_versions` is still empty (no upstream patch). Update the two BACKLOG entries' inline date stamps (e.g., "Re-checked 2026-04-24 per cycle-26 AC7") AND update the CLAUDE.md "Latest full-suite count" narrative. No code change (no pin bump); documentation-only.

### Cluster C — BACKLOG scope narrowing (1 AC)

**AC8 — Narrow HIGH-Deferred vector-index lifecycle entry.** Update BACKLOG.md:109 `query/embeddings.py` vector-index lifecycle entry to reflect cycle-26 cold-load observability shipped (sub-item 2 partial — latency visibility + warm-load hook). Remaining true-deferred shrinks to: **auto-rebuild via VectorIndex callback** (sub-item 3 remainder) + **dim-mismatch auto-rebuild orchestration** (needs new design for concurrent-rebuild idempotency). Explicitly cite cycle 26 ACs 1-5 as the narrow-scope observability variant.

## Conditions (Step 5 decision gate must resolve)

1. **Q1 — Warm-load thread lifecycle on server shutdown.** `threading.Thread(daemon=True)` means the thread dies with the process; should we also provide a cancel mechanism? *Bias:* daemon-only (KISS). Don't add a cancel API until a production incident demands it.
2. **Q2 — Warm-load error swallowing.** If `_get_model()` inside the warm-load thread raises (network error downloading model, import failure at runtime), the daemon thread dies silently. Should we log the exception? *Bias:* yes — `logger.exception(...)` inside the warm-load wrapper; the thread dies but the log captures the failure for operators.
3. **Q3 — Cold-load latency log level.** Log at INFO always, or only WARN on threshold breach? *Bias:* both — INFO always so operators can audit boot history; WARN on breach for alerting.
4. **Q4 — Counter threading.** Match cycle-25 dim-mismatch counter (no lock, approximate under concurrency)? Or tighter (re-use `_model_lock`)? *Bias:* re-use `_model_lock` — the counter lives inside the double-checked-lock critical section anyway, so no extra lock cost. Exact counts under concurrency.
5. **Q5 — Threshold value.** 0.3s is aggressive; 1.0s would rarely fire in practice. *Bias:* 0.3s — matches the backlog item's "300ms" threshold spec; this is a WARN (not an alert), so false positives on slow CI machines are fine.
6. **Q6 — MCP startup warm-load failure surface.** If the warm-load thread fails to start (e.g. `threading.Thread().start()` raises `RuntimeError` under resource exhaustion), should `main()` continue? *Bias:* yes — swallow + log.warning; MCP must boot even without warm-load. The warm-load is an optimisation, not a correctness requirement.
7. **Q7 — Test file-lock threshold interaction with CI.** If threshold is 0.3s, does `test_cold_load_logs_latency_info_and_warning` reliably fire WARN on slow CI? *Bias:* yes — the test uses a deterministic 0.5s monkeypatched sleep, well above 0.3s threshold.
8. **Q8 — Warm-load from `kb compile` CLI.** Should `kb compile` also warm-load? *Bias:* NO — compile is a one-shot CLI invocation; the warm-load exists for long-lived MCP workers. Keep scope tight.

## Blast radius

- `src/kb/query/embeddings.py` — new helper + 3 new module-level names (counter, threshold, function); instrumented `_get_model()`.
- `src/kb/mcp/__init__.py` — one-line addition to `main()`.
- `tests/test_cycle26_cold_load_observability.py` — new file.
- `BACKLOG.md` — 2 entries edited, 1 deleted.
- `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md` — cycle 26 narrative.

**No changes to:** compile pipeline, ingest pipeline, refine flow, file_lock semantics, vector index DB schema, MCP tool registry, CLI entry points.
