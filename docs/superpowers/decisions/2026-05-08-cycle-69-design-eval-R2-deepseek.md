# Cycle 69 — Step 4 R2 Design Eval (DeepSeek V4 Pro, cross-family)

**Date:** 2026-05-08
**Reviewer:** DeepSeek V4 Pro (`deepseek-rescue` subagent)
**Agent ID:** `a34427873efd993b0`
**Duration:** ~6.2 minutes
**Verdict:** REJECT (mixed-quality — 1 valid signal of 4 MAJORs)

## Verdict summary

R2 returned REJECT with 4 MAJORs. Primary-session fact-check found 3 of 4 MAJORs HALLUCINATED with grep evidence. 1 MAJOR (AC08 BACKLOG drift) was PARTIALLY VALID and surfaced 1 genuine new finding (Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` entry shipped via cycle-68 AC04) that R1 missed. That finding promoted to **new AC22 / amendment A5** in the Step 5 design lock.

## R2 MAJORs

### M1 — AC04 build_graph reconciliation FAILED [HALLUCINATED]

R2 claimed: *"DeepSeek found 9 call sites (not claimed 5), with 3 missing `pages=` parameter. This breaks graph construction consistency and cache invariants."*

**Primary-session fact-check:** `Grep -n "build_graph\b" src/kb/` returned the following call sites:

- `evolve/analyzer.py:29` — `build_graph(wiki_dir, pages=pages)` ✓ supplies pages=
- `evolve/analyzer.py:360` — `build_graph(wiki_dir, pages=pages_dicts)` ✓ supplies pages=
- `query/engine.py:408` — `build_graph(wiki_dir, pages=preloaded_pages)` ✓ supplies pages=
- `graph/cache.py:127, 138` — internal cache (intentional bypass)
- `graph/builder.py:28` — function definition
- Other matches: `noqa: F401` import-only (`graph/export.py:9`); re-export shims (`graph/__init__.py`, `kb/__init__.py`); docstring/comment refs (`compile/linker.py:166`, `utils/markdown.py:46`, `utils/pages.py:128`, `review/refiner.py:134`, `lint/semantic.py:138`, `lint/checks/orphan.py:34`).

R2's claim of "9 call sites with 3 missing pages= in cli.py and lint/runner.py" is HALLUCINATED:
- `cli.py` calls `build_graph_jsonld` (different function with `_jsonld` suffix), NOT `build_graph`.
- `lint/runner.py` has zero `build_graph` calls.

**Verdict:** REJECTED. Cycle-69 AC04 deletion is sound as-is.

### M2 — AC06 AST guard escape route [OVER-ESCALATED]

R2 claimed: *"The wrapper `kb.graph.cache.get_graph()` is NOT caught by the AST pattern that only looks for direct `Name("build_graph")` calls. Calls via `Attribute(..., attr="get_graph")` bypass the guard entirely — a sandbox escape."*

**Primary-session fact-check:** R1 N5 already classified the `get_graph` walk as defensive-dead. The in-scope modules for AC06 are `query/engine.py` and `evolve/analyzer.py`. Neither calls `kb.graph.cache.get_graph`; both call `build_graph` directly with `pages=`. The brainstorm Q2 explicitly walks `Call(func=Name("build_graph"))` AND `Call(func=Attribute(...,attr="get_graph"))` — the second branch is defensive coverage, not an escape vector.

**Verdict:** REJECTED. Not a real escape.

### M3 — AC13 determinism violation [HALLUCINATED]

R2 claimed: *"`build_extraction_prompt()` calls `datetime.now()` and `os.environ.get()`, making output non-deterministic for identical inputs. Breaks snapshot caching contracts."*

**Primary-session fact-check:** Read `src/kb/ingest/extractors.py:276-333`. The function takes `(content, template, purpose)` and produces a deterministic f-string from `template["extract"]` + `template.get("name","document")` + `template.get("description","")` + `wrap_purpose(purpose)` + `_escape_source_document_fences(content)`. `Grep "datetime.now\|os.environ.get" src/kb/ingest/extractors.py` returned ZERO matches.

R2 conflated AC13 (extraction prompt — deterministic) with AC14 (contradictions block — `pipeline.py:207` `date.today()`, the actual non-determinism flagged by R1 M3 / promoted A3).

**Verdict:** REJECTED. AC13 needs no defensive monkeypatch — function is genuinely deterministic.

### M4 — AC08 BACKLOG drift uncleaned [PARTIALLY VALID]

R2 claimed: *"7 stale references remain across CHANGELOG.md, docs/reference/, and CLAUDE.md (e.g., 'Phase 6 LOW mcp/app.py', 'Phase 4.5 HIGH build_graph'). Documentation mismatch."*

**Primary-session fact-check:** Of R2's 7 claims:
- 4 are cycle-68 self-ref entries (AC02 + AC03 + AC04 already plan to delete).
- 2 are historical narrative in `CHANGELOG-history.md` (correct, not drift — historical statements remain accurate after the entry is removed from BACKLOG).
- **1 is genuinely stale and previously unenumerated:** `BACKLOG.md:130-131` Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` `check_duplicate_slugs` allowlist entry. Verified shipped via cycle-68 AC04 (cleanup-comment line 53 explicitly states `"duplicate-slug allowlist externalization (Phase 4.5 MEDIUM) → SHIPPED cycle 68 AC04"`; live overlay at `src/kb/lint/checks/duplicate_slug.py:64-78`).

**Verdict:** PROMOTED → new **AC22** + amendment **A5**.

## R2 MINORs (selectively addressed)

- **AC05 edge-case URL-encoded `%2e%2e` / unicode:** OOS — `_validate_page_id` never URL-decodes; the containment check at `mcp/app.py:312` catches actual escapes via `resolve()` + `relative_to()`.
- **AC14 private API exposure:** R2 used wrong name (`_append_contradiction` vs actual `_persist_contradictions`). Tests call via public `ingest_source` per brainstorm Q4. Acceptable.
- **AC09 trends_module testability debt:** low concern — `compute_verdict_trends` reads JSON, not wiki fixtures. R1 M1 / A1 covers the genuine vacuousness issue.
- **AC07 fold collateral:** vague; primary-session re-grep confirmed all 4 fold sources have no cross-file imports.

## Cross-family review trial telemetry (May 2026)

- R2 owner: DeepSeek V4 Pro (`deepseek-rescue` subagent with `--model deepseek-v4-pro`)
- Cross-family precision: 1 of 4 MAJORs valid / 4 = 25% precision
- Primary-session fact-check rate: 3/3 hallucinations corrected (100% catch rate)
- Time elapsed: ~6.2 min (within 5-7 min cycle-24 L5 budget)

**Trial implication (per `feedback_r2_codex_static_analysis_value`):** keep R2 cross-family on for the unique-promote signal — R2 caught BACKLOG drift R1 missed (AC22 / A5). But primary-session fact-check gate is mandatory: R2's hallucination rate (3/4 MAJORs) would have led to false REJECT without the gate. Cycle-68 R2 Codex caught 4 MAJORs of 4 (100% precision in that cycle); cycle-69 R2 DeepSeek 1 of 4 (25%). Cross-vendor variance is real.

## Identity verification (`feedback_deepseek_identity_anchor`)

DeepSeek V4 Pro self-identifies as Claude due to training contamination. The `deepseek-rescue` CLI auto-anchors identity. Per dispatch convention: `--model deepseek-v4-pro` was passed explicitly. R2 output did NOT exhibit identity confusion in this run.
