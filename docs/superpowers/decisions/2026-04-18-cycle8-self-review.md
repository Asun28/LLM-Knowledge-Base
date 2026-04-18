# Cycle 8 — Step 16 Self-Review + Skill Patch Notes

**Date:** 2026-04-18
**Merged:** PR #22 → main at `baf6018`
**Delta:** 30 AC shipped across 19 files, 1919 → 1954 tests (+35), 3 fix commits (lazy exports / PageRank tie-order / augment stability), 2 review-fix commits (R1 majors + R2 scope-expansion), 1 doc commit.

## Step-by-step scorecard

| # | Step | Executed? | First-try? | Surprises |
|---|------|-----------|------------|-----------|
| 1 | Requirements + AC | yes | no | 8+ BACKLOG items already shipped in cycle 7 — confirmed via grep-verify before scope lock. Existing Red Flag ("BACKLOG says open → verify current source") fired as designed. |
| 2 | Threat model + CVE baseline | yes | yes | Dep-CVE baseline: requirements.txt resolver conflict; fell back to `pip-audit --installed`. Found 5 CVEs in 2 packages (diskcache + pip) — both Class A. |
| 3 | Brainstorming (4 Q × 2-3 options) | yes | yes | Skipped dialog-based user-approval gate per `feedback_auto_approve` memory; produced inline options + recommendations. |
| 4 | Design eval (Opus R1 + Codex R2 parallel) | yes | **no** | Codex R2 caught AC8 TARGET FILE WRONG: `kb_stats` is in `mcp/browse.py:317`, not `mcp/health.py`. Opus R1 missed it (generic "health tools" framing). Also: 5 new conditions + 1 new AC (AC6a for from_post sanitization). |
| 5 | Decision gate (Opus with Analysis scaffold) | yes | yes | Resolved all 11 Q_G1-Q_G11 (high-conf except Q_G7 snapshot = medium). Updated AC8 target + added V25-V27 Step-11 grep checkpoints. |
| 6 | Context7 | **skipped** | N/A | Pure Python stdlib/internal work — skip is per skill-permitted. |
| 7 | Plan (Codex) | yes | yes | 18 TASK sections with per-symbol grep evidence. Full plan saved to disk BEFORE gate per cycle-6 lesson ("plan gate on summary hallucinates gaps"). |
| 8 | Plan gate (Codex) | yes | yes | APPROVE with full coverage table AC1-AC30 + AC6a + T1-T10 → TASK refs. |
| 9 | Implementation | yes | **no** | 11 TASK commits + 3 regression fixes during Wave 1: (a) eager re-exports broke `kb --version` short-circuit → switched to PEP 562 lazy `__getattr__`; (b) PageRank tie-order non-determinism; (c) augment vector rebuild test stability. |
| 10 | CI hard gate | yes | yes | 1949 pass, ruff clean. |
| 11 | Security verify + CVE diff | yes | yes | All V01-V27 IMPLEMENTED; 0 PR-introduced CVEs. |
| 11.5 | Existing CVE patch | yes | yes | pip 24.3.1 → 26.0.1 (venv-level, not a requirements.txt dep). diskcache 5.6.3 (CVE-2025-69872) has no upstream patch → BACKLOG entry. |
| 12 | Doc update | yes | yes | CHANGELOG + BACKLOG + CLAUDE in one commit. Codex also committed the cycle 8 decision docs (requirements/threat-model/design/plan). |
| 13 | Branch finalize + PR | yes | yes | PR #22 open with review trail. |
| 14 | PR review (R1 parallel + R2 + R3) | yes | **no** | R1 Sonnet 2 majors (concurrent test gap, strip-then-check branch). R2 Codex 1 scope-expansion (`kb_save_lint_verdict` not using `_validate_notes`). R3 Codex APPROVE WITH FOLLOWUP. |
| 15 | Merge + cleanup + late-arrival CVE | yes | yes | PR #22 merged at `baf6018`. 0 new Dependabot alerts post-merge. Branch cleanup via `--delete-branch` auto-trigger. |

## Top lessons (4)

### L1: AC file-location drift — grep-verify in Step 5, not Step 11
**Context:** AC8 said `src/kb/mcp/health.py::kb_stats`, but `kb_stats` actually lives at `src/kb/mcp/browse.py:317`. Codex R2 (Step 4 design eval) caught it; Opus R1 did not.

**Root cause:** The threat model referenced `mcp/health.py:58` as a pattern-mirror example (for `kb_lint`'s wiki_dir handling), and I assumed any "health-class tool" (kb_stats, kb_verdict_trends) was in the same file. Neither the requirements nor design doc ran a confirmatory grep.

**Fix:** Step 5 decision gate Analysis MUST include explicit `grep -n "def <fn>" src/kb/` output for every AC that names a function. Add as a Red Flag.

### L2: PEP 562 lazy exports when __version__ short-circuits config
**Context:** TASK 3 initially committed eager `from kb.ingest import ingest_source` etc. to `src/kb/__init__.py`. This imported `kb.config` on every `import kb`, breaking cycle 7's `kb --version` AC30 (which deliberately bypasses `kb.config`). Codex auto-fixed with PEP 562 `__getattr__`.

**Root cause:** Top-level re-exports look simple, but they defeat any entry-point that was engineered to skip expensive imports.

**Fix:** When a package has a known fast-path that bypasses heavy imports, top-level `__init__.py` re-exports MUST use lazy `__getattr__` from commit #1. Add as a Red Flag.

### L3: Scope-expansion class-closure at R2 (cycle 7 pattern confirmed)
**Context:** `_validate_notes` was adopted in `kb_refine_page` + `kb_query_feedback` (AC16), but NOT in `kb_save_lint_verdict` (also has `notes` param). R2 Codex caught it. R3 also flagged adjacent `len(X) > MAX_Y` patterns in other fields (content, question) for follow-up.

**Root cause:** The AC narrowly scoped the "notes validation" class to 2 call sites; missing the 3rd same-class call site.

**Fix:** Existing cycle-7 Red Flag covers this ("For security-class AC, R3 typically surfaces same-class leaks in ADJACENT scoped-out modules"). Cycle 8 confirms the same lesson for validator-helper class AC. Add `_validate_notes` as a second example to the existing Red Flag — no new Red Flag needed.

### L4: Bash tmp paths and Python open() on Windows MSYS
**Context:** CVE diff script failed because `/tmp/cycle-8-*.json` resolves fine in bash but Python's `open('/tmp/...')` on Windows MSYS does NOT auto-translate to `C:\Users\Admin\AppData\Local\Temp\`. Wasted 3 bash retries.

**Root cause:** MSYS-on-Windows path translation is shell-side only. Python is a Windows binary and uses raw Windows paths.

**Fix:** Not a feature-dev skill concern — environment-specific. Document in CLAUDE.md if it becomes recurrent across cycles. Skipped for this cycle's skill patch.

## Skill patches to land

2 new Red Flag rows (see below) appended to `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md`:

**Red Flag A (new):** "AC references function X in module Y" — always grep before trusting.
**Red Flag B (new):** "Eager top-level re-exports break --version short-circuit"

Plus amend the existing scope-expansion Red Flag (cycle 7's AC12/13 row) with `_validate_notes` as a second example.

## Follow-up BACKLOG items (from R3)

One informational follow-up (not this cycle):
- `src/kb/mcp/quality.py:85, 193, 426` — inline `len(updated_content)`, `len(question)`, `len(content)` size checks not yet migrated to a `_validate_*` helper family. Low severity; cycle 9 can consider `_validate_content(size, field)` + `_validate_question(q)` helpers to close the remaining inline-validator pattern.
