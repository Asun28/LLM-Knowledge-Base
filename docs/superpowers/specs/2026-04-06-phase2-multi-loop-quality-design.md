# Phase 2 Design: Multi-Loop Quality System

**Date:** 2026-04-06
**Status:** Approved
**Trigger:** 68 wiki pages (past 50-page threshold)
**Branch:** `phase2-quality`

---

## 1. Problem Statement

Phase 1 (v0.3.0) delivers a functional 5-operation cycle (Ingest, Compile, Query, Lint, Evolve) with 68 wiki pages, 78 tests, and a 12-tool MCP server. Three weaknesses emerge at scale:

1. **No quality gate on ingestion** — pages are created in a single pass with no review. Unsourced claims, thin entity stubs, and missing connections go undetected.
2. **Lint is mechanical only** — 5 deterministic checks (dead links, orphans, staleness, frontmatter, source coverage) miss semantic issues: contradictions, incomplete coverage, unfaithful summaries.
3. **No feedback signal** — queries succeed or fail silently. No way to know which pages are trustworthy vs. stale/wrong.

## 2. Core Design Principle

**Claude Code IS the orchestrator.** The MCP server prepares context and executes writes. Claude Code handles all semantic reasoning. The "multi-loop supervision" is Claude Code deciding which tools to call next based on findings.

```
Claude Code Session (LLM reasoning)
    |
    |-- MCP Tool Calls (context preparation + writes)
    |       |
    |       |-- kb.review   (page + source context)
    |       |-- kb.feedback  (query outcome storage)
    |       |-- kb.lint      (mechanical + semantic contexts)
    |       |-- kb.ingest    (extraction + page creation)
    |
    |-- Sub-agents (context-isolated review)
            |
            wiki-reviewer agent (Actor-Critic pattern)
```

**Implications:**
- No LangGraph, no DSPy, no external orchestration framework
- Python modules handle I/O, hashing, indexing, and context assembly
- Claude Code handles evaluation, decision-making, and loop control
- API mode (`use_api=true`) remains available for headless/automated runs
- **Cleanup:** Remove `langgraph`, `dspy`, `langchain*`, `langsmith` from `requirements.txt` (currently unused, ~40 transitive deps). Move to `requirements-experimental.txt` if needed for Phase 3 experimentation.

## 3. Four Phase 2 Patterns

### 3.1 Multi-Loop Supervision for Lint

**Current state:** `lint/runner.py` runs 5 mechanical checks, returns a flat report.

**Phase 2:** Two tiers of lint checks.

**Tier 1 — Mechanical (existing, instant, zero API cost):**
- `check_dead_links` — wikilinks to non-existent pages
- `check_orphan_pages` — pages with no incoming links
- `check_staleness` — pages not updated within 90 days
- `check_frontmatter` — YAML frontmatter validation
- `check_source_coverage` — raw sources not referenced in wiki

**Tier 2 — Semantic (new, LLM-powered via Claude Code):**

| Check | Tool returns | Claude Code evaluates |
|-------|-------------|----------------------|
| Source fidelity | Page content + raw source side-by-side | Does each claim trace to a source passage? |
| Cross-page consistency | 2-5 related pages grouped by topic | Do these pages contradict each other? |
| Completeness | Page content + source + extraction template | Are key source claims missing from the page? |

**Supervision loop (Claude Code-orchestrated):**
1. `kb_lint()` returns mechanical report
2. For each error/warning, Claude Code decides: fix mechanically or investigate deeper
3. `kb_lint_deep(page_id)` returns page + source for fidelity evaluation
4. If issues found: `kb_refine_page(page_id, updated_content)` applies fix
5. After fixes: re-run affected mechanical checks to verify
6. `kb_lint_consistency()` returns related pages for contradiction scan
7. Log findings to `wiki/contradictions.md`
8. Max 3 lint-fix-relint rounds before stopping

