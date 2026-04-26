# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. **Detailed reference material lives in [`docs/reference/`](docs/reference/README.md)** — this file is the slim index. See the [Detailed Documentation](#detailed-documentation) table below for the full map.

## Quick Reference

- **State:** v0.11.0 · 2941 tests / 254 files (2930 passed + 10 skipped + 1 xfailed). Shipped → `CHANGELOG.md` (index) + `CHANGELOG-history.md` (per-cycle detail). Open → `BACKLOG.md`.
- **Always `.venv`** — activate before `pytest`, `kb`, `pip`. Never global Python.
- **Test fixtures** — use `tmp_wiki` / `tmp_project` / `tmp_kb_env`; never write real `wiki/` or `raw/`. `tmp_kb_env` already redirects `HASH_MANIFEST` — don't also monkeypatch it.
- **Patch the owner module** for the four MCP-migrated callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`) — not `kb.mcp.core.*`.
- **Path safety** — `_validate_page_id` at MCP boundary; library calls use `_validate_path_under_project_root(path, field_name)` (dual-anchor: literal + resolved both under `PROJECT_ROOT`).
- **Evidence Trail** — reverse-chronological, sentinel-guarded; sentinel is machine-maintained.
- **Release artifacts** — `SECURITY.md` (narrow-role CVE acceptance + disclosure path) + `.github/workflows/ci.yml` (ruff + pytest + pip-audit + build gate; cycle 34).
- **Doc update checklist** on push — see §Automation at bottom.

## Detailed Documentation

Detail moved out of this file lives in [`docs/reference/`](docs/reference/README.md). When you add cycle-level history, a new convention, or a new API, edit the relevant file there (it is the source of truth for its topic) and update this index only when a topic / file / heading itself changes. Per-topic depth lives in `docs/reference/`; CLAUDE.md stays slim.

| Topic | File |
|---|---|
| Architecture — 3-layer content, 5-ops cycle, Python package APIs, wiki index files | [docs/reference/architecture.md](docs/reference/architecture.md) |
| Module map — per-module breakdown of `src/kb/` | [docs/reference/module-map.md](docs/reference/module-map.md) |
| Implementation status — latest-cycle notes (32 / 33 / 34) | [docs/reference/implementation-status.md](docs/reference/implementation-status.md) |
| Testing — pytest layout + fixture rules | [docs/reference/testing.md](docs/reference/testing.md) |
| Error handling conventions | [docs/reference/error-handling.md](docs/reference/error-handling.md) |
| Phase 2 workflows — Standard / Thorough Ingest, Deep Lint, Query | [docs/reference/workflows.md](docs/reference/workflows.md) |
| Conventions — base rules, Evidence Trail, Architecture Diagram Sync | [docs/reference/conventions.md](docs/reference/conventions.md) |
| MCP servers — kb tool catalogue + memory / arxiv / sqlite | [docs/reference/mcp-servers.md](docs/reference/mcp-servers.md) |
| Ingestion commands — web / PDF / video → markdown | [docs/reference/ingestion-commands.md](docs/reference/ingestion-commands.md) |
| Opus 4.7 behaviour notes + extraction templates | [docs/reference/opus-47-notes.md](docs/reference/opus-47-notes.md) |

## Working Principles

*(Adapted from [Karpathy's LLM coding observations](https://x.com/karpathy/status/2015883857489522876). Bias toward caution over speed on non-trivial work. For a one-line typo fix, use judgment.)*

**Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**Goal-Driven Execution.** Transform imperative tasks into verifiable goals:
- "Fix the bug" → *"Write a failing test that reproduces it, then make it pass."*
- "Add validation" → *"Write tests for invalid inputs, then make them pass."*
- "Refactor X" → *"Ensure tests pass before and after."*
- For multi-step work, state the plan as `[step] → verify: [check]` — then loop.

**Two tests before declaring done:**
1. *Every changed line should trace directly to the request.* Drop drive-by edits.
2. *Would a senior engineer say this is overcomplicated?* If yes, simplify.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup
cp .env.example .env          # then fill in:
# ANTHROPIC_API_KEY (optional for Claude Code/MCP mode; required for direct API-backed flows), FIRECRAWL_API_KEY (optional), OPENAI_API_KEY (optional)
# Optional: override project root detection
export KB_PROJECT_ROOT=/path/to/your/kb    # heuristic + walk-up fallback if unset

# Install deps + editable package (enables `kb` CLI command)
# NOTE: `pip install -e .` must be run before `kb` CLI or `from kb import ...` works outside pytest
pip install -r requirements.txt && pip install -e .

# Run all tests
python -m pytest

# Run single test
python -m pytest tests/test_models.py::test_extract_wikilinks -v

# Lint, auto-fix, & format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/

# CLI (after pip install -e .)
kb --version
kb ingest raw/articles/example.md --type article
kb compile [--full]
kb query "What is compile-not-retrieve?"
kb lint [--fix]
kb evolve
kb publish [--out-dir PATH] [--format llms|llms-full|graph|all] [--incremental/--no-incremental]   # /llms.txt + /llms-full.txt + /graph.jsonld
kb rebuild-indexes [--wiki-dir PATH] [--yes]   # wipe manifest + vector DB + LRU caches
kb mcp                        # Start MCP server for Claude Code

# Playwright browser (needed by crawl4ai)
python -m playwright install chromium
```

