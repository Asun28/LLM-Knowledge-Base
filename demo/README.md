# Demo — Folder Structure Reference

This folder mirrors the real project layout with a small working example compiled from Karpathy's two foundational sources:

- `raw/articles/karpathy-x-post.md` — [Karpathy's X post](https://x.com/karpathy/status/2039805659525644595) (2026-04-03)
- `raw/papers/karpathy-llm-wiki-gist.md` — [Karpathy's LLM-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (2026-04-04)

Use it to understand where things go and what a compiled wiki looks like before adding real content of your own.

```
demo/
├── raw/                        ← Immutable source documents (LLM reads, never writes)
│   ├── articles/               ← Web articles, blog posts, tweets
│   │   └── karpathy-x-post.md
│   ├── papers/                 ← Academic papers, gists, spec documents
│   │   └── karpathy-llm-wiki-gist.md
│   ├── repos/                  ← GitHub repo READMEs / code summaries
│   ├── videos/                 ← YouTube transcripts
│   ├── podcasts/               ← Podcast transcripts
│   ├── books/                  ← Book excerpts / notes
│   ├── datasets/               ← CSV / JSON datasets
│   ├── conversations/          ← Chat logs, interviews
│   └── assets/                 ← Images referenced by raw sources
│
└── wiki/                       ← LLM-generated & LLM-maintained pages
    ├── index.md                ← Master catalog (< 500 lines)
    ├── _sources.md             ← raw/ → wiki/ traceability map
    ├── _categories.md          ← Auto-maintained category tree
    ├── log.md                  ← Append-only operation log
    ├── contradictions.md       ← Conflicting claims tracker
    ├── entities/               ← Named things: people, tools, orgs, datasets
    │   ├── andrej-karpathy.md
    │   └── obsidian.md
    ├── concepts/               ← Ideas, techniques, patterns
    │   ├── llm-knowledge-base.md
    │   ├── compile-not-retrieve.md
    │   ├── ingest-query-lint.md
    │   └── naive-search-engine.md
    ├── comparisons/            ← Side-by-side analysis of two+ approaches
    │   └── compile-vs-rag.md
    ├── summaries/              ← One summary per raw source
    │   ├── karpathy-x-post.md
    │   └── karpathy-llm-wiki-gist.md
    └── synthesis/              ← Cross-source insights not in any single raw file
        └── knowledge-compounding-flywheel.md
```

## What you can read here

- **Start with** `wiki/index.md` for the catalog, then `wiki/summaries/` for one-page overviews of each raw source.
- **See cross-source reasoning** in `wiki/synthesis/knowledge-compounding-flywheel.md` — it cites both raw files to make a claim neither source states directly.
- **See the traceability chain** in `wiki/_sources.md` — every wiki page maps back to the raw files that produced it.

## Wiki Page Frontmatter

Every wiki page starts with:

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-13
updated: 2026-04-13
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
---
```

## Five Key Operations

| Operation | What it does |
|-----------|-------------|
| `kb ingest <file>` | LLM reads raw source → creates/updates wiki pages |
| `kb compile` | Hash-based incremental rebuild of wiki from all sources |
| `kb query "..."` | BM25 + vector search → LLM synthesizes answer with citations |
| `kb lint` | Health check: orphans, dead links, staleness, cycles |
| `kb evolve` | Gap analysis: suggests new sources and missing coverage |
