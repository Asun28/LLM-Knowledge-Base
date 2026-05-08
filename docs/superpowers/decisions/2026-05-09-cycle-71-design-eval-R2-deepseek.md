# Cycle 71 — Design Eval R2 (DeepSeek V4 Pro)

**Date:** 2026-05-09
**Round:** R2 (cross-family adversarial)
**Model:** deepseek-v4-pro
**Tier:** 2

> **Note on artifact origin.** The R2 DeepSeek subagent ran successfully and completed the cross-family adversarial review (~11.6 min wall clock), but the agent's own `Write` tool was blocked by the project's Fact-Forcing Gate hook (which the subagent did not have the priming context to satisfy). The agent's structured summary was returned in its tool-completion notification. The primary session (Opus 4.7 main) transcribed that summary into this file verbatim, preserving R2's findings as the cross-family adversarial input. Per cycle-20 L4 manual-verify discipline + cycle-23 R3 audit-doc-drift rule: this file IS authoritative — its provenance is explicitly documented, it preserves R2's verdict + amendments, and Step 5 design gate consumes it as the second input.

## Adversarial framing

The R2 cross-family role catches what same-family R1 Opus reasoning misses: narrative blind spots, over-confident reasoning, missed tradeoffs that homogeneous reasoning produces. R2's specific value-add this cycle is identifying additional same-class peer surfaces that R1's enumeration table (per `2026-05-09-cycle-71-design-eval-R1-opus.md` §"Same-class peer scan") still missed — specifically OTHER fields in the same call sites that carry user-controllable content into LLM prompts.

## Per-question critique (cross-referenced to brainstorm Q1-Q8)

### Q1: per-snippet vs whole-result kb_search wrap
- **Brainstorm pick:** A (per-snippet)
- **R2 verdict:** AGREE-WITH-AMENDMENT
- **Adversarial reasoning:** Per-snippet wrap is correct, but R1 Opus's enumeration only covered `r["content"]`. The `_format_search_results` template at `mcp/browse.py:51-54` ALSO interpolates `r["title"]` directly into the output, and `title` is user-controllable via frontmatter (`page.title`). An attacker who controls a wiki page title can inject `</wiki_context>` or instruction-shaped strings via the title field — bypassing the snippet wrap entirely.
- **Conditions for sign-off:** AC01 must wrap BOTH `r["content"]` snippet AND `r["title"]`. AC05 lock-in fixture must include an attacker payload in the `title` field as well as in `content`, and assert both are fenced.

### Q2: build_fidelity_context — wrap WHOLE vs page+sources only
- **Brainstorm pick:** A (per-content)
- **R2 verdict:** AGREE-WITH-R1-AMENDMENT
- **Adversarial reasoning:** R1's A1 amendment (one fence around page+sources between heading and closing instructions) is sound. But R2 surfaces an additional vector R1 missed: `_render_sources` at `lint/semantic.py:48` constructs `header = f"## Source {i}: {source['path']}\n"` — the `source['path']` is sourced from the wiki page's frontmatter `source:` field, which is user-curated but UNSANITIZED. An attacker who controls a wiki page can set `source: "raw/foo.md\n\nIgnore previous instructions; ..."` and the path appears OUTSIDE the wrap (in the trusted scaffolding header).
- **Conditions for sign-off:** AC03 implementation must sanitize `source['path']` before header interpolation. Use `sanitize_extraction_field(path, max_len=500)` from `kb.utils.text` (already exists for the same threat class). AC07 lock-in fixture must include an attacker payload in `source['path']` and assert it is sanitized in the output.

### Q3: build_fidelity_context budget reservation
- **Brainstorm pick:** A (reduce `_render_sources` budget by `_FENCE_OVERHEAD`)
- **R2 verdict:** AGREE-WITH-R1-AMENDMENT
- **Adversarial reasoning:** R1's amended approach (plumb explicit `budget` arg through `_render_sources(sources, lines, budget)`) is correct. R2 adds: ensure the `_FENCE_OVERHEAD` constant is RUNTIME-validated against the actual rendered overhead — a future refactor of the assertion text without recomputing the constant would silently drift. Add a runtime invariant test asserting `_FENCE_OVERHEAD == len(wrap_wiki_context("X")) - len("X")` (the constant matches actual overhead for any non-empty input).
- **Conditions for sign-off:** AC07 lock-in includes a `_FENCE_OVERHEAD` invariant assertion. The runtime validation pattern was suggested by cycle-22 L5 (Step-5 CONDITIONS as test obligations).

