# Cycle 9 Design Decision — Step 5 Gate (2026-04-18)

**Role:** Step 5 decision gate for feature-dev cycle 9.
**Inputs:** `cycle9-requirements.md`, `cycle9-threat-model.md`, `cycle9-design-eval-R1.md`
(Opus APPROVE-WITH-CONDITIONS), `cycle9-design-eval-R2.md` (Codex REJECT).
**Verification:** every function/line reference below was grep-confirmed against
working tree `main` at commit `1c4ff5d`. Stale references are AMENDED in place
per cycle 8 R2 lesson — no AC is rejected solely for stale-line drift.

## VERDICT — approve with amendments

R2's REJECT rests on four concrete blockers (AC14 log, AC26 fast-path, AC22
assertion target, AC6/AC28 function drift) plus three CONCERNs (AC7 char/byte
ordering, AC12 signature, AC24 pattern ordering). Each blocker resolves to a
specific amendment that preserves the underlying goal without rewriting the
batch. No AC requires re-scoping by more than one AC-line. Gate passes with the
amendments in §CONDITIONS below.

## DECISIONS — per-question one-liners

- **Q1 (AC9):** Option **(a) DROP**. AC9 is characterization of already-shipped
  behaviour (G3 phase 4.5 R4 LOW, browse.py:87-104, error + ambiguity reporting
  already present). Cycle 9 closes with **30 AC** renumbered, not 31. Q1
  candidate (b) is invalid — `_validate_notes` is already wired to both
  `revision_notes` (quality.py:79), `notes` in `kb_query_feedback`
  (quality.py:195), and `notes` in `kb_save_lint_verdict` (quality.py:363);
  the `content` and `question` fields are intentionally gated by a DIFFERENT
  validator (`MAX_INGEST_CONTENT_CHARS`, `MAX_QUESTION_LEN`) and conflating the
  two classes would weaken both.
- **Q2 (AC14):** Option **(a) ADD LOG**. `logger.debug("normalize-for-scan
  decode-skip (%s): %s", stage, e)` inside the broadened except. Threat model
  already mandates this; promote from mitigation to AC contract. R1 and R2
  converge.
- **Q3 (AC26):** Option **(a) DROP + replace**. AC26 is REJECTED. Cycle 7 AC30's
  fast-path (cli.py:7-19) is load-bearing; moving function-local
  `from kb.X import Y` lines to module top (current lines 111, 141, 172, 173,
  235, 236, 263, 287, 300) would force `kb.config`, `kb.compile.compiler`,
  `kb.query.engine`, and others to import BEFORE the `kb --version` short-
  circuit runs. Replace with **new AC26' (capture.py MAX_PROMPT_CHARS
  assertion)** — BACKLOG LOW item on capture.py:618, same-file as AC14-19 and
  AC29 so it commits in the same capture.py diff. Low risk, trivial test.
- **Q4 (AC22):** Option **(a) rescope assertion target**. Current
  `tmp_captures_dir` returns `tmp_project / "raw" / "captures"` under
  `tmp_path`, not `PROJECT_ROOT`. Assert
  `captures.resolve().is_relative_to(tmp_project.resolve())` — matches actual
  intent ("fixture stays inside its sandboxed project") and fails loudly if
  future refactor escapes the sandbox. Q4(b) would require monkeypatching
  PROJECT_ROOT which is a bigger blast-radius change; rejected.
- **Q5 (AC6):** **AMEND**. `kb_compile_scan` calls `find_changed_sources`
  (compiler.py:127) and `scan_raw_sources` (compiler.py:89), NOT
  `detect_source_drift`. Final contract: derive `raw_dir = wiki_path.parent /
  "raw"` and `manifest_path = wiki_path.parent / ".data" / "hashes.json"` from
  the `wiki_dir` kwarg, thread both into `find_changed_sources(raw_dir,
  manifest_path)` (save_hashes=True default) and `scan_raw_sources(raw_dir)`.
  Requirements wording corrected.
- **Q6 (AC7):** Option **(a) reject char overflow at boundary too**.
  `kb_ingest`'s byte cap at core.py:286-287 stays. ADD a parallel char check
  before the function-local truncation at core.py:357: if `len(content) >
  QUERY_CONTEXT_MAX_CHARS`, return `"Error: source too long ({N} chars; max
  {QUERY_CONTEXT_MAX_CHARS} chars)"`. This converts the silent
  `logger.warning` + truncate into a consistent Error that matches
  `_validate_file_inputs` (core.py:68) wording class. The byte cap catches
  attacker files; the char cap catches char-heavy UTF-8 decoded content that
  passed the byte cap but still overwhelms extraction prompts.
