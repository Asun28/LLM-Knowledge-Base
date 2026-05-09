# Cycle 73 — Brainstorm: 2-3 approaches per AC

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**Pipeline step:** 03 (brainstorming)
**Inputs:**
- Requirements: `2026-05-09-cycle-73-requirements.md`
- Threat model: `2026-05-09-cycle-73-threat-model.md`

For each of the 6 ACs, list 2-3 viable approaches and tag the recommendation. Step 4 design-eval scores them; Step 5 commits.

---

## AC01 — `build_completeness_context` cap + wrap

### Approach A — exact mirror of cycle-72 AC01 (`build_fidelity_context`)
- Split into header / body / closing triplet; wrap body once.
- Reuse `_cap_page_content` helper as-is.
- Pass `budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` to `_render_sources`.
- Pros: zero new helpers; pattern-uniformity with cycle-72; identical lock-in test shape.
- Cons: copy-paste-near-duplicate of `build_fidelity_context` body — small DRY violation.

### Approach B — extract a `_assemble_wrapped_context(header, page_content, sources, closing, *, budget)` helper
- New helper applied at BOTH `build_fidelity_context` AND `build_completeness_context` (refactor cycle-72 site).
- Pros: single source of truth; future fidelity/completeness/consistency context migrations land in one place.
- Cons: blast radius increases (cycle-72 site refactored alongside); plan-gate sees a Tier-2-style refactor not a Tier-2 feature; cycle-72 R2 Codex M-1 cap-math fix is encoded inside `_cap_page_content` and propagates via the helper — but the indirection makes it harder to spot at review time.

### Approach C — inline the body assembly without a helper (no DRY at all)
- Just copy ~10 lines of cycle-72 code into `build_completeness_context`.
- Pros: lowest blast radius; review surface ≤10 lines.
- Cons: breaks `feedback_simplify` discipline; future reviewer asking "why two near-identical bodies?" gets no answer except "we added them in different cycles".

**Recommendation: Approach A** — direct mirror of cycle-72 AC01. Tier-2 cycle isn't the place for the cycle-72 body refactor; if a 3rd context-builder appears in cycle-74+ then Approach B becomes correct as same-class peer. Cycle-72 lessons L1+L8 already encoded in `_cap_page_content`; reusing the helper inherits both.

---

## AC02 — Verdict-store `prompt_version` stamp

### Approach A — accessor-not-mutation (recommended in requirements.md Lean)
- Write-side: `add_verdict` writes `entry["prompt_version"] = CURRENT_PROMPT_VERSION` into the new dict.
- Read-side: new `get_prompt_version(entry: dict) -> int` returns `entry.get("prompt_version", 0)`. Defensive: returns 0 on `not isinstance(entry, dict)`.
- `load_verdicts` UNCHANGED — does NOT mutate cached entries.
- Pros: on-disk fidelity preserved; cache contents = JSON contents byte-for-byte; no migration code path; back-compat read with pre-cycle-73 entries.
- Cons: every reader must use the accessor (not `entry["prompt_version"]`) — discipline burden on future code.

### Approach B — read-side back-fill (mutating)
- `load_verdicts` post-processes JSON list and inserts `entry["prompt_version"] = 0` for any entry missing the key.
- Pros: callers can use `entry["prompt_version"]` directly; no accessor discipline.
- Cons: changes on-disk-vs-in-memory equivalence (cache != disk); next save would write back the back-filled `0` which CHANGES the on-disk file (write-amplification on every load); breaks the threat-model T7 invariant that cache mirrors disk.

### Approach C — schema-versioned migration on first read
- One-shot migration: on first `load_verdicts` after deploy, walk all entries; for entries missing `prompt_version`, insert `0`; rewrite the file.
- Pros: legacy entries get the key explicitly; future readers see uniform schema.
- Cons: write-on-read is dangerous (corrupted file on partial-write); cycle-19 L2 reload-leak risk; user feedback `feedback_migration_breaks_negatives` lesson — one-shot migrations break legacy `K not in D` tests.

**Recommendation: Approach A** — accessor-not-mutation. Threat-model T7 demands no cache mutation. The "discipline burden" is solved by adding `get_prompt_version` to the public API; existing callers don't read the field today (it's brand new), so the burden materialises only on new code which can adopt the accessor immediately.

---

## AC03 — `_validate_tier_boundary` helper

### Approach A — module-level helper in `orchestrator.py` with explicit `expected_keys` param
- Helper signature: `_validate_tier_boundary(scan_output: dict, *, expected_keys: frozenset[str], max_depth: int = 4, max_string_len: int = 4096) -> dict`.
- Caller derives `expected_keys` from `schema['properties'].keys()` at the call site (NOT from LLM output — defends T5 spoofing).
- Pros: explicit param surface; helper testable in isolation; T5 defense lives at the call site (visible in Step-14 grep).
- Cons: caller must remember to derive from schema not from LLM output (review discipline).

### Approach B — helper accepts `schema` directly, derives keys internally
- Helper signature: `_validate_tier_boundary(scan_output: dict, *, schema: dict, ...) -> dict`. Internally: `expected_keys = frozenset(schema.get("properties", {}))`.
- Pros: single-argument convenience; T5 defense is inside the helper.
- Cons: harder to test (must construct a full schema dict for every test variant); JSONSchema's "properties" key isn't always the right place (e.g., `$ref`-resolved schemas); leaks JSONSchema internals into the helper.