Ruff config: line length 100, Python 3.12+, rules E/F/I/W/UP (see `pyproject.toml`).

## Model Tiering

| Tier | Model ID | Env Override | Use |
|---|---|---|---|
| `scan` | `claude-haiku-4-5-20251001` | `CLAUDE_SCAN_MODEL` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-4-6` | `CLAUDE_WRITE_MODEL` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-7` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

For Opus 4.7 behaviour notes (CoT scaffolding, instruction following, parallel tool calls, 1M context) and the 10 extraction templates, see [docs/reference/opus-47-notes.md](docs/reference/opus-47-notes.md).

## Wiki Page Frontmatter Template

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-05
updated: 2026-04-05
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
# Cycle 14 AC1/AC2/AC23 — optional epistemic-integrity fields; absent is valid.
# belief_state: confirmed | uncertain | contradicted | stale | retracted
# authored_by: human | llm | hybrid
# status: seed | developing | mature | evergreen
---
```

**Optional epistemic fields (cycles 14-15):** `belief_state` is the cross-source aggregate (orthogonal to per-source `confidence`); `authored_by` formalises human vs LLM authorship; `status` tracks the page lifecycle. Query engine applies a +5% `STATUS_RANKING_BOOST` to pages with `status in (mature, evergreen)` and a mild `AUTHORED_BY_BOOST` to `authored_by: human|hybrid` when full metadata passes `validate_frontmatter`. Publish outputs (`kb publish`) skip pages with `belief_state in {retracted, contradicted}` OR `confidence == speculative`.

## Implementation History & Roadmap

- **Shipped:** see `CHANGELOG.md` (brief compact index, newest first — compact Items / Tests / Scope / Detail per cycle) and `CHANGELOG-history.md` (full per-cycle bullet-level archive). Format: [Keep a Changelog](https://keepachangelog.com/).
- **Open work:** see `BACKLOG.md` — severity levels CRITICAL → LOW, grouped by file. Resolved items are deleted (brief entry in `CHANGELOG.md`, detail in `CHANGELOG-history.md`); resolved phases collapse to a one-liner under "Resolved Phases".
- **Roadmap (Phase 5 deferred + Phase 6 cut):** see `BACKLOG.md` §"Phase 5 — Community followup proposals" and §"Phase 6 candidates". Includes the 2026-04-13 Karpathy-gist re-evaluation ("RECOMMENDED NEXT SPRINT") and all deferred features (inline claim tags, URL-aware ingest, semantic chunking, typed graph relations, autonomous research loop, etc.).
- **Latest-cycle notes (32 / 33 / 34):** see [docs/reference/implementation-status.md](docs/reference/implementation-status.md).

## Automation

No auto-commit hooks. Doc updates and commits are done manually when ready to push.

### BACKLOG.md lifecycle
Resolved items are **deleted** from `BACKLOG.md` (brief entry added to `CHANGELOG.md [Unreleased]` Quick Reference; full detail added to `CHANGELOG-history.md`). When all items in a phase section are resolved, the section collapses to a one-liner under "Resolved Phases" (e.g., `- **Phase 3.92** — all items resolved in v0.9.11`). This keeps the backlog focused on open work only.

### Doc update checklist (before push)
When asked to update docs, review `git diff` and update as needed:
- `CHANGELOG.md` — add compact Items / Tests / Scope / Detail entry under `[Unreleased]` Quick Reference (newest first)
- `CHANGELOG-history.md` — add full per-cycle bullet-level detail (newest first)
- `BACKLOG.md` — **delete** resolved items (never strikethrough); collapse empty phase sections
- `CLAUDE.md` — update Quick Reference numbers (version, tests, tools), Model Tiering table, frontmatter template, Detailed Documentation index. Detail edits go in the matching [docs/reference/](docs/reference/README.md) file.
- `docs/reference/*.md` — source of truth for each topic. Update the relevant file when content within a section changes (architecture, error handling, mcp-servers, etc.).
- `README.md` — update if user-facing features or setup changed
- `docs/architecture/architecture-diagram.html` + re-render PNG if architecture changed

All tools are auto-approved for this project (permissions in `settings.local.json`).
