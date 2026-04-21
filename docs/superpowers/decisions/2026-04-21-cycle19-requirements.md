# Cycle 19 — Requirements + Acceptance Criteria

**Date:** 2026-04-21
**Branch (target):** `feat/backlog-by-file-cycle19`
**Operator:** Opus 4.7 (1M context) primary session
**Headline scope:** Reliability hardening — batch wikilink injection (close cycle-17 AC21 / cycle-18 deferral), refine_page two-phase write ordering (HIGH deferred since Phase 4.5 HIGH cycle 1), MCP test-monkeypatch owner-module migration (unlocks cycle-17 AC4 full scope), HASH_MANIFEST redundant-patch cleanup (cycle-18 D6 follow-up), compile_wiki manifest-key consistency fix (HIGH R4 open).

---

## Problem

Cycle 18 closed the per-page TOCTOU + observability gap, but four reliability holes carried forward and the cycle-19 candidate list adds three more. Rolled together they cover:

1. **`inject_wikilinks` is N×M reads under the hot path** (`ingest/pipeline.py:1345-1353` → `compile/linker.py:172-310`). One ingest creating 50 entities + 50 concepts × N existing pages = 100·N disk reads and 100 separate per-target locks. At 5k pages this is 500k peek reads per ingest — the slowest visible operation in the cycle. Cycle 18 added per-page locking but kept the per-target loop; the read amplification grew.

2. **`refine_page` write-then-audit ordering** (`review/refiner.py:209-241`) — page body atomic-writes succeed, then the audit history append happens after the page lock is released. A crash between the page write and the history-lock acquire leaves the wiki page mutated with **zero** audit record, violating the documented refine-has-audit-trail guarantee. R2 deferred fix from Phase 4.5 HIGH cycle 1.

3. **MCP test monkeypatch debt blocks lazy-import savings.** Cycle-17 AC4 intentionally narrowed lazy-deferral scope to `kb.capture` only because 13 legacy `patch("kb.mcp.core.<callable>")` sites assume `kb.mcp.core` re-exports `ingest_source` / `query_wiki` / `search_pages` / `compute_trust_scores`. Migrating those tests to patch the owner modules unblocks the next cycle's lazy-import work (~0.8s/35MB cold-boot savings projected in the BACKLOG HIGH item).

4. **Cycle-18 D6 leftover** — 20 existing tests still monkeypatch `kb.compile.compiler.HASH_MANIFEST` directly even though `tmp_kb_env` now redirects it. Additive-compatible today, but a footgun for future readers and an easy lint target.

5. **`compile_wiki` manifest-key inconsistency under non-default raw_dir** (`compile/compiler.py:434-466` + `ingest/pipeline.py:687`). `compile_wiki` writes the manifest with `_canonical_rel_path(source, raw_dir)`, but `ingest_source` writes with its own `make_source_ref` resolution. Under Windows case differences or `raw_dir` overrides the same source produces two divergent manifest keys, so `find_changed_sources` re-extracts on the next compile. (HIGH R4.)

6. **`compile_wiki` full-mode prune base bug** (`compile/compiler.py:268-290`). `_canonical_rel_path` uses `raw_dir.parent` as its anchor implicitly; the `find_changed_sources` deletion-prune block uses the same anchor as the per-source loop, but `compile_wiki(incremental=False)` re-derives `raw_dir.parent` for the prune check inconsistently across non-default `raw_dir` callers. Same root cause as #5; closing #5 with a single canonical helper closes both. (HIGH R4 + R4 prune-races bullet collapsed.)

7. **`scan_wiki_pages` is called inside the inject_wikilinks per-target loop** so each call re-walks the wiki directory tree from disk. Even if (1) lands the batch helper, the helper still needs a clean way to receive a pre-scanned `pages` bundle to avoid re-walking inside the pipeline.

---

## Non-goals

- **No new MCP tool surface.** No `kb_merge`, no `kb_delete_source`, no `kb_search` CLI. Those remain Phase-5 backlog.
- **No `kb.errors` module / `LLMError → KBError` taxonomy split.** That HIGH refactor is a one-cycle topic of its own; adding it here doubles cycle scope.
- **No `models/page.py` dataclass activation.** Migration target enumerated in cycle-17 AC8 docstring; explicit Phase-5 work.
- **No publish auto-hook** (`compile/publish.py` compile-time). Backlog MEDIUM, deferred.
- **No async MCP rewrite.** Backlog HIGH, infra-shaped, separate cycle.
- **No vector-index lifecycle (atomic temp-DB rebuild + cold-load warmup).** HIGH deferred bundle remains its own dedicated cycle.
- **No two-phase compile pipeline** (`compile_wiki` cross-source reconciliation). Phase 6 candidate.
- **No `IndexWriter` class extraction.** Cycle 18 `_write_index_files` helper covered the pragmatic ordering; the full state-machine receipt-file approach remains a Phase-5 reliability cycle.
- **No `kb.config` god-module split.** Same — separate refactor cycle.

