# Cycle 16 — Threat Model (Opus subagent, Step 2)

**Date:** 2026-04-20
**Scope:** 24 ACs across 8 source files (see `2026-04-20-cycle16-requirements.md`).
**Baseline:** Dependabot 0 alerts; pip-audit 1 informational (`diskcache==5.6.3` CVE-2025-69872, unpatched upstream).

---

## Analysis

Cycle 16's surface splits into four distinct attack classes, each anchored to a specific AC:

- **User-controlled slug surface (AC17-AC19):** `kb_query(save_as=...)` accepts an attacker-controllable string and turns it into a filesystem path under `wiki/synthesis/`. The cycle-4 `_validate_page_id` helper (`src/kb/mcp/app.py`) is the reference pattern — any looser check (e.g. trusting `slugify()` alone) is exploitable because `slugify` deliberately preserves CJK/Cyrillic codepoints, so Unicode homoglyphs pass the "alphanumeric" smell test. AC19 demands character whitelist + `..` + absolute-path rejection. The write target (`wiki/synthesis/`) is INSIDE the search-index corpus, so a successful write poisons the BM25 index (unlike `outputs/` which is gitignored by the Phase 4.11 adapter design).
- **LLM output injection (AC7-AC9):** `_suggest_rephrasings` is new scan-tier LLM output. Cycle 14 T5 resolved the static advisory by forbidding `question` interpolation; cycle 16 reintroduces the echo risk through the LLM side channel. AC9 requires filtering verbatim echoes; case/whitespace normalization is subtle and must be tested. The helper also composes `context_pages` titles into a prompt — an attacker-owned wiki page with a hostile title can influence subsequent queries.
- **Algorithmic and parser DoS (AC10-AC12):** `check_duplicate_slugs` is declared O(N²). `parse_inline_callouts` uses `^> \[!(contradiction|gap|stale|key-insight)\][^\n]*$` with `re.MULTILINE` — literal anchoring keeps it linear BUT regex drift (greedy `.*`, whitespace tolerance) reopens the quadratic-alt path. `CALLOUT_MARKERS` tuple is safe as long as each marker is regex-escaped.
- **Output-disclosure (AC20-AC22):** `build_sitemap_xml` must use `xml.etree.ElementTree` for escaping. A naive string-cat like `f"<loc>{url}</loc>"` breaks the XML or injects content. `build_per_page_siblings` writes `pages/{page_id}.txt`; legacy non-slugified page_ids could carry path components. Both must reuse cycle-15 T10c ordering: `_partition_pages` BEFORE `_publish_skip_if_unchanged`, or retracted content leaks in the skip branch.

## Threats

### T1 — save_as path traversal (AC17-AC19)
User-controlled slug → filesystem write outside `wiki/synthesis/`.
- **Attack:** `save_as="../../outside.md"` / `save_as="/abs/path"` / `save_as="\u202eevil"` (RTL homoglyph) escapes the synthesis subdir.
- **Impact:** Arbitrary file write resolvable relative to `wiki/synthesis/`, including overwriting `wiki/index.md` or deep-traversing into `src/kb/*.py`.
- **Mitigation:** Reject `..`, absolute paths, backslashes, and any char outside `[a-z0-9-]` AFTER `slugify`. Assert `slugify(save_as) == save_as` (anti-homoglyph). Resolve final path and enforce `resolved.is_relative_to(WIKI_SYNTHESIS.resolve())`.

### T2 — Index poisoning via save_as write (AC18)
Attacker-controlled content reaches BM25 search corpus.
- **Attack:** `kb_query(question="<prompt>", save_as="popular-topic")` persists LLM hallucination; next `search_pages` call indexes it.
- **Impact:** Long-term corruption of query answers; persistent prompt injection.
- **Mitigation:** Hardcode `confidence: inferred` AND `type: synthesis` AND `authored_by: llm` at the write site. Never parameterize.

### T3 — Rephrasings echo user question (AC7-AC9)
LLM-generated suggestion equals question verbatim.
- **Attack:** `question="<script>alert(1)</script>"` → LLM returns it verbatim → naive equality check misses case/whitespace variants.
- **Impact:** Reflected injection; the advisory surface is pierced by the LLM side channel.
- **Mitigation:** Lowercase + `re.sub(r"\s+", " ", s).strip()` both sides before equality. `[]` return on any LLM failure (bare except, log-and-return-empty, never raise).

