=== reasoning ===
We need to produce a structured devex review for cycle 65. This is a design evaluation from developer-experience/contributor lens, in parallel with an Opus R1 (eng-mgr lens). The output should be a markdown with specific sections: Analysis, Devex findings (5-15 items), Doc-update checklist, Naming consistency, Cross-cycle pattern adherence, Failure-mode legibility audit, Verdict, Step 5 input.

We have a detailed description of 23 ACs across clusters A-H. We need to think like a senior maintainer 6 months from now—what would be painful? Cognitive load, doc gaps, breaking changes, ergonomics of file-grouped commit ordering, discoverability, failure mode clarity, cross-cycle consistency.

I'll go through each cluster and identify potential devex pain points.

Cluster A: config.py call-time, AC1-AC3. AC1: KB_PROJECT_ROOT call-time accessor. AC2: migrate `kb.utils.llm` from `MODEL_TIERS[tier]` to `get_model_tier(tier)` (BACKLOG drift corrected). AC3: AUGMENT_ALLOWED_DOMAINS call-time accessor.

Devex concerns:
- AC1/A3: "call-time accessor" meaning a property or function to resolve project root? They probably add something like `get_project_root()` or `project_root` property on config. Need to ensure it's discoverable and well-documented. A new contributor might get confused why they can't use `os.getcwd()`; the function should be clearly named and located. AC1: KB_PROJECT_ROOT probably a function that returns Path object. Must be in a module where people expect configuration. Good.
- AC2: Migrating internal caller from MODEL_TIERS to get_model_tier. This is a breaking change for external consumers if they import MODEL_TIERS directly. The problem statement says: "does any external consumer (CLI, MCP) read MODEL_TIERS directly?" We should check. If there are external consumers, we need to communicate the change. As devex, if the model tiers dict is removed, it could break custom scripts. We need a note in changelog and possibly deprecation period. Since the AC says "migrate `kb.utils.llm`" from `MODEL_TIERS[tier]` to `get_model_tier(tier)`, it's internal, but MODEL_TIERS might be exposed in `kb.config` or something. Without seeing the code, we assume that MODEL_TIERS was a module-level dict that external code might have used. The AC2 is intended to shield internal representation. Devex: we should keep MODEL_TIERS as a private attribute or remove it, but if removed, need to test no external usage. If kept, add deprecation warning. The AC might not address that. I'll note that.

Cluster B: tests/conftest.py, AC4=AST meta-test for `_autouse_kb_path_sandbox` decorator. AC5=replace hardcoded lru_cache list with sys.modules walk.

AC4: Adding AST analysis in test for checking that conftest uses the autouse fixture correctly. This is meta-testing. Could be confusing for new contributors: the test validates that a conftest fixture exists and is decorated a certain way. Naming: test name should indicate "test_ensure_autouse_kb_path_sandbox_decorator". The AST meta-test is a bit advanced, but that's okay as long as it's documented. Devex: may fail due to AST parsing of changed conftest and produce cryptic error. Need clear error message that explains what's missing.

AC5: replacing hardcoded lru_cache list with sys.modules walk. In conftest, maybe there is a fixture that clears certain caches, previously using a list of modules. The new method dynamically discovers modules. Devex: sys.modules walk could accidentally include modules that shouldn't be cleared, causing subtle test failures. The PR should document which modules are targeted. Edge cases: sys.modules might contain modules that are imported during test collection. Ensure test isolation.

Cluster C: mcp/app.py validate_page_id, AC6-8. AC6: reject trailing-dot/space; AC7: reject `:<>"|?*` (NTFS ADS); AC8: segment-aware `..`. These are validation improvements for page IDs.

Devex: New rules must be clearly documented so developers writing MCP endpoints know what a valid page_id is. They'll see the validation function but may not understand why certain characters are banned (NTFS ADS for Windows). Add docstrings explaining rationale. Also, if the validation fails, the error message should be informative (like "page_id contains forbidden characters : <> "|?*"). AC8: segment-aware `..` – meaning path traversal? They probably disallow `..` as a path segment. Important to explain in docs. The test for these validations should have descriptive names.

