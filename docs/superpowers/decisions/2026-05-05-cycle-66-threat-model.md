# Cycle 66 — Threat Model + Dep-CVE Baseline

**Date:** 2026-05-05
**Branch:** `feat/cycle-66`
**Step:** 2 of 24
**Inputs:** `2026-05-05-cycle-66-requirements.md` (5 ACs)

---

## Analysis

Per cycle-3 L7 (Opus 4.7 needs explicit CoT scaffolding), step through each AC and ask "what trust boundary does this diff actually cross?" before mapping STRIDE categories.

### AC1 — Dead `__getattr__("PROJECT_ROOT")` branch removal (`src/kb/config.py:760-776`)

The branch is dead because line 107 binds `PROJECT_ROOT = _resolve_project_root()` at module load. PEP 562 only fires when the attribute is **not** in the module dict. The branch never executes; deleting it is signature-preserving. Real call-time behavior flows through `get_project_root()` which reads `globals().get("PROJECT_ROOT")` (cycle-65 Step-12 fix). The `AUGMENT_ALLOWED_DOMAINS` branch IS live (no module-level binding) and stays.

**STRIDE relevance:**
- **Tampering:** the only realistic threat is a *future revert* of the dead-branch removal that re-introduces it — would cause `kb.config.PROJECT_ROOT` attribute access to call `get_project_root()` on the PEP 562 path. That path is itself safe today (it reads env first, then `globals().get`, then heuristic), so the post-revert behavior would be functionally equivalent. The actual risk is therefore confined to *test regression* if a future test relies on the dead branch firing. → T1 below.
- **Spoofing / Repudiation / Info Disclosure / DoS / EoP:** vacuous. No auth boundary, no log line, no error message, no resource consumption, no privilege transition.

### AC2 — `_check_no_secrets_on_argv` sources keys from `CLI_BACKEND_ENV_INJECT` (`src/kb/utils/cli_backend.py:138-148`)

This is a real Information Disclosure surface: the CURRENT 6-key hardcoded list (ANTHROPIC, OPENAI, FIRECRAWL, DEEPSEEK, MIMOCODING, MIMOCHAT) misses `CLI_BACKEND_ENV_INJECT` entries. Verified at threat-model time, the post-AC2 frozenset will be:

| Source | Keys |
|---|---|
| Standalone (preserved) | ANTHROPIC_API_KEY, FIRECRAWL_API_KEY, MIMOCODING_API_KEY, MIMOCHAT_API_KEY |
| `CLI_BACKEND_ENV_INJECT["gemini"]` | GEMINI_API_KEY |
| `CLI_BACKEND_ENV_INJECT["opencode"\|"codex"]` | OPENAI_API_KEY (preserved — subsumed) |
| `CLI_BACKEND_ENV_INJECT["kimi"]` | KIMI_API_KEY |
| `CLI_BACKEND_ENV_INJECT["qwen"]` | QWEN_API_KEY |
| `CLI_BACKEND_ENV_INJECT["deepseek"]` | DEEPSEEK_API_KEY (preserved — subsumed) |
| `CLI_BACKEND_ENV_INJECT["zai"]` | ZAI_API_KEY, ZHIPUAI_API_KEY |

**Net new scrub coverage: 5 keys (GEMINI, KIMI, QWEN, ZAI, ZHIPUAI). Net dropped coverage: 0.** The previously-listed OPENAI and DEEPSEEK are subsumed by `CLI_BACKEND_ENV_INJECT` entries (verified above) — they remain in the frozenset.

