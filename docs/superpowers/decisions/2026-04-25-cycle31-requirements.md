# Cycle 31 — Requirements + Acceptance Criteria

**Date:** 2026-04-25
**Feature branch:** `feat/backlog-by-file-cycle31`
**Cycle goal:** Continue the CLI ↔ MCP parity sweep — land the **page_id-input cluster** (3 tools: `kb_read_page`, `kb_affected_pages`, `kb_lint_deep`) as thin CLI subcommands following the cycle-27/30 function-local-import wrapper pattern, plus a shared error-discriminator helper that handles heterogeneous MCP error-prefix shapes these specific tools emit. BACKLOG cleanup removes the resolved items from the remaining-12 list.

---

## Problem

The CLI↔MCP parity backlog (Phase 4.5 MEDIUM, `BACKLOG.md:146`) tracks 12 MCP tools still without CLI subcommand wrappers. Cycle 27 shipped 4 read-only wrappers (`search` / `stats` / `list-pages` / `list-sources`); cycle 30 shipped 5 more (`graph-viz` / `verdict-trends` / `detect-drift` / `reliability-map` / `lint-consistency`). The remaining 12 split into three clusters:

- **(a) Write-path (7):** `kb_review_page`, `kb_refine_page`, `kb_query_feedback`, `kb_save_source`, `kb_save_lint_verdict`, `kb_create_page`, `kb_capture` — write-side validation concerns; deferred to a dedicated write-path input-validation cycle.
- **(b) Read-bearing / page_id-input (3):** `kb_read_page`, `kb_affected_pages`, `kb_lint_deep` — all share the `_validate_page_id` discipline at the MCP boundary; read-only in behaviour.
- **(c) Ingest/compile variants (2):** `kb_ingest_content`, `kb_compile_scan` — partially covered by existing `kb ingest` / `kb compile` CLI aliases.

**Cluster (b) is the next clean batch.** All three tools emit string responses that include a distinctive complication vs the cycle-27/30 precedent: they produce **multiple error-prefix shapes**:

| Tool | Error shapes |
|------|-------------|
| `kb_read_page` | `"Error: {err}"` (validator), `"Page not found: {page_id}"` (logical miss), `"Error: Could not read page {id}: {e}"` (OSError) |
| `kb_lint_deep` | `"Error: {err}"` (validator), `"Error checking fidelity for {id}: {e}"` (FileNotFoundError / runtime exception) |
| `kb_affected_pages` | `"Error: {err}"` (validator), `"Error computing affected pages: {e}"` (runtime exception) |

The cycle-27/30 pattern uses `output.startswith("Error:")` as the exit-1 discriminator. Under that literal prefix, runtime-exception paths (`"Error checking fidelity"`, `"Error computing affected pages"`, `"Page not found:"`) would wrongly exit 0 with the error text printed to stdout — a silent false-negative for shell pipelines and CI usage.

## Non-goals

- **NOT refactoring the MCP tool error-prefix shapes.** Production MCP tools emit `"Error: ..."` (validator) and `"Error <verb>ing ...: ..."` (runtime) deliberately. Normalising these across all tools is a separate cross-cycle refactor; this cycle handles heterogeneity at the CLI boundary.
- **NOT adding the remaining write-path (7) or ingest/compile (2) wrappers.** Those clusters have different validation contracts (notes-length cap, verdict-type enum, ingest content-hash dedup) and belong in dedicated cycles.
- **NOT adding `--wiki-dir` overrides to any page_id subcommand.** The underlying MCP tools resolve paths via module-level `WIKI_DIR`, mirroring cycle 27's `list-pages` / `list-sources` decision. A wiki-dir override would require MCP tool signature changes.
- **NOT creating a new module.** The three wrappers belong in `src/kb/cli.py` alongside the existing 19 subcommands.
- **NOT changing `kb_lint_deep` / `kb_affected_pages` / `kb_read_page` MCP tool bodies.** CLI is a pure projection of MCP behaviour.
- **NOT shipping a `kb_capture` CLI wrapper** or any other non-listed tool.

## Acceptance Criteria

**AC1 — `kb read-page <page_id>` subcommand exists.**
- `@cli.command("read-page")` registered at module level in `src/kb/cli.py`.
- Positional argument `page_id` (str, Click `@click.argument("page_id")`).
- Function-local import of `kb.mcp.browse.kb_read_page` (preserves cycle-23 AC4 boot-lean contract).
- Happy path: `kb read-page <existing_id>` prints page body to stdout, exits 0.
- Error paths (below, AC4) propagate to exit 1 with text on stderr.
- Docstring references cycle 31 + the MCP tool as single source of truth (matches cycle 27/30 prose style).
- **Test (pytest):** body-spy test asserts kwargs forward RAW (no CLI-side transformation).

**AC2 — `kb affected-pages <page_id>` subcommand exists.**
- `@cli.command("affected-pages")` registered.
- Positional argument `page_id`.
- Function-local import of `kb.mcp.quality.kb_affected_pages`.
- Happy path: prints affected-pages report to stdout, exits 0.
- Empty-state: `"No pages are affected by changes to X."` prints to stdout and exits 0 (not an error — matches cycle-30 `reliability-map` precedent for empty-state messages).
- Error paths propagate to exit 1.
- **Test:** body-spy test asserts kwargs forward RAW.

**AC3 — `kb lint-deep <page_id>` subcommand exists.**
- `@cli.command("lint-deep")` registered.
- Positional argument `page_id`.
- Function-local import of `kb.mcp.quality.kb_lint_deep`.
- Happy path: prints fidelity-context markdown to stdout, exits 0.
- Error paths propagate to exit 1.
- **Test:** body-spy test asserts kwargs forward RAW.

