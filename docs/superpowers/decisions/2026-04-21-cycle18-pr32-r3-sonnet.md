# Cycle 18 PR #32 - R3 Sonnet Review

**Date:** 2026-04-21
**Reviewer:** claude-sonnet-4-6 (R3 synthesis round)
**Scope:** Integration gaps between R1 fixes, doc drift, contract coherence, vacuous-test probes.

---

## Verdict

**APPROVE**

---

## R1 fix quality

Both R1 fixes integrate cleanly with no cross-fix regressions.

**R1 Codex BLOCKER (try/except boundary):** The `_emit_ingest_jsonl("start")` call now lands at `pipeline.py:1079`, immediately followed by `try:` at `pipeline.py:1081`. `extract_from_source`, `_pre_validate_extraction`, `_check_and_reserve_manifest`, `_run_ingest_body`, and the success emission are all inside that try. The `except BaseException` at `pipeline.py:1141` fires on any exception from any of these steps. The duplicate-skip return at `pipeline.py:1099` is a normal return inside the try — `except BaseException` does not intercept it. Envelope is correct: every `start` row gets exactly one terminal row.

**R1 Sonnet M1 (byte truncation):** The chain at `pipeline.py:819-822` is `sanitize_text(err).encode("utf-8")[:2048].decode("utf-8", errors="ignore")`. The `errors="ignore"` disposition is the correct choice here — it silently drops the trailing partial byte sequence rather than inserting a replacement character (`�`) that would grow the decoded string and potentially re-exceed an external PIPE_BUF boundary assumption. No interaction with the try/except change.

**Potential double-emit on `KeyboardInterrupt` during success emission:** `_emit_ingest_jsonl("success")` at `pipeline.py:1129` is inside the same `try` as the body. If it raises (e.g. `KeyboardInterrupt` during `json.dumps` or an internal `file_lock` call that itself raises something other than `OSError`), the `except BaseException` fires and emits a `failure` row after the `success` row. This is a theoretical TOCTOU on the telemetry envelope itself — a `success` + `failure` sequence for the same `request_id`. In practice, `json.dumps` on the row dict (all primitives) and `_emit_ingest_jsonl`'s internal `OSError` guard make this path nearly unreachable. The risk is LOW and consistent with the "best-effort telemetry" design contract in Q8.

---

## New findings

None that rise above LOW. The `contradictions` key is conditionally absent from `_run_ingest_body`'s return dict (only set when `contradiction_warnings` is truthy at `pipeline.py:1406-1407`), while the duplicate-skip path always includes `"contradictions": []` (`pipeline.py:1109`). All known callers in `compiler.py` use `.get("pages_created", [])` style access so the missing key is not a runtime bug, and the prior contract pre-cycle-18 was identical. Not a regression.

---

## Doc drift scan

One stale comment fragment found: `wiki_log.py:140` reads "previous 'rotate outside lock' ordering" — this describes the OLD behavior being fixed, which is correct and intentional historical context. No doc drift.

`CHANGELOG.md` entry accurately describes all four R1 fixes with correct file:line references. `BACKLOG.md` still contains the open item at line 489 for `inject_wikilinks_batch` (cycle-18 AC7 scalar lock as a stepping stone), which is correctly deferred — not a doc drift issue.

No stale references to `_rotate_log_if_oversized` as a public API, no stale "success emitted in body" language, no orphan BACKLOG items from the closed cycle-18 ACs.

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MEDIUM   | 0     | pass   |
| LOW      | 1     | note   |

The LOW is the theoretical double-emit on `KeyboardInterrupt` during success emission, consistent with Q8 best-effort contract. All five R3 focus checks pass: try/except boundary is watertight, `pages_created`/`pages_updated`/`pages_skipped` are always lists in `_run_ingest_body`'s return dict (initialized at `pipeline.py:1174-1176`), `errors="ignore"` is the correct byte-truncation disposition, no doc drift, and all pinned regression tests are non-vacuous per the R1 Sonnet vacuous-test audit. R2 Codex full-suite count (2587 passed) confirms no regressions.

Verdict: APPROVE — no blockers or majors; safe to merge.
