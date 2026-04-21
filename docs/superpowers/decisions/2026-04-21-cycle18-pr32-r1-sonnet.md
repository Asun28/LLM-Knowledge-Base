# Cycle 18 PR #32 - R1 Sonnet Review

**Date:** 2026-04-21
**Reviewer:** claude-sonnet-4-6 (R3 independent round)
**Scope:** Edge cases, concurrency, security, test gaps.

---

## Verdict

**APPROVE-WITH-NITS**

---

## Blockers

None.

---

## Majors

### M1 - error_summary truncation is char-slicing, not byte-slicing

File: src/kb/ingest/pipeline.py:815

sanitize_text(err)[:_INGEST_JSONL_ERROR_SUMMARY_MAX] where the constant is 2048.
Python str[:n] counts code points. 2048 CJK characters encode to ~6144 UTF-8 bytes.
Design-gate Q20 justifies 2KB to stay under PIPE_BUF atomicity bounds, but that bound
is in bytes. With CJK error strings the row can exceed PIPE_BUF, undermining T7.

Fix: sanitize_text(err).encode("utf-8")[:2048].decode("utf-8", errors="ignore")

### M2 - scenario (c) LLM-count assertion inverted vs (a)/(b)

File: tests/test_workflow_e2e.py:240

assert counters["count"] == 0 is correct (both ingests use pre-provided extraction),
but calling it an anti-degeneracy assertion is misleading. The real anti-degeneracy
check is assert len(injected_into_first) >= 1 (non-vacuous). The count==0 assertion
means: if extraction-skipping regresses and LLM calls fire, test fails for that reason.
Low production risk; deserves a clarifying comment.

---

## Minors / NITs

### N1 - disk-full + failure emission: original exception preserved (confirmed)

If fsync raises OSError inside _emit_ingest_jsonl on the failure path, the helper
swallows it via its own try/except OSError. The outer except BaseException then
re-raises exc unchanged. No masking occurs. Design is correct.

### N2 - UNC regex does not misfire on //example.com/path (confirmed)

The ordinary UNC pattern at sanitize.py:17 requires literal backslash. Double-
forward-slash URLs do not match. Safe.

### N3 - rotate_if_oversized on symlink: asymmetry with append_wiki_log

append_wiki_log applies _reject_if_not_regular_file (lstat guard) before file_lock.
_emit_ingest_jsonl does not. If .data/ingest_log.jsonl is a symlink, path.rename()
on POSIX renames the symlink itself; subsequent appends open a fresh file at the
canonical path while old data lives under the original target. LOW risk in practice.

### N4 - inject_wikilinks timeout on all candidates: not silent (confirmed)

Each timed-out page emits a WARNING (linker.py:305) and loop continues.
ingest_source returns wikilinks_injected=[]. Recoverable on next ingest. Correct.

### N5 - _write_index_files failure not surfaced in result dict

Both helpers have always been best-effort/warn-pass-through. The new wrapper
preserves that contract. Not a regression; no change required.

### N6 - test_jsonl_rotation_inside_lock deferred PROJECT_ROOT import

_emit_ingest_jsonl uses from kb import config at call time, not module load time.
The test patches pipeline.PROJECT_ROOT before the call. Patch is honoured. Correct.

---

## Vacuous-test audit

AC4 (rotate-in-lock): If rotate moves back outside the lock, rotate_idx precedes
lock_enter_idx and assert lock_enter_idx < rotate_idx fails. Non-vacuous.

AC7 (TOCTOU re-read): test_inject_wikilinks_toctou_skip returns already-linked content
on second read_text. If under-lock re-read removed, one read fires (original content),
pattern matches, atomic_text_write fires, assert match_page not in write_calls fails.
Non-vacuous.

AC11 (failure emission): If except BaseException removed, only start emits and
stages == ["start", "failure"] assertion fails. Non-vacuous.

AC13 (redaction): If sanitize_text call dropped, raw paths appear in JSONL row and
the not-in assertions on Windows/UNC/POSIX paths all fail. Non-vacuous.

AC14 (independent failure): If shared try/except regresses the helper,
_update_index_batch never runs and assert "index" in calls fails. Non-vacuous.

AC16 scenario (c): If inject_wikilinks is no-op'd, wikilinks_injected == [] and
assert len(wikilinks_injected) >= 1 fails. Non-vacuous.

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MAJOR    | 2     | warn   |
| MINOR    | 6     | info   |

Verdict: APPROVE-WITH-NITS. M1 (char-vs-byte truncation) is the only functional gap
and only manifests with CJK-heavy error strings; ASCII error messages are unaffected.
M2 is a test-readability concern with no production risk. All 10 threats from the
threat model are implemented and covered by non-vacuous tests. Safe to merge.
