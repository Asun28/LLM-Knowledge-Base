# Cycle 34 — Release Hygiene · Step 5 Decision Gate

**Date:** 2026-04-25 · **Cycle:** 34 · **Decider:** Opus 4.7 (1M)
**Inputs:** requirements doc (48 ACs), threat model (5 TBs / 14 threats / 25-row checklist), brainstorming Q1-Q10 defaults, R1 Opus eval (APPROVE-WITH-CONDITIONS), R2 Codex-fallback eval (APPROVE-WITH-CONDITIONS, 8 NEW threats / 8 blocking conditions / 7 non-blocking).
**Output convention:** `docs/superpowers/decisions/2026-04-25-cycle34-design.md` (Step-5 standard).

---

## Verdict

**APPROVE-WITH-CONDITIONS.**

The 48-AC release-hygiene cycle is fundamentally sound. R1 and R2 surfaced amend-shape changes (line-number drift, untracked-not-tracked deletion semantics, version-bump symmetry across four sites, boot-lean import surface, missing CI tooling pkgs, comment-stale-after-AC24). All resolved inline below. Final AC count: **57** (48 original + 4 from AC4 four-site split into AC4a-AC4e + 5 new ACs for boot-lean fix, CI tooling install, concurrency, pytest-httpx, architecture diagram). Zero ESCALATIONs.

---

## Decisions

### Q1 — `anthropic` runtime dep: required vs `[default-llm]` extra

OPTIONS: A KEEP REQUIRED | B `[default-llm]` extra | C extra + runtime check

ARGUE:
## Analysis
The `anthropic` SDK is lazy-imported by `kb.utils.llm.call_llm` and is the default LLM backend whenever `KB_LLM_BACKEND` is unset. The README's "no API key required" claim refers strictly to the env-var (which Claude Code MCP supplies via session token), not to the SDK itself. A user running `pip install kb-wiki` and then `kb compile` (without setting `KB_LLM_BACKEND=cli`) would hit `ImportError` on the very first call if `anthropic` were extras-only. That is precisely the kind of post-install footgun cycle 34 is supposed to close, not introduce.

Option B (extras-only) breaks the default install path. Option C (extras + runtime check) is more polished but introduces a non-trivial code change in cycle 34's "metadata-only" theme — a Step-9 footgun if the lazy-import error message is mis-wired. R1 and R2 both AGREE with brainstorming default A. Cycle 34's bias is "narrow scope, mechanical fixes"; A satisfies that. C is a cycle-N+1 nice-to-have if anyone actually uses the CLI-backend path enough that they want to drop the SDK.

DECIDE: **A — KEEP REQUIRED**.
RATIONALE: Default install must succeed end-to-end without extras. R1 + R2 + brainstorming all converge.
CONFIDENCE: HIGH

### Q2 — PDF: remove from `SUPPORTED_SOURCE_EXTENSIONS` (a) or implement extractor (b)?

OPTIONS: A REMOVE | B IMPLEMENT EXTRACTOR | C KEEP+UPDATE-MESSAGE-ONLY

ARGUE:
## Analysis
The current code path already rejects binary PDFs after the extension check passes — the user gets a `UnicodeDecodeError`-chained `ValueError("Binary file cannot be ingested")` from `pipeline.py:1261`. This means today's user with a `raw/papers/foo.pdf` file already fails on ingest; option A merely moves the rejection earlier (extension check) with a clearer error pointing at `markitdown`/`docling`. Net behaviour: better UX, no regression. Option B (implement real extractor) means adding `pypdf` or `pdfplumber` as a runtime dep, handling encrypted PDFs, page caps, size caps — easily 1+ cycle of work and out of cycle-34 scope (explicit non-goal).

Option C is confusing — leaves the "supported" claim shipping while every PDF errors. R1, R2, and the comprehensive review all recommend A. T8 in the threat model confirms the change is a feature-narrowing (defence-in-depth tightening), not a feature regression. A BACKLOG entry for "real PDF text extraction (cycle-N+1 if requested)" tracks the future option-B path.

DECIDE: **A — REMOVE**.
RATIONALE: Comprehensive-review recommendation; net-better UX (extension-rejected at scan time vs binary-rejected at read time); B is out of scope.
CONFIDENCE: HIGH

### Q3 — Extras structure: 5 keys vs coarser?

OPTIONS: A 5 keys (hybrid/augment/formats/eval/dev) | B 3 coarser | C no extras

ARGUE:
## Analysis
The README's feature taxonomy already names `hybrid`, `augment`, output formats, eval-harness, and dev tooling as five distinct user-facing capabilities. Mapping `[project.optional-dependencies]` 1:1 to that taxonomy keeps install-time and feature-time vocabularies aligned — `pip install kb-wiki[hybrid]` does what its name says. Option B's three coarser extras (`runtime-extra`, `eval`, `dev`) collapse two distinct capability groups into one bucket and force users who want only `[augment]` to install `[hybrid]`'s ML dependencies (model2vec, sqlite-vec, numpy) too. That defeats the granularity gain and makes minimal installs heavier than necessary.

R1 and R2 both AGREE with the 5-key structure. R2 added concrete pin lower-bounds per extra (see Q25 below). Brainstorming approach C (no extras) doesn't close Finding 1 — packaging metadata still misaligns with code imports.

DECIDE: **A — 5 keys**.
RATIONALE: Matches README feature taxonomy; matches comprehensive review §4; matches both reviewers.
CONFIDENCE: HIGH

### Q4 — `pip-audit` strict vs `--ignore-vuln`?

OPTIONS: A `--ignore-vuln` per documented narrow-role | B strict | C continue-on-error

ARGUE:
## Analysis
Strict `pip-audit` would fail CI on day 1 because none of the four narrow-role advisories have available upstream fixes that are installable without breaking other pins (litellm 1.83.7 is the only one with a fix, blocked by the `click<8.2` transitive). `continue-on-error: true` (option C) loses the gate signal entirely — the CI green-checkmark would mean "pytest passed and we ignore everything else", which defeats the purpose of having the audit step at all.

Option A keeps the audit teeth-bearing while honestly documenting the four exceptions in `SECURITY.md`. The four `--ignore-vuln` flags are by-CVE-ID (not by-package), so a NEW vulnerability on the same package surfaces as a new failure. T4 in the threat model confirms this is the correct mitigation strategy and AC8 documents the per-cycle re-check cadence so the ignore list cannot outlive its rationale silently.

DECIDE: **A — `--ignore-vuln` per documented CVE**.
RATIONALE: Keeps audit gate meaningful (zero NEW CVEs); `SECURITY.md` is the audit trail; T4 mitigation strategy explicitly designed for this.
CONFIDENCE: HIGH

### Q5 — `KB_DISABLE_VECTORS=1` runtime flag or extras-only opt-out?

OPTIONS: A EXTRAS-ONLY | B add runtime flag | C extras + flag