**AC4 — Shared `_is_mcp_error_response` helper handles heterogeneous error-prefix shapes.**
- New private helper in `src/kb/cli.py` (near the existing `_error_exit`):

  ```python
  def _is_mcp_error_response(output: str) -> bool:
      """Return True if an MCP tool string response represents an error.

      Handles the three error-prefix shapes current MCP tools emit:
      - "Error: ..."      — validator-class errors (_validate_page_id,
                            _validate_wiki_dir, _validate_notes, etc.)
      - "Error <verb>..." — runtime-exception shapes like
                            "Error checking fidelity for X: ...",
                            "Error computing affected pages: ...",
                            "Error reading page X: ..."
      - "Page not found:" — logical-miss shape emitted by kb_read_page
                            after the validator allowed the ID through
                            (check_exists=False) but the file is gone.
      Empty-state messages (e.g. "No pages are affected", "No feedback
      recorded yet", "Showing 0 of 0 pages") are NOT errors — they
      exit 0.
      """
      return output.startswith(("Error:", "Error ", "Page not found:"))
  ```

- Replaces `output.startswith("Error:")` calls in the **three new subcommands only** — existing cycle-27/30 subcommands keep `output.startswith("Error:")` to avoid scope creep (their wrapped MCP tools emit only `"Error:"`-prefixed errors).
- **Test:** unit-test the helper directly with each of the three prefix classes + one non-error string. Assertion shape must be identical across the three error-class cases (cycle-30 L3 parallel-assertion discipline).

**AC5 — Body-execution tests per subcommand (cycle-27 L2 enforcement).**
- `--help` smoke tests do NOT count as body-execution. For each of AC1/AC2/AC3, the test suite must include at least one `CliRunner.invoke(cli, ["<subcmd>", "<arg>"])` with `monkeypatch.setattr(kb.cli, "kb_<tool>", spy)` + `assert spy_called["value"] is True` + `assert spy_called["kwargs"] == {"page_id": "<arg>"}` so argument forwarding regressions fail loudly.

**AC6 — Integration-boundary tests per subcommand (cycle-30 L2 enforcement).**
- For each of AC1/AC2/AC3, include one end-to-end integration test that invokes the real MCP tool (no monkeypatch) with an invalid `page_id` containing `..` (path traversal). The subcommand must exit non-zero and output the validator's `"Error: ..."` line to stderr. This pins the boundary contract and catches any future refactor that loses the `_validate_page_id` call at the MCP tool itself.

**AC7 — BACKLOG cleanup.**
- `BACKLOG.md` line 146 (CLI↔MCP parity entry): remove the bullet point listing `kb_read_page`/`kb_affected_pages`/`kb_lint_deep` from sub-item (b); update the "Remaining gap ≈ 12" count to "≈ 9"; keep the write-path (7) + ingest/compile variants (2) items open with their existing wording.
- CHANGELOG.md `[Unreleased]` Quick Reference: compact entry for cycle 31.
- CHANGELOG-history.md: full per-AC detail block.
- CLAUDE.md: bump Quick Reference CLI-command count from 19 to 22; update `src/kb/` module map CLI list; update test count from 2850 to post-cycle value (use `pytest --collect-only | tail -1` AFTER all R1/R2 fix commits, per cycle-15 L4).
- README.md: no user-facing changes expected; only touch if a CLI command reference table exists.
- Commit count: `+TBD` per cycle-30 L1 (backfill post-merge or accept stale at merge time).

## Blast radius

Primary module touched: `src/kb/cli.py` (one new helper + three new subcommands, ~150 LOC total). No changes to `src/kb/mcp/*.py` tool bodies.

Secondary modules possibly touched for test wiring: `tests/test_cycle31_cli_parity_page_id.py` (new test file, ~250 LOC covering body-spy + boundary + helper-unit tests per AC5/AC6).

Docs: `CHANGELOG.md`, `CHANGELOG-history.md`, `BACKLOG.md`, `CLAUDE.md`.

---

## Symbol verification (cycle-15 L1 gate)

| Symbol | File:line | Exists? |
|--------|-----------|---------|
| `kb_read_page(page_id: str) -> str` | `src/kb/mcp/browse.py:86` | ✅ |
| `kb_affected_pages(page_id: str) -> str` | `src/kb/mcp/quality.py:265` | ✅ |
| `kb_lint_deep(page_id: str) -> str` | `src/kb/mcp/quality.py:130` | ✅ |
| `_validate_page_id(page_id, *, check_exists=True) -> str \| None` | `src/kb/mcp/app.py:250` | ✅ |
| `_error_exit(exc)` (existing CLI error helper) | `src/kb/cli.py` (grep-verified present) | ✅ |
| Cycle 27/30 precedent wrappers (`stats`, `list-pages`, `list-sources`, `graph-viz`, `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency`) | `src/kb/cli.py:622-832` | ✅ |

All 3 target MCP tool signatures are `(page_id: str) -> str` — identical input contract, uniform thin-wrapper shape.

## Prior-art precedent

- **Cycle 27** (`2026-04-24-cycle27-*.md`): 4 read-only wrappers + L1 helper-extraction skill patch + L2 body-execution test requirement + L3 watchdog-failure fallback.
- **Cycle 30** (`2026-04-24-cycle30-*.md`): 5 read-only wrappers + L1 commit-count `+TBD` rule + L2 CLI-wrapper boundary-test requirement + L3 parallel-test assertion-shape discipline.

Cycle 31 applies cycle-27 L2 (body-spy tests) + cycle-30 L2 (integration-boundary tests per known validation range) + cycle-30 L3 (parallel assertion-shape across the three tool variants in AC4's helper-unit tests).
