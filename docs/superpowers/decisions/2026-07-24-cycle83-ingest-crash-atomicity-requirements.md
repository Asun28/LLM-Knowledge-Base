# Cycle 83 — Ingest crash-atomicity requirements

## Problem

`ingest_source` emits a JSONL `start` row and then `_check_and_reserve_manifest` writes the bare content hash to the manifest before `_run_ingest_body` starts (`src/kb/ingest/pipeline.py:1323-1362`); the body subsequently creates or updates summary, entity, and concept pages and index files (`pipeline.py:1481-1590`), reconfirms that same bare hash at `pipeline.py:1598-1604`, and only then performs the wiki-log, affected-page, wikilink, contradiction, and vector-index work before returning at line 1751. An interrupted run after the early bare-hash write can therefore leave zero or partial downstream effects while `find_changed_sources` treats a matching bare hash as unchanged (`src/kb/compile/compiler.py:177-186`). The existing `in_progress:` value is already retryable, is scanned on compile entry, and is exempt from both prune paths (`compiler.py:418-440`, `189-198`, `551-560`), but `compile_wiki` currently creates it only around its own call and direct CLI, MCP, and lint-augmentation callers enter `ingest_source` without that protection (`src/kb/cli.py:172-179`, `src/kb/mcp/ingest.py:140-268`, `312-443`, `src/kb/lint/augment/orchestrator.py:452-459`). In addition, `_check_and_reserve_manifest` swallows every reservation exception and continues (`pipeline.py:269-287`). Cycle 83 must make the manifest value at the shared `ingest_source` boundary mean “in progress” until the complete body returns, fail closed when that reservation cannot be persisted, and publish the bare hash only as the final commit so no caller can turn an interrupted ingest into an incrementally suppressed source.

## Verification table

