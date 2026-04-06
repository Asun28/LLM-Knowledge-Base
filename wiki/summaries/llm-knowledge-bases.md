---
title: "LLM Knowledge Bases"
source:
  - raw/articles/karpathy-llm-knowledge-bases-tweet.md
created: 2026-04-06
updated: 2026-04-06
type: summary
confidence: stated
---

# LLM Knowledge Bases

**Author:** Andrej Karpathy


## Overview

LLMs can be used to build and maintain personal knowledge bases by compiling raw source documents into structured, interlinked markdown wikis, replacing traditional RAG approaches with LLM-maintained indexes and summaries.


## Key Claims

- LLMs are effective at compiling raw sources into structured wiki pages
- Obsidian serves well as a frontend IDE for viewing LLM-maintained wikis
- RAG is unnecessary at small scale (~100 articles, ~400K words) when LLMs auto-maintain index files
- LLM health checks can find inconsistent data and suggest new connections
- Query outputs can be filed back into the wiki to enhance it incrementally
- The natural next step is synthetic data generation and finetuning


## Entities Mentioned

- [[entities/andrej-karpathy|Andrej Karpathy]]
- [[entities/obsidian|Obsidian]]
- [[entities/marp|Marp]]
- [[entities/matplotlib|matplotlib]]


## Concepts

- [[concepts/llm-knowledge-base|LLM Knowledge Base]]
- [[concepts/compile-not-retrieve|Compile-not-retrieve]]
- [[concepts/rag|RAG]]
- [[concepts/wiki-compilation|Wiki compilation]]
- [[concepts/incremental-compilation|Incremental compilation]]
- [[concepts/knowledge-linting|Knowledge linting]]
- [[concepts/synthetic-data-generation|Synthetic data generation]]
- [[concepts/finetuning|Finetuning]]
