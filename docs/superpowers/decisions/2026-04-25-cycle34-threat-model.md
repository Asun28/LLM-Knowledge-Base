# Cycle 34 — Release Hygiene · Threat Model

**Date:** 2026-04-25 · **Cycle:** 34 · **Theme:** Release hygiene
**Source:** Step-7 threat model for the 48-AC release-hygiene cycle. Becomes Step-11's verification checklist.
**Predecessor docs:** `docs/superpowers/decisions/2026-04-25-cycle34-requirements.md` (problem + ACs); `docs/reviews/2026-04-25-comprehensive-repo-review.md` § 1, 6, 7, 14 (findings + CI/CD review + security review + fix plan).

---

## Analysis

Cycle 34 is overwhelmingly an **internal-hygiene** cycle: the bulk of its 48 ACs are docs (README, CLAUDE.md, SECURITY.md), packaging metadata (pyproject.toml extras, version bump, requirements.txt header), scratch deletions (4 root files + 2 superseded review artifacts), and a one-line `config.py` removal of `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS`. None of those touch a runtime trust boundary. Moving the readme pointer from `CLAUDE.md` to `README.md` does not change what a `pip install .` installs (the wheel still bundles `src/kb/`); it only changes which file PyPI renders as the project description. Removing `.pdf` from the supported list is a *narrowing* of accepted input — a defence-in-depth tightening, not an expansion. Deleting `findings.md`/`progress.md`/`task_plan.md`/`claude4.6.md` removes information that was already on `main` and already public on the GitHub repo; the deletion does not retroactively scrub git history but the cycle does not rely on that property. The `kb_save_synthesis` clarification is a doc rename (the implementation has always been `kb_query(save_as=...)` since cycle 16). All of these are zero-attack-surface changes for an external attacker.

The genuinely **trust-boundary-introducing** changes are three: (1) **the new `.github/workflows/ci.yml` workflow**, which creates a new automated execution environment that runs untrusted PR code on Anthropic-paid GitHub-hosted runners; (2) **`pyproject.toml`'s newly-declared `[project.optional-dependencies]` extras**, which redefine what packages enter a downstream user's environment when they run `pip install kb-wiki[hybrid]` (versus the cycle-33 status quo of "pip install + everything from requirements.txt"); and (3) **the new `SECURITY.md` file**, which is a public artifact that documents the four narrow-role accepted CVEs — turning private internal knowledge ("we know about these and they're benign") into a public claim that an attacker can read. The CI workflow is by far the most material new boundary because it executes code with a `GITHUB_TOKEN` and is triggered automatically on every push and pull_request — including from forks. The packaging change is moderate: extras lists are append-only and do not introduce new dependencies the project did not already pin. The SECURITY.md disclosure is mild: every CVE listed is already public on NVD/GHSA, so there is no information-leak amplification, but the file does function as an "accepted-risk allow-list" that needs a re-check cadence to avoid going stale. The threats below address each of these three boundaries plus the tail of secondary risks (action SHA pinning, log redaction, fork-PR escalation, gitignore-vs-git-rm semantics, deletion irrecoverability).

---

## Trust boundaries

### TB1 — GitHub Actions workflow runner (`.github/workflows/ci.yml`)

