# Cycle 32 Brainstorm

**Cycle:** 32 · **Date:** 2026-04-25 · **Branch:** `feat/backlog-by-file-cycle32`

Per user-memory `feedback_auto_approve`, this cycle runs zero human-in-the-loop; brainstorm presents 2-3 approaches per open question. Step 5 decision gate commits verdicts via `## Analysis` scaffold (cycle-25 L1 discipline).

Structural choices already pinned by Step 1 requirements + Step 2 threat model:
- Thin-wrapper pattern (cycle 27+) — function-local MCP tool import + `_is_mcp_error_response` discriminator.
- Module-level `_LOCK_WAITERS` counter guarded by `threading.Lock` (C10 + T6).
- Revert-divergent regression tests on production call path (C1 + cycle-24 L4).
- Stagger clamp to `LOCK_POLL_INTERVAL` (C11 + T7).
- Context7 MANDATORY for Click 8.3+ semantics (C4 + cycle-31 L1).

---

## Q1. `--content-file` input modes

**A. File-only (`click.Path(exists=True, dir_okay=False)`)** — Path must exist, cannot be a directory. Operator must save content to disk before invoking. Simplest to test.

**B. File with stdin shorthand (`--content-file -` = stdin)** — Convention matches many Unix tools; `click.File("r")` natively interprets `-` as stdin. Operator can pipe: `curl URL | kb ingest-content --content-file - --filename X --type article`.

**C. Explicit `--stdin` flag + optional `--content-file`** — Two mutually-exclusive flags. Verbose but explicit. Overkill for a CLI wrapper.

**Tradeoffs:** A is simplest; B is standard Unix ergonomic (stdin-via-`-` is common); C adds surface area. T2 threat model notes stdin + file both legitimate; no security delta between A and B since operator controls both.

**Recommendation:** **B (file with stdin shorthand)**. Use `click.File("r", lazy=False, encoding="utf-8")`. `lazy=False` reads on parse so Click emits clean errors for unreadable/binary files. Size guard per T12/C13 via `hasattr(file_obj, 'seek')` + `os.fstat`. Documentation in help text: "`--content-file -` reads from stdin."

## Q2. `--extraction-json-file` required vs optional with `--use-api`

**A. `required=True` always** — Operator must always pass the flag. MCP-tier `use_api=True` ignores the content, but CLI forces the arg. Simplest but wastes operator time when `--use-api` is set.

**B. `required=False`; default `""` passthrough** — CLI defaults to empty string; MCP tool either parses (if `use_api=False`) and raises `"Error: Invalid extraction JSON — ..."`, or ignores (if `use_api=True`). Click accepts the flag or not. Delegates all validation to MCP.

**C. Click-level mutual-exclusion enforcement** — When `--use-api` flag present, reject `--extraction-json-file`; when not present, require `--extraction-json-file`. Enforces the MCP-tool-documented contract at CLI layer.

**Tradeoffs:** A is simplest but forces operator dance. B delegates to MCP (aligns with thin-wrapper pattern — cycle 27+ does NOT replicate MCP validation). C is defensive but duplicates MCP contract at CLI.

**Recommendation:** **B (optional with empty-string default)**. This matches the cycle 27+ thin-wrapper principle: CLI forwards args verbatim; MCP is authoritative. Help text documents the interaction. If operator passes nothing AND `--use-api` is False, MCP returns `"Error: Invalid extraction JSON — Expecting value: line 1 column 1"` which AC3 routes to stderr + exit 1.

## Q3. `--use-api` + `--extraction-json-file` conflict handling

Same question space as Q2. If B is chosen for Q2, the MCP tool at `core.py:773` (`if extraction is None`) already handles both branches. CLI passes the empty string or file content verbatim; MCP decides. NO CLI-level conflict detection required (C7 grep-verifiable: no new validation logic).

**Recommendation:** No CLI-level enforcement. Rely on MCP-side behaviour.

## Q4. Fair-queue counter storage: module-level int vs threading.local()

Already pinned by C10 + T6 in threat model. Module-level `_LOCK_WAITERS: int = 0` with sibling `_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()`. `threading.local()` would be per-thread (each thread sees 0 — WRONG for cross-thread fairness).