ARGUE:
## Analysis
R1 grep-confirmed `KB_DISABLE_VECTORS` does NOT exist anywhere in `src/kb/`. Adding a runtime kill-switch in cycle 34 is non-trivial code work in a metadata-themed cycle. The simpler and more honest path is "if you don't install `[hybrid]`, the hybrid layer simply isn't importable" — which is already true today (model2vec and sqlite-vec are lazy-imported in `kb.query.embeddings`). Option B introduces a new env var, requires new tests, and is exactly the kind of feature-creep cycle-34 is supposed to avoid.

R1 explicitly recommends narrowing AC19 to "extras-only opt-out" up-front rather than at verify time, to avoid a DESIGN-AMEND late in Step 9. R2 doesn't address this directly but the boot-lean concern (NEW-Q14) is a related issue — if extras-only is the opt-out, then the boot path must not transitively import extras-only modules.

DECIDE: **A — EXTRAS-ONLY**.
RATIONALE: `KB_DISABLE_VECTORS` doesn't exist; cycle 34 is metadata-themed; runtime flag is cycle-N+1 if anyone asks. Narrows AC19 contract.
CONFIDENCE: HIGH

### Q6 — Tests badge: static count, generic, dynamic shield?

OPTIONS: A generic `tests-passing` | B static count | C dynamic shields.io endpoint

ARGUE:
## Analysis
The original Finding 6 is exactly that the static count drifts — `tests-2850` while live count is 2923. Option B re-creates the same drift problem on a slightly later schedule. Option C is the most informative but requires a CI hook that updates an external service (shields.io endpoint), which is cycle-N+1 work. Option A removes the drift surface entirely by stating only the binary "passing" claim, which CI gating itself enforces.

The downside of A is loss of test-count signal at the README level. But the README has a "Latest full-suite" line in CLAUDE.md and a CHANGELOG entry per cycle that already document exact counts; the badge's job is to give a quick green/red indicator at glance, not to be a metric dashboard. R1, R2, and brainstorming all converge.

DECIDE: **A — generic `tests-passing-brightgreen`**.
RATIONALE: Removes drift surface entirely; CI is source of truth for "passing"; B re-creates the bug.
CONFIDENCE: HIGH

### Q7 — Comprehensive review file location?

OPTIONS: A `docs/reviews/<date>-...md` | B move/rename | C promote to canonical

ARGUE:
## Analysis
The review file already exists at `docs/reviews/2026-04-25-comprehensive-repo-review.md` (untracked). Date-stamped reviews under `docs/reviews/` is a clean convention because future audits can land alongside without renaming. Option B (move/rename) is bikeshed. Option C (promote to a canonical `docs/repo_review.md`) loses the date-stamp and creates an ambiguous "which is the latest?" problem if a future review supersedes this one.

R1 AGREES; R2 doesn't push back. The cycle-34 design also DELETES the older `docs/repo_review.{md,html}` (AC33-AC34) which the new review explicitly supersedes per its own header note.

DECIDE: **A — `docs/reviews/<date>-...md`**.
RATIONALE: Date-stamped naming under `docs/reviews/`; future-audit-friendly; matches R1 + R2.
CONFIDENCE: HIGH

### Q8 — Translate cycle-34 to `README.zh-CN.md`?

OPTIONS: A defer | B mirror this cycle | C defer + add "English canonical" note

ARGUE:
## Analysis
The Chinese mirror lags by design (sync cadence is "every 2-3 cycles, in batch"). Mirroring all cycle-34 changes this cycle doubles doc surface and makes the cycle-34 PR harder to review for non-Chinese readers. Option C (defer + add a one-line "English canonical" header note) is the cheap doc-debt acknowledgement R1 recommends; it costs ~2 lines of zh-CN edit but prevents bilingual PR review burden in this cycle and signals to future readers that the zh-CN file may lag.

The note itself is content-neutral and doesn't risk drift in different directions. R1 explicitly recommends ADD AC23.5 for this; R2 silent (out of scope for R2's CI/edge-case lens).

DECIDE: **A + tiny C — DEFER cycle-34 zh-CN sync; ADD a 1-line "English canonical" header note via a new AC23.5**.
RATIONALE: Cheap doc-debt acknowledgement; doesn't bloat cycle 34; matches R1's AC23.5 proposal.
CONFIDENCE: HIGH

### Q9 — `pip check` in CI: gate or report?

OPTIONS: A `continue-on-error: true` | B skip entirely | C strict (after fixing 3 conflicts)

ARGUE:
## Analysis
The three known conflicts (`arxiv`/`requests`, `crawl4ai`/`lxml`, `instructor`/`rich`) would fail `pip check` strict on day 1. Option B loses NEW-conflict signal. Option C requires upstream package coordination (1+ cycle) and is out of cycle-34 scope. Option A keeps the diagnostic running and visible in logs, with a documented unblock plan (cycle-N+1 fixes the three known conflicts then drops `continue-on-error`). T5 in the threat model accepts this trade-off explicitly.

R1 + R2 both AGREE; R2 adds the edge-case that the `continue-on-error` directive must be at the STEP level (not job level) to avoid silently passing other steps. Step-11 verification covers this.

DECIDE: **A — `continue-on-error: true` on the `pip check` step ONLY**.
RATIONALE: Soft-fail with named-cycle unblock plan; T5 mitigation strategy.
CONFIDENCE: HIGH

### Q10 — `requirements.txt` restructure now or defer?

OPTIONS: A keep + header comment | B split per-extra | C delete and rely on extras

ARGUE:
## Analysis
Concurrent reshuffle of `requirements.txt` pins WHILE declaring new `pyproject.toml` extras is exactly the kind of "too many things changing at once" pattern that breaks PR review and tempts pin-drift. Cycle 34 is metadata-themed; cycle 36 is the dedicated test-infrastructure cycle where the per-extra split fits naturally.

Option A's header comment is a one-line addition that signals intent without changing pins. Option C breaks the existing `pip install -r requirements.txt && pip install -e .` quick-start pattern that the README documents. R1 + R2 + brainstorming all converge.

DECIDE: **A — keep unchanged + header comment**.
RATIONALE: Risk discipline; concurrent pin reshuffle is the cycle-36 split's job.
CONFIDENCE: HIGH

### NEW-Q11 — AC4 version bump scope (FOUR sites)

OPTIONS: A expand AC4 to all four | B split into AC4a/4b/4c/4d | C scope to pyproject + `__init__.py` only, defer architecture HTML + README badge

ARGUE:
## Analysis
Cycle-21's audit explicitly aligned `pyproject.toml.version` with `src/kb/__init__.py.__version__` after they drifted. The same alignment pattern must hold post-cycle-34 or `pip show kb-wiki` and `kb --version` will disagree. R2 grep-confirmed FIVE total touchpoints: `pyproject.toml:3`, `src/kb/__init__.py:3`, `README.md:11` badge, `docs/architecture/architecture-diagram.html:501`, `docs/architecture/architecture-diagram-detailed.html:398`. CLAUDE.md is also touched per AC26 (test-count + state-line update).

