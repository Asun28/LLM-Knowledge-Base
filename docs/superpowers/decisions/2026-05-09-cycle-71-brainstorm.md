# Cycle 71 — Brainstorm

**Date:** 2026-05-09
**Tier:** 2
**Step:** 03

Open design questions for cycle 71. Each Q lists 2-3 approaches with tradeoffs; Step 5 gate resolves to one binding decision per Q.

Sources:
- `2026-05-09-cycle-71-requirements.md` — locked AC list (12 ACs), risk callouts R1-R5
- `2026-05-09-cycle-71-threat-model.md` — T1-T6 inherited + T7-T14 new; gaps G1-G5 surfaced

Cycle 70 precedent (`2026-05-08-cycle-70-design.md` + `mcp/core.py:417-432`):
- Helper lives in `kb.utils.text` (cycle-71 reuses it; no relocation question)
- `mcp/core.py` synthesis-prompt builder wraps ONLY the combined context, NOT the surrounding query/header (`f"# Query: {q}\n# Wiki Context\n{wrapped}\n# Answer the query..."`).
- `query/engine.py:1054` reserves `_FENCE_OVERHEAD` BEFORE composing the context; wrap is the LAST step.

---

## Q1: kb_search snippets — per-snippet wrap vs whole-result wrap (Gap G4)

**Context (AC01).** `_format_search_results` produces one string with N result blocks: `Found N matching page(s):` header + per-result `- **{id}** ...\n  Title: {title}\n  Snippet: {200-char excerpt}...`. The wiki content is the snippet only.

| Option | Pros | Cons |
|--------|------|------|
| **A: Per-snippet wrap** (recommended; threat-model T7 row, BACKLOG.md:152 explicit suggestion) | Each untrusted blob is isolated; surrounding scaffolding (`Found N`, `- **id**`, `Title:`, `Snippet:`) stays unfenced and visible to LLM as our trusted output; mirrors cycle-70 `mcp/core.py:417-432` (wrap content, not header) | N fence-pairs in one response (~10 max via `MAX_SEARCH_RESULTS=50`, capped lower in practice); ~215 chars/snippet overhead × 10 = ~2 KB transport overhead |
| B: Whole-result wrap | One fence-pair total; smaller overhead | Mixes trusted scaffolding (`Found N matching page(s)`, ID/title labels) with untrusted snippets inside one fence; LLM treats the entire response as "data, not instructions" including our own labels — confused boundary |
| C: No wrap (BACKLOG accepted "low risk per AC11 design (200 chars)") | Zero overhead | Defeats cycle-71's purpose; BACKLOG entry would have to be re-filed; threat-model T1 unmitigated for kb_search |

**Recommendation:** **A.** Matches BACKLOG.md fix prescription verbatim ("wrap each `r["content"]` snippet via `wrap_wiki_context`"), preserves cycle-70 boundary discipline (wrap content only, not scaffolding), and the per-snippet overhead is well within transport budget (~2 KB worst case).

---

## Q2: build_fidelity_context — wrap WHOLE assembled context vs page+sources only (Gap G1)

**Context (AC03).** `build_fidelity_context` returns a 6-section string: `# Source Fidelity Check: {id}` heading + evaluation framing + `## Wiki Page` body + `## Source N: {path}` blocks (rendered by `_render_sources`) + closing "For each factual claim..." instructions. Untrusted = page body + source bodies. Trusted = headings, framing, closing instructions.

| Option | Pros | Cons |
|--------|------|------|
| **A: Wrap ONLY page_content + each source body separately** (recommended per threat-model G1) | Tightest boundary discipline; matches cycle-70 `mcp/core.py:417-432` precedent (header outside, content inside); closing "For each factual claim…" instructions stay OUTSIDE fence and act as the LLM's REAL instruction set | More wrap calls (1 per page + N per source); more lock-in surface for AC07 |
| B: Wrap the WHOLE `"\n".join(lines)` (current AC03 wording) | Simplest implementation: one wrap call; smallest test surface | Headings + closing instructions inside fence; assertion sentence ("data, not instructions") implicitly tells LLM to ignore the closing instructions, which IS the LLM's task framing — semantic confusion |
| C: Wrap page_content as one block, then `_render_sources` outputs per-source pre-wrapped sections | Per-source isolation across N untrusted sources | Requires changing `_render_sources` signature/contract; broader blast radius |

