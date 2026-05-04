=== reasoning ===
We need to produce a DeepSeek V4 Pro brainstorm for Cycle 65 of llm-wiki-flywheel. The user wants independent ideas, not implementation. The Opus brainstorm (likely a Claude model) will run in parallel. So we need to be different: contrarian, cross-cutting, simpler, standards-based, wrong target, etc.

We have 8 clusters A-H with specific ACs. We need for each cluster 2-3 alternative approaches, and for at least 5 ACs, suggest a different module or interface than what the requirements doc proposes. Also cross-cutting ideas, contrarian drop-this suggestions, and threats missing.

I'll structure the output as requested. I'll produce 50-80 distinct ideas across the whole. I need to be specific with file paths, function names. Reference past cycle lessons if applicable. I'm not implementing.

I'll now think through each cluster and generate alternative ideas.

**Cluster A: config.py call-time accessors (AC1-3)**
Original: AC1: KB_PROJECT_ROOT -> get_project_root(). AC2: migrate to get_model_tier(tier) with AST guard. AC3: AUGMENT_ALLOWED_DOMAINS -> get_allowed_domains().

Alternatives:
- Contrarian: These call-time accessors might be over-engineering; you could just use environment variables directly with lazy evaluation via module-level `os.environ` reads that have guards. Simpler: "smallest change" = just add a function for project root that returns `Path(...)` but that's already proposed. Could argue that using `functools.cached_property` on a singleton config object would centralize all these, rather than multiple getters. Cross-cutting: combine into a single Config class with getters that handle validation, and have an AST guard that all config accesses go through that object. Could propose using `importlib.resources` for project root discovery instead of `__file__` hacks.
- Different module: For AC2, instead of `get_model_tier()` in `kb.utils.llm`, maybe move tier resolution to a dedicated `kb/config/tiers.py` and import from there. The current `kb.utils.llm` might be too scattered; centralize config into `kb/config/settings.py` with a `Config` class and accessors.

Idea: "Don't do AC1: the project root is already discoverable via `importlib.resources.files('kb')` or `Path(__file__).resolve().parent.parent`. The function just adds a layer. But if it's for testability, ok."

I'll generate 2-3 per cluster.

**Cluster B: tests/conftest.py sandbox (AC4-5)** 
AC4: meta-test that `_autouse_kb_path_sandbox` has autouse=True. AC5: replace hardcoded lru_cache list with sys.modules walk over `kb.*`.

Alternatives:
- Contrarian: The meta-test for autouse is fragile; what if we rename the fixture? Simpler: Instead of a meta-test, add a pytest marker requirement and validate in conftest that the fixture is listed as autouse at import time. Or better: avoid sandbox and use pytest's `monkeypatch` with `tmp_path` - but it's already a sandbox. Cross-cutting: The `sys.modules` walk approach for AC5 might be too broad; maybe just use `importlib.metadata` to list all subpackages of `kb` and ensure they are in the sandbox list. But AC5's original idea of walking `sys.modules` is good. Different module: AC5 could be implemented in `conftest.py` directly without needing a separate utility, but that's same. Actually I need to suggest a different interface: maybe instead of `sys.modules` walk, we could use `pytest_collect_file` to dynamically collect from `kb` namespace package's `__init__.py`? Not sure.

For AC4: Could invert: make the sandbox fixture not autouse but a session fixture that is used explicitly? But requirement is autouse to prevent leakage. Maybe the meta-test is unnecessary; we can rely on a decorator or a static assertion in fixture code: if `not kwargs.get('autouse')` then raise. The AST test is overkill; just add an assert in the conftest itself: `assert _autouse_kb_path_sandbox._pytestfixturefunction.autouse` by accessing internal fixture object? Not great. A simpler: Just document that it must be autouse, and rely on code review; the cost of a missing autouse is a broken test isolated, not a security hole.

**Cluster C: mcp/app.py _validate_page_id (AC6-8)**
AC6: reject trailing-dot/space. AC7: reject `:<>"|?*`. AC8: segment-aware `..` instead of substring.

