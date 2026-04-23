# Cycle 26 — Threat Model

**1 open alerts baseline: 0 sev=high, 0 sev=medium, 1 sev=low** (from `.data/cycle-26/alerts-baseline.json`: `ragas` GHSA-95ww-475f-pr4f, severity=low, no upstream fix; re-verified per AC7).

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle26`
**Scope:** AC1-AC8 in `2026-04-24-cycle26-requirements.md`. Surfaces: new `maybe_warm_load_vector_model` helper, `kb.mcp.__init__.main()` warm-load hook, `_get_model()` latency log + `_vector_model_cold_loads_seen` counter + `get_vector_model_cold_load_count()` getter, BACKLOG + CVE hygiene edits.

## Analysis

Cycle 26 is narrowly scoped observability — a daemon warm-load thread, three new module-level names (`_vector_model_cold_loads_seen`, `get_vector_model_cold_load_count`, `maybe_warm_load_vector_model`), a 0.3s-threshold `logger.warning`, and three BACKLOG edits. **No new trust boundary is introduced.** The warm-load thread executes inside the existing MCP server process (same UID, same container, same filesystem view as the foreground FastMCP worker threads); it consumes the SAME `WIKI_DIR` derived from `kb.config` at boot (no attacker-controllable input flows into `maybe_warm_load_vector_model`); and `_get_model()` already crossed the network boundary on cycle 3 via HuggingFace-Hub's `StaticModel.from_pretrained` cache-first fetch — the only change is now we measure how long that crossing took. The `vec_path.exists()` guard is a read-only check against the filesystem path `_vec_db_path(WIKI_DIR)` = `PROJECT_ROOT / ".data" / "vector_index.db"`, which is inside the already-validated project root per the cycle-23 AC2 dual-anchor containment pattern.

The main residual concerns are concurrency-adjacent: a warm-load thread racing with a user query (T2), the counter increment interacting with `_model_lock` (T3), and the asymmetry between this cycle's locked-counter pattern and cycle-25's lock-free dim-mismatch counter (documented — not a threat, a design inconsistency worth surfacing for future cycles). The warm-load thread's log line prints `vec_path` (which on Windows is `D:\...`) at INFO level; this matches the existing pattern at embeddings.py:236 (`logger.info("Vector index rebuilt: %s (%d entries)", vec_path, ...)`) and at compiler.py:761, so the leak surface is NOT new. Resource exhaustion via repeated `maybe_warm_load_vector_model` calls (T4) is bounded by the idempotency guards (`_model is not None` → `None` return after first successful load) — but a race between idempotency-check and thread-start under concurrent callers could theoretically spawn multiple threads before `_model` is set; the requirements doc accepts this per Q4 (double-checked-lock already serialises cold-loads so extra threads would wait on `_model_lock` and return quickly).

## Verdict

**APPROVE — proceed to Step 2 (baseline safety scan).** Six threats enumerated (T1-T6), none blocking. Cycle 26 adds no new sinks, no new authn/authz surfaces, no new persistent state. The warm-load thread inherits the MCP server's existing trust posture. Residual risks are bounded and documented.

## Trust boundary map

```
┌─ Caller ─────────────────────────┐
│  MCP client (single-user, stdio) │
└────────────┬─────────────────────┘
             │ [existing boundary — unchanged]
┌────────────▼──────────────────────────────────────────────┐
│  kb.mcp.__init__.main()  (MCP server process)             │
│  ├─ _register_all_tools()                                 │
│  ├─ maybe_warm_load_vector_model(WIKI_DIR)  ← NEW (AC2)   │
│  │  └─ threading.Thread(daemon=True, target=_get_model)   │
│  │     [runs in-process, same trust domain]               │
│  └─ _mcp.run()  (FastMCP stdio loop; spawns worker threads│
│                  that also call _get_model() on queries)  │
└────────────┬──────────────────────────────────────────────┘
             │ [existing boundary — unchanged]
