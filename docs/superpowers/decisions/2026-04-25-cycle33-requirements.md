# Cycle 33 — Requirements + Acceptance Criteria

## Problem

Two pre-Phase 5 BACKLOG MEDIUM items are quick, defensible wins that have been deferred across cycles:

1. **`mcp/core.py:762,881` raw `OSError` interpolation in `Error[partial]:` and paired `logger.warning`** — `kb_ingest_content` and `kb_save_source` post-create write-failure paths emit `f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); ..."` and `logger.warning("...partial write to %s: %s; client must retry", _rel(file_path), write_err)` where `write_err` is a raw `OSError` whose `__str__` on Windows includes the FULL absolute path (`[WinError 5] Access is denied: 'D:\\Projects\\...\\raw\\articles\\foo.md'`). `_rel(file_path)` is sanitised but `{write_err}` is not. Cycle-32 AC3 newly routes `Error[partial]:` strings to CLI stderr via `_is_mcp_error_response` widening, so the leak surfaces to operator terminals under write-failure conditions. Threat T11 in cycle 32. Same-class peer at `mcp/core.py:280` `kb_query` `save_as` write-failure logger.warning passes raw `exc`.

2. **`ingest/pipeline.py` index-file write order — re-ingest duplicate-prevention contract is undocumented and unpinned by tests.** BACKLOG entry says "A crash between `_sources.md` and manifest writes can duplicate entries on re-ingest." Source inspection shows `_update_sources_mapping` and `_update_index_batch` already implement dedup guards (line 777 `if f"\`{source_ref}\`" not in content`, line 818 `if f"[[{subdir}/{slug}|" in content or ...: continue`). The contract is not documented in docstrings and not pinned by regression tests — a future refactor could quietly drop dedup and the BACKLOG entry's failure mode would re-emerge silently.

Both are MEDIUM-severity audit-trail items: **MCP error strings flowing to the operator terminal must not leak absolute filesystem paths** (cycle-7 AC12/13 redaction discipline; cycle-18 AC13 helper extension); **idempotency of index-file writes across crash-then-re-ingest must be a pinned contract**, not an implementation accident.

## Non-goals

- NOT migrating ALL `mcp/*` `logger.warning(..., e)` sites that pass raw exceptions. Scope is limited to the three named sites in `mcp/core.py` (kb_ingest_content post-OSError, kb_save_source post-OSError, kb_query save_as post-OSError). Other files (`browse.py`, `health.py`, `quality.py`) typically pass `e` from a generic `except Exception as e:` block where the exception does not carry a known path attribute and the helper-redacted regex sweep is already adequate; expanding scope to those is a separate cycle's call.
- NOT introducing a `kb.graph.cache` module (Phase 4.5 HIGH item). Defer — large blast radius.
- NOT changing the multi-write `index.md → _sources.md → manifest → log.md → contradictions.md` ordering or introducing an `IndexWriter` abstraction. Scope is **document and pin the existing dedup-on-reingest contract**, not refactor the order.
- NOT modifying production code in `_update_sources_mapping` / `_update_index_batch` semantics — only docstrings + tests.
- NOT touching the BACKLOG `pip` / `litellm` / `ragas` / `diskcache` CVE entries (no upstream fix or transitive constraint blocks them).

## Acceptance criteria (testable as pass/fail)

### File 1 — `mcp/core.py` (path-leak in `Error[partial]:` + paired logger.warnings)

**AC1.** `kb_ingest_content` post-create OSError return (currently `core.py:762`) interpolates `{_sanitize_error_str(write_err, file_path)}` in place of raw `{write_err}`. After the change, an `OSError` whose `str(...)` contains the absolute file_path is rendered with the path replaced by its `_rel(...)` form (or `<path>` if the regex sweep catches a free-form absolute literal). PASS = the returned string contains neither `D:\\` (Windows drive-letter literal) nor `/Users/`/`/home/`/`/tmp/` POSIX-absolute prefix.

**AC2.** `kb_save_source` post-create OSError return (currently `core.py:881`) — same fix as AC1.

**AC3.** The paired `logger.warning(..., %s, write_err)` calls at `core.py:756-760` (kb_ingest_content) and `core.py:875-879` (kb_save_source) use a pre-formatted `_sanitize_error_str(write_err, file_path)` string instead of passing the raw exception. PASS = `caplog.records` for these lines contains no absolute-path literal under a forced-OSError test fixture.

**AC4.** Same-class peer at `core.py:279-281` (kb_query `save_as` write-failure path) — `logger.warning("save_as write failed for slug=%r: %s", slug, exc)` swapped to `_sanitize_error_str(exc, target)` so the captured log line is consistent with the already-sanitised return string at line 281.

