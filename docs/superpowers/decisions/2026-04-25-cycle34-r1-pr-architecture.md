# Cycle 34 — R1 PR Architecture Review

**Date:** 2026-04-25 · **Cycle:** 34 · **Reviewer:** Opus 4.7 (1M) · R1 (architecture / contracts / integration / correctness)
**Branch:** `feat/backlog-by-file-cycle34` · 9 commits · 2941 tests / 254 files · ruff clean · format clean.
**Inputs read:** design.md (57 ACs / 18 file groups / 5 R1 AMENDs / NEW-Q11-25 + Q1-Q10 resolutions), threat-model.md (14 threats / 25-row checklist + 11 cycle-34 deltas in design), plan.md (Step-7+8 + plan-gate inline), full diff `main..HEAD`, `tests/test_cycle34_release_hygiene.py` (18 fixture-free tests).

---

## Analysis

The cycle 34 batch is a clean, well-scoped release-hygiene cycle that closes 8 P0/P1 ship-blocker findings from the comprehensive review. Production code changes are minimal and surgical: `pyproject.toml` packaging metadata, `__init__.py` version, `config.py` `.pdf` removal, `pipeline.py` rejection-message rewrite. New artifacts (`SECURITY.md`, `.github/workflows/ci.yml`) carry meaningful trust-boundary content with disciplined least-privilege design (top-level `permissions: read-all`, no `secrets.*`, no `pull_request_target`, fork-PR-safe). The 18-test regression suite at `tests/test_cycle34_release_hygiene.py` is fixture-free per cycle-19 L2 safety and exercises real production contracts: every AC37-AC57 test imports the on-disk file or static-frozen module surface, so each test traces directly to a request and would FAIL under revert. Full suite passes (2930 + 10 skipped + 1 xfailed = 2941 collected) and ruff/format are clean. Step-9 DESIGN-AMENDs (AC4e DEFERRED, AC49 DROPPED with AC56 test-anchor retention) are documented transparently per cycle-17 L3.

The CI workflow walk-through holds up under execution-order analysis: `pip install -e '.[dev]'` runs first (which installs `pip-audit>=2.10`, `build>=1.2`, `twine>=5.0` per AC2 cycle-34 dev-extra), then the dedicated `pip install build twine pip-audit` step (AC50 — defense-in-depth in case future cycles drop them from `[dev]`), then ruff, then collect-only smoke, then full pytest, then `pip check` (with `continue-on-error: true` correctly indented at the STEP level only, not propagating), then `pip-audit -r requirements.txt --ignore-vuln=...` with all four documented narrow-role CVE IDs matching SECURITY.md 1:1, then `python -m build && twine check dist/*`. The boot-lean AC56 test correctly exercises the contract — under hypothetical revert (`from kb.lint.augment import run_augment` at `cli.py` module-top instead of inside `lint()`), `kb.lint.augment` would load `kb.lint.fetcher` + `httpx` + `httpcore` + `trafilatura` (still module-top in `augment.py:30-31`), and the subprocess probe asserts `LEAKS: []` would fail. I REPL-verified this: hypothetical-revert simulation produces `LEAKS UNDER HYPOTHETICAL REVERT: ['httpcore', 'httpx', 'kb.lint.fetcher', 'trafilatura']` — test correctly anchors. Same-class peer scan on README confirms no other "No vectors" / "no chunks" / "Structure, not chunks" stale phrases survive (the remaining `chunks` mentions are RAG-vs-this-project contrast text, intentional). Phase narrative test counts at lines 349/362/393/394 are explicitly out-of-scope per design.md same-class peer table lines 609-611. Architecture diagrams correctly stay at `v0.10.0` (AC4e deferred per NEW-Q15 fallback) with BACKLOG entry filed at `BACKLOG.md:170`.

There are no BLOCKERs. Three MINOR findings: (1) the threat-model file shipped with Step-5 amendments NOT folded back into rows 11/14/22 — those still say `git ls-files` (degenerate per NEW-Q19) and pre-`-r requirements.txt` text; the design.md has an "AMENDED rows" delta table, but a future reader landing on `2026-04-25-cycle34-threat-model.md` directly sees the un-amended check-list (cycle-19 L4 audit-doc drift class). (2) NEW-Q20 / threat-model row 36 requires the PR description to "reference a `claude4.6-deletion-diff` artifact (or include the diff inline)" — the deletion-diff was created at `.data/cycle-34/claude4.6-deletion-diff.txt` (gitignored), but neither the PR description (verified via `gh pr view`) nor the CHANGELOG-history mentions any link / reference / inline diff in the PR body itself. The CHANGELOG mentions the artifact location but the PR description does not link to it. (3) Threat-model T2 row 23 + descriptions on lines 71/73 still reference `actions/checkout@v4` and `actions/setup-python@v5` whereas the workflow shipped with `@v6` (Step-6 Context7 amendment) — same audit-doc drift class. None of these change shipped behaviour, but R1's first-position cycle-19 L4 hat surfaces them.

