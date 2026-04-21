# Cycle 22 — Implementation Plan (Step 07)

## Pre-flight grep evidence

Command:
```bash
grep -n "def ingest_source\|effective_wiki_dir\|_emit_ingest_jsonl(\"start\"\|source_path_nc\|raw_dir_nc" src/kb/ingest/pipeline.py
```

Output:
```text
192:    effective_wiki_dir: Path,
199:    contradictions_path = effective_wiki_dir / "contradictions.md"
1007:    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
1047:        item_path = effective_wiki_dir / subdir / f"{item_slug}.md"
1077:def ingest_source(
1164:    raw_dir_nc = Path(os.path.normcase(str(effective_raw_dir.resolve())))
1165:    source_path_nc = Path(os.path.normcase(str(source_path)))
1167:        source_path_nc.relative_to(raw_dir_nc)
1208:    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
1222:    _emit_ingest_jsonl("start", request_id, source_ref, source_hash, outcome={})
1229:            extraction = extract_from_source(raw_content, source_type, wiki_dir=effective_wiki_dir)
1270:            effective_wiki_dir=effective_wiki_dir,
1319:    effective_wiki_dir: Path,
1370:    summary_path = effective_wiki_dir / "summaries" / f"{summary_slug}.md"
1425:        wiki_dir=effective_wiki_dir,
1441:        wiki_dir=effective_wiki_dir,
1478:        wiki_dir=effective_wiki_dir,
1511:            effective_wiki_dir / "log.md",
1517:    all_wiki_pages = load_all_pages(wiki_dir=effective_wiki_dir)
1522:        wiki_dir=effective_wiki_dir,
1543:                wiki_dir=effective_wiki_dir,
1558:                    log_path = effective_wiki_dir / "log.md"
1594:                    _persist_contradictions(contradiction_warnings, source_ref, effective_wiki_dir)
1630:            rebuild_vector_index(effective_wiki_dir)
```

Command:
```bash
grep -n "class ValidationError\|class IngestError" src/kb/errors.py
```

Output:
```text
37:class IngestError(KBError):
52:class ValidationError(KBError):
```

Command:
```bash
grep -n "from kb.errors import" src/kb/ingest/pipeline.py
```

Output:
```text
27:from kb.errors import IngestError, KBError, StorageError
```

Command:
```bash
grep -n "def build_extraction_prompt\|If a field cannot be determined\|<source_document>" src/kb/ingest/extractors.py
```

Output:
```text
29:# `<source_document>` / `</source_document>` tolerating case variants AND
72:    """Replace any <source_document> / </source_document> tag (tolerating
276:def build_extraction_prompt(content: str, template: dict, purpose: str | None = None) -> str:
279:    Cycle 3 M9: wrap raw source content in a ``<source_document>`` sentinel
296:    # M9: fence-escape — content must never close the outer <source_document>
319:If a field cannot be determined from the source, use null.
327:<source_document>
```

Command:
```bash
grep -n "^def test_\|inspect.getsource\|_query_wiki_body" tests/test_cycle5_hardening.py src/kb/query/engine.py
```

Output:
```text
tests/test_cycle5_hardening.py:29:def test_synthesis_prompt_uses_wikilink_citation_format():
tests/test_cycle5_hardening.py:38:    synthesis prompt lives in ``_query_wiki_body``; the public ``query_wiki``
tests/test_cycle5_hardening.py:44:    source = inspect.getsource(engine.query_wiki) + inspect.getsource(engine._query_wiki_body)
tests/test_cycle5_hardening.py:51:def test_extract_citations_parses_wikilink_format():
tests/test_cycle5_hardening.py:67:def test_extract_citations_still_parses_legacy_source_format():
tests/test_cycle5_hardening.py:82:def test_extract_citations_wikilink_unicode_path_pin():
tests/test_cycle5_hardening.py:100:def test_extract_citations_wikilink_raw_path_typed_as_raw():
tests/test_cycle5_hardening.py:114:def test_extract_entity_context_cjk_name_observed_behavior():
tests/test_cycle5_hardening.py:150:def test_validate_page_id_accepts_at_max_page_id_len(monkeypatch, tmp_path):
tests/test_cycle5_hardening.py:168:def test_validate_page_id_rejects_over_max_page_id_len(monkeypatch, tmp_path):
tests/test_cycle5_hardening.py:185:def test_validate_page_id_single_source_of_truth(monkeypatch, tmp_path):
tests/test_cycle5_hardening.py:214:def test_wrap_purpose_escapes_sentinel_closer():
tests/test_cycle5_hardening.py:243:def test_load_verdicts_logs_warning_on_corrupt_utf8(tmp_path, caplog):
tests/test_cycle5_hardening.py:266:def test_load_feedback_logs_warning_on_corrupt_json(tmp_path, caplog, monkeypatch):
tests/test_cycle5_hardening.py:289:def test_wrap_purpose_exact_byte_preservation():
tests/test_cycle5_hardening.py:309:def test_citation_pattern_compiles_after_widening():
tests/test_cycle5_hardening.py:318:def test_augment_proposer_prompt_wraps_purpose_in_sentinel():
tests/test_cycle5_hardening.py:341:def test_pytest_integration_marker_registered():
src/kb/query/engine.py:979:    Cycle 20 AC5 / AC7 — this thin outer wrapper around ``_query_wiki_body``
src/kb/query/engine.py:986:        return _query_wiki_body(
src/kb/query/engine.py:1000:def _query_wiki_body(
```

