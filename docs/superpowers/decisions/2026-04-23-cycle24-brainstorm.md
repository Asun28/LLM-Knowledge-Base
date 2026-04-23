# Cycle 24 — Brainstorming (Step 3)

**Date:** 2026-04-23
**Input:** `2026-04-23-cycle24-requirements.md` (15 ACs across 5 clusters), `2026-04-23-cycle24-threat-model.md` (T1-T10 + design-gate conditions).

Per `feedback_auto_approve` (memory): no user gates. Opus Step-5 decision gate is the approval mechanism. This doc enumerates 2-3 approaches per cluster with trade-offs + recommendation, feeding Step 4 (parallel design eval).

## Cluster A — Evidence-trail inline render + error surfacing

### Approach A1 — Inline render in `_write_wiki_page` body, surface `OSError` in `_update_existing_page`

The new-page path (both `exclusive=True` and `exclusive=False` branches) builds the rendered content to include the `## Evidence Trail` section + sentinel + initial entry as part of the first write. No follow-up `append_evidence_trail` call for new pages. The update path (`_update_existing_page`) keeps the two-write pattern but wraps `append_evidence_trail` in a `try/except OSError` that re-raises as `StorageError(kind="evidence_trail_append_failure", path=page_path)`.

- **Pros:**
  - Eliminates the two-write race entirely for new pages (AC1 contract).
  - Minimal surface: only touches `_write_wiki_page` (both branches), `_update_existing_page`, and adds a small rendering helper.
  - Reuses the existing `format_evidence_entry` + `SENTINEL` primitives from `evidence.py` — sentinel format stays canonical.
  - Preserves the cycle-18 `_write_index_files` + cycle-20 `O_EXCL` exclusive-branch invariants.
- **Cons:**
  - Does not close the update-path window (two-write remains). AC2 only surfaces the failure; it doesn't prevent partial state.
  - Requires careful sentinel format match — any drift silently breaks `append_evidence_trail`'s FIRST-match fallback on existing pages (mitigated by reusing `evidence.py`'s SENTINEL constant).
  - The exclusive branch (`pipeline.py:361-390`) currently writes raw `os.open(O_WRONLY|O_CREAT|O_EXCL)` + `os.write(fd, rendered.encode())`. Inline render means the rendered payload gets bigger but the O_EXCL semantics are unchanged.

### Approach A2 — Rollback-aware composite helper

A new `_write_wiki_page_with_evidence` helper calls the body write + evidence append in sequence; on evidence-append failure, it unlinks the body file to roll back to pre-call state.

- **Pros:**
  - Single-write semantics from caller's perspective (either both succeed or neither does).
  - Unified contract across new + update paths.
- **Cons:**
  - **Rollback on update path loses user-visible content:** the body write may reflect a legitimate RMW update; unlinking it destroys data the user just committed elsewhere via hash-detected changes.
  - Complexity: 50+ LOC of bespoke rollback logic + error-path tests.
  - Doesn't compose with the `_write_index_files` pattern (cycle-18 best-effort writes with independent try/except).

### Approach A3 — Error-surfacing only (minimal)

Skip AC1's inline render. Only ship AC2 (surface `OSError` from `append_evidence_trail` as `StorageError`). Accept the two-write window for both new and update paths.

- **Pros:** Smallest diff (~5 LOC).
- **Cons:** Doesn't close the window — just makes failures visible. Violates the requirements' "phase 4 provenance invariant" goal.

### Recommendation — **A1** (matches requirements AC1-AC4).

**Implementation sketch:**

1. Extract a helper `render_initial_evidence_trail(source_ref, action, entry_date=None) -> str` in `evidence.py` that returns `f"\n## Evidence Trail\n{SENTINEL}\n- {date} | {_neutralize_pipe(source)} | {_neutralize_pipe(action)}\n"`.
2. In `_write_wiki_page` (both branches), `rendered = body + render_initial_evidence_trail(source_ref, action)` BEFORE writing.
3. Remove the `append_evidence_trail(effective_path, source_ref, f"Initial extraction: {page_type} page created")` call after the write.
4. In `_update_existing_page`, wrap the `append_evidence_trail(page_path, source_ref, verb...)` call in `try/except OSError as e: raise StorageError(kind="evidence_trail_append_failure", path=page_path) from e`.

