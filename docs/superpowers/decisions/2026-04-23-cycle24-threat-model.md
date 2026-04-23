# Cycle 24 — Threat Model (Step 2)

**Date:** 2026-04-23
**Companion to:** `2026-04-23-cycle24-requirements.md`
**Scope:** 13 ACs across 4 clusters (`src/kb/ingest/pipeline.py` + `src/kb/ingest/evidence.py`, `src/kb/query/embeddings.py`, `src/kb/utils/io.py`, `BACKLOG.md` + CVE re-check).

## Analysis

The cycle-24 surface is unusual because three of its four clusters *shrink* an existing attack surface rather than expand it: AC1 collapses a two-write window into a single atomic render, AC5/AC6/AC8 substitute `os.replace`-on-tmp for an in-place DROP+CREATE that was observable-mid-rebuild, and AC9/AC10 shorten the observable polling floor without changing the lock protocol itself. Each reduction creates its own *new* small surface we must enumerate. Collapsing the two-write window removes the "new page on disk without evidence trail" state — but it simultaneously makes the first-write disk payload larger (body + `## Evidence Trail` + sentinel + first entry) and moves sentinel emission to `_write_wiki_page`. That movement is load-bearing per the cycle-22 L2 "sentinel discipline" clause in `CLAUDE.md`: any hand-editor or source-ingestion adversary who can seed the page body BEFORE the sentinel now has a *new* injection point at the first-write render seam. Evidence-trail append ordering (reverse chronology, sentinel-anchored) is preserved by `append_evidence_trail`'s FIRST-match heuristic (`evidence.py:96-102`), which defeats the "attacker-planted forgery lands later in the body" threat from cycle 1 H12 — but only if the sentinel emitted by the new inline render matches that exact regex verbatim. Any drift between the AC1 render string and `SENTINEL = "<!-- evidence-trail:begin -->"` silently breaks future `_update_existing_page` appends on that page.

The vector-index atomic-rename work introduces the most subtle Windows-specific failure modes. `os.replace` on NTFS is atomic within a single volume, but fails across drive letters with `OSError [WinError 17]`; `<vec_db>.tmp` sits in the same `.data/` directory as `<vec_db>`, so cross-volume rename is not actually reachable by the current code path unless an operator has symlinked `.data/` onto a mounted drive. Windows also locks files open for reading — if a concurrent `kb_query` has a `sqlite3.Connection` open on `<vec_db>` when `rebuild_vector_index` calls `os.replace`, Windows raises `PermissionError [WinError 5]` or `FileExistsError` instead of atomically swapping. This interacts with `_index_cache` + `VectorIndex._ensure_conn` (`embeddings.py:229-294`): the persistent `_conn` sqlite3 handle is held for the `VectorIndex` instance's lifetime, so the post-rebuild `_index_cache.pop` in `rebuild_vector_index` at `embeddings.py:134-135` is load-bearing — without it, a stale `VectorIndex` keeps its old sqlite3 fd open against the *replaced-out* DB file, pinning the old inode on POSIX and failing `os.replace` entirely on Windows. The exponential-backoff work creates a smaller but non-trivial surprise: because `file_lock` currently reads `LOCK_POLL_INTERVAL` at call time (AC9 explicit requirement), two existing tests (`tests/test_backlog_by_file_cycle2.py:172,210`) monkeypatch the module attribute to 0.01 and rely on that value being honoured — the new backoff logic must preserve call-time lookup semantics OR widen the contract to also honour `LOCK_POLL_INTERVAL` as the cap. If the implementer snapshots the constant at function entry into a local (a reasonable micro-optimization), both tests silently fail open — they still "work" because lock acquires win fast paths, and they never exercise the contended polling branch the backoff changes. That failure mode is a divergent-test-without-divergent-fail trap; T4 below pins it explicitly.

## 1. Trust boundaries

