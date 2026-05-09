# Cycle 73 — Requirements + Acceptance Criteria

**Date:** 2026-05-09
**Branch:** `feat/cycle-73` (off `origin/main` @ `1802bd4`)
**Pipeline:** dev-mimo-opus (May 2026 trial — fourteenth)
**Predecessor:** cycle 72 (`ad262d0`) shipped `wrap_wiki_context` residual surface (17 ACs); 3 LOW deferred entries filed for cycle-73+.

---

## Tier classification

**Tier 2 — standard feature** (per `dev-mimo-opus` SKILL.md Tier classifier).

**Why not Tier 3:**
- AC02 adds a NEW frontmatter-style key (`prompt_version`) to verdict-store entries (JSON list) — *additive*, not destructive. Reversible (drop key on rollback). The SQLite-migration framing in BACKLOG was inaccurate; `kb.lint.verdicts.add_verdict` writes `json.dump`, not SQL.
- AC03 adds a defense-in-depth verifier on an EXISTING internal scan→orchestrate boundary (`kb.lint.augment.orchestrator._validate_tier_boundary` → fail-closed schema re-gate). No auth, IAM, crypto, secrets, or PII data-class boundary touched. The existing `_call_llm_json(tier="scan", schema=...)` already does first-pass validation; AC03 adds a *second*, stricter pass before the orchestrate-tier write.
- AC01 extends the cycle-71/72 `wrap_wiki_context` defense surface to a sibling site (`build_completeness_context`) — same threat class as cycle-72 AC01, judged Tier 2 there.

**Why not Tier 1:**
- AC02 (verdict-store schema add) is observable to downstream consumers (`get_page_verdicts`, `kb_verdict_trends`) — back-compat read path matters.
- AC03 is security-defense — Tier 1 explicitly excludes "trust boundary" changes.

**Pipeline subset:** full pipeline (1–24).

**Mandatory human gates:** none (per user `feedback_auto_approve` standing instruction — Opus subagent gates substitute).