Alternatives:
- Contrarian: For AC6, Windows Path.resolve strips trailing dot/space, but on Linux it doesn't. The threat is path traversal via NTFS ADS. Since the system likely runs on Linux servers, maybe not needed. But best practice. Simpler: Instead of blacklisting characters, why not just use a whitelist of allowed page_id characters (e.g., `[a-zA-Z0-9_-]+`)? That would prevent all these issues. Cross-cutting: `_validate_page_id` could be replaced by a function that maps user-provided ID to a safe slug using `slugify` library, then resolves with Path; no need for complex checks. That would handle all traversal and special chars. Different module: AC6-8 could be handled by a new `kb/utils/sanitize.py` function `sanitize_page_id(pid)` that returns a safe filesystem name, and then no validation needed, just transformation. But transformation might change user identifiers; better to validate and reject.

Another idea: Use pathvalidate library (already a dependency?) to validate page_id. Check if it's already in deps. That would subsume AC6-7 with `pathvalidate.is_valid_filename` with platform=None. But need to watch for cross-platform.

**Cluster D: Validator-contract drift (AC9, AC10, AC23)**
AC9: extract `_assert_under_project_root` into `kb/utils/path_safety.py` and migrate 3 sites. AC10: close TOCTOU on `rebuild_indexes` unlink with O_NOFOLLOW or re-resolve. AC23: AST same-class peer scan test.

Alternatives:
- Contrarian: For AC9, instead of extracting a utility, we could enforce the contract by using a Path validation decorator on functions that take paths, e.g., `@validate_path_under_project_root` on any function parameter annotated with `Annotated[Path, UnderProjectRoot]`. This leverages decorator and typing. That could be a different interface. Could be in `kb/utils/validators.py` with a decorator. Cross-cutting: AC9 and URL filter (AC12) both check allowlists; maybe a unified "chokepoint validation" system with decorators for security checks. AC10: TOCTOU on unlink: could use `filelock` (like AC13) to synchronize and then do safe delete, but AC13 is already using `file_lock`. Might be cross-cutting: use file locking for all filesystem mutations in rebuild_indexes. Simpler: Instead of O_NOFOLLOW, just use `os.remove` with prior `os.lstat` to check it's not a symlink, but that's still TOCTOU. Better: use `tempfile.mkstemp` in a safe directory and then rename, but that's complex. For AC23: The AST peer scan test for validators is novel. Alternative: Instead of AST, use `inspect.signature` and `ast` to find functions that use `_assert_under_project_root` and ensure they are in the same module. That's similar.

Different module suggestion: For AC9, the path_safety.py module is okay. Suggest instead that the safety checks be embedded in a `SecurePath` subclass of `pathlib.Path` that overrides `resolve` and `open` to enforce under project root and no symlink traversal, and then migrate all validators to use that type. That would be a cross-cutting change that eliminates drift entirely.

**Cluster E: URL filter (AC12)** 
Current: only gap scheme allowlist. Add `_url_scheme_allowed(url)` checking http/https at orchestrator.py:248 chokepoint.

Alternatives:
- Contrarian: The URL filter chokepoint may not be sufficient. An attacker could bypass by using a URL like `file:///etc/passwd` via a relative URL scheme? But httpx doesn't support file. However, there could be other schemes that might be dangerous (ftp, gopher). Simpler: In the httpx transport already, you could add a transport hook that checks scheme. Actually, the mention says they already use httpx.SafeTransport+SafeBackend that rejects RFC1918 etc. Maybe they already have a custom transport that also enforces scheme. So instead of adding a separate check at the orchestrator, just ensure the SafeTransport (which is custom) enforces http/https. That would centralize URL safety. Different module: The scheme check should be inside the `SafeTransport` class (probably in `kb/utils/http_client.py`) rather than at each call site. So AC12 should be a change to `SafeTransport.__init__` to enforce scheme, not at orchestrator.py. That's a different module/interface.

- Another alternative: Use `pydantic.HttpUrl` validation when receiving URLs, early on. That would reject non-http schemes. That's a type-level enforcement.

Cross-cutting: The URL filter and MCP error sanitization both deal with security checks; maybe a unified security utility module for all validation points.

**Cluster F: Deps (AC11, AC15, AC18)**
AC11: pin GitPython. AC15: set TRAFILATURA_DOWNLOAD_NO_CACHE=1. AC18: new test_security_cve_greps.py.

