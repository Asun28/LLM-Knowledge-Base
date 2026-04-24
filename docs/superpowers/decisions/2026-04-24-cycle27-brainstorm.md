# Cycle 27 — Brainstorm

**Scope reference:** 7 ACs across 2 clusters (CLI parity / BACKLOG + CVE hygiene).

## Approach A — Thin Click wrappers calling existing MCP tool functions

Each new CLI subcommand is a ~10-LOC Click handler that imports the corresponding `kb.mcp.browse` function (function-local, preserves boot-lean), calls it with CLI-parsed args, and prints the returned string.

**Pros**
- Zero code duplication — MCP and CLI share formatter.
- Parity is automatic on future MCP-tool changes.
- Minimum LOC (~60-80 src + ~80 test).

**Cons**
- CLI takes on MCP's output format verbatim (markdown with `**bold**`). Acceptable — stdout already renders markdown-ish text in most terminals.
- If MCP tool returns "Error: ..." string on failure, CLI inherits string-return (not non-zero exit). Need wrapper to detect `str.startswith("Error:")` and exit non-zero.

## Approach B — CLI handlers call library functions directly, skip MCP layer

Each CLI subcommand imports `kb.query.engine.search_pages` / `kb.utils.pages.load_all_pages` / etc. and formats output itself.

**Pros**
- Cleaner architecture — CLI doesn't depend on MCP.
- Can produce structured (JSON) output if desired.
- CLI error handling uses Click's built-in patterns (BadParameter, UsageError).

**Cons**
- Formatter duplication — re-implements the same output layout in CLI that MCP already has.
- Future MCP tweaks to output format silently drift from CLI.
- Higher LOC (~150 src + formatters + tests).

## Approach C — Extract shared formatter to `kb.query.formats` module

Factor the MCP tool's output formatting into dedicated `_format_search_results` / `_format_stats` / `_format_page_list` / `_format_source_list` helpers. Both MCP tool and CLI call the helper.

**Pros**
- Clean architecture AND no duplication.
- Single source of truth for output format.
- Easier to add JSON variant later.

**Cons**
- Touches `kb.mcp.browse.py` (extracts formatter) — adds cross-module diff risk.
- Higher initial LOC (~120 src + tests) and Step-11 same-class peer scan surface.
- Overkill for 4 subcommands; better as a future cycle if/when JSON output demanded.

## Recommendation: Approach A

KISS. The MCP tool's markdown output is CLI-printable; parity is automatic; total diff is minimal. One caveat: detect the `str.startswith("Error:")` pattern in CLI wrappers and map to non-zero exit code per Q3 bias.

If a future cycle adds `kb search --format=json`, a shared-formatter refactor becomes mandatory — that's when Approach C lands. Premature now.

## Edge cases surfaced

1. **Empty wiki directory** — `kb_search` / `kb_list_pages` return gracefully ("No matching pages" / empty list). CLI inherits.
2. **Missing `.data/` or `wiki/`** — MCP tools handle via `load_all_pages` which tolerates empty dirs.
3. **`--wiki-dir` override** — `kb_search` passes through to `search_pages(wiki_dir=)`; `kb_stats` accepts `wiki_dir=`. But `kb_list_pages` / `kb_list_sources` do NOT accept `wiki_dir` kwarg — they read the module-level `WIKI_DIR`. Per Q4 bias, SKIP `--wiki-dir` on AC3/AC4 this cycle; file as BACKLOG sub-item for a future parity cycle.
4. **Click eager-exit for `--help`** — already honoured (cycle-13 L3 red-flag noted). AC5 tests use `--help` invocations to avoid the eager-exit short-circuit hitting the subcommand body.
5. **Over-long query** — `kb_search` returns `"Error: Query too long (N chars; max M)."`. CLI detects and exits non-zero. AC1 test pattern.

## Open questions for Step 5

Q1-Q6 from requirements doc. Pre-bias recommended:
- Q1: function-local import (boot-lean)
- Q2: reuse MCP-tool string (Approach A)
- Q3: non-zero exit on error strings
- Q4: skip `--wiki-dir` on AC3/AC4 this cycle
- Q5: fresh Click-style help
- Q6: stderr for errors, stdout for results
