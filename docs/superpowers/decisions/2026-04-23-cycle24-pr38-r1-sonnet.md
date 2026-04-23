# Cycle 24 PR #38 — R1 Sonnet Review

**Date:** 2026-04-23
**Reviewer:** R1 Sonnet (edge cases, concurrency, security, test gaps)
**Branch:** feat/backlog-by-file-cycle24
**Verdict:** REQUEST_CHANGES — 1 BLOCKER, 2 MAJOR, 2 NITs

---

## BLOCKER

### B1 — `_EVIDENCE_TRAIL_HEADER_RE` matches `## Evidence Trail` inside fenced code blocks (`evidence.py`)

**File:** `src/kb/ingest/evidence.py`, `_EVIDENCE_TRAIL_HEADER_RE`

The regex `^## Evidence Trail[ \t]*\r?\n` with `re.MULTILINE` matches on literal text INSIDE fenced code blocks. If a page contains:

```
# Body

```
## Evidence Trail
```

Some text.

## Evidence Trail
<!-- evidence-trail:begin -->
- 2026-01-01 | raw/old.md | Old entry
```

The regex matches the one inside the fence FIRST. The section span `[header_end, next_h2_start)` is then ```` ``` \n\nSome text.\n\n ````; the sentinel is not found in that span; the migration path plants a new sentinel there — inside the fenced block. The new entry lands inside the code fence, not the real Evidence Trail section.

**Confirmed via direct test** (reproduced in review). The AC14 design explicitly addresses T5 (sentinel forgery) via span-limiting, but the guard does not extend to the header match itself. A literal `## Evidence Trail` in a body fenced code block is indistinguishable from the real header to the current regex.

**Fix:** Either (a) pre-strip fenced code block content before running `_EVIDENCE_TRAIL_HEADER_RE.search`, similar to the `cycle 7 AC5` fenced-block masking already used in `_update_existing_page_body`; or (b) after finding the first header match, check that the match position is not enclosed in a fenced region (count preceding backtick-fence markers on even/odd parity). Option (a) is simpler and consistent with the existing masking pattern.

**No test covers this case.** The five AC15 tests cover planted body sentinels and planted `## Evidence Trail` in `## References`, but not `## Evidence Trail` inside a fenced code block.

---

## MAJOR

### M1 — Concurrency gap in `_evict_vector_index_cache_entry`: close() outside the lock (`embeddings.py:80-103`)

**File:** `src/kb/query/embeddings.py`, `_evict_vector_index_cache_entry`

```python
with _index_cache_lock:
    popped = _index_cache.pop(str(vec_path), None)
# lock released here
if popped is not None and popped._conn is not None:
    popped._conn.close()          # <-- no lock held
```

A concurrent `get_vector_index` fast-path caller that grabbed the instance reference BEFORE the pop (dict lookup, no lock needed on fast path) now holds a strong reference to the same `VectorIndex`. After `_evict` releases the lock and calls `close()`, that concurrent caller calls `cached.query()` on a closed connection. `query()` delegates to `_ensure_conn()` which checks `self._conn is not None` (true — close does not set it to None), finds the closed connection, and passes it to `conn.execute()`, which raises `ProgrammingError`. The `except Exception` on line 488 swallows it and returns `[]` — silently downgrading to BM25-only for that query.

This is not a crash, but it is a silent accuracy regression during rebuild windows. The design document (Q2 §Analysis) acknowledges the residual "another thread holding its own strong reference" case but `_evict_vector_index_cache_entry` nulls `popped._conn = None` on line 103 after `close()` — that write races with a concurrent `query()` reading `self._conn` without any synchronization.

**Fix:** After `close()`, set `popped._conn = None` under the instance's `_conn_lock`, not bare. Or document explicitly that `_evict` is only safe when no concurrent query holds the instance (rebuild serialization guarantee).

**The test `test_cache_entry_closed_and_popped_before_replace` verifies ordering of close vs replace but does not model the concurrent query-during-rebuild race.**

### M2 — `test_sentinel_only_no_header_creates_fresh_section` does not divergent-fail on AC14 revert (`test_cycle24_evidence_sentinel_anchored.py:114`)

**File:** `tests/test_cycle24_evidence_sentinel_anchored.py:114-143`

The scenario (sentinel in body, no `## Evidence Trail` header) was already handled by the pre-cycle-24 `else` branch: no header → create fresh section at EOF. The AC14 span-limited search change does not affect this code path (the header regex never matches → falls straight to `else`). Reverting AC14 leaves this test green.

