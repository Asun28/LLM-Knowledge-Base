# Cycle 52 — Implementation Plan

**Branch:** `cycle-52-batch` (worktree at `D:/Projects/llm-wiki-flywheel-c52`)
**4 commits + 1 doc-sync commit + 0..N PR-review-fix commits.**
**No src/ edits.**

## TASK 1 — Fold AC1 (`test_cycle19_prune_base_consistency_anchor.py`)

**Files:**
- DELETE `tests/test_cycle19_prune_base_consistency_anchor.py`
- EDIT `tests/test_compile.py` (add 2 bare functions in `# ── Compiler tests ─` section after `test_compile_loop_does_not_double_write_manifest` at line ~366)

**Change:**
1. Read `tests/test_cycle19_prune_base_consistency_anchor.py` body (already in context).
2. Add 2 bare functions verbatim into `tests/test_compile.py` after the existing compiler tests block, before the `# ── Linker tests ─` section at line 206. Concrete insertion point: between line 196 and 206 (find `def test_compile_loop_does_not_double_write_manifest` end, insert after it).
3. Add `import inspect` at top (already imported in some receiver tests; check first).
4. Delete the source file.

**Test (revert-verify per C40-L3):**
- BEFORE deletion of source: insert `assert False` into `test_prune_base_uses_canonical_rel_path_at_both_sites` body in test_compile.py, run `pytest tests/test_compile.py::test_prune_base_uses_canonical_rel_path_at_both_sites -v -x`, confirm FAIL.
- Restore.
- Run `pytest tests/test_compile.py::test_prune_base_uses_canonical_rel_path_at_both_sites tests/test_compile.py::test_manifest_key_for_alias_is_canonical_rel_path_at_module_scope -v` (ISOLATION pytest per C51-L1).
- Run `pytest tests/test_compile.py -q` (full receiver file).

**Criteria:** AC1, AC5 (commit message uses `confirmed`), AC8 (isolation), AC9 (branch).

**Commit message file (`.data/cycle-52/commit-fold-1.txt`):**
```
test(cycle 52): fold cycle-19 prune-base consistency anchor into test_compile.py

Cycle 52 hygiene fold #1 of 4. Migrates the cycle-19 AC14 anchor (cycle-15 L2
DROP-with-test-anchor pattern) into the canonical compiler test file under the
existing `# Compiler tests` section.

- test_prune_base_uses_canonical_rel_path_at_both_sites — moved verbatim
  (inspect.getsource lint test for cycle-17 AC1 prune-base regression)
- test_manifest_key_for_alias_is_canonical_rel_path_at_module_scope — moved
  verbatim (manifest_key_for IDENTITY alias check)

Per C40-L3, isolation revert-verify confirmed (assert False -> FAIL on each
moved function, restored).

File count 229 -> 228 (-1). Test count preserved at 3025.
```

## TASK 2 — Fold AC2 (`test_cycle19_lint_redundant_patches.py`)

**Files:**
- DELETE `tests/test_cycle19_lint_redundant_patches.py`
- EDIT `tests/test_lint.py` (add new section at END with helpers + 1 test; UPDATE the self-exclusion guard per Q1 decision (b))

**Change:**
1. Append at END of `tests/test_lint.py` (after line 406):
   ```
   # ── Test-suite lint guards (cycle 52 fold) ─
   # Source: tests/test_cycle19_lint_redundant_patches.py (deleted in same commit).

   import ast as _ast  # local alias to avoid collision with possible existing 'ast' import

   _TESTS_DIR = Path(__file__).parent


   def _method_uses_tmp_kb_env(node: _ast.FunctionDef) -> bool:
       return any(arg.arg == "tmp_kb_env" for arg in node.args.args)


   def _method_body_text(source: str, node: _ast.FunctionDef) -> str:
       lines = source.splitlines()
       return "\n".join(lines[node.lineno - 1 : node.end_lineno])


   def test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method() -> None:
       """A test method that takes tmp_kb_env MUST NOT also patch kb.compile.compiler.HASH_MANIFEST. (cycle 19 AC18)"""
       offenders: list[str] = []
       _self = Path(__file__).resolve()
       for py in _TESTS_DIR.glob("test_*.py"):
           if py.resolve() == _self:
               continue
           source = py.read_text(encoding="utf-8")
           try:
               tree = _ast.parse(source)
           except SyntaxError:
               continue
           for node in _ast.walk(tree):
               if not isinstance(node, _ast.FunctionDef):
                   continue
               if not node.name.startswith("test_"):
                   continue
               if not _method_uses_tmp_kb_env(node):
                   continue
               body = _method_body_text(source, node)
               if "kb.compile.compiler.HASH_MANIFEST" in body and "monkeypatch.setattr" in body:
                   offenders.append(f"{py.name}::{node.name}")
       assert not offenders, (
           "Test methods using tmp_kb_env must not also monkeypatch "
           "kb.compile.compiler.HASH_MANIFEST; the fixture (cycle-18 D6) already "
           f"redirects it. Offenders: {offenders}"
       )
   ```
2. Verify `Path` is already imported in test_lint.py top (it is — `pathlib.Path` is used in existing tests).
3. Verify `ast` is NOT already imported. If it IS imported, the `_ast` alias avoids redefining; if it is NOT imported, the local `import ast as _ast` is the only access.
4. Delete the source file.

**Per Q1 (b):** the `if py.resolve() == _self: continue` guard self-references the file holding the guard, so future renames don't break self-exclusion. Robust per the design gate.

**Test (revert-verify per C40-L3):**
- Insert `assert False` after the for-loop in test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method (just before the `assert not offenders`).
- Run `pytest tests/test_lint.py::test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method -v -x`, confirm FAIL.
- Restore.
- Run `pytest tests/test_lint.py::test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method -v` (ISOLATION).
- Run `pytest tests/test_lint.py -q` (full receiver).

**Criteria:** AC2, AC5, AC8, AC9. Closes Q1 design-gate decision.

**Commit message file (`.data/cycle-52/commit-fold-2.txt`):**
```
test(cycle 52): fold cycle-19 lint-redundant-patches guard into test_lint.py

