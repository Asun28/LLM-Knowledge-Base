# Cycle 26 Self-Review

**Merged:** 2026-04-24 as `ec111f1` (PR #40 squash)
**Branch:** `feat/backlog-by-file-cycle26` (deleted)
**Scope:** 8 AC + AC2b (vector-model cold-load observability + BACKLOG hygiene)
**Shipped:** 2 src files modified, 1 new test file + 1 extended cycle-23 test, 8 commits, +8 tests (2782 → 2790)

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements + AC | yes | yes | — |
| 2 Threat model + CVE | yes | yes | — (6 threats, clean baseline) |
| 3 Brainstorming | yes | yes | — |
| 4 R1 Opus + R2 Codex design-eval | yes | yes | R1 caught missing boot-lean test (AC2 contract unenforceable without allowlist extension) |
| 5 Decision gate | yes | yes | 16 resolved questions (≥10 → R3 trigger for PR review) |
| 6 Context7 | skipped | yes | pure stdlib + internal |
| 7 Implementation plan (primary-session) | yes | yes | — |
| 8 Plan gate | yes | no | REJECT false-positive on T1 (accepted threat); resolved inline per cycle-21 L1 |
| 9 Implementation | yes | yes | — (all tests green in isolation + full suite) |
| 10 CI hard gate | yes | yes | 2789 → 2790 after R1 fix |
| 11 Security verify | yes | yes | APPROVE (all T1-T6 + CONDITIONS 1-13 IMPLEMENTED) |
| 11.5 CVE patch | skipped | yes | both CVEs have empty fix_versions — no-op |
| 12 Doc update | yes | no | initial CLAUDE.md refresh missed a sibling test-count site (R2 caught) |
| 13 Branch + PR | yes | yes | — |
| 14 PR review (R1+R2+R3) | yes | no | R1 Sonnet MAJOR on M1 revert-tolerance; R2 caught 2 count drifts; R3 clean |
| 15 Merge + cleanup | yes | yes | zero new CVEs post-merge |
| 16 Self-review + skill patches | yes (this doc) | yes | — |

## What Worked

- **Primary-session plan draft (cycle-14 L1).** 8-AC plan drafted in ~6 min. Plan-gate caught 2 doc gaps (T1 coverage framing, TASK 2-4 test cross-refs) — both resolved inline per cycle-21 L1.
- **Parallel R1 Opus + R2 Codex design-eval.** Opus caught the AC2 boot-lean test gap (biggest leverage amendment); Codex caught the caplog.set_level issue + counter asymmetry doc-debt. Orthogonal findings.
- **Cycle-25 L2 pattern applied proactively.** M1 fix (revert-tolerance on CONDITION 3) used the snapshot-stub pattern directly — `monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", raising_stub)` enters `_get_model` body AND fires the raise AFTER the success path log/counter, divergent-failing a `finally:` regression.
- **R3 fired at 9 ACs below the 25 threshold** due to 16 design-gate questions triggering cycle-17 L4's secondary criterion. R3 verified the post-success ordering trace; no new issues.

## What Hurt

- **CLAUDE.md test count drift hit a SECOND location** I didn't update. Line 33 (Implementation Status) was updated in TASK 8; line 191 (Testing section) was NOT. R2 Codex caught the miss. Both reference the full-suite count in different narrative framings.
- **Commit-count off by one after R1-fix commit.** CHANGELOG/CHANGELOG-history said "6 commits" after the R1-fix commit landed — but the R1-fix commit itself was #6, and the commit that updated the count was #7. Pre-commit arithmetic needs +1 for the commit that contains the count claim.
- **Plan-gate T1 false-positive.** T1 is an ACCEPTED threat with NO runtime mitigation (grep-only verification at Step 11). The Codex plan-gate prompt interpreted every T1-T6 row as requiring a test assertion, triggering a REJECT. Per cycle-21 L1 the gap was documentation-only — resolved in the plan doc by adding explicit "T1 grep-verification at TASK 7 CI gate" text.
- **CONDITION 9 grep spec was over-constrained.** "Returns exactly 2 lines" underestimated — docstring cross-refs + log-message text mentions of `maybe_warm_load_vector_model` inflated the count to 5. Intent ("one production call site") was satisfied but wording was wrong. Flagged by BOTH R1 Codex and R1 Sonnet; R3 noted as pre-known. No code action.

## Skill Patches (L1-L3)

### L1 — Commit-count in doc commits is self-referential (extends cycle-25 L3)

Cycle-25 L3 said "every R1 fix commit in Step 14 MUST re-run the count snippet and update docs atomically with the fix." Implicit in this: the commit being written IS one of the commits counted. So when the count is claimed at commit-write time, arithmetic is:

```python
count_for_commit_message = len(git_log_oneline_output) + 1  # the commit IS itself one of them
```

Cycle 26 evidence: after the R1-fix commit landed, `git log --oneline origin/main..HEAD | wc -l` returned 6. I wrote "6 commits" in CHANGELOG as part of the same R1-fix commit. But the R2 doc-drift-fix commit was not yet written — when it landed and I re-checked, actual was 7. The off-by-one was because the count-claim commit is the tail of the range.

**Refined rule.** When writing a commit that contains a count claim about the branch itself, add +1 to the `git log --oneline origin/main..HEAD | wc -l` output. Alternatively, leave the count as `+TBD` in Step-12 and backfill post-merge (cycle-25 L3 alternative path). For R1/R2/R3 fix commits, the +1 rule is simpler.

### L2 — CLAUDE.md has multiple test-count sites; grep the WHOLE file before doc updates

Cycle 26 refreshed the Implementation Status line (line 33) but missed the Testing section line (line 191). Both reference the full-suite count in different framings:
- Line 33: "Latest full-suite count: N tests across M test files; last full run was P passed + Q skipped".
- Line 191: "current full suite: N tests across M test files; last full run was P passed + Q skipped".

Same numbers, two sites. R2 Codex caught the miss.

**Rule:** before committing a Step-12 doc update OR any R1/R2 fix commit that touches test counts, run:

```bash
rg -n "full[- ]suite|\d{3,}\s+tests|\d{3,}\s+passed" CLAUDE.md
```

Every match site must reflect the current count. The grep pattern is sticky across narrative framings (Implementation Status / Testing / Current Shipped Phases / README). If a new narrative site is added in a future cycle, the grep still catches it.

**Self-check addition to Step 12 Codex prompt:**  "After updating test counts in CHANGELOG / CHANGELOG-history / CLAUDE.md, run `rg -n 'full[- ]suite\|\\d{3,}\\s+tests\\|\\d{3,}\\s+passed' CLAUDE.md` and verify every hit site is current."

### L3 — CONDITION grep specs must target call shape, not text matches

Cycle 26 CONDITION 9 said: `rg 'maybe_warm_load_vector_model' src/` returns exactly 2 lines. Actual count was 5 — docstring cross-ref in `embeddings.py:350` ("Consider warm-load on startup via :func:`maybe_warm_load_vector_model`"), log-message string in `embeddings.py:373` ("...maybe_warm_load_vector_model(wiki_dir)..."), import at `mcp/__init__.py:77`, call at `mcp/__init__.py:79`, and definition at `embeddings.py:112`. The INTENT ("one production call site") was satisfied; the GREP SPEC was over-constrained.

**Rule:** when a CONDITION wants to enforce "single call site" or "N callers exactly", specify the grep as call-shape not text-shape:

```bash
# Over-constrained (matches docstrings, log text, imports):
rg 'maybe_warm_load_vector_model' src/

# Call-shape (matches actual function invocations only):
rg '^\s*maybe_warm_load_vector_model\(' src/  # call at statement start
rg '=\s*maybe_warm_load_vector_model\(' src/  # assignment from call
rg '\b\w*\s*=\s*maybe_warm_load_vector_model\(' src/  # combined
```

Alternative: Python AST-walk via a one-off script that counts `ast.Call` nodes with matching `.func.id`:

```python
import ast
tree = ast.parse(source)
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'maybe_warm_load_vector_model']
```

**Self-check addition to Step 5 decision-gate prompt:** "For any CONDITION that enforces 'single caller' / 'N call sites', specify the grep pattern to target CALL-SHAPE (opening paren after the name) not TEXT-SHAPE (bare name). Text-shape greps inflate on docstring cross-refs + log messages + imports and produce false failures in CI-gate scripts."

## Metrics

- **Cycle wall-clock time:** ~4h from invocation to merge (including ~2x 4-min wakeup budgets for parallel design-eval + PR-review subagents).
- **Primary-session vs subagent time ratio:** Primary ~65% (plan + impl + R1/R2 fixes + docs); Subagents ~35% (threat model, R1 Opus design-eval, R1 Codex design-eval, Step-5 decision gate, Step-8 plan gate, Step-11 security verify, R1 Codex PR review, R1 Sonnet PR review, R2 Codex verify, R3 Sonnet synthesis).
- **R1 → R3 pipeline yield:** 5 reviewers, 3 actionable findings (1 MAJOR + 2 count drifts), 1 pre-known NIT. R3 fired at 9 ACs per cycle-17 L4 secondary trigger (16 design-gate questions) — not wasted: confirmed the M1 divergent-fail trace at structural level that R1+R2 hadn't covered.
