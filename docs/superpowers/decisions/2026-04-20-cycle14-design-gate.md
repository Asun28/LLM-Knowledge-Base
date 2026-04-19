# Cycle 14 — Design Decision Gate (Step 5)

**Date:** 2026-04-20
**Resolver:** Primary Opus (main) per auto-approve feedback
**Inputs:** requirements.md, threat-model.md, brainstorm.md, R1 Opus review, R2 Codex review

## VERDICT

**APPROVE WITH AMENDMENTS.** 6 structural blockers + 3 dropped ACs (duplicates).

Both R1 and R2 agree AC5, AC11, AC14, AC18, AC20, AC21, AC23 require amendments. Additionally primary-session grep confirmed AC13/14/15 duplicate existing `detect_source_type` at `src/kb/ingest/pipeline.py:288` (already wired at line 888 when `source_type is None`).

## DROPPED ACs (already shipped)

- **AC13** (SOURCE_TYPE_INFERENCE_MAP) — inverse of `SOURCE_TYPE_DIRS` is computed inline at `pipeline.py:298` (`type_map = {v.name: k for k, v in SOURCE_TYPE_DIRS.items()}`). Adding a top-level constant is dead code.
- **AC14** (`_infer_source_type`) — `detect_source_type(source_path, raw_dir)` at `pipeline.py:288-301` already implements the contract (checks `rel.parts[0]`, matches `SOURCE_TYPE_DIRS`, raises `ValueError` on miss). Called at line 887-888 when `source_type is None`.
- **AC15** — tests for AC13/AC14 become moot.

Updated cycle scope: **21 AC** (was 24). Close BACKLOG "per-subdir ingest rules" entry with a pointer to `detect_source_type`.

## Decisions (Q1..Q20 resolved)

### Q1 (T2 publish filter scope)

**OPTIONS:**
- (a) filter `belief_state in {retracted, contradicted}` only
- (b) also filter `stale`
- (c) also filter `uncertain`
- (d) additionally filter `confidence: speculative`

**## Analysis**

The whole point of `belief_state: retracted` is "this claim is wrong". Publishing retracted content to external LLM training corpora defeats the vocabulary. `contradicted` means "internal contradiction found; not yet resolved" — also unfit for external consumption. `stale` means "source has aged past decay threshold" — this is a freshness signal, not a correctness signal, and external consumers may have their own freshness policies; filtering stale here would be paternalistic. `uncertain` is explicitly the "we don't know" bucket — this IS the appropriate epistemic status for many real claims, and filtering it would make `/llms.txt` look falsely authoritative.

`confidence: speculative` is the augment auto-ingest default (`_mark_page_augmented` forces it). These are stub pages enriched from web sources without human review — publishing them verbatim risks promoting unreviewed gap-fill as if it were curated KB content. The Phase 5.0 augment design explicitly marks them speculative "until human review" — the publish builders should respect that marker.

**DECIDE:** (a) + (d). Filter `belief_state in {retracted, contradicted}` AND `confidence == speculative`. Emit `[!excluded]` count footer. Do NOT filter `stale` or `uncertain`.
**RATIONALE:** correctness-class exclusion (retracted/contradicted) + unreviewed auto-augment exclusion (speculative). Freshness/uncertainty are advisory, not exclusion-worthy.
**CONFIDENCE:** high.

### Q2 / Q13 (T5 advisory echo)

**OPTIONS:**
- (a) fixed template with zero question content
- (b) parametrized template with question pre-sanitized to 200-char safe slug
- (c) parametrized with question verbatim

**## Analysis**

(c) is ruled out: T5 XSS/prompt-injection. (a) is safest; a fixed message "Coverage {score:.2f} below threshold; consider rephrasing your question or widening the search." carries the signal the user needs — score + remediation action. The question itself is echoed in the user's own terminal anyway; no need to re-echo it in a downstream-renderable advisory string.

The BACKLOG item (line 293) asks for "LLM-suggested rephrasings" — this implies a scan-tier LLM call to propose alternative phrasings. That's a separate AC with its own cost/latency profile, and adds a new integration surface. For cycle 14 we ship the gate + fixed template only; the LLM-rephrasing expansion moves to a new BACKLOG entry referencing this cycle.

