# Cycle 65 — Locked Design (Step 5 decision gate)

**Cycle:** 65
**Date:** 2026-05-04
**Reviewer:** Opus 4.7 sub-agent (design decision gate, May 2026 MiMo trial)
**Inputs consumed:** Step 1 requirements, Step 2 threat model (T1-T21 / C1-C23 / OOS-1..10), Step 3 Opus + DeepSeek brainstorms, Step 4 R1 (Opus eng-mgr) + R2 (DeepSeek devex). Plus CLAUDE.md / SECURITY.md / source grep verification.
**Output role:** locks every design choice for Step 7 plan to consume verbatim.

---

## Analysis

The Step 4 R1 (eng-mgr) verdict (APPROVE-WITH-CONDITIONS) and Step 4 R2 (devex) verdict (APPROVE-WITH-CONDITIONS) converge: design is sound, conditions are tractable. R1 enumerates 10 unresolved questions Q2.1-Q2.10 + cross-AC dependencies + signature-drift watchlist + same-class peer scan. R2 surfaces 11 devex findings D1-D11 (a few rooted in things R1 already flagged but framed differently), plus naming + doc-update + cross-cycle pattern adherence.

What needs locking, by category:

1. **Q2.1-Q2.10 — explicit choice on each.** R1 already proposed a default option per question; my job is to confirm or amend, citing which input drove the decision.
2. **R2 devex D1-D11 — disposition.** Each is ADOPT (sub-AC), DEFER-TO-STEP-17-DOC-ONLY (Doc-update checklist), DEFER-TO-CYCLE-66, or REJECT (with reason).
3. **BACKLOG drift corrections (AC2, AC12) — verify all reviews still consistent.** Both R1 + R2 honour the corrections; threat-model T3 / T9-T11 verify wording is the only source of stale text. Per requirements doc § BACKLOG drift findings, the requirements doc wins.
4. **Symbol grep-verify (cycle-3 L4).** I grep-verified all symbols in current source. All historical sites in AC9 (mcp/app.py:121, mcp/app.py:230, compile/compiler.py:645) confirmed at named line numbers. `kb.utils.llm:17,69-71` confirmed using `MODEL_TIERS[tier]`. `_url_is_allowed` confirmed in `lint/fetcher.py:232`. `tests/_helpers/` does not yet exist (so the foundation commit creates it). One drift surfaced: `sanitize_error_text` lives in `kb.utils.sanitize`, NOT `kb.utils.text` as the threat model + requirements AC21 wording says — locked design corrects to `kb.utils.sanitize`. Another minor drift: actual env var in `config.py:480` is `AUGMENT_ALLOWED_DOMAINS` (no `KB_` prefix); locked design uses the actual name AND adds `KB_AUGMENT_ALLOWED_DOMAINS` as an additional alias to honour the call-time accessor pattern under both names.
5. **Conflict resolution.** R1 Q2.1 (delete vs keep `_DEFAULT_MODEL_TIERS`) — requirements drift correction wins (KEEP). R1 Q2.4 (boundary decorator vs context manager) — decorator inside `@mcp.tool()` chain. R1 Q2.5 (structural vs behavioural sandbox guard) — BOTH, per `feedback_inspect_source_tests`. R2 D2 (deprecate `MODEL_TIERS`) — REJECT, requirements drift correction explicitly KEEPS `MODEL_TIERS` for cycle 7 AC24 versioned tests. R2 D6 (commit ordering) — already adopted in R1 dependency-ordered minimum path; explicit Step 7 plan enforcement.
6. **CONDITIONS section (cycle-22 L5).** Each C1-C23 maps 1:1 to a named test in Step 7 plan. R1 already mapped them; I copy + add three sub-AC carve-outs for items Step 7 plan must split (per cycle-9 L1 dual-mechanism rule).
7. **Same-class peer scan (cycle-23 L4).** R1 enumerated peers per AC. I copy R1's enumeration verbatim and augment with one R2-discovered item (AC2 deprecation peers).
8. **Signature drift watchlist (cycle-7 L4).** R1 enumerated 10 entries. I confirm and add an 11th: `kb.config.PROJECT_ROOT` → `get_project_root()` migration is the load-bearing one because 200+ tests reference `kb.config.PROJECT_ROOT` via attribute lookup. R1 captured this under #4 already; I just upgrade it to first-class.

The design is at the upper bound of safe one-cycle complexity (R1's words). With the locked decisions below, MiMo Coding can proceed.

---

## Tier confirmation

**Tier 2 (standard feature) — multi-AC BACKLOG batch fix with security-touching items.**

Per the requirements doc § Tier (cycle 65, 2026-05-04): the user's `feedback_auto_approve.md` standing instruction overrides Tier 3's mandatory human gates at Step 5 + Step 20 R2. All approvals (this Step 5 design gate, Step 8 plan gate, Step 11 PR review, Step 21 land/merge) are handled by Opus + DeepSeek + MiMo Coding sub-agents. Pipeline runs Steps 1-24 in full per requirements doc § Steps run.

Cycle 65 user pipeline modifications also confirmed: Step 03 (parallel Opus + DeepSeek brainstorm — done, used as inputs); Step 20 (MiMo Coding R1 BLOCKER+MAJOR + Sonnet edge-case role; MiMo Coding R2 cycle-lessons-rule audit + Codex/DeepSeek cross-family confirmation).

---

## Locked decisions on R1 unresolved questions Q2.1-Q2.10

### Q2.1 — Does AC1 keep `_DEFAULT_MODEL_TIERS` or delete it?

- **Decision:** Option A — KEEP both `_DEFAULT_MODEL_TIERS` and `MODEL_TIERS`. AC2 migration scope is ONLY `kb/utils/llm.py:17,69-71` from `MODEL_TIERS[tier]` → `get_model_tier(tier)`. Add AST-walk guard `tests/test_config_no_direct_model_tiers.py` rejecting NEW direct `from kb.config import MODEL_TIERS` and `MODEL_TIERS[` references in `src/kb/**/*.py` excluding `config.py`. Versioned tests `test_v099_phase39.py` + `test_v0912_phase393.py:423` are exempt (intentional import-time-snapshot pinning per cycle 7 AC24).
- **Reason:** Requirements doc § BACKLOG drift findings is AUTHORITATIVE per the requirements doc itself: "BACKLOG drift correction per cycle-3 L4 verify-against-source ... Mimo audit description was inverted. Actual state at `config.py`: line 132 `_DEFAULT_MODEL_TIERS` is hardcoded fallbacks (no env capture); line 160 `MODEL_TIERS` IS the import-time-captured dict bypassing the call-time `get_model_tier()` accessor at line 139." Threat model T3 verify wording ("Grep `_DEFAULT_MODEL_TIERS` returns zero matches") is stale (predates the drift correction); requirements doc explicitly notes "T3 + T9-T11 verification methods predate the AC2/AC12 drift corrections; the requirements doc wins." R2 D2 ("deprecate MODEL_TIERS") — REJECTED for the same reason.
- **Step 7 plan implication:** Threat-model T3 verify text MUST be updated in Step 14 to read: "Grep `from kb.config import MODEL_TIERS` and `MODEL_TIERS[` in `src/kb/**/*.py` excluding `config.py` and the two versioned test files; assert zero matches." Plan step records this as a Step 14 verification text correction (NOT a code change).

### Q2.2 — AC9 helper public API: single function with kwargs OR two functions?

- **Decision:** Option A — single function with kwargs. Signature: `_assert_under_project_root(path: Path, field_name: str, *, require_exists: bool = False, require_dir: bool = False, dual_anchor: bool = True, allow_symlinks: bool = False) -> None`. Hard cap of FOUR keyword-only parameters in cycle 65; adding a fifth requires a Step 5 follow-up gate.
- **Reason:** R1 recommendation. Brainstorm D1 (default) and D2 (decorator pattern) both proposed kwargs-style; D2 added a decorator wrapper but R1 + R2 both agree decorator is YAGNI for cycle 65 (only 3 historical sites). Underscore prefix preserves "internal helper" status (R1 signature drift watchlist § NEW functions: "ALL of them lead with underscore (private)").
- **Step 7 plan implication:** Step 7 plan must lock the kwargs cap at 4 and reject any in-flight expansion. AC9 sub-AC: "kwargs cap=4". Tests must pass `dual_anchor=True` explicitly when migrating `_validate_path_under_project_root` (which currently does dual literal+resolved anchor).

### Q2.3 — AC10 fallback when kernel `O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT` unavailable?

- **Decision:** Option B — graceful fallback to D-TOCTOU-a (re-resolve immediately before mutation), with a single-line `logger.warning("AC10: O_NOFOLLOW unsupported on platform %s; falling back to re-resolve TOCTOU mitigation", sys.platform)` on first invocation per process. Document fallback in `docs/reference/error-handling.md`.
- **Reason:** R1 recommendation (Option B with Sentry/log warning). DeepSeek brainstorm cluster D § AC10 alternative ("use file_lock to mutex the entire rebuild") was considered; rejected because it overlaps AC13 unnecessarily and adds a second lock-file hazard. Linux + macOS + Windows 10+ all support the kernel flag in 2026; the warning fires on legacy platforms only. Option A (hard fail) breaks tests on minor platform variants; Option C (refuse to start `kb`) regresses developer experience.
- **Step 7 plan implication:** AC10 sub-ACs are: (a) primary path uses `os.open(path, os.O_NOFOLLOW | os.O_RDONLY)` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows); (b) fallback path re-resolves immediately before mutate; (c) one-time per-process `logger.warning` on fallback; (d) docstring in `kb/utils/path_safety.py::_assert_under_project_root` documents the contract. Test C9 (`test_symlink_swap_rejected`) MUST run on the primary path on supported platforms; an additional test exercises the fallback path with `monkeypatch` simulating `O_NOFOLLOW` unavailability.

