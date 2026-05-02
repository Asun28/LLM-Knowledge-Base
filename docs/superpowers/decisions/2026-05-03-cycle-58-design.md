# Cycle 58 — Design Decision Gate

**Owner:** Opus 4.7 primary session (per C21-L1 — gaps resolvable without code exploration)
**Date:** 2026-05-03
**Bias:** lower blast radius wins; reversible > irreversible; opt-in > always-on.

## Verdict

**PROCEED with all 5 ACs as written in `2026-05-03-cycle-58-requirements.md`.** No DESIGN-AMEND. No ESCALATE.

## Decisions (per Step 3 open question)

### Q1 — `test_cycle18_wiki_log.py` receiver: `test_utils.py` vs `test_ingest.py`

**OPTIONS:**
- (a) Receiver = `test_utils.py` — already imports `from kb.utils.wiki_log import append_wiki_log`; tests in receiver test `append_wiki_log` (3 tests at line 78+).
- (b) Receiver = `test_ingest.py` — wiki_log is consumed by ingest pipeline; test_ingest already exercises pipeline-stage outputs.

**ARGUE:**
The semantic question is "what's the unit under test?" The 5 incoming `test_rotate_*` tests test `rotate_if_oversized` directly + `append_wiki_log` rotation behaviour — both module-internal `kb.utils.wiki_log` functions, not the pipeline that consumes them. (a) puts the rotation tests next to the existing rotation-aware `test_append_wiki_log_*` tests. (b) would split related coverage across two files.

**DECIDE:** (a) `test_utils.py`.
**RATIONALE:** Module-cohesion wins — co-locate tests for the same `kb.utils.wiki_log` module. Receiver host-shape (existing `# ── append_wiki_log ─` section) already accommodates rotation-related tests.
**CONFIDENCE:** HIGH.

### Q2 — `test_cycle18_sanitize.py` namespace strategy: class-wrap vs prefix-rename

**OPTIONS:**
- (a) Class-wrap into `TestSanitizePathRedaction` — 16 methods become test-class methods; namespace isolation via class scope.
- (b) Prefix-rename each bare function — 16 individual edits to `test_sanitize_redaction_*` or `test_sanitize_path_redaction_*`.
- (c) Move to a NEW file `test_utils_sanitize.py` — preserves bare-function shape but creates a 1-test-file overhead.

**ARGUE:**
(a) requires 1 class wrapper edit + section header; receiver host-shape changes from bare-function-only to bare-function-with-one-class. The cycle-50 precedent (`TestMcpWikiDirValidation` added to `test_mcp_core.py`) is exactly the same shape — a class added to a bare-function-heavy receiver to scope cross-feature concerns. (b) requires 16 individual edits and the prefix `test_path_redaction_*` is wordy. (c) creates a NEW file, which is the OPPOSITE of the freeze-and-fold goal (file count -5, not -4 with a +1).

**DECIDE:** (a) class-wrap into `TestSanitizePathRedaction`.
**RATIONALE:** Cycle-50 cross-feature-hosting analogue + minimal edit surface + namespace clarity at the cost of a single host-shape break in the receiver. C40-L5 host-shape preservation is a guideline not a hard rule; the cycle-50 precedent is binding.
**CONFIDENCE:** HIGH.

### Q3 — P5 helper rename `_make_items` → `_make_two_pass_items` (feature-prefix) vs `_make_cycle17_items` (cycle-prefix)

**OPTIONS:**
- (a) Feature-prefix: `_make_two_pass_items`
- (b) Cycle-prefix: `_make_cycle17_items`
- (c) Both, with feature-prefix first: `_make_two_pass_items`

**ARGUE:**
(a) is semantically descriptive — a future reader sees "two-pass items" and immediately understands the contract. (b) is provenance-anchoring — survives feature rename if "two-pass write" gets renamed in production. C52-L4 cycle-prefix is for HELPER UNIQUENESS not provenance — uniqueness wins via either form. The cycle-prefix in source-test names already preserves provenance ("folded from `test_cycle17_capture_two_pass.py`"); the helper itself doesn't need to repeat it.