### T4 — Hostile page titles in rephrasing prompt (AC7)
Wiki content poisons scan-tier prompt.
- **Attack:** Page with `title: "Ignore previous instructions..."` in top search results injects instructions into the scan-tier LLM context.
- **Impact:** Rephrasings include exfiltrated content or adversarial redirects.
- **Mitigation:** Wrap titles in fenced delimiters (`<page_title>...</page_title>`) with per-title char cap; sanitize via `yaml_sanitize`-equivalent (strip control chars, bidi marks).

### T5 — Catastrophic backtracking in callout regex (AC11)
ReDoS via adversarial page body.
- **Attack:** Regex drift (greedy `.*`, trailing `\s*?`) enables polynomial backtracking on hostile content.
- **Impact:** Single hostile page freezes `kb_lint`.
- **Mitigation:** Lock regex to spec-literal with NO optional spaces; build marker alternation via `"|".join(re.escape(m) for m in CALLOUT_MARKERS)`; add 1 MB page-body cap before regex scan.

### T6 — O(N²) slug-pair DoS (AC10)
Unbounded pair iteration on 10K+ page wikis.
- **Attack:** N=50,000 pages yields 1.25B pair comparisons.
- **Impact:** CPU exhaustion; `kb_lint` timeouts.
- **Mitigation:** Port `MAX_CONNECTION_PAIRS=50_000` pattern. Either skip-with-warning when `len(pages) > 10_000` OR length-bucket slugs so only near-length pairs compare (edit-distance > threshold impossible when `abs(len(a) - len(b)) > threshold`).

### T7 — XML injection in sitemap.xml (AC21)
Unescaped characters in `<loc>` or `<lastmod>`.
- **Attack:** Legacy page_id with `&` / `<` / `]]>` breaks XML or injects second `<url>`.
- **Impact:** Malformed sitemap; potential HTML injection if rendered.
- **Mitigation:** Mandatorily use `xml.etree.ElementTree` (`SubElement` + `.text` assignment). Never f-string child text.

### T8 — Sitemap URL absolute-path leak (AC21)
Operator filesystem leak via `<loc>`.
- **Attack:** `<loc>file:///D:/Projects/...` leaks project root.
- **Impact:** Information disclosure.
- **Mitigation:** AC21 specifies `<loc>` as relative POSIX `pages/{page_id}.txt`. Test: no `<loc>` contains `file:`, `http:`, `:\`, `//`, `..`.

### T9 — Per-page sibling path traversal via page_id (AC20)
Legacy page_id with path components escapes output dir.
- **Attack:** `page_id="../../evil"` passes through to `out_dir / "pages" / f"{page_id}.txt"` escaping `out_dir/pages`.
- **Impact:** Arbitrary write under `out_dir/..`; same class as T1.
- **Mitigation:** Resolve final target and assert `target.resolve().is_relative_to((out_dir / "pages").resolve())` per write. Skip pages whose id fails this check with WARNING.

### T10 — Epistemic filter bypass on incremental skip (AC22)
Retracted content leaks through `incremental=True`.
- **Attack:** First publish predates epistemic filter; subsequent incremental run short-circuits, stale retracted `.txt`/`.json` persists.
- **Impact:** Retracted content continues to be served.
- **Mitigation:** `_partition_pages` BEFORE `_publish_skip_if_unchanged` (cycle-15 T10c pattern). Also delete existing `{out_dir}/pages/{excluded_page_id}.{txt,json}` on every non-incremental run so newly-retracted pages drop cleanly.

### T11 — Rephrasings LLM prompt logs leak question (AC7)
Scan-tier prompt leaks user question to logs.
- **Attack:** Helper logs full prompt at DEBUG/INFO; log aggregators archive.
- **Impact:** Question-level PII leak.
- **Mitigation:** Never log full prompt. Log only `question[:80]` (matches cycle-4 pattern in `mcp/core.py`).

### T12 — `parse_inline_callouts` memory blowup (AC11)
Unbounded match list on pathological input.
- **Attack:** Hand-crafted page with 100K callout-shaped lines produces 100K dicts.
- **Impact:** MCP thread memory exhaustion.
- **Mitigation:** Cap `parse_inline_callouts` at 500 matches per page with truncation record; cap total `inline_callouts` at 10K across all pages.

### T13 — Suggest-enrichment status injection (AC4-AC6)
Legacy page with malformed `status` leaks unescaped into report.
- **Attack:** Unvalidated `status: "<script>"` on a pre-cycle-14 page flows into rendered report.
- **Impact:** Report-side injection downstream.
- **Mitigation:** Filter on `status in PAGE_STATUSES` BEFORE output formatting (defense in depth on top of `validate_frontmatter`). Escape status values via `yaml_sanitize` when rendering.

