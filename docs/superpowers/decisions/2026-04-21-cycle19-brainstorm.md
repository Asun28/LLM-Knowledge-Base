# Cycle 19 Brainstorm

**Date:** 2026-04-21
**Scope:** 20 ACs across 5 clusters (A linker batch, B refine two-phase, C manifest-key, D test cleanup, E e2e + log)
**Upstream:** requirements.md (20 ACs) + threat-model.md (5 threats — 1 HIGH, 3 MEDIUM, 1 LOW)

---

## Design decisions (autonomous, grounded in requirements + threat model)

### D1 — Batch helper signature shape (AC1)
**Options:**
- (a) `inject_wikilinks_batch(new_pages: list[tuple[str, str]], wiki_dir=None, *, pages=None) -> dict[str, list[str]]`
- (b) `inject_wikilinks_batch(new_pages: dict[str, str], …)` — `{target_page_id: title}`
- (c) keep existing `inject_wikilinks` and add a `batch=False` flag

**Decision: (a) tuple list.** Rationale: preserves ordering for AC3's deterministic tie-break (longest-title-first), matches the existing `_sort_new_pages_by_title_length(new_pages_with_titles)` contract at pipeline.py:1344-1346, keeps the return-dict keyed by target_page_id (multiple new pages can map to updates on the same existing page). Option (c) hides the O(N) vs O(N·M) divergence behind a flag — code smell.

### D2 — Per-page read count strategy (AC2)
**Options:**
- (a) One `read_text` peek + one `pattern.search` per page, using a combined alternation regex of all batch titles.
- (b) One `read_text` peek per page, then per-title `pattern.search` on the cached body (N-title linear scan in-memory).

**Decision: (a) combined alternation.** Rationale: single compiled regex with `re.escape(t) for t in titles` + `re.IGNORECASE`; scans body once. Compiled regex caching per batch. ReDoS bounded by AC4's `MAX_INJECT_TITLES_PER_BATCH=200`. Re-use the `_mask_code_blocks` helper once per page.

### D3 — Write policy when multiple new titles match the same existing page (AC3)
**Options:**
- (a) Inject only the FIRST matching title per page per batch (deterministic iteration order).
- (b) Inject ALL matching titles per page per batch.
- (c) Inject the LONGEST matching title per page (prefer specificity).

**Decision: (c) longest-first tie-break matching the existing `_sort_new_pages_by_title_length` behaviour.** Rationale: equivalence with the pre-batch behaviour (which processed titles in sorted order and stopped on first match per page per title-round). `inject_wikilinks` already injects one link per page per call; the batch preserves one per page per batch. Remaining matches get linked on the next ingest/run.

### D4 — Refine two-phase status values (AC8)
**Options:**
- (a) `status ∈ {"pending", "applied", "failed"}` with `error` field populated only on `failed`.
- (b) Separate `applied_at` timestamp (null for pending); drop `status` field (relies on null check).
- (c) Append-only event log: one entry per state transition (`pending_at`, `applied_at`, `failed_at`).

**Decision: (a) status enum with error field.** Rationale: (b) overloads a nullable timestamp for state indication and breaks on forensic replay; (c) doubles write count. (a) extends the existing single-entry-per-refine model with one extra field, minimising migration cost. Existing history consumers ignore the new field by default.

### D5 — `manifest_key` kwarg ingestion (AC12)
**Options:**
- (a) Accept `manifest_key: str | None = None` keyword-only; document as opaque string from `manifest_key_for`.
- (b) Accept `manifest_key: str | Path`; if Path, canonicalize internally.
- (c) Skip the kwarg and make `ingest_source` grep its own caller stack.

**Decision: (a) keyword-only opaque string.** Rationale: T3 mitigation requires the caller to have already canonicalized (caller owns the trust). (b) re-introduces the exact divergence we're fixing (two different canonicalization paths). (c) is dark magic.

