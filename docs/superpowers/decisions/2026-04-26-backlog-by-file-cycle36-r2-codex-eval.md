# Cycle 36 — R2 (Primary-Session Fallback) Step-4 Design Eval

**Date:** 2026-04-26
**Reviewer:** Primary session (cycle-22 L2 + cycle-20 L4 + cycle-34 L5 fallback after R2 Codex dispatch hang >12 min — `block-no-verify` hook interception likely on the "verify" substring in the prompt prose)
**Inputs:** Step-1 requirements, Step-2 threat model, Step-3 brainstorm, R1 Opus eval (`2026-04-26-backlog-by-file-cycle36-r1-opus-eval.md`), Step-2 dependabot baseline at `.data/cycle-36/alerts-baseline.json`
**Branch:** `feat/backlog-by-file-cycle36`
**Verdict in one line:** APPROVE-WITH-AMENDMENTS — R1's findings are correct; R2 adds 3 NEW edge-case concerns + slow-test enumeration data the R1 eval did not cover.

---

## 1. Edge cases / failure modes (per AC area)

### Area A — Multiprocessing hang + pytest-timeout

**E1.** AC1+AC2 fix the cycle-23 multiprocessing test, but tests at positions 1156-2995 in pytest's collection order have NEVER been exercised on Windows GHA CI (1151 passed at hang, 3 skipped, 1 hung, 1840 unreached). Once AC2 unblocks pytest past position #1155, NEW failures may surface. Mitigation: AC4's local probe is necessary but insufficient — a CI probe-PR is needed before strict-gating (AC8). Recommendation: split the cycle's CI work into two pushes — push 1 = AC1+AC2+AC3+AC4 on a probe branch with `continue-on-error: true` STILL ON to surface unreached failures; push 2 = AC8 strict gate after the probe is clean.

**E2.** AC3 `pytest-timeout = 120s` (Q2=B): I verified locally that the cycle-23 multiprocessing test runs in 1.03s and the only other `@pytest.mark.integration` test (`test_pytest_integration_marker_registered`) is trivial. The full local suite runs ~50s. So 120s default is generous but safe. ONE concern: `pytest-timeout` uses a thread-based interrupt mechanism on Windows (no SIGALRM). Tests that hold the GIL via C extension (e.g., `numpy` work in cycle-25-26 vector tests) can ignore the interrupt. Mitigation: this is a Windows-runner-specific failure mode; if it surfaces, the affected test gets `@pytest.mark.timeout(N, method="signal")` override (not portable) OR is marked integration and run in a separate non-strict step.

**E3.** AC2's `os.environ.get("CI") == "true"` predicate: Codex Cloud / Anthropic's Verifier sandbox / Coolify CI all set `CI=true` so the predicate trips broadly — desired. But local `act` (GHA local runner) ALSO sets `CI=true`; developers using `act` to dry-run CI changes would skip the cycle-23 test silently. Acceptable; cycle-37 BACKLOG can switch to `GITHUB_ACTIONS` if that surfaces.

### Area B — Fragility-class fixes

**E4.** AC5 mirror-rebind: my probe of `tests/test_cycle10_quality.py` shows BOTH affected tests already monkeypatch:
- `kb.review.refiner.WIKI_DIR`
- `kb.compile.linker.WIKI_DIR`
- `kb.mcp.quality.WIKI_DIR`

But miss `kb.config.WIKI_DIR`. AC5's claim that adding `kb.config.WIKI_DIR` will fix the CI failure has a hidden dependency: which module's `WIKI_DIR` snapshot is the production code reading at the failure site? If the production code reads `kb.review.refiner.WIKI_DIR` (the test ALREADY patches that), then `kb.config.WIKI_DIR` patch is irrelevant. **Step-5 must verify by tracing the call chain.** Read of `src/kb/review/refiner.py` and `src/kb/mcp/quality.py` shows `kb_refine_page` → `refine_page` → reads `WIKI_DIR` from refiner module. The test ALREADY covers that path. Why does CI fail? Hypothesis: R1's eval said the tests pass locally; the CI failure was OBSERVED on cycle-34 ubuntu-latest before the workflow switched to windows-latest. AC5 may be FIXING A NON-PROBLEM if cycle-34's switch to windows-latest already incidentally fixed it.

