# Cycle 66 — Design Eval R1 (Opus)

**Date:** 2026-05-05
**Branch:** feat/cycle-66
**Step:** 4 of 24 (Round 1 of 2 — parallel with R2 DeepSeek)
**Reviewer:** Opus 4.7 subagent (cross-family R2 = DeepSeek V4 Pro)
**Inputs:** requirements.md, threat-model.md, brainstorm.md

## Analysis

Independent score against the four axes (behavioral preservation, test coverage, implementation effort, future-proofing) before reconciling with the brainstorm's "lean" column. Source files fact-checked:

- `src/kb/config.py:15-82` (`_resolve_project_root`, `get_project_root`, `_reset_project_root` stub) and `:760-776` (`__getattr__` PEP 562 shim).
- `src/kb/utils/cli_backend.py:123-159` (`_check_no_secrets_on_argv` with the literal 6-key list).
- `src/kb/utils/path_safety.py:13` (Q2.2 4-kwarg hard-cap docstring), `:30-100` (validator), `:103-153` (`_open_no_follow`).
- `tests/test_security_cve_greps.py:18-84` (4 separate `rglob`-walks with regex match).
- `tests/_helpers/ast_walk.py:7-40` (`find_imports_from` ImportFrom-only).
- `tests/_helpers/test_ast_walk.py:14-41` (the three `TestFindImportsFrom` cases are stubs — they create temp files but **never invoke** `find_imports_from`; only the function-def + calls-of cases at `:43-100` exercise their helpers).
- `src/kb/compile/compiler.py:672` (sole production caller of `_assert_under_project_root`; passes `dual_anchor=True` only).

The brainstorm's lean column matches this fact base. I reconcile below.

### AC1 — Independent walk-through

The dead-branch claim checks out: `PROJECT_ROOT = _resolve_project_root()` at `config.py:107` puts the name in the module dict, so PEP 562 only fires for names NOT in the dict. The branch at `:772-773` is provably unreachable on attribute access. The misleading comment block at `:760-769` claims "the shim fires if the attribute is not in the module dict, returning the fresh call-time value" — true in general, but the comment then names `PROJECT_ROOT` as the example, which is exactly the case where the shim does NOT fire. The comment is actively wrong and worth fixing as part of this AC.

`get_project_root()` at `:48-73` already does the work the comment claims `__getattr__` does: env first, then `globals().get("PROJECT_ROOT")` (which honors monkeypatch.setattr), then heuristic. That is the live path; PEP 562 is dead weight today.

Risk axes:
1. **Behavioral preservation** — perfect. No production observable changes.
2. **Test coverage** — the brainstorm's divergent-fail design (mutate `__getattr__` body to raise `AttributeError` for any name, assert `get_project_root()` still returns the monkeypatched value) is exactly the right shape. Implementation subtlety: `monkeypatch.setattr(kb.config, "__getattr__", new_fn)` may not behave as expected because Python module-level `__getattr__` is a special-method lookup. Worth flagging at Step 9 if the test pattern doesn't behave as expected (fall back to direct binding `kb.config.__getattr__ = new_fn` with explicit teardown).
3. **Implementation effort** — ~10 minutes.
4. **Future-proofing** — Option B (LazyPathProxy) is correctly out-of-scope; AC1 is the right minimum. After AC1 the only live PEP 562 branch is `AUGMENT_ALLOWED_DOMAINS` (verified at `config.py:85-104`: `get_allowed_domains()` exists; no `AUGMENT_ALLOWED_DOMAINS = ...` import-time binding).

### AC2 — Independent walk-through

The 6-key hardcoded list at `cli_backend.py:140-147` is exactly what the brainstorm describes. `CLI_BACKEND_ENV_INJECT` at `config.py:329-338` exposes 7 distinct keys across 8 backends (verified: `GEMINI_API_KEY`, `OPENAI_API_KEY` ×2, `KIMI_API_KEY`, `QWEN_API_KEY`, `DEEPSEEK_API_KEY`, `ZAI_API_KEY`, `ZHIPUAI_API_KEY`). The post-AC2 frozenset is 11 keys after dedup (5 net new: GEMINI/KIMI/QWEN/ZAI/ZHIPUAI).

The information-disclosure threat (T2) is real and not hypothetical: the model-override slot at `cli_backend.py:198` already calls `_build_cmd(backend, model)` for every backend, and any future enhancement that puts a key on argv (e.g., `--api-key=$X` style) would silently leak through the gap.

