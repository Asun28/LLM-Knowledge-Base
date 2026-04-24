# Cycle 29 — R2 Codex PR-fix verification

**Reviewer:** Codex (R2 round)
**Date:** 2026-04-24
**Branch head:** `6fc39e0` (pre this R2-note commit)
**Scope:** Verify R1 Sonnet S1 + R1 Codex M1/M2/M3 + R1 Sonnet S2 fixes land cleanly on PR #43

## Per-finding verdict

| R1 finding | Verdict | Evidence |
|---|---|---|
| S1 (Windows `Path(".")` regression) | IMPLEMENTED | `_validate_path_under_project_root` at `compiler.py:606-630`: empty-path guard removed, 16-line comment documents `Path("") == Path(".")` cross-platform equivalence. `TestOverrideCwdSemantics` class at line 403 replaces `TestOverrideEmptyInput` with 2 tests (CWD-outside-project rejects; CWD-inside-project accepts). |
| M1 (none-override spy strengthening) | IMPLEMENTED | `test_none_override_uses_default_without_validation_drift` at line 361 wraps `compiler._validate_path_under_project_root` via monkeypatch spy, collects `call_log`, asserts `fields_validated == ["wiki_dir"]` at line 397. Guard removal now divergent-fails via call-count assertion. |
| M2 (symlink decorator skip) | IMPLEMENTED | `@pytest.mark.skipif(os.name == "nt", ...)` decorator at line 313. `_has_symlink_priv` helper deleted (0 grep hits). |
| M3 (CLAUDE.md API doc) | IMPLEMENTED | CLAUDE.md:146 now documents override dual-anchor validation via `_validate_path_under_project_root`, `ValidationError` contract, `None` default skip, + AC1 compound `_audit_token` rendering. |
| S2 (design Q15 count drift) | IMPLEMENTED (updated post-R2) | Design doc Q15 annotation bumped 2825 → 2826 in a follow-up commit; CHANGELOG/CHANGELOG-history/CLAUDE.md already on 2826. |

## CONDITION audit

| C# | Check | Result |
|---|---|---|
| C1 | `_audit_token` helper with verbatim docstring | PASS |
| C2 | `_validate_path_under_project_root` helper + 3 callsites | PASS |
| C3 | CLI mirror imports `_audit_token` | PASS |
| C4 | `rg 'kb.compile.compiler.PROJECT_ROOT' tests/...` ≥5 hits | **PARTIAL** — 1 hit (docstring). Functional equivalent shipped via `_patch_project_root(monkeypatch, tmp_path)` helper at line 55 called from 14 test functions. Cycle-26 L3 class (CONDITION grep spec over-constrained vs actual coverage). No code change required; documented in CHANGELOG-history as a cosmetic condition-wording gap. |
| C5 | `from kb.errors import ValidationError` absent from test file | PASS (0 hits) |
| C6a | `_ResolvingPath` subclass defined | PASS (1 hit) |
| C6b | `os.symlink` real test body | PASS (2 hits) |
| C13 | Full-suite count 2826 | PASS (matches CLAUDE.md/CHANGELOG authoritative) |

## Count drift audit

- `git log --oneline origin/main..HEAD | wc -l` = **5 commits** (pre R2-note commit). CHANGELOG claims 5 commits — matches. After this R2-note commit lands, the count becomes 6 and CHANGELOG needs +1.
- `pytest --collect-only -q | tail -1` = **2826**. CHANGELOG "2809 → 2826 (+17)" matches. CLAUDE.md:33 + CLAUDE.md:195 both show 2826.
- `rg 'Path\(""\)' tests/test_cycle23_rebuild_indexes.py tests/test_cycle25_rebuild_indexes_tmp.py` = 0 hits (no pre-existing contract on Path("")).

## Regression sweep

- Cycle-23 + cycle-25 `rebuild_indexes` tests: 14 passed, 0 failures. Empty-path removal didn't break any prior contract (no pre-existing test used `Path("")`).

## Verdict

**APPROVE** — all 4 R1 code-fix findings (S1/M1/M2/M3) are IMPLEMENTED. S2 design-doc count drift resolved in a follow-up edit. One non-code CONDITION-wording PARTIAL (C4 grep spec over-constrained vs `_patch_project_root` helper coverage) flagged as cosmetic and documented in CHANGELOG-history per cycle-26 L3 precedent.

## R3 trigger evaluation (cycle-17 L4)

Cycle 29 metrics:
- AC count: 5 (below the 15-AC threshold)
- New security enforcement point: YES (AC2 `_validate_path_under_project_root` helper)
- Filesystem-write surface introduced: NO
- Step-5 gate questions resolved: 15 (above the 10-Q threshold)

Per cycle-17 L4: the 10-Q trigger fires ONLY when ≥15 ACs are in scope. With 5 ACs, R3 does NOT fire by the threshold rule. Cycle-16 L3 emphasises "risk profile trumps count" — here AC2 IS a new security surface, but R1+R2 collectively covered it (R1 Sonnet flagged the S1 regression; R1 Codex flagged M1/M2/M3; R2 Codex confirmed all fixes landed + caught S2 count drift + C4 grep-wording gap). No residual synthesis-level risks that R1+R2 missed.

**Decision: SKIP R3.** Manual-verify is authoritative per cycle-27 L3.

## Pre-merge checklist

- [x] All R1 findings IMPLEMENTED or documented.
- [x] Full suite 2816 passed + 10 skipped = 2826 collected.
- [x] Ruff check + format-check clean.
- [x] CLAUDE.md test-count narratives (both sites) updated to 2826.
- [x] CHANGELOG.md commit-count updated (will need +1 after this R2-note commit lands; the final merge tally will be 6).
- [x] No new PR-introduced CVEs (diff empty at Step 11).
- [x] BACKLOG hygiene preserved (3 stale entries deleted + 1 new Step-11 T1 PARTIAL entry added).

Hand off to Step 15 merge.
