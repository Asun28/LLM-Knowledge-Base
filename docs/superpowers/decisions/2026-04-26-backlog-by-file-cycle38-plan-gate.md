1. FINDING 1 — AC COVERAGE: PASS

All ACs from the design FINAL AC LIST are covered by named tasks in the plan. AC0 is covered by TASK 1, whose criteria line says `AC0 (D-NEW); CONDITIONS §1` and whose change is the `TestSymlinkGuard` subprocess refactor. AC1 is covered by TASK 2, with criteria `AC1; CONDITIONS §2`, and AC2 is covered by TASK 3, with criteria `AC2`. AC5 is covered by TASK 4, which says `Three test cases per CONDITIONS §3`. AC3 and AC4 are covered by TASK 5, titled `AC3 + AC4 remove _REQUIRES_REAL_API_KEY decorators`. AC6 is covered by TASK 6, titled `AC6 widen atomic_text_write patches in 2 tests + drop @_WINDOWS_ONLY`. AC7 and AC8 are covered together by TASK 7, titled `AC7 + AC8 POSIX off-by-one slug + creates_dir probes`. AC9 is covered by TASK 9, titled `AC9 Dependabot drift refresh`. AC10 is covered by TASK 10, titled `AC10 BACKLOG cleanup + cycle-39 fold pre-register + scratch-file hygiene`.

The design Q5 ruff T20 requirement is also covered. The design says `Add ruff T20 to pyproject.toml` and `mandate squash-merge of probe+revert + explicit Step-10 grep`; TASK 8 is titled `Add ruff T20 to pyproject.toml`, Step-9 commit ordering includes `add ruff T20 (flake8-print) for src/ defense (Q5)`, and Step-10 includes `Probe-print escape grep (design Q5)`.

2. FINDING 2 — THREAT COVERAGE: REJECT

T1 is covered: plan TASK 2 and TASK 3 widen `kb.utils.llm.call_llm_json`, TASK 4 adds the AC5 regression, and Step-11 maps T1 to `grep -n "kb.utils.llm.call_llm_json" tests/conftest.py`. T3 is covered by TASK 7 and Step-11 `grep -n "print(" src/kb/capture.py` against the diff. T4 is covered by TASK 9 and Step-11 `git diff main -- BACKLOG.md`. T5 is covered by Step-11 `grep -n "fake_call" tests/conftest.py`. T6 is covered at a verification-step level by Step-10 full pytest and the Step-11 check `CI green`. T7 is covered by the Step-11 `pip-audit --format=json` branch-vs-baseline check.

T2 is not covered as written in the threat model. Threat-model T2 says the new `tests/test_cycle38_mock_scan_llm_reload_safe.py` can leak state into sibling tests and says residual risk should be verified by sibling-order collection/execution. Threat-model §7 gives the concrete command: `python -m pytest ... tests/test_cycle38_mock_scan_llm_reload_safe.py ... tests/test_capture.py -v`. The plan's Step-11 T2 row instead says `TestSymlinkGuard subprocess isolation` and verifies `grep -n "del sys.modules" tests/test_capture.py = 0`. That command verifies AC0, not the T2 sibling-order leak described in the threat model. Because one enumerated threat is uncovered, this finding is REJECT.

3. FINDING 3 — CONDITIONS COVERAGE: PASS

All design CONDITIONS §1-§11 have implementation coverage. §1 maps to TASK 1, which replaces in-process `del sys.modules["kb.capture"]` with `subprocess.run` and verifies zero `del sys.modules` hits. §2 maps to TASK 2, which patches `kb.utils.llm.call_llm_json` before `kb.capture.call_llm_json` and documents `utils.llm FIRST`. §3 maps to TASK 4, which includes cases (a), (b), and (c), `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)`, and a manual revert check. §4 maps to TASK 3, which pairs the two inline `kb.capture.call_llm_json` patches with `kb.utils.llm.call_llm_json`. §5 maps to TASK 5, which removes 7 `test_capture.py` and 3 `test_mcp_core.py` decorators after TASKS 1-4. §6 maps to TASK 6, which limits `atomic_text_write` widening to the two cleanup tests.

§7 and §8 map to TASK 7, which names AC7 and AC8, uses a `Two-commit probe-revert pattern`, and includes M1 fallback. §9 maps to TASK 9, which states the expected no-change branch: `git diff main -- .github/workflows/ci.yml SECURITY.md requirements.txt shows no diff`. §10 maps to TASK 10, which deletes the two resolved entries, pre-registers the cycle-39 fold, and verifies scratch files. §11 maps across TASK 7, TASK 8, Step-9, and Step-10: probe commit, revert, squash-merge mandate, ruff T20, and grep are all present.

4. FINDING 4 — PLAN-VS-DESIGN CONFLICT SCAN: PASS

I found no plan contradiction against design decisions Q1-Q8, B-Q1..5, D1-D6, or M1. Q1/Q2 are honored by TASK 1 subprocess isolation and TASK 4's `monkeypatch.delitem(sys.modules, "kb.capture", raising=False)` plus `monkeypatch.delenv`. Q3 and B-Q3 are honored by TASK 6 strict scope. Q5 is honored by TASK 8 ruff T20, Step-9 squash-merge text, and Step-10 print grep. Q6-Q8 are honored by TASK 9 and TASK 10. B-Q1 is honored because the plan widens only capture plus `utils.llm`, not extractors. B-Q2, D6, and M1 are honored by TASK 7's probe-revert strategy and fallback. D2 is honored by the plan's ordering line: `AC0 → AC1 → AC2 → AC5 → AC3 → AC4 → AC6 → AC7 → AC8 → AC9 → AC10 + ruff T20`.

