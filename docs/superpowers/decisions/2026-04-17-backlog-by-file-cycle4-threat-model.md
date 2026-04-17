# Cycle 4 — Threat Model (Step 2 artifact)

**Date:** 2026-04-17 **Branch:** `feat/backlog-by-file-cycle4`
**Scope:** 30 items / 16 files mechanical backlog cleanup (requirements doc above).
**Author:** Opus subagent; reproduced verbatim for Step 11 checklist consumption.

## Trust boundaries

Cycle 4 is a hardening batch — several items **sit ON trust boundaries** rather than crossing them:

| # | Trust-boundary chain | Source (untrusted) → Sink (privileged) |
|---|---|---|
| 1 | MCP tool response → client terminal | Absolute paths in `_rel` interpolation leak filesystem layout to caller |
| 2 | **MCP client → rewriter LLM prompt** | `conversation_context` (attacker-controlled) → `rewrite_query` prompt → scan-tier LLM. Classic prompt-injection / jailbreak vector |
| 4 | **MCP client → filesystem** | `source_type` (attacker-controlled) → `SOURCE_TYPE_DIRS` lookup → `raw/<dir>/` path resolution |
| 5 | **MCP client → filesystem** | `kb_ingest_content` / `kb_save_source` write to `raw/` after path validation |
| 6 | MCP client → BM25 index | `question` → `search_pages` (DoS via unbounded length) |
| 9 | **MCP client → wiki body** | `kb_create_page` title + content → disk; control-chars + length cap gate |
| 10 | **MCP client → filesystem reads** | `source_refs` resolved against `PROJECT_ROOT`; needs `is_file()` within PROJECT_ROOT, NOT arbitrary path |
| 11 | MCP client → page lookup | `page_id` → `_validate_page_id(check_exists=True)` |
| 12 | MCP client → verdict store JSON | `description` unbounded → disk; 4KB cap prevents store bloat |
| 13 | **MCP client → Windows filesystem** | `page_id = "CON"` / `"PRN"` → `WIKI_DIR / "CON.md"` opens device, not file |

Items NOT crossing a trust boundary: 3, 7, 8, 14, 15, 16, 17, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30.

## Authn / authz

**Confirmed none.** Single-user KB over stdio MCP transport; no tokens, no session state, no escalation surface. **No auth changes in cycle 4.**

## Logging / audit requirements

- **#13 `_validate_page_id` Windows-reserved reject** — `logger.warning("Rejected reserved-name page_id: %s", page_id)` — operators must see repeated probing.
- **#22 contradiction telemetry** — WARNING log remains when truncated; dict return is additive, not a replacement.
- **#20 log rotation event** — log rotation event at `logger.info("Rotated %s to %s (%d bytes)")` BEFORE renaming — preserves audit chain.
- **#5 partial-write `Error[partial]`** — `logger.warning("kb_save_source partial write: %s bytes to %s; overwrite required")` — operator audit record independent of client.
- **#21 malformed frontmatter warning** — `logger.warning` specified; acceptable.

## Step 11 verification checklist (condensed)

Step 11 subagent must run each check:
- `grep _rel( src/kb/mcp/core.py` — every error-string `Path` interpolation routes through `_rel()`.
- `grep "<prior_turn>" src/kb/mcp/core.py src/kb/query/rewriter.py` — sentinel present AND input sanitised.
- `grep "\[source:" src/ tests/` — exhaustive sweep; every remaining parser updated or test-marked stale.
- `grep SOURCE_TYPE_DIRS src/kb/mcp/core.py` — `kb_ingest` whitelist check after empty branch.
- `grep "Error\[partial\]" src/kb/mcp/core.py` — OSError branch in both ingest_content + save_source, includes overwrite hint.
- `grep MAX_QUESTION_LEN src/kb/mcp/browse.py` — enforced before `search_pages`.
- `grep QUERY_CONTEXT_MAX_CHARS src/kb/mcp/browse.py` — `kb_read_page` truncate + footer.
- `grep "ambiguous page_id" src/kb/mcp/browse.py` — error on >1 case-insensitive match.
- `grep check_exists=True src/kb/mcp/quality.py` — `kb_affected_pages` validates.
- `grep "CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]" src/kb/mcp/app.py` — reserved set + `len <= 200`.
- `grep source-deleted src/kb/mcp/health.py` — three-category drift partition.
- `grep _WH_QUESTION_RE src/kb/query/rewriter.py` — regex exists + CJK-safe length gate.
- `grep -rn _postings src/kb/query/bm25.py` — postings dict populated in `__init__`.
- `grep _enforce_type_diversity src/kb/query/dedup.py` — running quota, not fixed cap.
- `grep STOPWORDS src/kb/utils/text.py` — removed words absent; no duplicate list in BM25 or contradiction.
- `grep -E "ufeff|u2028|u2029" src/kb/utils/text.py` — yaml_escape handles BOM + line-separators.
- `grep -E "log\.[0-9]" src/kb/utils/wiki_log.py` — rotation target pattern.
- `grep malformed_frontmatter src/kb/lint/checks.py` — distinct issue category.
- `grep DeprecationWarning src/kb/graph/export.py` — named removal target.
- `grep VALID_SOURCE_TYPES src/kb/compile/compiler.py` — whitelist check.
- `grep -A1 "CLAUDE_SCAN_MODEL\|CLAUDE_WRITE_MODEL\|CLAUDE_ORCHESTRATE_MODEL" .env.example` — three commented lines present.
- Read `CLAUDE.md` query_wiki section — `conversation_context` + `stale` documented.
- `grep load_purpose src/kb/` — every caller passes explicit `wiki_dir`.
- `grep "sort.*key=len.*reverse=True\|sorted.*len" src/kb/compile/linker.py` — title ordering pre-substitution.

