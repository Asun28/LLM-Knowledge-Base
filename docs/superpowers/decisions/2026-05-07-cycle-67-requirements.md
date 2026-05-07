# Cycle 67 — Requirements + Acceptance Criteria

**Date:** 2026-05-07
**Branch:** `worktree-feat+cycle-67` (worktree at `.claude/worktrees/feat+cycle-67`)
**Pipeline:** dev-mimo-opus (project trial)
**Predecessor:** cycle 66 (commit `162cbf0`, squash-merged)
**Baseline tests:** 3176 passed, 23 skipped (169.18s on Windows local, parent .venv via worktree pythonpath redirect)

## Tier

**Tier 2 — standard feature batch (multi-AC mimo-audit residual + Phase 4.5 cleanup).**

15 ACs spanning config accessor cleanup, test invariants, CI hygiene, and library hardening. No auth / IAM / crypto / data / migration changes. The most invasive AC (AC03 — chunked stdout cap with SIGTERM) replaces `subprocess.run` with `Popen` but preserves the same trust boundary (CLI subprocess output capping for memory bounds). All other ACs are additive or signature-preserving.

Tier-aware strict-audit denominator: 9 binding-owner steps in Tier 2 subset (steps 2, 4-R2, 7, 8, 9-bg-review, 14, 17, 18, 20-R1, 20-R2). Tracked in Step 24 scorecard per C59-L4.

## R3 trigger (cycle-17 L4)

**RECOMMENDED.** Cycle hits 15 ACs (R3 triggers at ≥25 OR at ≥15 with risk profile match). Risk profile match:
- (a) New filesystem-write surface — AC07 (`wiki/_lint.yml` allowlist file load)
- (b) Defensive check whose input is hard to reach — AC03 (`SIGTERM` at `MAX_CLI_STDOUT_BYTES`), AC05 (sqlite_vec error path)
- (c) New security enforcement point — AC11 (dummy-key grep), AC12 (docstring CI gate)
- (d) ≥10 design questions resolved at Step 5 — TBD; if hits threshold, R3 firmly required

Step 20 schedules R3 (Sonnet edge-case role) regardless; document trigger in PR body.

## Threat / risk surface (Step 2 will formalize)

Out-of-scope: SSRF on URL → external CLI argv (mimo r4 B). VERIFIED STALE — `lint/fetcher.py` (lines 100-149, 242, 366-421) already has DNS-resolve + `is_private`/`is_loopback`/`is_link_local`/`is_reserved`/`is_multicast`/`is_unspecified` IP filtering, scheme allowlist `{"http","https"}`, and per-hop redirect validation. `crawl4ai`/`yt-dlp` are not imported anywhere in `src/kb/`. `ingest_source(source_path: Path, ...)` (pipeline.py:1132) takes `Path`, not URL. Closing as "verified-resolved-in-prior-cycle"; will add a BACKLOG one-liner under "Resolved Phases" via Step 17 doc update.

In-scope security boundary: AC05 (sqlite_vec error sanitization), AC11 (CI grep for `sk-ant-dummy`), AC12 (docstring audit gate). Boundary-preserving.

## Acceptance criteria (15)

Grouped by file per `feedback_batch_by_file` memory.

### File: `src/kb/config.py`

**AC01 — `MODEL_TIERS` legacy import-time-captured dict → call-time view (mimo r5 Q1+Q2 — actual surface, not the misnamed `_DEFAULT_MODEL_TIERS`).**

Current state (verified at config.py:237-241):
```python
MODEL_TIERS = {
    "scan": os.environ.get("CLAUDE_SCAN_MODEL", "").strip() or "claude-haiku-4-5-20251001",
    "write": os.environ.get("CLAUDE_WRITE_MODEL", "").strip() or "claude-sonnet-4-6",
    "orchestrate": os.environ.get("CLAUDE_ORCHESTRATE_MODEL", "").strip() or "claude-opus-4-6",
}
```
Reads env at import time. Tests using `MODEL_TIERS["scan"]` directly (test_llm.py:215-217, test_v0912_phase393.py:423, test_v099_phase39.py) get stale values when env mutates after `kb.config` is loaded — same hazard class as cycle-19 L2 reload-leak.

