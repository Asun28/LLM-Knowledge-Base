# Cycle 65 — STRIDE / OWASP Threat Model

**Cycle:** 65
**Date:** 2026-05-04
**Branch:** `feat/cycle-65`
**Pipeline step:** Step 2 (threat model) — consumed 1:1 by Step 14 (security verify)
**Tier:** 2 (multi-AC fold with security-touching items; per-AC threat-model entry + Step 14 verify required)

---

## Analysis

Per cycle-3 L7 (Opus 4.7 needs explicit CoT scaffolding), step through each AC cluster before mapping threats. The 23 ACs split into 7 risk-bearing clusters and 4 hygiene clusters; the threats below are anchored to the risk-bearing ones, with hygiene ACs receiving "verify by absence" checks.

### Cluster A — Call-time accessor migration (AC1, AC2, AC3)

`config.py` currently captures `KB_PROJECT_ROOT`, `_DEFAULT_MODEL_TIERS`, and `AUGMENT_ALLOWED_DOMAINS` at IMPORT time. The cycle-19 L2 reload-leak hazard says any post-import env mutation is silently ignored. The security relevance is:
- `KB_PROJECT_ROOT` underwrites every dual-anchor containment check in `mcp/app.py` and `compile/compiler.py`. If the import-time value differs from the call-time intent, the validator anchors to the WRONG root (e.g., a parent directory containing other repos).
- `AUGMENT_ALLOWED_DOMAINS` is the SSRF/exfil allowlist for `lint/fetcher.py`. A test setting `KB_AUGMENT_ALLOWED_DOMAINS=evil.example.com` after import would silently inherit the import-time list and either over- or under-permit (test-bleed in either direction).
- `_DEFAULT_MODEL_TIERS` is dual-mechanism (cycle-9 L1 generalisation): a future code path importing the constant directly bypasses the call-time accessor. Risk: a wrapper test that swaps `CLAUDE_*_MODEL` env vars succeeds against the accessor but the production code still uses the cached tier.

Threats: T1 (root-anchor confusion → containment bypass), T2 (allowlist-stale SSRF), T3 (tier-cache routing).

### Cluster B — Sandbox guard hardening (AC4, AC5)

`tests/conftest.py::_autouse_kb_path_sandbox` is the load-bearing seal that 200+ tests rely on to redirect `WIKI_DIR` / `RAW_DIR` / `PROJECT_ROOT` to per-test `tmp_path`. A silent `autouse=True` removal cascades to writes against the developer's real `wiki/` tree (and the CI runner's checked-out tree). AC4 freezes the autouse decorator structurally; AC5 generalises the lru_cache-clear list so a fourth path-sensitive `@lru_cache` doesn't silently leak between tests.

Threats: T4 (test-side production-data write).

### Cluster C — `_validate_page_id` hardening (AC6, AC7, AC8)

Three sibling weaknesses in the MCP path-id gate (`mcp/app.py:230`):
- Trailing-dot/space (`"secret."`, `"secret "`) — Windows `Path.resolve()` silently strips them, target-substituting a different file. Containment HOLDS (it still resolves under wiki_dir) but the OPENED file differs from the CHECKED file. This is filename-confusion, OWASP A01.
- `:` and `< > " | ? *` — NTFS Alternate Data Stream syntax (`page:hidden` opens the `:hidden` stream of `page`) and POSIX-vs-Windows divergence (POSIX accepts `<` literally).
- `".." in page_id` substring match — a cosmetic over-rejection (rejects legitimate `notes..draft`, `c++..faq`); replacing with segment-aware split eliminates false positives without weakening the actual safety net (`resolve().relative_to()`).

Threats: T5 (Windows trailing-dot/space substitution), T6 (NTFS ADS / Win-illegal-char divergence).

### Cluster D — Validator-contract drift (AC9, AC10, AC23)

Three current containment validators differ in CONTRACT:
- `mcp/app.py:121 _validate_wiki_dir` — absolute + exists + dir + single resolved-anchor.
- `compile/compiler.py:645 _validate_path_under_project_root` — no exists check, dual literal+resolved anchor (raises-only).
- `mcp/app.py:230 _validate_page_id` containment — substring `..` + resolved-anchor.

A future fourth call site can adopt the weakest contract by accident. AC9 extracts a single `_assert_under_project_root(path, *, require_exists=False, dual_anchor=True, allow_symlinks=False)` in `kb/utils/path_safety.py` and migrates all three sites; AC10 closes the TOCTOU window between containment validation and `unlink`/`write` in `compile/compiler.py::rebuild_indexes` (re-resolve immediately before mutation, OR open with `O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT`); AC23 codifies the cycle-23 L4 same-class peer scan as a regression test.

Threats: T7 (contract-drift weakest-link), T8 (TOCTOU symlink-swap on `rebuild_indexes`).

### Cluster E — URL → external CLI hardening (AC12)

`ingest/pipeline.py` currently doesn't directly invoke `trafilatura` / `crawl4ai` / `yt-dlp`, but the AC anchors a NEW helper `kb.ingest.url_filter._is_safe_url(url) -> bool` that future ingestion code paths MUST gate through. The threat surface:
- Scheme abuse: `file:///etc/passwd`, `gopher://`, `data://`.
- SSRF to cloud metadata: `http://169.254.169.254/latest/meta-data/iam/...` (AWS), `http://[fd00:ec2::254]/latest/...` (AWS IPv6), `http://metadata.google.internal/...`.
- Loopback / RFC1918 / link-local exfil: `http://127.0.0.1:6379` (Redis), `http://10.0.0.1`, `http://192.168.1.1`.

Mitigation requires `urlparse(url).scheme in {"http","https"}` + DNS-resolve hostname + `ipaddress.ip_address(addr).is_private or .is_loopback or .is_link_local`. Per cycle-19 L2, the function MUST read `KB_AUGMENT_ALLOWED_DOMAINS` at call time (depends on AC3 landing first or alongside).

