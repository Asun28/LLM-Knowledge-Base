# Cycle 32 — FINAL DECIDED DESIGN (Step 5 Decision Gate)

**Date:** 2026-04-25 · **Branch:** `feat/backlog-by-file-cycle32`
**Method:** Primary-session synthesis (Step 5 Opus subagent `a5b27485f305ef56b` hung past cycle-20 L4 10-min threshold → fallback per cycle-27 L3 manual-verify-authoritative rule).

**Inputs consolidated:**
1. `2026-04-25-cycle32-requirements.md` — 8 ACs + 8 open Qs.
2. `2026-04-25-cycle32-threat-model.md` — T1-T12 + C1-C13 (Opus subagent `aa4fe0b87c2592862`, verdict PROCEED).
3. `2026-04-25-cycle32-brainstorm.md` — 8 Q recommendations + composite sketch.
4. `2026-04-25-cycle32-r1-opus-eval.md` — R1 Opus AMEND verdict with 3 fixes (AC5/AC6/AC8) + 14-symbol grep-verification table.
5. `2026-04-25-cycle32-r2-manual-verify.md` — R2 fallback; adds Q9 extraction-json cap.

## VERDICT: `PROCEED with AMEND to AC5/AC6/AC8`

All 14 symbols from R1 Opus's verification table re-confirmed present in `src/kb/` (no SEMANTIC-MISMATCH, no MISSING). Same-class peer scan for AC3 re-confirms zero legitimate non-error `"Error["` emitters. Ready for Step 6 Context7 + Step 7 plan.

## DECISIONS (by question)

### Q1 — `--content-file` input modes

**Decision: B (file with `-`=stdin shorthand).** Use `click.File("r", lazy=False, encoding="utf-8")` with native `-`=stdin support.

**Analysis:** Option A (file-only) is the most conservative. Option B adds zero code complexity because Click handles `-` transparently; tests only need one extra integration test (`kb ingest-content --content-file -` with `runner.invoke(..., input=content)`). Option C duplicates flag surface needlessly. Operator pain-point is real — piping `curl` / `yt-dlp` through `kb ingest-content` is a common CLI idiom; forcing a temp file is friction. T1/T2 threat surface is identical between A and B (operator controls both inputs); T12 size-guard is more complex in B because stdin lacks `os.fstat` st_size — the brainstorm's `hasattr(content_file, 'fileno')` + `os.fstat(...)` pattern with `try/except (OSError, AttributeError): pass` fallback handles this correctly by deferring to MCP cap when stat fails.

**Rationale:** Unix ergonomics; zero security delta; cycle 27+ thin-wrapper doctrine doesn't forbid stdin. **Confidence: HIGH.**

### Q2 — `--extraction-json-file` required vs optional with `--use-api`

**Decision: B (optional, empty-string default).** Delegates validation to MCP.

**Analysis:** Option A forces operator dance when `--use-api` is set (MCP ignores content); Option B matches cycle 27+ thin-wrapper principle (CLI forwards verbatim; MCP authoritative). Option C duplicates MCP contract at CLI layer. The exception path is clean: operator passes no flag + no `--use-api` → MCP returns `"Error: Invalid extraction JSON — ..."` which AC3 routes to stderr + exit 1.

**Rationale:** Thin-wrapper fidelity; MCP already enforces. **Confidence: HIGH.**

### Q3 — `--use-api` + `--extraction-json-file` conflict handling

**Decision: No CLI-level enforcement.** MCP authoritative per `core.py:701` `if not use_api:` gating.

**Analysis:** Matches Q2 Option B resolution. MCP's documented "Ignored when use_api=True" contract is tested at the MCP layer. CLI-level mutual-exclusion would duplicate the check and create two places to maintain when the contract evolves. No security delta — operator inputs trusted by B1.

**Rationale:** Consistency with thin-wrapper pattern. **Confidence: HIGH.**

### Q4 — Fair-queue counter storage

**Decision: Module-level `int` guarded by `threading.Lock`.** (C10 + T6 confirmed.)

**Analysis:** `threading.local()` is per-thread — each thread sees 0 — defeating the cross-thread fairness signal. Module-level shared counter is necessary. Python `+=` on int is NOT atomic under GIL (three bytecodes: `LOAD_GLOBAL`, `BINARY_OP`, `STORE_GLOBAL`); a sibling `threading.Lock` is required. Position snapshot MUST be BEFORE increment (first waiter sees 0, second sees 1).