- **Q7 (AC12):** Option **(a) scoped rework**. Do NOT change
  `check_source_coverage(pages: list[Path], ...)` signature (compiler-side
  precedent: signature is stable across 5 callers). Instead: for each `page`
  dict in `load_all_pages(wiki_dir)` output (runner.py:113 already threads
  pre-loaded dicts through `check_frontmatter` et al. via `pages=shared_pages`
  — but the current `pages` param here is `list[Path]`, not `list[dict]`).
  Fix: inside `check_source_coverage`, call `frontmatter.loads(content)` ONCE
  and pass `post.metadata` to both the frontmatter-fence check and the
  raw-refs merge — single parse per page, same signature. Test: mock
  `yaml.safe_load` as a spy; assert call count equals page count, not 2× page
  count.
- **Q8 (AC24):** **CONFIRM ordering** — redact BEFORE each `truncate(...,
  limit=500)` site (llm.py:127, 171, 238, 244). Pattern list order: `sk-ant-`
  before `sk-` (specific-before-generic); `Bearer ` tokens; 40-char base64
  threshold; 32-char hex threshold. Double-hit a string to ensure later
  patterns don't redact already-redacted markers. Replace marker format:
  `[REDACTED:ANTHROPIC_KEY]`, `[REDACTED:OPENAI_KEY]`, `[REDACTED:BEARER]`,
  `[REDACTED:HEX]`, `[REDACTED:BASE64]`. Hex threshold at 32 is tight but
  conservative — git SHAs (40-char) are also redacted, which is acceptable
  since the STRUCTURE signal survives (`[REDACTED:HEX]` tells operator a
  hash-like blob was present).
- **Q9 (AC27):** **CONFIRM**. Final test shape: `subprocess.run([sys.executable,
  "-c", "import sys, kb.ingest; assert 'kb.ingest.pipeline' not in sys.modules,
  sys.modules; from kb.ingest import ingest_source as f; assert
  'kb.ingest.pipeline' in sys.modules"], env={**os.environ, "PYTHONPATH":
  f'{repo_src}{os.pathsep}' + os.environ.get("PYTHONPATH", "")}, check=True)`.
  Matches cycle 8 `test_kb_version_no_config_import` pattern.
- **Q10 (AC28):** Option **(a) close through query_wiki**. `search_raw_sources`
  signature already accepts `raw_dir: Path | None` (engine.py:438-440);
  `query_wiki` derives `effective_raw_dir = (wiki_dir.parent / "raw").resolve()`
  at engine.py:688-692 and passes it at engine.py:800. AC28's goal is ALREADY
  wired on the hot path; the regression gap is a **missing test**. Retarget
  AC28 to a regression test that calls `query_wiki(wiki_dir=tmp_wiki)` with
  distinct `tmp_raw/articles/foo.md` and production `PROJECT_ROOT/raw/...`
  files and asserts fallback reads TMP. No signature change to
  `search_raw_sources`.

## CONDITIONS — numbered, specific, testable

1. **AC14 MUST include the log line**: broaden except to `except Exception as
   exc: continue` preceded by `logger.debug("normalize-for-scan decode-skip
   (%s): %s", stage, exc)`. Verified test: monkeypatch `base64.b64decode` to
   raise `RuntimeError`; assert `logger.debug` emits once per failed decode
   via `caplog`.

2. **AC26 DROPPED, replaced with AC26'**: `src/kb/capture.py:_extract_items_via_llm`
   gains `MAX_PROMPT_CHARS = 600_000` module-level const + `if len(prompt) >
   MAX_PROMPT_CHARS: raise LLMError(...)` pre-flight check. Same file as
   AC14-19 + AC29 — lands in the capture.py commit.

3. **AC22 assertion target**: `assert captures.resolve().is_relative_to(
   tmp_project.resolve())`, NOT `PROJECT_ROOT.resolve()`.

4. **AC6 plumbing**: `raw_dir = wiki_path.parent / "raw"` and `manifest_path =
   wiki_path.parent / ".data" / "hashes.json"` threaded to `find_changed_sources`
   and `scan_raw_sources`. When `wiki_dir is None`, preserve current behaviour
   (both functions fall back to their own `or RAW_DIR` / `or HASH_MANIFEST`).

