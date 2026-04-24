# Cycle 32 Threat Model

**Cycle:** 32 · **Date:** 2026-04-25 · **Branch:** `feat/backlog-by-file-cycle32`
**Scope:** CLI↔MCP parity category (b) closure (`kb compile-scan` + `kb ingest-content`), `_is_mcp_error_response` widening for `"Error["`, `file_lock` fair-queue stagger mitigation.

**Dispatched agent:** `aa4fe0b87c2592862` (Opus 4.7, 256s runtime).

---

## 1. Trust boundaries

Four boundaries are touched by this cycle:

**B1. Operator shell → CLI process (`kb compile-scan` / `kb ingest-content`).** Trusted side: CLI process. Data crossing: Click argv tokens (`--wiki-dir PATH`, `--filename SLUG`, `--type TYPE`, `--content-file PATH`, `--extraction-json-file PATH`, `--url URL`, `--use-api`, `--incremental/--no-incremental`). Existing controls: Click type coercion (`click.Path(exists=True, file_okay=...)`, `is_flag=True`); `sys.argv` is operator-controlled per cycle-7 contract (CLI is always invoked by a local operator, never network-exposed).

**B2. CLI wrapper → MCP tool callable (function-local import).** Trusted side: MCP layer (authoritative). Data crossing: Python-native positional/kwargs after Click parses argv. Existing controls: `kb_compile_scan` → `_validate_wiki_dir` (`src/kb/mcp/app.py:141-164` — absolute-path required, must exist, must be a dir, must resolve under `PROJECT_ROOT`); `kb_ingest_content` → `_validate_file_inputs` (`src/kb/mcp/core.py:167-178` — non-empty filename, ≤200 chars, content ≤`MAX_INGEST_CONTENT_CHARS`) + `slugify(filename)` + `SOURCE_TYPE_DIRS` whitelist + `os.O_EXCL` exclusive create.

**B3. MCP return-string → CLI stdout/stderr routing.** Trusted side: neither absolutely; the CLI discriminates. Data crossing: a plain `str` that may be a result body OR an error response. Existing controls: `_is_mcp_error_response()` (`src/kb/cli.py:73-110`) matches first-line prefix against `("Error:", "Error ", "Page not found:")` — AC3 widens to include `"Error["`.

**B4. Multi-process file-lock coordination (`utils/io.py`).** Trusted side: every same-UID waiter is cooperative (the lock is advisory — a malicious process can unlink the `.lock` sidecar). Data crossing: shared PID files on disk + a NEW module-level `_LOCK_WAITERS` counter (AC6, intra-process only). Existing controls: ASCII-only PID parse (`io.py:335-350`), stale-lock steal gated on `os.kill(pid, 0)` (`io.py:352-382`), exponential backoff with cap (`io.py:235-249`), lock-order convention at module docstring (`io.py:4-7`).

---

## 2. Data classification

| # | Item | Class | Cite |
|---|---|---|---|
| D1 | `--incremental/--no-incremental` (AC1) | operator-controlled | `cli.py` (new, AC1) |
| D2 | `--wiki-dir` PATH (AC1) | operator-controlled → validated at B2 | `cli.py` (new) + `app.py:141-164` |
| D3 | `--filename` SLUG (AC4) | operator-controlled → `_validate_file_inputs` + `slugify` | `core.py:681,685` |
| D4 | `--type` (AC4) | operator-controlled → `SOURCE_TYPE_DIRS` whitelist | `core.py:686-695` |
| D5 | `--content-file` PATH (AC4) | operator-controlled (CLI reads verbatim); content becomes filesystem-persisted under `raw/<type>/` | new |
| D6 | `--extraction-json-file` PATH (AC4) | operator-controlled → `json.loads` + dict shape check | `core.py:702-714` |
| D7 | `--url` URL passthrough (AC4) | operator-controlled → `yaml_escape` only | `core.py:718` |
| D8 | `--use-api` (AC4) | operator-controlled boolean | new |
| D9 | MCP return strings `"Error:"`, `"Error "`, `"Error[...]:"`, `"Page not found:"`, success bodies (AC3) | mcp-return-string | `cli.py:73-110`, `core.py:762`, `app.py:17` |
| D10 | `_LOCK_WAITERS: int` module-level counter (AC6) | process-local | `io.py` (new) |
| D11 | `position * _FAIR_QUEUE_STAGGER_MS / 1000` initial-sleep scalar (AC6) | process-local | `io.py` (new) |
| D12 | filesystem-persisted `raw/<type>/<slug>.md` (AC4) | filesystem-persisted | `core.py:697-764` |