### Q2.4 — AC21 boundary: decorator OR context manager?

- **Decision:** Option A — decorator. `_mcp_error_boundary` is a decorator that goes BELOW (inside) `@mcp.tool()` in the decorator chain. The decorator chain becomes:
  ```python
  @mcp.tool()
  @_mcp_error_boundary  # catches exceptions from the user-supplied function body
  def kb_query(...): ...
  ```
  Naming: keep `_mcp_error_boundary` (NOT `_mcp_error_handler` per R2 D10) because "boundary" is the same vocabulary used by cycle 18 AC13 + cycle 23 L4 in `docs/reference/error-handling.md` and CHANGELOG-history.md. R2 D10's rename suggestion is REJECTED — naming consistency with existing codebase wins. `_mcp_error_boundary` lives in NEW `src/kb/mcp/_error_boundary.py` to avoid bloating `mcp/app.py`. Imports `sanitize_error_text` from `kb.utils.sanitize` (NOT `kb.utils.text` — drift in threat model corrected at design lock).
- **Reason:** R1 recommendation. R2 D10 challenged the naming; rejected because cross-cycle pattern adherence (cycle 18 AC13, cycle 23 L4 vocabulary) outweighs ergonomic relabeling. The decorator chain order ("below `@mcp.tool()`") is verified by reading `mcp/quality.py:48` etc. (the existing `_validate_page_id`-then-body pattern) and confirmed by R1 Q2.4 reasoning.
- **Step 7 plan implication:** Step 9 implementer must add `@_mcp_error_boundary` BELOW each `@mcp.tool()` in `mcp/core.py`, `mcp/ingest.py`, `mcp/quality.py`. NOT in `mcp/browse.py` (already uses `sanitize_error_text` directly per OOS-3), NOT in `mcp/compile.py` or `mcp/health.py` (OOS-3). Step 11 caller-grep checkpoint: `Grep "@mcp.tool" mcp/{core,ingest,quality}.py` count == `Grep "@_mcp_error_boundary" mcp/{core,ingest,quality}.py` count.

### Q2.5 — AC4 sandbox guard test: structural OR behavioural OR both?

- **Decision:** Option C (synthesized) — BOTH structural AND behavioural. The structural test (`tests/test_conftest_sandbox_guard.py::test_autouse_decorator_present`) AST-parses `tests/conftest.py`, locates `_autouse_kb_path_sandbox` `FunctionDef`, asserts decorator list includes `pytest.fixture(autouse=True)` per C4. The behavioural test (`tests/test_conftest_sandbox_guard.py::test_path_constants_redirect_to_tmp`) requests `tmp_kb_env` (or another sandbox-aware fixture) and asserts `kb.config.WIKI_DIR != PROJECT_ROOT / "wiki"` for the duration of a hypothetical test run. Both live in the same file; ~30 LOC total.
- **Reason:** R1 Q2.5 recommendation. Per `feedback_inspect_source_tests`, structural-only is signature-only (passes after revert if the autouse decorator is removed but a comment says "autouse"); behavioural-only risks circularity (the test fixture itself relies on autouse). Belt-and-suspenders is cheap.
- **Step 7 plan implication:** AC4 sub-ACs: (a) structural ast-parse test, (b) behavioural redirect test. Both named test functions in the plan-gate's 1:1 condition-to-test traceability matrix.

### Q2.6 — AC5 sys.modules walk: scoped to `kb.*` only OR all loaded modules?

- **Decision:** Option A — scoped to `kb.*` only. Iterate `[mod for name, mod in sys.modules.items() if name.startswith("kb.")]`. Add a regression test that stubs `kb._test_path_sensitive_module` with `@lru_cache`, runs the sandbox teardown, asserts the cache was cleared.
- **Reason:** R1 recommendation. Performance bound (~50-100 modules in `kb.*` vs 500+ for all loaded). Threat model T4 attack scenario explicitly names "a fourth `@lru_cache` added to `kb.utils.pages.load_section_titles`" — only `kb.*` is in scope. DeepSeek brainstorm cluster B alternative ("`importlib.metadata.packages_distributions()`") is more explicit but overkill for cycle 65; defer.
- **Step 7 plan implication:** AC5 sub-ACs: (a) replace hardcoded list at `tests/conftest.py:334-336` with sys.modules walk filter `name.startswith("kb.")`; (b) regression test stubbing `kb._test_path_sensitive_module`. Step 11 caller-grep: `Grep "load_purpose|_load_template_cached|_build_schema_cached" tests/conftest.py` returns ZERO hits in the teardown block (proving hardcoded list was REMOVED).

### Q2.7 — AC22 CI grep step: blocks PRs OR warns?

- **Decision:** Option A — BLOCKS PRs. CI step exits non-zero if `sk-ant-dummy` appears in any tracked file outside `.github/workflows/ci.yml`. Cost is one CI step that runs in <1s.
- **Reason:** R1 recommendation. `feedback_ci_cost_discipline` applies to NEW CI MATRIX dimensions (Windows runner cost), not new linting steps within the existing ubuntu-latest matrix. R2 D9 (false positives in `docs/reference/`) addressed by the existing `grep -v ".github/workflows/ci.yml"` filter — extend to `grep -v 'docs/reference/'` ONLY if Step 9 finds a false-positive (deferred to Step 11 caller-grep verification, NOT a Step 7 sub-AC).
- **Step 7 plan implication:** AC22 sub-AC: CI step in `.github/workflows/ci.yml` after the existing `pip-audit` job, named `dummy-key-leak-guard`. Test C19 ast-parses `ci.yml` and asserts the `run:` block contains `sk-ant-dummy` AND `git ls-files` AND filters out `ci.yml` itself.

### Q2.8 — AC12 helper location: `kb/ingest/url_filter.py` OR `kb/lint/fetcher.py`?

- **Decision:** Option B — `_url_scheme_allowed(url: str) -> bool` lives in `src/kb/lint/fetcher.py` next to `_url_is_allowed` at line 232. Gate at TWO chokepoints: (1) inside `_url_is_allowed` (so all existing callers benefit transparently), (2) explicitly at `lint/augment/orchestrator.py:234` (`if not _url_is_allowed(url, ...)` already exists; the scheme gate runs INSIDE `_url_is_allowed`, single chokepoint). DeepSeek brainstorm E2 chokepoint at `orchestrator.py:248` is honoured because `orchestrator.py` already calls `_url_is_allowed` at line 234.
- **Reason:** Requirements doc § BACKLOG drift findings is AUTHORITATIVE: "AC12 scope reduced to scheme allowlist only — most defense already shipped in `lint/fetcher.py`; verify and add scheme gate as the remaining hardening." DeepSeek brainstorm cluster E suggests `kb/utils/http_client.py::SafeTransport`; rejected because R1 Q2.8 recommendation cited "extending existing keeps it next to the existing defense, easier discovery" and SafeTransport doesn't process the URL string at the scheme level. R2 D5 (discoverability) addressed by inline docstring + CLAUDE.md "URL fetching" section (Step 17 doc update).
- **Step 7 plan implication:** AC12 sub-ACs: (a) add `_url_scheme_allowed(url: str) -> bool` returning `urlparse(url).scheme in {"http","https"}`; (b) call `_url_scheme_allowed` at the top of `_url_is_allowed` (return False on failure); (c) parametrized test `tests/test_cycle65_url_scheme.py` covering 5 rejection cases (`file://`, `gopher://`, `data://`, `javascript://`, `ftp://`); (d) DNS-rebind test reuses existing `lint/fetcher.SafeBackend` per T11. NO new module — just an addition to existing `lint/fetcher.py`.

### Q2.9 — AC23 same-class peer test: fail on fourth caller OR allow additions?

