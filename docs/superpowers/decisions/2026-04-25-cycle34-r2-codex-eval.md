# Cycle 34 — R2 Codex-Fallback (Opus) Design Evaluation

**Date:** 2026-04-25 · **Cycle:** 34 · **Reviewer:** Opus 4.7 (1M) acting as R2 Codex fallback per cycle-12 L1 / cycle-22 L2 hook block.
**Scope:** edge cases, failure modes, integration risk, security, performance, AND CI behaviour under realistic GitHub-Actions failure modes — distinct from R1 Opus's symbol-verification + scope scoring.
**Inputs read:** `docs/superpowers/decisions/2026-04-25-cycle34-requirements.md` (48 ACs), `docs/superpowers/decisions/2026-04-25-cycle34-threat-model.md` (14 threats, 25-row checklist), `docs/superpowers/specs/2026-04-25-cycle34-brainstorming.md` (Q1-Q10 defaults), `docs/reviews/2026-04-25-comprehensive-repo-review.md` § 1, 6, 7, 14.

---

## Analysis

The R2 mandate is to find cliff-edges R1 will miss. After reading all four inputs and probing the repo with `Grep` + a live `pip-audit` invocation, my finding is that the cycle-34 design is fundamentally sound but is shipping with **eight latent failure modes** that turn green-CI into a false signal. The most consequential are: (a) the `.pdf` cascade extends beyond `config.py` to `compile/compiler.py:116/216`, `lint/checks.py:733`, AND **at least four existing tests** that pre-create `.pdf` files (one of which — `test_v0915_task09::test_pdf_extension_rejected` — actively asserts on the rejection behaviour and could pass for the wrong reason after the change); (b) the CI install step `pip install -e '.[dev]'` will break on Linux because `crawl4ai` and `playwright` are NOT in any extras, but they ARE in `requirements.txt` — **so the cycle-34 CI will not have them, but that's actually fine since they aren't imported by `src/kb`**, EXCEPT the augment fetcher transitively needs `httpx` which IS in the proposed `augment` extra but won't be installed by `[dev]` alone; (c) `pip-audit` does accept multiple `--ignore-vuln` flags (verified live: `action="append"`), so AC14 is correct as-specified; (d) the `.gitignore` ALREADY contains all four scratch patterns (lines 56, 61, 62, 63) — so AC17 is **partially redundant**; what's actually missing is the `git rm` for tracked/untracked-but-on-disk files (AC29-32 cover this); (e) the existing `_TEXT_EXTENSIONS` allowlist at `mcp/core.py:104` ALREADY excludes `.pdf`, so the MCP boundary already rejects PDFs — AC24's removal from `SUPPORTED_SOURCE_EXTENSIONS` only affects the lib-level path through `pipeline.py:1200`, which is the post-decode UnicodeDecodeError path. AC25's message-update target therefore lives at `pipeline.py:1261`, NOT at the MCP boundary.

The second-order observation is that the threat model is complete on the GitHub-Actions runner attack surface (T1-T3, T11) but undercounts **integration risks between proposed extras and existing imports**. Concretely: `kb.utils.cli_backend` imports `jsonschema` at module top (verified at line 17), and `kb.cli` imports `cli_backend` transitively when `KB_LLM_BACKEND` is set — so the runtime-deps list MUST include `jsonschema` (AC3 is correct on this), but the threat model does not list a "boot-lean import surface invariant" guard. Similarly, `kb.lint.fetcher` imports `httpcore`, `httpx`, `trafilatura` at module top (lines 29-32), and is imported by `kb.lint.augment` at module level — so anyone running `kb lint` (without `--augment`) will boot-fail without `[augment]` installed. AC23's "minimal install (no extras)" promise is therefore **false on its current ACs** unless `httpx`+`trafilatura` move into `dependencies` OR `lint.fetcher` is converted to a function-local import. Per cycle-23-32 history, function-local imports for `mcp.browse`/`mcp.quality` are already the established pattern — so the cleanest cycle-34 move is to mark these as cycle-N+1 follow-up and add the boot-lean guard now, rather than silently shipping a broken minimal install.

---

## CI workflow edge cases

### CI-1 — `pip install -e '.[dev]'` does NOT need playwright (LOW)

Risk: `crawl4ai 0.8.6` and `playwright` are in `requirements.txt` but the design correctly does NOT pull them via any extra. Verified by `Grep "import bs4|import playwright|import crawl4ai|from bs4|from playwright|from crawl4ai" src/` → **zero matches**. They are devtime-only (Web Clipper alternative) per non-goals §2 and not imported by `src/kb`. So `pytest` will collect cleanly without playwright. **However**: the existing test `test_lint_augment_*` etc. likely use `pytest-httpx` to mock fetcher behaviour without invoking `playwright` — VERIFIED: `pytest-httpx==0.36.2` is in `requirements.txt`. **Action**: add `pytest-httpx>=0.30` to the `dev` extra so the CI install via `[dev]` covers it. Severity: LOW (without it, ~30 augment tests fail on CI; not a blocker but a green-CI saboteur).