Alternatives:
- Contrarian: For AC11, pinning GitPython may be unnecessary if there's no vulnerability in 3.1.47+; but the requirement says pin it to <3.2 due to some breaking change? Could argue to just let pip resolve with current lockfile. But the AC says "pin" for security. Simpler: Instead of a separate test file for CVEs (AC18), integrate the grep into the existing `security` test suite or CI job, not as a separate test script that needs to be maintained. Or convert SECURITY.md into an automated dependabot config that checks for CVEs. Different module: AC15's TRAFILATURA_DOWNLOAD_NO_CACHE should be set in a `startup.py` module or as a `conftest` fixture, not in `lint/fetcher.py` module init; that way it's testable and central. So not in module init.

- AC18: The grep test could be replaced with a script that runs in CI that checks `pip audit` for known vulnerabilities, rather than manual greps. That would be standards-based.

**Cluster G: MCP error/secret hardening (AC14, AC16, AC21, AC22)**
AC14: wrap sqlite_vec.load in try/except with sanitized RuntimeError. AC16: replace token-shape regex with literal env-value comparison. AC21: _mcp_error_boundary wraps tools using sanitize_error_text. AC22: CI grep step blocks `sk-ant-dummy` outside ci.yml.

Alternatives:
- Contrarian: For AC14, instead of try/except around load, we could ensure that sqlite_vec is loaded in a separate process and if it fails, the error is sanitized at the IPC boundary. That's overkill. Simpler: Use a custom exception class that strips paths in its `__str__`, and catch any exception from sqlite_vec, re-raise as that. Different module: AC21 could be implemented as a decorator `@sanitize_errors` on tool functions, rather than calling `_mcp_error_boundary` explicitly. That would be a different interface (decorator). Could be in `kb/utils/sanitize.py` as a decorator that wraps with try/except and calls sanitize. 

- AC16: The secret detection on argv could be replaced by using `pytest`'s option `--override-ini` to pass sensitive values, but that's not the same. Actually, they want to compare command-line arguments against environment variable values to prevent leaking. An alternative: Instead of regex, use `secrets.compare_digest` between each argv token and env var values, but that would still need to iterate. Actually, the current approach uses regex to detect "token shapes", but better to compare literal values. So AC16 is right. Maybe suggest that the check be done at startup (in `kb/__init__.py` or `mcp/__init__.py`) rather than in a specific submodule.

- AC22: The CI grep for sk-ant-dummy could be extended to a pre-commit hook that scans for any API key patterns, making it earlier in the dev cycle.

**Cluster H: Hygiene (AC13, AC17, AC19, AC20)**
AC13: file_lock around VectorIndex.build. AC17: __all__ = [] in graph/cache.py + AST-walk test. AC19: paired negative-control snapshot tests + drop --snapshot-update from CI. AC20: INDEX.md meta-test.

Alternatives:
- Contrarian: For AC13, file_lock on SQLite operations is already handled by SQLite WAL mode; adding an external lock might cause deadlocks. SQLite itself manages concurrent access. If multiple processes try to build the index, is that actually happening? Could be better to rely on SQLite's built-in locking and retry on busy, or use `BEGIN IMMEDIATE`. So drop AC13. For AC17, `__all__ = []` might break type checkers; better to use `__all__ = ["explicitly_allowed_symbols"]` or just remove the imports from `__init__.py` and rely on explicit imports. The AST-walk test might be overkill; just use a linting rule (like pylint's `useless-import-alias` or custom). AC19: Negative-control snapshot tests could be fragile; you could use property-based testing that fuzzes the snapshot generation and ensures it doesn't change unexpectedly. Different module: For AC20, instead of INDEX.md, use MkDocs' own navigation to generate the TOC, and test against that.

Now I need to produce at least 5 ACs where I suggest a different module or interface. I'll mark those in bold.

I'll generate the output in the specified format.

Also need cross-cutting ideas: like "Centralize all security-sensitive validation into a `kb/security/` package with a common Guard class that is used by all validators, URL filters, error boundaries, and secret checks. This would reduce drift and ensure consistency." Or "Use pydantic validators on all inputs (page_id, URLs, model tiers) to centralize validation, replacing multiple custom checkpoints." Or "Adopt `importlib.resources` for all path handling to avoid `__file__` and project-root assumptions."