5. **AC7 char + byte gates**: both checks surface the same `Error: source too
   long` prefix (byte check unchanged at core.py:286; char check added at
   core.py:357 replacing the `logger.warning` + `content = content[:cap]`
   sequence). Regression test: a 200KB UTF-8 file that passes the byte cap
   (file_bytes < 320000) but whose decoded char count exceeds
   QUERY_CONTEXT_MAX_CHARS (80000) returns Error, not a truncated extraction
   prompt.

6. **AC12 single-parse**: preserve `pages: list[Path]` signature. Inside the
   function, call `frontmatter.loads(content)` ONCE per page and reuse
   `post.metadata` for both the fence check and the raw-refs merge. Spy test
   on `yaml.safe_load` asserts call count equals page count.

7. **AC24 redact BEFORE truncate AT EVERY SITE**: llm.py:127 (BadRequest/Auth),
   llm.py:171 (APIStatusError generic), llm.py:238 (retry-exhausted
   APIStatusError), llm.py:244 (retry-exhausted generic last_error). Extract
   `_redact_secrets(msg: str) -> str` helper co-located with
   `_LLM_ERROR_TRUNCATE_LEN`. Pattern ordering: ANTHROPIC_KEY → OPENAI_KEY →
   BEARER → BASE64 → HEX. Verified test: `APIStatusError(message="...sk-ant-
   abc123...")` surfaces as `LLMError` whose str contains `[REDACTED:
   ANTHROPIC_KEY]` and does NOT contain `abc123`.

8. **AC27 subprocess test** uses explicit `PYTHONPATH` per cycle 7 R3 lesson;
   asserts `'kb.ingest.pipeline' not in sys.modules` BEFORE attribute access,
   then asserts it APPEARS after `from kb.ingest import ingest_source as f`
   (or equivalent attribute touch).

9. **AC28 behavioural test only** — no signature change to
   `search_raw_sources`; test drives `query_wiki(wiki_dir=tmp_wiki)` to prove
   tmp raw/ reaches the fallback, production raw/ does not.

10. **Commit atomicity** (R1 condition 3, confirmed): (a) AC1+AC2+AC3+AC28 in
    ONE engine.py commit; (b) AC14-19 + AC29 + AC26' in ONE capture.py commit;
    (c) AC20/21/30 (test_capture.py) commit AFTER capture.py; (d) AC22/23
    (conftest.py) commit AFTER test_capture.py.

11. **Ruff-format AFTER all Edits** (MEMORY feedback): run `ruff format`
    exactly once per file at the end of each commit, never between two Edit
    passes in the same file.

## FINAL DECIDED DESIGN — 30 AC

Renumbered: original AC1–AC8 retained as-is; old AC9 DROPPED; old AC10-AC25
shift down by 1 (AC9–AC24); old AC26 DROPPED + replaced as new AC25 (AC26'
MAX_PROMPT_CHARS); old AC27-AC31 shift down as AC26-AC30. Final numbering
below. Each AC names sibling call sites DELIBERATELY out of scope
(cycle 7 R3 / cycle 8 R2 same-class-leak defence).

### Commit 1 — `src/kb/query/engine.py` (4 AC)

- **AC1** (engine.py:131): replace `Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX`
  with `_vec_db_path(wiki_dir or WIKI_DIR)` import from `kb.query.embeddings`.
  **Out of scope:** `rebuild_vector_index` (embeddings.py:79) already uses
  `_vec_db_path(wiki_dir)` — correct; no change.

- **AC2** (engine.py:214): `_flag_stale_results(scored[:max_results],
  project_root=(wiki_dir.parent if wiki_dir else None))`. Signature at
  engine.py:267 already accepts `project_root`; only the call site is
  unthreaded. **Out of scope:** no other callers of `_flag_stale_results`
  exist (grep confirmed).

- **AC3** (engine.py:756): replace `Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX`
  with `_vec_db_path(wiki_dir or WIKI_DIR)`. Same source of truth as AC1.
  **Out of scope:** same as AC1 — no other hardcoded vec_path derivations.

