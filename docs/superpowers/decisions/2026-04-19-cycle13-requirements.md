# Cycle 13 — Step 1 Requirements + Acceptance Criteria

**Date:** 2026-04-19
**Base commit:** `663952c` (post cycle-12 merge)
**Feature branch:** `feat/backlog-by-file-cycle13`
**Tests baseline:** 2118 collected (per CHANGELOG `Backlog-by-file cycle 12` Stats line)

## Problem

Cycle 12 shipped two helpers — `kb.utils.pages.load_page_frontmatter` (LRU + mtime cache for read paths) and `kb.utils.io.sweep_orphan_tmp` (non-recursive `.tmp` cleanup) — but only partial caller migration. The BACKLOG explicitly carries three follow-up items targeting cycle 13:

1. `frontmatter.load(str(...))` migration: 5 sites in `lint/augment.py`, 1 in `lint/semantic.py`, 1 in `graph/export.py`, 1 in `review/context.py` — **8 sites total**. Cycle 12 AC11 only migrated the 4 strict read-only sites in `lint/checks.py`. Each unmigrated site re-parses YAML on every call and never benefits from the LRU cache.
2. `sweep_orphan_tmp` has no default caller. The helper exists in `utils/io.py` but is never invoked from CLI boot or `ingest_source` tail. Without a wired caller the OneDrive/SMB-mount `.tmp` accumulation problem the helper was designed to solve is unaddressed in shipped code.
3. `lint/augment.py::run_augment` defaults `raw_dir = raw_dir or RAW_DIR` independently of `wiki_dir`. When a caller passes a non-default `wiki_dir`, the augment run proposes against the custom wiki but reads/writes raw sources from the project-global `raw/`, breaking project isolation. Cycle 12 AC13 worked around this by passing both dirs explicitly in tests.

These three are mechanical, low-risk, file-grouped follow-ups on cycle 12's helpers. Group-fix-by-file batching collapses them into one cycle.

## Non-goals

- **No write-back site migration.** Sites that mutate frontmatter and call `frontmatter.dumps(post)` (augment.py:914, 1026, 1053) require a live `frontmatter.Post` object. Migrating them via reconstruction (`frontmatter.Post(content, **metadata)` + dump) risks the cycle-7 R1 Codex M3 YAML-key-alphabetization regression. Defer to a dedicated cycle that fixes YAML key ordering holistically.
- **No cache-invalidation API surface change.** `load_page_frontmatter.cache_clear()` already exists from cycle 12. This cycle migrates callers; it does not redesign the cache contract.
- **No `sweep_orphan_tmp` recursion or new sweep targets.** Helper stays non-recursive (`glob("*.tmp")`). Wiring picks ONE caller (CLI boot OR ingest tail), not both.
- **No `run_augment(resume=…)` re-wiring.** That is a separate Phase-5-pre-merge MEDIUM item with CLI/MCP surface implications. Out of scope.
- **No frontmatter loader API contract change.** `load_page_frontmatter(path)` keeps its `(metadata: dict, body: str)` tuple signature.

## Acceptance Criteria

Each AC is a single-line testable contract. ACs marked **(behavioural)** require a regression test that exercises the production code path; **(scope)** ACs are documentation/guard-only.

### Frontmatter migration — read-only sites (AC1–AC5)

