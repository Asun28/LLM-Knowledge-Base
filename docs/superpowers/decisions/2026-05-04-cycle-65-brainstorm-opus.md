# Cycle 65 — Opus 4.7 Brainstorm (Step 3 main branch)

**Model:** Opus 4.7 main session
**Date:** 2026-05-04
**Inputs:** Step 1 requirements (23 ACs across 14 files) + Step 2 threat model (T1-T21, C1-C23) + cycle-65 BACKLOG drift findings on AC2/AC12.

---

## Analysis

Step through each AC cluster: what's the simplest closure of the threat that doesn't break existing callers? Where can ACs share infrastructure? Where is "DON'T do this" the right answer?

The 23 ACs split naturally into **4 high-leverage clusters** that share infrastructure and **4 standalone hardening clusters**:

- **High-leverage (share infra):** Cluster A (call-time accessors), Cluster D (path-safety helper), Cluster G (MCP error boundary).
- **Standalone:** Cluster B (sandbox guards), Cluster C (page-id chars), Cluster E (URL filter), Cluster F (deps).

Two ACs are **near-already-shipped** per the BACKLOG drift findings:
- **AC2** — `_DEFAULT_MODEL_TIERS` is fine; only `kb.utils.llm` direct-import migration remains.
- **AC12** — `SafeBackend` already implements RFC1918/loopback/link-local + DNS-rebind defense; only scheme allowlist + integration test gaps.

Two cross-cutting opportunities are visible from the threat model:
1. **AC4 + AC18 + AC23** are all "AST-walk regression test that fails CI on a structural drift" — they can share a `tests/_helpers/ast_walk.py` harness. Saves ~50 lines and standardizes the failure mode message.
2. **AC1 + AC3 + AC2** are all "module-level constant captures env at import time" — but the migration pattern is the same: `def get_X() -> T` accessor + `__getattr__` shim for back-compat. Single template, three applications.

The threat model's biggest gap (per OOS section): no threat covers the fact that **Step 9 implementer might add a NEW path-accepting MCP tool while the AC9 helper is still being built**. That's a temporal coordination hazard, not a design hazard — handle in Step 7 plan ordering.

---

## Cluster A — Call-time accessor migration (AC1, AC2, AC3)

### Approach A1 (default — straight migration)

Three independent accessors:
```python
def get_project_root() -> Path:
    env_root = os.environ.get("KB_PROJECT_ROOT")
    if env_root and (resolved := _try_resolve(env_root)):
        return resolved
    return _heuristic_root()

def get_allowed_domains() -> tuple[str, ...]:
    raw = os.getenv("KB_AUGMENT_ALLOWED_DOMAINS", "en.wikipedia.org,arxiv.org")
    return tuple(d.strip() for d in raw.split(",") if d.strip())
```
Plus `__getattr__` shim on `kb.config` for `PROJECT_ROOT` and `AUGMENT_ALLOWED_DOMAINS` back-compat. AC2 migrates `kb.utils.llm` from `MODEL_TIERS[tier]` to `get_model_tier(tier)`.

**Tradeoffs:** clean separation, three test files, three migration commits. Risk: 200+ tests reference `kb.config.PROJECT_ROOT` — `__getattr__` shim must NOT trigger an `AttributeError` cascade.

### Approach A2 (ENV class — single source)

Single `kb.config.env` module:
```python
class _Env:
    @property
    def project_root(self) -> Path: ...
    @property
    def allowed_domains(self) -> tuple[str, ...]: ...
    @property
    def model_tier(self, tier: str) -> str: ...

env = _Env()
```
All callers do `from kb.config import env; env.project_root`.

**Tradeoffs:** ergonomic clustering, but 200+ existing call sites would need migration. Out of scope for cycle 65 batch.

### Approach A3 (PEP 562 module-level `__getattr__` only — no helper functions)

Skip the helper-function pattern; just intercept attribute access at module level:
```python
def __getattr__(name: str):
    if name == "PROJECT_ROOT":
        return _resolve_project_root_now()
    if name == "AUGMENT_ALLOWED_DOMAINS":
        return _read_domains_now()
    raise AttributeError(name)
```