Command:
```bash
grep -n "^def test_\|tmp_kb_env\|tmp_wiki\|tmp_project" tests/conftest.py
```

Output:
```text
23:    "HASH_MANIFEST",  # cycle 18 AC1 — lives on kb.compile.compiler, not kb.config (see tmp_kb_env)
81:def tmp_wiki(tmp_path: Path) -> Path:
90:def tmp_project(tmp_path: Path) -> Path:
128:def tmp_kb_env(tmp_path: Path, monkeypatch) -> Path:
142:    module top before `tmp_kb_env` runs are NOT covered by the mirror-rebind
288:# Cycle 17 AC16 — `_kb_sandbox` is an alias for `tmp_kb_env` kept for the
289:# design-gate naming convention. New code should prefer `tmp_kb_env` (cycle 12).
290:_kb_sandbox = tmp_kb_env
299:            "concepts/rag", title="RAG", content="About RAG.", wiki_dir=tmp_wiki)
300:        page_path = create_wiki_page("entities/openai", page_type="entity", wiki_dir=tmp_wiki)
395:def tmp_captures_dir(tmp_project, monkeypatch):
401:    captures = tmp_project / "raw" / "captures"
403:    assert captures.resolve().is_relative_to(tmp_project.resolve()), (
404:        f"tmp_captures_dir escaped tmp_project: {captures} not under {tmp_project}"
426:def patch_all_kb_dir_bindings(monkeypatch, tmp_project):
432:    loudly rather than silently writing outside tmp_project.
437:    wiki = tmp_project / "wiki"
438:    raw = tmp_project / "raw"
481:    return tmp_project
```

Command:
```bash
grep -n "^- " BACKLOG.md | head -50
```