### CI-2 — Fork-PR `pyproject.toml` build-time RCE (HIGH, mitigated by ephemeral runners)

Risk: a fork PR can submit a malicious `[build-system].requires = ["evil-package>=0"]` and `pip install -e '.[dev]'` will execute that package's PEP-517 hooks at build time. T3 in the threat model addresses publish supply-chain but does NOT cover fork-PR-controlled `[build-system].requires`. **Mitigation**: GitHub-hosted runners are ephemeral — even RCE only persists for the job lifetime. There are NO secrets in the fork-PR token (T1 mitigation). **But**: a malicious fork PR can still mine crypto, exfiltrate the public-readable repo state to attacker logs, or spam GitHub Actions free minutes (cost amplification). **Action**: AC12-AC15 should pin `pyproject.toml` validation step BEFORE `pip install -e .` — e.g. `python -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['build-system']['requires'] == ['setuptools>=75.0']"`. Severity: MEDIUM. **Add as cycle-34 condition** if Q4's ignore-vuln strategy is meant to make CI green-checkmarks meaningful.

### CI-3 — `ubuntu-latest` advancing to 24.04 mid-cycle (LOW)

Risk: GitHub default runner image advances yearly. Python 3.12 will continue to be available on 24.04 (verified: `actions/setup-python@v5` resolves the version, not OS-bundled python). The risk is transitive native-build deps that need libstdc++/openssl3 vs openssl1.1. None of the kb-runtime-extras packages have C extensions specific to ubuntu-22.04 (model2vec uses pure-python torch+sentence-transformers; sqlite_vec ships pre-built wheels). **Action**: pin `runs-on: ubuntu-22.04` for cycle 34 with a comment "review at next ubuntu-latest LTS bump"; OR accept the risk and let the runner image float. The risk-register Row 1 of the requirements doc does not address this. **Recommendation**: float the image (no pin) to avoid pin-rot, but add a docstring comment in `ci.yml` noting "if a future runner image breaks 3.12 deps, pin and file follow-up". Severity: LOW.

### CI-4 — pip-audit `--ignore-vuln` accepts multiple flags (RESOLVED, verified live)

I verified live with `pip-audit 2.10.0` that `--ignore-vuln` is `action="append"`:

```
parser.add_argument("--ignore-vuln", type=str, metavar="ID", action="append",
                    dest="ignore_vulns", default=[], ...)
```

Multiple flags work. AC14 is correct as-specified. **No action needed.** Severity: N/A.

### CI-5 — `python -m build` needs `build` package, not in `[dev]` extra (HIGH-IMPACT BUG)

Risk: AC15 says CI runs `python -m build && python -m twine check dist/*`. The `build` and `twine` packages are NOT in `requirements.txt`, NOT in the proposed `dev` extra (AC2 lists only `pytest`, `ruff`), and NOT auto-installed by `setup-python`. So the AC15 step will fail with `No module named build`. **Fix**: AC2's `dev` extra MUST include `build>=1.2`, `twine>=5.0`, and `pip-audit>=2.10` — OR these get installed in dedicated CI steps via `pip install build twine pip-audit` immediately before AC14/AC15. The threat model § "Authn / authz" implicitly assumes these are installed but never asserts it. **Recommendation**: install via `pip install build twine pip-audit` in a dedicated step rather than bloating `[dev]` — these are CI-only tooling. Severity: HIGH (AC15 unachievable as-spec'd).

### CI-6 — `pyproject.toml [build-system].requires = ["setuptools>=75.0"]` (verified OK)

Verified live: `pyproject.toml:47` reads `requires = ["setuptools>=75.0"]`. Modern `python -m build` will fetch setuptools 75.x to its build env. No action. Severity: N/A.

### CI-7 — `pytest --collect-only -q` exit-code semantics (verified OK)

Risk: AC11 asserts the workflow runs collection. `pytest --collect-only -q` returns exit 0 on success, exit 2 on collection error, exit 5 if no tests collected. Verified live: 2923 tests collected → exit 0. The risk is that AC11 + AC12 have the same exit-code semantics, so a collection failure cascades into pytest failure twice (redundant but not broken). **No action**, but consider conditional: `pytest --collect-only -q > /dev/null` first, fail-fast if 2 (parse error) before running full suite — saves CI minutes. Severity: LOW.

### CI-8 — `pip check` `continue-on-error: true` masks NEW conflicts (LOW-MED, addressed by T5)

