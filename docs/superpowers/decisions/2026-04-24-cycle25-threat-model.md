# Cycle 25 — Threat Model

**Date:** 2026-04-24
**Scope:** Step-1 AC1-AC10 + C1-C8 in `2026-04-24-cycle25-requirements.md`. Surfaces: `rebuild_indexes` `.tmp` unlink, `VectorIndex.query` dim-mismatch remediation message + counter, `compile_wiki` per-source `in_progress:` marker, BACKLOG + CVE maintenance.

## Analysis

All four cycle-25 changes land on surfaces that already crossed a trust boundary in earlier cycles; none of them opens a new boundary. The `.tmp` unlink (AC1) is a hygiene extension of the cycle-23 `rebuild_indexes` sibling — it reuses the same `_vec_db_path(wiki_dir)`-derived parent and inherits cycle-23's dual-anchor `PROJECT_ROOT` containment, so no new path-escape surface exists. The dim-mismatch message (AC3) changes only the content of an existing `logger.warning` and does NOT introduce any new sink; the operator remediation string (`kb rebuild-indexes --wiki-dir <path>`) echoes back the path the operator already supplied to the VectorIndex constructor, so no new information leaves the process. The `_dim_mismatches_seen` counter (AC4) is a module-level Python int with no network/disk persistence — its only observer is the Python process itself and any in-process test that imports `get_dim_mismatch_count`. The `compile_wiki` `in_progress:{pre_hash}` marker (AC6) writes into the SAME `manifest[rel_path]` slot that `ingest_source` will overwrite; no new manifest-key namespace is introduced, so downstream consumers (lint, drift detection) that already tolerate `failed:{hash}` markers from cycle-17 will see `in_progress:{hash}` as a structurally identical sibling.

The most operationally sensitive risk is the `in_progress:` detection at `compile_wiki` entry (AC7). Per C5, the pre-marker write does NOT hold a lock across `ingest_source`, and `ingest_source` acquires its own manifest lock per cycle-19 AC13. This is correct — nested locks would self-deadlock per cycle-20 L1 — but it creates a race window where a SECOND `compile_wiki` invocation in a parallel process could read the first process's `in_progress:{hash}` and emit a false-positive warning (T3). The requirements doc explicitly accepts this: AC7 does NOT auto-delete markers, so the false-positive is operator-visible but non-destructive (the operator decides whether to investigate). For a single-user personal-KB workflow this is acceptable; the threat is bounded because `compile_wiki` is not a multi-tenant surface. The dim-mismatch counter (AC4) has a theoretical integer-overflow risk (T4) on a 32-bit platform, but Python 3 ints are arbitrary-precision — no overflow, only an eventual memory-consumption risk that would require >10^12 mismatch events per process. Out of threat budget for cycle 25. The CVE re-verification (AC9) inherits the cycle-22 L4 "late-arrival" pattern and uses the same four-gate model.

## Verdict

**APPROVE — proceed to Step 2 (baseline safety scan).** All enumerated threats are either bounded by existing cycle-17/19/20/23 safeguards or explicitly out-of-scope per requirements. No new trust boundary introduced.

## Findings

### 1. Trust boundaries
- **AC1 `.tmp` unlink:** crosses the filesystem boundary under `<wiki_dir>/../.data/` — same boundary as cycle-23 `rebuild_indexes`. Dual-anchor containment (compiler.py:585-594) already guards.
- **AC3 dim-mismatch message:** no new boundary; message stays in-process.
- **AC4 counter:** no boundary — module-level Python int.
- **AC6/AC7 `in_progress:` marker:** writes to `HASH_MANIFEST` (`.data/hashes.json`) under `file_lock`; same boundary as cycle-19 AC13.
- **AC6/AC7 log.md:** `compile_wiki` already appends one line at tail via `append_wiki_log`; `logger.warning` for AC7 stale markers stays in logs (not log.md).

### 2. Data classification
- **in_progress marker bytes:** `f"in_progress:{pre_hash}"` — hash is SHA-256 of source bytes, public-derivable, not secret. Source path (`rel_path`) is already stored as the manifest key in plain text; no new PII.
- **Dim-mismatch counter:** integer event count, non-observable to external attackers unless they can import `kb.query.embeddings` (which implies already executing in-process). Not in telemetry, not logged to disk.

### 3. Authn/authz
- **`.tmp` unlink file ownership:** inherits from cycle-23 — `Path.unlink` does not follow symlinks (the tmp file itself is removed, not any symlink target); `missing_ok=True` tolerates concurrent deletion.
- **log.md append:** `compile_wiki` tail append is unchanged by cycle 25. AC7 stale-marker detection emits `logger.warning` only — does NOT write log.md.

### 4. Logging/audit
- **`compile_wiki` does NOT emit `in_progress:` to `.data/ingest_log.jsonl`.** The manifest itself IS the audit trail for in-progress state; AC6/AC7 deliberately avoid a second audit sink to prevent divergence. `(deferred to backlog: §Phase 4.5 — ingest_log.jsonl in-progress mirror)`.
- **Dim-mismatch counter NOT in telemetry.** Cycle 25 scope is observability-for-tests; exporting to Prometheus/OpenTelemetry is `(deferred to backlog: §Phase 6 — observability stack)`.
- **AC7 stale marker:** uses `logger.warning("compile_wiki: stale in_progress:%s marker for %s", hash, source)` — anchored on `logger`, not `append_wiki_log`.

### 5. Enumerated threats

