# Cycle 67 Threat Model

**STRIDE coverage:** S(poofing) · T(ampering) · R(epudiation) · I(nformation Disclosure) · D(enial of Service) · E(levation of Privilege)

**Authored by:** Opus 4.7 main session as fallback per cycle-20 L4 (Step 2 subagent exceeded 10-min hang threshold; CVE baseline completed at `.data/cycle-67/pip-audit-baseline.json` but threat-model.md not produced before time budget elapsed).

**Predecessors:** `2026-05-07-cycle-67-requirements.md` (15 ACs, Tier 2), `2026-05-07-cycle-67-brainstorm.md`, R1 + R2 design evals.

## Trust boundaries in scope

| AC | Trust boundary | Boundary description |
|----|----------------|----------------------|
| AC01 | Process-internal | `MODEL_TIERS` legacy dict surface; env-var read-time consistency |
| AC02 | Test/source contract | `kb.graph.cache.get_graph` import form discipline |
| AC03 | Subprocess output | CLI backend stdout/stderr → main process memory bound |
| AC04 | Compile pipeline | `auto_publish_after_compile` exception propagation contract |
| AC05 | MCP error response | sqlite_vec extension load error → MCP client |
| AC06 | Query path | Hybrid search runtime kill-switch (operator-controlled) |
| AC07 | Wiki config file | `wiki/_lint.yml` operator-controlled allowlist override |
| AC08 | Test fixture invariant | `_autouse_kb_path_sandbox` autouse decorator preservation |
| AC09 | Snapshot capture vs runtime | Paired negative-control distinguishes data vs renderer |
| AC10 | CI workflow | `--snapshot-update` flag rejection in workflow steps |
| AC11 | CI artifact | `sk-ant-dummy` dummy-key not leaked into tracked files |
| AC12 | API surface doc contract | `kb.__all__` Args/Returns/Raises section coverage |
| AC13 | User onboarding | `KB_PROJECT_ROOT` bootstrap for non-clone install |
| AC14 | Doc index integrity | `docs/reference/INDEX.md` ↔ `CLAUDE.md` ↔ filesystem consistency |
| AC15 | Subprocess argv | `_check_no_secrets_on_argv` substring scan correctness |

## Threats

### T1 (I) — sqlite_vec.load() error message leaks .so/.dll absolute filesystem path via MCP error response

**AFFECTED:** AC05.
**Mitigation:** catch `sqlite3.OperationalError` at both call sites (embeddings.py:584, 665), re-raise as `RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel") from exc`.
**Residual:** traceback `from exc` chain still has the path in local logs (acceptable — local-only, not surfaced to MCP client).
**Cycle lessons:** cycle-23 L2 (return type preservation), cycle-21 L (information disclosure class).
**R2-F10 follow-up:** Step 9 must include `test_sqlite_vec_load_error_mcp_response_sanitized` that proves the MCP error boundary `_mcp_error_boundary` does NOT log `__cause__.repr()` somewhere that leaks the path back into the response.

### T2 (D) — Misbehaving CLI backend produces gigabytes of stdout, OOMing Python process before subprocess.run() truncation slice

**AFFECTED:** AC03.
**Mitigation:** chunked Popen reader with terminate at `MAX_CLI_STDOUT_BYTES`.
**Residual:** 64KB chunk + small overrun before terminate lands; bounded by chunk size, not by full output. `MAX_CLI_STDERR_BYTES = 64 KB` symmetric cap on stderr.
**Cycle lessons:** cycle-21 plan-gate gap-8 (accepted-risk acknowledgement to be removed in this cycle).
**R1-F1, R2-F6 follow-up:** Step 9 stdin-write-during-stdout-overflow test MUST not deadlock. Use `proc.stdin.write/close` separately, NOT `proc.communicate(input=...)` with daemon readers.
**R1-F2, R2-F7 follow-up:** Windows path uses `terminate(); wait(0.5)` (TerminateProcess is not soft-kill); POSIX path uses `terminate(); wait(2); kill()` for SIGTERM grace.

