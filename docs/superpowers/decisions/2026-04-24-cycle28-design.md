# Cycle 28 — Design Decision (Step 5)

**Date:** 2026-04-24
**Step:** feature-dev Step 5 (Opus main, decision gate)
**Branch:** `feat/backlog-by-file-cycle28`
**Inputs:** requirements (AC1-AC9), threat model (T1-T8), brainstorm (Approach A + Q1-Q8), R1 Opus (APPROVE-W-COND + 3 conditions), R2 Codex (APPROVE-W-COND + Q9-Q11 + 3 conditions).

This gate collapses 11 open questions and 6 reviewer conditions into a single numbered CONDITIONS list that Step-9 implementer and Step-11 security-verify can check mechanically.

---

## Q1 — BM25Index WARN threshold?

**OPTIONS.** (a) No threshold, INFO-only (brainstorm bias). (b) Single threshold like `BM25_BUILD_WARN_THRESHOLD_SECS = 0.5`. (c) Size-relative threshold (warn when build-time-per-doc exceeds a ratio).

### Analysis

The sqlite-vec extension load is a process-boot event whose cost is bounded by DLL-load + filesystem-cache state — a single 0.3s threshold is meaningful because the cost does not scale with wiki size. BM25 indexing is fundamentally O(tokens) over the entire corpus: a 100-page personal KB and a 5,000-page shared KB will produce build times differing by 1-2 orders of magnitude. Any fixed threshold is either spammy on a healthy large wiki or uselessly high on a small wiki. Option (c) is more principled but requires a calibrated constant (e.g., "warn if >2ms/doc") that has no empirical baseline today — adding the ratio would bake in an unverified assumption.

INFO-only preserves the raw signal for operators without fabricating a wrong alarm policy. The cycle-28 requirements doc and threat model both explicitly anchor on the cycle-26 symmetric pattern (INFO + WARNING) for sqlite-vec, and explicitly do NOT extend it to BM25 — R1 and R2 both confirm this is correct. A future cycle 29+ can introduce a calibrated threshold once operator telemetry from real large KBs lands, but cycle 28 is the wrong place to speculate.

**DECIDE.** No threshold. INFO-only for `BM25Index.__init__`.

**RATIONALE.** Corpus-size variance defeats any single threshold; calibration requires telemetry we do not yet have; scope-creep risk to "close HIGH-Deferred (b)" cycle boundary.

**CONFIDENCE.** HIGH.

---

## Q2 — Counter exact vs approximate for BM25?

**OPTIONS.** (a) Lock-free (cycle-25 precedent). (b) New dedicated `threading.Lock`. (c) Piggy-back on the cache lock (hold it across construction).

### Analysis

`BM25Index.__init__` runs OUTSIDE any caller-side lock at both construction sites — `engine.py:110` (wiki-side cache) and `engine.py:794` (raw-side cache) release `_WIKI_BM25_CACHE_LOCK` / `_RAW_BM25_CACHE_LOCK` before constructing, then reacquire for the double-check-and-store step. Option (c) would mean holding the cache lock across the (potentially expensive) construction, which would serialize all concurrent BM25 misses on the same lock — that is a material performance regression for diagnostic observability, an unacceptable trade. Option (b) adds a NEW lock exclusively for a counter; the lock cost exceeds the counter cost, and the counter's purpose is diagnostic not billing.

Lock-free matches the cycle-25 `_dim_mismatches_seen` precedent precisely: query-hot-path, under-count bounded by ≤N under N concurrent events, intentional asymmetry documented in the getter docstring. R2 Codex findings 2 and 9 stress that the resulting counter semantics are "constructor executions, approximate under concurrency" — NOT "cache-rebuild count" — and that must be captured in the getter docstring so future test writers do not mis-specify.

**DECIDE.** Lock-free. No new lock.

**RATIONALE.** Cycle-25 precedent applies exactly; adding a lock for a diagnostic counter is unjustified; holding the cache lock across construction is a real perf regression.

**CONFIDENCE.** HIGH.

---

## Q3 — INFO log severity for extension-load failure path?

**OPTIONS.** (a) No INFO on failure path; existing WARNING unchanged (brainstorm bias). (b) DEBUG on failure to capture attempted-load latency.

### Analysis

