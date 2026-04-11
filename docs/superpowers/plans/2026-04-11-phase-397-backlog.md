# Phase 3.97 Implementation Plan — v0.9.16

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 60+ issues identified by the 6-domain parallel code review of v0.9.15

**Architecture:** Surgical fixes organized by module area for parallel execution. Task 01 (CRITICAL) and Task 02 (Foundation) run first (can be parallel — no file overlap), then Tasks 03-08 run in parallel, then Task 09 (CLI + docs + version bump) finalizes.

**Tech Stack:** Python 3.12+, pytest, ruff

---

## Item Count

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 6 (1 already fixed) | Non-atomic writes, MCP exception gaps |
| HIGH | 15 | Data integrity, error handling, silent wrong results |
| MEDIUM | 18 | Quality gaps, dead code, missing coverage |
| LOW | 23 | Style, naming, minor inconsistencies |
| **Total** | **62** | |

## Task Overview

| Task | Module Area | Items | Files | Depends On |
|------|-------------|-------|-------|------------|
| [01](2026-04-11-phase-397-task-01.md) | CRITICAL fixes | 6 | lint/checks.py, mcp/quality.py, compile/linker.py, mcp/core.py | — |
| [02](2026-04-11-phase-397-task-02.md) | Foundation: Config + Utils + Models | 16 | config.py, utils/*.py, models/*.py | — |
| [03](2026-04-11-phase-397-task-03.md) | Ingest Pipeline | 14 | ingest/pipeline.py, ingest/extractors.py | 01, 02 |
| [04](2026-04-11-phase-397-task-04.md) | Compile / Linker | 4 | compile/linker.py, compile/compiler.py | 01, 02 |
| [05](2026-04-11-phase-397-task-05.md) | Query / Graph / Citations | 11 | query/*.py, graph/*.py | 02 |
| [06](2026-04-11-phase-397-task-06.md) | Lint / Review / Evolve | 15 | lint/*.py, review/refiner.py, evolve/analyzer.py | 01, 02 |
| [07](2026-04-11-phase-397-task-07.md) | MCP Server | 14 | mcp/core.py, mcp/quality.py, mcp/browse.py, mcp/app.py | 01, 02 |
| [08](2026-04-11-phase-397-task-08.md) | Feedback Store | 4 | feedback/store.py, feedback/reliability.py | 02 |
| [09](2026-04-11-phase-397-task-09.md) | CLI + Docs + Version Bump | 5 | cli.py, CLAUDE.md, CHANGELOG.md, BACKLOG.md | 01-08 |

## Execution Order

```
Phase 1 (parallel):  Task 01 + Task 02
Phase 2 (parallel):  Task 03, 04, 05, 06, 07, 08
Phase 3 (sequential): Task 09
```

## File Conflict Map

Tasks 03-08 are designed to avoid file conflicts:
- Task 03: `ingest/pipeline.py`, `ingest/extractors.py`
- Task 04: `compile/linker.py`, `compile/compiler.py`
- Task 05: `query/engine.py`, `query/citations.py`, `query/bm25.py`, `graph/builder.py`, `graph/export.py`
- Task 06: `lint/checks.py`, `lint/semantic.py`, `lint/trends.py`, `review/refiner.py`, `evolve/analyzer.py`
- Task 07: `mcp/core.py`, `mcp/quality.py`, `mcp/browse.py`, `mcp/app.py`
- Task 08: `feedback/store.py`, `feedback/reliability.py`

**Shared file:** `config.py` is modified only in Task 02. All parallel tasks import from it but do not write to it.

## Testing Strategy

Each task creates its own test file: `tests/test_v0916_task{NN}.py` to avoid merge conflicts. TDD: write failing test, verify failure, implement fix, verify pass. Every task runs the full suite before committing.