### Approach C — pluggable validator interface with multiple validators
- Build a `class TierBoundaryValidator: def validate(scan_output) -> dict` abstract; ship `KeySetValidator`, `DepthValidator`, `StringLengthValidator` instances; orchestrator instantiates a chain.
- Pros: maximally extensible; each validator independently testable.
- Cons: over-engineering for one call site (cycle-21 `feedback_simplify` discipline); cycle-72 R1 design eval would BLOCK on "5 LoC vs 80 LoC for the same defense".

**Recommendation: Approach A** — explicit `expected_keys` param. The T5 defense being visible at the call site is a feature not a bug — it makes Step-14 verification one grep. Approach C is the simplify-pass-rejecting variant.

### AC03 sub-question — `max_depth` default

- Option (i): `max_depth=4` — covers `dict[dict[dict[str, value]]]` (3-level nesting) plus root, which matches existing prompt depth in proposer/extractor schemas.
- Option (ii): `max_depth=8` — generous; handles future schema additions without code change.
- Option (iii): `max_depth=2` — conservative; might reject legitimate sub-objects.

**Recommendation: option (i) `max_depth=4`** — matches existing schema depth; cycle-74+ can raise if needed.

---

## AC04 — Manifest outcome distinctness

### Approach A — new `outcome="tier_boundary_rejected"` enum value
- Add the string to whatever enum/Literal type exists for outcomes; orchestrator catch-block sets it when the caught exception is `ValidationError` from `_validate_tier_boundary`.
- Pros: forensic-distinct; existing audit-row schema unchanged.
- Cons: needs an exception-type check in the catch block (existing pattern is `except Exception as e:`).

### Approach B — sub-key on existing `"llm_scan_failed"` outcome
- Outcome stays `"llm_scan_failed"`, add `subreason="tier_boundary_rejected"` in payload.
- Pros: outcome enum unchanged.
- Cons: forensically less distinct (greppers must read the sub-key); cycle-23 R1 BLOCKER lesson favors top-level distinctness.

### Approach C — raise distinct exception class `TierBoundaryError`
- Define `class TierBoundaryError(ValidationError)`; catch separately at orchestrator with explicit outcome string.
- Pros: caller can catch precisely; future code can raise without polluting the generic ValidationError surface.
- Cons: new exception class (extra import), but trivial.

**Recommendation: Approach C** — distinct exception class + outcome string. The exception-class distinction makes the catch-block precise (not a string-compare-on-message); outcome-string distinction makes the manifest forensically clean.

---

## AC05 — Snapshot subjects

### Approach A — `_render_sources` + `_build_summary_content` (recommended in requirements)
- Both have direct call sites in cycle-73 diff (`_render_sources` is plumbed via AC01; `_build_summary_content` is in compile/compiler.py, not touched by cycle-73 but is a prime regression candidate).
- Pros: regression-fence on rendering paths; one is new-call-site (regression bait), one is untouched (regression-fence integrity).
- Cons: two small subjects, not a thorough sweep.

### Approach B — `_render_sources` + `_build_summary_content` + `kb publish --format graph` JSON-LD
- Three subjects.
- Pros: more coverage.
- Cons: graph JSON-LD subject likely brittle (datetime/SHA in payload requires custom serializer).

### Approach C — Just `_render_sources` (one subject)
- Pros: minimal scope.
- Cons: misses `_build_summary_content` regression bait — the cycle-73 diff goes near `lint/semantic.py` `_render_sources` which is one logical step from `_build_summary_content`.

**Recommendation: Approach A** — two subjects. Three is more typing for marginal gain.

---

## AC06 — BACKLOG hygiene

### Approach A — delete only the stale `KB_DISABLE_VECTORS` entry
- Per requirements.
- Pros: minimal surgical change; obvious diff.
- Cons: doesn't catch other potentially-stale entries.

### Approach B — full BACKLOG audit pass
- Walk every Phase 4.5 MEDIUM entry; for each cite a current-source grep that confirms NOT-shipped or NOT-stale.
- Pros: comprehensive hygiene.
- Cons: scope creep — at 30+ entries, this is its own cycle.

### Approach C — defer + file as cycle-74+ entry
- Don't touch BACKLOG; file as cycle-74+ deferred audit task.
- Pros: zero scope creep.
- Cons: leaves a known-stale entry visible to cycle-74 planners.

**Recommendation: Approach A** — delete only the explicitly-known-stale entry. Approach B has been done implicitly by cycle 67's BACKLOG cleanup pass; another full sweep this cycle is over-budget.

---

## Summary recommendation table

| AC | Recommended approach | Rationale (1-line) |
|----|---------------------|---------------------|
| AC01 | A — mirror cycle-72 AC01 | Pattern uniformity; reuse `_cap_page_content` cycle-72 L8 fix |
| AC02 | A — accessor-not-mutation | Threat-model T7 demands cache fidelity |
| AC03 | A — explicit `expected_keys` + `max_depth=4` | T5 defense visible at call site; matches schema depth |
| AC04 | C — `TierBoundaryError` + distinct outcome | Precise catch + forensic-distinct manifest |
| AC05 | A — `_render_sources` + `_build_summary_content` | Two subjects; one in diff, one untouched |
| AC06 | A — delete only stale `KB_DISABLE_VECTORS` entry | Minimal surgical change |

Each recommendation is the LOWER blast radius of the alternatives, consistent with skill's "lower blast radius wins" bias.