Output:
```text
19:- `module/file.py` `function_or_symbol` — description of the issue
24:- Lead with the file path (relative to `src/kb/`), then the function/symbol.
25:- Include line numbers only when they add precision (e.g. `file.py:273`).
26:- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
27:- One bullet = one issue. Don't combine unrelated problems.
28:- When resolving an item, delete it (don't strikethrough). Record the fix in CHANGELOG.md.
29:- Move resolved phases under "## Resolved Phases" with a one-line summary.
79:- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
82:- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes across existing pages. Every step is independently atomic, none reversible. A crash between manifest-write (step 6) and log-append (step 7) leaves the manifest claiming "already ingested" while the log shows nothing; a mid-wikilink-injection failure leaves partial retroactive backlinks. (R2)
85:- `compile/compiler.py` `compile_wiki(incremental=False)` — "full" compile rescans and re-ingests but does NOT: clear manifest (deleted sources linger until a dedicated prune branch runs); rebuild vector index; invalidate in-process `_index_cache` in `embeddings.py`; re-validate evidence trails / contradictions / injected wikilinks. A page corrupted by a half-finished ingest stays corrupt across `--full`. (R2)
88:- `graph/builder.py` no shared caching policy — cycle 6 added a query-side PageRank cache and preloaded-page threading for `kb_query`, and cycle 7 threaded page bundles through several callers, but the graph layer itself still has no reusable cache/invalidation contract. `lint/runner.py` and `lint/checks.py` can still rebuild graphs independently in one lint pass, and no policy doc defines when graph-derived caches are invalidated after ingest/refine. (R2; query hot-path portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
91:- `tests/test_v0p5_purpose.py` purpose-threading coverage gap — cycle 6 added `rewrite_query` tests that mock `call_llm` and reject leaked preambles, but `test_v0p5_purpose.py` still checks only that the string "KB FOCUS" appears in the extraction prompt; it never verifies `query_wiki` threads `purpose.md` to the synthesizer. Phase 5's `kb_capture` will follow this template if not corrected. (R3; rewriter coverage portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
94:- `tests/` coverage-visibility — ~50 of 94 files are named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py`. To verify `evolve/analyzer.py` has tier-budget coverage you must grep ~50 versioned files because canonical `test_evolve.py` has only 11 tests (none touch numeric tokens, redundant scans, or three-level break — all open in Phase 4.5 MEDIUM). `_compute_pagerank_scores` is searched across 25 files. (R3)
97:- `tests/` no end-to-end ingest→query workflow — grepping for `end_to_end`, `e2e`, `workflow`, `ingest_to_query` returns only single-module tests; no test chains `ingest_source` → `build_graph` → `search` → `query_wiki` against the same `tmp_wiki`. `test_phase4_audit_query.py::test_raw_fallback_truncates_first_oversized_section` mocks `search_raw_sources`, `search_pages`, AND `call_llm` — only the glue is exercised. The Phase 4.5 items about "page write vs evidence append", "manifest race", "index-file write order", "ingest fan-out" all describe failures BETWEEN steps; pure-unit tests cannot catch them. (R3)
100:- `tests/conftest.py` `project_root` / `raw_dir` / `wiki_dir` leak surface — fixtures point at REAL `PROJECT_ROOT` and are documented as "read-only use" but nothing enforces it. `test_cli.py:61-63` proves the global-escape paths exist (multi-global monkeypatch). Phase 4.5 already flagged `WIKI_CONTRADICTIONS` leaking, `load_purpose()` reading the real file, `append_wiki_log` defaulting to production. Phase 5 will add `wiki/hot.md`, `wiki/overview.md`, `wiki/_schema.md`, `raw/captures/` — one more leak surface each. (R3; cycle 7 only added autouse embeddings reset)
103:- `mcp/__init__.py:4` + `mcp_server.py:10` — FastMCP `run()` eagerly imports `core, browse, health, quality`; those pull `kb.query.engine` → `kb.utils.llm` → `anthropic` (548 modules, 0.58s), and `kb.mcp.health` pulls `kb.graph.export` → `networkx` (285 modules, 0.23s). Measured cold MCP boot: 1.83s / +89 MB / 2,433 modules — of which ~0.8s / ~35 MB is unnecessary for sessions using only `kb_read_page`/`kb_list_pages`/`kb_save_source`. (R3)
106:- `query/embeddings.py` `_get_model` (~32-41) cold load — measured 0.81s + 67 MB RSS delta for `potion-base-8M` on first `kb_query` that touches vector search. `engine.py:87` gates on `vec_path.exists()` — per R2, vector index is almost always stale/absent so the model load is skipped AND hybrid silently degrades to BM25. Either outcome hurts: if the index exists we pay 0.8s on first user query; if it doesn't, "hybrid" is a lie. (R3)
109:- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. A `kb_query(use_api=True)` (30s+), `kb_lint()` (multi-second disk walk), `kb_compile()` (minutes), or `kb_ingest_content(use_api=True)` (10+s) each hold a thread; under concurrent tool calls the pool saturates and subsequent calls queue. Claude Code often fires multiple tool calls in parallel; this turns invisible latency spikes into observed user-facing stalls. (R3; cycle 7 did not address)
112:- `compile/compiler.py:367-380` `compile_wiki` full-mode manifest pruning — `stale_keys` filter uses `raw_dir.parent / k` to check `.exists()`, but `raw_dir.parent` is NOT the project root when a caller passes a non-default `raw_dir` — every entry gets pruned. The prune also runs on `current_manifest` AFTER the per-source loop wrote successful hashes; between the two `load_manifest` calls there's no lock, so a concurrent `kb_ingest` adding a manifest entry in the window gets silently deleted on save. (R4)
115:- `compile/compiler.py:343-347` `compile_wiki` manifest write — after a successful `ingest_source`, the code does `load_manifest → manifest[rel_path] = pre_hash → save_manifest`. But `ingest_source` itself writes `manifest[source_ref] = source_hash` via `kb.ingest.pipeline:687` using its own path resolution. Two code paths write the same key with potentially different normalization (`source_ref` via `make_source_ref` vs `_canonical_rel_path`). Windows case differences or `raw_dir` overrides produce two divergent keys for the same file — `find_changed_sources` sees it as "new" and re-extracts. (R4)
118:- `compile/linker.py:178-241` `inject_wikilinks` cascade-call write race — `ingest_source` calls `inject_wikilinks` once per newly-created page (`pipeline.py:714-721`). For an ingest creating 50 entities + 50 concepts = 100 sequential calls in one process. Each iterates ALL wiki pages, reads each, may rewrite each via `atomic_text_write`. NO file lock. Concurrent ingest_source from another caller is identically iterating and rewriting the SAME pages. Caller A reads page X, caller B reads page X, A writes "X with link to A", B writes "X with link to B" — only B's wikilink survives. The retroactive-link guarantee silently fails under concurrent ingest. Compounds R4 overlapping-title (intra-process); R5 is the cross-process write-write race on the SAME page. (R5)
121:- `ingest/pipeline.py:603,715-721,729-754` lock acquisition order risk between same-ingest stages — within one `ingest_source`: stage 1 writes summary page (line 609) → `append_evidence_trail` to SAME page; stage 2 calls `_update_existing_page` on each entity (re-reads + re-writes); stage 9 `inject_wikilinks` re-reads + re-writes some of the SAME pages it just wrote in stages 1-3; stage 11 writes `wiki/contradictions.md`. None use `file_lock`. Within ONE process this is OK. Under concurrent ingest A + B, the read-then-write windows in different stages of A overlap with different stages of B in non-deterministic order; debugging becomes impossible because each `kb_ingest` run shows different conflict patterns. R5 highlights the **systemic absence of any locking discipline across the entire 11-stage ingest pipeline** — a problem that compounds with every Phase 5 feature. (R5)
128:- `query/embeddings.py` vector-index lifecycle — Phase 4.5 HIGH cycle 1 shipped H17 hybrid (mtime-gated rebuild + batch skip), but deferred: (1) atomic temp-DB-then-replace rebuild (crash-mid-rebuild leaves empty index), (2) cold-load latency (0.8s+67MB on first query), (3) dim-mismatch (stored embedding dim vs current model not validated), (4) `_index_cache` cross-thread lock symmetry. Bundle into dedicated vector-index lifecycle cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*
130:- `tests/` multiprocessing tests for cross-process `file_lock` semantics — cycle 1 HIGH used in-process threading as a proxy but Windows NTFS lock behavior is not exercised. Add `@pytest.mark.slow` multiprocessing tests in a dedicated test-infrastructure cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*
140:- `models/page.py` dataclasses are dead — `WikiPage` / `RawSource` exist but nothing returns them; `load_all_pages` / `ingest_source` / `query_wiki` each return ad-hoc dicts. "What is a page?" has ≥4 answers (dict, `Post`, `Path`, markdown blob); chunk indexing in Phase 5 will fork it again. (R1)
143:- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
146:- `compile/compiler.py` `compile_wiki` (~320-380) — per-source loop saves manifest after ingest but does not roll back wiki writes if a later manifest save fails; failure-recording branch swallows nested exceptions with a warning; final `append_wiki_log` runs even on partial failure. (R1)
149:- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write (acquire `.lock`, load full list, serialize, `mkstemp` + `fdopen` + `replace`, release). `file_lock` polls at 50 ms, adding minimum-latency floor on every verdict add. (R1)
152:- `lint/fetcher.py` `diskcache==5.6.3` — CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE in diskcache cache files. No patched upstream version as of 2026-04-21 (Re-checked 2026-04-21 per cycle-20 AC21: `pip index versions diskcache` shows 5.6.3 = LATEST; `pip-audit` reports empty `fix_versions` for the CVE).
155:- `src/kb/lint/augment.py::_post_ingest_quality` — AC17-drop rationale for future reference: cache-invalidation work was reconsidered and DROPPED. Cycle-13 AC2 intentionally uses uncached `frontmatter.load` to avoid FAT32/OneDrive/SMB coarse-mtime holes. Do not re-open without a concrete failure case.
157:- `compile/linker.py` cross-reference auto-linking — deferred: when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` added to A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`.
159:- `compile/publish.py` compile-time auto-publish hook — deferred: hook `kb publish` into `compile_wiki` so every compile auto-emits the Tier-1 + sibling + sitemap outputs. Cycle 16 shipped the sibling + sitemap BUILDERS standalone; the auto-hook into compile remains deferred pending a dedicated cycle.
161:- `compile/publish.py` manifest-based incremental sibling cleanup — deferred from cycle 16 Q2/C3 resolution: cycle 16 cleanup is O(|excluded|) unconditional unlinks per publish. When N(retracted) exceeds ~1000 a `.data/publish-siblings-manifest.json` atomic-state approach becomes preferable; defer until retracted-page counts warrant.
163:- `ingest/pipeline.py` index-file write order (~653-700) — per ingest: `index.md` → `_sources.md` → manifest → `log.md` → `contradictions.md`. A crash between `_sources.md` and manifest writes can duplicate entries on re-ingest. (R2)
166:- `ingest/pipeline.py` observability — one `ingest_source` emits to `wiki/log.md` (step 7) + Python `logger.warning` (frontmatter parse failures, manifest failures, contradiction warnings, wikilink-injection failures, 8+ sites) + `wiki/contradictions.md` + N evidence-trail appends. No correlation ID connects them. `wiki/log.md` records intent ("3 created, 2 updated"), not outcome. Debugging a flaky ingest requires correlating stderr against `wiki/log.md` against `contradictions.md` by timestamp window. (R2)
169:- `ingest/pipeline.py` + `ingest/evidence.py` page write vs evidence append (~150-151, 362-365) — `_write_wiki_page` and `_update_existing_page` perform atomic page write, then call `append_evidence_trail` which does its own read+write+atomic-rename. If the second call fails (disk full, permission flap, lock contention), the page has a new source reference with no evidence entry explaining why. Phase 4's provenance guarantee is conditional. (R2)
172:- CLI ↔ MCP parity — `cli.py` exposes 6 commands; MCP exposes 25. Operational tasks (view trends, audit a verdict, refine a page, read a page, search, stats, list pages/sources, graph viz, drift, save source, create page, affected pages, reliability map, feedback) require an MCP-speaking client. Tests cannot piggyback on CLI invocation; debugging in CI / cron is by `python -c` only. (R2)
175:- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. MCP `kb_compile` and `kb compile` CLI are cosmetic wrappers. Phase 5's two-phase compile / pre-publish gate / cross-source merging would land in the wrong layer because `compile_wiki` has no batch context. (R2)
178:- `tests/` no golden-file / snapshot tests — grep for `snapshot`/`golden`/`syrupy`/`inline_snapshot`/`approvaltests` returns zero hits. Wiki rendering (`_build_summary_content`, `append_evidence_trail`, contradictions append, `build_extraction_prompt`, `_render_sources`, Mermaid export, lint report) is verified only by `assert "X" in output`. `test_v0917_evidence_trail.py` checks `"## Evidence Trail" in text` — the actual format (order of `date | source | action`, prepend direction, whitespace) is unverified. Phase 5's output-format polymorphism (`kb_query --format=marp|html|chart|jupyter`), `wiki/overview.md`, and `wiki/_schema.md` all produce structured output that LLM-prompt tweaks silently reformat. (R3)
181:- `tests/` thin MCP tool coverage — of 25 tools, `kb_compile_scan`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`, plus the entire `health.py` cluster each have 1-2 assertion smoke tests. Deeply-tested tools (`kb_query`, `kb_ingest`, `kb_refine_page`) accumulated coverage organically across version files. Phase 4.5 flags `kb_graph_viz` `export_mermaid` non-deterministic tie-break and `kb_detect_drift` happy-path-only, both unprotected by per-tool test. (R3)
184:- `tests/test_phase4_audit_concurrency.py` single-process file_lock coverage — `test_file_lock_basic_mutual_exclusion` spawns threads, never `multiprocessing.Process` / `subprocess.Popen`. Phase 4.5 R2 flags `file_lock` PID-liveness broken on Windows (PIDs recycled, `os.kill(pid, 0)` succeeds for unrelated process); threads share PID so this is structurally impossible to surface with the current test. Manifest race, evidence-trail RMW race, contradictions append race, feedback eviction race all involve separate processes — autoresearch loop, file watcher, SessionStart hook (Phase 5) all run in separate processes alongside MCP. (R3)
187:- `ingest/pipeline.py:712-721` `ingest_source` inject_wikilinks per-page loop — for each newly-created entity/concept page, `inject_wikilinks` is called independently, each time re-scanning ALL wiki pages from disk via `scan_wiki_pages` + per-page `read_text`. A single ingest creating 50 entities + 50 concepts = 100 `inject_wikilinks` calls × N pages = 100·N disk reads. At 5k pages that's 500k reads per ingest — worse than R2-flagged graph/load double-scan. (R4)
190:- `ingest/pipeline.py:682-693 + compile/compiler.py:117-196` manifest hash key inconsistency under concurrent ingest — `_is_duplicate_content` (102) calls `load_manifest` to check whether ANY entry matches `source_hash`. If caller A is mid-ingest of `raw/articles/foo.md` (passed dedup at 566 but not yet written manifest at 688), caller B starts ingest of an IDENTICAL-content `raw/articles/foo-copy.md` — B's `_is_duplicate_content` sees no match (A hasn't saved), B proceeds to full extraction + page writes, BOTH succeed and write to manifest. Wiki now has TWO summary pages with identical content but different titles. R2 flagged the duplicate-check race; R5 specifies the **window**: the entire LLM extraction (~30 seconds) + all 11 ingest stages between dedup-check and manifest-save is unprotected. (R5)
238:- `kb_consolidate` sleep-cycle pass — high effort; overlaps with existing lint/evolve; defer until lint is load-bearing.
239:- Hermes-style independent cross-family supervisor — infra-heavy (second provider + fail-open policy); Phase 6.
240:- `kb_drift_audit` cold re-ingest diff — defer until `kb_merge` + `belief_state` land (surface overlap).
241:- `kb_synthesize [t1, t2, t3]` k-topic combinatorial synthesis — speculative; defer until everyday retrieval is saturated.
242:- `kb_export_subset --format=voice` for mobile/voice LLMs — niche; defer until a second-device use case emerges.
243:- Multi-agent swarm + YYYYMMDDNN naming + capability tokens (redmizt) — team-scale pattern; explicit single-user non-goal.
244:- RDF/OWL/SPARQL native storage — markdown + frontmatter + wikilinks cover the semantic surface.
```

