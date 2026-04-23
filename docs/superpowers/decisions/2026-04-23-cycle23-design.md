# Cycle 23 — Design Decision Gate

**Date:** 2026-04-23
**Role:** Step 5 design gate — argue both sides of every open question surfaced by R1 Opus + R2 Codex, commit to a decision.
**Bias:** lower blast radius wins (reversible > irreversible, internal > public, opt-in > always-on).

## Inputs

- Step-1 requirements (8 ACs)
- Step-2 threat model (I1-I5)
- Step-4 R1 Opus verdict: APPROVE-WITH-AMENDMENTS (AC4 blocker on `_TEXT_EXTENSIONS`; AC2 amendments on return shape + vector-path helper; AC7 file_lock-timeout verification)
- Step-4 R2 Codex verdict: APPROVE-WITH-AMENDMENTS (AC2 file_lock + cache list + symlink; AC3 exit code; AC4 thread-safety + kb.query.__init__ eager import; AC5 subprocess specifics; AC6 rebuild_vector_index stub)

## Open Questions (13)

---

### Q1 (AC1) — Sentinel-word grep vs negative-phrase grep for docstring test?

**OPTIONS:**
- (a) Three sentinel substrings `"manifest"`, `"vector"`, `"LRU"` + literal `"rebuild_indexes"` helper name.
- (b) Full negative-phrase assertion (e.g. `"does NOT invalidate"` + each category).

**## Analysis**
R2 caught a real gap: sentinel words pass on the OPPOSITE claim ("manifest/vector/LRU are rebuilt"). The whole point of the docstring is to say these are NOT cleared by `--full`. A test that passes on the opposite claim is the cycle-16 L2 "stdlib-helper-in-isolation" anti-pattern at the doc layer — it doesn't exercise the contract.

On the other hand, asserting exact phrases makes the test brittle — a trivial rewording ("not invalidated" → "not cleared") would break it. The compromise is to assert BOTH: (a) each category word appears, AND (b) the phrase "NOT invalidated" (or equivalent negation token) appears near the category keyword. That pins the direction of the claim without locking the exact wording.

**DECIDE:** Option (b), narrowed: assert (i) the helper name `rebuild_indexes` appears, and (ii) a negation token (`"not"` — case-insensitive) appears within 200 chars of EACH of the three category words (`manifest`, `vector index`, `LRU`). Implementation: split docstring on whitespace, find the index of each category word, scan a 200-char window for `" not "` or `"n't "`.

**RATIONALE:** Direction-of-claim is load-bearing; locality-bounded negation check is resilient to rewording.

**CONFIDENCE:** High.

---

### Q2 (AC2) — Return shape for `rebuild_indexes()`?

**OPTIONS:**
- (a) Plan's original: `{"manifest_cleared": bool, "vector_cleared": bool, "caches_cleared": list[str]}`.
- (b) Amended: `{"manifest": {"cleared": bool, "error": str | None}, "vector": {"cleared": bool, "error": str | None}, "caches_cleared": list[str], "audit_written": bool}`.

**## Analysis**
The amended shape is strictly additive — bool callers can still check `result["manifest"]["cleared"]`. The benefit: when a lock-busy TimeoutError or PermissionError skips the unlink, the CLI can print WHY, not just "failed silently". That matters for CI debuggability — an `audit log` row is a record, but a per-clear error surfaced in the return dict is inspectable from the CLI exit.

The cost: every test asserting the shape pays 3 extra keystrokes. Acceptable given only the CLI + one regression test consume the return dict.

**DECIDE:** Option (b).

**RATIONALE:** Per-target error info + audit-written flag is cheap and pins R2's "report `manifest_cleared=False` on TimeoutError" requirement.

**CONFIDENCE:** High.

---

### Q3 (AC2) — Acquire `file_lock(HASH_MANIFEST, timeout=...)` before unlink?

**OPTIONS:**
- (a) Unlocked unlink (accept occasional races — concurrent `compile_wiki` may save back old state).
- (b) `file_lock(HASH_MANIFEST, timeout=1.0)` around the unlink; on `TimeoutError` return `cleared=False, error="lock busy"`.

**## Analysis**
`rebuild_indexes()` is an operator-initiated intervention — the operator runs it because they want the indices gone. A concurrent `compile_wiki` holding the manifest lock means ingest is in-flight. Two scenarios:

