# Cycle 68 — Threat Model + Dep-CVE Baseline

**Date:** 2026-05-08
**Branch:** `feat/cycle-68` (worktree path retained as `feat+cycle-67/`)
**Step:** 2 of 24 (dev-mimo-opus, Tier 2)
**Inputs:** `2026-05-07-cycle-68-requirements.md` (15 ACs), `2026-05-07-cycle-67-threat-model.md` (15 STRIDE threats), `2026-05-07-cycle-67-design.md` (19 binding CONDITIONS)
**STRIDE coverage:** S(poofing) · T(ampering) · R(epudiation) · I(nformation Disclosure) · D(enial of Service) · E(levation of Privilege)

---

## Analysis

Cycle 68's 15 ACs split cleanly into two groups along the cycle-67-carry-over axis:

- **Carry-overs from cycle 67 (9 of 15 ACs):** AC01/AC02/AC11 (`cli_backend.py` Popen refactor — cycle-67 AC03), AC03/AC04/AC12 (`_lint_yaml.py` lazy YAML loader — cycle-67 AC07), AC05/AC06/AC13 (`audit_docstrings.py` warn-only gate — cycle-67 AC12). Cycle 67's Step-5 design gate already produced 19 binding CONDITIONS for these (`C-AC03-{stdin,platform,stderr,error-kinds}`, `C-AC07-{safe,fallback,schema}`, `C-AC12-generator`, FW-1, FW-2, FW-4). Cycle 68 inherits those CONDITIONS verbatim — the trust boundaries, threat vectors, mitigations, and test contracts are unchanged. Cycle-67 STRIDE entries T3, T7, and T12 transcribe directly onto cycle 68 with the cycle-68 AC numbers and cycle-68 test files.
- **NEW in cycle 68 (6 of 15 ACs):** AC07/AC08 (graph cache caller migration across 5 sites in 4 files), AC09 (httpx pin ceiling), AC10 (BACKLOG.md cleanup of shipped entries), AC14/AC15 (AST + regression-pin test files). None of these introduces a new external trust boundary; they are correctness, supply-chain-hygiene, and test-signal hardening.

Per cycle-3 L7 (Opus 4.7 needs explicit CoT scaffolding) and cycle-23 L2 (every threat verifiable via behaviour assertion, not source-string scan), each threat below maps 1:1 to a behavioural test pin in `tests/test_cycle68_*.py`. The total count stays well under the cycle-67 ceiling (15) — cycle 68 has 7 threats because the carry-overs collapse into 3 grouped entries (Popen / YAML / docstring audit) where the cycle-67 mitigation already covers the cycle-68 scope.

The most invasive AC remains AC01 (Popen refactor) because it is the only structural change. AC07/AC08 are mechanical attribute-lookup-form migrations of internal call sites; AC09 is a one-line `pyproject.toml` constraint tightening; AC10 is a docs-only deletion pass; AC14/AC15 are pure test-additions.

The cycle-67 design verdict stands: **no Tier-3 escalation required**. AC01's design is locked to cycle-67's 19 CONDITIONS plus FW-1 (split stdin write from daemon readers) and FW-6 (workflow + dep changes commit before security-class src). The new items are all low-blast-radius.

---

## Trust boundaries in scope

| Boundary | Affected ACs | Notes |
|---|---|---|
| **CLI subprocess output → Python process memory** | AC01, AC02, AC11 | Inherited from cycle-67 AC03. Replace `subprocess.run` with `Popen` + `selectors`-based chunked stdout/stderr readers. NEW (cycle 68 vs cycle 67): symmetric stderr cap via `MAX_CLI_STDERR_BYTES = 64 * 1024`. |
| **Filesystem (`wiki/_lint.yml`) → lint check** | AC03, AC04, AC12 | Inherited from cycle-67 AC07. Lazy YAML loader; `yaml.safe_load` only; graceful fallback to defaults. NEW (cycle 68): explicit POSIX I/O-permission case (`chmod 000`) gets its own test pin per cycle-67 R2-F12 fallback trio. |
| **`kb.__all__` API surface → external caller** | AC05, AC06, AC13 | Inherited from cycle-67 AC12. Docstring audit script as CI gate; warn-only initially per cycle-67 R1-F4 transition path. NEW (cycle 68): generator-with-`raise` enforcement test (FW-4) is a fresh test pin. |
| **`kb.graph.builder.build_graph` direct callers → graph cache** | AC07, AC08 | NEW in cycle 68. 5 call sites across `evolve/analyzer.py`, `graph/export.py`, `mcp/browse.py`, `query/engine.py` migrate to attribute-lookup form `kb.graph.cache.get_graph(wiki_dir)` per cycle-18 L1 (avoids snapshot-binding hazard for `monkeypatch.setattr(kb.graph.cache, "get_graph", ...)` test spies). |
| **`pyproject.toml` install-time constraints → `pip install`** | AC09 | NEW in cycle 68. Tighten `httpx>=0.27` → `httpx>=0.28,<0.29` to match `lint/fetcher.py:51` runtime `assert`. Closes constraint-vs-runtime drift. |
| **`BACKLOG.md` → developer-facing project memory** | AC10 | NEW in cycle 68. Pure deletion pass over ~22 SHIPPED entries. Failure mode: deleting an OPEN item by mistake. |
| **Regression test artifact → CI signal** | AC14, AC15 | NEW in cycle 68. Three test files (`test_cycle68_graph_cache_caller_migrations.py` + `test_cycle68_httpx_pin_drift.py` + `test_cycle68_backlog_cleanup_lockin.py`) lock cycle 68's invariants. Risk: vacuous tests (cycle-22 L5 / cycle-11 L2 / user memory `feedback_inspect_source_tests`). |