**Tradeoffs:** zero call-site changes (existing `kb.config.PROJECT_ROOT` reads now lazy). BUT: `from kb.config import PROJECT_ROOT` STILL captures the value at import time (Python imports the attribute eagerly, then `__getattr__` is bypassed). So the snapshot-leak via `from-import` is NOT closed. Reject A3.

### Recommendation: **A1** with shared template.

A1 closes the threat, ships in three independent commits (per `feedback_batch_by_file` per-file granularity), preserves existing test suite via `__getattr__` shim. The shim fires for `kb.config.PROJECT_ROOT` (attribute access), and the THREAT we're closing is module-level cache staleness — not `from-import` capture (which is a separate hazard handled by ruff/AST guards in cluster D-style work).

Step 7 plan should land AC1, AC2, AC3 as three sequential commits in `config.py` order. Test file `tests/test_cycle65_config_call_time.py` covers all three with a parametrized `monkeypatch.setenv` test.

---

## Cluster B — Sandbox guard hardening (AC4, AC5)

### Approach B1 (default — AST + sys.modules walk)

AC4: `tests/test_conftest_sandbox_guard.py` ast-parses conftest, finds `_autouse_kb_path_sandbox` FunctionDef, asserts decorator `pytest.fixture(autouse=True)`.

AC5: replace hardcoded list with sys.modules walk:
```python
for module_name, mod in list(sys.modules.items()):
    if module_name.startswith("kb."):
        for attr_name in vars(mod):
            attr = getattr(mod, attr_name, None)
            cache_clear = getattr(attr, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
```

**Tradeoffs:** clean, dynamic, future-proof. Risk: walking sys.modules is O(N_modules × N_attrs); on a fresh test it could touch hundreds of modules. Per-test overhead is small (microseconds) but worth measuring.

### Approach B2 (registry pattern — modules opt-in)

Each module with a path-sensitive `@lru_cache` registers via `kb.utils.cache_registry.register(func)`. Sandbox teardown calls `cache_registry.clear_all()`.

**Tradeoffs:** explicit, easy to grep. BUT: requires ALL existing 3 cached callables to migrate (more code churn) AND a future contributor adding a 4th `@lru_cache` MUST remember to register (the failure mode AC5 was designed to PREVENT). Registry pattern fights the threat model.

### Approach B3 (decorator wrapper — auto-register at decoration time)

```python
def cached_path_sensitive(maxsize=128):
    """Drop-in @lru_cache replacement that auto-registers for sandbox teardown."""
    def decorator(func):
        wrapped = lru_cache(maxsize=maxsize)(func)
        _PATH_SENSITIVE_CACHES.append(wrapped)
        return wrapped
    return decorator
```

**Tradeoffs:** explicit and auto-registered (best of both worlds), but introduces a new project-wide convention (`@cached_path_sensitive` instead of `@lru_cache`). Migration of existing 3 callables required.

### Recommendation: **B1**.

The sys.modules walk is the smallest delta that closes the threat. The performance concern is bounded because `kb.*` modules are <100 (project size). One commit fixes both the sandbox decorator guard (AC4) and the cache walk (AC5). Single test file `tests/test_cycle65_sandbox_hardening.py` with two test classes (one per AC).

---

## Cluster C — `_validate_page_id` hardening (AC6, AC7, AC8)

### Approach C1 (default — three sequential edits)

Three independent guards added to `_validate_page_id`:
1. Trailing-dot/space rejection (`segment.rstrip(". ")` comparison) — before resolve()
2. Windows-illegal char rejection (`:`, `<`, `>`, `"`, `|`, `?`, `*`) — extend `_CTRL_CHARS_RE` or new `_WINDOWS_ILLEGAL_CHARS_RE`
3. `..` substring → segment-aware split

**Tradeoffs:** straightforward. Each guard is ~3 lines. Tests parametrize over rejection cases.

### Approach C2 (single normalisation pass — strict mode)

