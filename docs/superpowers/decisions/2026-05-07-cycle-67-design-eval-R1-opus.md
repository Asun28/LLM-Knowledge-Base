# Cycle 67 Design Eval — R1 (Opus 4.7)

**Date:** 2026-05-07
**Role:** Opus 4.7 main session, eng-mgr lens (`plan-eng-review` style — risk surface, telemetry, refactor blast radius).
**Scope:** 15 ACs at `2026-05-07-cycle-67-requirements.md` + brainstorm picks at `2026-05-07-cycle-67-brainstorm.md`.

## Analysis

The 15 ACs cluster into four risk classes:

1. **Pure-test additions** (AC02, AC08, AC09, AC15) — zero production change. Risk: vacuous-test class (cycle-11 L2, cycle-23 L2). Brainstorm and AC text already specify divergent-fail T*B tests.
2. **Workflow-only changes** (AC10, AC11) — CI yaml only. Risk: false-positive grep, comment leakage, regex over-match.
3. **New scripts + CI integration** (AC12, AC14) — produce reports today, become hard-fail gates later. Risk: transition path not specified for AC12 (warn-only → hard-fail).
4. **Library hardening** (AC01, AC03, AC04, AC05, AC06, AC07) — production code changes. Highest risk surface = AC03 (Popen refactor) and AC07 (new YAML config file).

I'll route my findings to the four classes most likely to land BLOCKERs.

## Verdict

**APPROVE-WITH-CONDITIONS.**

12 of 15 ACs are clean as specified. 3 ACs need pre-implementation conditions before Step 7 plan can lock: AC03 (Windows kill semantics + stdin starvation), AC04 (env-var truthiness handling), AC12 (warn-only → hard-fail transition path). All 3 are addressable with Step-5 inline resolutions; no re-architecture required.

## Findings

### R1-F1 (BLOCKER) — AC03 Popen approach must guard against stdin-write starvation

**AC:** AC03.
**Finding:** Brainstorm Approach A specifies "Two daemon threads (stdout + stderr) accumulate. Main thread calls `proc.communicate(input=stdin_input, timeout=timeout)`."

`proc.communicate(input=...)` internally uses its OWN stdout/stderr reader threads when both are PIPE. If we install our own daemon-thread readers AND call `communicate(input=...)`, communicate's internal threads conflict with ours — both read the same fd. Race: a chunk goes to one reader OR the other, non-deterministic.

**Suggested fix:** use `proc.stdin.write(stdin_input); proc.stdin.close()` (separately, possibly in another thread to avoid blocking on backend slow-read), then daemon-read stdout + stderr explicitly. `proc.wait(timeout=...)` for exit, NOT `communicate`.

**Trade-off:** more code, but no fd-read race. DeepSeek R2 may surface different angles on the same line.

### R1-F2 (BLOCKER) — AC03 must specify Windows kill grace and orphan-process risk

**AC:** AC03.
**Finding:** Brainstorm: "Use `proc.terminate()` then `proc.wait(timeout=2)` and on `TimeoutExpired`, `proc.kill()`."

On Windows, `terminate()` and `kill()` both call `TerminateProcess` (no SIGTERM grace; the API has no soft-kill). On POSIX, `terminate()` sends SIGTERM, `kill()` sends SIGKILL. The 2-second wait is meaningful only on POSIX.

For Windows: `terminate()` is effectively `kill()`. The 2-sec wait is wasted; we should do `terminate()` then `proc.wait(timeout=0.5)` only to allow the OS to clean up the handle. If wait times out, we can't `kill()` more aggressively (already killed).

**Suggested fix:** branch on `sys.platform.startswith("win")` — Windows: `terminate(); wait(0.5)` → log if still alive, accept. POSIX: `terminate(); wait(2)` → on `TimeoutExpired` → `kill(); wait(0.5)`.

### R1-F3 (MAJOR) — AC04 KB_STRICT_PUBLISH truthiness handling underspecified

**AC:** AC04.
**Finding:** Requirements doc says `If set to "1" or truthy non-empty, re-raise instead of swallow.`

Ambiguity: `KB_STRICT_PUBLISH=0` — strict-mode? `KB_STRICT_PUBLISH=false` — strict-mode? `KB_STRICT_PUBLISH= ` (whitespace) — strict-mode?

Cycle 64 AC6 / AC14 set the precedent: kill-switches read at call time and accept `"1"`, `"true"`, `"yes"` (case-insensitive). For SYMMETRIC ACs (kill-switch ON vs strict ON), use the SAME truthiness convention.

**Suggested fix:** specify in AC04: "Strict mode is enabled when `os.environ.get('KB_STRICT_PUBLISH', '').strip().lower() in ('1', 'true', 'yes')`. All other values (including `'0'`, `'false'`, `'no'`, empty, missing) leave default suppress-on-error behavior unchanged." Same convention as AC06 KB_DISABLE_VECTORS.

### R1-F4 (MAJOR) — AC12 warn-only → hard-fail transition path is unbounded