## Task list (one commit per TASK; batch-by-file)

TASK 1: pipeline.py wiki-path guard
  Files: src/kb/ingest/pipeline.py:27, src/kb/ingest/pipeline.py:1077, src/kb/ingest/pipeline.py:1164, src/kb/ingest/pipeline.py:1165, src/kb/ingest/pipeline.py:1167, src/kb/ingest/pipeline.py:1208, src/kb/ingest/pipeline.py:1222, src/kb/errors.py:52
  Change:
  - Extend the import at src/kb/ingest/pipeline.py:27 from `from kb.errors import IngestError, KBError, StorageError` to include `ValidationError`.
  - Inside `ingest_source` at src/kb/ingest/pipeline.py:1077, keep `source_path = Path(source_path).resolve()` as the first source normalization point.
  - Leave the raw-dir sibling guard at src/kb/ingest/pipeline.py:1164-1167 unchanged; it continues to raise `ValueError`.
  - Immediately after `effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR` at src/kb/ingest/pipeline.py:1208, add a resolved/normcase wiki guard before src/kb/ingest/pipeline.py:1222.
  - Guard algorithm: `wiki_dir_nc = Path(os.path.normcase(str(effective_wiki_dir.resolve())))`; reuse `source_path_nc = Path(os.path.normcase(str(source_path)))` or recompute after source resolution; reject when `source_path_nc.relative_to(wiki_dir_nc)` succeeds.
  - Raise `ValidationError("Source path must not resolve inside wiki/ directory")` with no absolute path interpolation.
  - Ensure the guard executes before `_emit_ingest_jsonl("start", ...)` at src/kb/ingest/pipeline.py:1222.
  Test: Assertions land in `tests/test_cycle22_wiki_guard_grounding.py` from TASK 3. Before this change, a source physically under wiki/ or a symlink resolving into wiki/ reaches ingest start and either emits a start JSONL row or proceeds toward extraction instead of raising `ValidationError`.
  Criteria: AC1, AC2, AC3, AC4
  Threat: T1, T2, T3, T4

