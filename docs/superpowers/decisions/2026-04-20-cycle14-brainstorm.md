# Cycle 14 — Brainstorm

**Date:** 2026-04-20
**Step:** 3 (feature-dev pipeline)
**Mode:** Auto-approve (per user memory `feedback_auto_approve`)

## Context

- Step 1 requirements: 24 AC across 12 source files (see `2026-04-20-cycle14-requirements.md`).
- Step 2 threat model: 10 items T1..T10, 6 AC amendments flagged (see `2026-04-20-cycle14-threat-model.md`).
- User ask: "fix as many as backlog items 30+" across multiple files, per `feedback_batch_by_file` memory.

## Approaches

### A — "Big batch" (current Step-1 scope, 24 AC)

Ship everything in one cycle: metadata fields + lint validation + query gates + publish module + wrapper + augment migration + status boost. Primary-session execution for small ACs (cycle-13 L2 heuristic); Codex-dispatched only for the publish module (novel JSON-LD work ≥100 combined lines).

- **Pros:**
  - Closes ~10-15 BACKLOG entries in one cycle; matches user ask.
  - Threat mitigations T1-T10 are localized (no cross-module refactor) — each fix lives in the file its AC names.
  - Phase 5 Tier-1 (`/llms.txt`) ships alongside Epistemic-Integrity fields so next cycles focus on harder HIGH items.
- **Cons:**
  - Largest cycle since cycle-12 (17 AC); review surface is wide.
  - T2 filtering logic cuts across three publish builders — needs central helper to avoid drift.
- **Risk level:** Medium. Cycle-13 shipped cleanly with 8 AC; scaling 3× requires disciplined primary-session/Codex split and parallel test writing.

### B — "Metadata-first slice" (12 AC, defer publish)

Ship frontmatter fields + lint validation + coverage gate + save wrapper + augment migration only. Defer `kb.compile.publish` + `kb publish` CLI to cycle 15.

- **Pros:**
  - Narrower review; easier T1/T3/T8 threats avoided (publish not touched).
  - Frontmatter/lint changes are mechanical — very low regression risk.
- **Cons:**
  - Tier-1 Karpathy-verbatim item (`/llms.txt`) keeps slipping; has been #1 recommended for two cycles.
  - Status boost (AC23) loses half its value without a publish surface to demo.
  - Fails user's "30+" target.

### C — "Publish-first slice" (12 AC, defer metadata)

Ship only publish module + `kb publish` CLI + save wrapper + augment migration + status boost. Defer belief_state/authored_by/status fields + query gates to cycle 15.

- **Pros:**
  - Ships Tier-1 recommended-next externally visible feature.
  - Publish module threat mitigations (T1, T2, T3, T8) all land in one file.
- **Cons:**
  - T2 mitigation (filter speculative/retracted/contradicted) needs `belief_state` vocabulary — which is NOT shipped in this slice. Hardcoding the filter without the vocabulary means cycle-15 needs a second pass over publish.py.
  - Status boost (AC23) ships without the `status` field being validated — invalid values go through the boost check anyway.
  - Fails user's "30+" target.

## Recommendation

**Approach A.** Reasons:

1. User explicitly asked for 30+ items. B and C both fail that bar.
2. T2 creates a cross-AC coupling (publish filter needs belief_state vocabulary) that makes splitting strategies wasteful.
3. Primary-session heuristic (cycle-13 L2) applies to every AC except AC20 (publish builders, ≥100 combined lines → Codex). Execution pipeline is well-understood.
4. Threat-model amendments in Step 5 gate tighten AC5/AC11/AC14/AC20/AC21 but don't change the count.

**Open questions (flagged for Step 5 decision gate):**

- **Q1 (T2 scope):** Should publish builders filter `belief_state: stale` too, or only `retracted`/`contradicted`? AC1 lists 5 belief states; T2 flags only 2.
- **Q2 (T5 advisory):** Fixed template vs sanitized-question echo vs question-free (just numerical score)?
- **Q3 (T6 matcher):** Hostname-only (`urlparse(ref).hostname`) vs full-URL check? What about bare-domain source_refs (no scheme)?
- **Q4 (T7 parent scan):** `path.parent.name` only (immediate parent), or walk upward scanning for first match? Affects files in nested subdirs.
- **Q5 (T8 `url` field):** POSIX relative only, or should we emit `https://...` when a deployed wiki URL is configured?
- **Q6 (T9 status boost):** Co-gate on `authored_by in (human, hybrid)`, or accept LLM-set `mature` (trust the pipeline)?
- **Q7 (AC20 size cap):** `build_llms_full_txt` hard cap 5 MB is specified. Truncate mid-page vs drop pages past cap?
- **Q8 (AC22 kb publish):** Should `kb publish` regenerate outputs on every run or diff against existing file mtimes and skip unchanged?
- **Q9 (AC18 wrapper):** Should the three augment write-back sites also log before/after key order for debugging the cycle-7 M3 regression, or ship clean?
- **Q10 (AC23 boost magnitude):** +5% specified. Tunable constant in config.py, or inline literal?

Ten open questions → Step 5 decision gate resolves each.

## Decision

Proceed with Approach A. Dispatch Step 4 design-eval subagents (Opus + Codex) in parallel, then Step 5 gate resolves Q1-Q10.
