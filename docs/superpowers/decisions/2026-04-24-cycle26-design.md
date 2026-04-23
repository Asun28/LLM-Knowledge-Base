# Cycle 26 — Step 5 Design Gate Decision

**Date:** 2026-04-24
**Gatekeeper:** Opus 4.7 (1M)
**Branch:** `feat/backlog-by-file-cycle26`
**Inputs:** requirements (8 ACs + Q1-Q8), threat model (T1-T6), brainstorm (A1/T1/C1/B1/N1), R1 Opus symbol-verify, R2 Codex edge-case review.

---

## VERDICT

**AMEND-AND-PROCEED.**

Requirements + threat model + brainstorm form an internally consistent KISS observability cycle. R1 Opus found 4 blocking gaps (boot-lean allowlist, 2 missing tests, post-success ordering, same-day CVE re-stamp noise). R2 Codex independently confirmed 2 of the 4 (caplog.set_level, BACKLOG evidence grep mismatch) and added the counter-asymmetry docstring ask. All amendments are reversible, internal, opt-in, and small — no AC is REJECT, no design principle breaks. Proceed to Step 2 with the amendments folded in; Step 9 must satisfy the CONDITIONS list.

---

## DECISIONS (Q1-Q16 one-line verdicts)

| Q | Decision | Confidence |
|---|----------|------------|
| Q1 | Daemon-only. No cancel API. | high |
| Q2 | `logger.exception` inside warm-load wrapper. Swallow (thread dies; next query re-attempts). | high |
| Q3 | INFO always + WARN on threshold breach. | high |
| Q4 | Exact count inside `_model_lock` critical section. | high |
| Q5 | Threshold = `0.3` (seconds). Module-level constant, no env override this cycle. | high |
| Q6 | Swallow `Thread.start()` `RuntimeError` with `logger.warning` in `main()`. | high |
| Q7 | Test uses a deterministic 0.5s monkeypatched sleep; 67% margin over 0.3s threshold is adequate on slow CI. | high |
| Q8 | NO warm-load in `kb compile`. CLI is one-shot; model loads naturally inside the compile loop. | high |
| Q9 | **Extend** `tests/test_cycle23_mcp_boot_lean.py` heavy-deps allowlist to include `kb.query.embeddings` AND ship AC2 regression test. Both — this cycle. | high |
| Q10 | **Add both tests** to AC5: (a) sys.modules boot-lean probe, (b) warm-load exception-swallow. AC5 grows from 5 → 7 tests. | high |
| Q11 | INFO + WARN + counter ALL fire AFTER `_model = StaticModel.from_pretrained(...)` succeeds. NOT in `finally:`. Pinned as CONDITION. | high |
| Q12 | **Skip same-day CVE re-stamp.** Cycle 25 already ran pip-audit on 2026-04-24; re-running + re-stamping on the same day is no-op noise. AC7 narrows to "verify cycle-25 stamp is still valid; no edit unless pip-audit output diverged from cycle-25 baseline." | high |
| Q13 | **Pin `caplog.set_level(logging.INFO, logger="kb.query.embeddings")`** in test #4 (AC5.4) + analogous setup in the new boot-lean / exception-swallow tests where INFO-level is observed. | high |
| Q14 | **Reword AC6 evidence.** Grep pattern becomes `rg "ctx\.Process\|mp\.Process\|get_context" tests/test_cycle23_file_lock_multiprocessing.py` (broader — matches the actual `ctx.Process(...)` spawn idiom). Plus the existing `@pytest.mark.integration` and `import multiprocessing as mp` confirmations. | high |
| Q15 | **Formalise in AC4 body.** Add invariant: "the `_vector_model_cold_loads_seen` docstring MUST cite the cycle-25 Q8 asymmetry rationale in one line (`# cf. _dim_mismatches_seen — lock-free per cycle-25 Q8; cold-load counter piggybacks on _model_lock for exact counts`)." | high |
| Q16 | **Out of scope** for cycle 26. Keep surface narrow. Add a BACKLOG entry (new sub-item under the HIGH-Deferred `query/embeddings.py` lifecycle entry) for "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation." Scope-tight wins. | high |

---

## RATIONALES

### Q1 (daemon lifecycle)