**DECIDE:** (a) fixed template. Explicitly: `advisory = "Coverage {score:.2f} below threshold {QUERY_COVERAGE_CONFIDENCE_THRESHOLD:.2f}. Consider rephrasing or widening the query."` — contains no user input.
**RATIONALE:** T5 resolved by construction; LLM-rephrasing deferred with a new BACKLOG entry pointing at `query/engine.py`.
**CONFIDENCE:** high.

### Q3 / Q20 (T6 decay matcher)

**OPTIONS:**
- (a) exact hostname + dot-suffix match via `urllib.parse.urlparse(ref).hostname`
- (b) substring match on raw ref
- (c) also accept non-URL refs like `raw/articles/github.com-note.md`

**## Analysis**

R1 and R2 both flag T6 as critical. (b) is a known exploit. For (c): the helper's purpose is to inform `_flag_stale_results` on how long to honor a source; source_refs in this KB are predominantly `raw/articles/*.md` paths OR URLs from augment ingest. A path like `raw/articles/github.com-note.md` refers to a LOCAL file whose NAME happens to contain `github.com` — the freshness policy for that local file should NOT be github.com's 180-day window; it should be the default (90-day). Accepting (c) conflates filename with source origin.

The AC should specify: the helper extracts hostname via `urlparse(ref).hostname`. If ref has no scheme (e.g., `raw/articles/foo.md` or `github.com/foo/bar`), `urlparse` returns empty hostname — fall through to default. If ref has an IDN hostname, apply IDNA encoding before comparison. If ref has userinfo/port, `hostname` strips those.

**DECIDE:** (a). Parse via `urlparse`, normalize via IDNA (`idna.encode(host).decode("ascii")` with fallback to raw on error), match exact host OR `host.endswith("." + key)`. No substring matching. No non-URL ref handling.
**RATIONALE:** T6 resolved; conflation of file-path with source-origin avoided.
**CONFIDENCE:** high.

### Q4 / Q18 (T7 parent scan)

**OPTIONS:**
- (a) `path.parent.name` (immediate parent)
- (b) first path-part under resolved `raw_dir`
- (c) scan all path parts, first match wins

**## Analysis**

