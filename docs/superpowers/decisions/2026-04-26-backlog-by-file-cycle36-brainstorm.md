# Cycle 36 — Brainstorm

**Date:** 2026-04-26
**Inputs:** Step 1 requirements + Step 2 threat model
**Output target:** Step 4 design eval (Opus + Codex parallel rounds)

7 open questions from Step 1 requirements. For each: 2-3 approaches with trade-offs and a recommendation. Step 5 decision gate commits.

---

## Q1 — Multiprocessing test on CI: fix vs skip

**Symptom (confirmed Step 2):** `tests/test_cycle23_file_lock_multiprocessing.py::test_cross_process_file_lock_timeout_then_recovery` is collected at position #1155 — exactly where Windows GHA CI hangs at 1151 passed + 3 skipped + 1 hung. Test passes locally on Windows in 1.03s; fails on GHA Windows runner. Root cause likely: child Python interpreter spawn-bootstrap can't import `kb.utils.io` cleanly on the GHA runner (editable-install pth-file resolution, or env-var difference), so parent's `child.start()` blocks at `popen_spawn_win32.py:112` (`reduction.dump(prep_data, to_child)` waiting on an unresponsive pipe).

**Options:**

A. **Skip on CI via env-var marker** — `@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Windows multiprocessing spawn hangs on GHA — local cycle-23 verification + integration mark suffices.")`. Test still runs locally (where it works). CI passes the strict gate. Simple, reversible, preserves audit trail.

B. **Fix the underlying spawn hang** — diagnose why GHA Windows runner can't bootstrap the spawned child. Hypotheses: (i) `pip install -e` editable .pth not resolving in spawned child's `sys.path`, (ii) `PYTHONNOUSERSITE` env var, (iii) `kb.config` PROJECT_ROOT detection failing in spawned child. Fix would require GHA reproduction (hard from local), iterative trial-and-error pushes, time-unbounded.

C. **Move the test to a separate CI workflow with longer timeout + isolation** — keep it green-checkmark independent of the main CI. Cosmetic — doesn't actually fix anything; just hides the failure in a different surface. Reverse of intent (we want strict gating).

**Recommendation: A.** Cycle 36's GOAL is to drop continue-on-error. Spending 2-3 implementation rounds debugging a GHA-Windows-only spawn quirk would block the cycle. The test is `@pytest.mark.integration` and represents an EDGE CASE (cross-process file lock recovery) that's already validated locally on the developer's actual Windows install. Filing a BACKLOG entry for cycle-37+ to investigate the GHA-Windows-spawn divergence is the right tradeoff. Option B is a 2-3 day rabbit hole that may or may not yield insight.

**Trade-off accepted:** integration coverage on GHA is incomplete for this single test until the GHA-spawn issue is investigated separately. Counterweight: BACKLOG entry tracks it; local cycle-23 verification stays valid; future cycle can re-enable when fixed.

## Q2 — pytest-timeout default

**Background (AC3):** Without a timeout, future hung tests would silently kill pytest like the cycle-23 multiprocessing test does today. `pytest-timeout` library provides per-test SIGALRM (POSIX) or thread-based (Windows) timeouts.

**Options:**

A. **60 s default** — aggressive enough to catch hangs quickly. Risk: longest legitimate tests (full PageRank computation, integration tests with multiple ingest cycles) may exceed 60s on slow CI runners and false-positive.

B. **120 s default** — balances catch-hangs with tolerance. Slowest legitimate tests (verified locally) are typically <30s; 120s gives 4x headroom.

C. **300 s default** — very generous. Only catches "truly forever" hangs. Tests that legitimately take 60-120s won't false-positive.

D. **No global default; require per-test marker** — `@pytest.mark.timeout(N)` on individual tests. More work; easy to forget; no protection against future hangs in unmarked tests.

**Recommendation: B (120 s) with override mechanism.** Aggressive enough that any 2-min hang fails fast. Wide enough that no current test should false-positive. Configure in pyproject.toml: `[tool.pytest.ini_options] timeout = 120` and document the override pattern (`@pytest.mark.timeout(300)` for legitimately-slow integration tests).

