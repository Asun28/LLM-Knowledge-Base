# Cycle 5 Redo — Threat Model (Step 2)

**Date:** 2026-04-18
**Author:** Opus subagent (architect)
**Feeds:** Step 5 design gate + Step 11 security verify

## Summary

Cycle 5 fixes touch two attack surfaces:

1. **Prompt-injection hardening** (items 1, 4, 5, 6) — `wrap_purpose` sentinel + word-boundary regex reduce LLM-prompt attack surface from file-system-writable `wiki/purpose.md` and LLM-supplied entity names.
2. **Data-layer hygiene + operational signal** (items 2, 3, 7, 8, 9-13) — control-char rejection, citation format, User-Agent, logging guards, pytest markers.

## Key findings to carry into Step 11

1. **GAP — citation-format asymmetry.** `mcp/core.py:208` was updated to instruct `[[page_id]]` but `query/engine.py:733` (API-mode synthesis prompt) still instructs `[source: page_id]`. Mixed styles depending on `use_api` flag.
2. **GAP — wrap_purpose sentinel forgery not guarded.** No escape of inner `</kb_purpose>` tokens; an attacker-controlled purpose can emit a forged closer and inject instructions after it. Textual defense only.
3. **GAP — `\b` ASCII boundary.** `_extract_entity_context` word-boundary regex falls back to substring semantics for CJK/non-Latin entity names.
4. **GAP — page-id length inconsistency.** `_validate_page_id` checks 255 chars; config has `MAX_PAGE_ID_LEN=200`.
5. **GAP — `load_verdicts` silent recovery no telemetry.** Corrupt file silently returns empty list, hiding prior fail verdicts.

## Threat Model Table (per item)

See full analysis in Agent output. Residual risks recorded per item (1-14).

## Step 11 Verification Checklist

Each row is a YES/NO the reviewer runs against the cycle 5 diff:

- [ ] `wrap_purpose` called from EVERY caller of `load_purpose` (grep both).
- [ ] `wrap_purpose` regex preserves `\t \n \r`.
- [ ] No raw `purpose` f-string interpolation bypassing the helper.
- [ ] `WIKI_CATEGORIES` zero remaining imports in `src/` + `tests/`.
- [ ] `VALID_SEVERITIES`, `VALID_VERDICT_TYPES` imported ONLY from `kb.config`.
- [ ] `load_verdicts` catches exactly `(JSONDecodeError, OSError, UnicodeDecodeError)`.
- [ ] `query/engine.py:733` citation instruction resolved — `[source: page_id]` updated OR documented as intentional.
- [ ] `ingest/extractors.py:build_extraction_prompt` uses `wrap_purpose(purpose)`; `None` branch preserved.
- [ ] `_extract_entity_context` uses `re.escape(name_lower)` inside `\b...\b`.
- [ ] Word-boundary regex applied to BOTH `(core_argument, abstract, …)` and `(key_claims, key_points)` branches.
- [ ] `_validate_page_id` control-char check runs BEFORE path-traversal check.
- [ ] `_CTRL_CHARS_RE` at module scope.
- [ ] MCP `instructions=` string + inline help text both use `[[page_id]]`.
- [ ] `kb_save_source` hint uses `yaml_escape(source_type)`.
- [ ] Anthropic client `default_headers` inside double-check lock.
- [ ] `__version__` import resolves at module load.
- [ ] CLI and MCP-server `basicConfig` use same predicate + level.
- [ ] `pyproject.toml` all four markers registered with descriptions.
- [ ] Regression test asserts EXACT unicode preservation (not just "contains newline").
- [ ] `test_anthropic_client_sets_package_user_agent` monkeypatches `_client = None` first.

## Dep-CVE Baseline (Step 2b)

Captured 2026-04-18 on `main` (prior to `feat/cycle5-redo-audit`):
- Dependabot alerts: 0 open (verified via gh api)
- pip-audit: 3 pre-existing advisories — `diskcache 5.6.3` (CVE-2025-69872 — pickle deserialization), `pip 24.3.1` (multiple advisories — vulnerability scanner self-references)
- **Class A** (existing on main) — candidates for Step 12.5 opportunistic patch.
- **Class B** (PR-introduced by this redo) — expected to be zero (no dep bumps planned).

## Risk prioritization for Step 5 decision gate

**MUST FIX this cycle** (has concrete attack or incorrect-behaviour vector):
- Gap 1 (citation format asymmetry) — produces mixed output citation styles, breaks retroactive backlink detection in API mode.

**SHOULD ADD TEST** (no attack today, but thin coverage invites regression):
- Gap 3 (CJK entity boundary) — add a failing test with a Japanese entity name.
- Gap 4 (page-id length inconsistency) — add a test at the 200-255 boundary, decide which limit wins.
- wrap_purpose sentinel forgery — add a test for an input containing `</kb_purpose>` verifying the payload is either escaped or visibly passed through.

**OK TO DEFER** (availability over visibility):
- Gap 2 (sentinel forgery hard fix) — textual-defense is accepted; log a BACKLOG entry.
- Gap 5 (load_verdicts telemetry) — logger.warning on widened path is sufficient.
