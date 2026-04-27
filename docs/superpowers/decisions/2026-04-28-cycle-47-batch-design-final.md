# Cycle 47 — Batch Design (FINAL)

**Date:** 2026-04-28
**Branch:** cycle-47-batch
**Worktree:** `D:\Projects\llm-wiki-flywheel-c47`
**Step:** 5 design-decision gate (post R1 DeepSeek + R2 Codex)
**Verdict:** APPROVED WITH AMENDMENTS — proceed to Step 6 (plan).

This document is the binding output of the Step-5 design-decision gate. It
RESOLVES every open question (Q1–Q5), every R2 BLOCKER (B1, B2), and every R2
MAJOR (M1, M2, M3). The 18-AC numbering from the design draft is preserved
(no renumber). Step 6 plan + Step 9 implementation MUST satisfy the binding
CONDITIONS at the bottom.

---

## Verification snapshot (re-grepped during this gate)

| Claim | Verification | Result |
|---|---|---|
| pip is NOT in `requirements.txt` | `Grep ^pip== requirements.txt` | NO MATCH — confirms B1 |
| 7 (not 6) `cycle-46 re-confirmed` stamps | `Grep "cycle-46 re-confirmed" BACKLOG.md` | 7 hits at lines 126, 129, 132, 135, 158, 170, 172 — confirms M3 |
| Current test-file count | `ls tests/test_*.py | wc -l` | 243 (108 cycle-stamped + 135 canonical) — confirms Q4 baseline |
| `tests/test_config.py` exists? | `ls tests/test_config.py` | NOT_PRESENT — confirms AC7 destination is greenfield |
| `_assert_create_page_error` collision in receiver? | `Grep tests/` | Only in source `test_cycle11_task6_mcp_ingest_type.py:4,20,31,44,57` — receiver `test_mcp_core.py` has zero hit; M1 path is clear |
| `test_cycle23_workflow_e2e.py` Thread/multiprocessing? | `Grep` | ZERO hits — R2 correct; remove from BACKLOG candidate list |
| Grep-proven Thread/MP candidates | `grep -lE "Thread\|multiprocessing\|ThreadPool" tests/test_cycle*.py` | `test_cycle16_duplicate_slugs.py`, `test_cycle20_write_wiki_page_exclusive.py`, `test_cycle23_file_lock_multiprocessing.py`, `test_cycle23_rebuild_indexes.py:233`, `test_cycle24_lock_backoff.py:222`, `test_cycle25_dim_mismatch.py:180`, `test_cycle26_cold_load_observability.py`, `test_cycle32_cli_parity_and_fair_queue.py`, `test_cycle36_ci_hardening.py`, `test_cycle8_contradictions_idempotent.py` |

---

# Part 1 — Open question decisions (Q1–Q5)

## Q1 — `test_config.py` (separate file) vs split AC7 constants between `test_lint.py` + `test_query.py`?

### Analysis

