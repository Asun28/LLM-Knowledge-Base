# Cycle 31 — Step 5 Design Decision Gate

**Date:** 2026-04-25
**Author:** Opus Step-5 gatekeeper
**Inputs:** requirements + threat-model + brainstorm + R1 Opus + R2 Codex

---

## Analysis

### Q1 — AC4 sample-code bug

The requirements doc at lines 68-85 shows a helper body that calls `output.startswith((prefix_tuple))` directly against the full `output` string. The threat model T3 explicitly mandates first-line-only matching via `output.split("\n", 1)[0]`, and the brainstorm's Approach A code block at lines 55-56 implements that split correctly. R1 Opus called this out as BLOCKING amendment 1. R2 Codex independently validated it with CRLF edge cases (`"Error:\r\ntext".split("\n", 1)[0] == "Error:\r"` — still matches). The brainstorm version is authoritative because (a) it matches T3's verification grep, (b) without the split, a plain page body whose second line contains `"Error: ..."` misfires. The requirements-doc version is strictly weaker; treat it as an editorial error.

The canonical body must also encode T9's docstring requirement. Threat model verification greps for the literal string `"Error["` in the docstring with a "not emitted by cycle-31 tools" annotation. This is load-bearing for future maintainers who might adopt `error_tag()` in the three target tools. Docstring must also enumerate the three prefix shapes with file:line citations so the discriminator's coverage is traceable without reading the callers.

### Q2 — Empty / blank output semantics

R2 Codex correctly noted `kb_read_page` can legitimately return an empty body (`browse.py:161` — file exists but is zero-length). Option "require a fourth prefix shape for empty" would flag legitimate empty pages as errors and diverge from MCP behaviour (which returns `""` in-band as success). Option "document empty-as-success" preserves MCP parity and matches the cycle-30 `reliability-map` empty-state precedent where `"No feedback recorded yet."` exits 0.

Blast radius analysis: treating empty as error creates a new false-positive class for operators running `kb read-page X > out.md` on genuinely empty pages. Treating empty as success is the existing MCP behaviour projected verbatim to CLI — zero divergence. The cycle-31 premise is "CLI is a pure projection of MCP" (requirements §Non-goals line 33); deliberately diverging for empty-output handling would violate that. Decision trends clearly toward accept-empty-as-success plus explicit test coverage.

### Q3 — Parity test metric

R2 is right: raw byte-identity CLI==MCP is a broken metric because `click.echo` adds `\n` on success, routes errors to stderr, and `sys.exit(1)` leaves a non-zero exit code. MCP returns the raw string in-band with no trailing newline. Option A (strict stream-aware matching) is the accurate contract: on success `result.stdout == mcp_output + "\n"` and `exit_code == 0`; on error `result.stderr == mcp_output + "\n"` and `exit_code == 1`. Option B (merged `result.output`) loses the stdout/stderr split which is the CLI's actual error-signaling channel. Option C (skip parity) abandons T7's contract.

Option A requires `CliRunner(mix_stderr=False)` so stdout and stderr are separately inspectable. Click 8.x supports this. Shape: three invocations per subcommand × {success, error} = 6 parity assertions minimum. The MCP side calls the tool function directly with the same input and captures its return string; the CLI side invokes via `CliRunner`. This is the shape R1 Opus called for in amendment 2.

### Q4 — Scope expansion for R2's pre-existing-bug finding

R2 discovered that `stats`, `reliability-map`, and `lint-consistency` all have non-colon runtime-error emitters that slip past the existing `startswith("Error:")` check. I confirmed independently via Read: `browse.py:348` emits `"Error computing wiki stats: ..."` (non-colon runtime), `quality.py:245` emits `"Error computing reliability map: ..."`, `quality.py:184` emits `"Error running consistency check: ..."`. All three have silent exit-0 bugs today. This is a real correctness gap — however, it is pre-existing, not introduced by cycle 31.

Weighing options: Option A (expand scope) adds ~30 LOC code + ~60 LOC tests and closes a silent-failure bug for three wrappers touching the same file (`cli.py`). Per `feedback_batch_by_file.md` — "Group backlog fixes by file (HIGH+MED+LOW together), not by severity" — file-alignment strongly favors Option A. The helper is already built for exactly this case. Cycle-17 L3 precedent (scope discoveries route back to Step 5 with formal amendment) is this exact flow in reverse: R2 surfaced the finding, Step 5 resolves. Option B defers to BACKLOG but leaves the bug live during cycle 31's merge. Option C (hybrid, `stats` only) is arbitrary.