Production fix: introduce `class _ModelTiersView` with `__getitem__` that delegates to `get_model_tier(tier)`. Replace module-level `MODEL_TIERS = {...}` with `MODEL_TIERS = _ModelTiersView()`. Existing callers (`d["scan"]`, `MODEL_TIERS["orchestrate"]`) keep working but read env at LOOKUP time. Note: dict-like view, not full dict — iteration support optional, only `__getitem__` mandatory.

Test: T01-A (positive) `monkeypatch.setenv("CLAUDE_SCAN_MODEL", "x"); kb.config.MODEL_TIERS["scan"] == "x"`; T01-B (divergent-fail) revert the proxy to a literal dict — ensure T01-A then fails. T01-C: `_ModelTiersView()["unknown"]` raises ValueError matching `get_model_tier`'s contract.

Note: existing `tests/test_config_no_direct_model_tiers.py` already grep-guards against `MODEL_TIERS[` access in `src/kb/`. AC01 does NOT remove that test — the bracket-access guard remains valuable as a "prefer get_model_tier()" hint, even though the proxy now makes bracket access env-dynamic.

### File: `src/kb/graph/cache.py`

**AC02 — AST-grep test for 6th-caller drift (mimo r1 Q4).**

Current state (verified): `__all__ = []` at cache.py:57, comment block at 122-152 documents attribute-lookup form per cycle-18 L1.

Add `tests/test_cycle67_graph_cache_callsite_form.py`:
```python
def test_no_from_kb_graph_cache_import_get_graph_in_src() -> None:
    """6th-caller drift guard. cycle-18 L1: monkeypatch hooks for tests
    require attribute-lookup form (`kb.graph.cache.get_graph(...)`).
    A new caller doing `from kb.graph.cache import get_graph` would silently
    bypass test spies set via `monkeypatch.setattr(kb.graph.cache, "get_graph", ...)`."""
    src_dir = Path(__file__).resolve().parents[1] / "src" / "kb"
    offenders: list[str] = []
    for path in src_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "kb.graph.cache":
                for alias in node.names:
                    if alias.name == "get_graph":
                        offenders.append(f"{path}:{node.lineno}")
    assert not offenders, ...
```
Test: T02-A (negative-control fixture) — temporarily inject a `from kb.graph.cache import get_graph` into a tmp `.py` file under `tmp_path`, point the walker at it, assert it FAILS. Then point at real `src/kb/`, assert it PASSES. Closes vacuous-test class.

### File: `src/kb/utils/cli_backend.py`

**AC03 — Chunked stdout cap with `SIGTERM`/`kill()` at limit (Phase 6 R2 MEDIUM, cli_backend.py:241).**

Current state (verified at cli_backend.py:213-247): `subprocess.run(capture_output=True)` buffers entire stdout in memory before `result.stdout[:MAX_CLI_STDOUT_BYTES]` slice. Comment at lines 242-244 acknowledges as accepted risk per cycle-21 plan-gate gap 8.

Production fix: replace `subprocess.run` body with `Popen(stdout=PIPE, stderr=PIPE)` + a reader thread accumulating stdout in 64KB chunks until `MAX_CLI_STDOUT_BYTES` is reached, then `proc.terminate()` (POSIX) / `proc.kill()` (Windows). stderr captured in parallel reader thread. Final `proc.wait(timeout=...)` for exit code. Preserve existing `LLMError(kind="timeout")` and `kind="not_installed"` paths.

Test:
- T03-A (positive) — backend that writes `b"A" * (MAX_CLI_STDOUT_BYTES * 3)` to stdout: assert returned stdout length == cap, assert subprocess was terminated, assert <2× cap memory usage via `tracemalloc` snapshot before/after
- T03-B (divergent-fail) — revert to `subprocess.run`: T03-A asserts on memory usage fail (≥3× cap)
- T03-C (back-compat) — existing test_cli_backend tests should still pass under chunked path; small backend output (< cap) returns intact

Test isolation via fake-CLI shell script. Use `python -c "import sys; sys.stdout.buffer.write(b'A' * N)"` for cross-platform fakes.

### File: `src/kb/compile/compiler.py`