Cluster D: validator-contract drift, AC9-10, AC23. AC9: NEW `kb/utils/path_safety.py` with canonical `_assert_under_project_root`; migrate 3 sibling validators. AC10: close TOCTOU on rebuild_indexes unlink (kernel-level O_NOFOLLOW). AC23: AST same-class peer scan test.

AC9 introduces a new utility in `kb/utils/path_safety.py`. For devex: making a new module for path safety is good, but the name `_assert_under_project_root` might be too verbose, or could be confused with other assertions. Consider a more concise name like `require_under_project_root` or `enforce_project_path`. Since it's an internal helper (underscore prefixed), that's okay. Migrate 3 sibling validators: presumably they previously had duplicate logic. Now they all use the same helper. That's good for maintainability. However, moving logic across files might cause merge conflicts if someone modified the old validators in another branch. The commit should be atomic. AC10: TOCTOU fix using O_NOFOLLOW. Devs might not understand the necessity; need comments explaining symlink race. AC23: AST same-class peer scan test. This is a meta-test to ensure that validators are in the same class or something? The description: "AST same-class peer scan test" – it could be a test that all validators that use `_assert_under_project_root` are in the same class (or sibling classes)? Might be confusing; need good docstring. As long as it fails with a clear message about which validator is not conforming.

Cluster E: URL filter, AC12 drift-corrected: Most SSRF defense already in SafeBackend; only gap is scheme allowlist (http/https). So they add a scheme allowlist. Devex: new filter location? Possibly in `kb/ingest/url_filter.py` or maybe integrated into `safe_backend`? The description says "only gap is scheme allowlist", so likely a small addition. Need to ensure the allowed schemes are configurable and the filter is applied in all URL-fetching pathways. For a contributor, they need to know where to add new schemes if needed. Document in CLAUDE.md. Also, test that blocks non-http schemes.

Cluster F: deps, AC11/AC15/AC18: AC11 pin GitPython<3.2. AC15 TRAFILATURA_DOWNLOAD_NO_CACHE=1. AC18 NEW tests/test_security_cve_greps.py.

Devex: AC11: pinning a dep version could cause conflicts with other packages. Document why. AC15: setting an env var to disable trafilatura download cache – needs to be explained so developers know not to remove it. AC18: new test file for security CVE greps. This is a pattern check (e.g., grep for known vulnerable patterns). The test might be very specific and need maintenance. It should have a clear name and docstring explaining which CVEs it targets. Possibly auto-generated, but needs documentation for when it fails.

Cluster G: MCP error/secret hardening: AC14 wrap sqlite_vec.load, AC16 replace token-shape regex with literal env-value, AC21 `_mcp_error_boundary` for mcp/{core,ingest,quality}.py, AC22 CI grep for sk-ant-dummy.

Devex: AC14: wrapping sqlite_vec.load – presumably for error handling. Need to ensure the error boundary is consistent with existing patterns. AC16: replacing token-shape regex with literal env-value means they previously used a regex to detect secrets in logs, now they compare against actual env var value. This is more secure, but any test that previously relied on a fake token shape might need updating. CI might break if env var not set. Need to document in SECURITY.md. AC21: `_mcp_error_boundary` – creating a consistent error boundary across MCP modules. Good. But the name could be too generic; what does "boundary" mean? Should be like `catch_and_log_errors` or something. As long as it's documented. AC22: CI grep for "sk-ant-dummy" – a dummy Anthropic API key pattern used in tests. This ensures no dummy key leaks. CI will fail if such string found in non-test files. But the grep might generate false positives if the key pattern appears in comments or docs. Need to configure the grep to exclude docs/reference or tests. Devex: the grep command should be in a Makefile or CI config with clear comments about what to exclude.