## Cluster B — Vector-index atomic rebuild

### Approach V1 — `<db>.tmp` + `os.replace`

`rebuild_vector_index` unlinks any stale `<vec_db>.tmp`, then calls `VectorIndex(vec_path).build(entries, db_path=tmp_path)` which writes to the tmp file, then `os.replace(tmp_path, vec_path)` atomically swaps.

- **Pros:**
  - POSIX `os.replace` is atomic. NTFS `MoveFileExW(MOVEFILE_REPLACE_EXISTING)` is near-atomic (kernel-serialised, not file-system atomic but observable-atomic).
  - Matches the requirements (AC5-AC8).
  - Minimal new surface: one helper kwarg + one unlink + one `os.replace`.
  - No new config constants.
- **Cons:**
  - **Windows reader-holds-connection blocks replace** → requires `_index_cache.pop(str(vec_path), None)` ordered BEFORE `os.replace` (Condition 2 from threat model T9).
  - The cached `VectorIndex._conn` may still hold a connection even after cache pop (other code paths might have grabbed the instance before the pop). On Windows this is a residual failure mode — documented as a Step-11 Codex verification item.

### Approach V2 — Atomic symlink swap

Write the new DB to `<db>.new-<ts>`, then `os.symlink` swap the production path. Old DB removed after next stable point.

- **Pros:** Classic atomic-swap pattern; enables MVCC-style readers to continue on old DB.
- **Cons:**
  - **Windows symlinks require SeCreateSymbolicLinkPrivilege** (admin or Developer Mode). Non-starter for a general-use tool.
  - Requires connection-redirect logic — readers opening `<db>` get redirected; readers with persistent `_conn` on the old inode diverge.
  - Significant new surface.

### Approach V3 — In-place rebuild in a single sqlite transaction

Open connection to `vec_path`, `BEGIN EXCLUSIVE`, `DROP TABLE`, `CREATE TABLE`, bulk insert, `COMMIT`.

- **Pros:** Uses sqlite's own ACID. No new files.
- **Cons:**
  - Large transactions (thousands of embeddings) hold WAL memory and can trigger checkpoint contention.
  - **`sqlite_vec` virtual-table `CREATE`/`DROP` behaviour inside EXCLUSIVE transactions is not documented as safe across all sqlite-vec versions**; testing shows it works on current builds but is fragile.
  - Crash mid-transaction: sqlite rolls back via journal, but the journal itself can become corrupt on disk-full mid-WAL. Not meaningfully safer than the current in-place flow.

### Recommendation — **V1** (matches requirements AC5-AC8 + Condition 2).

**Implementation sketch:**

1. Refactor `VectorIndex.build` to accept `db_path: Path | None = None`, default `self.db_path`; use `db_path if db_path is not None else self.db_path` (threat T10).
2. In `rebuild_vector_index`:
   - Compute `tmp_path = vec_path.parent / (vec_path.name + ".tmp")`.
   - `tmp_path.unlink(missing_ok=True)` (AC6).
   - `VectorIndex(vec_path).build(entries, db_path=tmp_path)` — builds to tmp.
   - `_index_cache.pop(str(vec_path), None)` (T9, Condition 2 — MUST be before replace).
   - `os.replace(str(tmp_path), str(vec_path))` (AC5).
3. Empty-pages branch: same tmp-then-replace flow for the zero-entries case.

## Cluster C — `file_lock` exponential backoff

### Approach L1 — Exponential schedule (10ms → 20ms → 40ms → 80ms → cap)

Cap at `LOCK_POLL_INTERVAL` (0.05 default). On each retry iteration, sleep `min(initial_interval * 2**iter, LOCK_POLL_INTERVAL)`. Module-level `LOCK_INITIAL_POLL_INTERVAL = 0.01` constant controls the floor.

