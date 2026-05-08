# Cycle 71 — Requirements + Acceptance Criteria

**Date:** 2026-05-09
**Tier:** 2 (standard feature — sibling-surface security hardening; full pipeline 1–24)
**Branch:** `feat/cycle-71` from `origin/main` (post-cycle-70 base @ `cccf7cb`)
**Scope tag:** Prompt-injection boundary completion across all 4 sibling wiki-content surfaces deferred from cycle-70 AC11 (Phase 4.5 LOW, cycle-71+ tagged).

## Tier rationale

Extension of the cycle-70 AC11 `wrap_wiki_context()` helper (already shipped at `src/kb/utils/text.py:355-379`) to 4 sibling surfaces that surface untrusted wiki content into LLM prompts but were scoped out of cycle 70:

1. `src/kb/mcp/browse.py:_format_search_results` — `kb_search` 200-char snippets
2. `src/kb/mcp/browse.py:kb_read_page` — full page body up to `QUERY_CONTEXT_MAX_CHARS`
3. `src/kb/lint/semantic.py:build_fidelity_context` — paired wiki-page + raw-source context for fidelity checks
4. `src/kb/lint/augment/proposer.py:_relevance_score` — `extracted_text[:2000]` injected into scan-tier LLM

No new helper, no new attack surface — all 4 sites consume the existing `kb.utils.text.wrap_wiki_context`. Same security pattern, same threat class as cycle 70 (T3 fence-escape, T4 empty input, T5 budget overhead).

**No** auth / crypto / IAM / migration / deploy-pipeline change → **Tier 2** (full pipeline, Opus-subagent gates, no mandatory human gate, auto-merge after Step 21). Per the dev-mimo-opus skill Tier classifier: prompt-injection extension on already-validated data flows is a sibling-surface security hardening, not a new IAM/data-class boundary.

## Acceptance criteria

### Bucket A — wrap_wiki_context extensions (4 ACs)

Each AC adds the existing `kb.utils.text.wrap_wiki_context()` call at one site, preserving existing length caps and the `_FENCE_OVERHEAD` budget contract per cycle-70 T5.

- **AC01** — Wrap `kb_search` snippets in `_format_search_results` at `src/kb/mcp/browse.py:31-56`. Apply per-snippet wrap on `r["content"][:200].replace("\n", " ").strip()` so each result's snippet section is independently fenced. The 200-char cap stays; the fence adds the documented `_FENCE_OVERHEAD` (~150 chars) per snippet. Surrounding scaffolding text (`Found N matching page(s)`, `- **id**`, `Title:`, `Snippet:`) stays unfenced — those are controlled output, not wiki content. **DELETE** Phase 4.5 LOW BACKLOG entry `mcp/browse.py:31-56 _format_search_results snippets prompt-injection wrap (cycle-71+)`.

- **AC02** — Wrap `kb_read_page` body return at `src/kb/mcp/browse.py:147-162`. Apply the wrap to the final `body` string (after the `QUERY_CONTEXT_MAX_CHARS` cap and the truncation footer). Reduce the cap to `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` BEFORE the wrap so total response stays ≤ `QUERY_CONTEXT_MAX_CHARS`. **DELETE** Phase 4.5 LOW BACKLOG entry `mcp/browse.py:147-162 kb_read_page body return prompt-injection wrap (cycle-71+)`.

- **AC03** — Wrap `build_fidelity_context` returned context at `src/kb/lint/semantic.py:76-95`. Apply the wrap to the joined `lines` string before return (after `_render_sources` populates the in-place buffer). The pre-existing `QUERY_CONTEXT_MAX_CHARS` budget in `_render_sources` reserves headroom; reduce `MIN_SOURCE_CHARS` floor calculation to factor `_FENCE_OVERHEAD` so the assembled lines + fence still respect the cap. **DELETE** Phase 4.5 LOW BACKLOG entry `lint/semantic.py:76-95 build_fidelity_context prompt-injection wrap (cycle-71+)`.

