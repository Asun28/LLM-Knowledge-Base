# Cycle 26 — Brainstorm

**Date:** 2026-04-24
**Scope reference:** 8 ACs across 3 clusters (cold-load observability / BACKLOG hygiene / scope narrowing).

## Cluster A — Vector-index cold-load observability

### Approach A1 — Eager thread-spawning warm-load + sticky cold-load log

Spawn a daemon thread inside `maybe_warm_load_vector_model(wiki_dir)` that calls `_get_model()` directly. The thread dies when load completes. Log timing inside `_get_model()` on every `StaticModel.from_pretrained` call.

**Pros**
- Simple: 15 LOC for the helper + 5 LOC hook in `main()`.
- Daemon thread cleanup is free — no resource leak.
- Latency log is at the deepest natural point (right where the expensive call happens).

**Cons**
- Double-call idempotency requires checking `_model is None` inside the helper AND relying on the `_model_lock` double-check inside `_get_model()` — slight duplication.
- No cancel API; if the model server changes URL mid-flight the thread blocks on the old URL until `from_pretrained` timeout.

### Approach A2 — `concurrent.futures.Executor`-based warm-load

Submit a `ThreadPoolExecutor(max_workers=1)` task. Return the `Future`; callers can `.result(timeout=...)`.

**Pros**
- Slightly cleaner API; `Future` composes with other async code.
- Easier to cancel if we ever need to.

**Cons**
- Executor lifecycle: who shuts it down? If we create one per `maybe_warm_load_vector_model` call we spawn a new pool each invocation (cheap but wasteful).
- Overkill for a one-shot warm-load.

### Approach A3 — Hook into `VectorIndex.__init__` for implicit warm-load

Make every `VectorIndex` instantiation trigger the model load. No explicit `maybe_warm_load_vector_model` function.

**Pros**
- Zero caller changes — the very first query that creates a `VectorIndex` warms the model automatically.

**Cons**
- Doesn't solve the problem (cold-load still charged to first user query).
- Tangles the cache-lookup path with model-load lifecycle.

**Recommendation: A1.** KISS. The helper is explicit, testable, and matches the backlog item's spec.

---

## Cluster A sub-question — cold-load threshold behaviour

### Approach T1 — INFO always, WARN above 0.3s

Matches backlog spec ("emit progress line if user-facing latency crosses 300ms").

### Approach T2 — WARN only above threshold

Less log noise under fast loads.

### Approach T3 — Single INFO level, no threshold

Simplest. Operators grep the numeric value themselves.

**Recommendation: T1.** INFO always gives operators boot-history audit; WARN above threshold triggers alerting pipelines. Compact + follows spec.

---

## Cluster A sub-question — counter update location

### Approach C1 — Increment inside `_model_lock` (exact)

The counter lives inside the already-held double-checked lock; no extra cost, exact under concurrency.

### Approach C2 — Increment lock-free (approximate, match cycle-25 dim-mismatch counter)

Consistent with cycle-25 convention.

**Recommendation: C1.** `_model_lock` is already held once per cold-load; the `+= 1` is free. Cycle 25's lock-free approach was driven by the query hot-path (can't afford a lock per query). Cold-load is rare and already gated — take the exact count.

---

## Cluster B — BACKLOG hygiene

### Approach B1 — Inline delete + comment

Delete stale items directly; add brief CHANGELOG closure note.

### Approach B2 — Bulk sweep

Grep entire BACKLOG for potentially-stale items, verify each against src, delete in one pass.

**Recommendation: B1.** Targeted. The multiprocessing file_lock item is the only item with a known-stale flag; deleting it + re-dating two CVE entries is all cycle 26 needs.

---

## Cluster C — scope narrowing

### Approach N1 — Explicit "partially shipped, see cycle 26" footnote on the HIGH-Deferred entry

Preserves the "still deferred" status while pointing readers at what shipped.

### Approach N2 — Split the HIGH-Deferred entry into two (shipped + truly deferred)

Cleaner to read but more doc surface.

**Recommendation: N1.** Minimal diff, matches cycle-25's pattern on the same entry.

---

## Open questions for Step 5

See Q1-Q8 in `cycle26-requirements.md` under "Conditions".

The main tension is **Q2 (warm-load error swallowing)**: if `_get_model()` raises inside the daemon thread, the thread dies silently; operators only discover this when a subsequent user query triggers the SAME failure from the user's critical path. A wrapper that catches + `logger.exception` + re-logs on the critical-path failure is worth it. Simple implementation: the warm-load helper wraps `_get_model()` in `try/except Exception: logger.exception("Warm-load failed — cold-load will repeat on first query")`.

The other mild tension is **Q4 (counter threading)**: consistency with cycle-25 pulls toward lock-free; correctness + marginal cost pulls toward `_model_lock`. I lean `_model_lock` because the counter already lives inside that critical section naturally.
