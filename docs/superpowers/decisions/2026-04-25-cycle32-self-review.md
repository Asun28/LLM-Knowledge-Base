# Cycle 32 Self-Review (Step 16)

**Date:** 2026-04-25 · **PR:** [#46](https://github.com/Asun28/llm-wiki-flywheel/pull/46) · **Merge commit:** `a99932a`

**Branch:** `feat/backlog-by-file-cycle32` (deleted post-merge) · **Commits on main:** 10 · **New tests:** 2882 → 2901 (+19).

## Scorecard (Steps 1-15)

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | yes | yes | — |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval (R1 Opus + R2 Codex) | yes | **no** | R2 Codex hung >12 min (cycle-20 L4 fallback); primary manual-verify caught `core.py:535` UTF-8-ratio misread |
| 5 — Design decision gate (Opus subagent) | yes | **no** | Opus subagent `a5b27485f305ef56b` hung >10 min; primary synthesis fallback per cycle-20 L4 |
| 6 — Context7 verification | yes | yes | — |
| 7 — Implementation plan (primary session) | yes | yes | Cycle-14 L1 — primary session held full context; plan drafted directly |
| 8 — Plan gate | yes | **no** | Codex plan-gate hung >8 min; primary-session inline plan-review per cycle-21 L1 |
| 9 — Implementation (TDD) | yes | **no** | TASK 2 probabilistic fairness test failed at 2/10 trials on Windows (15.6ms scheduler tick vs 2ms stagger); pivoted to deterministic counter-invariant test — see L1 below |
| 10 — CI hard gate | yes | yes | One transient flake on `test_persist_contradictions_concurrent`; clean on re-run |
| 11 — Security verify + PR-CVE diff | yes | **no** | PR-CVE diff surfaced 2 new advisories (litellm GHSA + pip CVE); bump blocked by click<8.2 transitive conflict, narrow-role exception documented |
| 11.5 — Existing-CVE opportunistic patch | yes | yes | No patchable advisories (diskcache + ragas both `fix_versions: []`) |
| 12 — Doc update (Codex subagent) | yes | yes | +TBD placeholder for commit count per cycle-30 L1 |
| 13 — Branch finalise + PR | yes | yes | — |
| 14 — PR review (R1 Codex + R1 Sonnet parallel, R2 Codex) | yes | **no** | R1 Codex REQUEST-CHANGES (counter-leak window + test doesn't pin integration); R1 Sonnet APPROVE with 2 MAJORs (C6 design-doc waiver gap, underflow-test fragility) — 5 MAJORs total; R2 Codex APPROVE after fixes |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes | 2 late-arrival Dependabot alerts (#13, #14) — both pre-documented in BACKLOG from Step 11 PR-CVE diff, informational only |

## New skill-patch lessons

### L1 — Timing-primitive tests MUST verify signal-vs-scheduler-resolution at Step 5

**Context:** Cycle-32 AC7 design was `max_workers=3, 10 trials, 80% tolerance` probabilistic fairness with `_FAIR_QUEUE_STAGGER_MS=2.0`. On Windows the default timer-tick is 15.6ms (the `GetSystemTimeAdjustment` default); the 2ms stagger is below resolution, so thread wake-ups are effectively simultaneous regardless of position. The observable fairness was 2/10 trials (20%), well below the 80% threshold. This didn't surface until Step 9 TDD-red; design doc's Q5 Analysis block said "below Windows coarse-timer default (15.6ms) but within `time.perf_counter()` microsecond resolution" — but `time.perf_counter()` measures elapsed time, NOT scheduler wake granularity. Confusing the two is a subtle trap.

**Rule:** when a design-gate CONDITION prescribes a probabilistic test on a timing primitive (jitter, stagger, retry backoff, delay distribution), the Step-5 Analysis block MUST include a REPL-verified probe of signal-vs-platform-resolution. Concrete probe pattern:

```python
import time
# For thread-wake signal: what's the coarse tick on this platform?
import platform
if platform.system() == "Windows":
    # Default ~15.6ms; can be lowered via timeBeginPeriod(1)
    print("Windows scheduler tick: ~15.6ms (Waitable-timer resolution)")
else:
    # Linux CONFIG_HZ typically 250 → 4ms; with HR_TIMER → ~1us
    with open("/proc/timer_list") as f:
        # inspect hrtimer resolution
        pass
```

If the designed signal (the stagger value, the jitter bound, etc.) is smaller than the platform's coarse-tick scheduler resolution, the probabilistic test CANNOT observe the signal — rewrite the CONDITION to specify a deterministic counter/position-correctness assertion instead. Cycle-32 evidence: the `_FAIR_QUEUE_STAGGER_MS=2.0` signal was sub-resolution on Windows; the deterministic `test_fair_queue_positions_unique_and_zero_based` (counter contract) replaced it; R1 Codex PR review then added the deterministic `test_fair_queue_stagger_integrates_with_file_lock` (monkeypatched `time.sleep` recording) as the integration-pin anchor.

**Self-check at Step 5:** for every CONDITION that includes a numeric timing value, identify the platform(s) the test must pass on and cross-check the numeric value against that platform's scheduler tick / wake granularity. Flag sub-resolution signals as a DESIGN-AMEND requiring a deterministic alternative.

**Generalises:** cycle-24 L4 (position-assertions for security-class revert-tolerance) to timing-class signal-vs-resolution mismatches. Both share "the test can silently pass on the wrong axis."

### L2 — Paired counter/resource acquisition MUST live INSIDE the outer try with a `slot_taken` guard

**Context:** Cycle-32 AC6 `file_lock` originally placed `position = _take_waiter_slot()` BEFORE the outer `try:` block. The paired `_release_waiter_slot()` in `finally:` correctly fires on all exception paths ONCE the try body is entered — but a `KeyboardInterrupt` landing between the helper's increment (inside `_take_waiter_slot`'s `with _LOCK_WAITERS_LOCK:`) and the try-entry would leak the counter permanently. Initial design rationalized "atomicity inside the helper is sufficient" — it's not, because the helper RETURN followed by try-ENTRY is a window that async signals can interrupt.

**Rule:** any paired counter/resource acquisition whose release is in a `finally:` block MUST use one of these two shapes:

```python
# Shape A (preferred): take INSIDE try, guard release with flag.
slot_taken = False
try:
    resource = _acquire_resource()  # may raise; that's fine — finally won't release
    slot_taken = True
    # ... body ...
finally:
    if slot_taken:
        _release_resource()
```

```python
# Shape B: take in a pre-try context manager whose __exit__ releases.
with _managed_acquisition() as resource:
    # ... body ...
# __exit__ is THE release; no separate finally needed.
```

**NEVER this shape:**
```python
# BROKEN: KeyboardInterrupt between acquire and try-entry leaks the counter.
resource = _acquire_resource()
try:
    # ... body ...
finally:
    _release_resource()
```

**Self-check at Step 9 TDD:** for any new helper pairing atomic increment + `finally`-decrement (or acquire/release on any resource), grep your diff for `<helper>\(\)\s*\n\s*try:` — a newline-separated acquire then try-entry is Shape C. Refactor to Shape A with a `slot_taken` / `resource_acquired` flag.

**Generalises:** Python's asyncio `@asynccontextmanager` documentation warns about this exact window; the lesson is the same for threading-based paired-resource helpers. Cycle-32 R1 Codex MAJOR 1 was the concrete catch.

### L3 — Deterministic replacement tests MUST pin the INTEGRATION, not just the contract

**Context:** When cycle-32 TASK 2's probabilistic fairness test couldn't fire on Windows (L1 above), I replaced it with `test_fair_queue_positions_unique_and_zero_based` — a deterministic test of the `_take_waiter_slot` / `_release_waiter_slot` counter contract. R1 Codex PR review correctly flagged: the counter-contract test would still pass if the `if position > 0: time.sleep(stagger_s)` call inside `file_lock` were removed. The deterministic test covers the atomic-counter PRIMITIVE, not the PATH-FROM-PRIMITIVE-TO-BEHAVIOUR. Revert of the stagger-sleep integration leaves the primitive test green.

**Rule:** when replacing a probabilistic integration test with a deterministic contract-primitive test (because the probabilistic signal is sub-resolution per L1, or because CI flakiness makes it unreliable), add AT LEAST ONE additional deterministic test that pins the specific integration-path call site. Concrete pattern for timing primitives:

```python
def test_<primitive>_integrates_with_<consumer>(monkeypatch):
    """Pin the integration path: consumer MUST invoke the primitive
    with the computed value at the expected call site."""
    recorded: list[float] = []
    real_sleep = module.time.sleep

    def fake_sleep(duration: float) -> None:
        recorded.append(duration)
        real_sleep(0)

    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    # Seed the primitive state so integration path fires.
    with module._PRIMITIVE_LOCK:
        module._PRIMITIVE_STATE = <value that triggers the path>
    # Call the consumer — uncontended / happy-path.
    module.consumer_function(...)
    # Assert the FIRST primitive-consuming call matches the expected formula.
    assert recorded[0] == <expected value from primitive state + config>
```

Without such a test, the probabilistic replacement covers the PRIMITIVE contract but not the PRIMITIVE → CONSUMER wiring; a refactor removing the wiring passes CI and ships silently.

**Self-check at Step 9 TDD:** for any probabilistic test replaced with a deterministic contract test, ask "does reverting the CONSUMER'S use of the primitive break any assertion?" If no, add an integration-path pin test via monkeypatch-recorder-then-assert pattern.

**Generalises:** cycle-24 L4 "content-presence assertions are revert-tolerant" — deterministic-contract replacements for probabilistic tests are a specific instance of the same class. The primitive contract holds; the integration contract doesn't, unless separately pinned.

## Meta-observations (not skill patches)

- **Hanging-agent pattern now canonical:** cycle-32 had THREE hangs (R2 Codex design eval, Step 5 Opus decision gate, Step 8 Codex plan-gate). Each fallback to primary session worked cleanly. The 10-min threshold (cycle-20 L4) is load-bearing — without it, cycle 32 would have burned 30+ min waiting for subagents that would have returned misleading output. Fallback-authority rule (cycle-27 L3) also held: the Step-5 decision gate's killed Opus agent surfaced the `core.py:535` UTF-8-ratio misread in its final output before termination — primary manual-verify was authoritative. No information loss.

- **Primary-session plan-gate is load-bearing for small cycles:** 4 AC cycle with full context → cycle-14 L1 primary plan + cycle-21 L1 primary plan-gate kept velocity up. Dispatch overhead for small batches is always higher than implementation cost.

- **R1 Codex's "MAJOR 2" class (test doesn't cover the integration):** this cycle's R1 Codex caught the same gap class that cycle-23 L2 (stub return-type), cycle-24 L4 (position assertions), and cycle-28 L2 (counter-stability baseline) all targeted — "what you're testing isn't what you need to pin." L3 above formalizes this for the deterministic-replacement case.