1. **ingest started BEFORE rebuild:** ingest holds the lock, rebuild waits (up to timeout), times out, returns `cleared=False`. The operator sees "manifest busy" and knows to wait. Good outcome.
2. **ingest started DURING rebuild (interleaved):** unlocked unlink would race. With the lock, ingest waits, rebuild unlinks, ingest proceeds against a fresh manifest. Good outcome.

Without the lock: case 2 can leave the operator thinking the manifest is gone when ingest has already saved it back with stale entries.

The lock is cheap (< 1 KB write + rename). Use it.

**DECIDE:** Option (b), timeout=1.0s.

**RATIONALE:** Cycle-19 established lock-discipline for manifest RMW; rebuild_indexes joins that discipline.

**CONFIDENCE:** High.

---

### Q4 (AC2) — Full cache list to clear?

**OPTIONS:**
- (a) Plan's original: just `_build_schema_cached.cache_clear()`.
- (b) Full: `kb.ingest.extractors.clear_template_cache()` (covers `_load_template_cached` + `_build_schema_cached`) + `kb.utils.pages.load_page_frontmatter.cache_clear()` + `kb.utils.pages.load_purpose.cache_clear()`.

**## Analysis**
Grep showed 3 `lru_cache` sites outside the one the plan named. Every cache that holds page metadata or templates is a stale-read risk after rebuild (the operator just wiped derived state; the next ingest must re-read everything). Missing any one means the next `kb compile` could see stale cached data.

R1 did not enumerate the full set but R2 did. Cost: 3 extra lines.

**DECIDE:** Option (b). Call `kb.ingest.extractors.clear_template_cache()` (if the helper exists — else call `_build_schema_cached.cache_clear()` and `_load_template_cached.cache_clear()` directly), plus `load_page_frontmatter.cache_clear()` and `load_purpose.cache_clear()`. The returned `caches_cleared` list names each helper that was cleared.

**RATIONALE:** Complete stale-read invalidation; cost is trivial.

**CONFIDENCE:** High. **Implementation note:** Step 9 must verify whether `kb.ingest.extractors.clear_template_cache` exists as a public function before relying on it; fallback is direct `.cache_clear()` calls.

---

### Q5 (AC2) — Symlink validation: link path or resolve()?

**OPTIONS:**
- (a) Validate `wiki_dir.resolve()` under PROJECT_ROOT.resolve() (i.e. let resolve() follow symlinks, check final target).
- (b) Validate the link path ITSELF under PROJECT_ROOT, NOT the resolved target.

**## Analysis**
R2's concern: if `.data/hashes.json` is a symlink to `/etc/shadow`, `unlink()` removes the SYMLINK (not the target) — so the system file is safe. But `resolve()` returns `/etc/shadow`; an `is_relative_to(PROJECT_ROOT)` check on the resolved target would REJECT the rebuild, even though the unlink is actually safe. Inverse failure: operator's legitimate symlink chain across drives fails containment.

For the `wiki_dir` argument to `rebuild_indexes()`, the correct semantics is: the caller-supplied `wiki_dir` must be a path inside the project (attacker can't aim rebuild at `/etc` directly — that's I1). Validate the ARGUMENT path (before resolve) and its resolved form are BOTH under PROJECT_ROOT — defensive but simple.

For `HASH_MANIFEST` and `vector_index.db`: these paths are derived INTERNALLY from `wiki_dir` via the project's own config/helpers. An attacker would need to pre-create a malicious symlink inside the project tree to exploit — if they can do that, they can also just modify the code. Treat these as trusted internal paths; skip symlink gymnastics.

**DECIDE:** Validate `wiki_dir`'s absolute input AND `wiki_dir.resolve()` are both under PROJECT_ROOT.resolve() (defensive pair). For HASH_MANIFEST and vector DB path: trust the derived paths (no additional symlink check).

**RATIONALE:** Attack surface is the `wiki_dir` argument only; internally-derived paths inherit trust from that validation. Keeps the helper simple.

**CONFIDENCE:** Medium. If Step-11 security verify flags symlink-specific same-class concerns, revisit.

---

### Q6 (AC2) — Vector DB path: helper or hardcode?

**OPTIONS:**
- (a) Hardcode `wiki_dir.parent / ".data" / "vector_index.db"` (the path derivation used in `query/embeddings.py:63`).
- (b) Import `kb.query.embeddings._vector_index_path(wiki_dir)` helper if it exists; else define one.

