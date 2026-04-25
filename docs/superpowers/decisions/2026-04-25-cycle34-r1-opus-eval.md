# Cycle 34 — Release Hygiene · R1 Opus Design Evaluation

**Date:** 2026-04-25 · **Cycle:** 34 · **Reviewer:** R1 Opus (parallel with R2 Codex)
**Inputs:** `2026-04-25-cycle34-requirements.md` (48 ACs), `2026-04-25-cycle34-threat-model.md` (5 TBs / 14 threats / 25-row checklist), `2026-04-25-cycle34-brainstorming.md` (Q1-Q10 defaults).
**Verification:** all cited symbols grep-confirmed against the live tree at HEAD = `e439539` (cycle 33 self-review).

---

## Analysis

Cycle 34 is a textbook "release hygiene" cycle: 48 ACs, 17 file groups, but the modal AC is a 1-3-line edit. Of the 48, 6 are file deletions, 12 are new pytest assertions, 14 are doc text replacements, 5 are pyproject.toml/requirements.txt/SECURITY.md/CI metadata, and ~11 are README/CLAUDE.md correctness updates. There is exactly one runtime-code change of any kind — `src/kb/config.py` removing `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` (AC24) and the matching error-message rewrite at `src/kb/ingest/pipeline.py:1261-1262` (AC25). The rest is metadata, prose, or filesystem state. Blast radius is the smallest of any cycle in the project's history; the genuinely novel boundary is the new `.github/workflows/ci.yml` workflow, which the threat model addresses comprehensively (T1-T5, T11, plus auth/log section). Every cited symbol I grep-checked exists where the requirements doc claims, with two minor caveats explained in the symbol-verification table below. Both R2 Codex and R3 will need to validate that the *implementation* does not drift from the spec — but the spec itself is internally consistent.