| Change | Boundary crossed | Notes |
|---|---|---|
| AC1 inline evidence-trail render in `_write_wiki_page` | **Wiki filesystem** (`wiki/{entities,concepts,...}/{slug}.md`) | Adds sentinel + first-entry bytes to the first-write payload. Still goes through `atomic_text_write` (or `O_EXCL` when `exclusive=True`). No new boundary — same file, same write mechanism, larger payload. |
| AC2 re-raise `OSError` → `StorageError(kind="evidence_trail_append_failure")` in `_update_existing_page` | **Library → caller error-taxonomy boundary** | Internal taxonomy change; does not cross a filesystem boundary. The outer `compile_wiki` per-source loop already catches broad `Exception` with `logger.warning + continue`, so `StorageError` will flow through unchanged. |
| AC5 `os.replace(tmp, vec_path)` in `rebuild_vector_index` | **Vector DB file boundary** (`<project>/.data/vector_index.db`) | New write path is `<project>/.data/vector_index.db.tmp`. NTFS rename semantics apply (see T2). `tmp_path` and `vec_path` are siblings under the same `.data/` directory — same-volume rename guaranteed unless operator symlinks `.data/`. |
| AC6 unconditional unlink of stale `<vec_db>.tmp` at entry | **Vector DB file boundary** | One-shot `Path.unlink(missing_ok=True)` on `<vec_path>.tmp`. Must happen BEFORE the `_rebuild_lock` check so a stale tmp from a crashed rebuild cannot be re-opened as a DB. |
| AC7 `VectorIndex.build(entries, db_path=...)` override | **Internal API boundary** | Additive kwarg; default behaviour (attribute lookup `self.db_path`) unchanged. No filesystem boundary change. |
| AC9 exponential backoff in `file_lock` | **Lock file boundary** (`<path>.lock`) | Same `.lock` sibling, same `O_CREAT\|O_EXCL` semantics. Retry schedule changes only; lock file payload / ASCII-PID convention unchanged. |
| AC11 BACKLOG.md deletion | **Doc boundary only** | `BACKLOG.md` edit. No code surface. |
| AC12/AC13 CVE re-check date bumps | **Doc boundary only** | BACKLOG.md + possibly `requirements.txt`/`CHANGELOG.md` if `pip-audit` shows a new patched version. |

**Internal-only (no boundary crossed):**

- AC2's taxonomy change stays inside `kb.errors` / `pipeline.py` module scope.
- AC7's kwarg addition is a pure signature extension.
- The `log.md` append path is NOT touched by any cycle-24 AC (evidence trail is a sidecar, not the wiki-log).

## 2. Data classification

| Data type | Flow | Sensitivity | Cycle-24 handling |
|---|---|---|---|
| `source_ref` (e.g. `raw/articles/foo.md`) | In-memory → inline rendered into `_write_wiki_page` body → written to wiki page | **Internal — path-like, but relative to `raw/`.** Never absolute. `_neutralize_pipe` backtick-wraps values containing `\|` at the `format_evidence_entry` render layer. | AC1: same string flows through the new render path as through the old `append_evidence_trail` call. Zero new exposure. |
| `action` string (e.g. `Initial extraction: entity page created`) | Constructed from `page_type` (enum-validated at config layer) | Non-sensitive — all inputs are enum values. | AC1: literal constant; safe by construction. |
| Wiki page body content (markdown) | Rendered by `_build_summary_content` / `_build_item_content` from LLM extraction | **User-controlled** (LLM sees raw source bytes) → `sanitize_extraction_field` already strips control chars + zero-width + BOM. | AC1: render order is header → body → evidence-trail section; the `## Evidence Trail` header + sentinel land at a DETERMINISTIC position AFTER the body. Adversary body content CANNOT preempt the sentinel — see T5. |
| `page_id` strings in vector DB | `entries: list[(page_id, embedding)]` → sqlite3 table `page_ids(rowid, page_id TEXT)` | **Internal** — page IDs are lowercased relative paths (`entities/foo`). | AC5: page IDs are copied verbatim into the tmp DB before rename. No new leakage path; the tmp file sits in `.data/` which is gitignored. If an attacker can read `.data/vector_index.db.tmp` they can already read `.data/vector_index.db`. |
| Vector embedding floats | `model2vec.StaticModel.encode()` output (256-dim typical) | **Non-sensitive** — lossy fingerprint, not invertible to source. | AC5: unchanged flow; just relocated to tmp path. |
| `StorageError.path` | `_update_existing_page` error path → caller logs | **Sensitive — absolute filesystem path.** Cycle-20 AC3 `__str__` redacts to `<path_hidden>` when BOTH `kind` and `path` are set. | AC2: `StorageError(kind="evidence_trail_append_failure", path=page_path)` triggers redaction (kind + path both present). T6 pins this. |

**Evidence-trail content is user-controlled via `source_ref`**: a malicious raw filename (e.g. `raw/articles/<script>alert(1)</script>.md`) would land inside the first-entry line. However: (a) `source_ref` is validated to be a relative `raw/` path at the `ingest_source` boundary (`pipeline.py:880-885`-style traversal check); (b) HTML-like content in a markdown file is rendered as-is by Obsidian but has no executable context in the pipeline; (c) the pipe character — the only format-relevant delimiter — is backtick-neutralized by `_neutralize_pipe`. The cycle-24 change does not alter any of these defenses.

**Vector DB `page_id` leak potential**: `.data/vector_index.db` contains the complete list of wiki page IDs. This is equivalent information to `wiki/index.md` which is itself committed. No new information leakage from AC5/AC6/AC7/AC8.

## 3. Authn / authz