---

## 3. Threat items

### T1: `--content-file` reads any operator-readable file outside project root

**STRIDE:** Information Disclosure (only if misused), Elevation of Privilege (bypass via file-copy)
**Attack surface:** `kb ingest-content --content-file PATH` — Click does NOT constrain the path to project root.
**Details:** Operator-controlled input path is legitimately allowed to read any readable file. This IS the point of the flag — `raw/` is the ingestion inbox. The threat is *unintentional leakage* (operator points at sensitive file, commits the resulting wiki page). `MAX_INGEST_CONTENT_CHARS` at `core.py:173-177` bounds the copy to a size cap.
**Required mitigation:** Step 9 MUST NOT add path-traversal rejection on `--content-file`. MUST document in CLI help that content is read verbatim into `raw/`. MUST NOT echo the file path in error output beyond what `_rel` scrubs. MUST NOT log content bytes on error.
**Existing control?** Partial — `MAX_INGEST_CONTENT_CHARS` caps bytes; `_sanitize_error_str` scrubs exception strings; no path-containment check (correct by design).

### T2: `--extraction-json-file` deserialisation DoS / type confusion

**STRIDE:** Denial of Service (parse cost), Tampering (malformed payload)
**Attack surface:** `click.File("r")` + `json.loads(f.read())` on operator-supplied path; raw content forwarded as `extraction_json` string.
**Details:** Operator can point at huge JSON file (100 MB) or deeply-nested object. `json.loads` is CPython-C and not easily DoS'd. MCP already parses at `core.py:704` → `JSONDecodeError` → `"Error: Invalid extraction JSON — {e}"` which AC3's widened discriminator routes to stderr + exit 1. Type check at `core.py:708-714` rejects non-dict.
**Required mitigation:** Step 9 MUST pass `--extraction-json-file` content as STRING (no client-side `json.loads`). Use `click.File("r", lazy=False)` to read once. `MAX_INGEST_CONTENT_CHARS` only bounds `content`, not `extraction_json` — Step-5 resolve cap size.
**Existing control?** Partial — MCP-side `json.loads` + type check covers malformed JSON but NO size cap on `extraction_json`.

### T3: `--url` passthrough YAML injection via operator-controlled URL

**STRIDE:** Tampering (YAML frontmatter injection)
**Attack surface:** `core.py:717-719` — `f'---\nurl: "{yaml_escape(url)}"\n...`
**Details:** `yaml_escape` is the defence — if operator passes `--url '" \ninjected: value\n#'`, escape MUST neutralise embedded newline + closing-quote. Existing ingest path has shipped this since cycle 6; CLI wrapper does NOT introduce a new bypass. CLI MUST forward `--url` verbatim (no decoration/strip) — client-side manipulation could re-break a carefully-escaped string.
**Required mitigation:** CLI forwards `--url` as raw `str` to `kb_ingest_content(url=url)`; NO `url.strip()`, NO URL re-validation.
**Existing control?** Yes — `yaml_escape` at `core.py:718`.

### T4: AC3 widening misclassifies a legitimate non-error MCP output beginning with `"Error["`

**STRIDE:** Denial of Service (false-positive exit 1 on success)
**Attack surface:** `_is_mcp_error_response()` widened prefix tuple `("Error:", "Error ", "Error[", "Page not found:")`.
**Details:** Same-class peer scan (§6) confirms EVERY current `"Error["` occurrence in `src/kb/` is an error emitter: `ERROR_TAG_FORMAT` at `mcp/app.py:17`; `Error[partial]:` at `mcp/core.py:762,881`; docstring at `cli.py:103`. All test-asserted forms (`Error[prompt_too_long]`, `Error[invalid_input]`, `Error[rate_limit]`, `Error[internal]`) at `tests/test_phase45_theme4_error_handling.py` are also error emitters.
**Required mitigation:** Step 11 grep MUST confirm zero legitimate (non-error) `"Error["` emitters. Step 9 MUST add regression test asserting `_is_mcp_error_response("Error[partial]: ...") is True` + same-class peer-scan docstring line referencing authoritative emitter set.
**Existing control?** Yes — helper classifies by FIRST-LINE only; empty output not an error.

