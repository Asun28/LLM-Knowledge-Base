# Cycle 68 — Step 1 Requirements + Acceptance Criteria

**Date:** 2026-05-07 (NZT) / cycle started ~23:47 GMT+12 immediately after cycle-67 merge (PR #94)
**Pipeline:** `dev-mimo-opus` (project-scoped MiMo trial variant of feature-dev)
**Tier:** **Tier 2** — standard feature batch (full pipeline 1–24, no mandatory human gates)
**Worktree:** `.claude/worktrees/feat+cycle-67/` (path retained from cycle-67 worktree; branch is `feat/cycle-68` off `origin/main` HEAD `d13da0b`)

## Tier classification rationale

The cycle's 15 ACs touch:
- **Subprocess control** (`cli_backend.py` Popen refactor) — security-adjacent (kill semantics, stdin/stdout interleave, env scrub) but no auth / IAM / crypto / secret-handling change.
- **YAML loading** (`_lint_yaml.py` with `yaml.safe_load`) — defensive vs T7 (RCE class) but introduces a new file-read surface, NOT a new trust boundary.
- **Docstring audit script** (`audit_docstrings.py`) — pure CI gate, warn-only initially.
- **Graph cache caller migration** (5 read-only sites) — internal correctness, no external surface change.
- **httpx version pin tightening** — supply-chain hygiene, no behavioural change.
- **BACKLOG.md cleanup** — pure docs.

None of these are auth, authorization, secrets handling, crypto change, PII/data-class boundary, irreversible migration, signing-key change, or deploy-pipeline change. **Tier 2 fits**; the "when in doubt, go up" guidance does not fire because the security-adjacent items (cli_backend Popen + YAML safe_load) are *already* design-locked from cycle-67's Step 5 with 19 binding CONDITIONS — no new trust-surface exploration needed in cycle 68.

Per `feedback_auto_approve` memory: zero human-in-the-loop, all approvals via Opus subagents.

## Carry-over inheritance from cycle 67

Three cycle-67 ACs were design-locked but deferred for time/risk:
| Cycle-67 AC | Cycle-68 AC | Spec source | Sub-conditions inherited |
|-------------|-------------|-------------|--------------------------|
| AC03 (`cli_backend.py` Popen) | AC01 + AC02 + AC11 | cycle-67 design.md C-AC03-{stdin,platform,stderr,error-kinds} + FW-1 | 4 sub-conditions |
| AC07 (`wiki/_lint.yml` lazy loader) | AC03 + AC04 + AC12 | cycle-67 design.md C-AC07-{safe,fallback,schema} + FW-2 | 3 sub-conditions |
| AC12 (`scripts/audit_docstrings.py`) | AC05 + AC06 + AC13 | cycle-67 design.md C-AC12-generator + FW-4 | 1 sub-condition |

These inherit cycle-67's R1+R2 design verdicts verbatim. Step 04 of cycle 68 only re-evaluates the NEW items (AC07-AC10) — graph-cache migration, httpx pin, BACKLOG cleanup.

## Acceptance criteria (15 ACs)

### Source deliverables

**AC01 — `src/kb/utils/cli_backend.py` Popen refactor.** Replace `subprocess.run(capture_output=True, ...)` at lines 213-247 with `subprocess.Popen` + `selectors`-based chunked stdout/stderr reader. Cap stdout incrementally at `MAX_CLI_STDOUT_BYTES`; cap stderr incrementally at the new `MAX_CLI_STDERR_BYTES`. Stdin write splits from daemon readers (do NOT use `proc.communicate(input=...)` — FW-1). Platform-aware kill grace (POSIX `terminate(); wait(2); kill()`; Windows `terminate(); wait(0.5)`). Preserve all `LLMError(kind=...)` paths: `not_installed`, `timeout`, generic exit-code-non-zero (R2-F9). **Owner:** Opus main (security-class src per `project_cycle61_mimo_failure`).

**AC02 — `src/kb/config.py` add `MAX_CLI_STDERR_BYTES = 64 * 1024` constant.** Symmetry with existing `MAX_CLI_STDOUT_BYTES`. Used by AC01.

**AC03 — `src/kb/lint/_lint_yaml.py` NEW.** Lazy YAML loader that reads optional `wiki/_lint.yml` via `yaml.safe_load` ONLY (FW-2 — never `yaml.load`, RCE class T7). Returns `{}` on file-not-found / parse-error / I/O-permission-error (logs warning, falls through). Schema validation: when `duplicate_slug_allowlist` is not list-of-pairs, log warning + fall through. Read at CALL TIME per cycle-19 L2 (no module-level cache).

**AC04 — `src/kb/lint/checks/duplicate_slug.py` externalize `DUPLICATE_SLUG_ALLOWLIST`.** Replace hardcoded list with `_lint_yaml.load_lint_config().get("duplicate_slug_allowlist", [])`. Read at call time.

**AC05 — `scripts/audit_docstrings.py` NEW.** Walks `kb.__all__`, parses `__doc__` via `ast.get_docstring`, checks for `Args:` / `Returns:` / `Raises:` sections via regex. Conditional Raises requirement: if function body contains `raise` (incl. generator functions per FW-4), `Raises:` section required. Warn-only mode initially per R1-F4 (transition path); BACKLOG entry if any offenders. Hard-fail mode planned for cycle 69+.

**AC06 — `.github/workflows/ci.yml` add docstring-audit step.** Runs `python scripts/audit_docstrings.py --warn-only`; emits stderr summary; never fails CI in cycle 68.

**AC07 — `src/kb/evolve/analyzer.py` migrate 3 `build_graph` call sites to `kb.graph.cache.get_graph`.** Per Phase 4.5 HIGH backlog (`graph/builder.py` non-lint callers). Use attribute-lookup form `kb.graph.cache.get_graph(wiki_dir)` per cycle-18 L1.

**AC08 — `src/kb/graph/export.py`, `src/kb/mcp/browse.py`, `src/kb/query/engine.py` migrate remaining `build_graph` call sites to `kb.graph.cache.get_graph`.** Same Phase 4.5 HIGH backlog. Total cycle-68 migration: 5 sites across 4 files.

**AC09 — `pyproject.toml` tighten httpx ceiling.** Change `httpx>=0.27` to `httpx>=0.28,<0.29` to match `lint/fetcher.py:51` runtime assertion. Closes Phase 4.5 HIGH httpx constraint mismatch.

**AC10 — `BACKLOG.md` cleanup.** Delete entries marked SHIPPED in the `CYCLE 67 cleanup pass` comment block: GitPython unpinned, SSRF on URL→external CLI, KB_PROJECT_ROOT call-time, `_autouse_kb_path_sandbox` no-drop guard, hardcoded lru_cache list, trafilatura+diskcache, `_DEFAULT_MODEL_TIERS` dual mechanism, `AUGMENT_ALLOWED_DOMAINS`, MCP error responses raw tracebacks, `_check_no_secrets_on_argv` self-DoS, `graph/cache.py` 6th-caller drift, `tests/test_cycle64_snapshots.py` tautology, CI `sk-ant-dummy` grep, `docs/reference/` INDEX.md, the 3 cycle-68 carry-over entries (now AC01-AC06), `auto_publish_after_compile` exceptions swallowed, `kb.query.hybrid` `KB_DISABLE_VECTORS=1`, README `KB_PROJECT_ROOT` bootstrap, `compile/compiler.py:645` validator drift, `mcp/app.py:230` Windows trailing-dot. Each verified shipped per cycle-67 changelog or earlier cycles.

### Test deliverables

**AC11 — `tests/test_cycle68_cli_backend_popen.py` NEW.** Covers C-AC03-{stdin,platform,stderr,error-kinds} from cycle-67 design:
- `test_cli_backend_popen_large_stdin_plus_large_stdout` — stdin write + chunked stdout + cap (no deadlock per FW-1).
- `test_cli_backend_popen_platform_kill_branch` — monkeypatch `sys.platform`; assert wait timeout differs (POSIX 2s vs Windows 0.5s).
- `test_cli_backend_popen_stderr_capped` — produces >`MAX_CLI_STDERR_BYTES` stderr; assert truncation.
- `test_cli_backend_popen_preserves_error_kinds` — three sub-cases for `kind="not_installed"`, `kind="timeout"`, generic exit-code-non-zero.

**AC12 — `tests/test_cycle68_lint_yaml.py` NEW.** Covers C-AC07-{safe,fallback,schema}:
- `test_lint_yaml_rejects_malicious_payload` — `!!python/object/new:os.system ['echo OWNED']` raises `yaml.YAMLError` (NOT executes).
- `test_lint_yaml_file_missing_returns_empty` — no `wiki/_lint.yml` → `{}` + no warning escalation.
- `test_lint_yaml_parse_error_returns_empty` — invalid YAML → `{}` + warning logged.
- `test_lint_yaml_io_permission_returns_empty` — chmod 000 (POSIX skipif) → `{}` + warning logged.
- `test_lint_yaml_schema_mixed_type_warning` — `duplicate_slug_allowlist: "not-a-list"` → warning + fall through to default.
- `test_lint_yaml_call_time_read` — patch `wiki/_lint.yml` between calls; assert second call sees new value (no caching leak).

**AC13 — `tests/test_cycle68_audit_docstrings.py` NEW.** Covers C-AC12-generator + transition path:
- `test_audit_docstrings_normal_func_requires_args_returns` — function with params and return annotation MUST have `Args:` and `Returns:`.
- `test_audit_docstrings_func_with_raise_requires_raises_section` — body has `raise X(...)` → `Raises:` required.
- `test_audit_docstrings_generator_with_raise_requires_raises_section` — body has `yield` AND `raise` → `Raises:` required (FW-4).
- `test_audit_docstrings_warn_only_exit_zero` — even if violations exist, exit code is 0 (cycle-68 transition mode).

**AC14 — `tests/test_cycle68_graph_cache_caller_migrations.py` NEW.** AST guard:
- `test_no_direct_build_graph_calls_in_migrated_files` — parse `evolve/analyzer.py`, `graph/export.py`, `mcp/browse.py`, `query/engine.py`; assert zero `ast.Call` with `func.attr == "build_graph"` outside `kb.graph.cache` module.
- `test_get_graph_cache_hit_on_repeat_call` — behavioural spy on `kb.graph.builder.build_graph`; first `get_graph(wiki)` calls builder, second hits cache (call_count == 1).

**AC15 — `tests/test_cycle68_httpx_pin_drift.py` NEW + `tests/test_cycle68_backlog_cleanup_lockin.py` NEW.** Regression locks:
- `test_pyproject_httpx_pin_has_explicit_ceiling` — parses `pyproject.toml`; asserts httpx constraint string contains both `>=0.28` and `<0.29`.
- `test_backlog_does_not_contain_shipped_phase_4_5_high_entries` — parses BACKLOG.md; asserts cleaned-up entries (e.g. GitPython unpinned, KB_PROJECT_ROOT call-time, `_autouse_kb_path_sandbox` no-drop guard) are absent.

## Test-pin grid (AC → test files)

| AC | Source files | Test files | CONDITIONS source |
|----|--------------|------------|-------------------|
| AC01 | `src/kb/utils/cli_backend.py` | AC11 | C-AC03-{stdin,platform,stderr,error-kinds} |
| AC02 | `src/kb/config.py` | AC11 (covered via AC01) | (config constant only) |
| AC03 | `src/kb/lint/_lint_yaml.py` (NEW) | AC12 | C-AC07-{safe,fallback,schema} |
| AC04 | `src/kb/lint/checks/duplicate_slug.py` | AC12 (call-time read sub-test) | C-AC07-{safe,fallback,schema} |
| AC05 | `scripts/audit_docstrings.py` (NEW) | AC13 | C-AC12-generator + R1-F4 transition |
| AC06 | `.github/workflows/ci.yml` | (AC13 covers script; CI step is glue) | R1-F4 |
| AC07 | `src/kb/evolve/analyzer.py` | AC14 | (Phase 4.5 HIGH carry-over) |
| AC08 | `src/kb/graph/export.py`, `src/kb/mcp/browse.py`, `src/kb/query/engine.py` | AC14 | (Phase 4.5 HIGH carry-over) |
| AC09 | `pyproject.toml` | AC15 (`test_pyproject_httpx_pin_has_explicit_ceiling`) | (Phase 4.5 HIGH carry-over) |
| AC10 | `BACKLOG.md` | AC15 (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) | (cycle-67 cleanup audit) |

## Skip-when verification per pipeline step

Steps 02, 06, 16, 19, 22, 23 may skip per their `Skip when` rows. Step 14 explicitly **NEVER** skipped per cycle-21 L1. Steps 11, 13 conditionally skip if no third-party deps changed and no I/O-bearing src changed — neither holds for cycle-68 (AC03 introduces YAML I/O, AC09 changes a dep constraint).

## Forward-looking risks (FW-1 through FW-6 inherited)

Per cycle-67 design.md FW section, Step-7 plan dispatch MUST include verbatim:
- **FW-1:** AC03 Popen MUST split stdin write from stdout/stderr reads — never `proc.communicate(input=...)` with daemon readers.
- **FW-2:** AC07 MUST use `yaml.safe_load` ONLY; never `yaml.load`.
- **FW-3:** AC11 dummy-key grep — DOES NOT APPLY to cycle 68 (cycle-67 already shipped).
- **FW-4:** AC12 generator + yield + raise — generators with `raise` need `Raises:` section.
- **FW-5:** AC01 (cycle-67) Mapping ABC — DOES NOT APPLY to cycle 68 (cycle-67 already shipped MODEL_TIERS).
- **FW-6:** Step-7 task ordering — cycle-68 ordering: AC09 → AC10 → AC07 → AC08 → AC02 → AC11 → AC01 → AC03 → AC04 → AC12 → AC05 → AC06 → AC13 → AC14 → AC15. Workflow + dep changes commit BEFORE security-class src per cycle-67 R1-C10.

## R3 trigger reaffirmation

Cycle-17 L4 risk-profile triggers met (any one fires R3 below the 25-AC line):
- (a) NEW filesystem-write surface: NO — `wiki/_lint.yml` is read-only.
- (b) Defensive check whose input is hard to reach: YES — AC01 platform-kill branch on Windows is hard to exercise in CI (R2-F8 documented scope).
- (c) NEW security enforcement point: YES — AC03 `yaml.safe_load` boundary, AC05 docstring audit gate (warn-only but new gate).
- (d) Step-5 design gate resolved ≥10 open questions: YES (cycle-68 inherits 19 CONDITIONS from cycle-67 + adds new conditions for AC07-AC10).

**Step 20 R3 REQUIRED** (Sonnet edge-case role per cycle-17 L4). Document trigger in PR body at Step 18.

## Owner mapping (per skill table + telemetry refinements)

| Step | Owner | Notes |
|------|-------|-------|
| 01 | Opus main | this doc |
| 02 | Opus subagent | threat model + dep-CVE baseline |
| 03 | Opus main | brainstorming |
| 04 R1 | Opus subagent | design eval R1 |
| 04 R2 | DeepSeek V4 Pro (`deepseek-rescue`) | design eval R2 |
| 05 | Opus subagent | design decision gate |
| 06 | Sonnet (main) | Context7 — likely SKIP per stdlib-only |
| 07 | MiMo Coding subagent (`mimocoding-rescue` @ `mimo-v2.5-pro`) | impl plan |
| 08 | MiMo Coding subagent (`mimo-v2.5-pro`) | plan gate |
| 09 | MiMo Coding (impl) + DeepSeek V4 Pro (background reviewer, cross-family adversarial) | TDD impl. Per `project_cycle61_mimo_failure`: security-class src (AC01, AC03) routes to primary Opus; non-security src to mimo. |
| 10 | Opus main | simplify |
| 11 | non-agent | bandit + semgrep + gitleaks |
| 12 | non-agent | full pytest + pip-audit |
| 13 | non-agent | pytest --cov |
| 14 | MiMo Coding subagent (audit role works per cycle-67 telemetry) | security verify vs Step 02 |
| 15 | non-agent | gh api dependabot |
| 16 | non-agent | likely SKIP (no `*.tf` / Dockerfile / dep-manifest change beyond AC09) |
| 17 | DeepSeek subagent | doc update |
| 18 | MiMo Coding subagent (`mimo-v2.5`) | PR finalize |
| 19 | non-agent | likely SKIP (no signing requirement) |
| 20 R1 | DeepSeek + Sonnet | PR review R1 |
| 20 R2 | Codex + Sonnet | PR review R2 |
| 20 R3 | Sonnet edge-case | required per cycle-17 L4 |
| 21 | automated | merge |
| 22 | external | SKIP (no deployable artifact change) |
| 23 | non-agent | SKIP (Step 22 was skipped) |
| 24 | Opus main | self-review + lessons |

## Definition of done

- [ ] All 15 ACs implemented per spec
- [ ] All test pins green; full suite (3231+ tests) passes
- [ ] Coverage delta ≥90% on touched files; ≤0.5pp repo regression
- [ ] BACKLOG.md cleaned per AC10
- [ ] CHANGELOG.md + CHANGELOG-history.md + CLAUDE.md + README.md (if applicable) updated
- [ ] PR squash-merged after R1+R2(+R3) APPROVE
- [ ] Step 24 self-review committed