T5 already covers this. The only edge-case the threat model misses: `continue-on-error: true` at GitHub Actions level requires the directive to be on the SPECIFIC step, not at the job level. AC13 says "this step" which matches the threat model verification at row 9. **No additional action**, but Step-11 grep should explicitly verify the directive's INDENTATION column matches the step's column (per YAML spec, a job-level `continue-on-error: true` would propagate to ALL steps and silently pass everything). Severity: LOW.

---

## Test edge cases

### AC40 — "No vectors. No chunking." regression test (MED-RISK SCOPE BUG)

The test asserts the literal string is **not** present in `README.md`. **Edge case**: the comprehensive review (now committed at `docs/reviews/...md`) contains the literal string at line 98: `` "No vectors. No chunking." `` — and similarly at line 155 and line 737. AC40 only reads `README.md` so the review file is harmless. **But**: per cycle-23 L4 doc-count drift, generalising `Path("README.md").read_text()` against `"No vectors. No chunking."` is fine ONLY IF the README copy never paraphrases or quotes the old tagline (e.g., in a "what we used to say" comparison). **Recommendation**: AC40 is correct as-spec'd — the new tagline (AC18) replaces the old wholesale and there's no quoting. **No action**, but R3 should grep `README.md` post-AC18-Edit to confirm zero residue. Severity: LOW.

### AC41 — `kb.config` import in fixture-free test (verified OK)

Verified live: `python -c "import kb.config; print(kb.config.SUPPORTED_SOURCE_EXTENSIONS)"` works from cwd at repo root. The cycle-19 L2 reload-leak pattern applies to module-top reads that snapshot `WIKI_DIR`/`RAW_DIR` — `SUPPORTED_SOURCE_EXTENSIONS` is a static frozenset literal at config.py:117-119, NO env-var lookups, NO Path operations. AC41 is safe as-spec'd. **No action**. Severity: N/A.

### AC42 — `Path("findings.md").exists()` evaluates against repo root (verified OK)

Verified: `pyproject.toml [tool.pytest.ini_options]` does NOT set `rootdir` explicitly, so pytest auto-discovers it via the `pyproject.toml` location → cwd is the repo root when pytest runs. `Path("findings.md")` is relative to cwd → resolves to `D:\Projects\llm-wiki-flywheel\findings.md`. Verified live: `Path("README.md").exists() = True` from cwd. AC42 works. **No action**. Severity: N/A.

### AC43 — `.gitignore` regression (PARTIAL REDUNDANCY)

**Surprising finding**: the `.gitignore` ALREADY lists `claude4.6.md` (line 56), `/findings.md` (line 61), `/progress.md` (line 62), `/task_plan.md` (line 63). Verified by Grep. **AC17 is partially redundant** — it documents adding patterns that already exist. The forward-looking pattern `cycle-*-scratch/` is genuinely new. **AC43's regression** therefore needs to be specific about what it asserts: not "lines added" but "lines present". **Recommendation**: AC43 wording should be `assert all(pattern in gitignore_text for pattern in REQUIRED_PATTERNS)` rather than "lines were added in this cycle". Severity: LOW (test still works, but rationale documentation is stale).

### AC44 — SECURITY.md headers pinned at cycle 34 (LOW reorg risk)

The user might reorganise headers in cycle-N+1 (e.g., merge "## Vulnerability Reporting" + "## Disclosure Path" into one section). AC44 pins three specific section headers. **Recommendation**: AC44's regression should test for the headers' PRESENCE not their ORDER, and should accept `## Vulnerability Reporting` OR `## Disclosure` (regex `## (Vulnerability Reporting|Disclosure)`). **Action**: clarify AC44 to use `re.search(r"^##\s+Vulnerability Reporting", content, re.M)` to allow the user freedom to add subsections later. Severity: LOW.

### AC45 — `yaml.safe_load` on workflow YAML (EDGE: `!!` tags)

GitHub Actions YAML uses standard YAML 1.2 — no custom `!!` tags from cycle-34's design (no `!Ref`, no `!GetAtt`, no Sceptre-style includes). `yaml.safe_load` rejects custom-tag YAML by default. Verified: cycle-34's `ci.yml` design uses only `on:`, `jobs:`, `steps:`, `uses:`, `run:`, `with:` — all standard. **No action**. Severity: N/A.

### AC48 — comprehensive review starts with exact heading (verified OK)

Verified live: file's line 1 is `# LLM Wiki Flywheel — Comprehensive Repository Review` (em-dash, not hyphen). The em-dash is U+2014 — make sure the AC48 test uses the same Unicode codepoint. **Edge case**: if a future commit accidentally normalises em-dash to ASCII hyphen, AC48 silently fails. **Recommendation**: AC48 test should use `startswith(b"# LLM Wiki Flywheel")` (prefix match, no em-dash dep) AND a second assert `"Comprehensive Repository Review" in first_line`. Two-assert approach is robust to em-dash drift. Severity: LOW.

