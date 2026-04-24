# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

- **State:** v0.10.0 · 2846 tests / 249 files (2836 passed + 10 skipped). Shipped → `CHANGELOG.md` (index) + `CHANGELOG-history.md` (per-cycle detail). Open → `BACKLOG.md`.
- **Always `.venv`** — activate before `pytest`, `kb`, `pip`. Never global Python.
- **Test fixtures** — use `tmp_wiki` / `tmp_project` / `tmp_kb_env`; never write real `wiki/` or `raw/`. `tmp_kb_env` already redirects `HASH_MANIFEST` — don't also monkeypatch it.
- **Patch the owner module** for the four MCP-migrated callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`) — not `kb.mcp.core.*`.
- **Path safety** — `_validate_page_id` at MCP boundary; library calls use `_validate_path_under_project_root(path, field_name)` (dual-anchor: literal + resolved both under `PROJECT_ROOT`).
- **Evidence Trail** — reverse-chronological, sentinel-guarded; sentinel is machine-maintained.
- **Doc update checklist** on push — see §Automation at bottom.

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

Shipped phases and per-cycle tallies → `CHANGELOG.md` (compact index, newest first) + `CHANGELOG-history.md` (per-cycle bullet archive). Open work + deferred roadmap → `BACKLOG.md`.

- **Latest full-suite:** 2846 tests / 249 files · 2836 passed + 10 skipped.
- **Latest cycle (30):** audit-log bloat cap (`_audit_token` truncates error strings at 500 chars) + CLI ↔ MCP parity continuation — 5 new read-only subcommands (`graph-viz`, `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency`) following the cycle-27 thin-wrapper pattern.
- **Per-AC rationale, question logs, R1/R2 fix trails** → `CHANGELOG-history.md` + `docs/superpowers/decisions/<date>-cycle<N>-*.md`.

### Module Map (`src/kb/`)

- **Core (Phase 1):** `config`, `models`, `utils`, `ingest`, `compile`, `query`, `lint`, `evolve`, `graph`, `mcp` (split package: `app`, `core`, `browse`, `health`, `quality`), `mcp_server` (entry shim), CLI (19 commands: `ingest`, `compile`, `query`, `lint`, `evolve`, `publish`, `mcp`, `refine-sweep`, `refine-list-stale`, `rebuild-indexes`, plus the MCP-parity wrappers `search`, `stats`, `list-pages`, `list-sources` (cycle 27), `graph-viz`, `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency` (cycle 30)).
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

**Key APIs** — non-obvious behavior only; signatures/mechanics live in source docstrings, cycle-level forensics in `CHANGELOG-history.md`.

- **LLM calls** (`kb.utils.llm`): `call_llm(prompt, tier)` + `call_llm_json(prompt, tier, schema)`. Tiers `scan`/`write`/`orchestrate` = Haiku/Sonnet/Opus. Routes via CLI subprocess when `KB_LLM_BACKEND` is set, else Anthropic SDK with forced tool_use for JSON. Raises `LLMError`. Config helpers: `get_cli_backend()`, `get_cli_model(tier)` (respects `KB_CLI_MODEL_<TIER>`).
- **Ingest** (`kb.ingest.pipeline`): `ingest_source(path, *, extraction=None, wiki_dir=None, manifest_key=None, ...)` — pass `extraction` to skip the LLM call (Claude Code mode). Raises `ValidationError` if `path` resolves inside the effective wiki (circular-ingest guard; redacted message).
- **Query** (`kb.query.engine`): `query_wiki(question, *, output_format=None, ...)` → `{answer, citations[{type,path,context,stale}], source_pages, context_pages, output_path?, output_format?, output_error?}`. `output_format` is keyword-only. Stale-flagging composes source mtime with `decay_days_for`; `STATUS_RANKING_BOOST` + `AUTHORED_BY_BOOST` applied post-`validate_frontmatter`. Library context-cap is 80K chars (separate from any direct-prompt pass-through).
- **Page helpers** (`kb.utils.pages`): `load_all_pages`, `scan_wiki_pages`, `page_id` (lowercases; use stored `path` for case-sensitive I/O; `content_lower` is pre-lowercased for BM25). `save_page_frontmatter(path, post)` is the single key-order-preserving write point — use it for any round-trip that must preserve insertion order (Evidence Trail, augment write-backs).
- **Text helpers** (`kb.utils.text`): `slugify`, `yaml_escape`. Single source of truth.
- **Refine** (`kb.review.refiner`): `refine_page` two-phase write — pending row → page body → applied/failed flip under `file_lock(history_path)`. Lock order `page_path FIRST, history_path SECOND`. Each row carries `attempt_id`. `list_stale_pending` (read) + `sweep_stale_pending(*, action="mark_failed"|"delete", dry_run=False)` (mutate); sweep matches by `attempt_id` never `page_id`, `delete` writes audit BEFORE mutation (fails closed with `StorageError(kind="sweep_audit_failure")`). MCP: `kb_refine_sweep`, `kb_refine_list_stale`.
- **Vector index** (`kb.query.embeddings`): `rebuild_vector_index` is tmp-then-`os.replace` with `_conn` closed before swap (Windows handle-release); stale `.tmp` unlinked on entry. `VectorIndex.build(*, db_path=None)` — override does NOT mutate `self._stored_dim`. Batch callers pass `_skip_vector_rebuild=True` and invoke once at tail. `maybe_warm_load_vector_model(wiki_dir) -> Thread|None` spawns a daemon preload (idempotent no-op if model already loaded); called by `kb.mcp.__init__.main()` after tool registration — `kb compile` intentionally NOT warm-loaded.
- **Evidence Trail** (`kb.ingest.evidence`): `render_initial_evidence_trail` writes inline on first page write (no separate append fires for new pages). `append_evidence_trail` thereafter — sentinel search is span-limited to the FIRST `## Evidence Trail` section, so stray sentinels elsewhere are inert. Header variants tolerate CRLF + trailing whitespace.
- **File locking** (`kb.utils.io`): `file_lock(path, timeout=None)` — NOT re-entrant. `LOCK_INITIAL_POLL_INTERVAL=0.01` (floor) / `LOCK_POLL_INTERVAL=0.05` (cap) both read at call time (monkeypatch-friendly); exponent capped at `2**30`.
- **Rebuild indexes** (`kb.compile.compiler`): `rebuild_indexes(wiki_dir=None, *, hash_manifest=None, vector_db=None)` — operator "clean-slate". Unlinks manifest (under lock) + vector DB, clears LRU caches, appends audit log best-effort. Dual-anchor `PROJECT_ROOT` containment on all three paths via `_validate_path_under_project_root(path, field_name)` (literal + resolved both under root; raises `ValidationError`). Audit + CLI render `<field>=cleared (warn: <error>)` on partial clears via `_audit_token(block)`. CLI: `kb rebuild-indexes`; no MCP tool yet.
- **Compile manifest states** (`kb.compile.compiler`): three-valued — `real_hash` (success), `failed:{pre_hash}` (handled exception), `in_progress:{pre_hash}` (only survives hard-kill; warned on next scan). `manifest_key_for(source, raw_dir)` is the stable opaque dict-key.
- **Wikilink injection** (`kb.compile.linker`): `inject_wikilinks_batch(new_pages, ...)` — chunked 200 titles/round, per-title 500-char cap. Pre-lock peek is candidate-gathering only; winner re-derived under per-page `file_lock` from fresh body. Prefer over single-target `inject_wikilinks` for new callers.
- **Exclusive write** (`kb.ingest.pipeline`): `_write_wiki_page(..., *, exclusive=True)` uses `O_EXCL|O_NOFOLLOW` + poison-unlink; raises `StorageError(kind="summary_collision")` on collision — callers pivot to `_update_existing_page` (which acquires `file_lock(page_path)` unconditionally). `append_evidence_trail` runs AFTER release (sidecar lock, not re-entrant with `file_lock`).
- **Errors** (`kb.errors`): `KBError` base + `IngestError`/`CompileError`/`QueryError`/`ValidationError`/`StorageError(msg, *, kind, path)`. `StorageError.__str__` redacts path to `<path_hidden>` when both kind+path set. `LLMError`, `CaptureError` reparent to `KBError`. Re-exported lazily via `kb/__init__.py` `__getattr__`. New code raises the nearest specialisation; bare `except Exception` only at boundary layers (CLI top-level, MCP tool wrappers, API retry loop, per-source continue-on-error, outer ingest wrap).
- **Observability counters** (diagnostic only; read-only; no reset): `get_dim_mismatch_count` + `get_bm25_build_count` (lock-free, hot paths — may undercount by ≤N under N concurrent callers); `get_vector_model_cold_load_count` + `get_sqlite_vec_load_count` (locked, exact per-instance). Paired with `logger.info` latency emissions at cold-load sites; WARN threshold `0.3s` for vector model + sqlite-vec.
- **Ingest helpers**: `build_extraction_schema(template)` in `kb.ingest.extractors` (LRU-cached via `_build_schema_cached(source_type)`).

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

