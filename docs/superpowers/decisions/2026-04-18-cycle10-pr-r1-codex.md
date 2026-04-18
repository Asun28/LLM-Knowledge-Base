## Verdict
APPROVE-WITH-REVISIONS

## Blockers
None.

## Majors
- `src/kb/lint/_safe_call.py:46` changes the shared error contract from raw exception text to `_sanitize_error_str(exc)`, but the added coverage only exercises the helper directly with synthetic labels (`tests/test_cycle10_safe_call.py:11`, `tests/test_cycle10_safe_call.py:29`). The two cycle-7 consumers called out by the design are therefore unverified at the caller boundary: `kb_lint` appends the `feedback_flagged_pages` error into an HTML comment at `src/kb/mcp/health.py:91`, and the pre-existing `lint/runner.py:137` verdict-history path is not touched in this diff. Add caller-level regression coverage that forces those exact paths to raise with an absolute path in the exception and asserts the surfaced message uses the sanitized shape.

## Nits
- Scope-discipline note: commit `70b5e49` groups the drift-pruning docstring change in `src/kb/compile/compiler.py:228` with the pipe-title escaping change in `src/kb/utils/text.py:294`. Both changes match the cycle-10 design, but this is a multi-source-file commit outside the explicitly sanctioned `browse`+`health` wiki_dir and `capture`+`CLAUDE.md` clusters.