Cycle 52 hygiene fold #2 of 4. Migrates the cycle-19 AC18 forward-looking lint
guard into test_lint.py under a new section `# Test-suite lint guards`.

Per cycle-52 design-gate Q1 decision (b), the self-exclusion guard is updated
from a hardcoded source-filename string to `Path(__file__).resolve()` self-
reference so future receiver renames do not break self-exclusion.

Per C40-L3, isolation revert-verify confirmed (assert False -> FAIL on the
moved function, restored).

File count 228 -> 227 (-1). Test count preserved at 3025.
```

## TASK 3 — Fold AC3 (`test_cycle15_load_all_pages_fields.py`)

**Files:**
- DELETE `tests/test_cycle15_load_all_pages_fields.py`
- EDIT `tests/test_utils.py` (add 6 bare functions + 1 helper in existing `# ── load_all_pages ─` section after line 180)

**Change:**
1. After `tests/test_utils.py` line 180 (end of `test_load_all_pages_normalizes_sources`), insert:
   ```
   # Cycle 52 fold — cycle-15 AC32 contract regression for load_all_pages
   # additive frontmatter keys (status / belief_state / authored_by).
   # Source: tests/test_cycle15_load_all_pages_fields.py (deleted in same commit).


   def _write_concept_page(wiki_dir: Path, pid: str, extra_fm: str = "") -> Path:
       path = wiki_dir / "concepts" / f"{pid}.md"
       path.parent.mkdir(parents=True, exist_ok=True)
       path.write_text(
           f"""---
   title: {pid}
   source:
     - raw/articles/{pid}.md
   created: 2026-04-20
   updated: 2026-04-20
   type: concept
   confidence: stated
   {extra_fm}---
   Body.
   """,
           encoding="utf-8",
       )
       return path


   def test_load_all_pages_emits_authored_by_when_present(tmp_path):
       _write_concept_page(tmp_path, "alpha", extra_fm="authored_by: human\n")
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert len(pages) == 1
       assert pages[0]["authored_by"] == "human"


   def test_load_all_pages_emits_belief_state_when_present(tmp_path):
       _write_concept_page(tmp_path, "beta", extra_fm="belief_state: confirmed\n")
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert pages[0]["belief_state"] == "confirmed"


   def test_load_all_pages_emits_status_when_present(tmp_path):
       """Cycle-14 AC23 regression — status key still surfaces."""
       _write_concept_page(tmp_path, "gamma", extra_fm="status: mature\n")
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert pages[0]["status"] == "mature"


   def test_load_all_pages_emits_all_three_keys_when_present(tmp_path):
       """Cycle-14 L3 atomicity — all three vocabulary keys ship together."""
       _write_concept_page(
           tmp_path,
           "complete",
           extra_fm="authored_by: hybrid\nbelief_state: uncertain\nstatus: developing\n",
       )
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert pages[0]["authored_by"] == "hybrid"
       assert pages[0]["belief_state"] == "uncertain"
       assert pages[0]["status"] == "developing"


   def test_load_all_pages_defaults_empty_string_when_absent(tmp_path):
       """AC32 — missing vocabulary keys default to empty string (additive shape)."""
       _write_concept_page(tmp_path, "minimal")
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert pages[0]["authored_by"] == ""
       assert pages[0]["belief_state"] == ""
       assert pages[0]["status"] == ""


   def test_load_all_pages_keys_are_strings(tmp_path):
       """AC32 — additive keys are always str type (no None/list/dict leakage)."""
       _write_concept_page(tmp_path, "types", extra_fm="authored_by: human\n")
       from kb.utils.pages import load_all_pages

       pages = load_all_pages(tmp_path)
       assert isinstance(pages[0]["authored_by"], str)
       assert isinstance(pages[0]["belief_state"], str)
       assert isinstance(pages[0]["status"], str)
   ```