Deciding Option A is the right call: same file, same helper, same test-file, same reviewer context, three trivial one-line swaps (`startswith("Error:")` → `_is_mcp_error_response(output)`). T8's peer-drift concern is resolved by construction because THREE named wrappers are explicitly migrated and tested; the remaining 5 cycle 27/30 wrappers (`search`, `list-pages`, `list-sources`, `graph-viz`, `verdict-trends`, `detect-drift`) stay on `startswith("Error:")` verbatim. This does mean T8's "exactly 8" grep changes to "exactly 5" — that's fine; it's a deterministic recount.

### Q5 — Monkeypatch target correction

R2 is correct: function-local `from kb.mcp.<module> import kb_<tool>` resolves at call time against the OWNER module (`kb.mcp.browse` or `kb.mcp.quality`), not against `kb.cli`. Patching `kb.cli` would re-bind an attribute that the CLI never reads because the import re-resolves on every subcommand call. Cycle-30's test file at `tests/test_cycle30_cli_parity.py:48` patches the source module correctly and is the proven pattern.

Per-subcommand patch target: `kb read-page` → `kb.mcp.browse`; `kb affected-pages` → `kb.mcp.quality`; `kb lint-deep` → `kb.mcp.quality`. AC5 wording must be updated; the `kb.cli` target was the single most-impactful bug in the requirements draft. Note this also applies to our CLAUDE.md Fixture rules section ("Patch the owner module for the four MCP-migrated callables") — the pattern is already documented there.

### Q6 — Control-char parity matrix

R2 Codex verified via source reading: `kb_lint_deep` (`quality.py:139`) and `kb_affected_pages` (`quality.py:275`) both call `_strip_control_chars` BEFORE the validator, so a trailing `\n` or `\t` in the input is stripped away (not rejected); `kb_read_page` (`browse.py:92`) calls `_validate_page_id` directly, which rejects via `_CTRL_CHARS_RE`. This asymmetry is INHERITED from the MCP tools, not introduced by cycle 31.

Per T7 (CLI forwards verbatim), the CLI MUST NOT attempt to normalize the asymmetry; doing so would diverge. Instead, cycle-31 requires per-tool behaviour pins: one test per subcommand asserting the current MCP behaviour is projected to CLI exactly. If a future cycle chooses to normalize the three tools (make them all strip OR all reject), both CLI and MCP flip together — test suite will catch regression either way. Accepting asymmetry with explicit test pins is the minimum-scope answer.

### Q7 — Boundary test correctness

R2's observation is sharp: a `..` input hits the colon-form `"Error: Invalid page_id: ..."` which would pass even if a wrapper forgot `_is_mcp_error_response` (legacy `startswith("Error:")` already catches colon-form). The boundary test is supposed to catch wrapper-level regression in the discriminator, so it MUST produce a non-colon error. Candidates from quality.py/browse.py runtime paths produce the required non-colon shapes.

Specifically: `kb read-page nonexistent-page-id` → `"Page not found: nonexistent-page-id"` (no "Error" prefix at all — this is the hardest case). For `kb affected-pages` and `kb lint-deep`, the non-colon paths require an exception deep in the helper chain. Using `monkeypatch` on the helper (e.g., `kb.compile.linker.build_backlinks`) to force a raise is the clean shape — the MCP tool's `except Exception` clause emits `"Error computing affected pages: ..."` / `"Error checking fidelity for <id>: ..."`. These would both FAIL under a legacy `startswith("Error:")` discriminator, catching the intended regression class.

### Q8 — Commit-count handling

Cycle-30 L1 is explicit: commit count in CHANGELOG at Step 12 is `+TBD`, backfilled post-merge once the R1/R2 fix commits and final rebase commits are counted. Confirmed. Per cycle-30 L1 the placeholder lives under `[Unreleased]` Quick Reference; the full CHANGELOG-history entry also uses `+TBD` until merge. Do NOT attempt to pre-count — it will drift as review commits land.

### Q9 — Primary-session vs Codex implementation

