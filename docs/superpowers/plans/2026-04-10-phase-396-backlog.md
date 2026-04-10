# Phase 3.96 Backlog Fixes — Implementation Plan (Index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 153 Phase 3.96 backlog items (4 CRITICAL, 31 HIGH, 54 MEDIUM, 64 LOW) from the v0.9.14 code review — bump to v0.9.15.

**Architecture:** Fixes are grouped by module area so subagents can work in parallel without file conflicts. Task 1 (foundation utils) runs first; Tasks 2–12 run in parallel after Task 1 completes. Task 13 runs last (version bump, docs, verification).

**Tech Stack:** Python 3.12+, pytest, ruff, NetworkX, frontmatter, FastMCP

## Task Index

| Task | File | Module | CRIT | HIGH | MED | LOW | Total |
|------|------|--------|------|------|-----|-----|-------|
| 1 | [task-01.md](2026-04-10-phase-396-task-01.md) | Utils, Config, Models | 0 | 3 | 8 | 12 | 23 |
| 2 | [task-02.md](2026-04-10-phase-396-task-02.md) | Ingest Pipeline | 2 | 5 | 8 | 7 | 22 |
| 3 | [task-03.md](2026-04-10-phase-396-task-03.md) | Compile & Linker | 0 | 5 | 7 | 5 | 17 |
| 4 | [task-04.md](2026-04-10-phase-396-task-04.md) | Query, BM25, Citations | 0 | 1 | 2 | 8 | 11 |
| 5 | [task-05.md](2026-04-10-phase-396-task-05.md) | Graph | 0 | 0 | 5 | 3 | 8 |
| 6 | [task-06.md](2026-04-10-phase-396-task-06.md) | Lint | 0 | 3 | 10 | 4 | 17 |
| 7 | [task-07.md](2026-04-10-phase-396-task-07.md) | Review | 1 | 2 | 3 | 1 | 7 |
| 8 | [task-08.md](2026-04-10-phase-396-task-08.md) | Feedback & Evolve | 0 | 3 | 2 | 4 | 9 |
| 9 | [task-09.md](2026-04-10-phase-396-task-09.md) | MCP | 1 | 5 | 9 | 9 | 24 |
| 10 | [task-10.md](2026-04-10-phase-396-task-10.md) | CLI | 0 | 0 | 1 | 2 | 3 |
| 11 | [task-11.md](2026-04-10-phase-396-task-11.md) | Test Coverage Gaps | 0 | 0 | 1 | 18 | 19 |
| 12 | [task-12.md](2026-04-10-phase-396-task-12.md) | Documentation | 0 | 0 | 1 | 0 | 1 |
| 13 | [task-13.md](2026-04-10-phase-396-task-13.md) | Version Bump & Verify | — | — | — | — | — |

## Parallel Execution Strategy

```
Task 1 (foundation)
  ├── Task 2 (ingest)        ─┐
  ├── Task 3 (compile/linker) │
  ├── Task 4 (query/bm25)     │
  ├── Task 5 (graph)           │ All run in parallel
  ├── Task 6 (lint)            │
  ├── Task 7 (review)          │
  ├── Task 8 (feedback/evolve) │
  ├── Task 9 (mcp)             │
  ├── Task 10 (cli)            │
  ├── Task 11 (test gaps)     ─┘ (can start after 2–10)
  └── Task 12 (docs)
Task 13 (version bump) — after all above
```

## File Conflict Zones

Tasks are designed to avoid file conflicts, but note:
- **`config.py`** is modified by Tasks 1, 4, and 8 (add constants). Run these sequentially for config changes, or merge at Task 13.
- **Test files**: Each task writes tests to its own file `tests/test_v0915_task{NN}.py` to avoid conflicts. Task 11 consolidates any remaining coverage gaps.

## Test File Strategy

Each task creates its own test file following the pattern `tests/test_v0915_task{NN}.py`. This prevents merge conflicts when tasks run in parallel. All test files follow the project convention with versioned names.

## Ruff Compliance

All code must pass `ruff check` with the project config (line length 100, Python 3.12+, rules E/F/I/W/UP). Run after each task commit.