**Rationale:** Correctness prerequisite; no alternative preserves cross-thread semantics. **Confidence: HIGH.**

### Q5 — `_FAIR_QUEUE_STAGGER_MS` value

**Decision: A (2.0ms).** With C11 clamp to `LOCK_POLL_INTERVAL=50ms`.

**Analysis:** At N=3 (AC7 test), positions produce 0ms/2ms/4ms — below Windows coarse-timer default (15.6ms) but within `time.perf_counter()` microsecond resolution on Windows. At N=10 realistic concurrency, max stagger = 18ms (well under 50ms cap). At N=25, hits the cap. 5ms would cap at N=10 (too aggressive for moderate N). 1ms signal below scheduler noise.

**Rationale:** Balances observability for target N=2-3 thundering-herd case with headroom before clamp. **Confidence: MEDIUM** (empirical; revisit if production metrics surface).

### Q6 — AC7 test harness

**Decision: A (`threading.Thread` + `threading.Barrier(3)`).** N=3 workers, 10 trials, 80% threshold.

**Analysis:** Barrier maximises signal — all 3 threads enter the `file_lock` retry loop simultaneously. ThreadPoolExecutor defers scheduling to executor (less deterministic). multiprocessing is cross-process but slow on Windows + NTFS locking quirks (cycle-17 L3 file-lock test issues). Use `barrier.wait()` return value as first-entrant identifier (NOT pre-barrier `time.perf_counter()` stamps which are race-prone — R1 Opus AC7 amendment).

**Rationale:** Maximum signal per cycle-17 L3 file-lock testing patterns; C6 compliant. **Confidence: HIGH.**

### Q7 — Tuple widening style

**Decision: A (literal tuple).** `("Error:", "Error ", "Error[", "Page not found:")`.

**Analysis:** Literal tuple is faster (C-level `str.startswith(tuple)` with short-circuit). Regex requires module-level compile + per-call match overhead. Grep-verifiable via `rg 'startswith\(\(' src/kb/cli.py`. Cycle 31 established the tuple form at `cli.py:110`; cycle 32 extends it by one literal. Regex would break the grep-verifiable invariant established in cycle 31.

**Rationale:** Performance + consistency + grep-verifiability. **Confidence: HIGH.**

### Q8 — Missing tagged-error shapes

**Decision: No missed shapes.** Widening to 4 prefixes is complete.

**Analysis:** R1 Opus + R2 manual-verify grep confirmed 6 occurrences of `Error[` in `src/kb/`: 1 template (`ERROR_TAG_FORMAT`), 2 emitters (`core.py:762,881`), 2 comments, 1 docstring cross-ref. All tagged-error forms start with `"Error["`. Add Step-11 grep `rg '[A-Z][a-z]+\[' src/kb/` to future-proof against divergent bracket-tagged emitters.

**Rationale:** Exhaustive grep enumeration. **Confidence: HIGH.**

### Q9 (R2 manual-verify surface) — `--extraction-json-file` CLI size cap

**Decision: Cap at `MAX_INGEST_CONTENT_CHARS = 160_000 chars` (same cap as content).**

**Analysis:** `_validate_file_inputs` at `core.py:167-178` ONLY bounds `content` (via `MAX_INGEST_CONTENT_CHARS=160_000`), NOT `extraction_json`. R2's manual-verify initially suggested `MAX // 4 = 40_000` citing a "historical 4× ratio" at `core.py:535` — this is a MISREAD. The comment at `core.py:535` refers to `MAX_INGEST_CONTENT_CHARS*4` as a conservative UTF-8 bytes-per-char upper bound for OOM protection on raw source `stat().st_size` (`QUERY_CONTEXT_MAX_CHARS*4` alignment), NOT an extraction-json overhead ratio. No canonical ratio exists.

Reusing the same `MAX_INGEST_CONTENT_CHARS=160_000` cap for extraction-json is the cleanest choice: (a) no magic constant, (b) real-world extraction JSON from `_extract_items_via_llm` is a few KB — 160_000 chars is already 40-80× typical size, (c) if operator sends >160_000 chars of extraction JSON, it's operator error or misuse. Stat-guard pattern identical to content cap (C13).

