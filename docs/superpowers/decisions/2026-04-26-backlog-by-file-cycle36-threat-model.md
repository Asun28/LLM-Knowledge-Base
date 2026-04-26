# Cycle 36 — Threat Model

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle36`
**Theme:** Test + CI infrastructure hardening. NO `src/kb/` source code changes. NO new runtime behavior.
**Audience:** Step-5 design-gate and Step-11 security-verify (Codex) subagents.

The cycle's only mutations are: (a) test markers / skips / fixtures, (b) `.github/workflows/ci.yml` (drop `continue-on-error`, add ubuntu matrix, refresh `--ignore-vuln`), (c) `pyproject.toml` `[tool.pytest.ini_options]` (`timeout = 60` + `pytest-timeout` dep), (d) NEW `requirements-*.txt` split files, (e) `SECURITY.md` advisory row, (f) docs. Because no production code changes, the relevant attack surface is **the merge gate itself** — the threat model centres on "what could let a bad PR pass green-checkmark CI" and "what could the cycle-36 changes break in the gate semantics."

---

## Trust boundaries

```
+---------------------------------------------------------------+
|  ATTACKER ZONE — public PR contributors (incl. fork PRs)       |
|  - controls: branch contents, PR description, fork repo state  |
|  - cannot: read repo secrets (permissions: read-all + no       |
|    pull_request_target), push to main without review           |
+---------------------------+-----------------------------------+
                            | git push / pull_request event
                            v
+---------------------------------------------------------------+
|  GITHUB ACTIONS RUNNER (ubuntu-latest + windows-latest)        |
|  - GITHUB_TOKEN: read-all                                       |
|  - env: ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only   |
|  - third-party actions pinned by major (v6) — see T3           |
|  - executes: pip install, ruff, pytest, pip-audit, build       |
+---------------------------+-----------------------------------+
                            | merge gate result (green/red)
                            v
+---------------------------------------------------------------+
|  MAINTAINER ZONE — branch protection, manual review            |
|  - sees: aggregated check status                                |
|  - signs off: PR review + merge                                |
+---------------------------+-----------------------------------+
                            | merge to main
                            v
