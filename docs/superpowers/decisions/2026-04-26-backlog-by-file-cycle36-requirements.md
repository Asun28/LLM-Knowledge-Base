# Cycle 36 — Requirements + Acceptance Criteria

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle36`
**Theme:** Test infrastructure hardening — close the three explicit cycle-36 BACKLOG items (strict pytest CI gate, cross-OS portability, requirements.txt split) plus opportunistic CVE recheck. Discovery during Step-2 baseline: CI is silently hanging on a Windows multiprocessing test at ~38% (1151/2995 tests). Strict-gating without diagnosing this first would block every PR.

---

## Problem

Cycle 34 bootstrapped CI but accepted three explicit cycle-36 follow-up items (BACKLOG.md MEDIUM, Phase 4.5):

1. **Strict pytest CI gate** — current `pytest -q` step is `continue-on-error: true` masking pre-existing test fragility.
2. **Cross-OS portability** — the 2995-test suite was authored on Windows; ~6+ tests assume Windows path semantics. Cycle 34 ran on `windows-latest` only.
3. **Requirements split** — `requirements.txt` is a full-dev superset; users wanting minimum-install paths have no `requirements-runtime.txt` etc. matching the pyproject extras.

**Discovery during Step-02 baseline (this cycle):** CI on Windows is silently hanging at ~1151/2995 tests via `multiprocessing\popen_spawn_win32.py:112: KeyboardInterrupt` — confirmed across 3 recent CI runs (run IDs 24947760653, 24947676139, 24945114305). The cycle-23 cross-process file-lock integration test (`test_cycle23_file_lock_multiprocessing.py`) is the leading suspect. The soft-fail step swallows the failure and CI shows green even though only 38% of tests run.

**Plus**: cycle-32/35 deferred CVE recheck is due (Dependabot has 4 open advisories incl. a new `GHSA-v4p8-mg3p-g94g` on litellm not yet in BACKLOG).

## Non-goals

1. **No Phase 5 features.** Pre-Phase-5 items only.
2. **No architectural refactor of `src/kb/`** — this is test/CI infrastructure only.
3. **No new test bodies** — only markers / skips / fixtures / monkeypatch fixes on existing tests.
4. **No CVE acceptance posture changes** — narrow-role exceptions in `SECURITY.md` stay; only ADD entries for new advisories.
5. **No bump of litellm beyond `1.83.0`** — still blocked by `click<8.2` transitive constraint (verified 2026-04-26: PyPI shows `litellm 1.83.7 requires click==8.1.8`; would force downgrading our `click==8.3.2` pin used by cycle-31/32 CLI wrappers).
6. **No new Python features or runtime behavior changes.**
7. **No fixing of intentionally-deferred conflicts** (`arxiv 2.4.1` vs `requests==2.33.0`, `crawl4ai 0.8.6` vs `lxml==6.1.0`, `instructor 1.15.1` vs `rich==15.0.0`) — these stay soft-failed at `pip check` per cycle-34 T5.
8. **No new test coverage** beyond regression tests pinning the cycle-36 fixes themselves.

## Acceptance criteria

Grouped by file/area. Each is testable as pass/fail.

### Area A — Fix the Windows CI hang (root cause for strict gate)

**AC1** — Identify which test causes the `multiprocessing\popen_spawn_win32.py:112` KeyboardInterrupt at ~1151/2995 in Windows CI. Verify by running `pytest -q --tb=line -x` on a probe CI run with verbose output OR by binary-search isolating the test via `pytest tests/<group>/ -q -x`. Document the offending test in `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md`.

**AC2** — Skip or fix the hanging test(s). Default approach: mark with `@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Windows multiprocessing hang under GHA — tracked C36-investigation.md")` so the test still runs locally where it works (cycle 23 verified), but skips on CI runner. Acceptable alternative: if root cause is fixable in the test (e.g., add `child.terminate()` + `child.join(timeout=...)` cleanup), prefer the fix.

**AC3** *(Step-5 amendment 2026-04-26 per Q2/R1-NEW-3)* — Add `pytest-timeout >= 2.3` to `[dev]` extras and `requirements.txt`. Wire into pyproject.toml `[tool.pytest.ini_options] timeout = 120` (120 s default per cycle-36 design Q2=B). Goal: any future hung test fails fast with a traceback instead of silently killing pytest. Skip for tests explicitly marked `@pytest.mark.timeout(N)` for legitimately-slow tests.