- **Decision:** Option B — assert the THREE historical sites are PRESENT but allow additional callers. Bumping the count requires a CHANGELOG-history note explaining the new caller's contract and same-class peer review.
- **Reason:** R1 recommendation. Threat T7 closure is achieved by the helper's existence + AC9's docstring contract; AC23 just guards the historical sites against accidental migration regression. Option A (`len(callers) == 3`) is annoying when a legitimate new caller lands and adds plan-gate friction without security gain.
- **Step 7 plan implication:** AC23 sub-AC: AST-walk in `tests/test_validator_contract_consolidation.py` finds all `Call(func=Name(id="_assert_under_project_root"))` occurrences, asserts the THREE historical sites (mcp/app.py:121 `_validate_wiki_dir`, mcp/app.py:230 `_validate_page_id` containment, compile/compiler.py:645 `_validate_path_under_project_root`) are PRESENT. Additional callers allowed; CHANGELOG-history note convention documented.

### Q2.10 — AC16 test with fixture-set env value OR real `ANTHROPIC_API_KEY`?

- **Decision:** Option A — fixture-set env values exclusively. Test sets `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-value-not-real")`, then asserts argv containing that exact string is blocked.
- **Reason:** R1 recommendation. `feedback_no_secrets_in_code`: "Real secrets go in .env (gitignored). Test fixtures resembling real tokens must be split-string constructed so platform scanners don't block pushes." Real `ANTHROPIC_API_KEY` in test scope risks pytest verbose output capture, GitHub Actions log retention, etc.
- **Step 7 plan implication:** AC16 sub-ACs: (a) replace regex-based `_check_no_secrets_on_argv` with value-based literal-equals check against the SIX env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, `DEEPSEEK_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`); (b) two-prong test (legitimate-token-shape allowed; literal env-value blocked); (c) BOTH tests use `monkeypatch.setenv` — never `os.environ.get(...)` to read a real key.

---

## Locked decisions on R2 devex findings D1-D11

| ID | Finding | Status | Reason |
|---|---|---|---|
| D1 | New `path_safety` module breadcrumb | DEFER-TO-STEP-17-DOC-ONLY | Adopted as `docs/reference/error-handling.md` "Path safety" section + CLAUDE.md Quick Reference bullet update. The helper's docstring is part of AC9 sub-ACs. |
| D2 | Deprecate `MODEL_TIERS` for one cycle | REJECT | Requirements drift correction explicitly KEEPS `MODEL_TIERS` per cycle 7 AC24 and versioned tests (`test_v099_phase39.py` + `test_v0912_phase393.py:423`). AC2 migrates internal callers ONLY. |
| D3 | AST meta-test failure messages | ADOPT | Sub-AC for AC4 + AC23: each AST assertion uses a custom helper `assert_decorator_present(func_def, expected_decorator, source_path)` that prints expected vs actual + line number on failure. Lives in `tests/_helpers/ast_walk.py` foundation commit. |
| D4 | Page-ID validation rationale in docstrings | ADOPT | Sub-AC for AC6/AC7/AC8: `_validate_page_id` docstring lists rejected patterns and links to Windows behaviour (NTFS ADS, `Path.resolve` stripping). Error messages name the offending character class. |
| D5 | Scheme allowlist discoverability | DEFER-TO-STEP-17-DOC-ONLY | Adopted as CLAUDE.md "URL fetching" section + inline comment near `_url_scheme_allowed` definition. The function itself is one line; docstring covers contract. |
| D6 | File-grouped commit ordering for new module | ADOPT | Step 7 plan locks the dependency-ordered commit sequence (R1 minimum path) — `kb/utils/path_safety.py` is committed BEFORE any file that imports it. The file-grouped batching (`feedback_batch_by_file`) is per-COMMIT, not per-CYCLE — order between commits is the dependency edge. |
| D7 | `__all__ = []` silently breaks `import *` | DEFER-TO-CYCLE-66 | Cycle 65 ships AC17 as-designed; documented in CHANGELOG.md compact entry that `import *` from `kb.graph.cache` is no longer supported. The DeprecationWarning sniffer (R2 suggestion) is YAGNI for cycle 65 — `import *` is explicitly discouraged in this codebase per cycle-18 L1; no known caller. Re-evaluate in cycle 66 if any user-reported breakage surfaces. |
| D8 | Token-shape regex replacement env-var test skip | ADOPT | Sub-AC for AC16: `monkeypatch.setenv("ANTHROPIC_API_KEY", ...)` wraps the test (already locked by Q2.10). The R2 concern about "test fails with confusing message about missing env var" is a false alarm because Q2.10 mandates fixture-set env exclusively. |
| D9 | CI `sk-ant-dummy` grep false positives in docs | DEFER-TO-CYCLE-66 | Cycle 65 ships AC22 as-designed (block on any tracked file outside ci.yml). If Step 11 caller-grep finds a legitimate `sk-ant-dummy` mention in `docs/reference/`, ADD `grep -v 'docs/reference/'` then; otherwise ship as-is. |
| D10 | Rename `_mcp_error_boundary` → `_mcp_error_handler` | REJECT | Naming consistency with cycle 18 AC13 + cycle 23 L4 vocabulary (`docs/reference/error-handling.md`, CHANGELOG-history.md) outweighs ergonomic relabeling. R2 D10's "boundary is UI jargon" claim is incorrect for this codebase. |
| D11 | Negative-control snapshot naming convention | ADOPT | Sub-AC for AC19: each paired negative-control test name suffixed `_neg_control` (e.g., `test_evidence_trail_snapshot_neg_control`). One-time docs note in `docs/reference/testing.md`. |

**Disposition tally: 7 ADOPT (D1, D3, D4, D5, D6, D8, D11) — wait, recount: D1=defer-doc, D3=adopt, D4=adopt, D5=defer-doc, D6=adopt, D8=adopt, D11=adopt. Recount with the table: ADOPT = D3, D4, D6, D8, D11 (5). DEFER-TO-STEP-17-DOC-ONLY = D1, D5 (2). DEFER-TO-CYCLE-66 = D7, D9 (2). REJECT = D2, D10 (2). Total = 11.**

---

## Final 23-AC list (locked)

For each AC: title, target file(s), chosen approach (file path + function name + signature), test conditions from threat model, and Step 7 sub-ACs the plan must split per cycle-9 L1 dual-mechanism rule.

### AC1 — `KB_PROJECT_ROOT` call-time accessor

- **File(s):** `src/kb/config.py`
- **Approach:** Add `def get_project_root() -> Path` reading `os.environ.get("KB_PROJECT_ROOT")` at call time + heuristic fallback. Add `def _reset_project_root() -> None` test helper (clears any internal cache used by `get_project_root`). Keep module-level `PROJECT_ROOT = _resolve_project_root()` BUT change it to delegate to `get_project_root()` so existing `kb.config.PROJECT_ROOT` attribute access reads call-time. Add `def __getattr__(name)` PEP 562 shim that re-routes `kb.config.PROJECT_ROOT` to `get_project_root()` on each access. Existing 200+ `kb.config.PROJECT_ROOT` callers see fresh values.
- **Test conditions:** C1 (T1)
- **Step 7 sub-ACs:** (a) add `get_project_root()` accessor; (b) add `_reset_project_root()`; (c) PEP 562 `__getattr__` shim; (d) `tests/test_cycle65_config_call_time.py::test_kb_project_root_call_time` exercises post-import `monkeypatch.setenv` then asserts the accessor reflects new value.

### AC2 — Migrate `kb.utils.llm` to `get_model_tier(tier)` + AST-walk guard

- **File(s):** `src/kb/utils/llm.py` (lines 17, 69-71); NEW `tests/test_config_no_direct_model_tiers.py`
- **Approach:** Change line 17 from `from kb.config import MODEL_TIERS` to `from kb.config import get_model_tier`. Change lines 69-71 from `if tier not in MODEL_TIERS: ... return MODEL_TIERS[tier]` to `try: return get_model_tier(tier) except ValueError: raise ValueError(...)`. KEEP `kb.config.MODEL_TIERS` and `kb.config._DEFAULT_MODEL_TIERS` (cycle 7 AC24). Add AST-walk test `tests/test_config_no_direct_model_tiers.py` walking `src/kb/**/*.py` excluding `config.py` itself, asserting zero `from kb.config import MODEL_TIERS` and zero `MODEL_TIERS[` references (treat the import name and subscript usage separately).
- **Test conditions:** C3 (T3)
- **Step 7 sub-ACs:** (a) edit `kb/utils/llm.py:17,69-71`; (b) AST-walk meta-test; (c) confirm versioned tests still pass unchanged.

### AC3 — `AUGMENT_ALLOWED_DOMAINS` call-time accessor

