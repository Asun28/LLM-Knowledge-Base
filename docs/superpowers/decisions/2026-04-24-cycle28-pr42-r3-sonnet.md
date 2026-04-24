# Cycle 28 — PR #42 R3 Sonnet Synthesis Review

**Date:** 2026-04-24
**Reviewer:** R3 Sonnet (audit-doc drift synthesis — cycle-19 L4)
**Branch:** `feat/backlog-by-file-cycle28`
**Scope:** Decision-trail vs shipped-artifact drift audit; NOT a fresh code review.

---

## Audit-doc drift check

### T1-T8 threat-model mitigations vs shipped code

| Threat | Mitigation text | Verified |
|--------|----------------|---------|
| T1 — log-injection via `db_path` | Accept existing-pattern parity; lazy `%s` format | PASS — embeddings.py:550 uses `%s` args, not f-string |
| T2 — path disclosure in INFO | Accept; cycle-20 L3 scopes `<path_hidden>` to StorageError exceptions only | PASS — `grep "<path_hidden>" src/kb/query/` returns zero (confirmed) |
| T3 — reload reset of counters | Monotonic-delta test pattern (before-snapshot + delta assertion) | PASS — all counter tests use baseline + delta; no `importlib.reload` in test file |
| T4 — perf_counter monkeypatch leak | `monkeypatch.setattr` fixture-based only; zero raw assignments | PASS — R1 Sonnet and R2 Codex both confirmed; raw assignment grep = zero |
| T5 — WARN threshold spam | Bounded by `_conn_lock` fast-path + `MAX_INDEX_CACHE_SIZE=8` cap | PASS — `_conn is not None` guard at embeddings.py line ~447 confirmed by R2 |
| T6 — `n_docs` corpus-size disclosure | Accept; single-user local-tool trust posture | PASS — documented; no code required |
| T7 — counter wraparound | No mitigation required (Python arbitrary-precision int) | PASS — documented theoretical only |
| T8 — importlib.reload counter poisoning | Same monotonic-delta discipline as T3 | PASS — zero `importlib.reload` calls in test file per R2 |

No threat-model mitigation was WITHDRAWN or AMENDED by the design gate. T3 and T8 are identical mitigations (both resolved by monotonic-delta test discipline); the threat model correctly documents them as the same underlying concern from two angles. No drift detected.

One potential ambiguity: the threat model AC3 docstring requirement (T3 "Verified-at: Step 9") states the docstring is "monotonic-delta assertions survive importlib.reload cascades per cycle-20 L1." R2 Codex confirmed the getter docstrings were implemented. No code contradiction found.

### Design AC count vs CHANGELOG AC count

Design (Q10 decision): 9 ACs (AC1-AC9 from requirements; design added no new numbered AC — Q10 expanded AC6 from 7→8 tests but did NOT add a 10th AC; C3 in design is a CONDITION not a new AC).

CHANGELOG Quick Reference: "Items: 9 AC / 2 src + 1 new test file / 6 commits"

**MATCH — 9 ACs in both.**

### CHANGELOG test count vs actual git diff

CHANGELOG claims: "Tests: 2801 → 2809 (+8)" and "1 new test file."

Actual `git diff --stat origin/main...HEAD -- tests/` output: exactly 1 file changed, `tests/test_cycle28_first_query_observability.py`, 308 insertions.

`git log --diff-filter=A -- tests/` equivalent confirmed via diff output: 1 new test file.

CLAUDE.md updated to 2809 tests across 245 test files. Design C3 specifies "+8 tests (2801 → 2809)."

**MATCH — 1 new test file, +8 tests, 2801 → 2809.**

### Commit count in CHANGELOG vs actual branch commits

CHANGELOG Quick Reference: "6 commits"

`git log --oneline origin/main..HEAD | wc -l` = 6

Commits:
1. `60a7016` feat(cycle 28): AC1-AC5 first-query observability
2. `a96f043` docs(cycle 28): BACKLOG hygiene + CHANGELOG + CLAUDE refresh
3. `2c5fdc2` docs(cycle 28): security-verify
4. `43922d4` docs(cycle 28): commit-count self-referential refresh (3 → 4)
5. `d9053c4` fix(cycle 28): R1 Sonnet M1 + M2
6. `ddedce6` docs(cycle 28): R2 Codex verification

**MATCH — 6 commits; self-referential arithmetic holds (feature commit + hygiene/CHANGELOG commit + security-verify + commit-count refresh + R1 fix + R2 doc = 6; the R2 doc commit lands as commit 6 which is the number stated).**

Note: commit 4 (`43922d4`) incremented the count from 3 to 4 after the R1 fix commit was anticipated but before R2 landed. The R2 doc commit (`ddedce6`) did not increment further — the count stayed at 6 because the R2 doc commit was already baked into the expected total when commit 5 set it to 6. This is arithmetically correct but relies on the R2 doc commit being count-last. No issue found.

### BACKLOG.md lifecycle hygiene

Design C13 specifies three mutations: (a) HIGH-Deferred sub-item (b) removed from vector-lifecycle entry; (b) MEDIUM AC17-drop line deleted; (c) LOW cycle-27 commit-tally entry deleted.

Verified from `git diff origin/main -- BACKLOG.md`:
- (a) HIGH-Deferred entry: sub-item "(b) first-query observability" removed; Cycle-28 AC1-AC5 delivery text added. PASS.
- (b) `grep -c "AC17-drop" BACKLOG.md` = 0. PASS.
- (c) LOW sentinel updated from "cycle 13" to "cycle 28"; comment block updated with cycle-28 closure note. PASS.

