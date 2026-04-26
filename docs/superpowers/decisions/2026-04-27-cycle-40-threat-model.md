# Cycle 40 — Threat model + dep-CVE baseline

**Date:** 2026-04-27
**Predecessor:** Cycle 39 baseline (2026-04-26)

## Threat model body — SKIP eligible

Per dev_ds skill Step 2 skip rule: *"skip when pure internal refactor, no I/O or trust boundary changes."*

Cycle 40's three implementation groups all qualify:

| Group | Operation | Trust boundary impact |
|---|---|---|
| A — Test fold (3 files) | Pure relocation of test classes/functions from `test_cycle10/11_*.py` source files into canonical `test_*.py` targets | None — tests don't ship; pytest collection only. |
| B — Dep-CVE re-verification | Read-only probes (`pip index versions`, `pip-audit --format=json`, `pip download --no-deps METADATA inspect`) | None — no install, no requirements.txt edits |
| C — Resolver + Dependabot drift re-verification | Read-only probes (`pip check`, `gh api dependabot/alerts`) + BACKLOG line edits | None — informational doc updates |
| D — BACKLOG hygiene | Doc edit only | None |

**Net trust-boundary delta for cycle 40 vs main: ZERO.**

No new attack surface. No new authn/authz. No new logging/audit requirements. No new I/O. The only "writes" are test files (collection-time only) and markdown documentation.

## Dep-CVE baseline (Step 11 diff anchor)

Captured 2026-04-27 09:30 GMT+12. Identical to cycle-39 baseline (1 day ago). Saved at `.data/cycle-40/cve-baseline.json` (21089 bytes) and `.data/cycle-40/dependabot-baseline.json` (407 bytes).

### pip-audit on live `.venv` install env (4 vulns)

| Package | Version | Advisory | fix_versions |
|---|---|---|---|
| `diskcache` | 5.6.3 | `CVE-2025-69872` (GHSA-w8v5-vhqr-4h9v) | `[]` (no upstream patch) |
| `litellm` | 1.83.0 | `GHSA-xqmj-j6mv-4862` | `['1.83.7']` (BLOCKED — `click==8.1.8` transitive) |
| `pip` | 26.0.1 | `CVE-2026-3219` (GHSA-58qw-9mgm-455v) | `[]` (no upstream patch) |
| `ragas` | 0.4.3 | `CVE-2026-6587` (GHSA-95ww-475f-pr4f) | `[]` (no upstream patch) |

### GitHub Dependabot alerts (4 open)

| Alert ID | Package | Severity | GHSA | first_patched |
|---|---|---|---|---|
| 12 | ragas | low | `GHSA-95ww-475f-pr4f` | `null` |
| 13 | litellm | high | `GHSA-xqmj-j6mv-4862` | `1.83.7` |
| 14 | litellm | critical | `GHSA-r75f-5x8p-qvmc` | `1.83.7` |
| 15 | litellm | high | `GHSA-v4p8-mg3p-g94g` | `1.83.7` |

### Pip-audit-vs-Dependabot drift (cycle-40+ tracker continuation)

pip-audit emits ONLY the parent litellm advisory `GHSA-xqmj-j6mv-4862` — NOT the two related Dependabot-only advisories `GHSA-r75f-5x8p-qvmc` and `GHSA-v4p8-mg3p-g94g`. Cycle-22 L4 + cycle-39 confirmed this is a pip-audit data-source lag, not a missing pin. Cycle 40 re-confirms drift persists 2026-04-27. Re-check next cycle's Step-2 baseline.

## Step 11 verification checklist (machine-checkable)

For Step 11 to PASS:

1. **PR-introduced CVEs (Class B)**: `comm -23 <(jq -r '.dependencies[].vulns[]?.id' .data/cycle-40/cve-branch.json | sort -u) <(jq -r '.dependencies[].vulns[]?.id' .data/cycle-40/cve-baseline.json | sort -u)` returns empty. Cycle 40 makes ZERO requirements.txt edits, so Class B should be empty by construction.

2. **Existing CVEs (Class A)**: All 4 pip-audit IDs (CVE-2025-69872, GHSA-xqmj-j6mv-4862, CVE-2026-3219, CVE-2026-6587) remain unchanged. Each entry's BACKLOG line gets a `(cycle-40 re-confirmed 2026-04-27)` marker per AC4-AC7.

3. **Resolver conflicts**: `.venv/Scripts/python.exe -m pip check` output exactly matches three documented conflicts (arxiv/requests, crawl4ai/lxml, instructor/rich). Per AC8.

4. **Dependabot drift**: pip-audit JSON does NOT contain `GHSA-r75f-5x8p-qvmc` or `GHSA-v4p8-mg3p-g94g`. Per AC9, AC10.

5. **Threat-model deferred-promise audit (per cycle-23 L3)**: every "deferred to cycle N+M" line in this doc has a corresponding BACKLOG entry. This cycle's "deferred to cycle-40+" lines (Windows CI, GHA spawn, POSIX off-by-one, Dependabot drift) all already have BACKLOG entries from cycle 36 — no NEW deferred-promise lines added in cycle 40.

6. **Test count invariant**: `pytest --collect-only -q | tail -1` returns "3014 tests collected" both before AC1-AC3 and after.
