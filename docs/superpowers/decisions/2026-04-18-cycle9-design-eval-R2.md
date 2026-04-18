# Cycle 9 Design Eval R2 — Codex

Scope: 31 AC across 16 files. Source function locations were checked before judging; several prose line references are stale but most function targets still exist.

AC1 | OK | `src/kb/query/engine.py::search_pages` still hard-codes vector DB at line 131; AC correctly closes cycle 8 R2 wiki_dir isolation leak. Test must prove override DB is used and repo DB is not read.
AC2 | OK | `src/kb/query/engine.py::_flag_stale_results` is line 267 and call at line 214 omits project root; AC correctly addresses cycle 8 R2 location leak. Regression must seed conflicting temp/repo `raw/` mtimes.
AC3 | OK | `src/kb/query/engine.py::query_wiki` branch is line 756, not ~line 756 only by coincidence; AC correctly uses `_vec_db_path` source of truth. Test must cover mid-session `wiki_dir` override, cycle 8 R2.
AC4 | OK | `src/kb/mcp/health.py::kb_lint` calls `get_flagged_pages()` at line 71 with no path; AC closes same-class feedback leak from cycle 7 R3/cycle 8 R2. Test needs prod feedback poison plus empty temp feedback.
AC5 | OK | `src/kb/mcp/health.py::kb_evolve` calls `get_coverage_gaps()` at line 126 with no path; AC mirrors AC4 and avoids same-class leak, cycle 7 R3/cycle 8 R2.
AC6 | CONCERN | `src/kb/mcp/core.py::kb_compile_scan` is line 602 and current code calls only `find_changed_sources()`/`scan_raw_sources()`, not `detect_source_drift`; AC wording has function-location/flow drift. Step 5 must specify derived `raw_dir` and manifest path from `wiki_dir.parent`, cycle 8 R2.
AC7 | CONCERN | `src/kb/mcp/core.py::kb_ingest` already has byte stat cap at line 285 but still truncates chars at line 357; AC says content exceeds `QUERY_CONTEXT_MAX_CHARS`. Step 5 must align byte-vs-char wording and exact error casing with sibling tools, cycle 7 R3 same-class leak.
AC8 | OK | `src/kb/mcp/core.py::kb_ingest_content` calls `_validate_file_inputs` before write at line 410; AC is valid as a boundary hardening check. Regression must assert no raw file exists after oversize reject, cycle 7 R3.
AC9 | CONCERN | `src/kb/mcp/browse.py::kb_read_page` already rejects multiple case-insensitive matches at lines 87-104; AC is mostly characterization. Test must query a non-exact case like `concepts/FOO`, otherwise exact `concepts/Foo` bypasses fallback, cycle 8 R2 location/test drift.
AC10 | OK | `src/kb/compile/compiler.py::load_manifest` line 65 catches JSON/Unicode only; widening to `OSError` mirrors cycle 3/5/7 store resilience. Test should monkeypatch read to raise `OSError`, not inspect source.
AC11 | OK | `src/kb/lint/augment.py::run_augment` summary lines 906-912 count URL attempts; AC correctly requires final per-stub outcome while retaining URL-level manifest audit, cycle 8 R2 reporting semantics.
AC12 | CONCERN | `src/kb/lint/checks.py::check_source_coverage` line 482 takes `pages: list[Path]`; AC's “shared corpus/load_all_pages output” risks signature drift unless callers migrate. Prefer scoped frontmatter parse inside this function; spy/micro-benchmark is acceptable if behavioral, cycle 7 signature lesson.
AC13 | OK | `src/kb/evolve/analyzer.py::analyze_coverage` line 25 uses `build_backlinks` exact-match behavior; AC correctly aligns orphan detection with `build_graph` slug resolution. Regression must use bare `[[b]]`, cycle 8 R2.
AC14 | BLOCK | `src/kb/capture.py::_normalize_for_scan` line 192 would broaden to `except Exception: continue`; AC omits required debug observability from threat model. Silent secret-scan decode failure is a security regression, cycle 7 R3 same-class leak.
AC15 | CONCERN | `src/kb/capture.py::_check_rate_limit` line 48 already documents per-process scope but lacks explicit `TODO(v2)` wording required by AC. Low risk, but Step 5 must verify exact doc update, cycle 8 R2 doc drift.
AC16 | OK | `src/kb/capture.py::_build_slug` line 354 has unbounded loop; AC correctly adds deterministic ceiling. Test should drive `_build_slug` directly and cross-process retry path indirectly, cycle 7 R3 failure-mode lesson.
AC17 | CONCERN | `src/kb/capture.py::_path_within_captures` line 381 has two call sites plus tests importing the private helper. Rename must update `tests/test_capture.py` imports/assertions or it becomes a ruff/autofix monkeypatch-style break, cycle 4 lesson.
AC18 | OK | `src/kb/capture.py::_scan_for_secrets` line 222 currently reports generic “via encoded form”; AC improves observability. Test must cover both base64 and URL-encoded paths behaviorally, cycle 6 R1 inspect-source trap.
AC19 | OK | `src/kb/capture.py::_CAPTURE_SECRET_PATTERNS` line 101 is internal-only by grep; NamedTuple refactor is safe if all call sites use `.label`/`.pattern`. Regression can be existing scanner behavior, not source inspection.
AC20 | OK | `tests/test_capture.py` imports `CAPTURE_KINDS` from `kb.capture` at line 23; AC moves to canonical `kb.config`, avoiding re-export coupling, cycle 4 ruff/autofix lesson.
AC21 | OK | `tests/test_capture.py` lacks backslash/double-quote title round-trip tests; AC is a behavioral guard against yaml escaping regressions, cycle 6 R1.
AC22 | CONCERN | `tests/conftest.py::tmp_captures_dir` line 176 returns a temp path outside `PROJECT_ROOT`; proposed `is_relative_to(PROJECT_ROOT)` assertion appears to fail current fixture. Step 5 must reconcile with monkeypatching `PROJECT_ROOT` or alter assertion target, cycle 8 R2 location drift.
AC23 | OK | `tests/conftest.py::RAW_SUBDIRS` line 11 is hardcoded to 5 dirs while `SOURCE_TYPE_DIRS` is broader; deriving dynamically avoids same-class fixture drift, cycle 7 R3.
AC24 | CONCERN | `src/kb/utils/llm.py::_make_api_call` truncates `e.message` at lines 127, 171, 238 and generic `last_error` at 244. AC must redact before every truncation path with specific-before-generic ordering (`sk-ant-` before `sk-`), cycle 7 R3 same-class leak.
AC25 | OK | `src/kb/mcp/app.py` instructions lines 34-55 are documentation; sorting within groups is low risk. Snapshot test is acceptable if it asserts generated text, not implementation source, cycle 6 R1.
AC26 | BLOCK | `src/kb/cli.py` deliberately short-circuits before `kb.config` at lines 7-16; moving function-local `from kb.X import Y` bindings to module top can break cycle 7 AC30 and existing tests monkeypatching provider modules (`kb.ingest.pipeline.ingest_source`, `kb.lint.runner.run_all_checks`). This is the ruff autofix monkeypatch trap plus fast-path break, cycle 4/cycle 8.
AC27 | CONCERN | `src/kb/ingest/__init__.py` eagerly imports `ingest_source`; AC's lazy `__getattr__` is right, but its test is insufficient for cycle 8 AC30 unless paired with exact version fast-path subprocess that proves `kb.config` and `kb.ingest.pipeline` stay unloaded.
AC28 | CONCERN | `src/kb/query/engine.py::search_raw_sources` line 438 has no `wiki_dir`; current `query_wiki` derives `effective_raw_dir` at lines 688-692 and passes it at line 800. AC target text has function-location drift; test should validate `query_wiki(wiki_dir=...)` fallback, cycle 8 R2.
AC29 | OK | `src/kb/capture.py::_verify_body_is_verbatim` line 327 currently appends original item after checking stripped body; AC correctly prevents downstream whitespace mismatch. Test should assert written markdown body, cycle 8 R2.
AC30 | OK | `tests/test_capture.py` has duplicate `import re as _test_re` at line 12 and stale byte comment at line 131; AC is test hygiene. Verify with the linter, cycle 4 ruff lesson.
AC31 | OK | `.env.example` line 3 still says required Claude API; AC is documentation-only and matches user-reported issue. No behavioral test needed; doc parity follow-up is enough, cycle 8 R2 doc drift.

