# Cycle 34 — Release Hygiene · Brainstorming (Step 3)

**Date:** 2026-04-25 · **Cycle:** 34 · **Mode:** lightweight 2-3-approach generation per feature-dev Step 3
**Inputs:** `docs/superpowers/decisions/2026-04-25-cycle34-requirements.md` (48 ACs, 17 file groups, 10 open design questions Q1-Q10) + `docs/superpowers/decisions/2026-04-25-cycle34-threat-model.md` (5 trust boundaries, 14 threats, 25-row Step-11 checklist).
**Approval flow:** User delegated approvals via `feedback_auto_approve` → resolution at Step 5 Opus decision gate, not at the brainstorming step.

---

## High-level shape — does cycle 34 need any reframing?

The cycle requires no creative architecture. It is mechanical hygiene: change a string in `pyproject.toml`, declare 5 extras, add a workflow file, replace a tagline in README, delete 6 files, write 12 fixture-free tests. The only non-mechanical decisions are:

1. CVE handling strategy in CI.
2. Extras structure (5 keys vs coarser).
3. Tests badge replacement strategy.
4. PDF — remove vs implement extractor.
5. Version bump 0.10.0 → 0.11.0 vs 0.10.1.
6. Whether to commit the comprehensive review under `docs/reviews/` or move/inline it.
7. Whether to also touch `README.zh-CN.md`.

For each, three approaches with the recommendation.

---

## Approach grid

### Q1 — `anthropic` runtime dep: required vs optional `[default-llm]` extra

**A. Keep required (recommended).** `anthropic>=0.7` stays in `dependencies = [...]`. The README's "no API key needed in MCP/Claude-Code mode" claim refers to the API KEY (env var), not to the SDK. The SDK is required because `kb.utils.llm.call_llm` lazy-imports it at runtime; without it, `kb compile`/`kb query` with `use_api=True` fail at first call. Default install must succeed.
**B. Move to `[default-llm]` extra; require `pip install kb-wiki[default-llm]` for any LLM work.** Cleanest separation but hostile to first-time users — the basic flow then needs an extra step.
**C. Move to `[default-llm]` extra AND add a runtime check that prints a helpful error if anthropic is missing AND `KB_LLM_BACKEND=anthropic` (the default).** Best UX but most work; risks a Step-9 footgun if the lazy-import is mis-wired.

**Pick A.** Matches user expectations; minimum risk. Extras still cover the OPTIONAL behaviour (hybrid, augment, formats, eval).

### Q2 — PDF support

**A. Remove `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` (recommended).** Already what the review recommends. Pre-cycle-34 the binary-rejection path fires AFTER the extension check; post-cycle-34, `.pdf` files raise an "unsupported extension" error sooner with a clearer message pointing at `markitdown`/`docling`. Net: better UX.
**B. Keep `.pdf`; implement real PDF extractor with `pypdf` or `pdfplumber`.** Adds a runtime dep, a size cap, a page cap, error handling for encrypted PDFs, and ≥1 cycle of work. Out of cycle-34 scope.
**C. Keep `.pdf`; only update the rejection message to point at conversion tools.** Confusing — "supported" claim still ships, error fires on every PDF.

**Pick A.** Aligns with cycle 34's "narrow + clarify" theme.

### Q3 — Extras structure

**A. 5 extras matching the review (recommended).** `hybrid`, `augment`, `formats`, `eval`, `dev`. Names mirror the README's feature taxonomy. Each maps to a small set of pinned packages.
**B. 3 coarser extras.** `runtime-extra` (everything beyond core), `eval`, `dev`. Lower cognitive cost but loses the "install only what I need" granularity.
**C. No extras at all; just declare runtime deps correctly and keep `requirements.txt` as the install path.** Punt the granularity. Doesn't close Finding 1 fully.

**Pick A.** The review explicitly recommends this set; matches Section 4 of the comprehensive review. Splitting the existing `requirements.txt` PINs into per-extra subset files is deferred to cycle 36 (per non-goals).

### Q4 — `pip-audit` strictness in CI

**A. Use `--ignore-vuln=ID` per documented narrow-role CVE; CI fails on any UNDOCUMENTED advisory (recommended).** SECURITY.md is the audit trail. Strong signal: green CI = "no new CVE since cycle 34 baseline". Threat T4's mitigation depends on this.
**B. `pip-audit` with `--strict` and no ignores.** Would fail CI today (4 known advisories). No-go without first patching all 4 — which is impossible (3 have no upstream fix).
**C. `pip-audit` with `continue-on-error: true` and report-only.** Loses the gating signal entirely. Defeats the purpose of CI security verification.

**Pick A.** Matches the threat model's T4 mitigation strategy.

### Q5 — Tests badge

**A. Replace with generic `tests-passing-brightgreen` (recommended).** Lowest maintenance; CI is the source of truth for whether tests pass.
**B. Static count `tests-2923-brightgreen` updated each cycle.** Drifts again next cycle. The Finding 6 problem.
**C. Dynamic shields.io endpoint that pulls from CI run history.** Best signal but needs a CI hook to update an external service. Cycle-N+1 work.

**Pick A.** Removes the drift surface entirely.

### Q6 — Version bump strategy

