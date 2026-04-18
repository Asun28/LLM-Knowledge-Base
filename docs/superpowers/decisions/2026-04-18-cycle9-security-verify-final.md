# Cycle 9 Security Re-Verification Final - 2026-04-18

Verdict: REJECT

Inputs checked:
- Prior verdict: `docs/superpowers/decisions/2026-04-18-cycle9-security-verify.md` rejected on unsplit test secret literals and unvalidated `wiki_dir` path derivation.
- `git log --oneline main..HEAD`: 16 commits confirmed. The two fix commits are at the tip: `0e42e3a` split-string test secret literals and `6381c2b` MCP `wiki_dir` validator.
- `git diff main..HEAD --stat`: 26 files changed, 1475 insertions, 177 deletions. Scope remains Cycle 9 implementation/tests plus the new MCP path-validation test file.

## Re-Checks

1. Secret hygiene:
   - Command equivalent: `rg -n -e 'sk-ant-[A-Za-z0-9]{10,}|sk-proj-[A-Za-z0-9]{10,}|Bearer [A-Za-z0-9]{20,}' tests`
   - Result: one remaining hit:
     - `tests/test_backlog_by_file_cycle1.py:118`: `Authorization: Bearer abcdefghijklmnop1234`
   - The Cycle 9 `sk-ant` / `sk-proj` test literals from the original rejection are fixed, and `tests/test_backlog_by_file_cycle1.py` is not changed by `main..HEAD`. However, the requested broad `tests/` scan still finds an unsplit key-shaped `Bearer` literal.

2. `wiki_dir` path containment:
   - `src/kb/mcp/core.py:624`: `kb_compile_scan` calls `_validate_wiki_dir(wiki_dir)` before deriving `raw_dir` and `manifest_path`.
   - `src/kb/mcp/health.py:56`: `kb_lint` calls `_validate_wiki_dir(wiki_dir)` before deriving lint/feedback paths.
   - `src/kb/mcp/health.py:116`: `kb_evolve` calls `_validate_wiki_dir(wiki_dir)` before invoking evolve analysis.
   - Result: PASS for the three requested MCP sites.

3. CVE delta:
   - Re-ran `.venv/Scripts/python -m pip_audit --format json > .tmp/cycle-9-cve-branch-final.json 2>&1`.
   - The command exited nonzero because one known vulnerability is present.
   - Baseline vuln IDs: `CVE-2025-69872`.
   - Branch vuln IDs: `CVE-2025-69872`.
   - Affected package: `diskcache 5.6.3`.
   - Introduced CVEs: none.
   - Result: PASS. Only the pre-existing Class A `diskcache` CVE remains.

## Remaining Gap

The broad test secret-hygiene scan still contains one unsplit `Bearer` token-shaped literal in `tests/test_backlog_by_file_cycle1.py:118`. Split that synthetic string before accepting the security re-verification.
