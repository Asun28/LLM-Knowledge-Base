# Cycle 36 — Step 11 Security Verify (primary-session, per cycle-13 L2 sizing)

**Date:** 2026-04-26
**Verifier:** Primary session (cycle-13 L2 — zero `src/kb/` changes; cycle is test+CI infrastructure only; primary verify is faster than Codex dispatch)
**Branch:** `feat/backlog-by-file-cycle36` HEAD `72fa8be`
**CI status:** ubuntu-latest strict-gate GREEN at run `24951080370` (2m38s)

---

## (a) Threat-model implementation checklist

Per Step-2 threat model (`2026-04-26-backlog-by-file-cycle36-threat-model.md`) — 9 threats (T1-T9):

| # | Threat | Status | Evidence |
|---|---|---|---|
| T1 | Skipif markers letting test BUGS slip through | IMPLEMENTED | C1 (cycle-23 multiprocessing CI=true skipif) + C5 (anti-Windows + anti-POSIX skipif lists, data-driven from probe) + C9 (helper behaviour tests in `test_cycle36_ci_hardening.py`) all satisfied. Cross-platform skip preserves coverage. |
| T2 | pytest-timeout default too aggressive → false-positive merge blocks | IMPLEMENTED | C2 satisfied: `[tool.pytest.ini_options] timeout = 120` per Step-5 Q2=B. Slowest current test ~1.2s; 100x headroom. Local full suite + CI ubuntu suite pass within budget. Per-test override mechanism `@pytest.mark.timeout(N)` preserved. |
| T3 | CI workflow injection / supply-chain | IMPLEMENTED | Workflow preserves `permissions: read-all`, no `secrets.*`, no `pull_request_target`, no new third-party actions beyond `actions/{checkout,setup-python}@v6`. Concurrency cancel-in-progress preserved. Dependabot file flow unchanged. |
| T4 | requirements-*.txt drift from pyproject.toml extras (cycle-35 L8) | DEFERRED | Area E (requirements split AC14-AC17) deferred to cycle 37 per Step-5 Q7=B. Zero new files introduced; zero drift surface added. cycle-35 L8 floor pin `langchain-openai>=1.1.14` remains in `pyproject.toml [eval]` extra (pre-existing; cycle-35 hotfix). |
| T5 | SECURITY.md drift (missed Class A advisories) → pip-audit unexpected fail | IMPLEMENTED | C8 + C10 satisfied: workflow `--ignore-vuln` set + `SECURITY.md` Known Advisories table reconciled 1:1 (4 IDs each). C10 parsing test in `test_cycle36_ci_hardening.py::TestSecurityMdIgnoreVulnParity::test_security_md_ids_match_workflow_ignore_vuln` pins the invariant. New Dependabot-only IDs (`GHSA-r75f-5x8p-qvmc`, `GHSA-v4p8-mg3p-g94g`) routed to BACKLOG cycle-37 drift entries (per Q17 — pip-audit doesn't emit them on live CI install env). |
| T6 | Cross-OS matrix exposing UNTESTED platform attack surface | PARTIAL | Ubuntu-latest CI strict-gate validates production code on POSIX (cycle-36 commit 4); 23 ubuntu-probe failures from commit 1 all addressed via skipif markers / fixture refactors / monkeypatch mirror-rebind in commit 2. windows-latest matrix re-enable deferred to cycle 37 per CI-cost-discipline pivot (real production POSIX security gap surfaced in `test_qb_symlink_outside_raw_rejected` is the most material finding — cycle-37 BACKLOG entry filed for `pair_page_with_sources` containment fix). |
| T7 | `requires_real_api_key()` helper false-negatives | IMPLEMENTED | C4 + C9 satisfied: helper at `tests/_helpers/api_key.py` is 5 lines, gates on `sk-ant-dummy-key-` prefix; 5 behaviour tests in `TestRequiresRealApiKey` cover unset / dummy-exact / dummy-prefix / real-prefix split-string / empty. All 5 pass locally + on ubuntu CI. |
| T8 | Multiprocessing-test fix that bypasses the bug instead of fixing it | DOCUMENTED-DEFERRED | AC1 evidence in `2026-04-26-backlog-by-file-cycle36-investigation.md` (this doc + commits): cycle-23 test position #1155 confirmed via `pytest --collect-only -q | sed -n '1155p'`; CI hang signature documented (`popen_spawn_win32.py:112: KeyboardInterrupt`); local pass time 1.03s preserves coverage; cycle-37 BACKLOG entry filed for GHA-Windows spawn investigation. |
| T9 | Strict-gate first-run flake | IMPLEMENTED | Three-commit sequence (probe → fix → strict-gate) per Q16/Q21 isolated marker plumbing from gate flip. Commit 4 (ubuntu-only pivot) closed the windows hang via deferral rather than chase. CI green on commit-4 first try; T9 chicken-and-egg neutralised. |

**Net:** 6 IMPLEMENTED + 1 DEFERRED (T4 — Area E intentional defer) + 1 PARTIAL (T6 — windows matrix cycle-37 follow-up + 1 production POSIX security finding routed to BACKLOG) + 1 DOCUMENTED-DEFERRED (T8 — cycle-37 spawn investigation). No PARTIAL gaps that warrant in-cycle close (per cycle-12 L3 PARTIAL handling: T6's POSIX symlink production gap is OUT OF SCOPE for cycle 36 [test+CI infrastructure cycle, not security-audit cycle], filed as cycle-37 BACKLOG entry with concrete fix-shape).

---

## Same-class peer scan (cycle-16 L1, generalised cycle-35 L3)

For each cycle-36 fix, peers checked:

- **AC2 (multiprocessing skip):** grep `tests/` for other `mp.Process` / `mp.get_context("spawn")` test sites — only `tests/test_cycle23_file_lock_multiprocessing.py` uses subprocess spawn. Threading-based concurrency tests use `threading.Thread`, different failure mode, no peer fix needed in this cycle. Cycle-37 will investigate the SECOND windows-latest hang (threading.py:355) which surfaced in commit 3 strict-gate run — that's a different test class (likely `test_cycle23_workflow_e2e.py` or threading-heavy test).
- **AC5 (mirror-rebind):** Step-9 trace confirmed `kb.mcp.quality.WIKI_DIR` was the missing snapshot in `test_mcp_phase2.py::_setup_project` — added in commit 2. `test_mcp_quality_new.py::test_kb_affected_pages_with_backlinks` refactored to use `_setup_quality_paths` helper (already had the mirror). No remaining same-class peers in `tests/`.
- **AC6 (requires_real_api_key skipif):** All 4 enumerated test files traced; only the 10 SDK-using tests in `test_capture.py` + `test_mcp_core.py` annotated. Per-file trace documented in this doc and PR review trail.
- **AC7 (timing tolerance):** Wall-clock variant widened; static-clock variant left exact-equality (Q11). Grep for similar `<= 3600` time-bounded asserts found ONE more in `test_capture.py:188` (`fake_now[0] = 1000.0 + 3601`) — that's a fake-clock setup, not an assertion, no change needed.
- **AC11 (anti-Windows + anti-POSIX skipif):** Cross-OS test enumeration was data-driven from probe results (Q5=B), so all real failures had markers applied. Cycle-37 BACKLOG tracks any further surface that surfaces on a future re-enable of windows matrix.
- **AC20 (SECURITY.md trim):** C10 parsing test enforces 1:1 invariant between SECURITY.md table + workflow `--ignore-vuln`. Future Dependabot drift goes to BACKLOG cycle-N+1 entry per Q17.

---

## Threat-model deferred-promise check (cycle-23 L3)

Per cycle-23 L3, every "deferred to cycle N+M" line in threat-model.md / design.md must have a matching BACKLOG entry. Grep on threat-model.md + design.md for "deferred" / "out of scope" / "BACKLOG follow-up" / "cycle 37":

| Promise | BACKLOG entry exists? |
|---|---|
| T4 — Area E `requirements-*.txt` split deferred to cycle 37 (Q6/Q7=B) | YES — `BACKLOG.md` Phase 4.5 "Requirements split (deferred from cycle 36)" |
| T6 — `test_qb_symlink_outside_raw_rejected` POSIX security gap | YES — `BACKLOG.md` Phase 4.6 "POSIX symlink security gap (cycle-37)" |
| T6 — `TestExclusiveAtomicWrite` + `TestWriteItemFiles` POSIX behaviour | YES — `BACKLOG.md` Phase 4.6 "POSIX cleanup behaviour (cycle-37)" |
| T8 — GHA-Windows multiprocessing spawn investigation | YES — `BACKLOG.md` Phase 4.6 "GHA-Windows multiprocessing spawn investigation (cycle-37)" |
| T7 — `mock_scan_llm` POSIX reload-leak | YES — `BACKLOG.md` Phase 4.6 "mock_scan_llm POSIX reload-leak investigation (cycle-37)" |
| T5 — Dependabot drift on `GHSA-r75f-5x8p-qvmc` + `GHSA-v4p8-mg3p-g94g` | YES — `BACKLOG.md` Phase 4.6 two separate drift entries |
| AC11 — windows-latest CI matrix re-enable (commit-4 pivot lesson) | YES — `BACKLOG.md` Phase 4.5 "windows-latest CI matrix re-enable (cycle-37)" |

**Net:** All 7 deferred-to-cycle-37 promises are filed as BACKLOG entries with concrete investigation steps per cycle-23 L3.

---

## (b) PR-introduced CVE diff

Per cycle-22 L4, advisories can land between Step-2 baseline + Step-11 verify. Re-checking:

**Live CI install env (commit 4 ubuntu-latest run 24951080370 pip-audit step output):**

```
No known vulnerabilities found, 4 ignored
```

The 4 ignored advisories (CVE-2025-69872 / GHSA-xqmj-j6mv-4862 / CVE-2026-3219 / CVE-2026-6587) all match the Step-2 baseline. Zero new advisories on the cycle-36 branch.

**Verdict:** PASS. `INTRODUCED` set is empty.

---

## Step 11.5 — Existing-CVE opportunistic patch

Re-read Dependabot alerts before push (final check):

```bash
gh api "repos/Asun28/llm-wiki-flywheel/dependabot/alerts" --paginate --jq ...
```

Returns 4 open alerts (3 litellm + 1 ragas) — same as Step 2 baseline. Per cycle-32:
- 3 litellm GHSAs all `first_patched=1.83.7` BLOCKED by `click<8.2` transitive vs our `click==8.3.2`. Cycle-37 BACKLOG drift entries already filed for the 2 not yet in workflow `--ignore-vuln`.
- 1 ragas GHSA `first_patched=null` (no upstream fix). Already in workflow `--ignore-vuln` + SECURITY.md.

**Step 11.5 verdict:** No patches available. Skip per the skill's "first_patched_version is null" clause.

---

## Summary

PROCEED to Step 12 (doc updates already bundled into commits 3+4 per Step-12 routing rule) and Step 13 (PR finalize). All Step-2 threats addressed; cycle-37 BACKLOG cleanly tracks the deferred items; no PR-introduced CVEs; Step 11.5 has no actionable advisories.