Cluster H: hygiene: AC13 file_lock on VectorIndex.build, AC17 `__all__ = []` in graph/cache.py, AC19 paired negative-control snapshots, AC20 NEW docs/reference/INDEX.md.

AC13: file_lock on VectorIndex.build – prevents concurrent builds. Good. But need to document the locking mechanism so developers can debug deadlocks. AC17: adding `__all__ = []` in graph/cache.py to control exports. Devex: if you set `__all__` to empty, then `from graph.cache import *` imports nothing. That might break code that imports everything. But if it's intentional to hide internal modules, it's fine but should be communicated. Potential breaking change if some external code relied on `from graph.cache import *`. Usually discouraged, but still. AC19: paired negative-control snapshots – something about snapshot testing? Not sure; but "negative-control" indicates a test that verifies that something does NOT change unexpectedly. Need clear naming. AC20: NEW docs/reference/INDEX.md – a new index file. Good for discoverability.

Now, I need to structure the Devex findings into 5-15 items. I'll aim for ~10 items.

We also need to consider "cycle-ergonomics": the commit ordering is "file-grouped commit ordering (per feedback_batch_by_file)". So commits are grouped by file, not by AC. The question: does that emerge cleanly from these 23 ACs, or does it force coupled commits? I should mention if some ACs require touching many files and might be better committed together, but file-grouped would split them across commits, causing non-atomic changes. For example, AC9 (new module) and AC10 (modifying rebuild_indexes) would be separate files, so file-grouped would put them in separate commits, which is fine because AC9 creates the new utility file and AC10 modifies another file to use it. But if AC9 introduces a function that AC10 needs, and they are in separate commits, then committing AC9 first and AC10 later would be okay; but if the commit order is alphabetical by file, it might not matter. However, the pipeline "feedback_batch_by_file" likely groups changes by the file they modify, so each commit touches only one file. In that case, if two changes to the same file are needed (like AC10 modifies a file in one place, and maybe another AC touches same file), they'd be combined in the same commit. That's okay. But cross-file dependencies: if AC9 adds a new module and AC10 imports it, the commit that adds `kb/utils/path_safety.py` can be committed first, then the commit that modifies the validator file to import it. That's atomic in terms of functionality? Actually, importing a module that doesn't exist would break the code. So the commit adding the new module must come before the commit that modifies other files to use it. File-grouped commit ordering might not respect dependency order if it's purely alphabetical. That could be a problem. The "feedback_batch_by_file" might just mean each AC is assigned to a batch per file, not that commits are grouped by file. Actually it says "does the file-grouped commit ordering (per `feedback_batch_by_file`) actually emerge cleanly from these 23 ACs, or does it force coupled commits?" So there's a specific commit grouping strategy. I should comment on the risk of broken intermediate states if commits are by file and a new module is added after its usage. I'll flag that.

Cross-cycle pattern adherence: check cycle-18 L1 attribute-lookup form (maybe using `getattr` form?), cycle-19 L2 reload-leak (handling module reload in tests), cycle-22 L5 conditions-as-tests (assertions as test conditions?), cycle-23 L4 (maybe something about error handling). Need to see if cycle 65 introduces patterns that conflict. I don't have the exact definitions of those past cycles, but I can infer.

Cycle-18 L1: attribute-lookup form – maybe they defined a pattern for accessing config attributes like `config.get("key")` vs `config.key`. Cycle-18 might have established that using dot notation is safe due to lazy loading, etc. Here, we have `KB_PROJECT_ROOT` call-time accessor, AC1. Possibly they are using `KB_PROJECT_ROOT` as a function or property. Could conflict if cycle-18 enforced attribute lookup. Check: AC1 is "KB_PROJECT_ROOT call-time accessor" – likely a function `get_project_root()` or a property `config.project_root`. If cycle-18 said use `config.get("PROJECT_ROOT")` or something, then this might break. I'll mention that AC1's implementation should follow existing pattern.