- **File(s):** `src/kb/config.py` (lines 478-480)
- **Approach:** Add `def get_allowed_domains() -> tuple[str, ...]` reading `os.getenv("KB_AUGMENT_ALLOWED_DOMAINS") or os.getenv("AUGMENT_ALLOWED_DOMAINS") or "en.wikipedia.org,arxiv.org"` then split + tuple. The dual env var name (`KB_AUGMENT_ALLOWED_DOMAINS` first, fallback `AUGMENT_ALLOWED_DOMAINS`) is the design lock for the env-var-name drift surfaced during grep verification (current source uses the unprefixed form per `config.py:480`). Migrate `kb.lint.augment.orchestrator:214,234` and `kb.lint.augment.proposer:78,105` from `config.AUGMENT_ALLOWED_DOMAINS` (attribute access) to `config.get_allowed_domains()` (call-time). PEP 562 `__getattr__` shim on `kb.config.AUGMENT_ALLOWED_DOMAINS` for back-compat with any test still using the constant.
- **Test conditions:** C2 (T2, partially T11 via AC12 dependency)
- **Step 7 sub-ACs:** (a) add `get_allowed_domains()` accessor; (b) `__getattr__` shim for back-compat; (c) migrate four call sites in `kb.lint.augment`; (d) `tests/test_cycle65_config_call_time.py::test_allowed_domains_call_time` parametrized over both env var names.

### AC4 — Sandbox autouse decorator AST guard + behavioural test

- **File(s):** NEW `tests/test_conftest_sandbox_guard.py`
- **Approach:** Two named test functions in same file: `test_autouse_decorator_present_structural` (ast-parses `tests/conftest.py`, locates `_autouse_kb_path_sandbox` `FunctionDef`, asserts decorator list contains a `Call` node with `func.attr == "fixture"` and `keywords` includes `keyword(arg="autouse", value=Constant(value=True))`) and `test_autouse_decorator_redirects_paths_behavioural` (instantiates pytest within pytest using `pytester` fixture, runs a probe test that touches `kb.config.WIKI_DIR`, asserts the path is under `tmp_path`).
- **Test conditions:** C4 (T4)
- **Step 7 sub-ACs:** (a) structural ast-parse test using `tests/_helpers/ast_walk.py::find_function_def`; (b) behavioural redirect test using `pytester`; (c) custom helper `assert_decorator_present` for legible failure messages (per R2 D3).

### AC5 — sys.modules walk over `kb.*` for cache_clear

- **File(s):** `tests/conftest.py` (lines 333-347 region)
- **Approach:** Replace hardcoded list `["kb.utils.pages.load_purpose", "kb.ingest.extractors._load_template_cached", "kb.ingest.extractors._build_schema_cached"]` with sys.modules walk: iterate `[mod for name, mod in sys.modules.items() if name.startswith("kb.")]`; for each module, iterate `vars(mod)`; if `getattr(attr, "cache_clear", None)` is callable, call it. Wrap in `try/except` per attribute so exotic objects can't break teardown.
- **Test conditions:** C5 (T4)
- **Step 7 sub-ACs:** (a) sys.modules walk replacing hardcoded list; (b) regression test stubbing `kb._test_path_sensitive_module` with `@lru_cache`, runs sandbox teardown (via fixture finalizer), asserts cache cleared.

### AC6 — `_validate_page_id` rejects trailing dot/space per segment

- **File(s):** `src/kb/mcp/app.py` (line 230 region)
- **Approach:** Add segment-by-segment check `for seg in page_id.replace("\\", "/").split("/"): if seg != seg.rstrip(". "): return error_message`. Place BEFORE the existing `resolve()` call (so the rejection fires before OS-level normalization can mask it). Error message: `"page_id segment %r has trailing dot or space (Windows would silently strip them)" % seg`.
- **Test conditions:** C6 (T5)
- **Step 7 sub-ACs:** (a) add segment-rstrip check; (b) parametrized 4-case test (`"secret."`, `"secret "`, `"foo/bar."`, `"foo/bar "`); (c) docstring update naming the rejected pattern + Windows rationale.

### AC7 — `_validate_page_id` rejects Windows-illegal chars

- **File(s):** `src/kb/mcp/app.py` (line 230 region)
- **Approach:** Add `_WINDOWS_ILLEGAL_CHARS_RE = re.compile(r'[:<>"|?*]')` near `_CTRL_CHARS_RE` (existing pattern). Use it in `_validate_page_id` at the same gate as `_CTRL_CHARS_RE`. Error message: `"page_id contains Windows-reserved character(s); rejecting for cross-platform parity (NTFS ADS hazard)"`.
- **Test conditions:** C7 (T6)
- **Step 7 sub-ACs:** (a) add `_WINDOWS_ILLEGAL_CHARS_RE`; (b) call inside `_validate_page_id` adjacent to `_CTRL_CHARS_RE`; (c) parametrized 7-case test (`:`, `<`, `>`, `"`, `|`, `?`, `*`).

### AC8 — `_validate_page_id` segment-aware `..` match

- **File(s):** `src/kb/mcp/app.py` (line 230 region)
- **Approach:** Replace `".." in page_id` substring with `any(seg == ".." for seg in page_id.replace("\\", "/").split("/"))`. KEEP the existing `resolve().relative_to(WIKI_DIR)` containment check (it's the actual safety net per Q1.6). Error message updated to `"page_id segment %r is parent-directory traversal" % ".."`.
- **Test conditions:** C8 (combined into AC9 test) — AC8 is part of `_validate_page_id` body; AC23's same-class peer scan covers this. Also has a positive test that `"notes..draft"` and `"c++..faq"` are now ACCEPTED (no longer rejected by substring match).
- **Step 7 sub-ACs:** (a) replace substring with split+segment-equals; (b) regression test for legitimate `..` substring acceptance; (c) verify existing `resolve().relative_to()` still fires on actual traversal.

### AC9 — Canonical `_assert_under_project_root` helper + 3-site migration

- **File(s):** NEW `src/kb/utils/path_safety.py`; `src/kb/mcp/app.py` (line 121 `_validate_wiki_dir`, line 230 `_validate_page_id` containment); `src/kb/compile/compiler.py` (line 645 `_validate_path_under_project_root`)
- **Approach:** New module `src/kb/utils/path_safety.py` exporting `_assert_under_project_root(path: Path, field_name: str, *, require_exists: bool = False, require_dir: bool = False, dual_anchor: bool = True, allow_symlinks: bool = False) -> None`. Body: dual literal-and-resolved anchor under `kb.config.get_project_root()` (call-time, depends on AC1); optional existence + isdir + symlink checks. Migrate `mcp/app.py:121 _validate_wiki_dir` to delegate (KEEP signature; body becomes `_assert_under_project_root(wiki_dir, "wiki_dir", require_exists=True, require_dir=True)` then `return wiki_dir.resolve(), None`). Migrate `compile/compiler.py:645 _validate_path_under_project_root` to delegate (KEEP signature; body becomes `_assert_under_project_root(path, field_name)`). Migrate `mcp/app.py:230 _validate_page_id` containment portion to delegate (containment-only; char rules from AC6/AC7/AC8 stay inline above).
- **Test conditions:** C8 (T7)
- **Step 7 sub-ACs:** (a) create new module + helper; (b) migrate `_validate_wiki_dir` body keeping signature; (c) migrate `_validate_path_under_project_root` body keeping signature; (d) migrate `_validate_page_id` containment portion; (e) AC9 alone has NO sub-AC for AC23 — that's a separate AC. Step 11 caller-grep checkpoint after each migration.

### AC10 — TOCTOU NOFOLLOW guard inside `rebuild_indexes` unlink

- **File(s):** `src/kb/compile/compiler.py` (lines 720-770 region inside `rebuild_indexes`); `src/kb/utils/path_safety.py` (helper extension)
- **Approach:** Primary path: replace `manifest_path.unlink()` and similar mutators inside `rebuild_indexes` with an open via `os.open(path, os.O_NOFOLLOW | os.O_RDONLY)` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows), then unlink/write through the resolved fd OR re-resolve immediately after open. Fallback path: per Q2.3, when the kernel flag unsupported, re-resolve immediately before mutation + one-time `logger.warning`. Wrap in helper `_open_no_follow(path: Path) -> int` in `src/kb/utils/path_safety.py`.
- **Test conditions:** C9 (T8)
- **Step 7 sub-ACs:** (a) add `_open_no_follow` helper to `path_safety.py`; (b) replace direct `unlink` calls in `rebuild_indexes` with helper-mediated open+unlink; (c) `tests/test_cycle65_rebuild_indexes_toctou.py::test_symlink_swap_rejected_primary` (uses `monkeypatch.setattr(Path, "unlink", swap_then_unlink)` to inject swap, asserts rejection); (d) `test_symlink_swap_rejected_fallback` exercises the re-resolve path with `monkeypatch` simulating `O_NOFOLLOW` unavailability; (e) `docs/reference/error-handling.md` "Path safety" section documents fallback warning.

### AC11 — Pin `GitPython` with explicit ceiling