TASK 2: extractors.py grounding clause
  Files: src/kb/ingest/extractors.py:276, src/kb/ingest/extractors.py:319, src/kb/ingest/extractors.py:327
  Change:
  - In `build_extraction_prompt` at src/kb/ingest/extractors.py:276, update the prompt template text.
  - Insert the exact sentence `Ground every extracted field in verbatim source content. When uncertain whether a claim is in the source, use null.` immediately after src/kb/ingest/extractors.py:319.
  - Keep the new clause before the `<source_document>` fence at src/kb/ingest/extractors.py:327.
  - Do not add schema fields, confidence fields, or LLM-output compliance assertions in production code; this cycle only changes the advisory prompt text.
  Test: Assertions land in `tests/test_cycle22_wiki_guard_grounding.py` from TASK 3. Before this change, `build_extraction_prompt(...)` does not contain the exact grounding sentence, so the clause-presence assertion fails; if inserted after the source fence, the ordering assertion `clause_idx < fence_idx` fails.
  Criteria: AC5, AC6
  Threat: T5, T6

TASK 3: new test file regression pins
  Files: tests/test_cycle22_wiki_guard_grounding.py (new), tests/conftest.py:81, tests/conftest.py:90, tests/conftest.py:128, src/kb/ingest/pipeline.py:1208, src/kb/ingest/pipeline.py:1222, src/kb/ingest/extractors.py:319, src/kb/ingest/extractors.py:327, src/kb/errors.py:52
  Change:
  - Add `tests/test_cycle22_wiki_guard_grounding.py`.
  - Use existing fixtures from tests/conftest.py:81 (`tmp_wiki`), tests/conftest.py:90 (`tmp_project`), and tests/conftest.py:128 (`tmp_kb_env`) instead of writing to real repo paths.
  - Add AC10 test: a source path under effective wiki/ raises `kb.errors.ValidationError` and the message equals `Source path must not resolve inside wiki/ directory` without leaking the absolute source path.
  - AC10 also verifies `.data/ingest_log.jsonl` has zero rows for the rejected request, pinning that src/kb/ingest/pipeline.py:1222 was not reached.
  - Add AC11 symlink test: create a source-shaped path outside wiki/ that is an `os.symlink` to a wiki-inward file; skip only when symlink creation is unavailable; expect `ValidationError`.
  - Add AC12 Windows case test: build a mixed-case spelling of the wiki path and assert the normcase guard still rejects. On case-sensitive/non-Windows filesystems, make the test non-vacuous by asserting the path exists before using it or skip with an explicit reason if a mixed-case alias cannot exist.
  - Add AC13 prompt-order test: call `build_extraction_prompt`, assert the exact grounding clause is present, assert `<source_document>` is present, and assert `prompt.index(clause) < prompt.index("<source_document>")`.
  Test: These tests fail before TASK 1/TASK 2. AC10-AC12 fail because no wiki-path guard exists after src/kb/ingest/pipeline.py:1208 and before src/kb/ingest/pipeline.py:1222. AC13 fails because the exact clause is absent after src/kb/ingest/extractors.py:319 and before src/kb/ingest/extractors.py:327.
  Criteria: AC10, AC11, AC12, AC13
  Threat: T1, T2, T3, T4, T5, T6

