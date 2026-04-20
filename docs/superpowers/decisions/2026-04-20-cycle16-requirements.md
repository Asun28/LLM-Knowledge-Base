# Cycle 16 — Requirements + Acceptance Criteria

**Date:** 2026-04-20
**Branch:** `feat/backlog-by-file-cycle16` (to be created at Step 13)
**Scope theme:** Query refinement + Lint quality + Publish polish
**Batch-by-file pattern:** HIGH + MEDIUM + LOW grouped by file per `feedback_batch_by_file` memory.

---

## Problem

Cycle 15 shipped 26 ACs covering authored-by boost, volatility config, source decay wiring, incremental publish, and lint drift/staleness checks. The BACKLOG still lists several explicitly deferred items that form a coherent follow-up:

1. **`evolve/analyzer.py` `suggest_enrichment_targets`** — Phase 4.5 MEDIUM tagged **"AC8-carry (cycle 16)"** — iterate EXISTING pages ranked by status rather than only dead-link targets.
2. **`query/engine.py` low-coverage advisory rephrasings** — deferred from cycle 15 non-goals — scan-tier LLM call proposing 2-3 alternative phrasings instead of a static "Consider rephrasing" string.
3. **`lint/checks.py` duplicate-slug check** — deferred Phase 4.5 MEDIUM — detect near-duplicate slugs (`attention` vs `attention-mechanism`).
4. **`lint/checks.py` inline callout parser** — deferred Phase 4.5 MEDIUM — parse `[!contradiction]` / `[!gap]` / `[!stale]` / `[!key-insight]` markers into aggregate lint counts.
5. **`mcp/core.py` `kb_query` `save_as` parameter** — deferred Phase 4.5 MEDIUM — immediately persist a query answer to `wiki/synthesis/{slug}.md`.
6. **`compile/publish.py` per-page sibling `.txt`/`.json` + `sitemap.xml`** — deferred Phase 4.5 MEDIUM — extend the Karpathy Tier-1 publish surface.

None of these require new external dependencies or architectural layers. All are additive.

## Non-goals

- NOT re-opening architectural BACKLOG items (`kb.errors` hierarchy, `compile_wiki` naming, `refine_page` two-phase audit, vector-index lifecycle, `file_lock` multiprocessing tests, `config.py` god-module split, CLI↔MCP parity, e2e test scaffolding, `models/page.py` dataclass migration) — those need dedicated cycles.
- NOT shipping `kb_merge`, `kb_consolidate`, `kb_delete_source`, `kb_synthesize`, `kb_export_subset`, or `.llmwikiignore` — deferred; separate cycles.
- NOT auto-hooking `kb publish` into `compile_wiki` — the BACKLOG lists this bundled with per-page siblings + sitemap, but tying publish to compile changes the compile contract and merits its own cycle. This cycle adds the NEW publish builders standalone; the auto-hook into compile remains deferred.
- NOT touching `ingest/pipeline.py` fan-out or manifest write order — separate cycles.
- NOT changing output defaults: `kb publish` default formats stay `llms|llms-full|graph|all`; `siblings` and `sitemap` are new opt-in formats.
- NOT migrating the low-coverage advisory to block synthesis entirely — rephrasings are additive to the existing fixed-text refusal; the threshold behavior from cycle 14 AC5 stays unchanged.

## Acceptance criteria (testable pass/fail)

### File 1: `src/kb/config.py`

- **AC1** — New constant `QUERY_REPHRASING_MAX: int = 3` defines the cap on alternative rephrasings surfaced in the low-coverage advisory. Typed, module-scope, no setter.
- **AC2** — New constant `DUPLICATE_SLUG_DISTANCE_THRESHOLD: int = 3` defines the maximum Levenshtein / edit-distance at which two slugs are considered near-duplicates. Typed, module-scope.
- **AC3** — New tuple `CALLOUT_MARKERS: tuple[str, ...] = ("contradiction", "gap", "stale", "key-insight")` defines the recognised inline callout marker names. Typed, module-scope, immutable (tuple).

### File 2: `src/kb/evolve/analyzer.py`

- **AC4** — New function `suggest_enrichment_targets(wiki_dir: Path | None = None, pages_dicts: list[dict] | None = None, *, status_priority: Sequence[str] = ("seed", "developing")) -> list[dict]` iterates EXISTING wiki pages (not dead-link targets, which are already handled by `suggest_new_pages`). Returns list of dicts with keys `{"page_id": str, "status": str, "reason": str}`, sorted by status-priority index (seed before developing before everything else). Pages with `status in {"mature", "evergreen"}` are excluded; pages with no `status` field sort LAST.
- **AC5** — `generate_evolution_report` output grows a new `enrichment_targets` key returning the AC4 function's output (threaded through the existing `pages_dicts` + `wiki_dir` args so no extra disk read).
- **AC6** — `format_evolution_report` appends an `### Enrichment targets` section when `enrichment_targets` is non-empty, listing top 10 targets by status priority with a leading line `N page(s) ranked by status priority (<priority-sequence>):`.