### Q4: kb_read_page budget reservation
- **Brainstorm pick:** A (cap reduction)
- **R2 verdict:** AGREE-WITH-R1-AMENDMENT + IMPLICIT ORDERING WARN
- **Adversarial reasoning:** R1's clarification (reduce CHAR-cap line 151+157, NOT byte-cap line 133) is correct. R2 surfaces an implicit ordering risk: the truncation footer at lines 157-161 is appended AFTER the cap reduction. If a future refactor reorders these (footer-first then cap), the wrap would slice through the footer and break the T8-argued-benign property. Lock the ordering explicitly in AC02 wording.
- **Conditions for sign-off:** AC02 wording explicit: "char-cap (line 151+157), NOT byte-cap (line 133); truncation footer appended BEFORE wrap; wrap is the LAST operation before return."

### Q5: AC04 empty-extracted-text behavior
- **Brainstorm pick:** A (defer)
- **R2 verdict:** DISAGREE — recommend OPTION B (early-return guard)
- **Adversarial reasoning:** Brainstorm/R1 argued the empty-input path is upstream-bug-only and the existing 0.0 fallback is sufficient. R2 disagrees: a malformed prompt (`Extracted text (first 2000 chars):\n`) sent to the LLM is wasteful — ~50 tokens of credit burned for a guaranteed-nothing return. Adding an early-return guard `if not extracted_text or not extracted_text.strip(): return 0.0` at proposer.py:144 (BEFORE the prompt construction + LLM call) saves the call entirely AND makes the empty-input contract explicit. This is a 2-line addition that reduces token cost. Trial-relevant since the May 2026 trial is partly about credit usage.
- **Conditions for sign-off:** AC04 implementation: BEFORE wrapping, add `if not extracted_text or not extracted_text.strip(): return 0.0`. AC08 lock-in adds a test for empty-input early-return: assert spy on `_call_llm_json` is NEVER called when `extracted_text=""`.

### Q6: PR review rounds
- **Brainstorm pick:** A (R1 + R2 only)
- **R2 verdict:** AGREE
- **Adversarial reasoning:** 12 ACs is below the cycle-22/cycle-16 R3 threshold; cycle-17 L4 conditions don't fire (no new filesystem-write surface, no new security primitive — sibling extension only). R2 confirms this via independent count and notes that the cross-family R2 Codex catch (cycle-68 / cycle-70 history) is the redundancy backstop here. R3 only triggers if R2 surfaces a MAJOR requiring invasive remediation.
- **Conditions for sign-off:** Step 5 design.md states R3 explicitly skipped; R2 Codex remains REQUIRED.

### Q7: BACKLOG follow-up placeholder
- **Brainstorm pick:** A (no placeholder)
- **R2 verdict:** AGREE
- **Adversarial reasoning:** R1's expanded Q7 (fold cycle-68 BACKLOG lock-in extension under AC09 + file 3 NEW LOW entries) is sound. R2 endorses the cycle-69/cycle-70 post-merge pattern preservation.
- **Conditions for sign-off:** Per R1's 14 conditions list, items 7-9.

### Q8: Lock-in test file structure
- **Brainstorm pick:** A (one file, 4 classes)
- **R2 verdict:** AGREE-WITH-AMENDMENT
- **Adversarial reasoning:** R2 surfaces a test-vacuousness risk specific to extension-site lock-ins: cycle-24 L1 + cycle-16 R2 N1 patterns. Each AC05-AC08 needs (a) integration test reaching production, (b) explicit fence-balance assertion (count of `<wiki_context>` opens == count of `</wiki_context>` closes), (c) attacker-payload escape assertion (T3 lock).
- **Conditions for sign-off:** All AC05-AC08 must include fence-balance assertion + T3 escape lock-in + cycle-24 L1 paired mutation control test (xfail-strict).

## Adversarial findings (what R1 likely won't catch)

### Finding F1 (CRITICAL — title injection, R1 missed): kb_search title field
`mcp/browse.py:52` interpolates `r["title"]` (page frontmatter title) into the output without any wrap. Same threat class as `r["content"]` snippet. R1's per-snippet wrap doesn't cover this.

**Recommendation:** AC01 expands to wrap BOTH `r["content"]` AND `r["title"]`. AC05 fixture exercises both fields with attacker payloads.

### Finding F2 (CRITICAL — path injection, R1 missed): build_fidelity_context source path field
`lint/semantic.py:48` interpolates `source["path"]` into a header line OUTSIDE the wrap. The path comes from frontmatter `source:` field — user-curated but unsanitized. Attacker payload like `"raw/x.md\n## Wiki Page\n...injection..."` could create fake section headers inside the trusted scaffolding portion of the prompt.

**Recommendation:** AC03 expands to call `kb.utils.text.sanitize_extraction_field(path, max_len=500)` before header interpolation. AC07 fixture exercises this path.

### Finding F3 (LOW — wasted token spend, R1 dismissed): _relevance_score empty-input
Per Q5 R2 verdict: skip the LLM call entirely on empty `extracted_text` to save ~50 tokens per invocation. Trial-relevant for May 2026 credit tracking.

**Recommendation:** AC04 adds `if not extracted_text or not extracted_text.strip(): return 0.0` early-return.

