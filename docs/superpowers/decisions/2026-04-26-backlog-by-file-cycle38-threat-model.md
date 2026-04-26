# Cycle 38 — Threat Model

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle38`
**Scope:** Re-enable 14 POSIX-skipped tests (10 Cat-A `mock_scan_llm` reload-leak + 4 Cat-B Windows-helper). 99% test-side; AC7/AC8 may add minimal `src/kb/capture.py` change only if probe surfaces a real bug.
**Companion:** [requirements.md](2026-04-26-backlog-by-file-cycle38-requirements.md)

---

## 1. Trust boundaries

**No new trust boundaries are introduced or modified.**

- `kb_capture` MCP tool boundary (rate-limit, secret-scan, size-cap, path-confinement) — UNCHANGED. AC1/AC2/AC6 widen test-side `monkeypatch.setattr` only; production callers / validators / `_validate_path_under_project_root` unchanged.
- LLM SDK boundary (`kb.utils.llm.call_llm_json` → Anthropic SDK) — UNCHANGED at runtime. The cycle widens the in-test mock to also patch the canonical-source binding so test code doesn't reach the real SDK; production binding is identical.
- File-system boundary (`CAPTURES_DIR` confinement via `_CAPTURES_DIR_RESOLVED`) — UNCHANGED. AC7/AC8 may add diagnostics but final fix preference is test-side per requirements §2.

## 2. Data classification

**Test data only. No PII, no secrets, no production state.**

- AC1/AC2/AC5 mock returns canned dicts (`{"items": [...], "filtered_out_count": N}`) — no real prompts or completions transit the SDK boundary.
- AC6 `boom`/`interrupted` callables raise `OSError`/`KeyboardInterrupt` — no payload data.
- AC7/AC8 use `_make_item("decision", "foo")` literals under `tmp_captures_dir` (always `tmp_path`-rooted, asserted relative-to in `tmp_captures_dir`).
- AC9 reads CVE metadata only (advisory IDs, fix versions) via `gh api` + `pip-audit`. No package modification.

## 3. Authn/authz needs

**No new authn/authz requirements.** Rate-limit (`_check_rate_limit` deque) untouched. Path confinement (`_validate_path_under_project_root`) untouched. CI dummy `ANTHROPIC_API_KEY` semantic preserved (the entire point of AC1 is to ensure mock fires so CI dummy key is never reached).

## 4. Logging/audit requirements

**No logging changes.** `kb.capture.logger` call sites unchanged. AC7/AC8 probe-style commit may add temporary `print()` diagnostics — these MUST be reverted before final commit (verified by Step-11 grep for `print(` in `src/kb/capture.py` diff).

---

## 5. Threat enumeration

| ID | Severity | Component | Vector | Mitigation in cycle | Residual risk |
|---|---|---|---|---|---|
| **T1** | MED | `mock_scan_llm` fixture (`tests/conftest.py:362`) | Reload-leak class (cycle-19 L2 / cycle-20 L1): if a sibling test runs `importlib.reload(kb.utils.llm)` after `mock_scan_llm` installs, `kb.capture.call_llm_json` may be re-bound to the real SDK callable, causing dummy-key 401 leak path. Could THEORETICALLY allow real outbound HTTP if a CI run had a non-dummy key. | AC1 dual-site patch (`kb.capture.call_llm_json` AND `kb.utils.llm.call_llm_json`); AC5 regression test pins post-reload behaviour and is required to FAIL if AC1 is reverted (per `feedback_test_behavior_over_signature`). | Third-party mod re-binding `call_llm_json` from a non-`kb.*` module is not covered. Acceptable — `tmp_kb_env` mirror loop already scopes to `kb.*` for the same reason (cycle-12 R1). |
| **T2** | MED | `tests/test_cycle38_mock_scan_llm_reload_safe.py` (NEW) | AC5 calls `importlib.reload(kb.utils.llm)`; if cleanup is incomplete the reloaded module instance leaks into sibling tests in collection order, mutating their `call_llm_json` reference. | `monkeypatch` undoes `setattr` on teardown automatically; `importlib.reload` does NOT mutate `sys.modules` to a new id (same module object updated in place), so subsequent `import kb.utils.llm` gets the same object. The autouse `_reset_embeddings_state` fixture is the only stateful cross-test resetter and is unaffected. Add explicit `monkeypatch` of `sys.modules["kb.utils.llm"]` if probe shows leak. | Order-dependent failure if the new test file lands BEFORE `test_capture.py` alphabetically — pytest default is collection-order, file is `test_cycle38_*` which sorts AFTER `test_capture.py` so risk is low. Verify via Step-11 `pytest --collect-only`. |
| **T3** | LOW→MED | `src/kb/capture.py` `_scan_existing_slugs`/`_build_slug`/`_reserve_hidden_temp` (lines 555/406/561) + `_write_item_files` (line 607) | AC7/AC8 may surface a real POSIX bug: (a) slug counter off-by-one (`decision-foo-3` instead of `-2`) → resource exhaustion if iteration unbounded; mitigated by `_SLUG_COLLISION_CEILING = 10000`; (b) `_write_item_files` dir recreation race → potential `EEXIST` on concurrent capture. NOT a confidentiality/integrity issue — slugs are advisory; `_exclusive_atomic_write` still uses `O_EXCL`. | If probe reveals real production bug: fix the production code (preferred for correctness). If probe shows POSIX-correct behaviour just differs from Windows, loosen test assertion (preferred per requirements §2 "preferred — POSIX behavior documented"). Either way, `_SLUG_COLLISION_CEILING` caps DoS surface and `O_EXCL` reservation prevents overwrite. | If AC7/AC8 ships a production-code change without a same-cycle peer-scan (cycle-16 L1) for similar slug-counting code paths in other modules, drift risk. Mitigation: requirements §7 Q3 mandates same-class peer scan for AC6; extend to AC7/AC8. |
| **T4** | LOW | `BACKLOG.md` litellm advisories GHSA-r75f / GHSA-v4p8 | Drift attestation: cycle-37 narrow-role rationale (litellm dev-eval-only; zero `src/kb/` imports; click<8.2 transitive blocks 1.83.7 fix) may have shifted between 2026-04-19 and 2026-04-26 if click pin moved or litellm relaxed transitive constraint. | AC9 re-runs `gh api dependabot/alerts` + `pip-audit -r requirements.txt --format=json`; updates BACKLOG re-check date; adds `--ignore-vuln` IDs ONLY if pip-audit catches up. No package upgrade attempted. | If a NEW litellm advisory drops between AC9 and PR merge (cycle-22 L4), Step-15 late-arrival warn covers it. |
| **T5** | LOW | `mock_scan_llm` fixture | AC1's `fake_call` returns canned `response` dict. Could a malicious test fixture in this PR smuggle a real secret into the canned response? | Mock signature has hard `assert isinstance(schema, dict)` and key-presence assertions BEFORE returning; mocked response never leaves the test process (no network, no disk write — `_write_item_files` writes to `tmp_captures_dir` only). AC1's widening adds no new return path — same `response` dict fed back. | No residual — canned data, in-memory only. |
| **T6** | MED | ubuntu-latest CI strict-gate | Re-enabling 14 tests previously skipped on POSIX could surface OTHER unrelated POSIX bugs in production code (path normalization, `os.fsync`, locale-dependent slug behaviour). Failure mode: cycle-37 L5 ships at the cycle-end with red CI. | Step-9 TDD per AC + Step-10 full local CI mirror BEFORE pushing (`pytest -q` on POSIX shell or `wsl pytest`); cycle-36 L1 limits to one new CI dimension/cycle (already paid in c36) so re-enabling existing dimension's tests is in-budget. | If a 15th POSIX-divergent test surfaces during Step-10, scope-cut option: keep `_REQUIRES_REAL_API_KEY` on the offending test, document as cycle-39 candidate (R1 in requirements). |
| **T7** | LOW | Dependabot drift between Step 2 and Step 11 | Cycle-22 L4: a new advisory can drop mid-cycle. Cycle-37 L1 sets the four-gate model (Step 2 baseline / Step 11 PR-introduced diff / Step 12.5 existing-CVE patch / Step 15 late-arrival warn). | Step-2 baseline captured (4 pip-audit + 4 Dependabot; drift on GHSA-r75f / GHSA-v4p8). Step-11 will re-run pip-audit + `gh api dependabot/alerts` and diff. Cycle adds zero deps so PR-introduced count = 0 expected. | Late-arrival window between Step 15 and merge — covered by `feedback_dependabot_pre_merge` Gate-D. |

---

## 6. Step-2 dep-CVE baseline summary

| Source | Count | IDs |
|---|---|---|
| `pip-audit -r requirements.txt` | 4 | diskcache@5.6.3 (CVE-2025-69872, no fix), litellm@1.83.0 (GHSA-xqmj-j6mv-4862, fix=1.83.7 BLOCKED), pip@26.0.1 (CVE-2026-3219, no fix), ragas@0.4.3 (CVE-2026-6587, no fix) |
| `gh api dependabot/alerts` | 4 open | same 4 IDs as above |
| Drift (Dependabot reports, pip-audit silent) | 2 | litellm GHSA-r75f-5x8p-qvmc (critical), GHSA-v4p8-mg3p-g94g (high). Both fix=1.83.7 BLOCKED by click<8.2. |
| **PR-introduced expected** | **0** | Cycle adds zero deps. |

Step-11 diff target: identical set or smaller. Any new ID = block, investigate, narrow-role rationale or pin.

---

## 7. Step-11 verification checklist

| Threat | Verify command (Windows-bash, absolute paths) |
|---|---|
| **T1** | `grep -n "kb.utils.llm.call_llm_json" D:/Projects/llm-wiki-flywheel/tests/conftest.py` → must return ≥1 line in `mock_scan_llm`; `grep -n "kb.utils.llm.call_llm_json" D:/Projects/llm-wiki-flywheel/tests/test_capture.py` → must return ≥2 lines (paired with the two `kb.capture.call_llm_json` sites). |
| **T1 (AC5)** | `python -m pytest D:/Projects/llm-wiki-flywheel/tests/test_cycle38_mock_scan_llm_reload_safe.py -v` → both cases PASS post-fix. Then locally revert AC1 (single-site patch) and re-run → case (b) MUST FAIL (proves not vacuous). |
| **T2** | `python -m pytest D:/Projects/llm-wiki-flywheel/tests/test_cycle38_mock_scan_llm_reload_safe.py D:/Projects/llm-wiki-flywheel/tests/test_capture.py -v` (sibling order) → all green. |
| **T3** | `grep -n "@_WINDOWS_ONLY" D:/Projects/llm-wiki-flywheel/tests/test_capture.py` → must return 0 lines (all 4 decorators removed); `grep -n "print(" D:/Projects/llm-wiki-flywheel/src/kb/capture.py` → no NEW lines vs `git diff main -- src/kb/capture.py` (probe diagnostics fully reverted); `python -m pytest D:/Projects/llm-wiki-flywheel/tests/test_capture.py::TestWriteItemFiles -v` → green. |
| **T4** | `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts --paginate \| python -m json.tool \| grep -E "GHSA-r75f\|GHSA-v4p8"` → matches requirements §AC9; `grep -n "GHSA-r75f\|GHSA-v4p8" D:/Projects/llm-wiki-flywheel/BACKLOG.md` → cycle-38 re-check date present. |
| **T5** | `grep -n "fake_call" D:/Projects/llm-wiki-flywheel/tests/conftest.py` → schema-assert + isinstance-dict assert lines unchanged; `grep -rn "ANTHROPIC_API_KEY" D:/Projects/llm-wiki-flywheel/tests/` → no new real-key usage. |
| **T6** | `python -m pytest D:/Projects/llm-wiki-flywheel/tests/ -q` (full suite, mimicking CI) → 3012+ tests, 0 fails; `python -m pytest D:/Projects/llm-wiki-flywheel/tests/test_capture.py D:/Projects/llm-wiki-flywheel/tests/test_mcp_core.py -q` → 14 previously-skipped tests now PASS, 0 newly-skipped. |
| **T6 (CI mirror)** | `ruff check D:/Projects/llm-wiki-flywheel/src/ D:/Projects/llm-wiki-flywheel/tests/ && ruff format --check D:/Projects/llm-wiki-flywheel/src/ D:/Projects/llm-wiki-flywheel/tests/ && pip-audit -r D:/Projects/llm-wiki-flywheel/requirements.txt && python -m build D:/Projects/llm-wiki-flywheel` → all green (cycle-34 L6 hard gate). |
| **T7** | `pip-audit -r D:/Projects/llm-wiki-flywheel/requirements.txt --format=json > /tmp/cycle38-step11.json && diff <(jq -S '.dependencies[].vulns[].id' /tmp/cycle38-step2.json) <(jq -S '.dependencies[].vulns[].id' /tmp/cycle38-step11.json)` → empty diff (no new IDs); if non-empty, investigate per cycle-37 L1. |

**Review trigger (cycle-17 L4):** 10 ACs, ≤5 src files, no new write surface, no new security enforcement point → R1+R2 only, R3 skipped.