- **File ownership / permissions.** All cycle-24 filesystem writes happen under the same process UID as the existing ingest and query paths. `_write_wiki_page` (AC1) uses `atomic_text_write` which does NOT explicitly set mode bits — mode is inherited from process umask (POSIX) or parent directory ACL (Windows/NTFS). Same for `atomic_json_write`, same for the new `<vec_db>.tmp` file. The `_write_wiki_page` exclusive branch uses `os.open(..., 0o644)` explicitly on POSIX; Windows ignores the mode parameter and inherits parent ACL. No change from cycle-20 baseline.
- **NTFS vs POSIX rename.** AC5 `os.replace` works cross-UID on POSIX (parent directory `WX` suffices). On Windows NTFS, `os.replace` requires `DELETE` on the source + `FILE_ADD_SUBDIRECTORY` on parent for the dest — mismatched ACLs (e.g. `.data/vector_index.db` created by a different user) can fail with `PermissionError [WinError 5]`. Residual: operator running `kb mcp` as a different Windows user than the one who ran the initial `kb compile` hits this. See T2.
- **Lock file privilege boundary.** `.lock` files are created with `O_CREAT|O_EXCL|O_WRONLY` and never chmod'd. The AC9 retry-schedule change does not change lock file ownership semantics. The existing `PermissionError` branch at `io.py:287-297` (cycle 3 H2) raises immediately on `EACCES` rather than spinning — this branch must remain intact through the exponential-backoff refactor (T3 residual).
- **Vector DB privilege.** `sqlite3.connect(str(self.db_path))` opens with process UID; cross-process read sharing is serialized by SQLite's internal lock. The new tmp-then-replace flow does not change this.

## 4. Logging / audit

| Change | Emits `wiki/log.md` line? | Emits `.data/ingest_log.jsonl` row? | Emits `logger.warning`? | Notes |
|---|---|---|---|---|
| AC1 inline evidence-trail render | No (no new log entry — evidence trail is its own ledger per CLAUDE.md "Evidence Trail Convention") | No | No | The log.md entry for "ingested X" is emitted by the outer `ingest_source` at the tail, unchanged. |
| AC2 `StorageError(kind="evidence_trail_append_failure")` | Conditional — `compile_wiki` per-source loop emits a WARNING if the error propagates | No (ingest JSONL is emitted at the outer boundary; stage=failure catches the exception) | Yes — inside `_update_existing_page` call site OR by the outer exception handler | The `error_summary` field in `.data/ingest_log.jsonl` passes through `sanitize_text` (cycle 18 AC13), which redacts absolute paths. Combined with the cycle-20 `StorageError.__str__` redaction, the path is double-redacted. **T6 pins this — the projection must NOT accidentally emit `path=...` through `repr()` bypassing `__str__`.** |
| AC5 atomic rename | No | No | Existing `logger.info("Vector index rebuilt: %s (%d entries)", ...)` at `embeddings.py:117,136` unchanged | The rebuild-completion log line fires AFTER successful `os.replace`. On replace failure the log line should NOT fire (implementer responsibility). |
| AC6 stale tmp unlink | No | No | Should emit `logger.info` OR `logger.debug` if a stale tmp was actually removed — surfaces the "prior crash recovery" event for operator visibility. | Optional but recommended. Not an AC requirement. |
| AC9/AC10 exponential backoff | No | No | No | Lock polling is silent today; silent tomorrow. |
| AC11/AC12/AC13 doc changes | N/A | N/A | N/A | Doc-only. |

**StorageError projection requirement (AC2).** The outer ingest path at `pipeline.py:_run_ingest_body` catches `Exception` and emits `stage=failure` with `error_summary=str(exc)`. For `StorageError(kind="evidence_trail_append_failure", path=...)`, `str(exc)` returns `"evidence_trail_append_failure: <path_hidden>"` — kind IS preserved in the summary, path is redacted. The Step-11 check must grep the failure-path log for `kind`-bearing strings, not raw `path=` substrings. See T6 below.

## 5. Enumerated threats

### T1 — Stale `<vec_db>.tmp` from crashed rebuild re-opened as partial DB

**Scenario:** A prior `rebuild_vector_index` crashed mid-`build()` before the `os.replace`. Its `<vec_db>.tmp` sits on disk with `CREATE TABLE page_ids` + `CREATE VIRTUAL TABLE vec_pages` executed but row inserts incomplete. Next operator run invokes `rebuild_vector_index`. Without AC6's unconditional unlink, the new build sees the stale tmp, (a) the new build's `sqlite3.connect(str(tmp_path))` succeeds on the partial DB, (b) the stale `DROP TABLE IF EXISTS` fires harmlessly, (c) the *new* `CREATE TABLE` collides with the partial table via `CREATE VIRTUAL TABLE vec_pages` (not `IF NOT EXISTS`), raising `sqlite3.OperationalError: table vec_pages already exists`. Worse case: if the partial tmp has residual `page_ids` rows from a different dim, the rebuild proceeds but the `os.replace` atomically swaps in a DB whose vec_pages dim column matches the new rebuild but whose `page_ids` may have orphan rowids.

**Mitigation:** AC6 — `Path(tmp_path).unlink(missing_ok=True)` AS THE FIRST STATEMENT inside `rebuild_vector_index` (before the `_rebuild_lock` acquire — or at least before any `sqlite3.connect(tmp_path)` call).