**## Analysis**
Hardcoding invites drift — if the vector index location ever moves (e.g. to `.data/vec/` or migrated to a different filename), rebuild_indexes would silently miss it. R1 flagged this.

The helper is already partially-factored: `query/embeddings.py:63` contains the logic; whether it's exported as `_vector_index_path` or inline, Step 9 should extract a named helper and have both `rebuild_vector_index` and `rebuild_indexes` use it.

**DECIDE:** Option (b). Step 9 extracts `_vector_index_path(wiki_dir: Path) -> Path` from `query/embeddings.py:63` if not already named, and `rebuild_indexes` imports + uses it.

**RATIONALE:** Single source of truth for the vector DB location.

**CONFIDENCE:** High.

---

### Q7 (AC3) — CLI exit code on user abort?

**OPTIONS:**
- (a) `click.confirm(abort=True)` — Click-default exit code 1.
- (b) `ctx.exit(2)` explicitly — distinguish "aborted by user" (2) from "failed" (1).

**## Analysis**
Click's convention for `abort=True` is exit-1 via `click.Abort` exception. The project's existing subcommands follow Click defaults. Introducing a non-conventional exit=2 path for one subcommand is inconsistent.

CI scripts that want to distinguish can always `set -e` + inspect the specific command — they don't need the help of an exit-code vocabulary. Operator-facing: "aborted" is visible in stderr.

**DECIDE:** Option (a). Use `click.confirm("Are you sure?", abort=True)`.

**RATIONALE:** Consistency with other subcommands; Click convention; no CI script reported as needing the distinction.

**CONFIDENCE:** High.

---

### Q8 (AC4) — PEP-562 `__getattr__` thread-safety lock?

**OPTIONS:**
- (a) No lock — rely on Python's import lock + idempotency of `globals()[name] = val`.
- (b) Add `threading.Lock` around the `globals()[name] = val` write.

**## Analysis**
Python's import system has its own lock; `importlib.import_module()` is thread-safe. The potential race is:

```
Thread A: __getattr__("ingest_pipeline") → import_module → returns module M
Thread B: __getattr__("ingest_pipeline") → import_module → returns module M (same object, cached)
Thread A: globals()["ingest_pipeline"] = M
Thread B: globals()["ingest_pipeline"] = M  (same value, idempotent)
```

Both write the SAME module object (import system returns the cached module on re-entry). The final `globals()` state is correct regardless of interleaving. No lock needed.

Cycle-6 PR #20 L2 lesson ("Adding a lock prevents duplicate construction; it does NOT make the protected resource thread-safe for ongoing use") is the converse warning — here we have a self-idempotent operation, not a non-thread-safe resource.

**DECIDE:** Option (a). No lock. Add a comment in the `__getattr__` body explaining the idempotency.

**RATIONALE:** Python import system guarantees same module object on re-entry; `globals()` write is idempotent. Adding a lock is ritual not safety.

**CONFIDENCE:** High.

---

### Q9 (AC4) — Migrate `kb/query/__init__.py` to PEP 562?

**OPTIONS:**
- (a) Leave `kb/query/__init__.py` as-is (eager `from kb.query.engine import ...`).
- (b) Migrate to PEP 562 lazy (mirror `kb/ingest/__init__.py`).

**## Analysis**
R2 caught this: `kb.query.__init__` currently does `from kb.query.engine import query_wiki, search_pages` eagerly. When ANY code does `from kb.query import engine as query_engine` (including PEP-562 `__getattr__` in core.py that calls `importlib.import_module("kb.query.engine")`), Python loads `kb/query/__init__.py` FIRST (parent package init), which loads `kb/query/engine.py` eagerly. So AC5's assertion "`kb.query.engine` not in `sys.modules` after bare `import kb.mcp`" fails as long as `kb.query.__init__` eagerly imports the engine.

Fix: migrate `kb/query/__init__.py` to PEP 562 (return `query_wiki` / `search_pages` on attribute access only). Same pattern as `kb/ingest/__init__.py`.

Blast radius: any `from kb.query import query_wiki` / `from kb.query import search_pages` caller continues to work (PEP 562 fires on the `from X import Y` path). Any `import kb.query; kb.query.query_wiki` also works. The only behaviour change is DELAYED import.

**DECIDE:** Option (b). Migrate in same AC4 scope.