### T5: AC3 regression test is revert-divergent

**STRIDE:** Defect Injection (revertable without test failure)
**Attack surface:** Cycle-24 L4 rule — regression test passing after fix revert is worthless.
**Details:** Test MUST exercise production call path. `_is_mcp_error_response("Error[partial]: ...")` must return True; `_is_mcp_error_response("# Title\n\nBody")` must return False.
**Required mitigation:** At least one AC3 test MUST be revert-divergent: `assert _is_mcp_error_response("Error[partial]: write failed; retry.") is True`. Plus CLI spy test: `CliRunner.invoke(cli, ["ingest-content", ...])` with MCP tool monkeypatched to return `"Error[partial]: ..."` → `exit_code == 1` + stderr contains `"Error[partial]"`.
**Existing control?** No — new AC3 coverage.

### T6: AC6 counter drift under exception paths

**STRIDE:** Denial of Service (permanently inflated stagger)
**Attack surface:** `_LOCK_WAITERS` module-level int — increment+unhandled-raise-before-decrement = monotonic drift.
**Details:** `file_lock` retry loop at `io.py:292-384` has several exception paths: `PermissionError` line 321, `OSError` from unparseable lock at 340/347, `TimeoutError` at 374/379/382. If increment is outside outermost `try/finally`, any of these leaks a waiter. Cycle 24's `acquired` is tracked by separate `try/finally` at `io.py:292,386`; AC6 MUST use SAME outer `try/finally`. Counter MUST be guarded by own `threading.Lock` on increment/decrement — naked `+=` on Python int is NOT atomic under GIL.
**Required mitigation:** `_LOCK_WAITERS` increment at TOP of outer try-block (BEFORE `while not acquired:`) and decrement in `finally:`. Guard by separate `threading.Lock`. Regression test asserts `_LOCK_WAITERS == 0` after raised `TimeoutError`.
**Existing control?** No — new.

### T7: AC6 stagger × exponential-backoff double-compounding

**STRIDE:** Denial of Service (unbounded acquire latency)
**Attack surface:** `_backoff_sleep_interval(attempt_count)` at `io.py:235-249` already returns up to `LOCK_POLL_INTERVAL=50ms`. AC6 stagger adds `position * 2ms` to FIRST sleep.
**Details:** If AC6 applies stagger to EVERY sleep, N=50 waiter adds `50 * 2ms = 100ms` to every retry — exceeding `LOCK_POLL_INTERVAL`. AC6 text specifies "FIRST `time.sleep(...)`" (singular) — Step 9 MUST apply stagger to first sleep ONLY. Stagger MUST be clamped.
**Required mitigation:** Step 9 MUST implement stagger as one-shot `time.sleep(min(position * STAGGER_MS / 1000, LOCK_POLL_INTERVAL))` BEFORE `while not acquired:` loop (or as guarded first-iteration branch). Regression test asserts N=1 waiter sees zero stagger.
**Existing control?** No — new.

### T8: AC6 fair-queue is mitigation only; advertised semantics must not oversell

**STRIDE:** Repudiation (doc-drift)
**Attack surface:** AC6 + AC8 documentation — "fair-queue" as a term implies a guarantee.
**Details:** Per cycle-28 L1 literal-ordering rule, docs MUST use "mitigation" (not "fix", not "guarantee"). Stagger improves N=2-3 thundering-herd case but doesn't prevent starvation under coarse-resolution `time.monotonic()` (Windows 15.6ms default) or preemption.
**Required mitigation:** AC8 CLAUDE.md note MUST include "mitigation" explicitly; MUST NOT use "guarantee"/"fair"; MUST state "intra-process only". Module docstring at `io.py:1-12` MUST add paragraph describing `_LOCK_WAITERS` semantics.
**Existing control?** Partial — requirements doc is clear; risk is in downstream doc-copy.

### T9: Operator-controlled `--wiki-dir` (AC1/AC2) boolean-flag inversion UX surface