Threats: T9 (cloud-metadata SSRF), T10 (file:// / gopher:// scheme abuse), T11 (DNS-rebind via repeated DNS lookup).

### Cluster F — Dependency hardening (AC11, AC15, AC18)

- AC11 pins `GitPython==3.1.47,<3.2`; without ceiling, an unattended `pip install -r requirements.txt -U` could pull a regression. Past CVEs: 2022-24439, 2023-40267, 2023-40590, 2024-22190.
- AC15 sets `TRAFILATURA_DOWNLOAD_NO_CACHE=1` to defeat the diskcache CVE-2025-69872 pickle-RCE chain through trafilatura's internal `fetch_url`. Project robots cache is in-memory `dict`, so direct exposure is mitigated; trafilatura's internals are NOT audited.
- AC18 elevates the SECURITY.md verification greps from documentation to a CI-enforced regression test. If a refactor adds `import diskcache` to `src/kb/`, the grep test fires CI-red.

Threats: T12 (dep-CVE drift via auto-bump), T13 (transitive diskcache pickle RCE), T14 (silent invalidation of accepted-CVE rationale).

### Cluster G — MCP error-response sanitisation + secret-shape DoS (AC14, AC16, AC21, AC22)

- AC14: `sqlite_vec.load(conn)` raises `sqlite3.OperationalError` whose message embeds the absolute filesystem path of the failing wheel (`/home/<user>/.venv/lib/python3.12/site-packages/sqlite_vec/...so`). Re-raising as a path-stripped `RuntimeError` closes the leak.
- AC21: each MCP tool wraps in `_mcp_error_boundary` that catches `Exception`, logs locally, and returns `f"Error: {sanitize_error_text(e)}"` to the client. Existing `kb.utils.sanitize.sanitize_error_text` (cycle 18 AC13) is reused. Closes information disclosure (filesystem paths, subprocess stderr) on the typically-trusted local boundary.
- AC16: `_check_no_secrets_on_argv` currently regex-matches `sk-[A-Za-z0-9_\-]{10,}|Bearer\s+\S+|ghp_[A-Za-z0-9]{10,}` against ALL argv elements. A user prompt that legitimately discusses key formats (`"how do sk- prefixes work in Anthropic API?"`) silently fails to spawn — self-DoS. Fix: refuse only if argv element equals the LITERAL VALUE of a listed env var.
- AC22: CI grep step blocks `sk-ant-dummy` from leaking into recorded cassettes / VCR / pytest-snapshot files outside `.github/workflows/ci.yml`.

Threats: T15 (sqlite-vec path leak), T16 (subprocess stderr / traceback path leak), T17 (secret-regex self-DoS), T18 (CI-dummy-key recorded in cassettes).

### Cluster H — Drift guards + hygiene (AC13, AC17, AC19, AC20)

- AC13: multi-PROCESS race on `VectorIndex.build` DROP→CREATE→INSERT→COMMIT. Existing `_rebuild_lock` is `threading.Lock` (in-process only). Two concurrent `kb` invocations against the same DB can produce a half-built index. `file_lock(db_path.with_suffix(".db.lock"))` closes it.
- AC17: `__all__ = []` in `graph/cache.py` + AST-grep test prevents a 6th caller using `from kb.graph.cache import get_graph` (snapshot-binding hazard per cycle-18 L1).
- AC19: snapshot tautology hardening — paired negative-control assertion + drop `--snapshot-update` from CI.
- AC20: docs/reference INDEX.md generation + meta-test.

Threats: T19 (multi-process DB-build corruption), T20 (snapshot-binding bypass via direct import), T21 (snapshot tautology — false-pass on revert).

---

## Threats

### T1 — KB_PROJECT_ROOT import-time stale value

- **Class:** Tampering, Elevation of Privilege
- **Affected ACs:** AC1
- **Attack scenario:** A test sets `monkeypatch.setenv("KB_PROJECT_ROOT", "/tmp/attacker")` after `import kb.config`. The module-level `_PROJECT_ROOT` already cached the original repo root; subsequent `_validate_path_under_project_root` calls anchor to the cached value, while the test ATTACKER FIXTURE expected validation against `/tmp/attacker`. In production, a long-running `kb mcp` server with a developer-rotated `KB_PROJECT_ROOT` (e.g., switching worktrees) silently keeps validating against the OLD root, so paths outside the new effective project tree are accepted.
- **Mitigation in cycle 65:** AC1 — `get_project_root()` accessor reads `os.environ["KB_PROJECT_ROOT"]` at call time; `_reset_project_root()` for tests; back-compat `__getattr__` shim on `kb.config.PROJECT_ROOT`.
- **Verify in Step 14 by:** `Grep "_PROJECT_ROOT = " src/kb/config.py` returns zero hits at module level (the assignment must be inside `get_project_root()`); `pytest tests/test_cycle65_config_call_time.py::test_kb_project_root_call_time` exercises post-import `monkeypatch.setenv` and asserts `kb.config.get_project_root()` reflects the new value.

### T2 — AUGMENT_ALLOWED_DOMAINS import-time stale value (SSRF allowlist bypass)

- **Class:** Spoofing, Information Disclosure
- **Affected ACs:** AC3, AC12
- **Attack scenario:** A test or runtime caller sets `KB_AUGMENT_ALLOWED_DOMAINS=internal.corp.local` to expand the allowlist for an evolution sweep. The module-level constant cached `["en.wikipedia.org", "arxiv.org"]` at import time, so the new domain is silently rejected (under-permits) — OR, the inverse: a test that NARROWS the allowlist for a negative-test is silently widened to the import-time default. Either case: tests pass green while production behaviour diverges.
- **Mitigation in cycle 65:** AC3 — `get_allowed_domains()` reads `KB_AUGMENT_ALLOWED_DOMAINS` at call time; AC12 helper `_is_safe_url` calls the accessor (NOT the constant).
- **Verify in Step 14 by:** `Grep "AUGMENT_ALLOWED_DOMAINS = " src/kb/config.py` only matches inside `get_allowed_domains()` body; `pytest tests/test_cycle65_config_call_time.py::test_allowed_domains_call_time`.

### T3 — _DEFAULT_MODEL_TIERS dual-mechanism bypass

- **Class:** Tampering
- **Affected ACs:** AC2
- **Attack scenario:** A future caller imports `from kb.config import _DEFAULT_MODEL_TIERS` (the underscore is advisory, not enforced). The constant captured `os.environ.get(CLAUDE_*_MODEL)` at import time. A test setting `CLAUDE_ORCHESTRATE_MODEL=test-stub-model` after import sees the accessor return the stub (because `MODEL_TIERS` re-reads), but the direct-import caller silently uses the cached production tier — routing test traffic to a paid API.
- **Mitigation in cycle 65:** AC2 — delete `_DEFAULT_MODEL_TIERS`; `MODEL_TIERS` accessor returns `os.environ.get(env_key, "").strip() or "<hardcoded-default>"` directly.
- **Verify in Step 14 by:** `Grep "_DEFAULT_MODEL_TIERS" src/kb/` returns zero matches anywhere in `src/kb/`; `pytest tests/test_cycle65_model_tiers.py::test_no_default_model_tiers_constant`.

### T4 — Autouse sandbox silent removal → real-tree write

- **Class:** Tampering, Repudiation
- **Affected ACs:** AC4, AC5
- **Attack scenario:** A future contributor refactoring `tests/conftest.py` removes the `@pytest.fixture(autouse=True)` decorator from `_autouse_kb_path_sandbox` (e.g., during a fixture-explicit-injection refactor, or accidentally during a merge conflict). All 200+ tests that ASSUMED autouse-redirect now write to `D:\Projects\llm-wiki-flywheel\wiki\` (developer machine) or `/home/runner/work/llm-wiki-flywheel/llm-wiki-flywheel/wiki/` (GHA). The damage is silent — pytest stays green, but `git status` after a test run shows production wiki contamination. SEPARATELY, AC5: a fourth `@lru_cache` added to `kb.utils.pages.load_section_titles` (hypothetical) caches a path-sensitive lookup across the tmp_path teardown boundary, leaking page state from test A into test B.
- **Mitigation in cycle 65:** AC4 — `tests/test_conftest_sandbox_guard.py` ast-parses `tests/conftest.py`, locates `_autouse_kb_path_sandbox` `FunctionDef`, asserts decorator list contains `pytest.fixture(autouse=True)`. AC5 — sandbox teardown walks every loaded `kb.*` module in `sys.modules`, introspects attributes for `cache_clear`, calls all of them.
- **Verify in Step 14 by:** `Read tests/test_conftest_sandbox_guard.py` shows `ast.parse` + decorator-list assertion (NOT a comment-grep); `Grep "load_purpose|_load_template_cached|_build_schema_cached" tests/conftest.py` returns zero hits in the teardown block (proving the hardcoded list was REMOVED, not just augmented); `pytest tests/test_conftest_sandbox_guard.py tests/test_cycle65_lru_cache_walk.py`.

### T5 — Windows trailing-dot/space target substitution

- **Class:** Tampering, Spoofing (filename confusion)
- **Affected ACs:** AC6
- **Attack scenario:** Adversary sends `kb_read_page(page_id="secret.")` to the MCP server. `_validate_page_id` checks `..` substring, control chars, length, Windows reserved basenames, and `resolve().relative_to(WIKI_DIR)` — ALL PASS, because `WIKI_DIR / "secret..md"` is under `WIKI_DIR`. On Windows, `Path("secret.").resolve()` silently strips the trailing dot and opens `secret`. Result: an attacker who can guess a page ID can target-substitute its sibling. Same for `"secret "` (trailing space). Same effect for `"foo/bar."` opening `foo/bar`.
- **Mitigation in cycle 65:** AC6 — `_validate_page_id` rejects any segment where `segment != segment.rstrip(". ")`.
- **Verify in Step 14 by:** `Read src/kb/mcp/app.py` lines 230-280 shows the `rstrip(". ")` guard added BEFORE `resolve()`; `pytest tests/test_cycle65_validate_page_id.py::test_rejects_trailing_dot tests/test_cycle65_validate_page_id.py::test_rejects_trailing_space tests/test_cycle65_validate_page_id.py::test_rejects_segment_trailing_dot` (3 cases: `"secret."`, `"secret "`, `"foo/bar."`).

### T6 — NTFS Alternate Data Stream / Windows-illegal-char divergence

- **Class:** Tampering, Information Disclosure
- **Affected ACs:** AC7
- **Attack scenario:** Adversary sends `kb_read_page(page_id="page:hidden")`. POSIX accepts the literal filename, but on Windows `:` is the NTFS Alternate Data Stream separator — `page:hidden.md` opens the `:hidden.md` ADS of `page`, which can carry arbitrary attacker-supplied content that bypasses normal `dir`/`ls` enumeration. Cross-platform divergence means a fixture that creates `page:hidden.md` on Linux ships normally; on Windows, the same caller surfaces a different artefact. Same hazard class for `< > " | ? *` (Windows-illegal, POSIX-legal).
- **Mitigation in cycle 65:** AC7 — `_validate_page_id` rejects `:` plus `< > " | ? *` at the same gate as `_CTRL_CHARS_RE`.
- **Verify in Step 14 by:** `Grep "_WINDOWS_ILLEGAL_CHARS_RE\|colon\|page:hidden" src/kb/mcp/app.py` shows the new char-class regex; `pytest tests/test_cycle65_validate_page_id.py::test_rejects_colon tests/test_cycle65_validate_page_id.py::test_rejects_windows_illegal_chars`.

### T7 — Validator-contract drift (weakest-link adoption)

- **Class:** Tampering, Elevation of Privilege
- **Affected ACs:** AC9, AC23
- **Attack scenario:** A future contributor adds a fourth path-accepting MCP tool (e.g., `kb_export_to_path`). They look at the existing trio (`_validate_wiki_dir` / `_validate_path_under_project_root` / `_validate_page_id` containment) and copy the WEAKEST one — perhaps a substring-only check, or a single-anchor (resolved-only) variant. The new tool accepts a path that resolves to `/etc/passwd` symlinked from inside the project tree, even though a stronger sibling validator would have rejected it. Per cycle-23 L4, this is exactly the same-class peer scan failure mode that bit cycle 23.
- **Mitigation in cycle 65:** AC9 — extract canonical `_assert_under_project_root` in `src/kb/utils/path_safety.py` with documented contract (`require_exists`, `dual_anchor`, `allow_symlinks`); migrate all three current sites to delegate. AC23 — `tests/test_validator_contract_consolidation.py` AST-walks `src/kb/**/*.py` and asserts the historical three sites (`mcp/app.py:121`, `mcp/app.py:230`, `compile/compiler.py:645`) all delegate to it.
- **Verify in Step 14 by:** `Read src/kb/utils/path_safety.py` shows the canonical helper with documented kwargs; `Grep "_assert_under_project_root" src/kb/` shows ≥3 callers (the historical sites) ALL using the new helper; `Grep -n "def _validate_wiki_dir\|def _validate_path_under_project_root" src/kb/` shows the original definitions are now thin wrappers / removed; `pytest tests/test_validator_contract_consolidation.py` (AST-walk regression).

### T8 — TOCTOU symlink-swap on rebuild_indexes unlink

- **Class:** Tampering, Elevation of Privilege
- **Affected ACs:** AC10
- **Attack scenario:** Adversary with local write access inside the project tree (e.g., a low-privilege user account on a shared dev box, or a malicious dependency post-install hook) creates a symlink at `wiki/.data/hashes.json` pointing to `/home/<user>/.ssh/authorized_keys`. They wait for a developer to run `kb rebuild-indexes`. The validator at `compile/compiler.py:645` resolves the path, confirms containment under PROJECT_ROOT, and returns. Between that check and the `manifest_path.unlink()` call (line ~750), the attacker (in a tight loop) replaces the symlink target with `/etc/passwd` (or, on Windows, replaces the file with a junction to `C:\Windows\System32\config\SAM`). The unlink follows the symlink and deletes the target. Variant: replace with a junction during the `file_lock` acquire wait.
- **Mitigation in cycle 65:** AC10 — `_assert_under_project_root` (and downstream callers in `compile/compiler.py::rebuild_indexes` unlink path) re-resolve + re-validate IMMEDIATELY before the `unlink`/write, OR open with `os.O_NOFOLLOW` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows) so symlink-following is rejected at the kernel.
- **Verify in Step 14 by:** `Grep "O_NOFOLLOW\|FILE_FLAG_OPEN_REPARSE_POINT\|allow_symlinks" src/kb/compile/compiler.py src/kb/utils/path_safety.py` shows the kernel-level guard; OR `Read src/kb/compile/compiler.py` lines 720-770 shows re-validation immediately before each `unlink`/`write_text`; `pytest tests/test_cycle65_rebuild_indexes_toctou.py::test_symlink_swap_rejected` (uses `pytest.MonkeyPatch` to inject a symlink between validate and unlink, asserts ValidationError).

