# Backlog

<!-- FORMAT GUIDE — read before adding items
Each phase section groups items by severity, then by module area.
Resolved phases collapse to a one-liner; active phases list every item.

## Severity Levels

| Level      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| CRITICAL   | Data loss, crash with no recovery, or security exploit — blocks release |
| HIGH       | Silent wrong results, unhandled exceptions reaching users, reliability risk |
| MEDIUM     | Quality gaps, missing test coverage, misleading APIs, dead code |
| LOW        | Style, docs, naming, minor inconsistencies — fix opportunistically |

## Item Format

```
- `module/file.py` `function_or_symbol` — description of the issue
  (fix: suggested remedy if non-obvious)
```

Rules:
- Lead with the file path (relative to `src/kb/`), then the function/symbol.
- Include line numbers only when they add precision (e.g. `file.py:273`).
- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
- One bullet = one issue. Don't combine unrelated problems.
- When resolving an item, delete it (don't strikethrough). Record the fix in CHANGELOG.md.
- Move resolved phases under "## Resolved Phases" with a one-line summary.
-->

---

## Cross-reference

| File | Role | Update rule |
|------|------|-------------|
| **BACKLOG.md** ← you are here | Open work only, ranked by severity | Add on discovery; **delete** on resolve |
| [CHANGELOG.md](CHANGELOG.md) | Every shipped change, newest first (2026-04-16+) | Every merge to main |
| [CHANGELOG-history.md](CHANGELOG-history.md) | Archive: Phase 4.5 CRITICAL (2026-04-15) and older releases | Read-only after initial split; new archive entries require explicit split from CHANGELOG.md |

**Resolve lifecycle:** Delete item here → record fix in `CHANGELOG.md [Unreleased]` → done.

> **For all LLMs (Sonnet 4.6 · Opus 4.7 · Codex/GPT-5.4):** BACKLOG = open work; CHANGELOG = shipped fixes. If an item says _"see CHANGELOG"_, it is resolved and can be safely deleted from this file.

---

## Phase 4 (v0.10.0) — Post-release audit

_All items resolved — see `CHANGELOG.md` `[Unreleased]`._

---

## Phase 4.5 — Multi-agent post-v0.10.0 audit (2026-04-13)

<!-- Discovered by 5 specialist reviewers (Python, security, code-review, architecture, performance)
     running 3 sequential rounds against v0.10.0 after the Phase 4 HIGH/MEDIUM/LOW audit shipped.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2/R3). -->

### CRITICAL

_All items resolved — see CHANGELOG `[Unreleased]` Phase 4.5 cycle 1, cycle 1-docs-sync, and Backlog-by-file cycle 4._

<!-- Cycle 4 closed (2026-04-17): #1 _rel() error-string sweep, #2 <prior_turn> sentinel +
     fullwidth angle-bracket fold + control-char strip, #5 Error[partial] on post-create
     OSError in kb_ingest_content/kb_save_source, #7 kb_read_page body cap with [Truncated:]
     footer, #11 kb_affected_pages check_exists=True, #12 add_verdict per-issue cap,
     #13 _validate_page_id Windows-reserved + 255-char cap, #14 kb_detect_drift source-deleted
     category, #15 query/rewriter CJK short-query gate, #16+#18 BM25 cache-invalidation,
     #17 type-diversity quota in dedup, #18 STOPWORDS prune, #19 yaml_sanitize BOM +
     U+2028/9 strip, #20 wiki_log monthly rotation, #22 detect_contradictions_with_metadata
     caller migration, #23 export_mermaid Path-shim, #24 BM25Index postings precompute,
     #25 _template_hashes VALID_SOURCE_TYPES whitelist, #28 load_purpose(wiki_dir) required,
     #29 inject_wikilinks caller-side sorted().
     Deferred: #3 [source: X] → [[X]] citation migration (tracked as dedicated atomic migration). -->

### HIGH

- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
  (fix: rename to `pipeline/orchestrator.py` and treat `compile/` as wikilink primitives only; or collapse `compile/compiler.py` into `kb.ingest.batch`)

- `utils/llm.py` — `LLMError` is the only custom exception in the codebase; CLI (`cli.py:54,79,98,121,135`), `compile/compiler.py:349`, and MCP catch bare `Exception` and string-format. Cannot retry selectively, cannot test error paths, bugs in manifest-write are indistinguishable from LLM failures. (R1)
  (fix: `kb.errors` with `KBError` → `IngestError` / `CompileError` / `QueryError` / `ValidationError` / `StorageError`; narrow `except` at the boundary)

- `review/refiner.py` `refine_page` (~114-137) — writes page atomically, THEN appends `review_history.json`, THEN `wiki/log.md`. Crash or disk-full between steps leaves the page mutated with zero audit record, violating the documented refine-has-audit-trail guarantee; `append_wiki_log` further swallows `OSError` with a warning. (R2)
  (fix: write audit record first with `status="pending"`, write page, flip status to `"applied"`; or stage via a `page.md.pending` sidecar flipped only after log is synced)

- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes across existing pages. Every step is independently atomic, none reversible. A crash between manifest-write (step 6) and log-append (step 7) leaves the manifest claiming "already ingested" while the log shows nothing; a mid-wikilink-injection failure leaves partial retroactive backlinks. (R2)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests; retries idempotent at step granularity)

- `compile/compiler.py` `compile_wiki(incremental=False)` — "full" compile rescans and re-ingests but does NOT: clear manifest (deleted sources linger until a dedicated prune branch runs); rebuild vector index; invalidate in-process `_index_cache` in `embeddings.py`; re-validate evidence trails / contradictions / injected wikilinks. A page corrupted by a half-finished ingest stays corrupt across `--full`. (R2)
  (fix: document exactly what `--full` does and does not invalidate; add `kb rebuild-indexes` CLI that wipes manifest + vector DB + in-memory caches before a full compile)

