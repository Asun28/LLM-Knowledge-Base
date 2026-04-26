# Cycle 36 — R1 (Opus) Step-4 Design Eval

**Date:** 2026-04-26
**Reviewer:** R1 / Opus 4.7 (1M context)
**Inputs:** Step-1 requirements, Step-2 threat model, Step-3 brainstorm
**Branch:** `feat/backlog-by-file-cycle36`
**Verdict in one line:** APPROVE-WITH-AMENDMENTS — recommended Q1=A / Q2=B / Q3=A / Q4=A / Q5=B / Q6=B / Q7=B is sound; the brainstorm's Q2 amendment from `60s` to `120s` is correct and AC3 in the requirements doc must be edited to match.

---

## 1. Verification table (symbols)

Greps run against `src/`, `tests/`, `pyproject.toml`, root files. All paths absolute under `D:\Projects\llm-wiki-flywheel\`.

| Symbol / artefact | Where found | Status |
|---|---|---|
| `_validate_path_under_project_root(path, field_name)` | `src/kb/compile/compiler.py:616, 695, 703, 708` | EXISTS — matches CLAUDE.md guidance |
| `_validate_page_id` | `src/kb/mcp/app.py:250`; called from `kb/mcp/browse.py:92`, `kb/mcp/quality.py:47/83/140/178/207/279/366/438` | EXISTS — MCP-boundary anchor confirmed |
| `kb.utils.io.file_lock` | `src/kb/utils/io.py:294` (with backoff at L277) | EXISTS — cycle-23 lock under test |
| `tests/_helpers/api_key.py::requires_real_api_key` | none | MISSING — planned in AC6 (helper to be CREATED). Only references are inside the cycle-36 decision docs themselves. No `tests/_helpers/` directory exists today. |
| `tests/test_cycle36_ci_hardening.py` | none | MISSING — planned new file (blast-radius line 137) |
| `requirements-runtime.txt` / `-hybrid.txt` / `-augment.txt` / `-formats.txt` / `-eval.txt` / `-dev.txt` | none | MISSING — planned in AC14-AC15. Only `requirements.txt` exists at repo root |
| `pytest-timeout` (pip dep) | none in `pyproject.toml`/`requirements.txt` | MISSING — planned in AC3 |
| `[tool.pytest.ini_options] timeout = N` | `pyproject.toml` `addopts` carries no timeout | MISSING — planned in AC3 |
| `test_cycle23_file_lock_multiprocessing.py::test_cross_process_file_lock_timeout_then_recovery` | `tests/test_cycle23_file_lock_multiprocessing.py:56` | EXISTS — already `@pytest.mark.integration`; uses `mp.get_context("spawn")` |
| `test_cycle10_quality.py::test_kb_refine_page_surfaces_backlinks_error_on_failure` | `tests/test_cycle10_quality.py:7` | EXISTS — already monkeypatches `kb.review.refiner.WIKI_DIR` + `kb.compile.linker.WIKI_DIR` + `quality.WIKI_DIR`. Missing `kb.config.WIKI_DIR` per AC5 |
| `test_kb_affected_pages_surfaces_shared_sources_error_on_failure` | `tests/test_cycle10_quality.py:28` | EXISTS — same monkeypatch shape |
| `test_capture.py::test_over_cap_rejected_with_retry_after` (`<= 3600`) | `tests/test_capture.py:158, asserting at 165` | EXISTS — assert at L165 |
| `test_capture.py::test_over_cap_retry_after_static_clock_is_one_hour` (`== 3600`) | `tests/test_capture.py:167-175` | EXISTS — uses monkeypatched static `time.time`; equality assert is fine — does NOT need widening (T7-style false-positive cannot occur with frozen clock) |
| `test_cycle10_validate_wiki_dir.py::test_validate_wiki_dir_symlink_to_outside_rejected` | `tests/test_cycle10_validate_wiki_dir.py:39-40` | EXISTS — and ALREADY HAS `@pytest.mark.skipif(sys.platform == "win32", ...)` (REVERSE direction!). See finding R1-NEW-1 below. |
| `test_cycle11_utils_pages.py::test_page_id_normalizes_backslashes_to_posix_id` | `tests/test_cycle11_utils_pages.py:32` | EXISTS — no skipif yet |
| `test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected` | `tests/test_phase45_theme3_sanitizers.py:399`; the file already gates with `os.name == "nt" and not ALLOW_SYMLINK_TESTS` at L396 | EXISTS — semi-gated; the existing condition SKIPS on Windows unless opt-in env-var. Actually the OPPOSITE of what AC11 enumerates. See R1-NEW-1. |
| `test_v0915_task09.py::TestValidatePageIdAbsoluteCheck::test_absolute_path_rejected` | `tests/test_v0915_task09.py:396` | EXISTS — no skipif yet |
| `TestExclusiveAtomicWrite` class | `tests/test_capture.py:693` | EXISTS — body uses `tmp_captures_dir` only. NO `os.symlink` calls. Privileged-symlink concern in requirements is unfounded for this class. The actual symlink test in `test_capture.py` is at L674 (`test_capture_symlink_chase`-style block) with skipif `sys.platform == "win32"` already. See R1-NEW-2. |
| dummy CI key `sk-ant-dummy-key-for-ci-tests-only` | `.github/workflows/ci.yml:38` | EXISTS — confirmed prefix |
| `--ignore-vuln=` set in CI | `.github/workflows/ci.yml:111-114` (4 IDs: CVE-2025-69872, GHSA-xqmj-j6mv-4862, CVE-2026-3219, CVE-2026-6587) | EXISTS — matches `SECURITY.md` 1:1 today |
| `langchain-openai>=1.1.14` | `pyproject.toml:45` | EXISTS — cycle-35 floor pin in `[eval]` |
| `litellm>=1.83` | `pyproject.toml:37` | EXISTS — pinned at the 1.83.0 floor |
| `import litellm` / `from litellm` | none in `src/` | NOT IMPORTED — `grep src/` returned no files. Confirms narrow-role acceptance posture in `SECURITY.md`. |
| `GHSA-v4p8-mg3p-g94g` | none in repo (other than decision docs) | MISSING from `SECURITY.md` and `ci.yml` `--ignore-vuln` — AC20 plans to add |

**Net:** every symbol cited in a requirements-doc AC is either (a) already present and exercised, or (b) explicitly planned to be created in the same cycle. No phantom-symbol REJECTs. Two AMENDMENTs surfaced from existing-but-different-shape evidence (R1-NEW-1, R1-NEW-2 in §5 below).

---

## 2. Monkeypatch / cross-OS enumeration counts

### `WIKI_DIR` monkeypatch sites (T1 / AC5 sizing)

Three greps were run as the prompt mandated:

| Form | Hits |
|---|---|
| `patch("kb.…WIKI_DIR"` (string-form `unittest.mock.patch`) | ~50 hits across 19 files (`test_cli.py`, `test_ingest.py`, `test_v090.py`, `test_phase4_audit_security.py`, `test_tier1_audit_v095.py`, `test_tier2_audit_v096.py`, `test_review_fixes_v099b.py`, `test_v070.py`, `test_v0912_phase393.py`, `test_v0913_phase394.py`, `test_v0916_task07.py`, `test_fixes_v060.py`, etc.) |
| `monkeypatch.setattr(.*WIKI_DIR` (reference + string forms) | ~110 hits across ~25 files |
| `WIKI_DIR =` (variable assignment in tests) | 1 hit (`test_cycle12_config_project_root.py:27` — assertion against `config.WIKI_DIR`, not an assignment) |
| Total `WIKI_DIR` token across `tests/` | 204 occurrences, 45 files |

**Implication for AC5.** AC5 only widens 2 specific tests in `test_cycle10_quality.py` (one already mirrors three modules, one mirrors two). The 50+ `patch(...)` callsites are an ALREADY-ESTABLISHED idiom — they prove the cycle-18 / cycle-19 mirror-rebind pattern is widely understood. AC5 is a *targeted* fix, not a sweeping one. The current state of `test_cycle10_quality.py:7` shows it already patches `kb.review.refiner.WIKI_DIR + kb.compile.linker.WIKI_DIR + quality.WIKI_DIR`; AC5 only adds the missing `kb.config.WIKI_DIR` snapshot binding. **AC5 scope is correct as written; no widening needed for cycle-36.** The 200-site enumeration confirms cycle-37 widening is unnecessary because each site is already locally mirror-correct (modulo any future regressions, which the cycle-19 lint check catches at AST scan time).

### Cross-OS test enumeration (T6 / AC11 sizing)

Combined grep on `os\.symlink|symlink_to|sys\.platform|os\.name` across `tests/` returned hits in 13 files. Distilled into the OS-conditional flavour:

| File:line | Current state | AC11 disposition |
|---|---|---|
| `test_cycle10_validate_wiki_dir.py:39` | **Already `skipif(sys.platform == "win32")`** — runs on POSIX only, not Windows | AC11 enumeration is **WRONG-DIRECTION** (R1-NEW-1) |
| `test_cycle11_utils_pages.py:32` | unguarded | needs `skipif(sys.platform != "win32")` per AC11 |
| `test_phase45_theme3_sanitizers.py:396-399` | `os.name == "nt" and not env(ALLOW_SYMLINK_TESTS)` — i.e. RUNS on POSIX, SKIPS on Windows unless opt-in | AC11 enumeration also REVERSED here |
| `test_v0915_task09.py:396` | unguarded | needs `skipif(sys.platform != "win32")` per AC11 |
| `test_capture.py:674` | already `skipif(sys.platform == "win32", reason="symlink creation requires admin on Windows")` | already correctly POSIX-only |
| `test_cycle19_manifest_key_consistency.py:283-323` | `skipif(not sys.platform.startswith("win"))` at L323 + earlier symlink ops at L283/307 | partially gated; symlink ops at 283/307 may need explicit guard |
| `test_cycle22_wiki_guard_grounding.py:151-176` | runtime `pytest.skip(...)` on `OSError` | dynamic skip — fine |
| `test_cycle29_rebuild_indexes_hardening.py:314-335` | `skipif(os.name == "nt", ...)` then runs `os.symlink` on POSIX | already correctly Windows-only or POSIX-only depending on intent |
| `test_cycle20_windows_tilde_path.py:54` | `skipif(sys.platform != "win32")` | already correctly Windows-only |
| `test_cycle11_cli_imports.py:123` | `if os.name == "nt": …` branch | inline guard, no decorator needed |
| `test_v0914_phase395.py:191` | `if sys.platform == "win32": …` branch | inline guard |
| `test_backlog_by_file_cycle1.py:622` + `test_backlog_by_file_cycle2.py:149` | `symlink_to` calls, no decorator | needs investigation — POSIX-only or runtime-skip? Cycle-37 candidate |

**Total tests touched by OS-conditional code:** 13 files. **Tests that match AC11's literal enumeration:** 2 of the 6 listed (`test_cycle11_utils_pages.py`, `test_v0915_task09.py`). **Two of the 6 listed are already gated in the OPPOSITE direction** (`test_cycle10_validate_wiki_dir.py`, `test_phase45_theme3_sanitizers.py`). **One (`TestExclusiveAtomicWrite`)** has no symlink calls at all. **The 6th** ("Plus any `os.symlink`-based tests that fail with `PermissionError` on Windows") is data-driven and depends on the probe.

**Recommendation:** Q5=B (probe ubuntu first) is therefore even more strongly justified — AC11's literal list is partly stale. **Action: Step 5 design gate must replace the AC11 list with the data-driven probe-result list.** Filing a cycle-37 follow-up for the unenumerated 4-5 sites (`test_backlog_by_file_cycle1.py:622`, `test_backlog_by_file_cycle2.py:149`, `test_cycle19_manifest_key_consistency.py:283/307`) is appropriate.

`pytest --collect-only` was not run in this eval (no venv activation in agent shell). The static grep above is sufficient evidence to require the probe at Step 5.

---

## 3. Per-AC scoring

### Area A — Windows CI hang

**AC1 (identify hanger via binary search):** APPROVE. The brainstorm has already done the binary-search work (`#1155 = test_cross_process_file_lock_timeout_then_recovery`). Step 5 should record this in the investigation doc rather than re-running the search.

**AC2 (skip-or-fix the hang):** APPROVE-AS-WRITTEN with note. `os.environ.get("CI") == "true"` is GHA-specific; if the project ever adds a self-hosted runner that doesn't set `CI`, the gate silently re-enables. Acceptable for cycle-36 — file a cycle-37 candidate to use a more specific marker (`GITHUB_ACTIONS`). Brainstorm Q1=A is the right call (T8 mitigation #4 names the BACKLOG follow-up).

**AC3 (pytest-timeout = 60 default):** AMEND. Brainstorm Q2=B (`120 s`) is correct. The requirements doc still says `60 s` (line 42) — this MUST be edited to `120 s` before Step 7 implementation begins, otherwise the design and requirements docs disagree. T2 explicitly flags 60 s as too aggressive for PageRank/integration tests. Specific change: `requirements.md AC3` → `timeout = 120` (60 s as override candidate); brainstorm Q2 wins.

**AC4 (probe pytest -q after AC1+AC2+AC3):** APPROVE.

### Area B — fragility-class fixes

**AC5 (mirror-rebind to `kb.config.WIKI_DIR` for the 2 quality tests):** APPROVE. The grep confirms the 2 target tests already mirror three of the four owner modules (`kb.review.refiner`, `kb.compile.linker`, `kb.mcp.quality`) but miss `kb.config.WIKI_DIR`. Adding it is mechanical. Fallback to the brainstorm Q3 fixture-seeding (Option C) is unnecessary because the test already calls `create_wiki_page("concepts/rag", ...)`.

**AC6 (`requires_real_api_key()` helper):** APPROVE. `tests/_helpers/` does not exist; AC6 creates `tests/_helpers/api_key.py` and a marker call. Body should be ≤10 lines. The 4 enumerated test files (`test_cycle21_cli_backend.py`, `test_v5_lint_augment_orchestrator.py`, `test_env_example.py`, `test_backlog_by_file_cycle1.py`) cover the `anthropic.Anthropic(api_key=...)` callsites — though my grep found ZERO direct `anthropic.Anthropic(api_key=` matches in `tests/`, which means the actual SDK construction happens via fixture or env-driven path, not literal API-key strings. Step 5 must verify which call shape the affected tests use; the helper still works either way (it gates on the env var, not the literal string).

**AC7 (widen `<= 3600` → `<= 3601`):** APPROVE for the wall-clock test at L165. REJECT the requirements-doc suggestion to widen `test_over_cap_retry_after_static_clock_is_one_hour` at L167-175 — it monkeypatches `time.time` to a static `1000.0` and asserts exact equality `retry_after == 3600`. With a frozen clock, no scheduler/clock-resolution variance is possible; the equality is correct. Read the body before widening, exactly as the requirements doc instructs. Specific change: AC7 should explicitly say "ONLY widen `test_over_cap_rejected_with_retry_after`; verify the static-clock variant remains `== 3600`."

### Area C — Strict gate

**AC8 (drop `continue-on-error` from pytest step):** APPROVE.
**AC9 (verify `--ignore-vuln` set unchanged unless new advisory):** APPROVE.
**AC10 (preserve `continue-on-error` on `pip check` step):** APPROVE — three documented transitive conflicts remain (non-goal #7).

### Area D — Cross-OS matrix

**AC11 (skipif on enumerated 6):** AMEND. Two of the six are already in REVERSED-skipif state today (R1-NEW-1). One (`TestExclusiveAtomicWrite`) has no symlink calls so the rationale doesn't apply (R1-NEW-2). Step 5 design must rewrite AC11 to reflect actual current state. Recommend: drop `TestExclusiveAtomicWrite` from the AC11 list; verify whether `test_cycle10_validate_wiki_dir.py::test_validate_wiki_dir_symlink_to_outside_rejected` and `test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected` are POSIX-only intentionally (per existing skipif), in which case they need NO new skipif — the matrix expansion already handles them correctly. Net surviving AC11 enumeration: 2-3 unguarded tests (`test_cycle11_utils_pages.py:32`, `test_v0915_task09.py:396`, plus possibly `test_backlog_by_file_cycle1.py:622`).

**AC12 (matrix `[ubuntu-latest, windows-latest]`):** APPROVE — preserves `permissions: read-all`, no `secrets.*` exposure (T3-mitigation 1).

**AC13 (verify ubuntu-latest passes; defer extras to cycle-37):** APPROVE. This is the brainstorm Q5=B "probe first" pattern in disguise. Strongly recommend Step 5 fold AC13's probe into AC11's enumeration phase (data-driven enumeration replaces guesswork).

### Area E — Requirements split

**AC14 (`requirements-runtime.txt`):** APPROVE-CONDITIONAL — only if Q7=A or "all 27 ACs" wins. Brainstorm Q7=B drops Area E entirely. Strongly support B.

**AC15 (5 per-extra files):** APPROVE-CONDITIONAL — same gate. T4 raised drift risk between `requirements-*.txt` and `pyproject.toml` extras (cycle-35 L8 lesson). Layered `-r requirements-runtime.txt` per Q6=B partly mitigates.

**AC16 (preserve `requirements.txt` superset):** APPROVE-CONDITIONAL — same gate.

**AC17 (README install-section update):** APPROVE-CONDITIONAL — same gate.

### Area F — CVE recheck

**AC18 (re-snapshot Dependabot alerts):** APPROVE — preserves cycle-22 L4 cross-cycle-CVE arrival discipline.

**AC19 (verify `litellm 1.83.7` still requires `click==8.1.8`):** APPROVE.

**AC20 (`SECURITY.md` 4th litellm row + `--ignore-vuln`):** APPROVE — non-trivial because the `--ignore-vuln` set (4 IDs) and the `SECURITY.md` table (4 packages) must stay 1:1 (T5). Recommend Step 11 add the parsing test from threat-model T5 mitigation #4 (`tests/test_cycle36_ci_hardening.py` cross-references the two sets).

### Area G — Docs

**AC21 (`CHANGELOG.md` Quick Reference compact entry):** APPROVE.
**AC22 (`CHANGELOG-history.md` per-cycle bullet detail):** APPROVE.
**AC23 (`BACKLOG.md` cleanup — delete the 3 cycle-36 entries):** APPROVE — but contingent on Areas D and E shipping. If only A+B+C+F+G ship (Q7=C), only ONE cycle-36 BACKLOG entry deletes (the strict-gate one).
**AC24 (`CLAUDE.md` Quick Reference numbers):** APPROVE — must re-collect via `pytest --collect-only` per cycle-26 L2 (test-count narrative drift).
**AC25 (`docs/reference/testing.md` refresh):** APPROVE — current file shows stale `2941 tests / 254 files (2930 passed + 10 skipped + 1 xfailed)` at L13. Quick Reference says `2995 / 256 (2985 passed + 10 skipped)`. Drift is real; AC25 is the fix.
**AC26 (`README.md` install-section update):** APPROVE-CONDITIONAL — only if Area E ships.

---

## 4. Per-Q answer scoring

| Q | Brainstorm pick | R1 verdict | One-sentence reason |
|---|---|---|---|
| Q1 — multiprocessing fix vs skip | A (skip on CI via env-var marker) | **AGREE** | Spawn-bootstrap divergence on GHA-Windows is genuinely out-of-scope for cycle-36; T8 mitigation #4 captures the cycle-37 follow-up so the bug doesn't get forgotten. |
| Q2 — pytest-timeout default | B (`120 s`) | **AGREE** | The requirements doc still says 60s (line 42); the brainstorm correctly amends to 120s, balancing T2 (false-positive risk) against the catch-hangs goal. AC3 must be edited to match. |
| Q3 — wiki-content-dependent: mirror-rebind vs skipif | A (mirror-rebind monkeypatch chain) | **AGREE** | The targeted test already uses `tmp_wiki + create_wiki_page`; only the `kb.config.WIKI_DIR` mirror is missing. Cycle-19 L1 pattern. |
| Q4 — CI dummy-key strategy | A (`requires_real_api_key()` + skipif) | **AGREE** | Threat-model T7 mitigation #4 explicitly recommends skipif over `MOCK_ANTHROPIC=1`; the latter requires SDK cooperation we don't control. |
| Q5 — Cross-OS matrix scope | B (probe ubuntu first; data-driven enumeration) | **AGREE-STRONG** | My grep evidence confirms AC11's literal list is partly stale (R1-NEW-1, R1-NEW-2); a probe replaces guesswork with data. |
| Q6 — Requirements split-file structure | B (layered `-r requirements-runtime.txt`) | **AGREE** | T4 drift risk is real (cycle-35 L8 lesson); layering minimises duplicate-pin maintenance. |
| Q7 — Cycle scope cap | B (drop Area E; ship ~23 ACs) | **AGREE** | Areas A+B+C+F+G are inseparable (16 must); Area D closes a stated cycle-36 BACKLOG entry; Area E is documentation-only and easily defers. |

---

## 5. Top concerns / open questions for Step-5 design gate

**R1-NEW-1 — AC11 enumeration is partly mis-directional.** Verified by grep: `test_cycle10_validate_wiki_dir.py::test_validate_wiki_dir_symlink_to_outside_rejected` is already `skipif(sys.platform == "win32")` (POSIX-only). `test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected` is already gated `os.name == "nt" and not env("ALLOW_SYMLINK_TESTS")` (POSIX-by-default). AC11 lists both as "needs `skipif(sys.platform != "win32")` (Windows-only)" — opposite direction. **Step 5 design must rewrite AC11 to reflect actual current state and rely on AC13's probe to surface the real list.** This also affects expected post-AC11 skip count (T1 mitigation #4 collect-only diff).

**R1-NEW-2 — `TestExclusiveAtomicWrite` has no `os.symlink` calls.** Read of `tests/test_capture.py:693-731` shows the class uses `tmp_captures_dir`, `_exclusive_atomic_write`, `os.replace` monkeypatches — no symlink ops. The privileged-symlink rationale in AC11 line 70 (`if os.symlink privileged-call`) does not apply. The symlink-bearing test at `test_capture.py:674` is already correctly gated `skipif(sys.platform == "win32")`. AC11 should drop `TestExclusiveAtomicWrite` from the enumeration.

**R1-NEW-3 — AC3 `60 s` ↔ Q2 brainstorm `120 s` mismatch.** Pre-implementation edit needed; otherwise Steps 7 and 9 will diverge on what the in-pyproject-toml value actually is. Trivial to fix; flag for Step 5 ratification.

**R1-NEW-4 — AC7 fix would unsoundly widen the static-clock test.** The wall-clock variant at `tests/test_capture.py:165` (`assert retry_after <= 3600`) genuinely needs `<= 3601` widening. The static-clock variant at L167-175 (`assert retry_after == 3600`) does NOT — `time.time` is monkeypatched to a constant. Widening that one to `<= 3601` would weaken a deterministic assertion. AC7 should explicitly distinguish the two (the requirements doc currently says "Same fix on `test_over_cap_retry_after_static_clock_is_one_hour` if needed (verify by reading the test body)" — verification result: NOT NEEDED).

**R1-NEW-5 — AC6's literal-string assumption uncertain.** No `anthropic.Anthropic(api_key=` strings in `tests/`; the SDK construction must be happening via fixtures or env-driven init. The helper-as-predicate still works (it gates on `os.environ.get("ANTHROPIC_API_KEY")`), but the threat-model T7 verification step "Grep for `anthropic.Anthropic(api_key=` outside test fixtures" returns zero — Step 11 should adjust to grep for `anthropic.Anthropic(` more broadly OR for the import + init pattern that the SDK actually uses in tests.

**R1-NEW-6 — `WIKI_DIR` monkeypatch surface is huge but stable.** 204 occurrences across 45 files. AC5 widens 2 of those tests to add `kb.config.WIKI_DIR`. The rest already follow the cycle-18/19 pattern. **No cycle-37 widening of this surface is recommended.** This addresses the prompt's "If >5 sites, AC5 may need to widen scope OR cycle-37 follow-up entry" question: 200+ sites is huge but the existing pattern is already correct; only the 2 quality tests are deficient.

**R1-NEW-7 — pytest-timeout interaction with `mp.Event.wait(15.0)`.** The cycle-23 test uses internal mp-Event timeouts (15s + 10s + 5s = 30s typical). With `pytest-timeout = 120` (Q2=B) the pytest timeout dominates only on hangs, not happy-path. Brainstorm "Risks not addressed in Step 1" already raises this; AC2 skipif on CI sidesteps it entirely. Worth a one-line explicit acknowledgement in the design doc.

**R1-NEW-8 — Cycle scope at 23 ACs (Q7=B) — R3 trigger threshold.** Requirements doc line 176 says "(d) >=10 design-gate questions resolved" likely fires given the 7 open questions plus my 6 NEW concerns above (13 total). Plan accordingly: Step 11 should run 3-round PR review per `feedback_3_round_pr_review.md` if scope hits 25+ items.

---

## 6. Recommended NEW open questions surfaced by this eval

**NEW-Q1.** Should AC11's enumeration be REPLACED by AC13's probe-driven enumeration (i.e., AC11 becomes "TBD pending probe" until AC13 surfaces the real list)? Verified above that the literal AC11 list is partly stale.

**NEW-Q2.** Does AC7's static-clock test (`test_over_cap_retry_after_static_clock_is_one_hour`) need ANY change? My read says NO (frozen clock → exact equality is sound). Step 5 should explicitly resolve this.

**NEW-Q3.** Should AC2's skip predicate be `GITHUB_ACTIONS` instead of `CI`? The latter is set by every CI provider; the former is GHA-specific. Cycle-36 default of `CI` is fine; cycle-37 cleanup possible.

**NEW-Q4.** Should the requirements doc's AC3 line ("60 s default") be edited to "120 s default" before Step 7 implementation, or does Step 5 ratify the brainstorm Q2=B amendment in-place?

**NEW-Q5.** Will AC6's helper test pass on a developer's real-key environment (`ANTHROPIC_API_KEY=sk-ant-api-...`) without burning credits? Threat-model T7 mitigation #2 requires a behaviour test "Returns True when `ANTHROPIC_API_KEY == sk-ant-real-looking-key`". The helper itself must NOT make any API call; only the dependent test does, and the developer-machine run is a known cost.

**NEW-Q6.** Does Step 11's `tests/test_cycle36_ci_hardening.py` parsing test for `requirements-*.txt` ↔ `pyproject.toml` extras need to be skipif'd if Area E is dropped (Q7=B)? Yes — drop the parsing test along with Area E. Step 5 should ratify the linkage.

**NEW-Q7.** Should the design doc note the dummy-key prefix `sk-ant-dummy-key-for-ci-tests-only` in `docs/reference/testing.md` AC25 update (per threat-model T7 verification step #4)? Recommend YES — preserves audit trail for future contributors.

---

## Summary

The cycle-36 design is fundamentally sound. The brainstorm's Q1-Q7 picks (A/B/A/A/B/B/B) all hold up under symbol verification, with one important correction: **AC3 default must be 120s (Q2=B), not the 60s in the requirements text**. AC11's enumeration needs Step-5 amendment because two of its six entries are already gated in the opposite direction and a third has no symlink calls — the brainstorm Q5=B probe-first approach is the correct path. AC7 should explicitly preserve the static-clock test's exact-equality assertion. The blast radius (~23 ACs across 7 areas under Q7=B) is right-sized; cycle-37 follow-up entries cover the deferred items (Area E, the unenumerated symlink tests, the GHA-Windows spawn root cause, and the click<8.2 vs click==8.3.2 transitive constraint). No phantom-symbol REJECTs; no source-code changes; merge-gate semantics tighten without expanding attack surface.

**Headline:** APPROVE-WITH-AMENDMENTS — proceed to Step 5 design gate after the AC3/AC7/AC11 textual edits land.