### D6 — MCP test monkeypatch migration execution order (AC15)
**Options:**
- (a) Refactor `kb.mcp.core` imports first (`from kb.ingest import pipeline; pipeline.ingest_source(...)`), then migrate tests to patch the owner module — breaks existing tests for one commit.
- (b) Migrate tests first (patch both old AND new targets), then refactor `kb.mcp.core` to use module-attribute access, then remove the old-target patches.
- (c) Single atomic commit: refactor imports + migrate all tests in one commit.

**Decision: (c) atomic single-commit.** Rationale: test files and kb.mcp.core change are tightly coupled; splitting across commits risks an intermediate red-CI state. A single commit is easier to review and revert. The batch-by-file convention accommodates a "cluster" commit when code + its paired tests must ship together.

### D7 — `tmp_kb_env` HASH_MANIFEST cleanup detection (AC18)
**Options:**
- (a) Grep test source files for `tmp_kb_env` argument usage; fail lint if the same file also has a literal `HASH_MANIFEST` monkeypatch.
- (b) Runtime fixture introspection via `request.node.fixturenames` — more accurate but couples the lint to pytest internals.
- (c) Defer the lint rule; do only the mechanical cleanup.

**Decision: (a) source-file grep lint.** Rationale: simpler, no pytest internals, deterministic. False-positive rate near zero because `tmp_kb_env` is an autouse fixture that's only pulled in when the test declares it as a parameter or via its module-level fixture chain.

### D8 — Lock order documentation for refine_page (AC10)
**Options:**
- (a) Inline comment inside `refine_page` explaining the order.
- (b) Module-level docstring section.
- (c) Both, plus a `lock_order_note.md` under `docs/`.

**Decision: (a) inline comment next to each acquisition site + (b) paragraph in the module docstring under a `## Concurrency notes` heading.** Rationale: callers reading the docstring (via IDE hover) see the contract; readers debugging inside the function see the adjacent comment. (c) is overkill — the contract is local to one module.

### D9 — e2e test placement (AC19)
**Options:**
- (a) Reuse `tests/test_workflow_e2e.py` (cycle-18 add) with a new scenario.
- (b) New `tests/test_cycle19_inject_batch_e2e.py`.
- (c) Integration marker + skip by default.

**Decision: (b) new file per cycle convention.** Rationale: the cycle-N test-file-per-topic convention keeps each cycle's regression scope reviewable by filename. Re-using a generic e2e file ages poorly.

### D10 — Pages bundle threading (AC7)
**Options:**
- (a) `inject_wikilinks_batch(new_pages, wiki_dir=None, *, pages=None)` — pages is an optional pre-loaded bundle.
- (b) Always require callers to pass pages; drop the disk-walk fallback.
- (c) Cache the pages bundle at module scope with mtime invalidation.

**Decision: (a) optional kwarg.** Rationale: call sites outside the ingest hot path (tests, `kb_lint`, future batch callers) benefit from the convenience default. (b) breaks tests. (c) re-introduces the cache-invalidation surface cycle 18 L1 warned about.

### D11 — Prune base consistency fix (AC14)
**Options:**
- (a) Single helper `_prune_base(raw_dir: Path) -> Path` returns `raw_dir.resolve()`; both prune sites call it.
- (b) Inline the fix at each site.
- (c) Compute `raw_dir.resolve().parent` lazily at call time in `_canonical_rel_path` (move resolution into the canonicalizer).

**Decision: (a) shared helper.** Rationale: one symbol to grep, one docstring to maintain, one site to test. (c) silently changes `_canonical_rel_path`'s semantics for other callers.

### D12 — `inject_wikilinks_batch` null-byte sanitizer placement (T2 mitigation)
**Options:**
- (a) `title = title.replace("\x00", "")` at each title entry in the batch loop.
- (b) Validate titles at the ingest pipeline extraction boundary (reject extractions containing `\x00`).
- (c) Both (a) and (b).