**Verification at Step 10:** run full local suite with `timeout=120`. Any test exceeding 120s gets flagged in the run log; either widen its specific marker OR file a perf BACKLOG entry.

## Q3 — Wiki-content-dependent tests: mirror-rebind monkeypatch vs skipif

**Tests affected:** `test_cycle10_quality.py::test_kb_refine_page_surfaces_backlinks_error_on_failure` + `test_kb_affected_pages_surfaces_shared_sources_error_on_failure`. Both use `tmp_wiki + create_wiki_page("concepts/rag", ...)` BUT only monkeypatch `kb.review.refiner.WIKI_DIR`. Tests pass locally because the developer's real `wiki/concepts/rag.md` exists as a fallback.

**Options:**

A. **Mirror-rebind monkeypatch chain** — patch ALL the WIKI_DIR snapshot bindings: `kb.config.WIKI_DIR`, `kb.review.refiner.WIKI_DIR`, `kb.mcp.quality.WIKI_DIR` (per `docs/reference/testing.md` rule generalised from cycle-19 L1). Test then exercises the production code path against the empty `tmp_wiki + concepts/rag.md` (created by `create_wiki_page`). The test ASSERTION (production raises an error → response includes `[warn] backlinks_error:`) should still hold against `tmp_wiki`.

B. **Skipif marker on production-wiki dependency** — `@pytest.mark.skipif(not (PROJECT_ROOT / "wiki" / "concepts" / "rag.md").exists(), reason="...")`. Tests only run on developer machines with populated wiki/. Simple but loses coverage on CI permanently.

C. **Fixture-level wiki seeding** — add a `populated_tmp_wiki` fixture to `conftest.py` that creates `concepts/rag.md` + minimal index/sources files. Tests opt in via `populated_tmp_wiki` instead of `tmp_wiki`. Reusable for any future wiki-content-dependent test.

**Recommendation: A.** Mirror-rebind is the cleanest fix; the test ALREADY uses `tmp_wiki + create_wiki_page` so the wiki content IS being seeded — only the monkeypatch is incomplete. The code change is ~3 lines per test. Maintains CI coverage. Cycle-19 L1 documented this exact pattern; we're just applying it to a test that was missed.

**Fallback:** if mirror-rebind doesn't reach the read site (production code reads via `from kb.config import WIKI_DIR` snapshot pre-monkeypatch), fall back to C (fixture seeding) — A and C are functionally equivalent at the test outcome level; A is just smaller.

## Q4 — CI dummy-key strategy for Anthropic SDK tests

**Symptom:** Tests instantiating `anthropic.Anthropic(api_key=...)` and trying to make a real API call would hang on `sk-ant-dummy-key-for-ci-tests-only`. Tests that mock the HTTP layer correctly are fine; tests that hit the real client are not.

**Options:**

A. **`requires_real_api_key()` predicate + skipif** — helper checks if `ANTHROPIC_API_KEY` matches the dummy CI prefix; skipif marks the affected tests. Simple, transparent, preserves the passing tests in CI (where the SDK is mocked at the HTTP layer).

B. **Mock the SDK at conftest level** — autouse fixture monkeypatching `anthropic.Anthropic.messages.create` to return canned responses. More invasive; risks breaking tests that legitimately test the SDK shape.

C. **Use a real test API key in CI via secrets** — `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_TEST_KEY }}`. Real coverage but: (i) cost (every CI run burns API credits), (ii) breaks `permissions: read-all` security posture, (iii) leak risk on fork PRs.

**Recommendation: A.** Aligns with the existing pattern (tests already mock the HTTP layer; the failing class is "tests that bypass the mock and try to construct a real client"). Helper is ~10 lines; skipif annotations are mechanical. No new attack surface.

**Granularity:** the helper checks the dummy-key PREFIX (`sk-ant-dummy-key-`), not exact equality, so any future CI key with that prefix is correctly identified as dummy.

## Q5 — Cross-OS matrix scope

**Background:** BACKLOG enumerates ~6 Windows-specific tests. Step-1 AC11 lists candidates from grep + BACKLOG. Step-1 AC12 proposes `[ubuntu-latest, windows-latest]` matrix.

