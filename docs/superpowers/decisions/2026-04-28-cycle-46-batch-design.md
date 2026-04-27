# Cycle 46 — Step 5 Design Decision Gate

**Date:** 2026-04-28
**Branch:** `cycle-46-batch` in worktree `D:/Projects/llm-wiki-flywheel-c46`
**Reviewer:** Opus 4.7 (1M context) decision gate
**Inputs:** requirements.md, threat-model.md, CLAUDE.md, CHANGELOG.md (cycles 39-45), dev_ds SKILL.md (skip rules + accumulated index Cs 25-42)

## Pre-decision empirical verification (live worktree greps)

| Claim | Requirements doc | Live grep result | Source of truth |
|---|---|---|---|
| Test patch sites | 38 | **40** (test_v5_lint_augment_orchestrator.py = 16 not 14) + 4 in test_lint_augment_split.py | `rg "kb\.lint\._augment_(manifest\|rate)" tests/` |
| Test count baseline | 3027 | **3025** | `pytest --collect-only \| tail -1` |
| Test file count | 244 | **243** | `git ls-files tests/test_*.py \| wc -l` |
| `import sys` in manifest.py | only used by `_sync_legacy_shim` | **CONFIRMED** (1 hit at line 167 — `_sync_legacy_shim` body) | `rg "sys\." src/kb/lint/augment/manifest.py` |
| `import sys` in rate.py | only used by `_sync_legacy_shim` | **CONFIRMED** (1 hit at line 82 — `_sync_legacy_shim` body) | `rg "sys\." src/kb/lint/augment/rate.py` |
| `import sys` in orchestrator.py | (not stated) | **MUST KEEP** — 2 hits at lines 43, 49 used by `_package_attr` + `_compat_symbol` | `rg "sys\." src/kb/lint/augment/orchestrator.py` |
| `run_augment` docstring placement | (not stated) | **single-line `"""Three-gate augment orchestrator."""` at line 75; imports at lines 76, 78-81 are AFTER closing quotes** — no orphan risk | Read orchestrator.py:65-82 |
| pip GHSA-58qw-9mgm-455v firstPatchedVersion | null at cycle-41 | **STILL null** at 2026-04-28 — `<= 26.0.1`, `firstPatchedVersion: null` | `gh api graphql ... GHSA-58qw-9mgm-455v` |
| Open Dependabot alerts | 4 (3 litellm + 1 ragas) | **CONFIRMED** — same 4 alerts, all carry-overs | `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` |

**Key findings:**
1. Requirements doc undercounts by 2 patch sites (`test_v5_lint_augment_orchestrator.py:996` + `:1051` are `monkeypatch.setattr("kb.lint._augment_rate.RateLimiter", ...)` — extra non-paired sites).
2. Test count baseline drift: 3027 in CLAUDE.md / requirements is 2 high vs live 3025. Two parametrize cases or skipped tests dropped after CLAUDE.md last touched.
3. The 4 sites in `test_lint_augment_split.py` are part of AC2 anchor-refresh, not AC1 migration — they get DELETED with `test_augment_compat_shims_resolve_to_new_package`.
4. So AC1 actual scope = **40 - 4 = 36 sites across 8 files** (the test_lint_augment_split.py 4 sites belong to AC2).
5. pip 26.1 advisory still unrefreshed → cycle-22 L4 conservative posture: **DO NOT bump pip pin**.

---

## Q1 — `tests/test_lint_augment_split.py` retention

OPTIONS:
- A. DELETE the file entirely (the cycle-44 anchor purpose vanishes once shims are gone).
- B. KEEP as structure-anchor: drop `test_augment_compat_shims_resolve_to_new_package`; invert `_augment_*.py is_file()` assertions to `not is_file()`; keep the other three tests (`test_augment_package_structure_cycle44`, `test_augment_package_reexports_match_former_flat_symbols_cycle44`, `test_augment_package_imports_with_nonexistent_wiki_dir_cycle44`).

## Analysis

The cycle-15 L2 DROP-with-test-anchor retention rule (codified in dev_ds SKILL.md and refined by C34-L4) is unambiguous: when production code is deleted, the test file SHOULD survive as a forward-protection regression anchor. The rule's express purpose is to prevent silent re-introduction of the deleted invariant. Option A would delete the cycle-44 contract that the package structure (9-file `kb/lint/augment/` package + `_augment_*.py` shims being the EXCEPTION not the rule) is real — making it possible for a future cycle to silently re-create the shims under a different name. Option B converts the file from "shims-are-still-present anchor" to "shims-must-stay-deleted anchor" by inverting two `is_file()` checks; this is the textbook DROP-with-test-anchor application.

Three of the four tests in this file are NOT shim-specific: `test_augment_package_structure_cycle44` enumerates the 9-module package shape, `test_augment_package_reexports_match_former_flat_symbols_cycle44` pins the cycle-44 `__init__.py` re-export contract for 9 symbols (still load-bearing), and `test_augment_package_imports_with_nonexistent_wiki_dir_cycle44` pins the lazy-evaluation contract that survives reload under non-existent WIKI_DIR. Deleting them via Option A would scrap three orthogonal regressions to remove ONE test — that's strictly worse than the targeted intervention in B. Reversibility: Option B's amendment is a pure ~2-line edit (delete `test_augment_compat_shims_resolve_to_new_package` + flip two asserts); reverting is trivial. Option A is one file delete + git restore on the prior content — also reversible, but loses the active anchor.

DECIDE: **B — KEEP file as structure-anchor with inverted `is_file()` assertions**.

RATIONALE: cycle-15 L2 DROP-with-test-anchor (refined C34-L4) directly governs; three of four tests pin orthogonal package-structure invariants unrelated to shim presence; the inverted assertions become the cycle-46 deletion regression-pin.

CONFIDENCE: HIGH.

---

## Q2 — `_sync_legacy_shim()` removal commit cadence

OPTIONS:
- A. One commit per file (3 commits: orchestrator.py imports, manifest.py drop, rate.py drop).
- B. Single batched commit per `feedback_batch_by_file` semantic.

