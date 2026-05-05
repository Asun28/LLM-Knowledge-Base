# Cycle 66 — Design Decision Gate (Authoritative Spec)

**Date:** 2026-05-05
**Branch:** `feat/cycle-66`
**Step:** 5 of 24
**Owner:** Opus 4.7 primary-session (quality-driven C58-L4 carve-out per `feedback_minimize_subagent_pauses`; ≤7-AC scope below the subagent-dispatch threshold)
**Inputs:** `2026-05-05-cycle-66-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek}.md`

---

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS.** Tier 2 stands. Cycle scope locked: 5 code ACs (AC1-AC5) + 1 test-infrastructure AC (AC6) + 1 doc-update AC (AC7). All R1 + R2 conditions inline-resolved into this spec. No design alternative-option deviations from the brainstorm leans on independent score. Step 6 (Context7) skip-candidate confirmed (pure stdlib, no new lib references). Proceed to Step 7 (implementation plan).

---

## Convergence summary

| AC | R1 Opus | R2 DeepSeek | LOCKED |
|----|---------|-------------|--------|
| AC1 | Option A — delete branch | Option A — delete branch | **A** |
| AC2 | Option A + parametrize-from-canonical | Option A + parametrize-from-canonical | **A** + canonical-source parametrize |
| AC3 | Option B — `lru_cache(maxsize=8)` | Both A/B sound; slight lean B | **B** |
| AC4 | Option B + mandatory helper tests | Option C OR Option B + mandatory helper tests | **B** + mandatory helper tests |
| AC5 | Option A — drop kwarg | Option A — drop kwarg | **A** |

Both reviewers converge on every AC. The only nuance: AC4 R2 prefers Option C as a fallback if helper tests aren't added. Both options close T6 equivalently when paired with the both-import-forms negative-control fixture; **Option B + mandatory helper tests** wins on future-proofing (reusable primitive for cycle-67+ banned-import additions) which is what R1 emphasized and R2 conditionally accepted. Lock Option B with the helper-test obligation made non-optional below.

---

## Final Acceptance Criteria (post-locks)

The five code ACs and two infra/doc ACs from the requirements doc are preserved with the following adjustments:

### AC1 — Remove dead `kb.config.__getattr__("PROJECT_ROOT")` branch (LOCKED)

**Source:** `src/kb/config.py:760-776`

**Diff:**
- Delete the `if name == "PROJECT_ROOT": return get_project_root()` branch (current lines 772-773).
- Rewrite the comment block at lines 760-769 to:
  - Name `AUGMENT_ALLOWED_DOMAINS` as the only live PEP 562 branch (it has no module-level binding, so the shim IS the live route — cycle-65 AC3).
  - Note that `PROJECT_ROOT` is bound at line 107, so attribute access never reaches `__getattr__`. Tests that monkeypatch `kb.config.PROJECT_ROOT` flow through `get_project_root()`'s `globals().get("PROJECT_ROOT")` shim (cycle-65 Step-12 fix).