**T1 — `.tmp` unlink on symlinked `.data/` escape.** `<vec_db>.tmp = vec_path.parent / (vec_path.name + ".tmp")`. If an attacker plants `.data` as a symlink to `/etc`, `tmp_path.unlink` could target `/etc/vector_index.db.tmp`. **Mitigation:** cycle-23 AC2 dual-anchor containment at compiler.py:585-594 rejects symlinked `wiki_dir` before the unlink runs; `vec_path` is derived from `_vec_db_path(effective_wiki)` which is bounded under the validated wiki dir. `Path.unlink` does NOT follow symlinks on the tmp file itself (removes the link, not the target). Residual risk: LOW.

**T2 — `in_progress:` marker accumulation under concurrent compile_wiki + rebuild-indexes race.** If `rebuild_indexes` unlinks the manifest between compile_wiki's pre-marker write and `ingest_source`'s overwrite, the marker is lost (acceptable — next compile re-detects the source as new). If `rebuild_indexes` runs AFTER pre-marker but BEFORE `ingest_source` fails, the `failed:` replacement writes to a fresh manifest (acceptable — cycle-17 AC3 idempotent RMW under `file_lock`). **Mitigation:** cycle-19 AC13 lock ordering + cycle-23 AC2 `file_lock` with 1s timeout. Residual risk: LOW.

**T3 — `in_progress` detection false-positives from legitimate in-flight compiles in another process.** AC7 runs the stale-marker check ONCE per `compile_wiki` invocation at loop entry. If a second `compile_wiki` starts while the first is mid-flight, it reads the first's `in_progress:` and logs a warning. **Mitigation:** warning-only (no auto-delete); operator judgment. Consider documenting in CLAUDE.md that concurrent `kb compile` invocations emit spurious stale-marker warnings. Residual risk: LOW-MEDIUM (cosmetic). `(deferred to backlog: §Phase 4.5 — compile_wiki concurrency docs)`.

**T4 — dim-mismatch counter integer overflow under adversarial load.** Python 3 ints are arbitrary-precision; no overflow. Memory bound requires ~10^12 mismatch events per process lifetime to exceed a few MB. Not exploitable. Residual risk: NEGLIGIBLE.

**T5 — logger.warning message containing wiki_dir path leaks absolute path on Windows.** The AC3 message format includes `self.db_path` and `%s` for wiki_dir (which on Windows is `D:\Projects\...`). If logs are shipped to a multi-tenant aggregator, the absolute path leaks. **Mitigation:** matches cycle-20 StorageError `<path_hidden>` pattern for persistent stores, BUT `logger.warning` on a developer-local log is an accepted boundary per cycle-20 L3 (StorageError redaction applies to exceptions, not log messages). Residual risk: LOW — document the leak surface.

**T6 — CVE late-arrival (cycle-22 L4 class).** Between Step 2 baseline and Step 15 merge, a new CVE for diskcache/ragas/anthropic/mcp could drop. **Mitigation:** cycle-22 L4 four-gate model (Step 2 + Step 11 + Step 12.5 + Step 15 warn). AC9 explicitly re-runs pip-audit at Step 11.5. Residual risk: LOW.

### 6. Deferred-to-BACKLOG tags
- Auto-rebuild on dim-mismatch → `(deferred to backlog: §Phase 4.5 HIGH-Deferred vector-index lifecycle sub-item 3)` per requirements §Non-goals.
- `_update_existing_page` consolidation → `(deferred to backlog: §Phase 4.5 MEDIUM M2)`.
- `utils/io.py` fair-queue lock → `(deferred to backlog: §Phase 4.5 io.py)`.
- `config.py` split → `(deferred to backlog: §Phase 4.5 config.py)`.
- ingest_log.jsonl `in_progress` mirror (T4 finding) → `(deferred to backlog: §Phase 4.5 — add after cycle 25 merge)`.
- Prometheus/OpenTelemetry dim-mismatch export (T4 finding) → `(deferred to backlog: §Phase 6 — observability)`.

### 7. Step-11 verification checklist

| Threat | Testable grep |
|--------|---------------|
| T1 | `grep -n 'tmp_path.*unlink\|name + ".tmp"' src/kb/compile/compiler.py` returns AC1's added line inside the vector-DB try/except, NOT outside the dual-anchor containment block. |
| T2 | `grep -n 'in_progress:' src/kb/compile/compiler.py` shows exactly TWO sites: the pre-marker write and the AC7 loop-entry scan; no third occurrence outside `file_lock`. |
| T3 | `grep -n 'stale in_progress' src/kb/compile/compiler.py` returns the AC7 `logger.warning` exactly once; no `manifest_path.unlink()` or `del manifest[` near it (no auto-delete). |
| T4 | `grep -n '_dim_mismatches_seen\s*+=' src/kb/query/embeddings.py` returns exactly one `+= 1` increment line, AND `grep -n 'def get_dim_mismatch_count' src/kb/query/embeddings.py` returns exactly one accessor. |
| T5 | `grep -n "kb rebuild-indexes" src/kb/query/embeddings.py` returns the AC3 operator-action string; `grep -n '<path_hidden>' src/kb/query/embeddings.py` returns zero (message is developer-log, not persistent-audit — intentional per cycle-20 L3). |
| T6 | `grep -n 'pip-audit\|pip index versions' docs/superpowers/decisions/2026-04-24-cycle25-*.md` returns the AC9 Step-11.5 invocations; BACKLOG.md lines 134+137 date stamps updated only if `pip-audit --format=json` shows `fix_versions: []` for both diskcache and ragas. |

---

**Word count:** ~590 words (analysis + findings, excluding verdict header and table).