- **AC1.** `src/kb/lint/augment.py:72` (`_collect_eligible_stubs` stub eligibility check) reads frontmatter via `load_page_frontmatter(page_path)` and consumes `metadata, body = …` rather than `post.metadata` / `post.content`. Exception class set widened to include the cached helper's re-raised classes (`OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError`). *(behavioural test — AC9)*
- **AC2.** `src/kb/lint/augment.py:1082` (`_post_ingest_quality` post-ingest source check) reads frontmatter via `load_page_frontmatter(page_path)`; `metadata.get("source")` semantics preserved. *(behavioural test — AC9)*
- **AC3.** `src/kb/lint/semantic.py:122` (`_group_by_shared_sources` page-paths branch) reads frontmatter via `load_page_frontmatter(page_path)`. The pre-loaded-bundle branch (line 111, `frontmatter.loads(content)`) is OUT OF SCOPE — that branch parses an already-in-memory string, not a file. *(behavioural test — AC10)*
- **AC4.** `src/kb/graph/export.py:132` (Mermaid title fallback) reads frontmatter via `load_page_frontmatter(Path(path))`. The pre-loaded `path` may be a string from a NetworkX node attribute; convert to `Path` first because the cached helper requires `.stat()`. *(behavioural test — AC11)*
- **AC5.** `src/kb/review/context.py:56` (`pair_page_with_sources`) reads frontmatter via `load_page_frontmatter(page_path)`; the broad `except yaml.YAMLError` becomes `except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError)` to match the cached helper's contract. *(behavioural test — AC12)*

### Write-back sites — explicit out-of-scope justification (AC6, scope)

- **AC6.** `src/kb/lint/augment.py:914` (`_record_verdict_gap_callout`), `:1026` (`_mark_page_augmented`), `:1053` (`_record_attempt`) MUST keep `frontmatter.load(str(path))`. Reason: each site mutates `post.metadata` and/or `post.content` then calls `frontmatter.dumps(post)`, which requires a live `frontmatter.Post` object. The cached helper returns a tuple; reconstructing a `Post` would risk YAML-key alphabetisation (cycle-7 R1 Codex M3 lesson). A grep + comment annotation is the deliverable; no behaviour change. *(scope test — AC13 grep assertion)*

### `sweep_orphan_tmp` default caller (AC7, behavioural)

- **AC7.** `kb.cli:cli` group invokes `sweep_orphan_tmp(<lock-and-manifest dirs>)` once at process boot, BEFORE any subcommand body runs. Sweeps the two atomic-write hot directories — `PROJECT_ROOT / ".data"` (manifest, feedback, verdicts) and `WIKI_DIR` (wiki page atomic writes). Sweep failures are swallowed by the helper itself (logged WARNING, returns int) and never block CLI startup; the per-call return is summed and discarded. *(behavioural test — AC14)*

### `run_augment` raw_dir derivation (AC8, behavioural)

- **AC8.** `src/kb/lint/augment.py::run_augment` derives `raw_dir` from `wiki_dir.parent / "raw"` when caller supplies a custom `wiki_dir` AND omits `raw_dir`. Mirrors the cycle-7 `effective_data_dir` derivation pattern at lines 569–580. Standard runs (no `wiki_dir` override OR explicit `raw_dir=`) fall through unchanged. *(behavioural test — AC15)*

### Test coverage (AC9–AC15)