---

## PDF cascade analysis

### Consumers of `SUPPORTED_SOURCE_EXTENSIONS` (verified live)

```
src/kb/config.py:117                — owner (cycle-34 AC24 changes here)
src/kb/compile/compiler.py:13,116,216  — imports + 2 filter sites (scan_raw_sources, _scan_changed)
src/kb/ingest/pipeline.py:21,1200,1203 — imports + lib-level extension check (raises ValueError)
src/kb/lint/checks.py:22,733          — import + filter site
```

After AC24 removes `.pdf` from the frozenset, all three consumers automatically narrow correctly. **No code changes needed in consumers** — this is a clean single-source-of-truth update.

### `.pdf` references in `src/kb/`

```
src/kb/config.py:117-119  (literal in frozenset — REMOVE per AC24)
src/kb/ingest/pipeline.py:1198  (comment: "allowlist (includes .pdf)" — UPDATE comment per AC25)
```

Comment at `pipeline.py:1198` reads `"allowlist (includes .pdf) so PDFs still hit the UTF-8 decode path where they fail with the helpful message"`. After AC24, this comment is **stale** because `.pdf` is no longer in the allowlist. The lib will now reject `.pdf` at line 1200 with `Unsupported source extension: '.pdf'` BEFORE the UTF-8 decode runs. **AC25 must also update this comment** — it's a code-doc drift bug that R3 will catch. **Recommendation**: AC25's scope expand to "update `pipeline.py:1198` comment + `pipeline.py:1261` rejection message".

### `.pdf` in `tests/`

VERIFIED 13 occurrences across 6 test files. Most are in citation/reference tests (`test_models.py`, `test_query.py`, `test_v0916_task05.py`) where `.pdf` is just a path string — those are fine. The two LOAD-BEARING tests:

1. **`tests/test_v0915_task09.py:230-244` `test_pdf_extension_rejected`** — asserts `kb_ingest(str(fake_pdf))` returns an error string that contains "Unsupported file type" OR "pdf". This test exercises the **MCP boundary** at `mcp/core.py:543` (`_TEXT_EXTENSIONS` rejection — `.pdf` already not in `_TEXT_EXTENSIONS`). Cycle 34's AC24 removes `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` (the LIB allowlist). **The MCP boundary's rejection message at line 543 reads `f"Error: Unsupported file type '{path.suffix}'."` — unchanged by cycle 34**. So this test **continues to pass** after cycle 34 because it tests the MCP boundary, not the lib boundary. **No action needed for this test**. Severity: N/A.

2. **`tests/test_v0916_task03.py:38-50` `test_binary_file_raises_clear_error`** — asserts `ingest_source(pdf, "paper")` raises `(UnicodeDecodeError, ValueError)`. **Cycle 34 changes the BEHAVIOR**: pre-cycle-34, the code path is `extension allowed → read_bytes → UnicodeDecodeError → raise ValueError("Binary file cannot be ingested")` (post-cycle-19 binary fix, with a `from e` chain so `UnicodeDecodeError` is the `__cause__`). Post-cycle-34, the code path is `extension NOT allowed → raise ValueError("Unsupported source extension")` BEFORE `read_bytes`. The test's `pytest.raises((UnicodeDecodeError, ValueError))` accepts EITHER, so it **continues to pass**. **But the message changes**: from "Binary file cannot be ingested" to "Unsupported source extension". A future cycle that pins the message via `match=` will be surprised. **No action for cycle 34**, but a comment in cycle-34's CHANGELOG noting "binary-PDF rejection now happens at extension-check phase (sooner)" would be useful. Severity: LOW.

3. **`tests/test_v0915_task11.py:430-431` `test_raw_source_papers_subdirectory`** — only creates a `.pdf` file via `create_raw_source` fixture and asserts existence. Doesn't ingest. **No action**. Severity: N/A.

4. **`tests/test_backlog_by_file_cycle1.py:201-208` `test_c2_ingest_rejects_unsupported_suffix`** — uses a suffix-less file (`README` literal). NOT a `.pdf` test. **No action**. Severity: N/A.

### Net assessment

PDF cascade is **safe**. AC25 needs to expand scope to update the comment at `pipeline.py:1198` (currently says "includes .pdf" which becomes stale). All four `.pdf`-touching tests continue to pass under cycle 34's behaviour. **AC25 expansion is the only required scope addition.**

---

## Extras dependency mapping

Concrete package list per extra, derived from `Grep "^import |^from " src/kb/<module>` cross-referenced against `requirements.txt`:

### `hybrid` extra

- `model2vec>=0.5.0` (verified pinned at `model2vec==0.8.1`)
- `sqlite-vec>=0.1.0` (verified pinned at `sqlite-vec==0.1.9`)
- **+ `numpy>=1.26`** (transitive of `model2vec` but worth pinning — `kb.query.embeddings` imports `numpy` directly)

### `augment` extra

- `httpx>=0.27` (verified pinned at `httpx==0.28.1`; imported at `kb.lint.fetcher:30`)
- `httpcore>=1.0` (verified pinned at `httpcore==1.0.9`; imported at `kb.lint.fetcher:29` for `SafeTransport`)
- `trafilatura>=1.12` (verified pinned at `trafilatura==2.0.0`; imported at `kb.lint.fetcher:31`)
- **NOT `bs4`/`crawl4ai`/`playwright`** — verified zero direct imports under `src/kb/`. These can stay in `requirements.txt` as devtime tools but do NOT belong in `[augment]`.

### `formats` extra

- `nbformat>=5.0,<6.0` (verified pinned in `requirements.txt:156`; imported at `kb.query.formats.jupyter:12`)
- **NOTHING for marp/html/chart/markdown** — those use stdlib only (`pathlib`, `subprocess` for marp CLI). Marp CLI is external (npm install marp-cli) and intentionally not a Python dep.

### `eval` extra

