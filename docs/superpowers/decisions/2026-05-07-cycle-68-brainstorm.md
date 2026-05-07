# Cycle 68 — Step 3 Brainstorming

**Date:** 2026-05-07
**Pipeline step:** 3 (Brainstorming)
**Owner:** Opus 4.7 main (primary session — `superpowers:brainstorming` discipline)
**Inputs:** cycle-68 requirements (15 ACs), cycle-67 design.md (carry-over CONDITIONS), cycle-67 brainstorm + threat model

## Carry-over inheritance

Cycle-67 brainstorm + design eval already explored design alternatives for the three carry-over ACs (cycle-67 AC03 → cycle-68 AC01+AC02+AC11; cycle-67 AC07 → cycle-68 AC03+AC04+AC12; cycle-67 AC12 → cycle-68 AC05+AC06+AC13). The 19 binding CONDITIONS in cycle-67 design.md lock the chosen alternative for each. Cycle-68 brainstorm focuses ONLY on the NEW ACs (AC07-AC10 + their test pins AC14-AC15).

## AC07-AC08 — `build_graph` caller migration to `kb.graph.cache.get_graph`

### Alternatives

**A. Inline attribute-lookup migration (recommended).**
Each call site `from kb.graph.builder import build_graph; g = build_graph(wiki_dir, pages)` becomes `import kb.graph.cache; g = kb.graph.cache.get_graph(wiki_dir)`. Per cycle-18 L1 (snapshot-binding hazard) we MUST use attribute-lookup form, NOT `from kb.graph.cache import get_graph` (which is forbidden by cycle-67 AC02 AST guard).

Pros: minimal churn, preserves cycle-67 AC02 enforcement, no new module added.
Cons: 5 call sites each need an import + line edit.

**B. Wrapper helper in `kb.graph.cache`.**
Add `kb.graph.cache.build_or_get(wiki_dir, pages=None)` that internally branches: pages-supplying = bypass cache (existing semantic per CLAUDE.md "Pages-supplying callers BYPASS the cache"); pages=None = `get_graph(wiki_dir)`.

Pros: single migration target.
Cons: introduces a thin wrapper that just dispatches on `pages is None`; cycle-67 AC02 AST guard would also need updating; **YAGNI** per CLAUDE.md "Don't add features beyond what the task requires".

**C. Migrate only the pages-None call sites; leave the others alone.**
Per CLAUDE.md the cache only fires for pages-None lookups; pages-supplying callers already bypass. So a partial migration is technically equivalent.

Pros: smallest diff.
Cons: the BACKLOG entry explicitly enumerates 5 sites (`evolve/analyzer.py` ×3, `graph/export.py`, `mcp/browse.py`, `query/engine.py`); deferring some leaves the BACKLOG dirty for the next cycle. Also breaks the AST guard's symmetry expectation.

### Pick

**A** — inline attribute-lookup migration to `kb.graph.cache.get_graph(wiki_dir)` for all pages-None call sites; pages-supplying call sites stay on `build_graph` per the cycle-64 contract. Aligned with cycle-67 AC02 AST guard. Test pin AC14 will assert zero `ast.Call` to `build_graph(pages=None)` (or `build_graph(wiki)` without pages kw) in the 5 migrated files; pages-supplying calls explicitly allowed.

## AC09 — httpx pin tightening

### Alternatives

**A. Tight upper bound `>=0.28,<0.29` (recommended).**
Matches `lint/fetcher.py:51` runtime assertion exactly. Locks to httpx 0.28.x line.

Pros: prevents silent regression on a 0.29 release; aligns runtime + metadata.
Cons: requires manual bump on each httpx 0.28 → 0.29 release; security patches inside 0.28.x continue to flow.

**B. Loose upper bound `>=0.28,<1.0`.**
Allows future 0.29.x / 0.30.x within the 0.x range.