**AC4** — After AC1+AC2+AC3, run a probe `pytest -q` locally; assert the suite still passes 2985 + 10 skipped (no regression to existing local tests beyond the marked-skip count). On CI a fresh run should pass 2985 - <skipif count> passing without KeyboardInterrupt.

### Area B — Fix the 3 BACKLOG-listed fragility classes

**AC5** — Wiki-content-dependent tests: `test_cycle10_quality.py::test_kb_refine_page_surfaces_backlinks_error_on_failure` + `test_kb_affected_pages_surfaces_shared_sources_error_on_failure`. The tests already use `tmp_wiki + create_wiki_page`, but the `monkeypatch.setattr("kb.review.refiner.WIKI_DIR", tmp_wiki)` chain doesn't reach the read site — production code reads via `kb.config.WIKI_DIR` snapshot (cycle-18 L1 hazard). Fix: add mirror-rebind monkeypatch on `kb.config.WIKI_DIR` and `kb.mcp.quality.WIKI_DIR` (per `docs/reference/testing.md` "Tests that reach `sweep_stale_pending` / `list_stale_pending` via MCP or CLI" rule, generalised to refine_page). Alternative if mirror-rebind cannot reach: `@pytest.mark.skipif(not (PROJECT_ROOT / "wiki" / "concepts" / "rag.md").exists(), reason="Requires populated wiki")` so the tests only run on developer machines.

**AC6** — Real-API-key-dependent tests: tests that instantiate `anthropic.Anthropic(api_key=...)` and would hang on the dummy CI key. Add a helper `tests/_helpers/api_key.py::requires_real_api_key()` predicate that returns False when `ANTHROPIC_API_KEY` matches the dummy CI key prefix `sk-ant-dummy-key-for-ci-tests-only` OR when the env var is unset. Mark affected tests in `test_cycle21_cli_backend.py`, `test_v5_lint_augment_orchestrator.py`, `test_env_example.py`, `test_backlog_by_file_cycle1.py` with `@pytest.mark.skipif(not requires_real_api_key(), ...)`.

**AC7** — Timing-precision tests: `test_capture.py::test_over_cap_rejected_with_retry_after` asserts `retry_after <= 3600`. CI runners have lower clock resolution; can return 3601 due to floating-point + scheduler variance. Widen tolerance to `retry_after <= 3601` (≥1 s tolerance on the 1-hour boundary). Same fix on `test_over_cap_retry_after_static_clock_is_one_hour` if needed (verify by reading the test body).

### Area C — Strict CI gate

**AC8** — Drop `continue-on-error: true` from the `Pytest full suite` step in `.github/workflows/ci.yml`. Update step name from "(soft-fail per cycle 34 R1 fallback)" to "(strict — cycle 36 closure)". Keep the explanatory comment block intact but rewrite to describe the cycle-36 fixes that closed the soft-fail loophole.

**AC9** — Verify `pip-audit` step retains its narrow-role `--ignore-vuln` flags (4 entries from cycle 34 `SECURITY.md`); ensure no new flags needed (i.e., no NEW Class A advisories that must be accepted). If a new advisory must be accepted, add it to `SECURITY.md` AND the workflow's `--ignore-vuln` list as part of this AC.