The existing `detect_source_type(source_path, raw_dir)` already implements (b) correctly: `rel = source_path.resolve().relative_to(effective_raw); first_part = rel.parts[0]`. It resolves symlinks first (so reparse points can't escape), checks containment (`relative_to` raises if outside), and uses the first path-part (so nested `raw/articles/captures/foo.md` correctly returns `article`, not `capture`).

This is one of the reasons AC13/14/15 are duplicates. The existing implementation is SECURELY correct.

**DECIDE:** N/A — AC13/14/15 dropped. Existing `detect_source_type` stays.
**RATIONALE:** already correct; see DROPPED ACs section.
**CONFIDENCE:** high.

### Q5 (T8 JSON-LD URL field)

**OPTIONS:**
- (a) POSIX relative to `wiki_dir`
- (b) `https://...` when a deployed wiki URL is configured
- (c) `file://...` absolute

**## Analysis**

(c) leaks filesystem. (b) adds a config dependency this cycle can avoid. (a) is the portable, spec-clean choice; external consumers can prefix with their own base URL.

**DECIDE:** (a) POSIX relative via `page_path.relative_to(wiki_dir).as_posix()`.
**RATIONALE:** minimal surface; T8 resolved by construction; consumers can prefix as needed.
**CONFIDENCE:** high.

### Q6 / Q17 (T9 status boost co-gate)

**OPTIONS:**
- (a) co-gate `status in (mature, evergreen) AND authored_by in (human, hybrid)`
- (b) no co-gate (trust the pipeline)
- (c) require `validate_frontmatter` to have passed at page-load time

**## Analysis**

The threat surface is "attacker lands PR with `status: mature`; poisoned page ranks higher". For THIS single-user KB the relevant threat is NOT a malicious external PR author — it's an LLM-extracted hallucination that set `status: mature` on a speculative page. That's a real risk: the augment auto-ingest path could silently promote stub pages.

The defensive cost of (a) is low: one extra dict lookup. Pages authored by the user's ingest pipeline will typically have `authored_by: llm` (the LLM wrote the page body via the ingest extractor). The user doesn't explicitly set `authored_by: human` today — no existing page has this field. So (a) defaults to "no boost ever" until we start setting `authored_by: human` for hand-authored pages. That's a reasonable zero-default: opt-in boost rather than opt-out.

But this creates a bootstrap problem: no existing page will receive the boost, which means AC23 ships no observable behavior change. The test passes, the code is dead for real wikis.

**DECIDE:** (b) no co-gate, BUT add a second guard: the boost only applies when `status` has passed `validate_frontmatter` AC2 validation (i.e., the value is in `PAGE_STATUSES`). For cycle 14, `authored_by` ships as vocabulary only with no ranking interaction; the co-gate can land in a later cycle if LLM-set `mature` becomes a real problem.
**RATIONALE:** avoids the bootstrap problem; `validate_frontmatter` path-gated boost limits the attack surface to "pages whose frontmatter is currently valid", which is what we want anyway. Document the tradeoff so the next cycle can revisit.
**CONFIDENCE:** medium. (If Step 9 testing reveals a path where invalid-value pages receive the boost, tighten to (a).)

### Q7 / Q15 (AC20 llms-full truncation granularity)

**OPTIONS:**
- (a) truncate mid-page at byte count, append `[TRUNCATED — {N} pages remaining]`
- (b) drop whole pages past cap, footer lists skipped page IDs
- (c) skip the page if adding it would exceed cap; always complete pages

**## Analysis**

Mid-page truncation (a) risks landing mid-codefence / mid-YAML / mid-wikilink, corrupting downstream parsers. (b) is cleanest but skips potentially relevant pages arbitrarily. (c) is page-level deterministic: before appending page N+1, check if `current_bytes + len(separator + header + body_utf8)` would exceed cap; if so, stop and emit footer.

For external LLM crawlers that consume `llms-full.txt`, getting the first 200 pages complete is more useful than getting 210 pages with 10 corrupted. Budget accounting in UTF-8 bytes (not Python chars) matches what the consumer will see.

**DECIDE:** (c). Cap in UTF-8 bytes including separators/footer/header overhead. Before appending page N, compute `prospective_bytes = current_bytes + len((separator + page_payload).encode("utf-8"))`; if prospective > cap, emit footer `[TRUNCATED — {skipped_count} pages remaining: {first_3_ids} ...]` and stop. If the FIRST page alone exceeds cap, include it truncated with an explicit `[!oversized page truncated at {N} bytes]` marker — partial delivery is better than empty output.
**RATIONALE:** page-level determinism + UTF-8 byte accounting; graceful first-page-oversize fallback.
**CONFIDENCE:** high.

### Q8 (AC22 kb publish regen vs diff)

**OPTIONS:**
- (a) regenerate all on every run
- (b) diff against existing file mtimes, skip unchanged

**## Analysis**

(b) adds complexity for a feature that runs on demand, not on every ingest. Builders are fast (single file scan). Shipping (a) is the simple baseline; incremental publish is a BACKLOG entry for a future cycle if perf becomes an issue.

**DECIDE:** (a). Regenerate unconditionally. Add a follow-up BACKLOG entry for incremental publish.
**CONFIDENCE:** high.

### Q9 (AC18 wrapper logging)

**OPTIONS:**
- (a) log before/after key order for debugging
- (b) ship clean

**## Analysis**

Logging every augment write adds noise to debug output. The wrapper is simple enough that a unit test catching order drift is sufficient.

**DECIDE:** (b) ship clean. Tests in `tests/test_cycle14_augment_key_order.py` cover the assertion.
**CONFIDENCE:** high.

### Q10 (AC23 boost magnitude)

**OPTIONS:**
- (a) inline `* 1.05` literal
- (b) new `STATUS_RANKING_BOOST = 0.05` constant in config.py

**## Analysis**

(b) keeps the tunable in one place; if future cycles need to widen/narrow, it's a one-line change. Negligible cost.

**DECIDE:** (b). Add `STATUS_RANKING_BOOST = 0.05` to config.py. Document it as "multiplicative boost factor for pages with `status in (mature, evergreen)`".
**CONFIDENCE:** high.

### Q11 / Q12 (AC5 use_api gate + coverage surface)

**Context:** R1 flagged that AC5 carves out `use_api=True`, contradicting the BACKLOG refusal-gate intent. R2 flagged `query_wiki` has no `use_api` parameter — it always calls `call_llm`. Checking engine.py:

Actually the `use_api` param lives in `mcp/browse.py::kb_query` as an MCP-tool flag — when False, the tool returns context for Claude Code to synthesize; when True, the tool forwards to `query_wiki` which always calls `call_llm`. So the "context-return path" R1 is referring to is the MCP `use_api=False` branch, which short-circuits before `query_wiki` is called.

**## Analysis**

For cycle 14, the pragmatic scope is: add the coverage-confidence computation INSIDE `query_wiki` (after `search_pages` returns and before `_build_query_context` packs). Surface the confidence score in the return dict ALWAYS (`coverage_confidence: float | None`), regardless of threshold. The gate-action (refusal) applies ONLY when the score is below threshold: the return dict gains `low_confidence: True` + `advisory: str` AND the `answer` field falls through a pre-configured refusal message instead of calling the synthesizer.

This applies to both MCP `use_api=True` (which calls `query_wiki` → `call_llm`) AND CLI `kb query` (which also calls `query_wiki`). The MCP `use_api=False` branch still short-circuits to Claude Code; we don't intervene there because Claude Code has its own judgment layer.

Implementation path:
1. `search_pages` returns `(results, telemetry)` — extend to include per-vector-hit cosine similarity in telemetry.
2. `query_wiki` after context packing computes `coverage_confidence = mean([vector_sim for page in ctx_pages if page has vector_sim])` or `None` if no vector hits packed.
3. If `coverage_confidence is not None and < QUERY_COVERAGE_CONFIDENCE_THRESHOLD`: skip `call_llm`; set `answer = "<refusal message referencing coverage and advisory>"`, `low_confidence = True`, `advisory = <fixed template>`.
4. Always include `coverage_confidence` in return dict (float or None).

**DECIDE:** coverage gate applies in `query_wiki` for both synthesis-bearing callers. Return dict ALWAYS carries `coverage_confidence: float | None`. Refusal triggers when score < threshold; refusal replaces `answer` with the fixed template. `vector_search` attaches `vector_similarity` to each hit; this is preserved through RRF fusion as a side-channel dict (not the `score` field).
**CONFIDENCE:** high. (Moderate complexity — requires `search_pages` signature extension but doesn't change existing callers.)

### Q14 (SOURCE_DECAY wire this cycle?)

**## Analysis**

R1 flagged that AC10/AC11 ship vocabulary without a consumer — "semi-fake" since the BACKLOG entry implies behavior change. However, wiring `_flag_stale_results` to per-platform decay is its own non-trivial change: `_flag_stale_results` currently uses `mtime_delta_days > STALENESS_MAX_DAYS`; switching to per-platform requires correlating each result's source to a ref (or domain), which means changes to the result-packaging path. That's another ~50-80 lines of code + tests.

Cycle 14 is already at 21 AC. Shipping vocabulary-only here with an explicit BACKLOG follow-up is defensible IF the BACKLOG entry stays open (AC26 amendment below).

**DECIDE:** ship vocabulary only (AC10/AC11). Do NOT delete the BACKLOG SOURCE_DECAY entry in AC26. Add new BACKLOG LOW entry: "wire `decay_days_for` into `_flag_stale_results` and lint staleness scan — cycle 15 target".
**RATIONALE:** scope control; prevents half-implementation risk.
**CONFIDENCE:** high.

### Q16 (AC16 wrapper signature)

**OPTIONS:**
- (a) rigid `sort_keys=False` inline
- (b) optional `sort_keys: bool = False` param

**## Analysis**

T4 argues for rigidity: if the flag is tunable, a future refactor may flip it to True "for alphabetization" and regress the evidence-trail sentinel. (a) is the safer interface contract.

**DECIDE:** (a) rigid. Wrapper body is literally `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)`. No parameters.
**CONFIDENCE:** high.

### Q17 (AC2 validate_frontmatter WARN vs ERROR)

**## Analysis**

Existing `validate_frontmatter` returns a list of ERRORS (hard). Switching new fields to warnings would break consistency. ERROR is correct — pages with invalid `belief_state` / `authored_by` / `status` should surface in lint output.

**DECIDE:** ERROR for invalid values. Absent fields remain silent (backwards compatible).
**CONFIDENCE:** high.

### Q19 (AC16 wrapper cache clear)

**## Analysis**

`load_page_frontmatter` is LRU-cached keyed by (path, mtime_ns). On filesystems with coarse mtime (FAT32, SMB, OneDrive), a write-immediately-followed-by-read can see stale cached metadata. The wrapper could call `load_page_frontmatter.cache_clear()` after every write — but that flushes ALL cached entries, not just the one path. The canonical fix is to use `cache_clear_for(path)` if the cache supports it, which `functools.lru_cache` does NOT.

For cycle 14, the augment write-back sites are the three callers (`_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`). None of them read the same page via `load_page_frontmatter` immediately after write — `_post_ingest_quality` DOES read, but cycle-13 AC2 already annotates it as using UNCACHED `frontmatter.load` for exactly this reason. So the cache-drift risk does not materialize in the augment flow.

**DECIDE:** no cache clear in the wrapper. Document in wrapper docstring: "after writing, same-process readers via `load_page_frontmatter` may see stale metadata on coarse-mtime filesystems until the mtime advances. Use `frontmatter.load(path)` directly if you need post-write read consistency."
**CONFIDENCE:** high.

## AMENDED ACCEPTANCE CRITERIA (final, post-gate)

### Metadata frontmatter fields

- **AC1** — `src/kb/config.py` adds three tuples: `BELIEF_STATES = ("confirmed", "uncertain", "contradicted", "stale", "retracted")`, `AUTHORED_BY_VALUES = ("human", "llm", "hybrid")`, `PAGE_STATUSES = ("seed", "developing", "mature", "evergreen")`.
- **AC2** — `validate_frontmatter` accepts absent optional fields; when present, rejects invalid values with one error per invalid field. `None` or empty-string values for a present optional field are INVALID.
- **AC3** — test coverage per AC2.

### Query coverage-confidence gate

- **AC4** — `src/kb/config.py` adds `QUERY_COVERAGE_CONFIDENCE_THRESHOLD = 0.45`.
- **AC5 (amended)** — `src/kb/query/engine.py` changes:
  - `vector_search` attaches `vector_similarity: float` to each hit.
  - `search_pages` returns per-page vector_similarity via a side-channel (parallel dict `vector_scores_by_id`) — does NOT modify the `score` field.
  - `query_wiki` computes `coverage_confidence: float | None = mean(vector_similarity for page in ctx_pages if in vector_scores_by_id) or None`.
  - Return dict ALWAYS includes `coverage_confidence` (float or None).
  - If `coverage_confidence is not None and < threshold`: skip `call_llm`; set `answer = "<fixed refusal template>"`, `low_confidence = True`, `advisory = <fixed template from Q2>`.
  - Gate applies to all `query_wiki` callers (CLI + MCP `use_api=True`). MCP `use_api=False` (context-only) path is unchanged.
- **AC6** — test coverage.

### CONTEXT_TIER1 split + per-platform decay (vocabulary only)

- **AC7** — `CONTEXT_TIER1_SPLIT = {"wiki_pages": 60, "chat_history": 20, "index": 5, "system": 15}`.
- **AC8** — `tier1_budget_for(component: str) -> int` helper. Invalid component → `ValueError`.
- **AC9** — test coverage.
- **AC10** — `SOURCE_DECAY_DAYS: dict[str, int]` with the six documented hosts. `SOURCE_DECAY_DEFAULT_DAYS = STALENESS_MAX_DAYS`.
- **AC11 (amended)** — `decay_days_for(ref: str | None) -> int`:
  - `None`/empty/no-scheme → default.
  - Parse via `urllib.parse.urlparse`, get `.hostname`, apply IDNA encode (fallback to raw on error).
  - Exact hostname OR `host.endswith("." + key)` match; first match in `SOURCE_DECAY_DAYS` (ordered dict).
  - No substring match.
- **AC12** — test coverage including `arxiv.org.evil.com`, `github.com:443`, IDN host, bare domain.

### Dropped ACs 13/14/15

(see DROPPED ACs section above)

### Frontmatter save wrapper

- **AC16 (amended)** — `src/kb/utils/pages.py::save_page_frontmatter(path: Path, post: frontmatter.Post) -> None` — single-line body: `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)`. Docstring notes: (i) preserves insertion-order of metadata keys; (ii) does NOT clear `load_page_frontmatter` cache; (iii) LF line endings per `atomic_text_write` contract.
- **AC17** — test coverage: insertion-order preservation for 3+ non-alphabetical keys; body content verbatim (incl. trailing newline); list-valued metadata order preserved.

### Augment write-back migration

- **AC18 (amended)** — `src/kb/lint/augment.py` migrates the three sites to use `save_page_frontmatter`. Comments updated to reference cycle-14 AC18 and the sort_keys=False guarantee. Post-migration grep `frontmatter\.dumps\(` in `lint/augment.py` → every hit must be inside a `save_page_frontmatter` call (zero bare hits).
- **AC19** — test coverage: each of the three sites preserves key insertion order; pre-existing `wikilinks: [...]` metadata survives round-trip; non-alpha custom fields preserved.

### Publish outputs

- **AC20 (amended)** — new module `src/kb/compile/publish.py`:
  - `build_llms_txt(wiki_dir, out_path)` — one line per page `title — source_ref — updated_iso` under type headers; skip pages with `belief_state in {retracted, contradicted}` OR `confidence == speculative`; title/source newlines collapsed; emit `[!excluded] N pages` footer.
  - `build_llms_full_txt(wiki_dir, out_path)` — UTF-8 byte-capped at 5 MiB including separators/footer/headers; page-level deterministic stop (complete pages only; if first page alone exceeds cap, include it with `[!oversized]` marker); same filter as llms.txt.
  - `build_graph_jsonld(wiki_dir, out_path)` — uses `json.dump(obj, f, ensure_ascii=False, indent=2)` with fully-constructed dict. `@context = "https://schema.org/"`. Each node: `@type = "CreativeWork"`, `name = title`, `url = page_path.relative_to(wiki_dir).as_posix()`, `dateModified = updated`, `citation = [relative URLs to linked pages]`. Same filter. Allowlist node fields (only named fields; never splat metadata).
  - All builders call `load_all_pages(include_content_lower=False)` or use `scan_wiki_pages + load_page_frontmatter` for streaming.
- **AC21 (amended)** — `src/kb/cli.py` `publish` subcommand:
  - `--out-dir` defaults to `PROJECT_ROOT/outputs`.
  - Resolve `--out-dir`: if `is_relative_to(PROJECT_ROOT)` pass, else require the directory to already exist on disk (operator-managed); otherwise `click.UsageError`. Reject UNC paths, `..` containing paths explicitly.
  - `--format` one of `llms|llms-full|graph|all`; default `all`.
- **AC22** — test coverage: (i) filter retracted/contradicted/speculative; (ii) out-dir containment; (iii) JSON-LD parses as valid JSON with schema.org context; (iv) url fields are relative POSIX; (v) oversized first page marker; (vi) empty wiki produces valid empty outputs; (vii) title with `"`, `\n`, `\u2028` survives JSON round-trip.

### Status ranking boost

- **AC23 (amended)** — `src/kb/query/engine.py` applies `score *= (1 + STATUS_RANKING_BOOST)` where `STATUS_RANKING_BOOST = 0.05` (new config constant, Q10) when page's `status in ("mature", "evergreen")` AND the value passed `validate_frontmatter` (Q6). No `authored_by` co-gate this cycle. Boost applied AFTER RRF fusion and BEFORE `dedup_results` (per R2 note: apply before dedup only with explicit tests for type-diversity interaction). Tests exercise tie-breakers for determinism.
- **AC24** — test coverage: (a) two otherwise-equal pages, one `status: mature` → boosted ranks first; (b) `status: seed` no boost; (c) invalid `status` value no boost; (d) `status: mature` with OTHER metadata corrupt (validation fails) → no boost; (e) tie-breaker determinism.

### Documentation

- **AC25** — CHANGELOG.md `[Unreleased]` Phase 4.5 cycle 14 section.
- **AC26 (amended)** — BACKLOG.md deletes:
  - `belief_state frontmatter` (HIGH LEVERAGE Epistemic Integrity 2.0)
  - `authored_by frontmatter` (HIGH LEVERAGE Epistemic Integrity 2.0)
  - `status frontmatter` — KEEP open. AC23 closes only the ranking-boost sub-ask; the `kb_evolve targets seed` and `lint flags mature > 90d` sub-asks remain. Rewrite the entry to note "ranking boost shipped in cycle 14; evolve + lint sub-asks still open."
  - `coverage-confidence refusal gate` (HIGH LEVERAGE Epistemic Integrity 2.0) — AC5 closes it.
  - `/llms.txt + /llms-full.txt + /graph.jsonld` (HIGH LEVERAGE Output-Format Polymorphism + Tier-1 recommended) — AC20-AC22 close it.
  - `per-subdir ingest rules` (HIGH LEVERAGE Ambient Capture) — close with a pointer to `detect_source_type`.
  - `frontmatter write-back migration` (cycle-14-target MEDIUM) — AC18 closes it.
  - NEW BACKLOG entries to ADD:
    - `CONTEXT_TIER1_BUDGET split helper wired but no call-site migration — cycle 15 target.` (AC7/AC8 vocabulary-only)
    - `decay_days_for helper wired but not consumed by _flag_stale_results / lint staleness scan — cycle 15 target.` (AC10/AC11 vocabulary-only)
    - `status frontmatter: kb_evolve should target seed pages; lint should flag mature pages not updated in 90+ days.` (AC23 partial-close)
    - `kb_query low-coverage advisory should optionally include LLM-suggested rephrasings (scan-tier call).` (AC5 partial-close)
    - `kb publish should diff against existing file mtimes and skip unchanged.` (incremental publish)
- **AC27** — CLAUDE.md notes for new frontmatter fields, `kb publish` command, and `save_page_frontmatter` utility.

## CONDITIONS (Step 11 checklist generated from Step 5)

1. **T1 verified:** grep `cli.py::publish` for `resolve()` + `is_relative_to(PROJECT_ROOT)` + `UsageError`; unit test `--out-dir=/tmp/outside-root` raises.
2. **T2 verified:** grep all three publish builders for the belief_state/confidence filter; unit test seeds wiki with retracted + contradicted + speculative → absent from all three outputs.
3. **T3 verified:** grep `build_graph_jsonld` for `json.dump` (present) and absence of `f'"` / `.format(` in the function body; test titles with `"`, `\n`, `\u2028`, `]`, `},{` round-trip via `json.loads`.
4. **T4 verified:** `Read` the `save_page_frontmatter` wrapper — must contain `sort_keys=False` AND `atomic_text_write`; unit test key-order preservation for 3+ non-alpha keys.
5. **T5 verified:** grep `query/engine.py` advisory string for interpolation of `question` var → must be absent; unit test question = `<script>alert(1)</script>` → advisory contains no `<script>`.
6. **T6 verified:** grep `decay_days_for` for `urlparse` + `endswith("." +`; unit tests for arxiv.org.evil.com → default; arxiv.org → arxiv; sub.arxiv.org → arxiv; IDN; port.
7. **T7 verified:** N/A (AC13-15 dropped; existing `detect_source_type` already correct).
8. **T8 verified:** grep `build_graph_jsonld` for `relative_to(wiki_dir).as_posix()` on url field; unit test with tmp wiki under `/tmp/foo` → output contains no `/tmp/foo` substring.
9. **T9 verified:** grep AC23 ranking site for `validate_frontmatter`-gated boost; unit test case (c) invalid status → no boost.
10. **T10 verified:** `grep -nE "frontmatter\.dumps\(" src/kb/lint/augment.py` → every hit inside `save_page_frontmatter(` call; `grep -nE "sort_keys" src/kb/lint/augment.py` → zero literal hits.

## Signature-drift check (Q11 residual)

`search_pages` signature will extend from `(results, telemetry)` (implicit) to include `vector_scores_by_id`. Must grep all callers:

```bash
grep -rn "search_pages(" src/ tests/
```

and confirm every caller either unpacks the new return shape OR the function returns a dict that additively gains the new key.

**DECIDE:** use a result class / dict expansion pattern — `search_pages` returns a dict where new keys are added-only. Preferred: a dataclass `SearchResult(results, telemetry, vector_scores_by_id)` if one doesn't exist, OR a dict with documented keys. Flag in Step 7 plan; Step 11 verifies no caller is broken by the signature change.

## FINAL DECIDED DESIGN

- **21 ACs (from 24):** AC1-AC12, AC16-AC24 (dropping AC13/14/15).
- **10 Conditions (Step 11 checklist):** above.
- **5 new BACKLOG entries:** tracked for cycle 15+.
- **1 signature drift (search_pages):** gated at Step 11.
- **Threat model fully incorporated:** T1 (AC21), T2 (AC20 Q1), T3 (AC20 json.dump), T4 (AC16 Q16), T5 (AC5 Q2), T6 (AC11 Q3), T7 (dropped), T8 (AC20 Q5), T9 (AC23 Q6), T10 (AC18 verification grep).

Proceed to Step 6 (Context7) — only `frontmatter.dumps(sort_keys=...)`, `json.dump(ensure_ascii=...)`, and `urllib.parse.urlparse` need confirmation. All stdlib or already-used.