Option A vs Option B (module-level frozenset vs runtime accessor):

- Option A binds the frozenset at IMPORT TIME of `cli_backend.py`. `CLI_BACKEND_ENV_INJECT` lives in `kb.config`, which is imported BY `kb.utils.cli_backend.py`. Python resolves the import order such that `cli_backend` reads `CLI_BACKEND_ENV_INJECT` after `kb.config` finishes initialising. Today, `CLI_BACKEND_ENV_INJECT` is a literal `dict[...]` at `config.py:329-338` with no env-var derivation, so import-time capture is safe.
- Cycle-19 L2 reload-leak hazard applies to env-var-derived constants. `CLI_BACKEND_ENV_INJECT` is NOT env-derived — it is a module-literal dict. Therefore cycle-19 L2 does not apply, and import-time capture (Option A) does not violate it.
- Option B's runtime accessor recomputes the frozenset on every `_check_no_secrets_on_argv` call. The function is on the hot path of `call_cli` (at least 1× per LLM call). Per-call cost is ~7-8 dict iterations + frozenset construction = trivial in absolute terms but unnecessary churn.
- Tests parametrize over `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened — that source IS the canonical map, satisfying the threat-model T4 condition. The parametrize source is independent of `_SCRUB_KEYS`'s computation strategy.

I conclude: Option A is correct. The cycle-19 L2 framing in the brainstorm's Cons column is a false alarm — that hazard targets env-derived constants, not module-literal-derived constants.

Risk axes:
1. **Behavioral preservation** — six pre-existing keys remain scrubbed; new five gain coverage. Substring-containment mechanism preserved.
2. **Test coverage** — parametrize-from-`CLI_BACKEND_ENV_INJECT.values()` (closes T4) plus paired negative-control (sentinel-mismatch passes, closes T3 false-positive) plus divergent-fail (revert frozenset to literal 6-key list → 5 cases fail). That is three layers; sound.
3. **Implementation effort** — ~15 minutes.
4. **Future-proofing** — frozenset auto-extends when a 9th backend is added. The risk is purely the contributor-revert hazard (T4) which the parametrize source closes.

### AC3 — Independent walk-through

The hot-path claim is plausible: `_validate_page_id` (MCP boundary) → `_assert_under_project_root` → `kb.config.get_project_root()`. Today the env-unset case walks up to 6 directories per call (`heuristic / "pyproject.toml"` check, then `Path.cwd().resolve()`, then up to 5 parent levels). For an MCP request that touches multiple page IDs, this multiplies.

Caveat I want to flag: the env-set case at `config.py:18-27` already short-circuits to one `Path(env_root).resolve()` + `is_dir()` call. Most production deployments set `KB_PROJECT_ROOT` (the example .env recommends it), so the cache primarily benefits dev/test scenarios. That is still worth doing, but it is not a 10× production speedup — it is mostly a test-suite speedup. Worth being honest about in the CHANGELOG entry.

Option A (hand-rolled tuple) vs Option B (`lru_cache(maxsize=8)` on inner fn):

- Option A: one `tuple[Path, Path] | None` global. Clear `_reset_project_root()` semantics ("set to None"). Single-entry cache — if `cwd` shifts, the next call recomputes and overwrites. Cycle-19 L2 alignment is automatic because env is read above the cache.
- Option B: `@functools.lru_cache(maxsize=8)` on a `_heuristic_walk_up_cached(cwd_str: str)` inner function. The 8-entry capacity covers pytest-xdist worker patterns. `cache_clear()` is built-in. Splits the function for cleaner unit testing.
- The brainstorm's Cons against Option A ("manual cache-key check in body — slightly more code") and against Option B ("8 entries vs Option A's 1 — marginal extra memory") are both minor.

The decisive factor for me is **test introspection**. The AC3 test contract requires "Hit-then-miss" (spy on `Path.cwd` to count invocations). With Option B, the spy lives on `Path.cwd` AND `_heuristic_walk_up_cached`, giving cleaner assertion semantics ("inner fn called once, cached on second call"). With Option A, the spy must mock `Path.cwd` calls inside `_resolve_project_root` directly. Option B is marginally cleaner for testing.

But Option B has a subtle pitfall: `lru_cache` decorates the inner function at import time. If a test wants to also verify "cache hit returns same Path identity", the cache returns the SAME `Path` instance on hits. Option A returns the SAME instance too (it is the cached tuple's second element), so both options share this property. Neither wins on this axis.

**My independent recommendation: Option B**, agreeing with the brainstorm. Reasons:
- Idiomatic Python — `lru_cache` is what most reviewers reach for first.
- Built-in `cache_clear()` matches `_reset_project_root()` semantics one-to-one.
- 8-entry capacity tolerates pytest-xdist + test-time `os.chdir` without explicit reset.
- Pure-function inner is unit-testable in isolation.

Risk axes:
1. **Behavioral preservation** — cache key is `cwd`; env and module-binding are checked before the cache. Behavior unchanged for every observed access pattern.
2. **Test coverage** — four behavioral assertions (hit-then-miss, reset clears, env override, module-binding override) plus divergent-fail. Sound.
3. **Implementation effort** — ~20-30 minutes for Option B (need to refactor `_resolve_project_root` into env-prefix + cached-inner).
4. **Future-proofing** — Option B handles thread-safety natively. Option A relies on GIL atomicity which is currently true on CPython but might be re-questioned under PEP 703 (free-threading). Option B's `lru_cache` will track free-threading correctness automatically.

### AC4 — Independent walk-through

The `find_imports_from` AST walker at `tests/_helpers/ast_walk.py:7-40` is verified to handle ONLY `ast.ImportFrom`. The walker is the right shape for the cycle-65 AC4/AC17/AC18/AC23 callers (which all pass `name="..."` for a specific symbol), but it is **structurally incapable** of detecting `import diskcache` (bare `ast.Import`) — that is a separate node class.

The threat-model T6 finding (T6.4 specifically) is correct: extending or adding a sibling helper is required, not optional. The current `tests/test_security_cve_greps.py` regex approach at `:27` does catch both `import X` and `from X` because the regex is `r"^\s*(import\s+diskcache\b|from\s+diskcache\b)"`. Switching to AST without covering both forms would silently REGRESS coverage. This is the highest-stakes AC in the cycle.

Option A (extend `find_imports_from`) vs Option B (sibling `find_module_imports`) vs Option C (in-test localized) vs Option D (regex consolidation):

- Option A extends the existing helper's contract with `name=None` overload. The five existing callers at cycle-65 (AC4/AC17/AC18/AC20/AC23) all pass `name="..."` — backward-compatible. But the helper module's `tests/_helpers/test_ast_walk.py` for `find_imports_from` is currently **stubs** (verified: lines 17-41 set up files, never call the helper). Extending the helper without writing real coverage doubles the existing tech-debt surface.
- Option B adds a sibling helper. Existing callers untouched. New helper is purpose-built. But the brainstorm flags that two helpers with overlapping concerns may confuse contributors. Mitigation: docstring-distinguish.
- Option C in-test localization: walk happens once via class-level cache, no helper-module change. Most localized. Trade-off: the logic isn't reusable, and a future banned-import test (e.g., a new Dependabot alert in cycle 67) re-implements it.
- Option D regex-consolidation: rejected per `feedback_inspect_source_tests` and cycle-3 L1 / cycle-6 L2 / cycle-11 L1 source-scan-tests-as-getsource hazard.

The brainstorm leans toward Option B. I weigh:

- **Behavioral preservation:** All four options can preserve coverage IF the negative-control fixture covers both `import X` AND `from X import Y` patterns. The threat-model T6.4 condition mandates this regardless of option. Equivalent.
- **Test coverage:** Options A and B both feed into `tests/_helpers/test_ast_walk.py`, which means the new helper's behavior gets test coverage in the helper's own test file (assuming the cycle adds those tests, which goes hand-in-hand with the new helper). Option C requires the negative-control fixture to live in `test_cycle66_cve_greps_consolidated.py`, which is fine but localized. Slightly more test surface for B than C.
- **Implementation effort:** Option C is smallest (one file changes). Option B adds a function to one helper file plus consumers. Option A modifies an existing function's contract. Roughly C < B < A in LOC.
- **Future-proofing:** Option B provides the most reusable primitive. Option A is reusable but mutates an existing contract (slight churn). Option C re-implements per-test.

I have a **deviation refinement on Option B**: I want to FLAG that Option B comes with an inline obligation to add real tests for `find_module_imports` in `tests/_helpers/test_ast_walk.py`. The existing stubs for `find_imports_from` are tech debt; adding more helper code with its own real tests (NOT stubs) closes the helper-module gap proportionally. The AC6 test-file plan should make this explicit (Step 5 condition).

Net: **Option B (sibling helper)** with the additional condition that `tests/_helpers/test_ast_walk.py` gains real `TestFindModuleImports` cases (≥3: positive control with `import X`, positive control with `from X import Y`, negative control with no matching imports). This is NOT extra scope — it is the natural test obligation for the new helper.

Risk axes:
1. **Behavioral preservation** — must cover BOTH import forms (T6.4). All options can satisfy this.
2. **Test coverage** — divergent-fail negative-control fixture per banned module is the load-bearing mitigation. T6 is the highest residual risk in the cycle; this test design closes it.
3. **Implementation effort** — Option B ~30-45 minutes (helper + 3 helper tests + parametrized consumer + fixture).
4. **Future-proofing** — Option B's reusable primitive ages well for cycle-67+ banned-import additions.

### AC5 — Independent walk-through

Verified facts:
- `path_safety.py:37` — `allow_symlinks: bool = False` parameter.
- `path_safety.py:50` — docstring entry.
- `path_safety.py:99` — `if not allow_symlinks and path.is_symlink(): raise`.
- `path_safety.py:13` — `Hard cap: 4 keyword-only parameters (Q2.2 design lock)` docstring.
- One production caller (`compile/compiler.py:672`) passes `dual_anchor=True` only — does NOT pass `allow_symlinks`.
- Zero `allow_symlinks` usage in `tests/` (verified by repo-wide Grep).

Removing the kwarg makes symlink rejection structurally unconditional. There is no current opt-out caller, so the change is purely subtractive. The Q2.2 hard-cap of 4 → 3 frees a kwarg slot for future params (the `path_safety.py:13` docstring needs to update from "Hard cap: 4" to "Hard cap: 3").

The behavioral test (create symlink under `tmp_path`, call validator, assert `ValueError`) exercises the production code path. The signature pin (`inspect.signature(_assert_under_project_root)` excludes `allow_symlinks`) is the structural-revert detector. Per cycle-7 L4, signature-only would be vacuous, but pairing with the behavioral test makes it belt-and-suspenders divergent-fail:
- If the kwarg is reverted, the signature pin fails RED.
- If the body-check is reverted to `if not allow_symlinks and ...`, behavior is unchanged (still rejects when default is False), but the signature pin fails RED.
- If both are reverted simultaneously and `allow_symlinks=True` is added to a caller, the behavioral test fails RED.

Three-way coverage; this is exactly the right shape.

Option B (deprecation cycle) is correctly rejected. Zero current opt-out callers → DeprecationWarning fires on the first hypothetical fourth caller, which is the case AC5 wants to prevent. Direct removal is correct.

Risk axes:
1. **Behavioral preservation** — symlink rejection still fires (was always-on; now structurally always-on).
2. **Test coverage** — behavioral + signature pin = belt-and-suspenders. Sound.
3. **Implementation effort** — ~10 minutes.
4. **Future-proofing** — closes T7 hazard structurally; frees kwarg slot. Ages well.

## Per-AC verdicts

### AC1 — Remove dead `kb.config.__getattr__("PROJECT_ROOT")` branch + rewrite misleading comment block

- **Brainstorm lean:** Option A (delete branch + rewrite comment).
- **R1 recommendation:** **CONFIRM Option A.**
- **Rationale:** Branch is provably dead (line 107 binds the name; PEP 562 only fires for names not in module dict). Comment block at `:760-769` is actively wrong about `PROJECT_ROOT`. Subtractive change with zero behavioral risk. Live behavior already flows through `get_project_root()`'s `globals().get("PROJECT_ROOT")` at `:70` per cycle-65 Step-12 fix.
- **Risks the brainstorm missed:** None substantive. The Step-9 implementation subtlety (Python module-level `__getattr__` may resist `monkeypatch.setattr`-style patching; verify the divergent-fail control actually triggers) is an implementation note, not a design flaw.
- **Step-5 conditions to lock:**
  1. AC1 test in `tests/test_cycle66_config_pep562.py` MUST mutate `kb.config.__getattr__` to raise `AttributeError` for any name AND THEN assert `get_project_root()` still returns the monkeypatched value — proving the test exercises the module-binding path, not the dead branch.
  2. Comment block rewrite MUST name `AUGMENT_ALLOWED_DOMAINS` as the only live PEP 562 branch and explicitly note `PROJECT_ROOT` is bound at line 107.

### AC2 — `_check_no_secrets_on_argv` sources keys from `CLI_BACKEND_ENV_INJECT`

- **Brainstorm lean:** Option A (module-level frozenset, derived once at import).
- **R1 recommendation:** **CONFIRM Option A.**
- **Rationale:** `CLI_BACKEND_ENV_INJECT` is a module-literal dict (not env-derived), so import-time capture does not violate cycle-19 L2 (which targets env-derived constants). Module-level frozenset is faster, simpler, and the parametrize-from-`CLI_BACKEND_ENV_INJECT.values()` test design closes T4 (revert hazard) regardless of the storage strategy.
- **Risks the brainstorm missed:** The brainstorm's framing of "captures `CLI_BACKEND_ENV_INJECT` at IMPORT TIME" as a Con applies a stricter cycle-19 L2 reading than the rule actually requires. Cycle-19 L2 specifically targets constants whose VALUES are derived from `os.environ.get(...)`. `CLI_BACKEND_ENV_INJECT` is a module-literal mapping; capturing it at import time is fine. Worth correcting in the design lock to avoid a future contributor mis-applying L2 to all module constants.
- **Step-5 conditions to lock:**
  1. AC2 test in `tests/test_cycle66_secret_scrub.py` parametrize source MUST be `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened (closes T4 per threat-model). NOT a literal mirror list.
  2. Each parametrize case MUST set its env var to a sentinel via `monkeypatch.setenv`, place that sentinel in argv, and assert `pytest.raises(LLMError)` with `match="(?i)refusing to place env secret"`.
  3. Paired negative control: same test with sentinel ≠ env value passes (closes T3 false-positive).
  4. Divergent-fail control: revert `_SCRUB_KEYS` to the cycle-66-pre 6-key literal → the parametrize cases for GEMINI/KIMI/QWEN/ZAI/ZHIPUAI MUST fail RED.
  5. Design comment in `cli_backend.py` MUST state that `_SCRUB_KEYS` derives at import time from `CLI_BACKEND_ENV_INJECT` and that adding a 9th backend automatically gains scrub coverage (positive constraint guiding future contributors).

