# Cycle 67 — Threat Model + Dep-CVE Baseline

**Date:** 2026-05-07
**Branch:** `worktree-feat+cycle-67`
**Step:** 2 of 24 (dev-mimo-opus, Tier 2)
**Inputs:** `2026-05-07-cycle-67-requirements.md` (15 ACs)
**STRIDE coverage:** S(poofing) · T(ampering) · R(epudiation) · I(nformation Disclosure) · D(enial of Service) · E(levation of Privilege)

---

## Analysis

Per cycle-3 L7 (Opus 4.7 needs explicit CoT scaffolding), step through each AC and ask "what trust boundary does this diff actually cross?" before mapping STRIDE categories. Per cycle-11 L2 / cycle-23 L2, every threat must be verifiable by a behaviour assertion, not a source-string scan.

The 15 ACs split into three risk-tiered clusters:

- **High-risk (one boundary, structural change):** AC03 (chunked stdout cap with `SIGTERM`/`kill()` — replaces `subprocess.run` with `Popen`; preserves the same trust boundary), AC05 (sqlite_vec error sanitization — closes a Phase 6 cross-LLM cycle-64 LOW info-disclosure surface; one of two call sites already shipped at `embeddings.py:583-588` per cycle 65 AC14), AC07 (new filesystem-write surface — `wiki/_lint.yml` allowlist file load).
- **Medium-risk (new defensive checks / kill-switches):** AC04 (`KB_STRICT_PUBLISH=1` re-raise), AC06 (`KB_DISABLE_VECTORS=1` runtime kill-switch), AC11 (CI grep for `sk-ant-dummy` outside `ci.yml`), AC12 (docstring audit gate).
- **Low-risk (additive tests / docs / signature-preserving refactor):** AC01 (`MODEL_TIERS` proxy view — preserves bracket-access surface), AC02 (graph cache AST-grep), AC08 (autouse decorator meta-test), AC09 (snapshot paired negative-controls), AC10 (CI `--snapshot-update` reject), AC13 (README "Non-clone install" prose), AC14 (docs INDEX consistency check), AC15 (existing scrub design lock-in tests; no production change).

The most invasive AC (AC03) replaces buffered stdout capture with chunked Popen + reader thread + SIGTERM at cap. This is a behaviour-preserving boundary change — the trust boundary (CLI subprocess output capping for memory bounds) is the same; the implementation tightens memory bounds from "OOM-then-truncate" to "truncate-then-SIGTERM". No new external surface.

AC05 closes a Phase 6 cross-LLM cycle-64 LOW: the `sqlite_vec.load(conn)` call at `embeddings.py:665` (inside `build()`) was missed by cycle 65 AC14 (which fixed only `_connect()` at line 583-588). Same hazard class (T15 from cycle 65 — sqlite-vec extension load path leak); same mitigation pattern. AC05 is the second-call-site closure.

AC11 and AC12 are NEW security enforcement points (CI hard-gates on tracked-artifact contents and docstring API contract). Both are "fail-closed" workflow steps: if grep returns matches OR script exits non-zero, CI fails red.

AC07 introduces a new filesystem-read surface (`wiki/_lint.yml`) but with explicit fall-through-to-defaults on missing/malformed YAML — no crash, no privilege escalation, no path-traversal exposure (the file path is built from `wiki_dir / "_lint.yml"` which goes through the cycle 65 `_assert_under_project_root` validator chain in callers).

The remaining ACs are test-only or docs-only and have minimal STRIDE surface. Each still gets a threat entry below to satisfy the "≥1 threat per AC" requirement; vacuous-by-design ACs get a single low-likelihood/low-impact threat noting what they close vs what they prevent.

---

## Trust boundaries in scope

| Boundary | Affected ACs | Notes |
|---|---|---|
| **CLI subprocess output → Python process memory** | AC03 | Chunked Popen reader + `SIGTERM`/`kill()` at `MAX_CLI_STDOUT_BYTES`; preserves cycle-21 timeout/not_installed contract. |
| **MCP error response → MCP client** | AC05 | sqlite_vec `OperationalError` message embeds `.so`/`.dll` absolute path; sanitize at both call sites (`embeddings.py:584,665`). |
| **Compile pipeline → caller (CLI / MCP)** | AC04 | `KB_STRICT_PUBLISH=1` env converts swallowed publish exceptions into propagating exceptions. CALL-time read per cycle-19 L2. |
| **Hybrid query → vector index** | AC06 | `KB_DISABLE_VECTORS=1` env switches hybrid dispatch to BM25-only without uninstalling extras. CALL-time read. |
| **Filesystem (wiki/_lint.yml) → lint check** | AC07 | New read surface; lazy YAML loader with graceful fallback to `kb.config.DUPLICATE_SLUG_ALLOWLIST`. |
| **CI artifact (tracked file) → repo** | AC10, AC11 | `--snapshot-update` flag rejection (AC10); `sk-ant-dummy` literal scan outside `ci.yml` (AC11). Both fail-closed grep gates. |
| **`kb.__all__` API surface → external caller** | AC12 | Docstring audit script as CI gate; warning-only mode this cycle, hard-fail in cycle 68+ (per AC12 design split). |
| **Test sandbox → real `wiki/` `raw/` dirs** | AC08 | AC4 of cycle 65 set the sandbox; AC08 of cycle 67 freezes the `autouse=True` decorator structurally. |
| **graph/cache.py → callers (test-spy hook)** | AC02 | Cycle 65 AC17 set `__all__ = []`; AC02 of cycle 67 adds AST-grep test for 6th-caller drift (negative-control fixture). |
| **Snapshot tests → production output** | AC09, AC10 | Cycle 65 AC19 added paired negative-controls for 3 subjects; AC09 of cycle 67 generalises pattern + AC10 hardens CI to forbid `--snapshot-update`. |
| **Documentation (CLAUDE.md / README.md / INDEX.md) → contributor** | AC13, AC14 | AC13 prose addition; AC14 CI-enforced consistency between filesystem `docs/reference/`, `INDEX.md`, and CLAUDE.md table. |
| **Argv subprocess scrub → user prompt** | AC15 | Cycle 65 AC16 + cycle 66 AC2 established substring-of-env-value scrub. AC15 adds three lock-in tests against future "simplify-to-regex-on-argv" refactor. |
| **`MODEL_TIERS` lookup → env mutation** | AC01 | Cycle-19 L2 reload-leak hazard — `MODEL_TIERS["scan"]` snapshot at import time today. AC01 makes lookup call-time via `_ModelTiersView.__getitem__`. |

No new auth boundary, no new IAM/crypto/data/migration surface, no new external network surface. Per requirements §"Tier" line 13: boundary-preserving.

---

## STRIDE pass

### T1 (T) — `MODEL_TIERS["scan"]` snapshot bypass on env mutation

