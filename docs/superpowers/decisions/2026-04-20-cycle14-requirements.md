# Cycle 14 — Requirements + Acceptance Criteria

**Date:** 2026-04-20
**Branch:** `feat/backlog-by-file-cycle14`
**Baseline:** `main` at `d4b227b` — 2140 tests collected.

## Problem

Cycle 13 closed the deferred LOW items (sweep wiring, raw_dir derivation) and set the stage for Phase 5 feature work by migrating read-only frontmatter sites to the cached helper. Three backlog clusters now dominate:

1. **Metadata signals are missing** — BACKLOG Phase 5 HIGH LEVERAGE items for `belief_state`, `authored_by`, and `status` frontmatter fields are all marked "Low effort — one field + rule hook". They add provenance and lifecycle orthogonal to existing `confidence`, and have been waiting for a cycle that touches `kb.models.frontmatter` + lint validation + query ranking.
2. **Query surface gaps** — the coverage-confidence refusal gate, the `CONTEXT_TIER1_BUDGET` 60/20/5/15 split, and the per-platform `SOURCE_DECAY_DAYS` dict are all Phase 5 "Low effort" query/engine tweaks with no shared blockers. They ride on existing hybrid search internals.
3. **Publish surface missing** — Tier-1 recommended next item is `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` publish outputs (BACKLOG §RECOMMENDED NEXT SPRINT Tier 1 #1). Contained blast radius in a new `kb.compile.publish` module + one CLI subcommand.
4. **Deferred cycle-14 targets** — BACKLOG Phase 4.5 MEDIUM lists two specific items (augment write-back frontmatter migration + `_post_ingest_quality` cache hook) pinned by `tests/test_cycle13_frontmatter_migration.py::TestWriteBackOutOfScope`.
5. **Ergonomics gaps** — per-subdir `source_type` inference, `kb search` CLI subcommand, `kb_query save_as` parameter, and inline callout marker lint aggregation are each BACKLOG "Low effort" entries with no cross-dependencies.

This cycle groups the low-effort, low-risk items across ~15 files so the next cycles can focus on the remaining HIGH concurrency cluster.

## Non-goals

- **NOT touching the concurrency cluster** — HIGH items on `compile/compiler.py` (manifest prune race, manifest key normalization), `compile/linker.py` inject_wikilinks cascade race, `ingest/pipeline.py` slug/path collisions, lock-acquisition-order risk are all OUT OF SCOPE. These need a dedicated cycle with cross-process tests.
- **NOT deleting `models/page.py` dataclasses** — grep shows 9 test files reference `WikiPage` / `RawSource` (cycle-8 validation tests depend on `from_post`). Deletion is a separate refactor.
- **NOT splitting `config.py`** — BACKLOG flags the god-module; out-of-scope here, needs dedicated cycle.
- **NOT shipping `SessionStart` hook / file watcher** — hook infrastructure is a separate concern; only the `wiki/hot.md` renderer ships if sized right.
- **NOT shipping `.llmwikiignore` + secret scanner** — security-sensitive, needs its own threat model cycle.
- **NOT shipping `kb_delete_source` / `kb_merge`** — cascade-deletion logic is a separate cycle with its own concurrency review.
- **NOT migrating `load_all_pages` / `ingest_source` / `query_wiki` return types to `WikiPage`** — downstream caller count is too high for this cycle.
- **NOT implementing `ingest/session.py` JSONL auto-ingest** — deferred to a later cycle.

## Acceptance criteria

Grouped by file/module. Each AC is independently testable pass/fail.

### Metadata frontmatter fields (HIGH LEVERAGE — Epistemic Integrity 2.0)

- **AC1** — `src/kb/config.py` adds three frozenset tuples documenting valid values: `BELIEF_STATES = ("confirmed", "uncertain", "contradicted", "stale", "retracted")`, `AUTHORED_BY_VALUES = ("human", "llm", "hybrid")`, `PAGE_STATUSES = ("seed", "developing", "mature", "evergreen")`. No code consumes them yet — purely the vocabulary.
- **AC2** — `src/kb/models/frontmatter.py::validate_frontmatter` accepts absent optional fields (backwards compatible) AND, when present, validates `belief_state`, `authored_by`, `status` against the AC1 tuples. Returns an error string per invalid value. Required-fields list stays unchanged.
- **AC3** — A new test file `tests/test_cycle14_frontmatter_fields.py` covers: (a) all three fields absent → no errors (legacy pages); (b) each field present with a valid value → no error; (c) each field present with an invalid value → one error per field; (d) mixing valid + invalid across the three fields yields exactly the invalid-field errors.

### Query coverage-confidence gate (HIGH LEVERAGE — Epistemic Integrity 2.0)

- **AC4** — `src/kb/config.py` adds `QUERY_COVERAGE_CONFIDENCE_THRESHOLD = 0.45` (float, documented as "mean cosine sim threshold — below this `query_wiki` returns a low-confidence advisory instead of synthesizing").
- **AC5** — `src/kb/query/engine.py::query_wiki` computes a per-call `coverage_confidence: float | None` (mean cosine similarity over the vector hits actually packed into Tier-1 context; `None` when no vector hits are available). When `coverage_confidence is not None and coverage_confidence < QUERY_COVERAGE_CONFIDENCE_THRESHOLD` AND `use_api is False` (default Claude-Code path), the return dict includes a new `low_confidence: True` key and an `advisory: str` field suggesting rephrasing. When the threshold is NOT exceeded (or `coverage_confidence is None` because only BM25 fired), the dict omits both keys (backwards compatible). The `use_api=True` synth path is unchanged — gating applies only to the context-return path.
- **AC6** — `tests/test_cycle14_coverage_gate.py` covers: (a) coverage above threshold → no `low_confidence`/`advisory` keys; (b) coverage below threshold → both keys set; (c) no vector hits (BM25-only) → both keys absent (`None` short-circuits).

### CONTEXT_TIER1_BUDGET 60/20/5/15 split (MEDIUM LEVERAGE — refinement)

- **AC7** — `src/kb/config.py` adds `CONTEXT_TIER1_SPLIT = {"wiki_pages": 60, "chat_history": 20, "index": 5, "system": 15}` (proportional percentages summing to 100; documented as "proportional budget shares under `CONTEXT_TIER1_BUDGET`"). Existing `CONTEXT_TIER1_BUDGET = 20_000` stays unchanged — the split is a proportional lens, not a total bump.
- **AC8** — `src/kb/config.py` adds `tier1_budget_for(component: str) -> int` returning `int(CONTEXT_TIER1_BUDGET * CONTEXT_TIER1_SPLIT[component] / 100)`. Invalid component raises `ValueError`. No existing query/engine.py call-site is migrated in this cycle (too much risk); the helper ships as a documented utility.
- **AC9** — `tests/test_cycle14_tier1_split.py` covers: (a) all four components return non-zero budgets; (b) components sum to exactly `CONTEXT_TIER1_BUDGET` (rounding-safe); (c) invalid component raises `ValueError`.

### Per-platform SOURCE_DECAY_DAYS (MEDIUM LEVERAGE — refinement)

- **AC10** — `src/kb/config.py` adds `SOURCE_DECAY_DAYS: dict[str, int]` with entries: `huggingface.co: 120, github.com: 180, stackoverflow.com: 365, arxiv.org: 1095, wikipedia.org: 1460, openlibrary.org: 1825`. Plus `SOURCE_DECAY_DEFAULT_DAYS = STALENESS_MAX_DAYS` (existing 90-day fallback).
- **AC11** — `src/kb/config.py` adds `decay_days_for(source_ref: str | None) -> int` helper that lowercases the ref, splits on `/` to extract the first domain-like token, matches against `SOURCE_DECAY_DAYS` keys (substring / suffix match), and returns the first match's days or `SOURCE_DECAY_DEFAULT_DAYS`. Does NOT reach into `_flag_stale_results` — migration of the call site is out of scope this cycle; the helper ships as the vocabulary.
- **AC12** — `tests/test_cycle14_source_decay.py` covers: (a) every domain in `SOURCE_DECAY_DAYS` returns its value; (b) an unknown domain returns default; (c) `None`/empty returns default; (d) a URL-style ref (`https://arxiv.org/abs/2401.12345`) resolves to the arxiv value.

### Per-subdir source_type inference (MEDIUM LEVERAGE — ergonomics)

- **AC13** — `src/kb/config.py` derives `SOURCE_TYPE_INFERENCE_MAP: dict[str, str]` from the existing `SOURCE_TYPE_DIRS` (inverted: map subdir name → source_type string). Documented as "source_type inferred from immediate parent directory when not explicitly passed".
- **AC14** — `src/kb/ingest/pipeline.py::ingest_source` gains a new helper `_infer_source_type(path: Path) -> str | None` that checks the first path-part matching `SOURCE_TYPE_INFERENCE_MAP` keys (path-parts scanned in order, first match wins). When the caller passes `source_type=None`, the helper result supersedes the existing ValueError; if the helper returns `None`, the existing ValueError fires.
- **AC15** — `tests/test_cycle14_type_inference.py` covers: (a) path under `raw/papers/foo.pdf` + `source_type=None` → `"paper"`; (b) path with no matching subdir + `source_type=None` → existing ValueError; (c) explicit `source_type="article"` on a `raw/papers/` path still uses `"article"` (explicit wins); (d) `raw/captures/foo.md` → `"capture"`.

### Frontmatter-preserving save wrapper (PREREQ for AC18, closes cycle-7 R1 M3 pattern)

- **AC16** — `src/kb/utils/pages.py` adds `save_page_frontmatter(path: Path, post: frontmatter.Post) -> None` wrapper that calls `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)`. Single call site semantics: preserves insertion order of `post.metadata` keys so downstream YAML-diff tools don't regress (cycle-7 R1 Codex M3 lesson).
- **AC17** — `tests/test_cycle14_save_frontmatter.py` covers: (a) round-trip of `title, source, created, updated, type, confidence` stays in insertion order; (b) extra metadata keys round-trip in insertion order; (c) round-trip preserves body content verbatim.

### Augment write-back migration (closes deferred cycle-14 target)

- **AC18** — `src/kb/lint/augment.py` migrates the three write-back sites (`_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`) to use `save_page_frontmatter` from AC16. Each site still reads via uncached `frontmatter.load` (required — the cached helper can't return a mutable Post), but writes go through the key-order-preserving wrapper. Comments at those sites updated to reference cycle-14 AC18 and the sort_keys-False guarantee; the `BACKLOG cycle-14-target` reference is resolved.
- **AC19** — `tests/test_cycle14_augment_key_order.py` covers: (a) `_mark_page_augmented` on a page with pre-existing non-alphabetical metadata preserves key order after write-back; (b) `_record_verdict_gap_callout` preserves key order; (c) `_record_attempt` preserves key order.

### Publish outputs (Tier-1 recommended — HIGH LEVERAGE)

- **AC20** — New module `src/kb/compile/publish.py` exposes three pure functions (no side effects beyond writing requested files):
  - `build_llms_txt(wiki_dir: Path, out_path: Path) -> Path` — one-line-per-page index `title — source_refs — updated_iso` grouped by `type:` subsection; deterministic order (page_id ascending); output is a plain-text file.
  - `build_llms_full_txt(wiki_dir: Path, out_path: Path) -> Path` — same ordering, full rendered body per page separated by `\n\n---\n\n`; hard size cap at 5 MB (returns truncated with a `[TRUNCATED — {N} pages remaining]` footer); no frontmatter included in body.
  - `build_graph_jsonld(wiki_dir: Path, out_path: Path) -> Path` — JSON-LD serialization using `@context: "https://schema.org/"` with `@graph` containing nodes for each page (`@type: CreativeWork`, `name`, `url: path/to/page.md`, `dateModified: updated`) and edges expressed as `citation` arrays on each node. Wikilinks inferred from body via existing `kb.utils.text.extract_wikilinks`.
- **AC21** — `src/kb/cli.py` adds `kb publish [--out-dir PATH] [--format llms|llms-full|graph|all]` subcommand. Defaults: `--out-dir PROJECT_ROOT/outputs` (consistent with Phase 4.11 outputs/), `--format all`. Existing short-circuit preserved.
- **AC22** — `tests/test_cycle14_publish.py` covers: (a) `build_llms_txt` output has one line per page, grouped under type headers, ordered by page_id; (b) `build_llms_full_txt` output separates pages by horizontal rule and truncates with footer at size limit; (c) `build_graph_jsonld` output parses as valid JSON with `@context`/`@graph` fields; (d) `kb publish --format llms` writes exactly one file.

### Status frontmatter ranking (MEDIUM LEVERAGE — refinement)

- **AC23** — `src/kb/query/engine.py` applies a +5% score boost to pages whose frontmatter `status` is `mature` or `evergreen` during the final ranking step. Boost is gated on the field being present AND having a valid value from AC1; absent/invalid → no boost (backwards compatible). Implementation is a small multiplier in the existing dedup/ranking path, not a new scoring system.
- **AC24** — `tests/test_cycle14_status_boost.py` covers: (a) two otherwise-equal pages with and without `status: mature` → boosted page ranks first; (b) `status: seed` applies no boost; (c) invalid status value applies no boost.

### Documentation

- **AC25** — `CHANGELOG.md [Unreleased]` adds a "Phase 4.5 -- Backlog-by-file cycle 14" section covering all ACs.
- **AC26** — `BACKLOG.md` deletes the closed items: belief_state + authored_by + status frontmatter (Phase 5 HIGH LEVERAGE Epistemic Integrity 2.0), coverage-confidence gate (Phase 5 HIGH LEVERAGE), CONTEXT_TIER1 split (Phase 5 MEDIUM LEVERAGE refinement), SOURCE_DECAY_DAYS (Phase 5 MEDIUM LEVERAGE refinement), per-subdir ingest rules (Phase 5 HIGH LEVERAGE Ambient Capture), /llms.txt + /llms-full.txt + /graph.jsonld (Phase 5 HIGH LEVERAGE Output-Format Polymorphism), augment write-back cycle-14-target (Phase 4.5 MEDIUM), status ranking hook (Phase 5 MEDIUM LEVERAGE Page Lifecycle).
- **AC27** — `CLAUDE.md` adds notes for the three new frontmatter fields (in the Wiki Page Frontmatter Template section), the `kb publish` command, and the `save_page_frontmatter` utility. Tool/test count updated.

## Blast radius

**Files touched (12 source files + 6 new/updated test files):**

- `src/kb/config.py` — 7 new constants + 2 new helpers (tier1_budget_for, decay_days_for) + 1 derived dict
- `src/kb/models/frontmatter.py` — 3 new validation blocks in `validate_frontmatter`
- `src/kb/query/engine.py` — coverage-confidence gate in `query_wiki` result path; status ranking boost in dedup
- `src/kb/ingest/pipeline.py` — `_infer_source_type` helper + call-site in `ingest_source`
- `src/kb/utils/pages.py` — `save_page_frontmatter` wrapper
- `src/kb/lint/augment.py` — 3 write-back sites migrated to use `save_page_frontmatter`
- `src/kb/compile/publish.py` — NEW module (3 builder functions)
- `src/kb/cli.py` — `kb publish` subcommand
- `CHANGELOG.md`, `BACKLOG.md`, `CLAUDE.md` — docs

**Tests (6 new files):**

- `tests/test_cycle14_frontmatter_fields.py` (AC3)
- `tests/test_cycle14_coverage_gate.py` (AC6)
- `tests/test_cycle14_tier1_split.py` (AC9)
- `tests/test_cycle14_source_decay.py` (AC12)
- `tests/test_cycle14_type_inference.py` (AC15)
- `tests/test_cycle14_save_frontmatter.py` (AC17)
- `tests/test_cycle14_augment_key_order.py` (AC19)
- `tests/test_cycle14_publish.py` (AC22)
- `tests/test_cycle14_status_boost.py` (AC24)

**Dependencies:** no new third-party packages; all ACs ride on existing stdlib + `frontmatter` + `networkx`.

**BACKLOG items closed:** ≈ 10 distinct entries (some ACs close multiple related entries — e.g. AC20-AC22 closes 3 separate BACKLOG bullets for llms.txt / llms-full.txt / graph.jsonld).

## Success metrics

- All 24 ACs land green (one test module per AC group, ≈ 60+ new assertions total).
- Full suite: 2140 → 2200+ tests, all passing.
- Zero class-B PR-introduced CVEs (new module is stdlib-only for publish.py; no new deps).
- `kb publish --format all` on the real wiki produces non-empty files for all three formats.
- CHANGELOG + BACKLOG + CLAUDE.md all reflect the shipped changes before Step 13.