No new auth boundary, no new IAM/crypto/data-class/migration surface, no new external network surface. Per requirements §"Tier" line 13: boundary-preserving.

---

## Threats

### T1 (D) — Misbehaving CLI backend OOMs Python process before subprocess.run truncation [INHERITED from cycle-67 T3]

- **Class:** Denial of Service (memory exhaustion before downstream slice)
- **AC origin:** AC01, AC02, AC11
- **Inheritance status:** INHERITED — cycle-67 T3 verbatim. Cycle-67 design CONDITIONS C-AC03-stdin (FW-1), C-AC03-platform, C-AC03-stderr, C-AC03-error-kinds (R2-F9) all apply unchanged.
- **Description:** A misbehaving CLI backend (e.g., `gemini` infinite-prompt-echo loop, attacker-controlled local CLI binary, runaway model-output stream) writes gigabytes to stdout before exiting. Current `subprocess.run(capture_output=True)` at `cli_backend.py:213-247` buffers ENTIRE stdout in memory before the `result.stdout[:MAX_CLI_STDOUT_BYTES]` slice fires. On a workstation with 16GB RAM, a backend writing 32GB of stdout OOMs the `kb` process before any cap fires. Cycle-68 scope adds AC02 (`MAX_CLI_STDERR_BYTES = 64 * 1024` for symmetric stderr cap) and AC11 (test pins for all four cycle-67 sub-conditions: stdin overflow, platform-aware kill, stderr cap, error-kind preservation).
- **Mitigation:** AC01 — replace `subprocess.run` with `subprocess.Popen` + `selectors`-based chunked stdout/stderr reader. Stdin write splits from daemon readers (FW-1; do NOT use `proc.communicate(input=...)`). Cap stdout incrementally at `MAX_CLI_STDOUT_BYTES`; cap stderr at the new `MAX_CLI_STDERR_BYTES`. Platform-aware kill: POSIX `terminate(); wait(2); kill()`; Windows `terminate(); wait(0.5)`. Preserve `LLMError(kind=...)` paths: `not_installed`, `timeout`, generic exit-code-non-zero (R2-F9). Owner per `project_cycle61_mimo_failure`: Opus main (security-class src).
- **Test pin:** `pytest tests/test_cycle68_cli_backend_popen.py::{test_cli_backend_popen_large_stdin_plus_large_stdout, test_cli_backend_popen_platform_kill_branch, test_cli_backend_popen_stderr_capped, test_cli_backend_popen_preserves_error_kinds}`. Behavioural assertions (not source-string scans) per cycle-23 L2.

### T2 (T, E) — `wiki/_lint.yml` malformed YAML crashes lint pass / `_lint.yml` allowlist abuse [INHERITED from cycle-67 T7]

- **Class:** Tampering (malformed YAML denial of lint); Elevation of Privilege (allowlist abuse hides duplicate-slug detection); Tampering→RCE if `yaml.load` is used instead of `yaml.safe_load`
- **AC origin:** AC03, AC04, AC12
- **Inheritance status:** INHERITED — cycle-67 T7 verbatim. Cycle-67 design CONDITIONS C-AC07-safe (FW-2 — `yaml.safe_load` only), C-AC07-fallback (R2-F12 — file-not-found / parse-error / I/O permission trio), C-AC07-schema (R2-F13 — list-of-pairs warning) all apply unchanged.
- **Description:** Three attack vectors:
  1. **Malformed YAML / parse error** — A user/attacker writes `wiki/_lint.yml` with invalid YAML (truncated quote, tab-indent error). Without graceful fallback, `kb lint` crashes hard, denying the entire lint pass.
  2. **YAML deserialization RCE** — `yaml.load` (NOT `safe_load`) interprets `!!python/object/new:os.system ['echo OWNED']` as a Python instantiation, executing arbitrary code at lint time. This is the canonical CVE-class for PyYAML before 5.1's `FullLoader` default change.
  3. **Allowlist abuse** — A malicious contributor with write access to `wiki/_lint.yml` allowlists `concepts/admin` vs `concepts/admin-real`, hiding a phishing-class duplicate-slug from `check_duplicate_slugs`.