**Test contract:** `tests/test_cycle66_config_pep562.py`
- **Behavioral test (divergent-fail control):** mutate `kb.config.__getattr__` to raise `AttributeError` for any name (use direct binding `kb.config.__getattr__ = new_fn` with explicit teardown if `monkeypatch.setattr` doesn't replace module-level `__getattr__` — verify in Step 9). After the mutation, assert `kb.config.get_project_root()` STILL returns the monkeypatched `PROJECT_ROOT` value. This proves the test exercises the module-binding path, not the dead branch.
- Standard regression: monkeypatch `kb.config.PROJECT_ROOT` → `tmp_path`; assert `kb.config.get_project_root() == tmp_path`.
- env-override test: `monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))`; assert `kb.config.get_project_root() == tmp_path.resolve()`.

**Closes:** T1 (test-correctness regression on dead-branch revert).

### AC2 — `_check_no_secrets_on_argv` sources keys from `CLI_BACKEND_ENV_INJECT` (LOCKED)

**Source:** `src/kb/utils/cli_backend.py:138-148`

**Diff:**
- Add module-level `_SCRUB_KEYS: frozenset[str]` immediately above `_check_no_secrets_on_argv`:
  ```python
  # AC2 (cycle 66): Derive scrub-key set at import time from the canonical
  # CLI_BACKEND_ENV_INJECT mapping plus the four standalone keys not bound
  # to any backend tuple. Adding a 9th backend to CLI_BACKEND_ENV_INJECT
  # automatically gains scrub coverage — DO NOT re-hardcode this list.
  #
  # Why import-time capture is safe (cycle-19 L2 clarification): cycle-19
  # L2 reload-leak hazard targets env-DERIVED constants. CLI_BACKEND_ENV_INJECT
  # is a module-literal dict at config.py:329-338, NOT env-derived, so
  # capturing it at import time is fine. The frozenset DOES need to be
  # rebuilt if CLI_BACKEND_ENV_INJECT is ever made runtime-mutable, which
  # is not the case today.
  _SCRUB_KEYS: frozenset[str] = frozenset(
      {
          "ANTHROPIC_API_KEY",
          "FIRECRAWL_API_KEY",
          "MIMOCODING_API_KEY",
          "MIMOCHAT_API_KEY",
      }
      | {key for keys in CLI_BACKEND_ENV_INJECT.values() for key in keys}
  )
  ```
- Replace the hardcoded 6-key list at lines 140-147 with a `for key in _SCRUB_KEYS:` iteration. Substring-containment scrub mechanism (cycle-65 AC16 + Step-09 DeepSeek BLOCKER-1 fix) UNCHANGED.

**Post-AC2 frozenset (11 keys):**
- 4 standalone: `ANTHROPIC_API_KEY`, `FIRECRAWL_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`.
- 7 from `CLI_BACKEND_ENV_INJECT.values()`: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `KIMI_API_KEY`, `QWEN_API_KEY`, `DEEPSEEK_API_KEY`, `ZAI_API_KEY`, `ZHIPUAI_API_KEY`.
- 5 net-new (cycle-66 gain): `GEMINI`, `KIMI`, `QWEN`, `ZAI`, `ZHIPUAI`.

**Test contract:** `tests/test_cycle66_secret_scrub.py`
- **Parametrize source MUST be `kb.config.CLI_BACKEND_ENV_INJECT` (the live canonical map), NOT the computed `_SCRUB_KEYS` literal.** Pseudocode:
  ```python
  _CANONICAL_KEYS = (
      {"ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY", "MIMOCODING_API_KEY", "MIMOCHAT_API_KEY"}
      | {k for v in kb.config.CLI_BACKEND_ENV_INJECT.values() for k in v}
  )

  @pytest.mark.parametrize("key", sorted(_CANONICAL_KEYS))
  def test_scrub_blocks_argv_with_env_value(key, monkeypatch):
      sentinel = f"sentinel-value-for-{key}-12345"
      monkeypatch.setenv(key, sentinel)
      with pytest.raises(LLMError, match=r"(?i)refusing to place env secret"):
          _check_no_secrets_on_argv(["kb", "--header", f"Authorization: Bearer {sentinel}"])
  ```
  Drift safeguard: if a future contributor reverts `_SCRUB_KEYS` to a hardcoded 6-key list, the parametrize loop still produces 11 cases, and the GEMINI/KIMI/QWEN/ZAI/ZHIPUAI cases fail RED (closes T4).
- **Paired negative-control:** same parametrize set, but sentinel placed in argv WITHOUT being set as the env value — assert `_check_no_secrets_on_argv` does NOT raise. Closes T3 (false-positive on key-NAME discussions).
- **Edge-case test:** empty env value (`monkeypatch.delenv(key, raising=False)`) — confirm scrub short-circuits and does NOT raise even if argv contains the literal env-var NAME.

**Closes:** T2 (argv leak of 5 net-new keys; CLOSED), T3 (substring scrub false-positive on legit prompts; intended behaviour preserved), T4 (future-revert hazard; CLOSED by canonical parametrize source).

### AC3 — `get_project_root()` heuristic walk-up cache (LOCKED)

**Source:** `src/kb/config.py:15-82`

**Diff:**
- Refactor `_resolve_project_root()` into env-prefix + cached-inner:
  ```python
  @functools.lru_cache(maxsize=8)
  def _heuristic_walk_up_cached(cwd_str: str) -> Path:
      """Cached: walk up from cwd looking for pyproject.toml.

      Cache key is cwd_str (env is read above this fn, module binding is
      checked above this fn — env mutations + monkeypatched PROJECT_ROOT
      flow through call-time without invalidating the cache). 8-entry
      capacity tolerates pytest-xdist worker patterns + test-time os.chdir
      without explicit reset.
      """
      heuristic = Path(__file__).resolve().parent.parent.parent
      cwd = Path(cwd_str)
      for candidate in (cwd, *cwd.parents[:5]):
          if (candidate / "pyproject.toml").exists():
              _LOG.info(...)
              return candidate
      return heuristic


  def _resolve_project_root() -> Path:
      heuristic = Path(__file__).resolve().parent.parent.parent
      env_root = os.environ.get("KB_PROJECT_ROOT")
      if env_root:
          # ... existing env-resolve branch UNCHANGED ...
          return resolved_or_heuristic

      if (heuristic / "pyproject.toml").exists():
          return heuristic  # fast path — own pyproject

      try:
          cwd = Path.cwd().resolve()
      except (OSError, RuntimeError):
          return heuristic

      return _heuristic_walk_up_cached(str(cwd))
  ```
- `_reset_project_root()` becomes:
  ```python
  def _reset_project_root() -> None:
      """Clear the heuristic walk-up cache (cycle 66 AC3)."""
      _heuristic_walk_up_cached.cache_clear()
  ```
- `get_project_root()` UNCHANGED (still env-first, then `globals().get("PROJECT_ROOT")`, then `_resolve_project_root()`).

**Test contract:** `tests/test_cycle66_project_root_cache.py`
- **Hit-then-miss:** spy on `Path.cwd` (or on `_heuristic_walk_up_cached.cache_info()`); call `_resolve_project_root()` twice with no env / no monkeypatch; assert second call hits cache (cwd invocation count unchanged OR `cache_info().hits` increments).
- **Reset clears cache:** `_reset_project_root()`; assert `_heuristic_walk_up_cached.cache_info().currsize == 0`. Re-call → fresh heuristic invocation.
- **env-override bypasses cache:** `monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_a))`; assert returns `tmp_a` regardless of whether `_HEURISTIC_CACHE` was warm or cold. Then `monkeypatch.delenv`; assert next call recomputes via heuristic.
- **Module-binding override bypasses cache:** `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_b)`; assert `kb.config.get_project_root() == tmp_b`. (This test exercises `get_project_root()`'s `globals().get` shim, not `_resolve_project_root()` — confirms cache doesn't shadow the binding override.)
- **cwd change recomputes:** `monkeypatch.chdir(tmp_a)`; first call. `monkeypatch.chdir(tmp_b)`; second call MUST return different value (cache key includes cwd, so cwd-change is a cache-miss).
- **Divergent-fail control:** revert AC3 (drop the `@lru_cache` decorator or inline the body) → hit-then-miss test fails because the heuristic invokes twice (`cache_info().hits == 0`).

**CHANGELOG framing (locked at Step 17):** Honestly characterise this as **test-suite + dev-loop perf**, not "MCP-boundary production perf" — production deployments typically set `KB_PROJECT_ROOT` and short-circuit at `config.py:18-27` before reaching the cache. The MCP-boundary-syscall claim from the BACKLOG entry is overstated for production but accurate for the env-unset case dominant in dev/test.

**Closes:** T5 (cache stale across `os.chdir` in concurrent tests; CLOSED by `cwd_str` cache key).

### AC4 — `tests/test_security_cve_greps.py` 4-walk → 1-walk + new helper (LOCKED)

**Source 1:** `tests/_helpers/ast_walk.py` — additive (existing `find_imports_from` unchanged).

**Source 2:** `tests/test_security_cve_greps.py` — replace 4 method bodies with a single parametrized test consuming the new helper.

**Diff (helper):**
```python
# Add to tests/_helpers/ast_walk.py:

def find_module_imports(
    module: str,
    *,
    src_root: Path = Path("src/kb"),
) -> dict[str, list[Path]]:
    """Find files importing `module` in ANY form.

    Detects:
    - `ast.Import` — bare `import {module}` AND `import {module}.x`.
    - `ast.ImportFrom` — `from {module} import *`, `from {module} import X`,
      `from {module}.x import y`.

    Returns:
        dict with two keys: "import" (list of files with bare-import form)
        and "from" (list of files with from-import form). A file may
        appear in BOTH lists if it uses both forms.

    Cycle-66 AC4: closes T6 (silent-pass on banned-import refactor) by
    structurally covering both AST node classes. The existing helper
    `find_imports_from(module, name)` only handles ImportFrom and is
    used by cycle-65 AC4/AC17/AC18/AC20/AC23 callers (unchanged).
    """
    matches: dict[str, list[Path]] = {"import": [], "from": []}
    if not src_root.exists():
        return matches
    for py_file in src_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        seen_import = False
        seen_from = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and not seen_import:
                for alias in node.names:
                    if alias.name == module or alias.name.startswith(f"{module}."):
                        matches["import"].append(py_file)
                        seen_import = True
                        break
            elif isinstance(node, ast.ImportFrom) and not seen_from:
                target = node.module or ""
                if target == module or target.startswith(f"{module}."):
                    matches["from"].append(py_file)
                    seen_from = True
            if seen_import and seen_from:
                break
    return matches
```

Note: namespace-prefix matching (`startswith(f"{module}.")`) catches `import diskcache.core` and `from diskcache.core import X` — important because `pip` sub-packages (e.g., `pip._internal`) share the banned-name root.

**Diff (consumer):**
```python
# tests/test_security_cve_greps.py — replace TestCVEBannedImports body:

class TestCVEBannedImports:
    """Assert that known-CVE packages are not imported by production code."""

    @pytest.mark.parametrize("module", ["diskcache", "litellm", "pip", "ragas"])
    def test_module_zero_imports(self, module):
        """Cycle-66 AC4: consolidated AST walker over src/kb/."""
        from tests._helpers.ast_walk import find_module_imports

        result = find_module_imports(module)
        bare = result["import"]
        from_ = result["from"]
        assert not bare and not from_, (
            f"{module} imports found: bare={bare}, from={from_}"
        )
```

**Test contract — helper coverage (NEW, mandatory):** `tests/_helpers/test_ast_walk.py` MUST gain real (NOT stub) `TestFindModuleImports` cases:
- `test_find_module_imports_bare_form`: write `tmp_path/src/kb/_test_only.py` with `import diskcache\n`; assert `find_module_imports("diskcache", src_root=tmp_path / "src" / "kb")["import"]` contains the file path.
- `test_find_module_imports_from_form`: same but `from diskcache import Cache\n`; assert `["from"]` contains the file path.
- `test_find_module_imports_both_forms`: file with BOTH lines; assert file appears in both lists.
- `test_find_module_imports_namespace_prefix_bare`: `import diskcache.core` should match (bare form, namespace prefix).
- `test_find_module_imports_namespace_prefix_from`: `from diskcache.core import X` should match (from form, namespace prefix).
- `test_find_module_imports_unrelated_module`: file with `import json` should NOT match `find_module_imports("diskcache", ...)` — both lists empty.
- `test_find_module_imports_syntax_error_file`: file with broken syntax should be silently skipped (catches `SyntaxError`).
- `test_find_module_imports_missing_src_root`: nonexistent `src_root` returns `{"import": [], "from": []}` (defensive).

**Test contract — consumer divergent-fail:** `tests/test_cycle66_cve_greps_consolidated.py`
- **Negative-control fixture per banned module:** parametrized over `["diskcache", "litellm", "pip", "ragas"]`. For each, write `tmp_path/_test_only_bare.py` with `import {module}` AND `tmp_path/_test_only_from.py` with `from {module} import X`. Run `find_module_imports({module}, src_root=tmp_path)` and assert BOTH `result["import"]` AND `result["from"]` contain the corresponding files.
- This is the load-bearing T6 closure: if the walker silently misses one form, the negative-control fires RED.

**Closes:** T6 (AC4 false-pass-on-revert; CLOSED structurally).

**Out of scope (filed cycle-67+):** Real test coverage for the EXISTING `find_imports_from` stubs at `tests/_helpers/test_ast_walk.py:17-41`. AC4 only obligates coverage for the NEW `find_module_imports` helper. The existing stubs remain pre-cycle tech debt.

### AC5 — Drop `allow_symlinks` kwarg from `_assert_under_project_root` (LOCKED)

**Source:** `src/kb/utils/path_safety.py`

**Diff:**
- Remove `allow_symlinks: bool = False` from signature (line 37).
- Remove the `allow_symlinks` arg description from docstring (line 50).
- Body line 99: `if not allow_symlinks and path.is_symlink():` → `if path.is_symlink():` (rejection becomes structurally unconditional).
- **Module docstring (line 13):** `Hard cap: 4 keyword-only parameters (Q2.2 design lock)` → `Hard cap: 3 keyword-only parameters (Q2.2 cycle-65 → cycle-66 reduced; allow_symlinks removed in cycle 66 AC5)`.

**Caller verification (Step 9 grep gate):**
- Only production caller: `src/kb/compile/compiler.py:672` — uses `_assert_under_project_root(path, field_name, dual_anchor=True)`. Unchanged.
- Test callers: zero (verified by repo-wide Grep at requirements + threat-model time, retained at Step 9).

**Test contract:** `tests/test_cycle66_path_safety_symlink.py`
- **Behavioral test:** create a symlink under `tmp_path`, call `_assert_under_project_root(symlink_path, "field", dual_anchor=True)`; assert `pytest.raises(ValueError, match=r"is a symlink")`.
- **Signature pin (cycle-7 L4 belt-and-suspenders, NOT vacuous because paired with behavioral):**
  ```python
  import inspect
  from kb.utils.path_safety import _assert_under_project_root

  sig = inspect.signature(_assert_under_project_root)
  assert "allow_symlinks" not in sig.parameters
  assert set(sig.parameters.keys()) == {"path", "field_name", "require_exists", "require_dir", "dual_anchor"}
  ```
- **Caller pin:** `compile/compiler.py::_validate_path_under_project_root` raises `ValidationError` on a symlink path (transitive via the helper).

**Doc updates (locked at Step 17):**
- `docs/reference/error-handling.md` Q2.2 entry: "Hard cap: 4 keyword-only parameters" → "Hard cap: 3 keyword-only parameters (cycle-66 AC5 dropped `allow_symlinks`)".

**Closes:** T7 (future-fourth-caller `allow_symlinks=True` opt-out; CLOSED structurally by removal).

### AC6 — Test infrastructure (LOCKED unchanged from requirements)

Five new test files under `tests/`:
- `tests/test_cycle66_config_pep562.py` (AC1)
- `tests/test_cycle66_secret_scrub.py` (AC2)
- `tests/test_cycle66_project_root_cache.py` (AC3)
- `tests/test_cycle66_cve_greps_consolidated.py` (AC4 consumer-side)
- `tests/test_cycle66_path_safety_symlink.py` (AC5)

Plus AC4 NEW addition: real `TestFindModuleImports` cases added to existing `tests/_helpers/test_ast_walk.py` (≥8 cases per AC4 helper coverage list above).

### AC7 — Doc update + BACKLOG cleanup (LOCKED unchanged from requirements)

Step 17 (doc-update gate) actions:
- **Delete** `BACKLOG.md` lines 27-46 (the `## Cycle 66 candidates` section).
- `CHANGELOG.md` `[Unreleased]` Quick Reference: compact one-liner per FORMAT GUIDE (Items / Tests / Files / Scope / Detail).
- `CHANGELOG-history.md`: full per-AC bullet detail newest-first; Detail line lists this design doc + R1 + R2 + threat-model + brainstorm + requirements.
- `CLAUDE.md` Quick Reference: update test count post-Step-12.
- `docs/reference/error-handling.md`: Q2.2 kwarg cap update (4 → 3) per AC5.
- `docs/reference/architecture.md`: optional — note the new `find_module_imports` helper if helpers section exists.

---

## Inline resolutions / clarifications

### IR-1 — AC2 cycle-19 L2 framing correction (R1 MINOR)

The brainstorm's Cons column for AC2 Option A says "captures `CLI_BACKEND_ENV_INJECT` at IMPORT TIME" as a hazard. **This conflates two hazard classes.** Cycle-19 L2 reload-leak hazard targets constants whose values are derived from `os.environ.get(...)`. `CLI_BACKEND_ENV_INJECT` is a module-literal `dict[str, tuple[str, ...]]` at `config.py:329-338` — it has no env-var derivation. Capturing its values into a frozenset at import time is **safe** under cycle-19 L2.

The design comment in `cli_backend.py` (per AC2 diff above) explicitly documents this clarification so a future contributor doesn't apply L2 over-eagerly to all module constants.

### IR-2 — AC1 monkeypatch-`__getattr__` test pattern caveat (R1 NIT)

Python module-level `__getattr__` is a special-method lookup. `monkeypatch.setattr(kb.config, "__getattr__", new_fn)` may or may not replace the lookup target depending on import patterns. Step 9 implementer **verifies the divergent-fail control actually triggers** — if `monkeypatch.setattr` does not replace the lookup, fall back to direct binding:

```python
def test_get_project_root_uses_module_binding_not_dead_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    original_getattr = kb.config.__getattr__

    def fail_getattr(name):
        raise AttributeError(f"__getattr__ should not fire for {name}")

    kb.config.__getattr__ = fail_getattr  # direct binding
    try:
        assert kb.config.get_project_root() == tmp_path
    finally:
        kb.config.__getattr__ = original_getattr
```

The teardown is required because `monkeypatch` won't manage a direct binding on the module.

### IR-3 — AC4 helper-test obligation is non-optional (R1 MAJOR + R2 condition)

The new `find_module_imports` helper SHIPS WITH ≥8 real (non-stub) test cases in `tests/_helpers/test_ast_walk.py`, NOT 0. The existing stub cases for `find_imports_from` remain as pre-cycle tech debt and are NOT inherited as an acceptable model. Step 9 implementer who skips the helper tests blocks the AC4 commit.

### IR-4 — AC3 perf framing for CHANGELOG (R1 MINOR)

CHANGELOG entry locked text: "AC3 — `_resolve_project_root()` heuristic walk-up cache (test-suite + dev-loop perf; production deployments setting `KB_PROJECT_ROOT` short-circuit before reaching the cache)". This honesty prevents a future cycle from claiming an MCP-boundary regression when the cache is removed in some hypothetical refactor.

### IR-5 — AC1 + AC3 `kb.config` co-evolution (R1 NIT)

AC1 edits `kb.config:760-776` (deletes 2 lines, rewrites comment block). AC3 edits `kb.config:15-82` (refactors `_resolve_project_root` + adds `_heuristic_walk_up_cached`). **These ranges are disjoint.** Step 9 commit order (AC1 commit → AC3 commit) keeps the diffs isolated. PR review at Step 20 verifies no accidental cross-range edits.

### IR-6 — Step-9 commit order (LOCKED)

Per brainstorm + R1 cross-AC findings, commit order is:

1. **AC5** (`path_safety.py` kwarg removal + module docstring 4→3 update) — smallest diff, lowest risk.
2. **AC1** (`config.py` dead-branch removal + comment rewrite) — small, no behaviour change.
3. **AC4** (helper + helper tests + consolidated CVE-greps test + negative-control fixture) — atomic file-grouped commit per `feedback_batch_by_file`. Single commit covers `tests/_helpers/ast_walk.py`, `tests/_helpers/test_ast_walk.py`, `tests/test_security_cve_greps.py`, `tests/test_cycle66_cve_greps_consolidated.py`.
4. **AC3** (`config.py` heuristic cache refactor) — `_resolve_project_root` split, `_heuristic_walk_up_cached`, `_reset_project_root` body, AC3 test file.
5. **AC2** (`cli_backend.py` `_SCRUB_KEYS` derivation + AC2 test file) — highest-stakes AC last, after all infrastructure is green.

5 commits. Each lands with its tests in the same commit (file-grouped per `feedback_batch_by_file`).

### IR-7 — Step 6 (Context7) skip confirmed

No new external library or API references in the locked diffs. All code uses Python stdlib (`functools`, `ast`, `inspect`, `pathlib`, `re`) which is well-known and stable. **Step 6 SKIP locked.** Mark task #6 complete with skip rationale at Step 6 transition.

### IR-8 — Step-9 background-reviewer dispatch timing (cross-family DeepSeek)

Per brainstorm cross-cutting #4: dispatch DeepSeek V4 Pro background reviewer AFTER AC2 lands (highest-stakes AC). Earlier dispatch on AC1/AC5 has lower marginal value. Lock this scheduling decision: dispatch the background reviewer after the AC2 commit hits `feat/cycle-66`, not before.

---

## Locked Step-5 conditions (consolidated 11 from R1 + 2 from R2)

All R1 conditions inline-resolved into the per-AC sections above. R2's 2 conditions are subsumed by R1's #2 (AC2 parametrize) and R1's #6/#7/#8 (AC4 helper + negative-control). The full enumerated list from R1 is reproduced here for Step 9 cross-reference:

1. ✅ AC1 test contract — divergent-fail control (locked in AC1 test contract above + IR-2).
2. ✅ AC2 parametrize source = `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened, NOT `_SCRUB_KEYS` literal (locked in AC2 test contract).
3. ✅ AC2 cycle-19 L2 framing clarification (locked in AC2 design comment + IR-1).
4. ✅ AC3 cache key = `cwd_str: str` only; `_reset_project_root()` calls `cache_clear()` (locked in AC3 diff).
5. ✅ AC3 CHANGELOG framing = test-suite/dev-loop, not MCP production (locked in IR-4).
6. ✅ AC4 helper signature = `find_module_imports(module: str, *, src_root: Path = Path("src/kb")) -> dict[str, list[Path]]` (locked in AC4 helper diff).
7. ✅ AC4 helper test obligation = ≥8 real cases (locked in AC4 helper coverage list + IR-3).
8. ✅ AC4 negative-control fixture = both `import` AND `from` forms per banned module (locked in AC4 consumer test contract).
9. ✅ AC5 belt-and-suspenders test = signature pin + behavioral + caller pin (locked in AC5 test contract).
10. ✅ AC5 doc-cap update = `path_safety.py:13` 4→3, `error-handling.md` Q2.2 update (locked in AC5 diff + AC7).
11. ✅ Step-9 commit atomicity = single file-grouped commit per AC; AC4 commit bundles helper + helper-tests + consumer + fixture (locked in IR-6).

---

## Open questions for Step 7 plan

The Step 7 implementation plan (MiMo Coding subagent) MUST answer:

- **Q-7.1:** Step 9 implementation order — confirm IR-6 (AC5 → AC1 → AC4 → AC3 → AC2) or propose alternative with rationale.
- **Q-7.2:** AC1 monkeypatch test pattern — implementer to verify whether `monkeypatch.setattr(kb.config, "__getattr__", ...)` works. If not, use direct binding per IR-2. Document the choice in test docstring.
- **Q-7.3:** AC3 cache spy mechanism — `cache_info().hits` increment vs `Path.cwd` call-count spy. Either is valid; pick one consistently across the AC3 test file.
- **Q-7.4:** AC4 namespace-prefix matching — verify `pip._internal` and `diskcache.core` are detected (the AC4 helper diff above implements this; Step 9 plan should include a test case for it).
- **Q-7.5:** Step-9 background-reviewer dispatch — confirm DeepSeek V4 Pro fires post-AC2 commit per IR-8.

---

## Tier escalation check (final)

**Tier 2 stands.**

- No threat in the cycle-66 set (T1-T7) crosses the Tier-3 threshold.
- AC2 is the highest-stakes AC (real Information Disclosure closure, `medium × high` risk), but it is **purely additive** scrub coverage — the substring-containment mechanism is unchanged from cycle-65 AC16. Not a new trust boundary.
- User's `feedback_auto_approve` memory authorises Opus subagent gating without human checkpoints.
- No Step-5 manual-merge gate required.
- Step 20 R2 manual-merge gate also NOT required (Tier 2).

---

## Cross-references

- **Inputs:** `2026-05-05-cycle-66-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek}.md`
- **Source files locked at design time:** `src/kb/config.py:15-82, :107, :329-338, :760-776`, `src/kb/utils/cli_backend.py:120-160`, `src/kb/utils/path_safety.py:13, :30-100`, `src/kb/compile/compiler.py:672`, `tests/test_security_cve_greps.py:1-118`, `tests/_helpers/ast_walk.py:7-40`, `tests/_helpers/test_ast_walk.py:14-100`.
- **Memory:** `feedback_test_behavior_over_signature`, `feedback_inspect_source_tests`, `feedback_batch_by_file`, `feedback_auto_approve`, `project_cycle61_mimo_failure`, `feedback_signature_drift_verify`, `feedback_minimize_subagent_pauses`.
- **Pipeline:** dev-mimo-opus Step 5 owner = Opus subagent; this cycle ran primary-session per quality-driven C58-L4 carve-out (≤7-AC scope, no value in subagent-roundtrip).

---

## Step 5 closure checklist

- [x] R1 + R2 verdicts both APPROVE-WITH-INLINE-RESOLUTIONS — consolidated.
- [x] All 11 R1 conditions + 2 R2 conditions inline-resolved into the AC contracts.
- [x] Convergence on all 5 AC option picks (A, A, B, B, A).
- [x] Tier 2 confirmed (no escalation).
- [x] Step 6 skip rationale recorded (IR-7).
- [x] Step 9 commit order locked (IR-6).
- [x] Step 9 background-reviewer dispatch timing locked (IR-8).
- [x] Open questions for Step 7 plan enumerated (Q-7.1 through Q-7.5).
- [x] Cross-references + memory citations.

→ Proceed to Step 6 (Context7 SKIP per IR-7) and Step 7 (MiMo Coding implementation plan).
