# Cycle 8 — Threat Model (Opus subagent)

**Date:** 2026-04-18
**Dep-CVE baseline:** 0 open Dependabot alerts (captured to
`/tmp/cycle-8-alerts-baseline.json`). `pip-audit` requirements.txt resolver
conflict documented below; `--installed` fallback used instead.

## Analysis

Cycle 8 is dominated by low-risk surface-polish work (`__init__` re-exports,
docstring edits, a telemetry INFO log, a validator helper, enum guards on a
dataclass). Four ACs touch real surfaces: (a) `wiki_dir: str | None` kwarg
added to `kb_stats` and `kb_verdict_trends` (MCP input → filesystem path),
(b) `_validate_notes(notes, field_name)` helper unified across
`kb_query_feedback` + `kb_refine_page`, (c) `_persist_contradictions`
idempotency check (compares same-day same-source headers), and (d)
PageRank-as-rank-list input to RRF fusion in `query_wiki`.

The `_make_api_call` INFO log adds a new sink for LLM telemetry that MUST
NOT carry prompt content (Item 7 in cycle 2 already truncates error messages
to 500 chars precisely because Anthropic echoes prompts into error bodies —
the same discipline applies to the new success path).

Regression risk concentrates in three places: (1) `wiki_dir` kwarg must
reuse the `Path(wiki_dir) if wiki_dir else None` pattern that
`kb_lint`/`kb_evolve` use — a raw `os.path.join` or string concat admits
traversal via `../../raw/secrets.md`; (2) the `_persist_contradictions`
"same-day same-source header" check MUST run INSIDE `file_lock()` or two
concurrent ingests will both miss the header and both append; (3)
`from_post(post, path)` must not trust `post.metadata.get("source")`
verbatim — that field originates in LLM-extracted frontmatter and can
contain `../../../etc/passwd` strings; the existing `normalize_sources`
helper is the correct sanitiser.

## Trust Boundaries

1. **MCP client → `kb_stats(wiki_dir=...)` / `kb_verdict_trends(wiki_dir=...)`**
   — new attacker-controlled path input.
2. **MCP client → `kb_query_feedback(notes=...)` / `kb_refine_page(revision_notes=...)`**
   — existing boundary, consolidation must preserve current caps.
3. **LLM output (frontmatter on disk) → `WikiPage.from_post()`** — disk
   frontmatter is LLM-emitted text; validators run on whatever the LLM
   wrote.
4. **Extracted contradiction claims → `wiki/contradictions.md`** — already
   sanitised upstream via `sanitize_extraction_field`; idempotency skip
   path must not be tricked into suppressing legitimate new
   contradictions.
5. **Telemetry sink → stdout/stderr via `logger.info`** — new output
   channel for `_make_api_call`; must not leak prompt/response content.

## Threat Items

- **T1 — `wiki_dir` traversal (source: MCP client):** Attacker passes
  `wiki_dir="../raw"` or `wiki_dir="/etc"` to read files outside project.
  **Defense:** when non-None, resolve to `Path(wiki_dir).resolve()` and
  require `relative_to(PROJECT_ROOT.resolve())`; match `kb_lint`'s
  pattern at `mcp/health.py:58`.
- **T2 — `_validate_notes` cap bypass (source: MCP client):** Helper
  defaulting to different cap than prior in-place checks silently accepts
  longer input. **Defense:** use `MAX_NOTES_LEN` from `kb.config`; both
  call sites' order (check → strip → validate) preserved.
- **T3 — `_validate_notes` field_name CRLF injection (source: caller bug):**
  `field_name` user-supplied interpolation injects CRLF into MCP response.
  **Defense:** `field_name` MUST be a compile-time literal (`"notes"` /
  `"revision_notes"`); never pass user value.
- **T4 — `_persist_contradictions` idempotency race (source: bug):** Read
  outside `file_lock(contradictions_path)` = two concurrent ingests both
  miss, both append. **Defense:** existence check MUST run INSIDE the
  existing `with file_lock(contradictions_path)` block, after
  `existing = ... .read_text(...)`, before `atomic_text_write`.
- **T5 — Header-match suppression (source: attacker-controlled source_ref):**
  Substring match on `safe_ref` alone lets an attacker-named source like
  `foo — 2026-04-18` suppress unrelated real contradictions. **Defense:**
  match the FULL normalised header line `## {safe_ref} — {date}`.
- **T6 — `from_post` traversal/control-char injection (source: on-disk
  frontmatter):** LLM hallucination produces `source: ["../../../etc/passwd"]`
  or embeds BIDI marks in `title`. **Defense:** `from_post` MUST
  delegate source parsing to `normalize_sources` (strips traversal);
  `__post_init__` rejects unknown `page_type`/`confidence`; `title`
  stripped of control chars.