**Recommendation:** **A.** Threat-model G1 explicitly recommends this option. Cycle-70 precedent is unambiguous: wrap content only, leave scaffolding/instructions unfenced. AC03 wording will be revised at Step 5 to say "wrap `paired['page_content']` AND each source body individually inside `_render_sources`," not "wrap the whole `"\n".join(lines)`." Locks AC07 lock-in to assert per-source `<wiki_context>` blocks (one per source body + one for page).

---

## Q3: build_fidelity_context budget — `_render_sources` cap reduction vs accept overshoot (Gap G2)

**Context (AC03 + threat-model T12).** `_render_sources` (`semantic.py:36-60`) caps per-source rendering at `QUERY_CONTEXT_MAX_CHARS` with `MIN_SOURCE_CHARS=500` floor. With Q2 Option A, each wrap adds `_FENCE_OVERHEAD ≈ 215` chars per source × N sources, plus 1 for page_content.

| Option | Pros | Cons |
|--------|------|------|
| **A: Reduce `_render_sources` per-source budget by `_FENCE_OVERHEAD`** (recommended per threat-model G2) | Parity with cycle-70 T5 reservation contract (`engine.py:1054`); total assembled context stays ≤ `QUERY_CONTEXT_MAX_CHARS`; testable via numeric assertion in AC07 lock-in | Requires touching `_render_sources`'s `remaining = max(_MIN_SOURCE_CHARS, QUERY_CONTEXT_MAX_CHARS - used - len(header) - 20)` arithmetic |
| B: Accept ~215-char overshoot per source | Smallest diff; `_render_sources` unchanged | Departs from cycle-70 reservation contract; overshoot scales with N sources (N=4 → 860-char overshoot); silent budget creep |
| C: Wrap WHOLE `"\n".join(lines)` and reduce `_render_sources` total budget by single `_FENCE_OVERHEAD` | One reservation point | Conflicts with Q2 Option A (the Q2 question chose per-content wrap, which means N reservations not 1) |

**Recommendation:** **A.** Companion lock to Q2 Option A. The arithmetic change is small: `remaining = max(_MIN_SOURCE_CHARS, QUERY_CONTEXT_MAX_CHARS - used - len(header) - 20 - _FENCE_OVERHEAD)`. AC07 lock-in adds a `len(returned_text) <= QUERY_CONTEXT_MAX_CHARS` assertion to prevent regression.

---

## Q4: kb_read_page budget arithmetic — cap reduction vs alternative (Gap embedded in R2)

**Context (AC02 + threat-model T11).** `kb_read_page` reads up to `cap_bytes = QUERY_CONTEXT_MAX_CHARS * 4 + 4096` bytes (UTF-8 multi-byte slack), decodes, then char-caps to `QUERY_CONTEXT_MAX_CHARS` at line 151. Wrap-after-cap means total response = cap + `_FENCE_OVERHEAD` > documented budget.

| Option | Pros | Cons |
|--------|------|------|
| **A: Reduce char-cap to `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` BEFORE wrap** (recommended per AC02 wording) | Total response ≤ `QUERY_CONTEXT_MAX_CHARS`; mirrors cycle-70 T5 reservation contract | Slightly smaller user-visible page body (~215 fewer chars before truncation kicks in) |
| B: Wrap then cap-after | Fence stays at full size | Cap may slice through fence tags or assertion sentence — broken output |
| C: Accept overshoot, document in CLAUDE.md | Smallest diff | Departs from documented budget; downstream MCP transport could fail silently |

