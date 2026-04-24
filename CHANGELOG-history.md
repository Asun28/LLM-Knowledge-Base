# Changelog — Historical Archive

> **Reading guide:** This file is the full-detail reference archive. Keep entries newest first. High-level summaries of all cycles live in [CHANGELOG.md](CHANGELOG.md); per-item bullet-level detail lives here.
> Cross-reference: [BACKLOG.md](BACKLOG.md) for open work.

---

## Active-unreleased archive — 2026-04-16 to 2026-04-24

> Detailed per-cycle entries live here. High-level summaries remain in [CHANGELOG.md](CHANGELOG.md); full bullet-level detail belongs here.

### Phase 4.5 — cycle 28 (2026-04-24)

9 AC / 2 src + 1 new test file / 4 commits. Tests: 2801 → 2809 (+8).

**First-query observability completion.** Closes HIGH-Deferred sub-item (b) in `query/embeddings.py` — cycle-26 Q16 follow-up. Cycle 26 shipped `_get_model()` cold-load observability; cycle 28 extends the same pattern to the two remaining first-query latency sources: `VectorIndex._ensure_conn` (sqlite-vec extension load) and `BM25Index.__init__` (corpus indexing). No new trust boundary; no filesystem-write contract; no MCP/CLI surface (counters stay diagnostic-only per cycle-26 Q14). After cycle 28, only sub-item (a) dim-mismatch AUTO-rebuild remains deferred under the HIGH-Deferred lifecycle entry.

**Cluster A — `src/kb/query/embeddings.py::_ensure_conn` sqlite-vec observability (AC1, AC2, AC3).** Before cycle 28, the sqlite-vec extension load inside `VectorIndex._ensure_conn` was unmeasured — operators seeing "slow first query" could not discriminate `sqlite_vec.load` cost from BM25 cost from model cold-load cost. Cycle 28 lands four additions: (a) `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS: float = 0.3` module constant (matches cycle-26 `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS` posture per Q4 — no env override), (b) `_sqlite_vec_loads_seen: int` counter incremented INSIDE `_conn_lock` for exact counts (intentional asymmetry vs cycle-25 lock-free `_dim_mismatches_seen` query-hot-path counter — matches cycle-26 AC4 locked low-rate-event pattern), (c) `get_sqlite_vec_load_count() -> int` public getter with precedent-documenting docstring (C8 — names both cycle-25 lock-free and cycle-26 locked variants), (d) `_ensure_conn` instrumented with `time.perf_counter` around the FULL extension-load block (CONDITION 1 — brackets `sqlite3.connect` through `enable_load_extension(False)` inclusive, not just `sqlite_vec.load`). INFO log `"sqlite-vec extension loaded in %.3fs (db=%s)"` always on success + WARNING `"sqlite-vec extension load took %.3fs (threshold=%.2fs); consider warm-loading"` above 0.3s. Post-success ordering invariant (CONDITION 4 / CONDITION 9): log + counter fire AFTER `self._conn = conn` assignment, NEVER in `finally:` — guarantees that an extension-load failure (the `except Exception: _disabled=True` branch) leaves the counter untouched and emits NO misleading "loaded" INFO record. The FAILURE path's existing `"sqlite_vec extension load failed"` WARNING remains unchanged (cycle-3 H7 contract preserved).

**Cluster B — `src/kb/query/bm25.py::BM25Index.__init__` corpus-indexing observability (AC4, AC5).** `BM25Index.__init__` builds the doc-frequency + postings + IDF structures from pre-tokenized documents; on a ~5K-page wiki this is the single largest first-query cost when the cache misses. Cycle 28 lands three additions: (a) `_bm25_builds_seen: int` module-level counter — lock-free per Q2 / cycle-25 Q8 precedent (the caller releases `_WIKI_BM25_CACHE_LOCK` / `_RAW_BM25_CACHE_LOCK` BEFORE invoking the constructor, so exact counts would require a new lock; operator-diagnostic use tolerates approximate counts under concurrent cache-miss rebuilds), (b) `get_bm25_build_count() -> int` public getter with Q11-pinned semantics "constructor executions, NOT distinct cache insertions" — explicitly names BOTH call sites `engine.py:110` (wiki-page cache) and `engine.py:794` (raw-source cache) so future maintainers can't mistake the aggregate for a per-cache-family metric, (c) `__init__` instrumented with `time.perf_counter` around the FULL method body (CONDITION 2 — brackets the corpus loop + avgdl + IDF pre-computation). INFO log `"BM25 index built in %.3fs (n_docs=%d)"` emits unconditionally on every construction including the empty-corpus edge case `n_docs=0` (per R2 finding 6 / Q10 empty-corpus coverage). NO WARNING threshold (Q1 decision — corpus size varies too widely; a fixed threshold is either too low on 5K-page wikis or too high on 100-page wikis).

**Cluster C — `tests/test_cycle28_first_query_observability.py` regression suite (AC6).** Eight tests per CONDITION 3 (one more than the 7-test baseline from the requirements doc; the +1 test is `test_sqlite_vec_load_no_info_on_failure_path` mandated by the design gate to divergent-fail against a future `finally:` regression per cycle-26 AC5 test-7 precedent): (1) successful extension load emits INFO with elapsed + db path, (2) 0.35s slow-load emits WARNING above 0.3s threshold, (3) fast sub-threshold load emits INFO only (no WARNING), (4) counter +1 exactly after first `_ensure_conn` call, (5) counter stable on fast-path (cached `self._conn`), (6) failure-path divergence — `sqlite_vec.load` raising produces NO INFO + counter stable + `_disabled=True`, (7) `BM25Index.__init__` emits INFO with `n_docs=2` + sub-assertion that empty-corpus still emits with `n_docs=0`, (8) counter monotonic across 3 constructor calls. All counter reads use monotonic-delta pattern (`baseline = get_X_count(); ...; delta = get_X_count() - baseline; assert delta == N`) per C6 — reload-safe against `importlib.reload(kb.query.embeddings)` cascades in sibling tests (cycle-20 L1 / T8). Monkeypatch discipline per C7: zero raw `time.perf_counter = ...` assignments in the test module; the WARN threshold is exercised via a slow `sqlite_vec.load` stub (real wall-clock elapsed), not by patching `perf_counter`.

**Cluster D — BACKLOG + CHANGELOG hygiene (AC7, AC8, AC9).** AC7 lands three BACKLOG.md edits per C13: (a) narrow HIGH-Deferred `query/embeddings.py` vector-index lifecycle entry to remove sub-item (b) "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation" (shipped this cycle); only sub-item (a) dim-mismatch AUTO-rebuild remains deferred. (b) Delete MEDIUM `src/kb/lint/augment.py::_post_ingest_quality — AC17-drop rationale for future reference` line — the "cache-invalidation work DROPPED, cycle-13 AC2 uses uncached `frontmatter.load`" rationale is duplicated in CHANGELOG-history cycle-13 AC2; keeping it in BACKLOG.md added no open work. (c) Delete LOW `CHANGELOG.md cycle-27 quick-reference commit tally` entry — CHANGELOG currently says "3 commits" which IS the correct value under the +1 self-referential rule (cycle-26 L1); the BACKLOG entry's claim "CHANGELOG says 2 commits" was stale. LOW section sentinel updated to `_All items resolved — see CHANGELOG cycle 28._` per BACKLOG.md format rule. AC8 codifies the commit-count convention in `CHANGELOG.md`'s existing entry-rule HTML-comment block: `<K> equals pre-doc-update branch commits + 1 for the landing doc-update that contains this changelog line (self-referential per cycle-26 L1 skill patch)`. Future cycles can grep the rule directly instead of re-reading `feature-dev` SKILL.md. AC9 — Step-2 pip-audit baseline matches cycles 25/26 exactly: 2 open advisories (diskcache CVE-2025-69872 + ragas CVE-2026-6587, both `fix_versions: []`). No-op CVE re-verify per cycle-27 AC7 skip-on-no-diff pattern; no BACKLOG re-stamp.

**Step-2 CVE baseline:** 2 open advisories (diskcache + ragas, both `fix_versions: []`, unchanged from cycles 25/26). **Step-11 PR-introduced diff:** empty — zero new CVEs. **Scope-outs preserved for future cycles:** env-override for thresholds, Prometheus/OTEL export, `rebuild_vector_index` duration / `model.encode` latency / end-to-end query tracing, INFO-log path redaction policy, warm-load hooks for sqlite-vec / BM25, per-cache-family BM25 counter split. Cycle-28 Q3 confirms no INFO log on the `_ensure_conn` failure path (existing WARNING is sufficient — no DEBUG on failure); Q7 confirms no path redaction on INFO logs (parity with existing `_get_model` INFO).

### Phase 4.5 — cycle 27 (2026-04-24)

7 AC / 2 src + 1 new test file / 3 commits. Tests: 2790 → 2801 (+11).

**CLI ↔ MCP parity for 4 read-only browse tools.** Narrow-scope cycle closing part of the Phase 4.5 HIGH "CLI ↔ MCP parity" BACKLOG item (BACKLOG.md:151) — operators working from scripts / cron / CI can now use `kb search`, `kb stats`, `kb list-pages`, `kb list-sources` instead of spawning an MCP client or calling `python -c "from kb.mcp.browse import ..."`. Pure internal refactor: no new trust boundaries, no filesystem writes, no new security enforcement points. Step 2 threat model skipped per skill clause; inline mini-threat-model captured 3 residual threats (T1-T3), all covered by existing MCP-tool validators.

**Cluster A — CLI subcommands (AC1-AC5).** `src/kb/cli.py` gains four Click subcommands: (1) `kb search <query> [--limit N] [--wiki-dir PATH]` calls `kb.query.engine.search_pages(wiki_dir=...)` directly + reuses the extracted `_format_search_results` helper; enforces `MAX_QUESTION_LEN` + `MAX_SEARCH_RESULTS` identically to the MCP `kb_search` tool. (2) `kb stats [--wiki-dir PATH]` forwards to `kb.mcp.browse.kb_stats` (which already accepts `wiki_dir`). (3) `kb list-pages [--type T] [--limit N] [--offset N]` and (4) `kb list-sources [--limit N] [--offset N]` forward to their MCP counterparts — `--wiki-dir` override is intentionally omitted this cycle because the MCP tool signatures would need to change (Q4 deferred to a future parity cycle). All subcommands use function-local imports (CONDITION 1 per cycle-23 AC4 boot-lean contract: bare `import kb` / `kb --version` must not pull `kb.mcp.browse`). Error-string returns (`"Error: ..."`) map to non-zero exit via `click.echo(..., err=True) + sys.exit(1)` (CONDITION 2 per Q3 Unix convention).

**AC1b formatter extraction.** `kb_search`'s inline result-formatting loop (snippet truncation + `[STALE]` markers + bold page IDs) extracted to `_format_search_results(results: list[dict]) -> str` in `kb.mcp.browse`. `kb_search` body reduced from ~17 LOC to 3 LOC (empty-check + length-gate + helper call). CLI `search` subcommand calls the same helper, guaranteeing parity with future MCP output tweaks. Two targeted regression tests pin the helper: empty-list behaviour (`"No matching pages found."`) and `[STALE]` marker preservation.

**Cluster B — BACKLOG + CVE hygiene (AC6-AC7).** AC6 narrows BACKLOG.md:151 `CLI ↔ MCP parity` entry to reflect the shipped commands (CLI count 10 → 14; remaining MCP-only tool count 18 → 14). Enumerates remaining quick-ship candidates for future cycles: write-path tools (8) + deeper browse/health tools (8). AC7 re-verifies `diskcache` (CVE-2025-69872) + `ragas` (CVE-2026-6587) — both still empty `fix_versions`, pip-audit output unchanged from cycle-26 baseline. NO BACKLOG edit per CONDITION 6 (same-day no-op noise avoidance).

**Step-2 CVE baseline:** 2 open advisories (diskcache + ragas, both `fix_versions: []`, unchanged from cycles 25-26). **Step-11 PR-introduced diff:** empty — zero new CVEs.

### Phase 4.5 — cycle 26 (2026-04-24)

8 AC (+AC2b) / 2 src + 1 new test file + 1 extended cycle-23 test / 7 commits. Tests: 2782 → 2790 (+8).

**Vector-model cold-load observability + BACKLOG hygiene.** Narrow observability cycle completing the cold-load-latency half of Phase 4.5 HIGH-Deferred `query/embeddings.py` sub-item 2 (sub-item 3 dim-mismatch observability shipped cycle 25). No new trust boundaries, no new filesystem-write contracts, no new security-enforcement surfaces.

