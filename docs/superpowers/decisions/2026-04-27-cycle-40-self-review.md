# Cycle 40 — Self-review scorecard + skill-patch lessons

**Date:** 2026-04-27
**Branch:** `cycle-40-self-review` (this PR)
**Implementation PR:** #56 merged at SHA `ad6952b` (Cycle 40 — Backlog hygiene + freeze-and-fold continuation + dep-drift re-verification)
**Predecessor self-review:** `2026-04-27-cycle-39-self-review.md` (PR #54)

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model body (skip-eligible) + dep-CVE baseline | yes | yes | pip 26.1 published TODAY (cycle day) but advisory metadata not yet updated to confirm fix — see C40-L1 below |
| 3 — Brainstorming | skipped per skill rule (pure hygiene, no design space) | n/a | — |
| 4 — Design eval | skipped per skill rule (trivial mechanical work) | n/a | — |
| 5 — Design decision gate (Opus subagent) | yes | yes | Opus subagent returned 15 binding CONDITIONS for 11 ACs with HIGH confidence on all 6 questions — exceptionally thorough due to the explicit "verify host file shape via grep BEFORE answering" prompt addition (cycle-15 L1 in action) |
| 6 — Context7 | skipped per skill rule (no third-party libs) | n/a | — |
| 7 — Implementation plan | yes | yes | — |
| 8 — Plan gate | yes (self-passed per cycle-21 L1) | yes | — |
| 9 — Implementation (3 folds + 1 BACKLOG marker pass + 1 doc-sync) | yes | yes | bash `/tmp/c40-litellm/` path mismatch fired despite cycle-22 L1 being a known footgun — see C40-L4 below; also TASK 8 ruff format flagged conftest.py despite cycle 40 not touching it (per C35-L7 — auto-normalized by git autocrlf, no commit needed) |
| 9.5 — Simplify pass | skipped per skill rule (zero src changes; well under 50 LoC) | n/a | — |
| 10 — CI hard gate (full pytest + ruff) | yes | yes | conftest.py CRLF normalization (C35-L7 confirmed; see Step 9 row) |
| 11 — Security verify + PR-CVE diff | yes | yes | brief verify per "Step 2 body skipped" rule; all 6 threat-model checklist items verified inline |
| 11.5 — Existing-CVE patch (re-verification) | yes | yes | pip 26.1 case (see C40-L2 below) |
| 12 — Doc update (CHANGELOG + history + CLAUDE + reference + README + decision docs) | yes | yes | C26-L2 + C39-L3 grep list covered all 4 narrative sites; no missed sites |
| 13 — Branch finalise + PR | yes | yes | — |
| 14 — PR review (R1 DeepSeek direct CLI + R2 codex:codex-rescue agent) | yes | no | **R1 false-positive BLOCKER** on `kb_lint` import that was actually pre-existing — see C40-L1 below |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes | bash `/tmp/c40-alerts-postmerge.json` mistake fired again (third time per cycle 40 alone) — see C40-L4 |
| 16 — Self-review + skill patch (this PR) | in progress | yes | — |

## Cycle-40 lesson candidates (C40-L1..L5)

### C40-L1 — Diff-only review prompts hallucinate "missing" pre-existing context (refines cycle-39 L1 + cycle-12 L2)

**Rule:** PR-review prompts handed to DeepSeek/Codex/any non-Anthropic reviewer that include only `git diff main...HEAD` will sometimes confidently flag "missing imports" / "missing function definitions" / "broken references" that ARE actually present in the unchanged surrounding context — because diff hunks only show ±3 lines around modifications, and pre-existing file-top imports often sit > 3 lines from any modification. Mitigation: include `git show HEAD:<file>` for each modified file (or at least the top 30 lines covering imports + module-level fixtures) ALONGSIDE the diff. Alternatively, instruct the reviewer in prompt: "Imports may be in unchanged context not shown in diff hunks; before flagging a missing-symbol blocker, confirm the symbol is not in the rest of the file via subsequent file read."

**Why:** Cycle 40 R1 DeepSeek (direct CLI) flagged a BLOCKER that `tests/test_mcp_browse_health.py` was missing `from kb.mcp.health import kb_lint` — when in fact line 20 (`from kb.mcp.health import kb_evolve, kb_lint`) was PRE-EXISTING. R1 saw the 4 NEW imports added at line 9-12 and inferred the rest of the import block from the diff hunks, missing the unchanged line 20. The "blocker" was empirically refuted by `pytest tests/test_mcp_browse_health.py::TestSanitizeErrorStrAtMCPBoundary -v` returning 5/5 PASSED. Cost: ~10 minutes investigating + composing the refutation comment + posting to PR.

**How to apply:** Future Step 14 R1/R2 dispatches MUST include either (a) a `git show HEAD:<file>` snippet for each MODIFIED-file's top-30-lines OR (b) an explicit prompt instruction "imports may be in unchanged context — confirm absence by re-reading the post-fix file before flagging missing-symbol blockers." This generalizes cycle-39 L1's wrapper-fabrication-risk lesson: even direct-CLI DeepSeek without a Haiku wrapper can hallucinate when diff context is dense AND the relevant symbol lives outside the visible hunk window. Cycle-15 L2's "run the actual tests to verify behavior" caught it post-hoc — make this catch UPFRONT next cycle.

**Self-check:** When dispatching R1 for a cycle that adds new imports OR new function-body references to symbols, the prompt must explicitly include: "BEFORE flagging any 'missing X' blocker, run `cat <file>` (or read the file in the repo) and confirm X is genuinely absent. Diff hunks may not show pre-existing imports."

---

### C40-L2 — pip-audit `fix_versions=[]` and GHSA `patched_versions: null` are independent signals; both must be checked (refines cycle-22 L4)

**Rule:** When re-verifying CVE state during Step 11.5, an empty `fix_versions` from pip-audit does NOT necessarily mean "no upstream fix exists" — it means "the GHSA advisory's `patched_versions` field is null." If a NEW LATEST version of the package has been released SINCE the advisory was filed but the advisory metadata hasn't been updated, pip-audit will continue to show `fix_versions=[]` even though the new version may or may not patch the vulnerability. Conservative posture: do NOT bump the pin until the advisory or vendor confirms the new version patches the CVE — but DOCUMENT both signals in the BACKLOG entry so the next cycle can re-check.

**Why:** Cycle 40 AC7 found that pip 26.1 was published to PyPI on cycle day (2026-04-27) but the GHSA-58qw-9mgm-455v advisory still listed `vulnerable_version_range: <=26.0.1` AND `patched_versions: null`. pip-audit on the live env continued to emit `fix_versions=[]`. This is a sub-pattern of cycle-22 L4 (cross-cycle CVE arrival) but INVERTED: instead of a new advisory landing, a new dep release landed but the advisory wasn't updated. If cycle 40 had naively interpreted `fix_versions=[]` as "still no patch" without checking for new releases, the documentation would have been stale; if it had naively bumped pin to 26.1 because "26.1 is newer", the bump would have been speculative (no advisory confirmation that 26.1 patches the CVE).

**How to apply:** Step 11.5 re-verification scripts MUST probe BOTH `pip-audit --format=json` (for `fix_versions`) AND `pip index versions <pkg>` (for the latest published version). When latest > vulnerable_version_range upper bound BUT advisory's `patched_versions` is still null, document the disjunction in BACKLOG explicitly: `"<pkg> X.Y.Z published on <date> but advisory metadata not yet updated; conservative posture per cycle-22 L4 — no pin bump until advisory confirms."`

**Self-check:** for any BACKLOG entry citing `pip-audit` empty-fix_versions, re-verify with `pip index versions <pkg>` AND `gh api /advisories/<GHSA>`. If `pip index` shows a newer version than `vulnerable_version_range` upper bound, the BACKLOG entry MUST address whether the new version is a confirmed patch or merely a not-yet-evaluated release.

---

### C40-L3 — Test fold of KNOWN-WEAK tests should immediately file cycle-N+1 upgrade candidate (refines cycle-15 L2 + cycle-23 L2 + feedback_inspect_source_tests)

**Rule:** When a freeze-and-fold cycle migrates a test that's KNOWN to be weak (vacuous-grep, signature-only, isolation-stub, docstring-introspection), the migration MUST file a follow-up cycle-N+1 candidate to upgrade the test — DO NOT silently propagate weak contracts into the canonical file. The fold preserves the test BODY for legacy-coverage continuity, but the weakness becomes harder to spot once buried in a 300-line canonical file vs. a 13-line cycle-tagged file.

**Why:** Cycle 40 AC2 test 1 (`test_detect_source_drift_docstring_documents_deletion_pruning_persistence` — folded from cycle10_linker.py to test_compile.py) is a docstring-grep test: `assert "deletion-pruning" in detect_source_drift.__doc__`. R2 Codex correctly identified this as the same vacuous pattern flagged in `feedback_inspect_source_tests.md` — reverting the FUNCTION'S BEHAVIOR would not fail the test; only deleting the docstring strings would. R2 also correctly noted "carry-forward, not introduced by the fold." Cycle 40 chose accept-now-and-file-future-cycle, but in practice "filed as future cycle candidate" lives in a PR comment — not in BACKLOG.md as a tracked entry. That risks the upgrade never happening because next cycle's BACKLOG sweep won't see it.

**How to apply:** When Step 14 R1/R2 reviewer flags a folded test as carry-forward-weak, the cycle MUST add an explicit BACKLOG.md entry under `### MEDIUM` (or appropriate severity) with format: `tests/<canonical>::<test_name>` upgrade candidate (cycle-N fold from <source>): <weakness pattern> — <upgrade approach>`. Posting in PR comments alone is INSUFFICIENT because next cycle's BACKLOG-driven planning won't see it.

**Self-check:** before merging a fold cycle's PR, grep the PR review comments for "carry-forward" / "vacuous" / "signature-only" / "weak" — for each match, verify there's a corresponding BACKLOG.md entry with the upgrade approach.

**Cycle 40 BACKLOG addition (post-merge follow-up):** filed `tests/test_compile.py::test_detect_source_drift_docstring_documents_deletion_pruning_persistence` upgrade candidate per R2 Codex finding — extract a helper that calls `detect_source_drift` with `save_hashes=False` on a fixture and verifies no manifest write occurs, replacing the docstring assert.

---

### C40-L4 — Bash `/tmp/` paths fail on Windows when read by Python (cycle-22 L1 fired THREE times in cycle 40 alone — needs harder enforcement)

**Rule:** ANY pip-audit / dependabot-baseline / wheel-inspection / artifact written from bash and read by Python on Windows MUST use a project-relative path (`.data/cycle-N/`). The bash `/tmp/foo` syntax IS aliased to `C:\Users\<user>\AppData\Local\Temp\foo` by the shell, but Python.exe interprets `/tmp/foo` as the literal POSIX path which DOESN'T EXIST on Windows. Cycle-22 L1 documented this; cycle-40 fired the SAME footgun three times in one cycle (litellm wheel extraction at AC6, late-arrival CVE check at Step 15, plus the file already saved to bash-tmp under cycle-40-litellm/).

**Why:** Cycle-22 L1 was already a documented lesson with explicit guidance: *"use PROJECT-RELATIVE paths (`.data/cycle-<N>/`) for ALL cross-tool artifact sinks during Step 02 + Step 11 on Windows."* Despite knowing this, cycle 40 reflexively used `/tmp/c40-litellm/` for the wheel download (worked accidentally because `pip download` + `unzip` both ran in bash), then `/tmp/c40-alerts-postmerge.json` for the postmerge alert check (FAILED — Python couldn't open the bash-aliased path). The footgun keeps firing because muscle-memory `/tmp/` is faster to type than `.data/cycle-40/`. The cycle-22 L1 lesson is correct but apparently insufficient — needs a stronger enforcement mechanism.

**How to apply:** Add a pre-Step-2 + pre-Step-15 self-check: BEFORE running any `gh api .../alerts | tee ...` OR `pip download ... -d ...` OR `pip-audit ... > ...`, the destination path MUST start with `.data/cycle-<N>/` (and the directory must exist via `mkdir -p .data/cycle-<N>`). Bash `/tmp/` paths are FORBIDDEN for cross-tool artifacts. Reinforce: even when an artifact is "throwaway" (just for inspection), use `.data/cycle-N/` so it shows in `git status` and gets cleaned via `.gitignore`.

**Self-check:** grep cycle's bash commands for `/tmp/c<N>` patterns; rewrite each as `.data/cycle-<N>/`. The `.data/cycle-<N>/` directory should be created at Step 2 and reused throughout the cycle.

---

### C40-L5 — Step 5 design gate prompts MUST mandate host-file shape grep BEFORE answering (codifies cycle-15 L1 application)

**Rule:** Step 5 Opus-subagent design-gate prompts that ask questions like "should we use a class or bare functions?" MUST explicitly require the subagent to grep the CANDIDATE TARGET FILE's existing structure (does it use classes? bare functions? section comments? specific imports?) BEFORE answering — the answer's quality depends entirely on knowing host shape. Without the explicit instruction, Opus may answer based on "general best practice" rather than host-shape match.

**Why:** Cycle 40's Step 5 design gate produced exceptionally clean answers (HIGH confidence on all 6 questions) because the prompt embedded explicit host-file inspection results: "current `test_mcp_browse_health.py` uses bare functions throughout with section comments — no classes" / "current `test_compile.py` uses bare functions exclusively with no existing classes" etc. Opus then made decisions explicitly contextualized: "test_compile.py has no classes to join, so option (b) is impossible." Without those grep results, Opus might have said "join an existing class" generically and the implementation would have hit a no-class file.

**How to apply:** Step 5 dispatch prompts for fold cycles (or any cycle modifying existing files) MUST include either (a) a "Source file inspection results" section pre-populated with the relevant greps, OR (b) an explicit prompt instruction "Grep the candidate target file's structure (classes? bare functions? section comments? import block style?) BEFORE answering each question. State the grep result in your `## Analysis` section."

**Self-check:** for any Step 5 dispatch resolving questions about WHERE/HOW to insert new code, the prompt MUST include grep-result data on the destination file. If the prompt doesn't, expect the subagent to answer generically and the implementation to hit shape mismatches.

## Net cycle assessment

**Steps 1-13:** ran cleanly first-try; primary-session per C37-L5 worked exactly as predicted (no dispatch overhead; ~2 hours wall-clock for 11 ACs + full doc-sync).

**Step 14:** R1 false-positive blocker cost ~10 min refutation work but caught nothing real. R2 APPROVE with 2 cosmetic NITs (1 carry-forward + 1 required Python indentation). Cycle-15 L2 anchor preservation (run the actual tests) saved us from accepting R1's false BLOCKER.

**Step 15:** merged cleanly post-CI green; no late-arrival CVEs.

**Step 16:** 5 lessons derived (C40-L1..L5).

## Skill-patch shipping plan

| Lesson | Where to add | Index entry under |
|---|---|---|
| C40-L1 | `references/cycle-lessons.md` top under `## Cycle 40 skill patches` | `### Subagent dispatch and fallback` (refines cycle-39 L1 + cycle-12 L2) |
| C40-L2 | same | `### Library and API awareness` (refines cycle-22 L4) |
| C40-L3 | same | `### Test authoring — ensure a production revert fails the test` (refines cycle-15 L2 + cycle-23 L2) |
| C40-L4 | same | `### Library and API awareness` or new `### Platform portability` row (refines cycle-22 L1) |
| C40-L5 | same | `### Design CONDITIONS` (codifies cycle-15 L1 application) |

Plus BACKLOG.md addition: `tests/test_compile.py::test_detect_source_drift_docstring_documents_deletion_pruning_persistence` upgrade candidate per C40-L3.

## Cycle metrics

- ACs: 11 (3 test folds + 7 dep-CVE/resolver/drift markers + 1 BACKLOG progress) → 11/11 shipped
- src/kb/ changes: 0 LoC (pure hygiene)
- requirements.txt changes: 0
- Test count: 3014 → 3014 (invariant)
- Test file count: 258 → 255 (3 sources deleted)
- Commits: 5 implementation + 1 self-review = 6 total
- Wall clock: ~3 hours (Steps 1-15)
- PR: #56 merged at SHA `ad6952b`
- Subagent dispatches: 1 (Opus design gate) + 1 (DeepSeek R1) + 1 (Codex R2) = 3 total
- Subagent failures: 0 (R1 false positive caught + refuted; not a dispatch failure)