### AC3 — `get_project_root()` per-call cost cache

- **Brainstorm lean:** Option B (`functools.lru_cache(maxsize=8)` on heuristic-only inner fn).
- **R1 recommendation:** **CONFIRM Option B.**
- **Rationale:** Idiomatic Python with built-in `cache_clear()` aligning with `_reset_project_root()` semantics. 8-entry capacity tolerates pytest-xdist workers + test-time `os.chdir` without explicit reset. Pure-function inner is unit-testable in isolation. Thread-safe under both CPython 3.13 and future PEP 703 free-threading.
- **Risks the brainstorm missed:** The perf benefit primarily helps the env-unset case (dev/test). Production deployments that set `KB_PROJECT_ROOT` already short-circuit at `config.py:18-27` and don't touch the heuristic. Worth being honest in the CHANGELOG: this is mostly a test-suite speedup, not a 10× MCP-boundary win.
- **Step-5 conditions to lock:**
  1. Cache key is `cwd_str: str` only (env is read above the cache, module binding is read above the cache). The cached inner fn signature is `_heuristic_walk_up_cached(cwd_str: str) -> Path`.
  2. `_reset_project_root()` calls `_heuristic_walk_up_cached.cache_clear()`.
  3. AC3 test contract MUST cover four behavioral assertions: hit-then-miss with spy on `Path.cwd`, reset clears cache, env override bypasses cache, module-binding override bypasses cache.
  4. Divergent-fail: revert AC3 (drop caching) → hit-then-miss test fails because the heuristic invokes twice.
  5. Refactor the env-prefix into `_resolve_project_root` and split the heuristic walk-up into the cached inner — keep the single-`_resolve_project_root` public surface so existing import paths don't break.

