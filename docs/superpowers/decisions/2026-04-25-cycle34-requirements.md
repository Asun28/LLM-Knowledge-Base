# Cycle 34 — Release Hygiene · Requirements + Acceptance Criteria

**Date:** 2026-04-25 · **Cycle:** 34 · **Theme:** Release hygiene (packaging + CI bootstrap + docs drift + scratch cleanup)
**Driver:** comprehensive repository review at `docs/reviews/2026-04-25-comprehensive-repo-review.md` (P0 ship-blockers 1, 2, 3, 5, 6, 7 + P1 #9 + P2 #20)
**Predecessor:** cycle 33 closed Finding #4 (MCP partial-write path leak) — merged in PR #47.
**Five-cycle plan context:** cycle 34 is the LOW-RISK, ~12-file, packaging+docs+CI bootstrap subset. Cycles 35-38 cover pre-ingest secret gate (35), test infrastructure (36), ingest recovery + config split (37), PRD + test consolidation (38).

---

## 1. Problem

The cycle-32 audit and the 2026-04-25 comprehensive repository review surfaced 8 P0 ship-blockers. Cycle 33 closed one (MCP partial-write path leak). The remaining seven plus two follow-up items are all in the "release hygiene" class — packaging metadata, CI absence, doc/code contradictions, scratch leftovers — none of which require deep architectural change but every one of which blocks confident release. Concretely:

1. `pyproject.toml:6` declares `readme = "CLAUDE.md"` (agent instructions, not user onboarding) and lists only 6 runtime deps despite `src/kb/` importing `jsonschema`, `httpx`, `trafilatura`, `nbformat`, `model2vec`, `sqlite_vec`. A clean `pip install .` from metadata breaks advertised features.
2. Three `pip check` resolver conflicts (`arxiv` ↔ `requests`, `crawl4ai` ↔ `lxml`, `instructor` ↔ `rich`) and four open `pip-audit` advisories (`diskcache`, `litellm`, `pip`, `ragas`) with no automated security gate.
3. No `.github/workflows/` directory at all — every quality gate is local + agent-run.
4. `README.md:5` says "No vectors. No chunking." while `README.md:384` and `src/kb/query/hybrid.py` ship hybrid BM25 + vector search via `model2vec` + `sqlite-vec`. Same drift on PDF support (`README.md:142` claims it; `src/kb/ingest/pipeline.py:1233` rejects binary PDFs).
5. `README.md:9` test badge says `tests-2850`; live `pytest --collect-only` shows 2923 (cycle 33 added +21).
6. Four scratch files persist in repo root (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`) — none gitignored, all visible on first checkout.
7. `kb_save_synthesis` is documented as a tool in some places but is actually `kb_query(save_as=...)` — a query call that also writes.

The longer this sits, the more credibility damage it does. None of it requires changing the core compile-not-retrieve thesis or the architecture. It requires **discipline applied to surfaces**.

## 2. Non-goals

- **Not** the pre-ingest secret/PII gate (Finding 8 → cycle 35 dedicated security cycle).
- **Not** the ingest receipt/recovery refactor (Finding 10 → cycle 37).
- **Not** golden/snapshot tests for rendered output (Finding 14 → cycle 36).
- **Not** the `config.py` god-module split (Finding 13 → cycle 37).
- **Not** async MCP tools (Finding 11 → cycle 35 or later).
- **Not** the formal PRD `docs/prd/v0.10.md` (Finding 15 → cycle 38).
- **Not** the `docs/superpowers/decisions/` subdivision (Finding 18 → cycle 36/38).
- **Not** moving existing `requirements.txt` pins around extras directories — `requirements.txt` stays as the all-deps superset for now; `pyproject.toml` extras are the new declarative layer beside it. Splitting the requirement file structure is a cycle-36 follow-up.
- **Not** real PDF text extraction — the chosen route is "remove `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` and document the convert-with-markitdown-first workflow." Implementing a real extractor is a cycle-N+1 follow-up if a user actually requests it.
- **Not** translating the cycle 34 README copy changes into `README.zh-CN.md` — the Chinese mirror lags by design (sync cadence is "every 2-3 cycles, in batch"). A separate cycle handles the bulk re-sync.

## 3. Acceptance Criteria

ACs grouped by file (per `feedback_batch_by_file`). Each is testable as pass/fail. **Bold** items are the AC's primary contract; the indented bullets are CONDITIONS that must hold (per cycle-22 L5 "design-gate CONDITIONS are load-bearing test coverage").

### File: `pyproject.toml`

- **AC1 — `readme = "README.md"`**
  - Verify: `python -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['readme'] == 'README.md'"` succeeds.
  - Regression test: pytest fixture-free check on the parsed TOML.
- **AC2 — `[project.optional-dependencies]` extras declared**
  - Required keys: `hybrid` (model2vec, sqlite_vec), `augment` (httpx, trafilatura), `formats` (nbformat), `eval` (ragas, litellm), `dev` (pytest, ruff). Existing `dev` extra extended.
  - Verify: parsed TOML has all five keys; each value is a non-empty list of pin strings.
- **AC3 — runtime deps cover the boot-lean import surface**
  - `pip install . --no-deps` followed by installation of only the listed `dependencies` MUST allow `kb --version` to run without `ImportError`. (Test runs in subprocess inside a clean venv via the CI workflow; locally pinned via subprocess probe.)
  - Required runtime: keep `click`, `python-frontmatter`, `fastmcp`, `networkx`, `anthropic`, `PyYAML` AND add `jsonschema` (cycle-21 cli_backend dependency). Decision Q1 (anthropic optional vs required) deferred to Step 5 design gate.
- **AC4 — version bump to 0.11.0**
  - `version = "0.11.0"` reflecting the release-hygiene minor bump (extras + CI + readme changes are user-visible).

### File: `requirements.txt`

- **AC5 — unchanged structure, header comment added**
  - Add a `# requirements.txt — full-dev superset; for runtime-only see [project.optional-dependencies]` header so a clone-and-pip-install user knows the file is the maximalist install path.
  - Pins NOT migrated to extras in this cycle (cycle-36 follow-up).

### File: `SECURITY.md` (NEW)

- **AC6 — narrow-role CVE acceptance table**
  - One row per open advisory: `diskcache 5.6.3` (CVE-2025-69872, no fix, narrow=robots.txt cache), `litellm 1.83.0` (GHSA-xqmj-j6mv-4862, fix=1.83.7 blocked by click<8.2 transitive, narrow=dev-eval ragas harness), `pip 26.0.1` (CVE-2026-3219, no fix, narrow=tooling), `ragas 0.4.3` (CVE-2026-6587, no fix, narrow=dev-eval).
  - Each row cites the verification grep that confirms the package is not used by `src/kb/` runtime.
- **AC7 — disclosure path documented**
  - "Report security issues via GitHub Security Advisory" + email to project owner.
- **AC8 — re-check cadence**
  - "Every cycle's Step 2 baseline + Step 11 PR-CVE diff + Step 15 late-arrival warn" — re-confirms the feature-dev workflow already does this; SECURITY.md just makes it discoverable.

### File: `.github/workflows/ci.yml` (NEW)

- **AC9 — workflow exists and triggers on push + pull_request**
  - Verify: `yaml.safe_load` parses the file; `on:` includes `[push, pull_request]`; `jobs:` has at least the `test` job.
- **AC10 — `test` job runs ruff check on `src/` and `tests/`**
- **AC11 — `test` job runs `pytest --collect-only -q`** (tests are discoverable)
- **AC12 — `test` job runs full `pytest -q`** (all tests pass)
- **AC13 — `test` job runs `pip check`** (resolver conflicts surface)
  - CONDITION: this WILL fail on `main` today because of the three known conflicts (`arxiv`, `crawl4ai`, `instructor`). The cycle 34 fix is to allow `pip check` to fail-but-warn (`continue-on-error: true`) and file the resolver conflicts as cycle-N+1 follow-up. Strict-fail comes when the conflicts are closed.
- **AC14 — `test` job runs `pip-audit` with documented `--ignore-vuln` for the four narrow-role advisories**
  - `--ignore-vuln=CVE-2025-69872 --ignore-vuln=GHSA-xqmj-j6mv-4862 --ignore-vuln=CVE-2026-3219 --ignore-vuln=CVE-2026-6587`. These are the SECURITY.md-documented exceptions. Any NEW advisory becomes a CI failure.
  - Decision Q4 (use --ignore-vuln vs report-only) deferred to Step 5; default to --ignore-vuln so the green checkmark means "no new CVE since cycle 34", not "tests pass and we ignore everything."
- **AC15 — `test` job runs `python -m build && python -m twine check dist/*`**
  - Catches malformed `pyproject.toml` + the wrong-readme bug we're fixing.
- **AC16 — Python 3.12 only, ubuntu-latest single platform for now**
  - Windows/extras matrix deferred to cycle 36 per the review's recommendation.

### File: `.gitignore`

- **AC17 — scratch patterns added**
  - `findings.md`, `progress.md`, `task_plan.md`, `cycle-*-scratch/` (forward-looking pattern).
  - `claude4.6.md` does NOT go in `.gitignore` — we DELETE it instead (one-shot legacy file, not a recurring scratch type).

### File: `README.md`

- **AC18 — "No vectors. No chunking." line replaced**
  - New tagline: `> **Compile, don't retrieve.** Drop a source in. Claude does the rest — extract entities, build wiki pages, inject wikilinks, track trust, flag contradictions. Markdown-first; optional hybrid retrieval. Pure markdown you own, browsable in Obsidian.`
  - Bullet near the top: `- 🧠 Structure first, optional vectors. Entities, concepts, wikilinks form a real graph; hybrid BM25 + vector search is opt-in for recall.`
- **AC19 — "Optional hybrid search" section added under Quick Start**
  - Documents how the hybrid layer is opt-in: requires `pip install -e .[hybrid]`; vector DB lives at `.data/vectors.db`; disable via `KB_DISABLE_VECTORS=1` (env-var honoured by `kb.query.hybrid` — verify it exists; if not, this AC narrows to "documents the OPT-OUT via not installing the `hybrid` extra").
  - Decision Q5: should we ship a runtime `KB_DISABLE_VECTORS` flag or rely on extras-not-installed? Step 5 design gate decides.
- **AC20 — PDF row removed from "Supported File Formats" table OR clarified**
  - Recommended phrasing: replace the row with a sentence under the table: `> PDF files: convert with markitdown or docling first, then place the .md output in raw/papers/. Direct .pdf ingest is not supported.`
- **AC21 — tests badge static-string updated to current OR replaced with generic**
  - Default: `[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#development)` (drops the count number entirely).
  - Decision Q6 (static count vs generic vs dynamic shield) → Step 5 design gate.
- **AC22 — kb_save_synthesis clarified**
  - Replace any "kb_save_synthesis" reference with the accurate "`kb_query(save_as=<slug>)`". Add a note that it is a query-mode write.
- **AC23 — Quick Start install instruction adds extras-aware path**
  - Existing line: `pip install -r requirements.txt && pip install -e .` stays for the dev workflow.
  - New section: "Minimal install (no hybrid, no augment, no eval extras)": `pip install -e .` and document that hybrid/augment/eval require the matching extra.

### File: `src/kb/config.py`

- **AC24 — `.pdf` removed from `SUPPORTED_SOURCE_EXTENSIONS`**
  - Verify: `from kb.config import SUPPORTED_SOURCE_EXTENSIONS; assert ".pdf" not in SUPPORTED_SOURCE_EXTENSIONS`.

### File: `src/kb/ingest/pipeline.py`

- **AC25 — binary-decode error message updated**
  - Update the `"Binary file cannot be ingested"` rejection to NOT name PDF specifically (since PDF is no longer in the supported list, suggest converting non-text source via markitdown/docling). Verify the message string matches the regression test exactly.
  - Existing test at `tests/test_v0916_task03.py:43` covers binary rejection; verify it still passes (the test asserts the rejection happens, not the exact message).

### File: `CLAUDE.md`

- **AC26 — test-count and file-count updated post-merge**
  - After cycle 34 lands, update `CLAUDE.md:7` and `:45` and `:189` from 2923 → cycle-34-final-count. Backfill via `pytest --collect-only -q | tail -1` after the doc-sync commit (cycle-15 L4).
- **AC27 — kb_save_synthesis clarified in Module Map + MCP Servers section**
  - Same wording change as AC22 (note: it's `kb_query(save_as=...)`, not a separate MCP tool).
- **AC28 — Quick Reference adds a "Release artifacts" line**
  - One line pointing at `SECURITY.md` and `.github/workflows/ci.yml` so future cycles know they exist.

### File deletions (4 scratch files + 1 superseded review)

- **AC29 — delete `findings.md`** (cycle-29 scratch, in repo root)
- **AC30 — delete `progress.md`** (cycle-29 scratch)
- **AC31 — delete `task_plan.md`** (cycle-29 scratch with stale `[in_progress]` marker)
- **AC32 — delete `claude4.6.md`** (legacy pre-Opus-4.7 copy of CLAUDE.md, 40 KB drift hazard)
- **AC33 — delete `docs/repo_review.md`** + **AC34 — delete `docs/repo_review.html`**
  - Per the review's own header note: "Prior draft at `docs/repo_review.md` is superseded by this review."

### File additions (commit the comprehensive review)

- **AC35 — commit `docs/reviews/2026-04-25-comprehensive-repo-review.md`** (currently untracked, 54 KB)
- **AC36 — commit `docs/reviews/2026-04-25-comprehensive-repo-review.html`** (currently untracked, 70 KB)

### File: `tests/test_cycle34_release_hygiene.py` (NEW)

- **AC37 — `test_pyproject_readme_is_readme_md`** — parses TOML, asserts AC1.
- **AC38 — `test_pyproject_has_required_extras`** — parses TOML, asserts AC2 keys present.
- **AC39 — `test_pyproject_runtime_deps_include_jsonschema`** — asserts AC3.
- **AC40 — `test_no_vectors_tagline_absent`** — `Path("README.md").read_text(encoding="utf-8")` does NOT contain literal `"No vectors. No chunking."` (regression for AC18; this is a content-presence assertion that flips on revert per cycle-24 L4).
- **AC41 — `test_pdf_not_in_supported_extensions`** — imports `kb.config`, asserts `.pdf` not in `SUPPORTED_SOURCE_EXTENSIONS` (regression for AC24).
- **AC42 — `test_scratch_files_absent`** — asserts `findings.md`/`progress.md`/`task_plan.md`/`claude4.6.md` do NOT exist at repo root (regressions for AC29-AC32).
- **AC43 — `test_gitignore_lists_scratch_patterns`** — reads `.gitignore`, asserts the cycle-34 patterns present (regression for AC17).
- **AC44 — `test_security_md_has_required_sections`** — asserts `SECURITY.md` exists with at least `## Vulnerability Reporting` + `## Known Advisories` + `## Re-check Cadence` headers.
- **AC45 — `test_ci_workflow_yaml_parses`** — asserts `.github/workflows/ci.yml` exists, parses as YAML, has `on: [push, pull_request]` and a `test` job with the steps from AC10-AC15.
- **AC46 — `test_kb_save_synthesis_clarification_in_claude_md`** — asserts CLAUDE.md text near "Quality (Phase 2)" or the MCP section mentions "`kb_query(save_as=...)`" or has the clarifying note (regression for AC27).
- **AC47 — `test_old_repo_review_files_deleted`** — asserts `docs/repo_review.md` and `docs/repo_review.html` do NOT exist (regression for AC33-AC34).
- **AC48 — `test_comprehensive_review_present`** — asserts `docs/reviews/2026-04-25-comprehensive-repo-review.md` exists and starts with `# LLM Wiki Flywheel — Comprehensive Repository Review` (regression for AC35).

**AC count: 48** across **17 file groups** (4 modifies + 4 deletes + 5 creates/news + 4 file collections). Per memory `feedback_batch_by_file`, target 30-40 items / 15-20 files. Cycle 34 is at the upper edge; this is appropriate because most ACs are 1-3-line changes (`Edit` operations), and the test file is parameter-driven.

## 4. Blast radius

- **`src/kb/`:** narrow — `config.py` line removal + `ingest/pipeline.py` message tweak. No semantic change. Existing tests unaffected (the binary-rejection test asserts behaviour, not message text).
- **Packaging:** `pyproject.toml` + `requirements.txt` header. Extras declaration is purely additive.
- **CI:** new file. Does not affect any existing local workflow.
- **Docs:** `README.md` + `CLAUDE.md` + new `SECURITY.md`. Public surface, but every change is correctness-improving (no API change).
- **Repo root:** 4 file deletions + 2 in `docs/` deletions + 2 in `docs/reviews/` additions.
- **Tests:** one new file (`test_cycle34_release_hygiene.py`) with 12 fixture-free tests. No existing test is touched.

## 5. Risk register

| Risk | Mitigation |
|---|---|
| `pip check` fails the new CI gate (3 known conflicts) | AC13 uses `continue-on-error: true` for `pip check` step; conflicts file as cycle-N+1 follow-up. |
| `pip-audit --strict` would block CI on the 4 narrow-role CVEs | AC14 uses `--ignore-vuln` for each documented narrow-role advisory; SECURITY.md is the audit trail. |
| Removing `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` may break a user's compile pass | The current code path REJECTS binary PDFs anyway with a helpful message; removing the extension produces a clearer "unsupported extension" error sooner. Net change: better error path, no regressed feature. |
| Deleting `claude4.6.md` may delete unique content | Diff against `CLAUDE.md` first; per the review header it's a legacy copy. If diff shows novel content, abort the delete and surface as a `DESIGN-AMEND` per cycle-17 L3. |
| Tests-badge change ("tests-passing" loses the count) | Q6 design-gate decision; if the project values the count, switch to a dynamic shields.io endpoint (cycle-N+1 CI hook). |
| Renaming `version = "0.10.0"` → `0.11.0` may surprise downstream | Single-developer project; no downstream consumers exist yet. CHANGELOG entry documents the semver rationale. |

## 6. Open design questions for Step 5 decision gate

| # | Question | Default | Why surface it |
|---|----------|---------|---------------|
| Q1 | Keep `anthropic` in required `dependencies` or move to `[default-llm]` extra? | KEEP REQUIRED | Removing it would break the default install path users expect. README clarifies it's optional only when running through Claude Code MCP. |
| Q2 | PDF — option (a) remove from `SUPPORTED_SOURCE_EXTENSIONS` or option (b) implement extractor? | OPTION (A) | Review explicitly recommends (a); (b) is 1+ cycle and not in this cycle's scope. |
| Q3 | Keep `crawl4ai` and `playwright` in default `requirements.txt`? | YES | Used by augment + the demo workflow. Splitting requirements.txt into per-extra files is cycle-36. |
| Q4 | `pip-audit` strict vs `--ignore-vuln` documented narrow-role CVEs? | --ignore-vuln | Strict would fail CI today; ignore makes the green check meaningful (zero NEW CVEs). |
| Q5 | Runtime `KB_DISABLE_VECTORS=1` flag or extras-only opt-out? | EXTRAS-ONLY for cycle 34 | Adding a runtime flag is cycle-N+1 if needed; extras-only is the simplest documented path now. |
| Q6 | Tests badge: static count, "tests-passing" generic, or dynamic shield? | GENERIC ("tests-passing") | Static count drifts (Finding 6); dynamic shield needs CI hook (cycle-N+1); generic is the lowest-maintenance correct answer. |
| Q7 | Translate cycle-34 changes to `README.zh-CN.md` this cycle? | NO | Chinese mirror lags by design; sync as a separate batched cycle. |
| Q8 | Version bump 0.10.0 → 0.11.0 vs hold at 0.10.x patch? | 0.11.0 minor bump | New extras + CI workflow + SECURITY.md are user-visible additions; semver minor is correct. |
| Q9 | Add Windows + extras-matrix to CI now or defer? | DEFER (cycle 36) | Single Linux + Python 3.12 lane is the minimum credible CI; matrix is expansion territory. |
| Q10 | `requirements.txt` split into runtime/dev/eval files now or defer? | DEFER (cycle 36) | Risky to reshuffle pins concurrently with extras declaration; do extras first, then split files in a follow-up cycle. |

10 open questions — per cycle-17 L4, this hits the trigger threshold for a Step-14 R3 review even though AC count (48) already triggers R3 via the >25-AC rule from `feedback_3_round_pr_review`.

## 7. Definition of done

- [ ] All 48 ACs have a passing test or a verified file-state assertion.
- [ ] CI workflow at `.github/workflows/ci.yml` runs and reports green on the feature branch.
- [ ] `pip-audit` reports zero NEW advisories vs the Step-2 baseline.
- [ ] All cycle-34 commits land on a single feature branch `feat/backlog-by-file-cycle34`.
- [ ] Step 12 doc update touches `CHANGELOG.md` (compact entry), `CHANGELOG-history.md` (full per-cycle detail), `BACKLOG.md` (delete resolved items: Findings 1, 2, 3, 5, 6, 7, 9, 20 from the comprehensive review), `CLAUDE.md` (test count + kb_save_synthesis clarification + release-artifacts line).
- [ ] Step 16 self-review scorecard committed at `docs/superpowers/decisions/2026-04-25-cycle34-self-review.md`.
- [ ] Skill patches landed in `references/cycle-lessons.md` + index entry in `SKILL.md`.

---

End of cycle-34 requirements.