| Brief-cited symbol or claim | Verified file:line | Status | Verification result |
|---|---:|---|---|
| `ingest_source` | `src/kb/ingest/pipeline.py:1139` | EXISTS | Shared single-source entry point; the reservation call is at line 1339 and body call at line 1362. |
| `_run_ingest_body` | `src/kb/ingest/pipeline.py:1420` | EXISTS | Performs page and downstream writes and returns at line 1751. |
| `load_manifest` | `src/kb/compile/compiler.py:82` | EXISTS | Reads JSON and returns `{}` on missing or corrupt/unreadable input. |
| `save_manifest` | `src/kb/compile/compiler.py:98` | EXISTS | Delegates to `atomic_json_write` at lines 100-103. |
| `compile_wiki` | `src/kb/compile/compiler.py:381` | EXISTS | Calls `find_changed_sources` in incremental mode and `ingest_source` per selected source. |
| Changed-source diff attributed to `compile_wiki` | `src/kb/compile/compiler.py:144-186`, `443-445` | SEMANTIC-MISMATCH | The comparison is implemented by `find_changed_sources`; `compile_wiki` delegates to it. |
| `HASH_MANIFEST` | `src/kb/compile/compiler.py:32` | EXISTS | Default path is `PROJECT_ROOT / ".data" / "hashes.json"`. |
| `file_lock` | `src/kb/utils/io.py:389` | EXISTS | Cross-process sidecar lock with exponential-backoff polling; `page_lock.py:3-5` confirms it is deliberately non-reentrant. |
| `atomic_json_write` | `src/kb/utils/io.py:174` | EXISTS | Writes and fsyncs a sibling temp file, then replaces the destination at line 196. |
| `page_lock` | `src/kb/utils/page_lock.py:92` | EXISTS | Reentrant only for the same thread and normalized page key; outer acquisition delegates to `file_lock` at line 145. |
| `_emit_ingest_jsonl` | `src/kb/ingest/pipeline.py:926` | EXISTS | Appends under a lock; `OSError` is warning-only at lines 1001-1015. |
| JSONL `start` with no terminal row is a partial-ingest oracle | `src/kb/ingest/pipeline.py:949-952`, `1013-1015`, `1316-1339` | SEMANTIC-MISMATCH | `start` precedes extraction, validation, and reservation, and the writer is best-effort; an orphan row proves an interrupted telemetry envelope, not that wiki mutation began. |
| `_check_and_reserve_manifest` | `src/kb/ingest/pipeline.py:254` | EXISTS | Under `file_lock`, it checks duplicates and writes `manifest[source_ref] = source_hash` at lines 273-284 before the body. |
| Reservation exceptions are swallowed | `src/kb/ingest/pipeline.py:285-287` | EXISTS | Every `Exception` is logged at DEBUG and the function returns “not duplicate,” allowing ingest to continue. |
| `_write_wiki_page` | `src/kb/ingest/pipeline.py:306` | EXISTS | Summary call is at lines 1493-1501; item-page call is at lines 1123-1125. |
| `_update_existing_page` | `src/kb/ingest/pipeline.py:535` | EXISTS | Summary update calls are at lines 1483 and 1507; item updates are at lines 1111-1113 and 1131-1133. |
| `_process_item_batch` | `src/kb/ingest/pipeline.py:1018` | EXISTS | Entity and concept batches are invoked at lines 1529 and 1545. |
| `_write_index_files` | `src/kb/ingest/pipeline.py:885` | SEMANTIC-MISMATCH | It calls only `_update_sources_mapping` and `_update_index_batch` at lines 902-909, so the brief's `_categories.md` claim is wrong. |
| Ingest write to `_categories.md` | `src/kb/ingest/pipeline.py` (no match); `src/kb/lint/checks/dead_links.py:133` | MISSING | The repository states `_categories.md` was designed but never written by the system. |
| `append_wiki_log` | `src/kb/utils/wiki_log.py:71`; call at `src/kb/ingest/pipeline.py:1618` | EXISTS | Ingest appends after the current manifest confirmation. |
| `_find_affected_pages` | `src/kb/ingest/pipeline.py:95`; call at line 1631 | EXISTS | Runs after the current manifest confirmation. |
| `inject_wikilinks_batch` | `src/kb/compile/linker.py:324`; call at `src/kb/ingest/pipeline.py:1652` | EXISTS | Can mutate pre-existing pages after the current manifest confirmation. |
| `_persist_contradictions` | `src/kb/ingest/pipeline.py:184`; call at line 1705 | EXISTS | Writes `wiki/contradictions.md` under a lock. |
| `rebuild_vector_index` | `src/kb/query/embeddings.py:281`; call at `src/kb/ingest/pipeline.py:1741` | EXISTS | Tail operation runs after contradiction processing unless suppressed for a batch caller. |
| `compile_wiki` pre-call `in_progress:{pre_hash}` marker | `src/kb/compile/compiler.py:474-495` | EXISTS | The marker save is best-effort and occurs before the compile-layer `ingest_source` call. |
| Stale-marker scan and prune exemptions | `src/kb/compile/compiler.py:418-440`, `189-198`, `551-560` | EXISTS | Compile warns for marker-valued entries and both prune paths retain them. |
| Marker values do not suppress incremental retry | `src/kb/compile/compiler.py:181-186` | EXISTS | A marker differs from the current bare hash, so the source is classified as changed. |
| Compile custom-manifest continuity into `ingest_source` | `src/kb/compile/compiler.py:503-508`; `src/kb/ingest/pipeline.py:1598-1604` | SEMANTIC-MISMATCH | `compile_wiki` passes `manifest_key` but not its effective `manifest_path`; ingest confirmation falls back to global `HASH_MANIFEST`. |
| CLI `kb ingest` direct call | `src/kb/cli.py:164-179` | EXISTS | The command imports and calls `ingest_source` directly. |
| MCP `kb_ingest` direct calls | `src/kb/mcp/ingest.py:140`, `230`, `268` | EXISTS | API and supplied-extraction branches call the owner-module `ingest_source`. |
| MCP `kb_ingest_content` direct calls | `src/kb/mcp/ingest.py:312`, `441-443` | EXISTS | Both extraction modes call the owner-module `ingest_source`. |
| Direct callers are limited to CLI and MCP | `src/kb/lint/augment/orchestrator.py:386`, `452-459` | SEMANTIC-MISMATCH | Lint augmentation is another production direct caller. |
| `kb compile --full` is the only recovery route | `src/kb/ingest/pipeline.py:275-284`; `src/kb/cli.py:552-591`; `src/kb/compile/compiler.py:688-742` | SEMANTIC-MISMATCH | Same-key direct re-ingest is not rejected as a duplicate, and `kb rebuild-indexes` clears the manifest so the next compile re-ingests all sources. |

## Non-goals

**Decision and assumption.** Cycle 83 selects option A with two necessary refinements: the marker belongs at the shared `ingest_source` boundary, and the bare-hash confirmation is moved out of `_run_ingest_body` so it occurs only after that body returns. The manifest is already the incremental scheduler and already understands retryable marker values; reusing it has a smaller state and test surface than option B. The JSONL log cannot be the recovery authority because its writer is explicitly best-effort, while a receipt directory would introduce a second state machine without itself rolling back overwritten pages. The explicit assumption is that retrying an interrupted ingest is the repair mechanism for this cycle; exact multi-file transactional rollback is not required.

1. Do not add `.data/ingest_locks/`, step receipts, a recovery scanner, or a new on-disk manifest format.
2. Do not snapshot or roll back wiki pages, index files, logs, injected links, contradictions, or the vector index.
3. Do not redesign the duplicate-content policy, page/index idempotency rules, or best-effort status of log, wikilink, contradiction, and vector-index operations except where a propagated exception must prevent the final bare-hash commit.
4. Do not change `file_lock`, `page_lock`, `atomic_json_write`, or add a runtime dependency.
5. Do not make CLI-, MCP-, compile-, or augmentation-specific recovery logic; protection must come from their existing call into `ingest_source`.

## Acceptance criteria

