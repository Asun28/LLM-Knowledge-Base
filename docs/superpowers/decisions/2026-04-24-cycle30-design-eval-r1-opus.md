# Cycle 30 — R1 Opus Design Evaluation

**Date:** 2026-04-24
**Role:** R1 Opus design review (architecture, symbol verification, AC scoring)
**Baseline:** 2826 tests / 247 files

## Symbol Verification Table

| Symbol | File:Line | Status |
|---|---|---|
| `kb.utils.text.truncate` | `src/kb/utils/text.py:9` | EXISTS — head+tail, default `limit=600`, marker `"...N chars elided..."` |
| `kb.compile.compiler._audit_token` | `src/kb/compile/compiler.py:590-603` | EXISTS — 3-branch body: `cleared` / `cleared (warn: {err})` / `{err}` / `"unknown"` |
| `kb.compile.compiler.rebuild_indexes` | `src/kb/compile/compiler.py:633-805` | EXISTS |
| `kb.mcp.health.kb_graph_viz` | `src/kb/mcp/health.py:171` (decl `@mcp.tool()` 171 / def 172) | EXISTS — sig `(max_nodes: int = 30, wiki_dir: str \| None = None)`, clamps `max(1, min(n, 500))` AFTER rejecting `0` |
| `kb.mcp.health.kb_verdict_trends` | `src/kb/mcp/health.py:211-232` | EXISTS — sig `(wiki_dir: str \| None = None)` |
| `kb.mcp.health.kb_detect_drift` | `src/kb/mcp/health.py:235-297` | EXISTS — sig `(wiki_dir: str \| None = None)` |
| `kb.mcp.quality.kb_reliability_map` | `src/kb/mcp/quality.py:229-261` | EXISTS — `()` zero args |
| `kb.mcp.quality.kb_lint_consistency` | `src/kb/mcp/quality.py:155-184` | EXISTS — sig `(page_ids: str = "")`; NO `wiki_dir` |
| `kb.mcp.quality.kb_lint_deep` | `src/kb/mcp/quality.py:129-152` | EXISTS — sig `(page_id: str)` single arg; body-bearing (validates + loads + returns fidelity context) |
| `kb.mcp.app._validate_wiki_dir` | `src/kb/mcp/app.py:141` | EXISTS |
| `kb.mcp.health._validate_health_wiki_dir` | `src/kb/mcp/health.py:17-18` | EXISTS — forwards to `_validate_wiki_dir(wiki_dir, project_root=PROJECT_ROOT)` |
| `kb.cli._error_exit` | `src/kb/cli.py:60-70` | EXISTS — applies `_truncate` + optional traceback |

**`_audit_token` current body (verified verbatim):**

```python
if block["cleared"]:
    if block["error"]:
        return f"cleared (warn: {block['error']})"
    return "cleared"
return str(block["error"]) if block["error"] else "unknown"
```

Both non-None error branches splice `block["error"]` verbatim — Q5 **confirmed**: cap must apply to both the warn-suffix branch AND the fallback `{error}` branch. `"unknown"` literal needs no cap.

## Analysis

Cycle 30 is a textbook cookie-cutter replay of cycle-27 plus a surgical one-point fix to the compound audit token shipped in cycle-29. The pattern fit is clean: AC2-AC6 mirror the exact shape of `kb stats` / `kb list-pages` / `kb list-sources` at `src/kb/cli.py:622-695` — function-local imports, `output.startswith("Error:") → sys.exit(1)` contract, `except Exception as exc: _error_exit(exc)` outer wrap. AC1 is a 3-branch edit of a 14-line function with a function-local `from kb.utils.text import truncate` — well inside the cycle-23 AC4 boot-lean envelope. The scope is honest: no write-path tools, no body-bearing tools (`kb_read_page`, `kb_affected_pages`, `kb_lint_deep`), no signature changes. AC7 is pure BACKLOG hygiene.

The threat surface is minimal and already enumerated: T1 (UTF-8) is moot because `truncate` slices `str`, not `bytes`; T2 (`--wiki-dir` raw-string shortcut) is correctly sidestepped by forwarding the click-validated path to the MCP tool untouched — the MCP tool re-enters `_validate_health_wiki_dir` which is the cycle-23 dual-anchor. The cycle-27 `list-pages`/`list-sources` pattern already demonstrates that when the MCP tool doesn't accept `--wiki-dir`, the CLI must not expose it (matches AC6 — `kb_lint_consistency` has NO `wiki_dir` parameter, verified at `quality.py:156`). Load-bearing audit assertions at `tests/test_cycle29_rebuild_indexes_hardening.py:102, 184, 212` all anchor at the head (`"vector=cleared (warn: tmp:"`) — these survive head+tail truncation because `half = max(40, (500-40)//2) = 230` preserves the 27-char prefix trivially. The AC1 regression test spec (head + marker + tail) matches the existing `truncate` contract and the cycle-3 M17 docstring verbatim.

One design subtlety worth flagging: Q2 recommends **function-local** import for `truncate` in `_audit_token` — I'd argue the cycle-23 AC4 boot-lean contract only binds MCP boot paths, and `kb.compile.compiler` already module-imports many heavy helpers at top level. However, keeping the import function-local costs nothing and preserves the pattern uniformly. Accept the cautious default.

## Per-AC Scorecard

