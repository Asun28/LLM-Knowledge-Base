# Cycle 24 Security Verification — 2026-04-24

## T1-T10 Threat Status

| Threat | Status | Evidence |
|---|---|---|
| T1 stale `<vec_db>.tmp` | IMPLEMENTED | `e306ab14` adds early tmp cleanup before gates at `src/kb/query/embeddings.py:140-146`; regression at `tests/test_cycle24_vector_atomic_rebuild.py:78-88`. |
| T2 Windows `os.replace` semantics | IMPLEMENTED | `e306ab14` builds sibling tmp and calls `os.replace(str(tmp_path), str(vec_path))` at `src/kb/query/embeddings.py:140,188`; spy test at `tests/test_cycle24_vector_atomic_rebuild.py:95-111`. |
| T3 backoff starvation | IMPLEMENTED | `82833fce` adds capped exponential backoff at `src/kb/utils/io.py:235-249,388-389`; fairness remains out-of-scope and tracked in `BACKLOG.md:131-132`. |
| T4 `LOCK_POLL_INTERVAL` compat | IMPLEMENTED | `82833fce` reads module constants at call time in `src/kb/utils/io.py:235-249`; monkeypatch tests at `tests/test_cycle24_lock_backoff.py:82-110,161-186`. |
| T5 body-planted sentinel | IMPLEMENTED | `6724745d` span-limits sentinel search to the real section at `src/kb/ingest/evidence.py:82-84,123-158`; tests at `tests/test_cycle24_evidence_sentinel_anchored.py`. |
| T6 `StorageError` path leak | IMPLEMENTED | `9a1d9d7a` raises typed redacted error at `src/kb/ingest/pipeline.py:578-593`; no diff hit for `exc.path`/`repr(exc)` logging; test file `tests/test_cycle24_evidence_error_redacted.py`. |
| T7 same-class two-write peers | PARTIAL | In-scope AC gap: none for new pages. `9a1d9d7a` inlines initial trail at `src/kb/ingest/pipeline.py:367-370`; exclusive branch writes same rendered payload at `:389`. Out-of-scope update-path two-write remains by design and is tracked at `BACKLOG.md:151-152`. |
| T8 CVE late-arrival | PARTIAL | Tooling gap, not AC deviation: `pip-audit` is not runnable on PATH and `python -m pytest` also lacks pytest. Existing `.data/cycle-24/cve-baseline.json` vs `.data/cycle-24/cve-post.json` contain identical IDs: `CVE-2025-69872`, `CVE-2026-6587`, both with empty `fix_versions`. |
| T9 cache pinning old DB | IMPLEMENTED | `e306ab14` evicts and closes cached connection before replace at `src/kb/query/embeddings.py:184-188`; helper closes at `:93-103`; ordering test at `tests/test_cycle24_vector_atomic_rebuild.py:190-228`. |
| T10 `db_path` override drift | IMPLEMENTED | `e306ab14` makes `db_path` keyword-only and uses `is not None` at `src/kb/query/embeddings.py:359-380`; behavior test at `tests/test_cycle24_vector_atomic_rebuild.py:170-186`. |

## Anti-Pattern Scan Results

- Path traversal / containment: no cycle-24 diff hits for `str.startswith(str(`, `resolved.startswith(`, or `startswith(base`.
- Secret-redaction bypass: no cycle-24 diff hits for `logger.*exc.path` or `repr(exc)`.
- Input bounds: no cycle-24 diff hits for `s[:N]` where `N` is bytes-named.
- Dep CVEs: live `pip-audit` unavailable in this shell; baseline/post artifacts match exactly with only known open diskcache/ragas advisories and no fix versions.

## Deferred-To-Backlog Audit

- `Phase 4.5 MEDIUM.*fair-queue`: semantic entry exists at `BACKLOG.md:131-132`.
- `Phase 4.5 HIGH.*_update_existing_page.*single-write`: semantic narrowed entry exists at `BACKLOG.md:151-152`; exact regex misses because line omits `Phase 4.5 HIGH`.
- `Phase 4.5 HIGH.*vector-index lifecycle`: semantic entry exists at `BACKLOG.md:109`; exact regex misses because line uses `Phase 4.5 HIGH cycle 1`, with sub-item 1 marked shipped.
- `Phase 4.5 HIGH.*JSONL migration`: semantic entry exists at `BACKLOG.md:128-129`; exact regex misses because line omits `Phase 4.5 HIGH`.
- `Phase 4.5 HIGH.*rebuild_indexes.*tmp`: semantic entry exists at `BACKLOG.md:111-112`; exact regex misses because line omits `Phase 4.5 HIGH`.

## Same-Class Peer Scan

- `str.startswith(str(` path containment: none in cycle-24 diff.
- Regex alternations routing user text without `re.escape`: none. New regexes are fixed literals only: `src/kb/ingest/evidence.py:82-84`.
- `depth -= 1` without `if depth > 0`: none in cycle-24 diff.

## Overall Verdict

CONDITIONAL PASS: production code and regression tests satisfy T1-T7/T9/T10 by inspection. Conditions: run live `pip-audit --format=json` and the five cycle-24 pytest files in an environment with those tools installed; optionally normalize BACKLOG lines so the exact Step-11 regex checklist passes, though the required entries are present semantically.