Pros: less manual upkeep.
Cons: defeats the purpose — 0.29 may break the runtime `lint/fetcher.py:51` assertion. The whole point of this AC is to PREVENT silent install of 0.27.x (per BACKLOG: "installs that satisfy the package metadata constraint but land on 0.27.x fail in production without any pip-install warning").

**C. Compatible-release `~=0.28.1`.**
Pip's compatible-release means `>=0.28.1,<0.29` — same upper bound as A but forces minimum to a specific patch.

Pros: idiomatic.
Cons: cycle-68 doesn't have a reason to demand 0.28.1+ specifically; httpx 0.28.0 is also acceptable per BACKLOG.

### Pick

**A** — `httpx>=0.28,<0.29`. Test pin AC15-1 will assert string contains both substrings.

Also consider: `lint/fetcher.py:51` currently `raise AssertionError` on version mismatch. Per BACKLOG suggested fix: "or make the `fetcher.py` guard a logged warning rather than a hard failure". **REJECT this softening**: the hard assertion catches the mismatch at module import time which is loud and obvious. Softening to a warning would let the divergence persist silently, which is exactly what tightening the pin is meant to prevent. Keep the hard assertion.

## AC10 — BACKLOG.md cleanup

### Alternatives

**A. Delete-in-place (recommended).**
Per BACKLOG.md FORMAT GUIDE comment block: "Resolve lifecycle: delete the item here → brief entry in CHANGELOG.md `[Unreleased]` → full detail in CHANGELOG-history.md." This is the documented project convention.

Pros: matches project convention; keeps BACKLOG focused on open work; cycle-67 changelog already has the brief entries; CHANGELOG-history.md already has full detail.

Cons: makes diff review noisy (~80-100 lines deleted across the file).

**B. Move to "Resolved Phases" section.**
Existing convention for fully-resolved phases (Phase 3.92, 3.93, etc.).

Pros: preserves attribution.
Cons: "Resolved Phases" is for entire phases, not individual items within a phase. Each item already has its CHANGELOG-history.md entry. Mixing item-level and phase-level resolutions in the same section breaks the existing pattern.

**C. Add a "verified shipped 2026-05-07" annotation, defer deletion.**
Half-measure.

Pros: low risk of accidental deletion.
Cons: BACKLOG fills with noise; future cycles have to skip past stale "verified" entries when planning. Defeats the purpose of the BACKLOG.

### Pick

**A** — delete-in-place. Per project convention. The diff is large but the cycle-67 audit comment block (lines 33-53 of BACKLOG.md) already documents WHY each entry is being deleted, providing a one-stop audit trail. AC15 regression test (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) locks the deletions against re-introduction.

For each deletion, the Step 17 doc-update subagent will:
1. Verify the entry is referenced in CHANGELOG.md `[Unreleased]` Quick Reference (cycle-67 changelog has the brief entries).
2. Verify the entry is referenced in CHANGELOG-history.md (cycle-67 history has the full detail).
3. Delete the BACKLOG entry.
4. If a section empties, collapse to "Resolved Phases" line per the format guide.

## AC14-AC15 — Test design (vacuous-test prevention)

The `feedback_test_behavior_over_signature` memory + cycle-11 L2 + cycle-16 L2 + cycle-23 L2 + cycle-24 L4 collectively forbid:
- `inspect.getsource(module).contains("X")` style assertions
- `re.findall(...)` over source files
- `Path.read_text().splitlines()` + string substring checks
- `if cond: assert ...` where `cond` is sometimes false in the happy path
- Tests that pass after `production_fn = lambda *a: True/False`

Cycle-68 test design must AVOID these. For AC14 graph cache caller migration, the AST guard MUST use `ast.parse` + `ast.walk` + `isinstance(node, ast.Call)` + `node.func.attr == "build_graph"` — NOT a string-based grep. For AC15 httpx pin and BACKLOG cleanup, parsing the file's actual structure (tomllib for pyproject.toml; markdown line iteration for BACKLOG.md) and asserting on parsed values, not raw substrings.

