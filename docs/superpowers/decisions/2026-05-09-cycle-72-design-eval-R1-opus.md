# Cycle 72 — Design eval R1 (Opus 4.7)

**Date:** 2026-05-09
**Pipeline step:** 04 — Design eval R1
**Reviewer:** Opus 4.7 subagent
**Inputs read:** requirements.md, brainstorm.md, threat-model.md (all present), 5 in-scope source files at HEAD, `kb.utils.text`, `tests/test_cycle71_wrap_extensions.py`, `BACKLOG.md` Phase 4.5 LOW.

---

## Analysis

**Scope of grep verification.** Re-ran the Step-1 grep checkpoints against current HEAD (`f42109e` post-cycle-71 merge). All 5 anchors present at the line numbers cited in requirements + brainstorm + threat-model. No drift.

- **AC01 — `build_fidelity_context` page-content cap.** Line numbers confirmed: `paired["page_content"]` at `src/kb/lint/semantic.py:115` (inside `build_fidelity_context`, post cycle-71 wrap) and `:428` (inside `build_completeness_context`, NO wrap). Brainstorm Approach A (inline `_cap_page_content` helper called at L115 + L428) MATCHES the threat model T1 mitigation. **Same-class peer concern surfaced:** `:428` is in `build_completeness_context` — a DIFFERENT function. The brainstorm's plan to call the helper at *both* L115 and L428 would silently pull `build_completeness_context` into AC01 scope. Threat model §T1 Out-of-scope explicitly defers `build_completeness_context` ("Cycle-72 deliberately scopes to fidelity per BACKLOG anchor; completeness OOS for cycle-73+"). **DUAL-MECHANISM HAZARD (cycle-9 L1):** the brainstorm pros bullet says "two-call-site discipline (cycle-9 L1 dual-mechanism is satisfied because both call sites are updated atomically)" — but the threat model says NOT to touch `:428`. Reconcile: AC01 caps ONLY at L115 (inside `build_fidelity_context`) where cycle-71 AC03 fence was added. L428 is `build_completeness_context` — file BACKLOG entry per threat model §Deferred line 120. Brainstorm wording is a foot-gun.

- **AC02 + AC02a — `build_review_context` migration + atomic checklist.** Line numbers confirmed: `<wiki_page_body>` literal at L195, `<raw_source_{i}>` f-string at L207, `</raw_source_{i}>` close at L209, checklist text at L151/L153. Brainstorm Approach A (single outer fence with markdown sub-headers) matches the cycle-70 `query/engine.py:1063` precedent — consistency wins per threat-model §Cross-cutting. Threat-model §T2 + §T3 confirm forgeability + atomicity rationale. **DUAL-MECHANISM CHECK (cycle-9 L1):** AC02 + AC02a is a TWO-PART atomic coupling — assembly migration + checklist text update. The brainstorm correctly identifies this; the plan-structure section commits both to the SAME commit (C2). Pre-condition for Step-7: must commit atomically, not as separate commits.

- **AC03 — orchestrator pre-extract.** Line confirmed: `<untrusted_source>` literal at `lint/augment/orchestrator.py:368` inside an f-string (`f"<untrusted_source>\n{raw_content}\n</untrusted_source>"`). Brainstorm Approach A (drop-in replacement with `wrap_wiki_context(raw_content)`) is trivially correct and matches threat-model §T4 mitigation. Sibling of cycle-71 AC04 (`_relevance_score` `extracted_text` wrap). No dual-mechanism hazard — single-site change.

- **AC04 — `build_consistency_context` per-page wrap + reservation.** Function defined at `semantic.py:313`. Per-page assembly loop at L383-L402. Truncation is at L394-L399 against `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` (already imported from `kb.config:467` where it's set to 4096 — the brainstorm's claim "Add at module level next to QUERY_CONTEXT_MAX_CHARS" is INCORRECT; the constant ALREADY EXISTS in `kb.config`). The brainstorm Approach A computes a NEW per-page cap via `(QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD) // 4`; this would be a SECOND constant or a redefinition that diverges from the existing 4096 value. **DRIFT HAZARD:** the existing 4096 should either be (a) MODIFIED in `kb.config` to subtract `_FENCE_OVERHEAD` (mechanical, conservative) or (b) left at 4096 with the wrap layered on AND the assembled total post-wrap still bounded by `QUERY_CONTEXT_MAX_CHARS` via outer guard. Threat model §T5 mitigation language is "cap is reduced by `_FENCE_OVERHEAD`" — it points at MODIFYING the existing 4096 rather than introducing a parallel constant. Brainstorm needs to clarify whether `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` mutates in place or a new constant is added. **DUAL-MECHANISM (cycle-9 L1):** wrap site (per-page in loop) AND cap site (constant or in-loop arithmetic) must update together; otherwise per-page wrap with old 4096 cap could push the assembled context over budget for the typical 4-pages-per-group case (4 × (4096 + ~190 fence) ≈ 17,144 chars vs. `QUERY_CONTEXT_MAX_CHARS` headroom).