## Verdict

**APPROVE-WITH-CONDITIONS.**

Production code is correct, tests anchor real contracts, CI workflow is least-privilege and execution-order-correct, AC4e/AC49 narrowings are transparent. Three MINOR audit-doc drift findings (threat-model row text vs shipped state, PR description missing claude4.6-deletion-diff reference) are recoverable inline before merge or in a follow-up doc-only commit.

## Findings

### MINOR-1 — Threat-model rows 11, 14, 22, 23 + lines 23/71/73 still carry pre-amendment text

**File:** `docs/superpowers/decisions/2026-04-25-cycle34-threat-model.md:117, 133, 245, 248, 256, 23, 71, 73`

**Reasoning:** design.md §"Step-11 verification delta" table at lines 632-638 documents that row 11 (T7 deletion verification) was AMENDED to `test ! -f findings.md && ...` (NEW-Q19), and row 22 (AC10-15) was AMENDED to assert `pip-audit -r requirements.txt` (NEW-Q17). The threat-model file itself shipped without those amendments folded back in:
- Row 11 (`threat-model.md:245`) still says `git ls-files findings.md ... returns empty` (degenerate — passes pre-cycle AND post-cycle).
- Row 14 (`threat-model.md:248`) still says `git show HEAD:claude4.6.md 2>/dev/null returns empty`. This row IS still meaningful (untracked file always returns empty; `test ! -f` is the test-anchor) — minor pedantic concern.
- Row 22 (`threat-model.md:256`) lists `pip-audit (with all 4 --ignore-vuln)` without the `-r requirements.txt` flag.
- Lines 23, 71, 73 reference `actions/checkout@v4` / `actions/setup-python@v5` — Step-6 Context7 amended both to `@v6`.

A future reader landing on `threat-model.md` (e.g., during a cycle-N+1 retrospective or a new-developer onboarding) sees the pre-amendment text without realising design.md supersedes it. This is the cycle-19 L4 audit-doc drift class that R1 is explicitly required to surface.

**Fix:** add a one-line amendment banner at the top of `threat-model.md` after line 6: *"Note: design.md `Step-11 verification delta` table supersedes rows 11 and 22 below; actions pinning was bumped @v4/@v5 → @v6 at Step-6 Context7."* Or, preferred, fold the amendments inline (replace row 11 text with `test ! -f findings.md && ...`; replace row 22 with `pip-audit -r requirements.txt --ignore-vuln=...`; bump @v4/@v5 → @v6 at lines 23/71/73). Doc-only commit; no test impact.

### MINOR-2 — PR description does not reference claude4.6-deletion-diff artifact (NEW-Q20 / threat-model row 36)

**File:** PR #48 body (verified via `gh pr view`)

**Reasoning:** design.md condition 10 at lines 466-467 mandates: *"PR description MUST include or link to a diff artifact (`docs/reviews/2026-04-25-claude4.6-deletion-diff.txt` or similar) showing what was deleted."* threat-model design-delta row 36 (design.md:653) confirms the same. The deletion-diff was generated at `.data/cycle-34/claude4.6-deletion-diff.txt` (54 KB, gitignored — confirmed via `ls .data/cycle-34/`). CHANGELOG-history.md cluster G mentions the artifact at line 30 but the PR body itself (which is what reviewers see in the GitHub UI) makes no reference: `gh pr view --json body` returns no occurrence of "claude4.6-deletion" or "deletion-diff". Plan.md §TASK 13 says "git add ... + the deletion-diff artifact" but `git status` is clean and the artifact is gitignored — it was NOT committed.

The risk is small (claude4.6.md was an untracked snapshot of older CLAUDE.md, novel-content review already performed), but the contract was specifically designed to provide auditability for a 40 KB deletion and that contract is unsatisfied.

