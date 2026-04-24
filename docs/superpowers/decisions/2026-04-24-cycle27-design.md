# Cycle 27 — Design Decision (merged R1/R2/gate, inline)

**Date:** 2026-04-24
**Scope:** 7 ACs, pure internal refactor (4 new CLI subcommands wrapping existing MCP tools). Step 2 threat model skipped per "pure internal refactor" skill clause; inline mini threat model at `cycle27-threat-model.md`.

## Verdict

**PROCEED.** Requirements + brainstorm + pre-biased Q1-Q6 answers form a coherent small-cycle plan. Symbol verification confirmed all cited symbols exist with expected signatures.

## Symbol verification (cycle-15 L1)

| Symbol | File:Line | Status |
|---|---|---|
| `kb_search` | `src/kb/mcp/browse.py:31` | EXISTS (signature: `query: str, max_results: int = 10`) |
| `kb_stats` | `src/kb/mcp/browse.py:318` | EXISTS (`wiki_dir: str \| None = None`) |
| `kb_list_pages` | `src/kb/mcp/browse.py:150` | EXISTS (`page_type: str = "", limit=200, offset=0`) |
| `kb_list_sources` | `src/kb/mcp/browse.py:209` | EXISTS (`limit=200, offset=0`) |
| `MAX_QUESTION_LEN` | `src/kb/config.py:426` (= 2000) | EXISTS |
| `MAX_SEARCH_RESULTS` | `src/kb/config.py:364` (= 100) | EXISTS |
| `sys.argv` short-circuit | `src/kb/cli.py:15-19` | EXISTS (cycle-7 AC30) |

## Decisions (Q1-Q6)

| Q | Decision | Rationale |
|---|----------|-----------|
| Q1 | Function-local import of MCP-browse functions inside each Click subcommand body | Preserves cycle-23 AC4 boot-lean contract (bare `import kb` / `kb --version` must not pull `kb.mcp.browse`) |
| Q2 | Reuse MCP-tool formatted output string directly; no formatter extraction | KISS; automatic parity on future MCP tweaks |
| Q3 | Error strings (output matches `"Error: ..."`) map to non-zero exit via `_error_exit()` or click.echo + sys.exit(1) | Unix convention: user-error → non-zero |
| Q4 | Skip `--wiki-dir` on `list-pages` and `list-sources` this cycle; AC1 + AC2 pass through (MCP tools already accept it) | `kb_list_pages` / `kb_list_sources` do NOT accept `wiki_dir` kwarg; adding it requires MCP signature change — defer to future parity cycle |
| Q5 | Fresh Click-style `help=...` on each option | Matches existing CLI convention (e.g. `kb ingest`, `kb query`) |
| Q6 | Results to stdout via `click.echo`; errors via `click.echo(..., err=True)` then `sys.exit(1)` | Standard |

## CONDITIONS (Step 9 must satisfy)

