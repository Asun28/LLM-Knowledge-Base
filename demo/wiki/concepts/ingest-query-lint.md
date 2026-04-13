---
title: "Ingest → Query → Lint"
source:
  - "raw/papers/karpathy-llm-wiki-gist.md"
  - "raw/articles/karpathy-x-post.md"
created: 2026-04-13
updated: 2026-04-13
type: concept
confidence: stated
---

# Ingest → Query → Lint

Karpathy's three-operation cycle for maintaining an LLM knowledge base.

## The Loop

1. **Ingest** — Process a new raw source once; the LLM updates 10–15 related pages so cross-references stay consistent (source: [[raw/papers/karpathy-llm-wiki-gist.md]]).
2. **Query** — Search the compiled wiki; valuable answers get filed back as new pages, compounding knowledge over time.
3. **Lint** — Periodic LLM health checks catch contradictions, orphaned pages, and gaps; Karpathy also uses lint to *impute missing data* via web searches and suggest new article candidates (source: [[raw/articles/karpathy-x-post.md]]).

## Why Three (Not Four)

The gist frames the cycle as **Ingest / Query / Lint**. This project adds a fourth operation, **Evolve**, as a forward-looking gap analysis pass — see [[comparisons/compile-vs-rag]].

## See Also

- [[concepts/llm-knowledge-base]]
- [[concepts/compile-not-retrieve]]