**STRIDE:** Tampering (wrong-project writes), Information Disclosure (scanning wrong raw tree)
**Attack surface:** `kb compile-scan --wiki-dir /some/path --no-incremental` — flag inversion may surprise operator.
**Details:** `_validate_wiki_dir` closes path traversal. Remaining threat is UX — not security.
**Required mitigation:** AC2 test asserts `incremental=True` (default) AND `incremental=False`. CLI help string MUST include "default: incremental".
**Existing control?** Yes — `_validate_wiki_dir` closes traversal.

### T10: AC6 integer overflow on `_LOCK_WAITERS`

**STRIDE:** N/A (Python bigint)
**Attack surface:** Counter drift from unsymmetric mutation.
**Details:** Python ints don't overflow; risk zero if T6/T7 mitigations land (T7's clamp caps stagger regardless of counter magnitude).
**Required mitigation:** T6 try/finally + T7 stagger clamp.
**Existing control?** Yes once T6+T7 land.

### T11: Post-create OSError path echoes filesystem path in MCP error string

**STRIDE:** Information Disclosure (path leakage to operator terminal)
**Attack surface:** `core.py:762` — `f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); retry..."`. Via AC3 widening, this NOW routes to `click.echo(output, err=True)` instead of silent exit 0.
**Details:** `_rel()` scrubs `file_path` but `{write_err}` interpolation may include un-scrubbed absolute path on Windows (`[WinError 5] Access is denied: 'D:\\...'`).
**Required mitigation:** Step 9 OUT OF SCOPE for MCP-tool refactoring (non-goal). Step 11 grep flags as pre-existing data-leak concern. AC8 doc sync notes "AC3 newly routes Error[partial]: strings to stderr; underlying emitter does not sanitise write_err." **File BACKLOG entry for future cycle.**
**Existing control?** Partial — `_rel(file_path)` scrubs path but `{write_err}` interpolation bypasses it.

### T12: `--content-file` large-file read DoS

**STRIDE:** Denial of Service (memory/time)
**Attack surface:** `click.File("r")` with no size cap reads entire file before passing to MCP.
**Details:** Click will `f.read()` a 2 GB file into memory; MCP rejects at `core.py:173-177` AFTER full read. CLI should stat-then-read to fail fast.
**Required mitigation:** Step 9 SHOULD stat `--content-file` BEFORE read and reject `st_size > MAX_INGEST_CONTENT_CHARS` with clean error. Not strictly security (operator trusted) but matches `_validate_file_inputs` philosophy.
**Existing control?** Partial — MAX bytes cap at MCP is POST-read.

---

## 4. Required CONDITIONS

**C1.** AC3 regression test MUST be revert-divergent per cycle-24 L4: ≥1 test asserts `_is_mcp_error_response("Error[partial]: write failed; retry.") is True` AND ≥1 asserts widened tuple's behaviour through full `CliRunner.invoke(cli, ["ingest-content", ...])` path where `kb_ingest_content` is monkeypatched to return `"Error[partial]: ..."` → `result.exit_code == 1` + `"Error[partial]" in result.stderr`. Grep-verifiable: `rg 'Error\[partial\]' tests/test_cycle32_*.py` returns ≥2 assertions.

**C2.** AC3 same-class peer scan — Step 11 grep `rg 'Error\[' src/kb/` must confirm exactly the known emitters: `src/kb/mcp/app.py:17`, `src/kb/mcp/core.py:762,881`, docstring at `src/kb/cli.py:103`. Zero legitimate non-error emitters. Test using `inspect.getsource` is signature-only (feedback_inspect_source_tests) — prefer direct string assertion.

**C3.** AC6 counter symmetry — regression test asserts that after raised `TimeoutError` inside `file_lock` (held lock file + deadline = 0), `kb.utils.io._LOCK_WAITERS == 0` when exception is caught. Grep-verifiable: `rg '_LOCK_WAITERS' src/kb/utils/io.py` shows exactly TWO mutations (increment + decrement) both inside ONE outermost `try/finally`.

**C4.** Context7 MUST be consulted for Click 8.3+ semantics: (a) `click.File("r", lazy=False)` exception on bad content (binary in text mode), (b) `click.Path(exists=True)` with `file_okay=True, dir_okay=False`, (c) `is_flag=True` + `default=True` interaction with `--no-flag` auto-inverse (per cycle-31 L1 mandatory-Context7 rule). Step 6 cites Context7 query or Click changelog.

