# Cycle 65 — Design Eval R1 (Opus, eng-mgr lens)

**Cycle:** 65
**Reviewer:** Opus 4.7 (main session, eng-mgr lens — `Skill("plan-eng-review")` style)
**Inputs:** Step 1 requirements (23 ACs / 14 files), Step 2 threat model (T1-T21 + C1-C23 + OOS-1..10), Step 3 Opus brainstorm (8 clusters A-H, 2-3 approaches each).
**Output role:** First of two parallel Step 4 reviews; R2 DeepSeek runs separately. Synthesize + challenge — do not duplicate brainstorm content.

---

## Analysis

The eng-mgr question is not "is the design correct?" — Step 3 brainstorm and Step 2 threat model already give crisp answers there. The eng-mgr question is **"can MiMo Coding land 23 ACs across 14 files in one cycle without the wheels coming off?"** That decomposes into six worries:

1. **Ordering hazards** — does AC9 (helper extraction) need to land before AC10 + AC23 + AC6/AC7/AC8 (callers / migrators)? If the implementer interleaves, do we get a half-migrated tree where Step 14 verify finds 1 caller delegating + 2 callers still on the old contract?
2. **Signature-drift cascade** — AC9 migrates THREE existing validators (`mcp/app.py:121 _validate_wiki_dir`, `mcp/app.py:230 _validate_page_id` containment, `compile/compiler.py:645 _validate_path_under_project_root`) to delegate to a new helper. Per cycle-7 L4 / `feedback_signature_drift_verify`, every renamed/refactored function signature is a Step-11 caller-grep checkpoint. The brainstorm under-specifies which signatures change at the edge.
3. **Test-coverage true-positives** — C1-C23 are condition statements. Per cycle-22 L5, each is a load-bearing test requirement. The brainstorm's recommended sharing (`tests/_helpers/ast_walk.py` for AC4/AC17/AC23, `tests/test_cycle65_config_call_time.py` for AC1/AC2/AC3) is good DRY, but consolidation can mask which condition is unverified if a single test silently regresses to "tests three things, only proves one."
4. **Brainstorm-vs-threat-model disagreements** — at least one direct conflict: brainstorm A1 (PEP 562 `__getattr__` shim) for AC1 vs threat-model T3 verification ("Grep `_DEFAULT_MODEL_TIERS` returns zero matches in `src/kb/`"). The threat model presumes deletion, the brainstorm presumes preservation behind a shim. Picking a side is a Step 5 lock-down.
5. **OOS scope-creep traps** — OOS-1 through OOS-10 are explicitly out of scope. But OOS-1 (`raw/` ingestion path validator) is functionally adjacent to AC6/AC7 — an implementer mid-stream may "while I'm here" extend the new char checks to the raw boundary. This bloats the diff and breaks the same-class-peer-scan discipline that AC23 codifies for cycle 65 ITSELF.
6. **Concurrent-cycle drift** — CLAUDE.md Quick Reference notes "subject to Step 21 rebase if cycles 53/59/61/62 still in flight." If any of those cycles touched `mcp/app.py` / `compile/compiler.py` / `query/embeddings.py` / `lint/fetcher.py`, AC9's three-site migration may need to grow to four sites (or rebase-skew the line numbers in the threat model).

The eng-mgr verdict is APPROVE-WITH-CONDITIONS because the design is sound but the plan-gate (Step 8) needs to lock down **commit ordering, signature-drift checkpoints, condition-to-test traceability, and the ~7 unresolved questions below** before MiMo Coding starts implementation. Treat the brainstorm's "10 commits, file-grouped" as a DRAFT — Step 5 must convert to "10 commits with explicit dependency edges and Step 11 signature-drift checkpoints inserted between them."

---

## Resolved / unresolved design questions

### Resolved (brainstorm + threat model + requirements all agree)

