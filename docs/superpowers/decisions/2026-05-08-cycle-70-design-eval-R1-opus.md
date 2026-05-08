# Cycle 70 — R1 Opus Design Eval

**Date:** 2026-05-08
**Reviewer:** Opus subagent (R1)
**Verdict:** APPROVE-WITH-AMENDMENTS

## Summary

Cycle 70 is a well-scoped Tier-2 fold (16 ACs, ~3 src/kb/ touches). BACKLOG hygiene (AC01-AC04) and snapshot ACs (AC06-AC08) are evidence-backed and shippable as written. AC09 (cycle-69 carry-over audit) is correct in conclusion (existing patch IS sufficient). Two binding amendments are required for AC11 (prompt-injection fence): (a) the AC's call-site enumeration is INCOMPLETE — at least 4 additional wiki/raw-content-into-LLM sites exist beyond `mcp/core.py:383` + `query/engine.py:1077`, and (b) the T5 fence-overhead reservation must be applied at the COMBINED-context site (engine.py:1063 `context = ctx["context"] + raw_context`), not only inside `_build_query_context`. AC06 has one factual error (no contradictions in `_build_summary_content`).

## AC-by-AC verdict

### Bucket A — BACKLOG hygiene

- **AC01** (httpx pin shipped) — **APPROVE.** Verified at `pyproject.toml:30` (`"httpx>=0.28,<0.29"`). BACKLOG entry exists at `BACKLOG.md:103`. Delete is safe.

- **AC02** (README KB_PROJECT_ROOT) — **APPROVE.** Verified at `README.md:137,141,142,148`. BACKLOG entry exists at `BACKLOG.md:165`. Delete is safe.

- **AC03** (KB_STRICT_PUBLISH) — **APPROVE.** Verified at `src/kb/compile/compiler.py:619,624` (env read with truthy variants `{1,true,yes}` per cycle-67 AC04 contract) and `src/kb/query/hybrid.py:21` (docstring reference). BACKLOG entry exists at `BACKLOG.md:159`. Delete is safe.

- **AC04** (inspect.getsource batch) — **APPROVE.** Verified zero function-call hits across the 4 cited test files. The 5 grep hits at `tests/test_lint_query_fixes_v092.py:276`, `tests/test_v0911_phase392.py:244`, `tests/test_v0915_task01.py:316,355`, `tests/test_v0915_task08.py:356` are ALL inside docstrings/comments documenting the prior conversion (cycle-69 AC07-AC12 work). BACKLOG entry exists at `BACKLOG.md:153`. Delete is safe.

- **AC05** (lock-in extension) — **APPROVE.** Pattern is well-established at `tests/test_cycle68_backlog_cleanup_lockin.py:19-33` (cumulative `DELETED_ENTRIES` tuple). Adding 4 new substrings is mechanical. NIT: pick substrings unique enough to survive future BACKLOG narrative drift (avoid e.g. `httpx` alone — pick `httpx constraint mismatch` per cycle-69 pattern).

### Bucket B — Snapshot subjects

- **AC06** (`_build_summary_content` snapshot) — **AMEND** (factual error in fixture spec). The function definition at `src/kb/ingest/pipeline.py:408-483` has NO contradictions handling. It processes `entities_mentioned`, `concepts_mentioned`, `key_claims`/`key_points`/`key_arguments`, `authors`, plus `core_argument`/`abstract`/`description`/`problem_solved`. The AC says "3 entities, 2 concepts, 2 contradictions" — the contradictions claim is wrong. **Required amendment:** drop "2 contradictions" from the fixture spec; replace with "2 key_claims" (which IS rendered). Negative-control unchanged. Determinism check: `slugify`, `sanitize_extraction_field`, `wikilink_display_escape`, `_is_untitled_sentinel` are all input-deterministic — no datetime, env, or random vectors. APPROVE on amended fixture.

