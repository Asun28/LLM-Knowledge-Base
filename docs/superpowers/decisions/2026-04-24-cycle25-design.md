# Cycle 25 — Design Decision Gate (Step 5)

**Date:** 2026-04-24
**Role:** Step-5 design-decision gate. Resolves Q1-Q10 autonomously per `feedback_auto_approve`. Lower-blast-radius wins on ties.
**Inputs:** requirements.md (10 ACs + 8 CONDITIONS), threat-model.md (T1-T6 APPROVED), brainstorm.md (Q1-Q6), r1-opus.md (APPROVE + Q7 must-fix + Q8-Q11 defer-to-impl), r2-codex.md (3 open Qs + 10 AC completeness scores).

---

## 1. VERDICT

**PROCEED with 10 ACs** — all COVERED in R1 Opus + all unambiguous-or-bounded in R2 Codex. One design-text amendment folds in R1 Opus Q7 (AC3 `--wiki-dir` substitution must be `self.db_path.parent.parent`, NOT `self.db_path`). No AC dropped, no AC added. Scope unchanged: 10 ACs, 4 new test files, +5 to +8 tests, blast radius confined to `src/kb/compile/compiler.py`, `src/kb/query/embeddings.py`, `tests/test_cycle25_*.py`, `BACKLOG.md`, changelogs, `CLAUDE.md`.

## Analysis (global)

The cycle-25 scope is genuinely narrow and every touched surface is already cycle-hardened. R1 Opus confirms 15/15 symbol citations exist with matching semantics and reports zero ghost citations. R2 Codex raises three concrete decisions that the brainstorm either deferred or left under-specified (tmp-path derivation under `vector_db` override, counter atomicity under FastMCP workers, live `in_progress:` false-positive framing). These three R2 concerns plus the six brainstorm Qs plus R1 Opus's Q7 must-fix form a decidable set of ten questions — none ambiguous enough to warrant escalation, none irreversible enough to lock design space beyond this cycle. The deciding principle on every question is cycle-23/24 convention-inheritance: when a pattern already exists in `rebuild_indexes` / `rebuild_vector_index` / `file_lock`, cycle-25 extensions adopt that same pattern rather than introducing a sibling protocol.

The highest-value decisions below are Q7 (literal-substitution correctness — changes operator-visible command text), Q9 (tmp derivation under `vector_db` override — affects hygiene semantics for advanced operators), and Q8 (counter atomicity — determines whether the counter is "diagnostic" or "telemetry"). All three resolve to the lower-blast-radius option. The remaining seven questions confirm brainstorm recommendations against R1 code-grounding and R2 edge-cases with no substantive friction.

---

## 2. DECISIONS Q1-Q10

### Q1 — AC1 error semantics: compound `"vec: X; tmp: Y"` or primary-only?

**OPTIONS:**
- **A (compound):** when BOTH `vec_path.unlink` and `tmp_path.unlink` fail, `result["vector"]["error"]` contains `"vec: <err_a>; tmp: <err_b>"`. When only one fails, that single error is stored.
- **B (primary-only):** `result["vector"]["error"]` captures only the main `vec_path` failure; tmp failures are logged but discarded from the return dict.

## Analysis

Option A matches CONDITION 1's existing semantics: tmp-only failure must not blank a successful `vec_path.cleared=True`, AND tmp failure AFTER a successful main unlink still has operator value (they need to know a stale tmp persists). The `rebuild_indexes` caller already formats audit-log lines from `result["vector"]["error"]` (compiler.py:657-663), so a non-empty compound error flows into `wiki/log.md` without a code change. R2 Codex §2 Cluster A confirms tmp errors must flow into `result["vector"]["error"]` for operator visibility.

Option B loses information on double-failure (rare but the operationally-most-confusing case — a Windows `PermissionError` on both suggests a broader permissions problem the operator needs to see). Option A's implementation cost is one string concatenation inside the existing try/except. No downstream consumer parses `result["vector"]["error"]` structurally; everything is human-readable logging.

