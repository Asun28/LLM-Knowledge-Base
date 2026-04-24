# Cycle 29 — Step-16 Self-Review

**Date:** 2026-04-24
**Cycle:** 29 (Backlog-by-file hygiene — `rebuild_indexes` audit + PROJECT_ROOT override validation + BACKLOG deletes)
**Merge commit:** `e52360d` (PR #43)
**Branch commits (pre-merge):** 6 + merge = 7 total landed on main
**Test delta:** 2809 → 2826 (+17 new tests)
**New test files:** 2 (`tests/test_cycle29_rebuild_indexes_hardening.py`, `tests/test_cycle29_backlog_hygiene.py`)

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements | yes | yes | — |
| 2 Threat model + CVE baseline | yes | yes | — |
| 3 Brainstorming | yes | yes | — (structured approach-generator per feedback_auto_approve) |
| 4 Design eval R1 Opus + R2 Codex | yes | yes | — (both returned in ~4-8 min) |
| 5 Design gate (Opus) | yes | yes | 15 decisions resolved, 15 CONDITIONS emitted, PROCEED |
| 6 Context7 | skipped (stdlib-only) | — | — |
| 7 Plan (primary) | yes | yes | — (cycle-14 L1 applied: operator held full context from Steps 1-5) |
| 8 Plan gate (Codex) | yes | yes | APPROVE, 0 gaps, 0 notes |
| 9 Implementation (primary per cycle-13 L2) | yes | no | one early bug — `Path(hash_manifest)` wrapping stripped `_ResolvingPath` subclass; caught by pre-commit test run; fixed before commit |
| 10 CI gate | yes | yes | 2815 passed + 10 skipped; ruff clean |
| 11 Security verify + PR-CVE diff | yes | yes | APPROVE-WITH-PARTIAL (T1 unbounded-OSError input-bounds gap filed as new MEDIUM BACKLOG per cycle-12 L3); PR-CVE diff empty |
| 11.5 Existing-CVE patch | skipped (no patchable advisories — diskcache + ragas both `fix_versions: []`) | — | — |
| 12 Doc update (primary) | yes | yes | CLAUDE.md dual-site test-count sync per cycle-26 L2 |
| 13 Branch finalise + PR | yes | yes | PR #43 opened cleanly |
| 14 PR review R1 (+ R2) | yes | no | R1 Sonnet S1 caught a regression I didn't pre-anticipate (cross-platform `Path("") == Path(".")` semantic invalidates Q7-A); R2 caught design-doc Q15 count drift + C4 grep-wording gap |
| 15 Merge + CVE warn | yes | yes | No late-arrival advisories during cycle span |
| 16 Self-review + skill patch | in-progress | — | — |

## What worked

- **Parallel R1 Opus + R2 Codex design eval returned BEFORE the 270s wake budget this cycle.** R1 Opus back in ~4.5 min, R2 Codex in ~8 min. Cycle-24 L5 default of 270s wake + 60s polling grace was correct; needed only one extra 240s follow-up wake for R2 Codex.
- **Primary-session plan per cycle-14 L1 was quick (~8 min).** Design gate resolved 15 Qs before plan draft; plan-gate APPROVE with 0 gaps confirmed the primary held enough context.
- **Cycle-13 L2 primary-session implementation was the right call for 5 ACs with <150 LOC combined impl+test.** All 4 impl tasks committed in under 20 minutes; no Codex dispatch round-trip overhead.
- **`_ResolvingPath(type(Path()))` subclass pattern (design Q8 hybrid) portably exercised the dual-anchor divergence test on both POSIX and Windows** without requiring real `os.symlink` privilege. The paired decorator-skip `os.symlink` test covers real on-disk escape on POSIX CI.
- **Step-11 PARTIAL handling per cycle-12 L3 avoided scope creep.** T1 input-bounds gap (unbounded OSError → `wiki/log.md`) was correctly filed as a new MEDIUM BACKLOG rather than expanding AC1 scope at Step 11.
- **R1 review caught a real cross-platform regression.** The `Path("") == Path(".")` semantic (Sonnet S1) meant the Q7-A "empty reject" design decision was fundamentally ill-specified — both operands stringify to `"."` and resolve to CWD. R1 Sonnet's live-REPL confirmation was essential; I would have shipped with a broken empty-path check otherwise.

## What hurt

- **Q7-A design decision had no cross-platform grounding.** The Step-5 decision gate recommended "explicit `Path("") → raise` per cycle-19 L3", but `Path("")` and `Path(".")` are the SAME Path object in Python pathlib on both platforms (they compare equal, stringify identically). The design gate didn't test the assumption with a REPL probe — ironic given cycle-16 R2 L-style "reproduce the failure mode before writing the regression test". The fix: remove the check, document cross-platform equivalence, trust the downstream resolve-anchor. Net: one R1 round-trip and one R1-fix commit.
- **Q15 test-count projection was off by 3 (2823 projected vs 2826 actual).** Cycle-23 L4 count-drift rule applied — R1 S1 added 1 new test post-fix, and the Q8 hybrid split into 2 tests (not 1 as Q15 assumed). R2 Codex S2 correctly caught the design-doc annotation's 1-drift (2825 vs 2826). Mitigation going forward: leave `+TBD` placeholders in design Q15 and backfill after Step 9 OR bump atomically with each fix commit (cycle-25 L3 alternative).
- **C4 CONDITION literal grep spec was over-constrained.** Cycle-26 L3 rule says spec CALL-SHAPE, not TEXT-SHAPE — but Q9 wrote `rg 'kb.compile.compiler.PROJECT_ROOT' tests/...` expecting ≥5 hits. Shipped `_patch_project_root` helper factored the patching from 14 test functions down to 1 helper call; literal grep returns 1 hit (docstring). Functional coverage equivalent. R2 Codex correctly classified as cycle-26 L3 cosmetic wording gap. Mitigation: future CONDITION grep specs must probe the helper FUNCTION NAME (`_patch_project_root`, `_seed_wiki_and_data`, etc.) OR use AST-walk.
- **Initial TASK 2 implementation wrapped the override Path via `Path(hash_manifest)` before calling the helper**, stripping the `_ResolvingPath` subclass dispatch and silently making the dual-anchor divergence test pass on a trivial call. Caught by the pytest red→green transition (the symlink-escape test remained RED). Fixed by passing `hash_manifest` directly. Self-check: any time I call `Path(x)` on a Path-typed argument, ask "does this strip a caller subclass?"

## Surprises / cycle-30 preview

- The remaining pre-Phase-5 BACKLOG items are all architectural (config.py 35-constant split, pipeline-orchestrator rename, async-def MCP conversion for 28 tools, `file_lock` fair-queue, CLI ↔ MCP parity for ~14 tools, tests/ freeze-and-fold, conftest sandbox-by-default, graph caching policy, tests/ snapshot testing, ingest state-store fan-out receipt). Each needs a dedicated design pass. Cycle 30 could pick one — most tractable is probably `config.py` split (mechanical, clear refactor boundary) or `tests/conftest.py` sandbox-by-default (test-infra only, no production surface risk).

## Skill patches

Three patches from this cycle's Step-14 rework:

### L1 — Cross-platform Python `Path("")` semantic equivalence is a design-gate trap (cycle-29)

**Problem:** Cycle 29 Step-5 design-gate Q7 decided "explicit `Path("") → raise` as an empty-input reject" per cycle-19 L3. R1 Sonnet caught that `Path("") == Path(".")` evaluates True on BOTH POSIX and Windows Python 3.x; both stringify to `"."` and `.resolve()` to CWD. Any "empty path reject" check therefore falsely rejects legitimate `Path(".")` inputs. The design gate didn't test the assumption.

**Rule:** When a design-gate Q proposes a Path-equality or Path-identity check (e.g., `path == Path("")`, `path.name == ""`, `not path.parts`), the Analysis block MUST include a REPL-verified probe of the discriminator against BOTH `Path("")` AND `Path(".")` AND `Path.cwd()` on the current platform. Example probe:

```python
>>> from pathlib import Path, PurePosixPath, PureWindowsPath
>>> Path("") == Path(".")
True  # cross-platform — no discriminator at Path level
>>> str(Path("")), str(Path("."))
('.', '.')  # no string-rep discriminator
>>> Path("").parts, Path(".").parts
((), ())  # no parts discriminator
```

The ONLY discriminator available BEFORE Path construction is the raw string input (`if not user_input.strip(): raise`), which requires threading the string through the helper signature. If the helper only accepts `Path`, the discriminator is already lost — remove the check and rely on downstream semantics.

**Self-check at Step 5:** for any validator AC that includes a Path-equality early-return, add a CONDITION requiring the Step-5 Analysis block to cite a REPL probe. Cycle-29 Q7 would have flipped to "fall through to resolve-anchor" (Q7-B) instead of "explicit reject" (Q7-A), saving the R1-fix round.

Generalises cycle-19 L3 (empty-input validator skip) with a cross-platform caveat: the advice holds for string validators, but fails for `Path` validators because `Path("")` has no distinguishing property.

### L2 — Path-subclass dispatch strip via `Path(caller_arg)` wrapping (cycle-29)

**Problem:** Cycle 29 TASK 2 implementation wrapped `hash_manifest` via `Path(hash_manifest)` before calling `_validate_path_under_project_root(...)`. The `_ResolvingPath(type(Path()))` subclass used in `test_hash_manifest_override_resolve_escape_raises` was stripped by the wrapping — `Path(resolving_path)` returns a bare `WindowsPath` / `PosixPath`, NOT the subclass. The dual-anchor resolve-divergence test silently passed on a trivial call; the actual override-validation code path was never exercised.

**Rule:** Any helper signature `def h(path: Path, ...)` that accepts a Path-typed argument must use the caller-supplied value DIRECTLY — never wrap in `Path(...)` to normalize. If the helper needs to call `.resolve()` or `.is_absolute()`, those dispatches go through the subclass's overrides naturally. `Path()` construction is only appropriate in test-fixture setup (constructing fresh paths), not in pass-through sites.

**Self-check at Step 9:** grep the diff for `Path\(<kwarg>\)` / `Path\(<arg>\)` patterns at helper call-sites; each is a candidate for subclass-dispatch stripping. Confirmed OK when the arg was originally a string; flag when the arg was already typed as `Path`. Cycle-29 caught this at the pytest red→green transition because the symlink-escape test stayed RED after the first fix pass.

Generalises cycle-23 L2 (monkeypatch stub return type) — both are "caller contract preservation" rules; the return-type rule governs stubs, the Path-wrap rule governs pass-through helpers.

### L3 — CONDITION grep specs for shared-helper test patterns need HELPER-NAME targeting (cycle-29, refines cycle-26 L3)

**Problem:** Cycle 29 Q9/C4 specified `rg 'kb.compile.compiler.PROJECT_ROOT' tests/test_cycle29_rebuild_indexes_hardening.py` expecting ≥5 hits (one per AC2 test). The implementation factored the dual-module PROJECT_ROOT patching into a shared `_patch_project_root(monkeypatch, tmp_path)` helper at line 55, called from 14 test functions. Literal grep returns 1 hit (the docstring cross-ref); the 14 monkeypatch applications happen INSIDE the helper body. R2 Codex correctly flagged as "condition-wording gap, not a functional bug."

**Rule:** When a CONDITION targets TEST-file patching discipline, the grep spec must probe:
1. The **helper function name** (`_patch_project_root`, `_seed_wiki_and_data`) — counts helper call sites.
2. OR an AST-walk counting `ast.Call(func=Name(id='monkeypatch.setattr'))` or similar with the target module as first arg.

Literal-string grep of the module path `kb.compile.compiler.PROJECT_ROOT` is too coarse — it misses shared-helper factoring that's the project's idiomatic test-file shape.

**Concrete patterns for cycle-30+:**
```bash
# Helper-function call-count:
rg "^\s*_patch_project_root\(" tests/test_cycle29_*.py | wc -l  # expect ≥5

# OR AST-walk script:
python -c "
import ast
tree = ast.parse(open('tests/test_cycle29_*.py').read())
helper_calls = [
    n for n in ast.walk(tree)
    if isinstance(n, ast.Call)
    and getattr(n.func, 'id', '') == '_patch_project_root'
]
print(len(helper_calls))
"
```

Generalises cycle-26 L3 (CONDITION grep specs target CALL-SHAPE) to include the shared-helper-name case. Text-shape greps are for audit / refactor traces, NEVER for CI-gate CONDITION enforcement.

**Self-check at Step 5:** for any CONDITION that counts test-file patching operations, verify the Step-5 Analysis block names (a) the expected helper function OR (b) the AST-walk pattern, and does not rely on a literal-string count. If the cycle-5 design allowed helper extraction (the default project idiom), the spec MUST target the helper.

## Cycle termination

**Status:** Cycle 29 complete.
- PR #43 merged to main as commit `e52360d`.
- Feature branch `feat/backlog-by-file-cycle29` deleted.
- 7 commits landed (6 branch + 1 merge).
- 17 new tests (2809 → 2826 full suite).
- 0 late-arrival CVE advisories during cycle span.
- All R1 Sonnet S1/S2 + R1 Codex M1/M2/M3 findings IMPLEMENTED or documented.
- 3 new L1-L3 skill-patch lessons codified.

**Next:** Run `/clear` before the next cycle so the design-eval runs against fresh context. To start cycle 30 later, re-invoke `/feature-dev <args>` in a fresh session.
