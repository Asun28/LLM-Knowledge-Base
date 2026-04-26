# Cycle 37 — Threat Model

**Date:** 2026-04-26
**Cycle:** 37 — POSIX symlink security gap fix + requirements.txt split
**Authored:** Primary session (cycle-36 L2 — tightly scoped, primary holds context from cycle-36 close)

## Trust boundaries

1. **`raw/` ↔ filesystem-outside-raw/** — Files inside `raw/` are user-curated KB sources. Files outside `raw/` (project root, /etc, %APPDATA%, etc.) are NOT trusted KB content. Symlinks crossing this boundary MUST be detected + rejected before content read.
2. **`requirements*.txt` ↔ pip resolver** — Files written here become the dep contract for `pip install`. Malformed content (broken `-r` reference, missing line, version-pin typo) becomes a CI / deploy failure.
3. **CI workflow ↔ user** — Each workflow run that lands `red` on `main` or on a tracked PR is user-visible noise (Dependabot warnings, email digests). Cycle-36 L1 mandates one new CI dimension per cycle; cycle 37 introduces ZERO.

## Data classification

- **Project secrets** — `.env`, credentials, anything outside `raw/` that the system isn't supposed to send to the LLM. The cycle-37 production fix (AC1) prevents these from being read via symlink-in-raw escape.
- **KB sources** — `raw/articles/*.md`, `raw/captures/*.md`, etc. Already trusted; the fix preserves legitimate intra-`raw/` symlinks (AC3).
- **Build dependencies** — `requirements*.txt` content. Public; no secrets.

## Authn / authz

Out of scope. The cycle-37 fix is a path-containment check; no authn/authz boundary changed.

## Logging / audit

- AC1: When a symlink rejection fires, the existing `logger.warning("Source symlink escapes raw/ directory — skipping: %s -> %s", ...)` line at `context.py:91` runs. No new logging surface; existing log line now actually fires (was dead code pre-AC1).
- AC4-AC8: No logging changes — pip resolver handles requirements files at install time, no application-level audit emission.

## Threats (T1-T7)

### T1 — POSIX symlink containment bypass (AC1 closes)

**Pre-cycle-37 state:** `pair_page_with_sources` has dead-code symlink containment check. `Path.resolve()` on line 70 follows symlinks before `is_symlink()` is checked on line 86, so `is_symlink()` always returns False on the resolved path.

**Attack vector:** A KB user (or compromised KB user account) creates a symlink at `raw/articles/foo.md → /home/user/.config/secrets.txt`. They add `source: ["raw/articles/foo.md"]` to a wiki page's frontmatter. When `pair_page_with_sources` runs (during review context generation, e.g., `kb_review_page` MCP tool), the dead-code containment check is bypassed and the secret file's content is embedded in the review context — sent to the LLM, returned to the caller, possibly logged.

**Containment check needed:** `is_symlink()` MUST be checked on the unresolved candidate path; if true, the resolved target MUST be verified inside `raw_dir.resolve()` BEFORE any read.

**Mitigation (AC1):** Reorder: capture `is_symlink()` on candidate path FIRST, then `.resolve()`, then containment check on resolved target. Existing skip-with-error-row UX preserved.

**Verification (AC2):** `test_qb_symlink_outside_raw_rejected` (`tests/test_phase45_theme3_sanitizers.py:409`) — pre-AC1 the test was `skipif(os.name != "nt")` because POSIX run revealed the bug. AC2 drops the skipif. Test asserts `s.get("content") != "SECRET DATA"` — divergent-fail per cycle-24 L4: revert AC1 → secret read → assertion flips → test fails.

**Verification (AC3):** New `test_qb_symlink_inside_raw_accepted` — symlink inside `raw/articles/foo.md → raw/sources/foo.md` resolves to a target STILL within `raw_dir`. Asserts content IS read. Pins legitimate-symlink behavior; revert AC1 → no change in this case (target-within-raw test still passes).

### T2 — Requirements split breaks existing `pip install -r requirements.txt` workflows (AC7 mitigates)

**Attack vector:** Existing CI configs / Dockerfiles / contributor docs do `pip install -r requirements.txt`. If cycle 37 deletes content from `requirements.txt` and moves it to per-extra files without preserving the legacy invocation, every existing pipeline breaks on next pull.

**Mitigation (AC7):** `requirements.txt` becomes a SHIM: `-r requirements-runtime.txt` + `-r requirements-dev.txt`. Existing `pip install -r requirements.txt` still installs the same superset. New users can opt into lean runtime (`pip install -r requirements-runtime.txt`) or per-extra (`pip install -r requirements-runtime.txt -r requirements-hybrid.txt`).

### T3 — `-r requirements-runtime.txt` reference breaks if file missing (AC9 mitigates)

**Attack vector:** A future commit deletes or renames `requirements-runtime.txt`. Every per-extra file's `-r requirements-runtime.txt` first line then errors out at `pip install`. Silent regression until next dep install.

**Mitigation (AC9):** Regression test asserts all 6 new files exist + each per-extra file's first non-comment line is `-r requirements-runtime.txt`. Revert AC4 (delete `requirements-runtime.txt`) → AC9's file-existence check fails.

### T4 — Cycle-35 L8 floor pin lost in split (AC6 + AC9 mitigate)

**Attack vector:** Cycle 35 added `langchain-openai>=1.1.14` to `pyproject.toml [eval]` extra to close GHSA-r7w7-9xr2-qq2r. If the per-extra `requirements-eval.txt` doesn't preserve this pin, the next `pip install -r requirements-eval.txt` resolves to 1.1.10 (vulnerable).

**Mitigation (AC6):** Floor pin `langchain-openai>=1.1.14` MUST appear in `requirements-eval.txt`.

**Verification (AC9):** Regression test greps `requirements-eval.txt` for `langchain-openai>=1.1.14`. Revert AC6 → grep fails → test fails.

### T5 — Cycle-22 L4 mid-cycle CVE arrival (Step 11 PR-CVE diff mitigates)

**Pre-cycle-37 state (baseline 2026-04-26):** 4 open Dependabot alerts (3 litellm + 1 ragas) + 4 pip-audit findings (diskcache + 1 of 3 litellm GHSAs + pip + ragas). All Class A (existing on main); none has an actionable upstream fix that doesn't also break our `click==8.3.2` pin.

**Risk:** A NEW advisory could land between this Step-2 baseline capture and Step-11 verification. Cycle-22 L4: must run pip-audit + Dependabot diff at Step 11.

**Mitigation:** Step 11 PR-CVE diff against baseline. If `INTRODUCED` set is non-empty AND fix is available WITHOUT breaking transitive constraints, patch in Step 11.5; otherwise add to BACKLOG cycle-38.

### T6 — Symlink test cross-platform skipif accidentally over-disables (AC2 mitigates)

**Attack vector:** AC2 drops `skipif(os.name != "nt")`. The remaining `skipif` is `os.name == "nt" and not os.environ.get("ALLOW_SYMLINK_TESTS")` — Windows-without-elevation is still skipped (correct: symlink creation requires elevated privileges on Windows). On POSIX (where most CI runs), the test now runs. On Windows-without-elevation (developer local), still skipped. On Windows-with-elevation (CI matrix in cycle 38+), runs.

**Verification:** Pre-AC2 the test had TWO conflicting skipif markers (cycle-36 added a Windows-only marker; the original was Windows-elevation marker). Post-AC2 only the Windows-elevation marker remains. Local Windows (no `ALLOW_SYMLINK_TESTS`) keeps the test skipped — same observable behavior.

### T7 — Requirements split changes installable surface (AC8 mitigates)

**Attack vector:** Users following old README install instructions land in a broken state if the install commands are stale.

**Mitigation (AC8):** README install section updated to document both old (`pip install -r requirements.txt`) AND new (`pip install -r requirements-runtime.txt`) options. Old commands still work via AC7 shim.

## Dep-CVE baseline summary (Step 2 capture)

**Source 1 — `gh api .../dependabot/alerts`:** 4 open alerts: `GHSA-v4p8-mg3p-g94g` (litellm, high, fix=1.83.7), `GHSA-r75f-5x8p-qvmc` (litellm, critical, fix=1.83.7), `GHSA-xqmj-j6mv-4862` (litellm, high, fix=1.83.7), `GHSA-95ww-475f-pr4f` (ragas, low, fix=null).

**Source 2 — `pip-audit` (live `.venv`):** 4 vulns: diskcache `CVE-2025-69872` (no fix), litellm `GHSA-xqmj-j6mv-4862` (fix blocked by click<8.2), pip `CVE-2026-3219` (no fix), ragas `CVE-2026-6587` (no fix).

**Class-A summary:** 4 advisories carrying over from main; none actionable in cycle 37 (3 litellm blocked by click<8.2; ragas + diskcache + pip have null upstream fix). All already in `SECURITY.md` + workflow `--ignore-vuln`.

**Class-B preview:** None at Step-2 time. Step-11 will diff branch baseline against this snapshot.

**Files:** `D:/Projects/llm-wiki-flywheel/.data/cycle-37/alerts-baseline.json` + `cve-baseline.json` (gitignored per cycle-22 L1 + cycle-34 .data/ pattern).

## Step-11 verification checklist (auto-derived from threats)

- [ ] T1: AC1 implemented (`is_symlink()` BEFORE `.resolve()`); AC2+AC3 tests pass on POSIX
- [ ] T2: AC7 `requirements.txt` shim valid; `pip install -r requirements.txt` succeeds
- [ ] T3: AC9 file-existence + line-content regression tests pass
- [ ] T4: AC6 + AC9 verify `langchain-openai>=1.1.14` in `requirements-eval.txt`
- [ ] T5: PR-CVE diff vs baseline shows empty INTRODUCED set
- [ ] T6: Test skipif markers correctly profile (POSIX runs, Windows-no-elevation skipped)
- [ ] T7: README updated with both old + new install commands
