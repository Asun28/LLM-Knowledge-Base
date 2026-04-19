# Cycle 13 — Step 2 Threat Model

**Date:** 2026-04-19
**Subagent:** Opus 4.7
**Cycle scope ref:** `docs/superpowers/decisions/2026-04-19-cycle13-requirements.md`

## Analysis

The cycle-13 changes are almost entirely mechanical migrations from `frontmatter.load(str(path))` to the cached `load_page_frontmatter(path)` helper landed in cycle 12. The trust-boundary surface is essentially unchanged: every migrated call site already reads a caller-provided `Path` that was either constructed from a validated wiki page ID (`wiki_dir / f"{page_id}.md"` — see `augment.py:67`), sourced from the internal wiki scan (`semantic.py`, `review/context.py`), or came from a NetworkX graph attribute set by `kb/graph/builder.py::build_graph` which always derives `path=str(page_path)` from pages discovered via `scan_wiki_pages(wiki_dir)`. No attacker-controlled string ever reaches `frontmatter.load` that is not already there today; the migration does not widen any existing surface. The one subtlety is that `load_page_frontmatter` performs an extra `page_path.stat()` call before delegating to the cached loader — on the graph export site (`export.py:132`) `path` is a bare `str` pulled from a NetworkX node attribute and must be wrapped in `Path(...)`, and on any of the migrated sites a caller passing a `str` instead of a `Path` would trigger `AttributeError` on `.stat()` (semantic-failure, not security).

The two genuinely new surfaces are (1) the CLI-boot sweep of `PROJECT_ROOT/.data` and `WIKI_DIR` via `sweep_orphan_tmp`, and (2) the `raw_dir` derivation inside `run_augment`. For (1), `sweep_orphan_tmp` already has three layered guards: it resolves the directory, scans non-recursively (cannot walk into a user wiki), and only unlinks `*.tmp` files older than 3600s. A concurrent CLI invocation that is mid-way through `atomic_text_write` holds the tempfile for at most milliseconds before the `Path(tmp_path).replace(path)` call; the 1-hour threshold is ~3.6 million times the worst-case write latency. For (2), `wiki_dir.parent / "raw"` mirrors the already-shipped `effective_data_dir` pattern (lines 569-580). The derivation is purely string-level (`Path.parent` is lexical), so a caller passing `wiki_dir=Path("/tmp/foo/wiki")` gets `raw_dir=Path("/tmp/foo/raw")` deterministically.

## Trust boundaries

- **CLI boot → filesystem.** New: `kb <anycmd>` now sweeps `PROJECT_ROOT/.data` and `WIKI_DIR` for orphan `*.tmp` files at startup.
- **`run_augment` caller → raw_dir derivation.** New: when caller supplies custom `wiki_dir` but omits `raw_dir`, `wiki_dir.parent / "raw"` is used.
- **NetworkX graph node `path` attribute → `load_page_frontmatter`.** Migrated `export.py:132`; `path` is always set by `build_graph` from `scan_wiki_pages(wiki_dir)`.
- **`page_path.stat()` syscall inside cached helper.** Already in place since cycle 12; each migrated site now goes through one additional stat call per invocation.

## Data classification

All data flowing through these changes is **local wiki markdown frontmatter** (non-sensitive). No PII, no secrets, no network data. `sweep_orphan_tmp` operates on atomic-write sibling files that never contained durable state.

## AuthN/AuthZ

**No new authn/authz surface.** Both the CLI sweep and the `raw_dir` derivation inherit existing filesystem ACL semantics; no new privilege.

## Logging / audit

- **CLI boot sweep** SHOULD log non-zero removal counts at INFO. Helper already handles errors at WARNING. Do NOT fail CLI boot on sweep error — helper returns 0 on directory problem.
- **`raw_dir` derivation** is pure logic with no IO; no new log site.
- **Migrated frontmatter reads** — no new logging; cached helper preserves caller's existing `try/except` contract.

## Threat items

