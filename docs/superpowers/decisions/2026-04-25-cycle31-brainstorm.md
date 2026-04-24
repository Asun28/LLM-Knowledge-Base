# Cycle 31 — Brainstorming

**Date:** 2026-04-25
**Inputs:** Requirements (`2026-04-25-cycle31-requirements.md`) + threat model (`2026-04-25-cycle31-threat-model.md`).

Per the user's auto-approve memory (`feedback_auto_approve.md`), this cycle runs autonomously — the brainstorming skill's user-gate ritual is skipped in favour of the feature-dev skill's autonomous Step 5 decision gate (Opus subagent resolves remaining questions).

## The problem in one line

Wrap three page_id-input MCP tools (`kb_read_page`, `kb_affected_pages`, `kb_lint_deep`) as CLI subcommands, with a shared discriminator helper that correctly classifies the three distinct error-prefix shapes these tools emit (`"Error:"`, `"Error <verb>"`, `"Page not found:"`).

## Approach A — Minimum-viable cycle-27/30 replay with additive shared helper (RECOMMENDED)

**Shape.** Three new `@cli.command` subcommands in `src/kb/cli.py` following the cycle 27/30 thin-wrapper template to the byte. Each subcommand:
1. Takes a single positional `@click.argument("page_id")`.
2. Imports the MCP tool via function-local `from kb.mcp.<module> import kb_<tool>  # noqa: PLC0415`.
3. Calls the tool with `page_id=page_id` (kwarg — matches cycle-30 spy-pattern).
4. Branches on `_is_mcp_error_response(output)`:
   - True → `click.echo(output, err=True); sys.exit(1)`.
   - False → `click.echo(output)`.
5. Wrapped in a `try/except Exception → _error_exit(exc)` catching the rare case where the MCP tool raises instead of returning an error string.

**New helper.** One new function near `_error_exit`:

```python
def _is_mcp_error_response(output: str) -> bool:
    """Return True if an MCP tool string response represents an error.

    Classifies by first-line prefix (split on '\\n') to avoid misfiring
    on page bodies whose second line happens to contain 'Error: ...'.
    Three shapes currently emitted by the cycle-31 target tools:
      - "Error:"           validator-class (kb_mcp app._validate_page_id)
      - "Error "           runtime-exception shapes like
                             "Error checking fidelity for X: ...",
                             "Error computing affected pages: ...",
                             "Error reading page X: ..."
      - "Page not found:"  logical-miss shape unique to kb_read_page
                             (src/kb/mcp/browse.py:125).

    Tagged-error form "Error[<category>]: ..." from src/kb/mcp/app.py:17
    is NOT matched — the three cycle-31 target tools do not emit it.
    (T9 — future refactor adopting `error_tag()` in these tools must
    widen the prefix set.)

    Empty-state messages (e.g. "No pages are affected", "No feedback
    recorded yet", "Showing 0 of N page(s)") are NOT errors — exit 0.

    Existing cycle 27/30 wrappers (search / stats / list-pages /
    list-sources / graph-viz / verdict-trends / detect-drift /
    reliability-map / lint-consistency) MUST keep their literal
    `output.startswith("Error:")` check — the MCP tools they wrap
    emit ONLY the colon form. Retrofitting this helper into those
    wrappers is explicit out-of-scope (T8 peer-drift).
    """
    first_line = output.split("\n", 1)[0]
    return first_line.startswith(("Error:", "Error ", "Page not found:"))
```

**Pros.**
- Zero changes to existing cycle 27/30 wrappers (T8 peer-drift mitigated).
- Single place to unit-test the three-prefix logic.
- Matches the cycle 27/30 template exactly → reviewer cognitive load is minimal.
- Forward-compatible: a future cycle migrating existing wrappers can swap `output.startswith("Error:")` → `_is_mcp_error_response(output)` for a deliberate convergence step.