The three constants under test in `test_cycle16_config_constants.py` —
`QUERY_REPHRASING_MAX`, `DUPLICATE_SLUG_DISTANCE_THRESHOLD`, and
`CALLOUT_MARKERS` — all live in `src/kb/config.py`. Semantically they
do split: `QUERY_REPHRASING_MAX` is consumed by query, the other two by
lint. R1 (DeepSeek) endorsed the new file as the right shape on cluster
grounds; R2 (Codex) confirmed there is no pre-existing `tests/test_config.py`,
so a new file has zero collision risk. The "constants module test cluster"
pattern matters because future cycles will add more constants from the same
module (cycle-44 already added `lint/checks` constants — those are the
cluster's natural growth path), and a single receiver gives one obvious
landing zone instead of forcing a per-consumer hunt every time.

The alternative (split between `test_lint.py` + `test_query.py`) is
non-obviously worse on three axes: (a) it drops the cluster-by-source-module
discoverability that mirrors `src/kb/config.py` itself (one source ↔ one
test file is the existing convention for `test_models.py` ↔ `models.py`,
`test_lint.py` ↔ `lint.py` legacy single-file etc.); (b) it splits 5 tests
across 2 files, complicating the cycle-43 L1 isolation+full-suite check
(now 2 receivers to re-collect-only); (c) it pre-commits a binding pattern
that future constants additions must follow even when the consumer is
ambiguous (e.g., a cross-cutting constant). The hygiene-cycle blast-radius
heuristic prefers reversible over irreversible: a new `test_config.py` is
trivially mergeable into `test_lint.py` later if the cluster collapses,
but a 2-file split is never trivially un-split.

**DECIDE:** New `tests/test_config.py` file. Fold all 5 tests as
`TestConfigConstants` class.
**RATIONALE:** Cluster-by-source-module mirrors `src/kb/config.py` (one
source ↔ one receiver). Greenfield destination = zero collision.
Single-receiver fold simplifies the cycle-43 L1 isolation+full-suite
re-collect check. Reversible if cluster ever collapses; un-split is
irreversible.
**CONFIDENCE:** HIGH.

## Q2 — AC9 fold (5 classes into `test_models.py`) risk fixture-scope collisions with existing `pages.load_page_frontmatter.cache_clear()` calls?

### Analysis

The source `test_cycle14_save_frontmatter.py` exercises
`save_page_frontmatter` (the WRITE path), not `load_page_frontmatter` (the
READ path). The receiver `test_models.py` has explicit
`load_page_frontmatter.cache_clear()` calls at lines 58, 78, 104, 135, 168,
197 — all inside read-path tests. Save-path tests do not touch the LRU,
so the fixture concern is asymmetric: the new classes do not need cache
teardown, and the existing read-path tests do not pre-poison the LRU with
state that the new write-path tests would observe (each save-path test
constructs a fresh `tmp_path` Post and asserts on disk bytes). Function-
scoped `tmp_path` provides fresh roots per test; `frontmatter.Post`
construction inside each test method (per Condition 3) avoids module-level
shared state.

The only residual risk is full-suite ordering: if a save-path test in a
new class somehow leaves an entry in the read-path LRU cache (e.g., by
opportunistically calling `load_page_frontmatter` for verification), a
later read-path test could observe stale data. Mitigation is to keep the
new classes pure-write — no `load_page_frontmatter` calls inside the
folded classes. R2 explicitly noted this risk and recommended the same:
"AtomicWrite must not depend on cache setup". The cycle-22 L3 isolation
+ full-suite check at Step 9 catches any drift.

**DECIDE:** SAFE to fold AC9 into `test_models.py` as 5 classes
(`TestSaveFrontmatterInsertionOrder`, `TestSaveFrontmatterBodyVerbatim`,
`TestSaveFrontmatterListValuedMetadataOrder`,
`TestSaveFrontmatterExtraKeysPreserved`, `TestSaveFrontmatterAtomicWrite`),
PROVIDED: (a) no folded test calls `load_page_frontmatter` (read path) —
all assertions read disk bytes directly; (b) `frontmatter.Post`
construction stays function-local (no module-level helper); (c) Step 9
runs both `pytest tests/test_models.py -q` AND
`pytest -q | tail -3` per cycle-22 L3.
**RATIONALE:** Save-path vs read-path asymmetry means the existing
`load_page_frontmatter.cache_clear()` calls are orthogonal to the new
classes; `tmp_path` is function-scoped so no on-disk cross-talk;
explicit no-load discipline keeps the LRU untouched.
**CONFIDENCE:** HIGH.

## Q3 — AC10 (Windows CI investigation): apply skipif inline if high-confidence reproducer found vs strictly defer per cycle-36 L1?

### Analysis

The deciding fact is reproducibility. The `threading.py:355` hang fires
ONLY on the GHA `windows-latest` runner; local Windows full suite passes
in 1.03s for the cycle-23 test that was previously skipif'd. I do not
have a self-hosted Windows runner. Without a reproducer, "high
confidence" via grep alone is illusory: cycle-36 L1 explicitly costs each
new failed CI run as user-visible noise, and applying a skipif to the
wrong test (a) wastes a CI dimension on a no-op fix, (b) hides the real
hanger from future investigation, (c) creates a false signal that the
investigation is "in progress" when in fact it is still untouched. The
grep evidence (R2 cited `test_cycle23_rebuild_indexes.py:213-248`,
`test_cycle25_dim_mismatch.py:180-184`, `test_cycle24_lock_backoff.py:222-228`)
narrows the candidate set, but ranking among 3 grep-proven candidates
without a reproducer is guessing.

The bias rule on this project is "lower blast radius wins" and "reversible
> irreversible". A BACKLOG-entry refresh with a ranked frontier list is
fully reversible; a CI skipif is not (other devs see "skipif" and stop
poking the test). Cycle-36 L1 is a conscious trade: defer the marker
until a reproducer exists. Cycle 47 is HYGIENE-only with 18 ACs already;
ship the frontier list now, ship the marker (or root-cause fix) when a
self-hosted runner exists in cycle 48+ or later.

**DECIDE:** STRICTLY DEFER skipif application. Cycle-47 produces a
refined BACKLOG entry only, with the grep-proven ranked frontier list
(see M2 below). NO skipif markers applied this cycle.
**RATIONALE:** No reproducer = no high confidence. Cycle-36 L1 CI-cost
discipline + bias toward reversible. BACKLOG frontier refresh is the
correct deliverable; root-cause work waits for reproducer.
**CONFIDENCE:** HIGH.

## Q4 — File count math: 243 → 241 (after −3 folds + 1 new file)?

### Analysis

The verification grep above confirms current `ls tests/test_*.py | wc -l`
is 243 (post-cycle-46). The design draft introduced a wording bug at line
21 ("Net file delta: −3 + 1 = **−2 files** (245 → 243)") that R2 caught
as B2: it cites the wrong baseline 245. The cycle-44 chain was 240 → 241
(net +1), cycle-45 added one then hotfix-removed one (244 → 243), cycle 46
was no-fold (243 → 243). So the cycle-47 starting baseline is unambiguously
243. Three folds (`test_cycle16_config_constants.py`,
`test_cycle11_task6_mcp_ingest_type.py`, `test_cycle14_save_frontmatter.py`)
remove 3 files. One new file (`test_config.py` per Q1) adds 1 file. Net
delta: −2. End state: 241.

Doc-sync surfaces that report file count: `BACKLOG.md` Phase 4.5 HIGH #4
progress note, `docs/reference/testing.md`, `docs/reference/implementation-status.md`.
Surfaces that report TEST count (not FILE count): `CLAUDE.md` Quick
Reference (3025), `README.md` tree block (3025), `CHANGELOG.md` cycle-47
Quick Reference. The test count should remain 3025 (folds preserve all
20 tests as classes/functions in destinations; AC10 in the original
requirements doc requires `pytest --collect-only | tail -1` zero-delta
verification — preserved here as Condition 6c). All file-count text
must say "243 → 241"; all test-count text must say "3025" (unchanged).

**DECIDE:** CANONICAL CHAIN: file count `243 → 241` (net −2);
test count `3025 → 3025` (unchanged, preserved as classes/parametrize).
This is the binding wording for ALL doc surfaces.
**RATIONALE:** Verified 243 baseline via direct ls. Math: -3 folds + 1
new file = -2 net. Test count unchanged because folds preserve, not
delete.
**CONFIDENCE:** HIGH.

## Q5 — Are there other dep-CVE entries beyond the 4 pip-audit + 2 Dependabot drift that need timestamp refresh?

### Analysis

R2 grep evidence (and re-verified during this gate) shows BACKLOG.md has
7 `cycle-46 re-confirmed` stamps, not 6: lines 126 (diskcache), 129
(ragas), 132 (litellm-1.83.0 wheel METADATA), 135 (pip 26.0.1), 158
(`requirements.txt` resolver conflicts — cycle-34 AC52), 170 (Dependabot
litellm GHSA-r75f), 172 (Dependabot litellm GHSA-v4p8). The line-158
entry is NOT a dep-CVE per se — it is a `pip check` resolver-conflict
status entry tracking three transitive constraint mismatches
(arxiv/requests, crawl4ai/lxml, instructor/rich). It uses the same
"cycle-46 re-confirmed" stamp pattern because it follows the same
"verify state hasn't changed" workflow.

The decision is not whether to refresh the line-158 stamp, but whether
to scope it INTO AC13 (dep-CVE refresh) or treat it as a separate
hygiene concern. Hygiene cycle posture: refreshing a 7th stamp is
text-only zero-risk, and skipping it leaves a falsely-old timestamp on a
tracked entry, violating the spirit of the cycle-22 L4 cross-cycle
re-confirmation discipline. AC13 already says "Refresh dep-CVE
re-verification dates"; the resolver-conflict entry is not a CVE but is
the same SHAPE of entry (tracked drift, no fix this cycle). Expanding
AC13's scope by one bullet adds zero blast radius. R2's M3 is correct
and I am adopting it.

**DECIDE:** YES — AC13 scope expands to include the line-158 resolver-
conflict entry. Canonical list of 7 stamps to refresh: BACKLOG.md lines
126 (diskcache), 129 (ragas), 132 (litellm-1.83.0), 135 (pip-26.0.1),
158 (requirements.txt resolver conflicts), 170 (Dependabot
GHSA-r75f-5x8p-qvmc), 172 (Dependabot GHSA-v4p8-mg3p-g94g).
**RATIONALE:** Same re-confirmation shape; refresh is text-only;
omitting leaves a stale stamp under cycle-22 L4 discipline.
**CONFIDENCE:** HIGH.

---

# Part 2 — R2 BLOCKER decisions (B1, B2)

## B1 — AC4 wording: pip is NOT in `requirements.txt` (live verification confirmed)

### Analysis

Direct verification: `Grep ^pip== requirements.txt` returns NO MATCH.
The current BACKLOG.md line 135 is misleading: it phrases the entry as
"`requirements.txt` `pip==26.0.1`" as if `pip==26.0.1` were a pin in
the requirements file, but in fact pip is the installer itself and its
version is a live-environment fact (the venv `.venv\Scripts\pip.exe`
reports 26.0.1). pip-audit reads the live env and emits the CVE for
what it sees installed; there is no requirements pin to bump. This
matters because the cycle-22 L4 conservative posture ("do NOT bump
26.0.1 → 26.1") was applied as if a pin existed; in reality the
posture is "do NOT upgrade the live-env installer until the GHSA-58qw
advisory confirms 26.1 patches the CVE". The semantic content is
correct but the locator and verb are wrong.

The fix is a one-paragraph re-word of the BACKLOG entry: replace the
locator (`requirements.txt` → `.venv installer`) and verb (do not
"bump" the pin → do not "upgrade" the installer). The verification
chain stays identical (advisory metadata + LATEST = 26.1 + null
patched_versions). AC4 the requirement still applies; only the BACKLOG
entry text is wrong. The Step-9 implementation must (a) re-word the
BACKLOG entry, (b) re-word any AC4 self-reference in CHANGELOG /
CHANGELOG-history that copy-pastes the misnomer.

**DECIDE:** AC4 BACKLOG entry MUST be re-worded. Canonical replacement:

> `.venv` `pip==26.0.1` (installer in live env; not a `requirements.txt`
> pin — pip is the installer itself) — CVE-2026-3219
> (GHSA-58qw-9mgm-455v): pip handles concatenated tar+ZIP files as ZIP
> regardless of filename, enabling confusing installation behavior. No
> CONFIRMED patched upstream as of 2026-04-27 (`pip-audit` still reports
> empty `fix_versions`). *(Surfaced 2026-04-25 cycle 32 Step 11 PR-CVE
> diff; cross-cycle advisory arrival per cycle-22 L4. Cycle-47
> re-confirmed 2026-04-28: pip 26.1 remains LATEST per `pip index
> versions pip` (published 2026-04-27 during cycle 40), but the
> GHSA-58qw-9mgm-455v advisory metadata still lists
> `vulnerable_version_range: <=26.0.1` AND `patched_versions: null` —
> the advisory has NOT yet been updated to confirm 26.1 patches the
> CVE, so pip-audit continues to emit empty `fix_versions`. Per
> cycle-22 L4 conservative posture: do NOT upgrade the installer until
> the advisory or PyPA security disclosure confirms 26.1 patches the
> CVE; track for next cycle.)*
>   (mitigation: narrow-role — pip is TOOLING, not runtime; advisory
> affects package installation (`pip install` of adversarial tar+zip
> payloads) which requires local shell access. Production kb runtime
> never shells out to pip. Track upstream for patched release.)

**RATIONALE:** Verified: pip is not in requirements.txt. Locator
correction (`.venv` installer, not `requirements.txt` pin) makes the
posture statement accurate. Re-confirms cycle-22 L4 conservative
posture without implying a pin exists. Single-text fix; zero blast
radius.
**CONFIDENCE:** HIGH.

## B2 — File-count drift: design draft says "245 → 243"; correct math is "243 → 241"

### Analysis

Per Q4 above, the verified baseline is 243 and the verified delta is −2,
so the canonical end state is 241. The design draft contained a wording
bug citing 245 (wrong baseline) → 243 (which happens to be the actual
current count, creating spurious agreement). All downstream docs that
reference this chain risk inheriting the wrong baseline. The full list
of doc surfaces that need consistent file-count wording:

1. `BACKLOG.md` Phase 4.5 HIGH #4 progress note (AC11)
2. `docs/reference/testing.md` cycle-47 history entry (AC18)
3. `docs/reference/implementation-status.md` cycle-47 latest-cycle notes (AC18)
4. `CHANGELOG.md` cycle-47 Quick Reference Items field (AC14)
5. `CHANGELOG-history.md` cycle-47 detail (AC15)

Surfaces that report TEST count (not FILE count) must remain on 3025
(folds preserve the 20 tests). `CLAUDE.md` Quick Reference and
`README.md` tree block both quote 3025; if Step 9 collect-only verifies
zero delta, NEITHER needs an update. Step 9 binding action is to run
`pytest --collect-only -q | tail -1` pre-fold and post-fold, assert
identical count, then write `3025` everywhere. Any drift kills the
fold protocol per cycle-22 L3.

**DECIDE:** CANONICAL FILE-COUNT WORDING FOR ALL DOCS:

- File count: `243 → 241` (net `−2`).
- Test count: `3025 → 3025` (unchanged; folds preserve as classes /
  parametrize / functions).
- Doc surfaces requiring file-count update: BACKLOG.md (line 91
  Phase 4.5 HIGH #4), `docs/reference/testing.md`,
  `docs/reference/implementation-status.md`, `CHANGELOG.md` cycle-47
  Quick Reference, `CHANGELOG-history.md` cycle-47 detail.
- Doc surfaces requiring TEST count VERIFICATION (no edit if unchanged):
  `CLAUDE.md` Quick Reference (3025), `README.md` tree block (3025).
- If pytest --collect-only -q shows test-count drift post-fold, the
  fold is broken (cycle-22 L3 violation) — STOP and investigate; do
  NOT silently update doc surfaces to a new test count.

**RATIONALE:** Verified 243 baseline; verified math −2. Canonical
wording prevents any inherited drift across 5 doc surfaces. Strict
test-count zero-delta gate enforces the fold-correctness contract.
**CONFIDENCE:** HIGH.

---

# Part 3 — R2 MAJOR decisions (M1, M2, M3)

## M1 — AC8 helper: `_assert_create_page_error` must be class-local/static, no module-level helper

### Analysis

Verified state: source `test_cycle11_task6_mcp_ingest_type.py:4` defines
`_assert_create_page_error` at module level and uses it in 4 tests
(lines 20, 31, 44, 57). Receiver `test_mcp_core.py` has zero hits for
the helper name and uses a different module-level helper
`_patch_source_type_dirs` at lines 25–35. Two failure modes if the
helper is folded as a module-level helper into the receiver: (a)
naming-pollution risk if a future test in `test_mcp_core.py` adds a
similarly-named helper for a different assertion shape, the file-local
search becomes ambiguous; (b) function-scoped monkeypatch isolation
between sibling tests can be subtly broken if a module-level helper
captures state at import time. The cleanest fold pattern is a class-
local static helper on the new test class (`TestKbCreatePageHintErrors`),
which (i) keeps the helper visible only inside the class, (ii) does
not pollute module namespace, (iii) preserves function-scoped
monkeypatch isolation since each test method gets its own `monkeypatch`
fixture instance.

R2 explicitly recommends class/static. The design draft Condition 2
already says "rename to `_assert_create_page_error_for_alternative_type`
or wrap inside the new class as a static helper" — adopt the SECOND
clause unconditionally and drop the rename option (renaming a module-
level helper still leaves it module-level, which is the failure mode).
The implementation pattern is `@staticmethod def _assert(result: str)
-> None: ...` inside `TestKbCreatePageHintErrors`. Each test method
calls `self._assert(result)`. This eliminates collision risk by
construction.

**DECIDE:** AC8 fold MUST use a class-local `@staticmethod` helper
inside `TestKbCreatePageHintErrors`. No module-level helper. No rename
of a module-level helper as fallback. Each test method calls
`self._assert_create_page_error(result)` (or shorter local name like
`self._assert_error`).
**RATIONALE:** Class-local + static keeps namespace clean, preserves
function-scoped monkeypatch isolation by construction, and eliminates
collision risk regardless of future receiver growth.
**CONFIDENCE:** HIGH.

## M2 — AC10 BACKLOG frontier: prioritize grep-proven threading tests; remove `test_cycle23_workflow_e2e.py`

### Analysis

R2 verified (and I re-verified): `test_cycle23_workflow_e2e.py` has
ZERO Thread/multiprocessing hits. The current BACKLOG.md line 164
text says "(likely in `test_cycle23_workflow_e2e.py` or
`test_cycle23_rebuild_indexes.py`)" — the first half is wrong. The
grep-proven candidates (re-verified during this gate) are:

- `test_cycle16_duplicate_slugs.py` (uses Thread/MP)
- `test_cycle20_write_wiki_page_exclusive.py` (uses Thread/MP)
- `test_cycle23_file_lock_multiprocessing.py` (the existing skipif'd file)
- `test_cycle23_rebuild_indexes.py:233` (uses `threading.Thread(target=holder)`)
- `test_cycle24_lock_backoff.py:222` (uses `threading.Thread(target=lambda: None)`)
- `test_cycle25_dim_mismatch.py:180` (uses `[threading.Thread(target=_worker) for _ in range(n_threads)]`)
- `test_cycle26_cold_load_observability.py` (uses Thread/MP)
- `test_cycle32_cli_parity_and_fair_queue.py` (uses Thread/MP)
- `test_cycle36_ci_hardening.py` (uses Thread/MP)
- `test_cycle8_contradictions_idempotent.py` (uses Thread/MP)

Ranking by likelihood of GHA-windows hang at `threading.py:355`: the
hang signature points at a thread waiting on `_tstate_lock.acquire()`
during shutdown, which most commonly fires when a test creates a
worker thread and the test exits before the thread finishes. The
top-3 highest-prior candidates are the ones with the MOST threads
held against an unreliable Windows-CI fs/sqlite shutdown:

1. `test_cycle25_dim_mismatch.py:180` — N-threads parallel sqlite
   write; sqlite-on-Windows shutdown is the known C25 hot zone.
2. `test_cycle23_rebuild_indexes.py:233` — single thread holding a
   long lock + main thread re-entry; rebuild-indexes path touches
   the manifest lock (slow Windows fs).
3. `test_cycle24_lock_backoff.py:222` — exponential-backoff thread
   may overshoot CI shutdown.

Lower-priority (instrument later): `test_cycle32_cli_parity_and_fair_queue.py`
(fair-queue Threads), `test_cycle26_cold_load_observability.py`
(load-observability Threads), `test_cycle16_duplicate_slugs.py`,
`test_cycle20_write_wiki_page_exclusive.py`,
`test_cycle36_ci_hardening.py`, `test_cycle8_contradictions_idempotent.py`.
The cycle-23 file_lock_multiprocessing test is already skipif'd
(cycle-36 AC2) so it is a "known second-step verify".

**DECIDE:** AC10 BACKLOG entry MUST replace the misleading
"(likely in `test_cycle23_workflow_e2e.py` or
`test_cycle23_rebuild_indexes.py`)" with the ranked frontier list:

> Cycle-47 frontier (grep-proven Thread/multiprocessing candidates,
> ranked by GHA-windows shutdown-hang likelihood):
> 1. `tests/test_cycle25_dim_mismatch.py:180-184` — N-thread parallel
>    sqlite write; sqlite-on-Windows shutdown is a known cycle-25 hot
>    zone.
> 2. `tests/test_cycle23_rebuild_indexes.py:213-248` (Thread at line
>    233) — single thread holding a long lock; rebuild-indexes path
>    touches the manifest lock (slow Windows fs).
> 3. `tests/test_cycle24_lock_backoff.py:222-228` — exponential-backoff
>    thread may overshoot CI shutdown.
>
> Lower-priority instrumentation order: `test_cycle32_cli_parity_and_fair_queue.py`,
> `test_cycle26_cold_load_observability.py`,
> `test_cycle16_duplicate_slugs.py`,
> `test_cycle20_write_wiki_page_exclusive.py`,
> `test_cycle36_ci_hardening.py`,
> `test_cycle8_contradictions_idempotent.py`. The cycle-23
> file_lock_multiprocessing test is already skipif'd
> (cycle-36 AC2) — re-verify the skipif still fires before the matrix
> re-enable. Note: the previously-cited `test_cycle23_workflow_e2e.py`
> has ZERO Thread/multiprocessing hits per cycle-47 grep — REMOVE from
> candidate set.

**RATIONALE:** Grep-proven candidate set + likelihood ranking gives
cycle 48+ a concrete first-look list. Removes the false-positive
candidate. No skipif applied this cycle (per Q3).
**CONFIDENCE:** HIGH.

## M3 — AC13 scope: case-sensitive grep for ALL `cycle-46 re-confirmed` stamps (7 entries, not 6)

### Analysis

Per Q5 above, the gate-time grep confirmed 7 hits at lines 126, 129,
132, 135, 158, 170, 172. The original AC13 wording "Refresh dep-CVE
re-verification dates in all 4 dep entries + 2 Dependabot drift
entries" misses the 7th: line 158 (`requirements.txt` resolver
conflicts — cycle-34 AC52 follow-up tracking three pip-check transitive
mismatches: arxiv/requests, crawl4ai/lxml, instructor/rich). This entry
uses the same "cycle-46 re-confirmed" stamp pattern because it follows
the same workflow — verify the state hasn't changed and refresh the
date — but it is NOT a CVE; it's a resolver-conflict status note.

R2's M3 is correct: AC13 should be expanded to include this entry. The
canonical 7-entry refresh list (in line-order):

1. Line 126 — `lint/fetcher.py` `diskcache==5.6.3` CVE
2. Line 129 — `requirements.txt` `ragas==0.4.3` CVE
3. Line 132 — `requirements.txt` `litellm==1.83.0` (3 GHSAs, click pin)
4. Line 135 — `requirements.txt` `pip==26.0.1` (re-worded per B1)
5. Line 158 — `requirements.txt` resolver conflicts (NOT a CVE; same workflow)
6. Line 170 — Dependabot litellm GHSA-r75f-5x8p-qvmc drift
7. Line 172 — Dependabot litellm GHSA-v4p8-mg3p-g94g drift

Step 9 implementation MUST run the case-sensitive grep
`grep -nE "cycle-46 re-confirmed" BACKLOG.md` BEFORE editing, count
the hits, and verify all 7 are touched. After editing, re-grep for
any residual `cycle-46 re-confirmed` (should be ZERO) and any new
`cycle-47 re-confirmed` (should be 7). This is the cycle-46 L4 case-
sensitive grep discipline — catches anyone editing only the named-CVE
entries and leaving the resolver-conflict entry behind.

**DECIDE:** AC13 SCOPE EXPANSION. Refresh dates on ALL 7
`cycle-46 re-confirmed` stamps to `cycle-47 re-confirmed 2026-04-28`.
The 5th entry (line 158, resolver conflicts) is NOT a CVE but uses
the same re-confirmation workflow. Step 9 verification: pre-edit grep
must count 7; post-edit grep for `cycle-46 re-confirmed` must count 0;
post-edit grep for `cycle-47 re-confirmed` must count 7.
**RATIONALE:** Same re-confirmation shape, same workflow; omitting one
leaves a stale stamp. Case-sensitive grep gate prevents partial
coverage.
**CONFIDENCE:** HIGH.

---

# Part 4 — FINAL DECIDED DESIGN

## 1. Final AC numbering

The design draft's AC1–AC18 numbering is preserved without renumber.
The mapping to requirements-doc AC1–AC20 (which used different
numbering) is implicit and need not be revisited.

## 2. Per-AC final scope

### Group A — Dep-CVE re-verification (6 ACs, mechanical, NO bumps)

- **AC1** — `requirements.txt` `diskcache==5.6.3`. Re-confirm
  `pip index versions diskcache` shows 5.6.3 = LATEST AND
  `pip-audit --format=json` reports empty `fix_versions` for
  GHSA-w8v5-vhqr-4h9v. Refresh BACKLOG.md line 126 timestamp from
  `cycle-46 re-confirmed 2026-04-28` to
  `cycle-47 re-confirmed 2026-04-28`.

- **AC2** — `requirements.txt` `ragas==0.4.3`. Re-confirm
  `pip index versions ragas` shows 0.4.3 = LATEST AND CVE-2026-6587
  has empty `fix_versions`. Refresh BACKLOG.md line 129 timestamp.

- **AC3** — `requirements.txt` `litellm==1.83.0`. Re-confirm via
  wheel-METADATA inspection (`pip download --no-deps litellm==1.83.14`
  + zipfile METADATA extraction) that the LATEST 1.83.14 still pins
  `Requires-Dist: click==8.1.8`. Refresh BACKLOG.md line 132 timestamp.

- **AC4 (RE-WORDED PER B1)** — `.venv` installer `pip==26.0.1` (NOT
  a `requirements.txt` pin — pip is the installer itself). Re-confirm
  `pip index versions pip` shows 26.1 = LATEST AND
  `gh api /advisories/GHSA-58qw-9mgm-455v --jq '{patched_versions, vulnerable_version_range}'`
  still reports null-patched. Re-word the BACKLOG.md line 135 entry
  per B1 canonical text. Refresh timestamp.

- **AC5** — Dependabot `litellm GHSA-r75f-5x8p-qvmc` drift. Re-confirm
  Dependabot still lists open AND `pip-audit --format=json` does NOT
  emit this ID. Refresh BACKLOG.md line 170 timestamp. Do NOT add to
  `--ignore-vuln`.

- **AC6** — Dependabot `litellm GHSA-v4p8-mg3p-g94g` drift. Same shape
  as AC5. Refresh BACKLOG.md line 172 timestamp.

### Group B — Test fold (3 ACs, atomic; protocol per Conditions 1, 2, 3, 6)

- **AC7** — Fold `tests/test_cycle16_config_constants.py` (5 tests, 38
  LOC, 3 constants `QUERY_REPHRASING_MAX`,
  `DUPLICATE_SLUG_DISTANCE_THRESHOLD`, `CALLOUT_MARKERS`) → NEW
  `tests/test_config.py` as `TestConfigConstants` class with 5 methods.
  Behaviour-only assertions. NO `inspect.getsource`. Source file
  DELETED in same commit. Per Q1: new file, not split.

- **AC8** — Fold `tests/test_cycle11_task6_mcp_ingest_type.py` (6 tests,
  78 LOC, 4 `_assert_create_page_error` callsites) →
  `tests/test_mcp_core.py` as `TestKbCreatePageHintErrors` class with 6
  methods. Helper `_assert_create_page_error` MUST be class-local
  `@staticmethod` (per M1). NO module-level helper. NO rename of a
  module-level helper. Coverage: `kb_ingest`, `kb_ingest_content`,
  `kb_save_source` rejecting `comparison`/`synthesis` with
  `kb_create_page` hint per cycle-11 AC2 same-class peer rule
  (cycle-11 L3). Source file DELETED in same commit.

- **AC9** — Fold `tests/test_cycle14_save_frontmatter.py` (9 tests, 139
  LOC, 5 source classes) → `tests/test_models.py` as 5 test classes
  (`TestSaveFrontmatterInsertionOrder`,
  `TestSaveFrontmatterBodyVerbatim`,
  `TestSaveFrontmatterListValuedMetadataOrder`,
  `TestSaveFrontmatterExtraKeysPreserved`,
  `TestSaveFrontmatterAtomicWrite`). Per Q2: NO test calls
  `load_page_frontmatter`; `frontmatter.Post` construction stays
  function-local; rename source `TestAtomicWriteProof` →
  `TestSaveFrontmatterAtomicWrite` in receiver only (note in fold
  comment per N1). Pinning `save_page_frontmatter` insertion-order +
  atomic-write contract per cycle-7 L1 (frontmatter `sort_keys=False`).
  Source file DELETED in same commit.

### Group C — Windows CI investigation (1 AC, best-effort, NO skipif)

- **AC10** — Read all tests using `threading.Thread`,
  `concurrent.futures.ThreadPoolExecutor`, `multiprocessing` from
  cycles 8, 16, 20, 23–26, 32, 36 (full grep-proven set). Update
  BACKLOG.md line 164 entry per M2 canonical text: insert the ranked
  frontier list (cycle-25 dim_mismatch, cycle-23 rebuild_indexes,
  cycle-24 lock_backoff as top-3) and EXPLICITLY REMOVE the false-
  positive `test_cycle23_workflow_e2e.py` reference. NO skipif markers
  applied (per Q3). NO `.github/workflows/ci.yml` changes. NO matrix
  re-enable.

### Group D — BACKLOG hygiene (3 ACs)

- **AC11** — Update BACKLOG.md Phase 4.5 HIGH #4 progress note (line
  91) with cycle-47 status: file count `243 → 241` (net `−2`); test
  count `3025 → 3025` (preserved); files folded:
  `test_cycle16_config_constants.py`, `test_cycle11_task6_mcp_ingest_type.py`,
  `test_cycle14_save_frontmatter.py`; cumulative remaining estimate
  (current 108 cycle-stamped → 105 post-cycle-47).