**Analysis.** A non-daemon thread would require an explicit shutdown hook in MCP — `_mcp.run()` returns only on stdio EOF, so any non-daemon thread would block process exit. `daemon=True` inherits the process lifecycle and costs nothing. A cancel API (e.g. `threading.Event`) would force every `_get_model()` caller to check the cancel flag, which is invasive for a ~0.8s one-shot operation with no production incident history. KISS + reversible (cancel can be added later when demanded).

**Decide: daemon-only. No cancel.** Matches Q1 bias and A1 recommendation.

### Q2 (warm-load exception swallow)

**Analysis.** If `StaticModel.from_pretrained` raises (offline box, corrupted HF-Hub cache, model2vec import failure), Python's default threading behaviour prints the stack to stderr then the thread exits. The singleton stays `None` so the next user query re-attempts via `_get_model()` — that's the natural retry. But silent stderr output is easy to miss under MCP's stdio-logging convention. `logger.exception(...)` in a wrapper emits a structured log line that operators + log aggregators see. Swallowing (not re-raising) is correct because the warm-load is an optimisation — re-raising would crash the daemon thread's top-level which already happens by default.

**Decide: wrap `_get_model()` in try/except; `logger.exception("Warm-load thread failed for vec_db=%s", vec_path)`.** Matches R2 Codex finding #3 and Q2 bias.

### Q3 (log level)

**Analysis.** Single-level (INFO only) would miss the alerting trigger for slow loads. Single-level (WARN only) would obscure boot-history audits during normal operation. Emitting both is cheap — two log calls gated on a single threshold check — and gives operators the best of both.

**Decide: INFO always on cold-load success; WARN additionally above `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS = 0.3`.** Matches Q3 bias + T1 brainstorm recommendation.

### Q4 (counter locking)

**Analysis.** Two signals pull in opposite directions. Consistency with cycle-25 `_dim_mismatches_seen` (lock-free, approximate) argues for a lock-free `+= 1`. Correctness + zero marginal cost argues for exact counts inside `_model_lock`. The tiebreaker: cold-loads happen **once per process** under normal operation (low rate); dim-mismatches happen **on every query** under the failure path (high rate). The hot-path counter needs to avoid locks for performance; the cold-path counter lives inside a lock that's already held for the actual load, so the lock is free. Asymmetry is defensible — documented per Q15.

**Decide: exact count inside `_model_lock`; getter reads lock-free.** Matches Q4 bias + R2 Codex finding #5 + C1 recommendation.

### Q5 (threshold)

**Analysis.** `0.3s` matches the backlog spec ("300ms" threshold) and fires the WARN on most real cold-loads (`StaticModel.from_pretrained` clocks ~0.8s in practice per requirements doc). `1.0s` would rarely fire and defeat the observability purpose. WARN is a nudge to consider warm-load, not a pager; false positives on slow CI machines are operator-tolerable.

**Decide: `0.3`.** Matches Q5 bias.

### Q6 (`Thread.start()` `RuntimeError`)

**Analysis.** `threading.Thread().start()` can raise `RuntimeError` under resource exhaustion (rare, but real on container-constrained boxes). If `main()` propagates, MCP fails to boot — but the warm-load is an optimisation, not a correctness requirement. Swallowing + `logger.warning` preserves MCP availability while making the failure operator-visible.

**Decide: swallow `RuntimeError` in `main()` with `logger.warning("Warm-load thread failed to start: %s", exc)`.** Matches Q6 bias.

### Q7 (CI threshold stability)

**Analysis.** Test #4's monkeypatched `StaticModel.from_pretrained` uses a deterministic `time.sleep(0.5)`. 0.5s sleep against 0.3s threshold = 67% margin. A slow CI box adding 100ms to `time.sleep(0.5)` still fires the WARN; adding 100ms the OTHER way (measured elapsed = 0.4s) still fires (> 0.3s). The test is deterministic — no real model load, no HF-Hub network call.

**Decide: fine as specified.** Matches Q7 bias.

### Q8 (`kb compile` warm-load)

**Analysis.** `kb compile` is a one-shot CLI invocation. The first source it ingests triggers `_get_model()` naturally via `ingest_source` → `rebuild_vector_index`. Adding a warm-load before the compile loop shifts cost from "source 1" to "before source 1" — zero net benefit because the process will exit after the loop anyway. MCP benefits from warm-load because its lifetime is minutes-to-hours and its FIRST query pays the cost. CLI is different.

**Decide: NO.** Matches Q8 bias + non-goals line 21-22.