This test is valuable as a preservation test for pre-existing behavior, but it does NOT serve as a divergent-fail regression for the new AC14 span-limited search. Per cycle-22 L5, a test that passes under revert is not load-bearing for the AC it claims to cover.

**Fix:** Retitle the test as `test_body_sentinel_no_header_preserved_as_dead_noise` (preservation test, not AC14 regression). Add a new test where `## Evidence Trail` header exists AND an attacker-planted sentinel appears AFTER the next `^## ` boundary (currently out-of-scope for the span): confirm the entry still lands in the real section, not after the out-of-span sentinel.

---

## NITs

### N1 — Windows stale-steal sleep path duplicates backoff formula inline (`io.py:370-375`)

**File:** `src/kb/utils/io.py:370-375`

The Windows `OSError` stale-steal path uses `min(LOCK_INITIAL_POLL_INTERVAL * (2**attempt_count), LOCK_POLL_INTERVAL)` inline instead of calling `_backoff_sleep_interval(attempt_count)`. Functionally equivalent and reads module attrs at call time (monkeypatch-compatible), but the duplicate is a maintenance divergence point: if the formula in `_backoff_sleep_interval` ever changes (e.g., exponential base or overflow cap), the Windows path silently stays on the old formula.

**Fix:** Replace lines 371-375 with `time.sleep(_backoff_sleep_interval(attempt_count))`.

### N2 — `test_lock_poll_interval_read_at_call_time` tests `LOCK_POLL_INTERVAL=0` but `LOCK_INITIAL_POLL_INTERVAL` stays at 0.01 (`test_cycle24_lock_backoff.py:158`)

**File:** `tests/test_cycle24_lock_backoff.py:158-186`

The test patches only `LOCK_POLL_INTERVAL=0` (cap = 0). Since `min(0.01 * 2**i, 0) = 0` for all i, all sleeps are 0 — the test passes. But the test comment says "CAP clamps everything to 0 — sleeps are no-ops." This is correct but the comment does not clarify that `LOCK_INITIAL_POLL_INTERVAL` is intentionally left at its real value (0.01). A future reader may expect that `LOCK_INITIAL_POLL_INTERVAL=0` is needed to get zero sleeps. No code bug, just a misleading comment.

**Fix:** Add a comment: `# LOCK_INITIAL_POLL_INTERVAL stays at 0.01; min(0.01*2^i, 0) = 0 for all i`.

---

## Other Checks (Passed)

- **No `inspect.getsource` source-scan tests** in cycle 24 files (confirmed via grep). The `test_build_signature_is_keyword_only` test uses `inspect.signature` but ALSO confirms behavior via a live `TypeError`-raising positional call — not signature-only per cycle-16 L2.
- **AC4 `StorageError` late-bind** (`pipeline_mod.StorageError`): correct per cycle-20 L1. No reload-leak risk.
- **AC8 crash stub** writes bytes BEFORE raising (`kwargs.get("db_path", ...).write_bytes(...)`): confirmed divergent-fail — removing the `except` cleanup leaves `tmp_path.exists()` True, failing the assertion.
- **`LOCK_INITIAL_POLL_INTERVAL=0` zero-sleep floor**: `min(0 * 2**i, CAP) = 0` for all attempts. Not an infinite loop — zero-sleeps are valid no-ops and the deadline still expires. No spin-lock issue.
- **Frontmatter-planted sentinel** (`title: "<!-- evidence-trail:begin -->"` in YAML): the regex searches `content` AFTER the frontmatter is still present as plain text. `_EVIDENCE_TRAIL_HEADER_RE` searches for `^## Evidence Trail`, not the sentinel — the sentinel search only runs on the span after the header match. A sentinel buried in YAML frontmatter values will not match `_EVIDENCE_TRAIL_HEADER_RE` and cannot hijack the insert. Safe.
- **EOF without trailing newline**: append inserts correctly (tested manually); no test gap here.
- **Multiple `## Evidence Trail` headers**: first match wins; entry lands in first section. No silent duplication. Acceptable behavior, no test gap.
- **Backoff zero-sleep (`LOCK_POLL_INTERVAL=0`)**: `test_lock_poll_interval_read_at_call_time` covers this path correctly (all observed sleeps == 0.0).
- **Unicode sentinel variants**: a zero-width-char variant of SENTINEL would NOT match `SENTINEL in span` — correctly treated as not-found, triggering the migration path (plant sentinel). The attacker cannot inject a working sentinel via Unicode homoglyphs. Safe.
