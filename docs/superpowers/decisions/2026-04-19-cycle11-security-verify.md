# Cycle 11 Step 11 Security Verify

**Date:** 2026-04-19  
**Branch:** `feat/backlog-by-file-cycle11`  
**HEAD:** `b1d3cd1`  
**Command basis:** `git diff main..HEAD -- src tests`

## Threat-Model Mapping

T1 — Extraction non-string values at unmigrated `.get("<field>")` sites can raise late and leave partially populated wiki pages.

Status: PARTIAL — `_coerce_str_field` is implemented and now used on summary string fields and title/name merge paths, but collection-bearing sites still read raw `extraction.get(...)` values for `key_claims`, `key_points`, `key_arguments`, `entities_mentioned`, and `concepts_mentioned`. The cycle-11 tests cover non-string scalar context/title paths, not the full threat-model list of collection read sites.

Evidence: `src/kb/ingest/pipeline.py:72` defines `_coerce_str_field`; `src/kb/ingest/pipeline.py:85` pre-validates `_SUMMARY_STRING_FIELDS`; `src/kb/ingest/pipeline.py:377` and `src/kb/ingest/pipeline.py:449` coerce context fields; `src/kb/ingest/pipeline.py:956` coerces summary title/name; raw collection reads remain at `src/kb/ingest/pipeline.py:384`, `src/kb/ingest/pipeline.py:398`, `src/kb/ingest/pipeline.py:411`, `src/kb/ingest/pipeline.py:1014`, `src/kb/ingest/pipeline.py:1030`, and `src/kb/ingest/pipeline.py:1128`; tests cover scalar rejection at `tests/test_cycle11_ingest_coerce.py:20`, `tests/test_cycle11_ingest_coerce.py:48`, and `tests/test_cycle11_ingest_coerce.py:65`.

T2 — `source_type="comparison"|"synthesis"` dead path adds a new error surface and could leak paths or extraction contents.

Status: IMPLEMENTED

Evidence: library guard rejects `comparison`/`synthesis` before `source_path.read_bytes()` at `src/kb/ingest/pipeline.py:861` and `src/kb/ingest/pipeline.py:891`; MCP `kb_ingest` returns a static `kb_create_page` message at `src/kb/mcp/core.py:300`; MCP `kb_ingest_content` returns the same static message at `src/kb/mcp/core.py:426`; tests assert no manifest/wiki writes at `tests/test_cycle11_ingest_coerce.py:88`, `tests/test_cycle11_ingest_coerce.py:98`, and `tests/test_cycle11_ingest_coerce.py:119`.

T3 — `kb.graph.builder` re-export shim can hide monkeypatch/import-path drift.

Status: PARTIAL — canonical helpers moved to `kb.utils.pages` and `kb.graph.builder` re-exports them, but existing tests still monkeypatch the shim and the private `_page_id` name remains as a compatibility alias, so the threat-model grep expectations are not fully satisfied.

Evidence: canonical `scan_wiki_pages` and `page_id` are in `src/kb/utils/pages.py:29` and `src/kb/utils/pages.py:40`; builder re-export is at `src/kb/graph/builder.py:11`; six cycle-11 callers import from `kb.utils.pages`, including `src/kb/compile/linker.py:12`, `src/kb/evolve/analyzer.py:19`, `src/kb/lint/checks.py:27`, `src/kb/lint/runner.py:20`, `src/kb/lint/semantic.py:21`, and `src/kb/compile/compiler.py:242`; existing shim monkeypatch remains at `tests/test_backlog_by_file_cycle7.py:437`; `_page_id` alias remains at `src/kb/utils/pages.py:50`.

T4 — `tmp_project` fixture use could fall back to real `WIKI_DIR`/`RAW_DIR` and write production wiki files.

Status: IMPLEMENTED

Evidence: the refactored `tests/test_ingest.py::test_ingest_source` uses `tmp_project` and passes explicit `wiki_dir` and `raw_dir` at `tests/test_ingest.py:98`, `tests/test_ingest.py:100`, and `tests/test_ingest.py:106`; other legacy calls without `raw_dir` are wrapped with config patches at `tests/test_ingest.py:181` and `tests/test_ingest.py:228`.

