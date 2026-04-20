# Cycle 15 Design Eval R2

Focus: edge cases, failure modes, integration, security, performance.

Verification: PATH `python -m pytest` failed: no pytest in Python 3.13; PATH `ruff check` and `pip-audit` not found. Venv equivalents passed: pytest 2238 passed / 7 skipped; ruff clean; pip-audit found pre-existing `diskcache 5.6.3 CVE-2025-69872`.

AC1 APPROVE — `_flag_stale_results` already loops normalized `sources`; list-vs-string source frontmatter is mechanical via `normalize_sources`.
AC2 APPROVE.
AC3 AMENDMENT: require explicit `validate_frontmatter` gate, mirroring `_apply_status_boost`.
AC4 AMENDMENT: default must distinguish omitted from override, e.g. `max_days: int | None = None`; current default-value shape would suppress per-page decay.
AC5 APPROVE.
AC6 AMENDMENT: Evidence Trail span regex must handle CRLF, EOF-without-next-section, and line-start `^## ` only; add tests for action text outside the span.
AC7 APPROVE.
AC8 REJECT: `suggest_new_pages` outputs dead-link target suggestions and accepts page paths, not page dicts with `status`; status-priority semantics are undefined.
AC9 APPROVE.
AC10 APPROVE.
AC11 AMENDMENT: use `atomic_text_write(json.dumps(...))` or `mkstemp(dir=out_path.parent)` plus cleanup; no cross-volume temp.
AC12 AMENDMENT: compare `st_mtime_ns`, document single-writer assumption, and keep publish epistemic filtering before any skip return.
AC13 AMENDMENT: preserve cycle-14 out-dir validation order before passing `incremental`; add containment regression with `--no-incremental`.
AC14 AMENDMENT: expose read-only mapping or copy; casefold keys at definition to avoid caller mutation/case drift.
AC15 AMENDMENT: add `re.escape(key)` and bounded input length before regex loop.
AC16 AMENDMENT: clamp finite multiplier result and compose `topics` robustly when tags are list/non-string.
AC17 AMENDMENT: process-wide `cache_clear()` needs adjacent comment and perf acceptance; current source intentionally uses uncached `frontmatter.load`.
AC18 AMENDMENT: already shipped in current `load_all_pages`; drop or convert to verification-only.
AC19 AMENDMENT: already shipped with AC18; drop or convert to verification-only.
AC20 APPROVE.
AC21 APPROVE.
AC22 APPROVE.
AC23 APPROVE.
AC24 APPROVE.
AC25 AMENDMENT: extend test matrix for AC6 span boundaries: CRLF, EOF end, no trail, and `action: ingest` above trail.
AC26 REJECT: blocked by AC8 semantic mismatch; cannot prove seed-first ordering without redefining status source.
AC27 AMENDMENT: spy test is acceptable only if JSON-LD also verifies no partial/temp residue on replace failure.
AC28 AMENDMENT: use ns mtimes or explicit freshening; Windows/network granularity makes second-level tests flaky.
AC29 AMENDMENT: include cycle-14 out-dir containment preservation; avoid relying on `capsys` with `CliRunner`.
AC30 AMENDMENT: include ReDoS/length-cap and clamp/non-finite multiplier tests from T1/T2.
AC31 AMENDMENT: assert both cache invalidation behavior and documented process-wide cost.
AC32 AMENDMENT: existing fixed key-set test is already updated; keep consumer grep audit for `set(page)` / `page.keys()` regressions.

Summary: blockers 2, amendments 19, approvals 11.