- **Mitigation:** AC03 — `kb.lint._lint_yaml.load_lint_config(wiki_dir)` is a LAZY reader: returns `{}` on file missing, returns `{}` + emits a `logger.warning` on YAML parse error or I/O-permission error. YAML schema restricted to top-level `duplicate_slug_allowlist: [["a", "b"], ...]`; uses `yaml.safe_load` (NOT `yaml.load`) — blocks Python-object instantiation and closes the RCE class. Read at CALL TIME per cycle-19 L2 (no module-level cache). AC04 — `duplicate_slug.py` consumes `_lint_yaml.load_lint_config().get("duplicate_slug_allowlist", [])` at call time, falling through to `kb.config.DUPLICATE_SLUG_ALLOWLIST` defaults when absent.
- **Test pin:** `pytest tests/test_cycle68_lint_yaml.py::{test_lint_yaml_rejects_malicious_payload, test_lint_yaml_file_missing_returns_empty, test_lint_yaml_parse_error_returns_empty, test_lint_yaml_io_permission_returns_empty, test_lint_yaml_schema_mixed_type_warning, test_lint_yaml_call_time_read}`. The first test asserts `!!python/object/new:os.system ['echo OWNED']` raises `yaml.YAMLError` and DOES NOT execute `os.system` (verified via spy on the os.system callable).

### T3 (R) — `kb.__all__` API surface lacks Args/Returns/Raises docstrings; downstream callers misuse contract [INHERITED from cycle-67 T12]