**AC04 — `KB_STRICT_PUBLISH=1` env var to re-raise `auto_publish_after_compile` exceptions (Phase 4.5 MEDIUM).**

Current state (verified at compiler.py:611-614): publish exceptions caught + suppressed. `compile_wiki` reports success when publish failed.

Production fix: at `auto_publish_after_compile` call site, read `os.environ.get("KB_STRICT_PUBLISH", "").strip()` at CALL time (cycle-19 L2 reload-leak rule). If set to `"1"` or truthy non-empty, re-raise instead of swallow. Default behavior (env unset) unchanged. Document in `kb compile --help` text and in `docs/reference/workflows.md`.

Test:
- T04-A (default) — patch publish to raise, env unset, `compile_wiki` succeeds
- T04-B (strict) — patch publish to raise, env=`"1"`, `compile_wiki` re-raises
- T04-C (call-time) — set env BEFORE first call, succeed; mid-test set env, second call re-raises (proves not module-import-captured)

### File: `src/kb/query/embeddings.py`

**AC05 — Sanitize `sqlite_vec.load(conn)` `OperationalError` to drop .so/.dll absolute path leak (Phase 6 cross-LLM cycle-64 LOW).**

Current state (verified at embeddings.py:584, 665): `sqlite_vec.load(conn)` raises `sqlite3.OperationalError` whose message includes absolute filesystem path of the loadable extension. Path can leak via MCP error responses (T3 information-disclosure class).

Production fix: at both call sites, wrap in `try/except sqlite3.OperationalError as exc` → `raise RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel") from exc`. Use `from exc` to preserve traceback in local logs but server response only sees the sanitized message.

Test:
- T05-A — monkeypatch `sqlite_vec.load` to raise `sqlite3.OperationalError("error loading C:\\Users\\Admin\\AppData\\foo.dll")`; call `VectorIndex.build()` and `VectorIndex._connect()`; assert raised `RuntimeError` message matches the sanitized literal AND assert `"AppData"` not in message
- T05-B (divergent-fail) — revert sanitization, T05-A then leaks the path (assert fails)

### File: `src/kb/query/hybrid.py` (or whichever module owns hybrid dispatch — confirmed at Step 7) + `src/kb/config.py`

**AC06 — `KB_DISABLE_VECTORS=1` runtime kill-switch for hybrid search (Phase 4.5 MEDIUM).**

Current state: hybrid search is opt-in via `[hybrid]` extra (cycle 34 AC19). No runtime env toggle.

Production fix: in the hybrid-dispatch entry, read `os.environ.get("KB_DISABLE_VECTORS", "").strip().lower() in ("1", "true", "yes")` at CALL time. When true, skip vector branch and fall back to BM25-only. Document in `CLAUDE.md` Quick Reference + `docs/reference/workflows.md` Query section.

Test:
- T06-A (default) — env unset, hybrid call returns vector-augmented results (assert non-empty vector contribution in scores)
- T06-B (kill-switch) — env=`"1"`, hybrid call returns BM25-only results, no `VectorIndex.query` call (assert via spy that `VectorIndex.query` was NOT invoked)
- T06-C (call-time) — flip env mid-test, prove behavior switches without process restart

### File: `src/kb/lint/checks/duplicate_slug.py` + `src/kb/config.py` + (new) `src/kb/lint/_lint_yaml.py`

**AC07 — Duplicate-slug allowlist externalization to `wiki/_lint.yml` (Phase 4.5 MEDIUM).**

Current state (verified at lint/checks/duplicate_slug.py:5): imports `DUPLICATE_SLUG_ALLOWLIST` from `kb.config`. Allowlist hardcoded in source. Adding entries requires code edit + commit.

Production fix:
1. Introduce `kb.lint._lint_yaml.load_lint_config(wiki_dir)` — lazy reader for `wiki_dir / "_lint.yml"` (returns `{}` if file missing). YAML schema: top-level `duplicate_slug_allowlist: [["a", "b"], ...]`.
2. `check_duplicate_slugs` calls `load_lint_config(wiki_dir).get("duplicate_slug_allowlist", DUPLICATE_SLUG_ALLOWLIST)` so file overrides config defaults. File missing or YAML key absent → fall through to `DUPLICATE_SLUG_ALLOWLIST` from config (back-compat).
3. Document in `docs/reference/workflows.md` (Deep Lint section) and add fallback-order paragraph.

