# Cycle 55 — Implementation Plan

**Date:** 2026-05-02
**Branch:** `cycle-55-batch`
**Pipeline:** `dev-mimo-opus` (project trial)
**Picks:** test_v01003_graph_fixes, test_v01007_evolve_fixes, test_v01009_ingest_aux_fixes, test_v01011_review_feedback_fixes
**Design doc:** `docs/superpowers/decisions/2026-05-02-cycle-55-batch-design.md`

## Tasks

### Step 02 — Dep-CVE baseline capture
```
mkdir -p .data/cycle-55
gh api "repos/Asun28/llm-wiki-flywheel/dependabot/alerts" --paginate --jq '[...]' > .data/cycle-55/alerts-baseline.json
pip-audit --format json > .data/cycle-55/cve-baseline.json 2>/dev/null || true
```
Save summary to `.data/cycle-55/baseline-summary.txt` for Step 14 + 15 cross-check.

### Step 09a — Fold test_v01003_graph_fixes into test_graph.py

**Files:**
- `tests/test_graph.py` (receiver, +50 LoC under new EOF section)
- `tests/test_v01003_graph_fixes.py` (delete)

**Changes:**
1. Append new section to `test_graph.py`:
   ```python
   # ── Phase 4 graph fixes (cycle 55 fold) ───────────────────────────────
   ```
2. Move 3 tests, with Q1 upgrade applied to test 1:
   - `test_graph_stats_avoids_per_node_degree_calls` — REPLACES the original `test_graph_stats_uses_precomputed_out_degrees`. Behavioral: monkey-patch `nx.DiGraph.degree` to a spy that increments a counter on every call; build a real graph; call `graph_stats(g)`; assert `spy.call_count == 0` (out_degrees dict precomputed). Function-local imports only.
   - `test_graph_stats_orphan_detection_with_isolated_node` — NEW test extracted from the orphan-count half of the original. Uses `nx.DiGraph` builder + asserts `stats["orphans"] == ["d"]`.
   - `test_export_mermaid_deterministic_edge_order` — verbatim, function-local imports preserved.
   - `test_graph_init_does_not_export_scan_wiki_pages` — verbatim.
3. Delete `tests/test_v01003_graph_fixes.py`.

**Test:**
```bash
pytest tests/test_graph.py::test_graph_stats_avoids_per_node_degree_calls -v
pytest tests/test_graph.py::test_graph_stats_orphan_detection_with_isolated_node -v
pytest tests/test_graph.py::test_export_mermaid_deterministic_edge_order -v
pytest tests/test_graph.py::test_graph_init_does_not_export_scan_wiki_pages -v
# Revert-verify (assert False) per C40-L3 on each
pytest tests/test_graph.py -q   # full file isolation per C51-L1
```

**Criteria:** AC1, AC5, AC6
**Threat:** N/A
**Commit:** `test(cycle 55): fold test_v01003_graph_fixes into test_graph.py (1/4)` with revert-verify line in body

### Step 09b — Fold test_v01007_evolve_fixes into test_evolve.py

**Files:**
- `tests/test_evolve.py` (receiver, +75 LoC under new EOF section)
- `tests/test_v01007_evolve_fixes.py` (delete)

**Changes:**
1. Append new section after the existing cycle-48 fold section:
   ```python
   # ── Phase 4 evolve fixes (cycle 55 fold) ──────────────────────────────
   ```
2. Move 3 tests verbatim — multi-attr `for attr in (...)` monkeypatch fallback pattern preserved. Function-local imports.
3. Delete `tests/test_v01007_evolve_fixes.py`.

**Test:**
```bash
pytest tests/test_evolve.py::test_find_connection_opportunities_caps_pairs -v
pytest tests/test_evolve.py::test_generate_evolution_report_scans_once -v
pytest tests/test_evolve.py::test_generate_evolution_report_handles_oserror -v
# Revert-verify per C40-L3 on each
pytest tests/test_evolve.py -q   # isolation per C51-L1
```

**Criteria:** AC2, AC5, AC6
**Threat:** N/A
**Commit:** `test(cycle 55): fold test_v01007_evolve_fixes into test_evolve.py (2/4)`

### Step 09c — Fold test_v01009_ingest_aux_fixes into test_ingest.py

**Files:**
- `tests/test_ingest.py` (receiver, +55 LoC under new EOF section)
- `tests/test_v01009_ingest_aux_fixes.py` (delete)

