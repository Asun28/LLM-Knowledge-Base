# Cycle 24 PR #38 — R3 Sonnet Synthesis Review

**Date:** 2026-04-23
**Reviewer:** R3 Sonnet
**Verdict:** APPROVE-WITH-NIT

---

## Focus Area 1 — Threat-model / design / doc audit

### Check 1 — T1..T10 mitigation fidelity

All 10 threats verified against shipped code.

- **T1 (stale .tmp re-opened):** AC6 ships unconditional `Path.unlink(missing_ok=True)` as the FIRST statement in `rebuild_vector_index`, before all gates. MATCHED.
- **T2 (os.replace NTFS):** AC5 routes through `os.replace(str(tmp_path), str(vec_path))`; T2's documented residual (concurrent reader holds `_conn`) is addressed by design-gate Q2's explicit `popped._conn.close()` before replace. Threat model correctly marks the cross-process read race as a pre-existing residual. MATCHED.
- **T3 (backoff starvation):** AC9 ships exponential schedule capped at `LOCK_POLL_INTERVAL` across all 3 polling sites. T3 residual (fairness) is backlogged. MATCHED.
- **T4 (LOCK_POLL_INTERVAL monkeypatch compat):** Design gate decided CAP semantics; CHANGELOG-history confirms "reading both constants at CALL TIME." Existing cycle-2 monkeypatches preserved. MATCHED.
- **T5 (sentinel injection via body):** AC14 ships section-span-limited search. Design gate Q8 chose option (a) — span only from `^## Evidence Trail` to next `^## ` or EOF. No deferred item needed. MATCHED.
- **T6 (StorageError path-leak):** AC2 raises `StorageError(kind="evidence_trail_append_failure", path=page_path)`. All MCP error paths go through `_sanitize_error_str` → `sanitize_error_text` → `str(exc)`, which invokes `StorageError.__str__` returning the redacted form. No `repr(exc)` or `.path` attribute access found in MCP tool responses. MATCHED.
- **T7 (same-class peer audit):** CHANGELOG-history confirms `_write_wiki_page` new-page path (both branches) converted to single-write. `_update_existing_page` two-write consolidation correctly deferred (BACKLOG line 151 narrowed per design gate Q11). MATCHED.
- **T8 (CVE late-arrival):** Step-11.5 re-audit executed per CHANGELOG-history Group E: both CVEs remain at `fix_versions: []`. MATCHED.
- **T9 (cache pinning old DB):** Explicit `_evict_vector_index_cache_entry` helper (per design CONDITION 2) pops cache AND calls `popped._conn.close()` BEFORE `os.replace`. MATCHED.
- **T10 (AC7 default kwarg):** `VectorIndex.build` signature is keyword-only via `*` separator; body uses `db_path if db_path is not None else self.db_path`. MATCHED.

No T-item describes behaviour that was withdrawn. T5's threat model §5 says "design-gate decision required" with two options; design gate chose option (b) (span-limited search) which is AC14 — not deferred. The threat-model's §6 deferred table entry for `§Phase 4.5 HIGH — ingest/evidence.py sentinel-anchor hardening` states "NO BACKLOG entry needed" correctly. PASS.

### Check 2 — AC count + test count consistency

- **design.md:** 15 ACs with 14 CONDITIONS. CONFIRMED (Conditions 1-14 verified in design.md).
- **CHANGELOG.md line 27:** "15 AC / 4 src + 5 new tests / 7 commits"
- **CHANGELOG.md line 28:** "Tests: 2743 → 2767 (+24)"
- **CHANGELOG-history.md line 14:** "15 AC / 4 src + 5 new tests / 7 commits. Tests: 2743 → 2767 (+24)."

NIT: "5 new tests" in the Items field means 5 new test FILES (5 test files confirmed: `test_cycle24_evidence_error_redacted.py`, `test_cycle24_evidence_inline_new_page.py`, `test_cycle24_evidence_sentinel_anchored.py`, `test_cycle24_lock_backoff.py`, `test_cycle24_vector_atomic_rebuild.py`). The "+24" on the Tests line is the correct test count. The "5 new tests" label is confusing — prior cycles use "N new test files" — but the +24 count is accurate. `pytest --collect-only` returns 2767. PASS with NIT.

- **CLAUDE.md:** Says 2767 tests across 239 test files; last full run 2758 passed + 9 skipped. CONSISTENT with pytest collection.

Minor: CHANGELOG-history Group E says "CLAUDE.md test count bumped 2743 → 2766" but CLAUDE.md itself says 2767. This internal archive note drifted by 1 (the R1-fix commit `4e22703` added one test). NIT.

### Check 3 — Commit count accuracy