**Recommendation:** **A.** AC02 already specifies this; lock at Step 5. AC06 lock-in includes the `len(response) <= QUERY_CONTEXT_MAX_CHARS` assertion (R4 in requirements doc) so regression is impossible.

---

## Q5: AC04 empty-extracted-text behavior (Gap G3)

**Context (AC04 + threat-model T4 site 4).** `_relevance_score(extracted_text="")` would call `wrap_wiki_context("")` which returns `""`. The prompt becomes `Extracted text (first 2000 chars):\n` (no fence, no data). LLM probably returns near-zero score; `_relevance_score`'s try/except (line 144-148) returns 0.0 on any exception or invalid float.

| Option | Pros | Cons |
|--------|------|------|
| **A: Defer / no change** (recommended per threat-model G3) | Existing 0.0 fallback handles degenerate case; caller's contract (`extracted_text` is the body of a fetched URL, never empty in practice) makes empty input an upstream bug not a security gap | Empty-input case produces a malformed-looking prompt (not a fence + content; just an empty `Extracted text:` label). Cosmetic only. |
| B: Skip the LLM call + return 0.0 directly on empty | Cleaner; saves a token spend | New branch + new test surface; not on the cycle's theme (prompt-safety, not error-handling) |
| C: Helper variant `wrap_wiki_context_strict(text)` that raises on empty | Surfaces upstream bug | Wider blast radius; helper API change touches cycle-70 callers; out of scope |

**Recommendation:** **A.** Defer per threat-model G3. The empty-input path is unreachable in the documented caller contract (URL bodies are never empty when reaching `_relevance_score`). Existing 0.0 fallback is sufficient. Document in Step 5 design doc; do NOT add a new AC.

---

## Q6: PR review rounds (Gap G5)

**Context.** Cycle has 12 ACs (4 wrap + 4 lock-in + 1 hygiene + 3 doc). `feedback_3_round_pr_review` memory: R3 fires at ≥25 ACs OR at ≥15 ACs with specific conditions (cycle-17 L4: NEW filesystem-write surface, defensive check w/ hard-to-reach input, NEW security enforcement point, ≥10 design-gate-resolved questions). Cycle-16 lesson: the 25-AC threshold is a heuristic, not a ceiling.

| Option | Pros | Cons |
|--------|------|------|
| **A: R1 (DeepSeek + Sonnet) + R2 (Codex + Sonnet); skip R3** (recommended per threat-model G5) | 12 ACs is well below 25; cycle-17 L4 conditions don't fire (no NEW security primitive — just sibling-surface extension of existing one); minimizes subagent pauses per `feedback_minimize_subagent_pauses` memory | Risk that R3 catches something both R1+R2 miss — but R2 Codex is the cross-vendor static-analysis backstop (`feedback_r2_codex_static_analysis_value` memory) |
| B: Run all three rounds | Maximum coverage; consistent with cycles 14-16 cadence | Adds ~10 min subagent pause; cycle-71 has no novel attack surface to justify the spend |
| C: R1 only (skip R2 too) | Fastest | Loses cross-vendor R2 Codex value; cycle-68 R2 caught 4 MAJORs that R2 Sonnet missed (memory) — DO NOT skip R2 |

**Recommendation:** **A.** Step 20 runs R1 (DeepSeek + Sonnet) → fix → R2 (Codex + Sonnet) → fix → merge. R3 is reserved for ≥25-AC cycles or the cycle-17 L4 condition set, neither of which fires here.

---

## Q7: AC09 BACKLOG hygiene scope — what to add as cycle-71 follow-up placeholder?

**Context (AC09 + threat-model T14).** AC09 deletes 4 Phase 4.5 LOW entries (the 4 wrap surfaces) and adds a NEW Phase 4.5 LOW entry as a cycle-71 R2/R1 review carry-over placeholder. What goes in the placeholder?