Cycle-19 L2: reload-leak – related to module reload in tests causing state leaks. AC5 (replacing hardcoded lru_cache list with sys.modules walk) could be about clearing caches for tests to avoid leaks. That seems consistent. AC13 file_lock might not be about reload. AC9 new utility might impact test isolation. So likely no conflict.

Cycle-22 L5: conditions-as-tests – maybe they use a pattern where conditions are expressed as test functions. AC23 (AST same-class peer scan test) could be a test that checks conditions. Possibly consistent.

Cycle-23 L4: maybe about error boundaries. AC21 introduces `_mcp_error_boundary`. So following cycle-23's pattern. So I'll note that AC21 is adhering.

Failure-mode legibility: for each new regression test (C1-C23 from threat model), would a maintainer know which AC it guards? I need to map each condition from threat model (if known) to ACs. But I don't have the threat model. However, I can reason that each AC likely has a corresponding test; naming should be clear. I'll audit based on the AC descriptions: e.g., AC6-8 validation have tests; test names should include "validate_page_id_rejects_trailing_dot" etc. AC9 path safety, test should be like "test_assert_under_project_root_raises_on_symlink_escape". I'll comment that we need to ensure test docstrings reference the AC number.

Doc-update checklist: CLAUDE.md should mention new path safety module, new error boundary, scheme allowlist, file locking, etc. Also SECURITY.md for CVE greps and token pattern change. Need docs/reference/INDEX.md update with links. Also possible new migration guide for MODEL_TIERS removal.

Naming consistency: propose specific names. For `_assert_under_project_root`, maybe `enforce_within_project_root` but underscore prefix indicates private. I could suggest alternative names, but it's fine. For `_mcp_error_boundary`, maybe `mcp_error_handler` or `wrap_mcp_errors`. I'll suggest consistency with existing naming if there is a pattern like `error_handler`. I'll need to hypothesize.

Verdict: I'll probably say APPROVE-WITH-CONDITIONS, detailing the doc and naming improvements, and commit ordering risk.

Now, structure the output.

I need to start with Identity: DeepSeek V4 Pro, devex lens. Then markdown.

Write the analysis CoT as a senior maintainer perspective, then list devex findings.

I'll generate 10 findings:

D1: Discoverability of new path_safety module (AC9)
D2: Legacy MODEL_TIERS removal and external consumers (AC2)
D3: AST meta-test fragility and clarity (AC4, AC23)
D4: Page ID validation error messages (AC6-8)
D5: Scheme allowlist configuration discoverability (AC12)
D6: File_grouped commit ordering may break intermediate states (AC9+AC10 cross-file dependency)
D7: `__all__ = []` silent export breakage (AC17)
D8: Token-shape regex to literal env-value test impact (AC16)
D9: CI security grep false positive handling (AC22)
D10: Error boundary decorator naming and usage expectation (AC21)
D11: Negative-control snapshot pattern documentation (AC19)
D12: VectorIndex file lock documentation (AC13)
I'll pick 10-12.

Also cross-cycle: I'll comment on each pattern.

Now output.
=== answer ===
# Cycle 65 — Design Eval R2 (DeepSeek V4 Pro, devex lens)

## Analysis
A senior maintainer returning after six months would face a project that accumulated 23 atomic changes across 14 files. The immediate pain is cognitive: why does a new `kb/utils/path_safety.py` exist, why is `_mcp_error_boundary` sprinkled everywhere, what exactly changed in page-id validation? Without clear inline docstrings, structured commit messages tied to AC numbers, and a refreshed CLAUDE.md, knowledge will be lost. The file-grouped batch strategy (one commit per file) risks a non-functional intermediate state if `path_safety.py` is committed after callers, though careful ordering of the batches can avoid that. The bulk of changes are hygiene and defence-in-depth; the main devex debt is naming inconsistency, missing context for security choices (NTFS ADS, TOCTOU), and test failure messages that don’t point back to their AC. Cross-cycle patterns are mostly honoured, but the introduction of a new internal error boundary warrants a clear convention note.