**AC5.** Regression tests in a new versioned test file (`tests/test_cycle33_mcp_core_path_leak.py`) cover AC1, AC2, AC3, AC4 with TWO platforms each:
- (a) Windows-style: monkeypatch `os.fdopen` (or the `f.write` call) to raise `OSError(13, "Access is denied", "D:\\\\Projects\\\\test\\\\fake.md")` and assert returned-string + caplog contain neither `D:\\` nor `D:/Projects/test/fake.md` raw form;
- (b) POSIX-style: same fixture but with `OSError(13, "Permission denied", "/tmp/test/fake.md")` and assert neither `/tmp/test/fake.md` nor `Permission denied: '/tmp/test/fake.md'` literal appears.

Tests must FAIL when the production fix is reverted (revert-fail check per cycle-24 L4).

### File 2 — `ingest/pipeline.py` (index-file write idempotency contract)

**AC6.** Add a `## Idempotency` paragraph to `_update_sources_mapping` and `_update_index_batch` docstrings stating: "Safe to re-call after a crash that aborted the ingest before manifest-save. The first call's effect is preserved; the second call is a no-op for already-present entries (sources: identical-ref + identical-pages, index: same `[[subdir/slug]]` already in section)."

**AC7.** Add a regression test in `tests/test_cycle33_ingest_index_idempotency.py` that:
- (a) seeds an empty `_sources.md` and `index.md` via the `tmp_wiki` fixture;
- (b) calls `_update_sources_mapping("raw/articles/x.md", ["entities/foo", "concepts/bar"], wiki_dir=tmp_wiki)` twice;
- (c) asserts `_sources.md` contains exactly ONE line referencing `raw/articles/x.md` (no duplicates);
- (d) calls `_update_index_batch([("entity", "foo", "Foo Title"), ("concept", "bar", "Bar Title")], wiki_dir=tmp_wiki)` twice;
- (e) asserts `index.md` contains exactly ONE entry per `[[entities/foo|Foo Title]]` / `[[concepts/bar|Bar Title]]` (no duplicates).

**AC8.** Crash-recovery scenario test:
- (a) call `_update_sources_mapping(...)` with a NEW source-ref (write succeeds);
- (b) simulate manifest-save failure by NOT updating the manifest;
- (c) call `_update_sources_mapping(...)` again with the SAME source-ref and the SAME pages (full re-ingest after crash);
- (d) assert `_sources.md` content unchanged after step (c);
- (e) call `_update_sources_mapping(...)` with the SAME source-ref but ADDED pages (e.g. concept added in re-ingest);
- (f) assert the existing line is MERGED (not duplicated) and now contains all old + new page IDs.

### File 3 — `BACKLOG.md` (lifecycle cleanup)

**AC9.** After AC1-AC5 ship, DELETE the `mcp/core.py:762,881` MEDIUM entry from `BACKLOG.md` per the lifecycle rule. Add a brief entry to `CHANGELOG.md` `[Unreleased]` Quick Reference and the per-cycle detail to `CHANGELOG-history.md`.

**AC10.** After AC6-AC8 ship, DELETE the `ingest/pipeline.py` index-file write order MEDIUM entry from `BACKLOG.md` (the dedup contract is now both implemented AND pinned, which closes the failure mode the entry described). Same CHANGELOG / CHANGELOG-history entries as AC9.

## Blast radius

| Module | Severity | Change shape |
|--------|----------|--------------|
| `src/kb/mcp/core.py` | LOW (bug fix, no API surface change) | 4 line-level swaps: 2 `Error[partial]:` interpolations + 2 paired `logger.warning` arg lists + 1 `kb_query.save_as` logger.warning |
| `src/kb/ingest/pipeline.py` | LOWEST (docstring-only — no code change) | 2 docstrings annotated with Idempotency paragraph |
| `tests/test_cycle33_*.py` | NEW FILES | ~70-100 LOC test code total across two files |
| `BACKLOG.md` | n/a (deletion-only) | 2 deleted bullet entries |
| `CHANGELOG.md` | n/a (compact entry) | 1 cycle-33 Quick Reference row |
| `CHANGELOG-history.md` | n/a | 1 cycle-33 detail block |
| `CLAUDE.md` | LOWEST | 1 test count + module-map line update if AC6's docstring annotations warrant a Key APIs note |

No public API change. No new imports beyond the existing `_sanitize_error_str` (already imported at `core.py:70`). No new dependencies. No threat-model item retired (T11 in cycle 32 was the originating threat — this closes its remaining surface).

## Threat-model index (will be filled at Step 2)

T1 — path leak in MCP error strings to operator terminal (cycle 7 AC12/13; cycle 18 AC13; cycle 23 L3; cycle 32 T11)
T2 — index-file dedup contract regression (silent re-ingest duplication if dedup guards are removed)
T3 — caplog regression test pollution / handler attachment under pytest-xdist
T4 — `OSError.filename` attribute stripping in `sanitize_error_text` — the helper already handles this (cycle 18 AC13 path attribute scan)