Test:
- T07-A — `_lint.yml` absent → uses config defaults (existing pairs `concepts/bot` vs `concepts/llm` etc.)
- T07-B — `_lint.yml` with explicit allowlist → uses YAML, ignores config defaults
- T07-C — `_lint.yml` malformed YAML → emits warning + falls through to config defaults (no crash)
- T07-D — call-time read: edit `_lint.yml` between two `check_duplicate_slugs` calls in same process; second call sees the new allowlist

### File: `tests/conftest.py` + (new) `tests/test_cycle67_conftest_invariants.py`

**AC08 — Meta-test for `_autouse_kb_path_sandbox` autouse decorator preservation (mimo r2 Q1).**

Current state (verified at tests/conftest.py:352-353): `@pytest.fixture(autouse=True)` decorator on `_autouse_kb_path_sandbox`. If a future refactor flips to `autouse=False` or removes the decorator entirely, the sandbox silently breaks and 200+ tests start writing to real `wiki/`/`raw/` dirs.

Add `tests/test_cycle67_conftest_invariants.py`:
```python
def test_autouse_kb_path_sandbox_decorator_intact() -> None:
    conftest = ast.parse((Path(__file__).resolve().parent / "conftest.py").read_text())
    fdef = next(n for n in ast.walk(conftest)
                if isinstance(n, ast.FunctionDef) and n.name == "_autouse_kb_path_sandbox")
    found = False
    for dec in fdef.decorator_list:
        if isinstance(dec, ast.Call) and any(
            kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in dec.keywords
        ):
            found = True
            break
    assert found, "_autouse_kb_path_sandbox MUST keep autouse=True; sandbox cascades to ~200 tests"
```

Test: T08-A passes against current conftest. T08-B (divergent-fail): mutate conftest in `tmp_path` copy with `autouse=False`, run AST walker → assert FAILS.

### File: `tests/test_cycle64_snapshots.py`

**AC09 — Per-snapshot paired negative-control test (mimo r2 Q4).**

Current state: cycle-64 snapshots captured FROM the same code path under test. No paired test mutating one input field that should diverge the snapshot.

Production fix: for each existing snapshot subject (evidence-trail / Mermaid export / lint-report-structure), add a paired test:
- T09-A (mutated input) — Mutate one field of the input dict (e.g., for evidence-trail change `source_ref` from `"raw/x.md"` to `"raw/x.md#mutated"`); assert the rendered output does NOT match the stored snapshot. Test must NOT update the snapshot.
- T09-B (regression-revert guard) — Trivially mutate the rendering function (e.g., add `+ "X"` to output); assert snapshot does NOT match. Reverts when production reverts.

Both must pass under default `pytest`. Neither may pass `--snapshot-update` (defensive).

### File: `.github/workflows/ci.yml`

**AC10 — Reject `--snapshot-update` flag in CI (Phase 6 R2 LOW, paired with AC09).**

Current state: CI invokes `pytest` directly. If a maintainer adds `--snapshot-update` to a workflow step, snapshot tests pass trivially.

Production fix: add a CI step BEFORE pytest that grep-fails on `--snapshot-update`:
```yaml
- name: Reject --snapshot-update in workflow
  run: |
    if grep -rn "\-\-snapshot-update" .github/workflows/; then
      echo "ERROR: --snapshot-update found in workflows; snapshots must be regenerated locally and committed."
      exit 1
    fi
```

Test: workflow itself is the test; PR diff inspection at Step 20.

**AC11 — CI grep step rejecting `sk-ant-dummy` outside ci.yml (mimo r5 Q7).**

Current state: CI sets `ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only` for tests that mock at the SDK boundary. If a test mocks at httpx layer + records a cassette/snapshot/VCR, the dummy key leaks into a tracked artifact.