C13 also required: `grep -c "cycle-27 quick-reference commit tally" BACKLOG.md` = 0. The LOW entry that was deleted described codifying the commit-count rule, which is what C14 addressed in CHANGELOG. That entry is confirmed absent. PASS.

Items not deleted: zero — no strikethrough items found in BACKLOG.md (lifecycle rule observed correctly).

**PASS — all three C13 mutations landed; no stale items.**

### C14 CHANGELOG format-guide self-referential rule

`grep -n "self-referential" CHANGELOG.md` returns exactly two matches: line 21 (inside the format-guide comment block) and line 55 (prose reference in the cycle-28 Quick Reference scope text).

N1 from R1 Sonnet flagged this as NIT — the C14 grep spec says "exactly one new match inside the format-guide comment block," which is satisfied (the comment block has exactly one occurrence). The second occurrence in the Quick Reference body is a legitimate prose cross-reference. N1 was correctly classified as cosmetic per cycle-12 L3 and carried forward per R2 Codex acknowledgement.

**PASS (with cosmetic NIT N1 carried) — comment block has exactly one match; condition intent is met.**

---

## Same-class peer scope-out audit

Threat model §Same-class peer candidates enumerates 6 candidates explicitly deferred out of scope:
1. `rebuild_vector_index` total-duration latency
2. `model.encode` per-batch encode latency
3. `VectorIndex.query` end-to-end latency
4. `tokenize()` call latency
5. `_evict_vector_index_cache_entry` close latency
6. `_get_model` HF cache-hit vs network-fetch discrimination

Verification: none of these 6 peers appear in `src/kb/query/embeddings.py` or `src/kb/query/bm25.py` changes (the only instrumented sites are `_ensure_conn` and `BM25Index.__init__`). CLAUDE.md API doc additions are limited to `get_sqlite_vec_load_count` and `get_bm25_build_count`. No peer candidate crept in-scope.

**PASS — scope-out clean.**

---

## NIT carry-forward check

R1 Sonnet raised N1-N5. R2 Codex confirmed all five were acknowledged in the fix commit message (`d9053c4`) under "Carried as cosmetic NITs not fixed in-cycle (per cycle-12 L3)."

| NIT | Status |
|-----|--------|
| N1 — C14 grep-spec yields 2 matches (comment + prose) | Carried; comment-block count satisfies intent |
| N2 — security-verify C2/C5/C9 FAILs are grep-spec drift | Carried; source behaviour correct per security-verify doc |
| N3 — 0.35s sleep fragile on slow CI hosts | Carried; acceptable for local personal-KB workflow |
| N4 — LOW sentinel reads "cycle 28" while inheriting cycle-13 closures | Carried; matches established sentinel pattern |
| N5 — `import time` asymmetry (function-local embeddings.py vs module-level bm25.py) | Carried; intentional cycle-26 style match for embeddings |

All five correctly classified as cosmetic per cycle-12 L3. None should have been fixed in-cycle.

**PASS — NITs properly carried; none silently dropped.**

---

## Pre-existing uncommitted BACKLOG.md modification

The git status at session start showed `M BACKLOG.md` (modified, unstaged). Inspecting `git diff HEAD -- BACKLOG.md` reveals two new MEDIUM entries:

- `compile/compiler.py rebuild_indexes audit status` (R2 Codex 2026-04-24)
- `compile/compiler.py rebuild_indexes hash_manifest / vector_db overrides` (R3 Codex 2026-04-24)

These entries are NOT present in the last committed revision of BACKLOG.md (`ddedce6`). The entries were not part of any committed cycle-28 doc or fix commit. Their date tag `(R2 Codex 2026-04-24)` / `(R3 Codex 2026-04-24)` suggests they were discovered during cycle-28's PR review process (the R2 Codex PR review doc `2026-04-24-cycle28-pr42-r2-codex.md` contained these findings) and staged for BACKLOG addition but never committed.

**Verdict on this pre-existing state:** these are legitimately new MEDIUM open issues discovered during PR review and correctly belong in BACKLOG.md. They were not part of cycle 28's C13 hygiene scope (C13 specified three specific mutations, all of which landed correctly in commit `a96f043`). The uncommitted working-tree state represents a valid post-review addition that was not yet committed — likely an oversight in the R2 doc commit. This cycle should commit these two lines to satisfy the BACKLOG lifecycle rule (discoveries from PR review go into BACKLOG before merge). This is a **minor omission**, not a design drift issue.

---

## Overall verdict

**APPROVE.**

All five audit-doc drift checks pass: threat-model T1-T8 mitigations match shipped code, AC count (9) matches between design and CHANGELOG, test file count (1 new) and delta (+8, 2801→2809) are correct, commit count (6) is arithmetically consistent with the self-referential rule, and BACKLOG C13 three-mutation hygiene is complete and follows the delete-not-strikethrough lifecycle rule.

Same-class peer scope-out is clean — none of the 6 deferred candidates crept in. N1-N5 from R1 Sonnet are properly carried as cosmetic NITs per cycle-12 L3.

One minor pre-merge action recommended: stage and commit the two uncommitted MEDIUM BACKLOG entries (`rebuild_indexes audit status` and `rebuild_indexes hash_manifest / vector_db overrides`) that exist in the working tree but were not captured in any branch commit. These are valid post-PR-review discoveries that belong in BACKLOG.md before merge; leaving them uncommitted means they would be lost on branch cleanup. This does not constitute a design drift issue but should be resolved before merge to maintain BACKLOG hygiene.

No blockers. No majors. One minor cleanup action before merge.