- **AC05 — `_relevance_score` `stub_title` sanitize.** Line confirmed: `{stub_title!r}` at `proposer.py:155`. Brainstorm Approach B (`sanitize_extraction_field`) chosen. This site is the residual same-class peer of cycle-71 AC04 (which wrapped `extracted_text`). The repr-quote at `!r` STAYS (defense-in-depth). Threat model §T6 confirms: "design gate selects based on data-class lineage" → stub_title is short-field → `sanitize_extraction_field` is right shape. The brainstorm's note that sanitize WILL strip `## ATTACKER` and length-cap at 2000 is structurally correct (verified against `text.py:247-282`).

- **Same-class peer scan beyond requirements.** Ran `grep -rnE '<wiki_(page_body|context)>|<raw_source_|<untrusted_source>' src/kb/`. Found ZERO additional sentinel sites beyond the 5 ACs. Also broadened to `<source_document>` (extractors.py) — that's a SEPARATE class (cycle-3 M9 with its own `_escape_source_document_fences` defense), correctly out-of-scope per threat model §Cross-cutting. `<wiki_context>` references in `query/engine.py:1143-1144` and `semantic.py:52,91` are docstring/comment references, not literal-sentinel emission sites — non-issue.

- **Test pattern alignment with cycle-71 template.** Reviewed `tests/test_cycle71_wrap_extensions.py:1-100`. Pattern is: per-AC class with lock-in test methods (count fence-opens / fence-closes for R2-F4 balance, position assertions for scaffolding outside fence, T3 escape-rewrite check). Mutation-control xfail-strict tests use **monkeypatch of the IMPORTED BINDING in the call-site module's namespace** (`kb.<module>.wrap_wiki_context`) to identity, expecting the lock-in to FAIL. Cycle-72 brainstorm describes mutation-controls only as "assert opposite" without specifying the monkeypatch-binding shape. **GAP:** the brainstorm should explicitly mandate the monkeypatch-imported-binding-to-identity pattern (cycle-71 R2 lesson) so cycle-72 mutation controls don't drift to weaker shapes (e.g., revert-via-edit-and-rerun, which is unimplementable in CI).

---

## Verdict per AC

### Group A — Production code

- **AC01** — `build_fidelity_context` page-content cap → **APPROVE-WITH-CONDITIONS**
  - C1: cap MUST be applied ONLY at `semantic.py:115` (inside `build_fidelity_context`); the L428 site (`build_completeness_context`) is OUT OF SCOPE and MUST be filed as a deferred BACKLOG entry per threat-model §Deferred line 120. The brainstorm's "two-call-site discipline" wording is misleading — the plan structure section MUST clarify that AC01 is a SINGLE-call-site change and the dual-mechanism rationale comes from cap-marker placement (truncation logic + marker emission), not two functions.
  - C2: truncation marker MUST be the literal string `"\n…[truncated for context budget]"` (per AC06 lock-in expectation in brainstorm L157).

- **AC02 + AC02a** — `build_review_context` migration + atomic checklist → **APPROVE-WITH-CONDITIONS**
  - C3: AC02 + AC02a MUST commit atomically (single C2 commit). If AC02 ships and AC02a misses, threat T3 (InformationDisclosure via reviewer mental-model mismatch) materializes between commits.
  - C4: New checklist text MUST reference `<wiki_context>` fence name (replacement for `<wiki_page_body>` / `<raw_source_N>`). AC07 lock-in MUST assert the checklist text and assembly tag names use the SAME token.

- **AC03** — orchestrator pre-extract migration → **APPROVE** (no conditions; trivial drop-in matching cycle-71 AC04 sibling).