TASK 4: inspect.getsource test replacement
  Files: tests/test_cycle5_hardening.py:29, tests/test_cycle5_hardening.py:38, tests/test_cycle5_hardening.py:44, src/kb/query/engine.py:979, src/kb/query/engine.py:986, src/kb/query/engine.py:1000, tests/conftest.py:81, tests/conftest.py:90, tests/conftest.py:128
  Change:
  - Replace `test_synthesis_prompt_uses_wikilink_citation_format` at tests/test_cycle5_hardening.py:29.
  - Delete the source-inspection pattern at tests/test_cycle5_hardening.py:44: `inspect.getsource(engine.query_wiki) + inspect.getsource(engine._query_wiki_body)`.
  - Keep the test intent from tests/test_cycle5_hardening.py:38, but verify runtime behavior through `query_wiki` rather than the source layout around src/kb/query/engine.py:979, src/kb/query/engine.py:986, and src/kb/query/engine.py:1000.
  - Build a minimal wiki fixture with tests/conftest.py:81/90/128 fixtures.
  - Define a spy for `call_llm` that records prompt arguments and returns a deterministic synthesis response.
  - Patch the module attribute exactly with `monkeypatch.setattr("kb.query.engine.call_llm", spy)`.
  - Call `query_wiki(...)` through production flow.
  - Assert `spy.call_count >= 1` unconditionally.
  - Assert at least one captured prompt contains the canonical `[[page_id]]` citation instruction substring that the old test tried to pin.
  - Assert NO captured prompt contains the legacy `[source: page_id]` instruction (pairs the positive + negative assertions from the original `inspect.getsource` test — Step 08 plan-gate AC8 gap close).
  Test: Before this change, the old test can pass after a runtime regression because it inspects function source instead of the LLM boundary. The new spy test fails before/fails on revert if `query_wiki` stops sending the wikilink citation instruction to `kb.query.engine.call_llm`, if the spy target is patched at the wrong module, or if the spy is never called, or if the legacy `[source: page_id]` instruction leaks back into the synthesis prompt.
  Criteria: AC7, AC8, AC9
  Threat: T8, T9
  Scope-out note: Threat-model items T7 (MCP error-string contract drift) and T10 (MCP happy-path-only coverage) are explicitly N/A for cycle 22 — Group D was dropped at Step 04 after R2 Codex grep confirmed `tests/test_cycle17_mcp_tool_coverage.py` already covers all four tools (kb_compile_scan, kb_graph_viz, kb_verdict_trends, kb_detect_drift) with both happy-path and error-string assertions. Deletion of the Phase 4.5 MEDIUM "thin MCP tool coverage" BACKLOG entry at BACKLOG.md:181 is the in-cycle closure evidence.

