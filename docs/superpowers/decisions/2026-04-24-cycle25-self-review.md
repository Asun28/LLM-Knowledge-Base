# Cycle 25 Self-Review

**Merged:** 2026-04-24 as `d429970` (PR #39 squash)
**Branch:** `feat/backlog-by-file-cycle25` (deleted)
**Scope:** 10 AC across 4 clusters (rebuild_indexes .tmp / dim-mismatch observability / compile_wiki in_progress markers / BACKLOG+CVE re-verify)
**Shipped:** 2 src files modified, 3 new test files, 6 commits, +14 tests (2768 → 2782)

## Scorecard

| Dimension | Result |
|---|---|
| AC coverage | 10/10 + CONDITION 13 |
| R1 findings | 1 BLOCKER (Codex) + 1 MAJOR (Sonnet) |
| R1 fix latency | Both fixed in same commit (31d3cc9) |
| R2 verification | APPROVE, no new findings |
| R3 synthesis | APPROVE with 1 NIT (doc count drift) |
| Full-suite green at merge | 2773 passed + 9 skipped, 0 failed |
| Dep-CVE diff | 0 new (only pre-existing ragas LOW) |

## What Worked

- **Snapshot-inside-stub AC6 test.** The R1 Sonnet MAJOR fix taught the cycle: the strongest AC6 regression test captures manifest state INSIDE the `ingest_source` monkeypatch stub, not only after the production code re-raises. Under AC6 revert, the snapshot is empty → divergent-fails. Under the final-state-only test the AC6 revert would silently pass because the `except` handler writes `failed:` unconditionally. Added as L2 below.
- **R1 parallel Codex+Sonnet caught two orthogonal issues.** Codex focused on control-flow coverage (incremental path missing exemption); Sonnet focused on test determinism (revert tolerance). Neither would have caught the other finding — parallel review was load-bearing.
- **Primary-session plan drafting (cycle-14 L1).** 10-AC plan drafted in ~8 min without dispatching Codex. Step-8 plan-gate still caught 3 amendments (TASK 3 truncation, CLAUDE.md missing concurrent-noise doc, TASK 4 missing AC10 test). Heuristic holds.
- **Primary-session implementation (cycle-13 L2).** All 4 tasks shipped in-primary: total <300 lines across src/tests. Dispatch overhead would have dominated.

## What Hurt

- **CONDITION 13 exemption shipped to ONE prune site but missed the OTHER.** `compile_wiki` has TWO prune sites: the full-mode tail (where the AC/CONDITION text pointed) AND `find_changed_sources` called on the incremental path. Design-gate text named CONDITION 13 only at the tail; Step-9 implementation followed the text literally; R1 Codex found the miss in under 5 minutes by running `kb compile` mentally through incremental vs full. **Skill lesson L1 below.**
- **Doc test-count drift (+13 claimed vs +14 actual).** CHANGELOG and CLAUDE.md claimed 2768 → 2781 (+13). Actual 2768 → 2782 (+14). R3 Sonnet caught. Root cause: mid-implementation added 1 regression test (`test_incremental_prune_exempts_in_progress_markers`) during the R1 Codex fix without updating the Step-12 doc pass. **Skill lesson L3 below.**
- **Commit count also off (4 claimed vs 6 shipped).** Same root cause — Step-12 doc pass ran before R1 fixes landed. Fixed atomically with the test-count NIT commit.

## Skill Patches (L1-L3)

### L1 — CONDITION exemptions must enumerate ALL prune sites

When a design-gate CONDITION carves out an exemption for a specific manifest-value pattern (cycle-25 CONDITION 13: `in_progress:` markers survive the prune), the Step-7 implementation plan MUST grep for EVERY site that prunes the manifest, not just the one named in the CONDITION text.

Concrete grep template:
```bash
rg "deleted_keys|\.pop\(.*rel_path|del manifest\[|del\s+\w+\[k\]" src/
```

For cycle 25, this would have surfaced both `find_changed_sources` (L182-191) AND `compile_wiki` tail (~L494) as manifest-mutation sites. The plan must explicitly list each site and assert the CONDITION exemption is applied there.

**Plan-gate check addition:** for every CONDITION that exempts a value prefix from a prune, the plan MUST enumerate ALL `manifest.pop` / `del manifest[...]` / `deleted_keys` sites and show the exemption predicate is threaded through each. Otherwise the Step-9 implementer will follow the CONDITION text literally and miss the sibling site.

Cycle 25 evidence: R1 Codex caught this in <5 min because a mental trace of `kb compile` (default incremental) immediately routed through `find_changed_sources` — a path the CONDITION text never named. The primary session had read the full-mode prune correctly but stopped there.

### L2 — Revert-tolerant AC tests need pre-action state capture inside the stub

When the AC under test is "write state X BEFORE calling operation Y" and the `except` handler writes a superseding state Z, a test that monkeypatches Y to raise and only asserts the final Z-state is REVERT TOLERANT — removing the AC X-write still leaves Z intact, so the test passes.

Strengthening pattern:
```python
snapshot: dict = {}
def _raise_and_snapshot(*args, **kwargs):
    snapshot.update(load_state_from_disk())  # capture Y's input state
    raise RuntimeError("simulated failure")
monkeypatch.setattr(owner_module, "operation_Y", _raise_and_snapshot)
operation_Y_caller(...)
# Pre-exception snapshot: AC-required state X must be present.
assert snapshot[key].startswith("X:"), "AC revert detection"
# Final state: except handler's Z still assertable.
final = load_state_from_disk()
assert final[key].startswith("Z:")
```

The snapshot captures disk state INSIDE the monkeypatched stub before the raise. Under AC revert, the state at call time lacks X, divergent-failing the snapshot assertion while the final-state assertion would still pass. This pattern generalises to any "pre-operation marker" contract (in_progress markers, lockfiles, provisional rows, staged manifest writes).

Cycle 25 evidence: `test_exception_during_ingest_overwrites_marker_with_failed` was revert-tolerant until R1 Sonnet flagged it. Post-fix, reverting AC6 produces `AssertionError: source_key is None` from the snapshot, not a silent pass.

### L3 — Doc pass MUST run AFTER R1 fixes, not before

The feature-dev Step-12 doc update pass runs after Step 11 security verify but before Step 13 PR. If Step 14 R1 review introduces fixes that add tests, the doc test-count + commit-count become stale before merge.

Two mitigations:

1. **Re-run the Step-12 count snippet as part of every R1 fix commit.** Simple bash: ```git log --oneline main..HEAD | wc -l``` for commits, ```.venv/Scripts/python -m pytest --collect-only -q 2>&1 | grep "^\d* tests collected" ``` for tests. Both are cheap.
2. **Strip counts from CHANGELOG entries during Step-12 and fill them in Step-15 (post-merge).** Move the count refresh to the merge-cleanup step so there's no drift window.

Recommend option 1 because CHANGELOG entries drifting at merge time break `git log` archaeology — a count in the commit message is more truthful than a retroactively-patched one.

Cycle 25 evidence: Step-12 doc claimed +13 tests / 4 commits. R1 Codex fix added 1 test; R1 Sonnet fix added 0 tests but 1 commit; R3 NIT fix added 0 tests but 1 commit. Final truth: +14 tests / 6 commits. R3 Sonnet caught both drifts in one pass; fix commit was 3 Edit calls (CHANGELOG, CHANGELOG-history, CLAUDE.md).

## Metrics

- **Cycle wall-clock time:** ~7h from `/feature-dev` invoke to merge (with two sleep gaps during Codex polling).
- **Primary session vs subagent time ratio:** Primary ~70% (plan + impl + R1 fixes + docs), Subagents ~30% (threat model, design eval R1+R2, design gate, plan gate, Step-11 security, R2 Codex verify, R3 Sonnet synthesis).
- **R1 → R3 pipeline:** 3 reviews, 2 fixes, 1 NIT — matches cycle-22+ pattern where R3 typically finds count/doc drift rather than logic issues.