**Fix:** edit PR description via `gh pr edit 48 --body` to add a one-line reference: *"`claude4.6.md` was an untracked snapshot of older CLAUDE.md; pre-deletion diff retained at `.data/cycle-34/claude4.6-deletion-diff.txt` (gitignored — local-only audit trail, no novel content found)."* Or, alternative-form, commit the diff to `docs/reviews/2026-04-25-claude4.6-deletion-diff.txt` (the originally-designed location) so it lands in the PR diff and is reviewable in the GitHub UI. The latter satisfies the original design contract more cleanly.

### MINOR-3 — CHANGELOG arithmetic: "53 ACs delivered out of 57 designed" — count off-by-one

**File:** `CHANGELOG.md:33`, `CHANGELOG-history.md:14`

**Reasoning:** Per Step-9 transcript:
- AC4e DEFERRED (counts as 1 not-delivered).
- AC49 DROPPED with AC56 test-anchor retention (counts as 1 not-delivered, but AC56 IS delivered).
- AC55 (architecture-diagram version regression test) intentionally deferred per test-file docstring lines 7-10 (counts as 1 not-delivered).

That's 3 not-delivered, leaving 57 - 3 = 54 delivered, not 53. The number 53 may be miscounting AC50 (which IS in the workflow at line 38) or double-counting AC4e somewhere. Minor narrative drift only; not a blocker.

**Fix:** verify the count and update CHANGELOG.md + CHANGELOG-history.md to "54 ACs delivered out of 57 designed" (or document the specific 4 that were not delivered explicitly so the arithmetic is auditable).

### NIT-1 — `test_cycle34_release_hygiene.py:8-10` references "AC55" intentional-deferral note that is not in the test file

**File:** `tests/test_cycle34_release_hygiene.py:8-10`

**Reasoning:** the docstring says *"AC55 (architecture-diagram version regression) is intentionally deferred per the cycle-34 design's NEW-Q15 fallback"*. Verified: there is no `test_architecture_diagram_html_version_is_0_11_0` function in the file (matches the deferral). However, this is a forward-looking comment rather than a present-state assertion — when AC4e ships in cycle 35, the test docstring should be updated. Low priority.

**Fix:** none required for cycle 34. Add a TODO marker: `# TODO(cycle 35): add test_architecture_diagram_html_version_is_0_11_0 when AC4e closes.`

### NIT-2 — `pyproject.toml:43-46` `[dev]` extra includes `pip-audit>=2.10`, `build>=1.2`, `twine>=5.0` — duplicating the AC50 dedicated install step

**File:** `pyproject.toml:43-46` + `.github/workflows/ci.yml:38-43`

**Reasoning:** Design Q13/AC50 explicitly chose *"dedicated `pip install build twine pip-audit` step in CI"* over Q13-A "bloat `[dev]` with these tools" because: *"build, twine, and pip-audit are CI-tooling, not developer-tooling. Putting them in `[dev]` forces every contributor running `pip install -e '.[dev]'` to also pull these — they're not needed for `pytest` or `ruff`."* But the shipped `[dev]` extra includes ALL THREE: `pip-audit>=2.10`, `build>=1.2`, `twine>=5.0`. So contributors running `pip install -e '.[dev]'` DO pull them — the rationale that motivated AC50 is no longer enforced. The dedicated step at `ci.yml:38-43` is now redundant (with a self-justifying comment "redundant install ensures it's available even if a future cycle removes it from `[dev]`").

This is a contract drift between design intent and shipped state — both ways work, but the design rationale is undermined. Minor, non-blocking. The shipped state is actually MORE convenient (one install command in CI; tools available locally too); just inconsistent with what the design.md says.

**Fix:** either (a) remove `build>=1.2`, `twine>=5.0`, `pip-audit>=2.10` from `[dev]` so the AC50 step becomes load-bearing again (matches design Q13 rationale); or (b) leave both and update the design-rationale comment in CHANGELOG-history.md to acknowledge the drift was intentional ("[dev] now includes all CI tools because contributors find it convenient; AC50 step is defense-in-depth"). Either form closes the audit gap.

---

## Audit-doc drift checks (cycle-19 L4 first-position)

