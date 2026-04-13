---
title: "Summary: Karpathy on LLM Knowledge Bases (X post)"
source:
  - "raw/articles/karpathy-x-post.md"
created: 2026-04-13
updated: 2026-04-13
type: summary
confidence: stated
---

# Summary: Karpathy on LLM Knowledge Bases (X post)

**Source:** `raw/articles/karpathy-x-post.md` ([tweet](https://x.com/karpathy/status/2039805659525644595))

## Key Points

1. A large share of Karpathy's LLM token throughput goes into building and querying a personal [[concepts/llm-knowledge-base]], not writing code.
2. Three-layer architecture: curated `raw/` inputs → LLM-compiled `wiki/` → `AGENTS.md` schema.
3. At ~100 articles / ~400K words the pattern needs no vector DB or RAG — structured markdown with LLM-maintained indexes is enough.
4. Output is polymorphic: markdown pages, Marp slide shows, matplotlib images — all viewable in [[entities/obsidian]].
5. LLM-driven "health checks" find inconsistencies, impute missing data via web searches, and surface new article candidates.
6. A vibe-coded [[concepts/naive-search-engine]] serves the wiki directly in a web UI and via CLI as a tool for a larger LLM.

## Entities Mentioned

- [[entities/andrej-karpathy]]
- [[entities/obsidian]]

## Concepts Introduced

- [[concepts/llm-knowledge-base]]
- [[concepts/compile-not-retrieve]]
- [[concepts/naive-search-engine]]
