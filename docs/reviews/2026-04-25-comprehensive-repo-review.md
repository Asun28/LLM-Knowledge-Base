# LLM Wiki Flywheel — Comprehensive Repository Review

**Date:** 2026-04-25 · **Branch:** `main` · **Version:** v0.10.0 · **Cycle:** 32 complete
**Reviewer scope:** actionable findings → PRD → architecture → implementation → tests → CI/CD → security → differentiation → innovation → advantages → disadvantages → risks → ways of working → fix plan.
**Boundary:** no source changes; only this document is produced. Prior draft at `docs/repo_review.md` is superseded by this review.

---

## 0. TL;DR

Serious, differentiated local-first knowledge-base system with deep implementation and a large test suite. Product idea is genuinely novel (compile-not-retrieve, MCP-native, Obsidian-native, trust-aware). The blocker is not capability — it is **product contract, dependency health, CI/CD, and doc hygiene**. The repo cannot be called release-ready today, but six focused fixes (≈2-3 cycles of work) would close that gap.

Maturity scorecard (1-10, review defensible):

| Area | Rating | One-line verdict |
| --- | ---: | --- |
| Product vision | 8 | Compile-not-retrieve + Karpathy-style structured wiki is a real thesis, not marketing. |
| PRD / product contract | 6 | Vision is strong; the public contract drifts across README, code, and backlog. |
| Architecture | 7.5 | Coherent three-layer model; ingest state fan-out and module size raise ownership risk. |
| Implementation | 7 | Many hardened primitives (SSRF, atomic writes, locks, path redaction); narrow leaks remain. |
| Code quality | 6.5 | Ruff-clean and disciplined, but 10 modules are 24-80 KB; config.py is a god-module. |
| Tests | 7 | 2901 collected (verified); volume is real, but no golden/snapshot tests for rendered output. |
| CI/CD | 2 | No root `.github/workflows` — all gates are local, enforced by developer discipline only. |
| Security | 6.5 | Strong SSRF / capture / subprocess controls; pre-ingest secret gate missing on main path; 4 unfixed CVEs in deps. |
| Differentiation | 8.5 | Real and defensible vs RAG, Obsidian vanilla, and the Karpathy gist. |
| Innovation | 8 | Trust+contradictions+evolve+publish stack + MCP-first is genuinely novel. |
| Release readiness | 4 | Dependency conflicts, drifting docs, no CI, and scratch files in repo root block a confident ship. |
| Ways of working | 7 | 17-step cycle workflow is disciplined; velocity is high (373 commits / 7 days) — verging on cycle overload. |

---

## 1. Actionable Findings (Leading)

Every finding is backed by a grep- or command-verifiable citation. `P0` = ship blocker, `P1` = maintainability, `P2` = positioning.

| # | Prio | Severity | Finding | Evidence |
| ---: | :---: | :---: | --- | --- |
| 1 | P0 | Critical | Dependency environment is broken: 3 pip conflicts, 4 unfixed CVEs | `pip check` + `pip-audit` runs below |
| 2 | P0 | High | No CI/CD — no `.github/workflows`, no enforced gate | `ls .github` → does not exist |
| 3 | P0 | High | Package `readme = "CLAUDE.md"` points at agent instructions | `pyproject.toml:6` |
| 4 | P0 | High | Partial-write MCP paths interpolate raw `OSError` — leak absolute Windows paths | `mcp/core.py:762`, `:881` vs sanitized siblings `:581`, `:616`, `:785` |
| 5 | P0 | High | Product contract drift: README says "No vectors" but v0.10 ships hybrid BM25+vector | `README.md:5` vs `README.md:384`, `src/kb/query/hybrid.py` |
| 6 | P0 | High | Test-count drift: badge says 2850; CLAUDE.md/CHANGELOG say 2901; actual collect = 2901 | `README.md:9` vs `CLAUDE.md:6`, live `pytest --collect-only` |
| 7 | P0 | High | PDF "support" is actually binary rejection — misleads users | `README.md:142`, `config.py:117`, `ingest/pipeline.py:1230,1233` |
| 8 | P0 | High | Main ingest path has no shared pre-LLM secret/PII filter (capture path does) | `capture.py:249-264, 771-779` vs `ingest/extractors.py:336-368` + `BACKLOG.md:219` |
| 9 | P1 | High | Scratch planning files live in repo root: `findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md` | `ls` root listing, all dated cycle-29 or earlier |
| 10 | P1 | High | Ingest has 11-stage side-effect fan-out with no whole-op recovery | `BACKLOG.md:83-84, 99-100` self-identified |
| 11 | P1 | Med-High | MCP tools are all sync `def`; FastMCP runs them on 40-thread pool | `BACKLOG.md:95-96`; `grep -n "@mcp.tool" src/kb/mcp/` shows no `async def` for long-I/O tools |
| 12 | P1 | Medium | 10 modules exceed 24 KB (`pipeline.py` 80 KB, `engine.py` 54 KB, `augment.py` 49 KB) | `du -b src/kb/**/*.py` |
| 13 | P1 | Medium | `config.py` is a 30 KB god-module with 35+ unrelated constants | `BACKLOG.md` Phase 4.5 MEDIUM |
| 14 | P1 | Medium | Zero golden/snapshot tests for structured output (llms.txt, graph, evidence trail, Mermaid, formats) | `grep -n "snapshot\|golden\|syrupy" tests/` → 0 hits |
| 15 | P2 | Medium | CLAUDE.md is 38 KB and doubles as PRD, onboarding, and runtime policy | `wc -l CLAUDE.md` = 343 lines |
| 16 | P2 | Medium | 251 decision docs in `docs/superpowers/decisions/` dominate the docs surface | `ls docs/superpowers/decisions/ \| wc -l` |
| 17 | P2 | Low-Med | `kb_save_synthesis` is conflated with `kb_query(save_as=...)` — a query call is also a write | `CLAUDE.md` line ~250, BACKLOG confirms 28 MCP tools, not 29 |
| 18 | P2 | Low | Optional features (`jsonschema`, `httpx`, `trafilatura`, `nbformat`, `model2vec`, `sqlite_vec`) not declared in `pyproject.toml`; all pulled via `requirements.txt` | `pyproject.toml:7-13` vs `requirements.txt` |

### Top 10 Detail

**Finding 1 — P0 Critical — Dependency environment is broken.**
- `pip check` reports three resolver conflicts:
  - `arxiv 2.4.1` requires `requests~=2.32.0`; installed `requests 2.33.0`.
  - `crawl4ai 0.8.6` requires `lxml~=5.3`; installed `lxml 6.1.0`.
  - `instructor 1.15.1` requires `rich<15.0.0,>=13.7.0`; installed `rich 15.0.0`.
- `pip-audit` reports four unfixed CVEs:
  - `diskcache 5.6.3` → CVE-2025-69872 (no upstream fix)
  - `litellm 1.83.0` → GHSA-xqmj-j6mv-4862 (fix `1.83.7`, blocked by transitive `click<8.2`)
  - `pip 26.0.1` → CVE-2026-3219 (no upstream fix)
  - `ragas 0.4.3` → CVE-2026-6587 (no upstream fix)
