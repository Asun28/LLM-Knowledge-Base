# Cycle 72 — Design Decision (Step 05)

**Date:** 2026-05-09
**Pipeline step:** 05 — Design decision gate
**Owner:** Opus 4.7 subagent (decision binding)
**Inputs:** requirements.md, brainstorm.md, threat-model.md, design-eval-R1-opus.md, design-eval-R2-deepseek.md
**Reviewer divergence:** R1 APPROVE-WITH-CONDITIONS (14) vs R2 BLOCK (5 findings) — reconciled below.

---

## Analysis

**Walk through every R1 condition (C1–C14) and R2 finding (F-1..F-5) with disposition.**

### R1 conditions

- **C1 — AC01 single-site only (cap at L115, NOT L428).** **MERGE.** This is the keystone scope-fence. Threat-model §T1 line 39 explicitly defers `build_completeness_context` ("Cycle-72 deliberately scopes to fidelity per BACKLOG anchor; completeness OOS for cycle-73+"). The brainstorm's "two-call-site discipline" wording is a foot-gun (cycle-9 L1 dual-mechanism is satisfied by truncation logic + marker emission within `build_fidelity_context`, not by touching two functions). Reconciled with R2 F-1 below in the **DIVERGENCE** section.

- **C2 — Truncation marker literal `"\n…[truncated for context budget]"`.** **MERGE.** Lock-in test AC06 expects this exact string per brainstorm L157. Position-not-presence rule (cycle-24 L1) applies — the marker must `endswith` the truncated content.

- **C3 — AC02 + AC02a atomic (single commit C2).** **MERGE.** Threat-model §T3 InformationDisclosure threat materializes if AC02 ships without AC02a (reviewer LLM looks for tag names that no longer exist in assembly). Cycle-9 L1 dual-mechanism applies — atomic commit prevents the gap. AC02 + AC02a are both inside `review/context.py`; single-file atomic commit is mechanical.

- **C4 — Checklist text references `<wiki_context>` token; AC07 lock-in asserts checklist+assembly use the SAME token.** **MERGE.** Direct atomic-coupling test. Cycle-22 L5 (conditions are coverage) — this becomes a Step-7 sub-AC.

- **C5 — AC04 constant resolution: pick (a) modify `kb.config:467` `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096 - _FENCE_OVERHEAD` or (b) add a NEW `MAX_CONSISTENCY_PAGE_CONTENT_CHARS_WRAPPED` constant.** **MERGE with refinement.** R1 prefers (a) but flags circular-import risk. **Reconciled choice:** OPTION (a) modify in place. `_FENCE_OVERHEAD` is defined in `kb.utils.text`; import direction is `config → utils.text`. Verify no cycle via Step-7 grep — `text.py` does not import `kb.config`, so this is safe. Step-7 plan encodes (a) explicitly and Step-8 plan-gate verifies.

- **C6 — AC04 per-page wrap shape (Approach A: per-page wrap, per-page assertion repetition).** **MERGE.** R1 picks this over one-outer-wrap because consistency-lint task asks the LLM to compare ACROSS pages — per-page boundary signal is load-bearing. Threat-model §T5 confirms.

- **C7 — Test AC09 asserts N `<wiki_context>` open tags for an N-page group.** **MERGE.** Divergent-fail per cycle-15 L1 (pre-cycle-72 has zero, post-cycle-72 has N=4 for a 4-page fixture).

- **C8 — AC06 lock-in uses position assertion (truncation marker is the LAST chars of the capped page region).** **MERGE.** Cycle-24 L1 position-not-presence rule.

- **C9 — AC07 asserts (a) `<wiki_context>` count == 2 (b) `<wiki_page_body>`/`<raw_source_1>` literals NOT present (c) checklist text references `<wiki_context>`.** **MERGE.** This is the atomic-coupling lock-in.

- **C10 — AC08 monkeypatch via call-site module's `wrap_wiki_context` binding (cycle-71 R2 monkeypatch-imported-binding pattern).** **MERGE.** Cycle-71 L1+L2 lesson — without the monkeypatch-imported-binding form the mutation control is unimplementable in CI.

- **C11 — AC09 fixed N=4 fixture, each page 50,000 chars, assert per-page length post-cap.** **MERGE.** Concrete fixture mandated.

- **C12 — AC10 stub_title fixture combines `## ATTACKER` + `---` fence-line + > 2000 chars.** **MERGE.** Exercises all three sanitize_extraction_field defenses (header-strip, frontmatter-strip, length-cap).

