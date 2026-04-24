# Cycle 30 — Brainstorm

## Approaches considered

### Approach A — Minimum-viable cycle-27 replay (recommended)

Each AC2-AC6 CLI wrapper follows cycle-27's `stats` / `list-pages` /
`list-sources` template verbatim: `@cli.command()` + `@click.option`
decorators, function-local import of the MCP tool, forward raw args,
`if output.startswith("Error:"): sys.exit(1)` handling. AC1 is a 3-line
body change plus one function-local import of `truncate`. AC7 is pure
text edits.

**Pros:**
- Lowest blast radius — every line is a pattern the codebase already
  carries.
- Cycle-27 L2 body-exercising tests are well-understood (spy on
  `kb.cli.<tool_symbol>` via `monkeypatch.setattr`).
- No new code paths; no new security surface beyond what Step-2 threat
  model enumerated.
- Primary-session implementation per cycle-13 sizing (each CLI wrapper
  ~15 LOC; total ~75 LOC across AC2-AC6).

**Cons:**
- Five near-identical blocks of boilerplate grow `cli.py` line count
  by ~150 lines. (Mitigation: the cycle-27 precedent already set the
  naming convention; extraction into a shared helper would cross file
  boundaries and is itself deferred as a future architectural AC.)

### Approach B — Extract `_forward_mcp_output` helper

Build a single helper `_forward_mcp_output(output: str) -> None` that
checks `"Error:"` prefix + exits or prints. Each new CLI wrapper becomes
3-4 lines instead of 8.

**Pros:** DRYer. ~50% line-count reduction in the `cli.py` additions.
**Cons:** Cross-cycle refactor — would want to migrate cycle-27's
existing `stats` / `list-pages` / `list-sources` to the helper too,
expanding the blast radius. Current cycle-27 variants have subtle
differences (one echoes on stdout, another uses `click.echo(err=True)`).
Extraction without migrating existing callers creates a code-style split.
**Decision:** REJECT this cycle. File as future refactor BACKLOG entry.

### Approach C — Defer AC6 (`lint-consistency`)

`kb_lint_consistency` takes a `page_ids: str = ""` arg that shapes the
report. Skipping this AC keeps cycle 30 purely zero-arg / single-flag
and ships one less test file.

**Pros:** Smaller cycle scope. Less input-validation surface.
**Cons:** The MCP tool already validates `page_ids` (cycle-20 audit).
The CLI wrapper adds zero new surface beyond what MCP already guarantees.
Shipping it keeps the cycle 30 scope evenly distributed (5 CLI AC),
matches cycle-27's 4-AC pacing, and closes one more item on the CLI↔MCP
parity backlog. **Decision:** KEEP AC6 in scope.

### Approach D — Add `kb_read_page` / `kb_affected_pages` wrappers

These are the two other MCP read-only tools without CLI surface. Both
take `page_id` args that require validation.

**Pros:** Higher item-count for the cycle.
**Cons:** Both invoke validators (`_validate_page_id`) that surface
edge cases (Windows reserved names, 255-char cap, ambiguous case-
insensitive matches on `kb_read_page`; cascading backlink computation
on `kb_affected_pages`). Each would be an independent design task —
worth its own cycle. **Decision:** DEFER to a page-id-input-centric cycle.

## Recommended approach

**Approach A.** Ship AC1 + AC2-AC6 via cycle-27 cookie-cutter replay.
AC7 is a pure delete/narrow pass over BACKLOG.md.

## Open questions

1. **Q1 — Truncate limit value.** The BACKLOG text suggests `limit=500`.
   `kb.utils.text.truncate`'s default is `600`. 500 for rebuild_indexes
   audit matches the BACKLOG suggestion and keeps the total `msg` line
   bounded when both manifest and vector tokens trip the cap (2×540 +
   static ~70 = ~1150 chars — still small). Confirm 500 is the AC1
   choice.
2. **Q2 — Where does `_truncate_text` live in AC1?** Current import at
   `cli.py:31` is `from kb.utils.text import truncate as _truncate_text`.
   `compile/compiler.py` doesn't yet import `truncate` — add a
   function-local import inside `_audit_token` (cycle-23 AC4 boot-lean
   preserved, though `compile/compiler.py` is not an MCP boot path —
   it's only loaded when `kb compile` / `kb rebuild-indexes` fire).
   Module-level import might be fine; function-local is the safe default
   mirroring cycle-27.
3. **Q3 — Test for AC1.** Pin behavior via `_audit_token` unit test
   (input block with 2000-char `error` → output ≤ 600 chars, head
   preserves `"tmp:"` prefix) AND end-to-end via `rebuild_indexes`
   monkeypatching `Path.unlink` to raise an `OSError("X" * 2000)` —
   assert `wiki/log.md` line length bounded. Two tests, separate
   concerns.
4. **Q4 — AC6 MCP tool `page_ids` validation.** Confirm whether
   `kb_lint_consistency` splits on `","` before validating. Checked
   during threat model (T3) — it does. CLI can pass the raw string
   through without splitting.
5. **Q5 — AC1 cap applies symmetrically or only to the `cleared
   (warn: ...)` branch?** The non-`cleared` branch also writes the
   error verbatim (`str(block["error"])`). Apply cap to both branches
   to avoid path asymmetry.
6. **Q6 — Commit count convention.** Per cycle-26 L1 / cycle-28 AC8,
   the self-referential doc-update commit counts itself. Plan for
   5-6 commits: (a) AC1, (b) AC2-AC3 (CLI parity health), (c) AC4-AC5
   (CLI parity health), (d) AC6 (CLI parity quality), (e) AC7 BACKLOG,
   (f) Step-12 doc update. Adjust per TDD grouping at Step 9.
7. **Q7 — Batch-by-file interpretation.** `cli.py` gets 5 AC in one
   file; `compile/compiler.py` gets 1 AC; `BACKLOG.md` gets the delete.
   Should each AC be a separate commit or grouped by file?
   **Proposal:** group AC2-AC3 as one commit (same file, small
   diff); group AC4-AC5 similarly; AC6 separately; AC1 + test
   separately; AC7 + doc separately. Step 5 decides.
8. **Q8 — CLI test-file split.** One file for all 5 CLI ACs
   (`test_cycle30_cli_parity.py`) vs. one per AC. **Proposal:** one
   file with one `TestXXX` class per subcommand (cycle-27 precedent).

## Artifacts ready to pass to Step 4 (design eval)

- Requirements: `docs/superpowers/decisions/2026-04-24-cycle30-requirements.md`
- Threat model: `docs/superpowers/decisions/2026-04-24-cycle30-threat-model.md`
- Baseline CVE snapshots: `.data/cycle-30/cve-baseline.json`,
  `.data/cycle-30/alerts-baseline.json`
- 8 open questions above for Step 5 to resolve.