- **AC07** (`build_llms_full_txt` snapshot) — **APPROVE-WITH-CONDITION.** Function at `src/kb/compile/publish.py:209-287`. Determinism vectors identified:
  - `load_all_pages` uses `sorted(subdir_path.glob("*.md"))` at `src/kb/utils/pages.py:142` — deterministic.
  - `_sort_pages` uses `sorted(pages, key=lambda p: p["id"])` at `publish.py:127` — deterministic.
  - `LLMS_FULL_MAX_BYTES` is a config constant.
  - `header = f"# {title}\n\n"` and `_PAGE_SEPARATOR` are static.

  Condition: fixture frontmatter MUST set `title`, `created`, `updated` explicitly (no autopopulation). The truncation footer also embeds `remaining_ids[:3]` — fixture must keep page count well below truncation cap. Negative-control valid: changing one page body content WILL produce a different output. APPROVE.

- **AC08** (`build_graph_jsonld` snapshot) — **AMEND** (canonicalization wording). Function at `src/kb/compile/publish.py:290-367` uses `json.dumps(document, ensure_ascii=False, indent=2)` — it does NOT use `sort_keys=True`. Python 3.7+ preserves dict insertion order so the output IS deterministic in practice, but the AC's wording "Use `json.dumps(obj, sort_keys=True, indent=2)` style canonicalization in the assertion" is misleading. **Required amendment:** EITHER (a) parse the snapshot back through `json.loads` and compare against a sort_keys-canonicalized expected (decouples from key-order changes), OR (b) drop the `sort_keys=True` mention and rely on insertion-order determinism since `build_graph_jsonld` itself does not sort keys. Pick (a) for robustness — future production-side dict-key reorderings won't break the snapshot. Determinism check: `extract_wikilinks` preserves source order (`src/kb/utils/markdown.py:81-91`), `id_to_url` iterates `kept` (already sorted by `_sort_pages`), `nodes.append(node)` preserves order. APPROVE on amended assertion.

### Bucket C — Cycle-69 R2 Codex carry-over

- **AC09** (date-coverage audit) — **APPROVE.** Verified by reading `_persist_contradictions` (`src/kb/ingest/pipeline.py:183-221`). The function's transitive closure inside `kb.ingest.pipeline` is: `file_lock`, `Path.read_text`, `source_ref.split`, `date.today().isoformat()` (lines 207, 216), `sanitize_extraction_field`, `atomic_text_write`. None of `file_lock`/`atomic_text_write`/`sanitize_extraction_field` call `date.today()` — they live in `kb.utils.io` / `kb.utils.text` and the `_FakeDate` patch on `pipeline.date` would NOT cover those modules, BUT they don't call date at all. Lines 351 (`_write_wiki_page`) and 664 (`_update_existing_page`) are NOT reached from `_persist_contradictions`. Coverage IS sufficient. The Q5 recommendation (audit + forward-looking date-string lock-in assertion) is sound; the lock-in test asserts `2026-05-08` appears in the snapshot's `## ref — DATE` header, so a future relocation that bypasses the patch would shift the date and trip the assertion. APPROVE.

### Bucket D — Test quality