- **AC4** (engine.py regression test only): new test `test_query_wiki_raw_
  fallback_uses_override_raw_dir` calls `query_wiki(wiki_dir=tmp_wiki)` with
  `tmp/raw/articles/only-in-tmp.md` and asserts the raw-fallback section
  contains tmp-only content. Zero signature changes to `search_raw_sources`.
  **Out of scope:** `search_raw_sources` already parameterized on `raw_dir`
  (engine.py:438-440); threading at `query_wiki:800` already correct.

### Commit 2 — `src/kb/mcp/health.py` (2 AC)

- **AC5** (health.py:68-75): derive `feedback_path = (wiki_path.parent if
  wiki_path else PROJECT_ROOT) / ".data" / "feedback.json"` and pass
  `path=feedback_path` through the `_safe_call` lambda to
  `get_flagged_pages(path=...)`. **Out of scope:** `kb_reliability_map`
  (quality.py:224) reads `compute_trust_scores()` without `wiki_dir` — the
  tool itself has no `wiki_dir` kwarg; defer to backlog.

- **AC6** (health.py:122-126): derive `feedback_path` same way as AC5 and pass
  `path=feedback_path` to `get_coverage_gaps(path=...)`. **Out of scope:**
  `kb_query_feedback` writes via `add_feedback_entry` without a `wiki_dir`
  kwarg — that tool's signature change remains in backlog.

### Commit 3 — `src/kb/mcp/core.py` (3 AC)

- **AC7** (core.py:601): `kb_compile_scan(incremental: bool = True, wiki_dir:
  str | None = None)`. Inside: `wiki_path = Path(wiki_dir) if wiki_dir else
  None`; `raw_dir = wiki_path.parent / "raw" if wiki_path else None`;
  `manifest_path = wiki_path.parent / ".data" / "hashes.json" if wiki_path
  else None`; thread both to `find_changed_sources(raw_dir, manifest_path)`
  and `scan_raw_sources(raw_dir)`. **Out of scope:** `kb_compile` (core.py:660)
  lacks `wiki_dir` — backlog, called out in R1 M4.

- **AC8** (core.py:357): after the char-length check, replace the
  `logger.warning` + `content = content[:QUERY_CONTEXT_MAX_CHARS]` sequence
  with `return f"Error: source too long ({len(content)} chars; max
  {QUERY_CONTEXT_MAX_CHARS} chars)."`. Byte cap at core.py:286 unchanged.
  **Out of scope:** `kb_ingest_content` (core.py:409) already calls
  `_validate_file_inputs` which emits `MAX_INGEST_CONTENT_CHARS` Error pre-
  write — AC9 extends that gate with an explicit parity assertion.

- **AC9** (core.py:409): add regression test asserting `kb_ingest_content`
  with content > `MAX_INGEST_CONTENT_CHARS` returns Error and leaves
  `raw/articles/` empty (no orphan file). Validator already in place via
  `_validate_file_inputs`; AC9 is verification, not new code. **Out of
  scope:** `kb_save_source` (core.py:565) already uses
  `_validate_file_inputs` — out of scope as no gap.

### Commit 4 — `src/kb/compile/compiler.py` (1 AC)

- **AC10** (compiler.py:75): widen `except (json.JSONDecodeError,
  UnicodeDecodeError)` to `except (json.JSONDecodeError, UnicodeDecodeError,
  OSError)` (append-only, never replace); log warning; return `{}`. **Out of
  scope:** `load_feedback` (cycle 3), `load_verdicts` (cycle 5),
  `load_review_history` (cycle 7) already OSError-widened — AC10 closes the
  4th store. Augment-manifest JSON (augment.py `atomic_json_write` state
  machine) is not a store in the same class — out of scope.

### Commit 5 — `src/kb/lint/augment.py` (1 AC)

- **AC11** (augment.py:906-912): compute summary from FINAL per-stub state
  recorded in `ingests` / `verdicts` (`len({e["stub_id"] for e in fetches
  if e["status"] == "saved"})` — dedupe to per-stub), not from URL-attempt
  entries. Per-URL detail preserved in the returned `fetches` list.
  Regression test: synthetic stub with URL-A fail + URL-B success reports
  `Saved: 1, Failed: 0`. **Out of scope:** the `fetches` return value itself
  stays per-URL — API contract unchanged.

### Commit 6 — `src/kb/lint/checks.py` (1 AC)