**New module: `src/kb/lint/semantic.py`**

Functions:
- `build_fidelity_context(page_id, wiki_dir, raw_dir) -> dict` — returns page content paired with all referenced source content. Includes claim extraction (sentences ending with factual assertions) for targeted checking.
- `build_consistency_context(page_ids, wiki_dir) -> dict` — groups related pages and returns paired content for contradiction detection. Auto-selects if no page_ids given, using three grouping strategies in priority order:
  1. Pages sharing raw sources (from frontmatter `source:` fields)
  2. Pages connected by wikilinks (from `build_graph()`)
  3. Pages with high term overlap (reuse logic from `evolve/analyzer.py:find_connection_opportunities`)
  Deduplicates across strategies and caps each group at `MAX_CONSISTENCY_GROUP_SIZE`.
- `build_completeness_context(page_id, wiki_dir, raw_dir) -> dict` — returns source content alongside page content, highlighting source sections not reflected in the page.

**Change-gated optimization:** Only check pages that have changed since last review. A review manifest at `.data/review_manifest.json` tracks both source and page hashes:

```json
{
  "page_id": {
    "last_reviewed": "2026-04-06",
    "source_hash": "abc123",
    "page_hash": "def456"
  }
}
```

Skip only when **both** hashes match. Pages can change independently of their sources (wikilink fixes, frontmatter corrections, content added via `_update_existing_page` when a new source mentions an existing entity). Reuses `content_hash()` from `kb.utils.hashing` for the page file.

### 3.2 Actor-Critic Compile

**Current state:** `kb_ingest(extraction_json=...)` creates pages in one pass with no review.

**Phase 2:** After ingestion, a separate Claude Code sub-agent reviews the output. Context isolation prevents agreeableness bias.

**Architecture:**

```
Main Session (Actor):
  1. Read source -> extract -> kb_ingest(extraction_json)
  2. Pages created
  3. Dispatch wiki-reviewer sub-agent
  4. Receive review findings
  5. Act on findings (fix via kb_refine_page or accept)

Reviewer Sub-agent (Critic):
  - Receives: list of page_ids to review
  - Calls kb_review_page(page_id) for each page
  - Evaluates against source, checklist (see below)
  - Returns structured findings JSON
  - Read-only: cannot edit pages
```

**Review checklist (returned by `kb_review_page`):**
1. Every claim traces to a specific source passage
2. Entities and concepts correctly identified
3. Wikilinks resolve to existing pages
4. Confidence level matches evidence strength
5. No hallucinated facts beyond source material
6. Title accurately reflects content

**Important distinction:** The `kb_review_page` MCP tool returns **raw context** — page markdown, source text, and checklist questions as plain text. The structured JSON review below is produced by **Claude Code or the wiki-reviewer agent** reasoning over that context. `review/context.py` builds a text prompt, not a structured review.

**Expected review output format (produced by Claude Code / wiki-reviewer agent):**
```json
{
  "verdict": "approve | revise | reject",
  "fidelity_score": 0.85,
  "issues": [
    {
      "severity": "error | warning | info",
      "type": "unsourced_claim | missing_info | wrong_confidence | broken_link",
      "description": "Claim X not found in source",
      "location": "line or section reference",
      "suggested_fix": "Remove claim or add source reference"
    }
  ],
  "missing_from_source": ["Key point A not represented", "..."],
  "suggestions": ["Add wikilink to [[concepts/foo]]", "..."]
}
```

**Agent definition: `.claude/agents/wiki-reviewer.md`**

```yaml
---
name: wiki-reviewer
description: Independent wiki page quality reviewer (Critic role)
model: sonnet
---
```

The agent is instructed to evaluate strictly against source material, flag confidence:stated claims that are actually inferences, and return structured JSON findings. It has access to: `kb_review_page`, `kb_read_page`, `kb_search`, `kb_list_pages`, `Read`.

### 3.3 Query Feedback Loop