- **AC04** — `build_consistency_context` per-page wrap + reservation → **APPROVE-WITH-CONDITIONS**
  - C5: Resolve the constant ambiguity. EITHER (preferred) modify `kb.config:467` `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096` to `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096 - _FENCE_OVERHEAD` (requires importing `_FENCE_OVERHEAD` in config — circular-import check needed) OR add a NEW constant `MAX_CONSISTENCY_PAGE_CONTENT_CHARS_WRAPPED` and use it inside `build_consistency_context`, leaving the unwrapped manual-mode path on the original. Pick ONE and document in C2 (test) so divergent-fail is unambiguous.
  - C6: Per-page wrap shape SELECTED — brainstorm Approach A (per-page wrap with per-page assertion repetition). NOT one-outer-wrap. Rationale: consistency lint asks the LLM to compare ACROSS pages, per-page boundary signal is load-bearing. Threat-model §T5 confirms.
  - C7: Assert N `<wiki_context>` open tags for an N-page group (test AC09 already mandates this).

- **AC05** — `_relevance_score` `stub_title` sanitize → **APPROVE** (Approach B `sanitize_extraction_field` selected; the repr-quote `!r` STAYS as defense-in-depth, do NOT remove it).

### Group B — Lock-in tests (AC06–AC10)

- **AC06** (page_content cap test) → **APPROVE-WITH-CONDITIONS**
  - C8: lock-in MUST use position assertion (truncation marker is the LAST chars of the capped page region, not just present-anywhere). Per cycle-24 L1.

- **AC07** (review_context migration + checklist coupling test) → **APPROVE-WITH-CONDITIONS**
  - C9: assert BOTH (a) `<wiki_context>` count == 2 (single outer fence) (b) `<wiki_page_body>` and `<raw_source_1>` literals NOT present (c) checklist text references `<wiki_context>` (atomic-coupling check).

- **AC08** (orchestrator pre-extract test) → **APPROVE-WITH-CONDITIONS**
  - C10: monkeypatch the call-site module's `wrap_wiki_context` binding to identity in the paired AC13 mutation control (per cycle-71 R2 monkeypatch-imported-binding pattern).

- **AC09** (consistency_context per-page reservation test) → **APPROVE-WITH-CONDITIONS**
  - C11: assert per-page content length AFTER cap is `<= MAX_CONSISTENCY_PAGE_CONTENT_CHARS` (whichever resolution C5 picks). Assert exactly N `<wiki_context>` open tags for an N-page group input. Use a fixed N=4 fixture with each page 50_000 chars.

- **AC10** (relevance_score stub_title test) → **APPROVE-WITH-CONDITIONS**
  - C12: Lock-in MUST send a stub_title containing `## ATTACKER` (level-2 markdown header) AND a frontmatter fence `---` AND > 2000 chars. Assert (a) `## ATTACKER` literal NOT in built prompt (b) `---` fence-line NOT in built prompt (c) title length post-sanitize <= 2000 chars (sanitize_extraction_field default cap).

### Group C — Mutation-control tests (AC11–AC15)