- `graph/builder.py` no shared caching policy — cycle 6 added a query-side PageRank cache and preloaded-page threading for `kb_query`, and cycle 7 threaded page bundles through several callers, but the graph layer itself still has no reusable cache/invalidation contract. `lint/runner.py` and `lint/checks.py` can still rebuild graphs independently in one lint pass, and no policy doc defines when graph-derived caches are invalidated after ingest/refine. (R2; query hot-path portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
  (fix: `kb.graph.cache` keyed on `(wiki_dir, max_mtime_of_wiki_subdirs)`; share within lint/evolve/query call stacks; invalidate at end of `ingest_source` + `refine_page`; document in CLAUDE.md alongside the manifest contract)

- `tests/test_v0p5_purpose.py` purpose-threading coverage gap — cycle 6 added `rewrite_query` tests that mock `call_llm` and reject leaked preambles, but `test_v0p5_purpose.py` still checks only that the string "KB FOCUS" appears in the extraction prompt; it never verifies `query_wiki` threads `purpose.md` to the synthesizer. Phase 5's `kb_capture` will follow this template if not corrected. (R3; rewriter coverage portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
  (fix: add `query_wiki(..., wiki_dir=tmp)` integration test asserting purpose text reaches the synthesis prompt)

- `tests/` coverage-visibility — ~50 of 94 files are named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py`. To verify `evolve/analyzer.py` has tier-budget coverage you must grep ~50 versioned files because canonical `test_evolve.py` has only 11 tests (none touch numeric tokens, redundant scans, or three-level break — all open in Phase 4.5 MEDIUM). `_compute_pagerank_scores` is searched across 25 files. (R3)
  (fix: freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file (`test_v0917_dedup.py` → `test_query.py::class TestDedup`); enable `coverage` in CI and surface per-module % in PR comments)

- `tests/` no end-to-end ingest→query workflow — grepping for `end_to_end`, `e2e`, `workflow`, `ingest_to_query` returns only single-module tests; no test chains `ingest_source` → `build_graph` → `search` → `query_wiki` against the same `tmp_wiki`. `test_phase4_audit_query.py::test_raw_fallback_truncates_first_oversized_section` mocks `search_raw_sources`, `search_pages`, AND `call_llm` — only the glue is exercised. The Phase 4.5 items about "page write vs evidence append", "manifest race", "index-file write order", "ingest fan-out" all describe failures BETWEEN steps; pure-unit tests cannot catch them. (R3)
  (fix: `tests/test_workflow_e2e.py` with 3-5 multi-step scenarios (ingest article → query entity → refine page → re-query) using real modules + mocked LLM at the boundary; mark `@pytest.mark.integration`)

- `tests/conftest.py` `project_root` / `raw_dir` / `wiki_dir` leak surface — fixtures point at REAL `PROJECT_ROOT` and are documented as "read-only use" but nothing enforces it. `test_cli.py:61-63` proves the global-escape paths exist (multi-global monkeypatch). Phase 4.5 already flagged `WIKI_CONTRADICTIONS` leaking, `load_purpose()` reading the real file, `append_wiki_log` defaulting to production. Phase 5 will add `wiki/hot.md`, `wiki/overview.md`, `wiki/_schema.md`, `raw/captures/` — one more leak surface each. (R3; cycle 7 only added autouse embeddings reset)
  (fix: make read-only fixtures fail loudly — return paths under a sandbox by default; provide explicit `real_project_root` fixture requiring `pytest --use-real-paths`; autouse monkeypatch of all `WIKI_*` constants to `tmp_path` for tests that don't explicitly opt out)

- `mcp/__init__.py:4` + `mcp_server.py:10` — FastMCP `run()` eagerly imports `core, browse, health, quality`; those pull `kb.query.engine` → `kb.utils.llm` → `anthropic` (548 modules, 0.58s), and `kb.mcp.health` pulls `kb.graph.export` → `networkx` (285 modules, 0.23s). Measured cold MCP boot: 1.83s / +89 MB / 2,433 modules — of which ~0.8s / ~35 MB is unnecessary for sessions using only `kb_read_page`/`kb_list_pages`/`kb_save_source`. (R3)
  (fix: defer `from kb.query.engine import …`, `from kb.ingest.pipeline import …`, `from kb.graph.export import …` into each tool body (pattern already used for feedback, compile); module-level imports in `kb/mcp/*` limited to `kb.config`, `kb.mcp.app`, stdlib)

- `query/embeddings.py` `_get_model` (~32-41) cold load — measured 0.81s + 67 MB RSS delta for `potion-base-8M` on first `kb_query` that touches vector search. `engine.py:87` gates on `vec_path.exists()` — per R2, vector index is almost always stale/absent so the model load is skipped AND hybrid silently degrades to BM25. Either outcome hurts: if the index exists we pay 0.8s on first user query; if it doesn't, "hybrid" is a lie. (R3)
  (fix: warm-load on MCP startup ONLY IF `vec_path.exists()`, and in a background thread so the user's first query isn't charged; or emit a "first query warm-up: embedding model loading…" progress line if user-facing latency crosses 300ms)

- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. A `kb_query(use_api=True)` (30s+), `kb_lint()` (multi-second disk walk), `kb_compile()` (minutes), or `kb_ingest_content(use_api=True)` (10+s) each hold a thread; under concurrent tool calls the pool saturates and subsequent calls queue. Claude Code often fires multiple tool calls in parallel; this turns invisible latency spikes into observed user-facing stalls. (R3; cycle 7 did not address)
  (fix: make long-I/O tools `async def` and `await anyio.to_thread.run_sync(...)` around the SDK call; or document / tune `FastMCP(num_threads=N)`; at minimum surface the concurrency model in the `app.py` instructions block)

- `compile/compiler.py:367-380` `compile_wiki` full-mode manifest pruning — `stale_keys` filter uses `raw_dir.parent / k` to check `.exists()`, but `raw_dir.parent` is NOT the project root when a caller passes a non-default `raw_dir` — every entry gets pruned. The prune also runs on `current_manifest` AFTER the per-source loop wrote successful hashes; between the two `load_manifest` calls there's no lock, so a concurrent `kb_ingest` adding a manifest entry in the window gets silently deleted on save. (R4)
  (fix: compute prune base once as `raw_dir.resolve().parent` matching `_canonical_rel_path`'s base; wrap "reload + prune + update templates + save" in `file_lock(manifest_path)` matching the per-source reload-save pattern)

- `compile/compiler.py:343-347` `compile_wiki` manifest write — after a successful `ingest_source`, the code does `load_manifest → manifest[rel_path] = pre_hash → save_manifest`. But `ingest_source` itself writes `manifest[source_ref] = source_hash` via `kb.ingest.pipeline:687` using its own path resolution. Two code paths write the same key with potentially different normalization (`source_ref` via `make_source_ref` vs `_canonical_rel_path`). Windows case differences or `raw_dir` overrides produce two divergent keys for the same file — `find_changed_sources` sees it as "new" and re-extracts. (R4)
  (fix: pipe `rel_path` into `ingest_source` (add `manifest_key: str | None = None`) OR delete the redundant per-loop write in `compile_wiki` and rely solely on `ingest_source`'s internal manifest update; assert one-key-per-source in tests)

- `compile/linker.py:178-241` `inject_wikilinks` cascade-call write race — `ingest_source` calls `inject_wikilinks` once per newly-created page (`pipeline.py:714-721`). For an ingest creating 50 entities + 50 concepts = 100 sequential calls in one process. Each iterates ALL wiki pages, reads each, may rewrite each via `atomic_text_write`. NO file lock. Concurrent ingest_source from another caller is identically iterating and rewriting the SAME pages. Caller A reads page X, caller B reads page X, A writes "X with link to A", B writes "X with link to B" — only B's wikilink survives. The retroactive-link guarantee silently fails under concurrent ingest. Compounds R4 overlapping-title (intra-process); R5 is the cross-process write-write race on the SAME page. (R5)
  (fix: per-target-page lock — `with file_lock(page_path): content = read; if needs_change: write`; or a wiki-wide writer lock during the inject phase since updates are usually fast)

- `ingest/pipeline.py:594-611,715` slug + path collision under concurrent ingest — two concurrent `ingest_source` calls extracting different titles that slugify to the same `summary_slug` (e.g., `"My Article"` and `"My  Article"` both → `my-article`) both check `summary_path.exists()` (603), both see False, both call `_write_wiki_page → atomic_text_write` to the SAME `wiki/summaries/my-article.md`. Last writer wins — first source's summary silently overwritten. Frontmatter `source:` lists only the second source, evidence trail is wrong, all entity references from the first source point to a now-deleted summary. Same flow at line 496 for entities/concepts. R1 flagged `kb_create_page` TOCTOU vs O_EXCL but `_write_wiki_page` and `_process_item_batch` have the SAME pattern AND are the actual hot path. (R5)
  (fix: replace `_write_wiki_page`'s `atomic_text_write` with exclusive-create — `os.open(O_WRONLY | O_CREAT | O_EXCL)` + temp-file rename; on `FileExistsError`, fall through to `_update_existing_page` (the merge path); same change in `_process_item_batch`)

- `ingest/pipeline.py:603,715-721,729-754` lock acquisition order risk between same-ingest stages — within one `ingest_source`: stage 1 writes summary page (line 609) → `append_evidence_trail` to SAME page; stage 2 calls `_update_existing_page` on each entity (re-reads + re-writes); stage 9 `inject_wikilinks` re-reads + re-writes some of the SAME pages it just wrote in stages 1-3; stage 11 writes `wiki/contradictions.md`. None use `file_lock`. Within ONE process this is OK. Under concurrent ingest A + B, the read-then-write windows in different stages of A overlap with different stages of B in non-deterministic order; debugging becomes impossible because each `kb_ingest` run shows different conflict patterns. R5 highlights the **systemic absence of any locking discipline across the entire 11-stage ingest pipeline** — a problem that compounds with every Phase 5 feature. (R5)
  (fix: introduce a per-page write-lock helper `with page_lock(page_path):` wrapping `read_text → modify → atomic_text_write` and use consistently across `_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`, and `inject_wikilinks`; OR adopt a coarse wiki-wide ingest mutex)

### HIGH — Deferred

> HIGH-severity items either surfaced after cycle-2 shipped or explicitly deferred from Phase 4.5 HIGH cycle-1 for a dedicated follow-up cycle.

- `review/refiner.py` `refine_page` write-then-audit ordering — after H1's page-file lock (cycle 1), a crash/OSError on the history-lock step still leaves the page body updated without an audit record. Adopt two-phase write (pending audit first → write page → flip to applied). See `docs/superpowers/decisions/2026-04-16-phase4.5-high-cycle1-design.md` Q_H. *(Deferred from Phase 4.5 HIGH cycle 1.)*

- `query/embeddings.py` vector-index lifecycle — Phase 4.5 HIGH cycle 1 shipped H17 hybrid (mtime-gated rebuild + batch skip), but deferred: (1) atomic temp-DB-then-replace rebuild (crash-mid-rebuild leaves empty index), (2) cold-load latency (0.8s+67MB on first query), (3) dim-mismatch (stored embedding dim vs current model not validated), (4) `_index_cache` cross-thread lock symmetry. Bundle into dedicated vector-index lifecycle cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*

- `tests/` multiprocessing tests for cross-process `file_lock` semantics — cycle 1 HIGH used in-process threading as a proxy but Windows NTFS lock behavior is not exercised. Add `@pytest.mark.slow` multiprocessing tests in a dedicated test-infrastructure cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*

### MEDIUM

<!-- Cycle 1 closed (2026-04-17): D1 _build_schema_cached deepcopy, E1 ingest/contradiction.py
     logger placement + tokens hoist + single-char language names, F1 kb_create_page O_EXCL,
     G1 kb_list_sources cap, F2 kb_refine_page caps, C2 _TEXT_EXTENSIONS library enforcement,
     J1 query/rewriter length guard, I2 search_raw_sources BM25 cache, I1 _flag_stale_results
     UTC, K1 _dedup_by_text_similarity tokens, M1 lint/verdicts load_verdicts mtime cache. -->

- `models/page.py` dataclasses are dead — `WikiPage` / `RawSource` exist but nothing returns them; `load_all_pages` / `ingest_source` / `query_wiki` each return ad-hoc dicts. "What is a page?" has ≥4 answers (dict, `Post`, `Path`, markdown blob); chunk indexing in Phase 5 will fork it again. (R1)
  (fix: delete dataclasses, or make them the canonical return type and migrate callers)

- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
  (fix: split into `config/paths.py` / `config/models.py` / `config/limits.py` / `config/search.py` / `config/lint.py`; or a `Settings` dataclass with grouped subfields; keep `from kb.config import *` shim)

- `compile/compiler.py` `compile_wiki` (~320-380) — per-source loop saves manifest after ingest but does not roll back wiki writes if a later manifest save fails; failure-recording branch swallows nested exceptions with a warning; final `append_wiki_log` runs even on partial failure. (R1)
  (fix: per-source "in-progress" marker in manifest cleared only after page write + log append; escalate manifest-write failure to CRITICAL)

- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write (acquire `.lock`, load full list, serialize, `mkstemp` + `fdopen` + `replace`, release). `file_lock` polls at 50 ms, adding minimum-latency floor on every verdict add. (R1)
  (fix: append-only JSONL with `msvcrt.locking` / `fcntl` locking; compact on read or via explicit `kb_verdicts_compact`)

- `lint/fetcher.py` `diskcache==5.6.3` — CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE in diskcache cache files. No patched upstream version as of 2026-04-18.
  (mitigation: diskcache is only used by trafilatura's robots.txt cache; exploit requires local write access to the cache directory; track upstream for a patched release)

- `src/kb/lint/augment.py::_post_ingest_quality` — AC17-drop rationale for future reference: cache-invalidation work was reconsidered and DROPPED. Cycle-13 AC2 intentionally uses uncached `frontmatter.load` to avoid FAT32/OneDrive/SMB coarse-mtime holes. Do not re-open without a concrete failure case.

- `compile/linker.py` cross-reference auto-linking — deferred: when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` added to A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`.

- `compile/publish.py` compile-time auto-publish hook — deferred: hook `kb publish` into `compile_wiki` so every compile auto-emits the Tier-1 + sibling + sitemap outputs. Cycle 16 shipped the sibling + sitemap BUILDERS standalone; the auto-hook into compile remains deferred pending a dedicated cycle.

- `compile/publish.py` manifest-based incremental sibling cleanup — deferred from cycle 16 Q2/C3 resolution: cycle 16 cleanup is O(|excluded|) unconditional unlinks per publish. When N(retracted) exceeds ~1000 a `.data/publish-siblings-manifest.json` atomic-state approach becomes preferable; defer until retracted-page counts warrant.

- `ingest/pipeline.py` index-file write order (~653-700) — per ingest: `index.md` → `_sources.md` → manifest → `log.md` → `contradictions.md`. A crash between `_sources.md` and manifest writes can duplicate entries on re-ingest. (R2)
  (fix: introduce an `IndexWriter` helper wrapping all four writes with documented order and recovery)

- `ingest/pipeline.py` observability — one `ingest_source` emits to `wiki/log.md` (step 7) + Python `logger.warning` (frontmatter parse failures, manifest failures, contradiction warnings, wikilink-injection failures, 8+ sites) + `wiki/contradictions.md` + N evidence-trail appends. No correlation ID connects them. `wiki/log.md` records intent ("3 created, 2 updated"), not outcome. Debugging a flaky ingest requires correlating stderr against `wiki/log.md` against `contradictions.md` by timestamp window. (R2)
  (fix: generate `request_id = uuid7()` at top of `ingest_source` and thread through every emitter; add structured `.data/ingest_log.jsonl` with full result dict per call, sharing the id with `wiki/log.md`)

- `ingest/pipeline.py` + `ingest/evidence.py` page write vs evidence append (~150-151, 362-365) — `_write_wiki_page` and `_update_existing_page` perform atomic page write, then call `append_evidence_trail` which does its own read+write+atomic-rename. If the second call fails (disk full, permission flap, lock contention), the page has a new source reference with no evidence entry explaining why. Phase 4's provenance guarantee is conditional. (R2)
  (fix: combine page body + evidence trail into a single rendered output and write atomically; or wrap the pair in a file lock and surface the second-call failure)

- CLI ↔ MCP parity — `cli.py` exposes 6 commands; MCP exposes 25. Operational tasks (view trends, audit a verdict, refine a page, read a page, search, stats, list pages/sources, graph viz, drift, save source, create page, affected pages, reliability map, feedback) require an MCP-speaking client. Tests cannot piggyback on CLI invocation; debugging in CI / cron is by `python -c` only. (R2)
  (fix: auto-generate CLI subcommands from the FastMCP tool registry; or collapse MCP + CLI onto a shared `kb.api` service module — also kills the function-local-import issue cleanly)

- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. MCP `kb_compile` and `kb compile` CLI are cosmetic wrappers. Phase 5's two-phase compile / pre-publish gate / cross-source merging would land in the wrong layer because `compile_wiki` has no batch context. (R2)
  (fix: make `compile_wiki` a real two-phase pipeline (collect extractions → reconcile cross-source → write) and document the contract; or rename to `batch_ingest` and stop pretending compile is distinct)

- `tests/` no golden-file / snapshot tests — grep for `snapshot`/`golden`/`syrupy`/`inline_snapshot`/`approvaltests` returns zero hits. Wiki rendering (`_build_summary_content`, `append_evidence_trail`, contradictions append, `build_extraction_prompt`, `_render_sources`, Mermaid export, lint report) is verified only by `assert "X" in output`. `test_v0917_evidence_trail.py` checks `"## Evidence Trail" in text` — the actual format (order of `date | source | action`, prepend direction, whitespace) is unverified. Phase 5's output-format polymorphism (`kb_query --format=marp|html|chart|jupyter`), `wiki/overview.md`, and `wiki/_schema.md` all produce structured output that LLM-prompt tweaks silently reformat. (R3)
  (fix: add `pytest-snapshot` or `syrupy`; start with frontmatter rendering, evidence-trail format, Mermaid output, lint report format; commit `tests/__snapshots__/`)

- `tests/` thin MCP tool coverage — of 25 tools, `kb_compile_scan`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`, plus the entire `health.py` cluster each have 1-2 assertion smoke tests. Deeply-tested tools (`kb_query`, `kb_ingest`, `kb_refine_page`) accumulated coverage organically across version files. Phase 4.5 flags `kb_graph_viz` `export_mermaid` non-deterministic tie-break and `kb_detect_drift` happy-path-only, both unprotected by per-tool test. (R3)
  (fix: one `tests/test_mcp_<tool>.py` per tool with at minimum: happy path, validation error, path-traversal rejection, large-input cap, missing-file branch; auto-generate skeletons from the FastMCP registry)

- `tests/test_phase4_audit_concurrency.py` single-process file_lock coverage — `test_file_lock_basic_mutual_exclusion` spawns threads, never `multiprocessing.Process` / `subprocess.Popen`. Phase 4.5 R2 flags `file_lock` PID-liveness broken on Windows (PIDs recycled, `os.kill(pid, 0)` succeeds for unrelated process); threads share PID so this is structurally impossible to surface with the current test. Manifest race, evidence-trail RMW race, contradictions append race, feedback eviction race all involve separate processes — autoresearch loop, file watcher, SessionStart hook (Phase 5) all run in separate processes alongside MCP. (R3)
  (fix: `multiprocessing.Process`-based test holding the lock from a child while parent attempts acquire; `@pytest.mark.integration`; assert PID file contains the child's PID)

- `ingest/pipeline.py:712-721` `ingest_source` inject_wikilinks per-page loop — for each newly-created entity/concept page, `inject_wikilinks` is called independently, each time re-scanning ALL wiki pages from disk via `scan_wiki_pages` + per-page `read_text`. A single ingest creating 50 entities + 50 concepts = 100 `inject_wikilinks` calls × N pages = 100·N disk reads. At 5k pages that's 500k reads per ingest — worse than R2-flagged graph/load double-scan. (R4)
  (fix: batch-aware `inject_wikilinks_batch(titles_and_ids, pages)` that scans each page once and checks for all new titles; compile N patterns into a single alternation; write back once)

- `ingest/pipeline.py:682-693 + compile/compiler.py:117-196` manifest hash key inconsistency under concurrent ingest — `_is_duplicate_content` (102) calls `load_manifest` to check whether ANY entry matches `source_hash`. If caller A is mid-ingest of `raw/articles/foo.md` (passed dedup at 566 but not yet written manifest at 688), caller B starts ingest of an IDENTICAL-content `raw/articles/foo-copy.md` — B's `_is_duplicate_content` sees no match (A hasn't saved), B proceeds to full extraction + page writes, BOTH succeed and write to manifest. Wiki now has TWO summary pages with identical content but different titles. R2 flagged the duplicate-check race; R5 specifies the **window**: the entire LLM extraction (~30 seconds) + all 11 ingest stages between dedup-check and manifest-save is unprotected. (R5)
  (fix: hold `file_lock(manifest_path)` across the entire `ingest_source` body OR write a "claim" entry to manifest as `{source_ref: "in_progress:{hash}"}` immediately after the dedup check, with `try/finally` to either commit the real hash on success or remove the claim on failure)

### LOW

_All items resolved — see CHANGELOG cycle 13._

<!-- Cycle 13 closed: AC7 sweep_orphan_tmp on kb.cli:cli boot ({.data, WIKI_DIR}); AC8 +
     _resolve_raw_dir helper derives run_augment raw_dir from wiki_dir.parent / "raw" when
     wiki_dir is overridden and raw_dir omitted. -->

---

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

### RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13)

<!-- Ranked priority derived from re-reading Karpathy's gist against current state.
     All items below already exist as entries in the leverage-grouped subsections — this block only SEQUENCES them.
     Rationale: research/karpathy-community-followup-2026-04-12.md §Prioritized roadmap additions + 2026-04-13 ranking pass.
     Ranking axes: (1) Karpathy-verbatim fidelity, (2) unsolved-gap coverage, (3) effort vs leverage. -->

**Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce:**
<!-- Tier 1 #1 (`kb_query --format=…` output adapters) SHIPPED in Phase 4.11 (2026-04-14). -->
<!-- Tier 1 #2 (`kb_lint --augment`) SHIPPED in Phase 5.0 (2026-04-15). -->
1. `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen — makes the wiki retrievable by other agents; renderers over existing frontmatter/graph. Cross-ref: HIGH LEVERAGE — Output-Format Polymorphism.
2. `wiki/_schema.md` vendor-neutral schema + `AGENTS.md` thin shim — Karpathy: *"schema is kept up to date in AGENTS.md"*; enables Codex / Cursor / Gemini CLI / Droid portability without forking schema per tool. Cross-ref: LOW LEVERAGE — Operational.

**Tier 2 — Epistemic integrity (unsolved-gap closers every community voice flagged):**
5. `belief_state: confirmed|uncertain|contradicted|stale|retracted` frontmatter — cross-source aggregate orthogonal to per-source `confidence`. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
6. `kb_merge <a> <b>` + duplicate-slug lint check — catches `attention` vs `attention-mechanism` drift; top-cited contamination failure mode in the thread. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
7. `kb_query` coverage-confidence refusal gate — refuses low-signal queries with rephrase suggestions instead of synthesizing mediocre answers. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
8. Inline `[EXTRACTED]` / `[INFERRED]` / `[AMBIGUOUS]` claim tags with `kb_lint_deep` sample verification — complements page-level `confidence` with claim-level provenance; directly answers "LLM stated this as sourced fact but it's not in the source." Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.

**Tier 3 — Ambient capture + security rail (distribution UX):**
9. `.llmwikiignore` + pre-ingest secret/PII scanner — missing safety rail given every ingest currently sends full content to the API. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.
10. `SessionStart` hook + `raw/` file watcher + `_raw/` staging directory — ship as a three-item bundle that eliminates the "remember to ingest" step. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.

**Recommended next target:** #1 (`/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen). Reasons: with output adapters (Phase 4.11) and reactive gap-fill (Phase 5.0) shipped, the next-highest Karpathy-fidelity item is the machine-consumable publish format — renderers over existing frontmatter + graph, low effort, makes the wiki itself a retrievable source for other agents. Contained blast radius in `kb.compile.publish` (new module) + compile-pipeline hook.

**Already in flight (excluded from ranking):** `kb_capture` MCP tool (spec landed 2026-04-13 in `docs/superpowers/specs/2026-04-13-kb-capture-design.md`), `wiki/purpose.md` KB focus document (shipped 2026-04-13, commit `d505dca`).

**Explicit scope-out from this re-evaluation pass (keep deferred to Phase 6 or decline):**
- `kb_consolidate` sleep-cycle pass — high effort; overlaps with existing lint/evolve; defer until lint is load-bearing.
- Hermes-style independent cross-family supervisor — infra-heavy (second provider + fail-open policy); Phase 6.
- `kb_drift_audit` cold re-ingest diff — defer until `kb_merge` + `belief_state` land (surface overlap).
- `kb_synthesize [t1, t2, t3]` k-topic combinatorial synthesis — speculative; defer until everyday retrieval is saturated.
- `kb_export_subset --format=voice` for mobile/voice LLMs — niche; defer until a second-device use case emerges.
- Multi-agent swarm + YYYYMMDDNN naming + capability tokens (redmizt) — team-scale pattern; explicit single-user non-goal.
- RDF/OWL/SPARQL native storage — markdown + frontmatter + wikilinks cover the semantic surface.
- Ed25519-signed page receipts — git log is the audit log at single-user scale.
- Full RBAC / compliance audit log — known and acknowledged ceiling; document as a README limitation rather than fix.
- Hosted multiplayer KB over MCP HTTP/SSE — conflicts with local-first intent.
- `qmd` CLI external dependency — in-process BM25 + vector + RRF already ships.
- Artifact-only lightweight alternative (freakyfractal) — sacrifices the persistence that is the reason this project exists.
- FUNGI 5-stage rigid runtime framework — same quality gain expected from already-deferred two-step CoT ingest.
- Synthetic fine-tuning of a personal LLM on the compiled wiki — over the horizon.

### HIGH LEVERAGE — Epistemic Integrity 2.0

<!-- `belief_state` vocabulary + validate_frontmatter integration SHIPPED in cycle 14 AC1/AC2 (2026-04-20). Cross-source propagation rules in lint/checks.py remain deferred. -->

- `ingest/pipeline.py` `source` subsection-level provenance — allow `source: raw/file.md#heading` or `raw/file.md:L42-L58` deep-links in frontmatter; ingest extractor captures heading context so citations point at the actual section that grounds the claim. Source: Agent-Wiki (kkollsga, gist — two-hop citation traceability).
  (effort: Medium — extractor update + citation renderer + backlink resolver for the new form)

- `lint/drift.py` `kb_drift_audit` — cold re-ingest a random sample of raw sources with no prior wiki context, diff against current wiki pages, surface divergence as "potential LLM drift" warnings. Different from existing `kb_detect_drift` which checks source mtime changes; this catches *wiki-side* drift where compilation has diverged from source truth. Source: Memory Drift Prevention (asakin, gist — cites ETH Zurich study: auto-generated context degraded 5/8 cases).
  (effort: Medium — new module; reuse existing `ingest_source` with `wiki_dir=tmp` then diff)

- `compile/merge.py` `kb_merge <a> <b>` — MCP tool merges two pages, updates all backlinks across `wiki/` and `wiki/outputs/`, archives absorbed page to `wiki/archive/` with a redirect stub, one git commit per merge. Source: Louis Wang.
  (effort: Medium — duplicate-slug detection is tracked separately in Phase 4.5 MEDIUM)

<!-- `query/engine.py` coverage-confidence gate SHIPPED in cycle 14 AC5 (fixed refusal template). LLM-suggested rephrasings remain deferred — see "kb_query low-coverage advisory LLM-suggested rephrasings" above. -->

<!-- `models/` `authored_by` frontmatter vocabulary + validate_frontmatter SHIPPED in cycle 14 AC1/AC2. Query-weight boost + lint human-auto-edited flag SHIPPED in cycle 15. -->

- `ingest/pipeline.py` `lint/semantic.py` inline claim-level confidence tags — emit `[EXTRACTED]`, `[INFERRED]`, `[AMBIGUOUS]` inline markers in wiki page bodies during ingest; modify ingest LLM prompts to annotate individual claims at source; `kb_lint_deep` spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file, flagging hallucinated attributions. Complements page-level `confidence` frontmatter without replacing it; directly answers "LLM stated this as sourced fact but it's not in the source." Source: llm-wiki-skill confidence annotation + lint verification model.
  (effort: Medium — ingest prompt update + regex claim parser + lint spot-check against raw source text)

### HIGH LEVERAGE — Output-Format Polymorphism

<!-- `query/formats/` `kb_query --format=…` adapters SHIPPED in Phase 4.11 (2026-04-14). -->

<!-- `compile/publish.py` `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` SHIPPED in cycle 14 AC20-AC22 (2026-04-20) with `kb publish` CLI subcommand. Atomic writes + incremental publish SHIPPED in cycle 15. Auto-compile hook + per-page sibling `.txt`/`.json` files + `/sitemap.xml` remain deferred — see Phase 4.5 MEDIUM. -->

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass modeled on biological memory consolidation: NREM (new events → concepts, cross-event pattern extraction), REM (contradiction detection → mark old edges `superseded` rather than delete), Pre-Wake (graph health audit). Runs as nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three distinct sub-passes; overlaps with existing lint/evolve but with "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics to surface cross-domain connections. New query mode beyond retrieval. Source: Elvis Saravia reply (*"O(n^k) synthesis across k domains — stoic philosophy × saas pricing × viral content × parenting"*).
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3 since path count explodes)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice (standalone blob) loadable into voice-mode LLMs or mobile clients. Addresses *"interactive podcast while running"* use case. Source: Lex-style reply.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `ingest/session.py` — auto-ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. Distinct from `kb_capture` (user-triggered, any text) and deferred "conversation→KB promotion" (positive-rated query answers only): this is ambient, runs on every session. Source: Pratiyush/llm-wiki.
  (effort: Medium — JSONL parsers per agent + dedup against existing raw/conversations/)

- `hooks/` `SessionStart` hook + `raw/` file watcher — hooks auto-sync on every Claude Code launch; file watcher with debounce triggers ingestion on new files in `raw/` without explicit CLI invocation. Source: Pratiyush/llm-wiki + Memory-Toolkit (IlyaGorsky, gist).
  (effort: Low — Claude Code hook + `watchdog` file observer)

- `ingest/filter.py` `.llmwikiignore` + secret scanner — pre-ingest regex-based secret/PII filter (API keys, tokens, passwords, paths on `.llmwikiignore`); rejects or redacts before content leaves local. Missing safety rail given every ingest currently sends full content to the API. Source: rohitg00 LLM Wiki v2 + Louis Wang security note.
  (effort: Low — `detect-secrets`-style regex list + glob-pattern ignore)

- `_raw/` staging directory — vault-internal drop-and-forget directory for clipboard pastes / rough notes; next `kb_ingest` promotes to `raw/` and removes originals. Distinct from `raw/` (sourced documents) and deferred `kb_capture` (explicit tool). Source: Ar9av/obsidian-wiki.
  (effort: Low — directory convention + promotion step in ingest)

<!-- Per-subdir source_type inference already implemented as `detect_source_type` at src/kb/ingest/pipeline.py:288-301 (cycle 14 Step 5 confirmed: AC13-15 dropped as duplicates). -->


### MEDIUM LEVERAGE — Refinements to existing Phase 5 deferred items

- Deferred "multi-signal graph retrieval" — use empirical weights 3 (direct link) / 4 (source-overlap) / 1.5 (Adamic-Adar) / 1 (type-affinity). Source: nashsu/llm_wiki (concrete ratios from production use).
  (effort: N/A — parameter choice for the existing deferred item)

- Deferred "community-aware retrieval boost" — Louvain intra-edge density <0.15 = "sparse/weak" threshold; surface sparse communities in `kb_evolve`. Source: nashsu.
  (effort: N/A — threshold choice)

<!-- Per-platform `SOURCE_DECAY_DAYS` dict + `decay_days_for` helper SHIPPED in cycle 14 AC10/AC11. Cycle 15 wired call sites into `_flag_stale_results` and lint staleness scan, and shipped the topic volatility multiplier. -->

<!-- `CONTEXT_TIER1_SPLIT` 60/20/5/15 constants + `tier1_budget_for` helper SHIPPED in cycle 14 AC7/AC8. Cycle 15 wired `_build_query_context` to `tier1_budget_for("wiki_pages")`. -->

- Deferred "graph topology gap analysis" — expose as card types: "Isolated (degree ≤ 1)", "Bridge (connects ≥ 3 clusters)", "Sparse community (cohesion < 0.15)" — each with one-click trigger that dispatches `kb_evolve --research` on the specific gap. Source: nashsu.
  (effort: N/A — card-type taxonomy for existing deferred item)

### LOW LEVERAGE — Testing Infrastructure

- `tests/test_e2e_demo_pipeline.py` hermetic end-to-end pipeline test — single test driving `ingest_source` → `query_wiki` → `run_all_checks` over the committed `demo/raw/karpathy-x-post.md` and `demo/raw/karpathy-llm-wiki-gist.md` sources with the synthesis LLM stubbed. Catches cross-module integration regressions (ingest ↔ compile manifest ↔ query engine ↔ lint runner) that single-module unit tests miss. Uses `ingest_source(..., extraction=dict)` to skip LLM extraction entirely; only monkeypatches the synthesis `call_llm` at `kb.query.engine.call_llm`, plus the module-level constants `RAW_DIR`/`PROJECT_ROOT`/`WIKI_CONTRADICTIONS`/`HASH_MANIFEST` at both `kb.config.X` and each consuming module. Deferred in favor of the active Phase 4.5 bug-fix backlog. Design spec content was drafted in-session but not committed; rewrite from this bullet when picked up. Source: Layer 1 of the three-layer e2e strategy (Layer 2 = MCP contract test via `fastmcp.Client` in-process; Layer 3 = gated `@pytest.mark.live` smoke test against real Anthropic API).
  (effort: Low — ~100-line single test file, no new fixtures or dependencies; `tmp_project` in `tests/conftest.py` is sufficient. Asserts page IDs in `pages_created`/`pages_updated`, frontmatter source-list merge on shared entities, `wikilinks_injected` on second ingest, `[source: …]` citation round-trip, and `lint_report["summary"]["error"] == 0`. Run cadence: every CI, hermetic, ~1s.)

### LOW LEVERAGE — Operational

- `wiki/_schema.md` vendor-neutral single source of truth — move project schema (page types, frontmatter fields, wikilink syntax, operation contracts) out of tool-convention files and into `wiki/_schema.md` co-located with the data it describes. Existing `CLAUDE.md` / future `AGENTS.md` / `GEMINI.md` stay as thin (~10-line) vendor shims that point at `_schema.md` for project rules. Schema is machine-parseable (fenced YAML blocks under markdown headers) and validated by lint on every ingest. Innovation vs. the common "symlink AGENTS.md → CLAUDE.md" pattern: the schema lives WITH the wiki, portable across agent frameworks (Codex, Cursor, Gemini CLI, shell scripts). Follows the existing `_sources.md` / `_categories.md` convention. Source: Karpathy tweet (schema portability prompt) + project design.
  (effort: Medium — (a) write `wiki/_schema.md` starter as self-describing meta page; (b) `kb.schema.load()` parser; (c) `kb_lint` integration validates frontmatter against schema; (d) `schema_version` + `kb migrate` CLI; (e) optional multi-persona sections `### for ingest` / `### for query` / `### for review` so agents load scoped context. Defer vendor shim updates — keep `CLAUDE.md` unchanged until user chooses to slim it)

- `cli.py` `kb search <query>` subcommand — colorized terminal output over the existing hybrid search; `kb search --serve` exposes a minimal localhost web UI. Power-user CLI over the same engine the LLM already uses via MCP. Source: Karpathy tweet (*"small and naive search engine, web ui and CLI"*).
  (effort: Low — Click command + Flask/FastAPI localhost UI)

- Git commit receipts on ingest — emit `"four new articles appeared: Amol Avasari, Capability Overhang, CASH Framework, Success Disasters"` style summary with commit hash and changed files per source. Source: Fabian Williams.
  (effort: Low — wrap existing ingest return dict with a formatter)

### HIGH LEVERAGE — Ingest & Query Convenience

- `mcp/core.py` `kb_ingest` URL-aware 5-state adapter — upgrade `kb_ingest`/`kb_ingest_content` to accept URLs alongside file paths; URL routing table in `kb.config` maps patterns to source type + `raw/` subdir + preferred adapter; before executing, checks 5 explicit states: `not_installed`, `env_unavailable`, `runtime_failed`, `empty_result`, `unsupported` — each emits a specific recovery hint and offers manual-paste fallback. Eliminates the "run crwl, save file, then kb_ingest file" three-step friction. Source: llm-wiki-skill adapter-state.sh 5-state model.
  (effort: Medium — URL routing table in config + per-state error handling + adapter dispatcher)

- `mcp/core.py` `kb_delete_source` MCP tool — remove raw source file and cascade: delete source summary wiki page, strip source from `source:` field on shared entity/concept pages without deleting them, clean dead wikilinks from remaining wiki pages, update `index.md` and `_sources.md`. Fills the only major operational workflow gap not addressed by existing tooling.
  (effort: Medium — cascade deletion logic + backlink cleanup + atomic index/sources update)

<!-- `kb_query save_as` parameter remains deferred — see Phase 4.5 MEDIUM. -->

- `evolve/analyzer.py` `kb_evolve mode=research` — for each identified coverage gap, decompose into 2–3 web search queries, fetch top results via fetch MCP, save to `raw/articles/` via `kb_save_source`, return file paths for subsequent `kb_ingest`; capped at 5 sources per gap, max 3 rounds (broad → sub-gaps → contradictions). Turns evolve from advisory gap report into actionable source acquisition pipeline. Source: claude-obsidian autoresearch skill.
  (effort: Medium — gap decomposition prompt + fetch MCP integration + 3-round loop with source cap)

- `wiki/purpose.md` KB focus document — lightweight file defining KB goals, key questions, and research scope; included in `kb_query` context and ingest system prompt so the LLM biases extraction toward the KB's current direction. Source: nashsu/llm_wiki purpose.md.
  (effort: Low — one markdown file + read in query_wiki + prepend in ingest system prompt)

### MEDIUM LEVERAGE — Search & Indexing

- `query/bm25.py` `query/embeddings.py` chunk-level sub-page indexing — split wiki pages into topically coherent chunks using Savitzky-Golay boundary detection (embed sentences with model2vec, compute adjacent cosine similarities, SG smoothing 5-window 3rd-order polynomial, find zero-crossings as topic boundaries); each chunk indexed as `<page_id>:c<n>`; query engine scores chunks, deduplicates to best chunk per page, loads full pages for synthesis. Resolves the weakness where relevant content is buried in long pages. Source: garrytan/gbrain semantic.ts + sage-wiki FTS5 chunking.
  (effort: High — SG chunking module + BM25 index schema change + chunk-to-page dedup aggregation layer)

<!-- Cross-reference auto-linking remains deferred — see Phase 4.5 MEDIUM. -->

- `lint/checks.py` `query/engine.py` PageRank-prioritized semantic lint sampling — when `kb_lint_deep` must limit its page budget, select pages by PageRank descending rather than arbitrary order; high-authority pages with quality issues have outsized downstream impact on citing pages. Source: existing `graph_stats` PageRank scores.
  (effort: Low — sort by graph_stats PageRank before sampling; zero new infrastructure required)

### MEDIUM LEVERAGE — Page Lifecycle & Quality Signals

<!-- `models/` `status` frontmatter vocabulary + validate_frontmatter + query ranking boost SHIPPED in cycle 14 AC1/AC2/AC23. Cycle 15 shipped `kb_lint` mature-stale flagging; `kb_evolve` status-priority routing remains deferred — see Phase 4.5 MEDIUM AC8-carry. -->

<!-- Inline quality callout markers remain deferred — see Phase 4.5 MEDIUM. -->

- `wiki/hot.md` wake-up context snapshot — ~500-word compressed context updated at session end (recent facts, recent page changes, open questions); read at session start via `SessionStart` hook; survives context compaction and session boundaries; enables cross-session continuity without full wiki crawl. Source: MemPalace concept + claude-obsidian hot cache.
  (effort: Low — append-on-ingest + SessionStart hook reads + one markdown file)

- `wiki/overview.md` living overview page — auto-revised on every ingest as the final pipeline step; always-current executive summary across all sources; updated not replaced on each ingest. Source: llm-wiki-agent living overview.
  (effort: Low — scan-tier LLM over index.md + top pages; one file auto-updated per ingest)

### MEDIUM LEVERAGE — Knowledge Promotion & Ingest Quality

- `query/engine.py` `feedback/store.py` conversation→KB promotion — positively-rated query answers (rating ≥ 4) auto-promote to `wiki/synthesis/{slug}.md` pages with citations mapped to `source:` refs; coexists with `save_as` parameter (immediate, no gate) as the feedback-gated deferred path. Source: garrytan/gbrain maintain skill.
  (effort: Medium — feedback store hook + synthesis page writer + conflict check against existing pages)

- `ingest/pipeline.py` two-step CoT ingest analysis pass — split ingest into: (1) analysis call producing entity list + connections to existing wiki + contradictions + wiki structure recommendations; (2) generation call using analysis as context. Improves extraction quality and enables richer contradiction flagging; feeds Phase 4 auto-contradiction detection. Source: nashsu/llm_wiki two-step chain-of-thought.
  (effort: Medium — split single ingest LLM call into two sequential calls with analysis-as-context)

### Phase 6 candidates (larger scope, not yet scheduled)

- Hermes-style independent quality-gate supervisor — different-model-family validator (not same-family self-review) before page promotion. Source: Secondmate (@jumperz, via VentureBeat).
  (effort: High — adds a second provider; challenges fail-open defaults)

- Mesh sync for multi-agent writes — last-write-wins with timestamp conflict resolution; private-vs-shared scoping (personal preferences private, architecture decisions shared). Source: rohitg00.
  (effort: High — assumes multi-writer concurrency model)

- Hosted MCP HTTP/SSE variant — multi-device access (phone Claude app, ChatGPT, Cursor, Claude Code) reading/writing the same KB. Source: Hjarni/dev.to.
  (effort: High — MCP transport + auth; currently stdio-only)

- Personal-life-corpus templates — Google Takeout / Apple Health / AI session exports / bank statements as a domain starter kit. Privacy-aware ingest layered on `.llmwikiignore`. Source: anonymous personal-data-RAG reply.
  (effort: Medium — per-source-type extractor templates; depends on `.llmwikiignore` landing first)

- Multi-signal graph retrieval — BM25 seed → 4-signal graph expansion: direct wikilinks ×3 + source-overlap ×4 + Adamic-Adar shared-neighbor similarity ×1.5 + type-affinity ×1; nodes ranked by combined BM25 + graph score with budget-proportional context assembly. Prerequisite: typed semantic relations (below). Source: nashsu/llm_wiki relevance model.
  (effort: High — graph score combination layer + per-signal weight tuning + typed relations as prerequisite)

- Typed semantic relations on graph edges — extract 6 relation types via keyword matching: `implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`; stored as edge attribute in NetworkX + SQLite; enables typed graph traversal in `kb_query`. Prerequisite for multi-signal retrieval. Source: sage-wiki configurable ontology.
  (effort: Medium — relation extractor pass + NetworkX/SQLite graph schema update)

- Temporal claim tracking — `valid_from`/`ended` date windows on individual claims within pages; enables staleness/contradiction resolution at claim granularity rather than page granularity. Requires new SQLite KG schema. Source: MemPalace SQLite KG pattern.
  (effort: High — claim-level SQLite schema + ingest extractor update + query-time filtering)

- Semantic edge inference in graph — two-pass graph build: existing wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS with confidence 0–1; re-infers only changed pages via content hash cache. Source: llm-wiki-agent.
  (effort: High — 2-pass build logic + confidence-weighted edges + per-page change detection)

- Answer trace enforcement — require synthesizer to tag every factual claim with `[wiki/page]` or `[raw/source]` citation at synthesis time; post-process strips or flags uncited claims as gaps. Source: epistemic integrity requirement.
  (effort: High — synthesis prompt rewrite + citation parser + enforcement pass + graceful fallback)

- Multi-mode search depth toggle (`depth=fast|deep`) — `depth=deep` uses Monte Carlo evidence sampling for complex multi-hop questions; `depth=fast` is current BM25 hybrid. Depends on MC sampling infrastructure. Source: Sirchmunk Monte Carlo evidence sampling.
  (effort: High — MC sampler architecture + budget allocation + fast/deep routing logic)

- Semantic deduplication pre-ingest — embedding similarity check before ingestion to catch same-topic-different-wording duplicates beyond content hash; flag if cosine similarity >0.85 to any existing raw source. Source: content deduplication research.
  (effort: Medium — embed new source + nearest-neighbor check vs existing vector store)

- Interactive knowledge graph HTML viewer — self-contained vis.js HTML export from `kb_graph_viz` with `format=html`; dark theme, search bar, click-to-inspect nodes, Louvain community clustering, edge type legend. Source: llm-wiki-agent graph.html.
  (effort: Medium — vis.js template + Louvain community IDs per node + edge type legend)

- Two-phase compile pipeline + pre-publish validation gate — phase 1: batch cross-source merging before writing; phase 2: validation gate rejects pages with unresolved contradictions or missing required citations. Architecture change to current single-pass compiler. Source: compilation best practices.
  (effort: High — compiler refactor into two phases + validation gate + publish/reject state machine)

- Actionable gap-fill source suggestions — enhance `kb_evolve` to suggest specific real-world sources for each gap ("no sources on MoE, consider the Mixtral paper"). Mostly superseded by `kb_evolve mode=research` (Phase 5) which fetches sources autonomously; keep as fallback for offline/no-fetch environments. Source: nashsu/llm_wiki.
  (effort: Low delta on evolve — add one LLM call per gap; ship only if mode=research is blocked)

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision, same failure mode as Evernote's "which folder" and Notion's "which tag". Document that our model merges aggressively and that atomic-note alternative exists.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; our counter is evidence-trail provenance plus two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion, not optional.

---

## Phase 5 pre-merge (feat/kb-capture, 2026-04-14)

<!-- Discovered by 6 specialist reviewers (security, logic, performance, reliability, maintainability, architecture)
     running Rounds 1 and 2 against feat/kb-capture. Primary scope: new kb.capture module + supporting changes.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2). -->

<!-- 2026-04-17 cleanup pass verified R1/R2/R3 HIGH, MEDIUM, and LOW items fixed in capture.py;
     remaining entries below are genuinely open. -->

### CRITICAL

- `capture.py:341-372, 428-460` two-pass write architecture needed — STRUCTURAL: `alongside_for[i]` is a frozen list built from Phase A slugs and never recomputed after a Phase C slug reassignment. Items 0..i-1 already written to disk retain `captured_alongside` entries pointing at item i's Phase A slug (which was never written) under cross-process collision. Only complete fix is two-pass: Pass 1 = `O_EXCL`-reserve all N slugs with retry; Pass 2 = compute `alongside_for` from finalized slugs, write all files. Documented as "v1 limitation" in `_write_item_files` docstring. (R3)
  (fix: implement two-pass `_write_item_files`; OR keep TODO(v2) marker and document explicitly in `CaptureResult` docstring)

### MEDIUM

- `capture.py:209-238` `_PROMPT_TEMPLATE` inline string vs templates/ convention — all other LLM prompts live as YAML files in `templates/` loaded via `load_template()`. R2 NIT refined: existing `templates/*.yaml` define JSON-Schema `extract:` fields for `build_extraction_schema()` — a structurally different purpose, so a plain format-string prompt does not fit there. (R1 + R2 NIT)
  (fix: `templates/capture_prompt.txt` in a new `prompts/` subdirectory; OR keep inline but extract to named module-level constant with comment)

- `config.py:40-53` + `CLAUDE.md` architectural contradiction — `CAPTURES_DIR = RAW_DIR / "captures"` places the capture write target inside `raw/`, which CLAUDE.md defines as "Immutable source documents. The LLM reads but **never modifies** files here." `raw/captures/` is the only LLM-written output directory inside `raw/`. (R1)
  (fix: either (a) move `CAPTURES_DIR` to `captures/` at project root, or (b) carve out an explicit exception in CLAUDE.md and the config comment)

---

## Phase 5 pre-merge (feat/phase-5-kb-lint-augment, 2026-04-15)

<!-- All items resolved in cycle 17. See CHANGELOG.md cycle 17. -->

_All items resolved — see CHANGELOG `[Unreleased]` Phase 4.5 cycle 17 (AC11/AC12/AC13 — `run_augment(resume=...)` wired through CLI + MCP with shared `_validate_run_id` 8-hex validator)._

---

## Cycle 20 candidates (surfaced during cycle 19)

<!-- Cycle 19 deferrals and Step-11 follow-ups. Effort estimates in parentheses. -->

### MEDIUM

- `src/kb/review/refiner.py::list_stale_pending` — sweep / auto-promote tool. Cycle-19 AC8b shipped the read-only visibility helper; the matching MUTATION tool (auto-promote `pending` rows older than N days to `failed` with a synthesized `error: "abandoned by sweep"` field, OR auto-delete) is deferred. Needs a policy decision (auto-promote vs auto-delete vs operator-review-only) plus its own lock discipline. *(Carried from cycle-19 AC8b decision.)*
  (effort: Medium — new MCP tool + CLI command + locking + policy spec)

- `src/kb/compile/compiler.py::_canonical_rel_path` — Windows tilde-shortened path coverage test (T-13a). Cycle-19 left the Windows-specific divergence test as a placeholder skipif because constructing tilde-shortened paths in pytest requires platform-specific os.environ + symlink fixtures. The portable T-13b symlink test ships and exercises the same canonicalizer. A dedicated Windows-only follow-up could harden the test suite for that platform.
  (effort: Low — Windows tilde fixture + CI matrix addition)

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
- **Phase 4 post-release audit** — all items resolved (23 HIGH + ~30 MEDIUM + ~30 LOW) in CHANGELOG.md [Unreleased]
- **Phase 5 three-round code review (2026-04-17)** — all items resolved in CHANGELOG `[Unreleased]` Backlog-by-file cycle 1 (3 HIGH: raw_dir threading, ingest raw_dir parameter, manifest failed-state advance; 4 MEDIUM: data_dir threading, max_gaps lower bound, proposal URL re-validation, summary-count semantics)
