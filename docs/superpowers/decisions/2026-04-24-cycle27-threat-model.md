# Cycle 27 — Threat Model (inline mini)

**1 open alerts baseline: 0 sev=high, 0 sev=medium, 1 sev=low** (unchanged from cycle 26: `ragas` GHSA-95ww-475f-pr4f, no upstream fix).

## Skip rationale

Per feature-dev skill: "Step 2 threat model — skip when pure internal refactor, no I/O or trust boundary changes."

Cycle 27 adds 4 Click subcommands (`kb search`, `kb stats`, `kb list-pages`, `kb list-sources`) that are thin wrappers around EXISTING MCP tool functions (`kb.mcp.browse.kb_search`, `kb.mcp.browse.kb_stats`, `kb.mcp.browse.kb_list_pages`, `kb.mcp.browse.kb_list_sources`). Each underlying MCP tool:

- Has existing trust-boundary validation (bounded query length, `_validate_page_id`, path containment, etc.) that the CLI reuses automatically.
- Already runs under operator credentials (single-user local).
- Produces pre-formatted string output (no new data classification).
- Is read-only (no filesystem writes, no manifest mutation, no network calls).

No new code paths, no new state, no new user input surface. The CLI adds a call site; it does NOT add a boundary.

## Residual threats (bounded)

| # | Threat | Mitigation | Blocking? |
|---|--------|-----------|-----------|
| T1 | Click argument injection via shell metacharacters | Click quotes/escapes args by default; `argparse`-equivalent semantics | No — stdlib-guaranteed |
| T2 | Function-local import regression breaks boot-lean contract | Same CONDITION as cycle-26 (function-local imports preserve `kb --version` short-circuit) | Verify via grep at Step 11 |
| T3 | CLI bypasses MCP-tool input-length gates | AC1 explicitly enforces the same `MAX_QUESTION_LEN` check; AC3/AC4 rely on existing MCP-tool caps | In-scope for AC1 |

## PR-CVE diff plan (Step 11)

Same as cycle 26: compare `pip-audit` output against `.data/cycle-27/cve-baseline.json`. Expected empty (cycle 27 adds zero new dependencies).

## Verdict

**APPROVE — proceed to Step 3 without Opus-subagent threat model dispatch.** Three lightweight residual threats (T1-T3) captured; T2 + T3 become Step-11 grep verifications.