**Current state:** `kb_query(question)` returns context for Claude Code to synthesize. No learning signal.

**Phase 2:** Record query outcomes, build a reliability map.

**Flow:**
1. User asks question
2. `kb_query(question)` returns context
3. Claude Code synthesizes answer with citations
4. User reacts (or Claude Code self-evaluates)
5. `kb_query_feedback(question, rating, cited_pages, notes)` records outcome
6. Feedback updates page trust scores

**Rating actions:**
- `useful` — boost trust scores of cited pages
- `wrong` — flag cited pages for priority re-lint, log the wrong claim
- `incomplete` — log coverage gap for `kb_evolve()` to surface

**Storage: `.data/query_feedback.json`**

```json
{
  "entries": [
    {
      "timestamp": "2026-04-06T16:00:00",
      "question": "What is compile-not-retrieve?",
      "rating": "useful",
      "cited_pages": ["concepts/compile-not-retrieve"],
      "notes": ""
    }
  ],
  "page_scores": {
    "concepts/compile-not-retrieve": {
      "useful": 3,
      "wrong": 0,
      "incomplete": 1,
      "trust": 0.75
    }
  }
}
```

**Trust score formula:**
```
trust = (useful + 1) / (useful + wrong + incomplete + 2)
```
Bayesian smoothing with prior of 0.5 (pseudocounts of 1 success, 1 failure). A page with no feedback starts at 0.5.

**Integration points (all in `mcp_server.py`, not in foundation modules — keeps modules independent):**
- `kb_query()` merges trust scores into search results before returning context. Done in `mcp_server.py` (which already calls `search_pages()`), NOT in `query/engine.py`. Wrapped in try/except so corrupted or missing feedback JSON doesn't break queries.
- `kb_lint()` appends a "low-trust pages" section to its report by calling `get_flagged_pages()`. Again in `mcp_server.py`, not `lint/runner.py`.
- `kb_evolve()` appends "incomplete" feedback as coverage gaps by calling `get_coverage_gaps()`. In `mcp_server.py`, not `evolve/analyzer.py`.

### 3.4 Self-Refine on Compile

**Current state:** Pages created in one pass, no self-critique.

**Phase 2:** After creating pages, a bounded Generate-Critique-Refine loop.

**Workflow (Claude Code-orchestrated):**
1. `kb_ingest(source_path, extraction_json=...)` creates pages (Generate)
2. `kb_review_page(page_id)` returns page + source + checklist (Critique context)
3. Claude Code self-critiques: identifies unsourced claims, missing info
4. `kb_refine_page(page_id, updated_content, notes)` applies fix (Refine)
5. Max 2 self-refine rounds. If issues remain after round 2, Claude Code spawns the wiki-reviewer sub-agent for independent evaluation (Actor-Critic escalation)

**The `kb_refine_page` tool:**
- Receives page_id, new markdown body, and revision notes
- Preserves YAML frontmatter (updates `updated` date only)
- Appends revision entry to `.data/review_history.json`
- Appends to `wiki/log.md`: `"Refined {page_id}: {revision_notes}"` (maintains the audit trail convention — every write operation logs)
- Returns confirmation with diff summary and list of affected pages (calls `kb_affected_pages` internally)

### 3.5 Lightweight Reweave

When a page is updated, identify ripple effects.

**`kb_affected_pages(page_id)`** returns:
- Pages that link TO this page (backlinks from existing `build_backlinks()`)
- Pages that share the same raw sources
- Count of affected pages

This is informational only — Claude Code (or the user) decides whether to review affected pages now or later. Full automatic rewriting is Phase 3.

## 4. New MCP Tools

