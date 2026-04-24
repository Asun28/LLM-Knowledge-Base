# Cycle 30 — Requirements + Acceptance Criteria

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle30`
**Baseline:** 2826 tests / 247 files (post-cycle-29 main)
**Pattern:** Backlog-by-file hygiene cycle (cycle-27 parity continuation + cycle-29 follow-up)

## Problem

Three distinct pre-Phase-5 backlog items discovered via Step 0 survey of `BACKLOG.md`
(Phase 4.5 MEDIUM section) and cycle-29 Step-11 T1 PARTIAL follow-up:

1. **Audit-log bloat exposure (cycle-29 follow-up).** `compile/compiler.py::_audit_token`
   passes `result[X]["error"]` verbatim into the `msg` string written via
   `append_wiki_log(msg, ...)` at line 794-798 and into CLI stdout via
   `kb.cli.rebuild_indexes_cmd` (line 544-559). On Windows `OSError.__str__()`
   can emit ~1KB for a single path-not-found error; a pathological chain of
   errors bloats `wiki/log.md` and floods the terminal. `append_wiki_log`
   sanitizes `| \n \r \t` but does NOT truncate. Filed in BACKLOG by cycle-29
   Step-11 Codex as MEDIUM.

2. **CLI ↔ MCP parity gap.** Cycle 27 added 4 CLI subcommands over browse-tier
   read-only tools (`search`, `stats`, `list-pages`, `list-sources`), leaving
   **14** MCP tools without CLI surface per BACKLOG line 149. Five of those
   tools are strictly read-only health/quality reports that follow the
   cycle-27 cookie-cutter pattern (function-local import + thin wrapper +
   `--help` smoke + body-exercising test per cycle-27 L2). Shipping them
   shrinks the gap to 9, aligns the CLI with the MCP surface a scripting
   user relies on, and closes the "consistent UX across both surfaces"
   half of the BACKLOG entry.

3. **BACKLOG lifecycle drift.** Cycle 29 AC5 deleted a Phase-4.5 HIGH #6
   cold-load bullet but left 14 BACKLOG entries in CLI↔MCP parity status
   outdated relative to the cycle-27 delta. A targeted narrow + stale-
   scan routine keeps the file aligned with reality.

## Non-goals

- No write-path CLI tools (`kb_refine_page`, `kb_save_source`,
  `kb_query_feedback`, etc.) — deferred pending a write-path-specific cycle
  with input-validation focus.
- No signature change to MCP tools (`kb_list_pages` / `kb_list_sources`
  intentionally omit `--wiki-dir` per cycle-27 Q4; carry the same omission
  here).
- No `kb_read_page` CLI wrapper in this cycle — it's read-only and shaped
  similarly, but it is **body-bearing** (50+ KB cap, UTF-8 decode fallback,
  ambiguous-page_id handling) and deserves its own design pass — deferred.
- No `kb_affected_pages` CLI wrapper — accepts `page_id` input and runs
  backlink computation; marginally more logic than a thin wrapper, deferred
  to keep cycle 30 uniformly read-only-health-tier.
- No second pass of `BACKLOG.md` MEDIUM structural rewrites (god-module
  split, file-lock JSONL migration, compile two-phase pipeline) — these
  are architectural changes, not batch-by-file hygiene.
- No change to `_audit_token`'s return shape. AC1 limits the mutation to
  the **error-string subfield** rendered inside the returned token — the
  "cleared" / "cleared (warn: ...)" / "unknown" schema is unchanged.
- No change to `append_wiki_log` sanitizer (widening its responsibility
  to include length caps crosses into scope of the deferred JSONL audit
  migration).

## Acceptance Criteria

### AC1 — Audit error-string length cap (`compile/compiler.py::_audit_token`)

- `_audit_token(block)` caps `block["error"]` at **500 chars** before
  rendering into the returned string, via a function-local import of
  `kb.utils.text.truncate(msg, limit=500)`. Both the `cleared (warn: ...)`
  branch and the fallback `{error}` branch pass through the cap.
- The cap is applied to the **string form of the error** — `str(block["error"])`
  — so non-string values (rare; compound prefixes already string-format upstream)
  are coerced then capped.
- `truncate` already implements head+tail smart truncation with an inline
  `"...N chars elided..."` marker (see `kb.utils.text.truncate` docstring,
  cycle 3 M17). Using it preserves diagnostic value — path prefix at head,
  errno at tail — on capped messages.
- **Regression test** pins: a 2000-char synthetic error round-trips
  through `_audit_token` with length ≤ 500 + `truncate` marker length
  (roughly ≤ 540 chars); the 500-char budget is divided head/tail with
  the cycle-3 marker verbatim in the middle; rebuild_indexes call path
  persists the capped line to `wiki/log.md` (not a raw 2000-char line).
- **Blast radius:** `compile/compiler.py::_audit_token` (3-line body change
  + 1-line function-local import); no caller contract change; CLI mirror
  (`cli.py::rebuild_indexes_cmd`) inherits the cap automatically via
  the same `_audit_token` import.
- **BACKLOG:** delete the cycle-29 MEDIUM entry for this exact item.

### AC2 — `kb graph-viz` CLI subcommand (`cli.py`)

- Thin wrapper over `kb_graph_viz(max_nodes, wiki_dir)`. Options:
  `--max-nodes INT` (default 30, range 1-500 per MCP contract — `0`
  rejected explicitly by the MCP tool with an error string; we pass the
  user value through verbatim so the CLI surfaces the same error line).
  `--wiki-dir PATH` (cycle-23 dual-anchor containment via
  `_validate_wiki_dir`).
- Prints the Mermaid diagram to stdout. On `"Error:"` prefix → exit 1
  and print to stderr (cycle-27 pattern in `stats`/`list-pages`/`list-sources`).
- **Regression test** pins: `--help` smoke test + body-exercising test
  that monkeypatches `kb_graph_viz` in `kb.cli` to return a fake diagram
  string and asserts stdout matches verbatim (cycle-27 L2 — body tests
  MUST bypass `--help`).
- **Blast radius:** new `graph_viz` command in `cli.py`; function-local
  imports only (cycle-23 AC4 boot-lean contract); no module-top imports.

### AC3 — `kb verdict-trends` CLI subcommand (`cli.py`)

- Thin wrapper over `kb_verdict_trends(wiki_dir)`. Option: `--wiki-dir PATH`.
- Prints formatted verdict trends to stdout. On error prefix → exit 1.
- **Regression test** pins: `--help` smoke + body-exercising spy test.
- **Blast radius:** same as AC2 shape. No new modules.

### AC4 — `kb detect-drift` CLI subcommand (`cli.py`)

- Thin wrapper over `kb_detect_drift(wiki_dir)`. Option: `--wiki-dir PATH`.
- Prints the drift report (changed + deleted + new sources) to stdout.
  Error prefix → exit 1.
- **Regression test** pins: `--help` smoke + body-exercising spy test.
- **Blast radius:** same shape.

### AC5 — `kb reliability-map` CLI subcommand (`cli.py`)

- Thin wrapper over `kb_reliability_map()` (zero args).
- Prints the trust-score map to stdout. On "No feedback recorded yet"
  (not an Error: prefix, so exit 0 per MCP contract — it's a normal
  empty-state message).
- **Regression test** pins: `--help` smoke + body-exercising spy test.
- **Blast radius:** same shape.

### AC6 — `kb lint-consistency` CLI subcommand (`cli.py`)

- Thin wrapper over `kb_lint_consistency(page_ids)`. Option:
  `--page-ids TEXT` (comma-separated list, default empty string).
- Prints the cross-page consistency report to stdout. Error prefix → exit 1.
- **Regression test** pins: `--help` smoke + body-exercising spy test.
- **Blast radius:** same shape. Note: the MCP tool signature accepts
  `page_ids: str = ""` — we mirror that rather than splitting in CLI
  (keeps the CLI a pure passthrough; the MCP tool already validates).

### AC7 — BACKLOG hygiene

- Delete the cycle-29 `_audit_token` error-string MEDIUM entry (closed
  by AC1).
- Narrow the Phase 4.5 MEDIUM "CLI ↔ MCP parity" entry: update the
  "Remaining gap ≈ 14" prose to reflect the 5 tools shipped this cycle
  (new remaining count = 9; enumerate which ones).
- Skip no-op CVE re-verify per cycle-27 AC7 / cycle-28 AC9 precedent
  (same-day as cycle-29 AC9 2026-04-24 re-stamp; diskcache + ragas
  still no upstream fix — no new `pip-audit` signal possible today).

## Blast radius

- **Src:**
  - `src/kb/compile/compiler.py` (AC1 — `_audit_token` body)
  - `src/kb/cli.py` (AC2-AC6 — 5 new `@cli.command` blocks, function-local imports)
- **Tests:**
  - `tests/test_cycle30_audit_token_cap.py` (AC1 regression)
  - `tests/test_cycle30_cli_parity.py` (AC2-AC6 regressions — `--help`
    smoke + body-exercising spy tests, one class per subcommand)
- **Docs:**
  - `CHANGELOG.md` (Quick Reference entry under `[Unreleased]`)
  - `CHANGELOG-history.md` (per-cycle bullet detail)
  - `CLAUDE.md` (test count, CLI command count, module map update)
  - `README.md` (test badge)
  - `BACKLOG.md` (AC7 — cycle-29 audit-cap delete + parity narrow)

## Verification targets

1. `pytest --collect-only -q | tail -1` → `2826 + N tests collected`, where
   N is the sum of new regression tests (projected: ~12-14 new tests).
2. Full pytest passes.
3. `ruff check src/ tests/` + `ruff format --check src/ tests/` clean.
4. `kb graph-viz --help`, `kb verdict-trends --help`, `kb detect-drift --help`,
   `kb reliability-map --help`, `kb lint-consistency --help` all emit
   help text without traceback.
5. `.venv/Scripts/python -c "from kb.compile.compiler import _audit_token;
   print(len(_audit_token({'cleared': True, 'error': 'X' * 2000})))"` →
   ≤ 600 (cap + marker slack).
6. BACKLOG `git diff` shows the expected deletions only (no unintended
   phase changes).

## Cross-references

- Cycle 27 decision doc: `docs/superpowers/decisions/2026-04-24-cycle27-*.md`
  (CLI parity pattern baseline)
- Cycle 29 decision doc: `docs/superpowers/decisions/2026-04-24-cycle29-*.md`
  (AC1 origin: Step-11 T1 PARTIAL)
- Skill patches: cycle-22 L5 (CONDITIONS mapping), cycle-27 L1 (decorator theft),
  cycle-27 L2 (`--help` tests ≠ body tests), cycle-29 L2 (Path-subclass dispatch
  stripping — irrelevant here, no Path-typed args)