- **AC12** (checks.py:482-539): keep signature `check_source_coverage(wiki_dir,
  raw_dir, pages: list[Path] | None = None)`. Inside the for-loop (lines 505-
  538), call `post = frontmatter.loads(content)` ONCE per page and pass
  `post.metadata.get("source")` to `normalize_sources` without a second parse.
  Test: patch `yaml.safe_load` as a spy; call `check_source_coverage` over N
  pages; assert call count == N (not 2×N). **Out of scope:**
  `check_frontmatter`, `check_staleness`, `check_frontmatter_staleness` each
  parse once already — no duplication exists there.

### Commit 7 — `src/kb/evolve/analyzer.py` (1 AC)

- **AC13** (analyzer.py:25-70): in the orphan-concept report at analyzer.py:58-
  63, replace the bare `pid not in backlinks` check with lookup against a
  `build_graph(wiki_dir)` node set (using the same slug_index fallback at
  builder.py:61-72). Extract a small helper `_orphan_via_graph_resolver(pages,
  wiki_dir)` returning orphans as determined by graph edges, not backlinks
  (which use exact-match at linker.py:137,159). Regression test: concept-A
  with `[[b]]` link to concept-B; pre-fix `analyze_coverage` reports B as
  orphan; post-fix does not. **Out of scope:** `build_backlinks` signature
  stays; the caller uses a different resolver at this site only.

### Commit 8 — `src/kb/capture.py` (8 AC, atomic)

- **AC14** (capture.py:211): broaden `except (ValueError, binascii.Error,
  UnicodeDecodeError)` to `except Exception as exc: logger.debug(
  "normalize-for-scan decode-skip: %s", exc); continue`. Both base64 and
  URL-decode except blocks get the log line. Test monkeypatches
  `base64.b64decode` to raise `RuntimeError` and asserts `caplog` records one
  DEBUG message per failed decode. **Out of scope:** `_scan_for_secrets`
  main loop already narrow-excepts — unchanged.

- **AC15** (capture.py:48-58): append to `_check_rate_limit` docstring: "This
  limit is per-process: a separate CLI or MCP-server process maintains its
  own independent deque, so the system-wide call rate can exceed
  `CAPTURE_MAX_CALLS_PER_HOUR` by N×. TODO(v2): move to a file-locked
  sliding-window deque persisted at `.data/capture_rate.json` (pattern
  analogous to `kb.lint._augment_rate`) for system-wide enforcement." **Out
  of scope:** no other rate limiter in `src/kb/` uses a file-locked deque —
  TODO names the pattern but does not build it this cycle.

- **AC16** (capture.py:354-378): add module-level const
  `_SLUG_COLLISION_CEILING = 10000`; inside `_build_slug` wrap `while True:`
  in `for _ in range(max(len(existing) + 2, _SLUG_COLLISION_CEILING)):` with a
  trailing `raise RuntimeError(f"slug collision exhausted for {kind}/{base!r}
  after {n} retries")`. Test injects 10001 synthetic colliding slugs and
  asserts `RuntimeError` raised deterministically. **Out of scope:**
  `kb_ingest_content` / `kb_save_source` use `slugify` + `O_EXCL` (different
  pattern) — not at risk.

- **AC17** (capture.py:381 + 567): rename `_path_within_captures` →
  `_is_path_within_captures`. Update both call sites in `_write_item_files`
  (capture.py:567) AND both grep hits at capture.py:708, 732. **Tests**
  follow in AC22 (test_capture.py:31, 505, 509, 513, 518 import + 4 asserts).
  **Out of scope:** symbol is leading-underscore private; no external
  consumers exist (grep confirmed).

- **AC18** (capture.py:222-237): split `_normalize_for_scan` to return
  `list[tuple[str, str]]` of `(segment, encoding_label)` where label is
  `"plain"`, `"via base64"`, or `"via URL-encoded"`. Update
  `_scan_for_secrets` to iterate the labels and return `(secret_label,
  encoding_label_of_segment)`. Test: base64 payload yields `"via base64"`;
  URL-encoded yields `"via URL-encoded"`; plain yields `"line N"` or
  equivalent per the existing contract. **Out of scope:** no callers outside
  `kb.capture`.

- **AC19** (capture.py:101-189): refactor `_CAPTURE_SECRET_PATTERNS: list[tuple[
  str, re.Pattern]]` into `list[_SecretPattern]` where `_SecretPattern` is a
  module-level `NamedTuple("SecretPattern", [("label", str), ("pattern",
  re.Pattern[str])])`. Call sites in `_scan_for_secrets` access `.label` /
  `.pattern` by name. **Out of scope:** all references are inside
  `kb.capture` (grep confirmed) — zero external consumers.