- **File(s):** `requirements.txt` (line 82)
- **Approach:** Change `GitPython>=3.1.47` to `GitPython>=3.1.47,<3.2`. AST-parse-style test in NEW `tests/test_cycle65_dep_pinning.py::test_gitpython_has_ceiling` that reads `requirements.txt` and asserts the line containing `GitPython` matches both `==` or `>=` floor pattern AND `<` ceiling pattern.
- **Test conditions:** C13 (T12)
- **Step 7 sub-ACs:** (a) edit `requirements.txt:82`; (b) regression test asserting both floor + ceiling.

### AC12 — `_url_scheme_allowed` gate inside `_url_is_allowed`

- **File(s):** `src/kb/lint/fetcher.py` (line 232 region)
- **Approach:** Add `def _url_scheme_allowed(url: str) -> bool: return urlparse(url).scheme in {"http", "https"}` next to `_url_is_allowed`. Modify `_url_is_allowed` to call `_url_scheme_allowed(url)` first and return False on failure. Reuse existing `SafeBackend` for the rest (RFC1918/loopback/link-local + DNS-rebind already handled). NEW test `tests/test_cycle65_url_scheme.py` with parametrized rejection of `file://`, `gopher://`, `data://`, `javascript://`, `ftp://` plus DNS-rebind acceptance test using `monkeypatch.setattr("socket.gethostbyname", ...)` confirming the existing SafeBackend still catches the rebind.
- **Test conditions:** C10, C11, C12 (T9, T10, T11)
- **Step 7 sub-ACs:** (a) add `_url_scheme_allowed` helper; (b) gate at top of `_url_is_allowed`; (c) parametrized 5-case scheme rejection test; (d) DNS-rebind regression test exercising existing SafeBackend code path; (e) verify `_url_is_allowed` is called from all 4 existing chokepoints (`lint/fetcher.py:361,414,455` + `lint/augment/orchestrator.py:234` + `lint/augment/proposer.py:105`) — no new chokepoint needed.

### AC13 — `file_lock` around `VectorIndex.build`

- **File(s):** `src/kb/query/embeddings.py`
- **Approach:** Wrap the DROP → CREATE → INSERT → COMMIT block in `VectorIndex.build` with `file_lock(db_path.with_suffix(".db.lock"))` (using existing `kb.utils.io.file_lock` per CHANGELOG history). Existing `_rebuild_lock = threading.Lock()` (line 29) stays for in-process serialization; the file lock is the multi-process layer. Test C20 spawns two `multiprocessing.Process` instances calling `VectorIndex.build`, asserts via `time.monotonic()` that the second waits + dim consistency.
- **Test conditions:** C20 (T19)
- **Step 7 sub-ACs:** (a) wrap block in `file_lock`; (b) multi-process regression test using `multiprocessing.Process`; (c) verify no deadlock with existing `_rebuild_lock` (acquire-order documentation).

### AC14 — sqlite-vec extension load error sanitization

- **File(s):** `src/kb/query/embeddings.py` (`VectorIndex._ensure_conn` region around `sqlite_vec.load(conn)`)
- **Approach:** Wrap `sqlite_vec.load(conn)` in `try/except sqlite3.OperationalError as exc`; re-raise as `RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel")` with no path detail. The original exception's `__cause__` is the OperationalError (Python's `raise X from Y` mechanic); the AC21 boundary in MCP further sanitizes via `sanitize_error_text` in case __cause__ leaks.
- **Test conditions:** C16 (T15)
- **Step 7 sub-ACs:** (a) wrap `sqlite_vec.load`; (b) regression test using `monkeypatch.setattr(sqlite_vec, "load", lambda c: raise OperationalError("/home/user/.../vec0.so: ..."))` asserting re-raised message contains NEITHER `"/home"` NOR `".so"` NOR `"site-packages"`.

### AC15 — `TRAFILATURA_DOWNLOAD_NO_CACHE=1` in `lint/fetcher.py`

- **File(s):** `src/kb/lint/fetcher.py` (module init / top of file)
- **Approach:** Add `os.environ.setdefault("TRAFILATURA_DOWNLOAD_NO_CACHE", "1")` at module top (above any trafilatura import). `setdefault` honours developer override per Opus brainstorm F1 adjustment. Test asserts (a) env var set after `import kb.lint.fetcher`; (b) `monkeypatch.setattr(trafilatura, "fetch_url", spy)`, then call wrapping helper, assert spy observed env var set.
- **Test conditions:** C14 (T13)
- **Step 7 sub-ACs:** (a) `os.environ.setdefault` at module top; (b) two-stage regression test (env var present + spy observation).

### AC16 — `_check_no_secrets_on_argv` value-based scrub

- **File(s):** `src/kb/utils/cli_backend.py` (line 128 region)
- **Approach:** Replace regex-based detection with literal-equals comparison against the SIX env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, `DEEPSEEK_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`). Iterate over (env_key_name → env_key_value) for each non-empty value; iterate argv; if any element equals the value (using `secrets.compare_digest` for safety), raise the existing `LLMError`. DELETE the regex pattern entirely. Two-prong test (legitimate-token-shape allowed; literal env-value blocked) using `monkeypatch.setenv` exclusively per Q2.10.
- **Test conditions:** C18 (T17)
- **Step 7 sub-ACs:** (a) delete regex; (b) iterate env keys + literal-equals check; (c) two-prong regression test using `monkeypatch.setenv`.

### AC17 — `__all__ = []` in `graph/cache.py` + AST-walk guard

- **File(s):** `src/kb/graph/cache.py` (top of module); NEW `tests/test_graph_cache_no_direct_imports.py`
- **Approach:** Set `__all__ = []` at the top of `src/kb/graph/cache.py` (current file shows no existing `__all__` per grep at line 107 + line 203 only). AST-walk test in `tests/test_graph_cache_no_direct_imports.py` walks `src/kb/**/*.py` for `ImportFrom(module="kb.graph.cache", names=[alias(name="get_graph")])` patterns; asserts ZERO matches. Uses `tests/_helpers/ast_walk.py::find_imports_from`.
- **Test conditions:** C21 (T20)
- **Step 7 sub-ACs:** (a) add `__all__ = []`; (b) AST-walk meta-test rejecting direct imports.

### AC18 — `tests/test_security_cve_greps.py` CI-enforced SECURITY.md greps

- **File(s):** NEW `tests/test_security_cve_greps.py`
- **Approach:** For each grep declared in SECURITY.md (`diskcache`, `litellm`, `pip`, `ragas`), run a Python-`re` scan over `src/kb/**/*.py` (NOT subprocess `grep` — cross-platform parity per Q1.5). Assert zero hits. Failure message: `"Found %s in src/kb/%s — remove the package from src/kb or reclassify the CVE in SECURITY.md."`. Test uses `pathlib.Path(...).rglob` + `re.search` per file.
- **Test conditions:** C15 (T14)
- **Step 7 sub-ACs:** (a) scan helper using Python-`re` over `Path.rglob`; (b) four-package parametrized assertion; (c) failure message includes file path + matched line.

### AC19 — Snapshot tautology hardening (paired negative-control)

- **File(s):** `tests/test_cycle64_snapshots.py`; `.github/workflows/ci.yml`
- **Approach:** For each cycle 64 snapshot subject (evidence-trail, Mermaid export, lint-report-structure), add a paired test named `test_<subject>_neg_control` (per R2 D11) that mutates one input field of the captured-from path AND asserts `snapshot != actual`. Update CI pytest invocation to include `-p no:cacheprovider --snapshot-warn-unused`; remove `--snapshot-update` from CI invocations.
- **Test conditions:** C22 (T21)
- **Step 7 sub-ACs:** (a) add three paired `_neg_control` tests; (b) update `.github/workflows/ci.yml` removing `--snapshot-update` flag; (c) `tests/test_cycle65_ci_snapshot_flags.py` regression test asserting CI yml has zero `--snapshot-update` and presence of `--snapshot-warn-unused`.

### AC20 — `docs/reference/INDEX.md` + meta-test

- **File(s):** NEW `docs/reference/INDEX.md`; NEW `tests/test_docs_reference_index_complete.py`
- **Approach:** Hand-author `docs/reference/INDEX.md` listing each `docs/reference/*.md` file's first H1 + frontmatter. Add `tests/test_docs_reference_index_complete.py` asserting every `docs/reference/*.md` (excluding INDEX.md, README.md) appears in INDEX.md AND in the CLAUDE.md "Detailed Documentation" table.
- **Test conditions:** C23 (no T mapping — pure hygiene)
- **Step 7 sub-ACs:** (a) author INDEX.md; (b) meta-test asserting completeness in two locations.

### AC21 — `_mcp_error_boundary` decorator on MCP tools

