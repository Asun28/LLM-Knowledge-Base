# Phase 4 Status Doc Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct misleading "Phase 4 complete" doc claims to accurately state Phase 4 v0.10.0 shipped 8 features + HIGH-severity audit fixes, while 54 MEDIUM/LOW audit items remain open in BACKLOG.md.

**Architecture:** Pure documentation update. Four files need edits: `BACKLOG.md` (one-line clarification), `CLAUDE.md` (two status lines + known-issues pointer), `README.md` (roadmap line already out of date), `CHANGELOG.md` (optional scope note in `[Unreleased]`). No code changes, no tests. Verification is `git diff` readthrough + `grep` for residual "Phase 4 complete" strings.

**Tech Stack:** Markdown only.

**Context (what the reader needs to know):**
- `v0.10.0` (2026-04-12) shipped 8 Phase 4 features — fully released.
- A post-release audit on 2026-04-12 found 68 backlog items: 23 HIGH, 38 MEDIUM, 27 LOW (rough counts).
- The 23 HIGH items were fixed on the same day; fixes live in `CHANGELOG.md` `[Unreleased]` (not yet version-tagged).
- `BACKLOG.md` line 36 reads `- **HIGH** — all 23 items resolved in Phase 4 audit fixes (2026-04-12)` — true, but easy to misread as "all 23 Phase 4 items" when the total is 68.
- `CLAUDE.md:13` and `CLAUDE.md:255` both say "Phase 4 complete (v0.10.0)" — misleading because MEDIUM/LOW audit work is still open.
- `README.md:298` still lists Phase 4 as "next" — outdated.
- No version tag needs cutting here; we are only correcting narrative claims. A follow-up patch-version bump (e.g., `0.10.1`) when the HIGH fixes ship is the author's call, not part of this plan.

---

### Task 1: Clarify BACKLOG.md HIGH-severity resolution line

**Files:**
- Modify: `BACKLOG.md:36`

- [ ] **Step 1: Read current state**

Run: `grep -n "HIGH.*resolved" BACKLOG.md`
Expected output:
```
36:- **HIGH** — all 23 items resolved in Phase 4 audit fixes (2026-04-12)
```

- [ ] **Step 2: Edit line 36 to disambiguate "23 items" vs "all Phase 4"**

Replace in `BACKLOG.md`:
```
- **HIGH** — all 23 items resolved in Phase 4 audit fixes (2026-04-12)
```
With:
```
- **HIGH** — all 23 HIGH-severity audit items resolved 2026-04-12 (fixes in `CHANGELOG.md` `[Unreleased]`). MEDIUM and LOW items below remain open.
```

- [ ] **Step 3: Verify edit**

Run: `grep -n "HIGH-severity audit items resolved" BACKLOG.md`
Expected: exactly one match on line 36.

Run: `grep -n "^### MEDIUM$\|^### LOW$" BACKLOG.md`
Expected: two matches (MEDIUM and LOW section headers still present — we did not delete content, only clarified the HIGH summary).

- [ ] **Step 4: Commit**

```bash
git add BACKLOG.md
git commit -m "docs(backlog): clarify Phase 4 HIGH-severity fixes do not cover MEDIUM/LOW"
```

---

### Task 2: Update CLAUDE.md Implementation Status lead-in

**Files:**
- Modify: `CLAUDE.md:13`

- [ ] **Step 1: Read current state**

Run: `sed -n '11,14p' CLAUDE.md` (reference only — use `Read` tool in practice).
Expected line 13 starts with: `**Phase 4 complete (v0.10.0).** 1111 tests, 25 MCP tools, 18 modules.`

- [ ] **Step 2: Edit line 13 — change "Phase 4 complete" to a hedged phrasing**

In `CLAUDE.md`, find the line that begins:
```
**Phase 4 complete (v0.10.0).** 1111 tests, 25 MCP tools, 18 modules. Phase 1 core
```

Replace `**Phase 4 complete (v0.10.0).**` with:
```
**Phase 4 shipped (v0.10.0) + HIGH-severity audit fixes (unreleased).**
```

Leave the rest of the paragraph (test counts, module list, version history) unchanged.

- [ ] **Step 3: Verify**

Run: `grep -n "Phase 4 shipped (v0.10.0)" CLAUDE.md`
Expected: one match near the top (around line 13).

