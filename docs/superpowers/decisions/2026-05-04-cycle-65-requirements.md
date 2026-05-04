# Cycle 65 — Requirements + Tier classifier

**Cycle:** 65
**Date opened:** 2026-05-04
**Branch:** `feat/cycle-65` (worktree: `.claude/worktrees/cycle-65`)
**Base:** `origin/main` @ `9b64a28` (cycle 64 final, post-PR-#89)
**Pipeline:** `dev-mimo-opus` (May 2026 MiMo trial — sixth+ run)

---

## Tier

**Tier 2 — standard feature** (multi-AC BACKLOG batch fix with security-touching items)

### Tier rationale

| Signal | Reading |
|--------|---------|
| Number of ACs | 23 across 14 files |
| Files touched | `config.py`, `tests/conftest.py`, `mcp/app.py`, `compile/compiler.py`, `requirements.txt`, `ingest/pipeline.py`, `query/embeddings.py`, `lint/fetcher.py`, `utils/cli_backend.py`, `graph/cache.py`, `tests/test_security_cve_greps.py` (NEW), `tests/test_cycle64_snapshots.py`, `docs/reference/INDEX.md` (NEW), `mcp/core.py`+`mcp/ingest.py`+`mcp/quality.py`, `.github/workflows/ci.yml` |
| Security-touch surface | Path validation (mcp/app.py + compile/compiler.py validator-contract drift), URL filtering (ingest/pipeline.py SSRF), MCP error-response sanitisation (info disclosure), dep pinning (GitPython unbounded), test-sandbox guard (autouse fixture preservation) |
| New auth/IAM/crypto/secrets/data-class boundaries? | **No** — these are HARDENING of existing surfaces, not introduction of new sensitive surfaces |
| Irreversible migration? | **No** — all changes are forward-compat refactors + additive guards |
| Deploy-pipeline change? | **No** |

### Tier decision

**Per skill: "When in doubt, go up"** — security-touches push toward **Tier 3**.
**Per user standing instruction `feedback_auto_approve.md`:** zero human-in-the-loop; Opus subagents handle all approvals.

**Resolution:** Tier 3's "mandatory human gates at Step 5 + Step 20 R2" is in DIRECT conflict with the user's standing instruction. Per the priority hierarchy established in `superpowers:using-superpowers`:

> 1. User's explicit instructions — highest priority
> 2. Superpowers skills — override default behavior where they conflict
> 3. Default system prompt — lowest priority

The user's `feedback_auto_approve` wins. **Effective classification: Tier 2 with full-pipeline coverage.** Each security-touching AC carries an explicit Step 2 threat-model entry and a 1:1 Step 14 verify.

### User pipeline modifications (cycle 65)

1. **Step 03 (Brainstorming)** — Opus main + DeepSeek V4 Pro parallel ideation for cross-model diversity. Compare convergent/divergent suggestions.
2. **Step 20 (PR review)** — Maximize MiMo Coding usage with modified prompts. R1: MiMo Coding (BLOCKER+MAJOR angle) + Sonnet (edge-case role). R2: MiMo Coding (cycle-lessons-rule audit angle, different prompt) + DeepSeek/Codex (cross-family confirmation).

These modifications soak the May 2026 trial in additional MiMo/DeepSeek roles. Step 20's standard cross-vendor diversity (DeepSeek+Sonnet R1 / Codex+Sonnet R2) is RELAXED for this cycle per user instruction.

### Steps run

Full pipeline (Steps 1–24). Skip-when conditions still respected per row (e.g., Step 19 signed commits skipped — repo doesn't require signing).

### Auto-merge

Yes — after Step 21 (per user's `feedback_auto_approve`).

---

## Acceptance Criteria — by file

Grouped by file per `feedback_batch_by_file` (HIGH+MED+LOW together, not by severity).

### A. `src/kb/config.py` — call-time accessor migration (3 ACs)

**Pattern:** several env vars / constants are read at module IMPORT time, inconsistent with the cycle-19 L2 call-time rule. Reload-leak hazard + tests setting env vars after import get stale values.

- **AC1** — `KB_PROJECT_ROOT` becomes call-time. Replace module-level `_PROJECT_ROOT = ...` with `get_project_root()` accessor reading `os.environ["KB_PROJECT_ROOT"]` at call time. Expose `_reset_project_root()` for tests. Existing `kb.config.PROJECT_ROOT` continues to work via `__getattr__` for back-compat. *(BACKLOG Phase 6 R2 HIGH; mimo r5 Q1)*
- **AC2** — *(BACKLOG drift correction per cycle-3 L4 verify-against-source.)* Mimo audit description was inverted. Actual state at `config.py`: line 132 `_DEFAULT_MODEL_TIERS` is hardcoded fallbacks (no env capture); line 160 `MODEL_TIERS` IS the import-time-captured dict bypassing the call-time `get_model_tier()` accessor at line 139. Migration: change `src/kb/utils/llm.py:17,69-71` to call `get_model_tier(tier)` instead of `MODEL_TIERS[tier]`. KEEP `MODEL_TIERS` dict for back-compat (cycle 7 AC24 explicitly kept it; versioned tests `test_v099_phase39.py` + `test_v0912_phase393.py:423` pin the import-time snapshot — those are intentional and stay). Add `tests/test_config_no_direct_model_tiers.py` AST-walk over `src/kb/**/*.py` excluding `config.py` itself, asserting zero `from kb.config import MODEL_TIERS` and zero `MODEL_TIERS[` references. *(BACKLOG Phase 6 R2 MED; mimo r5 Q1, Q2)*
- **AC3** — `AUGMENT_ALLOWED_DOMAINS` becomes call-time via `get_allowed_domains()` reading `KB_AUGMENT_ALLOWED_DOMAINS` env at call time, with default `["en.wikipedia.org", "arxiv.org"]`. *(BACKLOG Phase 6 R2 MED; mimo r5 Q5)*

### B. `tests/conftest.py` — sandbox-guard hardening (2 ACs)

**Pattern:** the autouse path sandbox is the load-bearing guard for 200+ test files; silent breakage cascades to real `wiki/`/`raw/` writes.

- **AC4** — Meta-test `tests/test_conftest_sandbox_guard.py` that `ast.parse`s `tests/conftest.py`, locates the `_autouse_kb_path_sandbox` `FunctionDef`, and asserts its decorator list includes `pytest.fixture(autouse=True)`. Test the structure, not the comment. *(BACKLOG Phase 6 R2 HIGH; mimo r2 Q1)*
- **AC5** — Replace hardcoded `lru_cache.cache_clear()` list (`load_purpose`, `_load_template_cached`, `_build_schema_cached`) with sandbox-teardown walk over every loaded `kb.*` module in `sys.modules`, introspecting attributes for `cache_clear` and calling all of them. Future `@lru_cache` additions auto-cleared. *(BACKLOG Phase 6 R2 HIGH; mimo r2 Q2)*

### C. `src/kb/mcp/app.py` — `_validate_page_id` hardening (3 ACs + AC9 spans here)

**Pattern:** Windows filename-confusion + cross-platform divergence + cosmetic correctness.

- **AC6** — `_validate_page_id` rejects any segment where `segment != segment.rstrip(". ")`. Closes Windows trailing-dot/space target-substitution (`"secret."` and `"secret "` both resolve to `"secret"`). Containment is preserved by the existing `relative_to` check; this AC closes filename-confusion. *(BACKLOG Phase 6 HIGH; mimo r2)*
- **AC7** — `_validate_page_id` rejects `:` plus `< > " | ? *` at the same gate as `_CTRL_CHARS_RE`. Closes NTFS Alternate Data Stream syntax (`"page:hidden"`) and aligns POSIX/Windows behaviour. *(BACKLOG Phase 6 MED; mimo r2)*
- **AC8** — Replace `".." in page_id` substring check with segment-aware `any(seg == ".." for seg in page_id.replace("\\", "/").split("/"))`. Permits legitimate `"notes..draft"` / `"c++..faq"`. The existing `resolve().relative_to()` is still the actual safety net. *(BACKLOG Phase 6 LOW; mimo r1)*

### D. `src/kb/mcp/app.py` + `src/kb/compile/compiler.py` — validator-contract drift (2 ACs)

**Pattern:** three sibling validators with three different contracts. A future fourth call site may quietly adopt the weakest contract.

- **AC9** — Extract canonical `_assert_under_project_root(path, *, require_exists=False, dual_anchor=True, allow_symlinks=False)` in a NEW module `src/kb/utils/path_safety.py`. Migrate `_validate_wiki_dir` (mcp/app.py:121), `_validate_path_under_project_root` (compile/compiler.py:645), `_validate_page_id`'s containment check (mcp/app.py:230) to delegate to it. Document contract in `docs/reference/error-handling.md`. *(BACKLOG Phase 6 MED; mimo r1, r2)*
- **AC10** — `_assert_under_project_root` (and downstream callers in `compile/compiler.py::rebuild_indexes` unlink path) close the TOCTOU window between containment validation and filesystem mutation by re-resolving + re-validating immediately before `unlink`/write, OR opening with `os.O_NOFOLLOW` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows). *(BACKLOG Phase 6 MED; mimo r1, r2)*

### E. `requirements.txt` — dep pinning (1 AC)

- **AC11** — Pin `GitPython` with explicit ceiling: `GitPython==3.1.47,<3.2` (or latest verified-safe). GitPython carried 4 RCE-class CVEs (2022-24439, 2023-40267, 2023-40590, 2024-22190); a future 3.1.48+ regression would land in main with no PR-time SCA signal. *(BACKLOG Phase 6 R2 HIGH; mimo r6 Q1)*

### F. `src/kb/ingest/pipeline.py` — URL → external CLI hardening (1 AC)

- **AC12** — *(BACKLOG drift correction per cycle-3 L4.)* Mimo audit description ("URL → external CLI") was wrong — the project does NOT pass URLs to `trafilatura.fetch_url` / `crawl4ai` / `yt-dlp` subprocess. URL flow goes through `lint/fetcher.py::AugmentFetcher.fetch()` → `httpx.Client(transport=SafeTransport())` → `SafeBackend` (lines 90-160). `SafeBackend` ALREADY rejects `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`, `is_unspecified` post-DNS, AND uses direct-IP connect to defeat DNS-rebind. Domain allowlist (`_url_is_allowed`) is also in place. **Real gap:** explicit scheme allowlist is missing — `_url_is_allowed` checks netloc but not `urlparse(url).scheme`; `file://`, `gopher://`, `data://` schemes may bypass at the orchestrator entry. **AC12 scope:** add `_url_scheme_allowed(url) -> bool` returning `urlparse(url).scheme in {"http","https"}`; gate at `lint/augment/orchestrator.py:248` (the URL-validation chokepoint) AND inside `_url_is_allowed`. New regression test exercises the actual `AugmentFetcher.fetch()` path with `file:///etc/passwd` + `gopher://...` + `data://...` URLs and confirms each is rejected. *(BACKLOG Phase 6 R2 HIGH; mimo r4 B; scope reduced — most SSRF defense already shipped)*

### G. `src/kb/query/embeddings.py` — VectorIndex.build hardening (2 ACs)

- **AC13** — Take `file_lock(db_path.with_suffix(".db.lock"))` around the DROP → CREATE → INSERT → COMMIT block in `VectorIndex.build`. Closes multi-PROCESS race; existing `_rebuild_lock` only serialises within one process. *(BACKLOG Phase 6 LOW; mimo r1)*
- **AC14** — Wrap `sqlite_vec.load(conn)` in `try/except sqlite3.OperationalError` and re-raise `RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel")` with no path detail. Closes filesystem-path leak via MCP error response. *(BACKLOG Phase 6 LOW; mimo r2)*

### H. `src/kb/lint/fetcher.py` — diskcache transitive RCE mitigation (1 AC)

- **AC15** — Set `TRAFILATURA_DOWNLOAD_NO_CACHE=1` in `lint/fetcher.py` module init AND assert via test that `trafilatura.fetch_url(...)` is invoked with caching disabled. Project robots cache is in-memory `dict`, but trafilatura's internal `fetch_url` not audited for diskcache pickle reads on attacker-supplied URLs. Belt-and-suspenders. *(BACKLOG Phase 6 R2 MED; mimo r6 Q5)*

### I. `src/kb/utils/cli_backend.py` — `_check_no_secrets_on_argv` self-DoS fix (1 AC)

- **AC16** — Replace generic token-shape regex with value-based scrub. Refuse only if argv element equals literal value of a listed env-var key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, `DEEPSEEK_API_KEY`, `MIMOCODING_API_KEY`, `MIMOCHAT_API_KEY`). Closes self-DoS where prompts legitimately discussing API-key formats fail to spawn. *(BACKLOG Phase 6 R2 MED; mimo r4 A)*

### J. `src/kb/graph/cache.py` — 6th-caller drift guard (1 AC)

- **AC17** — Set `__all__ = []` in `graph/cache.py` AND add `tests/test_graph_cache_no_direct_imports.py` AST-grep test that fails CI on any `from kb.graph.cache import get_graph` in `src/kb/**/*.py`. Forces all callers to use attribute-lookup form per cycle-18 L1. *(BACKLOG Phase 6 R2 MED; mimo r1 Q4)*

### K. `tests/test_security_cve_greps.py` — CI-enforced SECURITY.md greps (NEW, 1 AC)

- **AC18** — `tests/test_security_cve_greps.py` runs each grep declared in `SECURITY.md` (currently `diskcache`, `litellm`, `pip`, `ragas`) as a `subprocess` call against `src/kb/**/*.py` and asserts zero hits. CI failure message: "remove the package from src/kb or reclassify the CVE in SECURITY.md.". *(BACKLOG Phase 6 R2 HIGH; mimo r3 Q5)*

### L. `tests/test_cycle64_snapshots.py` — tautology hardening (1 AC)

- **AC19** — Add paired negative-control test per snapshot subject: mutate one input field of the captured-from path AND assert the snapshot does NOT match. Update CI pytest invocation to include `-p no:cacheprovider --snapshot-warn-unused` (drop `--snapshot-update` if present in CI). *(BACKLOG Phase 6 R2 LOW; mimo r2 Q4)*

### M. `docs/reference/INDEX.md` + meta-test (NEW, 1 AC)

- **AC20** — Generate `docs/reference/INDEX.md` from each `docs/reference/*.md` file's first H1 + frontmatter. Add `tests/test_docs_reference_index_complete.py` asserting every `docs/reference/*.md` (excluding INDEX.md and README.md) appears in INDEX.md AND in the CLAUDE.md "Detailed Documentation" table. *(BACKLOG Phase 6 R2 LOW; mimo r3 NEW)*

### N. `src/kb/mcp/core.py` + `src/kb/mcp/ingest.py` + `src/kb/mcp/quality.py` — error-response sanitisation (1 AC)

- **AC21** — Wrap each MCP tool body with a boundary handler `_mcp_error_boundary` that catches `Exception`, logs the full traceback locally to `kb.utils.text.sanitize_error_text`, and returns `f"Error: {sanitize_error_text(e)}"` to the MCP client. Closes information disclosure (filesystem paths, subprocess stderr) on the typically-trusted local boundary. Reuse existing `kb.utils.text.sanitize_error_text` from cycle 10. *(BACKLOG Phase 6 R2 MED; mimo r4 E)*

### O. `.github/workflows/ci.yml` — dummy-key leak guard (1 AC)

- **AC22** — Add CI grep step: `git ls-files | xargs grep -l "sk-ant-dummy" | grep -v ".github/workflows/ci.yml" | (! read)`. Step fails if `sk-ant-dummy` appears in any tracked file except the CI workflow itself. Closes recorded-cassette / VCR / pytest-snapshot leak hazard. *(BACKLOG Phase 6 R2 LOW; mimo r5 Q7)*

### P. `tests/test_validator_contract_consolidation.py` — AC9/AC10 verification (NEW, 1 AC)

- **AC23** — `tests/test_validator_contract_consolidation.py` enumerates ALL call sites of the canonical `_assert_under_project_root` from AC9 via AST-walk over `src/kb/**/*.py`. Asserts the historical three sites (`mcp/app.py:121`, `mcp/app.py:230`, `compile/compiler.py:645`) are present. Acts as cycle-23 L4 same-class peer scan codified.

---

## BACKLOG drift findings (caught during AC verification per cycle-3 L4)

Two ACs had inaccurate BACKLOG descriptions; both verified against current source and corrected inline above.

| AC | BACKLOG mimo claim | Actual current state | Resolution |
|----|---------------------|----------------------|------------|
| AC2 | `_DEFAULT_MODEL_TIERS` captures env at import time | `_DEFAULT_MODEL_TIERS` (line 132) is hardcoded fallbacks; `MODEL_TIERS` (line 160) is the actual import-time-captured dict | AC2 scope shifted to migrating `kb.utils.llm` from `MODEL_TIERS[tier]` to `get_model_tier(tier)` + AST-walk guard against new direct callers |
| AC12 | URL → external CLI subprocess SSRF | No URLs passed to subprocess. Flow is `httpx.Client(transport=SafeTransport())` with mature SSRF defense already in place (`SafeBackend.connect_tcp` lines 90-128) | AC12 scope reduced to scheme allowlist only — most defense already shipped in `lint/fetcher.py`; verify and add scheme gate as the remaining hardening |

These drift findings are themselves a Step-24 lesson candidate (BACKLOG mimo-audit descriptions need source-grep verification before being lifted into ACs).

## Out of scope (NOT in cycle 65)

- `kb/__init__.py` public API docstring audit — requires NEW `scripts/audit_docstrings.py`; defer to a docs-only cycle.
- `mcp_server.py` shim deletion — touches `pyproject.toml [project.scripts]` + may break external consumers; defer to a CLI-cleanup cycle.
- Phase 4.5 R3-R5 deferred items (`compile_wiki` two-phase pipeline, `compile/linker.py` cross-reference auto-linking, `IndexWriter` consolidation refactor) — larger architectural scope.
- Cycle-53+ items (windows-latest CI matrix, GHA Windows multiprocessing spawn, posix off-by-one).
- Phase 5 Karpathy-gist features (`wiki/_schema.md`, `kb_merge`, claim-tag inline markers, `.llmwikiignore`).
- Phase 6 candidates (Hermes-style supervisor, mesh sync, hosted MCP HTTP/SSE).

---

## Done conditions

- 23/23 ACs landed with regression tests
- Step 14 security verify produces 23/23 PASS against threat-model entries from Step 2
- Test count delta: ≥ +20 new tests (one+ per AC, plus integration)
- Full-suite pass on ubuntu-latest CI strict-gated (windows-latest matrix still deferred per cycle-36 L1)
- BACKLOG.md hygiene: 23 entries DELETED with brief CHANGELOG.md entry + full CHANGELOG-history.md detail
- Step 24 self-review scorecard committed; lesson candidates routed through cross-family DeepSeek+Codex governance gate before auto-apply
- PR merged to main, branch deleted local + remote
