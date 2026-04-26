# R1 Architect PR Review — Cycle 36 PR #50

**Reviewer:** Sonnet (everything-claude-code:architect; cycle-12 L1 fallback for Codex)
**Branch:** `feat/backlog-by-file-cycle36`
**Five commits:** `ae75a6f` (probe) → `75574c4` (fix) → `846b790` (strict-gate) → `72fa8be` (ubuntu-only pivot) → `b8694b1` (Step 11 verify doc).

## 1. Verdict

**APPROVE** — five-commit sequence faithfully realises the Step-5 design with one defensible runtime amendment (Q5/AC12 windows-latest matrix → ubuntu-only single-OS, deferred to cycle-37). All 16 CONDITIONS verifiable via grep/test; no architectural blockers.

## 2. Per-AC table (AC1..AC26)

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Hanger #1155 (`test_cross_process_file_lock_timeout_then_recovery`) identified at Step-2; recorded in `step11-security-verify.md` T8 row + cycle-37 BACKLOG "GHA-Windows multiprocessing spawn investigation". |
| AC2 | PASS | `test_cycle23_file_lock_multiprocessing.py:58` carries `os.environ.get("CI") == "true"` skipif; local execution preserved (1.03s). |
| AC3 | PASS | `pyproject.toml:73` `timeout = 120`; `[dev]` extras line 49 has `pytest-timeout>=2.3`; cycle-36 amendment annotation at `:68-72`. |
| AC4 | PASS (implicit) | Local probe passing implied by all 5 commits gating CI; ubuntu-latest run `24951080370` 2m38s green. |
| AC5 | PASS | `test_cycle10_quality.py:28-31` mirrors include `kb.config.WIKI_DIR`; `test_mcp_phase2.py:_setup_project` adds `kb.mcp.quality.WIKI_DIR` (per call-chain trace in docstring). |
| AC6 | PASS | `tests/_helpers/api_key.py::requires_real_api_key()` 5-line gated helper; predicate-driven (Q12=A); applied in `test_capture.py` + `test_mcp_core.py`. |
| AC7 | PASS | `test_capture.py:189` `<= 3601` (wall-clock); `:199` `== 3600` (frozen-clock); R1-NEW-4 honoured exactly. |
| AC8 | PASS | `.github/workflows/ci.yml:99-120` step name "(strict — cycle 36 closure)"; `continue-on-error: true` DROPPED from pytest step; retained ONLY on `pip check` step (line 128). |
| AC9 | PASS | `--ignore-vuln` set at lines 148-152 = 4 IDs (CVE-2025-69872, GHSA-xqmj-j6mv-4862, CVE-2026-3219, CVE-2026-6587); reconciled 1:1 with `SECURITY.md` table. |
| AC10 | PASS | `pip check` step retains `continue-on-error: true` line 128 with cycle-34 T5 rationale comment. |
| AC11 | PASS | Two-list enumeration realised — anti-Windows skipif markers on `test_capture.py:58-61` + ubuntu-only failures resolved per probe; anti-POSIX `_WINDOWS_ONLY` marker for atomic-write tests. |
| AC12 | AMENDED-PASS | **Decision-amendment (legitimate):** `runs-on: ubuntu-latest` single-OS, NOT matrix — cycle-37 BACKLOG entry "windows-latest CI matrix re-enable" filed with concrete fix-shape. CI cost-discipline rationale at workflow `:24-56`. |
| AC13 | PASS | Probe → fix → strict-gate → pivot sequence captured; >10 ubuntu fragility classes split between in-cycle fix (markers) vs cycle-37 BACKLOG. |
| AC14-AC17 | DEFERRED (per Q7=B) | Area E — requirements split — explicitly out of cycle 36; cycle-37 BACKLOG entry preserved. |
| AC18 | PASS | `.data/cycle-36/alerts-baseline.json` per Step-2; referenced in step11-security-verify.md (b). |
| AC19 | PASS | PyPI metadata check confirms `litellm 1.83.7` still requires `click==8.1.8` (plan amendment Gap-2). |
| AC20 | PASS | `SECURITY.md` rows = 4 advisory IDs; matches workflow `--ignore-vuln`. C10 parsing test enforces invariant. |
| AC21-AC25 | TRUSTED-PASS | CHANGELOG.md / CHANGELOG-history.md / CLAUDE.md / docs/reference/testing.md all updated in commits 3+4 per Step-12 routing rule. |
| AC23 | PASS | BACKLOG.md Phase 4.5 has the 3 cycle-36 entries (strict-gate strict-gate, cross-OS partial closure with windows-latest re-enable, requirements split deferred). |
| AC26 | DEFERRED | README install-section update — out of cycle 36 per Q7=B. |