- **Class:** Repudiation (documentation claims contract that the code doesn't carry)
- **AC origin:** AC05, AC06, AC13
- **Inheritance status:** INHERITED — cycle-67 T12 verbatim. Cycle-67 design CONDITION C-AC12-generator (FW-4 — generator-with-`raise` requires `Raises:`) applies unchanged. Cycle-67 R1-F4 transition path (warn-only this cycle, hard-fail in cycle 69+) explicitly carries forward.
- **Description:** `kb/__init__.py` is a 67-line lazy `__getattr__` shim. Real Args/Returns/Raises sections must live on the underlying functions in `kb/ingest/pipeline.py`, `kb/compile/__init__.py`, `kb/query/__init__.py`, `kb/graph/__init__.py`. A downstream caller (`pip install kb` + `from kb import ingest_source`) sees the shim's docstring (or no docstring at all) and infers the contract from name + type hints; misuse follows. Cycle-68 scope tightens FW-4: generator functions (those that `yield`) with `raise` in body MUST have a `Raises:` section.
- **Mitigation:** AC05 — `scripts/audit_docstrings.py` walks `kb.__all__`, parses `__doc__` via `ast.get_docstring`, checks for `Args:` / `Returns:` / `Raises:` sections via regex (`r"^\s*Args:"m`, `r"^\s*Returns:"m`, `r"^\s*Raises:"m`). Conditional Raises requirement: if function body contains `raise` (incl. generator functions per FW-4), `Raises:` section required. AC06 — CI step runs `python scripts/audit_docstrings.py --warn-only`; emits stderr summary; never fails CI in cycle 68. AC13 — test file pins the four behavioural cases including the generator-with-`raise` case (FW-4).
- **Test pin:** `pytest tests/test_cycle68_audit_docstrings.py::{test_audit_docstrings_normal_func_requires_args_returns, test_audit_docstrings_func_with_raise_requires_raises_section, test_audit_docstrings_generator_with_raise_requires_raises_section, test_audit_docstrings_warn_only_exit_zero}`. The fourth test asserts exit code is 0 even with violations present — locks cycle-67 R1-F4 transition path so a future hard-fail flip is deliberate.

### T4 (T) — Direct `build_graph` callers bypass cache test-spies; lint pass + caller-pass divergence [NEW]

- **Class:** Tampering (silent test-spy bypass; cache-vs-caller staleness divergence)
- **AC origin:** AC07, AC08, AC14
- **Inheritance status:** NEW — cycle-67 AC02 hardened the `kb.graph.cache.get_graph` lookup-form discipline for the LINT pass via the AST-walker negative control. Cycle 68 EXTENDS that discipline to the 5 remaining direct `build_graph` call sites in `kb.evolve.analyzer` (3 sites), `kb.graph.export`, `kb.mcp.browse`, `kb.query.engine` (Phase 4.5 HIGH backlog).
- **Description:** Cycle 64 AC9 introduced `kb.graph.cache.get_graph()` as the canonical cached entry for lint-pass graph lookup. Cycle 65 AC17 set `__all__ = []` to discourage `from kb.graph.cache import get_graph`. Cycle 67 AC02 added the AST negative-control walker for the lint pass. However, 5 non-lint call sites in `evolve/analyzer.py`, `graph/export.py`, `mcp/browse.py`, `query/engine.py` still call `kb.graph.builder.build_graph(wiki_dir)` directly — bypassing the cache. Two harms:
  1. **Cache staleness divergence** — A mutator (`ingest_source`, `refine_page`, `compile_wiki`) calls `kb.graph.cache.invalidate(wiki_dir)` post-success per CLAUDE.md cycle 64 AC9 contract. Subsequent lint reads see the rebuilt graph. But `evolve/analyzer.py` calls `build_graph(wiki_dir)` directly — never participates in invalidation. After a mutation, lint sees the new graph while `kb evolve` reads the source state freshly each time (no shared cache). This is a correctness divergence: lint says "OK"; evolve says "stale links". User confusion ensues.
  2. **Test-spy bypass** — A future test does `monkeypatch.setattr(kb.graph.cache, "get_graph", lambda wd: stub_graph)`. The lint pass picks up the stub. The `evolve/analyzer.py` call site does NOT — it imports `build_graph` from `kb.graph.builder` directly, never touching the cache attribute. Test spy fires but cycle-23 L4 same-class-peer scan reveals the divergence too late.
- **Mitigation:** AC07 — migrate 3 call sites in `kb.evolve.analyzer` to attribute-lookup form `kb.graph.cache.get_graph(wiki_dir)` per cycle-18 L1. AC08 — migrate the remaining 2 sites in `graph/export.py`, `mcp/browse.py`, `query/engine.py` (one per file, total 5 across 4 files). Use attribute-lookup form (`import kb.graph.cache` + `kb.graph.cache.get_graph(wd)`), NOT `from kb.graph.cache import get_graph` — the cycle-67 AC02 AST walker forbids the import form. AC14's first test pin AST-parses each migrated file and asserts zero `ast.Call` nodes whose `func.attr == "build_graph"` AND whose attribute chain resolves outside `kb.graph.cache`. AC14's second test pin behaviourally spies on `kb.graph.builder.build_graph` and asserts that two consecutive `kb.graph.cache.get_graph(wiki)` calls invoke the builder once (cache hit on second call).
- **Test pin:** `pytest tests/test_cycle68_graph_cache_caller_migrations.py::{test_no_direct_build_graph_calls_in_migrated_files, test_get_graph_cache_hit_on_repeat_call}`. The first is an AST guard, the second is a behavioural assertion (spy `call_count == 1` after two `get_graph` invocations) — together they close both the static and runtime divergence classes. Per user memory `feedback_test_behavior_over_signature`, the second test is REQUIRED — an AST-only test would pass after a revert to direct calls if the test fixture is wrong.
- **Related lessons:** cycle-18 L1 (attribute-lookup form vs snapshot-binding); cycle-22 L5 (load-bearing tests); cycle-23 L4 (same-class peer scan); cycle-67 AC02 (lint-pass AST walker — extended here); user memory `feedback_test_behavior_over_signature`.

### T5 (D, S) — `httpx` install-time constraint mismatch with runtime assertion [NEW]

- **Class:** Denial of Service (install fails at runtime when constraint is too loose); Spoofing (silent feature-mismatch when an older httpx ships features the runtime assumes patched)
- **AC origin:** AC09, AC15
- **Inheritance status:** NEW — Phase 4.5 HIGH carry-over not addressed in cycle 67.
- **Description:** `pyproject.toml` currently pins `httpx>=0.27`. `lint/fetcher.py:51` has a runtime `assert httpx.__version__ >= "0.28"` (or equivalent compat-check). Three failure modes:
  1. **Loose-constraint silent install of broken setup** — A user runs `pip install -e .` with a pre-existing `httpx==0.27.1` in their env. The `>=0.27` constraint is satisfied; pip skips the upgrade. The `kb lint --fetch` flow then crashes at the runtime assertion, exposing a confusing error: "ImportError or AssertionError" mid-CLI. This is the constraint-vs-runtime drift class.
  2. **Tight-constraint blocks valid security patches** — If cycle 68 pins `httpx==0.28.1` exactly, a future CVE-fix in `httpx==0.28.5` is blocked from being picked up by `pip install --upgrade`. The pin must be `>=0.28,<0.29` (range, not exact) to allow patch-level fixes within the supported minor.
  3. **Pin too loose causes wrong-version response in production** — A future major release `httpx==0.29.0` may change response-stream API (e.g., async iteration semantics). Without an upper ceiling, a transitive `pip install --upgrade-strategy eager` could pull `httpx==0.29.0` silently; runtime behaviour drifts (e.g., a streamed download returns differently). This is a Spoofing-class threat: the same code receives a different upstream contract.
- **Mitigation:** AC09 — change `pyproject.toml` httpx pin from `httpx>=0.27` to `httpx>=0.28,<0.29` to match the runtime `assert` floor and bound the upper to the supported minor. The range form (not exact) preserves CVE-fix uptake within `0.28.x`. AC15's first test pin parses `pyproject.toml`, locates the httpx constraint, and asserts both `>=0.28` and `<0.29` substrings present.
- **Test pin:** `pytest tests/test_cycle68_httpx_pin_drift.py::test_pyproject_httpx_pin_has_explicit_ceiling`. Behavioural assertion (parse-and-check) per cycle-22 L5 — NOT a `grep "httpx" pyproject.toml` source-string scan that would pass after a revert.
- **Related lessons:** cycle-22 L1 (pip-audit drift); user memory `feedback_dependabot_pre_merge` (4-gate dep-CVE model); SECURITY.md cadence (Step 11.5 opportunistic-patch slot); cycle-21 L7 (defence-in-depth — runtime assertion AND install constraint).

### T6 (T) — `BACKLOG.md` cleanup deletes OPEN items by mistake; project-memory data loss [NEW]

- **Class:** Tampering (loss of project-memory; future cycles re-investigate already-known issues)
- **AC origin:** AC10, AC15
- **Inheritance status:** NEW — pure docs-deletion pass introduced this cycle.
- **Description:** `BACKLOG.md` carries the SHIPPED-but-not-yet-pruned entries from cycle 67's "CYCLE 67 cleanup pass" comment block (~22 entries, listed in requirements line 55). AC10 is a deletion pass over those entries. The threat: an entry is deleted that was actually still open (e.g., partially-shipped, or shipped in a way that doesn't fully close the BACKLOG description). Failure modes:
  1. **Pattern-match miss** — A maintainer deleting based on title-grep deletes an entry whose title resembles a SHIPPED item but whose body describes a different open issue.
  2. **Stale "shipped" claim in cycle-67 comment block** — Cycle-67 author marked entry as SHIPPED but the actual fix only addressed one of two sub-bullets; deletion erases the open sub-bullet.
  3. **Future re-investigation cost** — Once deleted, the only recovery is `git log -p BACKLOG.md` archaeology. For a 100+ commit history this is costly.