## Novel risk callouts (verdicts)

- **Item #2 `<prior_turn>` sentinel** — **RISK.** Attacker can embed `</prior_turn>` closer. **Mitigation:** strip both `<prior_turn>` and `</prior_turn>` literals from `conversation_context` BEFORE wrapping (case-insensitive, also strip `<prior_turn ...>` variants with attributes). Add control-char strip in same pass.
- **Item #3 `[source: X]` → `[[X]]`** — **RISK.** Change is good for wikilink consistency but requires exhaustive grep for `[source:` parsers across `src/` + `tests/` before landing. Also: `[[X]]` will be picked up by `inject_wikilinks` in ingest; confirm intended or suppress.
- **Item #4 source_type whitelist** — **ACCEPTABLE.** `SOURCE_TYPE_DIRS` is canonical 9-type list; empty-string branch preserved; any test passing unknown types was exercising a bug.
- **Item #18 STOPWORDS removal** — **ACCEPTABLE.** Words removed are pure ranking signals; no exfiltration vector (single-user KB).
- **Item #22 contradiction return-dict** — **RISK.** Grep confirms `pipeline.py:909` + 4 tests consume `detect_contradictions` as `list[dict]`. **Mitigation:** use existing sibling `detect_contradictions_with_metadata` (cycle 3 shipped). Item #22 becomes "migrate `pipeline.py` caller + MCP surface to the metadata sibling; leave list variant intact for back-compat". **DO NOT change `detect_contradictions` signature.**
- **Item #30 `FRONTMATTER_RE` unification** — **ALREADY SHIPPED (cycle 1, PR #13).** `refiner.py:16` already imports from `utils/markdown`. Verify no secondary local regex and **mark DROPPED-ALREADY-SHIPPED in decision doc** (cycle 4 lesson alignment).

## Dep-CVE baseline

- **Dependabot (GitHub):** 0 open alerts.
- **pip-audit (local venv):** 7 vulns in 4 packages — `diskcache==5.6.3` (no fix), `langsmith==0.7.25→0.7.31`, `pip==24.3.1` (tool-chain, non-runtime), `python-multipart==0.0.22→0.0.26`.
- **requirements.txt state (verified via grep):** `diskcache==5.6.3` (pinned, no fix), `langsmith==0.7.31` (already patched), `python-multipart==0.0.26` (already patched).
- **Reconciliation:** local venv is stale; `requirements.txt` is source of truth. Step 12.5 action: re-run `pip install -r requirements.txt` in venv to sync then re-audit. If the audit is clean post-sync, no code changes needed; otherwise pin `langsmith>=0.7.31` / `python-multipart>=0.0.26` explicitly (they already are; no-op).
- **Cycle 4 introduces no new deps (non-goal).** Step 11 pip-audit diff vs baseline must be **empty**.

## Scope adjustments vs requirements doc

1. **Drop item #30** — shipped in cycle 1; cycle 4 verifies via grep and notes DROPPED-ALREADY-SHIPPED.
2. **Reshape item #22** — do not change `detect_contradictions` list signature. Migrate `pipeline.py:909` caller to the `detect_contradictions_with_metadata` sibling (already exists) and surface its `truncated: bool` + `claims_*` through the MCP tool result. No test migration required for the legacy list callers.
3. **Harden item #2** — closer strip + control-char strip required beyond the opening sentinel.
4. **Harden item #3** — exhaustive `[source:` grep in src/ + tests/ before migration; document any callers updated.

Remaining 27 items proceed as specified.
