# Demo — Folder Structure Reference

This folder mirrors the real project layout with placeholder files.
Use it to understand where things go before adding real content.

```
demo/
├── raw/                        ← Immutable source documents (LLM reads, never writes)
│   ├── articles/               ← Web articles, blog posts
│   │   └── example-article.md
│   ├── papers/                 ← Academic papers (PDF → markdown)
│   │   └── example-paper.md
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
    │   └── example-entity.md
    ├── concepts/               ← Ideas, techniques, patterns
    │   └── example-concept.md
    ├── comparisons/            ← Side-by-side analysis of two+ approaches
    │   └── example-comparison.md
    ├── summaries/              ← One summary per raw source
    │   └── example-summary.md
    └── synthesis/              ← Cross-source insights not in any single raw file
        └── example-synthesis.md
```

## Wiki Page Frontmatter

Every wiki page starts with:

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-12
updated: 2026-04-12
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
---
```

## Five Key Operations

| Operation | What it does |
|-----------|-------------|
| `kb ingest <file>` | LLM reads raw source → creates/updates wiki pages |
| `kb compile` | Hash-based incremental rebuild of wiki from all sources |
| `kb query "..."` | BM25 search → LLM synthesizes answer with citations |
| `kb lint` | Health check: orphans, dead links, staleness, cycles |
| `kb evolve` | Gap analysis: suggests new sources and missing coverage |
