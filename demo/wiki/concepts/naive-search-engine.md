---
title: "Naive Search Engine Over the Wiki"
source:
  - "raw/articles/karpathy-x-post.md"
created: 2026-04-13
updated: 2026-04-13
type: concept
confidence: stated
---

# Naive Search Engine Over the Wiki

Karpathy's hand-rolled search layer sitting between his wiki and the LLM agents querying it.

## What It Does

- "I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries." (source: [[raw/articles/karpathy-x-post.md]]).
- Dual surface: human-facing web UI *and* CLI tool for LLM consumption.
- Deliberately naive — no vector DB at ~100-article scale.

## See Also

- [[concepts/llm-knowledge-base]]
- [[concepts/compile-not-retrieve]]