**Changes:**
1. Append at EOF:
   ```python
   # ── Phase 4 ingest aux fixes (cycle 55 fold) ──────────────────────────
   ```
2. Move 3 tests verbatim. **Function-name pre-check:** `test_load_template` already exists at `test_ingest.py:24`. Source file's `test_load_template_returns_deep_copy` is distinct — keep its name as-is (no rename). Other 2 names (`test_evidence_trail_crlf_header`, `test_contradiction_truncation_logged`) — grep test_ingest.py to confirm no collision.
3. Delete `tests/test_v01009_ingest_aux_fixes.py`.

**Test:**
```bash
pytest tests/test_ingest.py::test_load_template_returns_deep_copy -v
pytest tests/test_ingest.py::test_evidence_trail_crlf_header -v
pytest tests/test_ingest.py::test_contradiction_truncation_logged -v
# Revert-verify per C40-L3 on each
pytest tests/test_ingest.py -q   # isolation per C51-L1
```

**Criteria:** AC3, AC5, AC6
**Threat:** N/A
**Commit:** `test(cycle 55): fold test_v01009_ingest_aux_fixes into test_ingest.py (3/4)`

### Step 09d — Fold test_v01011_review_feedback_fixes into test_review.py

**Files:**
- `tests/test_review.py` (receiver, +60 LoC under new EOF section)
- `tests/test_v01011_review_feedback_fixes.py` (delete)

**Changes:**
1. Append at EOF:
   ```python
   # ── Phase 4 review/feedback/config fixes (cycle 55 fold) ──────────────
   ```
2. Move 3 tests verbatim per Q2 host-shape preservation:
   - `test_refine_page_rejects_multiline_frontmatter_body`
   - `test_refine_page_updated_regex_anchored`
   - `test_embedding_dim_resolved` (config + embeddings — joins under host-shape preservation despite touching different territory)
3. Function-name pre-check: grep test_review.py — none of the 3 names collide.
4. Delete `tests/test_v01011_review_feedback_fixes.py`.

**Test:**
```bash
pytest tests/test_review.py::test_refine_page_rejects_multiline_frontmatter_body -v
pytest tests/test_review.py::test_refine_page_updated_regex_anchored -v
pytest tests/test_review.py::test_embedding_dim_resolved -v
# Revert-verify per C40-L3 on each
pytest tests/test_review.py -q   # isolation per C51-L1
```

**Criteria:** AC4, AC5, AC6
**Threat:** N/A
**Commit:** `test(cycle 55): fold test_v01011_review_feedback_fixes into test_review.py (4/4)`

### Step 12 — CI gate

```bash
python -m pytest -q                               # full suite, expect 3014 passed + 11 skipped
python -m pytest --collect-only -q | tail -1      # confirms 3025 tests collected
ruff check src/ tests/
ruff format --check src/ tests/
pip-audit -r requirements.txt --format json > .data/cycle-55/cve-branch.json 2>/dev/null || true
```

**Criteria:** AC7

### Step 14 — PR-introduced CVE diff

```bash
jq -r '.dependencies[].vulns[]?.id // empty' .data/cycle-55/cve-branch.json | sort -u > /tmp/cycle-55-b.txt
jq -r '.dependencies[].vulns[]?.id // empty' .data/cycle-55/cve-baseline.json | sort -u > /tmp/cycle-55-m.txt
INTRODUCED=$(comm -23 /tmp/cycle-55-b.txt /tmp/cycle-55-m.txt)
[ -z "$INTRODUCED" ] && echo "PASS — no PR-introduced advisories" || echo "REJECT: $INTRODUCED"
```

**Criteria:** AC9 (Class B subset)

### Step 15 — Existing-CVE opportunistic patch

For each baseline alert with `first_patched_version != null`:
1. Bump pin in requirements.txt
2. `pip install --upgrade <package>==<patched_version>`
3. Re-run pytest + ruff
4. Commit `fix(deps): patch <N> Dependabot advisories`

If all baseline alerts have `first_patched_version == null` → skip (file BACKLOG entry referencing GHSAs).

**Criteria:** AC9 (Class A subset)

### Step 17 — Doc update