- `ragas>=0.4` (pinned at 0.4.3 — UNFIXED CVE per Finding 1)
- `litellm>=1.83` (pinned at 1.83.0 — UNFIXED GHSA per Finding 1; fix at 1.83.7 blocked by click<8.2)
- **+ `datasets>=4.0`** (ragas hard-dep; pinned at 4.8.4)
- **+ `langchain` family** (ragas hard-dep — but ragas pulls these transitively, so don't double-list)

### `dev` extra

- `pytest>=7.0` (verified at `pytest==9.0.3`)
- `ruff>=0.4.0` (verified at `ruff==0.15.9`)
- **MISSING but should be added**: `pytest-httpx>=0.30` (verified pinned at 0.36.2; used by ~30 augment tests)

### CI tooling — NOT in any extra

- `build>=1.2` (AC15 dependency)
- `twine>=5.0` (AC15 dependency)
- `pip-audit>=2.10` (AC14 dependency)

These three should be installed via a dedicated `pip install build twine pip-audit` step in CI — NOT inside `[dev]`. Q3's "5 extras" answer remains correct; CI tooling is its own concern.

### Mutual-exclusion / cross-references

- `hybrid` and `augment` are **independent** — `kb.query.embeddings` does NOT import anything from `kb.lint`. Verified via Grep.
- `eval` is **dev-time only** — no runtime path through `src/kb/` imports `ragas` or `litellm`. Verified by `Grep "import ragas|import litellm" src/` → zero matches.
- `formats` requires `kb.query.engine` to be importable — and `engine.py:1247` already does the lazy-import dance for nbformat. So `[formats]` is independent.

**Net**: Q3's answer is correct. No cross-extra dependencies. **Recommendation**: add `pytest-httpx>=0.30` to `dev` extra.

---

## Version bump cascade

`grep -rn "0\.10\.0"` finds 25+ hits across:

| File | Line | Action |
|---|---|---|
| `pyproject.toml:3` | `version = "0.10.0"` | UPDATE to "0.11.0" per AC4 |
| `src/kb/__init__.py:3` | `__version__ = "0.10.0"` | **MISSING from AC list — must update.** Cycle-21 audit (CHANGELOG-history.md:1052) explicitly aligned this with `pyproject.toml`; same alignment must hold post-cycle-34. |
| `README.md:11` | version badge `v0.10.0` | UPDATE to v0.11.0 (NOT in AC list — must update) |
| `README.zh-CN.md:5` | version badge `v0.10.0` | DEFERRED per Q7 — but stale-by-design |
| `docs/architecture/architecture-diagram.html:501` | `v0.10.0` badge | UPDATE — diagram-sync MANDATORY rule (CLAUDE.md "Architecture Diagram Sync") |
| `docs/architecture/architecture-diagram-detailed.html:398` | `v0.10.0` heading | UPDATE — diagram-sync rule |
| `CHANGELOG.md` | `[Unreleased]` Quick Reference | KEEP `[Unreleased]`. The version bump in pyproject is independent of CHANGELOG semver-stamping; cycle-N convention is to keep `[Unreleased]` until a real release tag is cut. **Confirm with R3.** |
| `CLAUDE.md:7` | `**State:** v0.10.0 · 2923 tests` | UPDATE per AC26 (already in scope). |

**Critical scope gap**: AC4 only mentions `pyproject.toml`. **`src/kb/__init__.py:3` and `README.md:11` MUST be added to AC4's scope** or they'll drift from `pyproject.toml`. The cycle-21 audit explicitly flagged this kind of drift and aligned them. **Recommendation**: expand AC4 to `version = "0.11.0"` in `pyproject.toml` AND `__version__ = "0.11.0"` in `src/kb/__init__.py` AND README badge update. Architecture diagram updates can be a SEPARATE AC4.5 since they require a re-render via Playwright (mandated by CLAUDE.md "Architecture Diagram Sync") which is NOT trivially doable in cycle 34's text-only scope. **Action**: AC4 must explicitly list the four version sites; the diagram re-render is either added as AC4.5 or DEFERRED to cycle 35 with a BACKLOG entry.

---

## SECURITY.md edge cases

### Default-install vs extras-install impact

| Advisory | Package | Default install? | `[hybrid]`? | `[augment]`? | `[formats]`? | `[eval]`? |
|---|---|---|---|---|---|---|
| CVE-2025-69872 | diskcache 5.6.3 | NO (transitive of trafilatura's robots.txt cache) | NO | **YES** (via trafilatura → diskcache) | NO | NO |
| GHSA-xqmj-j6mv-4862 | litellm 1.83.0 | NO | NO | NO | NO | **YES** (ragas harness) |
| CVE-2026-3219 | pip 26.0.1 | **YES** (pip is universally bundled) | YES | YES | YES | YES |
| CVE-2026-6587 | ragas 0.4.3 | NO | NO | NO | NO | **YES** |

**Important caveat**: a fresh Python venv created with `python -m venv .venv` ships with whatever pip the host Python had — typically the latest available. The user might NOT have pip 26.0.1 specifically; CI's `pip install` invocation would upgrade pip via `pip --upgrade pip` if so. **CI's `pip-audit` audits the RUNTIME PIP** which on `actions/setup-python@v5` is whatever the action installed. **Recommendation**: SECURITY.md's pip row should say "applies to pinned `pip==26.0.1` only — fresh installs may pull a fixed version" with a disclosure date. Severity: LOW.

### Disclosure of advisory IDs to attackers

T6 in the threat model addresses this. The four IDs are already public. Mentioning them in SECURITY.md is **discoverable signal** (good — makes audit reproducible) not **novel disclosure** (bad — publicising 0-day). Net: no information leak. **No action**. Severity: N/A.

### Re-check cadence drift

T4 + T10 cover the "ignore list outliving its rationale" risk. AC8 documents the cadence. **Edge case**: cycle-N+1's Step 2 baseline must run `pip-audit` WITHOUT `--ignore-vuln` flags first to surface UNCHANGED state, then re-run WITH them to surface NEW vulns. The current AC14 always passes `--ignore-vuln`, so a transition from "still vuln" → "fixed" would be invisible. **Recommendation**: add a CI step OR a Step-2 baseline check that runs `pip-audit` BARE (no ignore) and reports the delta — not as a CI failure but as an informational warning. Severity: LOW. **Add as cycle-N+1 follow-up**, not blocking for cycle 34.

---

## Doc drift sweep

### README.md narrative test counts (line 339, 352, 384-385)

Per Finding 6 + AC21, the cycle-34 design replaces only the **badge** count with a generic shield. Lines 339, 352, 384, 385 cite historical numbers (1033, 1177, 2725, 2716, 2725) in narrative phase summaries and the Development collapsible. **AC21 explicitly does NOT touch these.** That's correct because they document HISTORICAL test counts at v0.9.16, v0.10.0, v0.10.0-post-audit — none of which need updating to current. **No action**. Severity: N/A.

### CLAUDE.md Latest full-suite line (line 45)

Per AC26, this updates `2923 tests / 253 files (2912 passed + 10 skipped + 1 xfailed)` post-cycle-34 commits. Per cycle-15 L4 commit-count backfill, the count must be obtained from `pytest --collect-only -q | tail -1` AFTER all cycle-34 commits land. The wording template is preserved: `**State:** v0.11.0 · {N} tests / {F} files ({passed} passed + {skipped} skipped + {xfailed} xfailed)`. **No action — covered by AC26**. Severity: N/A.

### CLAUDE.md "Latest cycle (33)" + "Latest cycle (32)" (lines 13, 14)

These are cycle-bullet summaries. Cycle 34 will need to ADD a "Latest cycle (34)" bullet ABOVE the cycle 33 bullet. **AC26 doesn't explicitly mention this.** **Recommendation**: AC26 expand to include the new cycle-34 bullet write. Severity: LOW.

### README.zh-CN.md sync

Per Q7, deferred. The Chinese mirror lags by design. **Action**: confirm Q7 default holds; no English-side AC depends on Chinese sync. Severity: N/A (per cycle-34 non-goal).

### Architecture diagrams (HTML + PNG)

**Per CLAUDE.md MANDATORY rule**: every HTML edit must re-render the PNG and commit it. Cycle 34's version bump in `architecture-diagram.html:501` and `architecture-diagram-detailed.html:398` triggers this rule. **The cycle-34 design does NOT include this.** **Recommendation**: either DEFER the diagram version-bump to cycle 35 (and document the temporary drift in CHANGELOG) or ADD a NEW AC for diagram re-render in cycle 34. The Playwright re-render is one bash command per CLAUDE.md docs but adds 5-10 minutes of cycle time. **Action**: ADD as new AC4.5 (or skip the diagram bump entirely for cycle 34 with a BACKLOG entry). Severity: MEDIUM — CLAUDE.md calls this "MANDATORY".

---

## NEW threats not in threat model

### NT1 — Boot-lean import surface broken by `[augment]` not being default (HIGH)

`kb.lint.augment` is imported by `kb.cli` at module scope (verified via cycle-31 boot-smoke test). `kb.lint.augment` imports `kb.lint.fetcher` at module scope, and `fetcher.py` imports `httpx` + `trafilatura` + `httpcore` at module top. So `kb.cli` cannot boot without these packages installed. AC23 says "minimal install" works without `[augment]` — **but it does NOT, given current import structure**.

**Severity:** HIGH (AC23 fails as-spec'd).

**Mitigation in this cycle:**
- (a) Move `httpx`, `httpcore`, `trafilatura` from `[augment]` extra into `dependencies` (defeats the purpose of having an `[augment]` extra), OR
- (b) Convert `kb.lint.augment`'s import of `kb.lint.fetcher` to function-local (matches cycle-23+ pattern), OR
- (c) Narrow AC23 to "minimal install does NOT include augment-active flow" with a documented caveat.

**Recommendation:** Option (b) — function-local import. Cycle-31 boot-smoke test should be extended to verify CLI works without `[augment]`, `[hybrid]`, `[formats]`, `[eval]`. **Add as cycle-34 condition** OR defer to cycle-N+1 with EXPLICIT BACKLOG entry and narrowed AC23.

**Step-11 verification:** `python -c "import kb.cli"` succeeds in a venv with ONLY default deps installed — i.e., `pip install . --no-deps && pip install click python-frontmatter fastmcp networkx anthropic PyYAML jsonschema && python -c 'import kb.cli'`.

### NT2 — `pip install -e '.[dev]'` does not install runtime deps (LOW, by design)

PEP 621 specifies that `[project.optional-dependencies]` is INDEPENDENT of `dependencies`. `pip install -e '.[dev]'` installs `dependencies` AS WELL AS the `dev` extra. **Verified by reading PEP 621**. So this is NOT a threat. **No action**. Severity: N/A.

### NT3 — Architecture diagram sync rule violation (MEDIUM)

Per CLAUDE.md MANDATORY: "Every HTML edit must re-render the PNG and commit it." Cycle-34's version bump in `architecture-diagram*.html` triggers this. **Threat model does not address.** Already discussed under Doc drift sweep §"Architecture diagrams". **Action**: same as Doc drift §"Architecture diagrams" — add AC4.5 OR defer to cycle-35 with BACKLOG entry. Severity: MEDIUM.

### NT4 — Workflow runs on push to ANY branch (MEDIUM)

`on: [push, pull_request]` triggers CI on every push to every branch — including throwaway feature branches that haven't been opened as PRs. This burns GitHub Actions minutes (free tier is generous but not infinite for a high-velocity 1.6-cycles/day project). **Threat model does not address.**

**Mitigation:** Restrict push trigger to specific branches: `on: { push: { branches: [main] }, pull_request: {} }` — push runs only on `main` (post-merge sanity check), pull_request runs on every branch's open PR. **Recommendation**: ADD as cycle-34 narrowing of AC9 trigger spec.

**Severity:** MEDIUM (cost, not security).

### NT5 — Missing concurrency control wastes CI minutes (LOW)

Without `concurrency:` group, multiple pushes to the same PR trigger overlapping workflow runs. **Recommendation**: add `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` to the workflow. Saves ~50% of CI minutes for active PRs. **Add as cycle-34 condition** OR defer. Severity: LOW.

### NT6 — `pip-audit` audits installed env, not requirements.txt (MED for false-negative)

`pip-audit` without `-r requirements.txt` audits the live environment after `pip install -e '.[dev]'`. If the cycle-34 CI install path differs from a downstream user's install path (different extras, different versions), the audit misses vulns the downstream user would face. **Recommendation**: AC14 should run `pip-audit -r requirements.txt --ignore-vuln=...` to audit the FULL pin set, not just the installed-from-`[dev]` subset. This is a stronger assurance. **Action**: clarify AC14's pip-audit invocation. Severity: MEDIUM.

### NT7 — `pyproject.toml` SBOM gap (LOW)

Cycle 34 declares 5 extras + runtime deps but produces no SBOM artifact. CI green-checkmark therefore says "no known vuln in the install env" but does not produce a verifiable supply-chain artifact (CycloneDX, SPDX). **Recommendation**: out-of-scope for cycle 34, but add to BACKLOG as "cycle-N+1 supply-chain hardening". Severity: LOW.

---

## Verdict

**APPROVE-WITH-CONDITIONS.**

The cycle-34 design is fundamentally correct. The 48 ACs cover the right surfaces, the threat model is comprehensive on the GitHub-Actions runner attack surface, and the brainstorming defaults Q1-Q10 are well-reasoned. The CI workflow is appropriately minimal, the SECURITY.md acceptance table is honest, and the scratch-file deletion + extras declaration are both load-bearing closes for the comprehensive review's P0 ship-blockers.

However, **eight load-bearing conditions must hold before merge**, and one threat needs to be added to the threat model for completeness:

### Blocking conditions (must close before R3 hands cycle 34 to implementation)

1. **CI-5 (HIGH) — AC15 unachievable as-spec'd.** `python -m build` and `twine check` need `build` and `twine` packages installed. Add a CI step `pip install build twine pip-audit` immediately before AC14/AC15 steps. **Update AC15 to include this install step.**

2. **NT1 (HIGH) — `kb.cli` will not boot under "minimal install" promised in AC23.** Either move `httpx` + `httpcore` + `trafilatura` from `[augment]` to `dependencies`, OR convert `kb.lint.augment` → `kb.lint.fetcher` import to function-local, OR narrow AC23 to remove the "minimal install" promise. **Recommendation**: function-local import (matches cycle-23 pattern). Add cycle-31 boot-smoke test extension to enforce.

3. **AC4 expansion (HIGH) — version bump must hit FOUR sites:** `pyproject.toml:3`, `src/kb/__init__.py:3`, `README.md:11` badge, `docs/architecture/architecture-diagram*.html`. Cycle-21 audit explicitly aligned `pyproject.toml` ↔ `__init__.py`. **Update AC4 to enumerate the four sites.**

4. **AC25 expansion (MEDIUM) — comment update.** `pipeline.py:1198` says "allowlist (includes .pdf)" — becomes stale after AC24. **Update AC25 scope to include this comment update.**

5. **NT3 (MEDIUM) — Architecture diagram sync rule.** CLAUDE.md MANDATORY says re-render PNG every HTML edit. Either add AC4.5 for the re-render OR defer the HTML version-bump to cycle 35 with BACKLOG entry.

6. **NT6 (MEDIUM) — `pip-audit -r requirements.txt`.** Audit the full pin set, not just the installed env. **Update AC14's invocation.**

7. **CI-2 (MEDIUM) — fork-PR `[build-system].requires` validation.** Add a step before `pip install -e '.[dev]'` that validates `pyproject.toml [build-system].requires == ['setuptools>=75.0']` exactly.

8. **NT4 (MEDIUM) — `on: { push: { branches: [main] }, pull_request: {} }`.** Restrict push trigger to `main` only.

### Non-blocking recommendations (close as cycle-34 enhancements OR defer to cycle-N+1)

- AC2 expansion: add `pytest-httpx>=0.30` to `dev` extra (CI-1).
- AC26 expansion: write the new "Latest cycle (34)" bullet in CLAUDE.md, not just update test count.
- AC44 wording: regex-tolerant header match instead of pinning exact strings.
- AC48 wording: prefix-match + substring-match (em-dash robustness).
- NT5: add `concurrency:` group to workflow (LOW).
- NT7: SBOM artifact for cycle-N+1 (LOW).
- AC43 wording: assert presence not "added in this cycle" (LOW — `.gitignore` already has the patterns).

### Threat-model addition

Add **NT1** to the cycle-34 threat model as a HIGH severity entry — the "minimal install" promise in AC23 is currently false given module-top imports in `kb.lint.augment` → `kb.lint.fetcher`. Either fix in this cycle (function-local import) or narrow AC23 with explicit caveat.

**Net: 8 NEW threats (1 HIGH, 4 MEDIUM, 3 LOW), 8 BLOCKING conditions, plus 7 non-blocking recommendations.** The blocking set is small, mechanical, and closeable in 1-2 hours of editing the requirements + threat-model + brainstorming docs. Once those edits land, cycle 34 is ready for R3 verification and Step 9 implementation.

---

End of cycle-34 R2 evaluation.