- **AC20** (capture.py:350 — part of `_verify_body_is_verbatim`): before
  `kept.append(item)` at capture.py:350, set `item["body"] = body_stripped`
  so downstream writers receive trimmed bodies. Test: round-trip capture
  with `body = "  hello  "` and assert on-disk file contains `"hello"`, not
  `"  hello  "`. **Out of scope:** the verbatim check itself (substring
  test) still accepts both stripped and raw content — no regression.

- **AC21** (capture.py:320-324, NEW module-level const + assertion):
  `MAX_PROMPT_CHARS = 600_000` (Haiku 200k-token context × ~3 chars/token safe
  margin); inside `_extract_items_via_llm` add `if len(prompt) >
  MAX_PROMPT_CHARS: raise LLMError(f"capture prompt {len(prompt)} chars
  exceeds MAX_PROMPT_CHARS={MAX_PROMPT_CHARS}")`. Replacement for old AC26
  (cli.py imports). Test synthetic prompt of 700k chars triggers the Error.
  **Out of scope:** `CAPTURE_MAX_BYTES` already 50KB — this guard fires
  ONLY if that cap is later raised.

### Commit 9 — `tests/test_capture.py` (3 AC)

- **AC22** (test_capture.py:23, 31, 505, 509, 513, 518): change
  `from kb.capture import CAPTURE_KINDS` → `from kb.config import
  CAPTURE_KINDS`. Update `_path_within_captures` → `_is_path_within_captures`
  in both the import and the 4 assert sites (pair with AC17). **Out of
  scope:** no other tests import `CAPTURE_KINDS` or `_path_within_captures`
  (grep confirmed).

- **AC23** (test_capture.py, NEW): two tests — `test_title_with_backslash_
  round_trips` passes `r"C:\path\to\file"` as title, asserts `_fm.loads(...)`
  recovers the exact title; `test_title_with_double_quote_round_trips`
  passes `'"quoted"'` and asserts equal. Both use `create_raw_source` /
  `capture_items` via `tmp_captures_dir` fixture. **Out of scope:**
  `yaml_escape` implementation itself not touched — AC23 is characterization
  only.

- **AC24** (test_capture.py:11-12, 131): remove duplicate `import re as
  _test_re`; fix the byte-comment at test_capture.py:128-132 to match actual
  arithmetic (`12500 + 1 = 12501 pairs; 4 bytes each = 50004 raw bytes;
  post-LF normalization 37503 bytes`) or rewrite the comment to match whatever
  the final expression evaluates to. **Out of scope:** no other tests have
  the same double-import pattern (`ruff check tests/ --select F811` confirms
  0 hits elsewhere).

### Commit 10 — `tests/conftest.py` (2 AC)

- **AC25** (conftest.py:182-186): inside `tmp_captures_dir`, after
  `captures.mkdir(...)`, add `assert captures.resolve().is_relative_to(
  tmp_project.resolve())`. **Out of scope:** other fixtures (`tmp_project`,
  `tmp_wiki`) derive directly from `tmp_path` — no assertion needed.

- **AC26** (conftest.py:11): replace `RAW_SUBDIRS = ("articles", "papers",
  "repos", "videos", "captures")` with `RAW_SUBDIRS = tuple(sorted(d.name
  for d in SOURCE_TYPE_DIRS.values()))` (lazy-import from `kb.config` at top
  of file). `tmp_project` fixture MUST create all entries in the derived
  tuple (current behaviour: creates every entry via `for subdir in
  RAW_SUBDIRS`). **Invariant clarification** (R1 condition 2): fixture now
  creates all 10 source-type subdirs on every `tmp_project` instantiation —
  acceptable because `mkdir` is fast (~100μs × 10 = 1ms). **Out of scope:**
  `WIKI_SUBDIRS` at conftest.py:10 stays hardcoded (different coupling
  argument — wiki subdir names are convention, not config).

### Commit 11 — `src/kb/utils/llm.py` (1 AC)