**C5.** AC6 hot-path peer scan — Step 11 grep confirms 25+ `file_lock(` call sites remain on unchanged `.lock` sidecar contract; no call site depends on `_LOCK_WAITERS` being specific value. Grep-verifiable: `rg 'file_lock\(' src/kb/` count unchanged pre/post cycle 32.

**C6.** AC7 probabilistic ordering test MUST use `max_workers >= 3` AND assert over ≥10 trials with 80% tolerance to OS thread-scheduling jitter. Test MUST NOT use `time.sleep(0)` or `Thread.join()` tricks that serialise workers — use `threading.Barrier` or microsleep stagger. Grep-verifiable: `rg 'ThreadPoolExecutor|threading\.Barrier' tests/test_cycle32_*.py` shows fixture; `rg 'max_workers=3' tests/test_cycle32_*.py`.

**C7.** AC4 CLI reads `--content-file` / `--extraction-json-file` WITHOUT client-side `json.loads` or text manipulation on `--url`: values passed to `kb_ingest_content` MUST be byte-identical to file contents (content) and argv token (url). Grep-verifiable: `rg -n 'json\.loads|url\.strip' src/kb/cli.py` after Step 9 returns no new matches in `ingest-content` function body.

**C8.** AC8 CLAUDE.md §"File locking" note MUST contain word "mitigation" (not "guarantee"); MUST state "intra-process only"; MUST NOT reference `threading.local()`. Grep-verifiable: cycle-32 paragraph in CLAUDE.md contains "mitigation" AND "intra-process only"; `rg -i 'guarantee|fair-queue' CLAUDE.md` does not match cycle-32 paragraph.

**C9.** AC1/AC2 CLI help text on `--incremental` MUST state "default: incremental". Grep-verifiable: `rg -A2 'incremental' src/kb/cli.py` shows help string.

**C10.** `_LOCK_WAITERS` and its guarding `threading.Lock` MUST be DEFINED at module level in `src/kb/utils/io.py` (NOT `threading.local()` per Q4). Grep-verifiable: `rg '_LOCK_WAITERS' src/kb/utils/io.py` shows module-level `_LOCK_WAITERS: int = 0` + sibling `_LOCK_WAITERS_LOCK`.

**C11.** AC6 stagger scalar `position * _FAIR_QUEUE_STAGGER_MS / 1000` MUST be clamped to `LOCK_POLL_INTERVAL` to prevent T7 double-compounding. Grep-verifiable: `rg 'min\(.*_FAIR_QUEUE_STAGGER' src/kb/utils/io.py` shows the clamp.

**C12.** T11 pre-existing leak — file a BACKLOG MEDIUM entry referencing `src/kb/mcp/core.py:762,881` and noting AC3 newly routes those strings to CLI stderr. Do NOT attempt MCP-tier fix in cycle 32 per non-goals.

**C13.** T12 `--content-file` large-file stat guard — Step 9 SHOULD `os.stat` the path and reject `st_size > MAX_INGEST_CONTENT_CHARS` with early error BEFORE reading. Grep-verifiable: `rg 'st_size|stat\(\)' src/kb/cli.py` shows the guard after Step 9.

---

## 5. Logging / audit surface

**MUST emit:**

- `file_lock` AC6: keep existing `logger.warning` on legacy-lock purge / write-failure / orphan-unlink. No new INFO for every acquire (would spam). OPTIONAL: `logger.debug` when stagger > 0.
- `kb compile-scan`: `click.echo(output, err=True)` on error; `click.echo(output)` on success.
- `kb ingest-content`: same routing; success body includes MCP's `Saved source: ... (N chars)` + `_format_ingest_result` body.

**MUST NOT emit:**

- Full absolute paths on CLI error surface (per T11 — pre-existing but newly routed).
- `content` bytes on error. MCP's `_validate_file_inputs` returns byte counts only.
- `extraction_json` value on error. `core.py:706` `"Error: Invalid extraction JSON — {e}"` with `{e}` from `json.JSONDecodeError` — accept pre-existing behaviour.
- Stack traces unless `KB_DEBUG=1` / `--verbose` (existing `_error_exit` discipline `cli.py:60-70`).
- `_LOCK_WAITERS` value on error — intra-process diagnostic, NOT user-facing.

