# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Principles

*(Adapted from [Karpathy's LLM coding observations](https://x.com/karpathy/status/2015883857489522876). Bias toward caution over speed on non-trivial work. For a one-line typo fix, use judgment.)*

**Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**Goal-Driven Execution.** Transform imperative tasks into verifiable goals:
- "Fix the bug" → *"Write a failing test that reproduces it, then make it pass."*
- "Add validation" → *"Write tests for invalid inputs, then make them pass."*
- "Refactor X" → *"Ensure tests pass before and after."*
- For multi-step work, state the plan as `[step] → verify: [check]` — then loop.

**Two tests before declaring done:**
1. *Every changed line should trace directly to the request.* Drop drive-by edits.
2. *Would a senior engineer say this is overcomplicated?* If yes, simplify.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Implementation Status

Current shipped phases and per-cycle tallies live in `CHANGELOG.md` (brief compact index, newest first; full per-cycle detail in `CHANGELOG-history.md`). Latest full-suite count: 2825 tests across 247 test files; last full run was 2815 passed + 10 skipped (cycle 29 — `rebuild_indexes` hardening: AC1 compound `_audit_token(block)` helper renders `cleared (warn: <error>)` on partial vector clears + mirrored to `kb rebuild-indexes` CLI stdout, AC2 shared `_validate_path_under_project_root(path, field_name)` dual-anchor containment applied to `hash_manifest` + `vector_db` overrides — closes cycle-28 R2+R3 Codex BACKLOG adds; + AC3 `CAPTURES_DIR` carve-out comment mirroring CLAUDE.md §raw/ + AC4/AC5 BACKLOG hygiene deleting stale `_PROMPT_TEMPLATE` and Phase 4.5 HIGH #6 cold-load bullets — shipped in cycles 19/26/28 respectively). Open work and deferred-feature roadmap live in `BACKLOG.md`.

### Module Map (`src/kb/`)

- **Core (Phase 1):** `config`, `models`, `utils`, `ingest`, `compile`, `query`, `lint`, `evolve`, `graph`, `mcp` (split package: `app`, `core`, `browse`, `health`, `quality`), `mcp_server` (entry shim), CLI (10 commands: `ingest`, `compile`, `query`, `lint`, `evolve`, `publish`, `mcp`, `refine-sweep`, `refine-list-stale`, `rebuild-indexes`).
- **Publish (Phase 5, cycles 14-16):** `compile.publish` — five builders for Karpathy Tier-1 machine-consumable outputs: `build_llms_txt`, `build_llms_full_txt`, `build_graph_jsonld` (cycle 14), plus `build_per_page_siblings` (cycle 16 — emits `{out_dir}/pages/{page_id}.{txt,json}` with deterministic `sort_keys=True` JSON and unconditional stale-sibling cleanup before incremental skip), and `build_sitemap_xml` (cycle 16 — `sitemap.org/0.9` schema via `xml.etree.ElementTree`, relative POSIX `<loc>`). JSON-LD uses schema.org `@context`; every builder filters pages with `belief_state in {retracted, contradicted}` OR `confidence == speculative`. Builders write via `atomic_text_write` and accept `incremental: bool = False`; `kb publish --format={llms|llms-full|graph|siblings|sitemap|all}` defaults to `--incremental` and also exposes `--no-incremental`. First post-upgrade publish should use `--no-incremental` so pre-cycle-14 outputs are regenerated under the current epistemic filter. Signature convention: single-file builders take a full `out_path`; multi-file `build_per_page_siblings` takes a base `out_dir` and derives child paths internally.
- **Quality (Phase 2):** `feedback` (weighted Bayesian trust — "wrong" penalized 2× vs "incomplete"), `review` (pairing, refiner with audit trail), `lint.semantic` (fidelity / consistency / completeness builders), `lint.verdicts` (persistent verdict store), `.claude/agents/wiki-reviewer.md` (Actor-Critic agent).
- **Capture (Phase 5):** `capture` — conversation/notes atomization for `raw/captures/`.
- **Output adapters (Phase 4.11):** `query.formats` — `markdown`, `marp`, `html`, `chart`, `jupyter`. Files land at `PROJECT_ROOT/outputs/{ts}-{slug}.{ext}` with provenance frontmatter. Outputs directory is **OUTSIDE** `wiki/` (gitignored) to prevent search-index poisoning. `kb_query(output_format=...)` requires `use_api=True`. Chart adapter emits a static Python script + JSON sidecar — matplotlib is NOT a kb runtime dependency.
- **Augment (Phase 5.0):** `lint.fetcher` (DNS-rebind-safe HTTP via `SafeTransport`, allowlists + secret scan + trafilatura + robots.txt). `lint.augment` (three-gate: propose → execute → auto_ingest; G1-G7 eligibility; LLM proposer with abstain; Wikipedia fallback; relevance gate; `[!gap]` callout). `lint._augment_manifest` (atomic JSON state machine). `lint._augment_rate` (file-locked sliding-window: 10/run + 60/hour + 3/host/hour).
- **Phase 3+ research (200+ pages):** DSPy Teacher-Student, RAGAS, Reweave — see `research/agent-architecture-research.md`.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup
cp .env.example .env          # then fill in:
# ANTHROPIC_API_KEY (optional for Claude Code/MCP mode; required for direct API-backed flows), FIRECRAWL_API_KEY (optional), OPENAI_API_KEY (optional)
# Optional: override project root detection
export KB_PROJECT_ROOT=/path/to/your/kb    # heuristic + walk-up fallback if unset

# Install deps + editable package (enables `kb` CLI command)
# NOTE: `pip install -e .` must be run before `kb` CLI or `from kb import ...` works outside pytest
pip install -r requirements.txt && pip install -e .

# Run all tests
python -m pytest

# Run single test
python -m pytest tests/test_models.py::test_extract_wikilinks -v

# Lint, auto-fix, & format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/

# CLI (after pip install -e .)
kb --version
kb ingest raw/articles/example.md --type article
kb compile [--full]
kb query "What is compile-not-retrieve?"
kb lint [--fix]
kb evolve
kb publish [--out-dir PATH] [--format llms|llms-full|graph|all] [--incremental/--no-incremental]   # /llms.txt + /llms-full.txt + /graph.jsonld
kb rebuild-indexes [--wiki-dir PATH] [--yes]   # wipe manifest + vector DB + LRU caches
kb mcp                        # Start MCP server for Claude Code

# Playwright browser (needed by crawl4ai)
python -m playwright install chromium
```

Ruff config: line length 100, Python 3.12+, rules E/F/I/W/UP (see `pyproject.toml`).

## Architecture

### Three-Layer Content Structure

- **`raw/`** — Immutable source documents. The LLM reads but **never modifies** files here (except raw/captures/, which is the sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest). Subdirs: `articles/`, `papers/`, `repos/`, `videos/`, `podcasts/`, `books/`, `datasets/`, `conversations/`, `assets/`. Use Obsidian Web Clipper for web→markdown; download images to `raw/assets/`.
- **`wiki/`** — LLM-generated and LLM-maintained markdown. Page subdirs: `entities/`, `concepts/`, `comparisons/`, `summaries/`, `synthesis/`. All pages use YAML frontmatter (see template below). Non-technical users can optionally install the [Remotely Save](https://github.com/remotely-save/remotely-save) Obsidian community plugin (Apache 2.0) to sync `wiki/` to S3, Azure Blob, OneDrive, or Dropbox — the pipeline writes to the bucket, Remotely Save pulls it into Obsidian automatically.
- **`research/`** — Human-authored analysis, project ideas, and meta-research about the knowledge base approach.

### Five Operations Cycle: Ingest → Compile → Query → Lint → Evolve

- **Ingest**: User adds source to `raw/`. LLM reads it, writes summary to `wiki/summaries/`, updates `wiki/index.md`, modifies relevant entity/concept pages, appends to `wiki/log.md`.
- **Compile**: LLM builds/updates interlinked wiki pages. Uses hash-based incremental detection — only processes new/changed sources. Manifest saved after each source (crash-safe). Proposes diffs, not full rewrites.
- **Query**: User asks questions. LLM searches wiki using BM25 ranking (term frequency saturation, IDF weighting, length normalization), synthesizes answers with inline citations to wiki pages and raw sources. Title tokens boosted by `SEARCH_TITLE_WEIGHT` (repeated N times before indexing). Context truncated to 80K chars. Good answers become new wiki pages.
- **Lint**: Health check — orphan pages, dead links, staleness, wikilink cycles, coverage gaps, frontmatter validation. Produces a report, does not silently fix.
- **Evolve**: Gap analysis — what topics lack coverage, what concepts should be linked, what raw sources would fill gaps. User picks suggestions, LLM executes.

### Python Package (`src/kb/`)

Entry point: `kb = "kb.cli:cli"` in `pyproject.toml`. Version in `src/kb/__init__.py`. MCP server entry: `python -m kb.mcp_server` or `kb mcp`. MCP package: `kb.mcp` (split from monolithic `mcp_server.py`).

All paths, model tiers, page types, and confidence levels are defined in `kb.config` — import from there, never hardcode. `PROJECT_ROOT` resolves from `config.py`'s location, so it works regardless of working directory.

**Key APIs** (non-obvious behavior — for full signatures, read the source):
- `call_llm(prompt, tier="write")` / `call_llm_json(prompt, tier, schema)` — In `kb.utils.llm`. Tiers: `scan` (Haiku), `write` (Sonnet), `orchestrate` (Opus). Routes to a CLI subprocess backend when `KB_LLM_BACKEND` is set (non-`"anthropic"` value); otherwise uses the Anthropic SDK path unchanged. `call_llm_json` uses forced tool_use on the Anthropic path for guaranteed structured JSON; on CLI backends, uses three-stage text extraction + `jsonschema.validate`. Raises `LLMError` on failure, `ValueError` on invalid tier. **Config helpers**: `get_cli_backend() -> str` (reads `KB_LLM_BACKEND` at call time; default `"anthropic"`; raises `ValueError` on unknown); `get_cli_model(tier) -> str` (respects `KB_CLI_MODEL_<TIER>` env override).
- `ingest_source(path, source_type=None, extraction=None, *, defer_small=False, wiki_dir=None)` — In `kb.ingest.pipeline`. Returns dict with `pages_created`, `pages_updated`, `pages_skipped`, `affected_pages`, `wikilinks_injected`, and `duplicate: True` on hash match. Pass `extraction` dict to skip LLM call (Claude Code mode). Pass `wiki_dir` to write to a custom wiki directory (default: `WIKI_DIR`). Raises `ValidationError` if `path` resolves inside the effective wiki directory — closes the circular-knowledge loop where LLM-generated pages could be re-ingested as raw sources (cycle 22 AC1-AC4; message contains no absolute path).
- `load_all_pages(wiki_dir=None)` / `scan_wiki_pages(wiki_dir=None)` / `page_id(page_path, wiki_dir=None)` — In `kb.utils.pages`. `load_all_pages` returns list of dicts. `page_id` lowercases IDs and preserves subdir separators; use the stored page `path` for filesystem I/O when case matters. **Gotcha**: `content_lower` field is pre-lowercased (for BM25), not verbatim. Cycle 14 AC23 adds an additive `status` key (empty string when absent).
- `save_page_frontmatter(path, post)` — In `kb.utils.pages`. Cycle 14 AC16 — the single enforcement point for key-order-preserving writes. Rigid contract: calls `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)`. USE THIS for any write-back that reads via `frontmatter.load` and needs to preserve metadata insertion order (Evidence Trail sentinel, downstream YAML-diff tools). The three augment write-back sites (`_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt` in `kb.lint.augment`) use this wrapper.
- `slugify(text)` / `yaml_escape(value)` — In `kb.utils.text`. Single source of truth — imported everywhere, never duplicate.
- `build_extraction_schema(template)` — In `kb.ingest.extractors`. Builds JSON Schema from template fields. `load_template()` is LRU-cached. Use `_build_schema_cached(source_type)` for cached schema lookups (avoids rebuilding on every extraction call).
- `query_wiki(question, wiki_dir=None, max_results=10, conversation_context=None, *, output_format=None)` — In `kb.query.engine`. Returns dict with keys:
  - `answer` (str) — synthesised answer
  - `citations` (list[dict]) — each with `type` (`'wiki'|'raw'`), `path` (str), `context` (str), and a `stale: bool` flag (cycle 4 item #27 doc-sync: surfaced alongside `search_pages` stale flagging so API callers can render `[STALE]` markers inline)
  - `source_pages` (list[str]) — page IDs retrieved before budget trimming
  - `context_pages` (list[str]) — page IDs whose body was packed into the LLM context; empty list on no-match
  - `output_path` + `output_format` — populated when `output_format` is non-text AND the Phase 4.11 adapter succeeded (cycle 4 item #27 doc-sync)
  - `output_error` — populated on adapter failure; absent on success or when `output_format` is empty/text
  `output_format` is keyword-only — additive, zero breakage to existing callers.
  Cycle 15 behavior: stale-result flagging composes source mtime with `decay_days_for(source, topics=...)`; summaries context budget uses `tier1_budget_for("wiki_pages")`; pages with `authored_by: human|hybrid` receive the mild `AUTHORED_BY_BOOST` after validation.
- `refine_page(page_id, content, notes)` — In `kb.review.refiner`. Uses regex-based frontmatter split (not YAML parser), rejects content that looks like a frontmatter block (`---\nkey: val\n---`) to prevent corruption.
- `rebuild_vector_index(wiki_dir, force=False)` — In `kb.query.embeddings`. Rebuilds sqlite-vec index from all pages in `wiki_dir`. Gated on (a) module-load-time `_hybrid_available` flag and (b) mtime check (skipped when `force=True`). Called at tail of `ingest_source()`. Batch callers (`compile_wiki`) pass `_skip_vector_rebuild=True` in loop and invoke once at tail. Cycle 24 AC5/AC6/AC8: rebuild writes to `<vec_db>.tmp` then `os.replace`-swaps; stale `.tmp` from crashed prior run unlinked unconditionally at entry; cached `VectorIndex._conn` closed BEFORE `os.replace` (Windows handle-release); on mid-build exception the tmp is unlinked and exception re-raised (clean-slate).
- `VectorIndex.build(entries, *, db_path: Path | None = None)` — In `kb.query.embeddings` (cycle 24 AC7). Keyword-only `db_path` override; when None (default) writes to `self.db_path` and updates `self._stored_dim`. When `db_path` is provided (used by `rebuild_vector_index` for tmp-then-replace) the build targets the override path WITHOUT mutating `self._stored_dim` so instance state stays coherent with its self-described DB.
- `append_evidence_trail(page_path, source_ref, action, entry_date=None)` — In `kb.ingest.evidence`. Cycle 24 AC14: sentinel search is SPAN-LIMITED within the FIRST `## Evidence Trail` section (header → next `^## ` heading or EOF). Attacker-planted `<!-- evidence-trail:begin -->` substrings in body, frontmatter, or other sections are inert. Header variants tolerate CRLF + trailing whitespace. Fallback matrix: (a) header + sentinel-in-span → insert after sentinel; (b) header + no-sentinel-in-span → sentinel-migration (plant at header end); (c) no header → fresh section at EOF with sentinel (body sentinel, if any, ignored and left in place).
- `render_initial_evidence_trail(source_ref, action, entry_date=None) -> str` — In `kb.ingest.evidence` (cycle 24 AC1). Used by `_write_wiki_page` to concatenate the initial `## Evidence Trail` section + sentinel + first entry INLINE into the first-write payload. Reuses `format_evidence_entry` for pipe neutralization. No separate `append_evidence_trail` call fires for new pages (eliminates the prior two-write race).
- `file_lock(path, timeout=None)` — In `kb.utils.io`. Cycle 24 AC9: exponential backoff across ALL THREE polling sites (normal `FileExistsError` retry, POSIX `ProcessLookupError` stale-steal, Windows `OSError` stale-steal). Floor `LOCK_INITIAL_POLL_INTERVAL = 0.01`, cap `LOCK_POLL_INTERVAL = 0.05`; both read at CALL TIME (module attribute lookup) so monkeypatching either constant steers the retry schedule. Exponent capped at `2**30` to defend against OverflowError under degenerate monkeypatch conditions. Monkeypatching `LOCK_POLL_INTERVAL = 0.001` clamps ALL observed sleeps to `<= 0.001` (CAP semantic).
- `get_dim_mismatch_count() -> int` — In `kb.query.embeddings` (cycle 25 AC4). Process-level counter of vector-index dim-mismatch events (stored dim vs query-vec dim). Incremented inside `VectorIndex.query` on EVERY mismatch query (not once-per-instance). Approximate under concurrent threads per Q8 — no lock around `+= 1`. Diagnostic only (not billing-grade telemetry). Companion to the existing `_dim_warned` sticky log gate which stays once-per-instance. Read-only: no reset helper (tests observe monotonic deltas).
- `maybe_warm_load_vector_model(wiki_dir: Path) -> threading.Thread | None` — In `kb.query.embeddings` (cycle 26 AC1). Spawns a daemon thread calling `_get_model()` when `_hybrid_available` AND `_vec_db_path(wiki_dir).exists()` AND `_model is None`. Returns the `Thread` so tests can `.join(timeout=...)`; production (`kb.mcp.__init__.main`) ignores the return. Returns `None` on any precondition failure (idempotent no-op). Daemon thread wraps `_get_model` via `_warm_load_target` which catches `Exception` + `logger.exception` — silent HF-Hub / network failures still produce structured log output (T6 mitigation). Single-spawn caveat: NOT locked against concurrent callers — T5 acceptance rests on the single-caller production invariant (CI-gate grep enforces).
- `get_vector_model_cold_load_count() -> int` — In `kb.query.embeddings` (cycle 26 AC4). Process-level counter of successful vector-model cold-loads (each `_get_model()` invocation that ran `StaticModel.from_pretrained`). Incremented INSIDE `_model_lock` — exact counts under concurrent threads (intentional asymmetry with cycle-25 `get_dim_mismatch_count` which is lock-free per Q8; documented in getter docstring). Cold-loads are low-rate (≤1 per process per model) so the lock cost is zero. Read-only; no reset helper. Paired with `maybe_warm_load_vector_model` to answer "did the warm-load fire AND complete?" in diagnostics.
- `_get_model` latency instrumentation (cycle 26 AC3): on every successful `StaticModel.from_pretrained` return, emits `logger.info("Vector model cold-loaded in %.2fs", elapsed)` plus — if `elapsed >= VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS = 0.3` — a WARNING nudging operators toward `maybe_warm_load_vector_model(wiki_dir)`. Post-success ordering (CONDITION 3): log + counter fire AFTER `_model = ...` assignment; on exception, `_model` stays `None`, no log fires, no counter increment — the next query re-attempts naturally. `kb.mcp.__init__.main()` calls `maybe_warm_load_vector_model(WIKI_DIR)` after `_register_all_tools()` and before `_mcp.run()` so long-lived MCP workers don't charge the cold-load cost to the FIRST user query. `kb compile` CLI is intentionally NOT warm-loaded (one-shot — the first ingest triggers the load naturally).
- `get_sqlite_vec_load_count() -> int` — In `kb.query.embeddings` (cycle 28 AC3). Process-level counter of successful sqlite-vec extension loads; incremented inside `VectorIndex._ensure_conn`'s `_conn_lock` span AFTER `self._conn = conn` (post-success ordering per CONDITION 4 — NEVER in `finally:`). Exact-per-instance because the enclosing lock is already held across the extension-load path; approximate across concurrent `VectorIndex` instances (each owns its own `_conn_lock`). Same locking posture as cycle-26 `get_vector_model_cold_load_count()`; contrast with cycle-25 lock-free `get_dim_mismatch_count()` (query-hot-path). Read-only; no reset helper. Paired with `_ensure_conn` latency-INFO log to answer "how many sqlite-vec extension loads has this process seen, and were any slow?" in diagnostics.
- `get_bm25_build_count() -> int` — In `kb.query.bm25` (cycle 28 AC5). Process-level counter of `BM25Index.__init__` constructor executions — NOT distinct cache insertions. Aggregates BOTH call sites in `engine.py:110` (wiki-page BM25 cache rebuilds) and `engine.py:794` (raw-source BM25 cache rebuilds). Lock-free per cycle-25 Q8 precedent (operator-diagnostic use tolerates undercount by ≤N under N concurrent cache-miss rebuilds); contrast with cycle-26 AC4 locked variant because `BM25Index.__init__` has no existing lock to piggy-back on (callers release their cache locks before constructing). Read-only; no reset helper. Diagnostic only (not billing-grade telemetry).
- `_ensure_conn` sqlite-vec latency instrumentation (cycle 28 AC1/AC2): on every successful first `_ensure_conn` call per `VectorIndex` instance, emits `logger.info("sqlite-vec extension loaded in %.3fs (db=%s)", elapsed, self.db_path)` plus — if `elapsed >= SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS = 0.3` — a WARNING suggesting warm-loading. Brackets the FULL extension-load block (`sqlite3.connect` through `enable_load_extension(False)`), not just `sqlite_vec.load(conn)`. Post-success ordering (CONDITIONS 4 + 9): log + counter fire AFTER `self._conn = conn` assignment inside the existing `_conn_lock` span; on exception (extension unavailable), `self._disabled = True`, no INFO/WARN fires, no counter increment, existing cycle-3 H7 failure WARNING preserved.
- `BM25Index.__init__` latency instrumentation (cycle 28 AC4): on every constructor call, emits `logger.info("BM25 index built in %.3fs (n_docs=%d)", elapsed, self.n_docs)` including the empty-corpus case (`n_docs=0` still emits — diagnostic floor per Q10/R2 finding 6). Brackets the full `__init__` body (corpus loop + avgdl + IDF pre-computation) per CONDITION 2. No WARN threshold (Q1 decision — corpus size variance defeats a fixed threshold; future cycle may revisit if operator feedback surfaces a canonical corpus size).
- `compile_wiki` manifest value states (cycle 25 AC6/AC7): three-valued, `{real_hash, "failed:{pre_hash}", "in_progress:{pre_hash}"}`. A `real_hash` (SHA256 hex or `_template_hashes()` output) means the last ingest succeeded. `failed:{pre_hash}` marks the last attempt raised a Python-level exception. `in_progress:{pre_hash}` is the pre-marker written before `ingest_source` runs and ONLY survives hard-kill / power-loss — the normal exception handler replaces it with `failed:`. On each `compile_wiki` invocation, an entry scan logs a warning for any surviving `in_progress:` values (operator remediates via `kb rebuild-indexes` or manual investigation). Concurrent `kb compile` invocations from another process may emit the warning for the OTHER process's in-flight work — this is expected noise per Q10 design decision (accept in favour of not adding a grace-window protocol).
- `inject_wikilinks_batch(new_pages, wiki_dir=None, *, pages=None) -> dict[str, list[str]]` — In `kb.compile.linker` (cycle 19 AC1). Batch variant of `inject_wikilinks` that scans each existing wiki page AT MOST ONCE per chunk via a combined alternation regex; pre-lock peek is candidate-gathering only and the winner is re-derived under per-page `file_lock` from FRESH body content (AC1b). Chunked at `MAX_INJECT_TITLES_PER_BATCH = 200` titles per round; per-title length cap `MAX_INJECT_TITLE_LEN = 500` (overlength titles skipped with warn, batch continues — chunk-level try/except prevents one chunk's failure from blocking others). Reduces N-per-title × M-page reads to ~U + 2M. The existing single-target `inject_wikilinks` is retained for legacy callers; new callers should use the batch.
- `manifest_key_for(source: Path, raw_dir: Path) -> str` — In `kb.compile.compiler` (cycle 19 AC11). Public alias for `_canonical_rel_path` so callers (`compile_wiki`, plugins) thread a stable opaque dict-key into `ingest_source(manifest_key=...)`. Verb-first naming matches `decay_days_for` / `tier1_budget_for`.
- `list_stale_pending(hours=24, *, history_path=None) -> list[dict]` — In `kb.review.refiner` (cycle 19 AC8b). Pure-read visibility helper that returns refine-history entries with `status="pending"` older than `hours` — surfaces rows where `refine_page` crashed between the pre-write pending entry and the applied/failed flip (the rare two-phase-write hole). Mutation/sweep tool: see `sweep_stale_pending` below.
- `rebuild_indexes(wiki_dir=None, *, hash_manifest=None, vector_db=None) -> dict` — In `kb.compile.compiler` (cycle 23 AC2). Operator-scoped "clean-slate" helper that unlinks `HASH_MANIFEST` under `file_lock(..., timeout=1.0)` (prevents racing a concurrent `compile_wiki` save), unlinks the vector DB (`_vec_db_path(wiki_dir)`), clears three LRU cache families (`kb.ingest.extractors.clear_template_cache`, `kb.utils.pages._load_page_frontmatter_cached`, `kb.utils.pages.load_purpose`), and appends one `rebuild-indexes` line to `wiki/log.md` best-effort (audit `OSError` logs warning + sets `audit_written=False`). Returns `{"manifest": {"cleared": bool, "error": str|None}, "vector": {"cleared": bool, "error": str|None}, "caches_cleared": list[str], "audit_written": bool}`. Validates `wiki_dir` resolves under `PROJECT_ROOT` (dual-anchor: the caller-supplied absolute path AND the `.resolve()` target must both land inside, defeating symlink-escape). Raises `ValidationError` on out-of-project `wiki_dir`. CLI surface `kb rebuild-indexes [--wiki-dir PATH] [--yes]` — no MCP tool (cycle 23 scope; future cycle may add `kb_rebuild_indexes`).
- `sweep_stale_pending(hours=168, *, action="mark_failed"|"delete", dry_run=False, history_path=None, wiki_dir=None) -> dict` — In `kb.review.refiner` (cycle 20 AC13). Mutation counterpart to `list_stale_pending`. `mark_failed` (default) flips matching rows' status to `failed` and adds `sweep_id` + `sweep_at` + `error="abandoned-by-sweep"` while preserving `attempt_id` + `revision_notes`. `delete` removes the row AND writes an audit entry to `wiki/log.md` BEFORE the mutation — fails CLOSED with `StorageError(kind="sweep_audit_failure")` if the audit write raises `OSError`. Matches rows by `attempt_id` equality, NEVER by `page_id` (prevents clobber of a concurrent refine that shares the page_id with a fresh attempt_id). `dry_run=True` returns candidates without mutation. Single `file_lock(history_path)` span; compatible with `refine_page`'s page-FIRST / history-SECOND order — sweep holds only the history lock (subset, no deadlock). MCP surface `kb_refine_sweep`, CLI `kb refine-sweep`.
- `refine_page` two-phase write (cycle 19 AC8/AC9/AC10): pending row written BEFORE page body, flipped to `applied` (or `failed` with `error` field) inside the SAME `file_lock(history_path)` span. Lock order is `page_path FIRST, history_path SECOND` (preserved from cycle-1 H1; AC10 WITHDRAW). Each row carries `attempt_id = uuid4().hex[:8]` so the flip targets the correct row even with concurrent stuck pending rows.
- `_write_wiki_page(..., *, exclusive=False)` — In `kb.ingest.pipeline` (cycle 20 AC8). When `exclusive=True`, uses `os.open(O_WRONLY|O_CREAT|O_EXCL)` + POSIX `O_NOFOLLOW` (guarded by `hasattr`) + write-phase poison-unlink instead of `atomic_text_write`. On `FileExistsError` raises `StorageError("summary_collision", kind="summary_collision", path=...)`. `ingest_source` summary + item writes pass `exclusive=True`; on that StorageError they pivot to `_update_existing_page` (which acquires `file_lock(page_path)` unconditionally per AC11). `append_evidence_trail` runs AFTER release because it acquires its own sidecar lock and `file_lock` is not re-entrant.
- `kb.errors` exception taxonomy (cycle 20 AC1/AC2/AC3): `KBError(Exception)` base + `IngestError` / `CompileError` / `QueryError` / `ValidationError` / `StorageError`. `LLMError` + `CaptureError` reparent to `KBError`. `StorageError(msg, *, kind=None, path=None)` — `__str__` returns `f"{kind}: <path_hidden>"` only when both kind and path set, else the raw msg. Re-exported lazily via `kb/__init__.py` `__getattr__` (preserves the `--version` short-circuit).

### Wiki Index Files

| File | Purpose |
|---|---|
| `wiki/index.md` | Master catalog, one-line per page, under 500 lines |
| `wiki/_sources.md` | Raw source → wiki page mapping (traceability for lint) |
| `wiki/_categories.md` | Auto-maintained category tree |
| `wiki/log.md` | Append-only chronological record of all operations |
| `wiki/contradictions.md` | Explicit tracker for conflicting claims across sources |

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

### Model Tiering

| Tier | Model ID | Env Override | Use |
|---|---|---|---|
| `scan` | `claude-haiku-4-5-20251001` | `CLAUDE_SCAN_MODEL` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-4-6` | `CLAUDE_WRITE_MODEL` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-7` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

### Opus 4.7 Behaviour Notes

Applies to orchestrate-tier calls. Added 2026-04-17.
- **Explicit CoT for reasoning-heavy calls.** `call_llm` (in `kb.utils.llm`) does not pass a `thinking={...}` parameter, so extended thinking is never auto-activated at the orchestrate tier — this is true on 4.6 and 4.7 alike. For query synthesis, contradiction detection, `kb_lint_deep`, and semantic reviewers, include "Think step by step before answering" or a structured `## Analysis` scaffold in the prompt.
- **Instruction following is literal.** Prefer positive phrasing ("write prose", "emit JSON") over negative ("don't use lists"). 4.x honours each stated constraint individually; long "don't X, don't Y, don't Z" forbid-lists tend to produce tangential hedging — express constraints as positive actions instead.
- **Minimal formatting remains the default (unchanged from 4.6).** 4.7 avoids bullet-heavy prose, excessive bold/headers, and report-style structure in conversational output. Reserve structure for reference material and lists of ≥4 parallel items.
- **Parallel tool calls preferred** for independent reads — batch `kb_search` + `kb_list_pages` + multi-page `kb_read_page` in one assistant turn rather than serialising.
- **Structured output via `call_llm_json()` (forced tool_use).** Keep using the existing helper in `kb.utils.llm`; it is cache-friendly and removes fence-stripping failure modes. Do not switch to assistant-prefill for JSON.
- **1M-context variant** is available from this runtime (exposed as `claude-opus-4-7[1m]`). For deep multi-source synthesis prefer calling out the capacity in the prompt ("you have ~1M tokens; use the full source text") and handing the subagent raw files directly — routing to the long-context variant is the runtime's job, not the caller's. (Note: `query_wiki`'s 80K-char cap is a library-level constant in `kb.query.engine` that applies to wiki-context assembly, not to direct-prompt pass-through — treat the two as separate concerns.)

### Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.

### Testing

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:
- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (all `SOURCE_TYPE_DIRS` subdirs) for tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

Run `python -m pytest -v` to list all tests (current full suite: 2825 tests across 247 test files; last full run was 2815 passed + 10 skipped — cycle 29 adds 16 new tests across `tests/test_cycle29_rebuild_indexes_hardening.py` (AC1 compound audit token + AC2 override PROJECT_ROOT validation, 12 tests — 1 skipped on Windows without symlink privilege) and `tests/test_cycle29_backlog_hygiene.py` (AC3/AC4/AC5 doc-hygiene source-scans, 4 tests); detailed count tracked in `CHANGELOG.md`). New tests per phase go in versioned files (e.g., `test_cycle20_errors_taxonomy.py`). Use the `tmp_wiki`/`tmp_project`/`tmp_kb_env` fixtures for any test that writes files — never write to the real `wiki/` or `raw/` in tests. Cycle 18: `tmp_kb_env` now redirects `kb.compile.compiler.HASH_MANIFEST` to `<tmp>/.data/hashes.json`. **Cycle 19: tests that use `tmp_kb_env` MUST NOT also `monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", ...)`** — the fixture already redirects it, and `tests/test_cycle19_lint_redundant_patches.py` enforces this via AST-based method-scope detection. Tests that monkeypatch one of the four cycle-19-migrated MCP callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`) MUST patch the OWNER MODULE (e.g. `patch("kb.ingest.pipeline.ingest_source")`) — not `kb.mcp.core.<callable>`, since cycle-19 AC15 refactored those imports to module-attribute style. **Cycle 20: tests that use `tmp_kb_env` AND reach `sweep_stale_pending` / `list_stale_pending` through the MCP or CLI layer should also `monkeypatch.setattr(kb.review.refiner.REVIEW_HISTORY_PATH, <tmp>)` and `monkeypatch.setattr(kb.mcp.quality.WIKI_DIR, <tmp_wiki>)` defensively** — the mirror-rebind loop may not hit modules imported post-fixture under some full-suite orderings (see `tests/test_cycle20_list_stale_surfaces.py::seeded_history`).

### Error Handling Conventions

- **Exception taxonomy** (cycle 20): `kb.errors` defines `KBError(Exception)` as the base for all kb-originated errors, with 5 specialisations — `IngestError` (raised by `ingest_source`), `CompileError` (`compile_wiki`), `QueryError` (`query_wiki` / `search_pages`), `ValidationError` (input validation), `StorageError` (atomic-write / file-lock / audit-write failures; carries `kind` + optional `path` with a redacting `__str__` that emits `<path_hidden>` so log-aggregators never see raw filesystem paths). `LLMError` and `CaptureError` subclass `KBError`; `isinstance(err, Exception)` is preserved via MRO, so existing outer catches keep working. Rule: new code that needs to raise should subclass the nearest specialised `KBError` — bare `except Exception` is only acceptable at boundary layers (CLI top-level via `_error_exit`, MCP tool wrappers, `_make_api_call` retry loop, per-source continue-on-error loops inside `compile_wiki`, `ingest_source` outer AC5 wrap).
- **MCP tools**: Return `"Error: ..."` strings on failure — never raise exceptions to the MCP client. Page IDs validated via `_validate_page_id()` (rejects path traversal, verifies path within WIKI_DIR).
- **LLM calls**: Shared retry logic in `_make_api_call()` — 3 attempts with exponential backoff on rate limits/overload/timeout. `LLMError` on exhaustion. `call_llm_json()` uses forced tool_use for guaranteed structured JSON (no fence-stripping needed).
- **Page loading loops**: Catch specific exceptions (not broad `Exception`) and skip with warning — never abort a full scan for one bad file.
- **JSON stores**: All use `atomic_json_write()` (temp file + rename). Capped at 10,000 entries each (feedback, verdicts).
- **Ingest limits**: `MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50` — prevents runaway page creation from hallucinated lists.
- **Path traversal**: Validated at MCP boundary (`_validate_page_id`, ingest path check), at library level (`refine_page`, `pair_page_with_sources`), and in reference extraction. `extract_citations()` and `extract_raw_refs()` reject `..` and leading `/`.
- **Drift pruning**: `compile.compiler.detect_source_drift` persists deletion-pruning to the manifest even though `save_hashes=False` is passed — this is the sole exception to the read-only contract; see function docstring.
- **Slug-collision hardening** (cycle 20): `_write_wiki_page(..., exclusive=True)` uses `os.open(O_WRONLY|O_CREAT|O_EXCL)` + POSIX `O_NOFOLLOW` (guarded) + write-phase poison-unlink to defeat two concurrent `ingest_source` calls from silently overwriting each other's summary. On collision raises `StorageError(kind="summary_collision", path=...)`; callers (`_run_ingest_body` summary write, `_process_item_batch` item write) pivot to `_update_existing_page` which acquires `file_lock(page_path)` unconditionally inside the helper body. `append_evidence_trail` is called OUTSIDE that lock because it acquires its own sidecar lock and `file_lock` is not re-entrant — chaining them would self-deadlock.

## Phase 2 Workflows

### Standard Ingest (with Self-Refine)
1. `kb_ingest(path)` — get extraction prompt
2. Extract JSON — `kb_ingest(path, extraction_json)`
3. For each created page: `kb_review_page(page_id)` — self-critique
4. If issues: `kb_refine_page(page_id, updated_content)` (max 2 rounds)

### Thorough Ingest (with Actor-Critic)
1-4. Same as Standard Ingest
5. Spawn wiki-reviewer agent with created page_ids
6. Review findings — fix or accept
7. `kb_affected_pages` — flag related pages

### Deep Lint
1. `kb_lint()` — mechanical report
2. For errors: `kb_lint_deep(page_id)` — evaluate fidelity
3. Fix issues via `kb_refine_page`
4. `kb_lint_consistency()` — contradiction check
5. Re-run `kb_lint()` to verify (max 3 rounds)

### Query with Feedback
1. `kb_query(question)` — synthesize answer
2. After user reaction: `kb_query_feedback(question, rating, pages)`

## Conventions

- All wiki pages must link claims back to specific `raw/` source files. Unsourced claims should be flagged.
- Use `[[wikilinks]]` for inter-page links within `wiki/`.
- Distinguish stated facts (`source says X`) from inferences (`based on A and B, we infer Y`).
- When updating wiki pages, prefer proposing diffs over full rewrites for auditability.
- Keep `wiki/index.md` under 500 lines — use category groupings, one line per page.
- Always install Python packages into the project `.venv`, never globally.

### Evidence Trail Convention

Every wiki page ingested via `ingest_source` grows an `## Evidence Trail` section whose entries `append_evidence_trail` inserts in **reverse-chronological order** (newest event at the top, immediately after a sentinel marker that identifies the section). The convention is load-bearing:

- **Append-only semantics.** Entries below the section are never rewritten; only new entries are prepended after the sentinel. Compiled truth ABOVE the section is still freely rewritten on re-ingest.
- **Reverse chronology, not bottom-append.** Unlike `wiki/log.md` (which appends at the bottom), the evidence trail reads newest-first so a reviewer scanning a long page immediately sees the most recent provenance event. Tools that parse evidence trails for historical timelines should iterate top-down and stop at the sentinel.
- **Sentinel discipline.** The ingest path writes a sentinel line exactly once per page; subsequent appends slip new entries between the sentinel and the previously-newest row. Hand-editing that removes the sentinel defeats append-ordering on the next ingest — treat the sentinel as machine-maintained.
- **When in doubt, trust the file.** Any manual auditor should read the evidence trail as printed; there is no separate index-of-evidence log to reconcile. The file is the ledger.
- **Architecture diagram sync (MANDATORY)**: Source: `docs/architecture/architecture-diagram.html` → Rendered: `docs/architecture/architecture-diagram.png` → Displayed: `README.md`. **Every time the HTML is modified**, you MUST re-render the PNG and commit it. Render command:
  ```python
  # Run from project root with .venv activated
  .venv/Scripts/python -c "
  import asyncio
  from playwright.async_api import async_playwright
  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.launch()
          page = await browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=3)
          await page.goto('file:///D:/Projects/llm-wiki-flywheel/docs/architecture/architecture-diagram.html')
          await page.wait_for_timeout(1500)
          dim = await page.evaluate('() => ({ w: document.body.scrollWidth, h: document.body.scrollHeight })')
          await page.set_viewport_size({'width': dim['w'], 'height': dim['h']})
          await page.wait_for_timeout(500)
          await page.screenshot(path='docs/architecture/architecture-diagram.png', full_page=True, type='png')
          await browser.close()
  asyncio.run(main())
  "
  ```

## Wiki Page Frontmatter Template

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-05
updated: 2026-04-05
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
# Cycle 14 AC1/AC2/AC23 — optional epistemic-integrity fields; absent is valid.
# belief_state: confirmed | uncertain | contradicted | stale | retracted
# authored_by: human | llm | hybrid
# status: seed | developing | mature | evergreen
---
```

**Optional epistemic fields (cycles 14-15):** `belief_state` is the cross-source aggregate (orthogonal to per-source `confidence`); `authored_by` formalises human vs LLM authorship; `status` tracks the page lifecycle. Query engine applies a +5% `STATUS_RANKING_BOOST` to pages with `status in (mature, evergreen)` and a mild `AUTHORED_BY_BOOST` to `authored_by: human|hybrid` when full metadata passes `validate_frontmatter`. Publish outputs (`kb publish`) skip pages with `belief_state in {retracted, contradicted}` OR `confidence == speculative`.

## Ingestion Commands

```bash
# Web page → markdown (heavy, JavaScript-rendered pages)
crwl URL -o markdown > raw/articles/page-name.md

# Web page → markdown (lightweight, articles/blogs — faster)
trafilatura -u URL > raw/articles/page-name.md

# PDF/DOCX → markdown (simple documents)
markitdown file.pdf > raw/papers/paper-name.md

# PDF → markdown (complex documents with tables/figures)
docling file.pdf --output raw/papers/

# YouTube transcript
yt-dlp --write-auto-sub --skip-download URL -o raw/videos/video-name

# arXiv paper (Python)
# import arxiv; paper = next(arxiv.Client().results(arxiv.Search(id_list=["2401.12345"])))

# Conversation capture (in-session bookmarks, scratch notes, chat transcripts)
# Via MCP: call kb_capture from your client; writes raw/captures/*.md files
# Then: kb_ingest raw/captures/<slug>.md --type capture for each
```

## MCP Servers

Configured in `.mcp.json` (git-ignored, local only): **kb**, git-mcp, context7, fetch, memory, filesystem, git, arxiv, sqlite. See `.mcp.json` for connection details.

Key usage:
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 28 tools — cycle 20 added `kb_refine_sweep` + `kb_refine_list_stale`, bringing total from 26 → 28). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
  - `kb_query(question, output_format="", save_as="")` — returns wiki context with trust scores; Claude Code synthesizes the answer. Add `use_api=true` for Anthropic API synthesis. Add `output_format={markdown|marp|html|chart|jupyter}` (requires `use_api=true`) to render the synthesized answer to a file under `outputs/`. `text` or empty = default stdout-only. Cycle 16: `save_as=<slug>` (requires `use_api=true`) persists the synthesised answer to `wiki/synthesis/{slug}.md` with hardcoded frontmatter (`type=synthesis`, `confidence=inferred`, `authored_by=llm`; `source` derived from the query's `source_pages`). `save_as` must match `[a-z0-9-]+`; traversal / Unicode homoglyph / Windows reserved names rejected with error strings. Low-coverage refusal path skips the save. Note: this makes `kb_query` a write path when `save_as` is set.
  - `kb_ingest(path, extraction_json=...)` — creates wiki pages from Claude Code's extraction. Omit `extraction_json` to get the extraction prompt. Add `use_api=true` for API extraction. Output includes `affected_pages` (cascade review list) and `wikilinks_injected` (pages updated with retroactive links). Shows "Duplicate content detected" with hash if source was already ingested.
  - `kb_ingest_content(content, filename, type, extraction_json)` — one-shot: saves content to `raw/` and creates wiki pages in one call.
  - `kb_save_source(content, filename, overwrite=false)` — save content to `raw/` for later ingestion. Returns error if file already exists unless `overwrite=true`.
  - `kb_capture(content, provenance=None)` — atomize up to 50KB of unstructured text into discrete `raw/captures/<slug>.md` items via scan-tier LLM. Returns file paths for subsequent `kb_ingest`. Secret-scanner rejects content with API keys, tokens, or private key blocks before any LLM call.
  - `kb_compile_scan(wiki_dir=None)` — find changed sources, then `kb_ingest` each. `wiki_dir` scopes changed-source discovery to that wiki project's sibling `raw/` and `.data/` paths.
  - `kb_compile(incremental=true)` — run full compilation (requires ANTHROPIC_API_KEY for LLM extraction).
  - Browse: `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`.
  - Health: `kb_stats`, `kb_lint(fix=False, augment=False, dry_run=False, execute=False, auto_ingest=False, max_gaps=5, wiki_dir=None)` — health checks (dead links, orphans, staleness, stub detection, flagged pages). With `augment=True`, runs reactive gap-fill in three opt-in modes: `propose` (default — writes `wiki/_augment_proposals.md`), `execute=True` (fetches URLs to `raw/`), `auto_ingest=True` (pre-extracts at scan tier + ingests with `confidence: speculative`). `wiki_dir` also scopes feedback-derived sections to `<project>/.data/feedback.json`. See `docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md`. Plus `kb_evolve(wiki_dir=None)` (includes coverage gaps + stub enrichment suggestions; feedback gaps are scoped to the wiki project), `kb_detect_drift` (finds wiki pages stale due to raw source changes), `kb_graph_viz` (Mermaid graph export with auto-pruning), `kb_verdict_trends` (weekly quality dashboard).
  - Quality (Phase 2): `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`.
- **memory** — Persistent knowledge graph in `.memory/memory.jsonl`. Track wiki entity relationships across sessions.
- **arxiv** — Search/download papers to `raw/papers/`.
- **sqlite** — Metadata DB at `.data/metadata.db`. For wikilink graph, ingestion history, lint results.

## Implementation History & Roadmap

- **Shipped:** see `CHANGELOG.md` (brief compact index, newest first — compact Items / Tests / Scope / Detail per cycle) and `CHANGELOG-history.md` (full per-cycle bullet-level archive). Format: [Keep a Changelog](https://keepachangelog.com/).
- **Open work:** see `BACKLOG.md` — severity levels CRITICAL → LOW, grouped by file. Resolved items are deleted (brief entry in `CHANGELOG.md`, detail in `CHANGELOG-history.md`); resolved phases collapse to a one-liner under "Resolved Phases".
- **Roadmap (Phase 5 deferred + Phase 6 cut):** see `BACKLOG.md` §"Phase 5 — Community followup proposals" and §"Phase 6 candidates". Includes the 2026-04-13 Karpathy-gist re-evaluation ("RECOMMENDED NEXT SPRINT") and all deferred features (inline claim tags, URL-aware ingest, semantic chunking, typed graph relations, autonomous research loop, etc.).

## Automation

No auto-commit hooks. Doc updates and commits are done manually when ready to push.

### BACKLOG.md lifecycle
Resolved items are **deleted** from `BACKLOG.md` (brief entry added to `CHANGELOG.md [Unreleased]` Quick Reference; full detail added to `CHANGELOG-history.md`). When all items in a phase section are resolved, the section collapses to a one-liner under "Resolved Phases" (e.g., `- **Phase 3.92** — all items resolved in v0.9.11`). This keeps the backlog focused on open work only.

### Doc update checklist (before push)
When asked to update docs, review `git diff` and update as needed:
- `CHANGELOG.md` — add compact Items / Tests / Scope / Detail entry under `[Unreleased]` Quick Reference (newest first)
- `CHANGELOG-history.md` — add full per-cycle bullet-level detail (newest first)
- `BACKLOG.md` — **delete** resolved items (never strikethrough); collapse empty phase sections
- `CLAUDE.md` — update version numbers, test counts, module/tool counts, API docs
- `README.md` — update if user-facing features or setup changed
- `docs/architecture/architecture-diagram.html` + re-render PNG if architecture changed

All tools are auto-approved for this project (permissions in `settings.local.json`).