### T3 (E) — Operator-supplied `wiki/_lint.yml` triggers RCE via PyYAML `unsafe_load` tag injection

**AFFECTED:** AC07.
**Mitigation:** `yaml.safe_load` only — never `yaml.load` or `yaml.unsafe_load`. Pin a test asserting that a YAML payload containing `!!python/object/new:os.system [["echo pwn"]]` is REJECTED by the loader.
**Residual:** YAML parser bugs in PyYAML itself (CVE class) — track via pip-audit at Step 12.
**Cycle lessons:** cycle-3 L (homoglyph defense scoping), cycle-22 L1 (pip-audit baseline gotchas).
**R2-F11 follow-up:** Step 9 `test_lint_yaml_rejects_malicious_payload` is REQUIRED.

### T4 (T) — Maintainer-pushed `--snapshot-update` flag in CI silently invalidates AC09 paired negative-control

**AFFECTED:** AC09 + AC10.
**Mitigation:** AC10 CI grep step rejects `--snapshot-update` in any workflow file before pytest runs. Commit order swapped to AC10 → AC11 → AC09 (R1-F10) so the gate is ON before AC09 ships.
**Residual:** local snapshot regen still possible (intentional — snapshots are meant to be regenerated locally and committed).
**Cycle lessons:** cycle-15 L1 (grep gate as first line of defense).

### T5 (I) — `sk-ant-dummy` dummy API key leaks into VCR/cassette/snapshot artifacts

**AFFECTED:** AC11.
**Mitigation:** CI grep step that fails if `sk-ant-dummy` (full literal value, dynamically extracted from ci.yml) appears in any tracked file outside `.github/workflows/ci.yml`. R1-F8 + R2-F15 noted false-positive risk on legitimate doc references in BACKLOG.md / CHANGELOG.md / docs/superpowers/decisions/ (10+ matches today).
**Residual:** the dummy value itself is not a real secret — CVE class is "future-test author misconfigures mock layer + records cassette". Pre-MVP threat.
**Cycle lessons:** Step 9 must run a one-time prep PR that either (a) tightens the literal to the FULL `sk-ant-dummy-key-for-ci-tests-only` string AND adds an exclusion list for legitimate doc files, OR (b) accepts the false-positives as a manual-review gate (commit-time only, not CI-blocking).

### T6 (T) — Test fixture decorator silently flipped to `autouse=False` cascades to ~200 tests writing real `wiki/`/`raw/` dirs

**AFFECTED:** AC08.
**Mitigation:** AST-walk meta-test in `tests/test_cycle67_conftest_invariants.py` asserts decorator list contains `pytest.fixture(autouse=True)` for `_autouse_kb_path_sandbox`.
**Residual:** test could be deleted in same commit as the decorator flip — but PR review (Step 20) catches that.
**Cycle lessons:** cycle-23 L2 (regression-revert guards).

### T7 (T) — Future caller adds `from kb.graph.cache import get_graph` and silently bypasses test spies

**AFFECTED:** AC02.
**Mitigation:** AST-walk test rejects `ImportFrom(module="kb.graph.cache", names=[alias(name="get_graph")])` in `src/kb/`. Aliased forms (`import kb.graph.cache as gc`) are FINE per cycle-18 L1 — they hit the patched module attribute.
**Residual:** none — explicit import-form discipline.
**Cycle lessons:** cycle-18 L1 snapshot-binding hazard.
**R1-F9 follow-up:** add a positive test for aliased form to confirm it's NOT a finding.

### T8 (E) — `MODEL_TIERS` proxy fails `dict()` conversion or `.keys()/.values()/.items()` access used by serializers

