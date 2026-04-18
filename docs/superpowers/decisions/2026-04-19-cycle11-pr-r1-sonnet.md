# Cycle 11 PR R1 — Sonnet Code Review

**Date:** 2026-04-19
**Branch:** `feat/backlog-by-file-cycle11`
**Focus:** Edge cases, concurrency, security, test gaps (complements Codex R1 architecture/contracts)

---

## Summary

Cycle 11 is a hardening cycle: defensive migration of `_coerce_str_field` call sites, dead-path closure for `comparison`/`synthesis` ingest, graph-helper relocation with back-compat re-exports, and test scaffolding cleanup. The security verify already surfaced five partial/fail items (T1, T3, T5, T9 partial; same-class `kb_save_source` fail). This R1 confirms most are addressed by the shipped code, surfaces two new issues, and flags one borderline anti-pattern.

---

## BLOCKERS

### B1 — `test_cycle11_ac4_six_callers_do_not_import_page_helpers_from_builder` is an inspect-source test in disguise

`tests/test_cycle11_utils_pages.py:80-94` reads six `.py` source files, splits on lines, and asserts `"page_id" not in line` and `"scan_wiki_pages" not in line` for any line starting with `from kb.graph.builder import`. This is the inspect-source anti-pattern flagged by `feedback_inspect_source_tests` and the cycle-4 RedFlag: the assertions pass if you revert the caller migration back to `from kb.graph.builder import page_id, scan_wiki_pages` because those lines do not start with `"from kb.graph.builder import"` — wait, actually they would match — but the test ALSO passes vacuously if zero lines in a file start with `from kb.graph.builder import`, which is the exact post-migration state. The vacuous-pass problem: if someone adds `from kb.graph.builder import build_graph, page_id` (non-top-level or mid-file), the `startswith` check misses it. More critically, `compiler.py`'s function-local import `from kb.graph.builder import page_id as get_page_id` inside `detect_source_drift` uses a leading space (four-space indent), so `line.startswith("from kb.graph.builder import")` returns **False** and the assertion is **never evaluated** for the only file where a builder import of a page helper could silently survive. The test does not exercise the production code path; it does a string scan of source files with a filter that excludes indented lines.

**Required fix:** Replace with a behavioral import test — import each module and assert `not hasattr(module, "page_id")` or verify the attribute `is` the canonical `kb.utils.pages.page_id` object. For `compiler.py`'s function-local import, call `detect_source_drift` with a stub manifest and assert the returned page IDs match what `kb.utils.pages.page_id` would compute.

---

## MAJORS

### M1 — T9 partial: `test_compile_loop_does_not_double_write_manifest` still lacks a second compile pass

The security verify confirmed this at T9. The test at `tests/test_compile.py:222-280` runs `compile_wiki` once, counts one `save_manifest` call, and reads the manifest content. It does **not** call `compile_wiki` a second time with the same source to assert idempotence. The design (AC13) explicitly requires a second pass to detect the double-write regression. A refactor that saves the manifest once-per-compile but does so with a stale hash on re-run would pass the current test. The counter is load-bearing only for the single-run case.

### M2 — AC8 subprocess copies full `os.environ`, inheriting potentially tainted `PYTHONPATH`

`_version_short_circuit_env()` at `tests/test_cycle11_cli_imports.py:110-118` does `env = os.environ.copy()` then prepends to `PYTHONPATH`. The design (condition 12) and threat model (T5) both call for a minimal env. On a developer machine with a `PYTHONPATH` that shadows `kb.*`, the test could import the wrong module and produce a false-green. The fix is a minimal env: `{"PYTHONPATH": src_path, "PATH": os.environ.get("PATH",""), "SYSTEMROOT": os.environ.get("SYSTEMROOT","")}` — already specified in condition 12 of the design doc.

---

## NITS

### N1 — `test_kb_save_source_comparison_names_kb_create_page` uses `tmp_project` but `kb_save_source` writes to `RAW_DIR` via the module-level constant, not via the fixture

`tests/test_cycle11_task6_mcp_ingest_type.py:60-67` passes `tmp_project` as a fixture for isolation but does not monkeypatch `core.SOURCE_TYPE_DIRS` or `core.RAW_DIR`. The `source_type in {"comparison","synthesis"}` guard fires before any file write, so no production file is written in practice — but the test is not actually isolated from production `RAW_DIR`. Low risk given the guard fires first, but worth adding `monkeypatch.setattr(core, "SOURCE_TYPE_DIRS", {"article": object()})` for symmetry with the other tests in that file.

### N2 — `ingest_source` AC2 error message does not match MCP wrapper message exactly

Library: `"source_type={source_type!r} is not valid for ingest_source; use kb_create_page for comparison and synthesis pages"` (pipeline.py:861-865). MCP wrapper: `'Error: source_type "comparison" and "synthesis" are wiki page types, not ingest source types. Use kb_create_page to create those pages directly.'` (core.py:300-304). Test `test_ingest_source_rejects_comparison_and_synthesis_with_kb_create_page_message` checks `match="kb_create_page"`, which catches both. Not a bug, but the inconsistency means user-facing error text differs depending on whether caller uses the library or MCP. Not a blocker.

### N3 — `test_flag_stale_results_source_mtime_equal_to_updated_is_not_stale` passes `project_root=tmp_path` but `_flag_stale_results` signature on main does not accept `project_root`

Verify that `_flag_stale_results` at `src/kb/query/engine.py` actually accepts a `project_root` keyword argument in this branch. If the signature was not updated, the test will fail with `TypeError` rather than the intended assertion error. The security verify noted the test exists at line 30 with `project_root=tmp_path` — confirm the production function signature matches.

---

## VERDICT

**REQUEST CHANGES** — B1 is a genuine inspect-source/vacuous-if anti-pattern that per project RedFlag policy must be fixed before merge. M1 (second compile pass) and M2 (minimal subprocess env) are required by the design document's own conditions 12 and AC13 and should be closed in R2. N1-N3 are advisory.

Positive notes: AC2 library guard lands before `source_path.read_bytes()` (correct ordering), MCP error messages are static and do not interpolate paths, `_page_id` alias is correctly placed, `tmp_project` fixture enhancement is clean and strictly additive, `test_version_short_circuit_*` behavioral approach is correct per design.