**Recommendation:** **Module-level int, guarded by `threading.Lock`.** Increment at outer-try-top, decrement in outer-finally. Read POSITION snapshot BEFORE increment (so first waiter sees 0, second sees 1, etc.).

## Q5. `_FAIR_QUEUE_STAGGER_MS` constant value

**A. 2ms (per AC6 text)** — Small; under N=10 waiters produces 20ms total stagger (under `LOCK_POLL_INTERVAL=50ms` cap).

**B. 5ms** — Larger per-position gap. Under N=10, produces 50ms total — AT the cap. Diminishing returns; wider fairness signal.

**C. 1ms (aggressive)** — Very tight stagger; N=50 waiters still under cap.

**Tradeoffs:** Smaller = less observable fairness under N=2-3 (target range); larger = more likely to hit cap at moderate N. Test at N=3 needs stagger of at least ~5ms to observe ordering reliably against Windows thread-scheduling jitter (~15.6ms coarse timer resolution).

**Recommendation:** **A (2ms)** as AC6 specifies, WITH the C11 clamp. Under N=3 (AC7 test), positions produce 0ms / 2ms / 4ms — small but observable under `time.perf_counter()` microsecond resolution. For AC7 test robustness, additionally use `threading.Barrier(3)` so all 3 threads block at the same instant before attempting lock; this amplifies the stagger signal against scheduling jitter.

## Q6. AC7 test harness

**A. `threading.Thread` + `threading.Barrier(3)` + list-shared acquire-order** — Manual thread management. Barrier ensures simultaneous start.

**B. `concurrent.futures.ThreadPoolExecutor(max_workers=3)` + `submit()` with microsleep** — Simpler API but scheduling is up to executor.

**C. `multiprocessing.Process` real-race test** — True cross-process fairness but slow on Windows (NTFS locking quirks, process-spawn cost).

**Tradeoffs:** A maximises signal via Barrier (per C6 — "threading.Barrier or microsleep stagger"). B is cleaner but less deterministic. C is authoritative but slow + Windows-hostile per CLAUDE.md threading contract.

**Recommendation:** **A (Thread + Barrier)**. Use `threading.Barrier(3)` so all 3 threads enter the `file_lock(path)` retry loop simultaneously; each thread records its acquire timestamp to a shared list under a sentinel lock. Run 10 trials; assert first-entering thread (identified by Barrier-entry order via `barrier.wait()` return value + pre-barrier monotonic stamp) acquires no later than last-entering in ≥8/10 trials.

## Q7. `_is_mcp_error_response` tuple widening style

**A. Literal tuple (current approach)** — `("Error:", "Error ", "Error[", "Page not found:")`. Fast — `str.startswith(tuple)` C-level check.

**B. Regex `re.match(r"^(Error[\[:\s]|Page not found:)", line)`** — One pattern handles more variants; harder to read + slower (regex compile cached).

**C. List + comprehension (maximum flexibility)** — Over-engineered.

**Recommendation:** **A (literal tuple).** Aligns with cycle 31 helper's existing style. Fast, readable, grep-verifiable.

## Q8. Any tagged-error form NOT starting with `"Error["` we'd miss?

**Answer (from threat model §6):** No. Comprehensive grep across `src/kb/` confirms: `ERROR_TAG_FORMAT = "Error[{category}]: {message}"` is the sole template; it only renders as `"Error[<tag>]:"`. No other error-emitter shape exists. AC3 widening is complete.

---

## C4 Context7 pre-flight (Step 6 lookups required)

Per cycle-31 L1: design references specific Click 8.3+ kwargs:
- `click.File("r", lazy=False, encoding="utf-8")` — confirm `lazy=False` still supported in Click 8.3.x (Click 8.2 removed `mix_stderr`; want to confirm `lazy` not similarly removed).
- `click.Path(exists=True)` vs `click.File` — when to prefer each. `click.Path` returns a path string; `click.File` opens and returns a file-like object. For `--content-file`, File is simpler because Click handles open/close.
- `is_flag=True` + `default=True` interaction with `--no-flag` auto-inverse — confirm Click 8.3 still auto-generates `--no-incremental` when `is_flag=True` and option name has `--` positional form. Can also explicitly use `"--incremental/--no-incremental"` Click syntax.

