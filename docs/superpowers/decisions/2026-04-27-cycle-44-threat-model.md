# Cycle 44 Threat Model + Dep-CVE Baseline

**Date:** 2026-04-27
**Branch:** cycle-44-batch
**Skip-when applies:** pure internal refactor (file splits + test folds + atomic-write helper consolidation). No new trust boundary, no new I/O surface, no new authn/authz. Captured below as a Step-11 verification checklist for refactor-class correctness invariants only — no full DeepSeek dispatch.

---

## Trust boundaries (unchanged)

- MCP tool boundary: 29 tools across `kb/mcp/{app,browse,core,health,quality}.py`. Cycle 44 splits `core.py` into `core.py` + `ingest.py` + `compile.py`; tool count must remain 29 and registration must fire on `import kb.mcp` per cycle-23 L5.
- CLI boundary: 24 subcommands in `src/kb/cli.py`. No CLI changes in cycle 44.
- Filesystem write boundary: `kb.utils.io.atomic_text_write` is the canonical write helper. M4 collapses `kb.capture._exclusive_atomic_write` into it via `exclusive=True`. Both contracts (crash-atomicity tempfile+rename for default; `O_EXCL` slug-collision for exclusive) MUST be preserved (cycle-15 L1).
- Lint pipeline boundary: `kb.lint.runner.run_all_checks` enumerates check functions registered in `kb.lint.checks`. M1 splits `checks.py` into a package; the runner's enumeration semantics MUST be preserved.

## Data classification (unchanged)

No new sensitive data flows. Module splits do not add logging, persistence, or telemetry. Vacuous-test upgrades in tests/ touch only test-fixture filesystem state under `tmp_path`.

## Refactor-class correctness invariants (Step-11 checklist)

T1. **Public import contract preserved** (cycle-23 L5). Every test or caller using `from kb.lint.checks import X`, `from kb.lint.augment import Y`, `from kb.mcp.core import Z` continues to resolve correctly. `__init__.py` re-export shims with `# noqa: F401` (C42-L5) for every former top-level symbol.

T2. **Monkeypatch target migration complete** (C42-L3). Every test using `monkeypatch.setattr("<module>.<func>", ...)` or `patch("<module>.<func>")` against a moved symbol updates its target string to the NEW canonical module. Re-exports do NOT make patches transparent. The plan must enumerate ALL patch sites BEFORE moving any symbol — string-form AND reference-form (cycle-19 L1).

T3. **`atomic_text_write` contract preservation** (cycle-15 L1, cycle-21 L4):
   - `exclusive=False` (default): preserves tempfile + `os.replace` crash-atomicity; PIPE_BUF byte bounds (cycle-18 L4); fsync semantics if any.
   - `exclusive=True`: preserves `O_CREAT | O_EXCL | O_WRONLY` slug-collision detection; raises `FileExistsError` on conflict.
   - The unified function MUST raise `FileExistsError` for `exclusive=True` AND atomic-replace existing files for `exclusive=False`.

T4. **MCP tool registration on import** (cycle-23 L5). After M3 split, `from kb.mcp import mcp` must yield a fully-registered FastMCP instance — all 29 `@mcp.tool()` decorators fire via the `__init__.py` `__getattr__` lazy-registration path or equivalent. Test: `len(mcp._tool_manager._tools) == 29`.

T5. **Lazy module-top reads** (cycle-19 L2). `lint/augment/manifest.py` and `lint/augment/rate.py` MUST NOT perform module-top `read_text()` / `json.load(open(...))`. Wrap any prior module-top JSON state in `_get_X()` lazy accessors. Test: `import kb.lint.augment.manifest` with no `WIKI_DIR` configured does not raise.

T6. **Vacuous-test behavioral coverage** (cycle-16 L2 + C40-L3 + C41-L1). New behavioral tests for AC29 (mtime-collision) and AC30 (file_lock PID recycling) MUST exercise the production code path such that a revert of the underlying logic FAILS the test. Self-check: replace the production helper with a no-op and confirm the test fails.

T7. **No fenced-block / sentinel evasion** (cycle-24 L2, cycle-3 ZW-strip). N/A — no markdown/sentinel parsing changes in cycle 44.

T8. **Path traversal** (cycle-7 L4 + cycle-21 L2 + C33-L1). N/A — no path validators changed.

T9. **Lock acquisition order** (cycle-15 L1 + cycle-18 L1). N/A — no locking discipline changes; M4 atomic_text_write keeps existing semantics.

## Logging / audit (unchanged)

No new audit emissions. `kb.utils.io.atomic_text_write` retains existing logger usage. `kb.lint.augment` package retains existing `logger.info` / `logger.warning` calls in their respective submodules.

## Authn / authz (unchanged)

N/A. No authentication or authorization surface in cycle 44.

---

## Dep-CVE baseline (captured 2026-04-27 22:48 PT)

### pip-audit (4 vulns — all pre-existing per cycle-32+ BACKLOG)

| Pkg | Advisory | Fix | Status |
|---|---|---|---|
| diskcache | CVE-2025-69872 | none | no upstream patch (Phase 4.5 MEDIUM, dev-only via trafilatura robots.txt cache; zero direct kb imports) |
| litellm | GHSA-xqmj-j6mv-4862 | 1.83.7 | BLOCKED by click==8.3.2 transitive (Phase 4.5 MEDIUM, dev-eval-only ragas dep; zero `import litellm` in src/kb) |
| pip | CVE-2026-3219 | none confirmed | tooling-only; pip 26.1 published but advisory still shows `patched_versions: null` (cycle-22 L4 conservative posture per BACKLOG) |
| ragas | CVE-2026-6587 | none | dev-eval-only; zero direct kb imports (Phase 4.5 MEDIUM) |

### Dependabot (4 open alerts — all pre-existing)

| ID | GHSA | Severity | Pkg | Fix |
|---|---|---|---|---|
| 12 | GHSA-95ww-475f-pr4f | low | ragas | none |
| 13 | GHSA-xqmj-j6mv-4862 | high | litellm | 1.83.7 (blocked) |
| 14 | GHSA-r75f-5x8p-qvmc | critical | litellm | 1.83.7 (blocked) |
| 15 | GHSA-v4p8-mg3p-g94g | high | litellm | 1.83.7 (blocked) |

The 3 litellm advisories are Class A (existing on `main`) and ALL gated on the same `click<8.2` transitive. Per BACKLOG, narrow-role mitigation: `grep -rnE "import litellm|from litellm" src/kb` confirms zero runtime imports — proxy endpoints unreachable. **Cycle 44 will NOT bump litellm** (would force click downgrade and break cycle 31/32 CLI wrappers). Step-11.5 will re-check post-implementation; the same blocked state is expected.

The pip + diskcache + ragas advisories have no upstream patch as of 2026-04-27. Step-11.5 will re-check; expected unchanged.

### Class B (PR-introduced) baseline expectation

Cycle 44 does NOT add or bump any dependency. Class B diff at Step 11 SHOULD be empty. If Step-11 surfaces a NEW advisory, it is a cross-cycle late-arrival per cycle-22 L4 — block at Step 11 only if the new fix is unblocked AND the fix wouldn't break parallel cycle 31/32 CLI work.

Baseline files saved to:
- `.data/cycle-44/cve-baseline.json` (pip-audit, 21 KB)
- `.data/cycle-44/alerts-baseline.json` (Dependabot, 0.4 KB)