**Residual:** If two operators race `rebuild_vector_index(force=True)` concurrently, Process A unlinks tmp, Process B unlinks tmp again (no-op), both build into tmp concurrently → last-writer-wins on `os.replace`. `_rebuild_lock` (threading.Lock, in-process) does NOT synchronize cross-process. This is an existing gap NOT widened by cycle 24.

**Step-11 grep target:** `git diff src/kb/query/embeddings.py -- rebuild_vector_index | grep -E "(unlink|missing_ok)"` must show a tmp-path unlink added. Test `test_cycle24_vector_atomic_rebuild.py::test_stale_tmp_unlinked_at_entry` must exist and divergently-fail on revert.

### T2 — `os.replace` semantics on Windows NTFS

**Scenarios:**
- **(a) Cross-drive rename**: `<vec_db>.tmp` and `<vec_db>` MUST be on the same volume. Since `_vec_db_path(wiki_dir)` returns `wiki_dir.parent / ".data" / "vector_index.db"` and AC5 places the tmp at `str(vec_path) + ".tmp"`, they are siblings — cross-drive reachable only if operator symlinks `.data/` across drives (not a supported configuration).
- **(b) Target file locked by concurrent reader**: A `kb_query` holding `_conn: sqlite3.Connection` open on `<vec_db>` via `_ensure_conn` blocks `os.replace` on Windows with `PermissionError [WinError 5]`. The cached `VectorIndex._conn` stays open for the instance lifetime (`embeddings.py:219` docstring confirms). Mitigation: the EXISTING `_index_cache.pop(str(vec_path), None)` at `embeddings.py:122,134` evicts the `VectorIndex` AFTER rebuild — but the eviction happens POST-rename in the current flow. Moving it PRE-rename is not in scope for cycle 24.
- **(c) Target file open for write by a parallel rebuilder**: `_rebuild_lock` (threading.Lock) serializes in-process. Cross-process rebuilders (two `kb mcp` processes on the same wiki) can both reach `os.replace` simultaneously. NTFS `MoveFileExW(MOVEFILE_REPLACE_EXISTING)` serializes at the kernel level — the later replace wins. Both rebuilders write the same content (both derive from `load_all_pages(wiki_dir)`), so the net effect is idempotent.

**Mitigation:** AC5 — accept the Windows-cross-process residual (matches existing cycle-20 precedent). Document the "reader holding connection" footgun in the AC5 commit or in a followup.

**Step-11 grep target:** `git diff src/kb/query/embeddings.py | grep -E "os\.replace"` must show exactly one new `os.replace(tmp_path, vec_path)` call inside `rebuild_vector_index`. Test must mock-patch `os.replace` and assert it was called with the correct path pair.

### T3 — Exponential-backoff retry starvation under many waiters

**Scenario:** N waiters contend for the same `file_lock`. Under 50ms-fixed polling, each waiter polls every 50ms — N waiters collectively poll at N/50ms=20N Hz against the lock. The first waiter whose `O_CREAT|O_EXCL` beats the scheduler wins. Under exponential backoff (10ms, 20ms, 40ms, 80ms, 100ms-cap), a waiter that polled once and lost waits 20ms, then 40ms, etc. — longer total wait per waiter than under fixed 50ms for a 500ms contention window. Fairness: waiters that just entered the loop poll at 10ms while waiters deep in the loop poll at 100ms. The late-entry waiter can "skip the queue" and grab the lock ahead of a patient waiter.

**Mitigation:** AC9 caps backoff at 100ms — matches or undershoots the 50ms fixed baseline within the first 2 retries. Fairness is not a documented invariant of `file_lock` today (the lock is cooperative, not a queue). Starvation tail is bounded by `LOCK_TIMEOUT_SECONDS = 5.0`; any waiter exceeding the deadline raises `TimeoutError` or steals-if-stale.

**Residual:** Under sustained contention (e.g. `compile_wiki` with 1000 sources hitting the same `_sources.md` lock), a specific late-arriving waiter could lose N consecutive races to waiters that just entered the loop. Not a security concern; surfaces as throughput variance. Documented deferral: fair-queue lock is a future cycle *(deferred to backlog: §Phase 4.5 MEDIUM — `utils/io.py` + HIGH-structural fair-queue lock)*.

**Step-11 grep target:** `git diff src/kb/utils/io.py | grep -E "(backoff|sleep_interval|initial_interval)"` must show a new exponential-backoff computation. Test `test_cycle24_lock_backoff.py::test_sleep_sequence_is_exponential` must assert `time.sleep` call-args match `[0.01, 0.02, 0.04, 0.08, 0.1, 0.1, ...]` (or whatever the AC9 schedule lands on).

### T4 — Monkeypatch compatibility: `LOCK_POLL_INTERVAL` re-bind semantics