**Side effects:**
- `kb ingest-content` on success writes `raw/<type>/<slug>.md` via existing `os.O_EXCL`; wiki pages per normal ingest.
- `_LOCK_WAITERS` mutation on every `file_lock` acquire (new). No disk write.

---

## 6. Same-class peer scan

**AC3 widening — `rg 'Error\[' src/`:**

| File:line | Form | Classification |
|---|---|---|
| `src/kb/mcp/app.py:17` | `ERROR_TAG_FORMAT = "Error[{category}]: {message}"` | Error template |
| `src/kb/mcp/core.py:730` | `# Cycle 4 item #5 — convert post-create OSError into Error[partial]` | Comment |
| `src/kb/mcp/core.py:762` | `f"Error[partial]: write to {_rel(file_path)} failed ..."` | Error emitter (kb_ingest_content) |
| `src/kb/mcp/core.py:853` | `# Cycle 4 item #5 — convert post-create OSError into Error[partial]` | Comment |
| `src/kb/mcp/core.py:881` | `f"Error[partial]: write to {_rel(file_path)} failed ..."` | Error emitter (kb_save_source) |
| `src/kb/cli.py:103` | Docstring: `Tagged-error form ``Error[<category>]: ...``` | Docstring cross-ref |

**Verdict:** Zero legitimate non-error outputs begin with `"Error["`. Widening is safe. Tests at `test_phase45_theme4_error_handling.py:125,145,165,181,200` corroborate — every `Error[<tag>]` asserted is an error assertion.

**AC6 fair-queue — `file_lock(` call sites in `src/kb/`:**

Hot paths:
1. `src/kb/compile/compiler.py:227,478,522,542,720` — manifest RMW. Single-writer hot path.
2. `src/kb/ingest/pipeline.py:272,1541` — duplicate-hash check + final-hash write.
3. `src/kb/ingest/pipeline.py:615,957` — per-page body update + jsonl rotation.
4. `src/kb/ingest/pipeline.py:196` — contradictions RMW.
5. `src/kb/ingest/evidence.py:193` — evidence trail sidecar lock.
6. `src/kb/compile/linker.py:242,495` — wikilink injection per-page. N ≥ 2 possible.
7. `src/kb/review/refiner.py:113,250,447` — two-phase refine. Nested lock: page_path FIRST, history_path SECOND.
8. `src/kb/lint/verdicts.py:194` — verdict store RMW.
9. `src/kb/lint/_augment_rate.py:86` — augment rate-limiter.
10. `src/kb/lint/_augment_manifest.py:95,153,173,200` — augment state machine.
11. `src/kb/utils/wiki_log.py:149` — wiki log append.

**Verdict:** Majority single-writer / low-N. Genuinely concurrent cases: (a) `compile/linker.py:242,495` — different `page_path` per worker, low cross-lock contention; (b) `ingest/pipeline.py:272` + `compile/compiler.py:227` — manifest path is exactly AC6's target starvation case; (c) `review/refiner.py` nested. Under T7's clamp (stagger ≤ `LOCK_POLL_INTERVAL`), no hot path is negatively affected. N=1 paths see zero change per AC6 text.

---

## 7. Verdict summary

`PROCEED`

The threat surface is well-contained. AC3 widening is safe per same-class peer scan. AC6 requires C3 + C10 + C11 to prevent counter drift (T6) and stagger/backoff double-compounding (T7), plus C4 Context7 on Click 8.3+ before Step 9 ships. AC4's file-path flags are operator-controlled by design; T1 and T2 are UX concerns, not security bugs. Step 11 grep-verifies C1-C13. T11 (pre-existing absolute-path leakage) noted in cycle decision doc + filed as BACKLOG MEDIUM per C12, OUT OF SCOPE per requirements non-goals.

**Baselines for Step 11 CVE diff:** 2 pre-existing vulns (diskcache CVE-2025-69872, ragas CVE-2026-6587), both no-upstream-fix, both in BACKLOG. Class A only. Baseline file: `.data/cycle-32/cve-baseline.json`. Dependabot: 1 open (ragas GHSA-95ww-475f-pr4f, low).