**AFFECTED:** AC01.
**Mitigation:** `_ModelTiersView` implements `__iter__`, `__len__`, `__contains__`, `__getitem__`. `dict(view)` should work via the `__iter__` + `__getitem__` protocol.
**Residual:** strict `isinstance(view, dict)` callers fail — but grep confirmed there are none today.
**Cycle lessons:** cycle-21 L (multi-stage fallback class — keep semantic-failure exceptions distinct from format-mismatch).
**R2-F1, R2-F2 follow-up:** Step 9 tests `test_model_tiers_dict_conversion_not_allowed` (or works-as-expected) and `test_model_tiers_dict_methods_guard` are REQUIRED. Decision: implement `.keys/.values/.items` via `collections.abc.Mapping` mixin so all three work AND read env-dynamic.

### T9 (T) — `KB_STRICT_PUBLISH` env var truthiness inconsistency with sibling `KB_DISABLE_VECTORS`

**AFFECTED:** AC04 + AC06.
**Mitigation:** both ACs use IDENTICAL truthiness check: `os.environ.get(KEY, '').strip().lower() in ('1', 'true', 'yes')`. R1-F3 condition C3.
**Residual:** none — symmetric convention.
**Cycle lessons:** cycle-19 L2 reload-leak rule (call-time read).

### T10 (R) — `auto_publish_after_compile` swallowed exception masks publish failure in CI / release pipeline

**AFFECTED:** AC04.
**Mitigation:** `KB_STRICT_PUBLISH=1` re-raises so CI step fails loudly. Default-off preserves back-compat.
**Residual:** operators who don't set the env var still see swallowed failures (intentional default).
**Cycle lessons:** cycle-3 PR #15 R1 Codex MAJOR (observability flags must reflect runtime, not config).

### T11 (D) — Hybrid search vector branch consumes resources operator wants disabled per-environment

**AFFECTED:** AC06.
**Mitigation:** `KB_DISABLE_VECTORS=1` (call-time read) skips vector branch.
**Residual:** vector model warm-load at import time may still cost — but this is bounded.
**Cycle lessons:** cycle-19 L2 (call-time env read).

### T12 (S) — `pip install kb` user without clone resolves data paths into venv `site-packages`

**AFFECTED:** AC13.
**Mitigation:** README "Non-clone install" section makes `KB_PROJECT_ROOT` bootstrap explicit.
**Residual:** docs-only — operator must read README.
**Cycle lessons:** cycle-12 L (boot-lean contract).

### T13 (T) — Docstring drift: `kb.__all__` API loses Args/Returns sections during refactor; library users see incomplete docs

**AFFECTED:** AC12.
**Mitigation:** `scripts/audit_docstrings.py` walks `kb.__all__`; CI runs it on push.
**Residual:** false-negative on indented section headers (regex `^\s*Args:` accepts any leading whitespace, sufficient for Google style which is the project convention).
**Cycle lessons:** cycle-10 L (when extracting helper, preserve full operation sequence).
**R2-F16 follow-up:** Step 9 `test_audit_docstrings_generator_with_raise_requires_raises_section` — for generator functions that `yield` and may `raise` from a downstream caller, `Raises:` is required. Use `ast.walk` to detect `raise` statements outside `try` blocks.

### T14 (T) — `docs/reference/` filesystem ↔ INDEX.md ↔ CLAUDE.md table drift

**AFFECTED:** AC14.
**Mitigation:** `scripts/check_docs_index.py` cross-references all three sources, fails CI on mismatch.
**Residual:** reference-style markdown links (`[label][ref]` + `[ref]: docs/reference/file.md`) NOT detected by inline-link regex. Acceptable per project convention (CLAUDE.md uses inline-link style only).
**R2-F18 follow-up:** Step 9 `test_docs_index_consistency_multilink_per_line` — handle multiple inline links on one line correctly.

### T15 (S) — `_check_no_secrets_on_argv` regression: future maintainer "simplifies" substring scan to regex-on-argv, re-introducing false-positive class