**STRIDE relevance:**
- **Information Disclosure:** the threat being CLOSED is "argv leak of Gemini/Kimi/Qwen/Zai/ZhipuAI keys via subprocess `ps`/audit log inspection" → T2.
- **Denial of Service:** AC2 expands scrub coverage. A new question is: does any LEGITIMATE workflow place one of these new keys on argv intentionally (e.g., explicit `--api-key=$GEMINI_API_KEY`)? The substring-containment scrub (cycle-65 AC16, preserved) would now refuse to spawn that subprocess → self-DoS. Worth a threat entry. → T3.
- **Tampering:** revert risk — a future caller adds a 9th `CLI_BACKEND_ENV_INJECT` backend (e.g., `"new_provider": ("NEW_API_KEY",)`) and the frozenset comprehension picks it up automatically. That's a *positive* property (no maintenance burden), but a contributor could ALSO drop the comprehension and re-hardcode the list, silently regressing coverage. → T4.
- **Spoofing / Repudiation / EoP:** vacuous — no auth, no audit, no privilege.

### AC3 — `_resolve_project_root()` heuristic walk-up cache (`src/kb/config.py:15-82`)

Cache key is `cwd` (env is short-circuited above). Cache stored in module-global `_HEURISTIC_CACHE: tuple[Path, Path] | None`. Reset via `_reset_project_root()`.

**STRIDE relevance:**
- **Tampering:** if a test changes `cwd` between calls, the cache key includes `cwd` so a stale value can't bleed. If a test calls `os.chdir(/tmp/attacker)` between resolves and the heuristic finds `/tmp/attacker/pyproject.toml`, that's the test's intended behavior, not a cache fault. Threat: a test that monkeypatches `kb.config.PROJECT_ROOT` THEN calls `_reset_project_root()` THEN calls `get_project_root()` — the reset clears the cache but `get_project_root()` reads `globals()["PROJECT_ROOT"]` BEFORE the heuristic, so the monkeypatch wins. Behavior preserved. → vacuous as a threat, listed as a test-correctness concern in T5.
- **Information Disclosure:** if `_HEURISTIC_CACHE` somehow leaked across user sessions on a multi-tenant system… but this is a Python module global, scoped per-process. There is no multi-tenant exposure. Vacuous.
- **Denial of Service:** the cache stores ONE tuple. No unbounded growth. Memory-DoS vacuous. A pathological test that fills `_HEURISTIC_CACHE` with a non-`Path` instance would crash the next read; that's a test-bug, not a security threat.
- **Concurrency:** Python `tuple` rebind is atomic (single STORE_GLOBAL on CPython). Two threads reading + one writing produces "either old value or new value" — both are valid resolutions. No torn reads. → no concurrency threat.
- **Spoofing / Repudiation / EoP:** vacuous.

### AC4 — Test consolidation: 4 `rglob` → 1 walk in `tests/test_security_cve_greps.py`

Self-test only. Production code unchanged.

**STRIDE relevance:**
- **Tampering:** the actual security property under test (zero `import diskcache|litellm|pip|ragas` in `src/kb/`) is the cycle-65 AC18 / T14 mitigation. The risk is that a consolidation refactor introduces a logic bug where the test PASSES even when a banned import is added — i.e., the test stops divergent-failing. → T6.
- **Repudiation:** the SECURITY.md "accepted CVE rationale" depends on this test enforcing zero direct imports. If the consolidated walker silently misses imports (e.g., AST visitor misses `from diskcache import Cache as C` style), the SECURITY.md narrative becomes unsupported without anyone noticing. → covered by T6 (same root cause).
- **Other:** vacuous.

### AC5 — Drop `allow_symlinks` kwarg from `_assert_under_project_root`

Verified at threat-model time:
- `src/kb/utils/path_safety.py:37` — current default `False`.
- `src/kb/utils/path_safety.py:99` — `if not allow_symlinks and path.is_symlink(): raise`.
- 1 production caller (`compile/compiler.py:672`) — does NOT pass `allow_symlinks`.
- 0 test callers (verified via grep against `tests/`).

Removing the kwarg makes symlink rejection structurally unconditional. There is no caller, anywhere in `src/` or `tests/`, currently opting out of symlink rejection. Therefore AC5 closes a "false-flexibility" hazard: a future contributor could have set `allow_symlinks=True` on a fourth caller, weakening the dual-anchor + symlink-rejection contract that cycle-65 AC9/AC10 established.

