---
title: "Compile-First Wiki vs. RAG"
source:
  - "raw/papers/karpathy-llm-wiki-gist.md"
  - "raw/articles/karpathy-x-post.md"
created: 2026-04-13
updated: 2026-04-13
type: comparison
confidence: inferred
---

# Compile-First Wiki vs. RAG

Karpathy explicitly positions the LLM knowledge-base pattern against retrieval-augmented generation.

| Dimension | Compile-First Wiki | RAG |
|-----------|-------------------|-----|
| Unit of work | Pages in a markdown wiki | Chunks in a vector index |
| When work happens | At ingest time (once per source) | At query time (every question) |
| Output fidelity | LLM has already read, summarized, cross-linked | LLM stitches fragments per query |
| Human readability | High — plain markdown, viewable in Obsidian | Low — opaque embeddings |
| Debuggability | Trivial — inspect a file | Hard — trace vector matches |
| Scale ceiling | ~100s–low-1000s of pages | Millions of chunks |
| Failure mode | Stale pages, hallucinated cross-links | Irrelevant retrievals, context stuffing |

## When to Use Each

- **Compile-first**: personal or team research KBs where curation is already a habit and the corpus is a few hundred documents.
- **RAG**: enterprise search over millions of chunks where no human is going to curate or maintain summaries.

## Sources

- [[summaries/karpathy-x-post]]
- [[summaries/karpathy-llm-wiki-gist]]
- [[concepts/compile-not-retrieve]]