Run: `grep -cn "Phase 4 complete" CLAUDE.md`
Expected: `1` (the `Current:` line further down — will be edited in Task 3). If the count is 0, stop and investigate: you may have accidentally also edited line 255.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): hedge 'Phase 4 complete' to reflect unreleased audit fixes"
```

---

### Task 3: Update CLAUDE.md "Current" status line

**Files:**
- Modify: `CLAUDE.md:255`

- [ ] **Step 1: Read current state**

Use the `Read` tool on `CLAUDE.md` with `offset=253, limit=6`.
Expected line 255 begins: `**Current:** Phase 4 complete (v0.10.0) — 1111 tests, 25 MCP tools, 18 modules.`

- [ ] **Step 2: Edit line 255**

Replace the opening fragment:
```
**Current:** Phase 4 complete (v0.10.0) — 1111 tests, 25 MCP tools, 18 modules. Phase 4 adds hybrid search with RRF fusion, 4-layer search dedup, evidence trail sections, stale truth flagging at query time, layered context assembly, raw-source fallback, auto-contradiction detection on ingest, and multi-turn query rewriting. See CHANGELOG.md for full details.
```

With:
```
**Current:** Phase 4 v0.10.0 shipped + HIGH-severity audit fixes unreleased — 1111 tests, 25 MCP tools, 18 modules. v0.10.0 features: hybrid search with RRF fusion, 4-layer search dedup, evidence trail sections, stale truth flagging at query time, layered context assembly, raw-source fallback, auto-contradiction detection on ingest, multi-turn query rewriting. Post-release audit (2026-04-12) resolved 23 HIGH-severity items in `CHANGELOG.md` `[Unreleased]`; 54 MEDIUM/LOW items remain open in `BACKLOG.md`. See CHANGELOG.md for full details.
```

- [ ] **Step 3: Verify**

Run: `grep -n "54 MEDIUM/LOW items remain open" CLAUDE.md`
Expected: one match around line 255.

Run: `grep -cn "Phase 4 complete" CLAUDE.md`
Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): split 'Phase 4 complete' into shipped vs unreleased audit"
```

---

### Task 4: Update CLAUDE.md "Known issues" pointer

**Files:**
- Modify: `CLAUDE.md` — the `**Known issues:**` line (around line 257, immediately after the `Current:` line edited in Task 3)

- [ ] **Step 1: Read current state**

Use the `Read` tool on `CLAUDE.md` with `offset=255, limit=10`.
Expected to find a line beginning: `**Known issues:** See `BACKLOG.md` for active backlog items.` ending at `Resolved items are deleted (fix recorded in CHANGELOG.md); resolved phases collapse to a one-liner under "Resolved Phases".`

- [ ] **Step 2: Replace the "Known issues" sentence with an itemised summary**

Find the line:
```
**Known issues:** See `BACKLOG.md` for active backlog items. Format guide is in the HTML comment at the top of that file. Severity levels: CRITICAL (blocks release), HIGH (silent wrong results / security), MEDIUM (quality gaps / missing coverage), LOW (style/naming). Items grouped by severity then by module area. Resolved items are deleted (fix recorded in CHANGELOG.md); resolved phases collapse to a one-liner under "Resolved Phases".
```

Replace with:
```
**Known issues:** See `BACKLOG.md` for active backlog items (Phase 4 section has ~30 MEDIUM + ~27 LOW items open as of 2026-04-12; all HIGH-severity items resolved). Format guide is in the HTML comment at the top of that file. Severity levels: CRITICAL (blocks release), HIGH (silent wrong results / security), MEDIUM (quality gaps / missing coverage), LOW (style/naming). Items grouped by severity then by module area. Resolved items are deleted (fix recorded in CHANGELOG.md); resolved phases collapse to a one-liner under "Resolved Phases".
```

(The `~30 / ~27` counts are approximate because the exact tally depends on whether you count "existing items carried forward" sub-groups; do not pause to get a precise count — the point is to signal volume to readers.)

- [ ] **Step 3: Verify**

Run: `grep -n "MEDIUM + ~27 LOW items open" CLAUDE.md`
Expected: one match.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): surface outstanding MEDIUM/LOW counts in known-issues pointer"
```

---

### Task 5: Update README.md roadmap to mark Phase 4 shipped

**Files:**
- Modify: `README.md:298`

- [ ] **Step 1: Read current state**

Use the `Read` tool on `README.md` with `offset=294, limit=10`.
Expected line 298 begins: `- **Phase 4 (next):** Layered context assembly, raw-source fallback retrieval, multi-turn query rewriting, auto-contradiction detection on ingest, LLM keyword query expansion with strong-signal skip`

- [ ] **Step 2: Replace the "Phase 4 (next)" line with shipped status**

Replace:
```
- **Phase 4 (next):** Layered context assembly, raw-source fallback retrieval, multi-turn query rewriting, auto-contradiction detection on ingest, LLM keyword query expansion with strong-signal skip
```

With:
```
- **Phase 4 (v0.10.0 shipped 2026-04-12):** Hybrid search with RRF fusion, 4-layer search dedup pipeline, evidence trail sections, stale truth flagging at query time, layered context assembly, raw-source fallback retrieval, auto-contradiction detection on ingest, multi-turn query rewriting. Post-release audit fixed 23 HIGH-severity items (unreleased); MEDIUM/LOW items tracked in `BACKLOG.md`.
```

Note: the feature list has drifted from the original roadmap — it intentionally matches what actually shipped per `CHANGELOG.md:80-101` rather than what was planned. "LLM keyword query expansion" was subsumed by RRF and is correctly omitted.

- [ ] **Step 3: Verify**

Run: `grep -n "Phase 4 (v0.10.0 shipped" README.md`
Expected: one match.

Run: `grep -n "Phase 4 (next)" README.md`
Expected: no matches (empty output, exit code 1 from grep).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): mark Phase 4 as shipped in v0.10.0 roadmap"
```