- **Fix:** Split dependencies into runtime / dev / eval / hybrid / augment / formats extras; remove `litellm` from default path or wait for its `click` pin to relax; accept the other three as documented narrow-role risks in a `SECURITY.md` with re-check cadence.
- **Effort:** 0.5 cycle.

**Finding 2 — P0 High — No CI/CD.**
- `ls .github` fails; the only `.github` directories live inside vendored skills (`.claude/skills/gstack/.github`, `.tools/ralph-claude-code/.github`) and are unrelated.
- No branch protection, no required checks, no enforced `ruff` / `pytest` / `pip check` / `pip-audit` / package-build gate.
- **Impact:** The 17-step cycle workflow's R1/R2 review gates are all model-driven and local; nothing stops a regression from landing on `main` if the agent misses it.
- **Fix:** `.github/workflows/ci.yml` with matrix `{py 3.12}`, steps: `ruff check`, `pytest --collect-only`, full `pytest`, `pip check`, `pip-audit`, `python -m build`.
- **Effort:** 0.25 cycle.

**Finding 3 — P0 High — Package `readme` points at agent instructions.**
- `pyproject.toml:6` → `readme = "CLAUDE.md"`. CLAUDE.md is 343 lines of internal runtime policy, not user onboarding.
- On PyPI / `pip show -v`, users would see the agent brief, not the marketing README.
- **Fix:** One-line change to `readme = "README.md"`. Add test via `python -m build && twine check dist/*`.
- **Effort:** 5 minutes (plus CI hook).

**Finding 4 — P0 High — Partial-write paths leak absolute paths.**
- `src/kb/mcp/core.py:762`:
  ```python
  f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); "
  ```
  The log-side (line 759) correctly passes `write_err` to `_sanitize_error_str`, but the return string interpolates it raw.
- Same pattern at `core.py:881` for `kb_save_source`.
- On Windows, `OSError.__str__()` typically reads `"[WinError 5] Access is denied: 'D:\\Projects\\...\\raw\\articles\\foo.md'"`. Cycle-32 AC3 widened `_is_mcp_error_response` to include `"Error["`, so this string is now routed to **operator stderr** under write-failure conditions.
- Cycle 32 Threat Model T11 already identified this; BACKLOG.md:146 tracks it.
- **Fix:** Two-line change — wrap `write_err` in `_sanitize_error_str(write_err, file_path)` at both sites. Add regression tests that assert no substring matches `str(Path.cwd().resolve())` in the returned `Error[partial]` response under a simulated `PermissionError`.
- **Effort:** 30 minutes.

**Finding 5 — P0 High — "No vectors" claim conflicts with hybrid search.**
- `README.md:5`: "No vectors. No chunking."
- `README.md:155`: `kb rebuild-indexes ... deletes the hash manifest + vector DB`.
- `README.md:384`: v0.10.0 ships "hybrid search with RRF fusion (BM25 + vector via `model2vec` + `sqlite-vec`)".
- `src/kb/query/engine.py:1` docstring: "BM25 + vector hybrid search + LLM synthesis".
- `src/kb/query/hybrid.py:1`: "RRF fusion of BM25 + vector".
- **Fix:** Replace the tagline with accurate positioning — *"Markdown-first wiki with optional hybrid retrieval"* — and add an **Opt-out guide** documenting how to disable vector search (set `model2vec`/`sqlite_vec` extras off, delete `.data/vectors.db`, short-circuit `kb.query.hybrid`).
- **Effort:** 2 hours (copy + guide + test that `--no-vectors` path is covered).

**Finding 6 — P0 High — Test-count drift.**
- Live: `pytest --collect-only -q` → **2901 tests**.
- `CLAUDE.md:6`: 2901. `CHANGELOG.md` cycle 32: 2901. Internally consistent.
- `README.md:9` badge: **tests-2850**. `README.md:339/352/366/385` reference historical counts (1033, 1177, 2850) in narrative v-milestone summaries.
- **Impact:** The first number a prospective user sees is wrong by 51, which is small in absolute terms but large in credibility.
- **Fix:** Generate the badge in CI from `pytest --collect-only -q | tail -1`, or drop exact numbers from the badge (use `tests-passing`). Stop citing exact counts in narrative text.
- **Effort:** 15 minutes plus CI hook.

**Finding 7 — P0 High — PDF support is advertised but absent.**
- `README.md:142`: "PDF `.pdf` supported by the compile pipeline".
- `src/kb/config.py:117` includes `.pdf` in `SUPPORTED_SOURCE_EXTENSIONS`.
- `src/kb/ingest/pipeline.py:1230` reads the file as UTF-8; `pipeline.py:1233` returns `"Binary file cannot be ingested"` when the decode fails.
- Net behavior: drag a real PDF in → error message. There is no PDF text extraction.
- **Fix:** Either (a) remove `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` and update `README.md` to say "convert PDF with `markitdown` or `docling` first", or (b) implement a real PDF extractor with size + page caps and tests. (a) is 20 minutes; (b) is 1 cycle.
- **Effort:** 20 minutes (option a, recommended).

**Finding 8 — P0 High — Main ingest path has no shared pre-LLM secret/PII filter.**
- `src/kb/capture.py:249-264` defines `_SECRET_PATTERNS` + decoded-base64 candidate checks; `capture.py:771-779` aborts with `CaptureError` when matched.
- `src/kb/ingest/extractors.py:336-368` builds the extraction prompt by concatenating raw source content; no secret scan before `call_llm_json(prompt, tier, schema)`.
- `BACKLOG.md:219` explicitly lists `.llmwikiignore` + pre-ingest secret/PII scanner as missing. `BACKLOG.md:293-294` notes every ingest sends full content to the API.
- **Fix:** Extract `_scan_for_secrets` from `capture.py` into `kb/utils/secrets.py`. Call it at the top of `ingest_source` and `compile_wiki`. Add `.llmwikiignore` reader. Default deny with `--allow-scanned-secrets` override.
- **Effort:** 1 cycle.

**Finding 9 — P1 High — Scratch planning files in repo root.**
- `findings.md` (1082 B, cycle-29 Step 11 scratch)
- `progress.md` (239 B, cycle-29 scratch)
- `task_plan.md` (345 B, cycle-29 scratch, still says `[in_progress] Synthesize T1-T3 verdicts`)
- `claude4.6.md` (40 KB, an older copy of `CLAUDE.md` — pre-Opus-4.7 rename)
- These are not in `.gitignore` (confirmed: `.gitignore` does not list them) yet they persist across merges.
- **Impact:** Visible in `git status`, clutters the project root for first-time visitors, and `claude4.6.md` will diverge from `CLAUDE.md` silently.
- **Fix:** Move scratch to `.data/` or delete; add `findings.md progress.md task_plan.md` to `.gitignore`; delete `claude4.6.md` or move to `docs/archive/`.
- **Effort:** 10 minutes.

**Finding 10 — P1 High — Ingest state fan-out is unrecoverable.**
- `BACKLOG.md:83-84` itself describes the 11-stage fan-out: summary page → N entity pages → N concept pages → `index.md` → `_sources.md` → `.data/hashes.json` → `wiki/log.md` → `wiki/contradictions.md` → N retroactive wikilink injections. Every stage is atomic individually; the operation as a whole is not.
- `BACKLOG.md:99-100` (R5) highlights systemic absence of locking discipline across the 11-stage pipeline.
- A crash between manifest-write (step 6) and log-append (step 7) leaves manifest saying "already ingested" while the log shows nothing; a mid-wikilink-injection crash leaves partial retroactive backlinks.
- **Fix:** Implement the backlog's receipt-file recipe (`.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass replays partials). Introduce `with page_lock(page_path):` helper used consistently across `_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`, and `inject_wikilinks`.
- **Effort:** 1-2 cycles.

