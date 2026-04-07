# v0.9.3 Remaining Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical manifest ordering bug, add missing kb_compile MCP tool, implement kb lint --fix, consolidate config constants, update README.

**Architecture:** Two independent fix groups (manifest+MCP+config, lint-fix) run in parallel. Post-fix: README update, version bump 0.9.3, CLAUDE.md update, commit, push.

**Tech Stack:** Python 3.12+, pytest, click, fastmcp, python-frontmatter

---

### Group 1: Manifest Fix + kb_compile MCP + Config Constants
**Files:** `src/kb/compile/compiler.py`, `src/kb/mcp/core.py`, `src/kb/config.py`
**Test:** `tests/test_compiler_mcp_v093.py`

Fixes:
1. Move manifest save AFTER successful ingest (compiler.py:182-185)
2. Add `kb_compile` MCP tool calling `compile_wiki()`
3. Add `MAX_SEARCH_RESULTS = 100` config constant, use in browse.py and core.py

### Group 2: Lint --fix Implementation
**Files:** `src/kb/cli.py`, `src/kb/lint/runner.py`, `src/kb/lint/checks.py`
**Test:** `tests/test_lint_fix_v093.py`

Fixes:
1. Implement `--fix` in lint runner: auto-fix dead links (replace broken `[[link]]` with plain text)
2. Plumb `fix` parameter through `run_all_checks()` to `check_dead_links()`
3. Report what was fixed in CLI output

### Post-Fix
1. Update README.md with v0.9.2 + v0.9.3 release notes
2. Bump version to 0.9.3
3. Update CLAUDE.md
4. Commit and push
