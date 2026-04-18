# Cycle 9 Threat Model (2026-04-18)

Scope: 31 AC across 16 files — backlog-by-file cleanup cycle.
Cross-ref: `docs/superpowers/decisions/2026-04-18-cycle9-requirements.md`.

## Analysis

Cycle 9 is a cleanup batch, not a feature cycle. Almost every AC either (a) plugs
leakage of an existing trust boundary that was already declared — `wiki_dir`
override (AC1-5, AC6, AC28), case-insensitive page match (AC9), oversize source
reject (AC7-8), `_normalize_for_scan` exception scope (AC14); or (b) tightens
observability and naming without touching on-disk layout or MCP wire format —
AC15-20, AC25-27, AC29-31. The one item with real defensive substance is AC24
(LLM error redaction), and it is *additive* to the existing
`_sanitize_error_str` path-redactor in `src/kb/mcp/app.py:84` — not a
replacement. AC11's augment summary is a reporting-only semantics fix, not a
policy change. AC10 is a resilience fix mirroring cycles 3/5/7 OSError widening
(precedent already shipped). Net new attack surface introduced by this cycle is
approximately zero: no new MCP tools, no new routes, no new file writers, no
new network paths, no new LLM prompt sites.

The largest blast radius in cycle 9 lives in the `query_wiki` / `search_pages`
hot path (AC1-3, AC28) because those four ACs collectively rewire how
custom-`wiki_dir` callers resolve vector index, feedback, and raw-fallback
locations. A regression here would NOT corrupt data — it would silently read
from the wrong directory, producing stale results or trust scores that mix the
override session's feedback with the production DB. Because cycle 6/7/8 already
shipped `wiki_dir` plumbing for `kb_lint`, `kb_evolve`, `kb_stats`,
`kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`, this cycle is
completing an existing migration rather than starting a new one. The second-
largest blast radius is AC14 (broadening `_normalize_for_scan`'s except to
`Exception`): this runs on every capture call before the secret scanner sees
normalized text. Without preserved logging the change trades a narrow-except
crash for a silent pass-through — a secret scanner that falsely reports "clean"
because a decoding path died mid-sweep is materially worse than one that
crashes loudly. The mitigation is writing a `logger.debug` alongside the
`continue`. Smallest-blast items are AC15, AC17, AC20, AC25, AC30, AC31 — all
doc / rename / import-ordering churn with near-zero behavioural surface.

## Trust boundaries

- **T1: MCP tool surface (FastMCP → Claude Code client)** — AC6 (kb_compile_scan
  wiki_dir), AC7/8 (kb_ingest / kb_ingest_content oversize reject at the
  boundary before the LLM fires), AC9 (kb_read_page ambiguity), AC11
  (run_augment summary semantics). These tools MUST return `"Error: ..."`
  strings, not raise, per `src/kb/mcp/app.py` contract.
- **T2: Filesystem path isolation when `wiki_dir` overridden** — AC1 (search
  `vec_path`), AC2 (`_flag_stale_results` root), AC3 (`kb_query`
  `_hybrid_configured` gate), AC28 (`search_raw_sources` `raw_dir`), AC4/5
  (feedback path in kb_lint / kb_evolve). Current code hard-codes
  `PROJECT_ROOT / VECTOR_INDEX_PATH_SUFFIX` at `src/kb/query/engine.py:131` and
  `:756`, and `path=None` to `get_flagged_pages` in `src/kb/mcp/health.py:71` —
  both evaluate the global `PROJECT_ROOT` regardless of the passed `wiki_dir`.
- **T3: Concurrency / cross-process write** — AC10 (`load_manifest` widens
  exception handler). NO new locks introduced this cycle; T3 tightens
  crash-recovery not concurrency.
