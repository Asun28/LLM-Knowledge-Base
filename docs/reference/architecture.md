# Architecture

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Architecture" sections. Pairs with [module-map.md](module-map.md) (`src/kb/` per-module breakdown).

## Three-Layer Content Structure

- **`raw/`** — Immutable source documents. The LLM reads but **never modifies** files here (except raw/captures/, which is the sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest). Subdirs: `articles/`, `papers/`, `repos/`, `videos/`, `podcasts/`, `books/`, `datasets/`, `conversations/`, `assets/`. Use Obsidian Web Clipper for web→markdown; download images to `raw/assets/`.
- **`wiki/`** — LLM-generated and LLM-maintained markdown. Page subdirs: `entities/`, `concepts/`, `comparisons/`, `summaries/`, `synthesis/`. All pages use YAML frontmatter (see template in [CLAUDE.md](../../CLAUDE.md#wiki-page-frontmatter-template)). Non-technical users can optionally install the [Remotely Save](https://github.com/remotely-save/remotely-save) Obsidian community plugin (Apache 2.0) to sync `wiki/` to S3, Azure Blob, OneDrive, or Dropbox — the pipeline writes to the bucket, Remotely Save pulls it into Obsidian automatically.
- **`research/`** — Human-authored analysis, project ideas, and meta-research about the knowledge base approach.

## Five Operations Cycle: Ingest → Compile → Query → Lint → Evolve

- **Ingest**: User adds source to `raw/`. LLM reads it, writes summary to `wiki/summaries/`, updates `wiki/index.md`, modifies relevant entity/concept pages, appends to `wiki/log.md`.
- **Compile**: LLM builds/updates interlinked wiki pages. Uses hash-based incremental detection — only processes new/changed sources. Manifest saved after each source (crash-safe). Proposes diffs, not full rewrites.
- **Query**: User asks questions. LLM searches wiki using BM25 ranking (term frequency saturation, IDF weighting, length normalization), synthesizes answers with inline citations to wiki pages and raw sources. Title tokens boosted by `SEARCH_TITLE_WEIGHT` (repeated N times before indexing). Context truncated to 80K chars. Good answers become new wiki pages.
- **Lint**: Health check — orphan pages, dead links, staleness, wikilink cycles, coverage gaps, frontmatter validation. Produces a report, does not silently fix.
- **Evolve**: Gap analysis — what topics lack coverage, what concepts should be linked, what raw sources would fill gaps. User picks suggestions, LLM executes.

## Python Package (`src/kb/`)

Entry point: `kb = "kb.cli:cli"` in `pyproject.toml`. Version in `src/kb/__init__.py`. MCP server entry: `python -m kb.mcp_server` or `kb mcp`. MCP package: `kb.mcp` (split from monolithic `mcp_server.py`).

All paths, model tiers, page types, and confidence levels are defined in `kb.config` — import from there, never hardcode. `PROJECT_ROOT` resolves from `config.py`'s location, so it works regardless of working directory.

**Key APIs** — non-obvious behavior only; signatures/mechanics live in source docstrings, cycle-level forensics in `CHANGELOG-history.md`.

- **LLM calls** (`kb.utils.llm`): `call_llm(prompt, tier)` + `call_llm_json(prompt, tier, schema)`. Tiers `scan`/`write`/`orchestrate` = Haiku/Sonnet/Opus. Routes via CLI subprocess when `KB_LLM_BACKEND` is set, else Anthropic SDK with forced tool_use for JSON. Raises `LLMError`. Config helpers: `get_cli_backend()`, `get_cli_model(tier)` (respects `KB_CLI_MODEL_<TIER>`).
- **Ingest** (`kb.ingest.pipeline`): `ingest_source(path, *, extraction=None, wiki_dir=None, manifest_key=None, ...)` — pass `extraction` to skip the LLM call (Claude Code mode). Raises `ValidationError` if `path` resolves inside the effective wiki (circular-ingest guard; redacted message).
- **Query** (`kb.query.engine`): `query_wiki(question, *, output_format=None, ...)` → `{answer, citations[{type,path,context,stale}], source_pages, context_pages, output_path?, output_format?, output_error?}`. `output_format` is keyword-only. Stale-flagging composes source mtime with `decay_days_for`; `STATUS_RANKING_BOOST` + `AUTHORED_BY_BOOST` applied post-`validate_frontmatter`. Library context-cap is 80K chars (separate from any direct-prompt pass-through).
- **Page helpers** (`kb.utils.pages`): `load_all_pages`, `scan_wiki_pages`, `page_id` (lowercases; use stored `path` for case-sensitive I/O; `content_lower` is pre-lowercased for BM25). `save_page_frontmatter(path, post)` is the single key-order-preserving write point — use it for any round-trip that must preserve insertion order (Evidence Trail, augment write-backs).
- **Text helpers** (`kb.utils.text`): `slugify`, `yaml_escape`. Single source of truth.
- **Refine** (`kb.review.refiner`): `refine_page` two-phase write — pending row → page body → applied/failed flip under `file_lock(history_path)`. Lock order `page_path FIRST, history_path SECOND`. Each row carries `attempt_id`. `list_stale_pending` (read) + `sweep_stale_pending(*, action="mark_failed"|"delete", dry_run=False)` (mutate); sweep matches by `attempt_id` never `page_id`, `delete` writes audit BEFORE mutation (fails closed with `StorageError(kind="sweep_audit_failure")`). MCP: `kb_refine_sweep`, `kb_refine_list_stale`.
- **Vector index** (`kb.query.embeddings`): `rebuild_vector_index` is tmp-then-`os.replace` with `_conn` closed before swap (Windows handle-release); stale `.tmp` unlinked on entry. `VectorIndex.build(*, db_path=None)` — override does NOT mutate `self._stored_dim`. Batch callers pass `_skip_vector_rebuild=True` and invoke once at tail. `maybe_warm_load_vector_model(wiki_dir) -> Thread|None` spawns a daemon preload (idempotent no-op if model already loaded); called by `kb.mcp.__init__.main()` after tool registration — `kb compile` intentionally NOT warm-loaded.
- **Evidence Trail** (`kb.ingest.evidence`): `render_initial_evidence_trail` writes inline on first page write (no separate append fires for new pages). `append_evidence_trail` thereafter — sentinel search is span-limited to the FIRST `## Evidence Trail` section, so stray sentinels elsewhere are inert. Header variants tolerate CRLF + trailing whitespace.
- **File locking** (`kb.utils.io`): `file_lock(path, timeout=None)` — NOT re-entrant. `LOCK_INITIAL_POLL_INTERVAL=0.01` (floor) / `LOCK_POLL_INTERVAL=0.05` (cap) both read at call time (monkeypatch-friendly); exponent capped at `2**30`. Cycle 32 AC6 — `_LOCK_WAITERS` counter + initial-wait stagger provide a probabilistic **mitigation** (intra-process only, not a guarantee) for starvation under N-waiter contention. Counter is taken inside the outer `try` with a `slot_taken` guard so a `KeyboardInterrupt` between increment and try-entry cannot leak the counter; stagger is clamped to `LOCK_POLL_INTERVAL` to prevent double-compounding with the existing exponential backoff.
- **Rebuild indexes** (`kb.compile.compiler`): `rebuild_indexes(wiki_dir=None, *, hash_manifest=None, vector_db=None)` — operator "clean-slate". Unlinks manifest (under lock) + vector DB, clears LRU caches, appends audit log best-effort. Dual-anchor `PROJECT_ROOT` containment on all three paths via `_validate_path_under_project_root(path, field_name)` (literal + resolved both under root; raises `ValidationError`). Audit + CLI render `<field>=cleared (warn: <error>)` on partial clears via `_audit_token(block)`. CLI: `kb rebuild-indexes`; no MCP tool yet.
- **Compile manifest states** (`kb.compile.compiler`): three-valued — `real_hash` (success), `failed:{pre_hash}` (handled exception), `in_progress:{pre_hash}` (only survives hard-kill; warned on next scan). `manifest_key_for(source, raw_dir)` is the stable opaque dict-key.
- **Wikilink injection** (`kb.compile.linker`): `inject_wikilinks_batch(new_pages, ...)` — chunked 200 titles/round, per-title 500-char cap. Pre-lock peek is candidate-gathering only; winner re-derived under per-page `file_lock` from fresh body. Prefer over single-target `inject_wikilinks` for new callers.
- **Exclusive write** (`kb.ingest.pipeline`): `_write_wiki_page(..., *, exclusive=True)` uses `O_EXCL|O_NOFOLLOW` + poison-unlink; raises `StorageError(kind="summary_collision")` on collision — callers pivot to `_update_existing_page` (which acquires `file_lock(page_path)` unconditionally). `append_evidence_trail` runs AFTER release (sidecar lock, not re-entrant with `file_lock`).
- **Errors** (`kb.errors`): `KBError` base + `IngestError`/`CompileError`/`QueryError`/`ValidationError`/`StorageError(msg, *, kind, path)`. `StorageError.__str__` redacts path to `<path_hidden>` when both kind+path set. `LLMError`, `CaptureError` reparent to `KBError`. Re-exported lazily via `kb/__init__.py` `__getattr__`. New code raises the nearest specialisation; bare `except Exception` only at boundary layers (CLI top-level, MCP tool wrappers, API retry loop, per-source continue-on-error, outer ingest wrap).
- **Observability counters** (diagnostic only; read-only; no reset): `get_dim_mismatch_count` + `get_bm25_build_count` (lock-free, hot paths — may undercount by ≤N under N concurrent callers); `get_vector_model_cold_load_count` + `get_sqlite_vec_load_count` (locked, exact per-instance). Paired with `logger.info` latency emissions at cold-load sites; WARN threshold `0.3s` for vector model + sqlite-vec.
- **Ingest helpers**: `build_extraction_schema(template)` in `kb.ingest.extractors` (LRU-cached via `_build_schema_cached(source_type)`).

## Wiki Index Files

| File | Purpose |
|---|---|
| `wiki/index.md` | Master catalog, one-line per page, under 500 lines |
| `wiki/_sources.md` | Raw source → wiki page mapping (traceability for lint) |
| `wiki/_categories.md` | Auto-maintained category tree |
| `wiki/log.md` | Append-only chronological record of all operations |
| `wiki/contradictions.md` | Explicit tracker for conflicting claims across sources |

**Local-only directories** (git-ignored): `.claude/`, `.tools/`, `.memory/`, `.data/`, `openspec/`, `.mcp.json`. The `others/` directory holds misc files like screenshots.

## Related

- [module-map.md](module-map.md) — per-module breakdown of `src/kb/`
- [error-handling.md](error-handling.md) — exception taxonomy and conventions
- [testing.md](testing.md) — fixtures and test conventions
- [conventions.md](conventions.md) — Evidence Trail, Architecture Diagram Sync
