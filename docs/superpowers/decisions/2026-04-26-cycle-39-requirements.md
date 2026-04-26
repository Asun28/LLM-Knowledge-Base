# Cycle 39 — Backlog hygiene + dep-drift re-verification + cycle-38 test fold

**Date:** 2026-04-26
**Branch:** cycle-39-backlog-hygiene
**Owner:** Opus 4.7 primary session (per C37-L5: ≤15 ACs / ≤5 src files / primary holds context)

## Problem

Six cycle-39+ tagged items in `BACKLOG.md` (Phase 4.5 MEDIUM) are due for periodic re-verification, plus one LOW-priority test fold per cycle-4 L4 freeze-and-fold rule:

1. **Two Dependabot pip-audit drift entries on litellm** (`GHSA-r75f-5x8p-qvmc` critical + `GHSA-v4p8-mg3p-g94g` high) — Dependabot reports them; pip-audit on the live env doesn't. Cycle-38 re-confirmed drift persists. Cycle 39 re-checks data refresh and escalates to `--ignore-vuln` only if pip-audit catches up.
2. **Four no-upstream-fix CVEs** carried in MEDIUM (diskcache `CVE-2025-69872`, ragas `CVE-2026-6587`, pip `CVE-2026-3219`, litellm `GHSA-xqmj-j6mv-4862`/`-r75f`/`-v4p8`) — re-verify (a) installed version is still latest, (b) `fix_versions` still empty OR the patched version still ResolutionImpossible-blocked. Document re-confirmation date so the next cycle's Step-2 baseline can find the cycle 39 marker.
3. **Three resolver conflicts (cycle-34 AC52)** — `arxiv 2.4.1` requires `requests~=2.32.0` vs `2.33.0`; `crawl4ai 0.8.6` requires `lxml~=5.3` vs `6.1.0`; `instructor 1.15.1` requires `rich<15.0.0` vs `15.0.0`. Re-check whether any upstream relaxed; if so, drop `continue-on-error: true` on `pip check` step in CI.
4. **Cycle-38 test fold** — `tests/test_cycle38_mock_scan_llm_reload_safe.py` was created as a cycle-tagged regression file at cycle 38 AC5; per cycle-4 L4 freeze-and-fold rule (and per its own self-tagged "cycle-39+ candidate" note), fold the two test methods into `tests/test_capture.py` as `class TestMockScanLlmReloadSafety` for module locality.

These are all small, mechanical items. Grouping them into one cycle 39 batch follows the user's `feedback_batch_by_file` preference and the C37-L5 primary-session-default heuristic.

## Non-goals

- **NOT** upgrading litellm to 1.83.7+ — verified 1.83.14 still pins `click==8.1.8`, ResolutionImpossible against our `click==8.3.2`. Narrow-role exception (`grep src/kb` shows zero litellm imports + we never start LiteLLM Proxy) remains valid.
- **NOT** patching diskcache/ragas/pip CVEs — no upstream fix available; narrow-role exceptions documented.
- **NOT** resolving resolver conflicts upstream — out of our control; CI gate `continue-on-error: true` remains until upstream relaxes.
- **NOT** investigating the windows-latest CI matrix re-enable / GHA-Windows multiprocessing spawn / TestWriteItemFiles POSIX cycle-39+ items — these need self-hosted Windows runner / POSIX shell access which the operator does not have in this session. They stay BACKLOG (cycle-40+).
- **NOT** changing any production `src/kb/*.py` code. Cycle 39 is BACKLOG.md/CHANGELOG.md/test-folder only.
- **NOT** rev-ing version (stays v0.11.0).

## Acceptance Criteria

Each AC is testable as pass/fail.