**Verification:** the cycle-35 hotfix CI run (2026-04-26 04:02:20Z, windows-latest) shows `tests/test_cycle10_quality.py::test_kb_refine_page_surfaces_backlinks_error_on_failure` LISTED in the collect-only output. No subsequent FAILED line. So the test PASSES on windows-latest. Step-5 should confirm whether AC5 is needed AT ALL or whether it's pre-emptively patching for ubuntu-latest matrix introduction.

**E5.** AC6 `requires_real_api_key()` helper: my grep returned ZERO hits for `anthropic.Anthropic(api_key=` in `tests/`. The 4 enumerated test files use `ANTHROPIC_API_KEY` env-var indirectly. This means AC6's primary risk (real API call burning credits in CI on dummy key) doesn't materialize through that code path. Re-scope: AC6 should helper-gate any test that ENTERS code that ULTIMATELY calls `anthropic.Anthropic(...).messages.create(...)`. The skip predicate is on WHO MIGHT CALL, not on WHERE THE STRING APPEARS. Step-5 must clarify: which tests in the 4 enumerated files actually risk a real API call?

**E6.** AC7 timing tolerance: R1 caught the static-clock variant correctly. ONE more concern: `test_capture.py:158` uses a wall-clock `time.time()` call. CI runners can have clock drift up to ~1 second on cold start. Even `<= 3601` may flake under extreme load. Mitigation: widen to `<= 3602` for safety margin, OR mark `@pytest.mark.flaky(reruns=3)` after installing `pytest-rerunfailures`. Step-5 can pick.

### Area C — Strict CI gate

**E7.** AC8 dropping `continue-on-error: true`: this commits the cycle to first-time-correctness on the strict gate. The chicken-and-egg risk (T9 in threat model) is real. Mitigation: push the AC1-AC11 fixes WITHOUT AC8 (keep continue-on-error) on a probe branch, observe full CI green, then add AC8 in a separate commit on the same branch. If the post-AC8 CI is red, only the AC8 commit needs reverting.

**E8.** AC9 `--ignore-vuln` set: my dependabot probe shows 4 alerts (3 litellm, 1 ragas). Workflow currently has 4 `--ignore-vuln` flags but they include `GHSA-xqmj-j6mv-4862` (ONE litellm) + `CVE-2026-6587` (ragas) — only 2 of the 3 litellm GHSAs are covered. Missing: `GHSA-r75f-5x8p-qvmc` AND `GHSA-v4p8-mg3p-g94g`. CI is currently passing pip-audit which means EITHER:
   - pip-audit only emits ONE advisory ID per package even when multiple exist, OR  
   - pip-audit's behaviour changed since cycle-32 / cycle-35 reads
   
**Verification:** Step-5 should run `pip-audit --format json` against CI's installed env and inspect actual advisory IDs reported. AC20 must add ALL missing GHSAs to both SECURITY.md table AND workflow `--ignore-vuln` list.

### Area D — Cross-OS matrix

**E9.** AC11 enumeration is partly stale (R1-NEW-1 confirms). My ubuntu-probe via grep shows additional unguarded sites:
- `tests/test_backlog_by_file_cycle1.py:622` (`symlink_to`)
- `tests/test_backlog_by_file_cycle2.py:149` (`symlink_to`)
- `tests/test_capture.py:682` (`symlink_to(...target_is_directory=True)`)
- `tests/test_cycle19_manifest_key_consistency.py:283/307` (`symlink_to(target_is_directory=True)`)
- `tests/test_cycle29_rebuild_indexes_hardening.py:319/335` (`os.symlink`)
- `tests/test_phase45_theme3_sanitizers.py:415` (`symlink_to`)

NOT all of these need skipif — POSIX runners CAN create symlinks; Windows runners cannot without admin/dev-mode. So tests needing symlinks are POSIX-OK / Windows-may-need-skipif. The current cycle-36 windows-latest ALREADY runs these — which suggests they pass via runtime `pytest.skip(OSError)` patterns or similar. AC12 matrix expansion is fine; AC11 should be replaced by AC13's data-driven probe.

### Area E — Requirements split (deferred per Q7=B)

**E10.** Brainstorm Q7=B drops Area E. R1 agreed. R2 agrees too — Area E adds maintenance surface for marginal user benefit; deferring to cycle-37 keeps cycle-36 focused on the test-CI hardening that has actual breakage.

### Area F — CVE recheck