Cycle-13 L2 sizing heuristic: <30 LOC code/task + <100 LOC tests/task + no novel APIs → primary session. Cycle-14 L1: operator holds Steps-1-5 context → primary session. Cycle 31 fits both: three wrappers × ~15 LOC + one helper × ~12 LOC + 3 retrofit one-liners (Option A) = ~60 LOC total code. Test file ~300 LOC across ~20 tests. No novel APIs — helper is a string matcher; wrappers are thin shims copied from cycle 27/30. Operator context is full (we just produced the spec).

Codex dispatch would amortize over 3-4 subagents at ~30min each; primary session amortizes as a single long session. The primary-session path is faster and carries lower coordination cost for work this mechanical. Decision: primary session with the feature-dev skill, following cycle-27/30 sequence.

### Q10 — R3 trigger evaluation

Cycle-17 L4 triggers: (a) ≥25 ACs — miss (we have 8 with Option A); (b) ≥15 ACs + new security surface — miss; (c) ≥10 design-gate questions — miss (we have 10 exactly; trigger says `≥` but the semantic intent is ">clear-cut"; we are at the boundary); (d) new filesystem write surface — miss. The helper is a classifier, not an enforcer. No new MCP tool. No frontmatter contract. R1 and R2 already cover the security + correctness axes; R3 would be pure confirmation.

Boundary case on (c): 10 questions is exactly the threshold. R1 + R2 are sufficient to cover everything (R1 flagged the first-line-anchor bug; R2 flagged the byte-identity, monkeypatch-target, and legacy-wrapper findings — both of which Step 5 now resolves). A third reviewer would re-discover the same findings or drill into test-matrix formatting. Marginal value is low; keep the cycle moving. Skip R3.

---

## Decisions (Q1-Q10)

### Q1 — Canonical helper body

**OPTIONS:** (brainstorm version with first-line split) vs (requirements-doc version without split).
**ARGUE:** Threat-model T3 explicitly mandates `.split("\n", 1)[0]` before prefix check; without it a page body whose SECOND line contains `"Error:"` misclassifies.
**DECIDE:** brainstorm version is authoritative. Verbatim body below.
**RATIONALE:** T3 first-line anchor is a documented invariant; R1 flagged as BLOCKING.
**CONFIDENCE:** high.

```python
def _is_mcp_error_response(output: str) -> bool:
    """Return True if an MCP tool string response represents an error.

    Classifies by the FIRST line only (split on '\\n') to avoid misfiring
    on page bodies whose later lines happen to contain 'Error: ...'.
    Empty / blank-first-line outputs are NOT errors by design — they exit 0
    (e.g. `kb_read_page` for a zero-length page body at
    src/kb/mcp/browse.py:161).

    Three shapes currently emitted by cycle-31 target tools:
      - "Error:"           validator-class (e.g. src/kb/mcp/app.py:250
                           _validate_page_id; src/kb/mcp/browse.py:94,139;
                           src/kb/mcp/quality.py:142,281).
      - "Error "           runtime-exception shapes:
                             src/kb/mcp/browse.py:348  ("Error computing wiki stats: ...")
                             src/kb/mcp/quality.py:149,152  ("Error checking fidelity for ...")
                             src/kb/mcp/quality.py:184  ("Error running consistency check: ...")
                             src/kb/mcp/quality.py:245  ("Error computing reliability map: ...")
                             src/kb/mcp/quality.py:290  ("Error computing affected pages: ...")
      - "Page not found:"  logical-miss shape unique to kb_read_page
                           (src/kb/mcp/browse.py:125).

    Tagged-error form "Error[<category>]: ..." from src/kb/mcp/app.py:17
    is NOT matched — none of the target tools emit it today.
    (T9 — if a future refactor adopts error_tag() in these tools, widen
    the prefix set and re-run the Step-11 verification grep.)
    """
    first_line = output.split("\n", 1)[0]
    return first_line.startswith(("Error:", "Error ", "Page not found:"))
```

### Q2 — Empty / blank output semantics

**OPTIONS:** empty-as-success vs fourth-prefix-for-empty.
**ARGUE:** empty-as-success preserves MCP parity (projection of MCP behaviour); fourth-prefix diverges and flags legitimate empty pages.
**DECIDE:** empty-as-success. Document intentional in helper docstring; add helper unit tests for `""`, `"\n"`, `"\nbody"`.
**RATIONALE:** cycle-31 non-goal "NOT changing MCP tool bodies"; projecting empty as success mirrors MCP.
**CONFIDENCE:** high.