- **AC9.** `tests/test_cycle13_frontmatter_migration.py::TestAugmentReadOnlySites` — two tests: (a) call `_collect_eligible_stubs` on a wiki containing a stub with frontmatter, mutate the stub's frontmatter on disk, call again, assert the SECOND call returns the updated metadata (proves non-stale cache via mtime); (b) call `_post_ingest_quality` against a freshly-augmented page with `source: ["raw/foo.md"]` and assert it returns `("pass", "")` proving `metadata.get("source")` works. *(behavioural)*
- **AC10.** `tests/test_cycle13_frontmatter_migration.py::TestSemanticMigration` — call `_group_by_shared_sources(wiki_dir)` against a wiki with two pages sharing `source: ["raw/foo.md"]` and assert both page IDs appear in the same group. *(behavioural)*
- **AC11.** `tests/test_cycle13_frontmatter_migration.py::TestGraphExportMigration` — build a mock graph with `path` attribute, call `export_mermaid` over it, assert the title from frontmatter appears in the Mermaid output (proves the title fallback branch loaded). *(behavioural)*
- **AC12.** `tests/test_cycle13_frontmatter_migration.py::TestReviewContextMigration` — call `pair_page_with_sources(page_id, project_root=tmp)` against a tmp wiki with a real frontmatter source, assert returned dict's `source_contents` is non-empty. *(behavioural)*
- **AC13.** `tests/test_cycle13_frontmatter_migration.py::TestWriteBackOutOfScope` — grep `src/kb/lint/augment.py` for the THREE remaining `frontmatter.load(str(` sites at functions `_run_augment` / `_mark_page_augmented` / `_record_attempt`, assert ALL THREE still present. Negative-pin so a future "fix everything" sweep doesn't silently break write-back YAML key order. *(scope)*
- **AC14.** `tests/test_cycle13_sweep_wiring.py::TestCliBootSweep` — `runner.invoke(cli, ["--version"])` triggers `sweep_orphan_tmp` against `.data` and `wiki` directories. Two assertions: (a) sweep is called at least twice with the expected paths via monkeypatch, (b) a stale `.tmp` file pre-seeded under `.data/` (mtime > 1 hour) is removed when invoking `--version` against a tmp project root. *(behavioural)*
- **AC15.** `tests/test_cycle13_augment_raw_dir.py::TestRawDirDerivation` — call `run_augment(wiki_dir=tmp/"wiki")` (no explicit `raw_dir`) and assert the resolved `raw_dir` inside `run_augment` equals `tmp/"raw"`. Uses `monkeypatch` on `RAW_DIR` to prove the FALLBACK is `wiki_dir.parent / "raw"`, NOT the global default. Second test: explicit `raw_dir=` override is honoured. Third test: standard run with neither override falls through to `RAW_DIR`. *(behavioural)*

### Documentation (AC16–AC17)

- **AC16.** `CHANGELOG.md [Unreleased]` gets a `Phase 4.5 -- Backlog-by-file cycle 13` section with Added / Changed / Stats. Quick Reference table at top gets a new row.
- **AC17.** `BACKLOG.md` deletes the three resolved cycle-13-target lines (MED frontmatter migration, LOW sweep_orphan_tmp wiring, LOW raw_dir derivation). Adds any new follow-up items (write-back site migration, run_augment resume re-wiring) only if surfaced during cycle 13.

## Blast radius

| Module | Change | Reversibility |
|---|---|---|
| `src/kb/lint/augment.py` | 5 sites: 2 migrate; 3 keep with annotation; 1 raw_dir derivation | Reversible — pure read-path migration + 4-line conditional |
| `src/kb/lint/semantic.py` | 1 site read-only migration | Reversible |
| `src/kb/graph/export.py` | 1 site read-only migration | Reversible |
| `src/kb/review/context.py` | 1 site read-only migration | Reversible |
| `src/kb/cli.py` | Add 1 sweep call in `cli` group body | Reversible — single-line if-failure-no-op |
| `tests/test_cycle13_*.py` | 3 new test modules | Additive |
| `CHANGELOG.md`, `BACKLOG.md`, `CLAUDE.md` | Cycle-13 entries + delete resolved | Reversible doc edits |

**Public API surface:** None. All migrations are internal to private helpers (`_collect_eligible_stubs`, `_post_ingest_quality`, `_group_by_shared_sources`, `export_mermaid`, `pair_page_with_sources`). The `run_augment(wiki_dir, raw_dir)` signature is unchanged — only the default-resolution rule when both kwargs are None+wiki_dir-overridden differs.

**MCP surface:** None. No new tools, no contract changes.

**Threat model handoff:** Step 2 must verify (a) `Path(path).stat()` cannot escape wiki_dir (graph/export.py loads path from a graph node attribute — possible attacker-controlled input?), (b) `sweep_orphan_tmp` wiring at CLI boot does not race with concurrent ingest writes (the helper only deletes files older than 1 hour, but boot runs while subcommands are launching), (c) the `wiki_dir.parent / "raw"` derivation in `run_augment` doesn't enable directory escape from a malicious wiki_dir.