| # | AC | Test |
|---|---|---|
| AC1 | Dependabot drift on `GHSA-r75f-5x8p-qvmc` re-verified — pip-audit live env still does NOT emit this ID; BACKLOG entry's date marker updated to "cycle-39 re-confirmed (2026-04-26)" | `jq` over `.data/cycle-39/cve-baseline.json` shows zero matches for `r75f-5x8p-qvmc`; `grep "cycle-39 re-confirmed" BACKLOG.md` returns the entry |
| AC2 | Dependabot drift on `GHSA-v4p8-mg3p-g94g` re-verified — same handling | `jq` returns zero; BACKLOG entry's date marker updated |
| AC3 | diskcache `CVE-2025-69872` re-confirmed — installed `5.6.3` is still pip's latest, `fix_versions` still empty | `pip index versions diskcache` shows 5.6.3 is highest; pip-audit JSON shows `fix_versions: []` for this ID; BACKLOG entry's date marker updated |
| AC4 | ragas `CVE-2026-6587` re-confirmed — installed `0.4.3` is still latest, `fix_versions` still empty | same shape; BACKLOG entry's date marker updated |
| AC5 | pip `CVE-2026-3219` re-confirmed — installed `26.0.1` is still latest, `fix_versions` still empty | same shape; BACKLOG entry's date marker updated |
| AC6 | litellm `GHSA-xqmj-j6mv-4862` (+`-r75f`/`-v4p8` aliased fix path) re-confirmed — 1.83.14 still pins `click==8.1.8`, ResolutionImpossible vs our `click==8.3.2` | `pip download litellm==1.83.14 --no-deps` + zipfile metadata read shows `Requires-Dist: click==8.1.8`; BACKLOG entry's date marker updated |
| AC7 | Three resolver conflicts re-confirmed unchanged — arxiv/crawl4ai/instructor still incompatible | `pip check` output verbatim contains the three known mismatches; BACKLOG entry's date marker updated |
| AC8 | Cycle-38 test file folded into canonical `tests/test_capture.py` — class `TestMockScanLlmReloadSafety` lands at end of file with both `test_baseline_dual_site_install_mock_fires` and `test_mock_scan_llm_patches_both_canonical_and_module_bindings` test methods preserved verbatim including docstrings and revert-check guidance; original `tests/test_cycle38_mock_scan_llm_reload_safe.py` deleted | `git diff` shows class added in test_capture.py + cycle-38 file deleted; full pytest collects unchanged total minus +0 (same 2 test names) |
| AC9 | Full pytest suite passes with no regressions | `python -m pytest -q 2>&1 \| tail -2` shows `3003 passed, 11 skipped` (cycle 38 baseline); ruff check + ruff format --check both clean |
| AC10 | BACKLOG.md updated — cycle-39+ tagged entries get "cycle-39 re-confirmed (2026-04-26)" suffix; cycle-38-fold entry deleted (resolved); test-count narrative unchanged (no test count delta from fold) | `grep -c "cycle-39 re-confirmed" BACKLOG.md` ≥ 7 (one per re-confirmed entry); `grep "test_cycle38_mock_scan_llm_reload_safe" BACKLOG.md` returns nothing |
| AC11 | CHANGELOG.md `[Unreleased]` Quick Reference gets a compact cycle-39 entry; CHANGELOG-history.md gets full per-cycle detail (newest first); CLAUDE.md test count unchanged at 3014 collected / 3003+11 | `head -30 CHANGELOG.md` shows the cycle-39 entry; CLAUDE.md grep for `3014 tests` unchanged |

## Blast radius

- `BACKLOG.md` — text edits to ~7 entries (date markers) + 1 deletion (cycle-38 fold-into-canonical entry resolved)
- `CHANGELOG.md` + `CHANGELOG-history.md` — 1 new cycle-39 entry each
- `tests/test_capture.py` — append `class TestMockScanLlmReloadSafety` (~110 lines pasted verbatim from cycle-38 file)
- `tests/test_cycle38_mock_scan_llm_reload_safe.py` — DELETE (folded into canonical)
- `src/kb/**` — **ZERO production code changes**

## Pre-flight verification (cycle-22 L1 + C34-L1 + C35-L1)

- `pip-audit` against installed venv (NOT `-r requirements.txt`) — `.data/cycle-39/cve-baseline.json` captured at 21089 bytes
- Dependabot alerts JSON — `.data/cycle-39/alerts-baseline.json` shows 4 open alerts (3 litellm + 1 ragas)
- pip-audit shows 4 vulns in 4 packages: diskcache, litellm (only `xqmj-j6mv-4862`), ragas, pip — confirms the two cycle-39+ Dependabot drift entries (`r75f` + `v4p8`) are STILL invisible to pip-audit
- `pip check` confirms three resolver conflicts persist verbatim
- `pip index versions <pkg>` confirms diskcache 5.6.3 / ragas 0.4.3 / pip 26.0.1 are all still the LATEST published versions (no upstream fix available)
- `pip download litellm==1.83.14 --no-deps` + zipfile metadata read confirms `Requires-Dist: click==8.1.8` — upgrade still ResolutionImpossible vs our `click==8.3.2`

These feed Step 2 (threat model + baseline) and Step 11 (PR-introduced CVE diff which will be empty since no deps change).
