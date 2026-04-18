# Cycle 10 PR #24 - Round 2 Code Review (Codex)

## Verdict

APPROVE-WITH-REVISIONS.

R1's code blockers are resolved, and the targeted regression set passes. I would not merge yet because the R1 claim for Codex M2 is not actually satisfied in `CHANGELOG.md`: the vector floor is mentioned, but the RRF skew / ranking trade-off is not clearly documented.

## Blockers closed

- Sonnet M1 (PROJECT_ROOT mutation race): CLOSED. `_validate_wiki_dir` now takes keyword-only `project_root: Path | None = None` and resolves `project_root or PROJECT_ROOT` locally (`src/kb/mcp/app.py:188-205`). The `health.py` and `browse.py` shims no longer mutate `mcp_app.PROJECT_ROOT`; they pass `project_root=PROJECT_ROOT` at each call site (`src/kb/mcp/health.py:14`, `:59`, `:121`; `src/kb/mcp/browse.py:324`).
- Sonnet M3 (`_sanitize_error_str` deferred import fragility): CLOSED. `sanitize_error_text` is in `src/kb/utils/sanitize.py:15-24`, has no side effects, handles `filename` / `filename2`, and applies the absolute-path regex sweep. `_safe_call` imports it at module load (`src/kb/lint/_safe_call.py:17`) and uses it in the exception path (`:47`).
- Codex M1 (caller-boundary tests missing): CLOSED. The two requested tests exist: `test_kb_lint_surfaces_sanitised_feedback_error_from_caller` (`tests/test_cycle10_safe_call.py:41`) and `test_lint_runner_surfaces_sanitised_verdict_history_error` (`:54`).
- Codex M2 (RRF skew): PARTIAL / OPEN. `CHANGELOG.md:43` notes `VECTOR_MIN_SIMILARITY`, and `src/kb/config.py:181-186` documents that below-threshold vector results are silent before RRF. However, neither clearly records the intentional ranking trade-off that weak vector hits can be dropped entirely, allowing BM25/PageRank to dominate RRF rather than preserving vector recall. Add a short explicit CHANGELOG sentence.
- Codex N3 (extraction None): CLOSED / unfounded. `src/kb/ingest/pipeline.py:916-918` calls `extract_from_source(...)` when `extraction is None`, then validates the resulting extraction.
- Sonnet N2 (monotonic clock): DEFERRED / still passing. The test remains wall-clock based (`tests/test_cycle10_capture.py:84-85`), matching the defer decision. It passed in the targeted regression run.

## New issues

- LOW: `src/kb/mcp/app.py:158-183` now calls `sanitize_error_text(exc)` before processing explicit `paths`. Because the shared helper regex-redacts absolute paths first, explicit path arguments no longer get rewritten to `_rel(path)` as the `_sanitize_error_str` docstring says; they become `<path>`. Security is preserved, but diagnostics and documentation changed. Either call `sanitize_error_text` after explicit path replacement, or update the docstring/tests to say explicit paths may be generically redacted.

## Nits

- The thread-safety test (`tests/test_cycle10_validate_wiki_dir.py:92-117`) spawns 20 threads with distinct `project_root` values and proves the new explicit-parameter API is independent. It would not have directly failed under the old shim mutation pattern because it calls `_validate_wiki_dir` directly rather than invoking `health.py` / `browse.py` wrappers in parallel. Code inspection still confirms the race source is removed.
- R1 touched support tests outside the three fix targets (`tests/test_backlog_by_file_cycle6.py`, `tests/test_cycle9_mcp_health.py`, `tests/test_v5_kb_lint_signature.py`) only to move monkeypatching from `mcp_app.PROJECT_ROOT` to `health.PROJECT_ROOT`; I do not see product scope creep.

## Verification

- `git show 244c095 --stat`: 10 files changed, 109 insertions, 36 deletions. Main changes were `_safe_call`, `_validate_wiki_dir` callers, new `kb.utils.sanitize`, and caller/thread-safety tests.
- Requested regression command needed PowerShell-expanded globs; equivalent run passed: 106 passed, 2 skipped.

## Merge recommendation

No - add the explicit RRF trade-off CHANGELOG note first; the code fixes themselves are acceptable.