The failure path already emits a WARNING with the exception message at the catch site in `_ensure_conn`. Adding a DEBUG log with elapsed time on failure is noise without diagnostic value — an operator who sees the WARNING already has the exception class and message that identifies the failure mode, and the elapsed time before failure is rarely actionable (a fast-failing ImportError looks like a slow-failing DLL-load only in pathological cases which a WARN message text distinguishes anyway).

More importantly, adding an INFO/DEBUG log on the failure path creates a subtle correctness hazard: if a future maintainer refactors the perf-bracket into a `try/finally:` the success INFO fires on failure paths and the counter increments on failure too. R1 Opus specifically calls out this "finally-block regression" class; R2 Codex independently flags it as "the main correctness/security-adjacent footgun". The cleanest defense is the explicit structural invariant: success log + counter fire ONLY after the full success path completes, NEVER in `finally`.

**DECIDE.** No log on failure path. Existing WARNING stays.

**RATIONALE.** No diagnostic value added; structural defense against finally-block regression.

**CONFIDENCE.** HIGH.

---

## Q4 — Per-instance vs module-level counters?

**OPTIONS.** (a) Module-level (cycle-25/26 precedent). (b) Per-instance attribute on `VectorIndex` / `BM25Index`.

### Analysis

Module-level counters answer the operator question "how many cold-loads occurred in this process?" which is the first-query observability signal. Per-instance counters answer "did THIS VectorIndex cold-load?" which is not useful — an operator who has a handle to the instance can just log elapsed directly. The MCP / CLI surface does not expose instances, so per-instance counters would be orphaned.

The one genuine risk of module-level is importlib.reload poisoning (threat T3/T8). Cycle-20 L1 already established the mitigation: test-side monotonic-delta pattern (`baseline = get_X(); ... assert after == baseline + N`) survives reload because both snapshots come from the same reloaded module state. Cycle-25 AC4 and cycle-26 AC5 validated this in production; AC6 test discipline (explicitly documented in test file docstring) inherits it.

**DECIDE.** Module-level.

**RATIONALE.** Process-level observability contract; reload-leak mitigated by delta-pattern test discipline.

**CONFIDENCE.** HIGH.

---

## Q5 — Cycle-28 scope-out from peer scan (6 candidates)?

**OPTIONS.** (a) Include none; stay narrow (brainstorm bias). (b) Include a subset (e.g., `rebuild_vector_index` total-duration).

### Analysis

The threat model §Same-class peer candidates enumerates 6 adjacent observability gaps: rebuild duration, encode per-batch, end-to-end query latency, tokenize cost, eviction close latency, HF cache-hit discrimination. Each is legitimate future work, and each has its own design trade (lock-free vs locked, INFO-only vs WARN, per-instance vs module-level). Bundling any of them with cycle 28's "close HIGH-Deferred (b)" mandate violates the batch-by-file convention (one cycle = one narrow theme) and exceeds the requirements non-goal list.

The most seductive candidate is `rebuild_vector_index` total-duration because it sits adjacent to cycle-26's cold-load and has identical pattern shape. But "adjacent and easy" is not "in scope". The cycle-22 L5 lesson — CONDITIONS must be load-bearing, not footnotes — applies symmetrically: scope additions must be load-bearing for the cycle theme, not convenient bundles. All six peers get BACKLOG-tag deferrals to the observability-stack phase; they will resurface when Phase 6 lands.

**DECIDE.** Include none. All 6 deferred to backlog under their named tags.

**RATIONALE.** Batch-by-file scope discipline; each peer merits its own cycle; deferral tags preserve discoverability.

**CONFIDENCE.** HIGH.

---

## Q6 — Test file location?

**OPTIONS.** (a) New file `tests/test_cycle28_first_query_observability.py`. (b) Extend `tests/test_cycle26_cold_load_observability.py`.

### Analysis

The cycle-per-file test convention has been stable since cycle 17 (cycle-25 = 3 new files, cycle-26 = 1, cycle-27 = 1). Each cycle's decision doc points to its matching test file, which makes both post-hoc archaeology and pre-merge review cleaner. Extending cycle-26's file would muddle the commit-scope narrative (a cycle-28 commit touching a cycle-26-named file looks like a regression patch, not a new feature).

A counter-argument for (b) is "co-locate similar observability tests" for discoverability. But the decision-doc chain + `grep -l cycle28 tests/` already makes discoverability trivial. The cycle-27 AC6 pattern (new file per cycle) has no observed downsides.

