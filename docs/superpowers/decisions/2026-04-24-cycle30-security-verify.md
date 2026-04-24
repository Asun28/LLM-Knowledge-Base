# Cycle 30 — Step 11 Security Verification + PR-CVE Diff

**Date:** 2026-04-25 (implementation landed 2026-04-24 late / 2026-04-25 early)
**Role:** Primary-session security verification against the Step-2 threat model (R2 Codex earlier stalled; consistent primary-session verify used to avoid second stall risk).
**Branch HEAD:** `824f78f docs(cycle 30): AC7 BACKLOG hygiene`
**Baseline:** cycle-30 Step-2 threat model T1-T8 at `docs/superpowers/decisions/2026-04-24-cycle30-threat-model.md`.

## (a) Threat-model implementation verification

| T# | Description | Verdict | Evidence |
|---|---|---|---|
| T1 | `_audit_token` UTF-8 boundary smash | **IMPLEMENTED** | `kb.utils.text.truncate` slices `str`, not bytes — Python str slicing is codepoint-safe by construction. Non-issue per threat model §T1. AC1 uses `truncate(str(block["error"]), limit=500)`; no byte indexing. |
| T2 | `--wiki-dir` raw-string shortcut (cycle-23 I1 class) | **IMPLEMENTED** | AC2-AC4 wrappers forward `--wiki-dir` raw to MCP tool (which re-enters `_validate_health_wiki_dir` dual-anchor). Grep `Path(wiki_dir)` in `src/kb/cli.py` shows ONE hit at line 551 — this is the pre-existing `rebuild_indexes_cmd` (cycle-23 code), NOT any cycle-30 AC2-AC5 block. `grep -A15 'def graph_viz\|def verdict_trends\|def detect_drift' src/kb/cli.py` confirms raw passthrough via `wiki_dir=wiki_dir` kwarg. |
| T3 | `--page-ids` comma-list injection | **IMPLEMENTED** | `kb_lint_consistency` body at `src/kb/mcp/quality.py:173-180` handles split + strip + 50-ID cap + `_validate_page_id` per ID. CLI passes `page_ids` string raw — `grep "page_ids.split" src/kb/cli.py` returns zero hits (C6 verified). Test `test_lint_consistency_body_executes_with_ids_raw` asserts raw-string divergent-fail. |
| T4 | `max_nodes=0` / negative | **IMPLEMENTED** | Click `type=int` accepts `0`; MCP `kb_graph_viz` at `src/kb/mcp/health.py:191-197` rejects `0` with error string and clamps negatives via `max(1, min(max_nodes, 500))`. AC2 CLI surface forwards verbatim. Test `test_graph_viz_body_executes_forwards_max_nodes` asserts the kwarg reaches the MCP tool unmodified. Help text documents the contract: "`Max nodes in graph (default 30; 1-500; 0 rejected).`" (C5 verified). |
| T5 | AC1 breaks audit-grep assertions | **IMPLEMENTED** | Full pytest on `tests/test_cycle23_rebuild_indexes.py` + `tests/test_cycle29_rebuild_indexes_hardening.py` → 29 passed, 1 skipped, 0 failed. Load-bearing head anchors (`"vector=cleared (warn: tmp:"`, `"manifest=cleared"`) survive head+tail truncation because they sit within `half = max(40, (500-40)//2) = 230` chars of the head. |
| T6 | Decorator theft (cycle-27 L1) | **IMPLEMENTED** | AC2-AC6 are pure `@cli.command` additions appended at EOF (no helper extraction between decorators). `grep -c "^@cli.command" src/kb/cli.py` = 19 (14 pre-cycle + 5 new cycle-30). All 5 new decorator blocks have distinct `def <fn>` lines — no sharing. |
| T7 | Docstring orphan (cycle-23 L1) | **IMPLEMENTED** | All 5 new CLI functions place `from kb.mcp.<mod> import <tool>` AFTER the triple-quoted docstring closes. Pattern matches cycle-27 `search`/`stats` precedent at `cli.py:584-595`. Manual review of TASK 2-4 edits confirms no function-body import before docstring. |
| T8 | Raw `{e}` leak in `except` clause | **IMPLEMENTED** | All 5 new CLI commands use `except Exception as exc: _error_exit(exc)` outer wrap. `grep -c "_error_exit(exc)" src/kb/cli.py` = 13 (8 cycle-27 baseline + 5 cycle-30). No `f"Error: {e}"` raw-format in new code. |

**Threat-model verdict:** ALL IN-SCOPE items IMPLEMENTED. No PARTIAL or MISSING.

## (b) PR-introduced CVE diff

```
baseline (main): ['CVE-2025-69872', 'CVE-2026-6587']
branch HEAD:    ['CVE-2025-69872', 'CVE-2026-6587']
PR-introduced:  (empty — PASS)
```

