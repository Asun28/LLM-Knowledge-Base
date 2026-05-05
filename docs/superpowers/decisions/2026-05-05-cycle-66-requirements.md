# Cycle 66 — Requirements + Acceptance Criteria

**Date:** 2026-05-05
**Branch:** `feat/cycle-66` (off `main` @ `6e4a6ba` — docs FORMAT GUIDE landing)
**Pipeline:** `/dev-mimo-opus`
**Step:** 1 of 24

---

## Tier

**Tier 2 — standard feature.** Full pipeline 1-24 runs.

**Rationale.** The five candidate items are HARDENING/CLEANUP of existing security primitives — none introduce new trust boundaries:

- AC1 removes a dead `__getattr__` branch and corrects a misleading comment (signature-preserving — module binding at line 107 already shadows the branch).
- AC2 expands an existing scrub list to source from `kb.config.CLI_BACKEND_ENV_INJECT` (additive coverage; no scrub mechanism change).
- AC3 caches the heuristic walk-up of `_resolve_project_root()` (perf only; semantics preserved by cache key including env + cwd).
- AC4 collapses 4 redundant filesystem walks into 1 (perf + readability; assertion semantics preserved).
- AC5 removes a redundant `allow_symlinks` kwarg from `_assert_under_project_root` (signature simplification; symlink rejection becomes unconditional, matching every existing call site's already-default behavior).

Item AC2 is the closest to Tier 3 territory (env-var handling + secrets) but is **purely additive** — it expands scrub coverage to keys (Gemini/Kimi/Qwen/Zai/ZhipuAI) currently leaking. User's `feedback_auto_approve` memory authorises Opus subagent gating without human checkpoints; Tier 2 fits.

When in doubt go up — but in this case the doubt is small enough that the Tier 3 manual-merge cost (a SOC-2 audit-style human gate at Step 5 + Step 20 R2) outweighs the marginal benefit on changes that all close existing gaps without expanding any boundary.

---

## Pre-cycle state snapshot

- **Test baseline:** 3134 passed + 21 skipped / ~213 files (CLAUDE.md Quick Reference, cycle-65 branch HEAD post-Step-12 fix-cascade).
- **CVE baseline:** 2 known accepted CVEs on `main` post PR #92 (diskcache `CVE-2025-69872` / `GHSA-w8v5-vhqr-4h9v` pickle-deserialization RCE — no fix version available; pip `CVE-2026-3219` / `GHSA-58qw-9mgm-455v` tar/ZIP confusion — no fix version available). PR #92 closed alerts #12-#15 by removing ragas + the `litellm` distribution and declaring `scipy` direct; the diskcache + pip pair remains as the accepted-with-mitigation baseline (see `SECURITY.md`).
- **Open BACKLOG cycle-66 candidates:** 5 (3 MEDIUM + 2 LOW), all flagged as cycle-65 Step-10 simplify findings deferred at Step-12 merge time.

---

## Scope

### In scope

Five items from `BACKLOG.md` § "Cycle 66 candidates (2026-05-04, surfaced by cycle-65 reviews)":

| # | Severity | File | Symbol | Concern |
|---|----------|------|--------|---------|
| 1 | MEDIUM | `src/kb/config.py` | `__getattr__("PROJECT_ROOT")` | Dead branch (shadowed by module binding at line 107); misleading comment block at 760-769 implies the shim is the active route. |
| 2 | MEDIUM | `src/kb/utils/cli_backend.py` | `_check_no_secrets_on_argv` | Hardcoded 6-key list misses the Gemini/Kimi/Qwen/Zai/ZhipuAI keys that `kb.config.CLI_BACKEND_ENV_INJECT` exposes — argv leak risk for any backend whose key isn't in the local list. |
| 3 | MEDIUM | `src/kb/config.py` | `get_project_root` / `_resolve_project_root` | Per-call cost on the MCP boundary path (`_validate_page_id` → `_assert_under_project_root` → `get_project_root`): ~6 syscalls per MCP call when env is unset. |
| 4 | LOW | `tests/test_security_cve_greps.py` | (4 test methods) | 4 separate `rglob("*.py")` walks read every `src/kb/` file 4 times (~600 file reads vs ~150 for a single walk). |
| 5 | LOW | `src/kb/utils/path_safety.py` | `_assert_under_project_root` | `allow_symlinks: bool = False` kwarg never overridden by any caller (verified: 1 production caller in `compile/compiler.py:672`, 0 test callers, 0 hits across `src/`). |

### Out of scope (deferred)

- **Larger PEP 562 redesign** (BACKLOG fix-option-b: replace module-level `PROJECT_ROOT = _resolve_project_root()` with `LazyPathProxy` re-reading on every attribute access). Touches 200+ `from kb.config import PROJECT_ROOT` snapshot callers — needs migration plan. Cycle 67+ candidate.
- **`kb.config._DEFAULT_MODEL_TIERS` dual-mechanism removal** (Phase 6 R2 MEDIUM `mimo r5 Q1, Q2`). Captures `os.environ.get(CLAUDE_*_MODEL)` at IMPORT time. Same hazard class as AC3 but a separate item.
- **`mcp_server.py` shim removal** (Phase 6 R2 LOW `mimo r1 Q5`). Two bootstrap paths for `mcp.app:main`. Cycle 67+ cleanup.
- **Phase 6 R2 BACKLOG hygiene** — many Phase 6 R2 items shipped in cycle 65 (AC11 GitPython pin, AC12 URL scheme allow-list, AC13 file_lock, AC14 sqlite-vec sanitization, AC16 cli_backend value-based scrub, AC17 graph cache __all__, AC18 banned-import test, AC19 snapshot warn-unused, AC20 INDEX.md, AC21 error boundary, AC22 sk-ant-dummy guard) but the BACKLOG entries weren't pruned. Step 17 doc-update may touch this opportunistically; not gated by an AC.

### Why this small scope

- Five items fit the cycle-65 Step-10 deferral set exactly — no scope creep.
- 5 ACs is well under user's `feedback_batch_by_file` 30-40 target, but these were a coherent surfaced set rather than a fresh BACKLOG sweep. Larger BACKLOG batches can resume in cycle 67.
- Below the cycle-16 L4 R3-trigger threshold (≥25 ACs) on count alone, but **AC2 is a NEW security enforcement point** (covering keys not previously scrubbed), which means R3 may be triggered per cycle-16 L4 condition (c). Reassess at Step 20.

---

## Acceptance Criteria

### AC1 — Remove dead `kb.config.__getattr__("PROJECT_ROOT")` branch

**Diff scope:** `src/kb/config.py` lines 760-776 only.

**Change:** Delete the `if name == "PROJECT_ROOT": return get_project_root()` branch from `__getattr__` (currently lines 772-773). Rewrite the comment block at lines 760-769 to reflect actual behaviour:
- `PROJECT_ROOT` is bound at module load (line 107) — attribute access returns that binding.
- `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp)` mutates the module dict; `get_project_root()`'s `globals().get("PROJECT_ROOT")` shim picks it up at call time (cycle-65 Step-12 fix).
- The `__getattr__` shim retains the `AUGMENT_ALLOWED_DOMAINS` branch (which IS live — the name is not bound at module level).

**Behavioral preservation (must hold post-AC1):**
- `kb.config.PROJECT_ROOT` attribute access returns the module binding (unchanged).
- `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)` is observed by every call to `kb.config.get_project_root()` (unchanged — flows through `globals().get`).
- `KB_PROJECT_ROOT` env-var override is observed (unchanged — flows through line 64-66).

**Test (AC1):** Add a behavioral regression in `tests/test_cycle66_config_pep562.py` that:
- Monkeypatches `kb.config.PROJECT_ROOT` → `tmp_path`, asserts `kb.config.get_project_root() == tmp_path`.
- Reverts production by replacing `__getattr__` body with a `raise AttributeError` for any name → test still passes (proves the test exercises the module-binding path, not the dead branch).

### AC2 — `_check_no_secrets_on_argv` sources keys from `CLI_BACKEND_ENV_INJECT`

**Diff scope:** `src/kb/utils/cli_backend.py` lines 138-148 (the hardcoded `_SCRUB_KEYS` list).

**Change:** Replace the hardcoded 6-key list with:
```python
_SCRUB_KEYS = frozenset(
    {"ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY", "MIMOCODING_API_KEY", "MIMOCHAT_API_KEY"}
    | {key for keys in CLI_BACKEND_ENV_INJECT.values() for key in keys}
)
```
(Standalone keys: ANTHROPIC, FIRECRAWL, MIMOCODING, MIMOCHAT — these are not in any `CLI_BACKEND_ENV_INJECT` backend tuple. The previously-hardcoded OPENAI and DEEPSEEK keys are subsumed by `CLI_BACKEND_ENV_INJECT["openai"]` and `CLI_BACKEND_ENV_INJECT["deepseek"]` respectively.)

**Verified at Step 1 grep-time:** `kb.config.CLI_BACKEND_ENV_INJECT` (config.py:329-338) maps backend → key tuples. Value-union: `{GEMINI_API_KEY, OPENAI_API_KEY, KIMI_API_KEY, QWEN_API_KEY, DEEPSEEK_API_KEY, ZAI_API_KEY, ZHIPUAI_API_KEY}` (7 distinct keys; ollama backend tuple is empty).

**Post-AC2 `_SCRUB_KEYS` set (11 keys total):**
- 6 standalone keys preserved: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, `DEEPSEEK_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`.
- 5 NEW keys (CLI_BACKEND_ENV_INJECT-only, currently leak-prone): `GEMINI_API_KEY`, `KIMI_API_KEY`, `QWEN_API_KEY`, `ZAI_API_KEY`, `ZHIPUAI_API_KEY`.
- (OPENAI and DEEPSEEK appear in both sources; `frozenset.union` collapses them.)

**Behavioral preservation (must hold post-AC2):**
- All 6 currently-listed keys remain scrubbed.
- Per-backend scrub coverage extends to whatever `CLI_BACKEND_ENV_INJECT` exposes (Gemini, Kimi, Qwen, Zai, ZhipuAI — exact list confirmed at design-eval).
- Substring-containment scrub mechanism (cycle-65 AC16 + Step-09 DeepSeek BLOCKER-1 fix) unchanged.

**Test (AC2):** In `tests/test_cycle66_secret_scrub.py`:
- Parametrized over every key in the post-AC2 `_SCRUB_KEYS` frozenset.
- Each parameter sets the env var to a sentinel via `monkeypatch.setenv`, calls `_check_no_secrets_on_argv` with `[..., sentinel, ...]`, asserts `pytest.raises(LLMError)` with `match="(?i)refusing to place env secret"` (matches the existing `LLMError(kind="invalid_request")` raised at cli_backend.py:156-159; substring match avoids drift from later wording tweaks).
- Paired negative control: same test with sentinel **NOT** matching the env value passes (no false positive).
- Divergent-fail check: revert AC2 (restore hardcoded 6-key list) → newly-covered keys fail.

### AC3 — `get_project_root()` per-call cost cache

**Diff scope:** `src/kb/config.py` lines 15-82.

**Change:**
- Add module-level `_HEURISTIC_CACHE: tuple[Path, Path] | None = None` storing `(cwd, resolved_root)`.
- In `_resolve_project_root()`: after the env-read block (which short-circuits early when env is set — caching that path adds no value), the heuristic walk-up portion checks the cache first and returns the cached value if `cwd` matches; otherwise computes and stores.
- `_reset_project_root()` clears `_HEURISTIC_CACHE` (was a no-op stub).
- Document: cache only applies to the heuristic fallback path. Tests that mutate env via `monkeypatch.setenv("KB_PROJECT_ROOT", ...)` do NOT need to call `_reset_project_root()` (env is checked before cache).
- Tests that mutate `cwd` between calls without changing env are auto-handled (cache key includes `cwd`).

**Open design questions for Step 3-5:**
- Cache by `(cwd, _has_env)` or just `cwd`? — env is short-circuited above the cache, so just `cwd` suffices.
- Use `functools.lru_cache(maxsize=8)` or hand-rolled? Hand-rolled wins for explicit `_reset_project_root()` invalidation.
- Thread-safety? `_HEURISTIC_CACHE` reads/writes are atomic enough for CPython (single rebinding) but a `threading.RLock` makes it explicit. Decide at Step 5.

**Behavioral preservation (must hold post-AC3):**
- All existing `get_project_root()` callers see the same return value (within a single cwd) as before.
- `monkeypatch.setenv("KB_PROJECT_ROOT", tmp)` continues to work (env is read before cache).
- `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp)` continues to work (module binding is read before cache).

**Test (AC3):** In `tests/test_cycle66_project_root_cache.py`:
- Hit-then-miss test: 1st call invokes heuristic, 2nd call returns same value without invoking (spy on `Path.cwd` to count invocations).
- Reset clears cache: `_reset_project_root()` then re-call → fresh heuristic invocation.
- env-override bypasses cache: setenv KB_PROJECT_ROOT → returns env value regardless of cache.
- Module-binding override bypasses cache: monkeypatch.setattr `PROJECT_ROOT` → returns binding regardless.
- Divergent-fail: revert AC3 (drop caching) → hit-then-miss test fails (heuristic invoked twice).

### AC4 — `tests/test_security_cve_greps.py` 4-walk consolidation

**Diff scope:** `tests/test_security_cve_greps.py` lines 25-95 (the 4 test methods, each with its own rglob).

**Change:** Collapse to one `_walk_kb_for_banned_imports()` helper that:
- Runs `rglob("*.py")` once.
- For each file, runs `find_imports_from(...)` from `tests/_helpers/test_ast_walk.py` (or equivalent AST walker — already used by cycle-65 AC4/AC17/AC18/AC23).
- Returns a dict `{module_name: list[str]}` of files importing each banned module.
- 4 individual test methods become 4 parametrized `pytest.mark.parametrize` cases over `[diskcache, litellm, pip, ragas]` that each consume the shared dict.

**Behavioral preservation (must hold post-AC4):**
- Each banned import (diskcache, litellm, pip, ragas) is still rejected if introduced.
- Test count delta: 4 → 4 (parametrized, count preserved).
- File reads: ~600 → ~150 (one rglob + one parse per file, results cached across the 4 assertions).

**Test (AC4):** Behavioural — paired negative-control fixture per banned module. Add a test that:
- Writes a temp `tmp_path/_test_only.py` with `import diskcache` (each banned in turn).
- Runs the consolidated walk over the temp tree, asserts the file appears in the banned dict.
- Demonstrates the AST walker actually catches imports vs ad-hoc grep.

### AC5 — Drop `allow_symlinks` kwarg from `_assert_under_project_root`

**Diff scope:** `src/kb/utils/path_safety.py` lines 30-100.

**Change:**
- Remove `allow_symlinks: bool = False` from signature (line 37).
- Remove `allow_symlinks: If False (default), raise if the path is a symlink.` from docstring (line 50).
- Body: `if not allow_symlinks and path.is_symlink():` → `if path.is_symlink():` (line 99). Symlink rejection becomes unconditional.
- Comment update: note that Q2.2 hard-cap of 4 kwargs (cycle-65) drops to 3, freeing namespace for a future param if needed.

**Caller verification:**
- Only production caller: `compile/compiler.py:672` — uses `_assert_under_project_root(path, field_name, dual_anchor=True)` (no `allow_symlinks`). Unchanged.
- Test callers: zero (grep `tests/` for `allow_symlinks` returns no matches).

**Behavioral preservation (must hold post-AC5):**
- Symlink rejection still fires (was always-on; now structurally always-on).
- `_assert_under_project_root` signature: 4 kwargs → 3 kwargs (`require_exists`, `require_dir`, `dual_anchor`).

**Test (AC5):** Add `tests/test_cycle66_path_safety_symlink.py`:
- Behavioral: create a symlink under `tmp_path`, call `_assert_under_project_root(symlink_path, "field")`, assert `ValueError` raised. (Already covered by cycle-65 tests but recheck under new signature.)
- Signature pin: `inspect.signature(_assert_under_project_root)` parameter set excludes `allow_symlinks`. (Note: cycle-7 L4 hazard — this is signature-only — but coupled with the behavioral test it's belt-and-suspenders, not vacuous.)
- Caller pin: `compile/compiler.py::_validate_path_under_project_root` still raises `ValidationError` on a symlink path (transitive via the helper).

### AC6 — Test infrastructure: cycle-66 file split

Each AC's tests live in a dedicated file under `tests/`:
- `tests/test_cycle66_config_pep562.py` (AC1)
- `tests/test_cycle66_secret_scrub.py` (AC2)
- `tests/test_cycle66_project_root_cache.py` (AC3)
- `tests/test_cycle66_cve_greps_consolidated.py` (AC4)
- `tests/test_cycle66_path_safety_symlink.py` (AC5)

Allow shared helpers in `tests/_helpers/` (existing `test_ast_walk.py` reused for AC4).

### AC7 — BACKLOG.md cleanup + docs

Step 17 (doc-update) action — not a code AC but explicitly enumerated to prevent drift:
- **Delete** the `## Cycle 66 candidates (2026-05-04, surfaced by cycle-65 reviews)` section from `BACKLOG.md` (lines 27-46).
- Compact entry in `CHANGELOG.md` `[Unreleased]` Quick Reference (Items / Tests / Files / Scope / Detail one-liner per FORMAT GUIDE).
- Full per-AC detail in `CHANGELOG-history.md` newest-first.
- Update `CLAUDE.md` Quick Reference test count post-Step-12.
- Update `docs/reference/error-handling.md` to note Q2.2 kwarg cap is now 3 not 4 (after AC5).

---

## Test-count contract

- **Pre-cycle:** 3134 passed + 21 skipped.
- **Post-cycle target:** 3134 + N new tests (where N ≥ ~12, distributed across AC1-AC5 test files); 21 skipped baseline preserved.
- **Hard floor:** 0 newly-failing or newly-skipped pre-existing tests (cycle-22 L3 full-suite gate).
- **AC4 count delta:** 0 (4 methods → 4 parametrized cases).

---

## Cross-references

- `BACKLOG.md` lines 27-46 (the 5 candidates).
- `CHANGELOG.md` Unreleased Quick Reference (cycle-65 entry — lists the 5 deferrals at end of paragraph).
- `docs/superpowers/decisions/2026-05-04-cycle-65-design.md:50` (Q2.2 kwarg hard-cap origin).
- `docs/superpowers/decisions/2026-05-05-cycle-65-step24-self-review.md:185` (5-deferrals capture).
- Memory: `feedback_test_behavior_over_signature`, `feedback_inspect_source_tests`, `feedback_batch_by_file`, `feedback_auto_approve`, `project_cycle61_mimo_failure`.

---

## Step 1 closure checklist

- [x] Tier classified (Tier 2) with rationale.
- [x] All 5 BACKLOG items grep-verified against current source (none stale; item #5 caller-count revised down from 3 to 1).
- [x] ACs numbered AC1-AC7 (5 code + 1 test infra + 1 doc).
- [x] Each code AC has: diff scope, change spec, behavioral preservation list, test contract.
- [x] Out-of-scope items enumerated (deferred to cycle 67+).
- [x] Pre-cycle test baseline recorded.
- [x] Cross-references to source-of-truth docs.

→ Proceed to Step 2 (threat model + dep-CVE baseline).