- **AC04** — Wrap `_relevance_score` extracted-text injection at `src/kb/lint/augment/proposer.py:136-148`. Wrap the `extracted_text[:2000]` substring BEFORE prompt construction (string interpolation moves to the wrapped variable). The 2000-char ceiling stays; the fence adds `_FENCE_OVERHEAD` to total prompt length, well within scan-tier limits. **DELETE** Phase 4.5 LOW BACKLOG entry `lint/augment/proposer.py:142 _relevance_score prompt-injection wrap (cycle-71+)`.

### Bucket B — Lock-in tests (4 ACs)

Each lock-in test follows cycle 24 L1 + cycle 16 R2 N1 + cycle 22 L5 discipline:
- Reaches the production call site (no signature-only / source-grep / inspect.getsource — see Red Flags table)
- Asserts the fence + assertion text is PRESENT in the rendered output
- Includes a paired negative-control: when the AC's wrap call is replaced with `lambda x: x`, the test FAILS
- Test file: `tests/test_cycle71_prompt_safety.py` (one new file, all 4 lock-ins co-located)

- **AC05** — Lock-in for AC01 (`_format_search_results`). Stub `kb.query.engine.search_pages` with a deterministic fixture returning 2 results whose content carries an attacker-planted `</wiki_context>` substring. Invoke `_format_search_results(stub_results)` and assert: (a) output contains exactly 2 occurrences of `<wiki_context>` and 2 of `</wiki_context>` (one per result), (b) each attacker substring is rewritten to `</wiki-context>`, (c) the assertion sentence appears at least once. Mutation budget: removing `wrap_wiki_context` from line ~47 fails ≥1 assertion.