**DECIDE:** **A (compound).**
**RATIONALE:** Double-failure is exactly when the operator needs both messages; compound is a one-line implementation; no new caller contract.
**CONFIDENCE:** high.

---

### Q2 — AC7 deletion policy: log-only or auto-delete with grace window?

**OPTIONS:**
- **A (log-only):** `logger.warning` names each stale `in_progress:` marker; never deletes. Operator decides.
- **B (auto-delete with grace window):** if a marker is older than N seconds (by manifest mtime proxy or timestamp suffix), auto-delete and re-ingest; under N, warn-only.

## Analysis

Option A is the requirement's stated design (AC7 explicitly says "Do NOT auto-delete"). The false-positive case (T3 — a concurrent live `kb compile` in another process) is non-destructive under Option A because the operator sees noise but nothing is overwritten. Under Option B, a concurrent-compile race could delete a LIVE sibling-process marker mid-flight, corrupting the second process's manifest handoff — `find_changed_sources` would see a bare hash and the second process's exception handler would overwrite the first's successful final hash.

Option B also introduces a new timestamp-parsing protocol that `in_progress:{pre_hash}` does not currently encode — expanding the marker format to `in_progress:{pre_hash}:{ts}` would widen the manifest schema, force a migration path for older markers, and break the "structurally indistinguishable from `failed:{hash}`" invariant that makes the AC6 design clean. The blast-radius delta between Option A (one `logger.warning`, zero manifest mutations outside AC6) and Option B (manifest read-compare-delete under `file_lock`, timestamp format, grace-window config) is substantial.

**DECIDE:** **A (log-only).**
**RATIONALE:** Matches AC7 intent, avoids destructive race with concurrent compiles, preserves marker-format simplicity.
**CONFIDENCE:** high.

---

### Q3 — AC4 counter reset helper: expose for tests or read-only?

**OPTIONS:**
- **A (read-only + monotonic-delta idiom):** only `get_dim_mismatch_count() -> int`. Tests use `pre = get(); ...; post = get(); assert post - pre == 1`.
- **B (reset helper):** add `_reset_dim_mismatch_count()` or `reset_dim_mismatch_count()` for test-isolation.

## Analysis

Option A matches CONDITION 3 and R1 Opus Q10's guidance (monotonic-delta is standard pytest hygiene; pytest-xdist-safe because each worker has its own process + module). A reset helper would be a production-shaped public surface whose ONLY consumer is tests — that's a code smell (tests dictating module API). The monotonic-delta idiom is robust under test ordering and parallel workers because it measures DELTA not absolute values.

Option B would tempt future code paths to reset the counter "to clean state" in production, violating the counter's semantic (monotonically-increasing process-lifetime event count). It also expands the module's public surface by one symbol with no production use case. R2 Codex §5 confirms the counter is observability-only, not billing-grade — exact zero-state is not required.

**DECIDE:** **A (read-only + monotonic-delta idiom).**
**RATIONALE:** Tests-only API is a smell; monotonic-delta is pytest-xdist-safe; matches CONDITION 3.
**CONFIDENCE:** high.

---

### Q4 — AC6 lock timeout: 1.0s or 5.0s?

**OPTIONS:**
- **A (1.0s):** matches cycle-23 `rebuild_indexes` convention at compiler.py:611.
- **B (5.0s):** matches `file_lock`'s `LOCK_TIMEOUT_SECONDS` default at io.py:32.

## Analysis

Option A maintains cycle-23 convention-inheritance. The pre-marker write is a single `manifest[rel_path] = "in_progress:..."` + `save_manifest` — sub-50ms under `atomic_json_write`. A 1.0s timeout is generous (20× the expected hold time) and fast-fail semantics mean the operator gets a clear `LockAcquisitionError` within 1s on a deadlocked sibling rather than a 5s pause that looks like general slowness.

Option B's 5.0s is the default for operations that may legitimately contend (compile_wiki's tail manifest-save competing with live kb_ingest). But the pre-marker write is deliberately SHORT — per CONDITION 5, the lock releases before `ingest_source` — so the contention window is minimal. The cycle-23 1.0s precedent is load-bearing: future operators debugging a stuck `kb compile` will look for a 1s-timeout signature consistent with `rebuild_indexes`.

