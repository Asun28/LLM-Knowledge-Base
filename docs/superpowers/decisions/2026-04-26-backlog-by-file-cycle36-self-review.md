# Cycle 36 — Self-Review Scorecard + Skill Patches

**Date:** 2026-04-26
**Cycle:** 36 — Test + CI infrastructure hardening
**PR:** #50 (squash-merged at `82d8289`) + post-merge hotfix `7fc8cea`
**Verdict:** SHIPPED — closes 2 of 3 explicit cycle-36 BACKLOG follow-ups (strict pytest CI gate + cross-OS portability matrix partial); requirements split deferred to cycle 37 per Step-5 Q7=B.

## Scorecard

| Dimension | Grade | Note |
|---|---|---|
| Plan adherence | A- | Five-commit sequence vs. planned three (commit 4 ubuntu-only pivot, commit 5 Step-11 verify doc) — defensible runtime amendment with concrete cycle-37 BACKLOG. |
| Step-5 design coverage | A | All 22 design-gate questions resolved at Step 5. R2 Codex hang triggered fallback eval; both reviewers converged on same shape. |
| Test discipline | A | 10 new tests (`test_cycle36_ci_hardening.py`) all non-vacuous (divergent assertions per cycle-15 L2 / cycle-24 L4). Zero `inspect.getsource` signature-only tests. |
| CI cost discipline | C | **4 failed CI runs before pivot** triggered explicit user feedback ("endless CI failure job runs"). Lesson L1 below. |
| Subagent reliability | C | **Two subagent hangs** in one cycle: R2 Codex at Step 4 (12 min), R1 edge-case at Step 14 (12 min). Lesson L2 below. |
| Doc routing | A | Per-cycle archive in `CHANGELOG-history.md`; compact entry in `CHANGELOG.md`; `docs/reference/implementation-status.md` mirrored; BACKLOG drift entries filed for both Dependabot-only IDs. |
| Threat coverage | A | 9/9 threats addressed (6 IMPLEMENTED + 1 DEFERRED + 1 PARTIAL + 1 DOCUMENTED-DEFERRED); all deferred-promises cross-checked against BACKLOG entries (cycle-23 L3 verified). |
| Scope discipline | A | DROPPED windows-latest matrix mid-cycle when CI surfaced second hang (threading.py:355) — preferred deferral over chase. |

## Skill patches (cycle-36 lessons → feature-dev guidance)

### L1 — CI-cost discipline: probe ONE OS before adding the matrix

**Trigger:** Cycle 36 ran 4 failed CI runs in sequence (commit 1 probe → commit 2 marker fix → commit 3 strict-gate failure → commit 4 ubuntu pivot). User flagged this as "endless CI failure job runs."

**Why it happened:** Step-5 Q5=B planned cross-OS matrix `[ubuntu-latest, windows-latest]` to land in the SAME cycle as the strict-gate flip. When commit 3 surfaced a SECOND windows-latest hang post-cycle-23-skipif (threading.py:355 at ~position 1168), commit 4 had to revert to ubuntu-only — wasting commit 3's CI run.

**Fix-shape for future cycles:**

> When introducing a NEW CI dimension (cross-OS, cross-Python-version, cross-runner-tier), the SAME cycle MUST NOT also flip a strictness gate. Sequence them across 2 cycles:
>
> - **Cycle N:** strict-gate flip on the *known-good* OS only. `runs-on: ubuntu-latest`. Drop `continue-on-error`.
> - **Cycle N+1:** introduce the second OS as `strategy.matrix.os: [...]` with `continue-on-error: true` for the new OS for one cycle (probe), then drop in cycle N+2.
>
> Each new CI dimension gets its own probe → fix → strict-gate sequence. **Do not stack two new dimensions in one cycle.** Each failed CI run that lands on `main` (or even on a draft PR) is visible to the user as noise.

**Generalisation:** This is cycle-36 L1 = "CI cost ≠ implementation cost. The user sees CI failures even on draft PRs (Dependabot warnings, email notifications, GitHub status badges turn red). Minimise failed CI runs per cycle by sequencing CI-affecting changes one-dimension-at-a-time."

**Skill-patch target:** `feature-dev` Step 10 ("CI hard gate") guidance — add a "CI dimension count" pre-check: if the cycle adds >1 new CI dimension, split across multiple cycles.

### L2 — Subagent hang fallback: 10-min threshold + tool-use-error signal

**Trigger:** Two hangs in one cycle:
- R2 Codex at Step 4 design-eval: 12 min, no output. Likely hit `block-no-verify` hook on "verify" prose in companion script (cycle-22 L2 precedent).
- R1 edge-case Sonnet at Step 14: 12 min stuck reporting `<result>The shell is Windows-based with bash syntax but Python writes to Windows paths. Let me use the Write tool directly:</result>` — agent stuck on tool-use issue, not actually doing review work.