### File 3: `src/kb/query/engine.py`

- **AC7** — New helper `_suggest_rephrasings(question: str, context_pages: list[dict], *, max_suggestions: int = QUERY_REPHRASING_MAX) -> list[str]` calls `call_llm(tier="scan")` with a compact prompt asking for up to `max_suggestions` alternative phrasings grounded in the titles of `context_pages`. Returns `[]` on any LLM failure or when `context_pages` is empty — never raises.
- **AC8** — When the low-coverage refusal branch fires (`coverage_confidence < QUERY_COVERAGE_CONFIDENCE_THRESHOLD`), call `_suggest_rephrasings` with `matching_pages` as context and include the returned list in `result_dict["rephrasings"]` (absent when the refusal did not fire; empty list is valid when the helper returned no suggestions).
- **AC9** — The returned rephrasings MUST NOT include the ORIGINAL question verbatim (case-insensitive, whitespace-normalised match). If the LLM returns one, it is filtered out before return.

### File 4: `src/kb/lint/checks.py`

- **AC10** — New check `check_duplicate_slugs(wiki_dir: Path | None = None, pages: list[Path] | None = None) -> list[dict]` compares every pair of page slugs (filename stem) using a bounded edit-distance implementation. Returns dicts `{"slug_a": str, "slug_b": str, "distance": int, "page_a": str, "page_b": str}` for every pair whose distance <= `DUPLICATE_SLUG_DISTANCE_THRESHOLD` AND > 0. Pairs with identical slugs (distance 0) are excluded (they are already caught by other checks or the filesystem). Distance is computed on the slug-form of the page id (lowercase, hyphen-normalised).
- **AC11** — New helper `parse_inline_callouts(content: str) -> list[dict]` captures Obsidian-style callouts matching the regex `^> \[!(?P<marker>{markers})\][^\n]*$` (multiline mode, case-insensitive marker) where `markers` is alternation of `CALLOUT_MARKERS`. Returns dicts `{"marker": str, "line": int, "text": str}`. `line` is 1-based.
- **AC12** — New check `check_inline_callouts(wiki_dir: Path | None = None, pages: list[Path] | None = None) -> list[dict]` walks pages and returns dicts `{"page_id": str, "marker": str, "line": int, "text": str}` for every callout discovered. Must skip pages that fail to read (log warning) rather than abort the walk (consistent with existing checks).
- **AC13** — Regression test: `check_duplicate_slugs` must flag `attention` vs `attention-mechanism` (distance 10 — above threshold, so NOT flagged) and `attention` vs `attnetion` (distance 2 — flagged). Test includes at least one flagged case and one unflagged case; asserts shape of returned dict.

### File 5: `src/kb/lint/runner.py`

- **AC14** — `run_all_checks` returns report with new keys `duplicate_slugs` and `inline_callouts`, each populated by the respective check function. `summary` counter incremented by `len(duplicate_slugs)` under `warning` severity and `len(inline_callouts)` under `info` severity (existing severity contract preserved; "info" added if not already present).
- **AC15** — `format_report` renders two new sections `## Duplicate slugs` and `## Inline callouts` when non-empty. Format follows the pattern of the existing frontmatter-issues section: header line + one bullet per item.
- **AC16** — When both lists are empty, the sections are OMITTED (not rendered as "None found") — mirrors existing orphan / dead-link behavior.

### File 6: `src/kb/mcp/core.py`

- **AC17** — `kb_query` gains keyword-only argument `save_as: str | None = None`. When `None` or empty, behavior unchanged. When set, treated as the desired slug for a new `wiki/synthesis/{slug}.md` page.
- **AC18** — When `save_as` is provided AND the query synthesised an answer (not a refusal), write a new page at `wiki/synthesis/{slugify(save_as)}.md` with frontmatter `{title: <save_as humanised or original question>, source: [...], created: <today>, updated: <today>, type: synthesis, confidence: inferred}`. Body is the answer text. Use `save_page_frontmatter` (cycle 14 AC16 enforcement point) for the write.
- **AC19** — `save_as` must reject path-traversal attempts. Specifically: `..`, absolute paths, and characters outside `[a-z0-9-]` after slugification are rejected with error string. Reuse the same validation pattern as `_validate_page_id` OR call `slugify` + assert the output equals the normalized input (anti-unicode-homoglyph).

