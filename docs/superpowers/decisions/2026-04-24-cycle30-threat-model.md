# Cycle 30 — Threat model

## Analysis

Cycle 30 is a pre-Phase-5 hygiene cycle: one audit-log cap (AC1 in `compile/compiler.py::_audit_token`) and five thin CLI wrappers (AC2-AC6) mirroring existing MCP tools. The surface is narrow; the AC1 threat centres on log-injection durability + Unicode boundary safety through `kb.utils.text.truncate`, while AC2-AC6 replay the cycle-27 pattern where the real risk is decorator theft / docstring-orphan regressions and `--wiki-dir` validator bypass.

Evidence: `_audit_token` at `src/kb/compile/compiler.py:590-603` currently inlines `block["error"]` verbatim into the returned f-string. `truncate(msg, limit=600)` at `src/kb/utils/text.py:9-35` operates on `str` via `len()` + slice (Python str slicing is codepoint-safe, so T1 is a non-issue — NOT byte-indexed). Grep of existing audit-grep assertions (`tests/test_cycle29_rebuild_indexes_hardening.py:102,184,212`) shows the load-bearing substring is `"vector=cleared (warn: tmp:"` — always at the HEAD of the error, so the head+tail split preserves it. Grep of `_validate_wiki_dir` / `_validate_health_wiki_dir` confirms the two-tier pattern: MCP health tools use `_validate_health_wiki_dir` (which forwards to `_validate_wiki_dir` with `project_root=PROJECT_ROOT`); the five new CLI wrappers should NOT add their own `_validate_wiki_dir` call — they should pass `--wiki-dir` untouched so the MCP tool's validator runs exactly once (cycle-27 `stats`/`list-pages`/`list-sources` pattern at `src/kb/cli.py:630-695`). Only `search` (AC1 in cycle 27) does its own pre-validation because it bypasses MCP and calls `search_pages` directly — AC2-AC6 do not.

## Trust boundaries

- **Untrusted → trusted:** CLI argv (`--wiki-dir`, `--max-nodes`, `--page-ids`) and `rebuild_indexes`'s `OSError.__str__()` content (which reflects OS error-message template strings + user-supplied path fragments on Windows).
- **Trusted:** the MCP tool functions themselves (already validated), `kb.utils.text.truncate` (pure function), `append_wiki_log` (already sanitizes `| \n \r \t [[ ]]` + prefix-neutralizes markdown).

## Data classification

- **AC1:** reads `result[{manifest,vector}]["error"]` (OS-origin strings; may contain redacted Windows paths). Writes to `wiki/log.md` (user-private repo file) + stdout.
- **AC2-AC6:** read-only wrappers. Write to stdout only. Do not mutate `wiki/`, `raw/`, `.data/`, or `.memory/`.

## Authn/Authz

N/A — local CLI, single-user. `--wiki-dir` override semantics: rely on the MCP tool's `_validate_health_wiki_dir` dual-anchor `PROJECT_ROOT` containment (cycle-23). AC2-AC6 pass the raw string through Click's `click.Path(resolve_path=True)`, then forward to the MCP tool, which re-validates — no double validation, no bypass.

## Logging/audit requirements (AC1)

Before: `manifest={_audit_token(...)} vector={_audit_token(...)} caches_cleared={N}` — unbounded. After: each `_audit_token` output is bounded to ~540 chars (500-char budget + `"...N chars elided..."` marker; `half = max(40, (500-40)//2) = 230` per side). `append_wiki_log` sanitizer runs UNCHANGED after the cap. Existing grep assertions (`"vector=cleared (warn: tmp:"`, `"manifest=cleared"`) sit at the HEAD of the token, preserved by head+tail truncation.

## Threats