Threats missing: Maybe "Prompt injection via augmented content could cause the system to make unsafe filesystem or network calls"? Not sure. Or "The use of GitPython to clone repos might be vulnerable to command injection if not sanitized correctly (but it's pinning)." Or "LLM-generated code executed in eval-like contexts? Not that." The current threat model (T1-T21) might be missing T22: "Dependency confusion attacks via mis-installed packages" - but AC11 and AC15 address that partially. Another: "Race condition in index build could lead to partial index corruption causing incorrect retrieval, leading to wrong LLM outputs, which could be a compliance issue." Might not be catastrophic. Could mention "Silent failure of path sandboxing when tests are skipped or misconfigured, leading to false security assumptions." The AC4/5 aim to ensure sandbox, but maybe a missing test for sandbox effectiveness.

Now I'll write the output.
=== answer ===
# Cycle 65 — DeepSeek V4 Pro Brainstorm

## Per-cluster alternatives

### Cluster A (config.py, AC1-3)

- **AC1 (KB_PROJECT_ROOT → `get_project_root()`):**  
  *Contrarian drop:* The project root is already determinable from any installed module via `importlib.resources.files('kb')`. A dedicated function is just indirection; skip it and instead enforce that all code uses `importlib.resources` (which also works with zip files, unlike `__file__`). If mocking is needed, monkeypatch `importlib.resources.files` in tests.  
  *Different interface: **Config object** — centralise all config accessors in a single `kb/config/__init__.py` class `Config` with `@property` getters. This eliminates scattered top-level functions and makes the AST guard trivial (check that all config references go through `Config`).  
  *Simplest:* Keep `KB_PROJECT_ROOT` as a `pathlib.Path` object, but compute it lazily via `functools.cached_property` on a module-level instance; no function call needed, just attribute access. AST guard can test that the attribute is never rebound.

- **AC2 (migrate `kb.utils.llm` from `MODEL_TIERS[tier]` to `get_model_tier(tier)` + AST guard):**  
  *Different module: **`kb/config/tiers.py`** — tier mapping is config, not a utility. Move `get_model_tier` there and import into `kb.utils.llm` as an alias. This separates concerns and makes the AST guard scope narrower.  
  *Standards-based:* Use `pydantic.Field` with `validate_default=True` and define a `ModelTier` enum. The configuration is then a `BaseSettings` instance, and call-time access is enforced by pydantic’s validation. No need for explicit AST guard; the type system prevents misuse at runtime.

- **AC3 (AUGMENT_ALLOWED_DOMAINS → `get_allowed_domains()`):**  
  *Cross-cutting:* The allowed domains are already validated in `orchestrator.py:248`. Instead of a new accessor, make the allowed domains a `frozenset` constant at the chokepoint module (the orchestrator), imported from config. The call-time security is ensured because the import happens once and is frozen.  
  *Small change:* `get_allowed_domains()` that returns a copy of the list; this is fine, but add a test that mutating the returned list does not affect the internal config. (Use `tuple` return.)

### Cluster B (tests/conftest.py sandbox, AC4-5)

- **AC4 (AST meta-test for `autouse=True`):**  
  *Contrarian:* The AST meta-test is fragile against fixture renaming and changes in decorator syntax. Simpler: in the conftest itself, add an assertion right after fixture definition:  
  ```python
  assert _autouse_kb_path_sandbox.autouse, "Sandbox fixture must be autouse=True"
  ```  
  This fails tests immediately if someone removes `autouse`, no AST needed.  
  *Different interface: **pytest marker** — require all test modules to explicitly apply `pytest.mark.sandbox`, and the fixture enables the sandbox only when the marker is present (like a fixture that checks `request.node.get_closest_marker('sandbox')`). This makes the requirement declarative and test-detectable without AST.

- **AC5 (replace hardcoded `lru_cache` list with `sys.modules` walk):**  
  *Alternative approach:* Use `importlib.metadata.packages_distributions()` to find all subpackages of `kb`, then ensure they are in the sandbox. This is more explicit than `sys.modules` walk (which may include unloaded modules).  
  *No change needed:* The current approach already works; the risk of missing a new submodule is low. Instead, add a test that any new `kb.*` module automatically gets caught by a CI lint that checks the sandbox list against the package structure. That’s a meta-test, not a runtime walk.

### Cluster C (mcp/app.py `_validate_page_id`, AC6-8)