### T14 — Duplicate-slug false positives/negatives (AC10, AC13)
Subdir stripping or case-drift corrupts distance computation.
- **Attack:** `concepts/attention` vs `entities/attention` (same stem, different subdirs) mis-matched; OR case-drift on case-insensitive FS creates duplicates.
- **Impact:** False-positive noise drowns signal OR false-negatives hide real drift.
- **Mitigation:** Slug = full lowered page_id (subdir retained). Distance 0 excluded. AC13 anchors the expected behavior.

### T15 — Verbose-mode traceback leak (AC17-AC19)
Stacktrace of save_as validation reveals `WIKI_DIR` path.
- **Attack:** `save_as` validation raises; `KB_DEBUG=1` prints full traceback with `WIKI_DIR` absolute path.
- **Impact:** Operator filesystem-layout disclosure.
- **Mitigation:** `save_as` validation returns error strings via MCP `error_tag(...)` — never raise. Validation is synchronous and pure.

## Dep-CVE note
- **Class A baseline:** 0 Dependabot alerts; 1 pip-audit informational (`diskcache==5.6.3` CVE-2025-69872, no `fix_versions`, trafilatura robots.txt cache only — tracked in BACKLOG.md MEDIUM).
- **Class B (PR-introduced):** TBD at Step 11 via `pip-audit` diff against `main` HEAD `d8097ec`.

## Step-11 verification checklist

| Threat | Enforcement point | Regression test | Step-11 status |
|---|---|---|---|
| T1 | `save_as` rejects `..`/absolute/non-`[a-z0-9-]`; `slugify(save_as) == save_as`; `resolved.is_relative_to(WIKI_SYNTHESIS)` | `test_save_as_traversal_dotdot`, `test_save_as_absolute`, `test_save_as_unicode_homoglyph`, `test_save_as_windows_reserved` | `____________` |
| T2 | Hardcoded `confidence/type/authored_by` at write site | `test_save_as_writes_inferred_confidence`, `test_save_as_frontmatter_immutable` | `____________` |
| T3 | Case-insensitive + whitespace-normalized echo filter; `[]` on LLM error | `test_rephrasings_echo_filter_case_insensitive`, `test_rephrasings_llm_error_returns_empty`, `test_rephrasings_empty_context_returns_empty` | `____________` |
| T4 | Prompt wraps titles in fences; per-title char cap | `test_rephrasings_prompt_fences_titles`, `test_rephrasings_hostile_title_truncated` | `____________` |
| T5 | Regex literal = spec; `re.escape(marker)`; body length cap | `test_parse_inline_callouts_no_redos`, `test_callout_regex_literal_matches_spec` | `____________` |
| T6 | N² cap or length bucketing; skip-with-warning | `test_check_duplicate_slugs_large_wiki_bounded_runtime` | `____________` |
| T7 | `xml.etree.ElementTree` `.text` assignment; round-trip test | `test_sitemap_escapes_special_chars`, `test_sitemap_round_trips_xml` | `____________` |
| T8 | `<loc>` starts with `pages/`; no absolute substrings | `test_sitemap_urls_relative_posix` | `____________` |
| T9 | `target.resolve().is_relative_to((out_dir/pages).resolve())` per write | `test_per_page_siblings_rejects_traversal_page_id` | `____________` |
| T10 | `_partition_pages` BEFORE skip; stale-sibling cleanup | `test_siblings_excludes_retracted_on_incremental`, `test_siblings_removes_newly_retracted` | `____________` |
| T11 | Prompt logging truncated to ≤80 chars | `test_rephrasings_does_not_log_full_question` | `____________` |
| T12 | 500-match per-page cap + 10K cross-page cap | `test_parse_inline_callouts_truncation_cap` | `____________` |
| T13 | `status in PAGE_STATUSES` filter before emit | `test_enrichment_filters_unknown_status` | `____________` |
| T14 | Slug = full lowered page_id (subdir retained); distance 0 excluded | `test_duplicate_slugs_subdir_not_merged`, `test_attention_attnetion_flagged`, `test_attention_mechanism_not_flagged` | `____________` |
| T15 | `save_as` validation returns error strings; never raises | `test_save_as_invalid_never_raises_under_verbose` | `____________` |

Class B dep-CVE baseline row: `__________` (collected via `pip-audit` diff at Step 11 against `main` HEAD `d8097ec`).