### AC4 — `tests/test_security_cve_greps.py` 4-walk consolidation

- **Brainstorm lean:** Option B (sibling `find_module_imports` in `tests/_helpers/ast_walk.py`).
- **R1 recommendation:** **CONFIRM Option B with an inline test-coverage condition.**
- **Rationale:** The new helper is purpose-built (cleaner naming than overloading `find_imports_from`), keeps existing 5 cycle-65 callers untouched, and provides a reusable primitive for future banned-import tests. Returning a dict shape `{"import": [...], "from": [...]}` makes the negative-control assertion crisp.
- **Risks the brainstorm missed:** Adding `find_module_imports` to `tests/_helpers/ast_walk.py` lands a new helper into a module whose existing `TestFindImportsFrom` cases are stubs (verified: `tests/_helpers/test_ast_walk.py:17-41` set up files but never invoke `find_imports_from`). Without real test coverage for the new helper, AC4 ships an unverified divergent-fail-detector. This is the highest-stakes AC (T6 → SECURITY.md CVE rationale). It is NOT acceptable to add helper code without real tests.
- **Step-5 conditions to lock:**
  1. The helper `find_module_imports(module: str, *, src_root: Path = Path("src/kb")) -> dict[str, list[Path]]` MUST detect BOTH `ast.Import` (`import diskcache`) AND `ast.ImportFrom` (`from diskcache import Cache`, `from diskcache.x import y`), AND must handle namespace packages by also matching `module.startswith(f"{module}.")` (e.g., `import diskcache.core`).
  2. `tests/_helpers/test_ast_walk.py` MUST gain real (NOT stub) `TestFindModuleImports` cases: ≥3 cases — (a) positive `import X` form, (b) positive `from X import Y` form, (c) negative-control case with imports of an unrelated module asserting empty result.
  3. AC4 negative-control fixture in `tests/test_cycle66_cve_greps_consolidated.py` MUST write `tmp_path/_test_only_{module}.py` with EACH banned import in turn — once with `import {module}` and once with `from {module} import Cache` — and assert the consolidated walker's result dict CONTAINS the temp file under both `"import"` and `"from"` keys.
  4. Divergent-fail control: temporarily insert a `from diskcache import Cache` line into a fresh `src/kb/` file, confirm the parametrized banned-imports test fires RED. (Manual revert immediately; document the verification in Step-14 notes.)
  5. Parametrize source is the literal banned-modules list `["diskcache", "litellm", "pip", "ragas"]` — that is the cycle-65 AC18 contract and is not dynamic.