| # | Tool | Signature | Purpose | Pattern |
|---|------|-----------|---------|---------|
| 1 | `kb_review_page` | `(page_id: str) -> str` | Page + sources + checklist for quality review | Actor-Critic, Self-Refine |
| 2 | `kb_refine_page` | `(page_id: str, updated_content: str, revision_notes: str) -> str` | Apply content updates preserving frontmatter | Self-Refine, Actor-Critic |
| 3 | `kb_lint_deep` | `(page_id: str) -> str` | Page + source side-by-side for fidelity check | Multi-Loop Lint |
| 4 | `kb_lint_consistency` | `(page_ids: str) -> str` | Related pages for contradiction detection | Multi-Loop Lint |
| 5 | `kb_query_feedback` | `(question: str, rating: str, cited_pages: str, notes: str) -> str` | Record query success/failure | Query Feedback |
| 6 | `kb_reliability_map` | `() -> str` | Page trust scores from feedback history | Query Feedback |
| 7 | `kb_affected_pages` | `(page_id: str) -> str` | Backlinks + shared sources (ripple effects) | Lightweight Reweave |

**Total tools:** 12 existing + 7 new = 19 (under 20 target).

## 5. New Module Structure

```
src/kb/
  review/                    # NEW
    __init__.py
    context.py               # build_review_context(), build_review_checklist()
    refiner.py               # refine_page(), load/save review history
  feedback/                  # NEW
    __init__.py
    store.py                 # load/save feedback entries, CRUD
    reliability.py           # compute_trust_scores(), get_flagged_pages()
  lint/
    checks.py                # UNCHANGED — existing 5 mechanical checks
    semantic.py              # NEW — build_fidelity_context(), build_consistency_context(),
                             #        build_completeness_context()
    runner.py                # UNCHANGED — run_all_checks() keeps current interface
  mcp_server.py              # MODIFIED — add 7 new tool functions
  config.py                  # MODIFIED — add new path constants
```

### 5.1 Shared Utility: Page-Source Pairing

`kb_lint_deep` and `kb_review_page` both need to pair a wiki page with its raw sources. Rather than duplicating this logic in `lint/semantic.py` and `review/context.py`, extract a shared function into `review/context.py`:

```python
def pair_page_with_sources(page_id, wiki_dir, raw_dir) -> dict:
    """Load a wiki page and all its referenced raw sources.
    
    Returns: { page_content, page_metadata, source_contents: [{path, content}] }
    """
```

Both `build_fidelity_context()` and `build_review_context()` call this, then add their own framing (lint checklist vs. review checklist).

### 5.2 New Data Files

```
.data/
  hashes.json                # EXISTING — content hash manifest
  query_feedback.json        # NEW — feedback entries + per-page scores
  review_manifest.json       # NEW — page_id -> last_reviewed + source_hash
  review_history.json        # NEW — revision log entries
```

### 5.3 Agent Definition

```
.claude/agents/
  wiki-reviewer.md           # NEW — Critic agent for Actor-Critic
```

### 5.4 Config Additions (`kb/config.py`)

```python
# Phase 2 data paths
FEEDBACK_PATH = PROJECT_ROOT / ".data" / "query_feedback.json"
REVIEW_MANIFEST_PATH = PROJECT_ROOT / ".data" / "review_manifest.json"
REVIEW_HISTORY_PATH = PROJECT_ROOT / ".data" / "review_history.json"

# Quality thresholds
LOW_TRUST_THRESHOLD = 0.4       # Pages below this are flagged
SELF_REFINE_MAX_ROUNDS = 2      # Max self-refine iterations
LINT_MAX_ROUNDS = 3             # Max lint-fix-relint cycles
MAX_CONSISTENCY_GROUP_SIZE = 5  # Max pages per consistency check group
```

## 6. Workflow Documentation (CLAUDE.md additions)

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

## 7. Implementation Order

Dependencies determine sequence:

### Phase 2a: Foundation Modules (no inter-dependencies)