Option C (scope to pyproject + `__init__.py` only) creates known drift in `README.md:11` badge and the architecture diagrams — it's exactly the Finding-6-class drift cycle 34 is supposed to fix. Option A (expand AC4 to all four) keeps everything as one AC but obscures the per-site verification. Option B (split into AC4a/4b/4c/4d/4e) makes the regression tests crisper and matches the per-site verification pattern from the threat model. Architecture diagrams trigger the MANDATORY PNG re-render rule (CLAUDE.md), which is non-trivial — that gets its own AC4e covering BOTH HTML diagrams + the PNG re-render command.

DECIDE: **B — SPLIT AC4 into AC4a (pyproject.toml), AC4b (`src/kb/__init__.py`), AC4c (README.md:11 badge), AC4d (CLAUDE.md state line + Latest full-suite line), AC4e (architecture-diagram*.html + PNG re-render)**.
RATIONALE: Per-site regression visibility; matches feedback_batch_by_file granularity; AC4e isolates the Playwright re-render so failure modes are debuggable.
CONFIDENCE: HIGH

### NEW-Q12 — AC42 + AC43 merge or stay separate?

OPTIONS: A merge | B keep separate

ARGUE:
## Analysis
AC42 asserts scratch files absent (regression for AC29-32). AC43 asserts gitignore patterns present (regression for AC17). They cover the two halves of T7 mitigation independently — gitignore-without-deletion or deletion-without-gitignore both defeat the purpose. Merging into one super-test makes failures harder to debug (which half failed?). Keeping separate makes the regression matrix crisper.

R1 + R2 both lean SEPARATE.

DECIDE: **B — keep separate**.
RATIONALE: Per-half debuggability; T7 mitigation has two distinct failure modes.
CONFIDENCE: HIGH

### NEW-Q13 — `build` + `twine` + `pip-audit` install location

OPTIONS: A bloat `[dev]` | B dedicated `pip install` step in CI | C separate `[ci]` extra

ARGUE:
## Analysis
`build`, `twine`, and `pip-audit` are CI-tooling, not developer-tooling. Putting them in `[dev]` forces every contributor running `pip install -e '.[dev]'` to also pull these — they're not needed for `pytest` or `ruff`. Option C (`[ci]` extra) is conceptually clean but creates a new extra just for three tools, which is bikeshed for cycle 34's narrow scope. Option B (dedicated `pip install build twine pip-audit` step in `ci.yml`) is the simplest and most explicit — it makes the CI workflow self-contained and doesn't leak CI tooling into the developer install path.

R2 explicitly recommends Option B. Cycle-N+1 can introduce a `[ci]` extra if more CI tooling accumulates.

DECIDE: **B — dedicated `pip install build twine pip-audit` step in CI**.
RATIONALE: Keeps `[dev]` lean for actual developers; CI workflow self-contained; minimal blast radius.
CONFIDENCE: HIGH

### NEW-Q14 — Boot-lean import surface (`kb.cli` → `kb.lint.augment` → `kb.lint.fetcher` → `httpx`)

OPTIONS: A move httpx/trafilatura/httpcore to `dependencies` | B convert `kb.lint.augment` import to function-local | C narrow AC23 with caveat

ARGUE:
## Analysis
This is the most consequential R2 finding. AC23 promises a "minimal install" path (`pip install -e .` without extras). But `kb.cli` transitively imports `kb.lint.augment` at module scope, which imports `kb.lint.fetcher` at module scope, which imports `httpx` + `httpcore` + `trafilatura` at module top. Without `[augment]` installed, `kb --version` would `ImportError`. AC23 is currently false-by-design.

Option A (move to `dependencies`) defeats the purpose of having an `[augment]` extra at all — the whole point is "augment is opt-in". Option C (narrow AC23) acknowledges the bug honestly but ships a known broken minimal-install promise. Option B (function-local import) matches the cycle-23+ lazy-shim pattern already established for `mcp.browse`/`mcp.quality` and is the canonical fix. The change is narrow: convert `from kb.lint.fetcher import ...` at module top of `kb.lint.augment` to function-local imports inside the functions that need fetcher capabilities. This is a 5-10 line edit with no behavior change for users who DO install `[augment]`.

R2 recommends Option B. The cycle-31 boot-smoke test extension to verify minimal install works is a natural follow-up that closes the loop.

DECIDE: **B — convert `kb.lint.augment`'s module-top fetcher imports to function-local; ADD a new AC for boot-smoke regression**.
RATIONALE: Matches established cycle-23+ lazy-shim pattern; keeps `[augment]` extras as actually opt-in; minimal blast radius (5-10 line edit); HIGH-severity AC23 false-promise gets closed honestly.
CONFIDENCE: HIGH

### NEW-Q15 — Architecture diagram version bump (HTML + PNG re-render)

OPTIONS: A update HTML + re-render PNG + commit (this cycle) | B defer to cycle 35 with BACKLOG entry | C update HTML only, skip PNG (violates MANDATORY rule)

ARGUE:
## Analysis
CLAUDE.md states: *"Every HTML edit must re-render the PNG and commit it"* under the MANDATORY heading. This is a load-bearing rule the project has enforced for prior cycles. Option C (update HTML only, skip PNG) directly violates this and creates exactly the kind of doc-drift cycle 34 is closing. Option B (defer entirely to cycle 35) is reasonable but means cycle 34 ships with a known `v0.10.0` diagram badge while everything else says `v0.11.0` — which IS drift, just in a contained doc.

Option A is the disciplined choice: the Playwright re-render is one bash command (the project has prior commits showing the exact invocation: `1440x900 viewport, device_scale_factor=3, full_page=True, png`). Cycle 34 already touches docs heavily; adding the diagram re-render is incremental cost and matches the project's MANDATORY rule. Worst case: if the Playwright re-render fails or produces a visual diff Step-11 doesn't accept, it can be split off as cycle 35 with a BACKLOG entry — but the design should plan for A and only fall back to B if the re-render breaks.

DECIDE: **A — update HTML + re-render PNG + commit, as a new AC4e (under the AC4 split per NEW-Q11)**.
RATIONALE: MANDATORY CLAUDE.md rule; avoids self-inflicted version-badge drift; B is fallback if A breaks at Step 9.
CONFIDENCE: MEDIUM (Playwright re-render carries some Step-9 risk; documented fallback to B if needed.)

### NEW-Q16 — Workflow trigger scope

OPTIONS: A `on: [push, pull_request]` (broad) | B push: branches: [main], pull_request: {} | C intermediate