- **AC6 (reject trailing dot/space):**  
  *Different module: **`kb/utils/sanitize.py`** — create a single `sanitize_page_id(pid: str) -> str` that normalises and validates all page ID rules (trim, reject illegal chars, reject `..`) and returns a clean `Path` segment. Then call this at all entry points, replacing `_validate_page_id`. This is simpler and more testable than three separate checks.*  
  *Contrarian:* On Linux, trailing dot/space is perfectly valid and does not cause any security problem. The Windows-specific stripping is a non-threat on server deployments. If the system never runs on Windows, skip. Add a CI check that ensures the service runs on Linux only.

- **AC7 (reject `:<>"|?*`):**  
  *Whitelist approach:* Instead of a growing blacklist, define a page ID as `[a-zA-Z0-9_-]+` (or `.` if dots allowed) and reject everything else. This automatically covers AC6 and AC8 as well, making all NTFS/reserved characters irrelevant.  
  *Standards:* Use `pathvalidate.validate_lain()` or `pathvalidate.is_valid_filename()` if the library is already a dependency. (Check `requirements.txt` or consider adding it; it’s lightweight.)

- **AC8 (segment-aware `..` instead of substring):**  
  *Different approach:* After splitting on `/`, verify each segment is not `..` and does not start with `.` (to avoid `.hidden` abuse). That’s already segment-aware; the substring check is just a lazy version. Use `all(part not in ('..', '.') and not part.startswith('.') for part in pid.split('/'))`. No need for a complex utility.

### Cluster D (validator-contract drift, AC9, AC10, AC23)

- **AC9 (extract `_assert_under_project_root` to `kb/utils/path_safety.py`):**  
  *Different module: **`kb/security/path_guard.py`** — make it a security-centric module that also contains a `SafePath` subclass of `pathlib.Path` that overrides `resolve()` and `open()` to enforce under-project-root and no symlink traversal. Then change all validators to accept `SafePath` instead of `Path`. This prevents drift by type enforcement; any new code that takes a `Path` won’t compile with the safety check.  
  *Decorator interface:* Create `@validate_path_under_project_root` that inspects function signatures (via `inspect`) and validates any argument annotated with `Annotated[Path, "under_root"]` before calling the function. This would be a cross-cutting security layer that can be applied to many functions, not just the three sites.

- **AC10 (TOCTOU on `rebuild_indexes` unlink):**  
  *Alternative chokepoint:* Instead of O_NOFOLLOW, wrap the entire index rebuild in a `file_lock` (like AC13), then perform all filesystem operations inside the critical section. The lock file is within the data directory. This eliminates the TOCTOU race entirely by mutual exclusion, and aligns with AC13’s pattern.  
  *Simplest:* Use `os.lstat` to check it’s a regular file (not symlink), then immediately `os.unlink`; the window is tiny and this is not a security-critical path (only admin rebuild). If an attacker can swap a symlink during that window, they already have local code execution. So consider dropping AC10 as non-exploitable.

- **AC23 (AST same-class peer scan test for validators):**  
  *Different test strategy:* Instead of AST, use `importlib.resources` to load the source of each validator’s module and `ast.parse` to find all calls to `_assert_under_project_root`, then check that each call’s function is defined within the same class. That’s still AST but more general.  
  *Alternative: use `unittest.mock` to mock `_assert_under_project_root` and verify that each validator calls it; if a validator does not call the mock in a test run, the test fails. That’s a behavioural test rather than static.

### Cluster E (URL filter, AC12)

- **AC12 (scheme allowlist at `orchestrator.py:248`):**  
  *Different module: **`kb/utils/http_client.py`** — the `SafeTransport` class already enforces IP-level restrictions. Add scheme enforcement there: override `resolve_connection` or `handle_request` to check `parsed_url.scheme` and raise `UnsupportedProtocol` for non-http(s). This closes the gap at the transport level, where it belongs, and all callers automatically benefit, not just the orchestrator.  
  *Pydantic early validation:* At the point where user-supplied URLs are deserialised (e.g., in API models or CLI args), enforce `HttpUrl` type. Pydantic will reject `file://`, `gopher://`, etc., making the orchestrator check redundant.  
  *Drop this AC?* The existing `SafeTransport` already prevents access to internal networks; a `file://` URL would not even reach the transport because httpx won't handle it. If an attacker could pass a non-http URL, they would need to exploit a deeper flaw (e.g., file:// used in another library like `requests`). The only real gap is `ftp://` but that’s not supported by httpx anyway. So AC12 may be unnecessary.

### Cluster F (deps, AC11, AC15, AC18)