**AFFECTED:** AC15.
**Mitigation:** explicit test cases T15-A, T15-B, T15-C lock the design intent. Backstops against the mimo r4 A finding's incorrect "self-DoS via generic regex" framing.
**Residual:** test could be deleted in a refactor commit — but PR review catches it.
**Cycle lessons:** cycle-15 L (grep-then-fix, not fix-then-test).

## Out-of-scope (verified mitigated in prior cycles)

Per requirements doc's "Out-of-scope" list — echoed here for Step 14 completeness:

- SSRF on URL → external CLI argv (mimo r4 B): VERIFIED STALE — `lint/fetcher.py` has DNS-resolve + IP-allowlist + scheme-allowlist + per-hop redirect validation. crawl4ai/yt-dlp not imported in src/kb/.
- `KB_PROJECT_ROOT` call-time accessor (mimo r5 Q1): SHIPPED cycle 65 AC1.
- `AUGMENT_ALLOWED_DOMAINS` call-time accessor (mimo r5 Q5): SHIPPED cycle 65 AC3.
- MCP error boundary (mimo r4 E): SHIPPED cycle 65 AC21 across `mcp/{core,ingest,quality}.py`.
- `_validate_page_id` Windows trailing dot/space (Phase 6 cycle-64 HIGH): SHIPPED cycle 65 AC6.
- `_validate_page_id` `:` Windows-illegal-char: SHIPPED cycle 65 (`_WINDOWS_ILLEGAL_CHARS_RE`).
- TOCTOU `rebuild_indexes` (Phase 6 cycle-64 MEDIUM): SHIPPED cycle 65 AC10 (`_open_no_follow`).
- Validator-contract drift: SHIPPED cycle 65 AC9 (`_assert_under_project_root`).
- `query/embeddings.py` multi-process race: SHIPPED via `file_lock(target_path.with_suffix(".db.lock"))`.
- conftest auto-discovery for lru_cache: SHIPPED cycle 17 AC16.
- `lint/fetcher.py` `TRAFILATURA_DOWNLOAD_NO_CACHE=1`: SHIPPED.
- `requirements.txt` GitPython upper bound: SHIPPED as `>=3.1.47,<3.2`.
- `docs/reference/INDEX.md` existence: SHIPPED.

## Dep-CVE baseline (Step 2 snapshot at `.data/cycle-67/pip-audit-baseline.json`)

3 NEW patchable + 1 known-unfixed. Step 15 (Existing-CVE opportunistic patch) addresses the patchable ones in this cycle.

| Package | Version | CVE | Severity (assumed) | Fix version | Cycle 67 plan |
|---------|---------|-----|--------------------|-------------|--------|
| gitpython | 3.1.47 | CVE-2026-44244 (GHSA-v87r-6q3f-2j67) | HIGH (RCE-class via newline-injected core.hooksPath) | 3.1.49 | Step 15 patch |
| mako | 1.3.11 | CVE-2026-44307 (GHSA-2h4p-vjrc-8xpq) | MEDIUM (Windows-only path traversal in template lookup) | 1.3.12 | Step 15 patch |
| python-multipart | 0.0.26 | CVE-2026-42561 (GHSA-pp6c-gr5w-3c5g) | MEDIUM (DoS via header parser in form-data) | 0.0.27 | Step 15 patch |
| diskcache | 5.6.3 | CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v) | MEDIUM (pickle deserialization RCE) | (none) | Track upstream; mitigated via cycle 65 (TRAFILATURA_DOWNLOAD_NO_CACHE=1) |
| pip | 26.1.1 | (none — patched since previous baseline) | — | — | No action |

**Delta vs cycle 66 baseline:** mako and python-multipart are NEW advisories landed since 2026-05-05 (cycle 66 cutoff). gitpython advisory is NEW (cycle 66 patched 3.1.46 → 3.1.47 fixing earlier CVEs; new CVE-2026-44244 affects current 3.1.47 too). diskcache CVE unchanged.