ARGUE:
## Analysis
Broad `on: [push, pull_request]` runs CI on every push to every branch, including throwaway feature branches before they're opened as PRs. At the project's velocity (~1.6 cycles/day per CLAUDE.md), this burns CI minutes for branches that may never become PRs. Option B narrows push to `main` (post-merge sanity check) and keeps `pull_request` open for every PR — which is exactly when CI signal is most valuable. Intermediate options (e.g., push: branches: [main, develop]) don't apply because this project doesn't use a develop-branch model.

R2 surfaced this as NT4 (MEDIUM, cost-not-security). The narrowing is one-line and reversible. Cycle-34 is exactly the cycle to set good defaults for the new workflow file.

DECIDE: **B — `on: { push: { branches: [main] }, pull_request: {} }`**.
RATIONALE: ~50% CI minutes saved; signal-rich (PR-time + post-merge); reversible.
CONFIDENCE: HIGH

### NEW-Q17 — `pip-audit` scope: installed env vs `-r requirements.txt`

OPTIONS: A audit installed venv | B `pip-audit -r requirements.txt`

ARGUE:
## Analysis
`pip-audit` without `-r` audits whatever's resolved in the live environment after `pip install -e '.[dev]'`. That's a SUBSET of the full pin set in `requirements.txt` (which includes hybrid + augment + eval + crawl4ai + playwright). A vulnerability that affects, say, `crawl4ai` would NOT be flagged because `crawl4ai` isn't in `[dev]` so isn't installed in the CI env. A downstream user running `pip install -r requirements.txt` would face that vuln; CI would silently miss it.

Option B (`pip-audit -r requirements.txt`) audits the full pin set the user is actually exposed to. Stronger assurance. The `--ignore-vuln` flags still apply identically. R2 explicitly recommends Option B.

DECIDE: **B — `pip-audit -r requirements.txt --ignore-vuln=...`**.
RATIONALE: Audits the full pin set users actually face; CI green-checkmark becomes a meaningful claim about user-facing supply chain.
CONFIDENCE: HIGH

### NEW-Q18 — `permissions: read-all` block

OPTIONS: A explicit AC9 condition + Step-11 grep | B new AC9.5 | C fold into AC9 wording with Step-11 grep

ARGUE:
## Analysis
The `permissions:` block is the principle-of-least-privilege guard for fork-PR token scope (T1 mitigation). It's a one-line addition to the workflow YAML. The question is purely organizational: where does this AC live?

Option A (condition under AC9) keeps AC9 as the umbrella "workflow exists and triggers correctly" AC and lists `permissions: read-all` as a verifiable condition under it — matches the existing AC9 format that already lists conditions. Option B (new AC9.5) is granular but adds an AC for what is logically part of "the workflow file is configured correctly". Option C is identical to A in effect.

R1 leans A; R2 leans toward an explicit assertion (either A or B). Threat-model row 2 already specifies the exact grep verification.

DECIDE: **A — explicit AC9 CONDITION + Step-11 row 2 grep**.
RATIONALE: Keeps AC count contained; matches threat-model verification row 2; principle-of-least-privilege is a CONDITION under "workflow correctly configured", not a separate concern.
CONFIDENCE: HIGH

### NEW-Q19 — Untracked deletions: `rm` vs `git rm`

OPTIONS: A `rm` (filesystem); update T7 to `test ! -f` | B `git rm` (would error since untracked) | C either

ARGUE:
## Analysis
R1 grep-confirmed all six "deletions" are UNTRACKED — `git ls-files` returns empty for `findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`, `docs/repo_review.md`, `docs/repo_review.html`. `git rm` on an untracked file errors with `fatal: pathspec 'X' did not match any files`. So option B doesn't work mechanically. Option A (filesystem `rm`) is the only viable approach. The threat-model's T7 verification row 11 currently uses `git ls-files` which is degenerate (passes pre-cycle AND post-cycle). Updating it to `test ! -f` (or `[ ! -f ]`) makes the regression actually meaningful.

R1 explicitly flagged this as Open-issue #1. Cycle-34 design must enshrine this in T7's verification text and Step-9's implementation guidance.

DECIDE: **A — filesystem `rm`; UPDATE T7 row 11 to use `test ! -f` for each path**.
RATIONALE: `git rm` mechanically fails on untracked files; T7 verification gains real teeth via `test ! -f`.
CONFIDENCE: HIGH

### NEW-Q20 — `claude4.6.md` diff snapshot in PR description

OPTIONS: A include `diff CLAUDE.md claude4.6.md` snapshot | B rely on cycle-17-L3 escape hatch only

ARGUE:
## Analysis
`claude4.6.md` is 40 KB / 314 lines and starts with `# CLAUDE.md` header — confirmed an older snapshot. The risk register Row 4 already mandates "if diff shows novel content, abort the delete and surface as a DESIGN-AMEND per cycle-17 L3." That escape hatch handles the *novel-content* case. The question is whether the cycle-34 PR description should also INCLUDE a diff snapshot for transparency.

Option A makes the deletion auditable in the PR record itself — future readers can see what was deleted without `git show`-ing pre-cycle commits. Option B saves PR-description bloat (40 KB diff) but loses the audit trail. The diff is large but PR descriptions can link to a gist or a separate `docs/reviews/2026-04-25-claude4.6-diff.txt` artifact rather than inlining 40 KB.

DECIDE: **A — include the diff in PR description, possibly via a linked artifact at `docs/reviews/2026-04-25-claude4.6-deletion-diff.txt`** (untracked at delete-time, then referenced from PR description).
RATIONALE: Auditability; cycle-17 L3 is escape-hatch for SURPRISES, not a substitute for proactive transparency on a 40 KB deletion. Keeps PR description focused while preserving the diff for review.
CONFIDENCE: MEDIUM (diff artifact location is implementation detail; principle is "preserve diff somewhere referenceable").

### NEW-Q21 — AC25 message rewrite scope

OPTIONS: A cosmetic enumeration rewrite | B no-op + assert existing | C drop AC25

ARGUE:
## Analysis
R1 confirmed the current rejection message at `pipeline.py:1261-1262` already says `"Convert to markdown first (e.g., markitdown or docling)"` — already names the conversion tools. So AC25 isn't fixing a bug; it's improving UX. Option A enumerates supported extensions (`f"Only text source types ({', '.join(sorted(SUPPORTED_SOURCE_EXTENSIONS))}) are supported"`) which is genuinely more helpful — the user immediately sees what IS allowed. Option B is honest about the no-op nature but loses the UX improvement. Option C drops the AC entirely; the AC24 frontline change still happens, but the rejection message stays slightly less helpful.

R2 also flagged that AC25 should expand to update the stale comment at `pipeline.py:1198` (`"allowlist (includes .pdf)"`) which becomes incorrect post-AC24. So AC25's scope expands regardless. Combining: AC25 covers (1) message rewrite at lines 1261-1262 to enumerate supported extensions and (2) comment update at line 1198.