Both baseline vulns are CVE-2025-69872 (diskcache) + CVE-2026-6587 (ragas) — identical to cycle-25/26/28/29 baselines, both with empty `fix_versions` (no upstream patch). No new advisories introduced.

**Verdict:** CVE diff PASS.

## (c) Same-class peer scan (cycle-20 L3)

Cycle 30 design Q13 + BACKLOG narrow already enumerate all 12 same-class MCP-tool peers by category:
- Write-path (7): `kb_review_page`/`kb_refine_page`/`kb_query_feedback`/`kb_save_source`/`kb_save_lint_verdict`/`kb_create_page`/`kb_capture` — deferred to a write-path input-validation cycle
- Read-bearing / page_id-input (3): `kb_read_page`/`kb_affected_pages`/`kb_lint_deep` — deferred to a page_id-centric cycle
- Ingest/compile variants (2): `kb_ingest_content`/`kb_compile_scan` — partially covered

BACKLOG.md:146 enumerates all 12 explicitly. **Verdict:** peer scan complete.

## (d) Deferred-promise enforcement (cycle-23 L3)

Grep for deferred / out-of-scope language across cycle-30 decision docs:
- 16 occurrences total (inside requirements / threat-model / design / design-eval docs).
- All correspond to the BACKLOG CLI-MCP parity narrow at `BACKLOG.md:146` which enumerates each deferred category + its target cycle.

**Verdict:** every `deferred` reference in cycle-30 docs maps to a BACKLOG entry.

## (e) CONDITION verification (C1-C15 from design gate)

| C# | Status | Evidence |
|---|---|---|
| C1 | ✅ | `grep -c "truncate(str(block" src/kb/compile/compiler.py` = 2 (both branches capped). |
| C2 | ✅ | `grep -n "from kb.utils.text import truncate" src/kb/compile/compiler.py` = 1 hit, inside `_audit_token` body. |
| C3 | ✅ | `tests/test_cycle30_audit_token_cap.py` 7 tests pass, covering unit + e2e + clean-path truthiness (R2-A2 addendum). |
| C4 | ✅ | Full-suite run shows cycle-23 + cycle-29 rebuild_indexes tests all pass (29 passed, 1 skipped). |
| C5 | ✅ | `grep "1-500; 0 rejected" src/kb/cli.py` → 1 hit in `graph-viz --max-nodes` help text. Test `test_graph_viz_help_exits_zero` asserts presence. |
| C6 | ✅ | `grep -n "page_ids.split" src/kb/cli.py` → zero hits. Test `test_lint_consistency_body_executes_with_ids_raw` asserts raw-string passthrough. |
| C7 | ✅ | `grep -A3 "def lint_consistency" src/kb/cli.py` shows signature `(page_ids: str)` — no `wiki_dir` param. Test asserts `"--wiki-dir" not in result.output`. |
| C8 | ✅ | Manual inspection of all 5 new CLI function bodies: function-local `from kb.mcp.*` import sits AFTER closing `"""`. |
| C9 | ✅ | `grep "Path(wiki_dir)" src/kb/cli.py` → 1 hit at line 551 (pre-existing `rebuild_indexes_cmd`, NOT cycle-30 code). New AC2-AC5 blocks forward `wiki_dir` raw. |
| C10 | ✅ | `grep -c "_error_exit(exc)" src/kb/cli.py` = 13 (5 new + 8 pre-existing). Pattern uniform across cycle-30 additions. |
| C11 | ✅ | `tests/test_cycle30_cli_parity.py` contains 5 `TestXxxCli` classes (one per subcommand). Each class has `--help` smoke + body-executing spy test. Total 13 tests. |
| C12 | ✅ | Commit history: 4cdcb5e (AC1) + 78af9a3 (AC2+AC3) + eaf2bb3 (AC4+AC5) + 2b7b748 (AC6) + 824f78f (AC7 BACKLOG) = 5 code commits. Step-12 doc commit forthcoming = 6 total per Q6 plan. |
| C13 | ✅ | `git diff origin/main BACKLOG.md` shows ONLY the two target edits (cycle-29 audit-cap delete + CLI-parity narrow). No unrelated edits. R2-A3 arithmetic correction ("14 → 12") applied. |
| C14 | ✅ | Full pytest pass (2836 passed + 10 skipped). `pytest --collect-only -q \| tail -1` shows `2846 tests collected` (delta +20). Ruff check + format all pass. |
| C15 | ⚠️ pending | PR body at Step-13 must include R3-SKIP note per Q11. |

## (f) Self-check PARTIAL policy per cycle-12 L3

Zero PARTIAL findings. Zero MISSING findings. All 8 threat items IMPLEMENTED. No follow-up BACKLOG entries filed.

## FINAL STEP-11 VERDICT

**PASS.** Proceed to Step 11.5 (CVE opportunistic patch — no-op per baseline, identical cycle-29 profile) and Step 12 (doc update).