## Analysis

The `feedback_batch_by_file` rule says "Group backlog fixes by file (HIGH+MED+LOW together), not by severity. Target 30-40 items across ~15-20 files per cycle." The keyword is "by file" — i.e. don't fragment one file's HIGH and LOW fixes into separate commits, group them. It's a guidance about WHERE the batching boundary lives (per-file, not per-severity), not a mandate that every cycle squash all files into one commit. Reading the rule strictly, it would say "Option A is correct: one commit per file, with all severities for that file in the same commit." Option B over-applies the rule by collapsing across files.

However, three additional considerations push toward batching: (1) the three changes are semantically ONE refactor — "delete shims and their sync mechanism" — and they MUST land together to keep tests green between commits (AC3 alone fails because tests still patch `kb.lint._augment_*`; AC4+AC5 alone leaves orchestrator pointing at deleted symbols). (2) Squash-merge is the established cycle-merge style per cycle-36 L1 CI-cost discipline; the per-commit branch granularity matters less than the merged-to-main shape. (3) Test patch migration AC1 spans 8 test files — if the cycle is "one commit per file" mechanically, that's 8 commits for AC1 alone, plus 3 for AC3-AC5, plus 2 for AC6-AC7, plus 2 for AC8-AC9 — 15+ commits for a hygiene cycle. Cycle-23 L4 says "after EACH R1/R2/R3 fix commit cascade, re-verify every numeric claim" — that scales linearly with commit count.

DECIDE: **A with bundling — three logical commits, but co-staged in one Step 9 task (TASK 3)**: commit 1 = AC3 orchestrator imports + AC1 test migrations (test patch sites + production caller switch land together to keep CI green); commit 2 = AC4+AC5 (drop `_sync_legacy_shim` + `import sys` from manifest.py + rate.py — these are sister changes); commit 3 = AC6+AC7 (delete shim files). AC2 anchor refresh + AC8+AC9 BACKLOG cleanup go in their own commits per the natural `feedback_batch_by_file` per-file boundary. Squash-merge collapses all of these to one main commit.

RATIONALE: `feedback_batch_by_file` says batch BY file not BY cycle; AC4+AC5 are sister changes that share the `import sys` removal pattern and should ride together; squash-merge means branch granularity is mostly cosmetic.

CONFIDENCE: MEDIUM (cosmetic — merge result is identical regardless of branch commit shape).

---

## Q3 — pip pin bump if advisory refreshed

OPTIONS:
- A. Bump pip 26.0.1 → 26.1 in `requirements.txt` if GHSA-58qw-9mgm-455v advisory has been updated to confirm 26.1 patches the CVE.
- B. Defer to cycle 47+ regardless.

## Analysis

The empirical check ran during this gate's pre-decision verification: `gh api graphql ... GHSA-58qw-9mgm-455v` returned `firstPatchedVersion: null`, `vulnerableVersionRange: <= 26.0.1`. The advisory has NOT been refreshed since cycle-41 verification. cycle-22 L4 conservative posture says: "do NOT bump speculatively — when latest > vulnerable_version_range upper bound BUT advisory's `patched_versions` is null, document the disjunction explicitly." We are in exactly that disjunction: pip 26.1 IS the latest version per `pip index versions pip`, and 26.1 IS technically outside the `<= 26.0.1` vulnerable range, but the advisory has not yet confirmed 26.1 is the fix. C40-L2 explicitly governs this exact scenario.

The decision rule embedded in the question — "if advisory metadata is updated to confirm the patch" — is conditional. Per the live grep result, the antecedent is FALSE. So the question collapses to: defer to cycle 47+. If during Step 11.5 the antecedent flips (advisory updated mid-cycle, which would be a cross-cycle advisory arrival per cycle-22 L4), the operator can opportunistically bump in the same cycle as a Class A patch. But the gate decision today, given the live state, is to NOT bump.

DECIDE: **B — DEFER to cycle 47+** (conditional on Step 11.5 re-check; if advisory flips during the cycle, opportunistic Class A patch under existing skill rules).

RATIONALE: Live `gh api graphql` confirms `firstPatchedVersion: null` — antecedent of the conditional bump is FALSE; cycle-22 L4 conservative posture + C40-L2 disjunction-documentation rule both apply.

CONFIDENCE: HIGH.

---

## Q4 — NEW advisory between cycle-41 and cycle-46

OPTIONS:
- A. Opportunistic Class A patching in scope.
- B. Defer all NEW advisories to cycle 47+.

## Analysis

Step 11.5 of the dev_ds skill explicitly carves out "Existing-CVE opportunistic patch" as a non-agent step that runs every cycle when there are open alerts. cycle-22 L4 codified the cross-cycle advisory arrival pattern: advisories CAN drop between Step-02 baseline and Step-11 verification, and the skill mandates handling them per Class B (PR-introduced, blocks at Step 11) vs Class A (existing on main, opportunistic at Step 11.5). Per the live `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` check, NO new advisories have arrived between cycle-41 and cycle-46 (same 4 alerts: GHSA-r75f / GHSA-v4p8 / GHSA-xqmj on litellm + GHSA-95ww on ragas, all carry-overs). So the question is hypothetical for THIS cycle.

For the future-shaped answer: opportunistic Class A patching is the established pipeline default and should remain in scope. The cost is bounded — Step 11.5 is a single `pip install <pkg>==<patched>` + re-run pip-audit + commit cycle. The benefit is that hygiene-cycle CHANGELOG narrative correctly captures the security delta. Refusing all new advisories until cycle 47+ would deliberately leave a known-unpatched dep at HEAD when a fix is available, which inverts cycle-22 L4's posture.

DECIDE: **A — Opportunistic Class A patching IN SCOPE** for cycle 46 (Step 11.5 re-runs `pip-audit` and patches any newly-fixable advisory; if the resolver-conflict pattern blocks the patch — e.g. another litellm release that still pins click==8.1.8 — document and defer).