**E11.** Dependabot alert #15 (`GHSA-v4p8-mg3p-g94g` litellm) — my probe shows it was created 2026-04-25T23:37Z, just hours before cycle-35 hotfix at 04:00Z. AC20 adds it correctly. ONE concern: alert #14 (`GHSA-r75f-5x8p-qvmc`) is the litellm CRITICAL-severity advisory, NOT in current `--ignore-vuln` list, but pip-audit on CI doesn't fail on it. Hypothesis: pip-audit reports advisories with explicit `--ignore-vuln` skipping; if the advisory ID isn't in the ignore list and pip-audit doesn't report it, then pip-audit's data source (PyPI advisory db) doesn't yet have the GHSA mapping. Verification needed in Step-5: run `pip-audit --strict --format json` on CI's installed env to see what IDs it actually reports.

### Area G — Documentation

**E12.** AC25 `docs/reference/testing.md` shows stale `2941 / 254 files` count. After cycle-36, the count after applying skipif markers will be:
- Total collected: 2995 (from cycle 35 baseline) + 5-10 NEW cycle-36 tests in `test_cycle36_ci_hardening.py`
- Total run on Windows: 3000 - <skipif count>
- Total run on POSIX (matrix): 3000 - <Windows-only skipif count> - <new POSIX-only skipif count if any>

Estimating with R1's count: ~2-3 unguarded Windows-only tests get skipif (from AC11). Plus cycle-23 multiprocessing skipif. Plus 2 wiki-content tests if AC5 adds skipif (vs mirror-rebind). Plus 4 API-key tests (AC6). Total skipif additions: ~9-13. Net Windows test count: ~2987-2991 passing + ~13-17 skipped.

Step-5 must commit to: which tests get skipif vs which use mirror-rebind. The doc update count depends on this decision.

## 2. Slow-test enumeration (for pytest-timeout AC3)