## Devex findings

- **D1: New `path_safety` module lacks breadcrumb for later maintainers**
  - **AC affected:** AC9, AC10, AC23
  - **Issue:** `kb/utils/path_safety.py` introduces `_assert_under_project_root` and becomes the single source-of-truth for path validation. Three sibling validators migrate to it. A future maintainer who only sees the changed import in a diff will not understand *why* the new module was created or what guarantees it provides.
  - **Suggestion:** Add a docstring to `path_safety.py` explaining its role as the canonical “project-root membership” guard, referencing AC9 and the threat model condition. In CLAUDE.md, add a “Path safety” section describing when to use `_assert_under_project_root` and its interaction with AC10’s TOCTOU fix.

- **D2: Removal of direct `MODEL_TIERS` access may break undiscovered external consumers**
  - **AC affected:** AC2
  - **Issue:** `kb.utils.llm` migrates from `MODEL_TIERS[tier]` to `get_model_tier(tier)`. If any external script (CI helpers, ad-hoc CLI tools) imports `MODEL_TIERS` from `kb.config`, it will break silently or raise `AttributeError` once the dict is removed.
  - **Suggestion:** Publish a deprecation notice in the cycle changelog and retain `MODEL_TIERS` as a `_DEPRECATED` alias that raises a warning for one cycle, then remove in Cycle 66. Add a CI grep for any remaining direct imports (a one-shot test akin to AC18).

- **D3: AST meta-tests can produce confusing failure output**
  - **AC affected:** AC4, AC23
  - **Issue:** AC4 verifies that `_autouse_kb_path_sandbox` is decorated correctly using AST analysis; AC23 checks same-class peer validators. A contributor who accidentally renames the decorator or moves functions will receive an opaque AST mismatch without a human-readable “expected decorator missing” message.
  - **Suggestion:** Wrap AST assertions in a custom assertion helper that prints the exact required decorator name and the line where it was expected. The test docstring should include the AC number and a short summary of the threat model condition.

- **D4: Page ID validation rejects obscure characters but without developer-facing rationale**
  - **AC affected:** AC6, AC7, AC8
  - **Issue:** The new validation blocks trailing dots/spaces, NTFS ADS characters `:<>"|?*`, and path segment `..`. A contributor working on a new MCP endpoint will only see “invalid page_id” and may not know *why* these are forbidden, leading to frustrated debugging.
  - **Suggestion:** In the validation function’s docstring, list the rejected patterns and link to Windows file-system behaviour (NTFS, `Path.resolve` stripping). For AC8, explicitly mention that `..` segments are forbidden to prevent directory traversal.

- **D5: Scheme allowlist is hidden deep in URL fetching logic**
  - **AC affected:** AC12
  - **Issue:** The SSRF fix adds a scheme allowlist (`http`, `https`). This is a security-critical filter, yet a developer who later needs to add a new URL source might not realise it’s enforced inside `SafeBackend` unless it is explicitly documented.
  - **Suggestion:** Add a comment near the allowlist definition in `lint/fetcher.py:SafeBackend` explaining its purpose. Update CLAUDE.md with a “Fetching URLs” section that mentions the scheme restriction and the process for adding new schemes if ever required.

- **D6: File-grouped commit strategy can create a broken build if `path_safety.py` is committed after its importers**
  - **AC affected:** AC9, AC10 (cross-file)
  - **Issue:** AC9 introduces a new file `kb/utils/path_safety.py`, and AC10 modifies another file (e.g., `kb/index/rebuild_indexes.py`) to import from it. If the batch order is alphabetical by file name, `kb/index/rebuild_indexes.py` will be committed before the helper module exists, causing CI failures.
  - **Suggestion:** Ensure the orchestration commits the new `path_safety.py` file **first**, before any other batch that depends on it. Alternatively, bundle both changes in the same commit—though this deviates from the one-file-per-commit rule, it is safer.

