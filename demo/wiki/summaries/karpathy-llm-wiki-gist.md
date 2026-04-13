---
title: "Summary: Karpathy LLM Wiki Gist"
source:
  - "raw/papers/karpathy-llm-wiki-gist.md"
created: 2026-04-13
updated: 2026-04-13
type: summary
confidence: stated
---

# Summary: Karpathy LLM Wiki Gist

**Source:** `raw/papers/karpathy-llm-wiki-gist.md` ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f))

## Key Points

1. Persistent LLM-maintained knowledge bases are positioned as an alternative to RAG — "the wiki is a persistent, compounding artifact."
2. Three layers: **raw sources** (immutable) → **wiki** (LLM-generated) → **schema** (configuration).
3. Three core operations: **Ingest**, **Query**, **Lint** — each source ingest updates 10–15 related pages; queries file answers back; lint catches contradictions, orphans, and gaps.
4. The human curates sources and asks questions; the LLM owns maintenance — "LLMs don't get bored, don't forget to update a cross-reference."
5. Minimal toolkit: `index.md` catalog, append-only `log.md`, optional Obsidian for viewing, optional `qmd` for semantic search.
6. The gist stays intentionally abstract — it is an "idea file" to be forked and instantiated per-domain, not a concrete implementation.

## Entities Mentioned

- [[entities/andrej-karpathy]]

## Concepts Introduced

- [[concepts/llm-knowledge-base]]
- [[concepts/compile-not-retrieve]]
- [[concepts/ingest-query-lint]]
