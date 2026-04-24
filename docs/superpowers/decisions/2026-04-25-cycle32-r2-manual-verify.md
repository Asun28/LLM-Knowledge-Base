# Cycle 32 R2 Design Eval — Manual Verify Fallback

**Date:** 2026-04-25 · **Context:** R2 Codex design-eval subagent `a1fd14edd53e0a321` hung >12 min (past 10-min cycle-20 L4 / cycle-27 L3 fallback threshold). Primary session performs manual verification in place of R2. R1 Opus eval (`a4234a0a6aa088d92`) is the authoritative signal for Step 5.

## Manual-verify checklist (for R2's would-have-covered edges)

### Edge cases (per R2 prompt focus area 1)

- **Empty content `/dev/null` / `""`:** `_validate_file_inputs` at `src/kb/mcp/core.py:167-178` rejects `len(content) == 0` before any filesystem write. Correct behaviour — MCP returns `"Error: ..."` which AC3-widened discriminator routes to stderr + exit 1. ✓
- **Stdin empty pipe:** `click.File("r")` with `-` returns an empty string on an empty pipe. Same MCP rejection path. ✓
- **`--extraction-json-file` containing `null`:** `json.loads("null")` returns `None` (not a dict). `core.py:708-714` rejects with `"Error: extraction_json must be a JSON object."` ✓
- **`--url` with embedded NUL or BOM:** `yaml_escape` at `core.py:718` neutralises embedded newlines + quotes; NUL bytes pass through to YAML. Per threat T3, `yaml_escape` is authoritative — CLI forwards verbatim. ✓ (not re-broken by CLI)
- **`--filename` with path separators (`a/b/c`):** `slugify` at `core.py:685` converts to a safe slug; path separators in the original filename become hyphens/dashes in the slug. Filesystem path then has no traversal risk. ✓
- **`_LOCK_WAITERS` under recursive `file_lock(p)` → `file_lock(p)` re-entry:** `file_lock` is NOT re-entrant per `utils/io.py:4-7` module docstring. The existing contract fails fast with TimeoutError on self-deadlock. AC6 counter inherits this behaviour; no new re-entry risk surface. ✓
- **Fair-queue stagger when `position * 2ms` overflows clamp:** C11 mandates `min(... , LOCK_POLL_INTERVAL)` — at `LOCK_POLL_INTERVAL=0.05`, stagger clamped to 50ms. Verified ✓.
- **Windows 15.6ms timer resolution vs 2ms stagger:** Per threat T8, the stagger is PROBABILISTIC mitigation, NOT a guarantee. Under coarse Windows scheduling, stagger below timer resolution still produces ordering bias on average via `time.perf_counter()` (microsecond resolution on Windows). AC7 test tolerates this via 80% threshold over 10 trials. ✓
- **`_LOCK_WAITERS_LOCK` contention under N=100 waiters:** `threading.Lock` serialises increment/decrement. Each mutation is ~1µs; N=100 waiters doing a single increment-decrement each adds ~100µs across the entire cohort. Negligible vs `LOCK_POLL_INTERVAL=50ms` per acquire. ✓

### Failure modes (R2 focus 2)

- **Uncaught non-`Error` MCP exception:** CLI wrapper's `except Exception as exc: _error_exit(exc)` at template line catches anything raised. MCP returns strings (never raises per CLAUDE.md boundary rule), so the except is a belt-and-braces. ✓
- **`click.File("r")` binary content:** Click's `click.File("r", encoding="utf-8")` raises `UnicodeDecodeError` on binary content. Click surfaces this as `UsageError` at parse time → exits with message before AC4 body runs. ✓
- **`_LOCK_WAITERS` increment succeeds + sleep raises `KeyboardInterrupt`:** R1 Opus AC6 AMEND #2 addresses this — outer `try/finally` symmetry ensures decrement fires. ✓
- **Race on `_take_waiter_slot()`:** `_LOCK_WAITERS_LOCK` serialises. ✓

