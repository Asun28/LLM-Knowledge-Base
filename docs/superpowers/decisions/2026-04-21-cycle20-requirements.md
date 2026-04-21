# Cycle 20 — Requirements + Acceptance Criteria

**Date:** 2026-04-21
**Cycle predecessor:** Cycle 19 (PR #33 merged at `9788103`; 2631 passed + 8 skipped; 2639 collected).
**Scope theme:** Exception taxonomy (HIGH #2) + slug-collision O_EXCL hardening (HIGH #16) + operator sweep/visibility for refine two-phase write (cycle-19 AC8b deferral) + misc housekeeping (Windows tilde test, diskcache CVE upstream check).
**Non-goals:** Mass migration of all 60+ `except Exception` sites (deferred to a focused exception-narrowing cycle to avoid cycle-17-L1 blast-radius); two-phase compile pipeline; graph shared cache; `_raw/` staging; `kb_merge`.

## Problem

Five distinct pain points have accumulated in BACKLOG.md that share enough adjacency to land in one cycle:

1. **HIGH #2 — No exception taxonomy.** The codebase has exactly two custom exceptions (`LLMError`, `CaptureError`) and ~60+ bare `except Exception` sites across `cli.py`, `compile/compiler.py`, `mcp/*`, `ingest/pipeline.py`, `query/engine.py`. CLI cannot distinguish "bad extraction JSON" from "LLM network flap" from "manifest write failure"; every error becomes a generic `Error: <truncated message>`. Narrow exception taxonomy unlocks selective retry, testable error paths, and clearer user messaging.

2. **HIGH #16 — `_write_wiki_page` slug-collision TOCTOU.** `ingest/pipeline.py:603` (summary write) + `ingest/pipeline.py:948-952` (item batch write) both check `path.exists()` before calling `_write_wiki_page`/`_update_existing_page`. Concurrent `ingest_source` calls with colliding slugs (e.g., `"My Article"` vs `"My  Article"` → same `my-article`) both see False and both call `_write_wiki_page` → `atomic_text_write`. Last writer wins; first source's summary is silently overwritten. `kb_create_page` and `kb_save_source` already use O_EXCL (since cycle-1 HIGH); the hot-path ingest pipeline does not.

3. **Cycle-19 deferral — `list_stale_pending` has no mutation/sweep tool.** Cycle 19 AC8b shipped the read-only `list_stale_pending(hours=24)` helper but explicitly deferred the sweep/auto-promote mutation tool + MCP/CLI surfaces. Stale pending rows accumulate with no ergonomic way to clear them.

4. **Cycle-19 deferral — Windows tilde-shortened path coverage.** `_canonical_rel_path` handles POSIX symlinks in T-13b; the T-13a tilde-shortened DOS path (e.g., `C:\PROGRA~1` vs `C:\Program Files`) is a placeholder skipif because constructing such paths in pytest requires platform-specific fixtures.

5. **CVE housekeeping — diskcache==5.6.3 (`CVE-2025-69872`) upstream check.** The pickle-deserialization RCE has been tracked since cycle 8. Per `feature-dev` Step 11.5 + 15 rules, each cycle should re-check whether the upstream has released a patched version.

## Non-goals

- Mass migration of every `except Exception` site (~60+). That is a blast-radius risk (cycle-17 L1) and requires per-site judgement: some need to stay broad at the boundary. Cycle 20 narrows only 3 hot-path sites + ships the taxonomy + exports + test + CLAUDE.md convention note.
- Compile-wiki real two-phase pipeline (HIGH #4) — architectural change; dedicated cycle.
- Graph shared cache + invalidation (HIGH #5) — unchanged from cycle 19.
- MCP async def (HIGH #12) — FastMCP thread-pool behavior change; needs its own threat model.
- CLI ↔ MCP parity auto-generation (MEDIUM) — large refactor; dedicated cycle.
- `.llmwikiignore` + secret scanner, `_raw/` staging, `kb_merge`, session capture — Phase 5 feature work.
- Python stdlib `O_BINARY` cross-platform edge cases for O_EXCL — if Windows throws `OSError` for reasons other than FileExistsError, we propagate; O_EXCL itself is supported on Windows by CPython.

## Acceptance criteria (cycle 20, pre–Step-5 gate)

### Cluster A — `kb.errors` exception taxonomy

**AC1** — New module `src/kb/errors.py` defines:
- `KBError(Exception)` — base class for all kb-originated errors.
- `IngestError(KBError)` — raised inside `kb.ingest.pipeline.ingest_source` for extraction/validation/manifest failures.
- `CompileError(KBError)` — raised inside `kb.compile.compiler.compile_wiki`.
- `QueryError(KBError)` — raised inside `kb.query.engine.query_wiki`/`search_pages` for synthesis/retrieval failures.
- `ValidationError(KBError)` — input-validation failures (page_id, wiki_dir, manifest_key, notes length, etc.).
- `StorageError(KBError)` — atomic-write / file-lock / manifest-save / evidence-trail append failures. Includes a convention for sub-kinds via a `kind: str` field (`summary_collision`, `manifest_corrupt`, `lock_timeout`) so callers branch on taxonomy, not string match.

**AC2** — `LLMError` (at `src/kb/utils/llm.py:381`) reparented from `Exception` to `KBError`. Existing `kind` attribute preserved; import path unchanged; existing `isinstance(err, LLMError)` checks still work. `CaptureError` (at `src/kb/capture.py:544`) similarly reparented. No behavioural change.

**AC3** — `src/kb/__init__.py` adds `KBError`, `IngestError`, `CompileError`, `QueryError`, `ValidationError`, `StorageError` to `__all__` (alongside existing `LLMError` if present); re-exports via `from kb.errors import ...`. `kb.LLMError` remains as a backward-compat alias (already re-exported or available via `from kb.utils.llm import LLMError`).

**AC4** — CLAUDE.md "Error Handling Conventions" section gains a new bullet listing the taxonomy + the rule "new code that needs to raise should subclass the nearest existing KBError specialization; bare `except Exception` is only acceptable at boundary layers (CLI top-level, MCP tool wrappers, LLM retry loop)."

**AC5** — Narrow hot-path migration (3 sites only — deliberate under-reach per cycle-17 L1):
- `compile/compiler.py:494` outer `except Exception as e:` in `compile_wiki` → `except (KBError, OSError) as e:` + explicit `raise CompileError(str(e)) from e` if the original wasn't already a KBError subclass. Keep inner `except Exception` sites unchanged for now (they are per-source continue-on-error loops).
- `ingest/pipeline.py` main `_run_ingest_body` outer guard — narrow to `(IngestError, OSError, ValueError)` and wrap unexpected into `IngestError`.
- `query/engine.py:195,206` two outer `except Exception as exc:` sites wrap into `QueryError(str(exc)) from exc` or narrow to `(KBError, OSError)`.

**AC6** — Tests `tests/test_cycle20_errors_taxonomy.py`:
- Subclass-relationship tests: `IngestError`, `CompileError`, `QueryError`, `ValidationError`, `StorageError` all subclass `KBError`; `KBError` subclasses `Exception`.
- `LLMError` subclasses `KBError`; `LLMError(..., kind="auth").kind == "auth"` preserved.
- `CaptureError` subclasses `KBError`.
- `StorageError(msg, kind="summary_collision")` exposes `.kind`; default `.kind is None`.
- Import-surface test: `from kb import KBError, IngestError, CompileError, QueryError, ValidationError, StorageError` succeeds.

**AC7** — Regression test behavioural — pin one hot-path conversion per narrowed site: injecting an `OSError` at the compile_wiki write path raises `CompileError` with the original exception in `__cause__`. Verifies the taxonomy is WIRED, not just defined (rule: cycle-11 L1 "no source-file string reads; import + call + assert behavior").

### Cluster B — `_write_wiki_page` slug-collision O_EXCL hardening

**AC8** — `_write_wiki_page(path, title, ..., *, exclusive: bool = False)` gains a keyword-only `exclusive` parameter. When True, replaces `atomic_text_write(...)` with:
```python
fd = os.open(str(effective_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
try:
    os.write(fd, frontmatter.dumps(post, sort_keys=False).encode("utf-8") + b"\n")
    os.fsync(fd)
finally:
    os.close(fd)
```
On `FileExistsError`, raises `StorageError("summary_collision: <path>", kind="summary_collision")`. Default `exclusive=False` preserves all existing callers' behavior byte-for-byte.

**AC9** — `ingest_source` summary write (`pipeline.py:603` region) passes `exclusive=True`. On `StorageError(kind="summary_collision")`, falls through to `_update_existing_page(summary_path, source_ref=..., extraction=extraction, verb="Summarized")` so the second ingest merges into the first.

**AC10** — `_process_item_batch` item write at `pipeline.py:949-956` — when the TOCTOU check `item_path.exists()` says False but the subsequent `_write_wiki_page` hits `FileExistsError` via `exclusive=True`, pivot to `_update_existing_page` in the same branch. The existing `.exists()` branch stays as a fast path; O_EXCL is the correctness guarantee.

**AC11** — Evidence trail after exclusive-create — `append_evidence_trail` is called only on the successful-create path. When O_EXCL fails, the merge path's `_update_existing_page` writes its own evidence trail (already does today). No double-write.

**AC12** — Tests `tests/test_cycle20_write_wiki_page_exclusive.py`:
- `exclusive=False` (legacy) branch byte-identical to pre-change behavior on fresh-path write.
- `exclusive=True` on fresh path: file created with frontmatter + content + evidence trail.
- `exclusive=True` on existing path: raises `StorageError(kind="summary_collision")`; file untouched.
- Concurrent-write race using `threading.Thread` × 2: both call summary write with same slug; assert exactly one succeeds with O_EXCL + one merges via fallback; final page has BOTH sources in frontmatter `source:` list. (Thread not multiprocess — cycle-17 L1 notes MP-lock tests deferred; thread variant catches intra-process race which is the documented HIGH #16 scenario.)

### Cluster C — `sweep_stale_pending` mutation tool

**AC13** — `src/kb/review/refiner.py::sweep_stale_pending(hours: int = 168, *, action: str = "mark_failed", history_path: Path | None = None) -> dict[str, int]`:
- Allowed `action` values: `"mark_failed"` (default, adds `status="failed"`, `error="abandoned-by-sweep"`, `sweep_id=uuid4().hex[:8]`, `sweep_at=<ISO-now>`) or `"delete"` (removes the pending row entirely).
- Unknown `action` raises `ValidationError("unknown sweep action: <action>; expected one of mark_failed|delete")`.
- `hours < 1` raises `ValidationError("hours must be >= 1")`.
- Acquires `file_lock(resolved_history_path)` ONLY — no page locks (page body is long-gone; only the history row is mutated). Lock span: load → mutate → save. Single `file_lock` span per cycle-19 AC9 lock-order rule.
- Returns `{"swept": <int>, "action": "mark_failed|delete", "sweep_id": "<8-hex>" or None for delete}`.
- Idempotent: re-running the same sweep on already-failed rows is a no-op (only rows with `status="pending"` and `timestamp < cutoff` are candidates).

**AC14** — MCP `kb_refine_sweep(hours: int = 168, action: str = "mark_failed") -> str` in `mcp/quality.py`:
- Validates `hours` as int ≥ 1 (otherwise returns `"Error: ..."` string per MCP convention).
- Calls the library helper, returns `json.dumps(result)` on success.
- `ValidationError` from the helper → `"Error: <msg>"` string. Unexpected exceptions → `"Error: sweep failed: <sanitized>"` via `_sanitize_error_str`.

**AC15** — CLI `kb refine-sweep --age-hours 168 --action mark_failed`:
- Prints `json.dumps(result, indent=2)` to stdout on success.
- Exit 0 on success; exit 1 on `ValidationError` / unexpected error (via `_error_exit`).

**AC16** — Tests `tests/test_cycle20_sweep_stale_pending.py`:
- Happy path: pending row older than cutoff with `action="mark_failed"` → flipped to `failed` with `sweep_id`, `sweep_at`, `error` fields. Original `attempt_id` preserved.
- Delete path: row removed entirely.
- Idempotence: second sweep with same cutoff is a no-op (0 swept).
- Under-cutoff: pending row younger than cutoff is untouched.
- Action validation: unknown action raises `ValidationError`.
- Lock held-through: monkeypatch `save_review_history` to inject a concurrent-write simulation; assert the `file_lock` prevents interleaving by spy on `load_review_history` + `save_review_history` call order (≥1 load before each save per the locked-RMW invariant per cycle-17 L1 guidance).

### Cluster D — `list_stale_pending` MCP/CLI surface

**AC17** — MCP `kb_refine_list_stale(hours: int = 24) -> str` in `mcp/quality.py` — reads `list_stale_pending`, returns `json.dumps([{"attempt_id": ..., "page_id": ..., "timestamp": ...}, ...])`.

**AC18** — CLI `kb refine-list-stale --hours 24` — prints the same JSON payload to stdout.

**AC19** — Tests `tests/test_cycle20_list_stale_surfaces.py` — both surfaces return expected JSON on fixture history with 2 pending rows (one stale, one fresh) — only the stale row returned.

### Cluster E — Windows tilde-shortened path coverage

**AC20** — `tests/test_cycle20_windows_tilde_path.py::test_canonical_rel_path_tilde_equivalence`:
- `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tilde-shortened path test")`
- Uses `ctypes.windll.kernel32.GetShortPathNameW` to obtain tilde-shortened form for the temp path.
- Constructs a source at the long-form path; manifest key via `_canonical_rel_path(long_form_path, raw_dir)` — remembers the key.
- Re-runs `_canonical_rel_path(short_form_path, raw_dir)` → assert it yields the SAME manifest key.
- Skip-within-test if `GetShortPathNameW` returns the long form verbatim (happens on filesystems with 8.3 disabled) — `pytest.skip("filesystem does not generate tilde-shortened names")`.

### Cluster F — diskcache CVE upstream check

**AC21** — Non-code audit: run `pip index versions diskcache` and compare against `CVE-2025-69872` GHSA-w8v5-vhqr-4h9v `first_patched_version`. If patched: bump `requirements.txt` pin; add CHANGELOG entry; delete the BACKLOG MEDIUM note. If NOT patched: add a dated `# Re-checked 2026-04-21: still no upstream patch` note to BACKLOG and CHANGELOG. Either outcome is a cycle-20 deliverable (visibility, not silence).

## Blast radius

| Module / file | AC touch | Risk surface |
|---|---|---|
| `src/kb/errors.py` | AC1 (NEW) | Module creation only. Zero risk. |
| `src/kb/__init__.py` | AC3 | Re-exports. Affects `import kb` surface. |
| `src/kb/utils/llm.py` | AC2 | `LLMError` parent class change; import path unchanged; `isinstance` still works through MRO. |
| `src/kb/capture.py` | AC2 | `CaptureError` parent class change; same reasoning. |
| `src/kb/compile/compiler.py` | AC5 | One outer `except` narrowed. Ingest error path is well-covered by tests. |
| `src/kb/ingest/pipeline.py` | AC5, AC9, AC10 | Hottest file in the codebase. Tests must stress summary + item write paths under concurrency. |
| `src/kb/query/engine.py` | AC5 | Outer except narrowing at synthesis layer. |
| `src/kb/review/refiner.py` | AC13 | New helper; adjacent to cycle-19 AC8/AC8b; reuses the same file_lock pattern. |
| `src/kb/mcp/quality.py` | AC14, AC17 | Two new tool registrations; MCP surface grows from 26 → 28 tools. |
| `src/kb/cli.py` | AC15, AC18 | Two new subcommands. |
| `CLAUDE.md` | AC4 | Convention doc update. |
| `BACKLOG.md` / `CHANGELOG.md` | AC21 | Upstream CVE status. |
| `requirements.txt` | AC21 (conditional) | Only if diskcache has upstream patch. |

## Test count expectations

- +~25 tests across 5 new test files (`test_cycle20_errors_taxonomy.py`, `test_cycle20_write_wiki_page_exclusive.py`, `test_cycle20_sweep_stale_pending.py`, `test_cycle20_list_stale_surfaces.py`, `test_cycle20_windows_tilde_path.py`).
- One of those tests is `@skipif` gated (Windows tilde), so collected-count may be ~2640+ collected with Windows +1 on Windows runs.
- Target delta: 2639 → 2664 collected (+25).

## Counts + ship criteria

- ~21 production ACs across ~10 files (core src + CLAUDE.md + BACKLOG.md + CHANGELOG.md + requirements.txt + 5 new test files).
- Ship when: Step 10 CI gate clean, Step 11 security verify clean, R1/R2 PR review addressed, R3 fires per cycle-17 L4 / cycle-19 L4 triggers (≥15 ACs + new MCP surface + audit-doc drift risk).

## Open questions for Step 3/4/5

- **Q1** — Should `kb.errors` live at `src/kb/errors.py` (flat) or `src/kb/errors/__init__.py` (package with `base.py`, `ingest.py`, etc.)? Flat file under 80 LOC seems right for cycle 20; split later if more kinds arrive.
- **Q2** — Should `LLMError.__init__` signature stay `(message, *, kind=None)` or gain a `cause: Exception | None = None` (PEP 487 `__cause__` is standard via `raise X from Y`)? Keep existing signature.
- **Q3** — On `FileExistsError` from O_EXCL in `_write_wiki_page`, is raising `StorageError(kind="summary_collision")` the right contract, or should it return a sentinel (e.g., `False`) so caller disambiguates without exception cost? Exception is cleaner for rare event; slug collision is not a hot path.
- **Q4** — `sweep_stale_pending` default `hours=168` (= 1 week) or `hours=24`? One week gives operators time to notice stuck pending rows before sweep; day is too aggressive for silent auto-promote. Keep 168h default, operators can override.
- **Q5** — `sweep_stale_pending` action `"mark_failed"` vs `"promote_failed"` wording — pick the one that matches the rest of the codebase. Lint sees `status="failed"` + a `sweep_id`, so `"mark_failed"` is accurate.
- **Q6** — Should `kb_refine_list_stale` and `kb_refine_sweep` share a single prefix (`kb_refine_*`) with `kb_refine_page` or sit under a new `kb_review_*` cluster? Keep `kb_refine_*` since `kb_refine_page` / `kb_review_page` split already exists and refine-history is review-adjacent; the new tools are refine-history-specific.
- **Q7** — `exclusive=True` on Windows O_EXCL — does CPython's `os.open(O_EXCL|O_CREAT)` atomically fail on an existing file, or is there a race between `CreateFileW(CREATE_NEW)` returning and the file being visible to other processes? Context7 check or `ntdll` docs — defer to Step 6 if needed. Existing `kb_create_page` has used this pattern since cycle 1; assume same semantics apply here.
- **Q8** — Does the narrow Cluster A migration (AC5 — 3 outer-except sites) risk breaking legacy tests that `pytest.raises(Exception)` against those sites? `except KBError` is a narrower raise; callers that expect `Exception` still catch it (subclass MRO). Tests that monkeypatch to force a `RuntimeError` may now propagate; pytest greps for this pre-migration.
- **Q9** — Should AC20 tilde-path test also cover the GetLongPathNameW round-trip (long → short → long yields the original) or just the _canonical_rel_path equivalence? Latter is smaller and targeted at the actual production invariant.
- **Q10** — AC21 diskcache CVE: if STILL unpatched, what is the threshold at which we replace diskcache with a stdlib cache? Outside cycle-20 scope; document only.
