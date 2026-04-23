# Cycle 25 — Brainstorming (Step 3)

**Date:** 2026-04-24
**Inputs:** requirements.md (10 ACs + 8 CONDITIONS), threat-model.md (6 threats, all bounded).

Per `feedback_auto_approve`: no user gates. Step 5 Opus gate is the approval mechanism. Brief since scope is narrow and approaches are constrained.

## Cluster A — `rebuild_indexes .tmp` awareness

### A1 — Extend vector-DB cleanup block in-place (RECOMMENDED)
Add `tmp_path.unlink(missing_ok=True)` immediately after `vec_path.unlink()` in the same try/except. On OSError, concatenate the error string so the caller sees BOTH failures (`"vec: <err_a>; tmp: <err_b>"`). Minimal diff; no new error-status field.

### A2 — Separate try/except for tmp
More error-class fidelity: tmp failure doesn't blank out `result["vector"]["cleared"]` if the main unlink succeeded. Slightly larger diff.

### Recommendation — **A2**. Keeps status bit accurate (CONDITION 1). AC1 explicitly requires this semantic.

## Cluster B — Dim-mismatch operator guidance

### B1 — Extend warning message inline (RECOMMENDED)
Update the f-string in `VectorIndex.query` to include `"Run 'kb rebuild-indexes --wiki-dir <path>' to realign"`. Add module-level `_dim_mismatches_seen: int = 0` counter + `get_dim_mismatch_count()` getter. Increment counter on every mismatch-detected query.

### B2 — Structured telemetry dict
Emit a dict through a callback or return channel. More observable but widens `VectorIndex.query`'s return shape — breaking change for callers. Not needed for this cycle's observability goal.

### Recommendation — **B1**. Matches AC3 + AC4 literally; no API break.

## Cluster C — `compile_wiki` per-source in-progress marker

### C1 — Pre-marker + overwrite via manifest_key (RECOMMENDED)
Before `ingest_source`, write `in_progress:{pre_hash}` into `manifest[rel_path]` under `file_lock(manifest_path)`. `ingest_source` (via cycle-19 AC13 `manifest_key=rel_path`) overwrites it on success. The existing `except Exception` replaces with `failed:{pre_hash}`. Startup scan at `compile_wiki` entry greps manifest for `in_progress:` prefix, logs warnings per stale marker (does NOT delete — operator remediates).

### C2 — Receipt-file design (`.data/ingest_locks/<hash>.json`)
The original M2 BACKLOG fix. Separate file per in-flight ingest with enumerated completion steps; recovery pass reads and completes/cleans. Much bigger scope — defer.

### Recommendation — **C1**. Matches AC6/AC7/AC8. C2 remains deferred.

## Cluster D — BACKLOG + CVE

### D1 — Standard cycle-24 pattern (RECOMMENDED)
Run pip-audit + pip index; update dates if unchanged, bump requirements.txt if new fix available. Delete resolved BACKLOG entry; add CHANGELOG entry.

### Recommendation — **D1**. Same pattern as cycle-24 AC12/AC13.

## Open questions for Step-5 decision gate

1. **Q1 — AC1 error semantics**: compound error message (`"vec: ...; tmp: ..."`) or only the primary error? Recommend compound — gives operator full picture.
2. **Q2 — AC7 deletion policy**: log-only (recommended) or auto-delete stale markers with a grace window? Recommend log-only — operator decides.
3. **Q3 — AC4 counter reset**: expose a `reset_dim_mismatch_count()` helper for tests, or just read-only? Recommend read-only + tests rely on monotonic observation.
4. **Q4 — AC6 lock timeout**: 1.0s (match cycle-23 `rebuild_indexes` convention) or 5.0s (match cycle-2 default)? Recommend 1.0s for fast-failure.
5. **Q5 — AC6 marker placement timing**: before `content_hash(source)` (so a hash-raise is still tracked) or after (so we only track sources we can compute the hash of)? Currently pre_hash is computed BEFORE the try at line 432-435; recommend placing the marker AFTER pre_hash is known but BEFORE the try (so SIGKILL between the pre-marker and `ingest_source` leaves a marker with a valid hash).
6. **Q6 — test test_cycle25_compile_wiki_in_progress_marker_on_hard_kill**: simulate hard-kill by directly seeding the manifest (primary recommendation) vs `multiprocessing.Process.kill`. Recommend seeded approach — faster, more portable.