### T9 — SSRF to cloud-metadata endpoints

- **Class:** Information Disclosure, Spoofing
- **Affected ACs:** AC12
- **Attack scenario:** Adversary submits `raw/articles/example.md` containing a frontmatter `source_url: http://169.254.169.254/latest/meta-data/iam/security-credentials/` (AWS) or `http://[fd00:ec2::254]/latest/...` (AWS IPv6) or `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token` (GCP). A future ingest path that resolves URLs server-side (e.g., a `kb augment` evolve sweep, or a cycle-N hybrid-augment ingest enhancement) DNS-resolves the hostname and connects, exfiltrating instance role credentials in the response body. The `source_url` round-trips through the wiki page's frontmatter.
- **Mitigation in cycle 65:** AC12 — new helper `kb.ingest.url_filter._is_safe_url(url) -> bool` enforces `urlparse(url).scheme in {"http","https"}` AND DNS-resolves hostname AND rejects when `ipaddress.ip_address(addr).is_private or .is_loopback or .is_link_local`. The 169.254.0.0/16 range is `is_link_local`; 127.0.0.0/8 is `is_loopback`; 10/8, 172.16/12, 192.168/16 are `is_private`. IPv6 fd00::/8 is `is_private`; ::1/128 is `is_loopback`.
- **Verify in Step 14 by:** `Read src/kb/ingest/url_filter.py` shows `import ipaddress` + the three-stage check; `pytest tests/test_cycle65_url_filter.py` covers each rejection class with parametrize: `http://169.254.169.254`, `http://127.0.0.1`, `http://10.0.0.1`, `http://[fd00::1]`, `http://[::1]`, `http://localhost`. CRITICAL: also test `http://example.com` resolving to `127.0.0.1` via monkeypatched `socket.gethostbyname` to confirm DNS resolution fires (not just URL-string parsing).