**Rationale:** Simplicity + aligned with existing content cap + no magic constant. **Confidence: HIGH** (updated from MEDIUM after catching R2's rationale misread before Step 9).

### R1 (AC5 amend) — Add 5th `--use-api` forwarding test

**Decision: ADOPT as AC5 test requirement.**

**Analysis:** Pins Q3 resolution via a grep-verifiable spy test. Without it, Q3's "delegate to MCP" resolution has no machine-checked anchor — a future refactor could add CLI-side mutual-exclusion without breaking any test. Low cost (~8 LOC additional test), high value (resolution stays pinned).

**Rationale:** Test-anchor retention per cycle-15 L2 principle. **Confidence: HIGH.**

### R2 (AC6 amend) — `_release_waiter_slot` diagnostic warning instead of silent clamp

**Decision: ADOPT.** Replace `max(0, _LOCK_WAITERS - 1)` with:
```python
if _LOCK_WAITERS > 0:
    _LOCK_WAITERS -= 1
else:
    logger.warning("_LOCK_WAITERS underflow — paired release missing")
```

**Analysis:** Counter drift under exception paths is a real T6 concern; silent clamp-to-zero makes it unobservable. A `logger.warning` on underflow surfaces the drift to operators without affecting control flow. Still prevents negative values. Counter drift still possible with excess increments, but now there's a log trail.

**Rationale:** Observability over silence; matches project's cycle-11-style thread-safety discipline. **Confidence: HIGH.**

### R3 (AC8 amend) — T11 BACKLOG + CLAUDE.md language + delete old BACKLOG entry

**Decision: ADOPT all three sub-items.**

**(a) Explicit BACKLOG MEDIUM entry for T11** (per C12): at end of cycle, add:
```markdown
- `src/kb/mcp/core.py:762,881` — `kb_ingest_content` / `kb_save_source` post-create OSError path leaks un-scrubbed absolute path via `{write_err}` interpolation (Windows `[WinError N]: '<abs-path>'` format). Cycle 32 AC3 newly routes this to CLI stderr. *(Surfaced 2026-04-25 cycle 32 threat model T11.)*
  (fix: apply `_sanitize_error_str(write_err, file_path)` instead of raw interpolation.)
```

**(b) CLAUDE.md §"File locking" paragraph** MUST contain the words "mitigation" AND "intra-process only" AND MUST NOT use "guarantee" / "fair-queue" (unqualified). Concrete target wording: *"Cycle 32 AC6 — `_LOCK_WAITERS` counter + initial-wait stagger provide a probabilistic **mitigation** (intra-process only, not a guarantee) for fair-queue starvation under N-waiter contention. Stagger is clamped to `LOCK_POLL_INTERVAL`."*

**(c) BACKLOG.md:125-126 fair-queue entry DELETED** (not strike-through) per BACKLOG lifecycle convention. The deletion lands atomically with the AC6 implementation commit.

**Analysis:** C12 mandates BACKLOG filing for deferred-promise enforcement (cycle-23 L3). C8 mandates doc-language discipline. BACKLOG.md:125-126 is resolved by this cycle's AC6 — per BACKLOG lifecycle, resolved items are deleted (never strike-through).

**Rationale:** Audit-doc consistency + BACKLOG lifecycle compliance. **Confidence: HIGH.**

---

## CONDITIONS (Step 9 must satisfy)

Consolidated from threat-model C1-C13 + R1 Opus residuals + Q9 + cycle-22 L5 (each CONDITION is test-coverage mandate, not footnote).

**C1.** AC3 revert-divergent regression test: ≥1 unit test `_is_mcp_error_response("Error[partial]: write failed; retry.") is True` AND ≥1 integration test `CliRunner.invoke(cli, ["ingest-content", ...])` with `kb_ingest_content` monkeypatched to return `"Error[partial]: ..."` → `exit_code == 1` + `"Error[partial]" in result.stderr`. Grep-verifiable: `rg 'Error\[partial\]' tests/test_cycle32_*.py` returns ≥2 assertions.

**C2.** AC3 same-class peer scan — Step 11 `rg 'Error\[' src/kb/` must confirm: `app.py:17` (template), `core.py:762,881` (emitters), `cli.py:103` (docstring). No more, no less.

**C3.** AC6 counter symmetry — regression test asserts `_LOCK_WAITERS == 0` after raised `TimeoutError` (held-lock scenario + deadline=0). Grep-verifiable: `rg '_LOCK_WAITERS' src/kb/utils/io.py` shows exactly TWO mutations (increment + decrement) inside ONE outermost `try/finally`.

**C4.** Context7 MANDATORY at Step 6 for:
   - `click.File("r", lazy=False, encoding="utf-8")` behaviour in Click 8.3.2 (binary content, lazy semantics).
   - `click.Path(exists=True, file_okay=..., dir_okay=...)` — file vs directory constraint.
   - `--flag/--no-flag` auto-inverse syntax vs `is_flag=True + default=True`.

**C5.** AC6 hot-path peer scan — Step 11 `rg 'file_lock\(' src/kb/` count unchanged pre/post. No call site mutates or reads `_LOCK_WAITERS`.

**C6.** AC7 probabilistic test: `max_workers=3`, 10 trials, 80% tolerance, `threading.Barrier(3)` for simultaneous entry. Grep-verifiable: `rg 'threading\.Barrier' tests/test_cycle32_*.py` shows fixture.

**C7.** AC4 CLI reads file contents WITHOUT client-side `json.loads` on extraction-json or `str.strip()` on url. Grep-verifiable: `rg -n 'json\.loads|url\.strip' src/kb/cli.py` returns no new matches in `ingest_content` body.

**C8.** AC8 CLAUDE.md §"File locking" paragraph contains literals `mitigation` AND `intra-process only`; contains ZERO occurrences of `fair-queue` as unqualified noun (may use "fair-queue stagger" as a compound adjective for the feature name). Grep-verifiable: `rg -n 'mitigation' CLAUDE.md` shows the cycle-32 line; `rg -n '\bfair-queue\b[^ ]*\s' CLAUDE.md` returns 0 unqualified usages outside compound "fair-queue stagger mitigation" phrase.

**C9.** AC1/AC2 CLI help text on `--incremental` includes "default: incremental". Grep-verifiable: `rg -A1 'incremental' src/kb/cli.py | rg 'default'`.

**C10.** `_LOCK_WAITERS` defined at module level in `src/kb/utils/io.py` as `_LOCK_WAITERS: int = 0` with sibling `_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()`. Grep-verifiable: `rg '^_LOCK_WAITERS' src/kb/utils/io.py` shows both declarations.

**C11.** AC6 stagger clamp `min(position * _FAIR_QUEUE_STAGGER_MS / 1000, LOCK_POLL_INTERVAL)` applied once before retry loop (not per iteration). Grep-verifiable: `rg 'min\(.*_FAIR_QUEUE_STAGGER' src/kb/utils/io.py` shows exactly one clamp.

**C12.** BACKLOG MEDIUM entry for T11 filed atomically with cycle 32 AC3 commit (NOT a follow-up cycle). Entry text: see AC8 amend (a) above. Grep-verifiable: `rg 'core\.py:762,881' BACKLOG.md` shows the entry after commit.

**C13.** `--content-file` AND `--extraction-json-file` CLI-layer stat guards. Both call `os.fstat(fileobj.fileno()).st_size` with `try/except (OSError, AttributeError): pass` fallback. BOTH capped at `MAX_INGEST_CONTENT_CHARS=160_000` (revised Q9 — simpler, no magic ratio). Grep-verifiable: `rg 'fstat|st_size' src/kb/cli.py` shows the guards in `ingest_content` body.

**C14.** AC6 `_release_waiter_slot` emits `logger.warning("_LOCK_WAITERS underflow...")` on negative branch (R1 residual R2). Grep-verifiable: `rg '_LOCK_WAITERS underflow' src/kb/utils/io.py`.

**C15.** AC5 5-test suite (R1 residual R1): body-spy happy-path + raw-forwarding spy + Error[partial] integration + error-path `--filename "bad!!!"` + explicit `--use-api` forwarding spy test asserting `use_api=True` forwards verbatim. Grep-verifiable: `rg 'use_api=True' tests/test_cycle32_*.py` returns ≥1 match.

**C16.** AC8 BACKLOG.md:125-126 fair-queue entry is DELETED (not strike-through) atomically with the AC6 commit. Grep-verifiable (post-commit): `rg 'fair-queue|waiters can be out-raced' BACKLOG.md` returns ZERO matches in the Phase 4.5 MEDIUM section.

---

## FINAL DECIDED DESIGN (by AC)

**AC1.** `kb compile-scan [--incremental/--no-incremental] [--wiki-dir PATH]` — thin wrapper over `kb_compile_scan` at `mcp/core.py:891`. Click syntax: `"--incremental/--no-incremental", default=True` (matches cycle-15 `kb publish` precedent at `cli.py:417`). Help: "Scan for new/changed raw sources. Default: incremental." `--wiki-dir` uses `click.Path(exists=True, file_okay=False)`. Function-local MCP import + `_is_mcp_error_response` + `click.echo(err=True)` on error.

**AC2.** AC1 tests — 3 tests: body-spy happy-path + raw-forwarding spy (`incremental=False, wiki_dir="/tmp/x"`) + error-path with monkeypatched `_validate_wiki_dir` → exit 1 + `"Error:" in result.stderr` + `result.stdout == ""`.

**AC3.** `_is_mcp_error_response` tuple widened to `("Error:", "Error ", "Error[", "Page not found:")`. Docstring updated: "Four shapes — `Error:` (validator), `Error ` (runtime verb-form), `Error[` (tagged per `ERROR_TAG_FORMAT` at `app.py:17`, emitted by `kb_ingest_content`/`kb_save_source` at `core.py:762,881`), `Page not found:` (`kb_read_page` logical-miss)." Regression tests per C1.

**AC4.** `kb ingest-content --filename X --type Y --content-file PATH [--extraction-json-file PATH] [--url URL] [--use-api]`. Implementation sketch:
```python
@cli.command("ingest-content")
@click.option("--filename", required=True, help="Slug for raw/<type>/<slug>.md.")
@click.option("--type", "source_type", required=True,
              type=click.Choice(["article", "paper", "repo", "video", "podcast",
                                 "book", "dataset", "conversation", "capture"]))
@click.option("--content-file", type=click.File("r", lazy=False, encoding="utf-8"),
              required=True, help="Path to content file. Use '-' for stdin.")
@click.option("--extraction-json-file", type=click.File("r", lazy=False, encoding="utf-8"),
              default=None,
              help="Optional; required when --use-api is not set. Ignored with --use-api.")
@click.option("--url", default="", help="Optional source URL for metadata.")
@click.option("--use-api", is_flag=True, default=False,
              help="Use Anthropic API for extraction. --extraction-json-file ignored if set.")
def ingest_content(filename, source_type, content_file, extraction_json_file,
                   url, use_api):
    """One-shot ingest: save content to raw/ and create wiki pages."""
    from kb.mcp.core import kb_ingest_content  # noqa: PLC0415

    # C13 — stat guard for content-file BEFORE read
    try:
        import os as _os
        st_size = _os.fstat(content_file.fileno()).st_size
        if st_size > MAX_INGEST_CONTENT_CHARS:
            click.echo(
                f"Error: --content-file size {st_size} exceeds {MAX_INGEST_CONTENT_CHARS}.",
                err=True,
            )
            sys.exit(1)
    except (OSError, AttributeError):
        pass  # stdin / non-seekable; defer to MCP cap

    # C13 — stat guard for extraction-json-file (Q9 cap = MAX_INGEST_CONTENT_CHARS)
    if extraction_json_file is not None:
        try:
            ej_size = _os.fstat(extraction_json_file.fileno()).st_size
            if ej_size > MAX_INGEST_CONTENT_CHARS:
                click.echo(
                    f"Error: --extraction-json-file size {ej_size} exceeds "
                    f"{MAX_INGEST_CONTENT_CHARS}.",
                    err=True,
                )
                sys.exit(1)
        except (OSError, AttributeError):
            pass

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

**AC5.** 5 tests per C15: (a) happy-path body-spy (extraction JSON provided), (b) raw-forwarding spy (all args verbatim), (c) error-path `--filename "bad!!!"` → MCP `_validate_file_inputs` rejection → exit 1 + `"Error:" in result.stderr` + `result.stdout == ""`, (d) `Error[partial]` integration via monkeypatched MCP returning `"Error[partial]: write failed; retry with overwrite=true."` → exit 1 + `"Error[partial]" in result.stderr` + `result.stdout == ""`, (e) `--use-api` forwarding spy asserting `use_api=True` passes through.

**AC6.** `utils/io.py` additions:
```python
_LOCK_WAITERS: int = 0
_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()
_FAIR_QUEUE_STAGGER_MS: float = 2.0


def _take_waiter_slot() -> int:
    """Increment and return 0-based position BEFORE increment.
    Caller MUST pair with _release_waiter_slot in a finally clause (C3)."""
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        position = _LOCK_WAITERS
        _LOCK_WAITERS += 1
        return position


def _release_waiter_slot() -> None:
    """Decrement the waiter count. Warn on underflow to surface paired-release
    bugs (C14 — R1 Opus residual R2)."""
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        if _LOCK_WAITERS > 0:
            _LOCK_WAITERS -= 1
        else:
            logger.warning(
                "_LOCK_WAITERS underflow — paired _take_waiter_slot release missing"
            )
```

Inside `file_lock` — wrap existing retry loop in outer try/finally with counter take/release (C3 + C11):
```python
position = _take_waiter_slot()
try:
    # C11 — one-shot stagger BEFORE retry loop; clamped to LOCK_POLL_INTERVAL
    if position > 0:
        stagger_s = min(
            position * _FAIR_QUEUE_STAGGER_MS / 1000.0,
            LOCK_POLL_INTERVAL,
        )
        time.sleep(stagger_s)
    # ... existing retry loop unchanged ...
finally:
    _release_waiter_slot()
    # ... existing acquired-unlink cleanup ...
```

**AC7.** Probabilistic ordering test per C6:
```python
from threading import Barrier, Thread

def test_fair_queue_stagger_probabilistic_ordering(tmp_path):
    lock_path = tmp_path / ".lock"
    n = 3
    trials = 10
    first_entrant_won = 0
    for _ in range(trials):
        acquire_order = {}
        barrier = Barrier(n)
        def worker(idx: int):
            entry = barrier.wait()  # returns 0..n-1 based on entry order
            with file_lock(lock_path, timeout=5.0):
                acquire_order[entry] = time.perf_counter()
        threads = [Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads: t.start()
        for t in threads: t.join()
        if acquire_order.get(0, float("inf")) <= acquire_order.get(n - 1, 0):
            first_entrant_won += 1
    assert first_entrant_won >= 8, f"Fair-queue stagger weakened: {first_entrant_won}/10"
```

**AC8.** Doc sync:
- CLAUDE.md Module Map: CLI count 22 → 24; §"File locking" paragraph updated per C8 language discipline.
- BACKLOG.md:125-126 fair-queue entry DELETED (C16).
- BACKLOG MEDIUM entry added for T11 at end of cycle (C12).
- BACKLOG CLI↔MCP parity note: 9 → 7 remaining (all write-path deferred).
- CHANGELOG.md Quick Reference + CHANGELOG-history.md per cycle conventions, with `+TBD commits` placeholder (cycle-30 L1).

---

## Step 6 Context7 prerequisites (C4)

Three Context7 queries required before Step 9 TDD:
1. `click.File` in Click 8.3 — confirm `lazy=False` + `encoding="utf-8"` kwargs supported; behaviour on binary content (UnicodeDecodeError? Click-surfaced UsageError?).
2. `click.Path` in Click 8.3 — `exists=True, file_okay=False` for `--wiki-dir`; `exists=True` (default file_okay) for content paths via `click.File`.
3. `--flag/--no-flag` syntax — confirm `"--incremental/--no-incremental"` is preferred Click 8.3+ form over `is_flag=True + default=True` inverse auto-generation.

Update design if any conflict surfaces. Cycle-31 L1 rule applies: Step 6 MANDATORY for library-API kwarg references.

---

## Additional unstated assumptions caught

1. **CLI stream discipline.** All error paths in AC1 + AC4 MUST route via `click.echo(output, err=True)` + `sys.exit(1)`. Success paths via `click.echo(output)` (stdout default). Tests per cycle-31 L3 strong-form: `result.stdout == ""` + `X in result.stderr`.

2. **`--filename` slug sanitization.** MCP-side `slugify(filename)` at `core.py:685` strips path separators; CLI forwards raw string. Test C15(c) exercises `"bad!!!"` which hits MCP validation's character-class rejection.

3. **`--url` NOT mutated.** Per T3/C7, CLI forwards `--url` verbatim (no strip, no encode). MCP-side `yaml_escape` at `core.py:718` neutralises embedded newlines/quotes.

4. **Step 7 primary-session plan.** Cycle 32 has 8 ACs (< 15 cycle-14 L1 threshold) BUT the primary session holds full context from Steps 1-5. Primary-session plan draft per cycle-14 L1 is appropriate; Codex dispatch would lose context.

---

## Verdict summary

**PROCEED with AMEND to AC5/AC6/AC8** as specified above. Ready for Step 6 Context7 verification (C4 — mandatory per cycle-31 L1), then Step 7 plan drafting in primary session (cycle-14 L1). All 14 symbols re-confirmed present; AC3 same-class peer scan confirms safety; C1-C16 are grep-verifiable.