RATIONALE: Step 11.5 is part of every cycle by skill default; cycle-22 L4 cross-cycle arrival pattern; refusal would invert conservative-posture intent.

CONFIDENCE: HIGH.

---

## Q5 — Drop `import sys` from manifest.py + rate.py

OPTIONS:
- A. Drop `import sys` from BOTH manifest.py and rate.py once `_sync_legacy_shim` is removed.
- B. Keep `import sys` defensively.

## Analysis

The pre-decision grep returned exactly one `sys.` reference per file: line 167 in manifest.py (`legacy = sys.modules.get("kb.lint._augment_manifest")`) and line 82 in rate.py (`legacy = sys.modules.get("kb.lint._augment_rate")`). Both are inside `_sync_legacy_shim()`. Removing the function makes the import dead code, and ruff F401 (unused-import) would fire on the next CI run, blocking the PR. Option B is therefore not even a stable equilibrium — it would force a follow-up commit to remove the now-flagged import.

A subtle nuance: orchestrator.py also has `import sys`, but it's used at lines 43 and 49 by `_package_attr` and `_compat_symbol` (the lazy-lookup pattern that survived the cycle-44 split). Q5's question deliberately targets ONLY manifest.py and rate.py. The orchestrator.py `import sys` MUST stay; modifying or removing it would break the cycle-44 patch-transparency contract. The requirements doc's AC4 + AC5 wording "Drop the now-orphan `import sys` if no other site uses it" is correct in scope and matches the grep evidence.

DECIDE: **A — DROP `import sys` from manifest.py and rate.py** (orchestrator.py `import sys` MUST be retained — AC3 does NOT touch it).

RATIONALE: ruff F401 fires immediately if kept; both files have only one `sys.` reference each, both in `_sync_legacy_shim` body; orchestrator.py has 2 active references and is out of scope for this question.

CONFIDENCE: HIGH.

---

## Q6 — `Edit replace_all=True` vs per-line for AC1

OPTIONS:
- A. `Edit replace_all=True` per file (one `kb.lint._augment_manifest` → `kb.lint.augment.manifest` Edit per file, then one `kb.lint._augment_rate` → `kb.lint.augment.rate` Edit per file = 16 Edit calls across 8 files).
- B. Per-line `Edit replace_all=False` for each of the 36 sites (36+ Edit calls).

## Analysis

cycle-24 L1 governs this directly: `Edit(replace_all=true)` on a MULTI-LINE code pattern silently misses sites with different indentation or line-break patterns. The lesson's exact words: "before using `Edit(replace_all=true)` on a multi-line code pattern, (a) grep the target for the verbatim pattern to count expected replacements, (b) after Edit, re-grep for the OLD pattern — zero hits expected outside exceptions." But Q6 EXPLICITLY notes that the substring `kb.lint._augment_manifest` is a SINGLE-LINE literal — the question states this verbatim. cycle-24 L1's silent-skip risk applies to multi-line patterns; for single-line literals, `replace_all=True` is documented-safe per the cycle-24 L1 inverse case.