Production fix: add a CI step that fails if `sk-ant-dummy` appears in any tracked file except `.github/workflows/ci.yml`:
```yaml
- name: No dummy API key in tracked files
  run: |
    matches=$(git ls-files | xargs grep -l "sk-ant-dummy" 2>/dev/null | grep -v "^\.github/workflows/ci\.yml$" || true)
    if [ -n "$matches" ]; then
      echo "ERROR: sk-ant-dummy leaked into tracked files: $matches"
      exit 1
    fi
```

Test: the CI step is the test. Step 11 SAST grep verifies the file shows in workflow at Step 17 doc-update sanity check.

### File: (new) `scripts/audit_docstrings.py` + `.github/workflows/ci.yml`

**AC12 — Docstring audit script for `kb.__all__` API surface (mimo r3 Q7).**

Current state: `kb/__init__.py` is a 67-line lazy `__getattr__` shim. Real Args/Returns/Raises sections must live on the underlying functions in `kb/ingest/pipeline.py`, `kb/compile/__init__.py`, `kb/query/__init__.py`, `kb/graph/__init__.py`. Whether they actually carry Google-style sections is unverified.

Production fix:
1. `scripts/audit_docstrings.py` imports `kb`, walks `kb.__all__`, resolves each name to its underlying function, parses `__doc__` via `ast.get_docstring` + simple regex (`r"^\s*Args:"m`, `r"^\s*Returns:"m`, `r"^\s*Raises:"m`). Fail (exit 1) if any function lacks `Args:` (when params present) AND `Returns:` (when non-None return). `Raises:` only required if function body has a `raise` outside `try`.
2. CI workflow runs `python scripts/audit_docstrings.py` on push.

Test:
- T12-A — script run against current `src/kb/` produces a list of missing sections; assert script exits 0 if all clean OR exits 1 with a parsable JSON list of offenders
- T12-B — fixture function with stripped docstring → script reports it
- T12-C (CI integration) — workflow runs script as a step; PR review verifies green

If audit produces N>0 offenders today, AC12 splits: (i) script lands as a tool; (ii) CI fail-on-offenders deferred to a follow-up cycle (entry in BACKLOG). Step 5 design gate decides. Default: ship script + warning-only CI mode in this cycle, hard-fail in cycle 68+.

### File: `README.md`

**AC13 — "Non-clone install" section documenting `KB_PROJECT_ROOT` bootstrap (Phase 4.5 MEDIUM).**

Current state: `kb.config` resolves project root via `cwd` → `pyproject.toml` walk → installed-file location heuristic. A `pip install kb` user (not cloning the repo) silently resolves data paths into the venv unless they set `KB_PROJECT_ROOT`. README does not prominently document this.

Production fix: add a new section to README between "Quick Start" and "Configuration" titled "Non-clone install (pip install)":
```markdown
## Non-clone install (pip install)

If you `pip install` kb without cloning the repo (e.g. for use as a library or
MCP server in a separate project tree), set `KB_PROJECT_ROOT` to the directory
containing your wiki:

  export KB_PROJECT_ROOT=/path/to/your/kb     # Unix
  $env:KB_PROJECT_ROOT = "C:\path\to\your\kb"  # PowerShell

Without this, `kb` resolves data paths to the directory it was installed in
(typically inside the venv `site-packages/`), which is not what you want.
```

Test: README diff inspection at Step 20 (no automated test required for prose).

### File: (new) `scripts/check_docs_index.py` + `.github/workflows/ci.yml`

**AC14 — `docs/reference/INDEX.md` ↔ filesystem ↔ `CLAUDE.md` table consistency check (mimo r3 NEW).**

Current state (verified): `docs/reference/INDEX.md` exists. CLAUDE.md has a "Detailed Documentation" table mapping topic → file. Both are hand-maintained; drift is silent.

Production fix:
1. `scripts/check_docs_index.py` reads `docs/reference/*.md`, extracts paths from `INDEX.md` and from CLAUDE.md's table (regex `\[.*?\]\(docs/reference/(.*?\.md)\)`), asserts every filesystem entry appears in BOTH lists. Reports drift.
2. CI runs script on push.

Test:
- T14-A — script run against current state; if green, ship as-is; if red (drift), Step 17 doc-update fixes it pre-merge
- T14-B — fixture: copy current docs to `tmp_path`, delete one entry from `INDEX.md`, run script → asserts fail
- T14-C — fixture: add a new `*.md` to `tmp_path/docs/reference/` not in either index, run script → asserts fail