- **AC12** — Refresh ALL `(cycle-47+)` tagged entries in BACKLOG.md
  (lines 164, 166, 168, 170, 172) with cycle-47 re-confirmation
  timestamps. Spawn entries that remain open keep `(cycle-47+)` AND
  add `(cycle-47 re-confirmed N/A — prerequisite missing: <reason>)`
  for entries 164, 166, 168 (no GHA-Windows runner / POSIX shell).
  Entries 170 + 172 (Dependabot drift) get `cycle-47 re-confirmed
  2026-04-28: drift persists` (paired with AC5/AC6).

- **AC13 (SCOPE-EXPANDED PER M3)** — Refresh dep-CVE / re-confirmation
  timestamps on ALL 7 `cycle-46 re-confirmed` stamps in BACKLOG.md
  (lines 126, 129, 132, 135, 158, 170, 172) to
  `cycle-47 re-confirmed 2026-04-28`. Includes the non-CVE
  resolver-conflict entry at line 158 (cycle-34 AC52 follow-up).
  Step-9 verification: pre-edit grep counts 7; post-edit grep for
  `cycle-46 re-confirmed` counts 0; post-edit grep for
  `cycle-47 re-confirmed` counts 7.

### Group E — Documentation (5 ACs)

- **AC14** — `CHANGELOG.md` cycle-47 Quick Reference entry under
  `[Unreleased]`. Compact format Items / Tests / Scope / Detail.
  Items: 18 ACs across ~8 src+test files + ~6 doc files. Tests:
  `3025 → 3025` (preserved as classes/parametrize). Scope: hygiene
  + dep-CVE re-verify + 3 small folds + best-effort Windows CI
  frontier + BACKLOG hygiene. Detail: file count `243 → 241` (−2);
  3 folds (cycle16_config_constants → new test_config.py;
  cycle11_task6_mcp_ingest_type → test_mcp_core.py;
  cycle14_save_frontmatter → test_models.py); 7 BACKLOG re-confirmed
  stamps refreshed cycle-46 → cycle-47.