### AC5 — Drop `allow_symlinks` kwarg from `_assert_under_project_root`

- **Brainstorm lean:** Option A (delete kwarg + unconditional symlink check).
- **R1 recommendation:** **CONFIRM Option A.**
- **Rationale:** Subtractive deletion. Single production caller (`compile/compiler.py:672`) does NOT pass the kwarg; zero test callers; zero `allow_symlinks=True` opt-outs anywhere. Q2.2 hard-cap drops 4 → 3, freeing namespace. Closes T7 (hypothetical-future-fourth-caller hazard) structurally.
- **Risks the brainstorm missed:** The `path_safety.py:13` module docstring says "Hard cap: 4 keyword-only parameters (Q2.2 design lock)" — this MUST update to "Hard cap: 3 keyword-only parameters (Q2.2 cycle-65 → cycle-66 reduced)" or equivalent. The brainstorm mentions this but it is worth elevating to a Step-5 condition because doc drift is the #1 way the structural cap gets re-violated.
- **Step-5 conditions to lock:**
  1. AC5 test in `tests/test_cycle66_path_safety_symlink.py` MUST include BOTH (a) signature pin via `inspect.signature(_assert_under_project_root)` excluding `allow_symlinks` AND (b) behavioral test creating a symlink under `tmp_path` and asserting `ValueError("… is a symlink (not allowed)")`.
  2. Caller-pin test: `compile/compiler.py::_validate_path_under_project_root` still raises `ValidationError` on symlink input (transitive via the helper).
  3. `path_safety.py:13` module docstring updates from "Hard cap: 4" to "Hard cap: 3" with cycle-66 reference.
  4. `docs/reference/error-handling.md` updates Q2.2 entry from 4-cap to 3-cap (per requirements AC7 doc-update — flag at Step 17 doc gate).