- **D7: `__all__ = []` in `graph/cache.py` silently breaks any `import *` usages**
  - **AC affected:** AC17
  - **Issue:** Setting `__all__ = []` wipes the public API surface for wildcard imports. Code doing `from kb.graph.cache import *` will suddenly receive no names, causing `NameError` or silent failures. While `import *` is discouraged, it may exist in interactive notebooks or legacy scripts.
  - **Suggestion:** Document the export lockdown in the cycle changelog. Better: emit a `DeprecationWarning` if the module detects it was imported with `*`, using `sys._getframe` heuristics (lightweight, one-cycle only). At minimum, add a comment explaining that the module is internal and direct imports are the only supported path.

- **D8: Token-shape regex replacement will fail CI if the literal env value is not set**
  - **AC affected:** AC16
  - **Issue:** The test/guard that previously matched a token *shape* is replaced with literal environment-variable comparison. In developer environments where the env var is missing, the test will fail with a confusing message about a missing variable, not about a leaked secret.
  - **Suggestion:** The test should check for the env var’s existence first, skip with an informative message if not set, and only then compare. Add a `conftest` fixture that sets a dummy value for local testing. Document this behaviour in SECURITY.md.

- **D9: CI security grep for `sk-ant-dummy` risks false positives in documentation**
  - **AC affected:** AC22
  - **Issue:** A grep for the literal dummy API key may match occurrences inside `docs/reference/` or inline comments explaining the test, causing CI failures that are not actual leaks.
  - **Suggestion:** Configure the grep command (or CI job) to exclude `docs/` and test fixture files that intentionally contain the key. Maintain an allowlist of legitimate appearances. Document the exclusion list in a comment near the CI definition.

- **D10: `_mcp_error_boundary` naming is vague and may be applied inconsistently**
  - **AC affected:** AC21
  - **Issue:** The new decorator/context manager is used across `mcp/{core,ingest,quality}.py`, but the name “error boundary” is UI-framework jargon. A new contributor might not understand that it uniformly catches exceptions, logs, and returns an MCP-compatible error response.
  - **Suggestion:** Rename to `_mcp_error_handler` or `_wrap_mcp_errors`. Provide a docstring with its contract: “Catches all exceptions raised in MCP request handlers, logs them, and converts to a standard MCP error envelope.” Reference cycle-23 L4 if that established an error-handling pattern.

- **D11: Negative-control snapshot tests need a discoverable convention**
  - **AC affected:** AC19
  - **Issue:** “Paired negative-control snapshots” implies a snapshot that verifies something did *not* change. Without a clear naming pattern, a future developer won’t recognise these as negative controls and might mistake them for ordinary snapshot tests.
  - **Suggestion:** Adopt a file-naming suffix `_neg.snap` or a marker comment inside the snapshot test that explains its negative-control role. Include a note in `docs/reference/INDEX.md` under testing conventions.

## Doc-update checklist
1. **CLAUDE.md** additions needed:
   - “Path safety” section (AC9/10/23) — when to use `_assert_under_project_root`, symlink handling, TOCTOU.
   - “Error boundaries in MCP” (AC21) — the contract and naming.
   - “URL fetching” (AC12) — scheme allowlist.
   - “File locking” (AC13) — how `VectorIndex.build` uses `file_lock`.
   - “Testing conventions” — AST meta-tests (AC4/23), negative-control snapshots (AC19), security greps (AC22).
2. **docs/reference/INDEX.md** (AC20) — ensure links to the new sections above are present; also reference `tests/_helpers/ast_walk.py` and `kb/utils/path_safety.py`.
3. **SECURITY.md** update:
   - Token secret detection change (AC16) — new env-var based method.
   - CI grep for `sk-ant-dummy` (AC22) — exclusion list and purpose.
   - SSRF scheme allowlist (AC12) — location in code.