Replace the entire validator with a "normalize then compare" approach:
```python
def _normalize_page_id(page_id: str) -> str:
    """Apply all OS-level normalizations Windows would apply."""
    parts = page_id.replace("\\", "/").split("/")
    return "/".join(p.rstrip(". ") for p in parts)

if _normalize_page_id(page_id) != page_id:
    return "page_id contains characters that would be silently normalized by the OS."
```

**Tradeoffs:** ONE check covers AC6 AND AC8. AC7 (Windows illegal chars) still separate. Conceptually cleaner but breaks the existing per-check error message granularity.

### Approach C3 (re-use `kb.utils.text.yaml_sanitize`)

The project already has `kb.utils.text.yaml_sanitize` for control chars. Extend that helper to be the single normalize + reject point.

**Tradeoffs:** consolidation across modules, but `yaml_sanitize`'s contract is YAML escaping — not filename safety. Forcing dual-use risks future regressions where YAML rules and filename rules diverge.

### Recommendation: **C1**.

Three independent guards, each with a specific error message that helps the MCP client correct their input. AC8's segment-aware match is independent of AC6/AC7 and doesn't conflict. The shared regression test file `tests/test_cycle65_validate_page_id.py` parametrizes over all rejection classes.

---

## Cluster D — Validator-contract consolidation (AC9, AC10, AC23)

### Approach D1 (default — extract canonical helper)

NEW `src/kb/utils/path_safety.py`:
```python
def assert_under_project_root(
    path: Path,
    field_name: str,
    *,
    require_exists: bool = False,
    require_dir: bool = False,
    dual_anchor: bool = True,
    allow_symlinks: bool = False,
) -> None:
    """Single canonical containment check. Migrate the three sibling validators."""
```
Migrate `mcp/app.py:121`, `mcp/app.py:230`, `compile/compiler.py:645` to delegate.

**Tradeoffs:** clean. Risk: subtle behavior diff if any existing validator does something the helper misses. Step 9 must capture the EXACT current contract of each before migrating.

### Approach D2 (canonical helper + decorator pattern)

Same as D1, plus a `@requires_under_project_root("field_name")` decorator that wraps MCP tool entry points and applies the check on a named parameter.

**Tradeoffs:** ergonomic for new MCP tools. BUT: introduces magic — a new contributor must know the decorator exists. Same-class peer scan still required (AC23). Decorator adds cycle-N+1 risk where someone forgets it.

### Approach D3 (don't extract — add a docstring contract test)

Keep the three validators but add a regression test that asserts they all pass the same battery of test inputs. No code consolidation, just behavioral parity.

**Tradeoffs:** minimal code churn, but doesn't close the "future fourth caller adopts weakest" threat. Reject D3.

### TOCTOU strategy for AC10

Two options:
- **D-TOCTOU-a:** Re-resolve path immediately before each `unlink`/`write_text` call. Tight loop attacker still has a window but it's microsecond-scale.
- **D-TOCTOU-b:** Use kernel-level `O_NOFOLLOW` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows). Atomic — kernel rejects symlink follow. Requires `os.open(path, flags)` instead of `Path.unlink()`.

D-TOCTOU-b is the correct choice. D-TOCTOU-a still has a race; D-TOCTOU-b closes it at the kernel.

### Recommendation: **D1 + D-TOCTOU-b**.

`path_safety.py` keeps the helper centralized. AC10's TOCTOU fix uses `os.open(path, os.O_NOFOLLOW | os.O_RDONLY)` (POSIX) and `FILE_FLAG_OPEN_REPARSE_POINT` (Windows). Test C9 (`test_symlink_swap_rejected`) uses `monkeypatch.setattr(Path, "unlink", swap_then_unlink)` to inject the swap.

AC23 (the AST-walk meta-test) lands as a separate commit so it can be enforced independent of the helper migration.

---

## Cluster E — URL filter (AC12)

### Approach E1 (default — new helper, full re-implementation)

NEW `src/kb/ingest/url_filter.py` with `_is_safe_url(url) -> bool` reimplementing scheme allowlist + DNS resolve + IP class check.