| Check | Verdict | Detail |
|---|---|---|
| **Threat-model row 11 (T7) reflects shipped `test ! -f` semantics?** | FAIL | Still reads `git ls-files ... returns empty`. Amendment lives in design.md §"Step-11 verification delta" but the threat-model file itself was not updated. MINOR-1. |
| **Threat-model row 22 (AC10-15) reflects `pip-audit -r requirements.txt`?** | FAIL | Reads `pip-audit (with all 4 --ignore-vuln)` without `-r`. Same MINOR-1. |
| **Threat-model lines 23/71/73 reflect Step-6 Context7 @v6 bump?** | FAIL | Still references `actions/checkout@v4` / `actions/setup-python@v5`. Same MINOR-1. |
| **Design.md AC count matches CHANGELOG.md Quick Reference?** | PARTIAL FAIL | Design.md says "Final AC count: 57"; CHANGELOG.md says "53 AC delivered (out of 57 designed)" — but actual delivered count appears to be 54 not 53 (AC4e + AC49 + AC55 = 3 not-delivered). MINOR-3. |
| **CHANGELOG.md narrative test count matches actual `pytest --collect-only`?** | PASS | CHANGELOG says 2941 collected; actual `pytest --collect-only -q | tail -1` returns `2941 tests collected`. CLAUDE.md `:7` matches. |
| **CHANGELOG.md narrative commit count matches `git log --oneline main..HEAD`?** | PASS-WITH-NOTE | CHANGELOG says "+TBD commits (backfill post-merge per cycle-15 L4 + cycle-30 L1)"; actual is 9 commits. The TBD is intentional (post-merge backfill) per project convention but is forward-looking; cycle-15 L4 backfill should land within 1 commit after merge to close the loop. |
| **PR description references claude4.6-deletion-diff artifact (NEW-Q20 / threat-model row 36)?** | FAIL | PR body has no reference to the artifact. CHANGELOG-history mentions `.data/cycle-34/claude4.6-deletion-diff.txt` but the PR description (which is what GitHub-UI reviewers see) does not. MINOR-2. |
| **Same-class peer scan on README — no other stale "No vectors / chunks" phrases?** | PASS | All literal `"No vectors"` / `"No chunking"` / `"Structure, not chunks"` removed. Remaining `chunks` mentions at lines 27/33/35 are RAG-contrast text (intentional; opposite-side-of-comparison column). |
| **Same-class peer scan on README — no other stale `v0.10.0` badge?** | PASS | Badge at line 11 is `v0.11.0`. Historical phase summaries at lines 373/394 reference v0.10.0 in PHASE 4 narrative — explicitly out-of-scope per design.md:609-611. |
| **Architecture diagrams + zh-CN badge correctly UNTOUCHED (Q8 + AC4e deferred)?** | PASS | `architecture-diagram.html:501` + `architecture-diagram-detailed.html:398` both still show `v0.10.0` (deferred per AC4e fallback); `README.zh-CN.md:8` badge still shows `v0.10.0` (deferred per Q8); BACKLOG.md:170 entry filed for cycle 35; AC23.5 canonical-note added at zh-CN lines 5-7. |
| **CI workflow execution order — `pip install -e '.[dev]'` BEFORE AC14 + AC15?** | PASS | Step 3 installs `[dev]` (which includes `pip-audit>=2.10`, `build>=1.2`, `twine>=5.0`), step 4 redundantly installs `build twine pip-audit`. AC14 (pip-audit) at step 9, AC15 (build/twine) at step 10. Tools available before need. |
| **`continue-on-error: true` indentation matches step-level only?** | PASS | YAML indentation at `ci.yml:60` aligns with `run:` at `:59`, NOT with `steps:` at `:25`. Verified: parsed YAML shows `continue-on-error: true` is a key on the pip-check step's dict only. Other steps do NOT inherit the directive. |
| **AC57 `-r requirements.txt` regression test correct + production aligned?** | PASS | Test at `test_cycle34_release_hygiene.py:281-301` parses `ci.yml`, finds `pip-audit ` substring, locates the step block, asserts `-r requirements.txt` in step body. Workflow at `ci.yml:68` ships `pip-audit -r requirements.txt`. Test passes. Note: the test only checks for the FLAG; per spec the at-CI-time exit code is enforced by the workflow run itself, not by the regression test (correct division of responsibility). |
| **AC56 boot-lean test would FAIL under hypothetical revert?** | PASS | REPL-verified: `import kb.lint.augment` (the hypothetical-revert state where `cli.py` module-top imports it) loads `httpx`, `httpcore`, `trafilatura`, `kb.lint.fetcher` because `augment.py:21-31` still has module-top fetcher imports. Test correctly anchors the contract — AC49 production fix was DROPPED but the BOOT-LEAN INVARIANT itself is enforced by `cli.py:354` keeping the augment import inside the function body. If a future cycle moves `from kb.lint.augment import run_augment` to module top, AC56 fails. Cycle-15 L2 DROP-with-test-anchor pattern correctly applied. |

---

End of cycle-34 R1 PR architecture review.
