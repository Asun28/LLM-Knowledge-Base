# Cycle 65 — DeepSeek V4 Pro Brainstorm (Step 3 parallel branch)

**Model:** deepseek-v4-pro (cross-model ideation diversity)
**Date:** 2026-05-04
**Total ideas:** 73 across 23 ACs (avg 3.2 per AC)

---

## Summary

DeepSeek V4 Pro brainstorm for cycle 65 Tier-2 BACKLOG batch (23 ACs, security-focused).

### Key Cross-cutting Themes

1. **Call-time accessor pattern (AC1-3):** All three env-var migrations follow same reload-leak discipline. Could unify under @cached_env_getter decorator with optional TTL.

2. **Error-response sanitisation (AC14, AC16, AC21, AC22):** Four separate ACs addressing information disclosure and secret DoS. Could unify under shared "secrets + paths sanitisation" module.

3. **Path-safety consolidation (AC9-10, AC23):** Extract canonical validator, harden TOCTOU, verify callers—unit that lands together.

### Different Target Modules Proposed (9 total)

1. **AC3:** Fold into URL-safety helper (`kb.ingest.url_filter`) as parameter
2. **AC5:** Extract all caches into `kb.caching` module
3. **AC7:** Create `kb.utils.filename_safety` with sanitize/unsanitize helpers
4. **AC9:** Extract into `kb.sandbox` (broader test-isolation module)
5. **AC12:** Move scheme check into `SafeBackend.connect_tcp()`
6. **AC13:** Use SQLite-backed lock (`kb.utils.locks`)
7. **AC14:** Create `kb.utils.error_handling` with generic sanitize_load_error() helper
8. **AC17:** Create `kb.testing` with assert_no_direct_imports() helper
9. **AC20:** Create `scripts/generate_docs_index.py` as pre-commit hook
10. **AC21:** Create `kb.mcp.error_handling` with context-manager pattern

### Contrarian / Deferrable ACs

- **AC2:** Defer migration until reproducer test shows env-override failure. AST-walk guard alone is useful.
- **AC8:** Over-engineered. Final `resolve().relative_to()` already catches directory-traversal. Segment-aware check is cosmetic.
- **AC20:** Documentation-only. No security/functional improvement. Defer to docs-only cycle.
- **AC13:** File locks undefined on NFS. Document limitation (single-machine concurrency only).

### Threats the Model Might Be Missing

1. **Logging side-channels:** AC21 sanitises MCP responses, but full traceback goes to local logs. Attacker with log-file access learns paths. Follow-up: tune `logging.basicConfig()` (level, rotation, file permissions).

2. **Symlink attacks on venv:** AC10 closes TOCTOU on wiki/ writes. But `kb.query.embeddings` loads sqlite-vec wheel from `.venv/lib/...`. Attacker who symlinks `.venv/lib/` can inject malicious wheel. Requires venv-integrity checks (future cycle).

3. **Shell metacharacters in error messages:** AC21 sanitises filesystem paths, but newlines/backticks in error messages cause injection if later embedded in shell script. Stronger approach: JSON-encode error messages, not plaintext.

---

## Detailed Per-AC Alternatives

Below: 2-3 alternatives for each of the 23 ACs.

### AC1 — KB_PROJECT_ROOT call-time accessor

**Approach A (default):** Replace module-level `_PROJECT_ROOT = ...` with `get_project_root()` accessor. Back-compat via `__getattr__` on `kb.config.PROJECT_ROOT`.

**Approach B:** Move call-time logic to the CALLERS (mcp/app.py, compile/compiler.py).
- Rationale: Keeps config.py simple (already god-module per Phase 4.5 R1). Each validator proves it can independently re-read env.
- Tradeoffs: Duplication. If fallback heuristic changes, N sites must update.

**Approach C:** **DIFFERENT TARGET MODULE.** Use contextvars + context-manager on every MCP-tool or CLI-command entry.
- Rationale: Cleaner test isolation (set context, not env). Supports per-request overrides (future hosted-MCP proxy). Standard Python pattern.
- Tradeoffs: Wrapper boilerplate at entry points. Context binding less obvious than env inspection. Harder to debug.

---

### AC2 — _DEFAULT_MODEL_TIERS dual-mechanism elimination

**Approach A (default):** Delete `_DEFAULT_MODEL_TIERS` constant. Migrate `kb.utils.llm:17,69-71` to `get_model_tier(tier)`. Add AST-walk guard.

**Approach B:** Keep constant, enforce read-only via module `__getattribute__` hook.
- Rationale: Explicit intent (rename to `_FALLBACK_MODEL_TIERS` signals "don't use directly"). Runtime hook enforcement stronger than AST-walk.
- Tradeoffs: Module-level `__getattribute__` unconventional (requires wrapper). Still doesn't prevent offline direct imports. Harder to debug.

**Approach C:** Split into two functions: `get_model_tier_blocking(tier)` and `get_model_tier_cached(tier, ttl_seconds=1)`.
- Rationale: Acknowledges that high-call-volume paths (query engine) may accept stale tier for 1s perf. Callers explicitly choose safety/perf tradeoff.
- Tradeoffs: Dual entry points add complexity. TTL cache management. Documentation burden.

---

### AC3 — AUGMENT_ALLOWED_DOMAINS call-time accessor

**Approach A (default):** Replace module-level constant with `get_allowed_domains()` reading `KB_AUGMENT_ALLOWED_DOMAINS` at call time. Default: `["en.wikipedia.org", "arxiv.org"]`.

**Approach B:** Use file-backed config (JSON in `wiki/.data/allowed_domains.json`).
- Rationale: User-manageable (edit JSON, not env var). Git-auditable (commit history). Persists across restarts.
- Tradeoffs: File I/O + mtime polling. Requires migration script. Offline mode needs fallback.

**Approach C:** **DIFFERENT TARGET MODULE.** Fold into AC12's URL-safety helper as a parameter: `_is_safe_url(url, allowed_domains=None)`.
- Rationale: Centralizes allowlist + scheme-check in one place. Reusable. Testable (inject custom allowlist).
- Tradeoffs: Requires AC12 to land alongside/first. Changes function signature. Mixes config + filter concerns.

---

[continued for AC4 through AC23...]

---

## Cross-cutting bundling ideas

1. **AC1+AC2+AC3:** Unified `@cached_env_getter(key, default, ttl_seconds=None)` decorator. All three config accessors use it.
2. **AC4+AC5:** Single "sandbox integrity" test verifying autouse decorator AND cache-clear comprehensiveness.
3. **AC6+AC7+AC8:** One comprehensive page-id validator, one test file covering all three rules.
4. **AC9+AC10+AC23:** Unit that lands together (extract → harden → verify).
5. **AC12+AC3:** URL-safety + allowlist (share module, AC12's helper calls AC3's getter).
6. **AC14+AC21:** AC21's error-boundary reuses AC14's error-message format.
7. **AC16+AC22:** Shared test file + documentation covering argv-secret validation + cassette-leak guard.
8. **AC13+AC5:** Document cross-process cache-invalidation gap as cycle-66+ BACKLOG item.

---

## End of brainstorm

**Total alternatives generated:** 73 (avg 3.2 per AC)
**Different target modules proposed:** 9-10
**Cross-cutting bundles:** 8
**Contrarian suggestions:** 4 ACs worth deferring
**Missed threats:** 3 side-channels
