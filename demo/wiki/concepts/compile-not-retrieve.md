---
title: "Compile, Don't Retrieve"
source:
  - "raw/papers/karpathy-llm-wiki-gist.md"
created: 2026-04-13
updated: 2026-04-13
type: concept
confidence: inferred
---

# Compile, Don't Retrieve

The core design principle behind Karpathy's LLM Knowledge Base pattern: pre-process raw sources into a structured artifact rather than searching fragments at query time.

## How It Works

- **Retrieval (RAG)** grabs fragments at runtime and asks the LLM to stitch an answer each time. Analogy: `grep`.
- **Compilation** pre-processes raw sources into summaries, entity pages, concept pages, and synthesis. Analogy: `gcc`. Cross-references and contradictions are already resolved before a query arrives (source: [[raw/papers/karpathy-llm-wiki-gist.md]]).
- The compiled wiki is the product, not an intermediate step. It stays human-readable, git-versioned, and debuggable.

## See Also

- [[concepts/llm-knowledge-base]]
- [[comparisons/compile-vs-rag]]
- [[concepts/ingest-query-lint]]