| Module | Functions | Depends On |
|--------|-----------|-----------|
| `review/context.py` | `build_review_context()`, `build_review_checklist()` | `config`, `models.frontmatter`, `utils.markdown` |
| `review/refiner.py` | `refine_page()`, `load_review_history()`, `save_review_history()` | `config`, `models.frontmatter` |
| `feedback/store.py` | `load_feedback()`, `save_feedback()`, `add_feedback_entry()` | `config` |
| `feedback/reliability.py` | `compute_trust_scores()`, `get_flagged_pages()`, `get_coverage_gaps()` | `feedback/store` |
| `lint/semantic.py` | `build_fidelity_context()`, `build_consistency_context()`, `build_completeness_context()` | `config`, `graph.builder`, `utils.markdown` |
| `config.py` | New constants | None |

### Phase 2b: MCP Tools (depends on 2a)

All 7 new tools in `mcp_server.py`, using the foundation modules.

### Phase 2c: Agent Definition + CLAUDE.md (depends on 2b)

- `.claude/agents/wiki-reviewer.md`
- CLAUDE.md workflow documentation updates

### Phase 2d: Integration Enhancements (depends on 2b)

- `kb_query()` enhanced with trust scores in context
- `kb_lint()` report enhanced with feedback-flagged pages
- `kb_evolve()` enhanced with feedback-driven coverage gaps

## 8. Testing Strategy

Each new module gets its own test file following the Phase 1 pattern (pytest, fixtures in conftest.py, no API calls):

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_review.py` | ~12 | `pair_page_with_sources`, `build_review_context`, `build_review_checklist`, `refine_page`, review history CRUD, frontmatter preservation, wiki/log.md audit trail |
| `tests/test_feedback.py` | ~10 | Feedback CRUD, trust score computation (Bayesian), flagged pages, coverage gaps, empty state, corrupted JSON resilience |
| `tests/test_lint_semantic.py` | ~10 | Fidelity context building, consistency grouping (3 strategies), completeness context, change-gated skipping (both hashes) |
| `tests/test_mcp_phase2.py` | ~8 | MCP tool integration for all 7 new tools, error cases (missing pages, invalid ratings, corrupted feedback) |

**Target:** ~40 new tests, bringing total to ~118.

All tests use `tmp_wiki` / `tmp_path` fixtures with pre-built pages and sources. No API calls — tests validate context assembly and data operations only.

## 9. What NOT to Do

| Anti-Pattern | Why | Instead |
|---|---|---|
| Put LLM reasoning in Python code | Claude Code IS the LLM; API calls duplicate work and cost money | Tools return context, Claude Code reasons |
| Build state machines in Python | LangGraph-style graphs are for systems without a conversational LLM | Claude Code orchestrates the loop |
| Add quality tier parameters to every tool | Overcomplicates the API surface | Claude Code decides workflow depth based on user intent |
| Auto-trigger Actor-Critic on every ingest | Expensive and unnecessary for small updates | User/Claude chooses: quick vs. thorough |
| Store feedback in SQLite | Premature complexity for current scale | JSON files, migrate at Phase 3 if needed |
| More than 2 self-refine rounds | Diminishing returns; 3-5 rounds is documented convergence ceiling | Cap at 2, then escalate to Actor-Critic |
| Add Reweave auto-updating | Phase 3 feature; too complex without evaluation metrics | Phase 2: flag only, don't auto-rewrite |

## 10. Success Criteria

Phase 2 is complete when:

1. All 7 new MCP tools are implemented and tested
2. `kb_review_page` returns structured page+source context with review checklist
3. `kb_refine_page` updates page content while preserving frontmatter
4. `kb_lint_deep` and `kb_lint_consistency` return semantic check contexts
5. `kb_query_feedback` persists feedback and updates trust scores
6. `kb_reliability_map` returns sorted trust scores
7. `kb_affected_pages` returns backlinks and shared-source pages
8. `.claude/agents/wiki-reviewer.md` enables context-isolated review
9. All ~118 tests pass (78 existing + ~40 new)
10. CLAUDE.md documents Phase 2 workflows