**Scenario:** Cycle-24 AC9 says `file_lock` MUST read `LOCK_POLL_INTERVAL` at call time (not import time). Two existing tests (`tests/test_backlog_by_file_cycle2.py:172,210`) monkeypatch the module attribute to `0.01` and expect that value to take effect. If the implementer writes:

```python
@contextmanager
def file_lock(path, timeout=None):
    poll_interval = LOCK_POLL_INTERVAL  # snapshot at function entry
    # ... retry loop uses poll_interval instead of LOCK_POLL_INTERVAL
```

This appears to work — the monkeypatch of the module attribute DOES propagate into the snapshot at function entry — BUT if the implementer instead writes the exponential-backoff local `current_interval` seeded from an INITIAL_INTERVAL constant without reading `LOCK_POLL_INTERVAL`, the monkeypatch is silently ignored. A worse variant: the implementer reads `LOCK_POLL_INTERVAL` only on the first iteration and uses doubling thereafter — a test monkeypatching to 0.01 sees the first sleep at 0.01 but subsequent sleeps at 0.02, 0.04 (ignoring the patch). Tests that only assert "at least one sleep at ~0.01" pass; tests asserting "all sleeps ≤ 0.02" silently drift.

**Mitigation:** AC9 contract states the cap is 100ms AND `LOCK_POLL_INTERVAL` compatibility is preserved. Either (a) treat `LOCK_POLL_INTERVAL` as the cap (so monkeypatching to 0.01 clamps ALL sleeps to 0.01), or (b) treat it as an overriding constant that disables backoff when set to a non-default value. Decision must be made at Step 5 design gate and baked into the regression test.

**Step-11 grep target:** `git diff src/kb/utils/io.py | grep -E "LOCK_POLL_INTERVAL"` must still show read-at-call-time semantics. Test must monkeypatch `LOCK_POLL_INTERVAL` to a non-default value, call `file_lock` under contention, and assert the spy-recorded sleep values HONOUR the monkeypatched constant per the design-gate decision. The test MUST fail when someone later refactors to a function-local constant that shadows the module attribute.

### T5 — Evidence-trail inline render vs sentinel convention

**Scenario:** An adversary who controls source content (via a compromised `raw/` file or LLM hallucination) embeds the literal sentinel `<!-- evidence-trail:begin -->` inside the page body BEFORE the `## Evidence Trail` section. Under AC1 the first write lays out:

```
---
frontmatter
---

# Title

<body content — possibly including attacker-planted sentinel here>

## Evidence Trail
<!-- evidence-trail:begin -->
- 2026-04-23 | raw/... | Initial extraction: entity page created
```

Next `_update_existing_page` call invokes `append_evidence_trail`, which runs `if SENTINEL in content: content.index(SENTINEL)` at `evidence.py:86-88`. `str.index` returns the **FIRST** occurrence — the attacker-planted sentinel in the body, NOT the real one in `## Evidence Trail`. The new evidence entry is injected into the body, not the trail section. Subsequent reviewers reading the trail see only the initial extraction entry; the new entry is silently misplaced.

**Mitigation — NEW REQUIREMENT surfaced by threat model:** The AC1 render MUST guarantee the sentinel appears exactly once AT FIRST WRITE, AND the `append_evidence_trail` sentinel-search must anchor on the `## Evidence Trail` header to defeat attacker-planted body sentinels. Options:
- (a) AC1 render ensures body content is sanitized to strip any `<!-- evidence-trail:...` substrings before writing (cycle-18 `sanitize_text` parallel).
- (b) `append_evidence_trail` is modified so the sentinel search is anchored AFTER the `## Evidence Trail` header — i.e. find the header first, then search for sentinel only within the section.

Option (b) is the safer long-term fix but widens cycle 24 scope. Option (a) is narrower but requires the implementer to add a sanitation pass to `_build_summary_content` / `_build_item_content`. **Design-gate decision required.** If neither is chosen this cycle, the threat is *(deferred to backlog: §Phase 4.5 HIGH — `ingest/evidence.py` sentinel-anchor hardening)*.

**Step-11 grep target:** Either (a) a sanitation call in `_build_summary_content` / `_build_item_content` stripping sentinel substrings, or (b) a new regex in `append_evidence_trail` anchoring sentinel search to the `## Evidence Trail` header.

### T6 — `StorageError` path-leak risk (verify cycle-20 redaction remains intact)

**Scenario:** AC2 creates `StorageError(kind="evidence_trail_append_failure", path=page_path)`. Cycle-20's `__str__` redacts to `"evidence_trail_append_failure: <path_hidden>"` when both `kind` and `path` are truthy. However: (a) if a caller uses `repr(exc)` instead of `str(exc)`, the default `Exception.__repr__` bypasses `__str__` and emits `StorageError('evidence_trail_append_failure', ...)` — which may or may not reveal path depending on Python version; (b) if a caller accesses `exc.path` directly (e.g. `logger.error("Failed: %s at %s", exc, exc.path)`), the path leaks.