**Decision: (c) both.** Rationale: (b) moves the defense to the edge where we already sanitize (`utils/text.sanitize_extraction_field`), reducing downstream defensive code. (a) is belt-and-suspenders because the batch helper may be called from other paths in the future. Cost: two 1-line edits.

---

## Open questions carried to Step 4 design eval

1. **Q1 (AC2)**: Expected `read_text` budget under the batch path — 1 per page × #matched (peek-only) + 2 per page × #updated (peek + under-lock re-read). Is the test budget `≤ 2 × len(existing_pages)` realistic, or tighter?

2. **Q2 (AC4)**: Should chunks of 200 titles process in parallel (threading) or serially? **Default: serially** — simpler, preserves deterministic output order, avoids lock-contention on pages that match multiple chunks.

3. **Q3 (AC7)**: If `pages=` is provided but `wiki_dir=` is also provided, what takes precedence? **Default: `pages=` wins** (caller explicitly pre-loaded); `wiki_dir` used only for defaults + log path.

4. **Q4 (AC8)**: Should the legacy `load_review_history` filter out `status="pending"` rows older than some TTL? **Default: no, keep visibility**. Garbage-collect via a dedicated sweep tool if it becomes a problem.

5. **Q5 (AC10)**: Should lock acquisition use nested `with file_lock(history) as h, file_lock(page) as p:` or the current pattern (manual `__enter__` / `__exit__`)? **Default: nested `with`-statements** — clearer, reduces manual `__exit__` discipline and aligns with the cycle-18 `with file_lock(log_path):` pattern in `append_wiki_log`.

6. **Q6 (AC11)**: Public alias name — `manifest_key_for` (verb-first, matches `decay_days_for`, `tier1_budget_for`, `volatility_multiplier_for`). **Default: `manifest_key_for`**.

7. **Q7 (AC13)**: Does `ingest_source` need to VALIDATE `manifest_key` beyond "is a non-empty str"? **Default: no format validation** — opaque per T3 contract. A malicious caller could poison the manifest dict key, but it's a dict key only (no FS access).

8. **Q8 (AC15)**: Are there any test sites where the `patch("kb.mcp.core.X")` pattern intentionally patches the MCP-local binding (e.g. to intercept only MCP-path calls while leaving CLI/library paths untouched)? **Audit in design eval.**

9. **Q9 (AC17)**: How do I detect whether a test file "uses tmp_kb_env" without running pytest collection? Grep for `tmp_kb_env` token as function parameter — simple and reliable.

10. **Q10 (AC19)**: Lock-count assertion — should the test spy on `file_lock` or on `Path.read_text`? **Default: both spies with independent assertions.**

11. **Q11 (cluster B)**: Should the refine two-phase write ALSO track sequence number / refine-attempt counter? **Default: no, keep single-entry-per-refine model** (AC8 only adds a status field + optional error). Forensic replay uses timestamps.

12. **Q12 (T5 mitigation)**: For AC20, should the batch log line list all N updated page IDs inline or just the count? **Default: count + page IDs comma-joined with 100-char cap** — preserves auditability without flooding log.md.

13. **Q13 (monkeypatch migration blast radius)**: If migration reveals a test call graph that also patches `kb.mcp.browse.ingest_source` or similar, expand the migration? **Default: no — scope AC15 strictly to `kb.mcp.core.<callable>` patches**. Any similar discovery in sibling MCP modules files a new cycle-19-discovered backlog entry.

14. **Q14 (T3 integration)**: Should `manifest_key_for` also be re-exported from `kb` top-level `__all__`? **Default: no** — low-level helper, internal to compile/ingest. Direct import from `kb.compile.compiler` if truly needed by external callers.

15. **Q15 (existing `inject_wikilinks` preservation)**: Keep the single-target `inject_wikilinks` function after adding the batch helper, or deprecate it? **Default: keep and mark batch as preferred.** Tests and existing single-target callers (if any) continue working. Legacy caller audit in step 4.

---

These feed the design-eval round 1 (Opus) + round 2 (Codex) with explicit question enumeration.