**RATIONALE:** Mandatory for AC5 assertion to pass. Mirrors the `kb.ingest.__init__` precedent.

**CONFIDENCE:** High.

---

### Q10 (AC4) — Relocate `_TEXT_EXTENSIONS`?

**OPTIONS:**
- (a) Move to `kb.mcp.core` (local frozenset at module top — no cross-module import).
- (b) Move to `kb.config` (consolidates with other extension constants).

**## Analysis**
Grep confirmed `_TEXT_EXTENSIONS` has ONE consumer: `kb.mcp.core:481`. Not used inside `kb.ingest.pipeline` itself. Moving it to `kb.mcp.core` keeps the scope local and eliminates one cross-module import — boot cost zero.

Moving to `kb.config` consolidates it with `SUPPORTED_SOURCE_EXTENSIONS` (semantic siblings), but `kb.config` is already imported by core.py at line 56, so that's also boot-cost zero. The semantic home is `kb.config` since it's a config-like whitelist.

Tie-breaker: `_TEXT_EXTENSIONS` carries MCP-only semantics ("stricter than SUPPORTED_SOURCE_EXTENSIONS — excludes .pdf"). Keeping it local to MCP is truer to its purpose. And moves less.

**DECIDE:** Option (a). Inline frozenset at top of `kb.mcp.core`, delete `pipeline.py:65` definition.

**RATIONALE:** Zero cross-module import, single consumer, MCP-only semantics.

**CONFIDENCE:** High.

---

### Q11 (AC5) — Subprocess output format?

**OPTIONS:**
- (a) JSON dict via `json.dumps(...)` on stdout.
- (b) Newline-separated keys.

**## Analysis**
JSON is structured; if the test adds assertions on multiple values (sys.modules deltas, identity check result), JSON is more robust than newline parsing. Negligible cost — Python stdlib.

**DECIDE:** Option (a). Subprocess prints `json.dumps({"missing": [...], "present": [...], "identity": bool})`; parent parses.

**RATIONALE:** Structured output is strictly better than string splitting.

**CONFIDENCE:** High.

---

### Q12 (AC6) — E2E test: stub `rebuild_vector_index` to no-op?

**OPTIONS:**
- (a) Run real `rebuild_vector_index` (pays 0.8s + 67 MB once for embedding model load).
- (b) Monkeypatch `kb.query.embeddings.rebuild_vector_index` to no-op.

**## Analysis**
For a hermetic CI test, the embedding model load is NOT the thing being tested. E2E test goal is to verify `ingest → query → lint` integration — vector-side correctness is covered by dedicated `test_phase4_audit_embeddings.py`. Stubbing saves 0.8s + 67 MB and avoids flakiness from cold model load on CI runners without GPU.

Cycle-17 L3 reminds: narrowing scope mid-cycle should go through Step 5 — which is this gate. Decision: stub.

**DECIDE:** Option (b). Monkeypatch `kb.query.embeddings.rebuild_vector_index` + `kb.query.embeddings._get_model` to no-ops. Budget relaxed from 3s to 15s as R2 suggested.

**RATIONALE:** Hermeticity + CI speed. Vector correctness covered elsewhere.

**CONFIDENCE:** High.

---

### Q13 (AC7) — Cross-platform multiprocessing context?

**OPTIONS:**
- (a) `mp.get_context("spawn")` unconditional.
- (b) Default context (platform-dependent: `fork` on POSIX, `spawn` on Windows).

**## Analysis**
`spawn` is the intersection-lowest-common-denominator: picklable workers, same semantics everywhere. `fork` on POSIX is faster but has fork-safety caveats (shared FDs, locks). For a test about cross-process file-lock behaviour, `spawn` is semantically cleaner (no inherited state).

Cost: spawn is slower — pays Python startup per child (~100ms). Acceptable for an `@pytest.mark.integration` test.

**DECIDE:** Option (a). `mp.get_context("spawn")` unconditional. Worker is a top-level module function.

**RATIONALE:** Deterministic semantics across platforms; avoids fork-specific flakiness.

**CONFIDENCE:** High.

---

## Summary