---

### Task 6: Add scope note to CHANGELOG.md [Unreleased] section

**Files:**
- Modify: `CHANGELOG.md:22-23`

- [ ] **Step 1: Read current state**

Use the `Read` tool on `CHANGELOG.md` with `offset=20, limit=10`.
Expected line 22: `## [Unreleased]` followed by a blank line at 23 and `### Added` at 24.

- [ ] **Step 2: Insert a scope sentence immediately after the [Unreleased] heading**

After the line `## [Unreleased]` (line 22) and its blank line, insert a scope note so the section reads:
```
## [Unreleased]

Post-release audit fixes for Phase 4 v0.10.0 — all 23 HIGH-severity items. MEDIUM and LOW audit items remain open in `BACKLOG.md`.

### Added
```

The existing `### Added` / `### Changed` / `### Fixed` / `### Stats` sub-sections stay untouched.

- [ ] **Step 3: Verify**

Run: `grep -n "all 23 HIGH-severity items" CHANGELOG.md`
Expected: one match in the `[Unreleased]` section near the top.

Run: `sed -n '20,30p' CHANGELOG.md` (or `Read` with `offset=20, limit=12`)
Expected: the heading, the new scope sentence, blank line, then `### Added`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note [Unreleased] covers HIGH-severity audit fixes only"
```

---

### Task 7: Final consistency sweep

**Files:** none modified — read-only verification.

- [ ] **Step 1: Confirm no stale "Phase 4 complete" strings remain in top-level docs**

Run: `grep -rn "Phase 4 complete" BACKLOG.md CHANGELOG.md CLAUDE.md README.md`
Expected: no matches (empty output).

If any matches appear, open the file, re-read Tasks 2/3/5, and edit the stale line to match the new phrasing.

- [ ] **Step 2: Confirm the audit scope is consistently worded across docs**

Run: `grep -n "HIGH-severity audit" BACKLOG.md CHANGELOG.md CLAUDE.md README.md`
Expected: at least one match in each of the four files. (Approximate wording is fine — the goal is that every status surface flags the HIGH-only scope, not that the wording is identical.)

- [ ] **Step 3: Confirm `[Unreleased]` body still lists the audit fixes**

Run: `grep -c "^- " CHANGELOG.md | head -1` (rough sanity check — output should be a large integer, well into the hundreds).

Run: `sed -n '24,78p' CHANGELOG.md` (or `Read` with `offset=24, limit=55`)
Expected: `### Added`, `### Changed`, `### Fixed` (with `#### Security` / `#### Observability` / `#### Query correctness` / `#### Compile / graph` / `#### Ingest data integrity` / `#### Concurrency` sub-sections), `### Stats` all still present. If any of these are missing, the Task 6 insertion went in the wrong place — revert and retry.

- [ ] **Step 4: Final commit if anything was corrected during the sweep; otherwise skip**

If Step 1 or Step 2 surfaced an issue and required another edit:
```bash
git add -A
git commit -m "docs: sweep — align residual Phase 4 status wording"
```

If no edits were needed, no commit — skip this step.

---

## Notes on scope and what this plan does NOT do

- **No version bump.** Whether `[Unreleased]` should become `0.10.1` is a separate release-process decision. This plan only corrects narrative status claims.
- **No MEDIUM/LOW item fixes.** Those are the 54 open bugs; fixing them is a separate plan per the user's earlier triage choice.
- **No audit-fixes plan file changes.** `docs/superpowers/plans/2026-04-12-phase4-audit-fixes.md` was already marked complete in a prior commit (`ff23484`); nothing here touches it.
- **No re-rendering of the architecture diagram.** The diagram is only updated when architecture changes; none here.

## Self-review checklist (performed before save)

1. **Spec coverage:** The goal was "update docs/status to reflect true Phase 4 completion". Tasks 1–6 cover the four files carrying the misleading claim (`BACKLOG.md`, `CLAUDE.md` x2, `README.md`) plus the `CHANGELOG.md` scope note. Task 7 is the consistency sweep. ✓
2. **Placeholder scan:** No "TBD" / "similar to" / "appropriate" — every Edit shows the exact old and new strings. ✓
3. **Type consistency:** Not applicable (no code). Cross-file wording is intentionally not required to be identical — only consistent in meaning. Task 7 verifies this. ✓
