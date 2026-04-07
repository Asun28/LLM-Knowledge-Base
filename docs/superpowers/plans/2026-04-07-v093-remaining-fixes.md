# v0.9.3 Remaining Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status: COMPLETE** — All fixes implemented and verified. 17/17 tests pass, full suite 574/574.

**Goal:** Fix critical manifest ordering bug, add missing `kb_compile` MCP tool, implement `kb lint --fix`, consolidate `MAX_SEARCH_RESULTS` config constant.

**Architecture:** Two independent fix groups (manifest+MCP+config, lint-fix) run in parallel. Post-fix: README update, version bump 0.9.3, CLAUDE.md update, commit, push.

**Tech Stack:** Python 3.12+, pytest, click, fastmcp

---

## Group 1: Manifest Fix + kb_compile MCP + Config Constants

**Files:** `src/kb/compile/compiler.py`, `src/kb/mcp/core.py`, `src/kb/config.py`, `src/kb/mcp/browse.py`
**Test:** `tests/test_compiler_mcp_v093.py` (11 tests)

### Fix 1: Manifest saved after successful ingest only

`compile_wiki()` in `compiler.py` — manifest entry written inside the `try` block after `ingest_source()` succeeds, not before. Ensures a failed ingest doesn't falsely mark a source as processed.

- [x] Move manifest save to after `ingest_result = ingest_source(source)` succeeds (`compiler.py`, inside `try` block)
- [x] Verify failed ingest leaves source absent from manifest (`test_compile_manifest_not_saved_on_error`)
- [x] Verify successful ingest records source hash in manifest (`test_compile_manifest_saved_on_success`)

### Fix 2: kb_compile MCP tool

Add `kb_compile` as the 22nd MCP tool in `kb.mcp.core`, calling `compile_wiki()` for full API-driven compilation. Complements `kb_compile_scan` (which lists sources but does not ingest them).

- [x] Add `@mcp.tool() def kb_compile(incremental: bool = True) -> str` in `core.py`
- [x] Wrap `compile_wiki()` in `try/except`, return `"Error running compile: ..."` on failure
- [x] Format output: mode, sources_processed, pages_created, pages_updated, errors sections
- [x] Test tool exists and is callable (`test_kb_compile_tool_exists`)
- [x] Test incremental mode output format (`test_kb_compile_incremental`)
- [x] Test full mode output format (`test_kb_compile_full_mode`)
- [x] Test error details in output (`test_kb_compile_with_errors`)
- [x] Test exception → error string (`test_kb_compile_error_handling`)
- [x] Test zero-sources case (`test_kb_compile_empty_results`)

### Fix 3: MAX_SEARCH_RESULTS config constant

Replace hardcoded `100` in `kb_query` and `kb_search` with `MAX_SEARCH_RESULTS` from `kb.config`. Single source of truth for the cap value.

- [x] Add `MAX_SEARCH_RESULTS = 100` to `config.py`
- [x] Import and use in `kb.mcp.core` — `max(1, min(max_results, MAX_SEARCH_RESULTS))`
- [x] Import and use in `kb.mcp.browse` — same clamping pattern
- [x] Test constant value (`test_max_search_results_config`)
- [x] Test `kb_query` caps at 100 / floors at 1 (`test_max_search_results_used_in_kb_query`)
- [x] Test `kb_search` caps at 100 / floors at 1 (`test_max_search_results_used_in_kb_search`)

---

## Group 2: Lint --fix Implementation

**Files:** `src/kb/cli.py`, `src/kb/lint/runner.py`, `src/kb/lint/checks.py`
**Test:** `tests/test_lint_fix_v093.py` (6 tests)

### Fix 4: fix_dead_links() function

Implement `fix_dead_links(wiki_dir)` in `checks.py`. For each broken wikilink: `[[target|Display Text]]` → `Display Text`; `[[target]]` → basename of target. Writes audit trail to `wiki/log.md`.

- [x] Add `fix_dead_links(wiki_dir)` to `checks.py` using `resolve_wikilinks()` to find broken links
- [x] Group broken links by source page to minimise file reads/writes
- [x] Use `re.IGNORECASE` (since `extract_wikilinks` lowercases targets)
- [x] Handle display-text variant: `re.compile(r"\[\[target\|([^\]]+)\]\]", IGNORECASE)` → `r"\1"`
- [x] Handle plain variant: replace with `target.split("/")[-1]`
- [x] Append audit log entry via `append_wiki_log("lint-fix", ...)`
- [x] Return list of fix dicts: `{check, severity, page, target, message}`
- [x] Test broken wikilink replaced with plain text basename (`test_fix_dead_links_replaces_broken_wikilink`)
- [x] Test display-text variant preserved (`test_fix_dead_links_preserves_display_text`)
- [x] Test valid links untouched (`test_fix_dead_links_ignores_valid_links`)

### Fix 5: run_all_checks(fix=False) plumbing

Plumb `fix` parameter through `run_all_checks()` in `runner.py`. When `fix=True`, call `fix_dead_links()` after `check_dead_links()`, remove fixed issues from the issues list, and populate `fixes_applied` in the return dict.

- [x] Add `fix: bool = False` parameter to `run_all_checks()`
- [x] After `dead_links = check_dead_links(wiki_dir)`, if `fix and dead_links`: call `fix_dead_links(wiki_dir)`
- [x] Remove fixed issues from `all_issues` using `(page, target)` pair matching
- [x] Always include `fixes_applied` key in return dict (empty list when `fix=False`)
- [x] Test `fix=True` populates `fixes_applied` with correct check type (`test_run_all_checks_with_fix_true`)
- [x] Test `fix=False` leaves `fixes_applied` empty and dead link still in issues (`test_run_all_checks_with_fix_false`)

### Fix 6: CLI lint --fix flag

Add `--fix/--no-fix` boolean flag to the `lint` CLI command in `cli.py`. After `format_report()`, print auto-fix summary when fixes were applied.

- [x] Add `@click.option("--fix/--no-fix", default=False, help="Auto-fix issues (default: report only)")` to `lint` command
- [x] Pass `fix=fix` to `run_all_checks(fix=fix)`
- [x] Print `"Auto-fixed N issue(s):"` + per-fix `"  Fixed: {message}"` when fixes applied
- [x] Test `lint --fix` displays auto-fix summary (`test_lint_cli_fix_flag`)

---

## Post-Fix Steps

- [x] Run full test suite (`python -m pytest`) — 431 passed (414→431, 17 new)
- [x] Update `src/kb/__init__.py` version to `"0.9.3"`
- [x] Update `pyproject.toml` version to `"0.9.3"`
- [x] Update `CHANGELOG.md` — Phase 3.4 / v0.9.3 entry
- [x] Update `CLAUDE.md` Implementation Status
- [x] Commit and push

---

## Verification

Context 7 verified (2026-04-08):
- `@click.option("--fix/--no-fix", default=False)` — correct click boolean flag syntax
- `runner.invoke(cli, ["lint", "--fix"])` — correct CliRunner invocation
- `max(1, min(max_results, MAX_SEARCH_RESULTS))` — idiomatic Python clamp
- `@mcp.tool()` — correct FastMCP tool registration decorator
- Tool `-> str` return type — valid, with explicit annotation recommended