- **AC15** — `CHANGELOG-history.md` cycle-47 full bullet detail
  (newest first), enumerating every AC closed (AC1–AC18). Use
  canonical file-count chain `243 → 241`.

- **AC16** — `CLAUDE.md` Quick Reference: VERIFY test count (3025)
  unchanged via `pytest --collect-only -q | tail -1`. If unchanged,
  edit only the cycle stamp ("cycle 36 / 39 / 40 / 41 / 42 / 43 / 44 /
  45 / 46" → append "/ 47"). If TEST count drifted, STOP — fold
  protocol violation per cycle-22 L3.

- **AC17** — `README.md` tree-block test count (per C39-L3). VERIFY
  3025 unchanged. If unchanged, no README edit required.

- **AC18** — `docs/reference/testing.md` cycle 47 history entry +
  `docs/reference/implementation-status.md` cycle 47 latest-cycle
  notes (per C26-L2 + cycle-35 extension). Use canonical file-count
  chain `243 → 241`.

## 3. Binding CONDITIONS for Step 9 (MUST satisfy)

These are the gate's binding conditions. Step 9 implementation
violations of any single condition are a fold/protocol failure.

**Condition 1 — Fold protocol (per AC7, AC8, AC9):** For each fold:
(a) `Read` source file verbatim; (b) write the receiver edits
(prepend with cycle-47 stamped section comment); (c) DELETE source
file in the same commit; (d) run `pytest <receiver_file> -q`
isolation check; (e) run `pytest -q | tail -3` full-suite check;
(f) if (d) or (e) shows test-count drift OR new failures, REVERT and
investigate before re-attempting (cycle-22 L3 + cycle-43 L1).

**Condition 2 — AC8 helper:** `_assert_create_page_error` MUST be a
`@staticmethod` inside `TestKbCreatePageHintErrors`. NO module-level
helper. NO module-level rename. Each test method calls
`self._assert_create_page_error(result)` (or shorter local name).

**Condition 3 — AC9 helper:** `frontmatter.Post` construction MUST
stay function-local in each new test method. NO module-level helper
or fixture promotion. Source class `TestAtomicWriteProof` renamed in
receiver to `TestSaveFrontmatterAtomicWrite` (note in fold comment).
NO folded test calls `load_page_frontmatter` (read path) — assertions
read disk bytes directly.

**Condition 4 — NO skipif this cycle (per AC10):** Cycle-36 L1
CI-cost discipline. AC10 produces refined BACKLOG entry only. NO
`.github/workflows/ci.yml` edits. NO matrix re-enable.

**Condition 5 — Timestamp pattern:** Use
`cycle-47 re-confirmed 2026-04-28` (NOT `cycle-46 re-confirmed
2026-04-28` and NOT bare `2026-04-28`). The cycle stamp distinguishes
re-confirmations on the same calendar day across parallel cycle
worktrees (cycle-43 L1 + cycle-42 L4).

**Condition 6 — Isolation + full-suite + collect-only checks per
fold commit:** (a) `pytest <receiver_file> -q` isolation pass;
(b) `pytest -q | tail -3` full suite pass; (c) `pytest --collect-only
-q | tail -1` test-count must equal 3025 BOTH pre-fold and post-fold.
Drift in (c) = fold broken; STOP.

**Condition 7 — AC4 re-word:** BACKLOG.md line 135 entry MUST be
re-worded per B1 canonical text. Replace locator (`requirements.txt`
→ `.venv` installer) and verb (do not "bump" → do not "upgrade").

**Condition 8 — File-count canonical chain:** ALL doc surfaces use
`243 → 241` (file count) and `3025 → 3025` (test count). No surface
may report a different chain. AC11, AC14, AC15, AC18 are the
file-count surfaces; AC16, AC17 are the test-count verification
surfaces.

**Condition 9 — AC13 7-entry coverage gate:** Step 9 MUST run
`grep -nE "cycle-46 re-confirmed" BACKLOG.md` BEFORE editing (must
count 7). After editing, MUST re-run and count 0. Must
`grep -nE "cycle-47 re-confirmed" BACKLOG.md` and count 7.
Coverage gate prevents partial AC13 application.

**Condition 10 — AC10 frontier text:** BACKLOG.md line 164 entry
MUST insert M2 canonical ranked frontier (cycle-25 dim_mismatch,
cycle-23 rebuild_indexes, cycle-24 lock_backoff in top-3) AND
EXPLICITLY REMOVE the false-positive `test_cycle23_workflow_e2e.py`
reference from the existing entry text.

**Condition 11 — Branch + worktree discipline:** Every commit MUST
verify `git branch --show-current` = `cycle-47-batch` and worktree
path = `D:\Projects\llm-wiki-flywheel-c47` (cycle-42 L4 +
cycle-43 L1). Never commit on `main`.

**Condition 12 — Step 11 PR-CVE diff baseline:** Use
`.data/cycle-47/cve-baseline.json` (already captured in Step 2).
Class B (PR-introduced) expected EMPTY since cycle 47 introduces no
new pins or transitive bumps. Late-arrival monitoring per cycle-22 L4.

## 4. SCOPE-OUT items (explicitly named)

These items are EXPLICITLY OUT OF SCOPE for cycle 47. Filing or
deferring is the correct disposition; inline implementation is a
scope violation.

1. **Apply skipif markers to Windows-CI tests** — deferred to cycle
   48+ pending self-hosted Windows runner. AC10 produces frontier
   list only.

2. **Re-enable matrix `[ubuntu-latest, windows-latest]`** — deferred
   to cycle 48+ pending skipif application after reproducer.

3. **Bump pip 26.0.1 → 26.1, litellm 1.83.0 → 1.83.7+, ragas 0.4.3 →
   newer, diskcache 5.6.3 → newer** — all blocked per cycle-22 L4
   conservative posture (no advisory confirmation OR transitive pin
   conflict). NO bumps this cycle.

4. **Add Dependabot drift IDs to `--ignore-vuln`** — DO NOT add unless
   pip-audit catches up (per AC5/AC6). Adding now would suppress a
   real signal if pip-audit later emits the ID.

5. **Aggressive folds** (e.g., `test_cycle14_augment_key_order.py`,
   `test_cycle13_frontmatter_migration.py`, `test_cycle19_lint_redundant_patches.py`)
   — REJECTED per design draft Approach B. Cycle 47 ships 3 folds;
   queue further folds for cycle 48+.

6. **Production-side opportunistic patches** (config.py god-module
   split, `kb.query.hybrid KB_DISABLE_VECTORS=1` shim) — REJECTED
   per design draft Approach C. Hygiene cycle scope only.

7. **POSIX `test_capture.py::TestWriteItemFiles` investigation** —
   deferred to cycle 48+ pending POSIX shell access. AC12 keeps the
   `(cycle-47+)` tag with `(cycle-47 re-confirmed N/A —
   prerequisite missing: POSIX shell)`.

8. **GHA-Windows multiprocessing spawn investigation** — deferred to
   cycle 48+ pending self-hosted Windows runner. AC12 keeps the
   `(cycle-47+)` tag with `(cycle-47 re-confirmed N/A —
   prerequisite missing: self-hosted Windows runner)`.

9. **CI workflow edits** — NO edits to `.github/workflows/ci.yml`
   this cycle (Condition 4). The workflow stays
   ubuntu-latest-strict-only.

10. **Test count delta** — folds MUST preserve all 20 source tests as
    classes/parametrize/methods in receivers. Test count `3025 → 3025`.
    Any drift in `pytest --collect-only -q | tail -1` = fold broken;
    Condition 6 enforces.

---

## Post-decision verdict

**Status:** APPROVED WITH AMENDMENTS. All 5 open questions decided.
Both R2 BLOCKERS (B1, B2) resolved with binding canonical text
(re-worded BACKLOG entry; canonical file-count chain). All 3 R2
MAJORS (M1, M2, M3) resolved with binding implementation conditions
(class-local helper; ranked frontier; 7-entry coverage gate). R1
verdict (APPROVE) is consistent with this gate's outcome modulo R2's
catches.

Step 6 (plan) MAY proceed using AC1–AC18 numbering and the 12 binding
Conditions above. Step 9 (implementation) MUST satisfy all 12
Conditions; any violation is a protocol failure and triggers REVERT
before re-attempt.
