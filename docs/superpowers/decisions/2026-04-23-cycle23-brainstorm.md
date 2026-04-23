# Cycle 23 — Brainstorm

## AC4 — MCP lazy shim

| Option | Viability |
|---|---|
| **PEP 562 `__getattr__`** (cycle-8 proven) | Preserves `kb.mcp.core.ingest_pipeline` module-attribute reachability needed by cycle-19 AC15 test (`monkeypatch.setattr(mcp_core.ingest_pipeline, ...)`). Deferred import happens on first attribute access. |
| Function-body `import kb.X` in each tool | **Breaks cycle-19 AC15 contract.** `kb.mcp.core.ingest_pipeline` no longer a module attribute. Rejected. |
| `__init__.py`-level shim | Doesn't help — `from kb.mcp import core` still loads `core.py` fully. Rejected. |

→ **PEP 562.**

## AC2 — `rebuild_indexes()` helper

| Option | Viability |
|---|---|
| Synchronous best-effort, `try/except OSError` per target, audit at end | Matches `sweep_stale_pending` pattern (refiner.py). Simple, testable. |
| Two-phase enumerate-then-delete | Overkill for 2 files (`HASH_MANIFEST`, `vector_index.db`) + LRU calls. |
| Coroutine / async | No concurrency benefit for 2 local-FS unlinks. |

→ **Synchronous best-effort + end-of-run audit write.**

## AC3 — `kb rebuild-indexes` CLI

| Option | Viability |
|---|---|
| `click.confirm` on TTY + `--yes` flag for scripts | Conventional; matches cycle-20 `kb refine-sweep` affordance. |
| Separate `--dry-run` | Over-engineered given 2-file scope. |

→ **`--yes` flag + `click.confirm` (abort on no).**

## AC6 — hermetic E2E test

| Option | Viability |
|---|---|
| `tmp_project` + `extraction=dict` (skip ingest LLM) + `monkeypatch` on `kb.query.engine.call_llm` (stub synthesis) + real `run_all_checks` | Matches BACKLOG LOW-LEVERAGE §test_e2e_demo_pipeline spec (line 330). |
| VCR / cassette-based | Dep-heavy; no real API calls to record anyway. |

→ **Monkeypatch synthesis `call_llm`; real ingest + query + lint.**

## AC7 — multiprocessing file_lock test

| Option | Viability |
|---|---|
| `multiprocessing.Process` with top-level worker fn + sentinel file + `timeout=0.5` acquire | Picklable across `spawn` / `fork`; clean Windows story. |
| `subprocess.Popen([sys.executable, "-c", ...])` | Workable but awkward — must serialise test code as string. |
| `concurrent.futures.ProcessPoolExecutor` | Same as option 1 but with more abstraction. |

→ **`multiprocessing.Process` + top-level worker.**

All approaches chosen. Proceeding to Step 4.