Local suite ran in ~50s (per CI log, which capped at 38% in 50.7s ≈ tests <= 1.7s avg through #1151). Tests >5s should be enumerated for `@pytest.mark.timeout(N)` overrides on the 120s default.

I ran `pytest tests/test_cycle23_file_lock_multiprocessing.py tests/test_cycle5_hardening.py -v --durations=20` and observed:
- All durations < 1.2s
- The cycle-23 multiprocessing test: 1.03s
- The wall-clock cycle-5 tests: 0.8-1.1s

`@pytest.mark.integration` is used by 2 tests. No `@pytest.mark.slow` or `@pytest.mark.llm` tests exist (greps returned nothing in tests/ directories beyond the marker decorator definitions in `pyproject.toml`).

Conclusion: 120s is GENEROUS. No per-test override needed for current suite. New cycle-36 tests must stay below 60s for safety margin.

## 3. OS-specific test enumeration (for AC11)

My grep of `os\.symlink|symlink_to|sys\.platform|os\.name` across `tests/` returned 13 distinct files. R1 enumerated this; my analysis adds:

**Already-correctly-gated (do not touch):**
- `test_cycle10_validate_wiki_dir.py:39` — `skipif(sys.platform == "win32")` — POSIX-only
- `test_phase45_theme3_sanitizers.py:396-399` — `skip_unless_(os.name == "nt") + ALLOW_SYMLINK_TESTS env` — POSIX-by-default opt-in
- `test_capture.py:674` — `skipif(sys.platform == "win32")` symlink
- `test_cycle20_windows_tilde_path.py:54` — `skipif(sys.platform != "win32")` — Windows-only
- `test_cycle19_manifest_key_consistency.py:283-323` — partial gating
- `test_cycle22_wiki_guard_grounding.py:151-176` — runtime `pytest.skip(OSError)` — dynamic
- `test_cycle29_rebuild_indexes_hardening.py:314-335` — `skipif(os.name == "nt")` POSIX-only

**Unguarded — actually needing skipif on POSIX runner:**
- `test_cycle11_utils_pages.py:32` (`test_page_id_normalizes_backslashes_to_posix_id`) — Windows backslash semantics; `\` is literal char on POSIX → assertion would fail
- `test_v0915_task09.py:396` (`test_absolute_path_rejected`) — Windows-style absolute path detection (drive letters); POSIX returns different result
- `test_capture.py::test_kind_prefix_immunizes_windows_reserved` (verified CON/AUX/PRN handling — production code blocks these UNIVERSALLY, not OS-conditional, so test passes on POSIX too)
- `test_capture.py::TestCycle9Task9And10Regressions::test_title_with_backslash_round_trips` — yaml escaping of backslash; OS-agnostic, no skipif needed

**Unguarded — actually needing skipif on Windows runner (POSIX-only):**
- `test_backlog_by_file_cycle1.py:622` — `symlink_to(real_log)` — needs investigation; production code may handle Windows OK
- `test_backlog_by_file_cycle2.py:149` — `symlink_to(real_log)` — same
- `test_capture.py:682` (in `TestSymlinkGuard::test_symlink_outside_project_root_refuses_import`) — needs check; may already be POSIX-only

**Net AC11 enumeration after my analysis:** ~2 confirmed Windows-only (test_cycle11_utils_pages.py:32 + test_v0915_task09.py:396) + ~3-5 to-be-investigated via probe. R1's recommendation Q5=B (probe ubuntu first) is correct.

## 4. Wiki-content monkeypatch chain analysis (for AC5)

`kb.config.WIKI_DIR` is imported at module-top in 3 src/kb/ modules (verified by grep):
- `src/kb/utils/pages.py:11` — `from kb.config import WIKI_DIR, WIKI_SUBDIR_TO_TYPE`
- `src/kb/graph/builder.py:19` — `from kb.config import WIKI_DIR`
- `src/kb/graph/export.py:7` — `from kb.config import WIKI_DIR`

Other modules use call-time `from kb.config import WIKI_DIR as ...` or `kb.config.WIKI_DIR` dynamic lookup — no snapshot hazard.

The 2 affected `test_cycle10_quality.py` tests already mirror `kb.review.refiner.WIKI_DIR + kb.compile.linker.WIKI_DIR + kb.mcp.quality.WIKI_DIR`. Adding `kb.config.WIKI_DIR` covers the snapshot pre-binding hazard cycle-18 L1.

But also missing for these tests: `kb.utils.pages.WIKI_DIR + kb.graph.builder.WIKI_DIR + kb.graph.export.WIKI_DIR` (the 3 module-top snapshot bindings). If the call chain `kb_refine_page → ... → kb.utils.pages.<helper>` reaches the pages-module snapshot, the test would break.

**Verification needed at Step-5:** trace `refine_page` → `refiner_helpers` → does it call `kb.utils.pages.X` for any path-using `X`? If yes, AC5 must mirror those too. If no, AC5 as-written is sufficient.

## 5. Per-AC scoring

R1 Opus's per-AC scoring is fundamentally correct. R2 deltas:

| AC | R1 verdict | R2 delta | Combined |
|---|---|---|---|
| AC1-AC4 | APPROVE | E1 risk: tests #1156+ unreached on CI | APPROVE — but split CI changes into probe + strict-gate pushes |
| AC5 | APPROVE | E4 doubt: test may pass on windows-latest already; AC5 adds POSIX coverage but isn't fixing windows-latest CI breakage | APPROVE-WITH-VERIFICATION (Step-5 trace `refine_page` call chain) |
| AC6 | APPROVE | E5: scope shifts from "literal `anthropic.Anthropic(api_key=`" to "any code path that ultimately calls Anthropic SDK" | APPROVE-WITH-RESCOPE |
| AC7 | APPROVE (wall-clock only) | E6: even `<= 3601` may flake; consider `<= 3602` or `pytest.mark.flaky` | AMEND — pick wider tolerance OR flaky |
| AC8 | APPROVE | E7: chicken-and-egg risk; split into probe push + strict-gate push | APPROVE-WITH-SEQUENCING |
| AC9 | APPROVE | E8: 2 of 4 litellm GHSAs missing from `--ignore-vuln`; verify pip-audit actual report | AMEND — verify and add missing IDs |
| AC10 | APPROVE | none | APPROVE |
| AC11 | AMEND (R1) | E9: enumeration is partly stale; ~2 confirmed unguarded + 3-5 to probe | AMEND — replace with AC13 probe-driven list |
| AC12 | APPROVE | none | APPROVE |
| AC13 | APPROVE | merge with AC11's enumeration phase | APPROVE-FOLD-IN |
| AC14-17 | APPROVE-CONDITIONAL | E10: Area E defer agreed | DEFER per Q7=B |
| AC18-19 | APPROVE | none | APPROVE |
| AC20 | APPROVE | E8+E11: must add 2 more litellm GHSAs (`r75f-5x8p-qvmc`, `v4p8-mg3p-g94g`) | AMEND |
| AC21-26 | APPROVE | E12: test count after skipif depends on Step-5 mirror-rebind-vs-skipif decision | APPROVE — defer count to Step-12 doc update |

## 6. Per-Q answer scoring

R2 fully agrees with R1's per-Q scoring. Brainstorm Q1=A / Q2=B / Q3=A / Q4=A / Q5=B / Q6=B / Q7=B all sound.

| Q | R1 | R2 | Combined |
|---|---|---|---|
| Q1 multiprocessing skip | AGREE | AGREE — but BACKLOG entry must be specific about the GHA-Windows spawn divergence | AGREE |
| Q2 timeout 120s | AGREE | AGREE — slow-test profile validates 120s headroom | AGREE |
| Q3 mirror-rebind | AGREE | AGREE-WITH-VERIFICATION (E4) | AGREE if verification passes |
| Q4 requires_real_api_key | AGREE | AGREE-WITH-RESCOPE (E5) | AGREE with Step-5 rescope |
| Q5 probe ubuntu first | AGREE-STRONG | AGREE-STRONG | AGREE-STRONG |
| Q6 layered -r requirements | AGREE | DEFER per Q7=B | DEFER |
| Q7 drop Area E | AGREE | AGREE | AGREE |

## 7. NEW issues / open questions surfaced by this eval

**R2-NEW-1.** AC8 should land on a SEPARATE commit AFTER all the marker fixes are verified green via probe push. Single-PR atomicity (T9) is insufficient mitigation — a probe-fix-strict 3-step landing pattern is safer.

**R2-NEW-2.** AC9's `--ignore-vuln` set is inconsistent with current Dependabot alerts. Step-5 must reconcile. Likely pip-audit's PyPI advisory db is not 1:1 with GitHub's GHSA db, so the current `--ignore-vuln` set may be CORRECT for what pip-audit emits even though the GHSA list is longer. Verify via `pip-audit --format json` on CI's pyproject-extras-installed env.

**R2-NEW-3.** AC5 may be patching a non-problem (the affected tests pass on windows-latest CI). Step-5 should explicitly determine whether AC5 is (a) preserving POSIX-runner success after AC12 matrix introduction, OR (b) fixing windows-latest CI failures. If only (a), AC5's priority is lower.

**R2-NEW-4.** R1-NEW-5 (AC6 literal-string assumption) deserves stronger attention: AC6 currently SCOPES the helper to 4 specific test files. If those files don't actually risk a real API call (no anthropic.Anthropic constructor in test bodies), AC6 may be unnecessary OR mis-targeted. Step-5 must trace the call chain.

**R2-NEW-5.** AC11 "anti-Windows" skipif vs "anti-POSIX" skipif: R1's enumeration mixed both directions. Step-5 should produce two distinct lists (skipif POSIX and skipif Windows) and apply each correctly.

**R2-NEW-6.** Chicken-and-egg ordering for cycle-36 PR: see R2-NEW-1. Recommend Step-5 design gate explicitly mandates this split.

**R2-NEW-7.** Test count after AC11+AC2+AC5+AC6 skipif additions: net change ~9-13 added skips. CHANGELOG numeric claims must reflect this. Step-12 doc update should re-collect via `pytest --collect-only` after each fix-cascade per cycle-23 L4.

---

## Summary

R2 (primary-session fallback) confirms R1 Opus's APPROVE-WITH-AMENDMENTS verdict and adds 7 NEW concerns focused on:
1. Sequencing of AC8 strict-gate landing (probe-fix-strict pattern)
2. Mismatch between Dependabot alerts and pip-audit ignore-vuln set
3. Verification that AC5 + AC6 actually fix real CI failures, not pre-emptive patches
4. AC11 enumeration accuracy (R1's R1-NEW-1)
5. Test count drift across the cycle's marker additions

Cycle scope at ~23 ACs (Q7=B) is right-sized; 7 brainstorm + 8 R1-new + 7 R2-new = 22 open questions/concerns, well within Step-5's resolution capacity. Cycle-19 L4 R3 trigger should fire (>=10 design-gate questions resolved + new enforcement points: skipif markers, pytest-timeout, CI matrix, requirements-* drift detection).

**Headline:** APPROVE-WITH-AMENDMENTS — proceed to Step-5 design gate after the AC3/AC5/AC6/AC7/AC9/AC11/AC20 amendments land.