- **AC11 (pin GitPython):**  
  *Different module: **`requirements.in` + `pip-compile`** — instead of a manual pin, use a constraints file generated by dependency scanning (e.g., `pip-audit` or `safety`). This allows flexible resolution of compatible versions while still blocking known-vulnerable ones. The pin to `<3.2` might be overly restrictive; consider `gitpython>=3.1.47,!=3.1.48` if a specific CVE exists.  
  *Cross-cutting:* Combine with AC18: have a CI step that runs `pip-audit` on the current environment and fails if any known vulnerability is found. That replaces both the manual pin and the CVE greps with a single audit.

- **AC15 (TRAFILATURA_DOWNLOAD_NO_CACHE=1):**  
  *Different module: **`conftest.py` or `pytest.ini`** — set the environment variable in the test configuration, not in the fetcher module init. Module-level side effects are hard to test and easy to overlook. In conftest, use `monkeypatch.setenv` in a session fixture. For production, set it in the deployment dockerfile or service supervisor config. This separates operational concerns from code.

- **AC18 (new test_security_cve_greps.py):**  
  *Standards-based: **`pip-audit` CI job** — run `pip-audit` with a configured vulnerability database; it covers diskcache, litellm, ragas etc. automatically. No need to grep SECURITY.md manually. A custom grep is fragile when SECURITY.md format changes.  
  *Alternative:* Use GitHub Dependabot alerts and enforce a policy that no alert remains open for more than 7 days. Then the test is just a check that dependabot alerts are addressed, not a code-level grep.  
  *Different test interface:* The grep test should scan `requirements.txt` or `pyproject.toml` for packages that are *allowed* to be flagged, then ensure that the latest version is used and no known CVEs exist for that version, using an API. But that’s overkill.

### Cluster G (MCP error/secret hardening, AC14, AC16, AC21, AC22)

- **AC14 (wrap `sqlite_vec.load` in sanitized try/except):**  
  *Different interface: **decorator `@sanitize_errors`** (from `kb/utils/sanitize`) that catches `Exception`, logs the full error internally, and re-raises a sanitized `RuntimeError`. This can be reused by AC21 and any future sensitive call. Apply `@sanitize_errors` above `sqlite_vec.load` call.  
  *Contrarian:* The path leaked is the path to the shared library, which is not a secret (it’s in the virtualenv). It reveals the installation directory, but that’s already known to the process owner. Only if the error message is returned to an external caller is it a risk. Add a global error handler in the MCP server that strips file paths from all responses, rather than patching each load site.

- **AC16 (replace token-shape regex with literal env-value comparison):**  
  *Different module: **`kb/utils/secret_guard.py`** — a function `validate_no_secrets_on_argv()` that compares every `sys.argv` token with the literal values of all known secret env vars (using `secrets.compare_digest`). Call it early in `kb/__init__.py` or in `main.py`. This decouples the check from the MCP context.*  
  *Simpler:* The regex approach is fine; the risk of false positive/negative is low if the token format is well-defined. Just ensure the regex is anchored and case-sensitive. A literal comparison could miss tokens that are base64-encoded or that have quotes, so it’s not strictly better. Consider not doing AC16 and stick with regex but add negative tests.

- **AC21 (`_mcp_error_boundary` wraps tools):**  
  *Different approach: **Middleware** — in the MCP framework, register an error mapper that takes any unhandled exception and runs `sanitize_error_text` on the message before returning to the client. This is more centralised and less error-prone than decorating each tool.  
  *Alternative: use `@tool_wrapper` decorator that internally calls `_mcp_error_boundary`; but AC21 already suggests that. The key alternative is a framework hook (like `register_error_handler`) if MCP supports it.

- **AC22 (CI grep blocks `sk-ant-dummy` outside ci.yml):**  
  *Pre-commit hook:* Move the check to a `pre-commit` hook that runs `grep -r sk-ant-dummy src/`; this catches the secret before it even reaches CI. Add a `.pre-commit-config.yaml` entry.  
  *Secrets scanning:* Use a tool like `git-secrets` or `detect-secrets` that already knows API key patterns, and ban sk-ant-dummy as a known dummy value. Then AC22 becomes a configuration of that tool. Simpler and more robust.

### Cluster H (hygiene, AC13, AC17, AC19, AC20)