DECIDE: **A + R2 expansion — cosmetic message rewrite enumerating supported extensions AND comment update at line 1198**.
RATIONALE: Better UX (user sees supported list immediately); R2 comment-stale fix is mandatory regardless; Option C wastes an opportunity.
CONFIDENCE: HIGH

### NEW-Q22 — AC25 covers comment at `pipeline.py:1198`

OPTIONS: A confirm AC25 expands | B leave comment stale

ARGUE:
## Analysis
The comment at `pipeline.py:1198` reads `"allowlist (includes .pdf) so PDFs still hit the UTF-8 decode path where they fail with the helpful message"`. After AC24 removes `.pdf` from the allowlist, the lib will reject `.pdf` at line 1200 with `Unsupported source extension: '.pdf'` BEFORE the UTF-8 decode runs — so the comment's premise is false. Leaving stale comments is exactly the kind of code-doc drift cycle 34 is closing.

R2 flagged this; R1 didn't catch it but doesn't oppose. The comment update is one line; minimal Step-9 burden.

DECIDE: **A — confirm AC25 expansion**.
RATIONALE: Stale comment is code-doc drift; cycle 34's whole theme is closing drift; one-line edit.
CONFIDENCE: HIGH

### NEW-Q23 — `concurrency:` group in workflow

OPTIONS: A add | B skip

ARGUE:
## Analysis
GitHub Actions `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` cancels superseded workflow runs when a new push to the same PR/branch arrives. Without it, multiple pushes to the same PR trigger overlapping CI runs, doubling/tripling CI minutes. Saves ~50% CI minutes for active PRs that get rebased or amended frequently.