1. **CONDITION 1 — Function-local imports.** Every new subcommand body imports `kb.mcp.browse.kb_*` INSIDE the function, NOT at module scope. Grep: `rg "^from kb\.mcp\.browse import" src/kb/cli.py` returns 0 matches.
2. **CONDITION 2 — Error-string → non-zero exit.** Each subcommand checks `if output.startswith("Error:"): click.echo(output, err=True); sys.exit(1)` before printing. Preserves Q3 contract.
3. **CONDITION 3 — 5 tests minimum in `test_cycle27_cli_parity.py`.** 4 `--help` smoke tests + 1 functional test using `tmp_wiki` fixture.
4. **CONDITION 4 — `kb --version` short-circuit still runs at line 15-19.** Grep: `rg "sys\.argv\[1\] in" src/kb/cli.py` returns the pre-existing guard untouched.
5. **CONDITION 5 — BACKLOG CLI↔MCP parity entry narrowed, not deleted.** Remaining-gap count updated from 18 to 14.
6. **CONDITION 6 — AC7 skip-on-no-diff.** Cycle-27 pip-audit output == cycle-26 baseline → NO BACKLOG edit on diskcache/ragas entries (same-day noise avoidance).
7. **CONDITION 7 — `--wiki-dir` scope limited per Q4.** AC1 passes `wiki_dir` through to `search_pages` (NOT via `kb_search` which doesn't accept it — call `search_pages` directly with `--wiki-dir` support); AC2 passes through to `kb_stats` (which accepts it); AC3/AC4 do NOT offer `--wiki-dir`.

### CONDITION 7 refinement

For AC1 `kb search`, the cleanest path is to call `kb.query.engine.search_pages` directly (which accepts `wiki_dir`) AND reuse the MCP formatter inline. Options:

- (a) Call `search_pages` + inline format → ~15 LOC duplication of `kb_search` formatter. Rejected.
- (b) Call `kb_search(query, max_results)` and accept that `--wiki-dir` isn't honoured on AC1. Simpler; loses feature.
- (c) Extract a `_format_search_results(results)` helper in `kb.mcp.browse` and call it from both `kb_search` and the new CLI subcommand with `wiki_dir` override. Modest refactor, ~15 LOC extracted.

**Resolution:** (c) — extract `_format_search_results` helper + CLI calls `search_pages(wiki_dir=...)` + formatter. Also satisfies Q4 (`--wiki-dir` pass-through). Updates AC1 test-expectation to cover the helper split.

## FINAL DECIDED DESIGN (folded)

### Cluster A — CLI subcommands (5 ACs)

**AC1 — `kb search <query>`.** Click subcommand. Imports `kb.query.engine.search_pages` + `kb.mcp.browse._format_search_results` function-locally. Supports `--limit`, `--wiki-dir`. Length-gate on query via `MAX_QUESTION_LEN`. Error strings → exit 1.

**AC1b — extract `_format_search_results(results: list[dict]) -> str` helper in `kb.mcp.browse`.** Preserves existing `kb_search` output 100%. New CLI uses this helper. Regression test: `kb_search` output equals formatted helper output on same seed.

**AC2 — `kb stats`.** Click subcommand. Function-local import of `kb.mcp.browse.kb_stats`. Supports `--wiki-dir`. Error strings → exit 1.

**AC3 — `kb list-pages`.** Click subcommand. Function-local import of `kb.mcp.browse.kb_list_pages`. `--type`, `--limit`, `--offset`. NO `--wiki-dir` this cycle.

**AC4 — `kb list-sources`.** Click subcommand. Function-local import of `kb.mcp.browse.kb_list_sources`. `--limit`, `--offset`. NO `--wiki-dir` this cycle.

**AC5 — `tests/test_cycle27_cli_parity.py`.** 5 tests: 4 `--help` smoke tests + 1 functional test via `tmp_wiki`. Use `CliRunner().invoke(cli, [subcmd, "--help"])`.

### Cluster B — BACKLOG + CVE hygiene (2 ACs)

**AC6 — Narrow BACKLOG `CLI ↔ MCP parity` entry** (CONDITION 5).

**AC7 — CVE date-stamp re-verification, conditional** (CONDITION 6). Cycle-27 pip-audit matches cycle-26 baseline → no edit.

## Blast radius (unchanged from requirements, +1 helper extraction)

- `src/kb/cli.py` — 4 new subcommands (~80 LOC).
- `src/kb/mcp/browse.py` — extract `_format_search_results` (~15 LOC moved, 0 new).
- `tests/test_cycle27_cli_parity.py` — new, 5 tests.
- `BACKLOG.md` — 1 entry narrowed.
- Docs cycle-27 narrative.

## Step 9 readiness

All CONDITIONS concrete. Primary-session implementation per cycle-13 L2 sizing (7 tasks, each <25 LOC, stdlib-only APIs). No Codex dispatch overhead.