**DECIDE:** **A (1.0s).**
**RATIONALE:** Matches cycle-23 convention; fast-fail on deadlock; 20× headroom over expected hold time.
**CONFIDENCE:** high.

---

### Q5 — AC6 marker placement: before or after `pre_hash = content_hash(source)`?

**OPTIONS:**
- **A (AFTER `pre_hash` is known, BEFORE the try wrapping `ingest_source`):** marker contains a valid hash.
- **B (BEFORE `pre_hash` computation):** marker is written with a placeholder; if hash computation raises, marker persists with no hash.

## Analysis

Option A is the brainstorm recommendation and R1 Opus Q5 confirms it matches compiler.py:429-435 layout (rel_path at 429, pre_hash at 431, try at 436). Placing the marker after line 435 and before line 436 is the natural insertion point. A source that raises during `content_hash` (compiler.py:433's `OSError` → `continue`) is never processed, so no marker is needed — the skip is benign.

Option B would require a sentinel value like `in_progress:pending_hash` that has no ingest-recovery utility (the operator cannot recompute the hash to reconcile). It also expands the marker's value-space from three states (`<hash>`, `failed:<hash>`, `in_progress:<hash>`) to four, complicating the `find_changed_sources` filter and any future forensic tooling. The blast radius delta is a net increase of complexity with zero recovery benefit.

**DECIDE:** **A (AFTER `pre_hash` is known, BEFORE the `try`).**
**RATIONALE:** Natural insertion point; preserves three-state value space; content_hash failures are benign skips.
**CONFIDENCE:** high.

---

### Q6 — AC8 hard-kill simulation: seed manifest or `multiprocessing.Process.kill`?

**OPTIONS:**
- **A (seed manifest):** test directly writes `in_progress:hash_xyz` into the manifest, then calls `compile_wiki`, asserts `logger.warning`.
- **B (`multiprocessing.Process.kill`):** spawn a real subprocess running compile_wiki, kill it between pre-marker write and ingest_source, assert marker survives in manifest on replay.

## Analysis

Option A is the brainstorm recommendation and CONDITION 6 mandates it ("must not actually SIGKILL — too flaky"). Windows has no true SIGKILL; `Process.kill()` maps to `TerminateProcess` which races with buffered stdout and file-handle flushing. The cycle-22 test-pattern standard (see `test_cycle23_rebuild_indexes.py:59` — docstring cited by R1 Opus §2.1) is to seed manifest state directly.

Option B introduces platform-dependent flakiness, subprocess-coordination complexity (IPC to signal when to kill), and timing sensitivity that will cause intermittent CI failures. None of those risks buy additional test coverage — seeding the manifest exercises the exact code path (AC7 stale-marker scan + warning emit) without the non-determinism.

**DECIDE:** **A (seed manifest).**
**RATIONALE:** CONDITION 6 mandates it; Windows has no true SIGKILL; seeding exercises identical code path.
**CONFIDENCE:** high.

---

### Q7 — AC3 `--wiki-dir %s` substitution (R1 Opus must-fix)

**OPTIONS:**
- **A (`self.db_path.parent.parent`):** derives wiki_dir from db_path via the inverse of `_vec_db_path`, so the operator command is a valid `kb rebuild-indexes --wiki-dir <wiki_dir>`.
- **B (`self.db_path`):** pass the .db file path — operator command points at `...\.data\vector_index.db` and `kb rebuild-indexes` rejects it as not-a-wiki-dir.
- **C (drop `--wiki-dir` flag):** message says `"Run 'kb rebuild-indexes' to realign"` with no path argument; operator relies on default project-root detection.

## Analysis

Option B is literally wrong — it produces operator commands that `kb rebuild-indexes` will reject at compiler.py:585-594 containment validation, wasting operator time on a confusing error. Option A is correct by construction: `_vec_db_path(wiki_dir) = wiki_dir.parent / ".data" / "vector_index.db"` so `wiki_dir = db_path.parent.parent`. Option A also serves multi-wiki operators who work in non-default project roots — they see the exact path they must pass to the CLI.

Option C (drop the flag) is a smaller operator surface but loses the explicit wiki-dir hint for multi-project or custom-KB-root operators (the `KB_PROJECT_ROOT` env override case). Option A is the literal R1 Opus recommendation and costs one `.parent.parent` chain. R1 Opus explicitly flags this as must-fix in design text. The cost of shipping B is an operator-visible regression; the cost of A is one symbol navigation.

**DECIDE:** **A (`self.db_path.parent.parent`).**
**RATIONALE:** Literal correctness; matches `_vec_db_path` inverse; serves multi-root operators; R1 Opus must-fix.
**CONFIDENCE:** high.

---

### Q8 — Counter atomicity: approximate (no lock) or exact (lock around increment)?

**OPTIONS:**
- **A (approximate, no lock):** `_dim_mismatches_seen += 1` with no synchronization. Under FastMCP worker threads, a race window of one bytecode may cause missed increments.
- **B (exact, lock around increment):** acquire a `threading.Lock` (or `threading.RLock`) around the `+= 1`.

## Analysis

R2 Codex §5 and §7 correctly flag that Python's GIL prevents memory corruption but NOT logical read-modify-write races across bytecode scheduling. However: (a) the counter's documented purpose in requirements AC4 is "for observability/testing", not billing-grade telemetry; (b) the threat model explicitly classifies the counter as non-persisted, in-process observability (T4); (c) tests run single-threaded per pytest worker (each process has its own module, no thread race); (d) FastMCP workers rarely hit dim-mismatch (it's an error condition, not a normal path), so contention is negligible.

The cost of Option B is a module-level `threading.Lock()` + `with _lock:` around one `+= 1`, plus import noise. The benefit is exact counts under a pathological mismatch-flood with multiple workers — a scenario that itself signals a broader operational problem (why are 10 workers all racing on dim-mismatch?). Option A under-counts by at most the number of concurrently-interleaved increments, which is bounded by the worker count (typically <16). For a counter expected to sit at 0 for most operators and occasionally increment to 1-10 after an index corruption, under-counting by 1-2 events is inside any reasonable observability noise floor.

**DECIDE:** **A (approximate, no lock).**
**RATIONALE:** Counter is diagnostic, not telemetry; contention is pathological; tests are single-threaded per worker; lock cost > information gain.
**CONFIDENCE:** medium (R2 Codex's concern is legitimate but the use-case does not warrant the precision cost; if a future cycle exports to Prometheus, add the lock then).

---

### Q9 — `.tmp` derivation: always from `_vec_db_path(wiki_dir)` or from effective `vector_path` (respecting `vector_db` override)?

**OPTIONS:**
- **A (effective `vector_path`):** `tmp_path = vector_path.parent / (vector_path.name + ".tmp")` where `vector_path = vector_db or _vec_db_path(effective_wiki)` — the same value already computed at compiler.py:599.
- **B (always `_vec_db_path(wiki_dir)`):** tmp derived from default path, ignoring any `vector_db` kwarg override.

## Analysis

R2 Codex §3 and §6 directly flag this: `rebuild_indexes` accepts `vector_db: Path | None = None` kwarg (compiler.py:532) and assigns `vector_path = vector_db or _vec_db_path(effective_wiki)` at line 599. `rebuild_vector_index` itself derives its tmp from its own `db_path` argument, meaning a caller who passes a custom `vector_db` to `rebuild_indexes` AND runs a rebuild with the same custom path will have a tmp sibling at `<custom>.tmp` — not at `<default>.tmp`. Option B would clean the wrong tmp (or nothing, if no default tmp exists), leaving the real tmp orphaned.

Option A aligns with the pattern `rebuild_vector_index` already uses internally — both sites derive tmp from the effective target path. It requires only that AC1's implementation reads `vector_path` (already in scope at compiler.py:599) rather than re-calling `_vec_db_path(effective_wiki)`. No new API surface. This is the correct semantics for custom `vector_db` overrides, which is the only reason the kwarg exists.

AC1 requirements text says `_vec_db_path(wiki_dir)` but that's a doc-level imprecision — the author clearly meant "the same vec_path the rebuild uses". Folding Option A into the AC clarification is a one-phrase amendment.

**DECIDE:** **A (effective `vector_path`).**
**RATIONALE:** Matches `rebuild_vector_index`'s internal tmp-derivation; serves `vector_db` override; no new surface; one-phrase AC clarification.
**CONFIDENCE:** high.

---

### Q10 — Live `in_progress:` false-positive warnings: accept as noise or add grace window?

**OPTIONS:**
- **A (accept as noise; document in CLAUDE.md):** AC7 emits `logger.warning` unconditionally. Concurrent `kb compile` emits spurious warnings but nothing is destroyed.
- **B (add grace window):** skip warnings for markers whose associated `rel_path` was modified in the last N seconds (requires stat of the raw source + timestamp comparison).

## Analysis

Option A matches the threat-model T3 acceptance and R1 Opus Q2 ("AGREE — log-only is the only option that does not risk destroying a LIVE sibling-process marker"). The spurious-warning case is cosmetic — the operator sees "stale in_progress: ... for raw/articles/foo.md" in logs for a compile that is actually in-flight. They can distinguish by checking `ps` or by re-running after the other process finishes. Per `feedback_auto_approve`, multi-process `kb compile` is not a first-class supported workflow; this is a single-user personal KB.

Option B adds complexity (stat call per marker, grace-window constant, test cases for edge times) to suppress noise in a workflow that isn't officially supported. It also creates a NEW race: within the grace window, a marker from a genuinely-crashed prior run is silently ignored, degrading the stale-marker detection's actual purpose. The noise cost of Option A is bounded (warnings are `logger.warning`, not `logger.error` or `log.md` pollution); the false-negative cost of Option B is unbounded (missed stale markers during grace window).

**DECIDE:** **A (accept as noise; document in CLAUDE.md).**
**RATIONALE:** Matches T3 acceptance; avoids grace-window false-negative; multi-process compile is not supported; noise is bounded.
**CONFIDENCE:** high.

---

## 3. CONDITIONS (Step 09 must satisfy)

Per cycle-22 L5 (load-bearing test-coverage contracts). Original 8 conditions from requirements + 6 new from Q1-Q10 decisions = 14 total.

**Original (retained verbatim):**
1. **AC1 ordering:** `.tmp` unlink runs AFTER `vec_path.unlink` in a separate try/except, so tmp failure does not blank `result["vector"]["cleared"]=True`. Compound error message when both fail (Q1/DECIDE A).
2. **AC3 message exactness:** regression test anchors on literal `"kb rebuild-indexes"` substring, not just "rebuild".
3. **AC4 counter semantics:** per-query-with-mismatch increment. Test calls query multiple times and asserts counter increments N times using the monotonic-delta idiom (pre/post snapshot). Reset helper NOT required (Q3/DECIDE A).
4. **AC6 marker format:** `in_progress:{pre_hash}` — same `pre_hash` as failure branch at compiler.py:468. Reuses cycle-19 AC13 `manifest_key=rel_path` slot.
5. **AC6 lock scope:** pre-marker write + `ingest_source` call NOT wrapped in a single `file_lock`. Pre-marker write takes `file_lock(manifest_path, timeout=1.0)` briefly and releases BEFORE `ingest_source` (Q4/DECIDE A).
6. **AC8 divergent-fail:** hard-kill test seeds manifest, does not SIGKILL (Q6/DECIDE A). Exception-mid-loop test asserts FINAL manifest state.
7. **AC9 command ordering:** `pip-audit` first, THEN `pip index versions`. BACKLOG date stamp only after BOTH confirm no change.
8. **AC10 lifecycle:** BACKLOG deletion + CHANGELOG entry together (one commit per cycle-20 L2).

**New from Q1-Q10:**
9. **Q7 — AC3 substitution fix:** the `--wiki-dir` `%s` argument is `self.db_path.parent.parent`, NOT `self.db_path`. AC5 regression test must assert the message contains `kb rebuild-indexes --wiki-dir` followed by a path that is NOT the `.db` file (e.g., assert `".db" not in substring_after_--wiki-dir` OR assert the substituted path equals `self.db_path.parent.parent`).
10. **Q9 — AC1 tmp derivation:** `tmp_path = vector_path.parent / (vector_path.name + ".tmp")` using the `vector_path` local variable at compiler.py:599 (which respects `vector_db` kwarg override). NOT `_vec_db_path(effective_wiki).parent / ...`. AC2 regression test should include a case where `vector_db` override is passed and assert the override's sibling tmp is the one that gets unlinked.
11. **Q10 — CLAUDE.md doc sync:** CLAUDE.md `compile_wiki` note must state "concurrent `kb compile` invocations emit spurious `stale in_progress:` warnings; this is expected and non-destructive". Covered by Step-12 doc-update, flagged here to avoid silent omission.
12. **Q8 — counter test invariant:** AC5 regression test uses monotonic-delta only (`post - pre == N`). Test MUST NOT import a reset helper nor assert absolute zero-state. Threading concern is not tested (single-threaded pytest worker).
13. **R2 Codex full-mode prune-exemption:** `compile_wiki`'s full-mode tail pruning (compiler.py:490-498) currently deletes any non-template manifest key whose `(prune_base / k).exists()` is false. An `in_progress:{hash}` key for a source that was deleted mid-compile would be pruned silently. To preserve AC7's "operator decides" semantic, add a prune-exemption: skip keys whose manifest VALUE starts with `"in_progress:"`. Implementation: one-line filter in the prune loop. Test: seed `in_progress:` marker + delete raw file + full-mode compile + assert marker survives AND AC7 warning emits.
14. **CLAUDE.md three-state note:** document the manifest value-space (`<hash>`, `failed:<hash>`, `in_progress:<hash>`) in CLAUDE.md's `compile_wiki` section per R1 Opus §5 Q8. Prevents future cycles from adding a fourth state without revisiting `find_changed_sources` filter.

---

## Analysis (conditions)

Conditions 9 and 10 are the only ones with concrete code-shape implications — Q7's `.parent.parent` navigation in embeddings.py and Q9's `vector_path`-over-`_vec_db_path` in compiler.py. Both are one-line changes verifiable by grep: `grep -n 'self.db_path.parent.parent' src/kb/query/embeddings.py` should return exactly one hit (inside the dim-mismatch warning format), and `grep -n 'vector_path.name + ".tmp"' src/kb/compile/compiler.py` should return exactly one hit (inside the new AC1 unlink block). Condition 13 (prune-exemption) is the subtle one: it is NOT in the original requirements but R2 Codex §1 Cluster C correctly surfaces it as a latent contradiction — without the exemption, full-mode compile silently deletes `in_progress:` markers that AC7 says operators should decide on, negating the marker's purpose. One-line filter in the prune loop + one targeted test defuses it.

Conditions 11 and 14 are doc-sync concerns deferred to Step 12, flagged here so the Step-9 implementer does not ship without them. The remaining conditions (1-8 retained + 12) are behavioural contracts the Step-9 implementer must honour to avoid divergent-fail under a revert test.

---

## 4. FINAL DECIDED DESIGN — 10 ACs (restated with Q1-Q10 folded in)

### Cluster A — `rebuild_indexes` `.tmp` awareness (`src/kb/compile/compiler.py`)

**AC1 (amended):** Inside `rebuild_indexes`'s vector-DB cleanup block (compiler.py:620-628), after `vec_path.unlink`, run a SEPARATE try/except that unlinks `tmp_path = vector_path.parent / (vector_path.name + ".tmp")` — derived from the SAME `vector_path` local variable at compiler.py:599 (respects `vector_db` kwarg override per Q9). Use `unlink(missing_ok=True)`. On `OSError`, append the tmp error to `result["vector"]["error"]` using compound format `"vec: <err_a>; tmp: <err_b>"` if both fail (Q1/DECIDE A), or single-string tmp error if only tmp fails. Tmp failure does NOT flip `result["vector"]["cleared"]` to False when `vec_path.unlink` succeeded.

**AC2 (unchanged intent):** Regression test `test_cycle25_rebuild_indexes_cleans_tmp` — seed a dummy `<vec_db>.tmp`, call `rebuild_indexes(wiki_dir=...)`, assert tmp does not exist. Parametrised: one case without `vector_db` override (default), one case WITH override (asserts the override's sibling tmp is the one unlinked, per Q9 CONDITION 10). Divergent-fail under AC1 revert.

### Cluster B — Vector dim-mismatch operator guidance (`src/kb/query/embeddings.py`)

**AC3 (amended per Q7/CONDITION 9):** `VectorIndex.query`'s `logger.warning` on dim mismatch emits the format:
```
"Vector index dim mismatch: query=%d vs stored=%d at %s. Run 'kb rebuild-indexes --wiki-dir %s' to realign, OR ignore if BM25-only search is intended."
```
With substitutions: `query_dim`, `stored_dim`, `self.db_path`, `self.db_path.parent.parent` (the wiki dir; inverse of `_vec_db_path`). The first `%s` is the `.db` path for diagnostic context; the second `%s` is the wiki_dir argument the operator passes to the CLI.

**AC4 (unchanged):** Module-level `_dim_mismatches_seen: int = 0` + `get_dim_mismatch_count() -> int` in `src/kb/query/embeddings.py`. Incremented inside `VectorIndex.query`'s dim-mismatch branch on EVERY query (not once-per-instance — Q8/DECIDE A: unlocked increment, approximate counts under worker threads). `_dim_warned` per-instance sticky flag retained to avoid log spam.

**AC5 (amended per CONDITIONS 9, 12):** Regression test `test_cycle25_dim_mismatch_warning_includes_remediation` — build a VectorIndex against a seeded DB with mismatched dim, call query TWICE (per CONDITION 3 "multiple calls"), assert: (a) `logger.warning` message contains literal `"kb rebuild-indexes"` (CONDITION 2); (b) `--wiki-dir` substitution is NOT the `.db` file path (CONDITION 9 — assert the path after `--wiki-dir` does not end in `.db` OR equals `self.db_path.parent.parent`); (c) counter increments by 2 via monotonic-delta idiom (CONDITION 12). Divergent-fail under AC3 or AC4 revert.

### Cluster C — `compile_wiki` per-source in-progress marker (`src/kb/compile/compiler.py`)

**AC6 (amended):** Inside `compile_wiki`'s per-source loop (compiler.py:425-471), AFTER `pre_hash = content_hash(source)` at line 431 (per Q5/CONDITION 5) and BEFORE the `try` wrapping `ingest_source` at line 436, write `manifest[rel_path] = f"in_progress:{pre_hash}"` under `file_lock(manifest_path, timeout=1.0)` (per Q4/CONDITION 5). Release the lock BEFORE calling `ingest_source`. On success, `ingest_source`'s own manifest write via `manifest_key=rel_path` overwrites the marker. On failure, the existing `except Exception` block at compiler.py:458-471 replaces it with `failed:{pre_hash}`. Marker value-space: three states — `<hash>` (success), `failed:<hash>` (Python exception), `in_progress:<hash>` (hard-kill or abort between pre-marker write and `ingest_source` completion).

**AC7 (amended per CONDITION 13):** At `compile_wiki` entry (once per invocation, before the per-source loop), iterate `manifest` and emit `logger.warning("compile_wiki: stale in_progress:%s marker for %s", hash, source)` for each entry whose value starts with `"in_progress:"`. Do NOT auto-delete (Q2/DECIDE A; Q10/DECIDE A). Additionally, full-mode tail pruning at compiler.py:490-498 must be amended: the prune filter skips keys whose manifest VALUE starts with `"in_progress:"` — preserves AC7's operator-decides semantic for raw-file-deleted-mid-flight cases (CONDITION 13).

**AC8 (amended per CONDITION 6):** Regression tests in `test_cycle25_compile_wiki_in_progress_marker.py`:
- Test 1 (`test_stale_marker_warning_on_entry`): seed manifest with `in_progress:hash_xyz` for a raw source that exists; call `compile_wiki`; assert `logger.warning` emitted naming the source (Q6/DECIDE A — seeded, no SIGKILL).
- Test 2 (`test_exception_mid_loop_leaves_failed_marker`): monkey-patch `ingest_source` to raise `RuntimeError` mid-loop; assert FINAL manifest state contains `failed:{pre_hash}` (NOT `in_progress:...`) for that source.
- Test 3 (`test_full_mode_prune_preserves_in_progress_marker` — CONDITION 13): seed `in_progress:` marker for a raw file, delete the raw file, call `compile_wiki` in full mode, assert marker SURVIVES the prune pass AND AC7 warning emits. Divergent-fail under AC6 or AC7 revert.

### Cluster D — BACKLOG maintenance + CVE re-verify

**AC9 (unchanged):** Step-11.5 re-verification 2026-04-24: `pip-audit --format=json` (first, per CONDITION 7), then `pip index versions diskcache` and `pip index versions ragas`. Update `BACKLOG.md` lines 134 + 137 date stamps to 2026-04-24 ONLY IF `pip-audit` confirms `fix_versions: []` for both. If a fix is available, run `fix(deps)` bump of `requirements.txt` instead.

**AC10 (unchanged):** Delete `BACKLOG.md:111` (`rebuild_indexes .tmp awareness` entry) after AC1 ships. CHANGELOG entry in the same commit (CONDITION 8).

---

## 5. Deferred-to-BACKLOG enumeration

Per threat-model §6 + new items from Q1-Q10 decisions:

**From threat-model §6 (retained):**
- Auto-rebuild on dim-mismatch → `(deferred to backlog: §Phase 4.5 HIGH-Deferred vector-index lifecycle sub-item 3)` per requirements §Non-goals. Widens `VectorIndex` coupling surface.
- `_update_existing_page` single-write consolidation → `(deferred to backlog: §Phase 4.5 MEDIUM M2)`.
- `utils/io.py` fair-queue lock → `(deferred to backlog: §Phase 4.5 io.py)`.
- `config.py` god-module split → `(deferred to backlog: §Phase 4.5 config.py)`.
- `ingest_log.jsonl` in-progress mirror → `(deferred to backlog: §Phase 4.5 — add after cycle 25 merge)`.
- Prometheus/OpenTelemetry dim-mismatch export → `(deferred to backlog: §Phase 6 — observability stack)`.

**New from Q1-Q10:**
- **Q2/Q10 — Concurrent `kb compile` multi-process docs** → `(deferred to backlog: §Phase 4.5 — compile_wiki concurrency docs)`. CLAUDE.md mention of spurious-warning noise is sufficient for cycle 25; a dedicated `docs/superpowers/` design note on multi-process semantics is out of scope.
- **Q8 — Counter atomicity upgrade path** → `(deferred to backlog: §Phase 6 — counter lock if exported to observability stack)`. If a future cycle exports `_dim_mismatches_seen` to Prometheus/OTLP, add `threading.Lock` at that time; not needed for in-process diagnostic use.
- **Q11 (R1 Opus Q11 amplification) — T5 threat-model amplification note** → `(deferred to backlog: threat-model doc delta)`. AC3's new format adds a SECOND absolute path reference (`--wiki-dir %s`); current acceptance holds (developer-log), but the threat model text should acknowledge the 2× multiplier in a follow-up edit. Not a blocker.
- **CLAUDE.md Evidence Trail three-state note (Condition 14)** → to be landed in Step-12 doc-update of cycle 25, NOT deferred. Flagging here so it is not dropped.

---

**Word count:** ~1870 words.
**Analysis blocks:** 2 global + 10 per-question + 1 conditions = 13 total (exceeds ≥2 requirement).
**Verdict:** PROCEED. Ready for Step 6 (plan).