### File: `src/kb/utils/cli_backend.py` (test add only)

**AC15 — Document + test the existing `_check_no_secrets_on_argv` substring scan (mimo r4 A — design intent clarification).**

Current state (verified at cli_backend.py:132-157): scrub is value-based substring containment of `os.environ[KEY]` actual value. Catches both bare-equality (`argv[i] == secret`) and embedded-in-flag (`argv[i] == "Authorization: Bearer secret"`) cases. Design intent stated in docstring lines 136-143.

Mimo r4 A claimed "self-DoS via generic regex match on full argv" — VERIFIED INCORRECT. The function does NOT regex-match argv; it iterates known env-var keys and scans argv for ACTUAL VALUE substrings.

Production fix: NO production change. Add three test cases to lock the design intent:
- T15-A (bare equality) — `["foo", os.environ["ANTHROPIC_API_KEY"]]` → raises `LLMError`
- T15-B (embedded in flag) — `["foo", f"Authorization: Bearer {os.environ['ANTHROPIC_API_KEY']}"]` → raises (split-string token construction per `feedback_no_secrets_in_code`)
- T15-C (false-positive guard) — `["foo", "ANTHROPIC_API_KEY"]` (key NAME, not value) when env value is `"sk-real-secret-..."` → does NOT raise

Closes the mimo r4 A finding via documentation rather than code change. Adds test coverage that didn't exist. Backstops a future maintainer who might "simplify" the scan to a regex-on-argv (which would re-introduce the false-positive class mimo claimed exists today).

## Out-of-scope (verified shipped in cycle ≤66)

- SSRF mitigation in URL → external CLI argv (mimo r4 B): VERIFIED STALE. Closed in lint/fetcher.py cycle ≤59. BACKLOG entry will be moved to "Resolved Phases" via Step 17.
- `KB_PROJECT_ROOT` call-time accessor (mimo r5 Q1): VERIFIED SHIPPED in cycle 65 AC1 as `get_project_root()` (config.py:70).
- `AUGMENT_ALLOWED_DOMAINS` call-time accessor (mimo r5 Q5): VERIFIED SHIPPED in cycle 65 AC3 as `get_allowed_domains()` (config.py:103).
- `_DEFAULT_MODEL_TIERS` deletion (mimo r5 Q2): MIS-IDENTIFIED. The actual stale-mechanism is the LEGACY `MODEL_TIERS` dict at config.py:237-241. AC01 fixes the actual surface; `_DEFAULT_MODEL_TIERS` (a dict literal of hardcoded IDs) is the source of truth and stays.
- MCP error boundary (Phase 6 R2 MEDIUM, mimo r4 E): VERIFIED SHIPPED across `mcp/core.py`, `mcp/ingest.py`, `mcp/quality.py` as `_mcp_error_boundary` decorator (cycle 65 AC21).
- `_validate_page_id` Windows trailing dot/space (Phase 6 cycle-64 HIGH): VERIFIED SHIPPED at `mcp/app.py:277` (cycle 65 AC6).
- `_validate_page_id` `:` Windows-illegal-char (Phase 6 cycle-64 MEDIUM): VERIFIED SHIPPED at `mcp/app.py:180` `_WINDOWS_ILLEGAL_CHARS_RE`.
- TOCTOU on `rebuild_indexes` (Phase 6 cycle-64 MEDIUM): VERIFIED SHIPPED via `_open_no_follow` (path_safety.py:103) used at compiler.py:757,775,801.
- Validator-contract drift (Phase 6 cycle-64 MEDIUM): VERIFIED SHIPPED via `_assert_under_project_root` (path_safety.py:31).
- `query/embeddings.py` multi-process race (Phase 6 cycle-64 LOW): VERIFIED SHIPPED via `file_lock(target_path.with_suffix(".db.lock"))` at embeddings.py:661.
- conftest auto-discovery for lru_cache (mimo r2 Q2): VERIFIED SHIPPED at conftest.py:336-347 via `for mod_name, mod in list(sys.modules.items())` + `getattr(attr, "cache_clear", None)`.
- `lint/fetcher.py` `TRAFILATURA_DOWNLOAD_NO_CACHE=1` (mimo r6 Q5): VERIFIED SHIPPED at fetcher.py:33.
- `requirements.txt` GitPython upper bound (mimo r6 Q1): VERIFIED SHIPPED as `GitPython>=3.1.47,<3.2` at requirements.txt:82.
- `docs/reference/INDEX.md` existence (mimo r3 NEW): VERIFIED EXISTS. AC14 adds the consistency check, not the file itself.
- `mcp_server.py` shim deletion (Phase 6 R2 LOW, mimo r1 Q5): DEFERRED. Pyproject already targets `kb.mcp:main` (not `kb.mcp_server`). The shim is a 6-line back-compat re-export. Low-value churn for cycle 67.