- **Mitigation:** AC10 — each deletion verified against current source via grep BEFORE deletion. The cycle-67 changelog (or the cycle-N changelog where cycle-N ≤ 67 shipped the item) is the source of truth for "shipped" status. The cycle-67 comment block in BACKLOG.md plus the cycle-67 CHANGELOG entries enumerate what shipped. AC15's second test pin parses BACKLOG.md and asserts known-shipped entries (e.g., `GitPython unpinned`, `KB_PROJECT_ROOT call-time`, `_autouse_kb_path_sandbox no-drop guard`) are absent — a regression lock that catches an accidental re-introduction during a future merge.
- **Test pin:** `pytest tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_does_not_contain_shipped_phase_4_5_high_entries`. Behavioural assertion (parse BACKLOG, check absence of N known-shipped strings) per cycle-22 L5. The test is deliberately positive-shape: assert ABSENCE of N specific shipped strings, not "BACKLOG.md unchanged" — that lets future legitimate edits proceed without breaking the regression lock.
- **Related lessons:** user memory `feedback_migration_breaks_negatives` (one-shot migrations + legacy negative-asserts); CLAUDE.md "BACKLOG.md lifecycle" (resolved items deleted, never strikethrough); cycle-65 AC11 (pin GitPython explicitly — example of a SHIPPED entry).

### T7 (T) — Vacuous regression test pins (AC14 + AC15) pass after revert; signal corruption [NEW]

- **Class:** Tampering (test signal corruption; false sense of coverage)
- **AC origin:** AC14, AC15
- **Inheritance status:** NEW — applies to the 3 new test files introduced this cycle (`test_cycle68_graph_cache_caller_migrations.py`, `test_cycle68_httpx_pin_drift.py`, `test_cycle68_backlog_cleanup_lockin.py`).
- **Description:** Three classes of vacuous test from cycle-11 L2 / cycle-23 L2 / cycle-22 L5 / user memory `feedback_inspect_source_tests`:
  1. **Source-string scan** — `assert "kb.graph.cache.get_graph" in inspect.getsource(evolve.analyzer)` passes both before and after a revert that re-imports `build_graph` directly because the cache form is mentioned in a docstring or comment. Cycle-23 L2 divergent-fail principle.
  2. **AST guard with no behavioural pair** — `test_no_direct_build_graph_calls_in_migrated_files` (AC14) is AST-only. If the AST walker has a bug (silent empty-pass on parse error per cycle-66 T6), the test passes vacuously. The behavioural pair (`test_get_graph_cache_hit_on_repeat_call`) closes that gap.
  3. **Constraint-string scan** — `assert "0.28" in pyproject_text` (AC15) passes after a revert if the constraint is `httpx>=0.20,<0.28.0` (the literal "0.28" appears, but the meaning inverts).
