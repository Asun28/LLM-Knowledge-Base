# Cycle 36 — Plan Amendments (Step 8 plan-gate REJECT response)

**Date:** 2026-04-26
**Source:** Codex plan-gate REJECT verdict (`aa9b6759614560b6b`) with 6 specific gaps + 1 PLAN-AMENDS-DESIGN flag
**Resolution:** Per cycle-21 L1, all gaps are documentation/design clarification gaps (no new code exploration required); resolved inline without re-dispatching Codex.

---

## PLAN-AMENDS-DESIGN response

The plan-gate flagged Task 9's combined `SECURITY.md` + workflow `--ignore-vuln` change as contradicting Step-5 Q17 / C8 / C10. Re-reading Q17:

> Workflow `--ignore-vuln` set + `SECURITY.md` Known Advisories table are reconciled 1:1 with what pip-audit emits. Any Dependabot alert NOT in pip-audit's report gets a cycle-37 BACKLOG entry...

The contradiction in my original Task 9: I added `GHSA-v4p8-mg3p-g94g` (Dependabot-only) to SECURITY.md while leaving workflow `--ignore-vuln` unchanged. C10 parsing test asserts SECURITY.md ↔ workflow set-equality — this would have FAILED.

Additionally inspection of current `SECURITY.md` line 21 reveals an EXISTING drift: the litellm row mentions `GHSA-r75f-5x8p-qvmc` parenthetically, but workflow does not flag this ID. C10 parsing test would fail on the cycle-35 baseline state too.

**Resolution per Q17**: Clean up SECURITY.md to be 1:1 with workflow `--ignore-vuln`; move Dependabot-only IDs (both `GHSA-r75f-5x8p-qvmc` and `GHSA-v4p8-mg3p-g94g`) to BACKLOG.md as Phase 4.6 drift entries. Workflow `--ignore-vuln` stays at the current 4-flag set (matches pip-audit emission). This is **NOT** a design change — it operationalises Q17's 1:1 reconciliation rule.

---

## Gap-by-gap resolution

### Gap 1 — AC18 uncovered (T5)

**Plan-gate finding:** Task 9 references `.data/cycle-36/alerts-baseline.json` but doesn't plan the explicit `gh api` snapshot or save command.

**Resolution:** AC18 was actually completed at Step 2 (the baseline file already exists at `.data/cycle-36/alerts-baseline.json` — created during cycle-36 Step 2 baseline capture). Task 9 inherits this artefact; no new `gh api` call needed during Step 9.

**Plan amendment:** TASK 9 is updated to explicitly cite the existing baseline file and to RE-READ Dependabot alerts via `gh api` ONLY at Step 11.5 (post-Step-11) per the skill's existing-CVE opportunistic patch protocol. AC18 verification at Step 11.5 against the Step 2 baseline confirms the alert state is unchanged or documents drift.

### Gap 2 — AC19 uncovered (T5)

**Plan-gate finding:** No task verifies `litellm 1.83.7` still requires `click==8.1.8`.

**Resolution:** This was confirmed at Step 2 baseline via `python -c "import urllib.request, json; data = json.loads(urllib.request.urlopen('https://pypi.org/pypi/litellm/1.83.7/json').read()); ..."` which returned `1.83.7 requires_dist: click==8.1.8`. The constraint is unchanged.

**Plan amendment:** TASK 9 confirmation step 4 added — "Confirm via PyPI metadata that `litellm 1.83.7` still requires `click==8.1.8` (per cycle-32 BACKLOG entry); document in cycle-36 investigation doc." If the constraint relaxes, escalate to design amendment per cycle-17 L3.

### Gap 3 — AC20 / C8 / C10 contradictory (T5)

**Plan-gate finding (PLAN-AMENDS-DESIGN):** Adding `GHSA-v4p8-mg3p-g94g` to `SECURITY.md` while leaving workflow `--ignore-vuln` unchanged contradicts Q17's 1:1 reconciliation rule.

**Resolution:** Per Q17, Dependabot-only advisories (NOT emitted by pip-audit) belong in BACKLOG as drift entries, NOT in SECURITY.md.

**Plan amendment for TASK 9:**

1. **`SECURITY.md` cleanup**: Update the litellm row to mention ONLY `GHSA-xqmj-j6mv-4862` (the ID pip-audit actually emits and the workflow flags). Move the parenthetical `GHSA-r75f-5x8p-qvmc (critical)` mention to a NEW BACKLOG entry. Do NOT add `GHSA-v4p8-mg3p-g94g` to SECURITY.md.
2. **Workflow `--ignore-vuln`**: NO CHANGE. Stays at current 4-flag set: `CVE-2025-69872`, `GHSA-xqmj-j6mv-4862`, `CVE-2026-3219`, `CVE-2026-6587`.
3. **BACKLOG.md cycle-37 drift entries** (per Q17 BACKLOG-shape):
   - `Phase 4.6 — Dependabot/pip-audit drift on litellm GHSA-r75f-5x8p-qvmc — Dependabot reports the critical advisory (LiteLLM Proxy code execution) but pip-audit on the live CI install env does not emit it as of 2026-04-26. Workflow ignore-vuln currently excludes this ID. Document in cycle-36 investigation; monitor for pip-audit data refresh; escalate if pip-audit emits it (would force CI fail).`
   - `Phase 4.6 — Dependabot/pip-audit drift on litellm GHSA-v4p8-mg3p-g94g — Dependabot reports the high-severity advisory (LiteLLM authenticated MCP-stdio command execution; created 2026-04-25T23:37Z; fix=1.83.7 BLOCKED by click<8.2 transitive). Pip-audit on the live CI install env does not emit it as of 2026-04-26. Same handling as GHSA-r75f-5x8p-qvmc above.`