### T10 — Non-HTTP scheme abuse (file://, gopher://, data://)

- **Class:** Information Disclosure, Tampering
- **Affected ACs:** AC12
- **Attack scenario:** Adversary submits a source with `source_url: file:///etc/passwd` or `file:///D:/Users/Admin/.ssh/id_rsa` or `gopher://internal-redis:6379/_FLUSHALL%0d%0a` or `data:text/html;base64,...`. Per AC12, the URL flows to `trafilatura` / `crawl4ai` / `yt-dlp` argv. `yt-dlp` famously processes `file://` and many obscure schemes. `gopher://` to a Redis port can issue arbitrary RESP commands (CRLF injection).
- **Mitigation in cycle 65:** AC12 — `urlparse(url).scheme in {"http","https"}` allowlist BEFORE DNS resolution.
- **Verify in Step 14 by:** `pytest tests/test_cycle65_url_filter.py::test_rejects_file_scheme tests/test_cycle65_url_filter.py::test_rejects_gopher_scheme tests/test_cycle65_url_filter.py::test_rejects_data_scheme tests/test_cycle65_url_filter.py::test_rejects_javascript_scheme`.

### T11 — DNS-rebinding via repeated DNS lookup

- **Class:** Spoofing, Information Disclosure
- **Affected ACs:** AC12
- **Attack scenario:** Adversary controls `attacker.example.com` which resolves to `93.184.216.34` (Example domain) on the FIRST DNS query and `127.0.0.1` on the SECOND. AC12's helper resolves once and validates, then passes the URL string to `trafilatura.fetch_url(url)` which performs ITS OWN DNS lookup and connects to the second (loopback) address. The validation IP and the connect IP differ — classic TOCTOU on DNS.
- **Mitigation in cycle 65:** AC12 design must EITHER (a) connect using the resolved IP literal (host header preserved) so the second lookup is bypassed, OR (b) defer to `kb.lint.fetcher.SafeBackend` which is already DNS-rebind-safe per `lint/fetcher.py:1-15` ("SafeBackend rejects ANY DNS RR-set containing a private/loopback/link-local /reserved IP"). The Step 9 implementer should reuse SafeBackend — do NOT roll a new resolver in `ingest/url_filter.py`.
- **Verify in Step 14 by:** `Grep "SafeBackend\|SafeTransport" src/kb/ingest/url_filter.py` shows the helper either reuses `lint/fetcher.SafeBackend` OR resolves the IP literal once and passes that literal to subprocess; `pytest tests/test_cycle65_url_filter.py::test_dns_rebind_resistance` uses `monkeypatch.setattr("socket.gethostbyname", ...)` to return public IP first, loopback second, and asserts the URL is rejected (NOT connected to loopback).

### T12 — GitPython unbounded version → CVE regression

- **Class:** Elevation of Privilege (RCE), Tampering
- **Affected ACs:** AC11
- **Attack scenario:** Today `requirements.txt:82` reads `GitPython>=3.1.47`. A user runs `pip install -r requirements.txt -U` (or `pip install --upgrade GitPython`) and pulls a hypothetical regressed `GitPython==3.2.0` that re-introduces a 2023-40267-class arg-injection RCE. CI's `pip-audit` step audits the live env and would catch a CVE-listed version, but there's a window between regression-shipped and pip-audit-data-refreshed where the upgrade ships green.
- **Mitigation in cycle 65:** AC11 — `GitPython==3.1.47,<3.2` (or latest verified-safe) with explicit ceiling. Combined with cycle-34 four-gate Dependabot model (Step 2 baseline + Step 11 PR-introduced + Step 11.5 existing-CVE patch + Step 15 late-arrival warn).
- **Verify in Step 14 by:** `Grep "GitPython" requirements.txt` matches a line containing both `==` and `<` (i.e., explicit floor and ceiling); `pip-audit --ignore-vuln=...` step in CI green; `pytest tests/test_cycle65_dep_pinning.py::test_gitpython_has_ceiling` ast-parses requirements.txt and asserts ceiling presence.

### T13 — diskcache pickle-RCE chain via trafilatura

- **Class:** Elevation of Privilege (RCE)
- **Affected ACs:** AC15
- **Attack scenario:** Adversary submits a URL that trafilatura's internal `fetch_url` resolves. trafilatura uses diskcache to memoize HTTP responses (or robots.txt parsing per AC15 docstring); the cache stores pickle-serialized objects in `~/.cache/trafilatura/`. CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): a local attacker who can write to the cache directory (e.g., a malicious cron job, a separate compromised process, a low-priv user on a shared box) plants a malicious pickle. Next time trafilatura reads the cache, `pickle.load` executes arbitrary code in the context of the `kb` process (which holds API keys + write access to wiki/).
- **Mitigation in cycle 65:** AC15 — set `TRAFILATURA_DOWNLOAD_NO_CACHE=1` in `lint/fetcher.py` module init AND assert via test that `trafilatura.fetch_url(...)` is invoked with caching disabled.
- **Verify in Step 14 by:** `Grep "TRAFILATURA_DOWNLOAD_NO_CACHE" src/kb/lint/fetcher.py` shows the env var set at module load (NOT inside a function — must run before any trafilatura call); `pytest tests/test_cycle65_trafilatura_cache_disabled.py::test_no_cache_env_set tests/test_cycle65_trafilatura_cache_disabled.py::test_fetch_url_cache_disabled` (the second test patches `trafilatura.fetch_url` and asserts the env var is observable from within the call).