- **Mitigation:** AC14 + AC15 — each test pin uses BOTH structural assertion AND behavioural assertion where possible:
  - AC14: AST guard (structural) + `kb.graph.builder.build_graph` spy on `call_count == 1` (behavioural) — behavioural pair revert-detects.
  - AC15-httpx: parse constraint, extract version specifier, assert BOTH `>=0.28` AND `<0.29` substrings present. A revert to `>=0.27` fails the first assertion; a removal of the upper ceiling fails the second.
  - AC15-backlog: assert absence of N specific shipped strings AND that the cleanup pass actually changed line count by ≥N (positive-shape behavioural delta) — protects against a revert that restores all entries.
- **Test pin:** Each cycle-68 test file MUST include at least one behavioural assertion that fails RED on revert. Verification at Step 14 by mimocoding-rescue: pick one production line being tested (e.g., the `kb.graph.cache.get_graph` call in `evolve/analyzer.py`); revert to `kb.graph.builder.build_graph`; run the test pin; assert RED. Restore. This is the divergent-fail check per cycle-23 L2.
- **Related lessons:** cycle-11 L2 / cycle-22 L5 / cycle-23 L2 (load-bearing tests, divergent-fail); cycle-66 T6 (consolidated walker silent-pass); user memory `feedback_test_behavior_over_signature`, `feedback_inspect_source_tests`.

---

## Risk ranking

Threats ranked by `likelihood × impact`. Closed-by-AC entries reflect post-cycle residual risk.

| Rank | ID | likelihood × impact | Notes |
|---|---|---|---|
| 1 | **T1** | medium × high | Inherited from cycle-67 T3. Highest implementation risk per cycle-67 R1-C10 commit-order. AC01 Popen refactor is the only structural change in cycle 68. |
| 2 | **T4** | medium × medium | Cache staleness divergence + test-spy bypass. 5 sites across 4 files; cycle-18 L1 attribute-lookup discipline. AC07/AC08/AC14 close. |
| 3 | **T2** | low × medium (CLOSED by AC03/AC04/AC12) | Inherited from cycle-67 T7. `yaml.safe_load` blocks RCE class; fallback trio + schema warning closes parse and abuse vectors. |
| 4 | **T7** | low × medium | Test signal corruption — applies to 3 new test files. Behavioural-pair discipline closes (AC14 spy, AC15 substring-pair). |
| 5 | **T5** | low × medium (CLOSED by AC09/AC15) | httpx constraint-vs-runtime drift. Range pin `>=0.28,<0.29` matches runtime assertion. |
| 6 | **T3** | low × low (CLOSED warn-mode by AC05/AC06/AC13) | Inherited from cycle-67 T12. Docstring audit; warn-only this cycle, hard-fail in cycle 69+. |
| 7 | **T6** | low × low (CLOSED by AC10/AC15) | BACKLOG cleanup. Per-deletion grep verify + regression lock test. |

**Tier escalation check:** No threat in the cycle-68 set crosses the Tier-3 threshold. T1 (Popen) is the highest-stakes item but inherits cycle-67's design lock (19 CONDITIONS). T4 (graph-cache caller migration) is mechanical with two-layer test coverage. Per requirements §"Tier classification rationale" line 18 and user memory `feedback_auto_approve` authorising Opus subagent gating, **NO Tier-3 escalation required**.

---

## Out-of-scope (verified mitigated in prior cycles)

Per cycle-7 L4 (avoid scope confusion in Step 14), Step 14 must NOT verify these and must NOT flag absence as a regression. They live in the same threat surface but are closed by cycles ≤67.

- **OOS-1 through OOS-15** from cycle-67 threat-model — same out-of-scope list applies (SSRF mitigation, `KB_PROJECT_ROOT` accessor, `AUGMENT_ALLOWED_DOMAINS` accessor, `_DEFAULT_MODEL_TIERS`, MCP error boundary, `_validate_page_id` Windows gates, TOCTOU on `rebuild_indexes`, validator-contract drift, embeddings multi-process race, conftest auto-discovery for lru_cache, `TRAFILATURA_DOWNLOAD_NO_CACHE=1`, GitPython upper bound (CVE-2026-44244 patch in scope at Step 11.5), `docs/reference/INDEX.md` existence + cycle-67 AC14 consistency check, `mcp_server.py` shim deletion).
- **OOS-16 (cycle-67 AC01-AC15 closures)** — cycle-67 shipped AC01 (`MODEL_TIERS` proxy), AC02 (graph-cache lookup-form AST walker), AC04 (`KB_STRICT_PUBLISH`), AC05 (sqlite-vec sanitization second call site), AC06 (`KB_DISABLE_VECTORS` kill-switch), AC08 (autouse decorator invariants meta-test), AC09 (snapshot paired negative-controls), AC10 (CI `--snapshot-update` reject), AC11 (`sk-ant-dummy` literal scan), AC13 (README "Non-clone install" prose), AC14 (docs INDEX consistency check), AC15 (argv-scrub design lock-in). Cycle-67 verdict APPROVED + Step 24 self-review committed at b64ed82. Cycle-68 inherits these as preconditions and does not re-verify.