2. Per Q4: helper renamed `_write_page` → `_write_concept_page`.
3. The function-local `from kb.utils.pages import load_all_pages` matches the existing pattern in test_utils.py (lines 125, 133, 165 — load_all_pages is consistently function-local-imported in test_utils.py).
4. `Path` is imported at line 4 of test_utils.py — confirmed.
5. Delete source file.

**Test (revert-verify per C40-L3):**
- Insert `assert False` into one of the moved tests (e.g., `test_load_all_pages_emits_authored_by_when_present`).
- Run `pytest tests/test_utils.py::test_load_all_pages_emits_authored_by_when_present -v -x`, confirm FAIL.
- Restore.
- Run `pytest tests/test_utils.py::test_load_all_pages_emits_authored_by_when_present tests/test_utils.py::test_load_all_pages_emits_belief_state_when_present tests/test_utils.py::test_load_all_pages_emits_status_when_present tests/test_utils.py::test_load_all_pages_emits_all_three_keys_when_present tests/test_utils.py::test_load_all_pages_defaults_empty_string_when_absent tests/test_utils.py::test_load_all_pages_keys_are_strings -v` (ISOLATION).
- Run `pytest tests/test_utils.py -q` (full receiver).

**Criteria:** AC3, AC5, AC8, AC9.

**Commit message file (`.data/cycle-52/commit-fold-3.txt`):**
```
test(cycle 52): fold cycle-15 load_all_pages additive-fields contract into test_utils.py

Cycle 52 hygiene fold #3 of 4. Migrates the cycle-15 AC32 contract regression
for load_all_pages additive frontmatter keys (status / belief_state /
authored_by per cycle-14 AC23 + AC1) into the existing `# load_all_pages`
section in test_utils.py.

Per cycle-52 design-gate Q4, the helper `_write_page` is renamed to
`_write_concept_page` for hygiene-class disambiguation per the cycle-50
helper-name uniqueness rule.

Per C40-L3, isolation revert-verify confirmed (assert False -> FAIL on a
moved function, restored).

