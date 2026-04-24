# Cycle 31 — Step 8 Plan Gate Review

**Verdict:** REJECT  
**Grounding:** Requirements AC1-AC7 are at `2026-04-25-cycle31-requirements.md:38-97`; design AC1-AC8 are at `2026-04-25-cycle31-design.md:232-250`; plan tasks are at `2026-04-25-cycle31-plan.md:31-359`.

## 1. Coverage Matrix

| AC | TASK(s) | CONDITION(s) | Gate |
|---|---|---|---|
| AC1 read-page | TASK 2 | C4, C6-C11 | Partial: wrapper/body-spy/traversal planned (`plan:86-181`), but no C7-C10 grep/AST commands. |
| AC2 affected-pages | TASK 2 | C4, C6-C9, C11 | Partial for same reason. |
| AC3 lint-deep | TASK 2 | C4, C6-C9, C11 | Partial for same reason. |
| AC4 helper | TASK 1 | C1-C4 | Partial: unit tests cover prefixes and first-line behavior (`plan:39-68`), but C1-C3 greps from design `209-216` are not in TASK 1 commands (`plan:77-80`). |
| AC5 body execution | TASK 2 + TASK 4 | C11, C12 | OK: owner-module monkeypatch and `mix_stderr=False` planned (`plan:163-164`, `219-222`). |
| AC6 boundaries/parity | TASK 2 + TASK 3 + TASK 4 | C12, C13 | Partial: traversal/non-colon boundaries planned (`plan:162-166`, `189-197`), but TASK 4 contradicts design parity metric; see PLAN-AMENDS-DESIGN. |
| AC7 docs | TASK 6 | none | OK: docs/test-count verification planned (`plan:318-359`). |
| AC8 retrofit | TASK 5 | C5, C14, C4 | Partial: tests and C5 planned (`plan:253-314`), but C4 call-site grep command is wrong. |

**Condition gaps:** C4 design expects `_is_mcp_error_response\(` count **7** including definition (`design:216`); TASK 5 command expects 6 with a regex that still matches the `def` line (`plan:309-314`). C7 requires module-scope AST scan (`design:219`; threat T6 `443-456`), missing from TASK 2. C8-C10 have condition claims (`plan:171`) but no grep commands (`plan:174-179`).

## 2. Threat Mapping

| Threat | Planned verification | Gate |
|---|---|---|
| T1 traversal | TASK 2 traversal tests + wrapper shape (`plan:160-181`) | OK, pending missing C7-C10 greps. |
| T2 sanitization | TASK 2 wrapper echoes MCP `output` (`plan:90-157`) | OK implementation shape; not listed in TASK 2 threat refs. |
| T3 discriminator | TASK 1 helper tests + TASK 3 non-colon tests (`plan:39-68`, `189-199`) | OK, except missing C1-C3 greps. |
| T4 control-char injection | Expected TASK 2/3 per-tool behavior tests | GAP: design requires one control-char test per subcommand (`design:165-172`); plan has none. |
| T5 output-size DoS | C10 no direct read-page file I/O | GAP: C10 claimed (`plan:171`) but no `Path/read_text/open/stat` grep command. |
| T6 boot-lean | Function-local import grep | GAP: threat requires module-level AST scan and subprocess `kb --version`/`sys.modules` test (`threat:443-456`); design also requires boot-lean test (`design:264-269`); plan omits it. |
| T7 parity | TASK 4 stream tests | GAP: plan monkeypatches MCP tools instead of direct MCP-vs-CLI calls (`plan:219-220`), contradicting design (`design:25-27`). |
| T8 peer drift | TASK 5 explicit retrofit + recount (`plan:239-314`) | Partial: intent OK; C4 grep count wrong. |
| T9 tagged Error[ | TASK 1 docstring/test discipline (`plan:35-75`) | OK. |
| T10 Click coercion | Informational, no code | OK. |

## 3. Per-TASK Completeness

| Task | Files | Change | Test expectation | Criteria | Threat | Commands | Gate |
|---|---|---|---|---|---|---|---|
| 1 | yes | yes | yes | yes | yes | yes | Partial: missing C1-C3 greps. |
| 2 | yes | yes | yes | yes | yes | yes | Partial: missing C7-C10 verification and T2/T4/T5 refs. |
| 3 | yes | yes | yes | yes | yes | yes | OK for C13/T3. |
| 4 | yes | yes | yes | yes | yes | yes | Reject: parity shape amends design. |
| 5 | yes | yes | yes | yes | yes | yes | Partial: C4 count command incorrect. |
| 6 | yes | yes | docs expectation at `plan:352-359` | yes | yes | yes | OK. |

## 4. Commit Count

OK. The plan states **6 tasks -> 6 commits** (`plan:27`) and TASK 6 keeps CHANGELOG commits as `+TBD` with post-merge backfill (`plan:336`), matching design Q8 (`design:57`, `190-191`). It does **not** pre-count R1/R2 fix commits.

## 5. PLAN-AMENDS-DESIGN

**PLAN-AMENDS-DESIGN:** TASK 4 replaces the design-required direct MCP-vs-CLI parity check with monkeypatched tool returns. Design Q3 says “The MCP side calls the tool function directly with the same input” (`design:27`); plan TASK 4 says to monkeypatch the owner-module tool to return a known string (`plan:219-220`). This is a real contradiction, not a harmless reorder.

## Final Verdict

**REJECT.** Approval requires: add the three control-char tests, add boot-lean subprocess/AST verification, add C7-C10 grep/AST commands, fix C4 count command to exclude or include the definition consistently, and restore TASK 4 to direct MCP-vs-CLI stream-semantic parity.
