# Cycle 32 R1 Opus Design Evaluation

**Date:** 2026-04-25 · **Agent:** `a4234a0a6aa088d92` (Opus 4.7, 264s)

## Grep-verification table

| Symbol | Cited | File:Line | Status |
|---|---|---|---|
| `_is_mcp_error_response` | requirements.md:13,30,39 | `src/kb/cli.py:73-110` | EXISTS |
| `kb_compile_scan` | requirements.md:30, brainstorm.md:114 | `src/kb/mcp/core.py:891` | EXISTS |
| `kb_ingest_content` | requirements.md:13,41 | `src/kb/mcp/core.py:653` | EXISTS (emits `Error[partial]:` at :762; sibling at :881 in `kb_save_source`) |
| `_validate_wiki_dir` | threat-model.md:14, requirements.md:35 | `src/kb/mcp/app.py:141-164` | EXISTS |
| `_validate_file_inputs` | threat-model.md:16 | `src/kb/mcp/core.py:167-178` | EXISTS |
| `MAX_INGEST_CONTENT_CHARS` | threat-model.md:49,136 | `src/kb/config.py:407` (=`160_000`); imported `src/kb/mcp/core.py:57` | EXISTS |
| `SOURCE_TYPE_DIRS` | threat-model.md:31 | `src/kb/config.py:92` | EXISTS |
| `LOCK_POLL_INTERVAL` | requirements.md:15,51; C11 | `src/kb/utils/io.py:32` (=`0.05`) | EXISTS |
| `LOCK_INITIAL_POLL_INTERVAL` | CLAUDE.md "File locking" | `src/kb/utils/io.py:37` (=`0.01`) | EXISTS |
| `_backoff_sleep_interval` | threat-model.md:96 | `src/kb/utils/io.py:235-249` | EXISTS |
| `file_lock` | requirements.md §AC6, threat-model.md §B4 | `src/kb/utils/io.py:253-388` | EXISTS (retry-loop `try` at :292, single `finally` at :386) |
| `_error_exit` | requirements.md:60-70 (AC1) | `src/kb/cli.py:60-70` | EXISTS |
| `ERROR_TAG_FORMAT` | threat-model.md:18 | `src/kb/mcp/app.py:17` | EXISTS (only emitter template; no non-error occurrence) |
| `_rel` | threat-model.md:128 | `src/kb/mcp/app.py:116-133` | EXISTS (handles None + non-Path, scrubs project-root; does NOT scrub interpolated `{write_err}`) |

All 14 symbols verified. No SEMANTIC-MISMATCH. No MISSING.

**Legacy 3-tuple invariant peer scan:** Zero tests in `tests/` assert the 3-tuple literal; only `test_cycle31_cli_parity.py:40` mentions shapes in a docstring. Widening to 4 prefixes is safe per cycle-17 L1.

**AC3 same-class peer scan:** 6 occurrences of `Error[` in `src/kb/`, all error emitters/templates/comments/docstring. Zero legitimate non-error emitters. Widening is safe.

## Per-AC verdicts

- **AC1** APPROVE — thin-wrapper matches cycle-27/30/31 precedent; `_is_mcp_error_response` already routes compile-scan shapes even pre-AC3.
- **AC2** APPROVE — three tests per cycle-27 L2 + cycle-30 L2 + cycle-31 L3; strong-form `result.stderr` + `result.stdout == ""`.
- **AC3** APPROVE — single-literal widening; zero non-error emitters; revert-divergent test via integration path required.
- **AC4** APPROVE (with STRONG RECOMMENDATION to adopt C13 stat guard at Step 9).
- **AC5** **AMEND** — add 5th test: `CliRunner.invoke(cli, ["ingest-content", ..., "--use-api"])` + spy asserts `use_api=True` forwards verbatim. Pins Q3 resolution as grep-verifiable test.
- **AC6** **AMEND** — `_release_waiter_slot` MUST NOT silently clamp underflow. Replace `max(0, ...)` with `if _LOCK_WAITERS > 0: -= 1; else: logger.warning("_LOCK_WAITERS underflow")`. Counter drift must be observable.
- **AC7** APPROVE (with STRONG RECOMMENDATION: use `barrier.wait()` return value as first-entrant identifier).
- **AC8** **AMEND** — (a) explicit BACKLOG MEDIUM entry for T11 per C12, (b) CLAUDE.md §"File locking" paragraph contains "mitigation" + "intra-process only" + zero unqualified "fair-queue" (C8), (c) fair-queue entry at BACKLOG.md:125-126 DELETED (not strike-through) per lifecycle.

## Per-Q recommendations

- **Q1=B** — `click.File("r", lazy=False, encoding="utf-8")` with native `-`=stdin.
- **Q2=B** — optional, empty-string default; MCP authoritative.
- **Q3=no CLI enforcement** — MCP's documented "Ignored when use_api=True" handles it.
- **Q4=module-level int + threading.Lock** — `threading.local()` is wrong (each thread sees 0).
- **Q5=A (2ms)** — matches AC6 literal; at N=10 produces 18ms (well under 50ms cap).
- **Q6=A** — `threading.Thread` + `threading.Barrier(3)`, 10 trials, 80% tolerance. `max_workers=3` minimum.
- **Q7=A** — literal tuple (C-level `str.startswith(tuple)`); regex breaks grep-verifiable invariant.
- **Q8=no missed shape today** — suggest Step-11 grep `rg '[A-Z][a-z]+\[' src/kb/` to enumerate bracket-tagged emitters for future-proofing.

## Verdict summary

**AMEND** — AC5 (add `--use-api` test), AC6 (diagnostic warning on underflow), AC8 (T11 BACKLOG + CLAUDE.md language + delete fair-queue entry).

## Residual items for Step 5

- **R1 (AC5):** Add 5th test exercising `--use-api` forwarding.
- **R2 (AC6):** Replace silent clamp with `logger.warning` on underflow in `_release_waiter_slot`.
- **R3 (AC8):** Explicit BACKLOG MEDIUM entry for T11 (`core.py:762,881` path leakage); CLAUDE.md language discipline; DELETE BACKLOG.md:125-126 fair-queue entry.
- **Q5.5 (new, defer):** Observability counter helper `get_lock_waiter_max_position()` for post-ship thundering-herd metrics. Defer to post-ship follow-up.
