# Cycle 32 — Requirements + Acceptance Criteria

**Date:** 2026-04-25
**Branch:** `feat/backlog-by-file-cycle32`
**Scope:** Close the CLI↔MCP parity gap category (b) + `utils/io.py` file_lock fair-queue starvation mitigation.

---

## Problem

**Primary.** CLI↔MCP parity remains open for category (b): `kb_ingest_content` and `kb_compile_scan` MCP tools have no dedicated CLI wrappers. Operators relying on the `kb` CLI must shell out via `python -m kb.mcp_server` or invoke through Claude Code instead. Cycles 27/30/31 established and shipped 12 thin-wrapper CLI commands (function-local MCP tool import + shared `_is_mcp_error_response` discriminator); cycle 32 extends the pattern to close category (b) completely.

A real bug surfaced during Step 1 grep-verification: `kb_ingest_content` emits `"Error[partial]: write to ... failed ..."` on post-create OSError at `src/kb/mcp/core.py:762`. The current `_is_mcp_error_response` helper at `src/kb/cli.py:73-110` explicitly does NOT match the `Error[<category>]:` tagged-error form (docstring notes T9 future-proofing). A naive thin wrapper over `kb_ingest_content` would silent-exit-0 on partial writes — the exact silent-exit-0 bug class cycle 31 AC8 closed for cycle-27/30 wrappers. AC3 below mandates the helper widening.

**Secondary.** `utils/io.py` `file_lock` has residual fair-queue / starvation risk under N-waiter contention. Cycle 24 AC9 added exponential backoff (floor 10ms, cap `LOCK_POLL_INTERVAL=50ms`) but did not add fair queueing or staggering. The Phase 4.5 MEDIUM entry at BACKLOG.md:125-126 calls out: *"waiters can be out-raced by newer entrants. Residual under sustained contention."* A simple per-process waiter counter + stagger mitigates the thundering-herd case.

## Non-goals

- **Write-path MCP tools** (`kb_review_page` / `kb_refine_page` / `kb_query_feedback` / `kb_save_source` / `kb_save_lint_verdict` / `kb_create_page` / `kb_capture`) remain DEFERRED per BACKLOG.md:146 — "deferred to a write-path input-validation cycle". Cycle 32 does NOT ship CLI wrappers for these; they require dedicated input-validation design.
- **Refactoring `kb ingest` / `kb compile` existing CLI commands.** The new `kb ingest-content` / `kb compile-scan` are SIBLINGS to the existing surfaces, not replacements.
- **No new MCP tools.** Wrappers only; MCP surface is unchanged.
- **No broader file-lock architecture changes** (fcntl replacement, distributed locks, per-process fair-queue guarantee). The fair-queue fix is a mitigation, not a guarantee. The cooperative `.lock` sidecar contract is preserved.
- **No structured `--format=json` output** across CLI surfaces (tracked separately at BACKLOG.md:146).
- **No Phase 5 items.** Per user direction: "before Phase 5 items."

## Acceptance Criteria

### Category (b) CLI parity — `kb compile-scan`

**AC1.** `kb compile-scan [--incremental/--no-incremental] [--wiki-dir PATH]` CLI subcommand exposes `kb_compile_scan` MCP tool via function-local MCP tool import (cycle 27+ thin-wrapper pattern). Default `--incremental` matches MCP default. Exit 0 on MCP success; exit 1 when `_is_mcp_error_response(output)` is True. Error output routed via `click.echo(output, err=True)` per cycle-31 L3.

**AC2.** AC1 test coverage per cycle-27 L2 + cycle-30 L2 + cycle-31 L3:
- Happy-path body-spy test: `monkeypatch.setattr(kb.mcp.core, "kb_compile_scan", spy)` + `CliRunner.invoke(cli, ["compile-scan"])` + `assert called["value"] is True` + spy receives `incremental=True, wiki_dir=None`.
- Raw-forwarding spy test: `CliRunner.invoke(cli, ["compile-scan", "--no-incremental", "--wiki-dir", "/tmp/x"])` + spy receives `incremental=False, wiki_dir="/tmp/x"` verbatim (no CLI-side transformation).
- Error-path integration test: use `tmp_kb_env` + monkeypatch `_validate_wiki_dir` to return `(None, "invalid wiki dir")` → exit 1 + `"Error:" in result.stderr` + `result.stdout == ""` (strong-form per cycle-31 L3).

### Category (b) CLI parity — `kb ingest-content`

**AC3.** Extend `_is_mcp_error_response` to match the `"Error["` tagged-error prefix. Current helper matches `("Error:", "Error ", "Page not found:")`; widen to `("Error:", "Error ", "Error[", "Page not found:")`. Update docstring to remove the "NOT matched" paragraph for tagged-error and replace with "Matched as of cycle 32 — extended for `kb_ingest_content` Error[partial]: emitter." Add ≥1 regression test asserting `_is_mcp_error_response("Error[partial]: write failed; retry.") is True` AND `_is_mcp_error_response("Error[validation]: bad input") is True` AND `_is_mcp_error_response("Error[ X")` edge-case (no closing bracket — still matches `"Error["` prefix, same class).

