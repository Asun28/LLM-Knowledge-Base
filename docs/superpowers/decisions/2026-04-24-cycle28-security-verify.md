# Cycle 28 — Step 11 Security Verify

## Dep-CVE diff summary
- Baseline: 2 CVEs (diskcache + ragas, both fix_versions: []), identical to cycle-26 baseline
- Branch: identical to baseline
- INTRODUCED: []
- Step 11.5 skip rationale: No new Class A advisories with upstream patches; no PR-introduced CVEs

Step-11 `pip-audit --format=json` rerun: `count=2` (`diskcache 5.6.3 CVE-2025-69872 fix_versions=[]`; `ragas 0.4.3 CVE-2026-6587 fix_versions=[]`). `.data/cycle-28/cve-baseline.json` and `.data/cycle-28/cve-branch.json` both match that set.

## Threat model verification (T1-T8)
| T | Verified-at claim | Actual state | Status |
|---|---|---|---|
| T1 | Lazy `%s`, not f-string. | `src/kb/query/embeddings.py:546` uses `logger.info("... db=%s", elapsed, self.db_path)`. | IMPLEMENTED |
| T2 | No path redaction, accepted parity. | `db_path` logs unredacted at `embeddings.py:546`; `grep -rn "<path_hidden>" src/kb/query/` = NO MATCH. | IMPLEMENTED |
| T3 | Module counters + delta tests. | Counters at `embeddings.py:80`, `bm25.py:31`; delta snapshots at `tests/...:166-170`, `:286-293`. | IMPLEMENTED |
| T4 | No raw `perf_counter` poisoning. | `grep -n "time.perf_counter\s*=" tests/...` = NO MATCH; tests monkeypatch `sqlite_vec.load` at `:116`, `:206`. | IMPLEMENTED |
| T5 | WARN rate bounded by connection fast path. | Fast paths at `embeddings.py:488-499`; warning only after successful load at `:547-552`. | IMPLEMENTED |
| T6 | `n_docs` disclosure accepted. | `self.n_docs = len(documents)` at `bm25.py:111`; INFO emits `n_docs` at `:146`. | IMPLEMENTED |
| T7 | Python int no overflow. | Comments document arbitrary-precision int at `embeddings.py:79`, `bm25.py:29` and `:51`. | IMPLEMENTED |
| T8 | `importlib.reload` grep zero + delta pattern. | Delta pattern exists (`tests/...:166`, `:182`, `:209`, `:286`), but grep is not zero because docstring mentions reload at `:29`. | PARTIAL gap: grep-check false positive; no executable reload call found. |

