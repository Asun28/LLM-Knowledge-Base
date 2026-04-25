# Cycle 33 — Step 16 Self-Review (Opus main)

**Cycle:** 33 (pre-Phase 5 backlog-by-file)
**PR:** #47 merged at 541427b
**Branch:** feat/backlog-by-file-cycle33 (deleted)
**Commits:** 6 feat+docs+fix on branch + 1 merge + 1 self-review (this) = 8 total
**Tests:** 2901 → 2912 passed (+21), 10 skipped (unchanged), 1 xfailed (Q8 sanitize.py UNC residual). Total collected: 2923.

## Per-step scorecard

| Step | Executed? | First-try? | Notes / surprise |
|------|-----------|------------|------------------|
| 1 — Requirements + ACs | yes | yes | 10 ACs drafted in primary; small-cycle context manageable |
| 2 — Threat model + CVE baseline | yes | yes | Opus subagent T1-T11; 4 existing alerts (all no-upstream-fix or click-conflict) |
| 3 — Brainstorming | yes | yes | 3 approaches per concern; chose minimal (A) for path-leak, (D) docstring+test-only for idempotency |
| 4 — Design eval R1 (parallel Opus + Codex) | yes | yes | R1 Opus PROCEED 4.9/5 in 140s; R1 Codex APPROVE-WITH-FIXES with 5 MAJOR + 6 MINOR in 444s — much slower than Opus |
| 5 — Design decision gate | yes | yes | 12 questions resolved with 7 AC amendments + 1 new AC (AC11 BACKLOG bookkeeping); 60.9KB output |
| 6 — Context7 verify | yes | yes | pytest `caplog.set_level(logger=name)` + `xfail(strict=True)` semantics confirmed |
| 7 — Implementation plan | yes | yes | Primary-session draft per cycle-14 L1 (operator held full context; 11 ACs borderline but justified) |
| 8 — Plan gate | yes | yes | Inline self-gate per cycle-21 L1; APPROVE; no PLAN-AMENDS-DESIGN |
| 9 — Implementation (TDD) | yes | **NO** | First-draft Windows assertions used single-backslash literals → vacuous against revert. Caught at revert-fail discipline check; expanded to 4-form leak assertion. **C33-L1.** |
| 10 — CI hard gate | yes | **NO** | 1 flaky failure (`test_concurrent_same_day_same_source_distinct_claims_both_persist`) on first run; gone on re-run. Likely a pre-existing flake on the contradictions test, not cycle-33 caused. |
| 11 — Security verify + PR-CVE diff | yes | yes | All 11 threats IMPLEMENTED or out-of-scope; same-class peer scan clean (only 2 `Error[partial]:` emitters, both fixed); zero PR-introduced CVEs |
| 11.5 — Existing-CVE patch | skipped | n/a | All 4 alerts blocked (no upstream fix or click<8.2 transitive conflict); deferred per existing BACKLOG mitigation |
| 12 — Doc update | yes | **NO** | R3 caught CHANGELOG-history.md drift after R1+R2 fix commits added 2 tests (+19 → +21 not refreshed). Cycle-23 L4 reminder fired. |
| 13 — Branch finalise + PR | yes | yes | PR #47 opened cleanly with full review trail in body |
| 14 — PR review (R1 + R2 + R3) | yes | **NO** | R1 Codex caught A1 MAJOR (UnboundLocalError on mkdir-before-target). R2 Codex caught same-class C33-R2-01 MAJOR (lazy-import-before-target). R3 Sonnet caught CHANGELOG-history doc drift. **3 fix rounds.** Two genuine MAJOR code findings + 1 doc drift. **C33-L2** + **C33-L3.** |
| 15 — Merge + cleanup + late-arrival CVE | yes | yes | Clean merge to main; zero late-arrival CVEs (3 existing alerts unchanged) |

## Surprises requiring skill patches

### C33-L1 — Path-leak assertions on Windows must check OSError-EMITTED form

**Surprise root cause:** Python source `"D:\\Projects\\test\\fake.md"` is a 24-char string `D:\Projects\test\fake.md` with single backslashes. `OSError(13, "x", filename).__str__()` formats `filename` with Python's repr-style escaping, producing a 32-char string with DOUBLED backslashes. Single-backslash assertions look right in source but never appear in real OSError output regardless of redaction state — vacuous.

**Caught by:** my own revert-fail discipline check (cycle-24 L4) at Step 9, before R1 review. Expected ≥4 failures; got 3. Investigation found the assertion mismatch.

**Skill patch:** define `_LEAKY_WIN_INPUT` (input form) AND `_LEAKY_WIN_EMITTED` (doubled-backslash repr-form) AND `_LEAKY_WIN_FWD` (slash-normalised) AND `_LEAKY_WIN_BASENAME_DIR` (distinguishing token); assert all four absent. REPL-probe `print(repr(str(OSError(...))))` to confirm what to assert.

**Refines** cycle-24 L4 (revert-tolerant assertions) with the Python-string-escaping subclass.

### C33-L2 — `except` handler references variable assigned ONLY in try body

**Surprise root cause:** R1 Codex caught `_save_synthesis` had `except OSError as exc: _sanitize_error_str(exc, target)` referencing `target`, which was assigned inside the try body AFTER `synthesis_dir.mkdir(...)`. If mkdir raised OSError (PermissionError, disk-full, etc.), `target` was unbound and the handler raised UnboundLocalError — bypassing the entire path-redaction contract. R1 fix moved `target` BEFORE mkdir. R2 Codex then caught a same-class extension: the lazy `import frontmatter` inside the try body could ALSO raise OSError before `target` was bound. R2 fix moved `target` OUTSIDE the try block entirely.