- **File(s):** NEW `src/kb/mcp/_error_boundary.py`; modify `src/kb/mcp/core.py`, `src/kb/mcp/ingest.py`, `src/kb/mcp/quality.py`
- **Approach:** New module `src/kb/mcp/_error_boundary.py` exporting `_mcp_error_boundary` decorator. Body: catches `Exception`, logs full traceback locally via `logging.getLogger("kb.mcp").exception(...)`, returns `f"Error: {sanitize_error_text(e)}"` to the MCP client. Import `sanitize_error_text` from `kb.utils.sanitize` (NOT `kb.utils.text` — drift in threat model corrected). Apply `@_mcp_error_boundary` BELOW each `@mcp.tool()`-decorated function in the three target files. NOT applied to `mcp/browse.py` (already uses sanitize_error_text per OOS-3), NOT to `mcp/compile.py` or `mcp/health.py` (OOS-3).
- **Test conditions:** C17 (T16)
- **Step 7 sub-ACs:** (a) create new module + decorator; (b) apply decorator to each `@mcp.tool()` in core/ingest/quality.py; (c) parametrized regression test over each tool, force exception inside body, assert response is `Error: <sanitized>`; (d) Step 11 caller-grep checkpoint: `Grep "@mcp.tool" mcp/{core,ingest,quality}.py` count == `Grep "@_mcp_error_boundary" mcp/{core,ingest,quality}.py` count.

### AC22 — CI dummy-key leak guard

- **File(s):** `.github/workflows/ci.yml`; NEW `tests/test_cycle65_ci_dummy_key_guard.py`
- **Approach:** Add CI grep step after pip-audit: `name: dummy-key-leak-guard\n  run: \"git ls-files | xargs grep -l 'sk-ant-dummy' | grep -v '.github/workflows/ci.yml' | (! read)\"`. Step fails if `sk-ant-dummy` appears in any tracked file except `ci.yml` itself. Regression test ast-parses `ci.yml` (using PyYAML) and asserts the step exists with the expected `run:` block contents.
- **Test conditions:** C19 (T18)
- **Step 7 sub-ACs:** (a) add CI step in correct order (after pip-audit); (b) regression test asserting step presence + `run:` block contents.

### AC23 — `tests/test_validator_contract_consolidation.py` AC9 same-class peer scan

- **File(s):** NEW `tests/test_validator_contract_consolidation.py`
- **Approach:** AST-walk `src/kb/**/*.py` for `Call(func=Name(id="_assert_under_project_root"))` (and `Call(func=Attribute(attr="_assert_under_project_root"))`). Assert the THREE historical call sites are PRESENT: (1) `mcp/app.py` `_validate_wiki_dir`, (2) `mcp/app.py` `_validate_page_id` containment, (3) `compile/compiler.py` `_validate_path_under_project_root`. Additional callers ALLOWED per Q2.9. Failure message: `"AC9 historical site missing from migration: %s"`.
- **Test conditions:** C8 (T7)
- **Step 7 sub-ACs:** (a) AST-walk using `tests/_helpers/ast_walk.py::find_calls_of`; (b) assert ≥3 callers including the three named historical sites; (c) failure message names the missing site.

---

## CONDITIONS section (cycle-22 L5)

Each condition C1-C23 is a load-bearing test requirement that Step 7 plan MUST itemise as a sub-AC and Step 9 implementer MUST point at a test line for. Names per R1's recommendation (no parametrize-collapsing):

- **C1 (T1, AC1):** `tests/test_cycle65_config_call_time.py::test_kb_project_root_call_time` — `monkeypatch.setenv("KB_PROJECT_ROOT", "<tmp>")` AFTER `import kb.config`, assert `kb.config.get_project_root()` reflects new value.
- **C2 (T2, AC3, AC12):** `tests/test_cycle65_config_call_time.py::test_allowed_domains_call_time` — both env-var names tested; stale-env mutation does NOT bleed across accessor boundary.
- **C3 (T3, AC2):** `tests/test_config_no_direct_model_tiers.py::test_no_direct_model_tiers_imports` — AST-walk; versioned tests exempt.
- **C4 (T4, AC4):** `tests/test_conftest_sandbox_guard.py::test_autouse_decorator_present_structural` — strict AST per `feedback_inspect_source_tests`.
- **C4-bis (T4, AC4):** `tests/test_conftest_sandbox_guard.py::test_autouse_decorator_redirects_paths_behavioural` — pytester-based.
- **C5 (T4, AC5):** `tests/test_conftest_sandbox_guard.py::test_lru_cache_walk_clears_kb_modules` — stub `kb._test_path_sensitive_module`.
- **C6 (T5, AC6):** `tests/test_cycle65_validate_page_id.py::test_ac6_rejects_trailing_dot_or_space` parametrized 4 cases.
- **C7 (T6, AC7):** `tests/test_cycle65_validate_page_id.py::test_ac7_rejects_windows_illegal_chars` parametrized 7 cases.
- **C8 (T7, AC9, AC23):** `tests/test_validator_contract_consolidation.py::test_three_historical_sites_present` — AST-walk; ≥3 callers.
- **C9 (T8, AC10):** `tests/test_cycle65_rebuild_indexes_toctou.py::test_symlink_swap_rejected_primary` + `test_symlink_swap_rejected_fallback`.
- **C10 (T9, AC12):** `tests/test_cycle65_url_scheme.py::test_ac12_rejects_private_loopback_link_local` parametrized 8 cases.
- **C11 (T10, AC12):** `tests/test_cycle65_url_scheme.py::test_ac12_rejects_non_http_schemes` parametrized 5 cases.
- **C12 (T11, AC12):** `tests/test_cycle65_url_scheme.py::test_ac12_dns_rebind_rejected_via_safebackend`.
- **C13 (T12, AC11):** `tests/test_cycle65_dep_pinning.py::test_gitpython_has_floor_and_ceiling`.
- **C14 (T13, AC15):** `tests/test_cycle65_trafilatura_cache_disabled.py::test_no_cache_env_set` + `::test_fetch_url_observes_no_cache`.
- **C15 (T14, AC18):** `tests/test_security_cve_greps.py::test_<package>_zero_imports` (4 named tests, one per package).
- **C16 (T15, AC14):** `tests/test_cycle65_sqlite_vec_error_sanitised.py::test_sqlite_vec_load_error_no_path`.
- **C17 (T16, AC21):** `tests/test_cycle65_mcp_error_boundary.py::test_<tool_name>_error_sanitised` parametrized over each `@mcp.tool` in core/ingest/quality.
- **C18 (T17, AC16):** `tests/test_cycle65_check_no_secrets.py::test_legitimate_token_format_discussion_allowed` + `::test_actual_env_value_blocked`.
- **C19 (T18, AC22):** `tests/test_cycle65_ci_dummy_key_guard.py::test_grep_step_present_in_ci_yml`.
- **C20 (T19, AC13):** `tests/test_cycle65_vector_build_multiprocess.py::test_concurrent_build_serialised_via_file_lock`.
- **C21 (T20, AC17):** `tests/test_graph_cache_no_direct_imports.py::test_all_callers_use_attribute_lookup_form`.
- **C22 (T21, AC19):** `tests/test_cycle64_snapshots.py::test_<subject>_neg_control` (3 named tests).
- **C22-bis (T21, AC19):** `tests/test_cycle65_ci_snapshot_flags.py::test_ci_yml_no_snapshot_update`.
- **C23 (AC20):** `tests/test_docs_reference_index_complete.py::test_index_md_includes_all_reference_files` + `::test_claude_md_table_includes_all_reference_files`.

**Total named tests: 23 conditions → 30 named test functions** (some conditions split into 2 tests for dual-mechanism per cycle-9 L1). Step 7 plan-gate must verify the 1:1 mapping and reject any parametrize-collapsing that obscures per-AC test naming.

---

## Same-class peer scan (cycle-23 L4)

Per cycle-23 L4 / R1's enumeration, for every AC introducing a new helper / check / regression test, peers DELIBERATELY out of scope are named with one-line justification.

- **AC1 (`get_project_root` call-time) — peers OUT:** `STATUS_RANKING_BOOST`, `AUTHORED_BY_BOOST`, `PUBLISH_BELIEF_FILTERS`, kill-switch env vars `KB_DISABLE_VECTOR_AUTO_REBUILD` / `KB_DISABLE_COMPILE_AUTO_PUBLISH`. — *Justification:* feature-flag/doc-only constants; not security-anchoring; reload-leak applies but doesn't cross security threshold; defer to hygiene cycle.

- **AC2 (`MODEL_TIERS` migration) — peers OUT:** other config-namespaced constants in `kb.utils.llm` callers; ts/cache/log frame patterns. — *Justification:* AC2 is scoped to the inversion-corrected drift only; project-wide audit deferred to a future "config hygiene" cycle.

- **AC3 (`get_allowed_domains` call-time) — peers OUT:** other domain-allowlist style constants (none currently — verified by grep). — *Justification:* `AUGMENT_ALLOWED_DOMAINS` is the only such constant in scope.