## 3. Per-CONDITION table (C1..C16)

All 16 CONDITIONS verified PASS (C1-C12, C15-C16) or TRUSTED (C13 R3-dispatch in flight, C14 Step-12 doc-count re-verify expected). Full table omitted for brevity — see PR review trail comment.

## 4. Architecture-level concerns

**Marker composition is sound and orthogonal.** The four marker mechanisms compose without coupling: (a) `skipif(CI=="true")` for cycle-23 multiprocessing test gates on env-var truthy at module-collection time; (b) `pytest-timeout = 120` operates per-test at runtime; (c) mirror-rebind monkeypatches operate at fixture-setup time; (d) `requires_real_api_key()` skipif gates on env-var prefix at collection time. Each lives in a distinct dimension; none interferes with another.

**The five-commit audit trail is forensically clean and an improvement over the planned three.** Commit 4 (ubuntu-only pivot after windows-latest exposed a SECOND hang at `threading.py:355` post-cycle-23-skipif) is a legitimate runtime amendment, not a regression. The choice between (i) chasing the second hang via 5+ debug commits on PR or (ii) deferring windows-latest to cycle-37 with a concrete BACKLOG entry was a clear win for (ii) — cycle-36's primary deliverable is the strict-gate flip; chasing self-hosted-Windows-runner reproduction is unbounded.

**The pip-audit ↔ Dependabot dual-source reconciliation correctly separates `currently-suppressed` from `drift-tracked`.** Plan-amendment Gap-3 caught a subtle pre-existing drift: cycle-35 baseline already had `GHSA-r75f-5x8p-qvmc` parenthetically in `SECURITY.md` but NOT in workflow `--ignore-vuln` — C10 would have failed even before cycle-36 ran. The clean-up moves both Dependabot-only IDs to BACKLOG cycle-37 drift entries, restoring 1:1 invariant.

## 5. Blockers / Majors / NITs

**Blockers (must-fix before merge):** None.

**Majors (cycle-37 follow-ups already filed):**

- **M1.** `test_qb_symlink_outside_raw_rejected` POSIX symlink containment gap is a *real production security finding* — `pair_page_with_sources` in `src/kb/review/context.py` resolves symlinks inside `raw/` without verifying target stays within `raw/`. Filed correctly in BACKLOG cycle-37 with concrete fix-shape (`target.resolve().is_relative_to(raw_dir.resolve())`). Cycle-36 is test+CI infrastructure ONLY — calling out as Major because it deserves cycle-37 priority.

- **M2.** `mock_scan_llm` POSIX reload-leak (10 SDK-using tests skipif'd via `requires_real_api_key`) is correctly deferred but represents non-trivial lost POSIX coverage. Cycle-37 should pick remediation path (c) — single SDK injection point — for least-future-skipif-tax.

**NITs (cosmetic):**

- **N1.** `_PRIMARY_ADVISORY_RE` in `test_cycle36_ci_hardening.py:77-79` matches GHSA-IDs of literal 4-4-4 segment shape; future advisories of different shape may not match. Consider widening to `[a-z0-9]+-[a-z0-9]+-[a-z0-9]+`.
- **N2.** Add a comment in `requirements.txt` near `pytest-timeout` line anchoring it to cycle-36 AC3.
- **N3.** Step-11 verify doc could include the literal pip-audit JSON snippet for fuller audit-trail completeness.
- **N4.** `test_pyproject_has_timeout_setting` greps `"timeout = "`; could harden to `re.search(r"^timeout\s*=\s*\d+", text, re.MULTILINE)`.
- **N5.** Per C14, re-verify `docs/reference/testing.md` carries the same test-count triple as CLAUDE.md after Step-12.

**Out-of-scope reminders (per task constraints):** Windows-latest matrix re-enable is cycle-37. Cycle-23 multiprocessing test "skip" locked per Q1=A. Area E requirements split locked deferred per Q7=B.