**STRIDE relevance:**
- **Tampering / EoP:** the threat being CLOSED is "future fourth caller passes `allow_symlinks=True`, accepts a `wiki/page.md → /etc/passwd` symlink, opens it, and either reads or unlinks the target". Closed structurally. → T7.
- **Other:** vacuous — no auth boundary change, no information leak, no DoS, no spoofing.

### Categories that yield zero cycle-66 threats

- **Spoofing.** No auth boundary touched (no MCP gate change, no URL allowlist change, no DNS resolution change). Cycle-65 closed the SSRF / DNS-rebind set (T9-T11) and that surface is unchanged here.
- **Repudiation.** No log/audit format changed; the AC4 test-coverage concern is folded into T6 as Tampering (the test stops detecting the violation), not Repudiation (logs deny what happened).

---

## STRIDE pass

### T1 — Dead-branch revert breaks monkeypatch test pattern

- **Category:** Tampering
- **AC origin:** AC1
- **Vector:** A future contributor mistakes the AC1 deletion for a regression and re-adds `if name == "PROJECT_ROOT": return get_project_root()` to `__getattr__`. Behavior is functionally equivalent today (PEP 562 doesn't fire because `PROJECT_ROOT` is module-bound), so no production observable changes — but the AC1 regression test (which asserts the test exercises the module-binding path, NOT the dead branch) goes silent.
- **Likelihood:** low — the dead-branch comment refactor explicitly documents why the branch is dead, reducing revert temptation.
- **Impact:** low — functionally equivalent post-revert; the only loss is a divergent-fail signal on the AC1 regression test.
- **Mitigation:** shipped in this cycle's diff — AC1 regression test in `tests/test_cycle66_config_pep562.py` MUST monkeypatch `kb.config.PROJECT_ROOT` THEN replace `__getattr__` body with `raise AttributeError` for any name, asserting `get_project_root()` still returns the monkeypatched value (proves the test exercises the module-binding path, not the dead branch — the divergent-fail control).
- **Verification:** Step 14 reads `tests/test_cycle66_config_pep562.py` and confirms the test mutates `__getattr__` to raise unconditionally; pytest green.

### T2 — Argv leak of Gemini/Kimi/Qwen/Zai/ZhipuAI keys (CLOSED by AC2)

- **Category:** Information Disclosure
- **AC origin:** AC2
- **Vector:** A user runs `kb` with `KB_LLM_BACKEND=gemini` (or kimi/qwen/zai). The `_build_cmd(backend, model)` path constructs argv, possibly including a `--api-key=$GEMINI_API_KEY` style argument from a future caller, OR the model-override slot at `cli_backend.py:198` placing a model name that happens to match the env value. Without AC2, `_check_no_secrets_on_argv` only iterates the hardcoded 6 (ANTHROPIC, OPENAI, FIRECRAWL, DEEPSEEK, MIMOCODING, MIMOCHAT) — `GEMINI_API_KEY` would slip past the scrub and land on argv. From there, `ps` / `/proc/$pid/cmdline` / Linux audit-log / Windows ETW / macOS `dtruss` reveals the key to any process able to enumerate the system PID table.
- **Likelihood:** medium — Gemini/Kimi/Qwen/Zai/ZhipuAI are live backends in `CLI_BACKEND_ENV_INJECT`; the leak fires the moment any caller places those keys on argv (no exploit chain needed, just ps/audit access).
- **Impact:** high — API key disclosure enables direct billable-API abuse and (per cycle-21 T8 threat-model docstring) downstream cost / quota / rate-limit DoS on the user's account.
- **Mitigation:** shipped in this cycle's diff — AC2 frozenset `_SCRUB_KEYS` derives from `CLI_BACKEND_ENV_INJECT.values() | standalone-set`, picking up GEMINI, KIMI, QWEN, ZAI, ZHIPUAI automatically.
- **Verification:** Step 14 — `pytest tests/test_cycle66_secret_scrub.py` parametrizes EVERY key in the post-AC2 frozenset and asserts scrub fires + paired negative-control (sentinel ≠ env value passes); divergent-fail check reverting AC2 to the hardcoded 6-key list MUST cause the GEMINI/KIMI/QWEN/ZAI/ZHIPUAI cases to fail.

### T3 — Substring-scrub self-DoS on legitimate prompts that mention new key values

- **Category:** Denial of Service
- **AC origin:** AC2 (introduced)
- **Vector:** Per cycle-21 T8 history, the original `_check_no_secrets_on_argv` regex over-triggered on prompts that DISCUSSED key formats. Cycle-65 AC16 fixed that by switching from regex-pattern-match to substring-containment against the LITERAL VALUE of env vars. AC2 expands the env var SET being checked. So a user prompt containing the literal value of `GEMINI_API_KEY` (e.g., a user asks "is `AIzaSyD…exact-real-value…` a valid Gemini key?") will refuse to spawn. This is the *correct* behavior (refusing is conservative — the prompt would otherwise leak a real key), but it's worth noting that AC2's expansion increases the surface for legitimate-prompt-confusion. Note also the existing scrub iterates `argv` via `secret_value in elem` — if `GEMINI_API_KEY=""`, the `if not secret_value: continue` short-circuit skips the scrub correctly, so empty env doesn't false-positive.
- **Likelihood:** low — the scrub matches LITERAL ENV VALUES, not regex patterns. A user accidentally typing the exact value of their own GEMINI_API_KEY into the prompt is an unusual action; if they do, refusing the spawn is the safer outcome.
- **Impact:** low — the user gets a `LLMError("Refusing to place env secret …")` and can investigate; no data loss, no leak.
- **Mitigation:** not-applicable — this is the *intended* behavior of the substring scrub, expanded by AC2 to more keys. The mitigation that already exists (cycle-65 AC16: literal-value match, not regex) prevents false-positives on KEY-NAME mentions; AC2 inherits that.
- **Verification:** Step 14 — `tests/test_cycle66_secret_scrub.py` paired negative control: sentinel literal NOT equal to env value MUST pass the scrub (no false positive on key-NAME discussion). Confirmed by the AC2 test contract.

### T4 — Future contributor reverts `CLI_BACKEND_ENV_INJECT` derivation to hardcoded list

- **Category:** Tampering
- **AC origin:** AC2
- **Vector:** A contributor refactoring `cli_backend.py` (e.g., to add a 9th backend) misses the `CLI_BACKEND_ENV_INJECT.values()` comprehension and re-hardcodes the list to the 8 they happened to think of, silently dropping coverage of any 9th key added later. The post-AC2 frozenset is dynamic — its strength depends on staying derived.
- **Likelihood:** low — the AC2 design comment will document the derivation; cycle-21 conventions discourage hardcoded enumerations.
- **Impact:** medium — silent regression of T2's mitigation; the GEMINI/KIMI/QWEN/ZAI/ZHIPUAI keys re-leak through whichever path AC2 closed.
- **Mitigation:** shipped in this cycle's diff — `tests/test_cycle66_secret_scrub.py` parametrizes over `kb.config.CLI_BACKEND_ENV_INJECT.values()` (NOT a hardcoded mirror), so any future addition to `CLI_BACKEND_ENV_INJECT` automatically generates a new test case. The test FAILS divergent if `_SCRUB_KEYS` is hardcoded back: a key in `CLI_BACKEND_ENV_INJECT` not in `_SCRUB_KEYS` produces a test failure on the parametrize loop.
- **Verification:** Step 14 — read `tests/test_cycle66_secret_scrub.py` and confirm parametrize source is `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened, not a literal list. Manual revert-test by hardcoding `_SCRUB_KEYS` to the cycle-66-pre 6-key list and confirming the parametrize yields RED.

### T5 — `_HEURISTIC_CACHE` stale across `os.chdir` in concurrent test runs

- **Category:** Tampering (test correctness; not production-security-critical)
- **AC origin:** AC3
- **Vector:** Test A monkeypatches `os.chdir(/tmp/A)` and calls `_resolve_project_root()` populating `_HEURISTIC_CACHE = (Path("/tmp/A"), Path("/tmp/A"))`. Test B in the same pytest worker does NOT monkeypatch `os.chdir` but its expected cwd is `/tmp/B` — the cache hit returns `/tmp/A`. Defensive design: cache key includes `cwd`, so cwd mismatch triggers a recompute. The threat is therefore confined to the *implementation correctness* of the cache-key check.
- **Likelihood:** low — the AC3 design specifies cache-key includes `cwd`, and `_reset_project_root()` is called in test fixtures that mutate env (and should be called by tests that mutate cwd between heuristic invocations). Pytest workers are process-isolated under `pytest-xdist`, eliminating the cross-test bleed scenario above; a single worker would only show this if the test itself forgot to reset.
- **Impact:** low — production code does not `os.chdir` in long-running paths. CI and dev usage start from a stable cwd. The bug surface is purely tests.
- **Mitigation:** shipped in this cycle's diff — AC3 design specifies `_HEURISTIC_CACHE` keyed by `cwd` (cache miss on cwd change); `_reset_project_root()` clears the cache for tests that need explicit invalidation. Test contract requires "Reset clears cache" + "Hit-then-miss" + "env-override bypasses cache" + "module-binding override bypasses cache" — four behavioral assertions covering every observed access pattern.
- **Verification:** Step 14 — `pytest tests/test_cycle66_project_root_cache.py::test_cwd_change_invalidates_cache` (force `os.chdir`, assert second call recomputes), plus the divergent-fail test (revert AC3 → hit-then-miss assertion fails because heuristic invokes twice).

### T6 — AC4 consolidated walker silently misses banned imports (lost divergent-fail)

- **Category:** Tampering (the test STOPS detecting the production violation)
- **AC origin:** AC4
- **Vector:** The 4-walk → 1-walk consolidation introduces a helper `_walk_kb_for_banned_imports()` returning `dict[module_name, list[str]]`. Failure modes:
  1. AST walker uses `find_imports_from(file, target_module)` but applies it only to top-level `Import` nodes, missing `ImportFrom` (`from diskcache import Cache`).
  2. Walker uses regex on the raw text but stops at the first match per file, missing nested `import litellm` inside a `try:` / `except ImportError:` block.
  3. Parametrize fixture name shadows the dict result, silently giving every parametrize case an empty list (zero hits) → all tests pass green → revert of cycle-65 AC18 / SECURITY.md rationale silently invalidates.
  4. The helper at `tests/_helpers/ast_walk.py::find_imports_from` (lines 7-40) **only handles `ast.ImportFrom`** — bare `import diskcache` (i.e., `ast.Import` nodes) is silently invisible. The dedicated tests for the helper at `tests/_helpers/test_ast_walk.py:17-41` are themselves stubs (fixture-setup only, never invoking the helper), so the limitation has no test coverage either. AC4 must either (a) extend `find_imports_from` to handle both forms, or (b) add a sibling helper `find_module_imports(module)` covering `ast.Import`, or (c) use a regex fallback for the bare-import case. Whichever path is chosen, the AC4 negative-control fixture MUST cover BOTH `import diskcache` AND `from diskcache import X` patterns.
- **Likelihood:** medium — consolidation refactors are a known false-pass-on-revert hazard (cycle-22 L5, user's `feedback_inspect_source_tests`).
- **Impact:** high — directly invalidates SECURITY.md's accepted-CVE rationale (CVE-2025-69872 diskcache pickle RCE; GHSA-xqmj-j6mv-4862 litellm proxy template injection; CVE-2026-6587 ragas SSRF). The SECURITY.md narrative says "zero direct imports of these packages in src/kb/"; if the test silently passes after a `from diskcache import Cache` lands, the rationale silently becomes false.
- **Mitigation:** shipped in this cycle's diff — AC4 test contract REQUIRES a paired negative-control fixture per banned module: writes `tmp_path/_test_only.py` with `import diskcache` (each banned in turn), runs the consolidated walk over the temp tree, asserts the file appears in the banned dict. This is a divergent-fail proof that the walker DETECTS imports rather than silently empty-passing.
- **Verification:** Step 14 — read `tests/test_cycle66_cve_greps_consolidated.py` and confirm the negative-control fixture exists and asserts `assert "_test_only.py" in result["diskcache"]` (or equivalent positive assertion). Manual revert-test: temporarily insert `from diskcache import Cache` into a fresh `src/kb/` file (revert immediately), confirm the consolidated test fires RED.

### T7 — AC5 closes "fourth caller passes `allow_symlinks=True`" hazard

- **Category:** Tampering, Elevation of Privilege (closed)
- **AC origin:** AC5
- **Vector:** Pre-AC5: a future fourth caller of `_assert_under_project_root` (e.g., a hypothetical `kb_export_to_path` MCP tool, or a new `compile_wiki` write target) could pass `allow_symlinks=True` to opt out of the symlink-rejection that cycle-65 AC9/AC10 established. With `allow_symlinks=True`, an attacker who can plant a symlink under the project tree (low-privilege user account on a shared dev box, malicious `pip install` post-install hook, malicious raw-source contributor sending `wiki/note.md → /etc/passwd`) opens a TOCTOU window where the validator returns success, then the production write/unlink follows the symlink to a target outside the project root.
- **Likelihood:** low — no caller currently passes `allow_symlinks=True` (verified: 0 hits across `src/`, 0 hits across `tests/`). The threat is hypothetical.
- **Impact:** medium — same impact class as cycle-65 T8 (TOCTOU symlink-swap on `rebuild_indexes`). A successful exploit could unlink or read files outside the project root — relevant for any process running `kb` as a privileged user (rare but not impossible).
- **Mitigation:** shipped in this cycle's diff — AC5 removes the kwarg entirely; symlink rejection becomes unconditional. The "false flexibility" parameter is gone, structurally preventing the hypothetical fourth-caller opt-out.
- **Verification:** Step 14 — `tests/test_cycle66_path_safety_symlink.py::test_signature_excludes_allow_symlinks` (signature pin via `inspect.signature`) + `tests/test_cycle66_path_safety_symlink.py::test_symlink_rejected_under_tmp_path` (behavioral: create symlink under tmp_path, call `_assert_under_project_root(symlink_path, "field")`, assert `ValueError("… is a symlink (not allowed)")`) + caller-pin test that `compile/compiler.py::_validate_path_under_project_root` still raises `ValidationError` on symlink inputs. Belt-and-suspenders divergent-fail: if AC5 is reverted (kwarg restored, default False), the signature pin fails RED; if the body is reverted to `if not allow_symlinks and path.is_symlink():`, behavior is unchanged but the pin still catches the structural regression.

---

## Risk ranking

Threats ranked by `likelihood × impact`. Closed-threat entries (T2, T7) reflect post-cycle residual risk.

| Rank | ID | likelihood × impact | Notes |
|---|---|---|---|
| 1 | **T6** | medium × high | AC4 consolidation false-pass-on-revert directly invalidates SECURITY.md CVE rationale. Highest residual concern in cycle 66. |
| 2 | **T2** | medium × high (CLOSED by AC2) | Argv leak of Gemini/Kimi/Qwen/Zai/ZhipuAI keys. AC2 closes; verification is critical. |
| 3 | **T4** | low × medium | Future contributor re-hardcodes `_SCRUB_KEYS`. Mitigated by parametrize-from-`CLI_BACKEND_ENV_INJECT` test design. |

T1, T3, T5, T7 all rank low-low or low-medium and are addressed by the AC test contracts.

**Tier escalation check:** No threat in the cycle-66 set crosses the Tier-3 threshold. AC2 is the highest-stakes item but is purely additive scrub coverage (not a NEW security boundary, not a new auth gate, not a new external surface). Per the requirements doc Tier-2 rationale (lines 21-22) and the user's `feedback_auto_approve` memory authorising Opus subagent gating, **NO Tier-3 escalation required**.

---

## Dep-CVE baseline

**Captured:** 2026-05-05 21:21 (project-relative artifact at `.data/cycle-66/pip-audit-baseline.json`, ~19KB).

**Method:** `.venv/Scripts/pip-audit --format=json` against the live installed environment (no `-r requirements.txt` per cycle-22 L1 + SECURITY.md line 36 — avoids `ResolutionImpossible` on `arxiv 2.4.1` ↔ `requests 2.33.0`).

**Findings: 2 known accepted CVEs (carry-over from cycle-65 post-PR-#92, no drift, no new advisories).**

| Package | Version | Advisory | Status | Source-of-truth |
|---|---|---|---|---|
| `diskcache` | 5.6.3 | `CVE-2025-69872` / `GHSA-w8v5-vhqr-4h9v` (pickle-deserialization RCE in cache files) | Accepted — no upstream fix; transitive via trafilatura's robots.txt cache; zero direct imports in `src/kb/` (verified by `tests/test_security_cve_greps.py::test_diskcache_zero_imports`). | `SECURITY.md:29` |
| `pip` | 26.0.1 | `CVE-2026-3219` / `GHSA-58qw-9mgm-455v` (pip handles concatenated tar+ZIP files as ZIP regardless of filename) | Accepted — no upstream fix; tooling not runtime; `kb` runtime never shells out to `pip`. | `SECURITY.md:30` |

**Status:** Both advisories are listed in `.github/workflows/ci.yml` `pip-audit` step via `--ignore-vuln=` (per SECURITY.md line 34). Cycle-66 introduces NO new dependencies (5-AC scope is pure src/tests refactor with no `requirements.txt` / `pyproject.toml` change). Therefore Step 11 PR-introduced-CVE diff is expected to be empty; Step 14 verification is purely "no NEW advisories surfaced during the cycle wall-clock window" (cycle-22 L4 late-arrival hazard).

**Skipped packages (not auditable on PyPI):** `llm-knowledge-base 0.2.0` and `llm-wiki-flywheel 0.11.0` — both are this project's own editable-install distributions, not on PyPI. `pip-audit` correctly skips them.

**Not present in baseline (sanity check):** `litellm` (the distribution removed by PR #92), `ragas` (also removed by PR #92). The `unclecode-litellm 1.81.13` entry is a separate distribution (devtime crawl4ai dependency) — unrelated to the original `litellm` CVE chain. Verified via `tests/test_security_cve_greps.py::test_litellm_zero_imports` enforcing zero direct imports of the `litellm` namespace from `src/kb/`.

---

## Out-of-scope threats (deferred)

Per cycle-7 L4 (avoid scope confusion in Step 14), the following same-class-peer threats are NOT closed by AC1-AC5 but were surfaced during analysis. Step 14 must not flag their absence as a regression. Each is filed as a cycle-67+ candidate.

- **OOS-1: Larger PEP 562 redesign for snapshot-callers.** Per requirements §"Out of scope (deferred)" line 52, replacing module-level `PROJECT_ROOT = _resolve_project_root()` with a `LazyPathProxy` that re-reads on every attribute access remains deferred. ~200 `from kb.config import PROJECT_ROOT` snapshot callers would need migration. Cycle-65 already mitigated the runtime hazard via `get_project_root()` accessor; the residual concern is import-time-snapshot consistency.
- **OOS-2: `_DEFAULT_MODEL_TIERS` dual-mechanism removal.** Same hazard class as AC3 cache (cycle-19 L2 reload-leak). Captures `os.environ.get(CLAUDE_*_MODEL)` at import time. Filed as cycle-67+ via requirements §"Out of scope" line 53.
- **OOS-3: `_check_no_secrets_on_argv` substring-scrub timing-leak audit.** Cycle-65 AC16 docstring (lines 134-136 of `cli_backend.py`) explicitly accepts the `in`-search timing leak as out-of-scope ("no remote attacker observes argv-construction timing"). AC2 inherits this acceptance. A future cycle could switch to constant-time comparison if a remote-observability path emerges.
- **OOS-4: `kb.utils.path_safety._open_no_follow` Windows ctypes path.** The current Windows fallback is `path.is_symlink()` (non-atomic). Cycle-65 Step 12 hard gate documented the ctypes `CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT)` issue. Re-attempting the atomic Windows path is a cycle-67+ candidate; AC5 does not touch this.
- **OOS-5: Other `_check_no_secrets_on_argv` callers.** AC2 modifies `_check_no_secrets_on_argv` in `cli_backend.py`. Cycle-65 confirmed no other call site uses the same regex pattern. A project-wide secret-scrub audit (other helpers across `src/kb/`) is OOS, deferred per cycle-65 OOS-10.
- **OOS-6: AC4 walker extension to other banned imports.** AC4 hardens the four cycle-65 AC18 banned modules (diskcache, litellm, pip, ragas). Future banned-import additions (e.g., new Dependabot alerts) would need to plug into the same `_walk_kb_for_banned_imports()` helper. The helper design should expose a `banned_modules: list[str]` parameter, but enforcing extensibility is OOS for cycle 66.

---

## Verdict

**APPROVE** — Tier-2 cleanup with no new trust boundaries.

Per honest analysis:

- **AC1** is structurally safe (dead-branch removal + comment correction). T1 is purely a test-correctness concern with low likelihood and low impact, fully covered by the AC1 test contract.
- **AC2** is the highest-stakes item (T2 — real argv leak of 5 backend keys) but is **purely additive scrub coverage** with the cycle-65 AC16 substring-containment mechanism unchanged. The only NEW threat introduced (T3 — self-DoS on legitimate prompts containing the literal value of the new keys) is the *intended* behavior of the substring scrub and is functionally equivalent to the existing 6-key behavior. T4 (future-revert hazard) is mitigated by parametrize-from-`CLI_BACKEND_ENV_INJECT` test design.
- **AC3** is a perf cache with explicit invalidation hooks; T5 is fully covered by the four behavioral test cases.
- **AC4** carries the highest residual risk (T6 — divergent-fail loss). The AC4 test contract's paired negative-control fixture per banned module is the load-bearing mitigation — Step 14 must verify each banned module has an `import-it-into-tmp-path` positive-control assertion, not just an absence-of-imports assertion.
- **AC5** closes a "false-flexibility" hazard (T7) with structural unconditional symlink rejection. No callers anywhere currently opt out of symlink rejection; removal is purely subtractive.

No condition required to escalate. The Step-5 design gate must verify three load-bearing test contracts:

1. **AC2 parametrize source:** `tests/test_cycle66_secret_scrub.py` parametrizes over `kb.config.CLI_BACKEND_ENV_INJECT.values()` (flattened) — NOT a literal list. (Closes T4.)
2. **AC4 negative-control fixture:** `tests/test_cycle66_cve_greps_consolidated.py` writes `tmp_path/_test_only.py` with each banned import in turn and asserts the consolidated walker's result dict CONTAINS the temp file. (Closes T6.)
3. **AC5 belt-and-suspenders:** `tests/test_cycle66_path_safety_symlink.py` includes BOTH the `inspect.signature` pin AND the behavioral symlink-rejection test. Per cycle-7 L4, signature-only would be vacuous; pairing closes the gap. (Closes T7 against partial revert.)

These are not Tier-escalation conditions — they are normal Step-5 design-gate checks that the test contracts already specify. Verdict APPROVE without conditions.
