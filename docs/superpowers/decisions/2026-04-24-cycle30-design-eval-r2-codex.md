## Analysis

Read the required Cycle 30 docs, `cli.py`, `_audit_token` / `rebuild_indexes`, MCP health/quality slices, `truncate`, and the git log. Regression context SHAs: cycle 27 `9ad467b` / `d4e5840` / `cc45814`; cycle 29 `aa419ef` / `6fc39e0` / `e52360d`.

Main drift: the structured headings here do not match Cycle 30 requirements. Requirements define AC3=`verdict-trends`, AC4=`detect-drift`, AC6=`lint-consistency`, while this review contract says `evolve`, `stats`, `affected_pages`. Treat that as design-gate blocking ambiguity, not implementation detail.

## AC1 — _audit_token truncation

- EDGE: `_audit_token` currently has three branches: clean `cleared`, warned `cleared (warn: ...)`, and fallback error/`unknown` (`src/kb/compile/compiler.py:590-603`). AC1 must not compute `truncate(str(block["error"]))` before the truthiness branch, or `None` becomes `"None"` and breaks the clean string promised by requirements (`docs/...cycle30-requirements.md:65-71`).
- REDACTION: non-string errors are handled if and only if `str(raw_error)` happens inside the truthy error branches before `kb.utils.text.truncate` (`src/kb/utils/text.py::truncate`).
- TEST-DEFEAT: AC1 test must assert the raw 2000-char string is absent from both `_audit_token` output and `wiki/log.md`; existing head assertions are `manifest=cleared` / `vector=cleared (warn: tmp:)` (`tests/test_cycle23_rebuild_indexes.py:270-273`, `tests/test_cycle29_rebuild_indexes_hardening.py:101-106,211-215`).
- verdict: APPROVE-WITH-AMEND — require branch-preserving pseudocode.

## AC2 — graph_viz CLI args

- EDGE: `kb_graph_viz` rejects `max_nodes == 0` itself and clamps negatives (`src/kb/mcp/health.py:191-197`). Click `type=int` will pass `0`, but `--max-nodes=` dies in Click parsing with usage exit 2 before MCP, so tests must not expect an MCP `Error:` line for blank/non-int input.
- INTEGRATION: proposed `--wiki-dir` mirrors existing `stats` `click.Path(exists=True, file_okay=False, resolve_path=True)` (`src/kb/cli.py:622-630`) then MCP containment (`src/kb/mcp/health.py:17-18`, `src/kb/mcp/app.py:141-164`). A symlink to outside is not a bypass because the resolved outside path is rejected, but error class differs from MCP for non-existent paths.
- TEST-DEFEAT: requirements say monkeypatch `kb.cli.kb_graph_viz` (`docs/...requirements.md:97-100`), but function-local imports mean the cycle-27 working pattern patches the source module (`tests/test_cycle27_cli_parity.py:156-166`, `src/kb/cli.py:636`).
- verdict: APPROVE-WITH-AMEND — fix test spy target and parser-error expectation.

## AC3 — evolve CLI --wiki-dir

- INTEGRATION: Cycle 30 AC3 is `verdict-trends`, not `evolve` (`docs/...requirements.md:104-109`). Existing CLI `evolve` has no `--wiki-dir` (`src/kb/cli.py:330-340`), while MCP `kb_evolve` does (`src/kb/mcp/health.py:131-140`). Step 5 must choose whether this is a heading typo or a scope change.
- EDGE: `--wiki-dir` omitted becomes `None`; explicit `--wiki-dir ""` is normalized by Click Path to CWD in local probe, then validator treats it as a real absolute path (`src/kb/mcp/app.py:144-164`; cycle-29 Path-empty lesson `docs/...cycle29-self-review.md:56-72`).
- verdict: APPROVE-WITH-AMEND — resolve AC identity and empty-string policy.

## AC4 — stats CLI --wiki-dir