There are no PLAN-AMENDS-DESIGN dependency violations. The Step-10 CI mirror problems below are conflicts against the actual `ci.yml`, not against the design decision text as written.

5. FINDING 5 — TDD ORDERING: PASS

Each task has either a test-first/check-first step or a stated rationale. TASK 1 is a test refactor and verifies via grep plus full pytest. TASK 2 and TASK 3 are ordered before TASK 4 because the plan explicitly says `AC1+AC2 widen patches; AC5 codifies the regression`; that is a clear rationale for not placing the regression before those edits. TASK 4 is the regression-test task and includes the manual revert check. TASK 5 re-enables existing skipped tests and verifies decorator removal plus full pytest. TASK 6 re-enables the two existing cleanup tests and verifies the paired `atomic_text_write` patch sites. TASK 7 is probe-driven and names the failed ubuntu CI tests as the test surface. TASK 8 is lint-rule hardening and uses pre-flight plus post-change `ruff check src/ --select T20`. TASK 9 is BACKLOG-only on the expected branch and says `Test expectations: None`. TASK 10 is doc/backlog cleanup and points to the cycle-34 release hygiene test.

6. FINDING 6 — STEP-10 CI MIRROR COMPLETENESS: REJECT

The workflow has 10 named steps: `Checkout`; `Set up Python 3.12 with pip cache`; `Install package + ALL feature extras + dev tools`; `Install CI tooling (build, twine, pip-audit)`; `Ruff check`; `Pytest collection (smoke check)`; `Pytest full suite`; `Pip resolver check`; `Pip-audit (live environment with documented narrow-role exceptions)`; and `Build distribution + twine check`.

The plan's Step-10 block covers ruff check, pytest collection, full pytest, pip check, pip-audit, and build/twine. It does not cover `Checkout`, `Set up Python 3.12 with pip cache`, `Install package + ALL feature extras + dev tools`, or `Install CI tooling (build, twine, pip-audit)`. The plan also adds `Ruff format check`, but `ci.yml` has no `ruff format --check` step. Most importantly, the pip-audit command does not mirror the workflow: `ci.yml` ignores four IDs (`CVE-2025-69872`, `GHSA-xqmj-j6mv-4862`, `CVE-2026-3219`, `CVE-2026-6587`) and has no `--format=json`, while the plan uses only `--ignore-vuln=GHSA-xqmj-j6mv-4862 --format=json`. This is not a harmless ordering difference; it changes the audited command surface. The plan's handoff claim that Step-10 mirrors `all 8 ci.yml steps` is factually wrong; the workflow has 10 named steps. Because ci.yml steps are absent from the mirror, this finding is REJECT.

7. FINDING 7 — STEP-11 SECURITY VERIFY MAPPING: REJECT

The plan maps T1 to `grep -n "kb.utils.llm.call_llm_json" tests/conftest.py`, T3 to `grep -n "print(" src/kb/capture.py`, T4 to `git diff main -- BACKLOG.md`, T5 to `grep -n "fake_call" tests/conftest.py`, and T7 to `pip-audit --format=json` on the branch matching the Step-2 baseline.

Two mappings fail the command requirement. First, threat-model T2 is the sibling-order leak for `tests/test_cycle38_mock_scan_llm_reload_safe.py`; threat-model §7 maps it to `python -m pytest ... test_cycle38_mock_scan_llm_reload_safe.py ... test_capture.py -v`. The plan's Step-11 T2 command is instead `grep -n "del sys.modules" tests/test_capture.py = 0`, which verifies AC0 subprocess isolation, not the T2 sibling-order threat. Second, T6 in the plan maps to `CI green`, which is a status, not a Step-11 verification command. Since at least one threat has no matching Step-11 command from the plan, this finding is REJECT.

8. FINDING 8 — PROBE-REVERT HYGIENE: PASS

TASK 7 explicitly includes the revert step. Its fix-commit instructions say `REVERT the print() diagnostics in the same commit`, and its verification says `grep -n "print(" src/kb/capture.py against git diff main returns zero lines`. The cycle-38 squash-merge mandate is also explicit: Step-9 says `PR is squash-merged so probe + revert pair never lands as separate commits on main per design Q5`. Both required hygiene elements are present.

9. FINDING 9 — CYCLE-22 L5 CONDITIONS BUNDLING: PASS

I found no load-bearing condition hidden inside an unrelated task. The only bundled implementation task is TASK 7 for AC7 plus AC8, but that grouping is cosmetic: the title names both ACs, the probe scope lists both affected tests, and the M1 fallback references `CONDITIONS §7-§8`. CONDITIONS §11 is distributed across TASK 7, TASK 8, Step-9, and Step-10, but the distribution is explicit: probe/revert, T20, squash-merge, and grep each have named plan text. No design condition that should be a separate sub-AC is obscured inside a larger task.

10. FINDING 10 — SUB-TASK SIZING: PASS

No task clearly exceeds the cycle-13 L2 plus cycle-37 L5 sizing threshold of touching more than 50 LoC across more than 3 files. TASK 4 likely exceeds 50 LoC, but it is one new test file. TASK 7 may touch production and test files, but the plan names only `src/kb/capture.py` and `tests/test_capture.py`. TASK 5 touches two files. TASK 10's task body names only `BACKLOG.md`, while Step-9 commit ordering separately mentions Step-12 docs; that doc update is not specified as a single oversized implementation task. No split suggestion is required.

FINAL VERDICT: REJECT