**DECIDE.** New file `tests/test_cycle28_first_query_observability.py`.

**RATIONALE.** Cycle-per-file convention; commit-scope clarity; no discoverability loss.

**CONFIDENCE.** HIGH.

---

## Q7 — Path redaction for INFO logs?

**OPTIONS.** (a) No redaction, parity with existing (brainstorm bias). (b) Redact `db_path` to `<path_hidden>`.

### Analysis

Cycle-20 L3 explicitly scoped `<path_hidden>` redaction to `StorageError.__str__` — ERROR-boundary exceptions that may propagate to log aggregators and structured error stores. INFO logs at `embeddings.py:138`, `:309`, and cycle-26's `:368` all log operator-configured paths unredacted; breaking parity in cycle 28 alone would create a confusing half-redacted log surface without actually solving the multi-tenant-aggregator concern (which requires the OTHER existing INFO sites to ALSO be redacted to be meaningful).

A blanket INFO-log redaction policy is legitimate future work (tagged `§Phase 6 — structured logging with path redaction`), but must land as a coherent policy across all INFO sites, not piecemeal. R2 Codex finding on logfmt-style convention reinforces this: the `(db=%s)` parenthetical tail format is the established local convention, and reversing it cycle-by-cycle is worse than keeping it consistent and solving structured logging properly later.

**DECIDE.** No redaction. Parity with existing `embeddings.py:138/:309/:368` INFO sites.

**RATIONALE.** Cycle-20 L3 scoping; parity with siblings; blanket policy belongs in future dedicated cycle.

**CONFIDENCE.** HIGH.

---

## Q8 — Test-fixture concurrency on `_ensure_conn` counter?

**OPTIONS.** (a) Document "exact per-instance, approximate across-instances" (brainstorm bias). (b) Add counter-level lock.

### Analysis

Each `VectorIndex` instance serializes its own `_ensure_conn` through `_conn_lock`, so inside the lock the counter `+= 1` is exact-per-instance. Across instances, the interleaving is not coordinated — two VectorIndex instances cold-loading concurrently could race on the counter line, undercounting by at most 1. This is the same semantics as cycle-25 `_dim_mismatches_seen` and is explicitly tolerated by the "diagnostic only, not billing-grade" contract.

Option (b) would require a MODULE-LEVEL lock wrapping just the increment — feasible but unnecessary since the operator-visible consequence is "counter may read N-1 instead of N under rare concurrent cold-loads", which does not affect the diagnostic signal. The cost is another lock to audit. R2 Codex finding 8 confirms xdist workers are per-process, so the cross-worker concern does not apply. Documenting the semantics in the getter docstring is both sufficient and aligned with cycle-25/26 precedent.

**DECIDE.** Document in getter docstring. No counter-level lock.

**RATIONALE.** Piggy-backs existing `_conn_lock` for exact-per-instance; cross-instance undercount bounded and tolerable; matches cycle-25 precedent.

**CONFIDENCE.** HIGH.

---

## Q9 (R2) — One BM25 counter vs separate wiki/raw counters?

**OPTIONS.** (a) One counter aggregating both call sites. (b) Separate `_bm25_wiki_builds_seen` + `_bm25_raw_builds_seen`.

### Analysis

The cycle-28 operator question is "how many BM25 indices did this process build?" — a first-query observability signal. That answer is satisfied by a single counter. The refined question "which cache family was expensive?" is legitimate but cycle-4's decision to split `_WIKI_BM25_CACHE` and `_RAW_BM25_CACHE` was about cache-semantics isolation, not about observability attribution. Binding observability to the cache split prematurely would couple the two concerns and inflate cycle-28 scope.

R2 finding 9 flags this as "slightly muddies first-query diagnosis when wiki and raw searches coexist" — true, but the mitigation is documentation, not an extra counter. The getter docstring must explicitly state "aggregates both wiki-page and raw-source BM25 constructions" so future test writers or dashboard builders do not assume per-family attribution. If operator feedback shows the aggregate is insufficient, a cycle 29+ follow-up can split the counter — the public getter signature stays backward-compatible by keeping `get_bm25_build_count()` as sum-of-both.

**DECIDE.** One counter. Docstring explicitly aggregates both sites.

**RATIONALE.** First-query observability scope; coupling observability to cache semantics is premature; docstring makes aggregation explicit.