T5 — Subprocess CLI smoke tests can inherit tainted `PYTHONPATH`; command help/import coverage should use `shell=False` and strong assertions.

Status: PARTIAL — cycle-11 command smoke coverage uses in-process `CliRunner`, not subprocess command help checks. The subprocess helper that does exist for version short-circuit uses argv-list `shell=False` by default, but copies the parent environment and appends any existing `PYTHONPATH`.

Evidence: command smoke tests use `CliRunner().invoke(...)` at `tests/test_cycle11_cli_imports.py:37`, `tests/test_cycle11_cli_imports.py:54`, `tests/test_cycle11_cli_imports.py:70`, `tests/test_cycle11_cli_imports.py:86`, `tests/test_cycle11_cli_imports.py:98`, and `tests/test_cycle11_cli_imports.py:106`; subprocess environment copies `os.environ` and preserves existing `PYTHONPATH` at `tests/test_cycle11_cli_imports.py:110` and `tests/test_cycle11_cli_imports.py:113`; subprocess invocation uses an argv list at `tests/test_cycle11_cli_imports.py:133`.

T6 — `kb --version` must short-circuit without importing `kb.config`.

Status: IMPLEMENTED

Evidence: subprocess code sets `sys.argv`, imports `kb.cli`, and asserts `kb.config` is absent from `sys.modules` at `tests/test_cycle11_cli_imports.py:123`, `tests/test_cycle11_cli_imports.py:126`, and `tests/test_cycle11_cli_imports.py:129`; both `--version` and `-V` are covered at `tests/test_cycle11_cli_imports.py:143` and `tests/test_cycle11_cli_imports.py:149`.

T7 — `_flag_stale_results` silent-skip branches can hide stale source changes.

Status: IMPLEMENTED

Evidence: production behavior skips missing/empty sources and non-ISO updates at `src/kb/query/engine.py:290`, `src/kb/query/engine.py:292`, `src/kb/query/engine.py:296`, and `src/kb/query/engine.py:297`; tests cover empty sources at `tests/test_cycle11_stale_results.py:11`, missing sources at `tests/test_cycle11_stale_results.py:17`, non-ISO and int `updated` values at `tests/test_cycle11_stale_results.py:23`, and mtime equality at `tests/test_cycle11_stale_results.py:30`.

T8 — Re-export shim import cache consistency after moving page helpers.

Status: IMPLEMENTED

Evidence: `kb.graph.builder` re-exports canonical helpers at `src/kb/graph/builder.py:11`; identity test asserts the re-exported helpers are the canonical objects at `tests/test_cycle11_utils_pages.py:11`; behavior tests cover lowercasing, backslash normalization, sorted page scanning, and sentinel skipping at `tests/test_cycle11_utils_pages.py:20`, `tests/test_cycle11_utils_pages.py:32`, and `tests/test_cycle11_utils_pages.py:38`.

T9 — Compile manifest double-write regression detection should be behavioral, not signature/source-grep based.

Status: PARTIAL — the test now inspects the manifest contents after compile, but it still executes one compile pass and does not capture before/after contents across a second compile as requested by the threat model.

Evidence: fake ingest preserves the manifest side effect at `tests/test_compile.py:244`; the test still counts `save_manifest` calls at `tests/test_compile.py:230` and `tests/test_compile.py:273`; it reads and asserts source hash entries after the compile at `tests/test_compile.py:276`, but there is no second `compile_wiki` invocation after `tests/test_compile.py:266`.

T10 — Class-B PR-introduced CVE surface from dependency edits.

Status: IMPLEMENTED

Evidence: `git diff main..HEAD -- requirements.txt pyproject.toml` returned zero lines; `git diff --stat main..HEAD -- requirements.txt pyproject.toml` returned zero lines.

## Additional Diff Scans