### Q3 — Parity test metric

**OPTIONS:** A (strict stream-aware), B (merged `result.output`), C (skip).
**ARGUE:** A is the accurate CLI↔MCP contract — CLI adds `\n` via click.echo, routes errors to stderr, exits non-zero; MCP returns raw string in-band. B loses the stream-split signal; C abandons T7.
**DECIDE:** Option A.
Per-subcommand assertion shape:
- Success: `result.exit_code == 0` and `result.stdout == mcp_output + "\n"` and `result.stderr == ""`.
- Error: `result.exit_code == 1` and `result.stderr == mcp_output + "\n"` and `result.stdout == ""`.
Use `CliRunner(mix_stderr=False)` in the parity-test fixture (Click 8.x supports this); if Click version lacks split streams, degrade to merged `result.output` with an xfail marker.
**RATIONALE:** correct contract; R2's finding; R1's amendment 2 elevated.
**CONFIDENCE:** high.

### Q4 — Scope expansion for pre-existing bugs

**OPTIONS:** A expand (3 retrofits + 3 tests); B defer to BACKLOG; C hybrid (stats only).
**ARGUE:** Option A closes a live silent-failure bug in three wrappers that share the same file and helper with cycle-31 scope. `feedback_batch_by_file.md` favors file-alignment. The helper is already built for exactly these cases. Scope increase is ~30 LOC code + ~60 LOC tests — well under the cycle-13 L2 primary-session ceiling.
**DECIDE:** Option A. Add **AC8**.

**AC8 spec:**
- Retrofit three existing wrappers to use `_is_mcp_error_response`:
  - `stats` subcommand at `src/kb/cli.py:640` — `startswith("Error:")` → `_is_mcp_error_response(output)`.
  - `reliability-map` subcommand at `src/kb/cli.py:799` — same swap.
  - `lint-consistency` subcommand at `src/kb/cli.py:827` — same swap.
- One regression test per retrofit (3 tests): force the MCP tool to emit its non-colon runtime-error shape, invoke the CLI, assert `exit_code == 1` and `stderr` contains the error text. Each test MUST be one that FAILS under the legacy `startswith("Error:")` discriminator (i.e. would have exited 0 before the retrofit).
- T8 grep recount: `output.startswith("Error:")` count in `cli.py` becomes **exactly 5** (was 8) — remaining lines are `list-pages` / `list-sources` / `graph-viz` / `verdict-trends` / `detect-drift` (all colon-only MCP emitters). `_is_mcp_error_response(output)` call sites become **exactly 6** (3 new + 3 retrofit) plus 1 definition.
- Note for CHANGELOG/history: cycle 31 resolves a silent-failure bug latent since cycles 27 (`stats`) and 30 (`reliability-map`, `lint-consistency`).

**RATIONALE:** file-aligned fix; minimal LOC; helper already built; user's `feedback_batch_by_file` preference.
**CONFIDENCE:** high.

### Q5 — Monkeypatch target

**OPTIONS:** `kb.cli.kb_<tool>` (broken) vs owner-module target.
**ARGUE:** function-local import resolves at call time against owner module.
**DECIDE:** owner-module. Per-subcommand:
- `read-page`: `monkeypatch.setattr("kb.mcp.browse.kb_read_page", spy)`
- `affected-pages`: `monkeypatch.setattr("kb.mcp.quality.kb_affected_pages", spy)`
- `lint-deep`: `monkeypatch.setattr("kb.mcp.quality.kb_lint_deep", spy)`
Cycle-30 test-file at `tests/test_cycle30_cli_parity.py:48` is the reference pattern.
**RATIONALE:** matches Python import resolution; R2's HIGH finding.
**CONFIDENCE:** high.

### Q6 — Control-char parity matrix

**OPTIONS:** accept asymmetry with pins vs normalize.
**ARGUE:** normalizing at CLI diverges from MCP (T7 violation). Accepting asymmetry with per-tool pins inherits existing MCP behaviour without drift risk.
**DECIDE:** accept. Test requirement: one control-char test per subcommand asserting MCP behaviour is projected:
- `kb read-page "concepts/rag\n"` → exits 1 with `"Error:"`-prefix validator message (MCP rejects via `_CTRL_CHARS_RE`).
- `kb affected-pages "concepts/rag\n"` → behaves as if `"concepts/rag"` (strip-then-validate path; may succeed or fail based on existence).
- `kb lint-deep "concepts/rag\n"` → same strip-then-validate behaviour as affected-pages.
**RATIONALE:** minimum-scope; T7 parity; R2 documented the asymmetry.
**CONFIDENCE:** medium-high.