---

## 2. PRD / Product Contract Review

### 2.1 What the repo claims (aggregate)

From `README.md`, `CLAUDE.md`, and `CHANGELOG.md`:

- **Promise:** drop a source in, Claude extracts entities/concepts/claims, wiki pages get created, wikilinks inject retroactively, trust scores update, contradictions flag.
- **Non-RAG identity:** "No vectors. No chunking." (`README.md:5`).
- **Obsidian-native** — open `wiki/` as a vault; graph view for free.
- **MCP-first** — 28 tools; "no API key needed" in Claude Code mode.
- **Publishable** — Karpathy Tier-1 `/llms.txt`, `/llms-full.txt`, `/graph.jsonld`, sitemap, per-page siblings.
- **Self-healing** — Bayesian trust, contradiction detection, staleness flags, dead-link lint.

### 2.2 Contract drift (what breaks the promise)

| Contract claim | Code reality |
| --- | --- |
| "No vectors" (`README.md:5`) | `query/hybrid.py`, `query/embeddings.py`, `model2vec` + `sqlite-vec` runtime deps |
| "PDF supported" (`README.md:142`) | `ingest/pipeline.py:1233` rejects binary PDFs |
| "Tests: 2850" badge | Actual 2901 |
| "No API key needed" | True for MCP with Claude Code; false for CLI `kb compile` / `kb query` without `--use-api=False`; false for `output_format=...` adapters |
| Package `readme = "CLAUDE.md"` | CLAUDE.md is agent instructions, not user onboarding |
| 28 MCP tools (README) | Accurate — but `kb_save_synthesis` is NOT a tool, it is `kb_query(save_as=...)`, which conflates read and write. BACKLOG.md:152 notes this. |
| "Optional: install `ANTHROPIC_API_KEY`" | `pyproject.toml:7-13` lists `anthropic>=0.7` as a **required** dep; package imports fail without it |

### 2.3 Missing PRD artifacts

The repo has:
- 40 KB CLAUDE.md (agent policy + project runtime guide)
- 70 KB BACKLOG.md (open work)
- 26 KB CHANGELOG.md (brief index)
- 277 KB CHANGELOG-history.md (per-cycle detail)
- 251 decision docs in `docs/superpowers/decisions/`
- 27 KB README.md (user-facing)

What it is missing:
1. **Stable PRD** — a ≤500-line spec that says who the user is, what the product promises, what it does NOT do, and what the release criteria are. Separate from cycle history.
2. **Product contract tests** — pytest files that assert the promises (PDF, vectors, extras, API key).
3. **User personas** — solo researcher vs Claude-Code user vs docs maintainer vs team knowledge owner. Today's README implicitly targets only Claude-Code power users.
4. **"What is NOT this"** — single-page non-goals list. This clarifies why it's not Notion AI, not a RAG platform, not a generic DMS.
5. **Release checklist** — shipped as cycle-step workflow but not as a PRD-level gate (docs, tests, CI, deps, migrations).

**Recommendation:** create `docs/prd/v0.10.md` (≤300 lines) as the single source of truth for product promises. Make `README.md` derive from it. Move test counts, cycle history, and roadmap out of the PRD.

---

## 3. Architecture Review

### 3.1 Three-layer content model

```
raw/           (human-owned, immutable)
  ├── articles, papers, videos, repos, podcasts, books, datasets, conversations, assets
  └── captures/   (sole LLM write into raw/; atomised by kb_capture)
wiki/          (LLM-owned, editable by user)
  ├── entities/, concepts/, comparisons/, summaries/, synthesis/
  ├── index.md, _sources.md, _categories.md, log.md, contradictions.md
research/      (human-owned analysis + meta-research)
```

Strong property: the **durable artifact is Markdown** — not an embedding, not a proprietary DB. The user can always read, version, and fork.

### 3.2 Five-operations cycle

```
Ingest ──→ Compile ──→ Query
  │                       │
  └── Evolve ←── Lint ←───┘
```

All five are defined in `CLAUDE.md` and mapped to CLI + MCP surfaces. Cleanly separable, but Compile is thin today — `compile/compiler.py:compile_wiki` is a ~50-line loop over `ingest_source`. BACKLOG.md:155 calls out that "Compile" does not currently perform cross-source reconciliation; the name is aspirational.

### 3.3 Module layout (`src/kb/`)

72 `.py` files, 21,593 LOC total. Top 15 by size:

| Module | KB | Role | Concern |
| --- | ---: | --- | --- |
| `ingest/pipeline.py` | 80 | 11-stage ingest orchestration | Too much in one file; stateful |
| `query/engine.py` | 54 | BM25 + hybrid + synthesis + output | Mixes retrieval + rendering |
| `lint/augment.py` | 49 | Three-gate augment + rate limit + manifest | OK but dense |
| `mcp/core.py` | 47 | Ingest/query/capture MCP tools | 28 tools in 4 files; this is the biggest |
| `cli.py` | 42 | 24 CLI commands | Grows linearly per cycle |
| `lint/checks.py` | 41 | Dead links, orphans, staleness | OK |
| `compile/compiler.py` | 37 | Batch ingest + rebuild-indexes | Misleadingly named |
| `capture.py` | 36 | Conversation atomization | Has the secret scan that others need |
| `query/embeddings.py` | 33 | `model2vec` + `sqlite-vec` + cold-load warmup | Hybrid optionality not enforced |
| `config.py` | 30 | 35+ unrelated constants | God-module |
| `compile/linker.py` | 25 | Wikilink injection | OK |
| `mcp/quality.py` | 25 | Refine/review/verdicts tools | OK |
| `lint/fetcher.py` | 24 | SSRF-hardened HTTP | **Model citizen — exemplar** |
| `compile/publish.py` | 24 | Karpathy Tier-1 output builders | OK |
| `review/refiner.py` | 22 | Two-phase pending→applied flip | OK, good discipline |

### 3.4 Strengths

- Raw→wiki→publish is easy to explain in 90 seconds.
- Markdown-as-artifact is a strong architectural anchor.
- CLI + MCP split avoids locking users into an agent shell.
- Many reliability primitives already exist: `utils/io.py::file_lock`, `atomic_json_write`, `utils/sanitize.py`, `errors.py` taxonomy, dual-anchor `_validate_path_under_project_root`.
- Observability counters (dim_mismatch, bm25_build, cold_load, sqlite_vec_load) are a small but real operational commitment.

### 3.5 Concerns

- Directory names misalign: `compile/` depends on `ingest/`, but the README positions compile as the orchestrator. BACKLOG.md HIGH item at line 80-82 calls this "naming inversion".
- Ingest state fan-out has no whole-op recovery (Finding 10).
- No shared caching policy for the graph layer — lint and query each rebuild PageRank separately.
- MCP tools are all sync; FastMCP thread-pool pressure is real for `kb_query(use_api=True)` and `kb_compile()`.
- Optional features (vector, formats, augment, cli-backends) are not package-isolated.