**AC:** AC12.
**Finding:** "If audit produces N>0 offenders today, AC12 splits: (i) script lands as a tool; (ii) CI fail-on-offenders deferred to a follow-up cycle."

This punts a real gate to "future cycle" without commitment. Without a deadline, the BACKLOG entry rots and the audit becomes vestigial.

**Suggested fix:** Step 7 plan MUST run the audit FIRST and report N. If N==0, ship hard-fail mode immediately (cleaner). If N>0, ship warn-only AND open BACKLOG entry under "Phase 6 R2 (cycle-67 carryover)" with explicit text: "AC12 hard-fail mode pending zero offenders; expected cycle 68-70."

Step 5 condition: design gate verdict requires Step 7 to make the audit-N call up front, not defer.

### R1-F5 (MAJOR) — AC07 PyYAML dep verification missing from plan

**AC:** AC07.
**Finding:** Brainstorm: "PyYAML is already a transitive dep (confirm via `python -c 'import yaml; print(yaml.__version__)'`)."

If it's NOT transitively present in the runtime env, AC07 silently broadens deps. Tests may pass on a dev machine where PyYAML is installed via Anthropic SDK, but `pip install kb` in a different SDK config breaks lint.

**Suggested fix:** Step 7 plan first task — verify `yaml` import in vanilla `pip install kb` install (no extras). If absent, add `PyYAML>=6.0` to `kb` install_requires (NOT `[lint]` extra) so external installers always have it. Document in CHANGELOG.

### R1-F6 (MAJOR) — AC03 stderr-pipe deadlock risk under high stderr volume

**AC:** AC03.
**Finding:** Brainstorm acknowledges Approach B (selectors) has stderr deadlock risk; Approach A is picked. But Approach A's stderr cap behavior is underspecified.

Current `subprocess.run` captures full stderr and slices `[:500]` after process completes (cli_backend.py:230). Replacement Popen path needs an EQUIVALENT stderr cap (any value < `MAX_CLI_STDOUT_BYTES` is safe; 64KB matches stdout chunk size).

**Suggested fix:** specify in AC03 — stderr daemon thread caps at 64KB total (one chunk) and discards the rest, OR caps at `min(MAX_CLI_STDERR_BYTES, MAX_CLI_STDOUT_BYTES)` if a separate constant exists (none today; introduce `MAX_CLI_STDERR_BYTES = 64 * 1024` in config.py for symmetry). Pin a test for backend that writes 1 MB to stderr: subprocess does NOT block, stderr returned has length ≤ cap.

### R1-F7 (MINOR) — AC09 paired negative-control should distinguish data mutation from rendering mutation

**AC:** AC09.
**Finding:** Requirements doc lists T09-A (mutate input) and T09-B (mutate rendering function). Both are "regression-revert guards" but they catch DIFFERENT classes:
- T09-A catches: input field is no longer read by the renderer
- T09-B catches: renderer no longer transforms input correctly

Brainstorm doc treats them interchangeably. If only ONE is added per snapshot, which?

**Suggested fix:** specify in AC09 — both T09-A AND T09-B are required PER SNAPSHOT. Otherwise the snapshot has only one direction of regression coverage.

### R1-F8 (MINOR) — AC11 `sk-ant-dummy` regex too narrow on PR review side

