# Cycle 39 — Threat Model + Dep-CVE Baseline

**Date:** 2026-04-26
**Owner:** Opus 4.7 primary session
**Skill skip rule check:** Step 2 normally skips for "pure internal refactor, no I/O or trust boundary changes". Cycle 39 IS pure internal (BACKLOG.md edits + test fold, zero `src/kb` changes), but the cycle's WORK is dep-CVE re-verification — so the baseline portion of Step 2 is load-bearing. The threat-model portion is intentionally brief.

## Trust boundaries

**No new trust boundaries.** Cycle 39 introduces zero new I/O paths, zero new MCP tools, zero new external-service calls. The only file writes are to:

- `BACKLOG.md` (markdown text edits)
- `CHANGELOG.md` + `CHANGELOG-history.md` (markdown text edits)
- `tests/test_capture.py` (Python source — folded test class)
- `tests/test_cycle38_mock_scan_llm_reload_safe.py` (DELETE)

## Data classification

- **BACKLOG.md / CHANGELOG.md** — public source-of-truth markdown; no secrets, no PII.
- **Test code** — folded verbatim from existing tracked file; no new test fixtures or external connections.

## Authn / authz

N/A — no new endpoints, no new permission surfaces.

## Logging / audit

N/A — no new log writers, no new emission surfaces.

## Step 11 verification checklist (2 items)

| # | Threat / contract | Step 11 verify |
|---|---|---|
| T1 | **No PR-introduced CVEs (Class B per skill)** | `comm -23 <branch.txt> <baseline.txt>` over pip-audit GHSA IDs returns empty — cycle 39 changes zero deps |
| T2 | **No production code drift** | `git diff origin/main -- src/kb/` is empty — cycle 39 is BACKLOG/test-fold only |
| T3 | **Cycle-38 fold preserves behavior** | `tests/test_capture.py::TestMockScanLlmReloadSafety::test_baseline_dual_site_install_mock_fires` and `::test_mock_scan_llm_patches_both_canonical_and_module_bindings` pass after fold; existing 3003+11 baseline holds |
| T4 | **Threat-model deferred-promise (cycle-23 L3)** | No new "deferred to cycle N+M" prose introduced in cycle-39 docs — we DELETE one resolved promise (cycle-38 test-fold entry). |

## Dep-CVE baseline (captured 2026-04-26)

### (a) GitHub Dependabot view

`.data/cycle-39/alerts-baseline.json` (4 open alerts):
- `id=15 ghsa=GHSA-v4p8-mg3p-g94g severity=high pkg=litellm first_patched=1.83.7`
- `id=14 ghsa=GHSA-r75f-5x8p-qvmc severity=critical pkg=litellm first_patched=1.83.7`
- `id=13 ghsa=GHSA-xqmj-j6mv-4862 severity=high pkg=litellm first_patched=1.83.7`
- `id=12 ghsa=GHSA-95ww-475f-pr4f severity=low pkg=ragas first_patched=null`

**Summary:** 4 open Dependabot alerts (1 critical, 2 high, 1 low). All 3 litellm advisories blocked by `click==8.1.8` transitive in litellm 1.83.7..1.83.14 vs our `click==8.3.2`. Re-verified via `pip download litellm==1.83.14 --no-deps` + zipfile metadata read.

### (b) pip-audit live env

`.data/cycle-39/cve-baseline.json` (21089 bytes; 4 vulns in 4 packages):
- `diskcache 5.6.3 / CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v)` — fix_versions=[]
- `litellm 1.83.0 / GHSA-xqmj-j6mv-4862` — fix_versions=["1.83.7"] (blocked by click)
- `ragas 0.4.3 / CVE-2026-6587 (GHSA-95ww-475f-pr4f)` — fix_versions=[]
- `pip 26.0.1 / CVE-2026-3219 (GHSA-58qw-9mgm-455v)` — fix_versions=[]

### Drift summary (pip-audit vs Dependabot)

| GHSA | Dependabot | pip-audit | Drift? |
|---|---|---|---|
| `GHSA-xqmj-j6mv-4862` (litellm high) | YES (id=13) | YES | NO |
| `GHSA-r75f-5x8p-qvmc` (litellm critical) | YES (id=14) | NO | **YES** — cycle-39+ entry valid |
| `GHSA-v4p8-mg3p-g94g` (litellm high) | YES (id=15) | NO | **YES** — cycle-39+ entry valid |
| `GHSA-95ww-475f-pr4f` (ragas low) | YES (id=12) | YES (CVE-2026-6587) | NO |
| `CVE-2025-69872` (diskcache high) | NO | YES | reverse-drift; not blocking |
| `CVE-2026-3219` (pip high) | NO | YES | reverse-drift; not blocking |

Cycle-39+ Dependabot drift entries on `r75f` + `v4p8` are STILL drifting; pip-audit hasn't caught up; no `--ignore-vuln` change needed.

## Class A vs Class B (per skill)

- **Class A — existing on `main`**: All 4 pip-audit vulns + 4 Dependabot alerts EXISTED at cycle 38 close. Cycle 39 patches NONE (none have actionable upstream fixes). Step 11.5 will re-confirm and document.
- **Class B — PR-introduced**: Cycle 39 introduces ZERO dep changes (no `requirements.txt` edits). Step 11 PR-introduced diff will return empty.

## Pip check resolver conflicts (cycle-34 AC52 carry-over)

```
arxiv 2.4.1 has requirement requests~=2.32.0, but you have requests 2.33.0.
crawl4ai 0.8.6 has requirement lxml~=5.3, but you have lxml 6.1.0.
instructor 1.15.1 has requirement rich<15.0.0,>=13.7.0, but you have rich 15.0.0.
```

All three persist — `continue-on-error: true` on the `pip check` CI step remains needed. Cycle 39 only re-confirms; no upstream relaxation.