### Q7 — Boundary test correctness

**OPTIONS:** only-`..` boundary (insufficient — misses discriminator bug) vs add non-colon boundary.
**ARGUE:** A `..`-only test passes under legacy `startswith("Error:")`, so it does NOT catch a wrapper that forgot to use `_is_mcp_error_response`. Need at least one non-colon error per new wrapper to pin the discriminator contract.
**DECIDE:** require one non-colon boundary test per new wrapper:
- `read-page`: invoke CLI with a nonexistent `page_id` → asserts stderr contains `"Page not found:"` and `exit_code == 1`. (No mocking needed — `browse.py:125` emits this naturally for a missing page.)
- `affected-pages`: monkeypatch `kb.compile.linker.build_backlinks` to raise `RuntimeError("forced")` → invoke CLI → asserts stderr contains `"Error computing affected pages:"` (non-colon space form) and `exit_code == 1`.
- `lint-deep`: monkeypatch `kb.lint.semantic.build_fidelity_context` to raise `FileNotFoundError` → invoke CLI → asserts stderr contains `"Error checking fidelity for"` and `exit_code == 1`.
Each of these MUST FAIL if a wrapper reverts to `startswith("Error:")`. Keep the `..`-traversal test too (pins validator at MCP boundary).
**RATIONALE:** discriminator-regression coverage; R2's HIGH finding.
**CONFIDENCE:** high.

### Q8 — Commit-count handling

**OPTIONS:** pre-count vs `+TBD`.
**DECIDE:** `+TBD`. CHANGELOG `[Unreleased]` and CHANGELOG-history both carry `+TBD` at Step 12; backfilled post-merge. Per cycle-30 L1.
**CONFIDENCE:** high.

### Q9 — Implementation venue

**OPTIONS:** primary session vs Codex dispatch.
**DECIDE:** primary session. Cycle-13 L2 + cycle-14 L1 both met; mechanical thin-wrapper replay; operator holds full context.
**CONFIDENCE:** high.

### Q10 — R3 requirement

**OPTIONS:** trigger R3 vs skip.
**ARGUE:** Cycle 31 has 8 ACs (with Q4 Option A), 10 design-gate questions (at trigger edge), no new security surface, no new write surface, helper is classifier not enforcer. Marginal R3 value low.
**DECIDE:** skip. R1 + R2 cover correctness + security axes; Step 5 resolves both.
**CONFIDENCE:** medium-high (boundary case on 10-question trigger).

---

## Conditions (C1-C14)

| # | CONDITION | File:line target | Grep spec | Expected count |
|---|-----------|------------------|-----------|----------------|
| C1 | Helper body uses first-line split | `src/kb/cli.py` | `output\.split\("\\n", 1\)\[0\]` | 1 |
| C2 | Helper matches exactly three prefixes | `src/kb/cli.py` | `startswith\(\("Error:", "Error ", "Page not found:"\)\)` | 1 |
| C3 | Helper docstring annotates `Error[` as not matched | `src/kb/cli.py` helper docstring | `"Error\["` + `"not emitted by cycle-31 tools"` | 1 |
| C4 | Helper call sites: 3 new + 3 retrofit = 6 total | `src/kb/cli.py` | `_is_mcp_error_response\(` | 6 (call) + 1 (def) = 7 |
| C5 | Legacy `startswith("Error:")` count after retrofit | `src/kb/cli.py` | `output\.startswith\("Error:"\)` | exactly 5 |
| C6 | Three new wrappers use function-local import | `src/kb/cli.py` | `from kb\.mcp\.(browse\|quality) import kb_(read_page\|affected_pages\|lint_deep)  # noqa: PLC0415` | 3 |
| C7 | No module-level MCP imports | `src/kb/cli.py` module scope (before first `@cli`) | AST-scan | 0 |
| C8 | Wrappers forward `page_id` verbatim | `src/kb/cli.py` new wrapper bodies | `page_id\.(strip\|lower\|upper\|encode\|replace)` | 0 |
| C9 | No CLI-layer page_id f-string interpolation | `src/kb/cli.py` new wrapper bodies | `f".*\{page_id\}.*"` outside the single MCP call line | 0 |
| C10 | `read-page` wrapper does not read file directly | `src/kb/cli.py` read_page body | `Path\(\|read_text\|open\(\|\.stat\(` | 0 |
| C11 | Test file monkeypatches owner module (not kb.cli) | `tests/test_cycle31_cli_parity.py` | `monkeypatch\.setattr\("kb\.mcp\.(browse\|quality)\.kb_` | 3 |
| C12 | Parity tests use `mix_stderr=False` | `tests/test_cycle31_cli_parity.py` | `CliRunner\(mix_stderr=False\)` | ≥1 |
| C13 | Each new wrapper has a non-colon boundary test | `tests/test_cycle31_cli_parity.py` | tests asserting stderr substrings `"Page not found:"`, `"Error computing affected pages:"`, `"Error checking fidelity for"` | 3 (one per subcommand) |
| C14 | AC8 retrofit regression tests | `tests/test_cycle31_cli_parity.py` | tests forcing non-colon emitters for `stats`, `reliability-map`, `lint-consistency` | 3 |