**Step 15 scope:**
- Bump `requirements.txt`: `GitPython>=3.1.47,<3.2` → `GitPython>=3.1.49,<3.2`.
- If `mako` is a direct dep: bump to 1.3.12. If transitive: identify owner package; defer to upstream pin OR override.
- If `python-multipart` is a direct dep: bump to 0.0.27. Same transitive-vs-direct check.
- After bumps: `pip install -U -r requirements.txt`, re-run pytest, commit `fix(deps): patch CVE-2026-44244 + CVE-2026-44307 + CVE-2026-42561`.
- Verify Step 12 baseline test count (3176+) still passes.

## Step 14 verifier checklist

For each AC, Step 14 security-verify subagent must check:

| Check | AC | Command / assertion |
|-------|-----|---------------------|
| AC01 proxy reads env at lookup time | AC01 | grep `os.environ` inside `_ModelTiersView.__getitem__` body OR delegation chain to `get_model_tier()` |
| AC01 dict-protocol methods (.keys/.values/.items) reach env | AC01 | spy `os.environ.get` calls during `MODEL_TIERS.keys()` lookup; expect 1+ calls |
| AC02 src/kb has zero `from kb.graph.cache import get_graph` | AC02 | `python tests/test_cycle67_graph_cache_callsite_form.py` exits 0 |
| AC03 stdin-write-during-stdout-overflow does NOT deadlock | AC03 | T03-large-stdin test passes within timeout |
| AC03 stderr-only volume capped at MAX_CLI_STDERR_BYTES | AC03 | T03-stderr test asserts len(stderr) ≤ cap |
| AC03 Windows kill-grace branch | AC03 | sys.platform branch logged with platform name; Windows test or skipif on POSIX |
| AC04 KB_STRICT_PUBLISH truthy variants | AC04 | T04-C tests `1`, `true`, `yes`, `TRUE`, `YES` all enable strict |
| AC04 default behavior unchanged when env unset | AC04 | T04-A passes (publish error swallowed) |
| AC05 sqlite_vec error message contains no path | AC05 | `assert "AppData" not in str(exc); assert "/usr/local" not in str(exc)` |
| AC05 both call sites covered | AC05 | T05 hits both line 584 and line 665 paths |
| AC06 KB_DISABLE_VECTORS skips vector dispatch | AC06 | spy on `VectorIndex.query` shows 0 calls when env=1 |
| AC07 yaml.safe_load enforced | AC07 | T07-malicious YAML payload REJECTED; never `yaml.load` |
| AC07 file-not-found falls through to defaults | AC07 | T07-A passes |
| AC07 malformed YAML emits warning + falls through | AC07 | T07-C passes |
| AC08 conftest decorator AST-asserted | AC08 | T08-A passes; T08-B (mutated tmp copy) FAILS |
| AC09 paired negative-control per snapshot | AC09 | each snapshot has T*A AND T*B |
| AC10 CI rejects --snapshot-update | AC10 | CI grep step exits 1 if flag found |
| AC11 sk-ant-dummy not in tracked files (excluding ci.yml + allowlist) | AC11 | CI grep step exits 0 |
| AC12 audit script run mode | AC12 | warn-only or hard-fail per Step-7 plan first-task decision |
| AC13 README has "Non-clone install" section | AC13 | grep README.md for the section heading |
| AC14 docs index consistency clean | AC14 | CI script exits 0 |
| AC15 substring scan tests | AC15 | T15-A, T15-B, T15-C all pass |

## Verifier hand-off note

Step 14 subagent should compare this checklist against the actual Step 9 test files. Per cycle-21 L (Step 14 catches real gaps even after thorough design gate), do not skim — read the actual diff and confirm the test reaches the production call site.

Step 11 (SAST + secrets scan) consumes this threat model AS its target list — Bandit / Semgrep should not flag any of the in-scope mitigations.
