# Cycle 42 self-review — Phase 4.6 small dedup batch

**Branch.** `cycle-42-phase46-dedup` (off main `9e07845`).
**Items.** 7 ACs (M1+M2+M3+L1+L2+L4+L5). 6 src files, 5 test/doc files. 3 implementation commits + 1 doc-update + 1 self-review = 5 total.
**Tests.** 3014 → 3014. 3003 passed + 11 skipped on Windows local. Pure behaviour-preserving dedup.

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — requirements | yes (primary, inline) | yes | — |
| 2 — threat model + dep-CVE baseline | SKIPPED | — | pure internal refactor, no I/O / trust-boundary changes (explicit skip-when condition met) |
| 3 — brainstorming | SKIPPED | — | mechanical dedup with crystal-clear BACKLOG text; no design space |
| 4 — design eval (2 rounds parallel) | SKIPPED | — | trivial mechanical ACs per cycle-13 L2 |
| 5 — design decision gate | inline (primary) | yes | one inline call: `_pagerank_cache_key` tuple-order normalisation safe because `_PAGERANK_CACHE` is process-local with no on-disk persistence |
| 6 — Context7 lib/API verification | SKIPPED | — | no third-party library APIs touched |
| 7 — implementation plan | inline (primary, C37-L5) | yes | — |
| 8 — plan gate | inline | yes | — |
| 9 — implementation (TDD) | yes (primary) | partial | **SURPRISE C42-L1**: `s.replace('_sanitize_error_str, ', '')` + `s.replace(', _sanitize_error_str', '')` regex sweep stripped commas from `error_tag("category", _sanitize_error_str(e))` calls, leaving `error_tag("category"(e))` syntax errors at three sites in `mcp/core.py`. Caught at the smoke-import step (Python emitted SyntaxWarnings before the actual NameError). **SURPRISE C42-L2**: parallel cycle-43 working-tree shared the same checkout; user `git stash` + branch-switch interleaved my work multiple times. Required cherry-pick + rebase to keep cycle-42 history clean. Surfaced AC4 monkeypatch-target gotcha as **C42-L3**: tests patched `engine.call_llm`, but moving `_suggest_rephrasings` to `rewriter.py` made the function body resolve `call_llm` against `rewriter`'s globals, not engine's; needed `monkeypatch.setattr(rewriter, "call_llm", ...)` for helper-direct tests but `engine.call_llm` patch retained for orchestrate-tier synthesis path test |
| 9.5 — simplify pass | SKIPPED | — | signature-preserving refactor; total `src/` diff <100 LoC code (skip-when row matched) |
| 10 — CI hard gate | yes | yes | full suite green; ruff check + format --check both clean |
| 11 — security verify + PR-CVE diff | SKIPPED | — | Step 2 was skipped; nothing to verify against |
| 11.5 — existing-CVE patch | yes | yes | no new advisories above cycle-41 baseline (litellm/diskcache/ragas/pip carry-overs unchanged) |
| 12 — doc update | yes | yes | CHANGELOG + CHANGELOG-history + BACKLOG cleanup + CLAUDE.md state-line |
| 13 — branch finalise + PR | yes | yes | — |
| 14 — PR review (2 rounds) | yes | yes | DeepSeek R1 + Codex R2 dispatched on dedup diff; ≤7 src files, ≤200-line diff — primary-session R3 skipped per C19-L4 thresholds (no new filesystem write surface; no new security enforcement point; <10 design-gate questions) |
| 15 — merge + cleanup | yes | yes | — |
| 16 — self-review + skill patch | yes (this doc) | yes | — |

## Skill patches derived

### C42-L1 — bulk regex `s.replace(', X', '')` strips commas from in-call positional args

When migrating an N-arg helper out of a module via `Python s.replace`, the patterns `s.replace('X, ', '')` and `s.replace(', X', '')` are NOT safe across the codebase: they match comma+symbol both in `from X import A, _sanitize_error_str, B` (intended target — strip from import list) AND in `error_tag("category", _sanitize_error_str(e))` (unintended — strips the comma between the two args, leaving the syntactically-broken `error_tag("category"(e))`). Python emits a SyntaxWarning ("'str' object is not callable; perhaps you missed a comma?") on import — visible only because I smoke-imported. Without that probe the corruption would have surfaced as a NameError at first MCP-tool call.

**Why.** `s.replace` has no notion of identifier boundaries, parenthesis depth, or comma role; the comma-symbol-space substring genuinely appears in both contexts.

