# Karpathy on LLM Knowledge Bases (X post)

**Author:** Andrej Karpathy
**Source:** https://x.com/karpathy/status/2039805659525644595
**Date:** 2026-04-03
**Captured via:** manual paste (tweet)

---

A large fraction of my recent LLM token throughput goes into building and querying an LLM-first personal knowledge base — not writing code. The pattern is simple enough to describe in a tweet.

## Raw data → compiled wiki

Raw sources (papers, articles, repos, datasets, images) go into a `raw/` directory. I curate what enters. The LLM reads `raw/` but never writes to it.

The LLM then "compiles" these sources into an interlinked markdown wiki: summaries, entity pages, concept pages, comparisons, synthesis. The wiki is the compiled artifact; `raw/` is the source of truth.

At ~100 articles / ~400K words I don't need a vector database or a RAG pipeline. Structured markdown with LLM-maintained indexes is simpler, more transparent, and debuggable.

## Output formats

Instead of getting answers in text/terminal, I like to have it render markdown files for me, or slide shows (Marp format), or matplotlib images, all of which I then view again in Obsidian. You can imagine many other visual output formats depending on the query.

## Health checks and maintenance

I've run some LLM "health checks" over the wiki to e.g. find inconsistent data, impute missing data (with web searchers), find interesting connections for new article candidates.

## Search

I vibe coded a small and naive search engine over the wiki, which I both use directly (in a web ui), but more often I want to hand it off to an LLM via CLI as a tool for larger queries.

## Schema

The schema is kept up to date in `AGENTS.md`.

## Why this works

LLMs don't get bored, don't abandon projects, don't forget updates, and don't hesitate to touch 20 files at once. Wikis always died on maintenance cost. That cost is now near-zero. Knowledge compounds from use — every query answered well becomes a new wiki page.