### T1 — CLI-boot sweep deletes in-flight concurrent atomic-write tmp file
**Severity: LOW.**
- Scenario: two `kb` CLI invocations race; B's boot-time sweep races against A's mid-write tmp file.
- Mitigation: keep `max_age_seconds=3600.0` (default). Do NOT override with smaller value.
- Verification: grep `src/kb/cli.py` for `sweep_orphan_tmp`; confirm no `max_age_seconds=` kwarg <3600.

### T2 — `wiki_dir.parent / "raw"` directory escape via relative/symlinked wiki_dir
**Severity: LOW.**
- Scenario: caller passes `wiki_dir=Path("wiki")` (relative); derived raw_dir resolves to CWD-relative path.
- Mitigation: mirror existing `effective_data_dir` pattern exactly; do NOT add `.resolve()` (would surprise users with symlinked mounts).
- Verification: grep `augment.py` for the new `elif wiki_dir != WIKI_DIR: raw_dir = wiki_dir.parent / "raw"` block; confirm structure mirrors lines 574-580 (no `.resolve()`).

### T3 — Graph-export `path` attribute is a string, not a Path — cached helper type mismatch
**Severity: MEDIUM.**
- Scenario: `export.py:132` calls `frontmatter.load(path)` where `path` is the string stored by `build_graph`. Swapping to `load_page_frontmatter(path)` raises `AttributeError` at `.stat()`. Surrounding `except Exception` catches it and logs at DEBUG, silently degrading Mermaid titles.
- Mitigation: wrap as `load_page_frontmatter(Path(path))`.
- Verification: read `export.py:132` after the change; confirm `Path(path)`-wrapped. Add a behavioural test that loads a graph node with a string `path` attribute and asserts the Mermaid output contains the page's title.

### T4 — Cached helper returns stale metadata on FAT32 / OneDrive / SMB
**Severity: LOW.**
- Scenario: write-then-immediate-read could return pre-write metadata on coarse mtime filesystems.
- Mitigation: no in-scope migrated site is a write-then-read pattern. Document the mtime caveat where adjacent. For callers that need write-then-read, use `load_page_frontmatter.cache_clear()`.
- Verification: confirm no in-scope migration site precedes the cached read with an in-process write of the same path.

### T5 — Symlink-traversal via `path` attribute in NetworkX graph
**Severity: LOW.**
- Scenario: wiki contains a symlink pointing outside `wiki_dir`; stored `path` would resolve to that target.
- Mitigation: invariant inherited from `scan_wiki_pages`; not widened by this cycle. `Path.stat()` follows symlinks identically to pre-migration `frontmatter.load`.
- Verification: confirm no new write-sites in this cycle.

### T6 — `WIKI_DIR` sweep deletes unrelated `.tmp` files from third-party apps
**Severity: LOW.**
- Scenario: `WIKI_DIR` configured to a shared dir where another app leaves `*.tmp` files older than 1h.
- Mitigation: kb is the sole producer of top-level `*.tmp` in `WIKI_DIR`. Non-recursive (`directory.glob("*.tmp")`, not `rglob`) means nested `.tmp` is never touched. Document the sweep scope in the CLI group docstring.
- Verification: grep new CLI-boot code for `rglob` (must not appear).

### T7 — `load_page_frontmatter` cache retains stale metadata after out-of-process edit
**Severity: LOW.**
- Scenario: long-running MCP server caches frontmatter; concurrent CLI rewrites; MCP still has cached entry.
- Mitigation: outer wrapper reads `st_mtime_ns` on every call and compares against cache key. Out-of-process writes that advance mtime_ns (every modern FS) naturally invalidate.
- Verification: confirm migrated sites call `load_page_frontmatter(page_path)` (wrapper) and NOT `_load_page_frontmatter_cached(...)` directly.

**Dep-CVE baseline:** 0 open Dependabot alerts; pip-audit shows 1 unfixed advisory (diskcache==5.6.3 CVE-2025-69872, already tracked in BACKLOG MEDIUM — no patched version available upstream).