The directive is 3 lines of YAML. Zero security implications (it doesn't change permissions or trigger scope). R2 flagged as LOW priority but cheap. Cycle 34 is the right cycle to set good workflow defaults; adding it later means a follow-up workflow PR.

DECIDE: **A — add `concurrency:` group**.
RATIONALE: Cheap, immediate CI-cost savings; right time to set workflow defaults; non-blocking but high-value-per-line.
CONFIDENCE: HIGH

### NEW-Q24 — `pytest-httpx` in `dev` extra

OPTIONS: A add | B skip

ARGUE:
## Analysis
R2 verified ~30 augment tests use `pytest-httpx` to mock fetcher behaviour. Without it, those tests fail on CI — a green-CI saboteur because contributors running `pip install -e '.[dev]'` and then `pytest` get failures unrelated to their changes. `pytest-httpx==0.36.2` is already pinned in `requirements.txt`; adding `pytest-httpx>=0.30` to the `dev` extra is one line.

Skipping (Option B) means the CI install path differs from the `requirements.txt` path on a load-bearing test dep, which is exactly the kind of CI-vs-local drift cycle 34 should not introduce.

DECIDE: **A — add `pytest-httpx>=0.30` to `dev` extra**.
RATIONALE: Required by ~30 augment tests; CI green-checkmark requires it; one-line addition.
CONFIDENCE: HIGH

### NEW-Q25 — Concrete pin lower-bounds per extra

OPTIONS: A R2's proposed pins | B looser bounds | C exact == pins

ARGUE:
## Analysis
R2 proposed concrete `>=` lower-bounds based on the actual versions in `requirements.txt`:
- `hybrid` = `model2vec>=0.5.0`, `sqlite-vec>=0.1.0`, `numpy>=1.26`
- `augment` = `httpx>=0.27`, `httpcore>=1.0`, `trafilatura>=1.12`
- `formats` = `nbformat>=5.0,<6.0`
- `eval` = `ragas>=0.4`, `litellm>=1.83`, `datasets>=4.0`
- `dev` = `pytest>=7.0`, `ruff>=0.4.0`, `pytest-httpx>=0.30`

Lower-bounds are the right choice for `[project.optional-dependencies]` — they assert the minimum API surface kb depends on without over-constraining downstream users. Option C (exact `==`) over-constrains and forces version churn every time a transitive bumps. Option B (looser e.g. no bounds) loses the API-surface assertion. R2's pins match the actual import surface and are conservative.

For `nbformat`, the `<6.0` upper bound is preserved from `requirements.txt:156` because nbformat 6.x has known schema-incompatibility risk; a cycle-N+1 task can re-evaluate.

DECIDE: **A — R2's proposed pins, verbatim**.
RATIONALE: Lower-bounds match actual API surface; conservative without over-constraining; aligned with `requirements.txt`.
CONFIDENCE: HIGH

### AMEND AC18 — README copy change preserves `> blockquote` markup

OPTIONS: A accept R1 verbatim | B counter-propose

ARGUE:
## Analysis
R1's amendment preserves the `> ` blockquote markup at line 5 (replacing the line wholesale, NOT splitting into a non-blockquote paragraph + bullet). It also modifies the existing bullet at line 17 (`🧠 Structure, not chunks.`) to `🧠 Structure first, optional vectors. Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.` This is the surgical fix: replace the misleading "No vectors. No chunking." tagline with one that names the new opt-in hybrid layer, while preserving the README header layout.

Counter-proposing would mean re-litigating the wording, which adds no value. R1's tagline matches the README's existing voice and acknowledges the hybrid layer honestly.

DECIDE: **ACCEPT R1's amendment verbatim**.
RATIONALE: Preserves blockquote markup; closes the line-5-vs-line-384 drift Finding 5 surfaced.
CONFIDENCE: HIGH

### AMEND AC19 — Narrow to extras-only opt-out

OPTIONS: A accept R1 verbatim | B counter-propose

ARGUE:
## Analysis
R1's amendment narrows AC19 to "documents OPT-OUT via not installing the `hybrid` extra"; does NOT introduce a runtime env var in cycle 34. This matches Q5 decision (extras-only) and avoids the verify-time fallback that risks a Step-9 DESIGN-AMEND.

DECIDE: **ACCEPT R1 verbatim**.
RATIONALE: Aligns with Q5 decision; avoids verify-time fallback to narrow form.
CONFIDENCE: HIGH

### AMEND AC22 — Forward regression only

OPTIONS: A accept R1 verbatim | B counter-propose

ARGUE:
## Analysis
R1 grep-confirmed `kb_save_synthesis` does NOT currently appear in `README.md`. The contract collapses from "Replace any reference" to "Verify the reference does NOT appear; if any future cycle re-introduces it, regression catches it." This is a forward regression — content-presence test that flips on revert (cycle-24 L4 pattern). No file edits required for AC22 alone.

DECIDE: **ACCEPT R1 verbatim**.
RATIONALE: Aligns with verified state; provides forward-regression protection via AC46-style test on README.md scope.
CONFIDENCE: HIGH

### AMEND AC25 — Line-number drift + scope expansion to comment at line 1198

OPTIONS: A accept merged amendment | B counter-propose

ARGUE:
## Analysis
R1 corrected line numbers (1261-1262, not 1230-1233). R2 added comment-at-line-1198 expansion. Combined, AC25 covers: (1) message rewrite at lines 1261-1262 to enumerate supported extensions per Q21 decision, (2) comment update at line 1198 per Q22 decision. The combined scope is a 3-5 line edit in `pipeline.py`.

DECIDE: **ACCEPT merged amendment** (R1 line-number correction + R2 comment-at-1198 + Q21 enumeration rewrite).
RATIONALE: Single coherent AC25 covering message + comment; both Step-9 edits live in one file.
CONFIDENCE: HIGH

### AMEND AC27 — Collapse to no-op

OPTIONS: A accept R1 verbatim | B counter-propose

ARGUE:
## Analysis
R1 verified CLAUDE.md ALREADY uses `save_as=` correctly at lines 46 and 308. AC27's original "Module Map + MCP Servers section" rename is a no-op; the AC46 regression test already provides forward-regression protection. AC27 collapses to a verify-only check that the existing correct text remains. No file edits required.

DECIDE: **ACCEPT R1 verbatim**.
RATIONALE: Existing state correct; AC46 regression already covers forward direction; collapses cleanly.
CONFIDENCE: HIGH

---

## Conditions

Each bullet here is a Step-7 plan test target (per cycle-22 L5).

1. **Boot-lean fix (NT1):** `kb.lint.augment` MUST convert its module-top imports of `kb.lint.fetcher` symbols to function-local imports (per cycle-23+ lazy-shim pattern). The cycle-31 boot-smoke test MUST be extended to verify `python -c "import kb.cli"` succeeds in a venv with ONLY default `dependencies` installed (no extras). [NEW AC49 below.]

2. **CI tooling install step (CI-5):** `.github/workflows/ci.yml` MUST include a dedicated `pip install build twine pip-audit` step BEFORE the AC14 + AC15 steps. Without this, AC14 + AC15 fail with `No module named build`. [NEW AC50 below.]

3. **Version-bump four-site sweep (NEW-Q11):** Step 9 MUST update version in (a) `pyproject.toml:3`, (b) `src/kb/__init__.py:3`, (c) `README.md:11` badge URL, (d) `CLAUDE.md` state line + Latest full-suite line, (e) `docs/architecture/architecture-diagram.html` + `architecture-diagram-detailed.html` AND re-render PNG via Playwright command per CLAUDE.md MANDATORY rule. [AC4 split into AC4a-AC4e.]

4. **AC25 dual scope:** Step 9 MUST update BOTH the rejection message at `pipeline.py:1261-1262` (enumerate supported extensions) AND the stale comment at `pipeline.py:1198`. Single AC, single file.

5. **`pip-audit -r requirements.txt` (NT6):** AC14 invocation MUST be `pip-audit -r requirements.txt --ignore-vuln=CVE-2025-69872 --ignore-vuln=GHSA-xqmj-j6mv-4862 --ignore-vuln=CVE-2026-3219 --ignore-vuln=CVE-2026-6587`. Audits the full pin set, not just the installed venv subset.

6. **Trigger scope narrowing (NT4):** `.github/workflows/ci.yml` `on:` block MUST be `{ push: { branches: [main] }, pull_request: {} }` — push runs only on main post-merge.

7. **Concurrency group (NT5):** Workflow MUST include `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }`.

8. **`permissions: read-all` block (T1):** Workflow top-level `permissions:` MUST be `read-all` (or equivalently `contents: read`). NOT `pull_request_target`. NO `secrets.*` references.

9. **Filesystem `rm` for untracked deletions (NEW-Q19):** Step 9 uses `rm` (or Bash `del`) for the six "deletions" — NOT `git rm`. T7 row 11 verification MUST be `test ! -f findings.md && test ! -f progress.md && test ! -f task_plan.md && test ! -f claude4.6.md && test ! -f docs/repo_review.md && test ! -f docs/repo_review.html` (replaces the degenerate `git ls-files` check).

10. **`claude4.6.md` deletion diff transparency (NEW-Q20):** PR description MUST include or link to a diff artifact (`docs/reviews/2026-04-25-claude4.6-deletion-diff.txt` or similar) showing what was deleted. If the diff reveals novel content, abort delete and surface as DESIGN-AMEND per cycle-17 L3.

11. **`pytest-httpx>=0.30` in `dev` extra (CI-1):** AC2's `dev` extra list MUST include `pytest-httpx>=0.30` to keep ~30 augment tests passing on CI.

12. **`pip check` `continue-on-error` directive at STEP level only:** Verify YAML indentation column matches the step's column, NOT the job's, so other steps don't silently pass.

13. **Architecture diagram PNG re-render via Playwright (NT3):** AC4e includes the re-render command (`1440x900 viewport, device_scale_factor=3, full_page=True, --type=png`); commit the regenerated PNG. Fallback: if Playwright re-render fails at Step 9, defer AC4e diagram bump to cycle 35 with BACKLOG entry rather than violating MANDATORY rule.

14. **Boot-smoke regression test:** Add to `tests/test_cycle34_release_hygiene.py` a test that verifies `kb.cli` importable from a minimal-deps state (default `dependencies` only). [NEW AC56 below.]

15. **`zh-CN.md` English-canonical note (Q8):** Add a 1-line header note to `README.zh-CN.md`: `> Note: English README is canonical. This Chinese mirror may lag by 1-2 cycles; see GitHub for current state.` [NEW AC23.5 below.]

---

## FINAL DECIDED DESIGN

ACs grouped by file (per `feedback_batch_by_file`). Numbering preserves AC1-AC48 from requirements doc; new ACs added at AC49+ for clarity.

### File: `pyproject.toml`

- **AC1** — `readme = "README.md"` (unchanged from requirements).
- **AC2** — `[project.optional-dependencies]` 5 extras with concrete pins per Q25:
  - `hybrid = ["model2vec>=0.5.0", "sqlite-vec>=0.1.0", "numpy>=1.26"]`
  - `augment = ["httpx>=0.27", "httpcore>=1.0", "trafilatura>=1.12"]`
  - `formats = ["nbformat>=5.0,<6.0"]`
  - `eval = ["ragas>=0.4", "litellm>=1.83", "datasets>=4.0"]`
  - `dev = ["pytest>=7.0", "ruff>=0.4.0", "pytest-httpx>=0.30"]` — EXTENDS existing.
- **AC3** — runtime `dependencies` MUST include: `click`, `python-frontmatter`, `fastmcp`, `networkx`, `anthropic`, `PyYAML`, `jsonschema`. Q1 decided KEEP `anthropic` required.
- **AC4a** — `pyproject.toml:3` version `"0.10.0"` → `"0.11.0"`.
- **AC4b** — `src/kb/__init__.py:3` `__version__ = "0.10.0"` → `"0.11.0"`.
- **AC4c** — `README.md:11` version badge `v0.10.0` → `v0.11.0`.
- **AC4d** — `CLAUDE.md:7` state line `v0.10.0` → `v0.11.0`; matches AC26 backfill.
- **AC4e** — `docs/architecture/architecture-diagram.html:501` + `architecture-diagram-detailed.html:398` `v0.10.0` → `v0.11.0`; re-render PNG via Playwright per CLAUDE.md MANDATORY rule; commit both HTML and PNG. Fallback to cycle 35 with BACKLOG entry if re-render breaks.

### File: `requirements.txt`

- **AC5** — header comment added; pins unchanged. Verify `jsonschema` is pinned (one-line addition if absent).

### File: `SECURITY.md` (NEW)

- **AC6** — narrow-role CVE acceptance table (4 rows: diskcache, litellm, pip, ragas) with verification grep per row + UNBLOCK condition for litellm.
- **AC7** — disclosure path: GitHub Security Advisory + email fallback to project owner.
- **AC8** — re-check cadence text matches requirements-doc wording verbatim.

### File: `.github/workflows/ci.yml` (NEW)

- **AC9** — workflow exists; `on: { push: { branches: [main] }, pull_request: {} }` (per NEW-Q16); top-level `permissions: read-all` block (per NEW-Q18); `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` (per NEW-Q23); NO `secrets.*` references; NO `pull_request_target`; tag-pin `actions/checkout@v4` + `actions/setup-python@v5`.
- **AC10** — `test` job ruff check on `src/` and `tests/`.
- **AC11** — `pytest --collect-only -q`.
- **AC12** — `pytest -q`.
- **AC13** — `pip check` with `continue-on-error: true` at STEP level only (per Q9).
- **AC14** — `pip-audit -r requirements.txt --ignore-vuln=CVE-2025-69872 --ignore-vuln=GHSA-xqmj-j6mv-4862 --ignore-vuln=CVE-2026-3219 --ignore-vuln=CVE-2026-6587` (per NEW-Q17).
- **AC15** — `python -m build && python -m twine check dist/*`. Requires AC50 install step.
- **AC16** — Python 3.12 only, `ubuntu-latest` single platform.
- **AC50 (NEW)** — dedicated `pip install build twine pip-audit` step BEFORE AC14 + AC15 (per NEW-Q13).

### File: `.gitignore`

- **AC17** — patterns added: `findings.md`, `progress.md`, `task_plan.md`, `cycle-*-scratch/`. (Note: per R2 verification, several of these may already exist; AC43 asserts presence not "added in this cycle".) `claude4.6.md` is INTENTIONALLY excluded (one-shot delete, not recurring).

### File: `README.md`

- **AC18** — replace line 5 wholesale, preserving `> ` blockquote markup: `> **Compile, don't retrieve.** Drop a source in. Claude does the rest — extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. Markdown-first; optional hybrid retrieval. Pure markdown you own, browsable in Obsidian.` ALSO modify line 17 bullet to `- 🧠 **Structure first, optional vectors.** Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.`
- **AC19** — "Optional hybrid search" section under Quick Start documents extras-only opt-out (`pip install -e .[hybrid]`); explicitly NO runtime env var in cycle 34.
- **AC20** — PDF row removed from supported-formats table; replaced with sentence below table about markitdown/docling conversion.
- **AC21** — tests badge replaced with generic `tests-passing-brightgreen` (Q6).
- **AC22** — verify `kb_save_synthesis` does NOT appear in README.md (forward regression only per R1 amendment).
- **AC23** — Quick Start adds extras-aware install path; documents minimal install separately.
- **AC23.5 (NEW)** — `README.zh-CN.md` gets 1-line "English canonical, may lag" header note (per Q8).

### File: `src/kb/config.py`

- **AC24** — `.pdf` removed from `SUPPORTED_SOURCE_EXTENSIONS`.

### File: `src/kb/ingest/pipeline.py`

- **AC25** — TWO edits: (1) message rewrite at lines 1261-1262 to enumerate supported extensions: `f"Binary file cannot be ingested: {source_path.name}. Only text source types ({', '.join(sorted(SUPPORTED_SOURCE_EXTENSIONS))}) are supported. Convert with markitdown or docling first."`; (2) update stale comment at line 1198 (drop "(includes .pdf)" reference).

### File: `src/kb/lint/augment.py`

- **AC49 (NEW)** — convert module-top imports of `kb.lint.fetcher` symbols to function-local imports (per NEW-Q14 boot-lean fix). Behaviour unchanged for `[augment]`-installed users; minimal install no longer ImportErrors at `import kb.cli`.

### File: `CLAUDE.md`

- **AC26** — test-count + file-count updated post-merge (cycle-15 L4 backfill); ALSO add new "Latest cycle (34)" bullet ABOVE cycle 33 bullet (per R2 doc-drift sweep).
- **AC27** — verify CLAUDE.md uses `save_as=` correctly (already does at lines 46, 308); collapses to no-op verify per R1 amendment.
- **AC28** — Quick Reference adds "Release artifacts" line pointing at `SECURITY.md` + `.github/workflows/ci.yml`.

### File deletions (4 scratch + 2 superseded review)

- **AC29** — delete `findings.md` (filesystem `rm`, per NEW-Q19).
- **AC30** — delete `progress.md`.
- **AC31** — delete `task_plan.md`.
- **AC32** — delete `claude4.6.md`; PR description includes diff artifact reference per NEW-Q20.
- **AC33** — delete `docs/repo_review.md`.
- **AC34** — delete `docs/repo_review.html`.

### File additions (commit comprehensive review)

- **AC35** — commit `docs/reviews/2026-04-25-comprehensive-repo-review.md`.
- **AC36** — commit `docs/reviews/2026-04-25-comprehensive-repo-review.html`.

### File: `tests/test_cycle34_release_hygiene.py` (NEW)

- **AC37** — `test_pyproject_readme_is_readme_md`.
- **AC38** — `test_pyproject_has_required_extras` (asserts AC2 5 keys present + non-empty pin lists).
- **AC39** — `test_pyproject_runtime_deps_include_jsonschema`.
- **AC40** — `test_no_vectors_tagline_absent` — literal `"No vectors. No chunking."` NOT in README.md.
- **AC41** — `test_pdf_not_in_supported_extensions`.
- **AC42** — `test_scratch_files_absent` (4 files: findings, progress, task_plan, claude4.6).
- **AC43** — `test_gitignore_lists_scratch_patterns` (asserts presence, not "added this cycle").
- **AC44** — `test_security_md_has_required_sections` (regex-tolerant header match per R2).
- **AC45** — `test_ci_workflow_yaml_parses` (asserts `on: { push: ..., pull_request: ...}`, `permissions:`, `concurrency:`, all step IDs).
- **AC46** — `test_kb_save_synthesis_clarification_in_claude_md` (positive: `save_as=` IS present).
- **AC47** — `test_old_repo_review_files_deleted`.
- **AC48** — `test_comprehensive_review_present` (uses prefix-match + substring per R2 robustness).
- **AC51 (NEW)** — `test_kb_save_synthesis_absent_from_readme` (forward regression for AC22).
- **AC52 (NEW)** — `test_pyproject_version_is_0_11_0` (AC4a regression).
- **AC53 (NEW)** — `test_kb_init_version_matches_pyproject` (AC4b lockstep regression).
- **AC54 (NEW)** — `test_readme_version_badge_is_v0_11_0` (AC4c regression).
- **AC55 (NEW)** — `test_architecture_diagram_html_version_is_0_11_0` (AC4e regression; PNG presence check optional).
- **AC56 (NEW)** — `test_boot_lean_minimal_install` — runs `python -c "import kb.cli"` in a subprocess venv with ONLY default dependencies installed; asserts exit 0 (NEW-Q14 boot-lean regression).
- **AC57 (NEW)** — `test_pip_audit_invocation_uses_dash_r` — parses `.github/workflows/ci.yml`, asserts the `pip-audit` step's `run:` uses `-r requirements.txt` (NEW-Q17 regression).

**Final AC count: 57** (AC1-AC57, with AC4 split into AC4a-AC4e and AC23.5 inserted; original 48 preserved + 9 new ACs at AC49-AC57).

**File group count: 18** (was 17; +1 for `src/kb/lint/augment.py` boot-lean fix).

---

## Same-class peer enumeration (cycle-20 L3)

### AC18 README copy change — every README.md location to touch

Per cycle-20 L3 ("same-class peer enumeration before merge"), every README.md location that mentions vectors/chunking/PDF/test-count/version must be reviewed:

| Line | Current text (verified) | Action |
|---|---|---|
| 5 | `> **Compile, don't retrieve.** ... No vectors. No chunking. Pure markdown ...` | REPLACE wholesale per AC18 (preserve `>` blockquote). |
| 9 | `[![Tests](.../tests-2850-brightgreen)](#development)` | REPLACE with `tests-passing-brightgreen` per AC21. |
| 11 | `[![Version](.../version-v0.10.0-orange)](CHANGELOG.md)` | UPDATE to `v0.11.0` per AC4c. |
| 17 | `🧠 **Structure, not chunks.** Entities, concepts, wikilinks ...` | REPLACE with `🧠 **Structure first, optional vectors.** ...` per AC18 second clause. |
| 142 (PDF row in Supported File Formats table) | `\| PDF \| .pdf \| Supported by the compile pipeline; for direct MCP ingest, convert to Markdown first \|` | REMOVE row; ADD sentence below table per AC20. |
| 339 / 352 / 384-385 (narrative phase summaries citing historical 1033 / 1177 / 2725 / 2716 counts) | NOT in scope — historical phase counts; NOT updated per Q21 (AC21 only touches the badge). |
| 384 (`Phase 4 — hybrid search with RRF fusion`) | Already aligned with AC18's new tagline; NO action needed (the line-5 vs line-384 drift is closed BY the AC18 line-5 update). |

### NEW-Q11 version bump — every site

| Site | Current | Target | AC |
|---|---|---|---|
| `pyproject.toml:3` | `version = "0.10.0"` | `"0.11.0"` | AC4a |
| `src/kb/__init__.py:3` | `__version__ = "0.10.0"` | `"0.11.0"` | AC4b |
| `README.md:11` | `version-v0.10.0-orange` | `version-v0.11.0-orange` | AC4c |
| `CLAUDE.md:7` | `v0.10.0 · 2923 tests` | `v0.11.0 · {N}` (post-merge backfill) | AC4d (composes with AC26) |
| `docs/architecture/architecture-diagram.html:501` | `v0.10.0` | `v0.11.0` | AC4e (HTML edit) |
| `docs/architecture/architecture-diagram-detailed.html:398` | `v0.10.0` | `v0.11.0` | AC4e (HTML edit) |
| `docs/architecture/architecture-diagram.png` | (rendered from pre-cycle HTML) | re-rendered post-AC4e HTML edit | AC4e (Playwright re-render) |
| `README.zh-CN.md:5` | `v0.10.0` badge | DEFERRED per Q8 (AC23.5 adds canonical-note instead) | AC23.5 (note only; badge sync deferred) |
| `CHANGELOG.md` `[Unreleased]` | (no version stamp) | KEEP `[Unreleased]` until tag cut (per cycle-N convention) | n/a |

---

## Step-11 verification delta

The threat-model's 25-row checklist is preserved as-is. The following rows are ADDED or AMENDED for cycle-34 final design:

### AMENDED rows

| # | Original | Amendment |
|---:|---|---|
| 11 (T7) | `git ls-files findings.md ... returns empty` | REPLACE with `test ! -f findings.md && test ! -f progress.md && test ! -f task_plan.md && test ! -f claude4.6.md && test ! -f docs/repo_review.md && test ! -f docs/repo_review.html` (per NEW-Q19; the original is degenerate). |
| 22 (AC10-15) | `pip-audit ... --ignore-vuln=...` (no `-r`) | UPDATE to assert `pip-audit -r requirements.txt --ignore-vuln=...` (per NEW-Q17). |

### NEW rows (added beyond the original 25)

| # | Threat / AC | Check |
|---:|---|---|
| 26 | NT1 / AC49 / AC56 | Subprocess venv with ONLY default deps installed runs `python -c "import kb.cli"` with exit 0. |
| 27 | NT4 / AC9 | `.github/workflows/ci.yml` `on:` block has `push: { branches: [main] }, pull_request: {}` (NOT bare `[push, pull_request]`). |
| 28 | NT3 / AC4e | `docs/architecture/architecture-diagram.html` and `architecture-diagram-detailed.html` reference `v0.11.0`; the rendered PNG is committed and Git-tracked. |
| 29 | NT5 / AC9 | Workflow contains `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }`. |
| 30 | NT6 / AC14 | `pip-audit` step uses `-r requirements.txt` (full-pin-set audit, not installed-env subset). |
| 31 | CI-5 / AC50 | Workflow contains a step `pip install build twine pip-audit` BEFORE the AC14 + AC15 steps. |
| 32 | NEW-Q18 / AC9 | Workflow top-level `permissions:` block exists and equals `read-all` (or `contents: read`); no `write` scopes. |
| 33 | CI-1 / AC2 | `pytest-httpx>=0.30` is present in the `dev` extra list. |
| 34 | NEW-Q11 / AC4b | `src/kb/__init__.py` `__version__` matches `pyproject.toml` version. |
| 35 | AC25 expansion / NEW-Q22 | Comment at `pipeline.py:1198` no longer contains the literal `"includes .pdf"`. |
| 36 | NEW-Q20 / AC32 | PR description references a `claude4.6-deletion-diff` artifact (or includes the diff inline). |

**Total checklist rows after cycle-34 final design: 25 (preserved) + 11 NEW = 36 rows. 2 rows AMENDED.**

---

End of cycle-34 Step-5 design decision gate.
