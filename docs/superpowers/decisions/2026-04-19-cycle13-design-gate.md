# Cycle 13 — Design Decision Gate (Step 5)

**Date:** 2026-04-19
**Gate:** Opus 4.7 — feature-dev Step 5
**Inputs:** requirements (AC1-AC17), threat model (T1-T7), brainstorm (Approach A; Q1-Q7 open). R1 Opus eval (REVISE-WITH-AMENDMENTS, 5 items). R2 Codex eval (REVISE-WITH-FIXES, 7 items). All open Qs (Q1-Q14) consolidated.

## VERDICT

**PROCEED TO STEP 7 (PLAN)** — once every CONDITION below is honoured.

## DECISIONS (summary table)

| Q | Topic | Decision | Confidence |
|---|---|---|---|
| Q1 | CLI sweep targets | Both `.data` + `WIKI_DIR` | HIGH |
| Q2 | CLI sweep error handling | Trust helper; no wrapping | HIGH |
| Q3 | AC13 pin mechanism | Monkeypatch spy on `kb.lint.augment.frontmatter.load` | HIGH |
| Q4 | `KB_RAW_ROOT` env var | Do NOT introduce | HIGH |
| Q5 | graph/export path migration | `Path(path)` wrap INSIDE broad try | HIGH |
| Q6 | Write-back pin scope | ALL THREE sites (914, 1026, 1053) | HIGH |
| Q7 | AC14 test isolation | Spy + real pre-aged `.tmp` in tmp_kb_env | HIGH |
| Q8 | `--version` triggers sweep | NO — AC30 wins | HIGH |
| Q9 | AC15 explicit-RAW_DIR case | YES — 4th sub-test | MEDIUM |
| Q10 | `sweep_orphan_tmp` import | Module-level in `kb/cli.py` AFTER AC30 guard | HIGH |
| Q11 | `_post_ingest_quality` migration | KEEP uncached — demote AC2 to scope/comment | HIGH |
| Q12 | `run_augment` wiki_dir cmp | Lexical (cycle-7 pattern), no `.resolve()` | HIGH |
| Q13 | Sweep dedup | `{Path.resolve()}` set | MEDIUM |
| Q14 | AC7 wording | Principled post-AC30/Click-eager framing | HIGH |

## CONDITIONS (must be true before Step 7 starts)

1. **AC7 amended** per Q14: sweep runs in the `cli` group body AFTER AC30 guard, on deduped set of resolved paths `{PROJECT_ROOT/".data", WIKI_DIR}`.
2. **AC2 demoted** per Q11: `_post_ingest_quality` (augment.py:1082) STAYS on uncached `frontmatter.load(str(page_path))`. AC2 becomes a scope/comment AC. Behavioural sub-test AC9(b) dropped.
3. **AC13 mechanism** per Q3+Q6: monkeypatch `kb.lint.augment.frontmatter.load` with a spy returning real `frontmatter.Post`. Drive `run_augment` so all 3 write-back sites execute. Assert spy `call_args_list` covers all 3 distinct stub/augmented file paths. NO `inspect.getsource`, NO `Path.read_text + splitlines`.
4. **AC4 implementation** per Q5: at `src/kb/graph/export.py:131-134`, `Path(path)` wrap goes INSIDE the existing `try/except Exception`; do NOT narrow the broad `except`.
5. **AC14 invocation** per R1 #3 + Q7: replace `["--version"]` with `["lint", "--help"]` (real subcommand). Two sub-tests: (i) spy assertion; (ii) real pre-aged `.tmp` removed under `<tmp>/.data/` and `<tmp>/wiki/`.
6. **AC15 fourth sub-test** per Q9: explicit `raw_dir=RAW_DIR` pass honoured (proves `raw_dir is not None` branch).
7. **Exception widening** per R2 #1-2: `_collect_eligible_stubs` (augment.py:73) widens to `(OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError)`; `pair_page_with_sources` (review/context.py:57) widens from `yaml.YAMLError`-only to the same 5-class tuple.
8. **`sweep_orphan_tmp` import** per Q10 + R2 #4: `from kb.utils.io import sweep_orphan_tmp  # noqa: E402` placed AFTER AC30 guard (line 19) and BEFORE `@click.group()`.
9. **Sweep dedup** per Q13 + R2 #4: `sweep_targets = sorted({Path(d).resolve() for d in (PROJECT_ROOT / ".data", WIKI_DIR)})`.
10. **`run_augment` derivation** per Q12: mirror `effective_data_dir` lines 574-580 exactly — LEXICAL `wiki_dir != WIKI_DIR`, no `.resolve()`. Docstring note about lexical-comparison choice.
11. **Signature drift check** (user-memory `feedback_signature_drift_verify`): grep callers of `run_augment`, `_collect_eligible_stubs`, `_post_ingest_quality`, `_group_by_shared_sources`, `export_mermaid`, `pair_page_with_sources` — confirm no implicit-default callers break.
12. **Ruff ordering** (user-memory `feedback_ruff_edit_ordering`): run `ruff format` AFTER all Edits per pass.
13. **BACKLOG.md delete-on-resolve**: cycle-13 fixes DELETE the three tracked items. Add a new LOW entry for write-back migration deferral.
14. **No source-scan tests** (cycle-11 L1, cycle-12 inspect-source): all pins use live monkeypatch spies on the production symbol.

