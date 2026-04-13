---
title: "Synthesis: The Knowledge-Compounding Flywheel"
source:
  - "raw/articles/karpathy-x-post.md"
  - "raw/papers/karpathy-llm-wiki-gist.md"
created: 2026-04-13
updated: 2026-04-13
type: synthesis
confidence: inferred
---

# Synthesis: The Knowledge-Compounding Flywheel

Combining the X post and the gist, Karpathy's pattern is less a storage format and more a **flywheel**: each rotation of ingest → query → lint increases the wiki's value without proportional human effort.

## Core Insight

Two signals from Karpathy converge on the same mechanism:

- From [[summaries/karpathy-llm-wiki-gist]]: *"The wiki is a persistent, compounding artifact."* The wiki is designed to accumulate, not reset.
- From [[summaries/karpathy-x-post]]: *"Good query answers get filed back as new wiki pages."* Every use contributes new content.

Together they describe a self-reinforcing loop: usage produces questions, questions produce answers, answers become pages, pages improve future answers.

## Evidence

- Source A (`raw/articles/karpathy-x-post.md`) says the LLM does the maintenance: lint, cross-reference updates, impute-missing-data via web search.
- Source B (`raw/papers/karpathy-llm-wiki-gist.md`) says each ingest updates 10–15 pages automatically — per-source work propagates.
- Together they suggest that human curation scales sublinearly: adding the 101st source costs roughly the same human attention as the first, but earns 10–15 page updates "for free" from the LLM.

## Why This Matters

- The flywheel only works if the LLM's maintenance is trustworthy. A silent hallucinated cross-link poisons every subsequent query — see [[concepts/compile-not-retrieve]] for why the pre-compiled layer is load-bearing and [[comparisons/compile-vs-rag]] for the scale ceiling.
- This project (`llm-wiki-flywheel`) takes the Karpathy pattern and adds quality gates to keep the flywheel from drifting — feedback-weighted trust scores, lint health checks, and an Evolve pass for forward gap analysis.

## Open Questions

- Does the flywheel survive past 1,000 pages, or does `index.md` become too long to read in a single LLM pass?
- What is the right trigger for promoting a query answer to a wiki page — rating, re-query frequency, or human approval?
- Does entity [[entities/andrej-karpathy]]'s `AGENTS.md` schema generalize to multi-agent setups, or does each agent want its own?