- INTEGRATION: Cycle 30 AC4 is `detect-drift`, not `stats` (`docs/...requirements.md:111-117`). `stats` already has the cycle-27 wrapper and `--wiki-dir` passthrough (`src/kb/cli.py:622-645`); `kb_detect_drift` is the uncovered target (`src/kb/mcp/health.py:236-252`).
- EDGE: same Click pre-validation vs MCP containment split as AC2; keep tests aware of CLI usage exit versus MCP `Error:` prefix.
- verdict: APPROVE-WITH-AMEND — correct the AC4 target.

## AC5 — reliability_map CLI

- INTEGRATION: `kb_reliability_map()` is zero-arg and returns `"No feedback recorded yet..."` as success, not `Error:` (`docs/...requirements.md:119-125`, `src/kb/mcp/quality.py:230-245`). Do not add `--wiki-dir` or convert the empty state to exit 1.
- TEST-DEFEAT: spy should patch `kb.mcp.quality.kb_reliability_map` unless a deliberate module-level `kb.cli` alias is introduced, which would violate the function-local import pattern.
- verdict: APPROVE.

## AC6 — affected_pages CLI

- INTEGRATION: Requirements explicitly exclude `kb_affected_pages` (`docs/...requirements.md:45-50`); AC6 is `lint-consistency` with `--page-ids TEXT` default `""` (`docs/...requirements.md:128-136`). `kb_affected_pages` is single `page_id` and backlink-computing (`src/kb/mcp/quality.py:264-281`).
- EDGE: preserve `--page-ids` default as empty string, not `None`; MCP maps empty to auto mode at `src/kb/mcp/quality.py:173-181`.
- verdict: APPROVE-WITH-AMEND — fix heading/scope; keep raw string passthrough.

## AC7 — BACKLOG narrowing arithmetic

- INTEGRATION: Count math `14-5=9` is not name-verifiable. BACKLOG says 14 but enumerates 16, including non-tool `kb_save_synthesis` (`BACKLOG.md:149`; actual `_save_synthesis` helper at `src/kb/mcp/core.py:220`, `kb_query(save_as)` at `src/kb/mcp/core.py:285-292`).
- EDGE: after removing the five planned tools, the BACKLOG-derived actual MCP remainder is at least 10: `kb_review_page`, `kb_refine_page`, `kb_query_feedback`, `kb_save_source`, `kb_save_lint_verdict`, `kb_create_page`, `kb_capture`, `kb_read_page`, `kb_affected_pages`, `kb_lint_deep`; actual MCP also has unlisted `kb_ingest_content` and `kb_compile_scan` (`src/kb/mcp/core.py:652-660,890-910`).
- INTEGRATION: cycle 29 ended with explicit no-auto-start guidance (`docs/...cycle29-self-review.md:120-131`); Cycle 30 Step-16 must repeat that instead of chaining into a new cycle.
- verdict: REJECT — AC7 must be recomputed from tool inventory.

## Design Gate Must-Answer

- Which AC names are authoritative: requirements or this review contract headings?
- What exact `_audit_token` pseudocode preserves `None -> cleared` while capping non-string errors?
- Are CLI tests patching MCP source modules or intentional `kb.cli` aliases?
- Is explicit `--wiki-dir ""` accepted as CWD or rejected before Click Path coercion?
- What is the verified remaining CLI/MCP tool list; why exactly 9?
- Does Step-16 include the cycle-29 no-auto-start termination clause?

## Security / CVE Residuals

No new CVE gap found; AC7 same-day skip is consistent with the threat model baseline (`docs/...cycle30-threat-model.md:38-40`). Real residual is CLI `--wiki-dir` error-class drift and explicit-empty normalization to CWD.

## FINAL VERDICT

APPROVE-WITH-AMEND — Design is mostly sound, but AC identity drift, spy-target mismatch, and AC7 arithmetic must be fixed before implementation.