| Q | Decision | AC impact |
|---|---|---|
| Q1 | Negation-token near category words | AC1 test |
| Q2 | Per-target error dict return | AC2 signature |
| Q3 | `file_lock(HASH_MANIFEST, timeout=1.0)` | AC2 body |
| Q4 | Full cache list (4 sites) | AC2 body + return |
| Q5 | Validate `wiki_dir` pre + post `resolve()` | AC2 body |
| Q6 | Use `_vector_index_path` helper | AC2 body |
| Q7 | `click.confirm(abort=True)` (exit-1) | AC3 body |
| Q8 | No `__getattr__` lock (idempotent) | AC4 body |
| Q9 | Migrate `kb/query/__init__.py` too | AC4 scope +1 file |
| Q10 | Inline `_TEXT_EXTENSIONS` in `kb.mcp.core` | AC4 scope +1 file edit |
| Q11 | JSON subprocess output | AC5 body |
| Q12 | Stub `rebuild_vector_index` + `_get_model` | AC6 body |
| Q13 | `mp.get_context("spawn")` unconditional | AC7 body |

**Scope growth from Step 5:**
- AC4 now also touches `kb/query/__init__.py` and `kb/ingest/pipeline.py` (delete `_TEXT_EXTENSIONS` definition).
- AC2 now uses `file_lock` — adds `kb.utils.io.file_lock` to imports.

## CONDITIONS (Step 9 must satisfy — cycle-22 L5)

1. **AC1 test** contains (a) `rebuild_indexes` literal token assertion, (b) negation-token-near-category-words assertion for each of `manifest`, `vector index`, `LRU`.
2. **AC2 helper** returns `{"manifest": {"cleared": bool, "error": str|None}, "vector": {"cleared": bool, "error": str|None}, "caches_cleared": list[str], "audit_written": bool}`.
3. **AC2 helper** acquires `file_lock(HASH_MANIFEST, timeout=1.0)` before unlink; `TimeoutError` → `cleared=False, error="lock busy"`.
4. **AC2 helper** clears all four cache sites OR `clear_template_cache()` if exported.
5. **AC2 helper** validates `wiki_dir` absolute input + `wiki_dir.resolve()` both under PROJECT_ROOT.resolve(); raises `ValidationError` otherwise.
6. **AC2 helper** uses `_vector_index_path(wiki_dir)` helper for the vector DB path.
7. **AC2 helper** appends to `wiki/log.md` via `append_wiki_log` AFTER unlinks; `OSError` logged via `logger.warning`, helper returns with `audit_written=False`.
8. **AC3 CLI** uses `click.confirm(..., abort=True)` for the confirm prompt; `--yes` skips the prompt.
9. **AC3 CLI** subprocess test asserts `kb --version` does NOT pull `kb.compile.compiler` into `sys.modules` (cycle-8 L1).
10. **AC4** deletes `_TEXT_EXTENSIONS` from `kb.ingest.pipeline:65`, re-adds as local frozenset in `kb.mcp.core` module top.
11. **AC4** migrates `kb/query/__init__.py` to PEP 562 lazy (mirror `kb/ingest/__init__.py`).
12. **AC4** adds `_LAZY_MODULES: dict[str, str]` allowlist + `__getattr__` / `__dir__` at `kb.mcp.core` module top; `AttributeError` fallback for names not in allowlist.
13. **AC4** regression test (in AC5) pins `kb.mcp.core.ingest_pipeline is kb.ingest.pipeline` after first access.
14. **AC5 test** uses subprocess with `sys.executable` + list-form argv + `PYTHONPATH` via `os.pathsep.join`; JSON output; 10s timeout.
15. **AC5 test** explicitly asserts missing: `anthropic`, `networkx`, `sentence_transformers`, `kb.query.engine`, `kb.ingest.pipeline`, `kb.feedback.reliability`.
16. **AC5 test** asserts post-lazy-load: `kb.mcp.core.ingest_pipeline is kb.ingest.pipeline`.
17. **AC5 test** asserts `getattr(kb.mcp.core, "os")` raises `AttributeError` (closed allowlist).
18. **AC6 test** monkeypatches `kb.query.engine.call_llm` + `kb.query.embeddings.rebuild_vector_index` + `kb.query.embeddings._get_model`; 15s wallclock budget.
19. **AC7 test** uses `mp.get_context("spawn")` unconditional; top-level worker function; sentinel cleanup in `finally`.
20. **AC7 test** calls `file_lock(path, timeout=0.5)` to pin the TimeoutError path; joins child with `timeout=5` + `kill()` fallback.

## Escalation

Zero double-ESCALATE questions. All decisions made; confidence levels are High (11) or Medium (1 — Q5 symlink). Proceed to Step 6.