- **AC4/AC5 (sandbox guards) — peers OUT:** non-autouse fixtures (`tmp_kb_env`, `kb_sandbox`, `real_project_root`); `_load_template_cached` migration to a different cache strategy. — *Justification:* AC4/AC5 close the autouse + lru_cache hazards; explicit fixtures keep cycle-12+ patch+mkdir contract.

- **AC6/AC7/AC8 (`_validate_page_id` char rules) — peers OUT:** `_validate_run_id` (cycles 17/29 hardened), `_validate_wiki_dir` containment (works on absolute paths post-OS-normalization), `raw/` ingestion path validator (OOS-1). — *Justification:* OOS-1 explicitly out; `_validate_run_id` already hardened; `_validate_wiki_dir` per OOS-4.

- **AC9 (path_safety helper) — peers OUT:** `_validate_page_id` char checks (live IN cycle 65 as AC6/AC7/AC8), `_validate_raw_source_path` (OOS-1), citation-graph URL handler in `evolve/` (OOS-2). — *Justification:* helper is for CONTAINMENT only; char rules + URL filtering are different threat classes (documented in helper docstring).

- **AC10 (TOCTOU NOFOLLOW) — peers OUT:** `ingest_source` writes (OOS-6), `compile_wiki` orchestration (OOS-5), `auto_publish_after_compile` writes (cycle 64 AC14). — *Justification:* AC10 is scoped to `compile/compiler.py::rebuild_indexes` unlink path; broader fan-out is Phase 4.5 R5.

- **AC11 (GitPython pin) — peers OUT:** other unbounded deps in `requirements.txt` (`arxiv 2.4.1` ↔ `requests` constraint per SECURITY.md). — *Justification:* GitPython has a 4-CVE history; arxiv constraint is a known-resolved cycle-22 L1 issue.

- **AC12 (scheme allowlist) — peers OUT:** URL handling in `evolve/` (OOS-2), `query/embeddings.py` (none — vector search is local), MCP tool descriptions (static strings). — *Justification:* OOS-2 is the deferred peer; no other URL surfaces in project.

- **AC13 (multi-process VectorIndex lock) — peers OUT:** `compile_wiki` orchestration race (OOS-5), `ingest_source` race (OOS-6). — *Justification:* broader fan-out coordination is Phase 4.5 R5.

- **AC14 (sqlite-vec sanitize) — peers OUT:** `VectorIndex.query` error sanitisation (cycle 64 AC8 partial), `compile/compiler.py::rebuild_indexes` other error sanitization. — *Justification:* AC14 targets specific extension-load path leak; broader sanitisation lives at AC21 MCP boundary.

- **AC15 (TRAFILATURA_DOWNLOAD_NO_CACHE) — peers OUT:** other dep env vars (`HTTPX_TIMEOUT`, etc.). — *Justification:* AC15 closes the diskcache transitive RCE chain only.