Step 6 executes before Step 9 lands.

---

## Composite implementation sketch (for Step 7)

```python
# src/kb/cli.py additions

@cli.command("compile-scan")
@click.option("--incremental/--no-incremental", default=True,
              help="Only new/changed sources (default: incremental).")
@click.option("--wiki-dir", type=click.Path(exists=True, file_okay=False), default=None)
def compile_scan(incremental: bool, wiki_dir: str | None) -> None:
    """Scan for new/changed raw sources that need ingestion."""
    from kb.mcp.core import kb_compile_scan  # noqa: PLC0415
    try:
        output = kb_compile_scan(incremental=incremental, wiki_dir=wiki_dir)
        if _is_mcp_error_response(output):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


@cli.command("ingest-content")
@click.option("--filename", required=True, help="Slug for raw/<type>/<slug>.md.")
@click.option("--type", "source_type", required=True,
              type=click.Choice(["article", "paper", "repo", "video", "podcast",
                                 "book", "dataset", "conversation", "capture"]))
@click.option("--content-file", type=click.File("r", lazy=False, encoding="utf-8"),
              required=True, help="Path to content file (use '-' for stdin).")
@click.option("--extraction-json-file", type=click.File("r", lazy=False, encoding="utf-8"),
              default=None, help="Optional; required when --use-api is not set.")
@click.option("--url", default="", help="Optional source URL for metadata.")
@click.option("--use-api", is_flag=True, default=False,
              help="Use Anthropic API for extraction (extraction JSON ignored).")
def ingest_content(filename: str, source_type: str, content_file, extraction_json_file,
                   url: str, use_api: bool) -> None:
    """One-shot ingest: save content to raw/ and create wiki pages."""
    from kb.mcp.core import kb_ingest_content  # noqa: PLC0415

    # T12/C13 — size guard BEFORE read
    try:
        # click.File("r") may report bytes only after read; use os.fstat on fileno
        import os as _os
        st_size = _os.fstat(content_file.fileno()).st_size if hasattr(content_file, "fileno") else None
        if st_size is not None and st_size > MAX_INGEST_CONTENT_CHARS:
            click.echo(f"Error: --content-file size {st_size} exceeds {MAX_INGEST_CONTENT_CHARS}.", err=True)
            sys.exit(1)
    except (OSError, AttributeError):
        pass  # stdin / non-seekable; defer to MCP cap

    content = content_file.read()
    extraction_json = extraction_json_file.read() if extraction_json_file else ""

    try:
        output = kb_ingest_content(
            content=content, filename=filename, source_type=source_type,
            extraction_json=extraction_json, url=url, use_api=use_api,
        )
        if _is_mcp_error_response(output):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)
```

```python
# src/kb/utils/io.py additions

_LOCK_WAITERS: int = 0
_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()
_FAIR_QUEUE_STAGGER_MS: float = 2.0


def _take_waiter_slot() -> int:
    """Increment and return the position (0-based). Caller MUST pair with
    _release_waiter_slot in a finally clause."""
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        position = _LOCK_WAITERS
        _LOCK_WAITERS += 1
        return position


def _release_waiter_slot() -> None:
    """Decrement the waiter count. Idempotent under re-entrant misuse is NOT
    a contract — callers must pair exactly one release per take."""
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        _LOCK_WAITERS = max(0, _LOCK_WAITERS - 1)


# Inside file_lock — sketch (outer try/finally wrapping):
# position = _take_waiter_slot()
# try:
#     if position > 0:
#         stagger_s = min(position * _FAIR_QUEUE_STAGGER_MS / 1000.0,
#                         LOCK_POLL_INTERVAL)
#         time.sleep(stagger_s)
#     # ... existing retry loop ...
# finally:
#     _release_waiter_slot()
#     if acquired:
#         lock_path.unlink(missing_ok=True)
```

---

## Summary

All 8 requirements questions have recommended answers grounded in threat-model conditions. Step 5 decision gate will commit verdicts; most recommendations align with conditions C1-C13, so the gate's Analysis block primarily validates coherence rather than choosing between meaningful alternatives. No design amendments expected.