4. **C10 parsing test (TASK 7)**: After SECURITY.md cleanup, the test passes set-equality between `SECURITY.md` advisory IDs and workflow `--ignore-vuln` flags.

**Net effect:** SECURITY.md and workflow stay 1:1; Dependabot drift is tracked in BACKLOG; C10 test passes.

### Gap 4 — AC1 / T8 partial

**Plan-gate finding:** Plan relies on "already done in Step 2 baseline" for AC1 hanger identification, but no task explicitly schedules the evidence write.

**Resolution:** The evidence is the cycle-36 investigation document (TASK 12). The hanger has been identified via Step-2 CI log analysis: position #1155 = `test_cross_process_file_lock_timeout_then_recovery` per `gh run view 24947760653 --log` output (1151 passed at hang).

**Plan amendment for TASK 12:** Investigation doc § "AC1 Hanger Identification" explicitly captures:
- CI run IDs where the hang occurred (24947760653, 24947676139, 24945114305)
- Pytest progress: 1151 passed at 38% completion before `KeyboardInterrupt` from `popen_spawn_win32.py:112`
- Test position via `pytest --collect-only -q | sed -n '1155p'` confirmed locally
- Hypothesis (editable-install pth resolution / PYTHONNOUSERSITE / kb.config PROJECT_ROOT heuristic in spawned child)
- Local pass time: 1.03s on Windows 11

This becomes the AC1 evidence trail for Step-11 verifier.

### Gap 5 — C13 partial (3-round PR review)

**Plan-gate finding:** Plan notes R3 review fires but doesn't assign a task to dispatch the three independent PR review rounds.

**Resolution:** R3 dispatch happens at Step 14 (PR review), not Step 9 (implementation). The plan covers Steps 1-12; Steps 13-15 are downstream skill-pipeline steps. C13 should be tracked as a Step-14 obligation, not a TASK-11 implementation step.

**Plan amendment:** Add explicit note at the end of the plan:

> **Step 14 (PR review) obligations from C13 / Q15:**
> - Round 1 (parallel): Codex (architecture) + Sonnet (edge-cases / security)
> - Round 2: Codex verifies R1 fixes
> - Round 3: Sonnet synthesis with audit-doc drift focus per cycle-19 L4
> - Trigger justification: 22 design-gate questions resolved at Step 5 fires R3 per cycle-19 L4 criterion (d) + cycle-17 L4 trigger threshold

### Gap 6 — TASK 9 separation concern (T5 / C8 / C10)

**Plan-gate finding:** Combining `.github/workflows/ci.yml` + `SECURITY.md` + `BACKLOG.md` in one cluster is too broad; accepted pip-audit suppressions and Dependabot-only drift entries have different invariants.

**Resolution:** Split TASK 9 into two:

**TASK 9a — pip-audit / SECURITY.md / workflow reconciliation (CLUSTER):**
- Files: `.github/workflows/ci.yml` (no change), `SECURITY.md` (remove parenthetical Dependabot-only mention)
- Rationale: workflow `--ignore-vuln` and SECURITY.md Known Advisories table must stay 1:1 (cycle-32 T5).
- Test: C10 parsing test passes set-equality.

**TASK 9b — BACKLOG drift entries (NEW):**
- Files: `BACKLOG.md`
- Rationale: Dependabot alerts NOT in pip-audit's emission go to BACKLOG as cycle-37 follow-ups, distinct from SECURITY.md's "currently-suppressed" semantic.
- Test: BACKLOG entries grep-able for Step-11 verifier.

This separation matches Q17's "1:1 reconciled" vs "drift-tracked" semantic distinction.

---

## Other plan-gate confirmations (no amendment needed)

- AC2-AC8, AC10-AC17 (deferred), AC21-AC25: Coverage is sufficient.
- C1-C7, C9, C11-C12, C14, C16: Coverage is sufficient.
- Three-commit sequencing per Q16/Q21: Validated.
- File grouping per `feedback_batch_by_file`: Validated except for TASK 9 split (above).
- C15 hygiene (scratch file cleanup): Add note in commit-3 self-check that `findings.md / progress.md / task_plan.md / claude4.6.md` are absent before push.

---

## Verdict

NO PLAN-AMENDS-DESIGN-HONORED — plan-gate's PLAN-AMENDS-DESIGN flag was correctly raised but the resolution is operationalising Q17's existing rule, not a design change. PROCEED to Step 9 with the amendments above folded in.

End of plan amendments.