- **AC10** (C41-L1 behavioral upgrade) — **APPROVE-WITH-CONDITION.** Verified test at `tests/test_compile.py:217-239` uses `inspect.getsource(compiler)`. The two call sites the spy must cover are:
  - **Site 1 (`detect_source_drift`):** lines 292 (`_canonical_rel_path(s, raw_dir)` in set comprehension) and 312 (`_canonical_rel_path(source, raw_dir)`) of `src/kb/compile/compiler.py`. Plus 373 (also in `detect_source_drift`'s return dict).
  - **Site 2 (`compile_wiki` full-mode):** line 466 of `compiler.py`.

  Condition: the parametrized B-option spy must NOT swap the helper with a bare `Mock()` because lines 292 and 312 are bare-name lookups inside the same module — replace `compiler._canonical_rel_path` with a `Mock(wraps=compiler._canonical_rel_path)` so calls still produce real return values (otherwise downstream `set` operations and `affected_pages` lookups will break and the test will fail for unrelated reasons). Mutation budget per AC text: "removing the helper call from either site fails ≥1 spy assertion" — the parametrized form satisfies this (test_full_mode and test_drift_detect each pinned independently). APPROVE.

### Bucket E — MCP prompt-injection boundary

- **AC11** (wrap_wiki_context fence) — **AMEND (binding).** Three issues:

  1. **Call-site enumeration is incomplete.** AC11 cites only `mcp/core.py:383` and `query/engine.py:1077`, but the actual wiki/raw-content-into-LLM-prompt sites in current source are:
     - `src/kb/query/engine.py:1063,1078` — `context = ctx["context"] + raw_context`; injected into synthesis prompt at the `WIKI CONTEXT:\n{context}` line. **Both `ctx["context"]` AND `raw_context` carry untrusted content** — fence MUST cover the combined value.
     - `src/kb/mcp/core.py:417-432` — `kb_query` Claude Code mode builds `--- Page: ... ---\nTitle: ...\n\n{r['content']}\n` and returns to Claude Code. This response IS the next prompt input.
     - `src/kb/mcp/browse.py:31-56` — `_format_search_results` snippets (200 chars of `r["content"]`).
     - `src/kb/mcp/browse.py:147-162` — `kb_read_page` returns raw page body up to `QUERY_CONTEXT_MAX_CHARS`.
     - `src/kb/lint/semantic.py:76-95` — `build_fidelity_context` injects `paired["page_content"]` + `_render_sources(paired["source_contents"])` into a Claude Code prompt.
     - `src/kb/lint/augment/proposer.py:142` — `_relevance_score` injects `extracted_text[:2000]` (untrusted source) into the scan-tier LLM prompt.

     **Required amendment:** AC11 must declare which subset of these is in-scope and which is out-of-scope, with rationale. Recommended in-scope: `engine.py` synthesis prompt (#1) + `mcp/core.py` Claude Code mode response (#2). Out-of-scope (with rationale documented): `kb_search` snippets (#3 — 200 chars, low risk), `kb_read_page` (#4 — by-id read of already-validated page), `build_fidelity_context` (#5 — defer to follow-up cycle as Phase 4.5 LOW), `proposer.py:_relevance_score` (#6 — separate scope, file separate BACKLOG entry).

  2. **T5 fence-overhead reservation site is wrong.** Threat model says "subtract fence_len from `effective_max` in `_build_query_context`" (engine.py:756). But the synthesis prompt site at engine.py:1063 concatenates `raw_context` AFTER `_build_query_context` returns. If the fence wraps the COMBINED `context` (correct scope), then the overhead reservation must be at the synthesis-prompt site, not in `_build_query_context`. Alternative: wrap `ctx["context"]` AND each raw section separately (each fenced) — but that double-fences and bloats overhead. **Required amendment:** decide which site owns the fence and revise T5 mitigation accordingly. Recommended: wrap the combined `context` at engine.py:1063-1078; reserve overhead from `QUERY_CONTEXT_MAX_CHARS` at line 1051 (`budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"])`) becomes `budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"]) - FENCE_OVERHEAD`.

  3. **Naming + module location.** The `wrap_purpose` precedent at `src/kb/utils/text.py:315-326` uses `<kb_purpose>...</kb_purpose>` + `_escape_kb_purpose_close`. Q1 picks `src/kb/query/prompt_safety.py` as a NEW module. The Q1 rationale (matches `kb.utils.path_safety` precedent) is reasonable but the existing `wrap_purpose` lives in `kb.utils.text`. **Recommendation:** colocate `wrap_wiki_context` with `wrap_purpose` in `kb.utils.text` to keep all prompt-fence helpers in ONE module — both functions share an identical contract (escape literal close-tag, wrap with sentinel, hard-cap optional). This is a NIT, not a binding amendment. If the new module is preferred, document the placement rationale in the design doc.

- **AC12** (lock-in tests for AC11) — **APPROVE.** Q7-C (unit + integration) is the right scope. Add coverage for:
  - Unit: `wrap_wiki_context("hello")` → contains both fence open + close + assertion; `wrap_wiki_context("")` → empty short-circuit (T4); `wrap_wiki_context("</wiki_context>")` → escaped (T3 sanitization).
  - Integration: spy `wrap_wiki_context` to assert it's called from each in-scope production site enumerated in the AC11 amendment. **Note:** if AC11 wraps the combined `context` at engine.py:1063, the integration test must call `_query_wiki_body` end-to-end with a fake `call_llm` to capture the prompt and assert the fence appears around the wiki content. APPROVE.

### Bucket F — Doc artifacts

- **AC13** (decision artifacts) — **APPROVE.** 9 files enumerated; files for Steps 1-3 already exist; this R1 verdict is one of them.

- **AC14** (CHANGELOG entries) — **APPROVE.** Standard cycle pattern. NIT: cycle-70 ships `src/kb/` changes (AC11) so CHANGELOG body should explicitly cite the touched modules + the new helper module path.

- **AC15** (CLAUDE.md sync) — **APPROVE.** Test-count delta + scope language are mechanical. AC11 helper is significant enough to warrant a Quick Reference bullet (mirrors how `wrap_purpose` was documented in cycle 7 AC23).

- **AC16** (BACKLOG.md final hygiene) — **APPROVE.** All 6 DELETE markers (AC01-AC04, AC10, AC11) trace to verified BACKLOG entries (lines 103, 151, 153, 159, 162, 165). CVE re-check timestamp + `cycle-71+` tag bumps are mechanical.

## Threat-by-threat verdict

- **T1 (prompt-injection from raw/ content)** — **ACCEPTED** with AC11 amendment. The `wrap_wiki_context()` + system-prompt assertion is industry-standard defense-in-depth. Residual (LLM compliance is best-effort) is acknowledged.

- **T2 (boundary helper bypassed by future code path)** — **ACCEPTED.** AC12 lock-in covers current sites; F1 (forward-looking AST guard) is a sensible BACKLOG addition.

- **T3 (literal `</wiki_context>` escape)** — **ACCEPTED.** Mirror the `_escape_kb_purpose_close` precedent (`src/kb/utils/text.py:310-313`). Lock-in test covers this case.

- **T4 (empty wiki-context orphan tags)** — **ACCEPTED.** Short-circuit pattern is identical to `wrap_purpose` (returns `""` on empty). Lock-in test covers this case.

- **T5 (length cap interaction)** — **NEEDS-MITIGATION-CHANGE.** As detailed in AC11 amendment item 2: the fence-overhead reservation site is wrong if the fence wraps the combined `context` (which it should, given that `raw_context` is also untrusted). Move the reservation to engine.py:1051 (the `budget` calculation for raw context) OR to the prompt-builder site. Document the choice in design.md.

- **T6 (snapshot determinism)** — **ACCEPTED.** AC06-AC08 production functions verified deterministic for fixed inputs (no datetime, env, or random vectors in `_build_summary_content` / `build_llms_full_txt` / `build_graph_jsonld`). Test docstrings should enumerate the verified vectors.

- **T7 (Python-version hash drift)** — **ACCEPTED.** No hash output appears in any of the three snapshot subjects' default flow. `slugify`'s `sha256[:6]` fallback only fires on pure-symbol input; AC06's fixture must avoid such inputs (recommend titles like `"Attention is all you need"` per cycle-69 AC13 fixture).

- **T8 (date.today() coverage)** — **ACCEPTED.** Verified by reading `_persist_contradictions` transitive closure. Q5-C (audit + lock-in) is sound. AC09 verdict: "audit-and-document" with forward-looking date-string lock-in. NO production change.

- **T9 (vacuous spy on AC10)** — **ACCEPTED** with AC10 condition. Q6-B (parametrize 2 sites) gives crisp regression-attribution. Use `Mock(wraps=...)` not `Mock()` to keep real return values.

- **T10 (BACKLOG re-introduction)** — **ACCEPTED.** Pattern proven across cycles 68-69; AC05 extends the existing tuple.

## Question resolutions

- **Q1 (`prompt_safety.py` location)** — **counter-proposal (soft).** Place `wrap_wiki_context` next to `wrap_purpose` in `kb.utils.text` so all prompt-fence helpers live in one module. The "future prompt-safety extensions" rationale for a separate module is speculative; YAGNI suggests staying in `kb.utils.text` until there's a second helper that doesn't fit. NIT only — if Step 5 prefers the dedicated module, document the placement rationale in design.md.

- **Q2 (XML tags + T3 escape)** — **agree-with-rec.** Matches `wrap_purpose` precedent. Use `_escape_wiki_context_close(text)` symmetric to `_escape_kb_purpose_close`.

- **Q3 (system + fence header)** — **agree-with-rec.** Defense-in-depth with minimal cost. The fence header sentence should be brief enough that it doesn't materially shift `effective_max` arithmetic.

- **Q4 (shared `_build_fixture_wiki(tmp_path)`)** — **agree-with-rec.** Cycle-50 helper-homing pattern. Single source of truth for the fixture.

- **Q5 (audit + forward-looking date-string lock-in, no production change)** — **agree-with-rec.** Verified above that no gap exists. The forward-looking lock-in is a low-cost safety net.

- **Q6 (parametrize 2 sites)** — **agree-with-rec.** Use `Mock(wraps=compiler._canonical_rel_path)` to preserve real return values. Note the `_canonical_rel_path(s, raw_dir)` set-comprehension form at line 292 will count as ONE invocation per source — assertion `spy.call_count >= 1` is correct.

- **Q7 (unit + integration)** — **agree-with-rec.** Both layers needed. Integration test must end-to-end exercise `_query_wiki_body` with a stub `call_llm` to capture the actual prompt string.

- **Q8 (3 new files + extend cycle-68 lock-in)** — **agree-with-rec.** Mirrors cycle-69 cadence.

## MAJORs (binding amendments — must be applied before Step 9)

1. **AC06 fixture spec is wrong** (`docs/superpowers/decisions/2026-05-08-cycle-70-requirements.md:38`). `_build_summary_content` (`src/kb/ingest/pipeline.py:408-483`) handles entities, concepts, key_claims/key_points/key_arguments, authors, and core_argument/abstract/description/problem_solved — but NOT contradictions. Drop "2 contradictions" from the fixture; replace with "2 key_claims" or similar field actually rendered.

2. **AC11 call-site enumeration is incomplete** (`docs/superpowers/decisions/2026-05-08-cycle-70-requirements.md:54`). At minimum, the design doc must enumerate ALL 6 wiki/raw-content-into-LLM-prompt sites listed above, mark each in-scope or out-of-scope, and justify the scope. Recommended in-scope: engine.py:1063 (synthesis combined-context) + mcp/core.py:417-432 (Claude Code mode response). Out-of-scope sites must be filed as Phase 4.5 LOW BACKLOG entries.

3. **T5 fence-overhead reservation is at the wrong site** (`docs/superpowers/decisions/2026-05-08-cycle-70-threat-model.md:19`). If AC11 wraps the COMBINED context (which it must, since `raw_context` at engine.py:1051 is also untrusted), the overhead reservation cannot live in `_build_query_context`. Move to the prompt-builder site (engine.py:1063 area) and update both the threat model and the design doc.

4. **AC08 canonicalization wording is misleading** (`docs/superpowers/decisions/2026-05-08-cycle-70-requirements.md:42`). `build_graph_jsonld` does NOT use `sort_keys=True` (verified at `src/kb/compile/publish.py:366`). The AC must either (a) state explicitly that the assertion canonicalizes by re-parsing + sort_keys (production output is insertion-order), or (b) drop the canonicalization mention and pin the actual production output bytes.

## MINORs / NITs (suggested but non-binding)

1. **N1** — Q1 module location: prefer colocation with `wrap_purpose` in `kb.utils.text` until a second prompt-safety helper exists. Speculative `prompt_safety.py` violates YAGNI but is acceptable if Step 5 prefers dedicated namespacing.

2. **N2** — AC05 substring uniqueness: pick distinctive phrases (cycle-69 pattern: 4-7 words including a unique noun). Avoid e.g. `"httpx"` alone.

3. **N3** — AC10 spy mechanic: use `unittest.mock.Mock(wraps=compiler._canonical_rel_path)` not bare `Mock()` so the real return value flows. Document this in plan.md.

4. **N4** — Step 14 verification checklist (threat-model.md:48-59) should add a check that `wrap_wiki_context` short-circuits BEFORE the truncation cap is applied (so empty-context callers don't pay the overhead).

5. **N5** — `kb.lint.augment.proposer._relevance_score` (line 142) injects `extracted_text[:2000]` into a scan-tier LLM prompt without wrapping. File as Phase 4.5 LOW BACKLOG entry per AC11 amendment item 1's out-of-scope handling.

6. **N6** — `kb.lint.semantic.build_fidelity_context` (line 76) injects `paired["page_content"]` + raw source content into a Claude Code prompt. Same out-of-scope BACKLOG handling as N5.

7. **N7** — AC11 should explicitly note whether `kb_search` snippets and `kb_read_page` body returns count as "wiki text into an LLM prompt". The MCP transport response IS the next prompt input for Claude Code; rigorously they qualify, but pragmatically they are out-of-scope for cycle-70 (would require fencing every Claude-Code-facing MCP response).

## Final fact-check

Re-verifying each MAJOR by Read or Grep:

1. **AC06 contradictions claim** — Re-read `src/kb/ingest/pipeline.py:408-483`. Confirmed: zero "contradiction" tokens in this function body. Confirmed: function reads `entities_mentioned`, `concepts_mentioned`, `key_claims`/`key_points`/`key_arguments`, `authors`, plus the abstract/description fields. MAJOR 1 stands.

2. **AC11 call-site enumeration** — Re-read `src/kb/query/engine.py:1063,1078` (combined `context`); `src/kb/mcp/core.py:417-432` (`lines.append(f"--- Page: ...")`); `src/kb/mcp/browse.py:31-56` (snippet); `src/kb/mcp/browse.py:147-162` (kb_read_page body); `src/kb/lint/semantic.py:76-95` (build_fidelity_context); `src/kb/lint/augment/proposer.py:142` (extracted_text in _relevance_score). All 6 sites confirmed to inject untrusted content into LLM-bound output. MAJOR 2 stands.

3. **T5 reservation site** — Re-read `src/kb/query/engine.py:1051,1063,1077-1086`. Confirmed: `_build_query_context` at line 728 returns BEFORE `raw_context` is appended at line 1063. The threat-model.md:19 says reserve fence_overhead in `_build_query_context` — this is upstream of the combined-context site. MAJOR 3 stands.

4. **AC08 canonicalization** — Re-read `src/kb/compile/publish.py:366`: `atomic_text_write(json.dumps(document, ensure_ascii=False, indent=2) + "\n", out_path)`. Confirmed: NO `sort_keys=True`. AC08 wording at requirements.md:42 says "Use `json.dumps(obj, sort_keys=True, indent=2)` style canonicalization in the assertion" — ambiguous whether this is the test's assertion or a request to change production. MAJOR 4 stands.

No downgrades. All 4 MAJORs survive fact-check.

## Verdict (final, post-fact-check)

**APPROVE-WITH-AMENDMENTS.** Apply MAJORs 1-4 before Step 9. NITs/MINORs are non-binding. Bucket A (BACKLOG hygiene) and AC09/AC10/AC12-AC16 are clean and shippable as-is. AC06/AC08/AC11 amendments are scoped and bounded. Total work-add from amendments: ~2 hours of design.md tightening + minor test-spec adjustments — no scope expansion to a follow-up cycle.