**Mitigation:** Cycle-20 AC3 `__str__` redaction is preserved — no change in cycle 24. The AC2 test must assert `str(storage_err) == "evidence_trail_append_failure: <path_hidden>"` exactly.

**Residual:** Any future caller that logs `exc.path` bypasses redaction. Not a cycle-24 regression.

**Step-11 grep target:** `grep -rn "\.path" src/kb/ingest/pipeline.py` adjacent to the AC2 raise site; confirm no caller dereferences `.path` in logging. Test `test_cycle24_evidence_error_redacted.py::test_str_hides_path` must assert the redacted form.

### T7 — Same-class peers to the evidence-trail two-write race

**Audit of `pipeline.py` body-write + sidecar-append pairs** (to verify cycle 24 isn't leaving same-class bugs unfixed):

1. **`_write_wiki_page` + `append_evidence_trail`** — the cycle-24 target. After AC1 the new-page path is single-write; the update-page path remains two-write but AC2 surfaces `OSError` as `StorageError`. ✅ Covered.
2. **`_update_existing_page` body write (`atomic_text_write` at `pipeline.py:734`) + `append_evidence_trail` (`pipeline.py:568`)** — two-write ; AC2 surfaces the append-side failure but does NOT collapse into single-write. Residual: a crash between the body write and the evidence append leaves a partial-state page (body updated, trail not). Cycle-24 accepts this — the page on disk is still self-consistent (frontmatter references the new source via `source:` list), and the missing evidence entry surfaces as a lint gap on next `kb_lint`. *(deferred to backlog: §Phase 4.5 HIGH — `ingest/pipeline.py` `_update_existing_page` single-write consolidation)*.
3. **`_write_wiki_page` exclusive branch + `append_evidence_trail` (outside lock)** (`pipeline.py:391-395`) — same two-write shape. AC1 applies only to the `exclusive=False` path per the requirements reading; the `exclusive=True` branch writes body via `os.open(O_EXCL)` then calls `append_evidence_trail` separately. **Design-gate must confirm AC1 also applies to the exclusive branch** OR explicitly scope to non-exclusive. *(deferred to backlog if not addressed this cycle: §Phase 4.5 HIGH — `_write_wiki_page` exclusive-branch evidence collapse)*.
4. **`_update_existing_page` → `_sources.md` write + `index.md` write** (`pipeline.py:740-808`) — both go through `atomic_text_write` sequentially, no sidecar-append pattern. Cycle-18 AC14's `_write_index_files` helper gives each an independent try/except. Not a same-class bug; no action needed.
5. **`ingest_source` body writes + `.data/ingest_log.jsonl` append** — JSONL append is best-effort with `OSError` swallowed to `logger.warning` (cycle-18 Q8). Not a same-class bug — the JSONL is explicitly allowed to be missing entries without blocking ingest.
6. **`refine_page` page write + `refine_history.jsonl` append** (`review/refiner.py`) — already single-lock (cycle 19 AC8/AC9/AC10 two-phase write). Pending row written BEFORE page body, flipped to applied/failed under same lock. Not a same-class bug.
7. **`append_evidence_trail` internal read + write** — already atomic within `file_lock(page_path)`. Not a two-write.

**Step-11 grep target:** `git log --oneline src/kb/ingest/pipeline.py` for cycle 24 commits must NOT touch `_update_existing_page`'s body-write + evidence-append sequence beyond AC2's error surfacing (confirming scope discipline). Any expansion requires an AC addition.

### T8 — CVE late-arrival during cycle wall-clock span

**Scenario:** A new CVE lands in `pip-audit` output between Step 2 (this threat model) and Step 12 (docs). Cycle-22 L4 ("advisories can arrive mid-cycle") requires a Step-11.5 re-audit. AC12/AC13 bump the diskcache + ragas re-check dates to 2026-04-23 — but the cycle's wall-clock span may extend past that date.

**Mitigation:** Per AC12/AC13 contingency clauses: if `pip-audit` reports non-empty `fix_versions` for either CVE during the cycle, a Step-11.5 `fix(deps)` commit bumps `requirements.txt` and the BACKLOG entry moves to CHANGELOG. Step 11 Codex verification must re-run `pip-audit` — not rely on this threat model's snapshot.

**Step-11 grep target:** Step-11 Codex must execute `pip-audit --strict --format=json` and diff against the Step-2 baseline. New CVE → bump commit. Preserved CVE → date bump in BACKLOG.

### T9 — Vector index cache pinning old DB after atomic replace

**Scenario:** AC5 performs `os.replace(tmp_path, vec_path)`. An existing `VectorIndex` instance in `_index_cache` has `_conn` pointing at the pre-replace file handle. On POSIX the old inode stays alive (unlinked but held open) → queries return old results silently. On Windows the `os.replace` *fails* because the old fd locks the file → rebuild bubbles up `PermissionError`.

**Mitigation:** Existing code already does `_index_cache.pop(str(vec_path), None)` POST-rebuild at `embeddings.py:134`. That pop must run BEFORE `os.replace` on Windows to release the lock. On POSIX it can run after — but consistency argues for before.

**Residual:** If the implementer keeps the pop AFTER `os.replace` (current line order), Windows rebuild fails mid-cycle and leaves the production DB unreplaced + `<vec_db>.tmp` on disk. AC6 catches this on next run but the current run surfaces an unhelpful error.

**Step-11 grep target:** `git diff src/kb/query/embeddings.py | grep -E "(_index_cache.pop|os\.replace)"` — the pop MUST be ordered before replace on the refactored flow OR the Windows PermissionError must be caught and translated to a clear "close existing connection first" error.

### T10 — AC7 default kwarg introduces call-time `db_path` attribute drift

**Scenario:** AC7 adds `db_path=None` to `VectorIndex.build`. Default behaviour: when `db_path is None`, use `self.db_path`. If the implementer codes this as:

```python
def build(self, entries, db_path=None):
    db_path = db_path or self.db_path
    conn = sqlite3.connect(str(db_path))
```

A caller passing `db_path=Path("")` or `db_path=False`-equivalent gets `self.db_path` silently — a subtle override bypass. Use `db_path if db_path is not None else self.db_path` instead.

**Mitigation:** AC7 signature test + behavioral test together pin the semantics. Test `test_cycle24_vector_build_override.py::test_build_respects_db_path_override` must pass an explicit `db_path=<tmp_path>` and assert the file appears at that path.

**Step-11 grep target:** `git diff src/kb/query/embeddings.py | grep -E "db_path is not None"` — the override comparison must use `is not None`, not truthy-coalesce.

## 6. Deferred-to-BACKLOG items

Every "out of scope" item below emits a specific deferred-to-backlog tag per cycle-23 L3 rule ("threat-model deferred-promises are load-bearing contracts"). Step 11 Codex must grep `BACKLOG.md` for each tag and confirm a matching entry exists.

| Tag | Source in this doc | BACKLOG.md section |
|---|---|---|
| *(deferred to backlog: §Phase 4.5 MEDIUM — `utils/io.py` fair-queue lock)* | T3 residual | §Phase 4.5 MEDIUM — `utils/io.py` entry. **NEW** — must be added if not present. |
| *(deferred to backlog: §Phase 4.5 HIGH — `ingest/evidence.py` sentinel-anchor hardening)* | T5 option (b) if not chosen this cycle | §Phase 4.5 HIGH — `ingest/evidence.py` entry. **NEW** if design-gate picks option (a) only. |
| *(deferred to backlog: §Phase 4.5 HIGH — `ingest/pipeline.py` `_update_existing_page` single-write consolidation)* | T7 item 2 | §Phase 4.5 HIGH — `ingest/pipeline.py` body+evidence pair entry. **UPDATE** existing line 147 to narrow scope (this cycle's AC2 partially addressed it). |
| *(deferred to backlog: §Phase 4.5 HIGH — `_write_wiki_page` exclusive-branch evidence collapse)* | T7 item 3 if AC1 scopes to non-exclusive | §Phase 4.5 HIGH — `ingest/pipeline.py` entry. **NEW** if design-gate leaves exclusive branch untouched. |
| *(deferred to backlog: §Phase 4.5 HIGH — vector-index lifecycle sub-items 2/3/4)* | Non-goals list from requirements (cold-load, dim-mismatch auto-rebuild, `_index_cache` cross-thread) | §Phase 4.5 HIGH-Deferred `query/embeddings.py` vector-index lifecycle entry. Already in BACKLOG line 109 — keep unchanged. |
| *(deferred to backlog: §Phase 4.5 HIGH — M3 JSONL migration)* | Non-goals: full `atomic_json_write` → append-only JSONL | §Phase 4.5 HIGH — existing `utils/io.py` atomic_json_write entry on line 127. Keep. |
| *(deferred to backlog: Phase 5 pre-merge items)* | Non-goals: `capture.py` two-pass, `_PROMPT_TEMPLATE` relocation, `CAPTURES_DIR` contradiction | §Phase 5 pre-merge. Keep untouched per user instruction. |
| *(deferred to backlog: §Phase 4.5 M2 per-source rollback)* | Non-goals: receipt-file mechanism | §Phase 4.5 MEDIUM M2 entry. Keep untouched. |
| *(deferred to backlog: §Phase 4.5 M10 full IndexWriter)* | Non-goals: extending `_write_index_files` to manifest+log+contradictions | §Phase 4.5 MEDIUM M10 entry. Keep untouched. |
| *(deferred to backlog: HIGH structural items)* | Non-goals: naming inversion, state-store fan-out, shared graph cache, async MCP, tests freeze-and-fold, conftest leak surface | §Phase 4.5 HIGH-structural entries. Keep untouched. |

## 7. Step-11 verification checklist

Each threat T1..T10 has exactly one grep-verifiable assertion below. Step-11 Codex must execute each against the cycle-24 branch diff.

| # | Threat | Grep/test assertion | Pass criterion |
|---|---|---|---|
| 1 | T1 stale tmp re-open | `git show <cycle-24-commit>:src/kb/query/embeddings.py \| grep -nE "(unlink.*missing_ok\|unlink.*tmp_path\|\.tmp\.*unlink)" ; pytest tests/test_cycle24_vector_atomic_rebuild.py::test_stale_tmp_unlinked_at_entry -v` | Greps match AND test passes AND test divergently-fails if the unlink line is reverted (`git stash` the unlink, re-run, confirm FAIL). |
| 2 | T2 os.replace Windows NTFS | `git show <commit>:src/kb/query/embeddings.py \| grep -nE "os\.replace\("` + test mock-spy on `os.replace` asserting call-args `(tmp_path, vec_path)`. | Exactly one new `os.replace` in `rebuild_vector_index`. Spy test passes. |
| 3 | T3 backoff starvation | `git show <commit>:src/kb/utils/io.py \| grep -nE "(INITIAL_POLL_INTERVAL\|backoff\|min\(.*100)"` + test asserts sleep sequence ≤ cap. | Exponential schedule present, capped at 0.1. No sleep > 0.1. |
| 4 | T4 LOCK_POLL_INTERVAL monkeypatch compat | `pytest tests/test_backlog_by_file_cycle2.py::test_file_lock_stale_steal -v` (existing test) + new `tests/test_cycle24_lock_backoff.py::test_module_attribute_monkeypatch_honored` | Both tests pass. The new test monkeypatches `LOCK_POLL_INTERVAL=0.001`, runs a contended acquire, and asserts ALL `time.sleep` calls ≤ 0.001 (or per design-gate decision, ≤ cap). |
| 5 | T5 sentinel injection via body | `grep -rn "<!-- evidence-trail:" src/kb/ingest/evidence.py src/kb/ingest/pipeline.py` + test seeds a page body containing the sentinel literal, triggers ingest, asserts `append_evidence_trail` places new entry under the **real** `## Evidence Trail` header (not the attacker-planted sentinel). | Test passes. If design-gate chose option (a) sanitation, confirm sanitation call in `_build_summary_content` / `_build_item_content`. If option (b), confirm anchored-search regex in `append_evidence_trail`. |
| 6 | T6 StorageError path-leak | `pytest tests/test_cycle24_evidence_error_redacted.py::test_str_hides_path -v` + `grep -rn "\.path" src/kb/ingest/pipeline.py` around the AC2 raise site. | Test asserts `str(err) == "evidence_trail_append_failure: <path_hidden>"`. No `logger.*%s.*exc\.path` patterns adjacent to the raise. |
| 7 | T7 same-class peer audit | `git diff cycle-24 -- src/kb/ingest/pipeline.py` for any unexpected changes OUTSIDE `_write_wiki_page` / `_update_existing_page`. | Diff scope limited to the declared functions. If the design-gate expanded scope to the exclusive branch, an AC1a must exist. |
| 8 | T8 CVE late-arrival | `pip-audit --strict --format=json > /tmp/cycle-24-cve-post.json ; diff /tmp/cycle-24-cve-baseline.json /tmp/cycle-24-cve-post.json` | Diff empty OR new CVE produces a Step-11.5 `fix(deps)` commit. |
| 9 | T9 cache pinning | `git show <commit>:src/kb/query/embeddings.py \| grep -nE "_index_cache\.pop\|os\.replace" ; awk` ordering check. | `_index_cache.pop` appears BEFORE `os.replace` in the control flow (OR a fresh ordering-test exists to pin it). |
| 10 | T10 AC7 default kwarg | `git show <commit>:src/kb/query/embeddings.py \| grep -nE "db_path is not None\|db_path is None"` + signature test `inspect.signature(VectorIndex.build).parameters['db_path'].default is None`. | Comparison uses `is not None`. Signature test passes. |

**Deferred-promise grep (per cycle-23 L3):**

```
for tag in \
  "Phase 4.5 MEDIUM.*fair-queue" \
  "Phase 4.5 HIGH.*sentinel-anchor" \
  "Phase 4.5 HIGH.*_update_existing_page.*single-write" \
  "Phase 4.5 HIGH.*exclusive-branch evidence" \
  "Phase 4.5 HIGH.*vector-index lifecycle" \
  "Phase 4.5 HIGH.*JSONL migration" \
  "Phase 5 pre-merge" ; do
    grep -q -E "$tag" BACKLOG.md || echo "MISSING: $tag"
done
```

Expected output: empty. Any `MISSING:` line is a Step-11 blocker — each deferred-to-backlog tag in §6 must have a corresponding BACKLOG entry OR a deliberate scope note in the PR description.