## FINAL DECIDED DESIGN

### File 1: `src/kb/lint/augment.py`

**AC1 (behavioural).** At `_collect_eligible_stubs` (line 45, modifying lines 71-75):
- Replace `post = frontmatter.load(str(page_path))` (line 72) with `metadata, body = load_page_frontmatter(page_path)`.
- Replace `post.metadata.get(...)`/`post.metadata` with `metadata.get(...)`/`metadata`; replace `post.content` with `body`.
- Widen except on line 73 from `(OSError, ValueError, UnicodeDecodeError)` to `(OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError)`.
- Add `from kb.utils.pages import load_page_frontmatter` (or extend existing import).

**AC2 (scope/comment — DEMOTED from behavioural).** At `_post_ingest_quality` (line 1062, unchanged call at 1082): keep `post = frontmatter.load(str(page_path))`. Add inline comment ABOVE line 1082:
```python
# Cycle 13 AC2 (scope): Intentionally uses uncached frontmatter.load. This
# read may immediately follow same-process writes from _mark_page_augmented
# / _record_verdict_gap_callout. On FAT32 / OneDrive / SMB (coarse mtime
# resolution), the cached helper could return stale metadata. Design gate Q11.
```

**AC6 (scope).** At lines 914, 1026, 1053 — keep `frontmatter.load(str(path))` + `frontmatter.dumps(post)` + `atomic_text_write(...)`. Add a `# Cycle-13 AC6: write-back; DO NOT migrate to load_page_frontmatter — see BACKLOG cycle-14-target.` comment above each of the three sites.

**AC8 (behavioural).** At lines 566-567, restructure as:
```python
wiki_dir = wiki_dir or WIKI_DIR
# Cycle 13 AC8: when caller supplies a custom wiki_dir but omits raw_dir,
# derive wiki_dir.parent / "raw" so augment runs stay project-isolated.
# Lexical comparison mirrors effective_data_dir (lines 574-580); do NOT
# .resolve() — users with symlinked wiki mounts rely on path identity.
if raw_dir is None and wiki_dir != WIKI_DIR:
    raw_dir = wiki_dir.parent / "raw"
else:
    raw_dir = raw_dir or RAW_DIR
```

### File 2: `src/kb/lint/semantic.py`

**AC3 (behavioural).** At `_group_by_shared_sources` line 121-129 (the `else` branch handling `page_paths`):
- Replace `post = frontmatter.load(str(page_path))` with `metadata, _body = load_page_frontmatter(page_path)`.
- Replace `post.metadata.get(...)` with `metadata.get(...)`.
- Keep the except on line 127 unchanged (already 5-class tuple).
- Add `load_page_frontmatter` to the `from kb.utils.pages import ...` line.
- Do NOT touch the pre-loaded-bundle branch at line 106-117.

### File 3: `src/kb/graph/export.py`

**AC4 (behavioural).** At lines 129-136 — keep broad `except Exception`; move `Path(path)` wrap INSIDE try:
```python
for node in nodes_to_include:
    path = graph.nodes[node].get("path")
    try:
        metadata, _body = load_page_frontmatter(Path(path))
    except Exception as exc:  # pragma: no cover — any corrupt page is non-fatal
        logger.debug("Graph export title load failed for %s: %s", node, exc)
        continue
    titles[node] = str(metadata.get("title", Path(path).stem))
```
Add `load_page_frontmatter` to `from kb.utils.pages import ...` line.

### File 4: `src/kb/review/context.py`

**AC5 (behavioural).** At `pair_page_with_sources` lines 55-58:
- Replace `post = frontmatter.load(str(page_path))` with `metadata, _body = load_page_frontmatter(page_path)`.
- Widen except from `except yaml.YAMLError as e:` to `except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError) as e:`.
- Replace `post.metadata.get("source")` with `metadata.get("source")`.
- Add `load_page_frontmatter` to the `from kb.utils.pages import ...` line.

### File 5: `src/kb/cli.py`

**AC7 (behavioural, amended per Q14).**
- AFTER line 19 (AC30 guard `sys.exit(0)`), with the `# noqa: E402` block, add:
```python
from kb.utils.io import sweep_orphan_tmp  # noqa: E402
```
- Inside `cli(ctx, verbose)` (line 93-98) at the top of the body, BEFORE `_setup_logging()`:
```python
    # Cycle 13 AC7: sweep orphan atomic-write .tmp siblings from hot dirs.
    # Runs once per CLI invocation, after the AC30 --version short-circuit
    # and after Click's eager --version/--help callbacks. Helper is no-op
    # on missing dirs, swallows all errors at WARNING, never raises.
    from kb.config import PROJECT_ROOT, WIKI_DIR

    sweep_targets = sorted({
        Path(d).resolve()
        for d in (PROJECT_ROOT / ".data", WIKI_DIR)
    })
    for target in sweep_targets:
        sweep_orphan_tmp(target)
```