### File 7: `src/kb/compile/publish.py`

- **AC20** — New builder `build_per_page_siblings(wiki_dir: Path, out_dir: Path, *, incremental: bool = False) -> list[Path]` emits `{out_dir}/pages/{page_id}.txt` (title + body plaintext) and `{out_dir}/pages/{page_id}.json` (JSON metadata: title, source, page_id, url, updated, confidence, belief_state, authored_by, status) per page passing the epistemic filter (retracted/contradicted/speculative EXCLUDED — same rule as existing builders). Uses `atomic_text_write` / `atomic_json_write`. Returns list of ALL output paths written (both `.txt` and `.json`).
- **AC21** — New builder `build_sitemap_xml(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path` emits an XML sitemap at `out_path` following the `sitemap.org/schemas/sitemap/0.9` schema: one `<url>` entry per page passing the epistemic filter, each with `<loc>` set to `pages/{page_id}.txt` (relative POSIX — threat T8 pattern) and `<lastmod>` set to the page `updated` frontmatter date (ISO-8601 YYYY-MM-DD). Uses `xml.etree.ElementTree` + `atomic_text_write`.
- **AC22** — Both AC20 and AC21 honour `incremental=True`: skip write when output exists AND is newer than the newest wiki page mtime, reusing the `_publish_skip_if_unchanged` helper. Idempotent: re-running with unchanged inputs leaves output bytes unchanged.

### File 8: `src/kb/cli.py`

- **AC23** — `kb publish --format` accepts two new values: `siblings` and `sitemap`. The existing choice set `{llms, llms-full, graph, all}` becomes `{llms, llms-full, graph, siblings, sitemap, all}`.
- **AC24** — `--format=all` dispatches all five non-all builders (existing three + siblings + sitemap). Honours the existing `--incremental/--no-incremental` flag for all five.

## Blast radius

| Module | Files touched | Risk |
|---|---|---|
| config | `src/kb/config.py` | LOW — three additive constants |
| evolve | `src/kb/evolve/analyzer.py` | LOW — one new function + two existing functions grow one key each |
| query | `src/kb/query/engine.py` | MEDIUM — one new helper + one new result-dict key; calls scan-tier LLM on refusal path only |
| lint | `src/kb/lint/checks.py`, `src/kb/lint/runner.py` | LOW — two net-new checks, one net-new helper; report shape grows two optional keys |
| mcp | `src/kb/mcp/core.py` | MEDIUM — `kb_query` grows a kwarg; path-traversal validation is net-new |
| publish | `src/kb/compile/publish.py` | LOW — two net-new builders mirroring existing three |
| cli | `src/kb/cli.py` | LOW — `--format` choice set grows |
| tests | `tests/test_cycle16_*.py` | LOW — 9 new test files, all isolated via `tmp_wiki` / `tmp_project` fixtures |

**Total:** 8 source files + 9 new test files + CHANGELOG + BACKLOG + CLAUDE.md updates.

## Threat surface preview (for Step 2 Opus threat model)

- Path traversal in `kb_query(save_as=...)` — new user input as a filename component.
- LLM-suggested rephrasings leaking prompt fragments OR the original question (cycle 14 T5 pattern extended).
- Inline callout regex DoS on adversarial page content (catastrophic backtracking).
- Slug distance computation DoS on O(N²) pair iteration when N = page count. Cap: document the O(N²) and keep `N` under reasonable bound; if N > 10,000 emit a warning and skip.
- XML injection in `sitemap.xml` if page URLs or dates contain raw `<` / `>` / `&` — `xml.etree.ElementTree` escapes by default; verify no manual string-cat.
- Per-page siblings filename injection — `page_id` must be slugified already; no dot-dot allowed in output path.

## Measured baseline

- Current full-suite count: **2334 collected / 2327 passed + 7 skipped** (cycle 15 final).
- `main` HEAD: `d8097ec` (cycle 15 Step 16 self-review).
- Working tree: clean.

## Success criterion

- All 24 ACs above verified by at least one behavioural regression test (no `inspect.getsource` / `read_text()` scan assertions — cycle-11 L2 Red Flag).
- Full pytest green; ruff check + format clean.
- PR review R1+R2+R3 (>20 ACs → 3 rounds per `feedback_3_round_pr_review`).
- Zero PR-introduced CVEs (Class B diff empty); existing `diskcache` CVE remains informational.
- CHANGELOG + BACKLOG + CLAUDE.md updated in same cycle.
- Step 16 self-review + skill patch committed before cycle termination.
