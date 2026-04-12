# GBrain Analysis: High-Value Patterns for llm-wiki-flywheel

*Researched 2026-04-12. Based on deep analysis of [garrytan/gbrain](https://github.com/garrytan/gbrain) — Garry Tan's Postgres-native personal knowledge brain with hybrid RAG search. v0.3.0, TypeScript/Bun, Supabase + pgvector backend.*

---

## Architecture Overview

GBrain is a personal knowledge management system built on Postgres + pgvector with hybrid search. Key differences from llm-wiki-flywheel: database-backed (not file-based), TypeScript (not Python), uses OpenAI embeddings + pgvector for vector search alongside PostgreSQL tsvector for keyword search. Contract-first design where ~30 operations are defined once and both CLI and MCP server are generated from them.

**Page model**: Each page has `compiled_truth` (current best understanding, rewritten on updates) and `timeline` (append-only evidence trail). Separated by `---` in markdown. This is the "intelligence assessment" pattern — what analysts actually do.

**Search**: Multi-query expansion (Haiku generates 2 reformulations) → vector search (HNSW cosine) + keyword search (tsvector) → RRF fusion → 4-layer dedup.

**Chunking**: 3-tier system — recursive (5-level delimiter hierarchy), semantic (Savitzky-Golay smoothing on sentence embeddings), LLM-guided (Haiku topic detection).

**Storage**: 10 Postgres tables (pages, content_chunks, links, tags, timeline_entries, page_versions, raw_data, files, ingest_log, config). All with proper FK cascades and indexes.

---

## High-Value Patterns to Adopt

### 1. Compiled Truth + Timeline Page Structure

**What**: Split each wiki page into two sections:
- **Compiled truth** (top): Current best understanding. REWRITTEN (not appended) when new evidence arrives.
- **Evidence trail** (bottom): Append-only provenance chain. Each entry has date, source file, and summary of what was added/changed.

**Why**: Directly addresses the hardest unsolved problem in `karpathy-llm-knowledge-bases-analysis.md` — epistemic integrity. When `kb_refine_page` rewrites content, the evidence trail shows WHAT changed and FROM WHICH SOURCE. Also enables stale truth detection: if newest evidence trail entry is newer than `updated` frontmatter date, the compiled truth hasn't incorporated recent evidence.

**Implementation sketch** (for llm-wiki-flywheel):
```markdown
---
title: "Transformer Architecture"
type: concept
confidence: stated
source:
  - "raw/papers/attention-is-all-you-need.md"
  - "raw/articles/illustrated-transformer.md"
updated: 2026-04-15
---

The transformer architecture introduces self-attention as a replacement for
recurrence and convolution in sequence transduction models...

## Evidence Trail
- 2026-04-15 | raw/articles/illustrated-transformer.md | Updated: added visual explanation of multi-head attention, positional encoding details
- 2026-04-12 | raw/papers/attention-is-all-you-need.md | Initial extraction: architecture overview, self-attention mechanism, training methodology
```

**Effort**: Low. Add `## Evidence Trail` section during ingest. Existing pages work without it until next compile. Ingest pipeline appends entries; compile/refine rewrites the top section.

**Feeds into**: Phase 5 temporal claim tracking (evidence trail provides the `valid_from` data), answer trace enforcement (citations map to evidence trail entries), inline confidence tags (evidence trail entries can carry confidence).

**Recommended phase**: Phase 4.

### 2. Hybrid Search with RRF Fusion

**What**: Replace BM25-only search with Reciprocal Rank Fusion of BM25 + vector search:
1. Multi-query expansion (Haiku generates 2 semantic reformulations)
2. Embed all query variants (model2vec — local, 8MB, 500x faster than sentence-transformers)
3. Vector search for each embedding (sqlite-vec — SQLite-native, zero infrastructure)
4. BM25 keyword search (existing engine)
5. RRF fusion: `score = Σ(1 / (60 + rank))` across all result lists

**Why**: BM25 and vector search are orthogonal signals. BM25 catches exact terms ("PageRank algorithm"), vectors catch semantics ("methods to rank web pages by importance"). RRF fuses ranked lists from different scoring systems without needing score normalization — it only uses rank positions. The algorithm is ~30 lines.

**gbrain implementation** (core logic):
```python
def rrf_fusion(lists: list[list[Result]], k=60) -> list[Result]:
    scores = {}
    for result_list in lists:
        for rank, result in enumerate(result_list):
            key = result.page_id
            scores.setdefault(key, {"result": result, "score": 0.0})
            scores[key]["score"] += 1.0 / (k + rank)
    return sorted(scores.values(), key=lambda x: -x["score"])
```

**Why this replaces two roadmap items**:
- Subsumes Phase 4 "LLM keyword query expansion with strong-signal skip" — RRF with multi-query expansion gives keyword diversity AND semantic coverage without the strong-signal skip complexity.
- Subsumes Phase 5 "BM25 + LLM reranking" — RRF is strictly cheaper (mathematical, no LLM call per query) and combines two orthogonal signals instead of just reranking one.

**Dependencies**: model2vec (already Tier 1 in `python-library-survey.md`), sqlite-vec (already Tier 1).

**Recommended phase**: Phase 4 (replaces item 5).

### 3. 4-Layer Search Dedup Pipeline

**What**: Post-search deduplication in four stages:

| Layer | Rule | Effect |
|-------|------|--------|
| 1. By source | Keep highest-scoring result per page | Prevents one long page dominating results |
| 2. By text similarity | Jaccard > 0.85 → drop | Removes near-duplicate content |
| 3. By type diversity | No page type > 60% of results | Prevents "all entities" or "all concepts" |
| 4. Per-page cap | Max 2 results per page | Ensures breadth across pages |

**Why**: Zero-cost, pure algorithmic quality improvement. Currently not on any roadmap phase. Prevents the failure mode where a single comprehensive page crowds out diverse results.

**Effort**: ~60 lines of Python. No dependencies. Drop-in addition to `query_wiki`.

**Recommended phase**: Phase 4 (pairs with any search improvement).

### 4. Semantic Chunking with Savitzky-Golay Topic Boundary Detection

**What**: Instead of fixed-size (~600-token) overlapping chunks, detect natural topic boundaries:
1. Split page into sentences
2. Embed each sentence (model2vec — local, fast)
3. Compute cosine similarity between adjacent sentence pairs
4. Apply Savitzky-Golay smoothing (5-window, 3rd-order polynomial) to filter noise
5. Find zero-crossings of 1st derivative → topic boundaries
6. Group sentences at boundaries, recursively split oversized groups
7. Fall back to fixed-size on failure

**Why**: A 2000-word page about "transformer architecture" covers attention, positional encoding, and training. Fixed-size splits these arbitrarily. SG-smoothed semantic chunking splits AT topic boundaries → each chunk is topically coherent → better retrieval precision.

**gbrain's implementation**: ~300 lines including full Gauss-Jordan matrix inversion for the SG filter. Clean, well-documented, portable to Python.

**Recommended phase**: Phase 5 (upgrade to chunk-level BM25 sub-page indexing item).

### 5. Stale Truth Flagging at Query Time

**What**: When returning search results, flag any page where `updated` frontmatter date is older than the newest `source` file's modification time. Display `[STALE]` marker on the result.

**Why**: `kb_lint` already does staleness detection, but only during lint runs. Surfacing staleness AT QUERY TIME is more impactful — the user sees "this answer draws on a page with newer evidence not yet incorporated."

**Effort**: ~10 lines added to `query_wiki`. Compare each result page's `updated` date against its source files' mtimes. Add `stale: bool` to result metadata.

**Recommended phase**: Phase 4 (trivial addition alongside other query improvements).

### 6. Cross-Reference Auto-Linking During Ingest

**What**: When ingesting a source that mentions entities A, B, and C:
- Current behavior: wikilink injection adds `[[A]]`, `[[B]]`, `[[C]]` to the summary page.
- Upgraded behavior: ALSO add `[[B]]` and `[[C]]` mentions to entity A's page (and reciprocally), since they're co-mentioned in the same source.

**Why**: Builds graph density automatically. If a paper discusses both "transformer" and "attention mechanism", those two entities should be linked to each other — not just to the paper's summary page.

**gbrain's approach**: During ingest, for each pair of entities mentioned in the source, create a typed link (knows, works_at, invested_in, founded, references, etc.). The same event appears on ALL mentioned entities' timelines.

**Recommended phase**: Phase 4 or early Phase 5.

---

## Patterns Evaluated but Not Adopted

| Pattern | Why Skip |
|---------|----------|
| Postgres + pgvector backend | File-based approach is intentional — git-tracked, Obsidian-compatible, zero infrastructure |
| OpenAI embeddings ($) | model2vec (local, free, 8MB) is the better fit per python-library-survey.md |
| Supabase dependency ($25/mo) | Adds hosting cost for no benefit at personal KB scale |
| TypeScript/Bun toolchain | Python codebase, no reason to change |
| Contract-first operation definitions | Current MCP + CLI already share underlying functions adequately |
| Pluggable engine interface | Over-engineering for single-storage-backend project |
| Page versioning/revert | Git already provides this for file-based wiki |
| Person/Company/Deal page types | Too VC-domain-specific; entity/concept taxonomy is more general |
| Briefing/Enrich/Migrate skills | Domain-specific (VC/investing), not general knowledge work |
| File storage (binary attachments) | Obsidian handles natively via `raw/assets/` |
| Environment/repo discovery (scan machine for markdown repos) | Single-repo model is intentional |
| Raw data JSONB storage per page | External API enrichment is not a priority |

---

## Roadmap Impact Summary

### Phase 4 changes:
- **Replace** item 5 (LLM keyword expansion with strong-signal skip) → Hybrid search: BM25 + model2vec + RRF fusion (simpler, better, cheaper)
- **Add** 4-layer search dedup pipeline (zero-cost quality)
- **Add** Evidence trail sections in wiki pages (epistemic integrity)
- **Add** Stale truth flagging at query time (~10 lines)

### Phase 5 changes:
- **Remove** BM25 + LLM reranking (subsumed by Phase 4's RRF hybrid search)
- **Upgrade** chunk-level BM25 sub-page indexing → use SG-smoothed semantic chunking instead of fixed-size splits
- **Add** cross-reference auto-linking during ingest (co-mentioned entity pairs)

Net: Phase 4 grows from 5 → 8 items. Phase 5 loses 1 redundant item, gains 1, and 1 gets a better implementation strategy.