**CONFIDENCE.** HIGH.

---

## Q10 (R2) — Failure-path divergence test for `_ensure_conn`?

**OPTIONS.** (a) Add 8th test `test_sqlite_vec_load_no_info_on_failure_path` (R1 + R2 bias). (b) Trust AC1's prose-only failure-path statement.

### Analysis

Both R1 Opus and R2 Codex independently identified the same risk: a future maintainer refactors the perf-bracket into `try/finally:` and the success INFO + counter fire on failure paths, silently breaking the observability contract. AC1 prose states "On the FAILURE path, NO perf log fires" — but prose is not a test. The cycle-26 AC5 test 7 pattern (post-success ordering test for `_get_model`) is the established defense: a test that explicitly exercises the failure path and asserts no success-INFO record appears.

This upgrades AC6 from 7 tests to 8 tests, raising the post-cycle-28 suite count from 2808 to 2809. The CLAUDE.md test-count bump must reflect this. The test name `test_sqlite_vec_load_no_info_on_failure_path` matches the cycle-26 naming style.

**DECIDE.** Add 8th test. Suite count 2808 → 2809.

**RATIONALE.** R1 + R2 converge on a real regression class that cycle-26 faced; prose-only AC is insufficient; cycle-26 test-7 precedent exactly applicable.

**CONFIDENCE.** HIGH.

---

## Q11 (R2) — BM25 getter docstring says "constructor executions, not distinct cache insertions"?

**OPTIONS.** (a) Explicit docstring stating "constructor executions" (R2 bias). (b) Generic docstring.

### Analysis

R2 finding 9 and finding 2 both center on the cache-rebuild-count vs constructor-count ambiguity. Two concurrent cache misses both construct their own `BM25Index`; the cache double-check-and-store discards the loser. A naive test writer who reads "BM25 build count" might assume it equals "number of distinct cache insertions" and write an assertion that passes only because the race is rarely observed. An explicit docstring pre-empts this class of test mis-specification.

The docstring must also cross-reference the cycle-25 Q8 lock-free rationale and the cycle-26 AC4 locked contrast — R1 condition 3 (AC3 docstring) inherits the same requirement. Docstring content is cheap to land and provides permanent guardrail for future maintainers. Zero downside.

**DECIDE.** Explicit docstring: "constructor executions, aggregate over wiki-side and raw-side call sites, approximate under concurrency".

**RATIONALE.** Pre-empts test mis-specification class; cheap; aligns with cycle-25/26 docstring precedent.

**CONFIDENCE.** HIGH.

---

## Verdict

**APPROVE-WITH-CONDITIONS.**

Both R1 and R2 approved with conditions; all 11 questions resolve to the brainstorm biases or to R1/R2 additions; all resolutions are low blast-radius, opt-in, and reversible.

## Decisions (one-line summary)

- **Q1** — No BM25 WARN threshold; INFO-only.
- **Q2** — Lock-free `_bm25_builds_seen`.
- **Q3** — No failure-path log; existing WARNING stays.
- **Q4** — Module-level counters (both).
- **Q5** — Include none of the 6 peer candidates; all deferred to backlog.
- **Q6** — New test file `tests/test_cycle28_first_query_observability.py`.
- **Q7** — No `db_path` redaction; parity with existing INFO sites.
- **Q8** — Document counter semantics in getter docstring; no new lock.
- **Q9** — One aggregate BM25 counter; docstring names both call sites.
- **Q10** — Add 8th test (failure-path divergence); suite count 2808 → 2809.
- **Q11** — BM25 getter docstring says "constructor executions, not distinct cache insertions".

## Conditions (Step 9 must satisfy)

Each condition maps to a Step-9 test assertion OR a Step-11 grep check. NOT footnotes (cycle-22 L5).

**C1 (AC1 bracket scope).** Step 9 brackets the FULL extension-load block in `_ensure_conn` (from `sqlite3.connect(self.db_path)` through `enable_load_extension(False)` inclusive), not only the `sqlite_vec.load(conn)` call. Step-9 verification: Read `src/kb/query/embeddings.py:461-491` after edit — `start = time.perf_counter()` must appear BEFORE `sqlite3.connect`; `elapsed = time.perf_counter() - start` must appear AFTER `enable_load_extension(False)` and BEFORE `self._conn = conn`.