AC01 — Every non-duplicate `ingest_source` invocation persists `in_progress:{source_hash}` at the effective `manifest_ref`, under the manifest `file_lock`, after extraction validation and before `_run_ingest_body` or any wiki mutation begins; this single boundary protects CLI, MCP, compile, and lint-augmentation callers. Pinned by `test_ingest_source_persists_marker_before_body`.

AC02 — If the reservation lock, manifest load, or marker save fails, `ingest_source` propagates the failure, emits no `success` row, and does not call `_run_ingest_body` or mutate any wiki page or index. Pinned by `test_ingest_source_reservation_failure_is_fail_closed`.

AC03 — A pre-existing `in_progress:{source_hash}` at the same manifest key is retryable: it is not reported as a duplicate, and the ingest body proceeds. Pinned by `test_same_key_in_progress_marker_is_retryable`.

AC04 — A matching bare hash or `in_progress:{source_hash}` under a different, still-existing source key remains a duplicate reservation: the second ingest returns `duplicate=True` without entering the body, preserving cross-process identical-content exclusion. Pinned by `test_cross_key_in_progress_marker_blocks_duplicate_body`.

AC05 — When a normal exception propagates after reservation but before final commit, the manifest contains `failed:{source_hash}` under the same lock, the existing JSONL terminal stage is `failure`, and the existing exception taxonomy is preserved. Pinned by `test_body_exception_records_failed_retry_state`.

AC06 — Abrupt process termination after reservation and before final commit leaves `in_progress:{source_hash}` durably present; a parent process can inspect the marker after terminating a child at a post-reservation barrier. Pinned by `test_hard_kill_after_reservation_leaves_marker`.

AC07 — On success, the bare `source_hash` is saved to the same manifest path and key only after `_run_ingest_body` has returned; a late-body spy observes the marker, and the completed call observes the bare hash with no remaining marker. Pinned by `test_success_commits_bare_hash_only_after_body_return`.

AC08 — If the final bare-hash save fails, `ingest_source` propagates the failure, emits `failure` and no `success`, and leaves a retryable `in_progress:` or `failed:` value rather than falsely committing the bare hash; already-written wiki effects are not rolled back. Pinned by `test_final_manifest_save_failure_remains_retryable`.

AC09 — `compile_wiki(..., manifest_path=custom)` threads that exact effective path into `ingest_source`; marker, failure-state if any, and final-hash writes for the source occur only in the custom manifest, and the default manifest remains untouched. Pinned by `test_compile_custom_manifest_uses_one_marker_lifecycle`.

AC10 — Existing manifests require no migration: an unchanged source with a legacy bare hash remains an incremental no-op, while `failed:{hash}` and `in_progress:{hash}` values schedule retry and remain exempt from the existing prune rules. Pinned by `test_manifest_state_backward_compatibility_and_retry`.

## Blast radius

Expected production changes under `src/kb/` are limited to:

- `src/kb/ingest/pipeline.py` — change reservation values and error handling, make marker-valued duplicate comparison safe, move final manifest confirmation to the outer success boundary, and accept/use the effective manifest path.
- `src/kb/compile/compiler.py` — pass its effective `manifest_path` into `ingest_source` and reconcile the compile-owned pre-marker/failure bookkeeping without adding another state store.

`src/kb/utils/io.py`, `src/kb/utils/page_lock.py`, `src/kb/utils/wiki_log.py`, `src/kb/compile/linker.py`, and `src/kb/query/embeddings.py` are dependencies to reuse, not expected edit targets.

Existing tests most at risk are:

| Existing test | Risk |
|---|---|
| `tests/test_cycle25_compile_wiki_in_progress.py` | Pins compile-owned pre-marker timing, stale-marker warnings, prune exemptions, and normal-exception conversion to `failed:`. |
| `tests/test_compile.py::test_compile_loop_does_not_double_write_manifest` | Pins exactly two manifest saves per source and describes the current compile-marker ownership. |
| `tests/test_cycle19_manifest_key_consistency.py::test_manifest_key_threaded_to_both_writes` and `::test_compile_wiki_threads_manifest_key` | Pin the key passed to reservation and the current early confirmation, but do not currently pin custom manifest-path continuity. |
| `tests/test_cycle18_ingest_observability.py::{test_jsonl_emitted_on_success,test_jsonl_emitted_on_duplicate,test_jsonl_emitted_on_failure}` | Pin the `start` plus exactly one terminal-stage contract and exception taxonomy. |
| `tests/test_cycle64_graph_cache.py::test_ingest_source_invalidates_graph_cache` | Stubs `_check_and_reserve_manifest` with a two-argument lambda and `_run_ingest_body`; a signature or finalization move can break the fixture rather than behavior. |
| `tests/test_v099_phase39.py` duplicate-content tests and `tests/test_ingest.py` duplicate result-shape/concurrency tests | Pin bare-hash identical-content dedup and duplicate return behavior that marker-aware comparison must preserve. |
| `tests/test_compiler_mcp_v093.py`, `tests/test_v0913_phase394.py`, and `tests/test_cycle17_compile_manifest.py` failure-path tests | Pin `failed:{pre_hash}` retry state and locked compiler exception-path writes. |