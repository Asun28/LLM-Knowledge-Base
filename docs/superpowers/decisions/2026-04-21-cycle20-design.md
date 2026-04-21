# Cycle 20 — Final Design Decision Gate (Step 5)

**Date:** 2026-04-21
**Inputs:**
- `2026-04-21-cycle20-requirements.md` (Step 1 — 21 ACs, Q1-Q10)
- `2026-04-21-cycle20-threat-model.md` (Step 2 — T1-T7)
- `2026-04-21-cycle20-brainstorm.md` (Step 3 — Q1-Q15 + tentative resolutions)
- R1 Opus design eval (Step 4a — 0 BLOCKERs, 8 MAJORs, 5 NITs, verdict AMEND-INLINE)
- R2 Codex design eval (Step 4b — 0 BLOCKERs, AMEND-INLINE) — adds AC11 `_update_existing_page` lock + AC13 `attempt_id` matching + `_TOOL_GROUPS` update + MCP tool-count correction (27→29)

## Decisions (Q1-Q15 + D-NEW-1..5)

### Q1 — kb.utils.llm passthrough
- Decision: Keep `LLMError` as separate sibling under `KBError`. No passthrough.
- Rationale: CLAUDE.md error convention + cycle-17 L1 narrow-blast-radius; preserves existing `isinstance(err, LLMError)` checks.
- Confidence: HIGH

### Q2 — StorageError.path attribute + __str__ hiding
- Decision: `StorageError(msg, *, kind: str | None = None, path: Path | None = None)`. Stores both. `__str__` returns `f"{kind}: <path_hidden>"` only when BOTH `kind` AND `path` are set; else `msg` verbatim.
- Rationale: T1 mitigation — prevents log-aggregator path disclosure while preserving local-debug introspection via `err.path`.
- Confidence: HIGH

### Q3 — Windows O_EXCL symlink semantics
- Decision: Guard `O_NOFOLLOW` with `hasattr(os, "O_NOFOLLOW")`; rely on `CreateFileW(CREATE_NEW)` on Windows.
- Rationale: T3 mitigation — POSIX hardening without Windows breakage.
- Confidence: HIGH

### Q4 — Thread vs multiprocess concurrent-write test
- Decision: Threading with `threading.Barrier(2)` for deterministic race.
- Rationale: Cycle-17 L1 defers MP tests; HIGH #16 is intra-process FastMCP thread-pool scenario.
- Confidence: HIGH

### Q5 — Default hours
- Decision: `list=24`, `sweep=168`.
- Rationale: Different risk gradients (read vs mutation).
- Confidence: HIGH

### Q6 — dry_run kwarg
- Decision: Add `dry_run: bool = False` to helper + MCP + CLI (AC13/AC14/AC15).
- Rationale: Operator-safety.
- Confidence: HIGH

### Q7 — sweep_id uuid4.hex[:8]
- Decision: 8-hex (matches cycle-19 `attempt_id`).
- Confidence: HIGH

### Q8 — notes_length projection
- Decision: MCP projects `{attempt_id, page_id, timestamp, notes_length}`; CLI returns full dict.
- Rationale: T5 + least-privilege MCP contract.
- Confidence: HIGH

### Q9 — GetLongPathNameW roundtrip sanity
- Decision: Add roundtrip assertion before equivalence check; skip test if roundtrip fails.
- Rationale: Test hygiene — defends against vacuous skip on 8.3-disabled filesystems.
- Confidence: HIGH

### Q10 — Star-import lint test
- Decision: Add one grep-based test in `test_cycle20_errors_taxonomy.py`.
- Rationale: AC4 convention needs machine-checkable guard.
- Confidence: HIGH

### Q11-Q15 — Reaffirmed per brainstorm.

### D-NEW-1 — `_update_existing_page` lock discipline
- Decision: Unconditional `file_lock(page_path)` inside helper (five-line change).
- Rationale: Leaf helper with no nested locks; protects future callers; R2 finding.
- Confidence: HIGH

### D-NEW-2 — AC5 target relocation
- Decision: Drop `compile/compiler.py` from AC5. Keep 2 sites: `ingest/pipeline.py _run_ingest_body` outer + `query/engine.py:195,206`.
- Rationale: R1 grep confirms no clean outer boundary in `compile_wiki`; narrowing `:443`/`:455`/`:494` would either break continue-on-error contract or elevate warning-only errors (cycle-17 L1 blast-radius).
- Confidence: HIGH

### D-NEW-3 — `_TOOL_GROUPS` update location
- Decision: Fold `_TOOL_GROUPS` tuple update into AC14 (`kb_refine_sweep`) and AC17 (`kb_refine_list_stale`). No new AC.
- Confidence: HIGH

### D-NEW-4 — Audit log ordering for delete
- Decision: `append_wiki_log` BEFORE `save_review_history` mutation.
- Rationale: Crash-safety forensics.
- Confidence: HIGH

### D-NEW-5 — AC count after amendments
- Decision: 21 ACs (unchanged). Test delta target: +26 tests (25 planned + 1 star-import lint).
- Confidence: HIGH

---

## Final decided design — AC1..AC21 (amended, authoritative)