- **Principal:** GitHub-hosted ubuntu-latest runner, ephemeral VM, executes as user `runner`.
- **Authorisation:** `GITHUB_TOKEN` minted per-job; default permissions for new workflows since 2023 GitHub default are `contents: read` only on PRs from forks (fork-PR tokens are read-only regardless of `permissions:` block).
- **In:** repository contents (`actions/checkout@v4`), Python 3.12 toolchain (`actions/setup-python@v5`), `pip install` traffic from PyPI (TLS-protected, but no `--require-hashes` enforcement).
- **Out:** workflow run logs (public for public repos, attached to the PR/commit), exit codes (gating merge), no artifacts uploaded by AC9-AC15 (no `actions/upload-artifact` step in cycle-34's design).
- **Trust:** untrusted (fork PR can submit arbitrary `pyproject.toml` / `tests/` content; CI executes that content via `pytest` + `pip install -e '.[dev]'`).

### TB2 — pip-install supply chain (extras declaration)

- **Principal:** the user running `pip install kb-wiki` or `pip install kb-wiki[hybrid]` (downstream consumer).
- **Authorisation:** none beyond PyPI's hash + signature handling; user trusts the project's pinning discipline.
- **In:** the new `[project.optional-dependencies]` mapping in `pyproject.toml`.
- **Out:** the resolved transitive dependency set after `pip install`.
- **Trust:** semi-trusted — the user has read the README and chosen to install; they have not necessarily audited every transitive.

### TB3 — CI artifact / log surface

- **Principal:** GitHub Actions log stream, surfaced on the workflow-run page.
- **Authorisation:** public for public repos (this repo is public per `Asun28/llm-wiki-flywheel`); private for private repos.
- **In:** stdout + stderr from each workflow step (ruff, pytest, pip check, pip-audit, build, twine check).
- **Out:** rendered run page; copy-paste into PR comments by humans.
- **Trust:** publicly readable; redaction is per-step (no `add-mask` directives in cycle-34's design).

### TB4 — public SECURITY.md disclosure

- **Principal:** any reader of the GitHub repo (public).
- **Authorisation:** none; file is in repo root.
- **In:** the four narrow-role CVE entries (each already public on NVD/GHSA); the disclosure path; the re-check cadence.
- **Out:** signal to attackers that the project knows about and accepts these CVEs.
- **Trust:** public; the question is whether mentioning them telegraphs *exploitable* surface, not whether mentioning them is itself novel disclosure.

### TB5 — git-tracked content lifecycle (gitignore vs git rm)

- **Principal:** a developer cloning the repo post-cycle-34.
- **Authorisation:** none beyond git read access.
- **In:** the cycle-34 commit which adds patterns to `.gitignore` AND deletes the four scratch files.
- **Out:** the resulting working tree; the resulting git history (where the scratch files still exist on `main^`).
- **Trust:** trusted developer; the threat is *forgetting one of the two halves of the fix* (gitignore added but file not deleted, or vice versa).

---

## Threats

### T1 — Fork-PR triggers workflow with write token; secrets exfiltrated

- **Description:** A malicious PR from a fork triggers `.github/workflows/ci.yml`. If the workflow grants `contents: write` or has access to repository secrets via `secrets.*`, the fork can exfiltrate them or push to `main`.
- **Affected boundary:** TB1.
- **Severity:** **HIGH** (default), but mitigated to LOW by GitHub's default fork-PR token-scope reduction.
- **Mitigation in this cycle:** AC9-AC16 specify NO repository secrets are referenced (no `secrets.ANTHROPIC_API_KEY`, no `secrets.PYPI_TOKEN`); workflow uses public-PyPI installs only. Add an explicit top-level `permissions: read-all` (or `contents: read`) block to make the principle of least privilege auditable. GitHub's 2023 default already drops fork-PR tokens to read-only, but the explicit block is defence-in-depth and discoverable.
- **Step-11 verification:** `grep -E 'secrets\.[A-Z_]+' .github/workflows/ci.yml` returns empty. `grep -E '^permissions:|^  permissions:' .github/workflows/ci.yml` matches `read-all` or `contents: read` (no `write`). `grep -E 'pull_request_target' .github/workflows/ci.yml` returns empty (only `pull_request`, which uses fork-scoped tokens).

### T2 — `actions/checkout@v4` pinned by tag; tag move swaps action code

- **Description:** Pinning by floating tag (`@v4` or `@v5`) means the action's code is whatever the tag points at *at the time CI runs*. A compromised maintainer can move the tag to a malicious commit. SHA-pinning prevents this.
- **Affected boundary:** TB1.
- **Severity:** **MEDIUM**. Both `actions/checkout` and `actions/setup-python` are official GitHub-org actions with strong maintainer protections, so realistic exploit requires either a GitHub-internal compromise or a stolen maintainer credential. SHA-pinning is best practice but not strictly required for first-party `actions/*` actions.
- **Mitigation in this cycle:** Tag-pin is acceptable for cycle 34 given (a) they are official GitHub actions, (b) Dependabot will surface action updates as PRs, (c) SHA-pinning would add per-cycle maintenance churn. **DEFER SHA-pinning to a follow-up cycle** if/when this repo gains supply-chain audit requirements.
- **Step-11 verification:** `grep -E 'uses: actions/(checkout|setup-python)@v[0-9]+$' .github/workflows/ci.yml` matches both. (The check confirms tag-pin is intentional, not accidentally floating to `@main`.)

### T3 — `python -m build` runs arbitrary build-time code; supply-chain risk if a build dep is compromised

- **Description:** `python -m build` invokes PEP-517 hooks, which execute arbitrary Python from the project's build backend (`hatchling` or whatever is in `[build-system].requires`). A compromised build dep on PyPI gets full code-execution at CI time. Same risk applies at PyPI publish time.
- **Affected boundary:** TB1.
- **Severity:** **MEDIUM**. Cycle 34 does not publish to PyPI — `twine check dist/*` is dry-run validation only. The exposure is the CI runner having a compromised `hatchling` (or whatever backend), which is a generic Python-supply-chain risk shared by every Python project.
- **Mitigation in this cycle:** Run on ephemeral GitHub-hosted runners (no persistent state). No publish step in CI (twine `check`, not twine `upload`). If/when the project adds a publish-on-tag workflow, that workflow MUST use trusted-publisher / OIDC token rather than long-lived PyPI credentials.
- **Step-11 verification:** `grep -E 'twine upload|TWINE_PASSWORD' .github/workflows/ci.yml` returns empty (dry-run only). `grep -E 'python -m build' .github/workflows/ci.yml` matches a step (AC15 confirmed).

### T4 — `pip-audit --ignore-vuln` becomes a permanent allow-list

- **Description:** AC14 ignores 4 narrow-role CVEs with `--ignore-vuln=CVE-2025-69872 --ignore-vuln=GHSA-xqmj-j6mv-4862 --ignore-vuln=CVE-2026-3219 --ignore-vuln=CVE-2026-6587`. If these are never re-evaluated, a CVE that gets a fix could remain ignored forever, and a future CVE on the same package could go unnoticed (because the ignore is by ID, not by package).
- **Affected boundary:** TB1, TB4.
- **Severity:** **MEDIUM**. The four IDs are by-ID-not-by-package, so a NEW CVE on the same package surfaces as a new failure. The risk is cycle-34's ignore list outliving its rationale.
- **Mitigation in this cycle:** AC8 documents re-check cadence: "Every cycle's Step 2 baseline + Step 11 PR-CVE diff + Step 15 late-arrival warn." SECURITY.md re-confirms this is the cadence. The feature-dev workflow already enforces this — cycle-N+1's Step 2 baseline will re-run pip-audit and surface any newly-fixable CVE in the four packages.
- **Step-11 verification:** `grep -E 'CVE-2025-69872|GHSA-xqmj-j6mv-4862|CVE-2026-3219|CVE-2026-6587' SECURITY.md` matches all four (each row in the acceptance table). `grep -E 're-check|recheck|cadence' SECURITY.md` matches a "Re-check Cadence" header (AC44).

### T5 — `pip check` with `continue-on-error: true` masks regressions

- **Description:** AC13 sets `continue-on-error: true` on `pip check` because the three known conflicts (`arxiv`/`requests`, `crawl4ai`/`lxml`, `instructor`/`rich`) would block CI today. The CI step still RUNS pip check and surfaces the output in logs, but does not fail the job. A new conflict introduced after cycle 34 would also be masked.
- **Affected boundary:** TB1.
- **Severity:** **LOW-MEDIUM**. The three conflicts are documented; new conflicts would be visible in the logs even though they don't fail the job. The unblock plan is "fix the three known conflicts in cycle-N+1, then drop `continue-on-error`".
- **Mitigation in this cycle:** AC13's CONDITION explicitly states this is a soft-fail with a documented unblock plan; cycle-N+1 follow-up tracked in BACKLOG. Step 11 should grep for the `continue-on-error: true` directive on the `pip check` step specifically (and confirm it is NOT applied to ruff, pytest, pip-audit, or build steps).
- **Step-11 verification:** `grep -E 'pip check' .github/workflows/ci.yml` matches a step. Within that step's block, `continue-on-error: true` is present. `grep -B1 -A1 'continue-on-error: true' .github/workflows/ci.yml` confirms the directive applies ONLY to the `pip check` step (not to ruff, pytest, pip-audit, or build).

### T6 — SECURITY.md disclosure path may not work for this repo configuration

- **Description:** "Report a vulnerability via GitHub Security Advisory" (private vulnerability reporting) requires the repo owner to have explicitly enabled the feature in repo settings. If it is disabled, the link in SECURITY.md fails open and reporters have no working channel.
- **Affected boundary:** TB4.
- **Severity:** **LOW**. The repo is single-developer (Asun28); a real reporter would also have email-fallback options.
- **Mitigation in this cycle:** AC7 documents BOTH the GitHub Security Advisory path AND an email fallback to the project owner. The email fallback is the always-works channel.
- **Step-11 verification:** `grep -E '@(gmail|protonmail|github)' SECURITY.md` matches at least one email. `grep -E 'security advisor|Security Advisory|Vulnerability Reporting' SECURITY.md` matches the disclosure-path header (AC7 + AC44).

### T7 — `.gitignore` additions don't retroactively delete tracked files

- **Description:** `.gitignore` only prevents UNTRACKED files from being added. If `findings.md`/`progress.md`/`task_plan.md` are already tracked in git, adding them to `.gitignore` does NOT remove them — they continue to live on `main`. The cycle requires AC29-AC32 (explicit `git rm`) to land in the SAME commit/PR as AC17 (gitignore additions). If the gitignore PR ships without the deletion PR, the four files persist.
- **Affected boundary:** TB5.
- **Severity:** **LOW** (process-only; no security impact, but defeats the purpose of the cycle).
- **Mitigation in this cycle:** Cycle 34 packages AC17 + AC29-AC32 + AC33-AC34 in a single PR (`feat/backlog-by-file-cycle34`). Step 11 verifies BOTH the gitignore and the deletion shipped together.
- **Step-11 verification:** `git ls-files findings.md progress.md task_plan.md claude4.6.md docs/repo_review.md docs/repo_review.html` returns empty (none tracked). `grep -E '^findings\.md$|^progress\.md$|^task_plan\.md$|^cycle-\*-scratch/$' .gitignore` matches all four cycle-34 patterns.

### T8 — Removing `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` breaks an existing user's workflow

- **Description:** A user with `raw/papers/foo.pdf` already in their repo would, post-cycle-34, see that file silently skipped during `kb compile`. AC25's pipeline message update only fires if the user *re-tries* ingest on the file.
- **Affected boundary:** none (this is a feature-narrowing change, not a security boundary).
- **Severity:** **LOW**. The cycle-34 risk register Row 3 confirms: today's code already REJECTS binary PDFs at ingest time (`ingest/pipeline.py:1233` raises). So a user with a PDF in `raw/papers/` was *never* successfully ingested — they have nothing to lose. The removal converts "binary-rejected at ingest time" into "extension-rejected at scan time" — strictly a clearer error.
- **Mitigation in this cycle:** AC25 updates the rejection message to suggest `markitdown` / `docling` conversion. AC20 updates the README to document the convert-first workflow.
- **Step-11 verification:** `python -c "from kb.config import SUPPORTED_SOURCE_EXTENSIONS; assert '.pdf' not in SUPPORTED_SOURCE_EXTENSIONS"` returns 0. AC25 regression test asserts the updated rejection message.

### T9 — Deleting `claude4.6.md` removes content the user relied on

- **Description:** `claude4.6.md` is a 40 KB legacy pre-Opus-4.7 copy of `CLAUDE.md`. If the user retained it as a "rollback baseline" for Opus 4.6 behaviour or as a reference for any specific instruction not yet ported into `CLAUDE.md`, deletion loses that.
- **Affected boundary:** TB5.
- **Severity:** **LOW**. Pre-deletion `git log -- claude4.6.md` shows zero commits (the file was never tracked — verified via `git log` returning empty). Even if it had been tracked, the file remains in git history and is recoverable via `git show` from any pre-cycle-34 commit.
- **Mitigation in this cycle:** Pre-delete diff against `CLAUDE.md` — risk-register Row 4 mandates "if diff shows novel content, abort the delete and surface as a `DESIGN-AMEND`." The cycle-17 L3 lesson (DESIGN-AMEND for surprises) is the escape hatch.
- **Step-11 verification:** `git show HEAD:claude4.6.md 2>/dev/null` returns empty (the file is not tracked at HEAD post-cycle). `test -f claude4.6.md && exit 1 || exit 0` (AC42 regression confirms).

### T10 — Tagged narrow-role CVE acceptance fails to unblock when fix becomes installable

- **Description:** SECURITY.md says litellm 1.83.7 fix is blocked by `click<8.2` transitive. If a future cycle relaxes the click pin (or litellm relaxes its transitive), the project should automatically pick up the fix and DROP the `--ignore-vuln=GHSA-xqmj-j6mv-4862` from CI. If no one notices the unblock, the ignore persists past its useful life.
- **Affected boundary:** TB1, TB4.
- **Severity:** **LOW**. T4's mitigation (per-cycle Step 2 baseline + Step 11 PR-CVE diff) catches this: when litellm 1.83.7 becomes installable, the next pip-audit run will report the GHSA as RESOLVABLE (not as a fresh vuln, because the ignore-list still suppresses it, but the resolution-state column changes).
- **Mitigation in this cycle:** AC8 + the cadence in SECURITY.md. The four `--ignore-vuln` flags must be reviewed every cycle's Step 2 baseline (per memory `feedback_dependabot_pre_merge`'s 4-gate model). When fix becomes installable, both the SECURITY.md row AND the CI flag get removed.
- **Step-11 verification:** SECURITY.md's litellm row explicitly cites "Fix available at 1.83.7, blocked by click<8.2 transitive" — the unblock condition is named. `grep -A2 'litellm' SECURITY.md` matches the unblock clause.

### T11 — Pip-audit JSON output, if archived as artifact, leaks installed-package fingerprint

- **Description:** AC14's `pip-audit` runs against the resolved environment. If the `--format=json` output were uploaded as a workflow artifact, it would publicly disclose the exact pinned-versions of every installed package — useful intel for an attacker mapping known-CVE-windows.
- **Affected boundary:** TB3.
- **Severity:** **LOW**. The package set is already public via `requirements.txt` and `pyproject.toml`; the marginal disclosure is minimal.
- **Mitigation in this cycle:** Cycle 34 does NOT use `actions/upload-artifact` for pip-audit output. The output is logged inline (where it is still public for public repos but not separately downloadable). If a future cycle adds artifact upload, the artifact must redact env-var values and not include `pip freeze` output.
- **Step-11 verification:** `grep -E 'actions/upload-artifact|pip freeze' .github/workflows/ci.yml` returns empty.

### T12 — README content drift could be re-introduced by future cycle

- **Description:** AC18 replaces the "No vectors. No chunking." line. Without a regression, a future cycle could re-introduce it via a copy-paste from older commits. AC40 codifies the regression: `tests/test_cycle34_release_hygiene.py::test_no_vectors_tagline_absent` asserts the literal string is NOT in `README.md`.
- **Affected boundary:** none (correctness, not security).
- **Severity:** **LOW**.
- **Mitigation in this cycle:** AC40 — content-presence regression that flips on revert (per cycle-24 L4 lesson).
- **Step-11 verification:** `pytest tests/test_cycle34_release_hygiene.py::test_no_vectors_tagline_absent -v` passes.

### T13 — Test-count badge static-string drift

- **Description:** Pre-cycle-34 the badge said `tests-2850` while live count was 2923 — a finding-6 P0 ship-blocker. AC21 replaces the count with a generic `tests-passing` shield, removing the drift surface entirely.
- **Affected boundary:** none (correctness).
- **Severity:** **LOW**.
- **Mitigation in this cycle:** AC21 replaces with generic shield; Q6 design-gate decision documented.
- **Step-11 verification:** `grep -E 'tests-[0-9]+-' README.md` returns empty (no static-count badges remain). `grep -E 'tests-passing-brightgreen' README.md` matches the new generic badge.

### T14 — `kb_save_synthesis` doc rename does not break callers

- **Description:** AC22 + AC27 rename references to `kb_save_synthesis` to `kb_query(save_as=...)`. If any external doc / external caller was matching the old name literally, the rename breaks it. But `kb_save_synthesis` was never an MCP tool — it never existed in the registry — so external matchers cannot have been using it functionally.
- **Affected boundary:** none.
- **Severity:** **LOW** (doc-only rename).
- **Mitigation in this cycle:** AC22 + AC27 + AC46 regression confirm the new wording is present. The implementation (`kb_query` with `save_as=` param) is unchanged; this is purely documentation alignment.
- **Step-11 verification:** `grep -rE 'kb_save_synthesis' README.md CLAUDE.md` returns empty (or matches only the clarifying note saying "this is `kb_query(save_as=...)`"). AC46 pytest passes.

---

## Data classification

| Data | Class | Crosses cycle-34 boundary? | Notes |
| --- | :---: | :---: | --- |
| Source code (`src/kb/`) | Public | TB1 | CI checks out and runs pytest on it; same as today's local pytest. |
| Test fixtures (`tests/`) | Public | TB1 | Same. |
| `pip-audit` output (package list + versions) | Semi-public | TB3 | Logs are public for public repos. Already inferable from `requirements.txt`. |
| `pyproject.toml` | Public | TB2 | New extras declaration; purely additive. |
| `requirements.txt` | Public | TB2 | Header comment added; pins unchanged. |
| `SECURITY.md` | Public | TB4 | Documents 4 already-public CVEs. No new disclosure. |
| GitHub Actions logs | Public | TB3 | Stdout/stderr from each step. |
| `ANTHROPIC_API_KEY` | **Secret** | NONE | Cycle 34 introduces NO secret references; CI does not call the API. |
| `raw/` content | Private | NONE | CI does not check out `raw/` (gitignored or absent). |
| `wiki/` content | Mixed | NONE | CI does not interact with a real `wiki/` (test fixtures use `tmp_wiki`). |
| `.env` content | **Secret** | NONE | `.env` is gitignored. CI does not have access. |
| `.data/` content | Mixed | NONE | Gitignored. CI does not interact. |

**Confirmed:** none of the cycle-34 changes leak API keys, content from `raw/`, content from `wiki/`, contents of `.env`, or contents of `.data/`. The CI workflow operates on PUBLIC repo content only.

---

## Authn / authz

For `.github/workflows/ci.yml` specifically:

- **`permissions:` block REQUIRED.** Add an explicit top-level `permissions: read-all` (or, more narrowly, `permissions: { contents: read }`) so the principle of least privilege is auditable.
- **No write scopes requested.** Confirm no `contents: write`, `pull-requests: write`, `issues: write`, or `id-token: write` (the last would be for trusted-publisher OIDC, which cycle 34 does not need).
- **No `secrets.*` references.** Cycle 34 does not call the Anthropic API in CI; does not publish to PyPI in CI; does not push to S3 / Azure Blob. Zero secret references is correct.
- **Trigger scope.** `on: [push, pull_request]` is correct. Avoid `pull_request_target` (which would grant the FORK PR a write-scoped token from the main repo's secrets — a known fork-PR escalation path).
- **Default `GITHUB_TOKEN` lifetime.** Per-job, minted by GitHub; no manual rotation needed.

**Step-11 verification:** the explicit `permissions: read-all` (or equivalent) line in `.github/workflows/ci.yml`. `grep -E 'pull_request_target|id-token: write|contents: write' .github/workflows/ci.yml` returns empty.

---

## Logging / audit

What the new workflow logs:

- **Ruff output** — file paths + line numbers + lint codes. Public-repo content only; no secrets.
- **Pytest output** — test names + assertion failures. May include path strings from test fixtures (which use `tmp_wiki` / `tmp_path`, so paths are `/tmp/pytest-xyz/...`, not `~/.env` or similar). Confirm: `tests/test_cycle34_release_hygiene.py` is fixture-free per AC37-AC48; uses `Path("README.md")` etc., relative to repo root. Safe.
- **`pip check` output** — names of conflicting packages. Public-by-`requirements.txt`.
- **`pip-audit` output** — names of installed packages + version pins + vulnerability IDs. Public-by-`requirements.txt` + `pyproject.toml`.
- **`python -m build` output** — wheel/sdist filenames; build hook stdout. Includes the repo's own modules' import paths. Safe.
- **`twine check dist/*` output** — readme rendering check; package metadata check. Safe.

**No `actions/upload-artifact` step in cycle 34.** No JSON pip-audit dump is archived. No env dump is archived. If a future cycle adds artifact upload, it must redact env-var values and not include `pip freeze` (covered under T11).

**No log mask directives.** Cycle 34 does not use `::add-mask::`. Acceptable because no secrets are referenced. If the project later adds an `ANTHROPIC_API_KEY`-using step, that step must `::add-mask::` the key value before any echo / debug print.

---

## Step 11 verification checklist

This is what Step 11's Codex security verify (R2) compares against. Each row maps a threat to a one-line check.

| # | Threat | Check |
| ---: | --- | --- |
| 1 | T1 | `grep -E 'secrets\.[A-Z_]+' .github/workflows/ci.yml` returns empty |
| 2 | T1 | `.github/workflows/ci.yml` has top-level `permissions: read-all` (or `contents: read`) |
| 3 | T1 | `grep -E 'pull_request_target' .github/workflows/ci.yml` returns empty |
| 4 | T2 | `grep -E 'uses: actions/(checkout|setup-python)@v[0-9]+$' .github/workflows/ci.yml` matches both (intentional tag-pin) |
| 5 | T3 | `grep -E 'twine upload\|TWINE_PASSWORD' .github/workflows/ci.yml` returns empty (dry-run only) |
| 6 | T3 | `grep -E 'python -m build' .github/workflows/ci.yml` matches a step (AC15) |
| 7 | T4 | `grep -E 'CVE-2025-69872\|GHSA-xqmj-j6mv-4862\|CVE-2026-3219\|CVE-2026-6587' SECURITY.md` matches all four |
| 8 | T4 | `grep -iE 're-check\|recheck\|cadence' SECURITY.md` matches a "Re-check Cadence" header |
| 9 | T5 | `grep -E 'pip check' .github/workflows/ci.yml` matches; `continue-on-error: true` is present on that step ONLY |
| 10 | T6 | `grep -iE '@(gmail\|protonmail\|github)\|Security Advisory\|Vulnerability Reporting' SECURITY.md` matches |
| 11 | T7 | `git ls-files findings.md progress.md task_plan.md claude4.6.md docs/repo_review.md docs/repo_review.html` returns empty |
| 12 | T7 | `grep -E '^findings\.md$\|^progress\.md$\|^task_plan\.md$\|^cycle-\*-scratch/$' .gitignore` matches all four patterns |
| 13 | T8 | `python -c "from kb.config import SUPPORTED_SOURCE_EXTENSIONS; assert '.pdf' not in SUPPORTED_SOURCE_EXTENSIONS"` exits 0 |
| 14 | T9 | `git show HEAD:claude4.6.md 2>/dev/null` returns empty; `test ! -f claude4.6.md` passes |
| 15 | T10 | SECURITY.md's litellm row contains "1.83.7" + "click<8.2" unblock clause |
| 16 | T11 | `grep -E 'actions/upload-artifact\|pip freeze' .github/workflows/ci.yml` returns empty |
| 17 | T12 | `pytest tests/test_cycle34_release_hygiene.py::test_no_vectors_tagline_absent -v` passes |
| 18 | T13 | `grep -E 'tests-[0-9]+-' README.md` returns empty; `grep -E 'tests-passing-brightgreen' README.md` matches |
| 19 | T14 | `pytest tests/test_cycle34_release_hygiene.py::test_kb_save_synthesis_clarification_in_claude_md -v` passes (AC46) |
| 20 | AC9 | `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` parses without error |
| 21 | AC9 | Workflow has `on:` including both `push` AND `pull_request` |
| 22 | AC10-15 | Workflow `test` job has steps for: ruff, `pytest --collect-only`, `pytest`, `pip check` (continue-on-error), `pip-audit` (with all 4 `--ignore-vuln`), `python -m build && twine check dist/*` |
| 23 | AC16 | Workflow `test` job runs on `ubuntu-latest` with python `'3.12'` (single platform, no matrix) |
| 24 | AC44 | `SECURITY.md` has headers `## Vulnerability Reporting`, `## Known Advisories`, `## Re-check Cadence` |
| 25 | AC45 | `pytest tests/test_cycle34_release_hygiene.py::test_ci_workflow_yaml_parses -v` passes |

**Total checklist rows: 25.**

---

## Summary

- **5 trust boundaries** identified: TB1 GitHub Actions runner, TB2 pip-install supply chain, TB3 CI logs, TB4 SECURITY.md disclosure, TB5 git-tracked-content lifecycle.
- **14 threats** surfaced (T1-T14): 1 HIGH-default-mitigated-to-LOW (T1 fork-PR), 4 MEDIUM (T2 tag-pin, T3 build supply-chain, T4 CVE allow-list, T5 pip-check soft-fail), 9 LOW.
- **All 14 threats** have mitigations in cycle-34 ACs except **T2 (action SHA-pinning)** which is explicitly DEFERRED to a follow-up cycle with documented rationale (official `actions/*` actions; SHA-pinning maintenance churn).
- **Step-11 verification checklist: 25 rows.**

End of cycle-34 threat model.