The grep evidence supports this: every one of the 36 sites is a single-line occurrence (`monkeypatch.setattr("kb.lint._augment_manifest.X", ...)` or `from kb.lint._augment_manifest import X` or `import kb.lint._augment_manifest`). All three forms are single-line. `Edit replace_all=True` on the literal substring `kb.lint._augment_manifest` will replace ALL occurrences in a file at once, with the ground-truth verification being a post-Edit re-grep showing zero hits (exactly what AC1's Verify clause demands). Per-line Edit (Option B) means 36 separate Edit calls with 36 separate failure modes — strictly worse cognitively + operationally for the same outcome.

The cycle-44 contrast is instructive: cycle-44 cycle-24 L1 fired on a MULTI-LINE inline `time.sleep(min(LOCK_INITIAL_POLL_INTERVAL * (2**attempt_count), LOCK_POLL_INTERVAL)); attempt_count += 1` pattern with different indentation across 3 sites. That's a different shape. The cycle-46 case is a 25-character single-line substring across 36 sites with consistent quoting — replace_all is the natural tool.

DECIDE: **A — `Edit replace_all=True` per file with mandatory post-edit grep verification**. Specifically: 2 Edits per file (one for `_augment_manifest` → `augment.manifest`, one for `_augment_rate` → `augment.rate`), then `rg "kb\.lint\._augment_(manifest|rate)" tests/<file>` returning zero hits as the per-file gate before moving on.

RATIONALE: cycle-24 L1's silent-skip risk is documented for MULTI-LINE patterns; the AC1 substring is single-line literal per the question itself; per-line Edits at 36+ calls is operational tax with no upside.

CONFIDENCE: HIGH (with mandatory verification — grep MUST be run after each file's Edits per cycle-24 L1 explicit guidance).

---

## Q7 — Cycle-44 BACKLOG comment block

OPTIONS:
- A. DELETE the entire cycle-44 comment block at BACKLOG.md lines 222-226.
- B. REPLACE with a "Cycle 46 closed" entry.
- C. KEEP as historical context.

## Analysis

The BACKLOG.md format guide at the top of the file says: "When resolving an item, delete it (don't strikethrough). Record a brief newest-first summary in CHANGELOG.md and put implementation detail in CHANGELOG-history.md." The format guide implies: BACKLOG.md is open work; resolved items leave the file. The cycle-44 close comment block is a HISTORICAL RECORD of resolution intent — its information is duplicated in CHANGELOG-history.md cycle-44 entry and will be superseded by cycle-46's CHANGELOG-history.md entry once shipped. Option C (keep) violates the BACKLOG-as-open-work principle and creates documentation drift over time (more cycles closing, more historical comment blocks, more state for future operators to filter through).

Option A (delete) follows the format guide cleanly. Option B (replace with cycle-46 closed) just shifts the temporal anchor — same problem as C, recurring next cycle. The only argument for B is informational continuity: future operators reading BACKLOG.md mid-Phase-4.6 might want to see "this LOW item was historically the lint shims, closed in cycle 46." But that's exactly what `git log BACKLOG.md` and CHANGELOG-history.md provide. CHANGELOG-history.md entry for cycle 46 will already include "M2 follow-up: lint/_augment_*.py shims deleted; orchestrator imports + 36 test patch sites migrated." Duplicating that fact inside a never-deleted BACKLOG.md comment is redundant.

DECIDE: **A — DELETE the cycle-44 historical comment block at lines 222-226**. AC8's wording "delete the cycle-44 'REMAIN as compat shims' comment block that referenced the cycle-45 deletion plan" already covers this. CHANGELOG-history.md cycle-46 entry preserves the complete ship-chain record.

RATIONALE: BACKLOG.md format guide says "when resolving, delete"; CHANGELOG-history.md is the authoritative ship-chain archive; keeping the cycle-44 block creates accumulating historical drift in BACKLOG with each closed item.

CONFIDENCE: HIGH.

---

## Q8 — Skip Step 4 design eval

OPTIONS:
- A. Skip Step 4 (parallel DeepSeek + Codex design-eval rounds).
- B. Run Step 4.

## Analysis

The dev_ds SKILL.md Step-4 skip rule: "trivial one-liner". Cycle 46 is a hygiene cycle deleting 2 src files (~52 LOC total) + dropping 2 dead `_sync_legacy_shim` functions (~23 LOC) + flipping 2 import paths in orchestrator.py + 36-site mechanical test-patch migration. The src/ diff is roughly +0 / -75 LOC — strictly DELETION, no novel behavior. Cycle-39 / cycle-40 / cycle-41 / cycle-42 all skipped Step 4 with similar profiles (pure hygiene, low-novelty mechanical migrations). The precedent is clear and the skip rationale matches the exact pattern.

Two cautions support running Step 4 in some form: (1) cycle-22 L5 says "design-gate CONDITIONS are load-bearing test coverage, not optional nice-to-haves" — Step 4 is the upstream input to those CONDITIONS via R1+R2 reviewer findings. (2) The 36 test-patch sites are mechanical but high-volume; cycle-24 L1's silent-skip risk on `Edit replace_all=True` could surface missed sites without independent review. However: Step 5 (this gate) IS the design-decision gate; Step 11 Codex security verify reads the actual diff post-implementation; Step 14 R1 DeepSeek + R2 Codex parallel PR review provides exactly the dual-review coverage Step 4 would. So skipping Step 4 doesn't lose the dual-review safety net — it just shifts it to the post-implementation gates where the diff is concrete.

DECIDE: **A — SKIP Step 4** (matches cycle-39/40/41/42 hygiene-cycle precedent; trivial-one-liner rule applies; Step 14 dual-PR-review preserves dual-eyeball coverage on the actual diff).

RATIONALE: hygiene-cycle precedent (4 prior cycles); src/ diff is pure deletion; Step 14 R1 DeepSeek + R2 Codex parallel review covers the dual-review need post-implementation.

CONFIDENCE: HIGH.

---

## Q9 — Skip Step 6 Context7

OPTIONS:
- A. Skip Step 6 (Context7 lib/API verification).
- B. Run Step 6.

## Analysis

Step-6 skip rule: "pure stdlib/internal code". Cycle 46 touches zero third-party libraries — no upgrade, no new dependency, no API change to verify. The orchestrator.py imports being changed (`from kb.lint._augment_manifest import X` → `from kb.lint.augment.manifest import X`) are PURELY INTERNAL kb-package paths. The test-patch migration is purely internal kb path strings. The `_sync_legacy_shim` removal removes internal mechanism. There is literally no third-party lib whose docs Context7 would resolve.

The only nuance: AC10 dep-CVE re-verification touches `pip-audit`, `pip index versions`, and `gh api` — those are CLI tooling for security verification, not library APIs to integrate with. Context7 doesn't cover GitHub Security Advisory API documentation in the relevant sense; the `gh` CLI's stable interface is documented internally. So Step 6 has nothing to look up even on the AC10 axis.

DECIDE: **A — SKIP Step 6** (no third-party libraries touched; pure-stdlib/internal-code rule applies trivially).

RATIONALE: Zero third-party API surface in cycle 46; Step-6 skip rule applies verbatim.

CONFIDENCE: HIGH.

---

## Q10 — Skip Step 9.5 simplify pass

OPTIONS:
- A. Skip Step 9.5.
- B. Run Step 9.5.

## Analysis

Step-9.5 skip rule: "trivial diff (<50 LoC), pure dep-bump, signature-preserving refactor". Cycle 46's src/ diff after AC3-AC7 = -75 LOC net (delete 27+25=52 from `_augment_*.py` + delete ~23 from two `_sync_legacy_shim` bodies + 2-line import flip in orchestrator.py = -75 net). On the strict <50 LoC threshold, cycle 46 EXCEEDS the trivial-diff bound. But the diff is PURE DELETION — there's no positive-LOC code to simplify. The rule's three skip criteria are alternatives ("OR"), not all-three. Specifically: (1) <50 LoC is one criterion; (2) pure dep-bump is another; (3) signature-preserving refactor is the third. Cycle 46 satisfies (3) — every change is signature-preserving (`Manifest.start`, `RateLimiter()`, `RESUME_COMPLETE_STATES` etc. all keep their public signatures; the file path that hosts them moves from `kb.lint._augment_manifest` → `kb.lint.augment.manifest` but the symbol surface is unchanged).

The dev_ds Red Flags table row at line 642 is precise: "Skip Step 9.5 only when its skip-when row matches (trivial diff, dep-bump, signature-preserving)." Cycle 46 matches the third condition. Cycle-39 / cycle-40 / cycle-41 all skipped 9.5 under similar logic. The contrast case where 9.5 SHOULD run is cycles introducing new helpers, new abstractions, or non-trivial refactors that could be over-engineered — none of those apply here.

DECIDE: **A — SKIP Step 9.5** (signature-preserving refactor; matches cycle-39/40/41 precedent; 9.5 has nothing to simplify when the diff is pure deletion + path renames).

RATIONALE: Skip-when third condition (signature-preserving refactor) applies; pure deletion has nothing to simplify; hygiene-cycle precedent.

CONFIDENCE: HIGH.

---

## Q11 (NEW) — Cycle-tag bump for ALL 9 dep-CVE items

OPTIONS:
- A. Bump cycle tags from `cycle-41+` → `cycle-47+` for ALL 9 items even if state matches cycle-41.
- B. Update tags ONLY where state changed.

## Analysis

cycle-23 L3 codifies the deferred-promise BACKLOG sync rule: "every 'deferred to cycle N+M' line in threat-model.md / design.md must have a matching BACKLOG entry; the cycle tag tracks the most-recent re-confirmation." The purpose of the tag is to encode "this item was last re-checked in cycle X and confirmed unchanged" — it's NOT a promise of resolution by that cycle. Cycle-39 / cycle-40 / cycle-41 each bumped their tag forward to indicate fresh verification, even when state matched. The pattern is: re-verify, bump tag, document the no-change finding. Reading cycle-39 / 40 / 41 CHANGELOG entries: each one bumped tags even when nothing changed — the bump itself encodes "this item was reviewed during cycle N and the state matches the prior cycle".

Option B (update only where state changed) would leave the cycle-41 tag in place for unchanged items, creating ambiguity at cycle 47: did cycle 46 review them and confirm unchanged? Or did cycle 46 skip the review? The prior-cycle pattern is to bump unconditionally on re-verification; that's the interpretation that scales. The cost of A is trivial — a single grep + multi-edit to refresh the tag string from `cycle-41+` to `cycle-47+` on each entry.

The exception is genuine state-change. AC10 explicitly handles those: per the requirements doc, "either re-confirm (update cycle tag) OR document state changes in CHANGELOG (e.g., new release, new advisory, resolver conflict cleared)." A state change goes to CHANGELOG; an unchanged-but-reviewed entry gets the tag bumped. That matches Option A semantics.

DECIDE: **A — BUMP cycle tags from `cycle-41+` → `cycle-47+` for ALL 9 items** (4 advisories + 3 resolver conflicts + 2 Dependabot drift). Where state has changed (e.g. new advisory drop, new release that confirms patch), document in CHANGELOG separately and either resolve OR re-tag with the new cycle baseline. Default no-state-change: tag bump only.

RATIONALE: cycle-23 L3 + cycle-39/40/41 precedent; tag encodes "last re-verified cycle"; ambiguity from leaving stale tags at cycle 47+ exceeds the trivial cost of bumping all 9.

CONFIDENCE: HIGH.

---

## Q12 (NEW) — Forward-protection assertion vs inverted `is_file()`

OPTIONS:
- A. Inverted `is_file()` check is sufficient (just `assert not (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()`).
- B. ALSO add a forward-protection assertion (e.g. `assert "kb.lint._augment_manifest" not in sys.modules` after import OR `assert importlib.util.find_spec("kb.lint._augment_manifest") is None`).

## Analysis

cycle-24 L4 governs revert-tolerance for security-class regression tests: "for regression tests of security-class anti-patterns, assertions MUST test the RELATIONSHIP between the attacker-controlled artifact and the legitimate artifact — not just their presence." Cycle 46 isn't security-class — it's hygiene/deletion — but the spirit applies: a test should fail under revert. The inverted `not is_file()` check passes if-and-only-if the shim files are absent on disk. Reverting cycle 46 (recreate `_augment_manifest.py` + `_augment_rate.py`) would immediately flip `not is_file()` → False, failing the test. So Option A is REVERT-SENSITIVE — a partial cycle-revert that recreates the files would trigger the regression.

Option B adds redundant detection. `importlib.util.find_spec("kb.lint._augment_manifest")` returns None when the module file is absent — same information as `is_file()`, just routed through importlib. `"kb.lint._augment_manifest" not in sys.modules` is weaker (sys.modules state depends on test ordering; might pass even if a shim exists but hasn't been imported in the current process). Option B's incremental value is approximately zero, and adds dependency on importlib state.

The C40-L3 lesson on vacuous tests advocates "behavior, not signature" — but that's about ASSERTION SHAPE (path-presence is signature-shaped, behavioral assertion would test "trying to import raises ModuleNotFoundError"). The strongest forward-protection variant would be: `with pytest.raises(ModuleNotFoundError): import kb.lint._augment_manifest`. That IS a behavioral test of the deletion. This is more valuable than `not is_file()` — file removal is checkable, but import failure is the SEMANTIC contract.

DECIDE: **A WITH AMENDMENT — keep inverted `not is_file()` AND add a behavioral `pytest.raises(ModuleNotFoundError)` assertion in the same test**. Concretely: add `with pytest.raises(ModuleNotFoundError): import kb.lint._augment_manifest` (and same for _augment_rate) inside `test_augment_package_structure_cycle44`. Two assertions, same file, no new test function.

RATIONALE: `not is_file()` is revert-sensitive on disk state; behavioral `ModuleNotFoundError` is the stronger semantic contract per C40-L3 / `feedback_test_behavior_over_signature`; adding both is cheap (2 lines) and pins both file-deletion and importability-removal contracts.

CONFIDENCE: HIGH.

---

## Q13 (NEW) — orchestrator.py docstring placement / orphan check

OPTIONS:
- A. Confirmed safe — no docstring orphan risk; AC3 import-flip preserves layout.
- B. Cycle-23 L1 risk applies — needs explicit docstring-first verification before/after Edit.

## Analysis

cycle-23 L1: "function-body imports added BEFORE the closing `"""` of a docstring turn the string literal into a no-op expression statement." The risk fires when imports are placed BETWEEN the parameter list and the closing `"""`. Pre-decision verification of orchestrator.py:65-82 confirms: line 75 = `"""Three-gate augment orchestrator."""` — single-line docstring with closing quotes ON the same line as the opening; line 76 = `from urllib.parse import urlparse` — first body statement AFTER the closing `"""`; lines 78-81 = `import kb` + the AC3-target imports + `from kb.mcp.app import _validate_run_id`. The docstring is fully closed on line 75 BEFORE any of the imports.

AC3's edit changes ONLY the import path strings (`kb.lint._augment_manifest` → `kb.lint.augment.manifest` and `kb.lint._augment_rate` → `kb.lint.augment.rate`). It does NOT change line ordering, does NOT touch the docstring, does NOT add or remove imports — only mutates two `from X import Y` lines' module path. The cycle-23 L1 risk is structurally inapplicable: the imports are already AFTER the docstring; the AC3 edit is an in-place path rename on existing import lines.

The defensive measure for future-proofing: AC3 implementation should retain `function.__doc__` testing. A targeted assertion `assert run_augment.__doc__ is not None and "Three-gate" in run_augment.__doc__` after the AC3 commit catches any silent docstring-orphan bug introduced by the Edit. The cost is trivial (one assert), and it's a worthwhile cycle-23 L1 forward-protection trace even when the current edit is structurally safe.

DECIDE: **A — Confirmed SAFE; AC3 import-flip preserves layout and docstring is line-75 single-line ABOVE the imports**. CONDITION: add a regression assertion in `test_lint_augment_split.py` or `test_v5_lint_augment_orchestrator.py` checking `run_augment.__doc__` is non-None and contains "Three-gate" (cycle-23 L1 forward-protection per accumulated rules index).

RATIONALE: live grep of orchestrator.py:65-82 confirms docstring closes on line 75 before imports; AC3 edit is path-string rename, not structural insert; defensive `__doc__` assertion prevents future silent regression.

CONFIDENCE: HIGH.

---

# VERDICT

**PROCEED-WITH-CONDITIONS.** All 13 questions resolved at HIGH confidence (Q2 at MEDIUM — cosmetic). The cycle is mechanically tractable: pure deletion + 36-site mechanical migration + BACKLOG hygiene + dep-CVE re-verification. No novel design surface; no new attack surface; no new deps. CONDITIONS below capture the 5 binding constraints Step-9 implementation MUST satisfy beyond the requirements doc's AC text.

# DECISIONS

- **Q1 → B:** KEEP `tests/test_lint_augment_split.py` as structure-anchor; delete `test_augment_compat_shims_resolve_to_new_package`; invert two `is_file()` assertions to `not is_file()`.
- **Q2 → A (with bundling):** AC3+AC1 ride together (commit 1); AC4+AC5 ride together (commit 2); AC6+AC7 ride together (commit 3); squash on merge.
- **Q3 → B:** DEFER pip pin bump to cycle 47+ — `gh api graphql` confirms `firstPatchedVersion: null` at 2026-04-28; cycle-22 L4 conservative posture.
- **Q4 → A:** Opportunistic Class A patching IS in scope per Step 11.5 standard pipeline — but live check shows zero new advisories since cycle 41.
- **Q5 → A:** DROP `import sys` from manifest.py + rate.py post-shim-removal (only one `sys.` ref each, both in `_sync_legacy_shim`); KEEP `import sys` in orchestrator.py (used by `_package_attr` + `_compat_symbol`).
- **Q6 → A:** `Edit replace_all=True` per file with mandatory post-edit `rg "kb\.lint\._augment_(manifest|rate)" tests/<file>` zero-hits gate per cycle-24 L1.
- **Q7 → A:** DELETE the cycle-44 historical comment block at BACKLOG.md lines 222-226 per BACKLOG-as-open-work format guide; ship-chain preserved in CHANGELOG-history.md cycle-46 entry.
- **Q8 → A:** SKIP Step 4 — hygiene-cycle precedent (cycles 39/40/41/42); pure deletion src/ diff; Step 14 R1+R2 PR review preserves dual-eyeball coverage.
- **Q9 → A:** SKIP Step 6 — zero third-party API surface; pure-stdlib/internal-code rule applies trivially.
- **Q10 → A:** SKIP Step 9.5 — signature-preserving refactor; pure deletion has nothing to simplify.
- **Q11 → A:** BUMP cycle tags from `cycle-41+` → `cycle-47+` on ALL 9 dep-CVE items (4 advisories + 3 resolver conflicts + 2 Dependabot drift); state-changes documented separately in CHANGELOG.
- **Q12 → A WITH AMENDMENT:** keep inverted `not is_file()` check AND add behavioral `pytest.raises(ModuleNotFoundError)` import-attempt assertions in `test_augment_package_structure_cycle44` per `feedback_test_behavior_over_signature`.
- **Q13 → A:** orchestrator.py docstring placement is SAFE (line 75 single-line `"""..."""` closes before line-76+ imports); add a `run_augment.__doc__` regression assertion as cycle-23 L1 forward-protection.

# CONDITIONS

Step 9 implementation MUST satisfy each of the following — explicit pass-fail at Step 11 verify:

1. **AC1 patch site count** — actual scope is **36 sites across 8 test files** (not 38 — requirements doc undercounts by 2 in `test_v5_lint_augment_orchestrator.py:996, :1051`). Per-file counts: `test_backlog_by_file_cycle1.py` (2), `test_cycle13_frontmatter_migration.py` (2), `test_cycle17_resume.py` (1), `test_cycle9_lint_augment.py` (2), `test_v5_kb_lint_signature.py` (1), `test_v5_lint_augment_manifest.py` (6), `test_v5_lint_augment_orchestrator.py` (16), `test_v5_lint_augment_rate.py` (6). The 4 sites in `test_lint_augment_split.py` belong to AC2 (deletion), not AC1. Verify via `rg -c "kb\.lint\._augment_(manifest|rate)" tests/` returning zero across all 8 + 0 across `test_lint_augment_split.py` after AC2.

2. **AC2 forward-protection upgrade** — `test_augment_package_structure_cycle44` MUST add `with pytest.raises(ModuleNotFoundError): import kb.lint._augment_manifest` AND `with pytest.raises(ModuleNotFoundError): import kb.lint._augment_rate` AFTER the inverted `not is_file()` assertions. This is per Q12 / `feedback_test_behavior_over_signature` / C40-L3 — file-deletion is signature-shaped, importability-failure is the behavioral contract. Verify by reverting AC6+AC7 in a scratch branch — both assertion classes MUST fail.

3. **AC3 docstring forward-protection** — append (or add to a sibling test) the assertion `assert run_augment.__doc__ is not None and "Three-gate" in run_augment.__doc__` per Q13. Place the assertion in `test_v5_lint_augment_orchestrator.py` or `test_lint_augment_split.py`. Cycle-23 L1 risk is structurally absent at AC3 implementation time but the assertion future-proofs the docstring contract against later edits.

4. **AC4+AC5 `import sys` removal** — explicit removal of line 7 (`import sys`) in manifest.py AND line 6 (`import sys`) in rate.py per Q5 / pre-decision grep. Verify post-implementation via `rg "^import sys" src/kb/lint/augment/{manifest,rate}.py` returning zero hits. Do NOT touch `import sys` in orchestrator.py — it's used at lines 43 + 49 by `_package_attr` + `_compat_symbol` and MUST stay.

5. **AC10 cycle-tag refresh + Dependabot baseline check** — Step 11.5 MUST execute `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` AND `pip-audit --format=json` against the live `.venv`. For each of 4 advisories + 3 resolver conflicts + 2 Dependabot drift entries: bump cycle tag from `cycle-41+` → `cycle-47+` AND append a one-line confirmation to CHANGELOG-history.md cycle-46 entry (e.g. "diskcache 5.6.3 / GHSA-w8v5-vhqr-4h9v re-confirmed unchanged 2026-04-28; pip-audit fix_versions=[]; pip index versions diskcache → 5.6.3 = LATEST"). Per Q11 / cycle-23 L3 / cycle-39 / cycle-40 / cycle-41 precedent.

6. **AC11 doc-sync count drift** — actual baseline is **3025 tests / 243 files** (not 3027 / 244 as CLAUDE.md / requirements doc claim). After AC2 deletes 1 test, expected post-cycle count is **3024 tests / 243 files** (no test-file delta this cycle — `test_lint_augment_split.py` edited not deleted; 2 src-file deletions don't affect the test count). Update `CLAUDE.md`, `docs/reference/testing.md`, `docs/reference/implementation-status.md`, `README.md` to the post-cycle authoritative counts via `pytest --collect-only | tail -1` + `git ls-files tests/test_*.py | wc -l`. Per cycle-23 L4 + cycle-15 L4: re-verify after EACH R1/R2 PR-review fix commit cascade.

7. **AC8 BACKLOG cleanup completeness** — DELETE both the Phase 4.6 LOW BACKLOG entry at lines 228-229 (`lint/_augment_manifest.py (213 LOC)...`) AND the cycle-44 historical comment block at lines 222-226 (`Cycle 44 closed (2026-04-27): L1 lint/_augment_manifest.py...`). Per Q7 / BACKLOG format guide. The Cycle-42 closed comment block at lines 216-221 stays (covers separate L1/L2/L4/L5 items unrelated to cycle 46).

# FINAL DECIDED DESIGN

### AC1 — Test patch migration across 8 test files (AMENDED — corrected from 9 files / 38 sites to 8 files / 36 sites)

Replace `kb.lint._augment_manifest` → `kb.lint.augment.manifest` and `kb.lint._augment_rate` → `kb.lint.augment.rate` across these test files:
- `tests/test_backlog_by_file_cycle1.py` (2 sites)
- `tests/test_cycle13_frontmatter_migration.py` (2 sites)
- `tests/test_cycle17_resume.py` (1 site)
- `tests/test_cycle9_lint_augment.py` (2 sites)
- `tests/test_v5_kb_lint_signature.py` (1 site)
- `tests/test_v5_lint_augment_manifest.py` (6 sites)
- `tests/test_v5_lint_augment_orchestrator.py` (**16** sites — corrected from 14)
- `tests/test_v5_lint_augment_rate.py` (6 sites)

Implementation: per Q6 / cycle-24 L1, use `Edit replace_all=True` (2 Edits per file: one for `_augment_manifest`, one for `_augment_rate`), then verify via `rg -c "kb\.lint\._augment_(manifest|rate)" tests/<file>` returning zero. After all 8 files migrated: `rg "kb\.lint\._augment_(manifest|rate)" tests/` returns zero outside `test_lint_augment_split.py`.

### AC2 — `tests/test_lint_augment_split.py` cycle-44 anchor refresh (AMENDED with forward-protection)

- Delete `test_augment_compat_shims_resolve_to_new_package`.
- In `test_augment_package_structure_cycle44`: invert lines 25-26 to `assert not (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()` and `assert not (ROOT / "src" / "kb" / "lint" / "_augment_rate.py").is_file()`.
- **AMENDMENT (CONDITION 2):** add behavioral importability assertions:
  ```python
  with pytest.raises(ModuleNotFoundError):
      import kb.lint._augment_manifest  # noqa: F401
  with pytest.raises(ModuleNotFoundError):
      import kb.lint._augment_rate  # noqa: F401
  ```
- Keep `test_augment_package_reexports_match_former_flat_symbols_cycle44` and `test_augment_package_imports_with_nonexistent_wiki_dir_cycle44` as-is.

### AC3 — `src/kb/lint/augment/orchestrator.py` lines 79-80 import flip (AMENDED with docstring forward-protection)

Replace function-local imports inside `run_augment` (line 65+):
```python
from kb.lint._augment_manifest import RESUME_COMPLETE_STATES, Manifest
from kb.lint._augment_rate import RateLimiter
```
with
```python
from kb.lint.augment.manifest import RESUME_COMPLETE_STATES, Manifest
from kb.lint.augment.rate import RateLimiter
```

Docstring at line 75 (`"""Three-gate augment orchestrator."""`) is single-line and CLOSES before line 76+ imports — no cycle-23 L1 orphan risk. **AMENDMENT (CONDITION 3):** add forward-protection assertion in a sibling test:
```python
def test_run_augment_docstring_survives_cycle46_import_flip():
    from kb.lint.augment.orchestrator import run_augment
    assert run_augment.__doc__ is not None
    assert "Three-gate" in run_augment.__doc__
```

### AC4 — `src/kb/lint/augment/manifest.py` cleanup (AMENDED with explicit `import sys` removal)

- Delete `_sync_legacy_shim()` function (lines 166-177).
- Delete module-level `_sync_legacy_shim()` call (line 180).
- **AMENDMENT (CONDITION 4):** delete `import sys` (line 7). Verify with `rg "^import sys" src/kb/lint/augment/manifest.py` returning zero.

### AC5 — `src/kb/lint/augment/rate.py` cleanup (AMENDED with explicit `import sys` removal)

- Delete `_sync_legacy_shim()` function (lines 81-85).
- Delete module-level `_sync_legacy_shim()` call (line 88).
- **AMENDMENT (CONDITION 4):** delete `import sys` (line 6). Verify with `rg "^import sys" src/kb/lint/augment/rate.py` returning zero.

### AC6 — Delete `src/kb/lint/_augment_manifest.py`.

### AC7 — Delete `src/kb/lint/_augment_rate.py`.

### AC8 — BACKLOG.md cleanup (AMENDED with comment-block scope)

- Delete Phase 4.6 LOW entry at lines 228-229 (`lint/_augment_manifest.py (213 LOC) and lint/_augment_rate.py (110 LOC)...`).
- Delete the cycle-44 historical comment block at lines 222-226 (`Cycle 44 closed (2026-04-27): L1 lint/_augment_manifest.py + lint/_augment_rate.py...`).
- KEEP the cycle-42 closed comment block at lines 216-221 (covers separate L1/L2/L4/L5 items).

### AC9 — Delete Phase 4.6 MEDIUM `mcp/core.py` BACKLOG entry at lines 211-212 (resolved by cycle-45 PR #65).

### AC10 — Dep-CVE re-verification (AMENDED — bump tags on ALL 9 items per Q11)

- Run `pip-audit --format=json` against live `.venv`.
- Run `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts`.
- Run `pip index versions {diskcache,ragas,litellm,pip}`.
- Run `pip download --no-deps litellm==<latest>` to extract `Requires-Dist: click==X.Y.Z` from wheel METADATA.
- For each of 4 advisories + 3 resolver conflicts + 2 Dependabot drift entries: **bump cycle tag from `cycle-41+` → `cycle-47+` unconditionally**; if state changed (e.g. new release confirms patch, advisory refreshed, resolver conflict cleared), document delta in CHANGELOG-history.md cycle-46 entry AND patch via Step 11.5 if Class A applicable.
- Pip 26.1 advisory check: `gh api graphql ... GHSA-58qw-9mgm-455v` — at gate time `firstPatchedVersion: null` confirmed; **DO NOT bump pip pin** per Q3.

### AC11 — Multi-site test-count narrative sync (AMENDED — corrected baseline)

- Authoritative pre-cycle baseline: **3025 tests / 243 files** (not 3027 / 244 — CLAUDE.md drift).
- Post-cycle expected: **3024 tests / 243 files** (-1 from AC2 deletion of `test_augment_compat_shims_resolve_to_new_package`; no test-file delta).
- Update via `pytest --collect-only | tail -1` + `git ls-files tests/test_*.py | wc -l` re-verified post-implementation.
- Update count in: `CLAUDE.md`, `docs/reference/testing.md`, `docs/reference/implementation-status.md`, `README.md`.

### AC12 — Phase 4.5 HIGH #4 progress note appended with cycle-46 marker noting "no new folds this cycle (cycle-46 prioritised Phase 4.6 LOW shim deletion); ~190+ versioned files still to fold across future cycles."

# AMENDMENT NOTES

| Original AC | New scope | Why |
|---|---|---|
| AC1 — 38 sites across 9 files | **AC1 — 36 sites across 8 files** | Live `rg` shows 16 (not 14) sites in `test_v5_lint_augment_orchestrator.py` (`:996` + `:1051` are extra `monkeypatch.setattr("kb.lint._augment_rate.RateLimiter", ...)`); 4 sites in `test_lint_augment_split.py` belong to AC2 (deletion target), not AC1 (migration target). |
| AC2 — invert `is_file()` only | **AC2 — invert `is_file()` AND add `pytest.raises(ModuleNotFoundError)` behavioral assertions** | Q12 / `feedback_test_behavior_over_signature` / C40-L3 — file-presence is signature-shaped; import-failure is the behavioral contract. |
| AC3 — replace 2 import lines | **AC3 — replace 2 import lines AND add `run_augment.__doc__` regression assertion** | Q13 / cycle-23 L1 forward-protection; cheap insurance even when current edit is structurally safe. |
| AC4 — drop `_sync_legacy_shim()` + "drop import sys if no other site" | **AC4 — drop `_sync_legacy_shim()` + drop `import sys` (CONFIRMED only 1 ref, in shim body)** | Pre-gate grep confirms unconditional drop; ruff F401 would fire otherwise. |
| AC5 — same as AC4 for rate.py | **AC5 — same explicit drop** | Same as above. |
| AC8 — delete LOW entry + cycle-44 comment block | **AC8 — delete LOW entry at lines 228-229 + cycle-44 comment block at lines 222-226 (PRESERVE cycle-42 block at 216-221)** | Cycle-42 block covers unrelated L1/L2/L4/L5 items still in CHANGELOG-history archive scope. |
| AC10 — re-confirm OR document state changes | **AC10 — bump tag `cycle-41+` → `cycle-47+` on ALL 9 items unconditionally; document state changes separately** | Q11 / cycle-23 L3 + cycle-39/40/41 precedent; tag encodes "last re-verified cycle" not "promised resolution". |
| AC11 — count drift fix to 3026 expected | **AC11 — baseline corrected to 3025 → 3024 expected (was 3027 → 3026)** | Live `pytest --collect-only` verification shows CLAUDE.md drift; correct baseline is 3025. |
