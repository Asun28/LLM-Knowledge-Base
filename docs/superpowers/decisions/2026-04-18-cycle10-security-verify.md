## Verdict
FAIL.

## Threat coverage
| Threat | Class | Evidence |
|---|---|---|
| T1 | IMPLEMENTED | `9d4b447`; `src/kb/lint/_safe_call.py:46-47` catches `Exception` and interpolates `_sanitize_error_str(exc)`; `tests/test_cycle10_safe_call.py:4-16` asserts path redaction. |
| T2 | IMPLEMENTED | `9d4b447`; `src/kb/lint/_safe_call.py:46` uses `except Exception`, not `BaseException`. |
| T3 | PARTIAL | `ee1279f` hardens `_validate_wiki_dir` at `src/kb/mcp/app.py:187-205`; `a1c1f79`/`82b582a` migrate callers. Gap: `src/kb/mcp/health.py:25-29` can return `Path(wiki_dir)` before validation when dependencies are monkeypatched. |
| T4 | IMPLEMENTED | `82b582a`; `src/kb/mcp/health.py:198-202` validates normal `kb_graph_viz` path; `tests/test_cycle10_validate_wiki_dir.py:96-115` asserts traversal rejection. |
| T5 | IMPLEMENTED | `46f0e34`; `src/kb/capture.py:357-365` uses `_secrets.token_hex(16)` UUID fences; `tests/test_cycle10_capture.py:19-31` asserts UUID fence use and legacy fence absence. |
| T6 | IMPLEMENTED | `46f0e34`; `src/kb/capture.py:356-367` caps retries at 3 and raises `ValueError("boundary collision after 3 retries ...")`; `tests/test_cycle10_capture.py:39-46` pins exhaustion. |
| T7 | OUT-OF-SCOPE | Design says torn-line backlog item is STALE/already fixed; current `src/kb/utils/wiki_log.py:126-128` uses `file_lock(log_path)` plus `newline="\n"`. No cycle-10 diff. |
| T8 | OUT-OF-SCOPE | Same design STALE rationale; no `tests/test_cycle10_wiki_log.py` diff. Current behaviour exists at `src/kb/utils/wiki_log.py:114,127`. |
| T9 | IMPLEMENTED | `01bb1bb`; `_coerce_str_field` at `src/kb/ingest/pipeline.py:72-79`; builder call sites at `src/kb/ingest/pipeline.py:352-378`; `tests/test_cycle10_extraction_validation.py:24-33`. |
| T10 | IMPLEMENTED | Design scope-out read; migration limited to summary fields plus pre-validation: `src/kb/ingest/pipeline.py:57-85,348-378,908-916`. Remaining non-summary sites are explicitly cycle-11 scope-out in design. |
| T11 | IMPLEMENTED | Existing cap is before `search_pages` import/call at `src/kb/mcp/browse.py:43-51`; stale marker parity at `src/kb/mcp/browse.py:58-59`; existing tests include `tests/test_backlog_by_file_cycle1.py:316-320` and `tests/test_backlog_by_file_cycle4.py:157-177`. |
| T12 | IMPLEMENTED | `a1c1f79`; `src/kb/mcp/browse.py:91-104` collects all case-insensitive matches and errors on ambiguity; `tests/test_cycle10_browse.py:16-31`. |
| T13 | IMPLEMENTED | `46f0e34`; `captured_at` moved before LLM extraction at `src/kb/capture.py:690-693`; used for writes at `src/kb/capture.py:748-752`; test at `tests/test_cycle10_capture.py:49-85`. |
| T14 | IMPLEMENTED | Design chose canonical `kb.lint._safe_call`; `src/kb/mcp/quality.py:20,106-113,307-331` and `src/kb/mcp/health.py:91-99` use it; implementation sanitized at `src/kb/lint/_safe_call.py:46-47`. |
| T15 | IMPLEMENTED | `70b5e49`/`46f0e34`; docstring notes deletion-pruning despite `save_hashes=False` at `src/kb/compile/compiler.py:228-241`; CLAUDE note at `CLAUDE.md:174`. |

## Secret scan
Finding: `tests/test_cycle10_safe_call.py:6` and `tests/test_cycle10_safe_call.py:16` add hard-coded absolute path `/home/user/secret/path/feedback.json`. It is a synthetic redaction fixture, not a credential, but it violates the requested generic diff scan for added absolute paths. No API keys, bearer tokens, private keys, or realistic credentials found in `git diff main..HEAD`.

## Path-traversal scan
Finding: `src/kb/mcp/health.py:25-29` defines `_wiki_dir_for_legacy_threading_test()` and returns `Path(wiki_dir)` for a caller-supplied `wiki_dir` before `_validate_wiki_dir` when the target function module is unexpected. Normal production paths for `kb_graph_viz`, `kb_verdict_trends`, and `kb_detect_drift` validate at `src/kb/mcp/health.py:198-202,220-224,247-253`, but this bypass remains production code.

Clean for other MCP `Path(...).resolve()` sites reviewed: `src/kb/mcp/browse.py:91-98` is behind `_validate_page_id` and WIKI containment; `src/kb/mcp/core.py:256-266` validates source paths under `RAW_DIR`; `src/kb/mcp/quality.py:480-500` rejects traversal/absolute source refs and resolves under `PROJECT_ROOT`; `src/kb/mcp/app.py:191-205` is the validator itself.

## Same-class residues
- `src/kb/mcp/core.py:206-209`: `logger.debug(..., exc_info=True)` in trust-score merge silently degrades query context; same class as cycle-10 `_safe_call` observability and should close in cycle 11 unless pulled into this PR.
- `src/kb/mcp/health.py:151-165`: `except Exception` logs feedback coverage-gap failure but does not surface a warning to MCP clients; defer to cycle 11 as adjacent fail-safe telemetry class.
- `src/kb/mcp/browse.py:91-98`: containment check is manual `resolve().relative_to(WIKI_DIR.resolve())`; acceptable because page_id is validated and path is non-`wiki_dir`, defer.
- `src/kb/mcp/quality.py:480-500`: manual source-ref traversal checks remain; acceptable because refs are validated as raw-relative and resolved under `PROJECT_ROOT`, defer.

## Blockers (if verdict != PASS)
1. Remove or test-only gate `src/kb/mcp/health.py:25-29` so every MCP `wiki_dir` value is routed through `_validate_wiki_dir` before use.
2. Replace the hard-coded `/home/user/secret/path/feedback.json` fixture in `tests/test_cycle10_safe_call.py:6,16` with a generated temporary absolute path or another non-literal fixture that still verifies redaction.
