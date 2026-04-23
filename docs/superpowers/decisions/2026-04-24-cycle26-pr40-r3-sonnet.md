# R3 Sonnet — Final Gate Review: PR #40 (Cycle 26)

**Branch:** `feat/backlog-by-file-cycle26`
**Date reviewed:** 2026-04-24
**Trigger:** cycle-17 L4 (Step-5 design gate resolved 16 questions ≥ 10 threshold)

## VERDICT: APPROVE

## Summary

- **Audit-doc drift:** NONE. All T1-T6 threat mitigations match shipped code; all 4 deferred-to-BACKLOG promises were scope-only notes (not required to file entries).
- **Design doc drift:** NONE. All 13 CONDITIONS verified. One acknowledged over-constraint in CONDITION 9's grep spec (pre-existing from R1 reviews).
- **Count consistency:** PASS. 2790 tests / 7 commits / 243 test files — CHANGELOG.md + CHANGELOG-history.md + CLAUDE.md all consistent.
- **BACKLOG lifecycle:** PASS. `phase4_audit_concurrency` entry deleted (AC6); HIGH-Deferred vector-index lifecycle narrowed + Q16 sub-item present (AC8).
- **Cross-cluster composition:** PASS. Warm-load thread + counter increment inside `_model_lock` + lock-free getter reads compose correctly. Asymmetry documented.
- **Code synthesis:** PASS. R1 Sonnet M1 fix (`test_cold_load_exception_suppresses_info_log_and_counter`) correctly catches `finally:` regression via structural trace.

## CONDITIONS 1-13 verification

| CONDITION | Status | Evidence |
|-----------|--------|----------|
| 1 — Boot-lean allowlist | PASS | `test_cycle23_mcp_boot_lean.py:85` includes `kb.query.embeddings` |
| 2 — 7 tests minimum | PASS | 8 tests collected (1 added by R1 M1 fix) |
| 3 — Post-success ordering | PASS | `embeddings.py:365-374` — counter + log inside `if _model is None:` inside `with _model_lock:`, AFTER `_model = ...` assignment, NO `finally:` |
| 4 — `caplog.set_level INFO` | PASS | Lines 140, 243 present; test 7 uses ERROR-level |
| 5 — Counter asymmetry docstring | PASS | `embeddings.py:58-63` references `_dim_mismatches_seen` + cycle-25 Q8 |
| 6 — AC7 skip-on-no-diff | PASS | CHANGELOG notes "pip-audit matches cycle-25 baseline; no edit" |
| 7 — AC6 grep broadened | PASS | Design doc uses `ctx\.Process\|mp\.Process\|get_context` |
| 8 — Function-local import in `main()` | PASS | `mcp/__init__.py:77` inside `try:` inside `main()`, not module scope |
| 9 — Single production caller | PASS with NIT (doc over-spec) |
| 10 — `_warm_load_target` wrapper | PASS | `embeddings.py:104-111` |
| 11 — `Thread.start()` RuntimeError swallow | PASS | `mcp/__init__.py:80-84` |
| 12 — AC8 BACKLOG narrow + Q16 | PASS | `BACKLOG.md:109` cites AC1-5 + Q16 sub-item |
| 13 — CHANGELOG reflects counts | PASS | 8 ACs, 8 tests (+AC2b extension), 7 commits — all match `git log` |

## Cross-cluster composition

Warm-load thread → `_get_model()` → `_vector_model_cold_loads_seen += 1` inside `_model_lock`. `get_vector_model_cold_load_count()` reads lock-free. Q4 decision explicitly accepts this asymmetry: stale reads are fine for diagnostic counters. CPython GIL provides atomicity for `int += 1` — the lock prevents concurrent increments (exact count contract), not stale reads.

"Exact count" means the counter is not decremented or double-incremented — NOT that readers always see the freshest value atomically. Documentation could be clearer but is not defective.

## `test_cold_load_exception_suppresses_info_log_and_counter` trace

Monkeypatch replaces `model2vec.StaticModel.from_pretrained` with `_raising_stub` that raises `RuntimeError`. `embeddings_mod._get_model()` is called directly (not via warm-load wrapper). Path:

```python
with _model_lock:
    if _model is None:
        start = time.perf_counter()
        _model = StaticModel.from_pretrained(...)   # RAISES here
        elapsed = ...                                # never reached
        _vector_model_cold_loads_seen += 1           # never reached
        logger.info(...)                             # never reached
```

`RuntimeError` propagates through `with _model_lock:` (releasing the lock), caught by `pytest.raises(RuntimeError)`. Counter + log are between raising line and end of `if` — success-path only. A `finally:` regression would move them outside the `if _model is None:` block, firing unconditionally. `assert not info_records` would then fail. `pytest.raises` does NOT suppress the `assert` check — it only catches the `RuntimeError` from `_get_model()`; assertions run AFTER the `with pytest.raises(...)` block exits.

**Test correctly divergent-fails on `finally:` regression.** Structurally sound.

## New findings

**NONE.** No issues beyond those already addressed by R1 fixes + R2 follow-up doc-count fix.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |
| NIT | 1 | note (doc over-spec, no code action) |

**Merge cleared.**