**Tradeoffs:** isolated, easy to test. BUT: violates DRY — `lint/fetcher.py::SafeBackend` already does this. Per cycle-23 L2 / cycle-15 L1, dead duplication is a bug not a style choice. Also: a re-implementation might MISS a check the existing `SafeBackend` has (e.g., `is_reserved`, `is_multicast`, `is_unspecified` per fetcher.py:122-124).

### Approach E2 (RECOMMENDED — extend existing SafeBackend with scheme gate)

The "real gap" per BACKLOG drift correction is just the scheme allowlist. Extend `_url_is_allowed` (or add a sibling `_url_scheme_allowed`):
```python
def _url_scheme_allowed(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}
```
Gate at `lint/augment/orchestrator.py:248` (URL chokepoint) and inside `_url_is_allowed`. Reuse the entire DNS+IP defense from `SafeBackend` unchanged.

**Tradeoffs:** small surface change, no DRY violation, leverages existing battle-tested code. Risk: future ingest paths (cycle-66+) outside `lint/augment/` need to ALSO call `_url_scheme_allowed`. Mitigation: document at module top + add to AC23-style same-class peer scan.

### Approach E3 (move SafeBackend to a shared module)

Move `SafeBackend` and `_url_is_allowed` from `lint/fetcher.py` to a new `kb/utils/url_safety.py`. Add scheme check there. Both `lint/augment/` and (future) `ingest/` import from the shared module.

**Tradeoffs:** future-proof, larger refactor (cycle 65 scope creep). Reject for now; revisit when a second consumer materializes.

### Recommendation: **E2**.

Smallest change, leverages existing defense, fits the BACKLOG drift correction. AC12 reduces to: (a) add `_url_scheme_allowed` helper, (b) gate at orchestrator URL entry, (c) parametrized test exercising file://, gopher://, data://, javascript:// rejection (per C11 in the threat model).

If Step 5 design gate disagrees and wants E3 for future-proofing, that's a defensible call. E1 should be rejected — it's the most code for the least gain.

---

## Cluster F — Dependency hardening (AC11, AC15, AC18)

### Approach F1 (default — three independent edits)

- AC11: pin `GitPython==3.1.47,<3.2` in `requirements.txt` directly
- AC15: set `os.environ["TRAFILATURA_DOWNLOAD_NO_CACHE"] = "1"` at top of `lint/fetcher.py`
- AC18: NEW `tests/test_security_cve_greps.py` with subprocess greps OR Python-re scans

**Tradeoffs:** minimal. Each AC is 1-3 lines. Independent commits possible.

### Approach F2 (consolidate via a new `kb.security` namespace module)

Create `src/kb/security/runtime_guards.py` with:
```python
def install_runtime_guards():
    """Apply runtime safety env vars and sanity checks at module import."""
    os.environ.setdefault("TRAFILATURA_DOWNLOAD_NO_CACHE", "1")
    # Future: HTTPX_DISABLE_HSTS_PRELOAD, REQUESTS_CA_BUNDLE warnings, etc.
```
Called from `kb/__init__.py`.

**Tradeoffs:** centralized, ergonomic for future expansion. BUT: cycle 65 has only ONE such guard (AC15); creating a namespace module for one item is YAGNI. Defer.

### Approach F3 (move SECURITY.md greps to a YAML manifest)

Replace SECURITY.md table with `wiki/_security/cve_acceptance.yml`:
```yaml
- package: diskcache
  advisory: CVE-2025-69872
  greps: ["diskcache", "DiskCache", "FanoutCache"]
  rationale: ...
```
Test reads YAML, runs greps. SECURITY.md auto-renders from the YAML.

**Tradeoffs:** machine-parseable, single source of truth. BUT: introduces a YAML parsing dep (we already have `python-frontmatter`/`pyyaml`). Larger change for cycle 65; defer to cycle-66+ if pattern repeats.

### Recommendation: **F1** with a small adjustment.

For AC15, prefer `os.environ.setdefault(...)` (not unconditional set) so a developer's existing env override wins. For AC18, prefer Python-`re` scanning over subprocess `grep` (cross-platform parity per threat-model dependencies note).