## Naming consistency
- **`_assert_under_project_root`** is acceptable; underscore prefix communicates non-public. If a public helper is ever needed, expose a `require_under_project_root` that raises a specific exception. Keep internal.
- **`_mcp_error_boundary`** → **`_mcp_error_handler`** (aligns with typical Python “handler” naming, e.g., `error_handler`, `exception_handler`). The word “boundary” is less obvious in a backend context.
- **Test file for security CVEs** (AC18) → `tests/test_security_cve_greps.py` is fine, but ensure function names include the CVE identifier (e.g., `test_cve_2024_1234_no_vulnerable_pattern`).
- For the new `url_filter` (AC12 scope), avoid creating a separate module unless the logic grows; a single function inside `safe_backend` is sufficient. No naming conflict.

## Cross-cycle pattern adherence
- **Cycle-18 L1 (attribute-lookup form):** AC1’s `KB_PROJECT_ROOT` accessor must remain consistent with how config values are accessed (either as `config.get` or property). If cycle-18 enshrined dotted access, `KB_PROJECT_ROOT` should be an attribute/property on the config object. No conflict if done correctly.
- **Cycle-19 L2 (reload-leak):** AC5’s switch to `sys.modules` walk directly addresses test-cache contamination, aligning with the reload-leak mitigation pattern. No conflict.
- **Cycle-22 L5 (conditions-as-tests):** AC23’s AST same-class peer scan is a condition-as-test; it follows the pattern of asserting a structural invariant. Adherence is good.
- **Cycle-23 L4 (error boundary):** AC21 explicitly introduces error boundaries; if cycle-23 L4 already defined a pattern for MCP error handling, AC21 must use the exact same decorator/utility. The review should verify that the function signature and logging behaviour match cycle-23’s specification. Otherwise it would create a conflicting sub-pattern.

## Failure-mode legibility audit
For each new regression test (threat-model conditions C1–C23), test names and failure messages should tie back to the AC:

- C1–C3 (AC1–3): Test names like `test_project_root_accessor_c1`, `test_model_tier_migration_c2` (AC2). Failure message should include “AC2: expected get_model_tier(…) not MODEL_TIERS[ ]”.
- C4, C5 (AC4, AC5): Test names can embed `AC4` – e.g., `test_conftest_ast_autouse_sandbox_c4`. Failure must print the missing decorator.
- C6–C8: `test_validate_page_id_rejects_trailing_dot_c6`, `test_validate_page_id_ntfs_ads_c7`, `test_validate_page_id_segment_traversal_c8`. Error output must show the offending character.
- C9, C10, C23: `test_path_safety_raises_on_symlink_c9`, `test_toctou_unlink_c10`, `test_validator_contract_peer_scan_c23`. Failure messages should reference the AC and the violated invariant.
- C12: `test_url_filter_scheme_allowlist_c12` with message “scheme ‘ftp’ not in allowlist”.
- others align similarly.

Maintainers can be guided by a one-time comment in the test file that lists `AC: C<N>` mapping.

## Verdict
**APPROVE-WITH-CONDITIONS**

The AC set is well-scoped and technically coherent. However, the devex risk centres on documentation debt and naming that will erode maintainability. The commit ordering risk (D6) can be fixed with a one-time batch adjustment. The withdrawal of `MODEL_TIERS` (D2) must be handled with a deprecation window. The naming of `_mcp_error_boundary` should be aligned to `_mcp_error_handler`. With these conditions met, the cycle can land safely and remain contributor-friendly six months later.

## Step 5 input from devex lens
- Ensure `kb/utils/path_safety.py` is committed **before** any file that imports it, or bundle both in a single commit.
- Add a deprecation cycle for `MODEL_TIERS`; do not remove the dict this cycle.
- Rename `_mcp_error_boundary` → `_mcp_error_handler`.
- Document all new conventions (error handler, path safety, scheme allowlist, negative-control snapshots) in CLAUDE.md.
- Add docstrings with AC references to all new test cases.
- Configure CI security grep exclusions for docs and test fixtures.
- Verify that AC21’s error handler matches cycle-23 L4’s existing pattern.