**Options:**

A. **Skipif markers on the 6 enumerated tests + matrix** — minimal-fix approach. Risk: ubuntu-latest run reveals ADDITIONAL fragility classes not in the enumeration (e.g., POSIX path-equality, case-sensitive filesystem, fork-vs-spawn defaults).

B. **Run a probe ubuntu-latest CI BEFORE adding the matrix; enumerate from REAL failures** — push a probe branch, observe ubuntu failures, then add skipif markers based on actual results. More accurate scope; adds a CI cycle to the workflow.

C. **Defer Area D entirely to cycle 37** — don't add ubuntu matrix in cycle 36; just close the strict-gate (Area C) on windows-latest. cycle 37 takes Area D as standalone.

**Recommendation: B.** A probe ubuntu run is fast (~5 min) and reveals the truth. Then the skipif enumeration is data-driven instead of guess-driven. If the probe reveals >10 new fragility classes, defer to cycle 37 (Option C path). If <=10, ship in cycle 36.

**Concrete probe:** open a draft PR with workflow change `runs-on: ubuntu-latest` (single OS, not matrix yet). Observe failures. Skipif those tests. Switch back to matrix. Total cost: 1 probe push + 1 fix push.

## Q6 — Requirements split-file structure

**Background:** AC14-AC17 propose `requirements-runtime.txt` / `requirements-hybrid.txt` / etc. matching pyproject extras.

**Options:**

A. **Self-contained per-extra files** — each `requirements-<extra>.txt` includes the runtime pins PLUS the extra's pins. Pin duplication across files; users get clean per-file install paths.

B. **Layered: `-r requirements-runtime.txt` includes** — each extra file starts with `-r requirements-runtime.txt` and adds only the extra's pins. Avoids pin duplication; users get composable install paths.

C. **Generate from pyproject + requirements.txt via tooling** — write a `scripts/generate_requirements.py` that reads pyproject extras + requirements.txt and emits split files. Reproducible; adds a new tool to maintain.

**Recommendation: B (layered).** Avoids pin duplication; matches how `pip install` semantics work; trivial to maintain by hand. Users still get one-file install paths (`pip install -r requirements-hybrid.txt` → installs runtime + hybrid, no manual chaining). C is over-engineering for this cycle.

**Concrete shape:**
```
# requirements-hybrid.txt
# Runtime + hybrid extras (vector search via model2vec + sqlite-vec).
-r requirements-runtime.txt

model2vec==0.8.1
sqlite-vec==0.1.9
numpy==2.4.4
```

## Q7 — Cycle scope cap (D / E defer-include decision)

**Inputs:** 16 must-land ACs (A+B+C+F+G), 3 D ACs, 4 E ACs, ~4 doc ACs = 27 total. Cycle-19 L4 R3 trigger fires at >=15 ACs when (a) new fs-write surface, (b) hard-to-reach defensive check, (c) new security enforcement, OR (d) >=10 design-gate questions.

**Options:**

A. **All 27 ACs in cycle 36** — full closure of all three cycle-36 BACKLOG entries + opportunistic CVE recheck. Risk: large blast radius; possible R3 cycle; longer subagent dispatches.

B. **Drop Area E (requirements split) → 23 ACs** — defer split to cycle 37; close A/B/C/D/F/G. Smaller; preserves cross-OS portability closure (which the BACKLOG cycle-36 entry explicitly names).

C. **Drop Area D AND E → 20 ACs** — focus only on strict-gate closure. Cleanest scope; defers two cycle-36 BACKLOG entries to cycle 37+.

**Recommendation: B.** Areas A+B+C are inseparable (strict gate requires hung-test fix + fragility-class fix). Area F (CVE recheck) is opportunistic, low-risk, and prevents cross-cycle drift. Area D (cross-OS matrix) is independent of strict gate but closes a cycle-36 BACKLOG entry — including it preserves cycle-36's stated purpose. Area E (requirements split) is documentation-side only, has no test/CI impact, and the work is mechanical — deferring it costs nothing other than another BACKLOG entry; including it adds 4-7 new files for marginal benefit.