The eval surfaces three real concerns that warrant CONDITIONS rather than wholesale amendments. (1) **AC18's exact-line replacement targets a `> blockquote`, not a paragraph.** The requirements doc proposes a multi-clause replacement tagline, but the literal line at `README.md:5` is `> **Compile, don't retrieve.** ... No vectors. No chunking. ...` — a single blockquote line. The edit MUST preserve `> ` markup so the README header layout stays intact. Naively splitting it into two lines (one tagline + one bullet) without preserving the `>` marker would change the rendered HTML. (2) **AC19 should be narrowed up-front, not at "verify time".** `KB_DISABLE_VECTORS` does NOT exist in `src/kb/` — grep confirmed zero matches. The requirements doc already provides the narrow form ("documents the OPT-OUT via not installing the `hybrid` extra"), but this should be the *default* AC19 contract rather than a verify-time fallback to avoid a DESIGN-AMEND late in Step 9. (3) **Both T7 and AC29-AC32 incorrectly assume the scratch files are git-tracked.** `git ls-files findings.md progress.md task_plan.md claude4.6.md docs/repo_review.md docs/repo_review.html` returns EMPTY — none of the six "deletions" are tracked files. They live only in the working tree. AC29-AC34 are therefore filesystem-only `rm` operations, not `git rm` operations, and the threat-model row 11's `git ls-files` check would *trivially* pass before the cycle even runs. The substantive threat T7 ("gitignore added but file not deleted") is real but easy to satisfy: the cycle just needs to do a regular `rm` (or Bash `del`) plus the `.gitignore` patterns. The requirements doc is correct in spirit, but Step 11's check should be `test ! -f findings.md && test ! -f ...` rather than `git ls-files`. The threat model writes one line that already covers both interpretations: "T7's verification: `git ls-files ... returns empty`" passes pre-cycle AND post-cycle, so it's a degenerate check. R2 Codex should call this out independently; R1 surfaces it here as Open-issue #1.

The 10 design questions Q1-Q10 are well-posed and the brainstorming defaults are conservative-correct in 9 of 10 cases. The one I push back on (mildly) is **Q5** (KB_DISABLE_VECTORS runtime flag vs extras-only): the brainstorming default of EXTRAS-ONLY is correct but the AC19 wording should be tightened. Beyond Q1-Q10, I surface two *new* design questions: (NEW-Q11) Should AC4's version bump be a separate AC for `pyproject.toml` and `src/kb/__init__.py` (which also carries a version), so both stay in lockstep? Grep for `__version__` shows it lives in `src/kb/__init__.py` — the requirements doc only mentions pyproject.toml. (NEW-Q12) Should AC42 also assert that `.gitignore` actually contains the patterns *and* the files don't exist on disk, since `claude4.6.md` is in `.gitignore` only by NEW pattern (per AC17) — with the AC17 wording "claude4.6.md does NOT go in `.gitignore` — we DELETE it instead", a future user manually creating a `claude4.6.md` working copy would NOT be caught by `.gitignore`. This is fine for cycle 34 (one-shot delete), but the regression test should call it out so a future reader understands why one of four scratch files is *not* in the gitignore pattern set.

---

## Symbol verification table

| Symbol | Cited at | Found at | Result |
|---|---|---|---|
| `jsonschema` import | `src/kb/utils/cli_backend.py:17` | `cli_backend.py:17` (`import jsonschema`) | EXISTS ✓ |
| `pyproject.toml` version | `pyproject.toml:3` = `0.10.0` | `pyproject.toml:3` = `version = "0.10.0"` | EXISTS ✓ |
| `pyproject.toml` `readme` | `pyproject.toml:6` = `"CLAUDE.md"` | `pyproject.toml:6` = `readme = "CLAUDE.md"` | EXISTS ✓ |
| `pyproject.toml` `[project.optional-dependencies]` | already declared (only `dev`) | line 20-24, only `dev = [...]` exists | EXISTS ✓ (only `dev`; AC2 adds 4 more keys) |
| `dependencies = [...]` 6 items | `pyproject.toml:7-14` | `click`, `python-frontmatter`, `fastmcp`, `networkx`, `anthropic`, `PyYAML` (6 items) | EXISTS ✓ (matches problem statement #1) |
| `README.md:5` literal | proposed: `> **Compile, don't retrieve.** ... No vectors. No chunking. ...` | exact match: `> **Compile, don't retrieve.** Drop a source in. Claude does the rest — extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. No vectors. No chunking. Pure markdown you own, browsable in Obsidian.` | EXISTS ✓ (it's a `>` blockquote — see AC18 condition) |
| `README.md:9` tests badge | `tests-2850-brightgreen` | `[![Tests](https://img.shields.io/badge/tests-2850-brightgreen)]` | EXISTS ✓ (drift confirmed: 2850 vs live 2923) |
| `README.md:142` PDF row | `\| PDF \| .pdf \| ...` | `\| PDF \| \`.pdf\` \| Supported by the compile pipeline; for direct MCP ingest, convert to Markdown first \|` | EXISTS ✓ |
| `README.md:384` hybrid mention | claims `hybrid search with RRF fusion` | `**v0.10.0:** Phase 4 — hybrid search with RRF fusion (BM25 + vector via model2vec + sqlite-vec)` | EXISTS ✓ (drift vs line 5 confirmed) |
| `KB_DISABLE_VECTORS` env var | claimed in `src/kb/query/hybrid` | grep across `src/` returns empty | **MISSING** — AC19 narrow form mandatory (see below) |
| `SUPPORTED_SOURCE_EXTENSIONS` | `src/kb/config.py:117-119` | `frozenset({.md, .txt, .pdf, .json, .yaml, .yml, .rst, .csv})` | EXISTS ✓ (`.pdf` confirmed present pre-cycle) |
| `Binary file cannot be ingested` rejection | claimed line 1230/1233 | actual at `src/kb/ingest/pipeline.py:1261-1262` (full message: `"Binary file cannot be ingested: {source_path.name}. " "Convert to markdown first (e.g., markitdown or docling)."`) | **SEMANTIC-MISMATCH (line numbers)** — message exists at 1261-1262, NOT 1230/1233. Already names markitdown/docling, so AC25 may be a no-op rewrite if the goal is just "drop PDF specificity". |
| `kb_save_synthesis` references in CLAUDE.md | claimed via AC22/AC27 | grep returns ZERO matches in CLAUDE.md (and ZERO in README.md) | **SEMANTIC-MISMATCH** — the only matches are in CHANGELOG.md, CHANGELOG-history.md, BACKLOG.md, docs/reviews/, and docs/superpowers/decisions/. CLAUDE.md uses `save_as=` everywhere (lines 308, 46). AC22 + AC27 + AC46 may be no-op for the listed file scope. |
| `tests/test_v0916_task03.py:43` binary rejection test | exists, asserts behaviour-not-message | actual at `tests/test_v0916_task03.py:43-50`: `pdf.write_bytes(b"%PDF-1.4\x00\x01\x02binary content"); ...; with pytest.raises((UnicodeDecodeError, ValueError)): ingest_source(pdf, "paper")` | EXISTS ✓ (test asserts exception type only — `UnicodeDecodeError` or `ValueError`. The message text is NOT asserted, so AC25 message change does NOT break it.) |
| Repo-root scratch files | `findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md` | `ls -la` confirms all 4 exist as files; `git ls-files` returns EMPTY for all 6 (incl. `docs/repo_review.{md,html}`). | EXISTS-on-disk ✓ but UNTRACKED — see Open-issue #1 |
| `docs/repo_review.{md,html}` | claimed exist | `ls -la` confirms both exist; UNTRACKED | EXISTS-on-disk ✓ |
| `docs/reviews/2026-04-25-comprehensive-repo-review.{md,html}` | claimed exist as untracked | `ls` confirms both exist | EXISTS-on-disk ✓ (untracked) |
| `tests/test_cycle34_*` | claimed empty | `ls tests/test_cycle34_*.py` returns "No such file or directory" | EMPTY ✓ (correct pre-implementation state) |
| `CLAUDE.md:7` test-count | claimed 2923 | line 7: `**State:** v0.10.0 · 2923 tests / 253 files (2912 passed + 10 skipped + 1 xfailed)` | EXISTS ✓ |
| `CLAUDE.md:45` test-count | claimed 2923 | line 45: `**Latest full-suite:** 2923 tests / 253 files · 2912 passed + 10 skipped + 1 xfailed` | EXISTS ✓ |
| `CLAUDE.md:189` test-count | claimed 2923 | line 189: `Full suite: 2923 tests / 253 files (2912 passed + 10 skipped + 1 xfailed)` | EXISTS ✓ |
| Live test count via `pytest --collect-only -q` | claimed 2923 | actual `2923 tests collected in 3.37s` | EXISTS ✓ (matches CLAUDE.md exactly; **no drift today** — but README.md:9 says 2850, that's the documented Finding 6 drift) |
| `_save_synthesis` helper | claimed `src/kb/mcp/core.py:220` | line 220: `def _save_synthesis(slug: str, result: dict) -> str:` | EXISTS ✓ (helper name, NOT MCP tool; cycle 16 cited correctly) |

**Net mismatches:** 3 — the line-number drift on AC25 (1230/1233 → 1261-1262), the line-number-irrelevant `KB_DISABLE_VECTORS` non-existence (AC19), and the `kb_save_synthesis` zero-match in target files for AC22 + AC27 (the rename is closer to "verify already absent" than "rename existing references"). Each becomes an AC AMEND below.

---

## AC scorecard

### Group A — trivial APPROVED (no risk, no conditions)

**AC1, AC4, AC5, AC10, AC11, AC12, AC15, AC16, AC23, AC26, AC28, AC29, AC30, AC31, AC33, AC34, AC35, AC36, AC37, AC38, AC39, AC41, AC42, AC43, AC44, AC45, AC47, AC48: APPROVED.** Why: each is a 1-3-line metadata change, file delete, or fixture-free pytest assertion that maps 1:1 to its parent contract. The threat model addresses each via Step-11 row 11-25. No conditions beyond the existing AC text.

### Group B — APPROVED with explicit CONDITIONS

**AC2 (extras declared): APPROVED.** Why: 5-key structure matches comprehensive review §4 + brainstorming Q3 default. CONDITIONS: (a) each extra MUST list pinned versions (e.g. `model2vec>=0.3.0`) using `>=`, not loose, to align with `requirements.txt` style; (b) `dev` extra must MERGE with the existing `dev = [pytest>=7.0, ruff>=0.4.0]` (not replace) — the requirements doc says "Existing `dev` extra extended" but Step-9 must verify the merge, not replace.

**AC3 (runtime deps incl. jsonschema): APPROVED.** Why: jsonschema confirmed at `cli_backend.py:17`; it's a real runtime import. CONDITIONS: (a) the `pip install . --no-deps` test in CI is a runtime-import surface check, NOT just an import-error test; (b) per Q1, `anthropic` STAYS in required `dependencies` (brainstorming default A — agree); (c) document in `pyproject.toml` comments that `anthropic` SDK is required for direct API mode but not used by Claude Code MCP path.

**AC6 (SECURITY.md narrow-role table): APPROVED.** CONDITIONS: (a) each row MUST include the verification grep that confirms `src/kb/` doesn't import the package; (b) row format must include UNBLOCK condition for litellm (per T10 + brainstorming Q4). The threat-model T4 row already mandates this.

**AC7, AC8 (disclosure path + cadence): APPROVED.** CONDITIONS: (a) AC7 must list BOTH a GitHub Security Advisory link AND an email fallback (T6 mitigation); (b) AC8's cadence text must match the wording `"Every cycle's Step 2 baseline + Step 11 PR-CVE diff + Step 15 late-arrival warn"` from the requirements doc verbatim so the AC44 pytest can assert the header.

**AC9 (CI workflow exists): APPROVED.** CONDITIONS: (a) MUST include explicit top-level `permissions: read-all` (or `contents: read`) per threat T1; (b) MUST use `on: [push, pull_request]` not `pull_request_target` per T1; (c) action pin form is `actions/checkout@v4` and `actions/setup-python@v5` per T2 (intentional tag-pin, not floating).

**AC13 (pip check soft-fail): APPROVED.** CONDITIONS: (a) `continue-on-error: true` MUST apply ONLY to the `pip check` step, not to ruff/pytest/pip-audit/build; (b) BACKLOG entry MUST be added in Step 12 (cycle-N+1 tracker) for "fix `pip check` resolver conflicts (`arxiv`/`requests`, `crawl4ai`/`lxml`, `instructor`/`rich`)".

**AC14 (pip-audit with --ignore-vuln): APPROVED.** CONDITIONS: (a) the four CVE IDs MUST exactly match the SECURITY.md acceptance table — NO disjoint set between CI and SECURITY.md; (b) any CVE that gains an upstream fix must be DROPPED from `--ignore-vuln` immediately, not deferred (T4 + T10 mitigation); (c) pip-audit step MUST `--strict` everywhere except those four IDs.

**AC17 (gitignore patterns added): APPROVED.** CONDITIONS: (a) the patterns MUST land in the same PR as AC29-AC34 deletions (T7 mitigation); (b) `claude4.6.md` is INTENTIONALLY excluded from the gitignore set (per cycle-34 design — one-shot legacy file, not a recurring scratch type). Step-9 must NOT auto-add `claude4.6.md` to gitignore. (c) the four patterns are: `findings.md`, `progress.md`, `task_plan.md`, `cycle-*-scratch/` (forward-looking).

**AC20 (PDF row clarified): APPROVED.** CONDITIONS: (a) the new sentence "PDF files: convert with markitdown or docling first ..." MUST appear UNDER the supported-formats table, not inside it; (b) `.docx`/`.pptx`/`.xlsx` paragraph at `README.md:144` is unchanged (not in scope).

**AC21 (tests badge replaced): APPROVED.** CONDITIONS: (a) per Q6 default A — switch to generic `tests-passing-brightgreen`; (b) the existing badge at `README.md:9` MUST be REPLACED, not duplicated; (c) no other count-bearing badge added in cycle 34 (per Q6, dynamic shield is cycle-N+1).

**AC24 (PDF removed from SUPPORTED_SOURCE_EXTENSIONS): APPROVED.** CONDITIONS: (a) verify by grep + import test in pytest (AC41); (b) downstream check: `kb compile` invocation on a `raw/papers/foo.pdf` file produces a CLEAR "unsupported extension" error PRIOR to read_bytes (per T8 mitigation); (c) BACKLOG entry MUST be added for "real PDF text extraction (cycle-N+1 if requested)".

**AC32 (delete claude4.6.md): APPROVED.** CONDITIONS: (a) MUST diff against current `CLAUDE.md` first (per risk register Row 4); (b) any novel-content drift MUST be surfaced as DESIGN-AMEND per cycle-17 L3 — NOT silently merged into CLAUDE.md; (c) the cycle-34 PR description MUST note that `claude4.6.md` was an UNTRACKED working-tree file, not a git-tracked file (so this is `rm`, not `git rm` — see Open-issue #1).

**AC40 (no_vectors_tagline_absent test): APPROVED.** CONDITIONS: (a) test asserts the LITERAL string `"No vectors. No chunking."` is NOT in `README.md` (cycle-24 L4 content-presence regression that flips on revert); (b) test must NOT also assert the new tagline is present in the same assertion (separate concerns, easier to debug failures).

**AC46 (kb_save_synthesis CLAUDE.md regression): APPROVED with MAJOR CONDITION.** CONDITIONS: (a) per the symbol-verification table, `kb_save_synthesis` does NOT currently appear in CLAUDE.md (zero matches). The regression must assert "(`kb_query(save_as=...)`" or "save_as=" mention is PRESENT in CLAUDE.md — NOT that "kb_save_synthesis is absent" (which would trivially pass pre-cycle). (b) Test name reads accurate: `test_kb_save_synthesis_clarification_in_claude_md` should assert `save_as` clarification, not the negative.

### Group C — AMEND

**AC18 — AMEND**: the requirements doc proposes a NEW multi-clause tagline + a NEW bullet, but `README.md:5` is currently a single `> blockquote` line. The replacement MUST preserve the `> ` blockquote markup. Also: the proposed wording introduces "optional hybrid retrieval" which is a separate phrase from the existing "No vectors. No chunking." — the AC needs to clarify whether the BLOCKQUOTE replaces the ENTIRE existing line 5 (yes, per the requirements doc + AC40 negative-assert) and whether the NEW bullet is a SEPARATE addition further down (probably under "Why users pick this over RAG" at lines 17-23, which already has 7 bullets). **AMENDED CONTRACT:** "Replace `README.md:5` with `> **Compile, don't retrieve.** Drop a source in. Claude does the rest — extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. Markdown-first; optional hybrid retrieval. Pure markdown you own, browsable in Obsidian.` (preserving `>` blockquote). Modify the existing bullet at `README.md:17` from `🧠 **Structure, not chunks.** ...` to `🧠 **Structure first, optional vectors.** Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.`"

**AC19 — AMEND**: `KB_DISABLE_VECTORS` does NOT exist in `src/kb/` (verified by grep — zero matches). The requirements doc already provides the narrow form ("documents the OPT-OUT via not installing the `hybrid` extra"). **AMENDED CONTRACT:** "Documents the hybrid layer as opt-in; the OPT-OUT mechanism is 'do not install the `hybrid` extra' (extras-only per Q5 default A). DO NOT introduce a new runtime env var in cycle 34. If a future user demands a runtime kill-switch, that's a cycle-N+1 follow-up."

**AC22 — AMEND**: `kb_save_synthesis` does NOT currently appear in `README.md` (zero matches). The contract should switch from "Replace any reference" to "Verify the reference does NOT appear; if any future cycle re-introduces it, regression catches it." The actual rename targets are CHANGELOG.md/CHANGELOG-history.md/BACKLOG.md (3 files, several occurrences), and BACKLOG.md:159 already says `kb_save_synthesis is NOT an MCP tool`. **AMENDED CONTRACT:** "Verify `README.md` does NOT contain `kb_save_synthesis`. If future drift introduces it, the cycle 34 test (a new variant of AC46 scoped to README.md) catches it. NO file edits required for AC22 alone."

**AC25 — AMEND (line numbers)**: the rejection message is at `src/kb/ingest/pipeline.py:1261-1262`, NOT 1230 or 1233. Current message is `"Binary file cannot be ingested: {source_path.name}. Convert to markdown first (e.g., markitdown or docling)."`. The current message ALREADY suggests markitdown/docling. **AMENDED CONTRACT:** "Update the rejection message at `src/kb/ingest/pipeline.py:1261-1262` to drop the implicit-PDF assumption. Proposed wording: `f'Binary file cannot be ingested: {source_path.name}. Only text source types ({", ".join(sorted(SUPPORTED_SOURCE_EXTENSIONS))}) are supported. Convert with markitdown or docling first.'`. Verify `tests/test_v0916_task03.py:49` still passes (the `pytest.raises((UnicodeDecodeError, ValueError))` test asserts type, not message text — confirmed safe)."

**AC27 — AMEND**: same root cause as AC22 — `kb_save_synthesis` does NOT appear in CLAUDE.md (zero matches). The Module Map section (CLAUDE.md:30-39) and MCP Servers section (CLAUDE.md:302-321) ALREADY use `save_as=` correctly (lines 46, 308). **AMENDED CONTRACT:** "CLAUDE.md ALREADY uses `kb_query(save_as=<slug>)` correctly; AC27 narrows to a no-op 'verify present' check. The actual rename work is in BACKLOG.md / CHANGELOG.md / CHANGELOG-history.md, which is OUT OF SCOPE for AC27 (those are Step-12 doc-update files, not editable in Step 9). AC27 thus collapses to AC46's regression."

### Group D — DROP CANDIDATES

**None.** No AC should be dropped. AC22, AC27, and AC19 above narrow but do not become no-ops because their pytest regressions (AC40, AC42, AC46) still provide forward-looking drift protection.

---

## Design questions Q1-Q10

**Q1 — Keep `anthropic` in required `dependencies` or move to `[default-llm]` extra?**
- Default: KEEP REQUIRED. **Verdict: AGREE.**
- Why: `anthropic` is lazy-imported by `kb.utils.llm.call_llm`; without it, any `use_api=True` MCP call or direct CLI compile/query fails at first call. Default install must work end-to-end. Brainstorming approach C (runtime check) is cycle-N+1 nice-to-have.

**Q2 — PDF: remove from `SUPPORTED_SOURCE_EXTENSIONS` (a) or implement extractor (b)?**
- Default: OPTION (A). **Verdict: AGREE.**
- Why: review explicitly recommends (a); cycle-34's narrow scope rules out (b). T8 confirms net-better UX (extension-rejected at scan time vs binary-rejected at read time). BACKLOG entry tracks (b) as cycle-N+1 if requested.

**Q3 — Extras structure (5 keys vs coarser)?**
- Default: 5 KEYS (`hybrid`, `augment`, `formats`, `eval`, `dev`). **Verdict: AGREE.**
- Why: matches comprehensive-review §4 + Karpathy-style "install only what you need" granularity. Brainstorming approach B (3 coarser) loses signal. CONDITION: `dev` must EXTEND existing, not replace.

**Q4 — `pip-audit` strict vs `--ignore-vuln`?**
- Default: `--ignore-vuln` per documented narrow-role CVE. **Verdict: AGREE.**
- Why: T4 mitigation depends on this exact strategy; SECURITY.md is the audit trail. Strict (B) fails CI day 1 since none of the 4 have upstream fixes. Brainstorming C (continue-on-error) defeats the gate signal entirely.

**Q5 — `KB_DISABLE_VECTORS=1` runtime flag or extras-only opt-out?**
- Default: EXTRAS-ONLY for cycle 34. **Verdict: AGREE.**
- Why: confirmed `KB_DISABLE_VECTORS` does NOT exist (grep). Adding it is cycle-N+1 if needed. AC19 tightens accordingly above.

**Q6 — Tests badge: static count, generic, or dynamic shield?**
- Default: GENERIC (`tests-passing`). **Verdict: AGREE.**
- Why: removes the drift surface (Finding 6); CI is the authoritative test pass signal. Static (B) drifts again next cycle; dynamic (C) needs a shields.io endpoint cycle-N+1.

**Q7 — Comprehensive review file location?**
- Default: `docs/reviews/2026-04-25-comprehensive-repo-review.{md,html}`. **Verdict: AGREE.**
- Why: date-stamped naming + dedicated `docs/reviews/` convention is the right discipline for future audit artifacts. Already untracked at the right path; cycle 34 just commits.

**Q8 — Translate cycle-34 changes to `README.zh-CN.md`?**
- Default: NO (defer to batched cycle). **Verdict: AGREE-WITH-MINOR-ADDITION.**
- Why: brainstorming's "tiny C addendum" (add an "English is canonical, may lag 1-2 cycles" header note) is cheap and prevents a bilingual PR review burden. Recommend ADD AC23.5: "Add header note to `README.zh-CN.md`: '> Note: English README is canonical. This Chinese mirror may lag by 1-2 cycles; see GitHub for current state.'"

**Q9 — `pip check` in CI: gate or report?**
- Default: `continue-on-error: true`. **Verdict: AGREE.**
- Why: T5 mitigation explicitly accepts this with a documented unblock plan (cycle-N+1 fixes the three known conflicts, then drops continue-on-error). Brainstorming B (skip entirely) loses NEW-conflict signal.

**Q10 — `requirements.txt` restructure?**
- Default: KEEP unchanged + header comment. **Verdict: AGREE.**
- Why: concurrent reshuffle with extras declaration is risky (too many things changing). Cycle-36 follow-up.

### NEW design questions surfaced by R1

**NEW-Q11 — Should AC4 also bump `src/kb/__init__.py.__version__`?**
- The version bump from `0.10.0` → `0.11.0` per AC4 only mentions `pyproject.toml`. But `src/kb/__init__.py` carries `__version__` (per CLAUDE.md docstring: "Version in `src/kb/__init__.py`"). If only one is bumped, `kb --version` could disagree with `pip show kb`.
- **Verdict: NEEDS-MORE-INFO.** Step-5 decision gate should rule: "AC4 covers BOTH pyproject.toml and src/kb/__init__.py" (recommended) OR "version source is pyproject.toml only and src/kb/__init__.py reads from it dynamically" (verify Step-9). If they're independent, AC4 needs to be SPLIT into AC4a + AC4b.

**NEW-Q12 — Should AC42 also assert `.gitignore` patterns are present + scratch files don't exist?**
- AC42 currently asserts only "scratch files absent". AC43 asserts ".gitignore lists patterns". Should they be merged or remain separate?
- **Verdict: AGREE-WITH-CURRENT-PROPOSAL.** Keep separate; AC42 + AC43 cover the two halves of T7 mitigation independently. Easier to debug failures.

---

## BACKLOG.md cleanup map

Per requirements doc § 7 Definition of Done, cycle 34 closes COMPREHENSIVE-REVIEW Findings 1, 2, 3, 5, 6, 7, 9, 20. Mapping each to the BACKLOG.md entry (where one exists) and cycle-34 AC:

| Finding # | BACKLOG entry / file:line key | cycle-34 AC | Step-12 action |
|---|---|---|---|
| 1 (`pyproject.toml` readme + missing deps) | NOT in BACKLOG.md (surfaced by 2026-04-25 comprehensive review) | AC1 + AC2 + AC3 + AC23 | NO BACKLOG entry to delete; ADD CHANGELOG entry "fixed pyproject.toml readme + extras + jsonschema runtime dep" |
| 2 (`pip check` + `pip-audit` advisories) | `requirements.txt litellm==1.83.0`, `requirements.txt pip==26.0.1`, `requirements.txt ragas==0.4.3`, `lint/fetcher.py diskcache==5.6.3` (4 entries in BACKLOG.md MEDIUM section, lines 125-135) | AC6 + AC8 + AC14 | NARROW (do NOT delete) — each entry stays open with the new "documented in SECURITY.md + ignored in CI" status; deletion happens when upstream fix lands |
| 3 (no `.github/workflows/`) | NOT in BACKLOG.md (surfaced by 2026-04-25 comprehensive review) | AC9-AC16 | NO BACKLOG entry to delete; ADD CHANGELOG entry "added .github/workflows/ci.yml with ruff + pytest + pip check + pip-audit + build" |
| 5 (README.md:5 vs README.md:384 + README.md:142 PDF drift) | NOT in BACKLOG.md (surfaced by 2026-04-25 comprehensive review) | AC18 + AC20 | NO BACKLOG entry to delete; ADD CHANGELOG entry "fixed README content drift: hybrid-search tagline, PDF support clarification" |
| 6 (tests badge `tests-2850` drift vs live 2923) | NOT in BACKLOG.md | AC21 | NO BACKLOG entry to delete; ADD CHANGELOG entry "replaced static tests-count badge with generic tests-passing" |
| 7 (4 scratch files in repo root) | NOT in BACKLOG.md | AC17 + AC29 + AC30 + AC31 + AC32 | NO BACKLOG entry to delete |
| 9 (`docs/repo_review.{md,html}` superseded) | NOT in BACKLOG.md | AC33 + AC34 + AC35 + AC36 | NO BACKLOG entry to delete |
| 20 (`kb_save_synthesis` doc clarification) | `BACKLOG.md:159` — `kb_save_synthesis is NOT an MCP tool` | AC22 + AC27 + AC46 | NARROW or DELETE — the BACKLOG note already calls out "NOT an MCP tool"; if the call-out is felt to be redundant after AC22/27/46 ship, delete. Per design-eval, RETAIN the BACKLOG note since the CLI ↔ MCP parity entry there is still open. |

**Summary:** ZERO BACKLOG entries fully deleted by cycle 34 (the 4 CVE entries stay open until upstream fix; the `kb_save_synthesis` call-out stays as a parity-tracker comment). All 8 closures are NEW CHANGELOG entries against `[Unreleased]`. This is correctly a "documentation-and-CI" cycle, not a backlog-burn cycle.

---

## Open issues

**Open-issue #1 — Six "deletions" are UNTRACKED, not git-tracked.**
- `git ls-files findings.md progress.md task_plan.md claude4.6.md docs/repo_review.md docs/repo_review.html` returns EMPTY.
- Implication: AC29-AC34 are filesystem-only `rm` operations, not `git rm`. The cycle-34 commit will NOT include any git-rm in its diff for these six files because they were never staged.
- The threat-model T7 verification row 11 (`git ls-files ... returns empty`) is degenerate: it passes pre-cycle AND post-cycle. Replace with `test ! -f findings.md && test ! -f progress.md && test ! -f task_plan.md && test ! -f claude4.6.md && test ! -f docs/repo_review.md && test ! -f docs/repo_review.html`.
- **DECISION-GATE RULING NEEDED:** confirm Step 9 implementer should use `rm` (or Bash `del`) for the six files, NOT `git rm`. Updates to T7 verification accordingly.

**Open-issue #2 — `claude4.6.md` UNTRACKED but contains `# CLAUDE.md` header.**
- Confirmed: `head -5 claude4.6.md` shows `# CLAUDE.md\n\nThis file provides guidance to Claude Code...`. So claude4.6.md IS a snapshot of an older CLAUDE.md.
- 314 lines vs current CLAUDE.md ~345 lines. Diff against current CLAUDE.md to verify NO novel content beyond the cycle-17-L3 escape hatch.
- **DECISION-GATE RULING NEEDED:** confirm Step 9 includes a `diff CLAUDE.md claude4.6.md` snapshot in the PR description so future readers can audit what the deleted snapshot contained.

**Open-issue #3 — AC25 message rewrite is partially redundant with current text.**
- Current message at `pipeline.py:1261-1262` already says `"Convert to markdown first (e.g., markitdown or docling)"` — it already names markitdown/docling.
- AC25's contract ("update the message to NOT name PDF specifically") could collapse to a no-op IF the current message doesn't name PDF.
- Inspection: current message says `"Binary file cannot be ingested"` — does NOT name PDF. So the current message is already PDF-agnostic. The AC25 rewrite is COSMETIC/STYLE only (e.g., enumerating the supported extensions).
- **DECISION-GATE RULING NEEDED:** confirm Step 9 implementer rewrites the message even though the current message is already adequate, OR collapses AC25 to a no-op (and AC25's regression test asserts the existing message text). Recommended: rewrite to enumerate supported extensions for the user's benefit (better UX).

**Open-issue #4 — `permissions: read-all` block missing from threat-model row 2.**
- Threat T1's mitigation requires `permissions: read-all` in `.github/workflows/ci.yml`. The Step-11 row 2 grep is `grep -E '^permissions:|^  permissions:' .github/workflows/ci.yml`.
- AC9 requirements text only mentions `on:` and `jobs:`. The `permissions:` block is implicit per T1 but not explicitly enumerated as an AC.
- **DECISION-GATE RULING NEEDED:** add to AC9 conditions: "MUST include explicit top-level `permissions: read-all` (or `contents: read`) block." OR add a new sub-AC9.5 explicitly for this.

**Open-issue #5 — `requirements.txt` may need updates if `pyproject.toml` adds `jsonschema`.**
- Pre-cycle, `requirements.txt` includes `jsonschema` indirectly via transitive deps. Post-cycle, `pyproject.toml.dependencies` adds `jsonschema` as a direct dep.
- Verify `requirements.txt` line 30+ has `jsonschema==X.Y.Z` pin. If not, AC5 may need a one-line addition (otherwise the requirements.txt file lacks the pin for direct install).
- **DECISION-GATE RULING NEEDED:** Step 9 verifies `jsonschema` is pinned in `requirements.txt` post-cycle. If absent, AC5 expands to add `jsonschema==X.Y.Z`.

**Open-issue #6 (NEW design question) — Version bump consistency between pyproject.toml and src/kb/__init__.py.**
- See NEW-Q11 above. Step-5 ruling needed.

**Open-issue #7 (process) — kb_save_synthesis BACKLOG.md note retention.**
- Per the BACKLOG cleanup map, the BACKLOG.md:159 prose `kb_save_synthesis is NOT an MCP tool` is a narrow call-out within a CLI ↔ MCP parity entry. Cycle 34 closes the doc-clarification half (AC22 + AC27); the CLI ↔ MCP parity entry remains open.
- **DECISION-GATE RULING NEEDED:** retain the BACKLOG.md call-out for now (cycle 34 doesn't fully close the parity entry); REMOVE the call-out only when the CLI ↔ MCP parity entry itself is closed.

---

## Verdict

**APPROVE-WITH-CONDITIONS.**

The 48 ACs cover the right surface for a release-hygiene cycle, the threat model addresses the new CI workflow boundary comprehensively, and the brainstorming defaults Q1-Q10 are conservative-correct. Three ACs need wording amendments (AC18 blockquote-preservation, AC19 narrow-form-only, AC25 line-number correction) and three carry significant CONDITIONS (AC22, AC27, AC46 reframe to "verify present" rather than "replace existing"). Two NEW design questions (NEW-Q11 version-bump symmetry, NEW-Q12 already-resolved) plus four open issues (untracked-not-tracked deletion semantics, claude4.6.md diff-snapshot requirement, AC25 message-rewrite redundancy, permissions-block explicitness) warrant Step-5 decision-gate rulings. None of the issues block the cycle; all are amend-shape, not reject-shape. Net counts: 28 APPROVED-trivial, 14 APPROVED-with-conditions, 5 AMEND, 0 DROP. Total = 47, +1 split (NEW-Q11 may split AC4 into AC4a+AC4b) = 48-49.

Cycle 34 is the right cycle, with the right scope. Ship after Step-5 rulings on Open-issues #1-#7 and the AC AMENDS land in the design doc.