**Step subset rationale (Tier 2 skip-when, applied row-by-row at execution time):**
- Step 06 — likely SKIP if pure-stdlib + internal-module diff and Step 4 absorbs Context7 pre-check.
- Step 16 — sub-step skips per artifact (no `*.tf`, no `Dockerfile`, dep-manifest unchanged → all 3 sub-steps skip).
- Step 19 — likely SKIP (repo doesn't require signing AND no published artifact).
- Step 22 — SKIP (no deployable artifact).
- Step 23 — SKIP (Step 22 was skipped).

---

## Problem

Three cycle-72-deferred LOW BACKLOG entries plus residual Phase-4.5 hygiene need a single bundled cycle to drain:

1. **`build_completeness_context` cap+wrap is missing** — `lint/semantic.py:466` reads `paired['page_content']` directly into the assembled prompt with NO `wrap_wiki_context` fence and NO `_cap_page_content`. This is the direct same-class peer of cycle-72 AC01 (`build_fidelity_context`). The cycle-72 design-decision DEFERRED this per threat-model §T1 OOS scoping; cycle-73 closes it.

2. **Verdict store has no prompt-shape version stamp** — `lint/verdicts.py::add_verdict` records issues with timestamp / page_id / verdict_type / verdict / issues / notes — but NOT which prompt-shape produced the LLM verdict. Forensic gap surfaced by cycle-72 threat-model §T7 Repudiation. Investigators cannot tell whether a 2026-04 verdict was produced under cycle-1 H14 literal-sentinel (`<wiki_page_body>` / `<raw_source_N>` / `<untrusted_source>`) prompts or under cycle-70+ `<wiki_context>` fenced prompts.

3. **No tier-boundary verifier** — scan-tier `_call_llm_json(tier="scan", schema=…)` outputs flow into orchestrate-tier callers via `proposer_mod._call_llm_json` at `orchestrator.py:394`. The first-pass schema validation accepts the LLM response shape; orchestrate-tier consumers then propose `kb_create_page` / `kb_save_lint_verdict`-class side effects with NO independent re-gating. Cycle-72 §T8 EscalationOfPrivilege — cycle-72 reduced *probability* of injection via `wrap_wiki_context` but did NOT bound the *blast radius*. Cycle-73 adds the radius bound.

4. **BACKLOG entries drift from current source** — Phase 4.5 MEDIUM lists "`kb.query.hybrid` `KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested)" but CLAUDE.md Quick Reference confirms cycle 67 AC06 already shipped this. Stale entry pollutes the open-work signal.

5. **Snapshot test foundation underutilised** — cycle 64 AC8 shipped 3 snapshot subjects (evidence-trail / Mermaid export / lint-report-structure) and BACKLOG lists 6 deferred subjects. Adding 2 incremental subjects this cycle lifts the regression-fence on rendering paths without requiring a dedicated cycle.

## Non-goals (out of scope)

- **NOT** migrating `lint/verdicts.py` to SQLite. The BACKLOG entry's "schema column" framing was inaccurate; current store is `atomic_json_write` of a `list[dict]`. AC02 adds a JSON key + read-side default; SQLite migration would be a separate cycle with its own threat model.
- **NOT** rewriting the scan→orchestrate flow. AC03 adds a *verification helper* called from existing call sites; it does NOT restructure the orchestrator's three-gate state machine.
- **NOT** auditing pre-cycle-70 verdicts and back-filling actual prompt shapes. AC02's read-side default is `prompt_version=0` (= "pre-cycle-70 unknown"); historical prompt-shape archaeology is a separate exercise.
- **NOT** adding new wiki-context fence sites OTHER than `build_completeness_context` (AC01). Other deferred peers stay deferred.
- **NOT** implementing `compile/linker.py` cross-reference auto-linking (Phase 4.5 MEDIUM). Substantive feature; separate cycle.

## Acceptance criteria (6 ACs)

Each is independently grep-testable and pass/fail.

### AC01 — `build_completeness_context` cap + wrap_wiki_context fence

**File:** `src/kb/lint/semantic.py:466` (`build_completeness_context`).

**Change:**
1. Cap `paired['page_content']` via `_cap_page_content(paired['page_content'], QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD)` BEFORE assembly.
2. Split assembled lines into header (outside fence) + body (inside fence) + closing (outside fence) — same shape as cycle-71 AC03 + cycle-72 AC01 in `build_fidelity_context`.
3. Wrap the assembled body in `wrap_wiki_context(...)` exactly once.
4. Pass `budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` to `_render_sources`.

**Pass test:** `tests/test_cycle73_completeness_wrap.py::test_completeness_context_includes_single_fence` — assembled output contains exactly one `<wiki_context>` open and one close, page+sources nested between them, with assertion-sentence + `</wiki_context>` close present.

**Mutation control (xfail-strict):** if either `_cap_page_content` OR `wrap_wiki_context` is identity-monkeypatched, the lock-in test FAILS (proves both invariants are load-bearing).

### AC02 — Verdict-store prompt-shape version stamp

**Files:**
- `src/kb/config.py` — add `CURRENT_PROMPT_VERSION = 1` constant (1 = post-cycle-70 `<wiki_context>` fence shape).
- `src/kb/lint/verdicts.py::add_verdict` — write `"prompt_version": CURRENT_PROMPT_VERSION` into each new entry.
- `src/kb/lint/verdicts.py::load_verdicts` — read-side back-fill: missing key returns default `0` via `get_prompt_version(entry: dict) -> int` helper. Do NOT mutate cached entries.

**Change:** Strictly additive. Read-side back-compat with pre-cycle-73 entries (no key → returns 0). Cache invalidation unchanged.

**Pass tests:**
1. `test_add_verdict_stamps_current_prompt_version` — fresh entry has `prompt_version == CURRENT_PROMPT_VERSION`.
2. `test_load_verdicts_legacy_entry_default_zero` — entry without the key reports `get_prompt_version(entry) == 0`.
3. `test_get_prompt_version_handles_non_dict_inputs` — type-safety: returns `0` on `None`/`list`/`str` defensively.

**Mutation control (xfail-strict):** if `CURRENT_PROMPT_VERSION` is monkeypatched to `0`, fresh-entry test FAILS (proves stamp is non-zero); if `get_prompt_version` is identity-replaced with `lambda e: 999`, legacy-entry default test FAILS (proves default-0 is load-bearing).

### AC03 — Tier-boundary verifier helper

**File:** `src/kb/lint/augment/orchestrator.py`.

**Change:** Add module-level helper `_validate_tier_boundary(scan_output: dict, *, expected_keys: frozenset[str], max_depth: int = 4, max_string_len: int = 4096) -> dict`. Re-gates scan-tier output against orchestrate-tier consumption rules:

1. Reject if not `isinstance(scan_output, dict)`.
2. Reject if any key not in `expected_keys` (rejects extension-by-LLM, e.g., LLM-injected `"side_effects"` key).
3. Reject any string value longer than `max_string_len` (length bound).
4. Reject any nested structure deeper than `max_depth` (defense against pathological JSON-bombs).
5. Reject any value of types other than `str | int | float | bool | None | list | dict` (rejects custom classes if Pydantic is bypassed).

Apply at `orchestrator.py:394` site: wrap the result of `proposer_mod._call_llm_json(_build_pre_extract_prompt(raw_content), tier="scan", schema=schema)` with `_validate_tier_boundary(..., expected_keys=frozenset(schema['properties'].keys()))` before the result reaches the orchestrate-tier persister.

On rejection: raise `ValidationError("tier-boundary verification failed: <reason>")`. The existing `except Exception` block at L399+ converts to a recoverable per-stub failure (matches existing failure-mode contract).

**Pass tests:**
1. `test_validate_tier_boundary_accepts_well_formed` — schema-conforming dict passes through unchanged.
2. `test_validate_tier_boundary_rejects_extra_key` — LLM-injected extra key raises `ValidationError`.
3. `test_validate_tier_boundary_rejects_oversize_string` — 5000-char value raises.
4. `test_validate_tier_boundary_rejects_deep_nesting` — 6-level-deep dict raises.
5. `test_orchestrator_pre_extract_calls_validator` — orchestrator integration test confirms the helper is called between `_call_llm_json` and the persister, via spy.

**Mutation control (xfail-strict):** if `_validate_tier_boundary` is monkeypatched to identity (`lambda d, **kw: d`), test #2 (extra-key rejection) FAILS (proves the call site is load-bearing).

### AC04 — Tier-boundary verifier wired with FAIL-CLOSED on persister side

**File:** `src/kb/lint/augment/orchestrator.py`.

**Change:** The `except Exception as e:` block catching `proposer_mod._call_llm_json` failures (L399+) MUST NOT swallow `ValidationError` raised by AC03 — it should record the gap to the manifest with explicit `outcome="tier_boundary_rejected"` rather than the generic `"llm_scan_failed"`. Caller can distinguish forensically.

**Pass test:** `test_orchestrator_records_tier_rejection_distinctly` — when AC03 raises, manifest entry shows the distinct outcome string.

**Mutation control (xfail-strict):** if the outcome string is monkeypatched to `"llm_scan_failed"`, the distinctness assertion FAILS.

### AC05 — Two new syrupy snapshot subjects

**Files:**
- `tests/test_cycle73_snapshots.py` — new file.
- `tests/__snapshots__/test_cycle73_snapshots.ambr` — generated.

**Change:** Add two snapshot subjects from BACKLOG Phase 4.5 MEDIUM `tests/ snapshot tests` deferred list:
1. `_render_sources` source-list rendering — exercises path sanitization + budget-aware truncation + multi-source layout.
2. `_build_summary_content` summary-page rendering — exercises evidence-trail + frontmatter assembly + sources block.

**Pass test:** `pytest tests/test_cycle73_snapshots.py` passes against committed `.ambr`. Subsequent `pytest --snapshot-update` runs leave the snapshot byte-identical (deterministic).

**Mutation control:** None needed — snapshot-based regression IS the lock-in.

### AC06 — BACKLOG hygiene: remove stale `KB_DISABLE_VECTORS` Phase 4.5 entry

**File:** `BACKLOG.md` lines ~88-89.

**Change:** Delete the stale entry "`kb.query.hybrid` `KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested) — …". CLAUDE.md Quick Reference §"Auto-rebuild + auto-publish" already documents this as cycle 67 AC06: "`KB_DISABLE_VECTORS=1` runtime kill-switch for hybrid search vector branch (BM25-only fallback)". Add a one-line entry to CHANGELOG.md `[Unreleased]` Quick Reference noting the BACKLOG cleanup.

**Pass test:** `tests/test_cycle73_backlog_hygiene.py::test_kb_disable_vectors_entry_absent` — `BACKLOG.md` does NOT contain the literal string `"KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested)"`.

**Mutation control:** None — doc-only, behaviour-tested via grep.

## Blast radius

Files modified (likely):
- `src/kb/config.py` — add `CURRENT_PROMPT_VERSION` constant.
- `src/kb/lint/semantic.py` — `build_completeness_context` cap + wrap (AC01).
- `src/kb/lint/verdicts.py` — write-side stamp + read-side helper (AC02).
- `src/kb/lint/augment/orchestrator.py` — `_validate_tier_boundary` + call site + outcome string (AC03 + AC04).
- `BACKLOG.md` — delete stale entry (AC06).
- `CHANGELOG.md` + `CHANGELOG-history.md` — cycle-73 entry.
- `CLAUDE.md` — bump test count + Quick Reference cycle-73 line.
- `docs/reference/*.md` — implementation-status + architecture/error-handling deltas if touched.

New test files:
- `tests/test_cycle73_completeness_wrap.py` — AC01 lock-in + xfail mutation control.
- `tests/test_cycle73_prompt_version.py` — AC02 lock-in + xfail.
- `tests/test_cycle73_tier_boundary.py` — AC03+AC04 lock-in + xfail.
- `tests/test_cycle73_snapshots.py` + `tests/__snapshots__/test_cycle73_snapshots.ambr` — AC05 snapshots.
- `tests/test_cycle73_backlog_hygiene.py` — AC06 staleness assertion.

Estimated diff: ~250 LoC `src/` + ~350 LoC `tests/`. ~10 new test classes plus 4 xfail-strict mutation controls.

## Open questions for Step 4 design eval

1. **Q1 — `prompt_version` mutability semantics.** Should `load_verdicts` mutate cached entries to include the back-filled `prompt_version=0` key, or keep the key absent and use `get_prompt_version(entry)` accessor? *Lean: accessor (no cache mutation; preserves on-disk fidelity).*

2. **Q2 — `_validate_tier_boundary` schema-derivation strategy.** Should the helper accept `expected_keys` explicitly, or derive from the same `schema` object passed to `_call_llm_json` (single source of truth)? *Lean: accept both; primary param is `expected_keys` with optional `schema=` shortcut.*

3. **Q3 — `max_depth` and `max_string_len` defaults.** Are 4 and 4096 the right floors? Higher might miss attacks; lower might reject legitimate long descriptions. *Lean: 4 / 4096 mirrors `MAX_ISSUE_DESCRIPTION_LEN` and existing prompt depth.*

4. **Q4 — Snapshot subjects: `_render_sources` vs `_build_summary_content`.** Both selected from BACKLOG; should we pick OTHER pairs (e.g., `kb publish --format graph` JSON-LD + contradictions append)? *Lean: stick with `_render_sources` + `_build_summary_content` — these have the most direct call sites in cycle-73 diff so any regression is caught immediately.*

5. **Q5 — `prompt_version` value: `1` for post-cycle-70 fence shape, OR `2` since cycle-71 AC03 introduced new wrap sites?** *Lean: `1` — represents "post-cycle-70 wrap_wiki_context family", treating the cycle-71/72/73 expansions as the same family.*

6. **Q6 — Cycle-72 L8 cap-math reservation: `_cap_page_content` already reserves `len(_CAP_TRUNCATION_MARKER)`. Does AC01's same-marker-reuse approach satisfy the cycle-72 L8 invariant in `build_completeness_context` too?** *Lean: yes — same `_cap_page_content` helper reused; cycle-72 R2 Codex M-1 fix already inside the helper.*

7. **Q7 — AC04 outcome-string distinctness — should it be a NEW outcome enum or a sub-key on existing `outcome="llm_scan_failed"`?** *Lean: NEW enum value `"tier_boundary_rejected"` for forensic distinctness; same audit-row schema otherwise.*

---

**Cycle-72 lessons applied (per Step-24 self-review):**
- L1 (circular-import surface) — AC02 places `CURRENT_PROMPT_VERSION` in `kb.config` (no new import edge); AC03 module-level helper in `orchestrator.py` (no new edge).
- L3 (mimocoding-rescue Bash/Read/Grep/Glob only — no Edit/Write) — Step 9 implementation will be primary-session; mimocoding-rescue advises only.
- L4 (sandbox blocks subagent Write) — Step 20 R1/R2 will pre-create review-file shells primary-session-side.
- L7 (count assertions for multi-page fixtures) — AC02 multi-entry fixture asserts COUNT and per-key presence.
- L8 (cap-math marker reservation) — AC01 reuses cycle-72 `_cap_page_content` which already reserves marker length.