TASK 5: doc updates
  Files: BACKLOG.md:91, BACKLOG.md:112, BACKLOG.md:115, BACKLOG.md:118, BACKLOG.md:140, BACKLOG.md:163, BACKLOG.md:166, BACKLOG.md:181, BACKLOG.md:187, BACKLOG.md:190, CHANGELOG.md:17, CHANGELOG.md:19, CHANGELOG.md:23, CHANGELOG.md:56, CLAUDE.md:33, CLAUDE.md:180
  Change:
  - Delete exactly these 10 stale BACKLOG.md bullet entries from the mandatory grep-7 output: BACKLOG.md:91, BACKLOG.md:112, BACKLOG.md:115, BACKLOG.md:118, BACKLOG.md:140, BACKLOG.md:163, BACKLOG.md:166, BACKLOG.md:181, BACKLOG.md:187, BACKLOG.md:190.
  - For BACKLOG.md:91, cite closure by `tests/test_v0p5_purpose.py:97` (`test_cycle17_ac14_query_wiki_threads_purpose_to_synthesis_prompt`) in CHANGELOG.
  - For BACKLOG.md:112, cite cycle-17 prune-base coverage plus the cycle-19 anchor: `tests/test_cycle17_compile_manifest.py` and `tests/test_cycle19_prune_base_consistency_anchor.py`.
  - For BACKLOG.md:115 and BACKLOG.md:190, cite closure by `tests/test_cycle19_manifest_key_consistency.py` (`manifest_key_for`, keyword-only `manifest_key=`, and dual write threading).
  - For BACKLOG.md:118 and BACKLOG.md:187, cite closure by `tests/test_cycle19_inject_wikilinks_batch.py` and `tests/test_cycle19_inject_batch_e2e.py`.
  - For BACKLOG.md:140, cite closure by `tests/test_cycle17_models_dead_code.py` documenting the keep-and-document decision for `WikiPage` / `RawSource`.
  - For BACKLOG.md:163 and BACKLOG.md:166, cite closure by `tests/test_cycle18_ingest_observability.py` and the cycle-18 `_write_index_files` / JSONL observability work.
  - For BACKLOG.md:181, cite closure by `tests/test_cycle17_mcp_tool_coverage.py`.
  - Add a Cycle 22 entry under CHANGELOG.md:56 or a new `#### Phase 4.5 — cycle 22 (2026-04-22)` section near CHANGELOG.md:56; update the Quick Reference at CHANGELOG.md:19/23 with the post-cycle count.
  - Update both stale CLAUDE.md test-count locations atomically: CLAUDE.md:33 and CLAUDE.md:180.
  - Before editing CLAUDE.md counts, run full collection after code/test changes and use the exact result in both locations; do not carry forward the stale `2710 passed + 8 skipped (cycle 21; 2718 collected)` or `2689 passed + 8 skipped; 2697 collected` text.
  Test: Documentation verification is grep-based. Before this task, `grep -n "2710 passed\|2718 collected\|2689 passed\|2697 collected" CLAUDE.md` finds stale counts at CLAUDE.md:33 and CLAUDE.md:180, and grep-7 still shows stale BACKLOG bullets at the 10 listed line numbers.
  Criteria: AC14
  Threat: T3, T4, T8, T9

