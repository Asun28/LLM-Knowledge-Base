# `docs/reference/` — CLAUDE.md detail

> **Part of [CLAUDE.md](../../CLAUDE.md)** — this folder holds detail extracted out of CLAUDE.md so the top-level file stays a slim index. CLAUDE.md links here; every file here links back.

## Files

| Topic | File |
|---|---|
| Architecture — 3-layer content, 5-ops cycle, Python package APIs, wiki index files | [architecture.md](architecture.md) |
| Module map — per-module breakdown of `src/kb/` | [module-map.md](module-map.md) |
| Implementation status — latest-cycle notes (32 / 33 / 34) | [implementation-status.md](implementation-status.md) |
| Testing — pytest layout, fixtures, fixture rules | [testing.md](testing.md) |
| Error handling conventions | [error-handling.md](error-handling.md) |
| Phase 2 workflows — Standard / Thorough Ingest, Deep Lint, Query | [workflows.md](workflows.md) |
| Conventions — base rules, Evidence Trail, Architecture Diagram Sync | [conventions.md](conventions.md) |
| MCP servers — kb tool catalogue + memory / arxiv / sqlite | [mcp-servers.md](mcp-servers.md) |
| Ingestion commands — web / PDF / video → markdown | [ingestion-commands.md](ingestion-commands.md) |
| Opus 4.7 behaviour notes + extraction templates | [opus-47-notes.md](opus-47-notes.md) |

## Update rule

When you add cycle-level history, a new convention, or a new API:

1. Edit the relevant file in this folder — it is the source of truth for its topic.
2. Update the matching row in CLAUDE.md (Detailed Documentation section) **only** if the topic itself changes (new file, renamed file, new section heading worth surfacing).

CLAUDE.md should stay slim; per-topic depth lives here.