---

## Cluster G — MCP error sanitisation (AC14, AC16, AC21, AC22)

### Approach G1 (default — per-AC edits)

- AC14: wrap `sqlite_vec.load(conn)` in try/except in `query/embeddings.py`
- AC16: rewrite `_check_no_secrets_on_argv` value-based
- AC21: add `_mcp_error_boundary` decorator/wrapper on each tool in `mcp/{core,ingest,quality}.py`
- AC22: add CI grep step to `.github/workflows/ci.yml`

**Tradeoffs:** independent, matches the threat-model 1:1.

### Approach G2 (decorator factory shared across AC14 + AC21)

```python
@boundary(redact_paths=True)
def kb_query(...):
    ...
```
The `boundary` decorator catches `Exception`, sanitizes via `sanitize_error_text`, and (for AC14) also catches `OperationalError` with custom message.

**Tradeoffs:** elegant. BUT: `query/embeddings.py::VectorIndex.build` is NOT an MCP tool — applying the same decorator there is wrong abstraction. The two are different threats (sqlite-vec path leak vs general MCP error path). Don't conflate.

### Approach G3 (per-MCP-tool boundary + per-call try/except for sqlite_vec)

Same as G1, but explicitly: AC14's try/except is INSIDE `VectorIndex.build()`, not at the MCP boundary. AC21's boundary is at the MCP `@mcp.tool()` decorator level.

**Tradeoffs:** clear separation. The error from `sqlite_vec.load` is re-raised as a sanitized `RuntimeError`, which then flows up through `query_wiki` MCP tool and gets caught by AC21's boundary (which formats it for the client). Defense in depth.

### Recommendation: **G3**.

Two concentric layers: AC14 at the data layer (sqlite-vec specific), AC21 at the MCP boundary (catch-all). AC16 is independent (CLI subprocess hardening, not MCP). AC22 is a CI workflow change.

For AC21, the boundary handler should be a context manager rather than a decorator, because some MCP tools have multiple early returns and a context manager wraps the whole body without changing return statements. Or, alternatively, a simple decorator that wraps the function. Step 5 design gate decides.

---

## Cluster H — Drift guards + hygiene (AC13, AC17, AC19, AC20)

### Approach H1 (default)

- AC13: `file_lock(db_path.with_suffix(".db.lock"))` around `VectorIndex.build` DROP/CREATE/INSERT/COMMIT
- AC17: `__all__ = []` in `graph/cache.py` + AST-walk test
- AC19: paired negative-control snapshot tests
- AC20: NEW `docs/reference/INDEX.md` + AST-walk test

**Tradeoffs:** independent, low-risk.

### Approach H2 (combined cache-discipline test)

AC17 + AC4 + AC23 share an AST-walk test infrastructure (`tests/_helpers/ast_walk.py`). Single helper module with `find_imports_from(module, name)`, `find_function_def(file, name)`, etc. All three tests use it.

**Tradeoffs:** DRY win. Test code is small (~20-40 lines per test) so consolidation is helpful.

### Approach H3 (auto-generate INDEX.md from frontmatter)

For AC20, the meta-test asserts `docs/reference/INDEX.md` exists AND every `*.md` (excluding INDEX.md, README.md) is listed. The INDEX.md content can be:
- Manually maintained
- Auto-generated from frontmatter at build time
- Generated lazy on `kb publish` (treated as build artifact)

**Tradeoffs:** auto-generation is more work, but lower drift risk. For cycle 65, hand-author + meta-test (manual + checked) is the smallest change. Future cycle can add `kb docs index` CLI generator.

### Recommendation: **H1 + H2**.

Use a shared `tests/_helpers/ast_walk.py` for AC4, AC17, AC23 (and any other AST-checking test). AC13/AC19/AC20 are independent. INDEX.md hand-authored + meta-test for cycle 65; defer auto-generation.

---

## Cross-cutting opportunities (synthesized)

1. **Shared AST-walk test helper** — `tests/_helpers/ast_walk.py` consumed by AC4 (conftest decorator), AC17 (graph/cache from-imports), AC23 (path_safety callers), AC20 (INDEX.md ↔ files cross-reference). One place to fix when ast.parse semantics change.