- **T1 — UTF-8 boundary smash (cycle-18 L4 class).** AC1. Python `str` slicing is codepoint-safe; `truncate` uses `msg[:half]` on a `str`, never bytes. **Mitigation:** none needed. **IN-SCOPE** verified by reading `src/kb/utils/text.py:27-35`.
- **T2 — `--wiki-dir` raw-string shortcut (cycle-23 I1 class).** AC2-AC6. **Mitigation:** wrappers MUST forward `--wiki-dir` to the MCP tool untouched (cycle-27 `stats` pattern lines 636-645); no pre-`Path()` coercion. **IN-SCOPE** — Step 11 greps for any `Path(wiki_dir)` in the 5 new commands.
- **T3 — `--page-ids` comma-list injection.** AC6. `kb_lint_consistency` at `src/kb/mcp/quality.py:173-180` already splits on `,`, strips whitespace, caps at 50 IDs, and runs `_validate_page_id(pid, check_exists=True)` per ID. **Mitigation:** CLI passes the raw string through. **IN-SCOPE.**
- **T4 — `max_nodes=0` / negative.** AC2. Click `type=int` accepts `0` and negatives. `kb_graph_viz` at `src/kb/mcp/health.py:191-197` explicitly rejects `0` with an error string and clamps negatives via `max(1, min(max_nodes, 500))`. **Mitigation:** unchanged; CLI surfaces the error verbatim. **IN-SCOPE.**
- **T5 — AC1 breaks audit-grep assertions.** `tests/test_cycle23_rebuild_indexes.py:273` (`"manifest=cleared"`) + `test_cycle29_rebuild_indexes_hardening.py:102,184,212` (`"vector=cleared (warn: tmp:"`) all anchor at the head — survive head+tail truncation. **Mitigation:** confirmed via grep. **IN-SCOPE.**
- **T6 — Decorator theft (cycle-27 L1).** AC2-AC6. **Mitigation:** each of 5 new blocks must pair `@cli.command(...)` + `@click.option(...)` + `def <fn>(...)` + closing `"""` before the next decorator. **IN-SCOPE** — Step 11 AST-parses `cli.py` to confirm 5 new `click.Command` objects.
- **T7 — Docstring orphan (cycle-23 L1).** **Mitigation:** function-local imports go AFTER the docstring closes (cycle-27 lines 592-595 pattern). **IN-SCOPE.**
- **T8 — Raw `{e}` leak in `except Exception`.** **Mitigation:** all 5 wrappers use `except Exception as exc: _error_exit(exc)` (cycle-27 lines 619/645/674/695). No `f"Error: {e}"` formatting. **IN-SCOPE.**

## Dep-CVE baseline

Baseline at `.data/cycle-30/cve-baseline.json` + `.data/cycle-30/alerts-baseline.json`. Expected Step-11 diff state: `diskcache` + `ragas` still have no upstream fix (cycle-28/29 precedent, AC7 skips no-op re-verify).

## Step-11 verification checklist

1. Full pytest passes (`2826 + ~12-14 = ~2838-2840` tests).
2. `ruff check src/ tests/` + `ruff format --check src/ tests/` clean.
3. AST scan of `src/kb/cli.py`: exactly 5 new `click.Command` objects named `graph-viz`, `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency`.
4. `grep -n "Path(wiki_dir)" src/kb/cli.py` in AC2-AC6 blocks → zero hits (no raw-string coercion).
5. `python -c "from kb.compile.compiler import _audit_token; assert len(_audit_token({'cleared': True, 'error': 'X' * 2000})) <= 600"` → passes.
6. `tests/test_cycle23_rebuild_indexes.py::test_audit_log` + `tests/test_cycle29_rebuild_indexes_hardening.py` still pass unchanged.
7. `BACKLOG.md` diff: only deletions + CLI-parity narrow; no unintended phase edits.
8. Dep-CVE diff vs `.data/cycle-30/cve-baseline.json` → zero new CVEs.

## Defer list

- **D1 — `append_wiki_log` length cap** (non-goal §5). Widens sanitizer scope; better handled in a dedicated JSONL-audit-migration cycle.
- **D2 — Write-path CLI wrappers** (`kb_refine_page`, `kb_save_source`). Deferred to a write-path input-validation-focused cycle.
- **D3 — `kb_read_page` + `kb_affected_pages` CLI wrappers.** Body-bearing / backlink-computing — deferred.

Cycle 30 threat surface is narrow and fully covered by existing cycle-23/27/29 patterns — eight threats enumerated, all IN-SCOPE, zero new mitigations required.
