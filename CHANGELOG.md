# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

> **High-level index.** One paragraph per cycle with scope, commit/test deltas, and a pointer to the full bullet-level archive in [CHANGELOG-history.md](CHANGELOG-history.md).
> Cross-reference: [BACKLOG.md](BACKLOG.md) tracks open work; resolved items are deleted from BACKLOG once shipped here.

<!-- Entry template — keep each cycle to ~3-5 lines in this file:
### Phase X.Y — <cycle-name> (YYYY-MM-DD)
<N> AC across <M> source files / <K> commits. Tests: A → B (+Δ).
<One-sentence scope>. <Security/review notes if any>.
Full detail: [history archive](CHANGELOG-history.md#<anchor>).
-->

## [Unreleased]

### Quick Reference — cycles 2026-04-16 → 2026-04-20

| Cycle | Date | Items | Test Δ | Primary areas |
|-------|------|-------|--------|---------------|
| cycle 16 | 2026-04-20 | 24 AC / 8 src / 14 commits | 2334 → 2464 (+130) | enrichment targets, query rephrasings, duplicate-slug + inline-callout lint, kb_query `save_as`, per-page siblings + sitemap publish |
| cycle 15 | 2026-04-20 | 26 AC / 6 src / 7 commits | 2245 → 2334 (+89) | authored-by boost, source volatility, per-source decay, incremental publish, lint decay/status wiring |
| cycle 14 | 2026-04-20 | 21 AC / 9 src / 8 commits | 2140 → 2235 (+95) | Epistemic-Integrity 2.0 vocabularies, coverage-confidence refusal gate, `kb publish` module (/llms.txt, /llms-full.txt, /graph.jsonld), status ranking boost |
| cycle 13 | 2026-04-20 | 8 AC / 5 src / 7 commits | 2119 → 2131 (+12) | frontmatter migration to cached loader, CLI boot `sweep_orphan_tmp`, `run_augment` raw_dir derivation |
| cycle 12 | 2026-04-19 | 17 AC / 13 src / 11 commits | 2089 → 2118 (+29) | conftest fixture, io sweep, `KB_PROJECT_ROOT`, LRU frontmatter cache, `kb-mcp` console script |
| cycle 11 | 2026-04-19 | 14 AC / 14 src / 13 commits | 2041 → 2081 (+40) | ingest coercion, comparison/synthesis reject, page-helper relocation, CLI import smoke, stale-result edges |
| cycle 10 | 2026-04-18 | 14 AC / 10 src | 2004 → 2041 (+37) | MCP `_validate_wiki_dir` rollout, `kb_affected_pages` warnings, `VECTOR_MIN_SIMILARITY` floor, capture hardening |
| cycle 9 | 2026-04-18 | 30 AC / 14 src | 1949 → 2003 (+54) | wiki_dir isolation across query/MCP, LLM redaction, env-example docs, lazy ingest export |
| cycle 8 | 2026-04-18 | 30 AC / 19 src | 1919 → 1949 (+30) | model validators, LLM telemetry, PageRank → RRF list, contradictions idempotency, pip toolchain CVE patch |
| cycle 7 | 2026-04-18 | 30 AC / 22 src | 1868 → 1919 (+51) | `_safe_call` helper, MCP error-path sanitization, Evidence Trail convention, many lint/query/ingest refinements |
| cycle 6 | 2026-04-18 | 15 AC / 14 src | 1836 → 1868 (+32) | PageRank cache, vector-index reuse, CLI `--verbose`, hybrid rrf tuple storage, graph `include_centrality` opt-in |
| cycle 5 redo | 2026-04-18 | 6 AC / 6 src | 1821 → 1836 (+15) | pipeline retrofit for Steps 2/5 artifacts; citation format symmetry, page-id SSOT, purpose-sentinel coverage |
| cycle 5 | 2026-04-18 | 14 AC / 13 src | 1811 → 1820 (+9) | `wrap_purpose` sentinel, pytest markers, verdicts/config consolidation, `_validate_page_id` control-char reject |
| PR #17 concurrency | 2026-04-18 | 3 files | 1810 → 1811 (+1) | `_VERDICTS_WRITE_LOCK` fix + capture docstring clarity; CHANGELOG split into active vs history |
| cycle 4 | 2026-04-17 | 22 AC / 16 src | 1754 → 1810 (+56) | `_rel()` path-leak sweep, `<prior_turn>` sentinel sanitizer, kb_read_page cap, rewriter CJK gate, BM25 postings index |
| cycle 3 | 2026-04-17 | 24 AC / 16 src | 1727 → 1754 (+27) | `LLMError.kind` taxonomy, vector dim guard + lock, stale markers in context, hybrid catch-degrade, inverted-postings consistency |
| cycle 2 | 2026-04-17 | 30 AC / 19 src | 1697 → 1727 (+30) | hashing CRLF normalization, file_lock hardening, rrf metadata merge, extraction schema deepcopy |
| cycle 1 | 2026-04-17 | 38 AC / 18 src | → 1697 | pipeline wiki/raw dir plumbing, augment rate/manifest scoping, capture secret patterns, 3-round PR review pattern established |
| HIGH cycle 2 | 2026-04-17 | 22 / 16 src | → 1645 | frontmatter regex cap, orphan-graph copy, semantic inverted index, trends UTC-aware timestamps |
| HIGH cycle 1 | 2026-04-16 | 22 / multi | → baseline | RMW locks across refiner/evidence/wiki_log, hybrid vector-index lifecycle, error-tag categories |
| CRITICAL docs-sync | 2026-04-16 | 2 | 1546 → 1552 | version-string alignment + `scripts/verify_docs.py` drift check |

> Older history (Phase 4.5 CRITICAL audit 2026-04-15 + all released versions): [CHANGELOG-history.md](CHANGELOG-history.md).

---

### Cycle summaries

#### Phase 4.5 — cycle 16 (2026-04-20)

24 AC / 8 src / 14 commits (incl. Step-11 N1 HIGH security fix + R1/R2/R3 review batches). Adds `suggest_enrichment_targets`, scan-tier query rephrasings on the low-coverage refusal branch, duplicate-slug + inline-callout lint checks (wired into runner), `kb_query(save_as=...)` synthesis persistence, and the `build_per_page_siblings` / `build_sitemap_xml` publish builders with CLI integration. Security: path-containment switched to `Path.is_relative_to` (T9 regression test pinned); all 15 threats IMPLEMENTED; 0 Dependabot alerts; empty pip-audit diff. Full detail: [history archive](CHANGELOG-history.md#phase-45----backlog-by-file-cycle-16-2026-04-20).

#### Phase 4.5 — cycle 15 (2026-04-20)

26 AC / 6 src / 7 commits (incl. 1 R1 PR-review fix). Adds `AUTHORED_BY_BOOST`, `SOURCE_VOLATILITY_TOPICS`, `volatility_multiplier_for`, mild authored-by ranking lift, status/authored-by drift lint checks, and `_publish_skip_if_unchanged` incremental short-circuit. Extends `decay_days_for` with `topics=` composition; stale-flag + tier1 budget wiring in `query_wiki`; `--incremental/--no-incremental` on `kb publish`. Security: all 10 threats IMPLEMENTED; operator note T10c recommends `--no-incremental` on first post-upgrade run. Full detail: [history archive](CHANGELOG-history.md#phase-45----backlog-by-file-cycle-15-2026-04-20).

#### Phase 4.5 — cycle 14 (2026-04-20)

21 AC / 9 src / 8 commits + 1 security-verify PARTIAL fix. Ships Epistemic-Integrity 2.0: `belief_state` / `authored_by` / `status` vocabularies; coverage-confidence refusal gate (`QUERY_COVERAGE_CONFIDENCE_THRESHOLD = 0.45`); per-platform `SOURCE_DECAY_DAYS` + `CONTEXT_TIER1_SPLIT`; `save_page_frontmatter` rigid wrapper + augment write-back migration; new `kb publish` CLI + three Karpathy Tier-1 builders (`/llms.txt`, `/llms-full.txt`, `/graph.jsonld`); `STATUS_RANKING_BOOST` post-RRF fusion. Security: all 10 threats IMPLEMENTED. Full detail: [history archive](CHANGELOG-history.md#phase-45----backlog-by-file-cycle-14-2026-04-20).

#### Phase 4.5 — cycle 13 (2026-04-20)

8 AC / 5 src / 7 commits. Additive housekeeping: migrates five read-only frontmatter sites to cached `load_page_frontmatter`, wires `sweep_orphan_tmp` into the CLI group callback (post `--version` short-circuit), and teaches `run_augment` to derive `raw_dir = wiki_dir.parent / "raw"` on custom wiki overrides. Extracts `_resolve_raw_dir` + `_record_verdict_gap_callout` helpers for testability. Security: all 7 threats IMPLEMENTED. Full detail: [history archive](CHANGELOG-history.md#phase-45----backlog-by-file-cycle-13-2026-04-20).

#### Phase 4.5 — cycle 12 (2026-04-19)

17 AC / 13 src / 11 commits + 1 security-verify PARTIAL fix. Adds `tmp_kb_env` isolation fixture, `sweep_orphan_tmp` helper, LRU `load_page_frontmatter`, `kb-mcp` console script. `KB_PROJECT_ROOT` env override with bounded walk-up fallback; `file_lock` / atomic-write docstring caveats for network mounts; lint/checks migration to cached loader; `sanitize_context` regression pin. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-12-2026-04-19).

#### Phase 4.5 — cycle 11 (2026-04-19)

14 AC / 14 src / 13 commits. Pipelines `_coerce_str_field` scalar/list handling; comparison/synthesis early-rejection with `kb_create_page` hint; canonical `page_id` / `scan_wiki_pages` relocated to `kb.utils.pages` (graph re-exports); CLI function-local imports + `--version` / `-V` short-circuit that avoids loading `kb.config`. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-11-2026-04-19).

#### Backlog-by-file cycle 10 (2026-04-18)

14 AC across mcp/*, query/engine, compile/compiler, utils/text, capture, ingest/pipeline, lint/_safe_call. Enforces `PROJECT_ROOT` containment in `_validate_wiki_dir`; surfaces `backlinks` / `shared_sources` warnings in `kb_affected_pages`; adds `VECTOR_MIN_SIMILARITY` cosine floor (BM25 rank preserved on vector-drop); capture UUID prompt boundary; `_coerce_str_field` helper; `_sanitize_error_str` for embedded exception text. 37 new tests; 7 Windows-skips; 0 new Dependabot alerts. Full detail: [history archive](CHANGELOG-history.md#backlog-by-file-cycle-10-2026-04-18).

#### Phase 4.5 — cycle 9 (2026-04-18)

30 AC / 14 src + 2 security-review fixes. Threads `wiki_dir` override through vector-index, stale-flag, search-mode, and raw-fallback paths; scopes `kb_lint` / `kb_evolve` feedback sections to the project's `.data/feedback.json`; `_redact_secrets` for LLM error text; capture hardening (bounded slug collision, encoded-secret labels, per-process rate-limit docs); `ANTHROPIC_API_KEY` documented as optional. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-9-2026-04-18).

#### Phase 4.5 — cycle 8 (2026-04-18)

30 AC / 19 src. `WikiPage` / `RawSource` model validators + `to_dict` / `from_post`; curated `__all__` for package surfaces; `_validate_notes` helper; `kb_stats` / `kb_verdict_trends` `wiki_dir` override; LLM success telemetry. PageRank no longer post-multiplies — now enters RRF as a ranked list; consistency build caps at 20 groups × 4096 chars; `_persist_contradictions` idempotent on re-ingest. Security: `pip` 24.3.1 → 26.0.1 patches CVE-2025-8869 + CVE-2026-1703; `diskcache==5.6.3` CVE-2025-69872 tracked. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-8-2026-04-18).

#### Phase 4.5 — cycle 7 (2026-04-18)

30 AC / 22 src / 48 behavioural regression tests. New `_safe_call` helper surfaces `<label>_error` instead of silent `None`; MCP `_sanitize_error_str` scrubs paths from exception strings across `mcp/core` + `mcp/health`; `get_model_tier` lazy env-aware tier lookup; keyword-only `pages=` param on `build_graph` / `build_backlinks` / `build_consistency_context` to avoid duplicate disk walks; `refine_page` rejects malformed YAML; `wrap_purpose` escapes `</kb_purpose>` closers; CLI `--version` short-circuit before `kb.config` import. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-7-2026-04-18).

#### Phase 4.5 — cycle 6 (2026-04-18)

15 AC / 14 src. `_PAGERANK_CACHE` with `_PAGERANK_CACHE_LOCK`; `VectorIndex._ensure_conn()` reuses one connection per instance + marks disabled on sqlite_vec load failure; `_is_debug_mode()` + `--verbose` top-level flag; `_iter_connection_pairs` generator for connection-opportunity cap. `kb_ingest_content(use_api=True)`; three health tools gain `wiki_dir=`; rewriter rejects LLM preamble leaks; `rrf_fusion` stores `(score, metadata)` tuples; dedup skips Jaccard across `type`; graph `graph_stats(include_centrality=False)` default. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-6-2026-04-18).

#### Phase 4.5 — cycle 5 redo (hardening, 2026-04-18)

6 AC / 6 src. Runs the full feature-dev pipeline retroactively over cycle 5, producing Step-2 threat-model + Step-5 decision-gate artifacts. Fixes citation-format symmetry between API-mode prompt (`[[page_id]]`) and `extract_citations` regex; removes duplicate `_MAX_PAGE_ID_LEN` constant in favour of `config.MAX_PAGE_ID_LEN`; wraps the third purpose callsite via `wrap_purpose`. Full detail: [history archive](CHANGELOG-history.md#phase-45--cycle-5-redo-hardening-2026-04-18).

#### Phase 4.5 — cycle 5 (2026-04-18)

14 AC / 13 src. `wrap_purpose(text, max_chars=4096)` sentinel helper; `VALID_SEVERITIES` / `VALID_VERDICT_TYPES` consolidated in `kb.config`; pytest markers registered; `_validate_page_id` rejects control characters; `_extract_entity_context` uses `\b`-word-boundary regex; MCP citation format updated to wikilinks; LLM client gets `User-Agent` default header. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-5-2026-04-18).

#### Concurrency fix + docs tidy (PR #17, 2026-04-18)

3 src files. `add_verdict` concurrency flake fixed via `_VERDICTS_WRITE_LOCK` in-process serializer (Windows PID-liveness heuristic could steal a live lock under load); capture docstrings clarify base64 / URL-decode scan cost bounds; CHANGELOG split into active (this file) + `CHANGELOG-history.md` archive. Full detail: [history archive](CHANGELOG-history.md#concurrency-fix--docs-tidy-pr-17-2026-04-18).

#### Phase 4.5 — cycle 4 (2026-04-17)

22 AC / 16 src (design-gate dropped 7 already-shipped + deferred 1 architecturally-deep). Highlights: `_rel()` sweep over `Path` error-string interpolations; `<prior_turn>` fence + fullwidth-angle-bracket sanitization in `_sanitize_conversation_context`; `kb_read_page` caps body at `QUERY_CONTEXT_MAX_CHARS`; `kb_affected_pages` tightened to `check_exists=True`; `_validate_page_id` rejects Windows reserved basenames + enforces 255-char cap; `kb_detect_drift` surfaces deleted sources; CJK short-query skip in rewriter; `BM25_TOKENIZER_VERSION = 2` salted into cache keys + stopwords pruned; monthly log rotation; BM25 postings index (~25× speedup). Security: `langsmith` + `python-multipart` CVEs resolved via venv sync. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-4-2026-04-17).

#### Phase 4.5 — cycle 3 (2026-04-17)

24 AC / 16 src + 2 security-verify follow-ups. `LLMError.kind` taxonomy (`invalid_request` / `auth` / `permission` / `status_error`); NFC page-id normalization in feedback; `VectorIndex.query` dim-cache + single-warn degrade; `_index_cache_lock` double-checked locking; `[STALE]` marker in context; `stale_citations` + `search_mode` additive return keys; raw-fallback semantic gate (empty / all-summary) instead of char count; `detect_contradictions_with_metadata`; source_document XML sentinel with closer-escape; `check_frontmatter_staleness`; `export_mermaid` prune-before-load; `kb_list_pages`/`kb_list_sources` pagination with int-coercion guard. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-3-2026-04-17).

#### Phase 4.5 — cycle 2 (2026-04-17)

30 AC / 19 src. CRLF/lone-CR normalization in `content_hash` / `hash_bytes`; `file_lock` PID-liveness + lazy legacy-lock purge; `atomic_json_write` / `atomic_text_write` fsync-before-replace; `call_llm_json` surfaces multi-tool-use; backoff jitter; `LLMError` message truncation; `wiki_log` zero-width-space escape for markdown markup; `rrf_fusion` metadata merge on collision; `export_mermaid` deterministic tie-break; `build_evidence_entry` / `format_evidence_entry` split (render backtick-wraps pipes); `inject_wikilinks` single regex call per page; `_find_overlapping_sentences` per-sentence segmentation. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-2-2026-04-17).

#### Phase 4.5 — cycle 1 (2026-04-17)

38 AC / 18 src. First cycle with the full feature-dev pipeline end-to-end via subagents + 3-round PR review pattern. `ingest_source(raw_dir=...)` plumbing; `SUPPORTED_SOURCE_EXTENSIONS` enforced library-side; `run_augment` + `Manifest` + `RateLimiter` accept `data_dir=`; capture secret patterns widened (env vars, Bearer / Basic split, opaque OAuth tokens); `kb_create_page` O_EXCL exclusive-create; `kb_search` `[STALE]` surfacing; `kb_ingest` stat pre-check; rewriter rejects LLM preamble leaks; `rewrite_query` absolute ceiling + floor; `_flag_stale_results` UTC-aware; `load_feedback` widened corruption-recovery; `utils/markdown` strips code blocks before pattern matching. Full detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-1-2026-04-17).

#### Phase 4.5 — HIGH cycle 2 (2026-04-17)

22 HIGH items across 5 themes (Query / Lint / Data Integrity / Performance / DRY). `FRONTMATTER_RE` bounded 10KB; `refine_page` requires `key:value` between fences (horizontal rules preserved); UTF-8 BOM strip; `check_cycles` capped at 100 via `itertools.islice`; `_group_by_term_overlap` inverted postings index (O(n²) wall removed); `build_graph(pages=...)` param; trends UTC-aware; per-source minimum context floor of 500 chars; feedback eviction timestamp-based; PageRank + centrality carry `status` metadata; slug-index dict for O(1) bare-slug resolution. Full detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-2-2026-04-17).

#### Phase 4.5 — HIGH cycle 1 (2026-04-16)

22 HIGH items / 4 themed commits. Page-file RMW locking across `refine_page` / `append_evidence_trail` / `_persist_contradictions` / `append_wiki_log`; `_check_and_reserve_manifest` replaces unlocked `_is_duplicate_content`; `sanitize_extraction_field` across untrusted ingest fields; `wikilink_display_escape` replaces ad-hoc helpers; XML sentinels in review-checklist; `ERROR_TAG_FORMAT` categories for MCP errors; hybrid vector-index lifecycle with mtime-gated rebuild + `_skip_vector_rebuild` for batch callers; `conversation_context` wired in Claude Code mode. Post-PR 2-round review surfaced 1 major + 8 minors (4 fixed). Full detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-1-2026-04-16).

#### Phase 4.5 — CRITICAL cycle 1 docs-sync (2026-04-16)

2 items + new `scripts/verify_docs.py` pre-push drift check. `pyproject.toml` version aligned 0.9.10 → 0.10.0 with `__init__.py` + README badge; CLAUDE.md stats refreshed (1552 tests / 119 test files / 67 py files / 26 MCP tools). R6 BACKLOG addenda for five deferred review findings. Full detail: [history archive](CHANGELOG-history.md#phase-45--critical-cycle-1-docs-sync-2026-04-16).

---

> **Older history** (Phase 4.5 CRITICAL audit 2026-04-15 + all released versions): see [CHANGELOG-history.md](CHANGELOG-history.md).
