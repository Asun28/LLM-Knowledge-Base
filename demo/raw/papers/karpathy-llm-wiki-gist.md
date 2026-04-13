# LLM Wiki — Core Concept Summary

**Author:** Andrej Karpathy
**Source:** https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
**Date:** 2026-04-04
**Captured via:** WebFetch

---

## The Main Idea

Karpathy proposes building **persistent, LLM-maintained knowledge bases** rather than relying on retrieval-augmented generation (RAG). The key insight: "the wiki is a persistent, compounding artifact" where an LLM incrementally integrates new sources into structured markdown files instead of re-deriving answers from scratch each time.

## Three-Layer Architecture

**Raw sources** (immutable documents) → **The wiki** (LLM-generated, interconnected markdown) → **The schema** (configuration file defining wiki structure and workflows).

## Core Operations

1. **Ingest** — Process new sources once, updating 10–15 related wiki pages automatically.
2. **Query** — Search compiled knowledge, file valuable answers back as new pages.
3. **Lint** — Periodic health checks for contradictions, orphaned pages, and gaps.

## Why This Works

The human curates sources and asks good questions. The LLM handles the maintenance burden — updating cross-references, tracking contradictions, maintaining consistency across dozens of pages. As Karpathy notes: "LLMs don't get bored, don't forget to update a cross-reference."

## Practical Tools

- `index.md` — Content catalog organized by category.
- `log.md` — Append-only chronological record.
- Optional: Obsidian for browsing, `qmd` for semantic search.

The pattern deliberately stays abstract — implementation details depend on domain, preferences, and specific LLM choice. The core principle: **persistent compilation beats ephemeral retrieval.**