### Cluster A — `kb.errors` exception taxonomy

**AC1** — New module `src/kb/errors.py`:
- `KBError(Exception)` — base.
- `IngestError(KBError)`, `CompileError(KBError)`, `QueryError(KBError)`, `ValidationError(KBError)`, `StorageError(KBError)`.
- `StorageError.__init__(msg: str, *, kind: str | None = None, path: Path | None = None)`. Stores `self.kind`, `self.path`. `__str__` returns `f"{self.kind}: <path_hidden>"` when BOTH `kind` and `path` set; else `msg` verbatim.
- `IngestError` / `CompileError` / `QueryError` / `ValidationError` take plain `(msg)` signature.

**AC2** — `LLMError` at `src/kb/utils/llm.py:381` reparented from `Exception` to `KBError`. Existing `kind` and `__init__(message, *, kind=None)` preserved. `CaptureError` at `src/kb/capture.py:544` similarly reparented. `isinstance` against `LLMError`/`Exception`/`KBError` all True via MRO.

**AC3** — `src/kb/__init__.py` extends BOTH `__all__` AND the PEP 562 `__getattr__` dispatcher with branches for each new name. Lazy import preserved — `from kb import KBError` does `from kb.errors import KBError; return KBError` on first access.

**AC4** — CLAUDE.md "Error Handling Conventions" gains:
- New bullet listing the taxonomy + rule on narrow vs boundary `except Exception`.
- MCP tool count corrected: "26 → 28 tools" → "27 → 29 tools" (R2 audit).
- Pointer to `_TOOL_GROUPS` edits in AC14+AC17.

**AC5** — Narrow hot-path migration — **2 sites only** (revised from 3):
- `ingest/pipeline.py _run_ingest_body` outer → `except (IngestError, OSError, ValueError) as e:` + wrap unexpected into `IngestError(str(e)) from e`.
- `query/engine.py:195,206` two outer `except Exception as exc:` → wrap into `QueryError(str(exc)) from exc` (or narrow to `(KBError, OSError)`).
- `compile/compiler.py` DROPPED from AC5 per D-NEW-2.

**AC6** — Tests `tests/test_cycle20_errors_taxonomy.py`:
- Subclass tests: all 5 new subclasses + `KBError` extends `Exception`.
- `LLMError` subclasses both `KBError` AND `Exception` (MRO guard).
- `LLMError(..., kind="auth").kind == "auth"` preserved.
- `CaptureError` subclasses `KBError`.
- `StorageError(msg)` → `.kind is None`, `.path is None`.
- `StorageError(msg, kind="summary_collision", path=Path(...))` → `str(err) == "summary_collision: <path_hidden>"` (T1 verification).
- `StorageError(msg, kind="summary_collision")` without path → `str(err) == msg` verbatim.
- Import-surface: `from kb import KBError, IngestError, CompileError, QueryError, ValidationError, StorageError`.
- Star-import lint: grep `tests/` for `from kb.errors import \*` — expect 0.

**AC7** — Regression behavior test — inject `OSError` at `atomic_text_write` called within `ingest_source`; assert raises `IngestError` with original in `__cause__`. Mirror for `query_wiki` path.

### Cluster B — `_write_wiki_page` slug-collision O_EXCL hardening

**AC8** — `_write_wiki_page(path, title, ..., *, exclusive: bool = False)`. When True:

```python
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW  # POSIX hardening; no-op on Windows
try:
    fd = os.open(str(effective_path), flags, 0o644)
except FileExistsError as e:
    raise StorageError("summary_collision", kind="summary_collision", path=effective_path) from e
try:
    try:
        os.write(fd, frontmatter.dumps(post, sort_keys=False).encode("utf-8") + b"\n")
        os.fsync(fd)
    except Exception:
        # Write-phase failed AFTER O_EXCL succeeded — unlink zero-byte poison.
        os.close(fd)
        fd = None
        try:
            os.unlink(str(effective_path))
        except OSError:
            pass
        raise
finally:
    if fd is not None:
        os.close(fd)
```

Default `exclusive=False` preserves byte-identical legacy behavior. Message NEVER interpolates path.

**AC9** — Summary write at `pipeline.py:1254` passes `exclusive=True`. On `isinstance(err, StorageError) and err.kind == "summary_collision"`, pivots to `_update_existing_page(summary_path, source_ref, verb="Summarized")`. Caller holds `file_lock(summary_path)` around create+evidence-trail (see AC11).

**AC10** — Item write at `pipeline.py:957` uses `exclusive=True`. On `StorageError(kind="summary_collision")`, pivots to `_update_existing_page`. Caller holds `file_lock(item_path)` for the span.

**AC11** — Lock discipline:
- Callers of `_write_wiki_page(exclusive=True)` wrap the create + `append_evidence_trail` span in `file_lock(page_path)`.
- `_update_existing_page` (`pipeline.py:480`) acquires `file_lock(page_path)` **unconditionally** inside the helper (D-NEW-1). Leaf RMW; no nested locks; protects all callers.
- `file_lock` is NOT re-entrant; ingest-lock and inject_wikilinks-batch-lock run sequentially, not nested — confirmed safe.

