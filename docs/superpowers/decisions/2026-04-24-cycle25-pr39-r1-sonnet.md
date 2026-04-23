# PR #39 Cycle 25 — R1 Sonnet Review

**Verdict: APPROVE with one MAJOR finding and two NITs.**

---

## MAJOR — Test gap: AC6 pre-marker write is not verified by the exception-path test

**File:** `tests/test_cycle25_compile_wiki_in_progress.py:88-119`

`test_exception_during_ingest_overwrites_marker_with_failed` stubs `ingest_source` to raise immediately. The test only asserts the FINAL manifest state is `failed:{hash}`. If AC6's pre-marker write block (compiler.py:470-483) is entirely deleted, the except-block at line 507-518 still writes `failed:{pre_hash}` and the test still passes — it never observes that an `in_progress:` entry was written before the exception fired.

**Suggested fix:** Add a capture inside the stub to snapshot the manifest at the moment `ingest_source` is called (before it raises), then assert the snapshot contains `in_progress:{pre_hash}` for the source key. This changes the test from asserting final state to asserting the intermediate state that distinguishes AC6 from no-AC6.

```python
captured_mid = {}
real_load = compiler_mod.load_manifest

def _raise_and_capture(*args, **kwargs):
    captured_mid.update(real_load(manifest_path))
    raise RuntimeError("simulated ingest failure")

monkeypatch.setattr(compiler_mod, "ingest_source", _raise_and_capture)
```

Then add: `assert str(captured_mid.get(source_key, "")).startswith("in_progress:")`.

---

## NIT 1 — Concurrency test tolerance is generous but not vacuous

**File:** `tests/test_cycle25_dim_mismatch.py:188-194`

The 5% tolerance (475 of 500) is wider than necessary for CPython's GIL-protected `+=`. Under CPython the effective loss rate for `int += 1` is essentially 0%, so the 5% floor will never trigger even if the counter is broken in a way that consistently loses a fixed percentage. However, a missing `global _dim_mismatches_seen` declaration raises `UnboundLocalError` on the first thread call, which propagates as a thread exception and causes the join to complete with `observed = 0` — which fails the `>= 475` assert. So the test does catch the most likely regression (missing `global`), just not subtle counter aliasing. Tolerable per Q8 design decision; no change required, flagging for awareness.

---

## NIT 2 — AC3 warning emits two absolute paths; pre-cycle-25 baseline only emitted one

**File:** `src/kb/query/embeddings.py:516-524`

Pre-cycle-25 the warning exposed `self.db_path` (absolute). Cycle 25 adds `wiki_dir_hint` (`self.db_path.parent.parent`), a second absolute directory path. Neither is a new class of leak relative to the existing convention in `compiler.py:458` (`source` path logged) and `compiler.py:87` (`manifest_path` logged). Threat model T5 explicitly accepts developer-local log paths. The cycle-20 `StorageError` redaction convention (`<path_hidden>`) applies only to exception `__str__` — not to logger warnings. No change needed; noting that this PR normalises the pattern, not introduces it.

---

## Other checks — no finding

- **Lock-timeout gap (AC6):** if `file_lock(manifest_path, 1.0)` times out, the marker is absent and a subsequent hard-kill leaves no `in_progress:` trace. Documented as best-effort in the code and design doc (Q4, CONDITION 5). Acceptable per existing cycle-23 convention.
- **Stale scan outside lock (AC7):** log-only; false-positive spurious warnings from concurrent compiles are documented (Q10, CONDITION 11). Not a correctness issue.
- **`pre_hash` JSON escaping:** `content_hash()` returns `hexdigest()[:32]` — hex characters only, no JSON special chars. `f"in_progress:{pre_hash}"` is always valid as a JSON string value.
- **Positive case for rebuild_indexes:** `test_stale_tmp_unlinked` (line 30) seeds both `vec_path` and `tmp_vec_path`, calls `rebuild_indexes`, asserts both gone, `cleared=True`, `error=None`. This is the positive case.
- **CONDITION 13 revert detection:** `test_full_mode_prune_exempts_in_progress_markers` asserts the `in_progress:` key survives the prune. Without the `not str(v).startswith("in_progress:")` guard the key would be pruned (file is absent), failing the assert. Test is divergent-fail.
- **`test_warning_uses_db_path_parent_parent_for_wiki_dir` revert detection:** if code reverts to `wiki_dir_hint = self.db_path`, the warning no longer contains `db_path.parent.parent` (`tmp_path`), so `matching = []` and the first assert fails. Test is divergent-fail.
- **CONDITION 11 and 14 doc sync:** both satisfied at `CLAUDE.md:135`.
- **Vacuous pattern scan:** no `inspect.getsource`, `read_text().splitlines()`, or conditional-assert patterns found in the three new test files.