## CONDITION verification (C1-C14)
| C | Grep command | Expected | Actual | Status |
|---|---|---|---|---|
| C1 | `grep -n "time\.perf_counter" src/kb/query/embeddings.py`; `grep -B3 "start = time\.perf_counter" ...` | Start/elapsed inside `_ensure_conn`. | Hits include `embeddings.py:507` start and `:543` elapsed; inside lock from `:494`; connect `:518`, load-disable `:523`. | PASS |
| C2 | `grep -n "time\.perf_counter" src/kb/query/bm25.py` | Exactly 2 hits in `BM25Index.__init__`. | 3 hits: docstring `bm25.py:102`, executable start `:114`, elapsed `:143`. | FAIL |
| C3 | `.venv/Scripts/python -m pytest tests/test_cycle28_first_query_observability.py --collect-only -q \| grep "collected"` | 8 items. | `8 tests collected in 0.22s`. | PASS |
| C4 | `grep -n "finally" src/kb/query/embeddings.py` | No finally wrapping perf/log/counter. | Hits at comments `:392`, `:539-540`; only code `finally` is build cleanup at `:613`, outside `_ensure_conn` instrumentation `:538-552`. | PASS |
| C5 | `grep -n "_sqlite_vec_loads_seen\s*+=" ...`; `grep -n "_bm25_builds_seen\s*+=" ...` | Exactly one each. | Exact BRE grep: NO MATCH for both. Portable equivalent hits `embeddings.py:545`, `bm25.py:145`. | FAIL |
| C6 | `grep -B2 "get_sqlite_vec_load_count\|get_bm25_build_count" tests/...` | Every read paired with baseline. | Baselines/read deltas at `tests/...:166-170`, `:182-186`, `:209-235`, `:286-293`. | PASS |
| C7 | `grep -n "time.perf_counter\s*=" tests/...` | Zero raw assignments. | NO MATCH. | PASS |
| C8 | `grep -c "cycle-25\|cycle-26" ...`; constructor/call-site greps | Counts meet thresholds. | embeddings count `10`; bm25 count `4`; `constructor executions` count `1`; `engine.py:110\|engine.py:794` count `4`. | PASS |
| C9 | `grep -n "finally" src/kb/query/embeddings.py \| wc -l` | Equals pre-cycle-28 baseline. | Current `4`; baseline `2`; increase is comment-only at `:539-540`, not new code. | FAIL |
| C10 | `grep -rn "get_sqlite_vec_load_count\|get_bm25_build_count" src/kb/mcp/`; `src/kb/cli.py` | Zero matches. | NO MATCH in both. | PASS |
| C11 | `grep -n "kb.query.embeddings\|kb.query.bm25" src/kb/mcp/__init__.py` | Same as baseline. | Current and baseline both `:69` comment + `:77` `maybe_warm_load_vector_model`; no `bm25` import. | PASS |
| C12 | pip-audit + CHANGELOG literal grep. | Same 2 CVEs; literal present. | pip-audit `count=2`; `CHANGELOG.md:56` has literal no-op CVE string. | PASS |
| C13 | BACKLOG greps for deleted/narrowed items. | Removed strings; sentinel count preserved. | `AC17-drop=0`; `cycle-27...=0`; `first-query observability` NO MATCH; `see CHANGELOG cycle=1`; committed `main...HEAD` diff is 3 content mutations + sentinel update. | PASS |
| C14 | `grep -n "self-referential" CHANGELOG.md` | Exactly one in comment block. | Two hits: `CHANGELOG.md:21` comment block and `:55` Quick Reference. | FAIL |

## Same-class peer scope-out audit
Command: `git diff --unified=0 main...HEAD -- src tests | grep -nE "^[+]([^+]|$).*?(rebuild_vector_index|model\.encode|VectorIndex\.query|tokenize\(\)|_evict_vector_index_cache_entry|HF cache|cache-hit|huggingface|_get_model)"`.

Actual: one added `_get_model` style-reference comment only (`src/kb/query/embeddings.py` diff line for cycle-26 style). No added instrumentation for `rebuild_vector_index`, `model.encode`, `VectorIndex.query`, `tokenize()`, `_evict_vector_index_cache_entry`, or HF cache discrimination. Full-diff matches for those names are documentation-only scope-out text.

## Revert-tolerance spot-checks
- `test_sqlite_vec_load_count_increments_exactly_once`: removing `_sqlite_vec_loads_seen += 1` at `embeddings.py:545` makes delta `0`, expected `1`.
- `test_sqlite_vec_load_no_info_on_failure_path`: moving the sqlite counter/log into a failure-reaching `finally` would make the failure-path delta nonzero and/or emit success INFO.
- `test_bm25_build_count_monotonic_across_instances`: removing `_bm25_builds_seen += 1` at `bm25.py:145` makes delta `0`, expected `3`.

## Overall verdict
APPROVE-WITH-PARTIAL

Security posture is acceptable: no new CVEs, no MCP/CLI exposure, counters/logs are process-local and bounded, and same-class peers stayed out of source/test scope. Partial is for mechanical verification drift: C14 is a real doc-grep mismatch, while C2/C5/C9 are grep-spec or comment-noise failures despite the source behavior being implemented.