- **AC13 (file_lock around VectorIndex.build DROP/CREATE/INSERT/COMMIT):**  
  *Contrarian: **Drop AC13.** SQLite with WAL mode handles concurrent writers safely; the race condition of two processes building the index simultaneously is non-destructive (the second build will simply fail to DROP if the table is locked, and can retry). The file_lock adds overhead and a potential deadlock if the lock file is not cleaned up. Rely on SQLite’s internal locking and add a retry loop with exponential backoff.*  
  *Different method: Use `BEGIN EXCLUSIVE` at the start of the build transaction; this will block other writers. It’s simpler and doesn’t need an external lock file.*  
  *Cross-cutting with AC10:* If we keep AC13, then use the same file locking utility for AC10 to avoid two different locking mechanisms.

- **AC17 (`__all__ = []` in `graph/cache.py` + AST-walk test):**  
  *Simplest: Just remove the `from kb.graph.cache import get_graph` from `kb/graph/__init__.py` entirely. Then nothing is exposed via `kb.graph`. If the function is needed, import it explicitly where used. No `__all__` needed. The AST-walk test can then assert that `graph/cache.py` has no symbols in `__all__` and that no `__init__.py` imports from that module.*  
  *Different lint rule: Use `pylint`'s `ungrouped-imports` or a custom rule that forbids importing from `kb.graph.cache` in `kb/graph/__init__.py`. Add to `.pylintrc`. Still requires a test, but more standard.

- **AC19 (paired negative-control snapshot tests + drop `--snapshot-update` from CI):**  
  *Alternative: Use property-based testing on the snapshot serialisation, generating random inputs and verifying that the snapshot never changes unless the structure changes. That provides negative control without needing a separate negative snapshot.*  
  *Drop `--snapshot-update` via pytest configuration:* In `pyproject.toml`, set `addopts = --no-snapshot-update` to prevent accidental updates, rather than relying on CI script removal. This is a one-line change.

- **AC20 (new INDEX.md + meta-test):**  
  *Different source of truth: Instead of maintaining an INDEX.md manually, use MkDocs’ `mkdocs-nav-enforce` plugin or a CI test that reads `mkdocs.yml` and checks that every markdown file in the repo is in the `nav` tree. Then INDEX.md can be auto-generated from that. The test verifies coverage, not a separate index.*  
  *Simpler: Generate INDEX.md from `docs/**/*.md` using a simple script (e.g., `find docs -name '*.md'`) and check that it matches the committed version. That’s the same idea but as a generation step instead of a meta-test.

---

## Cross-cutting ideas

1. **Unified security chokepoint module (`kb/security/`)**:  
   Move `path_safety.py`, `sanitize_error_text`, `secret_guard`, and `SafeTransport` into a single `kb/security/` package. Create a base `Guard` class that all validators, URL checks, and error boundaries must instantiate with configuration, ensuring that all security decisions are auditable and share common reporting. This reduces the chance of drift and makes it easier to apply new rules globally.

2. **Decorator-based contract enforcement**:  
   Instead of scattered `assert` calls, enforce security contracts with decorators:  
   - `@validate_path_safety` for functions taking file paths (applies `_assert_under_project_root` and symlink checks)  
   - `@url_safe` for functions that fetch URLs (does scheme/IP validation)  
   - `@sanitize_error` for MCP tools  
   These decorators can be composed, and their usage can be verified with AST or lint rules. This eliminates the need for many separate ACs.

3. **Pathlib subclass `SecurePath`**:  
   Introduce `from kb.security import SecurePath` which extends `pathlib.Path`. Its `resolve()` and `open()` methods enforce under-project-root and O_NOFOLLOW behaviour. All code that handles untrusted input is changed to accept `SecurePath` instead of `Path`. This single change addresses AC9, AC10, and any future path‑related threats. The type system ensures new code uses the safe version.

4. **Pydantic validation layer for all external inputs**:  
   Define pydantic models for `PageId`, `ModelTier`, `Url`, etc., with custom validators that enforce all rules. These models are used at the boundaries (API endpoints, CLI) and in tests. This approach covers AC1-3, AC6-8, AC12, and even parts of AC16 (argv secret detection could be modelled as a `SensitiveStr` type). Makes the system more declarative and testable.

5. **Single lock registry for filesystem operations**:  
   AC10 and AC13 both deal with race conditions. Create a `lock_registry` in `kb/utils/locking.py` that manages `filelock` instances keyed by canonical path. All code that modifies files