**DECIDE:** (a) feature-prefix `_make_two_pass_items`.
**RATIONALE:** Semantic descriptiveness + sufficient uniqueness vs existing helper names in `tests/test_capture.py` (no `_make_two_pass*` exists).
**CONFIDENCE:** HIGH.

### Q4 — P5 220 LoC sizing: primary-session vs MiMo dispatch

**OPTIONS:**
- (a) Primary session per C13-L2 + C37-L5 — pure test-code fold, no novel API.
- (b) MiMo Coding dispatch per skill Step 9 default — preserves trial-data symmetry.

**ARGUE:**
C13-L2 says "≤30 lines code + ≤100 lines test". P5 is 0 lines code + 220 lines test. The heuristic was about NOVEL CODE, not test mass. C37-L5 explicitly relaxes to ≤15 ACs / ≤5 src files / primary-holds-context — this cycle has 5 ACs, 0 src files, primary-holds-context. The dispatch overhead (cycle-23+ data shows ~5-10 min round-trip vs ~3 min primary-session per fold) is not justified.

**DECIDE:** (a) primary session.
**RATIONALE:** C37-L5 generalises beyond C13-L2's narrow novel-code threshold; this cycle's profile (5 small mechanical folds, primary holds context, no novel API) is the textbook primary-session case. Trial-data is preserved at Step 8 (plan-gate MiMo Coding) and Step 14 (security-verify MiMo Coding).
**CONFIDENCE:** HIGH.

### Q5 — AC2 host-shape break: acceptable vs forced bare-function

**OPTIONS:**
- (a) Accept host-shape break — class added to bare-function receiver (cycle-50 precedent).
- (b) Force bare-function with prefix-rename — preserves host-shape (Q2 (b) revisited).

**ARGUE:**
Already resolved at Q2 (a) wins — class-wrap. The host-shape break is intentional and bounded (one class, clearly labeled section header). C40-L5 is a default; C50 cross-feature-hosting precedent overrides for namespace-isolation needs.

**DECIDE:** (a) accept.
**RATIONALE:** Same as Q2.
**CONFIDENCE:** HIGH.

## CONDITIONS (Step 9 must satisfy — per C32-L1)

Each per-AC fold MUST satisfy the following before commit:

1. **Source file deleted** in the same commit as the receiver edit (one commit per fold).
2. **Receiver isolated pytest passes** — `pytest tests/test_<receiver>.py -q` zero-failure.
3. **Revert-verify per C40-L3** — sub-step: temporarily flip `assert <X>` → `assert False` on ONE moved test method; confirm `pytest -x tests/test_<receiver>.py` FAILs on that method; revert the assert flip. Document SHA of the receiver-state snapshot before fold.
4. **Helper renames applied:**
   - AC4: `_write_page` → `_write_status_mature_page` (verified no collision with receiver's `_create_page`).
   - AC5: `_make_items` → `_make_two_pass_items` (verified no collision with receiver).
5. **Class wrap applied (AC2 only):** 16 source bare functions become methods of `TestSanitizePathRedaction`; method names re-derive from source function names by stripping `test_sanitize_` and `test_sanitize_error_` prefixes; e.g., `test_sanitize_text_windows_backslash` → `test_text_windows_backslash`. (Wait — clarification: source uses `test_sanitize_text_*` and `test_sanitize_error_text_*`; methods become `test_text_windows_backslash` / `test_error_text_delegates_to_sanitize_text` / etc. inside the class. ALTERNATIVE simplification: keep method names verbatim — `test_sanitize_text_windows_backslash` works as a method name and the class scope already disambiguates from receiver's bare `test_sanitize_strips_*` functions.) **Decision: keep method names verbatim** to minimize rename surface; class scope handles namespace.
6. **Section header at insertion point** — each fold appends with a `# ── <feature> (cycle 58 fold) ─` section header at end-of-receiver (or the relevant existing section if extending).
7. **Import merge** — extend existing import lines alphabetically; add new lines for new modules. Per C16-L1 + C19-L1, snapshot-bind imports (`from X import Y`) are kept at module top per receiver convention; do NOT introduce dynamic `import kb.X; kb.X.Y` patterns unless the receiver already uses them.
8. **No `inspect.getsource` / source-string-read assertions in moved tests** — all 5 sources use behavioral assertions per spot-check; per C11-L1 this is verified before commit (no upgrade candidates filed for cycle 58).
9. **Per-fold full-suite pytest passes** — beyond per-isolation, run `pytest -q` after each fold to catch full-suite ordering bugs (per C22-L3). Optional but required at the LAST fold before Step 12.
10. **Ruff format + check pass** — run `ruff format <receiver>` THEN `ruff check <receiver>` per `feedback_ruff_edit_ordering`.
11. **Step 9 commit message format:** `test(cycle 58): fold test_<source-stem> into <receiver-stem> (N/5)`.
12. **Step 21 rebase awareness** — if cycle 53 (4 folds) merges first, cycle 58's branch HEAD file count delta becomes -5 vs the rebased main; document this conditional in CHANGELOG.

## Trial-data capture map

| Step | Subagent | Model | Rationale |
|------|----------|-------|-----------|
| 8 | `mimocoding-rescue` | `mimo-v2.5-pro` (2x credit) | Plan gate is reasoning-heavy; Pro tier matches skill default |
| 9 | primary session | Opus 4.7 (1M context) | Per C37-L5; 5 small mechanical folds |
| 14 | `mimocoding-rescue` | `mimo-v2.5-pro` | Security verify needs thinking |
| 17 | `deepseek-rescue` | `deepseek-v4-pro` | Per skill rationale (preserves Token-Plan budget) |
| 18 | `mimocoding-rescue` | `mimo-v2.5` (1x credit) | PR finalize doesn't need Pro tier |
| 20 R1 | `deepseek-rescue` (architecture) + `everything-claude-code:code-reviewer` (Sonnet edge-cases) | `deepseek-v4-pro` + Sonnet 4.6 | Cross-vendor R1 |
| 20 R2 | `codex:codex-rescue` (architecture verify) + `everything-claude-code:code-reviewer` (Sonnet regression-risk) | Codex + Sonnet 4.6 | Cross-vendor R2 |

## R3 trigger evaluation (per C16-L4 + C17-L4)

R3 fires at ≥25 ACs OR ≥15 ACs WITH risk-surface trigger. This cycle has 5 ACs + 0 risk-surface triggers (no new filesystem write, no new security enforcement, no >=10 design questions resolved). **R3 SKIP.**

## Final picks confirmation (Step 1 → Step 5)

| AC | Source | Receiver | Test count |
|----|--------|----------|-----------:|
| AC1 | `test_cycle17_mcp_tool_coverage.py` (110 LoC) | `test_mcp_core.py` (cross-module hosting per cycle-50 precedent) | 13 |
| AC2 | `test_cycle18_sanitize.py` (116 LoC) | `test_utils_text.py` (class-wrap into `TestSanitizePathRedaction`) | 16 |
| AC3 | `test_cycle18_wiki_log.py` (126 LoC) | `test_utils.py` (existing wiki_log section) | 5 |
| AC4 | `test_cycle15_lint_status_mature.py` (112 LoC) | `test_lint.py` (helper rename `_write_page` → `_write_status_mature_page`) | 8 |
| AC5 | `test_cycle17_capture_two_pass.py` (220 LoC) | `test_capture.py` (helper rename `_make_items` → `_make_two_pass_items`) | 10 |
| AC6 | (standing) | (no fold) | 0 |

**Total fold deltas:** 5 sources DELETED, 5 receivers EXTENDED, file count 208 → 203 at branch HEAD, test count 3021 → 3021 (preserved).