For the behavioural spy test in AC14:
```python
def test_get_graph_cache_hit_on_repeat_call(tmp_kb_env, monkeypatch):
    import kb.graph.cache, kb.graph.builder
    call_count = {"n": 0}
    real_build = kb.graph.builder.build_graph
    def spy(wiki_dir, pages=None):
        call_count["n"] += 1
        return real_build(wiki_dir, pages)
    monkeypatch.setattr(kb.graph.builder, "build_graph", spy)
    g1 = kb.graph.cache.get_graph(tmp_kb_env)
    g2 = kb.graph.cache.get_graph(tmp_kb_env)
    assert call_count["n"] == 1
    assert g1 is g2
```
Revert-test: replacing `get_graph` body with `return build_graph(wiki_dir)` (no caching) makes this test FAIL.

For the AST guard in AC14:
```python
def test_no_direct_build_graph_pages_none_calls_in_migrated_files():
    import ast, pathlib
    migrated = [
        "src/kb/evolve/analyzer.py",
        "src/kb/graph/export.py",
        "src/kb/mcp/browse.py",
        "src/kb/query/engine.py",
    ]
    for path in migrated:
        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name == "build_graph":
                    pages_kw = next(
                        (kw for kw in node.keywords if kw.arg == "pages"), None
                    )
                    pages_supplied = pages_kw is not None and not (
                        isinstance(pages_kw.value, ast.Constant)
                        and pages_kw.value.value is None
                    )
                    assert pages_supplied, (
                        f"{path}:{node.lineno} calls build_graph without pages — "
                        f"should use kb.graph.cache.get_graph instead"
                    )
```
Revert-test: re-introducing `build_graph(wiki_dir)` without `pages=...` in any migrated file makes this test FAIL with the file:line of the regression.

## Open questions for Step 04 design eval

1. **AC07/AC08 cache-invalidation responsibility.** When `evolve/analyzer.py` mutates the wiki, should it also call `kb.graph.cache.invalidate(wiki_dir)`? Per CLAUDE.md "Mutators (`ingest_source`, `refine_page`, `compile_wiki`) call `invalidate(wiki_dir)` post-success." Verify the 5 migrated callers are READ-ONLY (no graph mutation) — if any mutate, add invalidate call. Predict: all 5 are read-only. Step 5 to confirm.

2. **AC09 transitive httpx clamp.** Tightening `pyproject.toml` to `httpx>=0.28,<0.29` will resolve fine if all transitive consumers also accept httpx 0.28. Is any direct dependency (firecrawl-py, openai, anthropic, etc.) pinned to `httpx<0.28`? Step 5 to grep installed metadata.

3. **AC10 BACKLOG cleanup completeness.** The cycle-67 audit comment block lists ~14 stale entries. Are there OTHER entries that are also actually shipped but not mentioned in cycle-67's audit? Predict: cycle-67 audit was thorough; outliers go to cycle 69. Cycle-68 scope is ONLY the entries enumerated in the audit comment.

4. **AC14 AST guard kept-out callers.** The AST guard scopes to 5 migrated files. Should it ALSO assert that `kb.graph.cache.get_graph` is the ONLY function that calls `build_graph` outside those 5? Predict: cycle-67 AC02 already partially covers this for the cache module; cycle-68 explicit broader assertion would be over-reach. Step 5 to confirm scope.

## Step 04 design-eval dispatch outline

Cycle-68 Step 04 only needs to evaluate ACs 07-10 + 14-15 (NEW items). Carry-overs (01-06 + 11-13) inherit cycle-67's R1+R2 verdicts unchanged. Dispatch:
- R1 Opus subagent: focus on AC07-AC10 + AC14-AC15.
- R2 DeepSeek V4 Pro: same focus. Cross-family adversarial.
- Both R1 + R2 should explicitly note "carry-over ACs inherit cycle-67 design verbatim" so they don't waste tokens re-evaluating.