- **AC11–AC15** — paired xfail-strict mutation controls → **APPROVE-WITH-CONDITIONS**
  - C13: ALL FIVE mutation controls MUST use the cycle-71 monkeypatch-imported-binding pattern: monkeypatch `kb.<module>.wrap_wiki_context` (or `kb.lint.semantic._cap_page_content` for AC11; or `kb.lint.augment.proposer.sanitize_extraction_field` for AC15) to identity (`lambda x: x`). Mark `xfail(strict=True, reason="cycle-72 AC<N> divergence pin — passing means revert")`. Test then runs the production path and asserts the OPPOSITE of the lock-in. Brainstorm currently describes "assert opposite" without the monkeypatch shape; without the monkeypatch the mutation control is unimplementable in CI (you can't revert production code per-test).

### Group D — Documentation

- **AC16** (CLAUDE.md) → **APPROVE** (mechanical update; site count 6 → 11, deferred-peer list drops to 0 cycle-72+, but B4.5 LOW retains other items).
- **AC17** (CHANGELOG + history + BACKLOG) → **APPROVE-WITH-CONDITIONS**
  - C14: BACKLOG.md MUST also gain THREE deferred entries per threat-model §Deferred (T7 prompt_version, T8 tier-boundary, `build_completeness_context` page-content cap). Brainstorm AC17 text only mentions deletion of the 5 cycle-72+ entries — it does NOT mention these three additions. Without C14 the threat model's deferred-promise discoverability gate (cycle-23 R1 BLOCKER, threat-model §Deferred end-line "discoverable by Step-11's BACKLOG grep via the literal token `deferred — file BACKLOG entry post-cycle-72`") fails.

---

## Same-class peer scan (CRITICAL — cycle-7 L2)

`grep -rnE '<wiki_(page_body|context)>|<raw_source_|<untrusted_source>' src/kb/` (executed at HEAD `f42109e`):

| File:line | Literal | Classification |
|-----------|---------|----------------|
| `lint/augment/orchestrator.py:368` | `<untrusted_source>` | IN SCOPE (AC03) |
| `lint/semantic.py:52,91` | `<wiki_context>` | OUT OF SCOPE — docstring text, not emission |
| `query/engine.py:1143,1144` | `<wiki_context>` | OUT OF SCOPE — assertion-text comment + checklist string referring to cycle-70 AC11 fence (already shipped, not a literal sentinel emission) |
| `review/context.py:151,153` | `<wiki_page_body>`, `<raw_source_N>` (checklist text) | IN SCOPE (AC02a) |
| `review/context.py:195,207` | `<wiki_page_body>`, `<raw_source_{i}>` (assembly) | IN SCOPE (AC02) |
| `utils/text.py:368,378,383,390` | `<wiki_context>` | OUT OF SCOPE — primitive helper definition |

**Broader class scan** (`<wiki_\|<raw_\|<untrusted_\|<source_`):

- `ingest/extractors.py:29,72,279,296,330` — `<source_document>` cycle-3 M9 sentinel. **OUT OF SCOPE — different threat class.** Has its own `_escape_source_document_fences` defense (extractors.py:72). NOT a `wrap_wiki_context` peer; it's the parallel ingest-prompt fence family. Cycle-72 should NOT touch it. Sibling-but-different-sentinel-family per threat model §Cross-cutting (each fence family is independent).

**Cycle-73+ same-class peer candidates surfaced** (BACKLOG entries per C14):

1. **`build_completeness_context` `paired["page_content"]` uncapped** — `semantic.py:428`. Same shape as AC01 but in a DIFFERENT function. Currently has NO `wrap_wiki_context` (no cycle-71 wrap). Filing as "cycle-73+: apply AC01-shaped cap PLUS add `wrap_wiki_context` fence (analog of cycle-71 AC03)".

2. **T7 prompt_version forensic gap** — verdict-DB schema lacks `prompt_version` column. Filed under Phase 4.5 LOW per threat-model §Deferred.

3. **T8 tier-boundary enforcement** — scan-tier outputs trigger orchestrate-tier side effects. Filed under Phase 4.5 MEDIUM per threat-model §Deferred.

These three are the COMPLETE cycle-73+ candidate set surfaced by R1.

---

## Step-7 plan structure conditions

Binding conditions the Step-7 plan MUST contain (numbered to match Verdict-per-AC):

1. **AC01 single-site only** (C1): cap is at `semantic.py:115` ONLY. NO call at L428. Step-7 task description must explicitly state "do NOT modify L428 (`build_completeness_context`); file BACKLOG entry instead per AC17/C14".
2. **AC02 + AC02a atomic** (C3): single commit C2 covers both. Plan must NOT split into two commits.
3. **AC04 constant resolution** (C5): plan picks ONE of (a) modify `kb.config` `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096 - _FENCE_OVERHEAD` (b) add new `MAX_CONSISTENCY_PAGE_CONTENT_CHARS_WRAPPED` constant. Plan-gate Step 8 MUST verify the choice is documented and used consistently in test AC09.
4. **AC04 per-page wrap shape** (C6): brainstorm Approach A (per-page wrap, per-page assertion repetition). NOT one-outer-wrap.
5. **All mutation controls use monkeypatch-imported-binding** (C13): AC11–AC15 each monkeypatch `kb.<module>.<helper>` to identity in the test, mark `xfail(strict=True)`, and assert the lock-in's OPPOSITE.
6. **AC10/C12 stub_title test fixture explicit** (C12): payload combines `## ATTACKER` + `---` fence-line + > 2000 chars to exercise all three sanitize_extraction_field defenses.
7. **AC17 BACKLOG additions** (C14): three deferred entries (T7, T8, completeness peer) added in the SAME commit that deletes the 5 resolved entries. Step-7 must include this in the AC17 commit description.

These 7 plan-structure conditions correspond to Step-7 sub-ACs per cycle-22 L5.

---

## Final verdict

```
DESIGN-EVAL-R1: APPROVE-WITH-CONDITIONS (14)
```