### 3.6 Recommendation

Freeze six contracts and gate them with pytest:

1. **Source ingestion contract** — input types, size caps, returned shape.
2. **Wiki page schema contract** — frontmatter fields (required/optional), validator.
3. **Query result contract** — `{answer, citations[], source_pages, output_path?}`.
4. **Publish artifact contract** — llms.txt, llms-full.txt, graph.jsonld, siblings, sitemap shapes.
5. **Error response contract** — MCP strings never contain absolute paths; CLI exit codes map.
6. **Dependency extras contract** — `pip install llm-wiki-flywheel` succeeds with only the default deps; each optional feature lives behind a named extra.

Then refactor modules behind the contracts, not before.

---

## 4. Implementation Review

### 4.1 Exemplary patterns to preserve

- **SSRF hardening** — `src/kb/lint/fetcher.py` uses `SafeTransport`, per-request allowlists, private/reserved IP rejection, and validates every redirect.
- **Subprocess safety** — `src/kb/utils/cli_backend.py` avoids `shell=True`, prefers stdin prompt delivery, rejects token-shaped argv, and redacts output.
- **Pre-LLM secret scan (capture only)** — `src/kb/capture.py:249-264, 771-779`. The pattern is right; it just isn't shared.
- **Centralised redaction** — `src/kb/utils/sanitize.py`. Used by most MCP error paths (see `mcp/core.py:581, 616, 785, 842`).
- **Dual-anchor path validation** — `_validate_path_under_project_root(path, field_name)` shipped cycle 29.
- **Atomic writes** — `utils/io.py::atomic_text_write` + `atomic_json_write`; temp-file + `os.replace`.
- **File locks with fair-queue stagger** — cycle 32 AC6 added `_LOCK_WAITERS` counter + position-based stagger clamped to `LOCK_POLL_INTERVAL`. Intra-process mitigation (not cross-process), but a real primitive.
- **Exception taxonomy** — `kb.errors` defines `KBError` + 5 specialisations; `StorageError.__str__` redacts paths; `LLMError`/`CaptureError` reparent cleanly.
- **Observability counters** — four getters (`get_dim_mismatch_count`, `get_bm25_build_count`, `get_vector_model_cold_load_count`, `get_sqlite_vec_load_count`) plus structured `logger.info`/`logger.warning` at cold-load sites.
- **Extraction schema cache** — LRU-cached via `_build_schema_cached(source_type)` to avoid deepcopy on every ingest.

### 4.2 Weaknesses

- **Packaging vs runtime** — `pyproject.toml:7-13` declares 6 runtime deps; `src/kb` imports `jsonschema`, `httpx`, `trafilatura`, `nbformat`, `model2vec`, `sqlite_vec`. A clean `pip install .` from metadata breaks advertised features.
- **Large modules** — 10 modules > 24 KB; `config.py` is a god-module.
- **Implementation-coupled tests** — ~50 of 253 test files are named `test_v0NNN_taskNN.py` / `test_phase4_audit_*.py`; canonical module-level test files are small.
- **No golden / snapshot tests** — grep returns zero hits for `snapshot|golden|syrupy|inline_snapshot`.
- **Doc-code drift** — test counts, "No vectors", PDF support, 28 vs 29 MCP tools, required vs optional API key.
- **Stray scratch** in repo root (Finding 9).

### 4.3 Function-local import pattern

Cycles 23-32 introduced function-local imports to preserve boot-lean contracts (importing `kb.cli` must not transitively pull `kb.mcp.browse`/`kb.mcp.quality`). Subprocess-probe tests in cycle 31 pin the contract. This is a disciplined choice, but it creates a subtle trap: **patching must target the owner module** (`kb.mcp.browse.kb_search`), not `kb.cli.kb_search`. CLAUDE.md explicitly documents this. New contributors will get the wrong one on the first try.

**Recommendation:** add a `tests/test_boot_lean.py` that import-parses `kb.cli` in a subprocess and asserts only the allow-listed set is loaded. This is already done for cycle 31 — promote it into a permanent guard so future CLI additions cannot silently regress.

---

## 5. Tests Review

### 5.1 Scale

- **Collected:** 2901 tests (verified live 2026-04-25).
- **Files:** 253 in `tests/`.
- **Source:** 72 `.py` in `src/kb/` → test:source ratio ≈ 3.5 files per source file.
- **Runtime:** 144 s for full suite (cycle 32 CI gate, per memory S6584).

### 5.2 Strengths

- Exercises security edge cases (path traversal, Windows reserved filenames, 255-char ceiling).
- Cycle-specific regression files preserve history.
- AST-scan enforcement (`test_cycle19_lint_redundant_patches.py`) catches fixture drift.
- Boot-lean subprocess probe (cycle 31) — a test that enforces architectural contracts.
- Fixtures (`tmp_wiki`, `tmp_project`, `tmp_kb_env`) are real sandboxes.

### 5.3 Gaps

- **No golden/snapshot tests.** `assert "X" in output` does not catch rendered-Markdown drift. Phase 5's output adapters (`marp`, `html`, `chart`, `jupyter`) produce structured output that LLM-prompt tweaks will silently reformat.
- **Fixture leak surface.** `conftest.py`'s `project_root`, `raw_dir`, `wiki_dir` point at the REAL project; nothing enforces read-only usage. BACKLOG.md Phase 4.5 HIGH identifies five leak paths (`WIKI_CONTRADICTIONS`, `load_purpose`, `append_wiki_log`, `hot.md`, `_schema.md`).
- **Versioned test files are hard to navigate.** Verifying `evolve/analyzer.py` coverage requires grepping ~50 `test_v0NNN` files because canonical `test_evolve.py` has only 11 tests. BACKLOG HIGH R3 flags this.
- **No coverage gate.** No `coverage.py` in pipeline; no per-module % reporting.
- **No mutation testing.** Given the claim density (trust, contradictions, retroactive injection), a `mutmut` or `cosmic-ray` run on the hot paths would quickly show which tests are signature-only.
- **No contract tests for package extras.** No pytest asserts that `pip install llm-wiki-flywheel` (no extras) can import `kb.cli` and run `kb --version`.

### 5.4 Recommendation

Add in this order:

1. **Boot-smoke** — `pip install .` in a clean venv; `kb --version`; no ImportError.
2. **Golden tests** with `syrupy`: frontmatter render, evidence-trail format, Mermaid export, lint report, llms.txt, graph.jsonld, per-page sibling JSON.
3. **Fixture leak guard** — autouse monkeypatch of all `WIKI_*`/`RAW_*` constants to `tmp_path`; opt-in `--use-real-paths` for integration runs.
4. **Coverage gate in CI** — track per-module %; fail PR if any module drops ≥2 pp.
5. **Freeze-and-fold rule** — after a version ships, fold its tests into canonical module files.

---

## 6. CI/CD Review

**Current state:** none. Confirmed via `ls .github` (does not exist). Only `.github` directories in the tree are inside vendored skill bundles.