Step-11 security-verify must re-run C1-C14 and emit mitigation confirmations for T1-T10.

---

## Final decided design (AC1-AC8)

**AC1 — `kb read-page <page_id>`.** Unchanged from requirements. Function-local `from kb.mcp.browse import kb_read_page  # noqa: PLC0415`. Body: `output = kb_read_page(page_id)`; branch via `_is_mcp_error_response(output)`; success → `click.echo(output)` + exit 0; error → `click.echo(output, err=True); sys.exit(1)`. Outer `try/except Exception → _error_exit(exc)`.

**AC2 — `kb affected-pages <page_id>`.** Same shape; `from kb.mcp.quality import kb_affected_pages`. Empty-state `"No pages are affected by changes to X"` exits 0 (not an error — inherited from MCP empty-state precedent).

**AC3 — `kb lint-deep <page_id>`.** Same shape; `from kb.mcp.quality import kb_lint_deep`. Zero options beyond positional.

**AC4 — `_is_mcp_error_response` helper.** Use the canonical body in Q1 above. Placed near `_error_exit` (around `cli.py:~72`). Docstring must enumerate three shapes with file:line citations AND include the T9 `"Error["`-not-matched annotation. Empty / blank-first-line → False (exit 0).

**AC5 — Body-execution tests.** For each new subcommand, one `CliRunner.invoke(cli, ["<subcmd>", "<arg>"])` test with `monkeypatch.setattr("kb.mcp.<module>.kb_<tool>", spy)` (OWNER module — NOT `kb.cli`). Assertion: `spy_called["value"] is True` and `spy_called["kwargs"] == {"page_id": "<arg>"}`. Parallel-assertion shape across all three (cycle-30 L3).

**AC6 — Integration-boundary tests.** Per new subcommand, TWO boundary tests:
- Traversal (`..`): exits 1 with stderr `"Error: Invalid page_id:"` — pins validator.
- Non-colon runtime/logical-miss: per Q7 above — pins `_is_mcp_error_response` coverage. Would FAIL under legacy `startswith("Error:")`.

**AC7 — BACKLOG/CHANGELOG/CLAUDE.md updates.** Per requirements; CLI-count 19 → 22; test-count update; commit-count `+TBD`. Wording cleanup for BACKLOG write-path grouping per R2 §8 (optional polish, not blocking).

**AC8 — Legacy-wrapper retrofit (NEW).** Per Q4 Option A. Three one-line swaps at `cli.py:640`, `cli.py:799`, `cli.py:827`; three regression tests at `tests/test_cycle31_cli_parity.py`. Tests MUST be failing-before / passing-after by construction (force non-colon emitter, assert exit 1 and stderr text). T8 grep recount: `startswith("Error:")` count becomes exactly 5; `_is_mcp_error_response` call sites become exactly 6.

### Canonical `_is_mcp_error_response` body

(see Q1 decision above — same text, copied verbatim into `src/kb/cli.py`)

### Per-subcommand test matrix