**AC12** — Tests `tests/test_cycle20_write_wiki_page_exclusive.py`:
- `exclusive=False` byte-identical.
- `exclusive=True` fresh path: success.
- `exclusive=True` existing: raises `StorageError(kind="summary_collision")`, `err.path` set, `str(err)` hides path.
- Write-phase cleanup: monkeypatch `os.write` to raise; assert unlink + retry.
- **Concurrent via `ingest_source(...)` ×2 threads** (R2 finding) + `threading.Barrier(2)` (R1 NIT): assert both `source:` entries land, both evidence-trail entries survive, no double-write, no zero-byte file.

### Cluster C — `sweep_stale_pending` mutation tool

**AC13** — `sweep_stale_pending(hours: int = 168, *, action: str = "mark_failed", dry_run: bool = False, history_path: Path | None = None) -> dict`:
- `action ∈ {"mark_failed", "delete"}`; unknown → `ValidationError`.
- `hours < 1` → `ValidationError`.
- **Matches rows by `attempt_id` equality** — candidates filtered by `status="pending"` + `timestamp < cutoff`; mutations target recorded `attempt_id`s (R2 finding; prevents clobber of concurrent `refine_page` with same `page_id`).
- `dry_run=True`: returns candidates without mutation.
- `action="delete"` writes `append_wiki_log("sweep", ...)` to `wiki/log.md` **BEFORE** mutation (T4 + D-NEW-4).
- Lock: `file_lock(resolved_history_path)` only; single load→mutate→save span.
- Returns `{"swept": N, "action": ..., "sweep_id": "8-hex"|None, "dry_run": bool}`.

**AC14** — MCP `kb_refine_sweep(hours=168, action="mark_failed", dry_run=False) -> str`:
- Validates inputs; returns `"Error: ..."` on `ValidationError` / unexpected (via `_sanitize_error_str`).
- Returns `json.dumps(result)` on success.
- **Updates `src/kb/mcp/app.py:26` `_TOOL_GROUPS` Quality group tuple to list `("kb_refine_sweep", "quality review.")`** (R2 D-NEW-3).

**AC15** — CLI `kb refine-sweep --age-hours 168 --action mark_failed [--dry-run]`:
- Click command name hyphenated (R2); Python function name `refine_sweep`.
- Prints `json.dumps(result, indent=2)` on success; `_error_exit` on failure.
- Returns full helper dict (local-use exception).

**AC16** — Tests `tests/test_cycle20_sweep_stale_pending.py`:
- Happy path mark_failed: flips pending → failed with all sweep fields; preserves `attempt_id`.
- Delete path: removes row; `wiki/log.md` audit line present BEFORE mutation.
- Dry-run: candidates returned; history unchanged.
- Idempotence.
- Under-cutoff untouched.
- Action validation; `hours=0` validation.
- **attempt_id matching (R2):** (a) unrelated pending with different `page_id` untouched; (b) same `page_id` with different `attempt_id` untouched.
- Lock serialisation: spy on `load_review_history`/`save_review_history` call order within lock span.

### Cluster D — `list_stale_pending` MCP/CLI surface

**AC17** — MCP `kb_refine_list_stale(hours=24) -> str`:
- Reads `list_stale_pending`.
- Projects `[{"attempt_id": ..., "page_id": ..., "timestamp": ..., "notes_length": len(row.get("revision_notes", ""))}, ...]`.
- Excludes `revision_notes` entirely.
- **Updates `_TOOL_GROUPS` to list `("kb_refine_list_stale", "quality review.")`** (D-NEW-3).

**AC18** — CLI `kb refine-list-stale --hours 24`:
- Returns full helper dict (may include `revision_notes`).
- Prints JSON to stdout.

**AC19** — Tests `tests/test_cycle20_list_stale_surfaces.py`:
- Both surfaces return the stale row.
- **Asymmetric:** MCP keys exactly `{attempt_id, page_id, timestamp, notes_length}`, NO `revision_notes`. CLI MAY contain `revision_notes`.
- `notes_length == len(fixture_revision_notes)`.

### Cluster E — Windows tilde path

**AC20** — `tests/test_cycle20_windows_tilde_path.py`:
- `@pytest.mark.skipif(sys.platform != "win32")`.
- `ctypes.windll.kernel32.GetShortPathNameW` with `ctypes.create_unicode_buffer(260)`.
- **Roundtrip sanity:** `GetLongPathNameW(short) == long`. Skip with `pytest.skip` if fails.
- Assert `_canonical_rel_path(long, raw_dir) == _canonical_rel_path(short, raw_dir)`.
- Skip if `short == long` (8.3 disabled).

### Cluster F — diskcache CVE check

**AC21** — Non-code: `pip index versions diskcache`; compare `first_patched_version`. If patched: bump + CHANGELOG + BACKLOG delete. If not: dated `# Re-checked 2026-04-21` note.

---

## VERDICT
- Status: FINALIZED
- Total ACs: 21 (unchanged)
- Blockers resolved: 0
- Majors amended: 9
- NITs amended: 5
- Escalations: 0
- Proceed to Step 7: YES
