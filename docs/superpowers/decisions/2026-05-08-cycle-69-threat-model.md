# Cycle 69 — Threat Model + dep-CVE baseline

**Date:** 2026-05-08
**Tier:** 2
**Scope:** Pure-test / pure-doc / pure-BACKLOG cycle with **zero `src/kb/` changes**.

## Step 02 — Threat model

This cycle has **no production-code surface change**. All ACs land in `tests/` or `BACKLOG.md` or `CLAUDE.md` or `docs/superpowers/decisions/`. The ONLY security-adjacent surface is the AC03 + AC04 BACKLOG entry deletions (each paired with a behavioural lock-in test) — they remove stale entries against already-shipped code, they do NOT modify production behaviour.

### Threat enumeration (STRIDE-condensed)

| ID | Threat | Surface | Mitigation | Status |
|---|---|---|---|---|
| T1 | **Spoofing — fabricated lock-in:** the AC05 / AC06 lock-in tests look like they cover the deleted BACKLOG entries but actually pass under a revert (vacuous-test risk). | New `tests/test_cycle69_*_lockin.py` files | Each lock-in MUST exercise the production call site with inputs that DIVERGE the two behaviours (cycle-11 L1 / cycle-16 L2 / cycle-24 L5). Step 14 verifies via mutation: replace the production line with a no-op; the test must FAIL. | Required (Step 14) |
| T2 | **Tampering — fold lossy:** a fold (AC16–AC19) silently drops a unique behavioural assertion when migrating to a receiver that already has a "similar" test. | 4 fold target receivers | Each fold revert-checked per C40-L3 (`assert False` insertion → `pytest -x` FAIL → restored). Counts: source-file test count = receiver post-fold delta. | Required (Step 09) |
| T3 | **Repudiation — BACKLOG drift:** AC15b lock-in retirement (AC01) leaves the first lock-in (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) unchanged and only inverts the second. A future cycle could re-introduce a deleted entry without tripping any test. | `tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_does_not_contain_shipped_phase_4_5_high_entries` (kept) | Cycle-69 EXTENDS that test's `DELETED_ENTRIES` tuple with the AC03/AC04 entry strings (cycle-68's existing pattern). | Required (Step 09 — AC01 sub-task) |
| T4 | **Information disclosure — snapshot leak:** new snapshot subjects (AC13–AC15) capture filesystem-dependent or environment-dependent state that leaks into committed `.ambr` files. | `tests/test_cycle69_snapshots.py` + `tests/__snapshots__/test_cycle69_snapshots.ambr` | T15/T16 mitigations from cycle-64 preserved: snapshot fixture text constructed from controlled inputs only (no `os.environ` / `Path.home` / production paths). Default `pytest` invocation FAILs on drift; only `pytest --snapshot-update` rewrites. CI does NOT pass that flag. | Required (Step 09 + Step 14) |
| T5 | **Denial of service — fold deletes used helper:** a fold receiver depends transitively on a helper or fixture defined in the source file; deletion breaks an unrelated test. | 4 fold sources | Pre-fold: `grep -rn "from tests.test_v0917_<name>" tests/` AND `grep -rn "<helper_name>" tests/` for any defined-in-source helper. Each fold migrates required helpers into the receiver (cycle-47 L1). | Required (Step 09) |
| T6 | **Elevation — C11-L1 upgrade introduces broader monkeypatch surface:** the upgrade pattern (`monkeypatch + invoke production entry`) requires monkeypatching one or more `kb.*` symbols; if done sloppily, could mask a production regression elsewhere. | 6 upgrade sites in 4 versioned test files | Each upgrade revert-checked per cycle-21 L4: replace production fix with no-op (e.g., make the underlying helper return a constant); assert the upgraded test FAILs. | Required (Step 09 + Step 14) |
| T7 | **(deferred / out of scope)** — `src/kb/` changes are excluded by design. The diskcache CVE-2025-69872 risk is unchanged from cycle-68 acceptance. | n/a | Re-check at cycle-70 Step 02 baseline (cycle-68 BACKLOG entry preserved verbatim). | Tracked in BACKLOG |

**No new attack surface introduced this cycle.** AC03/AC04 are entry deletions against verified-shipped code; AC05/AC06 are net-new tests pinning that code; AC07–AC12 upgrade existing tests; AC13–AC15 add snapshot tests; AC16–AC19 are pure folds.

## Step 02 — Dep-CVE baseline snapshot

Captured 2026-05-08 from the project venv (per cycle-22 L1 — installed-venv audit, NOT `pip-audit -r requirements.txt`).

```
artifact: .data/cycle-69/pip-audit.json
audited: 323 packages
vulnerable: 1
  diskcache==5.6.3 — CVE-2025-69872 (pickle-deserialization RCE in transitive dep)
```

**Open Dependabot alerts (gh api / state=open): 0.**

### Risk acceptance for diskcache CVE-2025-69872

Unchanged from cycle 68 acceptance (BACKLOG.md):

> **diskcache 5.6.3 / CVE-2025-69872** — pickle-deserialization RCE in transitive dep. No fix published as of 2026-05-08. Risk acceptance: KB never reads diskcache from an untrusted directory; cache lives under `.venv/` which is user-owned. Re-check at next cycle's Step 02 baseline.

Cycle 69 re-check (2026-05-08):
- `pip index versions diskcache` — latest is still 5.6.3; no patched release (consistent with cycle-68 verdict).
- `grep -rnE "diskcache|DiskCache|FanoutCache" src/kb` — zero direct imports (only the trafilatura transitive dep).
- **Verdict:** acceptance unchanged; carry forward to cycle 70.

## PR-introduced CVE diff (Step 11 expected)

`Step-02 baseline ∩ Step-11 diff = ∅` (this cycle changes ZERO dependencies; `requirements.txt` and `pyproject.toml` will be untouched).

If ANY new dep advisory appears between Step-02 and Step-11 (cycle-22 L4 — advisories CAN drop mid-cycle), Step-15 (existing-CVE opportunistic patch) handles it.

## Files referenced

- `.data/cycle-69/pip-audit.json` — Step-02 baseline (committed under `.data/` per cycle-22 L1 Windows-relative-path rule).
- `tests/test_cycle69_app_segment_aware_lockin.py` — AC05.
- `tests/test_cycle69_graph_builder_intentional_bypasses.py` — AC06.
- `tests/test_cycle69_snapshots.py` + `tests/__snapshots__/test_cycle69_snapshots.ambr` — AC13–AC15.