- **C13 — ALL FIVE mutation controls (AC11–AC15) use monkeypatch-imported-binding to identity + xfail(strict=True).** **MERGE.** Critical cycle-71 R2 lesson — without this the mutation controls are vacuous.

- **C14 — AC17 BACKLOG.md gains THREE deferred entries (T7 prompt_version, T8 tier-boundary, completeness peer) in the SAME commit that deletes the 5 resolved entries.** **MERGE.** Cycle-23 R1 BLOCKER (deferred-promise discoverability) — Step-11 grep depends on the literal token `deferred — file BACKLOG entry post-cycle-72`.

### R2 findings

- **F-1 [HIGH] — Asymmetric capping: include `build_completeness_context` in AC01.** **DIVERGENCE — REJECT R2 / KEEP R1 C1.** See full rationale below.

- **F-2 [HIGH] — Non-atomic test design for review context + checklist pipeline.** **MERGE (already covered by C4 + C9).** R1 C4 mandates checklist+assembly use the SAME token; C9 asserts `<wiki_context>` count + literal-NOT-present + checklist-references-`<wiki_context>`. This is the same regression-proofing R2 demands. **SUPERSEDE** — no separate action; AC07 lock-in is the atomic-pipeline test R2 wants.

- **F-3 [MEDIUM] — Fence-tag semantic inconsistency across 3 sentinel schemes.** **SUPERSEDE.** R1 same-class peer scan (R1 line 83) explicitly enumerated all `<wiki_*>`/`<raw_*>`/`<untrusted_*>` literals: AC02 unifies `<wiki_page_body>`/`<raw_source_N>` → `<wiki_context>`; AC03 unifies `<untrusted_source>` → `<wiki_context>`. Post-cycle-72 there are ZERO non-`<wiki_context>` sentinels in scope. R2's concern is RESOLVED BY DESIGN — the cycle-72 migration IS the unification. `<source_document>` (extractors.py) is correctly out-of-scope per threat-model §Cross-cutting (separate ingest fence family with its own escape defense).

- **F-4 [MEDIUM] — Monkeypatch fragility from attribute-form imports.** **MERGE (already covered by C10 + C13).** R1 explicitly mandates monkeypatch-imported-binding form. F-4's recommendation to verify all 5 production call sites use direct-import is a Step-7 plan-gate task — encode as a Step-8 grep verify-step (`grep -nE 'from kb.utils.text import|from kb.utils import text' src/kb/lint/semantic.py src/kb/review/context.py src/kb/lint/augment/orchestrator.py src/kb/lint/augment/proposer.py` should show `from kb.utils.text import wrap_wiki_context, sanitize_extraction_field` direct form, NOT `from kb.utils import text`). **MERGE as additional Step-7 sub-AC** under C13.

- **F-5 [LOW] — `_FENCE_OVERHEAD` constant test is a definition-tautology.** **MERGE as REFINEMENT.** R2's point is valid: a test asserting `_FENCE_OVERHEAD == len(_WIKI_CONTEXT_ASSERTION) + len("<wiki_context>") + len("</wiki_context>") + N_newlines` is tautological (computed from the same source). The cycle-72 plan does NOT explicitly add such a test, but R2's recommendation to "independently render `wrap_wiki_context('test_string')` and MEASURE actual overhead at runtime" is sound for AC06 lock-in. **Encode as additional Step-7 sub-AC for AC06**: the lock-in MUST measure `len(wrap_wiki_context("x")) - len("x")` at runtime to confirm `_FENCE_OVERHEAD` matches the actual fence size, not just the constant's definition. Cost: ≈ +3 LoC in AC06 lock-in.

### DIVERGENCE — F-1 vs C1: EXPAND completeness or DEFER?

**Position selected: DEFER. Adopt R1 C1; reject R2 F-1.**

**Rationale (5 considerations, cycle-22 L5 weight):**

1. **Threat-model authority.** Threat-model §T1 line 39 explicitly defers `build_completeness_context` with documented rationale: "Cycle-72 deliberately scopes to fidelity per BACKLOG anchor; completeness OOS for cycle-73+ (also no `wrap_wiki_context` migration — different theme)." The threat-model is the binding STRIDE document for cycle-72; reviewers cannot expand scope past its boundary without invalidating Step-02. R2 did not consult §T1 line 39 (its analysis treats both functions as drop-in symmetric, missing the load-bearing nuance below).