### Q9 (boot-lean allowlist extension) — **HIGH LEVERAGE**

**Analysis.** R1 Opus identified this as blocking. The cycle-23 AC4 boot-lean contract asserts `import kb.mcp` does NOT pull heavy deps — current allowlist at `tests/test_cycle23_mcp_boot_lean.py:58-59` is `['anthropic', 'networkx', 'sentence_transformers', 'kb.query.engine', 'kb.ingest.pipeline', 'kb.feedback.reliability']`. Critically, `kb.query.embeddings` is NOT in that list. If someone later adds `from kb.query.embeddings import maybe_warm_load_vector_model` at module scope of `kb/mcp/__init__.py` instead of function-local inside `main()`, **zero existing tests catch it**. AC2's function-local import contract is unenforceable without this extension.

Two paths: (a) extend the existing test, (b) add a new cycle-26 test. (a) is the right call — it's the same contract, just a broader set of modules. The allowlist is a single tuple literal; adding one entry is mechanical. This way cycle-26 + cycle-23 boot-lean claims share one enforcement site, which future cycles maintain.

**Decide: extend `tests/test_cycle23_mcp_boot_lean.py` heavy-deps allowlist to add `"kb.query.embeddings"`. ALSO ship AC2 regression test in `test_cycle26_cold_load_observability.py` (sys.modules probe post-import) for belt-and-suspenders.** Matches R1 Opus blocking-issue #1 and AMEND-SCOPE on AC2.

### Q10 (2 missing tests) — **HIGH LEVERAGE**

**Analysis.** R1 Opus flagged AC5 with 5 tests as under-covered. The two gaps:

(a) **sys.modules boot-lean probe.** Direct verification that `"kb.query.embeddings" not in sys.modules` after bare `import kb.mcp` — this complements Q9's allowlist extension. Allowlist catches NEW heavy-deps added to existing modules; the probe catches someone accidentally importing embeddings at the `kb.mcp.__init__` module scope.

(b) **Warm-load exception-swallow.** Monkeypatch `_get_model` to raise a known exception; spawn the warm-load thread; `.join(timeout=5)`; assert caplog captured the `logger.exception` call with the matching message. Pins Q2 decision in a test — without this test, a future refactor that removes the try/except wrapper silently passes. Codex finding #3 explicitly confirmed this retry-on-next-query behaviour depends on the wrapper.

Both tests are cheap (~10-15 LOC each); both are regressions waiting to happen without the test. AC5 grows from 5 → 7 tests minimum.

**Decide: add both tests to AC5. Rename the AC5 spec to "seven tests minimum."** Matches R1 Opus blocking-issue #2 and R2 Codex finding #3 verification ask.

### Q11 (post-success ordering invariant) — **HIGH LEVERAGE**

**Analysis.** R1 Opus identified this as an implementation trap. If the AC3 timing/log/AC4 counter live inside a `try/finally:` block around `StaticModel.from_pretrained`, then on exception:
- The timing measurement fires (elapsed is defined).
- The INFO log "Vector model cold-loaded in X.XXs" fires — but the model DID NOT load (it raised).
- The counter increments — recording a "successful cold-load" that did not happen.