**Two-round catch is the lesson:** R1 fixed the obvious site (mkdir); R2 found a parallel site one line earlier (lazy import). The general class is "any OSError-raising line BEFORE the variable assignment leaves the except handler with an unbound reference."

**Skill patch:** any `except <Exc> as e:` handler that references a variable should be audited — walk the try body, find the line that assigns the variable, verify EVERY preceding line cannot raise the caught exception class. Lazy imports CAN raise OSError. `mkdir`, `open`, `read_text`, `Path.exists`, `Path.resolve` all raise OSError. ONLY OSError-safe operations: pure object construction (`Path / str`), arithmetic, dict lookups on built dicts. Move all handler-referenced names ABOVE unsafe operations OR initialise sentinels at function top.

**Generalises** cycle-22 L5 (design-gate CONDITIONS load-bearing) — this is a load-bearing CONDITION the design gate doesn't typically write but R1+R2 catches.

### C33-L3 — `sys.modules.pop` without `monkeypatch.delitem` poisons sibling tests

**Surprise root cause:** R2 fix added `test_lazy_import_oserror_does_not_raise_unboundlocalerror` which needed to force-re-import `frontmatter` to retrigger the patched-to-raise path. First draft used bare `sys.modules.pop("frontmatter", None)` — direct mutation, no teardown. After my test ran, frontmatter was unloaded. The next test that did `import frontmatter as fm_lib; fm_lib.load = mock` (e.g. `test_v0915_task06.py::test_does_not_swallow_keyboard_interrupt`) got a fresh module instance; the mock was applied to a different object than the production code imported. Sibling test FAILED.

**Caught by:** post-fix full-suite run (cycle-22 L3 — full suite is the only authoritative gate, isolation passes don't prove anything).

**Skill patch:** always use `monkeypatch.delitem(sys.modules, "<modname>", raising=False)` instead of bare `sys.modules.pop` / `del sys.modules[...]`. Pytest's monkeypatch saves the original value before deletion and restores on teardown. Same rule for any process-global mapping mutation.

**Generalises** cycle-19 L2 (reload-leak hazard via sibling-module `importlib.reload`) — both are "test mutates process state, fails to undo on teardown, sibling test breaks".

## Step-12 doc drift retrospective

R3 caught CHANGELOG-history.md line 14 stale at "+19 passed" after R1+R2 fix commits added 2 more passing tests (mkdir-failure + lazy-import-failure regressions). CHANGELOG.md was correctly updated; CHANGELOG-history was not.

This is exactly cycle-23 L4 ("count-sensitive doc fields drift across R1/R2/R3 fix commits"). The rule already exists; the gap was that I didn't run the count cross-check after each fix commit cascade. Future cycles must run `python -m pytest --collect-only | tail -1` AFTER every R1/R2/R3 commit and sync ALL count-bearing doc files. No new lesson; cycle-23 L4 stays canonical.

## What worked first-try

- Steps 1, 2, 3, 4, 5, 6, 7, 8, 11, 13, 15 — clean execution, no surprises.
- Cycle-14 L1 primary-session plan draft: 11 ACs handled efficiently; no Codex dispatch needed at Step 7.
- Cycle-21 L1 inline plan-gate: zero PLAN-AMENDS-DESIGN; no Codex dispatch needed at Step 8.
- Cycle-24 L5 budget for R1 dispatches (270s wake then poll): R1 Opus came back at 140s; R1 Codex came back at 444s — handled cleanly with one wakeup.
- Cycle-17 L4 R3 trigger: 12 design-gate questions ≥10 fired R3 correctly; R3 caught 1 doc drift R1+R2 missed.
- Cycle-22 L1 (`pip-audit --installed` for baseline + project-relative `.data/cycle-33/` paths): no Step-2 capture issues on Windows.

## Commit graph

```
af20499 docs(cycle 33): R3 audit-doc drift fix — CHANGELOG-history test count
ba2533c fix(cycle 33): R2 review — close lazy-import OSError UnboundLocalError (C33-R2-01)
363c4ac fix(cycle 33): R1 review — close UnboundLocalError on _save_synthesis mkdir failure (A1) + Sonnet defense-in-depth (MINOR)
0df1ab7 docs(cycle 33): CHANGELOG + CHANGELOG-history + BACKLOG + CLAUDE.md sync (AC9-AC11)
f0a76ab docs(cycle 33): pin ingest index-file dedup contract via spy regression (AC6-AC8)
d68b6a4 fix(cycle 33): redact write_err in MCP Error[partial] emitters (AC1-AC5)
541427b Merge pull request #47 from Asun28/feat/backlog-by-file-cycle33
```

## Skill-patch landing locations

1. `references/cycle-lessons.md` — TOP: full L1/L2/L3 entries under `## Cycle 33 skill patches (2026-04-25)` ✓ landed.
2. `SKILL.md` — one-liner index entries:
   - "Test authoring" section: `C33-L1 — Windows path-leak tests assert FOUR forms ...` ✓ landed.
   - "Implementation gotchas" section: `C33-L2 — except body references ... assigned BEFORE try ...` ✓ landed.
   - "Implementation gotchas" section: `C33-L3 — sys.modules.pop / del without monkeypatch.delitem ...` ✓ landed.

No obsoletion of prior rules.

## Cycle terminate

Cycle 33 complete. Branch deleted. `main` synced. No auto-start scheduled.