- **AC27** (llm.py:127, 171, 238, 244): define `_LLM_ERROR_REDACT_PATTERNS:
  list[tuple[str, re.Pattern]]` module-level with ordering ANTHROPIC_KEY
  (`sk-ant-[A-Za-z0-9_-]{20,}`) → OPENAI_KEY (`sk-[a-zA-Z0-9]{20,}`) →
  BEARER (`(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}`) → BASE64
  (`[A-Za-z0-9+/]{40,}={0,2}`) → HEX (`[a-fA-F0-9]{32,}`). Add
  `_redact_secrets(msg: str) -> str` helper. Call `truncate(_redact_secrets(
  str(e.message)), limit=500)` at all 4 sites. Pattern order confirmed:
  specific-before-generic. Test: `APIStatusError("...sk-ant-abc...")` yields
  `LLMError` containing `[REDACTED:ANTHROPIC_KEY]`, not `abc`. **Out of
  scope:** `_sanitize_error_str` in `src/kb/mcp/app.py:84` handles path
  redaction — different axis, not duplicated.

### Commit 12 — `src/kb/mcp/app.py` (1 AC)

- **AC28** (app.py:34-55): rewrite `mcp.instructions` to sort tool names
  alphabetically within each thematic block (Browse / Ingest / Quality /
  Health). Generated at module load — use a tuple-of-tuples source structure
  + `sorted()` calls so drift is impossible. Test: read `mcp.instructions`
  post-import; assert lines within each thematic block header are
  alphabetical by tool name. **Out of scope:** README.md / CLAUDE.md tool
  lists are handwritten — not affected.

### Commit 13 — `src/kb/ingest/__init__.py` (1 AC)

- **AC29** (ingest/__init__.py:3 full replacement): replace eager
  `from kb.ingest.pipeline import ingest_source` with PEP 562 lazy
  `__getattr__` pattern mirroring `src/kb/__init__.py:17-43`. Keep
  `__all__ = ["ingest_source"]`. Subprocess test asserts
  `'kb.ingest.pipeline' not in sys.modules` after `import kb.ingest`; then
  asserts it APPEARS after `from kb.ingest import ingest_source as f`.
  Subprocess uses explicit `PYTHONPATH` per cycle 7 R3 lesson. **Out of
  scope:** `kb.compile/__init__.py`, `kb.query/__init__.py`, `kb.graph/__init__.py`
  also have similar patterns — cycle 9 addresses ONLY `kb.ingest` (the
  blocking one for `kb --version` per cycle 8 Red Flag); the other three
  documented as follow-up backlog item.

### Commit 14 — `.env.example` (1 AC)

- **AC30** (.env.example:3): change `# Required — Claude API for compile/
  query/lint operations` to `# Optional — Claude API. NOT needed when using
  Claude Code (MCP mode is the default LLM; see CLAUDE.md § MCP servers).
  Required ONLY for: (a) CLI \`kb compile\` / \`kb query\` without
  use_api=False, (b) MCP tools called with use_api=True, (c) \`kb_query
  --format=…\` output adapters.` `ANTHROPIC_API_KEY=sk-ant-...` line
  unchanged. **Out of scope:** README.md wording — doc-updater agent catches
  drift in Step 12.

## Same-class leak defence summary

Every AC above names at least one sibling call site explicitly scoped-out of
cycle 9. The five documented out-of-scope classes (backlog follow-ups): (1)
non-`kb_compile_scan` compile tools lacking `wiki_dir`; (2) non-`kb_lint`/
`kb_evolve` MCP tools reading feedback without `wiki_dir`; (3) non-`kb.ingest`
`__init__.py` eager re-exports in `kb.compile`, `kb.query`, `kb.graph`; (4)
`WIKI_SUBDIRS` conftest hardcoding (different coupling class than
`RAW_SUBDIRS`); (5) `_path_within_captures` is the only rename target this
cycle — sibling helpers `_validate_input`, `_extract_items_via_llm` already
verb-first.

## Risk re-scorecard (post-amendment)

- **HIGH-risk AC:** 0 (unchanged from R1).
- **MEDIUM-risk AC:** 5 (AC1, AC2, AC3, AC13 resolver parity, AC27
  redaction).
- **LOW-risk AC:** 25.
- **Net new attack surface:** zero (threat model unchanged).
- **Net correctness surface:** 4 wiki_dir isolation leaks closed
  (engine.py:131, 214, 756 + health.py:68 + health.py:126); 1 silent-truncate
  upgraded to Error (core.py:357); 1 silent-failure regression risk mitigated
  with log (capture.py:211); 1 secret-leak path redacted (llm.py:4 sites).

Word count target (<4000 words): met.

---

*End of Step 5 decision. Proceed to Step 7 plan.*