**Why it happened:** cycle-20 L4 already gives a 10-min hung-agent threshold. Cycle 36 followed it in both cases, but BOTH primary-session fallbacks took ~5 min anyway. Net overhead of dispatching: ~17 min vs. ~5 min direct. For tightly-scoped review work (R1 edge-case on 10 specific tests, R2 design eval on a fully-written design doc), primary-session is faster.

**Fix-shape:**

> **Tightly-scoped review work** (≤ 30 specific items: file count, test count, AC count, etc.) where the primary session ALREADY HOLDS the relevant context: skip subagent dispatch, do it primary-session. Threshold: if subagent prompt is < 1500 chars AND primary has all needed context, primary-session is faster.
>
> **Agent-stuck-on-tool-use signal:** When a subagent's progress report contains language like "Let me use the Write tool directly" or "shell is Windows-based but ... bash syntax" or "tool unavailable, falling back to ...", that's a tool-use issue, NOT review progress. Kill at 5 min (not 10) — the agent is not making meaningful progress.

**Generalisation:** This refines cycle-20 L4 — different hang signatures warrant different thresholds. "Tool-use stuck" = 5 min. "Silent hang" = 10 min. "API error retry" = 3 min.

**Skill-patch target:** `feature-dev` Step 14 PR review section — add a "primary-session R1 escape hatch" for cycles with < 25 ACs where Step 9 already passed comprehensive Codex+2nd-Codex review. R3 synthesis can also be skipped if R1 architect APPROVED with no blockers (cycle-27 L3 precedent confirmed by cycle 36).

### L3 — Post-merge doc-accuracy hotfix pattern

**Trigger:** Just before squash-merge, I committed a doc-accuracy fix to the PR branch (`c116ae9 docs(cycle 36): R1 reviews + post-pivot doc-accuracy fix`) — but the PR was merged externally at the previous HEAD `b8694b1` while my commit was being pushed. Net: the doc-fix landed on the cycle36 branch only; main got the squash without it. I cherry-picked to main as commit `7fc8cea`.

**Why it happened:** The squash-merge consumed the PR head as it existed at merge-trigger time. Any commits pushed after the squash trigger don't make it into the squash commit unless explicitly re-PR'd.

**Fix-shape:**

> Once the squash-merge is triggered (manually OR by auto-merge label), DO NOT push more commits to the PR branch. If a doc-accuracy issue surfaces post-trigger, queue it as a separate post-merge hotfix commit directly on `main` (precedent: `7739c7a docs(cycle 35 post-merge hotfix)`).
>
> Better: include the post-pivot doc-accuracy fix as part of the *Step 12 doc-update commit* BEFORE the PR review step (Step 14). Don't let the doc-fix land between Step 14 (PR review) and Step 15 (merge).

**Generalisation:** "Step 12 doc-updates must be COMPLETE before Step 14 review starts. Any doc-fix surfaced during Step 14 review is a Step-9 fix-task, not a Step-12 amend-task."

**Skill-patch target:** `feature-dev` Step 12 — add an explicit "post-pivot doc-accuracy" sub-step IF the cycle pivoted scope mid-implementation (e.g., commit 4 ubuntu-only pivot in cycle 36 invalidated docs that read "ubuntu+windows matrix"). Run a doc-grep for the OLD scope language and ensure all references reflect the post-pivot reality.

### L4 — Marker-mechanism orthogonality (positive validation)

**Validated pattern:** Cycle 36 shipped four marker mechanisms that compose orthogonally:
1. `skipif(CI=="true")` for cycle-23 multiprocessing test (env-var truthy at collection time)
2. `pytest-timeout = 120` (per-test runtime kill)
3. `kb.mcp.quality.WIKI_DIR` mirror-rebind monkeypatch (fixture-setup time)
4. `requires_real_api_key()` skipif (env-var prefix at collection time)

Each mechanism lives in a distinct dimension; none interferes with another. R1 architect verified this in §4 of the review.

**Why this matters:** Cycle 17 L1 surfaced cases where multiple test-infra changes coupled (monkeypatch-target enumeration). Cycle 36 demonstrates a clean counter-example: when the cycle requires multiple test-infra changes, prefer orthogonal mechanisms.

**Generalisation:** When shipping a test-infrastructure cycle, enumerate the mechanisms upfront and verify orthogonality. If two mechanisms touch the same test (e.g., a test gets BOTH `skipif(CI=="true")` AND `requires_real_api_key`), that's a coupling smell — at least one mechanism is misapplied.

**Skill-patch target:** `feature-dev` Step 4 design-eval R1 prompt — add a "marker-orthogonality check" requirement when the cycle introduces ≥ 2 new test-infra mechanisms.