This is a silent lie in the logs. The fix is trivial: put the timing start just before `from_pretrained`, and place the log + counter increment AFTER the `_model = StaticModel.from_pretrained(...)` assignment, on the success path only. On exception, no log fires, no counter increments — `_model` stays `None`, next query re-attempts (Codex finding #3 confirms). This preserves the "cold-loaded" log's truthfulness.

**Decide: CONDITION — instrumentation placed AFTER successful `_model = StaticModel.from_pretrained(...)` assignment. Never in `finally:`. Step 09 must verify via grep + read-through.** Matches R1 Opus blocking-issue #3 and R1 per-AC verdict on AC3/AC4.

### Q12 (same-day CVE re-stamp)

**Analysis.** Cycle 25 ran pip-audit on 2026-04-24 and stamped the diskcache + ragas BACKLOG entries with "Re-checked 2026-04-24 per cycle-25 AC9." Cycle 26 is also 2026-04-24. Running pip-audit again on the same day against the same installed venv should return identical output. Re-stamping produces `"Re-checked 2026-04-24 per cycle-25 AC9; re-checked 2026-04-24 per cycle-26 AC7"` — verbose, noisy, offers zero operator value.

Three options: (a) skip, (b) conditional re-stamp only on diff, (c) unconditional re-stamp for cadence signal. (a) is correct — the cycle-25 stamp already claims 2026-04-24; repeating the claim doesn't strengthen it. Cadence signalling happens in CHANGELOG, not in BACKLOG inline.

**Decide: AC7 narrows to: "run pip-audit to VERIFY cycle-25 baseline still holds; if pip-audit output diverges (new fix_versions, new severity), edit the inline stamp to cite cycle-26 AC7; otherwise NO edit." This makes AC7 a conditional no-op on the common path.** Matches R1 Opus blocking-issue #4 AMEND-SCOPE option (a)+(b) hybrid.

### Q13 (caplog.set_level) — **HIGH LEVERAGE**

**Analysis.** R2 Codex verified: `src/kb/mcp/__init__.py:64-65` calls `basicConfig(level=logging.WARNING, ...)` when main() owns handler setup. Default root logger under pytest is WARNING. Asserting on INFO-level `caplog` records without `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` will silently fail — the INFO record never gets captured. The test passes with zero assertions firing, which is WORSE than a failing test (looks green, asserts nothing).

Targeted logger-scoped `set_level` (not global) is correct — avoids polluting other tests' caplog state. The test file should include a helper or setup function that all INFO-observing tests use.

**Decide: CONDITION — every AC5 test that asserts on an INFO-level log MUST call `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` inside the test body (or via a per-test setup). Pin in the AC5 spec + CONDITION list.** Matches R1 Opus AC5 verdict + R2 Codex finding #2.

### Q14 (BACKLOG evidence grep)

**Analysis.** R2 Codex pointed out that `rg "multiprocessing\.Process" tests/test_cycle23_file_lock_multiprocessing.py` returns zero matches — the test uses `ctx.Process(...)` via `multiprocessing.get_context("spawn")`. The AC6 claim that "the test exercises `multiprocessing.Process` spawn" is substantively true but the verification grep fails literally. This is trivial to fix: broaden the pattern.

Broader patterns: `ctx\.Process|mp\.Process|get_context`. All three match the actual file. R2 Codex also confirmed the `@pytest.mark.integration` marker, `import multiprocessing as mp`, and the Event handshake + PID assertion all exist — the test substantively closes the BACKLOG item. Just the grep pattern needs broadening.

**Decide: reword AC6 evidence grep to `rg "ctx\.Process\|mp\.Process\|get_context" tests/test_cycle23_file_lock_multiprocessing.py` + the existing `@pytest.mark.integration` confirmation. No change to the BACKLOG deletion itself.** Matches R2 Codex finding #4.

### Q15 (counter asymmetry docstring)

**Analysis.** T4 already flagged the asymmetry (cycle-25 lock-free vs cycle-26 locked). Mitigation in the threat model says "document the asymmetry in the `_vector_model_cold_loads_seen` docstring." R2 Codex finding #5 independently recommended the same. Formalising this in the AC4 body (rather than leaving it as a threat-model mitigation suggestion) ensures Step 09 reviewers catch it.

The docstring comment is one line. The formalisation cost is zero; the maintenance win is real (future maintainer reading `_dim_mismatches_seen` next to `_vector_model_cold_loads_seen` immediately sees the intentional asymmetry).

**Decide: CONDITION — AC4 implementation MUST include a one-line comment/docstring on `_vector_model_cold_loads_seen` citing cycle-25 Q8 asymmetry. Exact wording is not prescribed — just the rationale reference.** Matches T4 mitigation + R2 Codex finding #5.

### Q16 (scope extension to `_ensure_conn`/BM25)

**Analysis.** R2 Codex finding #6 raised this as a genuine gap — operators still can't fully distinguish "MCP slow" from "one of several cold-load sources." But cycle 26 is narrowly scoped per requirements non-goals (no IndexWriter helper, no ingest-side lock refactor, no security-enforcement surface). Adding `VectorIndex._ensure_conn` sqlite-vec extension-load instrumentation and BM25 build instrumentation would:
- Touch a different module (`kb.query.embeddings` `VectorIndex` class, not the `_get_model` top-level function).
- Require NEW thresholds + NEW counters + NEW tests.
- Double the AC count and blast radius.

Scope-tight wins. The right home for this is a NEW BACKLOG sub-item in the HIGH-Deferred `query/embeddings.py` lifecycle entry, queued for a future cycle. This preserves cycle 26's KISS profile while capturing the insight.

**Decide: out of scope for cycle 26. Add a new sub-item to the HIGH-Deferred BACKLOG entry at `query/embeddings.py` (alongside AC8's existing narrow): "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation. Deferred to a future observability cycle."** Matches R1 Opus scope-tight bias + R2 Codex finding #6 as a follow-up queue.

---

## CONDITIONS (Step 09 must satisfy)

These are load-bearing per cycle-22 L5. Step 09 MUST verify every condition before marking the cycle complete.

**CONDITION 1 — Boot-lean allowlist extended.** `tests/test_cycle23_mcp_boot_lean.py` heavy-deps allowlist includes `"kb.query.embeddings"`. Grep: `rg "kb\.query\.embeddings" tests/test_cycle23_mcp_boot_lean.py` returns a match inside the allowlist tuple/list.

**CONDITION 2 — AC5 grows to 7 tests minimum.** `tests/test_cycle26_cold_load_observability.py` contains at least these 7 test functions:
  1. `test_maybe_warm_load_returns_none_when_vec_path_missing`
  2. `test_maybe_warm_load_returns_thread_when_vec_path_exists`
  3. `test_maybe_warm_load_idempotent_when_model_already_loaded`
  4. `test_cold_load_logs_latency_info_and_warning`
  5. `test_cold_load_counter_increments_per_load`
  6. `test_bare_import_kb_mcp_does_not_load_embeddings_module` (Q10a — sys.modules probe)
  7. `test_warm_load_thread_swallows_exception_and_logs` (Q10b — exception swallow via logger.exception)

**CONDITION 3 — Post-success ordering invariant.** In `src/kb/query/embeddings.py` `_get_model`, the `logger.info("Vector model cold-loaded...")`, `logger.warning("... exceeded ...")`, and `_vector_model_cold_loads_seen += 1` statements fire AFTER the successful `_model = StaticModel.from_pretrained(...)` assignment. NOT inside a `finally:` block, NOT before the assignment. Grep: `rg -B5 "_vector_model_cold_loads_seen\s*\+=" src/kb/query/embeddings.py` shows the increment follows (not precedes) the `_model = StaticModel.from_pretrained` line within the same `with _model_lock:` / `if _model is None:` block.

**CONDITION 4 — caplog.set_level on INFO-observing tests.** Every test in `tests/test_cycle26_cold_load_observability.py` that asserts on an INFO-level log record calls `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` inside the test body. Grep: `rg "caplog\.set_level.*INFO.*kb\.query\.embeddings" tests/test_cycle26_cold_load_observability.py` returns at least 2 matches (tests #4 and #7 at minimum).

**CONDITION 5 — Counter asymmetry docstring.** `src/kb/query/embeddings.py` contains a one-line comment or docstring on `_vector_model_cold_loads_seen` that references the cycle-25 Q8 lock-free asymmetry. Grep: `rg -B2 -A2 "_vector_model_cold_loads_seen" src/kb/query/embeddings.py` shows a line matching `(cycle.?25|Q8|_dim_mismatches_seen|lock-free)` within 3 lines of the counter declaration.

**CONDITION 6 — AC7 skip-on-no-diff.** Step 09 runs `pip-audit --format=json` against the installed venv, compares output against `.data/cycle-26/alerts-baseline.json` (or equivalent cycle-25 baseline). If `fix_versions` and severity for `diskcache` + `ragas` are UNCHANGED from the baseline, no BACKLOG edit occurs (cycle-25 stamp is sufficient). If ANY field diverges, edit the inline stamp to cite cycle-26 AC7. Document the decision in the cycle-26 commit message either way ("AC7: pip-audit output matches cycle-25 baseline; no BACKLOG edit" OR "AC7: pip-audit output diverged; re-stamped diskcache/ragas per cycle-26 AC7").

**CONDITION 7 — AC6 grep pattern broadened.** AC6's evidence grep in the requirements doc + the cycle-26 CHANGELOG closure note uses the pattern `"ctx\.Process\|mp\.Process\|get_context"` (not literal `"multiprocessing\.Process"`). Plus `@pytest.mark.integration` AND `import multiprocessing as mp` confirmations. Grep: `rg "ctx\.Process\|mp\.Process\|get_context" tests/test_cycle23_file_lock_multiprocessing.py` returns matches (verified by R2 Codex).

**CONDITION 8 — Function-local import in MCP `main()`.** `src/kb/mcp/__init__.py` imports `maybe_warm_load_vector_model` ONLY inside the body of `main()`, NOT at module scope. Grep: `rg "^from kb\.query\.embeddings\|^import kb\.query\.embeddings" src/kb/mcp/__init__.py` returns zero matches (empty grep output).

**CONDITION 9 — Single production caller.** `maybe_warm_load_vector_model` is called from exactly ONE production site (`kb.mcp.__init__.main`). Grep: `rg "maybe_warm_load_vector_model" src/` returns exactly 2 lines — the definition in `src/kb/query/embeddings.py` and the call site in `src/kb/mcp/__init__.py`. (Tests may have additional callers per AC5.)

**CONDITION 10 — Warm-load wrapper catches Exception, logs via logger.exception.** The daemon thread's target is a wrapper function (not bare `_get_model`) that catches `Exception` and calls `logger.exception("Warm-load thread failed ...")`. Grep: `rg -A5 "daemon=True" src/kb/query/embeddings.py` shows a `try:` / `_get_model()` / `except Exception:` / `logger.exception` pattern inside the wrapper.

**CONDITION 11 — `Thread.start()` RuntimeError swallow in main().** `src/kb/mcp/__init__.py` `main()` wraps the `maybe_warm_load_vector_model(WIKI_DIR)` call (specifically the returned Thread's `.start()` if that's the call surface, or the function itself if it starts internally) in a try/except for `RuntimeError`, logs warning, continues to `_mcp.run()`. Grep: `rg -B2 -A5 "maybe_warm_load_vector_model" src/kb/mcp/__init__.py` shows a try/except around the call + `logger.warning` on RuntimeError.

**CONDITION 12 — AC8 BACKLOG narrow + Q16 follow-up.** `BACKLOG.md:109` HIGH-Deferred `query/embeddings.py` entry:
  - Cites cycle-26 AC1-5 for sub-item 2 (cold-load observability + warm-load hook) — per AC8.
  - Contains a NEW sub-item for "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation" — per Q16.
  - Remaining true-deferred reads: auto-rebuild via `VectorIndex` callback + concurrent-rebuild idempotency + Q16 follow-up.

**CONDITION 13 — CHANGELOG.md + CHANGELOG-history.md reflect 13 conditions + 7 ACs.** The cycle-26 entry in `CHANGELOG.md` Quick Reference cites: Items=8 ACs, Tests=7 new (+1 test-file extension), Scope=observability + hygiene, Detail=cold-load counter + warm-load thread + boot-lean extension + BACKLOG narrow. Full per-cycle detail lives in `CHANGELOG-history.md`.

---

## FINAL DECIDED DESIGN (folded ACs with amendments applied)

The 8 original ACs remain (no AC collapses, no AC renumbers) — amendments are additive invariants pinned via CONDITIONS. The following folded spec integrates all Q1-Q16 decisions:

### Cluster A — Vector-index cold-load observability (5 ACs)

**AC1 — `maybe_warm_load_vector_model(wiki_dir)` helper.** New function in `kb.query.embeddings`:

```python
def maybe_warm_load_vector_model(wiki_dir: Path) -> threading.Thread | None: ...
```

- Returns `None` when `_hybrid_available is False`.
- Returns `None` when `_vec_db_path(wiki_dir).exists() is False`.
- Returns `None` when `_model is not None` (idempotent no-op).
- Otherwise spawns `threading.Thread(daemon=True, target=_warm_load_target, args=(vec_path,))` where `_warm_load_target` is a wrapper that:
  - Calls `_get_model()`.
  - Catches `Exception` and calls `logger.exception("Warm-load thread failed for vec_db=%s", vec_path)` (Q2 + CONDITION 10).
- Logs `logger.info("Warm-loading vector model in background (vec_db=%s)", vec_path)` on thread-start.
- Returns the `Thread` object so tests can `.join()` and production can ignore it.
- **Single-spawn caveat:** the helper does NOT lock against concurrent callers; T5 acceptance rests on the single-caller production invariant (AC2). Docstring states this explicitly.

**AC2 — Wire warm-load hook into MCP startup.** Update `kb.mcp.__init__.main()` to call `maybe_warm_load_vector_model(WIKI_DIR)` AFTER `_register_all_tools()` and BEFORE `_mcp.run()`. Specifically:

- The `from kb.query.embeddings import maybe_warm_load_vector_model` import is FUNCTION-LOCAL inside `main()` (CONDITION 8).
- The call is wrapped in `try/except RuntimeError:` with `logger.warning("Warm-load thread failed to start: %s", exc)`; MCP continues to `_mcp.run()` on failure (Q6 + CONDITION 11).

**AC2b — Boot-lean allowlist extension (Q9).** Extend `tests/test_cycle23_mcp_boot_lean.py` heavy-deps allowlist to ADD `"kb.query.embeddings"` (CONDITION 1). The existing cycle-23 `test_bare_import_kb_mcp_does_not_pull_heavy_deps` test becomes the enforcement site for cycle 26's function-local-import claim.

**AC3 — Cold-load latency instrumentation.** Extend `_get_model()` to measure elapsed time of the `StaticModel.from_pretrained` call. Start timer via `time.perf_counter()` BEFORE `from_pretrained`; measure elapsed AFTER successful `_model = ...` assignment. On success:

- Always: `logger.info("Vector model cold-loaded in %.2fs", elapsed)`.
- If `elapsed >= VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS` (module-level constant = `0.3`): ALSO `logger.warning("Vector model cold-load exceeded %.2fs threshold (%.2fs actual). Consider warm-load on startup via maybe_warm_load_vector_model(wiki_dir).", VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS, elapsed)`.

**Post-success ordering invariant (Q11 + CONDITION 3):** log fires AFTER the successful assignment, NOT in `finally:`. On `from_pretrained` exception, no log fires, `_model` stays `None`, next query re-attempts (confirmed by R2 Codex finding #3).

**AC4 — Cold-load counter.** New module-level counter `_vector_model_cold_loads_seen: int = 0` + public getter `get_vector_model_cold_load_count() -> int`. Mirror of cycle-25 `get_dim_mismatch_count()` pattern.

- Incremented exactly once per successful `StaticModel.from_pretrained` return inside `_get_model()`.
- Increment is INSIDE `_model_lock` (Q4 — exact counts; lock is already held).
- Increment is AFTER the successful `_model = ...` assignment (Q11 + CONDITION 3).
- Getter reads lock-free (Q4 — stale reads are fine for diagnostic counters).
- **Docstring/comment cites cycle-25 Q8 asymmetry** (Q15 + CONDITION 5): one-line note on the counter declaration explaining "cf. `_dim_mismatches_seen` — lock-free per cycle-25 Q8; cold-load counter piggybacks on `_model_lock` for exact counts."

**AC5 — Regression test file `tests/test_cycle26_cold_load_observability.py`.** **Seven tests minimum** (Q10 expanded from 5 to 7):

1. `test_maybe_warm_load_returns_none_when_vec_path_missing`
2. `test_maybe_warm_load_returns_thread_when_vec_path_exists` (includes `.join(timeout=5)` per T3)
3. `test_maybe_warm_load_idempotent_when_model_already_loaded` (force `_model = object()`)
4. `test_cold_load_logs_latency_info_and_warning` — monkeypatch `StaticModel.from_pretrained` with a `time.sleep(0.5)` stub; includes `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` (Q13 + CONDITION 4); asserts both INFO + WARNING fire.
5. `test_cold_load_counter_increments_per_load` — counter delta equals number of `_reset_model()` + `_get_model()` cycles; test body includes `.join()` between warm-load and reset (T3).
6. **NEW (Q10a) — `test_bare_import_kb_mcp_does_not_load_embeddings_module`** — subprocess probe: `subprocess.run([sys.executable, "-c", "import kb.mcp; import sys; assert 'kb.query.embeddings' not in sys.modules"])` returns exit 0. Complements AC2b allowlist.
7. **NEW (Q10b) — `test_warm_load_thread_swallows_exception_and_logs`** — monkeypatch `_get_model` to raise `RuntimeError("simulated HF-Hub failure")`; call `maybe_warm_load_vector_model(wiki_dir)`; `.join(timeout=5)`; `caplog.set_level(logging.ERROR, logger="kb.query.embeddings")` (exception level); assert caplog has a record matching "Warm-load thread failed" with the RuntimeError text; assert MCP main-thread did NOT propagate.

### Cluster B — BACKLOG + CVE hygiene (2 ACs, both AMEND-SCOPE)

**AC6 — Delete stale multiprocessing file_lock BACKLOG entry (Q14 evidence-grep reworded).** The `tests/test_phase4_audit_concurrency.py single-process file_lock coverage` MEDIUM entry (BACKLOG.md:160-161) is RESOLVED by `tests/test_cycle23_file_lock_multiprocessing.py` (shipped cycle 23 AC7).

**Evidence (CONDITION 7):** `rg "ctx\.Process\|mp\.Process\|get_context" tests/test_cycle23_file_lock_multiprocessing.py` returns matches (the file uses `multiprocessing.get_context("spawn")` + `ctx.Process(...)`). Plus `@pytest.mark.integration` + `import multiprocessing as mp` confirmations. File exercises Event-based parent/child handshake, PID-file assertion, and the integration marker (all verified by R2 Codex).

Delete the BACKLOG entry; add brief closure note to `CHANGELOG-history.md` under cycle 26 (pointing back at cycle 23 AC7 as the actual ship).

**AC7 — CVE date-stamp re-verification, conditional (Q12 AMEND-SCOPE).** Run `pip-audit --format=json` against the installed venv. For `diskcache` (GHSA-w8v5-vhqr-4h9v) and `ragas` (GHSA-95ww-475f-pr4f), compare pip-audit output against cycle-25 baseline.

- **If output matches** cycle-25 baseline (same fix_versions, same severity): NO BACKLOG edit. The cycle-25 stamp "Re-checked 2026-04-24 per cycle-25 AC9" is sufficient (both cycles ran same day). Document in commit message: "AC7: pip-audit matches cycle-25 baseline; no edit."
- **If output diverges**: edit the inline stamp to cite cycle-26 AC7. Document divergence in commit message.

CONDITION 6 pins this. Update `CLAUDE.md` "Latest full-suite count" narrative only if test counts change. No code change (no pin bump); documentation-only.

### Cluster C — BACKLOG scope narrowing (1 AC, extended with Q16 follow-up)

**AC8 — Narrow HIGH-Deferred vector-index lifecycle entry + add Q16 follow-up.** Update BACKLOG.md:109 `query/embeddings.py` vector-index lifecycle entry to:

- Cite cycle-26 AC1-5 as the narrow-scope observability variant (sub-item 2 partial — latency visibility + warm-load hook).
- Keep remaining true-deferred: auto-rebuild via `VectorIndex` callback (sub-item 3 remainder) + dim-mismatch auto-rebuild orchestration (needs new design for concurrent-rebuild idempotency).
- **ADD NEW sub-item (Q16 follow-up — CONDITION 12):** "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation. Deferred to a future observability cycle; the requirements problem (`operators cannot distinguish 'MCP slow' from 'vector model loading'`) is partially addressed by cycle-26 `_get_model` instrumentation, but the other cold-load sources on first query remain uninstrumented."

---

## Blast radius (unchanged from requirements)

- `src/kb/query/embeddings.py` — new helper + 3 new module-level names (counter, threshold, function); instrumented `_get_model()`; warm-load target wrapper with try/except.
- `src/kb/mcp/__init__.py` — function-local import + one-line call + try/except RuntimeError in `main()`.
- `tests/test_cycle26_cold_load_observability.py` — new file, 7 tests.
- `tests/test_cycle23_mcp_boot_lean.py` — extend heavy-deps allowlist (one entry).
- `BACKLOG.md` — 1 entry deleted, 1 entry narrowed (AC8), 1 entry conditionally edited (AC7), 1 NEW sub-item added (Q16).
- `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md` — cycle 26 narrative.

**No changes to:** compile pipeline, ingest pipeline, refine flow, file_lock semantics, vector index DB schema, MCP tool registry, CLI entry points, `VectorIndex._ensure_conn`, BM25 build path (Q16 deferred).

---

## PROCEED condition

Step 2 (baseline safety scan) may begin. Step 09 implementation MUST satisfy all 13 CONDITIONS above. The 4 highest-leverage amendments (Q9, Q10, Q11, Q13) are all pinned as CONDITIONS 1, 2, 3, and 4 — any implementation that passes those four also satisfies R1 Opus's blocking-issue list.

CONFIDENCE: **high** on all 16 decisions. No escalation required — every question has at least one project-principle constraint (KISS / scope-tight / reversible / testable) resolving the choice.

---

**Word count:** ~2550 words (analysis + conditions + folded design).
