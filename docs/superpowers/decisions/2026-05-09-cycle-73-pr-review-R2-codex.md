# Cycle 73 — Step 20 R2 PR review (Codex)

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**PR:** #103
**Reviewer:** Codex GPT-5 (`codex:codex-rescue`)
**Round:** R2 (architecture / contract regressions in R1-fix commits + flag any NEW issue R1 missed)

<!-- Subagent fills in below this line. Pre-created by primary session
per cycle-72 L4 (sandbox blocks subagent Write tool). -->

## VERDICT

**NEEDS-REVISION**

## Findings

No BLOCKER findings.

- MAJOR M-1: [tests/test_cycle73_tier_boundary.py:241] — AC03's claimed orchestrator-wiring test manually replays the expected `_call_llm_json` -> `_validate_tier_boundary` sequence in the test body (`tests/test_cycle73_tier_boundary.py:248-256`) instead of invoking `run_augment`'s production auto-ingest path (`src/kb/lint/augment/orchestrator.py:502-515`). Removing the production validator call at `src/kb/lint/augment/orchestrator.py:512-515` would not fail this test, so the required "orchestrator integration test confirms the helper is called between `_call_llm_json` and the persister, via spy" lock-in is not actually present.
- MAJOR M-2: [tests/test_cycle73_tier_boundary.py:325] — AC04's manifest-distinctness test manually implements the catch block and writes `payload={"reason": f"tier_boundary_rejected: {e}"}` itself at `tests/test_cycle73_tier_boundary.py:338-343`; it never exercises the production split-catch at `src/kb/lint/augment/orchestrator.py:516-530`. Reordering/removing `except TierBoundaryError` or changing the production prefix at `src/kb/lint/augment/orchestrator.py:524` would not fail this test, so the required fail-closed persister-side behavior is not locked in.
- MINOR m-1: [src/kb/lint/augment/orchestrator.py:524] — the manifest reason prefixes raw `str(e)` with `tier_boundary_rejected:`, while `_validate_tier_boundary` includes unsanitized attacker-controlled key names in rejection messages (`src/kb/lint/augment/orchestrator.py:108-110`, `src/kb/lint/augment/orchestrator.py:127-135`). If an injected key contains the literal `tier_boundary_rejected:`, one manifest reason line can contain duplicate forensic prefixes. This does not break the distinct outcome, but it weakens count-based forensic grep and the inner message is not bounded/sanitized.
- NIT n-1: [src/kb/lint/semantic.py:52] — `_cap_page_content(None, max_chars)` raises a generic `TypeError` from `len(text)`. The observed production `pair_page_with_sources` path returns `_body` from `frontmatter.load(...).content` (`src/kb/utils/pages.py:61-62`, `src/kb/review/context.py:139-143`), so I did not escalate this beyond a nit, but the direct edge case requested in the review is not handled with an explicit default or clear validation error.

## Edge-case verification checklist

1. PASS: [src/kb/lint/augment/orchestrator.py:131] — string length rejection uses `len(value) > max_string_len`, so a string of length exactly `4096` passes; `4097+` fails.
2. PASS: [src/kb/lint/augment/orchestrator.py:78] — default `max_depth` is `4`. With root dict counted as level 1 and values started at depth 2 (`src/kb/lint/augment/orchestrator.py:145-146`), `{"a": {"b": {"c": {"d": "leaf"}}}}` reaches the leaf at depth 5 and raises via `depth > max_depth` (`src/kb/lint/augment/orchestrator.py:116-120`).
3. PASS: [src/kb/lint/augment/orchestrator.py:137-142] — empty dict/list values iterate zero times and return cleanly; there is no final raise block after those branches.
4. PASS: [src/kb/lint/augment/orchestrator.py:71] — `_TBV_ALLOWED_VALUE_TYPES` excludes `set`; a set value reaches the unsupported-type branch at `src/kb/lint/augment/orchestrator.py:125-128` and raises `TierBoundaryError`.
5. MINOR m-1: [src/kb/lint/augment/orchestrator.py:524] — inner exception text is not sanitized/bounded before the `tier_boundary_rejected:` prefix is added.
6. PASS: [src/kb/lint/verdicts.py:85-88] — `bool` prompt versions are explicitly rejected before the return path; `True` returns `0`, not `1`.
7. PASS/OBSERVED: [src/kb/lint/verdicts.py:89] — negative ints are accepted as-is because there is no lower-bound check; `{"prompt_version": -1}` returns `-1`.
8. PASS: [src/kb/lint/augment/orchestrator.py:516] — `except TierBoundaryError` appears before generic `except Exception` at `src/kb/lint/augment/orchestrator.py:530`.
9. NIT n-1: [src/kb/lint/semantic.py:498-499] — `build_completeness_context` passes `paired["page_content"]` directly into `_cap_page_content`; direct `None` input is not handled explicitly.
10. PASS: [src/kb/lint/semantic.py:93-110] — `_render_sources([], lines, budget=...)` has no iterations and returns without indexing; empty source lists are safe.
11. PASS: [tests/test_cycle73_snapshots.py:60] — snapshot tests use pytest's function-scoped `monkeypatch` fixture; `date` is patched through that fixture at `tests/test_cycle73_snapshots.py:57` and restored after each test.
12. PASS: [tests/test_cycle73_prompt_version.py:233] — all observed cycle-73 production-module monkeypatches use the `monkeypatch` fixture inside test functions/classes (`tests/test_cycle73_completeness_wrap.py:86`, `tests/test_cycle73_tier_boundary.py:215`, `tests/test_cycle73_snapshots.py:57`); no module-level raw `setattr` escape was observed.
13. PASS: [src/kb/lint/augment/orchestrator.py:11-20] — imports/top-level constants are in valid positions after formatting. `git diff --stat c39a8f9..HEAD` shows only the two R1 review docs changed after the `style(cycle-73): ruff format` commit, so no post-format source/test edit drift was observed.