**A. Bump 0.10.0 → 0.11.0 (recommended).** Cycle 34 adds extras (user-visible new install paths), CI workflow (release-process change), SECURITY.md, and changes the package readme. These are minor-version-worthy additions per semver.
**B. Bump 0.10.0 → 0.10.1 patch.** Strict reading of "no API change" → patch. But extras declaration is a documented contract addition (downstream `pip install kb-wiki[hybrid]` is new); minor is more honest.
**C. Hold at 0.10.0; bump on next feature cycle.** Skips the signal that release hygiene shipped.

**Pick A.** Honest semver.

### Q7 — Comprehensive review file location

**A. Commit at `docs/reviews/2026-04-25-comprehensive-repo-review.{md,html}` (recommended).** Already there as untracked files. Establishes a `docs/reviews/` convention for future audit artifacts.
**B. Move/rename to `docs/audits/<date>.md` or similar.** Bikeshed; no benefit.
**C. Delete the older `docs/repo_review.md` only; promote the comprehensive review to `docs/repo_review.md` (replacing).** Loses the date-stamped naming.

**Pick A.** Date-stamped review file in `docs/reviews/` is the right convention; delete the older superseded version per the review's own header note.

### Q8 — README.zh-CN.md sync

**A. Defer to a separate batched cycle (recommended).** The Chinese mirror lags by design (sync cadence is "every 2-3 cycles, in batch"). Concurrent edits risk drift in different directions.
**B. Mirror all cycle-34 changes in `README.zh-CN.md` this cycle.** Doubles the doc surface; makes the cycle-34 PR harder to review for non-Chinese readers.
**C. Add a header note to `README.zh-CN.md` saying "May be out of date by 1-2 cycles; English README is canonical".** Doc-debt acknowledgement; defers actual sync.

**Pick A** with a one-line addition of **C** — add the "English is canonical" note as part of AC23 OR a new AC23.5. Inexpensive, doesn't bloat the cycle.

### Q9 — `pip check` in CI: gate or report?

**A. `continue-on-error: true` on the `pip check` step (recommended).** Three known conflicts (`arxiv`/`requests`, `crawl4ai`/`lxml`, `instructor`/`rich`) would block CI today. The cycle-N+1 follow-up unblocks. Step T5's threat model accepts this with documented unblock plan.
**B. Skip `pip check` entirely.** Loses the resolver-conflict signal. Doesn't matter much because the conflicts are already known and don't break runtime imports — but a NEW conflict would slip in.
**C. Strict `pip check` after first patching the three conflicts.** 1+ cycle of upstream tracking. Out of cycle-34 scope.

**Pick A.** Soft-fail with named-cycle unblock plan.

### Q10 — `requirements.txt` restructure

**A. Keep as full-dev superset; add only a header comment (recommended).** Minimal-risk; pins are unchanged. Splitting per-extra is cycle-36 follow-up.
**B. Split into `requirements-runtime.txt`, `requirements-dev.txt`, `requirements-eval.txt`, `requirements-hybrid.txt`, `requirements-augment.txt`.** Concurrent reshuffle with extras declaration is risky — too many things changing at once.
**C. Delete `requirements.txt` entirely; rely on `pyproject.toml` extras.** Strongest position-statement but breaks the existing `pip install -r requirements.txt && pip install -e .` quick-start pattern in README.

**Pick A.** Matches the "narrow scope" principle of cycle 34.

---

## Summary table — defaults entering Step 4 design eval

| Q | Pick | Why |
|---|---|---|
| Q1 | A — keep `anthropic` required | Default install must work; "no API key" refers to env var, not SDK |
| Q2 | A — remove `.pdf` from supported list | Review's recommendation; net-better UX |
| Q3 | A — 5 extras: hybrid/augment/formats/eval/dev | Matches review §4 + Finding 18 |
| Q4 | A — `pip-audit --ignore-vuln` per documented CVE | T4 mitigation; SECURITY.md is the audit trail |
| Q5 | A — generic `tests-passing` badge | Removes drift surface; CI is source of truth |
| Q6 | A — bump to 0.11.0 minor | Honest semver for extras + CI + SECURITY.md additions |
| Q7 | A — `docs/reviews/<date>-...md` location | Date-stamped convention for audit artifacts |
| Q8 | A + tiny C — defer zh-CN sync; add "English canonical" header note | Cheap doc-debt acknowledgement |
| Q9 | A — `continue-on-error: true` on `pip check` | Soft-fail with named-cycle unblock plan |
| Q10 | A — `requirements.txt` unchanged + header comment | Risk discipline; reshuffle in cycle 36 |

All defaults are conservative and minimise blast radius. Step 4 design eval (R1 Opus + R2 Codex parallel) and Step 5 decision gate (Opus subagent) will challenge each, but the bias of cycle 34 is "narrow scope, mechanical fixes" — the defaults reflect that.

---

## What I am NOT brainstorming

(Confirming explicit non-goals from the requirements doc § 2.)

- Pre-ingest secret/PII gate → **cycle 35**.
- Async MCP tools → **cycle 35 or later**.
- Ingest receipt/recovery → **cycle 37**.
- `config.py` god-module split → **cycle 37**.
- Golden/snapshot tests → **cycle 36**.
- PRD `docs/prd/v0.10.md` → **cycle 38**.
- `docs/superpowers/decisions/` subdivision → **cycle 36/38**.
- Real PDF extraction → cycle-N+1 if requested.
- `requirements.txt` per-extra split → **cycle 36**.

---

End of brainstorming.