### File 6: `tests/test_cycle13_frontmatter_migration.py` (NEW)

**AC9 (behavioural, amended per Q11).** `TestAugmentReadOnlySites`:
- Test (a) `test_collect_eligible_stubs_sees_fresh_mtime`: create a stub page, call `_collect_eligible_stubs`, mutate frontmatter on disk, call `load_page_frontmatter.cache_clear()` (defensive against coarse mtime), call again, assert the eligibility result reflects the updated metadata.
- Test (b) DROPPED.

**AC10 (behavioural).** `TestSemanticMigration`: create two wiki pages both with `source: ["raw/foo.md"]`, call `_group_by_shared_sources(wiki_dir)`, assert both page IDs appear in the same returned group.

**AC11 (behavioural).** `TestGraphExportMigration`: build a `nx.DiGraph` with two nodes whose `path` attribute is the string path to a real wiki page, call `export_mermaid(graph)`, assert the Mermaid output contains the page's `title` value from frontmatter.

**AC12 (behavioural).** `TestReviewContextMigration`: create a wiki page with `source: ["raw/articles/foo.md"]` and a matching raw file, call `pair_page_with_sources("entities/foo", project_root=tmp)`, assert the returned dict's `source_contents` list has length 1 with non-empty body.

**AC13 (scope/behavioural via spy per Q3+Q6).** `TestWriteBackOutOfScope`: monkeypatch `kb.lint.augment.frontmatter.load` with a spy that records `(args, kwargs)` AND returns the real `frontmatter.load(*args)` result. Drive each of three paths (via `run_augment` exercising the augment loop end-to-end with stubbed fetches/LLMs). Assert the spy was called with each of three distinct page paths covering `_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`.

### File 7: `tests/test_cycle13_sweep_wiring.py` (NEW)

**AC14 (behavioural, amended per R1 #3 + Q7).** `TestCliBootSweep`:
- Test (i) `test_sweep_called_with_both_dirs`: use `tmp_kb_env`, monkeypatch `kb.cli.sweep_orphan_tmp` with spy, `runner.invoke(cli, ["lint", "--help"])`, assert spy received Path args matching both `tmp/".data"` and `tmp/"wiki"` (resolved).
- Test (ii) `test_stale_tmp_actually_removed`: use `tmp_kb_env`, pre-create `<tmp>/.data/old.tmp` + `<tmp>/wiki/old.tmp` with `os.utime(..., (now-7200, now-7200))`, also create a `fresh.tmp`, invoke `["lint", "--help"]`, assert old removed and fresh remains.

### File 8: `tests/test_cycle13_augment_raw_dir.py` (NEW)

**AC15 (behavioural, 4 sub-tests per Q9).** `TestRawDirDerivation`:
- Sub-test 1 `test_wiki_override_derives_raw_sibling`: monkeypatch a probe (e.g., `kb.lint.augment.AugmentFetcher` constructor or `kb.lint.augment.Manifest` constructor or wrap the body) to capture the resolved `raw_dir`. Call `run_augment(wiki_dir=tmp/"wiki")`. Assert captured == `tmp/"raw"`.
- Sub-test 2 `test_explicit_raw_dir_honoured`: call `run_augment(wiki_dir=tmp/"wiki", raw_dir=tmp/"custom-raw")`. Assert captured == `tmp/"custom-raw"`.
- Sub-test 3 `test_standard_run_uses_global_raw_dir`: monkeypatch `kb.lint.augment.RAW_DIR` to `tmp/"raw-global"`. Call `run_augment()` no kwargs. Assert captured == `tmp/"raw-global"`.
- Sub-test 4 (Q9) `test_explicit_raw_equals_global_honoured`: call `run_augment(wiki_dir=tmp/"wiki", raw_dir=tmp/"raw-global")` (where raw_dir literally equals patched RAW_DIR). Assert captured == `tmp/"raw-global"`.

### File 9: `CHANGELOG.md` — AC16

Add `## Phase 4.5 -- Backlog-by-file cycle 13 (2026-04-19)` block under `[Unreleased]` with Added / Changed / Stats. Quick Reference table gains a new row.

### File 10: `BACKLOG.md` — AC17

- DELETE: the three cycle-13-target lines (MED frontmatter migration, LOW sweep_orphan_tmp wiring, LOW raw_dir derivation).
- ADD (new LOW): `src/kb/lint/augment.py:914, 1026, 1053 — write-back frontmatter migration deferred. Requires a YAML-key-ordering-preserving _save_page_frontmatter wrapper (cycle-7 R1 Codex M3 lesson). Pinned by tests/test_cycle13_frontmatter_migration.py::TestWriteBackOutOfScope.`
