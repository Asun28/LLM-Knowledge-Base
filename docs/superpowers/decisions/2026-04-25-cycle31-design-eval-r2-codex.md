# Cycle 31 Design Evaluation - R2 Codex

Grounding read: the three Cycle 31 artifacts, `src/kb/cli.py:568-832`, `src/kb/mcp/browse.py`, `src/kb/mcp/quality.py`, `src/kb/mcp/health.py`, and `src/kb/mcp/app.py`. `src/kb/mcp/core/validators.py` is absent; `_validate_page_id` is in `src/kb/mcp/app.py:250`.

## 1. Discriminator Edge Cases

Severity: LOW. Affected path: planned `_is_mcp_error_response` near `src/kb/cli.py:60`; target wrappers planned near `cli.py:832+`.

`"".split("\n", 1)[0]` and `"\n".split("\n", 1)[0]` both produce `""`, so `startswith(("Error:", "Error ", "Page not found:"))` is false and exits 0. This is acceptable only if documented: `kb_read_page` can legitimately return an empty/blank-leading page body (`browse.py:161`). Treating blank output as suspect would create false failures for empty pages. Multi-line errors are safe with first-line-only matching because all current target error strings begin with the error prefix: `browse.py:94,125,139`; `quality.py:142,149,152,281,290`. CRLF is safe: `"Error:\r\ntext".split("\n", 1)[0] == "Error:\r"`, and it still starts with `"Error:"`.

Mitigation / AC amendment: AC4 should explicitly state empty output and blank first line are non-errors by design, with helper tests for `""`, `"\nbody"`, `"Error:\r\ndetails"`, and `"ok\nError: not first line"`.

## 2. Boundary Test Pathologies

Severity: MEDIUM. Affected paths: `_CTRL_CHARS_RE` at `app.py:188`, `_validate_page_id` at `app.py:250-289`, `_strip_control_chars` at `quality.py:31-33`, target tools at `browse.py:92`, `quality.py:139-142`, `quality.py:275-281`.

`_CTRL_CHARS_RE = r"[\x00-\x1f\x7f]"` includes newline, carriage return, and tab, so direct `_validate_page_id("concepts/rag\n")` rejects. But `kb_lint_deep` and `kb_affected_pages` strip ASCII controls before validation (`quality.py:139`, `quality.py:275`), so those tools normalize newline/tab away instead of rejecting. `kb_read_page` does not strip first (`browse.py:92`) and will reject. Bidi override and zero-width joiner are not in `_CTRL_CHARS_RE`; `_NOTES_UNSAFE_RE` covers bidi for notes (`app.py:189`) but page IDs can carry U+202E/U+200D until existence/path checks fail or a matching file exists.

CliRunner can pass strings that are awkward in a real shell, including embedded newline args, and it merges stderr unless configured. It also does not test the installed console entry point or Windows argv quoting.

Mitigation / AC amendment: add a tool-specific control-character matrix documenting current parity: read-page rejects newline/tab; lint-deep and affected-pages strip them. Add one real subprocess smoke for an invalid traversal or boot-lean probe; keep CliRunner for fast body-spy tests.

## 3. Parity Test Correctness

Severity: HIGH. Affected path: threat model T7 `docs/...threat-model.md:463-468`; planned `tests/test_cycle31_cli_parity.py`.

Raw byte identity between MCP return and CLI output is the wrong metric. CLI success uses `click.echo(output)`, adding a newline to stdout. CLI errors use stderr plus `sys.exit(1)`, while MCP returns the raw string in-band. Therefore a naive byte-identity assertion will either fail correctly implemented wrappers or ignore channel/exit semantics.

Mitigation / AC amendment: compare payload identity plus channel semantics: success `stdout == mcp_output + "\n"` and exit 0; error `stderr == mcp_output + "\n"` (or merged `output` if Click version lacks split streams) and exit non-zero. Phrase T7 as "exact payload preservation after Click's trailing newline and stderr routing."

## 4. Parallel Assertion Shape

Severity: HIGH. Affected paths: AC5 `requirements.md:92`; brainstorm Q7 `brainstorm.md:136-137`; existing precedent `tests/test_cycle30_cli_parity.py:48-58`.

AC5 says `monkeypatch.setattr(kb.cli, "kb_<tool>", spy)`, but the wrappers are planned to use function-local imports. Existing Cycle 30 tests correctly patch the source module (`kb.mcp.health` / `kb.mcp.quality`) because the import resolves at call time (`tests/test_cycle30_cli_parity.py:48-58,277-287`). Patching `kb.cli` will not intercept the planned imports.