2. **Asymmetric expansion cost — bigger than R2 thinks.** R2 frames F-1 as +50 LoC parallel cap. **R1 line 100 reveals the real cost:** `build_completeness_context` at L428 has NO cycle-71 `wrap_wiki_context` (cycle-71 AC03 wrap is at L115 in `build_fidelity_context` only). To make a "completeness cap" semantically meaningful, the migration would need BOTH (a) cap `paired["page_content"]` (R2's ask) AND (b) add `wrap_wiki_context` fence around the assembled context (analog of cycle-71 AC03). Without (b), the cap reduces injection-impact-magnitude but the injection vector is fully open (page injected into an unfenced prompt). Real cost: +100 LoC + new lock-in test + new mutation-control test + threat-model re-eval. NOT in scope for cycle-72.

3. **Cycle-71 AC03 precedent.** Cycle-71 hardened `build_fidelity_context` (single function); the `_render_sources` `budget=` plumb landed there. Cycle-72 closes the residual gap (page-content cap) in the same single function. Cycle-73+ extends to `build_completeness_context` (NEW wrap + NEW cap, paired). This single-function-per-cycle pattern is the cycle-71 L1+L2 lesson made operative — it bounds blast radius and lets each cycle have a clean grep verification footprint.

4. **Scope-creep ceiling.** Cycle-72 already at 17 ACs + 14 R1 conditions + 5 R2 findings. Per cycle-23+ design discipline (cycle-22 L5 — conditions are coverage, but each new sub-AC is also test-debt + grep-debt). Adopting F-1 would push to 18 ACs + 15+ conditions + 1 new test class + 1 new mutation-control + completeness-specific threat re-eval. The marginal injection-defense gain (a residual same-class peer that REQUIRES new wrap migration to be coherent) is not worth the scope-creep cost when the BACKLOG entry is the structurally correct vehicle.

5. **User intent: "drain BACKLOG".** The BACKLOG.md entry filed under C14 (`build_completeness_context` cap+wrap deferred — file BACKLOG entry post-cycle-72) IS the BACKLOG drain mechanism — it queues the work for cycle-73+ where it gets a proper threat model, brainstorm, and design-eval pair. Filing the deferred entry in cycle-72 (as C14 mandates) IS draining BACKLOG (the cycle-72+ tag is replaced with a cycle-73+ tag with explicit scope). User intent is preserved.

**Counter-argument considered (and rejected):** R2 says "any content-injection bypass discovered in fidelity checks will likely work in completeness checks unless BOTH are capped". TRUE in principle, but the `build_completeness_context` site has NO `wrap_wiki_context` at all — cycle-72 adopting F-1 without also adding the wrap leaves a half-defended site (cap without fence is structurally weaker than fence without cap, because the injection vector is the unwrapped LLM prompt). Doing F-1 properly = doing the full cycle-71 AC03 + cycle-72 AC01 pair = a full cycle's work. Defer-and-do-properly beats expand-and-do-half.

### Cycle-lessons rules audit

- **cycle-7 L2 (same-class peer in design doc).** R1 line 83 enumerates the FULL peer set; R2 F-3 surfaces the same peers from a different angle. SATISFIED — peers are documented in BOTH eval docs.
- **cycle-9 L1 (dual-mechanism collapse).** R1 C3 enforces atomic AC02+AC02a; R1 C5 enforces constant-resolution single-source. SATISFIED.
- **cycle-22 L5 (conditions are coverage).** All 14 R1 conditions become Step-7 sub-ACs; 4 R2 findings merge as Step-7 sub-ACs (1 of 5, F-1, rejected). SATISFIED.
- **cycle-23 R1 (deferred-promise discoverability).** C14 mandates the literal token `deferred — file BACKLOG entry post-cycle-72`. SATISFIED.
- **cycle-24 L1 (position-not-presence).** C8, C9, C11 enforce position assertions where relevant. SATISFIED.
- **cycle-71 L1+L2 (monkeypatch-imported-binding).** C10, C13, F-4-MERGE enforce direct-import + monkeypatch-imported-binding pattern. SATISFIED.

---

## Reconciled binding conditions

The Step-7 mimocoding implementation plan MUST encode these as numbered sub-ACs. Each condition has (text / verify-step / AC anchor).

1. **AC01 single-site only.** Cap is at `src/kb/lint/semantic.py:115` (inside `build_fidelity_context`). DO NOT modify L428 (`build_completeness_context`). **Verify (Step-14):** `grep -nE '_cap_page_content|QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD' src/kb/lint/semantic.py` shows hits ONLY in `build_fidelity_context` region (L100-L120 area), ZERO hits in L420-L440 area. **AC anchor:** AC01.

2. **AC01 truncation marker literal.** Marker text MUST be exactly `"\n…[truncated for context budget]"`. **Verify:** `grep -n "truncated for context budget" src/kb/lint/semantic.py` returns ≥1 hit; AC06 lock-in test asserts `endswith` this marker. **AC anchor:** AC01 + AC06.

3. **AC02 + AC02a atomic commit.** Single commit covers `src/kb/review/context.py` lines 195+207 (assembly migration) AND lines 151+153 (checklist text update). **Verify:** Step-7 commit C2 contains both regions in one diff; Step-8 plan-gate confirms. **AC anchor:** AC02 + AC02a.

4. **AC02a checklist tag-name token match.** Checklist text MUST reference `<wiki_context>` (replacement of `<wiki_page_body>` / `<raw_source_N>`). **Verify:** `grep -nE '<wiki_page_body>|<raw_source_' src/kb/review/context.py` returns ZERO hits post-cycle-72; `grep -n '<wiki_context>' src/kb/review/context.py` returns ≥1 hit in checklist function. **AC anchor:** AC02a + AC07.

5. **AC04 constant resolution — modify in place.** Modify `src/kb/config.py` `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096 - _FENCE_OVERHEAD` (option a). DO NOT add a parallel constant. **Verify:** `grep -n 'MAX_CONSISTENCY_PAGE_CONTENT_CHARS' src/kb/config.py` shows definition uses `_FENCE_OVERHEAD`; `grep -n 'from kb.utils.text import' src/kb/config.py` shows direct import (or PEP 562 lazy if circular). Step-8 plan-gate verifies no circular-import (`text.py` does not import `kb.config`, so direction is config→text — safe). **AC anchor:** AC04.

6. **AC04 per-page wrap shape (Approach A).** Per-page `wrap_wiki_context` call inside the interleave loop, with per-page assertion repetition. NOT one-outer-wrap. **Verify:** AC09 lock-in asserts N `<wiki_context>` open tags for an N-page group. **AC anchor:** AC04 + AC09.

7. **AC06 truncation marker position assertion.** Lock-in MUST use `endswith` (not just `in`) for the truncation marker. **Verify:** `grep -n 'endswith.*truncated' tests/test_cycle72_wrap_extensions.py` returns ≥1 hit. **AC anchor:** AC06.

8. **AC06 fence-overhead runtime measurement (R2 F-5 MERGE).** Lock-in MUST also assert that `len(wrap_wiki_context("x")) - len("x")` at runtime equals `_FENCE_OVERHEAD`. Decouples test from constant's definition. **Verify:** `grep -n 'wrap_wiki_context.*len.*FENCE_OVERHEAD\|len.*wrap_wiki_context' tests/test_cycle72_wrap_extensions.py` returns ≥1 hit. **AC anchor:** AC06.

9. **AC07 atomic-coupling pipeline test (R2 F-2 MERGE).** Lock-in asserts (a) `<wiki_context>` count == 2 (b) `<wiki_page_body>` AND `<raw_source_1>` literals NOT in output (c) `build_review_checklist(...)` text references `<wiki_context>` token. **Verify:** AC07 test contains all three assertions. **AC anchor:** AC07.

10. **AC09 fixed N=4 fixture, 50,000 chars/page.** Lock-in builds a group of 4 pages, each 50,000 chars; asserts each post-cap page length ≤ `MAX_CONSISTENCY_PAGE_CONTENT_CHARS`; asserts exactly 4 `<wiki_context>` open tags. **Verify:** test fixture explicit + assertion explicit. **AC anchor:** AC09.

11. **AC10 stub_title combined-attack fixture.** Lock-in payload combines (i) `## ATTACKER` (level-2 markdown header) (ii) `---` (frontmatter fence) (iii) > 2000 chars. Asserts (a) `## ATTACKER` literal NOT in built prompt (b) `---` fence-line NOT in built prompt (c) post-sanitize length ≤ 2000. **Verify:** test fixture explicit. **AC anchor:** AC10.

12. **AC11–AC15 monkeypatch-imported-binding pattern.** All 5 mutation-control tests MUST use `monkeypatch.setattr("kb.<module>.<helper>", lambda x: x)` (or equivalent identity) on the IMPORTED BINDING in the call-site module's namespace, not the source module. Mark with `@pytest.mark.xfail(strict=True, reason="cycle-72 AC<N> divergence pin — passing means revert")`. **Verify:** `grep -nE 'monkeypatch.setattr.*wrap_wiki_context|monkeypatch.setattr.*sanitize_extraction_field|monkeypatch.setattr.*_cap_page_content' tests/test_cycle72_wrap_extensions.py` returns ≥5 hits (one per mutation control). **AC anchor:** AC11 + AC12 + AC13 + AC14 + AC15.

13. **Direct-import verification (R2 F-4 MERGE).** All 5 production call-site modules MUST use direct-import form (`from kb.utils.text import wrap_wiki_context, sanitize_extraction_field`), NOT attribute-form (`from kb.utils import text; text.wrap_wiki_context(...)`). **Verify:** `grep -nE 'from kb.utils.text import|from kb.utils import text' src/kb/lint/semantic.py src/kb/review/context.py src/kb/lint/augment/orchestrator.py src/kb/lint/augment/proposer.py` shows direct-import form on every line. **AC anchor:** AC02 + AC03 + AC04 + AC05 (verify-step before Step-9 implementation).

14. **AC17 BACKLOG additions: 3 deferred entries.** AC17 commit DELETES the 5 cycle-72+ resolved entries AND ADDS 3 deferred entries (T7 prompt_version, T8 tier-boundary, completeness peer). All 3 entries contain the literal token `deferred — file BACKLOG entry post-cycle-72` for Step-11 discoverability. **Verify:** `grep -n 'deferred — file BACKLOG entry post-cycle-72' BACKLOG.md` returns ≥3 hits. **AC anchor:** AC17.

**Total binding conditions: 14** (matches R1 count exactly; R2 F-2 MERGE folds into condition 9, F-3 SUPERSEDE-by-design, F-4 MERGE folds into condition 13, F-5 MERGE folds into condition 8, F-1 REJECTED.)

---

## Final AC list

ACs unchanged from requirements.md (AC01 single-site; F-1 expansion REJECTED). NO sub-AC split — AC01 stays atomic.

- **AC01:** `build_fidelity_context` `paired["page_content"]` cap at `semantic.py:115` ONLY [single-site only — `build_completeness_context` at L428 OUT OF SCOPE per threat-model §T1; deferred to cycle-73+ via AC17 BACKLOG entry]
- **AC02:** `build_review_context` migration from `<wiki_page_body>` / `<raw_source_N>` XML sentinels to `wrap_wiki_context` (single outer fence, Approach A)
- **AC02a:** `build_review_checklist` atomic checklist text update referencing `<wiki_context>` token (paired with AC02 in single commit)
- **AC03:** `lint/augment/orchestrator.py:368` pre-extract migration from `<untrusted_source>` to `wrap_wiki_context`
- **AC04:** `build_consistency_context` per-page `wrap_wiki_context` (Approach A) + `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` reservation by `_FENCE_OVERHEAD` (modify-in-place per condition 5)
- **AC05:** `_relevance_score` `stub_title` sanitize via `sanitize_extraction_field` (Approach B; `!r` repr-quote retained as defense-in-depth)
- **AC06:** Lock-in test `TestAC01PageContentCap` (truncation marker position-assert + fence-overhead runtime measurement)
- **AC07:** Lock-in test `TestAC02ReviewContextMigration` (atomic-coupling pipeline: assembly + checklist token-match)
- **AC08:** Lock-in test `TestAC03OrchestratorPreExtractMigration`
- **AC09:** Lock-in test `TestAC04ConsistencyContextMigration` (N=4 fixture, 50,000 chars/page)
- **AC10:** Lock-in test `TestAC05RelevanceScoreStubTitle` (combined attack fixture: header + frontmatter + > 2000 chars)
- **AC11:** Mutation-control test `TestAC01MutationControl` xfail-strict (monkeypatch-imported-binding pattern)
- **AC12:** Mutation-control test `TestAC02MutationControl` xfail-strict
- **AC13:** Mutation-control test `TestAC03MutationControl` xfail-strict
- **AC14:** Mutation-control test `TestAC04MutationControl` xfail-strict
- **AC15:** Mutation-control test `TestAC05MutationControl` xfail-strict
- **AC16:** `CLAUDE.md` Quick-Reference update (site count 6 → 11; cycle-72+ deferred-peer list drops to 0; test/file counts; cycle-72 AC list inline)
- **AC17:** `CHANGELOG.md` + `CHANGELOG-history.md` cycle-72 entries; `BACKLOG.md` DELETE 5 cycle-72+ resolved entries AND ADD 3 deferred entries (T7 prompt_version, T8 tier-boundary, completeness peer)

**Final AC count: 17** (unchanged from requirements.md; F-1 expansion rejected; AC01a/AC01b sub-AC split NOT adopted).

---

## Approved deferred BACKLOG entries (cycle-73+)

Three entries added in AC17 commit. All contain the literal token `deferred — file BACKLOG entry post-cycle-72` for cycle-23 R1 BLOCKER discoverability.

### Entry 1 — `build_completeness_context` cap + wrap pair (Phase 4.5 LOW)

```markdown
- **`src/kb/lint/semantic.py:428` — `build_completeness_context` `paired["page_content"]` uncapped + unwrapped** [cycle-73+]
  Same-class peer of cycle-72 AC01 (`build_fidelity_context:115`). Currently has NO `wrap_wiki_context` fence (cycle-71 AC03 wrap was applied to fidelity only) AND no per-page char-cap. Cycle-73+ should ship paired migration: (a) add `wrap_wiki_context` fence around the assembled context (analog of cycle-71 AC03); (b) cap `paired["page_content"]` at `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` before assembly (analog of cycle-72 AC01). Coupling: `_render_sources(...,*,budget=...)` plumb same as cycle-71. Defense gain: closes the same-class injection peer surfaced by cycle-72 R2-F1; cycle-72 deferred — file BACKLOG entry post-cycle-72 per threat-model §T1 §Deferred (single-function-per-cycle pattern, cycle-71 AC03 precedent).
```

### Entry 2 — `kb.lint.verdict_db` `prompt_version` column (Phase 4.5 LOW)

```markdown
- **`kb.lint.verdict_db` schema lacks `prompt_version` column for forensic prompt-shape reconstruction** [cycle-73+]
  Cycle-72 migrates `build_review_context`, `build_consistency_context`, and orchestrator pre-extract from XML sentinels to `wrap_wiki_context` fences. Verdict-DB rows from before/after the migration are indistinguishable — cannot determine whether an old verdict's prompt used the old or new fence shape. Forensic gap. Cycle-73+: add `prompt_version` column to verdict-DB schema; back-fill pre-cycle-72 rows as `null` or `'pre-cycle-72'`. Threat-model T7 Repudiation. Cycle-72 deferred — file BACKLOG entry post-cycle-72 per threat-model §Deferred line 118.
```

### Entry 3 — Tier-boundary enforcement (Phase 4.5 MEDIUM)

```markdown
- **Tier-boundary enforcement: scan-tier `_call_llm_json` outputs that propose orchestrate-tier side effects must be re-gated** [cycle-73+]
  Cycle-72 (and cycles 70-71 prompt-fence family) reduce prompt-injection PROBABILITY but not BLAST RADIUS. A successful injection in any scan-tier site (e.g., `_relevance_score`, orchestrator pre-extract) could in principle emit JSON that downstream callers interpret as authorization to invoke `kb_create_page` / `kb_save_lint_verdict` / cascading refines. Cycle-73+: add an orchestrate-tier verifier call between scan-tier output and any side-effect-producing downstream caller. Defense-in-depth complement to the cycle-7..cycle-72 prompt-fence family. Threat-model T8 EscalationOfPrivilege. Cycle-72 deferred — file BACKLOG entry post-cycle-72 per threat-model §Deferred line 119.
```

---

## Final verdict

```
DESIGN-DECISION: APPROVE-WITH-CONDITIONS (14)
```

The 17 ACs of cycle-72 are APPROVED subject to the 14 binding conditions above. F-1 vs C1 divergence resolved as DEFER (R1 C1 stands; R2 F-1 rejected with documented rationale: §T1 explicit deferral + asymmetric expansion cost (+100 LoC + new wrap migration, not just +50 LoC parallel cap) + cycle-71 single-function-per-cycle precedent + scope-creep ceiling at 17 ACs + BACKLOG entry IS the user-intent drain mechanism). Step-7 mimocoding plan must encode all 14 conditions as Step-7 sub-ACs per cycle-22 L5.