### T14 — Silent invalidation of accepted-CVE rationale

- **Class:** Repudiation, Tampering
- **Affected ACs:** AC18
- **Attack scenario:** SECURITY.md justifies accepting `litellm` / `diskcache` / `pip` / `ragas` advisories on the grounds that `grep -rnE "PKG_NAME" src/kb` returns zero hits (i.e., they're transitive / dev-only / tooling). A future PR adds `import litellm` to `src/kb/query/engine.py` (perhaps to use a LiteLLM router for cost-optimized fallback). The grep verification in SECURITY.md is hand-maintained doc — no CI gate fires. The accepted-CVE rationale silently becomes false; the project ships with a runtime LiteLLM Proxy template-injection RCE (GHSA-xqmj-j6mv-4862) the user thinks is mitigated.
- **Mitigation in cycle 65:** AC18 — `tests/test_security_cve_greps.py` runs each grep declared in SECURITY.md as a `subprocess` call against `src/kb/**/*.py` and asserts zero hits. CI failure: "remove the package from src/kb or reclassify the CVE in SECURITY.md."
- **Verify in Step 14 by:** `Read tests/test_security_cve_greps.py` shows ALL FOUR greps (`diskcache`, `litellm`, `pip`, `ragas`) wired up; `pytest tests/test_security_cve_greps.py` green; manually test by inserting `import litellm` in `src/kb/__init__.py` (revert immediately) and confirming the test fails.

### T15 — sqlite-vec extension load path leak

- **Class:** Information Disclosure
- **Affected ACs:** AC14
- **Attack scenario:** Adversary triggers a `kb_query` MCP call that walks through `VectorIndex.build` on a system where the sqlite-vec wheel is missing or corrupted (or compiled for the wrong glibc). `sqlite_vec.load(conn)` raises `sqlite3.OperationalError` whose message contains the absolute filesystem path of the failing `.so`/`.dll`: `/home/runner/work/llm-wiki-flywheel/.venv/lib/python3.12/site-packages/sqlite_vec/vec0.linux-x86_64.so: cannot open shared object file`. Without AC21's boundary, this string flows back to the MCP client. Combined with T16's traceback leak, an external MCP client (e.g., via a hosted MCP HTTP/SSE proxy in the future) learns the username, virtualenv layout, OS, and arch.
- **Mitigation in cycle 65:** AC14 — wrap `sqlite_vec.load(conn)` in `try/except sqlite3.OperationalError` and re-raise `RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel")` with NO path detail.
- **Verify in Step 14 by:** `Read src/kb/query/embeddings.py` shows the wrap (line ~660 area); `pytest tests/test_cycle65_sqlite_vec_error_sanitised.py::test_sqlite_vec_load_error_no_path` (monkeypatches `sqlite_vec.load` to raise `OperationalError("/home/user/.../vec0.so: ...")` and asserts the re-raised message contains neither "/home" nor ".so").

### T16 — MCP error-response traceback leak

- **Class:** Information Disclosure
- **Affected ACs:** AC21
- **Attack scenario:** Adversary triggers ANY MCP tool that internally hits an unhandled exception path — e.g., `kb_review_page(page_id="…")` where the LLM call raises a transient `httpx.ConnectError`. Without AC21, several MCP tools currently catch broad `Exception` but format the error as `f"Error: {e!r}"` or `f"Error: {str(e)}"`, embedding `httpx.ConnectError("/home/<user>/.config/claude-code/...")` paths or subprocess stderr containing absolute paths. Some tools have NO outer handler at all and let FastMCP propagate the full traceback to the client (filesystem paths from every frame's `__file__`). Combined with T15's sqlite-vec leak, an attacker on a hosted-MCP boundary maps the host filesystem.
- **Mitigation in cycle 65:** AC21 — wrap each MCP tool body with `_mcp_error_boundary` that catches `Exception`, logs full traceback locally, returns `f"Error: {sanitize_error_text(e)}"` to the MCP client. Reuses `kb.utils.sanitize.sanitize_error_text` (cycle 18 AC13).
- **Verify in Step 14 by:** `Grep "_mcp_error_boundary\|sanitize_error_text" src/kb/mcp/core.py src/kb/mcp/ingest.py src/kb/mcp/quality.py` shows the helper imported and applied to EVERY `@mcp.tool()`-decorated function; `Grep "except Exception" src/kb/mcp/` shows zero raw `f"Error: {e!r}"` or `f"Error: {str(e)}"` formatters (all routed through `sanitize_error_text`); `pytest tests/test_cycle65_mcp_error_boundary.py` parametrizes over every MCP tool and asserts the response from a forced exception is path-sanitised.

### T17 — _check_no_secrets_on_argv self-DoS regex over-trigger

- **Class:** Denial of Service
- **Affected ACs:** AC16
- **Attack scenario:** A user invokes `kb query "Compare sk-ant-foo and sk-or-bar API key prefixes for routing"` (legitimately discussing the format). The CLI subprocess wrapper calls `_check_no_secrets_on_argv(["query", "Compare sk-ant-foo and sk-or-bar API key prefixes for routing"])`. The current regex `sk-[A-Za-z0-9_\-]{10,}` matches `sk-ant-foo` (only if foo is ≥10 chars; expand to `sk-ant-foo-and-sk-or-bar-API-key-prefixes-for-routing` and the match fires). `LLMError` is raised, the spawn is refused, the user's prompt cannot be answered. Self-DoS. ALSO: a prompt containing a harmless GitHub repo description that mentions `Bearer` tokens triggers the regex.
- **Mitigation in cycle 65:** AC16 — replace generic regex with value-based scrub. Refuse only if argv element EQUALS the literal value of a listed env-var key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, `DEEPSEEK_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`).
- **Verify in Step 14 by:** `Grep "_TOKEN_PATTERN\|sk-\[A-Za-z0-9" src/kb/utils/cli_backend.py` returns zero matches (the regex must be DELETED, not augmented); `Read src/kb/utils/cli_backend.py` shows `_check_no_secrets_on_argv` iterating over `(ANTHROPIC_API_KEY, OPENAI_API_KEY, ...)` env keys and comparing literal values; `pytest tests/test_cycle65_check_no_secrets.py::test_legitimate_token_format_discussion_allowed tests/test_cycle65_check_no_secrets.py::test_actual_env_value_blocked` (two-prong: false-positive negative test + true-positive positive test).

### T18 — CI dummy-key leakage into recorded cassettes

- **Class:** Information Disclosure
- **Affected ACs:** AC22
- **Attack scenario:** A future test uses `vcrpy` / `pytest-recording` / `syrupy` to record an HTTP interaction. The test runs in CI with `ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only` set. The test mocks at the wrong layer (e.g., wraps `httpx.Client.send` but not the `Anthropic` SDK constructor) — the SDK reads the dummy key from env and embeds it in the `Authorization: Bearer sk-ant-dummy-key-for-ci-tests-only` header. The recorded cassette / VCR YAML / syrupy snapshot contains the dummy. The cassette is committed to the repo. While the dummy itself is harmless, (a) it pollutes the real-key search space, (b) future test refactors that swap the dummy for a live key under `pytest --record-mode=once` would silently leak the live key.
- **Mitigation in cycle 65:** AC22 — CI grep step `git ls-files | xargs grep -l "sk-ant-dummy" | grep -v ".github/workflows/ci.yml" | (! read)` fails if `sk-ant-dummy` appears in any tracked file except the CI workflow.
- **Verify in Step 14 by:** `Read .github/workflows/ci.yml` shows the new grep step; manually test by inserting `sk-ant-dummy` into a fresh test cassette path (revert) and confirming the CI step fails locally via `act` or shell-replay; `pytest tests/test_cycle65_ci_dummy_key_guard.py::test_grep_step_present_in_ci_yml`.

### T19 — Multi-process VectorIndex.build race

- **Class:** Tampering, Denial of Service
- **Affected ACs:** AC13
- **Attack scenario:** Two `kb` invocations run concurrently against the same wiki: process A is `kb compile` running `VectorIndex.build(force_rebuild=True)`; process B is `kb query "..."` triggering an auto-rebuild on dim-mismatch (cycle 64 AC6). Both processes pass the in-process `_rebuild_lock` (`threading.Lock`) — independent locks per process. A drops the table; B drops it again (no-op); A creates and starts inserting; B creates with different dim and starts inserting; A commits; B commits. Result: half the rows have dim=N, half have dim=M. Subsequent queries fail with mixed-dim errors, OR worse — silently return wrong neighbors.
- **Mitigation in cycle 65:** AC13 — take `file_lock(db_path.with_suffix(".db.lock"))` around the DROP → CREATE → INSERT → COMMIT block.
- **Verify in Step 14 by:** `Grep "file_lock" src/kb/query/embeddings.py` shows the lock acquisition wrapping the DROP/CREATE/INSERT block; `pytest tests/test_cycle65_vector_build_multiprocess.py::test_concurrent_build_serialised` (uses `multiprocessing.Process` to fire two builds simultaneously, asserts the second waits for the first via the file lock — measurable via `time.monotonic()` ordering).

### T20 — graph/cache.py 6th-caller direct-import bypass

- **Class:** Tampering (silent test-spy bypass)
- **Affected ACs:** AC17
- **Attack scenario:** Cycle 64 AC9 introduced `kb.graph.cache.get_graph()` with a strict cycle-18 L1 attribute-lookup-form discipline (callers MUST do `kb.graph.cache.get_graph(...)`, not `from kb.graph.cache import get_graph`) so a `monkeypatch.setattr(kb.graph.cache, "get_graph", spy)` test-spy fires. A future contributor adds `from kb.graph.cache import get_graph` to `src/kb/lint/checks/orphans.py` (the 6th caller). Tests that monkeypatch `kb.graph.cache.get_graph` to inject a stub graph fail to intercept the new caller; bugs in the new caller's invariants pass unit tests because they exercise the REAL graph (not the stub).
- **Mitigation in cycle 65:** AC17 — set `__all__ = []` in `graph/cache.py` AND add `tests/test_graph_cache_no_direct_imports.py` AST-grep test that fails CI on any `from kb.graph.cache import get_graph` in `src/kb/**/*.py`.
- **Verify in Step 14 by:** `Read src/kb/graph/cache.py` shows `__all__ = []` at module top; `Read tests/test_graph_cache_no_direct_imports.py` shows AST-walk over `src/kb/**/*.py` rejecting `ImportFrom` nodes with `module == "kb.graph.cache"` and `name == "get_graph"`; `pytest tests/test_graph_cache_no_direct_imports.py` green.

### T21 — Snapshot tautology (false-pass on revert)

- **Class:** Repudiation (tests claim coverage they don't have)
- **Affected ACs:** AC19
- **Attack scenario:** Cycle 64 captured syrupy snapshots for evidence-trail / Mermaid export / lint-report-structure. The snapshots were captured FROM the same code path under test. A revert of a production fix that the snapshot was supposedly guarding (e.g., a Mermaid escaping fix) is followed by `pytest --snapshot-update`; the snapshot updates to match the REVERTED behaviour and the test goes green. The tautology: snapshot IS WHATEVER the code outputs. Per cycle-22 L5 (load-bearing tests) and the user's `feedback_inspect_source_tests` (signature-only tests pass after revert), this is the same hazard class.
- **Mitigation in cycle 65:** AC19 — paired negative-control test per snapshot subject: mutate one input field and assert the snapshot does NOT match; CI pytest invocation drops `--snapshot-update`.
- **Verify in Step 14 by:** `Read tests/test_cycle64_snapshots.py` shows ≥3 paired negative-control assertions (one per snapshot subject); `Grep -- "--snapshot-update" .github/workflows/ci.yml` returns zero hits; `pytest tests/test_cycle64_snapshots.py` green; manual revert-test: temporarily mutate the production code that one snapshot guards, run pytest, confirm RED (then revert).

---

## CONDITIONS

Per cycle-22 L5, each condition below is a load-bearing test requirement that MUST land in Step 9 and that Step 14 verifies. Format: each bullet maps 1:1 to one regression test (or test-class).

- **C1 (T1, AC1):** Test `kb.config.get_project_root()` reads `os.environ["KB_PROJECT_ROOT"]` at CALL TIME — set the env var via `monkeypatch.setenv` AFTER `import kb.config` and assert the accessor reflects it. NOT a `kb.config.PROJECT_ROOT` shim test alone — must exercise the accessor.
- **C2 (T2, AC3, AC12):** Test `kb.config.get_allowed_domains()` reads `KB_AUGMENT_ALLOWED_DOMAINS` at call time; `_is_safe_url` calls the accessor (NOT the constant). Negative test: stale-env mutation does NOT bleed across the accessor boundary.
- **C3 (T3, AC2):** AST-parse `src/kb/config.py` — assert NO module-level `_DEFAULT_MODEL_TIERS` assignment; the accessor body returns env-or-default directly.
- **C4 (T4, AC4):** AST-parse `tests/conftest.py` — locate `_autouse_kb_path_sandbox` `FunctionDef` — assert decorator list contains `Call(func=Attribute(value=Name(id='pytest'), attr='fixture'), keywords=[keyword(arg='autouse', value=Constant(value=True))])`. NOT a comment-grep, NOT a `inspect.getsource` substring (cycle-7 / `feedback_inspect_source_tests`).
- **C5 (T4, AC5):** Test that adding a fourth `@lru_cache` attribute to a dummy `kb._test_module` and triggering test teardown calls `_test_module.func.cache_clear()` — proves the walk over `sys.modules` finds attributes dynamically.
- **C6 (T5, AC6):** Parametrized test of `_validate_page_id` rejecting `"secret."`, `"secret "`, `"foo/bar."`, `"foo/bar "` — three- to four-case assertion that the trailing-dot/space guard fires BEFORE `resolve()`.
- **C7 (T6, AC7):** Parametrized test of `_validate_page_id` rejecting `"page:hidden"`, `"page<hidden"`, `"page>hidden"`, `"page\"hidden"`, `"page|hidden"`, `"page?hidden"`, `"page*hidden"` — seven-case Windows-illegal-char rejection.
- **C8 (T7, AC9, AC23):** AST-walk `src/kb/**/*.py` finding all callers of `_assert_under_project_root`. Assert ≥3 callers including the historical sites (`mcp/app.py` _validate_wiki_dir, `mcp/app.py` _validate_page_id containment, `compile/compiler.py` rebuild_indexes).
- **C9 (T8, AC10):** Test `compile/compiler.py::rebuild_indexes` rejects symlink-swap between containment validation and `unlink`. Inject the swap via `monkeypatch.setattr(Path, "unlink", swap_then_unlink)` — assert `ValidationError` raised.
- **C10 (T9, AC12):** Parametrized test of `_is_safe_url` rejecting `http://169.254.169.254`, `http://[fd00::1]`, `http://127.0.0.1`, `http://10.0.0.1`, `http://172.16.0.1`, `http://192.168.1.1`, `http://[::1]`, `http://localhost` — eight-case private/loopback/link-local rejection.
- **C11 (T10, AC12):** Parametrized test of `_is_safe_url` rejecting `file:///etc/passwd`, `gopher://...`, `data:...`, `javascript:...`, `ftp://...` — five-case scheme-allowlist rejection.
- **C12 (T11, AC12):** Test that `_is_safe_url` either reuses `kb.lint.fetcher.SafeBackend` OR resolves the IP literal once and passes that literal downstream — NOT just URL-string parsing. Use `monkeypatch.setattr("socket.gethostbyname", side_effect=[public_ip, loopback_ip])` to force DNS-rebind; assert URL is rejected.
- **C13 (T12, AC11):** AST-parse `requirements.txt` — assert the `GitPython` line contains both `==` AND `<` (explicit floor and ceiling). NOT just a string-grep for "GitPython".
- **C14 (T13, AC15):** Two-stage test: (a) `os.environ["TRAFILATURA_DOWNLOAD_NO_CACHE"] == "1"` after `import kb.lint.fetcher`; (b) `monkeypatch.setattr(trafilatura, "fetch_url", spy)` then call the wrapping helper and assert spy observes the env var set in its execution context.
- **C15 (T14, AC18):** `tests/test_security_cve_greps.py` runs ALL FOUR greps from SECURITY.md (`diskcache`, `litellm`, `pip`, `ragas`) as `subprocess` calls against `src/kb/**/*.py` and asserts zero hits. Manual revert-style test: temporarily inject `import litellm` into a dummy file, confirm test fails (then revert).
- **C16 (T15, AC14):** `monkeypatch.setattr(sqlite_vec, "load", lambda c: raise OperationalError("/home/user/.venv/lib/python3.12/site-packages/sqlite_vec/vec0.so: cannot open"))` — assert the re-raised `RuntimeError` message contains NEITHER "/home" NOR ".so" NOR "site-packages".
- **C17 (T16, AC21):** Parametrized test over every `@mcp.tool()`-decorated function in `mcp/{core,ingest,quality}.py` — force an exception inside the tool body — assert the response is `f"Error: ..."` AND the error string passes `sanitize_error_text` (no abs paths, no tracebacks).
- **C18 (T17, AC16):** Two-prong test: (a) negative — argv containing `"sk-ant-foo-and-sk-or-bar-API-key-prefixes-for-routing"` is ALLOWED (no LLMError raised); (b) positive — argv containing the literal value of `os.environ["ANTHROPIC_API_KEY"]` (when set) IS blocked.
- **C19 (T18, AC22):** AST-parse `.github/workflows/ci.yml` — locate the new dummy-key grep step; assert the `run:` block contains `sk-ant-dummy` AND `git ls-files` AND filters out `ci.yml` itself.
- **C20 (T19, AC13):** `multiprocessing.Process`-based test: spawn two concurrent `VectorIndex.build` calls against the same db_path. Assert via `time.monotonic()` ordering that the second build waits for the first (file lock observed); assert the resulting DB has only ONE consistent dim.
- **C21 (T20, AC17):** Read `src/kb/graph/cache.py` — assert `__all__ == []`. AST-walk `src/kb/**/*.py` for `ImportFrom(module="kb.graph.cache", names=[alias(name="get_graph")])` — assert zero matches. Manual revert-test: insert one such import, confirm test fails (revert).
- **C22 (T21, AC19):** For each cycle 64 syrupy snapshot subject (evidence-trail, Mermaid export, lint-report-structure), commit a paired negative-control test that mutates one input field and asserts `snapshot != actual`. Plus `Grep -- "--snapshot-update" .github/workflows/ci.yml` returns zero matches.
- **C23 (AC20):** AST-walk `docs/reference/*.md` — assert every file (excluding INDEX.md, README.md) appears in BOTH `docs/reference/INDEX.md` AND the CLAUDE.md "Detailed Documentation" table.

---

## Dependencies + new attack surface

### NEW imports introduced by this cycle

- **AC12 (`kb/ingest/url_filter.py`)** — adds `import ipaddress` (stdlib, low risk) AND likely `import socket` for hostname resolution. If the implementer chooses to reuse `kb.lint.fetcher.SafeBackend` per T11 mitigation, no new transport surface; if they roll a fresh resolver, audit for DNS-rebind discipline.
- **AC9 (`kb/utils/path_safety.py`)** — NEW module. Stdlib-only (`os`, `pathlib`). Risk: the helper must not regress symlink-following behaviour vs. the three current call sites. Step 14 must verify the unification preserves the dual-anchor semantics of `_validate_path_under_project_root` (cycle 23) AND the existence/dir-type checks of `_validate_wiki_dir`.
- **AC18 (`tests/test_security_cve_greps.py`)** — NEW test module. Uses `subprocess` to invoke `grep` against `src/kb/**/*.py`. Must use `shell=False` per existing project discipline (cycle-21 plan-gate gap 8 / cli_backend.py line 198). Cross-platform: `grep` is unavailable on Windows by default — the test must either skipif-Windows OR use Python `re` (the latter preferred per platform parity).

### Modules touched with past security incidents

- **`mcp/app.py`** — touched extensively by cycles 4, 5, 17, 23 (path validation, page_id, run_id, dual-anchor). Cycle 23 L4 (same-class peer scan) is THE direct lesson for AC9/AC23. Cycle 4 #13 (Windows reserved basenames) overlaps with AC6/AC7.
- **`compile/compiler.py`** — touched by cycle 23 (rebuild_indexes dual-anchor), cycle 25 (in-progress markers + stale-marker warning), cycle 29 (extended dual-anchor to keyword-only overrides). AC10's TOCTOU fix sits directly on this surface.
- **`query/embeddings.py`** — touched by cycle 25 (dim mismatch), cycle 64 (auto-rebuild on dim-mismatch + AC8 concurrent-query idempotency, kill-switch `KB_DISABLE_VECTOR_AUTO_REBUILD`). Cycle-19 L2 reload-leak applies — env var MUST be read at call time. AC13/AC14 sit on this surface.
- **`utils/cli_backend.py`** — entire module is cycle 21 / 31 / 32 work (CLI subprocess hardening with T1-T8 threat-model entries baked into the docstrings, e.g. line 178 "T8: check model-override"). AC16 modifies T8's specific check. The cycle-21 T-numbering is INTERNAL to that file; cycle-65 T-numbering in this document is SEPARATE.
- **`mcp/core.py` / `mcp/ingest.py` / `mcp/quality.py`** — `quality.py` already calls `sanitize_error_text` at 14+ sites (cycle 18 AC13). `core.py` and `ingest.py` are the gap that AC21 closes. The Step 9 implementer should AUDIT all three files for the SAME pattern and replace `f"Error: {e}"` / `f"Error: {e!r}"` formatters with the `_mcp_error_boundary` wrapper.
- **`tests/conftest.py`** — autouse path sandbox introduced cycle 64 AC1. AC4 + AC5 harden it.

### Four known Dependabot CVEs — does cycle 65 change risk surface?

| CVE | Package | Cycle 65 impact |
|---|---|---|
| CVE-2025-69872 (diskcache pickle RCE) | `diskcache==5.6.3` | **Risk REDUCED.** AC15 (`TRAFILATURA_DOWNLOAD_NO_CACHE=1`) closes the trafilatura→diskcache transitive path. AC18 (CI grep test) ensures the "zero direct imports" rationale stays valid. |
| GHSA-xqmj-j6mv-4862 (litellm proxy template injection, high) | `litellm==1.83.0` | **Risk UNCHANGED.** Cycle 65 does not import litellm into `src/kb/`. AC18 is the new gate that catches a future direct import. |
| GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g (litellm critical + high) | `litellm==1.83.0` | **Risk UNCHANGED.** Same as above — AC18 enforces the unchanged rationale. |
| CVE-2026-6587 (ragas SSRF, GHSA-95ww-475f-pr4f) | `ragas==0.4.3` | **Risk UNCHANGED.** Dev-eval-only. AC18 enforces. AC12 closes the SSRF surface in OUR ingest path even if ragas is later imported by mistake. |

Net: risk REDUCED on diskcache and SSRF; risk UNCHANGED on litellm; no NEW CVEs introduced (AC11's GitPython pin TIGHTENS the surface).

---

## Out-of-scope threats

Per cycle-7 L4 (avoid scope confusion in Step 14), the following SAME-CLASS-PEER threats are explicitly NOT in scope for cycle 65 but live in the same threat surface — Step 14 must NOT verify these and must NOT flag their absence as a regression.

- **OOS-1: Filename-confusion in `raw/` ingestion path.** AC6/AC7 harden `_validate_page_id` for the `wiki/` boundary. The corresponding `raw/` sources are read from disk paths supplied by the user via `kb ingest <path>` — no MCP-boundary validator currently enforces trailing-dot/space rejection on `raw/articles/secret.md`. Out of scope: a parallel `_validate_raw_path` helper.
- **OOS-2: URL filtering in `evolve/` vs `ingest/`.** AC12 ships `kb.ingest.url_filter._is_safe_url`. The `evolve/` analyzer also processes URLs (citation-graph, source verification). Migrating evolve's URL handling to the new helper is OUT OF SCOPE — defer to cycle-66+ once the helper is battle-tested.
- **OOS-3: MCP error-boundary on `browse.py` and `compile.py`.** AC21 hardens `mcp/core.py` + `mcp/ingest.py` + `mcp/quality.py`. `mcp/browse.py` already uses `sanitize_error_text` at 3 sites (read 17, 83, 140, 221) per pre-cycle audit. `mcp/compile.py` and `mcp/health.py` are NOT in the AC21 list — out of scope this cycle. Step 14 must NOT flag their absence.
- **OOS-4: `_validate_wiki_dir` parity with the new `_validate_page_id` rules.** AC9 unifies the containment check, but AC6/AC7's trailing-dot/space and Windows-illegal-char rules apply to PAGE IDs only — not to absolute `wiki_dir` paths supplied by callers (which go through OS-level path normalization). Out of scope: extending the char rules upstream.
- **OOS-5: Multi-process race on `compile_wiki` itself.** AC13 closes the `VectorIndex.build` multi-process race. The broader `compile_wiki` orchestration also has multi-write fan-out (cycle 35 partial-fix; Phase 4.5 R5 still open per BACKLOG). Out of scope: receipt-file design, cross-source reconciliation.
- **OOS-6: TOCTOU on `ingest_source` writes.** AC10 closes TOCTOU on `compile/compiler.py::rebuild_indexes` unlink. The pipeline.py write paths (stages 1-11 of `ingest_source`) have their own TOCTOU exposure (cycle 35 lock acquisition order). Out of scope: per-page write-lock helper or wiki-wide ingest mutex.
- **OOS-7: GitPython runtime hardening beyond pinning.** AC11 pins the version. Out of scope: switching from GitPython to `subprocess.run(["git", ...])` to eliminate the dep entirely (large architectural change).
- **OOS-8: Snapshot subjects beyond cycle 64's three.** AC19 hardens the existing 3 snapshot subjects (evidence-trail, Mermaid export, lint-report-structure). Phase 4.5 R3's deferred subjects (`_build_summary_content` page rendering, `kb publish --format graph` JSON-LD output, `auto_publish_after_compile`'s `_publish/llms-full.txt`) are out of scope.
- **OOS-9: `kb_publish` MCP error-boundary parity.** `kb publish` is a CLI surface (`cli.py`) — AC21 covers MCP tools only. Out of scope: extending error-boundary discipline to CLI subcommands.
- **OOS-10: Secret-shape detection elsewhere.** AC16 fixes `_check_no_secrets_on_argv`. The same regex is NOT used in any other call site (verified via grep) but a future audit could find similar over-zealous patterns. Out of scope: a project-wide secret-regex audit.