## Cross-AC findings

### Helper module evolution coupling (AC4 ↔ test infrastructure)

AC4's sibling helper proposal lands a new symbol in `tests/_helpers/ast_walk.py`. The cycle-65 audit shows the existing `find_imports_from` test cases at `tests/_helpers/test_ast_walk.py:14-41` are stubs (set up files but never invoke the helper). The new helper MUST come with real tests, not more stubs. This is a Step-5 condition for AC4 (conditions 2 and 3 above). The brainstorm correctly notes the existing stubs as out-of-scope tech debt, but adding a NEW helper without coverage doubles the gap proportionally — that is not acceptable inside cycle 66.

### AC2 + AC4 + AC5 — three load-bearing test contracts converge

The threat-model identifies T2 (AC2 closes), T6 (AC4 closes), and T7 (AC5 closes) as the load-bearing security closures. All three have prescribed test designs (parametrize-from-canonical, paired negative-control fixture, signature+behavioral pin). Step 5 must verify all three test contracts independently — Step-9 implementer should be able to run each AC's test file in isolation and observe divergent-fail before the rest of the cycle lands. Recommend Step-9 commit order matches the brainstorm's recommendation (AC5 → AC1 → AC4 → AC3 → AC2) so each AC's tests can be added incrementally.

### AC1 + AC3 — `kb.config` co-evolution