+---------------------------------------------------------------+
|  RELEASED PACKAGE — pip install + downstream users             |
|  - bears the cycle-36 quality claims (skipif coverage,         |
|    pytest-timeout SLA, pip-audit clean against documented      |
|    --ignore-vuln list)                                          |
+---------------------------------------------------------------+
```

The cycle-36 fixes change *only* the middle band: which tests run on which OS, when pytest aborts, and whether the gate is strict. The trust boundary at the top (read-all permissions, no `pull_request_target`, no `secrets.*`) inherited from cycle-34 is preserved unchanged.

---

## Data classification

| Asset | Classification | Where it lives | Cycle-36 exposure |
|---|---|---|---|
| Test fixtures (`tmp_wiki`, `tmp_project`, `tmp_kb_env`) | non-sensitive, ephemeral | pytest tmp dirs, deleted post-run | none — only marker changes |
| `.env` (real `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`) | SECRET | developer workstations, gitignored | none — CI never sees `.env` |
| CI dummy `ANTHROPIC_API_KEY` (`sk-ant-dummy-key-for-ci-tests-only`) | NON-SECRET intentionally fake | `.github/workflows/ci.yml` line 38, plain text | reused. AC6 must guarantee tests that would actually call Anthropic skip when this prefix is detected (T7) |
| `pip-audit` JSON output | non-sensitive (CVE IDs are public) | GHA logs (90-day retention) | refreshed each run |
| `.data/cycle-36/alerts-baseline.json` | non-sensitive | gitignored under `.data/` | NEW snapshot of 4 open Dependabot alerts (3 litellm, 1 ragas) |
| `pyproject.toml` `[project.optional-dependencies]` | non-sensitive but build-critical | repo root, version-controlled | unchanged content; mirrored into NEW `requirements-*.txt` split files (drift risk → T4) |
| `SECURITY.md` "Known Advisories" table | non-sensitive but trust-critical | repo root | adds 4th litellm row `GHSA-v4p8-mg3p-g94g`; if drift between table + workflow `--ignore-vuln` (T5) the gate falsely passes/fails |
| GHA logs (pytest stdout, pip-audit, build) | non-sensitive | github.com retention | richer after AC8 strictness (failures now visible vs swallowed) |

No new SECRET-classified asset is introduced. The only zone-crossing data is the `.data/cycle-36/alerts-baseline.json` snapshot, but it is gitignored and contains only public CVE/GHSA IDs.

---

## Authn / authz

- **GitHub Actions OIDC**: not used. The workflow has zero `secrets.*` references and no `id-token: write`. No token federation outward — good least-privilege baseline; cycle-36 preserves this. Adding ubuntu-latest to the matrix (AC12) does NOT change the permission set.
- **`permissions: read-all`** (top of `ci.yml`): explicit narrowing. Forks cannot escalate even if a malicious PR-from-fork lands. Cycle-36 must NOT add any write-scope permission; if AC9 needs to publish a CVE artifact, attach it as a step output, not as a release upload.
- **Dependabot**: separate identity, files PRs against `requirements.txt` / `pyproject.toml` extras. Dependabot PRs go through the same merge gate, so cycle-36's strict-pytest gate (AC8) automatically extends to Dependabot. There is no Dependabot auto-merge configured — every dep bump is human-reviewed.
- **`secrets.*` references**: zero, audited via `grep -nE "secrets\." .github/workflows/ci.yml`. Cycle-36 adds none. The dummy `ANTHROPIC_API_KEY` is plain `env:` not `${{ secrets.* }}`.
- **Maintainer authn**: branch protection on `main`, signed commits enforced (`Asun28` git config). Cycle-36 ships behind a normal feature-branch PR — no policy bypass.

---

## Logging / audit

- **GHA logs**: 90-day default retention. Cycle-36 AC8 makes failures *visible* (no more swallowed pytest exit codes). Cycle-36 AC3 surfaces hung tests with a 60 s timeout traceback rather than 6-hour silent kill.
- **pytest output**: AC8 strict-gate means stdout/stderr now correlate to the pass/fail decision. Cycle-36 should NOT mute pytest output (no `-q -q` super-quiet, no `--no-header`).
- **pip-audit JSON**: each CI run produces a fresh report; the `--ignore-vuln` list is checked into `ci.yml` so any silent suppression is reviewable in `git diff`.
- **CHANGELOG audit trail**: AC21 (`CHANGELOG.md` Quick Reference) + AC22 (`CHANGELOG-history.md` per-cycle detail) form the canonical record. The cycle-32 lesson (skip-marker delete-only) ensures resolved BACKLOG items leave a CHANGELOG breadcrumb — AC23 enforces this.
- **`.data/cycle-36/alerts-baseline.json`**: gitignored snapshot is the durable evidence for Step-11 dep-CVE diff. Step 11 verify diffs branch's pip-audit against this baseline (per `SECURITY.md` Re-check Cadence Step 11).

The audit trail is sufficient: any future "why did skipif X land?" question is answered by `git blame` on the marker + `CHANGELOG-history.md` + the requirements/threat-model/design docs in `docs/superpowers/decisions/`.

---

## Threats

### T1 — Skip markers letting test BUGS slip through

**Description.** AC2 marks `test_cycle23_file_lock_multiprocessing.py` with `skipif(os.environ.get("CI") == "true", ...)`. AC5 may add similar wiki-content `skipif`. AC6 adds `skipif(not requires_real_api_key(), ...)` on ~4 test files. AC11 adds `skipif(sys.platform != "win32", ...)` on ≤6 tests. The risk: a regression in `kb.utils.io.file_lock` (T1's leading example) now ships green because the multiprocessing regression test never actually runs in CI on either OS — POSIX runner skips because `requires_real_api_key()` is unrelated, Windows runner skips because of the `CI == "true"` guard. The test exists, looks reassuring on `pytest --collect-only -q`, but adds zero runtime coverage.

**Mitigation in this cycle.**
1. AC2 prefers a **fix over skip** when the multiprocessing hang root cause is identifiable (per requirements line 40). The skipif is the fallback, not the default.
2. AC2 narrows the skip to `CI == "true"` so local `pytest` still exercises the multiprocessing path on every developer machine. Cycle-23 verified the test passes locally on Windows.
3. NEW `tests/test_cycle36_ci_hardening.py` (per requirements blast-radius line 137) adds **regression tests for the skipif markers themselves** — that the markers parse, that the predicate functions return the expected booleans, and that the affected test IDs still appear in `pytest --collect-only` output (signature-only checks here are acceptable because the production code path is the marker plumbing itself, per `feedback_test_behavior_over_signature.md` exception clause).
4. AC11 cross-OS skipif markers are on tests asserting Windows-only path semantics; on POSIX the production code paths under test simply do not exist (e.g., backslash normalisation). Skip is correct, not a coverage gap.

**Step 11 verification.**
- Grep `tests/` for every `@pytest.mark.skipif(` added in this PR; for each, confirm the inverse-condition path *also* has at least one passing test that exercises the same production code (e.g., the cross-process file-lock invariant is covered by single-process `test_cycle23_rebuild_indexes.py` thread-based variant).
- Diff `pytest --collect-only -q | wc -l` before vs after the PR — net change should match the count claimed in `CHANGELOG.md` AC21 (Items / Tests delta).
- Confirm `requires_real_api_key()` returns `False` when `ANTHROPIC_API_KEY` is unset OR matches the dummy prefix, and `True` only on a developer's real-key environment. Codex should grep for the helper definition and read its body.

### T2 — pytest-timeout default too aggressive → false-positive merge blocks

**Description.** AC3 wires `[tool.pytest.ini_options] timeout = 60` and adds `pytest-timeout >= 2.3` to `[dev]` extras. Some legitimate tests (PageRank computation, integration tier, `tmp_kb_env` setup that compiles a wiki) may exceed 60 s on slower CI runners (especially `ubuntu-latest`'s shared-tier CPU vs `windows-latest` dedicated). Result: strict gate (AC8) starts false-blocking PRs unrelated to the timeout-target test. Worse, contributors learn to rerun-until-green, eroding the gate's signal value.

**Mitigation in this cycle.**
1. AC3 explicitly preserves the `@pytest.mark.timeout(N)` per-test override mechanism. Tests known to need >60 s (the cycle-23 multiprocessing test uses 15 s + 10 s + 5 s = 30 s typical, but `test_backlog_by_file_cycle7.py` shows 20 s subprocess timeouts already) get an explicit override.
2. Step-4 design eval (open question 2 in requirements) decides the default. If 60 s is too aggressive, propose 120 s as the default with a follow-up cycle to tighten.
3. The `integration` marker tier is an alternative escape hatch — slow integration tests can be deselected from the default `pytest -q` and run on a separate `pytest -m integration` step where the timeout is higher or disabled.
4. Probe AC4 (local `pytest -q` after AC1+AC2+AC3) catches false positives before they reach CI; if any test trips 60 s locally, raise the default or mark per-test before opening the PR.

**Step 11 verification.**
- Grep tests for the slowest legitimate operations: `mp.Process`, `subprocess.Popen`, full PageRank, `tmp_kb_env` setup with >100 pages. For each, confirm there's either an explicit `@pytest.mark.timeout(N)` or the operation is bounded well under 60 s.
- Run `pytest --collect-only -q` and verify `pytest-timeout` appears in `pip list` (i.e., it's actually installed via `[dev]` extras, not silently missing — silent absence would mean `timeout = 60` is a no-op, hiding the protection).
- Confirm at least one CI run after AC8 strictness has flushed all 2985+ tests within the timeout budget.

### T3 — CI workflow injection / supply-chain (PR-from-fork, ubuntu matrix, third-party action versions)

**Description.** Adding `ubuntu-latest` to the matrix (AC12) doubles the CI surface — any compromised third-party action tag (`actions/checkout@v6`, `actions/setup-python@v6`) now executes on a second runner. PR-from-fork builds run with read-only token (good), but a malicious fork PR could try to exfiltrate the dummy `ANTHROPIC_API_KEY` (worthless — already public-prefix), inject malicious deps via a poisoned `pyproject.toml` change, or attempt `pip install --extra-index-url=evil` via PR-edited `requirements.txt`. The cycle-36 NEW `requirements-*.txt` files (AC14-AC16) are 6 new attack surfaces a malicious PR could subtly tamper with.

**Mitigation in this cycle.**
1. Cycle-34 inheritance: `permissions: read-all`, no `pull_request_target`, no `secrets.*`. Cycle-36 preserves all three.
2. Pinning posture: `actions/checkout@v6` and `actions/setup-python@v6` are major-version tags. **NOT pinned to commit SHA** — a known supply-chain trade-off. Cycle-36 does not change this; if Step-5 design gate decides to upgrade pinning to SHA, that's a separate scoped change, not a cycle-36 prerequisite (deferred — out of scope, BACKLOG entry C36-T3).
3. Concurrency cancel-in-progress (`ci.yml` line 18-20) inherited from cycle-34 limits per-PR runtime cost; doubling matrix doesn't multiply cost as much as feared.
4. AC14-AC16 new `requirements-*.txt` files are reviewed in the same PR diff that adds them. The strict gate (AC8) means any Dependabot or contributor PR that mutates these files runs full pytest + pip-audit on both OSes. A malicious extra-index-url would be visible in PR diff.
5. `pip-audit` step has NO `--extra-index-url` and NO `--index-url` — only the default PyPI. Mutations to `requirements*.txt` cannot covertly route resolution.

**Step 11 verification.**
- Diff `.github/workflows/ci.yml` — confirm no new `secrets.*`, no `pull_request_target`, no new `actions/*` references beyond `checkout@v6` + `setup-python@v6` (any new third-party action requires explicit Step-5 sign-off).
- Confirm `permissions: read-all` survived AC12's matrix addition (matrix is a `strategy:` field; permissions is at the job level).
- Diff each new `requirements-*.txt` against `pyproject.toml` extras — pins must be a strict subset; no extra packages, no extra-index-url, no `git+https://` URLs.
- Verify ubuntu-latest run reads the same `--ignore-vuln` set as windows-latest run (i.e., the strategy doesn't accidentally skip the pip-audit step on one OS).

### T4 — `requirements-*.txt` drift from `pyproject.toml` extras (cycle-35 L8 floor-pin gap)

**Description.** Cycle-35 lesson L8: the resolver picked `langchain-openai 1.1.10` even though `requirements.txt` pinned `1.1.14` locally, because the `pyproject.toml [eval]` extra had no floor pin — only `requirements.txt` did. `pip install -e '.[eval]'` does NOT consult `requirements.txt`; it only reads `pyproject.toml` extras. AC14-AC16 introduce 5 new `requirements-*.txt` files that *each* duplicate the pyproject pin set. Drift between the 6 files and `pyproject.toml` extras can produce: (a) silent CVE re-introduction (Step-2 baseline shows 4 alerts; if a `requirements-*.txt` lacks a floor pin newly added to pyproject, the file ships outdated), (b) reproducibility surprises ("install path A passes, install path B fails CI even on identical commit"), (c) maintenance burden (6 files to update on every dep bump).

**Mitigation in this cycle.**
1. AC15 explicitly documents the cycle-35 L8 floor-pin (`langchain-openai>=1.1.14`) must appear in `requirements-eval.txt`.
2. AC16 keeps `requirements.txt` (the existing full-dev superset) authoritative for backwards compat — the new 5 files are **additive views**, not replacements. The drift surface is between *each new file* and `pyproject.toml`; existing tests that pin `requirements.txt` semantics (e.g., `test_env_example.py`, `test_cycle32_dependabot_pin.py` if present) continue to work.
3. NEW `tests/test_cycle36_ci_hardening.py` (per blast-radius) should add a parsing test that for each `requirements-<extra>.txt`, every package matches a corresponding `pyproject.toml [project.optional-dependencies] <extra>` entry (semver-compatible). This is a behavior test, not a signature test.
4. Step-5 design open question 6: "do `requirements-*.txt` `-r requirements-runtime.txt` or self-contained?" Self-contained duplicates pins (more drift surface) but simpler one-file install. `-r`-chained reduces drift but breaks if a user copies just one file. Recommend `-r`-chained per cycle-35 L8 reasoning.

**Step 11 verification.**
- For each NEW `requirements-<extra>.txt`: parse it, parse `pyproject.toml [project.optional-dependencies] <extra>`, assert (a) same package set, (b) `requirements-*` pin satisfies the pyproject floor.
- Confirm the cycle-35 L8 fix `langchain-openai>=1.1.14` is present in BOTH `requirements.txt` AND `requirements-eval.txt`.
- Run `pip install -r requirements-eval.txt` in a throwaway venv (Codex may run this in a sandbox) and `pip-audit` the result — must match the canonical `pip install -e '.[eval]'` audit set.

### T5 — `SECURITY.md` drift (missed Class A advisories) → pip-audit unexpected fail

**Description.** AC20 adds the 4th litellm advisory `GHSA-v4p8-mg3p-g94g` to `SECURITY.md` Known Advisories AND the workflow's `--ignore-vuln` list. The two MUST stay synchronized: a row in the table without a workflow flag → CI fails. A workflow flag without a table row → silent acceptance, audit-trail gap. The Step-2 baseline (`.data/cycle-36/alerts-baseline.json`) shows 4 advisories: 3 litellm (GHSA-v4p8-mg3p-g94g, GHSA-r75f-5x8p-qvmc, GHSA-xqmj-j6mv-4862), 1 ragas (GHSA-95ww-475f-pr4f). Current workflow `--ignore-vuln` lists CVE-2025-69872, GHSA-xqmj-j6mv-4862, CVE-2026-3219, CVE-2026-6587. The two ID schemes (CVE-* vs GHSA-*) make 1:1 matching by eyeball error-prone.

**Mitigation in this cycle.**
1. AC20 explicit: add row + `--ignore-vuln` flag in the same commit.
2. `SECURITY.md` Known Advisories table has a "Verification grep" column — every entry must keep the grep pointing to zero direct imports (cycle-32 verification practice).
3. The cycle-32 baseline lesson: snapshot Dependabot via `gh api` BEFORE editing `--ignore-vuln`, so the diff is provable. AC18 already mandates this snapshot.
4. NEW `tests/test_cycle36_ci_hardening.py` should add a parsing test cross-referencing `SECURITY.md` advisory IDs against `ci.yml --ignore-vuln=` flags — list-equality check on the two sets.

**Step 11 verification.**
- Grep `SECURITY.md` for advisory IDs (regex `(CVE-\d{4}-\d+|GHSA-[a-z0-9-]+)`); diff against `.github/workflows/ci.yml --ignore-vuln=` set; assert equality.
- Confirm the new GHSA-v4p8-mg3p-g94g row has its own narrow-role rationale (not just copy-pasted from the existing litellm row) — Codex reads the row text.
- Run `pip-audit --ignore-vuln=...` on the live install and confirm it exits 0.

### T6 — Cross-OS matrix exposing UNTESTED platform attack surface (e.g., POSIX symlink traversal that Windows tests miss)

**Description.** Cycle-36 was windows-latest only. Adding ubuntu-latest (AC12) is good defence-in-depth but introduces a new failure mode: tests that *pass* on POSIX but only because they don't test what they claim. Example: `test_validate_wiki_dir_symlink_to_outside_rejected` is currently Windows-only. On POSIX, `os.symlink` succeeds for any user (no admin needed). If the production code's symlink-traversal guard has a POSIX-specific bug, the windows-latest run never exercises it. Conversely, `test_page_id_normalizes_backslashes_to_posix_id` may fail on POSIX because backslash isn't a path separator there. The 6 enumerated AC11 tests get `skipif(sys.platform != "win32")`, but symmetric "POSIX-only" markers are not enumerated — the requirements explicitly defer enumeration of POSIX-only fragility to cycle-37 (line 74).

**Mitigation in this cycle.**
1. AC11 conservatively enumerates the 6 known Windows-only tests; AC12 adds the matrix; AC13 explicitly says "if ubuntu reveals additional fragility classes beyond the 6, file BACKLOG entries for cycle-37 follow-up rather than expanding cycle-36 scope." This bounds blast radius.
2. The 6 enumerated tests cover: symlink-outside-rejected, backslash-normalisation, qb_symlink_outside_raw, absolute-path-rejected, exclusive-atomic-write (needs verification), and "any `os.symlink` privileged-call." Step-5 design must decide which way `test_capture.py::TestExclusiveAtomicWrite` goes — its symlink usage may be portable or Windows-privileged.
3. **OPEN-QUESTION for Step-5 design gate:** AC11's enumeration is a "trust the BACKLOG" approach; the alternative is a `pytest --co -q | grep -E "(symlink|backslash|win32|drive_letter)"` enumeration to catch incidentally-Windows-coded tests not listed. Recommend running this grep at design-eval time.
4. POSIX symlink traversal is a real attack — the production code (`_validate_path_under_project_root`) is dual-anchor and platform-agnostic (literal + resolved both under PROJECT_ROOT). On POSIX the resolved path catches symlink-outside; on Windows the literal path catches it. The matrix increases assurance, not decreases it.

**Step 11 verification.**
- Grep `tests/` for `os.symlink`, `Path.symlink_to`, `\\\\` (UNC paths), `C:` (drive letters); for each match, confirm there's either an OS-conditional skipif or the test is OS-portable.
- Confirm ubuntu-latest run actually executes (look for the matrix entry in the GHA UI; not a "skipped because windows-only matrix" condition).
- Compare passing-test counts: ubuntu-latest passing should equal windows-latest passing minus the 6 AC11 skips, plus any POSIX-only tests Codex enumerates as a finding (BACKLOG follow-up).

### T7 — `requires_real_api_key()` helper false-negatives → real API calls in CI (cost / leak)

**Description.** AC6 introduces `tests/_helpers/api_key.py::requires_real_api_key()`. The helper must return `False` when `ANTHROPIC_API_KEY` is unset OR matches the dummy CI prefix `sk-ant-dummy-key-for-ci-tests-only`. A bug in the helper (e.g., string-`startswith` typo, wrong env var name, or `if os.getenv("ANTHROPIC_API_KEY")` truthy-check that returns True for the dummy because dummies are non-empty strings) would let tests that genuinely call `anthropic.Anthropic(api_key=...).messages.create(...)` execute in CI with the dummy key. Anthropic SDK would then raise auth-failure → potential `pytest -q` flake noise, but worst case a developer's REAL key sneaks into CI environment (e.g., via `act` local CI runner that loads `.env`) and gets billed. Even worse: a mistyped helper that lets the test through on `MOCK_ANTHROPIC=1` (open question 4) would issue real API calls if the SDK treats `MOCK_ANTHROPIC` as advisory.

**Mitigation in this cycle.**
1. The helper is a single-purpose 5-line function. Its body is testable in isolation (per `feedback_inspect_source_tests.md` — extract helper, test directly, do NOT use `inspect.getsource + 'X' in src`).
2. NEW `tests/test_cycle36_ci_hardening.py` MUST include behaviour tests for the helper:
   - `requires_real_api_key()` returns False when `ANTHROPIC_API_KEY` is unset (use `monkeypatch.delenv`).
   - Returns False when `ANTHROPIC_API_KEY == "sk-ant-dummy-key-for-ci-tests-only"`.
   - Returns False when `ANTHROPIC_API_KEY` starts with `"sk-ant-dummy"` (broader prefix match).
   - Returns True when `ANTHROPIC_API_KEY == "sk-ant-real-looking-key"` (split-string-constructed per `feedback_no_secrets_in_code.md`).
3. The CI `env:` line keeps the dummy key. AC6 marks affected tests `skipif(not requires_real_api_key(), ...)`; a buggy helper would either always-True (falsely run) or always-False (falsely skip). Behaviour test (2) catches the always-True bug; behaviour test (4) catches the always-False bug.
4. Open question 4 should resolve to **skipif, not MOCK_ANTHROPIC=1**. The latter requires SDK cooperation we don't control.

**Step 11 verification.**
- Read `tests/_helpers/api_key.py` source; confirm the matching uses `.startswith("sk-ant-dummy")` (broad) or exact-equals the documented dummy (narrow). Either is acceptable; document the choice.
- Run the 4 behaviour tests via `pytest tests/test_cycle36_ci_hardening.py::test_requires_real_api_key_*` — all must pass.
- Grep for `anthropic.Anthropic(api_key=` outside test fixtures; confirm every callsite is either in `src/kb/` (production, never executed in tests) or guarded by `requires_real_api_key()`.
- Confirm the dummy key's prefix `sk-ant-dummy-key-for-ci-tests-only` is documented in CONTRIBUTING.md or `docs/reference/testing.md` (AC25) so a future contributor doesn't accidentally use a similar-looking dummy that fails the prefix check.

### T8 — Multiprocessing-test fix that bypasses the bug instead of fixing it (hides root cause)

**Description.** AC1+AC2 first identifies the Windows CI hang (~1151/2995 tests, `multiprocessing\popen_spawn_win32.py:112: KeyboardInterrupt`) and either skips or fixes it. The skip path (default per AC2) protects the strict gate but masks any real bug in `kb.utils.io.file_lock` cross-process semantics on Windows GHA runners. The cycle-23 test was added precisely because thread-based tests are insufficient (cycle-23 R2 lesson). Skipping it on CI degrades cycle-23's coverage in exactly the environment (CI-like ephemeral Windows VMs) where production users with similar VM setups might hit the bug. Sub-risk: skip + 60 s pytest-timeout (AC3) means the next cross-process test that hangs on CI silently skips because the predicate fires on collection error, not runtime.

**Mitigation in this cycle.**
1. AC1 demands binary-search isolation FIRST. The investigation document at `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md` records the offending test + hang signature so future cycles can revisit.
2. AC2 prefers fix over skip when root cause is fixable (e.g., `child.terminate() + child.join(timeout=...)` cleanup, or `mp.set_start_method("spawn")` reorganisation). Reading `test_cycle23_file_lock_multiprocessing.py`: it already uses `ctx = mp.get_context("spawn")`, has `try / finally` cleanup with `child.kill()` fallback, and bounded `release_event.wait(timeout=10.0)`. The hang is likely **NOT** in this test's logic — it's in the GHA Windows runner's `popen_spawn_win32` itself or in earlier-running tests leaving a stale child. The investigation must be honest about whether the symptom-test is the actually-buggy test.
3. The `KeyboardInterrupt` at `popen_spawn_win32.py:112` strongly suggests GHA is hitting its 6-hour job timeout, not pytest exiting cleanly. With AC3's 60 s pytest timeout, the symptom would change from "silent hang" to "explicit timeout traceback at test ID X" — diagnostic improvement even before the fix lands.
4. The skip path includes a BACKLOG entry per AC23 ("Add NEW entry if AC1 reveals a CI-only hang root cause that needs deeper investigation") — bug doesn't get forgotten.

**Step 11 verification.**
- Read `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md` — must name the offending test, must show a binary-search log or pytest-isolation evidence, must explain why fix-vs-skip was chosen.
- If skipped: confirm BACKLOG entry exists for cycle-37 follow-up.
- If fixed: confirm a regression test in `test_cycle36_ci_hardening.py` exercises the same code path that previously hung, and that path now completes within `pytest-timeout = 60` s.
- Confirm the local probe (AC4) shows 2985 + 10 skipped (or 2985 - <skipif count> + skip-count) — the exact accounting must match.

### T9 — Strict gate first-run flake (AC8 + AC4 dependency)

**Description.** Dropping `continue-on-error: true` (AC8) before AC1+AC2+AC3+AC5+AC6+AC7+AC11 land would block every PR including the cycle-36 PR itself. The PR has a chicken-and-egg ordering: strict gate flips ON only after all marker fixes flip ON, but the marker fixes ARE the cycle-36 PR. If the PR is split into two (markers first, strict-gate second), the second PR is gated by the first's CI run.

**Mitigation in this cycle.**
1. Cycle-36 ships as a single PR; the marker fixes and the `continue-on-error` removal are in the same diff. The first CI run validates the entire stack atomically.
2. AC4 mandates a local probe BEFORE pushing — the developer asserts `pytest -q` passes locally with all markers applied. Catches at-least the developer-machine class of bugs.
3. If the PR's first CI run fails strict, the iterate-fix-rerun loop is bounded to cycle-36 itself, not propagated to other PRs (concurrency cancel-in-progress + branch protection on `main` keeps unrelated PRs unblocked while cycle-36 stabilises).

**Step 11 verification.**
- Read CI run history for the cycle-36 PR — confirm at least one run after AC8 strictness lands shows green without `continue-on-error` saving it.
- Confirm `continue-on-error: true` survives ONLY on `pip check` step (AC10 explicitly preserves it for the three documented transitive conflicts).

---

## Step 2 dep-CVE baseline summary

4 open Dependabot alerts: 3 litellm (GHSA-v4p8-mg3p-g94g, GHSA-r75f-5x8p-qvmc, GHSA-xqmj-j6mv-4862) all fix-at-1.83.7 BLOCKED by `litellm 1.83.7`'s `click==8.1.8` transitive constraint vs our `click==8.3.2` cycle-31/32 CLI pin; 1 ragas (GHSA-95ww-475f-pr4f) low severity, no upstream fix. `pip-audit` in the live CI install env passes with 4 documented narrow-role `--ignore-vuln` flags; AC20 adds the 4th litellm advisory to bring the workflow + `SECURITY.md` table back to 1:1. No new advisories outside the litellm/ragas family.

---

## Same-class peer notes (cycle-35 L3 generalisation)

For each cycle-36 fix, peers that may need same treatment:

- **AC2 (multiprocessing skip):** any other test using `mp.Process` / `mp.get_context("spawn")` that touches CI. Grep `tests/` shows only `test_cycle23_file_lock_multiprocessing.py`. Threading-based tests (`test_cycle20_write_wiki_page_exclusive.py`, `test_cycle23_rebuild_indexes.py`) use `threading.Thread`, not subprocess spawn — different failure mode, no peer fix needed yet.

- **AC5 (wiki-content-dependent monkeypatch mirror-rebind):** the `kb.config.WIKI_DIR` snapshot hazard generalises. Grep `tests/` for `monkeypatch.setattr.*WIKI_DIR` — peers found in `test_cycle10_quality.py` (AC5 target), and per `docs/reference/testing.md` rule, anything reaching `sweep_stale_pending`/`list_stale_pending`/`refine_page` via MCP/CLI. Step-11 should grep for additional reach-through callsites.

- **AC6 (`requires_real_api_key()` skipif):** peers are every `anthropic.Anthropic(api_key=...)` instantiation in tests. Grep result: `test_v5_lint_augment_orchestrator.py`, `test_env_example.py`, `test_backlog_by_file_cycle1.py`. AC6 already enumerates these. If Codex finds more, add to BACKLOG cycle-37.

- **AC7 (timing-precision tolerance widening):** the `<= 3600` vs `<= 3601` pattern. Grep shows 1 hit in `test_capture.py:165`. Step-11 grep for similar floating-point boundary asserts on time-bounded values: `<= 60.0`, `<= 86400`, `<= 3600`, `< 1.0` etc. Document any peers as cycle-37 candidates.

- **AC11 (cross-OS skipif):** peers are tests that use OS-specific path semantics. Grep shows ~8 files with `sys.platform` / `os.name` references already. The 6 enumerated tests are the *unguarded* ones. Step-11 verifies no incidentally-Windows-coded tests slip through (T6).

- **AC20 (`SECURITY.md` advisory row):** peers are any future advisory that pip-audit surfaces — the cadence in `SECURITY.md` Re-check Cadence governs.

---

This becomes the step 11 verification checklist.