2. **Shared `tests/test_cycle65_config_call_time.py`** — covers AC1, AC2, AC3 with one parametrized test class. Each test sets env, imports kb.config, monkeypatches setenv, asserts accessor reflects new value.

3. **Shared `tests/test_cycle65_validate_page_id.py`** — covers AC6, AC7, AC8 with parametrized rejection cases.

4. **Shared regression test for snapshot tautology + CVE greps** — AC18 + AC19 are both "subprocess + grep against repo". They could share a `subprocess` runner helper but the divergent pytest assertions don't justify the abstraction. Keep separate.

---

## Threats the threat model might be missing

1. **MCP `_mcp_error_boundary` ALSO leaks via the local log** — AC21 logs full traceback "locally" via `_LOG.exception(...)`. If the project ever ships logging-to-stderr-by-default OR a future MCP client subscribes to the server's stderr, the local log becomes remote-readable. Mitigation: log to a file under `.data/` (not stderr) and document.

2. **`_check_no_secrets_on_argv` value-based check (AC16) misses key-derivative secrets** — if a user prompts "my MCP_AUTH=$(echo $ANTHROPIC_API_KEY | base64)", the literal env value is no longer in the argv. Mitigation: out of scope for cycle 65 (acceptable — original threat is regex over-trigger, not key derivation).

3. **`__all__ = []` (AC17) does NOT prevent `import kb.graph.cache as gc; gc.get_graph(...)`** — the threat is closed at the `from-import` level only. Mitigation: AC17's AST-walk also catches `Import(names=[alias(name="kb.graph.cache", asname=...)])` AND any subsequent attribute access in the same file. (Or accept the gap — `import as` is rare in this codebase.)

4. **CI grep step for `sk-ant-dummy` (AC22) bypassable via base64-encoded snapshots** — if a future test serializes the dummy key into a base64 cassette field, the grep misses. Mitigation: also grep for `c2stYW50LWR1bW15` (base64 of "sk-ant-dummy"). Out of scope for cycle 65 baseline.

These are notes for Step 5 design gate consideration, not blocking Step 7 plan.

---

## Recommended cycle structure for Step 7 plan

Order of file-grouped commits (per `feedback_batch_by_file`):

1. **Foundation commit** — `tests/_helpers/ast_walk.py` (new helper) — needed by AC4, AC17, AC23.
2. **Config call-time accessors** — AC1, AC2, AC3 (single commit on `config.py` + migrate `kb.utils.llm`).
3. **Sandbox guards** — AC4, AC5 (single commit on `tests/conftest.py` + new test).
4. **Page-id hardening** — AC6, AC7, AC8 (single commit on `mcp/app.py`).
5. **Path-safety helper + migration** — AC9, AC10, AC23 (single commit; canonical helper + migrations + meta-test).
6. **URL scheme allowlist** — AC12 (single commit on `lint/augment/`).
7. **Dependency pinning** — AC11 (`requirements.txt`) + AC15 (`lint/fetcher.py`) + AC18 (`tests/test_security_cve_greps.py`) (one commit per file).
8. **MCP error boundary** — AC14 (`query/embeddings.py`), AC16 (`utils/cli_backend.py`), AC21 (`mcp/{core,ingest,quality}.py`) (one commit per file).
9. **CI grep guard** — AC22 (`.github/workflows/ci.yml`).
10. **Hygiene** — AC13 (`query/embeddings.py` file_lock), AC17 (`graph/cache.py` __all__), AC19 (`tests/test_cycle64_snapshots.py` negative controls), AC20 (`docs/reference/INDEX.md`).

That's ~10 commits across ~14 files, with each commit small enough to revert independently.

---

## Awaiting DeepSeek brainstorm output

DeepSeek V4 Pro is running a parallel brainstorm with bias toward non-obvious / contrarian / cross-cutting alternatives. Step 4 (Design eval) will compare convergent + divergent suggestions and feed both into Step 5 design decision gate.