- **Pros:**
  - Low-contention case finishes fast (first poll at 10ms vs 50ms).
  - High-contention case caps at the pre-cycle throughput (50ms).
  - `LOCK_POLL_INTERVAL` preserved as a visible module attribute — existing monkeypatches keep working.
  - Single math line: `interval = min(INITIAL * 2**n, LOCK_POLL_INTERVAL)`.
- **Cons:**
  - New config constant `LOCK_INITIAL_POLL_INTERVAL` — one more knob.
  - Tests that asserted a specific sleep count under contention may need to be updated (cycle-2 tests monkeypatch `LOCK_POLL_INTERVAL` but don't assert sleep count).

### Approach L2 — Jittered exponential

Same as L1 but with `random.uniform(0.5, 1.5) * interval` jitter.

- **Pros:** Reduces thundering-herd on N-waiter contention.
- **Cons:**
  - Non-deterministic — tests harder to write; `random.seed()` monkeypatching required for deterministic assertions.
  - Cycle-22 L1 reload-leak risk if `random` is imported at module top.

### Approach L3 — Single-constant retune to 10ms fixed

Just change `LOCK_POLL_INTERVAL = 0.05` to `0.01`. No exponential logic.

- **Pros:** Trivial (1-line change).
- **Cons:**
  - High-contention floor also drops to 10ms — busier polling under N-waiter contention → more syscall pressure.
  - The current 50ms is explicitly called out in the requirements as the minimum floor being addressed; dropping to 10ms fixed without backoff is a different gap.

### Recommendation — **L1** (matches requirements AC9 + Condition 3).

**Implementation sketch:**

1. Add `LOCK_INITIAL_POLL_INTERVAL = 0.01` module-level constant.
2. Inside `file_lock` retry loop: track `attempt_count` (reset each outer iteration), compute `poll = min(LOCK_INITIAL_POLL_INTERVAL * (2 ** attempt_count), LOCK_POLL_INTERVAL)`, then `time.sleep(poll)`; increment `attempt_count`.
3. Read both constants at CALL time (not snapshot into locals) — matches cycle-17 test monkeypatch expectations.

**Design-gate decision for T4:** `LOCK_POLL_INTERVAL` is the CAP. Monkeypatching `LOCK_POLL_INTERVAL = 0.001` → ALL sleeps clamped to ≤ 0.001. This preserves backward-compat and is the simpler semantic.

## Cluster D — BACKLOG maintenance

### Approach M1 — Edit BACKLOG.md inline

Delete cycle-23-resolved HIGH-Deferred multiprocessing entry. Update diskcache + ragas CVE re-check dates. Add any new deferred-to-backlog entries surfaced by the threat-model (§6 of threat-model.md). Commit as a single doc-only commit near the end of the cycle.

- **Pros:** One file touched, one commit, no code impact.
- **Cons:** None.

### Recommendation — **M1**.

## Cluster E — Sentinel-anchor hardening (new, T5)

### Approach E1 — Section-anchored regex search in `append_evidence_trail`

Change `if SENTINEL in content: ... content.index(SENTINEL)` to a regex that finds the `## Evidence Trail` header FIRST, then searches for sentinel only within the bytes following that header.

- **Pros:**
  - Structural fix: attacker-planted body sentinels are inert.
  - Preserves cycle-1 H12 FIRST-match heuristic at the section level.
  - Small diff (~10 LOC).
- **Cons:**
  - Existing pages with sentinel-but-no-header (unlikely but possible from pre-cycle-1 H12 upgrades) need careful handling — fall back to current FIRST-match behaviour when no `## Evidence Trail` header is present.

### Approach E2 — Body-sanitation pass in `_build_summary_content` / `_build_item_content`

Strip any `<!-- evidence-trail:...` substrings from LLM-extracted content before rendering. Parallel to cycle-18 `sanitize_text`.

- **Pros:** Prevents the sentinel from ever entering the body.
- **Cons:**
  - Only protects NEW pages. Pre-cycle-24 pages with existing attacker-planted sentinels remain vulnerable.
  - Strips legitimate markdown content containing the sentinel literal (obscure but possible — e.g., documentation ABOUT the evidence trail).
  - Must be added in multiple render paths; missing one reintroduces the vulnerability.

### Approach E3 — Combine E1 + E2

Both sanitation AND section-anchored search. Defense in depth.

- **Pros:** Belt-and-suspenders.
- **Cons:** Twice the test surface; possible over-engineering for a low-severity scenario.

### Recommendation — **E1** (section-anchored search).

**Implementation sketch:**

1. In `append_evidence_trail`, replace:
   ```python
   if SENTINEL in content:
       sentinel_pos = content.index(SENTINEL)
   ```
   with:
   ```python
   header_match = re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)
   if header_match:
       # Search for sentinel only AFTER the header
       header_end = header_match.end()
       tail = content[header_end:]
       if SENTINEL in tail:
           sentinel_pos = header_end + tail.index(SENTINEL)
           # ... existing insert-after-sentinel logic
       else:
           # Header present but no sentinel — plant sentinel at end of header
           content = content[:header_end] + SENTINEL + "\n" + entry + "\n" + content[header_end:]
   else:
       # No header at all — create section with sentinel (current fallback)
       content = content.rstrip("\n") + "\n\n## Evidence Trail\n" + SENTINEL + "\n" + entry + "\n"
   ```

2. AC15 regression test: seed a page body with a fake `<!-- evidence-trail:begin -->` literal BEFORE the real `## Evidence Trail` section; call `append_evidence_trail`; assert the new entry lands after the real header, not the fake.

## Cross-cluster considerations

- **Lock-order discipline.** None of the cycle-24 changes add new locks. AC1 keeps body write inside `file_lock(page_path)` via the existing `_write_wiki_page` flow. AC2 doesn't acquire a lock. AC5 uses `_rebuild_lock` (threading.Lock) + NTFS kernel-level serialisation on `os.replace`. AC9/AC10 only tune the retry interval — no protocol change.
- **Test ordering resilience.** All new cycle-24 tests follow cycle-20 L1 (late-bind exception classes), cycle-19 L2 (lazy loading for module-top file reads — not applicable here), cycle-18 L1 (dynamic config lookup for path constants).
- **Concurrency invariants.** The cycle-16 `_index_cache.pop` ordering (now Condition 2 for AC5) must be respected. The existing `file_lock(page_path)` convention around `append_evidence_trail` is preserved by AC1 (no new lock; just a larger first-write payload inside the existing lock).

## Open questions for Step-5 decision gate

1. **Q1 — AC1 scope: both branches of `_write_wiki_page`?** Requirements Condition 1 says yes. Confirm at gate.
2. **Q2 — AC5 ordering: `_index_cache.pop` before or after `os.replace`?** Requirements Condition 2 says BEFORE. Confirm at gate.
3. **Q3 — AC9 `LOCK_POLL_INTERVAL` semantic: CAP or fallback?** Recommendation says CAP. Confirm at gate.
4. **Q4 — AC14 sentinel-anchor: option E1 (section-anchored regex) or E3 (regex + sanitation)?** Recommendation says E1. Confirm at gate.
5. **Q5 — AC6 stale-tmp unlink placement: before `_rebuild_lock` acquire or after?** Design note says AS FIRST STATEMENT inside `rebuild_vector_index` — specifically BEFORE the `_hybrid_available` + `_is_rebuild_needed` gates so a crashed-previous-run tmp is cleaned even when gates say skip. Confirm at gate.
6. **Q6 — AC11 BACKLOG cleanup: edit inline in the same PR, or separate doc PR?** Recommendation says same PR (user feedback batches doc + code per cycle; feedback_batch_by_file memory).
7. **Q7 — New deferred-to-backlog entries** from threat-model §6: confirm addition of §Phase 4.5 MEDIUM fair-queue lock + §Phase 4.5 HIGH sentinel-anchor if E1 only + §Phase 4.5 HIGH exclusive-branch evidence + any others.

All 7 questions are INTERNAL (no user input needed). Step 5 Opus gate resolves each with an `## Analysis` block.