- **T7 — Enum validator DoS on legacy pages (source: bug):** Raising
  `ValueError` on unknown enum aborts `load_all_pages` scan. **Defense:**
  `__post_init__` raises `ValueError`; every call site that instantiates
  via `from_post` MUST catch `ValueError` and skip-log (per CLAUDE.md
  "page loading loops" convention). Existing `load_all_pages` at
  `utils/pages.py` does NOT invoke `WikiPage` — it returns dicts — so this
  risk materialises only when a downstream caller adopts `from_post`.
- **T8 — `_make_api_call` INFO log prompt leak (source: bug):** Success
  log that references `kwargs["messages"]` or `response.content` leaks
  prompt/response text. **Defense:** restrict log to `model`, `attempt`,
  `tokens_in`, `tokens_out`, `latency_ms`; tokens from
  `response.usage.input_tokens` / `output_tokens`; test asserts log
  record's args contain no substring from messages/system.
- **T9 — PageRank rank-list collision (source: internal):** Rank list
  built from unfiltered `pages` with attacker-controlled IDs could
  collide with BM25 IDs. **Defense:** rank list keyed on `id.lower()`
  parity with existing `_compute_pagerank_scores`.
- **T10 — `__all__` over-exposure (source: bug):** Typo in `__all__`
  exports internal helper. **Defense:** limit to names in scope; each
  already public (no leading `_`).

## Verification Checklist for Step 11

1. `kb_stats(wiki_dir=...)` and `kb_verdict_trends(wiki_dir=...)` reject
   traversal (`..`, absolute paths outside PROJECT_ROOT).
2. Both tools use `Path(wiki_dir) if wiki_dir else None` pattern matching
   `mcp/health.py:58`.
3. `_validate_notes` defined in `kb/mcp/app.py` (shared layer).
4. `_validate_notes` uses `MAX_NOTES_LEN` from `kb.config`.
5. `_validate_notes` strips control chars before length check.
6. Call sites in `core.py::kb_query_feedback` + `quality.py::kb_refine_page`
   pass literal `field_name` strings.
7. `_persist_contradictions` idempotency check reads inside
   `with file_lock(...)` (pipeline.py:168).
8. Idempotency header match uses FULL `## {safe_ref} — {date}` line.
9. `WikiPage.__post_init__` raises `ValueError` on unknown
   `page_type`/`confidence`; `RawSource.__post_init__` on unknown
   `source_type`.
10. `from_post` routes `source:` through `normalize_sources`.
11. `from_post` strips control characters from `title`.
12. `_make_api_call` INFO log references ONLY `model`, `attempt`,
    `tokens_in`, `tokens_out`, `latency_ms` — no messages/system/kwargs/
    response text.
13. Tokens read from `response.usage.input_tokens` /
    `response.usage.output_tokens`; fallback 0 when absent.
14. Log emitted only on success path.
15. Test asserts log record contains no substring of the prompt.
16. PageRank rank-list keyed on `id.lower()`.
17. `rrf_fusion` receives PageRank as separate list (not post-fusion
    multiply).
18. `src/kb/__init__.py` `__all__` = 8 names; no underscored names.
19. `src/kb/utils/__init__.py` `__all__` = 15 names.
20. `src/kb/models/__init__.py` `__all__` = `["WikiPage", "RawSource"]`.
21. `build_consistency_context` auto mode caps total groups at
    `MAX_CONSISTENCY_GROUPS = 20`.
22. Per-page body truncated at `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096`
    ONLY in auto mode.
23. `kb_lint_consistency` docstring documents cap behaviour.
24. Regression: same top-K result set when `PAGERANK_SEARCH_WEIGHT = 0`.

## Data Classification

- **User input (MCP tool args):** `wiki_dir` kwarg for
  `kb_stats`+`kb_verdict_trends`; `notes`/`revision_notes`.
- **LLM output:** frontmatter parsed by `from_post`; contradiction claims.
- **Filesystem paths:** `wiki_dir` kwarg; `path` arg of `from_post`.
- **Internal-only:** `__all__` re-exports, `to_dict()`, PageRank rank-list,
  new config constants, consistency docstring.
- **Telemetry:** `_make_api_call` INFO log.

## Logging / Audit Requirements

- **`_make_api_call` INFO log MUST** log `model/attempt/tokens_in/tokens_out/latency_ms`. MUST NOT log messages/system/kwargs/response text.
- **`_validate_notes` MUST NOT** log the full `notes` body on rejection — include length only.
- **`_persist_contradictions` skip path MUST** log at DEBUG with `safe_ref` + date only — no claim bodies.
- **`kb_stats`/`kb_verdict_trends` rejection MUST** use `_sanitize_error_str`.
- **PageRank rank-list change MUST NOT** introduce new logging.

## Dep-CVE Baseline (Class A tracking)

- Dependabot open alerts: **0** (`/tmp/cycle-8-alerts-baseline.json`).
- pip-audit vs requirements.txt: **RESOLVER CONFLICT** (requests==2.33.0
  vs line 16). Not a CVE — baseline noise. Use `--installed` fallback in
  Step 11.5 fresh read.
- No Class B (PR-introduced) changes expected — cycle 8 adds no new deps.