---

## Acceptance criteria

Each AC is testable as pass/fail. Test ID syntax `T-<n>` flags the regression test that pins it.

### Cluster A — `compile/linker.py` + `ingest/pipeline.py`: batch wikilink injection

- **AC1** New public function `inject_wikilinks_batch(new_pages, wiki_dir=None, *, pages=None) -> dict[str, list[str]]` in `kb.compile.linker`. `new_pages: list[tuple[title: str, target_page_id: str]]`. Returns `{target_page_id_lower: [updated_page_id, …]}`. T-1: a wiki containing pages mentioning two new titles A and B receives wikilinks to both after one batch call; return dict has both keys. **Cycle 17 AC21 closure.**

- **AC2** `inject_wikilinks_batch` walks each existing target page **at most once** (single `read_text` + single `pattern.search` per existing page, regardless of how many `new_pages` are in the batch). T-2: monkeypatch `Path.read_text` to count calls; for `len(new_pages) == 5` and `len(existing_pages) == 10`, total `read_text` calls ≤ 10 (ignoring frontmatter cache reads). **Cycle-11 L1 / cycle-16 L2 vacuous-test gate: assert reverting the batch loop to the per-target call still triggers >10 reads, confirming the test divergence.**

- **AC3** When a page mentions multiple new titles, **at most one** wikilink is injected per page per batch call (matches the per-call invariant of the existing `inject_wikilinks`; ensures behavioural parity). The remaining new-title mentions on that page get linked on the **next** ingest. T-3: page mentioning A and B; one batch call produces one wikilink (the first new-title in the iteration order, broken deterministically by `title` length descending then alphabetical — same tie-break as the existing `_sort_new_pages_by_title_length` helper).

- **AC4** ReDoS bound: `MAX_INJECT_TITLES_PER_BATCH = 200` constant in `kb.config`; batches longer than that are split into chunks of 200 titles each (executed sequentially). Each title is `re.escape`d before alternation. T-4: pass 250 new pages; assert two internal scan rounds happen and all 250 titles get processed.

- **AC5** Per-target `file_lock(page_path, timeout=_INJECT_LOCK_TIMEOUT)` is acquired **only** for pages where the pre-lock peek detects ≥1 candidate match (preserves cycle-18 AC7 fast-path); the under-lock re-read + re-validate semantics are preserved. T-5: monkeypatch `file_lock` to count acquisitions; pages with no candidate-title match acquire ZERO locks (cycle-18 T8 lock-overhead invariant unchanged).

- **AC6** `kb.ingest.pipeline._run_ingest_body` switches the inject-wikilinks loop from N separate `inject_wikilinks(title, pid)` calls to one `inject_wikilinks_batch([(title, pid), ...])` call. The output `wikilinks_injected` field of the ingest result keeps its existing shape (`list[str]`, deduplicated). T-6: monkeypatch `inject_wikilinks_batch` and assert it is called exactly once per ingest with the full new-pages tuple list.

- **AC7** When a caller passes `pages=` to `inject_wikilinks_batch`, the function uses the pre-loaded bundle and skips `scan_wiki_pages` entirely (mirrors `build_backlinks` cycle-7 AC10 contract). The pipeline pre-loads pages once from disk and threads the bundle through. T-7: pass `pages=[]`; assert the function returns `{}` without touching disk.

### Cluster B — `review/refiner.py` two-phase write

- **AC8** `refine_page` writes a `status="pending"` history entry **before** the page body atomic-write, then flips the entry to `status="applied"` after the page write succeeds. On page-write OSError, the history entry stays as `status="failed"` with an `error` field. T-8: inject an OSError into `atomic_text_write` for the page; assert the history JSON contains a single entry with `status == "failed"` and the original page body is unchanged. **Phase 4.5 HIGH cycle-1 deferred.**

- **AC9** Pending → applied flip is **inside** the same `file_lock(history_path)` window that wrote the pending entry — the history file is RMW-locked across the page-write window so a crash between pending-write and applied-flip leaves the audit row visible (with `status="pending"` being self-reporting "interrupted"). T-9: kill the process by raising `KeyboardInterrupt` between pending and applied; assert history contains `status == "pending"` row.

- **AC10** Lock acquisition order is **history_path FIRST, page_path SECOND** to preserve the existing two-lock chain (avoids deadlock with concurrent processes that already hold history_lock when calling refine). Document the order in the function docstring. T-10: a unit test that uses `inspect.signature` would be vacuous; instead, the test mocks both `file_lock` calls to record acquisition order and asserts history-lock is acquired first.