**AC4.** `kb ingest-content --filename SLUG --type TYPE --content-file PATH [--extraction-json-file PATH] [--url URL] [--use-api]` CLI subcommand exposes `kb_ingest_content` MCP tool. Design decisions deferred to Step 5: (a) whether `--content-file` accepts `-` for stdin, (b) whether `--extraction-json-file` is required when `--use-api` is False, (c) how to handle `--use-api` + `--extraction-json-file` conflict. AC4 guarantees only: all MCP args are forwarded verbatim via function-local import; exit 0 on success; exit 1 on `_is_mcp_error_response(output)` True (now including `Error[partial]:` via AC3).

**AC5.** AC4 test coverage:
- Happy-path body-spy test with minimal args + extraction JSON from file.
- Error-path integration test: `kb ingest-content --filename "bad!!!" --type article --content-file <valid-file>` → MCP tool rejects slug via `_validate_file_inputs` → exit 1 + `"Error:" in result.stderr` + `result.stdout == ""`.
- Error[partial] boundary test using `--use-api=False` path with post-create OSError simulation via monkeypatch (or direct discriminator test per AC3).
- Raw-forwarding spy test confirming flags forward unchanged.

### `utils/io.py` fair-queue starvation mitigation

**AC6.** `utils/io.py` `file_lock` gains a module-level `_LOCK_WAITERS: int` counter (ordinary int, guarded by `threading.Lock` on increment/decrement) AND a per-lock-acquisition stagger: when a waiter enters the retry loop, it samples `_LOCK_WAITERS` position BEFORE incrementing and uses that position to scale its FIRST `time.sleep(...)` by `position * _FAIR_QUEUE_STAGGER_MS / 1000` (where `_FAIR_QUEUE_STAGGER_MS = 2`). Waiter decrements on exit (success, timeout, KeyboardInterrupt — all via try/finally). Zero behaviour change on single-waiter lock acquisitions; under N ≥ 2 waiters, each subsequent entrant gets `2N ms` extra initial delay. Does NOT change the lock acquisition contract; fairness improvement is probabilistic, not guaranteed.

**AC7.** AC6 regression test — probabilistic ordering test via `concurrent.futures.ThreadPoolExecutor(max_workers=3)`: submit 3 workers staggered by small microsleep, each attempting `file_lock(tmp_lock_path)`, each recording acquire-order to a shared list. Assert `acquire_order[0] <= acquire_order[2]` (first-entering waiter acquires no later than last-entering) at least 80% of the time across 10 trials. Tolerant to OS-level thread scheduling jitter.

**AC8.** Documentation sync. CLAUDE.md CLI count bumped 22 → 24 (adds `compile-scan` + `ingest-content`); §"File locking" note mentions cycle-32 fair-queue stagger; BACKLOG CLI↔MCP parity note updated 9 → 7 remaining (all 7 category (a) write-path, still deferred) AND fair-queue entry at BACKLOG.md:125-126 deleted as resolved; CHANGELOG + CHANGELOG-history entries per cycle conventions with `+TBD commits` placeholder (cycle-30 L1).

## Blast radius

- `src/kb/cli.py` — 2 new Click subcommands + 1-line tuple widening in `_is_mcp_error_response` (+~80 LOC prod total).
- `src/kb/utils/io.py` — counter + stagger logic inside `file_lock` (+~25 LOC prod).
- `tests/test_cycle32_cli_parity_and_fair_queue.py` — new test file (~15 tests, ~250 LOC).
- `CLAUDE.md`, `CHANGELOG.md`, `CHANGELOG-history.md`, `BACKLOG.md` — doc sync only.

No changes to `src/kb/mcp/*.py`, `src/kb/ingest/*.py`, `src/kb/compile/*.py`, `src/kb/query/*.py`, `src/kb/lint/*.py`. Threat-model boundary unchanged (CLI forwards; MCP remains authoritative).

## Open questions (resolve at Step 5)

- **Q1.** Should `kb ingest-content --content-file` accept `-` for stdin? (Default NO unless brainstorm/design-eval surfaces strong operator demand; cycle-31 minimal-wrapper pattern favoured simplicity.)
- **Q2.** When `--use-api=False` (default), should `--extraction-json-file` be required at CLI level (`required=True`), or defer to MCP-side validation (MCP returns `"Error: Invalid extraction JSON"` when empty)?
- **Q3.** `kb ingest-content` has `--use-api` flag mirroring MCP; should CLI reject `--use-api --extraction-json-file X` as mutually-exclusive at click level, or defer to MCP tool which documents `extraction_json` as "Ignored when use_api=True"?
- **Q4.** Fair-queue counter: module-level `_LOCK_WAITERS: int` or `threading.local()`? Module-level shares across threads in one process (correct for cross-thread fairness); `threading.local()` would be per-thread (wrong — each thread would see 0). Confirm module-level.
- **Q5.** Fair-queue stagger constant `_FAIR_QUEUE_STAGGER_MS = 2` — is 2ms too small to observe fairness? Too large slows acquisition unnecessarily. Pin the constant at Step 5 based on `LOCK_POLL_INTERVAL=50ms` proportions.
- **Q6.** Should AC7 test `max_workers` be `3`, `5`, or `10`? Higher N gives more stable probabilistic signal but burns more test time.
- **Q7.** AC3 widening — should the prefix tuple be `("Error:", "Error ", "Error[", "Page not found:")` (4 literals) OR regex `r"^(Error[\[:\s]|Page not found:)"` (one pattern)? Literal tuple is faster + simpler; regex handles future shapes. Prefer literal tuple with docstring pointer to cycle-32.
- **Q8.** Is there any tagged-error form NOT starting with `Error[` that we'd miss? Grep cost ~30s.