These will be reflected in BACKLOG.md cleanup at Step 17 (delete the resolved entries; add one-liner under "Resolved Phases" or expand cycle-65 / cycle-66 notes).

## Verification gates per AC

Each AC requires:
- T*A — primary positive test
- T*B — divergent-fail test (revert production → test fails RED) per cycle-23 L2 + cycle-24 L4
- Behavior assertion (not source-string scan) per cycle-11 L2 / cycle-23 L2
- Step 12 hard-gate: full pytest suite (3176+ baseline) per cycle-22 L3, not isolated subset
- Step 13 coverage delta: touched-file ≥90%, repo-total regression ≤0.5pp

## Owner attribution (Tier 2 binding-owner subset)

- Step 02 — Opus subagent (threat model + CVE baseline)
- Step 04-R1 — Opus 4.7 (main session via plan-eng-review)
- Step 04-R2 — `deepseek-rescue` @ `deepseek-v4-pro`
- Step 05 — Opus subagent (decision gate)
- Step 07 — `mimocoding-rescue` @ `mimo-v2.5-pro`
- Step 08 — `mimocoding-rescue` @ `mimo-v2.5-pro` (audit role)
- Step 09 background reviewer — `deepseek-rescue` @ `deepseek-v4-pro` (cross-family adversarial post-AC03+AC07 commits)
- Step 14 — `mimocoding-rescue` @ `mimo-v2.5-pro`
- Step 17 — `deepseek-rescue` @ `deepseek-v4-pro`
- Step 18 — `mimocoding-rescue` @ `mimo-v2.5`
- Step 20-R1 — `deepseek-rescue` @ `deepseek-v4-pro` + Sonnet
- Step 20-R2 — `codex:codex-rescue` + Sonnet
- Step 20-R3 (per cycle-17 L4 trigger) — Sonnet edge-case role

Per memory `project_cycle61_mimo_failure`: treat mimo-v2.5-pro Step 7/9 implementation as failed-by-default. Step 7 plan dispatch will set explicit fall-back-to-deepseek-then-primary tripwire on first observable failure mode.

## Commit order (suggested, finalized at Step 7)

Lower-risk → higher-risk, each AC self-contained:

1. AC02 (graph/cache AST guard test) — pure new test, no production change
2. AC08 (conftest meta-test) — pure new test
3. AC15 (cli_backend secrets scrub tests) — pure new test, design clarification
4. AC09 (snapshot paired negative-control) — pure new test
5. AC11 (CI dummy-key grep) — workflow-only
6. AC10 (CI snapshot-update reject) — workflow-only
7. AC14 (docs INDEX consistency script + CI) — script + workflow
8. AC12 (audit_docstrings script + CI) — script + workflow
9. AC13 (README "Non-clone install" section) — docs-only
10. AC04 (KB_STRICT_PUBLISH env var) — config + compile/compiler.py + tests
11. AC05 (sqlite_vec error sanitization) — query/embeddings.py + tests
12. AC07 (duplicate-slug allowlist YAML) — lint/checks/duplicate_slug.py + new lazy YAML loader + tests
13. AC06 (KB_DISABLE_VECTORS) — query/hybrid (or engine) + config + tests
14. AC01 (MODEL_TIERS proxy view) — config + tests; broader caller surface
15. AC03 (chunked stdout cap) — utils/cli_backend.py Popen refactor + tests; highest-risk

Step 7 implementation plan from `mimocoding-rescue` will lock or amend.