- **Category:** Tampering (cross-test bleed; routes test traffic to production tier defaults)
- **AC origin:** AC01
- **Vector:** A test does `monkeypatch.setenv("CLAUDE_SCAN_MODEL", "test-stub")` AFTER `import kb.config`. The current `MODEL_TIERS` literal dict at `config.py:237-241` was populated from `os.environ.get(...)` at import time, so the dict still holds the original value. Tests reading `kb.config.MODEL_TIERS["scan"]` (verified at `tests/test_llm.py:215-217`, `tests/test_v0912_phase393.py:423`, `tests/test_v099_phase39.py`) silently route traffic to `claude-haiku-4-5-20251001` instead of the intended stub, reaching the paid Anthropic API in tests. Same hazard class as cycle-19 L2 reload-leak.
- **Likelihood:** medium — three known call sites today; env-mutation tests are common.
- **Impact:** medium — paid-API traffic from tests is a billing surface; routing test traffic to production models also pollutes cycle-23 L2 divergent-fail tests.
- **Mitigation:** AC01 — `_ModelTiersView()` proxy with `__getitem__` delegating to `get_model_tier(tier)` reads `os.environ["CLAUDE_<TIER>_MODEL"]` at call time. Existing bracket-access surface preserved. Existing `tests/test_config_no_direct_model_tiers.py` "prefer get_model_tier()" hint stays valuable per requirements line 55.
- **Residual:** low — proxy iteration support is OPTIONAL per requirements line 51 ("only `__getitem__` mandatory"); a future caller doing `for tier in MODEL_TIERS:` could see stale results if the proxy doesn't implement `__iter__`. T1 covers this with the AC01 test contract: T01-A positive, T01-B revert-to-literal-dict divergent-fail, T01-C unknown-tier `ValueError` per `get_model_tier` contract.
- **Verification (Step 14):** `pytest tests/test_cycle67_model_tiers_view.py::test_call_time_lookup` — sets env after import, asserts `MODEL_TIERS["scan"] == new_value`; divergent-fail test reverts proxy to literal dict and asserts T01-A then fails RED.
- **Related lessons:** cycle-19 L2 (reload-leak rule); cycle-65 AC1/AC2 (call-time accessor migration for `KB_PROJECT_ROOT` and `_DEFAULT_MODEL_TIERS`); user memory `feedback_inspect_source_tests` (signature-only tests pass after revert).

### T2 (T) — `from kb.graph.cache import get_graph` 6th-caller bypass

- **Category:** Tampering (silent test-spy bypass)
- **AC origin:** AC02
- **Vector:** Cycle 64 AC9 introduced `kb.graph.cache.get_graph()` with strict cycle-18 L1 attribute-lookup-form discipline. Cycle 65 AC17 set `__all__ = []` and added the AST-grep test. AC02 of cycle 67 hardens the SAME guard with a paired NEGATIVE-CONTROL fixture (per cycle-23 L2 + user memory `feedback_inspect_source_tests`): write `from kb.graph.cache import get_graph` into `tmp_path/_offender.py`, assert the walker FAILS on it; then point at real `src/kb/`, assert PASSES. Without the negative-control, a future helper refactor that silently empty-passes the walker (e.g., `find_module_imports` returns empty list on parse error) goes undetected.
- **Likelihood:** medium — walker consolidations are a known false-pass-on-revert hazard per cycle-22 L5.
- **Impact:** high — bypassing the AST guard re-opens cycle-64 / cycle-18 L1 attribute-binding hazard: a 6th caller doing `from kb.graph.cache import get_graph` would silently bypass `monkeypatch.setattr(kb.graph.cache, "get_graph", ...)` test spies.
- **Mitigation:** AC02 — divergent-fail negative-control fixture in `tests/test_cycle67_graph_cache_callsite_form.py` per requirements lines 78-82. Reuses cycle-66 AC4 helper pattern (`tests/_helpers/ast_walk.py::find_module_imports` per cycle-66 Step-10 simplify).
- **Residual:** low — the negative-control closes the vacuous-test class. Future drift detected immediately.
- **Verification (Step 14):** `pytest tests/test_cycle67_graph_cache_callsite_form.py::test_negative_control_offender_detected tests/test_cycle67_graph_cache_callsite_form.py::test_real_src_kb_clean` — both must be green; manual revert-test by inserting `from kb.graph.cache import get_graph` into a fresh `src/kb/` file (revert) confirms RED.
- **Related lessons:** cycle-18 L1 (attribute-lookup-form); cycle-66 T6 (consolidated walker silent-pass); cycle-22 L5 (load-bearing tests).

### T3 (D) — Misbehaving CLI backend OOMs Python process before subprocess.run truncation

- **Category:** Denial of Service (memory exhaustion before downstream slice)
- **AC origin:** AC03
- **Vector:** A misbehaving CLI backend (e.g., `gemini` infinite-prompt-echo loop, attacker-controlled local CLI binary, runaway model-output stream) writes gigabytes to stdout before exiting. Current `subprocess.run(capture_output=True)` at `cli_backend.py:213-220` buffers ENTIRE stdout in memory before the `result.stdout[:MAX_CLI_STDOUT_BYTES]` slice at line 245 fires. Comment at lines 242-244 acknowledges as accepted risk per cycle-21 plan-gate gap 8. On a workstation with 16GB RAM, a backend writing 32GB of stdout OOMs the `kb` process before any cap fires.
- **Likelihood:** medium — accidental loops in local CLI backends are common; a misconfigured `gemini` / `kimi` / `qwen` backend can produce runaway output.
- **Impact:** high — process OOM kills the entire `kb` subprocess (or the MCP server); for `kb mcp` long-lived process, this is service-DoS.
- **Mitigation:** AC03 — replace `subprocess.run` with `Popen(stdout=PIPE, stderr=PIPE)` + reader thread accumulating stdout in 64KB chunks; once accumulated bytes >= `MAX_CLI_STDOUT_BYTES`, call `proc.terminate()` (POSIX) / `proc.kill()` (Windows) and stop reading. Stderr captured in parallel reader thread (separate, smaller cap). Final `proc.wait(timeout=...)` for exit code; preserves cycle-21 `LLMError(kind="timeout")` and `kind="not_installed"` contracts.
- **Residual:** low — small overrun (one chunk = 64KB) before SIGTERM lands is bounded by chunk size, not by full output. The reader thread's per-chunk allocation is the upper bound on memory growth past the cap.
- **Verification (Step 14):** `pytest tests/test_cycle67_cli_backend_chunked_cap.py::test_runaway_backend_terminated_at_cap` — backend that writes `b"A" * (MAX_CLI_STDOUT_BYTES * 3)` to stdout via `python -c "import sys; sys.stdout.buffer.write(b'A' * N)"`; assert returned stdout length == cap, assert subprocess was terminated (verify via `proc.returncode != 0` or platform-specific signal), assert `<2× cap` memory usage via `tracemalloc` snapshot before/after. Divergent-fail (T03-B): revert to `subprocess.run` and assert memory usage `>= 3× cap` (test then fails RED, proving the chunked path is doing the work).
- **Related lessons:** cycle-21 plan-gate gap 8 (accepted-risk acknowledgement); cycle-21 L4 (cli_backend.py threat-model docstrings); cycle-23 L2 (divergent-fail tests).

### T4 (R, T) — Silent publish failure masks compile success