- **AC06** — Lock-in for AC02 (`kb_read_page`). Build a fixture wiki page whose body contains `</wiki_context>` and exceeds `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD`. Call `kb_read_page("entities/test")` and assert: (a) response contains the fence + assertion, (b) attacker substring rewritten, (c) total response length ≤ `QUERY_CONTEXT_MAX_CHARS`, (d) the cycle-3 truncation footer is preserved INSIDE the fence (it's part of `body`). Mutation budget: removing the wrap fails ≥1 assertion.

- **AC07** — Lock-in for AC03 (`build_fidelity_context`). Patch `pair_page_with_sources` to return a fixed dict with `page_content` + 1 source whose `content` carries `</wiki_context>`. Call `build_fidelity_context("entities/test")` and assert: (a) returned string contains the fence + assertion, (b) attacker substring rewritten, (c) the original `## Wiki Page` / `## Source 1:` / closing instructions remain INSIDE the fence (since the wrap is applied to the whole returned context). Mutation budget: removing the wrap fails ≥1 assertion.

- **AC08** — Lock-in for AC04 (`_relevance_score`). Patch `_call_llm_json` with a spy that captures the `prompt` argument; invoke `_relevance_score(stub_title="X", extracted_text="A" * 100 + "</wiki_context>" + "B" * 100)`. Assert: (a) the captured prompt contains the fence + assertion, (b) attacker substring rewritten in the prompt, (c) returned float matches the spy's stubbed score. Mutation budget: removing the wrap fails ≥1 assertion.

### Bucket C — BACKLOG hygiene (1 AC)

- **AC09** — Hygiene pass on `BACKLOG.md`:
  - DELETE the 4 Phase 4.5 LOW `cycle-71+` entries (per AC01-AC04 deletion markers).
  - Refresh CVE re-check timestamp for `diskcache 5.6.3 / CVE-2025-69872` (Phase 6 R2 LOW) from `2026-05-08` → `2026-05-09`.
  - Bump cycle-tag for ANY remaining `cycle-71+` items (none expected — all 4 are deleted by this cycle).
  - **NEW Phase 4.5 LOW entry** for cycle 71 R2 Codex / R1 review carry-overs (placeholder, populated post-merge if R2 surfaces non-blocking findings — mirrors cycle-69 / cycle-70 carry-over pattern).

### Bucket D — Doc artifacts (3 ACs)

- **AC10** — Cycle-71 decision artifacts under `docs/superpowers/decisions/`:
  - `2026-05-09-cycle-71-requirements.md` (this file)
  - `2026-05-09-cycle-71-threat-model.md` (Step 02)
  - `2026-05-09-cycle-71-brainstorm.md` (Step 03)
  - `2026-05-09-cycle-71-design-eval-R1-opus.md` (Step 04 R1)
  - `2026-05-09-cycle-71-design-eval-R2-deepseek.md` (Step 04 R2)
  - `2026-05-09-cycle-71-design.md` (Step 05 design gate output)
  - `2026-05-09-cycle-71-plan.md` (Step 07)
  - `2026-05-09-cycle-71-plan-gate.md` (Step 08)
  - `2026-05-09-cycle-71-step24-self-review.md` (Step 24 — landed via follow-up PR if needed)

- **AC11** — `CHANGELOG.md` `[Unreleased]` Quick Reference entry for cycle-71 (compact Items / Tests / Files / Detail) + `CHANGELOG-history.md` per-AC detail block (newest first).

- **AC12** — `CLAUDE.md` Quick Reference sync: test count (3288 → 3288 + ~4 new lock-ins = ~3292), scope language for cycle-71 (e.g., "12 ACs / 3 src/kb/ src files / 1 new test file / 4 prompt-injection wrap completions"), update the "Wiki-context boundary fence" bullet to reflect 6 in-scope sites (was 2 — adds the 4 cycle-71 sites). Remove the duplicate boundary-fence bullet that appears twice in current CLAUDE.md (lines 31 + 32 are the same — pre-existing minor doc drift to clean up).

## Out of scope (explicit)

- **Phase 6 R2 LOW** — `mcp_server.py` shim + `mcp/__init__.py` PEP-562 redundancy: deferred indefinitely per cycle-67 cleanup pass (low-value churn). Skip.
- **Phase 4.5 MEDIUM** — Remaining cycle-64 R3 deferred snapshot subjects (`build_extraction_prompt`, `_render_sources` — `_build_summary_content`, `build_llms_full_txt`, `build_graph_jsonld`, `contradictions_append` already shipped cycles 69-70). Defer to cycle 72 (theme-orthogonal — testing infra, not prompt-safety).
- **Phase 4.5 LOW** — `mutmut` mutation-coverage on cycle-64 regression suite. Defer (analytical only, no shipping change required this cycle).
- **Phase 4.5 MEDIUM** — `config.py` god-module split: deferred (large refactor, dedicated cycle).
- **Phase 4.5 MEDIUM** — `compile/compiler.py` per-source rollback: deferred (architectural).
- **Phase 4.5 MEDIUM** — `utils/io.py` JSONL migration: deferred (architectural).
- **Phase 4.5 MEDIUM** — `tests/` Windows CI matrix re-enable / GHA-Windows multiprocessing / TestWriteItemFiles POSIX off-by-one: deferred (already tagged `cycle-53+` / `cycle-57+`, not bumped).
- **Phase 5 candidates**: defer (feature roadmap, not BACKLOG bug-class).
- Phase 6/7/8 candidates: defer.

## Verification done at Step 01

| Item | Method | Status |
|------|--------|--------|
| AC01 target source line | `Read mcp/browse.py:1-200` → `_format_search_results` at lines 31-56, snippet computed at line 47 | confirmed |
| AC02 target source line | `Read mcp/browse.py:1-200` → `kb_read_page` returns at line 162; cap arithmetic at lines 133, 151-161 | confirmed |
| AC03 target source line | `Read lint/semantic.py:1-120` → `build_fidelity_context` returns `"\n".join(lines)` at line 95 | confirmed |
| AC04 target source line | `Read lint/augment/proposer.py:100-180` → `_relevance_score` at lines 136-148, prompt at lines 138-143 | confirmed |
| AC02 budget interaction | `Read mcp/browse.py:130-162` → `cap_bytes = QUERY_CONTEXT_MAX_CHARS * 4 + 4096`; char-cap at line 151 | budget point identified |
| AC03 budget interaction | `Read lint/semantic.py:36-60` → `_render_sources` budget loop respects `QUERY_CONTEXT_MAX_CHARS` | budget point identified |
| Helper exists | `Read utils/text.py:329-393` → `wrap_wiki_context` shipped, `_FENCE_OVERHEAD` exported | confirmed |
| Existing call sites | `grep -rn "wrap_wiki_context" src/kb/` → 4 hits (utils/text.py def + 1 call in mcp/core.py + 1 call + 1 import in query/engine.py) | confirmed |
| 4 BACKLOG entries | `Read BACKLOG.md:152-159` → 4 LOW entries tagged `cycle-71+` for the 4 surfaces | confirmed |

## Stats targets

- **ACs:** 12
- **Commits:** ~10-12 (per-AC + doc-sync)
- **Tests:** 3288 → ~3292 (+4 net: 4 lock-in tests in 1 new file)
- **src/kb/ files modified:** 3 (mcp/browse.py, lint/semantic.py, lint/augment/proposer.py)
- **New test files:** 1 (tests/test_cycle71_prompt_safety.py — all 4 lock-ins co-located)
- **Doc files modified:** 4-5 (CLAUDE.md, CHANGELOG.md, CHANGELOG-history.md, BACKLOG.md, plus decision docs)

## Risk callouts

- **R1 — Per-snippet vs whole-result fencing for kb_search.** AC01 wraps each `r["content"]` snippet independently rather than wrapping the full formatted output once. This produces multiple `<wiki_context>` blocks in a single result list. Step 03 brainstorming must choose: per-snippet (BACKLOG suggestion, isolates each untrusted blob) vs whole-result-once (smaller overhead, but mixes controlled scaffolding text into the fence). Step 05 locks one approach.
- **R2 — Budget arithmetic for kb_read_page.** AC02 requires reducing `QUERY_CONTEXT_MAX_CHARS` by `_FENCE_OVERHEAD` BEFORE wrapping so the total response stays ≤ `QUERY_CONTEXT_MAX_CHARS`. Failure mode: if the cap is applied as-is and then wrapped, total response exceeds the documented budget and downstream MCP transport limits could fail. Step 14 security-verify must confirm.
- **R3 — `build_fidelity_context` already-assembled-context wrap.** AC03 wraps the assembled `"\n".join(lines)` after `_render_sources`. The `_render_sources` budget loop is unaware of the outer `_FENCE_OVERHEAD`. Two options: (a) reduce the budget passed into `_render_sources` by `_FENCE_OVERHEAD`, OR (b) accept that fenced output may exceed `QUERY_CONTEXT_MAX_CHARS` by ~150 chars (the assertion text). Step 05 locks one approach.
- **R4 — Fence-overhead-aware budget regression in tests.** New lock-ins must NOT mask a budget regression. Add an explicit `len(response) <= QUERY_CONTEXT_MAX_CHARS` assertion in AC06 lock-in (`kb_read_page`).
- **R5 — Lock-in vacuousness.** Lock-in tests fail the cycle-9 L1 / cycle-11 L1 / cycle-16 L2 / cycle-24 L1 patterns. Per cycle-24 L1: position assertions beat content assertions when testing security-class anti-patterns. Each AC05-AC08 must include a paired negative control (replace `wrap_wiki_context` import locally with identity in a `monkeypatch.setattr` and assert the test FAILS — captured in a documented but normally-skipped `xfail`-style sentinel test, OR confirmed manually during Step 14 security verify with grep + Edit + run).

## Approval

Step 1 self-approved by primary session (Opus 4.7 main). Proceeding to Step 2 (threat model + dep-CVE baseline).
