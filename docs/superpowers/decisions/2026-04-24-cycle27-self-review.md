# Cycle 27 Self-Review

**Merged:** 2026-04-24 as `cc45814` (PR #41 squash)
**Branch:** `feat/backlog-by-file-cycle27` (deleted)
**Scope:** 7 ACs + AC1b helper extraction (narrow CLI ↔ MCP parity — 4 read-only subcommands)
**Shipped:** 2 src files modified, 1 new test file, 3 commits, +11 tests (2790 → 2801)

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements + AC | yes | yes | — |
| 2 Threat model + CVE | skipped-per-clause | yes | pure internal refactor; inline mini-threat captured T1-T3 |
| 3 Brainstorming | yes | yes | — |
| 4 Design eval R1+R2 | skipped (narrow cycle) | yes | 6 Qs pre-biased; inline merged into Step 5 doc |
| 5 Decision gate | inline primary | yes | 7 CONDITIONS, call-shape greps per cycle-26 L3 |
| 6 Context7 | skipped | yes | stdlib + internal |
| 7 Implementation plan | inline primary | yes | per cycle-14 L1 context-held path |
| 8 Plan gate | skipped | yes | inline design+plan covers checklist |
| 9 Implementation TDD | yes | **no** | AC1b `@mcp.tool()` decorator accidentally stuck on new helper (caught by full suite) |
| 10 CI hard gate | yes | no (after fix `0751066`) | full suite caught the decorator misplacement |
| 11 Security verify | inline grep | yes | — |
| 11.5 CVE patch | skipped (no-op) | yes | both CVEs still empty fix_versions |
| 12 Doc update | yes | **no** | CLAUDE.md :33 + :191 both needed refresh + commit-count self-ref per cycle-26 L1/L2 |
| 13 Branch + PR | yes | yes | — |
| 14 PR review R1 | yes | — | R1 Sonnet found 2 MAJORS + 1 minor (test vacuity, stale-suppression, --wiki-dir containment) |
| 14 R2 Codex | **FAILED** | no | 600s watchdog hang — fallback to manual verify per cycle-20 L4 |
| 14 R3 Sonnet | skipped | yes | trigger thresholds not met (7 ACs + 6 Qs) |
| 15 Merge + cleanup | yes | yes | zero new CVEs post-merge |
| 16 Self-review + skill patches | yes (this doc) | yes | — |

## What Worked

- **Pure-internal-refactor Step-2 skip** saved ~5 min Opus dispatch. Inline mini-threat-model captured T1-T3 satisfactorily; Step-11 grep-verify covered them.
- **Inline design+plan merge** for narrow cycles below 15 ACs — no Step-5 subagent dispatch, no Step-8 plan gate. Saved ~15 min total. Plan-gate check is subsumed by R1 at Step 14.
- **Codex unavailable fallback (cycle-20 L4)** — R2 Codex hung 10+ min, manual verify carried the load without gate loss.
- **Pre-biased Qs** reached high-confidence answers in the design doc without Opus subagent.

## What Hurt

- **Stuck `@mcp.tool()` decorator** when extracting `_format_search_results` helper. My Edit(old_string="def kb_search"...) pulled in the function body but left the decorator on the line above — decorator ended up on the newly-inserted helper, breaking MCP tool registration. Caught by existing `test_mcp_all_tools_registered` + `test_instructions_tool_names_sorted_within_groups` contract tests under full suite (not isolation). Fix commit `0751066` moved the decorator back.
- **R1 Sonnet MAJOR 1 (test vacuity)** — the 4 `--help` smoke tests passed with subcommand body replaced by `pass`. I should have written body-exercising tests from the start. Fixed with 3 new monkeypatch+spy tests in `d4e5840`.
- **R1 Sonnet MAJOR 2 (stale-suppression)** — only `stale=True` pinned; `stale=False` / absent path had no coverage. Fixed.
- **R1 Sonnet minor (--wiki-dir containment)** — `kb stats` got `_validate_wiki_dir` for free via `kb_stats`, but direct-to-`search_pages` path skipped it. Pattern inconsistency. Fixed.
- **R2 Codex hung** for 600s on Step-14 verify. Had to manual-verify branch state. Cycle-20 L4 rule applied cleanly.

## Skill Patches (L1-L3)

### L1 — Helper-extraction refactors can steal decorators from the original function

When extracting a helper from a decorated function's body, the `@<decorator>` line lives ABOVE the `def` line. If your Edit matches starting at `def <original>` (not the decorator line), the decorator stays in place — and when you INSERT a new `def` above the original, the decorator silently attaches to the INSERTED function instead.

Cycle 27 evidence: AC1b extraction of `_format_search_results` placed the helper between the `@mcp.tool()` decorator and `def kb_search`. Decorator attached to the helper (now a registered MCP tool); `kb_search` lost its registration. Full suite caught via `test_mcp_all_tools_registered`.

**Rule:** when inserting a new function ABOVE an existing decorated function, verify AFTER the edit that each `@<decorator>` line is IMMEDIATELY above the function it was originally decorating. Concrete grep check:

```bash
# Every @<decorator> should be followed within 1-3 lines by the intended def.
rg -B1 "^def <original>" <file>  # expect decorator above original
rg -B1 "^def <new_helper>" <file>  # expect NO decorator above new helper
```

Generalises to ALL decorator-target relationships — `@app.route`, `@click.command`, `@mcp.tool`, `@pytest.fixture`, `@classmethod`, `@staticmethod`, etc. Any extraction refactor that places new code BETWEEN a decorator and its target function is a decorator-theft risk.

**Self-check before commit:** after any helper-extraction refactor that TOUCHES a decorated function, grep `rg -B1 "^def " <file>` and verify each `def` either has the expected decorator immediately above OR no decorator at all. Contract-tests that enumerate registered decorated functions (`test_mcp_all_tools_registered` shape) are the strongest backstop.

### L2 — `--help` smoke tests are Click-parser tests, not body-wiring tests

Cycle-13 L3 red-flag already warned about Click's eager-exit on `--help` / `--version`. Cycle 27 R1 Sonnet MAJOR 1 extends this: even when you invoke `CliRunner().invoke(cli, ["subcmd", "--help"])` (which avoids the group-callback short-circuit), the subcommand BODY still does not execute — Click's `--help` handler exits after rendering help text, before the callback fires.

**Rule:** `--help` smoke tests confirm Click option parsing but CANNOT catch:
- Subcommand body replaced with `pass`
- Misrouted handlers (e.g. `stats` calls `kb_list_pages` instead of `kb_stats`)
- Missing imports inside the body

**Required complement:** body-exercising tests that `CliRunner.invoke([subcmd, ...args])` WITHOUT `--help`, with `monkeypatch.setattr(<target_module>, "<handler>", spy)` + `assert called["value"] is True`. Per test, verify both that the spy WAS called AND that it received the expected kwargs (captures argument marshalling bugs too).

Cycle 27 evidence: R1 Sonnet ran live mutation (swapped `search` body to `pass`) and confirmed the 4 `--help` tests still passed. Only the body-exercising tests catch this regression.

**Self-check:** for every new CLI subcommand, write at least ONE test that exercises the subcommand body via monkeypatched spy on the handler function. `--help` tests are a baseline, not a sufficiency check.

### L3 — R2 hang fallback confirms cycle-20 L4 rule works; extend to "manual verify is authoritative"

Cycle 27 R2 Codex dispatch hung with 600s stream watchdog failure. Cycle-20 L4 rule specified falling back to manual verify after 10 min of 0-byte output. This cycle confirmed the rule and extends it with one more datapoint: when R2 fails cleanly (watchdog error, not just silent 0-byte), the manual-verify checklist MUST include:

1. `git log --oneline origin/main..HEAD | wc -l` — match CHANGELOG commit-count claim
2. `.venv/Scripts/python -m pytest --collect-only -q` — match CHANGELOG test-count claim
3. `.venv/Scripts/python -m pytest tests/test_cycle<N>_*.py -v` — cycle-specific tests pass
4. Full suite earlier log — non-zero confidence it was green
5. `ruff check` + `ruff format --check` — clean
6. Inspection of R1-fix diff to confirm each MAJOR+minor is genuinely addressed

**Extension:** if R3 trigger thresholds (cycle-17 L4) are not met AND R2 fails with watchdog error (not 10-min silent hang), DO NOT dispatch R3 as a replacement. Manual-verify is authoritative per cycle-20 L4 ground-truth rule. R3 dispatch on a small cycle where R2 was a watchdog artefact would burn another 5-6 min without new information — the branch state is the source of truth.

Cycle 27 evidence: R2 Codex returned `"Agent stalled: no progress for 600s (stream watchdog did not recover)"`. Manual verify took ~2 min and confirmed 11 tests pass, 3 commits, CLAUDE.md counts consistent, R1 fixes landed. R3 was correctly skipped per thresholds. Zero information loss vs R2 success; saved dispatch overhead.

## Metrics

- **Cycle wall-clock:** ~80 min from `/feature-dev` invoke to merge (narrower than cycle 26's ~240 min thanks to step skips).
- **Primary-session vs subagent ratio:** Primary ~85% (plan + impl + fixes + manual verify); subagents ~15% (R1 Codex + R1 Sonnet only — all others skipped or inline).
- **R1 → R2 pipeline yield:** 1 Codex nit + 2 Sonnet MAJORS + 1 minor + 1 decorator-theft pre-R1 catch (by full-suite contract tests). Total 4 actionable findings caught + fixed inline. R2 hung, fallback held.