All quality gates today are local + agent-run:
- R1 Opus review (design eval, plan gate)
- R2 Codex review (design eval, plan gate) — often hangs and falls back to primary-session synthesis (cycle-20 L4 lesson)
- R3 Sonnet verification
- Manual `pytest` + `ruff` before commit
- Manual `pip-audit` (per Step 2 baseline + Step 11 PR-CVE diff + Step 11.5 existing-CVE patch + Step 15 late-arrival warn)

### Recommended minimum pipeline

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e '.[dev]'
      - run: ruff check .
      - run: pytest --collect-only -q
      - run: pytest -q
      - run: pip check
      - run: pip install pip-audit && pip-audit --strict
      - run: python -m build && pip install twine && twine check dist/*
  extras-smoke:
    strategy: { matrix: { extra: [hybrid, augment, formats, cli-backends] } }
    steps: [...install with extras only, run smoke...]
  windows-smoke:
    runs-on: windows-latest
    steps: [...minimal `kb --version` and path-redaction tests...]
```

Gate `main` on `test`. Run `extras-smoke` and `windows-smoke` nightly. **Effort:** 0.5 cycle for a working-but-minimal CI; 1 cycle for full matrix.

### Release automation

Today `CHANGELOG.md` is hand-maintained with a commit-count convention documented in the format guide. A CI step could verify `<K>` equals `git log --oneline main..HEAD | wc -l + 1` before merge. Cycle 28 AC8 documented the rule; automating it would prevent drift (commit-count backfills were needed in cycles 30 and 32).

---

## 7. Security Review

### 7.1 Strong controls

- SSRF-aware fetcher with private-IP rejection and redirect revalidation.
- Subprocess backend without `shell=True`; stdin prompt delivery; argv token rejection; output redaction.
- Capture-path pre-LLM secret scan with decoded-base64 candidates.
- Path traversal validated at MCP boundary (`_validate_page_id`) AND library level (`_validate_path_under_project_root`, dual-anchor).
- `StorageError.__str__` redacts paths when `kind` + `path` are set.
- Atomic writes across all JSON stores (feedback, verdicts, lint manifests, augment manifest).
- Exception taxonomy prevents information disclosure through uncaught `Exception`.
- `kb_query(save_as=...)` validates against `[a-z0-9-]+`; rejects Windows reserved names, traversal, Unicode homoglyphs.
- Cycle 20 slug-collision hardening: `O_EXCL|O_NOFOLLOW` + poison-unlink on concurrent summary writes.

### 7.2 Material gaps

| Gap | Severity | Evidence | Fix |
| --- | :---: | --- | --- |
| Main ingest path has no pre-LLM secret/PII filter | High | `ingest/extractors.py:336-368` vs `capture.py:249-264` | Extract `_scan_for_secrets` → `utils/secrets.py`; share across ingest/capture/compile; add `.llmwikiignore` |
| Partial-write MCP errors leak absolute paths | High | `mcp/core.py:762, 881` | Wrap `{write_err}` in `_sanitize_error_str(..., file_path)` |
| 4 unfixed CVEs in deps (1 fixable at 1.83.7 but blocked by click transitive) | High | `pip-audit` | Dep extras; narrow-role SECURITY.md |
| No CI security gate | High | no `.github/workflows/` | CI with `pip-audit --strict` |
| No rate limit on MCP `kb_ingest_content` | Medium | grep for rate-limit in `mcp/core.py` → hit only in capture path | Add per-process sliding-window limiter like `lint/_augment_rate.py` |
| Augment `auto_ingest=True` with `confidence: speculative` writes to disk from external fetch | Medium | `lint/augment.py` three-gate flow | Already gated behind opt-in flag; document the threat model |
| `CHANGELOG-history.md` at 277 KB is unversioned security-relevant history | Low | size check | Fine as-is; worth rotating at 500 KB |

### 7.3 Dependency CVE table (live pip-audit 2026-04-25)

| Package | Version | Advisory | Fixed in | Narrow role? |
| --- | --- | --- | --- | --- |
| `diskcache` | 5.6.3 | CVE-2025-69872 (pickle RCE) | none | Yes — trafilatura's robots.txt cache; zero direct imports in `src/kb` |
| `litellm` | 1.83.0 | GHSA-xqmj-j6mv-4862, GHSA-r75f-5x8p-qvmc | 1.83.7 | Yes — dev-eval (ragas harness); zero runtime imports; proxy mode never started |
| `pip` | 26.0.1 | CVE-2026-3219 | none | Yes — tooling only; not runtime |
| `ragas` | 0.4.3 | CVE-2026-6587 (SSRF) | none | Yes — dev-eval only; zero runtime imports |

Each is defensible as a narrow-role exception. The real fix is to split extras so the default install doesn't include them.

---

## 8. Differentiation

### 8.1 vs generic RAG

| | RAG | This Project |
| --- | --- | --- |
| Durable artifact | Vector DB | Markdown pages (user-readable, git-able) |
| Unit of knowledge | Chunk | Entity / concept / summary page with frontmatter |
| Relationships | None (latent in embeddings) | `[[wikilinks]]` + NetworkX graph + PageRank |
| Contradiction handling | Returns conflicting chunks silently | `contradictions.md` + `kb_lint_consistency` |
| Gap awareness | None | `kb_evolve` proposes missing pages |
| Updating | Re-embed | SHA-256 diff → only changed sources recompiled |
| Output format | JSON / prose | Markdown + optional Marp / HTML / chart / Jupyter |
| Agent surface | API | 28 MCP tools |
| Ownership | DB file | Markdown files in git |

**Net:** this is a structurally different answer to the same problem. The value bet is that *structure wins long-term over vectors for personal/team knowledge*.

### 8.2 vs Karpathy's gist

The gist is a manual pattern ("ask Claude to write pages"). This project is a **compiled automation** of that pattern with retroactive linking, trust scoring, contradiction tracking, evolve loop, and Tier-1 publish outputs. The `demo/` folder ships a concrete worked example from Karpathy's own X post so the reader can see what the pipeline actually produces.

### 8.3 vs vanilla Obsidian vault

Obsidian is a UI over Markdown with a graph view. It does not ingest, compile, or synthesize. This project writes to the same vault format, so a user can **adopt Obsidian for free** after `kb compile`. The "meet users where they are" move is genuinely strong.

### 8.4 vs commercial KB tools (Notion AI, Mem, Reflect, Tana)

- **Local-first** — all data on disk, git-able, offline-capable.
- **User-owned formats** — Markdown + YAML; no lock-in.
- **LLM-agnostic** — Claude, Ollama, Gemini CLI, OpenCode, Codex CLI via `KB_LLM_BACKEND`.
- **Agent-native** — 28 MCP tools integrate with Claude Code natively.
- **Lower polish** — no mobile app, no shared workspace, no real-time collab, no enterprise SSO. Clearly a developer/researcher tool, not an enterprise product.

### 8.5 Where differentiation is currently weakened

- "No vectors" claim (Finding 5) undermines the pitch when a user sees `model2vec` in requirements.
- PDF support is advertised but absent (Finding 7).
- Heavy install surface (crawl4ai, playwright, ragas, litellm, etc.) belies the "simple Markdown wiki" story.
- 32 cycles + 251 decision docs in 20 days imply high churn, which can feel incompatible with the "trusted personal KB" positioning.

---

## 9. Innovation

Genuinely novel contributions (beyond the Karpathy gist):

1. **Retroactive wikilink injection.** When a new source mentions entity X, existing pages that mention X get auto-linked — without re-ingesting them. Implemented in `compile/linker.py:inject_wikilinks_batch` with per-page locks + chunked 200-title batches + per-title 500-char cap. This is the move that makes the flywheel real.
2. **Incremental compile with crash safety.** SHA-256 hashes + three-valued manifest (`real_hash` / `failed:{pre_hash}` / `in_progress:{pre_hash}`) + crash-resume audit. `compile/compiler.py`.
3. **Trust = Bayesian + feedback-driven.** "Wrong" penalised 2× vs "incomplete"; per-page posterior updated by `kb_query_feedback`. `feedback.py`.
4. **Two-phase refine with audit trail.** `review/refiner.py` writes a `pending` row, mutates the page body, then flips to `applied` or `failed` under `file_lock(history_path)`. Lock order documented (page first, history second). Cycle-20 attempt-id + cycle-21 sweep-by-attempt-id hardening makes this robust to partial crashes.
5. **Actor-Critic wiki review.** `.claude/agents/wiki-reviewer.md` + `kb_review_page` with structured 6-item checklist. Not just "a chatbot reads a page".
6. **Boot-lean contract.** Function-local imports at CLI→MCP boundaries, enforced by a subprocess probe test (cycle 31). This is an architectural invariant pinned by a test.
7. **Evidence Trail sentinel pattern.** Append-only reverse-chronological section within each page, sentinel-guarded, with inline render on first write and append thereafter. A lightweight audit trail that lives WITH the artifact, not alongside it.
8. **Publish-ready outputs.** `compile.publish` ships `llms.txt`, `llms-full.txt`, `graph.jsonld`, sitemap, and per-page `.txt`/`.json` siblings — the Karpathy Tier-1 machine-consumable stack. This is the first tool I've seen that makes that happen from a single command.
9. **Output adapters outside `wiki/`.** `PROJECT_ROOT/outputs/` is gitignored and separate from the search index — a small decision that prevents adapter output from poisoning future queries. Small but thoughtful.
10. **Fair-queue lock stagger (cycle 32).** `_LOCK_WAITERS` counter + position-based first-sleep stagger inside `file_lock`. Intra-process mitigation; clamped to `LOCK_POLL_INTERVAL` so it cannot double-compound with exponential backoff. Counter guarded by `slot_taken` + `KeyboardInterrupt`-safe. Not a cross-process guarantee, but a real primitive.

Lesser but still noteworthy:
- Stub deferral for short sources (< 1000 chars) prevents entity-page explosion.
- `kb_capture` atomises unstructured text into discrete items with secret scan + rate limit.
- Per-source `alongside_for[i]` in capture's two-pass write is a design limitation explicitly called out as `v1` — transparent tech debt beats hidden tech debt.

---

## 10. Advantages

- **Markdown-first.** The durable artifact is human-readable, git-able, forkable.
- **Obsidian-native.** Free graph view, backlinks, hover preview.
- **CLI + MCP parity** — scripting and agent workflows share a core.
- **28 MCP tools** in Claude Code; "no API key needed" for the main flow.
- **Local-first.** Works offline with `KB_LLM_BACKEND=ollama` / `gemini-cli` / etc.
- **Incremental + crash-safe compile.** Hash-based change detection; in-progress markers.
- **Trust + contradictions + evolve** stack is meaningfully more than RAG-as-a-library.
- **Strong security primitives** for the paths that have them (SSRF, subprocess, capture, path redaction).
- **High test volume** — 2901 tests run in 144 s.
- **Karpathy Tier-1 publish outputs** from one command.
- **Honest cycle history** — every decision is archived under `docs/superpowers/decisions/`.

## 11. Disadvantages

- **Install is heavy.** `requirements.txt` pulls crawl4ai, playwright, ragas, litellm, diskcache — far more than the "simple Markdown wiki" story.
- **Package metadata is wrong.** `readme = "CLAUDE.md"`; only 6 runtime deps declared despite imports of 6+ more.
- **No CI.** Every gate is local and agent-run.
- **Docs disagree with code** (vectors, PDF, test count, API-key optionality).
- **Modules are large.** Ten >24 KB; `config.py` is a god-module.
- **Tests are versioned, not folded.** Locating canonical coverage requires grepping ~50 `test_v0NNN` files.
- **No golden tests** for structured output.
- **High cycle velocity** — 373 commits in the last 7 days — which can leave docs and tests behind.
- **Onboarding friction.** Python + venv + Claude Code + MCP + Obsidian is a lot to ask before value is visible.
- **CLAUDE.md is 38 KB** and doubles as PRD, onboarding, and runtime policy.
- **Scratch files in repo root** (Finding 9) signal lax hygiene to first-time visitors.
- **Windows-first workflow.** Developer clearly works on Windows (paths, forward-slash notes in `CLAUDE.md`); Unix users may hit edge cases less covered.

## 12. Risks

- **Trust risk.** LLM extraction can hallucinate, omit nuance, or overstate certainty. Current mitigation (trust scoring + contradictions + actor-critic) is strong but not infallible.
- **Privacy risk.** Main ingest path sends full content to an API without pre-ingest secret/PII scanning (Finding 8). A user can accidentally leak credentials, medical notes, or client data.
- **Dependency risk.** Broad optional-feature surface increases CVE and resolver pressure. 4 open CVEs right now.
- **State-consistency risk.** 11-stage ingest with no whole-op recovery (Finding 10).
- **Scaling risk.** Markdown filesystem + graph rebuilds + index updates will slow at 10k+ pages. No measured benchmark exists.
- **Onboarding risk.** The mental-model stack is high.
- **Maintenance risk.** Cycle-driven development has left stale scratch files, drifting test counts, and contradictions in README.
- **Product-claim risk.** "No vectors" and "PDF supported" are load-bearing differentiators that current code does not honor.
- **Supply-chain risk.** Running `crawl4ai` + `playwright` against arbitrary user-supplied URLs in augment `execute=True` mode is a real attack surface if the fetcher allowlist is weakened.
- **Lock contention risk.** File locks are not re-entrant and require documented acquire order (page first, history second). A new contributor will violate this on day one.
- **Vendor-lock subtlety.** "No API key needed" is true in Claude Code mode; false in CLI without `use_api=False`; false with `output_format=...` adapters. Partial vendor-lock is harder to explain than full independence.

## 13. Ways of Working

This is the section most reviews miss. It matters here because the *meta-process* is as distinctive as the product.

### 13.1 17-step cycle workflow

Documented in `CLAUDE.md` header, `memory/feedback_*.md`, and the prior memory observations. Each cycle shipped:

1. Requirements gathering
2. Threat modeling
3. Brainstorming (optional)
4. Design evaluation (R1 Opus + R2 Codex in parallel)
5. Design decision gate (R1/R2 synthesis → final verdict)
6. Context7 doc verification (optional)
7. Implementation plan
8. Plan gate (Codex verifies coverage matrices + condition + task completeness)
9. TDD implementation
10. CI hard gate (full `pytest`)
11. Security verification (threat-model grep conditions)
11.5 Existing-CVE patch (optional)
12. Documentation update
13. PR creation
14. Multi-round PR review (R1 Opus + R1 Sonnet + R1 Codex, then R2, then R3 if ≥25 items)
15. Merge + cleanup
16. Self-review with skill patching (MANDATORY)

### 13.2 Evidence of discipline

- `docs/superpowers/decisions/` contains **251 decision docs** — one or more per step per cycle, spanning 20 days.
- 788 total commits on `main`; 373 in last 7 days → ~53 commits/day average recently.
- 32 cycles shipped since project init on 2026-04-05 (20 days) → **1.6 cycles / day**.
- Each cycle produces ~4 artifacts: design, plan, PR review, self-review.
- Memory includes codified feedback rules (`memory/feedback_*.md`) that become part of future cycle behavior — 18 feedback entries as of today.
- Skill patches are mandatory in Step 16 — bugs become process improvements.

### 13.3 Strengths of this way of working

- **Explicit gates.** Design + plan + CI + security each have independent review.
- **Multi-model adversarial review.** Opus + Codex + Sonnet catch different classes of bugs.
- **Self-modifying process.** Skill patches create compounding quality.
- **Audit trail is the product.** Every decision is archived; you can reconstruct why anything was done.
- **Explicit lesson codification.** `feedback_*.md` rules ("batch by file", "test behavior not signature", "ruff autofix can remove monkeypatched imports") are hard-won and captured.
- **Auto-approve all gates** — single developer + sub-agent approvers, so cycles don't stall on human-in-the-loop.

### 13.4 Risks of this way of working

- **Cycle overload.** 1.6 cycles/day is very high. CHANGELOG-history.md is 277 KB; CHANGELOG.md is 26 KB; BACKLOG.md is 70 KB. Someone who joins tomorrow has to read a lot before shipping.
- **Decision-doc sprawl.** 251 docs in one folder without categorisation make lookup expensive. Consider subfolders by cycle range (`decisions/cycles-01-10/`, etc.).
- **Process is the product.** CLAUDE.md is 38 KB and largely describes the workflow, not the product. The tradeoff is real — the workflow is a competitive advantage, but it has crowded out the PRD.
- **Agent reviewers hang.** Cycle 32 notes R2 Codex hung past 12 min and R1 Opus past 10 min (CHANGELOG.md:76-84). The cycle-20 L4 lesson ("primary-session synthesis fallback on agent hang") is a workaround, not a fix.
- **Sonnet-4.6 versioning artifact** — `claude4.6.md` in repo root (Finding 9) is a legacy pre-4.7 copy. Agentic self-modification creates this kind of drift.
- **Scratch leaks.** `findings.md`/`progress.md`/`task_plan.md` are cycle-29 scratch that never got cleaned up — the process does not enforce scratch cleanup.
- **No observable SLA.** Cycle "wall-clock" is mentioned anecdotally (4 hours for cycle 26 per memory observation) but not tracked formally.

### 13.5 Recommendations

1. **Cap cycle velocity** — ≤0.5 cycle/day would let docs, tests, and feedback catch up.
2. **Promote the Cycle N retrospective** into a lightweight executive summary (≤200 words) at the top of each CHANGELOG entry, so a reader can skim the last 10 cycles in 5 minutes.
3. **Subdivide `decisions/`** by cycle range.
4. **Separate PRD from CLAUDE.md** (Finding 15 / section 2.3).
5. **Add `scripts/check_stale_scratch.py`** as a commit-hook that fails if root-level `findings.md` / `progress.md` / `task_plan.md` exist.
6. **Fold versioned tests** after each cycle so canonical coverage is easy to find.
7. **Track R1/R2 hang rate** — if Codex hangs > 20 % of runs, switch fallback to a deterministic condition-grep harness.

---

## 14. Fix Plan

Columns: **#**, priority (P0/P1/P2), severity, title, effort (ideal-hours), cycle slot, owner hint. One cycle ≈ 4 hours per memory observation 6640.

| # | Prio | Sev | Fix | Evidence / Fix | Effort | Cycle | Owner |
| ---: | :---: | :---: | --- | --- | ---: | :---: | --- |
| 1 | P0 | Crit | Split deps into extras; remove `litellm` + `crawl4ai` + `playwright` from default | Finding 1, `requirements.txt` | 4 h | N+1 | packaging |
| 2 | P0 | High | Add `.github/workflows/ci.yml` (ruff + pytest + pip check + pip-audit + build) | Finding 2 | 2 h | N+1 | CI |
| 3 | P0 | High | Fix `pyproject.toml:6` → `readme = "README.md"` and declare runtime deps correctly | Finding 3 | 0.5 h | N+1 | packaging |
| 4 | P0 | High | Wrap `{write_err}` in `_sanitize_error_str` at `mcp/core.py:762` + `:881` + regression tests | Finding 4, BACKLOG.md:146 | 1 h | N+1 | security |
| 5 | P0 | High | Reposition "No vectors" → "Markdown-first, optional hybrid retrieval"; document opt-out | Finding 5 | 2 h | N+1 | docs |
| 6 | P0 | High | Generate test-count badge in CI; drop exact counts from narrative text | Finding 6 | 0.5 h | N+1 | CI |
| 7 | P0 | High | Remove `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS` + README row; or ship real extractor | Finding 7 | 0.5 h (remove) / 4 h (extract) | N+1 | product |
| 8 | P0 | High | Extract `_scan_for_secrets` to `utils/secrets.py`; call from ingest + capture + compile; add `.llmwikiignore` | Finding 8 | 4 h | N+2 | security |
| 9 | P1 | High | Delete / move `findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`; add to `.gitignore`; add commit-hook | Finding 9 | 0.5 h | N+1 | hygiene |
| 10 | P1 | High | Implement ingest receipt/recovery (`.data/ingest_locks/<hash>.json`); per-page `page_lock` helper | Finding 10, BACKLOG.md:83-84, 99-100 | 8 h | N+3 | architecture |
| 11 | P1 | Med-H | Make long-I/O MCP tools `async def` OR tune `FastMCP(num_threads=N)` | Finding 11, BACKLOG.md:95-96 | 4 h | N+2 | performance |
| 12 | P1 | Med | Split `config.py` into `config/{paths,models,limits,search,lint}.py` with shim | Finding 13 | 4 h | N+3 | architecture |
| 13 | P1 | Med | Add `syrupy` golden tests for evidence-trail, Mermaid, llms.txt, graph.jsonld, siblings, query formats | Finding 14 | 6 h | N+2 | tests |
| 14 | P1 | Med | Fixture leak guard — autouse monkeypatch of all `WIKI_*`/`RAW_*` constants; opt-in `--use-real-paths` | BACKLOG Phase 4.5 HIGH | 3 h | N+2 | tests |
| 15 | P1 | Med | Coverage gate in CI; per-module % reporting | Section 5.4 | 2 h | N+2 | CI |
| 16 | P2 | Med | Write `docs/prd/v0.10.md` (≤300 lines) as stable product contract | Section 2.3 | 4 h | N+3 | product |
| 17 | P2 | Med | Freeze-and-fold rule — after a version ships, fold `test_v0NNN_*` into canonical module files | BACKLOG HIGH R3 | 1 cycle | N+4 | tests |
| 18 | P2 | Med | Subdivide `docs/superpowers/decisions/` by cycle range | Section 13.5 | 1 h | N+2 | docs |
| 19 | P2 | Low | Boot-smoke test: `pip install .` in clean venv; `kb --version`; assert importability | Section 5.4 | 1 h | N+2 | tests |
| 20 | P2 | Low | Document `kb_save_synthesis` correctly (it's `kb_query(save_as=...)`, not a separate tool) | Finding 17 | 0.25 h | N+1 | docs |

### Suggested cycle plan

- **Cycle 33 ("Release hygiene")** — items 1-7 + 9 + 20. Closes the P0 ship-blocker set in ~1 cycle. This is entirely docs + packaging + a 2-line security fix + CI bootstrap.
- **Cycle 34 ("Tests + security")** — items 8 (pre-ingest secret gate), 11, 13, 14, 15, 18, 19. Adds golden tests, fixture guard, coverage gate, async MCP, pre-ingest secret scan.
- **Cycle 35 ("Architecture")** — item 10 (ingest recovery), item 12 (config split). Harder, more invasive.
- **Cycle 36 ("Consolidation")** — item 16 (PRD), item 17 (test freeze-and-fold). Pays down docs debt before Phase 5 features resume.

Total ship-blocker fix time: **≈13 hours (~3 cycles)**. Realistic given current velocity.

---

## 15. Bottom Line

This repo is stronger than it looks from the outside. The product idea is original and defensible, the implementation has serious reliability and security primitives, and the test volume is real. The bottleneck is not capability — it is that the **product contract, dependency story, CI, and doc hygiene have not kept pace with the code**. The velocity that produced 32 cycles in 20 days is the same velocity that left scratch files in the repo root, "No vectors" in the README, and `readme = "CLAUDE.md"` in `pyproject.toml`.

Three cycles of focused release-hygiene work — most of which is documentation, packaging, CI bootstrap, and a two-line security fix — would produce a repo that **matches its code quality with its product contract**. At that point, "local-first Markdown knowledge compiler with MCP-native maintenance" becomes a credible claim, not an aspirational one.

If the author continues to treat process as the product, the compounding quality loop (skill patches, codified feedback, decision archive, multi-model review) will keep paying dividends. The thing to protect against is cycle overload — high-frequency iteration only works if the repo surfaces stay clean enough for the next cycle to start from a known state.

---

## Appendix A — Live Verification Log (2026-04-25)

All commands run from project root in the project `.venv`.

### A.1 Test collection

```text
$ .venv/Scripts/python.exe -m pytest --collect-only -q | tail -5
tests/test_workflow_e2e.py::test_e2e_ingest_then_query
tests/test_workflow_e2e.py::test_e2e_ingest_refine_requery
tests/test_workflow_e2e.py::test_e2e_shared_entity_wikilink_injection
2901 tests collected in 2.95s
```

### A.2 Dependency conflicts

```text
$ .venv/Scripts/python.exe -m pip check
arxiv 2.4.1 has requirement requests~=2.32.0, but you have requests 2.33.0.
crawl4ai 0.8.6 has requirement lxml~=5.3, but you have lxml 6.1.0.
instructor 1.15.1 has requirement rich<15.0.0,>=13.7.0, but you have rich 15.0.0.
```

### A.3 Vulnerability scan

```text
$ .venv/Scripts/python.exe -m pip_audit --format=columns
Found 4 known vulnerabilities in 4 packages
Name      Version ID                  Fix Versions
--------- ------- ------------------- ------------
diskcache 5.6.3   CVE-2025-69872
litellm   1.83.0  GHSA-xqmj-j6mv-4862 1.83.7
pip       26.0.1  CVE-2026-3219
ragas     0.4.3   CVE-2026-6587
```

### A.4 CI presence

```text
$ ls .github
ls: cannot access '.github': No such file or directory

$ find . -maxdepth 4 -type d -name ".github"
./.claude/skills/gstack/.github       # vendored skill, unrelated
./.tools/ralph-claude-code/.github    # vendored tool, unrelated
```

### A.5 Module sizes

```text
$ du -b src/kb/**/*.py src/kb/*.py | sort -rn | head -10
79682  src/kb/ingest/pipeline.py
54403  src/kb/query/engine.py
48835  src/kb/lint/augment.py
46859  src/kb/mcp/core.py
41793  src/kb/cli.py
40966  src/kb/lint/checks.py
36673  src/kb/compile/compiler.py
35543  src/kb/capture.py
33218  src/kb/query/embeddings.py
30143  src/kb/config.py
```

### A.6 Partial-write leak (findings 4)

```text
$ grep -n "_sanitize_error_str\|write_err" src/kb/mcp/core.py | head
70:    _sanitize_error_str,
...
581:            return f"Error ingesting source: {_sanitize_error_str(e, path)}"
616:            return f"Error ingesting source: {_sanitize_error_str(e, path)}"
748:    except OSError as write_err:
759:            write_err,                  # <-- log is sanitised indirectly via _sanitize_error_str
762:            f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); "
                                                                   ^^^^^^^^^^^
                                               raw OSError string → absolute path leak on Windows
785:        return f"Error: Ingest failed — {_sanitize_error_str(e, file_path)}"
868:        except OSError as write_err:
881:                f"Error[partial]: write to {_rel(file_path)} failed ({write_err}); "
                                                                      same pattern
```

### A.7 Product-claim drift

```text
$ grep -n "No vectors\|No chunking\|hybrid\|vector" README.md | head
5:> No vectors. No chunking.
17:- 🧠 Structure, not chunks. Entities, concepts, wikilinks — a real graph, not opaque vectors.
155:| Rebuild indexes | ... deletes the hash manifest + vector DB + in-process LRU caches
384:- v0.10.0: Phase 4 — hybrid search with RRF fusion (BM25 + vector via model2vec + sqlite-vec)

$ grep -n "tests-[0-9]" README.md
9:[![Tests](https://img.shields.io/badge/tests-2850-brightgreen)](#development)
```

### A.8 Scratch files in root

```text
$ ls -la findings.md progress.md task_plan.md claude4.6.md
-rw-r--r-- 1 Admin  1082 Apr 25 05:20 findings.md
-rw-r--r-- 1 Admin   239 Apr 25 05:20 progress.md
-rw-r--r-- 1 Admin   345 Apr 25 05:20 task_plan.md
-rw-r--r-- 1 Admin 40452 Apr 17 20:44 claude4.6.md
```

### A.9 Decision / velocity metrics

```text
$ ls docs/superpowers/decisions/ | wc -l
251

$ git log --oneline main | wc -l
788

$ git log --oneline --since="7 days ago" | wc -l
373
```

### A.10 Packaging gap

```text
$ head -14 pyproject.toml
[project]
name = "llm-wiki-flywheel"
version = "0.10.0"
description = "LLM-maintained knowledge wiki — compile raw sources into structured, interlinked markdown."
requires-python = ">=3.12"
readme = "CLAUDE.md"         # <-- should be README.md
dependencies = [
    "click>=8.0",
    "python-frontmatter>=1.0",
    "fastmcp>=2.0",
    "networkx>=3.0",
    "anthropic>=0.7",        # <-- declared required; README says optional
    "PyYAML>=6.0",
]
# Missing: jsonschema, httpx, trafilatura, nbformat, model2vec, sqlite_vec (all imported under src/kb)
```

---

*End of review. Supersedes `docs/repo_review.md`.*
