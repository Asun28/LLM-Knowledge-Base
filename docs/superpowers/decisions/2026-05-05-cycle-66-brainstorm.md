# Cycle 66 — Brainstorming (Design Alternatives)

**Date:** 2026-05-05
**Branch:** `feat/cycle-66`
**Step:** 3 of 24
**Inputs:** `2026-05-05-cycle-66-requirements.md` (5 ACs) · `2026-05-05-cycle-66-threat-model.md` (7 threats T1-T7, verdict APPROVE)

---

## Summary

Five ACs. Two have an obvious single-option answer (subtractive deletes); three have 2-4 alternatives worth comparing in Step 4 design eval. Per dev-mimo-opus convention, this doc enumerates options without picking — Step 4 R1 (Opus) + R2 (DeepSeek) score them, Step 5 locks the choice.

| AC | Real design choice? | Recommended option (this doc's lean) |
|---|---|---|
| AC1 | No — branch is dead, just delete + fix comment. | **A** (delete) |
| AC2 | Yes — import-time vs call-time derivation. | **A** (module-level frozenset, derive once) |
| AC3 | Yes — hand-rolled vs `lru_cache`; cache key shape. | **B** (`lru_cache(maxsize=8)` on heuristic-only inner fn) |
| AC4 | Yes — extend helper vs sibling helper vs in-test consolidation. | **B** (sibling `find_module_imports` in `_helpers/ast_walk.py`) |
| AC5 | No — drop kwarg (zero callers opt out). | **A** (delete kwarg + unconditional check) |

The "lean" column is non-binding; it's the primary-session's first-cut preference, included so Step 4 reviewers know which option this doc considers default.

---

## AC1 — Remove dead `kb.config.__getattr__("PROJECT_ROOT")` branch

### Option A — Delete branch + rewrite comment block

```python
# Before (config.py:760-776):
def __getattr__(name: str):
    if name == "PROJECT_ROOT":
        return get_project_root()  # ← DEAD: line 107 binds the name
    if name == "AUGMENT_ALLOWED_DOMAINS":
        return get_allowed_domains()
    raise AttributeError(...)

# After:
def __getattr__(name: str):
    """PEP 562 hook for names NOT bound at module load.

    PROJECT_ROOT IS bound at line 107, so attribute access returns the
    binding directly (this hook never fires for it). Tests monkeypatch
    `kb.config.PROJECT_ROOT` and the new value flows through
    `get_project_root()`'s `globals().get("PROJECT_ROOT")` shim
    (cycle-65 Step-12 fix).

    AUGMENT_ALLOWED_DOMAINS is NOT bound at module load — this hook IS
    the live route for that name (cycle-65 AC3).
    """
    if name == "AUGMENT_ALLOWED_DOMAINS":
        return get_allowed_domains()
    raise AttributeError(...)
```

**Pros:**
- Truly subtractive change — no behavior shift on any production path.
- Comment block becomes accurate (currently misleading, says "the shim fires if the attribute is not in the module dict" without acknowledging that `PROJECT_ROOT` IS in the dict).
- Step-9 implementation effort: ~10 minutes.

**Cons:**
- None identified — the branch is provably dead.

### Option B — LazyPathProxy redesign (Out of Scope, deferred)

Replace `PROJECT_ROOT = _resolve_project_root()` (config.py:107) with a class that re-reads on every attribute access. Would resolve cycle-19 L2 hazard for ALL `kb.config.PROJECT_ROOT` access patterns including snapshot-bound ones (`from kb.config import PROJECT_ROOT`).

**Out of scope per requirements doc** — touches ~200 import-time snapshot callers, needs migration plan, deferred to cycle 67+.

### Verdict

**Option A.** Subtractive. No alternative considered viable for cycle 66.

---

## AC2 — `_check_no_secrets_on_argv` sources keys from `CLI_BACKEND_ENV_INJECT`

### Option A — Module-level frozenset, derived once at import

```python
# In cli_backend.py, right above _check_no_secrets_on_argv:

_SCRUB_KEYS: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "FIRECRAWL_API_KEY",
        "MIMOCODING_API_KEY",
        "MIMOCHAT_API_KEY",
    }
    | {key for keys in CLI_BACKEND_ENV_INJECT.values() for key in keys}
)


def _check_no_secrets_on_argv(argv: list[str]) -> None:
    from kb.utils.llm import LLMError

    for key in _SCRUB_KEYS:
        secret_value = os.environ.get(key, "")
        if not secret_value:
            continue
        for elem in argv:
            if secret_value in elem:
                raise LLMError(
                    f"Refusing to place env secret {key!r} on subprocess argv (T8, AC16).",
                    kind="invalid_request",
                )
```

**Pros:**
- Fast: frozenset built once at import.
- Simple: no extra accessor.
- Tests parametrize over `kb.config.CLI_BACKEND_ENV_INJECT.values()` (the live canonical map) — divergent-fail catches any drift between `_SCRUB_KEYS` and the canonical source (closes T4).

**Cons:**
- Captures `CLI_BACKEND_ENV_INJECT` at IMPORT TIME. If a future cycle ever makes `CLI_BACKEND_ENV_INJECT` runtime-mutable (e.g., dynamic backend registration), this snapshot becomes stale. Not a current risk — the map is a module-level constant in `kb.config`.

### Option B — Runtime accessor `_get_scrub_keys()`

```python
def _get_scrub_keys() -> frozenset[str]:
    return frozenset(
        {"ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY", "MIMOCODING_API_KEY", "MIMOCHAT_API_KEY"}
        | {key for keys in CLI_BACKEND_ENV_INJECT.values() for key in keys}
    )


def _check_no_secrets_on_argv(argv: list[str]) -> None:
    ...
    for key in _get_scrub_keys():
        ...
```

**Pros:**
- Aligns with cycle-19 L2 call-time-read discipline.
- Safe under hypothetical runtime mutation of `CLI_BACKEND_ENV_INJECT`.

**Cons:**
- Recomputes the frozenset on every `_check_no_secrets_on_argv` call (~once per `call_cli` invocation, possibly 2× when prompt is on argv via `--prompt`). Not in a tight loop, but unnecessary work.
- Adds an indirection layer — slightly less obvious that the canonical map is the source of truth.

### Option C — Module-level + lazy `_reset_scrub_keys()` for tests

Combines A's static cache with explicit invalidation hooks for tests that mutate `CLI_BACKEND_ENV_INJECT`. Overkill — no test today mutates the map.

### Verdict

**Option A.** Module-level frozenset is faster, simpler, and the parametrize-from-`CLI_BACKEND_ENV_INJECT` test (per T4 closure in threat model) catches drift. Step 5 may swap to Option B if reviewers flag the cycle-19 L2 alignment as load-bearing.

---

## AC3 — `get_project_root()` per-call cost cache

The cache target is the heuristic walk-up portion of `_resolve_project_root()` (the env-var path is already a one-line short-circuit, no value in caching). Cache key = `cwd` (env is read above the cache, module binding is read above the cache).

### Option A — Hand-rolled module-global tuple

```python
# config.py:

_HEURISTIC_CACHE: tuple[Path, Path] | None = None  # (cwd, resolved_root)


def _resolve_project_root() -> Path:
    global _HEURISTIC_CACHE
    env_root = os.environ.get("KB_PROJECT_ROOT")
    if env_root:
        # Existing env-resolve branch — not cached (already cheap).
        ...
        return resolved_or_heuristic

    try:
        cwd = Path.cwd().resolve()
    except (OSError, RuntimeError):
        return _resolve_project_root_uncached()  # heuristic-only, no cwd

    if _HEURISTIC_CACHE is not None and _HEURISTIC_CACHE[0] == cwd:
        return _HEURISTIC_CACHE[1]

    result = _heuristic_walk_up(cwd)
    _HEURISTIC_CACHE = (cwd, result)
    return result


def _reset_project_root() -> None:
    """Test helper: clear the heuristic cache."""
    global _HEURISTIC_CACHE
    _HEURISTIC_CACHE = None
```

**Pros:**
- Explicit single-entry cache — 1 tuple, no unbounded growth.
- `_reset_project_root()` is a clean direct invalidation (matches the existing stub at config.py:76 promised "explicit reset hook").
- Trivial to reason about thread-safety: tuple rebind is atomic on CPython.

**Cons:**
- Manual cache-key check in body — slightly more code than Option B.
- Mutable module global — one more thing to track for tests.

### Option B — `functools.lru_cache(maxsize=8)` on inner fn

```python
@functools.lru_cache(maxsize=8)
def _heuristic_walk_up_cached(cwd_str: str) -> Path:
    """Cached inner: walk up from cwd looking for pyproject.toml."""
    cwd = Path(cwd_str)
    for candidate in (cwd, *cwd.parents[:5]):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path(__file__).resolve().parent.parent.parent  # heuristic fallback


def _resolve_project_root() -> Path:
    env_root = os.environ.get("KB_PROJECT_ROOT")
    if env_root:
        ...env-resolve branch...
        return resolved

    heuristic = Path(__file__).resolve().parent.parent.parent
    if (heuristic / "pyproject.toml").exists():
        return heuristic  # fast path — own pyproject

    try:
        cwd = Path.cwd().resolve()
    except (OSError, RuntimeError):
        return heuristic

    return _heuristic_walk_up_cached(str(cwd))


def _reset_project_root() -> None:
    _heuristic_walk_up_cached.cache_clear()
```

**Pros:**
- Battle-tested `lru_cache` — handles thread-safety, hashing, eviction.
- 8-entry capacity tolerates pytest-xdist worker `os.chdir` patterns naturally.
- Splits caller body into env-resolve + cached-inner pure function — testable in isolation.

**Cons:**
- 8 entries vs Option A's 1 — marginal extra memory (8 × ~64 bytes per Path); not a real concern.
- `lru_cache` requires hashable args — `cwd_str: str` is fine but slightly less clean than `cwd: Path`.
- The wrapping function is split across two scopes — slightly less readable than Option A's single-function form.

### Option C — `@functools.cache` (unbounded)

Same as Option B but no LRU eviction. **REJECT** — long-running test sessions that change cwd many times accumulate entries indefinitely. Option B's 8-cap is the right shape for any plausible pattern.

### Cache-key shape — sub-question

| Cache key | Pros | Cons |
|---|---|---|
| `cwd` only | Simplest. Env is read above the cache so doesn't affect key. | None for current code shape. |
| `(cwd, env_value)` | Robust to future refactors that move env-read into the cached fn. | Adds an axis that the code shape doesn't currently use. |

**Lean: `cwd` only** for both Options A and B. Env-read is ABOVE the cache and stays there.

### Thread-safety — sub-question

`_HEURISTIC_CACHE` writes are single-statement rebinding (`global X; X = (a, b)` compiles to one `STORE_GLOBAL` op). Reads are single `LOAD_GLOBAL`. CPython's GIL makes both atomic. Two threads racing produce one of two valid resolutions — no torn state.

`functools.lru_cache` is internally locked.

**Lean: no explicit lock** for either option. Document the GIL atomicity assumption in a code comment for Option A.

### Verdict

**Option B.** `lru_cache(maxsize=8)` is more idiomatic Python, handles thread-safety + eviction structurally, and splits the function for cleaner unit testing. Option A is fine if reviewers prefer the explicitness; Step 4 picks.

---

## AC4 — Walker consolidation: 4 `rglob` → 1 walk

Helper at `tests/_helpers/ast_walk.py::find_imports_from(module, name)` only handles `ast.ImportFrom` (verified at threat-model time, T6.4). The four banned-import tests need to detect BOTH `import diskcache` (`ast.Import`) AND `from diskcache import Cache` (`ast.ImportFrom`) patterns. Three integration shapes, plus an in-test localized variant:

### Option A — Extend `find_imports_from` to handle both forms

```python
# tests/_helpers/ast_walk.py:

def find_imports_from(
    module: str,
    name: str | None = None,
    *,
    src_root: Path = Path("src/kb"),
) -> list[Path]:
    """Find files importing `module` (any form) or `module.name` (specific).

    - If `name` is None: matches BOTH `import {module}` (ast.Import)
      AND `from {module} import *` / `from {module} import X` (ast.ImportFrom).
    - If `name` is set: matches only `from {module} import {name}` (ImportFrom).
    """
    ...
```

**Pros:**
- Single helper API for all banned-import scans.
- Re-uses existing helper — `name=None` is a backward-compatible extension (existing 5 callers in cycle-65 AC4/AC17/AC18/AC20/AC23 all pass `name=...`, unchanged).

**Cons:**
- Mutates the helper's contract — adds an `Optional[None]` overload that affects future callers.
- Existing tests at `tests/_helpers/test_ast_walk.py:17-41` are stub fixtures; extending the helper without writing real tests leaves the new code path uncovered.

### Option B — Sibling helper `find_module_imports`

```python
# tests/_helpers/ast_walk.py (additive — no change to find_imports_from):

def find_module_imports(
    module: str,
    *,
    src_root: Path = Path("src/kb"),
) -> dict[str, list[Path]]:
    """Find files importing `module` in ANY form.

    Detects both `ast.Import` (bare `import {module}`) and `ast.ImportFrom`
    (`from {module} import *` / `from {module}.x import *`).

    Returns a dict keyed by import-statement form (`"import"` or `"from"`)
    mapping to the list of files that contain the matching import.
    """
    matches: dict[str, list[Path]] = {"import": [], "from": []}
    if not src_root.exists():
        return matches
    for py_file in src_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == module or alias.name.startswith(f"{module}."):
                        matches["import"].append(py_file)
                        break
            elif isinstance(node, ast.ImportFrom):
                if node.module == module or (node.module or "").startswith(f"{module}."):
                    matches["from"].append(py_file)
    return matches
```

**Pros:**
- Existing `find_imports_from` callers (5 from cycle-65) entirely unchanged.
- New helper is purpose-built for the AC4 use case — clear naming.
- Returns shape `{"import": [...], "from": [...]}` makes assertion shape obvious.

**Cons:**
- Helper module gains a new symbol — slight surface growth.
- Two helpers with overlapping concerns (one specific-symbol, one any-form) — could confuse future contributors choosing between them. (Mitigated by docstring distinguishing use cases.)

### Option C — In-test single-walk consolidation (no helper change)

```python
# tests/test_security_cve_greps.py:

class TestCVEBannedImports:
    @staticmethod
    def _scan_imports() -> dict[str, list[str]]:
        """Walk src/kb/ once, return {module_name: [files]} for the 4 banned modules."""
        banned = {"diskcache", "litellm", "pip", "ragas"}
        result = {m: [] for m in banned}
        src_kb = Path("src/kb")
        for py_file in src_kb.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in banned:
                            result[root].append(str(py_file))
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".", 1)[0]
                    if root in banned:
                        result[root].append(str(py_file))
        return result

    @pytest.mark.parametrize("module", ["diskcache", "litellm", "pip", "ragas"])
    def test_banned_module_zero_imports(self, module):
        result = self._scan_imports()
        assert result[module] == [], f"{module} imports found: {result[module]}"
```

**Pros:**
- No helper-module change.
- Maximally localized — one file changes.
- Walk happens once per test session via class-level cache (could add `@functools.cache`).

**Cons:**
- Re-implements logic that `find_imports_from` could host. Future banned-import scans face the same friction.
- Couples the test to a private static method — slightly less reusable.

### Option D — Regex-based consolidation (existing approach, just merged)

Keep the regex approach but consolidate to one walk:

```python
def _scan_imports() -> dict[str, list[str]]:
    patterns = {
        m: re.compile(rf"^\s*(import\s+{m}\b|from\s+{m}\b)")
        for m in ("diskcache", "litellm", "pip", "ragas")
    }
    ...one rglob, four pattern checks per file...
```

**Pros:**
- Minimal change from existing code.
- Catches both `import X` and `from X` via the alternation pattern.

**Cons:**
- Regex misses edge cases AST handles cleanly: line continuations, multi-line imports, conditional imports inside `try:`/`except ImportError:` blocks, comments-with-the-pattern.
- Regex on file body is the SAME hazard class as cycle-3 L1 / cycle-6 L2 / cycle-11 L1 (source-scan tests as `inspect.getsource` in disguise). Closing this hazard is part of the cycle's value.

### Verdict

**Option B (sibling helper).** Cleanest separation, no risk to AC17 callers, helper module gains a reusable primitive. Option D is rejected for the regex hazard. Options A and C are viable; Step 4 may prefer C for localization or A for API consolidation.

---

## AC5 — Drop `allow_symlinks` kwarg from `_assert_under_project_root`

### Option A — Direct deletion

```python
# Before (path_safety.py:30-100):
def _assert_under_project_root(
    path: Path,
    field_name: str,
    *,
    require_exists: bool = False,
    require_dir: bool = False,
    dual_anchor: bool = True,
    allow_symlinks: bool = False,  # ← delete this
) -> None:
    ...
    # Optional symlink rejection
    if not allow_symlinks and path.is_symlink():
        raise ValueError(f"{field_name} is a symlink (not allowed)")

# After:
def _assert_under_project_root(
    path: Path,
    field_name: str,
    *,
    require_exists: bool = False,
    require_dir: bool = False,
    dual_anchor: bool = True,
) -> None:
    ...
    # Symlink rejection (unconditional — cycle-66 AC5 dropped allow_symlinks kwarg).
    if path.is_symlink():
        raise ValueError(f"{field_name} is a symlink (not allowed)")
```

Also update:
- Module docstring (line 13): `Hard cap: 4 keyword-only parameters` → `Hard cap: 3 keyword-only parameters (Q2.2 cycle-65 → cycle-66 reduced)`.
- Function docstring (line 50): remove `allow_symlinks` arg description.

**Pros:**
- Subtractive change — zero callers across `src/` and `tests/` opt out (verified at requirements + threat-model time).
- Q2.2 hard kwarg cap drops 4 → 3, freeing namespace for future param.
- Closes T7 ("future fourth caller passes `allow_symlinks=True`") structurally.

**Cons:**
- Hypothetical future caller that genuinely WANTS to opt out of symlink rejection would now need a separate mechanism. Not a current concern; revisit if needed.

### Option B — Deprecate-then-remove via `DeprecationWarning`

Standard Python deprecation flow: keep the kwarg, emit a warning when set to `True`, remove in cycle 67.

**REJECT** — overkill. Zero callers opt out today; warning would only fire on the hypothetical future fourth caller, which is exactly the case AC5 wants to prevent. Direct removal is correct.

### Verdict

**Option A.** Subtractive, well-scoped.

---

## Cross-cutting concerns

### 1. Test file count and naming

Per AC6 (requirements doc):
- `tests/test_cycle66_config_pep562.py` (AC1)
- `tests/test_cycle66_secret_scrub.py` (AC2)
- `tests/test_cycle66_project_root_cache.py` (AC3)
- `tests/test_cycle66_cve_greps_consolidated.py` (AC4)
- `tests/test_cycle66_path_safety_symlink.py` (AC5)

5 new test files. Cycle-65 split similarly (12 new test files for 23 ACs, roughly 1 test file per multi-AC cluster). Consistent with project convention.

### 2. Helper extension scope (AC4 → cross-cutting with `_helpers/`)

If Option B for AC4 lands, `tests/_helpers/ast_walk.py` gains `find_module_imports`. The dedicated test file `tests/_helpers/test_ast_walk.py` should gain real tests for it (the existing 3 stub tests for `find_imports_from` at lines 17-41 are pre-existing tech debt not covered by AC4). Recommendation: out of scope for cycle 66; file as cycle-67+ candidate ("`test_ast_walk.py` stubs need real coverage").

### 3. Step-9 implementation order

Recommended commit order (one commit per AC, file-grouped per `feedback_batch_by_file`):
1. AC5 (path_safety.py kwarg removal) — smallest diff, lowest risk.
2. AC1 (config.py dead-branch removal) — small diff, no behavior change.
3. AC4 (test consolidation + new sibling helper if Option B chosen).
4. AC3 (config.py heuristic cache) — perf change with explicit reset hook.
5. AC2 (cli_backend.py scrub canon expansion) — highest-stakes Information Disclosure closer.

Order rationale: lowest-risk first to keep CI green during incremental commits; AC2 last because its parametrize-from-`CLI_BACKEND_ENV_INJECT` test depends on cycle-65 AC16's existing scrub mechanism being intact (which it is on `feat/cycle-66` branch HEAD).

### 4. Step-9 background reviewer (DeepSeek V4 Pro, cross-family)

Per pipeline: DeepSeek V4 Pro background reviewer runs alongside primary impl. For cycle 66, dispatch the DeepSeek background after AC2 lands (highest-stakes AC) so cross-family review focuses where it adds most value. Earlier dispatch on AC1/AC5 has lower marginal value (subtractive changes).

### 5. Memory references

- `feedback_test_behavior_over_signature` — every test exercises production path; AC1's `__getattr__`-mutation control is the divergent-fail proof.
- `feedback_inspect_source_tests` — AC4 must NOT use `inspect.getsource` or regex-on-source; AST-walk via Option B is the right shape.
- `feedback_batch_by_file` — commits group by file; 5 ACs across 4 production files + 5 test files = 5 commits.
- `project_cycle61_mimo_failure` — primary-session impl for security-class ACs; AC2 specifically goes primary-session.

---

## Step 4 hand-off

Step 4 R1 (Opus) and R2 (DeepSeek V4 Pro) will score these alternatives in parallel. Each reviewer should:

1. Confirm the lean column's recommendation OR propose a different option with rationale.
2. Surface any threat the brainstorm missed (especially cross-AC interactions).
3. Identify Step-5 conditions the design-decision gate must lock.
4. Flag Tier-escalation risk (none expected per Step-2 threat-model verdict).

Open design questions for reviewers:
- **AC2:** Module-level frozenset (Option A) vs runtime accessor (Option B)? cycle-19 L2 alignment vs simplicity.
- **AC3:** Hand-rolled (Option A) vs `lru_cache(maxsize=8)` (Option B)? Explicitness vs idiomatic Python.
- **AC4:** Extend helper (Option A) vs sibling helper (Option B) vs in-test (Option C)? Reusability vs locality.

---

## Verdict

**Brainstorm complete. 5 ACs surveyed; 3 with real design choices (AC2, AC3, AC4) and 2 with single-option answers (AC1, AC5).**

→ Proceed to Step 4 (parallel R1 Opus + R2 DeepSeek design eval).