- **Q1.1: Shape of the AC9 helper.** All three docs converge on `kb/utils/path_safety.py::_assert_under_project_root(path, *, require_exists=False, dual_anchor=True, allow_symlinks=False)` (or the public-named `assert_under_project_root` per Opus brainstorm D1). → **Resolution:** new module + canonical helper, three migrations.
- **Q1.2: AC10 TOCTOU mitigation.** Brainstorm D-TOCTOU-b (kernel `O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT`) wins over D-TOCTOU-a (re-resolve before mutate). Threat model T8 verify accepts EITHER but D-TOCTOU-b is atomic. → **Resolution:** kernel-level NOFOLLOW. Re-resolve as a fallback only if the kernel flag is unsupported on a given platform.
- **Q1.3: AC12 reuse of `SafeBackend`.** Brainstorm E2 (extend existing `SafeBackend` with scheme allowlist) + threat model T11 ("the Step 9 implementer should reuse SafeBackend — do NOT roll a new resolver") agree. → **Resolution:** add `_url_scheme_allowed` helper, gate at orchestrator entry + `_url_is_allowed`. Reject brainstorm E1 (full re-implementation).
- **Q1.4: AC15 env var setting style.** Brainstorm F1 with `os.environ.setdefault(...)` adjustment. → **Resolution:** `setdefault` so developer override wins.
- **Q1.5: AC18 cross-platform.** Threat-model dependencies note ("`grep` is unavailable on Windows by default — the test must either skipif-Windows OR use Python `re`, the latter preferred per platform parity") + brainstorm F1 ("prefer Python-`re` scanning over subprocess `grep`") agree. → **Resolution:** Python `re` over `Path.read_text`, NOT subprocess `grep`. The phrase "subprocess grep" in the AC18 wording is misleading and Step 5 should re-word it.
- **Q1.6: AC8 segment-aware match keeps the `resolve().relative_to()` safety net.** All three docs explicitly mark this as cosmetic over-rejection rather than a security primitive. → **Resolution:** segment-aware split + DO NOT remove the existing resolve-and-relativize check.
- **Q1.7: Shared AST-walk helper.** Brainstorm H2 + cluster I (synthesized) + AC4/AC17/AC23 all walk AST. → **Resolution:** `tests/_helpers/ast_walk.py` with `find_imports_from(module, name)` + `find_function_def(file_path, name)` + `find_calls_of(file_paths, qualified_name)`.
- **Q1.8: AC2 scope limited to `kb.utils.llm` migration.** Requirements doc BACKLOG drift correction is authoritative — the brainstorm and threat model both pre-date the correction in places (threat model T3 still says "delete `_DEFAULT_MODEL_TIERS`"). → **Resolution:** keep `_DEFAULT_MODEL_TIERS` AND `MODEL_TIERS` (versioned tests pin the import-time snapshot intentionally); migrate ONLY `kb/utils/llm.py:17,69-71` from `MODEL_TIERS[tier]` → `get_model_tier(tier)`; AST-walk guard rejects new direct callers.
- **Q1.9: AC12 scope limited to scheme allowlist.** Requirements doc BACKLOG drift correction is authoritative — `SafeBackend` already covers RFC1918/loopback/link-local + DNS-rebind. → **Resolution:** AC12 is just the scheme gate at `lint/augment/orchestrator.py:248` + parametrized rejection test for `file://`/`gopher://`/`data://`/`javascript://`/`ftp://`. NOT a fresh SSRF defense.
- **Q1.10: AC22 grep step in CI.** Threat model T18 verify + brainstorm cluster G + requirements all agree on `git ls-files | xargs grep -l "sk-ant-dummy" | grep -v ".github/workflows/ci.yml" | (! read)`. → **Resolution:** as-written. Step 5 should additionally consider whether to add the base64-encoded form per brainstorm-found gap #4 (note for Step 5, not blocking).

### Unresolved (Step 5 design gate must decide)

- **Q2.1: Does AC1 keep `_DEFAULT_MODEL_TIERS` (per requirements drift correction) OR delete it (per threat model T3 verify wording)?**
  - **Option A (requirements doc wins):** keep both `_DEFAULT_MODEL_TIERS` and `MODEL_TIERS`; migrate only `kb.utils.llm`; AST-walk guard against NEW direct callers (allow the existing versioned tests). T3 verify wording is corrected.
  - **Option B (threat model wins):** delete `_DEFAULT_MODEL_TIERS`; refactor versioned tests `test_v099_phase39.py` + `test_v0912_phase393.py:423` to no longer depend on the constant.
  - **Tradeoff:** Option A respects cycle 7 AC24's explicit decision to keep the constant; Option B is cleaner but breaks two intentional regression tests.
  - **Recommendation:** Option A (requirements drift correction is later than the threat model and is authoritative per the requirements doc itself).

- **Q2.2: AC9 helper public API — single function or two functions?**
  - **Option A (single function with kwargs):** `_assert_under_project_root(path, *, require_exists=False, require_dir=False, dual_anchor=True, allow_symlinks=False)`. Callers pass kwargs.
  - **Option B (two functions):** `_assert_under_project_root(path)` (the strict default) + `_assert_existing_dir_under_project_root(path)` (wraps the first, adds existence + isdir checks).
  - **Tradeoff:** Option A is one place to maintain but kwargs-explosion is a slow drift toward C2-style "configuration object" anti-patterns. Option B has explicit names but doubles the migration surface.
  - **Recommendation:** Option A but limit kwargs to the four already named (`require_exists`, `require_dir`, `dual_anchor`, `allow_symlinks`) — adding a 5th is a Step-5 follow-up gate.

- **Q2.3: AC10 fallback when kernel `O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT` is unavailable.**
  - **Option A:** raise `NotImplementedError` and skip-test on platforms where the flag is unsupported.
  - **Option B:** fall back to D-TOCTOU-a (re-resolve immediately before mutation) on unsupported platforms.
  - **Option C:** require the flag on all supported platforms (Linux, macOS, Windows 10+) — refuse to start `kb` on older platforms.
  - **Tradeoff:** A is safest (fails loud), B is graceful but has the residual race, C is strict but blocks legacy environments.
  - **Recommendation:** Option B with a Sentry/log warning on fallback. Document in `docs/reference/error-handling.md`.