### AC1 — Audit error-string length cap
- **Pattern fit:** HIGH — reuses existing `kb.utils.text.truncate` with the same `limit=...` kwarg already used by `_truncate` in `cli.py:41`.
- **Testability:** HIGH — unit test on `_audit_token({'cleared': True, 'error': 'X'*2000})`, end-to-end via `rebuild_indexes` with monkeypatched `Path.unlink`. Both paths bypass `--help` per cycle-27 L2.
- **Coverage gaps:** None. Both `cleared (warn: ...)` AND fallback `{error}` branches must wrap — AC1 text explicitly states "both branches pass through the cap" — correct.
- **Verdict:** **APPROVE.**

### AC2 — `kb graph-viz`
- **Pattern fit:** HIGH — cycle-27 shape.
- **Testability:** HIGH — spy-based body test per cycle-27 L2.
- **Coverage gaps:** None material. See probe-2: `max_nodes=-1` → Click accepts, MCP clamps to 1. Document in AC text (user-facing surprise); acceptable because the MCP tool is the single source of truth and treating CLI as a passthrough is exactly the cycle-27 contract. Consider CLI-level `click.IntRange(1, 500)` for cleaner UX, but this would DIVERGE from `kb_graph_viz`'s own error-string behavior for `0`. **Recommend:** keep pure passthrough; NEG values silently clamp to 1 at MCP layer, `0` returns explicit error string — document in the help text (e.g., `"1–500; 0 rejected"`).
- **Verdict:** **APPROVE-WITH-AMEND** "help text notes 1-500 range + '0 rejected' explicitly so operators see the contract without running it."

### AC3 — `kb verdict-trends`
- **Pattern fit:** HIGH.
- **Testability:** HIGH.
- **Coverage gaps:** None.
- **Verdict:** **APPROVE.**

### AC4 — `kb detect-drift`
- **Pattern fit:** HIGH.
- **Testability:** HIGH.
- **Coverage gaps:** None.
- **Verdict:** **APPROVE.**

### AC5 — `kb reliability-map`
- **Pattern fit:** HIGH.
- **Testability:** HIGH.
- **Coverage gaps:** None. Probe-6 confirmed: `kb_reliability_map()` takes no args. AC5 correctly omits `--wiki-dir`. Note: the "No feedback recorded yet" message does NOT start with `"Error:"` — AC5 text explicitly calls this out. Good edge-catch.
- **Verdict:** **APPROVE.**

### AC6 — `kb lint-consistency`
- **Pattern fit:** HIGH.
- **Testability:** HIGH.
- **Coverage gaps:** Probe-3 confirmed arg name is `page_ids` (plural, string). Probe-4 confirmed NO `wiki_dir` — AC6 correctly omits. MCP tool validates + splits + caps at 50 IDs + calls `_validate_page_id(pid, check_exists=True)` per ID. CLI is a pure passthrough per T3.
- **Verdict:** **APPROVE.**

### AC7 — BACKLOG hygiene
- **Pattern fit:** HIGH — matches cycle-27 AC7 / cycle-28 AC9 / cycle-29 AC9.
- **Verdict:** **APPROVE.**

## Open-question recommendations

| Q | Recommendation | Reasoning |
|---|---|---|
| Q1 | **limit=500** per AC1 text | Matches BACKLOG suggestion; 2×540 + ~70 static = ~1150 chars per log line still small |
| Q2 | **Function-local** import in `_audit_token` | Uniform with cycle-27 pattern; trivially cheap |
| Q3 | **Two tests** (unit + e2e) | Separates contract from integration; matches cycle-25 AC1 test style |
| Q4 | Already resolved (T3) — CLI passes raw `page_ids` through | Confirmed via `quality.py:173` split-then-validate |
| Q5 | **Apply cap to BOTH branches** | Confirmed by reading `_audit_token` body — fallback branch also splices `block["error"]` verbatim |
| Q6 | **5-6 commits** as proposed | Matches cycle-26 L1 convention |
| Q7 | **Group by file** — AC1+test, AC2-AC3 together, AC4-AC5 together, AC6, AC7+docs | Per user feedback_batch_by_file memory |
| Q8 | **One file, one class per subcommand** | Matches cycle-27 precedent at `tests/test_cycle27_cli_parity.py` |

## Hidden AC probe (Q: `kb_lint_deep`?)

Read `kb.mcp.quality.kb_lint_deep` at `quality.py:129-152` — sig is `(page_id: str)`, body validates via `_validate_page_id`, strips control chars via `_strip_control_chars`, returns `build_fidelity_context(page_id)`. **It IS a thin wrapper** — but page_id validation couples it to the `kb_read_page` / `kb_affected_pages` page_id-input cycle explicitly deferred in the Non-goals. **Correctly OUT of scope** for cycle 30; defer with the page_id-centric cycle as planned.

## Open questions for Step 5

1. **AC2 help-text range note:** confirm the AC amendment above (document `0` rejection + 1-500 range in `--max-nodes` help text) before Step 9.
2. **Test file naming:** `test_cycle30_cli_parity.py` vs splitting out `test_cycle30_audit_token_cap.py` — requirements doc already specifies split; confirm.

## FINAL VERDICT: APPROVE-WITH-AMENDS

**Amend:** AC2 `--max-nodes` help text explicitly documents "1–500; 0 rejected" so the Click-passthrough contract is self-documenting. All other ACs approved as-written. Symbol verification clean, scope honest, pattern-fit excellent.