## Commit order
1. TASK 1: pipeline.py guard
2. TASK 2: extractors.py grounding clause
3. TASK 3: new test file regression pins
4. TASK 4: inspect.getsource test replacement
5. TASK 5: doc updates (single commit)
Reasoning: production code before its regression tests; also note where batch-by-file rule allows test+prod in same commit. TASK 1 and TASK 3 may be batched by file group if the implementation policy requires every red test to land with the production guard, and TASK 2 and the AC13 portion of TASK 3 may likewise be batched. Keep TASK 5 as the single docs commit so BACKLOG deletion, CHANGELOG closure notes, and both CLAUDE.md count updates stay atomic.

## Risks + mitigations

Risk: Wiki guard accidentally blocks legitimate raw sources because of a bad containment comparison.
Mitigation: Compare resolved/normcased `source_path` only against resolved/normcased `effective_wiki_dir`, and keep the existing raw-dir sibling guard unchanged at src/kb/ingest/pipeline.py:1164-1167.

Risk: ValidationError import changes exception taxonomy in a way callers do not expect.
Mitigation: Use `ValidationError` only for the new wiki-path failure mode and leave the raw-dir guard on `ValueError`. Add the caller-grep checkpoint during implementation review for `except ValueError` around `ingest_source`.

Risk: Absolute paths leak through the new rejection.
Mitigation: Use the fixed message `Source path must not resolve inside wiki/ directory`; test that `str(source_path)` and `str(wiki_dir)` are absent from `str(exc.value)`.

Risk: Rejected ingest emits an orphan JSONL `start` row.
Mitigation: Place the guard before src/kb/ingest/pipeline.py:1222 and test zero JSONL rows for the rejected request.

Risk: Symlink and Windows-case tests become vacuous on platforms without symlink privileges or case-insensitive aliases.
Mitigation: For symlink, skip only on explicit symlink creation failure. For mixed-case, assert the mixed-case fixture exists before using it or skip with a platform-specific reason.

Risk: Grounding clause is inserted after the untrusted source fence.
Mitigation: Test `clause_idx < fence_idx` against `build_extraction_prompt`.

Risk: The replacement query test patches the wrong symbol and never exercises the LLM boundary.
Mitigation: Patch `kb.query.engine.call_llm` exactly, assert `spy.call_count >= 1`, and inspect captured prompt arguments only after the call.

Risk: BACKLOG deletions lose provenance.
Mitigation: Every deleted BACKLOG line listed in TASK 5 gets a CHANGELOG closure note naming the closing test file/function or cycle commit evidence.

Risk: CLAUDE.md test-count drift persists.
Mitigation: Update CLAUDE.md:33 and CLAUDE.md:180 in the same docs commit using the post-implementation `pytest --collect-only` count, then grep for old count fragments.

## Effort estimate per task

TASK 1: ~8-14 LOC, 20-30 minutes. Most work is placement and exact exception/message behavior.

TASK 2: ~1 LOC, 5-10 minutes. Main risk is preserving prompt ordering.

TASK 3: ~90-140 LOC, 60-90 minutes. Symlink and mixed-case fixtures are the time sink.

TASK 4: ~35-70 LOC net churn, 45-75 minutes. Requires a minimal query fixture that reaches `call_llm` without brittle source inspection.

TASK 5: ~25-60 doc LOC net churn, 30-60 minutes plus test collection time. Keep all doc edits in one commit after the exact suite count is known.