### Cluster C — `compile/compiler.py` + `ingest/pipeline.py` manifest-key consistency

- **AC11** Single canonical helper `manifest_key_for(source: Path, raw_dir: Path) -> str` in `kb.compile.compiler` (alias of existing `_canonical_rel_path` made public + documented). T-11: importable from `kb.compile.compiler`; returns deterministic POSIX-style relative path.

- **AC12** `ingest_source` accepts an optional `manifest_key: str | None = None` parameter. When provided, the manifest write at the existing site uses this key instead of computing its own. When omitted, behaviour is unchanged (backwards-compatible default). T-12: assert legacy callers without `manifest_key=` continue passing.

- **AC13** `compile_wiki`'s per-source loop passes `manifest_key=rel_path` into `ingest_source`, eliminating the dual-write divergence path (BACKLOG HIGH R4 §"manifest hash key inconsistency"). T-13: integration test runs `compile_wiki` against a `raw_dir` with a tilde-shortened Windows path and asserts manifest contains exactly one key per source after a re-compile (no duplicates with case differences).

- **AC14** `compile_wiki(incremental=False)` prune base derives from `raw_dir.resolve()` consistently in both prune sites (line ~268 + line ~454), so a non-default `raw_dir` no longer wipes legitimate manifest entries. T-14: pass a sibling `raw_dir` (not the default `RAW_DIR`); assert no manifest entries are pruned for sources that still exist on disk.

### Cluster D — Test infrastructure cleanup

- **AC15** Migrate the **callable** monkeypatches (not constants) at `kb.mcp.core.<callable>` to their owner module: 13 sites across 7 test files — `kb.mcp.core.ingest_source` → `kb.ingest.pipeline.ingest_source`, `kb.mcp.core.search_pages` → `kb.query.engine.search_pages`, `kb.mcp.core.query_wiki` → `kb.query.engine.query_wiki`, `kb.mcp.core.compute_trust_scores` → `kb.feedback.reliability.compute_trust_scores`. **Plus one corresponding refactor in `kb.mcp.core`**: switch the affected call sites from `from … import name; name(…)` to `from kb.ingest import pipeline; pipeline.name(…)` etc., so the patch on the owner module actually intercepts the call (Python snapshot-binding semantics — see cycle-18 L1). T-15: each migrated test continues to pass; one new vacuous-gate test asserts that reverting `kb.mcp.core` to the `from … import name` form makes the migrated patch ineffective (proves the test divergence is real). **Cycle-19 candidate, MEDIUM.**

- **AC16** Constant patches (`PROJECT_ROOT` / `RAW_DIR` / `SOURCE_TYPE_DIRS`) on `kb.mcp.core` REMAIN — `from kb.config import X` snapshot-binding means patching `kb.config.X` does NOT propagate to `kb.mcp.core.X`. Document this asymmetry in `kb/mcp/core.py` module docstring under the existing AC4 section. T-16: a new docstring-extraction test asserts the module docstring contains the rationale.

- **AC17** Remove `monkeypatch.setattr(…, "kb.compile.compiler.HASH_MANIFEST", …)` from tests that already use `tmp_kb_env` (which redirects HASH_MANIFEST under the cycle-18 D6 fixture extension). 12 files with HASH_MANIFEST patches today; the affected subset is those using `tmp_kb_env` autouse — verify by grep + remove redundant patch lines. Tests with explicit isolation (no `tmp_kb_env`) keep their HASH_MANIFEST patches. T-17: full-suite pass count unchanged after removal.

- **AC18** New lint rule in `tests/test_cycle19_lint_redundant_patches.py` that fails if a test file uses both `tmp_kb_env` (autouse fixture name in collected fixtures) AND a literal `kb.compile.compiler.HASH_MANIFEST` monkeypatch. T-18: lint test passes after AC17 cleanup; reverting AC17 makes it fail.

### Cluster E — End-to-end + observability sanity (carry from cycle 18 ingest log)

- **AC19** New end-to-end test `tests/test_cycle19_inject_batch_e2e.py` chains `tmp_kb_env` → seed 3 existing pages mentioning new titles → ingest one new article producing 2 new entity pages → assert the per-page lock count from cycle-18 telemetry stays at the new lower bound (≤ existing-pages-with-matches, not ≤ N×M). T-19.

- **AC20** Update `wiki/log.md` rendering for the batch path: a single ingest with N batch-injected wikilinks emits ONE `inject_wikilinks_batch` log line (not N separate `inject_wikilinks` lines). Preserves audit-trail readability. T-20.