| Option | Pros | Cons |
|--------|------|------|
| **A: No placeholder; populate post-merge if R2 surfaces non-blocking findings** (recommended) | Keeps BACKLOG clean unless real follow-up surfaces; mirrors cycle-69 / cycle-70 pattern | None |
| B: Pre-fill with "potential carry-over: R2 may flag fence-position concerns at non-cycle-71 surfaces" | Documents known scope edge; reviewer can verify | Speculative; risks vacuous BACKLOG entries |
| C: Add a NEW LOW entry for the BACKLOG-re-introduction lock (T14) — extend `tests/test_cycle68_backlog_cleanup_lockin.py` with cycle-71 deletions | Defends against future stale-context drift | Already implicitly covered by AC09 deletion; the lock-in test would itself be a separate AC if added |

**Recommendation:** **A.** No placeholder pre-merge; if Step 20 R2 surfaces NIT-level findings the post-merge step (cycle-69 / cycle-70 precedent) files them. Keeps cycle-71 scope tight at 12 ACs. Re: T14 — confirm at Step 5 whether `tests/test_cycle68_backlog_cleanup_lockin.py` exists; if it does, add cycle-71 deletion strings via a 1-line extension fold under AC09 (no new AC). If it doesn't, document in Step 24 self-review and file as cycle-72 carry-over.

---

## Q8: Lock-in test file structure (extends R5 in requirements)

**Context.** AC05-AC08 lock-ins reach 4 different production sites across 3 modules. New file: `tests/test_cycle71_prompt_safety.py`.

| Option | Pros | Cons |
|--------|------|------|
| **A: One test class per AC, 4 classes in 1 file** (recommended) | Clear AC ↔ class mapping; co-located helper fixtures; matches `tests/test_cycle70_prompt_safety.py` pattern (cycle-70 created same-named file) | Larger single file (~300 LoC) |
| B: 4 separate test files (1 per AC) | Smaller files; per-test isolation | Loses fixture reuse; freeze-and-fold cadence treats each test file as a unit; 4 files harder to fold later |
| C: Functional grouping (1 class per module: browse / semantic / proposer) | Module-aligned | Mismatch with AC numbering; harder for Step 14 grep to verify "AC05 lock-in covers AC01" |

**Recommendation:** **A.** One file `tests/test_cycle71_prompt_safety.py` with 4 test classes (`TestAC01_KbSearchSnippetWrap`, `TestAC02_KbReadPageBodyWrap`, `TestAC03_FidelityContextWrap`, `TestAC04_RelevanceScoreWrap`). Co-locate a `_make_attacker_payload(prefix, suffix)` helper at module level returning `f"{prefix}</wiki_context>{suffix}"` for the T3 attacker-substring fixture. Each class has 2-3 tests: positive (fence appears + assertion text), negative-control (`</wiki_context>` rewritten), budget assertion (where applicable per Q3/Q4).

⚠ **Cycle-70 file-name collision check:** verify `tests/test_cycle70_prompt_safety.py` exists; if cycle-71's filename collides, rename to `tests/test_cycle71_wrap_extensions.py`. Step 5 confirms via grep.

---

## Open question cluster (closed at Step 5)

The 8 questions above are the full Step 3 open set. Step 5 design gate Opus subagent will:
- READ this brainstorm + threat model + requirements
- LOCK each question to one option
- EMIT a `## CONDITIONS` section per cycle-22 L5 (each condition becomes a sub-AC test obligation in Step 7 plan)
- VERIFY each AC's named function exists in current source per cycle-8 L1 + cycle-3 L1 ("BACKLOG.md is open" red flag) — already done at Step 1, but Step 5 re-confirms
- VERIFY same-class peer scan per cycle-7 L3 + cycle-11 L3 (any other MCP tool that returns wiki page bodies? — `kb_list_pages`, `kb_list_sources`, `kb_stats` etc. — confirm explicitly in/out of scope)

## Approval

Step 3 self-approved by primary session (Opus 4.7 main). Per `feedback_auto_approve` user memory, no human gate; Step 5 Opus subagent is the binding-decision gate. Proceeding to Step 4 (design eval R1 Opus + R2 DeepSeek, parallel).