**Cons.**
- Introduces one new symbol to the CLI namespace. Mitigation: leading underscore + scoped docstring.
- Future new MCP tools with a 4th error prefix shape would need to update this helper (expected — it's the single source of truth).

## Approach B — Copy-paste inline per-subcommand discriminator (no shared helper)

**Shape.** Three new subcommands, each with its own inline `output.split("\n", 1)[0].startswith(("Error:", "Error ", "Page not found:"))` expression. No shared helper.

**Pros.**
- Maximally minimal new surface — zero new private helpers.
- Absolutely no same-class peer-drift risk (T8) because there's no helper to retrofit.

**Cons.**
- Copy-paste drift: three places to update if a 4th error shape emerges.
- Harder to unit-test in isolation (requires invoking a subcommand end-to-end).
- Violates DRY for the second time in the same cycle — cycle-24 L1 (`Edit(replace_all=true)` silent-miss risk) is the family precedent for "three copy-paste sites get out of sync".
- Each subcommand grows to ~25 LOC vs ~15 LOC — noisier per-subcommand diff at review time.

**Verdict: rejected.** The maintenance cost of copy-paste drift across three sites outweighs the ~5 LOC savings. Approach A's helper is explicitly additive (T8 verified).

## Approach C — Generalise to `_mcp_passthrough(tool_callable, **kwargs)` helper

**Shape.** One new helper that wraps the full invoke-discriminate-echo-exit cycle. All three new subcommands become 3-line wrappers. Opportunistically retrofit existing cycle 27/30 wrappers (9 of them) to use the same helper for maximum DRY.

**Pros.**
- Peak DRY: shared `_mcp_passthrough` is the only call in every wrapper.
- Future subcommand additions become trivial.

**Cons.**
- **Fails T8 (same-class peer drift).** Retrofitting 9 existing cycle 27/30 wrappers requires behavioural-regression testing for each of them; Opus threat-model explicitly flags this as the single biggest footgun.
- Scope explosion: 9 wrappers × ~3 min per retrofit = half-day of work with no new user-facing capability.
- Higher review burden: reviewers must read all 9 retrofits to confirm no behaviour drift.
- Shared helper must handle BOTH the cycle 27/30 `startswith("Error:")` discriminator AND the cycle-31 three-prefix discriminator via an optional arg — adds parameterisation complexity.
- Cycle-24 L1 warns about `Edit(replace_all=true)` silent-miss on multi-line patterns — retrofitting 9 multi-line wrapper bodies risks that exact failure mode.

**Verdict: rejected.** Fails T8 by construction; scope explosion; no user-facing benefit.

## Recommended approach: A

**Rationale:**
1. **Mitigates T8 by construction** — helper is additive; cycle 27/30 wrappers untouched. Step-11 grep at `src/kb/cli.py:640,669,690,724,751,779,799,827` returns exactly 8 unchanged `startswith("Error:")` lines.
2. **Clean unit-testability** — the helper is a pure string-prefix matcher; cycle-30 L3 parallel-assertion discipline applies to its positive/negative test matrix.
3. **Matches cycle-27/30 template** — single-file diff, single test file, ~150 LOC primary + ~250 LOC test.
4. **Cycle-13 L2 sizing heuristic fits** — 3 wrappers × ~15 LOC each + helper ~12 LOC = 57 LOC code, sub-30 LOC per task; tests ~250 LOC. Primary-session implementation per heuristic.
5. **Forward-compatible** — if a future cycle deliberately widens existing wrappers' error-discriminator (e.g., to handle `"Error "` space form from a new MCP tool), the helper is pre-built and the migration is a targeted swap.

## Open questions (for Step 5 design decision gate)

**Q1.** Should `_is_mcp_error_response` accept arbitrary iterable / tuple of prefixes (generalised) or hard-code the three shapes (specialised)?
- Option A: `def _is_mcp_error_response(output, prefixes=("Error:", "Error ", "Page not found:"))`
- Option B: `def _is_mcp_error_response(output)` with hardcoded tuple inside.
- Bias: lower blast radius wins → **Option B (specialised)**. Changing prefix set is a deliberate cycle-level decision, not a caller's configuration knob.

**Q2.** Subcommand naming: kebab-case `read-page` vs. underscore `read_page` vs. action-first `page-read`?
- Cycle 27/30 precedent: kebab-case with noun-action or action-only (`list-pages`, `list-sources`, `detect-drift`, `reliability-map`, `lint-consistency`). Bias: match precedent.
- Decision: **`read-page`, `affected-pages`, `lint-deep`** — matches existing verbal mood and cycle 27/30 hyphenation.

**Q3.** Error-branch: `click.echo(output, err=True); sys.exit(1)` or `_error_exit(Exception(output))`?
- T2 verification explicitly requires `click.echo(output, err=True)` (sanitised MCP output already). `_error_exit` route would double-sanitise via `_truncate(str(exc))` and possibly truncate error text. Decision: **`click.echo(output, err=True); sys.exit(1)`** — mirrors cycle 27/30 pattern lines 640-645, 667-674, etc.

**Q4.** Should the CLI wrapper additionally validate `page_id` for emptiness before calling the MCP tool (defence-in-depth)?
- Option A: CLI pre-validates, rejects empty or control-char.
- Option B: CLI forwards raw; MCP tool's `_validate_page_id` is the single checkpoint.
- T7 verification requires verbatim forwarding — defence-in-depth would be divergence. Decision: **Option B (MCP-only)**.

**Q5.** Helper location: top of `src/kb/cli.py` near `_error_exit`, or at the BOTTOM near the `if __name__ == "__main__"` guard?
- Cycle-27/30 helpers (`_error_exit`, `_truncate`, `_is_debug_mode`, `_setup_logging`) cluster at the top before the `@click.group()`. Decision: **near `_error_exit` at ~line 72** for discoverability.

**Q6.** Test file naming: `test_cycle31_cli_parity.py` (matches cycle 27/30) or `test_cycle31_cli_page_id_wrappers.py` (topical)?
- Cycle 27/30 used `test_cycle27_cli_parity.py` and `test_cycle30_cli_parity.py`. Decision: **`test_cycle31_cli_parity.py`** — match precedent. If a future sibling parity-cycle (cluster a or c) ships in parallel, the test file split by cycle ID keeps ownership clear.

**Q7.** Test coverage matrix — should each of the three subcommands include the full matrix (help + body-spy + integration-boundary + parity byte-identity) or just the cycle-27 L2 + cycle-30 L2 subset?
- Threat model T7 requires a parity test (byte-identity between CLI and MCP). Decision: **full matrix.** Full matrix per subcommand = help + body-spy + integration-boundary-rejection + CLI/MCP-parity = 4 tests × 3 subcommands = 12 wrapper tests. Plus helper unit tests: 3 positive (one per prefix shape) + 2 negative (plain body, substring-only "Error" mid-line) + 1 first-line-split test = 6 helper tests. Total: 18 tests minimum. Parallel-assertion shape across the 3 subcommand tests (cycle-30 L3).

**Q8.** Should `kb lint-deep` also support the `--force` / `--yes` / `--verbose` override Click options, or stay zero-option?
- `kb_lint_deep(page_id)` takes only `page_id`. Adding CLI-level options without an MCP equivalent would be divergence. Decision: **zero options beyond positional page_id.** Matches cycle-30 `reliability-map` (zero opts) and `lint-consistency` (one opt that maps directly to MCP kwarg).

**Q9.** Should we also bundle a BACKLOG re-verification of the CVE line items (diskcache / ragas, both no-upstream-fix) into this cycle, or leave as-is?
- Both were re-verified in cycle-25 AC9 and cycle-30 baseline. Bias: do NOT add scope. Decision: **leave as-is.** Step-2 baseline already shows the same 2 open no-fix vulns; Step-12 doc-update touches BACKLOG only for the cycle-31 resolution of the 3-tool parity sub-item.

**Q10.** Should the cycle add a `--force` / `--verbose` / `--output` structured-format flag to the three subcommands? (MCP parity gap — MCP tools return raw strings; CLI has no JSON-output surface yet.)
- Phase 4.5 MEDIUM BACKLOG entry says "Structured `--format=json` output across both surfaces still open." Decision: **NO — deferred to a dedicated cross-surface JSON cycle.** Mixing this into the parity-only cycle would expand scope.

All ten questions have recommended resolutions above. The Step 5 decision gate will either confirm these or surface divergences.