- **Category:** Repudiation (compile reports green when publish failed); Tampering (downstream tooling reads `_publish/llms.txt` from a stale snapshot)
- **AC origin:** AC04
- **Vector:** `compile_wiki` post-success calls `auto_publish_after_compile` to emit `_publish/{llms,llms-full,graph,sitemap}.{txt,jsonld,xml}` (per CLAUDE.md cycle 64 AC6/AC14). Current `compiler.py:611-614` catches publish exceptions + logs warning + returns success. A long-running CI / cron job that compiles + publishes silently produces a STALE `_publish/` snapshot when publish errors (e.g., disk-full, permissions, AC14 dual-anchor symlink-rejection). Downstream (e.g., a `llms.txt` consumer) reads the stale snapshot. Repudiation: the compile log says "success" while the publish artifacts disagree. No CI alert fires.
- **Likelihood:** low — publish errors are rare in normal operation; failure modes are mostly disk-full or permission classes.
- **Impact:** medium — stale `_publish/` snapshot silently propagates to `llms.txt` consumers (LLM training data, search engines, downstream tools). The cycle-64 publish contract assumed atomic visibility.
- **Mitigation:** AC04 — at `auto_publish_after_compile` call site, read `os.environ.get("KB_STRICT_PUBLISH", "").strip()` at CALL time (cycle-19 L2 rule). When set to `"1"` or truthy non-empty, re-raise instead of swallow. Default behaviour (env unset) unchanged. Document in `kb compile --help` and `docs/reference/workflows.md`.
- **Residual:** low — env-unset default preserves back-compat with existing CI / cron callers. The strict mode is opt-in, gated by deliberate operator action.
- **Verification (Step 14):** `pytest tests/test_cycle67_strict_publish.py::test_default_swallows tests/test_cycle67_strict_publish.py::test_strict_reraises tests/test_cycle67_strict_publish.py::test_call_time_read` — three behavioural assertions covering each branch. T04-C (call-time) uses `monkeypatch.setenv` mid-test between two `compile_wiki` invocations, asserting the second invocation re-raises while the first did not — proves env not module-import-captured per cycle-19 L2.
- **Related lessons:** cycle-19 L2 (reload-leak); cycle-64 AC6 (auto-rebuild kill-switch precedent for `KB_DISABLE_VECTOR_AUTO_REBUILD`); user memory `feedback_migration_breaks_negatives` (one-shot migrations breaking legacy negative tests — strict-publish env-unset default avoids this class).

### T5 (I) — sqlite_vec.load() error leaks .so/.dll absolute path via MCP error response

- **Category:** Information Disclosure (filesystem layout, username, OS, arch)
- **AC origin:** AC05
- **Vector:** Adversary triggers an MCP `kb_query` call that walks through `VectorIndex.build()` on a system where the `sqlite-vec` wheel is missing/corrupted/wrong-glibc. `sqlite_vec.load(conn)` raises `sqlite3.OperationalError("/home/<user>/.venv/lib/python3.12/site-packages/sqlite_vec/vec0.linux-x86_64.so: cannot open shared object file")`. Currently at `embeddings.py:665` the call is bare (no try/except). The error propagates to the MCP `_mcp_error_boundary` (cycle 65 AC21) which calls `sanitize_error_text(exc)` — but that helper sanitizes known patterns (project-root paths, API keys); a raw absolute filesystem path INSIDE the venv is partially mitigated but not fully reliable for `/home/runner/work/...` style paths in CI artifacts or hosted-MCP futures. Cycle 65 AC14 closed the SAME hazard class at the OTHER call site (`embeddings.py:584`) but the `build()` site at line 665 was overlooked.
- **Likelihood:** low — wheel-load failures are rare in production; surface is widest on first-install / glibc mismatches / hosted MCP environments.
- **Impact:** medium — discloses username, virtualenv layout, OS, arch. Combined with cycle-65 T16 (MCP error-response traceback leak), an external MCP client can map host filesystem.
- **Mitigation:** AC05 — at both call sites (`embeddings.py:584,665`), wrap `sqlite_vec.load(conn)` in `try/except sqlite3.OperationalError as exc` → `raise RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel") from exc`. The `from exc` chain preserves traceback in local logs but the SERVER RESPONSE only sees the sanitized literal. Verified at threat-model time: `embeddings.py:583-588` already shipped this wrap in cycle 65 AC14; `embeddings.py:665` (inside `build()`) is the SECOND call site that AC05 closes.
- **Residual:** low — `from exc` traceback chain still has the path in local logs (acceptable per requirements line 117, local-only, not surfaced to MCP client). A future `_mcp_error_boundary` regression that calls `repr(exc.__cause__)` would re-leak; out-of-scope for cycle 67 (filed as cycle-66 T16 residual).
- **Verification (Step 14):** `pytest tests/test_cycle67_sqlite_vec_error_sanitised.py::test_build_path_no_path_leak` — monkeypatches `sqlite_vec.load` to raise `sqlite3.OperationalError("error loading C:\\Users\\Admin\\AppData\\foo.dll")`; calls `VectorIndex().build([...entries])`; asserts raised `RuntimeError` message matches the sanitized literal AND `"AppData"` not in message. Divergent-fail (T05-B): revert sanitization at line 665 → assert RED (path leaks). T05-A also covers `_connect()` at line 584 to lock cycle 65 AC14's behaviour.
- **Related lessons:** cycle-65 T15 (sqlite-vec extension load path leak — same hazard class, FIRST call site); cycle-65 AC21 (MCP error boundary — downstream sanitizer, defence-in-depth); cycle-23 L4 (same-class peer scan).

### T6 (D, T) — `KB_DISABLE_VECTORS=1` toggle leaks vector path on stale read

- **Category:** Denial of Service (intended fail-closed); Tampering (intended kill-switch toggle for incident response)
- **AC origin:** AC06
- **Vector:** Operator detects a vector-index corruption / dim-mismatch storm / sqlite-vec wheel issue and sets `KB_DISABLE_VECTORS=1` at runtime to fall back to BM25-only without uninstalling extras. Without AC06's call-time read, the env var is silently ignored if hybrid search code captured the value at import time. Operator's emergency mitigation fails silently — vector path keeps firing, dim-mismatch storm continues. Operationally critical for `kb mcp` long-lived servers where a process restart means dropped MCP connections.
- **Likelihood:** medium — vector-index incidents are a known class (cycle 25 dim-mismatch, cycle 64 auto-rebuild). The kill-switch is the well-trodden mitigation pattern (cf. cycle 64 AC6 `KB_DISABLE_VECTOR_AUTO_REBUILD`, cycle 64 AC14 `KB_DISABLE_COMPILE_AUTO_PUBLISH`).
- **Impact:** medium — without the kill-switch, operator must restart the MCP server, dropping in-flight MCP connections; with stale-read kill-switch, operator's mitigation is silently non-functional.
- **Mitigation:** AC06 — at the hybrid-dispatch entry, read `os.environ.get("KB_DISABLE_VECTORS", "").strip().lower() in ("1", "true", "yes")` at CALL time. When true, skip vector branch and fall back to BM25-only. Document in `CLAUDE.md` Quick Reference + `docs/reference/workflows.md` Query section.
- **Residual:** low — a stale BM25-only response is functionally equivalent to a no-vectors install; no information disclosure, no privilege escalation. Per requirements line 134, `VectorIndex.query` MUST NOT be invoked when env=1 (assertion via spy in T06-B).
- **Verification (Step 14):** `pytest tests/test_cycle67_disable_vectors_kill_switch.py::test_default_uses_vectors test_kill_switch_skips_vectors test_call_time_read` — three behavioural assertions per requirements lines 131-135. T06-C uses `monkeypatch.setenv` mid-test to flip the env; asserts behaviour switches without process restart per cycle-19 L2.
- **Related lessons:** cycle-19 L2 (call-time env read); cycle-64 AC6/AC14 (kill-switch precedent); CLAUDE.md Quick Reference (env-var-as-kill-switch pattern).

### T7 (T, E) — `wiki/_lint.yml` malformed YAML crashes lint pass / `_lint.yml` allowlist abuse

- **Category:** Tampering (malformed YAML denial of lint); Elevation of Privilege (an attacker who can plant `wiki/_lint.yml` via a malicious raw-source contributor could allowlist arbitrary slug-collisions, bypassing duplicate-detection)
- **AC origin:** AC07
- **Vector:**
  1. Malformed YAML — A user / attacker writes `wiki/_lint.yml` with invalid YAML (truncated quote, tab-indent error). Without graceful fallback, `kb lint` crashes hard, denying the entire lint pass. Per `feedback_test_failures` user memory: this would surface as confusing test failure ("YAML error") rather than the underlying allowlist gap.
  2. Allowlist abuse — A malicious contributor with write access to `wiki/_lint.yml` (e.g., via PR with raw-source ingestion that populates the file) allowlists `concepts/admin` vs `concepts/admin-real`, hiding a phishing-class duplicate-slug from `check_duplicate_slugs`.