**AC10** — Keep `pip check` step `continue-on-error: true` per cycle-34 T5 (the three transitive conflicts are still upstream-unfixed; non-goal #7).

### Area D — Cross-OS matrix (defer-candidate if cycle gets large)

**AC11** — Add `pytest.mark.skipif(sys.platform != "win32", reason="Windows path semantics")` to the ≤6 enumerated Windows-specific tests:
- `tests/test_cycle10_validate_wiki_dir.py::test_validate_wiki_dir_symlink_to_outside_rejected`
- `tests/test_cycle11_utils_pages.py::test_page_id_normalizes_backslashes_to_posix_id`
- `tests/test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected`
- `tests/test_v0915_task09.py::TestValidatePageIdAbsoluteCheck::test_absolute_path_rejected`
- `tests/test_capture.py::TestExclusiveAtomicWrite` (if `os.symlink` privileged-call) — verify by reading test body
- Plus any `os.symlink`-based tests that fail with `PermissionError` on Windows (probe enumerates by reading code)

**AC12** — Add ubuntu-latest to the CI workflow's `runs-on:` via a `strategy.matrix.os: [ubuntu-latest, windows-latest]`. Pip-install commands need no change (pyproject extras work identically on both). Pip-audit `--ignore-vuln` flags identical. The workflow comment block updated to document the matrix rationale.

**AC13** — Verify ubuntu-latest CI run passes after AC11+AC12 — local probe via `WSL` is acceptable proof OR an actual probe-PR CI run. If ubuntu reveals additional fragility classes beyond the 6 already enumerated, file BACKLOG entries for cycle-37 follow-up rather than expanding cycle-36 scope.

### Area E — Requirements split (defer-candidate)

**AC14** — Generate `requirements-runtime.txt` containing only the `[project] dependencies` runtime pins, with strict pins matching `requirements.txt`. Header documents the install path: `pip install -r requirements-runtime.txt` for minimum runtime install.

**AC15** — Generate per-extra requirements files matching pyproject `[project.optional-dependencies]`:
- `requirements-hybrid.txt` — runtime + hybrid extras
- `requirements-augment.txt` — runtime + augment extras
- `requirements-formats.txt` — runtime + formats extras
- `requirements-eval.txt` — runtime + eval extras (incl. `langchain-openai>=1.1.14` cycle-35 hotfix floor)
- `requirements-dev.txt` — runtime + dev extras (testing tools)

**AC16** — Keep `requirements.txt` as the full-dev superset (backwards compat). Update its header to document the new split files and direct users to the right one. No pin changes — preserves `arxiv 2.4.1` and other tooling pins outside pyproject extras.

**AC17** — README.md install section updated to document the four canonical install paths:
- `pip install -e '.[hybrid,augment,formats,eval,dev]'` (recommended for developers)
- `pip install -r requirements.txt` (full-dev superset, backwards compat)
- `pip install -r requirements-runtime.txt` (minimum runtime, no extras)
- `pip install -r requirements-<extra>.txt` (per-extra paths)

### Area F — CVE recheck

**AC18** — Re-snapshot Dependabot alerts via `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts`. Confirm the 4 open alerts (3 litellm + 1 ragas) are unchanged or document any new arrivals. Save snapshot to `.data/cycle-36/alerts-baseline.json` (gitignored).

**AC19** — Verify `litellm 1.83.7` STILL requires `click==8.1.8` (blocking our `click==8.3.2`). If litellm has relaxed the constraint, bump to `1.83.7+` in `requirements.txt` + pyproject `[eval]` extra; otherwise the BACKLOG entry stays.

**AC20** — Update `SECURITY.md` to add the 4th litellm advisory `GHSA-v4p8-mg3p-g94g` to the "Known Advisories" section (same narrow-role acceptance rationale as the existing 3 litellm entries — eval-only dep, no runtime imports). Add to workflow `--ignore-vuln` if it shows up in pip-audit.

### Area G — Documentation + BACKLOG cleanup

**AC21** — `CHANGELOG.md` `[Unreleased]` Quick Reference: add cycle-36 compact entry (Items / Tests / Scope / Detail).

**AC22** — `CHANGELOG-history.md`: full per-cycle bullet detail.

**AC23** — `BACKLOG.md` cleanup:
- Delete the 3 cycle-36 follow-up entries (resolver conflicts row stays — non-goal #7)
- Delete the cycle-32 deferred-CVE-recheck entry once AC18 confirms the state
- Add NEW entry if AC1 reveals a CI-only hang root cause that needs deeper investigation

**AC24** — `CLAUDE.md` Quick Reference: update version (stays 0.11.0), test count (re-collect with `pytest --collect-only | tail -1` after all skipif markers add), tool count, last-cycle reference.

**AC25** — `docs/reference/testing.md`: refresh test count (currently stale at 2941/254); document the new conventions:
- Cross-OS skipif marker pattern
- `requires_real_api_key()` helper
- `pytest-timeout` default + override mechanism
- CI vs local skip strategy

**AC26** — `README.md`: install-section update from AC17 (only if Area E ships).

## Blast radius

**Source files touched (`src/kb/`):** none. This is test+CI infrastructure only (consistent with non-goal #2).

**Test files touched (~10-15):**
- `tests/test_cycle10_quality.py` (AC5)
- `tests/test_capture.py` (AC7 + AC11)
- `tests/test_cycle21_cli_backend.py`, `tests/test_v5_lint_augment_orchestrator.py`, `tests/test_env_example.py`, `tests/test_backlog_by_file_cycle1.py` (AC6)
- `tests/test_cycle10_validate_wiki_dir.py`, `tests/test_cycle11_utils_pages.py`, `tests/test_phase45_theme3_sanitizers.py`, `tests/test_v0915_task09.py` (AC11)
- `tests/test_cycle23_file_lock_multiprocessing.py` (AC2 — primary suspect for hang)
- NEW `tests/_helpers/api_key.py` (AC6 helper)
- NEW `tests/test_cycle36_ci_hardening.py` (regression tests for skipif markers + helper)

**Config files:**
- `.github/workflows/ci.yml` (AC8, AC9, AC12)
- `pyproject.toml` (AC3 — pytest-timeout config + dep)
- `requirements.txt` (AC3, AC14, AC16)
- NEW `requirements-runtime.txt`, `requirements-hybrid.txt`, `requirements-augment.txt`, `requirements-formats.txt`, `requirements-eval.txt`, `requirements-dev.txt` (AC14, AC15)

**Docs:**
- `SECURITY.md` (AC20)
- `BACKLOG.md` (AC23)
- `CHANGELOG.md` (AC21)
- `CHANGELOG-history.md` (AC22)
- `CLAUDE.md` (AC24)
- `docs/reference/testing.md` (AC25)
- `README.md` (AC26 — only if Area E ships)
- NEW `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-*.md` (this requirements doc + threat-model + brainstorm + design + plan + self-review)

**External impacts:**
- CI: drops continue-on-error → any future regression blocks merge. THIS IS THE GOAL but means the cycle MUST land all fixes correctly the first time.
- Cross-OS matrix doubles CI minutes on PR runs (~9 min → ~18 min). Concurrency cancellation already mitigates duplicate runs.
- New requirements-*.txt files = 6 new files; users may need a CHANGELOG note explaining which to use.

## Cycle scope decisions

**MUST land**: Areas A, B, C, F, G (~16 ACs). Without A the strict gate (C) cannot ship; without B the strict gate fails on first run; without F the cycle ships with a known-but-undocumented advisory.

**SHOULD land if scope permits**: Area D (cross-OS matrix, AC11-AC13). Closes a cycle-36 BACKLOG entry but is independent of strict-gate enforcement.

**MAY land if scope permits**: Area E (requirements split, AC14-AC17). Closes a cycle-36 BACKLOG entry but is documentation-side only — no test/CI impact. Defer to cycle 37 if Area D forces narrow scope.

**Decision authority**: Step 5 design gate decides whether D and/or E ship in cycle 36 based on Step 4 design eval risk assessment.

## Open questions for Step 4-5 design eval

1. **AC2 fix vs skip**: do we skip the multiprocessing test on CI (preserves local coverage) or attempt to fix the underlying Windows-runner hang (more durable but unknown effort)?
2. **AC3 pytest-timeout default**: is 60s appropriate? Some legitimate tests (full PageRank computation, integration tests) may need longer. Risk: too aggressive default → false-positive timeout failures.
3. **AC5 alternative**: do we mirror-rebind monkeypatch (deeper fix) or skipif (simpler, preserves test on developer machines only)?
4. **AC6 dummy-key strategy**: does CI need a `MOCK_ANTHROPIC=1` env var so SDK calls hit a stub instead of the real API? Or is skipif on real-key tests sufficient?
5. **Area D scope**: enumerate all Windows-only tests at design-eval time vs trust the BACKLOG enumeration of 6.
6. **Area E split-file behavior**: do `requirements-hybrid.txt` etc. include `requirements-runtime.txt` via `-r requirements-runtime.txt`, OR are they fully self-contained? Self-contained is simpler but duplicates pins.
7. **Cycle scope cap**: 16 (must) + 3 (D) + 4 (E) + ~4 docs = 26-27 ACs. Cycle-19 L4 says R3 fires at >=15 ACs when (a) a new filesystem-write surface, (b) hard-to-reach defensive check, (c) new security enforcement point, OR (d) >=10 design-gate questions resolved. None of (a)-(c) apply; (d) likely fires given the 7 open questions above. Plan accordingly.