`git log --oneline origin/main..HEAD` returns 8 commits (matches the task's enumerated list: f304e46 + 6724745 + d60bd15 + 9a1d9d7 + e306ab1 + 82833fc + fa4fe28 + 4e22703). CHANGELOG says 7 commits. The discrepancy is the R1-fix commit (`4e22703` — "fix(cycle 24): R1 review fixes") added AFTER docs were written. NIT — doc written at R1-dispatch time (7 commits), R1-fix commit is #8.

### Check 4 — BACKLOG lifecycle compliance

- `multiprocessing tests for cross-process` — ABSENT from BACKLOG.md. PASS (deleted per AC11).
- `fair-queue` — PRESENT at BACKLOG.md line 131. PASS.
- `rebuild_indexes .tmp awareness` — PRESENT at BACKLOG.md line 111. PASS.

### Check 5 — Deferred-to-backlog promise enforcement

All threat-model §6 deferred tags verified against BACKLOG.md:

| Tag | Status |
|---|---|
| `Phase 4.5 MEDIUM.*fair-queue` | PRESENT (line 131) |
| `Phase 4.5 HIGH.*_update_existing_page.*single-write` | PRESENT (line 151, narrowed) |
| `Phase 4.5 HIGH.*vector-index lifecycle` | PRESENT (line 109, sub-item 1 struck) |
| `Phase 4.5 HIGH.*JSONL migration` | PRESENT (line 128) |
| `Phase 5 pre-merge` | PRESENT (line 177) |
| `sentinel-anchor hardening` | CORRECTLY ABSENT (AC14 shipped it) |
| `exclusive-branch evidence collapse` | CORRECTLY ABSENT (AC1 both-branch scope closed it) |

PASS.

---

## Focus Area 2 — Cross-cluster integration gaps

### Check 6 — Evidence-trail + dedup regex interaction

`kb.query.dedup._TRAIL_SECTION_RE` at `src/kb/query/dedup.py:16` uses `re.DOTALL` with `^## (Evidence Trail|References).*$`. AC1's inline render places `## Evidence Trail` at the END of a first-write page (no section follows it), whereas pre-AC1 pages could have a subsequent section. Tested: the DOTALL-greedy pattern strips from `## Evidence Trail` to EOF in both cases. No dedup regression. PASS.

Note: the DOTALL regex is greedy and would strip content from `## Evidence Trail` through EOF in any multi-section page, including content under subsequent `## ` sections in the same file. This is a pre-existing behaviour (the section-span anchor added by AC14 only affects `append_evidence_trail`, not the dedup regex). Not introduced by cycle 24.

### Check 7 — MCP StorageError path projection

All MCP tool exception handlers route through `_sanitize_error_str` (defined in `src/kb/mcp/app.py:136`) which delegates to `sanitize_error_text`. That function calls `str(exc)` to produce the message, which for `StorageError` invokes the cycle-20 `__str__` redaction (`"evidence_trail_append_failure: <path_hidden>"`). No `repr(exc)` or `.path` direct dereference found in MCP error handling paths. PASS.

### Check 8 — rebuild_indexes + .tmp interaction

`rebuild_indexes` (`src/kb/compile/compiler.py:528`) unlinks `vector_index.db` but does NOT unlink `vector_index.db.tmp`. If an operator runs `kb rebuild-indexes` while `<vec_db>.tmp` exists from a crashed rebuild, the `.tmp` stays on disk. On the NEXT invocation of `rebuild_vector_index`, AC6's unconditional unlink at function entry cleans it (before any gates). No correctness break — the live DB was unlinked by `rebuild_indexes`, so the next build starts fresh and AC6 removes the stale `.tmp`. This is the hygiene gap tracked at BACKLOG.md line 111. PASS (acknowledged gap, not new regression).

---

## Summary

| Check | Result |
|---|---|
| 1. T1..T10 mitigation fidelity | PASS |
| 2. AC count + test count | PASS (NIT: "5 new tests" should read "5 new test files") |
| 3. Commit count | NIT — docs say 7, actual is 8 (R1-fix commit added post-doc) |
| 4. BACKLOG lifecycle | PASS |
| 5. Deferred-to-backlog promises | PASS |
| 6. Dedup + Evidence Trail | PASS |
| 7. MCP StorageError path-leak | PASS |
| 8. rebuild_indexes + .tmp | PASS (tracked in BACKLOG) |

**NITs only — no MAJORs, no blockers.**

- `CHANGELOG.md:27` + `CHANGELOG-history.md:14`: "5 new tests" should read "5 new test files" for clarity with the +24 count.
- `CHANGELOG-history.md` Group E: says "bumped 2743 → 2766" but current CLAUDE.md and pytest show 2767 (R1-fix commit added 1 test after docs were written).
- `CHANGELOG.md:27`: "7 commits" is accurate at R1-dispatch but the branch now has 8 commits including the R1-fix.