- **T4: LLM prompt injection / capture input** — AC14-19 (capture.py), AC21
  (yaml_escape round-trip tests guarding future regressions), AC24
  (`_make_api_call` secret redaction BEFORE truncation in
  `src/kb/utils/llm.py:171,238`). AC18's encoding-label split is an
  observability hardening — operators need to know if a secret was found via
  base64 vs URL-encoded to tune the scanner.
- **T5: Package/module boot time** — AC27 (lazy `__getattr__` for
  `ingest_source` in `src/kb/ingest/__init__.py`). Mirrors cycle 8 AC30
  pattern in `src/kb/__init__.py:17` that preserves `kb --version` fast-path.
- **T6: Lint/query performance / correctness** — AC12 (avoid double YAML parse
  in `check_source_coverage`), AC13 (backlinks resolver consistency with
  `build_graph`'s slug_index). AC13 in particular is a CORRECTNESS boundary:
  the same `[[foo]]` wikilink is resolved by `build_graph`
  (`src/kb/graph/builder.py:61-65` slug_index fallback) and by `build_backlinks`
  (`src/kb/compile/linker.py:137,159` exact-match only). Today a bare slug
  that resolves via slug_index in the graph shows as "orphan" in evolve — AC13
  aligns the two.
- **T7: Documentation drift** — AC25 (instructions block alpha-sort), AC26
  (cli imports), AC31 (.env.example wording). Zero runtime impact.

## Data classification

For each AC, classify inputs / outputs / flow:

- **Private (never leaves machine):** MCP tool args from Claude Code, local
  `raw/` files, local `wiki/` files, `.data/feedback.json`, `.data/verdicts.json`,
  `.data/hashes.json`, `.data/vector_index.db`.
- **External writes:** Anthropic API prompt payload ONLY in `use_api=True`
  paths (kb_ingest, kb_query, kb_compile) + scan-tier LLM payload in
  `kb.capture._extract_items_via_llm` (the verbatim-verify gate at
  `capture.py:327-351` + the AC24 redactor limit exposure to API prose
  via `_make_api_call` error surface). `pip-audit` / dependabot scans are
  read-only GitHub API; no code-path change in cycle 9.
- **Log output:** `wiki/log.md`, `raw/captures/*.md` (user-consented), `.data/`
  JSON stores, Python `logger` (stderr when running under MCP; file on CLI).

Per-AC override-path widening:
- **AC4/5** (feedback path): without the fix, `kb_lint(wiki_dir=/tmp/test)`
  currently reads `PROJECT_ROOT/.data/feedback.json` — production trust data
  leaks into a test-harness report. Fix narrows scope.
- **AC1/2/3/28** (query engine): without the fix,
  `query_wiki(wiki_dir=/tmp/test)` reads production vector DB. Silent
  cross-corpus contamination in search results — NOT a security leak (both
  corpora are local), but a correctness leak that could surface stale answers
  containing production wiki content when testing against an isolated
  `tmp_project`.
- **AC24** (LLM error redaction): the direction is narrowing, not widening —
  secrets in an `anthropic.APIStatusError.message` body currently flow
  verbatim into `LLMError(...)` and thence into MCP-tool response strings
  (truncated at 500 chars but still raw). Redaction eliminates that leak.

## Authn / authz

- Single-user project; no auth surface added or changed this cycle.
- AC24 redaction-list sanity check (grep against `src/kb/utils/llm.py`
  `_make_api_call`, current lines 127, 171, 238):
  - `str(e.message)` → `truncate(..., limit=500)` → `LLMError` — the fix must
    run REDACTION before `truncate()` or a secret spanning the truncation
    boundary can be split-preserved. The AC wording already specifies "BEFORE
    truncating" — correct ordering.
  - Secret prefixes the project legitimately holds / sees:
    - `sk-ant-` (Anthropic) — holds in .env, receives in API errors echoing
      Authorization header on malformed proxies.
    - `sk-` (legacy OpenAI) — listed in `.env.example:10`, optional.
    - `Bearer ` tokens — any HTTP fetch error body passthrough in
      `kb.lint.augment` (but that path has its own scanner; the llm.py fix is
      for Anthropic errors specifically).
    - Base64 blobs ≥40 chars — service-account JSON, JWT payloads.
    - Long hex blobs ≥32 chars — UUIDs and session IDs; this is the
      false-positive risk class. The AC pattern `≥32` is conservative; flag
      as low-risk since the redacted output is STILL useful to the user (they
      see `[REDACTED:HEX]` and know structure was present).
  - AC24 is ADDITIVE to `_sanitize_error_str` in `src/kb/mcp/app.py:91` —
    the app-layer sweep handles filesystem paths; the llm-layer sweep will
    handle secret tokens. Different axes, no duplicate logic.

## Logging / audit

- **AC11** (augment summary): the current summary line at
  `src/kb/lint/augment.py:906-912` computes Saved / Skipped / Failed by
  iterating the `fetches` list (one entry per URL attempt). For a two-URL
  stub that fetched URL-A → fail, URL-B → success, this produces
  `Saved: 1, Failed: 1` — misleading. AC11 requires collapsing to per-stub
  outcome. MUST keep per-URL detail in the manifest (the manifest IS the
  audit ledger); the summary line is a human-readable TLDR. Confirm via test:
  after fix, `manifest.entries[stub_id]` still contains URL-level rows.
- **AC14** (`_normalize_for_scan` broaden to `except Exception`): the current
  code at `src/kb/capture.py:211-212` catches `(ValueError, binascii.Error,
  UnicodeDecodeError)` and `continue`s. AC14 broadens to bare `Exception`.
  The risk is silent failure: a future `MemoryError` on a 50 KB payload, or a
  new regex engine bug that raises `IndexError`, would be swallowed without
  signal. Mitigation: the broadened except MUST add
  `logger.debug("normalize-for-scan skipped %s: %s", kind, e)` so operators
  can see the pattern in practice. Without the log line, AC14 trades safety
  for robustness — verify Step 9 implementation keeps observability.
- **AC29** (stripped body in `_verify_body_is_verbatim`): trimming `body`
  from `body.strip()` removes leading/trailing whitespace. Audit risk is
  zero — the body is still verbatim relative to the input (a substring
  test passes on both the raw and the stripped form if the stripped form is
  non-empty and in content). The `source: mcp-capture` provenance tag is
  unchanged. Capture frontmatter already records `captured_from: {provenance}`
  so traceability is preserved.

## Per-AC verification checklist for Step 11

| AC | Threat item(s) | Verification | Scoped-out same-class sites |
|---|---|---|---|
| AC1 | T2 wiki_dir isolation — search vec_path | Write a test that seeds `tmp_wiki/.data/vector_index.db` AND `PROJECT_ROOT/.data/vector_index.db` with different content; call `search_pages(q, wiki_dir=tmp_wiki)`; assert results come from tmp DB. | No other `vec_path` call sites outside `kb.query.engine` / `kb.query.embeddings` — grep `_vec_db_path` / `VECTOR_INDEX_PATH_SUFFIX`: exactly 7 hits, already covered by AC1+AC3. |
| AC2 | T2 — stale-flag root under override | Test: temp project with a `raw/foo.md` newer than wiki page's `updated:`; call `search_pages(..., wiki_dir=tmp_wiki)`; assert result.stale=True computed against TMP raw, not PROJECT_ROOT raw. | No other caller of `_flag_stale_results` outside `search_pages`. Cycle 4 already threaded `root` parameter; only the call site at engine.py:214 needed wiring. |
| AC3 | T2 — kb_query hybrid gate | Test: `query_wiki(wiki_dir=tmp_wiki)` where tmp has NO vector DB but PROJECT_ROOT HAS one — assert `search_mode == "bm25_only"`. Mirrors AC1. | Same as AC1 — no other hard-coded `PROJECT_ROOT/VECTOR_INDEX_PATH_SUFFIX` usage. |
| AC4 | T2 — kb_lint feedback_path scope | Test: write prod `.data/feedback.json` with a low-trust page; call `kb_lint(wiki_dir=tmp_wiki)` where tmp has no feedback; assert report has NO "Low-Trust Pages" section. | `kb_review_page`, `kb_refine_page`, `kb_reliability_map`, `kb_query_feedback` also touch feedback — those use their own wiki_dir paths via the same pattern. Scope is limited to AC4+AC5 in this cycle. Other MCP sites remain OPEN. |
| AC5 | T2 — kb_evolve coverage_gaps scope | Test: write prod feedback with `rating=incomplete`; call `kb_evolve(wiki_dir=tmp_wiki)` with no feedback; assert no "Coverage Gaps" section. | Same as AC4 — tighter than the full MCP feedback sweep; intentionally scoped. |
| AC6 | T1+T2 — kb_compile_scan wiki_dir | Test: `kb_compile_scan(wiki_dir=str(tmp_wiki))` reads tmp's `.data/hashes.json`, not prod's. | `kb_compile` (sister tool) does NOT take `wiki_dir` in cycle 9 — scoped-out (remains in backlog). |
| AC7 | T1 — oversize kb_ingest reject | Test: write 200KB `raw/articles/big.md`; `kb_ingest("raw/articles/big.md")` returns Error, NOT partial ingest. | `kb_save_source`, `kb_refine_page` already have caps from cycle 7/8 (verify via `MAX_INGEST_CONTENT_CHARS` grep); `kb_ingest_content` ALSO AC8 in this cycle. All three enforce the same `QUERY_CONTEXT_MAX_CHARS * 4` byte cap. |
| AC8 | T1 — oversize kb_ingest_content reject BEFORE write | Test: call kb_ingest_content with 200KB content; assert NO file created at `raw/articles/{slug}.md` AND Error returned. | `kb_save_source` already pre-checks via `_validate_file_inputs` (core.py:68); AC8 extends to `kb_ingest_content` same file. |
| AC9 | T1 — ambiguous page_id | Test: create `concepts/Foo.md` + `concepts/foo.md`; call `kb_read_page("concepts/Foo")` — first confirms exact match returns OK; then `kb_read_page("concepts/FOO")` asserts Error with both filenames. | Existing code at `src/kb/mcp/browse.py:87-104` already has the matching logic from cycle 3/4; AC9 is a doc-sync verifying the behavior is still present post-refactor. Scoped-out: `kb_review_page` / `kb_refine_page` do their own page lookup — out of scope, those use exact-match only. |
| AC10 | T3 — load_manifest resilience | Test: inject a mid-write `OSError(EACCES)` during `json.loads` via a file permission race; assert `load_manifest()` returns `{}` and logs a warning, does NOT raise. | `load_feedback` (cycle 3), `load_verdicts` (cycle 5), `load_review_history` (cycle 7) already widened. `load_manifest` is the last of the 4 stores. Scoped-out: the one-off `atomic_json_write`-backed stores (`.data/augment_manifest_*.json`) use their own try/except and are not in cycle 9. |
| AC11 | T1 — augment summary per-stub | Test: synthetic run with one stub, two URLs, fail-then-success; assert `result['summary']` contains `Saved: 1, Failed: 0`. AND assert `manifest.entries[stub_id]` has TWO URL rows (per-URL detail preserved). | The per-URL `fetches` array in the return dict stays as-is; only the summary string is collapsed. |
| AC12 | T6 — single YAML parse | Test: patch `yaml.safe_load` as a spy; call `check_source_coverage` over 10 pages; assert call count == 10 (one per page), not 20. | Other lint checks (`check_frontmatter`, `check_staleness`, `check_frontmatter_staleness`) each parse once already — scoped-out; this AC is specifically the `check_source_coverage` double-parse at `src/kb/lint/checks.py:514-536`. |
| AC13 | T6 — orphan-concept consistency | Test: create concept-A that links `[[b]]` (bare slug), and concept-B at `concepts/b.md`. `build_graph` resolves the edge; `analyze_coverage` currently reports B as orphan. Post-fix: B not orphan. | Other callers of `build_backlinks` (`find_connection_opportunities`, `evolve.generate_evolution_report`) do NOT depend on orphan-detection specifically. Scoped-out: `build_backlinks`'s own signature stays the same; the caller uses an alternate resolution at AC13 site only. |
| AC14 | T4 — broader except in normalize_for_scan | Test: monkeypatch `base64.b64decode` to raise `RuntimeError`; call `_normalize_for_scan("...")`; assert no crash, `logger.debug` emitted once per failed decode (not silent). | `_scan_for_secrets` main loop already narrow-excepts; AC14 only broadens the decode-candidate sub-loop. Scoped-out: the URL-decode `unquote()` call does not raise per stdlib contract — no change needed there. |
| AC15 | Doc — per-process rate-limit scope | Verify docstring at `capture.py:48` explicitly says "per-process only; MCP server and CLI maintain independent deques" + TODO v2 ref. No behavior change. | No other module-level rate limiter in `src/kb/` uses a file-locked deque; the TODO ref names `.data/capture_rate.json` pattern — out of scope for cycle 9 (deferred). |
| AC16 | T1 — bounded slug collision | Test: inject 10001 synthetic colliding slugs in `existing`; call `_build_slug("decision", "x", existing)`; assert `RuntimeError` with "slug collision exhausted" message. | `slugify` itself (kb.utils.text) is unbounded input→output; AC16 only bounds the RETRY loop. Scoped-out: `kb_ingest_content` / `kb_save_source` use `slugify + overwrite=False`, not a retry loop — different pattern, not at risk. |
| AC17 | Doc/naming — `_is_path_within_captures` rename | Verify both call sites in `_write_item_files` updated; import in `tests/test_capture.py:31` updated (from `_path_within_captures` → `_is_path_within_captures`). | Rename is confined to `kb.capture`. Scoped-out: no external callers — the symbol is a leading-underscore private. |
| AC18 | Observability — label disambiguation | Test: base64-encoded `sk-ant-...`; assert `_scan_for_secrets()` returns `(label, "via base64")`. URL-encoded: returns `(label, "via URL-encoded")`. | `_normalize_for_scan` returns `str`; AC18 changes return to `list[tuple[str, str]]`. No callers of the private function outside `kb.capture`. |
| AC19 | Type/naming — NamedTuple for secret patterns | Static: `grep _CAPTURE_SECRET_PATTERNS -A0` shows only `.label` / `.pattern` access, no tuple-index. | Scoped-out: `_CAPTURE_SECRET_PATTERNS` is only referenced inside `kb.capture` — zero external consumers. |
| AC20 | Test hygiene — CAPTURE_KINDS import source | `grep "from kb.capture import CAPTURE_KINDS"` in tests after fix: expect 0 hits, replaced by `from kb.config import CAPTURE_KINDS`. | Scoped-out: any future import of CAPTURE_KINDS should follow the same rule; CLAUDE.md does not need update (config is already the canonical location). |
| AC21 | T4 — yaml_escape round-trip regression | Two new tests passing literal `C:\path\to\file` and `'"quoted"'` as `title`; write via `capture_items`; read back via `frontmatter.loads`; assert equal. | Scoped-out: `yaml_escape` implementation not changed — AC21 is a pure characterization test guarding against future refactors. |
| AC22 | Test hygiene — captures assertion | Add `assert captures.resolve().is_relative_to(PROJECT_ROOT.resolve())` in `tmp_captures_dir` fixture at `tests/conftest.py:182`. | Scoped-out: other fixtures (`tmp_project`, `tmp_wiki`) don't touch PROJECT_ROOT because they use `tmp_path` directly — AC22 is specific to the captures monkey-patch pattern. |
| AC23 | Test hygiene — RAW_SUBDIRS dynamic | Change `RAW_SUBDIRS` in conftest.py:11 to derive from `SOURCE_TYPE_DIRS.keys()`. Verify all 10 subdirs are created; re-run full suite. | `WIKI_SUBDIRS` is also hardcoded at conftest.py:10 — NOT in scope this cycle (conventions vs. config coupling is different argument); scoped-out. |
| AC24 | T4 — LLM error redaction BEFORE truncation | Test: `_make_api_call` receives `APIStatusError(message="...sk-ant-abc123...")`; assert raised `LLMError.args[0]` contains `[REDACTED:ANTHROPIC_KEY]`, does NOT contain `abc123`. | `_sanitize_error_str` in `src/kb/mcp/app.py:91` handles path redaction (different axis) — AC24 is ADDITIVE, not duplicative. Other error sites (`kb.mcp.core._sanitize_error_str(e)` call sites) inherit path-redaction only; if an Anthropic error's message ends up wrapped in `LLMError` and re-stringified, the llm-layer redaction runs FIRST so downstream paths are already safe. |
| AC25 | Doc — instructions alpha sort | Verify `mcp.instructions` string in `src/kb/mcp/app.py:34-55` after fix has each thematic group alphabetized. Line-by-line snapshot test. | Scoped-out: README.md / CLAUDE.md tool lists are handwritten — not affected. No downstream client parses the instructions block. |
| AC26 | Doc/import — CLI top-level imports | Verify `ruff check` clean; `python -c "import kb.cli"` succeeds without side-effects (kb.version fast-path not broken). | Scoped-out: `kb.mcp_server` and `kb.mcp.*` also have function-local imports — those are optimization for server startup, NOT the same cleanup class; out of scope. |
| AC27 | T5 — lazy ingest_source re-export | Test (subprocess): `python -c "import sys, kb.ingest; assert 'kb.ingest.pipeline' not in sys.modules; kb.ingest.ingest_source; assert 'kb.ingest.pipeline' in sys.modules"`. Mirrors cycle 8 AC30 test shape. | `kb.compile`, `kb.query`, `kb.graph` `__init__.py` files have similar eager re-exports — NOT scoped for cycle 9 (kb_ingest is the one blocking `kb --version` per cycle 8 Red Flag). Document the others as a follow-up backlog item. |
| AC28 | T2 — raw-fallback root | Test: `query_wiki(wiki_dir=tmp_wiki)` with `tmp/raw/articles/*.md` and `PROJECT_ROOT/raw/articles/*.md`; assert raw-fallback hits TMP. | Scoped-out: `search_raw_sources` is internal; no other caller. |
| AC29 | T4 — stripped body downstream | Test: `_verify_body_is_verbatim([{"body": "  hello  "}], content="  hello  world")`; assert `kept[0]["body"] == "hello"` (stripped). File on disk contains stripped body. | Scoped-out: capture_items' verbatim-check already passes both stripped and raw; only the DOWNSTREAM write-to-disk path changes. |
| AC30 | Test hygiene — duplicate import | `grep "import re as _test_re"` in test_capture.py after fix: expect zero hits. Comment at line 120-122 matches new arithmetic. | Scoped-out: no other test files have the same double-import pattern — run `ruff check tests/` for confirmation. |
| AC31 | Doc — .env.example wording | Verify new wording in `.env.example:3-5`. README.md parity check: if README says ANTHROPIC_API_KEY is "required", doc-updater agent should flag in Step 12. | Scoped-out: CLAUDE.md already reflects the correct (optional-under-Claude-Code-mode) positioning. |

## Dep-CVE baseline summary

0 open Dependabot alerts (`.tmp/cycle-9-alerts-baseline.json` is `[]`); 1 pip-audit
finding: `diskcache==5.6.3` CVE-2025-69872 Class A (unfixable, tracked in
BACKLOG).
