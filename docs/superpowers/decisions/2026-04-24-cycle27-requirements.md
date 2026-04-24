# Cycle 27 — Requirements + Acceptance Criteria

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle27` (branched from `main` @ `0e3fc12`)
**Scope:** Narrow CLI ↔ MCP parity — add 4 read-only CLI subcommands (`search`, `stats`, `list-pages`, `list-sources`) to close part of the Phase 4.5 HIGH "CLI ↔ MCP parity" backlog item.

## Problem

Phase 4.5 HIGH backlog item `cli.py ↔ MCP parity` (BACKLOG.md:151): CLI currently exposes 10 subcommands while MCP exposes 28 tools. Operators working from scripts / cron / CI must use `python -c "from kb.mcp.browse import kb_search; ..."` or spawn an MCP client just to run basic read-only queries. The gap is 18 tools; cycle 27 closes FOUR of them — the most operationally useful read-only lookups:

- `kb search <query>` — BM25 search with optional vector fusion; ranks pages by relevance.
- `kb stats` — wiki-health snapshot (page counts by type, orphan count, dead-link count).
- `kb list-pages [--type T]` — enumerate wiki pages (optional filter by page type).
- `kb list-sources` — enumerate raw sources with wiki-backlink info.

Each is a thin Click wrapper around the existing MCP-tool body. Reusing the pre-formatted MCP output string keeps parity automatic on future changes. All four tools are read-only — no filesystem writes, no new trust boundary, no new state.

## Non-goals

- **NOT** adding write-path CLI commands (`kb_review_page`, `kb_refine_page`, `kb_query_feedback`, `kb_save_source`, `kb_save_lint_verdict`, `kb_create_page`, `kb_capture`, `kb_save_synthesis`). Those have their own concurrency + validation concerns; deferred.
- **NOT** adding `kb_query` / `kb_ingest` / `kb_ingest_content` / `kb_compile` — these already have CLI wrappers (`kb query`, `kb ingest`, `kb compile`).
- **NOT** adding the remaining health/quality tools (`kb_lint_deep`, `kb_lint_consistency`, `kb_verdict_trends`, `kb_graph_viz`, `kb_detect_drift`, `kb_reliability_map`, `kb_affected_pages`). Those produce complex output better suited to an MCP client's rendering; deferred.
- **NOT** refactoring shared formatting into a helper. The MCP tool returns a formatted string; CLI prints it. If a future cycle wants structured output (JSON), it becomes a format-split design discussion.
- **NOT** changing existing MCP tool signatures or return types.

## Acceptance Criteria

### Cluster A — CLI subcommand additions (5 ACs)

**AC1 — `kb search <query>` CLI subcommand.** New Click subcommand in `src/kb/cli.py`:

```
kb search <query> [--limit N] [--wiki-dir PATH]
```

- Forwards to `kb.query.engine.search_pages(question=query, wiki_dir=wiki_dir, max_results=limit)`.
- Formats output identically to `kb.mcp.browse.kb_search` — preserves `[STALE]` markers + type + score.
- `--limit` defaults to 10; capped at `MAX_SEARCH_RESULTS` (existing constant).
- `--wiki-dir` defaults to `WIKI_DIR` (None → use config default).
- Empty query → non-zero exit with "Query cannot be empty." stderr message.
- Over-long query (`> MAX_QUESTION_LEN`) → non-zero exit with length error.

**Test expectation:** `CliRunner().invoke(cli, ["search", "--help"])` exit 0; `["search", ""]` exit non-zero with error message.

**AC2 — `kb stats` CLI subcommand.** New Click subcommand:

```
kb stats [--wiki-dir PATH]
```

- Forwards to `kb.mcp.browse.kb_stats(wiki_dir=wiki_dir)` (already accepts `wiki_dir`).
- Prints the formatted stats string exactly as the MCP tool returns.
- `--wiki-dir` accepted; passes through to the library function.

**Test expectation:** `CliRunner().invoke(cli, ["stats", "--help"])` exit 0; `["stats", "--wiki-dir", str(tmp_wiki)]` exit 0 with non-empty output.

**AC3 — `kb list-pages` CLI subcommand.** New Click subcommand:

```
kb list-pages [--type TYPE] [--limit N] [--offset N] [--wiki-dir PATH]
```

- Forwards to `kb.mcp.browse.kb_list_pages(page_type=type, limit=limit, offset=offset)`.
- `--type` is optional (`""` default = all types).
- `--limit` defaults to 200 (existing MCP default).
- `--offset` defaults to 0.

**Test expectation:** help + basic invocation with tmp_wiki; filters by `--type concepts`.

**AC4 — `kb list-sources` CLI subcommand.** New Click subcommand:

```
kb list-sources [--limit N] [--offset N]
```

- Forwards to `kb.mcp.browse.kb_list_sources(limit=limit, offset=offset)`.
- `--limit` defaults to 200 (existing MCP default).
- `--offset` defaults to 0.

**Test expectation:** help + basic invocation.

**AC5 — Regression test file `tests/test_cycle27_cli_parity.py`.** Four tests minimum (one per new subcommand), using `CliRunner().invoke(cli, [...])`:

1. `test_cli_search_help_exits_zero` — `["search", "--help"]` exits 0, output mentions "Search wiki pages".
2. `test_cli_stats_help_exits_zero` — `["stats", "--help"]` exits 0.
3. `test_cli_list_pages_help_exits_zero` — `["list-pages", "--help"]` exits 0, mentions `--type`.
4. `test_cli_list_sources_help_exits_zero` — `["list-sources", "--help"]` exits 0.

Plus 1 functional smoke test (AC5b): `test_cli_search_returns_empty_on_empty_wiki` using `tmp_wiki` fixture — empty wiki → "No matching pages found" output.

Total: 5 tests.

### Cluster B — BACKLOG + CVE hygiene (2 ACs)

**AC6 — Narrow BACKLOG `CLI ↔ MCP parity` entry.** Update BACKLOG.md:151 to cite cycle 27 shipped commands. New gap: 14 tools (was 18). Remaining quick-ship candidates enumerated in the BACKLOG entry for future cycles.

**AC7 — CVE date-stamp re-verification, conditional.** Run `pip-audit --format=json` against installed venv; compare `diskcache` + `ragas` output against cycle-26 baseline (already 2026-04-24). If unchanged: NO BACKLOG edit (same-day re-stamp is noise per cycle-26 Q12). If diverged: re-stamp. Document either way in commit message.

## Conditions (Step 5 decision gate must resolve)

1. **Q1 — Import strategy for CLI shims.** Function-local import of MCP tools inside Click subcommand body (preserves boot-lean contract per cycle-23 AC4) OR top-level import (simpler)? *Bias:* function-local — keeps `kb --version` short-circuit intact.
2. **Q2 — Reuse MCP-tool formatted output vs library-level call?** MCP tool output includes emoji-free formatted markdown which IS CLI-printable. Library call would require re-implementing formatting. *Bias:* reuse MCP-tool output string directly (KISS, auto-parity).
3. **Q3 — Exit code on "empty query" / "no results"?** Empty query should exit non-zero (user error). No results should exit 0 (valid outcome). *Bias:* yes.
4. **Q4 — `--wiki-dir` scope.** AC1/AC2 pass through; AC3/AC4 — MCP `kb_list_pages` + `kb_list_sources` do NOT accept `wiki_dir` kwarg today. Add `--wiki-dir` anyway (pre-validate, ignore if not supported)? Or skip? *Bias:* skip `--wiki-dir` on AC3/AC4 this cycle — file as separate BACKLOG sub-item if demanded.
5. **Q5 — CLI help text source.** Derive from MCP tool docstring, or write fresh Click-style help? *Bias:* fresh Click-style — matches existing CLI convention.
6. **Q6 — Stdout vs stderr for error messages.** Errors (empty query, over-long) go to stderr per Unix convention; results go to stdout. *Bias:* yes.

## Blast radius

- `src/kb/cli.py` — 4 new Click subcommand functions (~15-25 LOC each).
- `tests/test_cycle27_cli_parity.py` — new file, 5 tests.
- `BACKLOG.md` — 1 entry narrowed (AC6).
- `CHANGELOG.md` / `CHANGELOG-history.md` / `CLAUDE.md` — cycle 27 narrative.

**No changes to:** MCP tool registry, library functions (`search_pages` etc.), any trust boundary. No new filesystem writes (all read-only paths). No new security enforcement.