**Step 5 may overrule** — if the design eval surfaces complications in Area D (e.g., probe ubuntu reveals 20+ failing tests), Option C becomes the right call. The decision-gate Opus subagent has the final say.

---

## Cross-cutting brainstorm notes

**Lessons-learned applicable here:**

- **Cycle-18 L1 (snapshot-binding hazard):** AC5's mirror-rebind monkeypatch IS the cycle-18 fix pattern; nothing new.
- **Cycle-19 L1 (`module.X` reload-leak via importlib):** if any cycle-36 fix involves `importlib.reload`, watch for cycle-19 L1.
- **Cycle-22 L4 (cross-cycle CVE arrival):** AC18 explicit re-snapshot covers this.
- **Cycle-22 L3 (full-suite Step-10):** Step 10 must run `pytest -q` (full), not just changed-tests; this cycle's strict-gate change LITERALLY tests this.
- **Cycle-26 L2 (test-count narrative drift):** doc updates (AC25) must re-grep CLAUDE.md AND `docs/reference/testing.md` for stale counts.
- **Cycle-30 L3 (parallel test cases share assertion shape):** if AC11 enumerates 6 platform-specific tests, all 6 should use the same skipif marker shape.
- **Cycle-32 L2 (paired counter / resource acquire INSIDE try):** N/A this cycle (no source changes).
- **Cycle-34 L6 (CI workflow steps mirror):** if Step-10 introduces new shell commands locally, they MUST also exist in `.github/workflows/ci.yml`.
- **Cycle-35 L7 (CRLF/LF carryover):** if any test file edits trigger ruff format whitespace flags, normalize as a separate `chore(ruff, cycle 36)` commit.
- **Cycle-35 L8 (CI verification means `gh run watch` to completion):** Step-15 merge gate MUST poll the merge-commit CI to completion + check step-level conclusions.

**Risks not addressed in Step 1:**

- **Pre-existing local-only-passing tests:** there may be more tests beyond the BACKLOG-listed 3 fragility classes that were silently failing on CI under `continue-on-error`. The probe ubuntu run (Q5 Option B) doubles as a comprehensive scan.
- **pytest-timeout interaction with multiprocessing tests:** the cycle-23 test uses its own `acquired_event.wait(timeout=15.0)`. With pytest-timeout=120s, the multiprocessing test's internal timeout finishes first — fine. But if pytest-timeout fires mid-spawn, the kill semantics on Windows could leave zombie processes. AC2 skipif on CI sidesteps this entirely.
- **Cross-OS matrix doubles billing:** cycle 34 already noted concurrency.cancel-in-progress mitigates duplicate runs; matrix doubles per-PR cost. Acceptable for closing the cycle-36 BACKLOG entry.

---

## Recommendation summary for Step 4 design eval

| Q | Approach | Rationale |
|---|---|---|
| Q1 | A — skipif on CI for `test_cross_process_file_lock_timeout_then_recovery` | Spawn-bootstrap divergence on GHA-Windows is out of cycle 36 scope. |
| Q2 | B — `pytest-timeout = 120 s` global default + per-test override | Catches hangs without false-positives. |
| Q3 | A — mirror-rebind monkeypatch on `kb.config.WIKI_DIR` + peers | Maintains CI coverage; cycle-19 L1 pattern. |
| Q4 | A — `requires_real_api_key()` helper + skipif | Aligned with existing test mocking pattern. |
| Q5 | B — probe ubuntu first; skipif from real failures; then matrix | Data-driven enumeration. |
| Q6 | B — layered `-r requirements-runtime.txt` includes | Avoids pin duplication. |
| Q7 | B — drop Area E; ship A+B+C+D+F+G (~23 ACs) | Areas D + E are independent; D closes a cycle-36 BACKLOG entry; E is doc-only. |

**Open for Step 4 to escalate:**

- Q5 specifically — Option B requires a CI probe push. Step 4 may conclude C (defer Area D entirely) is safer if Option B's probe isn't feasible from the design phase.
- Q7 — if Step 4 design eval surfaces previously-unknown complications in Area B (e.g., the wiki-content tests don't actually accept mirror-rebind), the cycle scope may need to narrow further.