Path-traversal regressions: no new path traversal pattern was found in `git diff main..HEAD -- src tests`. Existing `ingest_source` raw-dir containment remains at `src/kb/ingest/pipeline.py:876` through `src/kb/ingest/pipeline.py:884`.

Injection vectors: no new `eval`, `exec`, `yaml.load`, `pickle.loads`, `shell=True`, or shell-string subprocess vector was found in the diff. New MCP source-type errors are static for `comparison`/`synthesis` at `src/kb/mcp/core.py:300` and `src/kb/mcp/core.py:426`.

Secrets in diff: no `sk-*`, AWS `AKIA*`, Google API key, GitHub PAT, or Slack token pattern was found in `git diff main..HEAD -- src tests`. Repo-wide scan still finds pre-existing contiguous AWS example fixture strings in non-cycle11 files such as `tests/test_capture.py:220`, `tests/test_capture.py:275`, `tests/test_capture.py:296`, `tests/test_capture.py:1050`, `tests/test_capture.py:1537`, and `tests/test_mcp_core.py:364`; those are not introduced by this PR diff.

Input bounds: source-type rejection is early enough to avoid raw-byte reads at `src/kb/ingest/pipeline.py:861` before `src/kb/ingest/pipeline.py:891`. The existing raw-dir containment check remains after the source-type guard at `src/kb/ingest/pipeline.py:876`.

Same-class completeness: PARTIAL. `kb_ingest` and `kb_ingest_content` have the new `comparison`/`synthesis` message, but same-class `kb_save_source` still uses the generic unknown-source-type response and interpolates `source_type` at `src/kb/mcp/core.py:551` and `src/kb/mcp/core.py:553`.

Scope bypasses: FAIL. The required grep was not zero-hit.

```text
grep -rnE 'def _\w*_for_legacy|bypass|unsafe_' src/kb
src/kb/capture.py:179:        # `SECRET="has spaces but is still a long secret"` bypassed the
src/kb/feedback/store.py:167:        # asymptote is silently bypassed — each normalization variant gets its own
src/kb/lint/augment.py:603:    # proposals file. We refuse to re-propose silently, because that bypasses
src/kb/lint/fetcher.py:134:        # This bypasses OS-level re-resolution so a DNS-rebinding attacker
src/kb/lint/fetcher.py:174:        # RuntimeError instead of a silent AttributeError that would bypass the
src/kb/lint/fetcher.py:333:        # to break recursion. Using RobotFileParser.read() would bypass our
src/kb/lint/verdicts.py:50:# Scope: guards only add_verdict's RMW; save_verdicts callers that bypass
```

## Required Grep Results

Class-B CVE surface: EMPTY. `git diff main..HEAD -- requirements.txt pyproject.toml` produced zero lines.

Scope-bypass grep: NON-ZERO, see findings above.

Test anti-pattern grep 1:

```text
grep -rnE 'inspect\.getsource|re\.findall.*\.py' tests/test_cycle11*
zero hits
```

Test anti-pattern grep 2:

```text
grep -rnE 'if\s+\w+:\s*$' tests/test_cycle11*
zero hits
```

## Final Verdict

FAIL

Remediation required:

1. Fix same-class source-type completeness in `src/kb/mcp/core.py:551` by adding the same `comparison`/`synthesis` `kb_create_page` guard to `kb_save_source`, or document why `kb_save_source` intentionally accepts a different error contract.
2. Resolve the required zero-hit scope-bypass grep. Either reword the listed comments to avoid the `bypass` token or narrow the verification grep and update the threat-model expectation.
3. Close T3 drift by migrating `tests/test_backlog_by_file_cycle7.py:437` to patch the canonical import target used by the code under test, and decide whether `src/kb/utils/pages.py:50` should remain as a documented compatibility alias or be removed to satisfy the threat-model grep.
4. Close T5 by adding subprocess CLI command smoke coverage with a minimal environment, or revise the threat model to accept `CliRunner` import smoke tests.
5. Close T9 by running `compile_wiki` twice and asserting manifest contents remain stable across the second pass.