- **Q2.4: AC21 boundary — decorator vs context manager?**
  - **Option A (decorator):** `@_mcp_error_boundary` on each `@mcp.tool()`-decorated function.
  - **Option B (context manager):** `with _mcp_error_boundary():` inside each tool body.
  - **Tradeoff:** A is cleaner but interacts with the FastMCP `@mcp.tool()` decorator order — must verify Pydantic param-validation still fires before the boundary catches. B is verbose but doesn't fight FastMCP's decorator chain.
  - **Recommendation:** Option A — but Step 5 must explicitly verify the FastMCP / mcp_tool decorator order. If FastMCP wraps the function, `@_mcp_error_boundary` must go BELOW `@mcp.tool()` (i.e., inside it) so exceptions in the user-supplied function body propagate UP to the boundary, not around it.

- **Q2.5: AC4 sandbox-guard test — strictly structural OR behavioural?**
  - **Option A (structural — brainstorm B1 / threat model C4):** ast-parse conftest, locate `_autouse_kb_path_sandbox` FunctionDef, assert decorator list contains `pytest.fixture(autouse=True)`.
  - **Option B (behavioural):** simulate a test with a path-touching call, assert the path is redirected to tmp_path. Doesn't depend on parsing the decorator structure.
  - **Tradeoff:** A is tight and catches the specific failure mode (decorator removal). B is robust to refactoring but might be a tautology if the test fixture itself uses the autouse fixture (circularity).
  - **Recommendation:** BOTH. Per `feedback_inspect_source_tests` (signature-only tests pass after revert) — A alone catches structural removal; B alone catches behavioural breakage. Belt-and-suspenders is cheap (~30 LOC).

- **Q2.6: AC5 sys.modules walk — bound the search to `kb.*` only, OR include user code?**
  - **Option A (kb.* only — brainstorm B1):** iterate `[mod for name, mod in sys.modules.items() if name.startswith("kb.")]`.
  - **Option B (all loaded modules):** iterate every loaded module.
  - **Tradeoff:** A is fast (~50-100 modules), B is slow (~500+ modules in a typical pytest run including all stdlib + deps + site-packages). B catches third-party `@lru_cache` test pollution (low probability but possible).
  - **Recommendation:** Option A. Add a regression test that stubs in a fake `kb._test_path_sensitive_module` with a `@lru_cache` and asserts teardown clears it.

- **Q2.7: AC22 CI grep step — does it block PRs OR warn?**
  - **Option A (block):** CI step exits non-zero if `sk-ant-dummy` found outside `ci.yml`. PR cannot merge.
  - **Option B (warn):** CI step logs a warning, does not block. Maintainer review catches.
  - **Tradeoff:** A is strict, B is lenient. Past `feedback_ci_cost_discipline` argues against new CI dimensions per cycle.
  - **Recommendation:** Option A. The cost is one CI step that runs in <1s. CI-cost discipline applies to NEW CI MATRIX dimensions (Windows, etc.), not new linting steps within existing matrix. AC22 is in scope.

- **Q2.8: Where does AC12's helper live — `kb/ingest/url_filter.py` (per threat model T9 verify) OR `kb/lint/fetcher.py` (per BACKLOG drift correction "scheme gate at `_url_is_allowed`")?**
  - **Option A (new module):** `kb/ingest/url_filter.py::_url_scheme_allowed` — per threat-model wording.
  - **Option B (extend existing):** add `_url_scheme_allowed` to `lint/fetcher.py` next to `_url_is_allowed` — per requirements drift correction.
  - **Tradeoff:** A creates a new ingestion-scoped module that future ingest paths can import. B keeps it next to the existing defense, easier discovery.
  - **Recommendation:** Option B (per requirements drift correction — authoritative). If a future cycle adds a second `ingest/`-scoped URL gate, promote to `kb/utils/url_safety.py` per brainstorm E3.

- **Q2.9: AC23 same-class peer scan — does it FAIL CI on a fourth caller, or just enumerate?**
  - **Option A (fail CI on fourth caller):** AST-walk asserts `len(callers) == 3` (the historical sites). Adding a fourth fails CI.
  - **Option B (fail CI on missing historical caller):** AST-walk asserts the three historical sites are PRESENT, but additional callers are allowed.
  - **Tradeoff:** A forces every NEW path-accepting tool to migrate via plan review, but is annoying when a legitimate new caller lands. B trusts future contributors but doesn't catch the "fourth caller adopts weakest contract" threat (which is THE threat T7 closure).
  - **Recommendation:** Option B with a CHANGELOG-history note that bumps the expected count. T7 is closed by the helper's existence + AC9's docstring contract; AC23 just guards the historical sites.

- **Q2.10: Is AC16's value-based scrub tested with a fixture-set env var, or with the real ANTHROPIC_API_KEY value if set?**
  - **Option A (fixture):** test sets `os.environ["ANTHROPIC_API_KEY"] = "test-fake-value-not-real"` via monkeypatch, asserts argv containing that exact string is blocked.
  - **Option B (real if set):** test reads `os.environ.get("ANTHROPIC_API_KEY")` at runtime, asserts blocking only if the env var is set in CI.
  - **Tradeoff:** A is deterministic + safe (no real key in test scope). B exercises the production code path more realistically but RISKS the real key entering pytest output if a test fails with verbose mode.
  - **Recommendation:** Option A — exclusively. Real keys must not enter test code per `feedback_no_secrets_in_code`.