The 12 wrapper tests are also asymmetric unless each subcommand has the same four test roles. `affected-pages` needs one extra empty-state assertion (`quality.py:317`), and `read-page` has a unique `Page not found:` branch (`browse.py:125`); these should be additions, not replacements. Boundary tests using only `..` hit only `"Error:"` and would miss a wrapper that forgot `_is_mcp_error_response`.

Mitigation / AC amendment: patch `kb.mcp.browse` or `kb.mcp.quality`, assert `kwargs == {"page_id": raw}` identically for all three, and add one wrapper-level non-colon error test per command: `Page not found:`, `Error computing affected pages:`, and `Error checking fidelity for`.

## 5. Cross-Cycle Helper Retrofit Risk

Severity: HIGH. Affected paths: legacy wrappers at `cli.py:584-827`; MCP emitters below.

The "legacy tools emit only `Error:`" premise is false. Inventory:

- `search` -> MCP counterpart `kb_search`; CLI uses `search_pages` + `_format_search_results` (`cli.py:584-617`); `kb_search` emits colon-only errors (`browse.py:67,71,82`).
- `stats` -> `kb_stats` (`cli.py:630-645`); emits `Error: {err}` and non-colon `Error computing wiki stats:` (`browse.py:341,348`).
- `list-pages` -> `kb_list_pages`; colon-only (`browse.py:187,194,220`).
- `list-sources` -> `kb_list_sources`; colon-only (`browse.py:245,329`).
- `graph-viz` -> `kb_graph_viz`; colon-only (`health.py:191-208`).
- `verdict-trends` -> `kb_verdict_trends`; colon-only (`health.py:225,232`).
- `detect-drift` -> `kb_detect_drift`; colon-only (`health.py:251,255`).
- `reliability-map` -> `kb_reliability_map`; non-colon `Error computing reliability map:` (`quality.py:245`).
- `lint-consistency` -> `kb_lint_consistency`; non-colon `Error running consistency check:` (`quality.py:184`).

Mitigation / AC amendment: do not claim all legacy wrappers are colon-only. Either create a follow-up bug for the three existing false-negative paths, or deliberately include them in this cycle with wrapper-specific tests. If not included, T8 should say "no retrofit for scope control, despite known non-colon legacy emitters."

## 6. Boot-Lean Contract

Severity: MEDIUM. Affected paths: `cli.py:15-31`, planned wrappers at `cli.py:832+`.

Current `cli.py` has no module-level `kb.mcp.browse` or `kb.mcp.quality` import in lines 1-31, and existing wrappers use function-local imports with `# noqa: PLC0415` (`cli.py:636,665,686,795,823`). The Cycle 31 docs plan the same for all three new imports.

Mitigation / AC amendment: Step 11 should AST-scan the whole file for module-level `kb.mcp.browse` / `kb.mcp.quality` imports, not only lines 1-32. Require the three new import lines to include `# noqa: PLC0415`.

## 7. Step-11 Checklist Gaps

Severity: MEDIUM. Affected path: threat model Section 7.

Gaps: T7's byte-identity check is incorrect; T8's exact-eight `startswith("Error:")` check ignores the ninth wrapper (`search`) and the false legacy emitter premise; T3 does not require empty/blank/CRLF helper tests; AC6 traversal-only boundary tests do not exercise non-colon error routing; T4 does not detect quality-tool control stripping; T6's "subprocess then inspect `sys.modules` afterwards" needs a Python subprocess that performs the inspection before exit.

Mitigation / AC amendment: update Step 11 to include the added helper edge cases, wrapper-level non-colon error tests, source-module monkeypatching, and an AST-based boot-lean check.

## 8. AC Scope Completeness

Severity: MEDIUM. Affected path: AC7 and backlog `BACKLOG.md:146`.

Updating remaining "~12" to "~9" is arithmetically correct after removing three tools: write-path seven plus ingest/compile two remain. However, `kb_review_page` is grouped under "write-path" even though the implementation is read-only and page_id-based (`quality.py:37-59`); its error shape is also non-colon (`quality.py:56,59`). Bulk input for `lint-deep` has no MCP signature equivalent, so it should remain out of scope. Structured `--format=json` is already deferred in `BACKLOG.md:146` and brainstorm Q10.

Mitigation / AC amendment: clean BACKLOG wording to "write/review workflow tools (7)" or split `kb_review_page` into a future page_id/read-quality wrapper item so the remaining state is not misleading.

## Verdict

AMEND. Approach A is the right implementation shape, but AC5, T7, T8, and Step-11 need correction before this is safe to hand to implementation.