- **AC16 (value-based secret scrub) — peers OUT:** secret detection in MCP tool args, secret detection in env loading, secret derivation patterns (gap #2 from brainstorm). — *Justification:* OOS-10 explicitly out; AC16 fixes the self-DoS regression.

- **AC17 (graph/cache `__all__ = []`) — peers OUT:** other `kb.*` modules with snapshot-binding hazards (e.g., `kb.config.MODEL_TIERS` handled by AC2; `kb.utils.text.sanitize_error_text` no test-spy use case). — *Justification:* AC17 closes specific cycle-18 L1 detected drift; project-wide audit is future cycle.

- **AC18 (CVE greps test) — peers OUT:** SAST scanning on `tests/`, license scanning, supply-chain attestation. — *Justification:* AC18 mechanizes SECURITY.md table only; broader supply-chain is Phase 6.

- **AC19 (snapshot negative controls) — peers OUT:** snapshot subjects beyond cycle 64's three (OOS-8). — *Justification:* OOS-8 explicitly out.

- **AC20 (docs/reference/INDEX.md) — peers OUT:** auto-generation of CLAUDE.md "Detailed Documentation" table, auto-generation of CHANGELOG.md compact entries, frontmatter-driven docs index. — *Justification:* AC20 is hand-authored INDEX + meta-test; auto-generation is future cycle.

- **AC21 (MCP error boundary) — peers OUT:** `mcp/browse.py` (already uses sanitize_error_text), `mcp/compile.py` + `mcp/health.py` (OOS-3), CLI subcommand boundary in `cli.py` (OOS-9). — *Justification:* OOS-3 + OOS-9 explicitly out.

- **AC22 (CI dummy-key grep) — peers OUT:** other live key formats (`sk-or-`, `OPENAI_*`), base64-encoded forms (gap #4 from brainstorm). — *Justification:* AC22 anchors on `sk-ant-dummy` specifically; broader CI secret scanning is future cycle.

- **AC23 (same-class peer test) — peers OUT:** AST-walk regression for non-path-safety helpers, generic same-class peer scan harness. — *Justification:* AC23 is one-off targeted test; generalizing is `tests/_helpers/` evolution for future cycle.

---

## Signature drift watchlist (cycle-7 L4)

Per cycle-7 L4 / `feedback_signature_drift_verify`. Each signature change is a Step-11 caller-grep checkpoint. Confirmed by source grep verification at design lock time.

### Functions whose signature is touched in cycle 65

1. **`mcp/app.py:121 _validate_wiki_dir(wiki_dir: Path, ...) -> tuple[Path, str | None]`** — KEEP signature; body delegates to `_assert_under_project_root` (AC9). Step 11: `Grep "_validate_wiki_dir(" src/kb/ tests/` SAME count pre+post. Verified callers: `cli.py:633,651`, `mcp/health.py:12,19,76,142`, `mcp/browse.py:15,340`, `mcp/compile.py:5,12,46`, `mcp/core.py:33,51`. (8+ caller sites — wrapper-keep is the safe choice.)

2. **`compile/compiler.py:645 _validate_path_under_project_root(path: Path, field_name: str) -> None`** — KEEP signature; body delegates to `_assert_under_project_root` (AC9). Step 11: `Grep "_validate_path_under_project_root(" src/kb/ tests/` SAME count. Verified callers: `compile/compiler.py:724,732,737`, `compile/publish.py:684,691`, `query/embeddings.py:766,769` (7 sites).

3. **`mcp/app.py:230 _validate_page_id(page_id, ...) -> ...`** — KEEP signature; body adds AC6/AC7/AC8 char rules + delegates containment to `_assert_under_project_root`. Step 11: `Grep "_validate_page_id(" src/kb/ tests/` SAME count + new test cases for char-rule rejections. Verified callers: `mcp/quality.py:48,84,141,179,208,280,367,439`, `mcp/browse.py:93` (9 sites).

4. **`config.py PROJECT_ROOT` (module-level constant)** — becomes call-time via `get_project_root()` + PEP 562 `__getattr__` shim. Step 11: `Grep "from kb.config import PROJECT_ROOT" src/kb/ tests/` returns ZERO OR all matches in test files that intentionally test import-time-snapshot. Verified at `config.py:48-180` (multiple uses internal to config.py — these stay; external attribute access via `kb.config.PROJECT_ROOT` is back-compat). LOAD-BEARING — 200+ test files reference `kb.config.PROJECT_ROOT`.

5. **`config.py AUGMENT_ALLOWED_DOMAINS`** — same migration pattern via `get_allowed_domains()` + `__getattr__` shim. Verified callers: `lint/augment/orchestrator.py:214,234`, `lint/augment/proposer.py:78,105` (4 sites — migrated).

6. **`config.py MODEL_TIERS` + `_DEFAULT_MODEL_TIERS`** — KEEP per Q2.1. AC2 migrates `kb/utils/llm.py:17,69-71` only. Step 11: `Grep "MODEL_TIERS\[" src/kb/` returns ZERO outside `config.py` (test files exempt).

7. **`utils/cli_backend.py:128 _check_no_secrets_on_argv(argv: list[str]) -> None`** — KEEP signature; body rewrites regex → value-based. Step 11: `Grep "_check_no_secrets_on_argv\b" src/kb/ tests/` SAME count. Verified callers: `utils/cli_backend.py:178,185` (2 sites).

8. **`query/embeddings.py VectorIndex.build(force_rebuild=False) -> None`** — KEEP signature; body adds `file_lock` wrap. Step 11: SAME count.

9. **`lint/fetcher.py:232 _url_is_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool`** — KEEP signature; body adds `_url_scheme_allowed(url)` check at top. Step 11: SAME count. Verified callers: `lint/fetcher.py:361,414,455`, `lint/augment/orchestrator.py:234`, `lint/augment/proposer.py:105` (5 sites).

10. **`graph/cache.py:107 get_graph(wiki_dir, *, pages=None) -> nx.DiGraph`** — KEEP signature; only `__all__ = []` added. Step 11: `Grep "from kb.graph.cache import get_graph" src/kb/` returns ZERO (entire point of AC17).

### NEW functions introduced in cycle 65

- `kb/utils/path_safety.py::_assert_under_project_root(path, field_name, *, require_exists=False, require_dir=False, dual_anchor=True, allow_symlinks=False) -> None`
- `kb/utils/path_safety.py::_open_no_follow(path: Path) -> int` (helper for AC10)
- `kb/config.py::get_project_root() -> Path`
- `kb/config.py::get_allowed_domains() -> tuple[str, ...]`
- `kb/config.py::_reset_project_root() -> None` (test helper)
- `kb/config.py::__getattr__(name: str)` (PEP 562 shim — back-compat for `PROJECT_ROOT`, `AUGMENT_ALLOWED_DOMAINS`)
- `kb/lint/fetcher.py::_url_scheme_allowed(url: str) -> bool`
- `kb/mcp/_error_boundary.py::_mcp_error_boundary` (decorator)
- `tests/_helpers/ast_walk.py::find_imports_from(module: str, name: str) -> list[Path]`
- `tests/_helpers/ast_walk.py::find_function_def(file_path: Path, name: str) -> ast.FunctionDef | None`
- `tests/_helpers/ast_walk.py::find_calls_of(file_paths: list[Path], qualified_name: str) -> list[tuple[Path, int]]`
- `tests/_helpers/ast_walk.py::assert_decorator_present(func_def, expected_decorator, source_path)` (per R2 D3)

**All new functions lead with underscore (private)** per R1 signature-watchlist eng-mgr concern. Public API surface is NOT expanded by cycle 65.

---

## Step 7 plan inputs

### Foundation commit

- `tests/_helpers/ast_walk.py` — needed by AC4, AC17, AC18, AC20, AC23. Includes `assert_decorator_present` per R2 D3 for legible AST failure messages.
- `tests/_helpers/__init__.py` — make it an importable package.

### Commit ordering (R1's recommended sequence — confirmed)

```
1. foundation: tests/_helpers/ast_walk.py + __init__.py
2. AC18 (CVE greps test — surfaces accidental imports early)
3. AC11 (GitPython pin — no deps)
4. AC15 (TRAFILATURA env var — no deps)
5. AC1 (get_project_root call-time + __getattr__ shim)
6. AC2 (MODEL_TIERS migration in kb/utils/llm.py + AST guard)
7. AC3 (get_allowed_domains call-time + 4-site migration)
8. AC4 + AC5 (sandbox guards — structural + behavioural + sys.modules walk)
9. AC6 + AC7 + AC8 (page-id char rules — inside _validate_page_id, BEFORE AC9 migration)
10. AC9 (path_safety.py helper + migrate three sites — depends on AC1)
11. AC10 (TOCTOU NOFOLLOW + fallback inside helper / rebuild_indexes)
12. AC23 (same-class peer test — depends on AC9)
13. AC12 (_url_scheme_allowed in lint/fetcher.py)
14. AC13 (file_lock around VectorIndex.build)
15. AC14 (sqlite-vec error sanitize)
16. AC16 (cli_backend value-based scrub)
17. AC17 (graph/cache __all__ + AST test)
18. AC21 (mcp/{core,ingest,quality}.py error boundary — depends on AC14)
19. AC19 (snapshot negative controls + CI yml --snapshot-update removal)
20. AC20 (docs/reference/INDEX.md + meta-test)
21. AC22 (CI grep step in ci.yml)
```

This is 21 commits across ~14 files with explicit dependency edges (AC1→AC9, AC1→AC2, AC9→AC10, AC9→AC23, AC14→AC21, AC3→AC12). Per R2 D6 (file-grouped commits could break intermediate states), the dependency edges OVERRIDE alphabetical-by-file ordering — the foundation commit always lands first, AC1 lands before AC9, etc.

### Per-file grouping per `feedback_batch_by_file`

Per `feedback_batch_by_file`, each commit groups HIGH+MED+LOW from the same file together. AC6+AC7+AC8 share `mcp/app.py`; AC1+AC3 share `config.py`; AC13+AC14 share `query/embeddings.py`. AC2 alone touches `kb/utils/llm.py`. AC9 touches three files but the helper module creation is the load-bearing first step before each migration — split into 4 sub-commits within the AC9 logical unit if Step 7 plan prefers (per dependency-edge discipline).

### Plan-gate (Step 8) requirements

- 1:1 condition-to-test traceability matrix mapping all 23 conditions C1-C23 to named test functions; reject if Step 7 plan has parametrize-collapsing that masks per-AC tests.
- Explicit named test functions per AC (no parametrize collapsing per R1 § Test-coverage gap analysis). Naming convention: `test_ac<N>_<behaviour>` OR `test_<behaviour>_c<N>` per R2 § Failure-mode legibility audit.
- Step 9 begins with rebase-against-main + re-grep `_validate_*` line numbers — confirm AC9's three sites still match. If a fourth site appeared (cycles 53/59/61/62 in flight), expand AC9 OR escalate.
- Step 11 inserts caller-grep checkpoints AFTER each signature-touching commit (commits #5 AC1, #6 AC2, #7 AC3, #10 AC9, #11 AC10, #16 AC16, #17 AC17, #18 AC21).

---

## Step 9 implementation guardrails

- **Cycle-19 L2 reload-leak:** AC1's `get_project_root()` AND AC3's `get_allowed_domains()` AND AC15's TRAFILATURA env var read MUST happen at call time, never cached at import. AC1 internal cache (if any) cleared by `_reset_project_root()`.
- **Cycle-18 L1 attribute lookup:** AC9 callers use `import kb.utils.path_safety; kb.utils.path_safety._assert_under_project_root(...)` form — NOT `from kb.utils.path_safety import _assert_under_project_root`. AC17 enforces the same discipline for `kb.graph.cache.get_graph`.
- **Cycle-22 L5 conditions-as-tests:** every C1-C23 has a named test (30 named test functions per CONDITIONS section); plan-gate verifies the 1:1 map.
- **Cycle-23 L4 same-class peer scan:** AC23 codifies for AC9; same-class peer scan section above lists deliberate OOS peers per AC.
- **Cycle-3 L4 grep-verify:** all symbols listed in design verified at named line numbers via Grep at design lock time. One drift surfaced: `sanitize_error_text` lives in `kb.utils.sanitize` (NOT `kb.utils.text` per requirements/threat-model wording) — corrected in AC21 design. Another minor drift: `AUGMENT_ALLOWED_DOMAINS` env var has no `KB_` prefix in current source — AC3 reads BOTH names with `KB_` first.
- **Cycle-9 L1 dual-mechanism rule:** AC4 has both structural + behavioural tests; AC10 has both primary + fallback paths; AC16 has both negative + positive prongs.
- **`feedback_inspect_source_tests`:** AC4 structural test must use `ast.parse` + decorator-list assertion, NOT `inspect.getsource(module) + "X" in src`.
- **`feedback_no_secrets_in_code`:** AC16 test uses `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-value-not-real")` exclusively per Q2.10. NEVER reads real `os.environ.get("ANTHROPIC_API_KEY")` in test scope.
- **`feedback_signature_drift_verify`:** Step 11 caller-grep after each signature-touching commit per signature drift watchlist.
- **`feedback_batch_by_file`:** commits group HIGH+MED+LOW from same file; dependency edges override alphabetical ordering.

---

## Verdict

**APPROVE**

Rationale (under 200 words): The locked design resolves all 10 R1 unresolved questions Q2.1-Q2.10 with explicit choice + reason citation; disposes of all 11 R2 devex findings D1-D11 (5 ADOPT / 2 DEFER-DOC / 2 DEFER-CYCLE-66 / 2 REJECT). The BACKLOG drift corrections for AC2 + AC12 are AUTHORITATIVE per the requirements doc; threat-model T3/T9-T11 verify wording is corrected at design lock and propagated to Step 14. Two grep-verified source-vs-spec drifts surfaced (`sanitize_error_text` location, `AUGMENT_ALLOWED_DOMAINS` env-var prefix) — both corrected in AC21 + AC3 design. All 23 ACs map 1:1 to ≥30 named test functions covering C1-C23 (some conditions split per cycle-9 L1). Same-class peer scan exhaustively enumerated per AC. Signature drift watchlist confirms 10 signature-keep migrations + 12 NEW underscore-private functions; no public-API expansion. Step 7 commit ordering preserves dependency edges AC1→AC9, AC9→AC10, AC14→AC21, AC3→AC12 over alphabetical file grouping. Plan is at upper end of cycle complexity but each AC is small. Step 7 plan-gate must enforce the 1:1 condition-to-test matrix + explicit named test functions + Step 11 caller-grep checkpoints; with those gates, MiMo Coding can ship safely.