---

## Dep-CVE baseline (Step 2 snapshot — DEFERRED to primary session)

Per task constraint: pip-audit baseline capture is being done in the primary Opus 4.7 session in parallel with this threat model. This subagent does NOT capture pip-audit. Cross-reference to `2026-05-08-cycle-68-pip-audit-baseline.md` (or the `.data/cycle-68/pip-audit-baseline.json` artifact) at Step 11.5 / Step 17.

**Expected drift vs cycle-67 baseline:**
- `gitpython` carry-over from cycle-67 baseline (NEW advisory CVE-2026-44244, fix 3.1.49) — cycle-68 AC09 is httpx-only; gitpython patch is a separate Step-11.5 opportunistic-patch slot.
- `mako`, `python-multipart` carry-overs from cycle-67 — same Step-11.5 slot.
- `diskcache` carry-over (no upstream patch).

Cycle 68 introduces NO new dependencies (15-AC scope is pure src/tests/CI/docs with one `pyproject.toml` constraint tightening for AC09 — does not add a new package). Therefore Step 11 PR-introduced-CVE diff is expected to contain ONLY any Step-11.5 CVE-fix patches; Step 14 verification is "no NEW advisories surfaced during the cycle wall-clock window" per cycle-22 L4 late-arrival hazard.

---

## Step 14 verifier checklist

Per cycle-22 L5, each item below maps 1:1 to one regression test (or test-class) Step 14 (mimocoding-rescue @ mimo-v2.5-pro per cycle-67 telemetry — audit role works) must verify. Format: `[T-id] [AC-origin] verification command(s)`.

- **T1, AC01+AC02+AC11:** `pytest tests/test_cycle68_cli_backend_popen.py::{test_cli_backend_popen_large_stdin_plus_large_stdout, test_cli_backend_popen_platform_kill_branch, test_cli_backend_popen_stderr_capped, test_cli_backend_popen_preserves_error_kinds}` — four behavioural assertions covering FW-1 (split-stdin), platform-aware kill grace, symmetric stderr cap, and `LLMError(kind=...)` preservation for `not_installed` / `timeout` / generic exit-code-non-zero. Verify `MAX_CLI_STDERR_BYTES = 64 * 1024` exists in `kb.config`. Divergent-fail: revert to `subprocess.run` and assert RED.
- **T2, AC03+AC04+AC12:** `pytest tests/test_cycle68_lint_yaml.py::{test_lint_yaml_rejects_malicious_payload, test_lint_yaml_file_missing_returns_empty, test_lint_yaml_parse_error_returns_empty, test_lint_yaml_io_permission_returns_empty, test_lint_yaml_schema_mixed_type_warning, test_lint_yaml_call_time_read}` — six behavioural assertions covering FW-2 (`yaml.safe_load` ONLY), fallback trio (file-not-found / parse-error / I/O-permission), schema warning (mixed-type fall-through), call-time read (no caching leak). The first test asserts `!!python/object/new:os.system ['echo OWNED']` raises `yaml.YAMLError` and DOES NOT execute `os.system` (verified via spy). Divergent-fail: change `yaml.safe_load` → `yaml.load` and assert the malicious payload test fails RED with `os.system` invocation detected.
- **T3, AC05+AC06+AC13:** `pytest tests/test_cycle68_audit_docstrings.py::{test_audit_docstrings_normal_func_requires_args_returns, test_audit_docstrings_func_with_raise_requires_raises_section, test_audit_docstrings_generator_with_raise_requires_raises_section, test_audit_docstrings_warn_only_exit_zero}` — four behavioural assertions covering Args/Returns gate, body-has-raise → Raises gate, FW-4 generator-with-raise → Raises gate, R1-F4 transition-path warn-only exit code. CI integration verified by reading `.github/workflows/ci.yml` and confirming `python scripts/audit_docstrings.py --warn-only` step present (warn-only flag explicit).
- **T4, AC07+AC08+AC14:** `pytest tests/test_cycle68_graph_cache_caller_migrations.py::{test_no_direct_build_graph_calls_in_migrated_files, test_get_graph_cache_hit_on_repeat_call}` — AST guard + behavioural cache-hit assertion. AST walker parses `evolve/analyzer.py`, `graph/export.py`, `mcp/browse.py`, `query/engine.py`; asserts ZERO `ast.Call` whose `func.attr == "build_graph"` outside `kb.graph.cache` module. Behavioural test spies on `kb.graph.builder.build_graph`; first `kb.graph.cache.get_graph(wiki)` call → builder invoked (call_count=1); second call → cache hit (call_count=1). Divergent-fail: revert one migrated call site to `kb.graph.builder.build_graph(wiki_dir)` and assert the AST guard fails RED on that file.
- **T5, AC09+AC15:** `pytest tests/test_cycle68_httpx_pin_drift.py::test_pyproject_httpx_pin_has_explicit_ceiling` — parses `pyproject.toml`, locates httpx constraint, asserts BOTH `>=0.28` AND `<0.29` substrings present in the version specifier. Divergent-fail: revert to `httpx>=0.27` and assert the test fails RED on the missing `<0.29` ceiling.
- **T6, AC10+AC15:** `pytest tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_does_not_contain_shipped_phase_4_5_high_entries` — parses `BACKLOG.md`, asserts known-shipped entries from cycle-67 cleanup pass (`GitPython unpinned`, `SSRF on URL→external CLI`, `KB_PROJECT_ROOT call-time`, `_autouse_kb_path_sandbox no-drop guard`, `hardcoded lru_cache list`, `_DEFAULT_MODEL_TIERS dual mechanism`, `AUGMENT_ALLOWED_DOMAINS`, `MCP error responses raw tracebacks`, `_check_no_secrets_on_argv self-DoS`, `graph/cache.py 6th-caller drift`, `tests/test_cycle64_snapshots.py tautology`, `CI sk-ant-dummy grep`, `docs/reference/ INDEX.md`, the 3 cycle-68 carry-over entries, `auto_publish_after_compile exceptions swallowed`, `kb.query.hybrid KB_DISABLE_VECTORS=1`, `README KB_PROJECT_ROOT bootstrap`, `compile/compiler.py:645 validator drift`, `mcp/app.py:230 Windows trailing-dot`) are ABSENT. Divergent-fail: re-add one entry to BACKLOG.md and assert the test fails RED on that string.
- **T7, AC14+AC15 (cross-cutting):** Step 14 must verify each new test file has at least one behavioural (not signature-only) assertion. For `test_cycle68_graph_cache_caller_migrations.py`, verify the cache-hit spy test exists. For `test_cycle68_httpx_pin_drift.py`, verify the constraint parser asserts BOTH bounds. For `test_cycle68_backlog_cleanup_lockin.py`, verify the absence-list contains ≥10 entries.

