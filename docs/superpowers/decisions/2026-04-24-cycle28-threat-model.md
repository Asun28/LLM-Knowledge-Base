# Cycle 28 — Threat Model

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle28`
**Scope:** AC1-AC9 in `2026-04-24-cycle28-requirements.md`. Surfaces: `VectorIndex._ensure_conn` sqlite-vec extension-load perf-bracket (embeddings.py:461-476 region), new constant `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS`, module counter `_sqlite_vec_loads_seen` + getter `get_sqlite_vec_load_count`; `BM25Index.__init__` perf-bracket (bm25.py:59-94), module counter `_bm25_builds_seen` + getter `get_bm25_build_count`; BACKLOG + CHANGELOG hygiene + CVE re-verify.

## Analysis

Cycle 28 is a narrow observability batch — two new `logger.info`/`logger.warning` sites, two new module-level `int` counters with getters, one new module-level float constant. No new HTTP endpoint, no new file write, no new user-input path, no new subprocess, no new tool registration (intentionally NOT exposed through MCP or CLI per requirements non-goal). All new code lands inside existing functions that ALREADY crossed their trust boundaries in earlier cycles (`_ensure_conn` = cycle 6 AC5 persistent sqlite conn; `BM25Index.__init__` = pre-phase-1 construction). The cycle is the direct successor to cycle-25 (dim-mismatch counter) and cycle-26 (model cold-load counter), and inherits the same threat profile modulo the intentional asymmetry in counter locking.

The `_ensure_conn` counter sits INSIDE the existing `_conn_lock` (embeddings.py:453 `with self._conn_lock:`) — exact counts are free because the lock is already held. The `BM25Index` counter is lock-FREE because `BM25Index.__init__` runs outside any caller-held lock (cache-population in `engine.py:110` + `engine.py:794` holds a DIFFERENT cache lock around cache-lookup, releasing before constructing). This matches the cycle-25 Q8 precedent for lock-free diagnostic counters — approximate counts adequate, under-count bounded by ≤N under N concurrent constructions.

Main residual concerns are log-content classification (INFO records include absolute `db_path` + `n_docs` corpus size — no new leak surface vs existing siblings), test-poisoning via `time.perf_counter` monkeypatch (standard pytest-fixture cleanup), importlib.reload interactions with module-level counters (cycle-20 L1 class; mitigated by keeping counters module-level as cycle-25/26), and the same-class peer scan (§ Same-class peer candidates below).

## Verdict

**APPROVE — proceed to Step 3 baseline safety scan.** Eight threats enumerated (T1-T8), none blocking. Cycle 28 adds no new trust boundary, no new persistent state, no new MCP/CLI surface. All residual risks are bounded and each maps to a Step-9 or Step-11 grep verification.

## Trust boundaries

```
┌─ Caller ─────────────────────────┐
│  MCP client OR kb CLI            │
└────────────┬─────────────────────┘
             │ [existing boundary — unchanged]
