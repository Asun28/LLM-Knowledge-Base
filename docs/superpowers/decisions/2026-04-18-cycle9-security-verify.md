# Cycle 9 Security Verification (Step 11) - 2026-04-18

Inputs checked:
- `docs/superpowers/decisions/2026-04-18-cycle9-threat-model.md`
- `docs/superpowers/decisions/2026-04-18-cycle9-design.md`
- `git log --oneline main..HEAD`: 14 cycle-9 commits present
- `git diff main..HEAD --stat`: 25 files, focused on the planned cycle-9 blast radius

## Threat Checklist

T1: PARTIAL - AC7/AC8 size caps are present for `kb_ingest` and `kb_ingest_content`; AC11 augment summary is per-stub; `kb_compile_scan` gained `wiki_dir` and threads `raw_dir` plus `manifest_path`. Gap: `kb_compile_scan(wiki_dir=...)` derives paths directly from `Path(wiki_dir)` with no validation, so a caller can steer scan/read and manifest write targets outside the intended project shape.

T2: PARTIAL - AC1/AC2/AC3 query vector path, stale flag root, and hybrid gate use `_vec_db_path(wiki_dir or WIKI_DIR)` / `wiki_dir.parent`; raw fallback derives `wiki_dir.parent / "raw"`; AC5/AC6 feedback reads use an override-scoped `feedback_path`. Gap: the new `wiki_dir` to `raw_dir` / `manifest_path` / `feedback_path` derivations are not validated before use.

T3: IMPLEMENTED - `load_manifest` now catches `OSError` in addition to JSON/Unicode decode errors and returns `{}` with a warning. No new locks were expected or introduced.

T4: IMPLEMENTED - `_normalize_for_scan` broadens decode exceptions and logs debug skips; `MAX_PROMPT_CHARS` exists and gates capture LLM prompt assembly; YAML title round-trip regression tests cover backslashes and quotes; `_make_api_call` redacts secrets before truncation at all four error paths. Redaction markers are static strings, so regex-matched secret content is not reflected into the output.

T5: IMPLEMENTED - `src/kb/ingest/__init__.py` uses lazy `__getattr__` for `ingest_source`, with subprocess coverage proving `kb.ingest.pipeline` is not loaded until attribute access.

T6: IMPLEMENTED - `check_source_coverage` parses frontmatter once per page and reuses the parsed body/metadata; evolve orphan detection now uses graph resolver parity with the slug-index behavior.

T7: IMPLEMENTED - MCP instructions are rendered from grouped tool tuples and sorted within each group; `.env.example` marks `ANTHROPIC_API_KEY` optional for Claude Code MCP mode.

## Additional Security Scans

Path traversal:
- New path parameters/derivations found at `src/kb/mcp/core.py:617-619`, `src/kb/mcp/health.py:59-60`, `src/kb/mcp/health.py:116-117`, and `src/kb/query/engine.py:694`.
- `kb_compile_scan(wiki_dir=...)` does run into an unvalidated path: `Path(wiki_dir)` is used to derive sibling `raw/` and `.data/hashes.json` without `resolve()` plus shape/containment checks.
- `query_wiki` raw fallback resolves `wiki_dir.parent / "raw"`, but does not enforce containment; the function docstring explicitly says it does not enforce `PROJECT_ROOT` containment.

Injection:
- No new LLM prompt assembly path was added other than the capture `MAX_PROMPT_CHARS` guard.
- AC27 redaction uses fixed regexes and fixed replacement markers; matched content is removed before truncation and not reflected into the error string.

Secrets in code:
- `rg -n "sk-ant-|sk-proj-|Bearer " src` found only regex patterns/comments in `src/kb/capture.py` and `src/kb/utils/llm.py`, not committed live keys.
- Gap: new tests contain full key-shaped literals instead of split-string construction: `tests/test_cycle9_llm_redaction.py:80`, `:94`, and `:125`. These are synthetic, but violate the test-secret hygiene rule.

Input bounds:
- AC7 char cap: implemented in `kb_ingest` before prompt construction.
- AC8 content cap: implemented via `MAX_INGEST_CONTENT_CHARS` validation before `kb_ingest_content` writes.
- AC16 slug collision cap: implemented with `_SLUG_COLLISION_CEILING = 10000`.
- AC21 prompt cap: implemented with `MAX_PROMPT_CHARS = 600_000`.

Dependency CVEs:
- Ran `.venv/Scripts/python -m pip_audit --format json > .tmp/cycle-9-cve-branch.json 2>&1`.
- Baseline IDs: `CVE-2025-69872`.
- Branch IDs: `CVE-2025-69872`.
- INTRODUCED: none.

Same-class leak check:
- AC5/AC6 scope-out preserved: `kb_reliability_map()` and `kb_query_feedback(...)` did not gain `wiki_dir` plumbing.
- AC7 scope-out preserved: `kb_compile(incremental=True)` did not gain `wiki_dir` plumbing.
- AC27 scope-out preserved: `_sanitize_error_str` in `src/kb/mcp/app.py` still handles filesystem path redaction only; it was not widened to secret redaction and was not narrowed.

## Final Verdict

REJECT

Gaps:
1. Unvalidated override path derivation on new path-plumbing sites. At minimum, `kb_compile_scan(wiki_dir=...)` must validate the resolved wiki directory and derived `raw_dir` / `manifest_path` before scanning or writing the manifest. Apply the same validation stance to newly derived `feedback_path` and raw fallback paths, or explicitly document and test the accepted trust boundary.
2. Replace full synthetic key-shaped strings in new tests with split-string construction so repository scans do not contain realistic-looking `sk-ant-` / `sk-proj-` literals outside regex definitions or placeholders.