---

## Cross-AC dependencies

Ordered: A must land before B if A's outputs are referenced by B's tests or migrations.

1. **AC9 (path-safety helper) → AC10 (TOCTOU NOFOLLOW), AC23 (same-class peer test), AC6+AC7+AC8 (page-id char rules)**
   - AC10 wraps file ops INSIDE the helper (or its callers); cannot land before the helper exists.
   - AC23 AST-walks callers of the helper; meaningless without the helper.
   - AC6/AC7/AC8 are inside `_validate_page_id` whose containment-check WILL be migrated by AC9. Keep the char-rule edits in the SAME commit as the AC9 migration of `_validate_page_id`, OR land AC6-8 first then migrate AC9 separately. Brainstorm Step 7 plan #4 → #5 (AC6/7/8 commit before AC9 commit) is the safer ordering.

2. **AC1 (`get_project_root`) → AC10 (TOCTOU re-validation against PROJECT_ROOT) AND AC9 callers' dual-anchor logic**
   - AC9 helper kwargs include `dual_anchor=True` which references PROJECT_ROOT at call time. If AC1 isn't shipped, the helper still reads the import-time stale value.
   - Land AC1 before AC9.

3. **AC3 (`get_allowed_domains`) → AC12 (`_url_scheme_allowed` and downstream URL gates that read the allowlist)**
   - Per threat model T11: "Per cycle-19 L2, the function MUST read `KB_AUGMENT_ALLOWED_DOMAINS` at call time (depends on AC3 landing first or alongside)."
   - Land AC3 before AC12.

4. **`tests/_helpers/ast_walk.py` (foundation commit) → AC4, AC17, AC23, AC18, AC20**
   - All five tests AST-walk. The helper must land first.
   - Brainstorm Step 7 plan correctly puts the helper as commit #1.

5. **AC11 (`GitPython` pin) → independent. No upstream dep.**

6. **AC15 (`TRAFILATURA_DOWNLOAD_NO_CACHE`) → independent (env var set at module init).**

7. **AC18 (CVE greps test) → independent of source-code ACs but DOWNSTREAM of any new imports landed in this cycle.**
   - If the cycle accidentally adds `import litellm` to fix some other AC, AC18 fires. So AC18 must land EARLY to surface accidental drift.
   - Land AC18 right after the foundation helper commit.

8. **AC14 (sqlite-vec sanitize) → AC21 (MCP boundary catches re-raised RuntimeError)**
   - AC21's boundary catches `RuntimeError`; AC14's sanitized re-raise becomes the message that AC21 wraps. They're concentric layers, must both land for the full defense.
   - Land AC14 before AC21 (defense at the deepest layer first).

9. **AC4 + AC5 (sandbox guards) → independent of all source-code ACs but their TESTS depend on the foundation AST helper.**
   - Land after the foundation, before any source-code edits that might rely on the sandbox.

10. **AC22 (CI grep step in ci.yml) → independent of source code; lands last so it doesn't gate other commits.**

11. **AC19 (snapshot negative controls) → no AC dependency, but should land AFTER any cycle-65 source change that affects a snapshot subject (none expected per OOS-8).**