Update in this order (per cycle 51/52 convention):
1. `BACKLOG.md` — append cycle 55 progress note to the freeze-and-fold HIGH parenthetical (line 91).
2. `CHANGELOG.md` — add `[Unreleased]` Quick Reference entry (Items / Tests / Scope / Detail).
3. `CHANGELOG-history.md` — add full per-cycle bullet detail.
4. `CLAUDE.md` — bump `225 files` → `221 files` (subject to Step 21 rebase if 53/54 land first).
5. `docs/reference/testing.md` — bump file count narrative.
6. `docs/reference/implementation-status.md` — bump latest-cycle notes if it tracks per-cycle file counts.
7. `README.md` — only if user-facing; folds typically don't touch README.

**Try MiMo Chat dispatch first:** `Agent(subagent_type="mimochat-rescue", model="mimo-v2-flash")`. On failure → primary.

**Criteria:** AC8

### Step 18 — Branch finalise + PR

```bash
git push -u origin cycle-55-batch
gh pr create --title "Cycle 55 — Backlog hygiene + freeze-and-fold continuation (4 folds, 225→221) + dep-CVE re-confirm" \
  --body "$(cat <<'EOF'
## Summary

- Phase 4.5 HIGH freeze-and-fold continuation: 4 folds (test_v01003_graph_fixes, test_v01007_evolve_fixes, test_v01009_ingest_aux_fixes, test_v01011_review_feedback_fixes) into canonical receivers
- AC1 includes a C11-L1 upgrade: vacuous getsource half of test_graph_stats_uses_precomputed_out_degrees replaced by behavioral spy on nx.DiGraph.degree
- dep-CVE re-confirm baseline → branch diff = empty (Class B)
- File count 225 → 221; test count preserved 3025

## First MiMo trial cycle (dev-mimo-opus skill)

This is the first real-cycle exercise of the May 2026 MiMo trial. Step 7 plan + Step 17 doc update attempted MiMo dispatch with primary-session fallback. Outcomes captured in Step 24 self-review for the 2026-05-31 writeup.

## Test plan

- pytest -q: 3014 passed + 11 skipped
- pytest --collect-only -q: 3025 tests
- ruff check: pass
- pip-audit: PR-introduced advisories empty

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Step 20 — PR review (R1 + R2)

R1 parallel:
- DeepSeek (`deepseek-rescue` @ `deepseek-v4-pro`) — architecture/contracts/correctness
- Sonnet (`everything-claude-code:code-reviewer`) — edge cases / Red Flags scan

R2 parallel (after R1 fixes land):
- Codex (`codex:codex-rescue`) — verify R1 fixes resolved without new regressions
- Sonnet — same goal, different lens

Document EVERY substitution in PR review-trail comment.

### Step 21 — Merge + cleanup

```bash
gh pr merge <PR> --merge
git fetch origin main && git checkout main && git pull --ff-only
git branch -d cycle-55-batch
gh api "repos/Asun28/llm-wiki-flywheel/dependabot/alerts" --paginate --jq '...' > .data/cycle-55/alerts-postmerge.json
# late-arrival CVE warn diff
```

**If cycle 53 or 54 merged before me:** rebase + bump CLAUDE.md / CHANGELOG / docs counts before merge per AC7 caveat.

### Step 24 — Self-review

Scorecard for steps 01-23. Skill patches under `## Cycle 55 skill patches (2026-05-02)` in `.claude/skills/dev-mimo-opus/references/cycle-lessons.md` (TBD — file may not yet exist; create if missing) AND a one-liner under SKILL.md "Accumulated rules index". Special: first MiMo trial data point (dispatch outcomes).

## Verification Plan

- `python -m pytest tests/test_graph.py tests/test_evolve.py tests/test_ingest.py tests/test_review.py -v`
- `python -m pytest --collect-only -q | tail -1` → `3025 tests collected`
- `python -m ruff check src/ tests/`
- `python -m ruff format --check src/ tests/`
- `python -m pytest -q`
- `find tests -maxdepth 1 -name 'test_*.py' | wc -l` → `221`

## Scope Controls

- Production source (`src/kb/`) untouched.
- CI/dependency files (`.github/`, `requirements.txt`, `pyproject.toml`) untouched UNLESS Step 15 dep-CVE patch fires.
- Receivers held by cycle 53 (test_compile.py / test_config.py / test_query.py) and cycle 54 (test_lint.py / test_mcp_browse_health.py / test_models.py / test_utils_io.py / test_compile.py) NOT touched.
- BACKLOG.md updates only the freeze-and-fold HIGH parenthetical (line 91) — no other entries touched.