**Cluster A — `src/kb/query/embeddings.py` cold-load observability (AC1, AC3, AC4).** Before cycle 26, the 0.8s + ~67 MB RSS `StaticModel.from_pretrained` call in `_get_model()` happened invisibly on the first user query that touched vector search — operators could not distinguish "MCP slow" from "vector model loading." Cycle 26 lands four additions: (a) `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS: float = 0.3` module constant, (b) `_vector_model_cold_loads_seen: int` counter + `get_vector_model_cold_load_count() -> int` getter (mirror of cycle-25 `_dim_mismatches_seen`; intentional asymmetry — this cold-load counter is incremented INSIDE `_model_lock` for exact counts per Q4 because the lock is already held for the `from_pretrained` call, whereas cycle-25's query-hot-path counter is lock-free per Q8), (c) `maybe_warm_load_vector_model(wiki_dir) -> threading.Thread | None` helper that spawns a daemon thread calling `_get_model()` when `_hybrid_available` AND `_vec_db_path(wiki_dir).exists()` AND `_model is None` (idempotent no-op otherwise), with a `_warm_load_target` wrapper that catches `Exception` and calls `logger.exception` per Q2 so daemon-thread failures are operator-visible, and (d) `_get_model()` instrumentation with `time.perf_counter` — INFO log `"Vector model cold-loaded in %.2fs"` always on successful load, plus WARNING `"exceeded %.2fs threshold (%.2fs actual). Consider warm-load on startup via maybe_warm_load_vector_model(wiki_dir)."` when elapsed ≥ 0.3s. Post-success ordering invariant (CONDITION 3): log + counter fire AFTER the successful `_model = ...` assignment, NEVER in `finally:` — this prevents misleading "cold-loaded" log lines on exception paths where `_model` stays `None`.

**Cluster B — `src/kb/mcp/__init__.py` warm-load wiring (AC2, AC2b).** `main()` now calls `maybe_warm_load_vector_model(WIKI_DIR)` between `_register_all_tools()` and `_mcp.run()`. Imports are function-local (CONDITION 8) to preserve cycle-23 AC4 boot-lean contract — bare `import kb.mcp` must not pull `kb.query.embeddings` or `kb.config` into `sys.modules`. The call is wrapped in `try/except RuntimeError` with `logger.warning` per Q6/CONDITION 11 so MCP still boots under resource pressure (thread-spawn exhaustion); a broader `except Exception` with `logger.exception` guards any other setup-path failure. AC2b (CONDITION 1) extends `tests/test_cycle23_mcp_boot_lean.py`'s heavy-deps allowlist to include `"kb.query.embeddings"` — the function-local-import contract is now machine-enforced; any future regression that hoists the import to module scope trips the existing cycle-23 test.

**Cluster C — `tests/test_cycle26_cold_load_observability.py` regression suite (AC5).** Seven tests per CONDITION 2: (1) `maybe_warm_load` returns `None` when vec_path missing, (2) returns Thread when vec_path exists + model unset, (3) idempotent when `_model` already set, (4) cold-load emits BOTH INFO `"cold-loaded in"` AND WARNING `"exceeded 0.30s threshold"` records on a 0.5s monkeypatched sleep (via `caplog.set_level(logging.INFO, logger="kb.query.embeddings")` per CONDITION 4 — defensive against pytest's default WARNING root threshold), (5) counter increments exactly once per successful cold-load across reset cycles, (6) subprocess-isolated sys.modules probe confirms bare `import kb.mcp` does NOT load `kb.query.embeddings` (Q10a — companion to cycle-23 boot-lean + AC2b allowlist), (7) warm-load thread swallows exception + emits `logger.exception("Warm-load thread failed")` with the `RuntimeError` text in `exc_info` (Q10b — pins CONDITION 10 against silent stderr fallout). All tests call `thread.join(timeout=5)` per T3 to prevent `_reset_model()` from blocking on a still-held `_model_lock`.

**Cluster D — BACKLOG + CVE hygiene (AC6, AC7, AC8).** AC6 (CONDITION 7): the `tests/test_phase4_audit_concurrency.py single-process file_lock coverage` MEDIUM entry (BACKLOG.md:160-161) is resolved by cycle-23 AC7 which shipped `tests/test_cycle23_file_lock_multiprocessing.py` — `rg "ctx\.Process|mp\.Process|get_context"` confirms the test exercises `multiprocessing.get_context("spawn")` + `ctx.Process(...)` + Event handshake + PID-file assertion + `@pytest.mark.integration`. Entry deleted. AC7 (CONDITION 6): cycle-26 pip-audit recheck against cycle-25 baseline shows UNCHANGED output — both `diskcache` (CVE-2025-69872, GHSA-w8v5-vhqr-4h9v) and `ragas` (CVE-2026-6587, GHSA-95ww-475f-pr4f) still have empty `fix_versions`. NO BACKLOG edit per Q12 — the cycle-25 2026-04-24 stamp is sufficient (same-day recheck is no-op noise). Per cycle-21 L1: document the skip in the commit message. AC8 (CONDITION 12): narrow the HIGH-Deferred `query/embeddings.py` vector-index lifecycle entry to reflect cycle-26 AC1-AC5 shipped (cold-load observability + warm-load hook for sub-item 2). Add new Q16 follow-up sub-item: "first-query observability — `VectorIndex._ensure_conn` sqlite-vec extension load + BM25 build latency instrumentation" (deferred to a future observability cycle; cycle-26 covers only `_get_model` cold-load).

**Step-2 CVE baseline:** 2 open advisories (diskcache + ragas, both `fix_versions: []`; unchanged from cycle 25). **Step-11 PR-introduced diff:** empty — zero new CVEs.

### Phase 4.5 — cycle 25 (2026-04-24)

10 AC / 2 src + 3 new test files / 6 commits. Tests: 2768 → 2782 (+14).

**Observability-layer follow-ups + operator-facing hardening.** Narrowly scoped cycle completing three Phase 4.5 follow-ups that surfaced during cycle 24 (rebuild_indexes .tmp awareness) or that had observability-only variants of larger deferred work (dim-mismatch auto-rebuild, compile_wiki per-source rollback). No new security surface; no new filesystem-write contract.

**Group A — `src/kb/compile/compiler.py` `rebuild_indexes` .tmp cleanup (AC1, AC2).** Cycle-24 AC5/AC6/AC8 landed the tmp-then-replace flow for `rebuild_vector_index`. `rebuild_indexes` (cycle-23 clean-slate helper) still only unlinked the main `vector_index.db` — a crashed-prior-run `.tmp` sibling persisted until the next `rebuild_vector_index` entry triggered its AC6 cleanup. Cycle-25 extends `rebuild_indexes` to `Path.unlink(missing_ok=True)` the sibling `<vec_path>.tmp` immediately after the main unlink. Q9 decision: derive tmp from the EFFECTIVE `vector_path` (line 599 of compiler.py) so callers using the optional `vector_db=` override see their sibling `.tmp` cleaned too. Q1 / CONDITION 1: a tmp-unlink failure produces a compound error (`"vec: <err_a>; tmp: <err_b>"`) but `result["vector"]["cleared"]` stays `True` when the main unlink succeeded — hygiene failures must not downgrade correctness status.

**Group B — `src/kb/query/embeddings.py` dim-mismatch operator guidance + counter (AC3, AC4, AC5).** `VectorIndex.query`'s existing `logger.warning` on stored-dim vs query-dim mismatch was silent on remediation. Cycle-25 extends the warning to include `"Run 'kb rebuild-indexes --wiki-dir <path>' to realign"`, where the wiki-dir substitution uses `self.db_path.parent.parent` per Q7 — the inverse of `_vec_db_path(wiki_dir) = wiki_dir.parent / ".data" / "vector_index.db"`. Passing `self.db_path` directly would emit a `kb rebuild-indexes --wiki-dir <.db-file>` command that fails `rebuild_indexes`'s containment validator. A new module-level `_dim_mismatches_seen: int` counter + `get_dim_mismatch_count() -> int` getter exposes event counts for diagnostic scripts. Counter increments on EVERY mismatch query (decoupled from `_dim_warned`'s once-per-instance log gate per CONDITION 3). Q8: approximate under concurrent threads (no lock around `+= 1`) — the counter is diagnostic, not billing-grade telemetry, and Python's GIL keeps skew well under 5% even at 10-thread × 50-query load.

**Group C — `src/kb/compile/compiler.py` `compile_wiki` in_progress marker (AC6, AC7, AC8, CONDITION 13).** Before each `ingest_source` call in `compile_wiki`'s per-source loop (after `pre_hash = content_hash(source)` succeeds, before the main try block — Q5 placement), cycle-25 writes `manifest[rel_path] = f"in_progress:{pre_hash}"` under `file_lock(manifest_path, timeout=1.0)` (Q4). On success, `ingest_source`'s own manifest write (via cycle-19 AC13 `manifest_key=rel_path`) overwrites the marker with the real hash. On normal Python exceptions, the existing `except Exception` block replaces with `failed:{pre_hash}`. The marker only survives HARD-KILL / power-loss between the pre-marker write and `ingest_source`'s overwrite. At `compile_wiki` entry, a new scan grepping the manifest for `in_progress:`-prefixed values logs a `logger.warning` naming every stale source (truncation dropped per Step-8 plan-gate amendment — operators need per-source correlation). Log-only per Q2: operator decides remediation via `kb rebuild-indexes` or manual investigation. Q10: concurrent `kb compile` invocations from a sibling process may emit the warning for the OTHER process's in-flight work — documented in CLAUDE.md as accepted noise. CONDITION 13: full-mode prune at the tail of `compile_wiki` exempts `in_progress:`-valued entries from the stale-key deletion list — otherwise full-mode compile silently deletes the markers AC7 says operators should see.

**Group D — BACKLOG maintenance + CVE re-verify (AC9, AC10).** Deleted `rebuild_indexes .tmp awareness` BACKLOG entry (line 111) — resolved by AC1. Narrowed vector-index lifecycle entry (line 109) to reflect sub-item 3 observability-shipped, auto-rebuild still deferred. Narrowed `compile_wiki per-source rollback` MEDIUM entry to reflect AC6/AC7/AC8 observability variant shipped, full receipt-file rollback still deferred. Diskcache CVE-2025-69872 re-verified 2026-04-24 per AC9: `pip index versions diskcache` confirms 5.6.3 is LATEST INSTALLED; `pip-audit --format=json` reports empty `fix_versions`. Ragas CVE-2026-6587 re-confirmed 2026-04-24 per AC10: 0.4.3 = LATEST INSTALLED; empty `fix_versions`. BACKLOG date stamps updated accordingly.

**Step-2 CVE baseline:** 2 open advisories (diskcache + ragas, both `fix_versions: []`). **Step-11 PR-introduced diff:** empty — zero new CVEs.

### Phase 4.5 — cycle 24 (2026-04-23)

15 AC / 4 src + 5 new test files / 9 commits. Tests: 2743 → 2768 (+25).

**Evidence-trail race closure + vector-index atomic rebuild + file_lock exponential backoff.** Targeted pre-Phase-5 cycle covering two Phase 4.5 HIGH / HIGH-Deferred items (vector-index atomic rebuild sub-item 1, `_write_wiki_page` two-write race) plus three MEDIUM items (file_lock 50ms polling floor, evidence-append error surfacing, stale BACKLOG maintenance). A new Cluster E (sentinel section-span hardening) was surfaced by Step-2 threat model T5 and joined the scope as a load-bearing prerequisite for AC1.

**Group A — `src/kb/ingest/evidence.py` section-span sentinel search (AC14, AC15).** Pre-cycle-24 `append_evidence_trail` used whole-file `content.index(SENTINEL)` — an attacker-planted `<!-- evidence-trail:begin -->` substring in the page body, frontmatter, or `## References` section would hijack future evidence appends (T5 threat). Cycle 24 rewrites the search as SPAN-LIMITED: `re.search(r"^## Evidence Trail[ \t]*\r?\n", ...)` finds the real section header (CRLF + trailing-whitespace tolerant), then `re.search(r"^## ", ...)` bounds the section span to the next `^## ` heading or EOF. Sentinel search runs ONLY within `content[header_end:section_end]`. Fallback matrix: (i) header + sentinel-in-span → existing cycle-1 H12 behaviour preserved; (ii) header + no-sentinel-in-span → migration path plants sentinel at header end; (iii) no header at all → fresh section at EOF, body sentinel ignored and left intact in the body. New helper `render_initial_evidence_trail(source_ref, action, entry_date=None) -> str` reuses `format_evidence_entry` for pipe neutralization; used by Group B for inline first-write rendering.

**Group B — `src/kb/ingest/pipeline.py` evidence-trail inline render + StorageError surfacing (AC1, AC2, AC3, AC4).** `_write_wiki_page` now concatenates the initial `## Evidence Trail` section into the rendered page payload BEFORE writing, for BOTH branches per design CONDITION 1: the `exclusive=False` branch writes via `atomic_text_write(rendered_with_trail, ...)`; the `exclusive=True` branch writes via `os.write(fd, rendered_with_trail.encode("utf-8"))` inside the existing `os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` span. The post-write `append_evidence_trail` call is REMOVED for new pages in both branches — eliminating the two-write race where a crash between body write and trail write leaves a page on disk without provenance. `_update_existing_page`'s `append_evidence_trail` call is wrapped in `try/except OSError`; on failure it raises `StorageError(kind="evidence_trail_append_failure", path=page_path)` for cycle-20 taxonomy-coverage (non-OSError exceptions propagate unchanged, preserving the cycle-20 scope boundary). Path redaction pinned via cycle-20 `__str__` contract (`"evidence_trail_append_failure: <path_hidden>"`).

**Group C — `src/kb/query/embeddings.py` vector-index atomic rebuild (AC5, AC6, AC7, AC8).** `rebuild_vector_index` now writes to `<vec_db>.tmp`, then `os.replace(tmp_path, vec_path)` atomically swaps. Stale `.tmp` from a crashed prior run is unlinked unconditionally at the FIRST statement — before `_hybrid_available`, `_is_rebuild_needed`, and `_rebuild_lock` gates — so the next invocation cleans up even on a skip path (design CONDITION from Q7). Both empty-pages and populated-pages branches route through the same tmp-then-replace flow (design CONDITION 5). The `.build()` + `os.replace` pair is wrapped in `try/except`; on mid-build exception `tmp_path.unlink(missing_ok=True)` runs before re-raise (clean-slate policy from Q5). New helper `_evict_vector_index_cache_entry(vec_path)` pops `_index_cache` AND explicitly calls `popped._conn.close()` BEFORE `os.replace` (design CONDITION 2): on Windows NTFS, a cached `sqlite3.Connection` holds a read handle that blocks `os.replace` with `PermissionError [WinError 5]`; explicit close unpins it. `VectorIndex.build` signature extended with keyword-only `db_path` kwarg (AC7 via `*` separator, design CONDITION 11): `db_path is not None` override targets the custom path without mutating `self._stored_dim`, preventing instance-state drift.

**Group D — `src/kb/utils/io.py` `file_lock` exponential backoff (AC9, AC10).** New module constant `LOCK_INITIAL_POLL_INTERVAL = 0.01` sets the backoff floor; `LOCK_POLL_INTERVAL = 0.05` (unchanged value) is now the CAP. New helper `_backoff_sleep_interval(attempt_count) -> float` computes `min(LOCK_INITIAL_POLL_INTERVAL * (2 ** min(attempt_count, 30)), LOCK_POLL_INTERVAL)` reading both constants at CALL TIME (module attribute lookup, not function-entry snapshot) so test monkeypatches on either constant take effect immediately. The `2 ** min(attempt, 30)` exponent cap defends against OverflowError under degenerate monkeypatch conditions (`LOCK_POLL_INTERVAL = 0` + spinning). Exponential backoff applies to ALL THREE polling sites (design CONDITION 7): normal `FileExistsError` retry, POSIX `ProcessLookupError` stale-steal recovery, and Windows `OSError` stale-steal recovery. `attempt_count` initialized once outside the retry loop and incremented after each `time.sleep`. Existing cycle-2 monkeypatch tests (`test_backlog_by_file_cycle2.py:172,210` setting `LOCK_POLL_INTERVAL = 0.01`) continue to clamp all observed sleeps per the CAP semantic pinned in design CONDITION 3.

**Group E — `BACKLOG.md` + `CHANGELOG.md` + `CHANGELOG-history.md` + `CLAUDE.md` (AC11, AC12, AC13).** BACKLOG.md edits: (1) DELETED HIGH-Deferred multiprocessing `tests/` entry (shipped cycle 23); (2) UPDATED vector-index lifecycle entry striking sub-item 1 (atomic rebuild shipped this cycle) and sub-item 4 (`_index_cache` cross-thread lock shipped across cycles 3/6/24); (3) UPDATED `ingest/pipeline.py` body-write + evidence-append entry narrowing to "consolidation still deferred" (AC1 + AC2 shipped); (4) UPDATED `utils/io.py` atomic_json_write entry noting AC9 eliminated the 50ms polling floor (JSONL-migration remains); (5) NEW `utils/io.py` fair-queue lock entry (T3 residual from threat model); (6) NEW `compile/compiler.py` `rebuild_indexes .tmp` awareness entry (R2 Codex observation — belt-and-suspenders hygiene). Diskcache CVE-2025-69872 re-verified 2026-04-23 per AC12: `pip index versions diskcache` confirms 5.6.3 is LATEST + INSTALLED; `pip-audit --format=json` reports empty `fix_versions`. Ragas CVE-2026-6587 re-confirmed 2026-04-23 per AC13: 0.4.3 = LATEST INSTALLED; empty `fix_versions`. CLAUDE.md test count bumped 2743 → 2766; new API notes for `VectorIndex.build(*, db_path=)`, `append_evidence_trail` section-span search, and `file_lock` exponential backoff.

**Step-2 CVE baseline:** 2 open advisories (diskcache 5.6.3 / CVE-2025-69872; ragas 0.4.3 / CVE-2026-6587) — both `fix_versions: []`. **Step-11 PR-introduced diff:** empty — zero new CVEs introduced by cycle-24 changes.

**Step-14 PR review:** R1 Codex APPROVE (zero findings). R1 Sonnet REQUEST_CHANGES — 1 BLOCKER (fenced-code header hijack), 2 MAJOR (`_evict_vector_index_cache_entry` close-outside-lock race; `test_sentinel_only_no_header_creates_fresh_section` not divergent-fail), 2 NITs — all fixed in commit `4e22703`. R2 Codex verification: all R1 findings VERIFIED-FIXED; one new MAJOR (`_FENCED_CODE_RE` missed tilde + 4+ backtick fences) fixed in R2-fix commit with `_mask_fenced_blocks` rewritten as a line-walk CommonMark parser + `test_tilde_fence_and_four_backtick_fence_respected` added (+1 test → 2768 total). R3 Sonnet APPROVE-WITH-NIT: audit-doc drift sweep confirmed threat-model T1..T10 mitigations match shipped code; 3 numeric-drift NITs (test count, commit count, "5 new tests" wording) fixed in this doc pass.

### Phase 4.5 — cycle 23 (2026-04-23)

8 AC / 6 src + 4 new tests / 6 commits. Tests: 2725 → 2743 (+18).

**MCP boot latency + operator-scoped `rebuild_indexes` + cross-module integration coverage.** Targeted pre-Phase-5 cycle covering three Phase 4.5 HIGH items and one HIGH-Deferred test-infra item that prior cycles could not land without the cycle-19 AC15 owner-module monkeypatch contract first landing.

**Group A — `src/kb/mcp/core.py` + `kb/mcp/__init__.py` + `kb/query/__init__.py` + `kb/ingest/pipeline.py` PEP-562 lazy shim (AC4, AC5).** A bare `import kb.mcp` no longer pulls `anthropic`, `networkx`, `sentence-transformers`, `kb.query.engine`, `kb.ingest.pipeline`, or `kb.feedback.reliability` into `sys.modules`; all load only when an MCP tool that actually uses them runs. Achieved via three coordinated changes: (1) `kb.mcp.__init__` defers the `from kb.mcp import browse, core, health, quality` tool-registration imports from module top to a new `_register_all_tools()` helper called inside `main()`; (2) `kb.mcp.core` adds a PEP-562 `__getattr__` + closed `_LAZY_MODULES` dict (`ingest_pipeline`, `query_engine`, `reliability`) that loads on first external attribute access — preserving the cycle-19 AC15 contract (`monkeypatch.setattr(mcp_core.ingest_pipeline, "ingest_source", fake)` still works because `__getattr__` returns the real module object) while keeping `import kb.mcp.core` lean; (3) `kb.query.__init__` migrates to the same PEP-562 pattern that `kb.ingest.__init__` already uses, so `import kb.query` alone no longer triggers `kb.query.engine`. Function-body `from kb.X import Y` bindings added inside `kb_query`, `kb_ingest`, and `kb_ingest_content` so bare names resolve under function scope even though the module-top imports are gone. `_TEXT_EXTENSIONS` relocated from `kb.ingest.pipeline:65` to `kb.mcp.core` (MCP-only consumer; zero cross-module cost). Threat I3 (closed allowlist) pinned via subprocess probe asserting `getattr(kb.mcp.core, "<arbitrary>")` raises `AttributeError`.

**Group B — `src/kb/compile/compiler.py` + `src/kb/cli.py` clean-slate rebuild affordance (AC1, AC2, AC3).** `compile_wiki(incremental=False)` docstring now explicitly enumerates the three derived stores `--full` does NOT invalidate — (a) hash **manifest** deletion-prune (runs only via `detect_source_drift`), (b) **vector** index (rebuilt incrementally inside `ingest_source`), (c) in-process **LRU** caches (template + frontmatter + purpose) — and points operators at the new helper for a true clean-slate recompile. New public `rebuild_indexes(wiki_dir=None, *, hash_manifest=None, vector_db=None) -> dict` helper validates `wiki_dir` resolves under `PROJECT_ROOT` (threat I1; raises `ValidationError`), acquires `file_lock(HASH_MANIFEST, timeout=1.0)` before unlinking to avoid racing a concurrent `compile_wiki` save (cycle-23 Q3 design decision), unlinks the vector DB, clears three LRU cache families (`kb.ingest.extractors.clear_template_cache`, `kb.utils.pages._load_page_frontmatter_cached`, `kb.utils.pages.load_purpose`), and appends one audit line to `wiki/log.md` best-effort (threat I5; audit `OSError` logs warning + sets `audit_written=False`, does not abort). Return shape surfaces per-target error strings so CLI callers can distinguish "lock busy" timeouts from missing-file no-ops. `kb rebuild-indexes [--wiki-dir PATH] [--yes]` CLI command prompts via `click.confirm(abort=True)` on TTY, skips the prompt with `--yes`, and lazy-imports `kb.compile.compiler` inside the command body so the cycle-8 L1 `kb --version` short-circuit is preserved (pinned via subprocess probe).

**Group C — `tests/test_cycle23_workflow_e2e.py` hermetic end-to-end workflow (AC6).** Single test drives `ingest_source` (two articles, explicit `extraction=dict` → no LLM) → `query_wiki` (stubbed `kb.query.engine.call_llm`) → `run_all_checks` against a single `tmp_project` fixture. Monkeypatches `kb.query.embeddings.rebuild_vector_index` + `_get_model` + `kb.query.engine._flag_stale_results` for hermeticity (cycle-23 Q12). Asserts `pages_created` on first ingest, `pages_created or pages_updated` on second ingest (source-merge path), query `citations` / `source_pages` key presence, and `lint_report["summary"]["error"] == 0`. Closes the Phase 4.5 HIGH "no end-to-end ingest→query workflow" backlog entry by exercising cross-module glue that unit tests cannot reach.

**Group D — `tests/test_cycle23_file_lock_multiprocessing.py` cross-process `file_lock` regression (AC7).** `@pytest.mark.integration` test uses `mp.get_context("spawn")` unconditional (cycle-23 Q13) to spawn a child that holds `kb.utils.io.file_lock` for 2 s while writing its PID to a sentinel. Parent asserts: PID sentinel matches child PID, parent's `file_lock(path, timeout=0.5)` raises `TimeoutError` while child holds, child exits 0, parent reacquires after release. Top-level worker function `_child_hold_lock` is picklable for `spawn` (cycle-23 Q13); `child.join(timeout=10)` + `child.kill()` fallback bounds worst-case hang. Closes the Phase 4.5 HIGH-Deferred "multiprocessing tests for cross-process `file_lock` semantics" backlog entry.

**Group E — docs + BACKLOG cleanup (AC8).** Four resolved Phase 4.5 items deleted (not strikethrough) from BACKLOG.md — MCP boot heavy-imports (lines 101-102), `compile_wiki(incremental=False)` opacity (lines 86-87), missing E2E ingest→query workflow test, and multiprocessing file_lock HIGH-Deferred. One BACKLOG entry added: ragas 0.4.3 CVE-2026-6587 (SSRF in `_try_process_local_file` / `_try_process_url`; no upstream fix; dev-eval-only dep with zero direct imports in `src/kb/` — same handling class as diskcache CVE-2025-69872). CLAUDE.md test count bumped 2725 → 2742 (post-cycle-23 `pytest --collect-only`); CLI command count 7 → 8 (`kb rebuild-indexes` added); module map notes the `rebuild_indexes` helper on `kb.compile.compiler`. README documents `kb rebuild-indexes` in both the CLI table and the Development Commands block.

**Step-2 CVE baseline:** 2 open advisories (diskcache 5.6.3 / CVE-2025-69872; ragas 0.4.3 / CVE-2026-6587) — both `fix_versions: []`; Step 11.5 skip path. **Step-11 PR-introduced diff:** empty — zero new CVEs from cycle-23 code changes.

### Phase 4.5 — cycle 22 (2026-04-22)

14 AC / 3 src + 2 new tests / 11 commits. Tests: 2720 → 2725 (+5; 1 Windows-skip).

**Pre-Phase-5 backlog hardening.** Targeted cleanup cycle covering three production gaps (all Cycle 21 / 22 backlog candidates) + nine stale BACKLOG items that were verified already-resolved in prior cycles (17, 18, 19).

**Group A — `src/kb/ingest/pipeline.py` wiki-path guard (AC1-AC4).** `ingest_source` now raises `kb.errors.ValidationError("Source path must not resolve inside wiki/ directory")` when the resolved `source_path` is inside the resolved `effective_wiki_dir`. Closes the circular-knowledge loop where an LLM-generated wiki page could be re-ingested as if it were a raw source, defeating the `raw/` immutability invariant. Guard mirrors the existing raw-dir pattern (`os.path.normcase` on both sides + `Path.relative_to`) so symlinks / junctions (T1) and Windows case variants (T2) cannot bypass. Message is a fixed string — no `source_path` interpolation — so absolute wiki paths never leak through CLI / MCP logs (T3). Placed BEFORE the raw-dir check so wiki paths surface the specific error instead of the generic `ValueError: must be within raw/`; placed BEFORE the `_emit_ingest_jsonl("start", ...)` emission at line ~1222 so rejected wiki paths never produce an orphan `stage="start"` row in `ingest_log.jsonl` (cycle-18 L3 orphan-start rule). `effective_wiki_dir` computation moved up next to `effective_raw_dir` to enable this placement. `ValidationError` added to the existing `from kb.errors import ...` line. Asymmetry with the raw-dir guard's legacy `ValueError` is accepted this cycle — follow-up cycle 23 will migrate under its own caller-grep gate (Q1 design-gate decision).

**Group B — `src/kb/ingest/extractors.py` grounding clause (AC5, AC6).** `build_extraction_prompt` output now contains the exact phrase `Ground every extracted field in verbatim source content. When uncertain whether a claim is in the source, use null.` positioned immediately AFTER the existing "If a field cannot be determined from the source, use null." line AND BEFORE the `<source_document>` sentinel fence, so adversarial raw content inside the fence cannot reflect a counter-instruction (T6). Single-point change in the shared prompt builder applies universally to all 10 source-type extractions — no per-YAML edits. Best-effort advisory only; claim-level provenance verification remains tracked under Phase 5 HIGH LEVERAGE epistemic-integrity backlog items.

**Group C — `tests/test_cycle5_hardening.py` spy replacement (AC7-AC9).** `test_synthesis_prompt_uses_wikilink_citation_format` dropped its `inspect.getsource(engine.query_wiki) + inspect.getsource(engine._query_wiki_body)` substring check (survived a full revert — cycle-11 L1 / `feedback_inspect_source_tests`) in favour of a monkeypatched `kb.query.engine.call_llm` spy that captures the actual prompt string sent to the synthesiser. Assertions now pair: `spy.call_count >= 1` (AC9 vacuous-test guard per cycle-16 L2), `any("[[page_id]]" in p for p in captured_prompts)` (AC8 positive), and `not any("[source: page_id]" in p for p in captured_prompts)` (AC8 negative — Step 08 plan-gate gap close). Module-attribute spy target catches BOTH the trampoline (`query_wiki`) and the inner `_query_wiki_body` call sites without path-dependent assertions. The now-unused top-level `import inspect` removed.

**Group E — `tests/test_cycle22_wiki_guard_grounding.py` (new, AC10-AC13).** Four regression pins: AC10 asserts `ingest_source` raises `ValidationError` for a path inside the default `WIKI_DIR` AND the message contains no absolute path substring (T3 pin); AC11 asserts the same for a caller-supplied `wiki_dir=<custom>` arg; AC12 asserts a legitimate `raw/articles/*.md` path passes the guard and reaches the extraction pipeline (revert-detector — if the guard wires to `raw_dir` by mistake or rejects everything, this test fails); AC13 asserts `build_extraction_prompt` output for article / paper / repo / video / podcast templates all contain the grounding clause AND the clause index < `<source_document>` fence index. `ValidationError` is imported inside each test function to late-bind against the current `kb.errors` module object — defeats the cycle-20 L1 reload-drift class.

**Group F — docs + BACKLOG cleanup (AC14).** Nine verified-resolved items removed from BACKLOG.md:
1. `tests/test_v0p5_purpose.py` purpose-threading coverage gap — closed by `tests/test_v0p5_purpose.py:97` (`test_cycle17_ac14_query_wiki_threads_purpose_to_synthesis_prompt`).
2. `compile/compiler.py:367-380` full-mode manifest pruning — closed by cycle-17 AC1 prune-base fix (`raw_dir.resolve().parent` + `file_lock` symmetry).
3. `compile/compiler.py:343-347` manifest write hash-key inconsistency — closed by cycle-19 AC12/AC13 `manifest_key_for` threading (evidence: `tests/test_cycle19_manifest_key_consistency.py`).
4. `compile/linker.py:178-241` `inject_wikilinks` cascade-call write race — closed by cycle-19 per-page `file_lock` + `inject_wikilinks_batch`.
5. `models/page.py` dataclasses are dead — closed by cycle-17 keep-and-document decision (`tests/test_cycle17_models_dead_code.py`).
6. `ingest/pipeline.py` observability — closed by cycle-18 AC11-AC13 `_emit_ingest_jsonl` + 16-hex `request_id` correlation (`tests/test_cycle18_ingest_observability.py`).
7. `tests/` thin MCP tool coverage — closed by cycle-17 `tests/test_cycle17_mcp_tool_coverage.py` (covers `kb_compile_scan`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`). This discovery at Step-04 R2 Codex review dropped the planned Group D (8 redundant MCP tests) from cycle 22 entirely.
8. `ingest/pipeline.py:712-721` inject_wikilinks per-page loop — closed by cycle-19 AC1 `inject_wikilinks_batch`.
9. `ingest/pipeline.py:682-693` manifest hash-key race under concurrent ingest — closed by cycle-19 atomic `_is_duplicate_content_and_reserve` under `file_lock(HASH_MANIFEST)`. CHANGELOG breadcrumb per item mitigates re-add (T11). CLAUDE.md test-count updated atomically at both stale locations (Implementation Status + Testing section) per cycle-20 L2 drift-class rule; count reflects post-cycle-22 `pytest --collect-only` output.

**Step-10 CI reload-drift fixes.** Full-suite pytest exposed two reload-leak classes that isolated-run cycle-22 tests didn't hit:
1. **cycle-18 L1 snapshot-bind**: the new wiki-path guard used the module-top `from kb.config import WIKI_DIR` snapshot; under full-suite ordering a sibling test's `importlib.reload(kb.config)` decouples the snapshot from the current `kb.config.WIKI_DIR` and `tmp_kb_env`'s mirror-rebind equality check skips the rebind. Fix: guard now does `import kb.config as _kb_config` + attribute access at call time. Existing `effective_wiki_dir` snapshot unchanged (cycle-18 L1 rule: do not refactor working patterns proactively).
2. **cycle-20 L1 reload-drift on exception classes**: AC10/AC11 test functions imported `ValidationError` from `kb.errors` at entry; under reload-leak cascade, production `kb.ingest.pipeline.ValidationError` retains the OLD class pointer while `kb.errors.ValidationError` is a NEW class — `pytest.raises(OLD_CLS)` couldn't catch the `NEW_CLS` instance. Fix: late-bind via `pipeline_mod.ValidationError` so tests catch exactly what production raises.
3. **cycle-19 L2 reload-leak on `TEMPLATES_DIR`**: AC13 hit a stale `_load_template_cached` LRU binding after cycle-15's reload. Fix: monkeypatch `kb.ingest.extractors.TEMPLATES_DIR` back to the canonical repo templates dir at test entry.
4. **AC12 hermetic refactor**: passes explicit `wiki_dir=` + `raw_dir=` args instead of relying on `tmp_kb_env` autouse patching.

**Threat coverage.** All cycle-22 threats IMPLEMENTED. T7 + T10 marked N/A (Group D dropped). **PR-introduced CVE at Step 11:** `lxml CVE-2026-41066` appeared in branch pip-audit (not in Step-02 baseline — advisory dropped mid-cycle). Patched by bumping `requirements.txt` `lxml==5.4.0` → `lxml==6.1.0`; `crawl4ai==0.8.6` declares `lxml~=5.3` but grep confirms no runtime `import crawl4ai` sites in `src/kb/` (used as external `crwl` CLI only). Post-patch pip-audit shows only the pre-existing `diskcache CVE-2025-69872` (Class A, no upstream fix, tracked in BACKLOG Phase 4.5 MEDIUM). 0 open Dependabot alerts.

### Phase 4.5 — cycle 21 (2026-04-21)

30 AC / 4 src / 1 commit. Tests: 2697 → 2710 (+13). **CLI subprocess backend** — adds `KB_LLM_BACKEND` env-var routing so `call_llm` / `call_llm_json` can dispatch prompts to locally-installed AI CLI tools instead of the Anthropic SDK. The Anthropic path is completely unchanged (default `"anthropic"` value is a no-op). **New constants in `src/kb/config.py`**: `CLI_TOOL_COMMANDS` (MappingProxyType, 8 backends), `CLI_TOOL_MODELS` (scan/write/orchestrate per backend; empty string for single-model CLIs), `CLI_INSTALL_HINTS` (one-line install hint per backend), `CLI_SAFE_ENV_KEYS` (13-key env allowlist), `CLI_BACKEND_ENV_INJECT` (per-backend secret key names), `CLI_VALID_BACKENDS` (frozenset), `CLI_MAX_CONCURRENCY = 2`, `MAX_CLI_STDOUT_BYTES = 2_000_000`, `CLI_PROMPT_VIA_ARG = frozenset({"gemini"})`. **New helpers**: `get_cli_backend() -> str` (reads `KB_LLM_BACKEND` at call time; 32-char cap; unknown value raises `ValueError` without echoing raw env — T7); `get_cli_model(tier) -> str` (respects `KB_CLI_MODEL_<TIER>` override). **New module `src/kb/utils/cli_backend.py`**: `check_cli_available(backend)` via `shutil.which`; `call_cli(prompt, *, backend, model, timeout)` with `shell=False`, scrubbed subprocess env (`_scrub_env`), stdin delivery for all backends except Gemini (`--prompt` arg, weaker isolation documented — T8), `MAX_CLI_STDOUT_BYTES` cap + `_redact_secrets` on stdout before return (T3), redacted stderr on non-zero exit (T3), `LLMError(kind="not_installed")` guard before subprocess dispatch (T2), `LLMError(kind="timeout")` on `TimeoutExpired` (T5), per-backend `threading.Semaphore` with double-checked lazy init under `_semaphore_lock` (T6); `call_cli_json(...)` with three-stage JSON extraction (`json.loads` → fenced-block strip bounded at `MAX_CLI_JSON_SCAN_BYTES` → depth-bounded brace scan) + `jsonschema.validate` (T4); `_check_no_secrets_on_argv` called unconditionally on static argv elements + on Gemini `--prompt` value (T8). **Routing gate in `src/kb/utils/llm.py`**: `get_cli_backend` + `get_cli_model` imported at module top from `kb.config`; inside `call_llm` / `call_llm_json`, `from kb.utils import cli_backend` is a **function-local lazy import** inside the non-anthropic branch only (zero import-time side effects for anthropic-only deployments — AC16). System prompt prepended as `"System: {system}\n\n{prompt}"` when `system` is set. API integration (LiteLLM / per-provider SDK) explicitly deferred to BACKLOG. Security: all 8 threats IMPLEMENTED after Codex Step-11 review closed T4.2 (fence regex bounded), T8.3 (argv token check unconditional), and T1.4 test (stdin round-trip). 0 PR-introduced CVEs.

### Phase 4.5 — cycle 20 (2026-04-21)

21 AC / 10 src / 13 commits (10 feature/test + 1 R1-fix + 1 R2-fix + 1 R3-fix). **Exception taxonomy** (`kb.errors` — HIGH #2 closure): new `KBError(Exception)` base + `IngestError` / `CompileError` / `QueryError` / `ValidationError` / `StorageError` specialisations in a new `src/kb/errors.py` (~75 LOC). `LLMError` (at `kb.utils.llm.py:381`) and `CaptureError` (at `kb.capture.py:544`) reparent from `Exception` to `KBError`; MRO preserves `isinstance(err, Exception)` so every existing outer catch still fires. `StorageError(msg, *, kind=None, path=None)` stores `path` for local-debug introspection but `__str__` emits only `f"{kind}: <path_hidden>"` when both fields are set — prevents log-aggregator filesystem-path disclosure (T1 mitigation). `kb/__init__.py` extends `__all__` and adds a PEP 562 `__getattr__` branch so `from kb import KBError, IngestError, CompileError, QueryError, ValidationError, StorageError` resolves lazily without forcing early `kb.config` load (preserves the `--version` short-circuit). **Narrow AC5 hot-path wraps** at ingest + query outer boundaries only (3-site scope after R1-grep confirmed `compile_wiki` has no single outer `except Exception` — dropped from the AC per cycle-17 L1 blast-radius rule): `ingest_source` outer converts unexpected `Exception` subclasses to `IngestError(str(exc)) from exc`; `query_wiki` split into a thin outer trampoline + `_query_wiki_body` so the trampoline wraps unexpected exceptions to `QueryError`. Expected kinds (`KBError`, `OSError`, `ValueError`) pass through unchanged. `BaseException` subclasses NOT inheriting `Exception` (`KeyboardInterrupt`/`SystemExit`/`GeneratorExit`) propagate without wrap. **Slug-collision O_EXCL hardening** (HIGH #16 closure): `_write_wiki_page(path, ..., *, exclusive: bool = False)` gains a keyword-only `exclusive` flag. When True, uses `os.open(O_WRONLY|O_CREAT|O_EXCL)` plus POSIX `O_NOFOLLOW` (guarded by `hasattr(os, "O_NOFOLLOW")`) and `0o644` mode; on `FileExistsError` raises `StorageError("summary_collision", kind="summary_collision", path=...)`; on write-phase exception AFTER successful O_EXCL reservation, unlinks the zero-byte poison so retries can re-reserve cleanly. Default `exclusive=False` preserves byte-identical legacy `atomic_text_write` path. `_run_ingest_body` summary write (`pipeline.py:1254`) and `_process_item_batch` item write (`pipeline.py:957`) pass `exclusive=True`; on `StorageError(kind="summary_collision")` pivot to `_update_existing_page`. **`_update_existing_page` split** into a thin wrapper + `_update_existing_page_body` under unconditional `file_lock(page_path)` (AC11 / D-NEW-1 — R2 finding); `append_evidence_trail` stays OUTSIDE the lock because it acquires its own sidecar lock and `file_lock` is NOT re-entrant. Thread-A's create + evidence-trail append and Thread-B's merge serialise via the `append_evidence_trail` self-lock + the new `_update_existing_page_body` unconditional lock (no caller-held wrapper — would self-deadlock). **`sweep_stale_pending(hours=168, *, action="mark_failed"|"delete", dry_run=False)` mutation tool** (`src/kb/review/refiner.py`) — counterpart to cycle-19 AC8b's read-only `list_stale_pending`. Matches rows by `attempt_id` equality, NEVER `page_id` (prevents concurrent-refine clobber). `mark_failed` default adds `status="failed"` + `error="abandoned-by-sweep"` + `sweep_id=uuid4().hex[:8]` + `sweep_at=<ISO>` while preserving `attempt_id` + `revision_notes`; `delete` writes a pre-mutation audit line to `wiki/log.md` via `append_wiki_log("sweep", ...)` and — per Step-11 Codex T4 fix — fails CLOSED with `StorageError(kind="sweep_audit_failure")` if the audit write raises `OSError` (no silent audit-free delete). `dry_run=True` returns candidates without mutation. Input validation via `ValidationError` (unknown action or `hours < 1`). Lock: single `file_lock(history_path)` span across load → mutate → save per cycle-19 AC9; compatible with refine_page's page-FIRST / history-SECOND order (sweep holds only the history lock — subset, no deadlock). **New MCP surfaces**: `kb_refine_sweep(hours, action, dry_run)` and `kb_refine_list_stale(hours)` in `mcp/quality.py`, listed in `mcp/app.py:26` `_TOOL_GROUPS` Quality tuple (total decorator count 26 → 28). MCP `kb_refine_list_stale` projects to `{attempt_id, page_id, timestamp, notes_length}` only — `revision_notes` NEVER crosses the MCP boundary (T5 mitigation + brainstorm Q8 resolution). **New CLI subcommands**: `kb refine-sweep --age-hours --action [--dry-run]` and `kb refine-list-stale --hours` — CLI returns the FULL helper dict (local-use exception per T5). **Windows tilde-path regression test** (closes cycle-19 T-13a placeholder): `tests/test_cycle20_windows_tilde_path.py` uses `ctypes.windll.kernel32.GetShortPathNameW` with a 260-char `create_unicode_buffer`, performs a `GetLongPathNameW` roundtrip sanity check (skip if the fixture is vacuous on 8.3-disabled filesystems), then asserts `_canonical_rel_path(long_form) == _canonical_rel_path(short_form)`. 55 new tests across 5 new test files (`test_cycle20_errors_taxonomy`, `test_cycle20_write_wiki_page_exclusive`, `test_cycle20_sweep_stale_pending`, `test_cycle20_list_stale_surfaces`, `test_cycle20_windows_tilde_path`). **Cycle-18 test update**: `test_jsonl_emitted_on_failure` now expects `IngestError` wrap with `__cause__` preserved (AC5/AC7 taxonomy behavior change). **Cycle-5 hardening test update**: `test_synthesis_prompt_uses_wikilink_citation_format` inspects both `query_wiki` and `_query_wiki_body` after the trampoline refactor. **Cycle-8 package-exports test**: `__all__` curated list extended with 6 new kb.errors names. Security: all 7 threats IMPLEMENTED after the Step-11 T3 audit-doc correction + T4 fail-closed fix; 0 PR-introduced CVEs (pip-audit diff vs cycle-20 baseline shows only the existing `diskcache CVE-2025-69872`, still no upstream patch — `Re-checked 2026-04-21`); 0 open Dependabot alerts. AC21 status: `diskcache==5.6.3` LATEST=5.6.3 confirmed via `pip index versions`; fix_versions empty; tracking re-check in next cycle's Step 2.

### Phase 4.5 — cycle 19 (2026-04-21)

23 AC / 6 src / 9 commits (incl. 1 R1-fix commit + 2 doc-update commits). Closes cycle-17 AC21 / cycle-18 deferral on **batch wikilink injection**: new `inject_wikilinks_batch(new_pages, *, pages=None) -> dict[str, list[str]]` in `kb.compile.linker` scans each existing wiki page AT MOST ONCE per chunk via a combined alternation regex; pre-lock peek is candidate-gathering only (cycle-19 AC1b) with under-lock re-derivation of the winning title from FRESH body content; `_run_ingest_body` switches from N per-title `inject_wikilinks` calls to one batch call (replaces the documented 500k-disk-reads hot path at 5k pages × 100 entities/concepts). ReDoS bound: `MAX_INJECT_TITLES_PER_BATCH = 200` chunking + per-title `MAX_INJECT_TITLE_LEN = 500` skip-with-warn (T2 null-byte titles also stripped at entry as defense-in-depth). Chunk-level try/except preserves per-failure granularity (AC6). Wiki/log.md gains a single `inject_wikilinks_batch` audit line per ingest via `append_wiki_log` (AC20 / T5 routes through `_escape_markdown_prefix`). **Manifest-key consistency**: `manifest_key_for = _canonical_rel_path` public alias in `kb.compile.compiler`; `compile_wiki` threads `manifest_key=rel_path` into `ingest_source(...)`; `ingest_source` accepts `manifest_key: str | None = None` keyword-only (AFTER `*` sentinel — R2 N1) with traversal-rejection validation at function entry (rejects `..`, leading `/`/`\`, `\x00`, len > 512); `manifest_ref = manifest_key or source_ref` is derived once and threaded into BOTH `_check_and_reserve_manifest` (Phase 1 reservation) AND the tail confirmation (Phase 2) per R2 M1. **Refine two-phase write**: `refine_page` now writes a `status="pending"` history row tagged with `attempt_id = uuid4().hex[:8]` BEFORE the page-body atomic-write, then flips that row to `applied` or `failed` (with `error` field on OSError) under the SAME `file_lock(history_path)` span (single-span hold-through per cycle-19 AC9). Lock order PRESERVED as `page_path FIRST, history_path SECOND` per cycle-1 H1 contract (AC10 WITHDRAW — module docstring documents the rationale). New `list_stale_pending(hours=24, *, history_path=None)` visibility helper for operators to detect rows that crashed between pending and flip. **MCP monkeypatch migration**: 13 callable monkeypatch sites across 7 test files migrated from `kb.mcp.core.<callable>` to the owner modules (`kb.ingest.pipeline.ingest_source`, `kb.query.engine.query_wiki/search_pages`, `kb.feedback.reliability.compute_trust_scores`); `kb.mcp.core` imports refactored to module-attribute style (`from kb.ingest import pipeline as ingest_pipeline`) with corresponding call-site updates. AC16 documents the snapshot-binding asymmetry for constants (PROJECT_ROOT/RAW_DIR/SOURCE_TYPE_DIRS still patched at `kb.mcp.core.X` directly). 7 vacuity tests pin AC15 owner-module-patch contract per migrated callable + AC16 behavioural snapshot test. **Cycle-15 reload state-leak fix**: `kb.capture._PROMPT_TEMPLATE` switched to lazy load via `_get_prompt_template()` cached helper — defeats the `importlib.reload(kb.config)` snapshot leak from `test_cycle15_cli_incremental.py` that broke any subsequent `kb.mcp.core` test import. **AC18** forward-looking lint: AST-based method-scope detection in `tests/test_cycle19_lint_redundant_patches.py` flags any test method that takes `tmp_kb_env` AND patches `HASH_MANIFEST` directly (cycle-18 D6 fixture already redirects). **AC14 DROP** with test-anchor retention (cycle-15 L2 rule): cycle-17 AC1 already shipped the prune-base consistency fix; cycle-19 retains `tests/test_cycle19_prune_base_consistency_anchor.py` to machine-enforce the shipped form. Tests: 47 new across 7 new test files (`test_cycle19_inject_wikilinks_batch`, `test_cycle19_manifest_key_consistency`, `test_cycle19_refiner_two_phase`, `test_cycle19_mcp_monkeypatch_migration`, `test_cycle19_lint_redundant_patches`, `test_cycle19_prune_base_consistency_anchor`, `test_cycle19_inject_batch_e2e`). Security: all 5 threats IMPLEMENTED (T1 ReDoS, T2 null-byte, T3 manifest_key injection, T4 refine liveness, T5 log injection); same-class peer scan clean; 0 PR-introduced CVEs (existing diskcache `CVE-2025-69872` deferred — no patched upstream). Plan-gate REJECT-WITH-AMENDMENTS resolved 5 amendments: AC12 dual-write, T2 null-byte sanitizer, AC17 DROP per cycle-17 L3 (re-grep showed zero current redundancy), T3 docstring, explicit revert-checks. R3 review triggers: 22 ACs (>15 + new security enforcement + new test surface) — mandatory.

### Phase 4.5 — cycle 18 (2026-04-21)

16 AC / 5 src / 6 commits. Closes five cycle-17 deferrals (AC15 e2e, AC19 observability, AC20 index-files helper, wiki_log rotate-in-lock Q11, linker scalar lock Q12, `tmp_kb_env` HASH_MANIFEST redirection). Adds **structured ingest audit log** at `<PROJECT_ROOT>/.data/ingest_log.jsonl`: one JSON row per emission at `start`/`duplicate_skip`/`success`/`failure` with 16-hex `request_id` correlation; `file_lock` + `open("a") + fsync` writer (NOT `atomic_text_write`); field allowlist enforced at writer boundary; `sanitize_text` redaction on `error_summary` (truncated 2KB); best-effort OSError swallow so telemetry failure never masks ingest outcome. `wiki/log.md` success messages gain `[req=<16-hex>]` prefix that correlates 1:1 with JSONL; duplicate-skip and failure paths remain JSONL-only per Q15. **Rotate-in-lock**: generic `rotate_if_oversized(path, max_bytes, archive_stem_prefix)` public helper extracts current `_rotate_log_if_oversized` logic; `append_wiki_log._write` moves the rotate call INSIDE `file_lock(log_path)` (closes Phase 4.5 HIGH R5 POSIX handle-holding-stale-file race / threat T2); JSONL rotation reuses the helper under its own lock. **Linker per-page lock**: `inject_wikilinks` wraps read-modify-write in `file_lock(page_path, timeout=0.25s)` with **pre-lock cheap read + under-lock re-read** (TOCTOU mitigation / threat T3); no-match / already-linked / self pages acquire ZERO locks (fast-path, threat T8); bounded timeout + skip-with-warning prevents 100s stalls on stuck locks. **Sanitize UNC**: new `sanitize_text(s: str) -> str` sibling to `sanitize_error_text` with shared `_ABS_PATH_PATTERNS`; regex extended to cover ordinary UNC `\\server\share\path` (threat T1). **`_write_index_files` helper** in `pipeline.py` consolidates `_update_sources_mapping` + `_update_index_batch` with sources-BEFORE-index ordering (behavioural change from previous index-then-sources) + INDEPENDENT per-call try/except; both helpers remain module attributes for legacy monkeypatch compat (threat T10). **`tmp_kb_env` HASH_MANIFEST**: fixture patches `kb.compile.compiler.HASH_MANIFEST` separately from the `kb.config` getattr loop; mirror-rebind covers in-process `kb.*` bindings (threat T5). Tests: 44 new across 6 files (`test_cycle18_conftest`, `test_cycle18_wiki_log`, `test_cycle18_sanitize`, `test_cycle18_linker_lock`, `test_cycle18_ingest_observability`, `test_workflow_e2e`). Security: all 10 threats IMPLEMENTED; same-class peer scan clean; 0 PR-introduced CVEs; existing diskcache `CVE-2025-69872` deferred (no patched upstream). Design-gate Q count 21 + R3 triggers (new FS write surface, vacuous-test risk, new security enforcement, ≥10 questions) → R3 review mandatory.

### Phase 4.5 — cycle 17 (2026-04-20)

16 AC / 11 src / 12 commits (incl. Step-11 T2 same-class-peer follow-up).
Closes three manifest RMW races (`compile_wiki` tail + exception path + `find_changed_sources`
save branch) via `file_lock(manifest_path)` symmetry. Adds shared
`_validate_run_id` helper (exact 8-hex via `re.fullmatch`) at
`src/kb/mcp/app.py`; wires `run_augment(resume=...)` through CLI
(`kb lint --resume`) and MCP (`kb_lint(resume=...)`) with `--augment`
dependency check. Switches `Manifest.resume` from glob-prefix to exact-match
direct path (eliminates the prefix-collision branch as structurally
unreachable). Adds `templates/capture_prompt.txt` (AC9) and restructures
`capture._write_item_files` to all-or-nothing two-pass with hidden-temp
`.{slug}.reserving` reservations + `os.replace` atomic promote +
rollback-all on mid-batch failure. MCP lazy imports narrowed (AC4): keeps
kb.query.engine/kb.ingest.pipeline/etc. at module level for legacy-test
monkeypatch compat; defers `kb.graph.export` from `mcp/health.py` +
`anthropic`/`frontmatter`/`kb.utils.llm.LLMError`/`kb.utils.pages.save_page_frontmatter`
inside tool bodies. AC8 documents `WikiPage`/`RawSource` as Phase-5
migration targets via module docstring + AST inventory test.
`tmp_kb_env` fixture clears `load_purpose` / `_load_template_cached` /
`_build_schema_cached` LRU caches on setup (AC16 / Q3). Adds 13 new
thin-coverage tests for 5 MCP tools (kb_stats, kb_graph_viz,
kb_verdict_trends, kb_detect_drift, kb_compile_scan). AC14 pins
`query_wiki(wiki_dir=tmp)` threads `purpose.md` into the synthesis prompt.
AC18 regression pin prevents a future `KB_PROJECT_ROOT` fallback in
`load_purpose`. Deferred to cycle 18: AC15 (e2e workflow test), AC19 / AC20
(ingest observability + IndexWriter helper), AC21 (linker batch). Security:
all in-scope threats IMPLEMENTED after T2 peer closure; 0 Dependabot
alerts; empty pip-audit diff; same-class peer scan (cycle-16 L1) closed
by the `find_changed_sources` save-branch lock.

### Phase 4.5 — Backlog-by-file cycle 16 (2026-04-20)

24 AC across 8 source files + 9 new test files + doc updates / 14 commits (1 Step-11 security-verify N1 fix + 1 R1 fix batch + 1 R2 fix batch + 1 R3 NIT batch). Tests: 2334 → 2464 collected (+130); full suite 2457 passed + 7 skipped (run-time count).

#### Added
- `src/kb/config.py` — new constants `QUERY_REPHRASING_MAX = 3`, `DUPLICATE_SLUG_DISTANCE_THRESHOLD = 3`, `CALLOUT_MARKERS = ("contradiction","gap","stale","key-insight")`.
- `src/kb/evolve/analyzer.py` — `suggest_enrichment_targets(wiki_dir, pages_dicts, *, status_priority=("seed","developing"))` ranks EXISTING pages by status (complementary to `suggest_new_pages`). Includes absent-status pages sorted LAST (Q4); drops mature/evergreen and invalid non-vocabulary values (T13).
- `src/kb/query/engine.py` — scan-tier `_suggest_rephrasings` helper + `_normalise_for_echo` filter. Surfaces up to 3 rephrasings on the low-coverage refusal path (cycle 14 AC5 branch) via new `result_dict["rephrasings"]` key.
- `src/kb/lint/checks.py` — `check_duplicate_slugs` (length-bucketed bounded-Levenshtein, 10K-page cap), `parse_inline_callouts` (Obsidian `[!marker]` regex with 1 MiB + 500-match caps), `check_inline_callouts` (cross-page 10K cap).
- `src/kb/mcp/core.py` — `kb_query(save_as=...)` keyword argument persists a synthesised answer to `wiki/synthesis/{slug}.md`. New `_validate_save_as_slug` helper (slugify + ASCII regex + Windows-reserved rejection) and `_save_synthesis` writer (hardcoded `type=synthesis`, `confidence=inferred`, `authored_by=llm` — T2).
- `src/kb/compile/publish.py` — two new builders: `build_per_page_siblings` emits `.txt` + `.json` siblings per kept page (deterministic `sort_keys=True` JSON) with unconditional stale-sibling cleanup (Q2/C3); `build_sitemap_xml` emits `sitemap.org/0.9` XML via `xml.etree.ElementTree` (T7 safe escaping, T8 relative POSIX `<loc>`).
- `src/kb/cli.py` — `kb publish --format` accepts two new values `siblings` and `sitemap`; `--format=all` now dispatches all five builders.
- `tests/test_cycle16_*.py` — 9 new test files covering config constants, enrichment targets, rephrasings, duplicate slugs, inline callouts, lint wiring, save_as, publish siblings/sitemap, CLI flags.

#### Changed
- `src/kb/query/engine.py` — low-coverage refusal branch now adds `rephrasings: list[str]` to result_dict (empty list when LLM unavailable or context empty).
- `src/kb/lint/runner.py` — `run_all_checks` adds `duplicate_slugs` + `inline_callouts` top-level keys; summary counters increment `warning` / `info` accordingly. `checks_run` count bumped 10 → 12.
- `src/kb/lint/runner.py` — `format_report` renders new `## Duplicate slugs` and `## Inline callouts` sections only when non-empty.
- `src/kb/mcp/core.py` — `kb_query` docstring notes the read→write shift when `save_as` is set (Q8 amendment).
- `src/kb/compile/publish.py` — module docstring documents the single-file-builder (`out_path`) vs multi-file-builder (`out_dir`) signature asymmetry (Q9; intentional — encodes output cardinality).
- `src/kb/evolve/analyzer.py` — `generate_evolution_report` threads `pages_dicts` into enrichment helper (no extra disk walk) and exposes `enrichment_targets` + `status_priority` keys.
- `tests/test_cycle14_coverage_gate.py::test_gate_triggers_refusal` — AC5 invariant narrowed from "call_llm never fires" to "orchestrate (synthesis) tier never fires"; cycle 16 adds a scan-tier rephrasings call on refusal which is additive.
- `tests/test_lint.py::test_run_all_checks` — `checks_run` length pinned to 12 after AC14 wiring.
- `BACKLOG.md` — deletes closed items (suggest_enrichment_targets cycle-16 target, low-coverage rephrasings, duplicate-slug lint, inline callout markers, kb_query save_as, compile/publish per-page siblings + sitemap).

#### Fixed
- `src/kb/compile/publish.py` (Step-11 N1 HIGH) — `_is_contained` switched from `str(target).startswith(str(base))` to `Path.is_relative_to`, closing a sibling-prefix-directory traversal hole (`pages_evil` would have string-prefix-matched `pages`). Regression test `test_rejects_sibling_prefix_directory` pins the contract.

#### Security
- Step-11 verify (Codex): 14/15 threats IMPLEMENTED cleanly; T9 PARTIAL resolved same-cycle with N1 fix. All 15 final status IMPLEMENTED.
- Class A Dependabot: 0 open alerts (fresh pre-push read).
- Class B pip-audit diff: empty (no PR-introduced CVEs). Pre-existing `diskcache==5.6.3` CVE-2025-69872 remains informational — no upstream fix_versions.
- Semantic shift disclosure (Q8): `kb_query(save_as=...)` is now a write path; docstring + non-goals doc flag the shift; hardcoded frontmatter (T2) + path validation (T1/T15) + slugify+ASCII whitelist (Q3/C4) guard the boundary.

### Phase 4.5 — Backlog-by-file cycle 15 (2026-04-20)

26 AC across 6 source files + 11 new test files + doc updates / 6 commits + 1 R1 PR-review fix commit. Tests: 2245 → 2334 (+89); full suite 2334 collected, 2327 passed + 7 skipped (run-time count).

#### Added
- `src/kb/config.py` — new config constants/helpers: `AUTHORED_BY_BOOST`, `SOURCE_VOLATILITY_TOPICS`, and `volatility_multiplier_for`.
- `src/kb/query/engine.py` — `_apply_authored_by_boost` query helper for mild `authored_by: human|hybrid` ranking lift.
- `src/kb/lint/checks.py` / `src/kb/lint/runner.py` — new lint checks `check_status_mature_stale` and `check_authored_by_drift`.
- `src/kb/compile/publish.py` — `_publish_skip_if_unchanged` helper for incremental publish short-circuiting.
- `tests/test_cycle15_*.py` — 7 new test files covering authored-by boost, volatility config, lint decay/status/authored wiring, publish atomic/incremental behavior, and query/publish integration.

#### Changed
- `src/kb/config.py` — `decay_days_for` gained `topics=None` keyword argument and composes hostname decay with topic volatility.
- `src/kb/query/engine.py` — `_flag_stale_results` composes source mtime and per-source decay gates; `_build_query_context` uses `tier1_budget_for("wiki_pages")`.
- `src/kb/lint/checks.py` — `check_staleness` uses per-source `decay_days_for` instead of flat staleness only.
- `src/kb/compile/publish.py` — `build_llms_txt`, `build_llms_full_txt`, and `build_graph_jsonld` migrated to `atomic_text_write` and accept `incremental: bool = False`.
- `src/kb/cli.py` — `kb publish` gains `--incremental/--no-incremental` flag.
- `BACKLOG.md` — deletes cycle-15-closed follow-ups and records cycle-16/deferred follow-ups for status-priority evolve routing, dropped `_post_ingest_quality` rationale, low-coverage rephrasings, cross-reference auto-linking, `kb_query save_as`, inline callouts, duplicate-slug lint, and compile-time auto-publish siblings/sitemap.

#### Fixed
- `tests/test_cycle11_stale_results.py` — dropped the `20260101` parametrized case because Python 3.11+ parses it as valid ISO.
- `tests/test_phase4_audit_query.py::test_tier1_budget_allows_multiple_small_summaries` — resized to the new summaries budget.
- `src/kb/compile/publish.py` (R1 MAJOR 1) — all three builders now partition pages ONCE before the incremental skip check instead of calling `_partition_pages` twice and discarding the first result. Prevents wasted work and removes the misleading "filter runs before skip" comment that did not match actual behaviour. Skip-case semantics unchanged (cycle-13 `sweep_orphan_tmp` + mtime-based gate preserve T10c in practice).
- `src/kb/query/engine.py` (R1 MAJOR 2) — added key-name clarification comment: AC2 spec cites `"summaries"` but the canonical `CONTEXT_TIER1_SPLIT` key is `"wiki_pages"`; future refactors that introduce a dedicated `"summaries"` bucket must re-audit this call.
- `src/kb/lint/checks.py` (R1 MINOR 1) — `_EVIDENCE_TRAIL_ANCHOR` now tolerates trailing horizontal whitespace on the header line.
- `tests/test_cycle15_query_tier1_wiring.py` (R1 MINOR 2) — dropped redundant `config.tier1_budget_for` spy; only the engine-module alias is observable.
- `tests/test_cycle15_publish_incremental.py` (R1 MINOR 3) — added comment documenting the 5-second mtime offset rationale.

#### Security
- Step-11 verify (Codex): all 10 threat-model items IMPLEMENTED. Class A Dependabot 0 open; Class B pip-audit diff empty; pre-existing `diskcache` CVE remains informational.
- Operator note (T10c): First post-upgrade `kb publish` run should use `--no-incremental` so any pre-cycle-14 outputs are regenerated under the current epistemic filter (threat T10c).

### Phase 4.5 — Backlog-by-file cycle 14 (2026-04-20)

21 AC across 9 source files + 1 new module / 8 implementation commits + planning artifacts + 1 security-verify PARTIAL fix. Tests: 2140 → 2235 (+95); full suite 2235 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs (Class A baseline 0 Dependabot alerts, Class B diff empty). Scope: Epistemic-Integrity 2.0 metadata vocabularies (belief_state, authored_by, status), query coverage-confidence refusal gate, per-platform source-decay + tier1-budget helpers, frontmatter-preserving save wrapper with augment write-back migration, Karpathy Tier-1 publish module (`kb publish` + /llms.txt + /llms-full.txt + /graph.jsonld), and status ranking boost.

#### Added
- `src/kb/compile/publish.py` — new module with `build_llms_txt`, `build_llms_full_txt`, `build_graph_jsonld` builders. Filter retracted/contradicted/speculative pages (threat T2). JSON-LD uses `json.dump` with a fully-constructed dict (T3); url is relative POSIX (T8). `LLMS_FULL_MAX_BYTES` = 5 MiB UTF-8 cap with page-level deterministic stop + oversized-first-page marker.
- `src/kb/cli.py` — `kb publish [--out-dir] [--format llms|llms-full|graph|all]` subcommand. Validates `--out-dir` via `is_relative_to(PROJECT_ROOT)` OR pre-existing directory; rejects UNC and `..` traversal (threat T1).
- `src/kb/utils/pages.py` — `save_page_frontmatter(path, post)` rigid wrapper (`sort_keys=False` + `atomic_text_write`) — single enforcement point for the cycle-7 R1 M3 key-order contract (threat T4).
- `src/kb/config.py` — `BELIEF_STATES`, `AUTHORED_BY_VALUES`, `PAGE_STATUSES` vocabularies (AC1); `QUERY_COVERAGE_CONFIDENCE_THRESHOLD = 0.45` (AC4); `CONTEXT_TIER1_SPLIT` + `tier1_budget_for` helper (AC7/AC8); `SOURCE_DECAY_DAYS` + `decay_days_for` helper with dot-boundary match (AC10/AC11 + threat T6); `STATUS_RANKING_BOOST = 0.05` (Q10).
- `src/kb/query/engine.py` — coverage-confidence refusal gate in `query_wiki` (AC5); `_apply_status_boost` helper applied after RRF fusion, gated by `validate_frontmatter` (AC23 + threat T9); `vector_search` stashes per-hit cosine on `search_telemetry["vector_scores_by_id"]` side-channel (additive — no signature break).
- `tests/test_cycle14_*.py` — 7 new test files (`config_constants`, `frontmatter_fields`, `save_frontmatter`, `augment_key_order`, `coverage_gate`, `status_boost`, `publish`) covering 95 new assertions.

#### Changed
- `src/kb/models/frontmatter.py` — `validate_frontmatter` rejects invalid `belief_state`, `authored_by`, `status` values; absent fields remain valid (AC2).
- `src/kb/lint/augment.py` — three augment write-back sites (`_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`) migrated to `save_page_frontmatter` (AC18 + threat T10). Comments updated; `sort_keys` literal no longer appears in the module.
- `src/kb/utils/pages.py` — `load_all_pages` returns additive `status` key from page metadata (empty string when absent); existing consumers ignore (AC23 support).
- `BACKLOG.md` — deletes the closed entries (belief_state, authored_by, status ranking-boost, coverage-confidence gate, /llms.txt + /llms-full.txt + /graph.jsonld, augment write-back cycle-14-target, per-subdir ingest rules — closed via pointer to existing `detect_source_type`). Adds 5 new entries for cycle-15+ follow-ups (tier1 split wiring, decay_days_for wiring, status evolve/lint sub-asks, LLM-suggested rephrasings, incremental publish, atomic publish writes).

#### Fixed
- None — cycle 14 is additive housekeeping per the cycle-13 plan.

#### Security
- Step-11 verify (Codex): all 10 threat-model items IMPLEMENTED after three follow-up fixes. T1 (traversal guard explicit `..` + `is_relative_to`), T2 (publish epistemic filter), T3 (JSON-LD no-f-string), T4 (save wrapper contract), T5 (advisory no-echo), T6 (decay dot-boundary match), T7 (dropped — existing code covers), T8 (relative POSIX url), T9 (status boost validated), T10 (augment migration complete). Class A Dependabot 0 open; Class B diff empty.

### Phase 4.5 — Backlog-by-file cycle 13 (2026-04-20)

8 AC across 5 source files / 7 implementation commits + planning artifacts. Tests: 2119 → 2131 (+12); full suite 2131 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs (Class A baseline 0 alerts, Class B diff empty).

#### Added
- `tests/test_cycle13_frontmatter_migration.py` — behavioural regressions for AC9-AC13 (read-only migration spies + mtime-invalidation pin + write-back negative-pin spy across all 3 augment write-back sites).
- `tests/test_cycle13_sweep_wiring.py` — AC14 sweep wiring + stale-`.tmp`-removed + dedup-pathological-alias coverage.
- `tests/test_cycle13_augment_raw_dir.py` — AC15 four-branch raw_dir derivation + integration sanity that `run_augment` routes through the new resolver.
- `src/kb/lint/augment.py` — `_resolve_raw_dir(wiki_dir, raw_dir)` helper extraction (AC8 testability) and `_record_verdict_gap_callout(stub_path, run_id, reason)` helper extraction (AC13 testability). Both pure refactors.

#### Changed
- `src/kb/lint/augment.py` — `_collect_eligible_stubs` migrated to `load_page_frontmatter` cached helper with widened except tuple (AC1). 3 write-back sites annotated as out-of-scope (AC6). `run_augment` derives `raw_dir = wiki_dir.parent / "raw"` when wiki_dir is overridden and raw_dir is omitted (AC8).
- `src/kb/lint/semantic.py` — `_group_by_shared_sources` page-paths branch migrated to `load_page_frontmatter` (AC3). Pre-loaded-bundle branch unchanged.
- `src/kb/graph/export.py` — `export_mermaid` title fallback migrated to `load_page_frontmatter`; `Path(path)` wrap is INSIDE the broad `try` so a non-path-like graph node attribute degrades to title fallback (AC4). Removes module-level `import frontmatter`.
- `src/kb/review/context.py` — `pair_page_with_sources` migrated to `load_page_frontmatter` with widened except tuple (AC5). Removes module-level `import frontmatter`.
- `src/kb/cli.py` — `cli` group callback now sweeps `{PROJECT_ROOT/.data, WIKI_DIR}` (resolved + deduped) on every CLI invocation via `sweep_orphan_tmp` (AC7). Runs after the AC30 `--version` short-circuit and Click's eager callbacks; helper swallows all errors at WARNING.
- `BACKLOG.md` — deletes the 3 cycle-13-target entries (frontmatter migration MED, sweep_orphan_tmp wiring LOW, run_augment raw_dir derivation LOW); adds a new LOW entry pinning the 3 augment write-back sites for cycle-14-target.

#### Fixed
- None — cycle 13 is additive housekeeping per the cycle-12 plan.

#### Security
- Step-11 verify (Codex): all 7 threat-model items IMPLEMENTED. T1 (sweep tmp race): mitigated by helper's 3600s threshold. T2 (raw_dir escape): lexical comparison mirrors cycle-7 effective_data_dir pattern. T3 (graph path type): `Path(path)` inside broad try. T4 (cached stale on FAT32/OneDrive): out-of-scope `_post_ingest_quality` stays uncached. T6 (WIKI_DIR third-party tmp): non-recursive glob. Class A Dependabot 0 open; Class B diff empty.

### Phase 4.5 — Backlog-by-file cycle 12 (2026-04-19)

17 AC across 13 files / 10 implementation commits + 1 security-verify PARTIAL fix. Tests: 2089 to 2118 (+29); full suite 2111 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs.

#### Added
- `tests/conftest.py` — `tmp_kb_env` fixture for isolated project roots in write-sensitive tests (AC1).
- `src/kb/utils/io.py` — `sweep_orphan_tmp` helper for non-recursive stale `.tmp` sibling cleanup (AC2).
- `src/kb/utils/pages.py` — LRU-cached `load_page_frontmatter` helper keyed by path and `mtime_ns` (AC8).
- `pyproject.toml` / `kb.mcp` — `kb-mcp` console script alongside the existing CLI entry point (AC7).
- Cycle-12 regression coverage — `test_cycle12_*.py` files including `sanitize_context` (AC14), plus augment regressions in `test_v5_lint_augment_cli.py` and `test_v5_lint_augment_orchestrator.py` (AC12, AC13).

#### Changed
- `src/kb/config.py` — `KB_PROJECT_ROOT` environment override plus bounded walk-up fallback from the current working directory (AC5, AC6).
- `src/kb/utils/io.py` — docstring caveats for `file_lock` PID behavior and atomic-write behavior on network mounts (AC3, AC4).
- `src/kb/utils/pages.py` — `load_all_pages` now uses `load_page_frontmatter` (AC9).
- `src/kb/lint/checks.py` — four `frontmatter.load` sites migrated to `load_page_frontmatter` (AC11).
- `src/kb/mcp_server.py` — back-compat shim for the package-level MCP entry point (AC7).
- `src/kb/graph/builder.py` — module docstring documents `page_id()` lowercasing and case-sensitive filesystem caveat (AC10).

#### Fixed
- None - cycle 12 is additive housekeeping.

#### Security
- `KB_PROJECT_ROOT` is OS-trusted; `Path.resolve()` plus `.is_dir()` gates invalid values, logs `WARNING`, and falls back safely. A hostile local environment can still redirect file I/O in the single-user CLI context, which is documented here for awareness. AC14 pins `conversation_context` sanitization across both `kb_query` branches.

### Phase 4.5 — Backlog-by-file cycle 11 (2026-04-19)

14 AC across 14 files / 13 implementation commits. Tests: 2041 → 2081 (+40); full suite 2081 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs.

#### Added
- `tests/test_cycle11_ingest_coerce.py` — regression coverage for `_coerce_str_field` scalar/list/dict/missing-field handling, comparison/synthesis rejection, and MCP no-file no-write behavior (AC1, AC2, AC3).
- `tests/test_cycle11_utils_pages.py` — direct canonical coverage for `page_id` / `scan_wiki_pages`, including lowercasing, subdir IDs, sentinel skip, deterministic order, and graph-builder re-export identity (AC6).
- `tests/test_cycle11_cli_imports.py` — CLI command smoke tests for function-local import paths plus subprocess `--version` / `-V` short-circuit checks that avoid importing `kb.config` (AC7, AC8).
- `tests/test_cycle11_stale_results.py` — `_flag_stale_results` edge-case coverage for missing/empty sources, non-ISO `updated`, non-string `updated`, and mtime-equals-page-date (AC9, AC10, AC11).
- `tests/test_cycle11_task6_mcp_ingest_type.py` — MCP same-class coverage that `kb_ingest`, `kb_ingest_content`, and `kb_save_source` steer comparison/synthesis callers to `kb_create_page` (AC2).

#### Changed
- `src/kb/utils/pages.py` — canonical home for `page_id(page_path, wiki_dir=None)` and `scan_wiki_pages(wiki_dir=None)`; `src/kb/graph/builder.py` now re-exports both for back-compat (AC4, AC5).
- `src/kb/compile/compiler.py`, `src/kb/compile/linker.py`, `src/kb/evolve/analyzer.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/lint/semantic.py` — internal callers now import page filesystem helpers from `kb.utils.pages` instead of `kb.graph.builder` (AC4, AC5).
- `tests/test_ingest.py` — `test_ingest_source` uses `tmp_project` plus explicit `wiki_dir=` / `raw_dir=` instead of manual wiki scaffolding and module-global patching (AC12).
- `tests/test_compile.py` — manifest double-write regression now includes a behavioral manifest-content assertion in addition to the existing save-count pin (AC13).

#### Fixed
- `src/kb/ingest/pipeline.py` — remaining scalar extraction read sites use `_coerce_str_field`; `source_type="comparison"` / `"synthesis"` now rejects early with a `kb_create_page` hint instead of falling into the broken ingest-render path (AC1, AC2, AC3).
- `src/kb/mcp/core.py` — `kb_ingest`, `kb_ingest_content`, and `kb_save_source` return explicit comparison/synthesis guidance naming `kb_create_page` before generic unknown-source-type handling (AC2).

#### Security
- Cycle-11 security verify recorded no dependency diff in `requirements.txt` / `pyproject.toml`; no Class-B PR-introduced CVEs. Same-class comparison/synthesis MCP handling was completed in follow-up (AC2).

### Backlog-by-file cycle 10 (2026-04-18)

- `src/kb/mcp/app.py` — AC0: `_validate_wiki_dir` now enforces `PROJECT_ROOT` containment; error strings standardised (commit `ee1279f`).
- `src/kb/mcp/quality.py` — AC1+AC1b: `kb_affected_pages` surfaces `backlinks` / `shared_sources` warnings (commit `4f045a4`).
- `src/kb/mcp/browse.py` — AC3: `kb_stats` migrated to `_validate_wiki_dir`. AC2 regression-pinned (commit `a1c1f79`).
- `src/kb/mcp/health.py` — AC4+AC5+AC6: `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` migrated to `_validate_wiki_dir` (commit `82b582a`). Plus security follow-up `1c3832e` removing `Path.resolve()` bypass.
- `src/kb/query/engine.py` + `src/kb/config.py` — AC7+AC8: `VECTOR_MIN_SIMILARITY` cosine floor in `search_pages` (commit `6159d85`).
  - **Note — RRF ranking interaction with `VECTOR_MIN_SIMILARITY`.** When a page is returned by BM25 but the vector backend returns the same page with cosine score below `VECTOR_MIN_SIMILARITY` (0.3), the vector contribution to RRF fusion is intentionally dropped. This tightens ranking so marginal-vector-similarity pages no longer receive a dual-backend boost; pages with strong BM25 match retain their BM25 rank. If observed regressions in recall suggest the threshold is too strict, tune via the `VECTOR_MIN_SIMILARITY` constant in `src/kb/config.py`.
- `src/kb/compile/compiler.py` — AC9: `find_changed_sources` docstring documents deletion-pruning persistence (commit `70b5e49`).
- `src/kb/utils/text.py` — AC28.5: `wikilink_display_escape` now backslash-escapes `|` instead of silently substituting an em dash (commit `70b5e49`).
- `src/kb/capture.py` — AC10+AC11: UUID prompt boundary + submission-time `captured_at` (commit `46f0e34`).
- `src/kb/ingest/pipeline.py` — AC12+AC13a+AC13b: `_coerce_str_field` helper + `extraction_json` pass before manifest reservation + defensive checks in `_build_summary_content` (commit `01bb1bb`).
- `src/kb/lint/_safe_call.py` — AC1s: sanitises embedded exception text via `_sanitize_error_str` (commit `9d4b447`).
- `src/kb/capture.py` — AC14: `CaptureError` exception + `raw/captures` side-effect note (commit `46f0e34`).
- Tests: 2004 → 2041 (+37 new tests); all passing, 7 Windows-skips (case-insensitive FS + symlinks); 0 new Dependabot alerts.
- STALE at cycle 10 review (already fixed, removed from BACKLOG): `utils/wiki_log.py` torn-last-line (MEDIUM); `mcp/browse.py` query-length-cap + stale-flag (HIGH-Additional).

### Phase 4.5 — Backlog-by-file cycle 9 (2026-04-18)

30 AC across 14 files plus 2 security-review fixes. Tests: 1949 → 2003 (+54, across 150 test files). Full feature-dev pipeline (requirements → threat model + design gate → implementation + security verify → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/ingest/__init__.py` — lazy `__getattr__` re-export for `ingest_source`, preserving the package public API without loading the ingest pipeline on package import (AC29).
- `src/kb/mcp/app.py` — `_validate_wiki_dir(wiki_dir)` boundary helper for MCP wiki override paths (security review).
- `src/kb/evolve/analyzer.py` — `_orphan_via_graph_resolver` helper so orphan-concept detection uses `build_graph`'s bare-slug resolver (AC13).
- `src/kb/utils/llm.py` — `_redact_secrets` helper for LLM error text before truncation (AC27).
- Cycle-9 regression coverage across compiler, evolve, lint augment/checks, LLM redaction, MCP app/core/health/path validation, package exports, query engine, and env example tests.

#### Changed
- `src/kb/query/engine.py` — vector-index lookup, stale-flag project root, `search_mode`, and raw fallback now derive paths from the active `wiki_dir` override instead of repo defaults (AC1, AC2, AC3, AC4).
- `src/kb/mcp/core.py` — `kb_compile_scan(wiki_dir=None)` threads custom wiki directories into changed-source scanning; `kb_ingest` rejects over-cap source files instead of silently truncating; `kb_ingest_content` validates boundary content size consistently (AC7, AC8, AC9).
- `src/kb/mcp/health.py` — `kb_lint` and `kb_evolve` scope feedback-derived sections to the provided wiki project's `.data/feedback.json` (AC5, AC6).
- `src/kb/mcp/app.py` — MCP instructions render from alphabetized `_TOOL_GROUPS` instead of a monolithic FastMCP instructions string (AC28).
- `src/kb/lint/augment.py` — `run_augment` summary counts final per-stub outcomes, so fallback URL success no longer reports a failed stub (AC11).
- `src/kb/lint/checks.py` — `check_source_coverage` parses frontmatter once and extracts body refs from parsed content (AC12).
- `tests/conftest.py` — `RAW_SUBDIRS` derives from `SOURCE_TYPE_DIRS`; `tmp_captures_dir` asserts containment under `PROJECT_ROOT` (AC25, AC26).
- `.env.example` — `ANTHROPIC_API_KEY` documented as optional for Claude Code/MCP mode and required only for direct API-backed flows (AC30).

#### Fixed
- `src/kb/compile/compiler.py` — `load_manifest` now catches transient `OSError` alongside JSON/Unicode read failures (AC10).
- `src/kb/capture.py` — capture scanner and writer hardening: best-effort decode logging, bounded slug collision attempts, `_is_path_within_captures` rename, encoded-secret labels, `NamedTuple` secret patterns, stripped accepted bodies, prompt-size guard, and per-process rate-limit documentation (AC14, AC15, AC16, AC17, AC18, AC19, AC20, AC21).
- `tests/test_capture.py` — capture tests import `CAPTURE_KINDS` from config, add YAML title round-trip regressions, correct the CRLF-size comment, and remove duplicate `re` import (AC22, AC23, AC24).

#### Security
- `src/kb/utils/llm.py` — four LLM error sites redact API keys/tokens/secrets before truncation and surfacing errors (AC27).
- `src/kb/mcp/app.py`, `src/kb/mcp/core.py`, `src/kb/mcp/health.py` — `wiki_dir` overrides are validated at the MCP boundary before use (security review).
- Test secret literals were split so redaction fixtures do not carry scanner-triggering full secret strings (security review).

---

### Phase 4.5 — Backlog-by-file cycle 8 (2026-04-18)

30 AC across 19 files. Tests: 1919 → 1949 (+30, across 138 test files). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan + plan-gate → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/config.py` — new config constants: `MAX_CONSISTENCY_GROUPS`, `MAX_CONSISTENCY_PAGE_CONTENT_CHARS`.
- `src/kb/models/page.py` — `WikiPage` and `RawSource` model validators, `WikiPage.to_dict()`, and `WikiPage.from_post()` class methods.
- `src/kb/__init__.py`, `src/kb/utils/__init__.py`, `src/kb/models/__init__.py` — curated `__all__` for top-level `kb` package, `kb.utils`, and `kb.models`.
- `src/kb/mcp/app.py` — `_validate_notes(notes, field_name)` helper.
- `src/kb/mcp/browse.py::kb_stats` and `src/kb/mcp/health.py::kb_verdict_trends` MCP tools gain `wiki_dir` override with path-traversal rejection.
- `src/kb/utils/llm.py` — LLM success INFO telemetry: logs model/attempt/tokens_in/tokens_out/latency_ms on each successful call.
- 30 new tests across 7 test files (`tests/test_cycle8_*.py`).

#### Changed
- `src/kb/query/engine.py` — PageRank no longer applied as a post-fusion score multiplier; it now enters `rrf_fusion` as a separate ranked list (union of BM25 + vector candidates), giving it equal standing in Reciprocal Rank Fusion.
- `src/kb/ingest/pipeline.py::_persist_contradictions` is now idempotent: a re-ingest with the same source, same date, and same claims produces no duplicate block (exact block match inside `wiki/contradictions.md`).
- `src/kb/lint/semantic.py::build_consistency_context` auto mode now caps at `MAX_CONSISTENCY_GROUPS` (20) total groups and truncates per-page body at `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` (4096 chars) after frontmatter strip.

#### Fixed
- Eager `kb.__init__` imports at package import time caused a circular import on the `kb --version` short-circuit path (regression from cycle-8 TASK 3); fixed via PEP 562 lazy `__getattr__` in `src/kb/__init__.py`.
- `src/kb/query/engine.py` — PageRank tie-order non-determinism when multiple pages share the same score.

#### Security
- (Class A) `pip` upgraded 24.3.1 → 26.0.1 in venv; patches CVE-2025-8869 and CVE-2026-1703 plus 2 ECHO advisories.
- `diskcache==5.6.3` (CVE-2025-69872, GHSA-w8v5-vhqr-4h9v) has no upstream patch as of 2026-04-18; recorded in BACKLOG. No Class B (PR-introduced) CVEs.

---

### Phase 4.5 — Backlog-by-file cycle 7 (2026-04-18)

30 items across 22 source files. Tests: 1868 → 1919 (+51, including 48 new behavioural tests in `test_backlog_by_file_cycle7.py` + 3 inline template-sentinel + updated cycle-5 wrap_purpose pin). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan + plan-gate → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/lint/_safe_call.py` — new module hosting `_safe_call(fn, *, fallback, label)` helper so lint/runner and mcp/health silent-degradation sites surface `<label>_error: …` instead of silent `None` (AC27).
- `src/kb/mcp/app.py::_sanitize_error_str(exc, *paths)` — helper that strips Windows absolute/UNC paths, POSIX absolute paths, and `OSError.filename`/`filename2` attributes from exception strings before MCP tools return them to the client (AC12/AC13 shared helper).
- `src/kb/config.py::get_model_tier(tier)` — lazy env-aware alternative to the import-time `MODEL_TIERS` dict so tests and long-lived processes observe `CLAUDE_*_MODEL` env mutations mid-run (AC24).
- `tests/test_backlog_by_file_cycle7.py` — 48 behavioural regression tests covering every cycle-7 AC. Red-flag self-checks: no `re.findall` source-scans, no `inspect.getsource` grep, no negative-assert patterns.
- `CLAUDE.md` — new `### Evidence Trail Convention` subsection documenting the reverse-chronological insert-after-sentinel behaviour (AC25).

#### Changed
- `src/kb/graph/builder.py` `build_graph(wiki_dir, *, pages=None)` — `pages` is now keyword-only; callers supplying preloaded page dicts skip the internal `scan_wiki_pages` walk (AC11).
- `src/kb/compile/linker.py` `build_backlinks(wiki_dir, *, pages=None)` — same pattern (AC10).
- `src/kb/lint/semantic.py` — `build_consistency_context` + `_group_by_shared_sources` / `_group_by_wikilinks` / `_group_by_term_overlap` accept optional `pages=` bundle (AC19).
- `src/kb/evolve/analyzer.py::generate_evolution_report` — loads `pages_dicts` once via `load_all_pages` and threads into `build_graph(pages=…)` + `analyze_coverage(pages_dicts=…)` (AC9).
- `src/kb/ingest/pipeline.py::_find_affected_pages` — passes preloaded pages into `build_backlinks` so the cascade path no longer does a second disk walk (AC8).
- `src/kb/ingest/pipeline.py::_update_existing_page` — References regex masks fenced code blocks before substitution + normalises trailing newline (AC5); re-ingest context enrichment now appends `### From {source_ref}` subsection under existing `## Context` header instead of silently dropping the new context (AC7); `ctx=` kwarg added for direct callers; bare contradiction `except` narrowed to `(KeyError, TypeError, re.error)` so bug-indicating `ValueError` / `AttributeError` propagate (AC6).
- `src/kb/ingest/pipeline.py::_write_wiki_page` — hand-rolled f-string YAML frontmatter replaced with `frontmatter.Post` + `frontmatter.dumps()` so YAML-escaping becomes the library's responsibility; back-compat shim accepts `page_path=` or legacy `path=` (AC29).
- `src/kb/ingest/extractors.py::clear_template_cache` — serialized via module-level `_template_cache_lock` so concurrent clears vs readers cannot observe mid-clear state (AC28).
- `src/kb/query/embeddings.py::rebuild_vector_index` — batch path bypasses `embed_texts`, calls `model.encode(texts)` directly and passes each numpy row via buffer protocol to `sqlite_vec.serialize_float32` (AC2). `_index_cache` now bounded at `MAX_INDEX_CACHE_SIZE=8` with FIFO eviction under `_index_cache_lock` (AC3).
- `src/kb/query/engine.py::query_wiki` — docstring documents the `stale` flag on each citation entry + the `stale_citations` return field (AC4).
- `src/kb/lint/checks.py::check_dead_links` — skips targets matching root-level `_INDEX_FILES` (`index.md`/`_sources.md`/`log.md`) when the file exists (AC18).
- `src/kb/lint/verdicts.py::load_verdicts` — adds single 50 ms retry on transient `OSError` / `JSONDecodeError` / `UnicodeDecodeError` for Windows atomic-rename window (AC20).
- `src/kb/lint/runner.py::run_all_checks` — verdict-summary load routed through `_safe_call(label="verdict_history")`; report dict gains `verdict_history_error` field on failure (AC27).
- `src/kb/mcp/core.py` — ingest/read/scan/compile/search/capture error-string sites route `{e}` through `_sanitize_error_str(e, <path>)`; R1 security verify caught 4 residual sites (API-mode ingest, `read_text`, `kb_compile_scan`, `kb_compile`) patched in follow-up commit (AC12).
- `src/kb/mcp/health.py` — 5 error-string sites (`kb_lint`, `kb_evolve`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`) piped through `_sanitize_error_str`; feedback-flagged-pages block in `kb_lint` routed through `_safe_call` (AC13 + AC27 wiring).
- `src/kb/mcp/app.py::_rel()` — defensive guard for `None` / non-`Path` inputs so `_sanitize_error_str` can safely scan `exc.filename` without `AttributeError` (AC12 follow-up).
- `src/kb/review/context.py::pair_page_with_sources` — accepts explicit keyword-only `project_root=` ceiling; falls back to `raw_dir.parent` for back-compat (AC21).
- `src/kb/review/refiner.py::refine_page` — parses frontmatter block with `yaml.safe_load` before rewriting; malformed YAML pages return `Error` instead of being laundered through a successful write (AC22).
- `src/kb/utils/text.py::wrap_purpose` — now escapes attacker-planted `</kb_purpose>` closers to the inert `</kb-purpose>` hyphen variant, mirroring `_escape_source_document_fences` (AC23).
- `src/kb/utils/io.py` module docstring — documents lock-ordering convention `VERDICTS → FEEDBACK → REVIEW_HISTORY` (AC17).
- `src/kb/cli.py` — `--version` short-circuits BEFORE any `kb.config` import so operators with broken configs can still query the installed version; module docstring documents exit-code contract (AC16 + AC30).
- `src/kb/graph/export.py` — Mermaid title-fallback uses the unmodified filename stem when `_sanitize_label` strips the title to empty, preserving `-` in the rendered label (AC26).
- `tests/conftest.py` — autouse fixture `_reset_embeddings_state` clears `kb.query.embeddings._model` and `_index_cache` between every test (AC1).
- `tests/test_phase4_audit_compile.py::test_manifest_pruning_keeps_unchanged_source` — asserts `_template/article` sentinel key AND hash value preserved across unrelated-source mutation (AC15).
- `tests/test_cycle5_hardening.py::test_wrap_purpose_escapes_sentinel_closer` — flipped from pinning non-escape (cycle 5 decision) to asserting the escape fires (cycle 7 AC23 supersedes).

#### Fixed
- `src/kb/mcp/core.py` — 4 residual raw `{e}` error-string sites flagged by R1 Codex security verify (AC12 follow-up, commit `32b9387`).

---

### Phase 4.5 — Backlog-by-file cycle 6 (2026-04-18)

15 items across 14 source files. Tests: 1836 → 1868 (+32). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Process artifacts (new)

- `docs/superpowers/decisions/2026-04-18-cycle6-requirements.md` — Step 1 AC1-AC16 (15 backlog items + tests).
- `docs/superpowers/decisions/2026-04-18-cycle6-threat-model.md` — Step 2 threat table + Step 11 checklist.
- `docs/superpowers/decisions/2026-04-18-cycle6-design.md` — Step 5 Opus decision gate verdict: APPROVE with 6 conditions.

#### Added

- `src/kb/query/engine.py` — `_PAGERANK_CACHE` process-level cache + `_PAGERANK_CACHE_LOCK` (AC4). Keyed on `(str(wiki_dir.resolve()), max_mtime_ns, page_count)` matching `_WIKI_BM25_CACHE_LOCK` precedent; unbounded per single-user local stance; thread-safe under FastMCP pool via check-under-lock + double-check-store pattern.
- `src/kb/query/embeddings.py` — `VectorIndex._ensure_conn()` + `self._disabled` + `self._ext_warned` attrs (AC5). sqlite3 connection opened ONCE per VectorIndex instance; on `sqlite_vec.load` failure the instance is marked disabled, a single WARNING is logged, and every subsequent `query()` call returns `[]` without retrying extension load. Connection left open for instance lifetime (process exit closes fd).
- `src/kb/cli.py` — `_is_debug_mode()` + `_error_exit()` + `_setup_logging()` helpers plus top-level `--verbose` / `-v` flag (AC9). `KB_DEBUG=1` env var OR `--verbose` prints full `traceback.format_exc()` to stderr BEFORE the truncated `Error:` line. Default behavior unchanged.
- `src/kb/evolve/analyzer.py` — `_iter_connection_pairs` generator helper (AC12). Replaces the three-level `break` + `_pairs_truncated` flag with a single-source-of-truth cap gate that emits one WARNING on truncation.
- `tests/test_backlog_by_file_cycle6.py` — 31 behavioral regression tests for AC1-AC15 + Step-11 condition (`sqlite3.connect(` count == 3 in embeddings.py). Every test exercises production code paths, not `inspect.getsource` greps (per `feedback_inspect_source_tests` memory).

#### Changed

- `src/kb/mcp/core.py` — `kb_ingest_content` accepts `use_api: bool = False` kwarg (AC1). When `True`, skips the `extraction_json` requirement and falls through to `ingest_source`'s LLM extraction path — mirroring `kb_query` / `kb_ingest`'s existing contract.
- `src/kb/mcp/health.py` — `kb_detect_drift`, `kb_evolve`, `kb_graph_viz` each accept `wiki_dir: str | None = None` (AC2) and thread it to `detect_source_drift`, `generate_evolution_report`, `export_mermaid` respectively. Matches the Phase 5.0 `kb_lint(wiki_dir=...)` pattern.
- `src/kb/query/rewriter.py` — `rewrite_query` rejects LLM preamble leaks by reusing `_LEAK_KEYWORD_RE` from `engine.py` (AC3). Patterns include "Sure! Here's…", "The standalone question is:", "Rewritten query:", etc. Previously leaked preambles flowed into BM25 tokenize + vector embed + synthesis prompt, silently degrading retrieval quality.
- `src/kb/query/engine.py` — `_compute_pagerank_scores(wiki_dir, *, preloaded_pages=None)` now accepts pre-loaded pages and threads them into `build_graph(pages=...)` (AC6). `search_pages` passes its already-loaded `pages` list, eliminating a second disk walk per query.
- `src/kb/query/hybrid.py` — `rrf_fusion` stores `(accumulated_score, merged_metadata)` tuples in the intermediate dict instead of shallow-copy result dicts (AC10). Defers dict materialization to sort time; preserves late-list-wins metadata merge (Phase 4.5 HIGH Q2).
- `src/kb/query/dedup.py` — `_dedup_by_text_similarity` skips the Jaccard threshold when comparing results of different `type` (AC11). Summaries quoting an entity's text no longer collapse the entity row under layer-2 similarity pruning.
- `src/kb/ingest/pipeline.py` — `_update_existing_page` normalizes `content.replace("\r\n", "\n")` after read (AC7) so CRLF-encoded frontmatter matches `_SOURCE_BLOCK_RE` (LF-only). Previously CRLF files fell through to a weak fallback, producing double `source:` keys that crashed the next frontmatter parse.
- `src/kb/ingest/pipeline.py` — `_process_item_batch` accepts `shared_seen: dict[str, str] | None = None` keyword-only (AC8). When provided, slug collisions are detected across entity+concept batches. Entity batch runs first → concept batch colliding on same slug is skipped with `pages_skipped` entry + WARNING per OQ5 entity-precedence.
- `src/kb/graph/builder.py` — `graph_stats(graph, *, include_centrality: bool = False)` (AC13). Default `False` skips `nx.betweenness_centrality` (O(V*E) at 5k-node scale dominated every `kb_stats` / `kb_lint` call). `bridge_nodes` returns `[]`, `bridge_nodes_status` returns `"skipped"`. NOT exposed via MCP per OQ11.
- `src/kb/utils/pages.py` — `load_purpose` decorated with `@functools.lru_cache(maxsize=4)` (AC14). Docstring documents the `load_purpose.cache_clear()` invalidation contract for tests that mutate `purpose.md` mid-run.
- `src/kb/utils/pages.py` — `load_all_pages` accepts keyword-only `return_errors: bool = False` (AC15). Default returns `list[dict]` (backward-compatible); `True` returns `{"pages": list[dict], "load_errors": int}` so callers can distinguish "fresh install" from "100 permission errors."

#### Docs

- `CHANGELOG.md` — this cycle-6 entry. Test count 1836 → 1868 (+32).
- `CLAUDE.md` — test count, file count, cycle-6 reference.
- `BACKLOG.md` — 15 resolved items deleted per BACKLOG lifecycle rule.

#### Security posture (cycle 6)

- **PR-introduced CVE diff:** 0 entries vs Step-2 baseline (`pip-audit` + Dependabot clean).
- **Class-A existing CVEs (unchanged from cycle 5):** `diskcache==5.6.3` CVE-2025-69872 — no upstream patch; accepted risk. `pip==24.3.1` toolchain CVEs — not runtime.
- **Threat-model mitigations:** all 15 AC rows grep-verified at Step 11. New trust boundary (process-level PageRank cache, `load_purpose` lru_cache) keyed on `wiki_dir.resolve()` path so multiple tmp wikis in one process do not collide.

#### Legacy test adaptations

- `tests/test_phase45_high_cycle2.py::TestQ4CentralityStatusMetadata::test_bridge_nodes_has_status` — updated to pass `include_centrality=True` (AC13 made it opt-in).
- `tests/test_v0913_phase394.py::TestKbGraphVizMaxNodes::test_max_nodes_clamped` — mock signature accepts new `wiki_dir` kwarg.
- `tests/test_v09_cycle5_fixes.py::test_cli_configures_logging_when_root_has_no_handlers` — calls `cli._setup_logging()` directly (Click group callback now requires context).

#### Stats

1868 tests across 130 test files; +32 tests vs cycle 5 redo baseline; 15 items across 14 source files on `feat/backlog-by-file-cycle6`.

---

### Phase 4.5 — Cycle 5 redo (hardening, 2026-04-18)

6 items across 6 files. Tests: 1821 → 1836 (+15). Cycle 5 shipped 14 items but shortcut the feature-dev pipeline (no Step 2 threat model artifact, no Step 5 decision gate doc, only 1 PR review round). This redo ran the full pipeline retroactively and surfaced concrete gaps the missing process would have caught.

#### Process artifacts (new)

- `docs/superpowers/decisions/2026-04-18-cycle5-redo-requirements.md` — Step 1 AC1-AC8.
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-threat-model.md` — Step 2 threat table + Step 11 verification checklist.
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-design.md` — Step 5 Opus decision gate verdict: CONDITIONAL-APPROVE with 6 conditions.

#### Fixed

- `query/engine.py` + `query/citations.py` — **T1 citation-format symmetry.** API-mode synthesis prompt at line 733 said `[source: page_id]` while MCP-mode instructions at `mcp/core.py:208` said `[[page_id]]`. Asymmetric → API-mode answers produced zero extractable citations because `extract_citations`' regex only matched the legacy form. Fixed by coordinating both: prompt now instructs `[[page_id]]`; `_CITATION_PATTERN` widened with alternation to accept both legacy and canonical forms (backward compat preserved).
- `mcp/app.py` — **T3 page-id length single source of truth.** Local `_MAX_PAGE_ID_LEN=255` diverged from `config.MAX_PAGE_ID_LEN=200`. Removed the local constant; `_validate_page_id` now imports from config. Pre-change grep confirmed no existing page IDs exceed 200 chars.
- `lint/augment.py` — **Step 11 verify finding.** Third purpose callsite (`_build_proposer_prompt`) bypassed `wrap_purpose`, breaking the "every purpose interpolation goes through the sentinel" invariant. Now wraps via `wrap_purpose(purpose_text, max_chars=1000)`.
- `tests/test_v0913_phase394.py` — updated legacy negative-assert for T1b regex widening (nested `[source: [[X]]]` now extracts the inner wikilink correctly).

#### Added (tests)

- `tests/test_cycle5_hardening.py` — 15 tests covering: T1 prompt + regex coordination, T1 backward compat, T2 CJK entity boundary (pins Python `re` Unicode-aware `\b` behavior), T3 page-id length at boundary (200 accept, 201 reject), T4 wrap_purpose sentinel-forgery pinning (textual-only defense documented), T4 byte-exact newline preservation, T5 verdict + feedback `logger.warning` on corrupted UTF-8 via `caplog`, augment proposer sentinel wrapping, pytest integration marker smoke test.

#### Changed

- `utils/text.py` — one-line trust-model comment on `wrap_purpose`: *"Defense is textual-only: wiki/purpose.md is human-curated (trusted). The helper strips non-whitespace C0 controls and caps length, but does NOT escape an attacker-supplied `</kb_purpose>` closer inside the input — sentinel semantics are an LLM-trust boundary, not a hard parse."*

---

### Phase 4.5 — Backlog-by-file cycle 5 (2026-04-18)

14 items across 13 files. Tests: 1811 → 1820 (+9). 1-round PR review.

#### Added

- `utils/text.py` — `wrap_purpose(text, max_chars=4096)` helper: strips control characters, caps at 4096 chars, wraps in `<kb_purpose>` sentinel tags for safe injection in LLM prompts.
- `pyproject.toml` — registered `slow`, `network`, `integration`, `llm` pytest markers to eliminate `PytestUnknownMarkWarning`.

#### Changed

- `config.py` — added `VALID_SEVERITIES = ("error", "warning", "info")` and `VALID_VERDICT_TYPES` tuple; deleted orphaned `WIKI_CATEGORIES` constant (zero importers confirmed).
- `lint/verdicts.py` — migrated `VALID_SEVERITIES`, `VALID_VERDICT_TYPES`, `MAX_NOTES_LEN` to `kb.config`; re-exported for backward compat; widened `load_verdicts` except to `(json.JSONDecodeError, OSError, UnicodeDecodeError)`.
- `query/engine.py` — replaced raw purpose f-string injection with `wrap_purpose()` sentinel call.
- `ingest/extractors.py` — replaced raw purpose f-string injection with `wrap_purpose()` sentinel call.
- `mcp/core.py` — updated citation format in Claude Code mode instructions from `[source: page_id]` to `[[page_id]]` wikilink syntax; applied `yaml_escape(source_type)` in hint string.
- `utils/llm.py` — added `default_headers={"User-Agent": "llm-wiki-flywheel/<version>"}` to Anthropic client constructor.
- `cli.py` and `mcp_server.py` — added `logging.basicConfig` with handler guard to prevent duplicate log lines.

#### Fixed

- `ingest/pipeline.py` — `_extract_entity_context()` now uses `\b{name}\b` word-boundary regex instead of `name in string` substring match, preventing false matches (e.g., "Ray" matching "stray").
- `mcp/app.py` — `_validate_page_id()` now rejects page IDs containing any control character (`\x00`–`\x1f`, `\x7f`) with a clear error; fail-closed posture consistent with existing path-traversal guard.
- `tests/` — fixed midnight boundary flake in `test_basic_entry` (explicit `entry_date`); replaced false-positive-prone contradiction test vocabulary; corrected `content_lower` mock values to exclude frontmatter.

---

### Concurrency fix + docs tidy (PR #17, 2026-04-18)

3 source-file changes. Tests: 1810 → 1811 (+1). 2-round parallel Codex PR review (R1: 1 MAJOR-non-regression, 2 MINORs fixed; R2: pass).

#### Fixed

- `lint/verdicts.py` — `add_verdict` pre-existing concurrency flake (`test_concurrent_add_verdict_no_lost_writes`): added `_VERDICTS_WRITE_LOCK` (threading.Lock) as in-process write serializer. Root cause: Windows PID-liveness heuristic in `file_lock` could steal the lock from a live same-PID thread under heavy suite load, putting two threads in the critical section simultaneously → lost entries. Threads now queue via `_VERDICTS_WRITE_LOCK` before acquiring `file_lock`; lock order documented (`_VERDICTS_WRITE_LOCK → file_lock → _VERDICTS_CACHE_LOCK`); `save_verdicts` scope boundary documented.
- `capture.py` — `_normalize_for_scan` docstring: cost note now separately documents base64 scan bound `O(n/17)` (16-char minimum) and URL-decode scan bound `O(n/10)` (9-char minimum), both load-bearing on `CAPTURE_MAX_BYTES`. `_check_rate_limit` docstring: per-process scope and cross-process persistence path documented.

#### Added

- `tests/test_v0915_task06.py` — `test_concurrent_writes_trim_at_max_verdicts`: pre-fills store to `MAX_VERDICTS-3`, runs 5 concurrent `add_verdict` threads, asserts final count `≤ MAX_VERDICTS`. Previously the trim branch (`verdicts[-MAX_VERDICTS:]`) was never reached by the concurrency test (10 entries vs 10,000 cap).

#### Docs

- `BACKLOG.md` — cross-reference table added (was HTML comment); 20+ verified-shipped items deleted across Phase 4.5 HIGH and Phase 5 kb-capture sections; `load_verdicts` readers-without-lock item updated to note write-write race is now fixed (remaining: reader PermissionError on Windows mid-rename).
- `CHANGELOG.md` — split into active (2026-04-16+) and `CHANGELOG-history.md` archive (Phase 4.5 CRITICAL 2026-04-15 and earlier) for multi-LLM scannability.

---

### Phase 4.5 — Backlog-by-file cycle 4 (2026-04-17)

22 mechanical bug fixes across 16 source files (HIGH + MEDIUM + LOW). File-grouped commits, continuing cycles 1–3 cadence. Tests: 1754 → 1810 (+56).

**Pipeline:** requirements → threat model + CVE baseline → brainstorm → parallel R1 Opus + R2 Codex design review → Opus decision gate → Codex plan + gate → TDD impl → CI hard gate → security verify + CVE diff → docs → PR → 2-round PR review.

**Scope narrowed to 22 at design gate** (cycle 3 verify-before-design lesson applied up-front):

- **7 already shipped** (grep-confirmed): #4 source_type whitelist, #6 MAX_QUESTION_LEN + stale marker, #8 ambiguous page_id match, #9 title cap 500, #10 source_refs is_file, #21 frontmatter_missing_fence, #30 FRONTMATTER_RE
- **1 deferred** (too architecturally deep for mechanical cleanup): #3 `[source: X]` → `[[X]]` citation migration — requires atomic update of 15+ test callsites + `extract_citations()` + `engine.py` — tracked in [BACKLOG.md](BACKLOG.md) Phase 4.5

Test behavioural rewrites: `TestSortedWikilinkInjection` + `TestContradictionMetadataMigration` after PR R1 Sonnet flagged both as signature-only.

#### Fixed — Backlog-by-file cycle 4 (22 items)

- `mcp/core.py` — `_rel()` sweep on error-string `Path` interpolations; `kb_ingest` 'source file not found' no longer leaks absolute filesystem paths (item #1)
- `mcp/core.py` + `utils/text.py` — `_sanitize_conversation_context` strips `<prior_turn>` / `</prior_turn>` fences (case-insensitive, with optional attributes) AND fullwidth angle-bracket variants (U+FF1C / U+FF1E) limited to fence-match region AND control characters via `yaml_sanitize`, before passing context to the rewriter LLM. Prevents fence-escape prompt injection via attacker-controlled conversation context (item #2)
- `mcp/core.py` — `kb_ingest_content` and `kb_save_source` post-create OSError paths now return `Error[partial]: ...` string with `overwrite=true` retry hint + `logger.warning` for operator audit. Previous `except BaseException: ... raise` violated the MCP "tools return strings, never raise" contract (item #5)
- `mcp/browse.py` — `kb_read_page` caps response body at `QUERY_CONTEXT_MAX_CHARS` with explicit `[Truncated: N chars omitted]` footer. Prevents MCP transport DoS from a runaway wiki page whose append-only Evidence Trail grew unbounded (item #7)
- `mcp/quality.py` — `kb_affected_pages` tightened to `_validate_page_id(check_exists=True)`; a typo'd page_id now returns `Error: Page not found: ...` instead of silently reporting 'No pages are affected' (false-negative). Legacy `test_kb_affected_pages_no_affected` test updated in the same commit per cycle 3 `feedback_migration_breaks_negatives` memory (item #11)
- `lint/verdicts.py` — `add_verdict` caps per-issue `description` at `MAX_ISSUE_DESCRIPTION_LEN=4000` inside the library function. Prevents a direct-library caller passing `issues=[{'description': 1_000_000*'x'}] × 100` from inflating a single verdict entry to ~100MB and thrashing the mtime-keyed verdict cache (item #12)
- `mcp/app.py` — `_validate_page_id` rejects Windows reserved basenames cross-platform (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) AND enforces `len(page_id) <= 255`. Reject happens on basename stem (before first dot), so `CON.backup` also fails matching Windows CreateFile semantics. Rationale: cross-platform corpus portability — a wiki file named `NUL.md` created on Linux would brick the whole Windows sync path (item #13)
- `compile/compiler.py` + `mcp/health.py` — `kb_detect_drift` surfaces deleted raw sources as distinct 'source-deleted' category + companion 'Pages Referencing Deleted Sources' section. `detect_source_drift()` return dict gains `deleted_sources` + `deleted_affected_pages` keys. Previously the drift case most likely to corrupt lint fidelity (wiki page still cites a deleted source) was silently pruned from the manifest without surfacing (item #14)
- `query/rewriter.py` — `_should_rewrite` adds `_is_cjk_dominant` + universal short-query gate (`len(question.strip()) < 15`) so CJK follow-ups like `什么是RAG` / `它是什么` skip the scan-tier LLM rewrite call. Prior heuristic used `question.split()` which returns `[question]` for CJK (no whitespace separators), causing every CJK query to ALWAYS trigger rewrite (item #15)
- `query/engine.py` + `utils/text.py` — new `_WIKI_BM25_CACHE` mirrors cycle 3's `_RAW_BM25_CACHE`. Both keys now include `BM25_TOKENIZER_VERSION` so tokenizer-semantic changes (STOPWORDS prune, new sanitize) invalidate stale indexes without requiring a file touch (items #16 + #18 invalidation path)
- `query/dedup.py` — `_enforce_type_diversity` uses running quota (`tentative_kept * max_ratio` recomputed each iteration) instead of fixed cap based on input length. Ensures 'no type exceeds X%' contract holds regardless of input-to-output compression ratio from prior dedup layers (item #17)
- `utils/text.py` — STOPWORDS pruned by 8 overloaded quantifiers (`new`, `all`, `more`, `most`, `some`, `only`, `other`, `very`) that appear in legitimate technical entity names (All-Reduce, All-MiniLM, New Bing). `BM25_TOKENIZER_VERSION = 2` added as cache-key salt so cycle 4 deploys invalidate stale on-disk / in-memory BM25 indexes (item #18)
- `utils/text.py` — `yaml_sanitize` silently strips BOM (U+FEFF), LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR (U+2029). Common noise from Word / Google Docs / Obsidian pastes that corrupt YAML with no security benefit from rejection (item #19)
- `utils/wiki_log.py` — monthly rotation with ordinal collision. When `log.md` exceeds `LOG_SIZE_WARNING_BYTES` (500KB), append rotates to `log.YYYY-MM.md` (or `log.YYYY-MM.2.md`, `.3.md` on mid-month overflow). Rotation event logs at INFO before rename to preserve audit chain. Replaces the warn-only path that let `wiki/log.md` grow unbounded (item #20)
- `ingest/pipeline.py` — migrated contradiction-detection caller from list-returning `detect_contradictions` to `detect_contradictions_with_metadata` sibling. When `truncated=True`, pipeline now emits `logger.warning` naming the source_ref + checked/total counts so operators can detect coverage gaps. Legacy `detect_contradictions` signature preserved for non-pipeline callers (item #22)
- `graph/export.py` — `export_mermaid(graph=<Path>)` positional-form shim emits `DeprecationWarning` with v0.12.0 removal target. Behaviour preserved so no existing caller breaks this cycle (item #23)
- `query/bm25.py` — `BM25Index.__init__` precomputes `_postings: dict[str, list[int]]` inverted index; `score()` iterates only docs that contain a query term instead of walking every doc per term. ~25× speedup on sparse queries at 5k-page scale. Memory profile documented as ~150 MB (item #24)
- `compile/compiler.py` — `_template_hashes` filters by `VALID_SOURCE_TYPES` instead of just excluding tilde/dotfile prefixes. Prevents editor backup files (`article.yaml.bak`, `*.yaml.swp`) from entering the manifest and triggering a full re-ingest when they change (item #25)
- `.env.example` — added commented `CLAUDE_SCAN_MODEL` / `CLAUDE_WRITE_MODEL` / `CLAUDE_ORCHESTRATE_MODEL` env-override vars to close drift vs `config.py:65-69` + CLAUDE.md model tier table (item #26)
- `CLAUDE.md` — documented `query_wiki` return-dict `stale` + Phase 4.11 output-adapter `output_format` / `output_path` / `output_error` keys (item #27)
- `utils/pages.py` — `load_purpose` signature tightened: `wiki_dir` is now REQUIRED. Previous `wiki_dir: Path | None = None` fallback silently leaked production `WIKI_DIR` into tests that forgot to pass `tmp_wiki`. All current callers (`query/engine.py:653`, `ingest/extractors.py:335`) already pass explicit `wiki_dir`; `extract_from_source` gains a local default via `from kb.config import WIKI_DIR` for its own `wiki_dir=None` back-compat (item #28)
- `ingest/pipeline.py` — retroactive wikilink injection loop sorts `(pid, title)` pairs descending by title length before iterating `inject_wikilinks`. Prevents short titles like `RAG` from swallowing body text that longer entities like `Retrieval-Augmented Generation` should own; tie-break on pid for deterministic ordering (item #29)

#### Test-backfill (already-shipped items #6, #8, #9, #10)

- `tests/test_backlog_by_file_cycle4.py::TestStaleMarkerInSearch` — shipped `[STALE]` surfacing in `kb_search` output
- `tests/test_backlog_by_file_cycle4.py::TestAmbiguousPageId` — shipped ambiguous case-insensitive match rejection in `kb_read_page` (NTFS-safe via mocked glob since NTFS can't hold two case-variants simultaneously)
- `tests/test_backlog_by_file_cycle4.py::TestTitleLengthCap` — shipped 500-char title cap in `kb_create_page`
- `tests/test_backlog_by_file_cycle4.py::TestSourceRefsIsFile` — shipped `is_file()` check on `source_refs` in `kb_create_page`

#### Security posture (cycle 4)

- **PR-introduced CVE diff:** 0 entries vs Step-2 baseline (`pip-audit` clean).
- **Class-A existing CVEs patched at Step 12.5:** `langsmith` 0.7.25 → 0.7.32 (GHSA-rr7j-v2q5-chgv resolved), `python-multipart` 0.0.22 → 0.0.26 (CVE-2026-40347 resolved). `requirements.txt` already pinned the patched versions — cycle 4 only synced the stale local venv.
- **Accepted risk:** `diskcache==5.6.3` CVE-2025-69872 — no patched release published; tracked in BACKLOG for next-cycle watchlist. `pip==24.3.1` toolchain CVEs — not runtime code.

#### Stats

1810 tests across 127 test files; +56 tests vs cycle 3 baseline (1754); 22 items across 16 source files on `feat/backlog-by-file-cycle4`.

### Phase 4.5 — Backlog-by-file cycle 3 (2026-04-17)

24 mechanical bug fixes across 16 source files (HIGH + MEDIUM + LOW) plus 2 security-verify follow-ups. One commit per file; full feature-dev pipeline (threat model → parallel design review → Opus decision gate → Codex plan + gate → TDD impl → CI hard gate → Codex security verify → docs → PR → review rounds) gated via subagents. Test count 1727 → 1754 (+27).

During design review, R1 Opus flagged that 9 of the original 30-item design-spec entries were ALREADY SHIPPED in cycles 1 and 2 (wiki_log is_file, markdown code-block strip, load_feedback widen, reliability trust-recompute, rewriter WH-question, kb_search stale marker, source_type validation, kb_ingest stat pre-check, rewrite_query leak-prefix). Decision-gate dropped those items and rescoped to 24 genuinely-open items plus 2 security-verify closures. This is the first cycle where "verify-before-design" changed scope midflight and the lesson is recorded in the self-review.

#### Fixed — Backlog-by-file cycle 3 (24 items + 2 security-verify)

- `utils/llm.py` `_make_api_call` — branch `anthropic.BadRequestError` / `AuthenticationError` / `PermissionDeniedError` BEFORE generic `APIStatusError`; raise non-retryable `LLMError(kind="invalid_request"|"auth"|"permission")`. Caller-bug 4xx classes no longer consume retries. `LLMError` gains a typed `kind` attribute with documented taxonomy so callers can programmatically recover without string-matching (H1)
- `utils/llm.py` `_make_api_call` — drop dead `last_error = e` on non-retryable `APIStatusError` branch (raise-immediately path has no consumer) (L1)
- `utils/io.py` `file_lock` — split over-broad `except (FileExistsError, PermissionError)` into separate branches. `FileExistsError` continues retry / stale-lock handling; `PermissionError` raises `OSError(f"Cannot create lock at {lock_path}: {exc}")` immediately instead of spinning to deadline and then attempting to "steal" a lock the operator cannot create (H2)
- `feedback/store.py` `add_feedback_entry` — `unicodedata.normalize("NFC", pid)` on every cited page id before dedup/`page_scores` mutation. Pages whose IDs differ only in NFC vs NFD form (macOS HFS+ filenames vs everywhere-else) now collapse into one trust-score entry instead of accumulating separate (useful, wrong, incomplete, trust) tuples (M3)
- `feedback/reliability.py` `compute_trust_scores` — docstring documents the Bayesian asymptote: wrong-weight is ~1.5× at small N, converging to 2× at high N. Prevents future tests from asserting literal 2× at small N (L5)
- `query/embeddings.py` `VectorIndex.query` — cache stored dim via `PRAGMA table_info(vec_pages)` on first query; on dim mismatch log ONE warning and return `[]` without raising. Empty DB / missing-table returns `[]` silently (not a mismatch). Prevents silent hybrid→BM25-only degradation after a model swap without rebuild (H7)
- `query/embeddings.py` `get_vector_index` — add `_index_cache_lock` with double-checked locking matching `_model_lock` + `_rebuild_lock` pattern. Concurrent FastMCP worker threads observe a single shared `VectorIndex` instance (H8)
- `query/embeddings.py` `VectorIndex.build` — validate `dim` is `int` in `[1, 4096]` before f-string interpolation into `CREATE VIRTUAL TABLE vec_pages USING vec0(embedding float[{dim}])`. Hardens SQL path against bug-introduced non-int or oversized dim from future chunk-indexing callers (L2)
- `query/engine.py` `_build_query_context` — prefix page header with `[STALE]` marker when `page["stale"]` is True. Surfaces staleness INSIDE the synthesis prompt so the LLM can caveat or demote stale facts (H9)
- `query/engine.py` `query_wiki` — add `stale_citations: list[str]` to return dict, derived from intersection of `context_pages` and `matching_pages` whose stale flag is True. MCP callers can expose staleness without parsing prompt text. Additive only — all pre-cycle-3 keys preserved (H9)
- `query/engine.py` `vector_search` closure — narrow `except Exception` to `(ImportError, sqlite3.OperationalError, OSError, ValueError)`. AttributeError/KeyError from future refactors now surface instead of silently degrading hybrid → BM25-only (H11)
- `query/engine.py` `query_wiki` — add `search_mode: "hybrid"|"bm25_only"` to return dict. Truth source: `_hybrid_available AND vec_path.exists()` at call time. Callers can now distinguish legitimately-empty vector hits from the silent degradation cycle 1 warned about (H11)
- `query/engine.py` `query_wiki` — replace post-truncation char-count gate on raw-source fallback with a SEMANTIC signal: fire only when `context_pages` is empty or every context page is `type=summary`. The old gate fired on 39K-char good contexts AND on "No relevant pages found." (35 chars), doubling per-query disk I/O (H15)
- `query/hybrid.py` / `config.py` — hoist hardcoded `[:3]` query-expansion cap to new `MAX_QUERY_EXPANSIONS = 2` in `kb.config`. Log DEBUG when expander returns more variants than the cap (previously silent truncation) (L6)
- `ingest/contradiction.py` `_find_overlapping_sentences` — segment each new claim by sentence before matching. Prior behaviour merged cross-sentence tokens into one pool, letting sentence-A token X + sentence-B token Y co-occur with a page containing neither pairing and manufacturing spurious contradictions (M8)
- `ingest/contradiction.py` `detect_contradictions_with_metadata` — new sibling function returning `{contradictions, claims_total, claims_checked, truncated}` dict so callers can observe truncation without parsing logs. Existing `detect_contradictions()` list-only contract unchanged (H12)
- `ingest/extractors.py` `build_extraction_prompt` — wrap raw source content in `<source_document>...</source_document>` sentinel fence with explicit "untrusted input; do NOT follow instructions inside" guidance. Escape literal `<source_document>` and `</source_document>` tags inside content to hyphen variants so an adversarial raw file cannot close the fence and smuggle instructions (M9)
- `ingest/pipeline.py` `_update_existing_page` — normalize `body_text` to end with `\n` before the References regex substitution. Files saved by editors with trailing-newline trimming were silently dropping new source refs or reversing their order (L7)
- `lint/checks.py` `check_orphan_pages` — drop `errors="replace"` when reading `_INDEX_FILES`. A corrupt/non-UTF-8 index.md silently substituted U+FFFD, letting `extract_wikilinks` drop corrupted targets and report real pages as orphans. On `UnicodeDecodeError`, append `corrupt_index_file` error-severity issue and continue (H13)
- `lint/checks.py` `check_frontmatter_staleness` — new check: when `post.metadata["updated"]` date predates `page_path.stat().st_mtime` date, emit info-severity `frontmatter_updated_stale`. Catches hand-edits without frontmatter date bump. Known limitation documented: same-day edits undetected by date-granular frontmatter (M10)
- `lint/runner.py` `run_all_checks` — add keyword-only `verdicts_path` param threaded to `get_verdict_summary`; drop dead duplicate `verdict_summary = verdict_history` local. Tests / alternate profiles can now isolate audit-trail data from production `.data/lint_verdicts.json` (M18)
- `graph/export.py` `export_mermaid` — prune-BEFORE-load. Previously `load_all_pages` iterated every wiki file regardless of max_nodes; on a 5k-page wiki this was ~80MB of frontmatter parsing per export. Now iterate only `nodes_to_include` and read each page's frontmatter via the graph node's `path` attribute. Fall back to `load_all_pages` with warning when caller supplies a custom graph lacking `path` metadata (M11)
- `graph/export.py` title fallback — already preserved hyphens in cycle 2; cycle 3 regression test locks this in against future drift (L4)
- `review/context.py` `build_review_context` — emit `logger.warning("Source not found during review context: %s (page %s)", ...)` for every source whose content could not be loaded. Prior "source file not available" appeared only inside rendered review text; integrity dashboards aggregating logs can now alert (M12)
- `mcp/browse.py` `kb_list_pages` / `kb_list_sources` — add `limit` (clamped `[1, 1000]`) + `offset` (clamped `>=0`) params. For `kb_list_sources`, flatten per-subdir entries after the G1 per-subdir cap so pagination is deterministic. Preserve legacy `Total: N page(s)` line alongside the new `Showing Y of N (offset=X, limit=L)` pagination header for backcompat with existing test assertions (M13)
- `mcp/health.py` `kb_graph_viz` — reject `max_nodes=0` with explicit Error string. Docstring previously advertised 0 as "all nodes" but code silently remapped to 30, returning a 30-node slice with no signal to agents following the docstring (M16)
- `utils/text.py` `truncate` — head+tail smart truncation with `"...N chars elided..."` marker. Prior head-only slice destroyed diagnostic tails in tracebacks (exception class in head, failing frame in tail). Default limit bumped 500 → 600 (M17)
- `cli.py` `_truncate` — delegate to `kb.utils.text.truncate` so CLI errors inherit the new head+tail behaviour. Default limit aligned at 600 (M17 security-verify follow-up)
- `mcp/browse.py` `kb_list_pages` / `kb_list_sources` — wrap `int(limit)` / `int(offset)` coercion in `try/except (TypeError, ValueError)` returning an Error string; malformed MCP input (e.g. `limit="x"`) no longer raises through the FastMCP framework boundary (MCP contract: tools never raise) (Security-verify follow-up)

#### Changed

- `LLMError` gains a keyword-only `kind` attribute (default `None`); documented taxonomy: `invalid_request` / `auth` / `permission` / `status_error`. Existing `raise LLMError(msg) from e` callers unchanged.
- `query_wiki` result dict gains `stale_citations: list[str]` and `search_mode: "hybrid"|"bm25_only"` as additive keys — no existing key was removed or renamed.
- `kb_list_pages` / `kb_list_sources` MCP tools gain `limit`/`offset` kwargs with documented defaults.
- `rrf_fusion` still merges metadata on collision (cycle 1 Q2 preserved); `MAX_QUERY_EXPANSIONS` constant replaces hardcoded `[:3]` slice.

#### Stats

1754 tests across 126 test files; +27 tests vs cycle 2 baseline (1727); 24 items across 16 source files + 2 security-verify follow-ups landed as 20 commits on `feat/backlog-by-file-cycle3`.

### Phase 4.5 — Backlog-by-file cycle 2 (2026-04-17)

30 mechanical bug fixes across 19 files (HIGH + MEDIUM + LOW) grouped by file, cycle-1 profile. One commit per file; full pipeline (threat model → design gate → plan gate → implementation → regression tests → security verification) gated end-to-end via subagents.

#### Fixed — Backlog-by-file cycle 2 (30 items)

- `utils/hashing.py` `content_hash` / `hash_bytes` — normalize CRLF / lone CR to LF before hashing so Windows clones with `core.autocrlf=true` hash the same as POSIX; prevents full corpus re-ingest on first compile (LOW)
- `utils/markdown.py` `_strip_code_spans_and_fences` — fast-path `startswith("---")` before running `FRONTMATTER_RE.match`; saves regex work for every page without frontmatter in `build_graph` + `load_all_pages` hot paths (MED R2)
- `utils/wiki_log.py` `append_wiki_log` — zero-width-space-escapes leading `#`/`-`/`>`/`!` and `[[...]]` wikilinks in operation + message; audit entries no longer render as active headings, lists, callouts, or clickable links when an ingested source contains markdown markup (MED R4 #8 + R5 #9 retained + LF `newline="\n"` #29)
- `utils/io.py` `file_lock` — sets `acquired=True` only AFTER `os.write` returns successfully; cleanup branch unlinks the lock file if `os.write` fails so the next waiter does not encounter an empty-content lock that the RAISE-on-unparseable policy rejects forever (LOW R6 #1 + PR review R3 MAJOR regression fix); ASCII-decodes lock PID and RAISES `OSError` on decode/int-parse failure instead of silently stealing the lock; `_purge_legacy_locks()` now runs LAZILY on first `file_lock` acquisition rather than at module import (PR review R1 MAJOR) (MED R3 #2)
- `utils/io.py` `atomic_json_write` / `atomic_text_write` — `f.flush() + os.fsync()` before `Path.replace` to prevent half-written files from atomically replacing a good file on crash (MED R5 #3); tempfile cleanup failures now log WARNING instead of silent swallow, without masking the original exception (MED R5 #4)
- `utils/llm.py` `call_llm_json` — collects ALL `tool_use` blocks and raises listing every block name when Claude returns multiple; prior code silently discarded all but the first (HIGH R4 #5)
- `utils/llm.py` `_backoff_delay` — applies 0.5-1.5× jitter per attempt then clamps to `RETRY_MAX_DELAY`; prevents thundering-herd retries when two MCP processes hit 429 simultaneously. Pre-existing `test_llm.py::test_call_llm_exponential_backoff` + `test_backoff_delay_values` updated to assert jittered window instead of exact-value equality (MED R5 #6)
- `utils/llm.py` `_make_api_call` — `LLMError` truncates `e.message` to ≤500 chars via shared `kb.utils.text.truncate` helper; preserves exception class name, model ID, and `status_code` verbatim; prevents Anthropic error bodies that echo full prompts from leaking into logs. Truncation applies to BOTH the non-retryable branch and the retry-exhausted branch (Step 11 security verify gap fix) (MED R4 #7)
- `utils/text.py` `truncate` — moved from `kb.cli._truncate` so utility modules (`llm`, `wiki_log`, etc.) no longer import downward into the CLI layer; eliminates latent circular-import risk on the LLM error path (PR review R1 MAJOR)
- `utils/io.py` `file_lock` PID liveness — Windows-specific: any `OSError` from `os.kill(pid, 0)` treats the PID as unreachable and steals (Windows `os.kill` raises generic `OSError` on nonexistent PIDs). POSIX: only `ProcessLookupError` steals; non-`ProcessLookupError` `OSError` (typically EPERM) correctly raises `TimeoutError` to avoid stealing a live lock held by another user (PR review R1 MAJOR)
- `graph/export.py` `export_mermaid` — tie-break switched from `heapq.nlargest(key=(x[1], x[0]))` (ID DESC on ties) to `sorted(key=(-degree, id))[:max_nodes]` so equal-degree nodes are ordered `id ASC` per spec (PR review R1 MAJOR #27)
- `ingest/evidence.py` `build_evidence_entry` vs `format_evidence_entry` — split restored: `build_*` stores byte-clean raw `source_ref`/`action`; `format_*(date_str, source, summary)` (RENDER path, original positional contract preserved per PR review R3 MAJOR) backtick-wraps pipes; `append_evidence_trail` calls `format_*` so stored entries remain backward-compatible
- `query/engine.py` `query_wiki` — `normalized_question = re.sub(r"\s+", " ", question)` is the SINGLE source of truth; `rewrite_query` receives the normalized form, leak-fallback reverts to normalized (not raw), so item 12's whitespace collapse is no longer silently undone on the rewrite path (PR review R1 MAJOR)
- `ingest/evidence.py` `format_evidence_entry` — backtick-wraps `source`/`summary` when either contains `|`; pipe-delimited parsers no longer misalign on a legitimate pipe. `build_evidence_entry` stays byte-for-byte clean; `append_evidence_trail` now writes via `format_evidence_entry` (LOW R4 #28 + PR review R1 MAJOR restored after R3 positional review)
- `compile/linker.py` `inject_wikilinks` — single `_FRONTMATTER_RE.match` call per page; body-check and split share the match result, halving regex cost for N-titles-per-ingest (MED R4 #26)
- `feedback/store.py` `load_feedback` — one-shot schema migration backfills legacy `useful` / `wrong` / `incomplete` count keys once at load; `trust` is NOT backfilled so `get_flagged_pages` can recompute it from counts (cycle-1 Q2 semantics); per-write `setdefault` loop removed from `add_feedback_entry` (LOW R4 #24)
- `feedback/reliability.py` `get_coverage_gaps` — dedup now keeps entry with LONGEST notes (ties broken by newest timestamp); prior first-occurrence policy suppressed later, more-specific notes (MED R2 #25)
- `evolve/analyzer.py` `find_connection_opportunities` — strips `[[wikilink]]` markup + drops purely-numeric tokens before tokenising; prior behaviour flagged pages sharing year/version numbers or wikilink slug fragments as false "connection opportunities" (MED R2+R4 #18, #19)
- `evolve/analyzer.py` `generate_evolution_report` — narrowed over-broad `(ImportError, AttributeError, OSError, ValueError)` catch around `get_flagged_pages` to `(KeyError, TypeError)`; OSError on feedback read now propagates so disk faults surface instead of producing a silent empty flagged-list (MED R4 #20)
- `lint/trends.py` `compute_verdict_trends` — now accepts either a path or a list of verdict dicts; surfaces `parse_failures` counter in the returned dict so malformed-timestamp counts no longer silently widen the gap between `total` and `sum(periods)` (MED R5 #21)
- `lint/trends.py` `_parse_timestamp` — dropped vestigial `ValueError` fallback for date-only strings; project pins Python 3.12+ where `datetime.fromisoformat` parses both forms natively (LOW R4 #22)
- `lint/semantic.py` `_group_by_term_overlap` — already imports shared `FRONTMATTER_RE` from `kb.utils.markdown`; cycle-2 regression test locks the import in place to prevent re-divergence in future edits (LOW R4 #23)
- `graph/export.py` `export_mermaid` — auto-prune key bumped from `lambda x: x[1]` to `lambda x: (x[1], x[0])` so equal-degree nodes are selected deterministically (degree desc, id asc); prevents the committed architecture PNG from churning between runs (MED R2 #27)
- `query/citations.py` `extract_citations` — dedups citations by `(type, path)` preserving the first occurrence's context (LOW R1 #17)
- `query/hybrid.py` `hybrid_search` — wraps `bm25_fn()` and `vector_fn()` in try/except returning `[]`; structured WARN log reports backend name, exception class, exception text, and `len(question.split())` as token proxy; prevents a corrupt page dict or sqlite-vec schema drift from crashing the MCP tool (HIGH R4 #16)
- `query/dedup.py` `dedup_results` — optional `max_results: int | None = None` clamp applied AFTER all four dedup layers (MED R4 #15); layer 2 falls back to lowercasing `content` when `content_lower` is missing so MCP-provided citations and future chunk rows participate in similarity dedup (MED R4 #30)
- `query/rewriter.py` `_should_rewrite` — cycle-1 WH-question + proper-noun skip is now locked in by a cycle-2 regression test (LOW R4 #14 retained)
- `query/engine.py` `query_wiki` — `effective_question` uses `re.sub(r"\s+", " ", …).strip()` so ALL Unicode whitespace (tabs, vertical tab, U+2028, U+2029, non-breaking space, …) collapses to a single space before search; prior code only replaced `\n`/`\r` in the synthesis prompt (LOW R4 #12)
- `query/engine.py` `search_raw_sources` — `path.stat().st_size > RAW_SOURCE_MAX_BYTES` pre-check skips oversized files with an INFO log BEFORE `read_text`, so a 10 MB scraped article cannot balloon the in-memory corpus; YAML frontmatter stripped via shared `FRONTMATTER_RE` before tokenizing so title/tags no longer mis-rank results (MED R4 #13)
- `config.py` — new `RAW_SOURCE_MAX_BYTES = 2_097_152` (2 MiB) paired with `CAPTURE_MAX_BYTES`; single source of truth for the raw-source size cap (MED R4 #13)

### Phase 4.5 — Backlog-by-file cycle 1 (2026-04-17)

38 mechanical bug fixes across 18 files (HIGH + MEDIUM + LOW) grouped by file instead of by severity. One commit per file; full pipeline (threat model → design review → plan gate → implementation → regression tests → security verification) gated end-to-end via subagents.

#### Fixed — Backlog-by-file cycle 1 (38 items)

- `ingest/pipeline.py` `ingest_source` — accepts `raw_dir=None` kwarg threaded to `detect_source_type` + `make_source_ref` so custom-project augment runs can honor caller raw/ (three-round HIGH)
- `ingest/pipeline.py` `ingest_source` — enforces `SUPPORTED_SOURCE_EXTENSIONS` inside the library, not only at the MCP wrapper; suffix-less files (README, LICENSE) now rejected (Phase 4.5 MED)
- `ingest/pipeline.py` contradiction detection — narrowed bare `except Exception` to `(KeyError, TypeError, ValueError, re.error)`; warnings promoted from DEBUG (Phase 4.5 R4 HIGH)
- `lint/augment.py` `run_augment` — passes `raw_dir` to `ingest_source`; adds `data_dir` kwarg derived from `wiki_dir.parent / .data` on custom-wiki runs; rejects `max_gaps < 1`; re-runs `_url_is_allowed` on reviewed proposal URLs before `RateLimiter.acquire` (three-round HIGH + 3× MED)
- `lint/_augment_manifest.py` `Manifest` — `start` / `resume` accept `data_dir` so custom-project runs do not leak manifests into the main repo's `.data/` (three-round MED)
- `lint/_augment_rate.py` `RateLimiter` — accepts `data_dir` kwarg; rate state follows the supplied project (three-round MED)
- `cli.py` / `mcp/health.py` — both reject `max_gaps < 1` at the public surface (three-round MED)
- `capture.py` `_render_markdown` — removed dead `slug: str` param + 6 test call sites (R3 MED)
- `capture.py` `_CAPTURE_SCHEMA` — `body.maxLength=2000` caps LLM return size (LOW)
- `capture.py` `capture_items` / `_write_item_files` — `captures_dir=None` kwarg threaded to all three `CAPTURES_DIR` references (R2 MED + R3 MED)
- `capture.py` `_CAPTURE_SECRET_PATTERNS` — env-var regex matches suffix variants (`ANTHROPIC_API_KEY`, `DJANGO_SECRET_KEY`, `GH_TOKEN`, `ACCESS_KEY`) + optional shell `export ` prefix; requires `\S{8,}` value to reject `TOKEN_EXPIRY=3600` (MED + 2× LOW)
- `capture.py` `_path_within_captures` — accepts `base_dir=None` and uses the module-level `_CAPTURES_DIR_RESOLVED` cache (MED)
- `capture.py` Authorization regex — split into Basic + Bearer patterns; opaque OAuth/Azure/GCP Bearer tokens (16+ chars) now detected (LOW)
- `ingest/extractors.py` `extract_from_source` — deepcopy schema from the `lru_cache` before handing to the SDK so mutation in one call cannot poison the next (Phase 4.5 MED)
- `ingest/extractors.py` `build_extraction_prompt` — caps `purpose` interpolation at 4096 chars (R4 HIGH — cap-only subset; sentinel markup deferred)
- `ingest/contradiction.py` `_extract_significant_tokens` — two-pass tokenization preserves single-char / acronym language names (C, R, C#, C++, F#, Go, .NET) (R4 HIGH)
- `mcp/quality.py` `kb_create_page` — O_EXCL exclusive-create replaces `exists()` + `atomic_text_write`; source_refs existence check; title capped at 500 chars + control-char stripped (Phase 4.5 MED + 2× LOW)
- `mcp/quality.py` `kb_refine_page` — caps `revision_notes` at `MAX_NOTES_LEN` and `page_id` at 200 chars before path construction / log writes (Phase 4.5 MED)
- `mcp/browse.py` `kb_list_sources` — `os.scandir` + per-subdir cap 500 + total response size cap 64KB; skips dotfiles (Phase 4.5 MED)
- `mcp/browse.py` `kb_search` — rejects queries over `MAX_QUESTION_LEN`; surfaces `[STALE]` alongside score (R4 HIGH)
- `mcp/browse.py` `kb_read_page` — returns ambiguity error when case-insensitive fallback matches >1 file (R4 LOW)
- `mcp/core.py` `kb_ingest` — `stat().st_size` pre-check against `MAX_INGEST_CONTENT_CHARS*4` bytes prevents OOM read before truncate; validates `source_type in SOURCE_TYPE_DIRS` (Phase 4.5 HIGH + R4 HIGH)
- `query/engine.py` `_flag_stale_results` — UTC-aware `datetime.fromtimestamp(..., tz=UTC).date()` eliminates local-TZ/naive mismatch (Phase 4.5 MED)
- `query/engine.py` `search_raw_sources` — BM25 index cached keyed on `(raw_dir, file_count, max_mtime_ns)` (Phase 4.5 MED)
- `query/engine.py` `query_wiki` — rejects rewrite output containing newlines or `Sure|Here|Rewritten|Standalone|Query:` preambles; falls back to original (R4 HIGH)
- `query/rewriter.py` `rewrite_query` — absolute `MAX_REWRITE_CHARS=500` ceiling + floor `max(3*len, 120)`; replaces the 3×-only bound (Phase 4.5 MED)
- `query/rewriter.py` `_should_rewrite` — skips WH-questions ending in `?` that contain a proper-noun / acronym body (R4 LOW)
- `query/dedup.py` `_dedup_by_text_similarity` — caches `_content_tokens` per kept result; eliminates O(n·k) re-tokenization (Phase 4.5 MED)
- `lint/verdicts.py` `load_verdicts` — `(mtime_ns, size)` cache with explicit `save_verdicts` invalidation (Phase 4.5 MED)
- `lint/checks.py` `check_source_coverage` — short-circuits on pages missing opening frontmatter fence, emitting a frontmatter issue (R4 HIGH)
- `utils/markdown.py` `extract_wikilinks` — `_strip_code_spans_and_fences` helper strips fenced blocks, inline code, and frontmatter before pattern matching (R4 HIGH)
- `feedback/store.py` `load_feedback` — widened except to `(JSONDecodeError, OSError, UnicodeDecodeError)` for full corruption-recovery (R5 HIGH)
- `feedback/reliability.py` `get_flagged_pages` — recomputes trust from raw counts when `trust` key missing instead of defaulting to 0.5 (R4 HIGH)
- `review/refiner.py` `refine_page` — imports shared `FRONTMATTER_RE`; caps `revision_notes` at `MAX_NOTES_LEN` before log writes (R4 HIGH + R4 LOW)
- `utils/wiki_log.py` `append_wiki_log` — verifies `log_path.is_file()` so directory / symlink / FIFO targets raise a clear `OSError` instead of a misleading second error from `open("a")` (R5 HIGH)

#### Added — regression coverage

- `tests/test_backlog_by_file_cycle1.py` — 30 parameter / behaviour / regex / path fixtures covering the batch above

#### Decisions

- `docs/superpowers/decisions/2026-04-17-backlog-by-file-cycle1-design.md` — batch-size, deferral, and dependency ordering rationales
- `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle1-design.md` — file-grouped scope + test expectations per item

#### PR review — 3 rounds (Opus + Sonnet + 3× Codex)

Round 1 (Opus + Sonnet parallel, Codex round 1): 11 findings addressed
in commit `fix(pr-review-r1)`:
- `lint/checks.py` O1 issue key drift `type` → `check: frontmatter_missing_fence`
- `utils/wiki_log.py` S1 symlink rejection via `lstat` + `S_ISLNK`
- `lint/verdicts.py` M1 cache thread-safety + return-copy + invalidate-before-save
- `mcp/quality.py` F1 O_EXCL + fdopen in one try-block (signal-race fix)
- `mcp/core.py` H1 size cap aligned to `QUERY_CONTEXT_MAX_CHARS*4`
- `query/engine.py` I3 removed `_LEAK_PREFIX_RE` (dropped legit "RAG:…" rewrites); added raw BM25 cache lock
- `capture.py` A4 env-var regex accepts quoted-with-spaces values
- `feedback/store.py` Q1 re-raises `PermissionError` instead of swallowing
- Test updates: D1 exercises `extract_from_source` with SDK-mutating stub; A3 uses public `capture_items`; S1 symlink regression; I3 legit "RAG:" preserved; A4 quoted-secret; Q1 EACCES propagation

Round 2 (Codex round 2): 4 MAJORS addressed in commit `fix(pr-review-r2)`:
- `query/engine.py` I3 removed bare "sure"/"okay"/"alright" over-match
- `query/engine.py` I2 rebuild outside lock + double-check under lock
- `ingest/contradiction.py` E1 short-token whitelist {c,r,go,f,d}
- `BACKLOG.md` Phase 4.5 MEDIUM items collapsed to summary pointer

Round 3 (Codex round 3): **APPROVE** — no blocker-severity regressions. One pre-existing scope issue noted (`>= 2` overlap threshold in contradiction detection makes single-token language-name contradictions invisible; predates this PR).

Post-release audit fixes for Phase 4 v0.10.0 — all HIGH (23) + MEDIUM (~30) + LOW (~30) items.
Plus Phase 4.1 sweep: 16 LOW/NIT backlog items applied directly. One test expectation
(`TestSymlinkGuard.test_symlink_outside_project_root_refuses_import`) was updated to match
production (`RuntimeError` rather than `AssertionError`, following the assert → raise
migration that shipped in the original kb_capture PR); no new tests added, no test semantics changed.

Plus Phase 4.11: `kb_query --format={markdown|marp|html|chart|jupyter}` output adapters.

Plus Phase 5.0: `kb_lint --augment` reactive gap-fill (modules `kb.lint.fetcher` / `kb.lint.augment` / `kb.lint._augment_manifest` / `kb.lint._augment_rate`; CLI + MCP flags; three-gate propose → execute → auto-ingest). Plus three bundled fixes: `kb_lint` MCP signature drift (CLAUDE.md:245 `--fix` claim), `kb_lint` MCP `wiki_dir` plumbing, `_AUTOGEN_PREFIXES` consolidation, and npm / Postgres DSN secret patterns.

Plus backlog cleanup: removed 3 stale assert→RuntimeError items from Phase 5 kb-capture pre-merge section (all fixed and shipped in Phase 5 kb-capture release).

Plus Phase 4.5 CRITICAL cycle 1: 16 CRITICAL items from the post-v0.10.0 multi-agent audit, fixed across 4 themed commits (test-isolation, contract-consistency, data-integrity, error-chain) via an automated feature-dev pipeline with Opus decision gates + adversarial gates + branch-level Codex + security review.

Plus Phase 4.5 CRITICAL cycle 1 docs-sync (items 4 + 5): version-string alignment across `pyproject.toml` / `__init__.py` / README badge, CLAUDE.md stats updated to current counts (1552 tests / 119 test files / 67 py files / 26 MCP tools), and new `scripts/verify_docs.py` pre-push check. Also 5 new R6 BACKLOG entries from the 2-round post-PR review deferrals.

Plus Phase 4.5 HIGH cycle 1: 22 HIGH-severity items from the post-v0.10.0 multi-agent audit, fixed across 4 themed commits (wiki_dir plumbing, cross-process RMW locking, prompt-injection sanitization + security, error-handling + vector-index lifecycle) via the automated feature-dev pipeline with Opus design + plan decision gates.

### Phase 4.5 — HIGH cycle 2 (2026-04-17)

22 HIGH-severity bugs across 5 themes (Query, Lint, Data Integrity, Performance, DRY).

#### Fixed — Phase 4.5 HIGH cycle 2 (22 items)

- `utils/markdown.py` `FRONTMATTER_RE` — bounded to 10KB to prevent catastrophic backtracking on malformed pages (D3)
- `review/refiner.py` frontmatter guard — require YAML key:value between fences; horizontal rules (`---`) no longer rejected (D1)
- `review/refiner.py` — strip UTF-8 BOM before frontmatter parsing (D2)
- `evolve/analyzer.py` — replaced inlined frontmatter regex with shared `FRONTMATTER_RE` import (P3)
- `lint/semantic.py` `_group_by_term_overlap` — fixed `group(1)` → `group(2)` so consistency checking tokenizes body text, not YAML keys (L7)
- `ingest/extractors.py` — removed duplicate `VALID_SOURCE_TYPES`; uses `SOURCE_TYPE_DIRS` directly (C1)
- `compile/compiler.py` — imports `SOURCE_TYPE_DIRS` from config instead of extractors (C1)
- `lint/checks.py` `check_cycles` — bounded `nx.simple_cycles` to 100 via `itertools.islice` (L1)
- `lint/semantic.py` `_group_by_term_overlap` — replaced O(n²) pairwise loop with inverted postings index; removed 500-page wall (L2)
- `graph/builder.py` `build_graph` — accepts optional `pages: list[dict]` param to avoid redundant disk reads (L3)
- `lint/trends.py` `_parse_timestamp` — all timestamps now UTC-aware; date-only strings treated as midnight UTC (L4)
- `lint/trends.py` `compute_verdict_trends` — parse failures excluded from both `overall` and `period_buckets` (L5)
- `lint/semantic.py` `_render_sources` — per-source minimum budget floor of 500 chars; large wiki pages no longer starve source context (L6)
- `feedback/store.py` — eviction changed from activity-count to timestamp-based; oldest entries evicted first (D4)
- `ingest/contradiction.py` — claim truncation promoted from `logger.debug` to `logger.warning` with unchecked count (D5)
- `ingest/pipeline.py` — contradiction detection excludes pages created in current ingest to prevent noisy self-comparison (D6)
- `query/engine.py` `_build_query_context` — tier 1 budget enforced per-addition; one oversized summary no longer starves tier 2 (Q1)
- `query/hybrid.py` `rrf_fusion` — metadata merge preserves all fields on id collision, not just score (Q2)
- `query/rewriter.py` — strips smart quotes, backticks, and single quotes from LLM-rewritten queries (Q3)
- `graph/builder.py` `graph_stats` — PageRank and betweenness centrality include `status` metadata (ok/failed/degenerate) (Q4)
- `graph/builder.py` `build_graph` — bare-slug resolution uses pre-built `slug_index` dict for O(1) lookup (P1)
- `utils/pages.py` `load_all_pages` — `include_content_lower` param (default True) allows callers to skip unnecessary `.lower()` computation (P2)

#### Stats

- 1645 tests across 126 test files

### Phase 4.5 — HIGH cycle 1 (2026-04-16)

22 HIGH-severity bugs from Rounds 1-6 of the Phase 4.5 multi-agent audit. 4 themed commits.

#### Fixed — Phase 4.5 HIGH (22 items)

- `review/refiner.py` `refine_page` — page-file RMW lock via `file_lock(page_path)` (R6 HIGH)
- `ingest/evidence.py` `append_evidence_trail` — page-file lock around RMW (R2)
- `ingest/pipeline.py` `_persist_contradictions` — contradictions-path `file_lock` (R4)
- `utils/wiki_log.py` `append_wiki_log` — `file_lock` + retry-once; `log_path` now required (R2)
- `query/engine.py` `query_wiki` — dropped dead `raw_dir` containment `try/except` (R6 MEDIUM)
- `ingest/pipeline.py` `_is_duplicate_content` → `_check_and_reserve_manifest` — dual-phase `file_lock(MANIFEST_PATH)` around hash-dedup check+save (R2; fulfills cycle-1 C8 commitment)
- `ingest/pipeline.py` contradictions path — derived from `effective_wiki_dir` (R1)
- `utils/wiki_log.py` `append_wiki_log` — `wiki_dir`/`log_path` required parameter, no default (R2)
- `utils/pages.py` `load_purpose` + MCP `load_all_pages` — `wiki_dir` parameter (R2)
- `tests/conftest.py` `create_wiki_page` — factory requires explicit `wiki_dir` kwarg (R3)
- `ingest/pipeline.py` `_build_summary_content` + `_update_existing_page` — `sanitize_extraction_field` on all untrusted fields (R1; Q_J expansion)
- `compile/linker.py` `inject_wikilinks` — `wikilink_display_escape` replaces ad-hoc `safe_title` (R3)
- `ingest/evidence.py` — HTML-comment sentinel `<!-- evidence-trail:begin -->` with FIRST-match heuristic (R2)
- `ingest/pipeline.py` `_persist_contradictions` — `source_ref` newline/leading-`#` stripped (R2)
- `review/context.py` `build_review_context` — XML sentinels + untrusted-content instruction in `build_review_checklist` (R4; Q_L)
- `review/context.py` `pair_page_with_sources` — symlink traversal blocked outside `raw/` (R1 HIGH security)
- `query/citations.py` `extract_citations` — per-segment leading-dot rejection (R4)
- `utils/markdown.py` `WIKILINK_PATTERN` — 200→500-char cap + `logger.warning` on drop (R4)
- `query/rewriter.py` `rewrite_query` — narrowed `except` to `LLMError`; logs at WARNING (R5)
- `mcp/core.py` `kb_query` — category-tagged errors via `ERROR_TAG_FORMAT` in `mcp/app.py` (R5)
- `query/embeddings.py` + `ingest/pipeline.py` + `compile/compiler.py` — hybrid vector-index lifecycle: mtime-gated `rebuild_vector_index`, `_skip_vector_rebuild` for batch callers (R2)
- `mcp/core.py` `kb_query` — `conversation_context` wired in Claude Code mode (R4)
- `ingest/pipeline.py` `_update_existing_page` — returns on frontmatter parse error (R1)

#### Added

- `sanitize_extraction_field(value, max_len=2000)` helper in `kb.utils.text` — strips control chars, frontmatter fences, markdown headers, HTML comments, length-caps untrusted extraction fields
- `wikilink_display_escape(title)` helper in `kb.utils.text` — strips `]`/`[`/`|`/newlines for safe wikilink display
- `ERROR_TAG_FORMAT` constant + `error_tag(category, message)` helper in `kb.mcp.app` — categories: `prompt_too_long`, `rate_limit`, `corrupt_page`, `invalid_input`, `internal`
- `rebuild_vector_index(wiki_dir, force=False)` in `kb.query.embeddings` — mtime-gated with `_hybrid_available` flag
- `_persist_contradictions` helper extracted from inline `ingest_source` code
- `_check_and_reserve_manifest` replacing `_is_duplicate_content` with lock discipline
- `tests/fixtures/injection_payloads.py` — attack payload catalog from BACKLOG R1-R4

#### Fixed — Post-PR 2-round adversarial review (2026-04-16)

2-round review (1 Opus + 1 Sonnet) surfaced 1 major + 8 minors; 4 fixed in commit `330db40`:

- `ingest/pipeline.py` + `review/refiner.py` — `append_wiki_log` retry-then-raise crashed callers after successful page writes; now wrapped in try/except OSError with best-effort semantics (MAJOR)
- `utils/io.py` lock-order doc — corrected to note `refine_page` holds two locks (page_path then history_path)
- `ingest/pipeline.py` `_persist_contradictions` — space-then-hash source_ref edge case; `.strip()` before `.lstrip("#")`
- `review/refiner.py` — added missing `logger` import for new OSError warning

### Phase 4.5 — CRITICAL cycle 1 docs-sync (2026-04-16)

Immediately-following PR after cycle 1 merged. Addresses the 2 items the second-gate Opus review deferred from cycle 1 as preventive-infrastructure drive-by:

#### Fixed — Phase 4.5 CRITICAL (items 4 + 5)

- **`pyproject.toml` version alignment** (item 4) — bumped from `0.9.10` → `0.10.0` to match `src/kb/__init__.py.__version__` and the README badge. `pip install -e .` / `pip freeze` now report the correct version.
- **CLAUDE.md stats refresh** (item 5) — test count updated (1531 → 1552 actual), test-file count updated (1434-era claim → 119 actual), replaced ambiguous "24 modules" with "67 Python files in src/kb/", and added Phase 4.5 CRITICAL cycle 1 + docs-sync to the shipped-unreleased list.

#### Added

- **`scripts/verify_docs.py`** — pre-push / CI-friendly drift check:
  - Verifies `pyproject.toml` version == `src/kb/__init__.py.__version__` == README badge version.
  - Runs `pytest --collect-only` and compares collected count against CLAUDE.md's claimed "N tests" lines (tolerance ±10 by default; `KB_VERIFY_STRICT=1` env var for exact match).
  - Checks `CLAUDE.md`'s "across N test files" claim against the actual test-file count.
  - Reports source file count for reference (not gated — `src/kb/` file count shifts naturally across cycles).
  - Exit 0 on alignment, exit 1 on drift. Only REPORTS; does not auto-fix.

#### Changed — BACKLOG.md R6 additions

Five deferred findings from the post-PR 2-round adversarial review (commit `99e99d8` addendum) now logged for the next cycle:

- **Phase 4.5 HIGH:** `refine_page` page-file RMW race (no lock on the wiki page body itself; only history RMW was fixed in cycle 1 item 13).
- **Phase 4.5 MEDIUM:** `query_wiki` raw_dir containment-check tautology (the `try/except ValueError` block is dead code by construction; either remove or anchor against `PROJECT_ROOT` to make it enforce something).
- **Phase 4.5 LOW ×3:** `utils/io.py` `acquired = True` timing comment misleading; `utils/llm.py` `last_error = e` on non-retryable branch dead code; `test_compile_loop_does_not_double_write_manifest` monkeypatch brittleness.

---

### Phase 4.5 — Multi-agent audit CRITICAL cycle 1 (2026-04-15)

Resolves 16 CRITICAL items from the 2026-04-13 multi-agent post-v0.10.0 audit. 4 theme commits + 1 style fix + 1 post-review fix for `slugify` cross-cut regression. Theme 5 (docs-sync, items 4 + 5) deferred to immediately-following PR. Phase 4.5 HIGH/MEDIUM/LOW deferred to subsequent cycles.

#### Fixed — Phase 4.5 CRITICAL (16 items)

- **`ingest/pipeline.py` duplicate-branch result contract** (item 6) — duplicate re-ingest now returns the same keys (`affected_pages`, `wikilinks_injected`, `contradictions`) as the normal path, eliminating downstream `KeyError`.
- **`query/engine.py` raw-sandbox leak** (item 7) — `query_wiki(wiki_dir=...)` now threads `raw_dir` through to `search_raw_sources` via `(wiki_dir.parent / "raw").resolve()` derivation; tests no longer leak to production `raw/`.
- **`lint/checks.py` shared_graph mutation** (item 8) — `check_orphan_pages` operates on a graph copy; sentinel `_index:<name>` nodes no longer leak into downstream cycle checks. `_index:` prefix guard added to orphan warning filters so the sentinel never surfaces as a spurious orphan.
- **`lint/runner.py` fix-mode consistency** (item 9) — `run_all_checks(fix=True)` re-scans pages and rebuilds the graph after `fix_dead_links`; remaining checks run against post-fix state.
- **`review/refiner.py` lstrip code-block corruption** (item 10) — body rewrite uses `re.sub(r"\A\n+", "", ...)` to strip only leading blank lines; 4-space-indented code blocks preserved.
- **`review/refiner.py` audit cross-process lock** (item 13) — review-history RMW uses `file_lock` instead of in-process `threading.Lock`; concurrent refiners no longer silently lose audit entries.
- **`utils/text.py` slugify CJK** (item 11) — `re.ASCII` removed; CJK/Cyrillic/accented titles produce valid slugs; empty-result titles fall back to `untitled-<hash6>` for filename-needing contexts. Entity/concept extraction paths skip `untitled-*` sentinels so nonsense-punctuation entities (`"!!!"`) no longer create ghost pages (blocker B1 from branch-level Codex review).
- **`utils/markdown.py` empty wikilink target** (item 12) — `[[   ]]` whitespace-only links rejected; no more phantom empty-target graph nodes.
- **`utils/llm.py` non-retryable APIStatusError last_error tracking** (item 16) — `_make_api_call` sets `last_error = e` in the non-retryable branch for consistency with other except clauses.
- **`utils/llm.py` `call_llm_json` no-tool-use diagnostic** (item 17) — leading text-block content (up to 300 chars) preserved in `LLMError` message when the model returns text only (content-moderation refusals no longer look like generic API errors). Defensive `getattr(block, "type", None)` applied consistently.
- **`utils/io.py` file_lock SIGINT cleanup** (item 15) — lock-file acquisition moved inside the `try:` block with an `acquired` flag; KeyboardInterrupt during `os.write` no longer leaves orphan lock files.
- **`compile/compiler.py` + `ingest/pipeline.py` double manifest write** (item 14) — redundant per-loop manifest save removed; `ingest_source` already persists. `# TODO(phase-4.5-high)` planted at `_is_duplicate_content` for the next-cycle race-condition fix (manifest RMW is single-writer but unlocked).
- **`ingest/pipeline.py` UnicodeDecodeError + sandbox-escape `from e`** (item 18) — `raise ValueError(...) from e` on binary-file path; byte-offset diagnostic preserved. Same fix applied to `relative_to` ValueError at line 546 (sandbox-escape diagnostic preserved). `pipeline.py:456` and `extractors.py:74` audited and skipped (no caught exception to chain).
- **`tests/test_ingest.py` WIKI_CONTRADICTIONS patch** (item 1) — mock patches `kb.ingest.pipeline.WIKI_CONTRADICTIONS` to tmp wiki; production `wiki/contradictions.md` no longer mutated by test runs. Added explicit mtime-comparison regression test.
- **`tests/test_v0917_contradiction.py` split** (item 2) — dict-shape contract test seeds a provably-caught contradiction and asserts `len(result) >= 1` before the dict-key loop; empty-case split into separate test so the for-loop body never silently skips all assertions.
- **`tests/test_phase4_audit_security.py` positive assertions** (item 3) — `test_kb_refine_page_accepts_valid_content` now asserts `result["updated"] is True` and reads back the page file body.

#### Changed

- Existing test files updated to reflect behavior changes introduced by items 11 + 14: `test_v4_11_formats_common.py` (slugify `untitled-<hash>` fallback), `test_fixes_v060.py` + `test_v0913_phase394.py` + `test_compiler_mcp_v093.py` (compile-loop single-write manifest contract), `test_capture.py` + `test_utils.py` + `test_fixes_v050.py` + `test_v0914_phase395.py` (CJK slug preservation).

#### Post-PR 2-round adversarial review fixes (commit `4688763`)

Independent 2-round post-PR review (1 Opus architecture + 1 Sonnet edge-cases, dispatched when Codex CLI hit its usage quota) surfaced 1 blocker + 3 majors. All addressed before human merge:

- **`ingest/pipeline.py` `_is_untitled_sentinel` (blocker)** — the post-B1 fix's `slug.startswith("untitled-")` guards false-positived on legitimate entity names like `Untitled-Reports` (slug `untitled-reports`). Tightened to a regex `^untitled-[0-9a-f]{6}$` via new `_is_untitled_sentinel()` helper; all 3 guard sites updated. 2 new regression tests (legit names allowed, sentinel still blocked).
- **`review/refiner.py` CRLF defense-in-depth** — body regex `r"\A\n+"` → `r"\A[\r\n]+"` so Windows CRLF leading blanks strip even if the upstream `replace("\r\n", "\n")` normalization is bypassed.
- **`review/refiner.py` history_path wiki_dir derivation** — same test-isolation class as item 7; `refine_page(wiki_dir=tmp)` now derives `resolved_history_path = wiki_dir.parent / ".data" / "review_history.json"` instead of silently falling back to the production global. Regression test asserts prod `.data/review_history.json` mtime unchanged.
- **`ingest/pipeline.py` summary-page CJK discoverability** — emoji / CJK titles that yield a sentinel slug now fall back to `slugify(source_path.stem)` instead of accepting `untitled-<hash>.md` as the summary filename. Regression test: title `"😀😀😀"` on `readable-stem.md` produces summary `readable-stem.md`.

5 items deferred from review (tracked):

- `utils/io.py` `acquired = True` timing comment misleading (behavior correct, comment-only).
- `utils/llm.py` `last_error = e` on non-retryable branch dead code (harmless consistency tweak, kept).
- `review/refiner.py` page-file RMW race (no lock on wiki page file itself; only history JSON locked) — pre-existing, out of scope for item 13 — next HIGH cycle.
- `ingest/pipeline.py` `_is_duplicate_content` manifest race in single-process MCP — matches C8 TODO comment — Phase 4.5 HIGH cycle.
- `test_compile_loop_does_not_double_write_manifest` monkeypatch-at-module-level is brittle if `save_manifest` is ever moved — noted.

#### Notes

- **Deferred to follow-up docs-sync PR:** items 4 (version-string drift across `pyproject.toml` / `__init__.py` / README badge) and 5 (CLAUDE.md stats drift + `scripts/verify_docs.py` pre-commit check). Second-gate Opus review moved these out of this cycle as preventive-infrastructure drive-by.
- **Deferred to Phase 4.5 HIGH cycle:** `_is_duplicate_content` manifest RMW race (TODO planted in `ingest/pipeline.py`), `file_lock` stale-steal-loop Windows infinite-spin edge case, `refine_page` page-file RMW race.
- **Automated pipeline gates exercised:** Opus scope decomposition gate, adversarial Theme 5 deferral gate, Step 1.6 design gate (11 decisions, 2 overrides), Step 2.5 plan gate (7 amendments applied), security review (4-item checklist, 8/8 PASS), branch-level Codex review (1 blocker fixed, 2 majors triaged), **post-PR 2-round adversarial review (1 Opus + 1 Sonnet, replacing rate-limited Codex — 1 blocker fixed, 3 majors fixed, 5 deferred)**.
- **Decision trails:** `docs/superpowers/decisions/2026-04-15-backlog-phase4.5-critical-scope.md`, `2026-04-15-phase4.5-critical-design.md`, `2026-04-15-phase4.5-critical-plan.md`.
- **Test count movement:** 1530 (baseline) → 1546 (after 16 CRITICAL regression tests) → 1551 (after 5 post-PR review regression tests). 1 skipped throughout.

### Phase 5.0 — kb_lint --augment reactive gap-fill (2026-04-15)

Implements Karpathy Tier 1 #2 from BACKLOG.md: *"impute missing data (with web searchers)"*. When lint flags a stub page, the augment orchestrator proposes authoritative URLs (Wikipedia, arxiv), fetches them with a DNS-rebind-safe transport, pre-extracts at scan tier, and ingests as `confidence: speculative` — with a three-gate execution model that preserves the "human curates sources" contract.

#### Added

- **`kb lint --augment`** — reactive gap-fill via in-process HTTP fetch. Three execution gates (`propose` default → `--execute` → `--auto-ingest`) honor the "human curates sources" contract. New modules:
  - `src/kb/lint/fetcher.py` — DNS-rebind-safe transport via custom `httpcore.NetworkBackend`, scheme / domain / content-type allowlists, 5 MB stream cap, secret scan, trafilatura extraction, robots.txt via `SafeTransport`, `httpx.TooManyRedirects` handling.
  - `src/kb/lint/augment.py` — orchestrator with eligibility gates G1-G7 (placeholder titles, inbound links from non-summary pages, non-speculative confidence, per-page `augment: false` opt-out, autogen-prefix skip, 24 h cooldown, autogen prefix), LLM URL proposer with `abstain` action + allowlist filter, Wikipedia fallback for entity/concept stubs, scan-tier relevance gate (≥0.5), post-ingest quality verdict + `[!gap]` callout on regression.
  - `src/kb/lint/_augment_manifest.py` — atomic JSON state machine for run progression (propose → fetched → extracted → ingested → verdict → done).
  - `src/kb/lint/_augment_rate.py` — file-locked sliding-window rate limiter: 10/run + 60/hour + 3/host/hour. Cross-process safe via `kb.utils.io.file_lock`.
  - Augmented raw files carry `augment: true` + `augment_for: <stub_id>` + `augment_run_id` frontmatter. Resulting wiki pages get `confidence: speculative` + `[!augmented]` callout. On quality regression the page also gets a `[!gap]` callout flagging it for manual review.
  - CLI: `kb lint --augment [--execute] [--auto-ingest] [--dry-run] [--max-gaps N] [--wiki-dir PATH]`. Flag dependency validation: `--execute` requires `--augment`; `--auto-ingest` requires `--execute`; `--max-gaps` bounded by `AUGMENT_FETCH_MAX_CALLS_PER_RUN=10`.
  - MCP: `kb_lint(fix=False, augment=False, dry_run=False, execute=False, auto_ingest=False, max_gaps=5, wiki_dir=None)`. Preserves existing zero-arg behavior — all new kwargs default safe.
  - Spec: `docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md`. Plan: `docs/superpowers/plans/2026-04-15-kb-lint-augment.md`.
- `tests/test_v5_lint_augment_fetcher.py` — DNS rebind + scheme allowlist + content-type reject + 5 MB streaming cap + robots.txt + redirect-loop handling
- `tests/test_v5_lint_augment_manifest.py` — atomic state progression + terminal `done` + resume-from-partial
- `tests/test_v5_lint_augment_rate.py` — per-run / per-hour / per-host caps + sliding-window + lock safety
- `tests/test_v5_lint_augment_orchestrator.py` — eligibility gates G1-G7 + proposer abstain + Wikipedia fallback + relevance gate + propose / execute / auto-ingest modes + post-ingest quality verdict
- `tests/test_v5_kb_lint_signature.py` — MCP tool accepts all new kwargs + default-call unchanged + `--augment` appends `## Augment Summary` section
- `tests/test_v5_lint_augment_cli.py` — `--augment` / `--dry-run` + max-gaps validation + `--execute` requires `--augment` + `--auto-ingest` requires `--execute`
- `tests/test_v5_augment_config.py` — config constants sanity checks
- `tests/test_v5_autogen_prefixes.py` — `AUTOGEN_PREFIXES` consolidation regression guard
- `tests/test_v5_verdict_augment_type.py` — `VALID_VERDICT_TYPES` now includes `"augment"`

#### Fixed

- **`kb_lint` MCP signature drift** (CLAUDE.md:245) — tool now accepts `fix`, `augment`, `dry_run`, `execute`, `auto_ingest`, `max_gaps`, `wiki_dir` kwargs. Previously the MCP tool was zero-arg (`def kb_lint() -> str:`) while CLAUDE.md claimed `--fix` support. Agents following the docstring would hit FastMCP's unknown-kwarg error or silently get no fix behavior. The new signature routes `fix` through to `run_all_checks(fix=fix)` and gates `augment=True` through to `kb.lint.augment.run_augment(...)`.
- **`kb_lint` MCP `wiki_dir` plumbing** — tool can now be called with `wiki_dir=...` for hermetic test isolation. Previously the MCP tool read the `WIKI_DIR` global only, so tests had to either skip or mutate `kb.config` globally. Note: `kb_detect_drift`, `kb_evolve`, `kb_stats`, `kb_graph_viz`, `kb_compile_scan`, `kb_verdict_trends` still need the same plumbing (tracked in BACKLOG.md).
- **`_AUTOGEN_PREFIXES` consolidation** — `kb.config.AUTOGEN_PREFIXES = ("summaries/", "comparisons/", "synthesis/")` centralizes the autogen-page-type list. `check_stub_pages` now skips `comparisons/` and `synthesis/` consistently with `check_orphan_pages` (was summaries-only at `checks.py:446`). A fresh two-entity comparison page is no longer flagged as "stub — consider enriching" when its purpose is to be concise.
- **`_CAPTURE_SECRET_PATTERNS` extended** — PostgreSQL DSN passwords (`postgresql://user:pass@host`) and npm registry `_authToken` patterns now caught by the secret scanner in `kb_capture` before any LLM call.

### Phase 4.11 — kb_query output adapters (2026-04-14)

Implements Karpathy Tier 1 #1 from BACKLOG.md: *"render markdown files, slide shows (Marp format), matplotlib images"*. Synthesized query answers can now leave the session as a slide deck, a web page, a plot script, or an executable notebook.

- `src/kb/query/formats/` — new package with 5 output adapters dispatched via `render_output(fmt, result)`: markdown (YAML frontmatter + citations), marp (`marp: true` deck with code-fence-aware slide splitter that never shatters fenced code blocks), html (self-contained HTML5 with inline CSS + per-field `html.escape(quote=True)`), chart (static matplotlib Python script + JSON data sidecar — zero runtime matplotlib dep, no in-process image generation), jupyter (nbformat v4 with explicit Python 3 kernelspec; `metadata.trusted` never set to avoid auto-exec).
- `src/kb/query/formats/common.py` — shared helpers: `safe_slug` (empty-fallback `untitled`, Windows-reserved-name disambig, 80-char cap), `output_path_for` (microsecond timestamp + collision retry `-2..-9`), `build_provenance` (dynamic `kb_version` from `kb.__version__`), `validate_payload_size` (pre-render `MAX_OUTPUT_CHARS=500_000` guard).
- `src/kb/query/citations.py` `format_citations(citations, mode="markdown")` — new `mode` kwarg; adds `"html"` (`<ul>` with `<a>` anchors + html.escape) and `"marp"` modes. Default preserves all existing call sites.
- `src/kb/query/engine.py` `query_wiki(..., *, output_format=None)` — new keyword-only parameter (zero breakage to existing callers). When set and non-text, dispatches to `render_output` and adds `output_path` + `output_format` keys to the return dict. `output_error` on failure (answer still usable).
- `src/kb/cli.py` `kb query --format {text|markdown|marp|html|chart|jupyter}` — Click Choice flag; echoes `Output: <path> (<format>)` on non-text.
- `src/kb/mcp/core.py` `kb_query(..., output_format="")` — new MCP parameter. Validated via `VALID_FORMATS` enum with `.lower().strip()` normalization at the tool boundary. **Requires `use_api=true`** — Claude-Code-mode returns raw context, not a synthesized answer; adapters have nothing to render.
- `src/kb/config.py` — new constants `OUTPUTS_DIR = PROJECT_ROOT / "outputs"` (OUTSIDE `wiki/` to prevent search-index poisoning) and `MAX_OUTPUT_CHARS = 500_000`.
- `.gitignore` — `outputs/` added.
- `requirements.txt` — `nbformat>=5.0,<6.0` added.

**Security gates (all covered by tests in `tests/test_v4_11_security.py`):**
- No caller-supplied `output_path` override day-one — removes path-traversal attack surface entirely.
- `outputs/` lives outside `wiki/`; `load_all_pages` never surfaces output files.
- HTML adapter escapes every interpolated field individually (question, answer, page titles, citation paths, context); citation anchors built from structured list — never regex over already-escaped text.
- Chart adapter is a static Python script template; question + page IDs serialized via `json.dumps()` into sidecar JSON — zero user-data interpolation into the script source. Matplotlib only mentioned in the emitted script, never imported by kb.
- Jupyter adapter never sets `metadata.trusted` — notebooks do NOT auto-execute on open. Question in code cell serialized via `json.dumps()`.
- Marp slide splitter is a fence-aware state machine — triple-backtick regions stay intact.
- `MAX_OUTPUT_CHARS=500_000` enforced on raw answer pre-render.
- Slug: empty question → `untitled`; Windows reserved filenames (`CON`/`PRN`/`NUL`/`COM[1-9]`/`LPT[1-9]`) disambiguated with `_0` suffix.
- OSError messages from output writes no longer surface absolute tempfile paths to MCP callers.

Test deltas: +112 tests across 8 new `tests/test_v4_11_*.py` files (total 1434 passing, up from 1322 baseline).

### Phase 4.1 — easy backlog sweep (2026-04-14)
- `src/kb/capture.py` `_check_rate_limit` — `retry_after = max(1, ...)` so frozen-clock test fixtures can't yield ≤0 retry hints
- `src/kb/capture.py` `_validate_input` — ASCII fast-path skips full UTF-8 encode() for the common case
- `src/kb/capture.py` `_CAPTURE_SECRET_PATTERNS` — GCP OAuth `ya29.` pattern tightened to require 20+ char suffix (prevents false positives like `ya29.Overview`)
- `src/kb/capture.py` `_normalize_for_scan` — removed dead `except (ValueError, UnicodeDecodeError)` around `urllib.parse.unquote()` (unreachable — unquote uses `errors='replace'`)
- `src/kb/capture.py` `_path_within_captures` — now also catches `OSError` (ELOOP/EACCES on resolve) instead of propagating as unhandled 500
- `src/kb/capture.py` `_write_item_files` — early return on empty items skips mkdir + scandir
- `src/kb/capture.py` `_build_slug` — added explanatory comment on the collision loop bound
- `src/kb/capture.py` `_write_item_files` — added O(N²) comment on the `alongside_for` computation
- `src/kb/capture.py` module-level symlink guard — `.resolve()` calls wrapped in try/except `OSError` → `RuntimeError` for clear mount-failure diagnostics
- `src/kb/utils/text.py` `yaml_sanitize` — hoisted `_CTRL_CHAR_RE` to module scope (no recompile per call)
- `src/kb/graph/builder.py` `page_id` — uses `Path.as_posix()` instead of `str().replace("\\", "/")` for canonical cross-platform serialization
- `src/kb/lint/checks.py` `_INDEX_FILES` — dropped `"_categories.md"` (file never written; dead lookup removed)
- `src/kb/utils/hashing.py` `content_hash` — docstring now documents 128-bit prefix + collision bound + non-security use
- `src/kb/query/bm25.py` `tokenize` — docstring now mentions `STOPWORDS` filter so readers understand why `"what is rag"` → `["rag"]`
- `src/kb/evolve/analyzer.py` `suggest_new_pages` — skips empty wikilink targets (prevents ghost "Create  — referenced by …" suggestions from `[[   ]]` artifacts)

### Added
- **`kb_capture` MCP tool** — atomize up to 50KB of unstructured text (chat logs, scratch notes, LLM session transcripts) into discrete `raw/captures/<slug>.md` files via scan-tier LLM. Each item gets typed `kind` (decision / discovery / correction / gotcha), verbatim body, and structured frontmatter (title, confidence, captured_at, captured_from, captured_alongside, source). Returns file paths for subsequent `kb_ingest`. New `kb.capture` module + `templates/capture.yaml` + 5 new MCP wrapper tests + ~130 library tests.
- **Secret scanner with reject-at-boundary** — `kb_capture` content scanned for AWS / OpenAI / Anthropic / GitHub / Slack / GCP / Stripe / HuggingFace / Twilio / npm / JWT / DB connection strings / private key blocks BEFORE any LLM call; matches reject the entire batch with precise pattern label and line number. Encoded-secret normalization pass catches base64-wrapped and URL-encoded patterns (3+ adjacent triplets).
- **Per-process rate limit** — `kb_capture` enforces a 60-call-per-hour sliding-window cap under `threading.Lock` for FastMCP concurrent-request safety. Configurable via `CAPTURE_MAX_CALLS_PER_HOUR`.
- **`templates/capture.yaml`** — new ingest template for `raw/captures/*.md` with field names matching existing pipeline (`core_argument`, `key_claims`, `entities_mentioned`, `concepts_mentioned`).
- **`yaml_escape` strips Unicode bidi override marks** (`\u202a-\u202e`, `\u2066-\u2069`) — defends LLM-supplied frontmatter values against audit-log confusion attacks where U+202E renders text backward in terminals.
- **`pipeline.py` strips frontmatter for capture sources** — when `kb_ingest` processes a `raw/captures/*.md` file, leading YAML frontmatter is stripped before write-tier extraction. Gated on `source_type == "capture"` so other sources (Obsidian Web Clipper, arxiv) preserve their frontmatter for the LLM.
- `research/gbrain-analysis.md` — deep analysis of garrytan/gbrain patterns applicable to llm-wiki-flywheel roadmap
- `src/kb/utils/hashing.py` `hash_bytes()` — hash already-loaded bytes without re-reading the file; fixes TOCTOU inconsistency in ingest pipeline
- `src/kb/utils/io.py` `file_lock()` — cross-process exclusive lock via PID-stamped lock file with stale-lock detection; replaces `threading.Lock` in feedback store and verdicts
- `src/kb/config.py` `BM25_SEARCH_LIMIT_MULTIPLIER` — decouples BM25 candidate count from vector search multiplier in hybrid search
- `tests/test_phase4_audit_security.py` — 7 tests covering null-byte validation, content size bounds, and prompt injection
- `tests/test_phase4_audit_observability.py` — 4 tests covering retry logging, PageRank convergence warning, sqlite_vec load warning, and compile exception traceback
- `tests/test_phase4_audit_query.py` — 5 tests covering tier-1 budget enforcement, raw fallback truncation, and BM25 limit decoupling
- `tests/test_phase4_audit_compile.py` — 4 tests covering manifest pruning, source_id case normalisation, bare-slug resolution, and word normalisation
- `tests/test_phase4_audit_ingest.py` — 8 tests covering TOCTOU hash, sources-mapping merge, template key guards, and markdown stripping in contradiction detection
- `tests/test_phase4_audit_concurrency.py` — 4 tests covering cross-process file locking for feedback store and verdicts

### Changed
- `CLAUDE.md` Phase 4 roadmap expanded from 5 → 8 features: added hybrid search with RRF fusion (replaces LLM keyword expansion), 4-layer search dedup pipeline, evidence trail sections in wiki pages, stale truth flagging at query time — all inspired by garrytan/gbrain
- `CLAUDE.md` Phase 5 roadmap: removed BM25 + LLM reranking (subsumed by Phase 4 RRF), upgraded chunk-level indexing to use Savitzky-Golay semantic chunking, added cross-reference auto-linking during ingest
- `src/kb/feedback/store.py` `_feedback_lock` — switched from `threading.Lock` to `file_lock` for cross-process safety
- `src/kb/lint/verdicts.py` `add_verdict` — switched from `threading.Lock` to `file_lock` for cross-process safety

### Fixed

#### Security
- `src/kb/mcp/app.py` `_validate_page_id` — null bytes (`\x00`) now explicitly rejected before path resolution
- `src/kb/mcp/quality.py` `kb_refine_page` / `kb_create_page` — added `MAX_INGEST_CONTENT_CHARS` size bound on submitted content
- `src/kb/query/engine.py` `query_wiki` — synthesis prompt now uses `effective_question` (not raw `question`) with newlines collapsed to prevent prompt injection

#### Observability
- `src/kb/utils/llm.py` `_make_api_call` — final retry attempt now logs "giving up after N attempts" instead of the misleading "retrying in X.Xs"
- `src/kb/graph/builder.py` `graph_stats` — `PowerIterationFailedConvergence` now logs a warning with node count before returning empty results
- `src/kb/query/embeddings.py` `VectorIndex.query` — `sqlite_vec` extension load failure now logs a warning instead of silently returning empty results
- `src/kb/compile/compiler.py` `compile_wiki` — bare `except Exception` now calls `logger.exception()` to preserve full traceback in compile failure logs

#### Query correctness
- `src/kb/query/engine.py` `_build_query_context` — `CONTEXT_TIER1_BUDGET` now enforced; tier-1 loop tracks `tier1_used` separately to prevent summary pages consuming the entire context budget
- `src/kb/query/engine.py` `query_wiki` — raw-source fallback now truncates the first oversized section instead of producing no fallback context when the section exceeds remaining budget
- `src/kb/query/hybrid.py` `hybrid_search` — BM25 candidate count now uses `BM25_SEARCH_LIMIT_MULTIPLIER` (default 1×) instead of `VECTOR_SEARCH_LIMIT_MULTIPLIER` (2×), decoupling the two signals

#### Compile / graph
- `src/kb/compile/compiler.py` `compile_wiki` — manifest pruning now checks `Path.exists()` per key instead of comparing against `scan_raw_sources()` results; prevents phantom re-ingest when a source directory is temporarily unreadable
- `src/kb/compile/linker.py` `inject_wikilinks` — `source_id` now lowercased to match the lowercased `existing_ids` set; fixes silent lookup mismatches in broken-link reporting
- `src/kb/graph/builder.py` `build_graph` — bare-slug wikilinks (e.g., `[[rag]]`) now resolved by trying each wiki subdir prefix; fixes disconnected graph edges and corrupted PageRank scores
- `src/kb/evolve/analyzer.py` `find_connection_opportunities` — word normalisation now uses `re.sub(r"[^\w]", "", w)` to strip all non-word chars including `*`, `#`, `>`, `` ` ``, eliminating spurious shared-term matches from Markdown formatting tokens

#### Ingest data integrity
- `src/kb/ingest/pipeline.py` `ingest_source` — `source_hash` now derived from already-read `raw_bytes` via `hash_bytes()` instead of re-opening the file; eliminates TOCTOU inconsistency between content and hash
- `src/kb/ingest/pipeline.py` `_update_sources_mapping` — re-ingest now merges new page IDs into the existing `_sources.md` entry instead of returning early; previously new pages from re-ingest were silently dropped from the source mapping
- `src/kb/ingest/extractors.py` `build_extraction_prompt` — `template["name"]` and `template["description"]` replaced with `.get()` calls with fallbacks; prevents bare `KeyError` from user-authored templates missing optional keys
- `src/kb/ingest/contradiction.py` `detect_contradictions` — markdown structure (wikilinks, section headers) now stripped before tokenisation; prevents Evidence Trail boilerplate from inflating false overlap matches

#### Concurrency
- `src/kb/utils/io.py` `file_lock` — Windows `PermissionError` from `os.open(O_CREAT|O_EXCL)` now handled identically to `FileExistsError`; fixes concurrent thread contention on Windows

- **Phase 4 MEDIUM audit (~30 items)**: `load_all_pages` datetime→date normalisation; slugify version-number collision fix; `fd_transferred` flag prevents double-close in atomic writes; `extract_wikilinks` filters embedded newlines; `wiki_log` sanitises tabs; `FRONTMATTER_RE` consolidated to `kb.utils.markdown`; `STOPWORDS` consolidated to `kb.utils.text`; `VALID_VERDICT_TYPES` consolidated to `kb.lint.verdicts`; graph `out_degrees` precomputed dict (O(n) vs per-node `graph.degree`); graph export deterministic edge ordering; query citation path traversal guard; `_build_query_context` skipped-count fix; query engine removes inner config import; `_should_rewrite` checks deictic words before word count; rewriter length explosion guard; `VectorIndex` cached per-path via `get_vector_index()`; compiler `content_hash` isolated try/except; compiler `save_manifest` guarded; compiler skips `~`/`.` template stems; evolve `MAX_CONNECTION_PAIRS` cap; evolve `generate_evolution_report` single page-load; ingest contradiction appends to `WIKI_CONTRADICTIONS`; ingest `_build_summary_content` only on new pages; ingest references whitespace-line regex; ingest `_update_existing_page` early-return on missing frontmatter; ingest `_process_item_batch` raises on unknown type; ingest O(n) slug-lookup dicts; lint `check_orphan_pages` scans index/sources/categories/log; lint `check_source_coverage` uses rglob; lint `_group_by_term_overlap` bails at 500 pages; lint `_render_sources` budget fix; lint `_parse_timestamp` accepts date-only strings; MCP question/context length cap; MCP `kb_ingest` normcase path check; MCP atomic exclusive create; MCP `kb_list_pages` page_type validation; MCP `kb_graph_viz` treats max_nodes=0 as default; MCP `kb_detect_drift` None-safe join; MCP lint-verdict issues cap; MCP `kb_query_feedback` question length cap; MCP `kb_lint_consistency` page-ID cap.
- **Phase 4 LOW audit (~30 items)**: Consolidated `FRONTMATTER_RE`, `STOPWORDS`, `VALID_VERDICT_TYPES` as single sources of truth; BM25 avgdl branch demoted to debug; `graph/__init__.__all__` pruned; hybrid BM25 asymmetry comment; dedup Jaccard strips markup; type-diversity docstring; rewriter deictic word pattern; evidence CRLF-safe regex + `format_evidence_entry` helper; contradiction truncation log; contradiction symmetric-negation docstring; feedback eviction-policy comment; refiner `re.DOTALL` confirmed; refiner `re.MULTILINE` anchor; CLI error truncation via `_truncate(str(e), limit=500)` on all 5 command handlers.

### Changed
- `kb.utils.markdown.FRONTMATTER_RE` exported as public constant; `kb.graph.builder` and `kb.compile.linker` import it from there.
- `kb.utils.text.STOPWORDS` is the single source of truth; `kb.query.bm25` and `kb.ingest.contradiction` import from there.
- `kb.lint.verdicts.VALID_VERDICT_TYPES` is the single source of truth for verdict type names.
- `kb.query.embeddings.get_vector_index(path)` provides a singleton cache for `VectorIndex` instances.
- `kb.config` gains `WIKI_CONTRADICTIONS` path constant and `MAX_QUESTION_LEN = 2000`; removes unused `EMBEDDING_DIM`.

### Stats
- 1309 tests, 26 MCP tools, 19 modules

---

## [0.10.0] — 2026-04-12

Phase 4 — 8 features: hybrid search, dedup pipeline, evidence trails, stale flagging, layered context, raw fallback, contradiction detection, query rewriting.

### Added
- `src/kb/query/hybrid.py` — hybrid search: Reciprocal Rank Fusion of BM25 + vector results; `rrf_fusion()` and `hybrid_search()` with optional multi-query expansion
- `src/kb/query/dedup.py` — 4-layer search dedup pipeline: by source (highest score per page), text similarity (Jaccard >0.85), type diversity (60% cap), per-page cap (max 2)
- `src/kb/query/embeddings.py` — model2vec embedding wrapper (potion-base-8M, 256-dim, local) + sqlite-vec vector index (`VectorIndex` class)
- `src/kb/query/rewriter.py` — multi-turn query rewriting: scan-tier LLM expands pronouns/references in follow-up questions; heuristic skip for standalone queries
- `src/kb/ingest/evidence.py` — evidence trail sections: append-only `## Evidence Trail` provenance in wiki pages; `build_evidence_entry()` and `append_evidence_trail()`
- `src/kb/ingest/contradiction.py` — auto-contradiction detection on ingest: keyword overlap heuristic flags conflicts between new claims and existing wiki content
- `search_raw_sources()` in `kb.query.engine` — BM25 search over `raw/` source files for verbatim context fallback when wiki context is thin
- `_flag_stale_results()` in `kb.query.engine` — stale truth flagging at query time: compares page `updated` date vs source file mtime; adds `[STALE]` label in MCP output
- `_build_query_context()` refactored for tiered loading: summaries loaded first (20K chars), then full pages (60K chars), replacing naive 80K truncation
- `conversation_context` parameter on `query_wiki()` and `kb_query` MCP tool for multi-turn rewriting
- Evidence trail wired into ingest pipeline: `_write_wiki_page` and `_update_existing_page` automatically append provenance entries
- Auto-contradiction detection wired into `ingest_source()`: runs post-wikilink-injection, returns `contradictions` key in result dict
- `search_pages()` now uses `hybrid_search()` with RRF fusion + `dedup_results()` pipeline

### Changed
- `src/kb/config.py` — added 12 Phase 4 constants: `RRF_K`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `VECTOR_INDEX_PATH_SUFFIX`, dedup thresholds, context tier budgets, contradiction/rewriter limits

### Stats
- 1079 tests, 25 MCP tools, 18 modules

---

## [0.9.16] — 2026-04-12

Phase 3.97 — 62 fixes from 6-domain code review of v0.9.15.

### Fixed

#### CRITICAL
- Non-atomic writes in `fix_dead_links`, `kb_create_page`, `inject_wikilinks` replaced with `atomic_text_write`
- MCP exception guard on `kb_query` non-API path (search failures no longer crash sessions)
- `kb_save_lint_verdict` now catches `OSError` alongside `ValueError`
- Confirmed `refine_page` atomic write was already fixed in v0.9.15

#### HIGH
- `slugify` now maps C++→cpp, C#→csharp, .NET→dotnet to prevent cross-ingest entity merging
- `load_all_pages` coerces integer titles to strings (prevents `AttributeError` in BM25 search)
- `kb_query` API mode now forwards `max_results` parameter
- `kb_ingest_content`/`kb_save_source` raw file writes are now atomic
- `fix_dead_links` masks code blocks before modifying wikilinks
- `_is_valid_date` rejects empty strings and non-ISO date values
- `refine_page` catches `OSError`/`UnicodeDecodeError` on file read
- `load_review_history` catches `OSError`/`UnicodeDecodeError`, validates list shape
- `check_source_coverage` guards against `ValueError` from symlinks
- `load_feedback` validates `entries` is list and `page_scores` is dict (not null)
- `add_feedback_entry` initializes missing keys with defaults before arithmetic
- `kb_reliability_map` uses `.get()` for all score keys
- `kb_create_page` rejects nested page_id with more than one slash
- `kb_read_page` catches `UnicodeDecodeError`
- Feedback lock adds sleep after stale lock eviction

#### MEDIUM
- `atomic_text_write`/`atomic_json_write` write LF line endings on Windows (fixes cross-platform hash mismatches)
- `yaml_escape` strips Unicode NEL (`\x85`)
- `_update_index_batch` uses wikilink-boundary match instead of substring
- Title sanitization in `_update_index_batch`, `inject_wikilinks`, `_build_item_content`, `_build_summary_content`
- `build_extraction_schema` rejects `extract: None` templates
- `VALID_SOURCE_TYPES` includes comparison/synthesis
- `SUPPORTED_SOURCE_EXTENSIONS` shared constant replaces duplicate extension lists
- Binary PDF files get clear error instead of silent `UnicodeDecodeError`
- `detect_source_type` accepts custom `raw_dir` parameter
- PageRank returns empty for edge-free graphs instead of uniform 1.0
- `_compute_pagerank_scores` catches `OSError`
- `export_mermaid` uses `graph.subgraph()` for efficient edge iteration
- `_sanitize_label` falls back to slug on empty result
- `extract_citations` overrides type based on path prefix (raw/ paths → "raw")
- Citation regex hoisted to module level
- `compile` CLI exits code 1 on errors
- Verdict trends checks explicit verdict values, not dict membership
- `build_consistency_context` shows missing pages, filters single-page chunks
- Evolve frontmatter strip regex handles CRLF
- `generate_evolution_report` catches all exceptions in stub check
- `kb_create_page` requires source_refs to start with "raw/"
- `kb_query` coerces `None` trust to 0.5
- `kb_query_feedback` sanitizes question/notes control chars
- `_validate_page_id` rejects empty strings
- Various control character sanitization in MCP tools

#### LOW
- `WIKILINK_PATTERN` excludes `![[embed]]` syntax
- `_RAW_REF_PATTERN` case-insensitive, excludes hyphen before `raw/`
- `normalize_sources` filters empty strings and warns on non-string items
- `RawSource.content_hash` default standardized to `None`
- `RESEARCH_DIR` annotated as reserved
- Config constants for `UNDER_COVERED_TYPE_THRESHOLD`, `STUB_MIN_CONTENT_CHARS`
- `kb_list_sources` excludes `.gitkeep` files
- `kb_save_lint_verdict` uses `MAX_NOTES_LEN` constant
- Template cache clear helper added
- `ingest_source` uses `content_hash()` utility
- CLI source type list derived from `SOURCE_TYPE_DIRS`
- `graph_stats` narrows betweenness_centrality exception, adds `ValueError` to PageRank
- BM25 tokenize regex dead branch removed
- `query_wiki` docstring documents citation dict structure
- `get_coverage_gaps` deduplicates repeated questions

### Stats
1033 tests, 25 MCP tools, 12 modules.

---

## [0.9.15] — 2026-04-11

### Fixed
- **CRITICAL**: Non-atomic wiki page writes — crash mid-write could leave truncated files (ingest/pipeline, compile/linker, review/refiner)
- **CRITICAL**: TOCTOU race in `_update_existing_page` — double file read replaced with in-memory parse
- **CRITICAL**: Frontmatter guard regex allowed empty `---\n---` blocks through, causing double-frontmatter corruption
- **CRITICAL**: `kb_query` MCP tool missing empty-question guard
- `yaml_escape` now strips ASCII control characters (0x01-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F) that cause PyYAML ScannerError
- `normalize_sources` returns empty list for dict/int/float types instead of silently returning dict keys or raising TypeError
- `WIKILINK_PATTERN` rejects triple brackets `[[[...]]]` and caps match length at 200 chars
- `wiki_log` sanitizes newline/carriage return characters in operation and message fields
- `_page_id` in `utils/pages.py` now lowercases, consistent with `graph/builder.py`
- `WIKI_SUBDIRS` derived from `config.WIKI_SUBDIR_TO_TYPE` instead of hardcoded in 3 modules
- `load_all_pages` converts `null` dates to empty string instead of literal `"None"`
- `content_hash` uses streaming reads instead of loading entire file into memory
- `atomic_json_write` rejects `NaN`/`Infinity` values (`allow_nan=False`)
- `compile_wiki` forwards `wiki_dir` parameter to `ingest_source`
- Manifest double-write race fixed — compile loop reloads manifest after each ingest
- Partial ingest failure records hash with `failed:` prefix to prevent infinite retry
- `inject_wikilinks` guards against empty titles, fixes closure bug, skips blocked matches correctly
- Source ref injection targets `source:` block specifically, not any YAML list item
- Context block dedup checks for `## Context` header, not full block substring
- `extract_citations` dead code removed, `./` path traversal blocked
- Graph builder: self-loop guard, deterministic betweenness centrality (seed=0), frontmatter stripped before wikilink extraction
- Backlinks dedup changed from O(n²) list scan to O(1) set operations
- Code masking extended to markdown links/images, UUID-prefix placeholders prevent collision
- Lint: `fix_dead_links` count corrected, `resolve_wikilinks` deduped, threading locks added for verdicts/history
- Star-topology grouping uses `nx.connected_components` for complete coverage
- `check_staleness` handles unexpected `updated` types (int, etc.)
- Consistency groups auto-capped at `MAX_CONSISTENCY_GROUP_SIZE`
- Stale lock recovery retries acquisition instead of falling through unprotected
- Feedback lock creates `.data/` directory if missing
- Cross-link opportunity ranking uses uncapped term count
- MCP: path boundary tightened to `RAW_DIR`, filename/content length caps, page_id validation for cited_pages
- Review checklist verdict vocabulary aligned with `add_verdict()` accepted values
- CLI shows duplicate detection, removes invalid `comparison`/`synthesis` from source type choices
- `query_wiki` API documentation corrected in CLAUDE.md

### Changed
- `validate_frontmatter` checks date field types and source list item types
- `conftest.py` `create_wiki_page` fixture supports separate `created` parameter
- `extract_raw_refs` uses word-boundary anchor to avoid URL false positives
- `detect_source_type` gives clear error message for `raw/assets/` files
- Bare `except Exception` narrowed to specific exception tuples in lint/semantic modules

### Stats
952 tests, 25 MCP tools, 12 modules.

---

## [0.9.14] — 2026-04-09 (Phase 3.95)

38-item backlog fix pass across 13 source files. No new modules. All fixes have tests in `tests/test_v0914_phase395.py`.

### Fixed
- `utils/io.py` `atomic_json_write` — close fd on serialization failure (fd leak)
- `utils/paths.py` `make_source_ref` — always use literal `"raw/"` prefix instead of resolved dir name
- `utils/llm.py` `_make_api_call` — skip sleep after final failed retry
- `utils/text.py` `slugify` — add `re.ASCII` flag to strip non-ASCII chars
- `utils/wiki_log.py` `append_wiki_log` — wrap write+stat in `try/except OSError`, log warning instead of raising
- `models/frontmatter.py` `validate_frontmatter` — flag `source: null` and non-list/str source fields
- `models/page.py` `WikiPage` — `content_hash` defaults to `None` instead of `""`
- `query/engine.py` `search_pages` — no mutation of input page dicts (use spread-copy for score)
- `query/engine.py` `_build_query_context` — returns dict with `context` and `context_pages` keys; small-max_chars guard
- `query/engine.py` `query_wiki` — includes `context_pages` in return dict; fixed missing key in no-match early return
- `query/bm25.py` `tokenize` — documented version-string fragmentation behavior
- `ingest/pipeline.py` `_update_existing_page` — CRLF-safe frontmatter regex (`\r?\n`)
- `ingest/pipeline.py` `_build_summary_content` — handle dict authors via `a.get("name")`, drop non-str/non-dict with warning
- `ingest/pipeline.py` `ingest_source` — thread `wiki_dir` through all helpers; `_update_index_batch` and `_update_sources_mapping` use `atomic_text_write`
- `utils/io.py` — add `atomic_text_write` helper (temp file + rename for text files)
- `ingest/extractors.py` `_parse_field_spec` — warn on non-identifier field names
- `compile/compiler.py` `compile_wiki` — reload manifest after `find_changed_sources` to preserve template hashes
- `compile/linker.py` `inject_wikilinks` — mask code blocks before wikilink injection; unmask before write
- `lint/checks.py` `check_staleness` — flag pages with `None`/missing `updated` date
- `lint/runner.py` `run_all_checks` — use `f.get("source", f.get("page"))` for dead-link key consistency
- `lint/checks.py` `check_source_coverage` — use `make_source_ref` instead of hardcoded `raw/` prefix
- `lint/checks.py` `check_stub_pages` — narrow `except Exception` to specific exception types
- `lint/semantic.py` `_group_by_wikilinks` — `seen.update(group)` so all group members marked seen (prevents overlapping groups)
- `lint/semantic.py` `_group_by_term_overlap` — strip-before-filter using walrus operator
- `lint/trends.py` `compute_verdict_trends` — require minimum 3 verdicts in latest period for trend classification
- `lint/verdicts.py` `add_verdict` — truncate long notes instead of raising `ValueError`
- `graph/builder.py` `page_id` — normalize node IDs to lowercase
- `evolve/analyzer.py` `find_connection_opportunities` — strip-before-filter using walrus operator
- `evolve/analyzer.py` `generate_evolution_report` — narrow `except Exception` to specific types
- `mcp/core.py` `kb_ingest_content` — return error instead of overwriting existing source file
- `mcp/core.py` `kb_ingest` — truncate oversized content before building extraction prompt
- `feedback/store.py` `add_feedback_entry` — UNC path guard via `os.path.isabs`; file locking via `_feedback_lock`
- `feedback/store.py` — move constants to `config.py`
- `config.py` — add feedback store constants (`MAX_QUESTION_LEN`, `MAX_NOTES_LEN`, `MAX_PAGE_ID_LEN`, `MAX_CITED_PAGES`)
- `review/refiner.py` `refine_page` — write page file before appending history; OSError returns error dict
- `mcp/quality.py` `kb_create_page` — derive `type_map` from config instead of hardcoding

### Stats
692 tests, 25 MCP tools, 12 modules.

---

## [0.9.13] — 2026-04-09 (Phase 3.94)

54-item backlog fix pass covering BM25, query engine, citations, lint, ingest, compile, MCP, graph, evolve, feedback, refiner, and utils. Ruff clean. Plus cross-cutting rename `raw_content` → `content_lower` in `load_all_pages` and all callers.

### Fixed
- `query/bm25.py` `BM25Index.score`: deduplicate query tokens via `dict.fromkeys()` — duplicate terms no longer inflate BM25 scores against standard behavior
- `query/engine.py` `search_pages`: remove dead stopword-fallback block (BM25 index has no stopword entries; fallback never matched); add `max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))` upper-bound clamp at library level
- `query/engine.py` `_build_query_context`: emit `logger.warning` when the top-ranked page (`i == 0`) is excluded because it exceeds `max_chars` — previously silently skipped with only a DEBUG log
- `query/citations.py` `extract_citations`: add pre-pass normalizing `[[path]]` → `path` inside `[source: ...]` brackets — wikilink-wrapped citation paths were silently dropped
- `lint/runner.py` `run_all_checks`: fix post-fix dead-link filter — field name mismatch `"source"` vs `"page"` meant the filter was a no-op; fixed links now correctly removed from the report; add `logger.warning` when `get_verdict_summary()` raises — previously silent
- `lint/checks.py` `check_staleness`: add `TypeError` to except clause and coerce `datetime.datetime` → `datetime.date` — pages with ISO-datetime `updated` fields aborted the entire staleness check
- `lint/checks.py` `check_orphan_pages` / `check_cycles`: accept optional pre-built graph parameter; `run_all_checks` builds graph once and passes it to both — eliminates double full-graph build per lint run
- `lint/verdicts.py` `add_verdict`: add path-traversal guard (reject `..` and leading `/`/`\`); cap `notes` at `MAX_NOTES_LEN` consistent with feedback store
- `ingest/pipeline.py` `_update_existing_page`: scope source-entry regex to frontmatter section only (split on closing `---`) — regex previously matched any indented quoted list item in the page body
- `ingest/pipeline.py` `_process_item_batch`: add `isinstance(item, str)` guard — non-string items (`None`, int, nested dict) now log a warning and skip instead of raising `AttributeError`
- `ingest/pipeline.py` `ingest_source`: add fallback slug `source_path.stem` when `slugify(title)` returns empty string — punctuation-only titles no longer create hidden dotfile pages
- `ingest/pipeline.py` `_update_sources_mapping`: change plain substring match to backtick-wrapped format check (`` f"`{source_ref}`" in content ``) — `raw/articles/a.md` no longer falsely matches `raw/articles/abc.md`
- `ingest/pipeline.py` `_build_summary_content`: filter `authors` list with `isinstance` guard before `join` — `None` elements no longer raise `TypeError`; same guard applied to `slugify()` calls over `entities_mentioned`/`concepts_mentioned`
- `ingest/pipeline.py` `_write_wiki_page`: rename local variable `frontmatter` → `fm_text` to stop shadowing the `import frontmatter` module
- `ingest/pipeline.py` `_extract_entity_context`: use `is not None` check for `key_claims` — an explicitly empty `[]` primary field no longer triggers the fallback to `key_points`
- `compile/linker.py` `inject_wikilinks`: lowercase `target_page_id` at function entry — self-skip check and injected wikilink now consistently lowercased; log warning when nested-wikilink guard fires and blocks injection
- `compile/linker.py` `resolve_wikilinks`: lowercase `existing_ids` — case-sensitive filesystems no longer produce false broken-link reports for mixed-case page IDs
- `compile/compiler.py` `compile_wiki`: capture `content_hash(source)` before calling `ingest_source` — externally modified files during ingest no longer cause manifest drift
- `compile/compiler.py` `compile_wiki`: reload manifest after `find_changed_sources` returns — template hashes are no longer overwritten by per-source `save_manifest` calls in the loop
- `compile/compiler.py` `scan_raw_sources`: emit `logger.warning` for subdirs under `raw/` not in `SOURCE_TYPE_DIRS` (excluding `assets`) — new source types added to config but not here are now visible
- `compile/compiler.py` `_canonical_rel_path`: add `logger.warning` when fallback (absolute path as manifest key) fires
- `mcp/core.py` `kb_ingest_content`: wrap `file_path.write_text()` and `ingest_source()` in `try/except`; on exception, delete the orphaned raw file before returning `"Error: ..."`
- `mcp/quality.py` `kb_create_page`: wrap `page_path.write_text()` and `append_wiki_log` in `try/except OSError` — unhandled OS errors no longer escape to MCP client
- `mcp/quality.py` `kb_query_feedback`: catch `OSError` after existing `ValueError` handler — disk-full/permissions errors now return `"Error: ..."` instead of propagating
- `mcp/quality.py` `kb_lint_consistency`: use `check_exists=True` when explicit page IDs are supplied — non-existent pages now return a clear error instead of silent empty output
- `mcp/health.py` `kb_graph_viz`: clamp `max_nodes = max(0, min(max_nodes, 500))` at tool boundary — unbounded values no longer risk memory exhaustion
- `mcp/health.py` `kb_lint` / `kb_evolve`: promote feedback-data load failure from `DEBUG` to `logger.warning` — corrupt feedback store is no longer invisible at default log level
- `mcp/app.py` `_format_ingest_result`: use `.get()` for `pages_created` and `pages_updated` — partial/error-state result dicts no longer raise `KeyError`
- `mcp/browse.py` `kb_list_sources`: wrap per-file `f.stat()` in `try/except OSError` — a broken symlink no longer aborts the entire directory listing
- `mcp/core.py` `kb_ingest`: add soft size warning when source exceeds `QUERY_CONTEXT_MAX_CHARS` — multi-megabyte sources now log a warning before extraction
- `utils/paths.py` `make_source_ref`: raise `ValueError` for paths outside `raw/` instead of returning a fabricated path — silent collision with legitimate `raw/` files prevented
- `utils/llm.py` `call_llm`: iterate `response.content` to find the first `type == "text"` block instead of assuming `[0]` is text — `thinking` blocks first no longer cause `AttributeError`
- `utils/llm.py` `_make_api_call`: fix retry log denominator from `MAX_RETRIES` to `MAX_RETRIES + 1` — no longer logs "attempt 4/3" on final attempt
- `utils/wiki_log.py` `append_wiki_log`: sanitize `|` chars in `operation` and `message` before writing — pipe characters no longer produce unparseable extra columns in the log
- `utils/pages.py` `normalize_sources`: filter non-string elements — malformed YAML `source:` fields with nested items no longer cause downstream `AttributeError`
- `utils/hashing.py` `content_hash`: fix docstring — "32-char hex digest" corrected to "first 32 hex chars (128-bit prefix of SHA-256)"
- `ingest/extractors.py`: add `_build_schema_cached(source_type: str)` LRU-cached wrapper around `load_template` + `build_extraction_schema` — schema is no longer rebuilt on every extraction call
- `graph/builder.py` `graph_stats`: wrap `betweenness_centrality` in `try/except Exception` with `logger.warning` — unexpected failures no longer propagate to caller
- `graph/builder.py` `graph_stats`: rename `"orphans"` key → `"no_inbound"` — aligns with lint module's definition (zero backlinks regardless of out-degree)
- `graph/export.py` `_sanitize_label`: strip `(` and `)` from Mermaid node labels — parentheses caused parse errors in some renderer versions
- `graph/export.py` `export_mermaid`: quote subgraph names (`subgraph "{page_type}"`) — future page types with spaces produce valid Mermaid syntax
- `evolve/analyzer.py` `generate_evolution_report`: promote `check_stub_pages` / `get_flagged_pages` exception logging from `DEBUG` to `logger.warning` — genuine bugs no longer silently omit report sections
- `evolve/analyzer.py` `find_connection_opportunities`: replace O(V×T) re-scan with `pair_shared_terms` accumulator in outer loop — eliminates redundant full `term_index` iteration per qualifying pair
- `feedback/store.py` `load_feedback`: validate JSON shape after load (`isinstance(data, dict)` + required keys check) — wrong-shaped files now return `_default_feedback()` instead of raising `KeyError`
- `review/refiner.py` `refine_page`: tighten `startswith("---")` guard to `startswith("---\n") or == "---"` — valid markdown opening with a horizontal rule (`---\n`) no longer falsely rejected
- `lint/semantic.py` `_group_by_wikilinks`: remove dead `existing_neighbors` filter — `build_graph` only creates edges to existing nodes; filter never removed anything
- `models/frontmatter.py` `load_page`: remove dead function with zero callsites — `lint/checks.py` uses `frontmatter.load()` directly

### Changed
- `utils/pages.py` `load_all_pages`: rename field `raw_content` → `content_lower` — name now accurately reflects that the field is pre-lowercased for BM25, not verbatim content; all callers updated (`query/`, `lint/`, `compile/`, `evolve/`)
- `mcp/browse.py`: simplified `except (OSError, PermissionError)` → `except OSError` in `kb_read_page` and `kb_list_sources` (`PermissionError` is a subclass of `OSError`)
- `compile/compiler.py` `load_manifest`: returns `{}` on `json.JSONDecodeError` or `UnicodeDecodeError` instead of propagating — corrupt `.data/hashes.json` no longer crashes compile, detect-drift, or find-changed-sources
- `ingest/pipeline.py` `_update_existing_page`: entity context insertion uses `re.search(r"^## References", …, re.MULTILINE)` and positional splice instead of `str.replace` — prevents double-injection when LLM-extracted context itself contains `## References`
- `lint/semantic.py` `build_fidelity_context` / `build_completeness_context`: source content now truncated at `QUERY_CONTEXT_MAX_CHARS` (80K) — large books and arXiv PDFs no longer overflow the LLM context window
- `lint/semantic.py` `_group_by_wikilinks`: changed `seen.update(group)` → `seen.add(node)` + added frozenset dedup pass — pages in link chains (A→B→C) were consumed by A's group and skipped; B and C now form their own consistency groups
- `mcp/core.py` `kb_query`: API branch wraps `query_wiki()` in `try/except` — `LLMError`/timeout no longer escapes raw to MCP client
- `mcp/core.py` `kb_ingest_content`: extraction JSON validated before writing the raw file — validation failure no longer leaves an orphaned file on disk
- `mcp/core.py` `kb_save_source`: added `overwrite` parameter (default `false`) with file-existence guard; `write_text` wrapped in `try/except OSError`
- `mcp/quality.py` `kb_refine_page` / `kb_affected_pages` / `kb_save_lint_verdict` / `kb_lint_consistency`: added `_validate_page_id()` guards
- `mcp/quality.py` `kb_create_page`: `source_refs` validated against path traversal before being written to frontmatter
- `review/context.py` `pair_page_with_sources`: added `page_path.resolve().relative_to(wiki_dir.resolve())` guard and `try/except (OSError, UnicodeDecodeError)` around source reads
- `review/refiner.py` `refine_page`: added path traversal guard; normalized CRLF→LF before frontmatter parsing (Windows fix); swapped write order so audit history is persisted before page file
- `utils/llm.py` `call_llm_json`: validates `block.name == tool_name` before returning — wrong-tool responses no longer silently corrupt callers
- `utils/llm.py`: retry loop fixed from `range(MAX_RETRIES)` to `range(MAX_RETRIES + 1)`; `last_error` initialized to avoid `AttributeError` when `MAX_RETRIES=0`
- `utils/wiki_log.py` `append_wiki_log`: replaced `exists()` + `write_text()` with `open("x")` + `FileExistsError` guard — concurrent MCP calls can no longer race on initial log creation
- `evolve/analyzer.py` `find_connection_opportunities`: strips YAML frontmatter before tokenizing — structural keys no longer produce false-positive link suggestions
- `feedback/store.py` `add_feedback_entry`: `page_scores` dict now capped at `MAX_FEEDBACK_ENTRIES` (10k) — previously only `entries` list was capped
- `graph/builder.py` `graph_stats`: `betweenness_centrality` uses `k=min(500, n_nodes)` sampling approximation for graphs > 500 nodes — prevents O(V·E) stall in `kb_evolve` on large wikis
- `utils/pages.py`: inlined `_page_id` helper to break circular import dependency on `kb.graph.builder`
- `evolve/analyzer.py`: bare `except Exception: pass` on feedback lookup narrowed to `logger.warning`
- `config.py`: env override model IDs accepted empty strings; `MAX_FEEDBACK_ENTRIES` and `MAX_VERDICTS` moved from module constants to `kb.config`
- `lint/checks.py`: `check_staleness` silently skipped quoted-string `updated` fields; orphan/isolated detection now exempts `comparisons/` and `synthesis/`; `check_source_coverage` suffix match tightened to avoid false positives on same-named files in different subdirs
- `lint/verdicts.py`: `load_verdicts` now warns on `JSONDecodeError` instead of silently discarding verdict history
- `graph/export.py`: `_sanitize_label` now strips newlines and backticks from Mermaid node labels
- `feedback/reliability.py`: docstring corrected from "below threshold" to "at or below threshold"
- `cli.py`: `mcp` command now has `try/except`; `--type` choices include `comparison` and `synthesis`
- `mcp/browse.py`: `kb_search` and `kb_list_pages` now have outer `try/except`
- `mcp/app.py`: `_format_ingest_result` dead legacy dict-branch for `affected_pages` removed

### Removed
- `scripts/hook_review.py`: deleted — standalone Anthropic-API commit-gate script removed; the `claude -p` skill gate in hooks covers this use case
- `docs/superpowers/specs/2026-04-06-phase2-multi-loop-quality-design.md`: deleted obsolete Phase 2 design spec (fully implemented as of v0.6.0)
- `docs/superpowers/plans/2026-04-06-phase2-multi-loop-quality.md`: deleted obsolete Phase 2 implementation plan (fully shipped)
- `docs/superpowers/plans/2026-04-07-v092-audit-fixes.md`: deleted obsolete v0.9.2 audit-fixes plan
- `docs/superpowers/plans/2026-04-07-v093-remaining-fixes.md`: deleted obsolete v0.9.3 remaining-fixes plan
- `docs/superpowers/plans/2026-04-08-phase393-backlog.md`: deleted — Phase 3.93 plan fully shipped
- `docs/superpowers/plans/2026-04-09-phase394-backlog.md`: deleted — Phase 3.94 plan fully shipped

### Stats
- 651 tests (+38), 25 MCP tools, 12 modules

---

## [0.9.11] — 2026-04-08 (Phase 3.92)

9-item backlog hardening. All Phase 3.92 known issues resolved. Ruff clean.

### Added
- `config.py`: `MAX_REVIEW_HISTORY_ENTRIES = 10_000` and `VERDICT_TREND_THRESHOLD = 0.1` constants

### Changed
- `compile/linker.py`: `inject_wikilinks` uses smart lookahead/lookbehind for titles starting/ending with non-word chars (`C++`, `.NET`, `GPT-4o`)
- `compile/compiler.py`: `compile_wiki` now propagates `pages_skipped`, `wikilinks_injected`, `affected_pages`, `duplicates` from ingest result; `kb_compile` MCP output shows these fields
- `lint/checks.py`: `check_staleness` narrows `except Exception` to specific types; `check_source_coverage` merged into single-pass loop (reads each file once via `frontmatter.loads()`)
- `lint/trends.py`: hardcoded `0.1` trend threshold replaced with `VERDICT_TREND_THRESHOLD` config constant
- `utils/wiki_log.py`: `stat()` result cached — called once instead of twice
- `README.md`, `others/architecture-diagram.html`: corrected "26 tools" to "25 tools"

### Fixed
- `review/refiner.py`: review history now capped at `MAX_REVIEW_HISTORY_ENTRIES` (same pattern as feedback/verdict stores)
- `mcp/browse.py`: `kb_read_page` and `kb_list_sources` wrap I/O in `try/except OSError` — raw exceptions no longer escape to MCP client
- `lint/checks.py`: `fix_dead_links` only appends audit trail entry when `re.sub` actually changed content (eliminates phantom entries)
- `evolve/analyzer.py`: added module-level logger; `find_connection_opportunities` and `suggest_new_pages` guard `read_text()` with `try/except (OSError, UnicodeDecodeError)`

### Stats
- 583 tests (+9), 25 MCP tools, 12 modules

---

## [0.9.10] — 2026-04-07 (Phase 3.91)

5-agent parallel code review fix list.

### Changed
- `ingest/pipeline.py`: `inject_wikilinks` frontmatter split uses regex (`_FRONTMATTER_RE`)
- `compile/linker.py`: `resolve_wikilinks`/`build_backlinks` wrap `read_text()` in `try/except (OSError, UnicodeDecodeError)`
- `ingest/extractors.py`: `KNOWN_LIST_FIELDS` extended with `key_arguments`, `quotes`, `themes`, `open_questions`
- `graph/export.py`: Mermaid `_safe_node_id` tracks seen IDs with suffix deduplication
- `lint/runner.py`: `run_all_checks` with `fix=True` removes fixed issues from report
- `mcp/core.py`: `kb_ingest` wrapped in `try/except`; `kb_create_page` uses `_validate_page_id(check_exists=False)`
- `mcp/core.py`: URL in `kb_ingest_content`/`kb_save_source` wrapped in `yaml_escape()`
- `config.py`: `VERDICTS_PATH` and LLM retry constants moved from inline definitions
- `evolve/analyzer.py`: `detect_source_drift` bare `except` narrowed
- `ingest/extractors.py`: `extract_raw_refs` extended to `.csv`/`.png`/`.jpg`/`.jpeg`/`.svg`/`.gif`

### Fixed
- `compile/compiler.py`: `save_manifest` now uses `atomic_json_write`

### Stats
- 574 tests, 25 MCP tools, 12 modules

---

## [0.9.9] — 2026-04-07 (Phase 3.9)

Infrastructure for content growth and AI leverage.

### Added
- `config.py`: environment-configurable model tiers (`CLAUDE_SCAN_MODEL`, `CLAUDE_WRITE_MODEL`, `CLAUDE_ORCHESTRATE_MODEL` env vars)
- `search.py`: PageRank-blended search ranking (`final_score = bm25 * (1 + PAGERANK_SEARCH_WEIGHT * pagerank)`)
- `ingest/pipeline.py`: hash-based duplicate detection (checks compile manifest for existing sources with identical content hash)
- `kb.lint.trends`: new module — `kb_verdict_trends` MCP tool (weekly pass/fail/warning rates, quality trend direction)
- `kb.graph.export`: new module — `kb_graph_viz` MCP tool (Mermaid flowchart with auto-pruning, subgraph grouping)
- `compile/linker.py`: `inject_wikilinks()` for retroactive inbound wikilink injection
- `ingest/pipeline.py`: content-length-aware tiering (`SMALL_SOURCE_THRESHOLD=1000`)
- `ingest/pipeline.py`: cascade update detection (`affected_pages` return key)

### Fixed
- (post-review round 1) `inject_wikilinks` integrated into `ingest_source()` with lazy import; `_format_ingest_result` shows duplicate detection
- (post-review round 2) `_update_existing_page` accepts `verb` parameter — concept pages write "Discussed in" correctly; `_process_item_batch` derives `subdir` from `_SUBDIR_MAP`
- (post-review round 3) `_format_ingest_result`: `affected_pages` flat list handling; `wikilinks_injected` key now read by formatter

### Stats
- 574 tests (+56), 25 MCP tools (+2), 12 modules (+2)

---

## [0.9.8] — 2026-04-06 (Phase 3.9a)

Deep audit fixes and structured outputs.

### Added
- `utils/llm.py`: `call_llm_json()` — structured output via Claude tool_use (forced tool choice guarantees valid JSON)
- `ingest/extractors.py`: `build_extraction_schema()` + `_parse_field_spec()` for template-to-JSON-Schema conversion
- `utils/llm.py`: `_make_api_call()` shared retry helper (extracted from `call_llm`, used by both text and JSON calls)
- `utils/io.py`: `atomic_json_write()` utility (consolidated 3 identical atomic write implementations)
- `utils/llm.py`: `_resolve_model()` helper (deduplicated tier validation)

### Changed
- `ingest/extractors.py`: `load_template()` is now LRU-cached; precompiled regex in `_parse_field_spec()`
- `utils/llm.py`: removed dead 429 from `APIStatusError` retry codes (handled by `RateLimitError` catch)

### Fixed
- `mcp/core.py`: `kb_ingest` path traversal protection (validates resolved path within `PROJECT_ROOT`)
- `feedback.py`: `cited_pages` deduplicated before trust scoring (prevents inflated trust)
- `review/refiner.py`: atomic writes for review history (tempfile+rename)

### Stats
- 518 tests (+29), 23 MCP tools, 10 modules

---

## [0.9.7] — 2026-04-06 (Phase 3.8)

Tier-3 fixes and observability.

### Changed
- `query.py`: search logs debug when falling back to raw terms (all stopwords filtered)
- `mcp/health.py`: `kb_affected_pages` uses `debug` instead of `warning` for expected shared-sources failure
- `utils/llm.py`: `LLMError` messages distinguish error types (timeout, rate limit, connection, server error with status code)

### Stats
- 490 tests (+7), 23 MCP tools, 10 modules

---

## [0.9.6] — 2026-04-06 (Phase 3.7)

Tier-2 audit hardening.

### Changed
- `query.py`: context skips whole pages instead of truncating mid-page (preserves markdown structure)
- `feedback.py` / `lint/verdicts.py`: atomic writes (temp file + rename)
- `ingest/pipeline.py`: entity/concept count limits (`MAX_ENTITIES_PER_INGEST=50`, `MAX_CONCEPTS_PER_INGEST=50`)

### Fixed
- `search.py`: empty query validation in `kb_search`
- `feedback.py`: citation path traversal validation (rejects `..` and leading `/`)
- `mcp/quality.py`: bare except logging in `kb_refine_page`
- `evolve/analyzer.py`: surfaces low-trust pages from feedback (`flagged_pages` in report)

### Stats
- 483 tests (+18), 23 MCP tools, 10 modules

---

## [0.9.5] — 2026-04-05 (Phase 3.6)

Tier-1 audit hardening.

### Changed
- `mcp_server.py`: MCP instructions string updated with 3 missing tools (`kb_compile`, `kb_detect_drift`, `kb_save_source`)
- `evolve/analyzer.py`: stub check logs on failure instead of silent `pass`
- `lint/checks.py`: `fix_dead_links()` writes audit trail to `wiki/log.md`

### Fixed
- `ingest/pipeline.py`: extraction data type validation (`isinstance` guard for `entities_mentioned`/`concepts_mentioned`)
- `graph/analysis.py`: `UnicodeDecodeError` handling in `build_graph()` (skips unreadable pages)
- `mcp/core.py`: empty title validation in `kb_create_page`

### Stats
- 465 tests (+13), 23 MCP tools, 10 modules

---

## [0.9.4] — 2026-04-05 (Phase 3.5)

Tier 1-3 improvements.

### Added
- `lint/checks.py`: `check_stub_pages()` — flags pages with <100 chars body, integrated into `run_all_checks()` and evolve
- `evolve/analyzer.py`: `detect_source_drift()` — finds wiki pages stale due to raw source changes
- `mcp/health.py`: `kb_detect_drift` MCP tool (23rd tool)

### Fixed
- `graph/analysis.py`: `build_backlinks()` now filters broken links (consistent with `build_graph()`)
- `evolve/analyzer.py`: `analyze_coverage()` uses `parent.name` instead of fragile string containment
- `ingest/pipeline.py`: redundant `.removesuffix(".md")` removed from evolve
- `ingest/extractors.py`: JSON fence stripping handles whitespace

### Stats
- 452 tests (+21), 23 MCP tools (+1), 10 modules

---

## [0.9.3] — 2026-04-05 (Phase 3.4)

Feature completion.

### Added
- `mcp/core.py`: `kb_compile` MCP tool (22nd tool, calls `compile_wiki()`)
- `lint/runner.py` / `cli.py`: `kb lint --fix` (auto-fixes dead links by replacing broken `[[wikilinks]]` with plain text)
- `config.py`: `MAX_SEARCH_RESULTS` constant (replaces hardcoded 100)

### Stats
- 431 tests (+17), 22 MCP tools (+1), 10 modules

---

## [0.9.2] — 2026-04-05 (Phase 3.3)

Audit fixes — 15 bug fixes across ingest, lint, query, and validation.

### Changed
- `ingest/pipeline.py`: replaced flawed regex in `_update_existing_page()` with `finditer` last-match approach; added logging to silent exception handler
- `lint/semantic.py`: removed domain terms from `common_words` stoplist; fixed consistency group truncation (chunks instead of silent discard)
- `query.py`: added context truncation logging; BM25 avgdl guard logging
- `mcp/browse.py`: case-insensitive page lookup validates resolved path stays in WIKI_DIR
- `mcp/health.py`: `logger.exception` replaced with `logger.error`

### Fixed
- `feedback.py`: length limits enforced (question/notes 2000 chars, page ID 200 chars, max 50 cited pages, path traversal rejection)
- `lint/verdicts.py`: severity validation (`error`/`warning`/`info`)
- `review/refiner.py`: rejects content starting with `---`
- `ingest/pipeline.py`: `pages_skipped` surfaced in CLI and MCP output

### Stats
- 413 tests (+31), 21 MCP tools, 10 modules

---

## [0.9.1] — 2026-04-04 (Phase 3.2)

Comprehensive audit and hardening.

### Added
- 93 new tests across 6 new test files: `test_llm.py`, `test_lint_verdicts.py`, `test_paths.py`, `test_mcp_browse_health.py`, `test_mcp_core.py`, `test_mcp_quality_new.py`

### Changed
- `utils/llm.py`: thread-safe LLM client singleton (double-check locking); `ValueError` on invalid tier
- `utils/wiki_log.py`: O(1) append (replaces O(n) read-modify-write)
- `mcp/`: consistent `_validate_page_id()` usage across all tools; confidence level validation in `kb_create_page`
- `utils/text.py`: `yaml_escape` handles `\r` and `\0`
- `feedback.py` / `lint/verdicts.py`: 10k entry retention limits

### Fixed
- `search.py`: BM25 division-by-zero fix (avgdl=0 guard)
- `ingest/pipeline.py`: source path traversal protection in `pair_page_with_sources()`
- `ingest/pipeline.py`: frontmatter-aware source collision detection in `_update_existing_page()`
- `lint/semantic.py`: duplicate "could" removed

### Stats
- 382 tests (+93), 21 MCP tools, 10 modules. MCP tool test coverage 41% to 95%.

---

## [0.9.0] — 2026-04-04 (Phase 3.1)

Hardening release.

### Changed
- `mcp/`: all tools wrap external calls in try/except; `max_results` bounds [1, 100] in `kb_query`/`kb_search`; MCP instructions updated with Phase 2 tools
- `utils/llm.py`: Anthropic SDK `max_retries=0` (double-retry fix)
- `compile/linker.py` / `graph/analysis.py`: redundant `.removesuffix(".md")` removed

### Fixed
- `mcp/`: `_validate_page_id()` rejects `..` and absolute paths, verifies resolved path within WIKI_DIR — applied to `kb_read_page`, `kb_create_page`
- `models.py`: citation regex fix (underscore support in page IDs)
- `ingest/pipeline.py`: slug collision tracking (`pages_skipped` in ingest result)
- `ingest/extractors.py`: JSON fence hardening (handles single-line `` ```json{...}``` ``)

### Stats
- 289 tests (+37), 21 MCP tools, 10 modules

---

## [0.8.0] — 2026-04-03 (Phase 3.0)

BM25 search engine.

### Added
- `search.py`: BM25 ranking algorithm replacing naive bag-of-words (term frequency saturation, inverse document frequency, document length normalization)
- `search.py`: custom tokenizer with stopword filtering and hyphen preservation
- `config.py`: configurable `BM25_K1`/`BM25_B` parameters; title boosting via `SEARCH_TITLE_WEIGHT` token repetition

### Stats
- 252 tests, 21 MCP tools, 10 modules

---

## [0.7.0] — 2026-04-02 (Phase 2.3)

S+++ upgrade.

### Added
- `kb.mcp` package: MCP server split into 5 modules from 810-line monolith (`app`, `core`, `browse`, `health`, `quality`)
- `graph/analysis.py`: PageRank and betweenness centrality
- `ingest/pipeline.py`: entity/concept enrichment on multi-source ingestion
- `lint/verdicts.py`: persistent lint verdict storage with audit trail
- `mcp/core.py`: `kb_create_page` and `kb_save_lint_verdict` tools
- `templates/`: comparison and synthesis extraction templates

### Changed
- `compile/linker.py`: case-insensitive wikilink resolution
- `feedback.py`: trust threshold boundary fix (`<` to `<=`)
- `compile/compiler.py`: template hash change detection triggers recompile

### Stats
- 234 tests, 21 MCP tools, 10 modules

---

## [0.6.0] — 2026-04-01 (Phase 2.2)

DRY refactor and code quality.

### Added
- `kb.utils.text`: shared `slugify()` (2x to 1x)
- `kb.utils.wiki_log`: shared log appending (4x to 1x)
- `kb.utils.pages`: shared `load_all_pages()` / `page_id` (3x to 1x)
- `ingest/pipeline.py`: source type whitelist validation; `normalize_sources()` for consistent list format

### Changed
- `mcp_server.py`: `_apply_extraction` (80 lines) replaced by `ingest_source(extraction=...)`
- `utils/text.py`: `yaml_escape` extended for newlines/tabs
- `utils/wiki_log.py`: auto-create `wiki/log.md` on first write
- Test fixtures consolidated (`create_wiki_page`, `create_raw_source`)

### Stats
- 180 tests (+33 parametrized edge case tests), 19 MCP tools, 10 modules

---

## [0.5.0] — 2026-03-31 (Phase 2.1)

Quality and robustness fixes.

### Added
- `feedback.py`: weighted Bayesian trust scoring (wrong penalized 2x)
- `utils/text.py`: canonical path utilities (`make_source_ref`, `_canonical_rel_path`)
- `config.py`: tuning constants (`STALENESS_MAX_DAYS`, `SEARCH_TITLE_WEIGHT`, etc.)

### Changed
- `ingest/extractors.py`: YAML injection protection; extraction JSON validation
- `models.py`: regex-based frontmatter parsing
- `graph/analysis.py`: edge invariant enforcement; empty slug guards

### Stats
- 147 tests, 19 MCP tools, 10 modules

---

## [0.4.0] — 2026-03-30 (Phase 2)

Multi-loop supervision system.

### Added
- `kb.feedback`: query feedback store with weighted Bayesian trust scoring
- `kb.review`: page-source pairing, review context/checklist builder, page refiner
- `kb.lint.semantic`: fidelity, consistency, completeness context builders for LLM evaluation
- `kb.lint.verdicts`: persistent lint/review verdict storage
- `.claude/agents/wiki-reviewer.md`: Actor-Critic reviewer agent
- 7 new MCP tools: `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`

### Stats
- 114 tests, 19 MCP tools (+7), 10 modules (+3)

---

## [0.3.0] — 2026-03-29 (Phase 1)

Initial release. Core system with 5 operations + graph + CLI.

### Added
- Content-hash incremental compile with three index files
- Model tiering (scan/write/orchestrate)
- Structured lint output
- 5 operations: ingest, compile, query, lint, evolve
- Knowledge graph with wikilink extraction
- CLI with 6 commands
- 12 MCP tools

### Stats
- 81 tests, 12 MCP tools, 7 modules