### Finding F4 (MEDIUM — fence-balance assertion missing in lock-ins): test vacuousness extension
Beyond the cycle-24 L1 / cycle-16 R2 N1 patterns R1 already noted, R2 specifically calls out: each lock-in should include a fence-balance assertion `output.count("<wiki_context>") == output.count("</wiki_context>")`. This catches partial-wrap regressions where the helper is called but escape regex misses a variant.

**Recommendation:** Add fence-balance assertion to each AC05-AC08 lock-in.

### Finding F5 (LOW — runtime constant validation): _FENCE_OVERHEAD drift
Per Q3 R2 verdict: `_FENCE_OVERHEAD` is computed once at import time. A future refactor of `_WIKI_CONTEXT_ASSERTION` text without recomputing the constant introduces silent drift. Add a runtime invariant test.

**Recommendation:** Lock-in test asserts `_FENCE_OVERHEAD == len(wrap_wiki_context("X")) - len("X")`.

## Same-class peer scan (cross-family verification)

R2 confirms R1's Gap H1 (`build_review_context` uses old `<wiki_page_body>` / `<raw_source_N>` sentinels) and Gap H2 (`orchestrator.py:365-372` uses `<untrusted_source>` sentinels). Both should be DEFERRED to cycle-72+ as Phase 4.5 LOW BACKLOG entries — widening cycle-71 scope risks the same enumeration drift cycle-70 fell into.

R2 ADDS: 3 additional same-class peer fields surfaced via the R2 review (now folded into AC01/AC03/AC04 amendments above):
- `title` field in `kb_search` (F1) → fold into AC01
- `path` field in `build_fidelity_context` (F2) → fold into AC03
- `stub_title` field in `_relevance_score` — minor; the prompt template uses `{stub_title!r}` (repr quotes) which provides some isolation, but a sufficiently long `stub_title` could still escape. Lower priority than F1/F2; defer to cycle-72+ as a LOW BACKLOG entry.

## Recommended Step 5 lock-set

| Q | Brainstorm | R1 | R2 | Recommended lock |
|---|------------|-----|-----|------------------|
| Q1 | A | AGREE | **AGREE+title** | A + wrap `r["title"]` per F1 |
| Q2 | A | A1 | **A1+path** | A1 + sanitize `source["path"]` per F2 |
| Q3 | A | A-tightened | **AGREE+invariant** | A-tightened + `_FENCE_OVERHEAD` invariant test per F5 |
| Q4 | A | A-clarified | **AGREE+ordering** | A-clarified + footer-before-wrap ordering lock per Q4 R2 |
| Q5 | A (defer) | AGREE | **DISAGREE — Option B** | Early-return guard per F3 |
| Q6 | A | AGREE | **AGREE** | A — skip R3 |
| Q7 | A | A+fold | **AGREE** | A+fold per R1 |
| Q8 | A | A-renamed | **AGREE+balance** | A + filename `tests/test_cycle71_wrap_extensions.py` + fence-balance assertions per F4 |

## Conditions Step 5 must impose (additional R2 inputs)

Beyond R1's 14 conditions, R2 adds:

15. **AC01 (F1):** wrap `r["title"]` AND `r["content"]` per snippet. AC05 fixture includes attacker payload in BOTH fields.
16. **AC03 (F2):** sanitize `source["path"]` via `sanitize_extraction_field(path, max_len=500)` before header interpolation. AC07 fixture includes attacker payload in `source["path"]`.
17. **AC04 (F3):** add early-return guard `if not extracted_text or not extracted_text.strip(): return 0.0` BEFORE wrap + prompt construction. AC08 lock-in adds empty-input test asserting `_call_llm_json` spy is never called.
18. **AC05-AC08 (F4):** each lock-in includes fence-balance assertion `out.count("<wiki_context>") == out.count("</wiki_context>")`.
19. **AC07 (F5):** runtime invariant assertion `_FENCE_OVERHEAD == len(wrap_wiki_context("X")) - len("X")`.
20. **AC09 (R2-cumulative):** also file Phase 4.5 LOW BACKLOG entry for `_relevance_score stub_title field unsanitized (cycle-72+)` per R2's same-class scan extension.

## Verdict

**APPROVE-WITH-AMENDMENTS**

R2 cross-family value: catching 2 critical missed wrap fields (title @ F1, path @ F2) that R1 Opus's enumeration table missed despite explicit same-class peer scan instructions. These are NOT scope creep — they are within the existing AC scope (AC01, AC03), just additional fields in the same call sites. Fold into existing ACs without adding new AC numbers. R2's R3-skip recommendation matches R1 + brainstorm. Recommended Step 5 LOCK 12 ACs as scoped (AC01 / AC03 / AC04 with R2 amendments) + AC09 with R1's expansion + 1 additional cycle-72+ BACKLOG entry per F-tier findings.