Full suite: 2846 tests / 249 files (2836 passed + 10 skipped). New tests per cycle go in versioned files (e.g. `test_cycle20_errors_taxonomy.py`). Per-cycle test-file details → `CHANGELOG-history.md`.

**Fixture rules** (enforced by `test_cycle19_lint_redundant_patches.py` AST scan):
- Writing tests: use `tmp_wiki` / `tmp_project` / `tmp_kb_env` only — never touch the real `wiki/` or `raw/`.
- `tmp_kb_env` already redirects `kb.compile.compiler.HASH_MANIFEST` — do NOT also `monkeypatch.setattr` it.
- Patching the four migrated MCP callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`): patch the OWNER MODULE (`kb.ingest.pipeline.ingest_source`), not `kb.mcp.core.*`.
- Tests that reach `sweep_stale_pending` / `list_stale_pending` via MCP or CLI: also `monkeypatch.setattr(kb.review.refiner.REVIEW_HISTORY_PATH, ...)` and `kb.mcp.quality.WIKI_DIR` defensively (mirror-rebind loop isn't guaranteed to hit post-fixture imports under every test ordering).

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

### Architecture Diagram Sync (MANDATORY)

Source `docs/architecture/architecture-diagram.html` → rendered PNG sibling → displayed in `README.md`. **Every HTML edit must re-render the PNG and commit it.** Render via headless Playwright at 1440×900 viewport (auto-expanded to content), `device_scale_factor=3`, `full_page=True`, `--type=png`; see prior commits for the exact invocation.

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
- **kb** — The knowledge base MCP server (`kb.mcp_server`, 28 tools). Start with `kb mcp` or `python -m kb.mcp_server`. Claude Code is the default LLM — no API key needed.
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