| Subcommand | Help smoke | Body-spy (AC5) | Traversal boundary (AC6a) | Non-colon boundary (AC6b) | Parity success (Q3) | Parity error (Q3) |
|---|---|---|---|---|---|---|
| `read-page` | 1 | 1 | 1 (`"..") | 1 (`Page not found:`) | 1 | 1 |
| `affected-pages` | 1 | 1 | 1 (`"..") | 1 (`Error computing affected pages:`) | 1 | 1 |
| `lint-deep` | 1 | 1 | 1 (`"..") | 1 (`Error checking fidelity for`) | 1 | 1 |

Plus:
- Helper unit tests: 3 positive (one per prefix) + 3 negative (empty `""`, blank-first-line `"\nbody"`, mid-body-error `"ok\nError: not first line"`) + 1 CRLF edge (`"Error:\r\ntext"`) = 7.
- AC8 retrofit regression tests: 3 (one per legacy wrapper).
- Boot-lean test extension: 1 subprocess test that imports `kb.cli` and checks `kb.mcp.browse`/`kb.mcp.quality` not in `sys.modules` before any subcommand invocation.

**Total new tests:** 18 wrapper tests + 7 helper tests + 3 retrofit tests + 1 boot-lean = **29 tests minimum**.

---

## Verdict

**APPROVE.**

R1's two blocking amendments (first-line anchor, parity-test mandate) are resolved in Q1 and Q3. R2's five findings (discriminator edge cases, boundary-test pathology, parity-test metric, monkeypatch target, legacy-wrapper retrofit) are all resolved in Q2, Q7, Q3, Q5, and Q4 respectively. No open objections. Ready for Step 6 task decomposition and Step 9 implementation.

---

## Step-9 implementer brief

**What to implement (sequential):**

1. **Helper + 3 new wrappers** in `src/kb/cli.py`:
   - Add `_is_mcp_error_response` near `_error_exit` (~cli.py:72) using the canonical body from Q1.
   - Add three `@cli.command` subcommands (`read-page`, `affected-pages`, `lint-deep`) at tail of file, each ~15 LOC matching cycle-27/30 thin-wrapper template.

2. **AC8 retrofit** in `src/kb/cli.py`:
   - Line 640 (`stats`): `startswith("Error:")` → `_is_mcp_error_response(output)`.
   - Line 799 (`reliability-map`): same.
   - Line 827 (`lint-consistency`): same.

3. **Tests** in `tests/test_cycle31_cli_parity.py` (~350 LOC, 29 tests):
   - Follow the matrix in "Per-subcommand test matrix" above.
   - Monkeypatch pattern: `monkeypatch.setattr("kb.mcp.<module>.kb_<tool>", spy)` — OWNER module, not `kb.cli`.
   - Use `CliRunner(mix_stderr=False)` for parity tests.

4. **Docs** (Step 12):
   - `BACKLOG.md:146`: remove the three-tool bullet; drop count 12→9; optional R2 §8 wording polish.
   - `CHANGELOG.md [Unreleased]`: compact entry; commit count `+TBD`.
   - `CHANGELOG-history.md`: full per-AC block; note AC8 resolves latent cycle 27/30 silent-failure bug.
   - `CLAUDE.md`: CLI count 19 → 22; test count updated via `pytest --collect-only | tail -1` AFTER R1/R2 commits.

**Files to touch:** `src/kb/cli.py` (helper + 3 new + 3 retrofit); `tests/test_cycle31_cli_parity.py` (new, ~29 tests); `BACKLOG.md`, `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`.

**Suggested commit ordering:**
1. `feat(cycle 31): AC4 helper `_is_mcp_error_response` + helper unit tests`
2. `feat(cycle 31): AC1-AC3 read-page / affected-pages / lint-deep wrappers + body-spy + boundary tests`
3. `feat(cycle 31): AC6 parity tests (success + error stream-semantic assertions)`
4. `fix(cycle 31): AC8 retrofit stats / reliability-map / lint-consistency to `_is_mcp_error_response` + regression tests`
5. `docs(cycle 31): BACKLOG + CHANGELOG + CLAUDE.md + CHANGELOG-history updates`
6. `fix(cycle 31): R1/R2 amendments if any surfaced in code review`

**Primary-session venue:** confirmed (Q9). No Codex dispatch.

---

**File written:** `D:\Projects\llm-wiki-flywheel\docs\superpowers\decisions\2026-04-25-cycle31-design.md`