- **Likelihood:** low — `wiki/_lint.yml` is operator-managed; AC07 design caps the allowlist to a list of pairs (no executable code, no path expansion). Vector 2 requires the attacker to also pass other lint gates (frontmatter validation, link checks) — the duplicate-slug check is one of many.
- **Impact:** medium — Vector 1 denies lint (CI-red, easily diagnosed); Vector 2 hides a duplicate-slug warning (subtle, low-leverage).
- **Mitigation:** AC07 — `kb.lint._lint_yaml.load_lint_config(wiki_dir)` is a LAZY reader: returns `{}` on file missing, returns `{}` + emits a `logger.warning` on YAML parse error (no crash). YAML schema is restricted to top-level `duplicate_slug_allowlist: [["a", "b"], ...]` — no `!!python/object` tags, parser uses `yaml.safe_load` (NOT `yaml.unsafe_load`). The lint check falls through to `kb.config.DUPLICATE_SLUG_ALLOWLIST` defaults if the file or key is absent. Per requirements line 144: file overrides config defaults; absent file = config-defaults back-compat.
- **Residual:** low — `yaml.safe_load` blocks Python-object instantiation (no RCE class). Vector 2 (allowlist abuse) reduces to "operator owns `wiki/_lint.yml`" trust assumption — same as operator owning `wiki/_categories.md`, `wiki/log.md`, etc.
- **Verification (Step 14):** `pytest tests/test_cycle67_lint_yaml_loader.py::test_absent_falls_through_to_config_defaults test_yaml_overrides_defaults test_malformed_yaml_warns_and_falls_through test_call_time_read_picks_up_edits` — four behavioural assertions per requirements lines 148-151. Negative-control: verify `yaml.safe_load` is the parser (not `yaml.load`) by asserting an `!!python/object` tag in the YAML raises `yaml.YAMLError` and falls through.
- **Related lessons:** cycle-19 L2 (call-time read for T07-D); cycle-21 L7 (defence-in-depth — YAML safe_load); user memory `feedback_test_failures` (test failure diagnosis path).

### T8 (T, R) — `_autouse_kb_path_sandbox` `autouse=True` removal cascades 200+ tests writing real wiki/