Conditions Step 5 Must Resolve

1. Resolve AC14 before implementation: broad `_normalize_for_scan` exception handling must log debug-level decode failures; a silent `continue` is rejected as a secret-scanner observability regression.
2. Rewrite or tightly constrain AC26: keep the version short-circuit before heavy/config imports, avoid binding imported functions in a way that bypasses existing module monkeypatch tests, and add the exact subprocess fast-path guard:

```text
kb --version
```

3. For AC27, add a fresh-interpreter behavioral guard proving the fast path does not load `kb.config` or `kb.ingest.pipeline` until attribute access. Include explicit `PYTHONPATH` in subprocess tests per cycle 7 R3.
4. Clarify AC6/AC28 target drift: `kb_compile_scan` must derive `raw_dir` and manifest path from `wiki_dir.parent`; raw fallback should be tested through `query_wiki(wiki_dir=...)`, not by inventing a `wiki_dir` parameter on `search_raw_sources`.
5. Fix AC22 design: current `tmp_captures_dir` is under `tmp_path`, not `PROJECT_ROOT`; either patch `PROJECT_ROOT` in the fixture before asserting or assert against the effective temp project root.
6. For AC7/AC8, standardize the limit unit and error string across `kb_ingest`, `kb_ingest_content`, and `kb_save_source` to avoid same-class size-cap drift.
7. For AC12, avoid changing `check_source_coverage` public parameter shape unless all callers migrate; do not accept inspect-source or regex tests as proof.
8. For AC24, redact before truncation in all `_make_api_call` message paths and order specific key patterns before generic ones.

Final verdict: REJECT (explicit rewrites required for AC14 and AC26; AC6/AC22/AC28 need clarification before Step 5 planning).