AC1 simplifies the `__getattr__` PEP 562 shim (removes dead branch) while AC3 caches the `_resolve_project_root()` heuristic walk-up. These touch overlapping ranges of `kb.config` (lines 760-776 and 15-82 respectively). Risk: a Step-9 commit that lands AC3 first may show a diff that overlaps with AC1's planned edits in non-trivial ways if the implementer refactors the comment block. Mitigation: keep AC1's diff scope strictly to `:760-776` and AC3's diff scope strictly to `:15-82`. Verify at PR review (Step 11/20).

### AC3's perf claim honesty

The MCP-boundary perf benefit at the threat-model's "~6 syscalls per MCP call when env is unset" is a TEST-suite-leaning win, not a production win, because production typically sets `KB_PROJECT_ROOT`. CHANGELOG entry should reflect this — claim "test-suite + dev-loop perf" rather than "MCP-boundary perf" to avoid overstating. Step-17 doc-update gate.

### No cross-AC interactions that block

None of the five ACs have dependency conflicts. AC2's parametrize source (`CLI_BACKEND_ENV_INJECT.values()`) reads from `kb.config` at test-collection time, which is unaffected by AC1 (which removes a dead branch in `__getattr__`) and AC3 (which adds a heuristic cache to `_resolve_project_root`). AC4 and AC5 are entirely orthogonal to the `kb.config` changes.

## Tier escalation check

Tier 2 stays Tier 2.

The threat-model verdict is APPROVE without conditions. The five ACs are HARDENING/CLEANUP of existing security primitives — none introduce new trust boundaries. AC2 is the closest to Tier-3 territory because it is a real Information Disclosure closure with `medium × high` risk, but it is **purely additive** scrub coverage (the substring-containment mechanism is unchanged from cycle-65 AC16). The user's `feedback_auto_approve` memory authorises Opus subagent gating; Tier 2 is sufficient.

No threat in the cycle-66 set crosses the Tier-3 threshold. No Step-5 manual-merge gate required.

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS**

The five brainstorm "lean" picks are all correct on independent score. I confirm A/A/B/B/A. The inline resolutions below are NOT escalations or alternative-option deviations — they are the test-contract conditions and design-comment locks that the threat-model already identified, plus one new helper-module-test obligation surfaced during AC4's independent walk.

Step 5 must apply the following resolutions:

1. **AC1** — design-lock the divergent-fail control: AC1 test MUST mutate `kb.config.__getattr__` to raise unconditionally AND THEN assert `get_project_root()` still returns the monkeypatched value. Step-9 implementation note: verify the monkeypatch pattern actually works for module-level `__getattr__` (Python special-method lookup may need explicit `kb.config.__getattr__ = new_fn` rather than `monkeypatch.setattr`).
2. **AC2** — design-lock the parametrize source as `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened (NOT a literal mirror list). Closes T4. Add an inline design comment in `cli_backend.py` stating that `_SCRUB_KEYS` derives at import time from `CLI_BACKEND_ENV_INJECT` so future contributors don't re-hardcode.
3. **AC2** — clarify in design lock that import-time capture of `CLI_BACKEND_ENV_INJECT` does NOT violate cycle-19 L2 (which targets env-derived constants, not module-literal-derived constants). Prevents a future contributor from mis-applying L2 to all module constants and forcing an unnecessary call-time accessor refactor.
4. **AC3** — design-lock cache key as `cwd_str: str` only; `_reset_project_root()` calls `_heuristic_walk_up_cached.cache_clear()`. Refactor splits `_resolve_project_root` into env-prefix + cached-inner while keeping the public function name unchanged.
5. **AC3** — CHANGELOG entry must honestly characterize this as test-suite/dev-loop perf, not MCP-boundary production perf (because production typically sets `KB_PROJECT_ROOT`).
6. **AC4** — design-lock the new helper signature `find_module_imports(module: str, *, src_root: Path = Path("src/kb")) -> dict[str, list[Path]]` returning `{"import": [...], "from": [...]}` keys. Helper MUST detect both `ast.Import` and `ast.ImportFrom` plus namespace-prefix matches (`startswith(f"{module}.")`).
7. **AC4** — `tests/_helpers/test_ast_walk.py` MUST gain real (NOT stub) `TestFindModuleImports` cases covering both import forms plus a negative control. This is a NEW test obligation tied to the new helper; it does NOT inherit the existing `TestFindImportsFrom` stubs as acceptable.
8. **AC4** — Negative-control fixture in `tests/test_cycle66_cve_greps_consolidated.py` MUST write `tmp_path/_test_only_{module}.py` files with EACH banned import in BOTH `import X` AND `from X import Y` forms, and assert the walker's dict result contains the temp file under both keys. Closes T6.
9. **AC5** — design-lock both signature pin AND behavioral symlink-rejection test in `tests/test_cycle66_path_safety_symlink.py` (cycle-7 L4 belt-and-suspenders). Closes T7.
10. **AC5** — `path_safety.py:13` module docstring updates "Hard cap: 4 keyword-only parameters" to "Hard cap: 3 keyword-only parameters (Q2.2 cycle-65 → cycle-66 reduced)". `docs/reference/error-handling.md` updates Q2.2 entry to match (Step 17 doc gate).
11. **AC4 commit atomicity** — Step-9 commit order recommended in brainstorm (AC5 → AC1 → AC4 → AC3 → AC2) is sound. Each AC commits independently; the AC4 commit must include the new helper, the helper's tests, the consolidated CVE-greps test, and the negative-control fixture together (single atomic file-grouped commit per `feedback_batch_by_file`).

These eleven resolutions are not new requirements — they are the threat-model's already-stated test-contract conditions made explicit for Step 5, plus the AC4 helper-module-test obligation surfaced during R1 fact-checking.

## BLOCKERs / MAJORs / NITs surfaced

### BLOCKER — none

No design flaw blocks the cycle.

### MAJOR — AC4 helper-module-test obligation

Adding `find_module_imports` to `tests/_helpers/ast_walk.py` without real test coverage in `tests/_helpers/test_ast_walk.py` would land an unverified divergent-fail-detector on the highest-stakes AC (T6 → SECURITY.md CVE rationale). The existing `TestFindImportsFrom` stubs are NOT acceptable as a model. Resolution captured in Step-5 conditions 6 and 7 above.

### MINOR — AC2 cycle-19 L2 framing in brainstorm Cons column

The brainstorm's Cons column for Option A says "captures `CLI_BACKEND_ENV_INJECT` at IMPORT TIME. If a future cycle ever makes `CLI_BACKEND_ENV_INJECT` runtime-mutable…" — this conflates two different hazard classes. Cycle-19 L2 targets env-derived constants. `CLI_BACKEND_ENV_INJECT` is a module-literal dict — capturing it at import time is fine. The Step-5 design lock should clarify the distinction so future contributors do not apply L2 over-eagerly. Resolution captured in Step-5 condition 3 above.

### MINOR — AC3 perf framing honesty

The threat-model claims "~6 syscalls per MCP call when env is unset" — which is true, but production typically sets `KB_PROJECT_ROOT` and short-circuits before the heuristic. CHANGELOG should claim "test-suite + dev-loop perf" not "MCP-boundary production perf" to avoid overstating. Resolution captured in Step-5 condition 5 above.

### NIT — AC1 monkeypatch-`__getattr__` test pattern

Python's special-method lookup for module-level `__getattr__` may not behave identically to instance-attribute monkeypatching. Step-9 implementer should verify the divergent-fail control actually triggers — if `monkeypatch.setattr(kb.config, "__getattr__", new_fn)` does not replace the lookup, the test should use direct binding (`kb.config.__getattr__ = new_fn` with explicit teardown). Resolution captured in Step-5 condition 1 above.

### NIT — AC1 + AC3 diff overlap discipline

AC1 edits `kb.config:760-776` and AC3 edits `kb.config:15-82`. Strict diff-scope discipline at Step-9 prevents accidental overlap. Verify at PR review (Step 11/20).

---

**Step 4 R1 review complete.** Verdict APPROVE-WITH-INLINE-RESOLUTIONS. Eleven Step-5 resolutions enumerated. No design alternatives recommended over the brainstorm leans; the five A/A/B/B/A picks are confirmed on independent score. No Tier escalation required.

→ Proceed to Step 5 (design-decision lock), reading both R1 (this doc) and R2 (DeepSeek) outputs.