**C2 (AC4 bracket scope).** Step 9 brackets the FULL `BM25Index.__init__` body (corpus loop + avgdl + IDF pre-computation), not only the corpus loop at line 78-84. Step-9 verification: Read `src/kb/query/bm25.py` after edit — `start = time.perf_counter()` must appear at top of `__init__` body AFTER `self.n_docs = len(documents)` assignment; `elapsed = time.perf_counter() - start` must appear AFTER the IDF pre-computation and BEFORE the `logger.info` call.

**C3 (AC6 expansion to 8 tests).** Step 9 writes 8 regression tests in `tests/test_cycle28_first_query_observability.py`, adding `test_sqlite_vec_load_no_info_on_failure_path` as test #8. This test monkeypatches `sqlite_vec.load` to raise ImportError, calls `_ensure_conn`, asserts no INFO record matches `"sqlite-vec extension loaded in"` in caplog AND asserts `get_sqlite_vec_load_count()` delta is 0. Test-count bump: CLAUDE.md 2801 → 2809 (not 2808).

**C4 (post-success ordering invariant).** Step 9 places the INFO log + WARNING (if above threshold) + counter increment AFTER `self._conn = conn` assignment in `_ensure_conn`. These three MUST NOT be inside any `finally:` block. Step-11 grep: `grep -n "finally" src/kb/query/embeddings.py` must not show a new finally-block wrapping the perf log or counter increment.

**C5 (single-site counter increments).** Step-11 grep: `grep -n "_sqlite_vec_loads_seen\s*+=" src/kb/query/embeddings.py` returns exactly ONE match (inside `_ensure_conn`, inside `_conn_lock` span). `grep -n "_bm25_builds_seen\s*+=" src/kb/query/bm25.py` returns exactly ONE match (at end of `BM25Index.__init__`, lock-free).

**C6 (monotonic-delta test pattern).** Step-11 grep: every call-site of `get_sqlite_vec_load_count()` and `get_bm25_build_count()` in `tests/test_cycle28_first_query_observability.py` must be paired with a `baseline = ` or `before = ` snapshot preceding the action under test. `grep -B2 "get_sqlite_vec_load_count\|get_bm25_build_count" tests/test_cycle28_first_query_observability.py` must show every call-site has a preceding snapshot; no absolute-equality assertions (e.g., `assert get_X() == 1`).

**C7 (monkeypatch discipline).** Step-11 grep: `grep -n "time.perf_counter\s*=" tests/test_cycle28_first_query_observability.py` returns zero raw assignments. Patches use `monkeypatch.setattr("kb.query.embeddings.time.perf_counter", fake)` or equivalent module-scoped target, never raw `time.perf_counter = fake` and never global-scope unqualified patching.

**C8 (getter docstring content).** Step 9 writes getter docstrings that explicitly name-check precedents:
- `get_sqlite_vec_load_count()` docstring states: "exact per-instance (inside `_conn_lock`), approximate across concurrent VectorIndex instances. Companion to cycle-25 `_dim_mismatches_seen` (lock-free) and cycle-26 `_vector_model_cold_loads_seen` (locked via `_model_lock`)."
- `get_bm25_build_count()` docstring states: "constructor executions, NOT distinct cache insertions; aggregates wiki-side (`engine.py:110`) and raw-side (`engine.py:794`) call sites; approximate under concurrency. Lock-free per cycle-25 Q8 precedent; contrast cycle-26 AC4 locked counter."

**C9 (no finally-block wrapping).** Step-9 code review: the perf-counter + log + counter triple MUST NOT live in a `try/finally:` structure. The natural placement is a simple linear sequence inside the success path.

**C10 (no MCP/CLI exposure).** Step-11 grep: `grep -rn "get_sqlite_vec_load_count\|get_bm25_build_count" src/kb/mcp/` returns zero matches. `grep -rn "get_sqlite_vec_load_count\|get_bm25_build_count" src/kb/cli.py` returns zero matches. Counters stay diagnostic-only library surface per cycle-26 Q14.

**C11 (no new boot-lean imports).** Step-11 grep: `grep -n "kb.query.embeddings\|kb.query.bm25" src/kb/mcp/__init__.py` returns the SAME match count as pre-cycle-28 baseline. No new module-scope imports of `embeddings` or `bm25` added to `kb.mcp.__init__`. `import time` added ONLY to `embeddings.py` / `bm25.py` bodies (function-local matching cycle-26 style OR module-level — either is safe since `time` is stdlib).