12. **AC20 (INDEX.md) → must land WITH or AFTER docs/reference/*.md changes (none expected this cycle except the AC9 path-safety section in `docs/reference/error-handling.md`).**

13. **AC2 (`MODEL_TIERS` migration in `kb/utils/llm.py`) → AC1's `__getattr__` shim must work for `kb.config.MODEL_TIERS` attribute access (cycle 7 AC24 keeps the constant for the versioned tests).**
   - Land AC1 before AC2.

**Execution-risk-ordered minimum path:**

```
foundation: tests/_helpers/ast_walk.py
  → AC18 (CVE greps test — surfaces accidental imports)
  → AC11 (GitPython pin — no deps)
  → AC15 (TRAFILATURA env var — no deps)
  → AC1 (get_project_root call-time)
  → AC2 (MODEL_TIERS migration in kb/utils/llm.py)
  → AC3 (get_allowed_domains call-time)
  → AC4 + AC5 (sandbox guards)
  → AC6 + AC7 + AC8 (page-id char rules — inside _validate_page_id)
  → AC9 (path_safety.py helper + migrate three sites)
  → AC10 (TOCTOU NOFOLLOW inside helper / rebuild_indexes)
  → AC23 (same-class peer test)
  → AC12 (scheme allowlist in lint/augment/)
  → AC13 (file_lock around VectorIndex.build)
  → AC14 (sqlite-vec sanitize)
  → AC16 (cli_backend value-based scrub)
  → AC17 (graph/cache __all__ + AST test)
  → AC21 (mcp/{core,ingest,quality}.py error boundary)
  → AC19 (snapshot negative controls)
  → AC20 (docs/reference/INDEX.md + meta-test)
  → AC22 (CI grep step)
```

This is 23 distinct logical units across ~10-12 commits depending on file-grouping. Step 5 should approve a commit-merge plan that groups by file (per `feedback_batch_by_file`) but PRESERVES this dependency order.

---

## Same-class peer scan (cycle-23 L4)

For each AC introducing a new check / helper / regression test, name the same-class peers DELIBERATELY out of scope and the one-line justification:

- **AC1 (`get_project_root` call-time) — peers OUT of scope:** other module-level constants like `STATUS_RANKING_BOOST`, `AUTHORED_BY_BOOST`, `PUBLISH_BELIEF_FILTERS`, kill-switch env vars `KB_DISABLE_VECTOR_AUTO_REBUILD`/`KB_DISABLE_COMPILE_AUTO_PUBLISH`. → **Justification:** these are documentation/feature-flag constants not security-anchoring; cycle-19 L2 reload-leak applies but doesn't cross the security threshold. Defer to a hygiene cycle.

- **AC6/AC7 (page-id char rules) — peers OUT of scope:** `_validate_run_id` (cycles 17/29), `_validate_wiki_dir` containment, `raw/` ingestion path validator (OOS-1). → **Justification:** OOS-1 explicitly out of scope; `_validate_run_id` was hardened in cycle 17/29 with run-id-specific rules; `_validate_wiki_dir` operates on absolute paths going through OS normalization (OOS-4).

- **AC9 (path-safety helper) — peers OUT of scope:** `_validate_page_id` char checks (live IN this cycle as AC6/AC7/AC8), `_validate_raw_source_path` (OOS-1), the citation-graph URL handler in `evolve/` (OOS-2). → **Justification:** the helper is for CONTAINMENT only; char rules and URL filtering are different threat classes. Documented in helper docstring.

- **AC10 (TOCTOU NOFOLLOW) — peers OUT of scope:** TOCTOU on `ingest_source` writes (OOS-6), TOCTOU on `compile_wiki` orchestration (OOS-5), TOCTOU on `auto_publish_after_compile` writes (cycle 64 AC14). → **Justification:** AC10 is scoped to `compile/compiler.py::rebuild_indexes` unlink path; broader fan-out TOCTOU is Phase 4.5 R5 (still open).

- **AC12 (scheme allowlist) — peers OUT of scope:** URL handling in `evolve/` (OOS-2), URL handling in `query/embeddings.py` (none — vector search is local), URL handling in MCP tool descriptions (none — descriptions are static strings). → **Justification:** OOS-2 is the deferred peer; no other URL surfaces in the project.

- **AC13 (multi-process VectorIndex lock) — peers OUT of scope:** multi-process race on `compile_wiki` (OOS-5), multi-process race on `ingest_source` (OOS-6). → **Justification:** broader fan-out coordination is a Phase 4.5 R5 architectural item.

- **AC14 (sqlite-vec sanitize) — peers OUT of scope:** error sanitisation in `query/embeddings.py::VectorIndex.query`, error sanitisation in `compile/compiler.py::rebuild_indexes` (cycle 64 AC8 partially covers). → **Justification:** AC14 targets the specific extension-load path leak; broader sanitisation lives in AC21's boundary at the MCP layer.

- **AC16 (value-based secret scrub) — peers OUT of scope:** secret detection in MCP tool args, secret detection in environment loading, secret derivation patterns (brainstorm-found gap #2). → **Justification:** OOS-10 explicitly out of scope; AC16 fixes the self-DoS regression on the existing `_check_no_secrets_on_argv` only.

- **AC17 (graph/cache `__all__ = []`) — peers OUT of scope:** other `kb.*` modules with snapshot-binding hazards, e.g. `kb.config.MODEL_TIERS` (handled by AC2), `kb.utils.text.sanitize_error_text` (no test-spy use case). → **Justification:** AC17 closes a SPECIFIC drift detected via cycle-18 L1; project-wide attribute-binding audit is a future cycle.

- **AC18 (CVE greps test) — peers OUT of scope:** SAST scanning on `tests/`, license scanning, supply-chain attestation. → **Justification:** AC18 mechanizes the SECURITY.md table only; broader supply-chain hardening is a Phase 6 item.

- **AC19 (snapshot negative controls) — peers OUT of scope:** snapshot subjects beyond cycle 64's three (OOS-8). → **Justification:** OOS-8 explicitly out of scope.

- **AC20 (docs/reference/INDEX.md) — peers OUT of scope:** auto-generation of CLAUDE.md "Detailed Documentation" table, auto-generation of CHANGELOG.md compact entries, frontmatter-driven docs index. → **Justification:** AC20 is hand-authored INDEX + meta-test (per brainstorm H3 recommendation); auto-generation is a future cycle.

- **AC21 (MCP error boundary) — peers OUT of scope:** error boundary on `mcp/browse.py` (already uses sanitize_error_text), `mcp/compile.py` and `mcp/health.py` (OOS-3), CLI subcommand boundary in `cli.py` (OOS-9). → **Justification:** OOS-3 + OOS-9 explicitly out of scope; AC21 covers the remaining gap.

- **AC22 (CI dummy-key grep) — peers OUT of scope:** scanning for live key formats other than `sk-ant-`, base64-encoded forms (brainstorm-found gap #4), other secret patterns (`OPENAI_*`, `FIRECRAWL_*`). → **Justification:** AC22 anchors on the specific dummy-key leakage hazard; broader CI secret scanning is a future cycle.

- **AC23 (same-class peer test) — peers OUT of scope:** AST-walk regression for non-path-safety helpers, generic same-class peer scan harness. → **Justification:** AC23 is a one-off targeted test for AC9's three sites; generalizing to a harness is a `tests/_helpers/` evolution for a future cycle.

---

## Test-coverage gap analysis

For each C1-C23 condition, state load-bearing vs nice-to-have, and whether it should be sub-AC'd in Step 7 plan.

| C# | Maps to | Load-bearing? | Sub-AC in Step 7? | Notes |
|----|---------|----|----|---|
| C1 | T1, AC1 | YES | YES | Specifically: `monkeypatch.setenv("KB_PROJECT_ROOT")` AFTER `import kb.config` then assert accessor reflects new value. Brainstorm A1 risk noted (200+ tests rely on `kb.config.PROJECT_ROOT` shim). |
| C2 | T2, AC3, AC12 | YES | YES | Stale-env mutation does NOT bleed across the accessor boundary. Negative test required. |
| C3 | T3, AC2 | YES | YES | AST-walk over `src/kb/**/*.py` excluding `config.py` itself for `from kb.config import MODEL_TIERS` AND `MODEL_TIERS[`. Versioned tests are exempt. |
| C4 | T4, AC4 | YES | YES | Strictly structural per `feedback_inspect_source_tests`. Brainstorm Q2.5 recommends BOTH structural + behavioural. |
| C5 | T4, AC5 | YES | YES | Stub `kb._test_path_sensitive_module` with `@lru_cache`, trigger teardown, assert clear fired. |
| C6 | T5, AC6 | YES | YES | 4-case parametrized: `"secret."`, `"secret "`, `"foo/bar."`, `"foo/bar "`. |
| C7 | T6, AC7 | YES | YES | 7-case parametrized for `:`, `<`, `>`, `"`, `|`, `?`, `*`. |
| C8 | T7, AC9, AC23 | YES | YES | AST-walk asserting ≥3 callers of the helper. Q2.9 unresolved (== 3 vs ≥ 3). |
| C9 | T8, AC10 | YES | YES | `monkeypatch.setattr(Path, "unlink", swap_then_unlink)` to inject the swap. |
| C10 | T9, AC12 | YES | YES | 8-case parametrized rejection of private/loopback/link-local IPs. |
| C11 | T10, AC12 | YES | YES | 5-case parametrized rejection of `file://`, `gopher://`, `data:`, `javascript:`, `ftp://`. |
| C12 | T11, AC12 | YES | YES | DNS-rebind test via `monkeypatch.setattr("socket.gethostbyname", ...)`. NOT just URL-string parsing. |
| C13 | T12, AC11 | YES | YES | AST-parse `requirements.txt` for `==` AND `<` on GitPython line. |
| C14 | T13, AC15 | YES | YES | Two-stage: (a) env var set at module load; (b) spy on `trafilatura.fetch_url` confirms env var observable. |
| C15 | T14, AC18 | YES | YES | All FOUR greps wired up; manual revert-style test. |
| C16 | T15, AC14 | YES | YES | `monkeypatch.setattr(sqlite_vec, "load", raise_with_path)` then assert sanitised message. |
| C17 | T16, AC21 | YES | YES | Parametrized over EVERY `@mcp.tool()` in `mcp/{core,ingest,quality}.py`. |
| C18 | T17, AC16 | YES | YES | Two-prong: (a) legitimate token-shape allowed; (b) literal env value blocked. Per Q2.10, fixture-set env value only. |
| C19 | T18, AC22 | YES | YES | AST-parse `ci.yml` for the grep step. |
| C20 | T19, AC13 | YES | YES | `multiprocessing.Process`-based test. Time.monotonic() ordering check + dim consistency. |
| C21 | T20, AC17 | YES | YES | `__all__ == []` + AST-walk for `from kb.graph.cache import` rejecting matches. |
| C22 | T21, AC19 | YES | YES | One paired negative-control per snapshot subject (3 total). Plus zero `--snapshot-update` in CI. |
| C23 | AC20 | NICE-TO-HAVE | YES | INDEX.md ↔ files cross-reference. Less security-load-bearing than C1-C22 but still required for AC20 closure. |

**All 23 conditions are sub-ACs in the Step 7 plan.** No condition is "nice-to-have-only-skip-for-time" — even C23 is required for AC20 closure. The Step 7 plan-gate must include a 1:1 condition-to-test traceability matrix; if the plan-gate sees N tests for fewer than 23 conditions, REJECT.

**Test-coverage gap risk:** the brainstorm's "shared regression test files" (e.g., `tests/test_cycle65_validate_page_id.py` covering AC6/AC7/AC8) save LOC but introduce a hazard — if the test file accidentally collapses three parametrized cases into one parametrize block with weakened assertions, the regressions for two of the three ACs silently disappear. **Step 7 plan-gate must require explicit test functions per AC** even inside shared files. Naming convention: `test_ac6_rejects_trailing_dot`, `test_ac7_rejects_colon`, `test_ac8_segment_aware_match` — NOT a single `test_validate_page_id_rejections` parametrize.

---

## Signature drift watchlist

Per cycle-7 L4 / `feedback_signature_drift_verify`, refactoring an existing function signature requires a Step-11 caller-grep checkpoint. AC9's three migrations are the primary signature-drift surface for cycle 65.

### Functions whose signature changes during AC9 migration

1. **`mcp/app.py:121 _validate_wiki_dir(wiki_dir: Path) -> Path`**
   - **Pre-migration:** absolute + exists + dir + single resolved-anchor; raises ValidationError on failure; returns the validated Path.
   - **Post-migration option A (delegate, keep wrapper):** signature unchanged; body becomes `_assert_under_project_root(wiki_dir, "wiki_dir", require_exists=True, require_dir=True)` then `return wiki_dir.resolve()`. Callers unaffected.
   - **Post-migration option B (deprecate, point at helper):** delete the function; migrate ~15 callers to `_assert_under_project_root(wiki_dir, "wiki_dir", require_exists=True, require_dir=True)`.
   - **Recommendation:** Option A. Zero caller-side churn. The wrapper is 2 lines.
   - **Step 11 caller-grep checkpoint:** `Grep "_validate_wiki_dir(" src/kb/ tests/` should return SAME count pre + post migration.

2. **`compile/compiler.py:645 _validate_path_under_project_root(path: Path, field_name: str) -> Path`**
   - **Pre-migration:** dual literal + resolved anchor; raises ValidationError on failure; returns validated Path.
   - **Post-migration option A:** signature unchanged; body becomes `_assert_under_project_root(path, field_name)` then `return path.resolve()`.
   - **Post-migration option B:** rename to `_assert_under_project_root` and update callers.
   - **Recommendation:** Option A. Zero caller-side churn.
   - **Step 11 caller-grep checkpoint:** `Grep "_validate_path_under_project_root(" src/kb/ tests/` returns SAME count.

3. **`mcp/app.py:230 _validate_page_id(page_id: str) -> Path`** (this one has the AC6/AC7/AC8 char rules ALSO landing in cycle 65)
   - **Pre-migration:** ad-hoc containment via `..` substring check + resolved-anchor.
   - **Post-migration:** delegate the containment portion to `_assert_under_project_root(resolved_path, "page_id", dual_anchor=True)`. Char rules (AC6/AC7/AC8) added IN this function alongside.
   - **Recommendation:** keep `_validate_page_id` signature unchanged; the char rules are added inline; the containment call is delegated.
   - **Step 11 caller-grep checkpoint:** `Grep "_validate_page_id(" src/kb/ tests/` returns SAME count, AND new test cases for the three new char-rule rejections (per C6/C7).

### Other functions touched in cycle 65 with potential signature drift

4. **`config.py::PROJECT_ROOT` (module-level constant)** → becomes `get_project_root()` accessor + `__getattr__` shim. **Risk:** the shim must NOT break `from kb.config import PROJECT_ROOT` (Python imports the attribute eagerly). Per brainstorm A3 rejection, `from-import` STILL captures the value at import time. **This is acceptable** for the threat model (the threat is module-level cache staleness, not from-import capture) but Step 11 must verify `Grep "from kb.config import PROJECT_ROOT" src/kb/ tests/` returns zero matches OR all matches are in test files that intentionally test the import-time snapshot.

5. **`config.py::AUGMENT_ALLOWED_DOMAINS`** → same migration pattern. Same Step 11 caller-grep checkpoint.

6. **`config.py::MODEL_TIERS`** → KEEP per requirements drift correction. Migration is in `kb/utils/llm.py:17,69-71` only. **Risk:** `kb.utils.llm.py:17,69-71` is the migration site; no signature change to `MODEL_TIERS` itself. Step 11 caller-grep: `Grep "MODEL_TIERS\[" src/kb/` returns ZERO outside `config.py` (test files exempt).

7. **`utils/cli_backend.py::_check_no_secrets_on_argv(argv: list[str]) -> None`** → signature unchanged; body rewrites from regex-based to value-based. **Step 11 caller-grep:** `Grep "_check_no_secrets_on_argv\b" src/kb/ tests/` returns SAME count.

8. **`query/embeddings.py::VectorIndex.build(force_rebuild=False) -> None`** → signature unchanged; body wraps DROP/CREATE/INSERT/COMMIT in `file_lock`. **Step 11 caller-grep:** SAME count.

9. **`lint/fetcher.py::_url_is_allowed(url: str) -> bool`** → augmented (NOT replaced) with scheme check via Q2.8 Option B. Signature unchanged.

10. **`graph/cache.py::get_graph(wiki_dir, *, pages=None)`** → signature unchanged; only `__all__ = []` added. **Step 11 caller-grep:** `Grep "from kb.graph.cache import get_graph" src/kb/` returns ZERO (the entire point of AC17).

### NEW functions introduced in cycle 65

- `kb/utils/path_safety.py::_assert_under_project_root(path, field_name, *, require_exists=False, require_dir=False, dual_anchor=True, allow_symlinks=False) -> None`
- `kb/config.py::get_project_root() -> Path`
- `kb/config.py::get_allowed_domains() -> tuple[str, ...]`
- `kb/config.py::_reset_project_root() -> None` (test helper)
- `kb/lint/fetcher.py::_url_scheme_allowed(url: str) -> bool` (or wherever Q2.8 lands)
- `kb/mcp/_error_boundary.py::_mcp_error_boundary` (decorator or context manager per Q2.4)
- `tests/_helpers/ast_walk.py::find_imports_from / find_function_def / find_calls_of`

**Eng-mgr concern:** seven new public-facing-ish functions in one cycle is at the upper bound of safe. Each is a future-API commitment. Step 5 should confirm whether any could be private (leading underscore) to keep the contract surface small. Recommendation: ALL of them lead with underscore (private) — they're internal helpers, not public API.

---

## Verdict

**APPROVE-WITH-CONDITIONS**

The design is sound. Brainstorm + threat model + requirements converge cleanly on 8 of 10 unresolved questions; the remaining 2 (Q2.1 model-tier delete-vs-keep, Q2.4 boundary decorator-vs-context-manager) are routine plan-gate decisions. The 23 ACs are well-bounded with tight peer-scan discipline (cycle-23 L4 codified in AC23). The four cross-cutting opportunities (shared AST helper, shared config-call-time test, shared page-id test, separate CVE/snapshot tests) are correctly identified.

**Conditions before MiMo Coding starts:**
1. Step 5 design gate locks down Q2.1-Q2.10 (10 unresolved questions).
2. Step 7 plan converts brainstorm's "10 commits" to a dependency-ordered list with explicit Step 11 signature-drift checkpoints inserted between AC9 / AC10 / AC23 commits.
3. Step 7 plan includes a 1:1 condition-to-test traceability matrix mapping all 23 conditions C1-C23 to named test functions (no parametrize collapsing without explicit per-AC test naming).
4. Step 7 plan adds a "concurrent-cycle drift" pre-check at the start of Step 9: rebase against main, re-grep `_validate_*` line numbers, confirm AC9's three sites still match the threat-model wording. If a fourth site appeared (e.g., from cycles 53/59/61/62 still in flight), expand AC9 scope OR escalate to Step 5 redesign.

The plan is at the high end of cycle complexity (23 ACs / 14 files / 7 new internal helpers / 2 cross-platform OS flag concerns / 4 dependency-ordering cascades) but each individual AC is small. With the conditions above, MiMo Coding can ship safely.

---

## Step 5 input

The Step 5 design gate must lock down:

- **Q2.1:** AC1 keeps `_DEFAULT_MODEL_TIERS` per requirements drift correction (Option A) → confirm threat-model T3 verify wording is updated to match.
- **Q2.2:** AC9 helper API is a single function with kwargs, capped at 4 kwargs (`require_exists`, `require_dir`, `dual_anchor`, `allow_symlinks`).
- **Q2.3:** AC10 fallback when `O_NOFOLLOW` unavailable → graceful fallback to re-resolve (Option B) with a Sentry/log warning.
- **Q2.4:** AC21 boundary is a decorator (Option A) — but verify FastMCP decorator order. Document the order in the helper's docstring.
- **Q2.5:** AC4 sandbox guard test is BOTH structural AND behavioural — neither alone is sufficient.
- **Q2.6:** AC5 sys.modules walk scoped to `kb.*` only (Option A), with a stub-module regression test.
- **Q2.7:** AC22 CI grep step BLOCKS PRs (Option A).
- **Q2.8:** AC12 helper lives in `lint/fetcher.py` (Option B per requirements drift correction) — NOT a new `ingest/url_filter.py` module.
- **Q2.9:** AC23 same-class peer test asserts the THREE historical sites are PRESENT but allows additional callers (Option B) — bumping the count requires a CHANGELOG-history note.
- **Q2.10:** AC16 test uses fixture-set env values exclusively (Option A) — no real `ANTHROPIC_API_KEY` in test scope.

Plus the four cross-cutting plan-gate conditions:
- Foundation commit (`tests/_helpers/ast_walk.py`) lands before AC4/AC17/AC18/AC20/AC23 tests.
- Step 9 begins with a rebase-against-main + re-grep check on AC9's three sites.
- Step 11 inserts caller-grep checkpoints after each signature-touching commit (AC1, AC2, AC3, AC9, AC10, AC16, AC17, AC21).
- Step 7 plan adds explicit named test functions per AC, no parametrize-collapsing.

Step 4 R2 (DeepSeek) runs in parallel; Step 5 design gate consumes both reviews.