**AC:** AC11.
**Finding:** Suggested CI step: `git ls-files | xargs grep -l "sk-ant-dummy"`. If the dummy key is documented in a different file (e.g. `SECURITY.md` describing CI's dummy-key posture), the step fails on a legitimate documentation reference.

**Suggested fix:** Step 7 plan grep-verify `sk-ant-dummy` against current tracked files BEFORE writing AC11 CI step. If matches found in legitimate docs (SECURITY.md, README.md), tighten regex to match the exact dummy-key value `sk-ant-dummy-key-for-ci-tests-only` (or the literal key value used in ci.yml) and add an allowlist for grep-step exclusions: `grep -v "^SECURITY\.md$"`.

Better: extract the dummy-key value from ci.yml dynamically: `dummy=$(grep -oP "sk-ant-dummy[^\s\"']*" .github/workflows/ci.yml | head -1)`, grep for that exact string, exclude ci.yml only.

### R1-F9 (MINOR) — AC02 AST-grep test should also catch `import kb.graph.cache as gc; gc.get_graph(...)` aliased form

**AC:** AC02.
**Finding:** Test pattern `ImportFrom(module="kb.graph.cache", names=[alias(name="get_graph")])` catches `from kb.graph.cache import get_graph`. Does NOT catch:
1. `import kb.graph.cache as gc; gc.get_graph(...)` — aliased module form
2. `from kb.graph import cache as gc; gc.get_graph(...)` — submodule alias

Both are valid attribute-lookup forms (cycle-18 L1 compliant — they hit the patched module attribute), so they're fine. But if AC02's purpose is "discourage from-import", the test should be precise.

**Suggested fix:** clarify AC02 docstring — only `from kb.graph.cache import get_graph` is forbidden. Aliased forms (`import kb.graph.cache as gc`) are FINE because `monkeypatch.setattr(kb.graph.cache, "get_graph", ...)` reaches them via attribute on the module. Pin a positive test that proves an aliased form is NOT a finding.

### R1-F10 (NIT) — Commit order suggested in requirements doc could group AC11 + AC10 ahead of AC09

**AC:** Cross-cutting (commit ordering only).
**Finding:** Requirements suggested commit order:
4. AC09 (snapshot paired negative-control)
5. AC11 (CI dummy-key grep)
6. AC10 (CI snapshot-update reject)

If AC09 lands before AC10/AC11, snapshot-update is still permitted in CI. A maintainer landing AC09 + accidentally including `--snapshot-update` to bypass T09-B's divergent-fail would slip through.

**Suggested fix:** swap to AC10 → AC11 → AC09 order. Workflow-only changes (AC10/AC11) are tiny and can land first; AC09 then lands knowing CI cannot mask its divergent-fail.

## CONDITIONS list

Step-9 implementation MUST honor:

1. **C1** (R1-F1) — AC03 implementation: do NOT use `proc.communicate(input=...)` together with daemon-thread readers. Use `proc.stdin.write/close` + daemon stdout+stderr readers + `proc.wait()`. Pin a test where backend reads stdin slowly while writing >cap to stdout: subprocess does NOT deadlock.

2. **C2** (R1-F2) — AC03 platform-branch: Windows path uses `terminate(); wait(0.5)`; POSIX path uses `terminate(); wait(2); kill()`. Pin tests for both branches if possible (CI matrix is currently ubuntu-latest only; Windows test is local-only manual verification).

3. **C3** (R1-F3) — AC04 truthiness convention: `KB_STRICT_PUBLISH` accepts `'1'`, `'true'`, `'yes'` (case-insensitive). Symmetric with AC06's `KB_DISABLE_VECTORS`. Pin the case-insensitive test.

4. **C4** (R1-F4) — AC12 transition path: Step 7 plan FIRST runs audit, reports N. If N==0, ship hard-fail. If N>0, ship warn-only AND open BACKLOG entry with cycle-68-70 expected-resolution. The defer is bounded.

5. **C5** (R1-F5) — AC07 PyYAML dep: verify `yaml` import is reachable from a vanilla `pip install kb` install (no extras). If not, add `PyYAML>=6.0` to install_requires AND document.

6. **C6** (R1-F6) — AC03 stderr cap: stderr daemon thread caps at `MAX_CLI_STDERR_BYTES` (introduce constant matching stdout chunk size). Pin a test for stderr-only volume.

7. **C7** (R1-F7) — AC09 dual coverage: each snapshot subject gets BOTH T*A (input mutation) AND T*B (renderer mutation) tests.

8. **C8** (R1-F8) — AC11 grep dynamic value extraction: pull dummy-key value from ci.yml at run-time; exclude ci.yml from the grep target; don't hardcode `sk-ant-dummy` literal in the grep pattern (use the FULL value to avoid false-positives in docs).

9. **C9** (R1-F9) — AC02 docstring: clarify "from-import is forbidden, aliased imports are fine"; add a positive test for aliased form.

10. **C10** (R1-F10) — commit order swap: AC10 → AC11 → AC09 to ensure CI cannot mask AC09's divergent-fail.

## New ACs proposed

None. The 15 ACs are scoped correctly. Each finding fits into existing AC scope as an implementation condition.

## Anti-vacuous-test verification

Per cycle-22 L5: each CONDITIONS bullet maps to a Step-9 sub-AC pin:
- C1 → AC03 sub-test "stdin-write-during-stdout-overflow does not deadlock"
- C2 → AC03 sub-test "Windows / POSIX kill-grace branch"
- C3 → AC04 sub-test "truthy variants {1, true, yes, TRUE}"
- C4 → Step-7 plan first-task: run audit; ship correct mode
- C5 → Step-7 plan task: verify PyYAML
- C6 → AC03 sub-test "1 MB stderr cap"
- C7 → AC09 sub-test "dual coverage per snapshot"
- C8 → AC11 sub-test "doc reference of `sk-ant-dummy` substring does NOT trigger"
- C9 → AC02 sub-test "aliased import form does NOT trigger"
- C10 → no test pin needed; ordering is git-graph evidence

All conditions test-pinned. Step 5 decision gate inherits this verifier checklist.

## Trade-offs flagged

- AC03's platform-branch implementation adds ~10 LoC vs the brainstorm's "do the same on both" simple path. Offset by failure-mode reduction.
- AC04's truthiness convention costs ~5 LoC for the `.lower() in ()` check vs the brainstorm's "any non-empty truthy". Offset by symmetry with AC06 — both env-var ACs follow the same rule, easier to remember.
- AC12's warn-only mode is a temporary state. Cycle-68-70 needs the BACKLOG follow-through; if it slips beyond cycle 70, it's a soft-rot signal.