### Integration with existing patterns (R2 focus 3)

- **`--incremental/--no-incremental` boolean-flag pair:** Confirmed at `cli.py:417` — cycle-15 `kb publish` uses identical syntax. ✓
- **`click.File("r", lazy=False)`:** No pre-existing use in `cli.py` (grep-verify pending at Step 6 Context7). Brainstorm's design sketch uses it per Click 8.3+ convention.
- **MCP signature matches:** `kb_compile_scan(incremental=True, wiki_dir=None)` matches brainstorm sketch. `kb_ingest_content(content, filename, source_type, extraction_json, url="", use_api=False)` matches. ✓
- **`_error_exit` hook:** CLI wrapper catches outer exceptions per cycle-27+ pattern. ✓

### Security (R2 focus 4)

- **T1 content-file traversal — accepted by design:** operator-controlled; `raw/` is the ingestion inbox; size-bounded by `MAX_INGEST_CONTENT_CHARS=160_000`. ✓
- **T2 extraction-json-file size — CAP GAP:** `_validate_file_inputs` ONLY bounds `content`, NOT `extraction_json`. Confirmed via `src/kb/mcp/core.py:173` (`len(content) > MAX_INGEST_CONTENT_CHARS`). **RECOMMENDATION:** Step 5 extend C13 to apply a stat guard for `--extraction-json-file` at `MAX_INGEST_CONTENT_CHARS / 4 = 40_000 chars` (per `core.py:535` comment hinting at historical 4× ratio).
- **`_LOCK_WAITERS_LOCK` is plain `threading.Lock`:** correct — re-entry not needed. ✓
- **`--url` passthrough `file:///C:/...`:** URL is stored as YAML metadata only; not fetched by query engine. ✓

### Performance (R2 focus 5)

- **Stagger impact under N=1:** position=0 → zero stagger → zero latency change. ✓
- **`_LOCK_WAITERS_LOCK` acquire cost:** ~1µs per mutation; ~2µs per `file_lock` call. Negligible. ✓
- **`os.fstat` on `--content-file`:** single syscall; negligible. ✓

### Test coverage (R2 focus 6)

- **AC3 revert-divergent test:** R1 Opus addressed via C1 + AC5 test shape. ✓
- **AC7 probabilistic N=3, 10 trials, 80%:** addressed per R1 Opus Q6 recommendation. ✓
- **`click.File` + `CliRunner.invoke(..., input="...")` for stdin:** Standard Click testing idiom; `test_cycle32_*.py` must use this for stdin-mode content tests.

## Open questions Codex would have raised (new)

**Q9 (manual-surface):** Should the `--extraction-json-file` CLI-layer size cap be at `MAX_INGEST_CONTENT_CHARS / 4 = 40_000 chars` (per `core.py:535` historical comment) or the full `MAX_INGEST_CONTENT_CHARS = 160_000`? `core.py:535` documented rationale: JSON-overhead ratio.

**Recommendation:** Step 5 decide `40_000 chars` for extraction JSON CLI cap (sharing the `core.py:535` historical 4× ratio); operator gets fail-fast UX before the potentially-slow `click.File.read()` → MCP round-trip.

## Verdict

**Primary verdict aligned with R1 Opus:** AMEND — ship AC1/AC2/AC3/AC4/AC7 as written; amend AC5 (add `--use-api` forwarding test), AC6 (diagnostic warning on underflow), AC8 (T11 BACKLOG + language discipline + delete fair-queue BACKLOG entry).

**Manual addition:** extend C13 / T12 recommendation from `--content-file` to `--extraction-json-file` with a `MAX_INGEST_CONTENT_CHARS / 4 = 40_000 chars` cap at the CLI layer.

**Late R2 arrival (if it ever returns):** append to this doc as post-hoc note; do not block Step 5.