File count 227 -> 226 (-1). Test count preserved at 3025.
```

## TASK 4 — Fold AC4 (`test_cycle15_query_tier1_wiring.py`)

**Files:**
- DELETE `tests/test_cycle15_query_tier1_wiring.py`
- EDIT `tests/test_query.py` (append new section at END after line 349 with 1 helper + 2 tests)

**Change:**
1. Append at END of `tests/test_query.py` (after line 349):
   ```


   # ── Tier-1 budget wiring (cycle 52 fold) ─
   # Cycle 15 AC2/AC21 — `_build_query_context` uses tier1_budget_for.
   # Source: tests/test_cycle15_query_tier1_wiring.py (deleted in same commit).


   def _summary_page(pid: str, content_chars: int) -> dict:
       return {
           "id": pid,
           "path": f"/wiki/summaries/{pid}.md",
           "title": f"Summary {pid}",
           "type": "summary",
           "confidence": "stated",
           "content": "x" * content_chars,
           "score": 1.0,
       }


   def test_tier1_wiki_pages_budget_controls_summaries(monkeypatch):
       """AC21 — monkeypatching split['wiki_pages'] shrinks summaries cap proportionally."""
       from kb import config
       from kb.query.engine import _build_query_context

       # Create many 2KB summaries that would all fit at 60% split but NOT at 10%.
       pages = [_summary_page(f"s{i}", content_chars=2_000) for i in range(20)]

       # At 60% split (default), wiki_pages_budget = 20_000 * 60 / 100 = 12_000 chars.
       default_result = _build_query_context(pages)
       default_count = len(default_result["context_pages"])
       assert default_count >= 5, "default 60% split should admit at least 5 summaries"

       # Monkeypatch wiki_pages split to 10 -> wiki_pages_budget = 20_000 * 10 / 100 = 2_000.
       shrunken = dict(config.CONTEXT_TIER1_SPLIT)
       shrunken["wiki_pages"] = 10
       shrunken["chat_history"] = 20
       shrunken["index"] = 15
       shrunken["system"] = 55  # sum to 100
       monkeypatch.setattr(config, "CONTEXT_TIER1_SPLIT", shrunken)

       shrunken_result = _build_query_context(pages)
       shrunken_count = len(shrunken_result["context_pages"])
       assert shrunken_count < default_count, (
           "shrinking wiki_pages split must reduce summaries admitted; "
           f"default={default_count} shrunken={shrunken_count}"
       )


   def test_tier1_budget_for_is_called(monkeypatch):
       """AC21 — _build_query_context invokes tier1_budget_for('wiki_pages')."""
       from kb import config
       import kb.query.engine as engine_mod
       from kb.query.engine import _build_query_context

       spy_calls: list[str] = []
       real = config.tier1_budget_for

       def _spy(component: str) -> int:
           spy_calls.append(component)
           return real(component)

       # Patch the engine's import alias so the spy is picked up.
       monkeypatch.setattr(engine_mod, "tier1_budget_for", _spy)

       pages = [_summary_page("x", content_chars=500)]
       _build_query_context(pages)
       assert "wiki_pages" in spy_calls, (
           f"expected tier1_budget_for('wiki_pages') call; got {spy_calls}"
       )
   ```
2. Per Q3: helper `_summary_page` kept as-is (no clash; R1 confirmed).
3. Per Q5: end-of-file placement.
4. Function-local imports for `kb.config`, `kb.query.engine` consistent with the existing test_query.py pattern (line 12 has top-level import of `_flag_stale_results`; the cycle-19 L2 lazy-import lesson recommends function-local for new fold tests to avoid module-load side effects in receiver). Use function-local for safety.
5. Delete source file.

**Test (revert-verify per C40-L3):**
- Insert `assert False` into `test_tier1_wiki_pages_budget_controls_summaries`.
- Run `pytest tests/test_query.py::test_tier1_wiki_pages_budget_controls_summaries -v -x`, confirm FAIL.
- Restore.
- Run `pytest tests/test_query.py::test_tier1_wiki_pages_budget_controls_summaries tests/test_query.py::test_tier1_budget_for_is_called -v` (ISOLATION).
- Run `pytest tests/test_query.py -q` (full receiver).

**Criteria:** AC4, AC5, AC8, AC9.

**Commit message file (`.data/cycle-52/commit-fold-4.txt`):**
```
test(cycle 52): fold cycle-15 tier-1 budget wiring into test_query.py

Cycle 52 hygiene fold #4 of 4. Migrates the cycle-15 AC2/AC21 wiring
regression for `_build_query_context` -> `tier1_budget_for("wiki_pages")` into
test_query.py under a new section `# Tier-1 budget wiring (cycle 52 fold)`.

Per cycle-52 design-gate Q3, the helper `_summary_page` is kept as-is
(no clash with existing `_create_wiki_page` helper). Per Q5, placed at
end-of-file to avoid splitting existing test groupings.

Function-local imports per cycle-19 L2 lazy-import safety in receiver
context.

Per C40-L3, isolation revert-verify confirmed (assert False -> FAIL on a
moved function, restored).

File count 226 -> 225 (-4 cumulative). Test count preserved at 3025.
```

## TASK 5 — Doc-sync commit + BACKLOG cycle-53+ entry

(Step 12 doc update — see Step 12 task in main task list)

## Plan-gate decision

Per C37-L5: 4 ACs, all surface-level fold ops, primary holds full context from Steps 1-5,
receivers grep-verified by R1, no new src/ exploration needed. **Skip Step 8 plan-gate dispatch.**
Proceed directly to Step 9 implementation.

If a fold surfaces an unexpected isolation pytest failure (per C51-L1), pause the cycle, dispatch
DeepSeek for a focused diagnosis, and re-enter Step 5 design gate with a DESIGN-AMEND per
C17-L3 (scope-narrowing discoveries route BACK to Step 5).