---

## Blast radius

| Module | Files | Change type |
|---|---|---|
| `compile/linker.py` | 1 | Add `inject_wikilinks_batch` (~80 lines); preserve `inject_wikilinks` for existing callers and tests |
| `compile/compiler.py` | 1 | Public `manifest_key_for` alias; thread `manifest_key=` through per-source loop; consistent prune base |
| `ingest/pipeline.py` | 1 | Switch wikilink-injection loop to batch call; accept `manifest_key=` param |
| `review/refiner.py` | 1 | Two-phase write (pending → applied); reorder file_lock acquisitions; status field on history entries |
| `mcp/core.py` | 1 | 4 import-style refactors (`from … import name` → `from … import module`) for monkeypatch test path consistency |
| `tests/` (existing) | ~7 | Migrate `patch("kb.mcp.core.<callable>")` → owner module |
| `tests/` (existing) | ~12 | Drop redundant `HASH_MANIFEST` patches when `tmp_kb_env` already in scope |
| `tests/` (new) | 6 | `test_cycle19_inject_wikilinks_batch.py`, `test_cycle19_refiner_two_phase.py`, `test_cycle19_manifest_key_consistency.py`, `test_cycle19_mcp_monkeypatch_migration.py`, `test_cycle19_lint_redundant_patches.py`, `test_cycle19_inject_batch_e2e.py` |
| `config.py` | 1 | Add `MAX_INJECT_TITLES_PER_BATCH = 200` |

Total source files: 6 (5 modules + config). Total test files added: 6. Total test files modified: ~19. Estimated commits: 6-7 (one per file cluster + plan-gate amendments + R1 fixes).

## Cycle 18 lessons applied to this cycle

- **L1 (snapshot-binding):** New helpers in `compile/linker.py` and `review/refiner.py` will use `import kb.config; kb.config.X` for any cross-module path constant they read at call time, never `from kb.config import X` at module top.
- **L2 (telemetry envelope boundary):** When `_run_ingest_body` switches to `inject_wikilinks_batch`, no telemetry emission moves into the batch helper — the caller still owns the wiki_log entry and the JSONL emission.
- **L3 (pre-body exception orphans):** AC8 two-phase write puts the pending-history-write **inside** the existing try block, so a crash between page-write and applied-flip leaves a self-describing pending row (no orphan in the other direction).
- **L4 (byte vs char truncation):** No new error-summary truncation in cycle 19; existing code unchanged.

## Open questions for Step 4 design eval

1. AC1: should `inject_wikilinks_batch` accept a `dict[str, str]` or `list[tuple[str, str]]`? Tuple list preserves iteration order (important for AC3 deterministic tie-break). **Default: tuple list.**
2. AC2: is "≤10 reads" too strict given the in-lock re-read? Counting strategy: pre-lock peek + under-lock re-read = 2 per modified page; 1 per unmodified page. **Adjust T-2 budget accordingly.**
3. AC4: is 200 the right batch ceiling? Larger batches inflate the alternation regex; smaller batches multiply the per-page reads. **Empirical default 200; revisit on perf data.**
4. AC8/AC9: pending-row visibility — should `load_review_history` filter out `status == "pending"` rows older than N hours? Could mask legitimate audit gaps. **Default: no filter, pending rows stay visible until the next manual sweep.**
5. AC11: alias name `manifest_key_for` vs preserving private `_canonical_rel_path` and adding a one-line public re-export. **Default: re-export with a one-line public alias to minimize blast radius.**
6. AC12: does `manifest_key` need to be keyword-only? **Default: yes, to prevent positional-arg drift.**
7. AC13: how should the integration test actually create a tilde-shortened Windows path? On non-Windows it's a no-op. **Mark `@pytest.mark.skipif(sys.platform != "win32")`.**
8. AC15: which call sites in `kb.mcp.core` need the `from … import module` refactor? Enumerate: `kb_ingest` calls `ingest_source`; `kb_query` calls `query_wiki`; multiple tools call `search_pages`; reliability tools call `compute_trust_scores`. **4 owner modules total.**
9. AC15: are there call sites where the local-name binding is intentional (e.g. for a local alias)? **Audit before refactor.**
10. AC17: should the redundant-HASH_MANIFEST cleanup also remove `monkeypatch.setattr(kb.config, "PROJECT_ROOT", ...)` patches that `tmp_kb_env` covers? **No — scope-creep. AC17 limited to HASH_MANIFEST.**
11. AC18: `tmp_kb_env` detection — use `request.node.fixturenames` introspection? Or grep test source for `tmp_kb_env` argument? **Default: grep — simpler, no live-fixture dependency.**

These feed Step 4 design eval and Step 5 decision gate.