**Cross-AC verifications (Step 14 must also confirm):**

- Full pytest suite green (3248+ baseline per CLAUDE.md Quick Reference + ~75 new cycle-68 tests; expected ~3320+ post-cycle) per cycle-22 L3 — NOT an isolated subset.
- Coverage delta: touched-file ≥90%, repo-total regression ≤0.5pp per requirements §"Definition of done" line 161.
- Workflow + dep changes commit BEFORE security-class src per cycle-67 R1-C10 / FW-6 ordering: AC09 → AC10 → AC07 → AC08 → AC02 → AC11 → AC01 → AC03 → AC04 → AC12 → AC05 → AC06 → AC13 → AC14 → AC15.
- `D:/Projects/llm-wiki-flywheel/.venv/Scripts/pip-audit.exe --format=json` against final HEAD venv shows ≤baseline + 0 NEW advisories (existing carry-overs `gitpython`, `mako`, `python-multipart`, `diskcache` may persist; Step-11.5 patches handle gitpython/mako/python-multipart per SECURITY.md cadence).
- `git ls-files BACKLOG.md` line-count strictly DECREASED vs `origin/main` HEAD (positive-shape delta per T7 mitigation — protects against AC10 revert).

**Step 14 must NOT verify (per cycle-7 L4 / out-of-scope list above):**

- Anything in OOS-1 through OOS-15 from cycle-67 threat-model.
- Anything closed by cycle-67 AC01-AC15 (cycle-67's own threat surface; OOS-16 above).
- pip-audit baseline capture itself (primary session owns this artifact in parallel with this document).

---

## Verdict

**APPROVE** — Tier-2 cleanup with three carry-over threats (T1, T2, T3) inheriting cycle-67's design lock (19 CONDITIONS) and four NEW threats (T4, T5, T6, T7) covering the cycle-68-specific surface (graph-cache caller migration, httpx pin tightening, BACKLOG cleanup, regression test signal hardening). All 7 threats map to behavioural test pins per cycle-23 L2 + user memory `feedback_test_behavior_over_signature`. No Tier-3 escalation, no new trust boundaries, no architecture changes.

The cycle-68 implementation can proceed against cycle-67's 19 CONDITIONS plus the 4 new test-pin contracts surfaced here:
1. AC07/AC08 attribute-lookup form per cycle-18 L1 (T4 mitigation).
2. AC09 explicit ceiling `>=0.28,<0.29` matched to runtime assertion (T5 mitigation).
3. AC10 per-deletion grep-verify against cycle-N CHANGELOG ≤67 (T6 mitigation).
4. AC14/AC15 behavioural-pair discipline — every new test file MUST include at least one assertion that fails RED on production revert (T7 mitigation).

These four contracts plus cycle-67's 19 CONDITIONS are the locked Step-7 plan input.