**How to apply.** When sweeping a name from imports across a tree of files:
1. Use a Python AST walk (`ast.parse` + `ImportFrom` node filter) for import-list edits, not regex substring replacement.
2. If you must regex, anchor on the FULL import-statement context (`from X import` prefix) so call-site occurrences cannot match.
3. Run `python -c "import <module>"` on every modified file as a smoke step BEFORE `pytest`. SyntaxWarning + NameError surface here in <100ms; pytest takes 2+ minutes to surface the same break.
4. Grep AFTER the sweep for the no-op-corrupted shape: `grep -nE '"\w+"\([a-zA-Z_]'` matches `error_tag("category"(e))` and similar lost-comma artifacts.

Cross-references: refines feedback `feedback_ruff_unused_import_monkeypatch` (ruff autofix on monkeypatched imports) — same class of "automated code mutation has no semantic awareness" gotcha.

### C42-L2 — parallel cycles in the SAME working tree need explicit branch discipline at every Edit

When the user runs cycle N+1 in parallel in the same checkout, every `git stash` + `git checkout` + `git stash pop` cycle they perform may leave the assistant's in-flight Edit on the wrong branch. The assistant cannot detect this from in-context clues — file states reset silently. Symptoms:

- A `<system-reminder>` "file was modified, either by the user or by a linter" appears showing PRE-EDIT content of files I had just edited; this means a checkout reverted my work.
- `git status` shows the working tree clean despite recent `Edit` calls; the changes are sitting on a different branch (or got stashed).
- A commit lands on the wrong branch (`[cycle-43-test-folds 7715161]` when expected was `cycle-42-phase46-dedup`).

**How to apply.** When operating in a working tree shared with a parallel cycle:
1. Run `git branch --show-current` BEFORE every commit, not just at session start.
2. After observing the file-modified system-reminder showing PRE-EDIT content, treat it as a checkout-revert signal: re-check `git status` + `git branch --show-current` and either stash forward or cherry-pick back as needed.
3. When committing on an unexpected branch, cherry-pick to the correct branch + reset the wrong branch BEFORE moving on; don't try to "fix later" — the parallel cycle's user will quickly land their own commits and create a 3-way merge mess.
4. Prefer `git worktree` over branch-switching for parallel cycles in the future (one disk path per branch, no checkout drama). Document this preference for cycle 43+ in the next dev_ds skill patch.

Cross-references: refines cycle-22 L2 (block-no-verify hook intercepting Codex companion). Same class of "external state mutation invisible from prompt context".

### C42-L3 — moving a function across modules invalidates monkeypatches that target the OLD module

When `_suggest_rephrasings` moved from `kb.query.engine` to `kb.query.rewriter`, the tests that did `monkeypatch.setattr(engine, "call_llm", ...)` started running the REAL Anthropic SDK — because the function body now resolves `call_llm` against `kb.query.rewriter`'s globals (the new module), not `engine`'s. Re-exporting `_suggest_rephrasings` from engine.py is NOT enough: re-export only matters for the import-time binding, not for runtime global lookups inside the function body.

**How to apply.** When moving a function `F` from module `A` to module `B`:
1. Grep `monkeypatch\.setattr.*<name>` and `patch\("A\..*"\)` for every name `F` reads from `A`'s globals (`call_llm`, helpers, constants).
2. For each call site that references a global, the test patch MUST target `B` instead of `A` — `monkeypatch.setattr(B, "call_llm", ...)`. Re-exports don't help with this.
3. KEEP test patches on `A` for any caller that LIVES in `A` and calls `F` indirectly (e.g. `engine.query_wiki` calls `engine.call_llm` for synthesis — that path stays `monkeypatch.setattr(engine, "call_llm", ...)`).
4. The triage rule: did the function body MOVE? Then `B`-patch. Did only the wiring at the caller MOVE? Then `A`-patch.

Cross-references: refines cycle-18 L1 + cycle-19 L2 (snapshot-binding hazard). Same class of "global lookup binds at call time against the module the function lives in." Together these form the "where does the global resolve" rule: function bodies look up globals against THEIR OWN module's namespace, not against the import-time caller's namespace.

## What the cycle did NOT do

- Did NOT touch the four big package-split MEDIUM items (`lint/checks.py` 1046 LOC, `lint/augment.py` 1186 LOC, `mcp/core.py` 1149 LOC, `capture.py` + `utils/io.py` `atomic_text_write` consolidation). Those are dedicated cycles per cycle-37 L5 (≤15 ACs / ≤5 src files default) — a 4-file → package split exceeds the primary-session budget and warrants its own design eval pass.
- Did NOT advance the windows-latest CI matrix per cycle-36 L1 (one CI dimension per cycle; no CI-strictness flip stacked with new dedup work).
- Did NOT bump pip / litellm / ragas / diskcache pins — Step 11.5 baseline showed all four advisory IDs unchanged from cycle-41; per cycle-22 L4 conservative posture do NOT bump speculatively.

## Final state

Cycle 42 complete. Run `/clear` before the next cycle so the next design-eval runs against fresh context.
