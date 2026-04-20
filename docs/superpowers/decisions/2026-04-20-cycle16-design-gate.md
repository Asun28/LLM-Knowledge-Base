# Cycle 16 — Design Decision Gate (Step 5)

**Date:** 2026-04-20
**Input:** R1 Opus (APPROVE-WITH-AMENDMENTS, 5 REVISE), R2 Codex (REJECT, 2 BLOCK + 4 REVISE)
**Output:** 10 decisions, 6 conditions, final amendments below.

---

## Q1 — `save_as` synthesis `source:` list — DECIDE: b

Use `source_pages` (wiki page IDs) as `source:`. `validate_frontmatter` rejects empty `source: []` explicitly. If `source_pages` is empty (refusal path gate already prevents this), return MCP error string.

## Q2 — Incremental sibling cleanup — DECIDE: a

Unconditional cleanup on every publish. O(|excluded|) `unlink(missing_ok=True)` calls — trivial cost. Manifest approach (option c) deferred to BACKLOG when N(retracted) > 1000.

## Q3 — Slug validation — DECIDE: b

Require BOTH `slugify(slug) == slug` AND `re.fullmatch(r"[a-z0-9-]+", slug)`. Slugify catches structural issues; regex catches Cyrillic/CJK homoglyphs.

## Q4 — Absent-status handling — DECIDE: b

Include absent-status pages sorted LAST (matches AC4 "sort LAST" wording). Filter only invalid/injected statuses (T13 defense — `"<script>"`-shaped values).

## Q5 — `_suggest_rephrasings` hardening — DECIDE: b

Narrow except to `(LLMError, OSError)`; strip bullet/number prefixes; drop lines > 300 chars; drop lines containing `\n` after strip. Schema parse (option c) is overkill at scan tier.

## Q6 — Echo filter normalisation — DECIDE: b

Normalise both sides via `re.sub(r"[\W_]+", " ", s).strip().lower()` — catches `"X?"` vs `"X"` and `"X."` vs `"X"` echoes.

## Q7 — AC14 dead-code — DECIDE: drop conditional

`runner.py:138` already seeds `"info": 0`. Drop the "if absent" branch; add assertion test to lock the contract.

## Q8 — `kb_query` read→write shift — DECIDE: c

Keep one-call ergonomics; document the shift in tool docstring + cycle-16 non-goals. Split-tool (option b) costs a second MCP roundtrip.

## Q9 — Builder signature asymmetry — DECIDE: c

Leave `build_sitemap_xml(..., out_path, ...)` vs `build_per_page_siblings(..., out_dir, ...)` asymmetry as-is. Mirrors existing peer conventions (single-file = full path, multi-file = base dir). Document in module docstring.

## Q10 — Slug bucket radius — DECIDE: b

Bucket radius = `DUPLICATE_SLUG_DISTANCE_THRESHOLD` (3), not ±1. Levenshtein lower-bound `|len(a)-len(b)| <= distance` — radius 1 misses distance-2 and distance-3 pairs.

## Conditions (cross-Q invariants)

- **C1:** `kb_query(save_as=...)` output MUST pass `validate_frontmatter` with zero errors.
- **C2:** `save_as` validation path MUST return error strings, never raise (verified under `KB_DEBUG=1`).
- **C3:** Every publish call (incremental or not) MUST remove sibling files for currently-excluded pages; idempotent.
- **C4:** `_validate_save_as_slug` MUST apply BOTH `slugify(slug) == slug` AND `re.fullmatch(r"[a-z0-9-]+", slug)`.
- **C5:** `_suggest_rephrasings` MUST normalise via `re.sub(r"[\W_]+", " ", s).strip().lower()`; drop > 300-char candidates; catch only `(LLMError, OSError)`.
- **C6:** Duplicate-slug bucket iteration MUST use radius = `DUPLICATE_SLUG_DISTANCE_THRESHOLD`.

## Final decided amendments

Baked into `docs/superpowers/specs/2026-04-20-cycle16-design.md` as the canonical spec (see commit). Concrete changes:

1. **AC18 (Component 6):** `source=list(result_dict.get("source_pages") or [])`; if empty after threading, return `"Error: cannot save synthesis — query returned no source_pages"`. No write.
2. **AC19 (Component 6):** `_validate_save_as_slug` applies BOTH slugify idempotence check AND `re.fullmatch(r"[a-z0-9-]+", slug)`.
3. **AC22 (Component 7):** `build_per_page_siblings` cleanup runs UNCONDITIONALLY (before skip check). BACKLOG follow-up for manifest approach.
4. **AC4 (Component 2):** Absent-status pages INCLUDED, sorted last; invalid-status (not in `PAGE_STATUSES`) filtered; mature/evergreen excluded.
5. **AC7 (Component 3):** Narrow except `(LLMError, OSError)`; bullet-strip prefix regex; 300-char cap; drop lines with embedded `\n` after strip.
6. **AC9 (Component 3):** `_normalise_for_echo(s) = re.sub(r"[\W_]+", " ", s).strip().lower()` helper applied both sides.
7. **AC14 (Component 5):** Drop dead "if absent" branch; add lock-in test `report["summary"]["info"] == len(inline_callouts)`.
8. **AC17 (Component 6):** Docstring note on read→write shift; non-goals amendment.
9. **AC20/21 (Component 7):** Asymmetry preserved + documented in module docstring.
10. **AC10 (Component 4):** Bucket iteration radius = threshold (3); regression test `test_duplicate_slugs_length_diff_3_flagged` for `foo` vs `foobar`.

## New test cases added

1. `test_save_as_source_from_source_pages` (Q1/C1)
2. `test_save_as_empty_source_pages_returns_error` (Q1/C1)
3. `test_save_as_cyrillic_a_rejected` (Q3/C4)
4. `test_enrichment_includes_absent_status_sorted_last` (Q4)
5. `test_rephrasings_bullet_prefix_stripped` (Q5/C5)
6. `test_rephrasings_punctuation_shifted_echo_filtered` (Q6/C5)
7. `test_siblings_cleanup_on_incremental_retraction` (Q2/C3)
8. `test_duplicate_slugs_length_diff_3_flagged` (Q10/C6)

All via production symbol imports — no `inspect.getsource`, no `read_text().splitlines()` (cycle-11 L2).

## Status
FINAL — design advances to Step 6 (Context7 verification, likely minimal — only stdlib `re`, `xml.etree`, `json` used).