┌────────────▼──────────────────────────────────────────────┐
│  VectorIndex._ensure_conn   (embeddings.py:427)           │
│  ├─ Fast-path _conn is not None → return (no change)      │
│  ├─ with self._conn_lock:                                 │
│  │  ├─ sqlite3.connect(self.db_path) + sqlite_vec.load    │
│  │  │  [existing DLL-load boundary — unchanged]           │
│  │  ├─ time.perf_counter delta     ← NEW (AC1)            │
│  │  ├─ _sqlite_vec_loads_seen += 1  ← NEW (AC3 inside lock│
│  │  ├─ logger.info(%s db_path)      ← NEW (AC1)           │
│  │  └─ logger.warning if ≥threshold ← NEW (AC2)           │
│  └─ return self._conn                                     │
│                                                            │
│  BM25Index.__init__   (bm25.py:59)                        │
│  ├─ (existing corpus loop, unchanged)                     │
│  ├─ time.perf_counter delta        ← NEW (AC4)            │
│  ├─ _bm25_builds_seen += 1          ← NEW (AC5 lock-free) │
│  └─ logger.info(%d n_docs)         ← NEW (AC4)            │
└───────────────────────────────────────────────────────────┘
```

**Crossings:**
- Module → log sink (`logger.info/warning`): existing stderr/logging-handler boundary. Record payload contains `self.db_path` (Path), `elapsed` (float), `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS` (float), `self.n_docs` (int). No user-controllable content reaches format args.
- Module → counter storage: process-local `int`. No disk/network persistence. Not reachable from external callers (no MCP tool, no CLI subcommand).

**No new boundary introduced.** `self.db_path` is set at `VectorIndex(db_path)` construction (embeddings.py:404-405) which is called by `get_vector_index(vec_path)` (embeddings.py:333) and `rebuild_vector_index` (embeddings.py:279+291) — both derive `vec_path` from `_vec_db_path(wiki_dir)` (embeddings.py:159-161) which resolves under the already-validated `PROJECT_ROOT` (cycle-23 AC2 dual-anchor containment). `self.n_docs` = `len(documents)` from bm25.py:71, where `documents` is built in `engine.py:110` from `load_all_pages(wiki_dir)` — no attacker-controllable corpus-size input.

## Data classification

| Data | Classification | Leak surface |
|---|---|---|
| `self.db_path` (absolute Path) | PII-adjacent in multi-tenant aggregators | INFO log at AC1 success path |
| `elapsed` (float, seconds) | Timing-only; no secret | INFO + WARNING logs |
| `self.n_docs` (int, corpus size) | Wiki-size fingerprint (see T6) | INFO log at AC4 |
| `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS` (0.3) | Module-local constant | WARNING log only |
| `_sqlite_vec_loads_seen` / `_bm25_builds_seen` | Process-local int | NOT exposed externally; only importable in-process |

Matches cycle-26 classification precedent (embeddings.py:138 already logs `vec_path` at INFO, embeddings.py:309 already logs `vec_path` + entry count). No new persistent audit sink.

## Authn / authz

**None required.** Single-user stdio MCP / local CLI surface; both counters are diagnostic-only and NOT exposed through `kb.mcp.*` or `kb.cli`. No caller can steer the counter reads or the log content from outside the process (requirements §Blast radius confirms counters NOT in MCP/CLI tool registration, intentional per cycle-26 Q14). Specifically NOT needed:

- Rate limiting on `_ensure_conn` — per-instance `_conn_lock` + `_conn is not None` fast path already bound calls to ≤1 extension-load per VectorIndex instance lifetime.
- Input validation on `n_docs` — derived from `len(documents)` internally.
- Containment check on `db_path` — already enforced upstream at `_vec_db_path`/`rebuild_vector_index` entry.

## Logging / audit requirements

| New log site | Level | Payload | Threat refs |
|---|---|---|---|
| AC1 `_ensure_conn` success | INFO | `"sqlite-vec extension loaded in %.3fs (db=%s)"` + `elapsed` + `self.db_path` | T1 (log injection), T2 (path disclosure) |
| AC2 `_ensure_conn` threshold | WARNING | `"sqlite-vec extension load took %.3fs (threshold=%.2fs); consider warm-loading"` + `elapsed` + threshold | T5 (warn DoS) |
| AC4 `BM25Index.__init__` | INFO | `"BM25 index built in %.3fs (n_docs=%d)"` + `elapsed` + `self.n_docs` | T6 (corpus-size disclosure) |

**No new persistent audit.** `.data/hashes.json`, `wiki/log.md`, `.data/ingest_log.jsonl` not touched. No new SIEM-exportable event. Counter getters (`get_sqlite_vec_load_count`, `get_bm25_build_count`) are process-local read accessors only; not wrapped in MCP tool, not emitted through any stream.

## Dep-CVE baseline

**Baseline file:** `.data/cycle-28/cve-baseline.json` (captured 2026-04-24 on `feat/backlog-by-file-cycle28`).

**Summary:** 2 CVEs, both with empty `fix_versions`:
- `diskcache 5.6.3` — CVE-2025-69872 — `fix_versions=[]` (no upstream fix)
- `ragas 0.4.3` — CVE-2026-6587 — `fix_versions=[]` (no upstream fix)

**Comparison:** identical to cycle-25 AC9 + cycle-26 AC7 baselines. Routine no-op re-verify. AC9 explicit: CHANGELOG notes "no-op CVE re-verify, matches cycle-26 baseline" under the cycle-27 AC7 skip-on-no-diff pattern. Zero new dependencies introduced this cycle (cycle 28 adds perf-bracket + counters only — no `requirements.txt` edit).

**Late-arrival mitigation:** cycle-22 L4 four-gate model (Step 2 + Step 11 + Step 12.5 + Step 15 warn) still applies. Step 11 re-runs `pip-audit --format=json` against the installed venv (cycle-22 L1 drop `-r requirements.txt` to avoid ResolutionImpossible on Windows).

## Threats

### T1 — Log-injection through `self.db_path`

**Description:** AC1 emits `logger.info("sqlite-vec extension loaded in %.3fs (db=%s)", elapsed, self.db_path)`. `self.db_path` is a `Path` set at `VectorIndex(db_path)` construction (embeddings.py:405). Origin trace: `get_vector_index(vec_path)` (embeddings.py:313) ← `_vec_db_path(wiki_dir)` (embeddings.py:159) ← `wiki_dir` from `kb.config.WIKI_DIR` (resolved at boot under `PROJECT_ROOT`). If the project directory path contains ANSI escapes or embedded newlines, they reach the `%s` format arg verbatim.

**Likelihood:** LOW — requires write access to the filesystem path where kb is installed, or control of `KB_PROJECT_ROOT`. Windows NTFS blocks `\n` / reserved chars at `mkdir`; POSIX permits ANSI escapes in directory names but that requires already-attacker-controlled filesystem.

**Impact:** LOW — terminal-sink log spoofing at most; multi-tenant JSON log aggregators serialize escapes as string fields. No privilege change, no persistence.

**Mitigation:** inherit cycle-26 T1 precedent. Existing sibling emissions at embeddings.py:138 + embeddings.py:309 already log paths at INFO without sanitisation. The `logging` framework's lazy `%s` format is safe from `.format`-style injection. **Accept as existing-pattern parity.**

**Verified-at:** Step 9 — source grep confirms `%s` lazy format, not f-string. `grep -n "sqlite-vec extension loaded in" src/kb/query/embeddings.py` returns exactly one site using `%s` + args.

**Residual:** LOW — bounded by filesystem write access requirement.

### T2 — Information disclosure via INFO logs (absolute `db_path` in log aggregators)

**Description:** AC1 INFO record includes `self.db_path` absolute path (e.g., `D:\Projects\llm-wiki-flywheel\.data\vector_index.db`). Cycle-20 established `<path_hidden>` redaction for `StorageError.__str__` to defend against multi-tenant log aggregators scraping raw filesystem paths. Does AC1/AC4 need the same?

**Likelihood:** LOW for the single-user local personal-KB workflow. HIGH for future deployments that ship kb stderr to a multi-tenant SIEM.

**Impact:** LOW — absolute path reveals OS + install location. No credentials, no user content.

**Mitigation:** **accept existing-pattern parity**. Cycle-20 L3 decided StorageError redaction applies to EXCEPTIONS that persist to structured error stores, NOT developer-log INFO lines. Sibling INFO lines at embeddings.py:138, embeddings.py:309, compiler.py:761 all log `vec_path` unredacted. AC1 matches this precedent exactly. The AC4 `n_docs=%d` carries no path.

**Verified-at:** Step 9 — `grep -rn "<path_hidden>" src/kb/query/` returns zero (intentional per cycle-20 L3). Future Phase-6 observability-stack work may revisit this when structured-logging infra lands.

**Residual:** LOW — documented leak surface, no code change.

### T3 — Counter race under pytest concurrency / `importlib.reload` cascade

**Description:** cycle-20 L1 established that `importlib.reload(kb.config)` cascades can re-execute sibling modules. If a test under full-suite ordering calls `importlib.reload(kb.query.embeddings)`, it re-executes line 52 (`_dim_mismatches_seen: int = 0`) and line 64 (`_vector_model_cold_loads_seen: int = 0`) resetting them to 0 mid-suite. AC3 adds `_sqlite_vec_loads_seen: int = 0` at module scope; it inherits the same reload-reset behaviour. AC5 adds `_bm25_builds_seen: int = 0` in `kb.query.bm25`. A contract-test in a sibling file that asserts "counter > 0 after my test" can fail if an intervening reload in another test zeroes it.

**Likelihood:** MEDIUM under full-suite ordering; LOW under targeted test files.

**Impact:** LOW — flaky test, not production bug. Production never reloads these modules.

**Mitigation:** AC6 regression tests snapshot `get_X()` BEFORE their action and assert monotonic delta (same pattern as cycle-25 AC4 + cycle-26 AC5), NOT absolute equality. This is reload-safe. Document in AC6 test file docstring: "monotonic-delta assertions survive importlib.reload cascades per cycle-20 L1."

**Verified-at:** Step 9 — test file contains `before = get_sqlite_vec_load_count(); …; assert get_sqlite_vec_load_count() == before + 1` pattern (not `assert get_X() == 1`).

**Residual:** LOW — test-writing discipline, not code concern.

### T4 — `time.perf_counter` monkeypatch test poisoning across sibling tests

**Description:** AC6 tests monkeypatch `time.perf_counter` to synthesise deterministic elapsed values (cycle-26 AC5 style). If the monkeypatch uses `monkeypatch.setattr(time, "perf_counter", fake)` in a pytest fixture, revert is automatic at test teardown. If a test mistakenly patches the GLOBAL `time` module attribute via a raw `time.perf_counter = fake` assignment (not through the pytest fixture), the mutation persists into sibling tests.

**Likelihood:** LOW — cycle-26 established the `monkeypatch.setattr` pattern; AC6 explicitly copies it.

**Impact:** MEDIUM if exploited — a leaked fake `perf_counter` returning a constant would cause sibling tests asserting "elapsed > 0" to fail silently.

**Mitigation:** AC6 tests MUST use the pytest `monkeypatch` fixture, NOT raw module-attribute assignment. Docstring in test file: "patch via `monkeypatch.setattr('kb.query.embeddings.time.perf_counter', fake)` so revert is automatic."

**Verified-at:** Step 9 — `grep -n "time.perf_counter\s*=" tests/test_cycle28_first_query_observability.py` returns zero raw assignments. `grep -n "monkeypatch.setattr.*perf_counter" tests/test_cycle28_first_query_observability.py` returns the fixture-based patches.

**Residual:** LOW — caught by grep verification.

### T5 — WARN threshold DoS hint spam

**Description:** AC2 emits `logger.warning` on every `_ensure_conn` call where `elapsed >= 0.3`. If a test fixture creates 100 `VectorIndex` instances in a tight loop AND the machine is slow enough that each extension-load exceeds 0.3s, the log stream fills with 100 WARNING records.

**Likelihood:** LOW. Observation from requirements doc: `_ensure_conn` is called AT MOST ONCE per `VectorIndex` INSTANCE due to `_conn_lock` + cached `self._conn` fast path (embeddings.py:447-448). The warning rate is therefore bounded by the number of `VectorIndex` instances created in a process. Production creates ≤ `MAX_INDEX_CACHE_SIZE = 8` via `get_vector_index` (embeddings.py:337-339 FIFO eviction). Tests MAY create many more, but the WARNING rate remains bounded by the test-suite instance count, not by query frequency.

**Impact:** LOW — log noise, not resource exhaustion. Counter increments are cheap (int add under lock).

**Mitigation:** accept as bounded. The `_index_cache` cap (8) + FIFO eviction + per-instance `_conn_lock` fast path intrinsically bound production WARNING rate to ≤8 per process lifetime. Tests that create many instances should pass `--log-cli-level=ERROR` or use `caplog.set_level(logging.INFO)` selectively. No code change.

**Verified-at:** Step 9 — `grep -n "_conn is not None" src/kb/query/embeddings.py` returns the fast-path guard at line 447 and 457 (both inside and outside lock) confirming the rate bound.

**Residual:** LOW — bounded by cache size.

### T6 — BM25 `n_docs` disclosure of wiki-size fingerprint

**Description:** AC4 INFO log includes `n_docs=%d` which reveals the wiki corpus size (number of pages) to any observer with stderr access. For a single-user local personal-KB tool this is low-value information; an attacker who reaches stderr has already reached the filesystem where they could `ls wiki/ | wc -l` anyway.

**Likelihood:** LOW — requires stderr access.

**Impact:** LOW — corpus-size disclosure; no content leak.

**Mitigation:** **accept**. Matches cycle-26 T1 acceptance pattern for the single-user local-tool trust posture. Future multi-tenant deployment (§Phase 6 observability stack) may revisit.

**Verified-at:** Step 9 — documented in this threat model; no code change.

**Residual:** LOW — noted for future multi-tenant reassessment.

### T7 — Counter wraparound / external serialization edge case

**Description:** `get_sqlite_vec_load_count() -> int` and `get_bm25_build_count() -> int` return Python `int`. Python 3 ints are arbitrary-precision — no native overflow. If a future cycle exports these via JSON (e.g., Prometheus scrape), large values may overflow JSON spec's 2^53 safe integer boundary. At ≤8 extension-loads/process and typical ≤10^4 BM25 builds/process, this is not reachable in practice.

**Likelihood:** NEGLIGIBLE — requires >10^15 events per process lifetime.

**Impact:** NEGLIGIBLE — theoretical JSON-int-range artifact; no exploit.

**Mitigation:** none required. Document for completeness per requirements preamble.

**Verified-at:** N/A — theoretical.

**Residual:** NEGLIGIBLE.

### T8 — `importlib.reload(kb.query.embeddings)` poisoning the counters mid-suite (concrete reload-leak)

**Description:** Cycle-20 L1 showed `importlib.reload(kb.config)` cascades re-execute sibling modules including `kb.query.embeddings` when tests touch config. Each reload re-executes line 52/64/(new AC3 line) resetting counters to 0 mid-test-suite. A contract test in `tests/test_cycle25_dim_mismatch_counter.py` or `tests/test_cycle26_cold_load_observability.py` that asserted "counter grew monotonically since module import" would break under any test-ordering that triggers reload between its setup and assertion.

**Likelihood:** MEDIUM — cycle-20 L1 incident is directly relevant; AC3/AC5 add one more counter per module.

**Impact:** MEDIUM — test flakiness under full-suite ordering; non-deterministic reproduction.

**Mitigation:** AC6 regression tests MUST use monotonic-delta pattern (snapshot before, assert + delta after) — same as T3 mitigation. Additionally, cycle-28 AC6 tests should NOT call `importlib.reload` themselves. The cycle-25 AC4 getter docstring ("tests observe monotonic deltas") is normative precedent.

**Verified-at:** Step 11 — `grep -n "importlib.reload" tests/test_cycle28_first_query_observability.py` returns zero occurrences. `grep -B1 -A2 "get_sqlite_vec_load_count\|get_bm25_build_count" tests/test_cycle28_first_query_observability.py` confirms every call-site uses a before/after snapshot.

**Residual:** LOW — under AC6 test discipline.

---

## Same-class peer candidates (scope-out confirmation)

Per the cycle-11 L3 same-class peer scan discipline applied at Step 2: cycle-25 shipped `_dim_mismatches_seen` (query-hot-path, lock-free), cycle-26 shipped `_vector_model_cold_loads_seen` (model-load path, locked), cycle-28 ships `_sqlite_vec_loads_seen` + `_bm25_builds_seen`. OTHER observability gaps exist on `_get_model()`-adjacent and `_ensure_conn()`-adjacent hot paths that are INTENTIONALLY OUT OF SCOPE for cycle 28 — list surfaced here for the Step-5 design-gate to confirm the scope-out with justification:

1. **`rebuild_vector_index` total-duration latency** (embeddings.py:216) — full-corpus re-embed spans multiple seconds; currently logs only entry count at line 309. Out of scope: cycle 28 is first-query observability, not batch-rebuild.
2. **`model.encode(texts)` per-batch encode latency** (embeddings.py:289) — HuggingFace inference timing. Out of scope: hot-path in every query; high-rate counter would be cycle-25 class (lock-free), not cycle-28 class.
3. **`VectorIndex.query` end-to-end latency** (embeddings.py:580+) — the user-visible query time. Out of scope: covered by Phase 6 observability stack `(deferred to backlog: §Phase 6 — end-to-end query tracing)`.
4. **`tokenize()` call latency** (bm25.py:22) — per-document stopword + regex cost. Out of scope: microsecond-scale; counter overhead would exceed measurement.
5. **`_evict_vector_index_cache_entry` close latency** (embeddings.py:177) — `_conn.close()` duration on Windows. Out of scope: eviction is rare, `MAX_INDEX_CACHE_SIZE = 8`.
6. **`_get_model` network-fetch vs cache-hit discrimination** — cycle-26 logs the total cold-load time but does not distinguish HF cache-hit from network-fetch. Out of scope: requires HF-Hub internal hooks.

These are surfaced for the Step-5 design gate ONLY. Each one would merit its own cycle. **Cycle 28 scope stays narrow: first-query observability (sqlite-vec extension load + BM25 build) and nothing else.**

## Step-11 verification checklist

| Threat | Testable grep |
|--------|---------------|
| T1 | `grep -n "sqlite-vec extension loaded in" src/kb/query/embeddings.py` returns AC1 `%s` lazy-format, not f-string. |
| T2 | `grep -rn "<path_hidden>" src/kb/query/` returns zero (intentional per cycle-20 L3). |
| T3 | `grep -B2 -A2 "_sqlite_vec_loads_seen\s*+=\|_bm25_builds_seen\s*+=" src/` returns exactly two increment sites total, each inside its respective AC-specified scope (`_conn_lock` span for AC3; lock-free for AC5). |
| T4 | `grep -n "time.perf_counter\s*=" tests/test_cycle28_first_query_observability.py` returns zero raw assignments. |
| T5 | `grep -n "_conn is not None" src/kb/query/embeddings.py` returns fast-path guards at embeddings.py:447 and :457. |
| T6 | Documented; no grep. |
| T7 | Documented; no grep. |
| T8 | `grep -n "importlib.reload" tests/test_cycle28_first_query_observability.py` returns zero; `grep -B1 -A2 "get_sqlite_vec_load_count\|get_bm25_build_count" tests/test_cycle28_first_query_observability.py` confirms monotonic-delta pattern. |

## Deferred-to-BACKLOG tags

- Env-override for `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS` (matches cycle-26 Q4 scope-out): `(deferred to backlog: §Phase 4.5 — env-override for observability thresholds)`.
- Prometheus/OpenTelemetry export of counters (T7 finding): `(deferred to backlog: §Phase 6 — observability stack)`.
- End-to-end `VectorIndex.query` latency + `model.encode` latency + `rebuild_vector_index` duration (same-class peer candidates 1-3): `(deferred to backlog: §Phase 6 — end-to-end query tracing)`.
- Log-redaction of absolute `db_path` in INFO records (T2 finding): `(deferred to backlog: §Phase 6 — structured logging with path redaction)`.
- Warm-load hook for sqlite-vec / BM25 (requirements §Non-goals): `(deferred — observability first; warm-load later if data supports it per requirements)`.

---

**Word count:** ~1490 words.
