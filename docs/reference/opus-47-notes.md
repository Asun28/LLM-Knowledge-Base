# Opus 4.7 Behaviour Notes & Extraction Templates

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the Opus 4.7 behaviour notes and extraction templates referenced from the "Model Tiering" section.

## Opus 4.7 Behaviour Notes

Applies to orchestrate-tier calls. Added 2026-04-17.

- **Explicit CoT for reasoning-heavy calls.** `call_llm` (in `kb.utils.llm`) does not pass a `thinking={...}` parameter, so extended thinking is never auto-activated at the orchestrate tier — this is true on 4.6 and 4.7 alike. For query synthesis, contradiction detection, `kb_lint_deep`, and semantic reviewers, include "Think step by step before answering" or a structured `## Analysis` scaffold in the prompt.
- **Instruction following is literal.** Prefer positive phrasing ("write prose", "emit JSON") over negative ("don't use lists"). 4.x honours each stated constraint individually; long "don't X, don't Y, don't Z" forbid-lists tend to produce tangential hedging — express constraints as positive actions instead.
- **Minimal formatting remains the default (unchanged from 4.6).** 4.7 avoids bullet-heavy prose, excessive bold/headers, and report-style structure in conversational output. Reserve structure for reference material and lists of ≥4 parallel items.
- **Parallel tool calls preferred** for independent reads — batch `kb_search` + `kb_list_pages` + multi-page `kb_read_page` in one assistant turn rather than serialising.
- **Structured output via `call_llm_json()` (forced tool_use).** Keep using the existing helper in `kb.utils.llm`; it is cache-friendly and removes fence-stripping failure modes. Do not switch to assistant-prefill for JSON.
- **1M-context variant** is available from this runtime (exposed as `claude-opus-4-7[1m]`). For deep multi-source synthesis prefer calling out the capacity in the prompt ("you have ~1M tokens; use the full source text") and handing the subagent raw files directly — routing to the long-context variant is the runtime's job, not the caller's. (Note: `query_wiki`'s 80K-char cap is a library-level constant in `kb.query.engine` that applies to wiki-context assembly, not to direct-prompt pass-through — treat the two as separate concerns.)

## Extraction Templates (`templates/`)

10 YAML schemas (article, paper, video, repo, podcast, book, dataset, conversation, comparison, synthesis). Each defines `extract:` fields and `wiki_outputs:` mapping (documentation-only, not enforced in code). All follow the same output pattern: summaries → entities → concepts. Used by the ingest pipeline to drive consistent extraction via the `extract:` fields.