### L5 — Dummy-key prefix gating (positive validation)

**Validated pattern:** `requires_real_api_key()` predicate gates SDK tests on `sk-ant-dummy-key-` prefix:

```python
_DUMMY_KEY_PREFIX = "sk-ant-dummy-key-"
def requires_real_api_key() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith(_DUMMY_KEY_PREFIX)
```

Cleaner than env-var-presence-only because:
- CI MUST set `ANTHROPIC_API_KEY` (other tests probe `os.environ` for it)
- But SDK-using tests should still skip (no real Anthropic key on CI)
- Prefix sentinel = "this is a fake key for non-SDK tests"

**Why this matters:** Cycle 24 L4 already noted that "test failures? check mocks/fixtures first" — but the deeper pattern is "use sentinel values to differentiate fake-vs-real credentials."

**Generalisation:** For any "is this real or fake X" predicate where the variable MUST be present:
- Define a `_FAKE_PREFIX = "..."` sentinel constant
- Predicate returns True iff `bool(value) and not value.startswith(_FAKE_PREFIX)`
- Pin the predicate with 4-5 behaviour tests (unset / fake-exact / fake-prefix / real-prefix / empty) per cycle-15 L2 / cycle-24 L4

**Skill-patch target:** No new skill text — this is a reusable Python pattern. Worth elevating to `docs/reference/conventions.md` if more than one cycle adopts it. Cycle-37 candidate for codification IF the requirements split (AC14-AC17) needs a similar predicate.

### L6 — Pivot-with-BACKLOG-entry over chase (positive validation)

**Validated pattern:** When commit 3 surfaced a SECOND windows-latest hang at threading.py:355 (~position 1168, post-cycle-23-skipif), the choice was:
- **(A)** Chase the second hang via 5+ debug commits on the PR (unbounded — Windows GHA spawn semantics differ from local)
- **(B)** Defer windows-latest to cycle-37 with a concrete BACKLOG fix-shape

Cycle 36 chose (B) at commit 4. R1 architect verified this in §4 of the review as "a clear win for (B)."

**Generalisation:** "When CI surfaces a NEW failure post-fix, the chase-vs-defer decision should bias toward defer if the cycle's PRIMARY deliverable is independent of the new failure." Cycle 36's primary deliverable was the strict-gate flip — that succeeded on ubuntu. The cross-OS matrix was a SECONDARY deliverable that surfaced an unbounded debugging cost.

**Skill-patch target:** `feature-dev` Step 9 implementation guidance — add an explicit "secondary-deliverable scope check" when CI failures surface post-fix on a non-primary deliverable.

### L7 — Threat-model deferred-promise check (cycle-23 L3 reaffirmed)

**Validated pattern:** Cycle 36 shipped 7 cycle-37 deferred-promises (windows matrix re-enable, GHA-Windows multiprocessing, mock_scan_llm POSIX leak, POSIX symlink security gap, TestExclusiveAtomicWrite POSIX, Dependabot drift on 2 GHSAs, Requirements split). The Step-11 security-verify doc cross-checked all 7 against BACKLOG entries — all 7 found.

**Why this matters:** Cycle-23 L3 mandated this check; cycle 36 ran it cleanly and the deferred-promise table is reproducible from a grep + cross-ref pass. No promises orphaned.

**Generalisation:** This pattern works. Continue running it at every Step 11 verify.

## Cycle-37 candidates filed at BACKLOG

Per cycle-23 L3 deferred-promise check, all 7 cycle-37 candidates are in `BACKLOG.md` Phase 4.5/4.6:
1. windows-latest CI matrix re-enable (L1 + commit-4 pivot)
2. GHA-Windows multiprocessing spawn investigation (T8)
3. `mock_scan_llm` POSIX reload-leak investigation (T7 / 10 SDK tests)
4. POSIX symlink security gap in `pair_page_with_sources` (T6 — production fix)
5. TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour (T6)
6. Dependabot pip-audit drift on `GHSA-r75f-5x8p-qvmc` + `GHSA-v4p8-mg3p-g94g` (T5)
7. Requirements split (AC14-AC17 — Q7=B deferral)

## Summary

Cycle 36 shipped its primary deliverable (strict CI gate on ubuntu) cleanly with one defensible mid-cycle pivot. CI-cost discipline and subagent-hang patterns are the two operational lessons that warrant feature-dev skill patches. The four marker mechanisms compose orthogonally — a positive pattern worth preserving.

**Net:** 7 cycle-36 lessons (L1-L7), 3 actionable skill-patch targets (L1 Step 10 dimension-count, L2 Step 14 primary-session R1 escape, L3 Step 12 post-pivot doc-accuracy sub-step), 4 positive-pattern validations (L4-L7).