- **Category:** Tampering, Repudiation
- **AC origin:** AC08
- **Vector:** A future contributor refactoring `tests/conftest.py` (e.g., during a fixture-explicit-injection refactor, or accidentally during a merge conflict) flips `@pytest.fixture(autouse=True)` to `@pytest.fixture(autouse=False)` or removes the decorator entirely. All 200+ tests that ASSUMED autouse-redirect now write to `D:\Projects\llm-wiki-flywheel\wiki\` (developer machine) or `/home/runner/work/llm-wiki-flywheel/wiki/` (GHA). Damage is silent — pytest stays green, but `git status` after a test run shows production wiki contamination. Cycle 65 AC4 already added an AST-based meta-test (`tests/test_conftest_sandbox_guard.py`); AC08 of cycle 67 adds a SECOND independent meta-test (`tests/test_cycle67_conftest_invariants.py`) for same-class-peer scan resilience per cycle-23 L4.
- **Likelihood:** low — conftest refactors are infrequent; cycle 65 AC4 already shipped one meta-test.
- **Impact:** high — silent cascade to production wiki/raw write during routine `pytest` invocation. Repudiation: developer workflow shows green tests but contaminated state.
- **Mitigation:** AC08 — `tests/test_cycle67_conftest_invariants.py` AST-parses `tests/conftest.py`, locates `_autouse_kb_path_sandbox` `FunctionDef`, asserts decorator list contains `pytest.fixture(autouse=True)` keyword. Belt-and-suspenders against cycle 65 AC4 — different walker, different assertion shape. Per requirements lines 159-174.
- **Residual:** low — two independent meta-tests now guard the same invariant. A refactor that disables BOTH simultaneously is structurally implausible.
- **Verification (Step 14):** `pytest tests/test_cycle67_conftest_invariants.py::test_autouse_kb_path_sandbox_decorator_intact` — passes against current conftest. T08-B (divergent-fail): mutate conftest in `tmp_path` copy with `autouse=False`, run AST walker, assert FAILS RED.
- **Related lessons:** cycle-65 T4 (autouse silent removal — same-class threat); cycle-23 L4 (same-class peer scan); user memory `feedback_inspect_source_tests` (signature-only tests pass after revert — AC08 uses behavioural AST walk, not source-string scan).

### T9 (R) — Snapshot tautology: snapshot updates to match reverted production code

- **Category:** Repudiation (tests claim coverage they don't have)
- **AC origin:** AC09
- **Vector:** Cycle 64 captured syrupy snapshots for evidence-trail / Mermaid export / lint-report-structure. Snapshots were captured FROM the same code path under test. A revert of a production fix that the snapshot was supposedly guarding (e.g., a Mermaid escaping fix) is followed by `pytest --snapshot-update`; the snapshot updates to match the REVERTED behaviour and the test goes green. Cycle 65 AC19 added paired negative-control tests for the existing 3 subjects. AC09 of cycle 67 GENERALISES the pattern with a regression-revert guard (T09-B per requirements line 187) — trivially mutate the rendering function (e.g., add `+ "X"` to output); assert snapshot does NOT match. Reverts when production reverts.
- **Likelihood:** medium — snapshot-tautology is a known false-pass-on-revert hazard per cycle-22 L5 / user memory `feedback_inspect_source_tests`.
- **Impact:** medium — snapshot tests claim coverage they don't have; a future regression of a snapshot-guarded property silently passes.
- **Mitigation:** AC09 — for each existing snapshot subject, add T09-A (mutated input) + T09-B (regression-revert guard). Both must pass under default `pytest`. Neither may pass under `--snapshot-update` (defensive — paired with AC10 CI gate).
- **Residual:** low — paired negative-control + regression-revert guard closes the tautology class for the 3 known subjects. Future subjects must follow the same pattern (AC09 establishes the convention).
- **Verification (Step 14):** `pytest tests/test_cycle64_snapshots.py` — all paired tests green; manually revert the production fix that one snapshot guards (e.g., add `+ "X"` to Mermaid renderer output), run pytest, confirm RED; revert.
- **Related lessons:** cycle-65 T21 (snapshot tautology); cycle-22 L5 (load-bearing tests); user memory `feedback_inspect_source_tests` (signature-only false-pass).

### T10 (T) — CI accepts `--snapshot-update` and snapshots auto-regenerate to match reverted code

- **Category:** Tampering (CI silently accepts a maintainer flag flip)
- **AC origin:** AC10
- **Vector:** A maintainer adds `--snapshot-update` to a workflow step (intentionally for a one-time regen, then forgets to remove; or accidentally via merge conflict). Snapshot tests pass trivially in CI because every run regenerates the snapshot to match current output. Combined with T9 (snapshot tautology), this neutralises the entire snapshot-test class.
- **Likelihood:** low — `--snapshot-update` is rarely added to CI; cycle 65 AC19 already documented the rule.
- **Impact:** medium — silent neutralisation of cycle 64's 3 snapshot subjects + AC09's expanded coverage.
- **Mitigation:** AC10 — CI step BEFORE pytest greps `.github/workflows/` for `--snapshot-update`; fails red on any match. Per requirements lines 198-204.
- **Residual:** low — grep gate is fail-closed. A future contributor adding `--snapshot-update` to a workflow step gets immediate CI-red.
- **Verification (Step 14):** Read `.github/workflows/ci.yml` — confirm new "Reject --snapshot-update in workflow" step present BEFORE pytest invocation. PR diff inspection at Step 20.
- **Related lessons:** cycle-65 T21 / AC19 (paired negative-control + drop-flag-from-CI); cycle-22 L5; user memory `feedback_dependabot_pre_merge` (CI gate model — fail-closed defaults).

### T11 (I) — `sk-ant-dummy` CI placeholder leaks into recorded cassette / VCR / pytest-snapshot

- **Category:** Information Disclosure (CI artifact pollution)
- **AC origin:** AC11
- **Vector:** A future test uses `vcrpy` / `pytest-recording` / `syrupy` to record an HTTP interaction. Test runs in CI with `ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only` set. Test mocks at the WRONG layer (e.g., wraps `httpx.Client.send` but not the `Anthropic` SDK constructor) — the SDK reads the dummy key from env and embeds it in the `Authorization: Bearer sk-ant-dummy-key-for-ci-tests-only` header. The recorded cassette / VCR YAML / syrupy snapshot contains the dummy literal. Cassette is committed to repo. Two harms: (a) it pollutes the real-key search space, (b) future test refactors that swap the dummy for a live key under `pytest --record-mode=once` would silently leak the LIVE key (the `sk-ant-dummy` literal in the cassette is the hint that the recording boundary was wrong).
- **Likelihood:** low — VCR/cassette tests are not currently in the repo; threat is preemptive.
- **Impact:** medium — the dummy itself is harmless but signals a mocking-layer error that could bring real keys into the cassette under `--record-mode=once`.
- **Mitigation:** AC11 — CI step that fails if `sk-ant-dummy` appears in any tracked file except `.github/workflows/ci.yml`. Per requirements lines 213-220 (uses `git ls-files | xargs grep -l "sk-ant-dummy" | grep -v "^\.github/workflows/ci\.yml$"`).
- **Residual:** low — fail-closed grep gate. A future test that writes `sk-ant-dummy` into a tracked artifact gets immediate CI-red.
- **Verification (Step 14):** Read `.github/workflows/ci.yml` — confirm the new "No dummy API key in tracked files" step present. Step 11 SAST grep verifies the file shows in workflow at Step 17 doc-update sanity check.
- **Related lessons:** cycle-65 T18 (CI dummy-key recorded in cassettes); user memory `feedback_no_secrets_in_code` (.env for real, split-string for tests); user memory `feedback_dependabot_pre_merge` (CI fail-closed pattern).

### T12 (R) — `kb.__all__` API surface lacks Args/Returns/Raises docstrings; downstream callers misuse contract

- **Category:** Repudiation (documentation claims contract that the code doesn't carry)
- **AC origin:** AC12
- **Vector:** `kb/__init__.py` is a 67-line lazy `__getattr__` shim. Real Args/Returns/Raises sections must live on the underlying functions in `kb/ingest/pipeline.py`, `kb/compile/__init__.py`, `kb/query/__init__.py`, `kb/graph/__init__.py`. Whether they actually carry Google-style sections is unverified. A downstream caller (external user `pip install kb` + `from kb import ingest_source`) sees the shim's docstring (or no docstring at all) and infers the contract from name + type hints; misuse follows (e.g., passes a `str` URL to `ingest_source(source_path: Path, ...)` despite Path-only contract).
- **Likelihood:** low — current callers are mostly internal; external `pip install kb` users are rare.
- **Impact:** low — misuse produces immediate `ValidationError` / `TypeError` rather than silent corruption; the contract gap is documentation hygiene, not runtime safety.
- **Mitigation:** AC12 — `scripts/audit_docstrings.py` imports `kb`, walks `kb.__all__`, resolves each name to its underlying function, parses `__doc__` via `ast.get_docstring` + simple regex (`r"^\s*Args:"m`, `r"^\s*Returns:"m`, `r"^\s*Raises:"m`). Fails if any function lacks `Args:` (when params present) AND `Returns:` (when non-None return). `Raises:` only required if function body has a `raise` outside `try`. Per requirements line 232.
- **Residual:** low — Step-5 design gate decides whether to ship hard-fail OR warning-only mode in cycle 67 (per requirements lines 240-241); default warning-only with hard-fail in cycle 68+. Any false-positives (rare per AC12 design's regex precision) emit warnings rather than blocking CI.
- **Verification (Step 14):** `pytest tests/test_cycle67_audit_docstrings.py::test_script_against_current_src_kb test_fixture_function_with_stripped_docstring_reported` per requirements lines 235-238. T12-C (CI integration): workflow runs script as a step; PR review at Step 20 verifies green / warning-mode acknowledged.
- **Related lessons:** cycle-65 T14 (silent invalidation of accepted-CVE rationale — same hazard class: documentation says X, code does Y); user memory `feedback_inspect_source_tests` (signature-only tests).

### T13 (T) — `pip install kb` user (non-clone) silently resolves data paths inside venv site-packages

- **Category:** Tampering (test-side behaviour drift); user-experience drift (not a security threat per se, but related to project-root resolution boundary)
- **AC origin:** AC13
- **Vector:** A user runs `pip install kb` (without cloning the repo, e.g., for use as a library or MCP server in a separate project tree) and invokes `kb compile`. `kb.config.get_project_root()` resolves project root via `cwd` → `pyproject.toml` walk → installed-file location heuristic. Without `KB_PROJECT_ROOT` set, the heuristic finds the venv `site-packages/kb/` location (wrong) instead of the user's intended wiki directory. Data paths (`.data/`, `wiki/`, `raw/`) silently land inside `venv/lib/python3.12/site-packages/`. User confusion ensues; on `pip uninstall kb`, the data is wiped.
- **Likelihood:** low — most current users are repo-clone-based; the `pip install kb` (non-clone) path is rare.
- **Impact:** low — data loss on uninstall is recoverable from git for repo-clone users; for non-clone users, AC13 prevents the misconfiguration BEFORE it happens by surfacing `KB_PROJECT_ROOT` in README. No security exposure.
- **Mitigation:** AC13 — README "Non-clone install (pip install)" section between "Quick Start" and "Configuration", documenting `export KB_PROJECT_ROOT=/path/to/your/kb` (Unix) / `$env:KB_PROJECT_ROOT = "C:\path\to\your\kb"` (PowerShell). Per requirements lines 244-263.
- **Residual:** low — README documentation does not enforce; a non-reading user still hits the surface. Out-of-scope for AC13: failing-loud at runtime when project_root resolves inside `site-packages/` (filed as cycle-68+ candidate).
- **Verification (Step 14):** Read `README.md` — confirm new section between "Quick Start" and "Configuration". PR diff inspection at Step 20 (no automated test required for prose).
- **Related lessons:** cycle-65 AC1 (`get_project_root()` accessor — call-time env precedence); user memory `feedback_env_example_api_key_optional` (README accuracy hygiene).

### T14 (R) — Drift between filesystem `docs/reference/`, `INDEX.md`, and CLAUDE.md table

- **Category:** Repudiation (documentation index claims coverage it doesn't have)
- **AC origin:** AC14
- **Vector:** Hand-maintained `docs/reference/INDEX.md` exists; CLAUDE.md has a "Detailed Documentation" table mapping topic → file. Both are hand-maintained; drift is silent. Three failure modes: (a) new `*.md` added to `docs/reference/` not added to `INDEX.md` or CLAUDE.md table → docs orphaned; (b) `INDEX.md` references a file that no longer exists → broken link; (c) CLAUDE.md table references a file in `docs/reference/` that `INDEX.md` doesn't list → mismatch.
- **Likelihood:** medium — hand-maintained tables drift naturally on push.
- **Impact:** low — orphaned docs are still findable via filesystem; broken links degrade UX but don't expose data.
- **Mitigation:** AC14 — `scripts/check_docs_index.py` reads `docs/reference/*.md`, extracts paths from `INDEX.md` and from CLAUDE.md's table (regex `\[.*?\]\(docs/reference/(.*?\.md)\)`), asserts every filesystem entry appears in BOTH lists. CI runs script on push. Per requirements lines 271-274.
- **Residual:** low — fail-closed CI gate. A future contributor adding a new `docs/reference/foo.md` without updating both indexes gets immediate CI-red.
- **Verification (Step 14):** `pytest tests/test_cycle67_docs_index_consistency.py::test_current_state_consistent test_missing_from_index_fails test_extra_md_fails` per requirements lines 276-278.
- **Related lessons:** cycle-65 AC20 (docs/reference INDEX.md generation); user memory `feedback_signature_drift_verify` (caller-grep checkpoint — same hazard class: file moved or renamed without updating callers/index).

### T15 (I) — `_check_no_secrets_on_argv` substring scrub: design-intent regression to argv-regex

- **Category:** Information Disclosure (regression-class threat)
- **AC origin:** AC15
- **Vector:** Cycle 65 AC16 + cycle 66 AC2 established that `_check_no_secrets_on_argv` iterates known env-var keys and scans argv for ACTUAL VALUE substrings (verified at `cli_backend.py:132-157`). Mimo r4 A claimed "self-DoS via generic regex match on full argv" — VERIFIED INCORRECT per requirements line 286. The function does NOT regex-match argv. AC15 backstops against a future maintainer who might "simplify" the scan to a regex-on-argv (which would re-introduce the false-positive class mimo claimed exists today).
- **Likelihood:** low — the design intent is documented in the docstring (cli_backend.py:136-143); a contributor reading it would not regex-simplify without cause.
- **Impact:** low — regex-simplification is the cycle-21 T8 hazard (self-DoS on legitimate prompts that DISCUSS key formats). AC15 is preventative, not corrective.
- **Mitigation:** AC15 — three test cases lock the design intent: T15-A (bare equality) — argv element == secret raises `LLMError`; T15-B (embedded in flag) — `f"Authorization: Bearer {secret}"` raises (split-string token construction per `feedback_no_secrets_in_code`); T15-C (false-positive guard) — argv element == ENV-VAR-NAME (not value) does NOT raise. Per requirements lines 286-293.
- **Residual:** low — the three tests pin the exact behavioural shape. A regex-simplification would fail T15-C immediately.
- **Verification (Step 14):** `pytest tests/test_cycle67_secret_scrub_intent.py::test_bare_equality_blocked test_embedded_in_flag_blocked test_key_name_not_value_allowed` — three behavioural assertions per requirements lines 290-291. Divergent-fail: simplify the scan to a generic regex pattern (e.g., `r"sk-[A-Za-z0-9_\-]{10,}"`) and assert T15-C fails RED.
- **Related lessons:** cycle-21 T8 (self-DoS regex over-trigger — mitigated by cycle-65 AC16); cycle-66 T3 (substring-scrub self-DoS on legitimate prompts — accepted residual); cycle-23 L2 (divergent-fail tests); user memory `feedback_no_secrets_in_code` (split-string token construction).

---

## Risk ranking

Threats ranked by `likelihood × impact`. Closed-by-AC entries reflect post-cycle residual risk.

| Rank | ID | likelihood × impact | Notes |
|---|---|---|---|
| 1 | **T3** | medium × high | AC03 chunked stdout cap is the only structural-change AC. `subprocess.run` → `Popen` boundary preserved but body redesigned. Highest implementation risk per requirements line 360 (commit-order #15). |
| 2 | **T9** | medium × medium | AC09 snapshot paired negative-control + regression-revert guard. Tautology class is well-known (cycle-22 L5). |
| 3 | **T1** | medium × medium | AC01 `MODEL_TIERS` proxy view. Three known direct callers; preserves bracket-access surface. |
| 4 | **T6** | medium × medium | AC06 `KB_DISABLE_VECTORS` runtime kill-switch. Operational mitigation surface. |
| 5 | **T2** | medium × high (CLOSED by AC02) | Walker false-pass-on-revert; closed by negative-control fixture. |
| 6 | **T8** | low × high (CLOSED by AC08) | Autouse silent removal cascade; double-meta-test guard. |
| 7 | **T5** | low × medium (CLOSED by AC05) | sqlite_vec path leak (second call site). |
| 8 | **T14** | medium × low (CLOSED by AC14) | Docs INDEX drift. |
| 9 | **T11** | low × medium (CLOSED by AC11) | CI dummy-key cassette pollution (preemptive). |
| 10 | **T7** | low × medium (CLOSED by AC07) | `_lint.yml` malformed YAML / allowlist abuse. |
| 11 | **T4** | low × medium (CLOSED by AC04) | Silent publish failure. Strict mode opt-in. |
| 12 | **T10** | low × medium (CLOSED by AC10) | CI `--snapshot-update` rejection. |
| 13 | **T15** | low × low (preventative) | Argv scrub design-intent lock-in. |
| 14 | **T12** | low × low (CLOSED warning-mode by AC12) | Docstring audit; warning-only this cycle. |
| 15 | **T13** | low × low (CLOSED by AC13) | README non-clone install prose. |

**Tier escalation check:** No threat in the cycle-67 set crosses the Tier-3 threshold. AC03 is the highest-stakes item but is a boundary-preserving refactor (same trust boundary, tighter implementation). Per requirements §"Tier" line 13 and user memory `feedback_auto_approve` authorising Opus subagent gating, **NO Tier-3 escalation required**.

---

## Out-of-scope (verified mitigated in prior cycles)

Per cycle-7 L4 (avoid scope confusion in Step 14), the following same-class-peer threats are NOT closed by AC1-AC15 but live in the same threat surface — Step 14 must NOT verify these and must NOT flag their absence as a regression. Each echoes the requirements doc's "Out-of-scope (verified shipped in cycle ≤66)" section per requirements lines 295-311.

- **OOS-1: SSRF mitigation in URL → external CLI argv** (mimo r4 B). VERIFIED STALE — `lint/fetcher.py:100-149,242,366-421` already has DNS-resolve + IP filtering + scheme allowlist. `crawl4ai`/`yt-dlp` not imported in `src/kb/`. `ingest_source(source_path: Path, ...)` takes `Path`, not URL. Closed in cycle ≤59. Step 17 BACKLOG cleanup moves to "Resolved Phases".
- **OOS-2: `KB_PROJECT_ROOT` call-time accessor** (mimo r5 Q1). VERIFIED SHIPPED in cycle 65 AC1 as `get_project_root()` (config.py:70).
- **OOS-3: `AUGMENT_ALLOWED_DOMAINS` call-time accessor** (mimo r5 Q5). VERIFIED SHIPPED in cycle 65 AC3 as `get_allowed_domains()` (config.py:103).
- **OOS-4: `_DEFAULT_MODEL_TIERS` deletion** (mimo r5 Q2). MIS-IDENTIFIED. The actual stale-mechanism is the LEGACY `MODEL_TIERS` dict at config.py:237-241 — fixed by AC01 of cycle 67. `_DEFAULT_MODEL_TIERS` (a dict literal of hardcoded IDs) is the source of truth and stays.
- **OOS-5: MCP error boundary** (Phase 6 R2 MEDIUM, mimo r4 E). VERIFIED SHIPPED across `mcp/{core,ingest,quality}.py` as `_mcp_error_boundary` decorator (cycle 65 AC21). Cycle 65 OOS-3 noted `mcp/{browse,compile,health}.py` carry their own error handling (out of scope).
- **OOS-6: `_validate_page_id` Windows trailing dot/space** (Phase 6 cycle-64 HIGH). VERIFIED SHIPPED at `mcp/app.py:277` (cycle 65 AC6).
- **OOS-7: `_validate_page_id` `:` Windows-illegal-char** (Phase 6 cycle-64 MEDIUM). VERIFIED SHIPPED at `mcp/app.py:180` `_WINDOWS_ILLEGAL_CHARS_RE`.
- **OOS-8: TOCTOU on `rebuild_indexes`** (Phase 6 cycle-64 MEDIUM). VERIFIED SHIPPED via `_open_no_follow` (path_safety.py:103) used at compiler.py:757,775,801.
- **OOS-9: Validator-contract drift** (Phase 6 cycle-64 MEDIUM). VERIFIED SHIPPED via `_assert_under_project_root` (path_safety.py:31) — cycle 65 AC9 + cycle 66 AC5 dropped `allow_symlinks` kwarg.
- **OOS-10: `query/embeddings.py` multi-process race** (Phase 6 cycle-64 LOW). VERIFIED SHIPPED via `file_lock(target_path.with_suffix(".db.lock"))` at embeddings.py:661.
- **OOS-11: conftest auto-discovery for lru_cache** (mimo r2 Q2). VERIFIED SHIPPED at conftest.py:336-347 via `for mod_name, mod in list(sys.modules.items())` + `getattr(attr, "cache_clear", None)`.
- **OOS-12: `lint/fetcher.py` `TRAFILATURA_DOWNLOAD_NO_CACHE=1`** (mimo r6 Q5). VERIFIED SHIPPED at fetcher.py:33.
- **OOS-13: `requirements.txt` GitPython upper bound** (mimo r6 Q1). VERIFIED SHIPPED as `GitPython>=3.1.47,<3.2` at requirements.txt:82. NOTE: cycle 67 Step-2 baseline surfaced a NEW advisory CVE-2026-44244 against 3.1.47; see Dep-CVE Baseline section below.
- **OOS-14: `docs/reference/INDEX.md` existence** (mimo r3 NEW). VERIFIED EXISTS. AC14 of cycle 67 adds the consistency check, not the file itself.
- **OOS-15: `mcp_server.py` shim deletion** (Phase 6 R2 LOW, mimo r1 Q5). DEFERRED. Pyproject already targets `kb.mcp:main`. The shim is a 6-line back-compat re-export. Low-value churn for cycle 67.

---

## Dep-CVE baseline (Step 2 snapshot)

**Captured:** 2026-05-07 22:06 NZST (project-relative artifact at `.data/cycle-67/pip-audit-baseline.json`, ~26KB).

**Method:** `D:/Projects/llm-wiki-flywheel/.venv/Scripts/pip-audit.exe --format=json --output=...` against the live installed environment (no `-r requirements.txt` per cycle-22 L1 + SECURITY.md line 36 — avoids `ResolutionImpossible` on `arxiv 2.4.1` ↔ `requests 2.33.0`).

**Findings: 4 known vulnerabilities in 4 packages (323 deps audited; 0 skipped).**

| Package | Version | Advisory | Aliases | Fix versions | First seen vs cycle 66 |
|---|---|---|---|---|---|
| `diskcache` | 5.6.3 | `CVE-2025-69872` | `GHSA-w8v5-vhqr-4h9v` | none (no upstream patch) | CARRY-OVER from cycle ≤59 |
| `gitpython` | 3.1.47 | `CVE-2026-44244` | `GHSA-v87r-6q3f-2j67` | 3.1.49 | **NEW since cycle 66** |
| `mako` | 1.3.11 | `CVE-2026-44307` | `GHSA-2h4p-vjrc-8xpq` | 1.3.12 | **NEW since cycle 66** |
| `python-multipart` | 0.0.26 | `CVE-2026-42561` | `GHSA-pp6c-gr5w-3c5g` | 0.0.27 | **NEW since cycle 66** |

**Drift vs cycle 66 baseline:**

- `diskcache` — UNCHANGED (carry-over; SECURITY.md line 29 narrow-role rationale stands; `tests/test_security_cve_greps.py` enforces zero direct imports).
- `pip` — RESOLVED. Cycle 66 carried `pip 26.0.1` CVE-2026-3219 + later CVE-2026-6357. SECURITY.md line 33 confirms cycle 66 upgraded `pip>=26.1` in CI; cycle 67 venv now ships a patched `pip` (no advisory in this baseline).
- `gitpython` — **NEW** advisory (configparser newline injection). FIX AVAILABLE (3.1.49). Action: bump pin in `requirements.txt` (cycle 67 Step 11.5 opportunistic-patch slot per SECURITY.md "Re-check Cadence"). The cycle 65 AC11 `GitPython>=3.1.47,<3.2` ceiling SUFFICES (3.1.49 < 3.2) — straight bump from 3.1.47 to 3.1.49.
- `mako` — **NEW** advisory (Windows backslash directory traversal in `Template.__init__`). FIX AVAILABLE (1.3.12). Mako is a transitive (likely via `alembic` if present, or a docs/templating extra). Action: bump pin or accept with verification grep that `from mako` returns zero direct imports in `src/kb/` (preferred — track upstream).
- `python-multipart` — **NEW** advisory (DoS in multipart part header parsing). FIX AVAILABLE (0.0.27). Transitive (likely via `fastapi`/`starlette`/`mcp` SDK). Action: same as mako — bump or accept-with-grep.

**SECURITY.md updates needed at Step 17:**
1. Update "Last reviewed" date to 2026-05-07.
2. Step 11.5 opportunistic-patch slot per cycle-34 four-gate model (user memory `feedback_dependabot_pre_merge`): bump `GitPython` to `==3.1.49,<3.2` in `requirements.txt`; bump `mako` and `python-multipart` if direct deps OR add narrow-role rows to "Known Advisories" table if transitive.
3. Add new `--ignore-vuln=` entries to `.github/workflows/ci.yml` `pip-audit` step IFF accepting the advisories (otherwise the patch closes the alert).

**Skipped packages:** zero (the local editable installs `llm-knowledge-base` / `llm-wiki-flywheel` ARE present in the audit list — cycle 66 baseline noted these; current baseline doesn't skip them, suggesting the venv layout differs slightly. Verify at Step 11 PR-introduced-CVE diff.)

**Cycle 67 introduces NO new dependencies** (15-AC scope is pure src/tests/CI/docs with no `requirements.txt` / `pyproject.toml` change beyond the opportunistic CVE bumps in Step 11.5). Therefore Step 11 PR-introduced-CVE diff is expected to be empty (or contain ONLY the Step-11.5 CVE-fix patches); Step 14 verification is "no NEW advisories surfaced during the cycle wall-clock window" (cycle-22 L4 late-arrival hazard).

---

## Step 14 verifier checklist

Per cycle-22 L5, each item below maps 1:1 to one regression test (or test-class) Step 14 (mimocoding-rescue @ mimo-v2.5-pro) must verify. Format: `[T-id] [AC-origin] verification command(s)`.

- **T1, AC01:** `pytest tests/test_cycle67_model_tiers_view.py::test_call_time_lookup test_unknown_tier_raises_value_error test_revert_to_dict_diverges` — three behavioural assertions; T01-A positive, T01-B revert-to-dict divergent-fail, T01-C unknown-tier `ValueError`. AST-walk verifies `MODEL_TIERS = _ModelTiersView()` line at config.py (NOT a literal dict).
- **T2, AC02:** `pytest tests/test_cycle67_graph_cache_callsite_form.py::test_real_src_kb_clean test_negative_control_offender_detected` — both green; manual revert-test by inserting `from kb.graph.cache import get_graph` in fresh `src/kb/` file confirms RED.
- **T3, AC03:** `pytest tests/test_cycle67_cli_backend_chunked_cap.py::test_runaway_backend_terminated_at_cap test_under_cap_returns_intact test_back_compat_existing_tests_green` — three behavioural assertions including memory-tracemalloc bound. Divergent-fail: revert to `subprocess.run` and assert RED.
- **T4, AC04:** `pytest tests/test_cycle67_strict_publish.py::test_default_swallows test_strict_reraises test_call_time_read` — three behavioural assertions; T04-C uses `monkeypatch.setenv` mid-test to prove call-time read.
- **T5, AC05:** `pytest tests/test_cycle67_sqlite_vec_error_sanitised.py::test_build_path_no_path_leak test_connect_path_no_path_leak` — two call-site assertions (lines 584 + 665); divergent-fail revert to bare call confirms RED on each.
- **T6, AC06:** `pytest tests/test_cycle67_disable_vectors_kill_switch.py::test_default_uses_vectors test_kill_switch_skips_vectors test_call_time_read` — three behavioural assertions; T06-B uses spy on `VectorIndex.query` to assert NOT invoked.
- **T7, AC07:** `pytest tests/test_cycle67_lint_yaml_loader.py::test_absent_falls_through_to_config_defaults test_yaml_overrides_defaults test_malformed_yaml_warns_and_falls_through test_call_time_read_picks_up_edits test_yaml_safe_load_blocks_python_object` — five behavioural assertions; the safe_load assertion verifies `!!python/object` tag rejection.
- **T8, AC08:** `pytest tests/test_cycle67_conftest_invariants.py::test_autouse_kb_path_sandbox_decorator_intact` — AST-walk on `tests/conftest.py`; T08-B (divergent-fail) mutates conftest copy with `autouse=False` and asserts FAILS.
- **T9, AC09:** `pytest tests/test_cycle64_snapshots.py` — paired tests for each of 3 subjects (evidence-trail / Mermaid / lint-report); T09-A (mutated input) + T09-B (regression-revert guard); manual revert-test confirms RED.
- **T10, AC10:** Read `.github/workflows/ci.yml` — confirm "Reject --snapshot-update in workflow" step BEFORE pytest invocation; PR diff inspection at Step 20.
- **T11, AC11:** Read `.github/workflows/ci.yml` — confirm "No dummy API key in tracked files" step present; Step 17 doc-update sanity check verifies file path filter excludes `ci.yml` itself.
- **T12, AC12:** `pytest tests/test_cycle67_audit_docstrings.py::test_script_against_current_src_kb test_fixture_function_with_stripped_docstring_reported` — script exits 0 if all clean OR exits 1 with parsable JSON list of offenders; CI integration at workflow level.
- **T13, AC13:** Read `README.md` — confirm "Non-clone install (pip install)" section between "Quick Start" and "Configuration"; PR diff inspection at Step 20.
- **T14, AC14:** `pytest tests/test_cycle67_docs_index_consistency.py::test_current_state_consistent test_missing_from_index_fails test_extra_md_fails` — three behavioural assertions; CI integration at workflow level.
- **T15, AC15:** `pytest tests/test_cycle67_secret_scrub_intent.py::test_bare_equality_blocked test_embedded_in_flag_blocked test_key_name_not_value_allowed` — three behavioural assertions per requirements lines 290-291; tokens use split-string construction per `feedback_no_secrets_in_code`.

**Cross-AC verifications (Step 14 must also confirm):**

- Full pytest suite green (3176+ baseline per requirements line 7) per cycle-22 L3 — NOT an isolated subset.
- Coverage delta: touched-file ≥90%, repo-total regression ≤0.5pp per requirements line 322.
- `git ls-files | xargs grep -l "sk-ant-dummy" | grep -v "^\.github/workflows/ci\.yml$"` returns no matches (AC11 self-test).
- `D:/Projects/llm-wiki-flywheel/.venv/Scripts/pip-audit.exe --format=json` against final HEAD venv shows ≤4 advisories (no NEW since baseline at this document time, plus any Step-11.5 patches that closed the 3 NEW carry-overs — gitpython, mako, python-multipart).

**Step 14 must NOT verify (per cycle-7 L4 / out-of-scope list above):**

- SSRF mitigation in URL → external CLI argv (OOS-1).
- `KB_PROJECT_ROOT` / `AUGMENT_ALLOWED_DOMAINS` call-time accessors (OOS-2, OOS-3).
- MCP error boundary on `mcp/{core,ingest,quality}.py` (OOS-5).
- `_validate_page_id` Windows trailing-dot/space, `:`, illegal-char gates (OOS-6, OOS-7).
- TOCTOU on `rebuild_indexes` (OOS-8).
- Validator-contract drift (OOS-9).
- `query/embeddings.py` multi-process race (OOS-10).
- conftest auto-discovery for lru_cache (OOS-11).
- `TRAFILATURA_DOWNLOAD_NO_CACHE=1` (OOS-12).
- `requirements.txt` GitPython upper bound (OOS-13 — but the NEW `CVE-2026-44244` patch IS in scope at Step 11.5).
- `docs/reference/INDEX.md` existence (OOS-14 — but the consistency check IS in scope via AC14).
- `mcp_server.py` shim deletion (OOS-15).

---

## Verdict

**APPROVE** — Tier-2 cleanup with no new trust boundaries. All 15 ACs map to a single cycle-N L lesson chain (cycle-19 L2 reload-leak, cycle-22 L5 load-bearing, cycle-23 L2 divergent-fail, cycle-23 L4 same-class peer scan, cycle-65 AC9 dual-anchor + symlink-rejection, cycle-66 AC2 frozenset derivation pattern). No condition required to escalate.

The Step 5 design gate must verify three load-bearing test contracts:

1. **AC03 boundary preservation:** `tests/test_cycle67_cli_backend_chunked_cap.py` includes the `tracemalloc`-based memory bound assertion AND the `subprocess.terminated` (or platform-equivalent return-code) assertion AND back-compat tests for cycle-21 `LLMError(kind="timeout")` + `kind="not_installed"` paths. Per requirements lines 89-94.
2. **AC09 paired regression-revert guard:** Each of the 3 cycle-64 snapshot subjects gets BOTH a mutated-input divergence test AND a "trivial production mutation reverts when production reverts" test. Per requirements lines 184-188 — both must pass under default `pytest`; neither under `--snapshot-update`.
3. **AC07 YAML safe-load enforcement:** `tests/test_cycle67_lint_yaml_loader.py` includes the `!!python/object` tag rejection assertion (proves `yaml.safe_load`, not `yaml.load`). Per cycle-21 L7 defence-in-depth.

These are normal Step-5 design-gate checks that the test contracts already specify (per requirements lines 88-95, 187-188, 150-151). Verdict APPROVE without conditions.

The cycle-67 Step-2 baseline surfaces 3 NEW dependency advisories (`gitpython`, `mako`, `python-multipart`) all with patches available — Step 11.5 opportunistic-patch slot per SECURITY.md cadence. SECURITY.md update at Step 17 is required.