┌────────────▼──────────────────────────────────────────────┐
│  _get_model()  (embeddings.py:270)                        │
│  ├─ _model_lock  (existing — cycle 3)                     │
│  ├─ StaticModel.from_pretrained(EMBEDDING_MODEL)          │
│  │  └─ HuggingFace-Hub cache → optional network fetch     │
│  │     [existing network boundary — unchanged]            │
│  ├─ time.perf_counter delta  ← NEW (AC3)                  │
│  ├─ logger.info + logger.warning (threshold)  ← NEW (AC3) │
│  └─ _vector_model_cold_loads_seen += 1  ← NEW (AC4)       │
└───────────────────────────────────────────────────────────┘
```

**Crossings:**
- Caller → module (`maybe_warm_load_vector_model`): parameter is `WIKI_DIR` from `kb.config`, NOT from MCP client input.
- Module → OS (`threading.Thread.start`): no privilege change; daemon threads inherit process UID.
- Module → disk (`_vec_db_path(wiki_dir).exists()`): read-only stat; path derived under PROJECT_ROOT.
- Module → network (transitive, `StaticModel.from_pretrained`): unchanged from cycle 3.
- Module → log sink (`logger.info/warning`): existing stderr/logging-handler boundary.

**New code in FastMCP worker thread context?** No. The warm-load runs in a dedicated daemon thread spawned by `main()` BEFORE `_mcp.run()`. FastMCP workers are spawned later by the FastMCP stdio loop; they share `_model_lock` with the warm-load thread via the module-level singleton, but execute concurrently.

## Data classification

- **`wiki_dir` paths:** absolute filesystem paths (e.g., `D:\Projects\llm-wiki-flywheel\wiki`). NOT secret, but considered PII-adjacent in multi-tenant log aggregators. This cycle emits one new INFO line containing `vec_path` — same classification as the existing `embeddings.py:236` emission. Acceptable per cycle-20 L3 (StorageError redaction applies to persistent errors, not dev-log INFO lines).
- **`_vector_model_cold_loads_seen`:** process-local Python int. No disk/network persistence. Only observable to in-process callers of `get_vector_model_cold_load_count()`.
- **Model weights (`potion-base-8M`, ~8 MB on disk, ~67 MB RSS):** public model, no secrets embedded. Cached under HuggingFace-Hub default (`~/.cache/huggingface/`).
- **PII / secrets / user content:** none touched by cycle-26 code. `_get_model()` does NOT process wiki page content in this cycle — only loads the model object.

## Authn / authz

**None required.** Single-user stdio MCP surface; the warm-load is an internal optimisation. `maybe_warm_load_vector_model` takes `WIKI_DIR` from `kb.config` (process-boot constant, not from an MCP tool argument), so no caller can steer the warm-load toward a different directory. No new enforcement surface.

Specifically NOT needed:
- Wiki-dir containment validation — `WIKI_DIR` is already dual-anchor-validated at `kb.config` boot.
- Rate limiting on `_get_model()` — existing `_model_lock` serialises.
- Permission check on the daemon-thread spawn — Python's GIL + thread inheritance model suffices.

## Logging / audit

| New log site | Level | Payload | Leak risk |
|---|---|---|---|
| `maybe_warm_load_vector_model` thread-start (AC1) | INFO | `"Warm-loading vector model in background (vec_db=%s)"` + `vec_path` | Absolute path (existing-pattern parity with embeddings.py:236) |
| `_get_model` success (AC3) | INFO | `"Vector model cold-loaded in %.2fs"` + elapsed float | Timing-only; no path leak |
| `_get_model` threshold breach (AC3) | WARNING | `"Vector model cold-load exceeded %.2fs threshold (%.2fs actual). Consider warm-load on startup via maybe_warm_load_vector_model(wiki_dir)."` | No path; remediation hint only |
| Warm-load thread error swallowing (Q2) | EXCEPTION | `logger.exception("Warm-load thread failed")` | Stack trace — may include model-cache path from HF-Hub traceback |

**No new persistent audit surface.** `.data/hashes.json`, `wiki/log.md`, `.data/ingest_log.jsonl` are not touched.

**Env-var leak surface:** none. `StaticModel.from_pretrained` reads `HF_TOKEN` / `HF_HOME` environment variables internally, but those values never reach a log line at this tier.

## Threats

### T1 — `wiki_dir` log injection via attacker-controlled project path

**Description:** `logger.info("Warm-loading vector model in background (vec_db=%s)", vec_path)` emits a filesystem path under caller control (via `KB_PROJECT_ROOT` env var or cwd walk-up detection). If the project directory path contains ANSI escape sequences (`\x1b[...m`) or embedded newlines (`\n`), they are passed verbatim to the Python `logging` framework. In a terminal sink this could spoof log entries or emit fake "INFO: ..." lines.

**Likelihood:** LOW — requires write access to the project path or `KB_PROJECT_ROOT` env var, which already implies attacker has filesystem control over the kb installation. Windows + POSIX both reject embedded newlines in directory names at `mkdir` time; ANSI escapes are permitted in directory names on POSIX but blocked on Windows NTFS by the reserved-char filter (`< > : " / \ | ? *`).

**Impact:** LOW — a local operator viewing `stderr` sees spoofed lines but no privilege escalation. Multi-tenant log aggregators consuming structured JSON (`python-json-logger`) would serialize the escape sequence as a string field, neutralising the terminal exploit.

**Mitigation:** accept the existing pattern. Cycle-4 T1 established that absolute-path leaks in MCP response strings are acceptable for a single-user local tool; the same threshold applies here. Existing sibling emissions at embeddings.py:236 (`Vector index rebuilt: %s`) and compiler.py:761 (`rebuild_indexes: audit write to %s failed`) already follow this pattern without sanitisation. No new mitigation required.

**Step-11 check:** `grep -n "vec_db=\|Warm-loading" src/kb/query/embeddings.py` returns the AC1 site and confirms the `%s` uses the logging framework's lazy-format (safe from direct `str.format` injection).

---

### T2 — Warm-load thread races a user query on `_model is None`

**Description:** `maybe_warm_load_vector_model` spawns a daemon thread that calls `_get_model()`. If an MCP client fires a query BEFORE the daemon finishes `StaticModel.from_pretrained`, the query-path `_get_model()` enters the critical section and sees `_model is None`. Existing double-checked-lock at embeddings.py:272-278 handles this correctly — the second caller blocks on `_model_lock.acquire()`, and on entering the critical section observes `_model is None` still (or NOT — depends on race) and re-checks. The actual model load happens exactly once because of the inner `if _model is None:` check.

**Likelihood:** HIGH — the race IS the intended behaviour. The warm-load starts 0-10 ms before `_mcp.run()`; a client query fired within the first second of server boot WILL hit this race.

**Impact:** NONE — the second caller blocks on `_model_lock`, waits for the first caller's `from_pretrained` return, then the second caller's `if _model is None` check fails and it returns the already-loaded `_model`. Semantically identical to the pre-cycle-26 behaviour where the query itself triggered the load; the user's query waits for the model load either way. The warm-load just shifts WHERE the wait happens (from query hot path to boot hot path).

**Mitigation:** existing double-checked-lock is correct. The cold-load counter will increment exactly ONCE under this race because the counter lives inside the `_model_lock` critical section (Q4 decision: tight lock for exact counts). AC4 contract regression test (`test_cold_load_counter_increments_per_load`) exercises this invariant.

**Step-11 check:** `grep -B2 -A2 "_vector_model_cold_loads_seen\s*+=" src/kb/query/embeddings.py` returns exactly one increment site, inside the inner `if _model is None:` block AND inside the `with _model_lock:` span.

---

### T3 — Warm-load thread holds `_model_lock` while test calls `_reset_model()`

**Description:** Tests call `_reset_model()` (embeddings.py:71) to clear the module singleton between cases. `_reset_model` acquires `_model_lock` and sets `_model = None`. If a cycle-26 test spawns `maybe_warm_load_vector_model` and then immediately calls `_reset_model()` before the warm-load thread has exited the critical section, `_reset_model` blocks waiting for the lock.

**Likelihood:** MEDIUM — only in tests that combine warm-load + reset without `.join()`. Production never calls `_reset_model()`.

**Impact:** LOW — test hang, bounded by the `from_pretrained` duration (~0.8s real-model or ~0.5s stubbed). Not a production bug. `_reset_model` eventually acquires the lock and resets, but by then the warm-load thread has ALREADY written `_model = <StaticModel>`; `_reset_model` then overwrites to `None`. The net effect: test observes `_model is None` post-reset, which is the contract. No data loss, no state corruption.

**Mitigation:** AC5 test suite should call `thread.join(timeout=5)` after `maybe_warm_load_vector_model` before any `_reset_model()` invocation. Document this in the cycle-26 test file docstring. No production code change.

**Step-11 check:** `grep -n "maybe_warm_load_vector_model\|_reset_model" tests/test_cycle26_cold_load_observability.py` — every test that calls both MUST have a `.join(timeout=` between them.

---

### T4 — Counter increment inside `_model_lock` vs cycle-25 dim-mismatch counter lock-free (asymmetry)

**Description:** Cycle-25 `_dim_mismatches_seen` is incremented WITHOUT a lock (Q8 decision: approximate under concurrency is adequate for diagnostic observation). Cycle-26 `_vector_model_cold_loads_seen` is incremented INSIDE `_model_lock` (Q4 decision: exact counts because the lock is already held). This is an intentional asymmetry but risks confusing future maintainers ("why does one counter need a lock and the other doesn't?").

**Likelihood:** LOW — code-review-time confusion, not a runtime bug.

**Impact:** LOW — no correctness issue. Dim-mismatches can occur on every query (high rate, lock-free acceptable); cold-loads occur ONCE per process per model (low rate, lock already held for unrelated reasons). Both decisions are defensible.

**Mitigation:** document the asymmetry in the `_vector_model_cold_loads_seen` docstring (pointing at cycle-25 `get_dim_mismatch_count` docstring's Q8 note for contrast). AC4 implementation should include a one-line comment: `# Cycle 26 AC4 — counter increment piggybacks on _model_lock for exact counts; cf. cycle-25 _dim_mismatches_seen which is lock-free per Q8.`

**Step-11 check:** `grep -B3 -A3 "_vector_model_cold_loads_seen" src/kb/query/embeddings.py` returns a comment or docstring referencing the asymmetry rationale.

---

### T5 — Unbounded thread spawn via repeated `maybe_warm_load_vector_model` calls

**Description:** Scenario: a caller invokes `maybe_warm_load_vector_model(WIKI_DIR)` in a tight loop (100 rapid calls). Each call checks `_model is None` and `_vec_db_path(wiki_dir).exists()`. If the first thread has NOT yet entered the `_model_lock` critical section AND `_model is None` still holds across the check, each loop iteration spawns a new daemon thread. Each thread consumes ~8 KB stack + the ~67 MB model allocation (only the first will actually allocate; the rest will block on `_model_lock` and return after the first's load).

**Likelihood:** LOW — `maybe_warm_load_vector_model` is called exactly ONCE by `main()`. The only other caller path is test code. No external MCP-client-reachable path triggers it.

**Impact:** MEDIUM if exploited — N daemon threads briefly hold ~8 KB × N stack + block on `_model_lock`. Under 100 rapid calls before the first thread completes: 100 × 8 KB = 800 KB stack, all blocked on the lock. Once the first thread returns, the remaining 99 observe `_model is not None` in the inner check and return quickly. Memory footprint recovers within ~1 second.

**Mitigation:** `maybe_warm_load_vector_model` is an internal helper; it's NOT exposed via MCP tool surface (AC2 restricts caller to `main()`). Tests should guard against spawning in a loop. For defence-in-depth, consider tightening the outer `_model is None` check to use `_model_lock` pre-spawn — but this defeats the "lean check, spawn-then-return" design. **Accept the risk** per Q6 (warm-load is an optimisation, not a correctness requirement) and Q8 (no CLI/compile caller).

**Step-11 check:** `grep -rn "maybe_warm_load_vector_model" src/` returns exactly ONE production caller (in `kb.mcp.__init__.main`). Test files may have additional callers per AC5.

---

### T6 — Warm-load thread swallows exception from `StaticModel.from_pretrained` (network / cache / import failure)

**Description:** If `StaticModel.from_pretrained` raises (offline machine, corrupt HF cache, model2vec upgrade breaking change), the daemon thread's exception propagates to the thread's top-level. Per Python's default threading behaviour, the exception prints to stderr but does NOT crash the parent process. The MCP server continues; the model stays `None`; the next user query triggers the cold-load path again and fails AGAIN. Without logging, the operator sees "first query slow + hang" with no attributable cause.

**Likelihood:** MEDIUM — offline environments, stale caches, and model2vec upgrades all trigger this.

**Impact:** LOW-MEDIUM — MCP server still boots and serves non-vector queries (BM25 fallback). Cycle-3 H17 graceful-degrade to BM25-only already handles missing `_hybrid_available`; an exception during warm-load crosses a different fault boundary (the model IS available, loading failed).

**Mitigation:** per Q2 bias, wrap the warm-load thread's target callable in a try/except that calls `logger.exception("Warm-load thread failed: %s", e)`. This makes the failure operator-visible without crashing the server. Implementation:

```python
def _warm_load_target(vec_path: Path) -> None:
    try:
        _get_model()
    except Exception as e:
        logger.exception("Warm-load thread failed for vec_db=%s: %s", vec_path, e)
```

The `logger.exception` will emit a stack trace that may include HF-Hub internal paths — acceptable per T1 rationale (dev-log, not persistent audit).

**Step-11 check:** `grep -B2 -A5 "def _warm_load_target\|daemon=True" src/kb/query/embeddings.py` returns a try/except wrapping `_get_model()` with `logger.exception` inside.

---

## Deferred-to-BACKLOG tags

- Cancel mechanism for warm-load thread (Q1): `(deferred to backlog: §Phase 4.5 — warm-load cancel API, add when production incident demands)`.
- Prometheus/OpenTelemetry export of `_vector_model_cold_loads_seen`: `(deferred to backlog: §Phase 6 — observability stack)`.
- Env-var override for `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS`: `(deferred to backlog: §Phase 4.5 — env-override for observability thresholds)`.
- `kb compile` CLI warm-load (Q8): `(deferred — scope-tight per Q8 bias)`.

## Step-11 verification checklist (condensed)

| Threat | Testable grep |
|--------|---------------|
| T1 | `grep -n "vec_db=%s\|Warm-loading vector model" src/kb/query/embeddings.py` returns the AC1 `logger.info` using lazy-format. |
| T2 | `grep -B2 -A2 "_vector_model_cold_loads_seen\s*+=" src/kb/query/embeddings.py` returns one increment inside `if _model is None:` inside `with _model_lock:`. |
| T3 | `grep -n "thread\.join\|\.join(timeout" tests/test_cycle26_cold_load_observability.py` — every test combining warm-load + reset calls `.join()` between. |
| T4 | `grep -B3 -A3 "_vector_model_cold_loads_seen\|get_vector_model_cold_load_count" src/kb/query/embeddings.py` returns a comment referencing cycle-25 Q8 asymmetry. |
| T5 | `grep -rn "maybe_warm_load_vector_model" src/` returns exactly ONE production caller at `kb.mcp.__init__.main`. |
| T6 | `grep -n "logger\.exception.*[Ww]arm-load" src/kb/query/embeddings.py` returns one exception-wrapped thread target. |

---

**Word count:** ~1260 words (analysis + threats, excluding trust-boundary ASCII diagram).