**C12 (CVE re-verify no-op path).** Step 11 re-runs `pip-audit --format=json` against installed venv (drop `-r requirements.txt` per cycle-22 L1). If advisory set is identical to cycle-26 baseline (2 CVEs, both `fix_versions=[]`), CHANGELOG Quick Reference includes literal string `"no-op CVE re-verify, matches cycle-26 baseline"`. Any new advisory routes to Step 11 Class B / Step 11.5 Class A per cycle-22 L4 four-gate model.

**C13 (BACKLOG.md three edits land cleanly).** Step 9 produces `git diff BACKLOG.md` showing exactly three mutations: (a) HIGH-Deferred vector-index-lifecycle entry narrowed to remove sub-item (b), prose references cycle 28 AC1-AC5; (b) MEDIUM `_post_ingest_quality AC17-drop` line DELETED; (c) LOW `CHANGELOG.md cycle-27 commit tally` line DELETED. Step-11 grep: `grep -c "AC17-drop" BACKLOG.md` returns 0; `grep -c "cycle-27 quick-reference commit tally" BACKLOG.md` returns 0.

**C14 (CHANGELOG format-guide one-liner).** Step 9 adds exactly one HTML-comment line inside the existing entry-rule comment block (CHANGELOG.md lines 10-17 area) codifying the commit-count self-referential rule. Step-11 grep: `grep -n "self-referential" CHANGELOG.md` returns exactly one new match inside the format-guide comment block.

## Final Decided Design

Approach A (precedent-mirror), narrow scope, 8-test regression file, with the following concrete decisions folded in:

1. **`VectorIndex._ensure_conn` (sqlite-vec extension load):**
   - Add `import time` (function-local or module-level, match cycle-26 style).
   - Add module constant `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS: float = 0.3`.
   - Add module counter `_sqlite_vec_loads_seen: int = 0`.
   - Bracket the FULL extension-load block (connect → load → enable_load_extension(False)) with `time.perf_counter()` inside the existing `_conn_lock` span.
   - On success (AFTER `self._conn = conn`): increment counter, emit INFO, conditionally emit WARNING if elapsed >= threshold.
   - On failure: NO new log; existing WARNING unchanged; counter not incremented.
   - Export `get_sqlite_vec_load_count() -> int` with docstring per C8.

2. **`BM25Index.__init__` (corpus indexing):**
   - Add `import time` at module header.
   - Add module counter `_bm25_builds_seen: int = 0` (lock-free).
   - Bracket the FULL `__init__` body (after `self.n_docs = len(documents)` through IDF pre-computation).
   - Before return: increment counter, emit INFO unconditionally (including `n_docs=0` empty-corpus case).
   - NO WARNING threshold for BM25.
   - Export `get_bm25_build_count() -> int` with docstring per C8.

3. **Tests:** `tests/test_cycle28_first_query_observability.py` (new file, 8 tests). Tests 1-5 + new test 8 cover `_ensure_conn`. Tests 6-7 cover `BM25Index`. All use `monkeypatch.setattr` fixture-based patching; all counter assertions use monotonic-delta pattern (baseline + delta, never absolute equality); test file docstring documents the reload-defense rationale (cycle-20 L1).

4. **BACKLOG / CHANGELOG / CVE:**
   - BACKLOG.md three edits per C13.
   - CHANGELOG.md entry-rule comment block gets one new line per C14.
   - CLAUDE.md test count 2801 → 2809 (+8 not +7 per C3/Q10).
   - CVE re-verify is no-op per C12 if baseline matches cycle-26.

5. **Scope-outs** (all tagged for backlog, per threat model §Deferred-to-BACKLOG tags):
   - Env-override for thresholds → `§Phase 4.5 — env-override for observability thresholds`.
   - Prometheus/OTEL export of counters → `§Phase 6 — observability stack`.
   - `rebuild_vector_index` duration + `model.encode` latency + end-to-end query latency → `§Phase 6 — end-to-end query tracing`.
   - INFO-log path redaction policy → `§Phase 6 — structured logging with path redaction`.
   - Warm-load hook for sqlite-vec / BM25 → deferred pending observability data.
   - Per-cache-family BM25 counter split → deferred pending operator feedback.

## ESCALATE

(empty — all 11 questions resolved)
