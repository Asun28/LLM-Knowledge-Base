# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

> **High-level index.** Keep this file brief and newest first. Each cycle gets compact Items / Tests / Scope / Detail fields and points to the full archive in [CHANGELOG-history.md](CHANGELOG-history.md).
> Cross-reference: [BACKLOG.md](BACKLOG.md) tracks open work; resolved items are deleted from BACKLOG once shipped here.

<!-- Entry rule — newest first; keep this file brief and move details to CHANGELOG-history.md.
#### YYYY-MM-DD — cycle N
- Items: <N> AC / <M> src / <K> commits
- Tests: A → B (+Δ)
- Scope:
  <one-sentence scope only>
- Detail: [history archive](CHANGELOG-history.md#<anchor>)

Commit-count convention (codified cycle 28 AC8 per cycle-26 L1 skill patch):
on the feature-branch squash-merge flow, the reported <K> equals pre-doc-update
branch commits + 1 for the landing doc-update that contains this changelog
line (self-referential). If R1/R2 PR review triggers fix commits, increment
<K> atomically with each fix commit and re-check `git log --oneline main..HEAD`
before push.
-->

## [Unreleased]

### Quick Reference

Newest first. `CHANGELOG.md` is the compact index; full detail lives in [CHANGELOG-history.md](CHANGELOG-history.md).

- **Cycle 89 (barrier tri-state — the shared root cause of two cycle-88 review findings)** — Items: 2 ACs, 2 src files + 1 new test file. Cycle 88's review produced the same finding twice from two model families approaching from opposite ends: R1 DeepSeek said the Windows rollback claims a durability it does not have, R2 Codex said the POSIX tolerated-errno path does the same. Both proposed having callers REPORT a missing barrier, and neither noticed that `_fsync_parent_dir` returned `None` in all three cases — the information needed to report it did not exist. Cycle 88 rejected both remedies for consistency and filed the root cause; this cycle closes it. **AC01** `_fsync_parent_dir` returns `BarrierResult.{FLUSHED,UNSUPPORTED,SKIPPED_PLATFORM}`; a genuine storage failure (`EIO`/`ENOSPC`) still RAISES, so there are three values and not four. `_dir_fsync_supported()` is added as the platform seam per C86-L3 — a `skipif`-guarded branch is untested on whichever platform the developer is not using, which is how the Windows gap survived cycle 86; it is kept separate from `_use_windows_write_through()` because the two answer different questions and could diverge. Additive: `durable_replace` and `durable_rename` ignore the return value and are behaviourally unchanged, pinned by test. **AC02** `capture._finish_rollback` consumes it, and this is where the third value earns its keep: `UNSUPPORTED` is unusual and filesystem-specific so it emits `BARRIER_UNSUPPORTED_MARKER`, while `SKIPPED_PLATFORM` is constant on Windows and stays SILENT — surfacing it would ride along on every capture failure and train the reader to ignore it, the crying-wolf failure cycle 88 rejected twice. A bool could not express that split. The note is a SEPARATE suffix from `ROLLBACK_INCOMPLETE_MARKER` and both can appear on one error: they make different claims ("state UNKNOWN, go look" vs "state known, not yet durable"), and merging them would undo the cycle-88 decision. Tests: 3537 → 3560 (+24 incl. 1 platform-skipped); the AC01 tests drive BOTH platform branches on either OS via the new seam, cutting 11 skips to 1. Scope: closes the API half of the filed residual; the remaining half is that Windows has no directory-flush primitive at all, rewritten in BACKLOG and likely won't-fix. Detail: [history archive](CHANGELOG-history.md#2026-07-29--cycle-89-barrier-tri-state).

- **Cycle 88 (honest durability & rollback reporting — 3 cycle-87 review residuals)** — Items: 3 ACs, 2 src files + 1 new test file. All three share one shape: the code takes a correct ACTION, then tells the caller something the filesystem does not support. None is data loss — the bytes on disk are right and a retry is idempotent in every case — which is exactly why they matter, since a caller that cannot trust the report cannot automate the retry. **AC01** `review/refiner.py` recorded a revision `failed` when only the durability barrier failed, contradicting a page that already held `new_text`. `RenameCompletedBarrierError` is now caught BEFORE the broad `except OSError` and records `status: applied` + `durable: false` + `durability_error`; `refine_page` returns `durable: False` + a `warning` with `updated: True` and NO `error` key, so callers branching on `error` do not treat a completed write as a refusal. `status` ("did it land?") and `durable` ("will it survive power loss?") stay separate axes rather than adding a fourth status value, so `sweep_stale_pending`'s pending-only logic and every existing `status` consumer are untouched; the two fields are written ONLY on the not-durable path, per the `get_prompt_version` legacy-default convention. **Catch order is load-bearing** — the barrier type subclasses `OSError`, the same hazard as `ValueDomainError` before `TierBoundaryError` (cycle 86) — and two tests pin it from both sides so no ordering passes both. `durability_error` is bound before the lock span so a future early exit cannot make it an `UnboundLocalError`. **AC02** `capture.py`'s all-or-nothing rollback swallowed every unlink `OSError` with a warning and took no barrier, so `([], error)` conflated "nothing was written" with "the batch state is unknown". Both rollback helpers now RETURN the paths whose unlink failed, the cycle-87 completed-promote orphan unlink feeds the same list (that unlink could itself fail, so the exact orphan cycle 87 set out to prevent could still survive unreported), and `_finish_rollback` adds one directory fsync after the last deletion plus a `ROLLBACK_INCOMPLETE_MARKER` suffix naming the surviving paths. Two guards against over-reporting: the barrier is `attempted`-gated so a rollback that deleted nothing cannot manufacture an indeterminacy report from an fsync failure, and a clean rollback still returns the plain error. **Honest scope: the barrier half is POSIX-only** — `_fsync_parent_dir` no-ops on `nt`, and there is no cheap Win32 equivalent (`DeleteFileW` has no write-through flag; `FlushFileBuffers` is unsupported on a directory handle), so the docstring says so rather than implying a cross-platform guarantee, and the residual is filed in BACKLOG. The cross-platform indeterminacy report is the more load-bearing half. **AC03** Windows reparse-point coverage for cycle-87's no-follow stat, which was pinned on POSIX symlinks only; junctions (`mklink /J`) need no privileges — unlike symlinks, which fail `WinError 1314` — so they are the reachable probe on the primary dev platform. Adds helper-level junction rejection, the true TOCTOU peer (junction swapped in AFTER the containment check), a hardlink ACCEPTANCE test pinning the boundary against a future `st_nlink == 1` tightening, and the documented ancestor-swap residual as an executable statement. **One expectation was corrected by the code, not the reverse** — a junction left in place under `raw/` is caught by the containment check as an `error` and never stat'd (the T1 no-oracle rule), stronger than the `warning` the test first asserted. Tests: 3520 → 3537 (+17). Scope: reporting accuracy for durability and rollback outcomes; closes all 3 residual MEDIUMs filed by cycle-87's own review. Detail: [history archive](CHANGELOG-history.md#2026-07-29--cycle-88-honest-durability--rollback-reporting).

- **Cycle 87 (durability & containment completion — 3 cycle-86 review follow-ons + 1 stale-backlog deletion)** — Items: 3 ACs, 4 src files + 1 new test file. **AC01** Windows had NO rename-durability barrier: `_fsync_parent_dir` returns immediately when `os.name == "nt"`, and its docstring claimed `os.replace`'s underlying `MoveFileEx` covered the gap. It does not — CPython passes only `MOVEFILE_REPLACE_EXISTING`, never `MOVEFILE_WRITE_THROUGH` — so cycle-86 AC04 hardened only the CI platform while leaving the PRIMARY development platform with no power-loss guarantee at all. New `durable_replace(tmp, dest)` is now the single promote path, which is the other half of the fix: the gap kept reappearing because each site rolled its own `os.replace`. POSIX keeps rename-then-fsync-the-parent-directory; Windows uses `MoveFileExW` with `MOVEFILE_WRITE_THROUGH` (`MOVEFILE_COPY_ALLOWED` deliberately omitted — it would let the move degrade into a non-atomic cross-volume copy+delete). **Two shapes were rejected in design, both reviewers agreeing independently:** re-opening `dest` after the rename and fsync-ing that handle is durability theatre, because `FlushFileBuffers` flushes the file's own data and MFT record but not the parent directory index that carries the name (and it races a concurrent unlink of `dest`); and falling back to `os.replace` when the write-through move fails is worse than the original bug, since it converts a durability failure into a successful-looking write. The ctypes surface is declared explicitly (`WinDLL(..., use_last_error=True)` + `wintypes` argtypes/restype + `ctypes.WinError`) — `use_last_error` is load-bearing, since a bare `GetLastError()` lookup can be clobbered by an intervening call. **AC02** `capture.py:694` and `query/embeddings.py:363` bypassed both atomic-write helpers with a bare `os.replace`, so they had no barrier whatsoever; power loss could surface a reported capture as missing or empty, or silently restore the previous vector index while `rebuild_vector_index` returned True. Both now promote through `durable_replace`, and capture additionally flushes the body — it used `write_text`, leaving content in the page cache, so the promote could win the race even once the rename was durable. The backlog preferred routing both through `atomic_text_write`/`atomic_json_write`; neither fits (capture promotes into a path already reserved by an `O_EXCL` two-pass protocol, and the vector index is a binary sqlite file built by another writer), and sharing one promote primitive satisfies the actual intent, which was to stop adding bespoke write paths. **AC03** `evidence_resolvable.py` decided containment against a resolved path and then ran a separate `Path.is_file()`; replacing the final component under `raw/` with a link pointing outside made that stat follow it, so lint output became a filesystem-existence oracle for host paths — the same T1 boundary containment exists to hold. `os.lstat` never follows a final-component symlink, so the answer describes the entry containment accepted. **DESIGN-AMEND vs the backlog's suggested `_open_no_follow` + `fstat`:** `lstat` opens nothing (no descriptor to leak, no side effects on FIFOs or device nodes), needs no platform branch, and avoids `_open_no_follow` misreading a plain `ENOENT` as "O_NOFOLLOW unsupported" and warning once per process — which a check that routinely meets missing files would trip constantly. Scope is stated honestly in the docstring: this closes the FINAL-component swap, not an ancestor-directory swap, because both shapes re-walk ancestors and only `openat2(RESOLVE_BENEATH)` would (Linux 5.6+). **AC04 was DROPPED as stale** — the backlog claimed the two contradiction-concurrency tests "rely on wall-clock thread overlap rather than a deterministic barrier", but both already use `threading.Barrier(2)` plus widened lock timeouts (shipped cycle 84, PR #127), and cycle 85 added `test_removing_the_lock_loses_a_write` as a falsifiability meta-test. Entry deleted, no code change. **Platform branches are now driven by faked-platform tests rather than `skipif` (C86-L3)** — a `skipif`-guarded branch holding a decision rule is untested on whichever platform the developer is not using, which is exactly how the Windows gap survived cycle 86. `_use_windows_write_through()` is the seam; faking `os.name` directly is not viable because `pathlib.Path` selects its flavour from it, so every `Path(...)` in the call stack raises. **Cycle-86's four AC04 tests are now pinned to the POSIX branch explicitly** — they previously passed on Windows only because the no-op helper was still *called* there, the accident that let the gap survive. **Nine stale promote seams retargeted** across 6 test files: `Path.replace` and `os.replace` fault-injectors no longer intercept on Windows, so `durable_replace` is the only platform-agnostic seam. **Revert-sensitivity confirmed per test, not assumed:** forcing the no-follow helper False must flip the lint verdict (impossible if `.is_file()` is still called), the Windows branch must call `MoveFileExW` with flags 9 and must NOT call `os.replace` or `_fsync_parent_dir`, a failed move must raise with no fallback, and capture's content flush must be ordered before its promote.  **R1 (Codex) found 1 MAJOR that this cycle itself introduced, 1 MAJOR refuting a scope-out, and 3 MINORs; 4 fixed in-cycle, 1 filed.** **MAJOR-1** — `os.replace` was atomic in the sense callers relied on (raise XOR rename); `durable_replace` broke that, because the POSIX barrier runs AFTER the rename and cycle-86 made it raise on `EIO`. `capture._write_item_files` records the item only after the promote returns, so a barrier failure left the final on disk, absent from `written`, with its temp already renamed away — neither rollback touched it, and an orphan `<slug>.md` survived a capture reported as `([], error)`, silently breaking an explicit all-or-nothing contract. New `RenameCompletedBarrierError(OSError)` marks the rename-completed-barrier-failed case (subclassing `OSError` so every legacy `except OSError` still catches); capture unlinks the final on it. **MAJOR-2** — the PR had scoped out `orchestrator.py`'s proposal-consumption rename as "idempotent re-consumption". R1 refuted that with the downstream trace: a reverted rename makes the next run reparse the proposals AND `persister.py` write ANOTHER raw article under a fresh run id — duplicated content, not a no-op. Brought in scope per the same-class-peer rule that weak scope-out justifications lose. **MINOR-3** — `wiki_log.rotate_if_oversized` was a third bare-rename peer the concept-grep missed; also routed through the barrier. **MINOR-4** — the faked-platform tests stub `_resolve_move_file_ex_w`, so a wrong `argtypes`/`restype` or a dropped `use_last_error` left them all green; two Windows-only tests now assert the real ABI declaration and drive a genuine create/overwrite/failure cycle through kernel32, which ubuntu CI can never do. **MINOR-5 filed, not fixed** — R1 agreed the flagged AC03 tests should be RETAINED as non-regression guards and wanted ADDED Windows reparse coverage; deferred because unprivileged symlink creation fails on the dev machine (`WinError 1314`), so the test would skip on the only platform that could run it. **R1 DeepSeek's 4 findings were all rejected with citations** — the claimed temp-file leak is contradicted by the unconditional `_cleanup_tmp` at io.py:401/429 (only the `os.close` is gated on `fd_transferred`), one cited a test name absent from the repo, and the claimed legitimate-symlink regression misses that `_resolve_evidence_ref` returns the RESOLVED path; that last one is now pinned by a test rather than left as an argument. **CI caught a bad test of mine**: the POSIX symlink test let the real resolver run, whose `.resolve()` follows the link, so containment rejected it upstream and the stat under test was never reached — it looked green locally only because Windows skips it. | BACKLOG: 4 entries deleted (3 shipped, 1 stale) + 3 filed (Windows reparse coverage, capture rollback indeterminacy, refiner not-durable state). | Tests: 3541 → 3565 collected (+24 in `tests/test_cycle87_durability_containment.py`); full Windows local suite green; ruff clean. | Files: 238 → 239 test files. | src/kb/ changes: 6 files (`utils/io.py`, `capture.py`, `query/embeddings.py`, `lint/checks/evidence_resolvable.py`, `lint/augment/orchestrator.py`, `utils/wiki_log.py`). | Detail: see CHANGELOG-history.md cycle-87.
- **Cycle 86 (validation & ordering correctness — 2 Phase-5 items + 2 Phase-4.5 defects + 1 stale-backlog deletion)** — Items: 5 ACs, 8 src files (1 NEW module + 7 modified) + 1 new test file. **AC01** NEW `lint/checks/evidence_resolvable.py` + runner registration: every file-shaped `source:` frontmatter entry must resolve to a real file under `raw/`. Raw-source-side peer of `dead_links.py` (wikilink targets only) and reverse direction of `check_source_coverage` (raw files nothing references) — a page could pass both while its whole provenance chain dangled. **Severity is split deliberately:** a ref that resolves under `raw/` but finds no file is a `warning`, because a raw source can legitimately be pruned after ingest and an `error` would flip `kb lint`'s exit code on every repo that ever cleaned one up (this surfaced at Step 9 when an existing augment-CLI test began failing — recorded as a DESIGN-AMEND rather than silently narrowed); a ref that does not resolve under `raw/` at all is an `error`, since no legitimate workflow produces one. **Out-of-tree refs are reported WITHOUT being stat'd** — frontmatter is LLM-written, so probing the path would turn lint output into a filesystem-existence oracle (T1); containment is checked before any filesystem access and a `Path.is_file` spy pins it. Per-page ref cap (200) bounds the work and reports its own truncation. **AC02** `_validate_tier_boundary` gains `allowed_values`, closing the VALUE domain its cycle-73/74 checks left open: those cover the KEY domain plus shape bounds, so `{"action": "exfiltrate"}` — legal keys, legal shape — passed through untouched, and the permitted-action enum lived only in JSON-schema text plus a hand-rolled `if` that every new call site had to re-implement. New `ValueDomainError(TierBoundaryError)` keeps legacy `except TierBoundaryError` / `except ValidationError` sites catching by inheritance while letting `proposer.py` split-catch and fail closed with the forensically distinct `action_not_in_vocabulary:` reason (separable in an audit from `tier_boundary_rejected:`); catch ordering is load-bearing and commented as such. Vocabulary derived from `_PROPOSER_SCHEMA`'s own `enum`, never from the response (T5 carried over unchanged); the now-dead `if action != "propose"` re-check is removed rather than left to drift. Scope is root-level keys only — `capture.py`'s nested `kind`/`confidence` enums would need a path mini-language inside a security validator, so they are FILED in BACKLOG, not built speculatively. **AC03** the human `Ingested …` line moved out of `_run_ingest_body` step 7 (where it ran BEFORE `_commit_ingest_manifest`) into `ingest_source`, after the commit and after the `stage=success` JSONL row. Previously a failed commit left `wiki/log.md` asserting a successful ingest the manifest never recorded, so the human trail contradicted `find_changed_sources`. Extracted as `_append_ingest_success_log` so ordering is spy-testable at a named symbol; `_run_ingest_body` is now a pure worker with no audit emissions (same envelope rule as the cycle-83 manifest move). Second half: a `committed` flag splits pre-commit failure from post-commit interruption — previously ANY exception reaching the handler emitted `stage=failure`, including an async KeyboardInterrupt landing after the commit, producing a failure record for an ingest whose pages and manifest entry are both durable. Post-commit the handler emits the terminal success row if the tail missed it and re-raises unchanged; if the success emission is ITSELF what failed, the retry is swallowed with a warning so telemetry can never replace the caller's exception. Genuine pre-commit failures still emit `failure`. **AC04** new `_fsync_parent_dir` called from BOTH `atomic_json_write` and `_atomic_text_write_replace`: `_flush_and_fsync` makes the temp file's contents durable but not the RENAME, so on ext4 `data=writeback` / XFS / several network filesystems a power loss just after `os.replace` can revert a completed write. Best-effort with a WARNING, unlike `_flush_and_fsync` which must raise — a content-fsync failure is corruption, a dir-fsync failure costs a re-ingest, and making it fatal would break writes that work today on filesystems rejecting fsync on a directory handle. The backlog named only the JSON path; the text path is identical in shape and carries far more traffic (every wiki page, evidence append, log line), so hardening only the rarer surface would have been arbitrary. No-op on Windows, where rename durability comes from `MoveFileEx`. **AC05** the Phase-4.5 MEDIUM entry claiming `compiler.py`'s `load_manifest` read sites "remain unguarded" is DELETED as stale — cycle 84 shipped the `isinstance(stored, str)` guard at `compiler.py:185`; all five read sites were re-checked (185 guards 205 via the `elif` chain, 218/460/588 coerce with `str(v)`, 230 is a plain `!=`) and a behavioural test now pins that a corrupt non-string value classifies the source as changed instead of raising `AttributeError`. **Revert-sensitivity confirmed by mutation, not assumed:** dropping `allowed_values`, neutering the `committed` flag, removing the dir-fsync call, reverting the severity split, and moving the human log back to its pre-cycle-86 position each fail their corresponding tests. **Codex PR review (R1) found 2 BLOCKERs + 4 MAJORs; all fixed in-cycle.** **BLOCKER-1** — AC01 checked containment AFTER `Path.resolve()`, but resolve IS filesystem access: a UNC ref (`\\attacker.invalid\share\probe`) initiates SMB/DNS/authentication traffic during resolution, so the probe fires before the check that was supposed to prevent it. Hostile refs (UNC, drive-absolute, POSIX-absolute, and UNC smuggled behind the `raw/` strip) are now rejected LEXICALLY, before any filesystem call. **BLOCKER-2 (pre-existing, not introduced here)** — `review/context.py:75` confined source refs to the PROJECT ROOT and applied the `raw/` containment check ONLY when the ref was a symlink, so a plain `source: .env` was read at `context.py:111` and rendered back to the model through `lint/semantic.py` and `mcp/quality.py:kb_refine_page`. Frontmatter is LLM-written and user-editable, making that a concrete secret-disclosure path; raw-containment now applies to EVERY ref regardless of spelling, with the `is_link` flag retained only to distinguish the two cases in the log. **MAJOR-1/2** — `committed = True` and `success_emitted = True` are both set AFTER the operations they describe, so an interrupt in either gap produced a `failure` row for a durably-committed ingest, or a SECOND success row for one request_id. Both now confirm against the authority (`_manifest_records_commit` re-reads `.data/hashes.json`; `_jsonl_has_terminal_row` re-reads the JSONL) instead of trusting an in-memory flag; both helpers are non-raising so the audit path can never replace the caller's original exception. **MAJOR-4** — `_fsync_parent_dir` swallowed every `OSError`, including `EIO`/`ENOSPC`. Silence reads as durability, so `_commit_ingest_manifest` would declare an ingest committed whose manifest a power loss can still revert, with success telemetry already written. Only `_FSYNC_UNSUPPORTED_ERRNOS` (EINVAL/ENOTSUP/EPERM/…) are now tolerated; genuine storage failures RAISE (an amendment to design Q5, which had specified blanket swallowing). Review also corrected three tests that could not fail against a revert: the xfail called the validator directly and supplied `allowed_values` itself (so dropping it at the proposer call site would not have tripped it — now driven through `_propose_urls`), the AC05 test never read `BACKLOG.md`, and the text-path fsync ordering was untested. **MAJOR-3 deferred with its analysis** (Windows has no rename-durability barrier at all — `os.replace` does not request `MOVEFILE_WRITE_THROUGH`), along with the `capture.py`/`embeddings.py` bare-`os.replace` peers and the inherent `.is_file()` TOCTOU. | BACKLOG: 4 entries deleted (2 Phase-5 HIGH LEVERAGE shipped, 2 Phase-4.5 MEDIUM shipped, 1 stale) + 4 new entries filed (nested-enum scope-out, Windows durability gap, rename peers, TOCTOU). | Tests: 3479 → 3541 collected (+62 in `tests/test_cycle86_validation_ordering.py`); full Windows local suite 3491 passed / 26 skipped / 17 xfailed; ruff clean. | Files: 237 → 238 test files. | src/kb/ changes: 8 files (`lint/checks/evidence_resolvable.py` NEW, `lint/checks/__init__.py`, `lint/runner.py`, `lint/augment/tier_boundary.py`, `lint/augment/proposer.py`, `errors.py`, `ingest/pipeline.py`, `utils/io.py`). | Detail: see CHANGELOG-history.md cycle-86.
- **Cycle 85 (contradiction-drop visibility + lock-test falsifiability)** — Items: 1 src file + 1 test file. **Dropped contradictions were untraceable.** `_persist_contradictions` caught every write failure and logged `"Failed to write contradictions.md: <err>"` — which named neither the source nor how many claims were discarded, so an operator could see that something failed but not what was lost or which source to re-run. (My cycle-84 backlog entry overstated this as "no error surfaced"; there was a WARNING, just not an actionable one — corrected here.) The message now names the source ref and claim count and says DROPPED explicitly. **A lock timeout is now retried once** on a longer deadline (`_CONTRADICTION_RETRY_LOCK_TIMEOUT = 15.0s`), since a timeout means another ingest is mid-append and is transient; other failures are NOT retried, because retrying a permission error or a full disk only doubles the wait. The locked read-modify-write is extracted to `_write_contradiction_block` so the retry loop stays readable — read and write remain inside one locked span (the H3 invariant). **Lock tests are now falsifiable.** The existing no-lost-write tests only failed against a REMOVED lock if the two threads' RMW windows happened to overlap, which a barrier aligning thread *starts* does not guarantee — so "they pass" was weak evidence the lock was load-bearing. New `test_removing_the_lock_loses_a_write` neuters `file_lock` and FORCES the overlap (alpha is held at its write until beta has fully committed, so alpha's stale read clobbers beta), then asserts a write really is lost. If it ever stops losing a write, the sibling tests have stopped being able to detect a broken lock. BACKLOG: both cycle-84 review MINORs deleted (resolved). | Tests: 3435 → 3439 collected (+4); full suite 3439 passed / 24 skipped / 16 xfailed; ruff clean. | src/kb/ changes: 1 file (`ingest/pipeline.py`). | Detail: see CHANGELOG-history.md cycle-85.
- **Cycle 83 (ingest crash-atomicity — closes the data-loss half of Phase 4.5 HIGH R2)** — Items: 2 src files + 1 new test file. **The defect:** the manifest slot was reserved with the BARE content hash BEFORE the first wiki page was written — ahead of the entire `_run_ingest_body` fan-out, not "between manifest-write and log-append" as the backlog recorded. A bare hash is indistinguishable from a completed ingest, so a crash anywhere across the body left `.data/hashes.json` asserting the source was fully ingested while the wiki held zero or partial pages; because `find_changed_sources` diffs stored-vs-current hash, that source was then skipped **permanently** on every later compile. All 6 `ingest_source` entry points were exposed; only `compile_wiki` had any (cycle-25) marker protection. **First attempt (rejected in review):** reserve an `in_progress:{hash}` marker with a three-way `_claims_content` dedup vocabulary. Codex R1 on PR #126 found a BLOCKER — two `in_progress:` markers for identical content mutually suppress forever, reintroducing the data loss — plus two MAJORs (fail-open reservation, `failed:` downgrade clobbering a completed hash). Root cause: one on-disk value cannot serve both concurrency dedup (a live claim must suppress) and crash recovery (a dead claim must not), because nothing on disk distinguishes live from dead except process liveness. **The fix (Design C):** stop overloading the value. Manifest values are uniformly bare content hashes again (cycle-17 semantics; `in_progress:`/`failed:` retired from the ingest path). Two mechanisms with matching lifetimes replace it — (1) **crash recovery**: `_commit_ingest_manifest` writes the hash exactly once, LAST, after `_run_ingest_body` succeeds, so a crash before it leaves no entry and `find_changed_sources` re-selects the source (no reservation, no marker, nothing to roll back); (2) **same-process concurrency**: `_content_ingest_lock`, a per-content-hash `threading.Lock` held across check → body → commit, so a second thread ingesting identical content deterministically sees a committed duplicate (replaces the timing-flaky threaded assertion). **Deliberate scope reduction (user-chosen):** cross-process concurrent ingest of identical-content-different-files is not serialized; it degrades to the existing summary-collision merge (safe, not corruption), rather than adding a durable cross-process claim whose crash semantics were the whole problem. `_check_and_reserve_manifest`/`_is_duplicate_content` are kept as read-only dup-check shims so the cycle-19 spy and cycle-18/64 monkeypatch seams still resolve; the old Phase-2 mid-body confirmation is removed (its `manifest_path`-divergence bug goes with it); `compiler.py`'s cycle-25 premarker is left untouched (under bare-hash dedup an `in_progress:` value never matches, so it cannot suppress or deadlock). **Separate live bug fixed:** `find_changed_sources` passed an unresolved `manifest_path` (`None`) to `file_lock`, raising `AttributeError: 'NoneType' object has no attribute 'with_suffix'` — reachable from `kb_compile_scan` (MCP) whenever `wiki_dir` is omitted; `compile_wiki` resolves the default earlier, which is why no existing test caught it. **GitPython** floor raised to 3.1.51, clearing 3 pre-existing advisories (Class A; local pip-audit now zero). BACKLOG: HIGH entry rewritten to the residual (no rollback of wiki-side page writes, deferred); new entries filed (T4 manifest value type check at the compiler read sites, T6 immortal legacy markers, T12 parent-dir fsync, contradiction-concurrency test load-sensitivity). | Tests: 3461 → 3472 collected (+11 in `tests/test_cycle83_ingest_crash_atomicity.py`); full suite 3432 passed / 24 skipped / 16 xfailed; ruff clean. | src/kb/ changes: 2 files (`ingest/pipeline.py`, `compile/compiler.py`). | Detail: see CHANGELOG-history.md cycle-83.
- **Cycle 82b (R2 Codex adversarial-review response — 2 MAJOR + 1 MINOR)** — Items: 2 src files + 1 test file. **MAJOR-1 phantom depth on async interrupt** (`utils/page_lock.py`): both branches mutated the thread-local depth BEFORE entering the `try` that guards it, so an async exception (KeyboardInterrupt / signal / injected cancellation) landing in that window skipped the `finally` and stranded a positive depth after `file_lock` released — a pooled thread reused later would treat a fresh acquisition as a re-entry and mutate the page holding NO lock. Both mutations moved INSIDE the `try`, and cleanup switched from a decrement to new helper `_restore_depth(depths, key, prior)`, an ABSOLUTE restore of the exact pre-acquisition depth (a decrement is only correct when the matching increment definitely ran). **MAJOR-2 `StorageError` masking** (`utils/io.py`): `file_lock`'s `finally` ended with an unguarded `lock_path.unlink(missing_ok=True)`. Cycle 81 AC04 moved the evidence append INSIDE the page lock, so `StorageError("evidence_trail_append_failure")` now propagates while the lock is held — an OSError from that unlink during unwinding would REPLACE it and destroy the caller's partial-write classification. Raising there is also wrong on the success path (the guarded writes already committed). Now wrapped in `try/except OSError` with a `logger.warning`; a leftover sidecar is self-healing via PID-based stale-lock steal. This is a `file_lock`-wide fix, not a `page_lock`-only one. **MINOR-3 sleep-based concurrency tests**: the two cross-thread exclusion tests held the lock for a fixed `time.sleep(0.4)` (a descheduled contender on a loaded runner passes falsely) and accepted any `OSError` (an unrelated permission/lock-parse failure satisfied the exclusion assertion). Both are now event-driven — the holder waits on an `attempt_done` Event so the lock is held until the contender's attempt fully resolves — assert specifically `TimeoutError`, and assert `not t.is_alive()` after join. `time` is no longer imported by the test module. **Verification honesty (cycle-11 L1 revert-checks):** the 2 new interrupt-unwinding tests pass with AND without the MAJOR-1 fix, because an exception raised inside the `with` body always reaches the `finally`; the vulnerable gap sits between two adjacent statements and is not deterministically reachable from pure Python without brittle trace injection. That limitation is documented in the test class docstring, and `test_restore_depth_is_absolute_not_decrement` is designated the real gate (it pins the absolute-restore contract directly). **Tooling note:** this review only ran after fixing the Codex harness — see CHANGELOG-history.md cycle-82b for the orphaned-job root cause. | Tests: 3458 → 3461 collected (+3); full Windows local suite 3421 passed / 24 skipped / 16 xfailed; ruff clean. | src/kb/ changes: 2 files (`utils/page_lock.py`, `utils/io.py`). | Detail: see CHANGELOG-history.md cycle-82b.
- **Cycle 82 (refiner page-lock migration — single page-lock primitive across the codebase)** — Items: 1 src file + 1 test-seam update. `review/refiner.py:118` `refine_page` was the last page-mutating site still acquiring the page via `file_lock`; it now uses the canonical `kb.utils.page_lock.page_lock` (cycle 81 AC01), making the primitive uniform across all 5 page-mutating sites. The local variable was renamed `page_lock` → `page_lock_cm`: the old name shadowed the helper, so adding the import without renaming would have silently rebound the call to a `_GeneratorContextManager` instance. The manual `__enter__()` / `finally: __exit__(None, None, None)` form is RETAINED — the lock spans a long region with early returns, and a `with` block would require restructuring the whole function body for no behavioural gain. Lock order is unchanged: page FIRST via `page_lock`, history SECOND via `file_lock(resolved_history_path)`, preserving the cycle-1 H1 / cycle-19 AC10 contract that `T-10` asserts. Only `tests/test_cycle19_refiner_two_phase.py` needed updating (2 lock-order spies now cover BOTH seams — `refiner.page_lock` for the page, `refiner.file_lock` for history); `test_cycle20_sweep_stale_pending.py` and `test_refiner.py` needed NO change because they only assert on the history acquisition, which still goes through `file_lock`. BACKLOG: the cycle-81-filed `review/refiner.py:113` entry DELETED. | Tests: 3461 collected; full Windows local suite 3421 passed / 24 skipped / 16 xfailed; ruff clean. | src/kb/ changes: 1 file (`review/refiner.py`). | Detail: see CHANGELOG-history.md cycle-82.
- **Cycle 81 (reentrant per-page write lock — closes Phase 4.5 HIGH R5 lock-ordering item)** — Items: 5 ACs, 1 NEW src module + 3 src files + 1 new test file + 3 test-seam updates. **AC01** NEW leaf module `src/kb/utils/page_lock.py` exposing `page_lock(path, timeout=None)` — a reentrant-per-(thread, page) context manager that delegates to `kb.utils.io.file_lock` on the OUTERMOST acquisition and degrades to a no-op on same-thread same-page re-entry. Depth is tracked in `threading.local()` state keyed by `os.path.normcase(os.path.abspath(path))`, so cross-thread and cross-process exclusion are unchanged — only the self-deadlock case is relaxed. Depth is incremented only AFTER `file_lock` yields, so a failed acquire leaves no phantom depth. **AC02** `ingest/evidence.py:append_evidence_trail` switches its `file_lock` → `page_lock`. **AC03** `ingest/pipeline.py:_update_existing_page_body` likewise. **AC04** (the actual fix) `ingest/pipeline.py:_update_existing_page` now wraps body-write + evidence-append in ONE outer `page_lock(page_path)`. Pre-cycle-81 the body-write lock had to be RELEASED before `append_evidence_trail` re-acquired it — the sidecar lock is not reentrant and cycle 24 documented the gap rather than closing it. A concurrent writer could land between a page's body update and its provenance row. **AC05** `compile/linker.py` `inject_wikilinks` + `inject_wikilinks_batch` route through `page_lock` for lock-discipline consistency; a nested caller that already holds the page now injects successfully instead of silently timing out at `_INJECT_LOCK_TIMEOUT` (0.25s) and skipping the page with a warning. Cycle-18/19 lock-spy tests re-point their monkeypatch seam `linker.file_lock` → `linker.page_lock`; every acquisition-count / call-order assertion is unchanged. **Audit finding:** the BACKLOG entry's claim that the five named RMW sites "None use `file_lock`" was STALE — stages 1/2/9/11 were locked across cycles 18/20/24/35 and `_write_wiki_page` is a single atomic write; the release-then-reacquire window was the only live residual, and the broader cross-stage atomicity concern is already carried by the Phase 4.5 HIGH `ingest/pipeline.py` state-store fan-out (receipt-file) item. BACKLOG: Phase 4.5 HIGH R5 entry DELETED. | Tests: 3437 → 3461 collected (+24 in `tests/test_cycle81_page_lock.py`); full Windows local suite 3421 passed / 24 skipped / 16 xfailed; ruff clean. | Files: ~220 → ~222 (+1 src module, +1 test file). | src/kb/ changes: 4 files (`utils/page_lock.py` NEW, `ingest/evidence.py`, `ingest/pipeline.py`, `compile/linker.py`). | Detail: see CHANGELOG-history.md cycle-81.
- **Cycle 80 (freeze-and-fold — v0915 series batch 1: task02/04/05/07)** — Items: 4 fold sources → 5 receivers; 51 tests moved VERBATIM (names preserved), 4 versioned test files DELETED. Folds: `test_v0915_task02.py` (7, ingest pipeline) → `test_ingest.py`; `test_v0915_task04.py` (19, query+citations+bm25) SPLIT → `test_query.py` (citations + query-context/config, 13) + `test_bm25.py` (tokenize, 6); `test_v0915_task05.py` (15, graph) → `test_graph.py`; `test_v0915_task07.py` (10, review/refiner) → `test_refiner.py`. Zero class-name collisions (pre-flight grep across all 5 receivers); shared conftest fixtures (`tmp_wiki`/`create_wiki_page`/`tmp_path`/`monkeypatch`) + function-local imports made the moves byte-verbatim (only the fold-provenance banner comment added). Advances Phase 4.5 HIGH coverage-visibility freeze-and-fold cadence: versioned `test_v0*` + `test_phase4_audit` files 24 → 20 (remaining `test_v0915_task{01,03,06,08,09,11}` + `test_v0{70,90,98,99}*` + `test_v09_cycle5_fixes` + 5 `test_phase4_audit_*` deferred to cycle 81+). | Tests: 3437 collected (preserved — moves only); 51 folded tests pass + receiver suites green (239 passed / 1 skipped across the 5 receivers); ruff clean. | Files: ~224 → ~220 (−4). | src/kb/ changes: ZERO. | Detail: see CHANGELOG-history.md cycle-80.
- **Cycle 79 (nltk 3.10.0 — last tracked upstream advisory closed, local pip-audit ZERO findings)** — Items: `nltk==3.9.4` → `nltk==3.10.0` in requirements.txt + venv. The cycle-75 re-check condition fired: advisory GHSA-p4gq-832x-fm9v / CVE-2026-54293 (HIGH, URL-encoded path-traversal in `nltk.data.load()`, decode-after-check) NOW lists fixed version 3.10.0 (was fix-less through cycle 75, making a bump "unverified churn" then), and GitHub raised Dependabot alert #63 on it — the bump is now a verified remediation, closing the alert. nltk remains TRANSITIVE-only (Crawl4AI + textstat; zero direct `src/kb` imports); import sanity verified (`nltk 3.10.0`, textstat loads). **Milestone:** local `pip-audit` reports ZERO findings for the first time (nltk was the last advisory standing after cycle-76's diskcache elimination) and `pip check` stays clean. **BACKLOG:** Phase 4.5 MEDIUM nltk entry DELETED (its "re-check whether the advisory gains a fixed-version stamp next cycle" instruction discharged). SECURITY.md Last-reviewed footer refreshed. | Tests: 3437 collected (no changes — full suite re-run against the bump). | src/kb/ changes: ZERO (manifest + docs only). | Detail: see CHANGELOG-history.md cycle-79.
- **Cycle 78 (freeze-and-fold — v0916 + v0917 series completed + stale diskcache BACKLOG entry deleted)** — Items: 12 fold sources → 16 receivers; 96 tests moved VERBATIM (1 class renamed), 12 versioned test files DELETED. Folds: `test_v0917_{dedup,embeddings,layered_context,stale_query}.py` + `test_v0916_task05.py` (query/citations parts) → `test_query.py`; `test_v0917_{contradiction,evidence_trail}.py` + `test_v0916_task03.py` → `test_ingest.py`; `test_v0916_task01.py` split 4-way (lint → `test_lint.py`, compile/linker → `test_compile.py`, mcp/core → `test_mcp_core.py`, mcp/quality → `test_mcp_quality_new.py`); `test_v0916_task02.py` split 6-way (`test_config.py`, `test_utils.py`, `test_utils_text.py`, `test_utils_io.py`, `test_utils_markdown.py`, `test_models.py`); `test_v0916_task04.py` → `test_compile.py`; `test_v0916_task05.py` graph parts → `test_graph.py`, bm25 part → `test_bm25.py`; `test_v0916_task06.py` split (lint/trends → `test_lint.py`, review/refiner → `test_refiner.py`, evolve → `test_evolve.py`). One collision: incoming `TestConfigConstants` renamed → `TestConfigConstantsV0916` (receiver defines same name). Deviations beyond fold-site imports: one function-local `import time` in `TestFlagStaleResults` (receiver's module-level `time` is `datetime.time`). **BACKLOG hygiene:** stale Phase 6 R2 LOW `diskcache 5.6.3 / CVE-2025-69872` risk-acceptance entry DELETED — cycle 76 removed dspy + diskcache from the dependency tree entirely (`pip show diskcache` empty; entry predated that removal). Advances Phase 4.5 HIGH coverage-visibility freeze-and-fold cadence: versioned `test_v0*` files 31 → 19. | Tests: 3437 collected (preserved — moves only); 536 passed + 1 skipped across the 16 receivers. | Files: ~236 → ~224 (−12). | src/kb/ changes: ZERO. | Detail: see CHANGELOG-history.md cycle-78.
- **Cycle 77 (freeze-and-fold — v0100x series completed)** — Items: 5 fold sources → 4 receivers; 26 tests moved VERBATIM (names preserved), 5 versioned test files DELETED. Folds: `test_v01004_query_correctness.py` (6) + `test_v01005_query_perf_docs.py` (5) → `test_query.py`; `test_v01006_compile_fixes.py` (4) → `test_compile.py`; `test_v01008_ingest_pipeline_fixes.py` (8) → `test_ingest.py`; `test_v01010_lint_fixes.py` (3) → `test_lint.py`. Completes the v0100x family (v01003/v01007/v01009/v01011 folded cycles 52/55). Zero collisions (pre-flight name grep); function-local imports made moves verbatim; duplicate top-level `import pytest` stripped for the ingest receiver. Advances Phase 4.5 HIGH coverage-visibility freeze-and-fold cadence: versioned `test_v0*` files 36 → 31. | Tests: 3437 collected (preserved — moves only). | Files: ~241 → ~236 (−5). | src/kb/ changes: ZERO. | Detail: see CHANGELOG-history.md cycle-77.
- **Cycle 76 (dspy removal — accepted-advisory table EMPTIED, CI pip check + pip-audit both strict)** — Items: removes the unused `dspy==3.1.3` pin plus its 6 orphan-only transitive pins (`diskcache`, `gepa`, `optuna`, `asyncer`, `cloudpickle`, `json_repair`) from requirements.txt + venv — verified safe by `pip show` reverse-dependency walk (each Required-by lists only dspy; `xxhash` retained — also needed by Crawl4AI/datasets/langgraph/langsmith) and zero-imports grep repo-wide. **Security win:** `diskcache` (the pickle-RCE CVE-2025-69872 accepted advisory) leaves the dependency tree entirely — the old "transitive of trafilatura's robots.txt cache" rationale was stale (trafilatura 2.0.0 neither declares nor imports it; dspy was the ONLY dependent). SECURITY.md Known Advisories table now EMPTY (row → resolution note per FORMAT GUIDE). **CI strictness (closes cycle-34 AC52 + T4/T5 mitigations):** `pip check` step drops `continue-on-error: true` (the dspy→litellm gap was the last tolerated conflict; `pip check` now fully clean locally for the first time since cycle 34); `pip-audit` step drops its last `--ignore-vuln` flag (exception-free audit — ANY CVE on ANY installed package now fails CI). **Test lock-ins updated atomically (cycle-2 L1):** `test_cycle36_ci_hardening.py` `test_workflow_ignore_vuln_nonempty` INVERTED to `test_workflow_ignore_vuln_empty_since_cycle76` (the old guard protected against ACCIDENTAL emptying; cycle 76 empties INTENTIONALLY); `test_cycle34_release_hygiene.py` AC14 assertions inverted to `--ignore-vuln absent` + bare `run: pip-audit` locator; SECURITY.md↔ci.yml set-parity test passes with both sides empty. **BACKLOG:** diskcache CVE entry + resolver-conflicts entry DELETED (both fully resolved). pip-audit local: 1 finding remains (nltk, fix-less upstream, not installed in CI). | Tests: 3437 collected (net 0 — lock-ins updated in place). | src/kb/ changes: ZERO (manifests + CI + security docs + 2 test files). | Detail: see CHANGELOG-history.md cycle-76.
- **Cycle 75 (dep-hygiene re-check — 6 of 8 pip-audit findings + 3 of 4 resolver conflicts cleared)** — Items: backlog-mandated upstream re-check of the 3 tracked no-fix CVEs + 4 resolver conflicts. **Patched now-fixable vulns:** `joserfc` 1.6.4→1.6.8 (PYSEC-2026-2528 + PYSEC-2026-2530; orphan dist, nothing requires it — pinned in requirements.txt for Dependabot visibility), `msgpack` 1.1.2→1.2.1 (GHSA-6v7p-g79w-8964; transitive via CacheControl — pinned), local `.venv` pip 26.1.1→26.1.2 (PYSEC-2026-196; CI already pins `pip>=26.1`). **Resolver conflicts cleared (3 of 4):** arxiv 2.4.1→4.0.0 (`requests<2.34` now accepts 2.33.0; arxiv-mcp-server allows `arxiv>=2.1.0`), Crawl4AI 0.9.0→0.9.2 (`lxml<7` now accepts 6.1.1), venv `rich` synced back to manifest pin 14.3.3 (15.0.0 was venv drift; nothing installed requires `rich>=15`) — `pip check` now reports ONLY the deliberate dspy/litellm gap. **Still fix-less upstream (entries retained with refreshed timestamps):** diskcache CVE-2025-69872 (5.6.3 still latest), nltk GHSA-p4gq-832x-fm9v (3.10.0 released but advisory lists NO fixed version — bump would be unverified churn). **BACKLOG:** stale `.venv pip==26.0.1` CVE-2026-3219 entry DELETED (SECURITY.md resolved it 2026-05-06 via CI `pip>=26.1` floor; local venv now 26.1.2, pip-audit clean); resolver-conflicts entry rewritten to the single remaining dspy/litellm item with removal options. SECURITY.md diskcache row + Last-reviewed footer refreshed. | Tests: full suite re-run against bumped deps (see PR CI). | src/kb/ changes: ZERO (manifests + docs only). | Detail: see CHANGELOG-history.md cycle-75.
- **Cycle 74 (tier-boundary verifier hardening — closes all 3 cycle-74+ deferred entries)** — Items: 3 ACs across 3 src/kb/ files (1 NEW module) + 1 new test file. **AC01** (cycle-73 R2 DeepSeek F-2) `max_keys: int = 500` DoS bound on `_validate_tier_boundary` — caps the key count of the root dict (checked cheap-first, BEFORE the extra-key set difference) AND every nested dict (the realistic mass-key surface: the extra-key check only covers the root); override path via kwarg. **AC02** (cycle-73 R1 Opus C2) same-class peer expansion — the two `_call_llm_json(tier="scan", schema=...)` call sites in `lint/augment/proposer.py` (`_propose_urls`, `_relevance_score`) now re-gate their scan-tier responses through `_validate_tier_boundary` with site-specific `expected_keys`/`required_keys` derived from the LOCAL `_PROPOSER_SCHEMA`/`_RELEVANCE_SCHEMA` constants (T5 anti-spoofing); rejection is fail-closed (abstain / 0.0) with the forensic-distinct `tier_boundary_rejected:` marker (split-catch BEFORE generic handler, mirroring cycle-73 AC04); also closes a latent crash path (`_relevance_score` non-dict response previously hit `response.get(...)` OUTSIDE the try → AttributeError). Mechanically: validator extracted from `orchestrator.py` into NEW leaf module `lint/augment/tier_boundary.py` (orchestrator imports proposer at module level → proposer could not import back); orchestrator re-exports `_validate_tier_boundary` + `_TBV_ALLOWED_VALUE_TYPES` so the cycle-73 monkeypatch surface is unchanged (all 32 cycle-73 tier-boundary tests pass unmodified). **AC03** (cycle-73 R2 F-3) `required_keys: frozenset[str] = frozenset()` kwarg — enforces the JSONSchema `"required"` list separately from `expected_keys`; empty default preserves the cycle-73 optional-subset contract; plumbed at all 3 call sites (`orchestrator.py` auto_ingest via `schema.get("required", [])`, both proposer sites via schema constants). **R1 Codex review (REQUEST-CHANGES → fixed)**: M-1 `capture.py:_extract_items_via_llm` was the LAST scan-tier `call_llm_json` site in src/kb/ without the re-gate — added with loud rejection (TierBoundaryError propagates; response drives capture file creation; lazy import avoids the genuine circular import `kb.capture → augment.__init__ → proposer → kb.lint.fetcher → kb.capture`); MINOR-2 replay-style required_keys plumb test replaced with real `run_augment(mode='auto_ingest')` integration spy; MINOR-3 relevance rejection test now pins the `tier_boundary_rejected` log marker (split-catch vs generic-handler distinctness). Drive-by flake fix surfaced during verification: `tests/test_cycle23_mcp_boot_lean.py::_run_probe` default timeout 10s → 30s (cold-start probes take 6-8s on the Windows dev box; 10s spuriously expired under concurrent machine load — A/B import timing branch-vs-main confirmed code-independent; the tests assert boot-leanness via `sys.modules`, not wall-clock). BACKLOG: 3 Phase 4.5 LOW cycle-74+ deferred entries DELETED (all shipped). | Tests: 3413 → 3437 collected (+24: 22 positive + 2 xfail-strict mutation pins in `tests/test_cycle74_tier_boundary_hardening.py`); full Windows local suite 3397 passed + 24 skipped + 16 xfailed. | Files: 239 → 241 (+1 test file, +1 src module `lint/augment/tier_boundary.py`). | src/kb/ changes: 4 files (`lint/augment/tier_boundary.py` NEW, `lint/augment/orchestrator.py` re-export + required_keys plumb, `lint/augment/proposer.py` 2 call-site re-gates, `capture.py` R1 M-1 re-gate). | Detail: see CHANGELOG-history.md cycle-74.
- **Cycle 73 (dev-mimo-opus trial — completeness wrap + verdict prompt-version + tier-boundary verifier + BACKLOG hygiene + snapshot, fourteenth trial cycle)** — Items: 6 ACs across 4 src/kb/ files + 5 new test files + BACKLOG hygiene. **AC01** `lint/semantic.py:466 build_completeness_context` cap+wrap mirrors cycle-72 AC01 pattern (cap `paired['page_content']` via shared `_cap_page_content` helper inheriting cycle-72 R2 Codex M-1 marker reservation; header/body/closing triplet; single `wrap_wiki_context` fence; `_render_sources` budget reserves `_FENCE_OVERHEAD`) — closes cycle-72 §T1 OOS deferred peer (T1 Tampering + T2 InformationDisclosure). **AC02** `lint/verdicts.py::add_verdict` writes `prompt_version: int` field; new `get_prompt_version(entry: dict) -> int` accessor with default 0 for legacy entries; defensive type-handling (non-dict / non-int / bool returns 0); `kb.config.CURRENT_PROMPT_VERSION = 1` constant; `load_verdicts` UNCHANGED (no cache mutation per T7 cache-fidelity invariant) — closes cycle-72 §T7 Repudiation forensic gap. **AC03** `lint/augment/orchestrator.py` new `_validate_tier_boundary(scan_output, *, expected_keys, max_depth=4, max_string_len=4096) -> dict` helper at L394 site re-gates scan-tier `_call_llm_json` outputs against orchestrate-tier consumption rules (rejects: non-dict root / extra keys / oversize strings / deep nesting / unsupported value types); `expected_keys` derived from local schema (T5 spoofing defense at call site) — closes cycle-72 §T8 EscalationOfPrivilege blast-radius gap. **AC04** `kb.errors.TierBoundaryError(ValidationError)` exception + orchestrator split-catch (`except TierBoundaryError as e:` BEFORE generic `except Exception`); manifest reason prefix literal `"tier_boundary_rejected: ..."` for forensic distinctness — T9 Repudiation. **AC05** (PIVOTED at Step 5) snapshot for `_persist_contradictions` at `src/kb/ingest/pipeline.py:183` with `date.today()` monkeypatched for determinism — primary-session grep proved 5 of 6 BACKLOG-listed deferred subjects already shipped cycles 69/70 (`_render_sources`, `build_extraction_prompt`, `_build_summary_content`, `build_llms_full_txt`, `build_graph_jsonld`); cycle-73 closes the last one. **AC06** (EXTENDED) BACKLOG hygiene: deletes stale `KB_DISABLE_VECTORS=1` Phase 4.5 MEDIUM line (shipped cycle 67 AC06), updates snapshot-subjects line 79-80 to reflect cycle-69/70/73 ALL 6 SHIPPED, deletes 3 cycle-72-deferred LOW entries closed by cycle-73 AC01/AC02/AC03+AC04, adds 3 NEW cycle-74+ deferred entries (max_keys DoS bound + proposer.py:91/168 same-class peer expansion + required-keys enforcement). | Tests: 3369 → ~3403 (+34 net: 14 positive AC03+AC04 + 8 positive AC02 + 6 positive AC01 + 3 AC05 snapshot + 4 AC06 hygiene + 5 xfail-strict mutation controls in 5 new test files; 1 .ambr snapshot generated). | Files: 234 → 239 (+5 new test files: `test_cycle73_completeness_wrap.py`, `test_cycle73_prompt_version.py`, `test_cycle73_tier_boundary.py`, `test_cycle73_snapshots.py`, `test_cycle73_backlog_hygiene.py`). | src/kb/ changes: 4 files (`lint/semantic.py` AC01, `lint/verdicts.py` AC02, `lint/augment/orchestrator.py` AC03+AC04, `errors.py` AC04 new TierBoundaryError class) + `config.py` AC02 new CURRENT_PROMPT_VERSION constant. | Trial telemetry: R1 Opus APPROVE-WITH-CONDITIONS (9), R2 DeepSeek V4 Pro APPROVE-WITH-FINDINGS (4, 0 blockers); cycle-72 lessons L1 (circular-import) + L8 (cap-math) verified PASS. | Detail: see CHANGELOG-history.md cycle-73 + docs/superpowers/decisions/2026-05-09-cycle-73-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design-decision,plan,plan-gate}.md.
- **Cycle 72 (dev-mimo-opus trial — wrap_wiki_context residual surface completion, thirteenth trial cycle)** — Items: 17 ACs across 4 src/kb/ files + 1 new test file (`tests/test_cycle72_wrap_extensions.py`) + 2 atomic test updates. Bucket A (AC01-AC05) extends cycle-70/71 `wrap_wiki_context()` to 5 residual surfaces (all 5 cycle-72+ Phase-4.5 LOW BACKLOG entries shipped): **AC01** `lint/semantic.py:_cap_page_content` helper caps `paired['page_content']` at `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` before assembly inside `build_fidelity_context` (single-site only — `build_completeness_context` deferred to cycle-73+ per threat-model §T1; R2 F-1 expansion REJECTED at Step 5 decision gate); **AC02 + AC02a (atomic)** `review/context.py:build_review_context` migrates cycle-1 H14 `<wiki_page_body>` / `<raw_source_N>` XML literal sentinels to a single outer `wrap_wiki_context` fence with markdown sub-headers, AND atomically updates `build_review_checklist` text to reference the new `<wiki_context>` token (T3 InformationDisclosure mitigation); **AC03** `lint/augment/orchestrator.py:_build_pre_extract_prompt` helper extraction at L368 replaces literal `<untrusted_source>` sentinel with `wrap_wiki_context`; helper extraction enables AC08 lock-in test to reach the call site without complex `run_augment` fixture setup (cycle-23 L2 + cycle-16 L2); **AC04** `lint/semantic.py:build_consistency_context` per-page wrap_wiki_context fence (Approach A — per-page assertion repetition); new module-level constant `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS = MAX_CONSISTENCY_PAGE_CONTENT_CHARS - _FENCE_OVERHEAD` reserves fence overhead (option (b) per design-decision condition 5 — option (a) modify-in-place would have caused circular import; the public `kb.config.MAX_CONSISTENCY_PAGE_CONTENT_CHARS` constant stays at 4096); **AC05** `lint/augment/proposer.py:_relevance_score` wraps `stub_title` with `sanitize_extraction_field()` BEFORE the `!r` repr-quote (header-strip + frontmatter-fence-strip + length-cap at 2000; the `!r` STAYS as defense-in-depth). Bucket B (AC06-AC10) lock-in tests + Bucket C (AC11-AC15) paired `xfail(strict=True)` mutation control tests in `tests/test_cycle72_wrap_extensions.py` — all 5 mutations monkeypatch the IMPORTED BINDING in the call-site module's namespace per cycle-71 L1+L2; runtime `_FENCE_OVERHEAD` measurement (R2 F-5 MERGE) decouples test from constant definition; AC07 atomic-coupling pipeline test (R2 F-2 MERGE) asserts `<wiki_context>` count + literal old-sentinel absence + checklist `<wiki_context>` reference together. Pre-existing test atomic updates per cycle-2 L1: `tests/test_phase45_theme3_sanitizers.py:332-377` H14 regression updates and `tests/test_cycle8_consistency_caps.py:38-94` truncation marker (uses `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS`). Bucket E (AC16-AC17) doc artifacts: this CHANGELOG entry + CHANGELOG-history.md cycle-72 detail + CLAUDE.md sync + 5 cycle-72+ BACKLOG entries DELETED + 3 cycle-73+ deferred entries ADDED (`build_completeness_context` cap+wrap, `kb.lint.verdict_db.prompt_version` schema, scan-tier→orchestrate-tier boundary verifier). Trial telemetry: 14 binding R1 conditions integrated; R2 DeepSeek BLOCK reconciled at Step-5 decision gate (R2 F-1 REJECTED with rationale, 4 R2 findings MERGED into R1 conditions); circular-import surfaced at Step-9 implementation forced switch from design-decision option (a) to option (b) — change documented in C1 commit message + design-decision note. R3 skipped per <25-AC threshold. | Tests: ~3345 → ~3369 (+24 net: 19 positive + 5 xfail-strict in 1 new file). | Files: ~233 → ~234 (+1: `tests/test_cycle72_wrap_extensions.py`). | src/kb/ changes: 4 files (`lint/semantic.py` AC01+AC04, `review/context.py` AC02+AC02a, `lint/augment/orchestrator.py` AC03, `lint/augment/proposer.py` AC05) plus `kb/config.py` doc-only comment. | Detail: see CHANGELOG-history.md cycle-72 + docs/superpowers/decisions/2026-05-09-cycle-72-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design-decision,plan,plan-gate}.md.
- **Cycle 71 (dev-mimo-opus trial — wrap_wiki_context sibling-surface completion, twelfth trial cycle)** — Items: 12 ACs across 3 src/kb/ files + 1 new test file (`tests/test_cycle71_wrap_extensions.py`). Bucket A (AC01-AC04) extends cycle-70 `wrap_wiki_context()` to 4 sibling surfaces deferred from cycle-70 AC11: AC01 `mcp/browse.py:_format_search_results` per-snippet content + R2-F1 title wrap; AC02 `mcp/browse.py:kb_read_page` body wrap with R2 footer-before-wrap ordering + char-cap reduction by `_FENCE_OVERHEAD + _MAX_TRUNCATION_FOOTER_BYTES=200` (SHARP cap on truncation path); AC03 `lint/semantic.py:build_fidelity_context` Q2 A1 single-fence around page+sources between heading and closing instructions, with `_render_sources(...,*,budget=...)` keyword-only plumb + R2-F2 `sanitize_extraction_field(source['path'], max_len=500)`; AC04 `lint/augment/proposer.py:_relevance_score` R2-F3 empty/whitespace-input early-return guard + wrap_wiki_context. Bucket B (AC05-AC08) lock-in tests: 4 positive lock-in classes per AC + 4 paired `xfail(strict=True)` mutation control classes per cycle-24 L1 — all monkeypatch the IMPORTED BINDING in the call-site module's namespace; R2-F4 fence-balance equality + R2-F5 `_FENCE_OVERHEAD` runtime invariant assertions. Bucket C (AC09) BACKLOG hygiene: 4 deletions + 5 NEW Phase 4.5 LOW entries for cycle-72+ deferred peers (page-content overshoot Q3 carry; H1 `build_review_context` XML-sentinel migration; H2 `lint/augment/orchestrator.py:365-372` pre-extract migration; H6 `build_consistency_context` migration; R2-cumulative `_relevance_score` `stub_title` field) + cycle-68 lock-in tuple extension + diskcache CVE timestamp refresh. Bucket D (AC10-AC12) doc artifacts: 8 decision docs + this CHANGELOG + CLAUDE.md sync. Trial telemetry: R2 DeepSeek caught 2 critical wrap-field omissions R1 Opus missed (R2-F1 title + R2-F2 path); Step 7 mimocoding-rescue dispatch failed (file shell created with no content per cycle-12 L2) → primary-session fallback per cycle-13 sizing heuristic; Step 4 R2 DeepSeek's own Write tool blocked by Fact-Forcing Gate hook → primary-session transcribed R2's structured summary into the canonical R2 file per cycle-20 L4 manual-verify. R3 skipped per design.md Q6. | Tests: ~3288 → ~3306 (+18 net: 14 positive + 4 xfail-strict in 1 new file). | Files: ~234 → ~235 (+1: `tests/test_cycle71_wrap_extensions.py`). | src/kb/ changes: 3 files (`mcp/browse.py` AC01+AC02, `lint/semantic.py` AC03, `lint/augment/proposer.py` AC04). | Detail: see CHANGELOG-history.md cycle-71 + docs/superpowers/decisions/2026-05-09-cycle-71-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design,plan,plan-gate}.md.
- **Cycle 70 (dev-mimo-opus trial — MCP prompt-injection boundary + snapshot subjects + cycle-69 carry-over + BACKLOG hygiene, eleventh trial cycle)** — Items: 16 ACs shipped across 6 buckets. Bucket A (AC01-AC04) verify-and-delete BACKLOG hygiene: cycle-68 AC09 httpx pin shipped; cycle-67 AC13 README KB_PROJECT_ROOT bootstrap shipped; cycle-67 AC04 KB_STRICT_PUBLISH shipped; cycle-69 AC07-AC12 inspect.getsource batch shipped. AC05 lock-in extension (`tests/test_cycle68_backlog_cleanup_lockin.py` cumulative `DELETED_ENTRIES` tuple gains 6 cycle-70 substrings per design.md C1). Bucket B (AC06-AC08) snapshot subjects deferred from cycle-64 R3: `kb.ingest.pipeline._build_summary_content` (per amendment A1 fixture uses key_claims, NOT contradictions — function does not process them); `kb.compile.publish.build_llms_full_txt` (incremental=False per C3 with explicit-date frontmatter); `kb.compile.publish.build_graph_jsonld` (assertion canonicalization per A4 — re-parses + sort_keys, production unchanged). Bucket C (AC09) cycle-69 R2 Codex post-merge carry-over — date-coverage audit verdict: covered (4 sites in pipeline.py module-globally patched via `from datetime import date`, 2 reachable from `_persist_contradictions`); forward-looking date-string lock-in asserts persisted block contains 2026-05-08. Bucket D (AC10) C41-L1 behavioural upgrade for `tests/test_compile.py::test_prune_base_uses_canonical_rel_path_at_both_sites` — replaces inspect.getsource source-grep with parametrized `Mock(wraps=compiler._canonical_rel_path)` spy covering both detect_source_drift + compile_wiki(mode='full') sites. Bucket E (AC11/AC12) MCP prompt-injection boundary — NEW `wrap_wiki_context()` helper in `kb.utils.text` (mirroring cycle-7 wrap_purpose pattern: T3 `</wiki_context>` escape, T4 empty short-circuit, T5 `_FENCE_OVERHEAD` reservation); wired at 2 in-scope sites (engine.py:1063 synthesis prompt combined context + mcp/core.py:417-432 Claude Code mode response); 4 out-of-scope sibling surfaces filed as Phase 4.5 LOW BACKLOG entries for cycle-71+ (kb_search snippets / kb_read_page body / build_fidelity_context / _relevance_score). Bucket F (AC13-AC16) doc artifacts. R1 Opus 100% precision (4/4 valid MAJORs after fact-check); R2 DeepSeek 0% precision (2/2 hallucinations rejected — date-coverage already module-global; injection-points named static-artifact builders, not LLM prompts). | Tests: 3288 → 3302 (+14 net: 6 cycle-70 prompt_safety + 7 cycle-70 snapshots [3 positive + 3 negative-control + 1 date lock-in] + 2 AC10 parametrized spy − 1 inspect.getsource test removed = +14). | Files: ~232 → ~234 (+2 new test files: test_cycle70_snapshots.py, test_cycle70_prompt_safety.py). | src/kb/ changes: 3 files (utils/text.py +67 lines wrap_wiki_context helper; query/engine.py wired 3 sites; mcp/core.py wired 1 site). | Detail: see CHANGELOG-history.md cycle-70 + docs/superpowers/decisions/2026-05-08-cycle-70-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design,plan,plan-gate}.md.
- **Cycle 69 (dev-mimo-opus trial — backlog hygiene + test-quality + folds + snapshots, tenth trial cycle)** — Items: 22 ACs shipped (AC01 cycle-68 lock-in retirement + DELETED_ENTRIES extension; AC02 cycle-68 carry-over BACKLOG section deletion; AC03 stale Phase 6 LOW path-validation entry deletion (verified-shipped at `mcp/app.py:291` segment-aware form, the in-project `_validate_page_id` helper — not any third-party library); AC04 stale Phase 4.5 HIGH `graph/builder.py` non-lint callers entry deletion (cycle-68 AC07/AC08a/AC08b shipped 3 of 5; remaining 2 sites are FW-7 pages-supplying intentional bypasses by design); AC05–AC06 lock-in tests (segment-aware page_id parametrized matrix + AST guard for FW-7 build_graph bypasses); AC07–AC12 C11-L1 inspect.getsource batch upgrade (4 versioned files / 6 sites converted to behavioural assertions per cycle-11 L1 — kb_lint/kb_evolve logger.error spy, compute_verdict_trends threshold-divergence monkeypatch, build_graph WIKI_SUBDIRS scan filter, analyze_coverage WIKI_SUBDIRS pinning, analyzer FRONTMATTER_RE identity check); AC13–AC15 snapshot subjects (3 cycle-64 deferred follow-up subjects: `kb.ingest.extractors.build_extraction_prompt` (deterministic, no monkeypatch needed), `kb.ingest.pipeline._persist_contradictions` (FakeDate freeze of `date.today()` per amendment A3), `kb.lint.semantic._render_sources` (truncation negative-control via `kb.lint.semantic.QUERY_CONTEXT_MAX_CHARS` monkeypatch per cycle-18 L1)); AC16–AC19 freeze-and-fold (4 small versioned tests folded into `tests/test_query.py` + `tests/test_config.py`); AC20–AC21 doc artifacts (decisions docs + this CHANGELOG); AC22 (R2-promoted, NEW): stale Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` allowlist entry deletion (verified shipped via cycle-68 AC04 wiki/_lint.yml lazy YAML loader + DUPLICATE_SLUG_ALLOWLIST overlay — same in-project module name, distinct from any external library). | Tests: 3274 → 3288 (+14 net: +5 AC05 parametrize rows, +2 AC06 AST guard tests, +6 snapshots/AC13-AC15 [3 positive + 3 negative-controls], +6 C11-L1 upgraded behavioural tests, -4 fold-source rows net 0; +14 actual). | Files: ~232 → ~232 (4 fold deletions + 3 new test files + 1 snapshot baseline + 9 cycle-69 decision artifacts; net stable). | src/kb/ changes: ZERO (pure-test/doc/BACKLOG hygiene cycle — no module migrations, no library changes, no dependency changes). | Trial telemetry: R1 100% precision; R2 25% precision (3 of 4 R2 MAJORs hallucinated, 1 valid → AC22); primary-session fact-check rate 3/3 hallucinations corrected. | Detail: see CHANGELOG-history.md cycle-69 + docs/superpowers/decisions/2026-05-08-cycle-69-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design,plan,plan-gate}.md.
- **Cycle 68 (dev-mimo-opus trial — CLI hardening, lint/deps hygiene, automated docstring gate, backlog lock-in)** — Items: 15 ACs shipped (AC01–AC10 production, AC11–AC15 regression tests). AC01 cli_backend Popen refactor + 2 daemon reader threads + separate stdin write thread (FW-1) + chunked stdout/stderr cap + platform-aware terminate→kill grace (2.0s POSIX / 0.5s Windows); AC02 `MAX_CLI_STDERR_BYTES = 64 KB` constant; AC03 YAML lint loader (`yaml.safe_load` only, schema validation, FW-2 RCE T7 mitigation); AC04 `duplicate_slug` allowlist overlay from `wiki/_lint.yml`; AC05–AC06 automated docstring audit (`scripts/audit_docstrings.py` + CI step, warn-only this cycle, hard-fail in cycle 69+); AC07 `kb.evolve.analyzer:127` migrated `build_graph` (pages=None) → `kb.graph.cache.get_graph` (pages-supplying calls at lines 28+358 retained per FW-7); AC08a `kb.graph.export:83` migrated; AC08b `kb.mcp.browse.kb_stats:345` migrated; AC09 `httpx>=0.28,<0.29` pin for drift protection; AC10 BACKLOG cleanup (cycle-67-audited shipped entries deleted; CVE-2025-69872 / diskcache transitive pickle-RCE accepted-with-rationale, no fix published). | Tests: 3248 → 3274 (+26 across 6 new cycle-68 test files; 92% cli_backend coverage). | Files: ~226 → ~232 (+6 cycle-68 test files). | Detail: see CHANGELOG-history.md cycle-68.
- **Cycle 67 (mimo-audit residual + Phase 4.5 cleanup — ninth dev-mimo-opus trial cycle)** — Items: 12 ACs (AC01/02/04/05/06/08/09/10/11/13/14/15) across 4 src files + 8 new test files + ci.yml + README + 3 dep-CVE patches / ~16 commits. AC01 `MODEL_TIERS` legacy import-time-captured dict → `_ModelTiersView(Mapping)` call-time view (closes mimo r5 Q1+Q2 — actual surface, not the misnamed `_DEFAULT_MODEL_TIERS`); AC02 graph/cache 6th-caller-drift AST guard test (forbid `from kb.graph.cache import get_graph` in src/kb/; aliased forms allowed); AC04 `KB_STRICT_PUBLISH=1` env var re-raises `auto_publish_after_compile` failures; AC05 sqlite_vec.load() error sanitization at second call site `embeddings.py:665`; AC06 `KB_DISABLE_VECTORS=1` runtime kill-switch for hybrid search vector branch; AC08 `_autouse_kb_path_sandbox` decorator AST meta-test; AC09 non-vacuous paired snapshot negative-controls (replaces vacuous cycle-64 _neg_control with proper divergence assertions); AC10 verified-shipped via cycle-65 AC19 + backstop test; AC11 broaden cycle-65 `dummy-key-leak-guard` to all tracked files with explicit allowlist (mimo r5 Q7 cassette/snapshot leak); AC13 README "Non-clone install" section (KB_PROJECT_ROOT bootstrap); AC14 `docs/reference/INDEX.md` inverse-direction consistency check (typo guard); AC15 `_check_no_secrets_on_argv` design-intent lock-in tests. Step 15 dep-CVE patches: GitPython 3.1.47 → 3.1.49 (CVE-2026-44244), Mako 1.3.11 → 1.3.12 (CVE-2026-44307), python-multipart 0.0.26 → 0.0.27 (CVE-2026-42561). | Tests: 3173 → ~3231 (+~58 across 8 new cycle-67 test files). | Files: ~218 → ~226 (+8 new test files). | Carry-over to cycle 68: AC03 (`call_cli` Popen refactor with chunked stdout cap), AC07 (`wiki/_lint.yml` lazy YAML loader), AC12 (`scripts/audit_docstrings.py` Args/Returns/Raises gate). | Trial telemetry: Step 2 Opus subagent latency was 24 min (exceeded 10-min cycle-20 L4 hang threshold; primary-session fallback worked, then subagent caught up with higher-quality output); Step 4 R2 DeepSeek 8 min within budget; Step 8 mimo audit role 5 min APPROVE-with-zero-gaps (cycle-61 memory holds: mimo audit works, implementer doesn't). | Detail: see CHANGELOG-history.md cycle-67 + docs/superpowers/decisions/2026-05-07-cycle-67-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design,plan,plan-gate}.md.
- **Cycle 66 (carry-over hardening — eighth dev-mimo-opus trial cycle)** — Items: 5 ACs across 3 src files + 1 helper module + 5 new test files / 7 commits. (A) AC1 dead `__getattr__("PROJECT_ROOT")` branch removal in `kb.config` (PEP 562 only fires for missing names; line-107 binding shadows it); (B) AC2 `_check_no_secrets_on_argv` derives `_SCRUB_KEYS` frozenset from `CLI_BACKEND_ENV_INJECT.values()` plus 4 standalone keys (5 net-new keys gain coverage: GEMINI/KIMI/QWEN/ZAI/ZHIPUAI); (C) AC3 `lru_cache(maxsize=8)` on heuristic walk-up via new `_heuristic_walk_up_cached(cwd_str)` (test-suite + dev-loop perf — production typically sets `KB_PROJECT_ROOT` and short-circuits before the cache); (D) AC4 `find_module_imports` AST helper in `tests/_helpers/ast_walk.py` covering both `ast.Import` (bare form) + `ast.ImportFrom` (from form) — consolidates 4 cycle-65 banned-import walks into 1 parametrized test; (E) AC5 `_assert_under_project_root` `allow_symlinks` kwarg dropped (Q2.2 cap 4→3, symlink rejection now structurally unconditional). | Tests: 3134 → 3173 (+39 across 5 new test files + 8 helper tests). | Files: ~213 → ~218 (+5 cycle-66 test files). | Detail: see CHANGELOG-history.md cycle-66 + docs/superpowers/decisions/2026-05-05-cycle-66-{requirements,threat-model,brainstorm,design-eval-R1-opus,design-eval-R2-deepseek,design,plan,plan-gate}.md.
- **Dependabot alert repair (2026-05-05)** — Removed `ragas` and the `litellm` distribution from `pyproject.toml` and `requirements.txt`, closing Dependabot alerts #12 through #15 without downgrading `click`. Declared `scipy` directly because graph stats already require `networkx.pagerank`'s SciPy path; previously this was accidentally supplied by the removed eval harness. Retired the resolved `pip-audit` ignores and removed the stale BACKLOG/SECURITY entries. Scope: dependency manifests, security docs, CI audit config, and matching regression tests only; no `src/kb/` runtime code changes. Detail: [history archive](CHANGELOG-history.md#2026-05-05--dependabot-alert-repair).
- **Cycle 65 (Security hardening + config consistency)** — Items: 23 ACs across ~15 files (config call-time accessors, path_safety.py NEW, mcp/_error_boundary.py NEW, _validate_page_id hardening, http-only allowlist, VectorIndex.build file_lock, CLI secret-scrub) | Tests: 3039->3134 (+95, 12 new test files) | Files: 207->~213 (+5 NEW src files) | Detail: see CHANGELOG-history.md cycle-65
- **Cycle 64 (Backlog batch -- sixth dev-mimo-opus trial cycle)** -- Items: 25 ACs across 6 domains (autouse sandbox, dim-mismatch auto-rebuild, graph cache NEW, auto-publish, snapshots) | Tests: 3021->3039 (+18, 6 new test files) | Files: 200->207 (+7: graph/cache.py + 6 test_cycle64_*.py) | Detail: see CHANGELOG-history.md cycle-64
- **Cycle 58 (folds -- fourth dev-mimo-opus trial cycle)** -- Items: 4 ACs (5 planned, 1 dropped at rebase) / 4 test files DELETED via fold | Tests: 3021 (preserved -- 44 tests moved) | Files: 204->200 (-4) | Detail: see CHANGELOG-history.md cycle-58
- **Cycle 54-pickup (folds -- salvage of abandoned cycle-54 worktree)** -- Items: 4 fold ACs / 4 test files DELETED | Tests: 3021 (preserved -- 24 tests moved) | Files: 208->204 (-4) | Detail: see CHANGELOG-history.md cycle-54-pickup
- **Cycle 57 (folds + sentinel-DELETE)** -- Items: 6 ACs / 5 test files DELETED via fold + 1 vacuous test DELETED | Tests: 3022->3021 (-1) | Files: 213->208 (-5) | Detail: see CHANGELOG-history.md cycle-57
- **Cycle 56 (folds, dep-CVE re-confirm)** — Items: 5 fold sources → 6 receivers; 26 tests folded; ruff fix + chore commit | Tests: 3026 (preserved) | Files: 219 → 214 (-5) | Detail: see CHANGELOG-history.md cycle-56 + docs/superpowers/decisions/2026-05-02-cycle56-folds-{design,plan}.md

#### 2026-05-02 — cycle 55 (First MiMo trial cycle: freeze-and-fold continuation + dep-CVE re-confirm)

- Items: 10 ACs / 0 src files modified / 4 test files DELETED via fold (`test_v01003_graph_fixes.py`, `test_v01007_evolve_fixes.py`, `test_v01009_ingest_aux_fixes.py`, `test_v01011_review_feedback_fixes.py`) + 4 receivers EDITED (`test_graph.py`, `test_evolve.py`, `test_ingest.py`, `test_review.py`) + BACKLOG.md (Phase 4.5 HIGH #4 progress note appended + litellm CVE block re-confirmed cycle-52 → cycle-55 with new python-dotenv==1.0.1 transitive-pin discovery) + CLAUDE.md / docs/reference/{testing,implementation-status}.md narrative + 2 cycle-55 decision docs / 4 fold commits + 1 doc-sync `+TBD` per C30-L1 + self-review.
- Tests: 3025 → 3026 (+1 from R1-fix behavioral spy `test_graph_stats_avoids_per_node_degree_calls` per Q1 design upgrade — folds initially moved 3+3+3+3 = 12 tests across 4 receivers (net 0), R1 review caught design-deviance MAJOR (spy upgrade not implemented), R1-fix commit lands the spy + renames the orphan test per design Q1 spec). Windows local: 3015 passed + 11 skipped.
- Scope:
  Pure tests/ + BACKLOG.md + docs/ hygiene cycle. Zero `src/kb/` changes. Zero new dependencies. **First real-cycle exercise of the project-scoped `dev-mimo-opus` skill**: ran in parallel with worktree-cycle-53 (4/4 folds done, no PR yet) and worktree-cycle-54 (mid-cycle src/kb/{compile/compiler.py, utils/io.py} fixes + 4 different fold picks), receivers verified disjoint. AC1 included a C11-L1 vacuous-test upgrade (`test_graph_stats_uses_precomputed_out_degrees` → `test_graph_stats_orphans_includes_isolated_node`, drop `inspect.getsource` grep). AC4 used Q2 host-shape preservation (C40-L5) keeping `test_embedding_dim_resolved` with the refine_page tests despite touching config + embeddings — split would create merge surface with parallel cycle-53 test_query.py edits. **First MiMo trial data point**: `mimocoding-rescue` and `mimochat-rescue` not registered in active subagent set; Step 8 plan-gate fell back to `codex:codex-rescue` (REJECT 5 gaps closed inline per C21-L1); Steps 7/9/17 ran in primary session per cycle-13 L2 + C37-L5 sizing heuristic. Step 15 litellm patch attempted + reverted: pip silent-downgrades click + python-dotenv to satisfy litellm 1.83.7 hard-pins, introducing CVE-2026-28684 (HIGH symlink) on python-dotenv 1.0.1 — reverted; BACKLOG entry updated with finding.
- Detail: [history archive](CHANGELOG-history.md#2026-05-02--cycle-55--first-mimo-trial-cycle-freeze-and-fold-continuation--dep-cve-re-confirm)

#### 2026-04-28 — cycle 52 (Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm)

- Items: 13 ACs / 0 src files modified / 4 test files DELETED via fold (`test_cycle19_prune_base_consistency_anchor.py`, `test_cycle19_lint_redundant_patches.py`, `test_cycle15_load_all_pages_fields.py`, `test_cycle15_query_tier1_wiring.py`) + 4 receivers EDITED (`test_compile.py`, `test_lint.py`, `test_utils.py`, `test_query.py`) + BACKLOG.md (4 dep-CVE timestamp refreshes cycle-51 → cycle-52 + 2 Dependabot drift bumps cycle-51+ → cycle-52+ + 1 resolver-conflict refresh + 3 cycle-52+ → cycle-53+ tag bumps + Phase 4.5 HIGH #4 progress note appended + new cycle-53+ behavioral-upgrade candidate filed for AC1 prune-base anchor per C40-L3) + CLAUDE.md / README.md / docs/reference/{testing,implementation-status}.md narrative + 3 cycle-52 decision docs / 4 implementation commits + +TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds move 2+1+6+2 = 11 tests + 1 helper across 4 receivers; net 0 because moves preserve names). Windows local: 3014 passed + 11 skipped in 138.41s.
- Scope:
  Pure tests/ + BACKLOG.md + docs/ hygiene cycle. Zero `src/kb/` changes. Zero new dependencies. R1 DeepSeek V4 Pro returned APPROVE-WITH-AMENDMENTS — caught a real MAJOR for AC2 (post-fold self-exclusion guard would no longer skip the receiver file, causing potential false positive on test_lint.py drift). Step 5 promoted R1's amendment to binding decision (b) — replaced hardcoded source-filename string with `Path(__file__).resolve()` self-reference. R1's AC1 NIT (vacuousness claim arguable for inspect.getsource test) routed to a cycle-53+ BACKLOG behavioral-upgrade candidate per C40-L3.
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-52--backlog-hygiene--freeze-and-fold-continuation--dep-cve-re-confirm)

#### 2026-04-28 — cycle 51 (Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm)

- Items: 25 ACs / 0 src files modified / 4 test files DELETED via fold (`test_cycle12_conftest.py`, `test_cycle17_capture_prompt.py`, `test_cycle17_validators.py`, `test_cycle8_package_exports.py`) + 2 receivers EDITED (`test_v070.py`, `test_capture.py`) + BACKLOG.md (4 dep-CVE timestamp refreshes cycle-50 → cycle-51 + 2 Dependabot drift bumps cycle-50+ → cycle-51+ + 1 resolver-conflict refresh + 3 cycle-51+ → cycle-52+ tag bumps + Phase 4.5 HIGH #4 progress note appended) + CLAUDE.md / README.md / docs/reference/{testing,implementation-status}.md narrative + 4 cycle-51 decision docs / 4 implementation commits + +TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds move 2+5+5+6 = 18 method declarations across 2 receivers but parametrize expansion matches source so net 0). Windows local: 3014 passed + 11 skipped in 151.95s.
- Scope:
  Pure tests/ + BACKLOG.md + docs/ hygiene cycle. Zero `src/kb/` changes. Zero new dependencies. Step 2 threat-model SKIP per pure-test-fold (only dep-CVE baseline captured). C41-L1 in-fold behavioral upgrade applied to test_cycle17_capture_prompt fold: 3 of 5 tests had latent test-ordering dependency on `_PROMPT_TEMPLATE` lazy-init; switched to canonical `_get_prompt_template()` accessor per cycle-19 L2.
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-51--backlog-hygiene--freeze-and-fold-continuation--dep-cve-re-confirm)

#### 2026-04-28 — cycle 50 (Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm)

- Items: 25 ACs / 0 src files modified / 4 test files DELETED via fold (`test_cycle9_lint_checks.py`, `test_cycle45_lint_runner_order_invariant.py`, `test_cycle8_llm_telemetry.py`, `test_cycle9_mcp_path_validation.py`) + 3 receivers EDITED (`test_lint.py`, `test_llm.py`, `test_mcp_core.py`) + BACKLOG.md (4 dep-CVE timestamp refreshes cycle-49 → cycle-50 + 2 Dependabot drift bumps cycle-49+ → cycle-50+ + 1 resolver-conflict refresh + 3 cycle-50+ → cycle-51+ tag bumps + Phase 4.5 HIGH #4 progress note appended) + CLAUDE.md / README.md / docs/reference/{testing,implementation-status}.md narrative + 3 cycle-50 decision docs / 4 implementation commits + +TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds move 1+1+2+9 = 13 tests across 3 receivers; +1 helper class `_TelemetryFakeMessages` + 1 helper function `_install_telemetry_client` in test_llm.py renamed from cycle-8 source; +1 class `TestMcpWikiDirValidation` with 9 methods + `@staticmethod _missing_abs_path` in test_mcp_core.py). Windows local: 3014 passed + 11 skipped in 139.76s.
- Scope:
  Phase 4.5 HIGH #4 freeze-and-fold cadence match with cycle 49 (4 folds): smallest 4 remaining versioned files with collision-free canonical homes. AC1 fold `test_cycle9_lint_checks.py` (1506 B, 1 test on `check_source_coverage` YAML-load count) → `tests/test_lint.py` bare function inside existing `# ── Source coverage checks ─` section per Step-5 Q3 (no new section comment); imports gain `import frontmatter.default_handlers`. AC2 fold `test_cycle45_lint_runner_order_invariant.py` (1358 B, 1 test on `run_all_checks` enumeration order) → `tests/test_lint.py` bare function inside existing `# ── Runner tests ─` section with `EXPECTED_CHECK_ORDER` kept function-local per AC5 host-shape preservation (test_lint.py has no module-level constants); imports gain `from kb.lint import runner`. AC3 fold `test_cycle8_llm_telemetry.py` (2300 B, 2 tests + 2 helpers on `_make_api_call` telemetry contract) → `tests/test_llm.py` under new `# ── Telemetry: _make_api_call success path (cycle 50 fold) ─` section per Step-5 Q4; helpers renamed `_FakeMessages`→`_TelemetryFakeMessages` and `_install_client`→`_install_telemetry_client` per Step-5 Q1 (R1 amendment 1 — telemetry-scoped prefix matches receiver's `_make_*` factory-style naming pattern, prevents future helper-name collisions). AC4 fold `test_cycle9_mcp_path_validation.py` (2226 B, 9 tests on wiki_dir validation across kb_compile_scan/kb_lint/kb_evolve) → `tests/test_mcp_core.py` as new `TestMcpWikiDirValidation` class (single class with 9 methods + `@staticmethod _missing_abs_path` per Step-5 Q2 — single-class hosting matches existing `TestKbCaptureWrapper` / `TestKbCreatePageHintErrors` precedent for grouped behavior tests, over 3-sub-classes which would over-fragment); imports gain `from kb.mcp.health import kb_evolve, kb_lint`. AC5 each fold revert-checked per C40-L3 (`assert False` insertion → pytest -x FAIL confirmed → restored on the highest-coverage representative — fold 1: parses_yaml_once_per_page; fold 2: lint_runner_enumeration; fold 3: success_logs_info_record_without_prompt_leak; fold 4: kb_compile_scan_rejects_nonexistent_wiki_dir). Re-confirmed 4 pip-audit (diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1) + 2 Dependabot drift (litellm GHSA-r75f-5x8p-qvmc, GHSA-v4p8-mg3p-g94g) + 1 resolver-conflict (cycle-34 AC52) entries — all unchanged from cycle 49 baseline (`.data/cycle-50/cve-baseline.json` 21089 bytes; alerts-baseline.json 4 alerts: #12 ragas low, #13/14/15 litellm). Bumped cycle-50+ → cycle-51+ on 3 N/A prerequisite-missing entries (windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX off-by-one) — none of self-hosted Windows runner / POSIX shell / GHA-Windows reproducer became available during cycle 50. Bumped cycle-49+ → cycle-50+ on 2 Dependabot drift entries. Steps 1-3 + 5 + 7-13 + 16 ran primary-session per C37-L5 (≤25 ACs / 0 src files / primary holds full context post requirements). Step 4 R1 DeepSeek V4 Pro direct CLI (cycle-39 L1) returned APPROVE-WITH-MINOR-AMENDMENTS (3 load-bearing amendments + 5 risk flags + 8 CONDITIONS, all addressed at Step 5/Step 9); R2 SKIP per cycle-49 precedent (hygiene-only cycle, no security surface). Step 5 design decision gate primary-session per cycle-21 L1 — promoted DeepSeek's 3 amendments + added 12 binding CONDITIONS + 6 SCOPE-OUT items (deferred fold of test_cycle12_conftest.py + the 3 cycle-51+ items + LiteLLM CVE patch + Phase 5/6/7/8 candidates per user scope). Step 6 (Context7) + 9.5 (simplify) + 11.5 (existing-CVE patch) skipped per skip-eligibility (no third-party libs; 0 src/ diff; no patchable upstream — diskcache/ragas/pip empty fix_versions, litellm trio blocked by click==8.1.8 transitive per cycle-22 L4). Cycle-50 worktree at `D:/Projects/llm-wiki-flywheel-c50` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-branch diff = empty set; cycle 50 changes 0 dependencies).
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-50)

#### 2026-04-28 — cycle 49 (Backlog hygiene + freeze-and-fold continuation + dep-CVE re-confirm)

- Items: 18 ACs / 0 src files modified / 4 test files DELETED via fold (`test_cycle9_capture_runtime_guard.py`, `test_cycle9_mcp_app.py`, `test_cycle9_package_exports.py`, `test_cycle12_mcp_console_script.py`) + 2 test files modified as receivers (`test_v070.py`, `test_capture.py`) + BACKLOG.md (5 dep-CVE timestamp refreshes cycle-48 → cycle-49 + 2 Dependabot drift bumps cycle-47+ → cycle-49+ + 1 resolver-conflict refresh + 3 cycle-49+ → cycle-50+ tag bumps + Phase 4.5 HIGH #4 progress note appended) + CLAUDE.md / README.md / docs/reference/{testing,implementation-status}.md narrative + 3 cycle-49 decision docs / 5 implementation commits + TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds preserve all 6 source tests as 3 in `TestKbMcpConsoleScript` class methods + 1 bare in `test_capture.py` + 1 bare in `test_v070.py` + 1 in `TestMcpAppInstructions` class method). Windows local: 3014 passed + 11 skipped in 130.19s.
- Scope:
  Phase 4.5 HIGH #4 freeze-and-fold cadence step-up from cycle 48's 2 folds: 4 small folds (24/33/36/37 LOC each), file count 241 → 237 (-4), test count preserved at 3025. AC1 fold `test_cycle12_mcp_console_script.py` → `test_v070.py::TestKbMcpConsoleScript` (3 tests, class wrapping per cycle-43 L4 cohesion); AC2 fold `test_cycle9_capture_runtime_guard.py` → `test_capture.py` (bare function in mixed-host receiver); AC3 fold `test_cycle9_package_exports.py` → `test_v070.py` bare function (Step-5 AMENDED from class to bare-function per C40-L5 host-shape — test_v070.py is purely bare-function shaped pre-cycle-49); AC4 fold `test_cycle9_mcp_app.py` → `test_v070.py::TestMcpAppInstructions` with `@staticmethod _instruction_tool_groups` per cycle-47 L1 (helper homing). AC5 each fold revert-verified per C40-L3 (`assert False` injection → pytest -x FAIL → restored). Re-confirmed 4 pip-audit (diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1) + 2 Dependabot drift (litellm GHSA-r75f-5x8p-qvmc, GHSA-v4p8-mg3p-g94g) + 1 resolver-conflict (cycle-34 AC52) entries — all unchanged from cycle 48 baseline (`.data/cycle-49/cve-baseline.json` 21089 bytes; alerts-baseline.json 4 alerts: #12 ragas low, #13/14/15 litellm). Bumped cycle-49+ → cycle-50+ on 3 N/A prerequisite-missing entries (windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX off-by-one) — none of self-hosted Windows runner / POSIX shell / GHA-Windows reproducer became available during cycle 49. Steps 1-3 + 5 + 7-13 + 16 ran primary-session per C37-L5 (≤15 ACs / 0 src files / primary holds full context post requirements). Step 4 R1 DeepSeek V4 Pro direct CLI (cycle-39 L1) returned APPROVE-WITH-CONDITIONS (5 conditions, all addressed at Step 5/Step 9); R2 Codex SKIP per cycle-48 cadence match (hygiene-only cycle, no security surface). Step 5 design decision gate primary-session per cycle-21 L1 + cycle-48 precedent — promoted DeepSeek's 5 conditions + added 1 binding AMENDMENT (AC3 host-shape per C40-L5 — R1 DeepSeek did not flag this; primary caught at receiver inspection) + 6 additional binding conditions. Step 6 (Context7) + 9.5 (simplify) + 11 threat-model verify + 11.5 (existing-CVE patch) skipped per skip-eligibility (no third-party libs; zero src/ diff; pure hygiene cycle no I/O or trust boundary changes; no patchable upstream — diskcache/ragas/pip empty fix_versions, litellm trio blocked by click==8.1.8 transitive per cycle-22 L4). Cycle-49 worktree at `D:/Projects/llm-wiki-flywheel-c49` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-branch diff = empty set; cycle 49 changes 0 dependencies).
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-49)

#### 2026-04-28 — cycle 48 (Test-quality upgrades + freeze-and-fold + dep-CVE re-confirm)

- Items: 16 ACs / 1 src file modified (`src/kb/utils/pages.py` docstring augment per C41-L1) / 4 test files modified (2 deleted folds: `test_cycle9_evolve.py`, `test_cycle9_compiler.py`; 4 modified: `test_mcp_core.py` AC1 forward-protection patches, `test_models.py` AC2+AC3 contract upgrades, `test_evolve.py` + `test_compile.py` fold receivers) + BACKLOG.md (5 dep-CVE timestamp refreshes + 2 Dependabot drift + 1 resolver-conflict cycle-47 → cycle-48 + 3 cycle-48+ → cycle-49+ tag bumps + 2 resolved cycle-48+ upgrade-candidate entries removed + HIGH #4 progress note extended) + CLAUDE.md / docs/reference/{testing,implementation-status}.md / README.md narrative + 2 cycle-48 decision docs / 6 implementation commits + TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds preserve all 2 source tests as bare functions; AC1+AC2+AC3 modify in-place). Windows local: 3014 passed + 11 skipped.
- Scope:
  Test-quality upgrades closing the 2 cycle-48+ candidates filed by cycle-47 R2 Codex review: AC1 adds forward-protection `monkeypatch.setattr(_ingest_mod, "PROJECT_ROOT"/"RAW_DIR"/"SOURCE_TYPE_DIRS", tmp_path)` to 4 `TestKbCreatePageHintErrors` methods so tests reading `kb.mcp.ingest` globals directly (without first invoking an ingest tool to trigger `_refresh_legacy_bindings()`) see tmp_path values, not stale core (cycle-23 L5 + cycle-42 L3 same-class peer pattern). AC2 upgrades `TestSaveFrontmatterBodyVerbatim::test_body_content_with_trailing_newline` from substring asserts to exact body-region equality `text.split("---", 2)[2] == "\n\n" + body.rstrip("\n")` matching python-frontmatter's actual dumps convention; per C41-L1, `src/kb/utils/pages.py` `save_page_frontmatter` docstring updated to describe actual leading-blank-line + trailing-newline-strip behavior (the original "verbatim" claim was technically false; divergence caught when first AC2 attempt failed). AC3 spies on `kb.utils.io.atomic_text_write` (as bound in `kb.utils.pages`) and asserts `call_count == 1` + `path` arg — revert-verified: replacing `atomic_text_write(...)` with `path.write_text(...)` makes the test FAIL with "got 0 calls". Freeze-and-fold continuation (Phase 4.5 HIGH #4): 2 small folds — `test_cycle9_evolve.py` (20 LOC, 1 test) → `tests/test_evolve.py`, `test_cycle9_compiler.py` (28 LOC, 1 test) → `tests/test_compile.py`. File count 243 → 241 (note: cycle-47 doc said 241 but actual `find tests -maxdepth 1 -name '*.py' | wc -l` was 243 due to historical doc drift; cycle 48 brings actual into alignment with stated). Re-confirmed 4 pip-audit (diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1) + 2 Dependabot drift (litellm GHSA-r75f-5x8p-qvmc, GHSA-v4p8-mg3p-g94g) + 1 resolver-conflict (cycle-34 AC52) entries — all unchanged from cycle 47. Bumped cycle-48+ → cycle-49+ on 3 N/A prerequisite-missing entries (windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX off-by-one) — none of the prerequisites became available during cycle 48. Steps 1-9 + 10-12 + 16 ran primary-session per C37-L5 (≤15 ACs / 1 src file / primary holds full context). Step 4 R1 DeepSeek V4 Pro direct CLI (cycle-39 L1) returned APPROVE-WITH-CONDITIONS (4 conditions, all addressable in Step 9); R2 SKIP per cadence match with cycle 47. Step 5 design decision gate primary-session per cycle-21 L1 — promoted DeepSeek's 4 conditions + added C5 cycle-23 L5 self-healing rationale documentation. Step 6 (Context7) + 9.5 (simplify) + 11.5 (existing-CVE patch) skipped per skip-eligibility (no third-party libs; src/ diff is one-line docstring augment; no patchable upstream). Cycle-48 worktree at `D:/Projects/llm-wiki-flywheel-c48` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-branch diff = empty set; cycle 48 changes 0 dependencies).
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-48)

#### 2026-04-28 — cycle 47 (Backlog hygiene + dep-CVE re-confirm + freeze-and-fold continuation)

- Items: 18 ACs / 0 src files modified / 4 test files modified (1 NEW `tests/test_config.py` + 3 deleted `test_cycle{16_config_constants,11_task6_mcp_ingest_type,14_save_frontmatter}.py` source files + 2 receivers `test_mcp_core.py` + `test_models.py` appended) + BACKLOG.md (7 cycle-46 → cycle-47 stamp refreshes + AC4 pip-locator re-word + AC10 frontier replacement removing false-positive `test_cycle23_workflow_e2e.py` + AC11 Phase 4.5 HIGH #4 progress note appended + 3 cycle-47+ → cycle-48+ tag bumps) + CLAUDE.md / docs/reference/{testing,implementation-status}.md / README.md test+file count narrative + 5 cycle-47 decision docs / 5 implementation commits + TBD doc-sync + self-review.
- Tests: 3025 → 3025 (unchanged — folds preserve all 19 source tests as classes/methods in destinations: 5 in TestConfigConstants + 6 in TestKbCreatePageHintErrors + 8 in 5 SaveFrontmatter classes; design said 20 / 9 SaveFrontmatter but actual source had 8 — minor miscount, math still works). Windows local: 3014 passed + 11 skipped.
- Scope:
  Test-fold continuation (Phase 4.5 HIGH #4 freeze-and-fold rule): 3 small folds — `test_cycle16_config_constants.py` (38 LOC, 5 tests) → NEW `tests/test_config.py` as `TestConfigConstants` per Step-5 Q1 (greenfield destination, no canonical receiver existed); `test_cycle11_task6_mcp_ingest_type.py` (78 LOC, 6 tests) → `tests/test_mcp_core.py` as `TestKbCreatePageHintErrors` with `@staticmethod _assert_create_page_error` per Step-5 Condition 2 (NO module-level helper); `test_cycle14_save_frontmatter.py` (139 LOC, 8 tests / 5 classes) → `tests/test_models.py` as 5 classes incl. `TestSaveFrontmatterAtomicWrite` renamed from `TestAtomicWriteProof` per Step-5 N1 + Condition 3. File count 243 → 241 (net -2: -3 folded sources + 1 new test_config.py). Re-confirmed 4 pip-audit + 2 Dependabot drift + 1 resolver-conflict (line 158, AC13 scope-expanded per Step-5 M3) BACKLOG entries — all unchanged: diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 fix_versions=[]; pip 26.0.1 advisory metadata `vulnerable_version_range:<=26.0.1` + `first_patched_version:null` (extracted from `.vulnerabilities[0]`, NOT top-level keys — earlier jq `null` was misleading); litellm 1.83.14 wheel METADATA still pins click==8.1.8 (baseline wheel preserved at `.data/cycle-47/litellm-1.83.14-py3-none-any.whl`); 3 resolver conflicts persist verbatim. AC4 BACKLOG entry re-worded per Step-5 B1: pip is `.venv` installer, NOT a `requirements.txt` pin (`grep -nE "^pip==" requirements.txt` returns no hit). AC10 (Windows CI matrix re-enable) BACKLOG entry frontier replaced per Step-5 M2 with grep-proven ranked Thread/multiprocessing candidates (top-3: cycle-25 dim_mismatch, cycle-23 rebuild_indexes, cycle-24 lock_backoff); REMOVED false-positive `test_cycle23_workflow_e2e.py` (R2-grep confirmed ZERO Thread/MP hits). NO skipif markers applied (Step-5 Q3 strict-defer per cycle-36 L1 — no GHA-Windows reproducer; investigation deferred to cycle-48+). Bumped cycle tags `(cycle-47+)` → `(cycle-48+)` on 3 deferred CI items (windows-latest matrix, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX) per cycle-46 precedent. Steps 1-3 + 7-13 + 16 ran primary-session per C37-L5 (≤15 ACs / 0 src files / primary holds context); Step 4 design eval ran in parallel R1 DeepSeek V4 Pro direct CLI (cycle-39 L1) + R2 Codex via codex:codex-rescue agent dispatch — R1 APPROVE, R2 APPROVE WITH AMENDMENTS (2 blockers + 3 majors + 1 nit; R2 caught real issues: B1 pip pin, B2 file-count drift, M3 7th `cycle-46 re-confirmed` stamp) — Step 5 Opus subagent gate resolved Q1-Q5 + B1+B2 + M1+M2+M3 with HIGH confidence + 12 binding CONDITIONS + 10 SCOPE-OUT items. Step 4 R2 agent's summary mis-named the AC8 source file (`test_cycle19_create_page_hints.py` instead of `test_cycle11_task6_mcp_ingest_type.py`) — full output was correct; agent summary unreliable. Step 5 design grep over-counted `cycle-46 re-confirmed` literal (Opus claimed 7 hits including lines 170/172, but those use `cycle-37/38/39/40/41/46 re-confirmed drift persists` pattern — not literal `cycle-46 re-confirmed`); intent (refresh all 7 entries) honored. Step 6 (Context7) + 9.5 (simplify) + 11.5 (existing-CVE patch) skipped per skip-eligibility (no third-party libs; zero src/ diff; no patchable upstream). Cycle-47 worktree at `D:/Projects/llm-wiki-flywheel-c47` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-branch diff = empty set; cycle 47 changes 0 dependencies).
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-47)

#### 2026-04-28 — cycle 46 (Phase 4.6 LOW closeout — lint/_augment_*.py shim deletion + dep-CVE re-verify + BACKLOG hygiene)

- Items: 12 AC (AC1-AC12) / 3 src files modified (orchestrator.py imports + manifest.py drop _sync_legacy_shim + rate.py drop _sync_legacy_shim) + 2 src files deleted (_augment_manifest.py + _augment_rate.py) / 9 test files modified (8 path-string migrations across 36 sites + test_lint_augment_split.py anchor refresh + 1 new docstring forward-protection test) + BACKLOG.md (entire Phase 4.6 section deleted + 9 dep-CVE entries re-tagged cycle-41+/40+ → cycle-47+ + Phase 4.5 HIGH #4 progress note appended) + CLAUDE.md / docs/reference/testing.md / docs/reference/implementation-status.md / README.md test-count drift narrative + 4 cycle-46 decision docs / +TBD commits (Step-7 plan: 6 implementation + 1 doc-update + 1 self-review = 8 total)
- Tests: 3025 → 3025 (-1 from AC2 deletion of `test_augment_compat_shims_resolve_to_new_package`; +1 from AC2 addition of `test_run_augment_docstring_survives_cycle46_import_flip` per CONDITION 3 forward-protection; net 0). Windows local: 3014 passed + 11 skipped.
- Scope:
  Phase 4.6 LOW closeout — `lint/_augment_*.py` shim deletion deferred from cycle-44 → cycle-45 → cycle-46. Closes 2 of 2 Phase 4.6 BACKLOG entries (LOW lint shim files + MEDIUM mcp/core.py — the latter was stale documentation only since cycle-45 PR #65 already shipped the M3 split). Migrated 36 test patch sites across 8 test files from `kb.lint._augment_manifest` / `kb.lint._augment_rate` paths to `kb.lint.augment.manifest` / `kb.lint.augment.rate` per Q6 / cycle-24 L1 single-line literal `Edit replace_all=True` with mandatory post-edit grep verification. Switched 2 production caller imports in `src/kb/lint/augment/orchestrator.py:79-80` (function-local lazy imports inside `run_augment`) per cycle-23 L1 SAFE-confirmed-by-grep. Dropped `_sync_legacy_shim()` + `import sys` from `manifest.py` + `rate.py` per CONDITION 4 ruff F401 forced removal. Deleted `_augment_manifest.py` (27 LOC) + `_augment_rate.py` (25 LOC). Refreshed `test_lint_augment_split.py` cycle-44 anchor: dropped `test_augment_compat_shims_resolve_to_new_package`, inverted 2× `is_file()` to `not is_file()`, added `pytest.raises(ModuleNotFoundError)` behavioural assertions per CONDITION 2 / `feedback_test_behavior_over_signature` / C40-L3, added `test_run_augment_docstring_survives_cycle46_import_flip` per CONDITION 3 / cycle-23 L1 forward-protection. Re-confirmed 9 dep-CVE BACKLOG entries unchanged (4 advisories: diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all `fix_versions=[]` per pip-audit; pip 26.1 GHSA-58qw-9mgm-455v advisory metadata still `firstPatchedVersion: null` per `gh api graphql` — DO NOT bump pin per cycle-22 L4; 3 resolver conflicts persist; 2 Dependabot drift entries litellm GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g still not emitted by pip-audit; litellm 1.83.14 wheel METADATA still pins click==8.1.8). Bumped cycle tags `cycle-41+` / `cycle-40+` → `cycle-47+` on all 9+3 deferred items per cycle-23 L3 + cycle-39/40/41 precedent. Multi-site doc-sync per C26-L2 + C39-L3: corrected 2-file drift (CLAUDE.md said 3027/244, testing.md/implementation-status.md/README.md said 3019/241; cycle 45 ship state was 3027/244 but cycle 45 CI hotfix #67 deleted test_cycle45_init_reexports_match_legacy_surface.py without updating doc sites). Steps 1-2 + 5 + 7-15 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Step 5 design gate via Opus subagent (mandatory) → 13 questions resolved with HIGH confidence (Q2 MEDIUM cosmetic) + 7 binding CONDITIONS satisfied; Step 4 + 6 + 9.5 SKIPPED per skip-eligibility (hygiene cycle, no third-party libs, signature-preserving deletion). Cycle-46 worktree at `D:/Projects/llm-wiki-flywheel-c46` per C42-L4 from-the-start isolation. Zero PR-introduced CVEs (Step 11 baseline-vs-postcheck diff = empty set; cycle 46 changes 0 dependencies).
- Detail: [history archive](CHANGELOG-history.md#2026-04-28--cycle-46)

#### 2026-04-27 — cycle 45 (M3 mcp/core.py split + AC32-AC34 regression tests; M1/M2/M4 already shipped via cycle 44 parallel)

- Items: 8 ACs (M3 AC19+AC20+AC22+AC23+AC24 + AC32+AC33+AC34) / 5 src files (mcp/{core,ingest,compile,__init__,health}.py — 1149 LOC core split into 447 LOC core + 612 LOC ingest + ~140 LOC compile) / 3 new test files / 4 commits
- Tests: 3019 → 3027 (+8). Windows local: 3016 passed + 11 skipped.
- Scope:
  M3 mcp/core.py split — extract 5 ingest tools to mcp/ingest.py; extract 2 compile tools to mcp/compile.py; update kb/mcp/__init__.py:_register_all_tools() to import all 6 modules; mcp/core.py reduced from 1149 LOC → 447 LOC under hard ≤450 cap; 28 MCP tools registered. AC32-AC34 regression coverage: package-constants propagation parametrised, lint-runner-order snapshot. Cycle 44 (PR #63) merged in parallel with M1+M2+M4+AC10+AC28-30 — cycle 45 PR #65 was rebased onto cycle-44's main, dropping redundant M1/M2/M4 commits, dropping 3 surface-regression parametrize cases that tested cycle-45-specific structural choices that cycle 44 chose differently, and retargeting source-coverage propagation to cycle 44's actual checks.consistency module. Per cycle-43 L4 + new cycle-45 L1 lesson on parallel-cycle merge handling.
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-45)

#### 2026-04-27 — cycle 44 (Phase 4.6 close: M1+M2+M4 splits + AC10 fold + vacuous-test upgrades)

- Items: 23 AC + 7 CONDITIONS / 25+ src files (M1: 8 new submodules + 1 delete; M2: 9 new submodules + 2 shim rewrites + 1 delete; M4: utils/io.py + capture.py; cli.py + mcp/health.py canonical imports) / 4 commits + 1 doc-update + 1 self-review = 6 total
- Tests: 3007 → 3019 (+12). Windows local: 3008 passed + 11 skipped. File count 240 → 241 (+1: −1 `test_cycle12_sanitize_context.py` fold; +2 new `test_lint_*_split.py`).
- Scope: Phase 4.6 closure. **M1** (`lint/checks.py` 1046 LOC → 8 per-rule submodules in `kb/lint/checks/`); **M2** (`lint/augment.py` 1189 LOC → 9-file `kb/lint/augment/` package; `_augment_manifest.py` + `_augment_rate.py` kept as compat shims for cycle-45 deletion per design Q2); **M4** (`atomic_text_write` gains keyword-only `exclusive: bool = False`; `_exclusive_atomic_write` removed from `capture.py` — was effectively a test fixture). **M3** (`mcp/core.py` split) DEFERRED to cycle 45 per design Q13 (≥50 patch sites; cycle-22 L4 conservative posture). Cycle-43 carry-overs closed: **AC fold-1** (`test_cycle12_sanitize_context.py` → `test_mcp_core.py` + 3 new behavioral sanitize tests, ≥6 per CONDITION 5); **AC28** (delete `test_graph_builder_documents_case_sensitivity_caveat`); **CONDITION 8** (was AC29; cache-stability behavioral test pinning the documented stale-read contract — non-goal #1 forbids cache-key change); **CONDITION 9** (was AC30; `file_lock` dead-PID test patching `kb.utils.io.os.kill` to raise `ProcessLookupError`). Patch migrations: 22 `call_llm_json` sites → `kb.lint.augment.proposer.call_llm_json`; 2 `run_augment` sites → `kb.lint.augment.orchestrator.run_augment` + `cli.py` + `mcp/health.py` production callers also updated to import from orchestrator directly (C42-L3 deviation discovered mid-cycle: re-exports invalidate patches on PRODUCTION callers, not just tests). Step 4 R1 DeepSeek direct CLI + R2 Codex agent parallel; Step 5 Opus resolved Q1-Q14 with HIGH confidence + 7 binding CONDITIONS; Step 9 hybrid (primary for TASKs 1-7, 12-14; Codex subagents for M1 + M2 splits in parallel — both completed without main-worktree contamination after Codex self-detected and reverted via git restore). Step 6 + 9.5 skipped per skip-eligibility (no third-party libs; signature-preserving refactor). Cycle-44 worktree at `D:/Projects/llm-wiki-flywheel-c44` per cycle-43 L1 from-the-start isolation; main worktree never touched. Zero PR-introduced CVEs (all 4 baselined advisories pre-existing — diskcache / ragas / litellm / pip — same blocked-no-upstream-fix state as cycles 32-43).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-44)

#### 2026-04-27 — cycle 43 (Test-fold continuation — Phase 4.5 HIGH #4 — 11 folds + 4 BACKLOG entries)

- Items: 12 AC (AC1-AC12) / 0 src (`src/kb/` untouched — pure test-fold + BACKLOG cycle) / 9 test-file edits (`tests/test_mcp_browse_health.py` +28 / -1; `tests/test_ingest.py` +109 / -3; `tests/test_query.py` +73 / -1; `tests/test_paths.py` +131 / -1; `tests/test_utils.py` +137 / -1; `tests/test_models.py` +199 / -3; `tests/test_utils_io.py` +136 / -2; `tests/test_lint.py` +93 / -1; `tests/test_cli.py` +103 / -1) + 11 test-file deletes (cycle 10: browse, extraction_validation, vector_min_sim; cycle 11: conftest_fixture, ingest_coerce, utils_pages; cycle 12: config_project_root, frontmatter_cache, io_sweep; cycle 13: augment_raw_dir, sweep_wiring) + BACKLOG.md (Phase 4.5 HIGH #4 progress note refresh + 3 vacuous-test upgrade candidates + 1 AC10 deferral) + CLAUDE.md / docs/reference/testing.md / docs/reference/implementation-status.md / README.md test-count drift narrative + 5 cycle-43 decision docs / +TBD commits (Step-7 plan expected 11 folds + 1 BACKLOG consolidation + 1 ruff-cleanup + doc-update + self-review = ~14 total; actual TBD post-Step 14)
- Tests: 3014 → 3007 (−7: 11 folds preserve count; AC5 design-amendment per cycle-17 L3 dropped 7 _coerce_str_field bare-function duplicates redundant with AC2's parametrized 10-row fold; net ─7. Full Windows local: 2996 passed + 11 skipped, was 3003 passed + 11 skipped at cycle-41 baseline. File count 251 → 242 via 11 source-file deletions.)
- Scope:
  Phase 4.5 HIGH #4 (`tests/` coverage-visibility) — folded 11 cycle-10/11/12/13 era versioned test files into their canonical homes per cycle-4 L4 freeze-and-fold rule. AC10 (`test_cycle12_sanitize_context.py` → `test_mcp_core.py`) DEFERRED to cycle 44+ due to active cycle-42 Phase 4.6 mcp/* dedup interference (the `_sanitize_conversation_context` symbol survives cycle-42, but co-location with cycle-42's surrounding `mcp/core.py` edits creates merge surface). AC7 wrapped 5 reload-using config tests in `TestProjectRootResolution` class with autouse `_restore_config_after_test` fixture for cycle-19 L2 / cycle-20 L1 reload-isolation; AC11+AC12 preserved source class structure into bare-function hosts (cycle-40 L5 host-shape rule allows class addition for cohesive multi-test sets). AC13 filed 4 BACKLOG entries: 3 vacuous-test upgrade candidates (`test_graph_builder_documents_case_sensitivity_caveat`, `test_load_page_frontmatter_docstring_documents_mtime_caveat`, `test_cycle12_io_doc_caveats_are_present` — all docstring-introspection patterns flagged per C40-L3 do-not-auto-upgrade rule, with concrete behavior-based replacement plans) + 1 deferral note for AC10. AC14 multi-site test-count grep per C26-L2 + C39-L3 (CLAUDE.md / testing.md / implementation-status.md / README.md) — all updated to 3007 / 242 narrative. Steps 1-2 + 5 + 7 + 9-15 ran primary-session+subagent (Step 4 R1 DeepSeek V4 Pro via direct CLI per cycle-39 L1; Step 4 R2 Codex via agent dispatch in parallel — both returned full reviews); Step 5 Opus subagent resolved 10 questions with HIGH confidence + 10 binding CONDITIONS; Step 6 (Context7) and 9.5 (simplify) skipped per skip-eligibility (no third-party libs, test-only diff). Major operational lesson surfaced for Step 16: parallel cycle-42 session sharing the working tree caused 2 mistaken commits + lost stash mid-cycle; recovered via cherry-pick + `git worktree add D:/Projects/llm-wiki-flywheel-c43 cycle-43-test-folds` for true isolation (skill-patch candidate). Zero PR-introduced CVEs (Step 11 baseline-vs-postcheck diff = empty set; same 4 advisories as cycle 41/42 baseline — diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all still no-upstream-fix or blocked-by-transitive).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-43)

#### 2026-04-27 — cycle 42 (Phase 4.6 small dedup batch — Phase 4.6 MEDIUM M1+M2+M3 + LOW L1+L2+L4+L5)

- Items: 7 AC (M1 cli._truncate / M2 mcp.app._rel / M3 query/engine cache-keys / L1 lint/augment._load_purpose_text / L2 mcp.app._sanitize_error_str wrapper / L4 query rephrasing relocation / L5 feedback+review __init__) / 6 src files (cli.py, mcp/{app,browse,health,quality,core}.py, query/{engine,rewriter}.py, lint/augment.py, feedback/__init__.py, review/__init__.py) / 3 commits + 1 doc-update + 1 self-review = 5 total
- Tests: 3014 → 3014 (+0; pure behavior-preserving dedup. 3003 passed + 11 skipped local Windows)
- Scope: collapse 7 Phase 4.6 DeepSeek-audit MEDIUM/LOW duplications — three near-identical cache-key helpers fold into a single `_compute_cache_key`; `_truncate` / `_rel` / `_sanitize_error_str` MCP-app passthroughs deleted in favour of canonical `kb.utils.text.truncate` / `kb.utils.sanitize.{_rel,sanitize_error_text}`; rephrasing-for-UI helpers moved from `query/engine.py` to `query/rewriter.py` alongside `rewrite_query`; `lint/augment._load_purpose_text` now delegates to LRU-cached `kb.utils.pages.load_purpose`; empty `feedback/` and `review/` `__init__.py` gain module docstring + explicit empty `__all__`.
- Detail: [history archive](CHANGELOG-history.md#cycle-42)

#### 2026-04-27 — cycle 41 (Backlog hygiene + freeze-and-fold continuation + C40-L3 docstring-grep upgrade + dep-drift re-verification)

- Items: 6 AC (AC1-AC6) / 1 src (`src/kb/compile/compiler.py` docstring alignment, 6 lines net) / 4 test-file edits (`tests/test_mcp_browse_health.py` +212 / -0; `tests/test_capture.py` +97 / -2; `tests/test_mcp_quality_new.py` +60 / -1; `tests/test_cli.py` +146 / -2; `tests/test_compile.py` +44 / -10) + 4 test-file deletes (`tests/test_cycle10_validate_wiki_dir.py` -224; `tests/test_cycle10_capture.py` -97; `tests/test_cycle10_quality.py` -67; `tests/test_cycle11_cli_imports.py` -159) + BACKLOG.md (cycle-41 re-confirmation tags + C40-L3 entry deletion) + CHANGELOG/CHANGELOG-history/CLAUDE.md test-FILE count narrative / +TBD commits (Step-9 expected 5 implementation + 1 doc-update + 1 self-review = 7 total)
- Tests: 3014 → 3014 (+0: folds preserve count; C40-L3 1 docstring test → 1 behavior test net 0; file count 255 → 251 via 4 source-file deletions; full Windows local: 3003 passed + 11 skipped, unchanged from cycle-40 baseline)
- Scope:
  Continued the cycle-4 freeze-and-fold rule (Phase 4.5 HIGH item #4) by folding four more cycle-10/11 era test files into their canonical homes. AC1 folded `tests/test_cycle10_validate_wiki_dir.py` (8 tests + 1 helper covering `_validate_wiki_dir` + 4 MCP tools that wrap it) into `tests/test_mcp_browse_health.py` as a "Cycle 10 AC15 — wiki_dir validation hardening" section. AC2 folded `tests/test_cycle10_capture.py` (4 tests covering UUID-boundary fence + slow-LLM captured_at + raw_captures docstring invariant) into `tests/test_capture.py` per cycle-39 sibling-fold precedent. AC3 folded `tests/test_cycle10_quality.py` (2 tests covering `kb_refine_page` + `kb_affected_pages` warning-degradation paths) into `tests/test_mcp_quality_new.py`. AC4 folded `tests/test_cycle11_cli_imports.py` (8 tests: 6 CLI runner smoke + 2 short-circuit subprocess tests) into `tests/test_cli.py`. AC5 closed BACKLOG entry C40-L3: replaced the vacuous docstring-grep test `test_detect_source_drift_docstring_documents_deletion_pruning_persistence` (asserted only that 'deletion-pruning' and 'save_hashes=False' appeared in the docstring — would have survived a behavior revert per `feedback_inspect_source_tests`) with `test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted`, which seeds a manifest with a deleted-source entry, calls `detect_source_drift`, and asserts the manifest bytes are byte-identical post-call. The new assertion fails on revert of cycle 4 R1 Codex MAJOR 3 (the `elif deleted_keys: save_manifest(...)` removal under `save_hashes=False`). Discovered the cycle-10 docstring text was OUTDATED: it claimed "deletion-pruning is always persisted even when save_hashes=False" but cycle 4 made `find_changed_sources` fully read-only on that branch — fixed the docstring to match current behaviour (6-line src/ delta). AC6 re-verified all six cycle-40+ tagged carry-overs against the live pip-audit + Dependabot baselines (state matches cycle 40 verbatim — diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all still no-upstream-fix; three resolver conflicts persist; two Dependabot drift entries still NOT emitted by pip-audit; litellm 1.83.14 wheel METADATA still pins `Requires-Dist: click==8.1.8`). Steps 1-13 ran primary-session per C37-L5 (≤15 ACs / 1 src file / primary holds context); Steps 3 (brainstorming), 4 (design eval), and 6 (Context7) skipped per their skip-eligibility rules (pure hygiene, trivial, no third-party libs); Step 9.5 (simplify) skipped per <50 LoC src trivial-diff rule (6-line docstring delta only). Zero PR-introduced CVEs (Step 11 baseline-vs-postcheck diff = empty set). Step 11 same-class peer scan: zero new path-containment / injection / secrets sites added (test fold + behavior test rewrite + docstring fix only).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-41)

#### 2026-04-27 — cycle 40 (Backlog hygiene + freeze-and-fold continuation + dep-drift re-verification)

- Items: 11 AC (AC1-AC11) / 0 src (`src/kb/` untouched — test fold + BACKLOG + doc-sync only) / 4 test-file edits (`tests/test_mcp_browse_health.py` +90 / -0; `tests/test_compile.py` +14 / -0; `tests/test_utils_text.py` +13 / -0; `tests/test_query.py` +51 / -1) + 3 test-file deletes (`tests/test_cycle10_safe_call.py` -75; `tests/test_cycle10_linker.py` -13; `tests/test_cycle11_stale_results.py` -50) + BACKLOG.md (8 hunks: 7 cycle-40 markers on dep-CVE/resolver/Dependabot-drift entries + 1 Phase 4.5 HIGH #4 progress marker) + CHANGELOG/CHANGELOG-history/CLAUDE.md/docs/reference/README test-FILE count narrative + 4 cycle-40 decision docs / +TBD commits (Step-7 plan expected 5 implementation + 1 self-review = 6 total)
- Tests: 3014 → 3014 (+0: folds preserve count; file count 258 → 255 via 3 source-file deletions; full Windows local: 3003 passed + 11 skipped, unchanged from cycle-39 baseline)
- Scope:
  Continued the cycle-4 freeze-and-fold rule (Phase 4.5 HIGH item #4) by folding three more cycle-10/11 era test files into their canonical homes. AC1 folded `tests/test_cycle10_safe_call.py` (5 tests, sanitization at MCP boundary) into `tests/test_mcp_browse_health.py` as `class TestSanitizeErrorStrAtMCPBoundary` per cycle-39 class-precedent for thematic clusters. AC2 split `tests/test_cycle10_linker.py` (2 misnamed tests — neither was actually about linker.py) by actual symbol ownership: test 1 (`detect_source_drift` docstring contract) → `tests/test_compile.py` Compiler section as bare function; test 2 (`wikilink_display_escape` pipe behavior) → `tests/test_utils_text.py` wikilink section as bare function. AC3 folded `tests/test_cycle11_stale_results.py` (4 tests, `_flag_stale_results` edge cases) into `tests/test_query.py` as `class TestFlagStaleResultsEdgeCases` with the cycle-15 AC1 explanatory comment about the removed `20260101` int parametrize case preserved verbatim. AC4-AC10 re-verified all seven cycle-39+ tagged carry-overs against the live pip-audit + Dependabot baselines (state matches cycle 39 — diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all still no-upstream-fix; three resolver conflicts persist verbatim; two Dependabot drift entries still NOT emitted by pip-audit on live env). Notable cycle-40 finding: pip 26.1 was published TODAY 2026-04-27 (now LATEST per `pip index versions pip`), but the GHSA-58qw-9mgm-455v advisory metadata still shows `vulnerable_version_range: <=26.0.1` with `patched_versions: null` — pip-audit therefore continues to emit empty `fix_versions`. Conservative posture per cycle-22 L4: do NOT bump the pip pin until the advisory or PyPA security disclosure confirms 26.1 patches the CVE; track for next cycle. AC11 marker-appended on Phase 4.5 HIGH #4 BACKLOG entry: 4 files folded across cycles 39+40 (1 + 3); tests/ file count 258 → 255 via this cycle's deletions; HIGH item remains open with ~200+ versioned files still to fold across future cycles. Steps 1-13 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Steps 3 (brainstorming), 4 (design eval), 6 (Context7), and 9.5 (simplify) all skipped per their skip-eligibility rules (pure hygiene, trivial, no third-party libs, zero src changes). Step 5 design gate ran via Opus subagent per skill rule despite zero open questions → 6 questions resolved with HIGH confidence + 15 binding CONDITIONS; ALL 15 satisfied by Step 9 implementation. All 6 threat-model checklist items verified clean (T1 PR-introduced CVE diff = empty since cycle 40 changes zero deps; T2-T4 baselines match; T5 deferred-promise BACKLOG tags consistent post-re-tag; T6 test-count invariant 3014).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-40)

#### 2026-04-27 — cycle 39 (Backlog hygiene + dep-drift re-verification + cycle-38 test fold)

- Items: 11 AC (AC1-AC11) / 0 src (`src/kb/` untouched — BACKLOG + test fold + doc-sync only) / 1 test-file edit (`tests/test_capture.py` +180 / -0) + 1 test-file delete (`tests/test_cycle38_mock_scan_llm_reload_safe.py` -192) + BACKLOG.md (10 hunks: 7 re-confirm markers + 3 cycle-39+→cycle-40+ re-tags + 1 resolved-fold-entry deletion) + CHANGELOG/CHANGELOG-history/CLAUDE.md/docs/reference test-count narrative + README test/file count + 4 cycle-39 decision docs / +TBD commits (Step-5 D7 expected 4 implementation + 1 self-review = 5 total; actual 5 implementation post-Codex-NIT fixes + 1 Step-16 = 6 total post-merge)
- Tests: 3014 → 3014 (+0: fold preserves count; file count 259 → 258 via cycle-38 file deletion; full Windows local: 3003 passed + 11 skipped, unchanged from cycle-38 baseline)
- Scope:
  Backlog hygiene cycle. Re-confirmed seven cycle-39+ tagged carry-over entries against the live pip-audit + Dependabot baselines: four no-upstream-fix CVEs (`diskcache 5.6.3 / CVE-2025-69872`, `ragas 0.4.3 / CVE-2026-6587`, `litellm 1.83.0 / GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g`, `pip 26.0.1 / CVE-2026-3219`), three resolver conflicts (cycle-34 AC52 carry-over: `arxiv requests~=2.32.0 vs 2.33.0`, `crawl4ai lxml~=5.3 vs 6.1.0`, `instructor rich<15.0.0 vs 15.0.0`), and two Dependabot pip-audit drift entries (litellm `GHSA-r75f-5x8p-qvmc` + `GHSA-v4p8-mg3p-g94g` reported by Dependabot but still NOT emitted by pip-audit on the live env). litellm upgrade still ResolutionImpossible: `pip download litellm==1.83.14 --no-deps` zipfile metadata shows `Requires-Dist: click==8.1.8` (no relaxation across 7 patch releases since cycle 32 baseline). Folded `tests/test_cycle38_mock_scan_llm_reload_safe.py` into `tests/test_capture.py::TestMockScanLlmReloadSafety` per cycle-4 L4 freeze-and-fold rule and cycle 38's own self-tagged candidate note: 2 test methods + 4 module-level helpers + 1 autouse `_restore_kb_capture` fixture moved verbatim with full docstrings (manual revert-check guidance preserved per `feedback_test_behavior_over_signature`); defensive `import kb.capture as _kb_capture` line dropped (test_capture.py:20 `from kb.capture import (...)` already loads kb.capture under real PROJECT_ROOT before any fixture runs); `import importlib` added for the autouse fixture body. Re-tagged 3 cycle-39+ items deferred from cycle 39 (windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn investigation, `TestWriteItemFiles` POSIX off-by-one) to cycle-40+ per cycle-23 L3 deferred-promise BACKLOG sync — these need self-hosted Windows runner / POSIX shell access unavailable to the cycle-39 operator session. Steps 1-13 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Step 6 Context7 skipped per pure-stdlib/internal rule; Step 9.5 simplify pass skipped per <50 LoC src trivial-diff rule (zero src changes). All 4 threat-model items verified clean (T1 PR-introduced CVE diff = empty since cycle 39 changes zero deps; T2 `git diff origin/main -- src/` = 0 bytes; T3 folded tests pass + 3003+11 baseline preserved; T4 deferred-promise BACKLOG tags consistent post-re-tag).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-39)

#### 2026-04-26 — cycle 38 (POSIX test re-enable: mock_scan_llm dual-site + ruff T20)

- Items: 9 AC (AC0-AC6, AC9, AC10) / 0 src (`src/kb/` untouched — fixture + test-side fix) / 4 test-file edits (`tests/conftest.py`, `tests/test_capture.py`, `tests/test_mcp_core.py`, `tests/test_cycle38_mock_scan_llm_reload_safe.py` NEW) + 1 config (`pyproject.toml` ruff T20) + BACKLOG.md cleanup + 8 cycle-38 decision docs / +TBD commits (expected 3-4 squash-merge per Step-5 Q5 squash mandate)
- Tests: 3012 → 3014 (+2: cycle-38 mock_scan_llm reload-safety regression — case (a) baseline + case (b) dual-site contract assertion; full Windows local: 3003 passed + 11 skipped, was 2991 + 21 — 10 SDK tests + 2 atomic_text_write tests now exercise unconditionally)
- Scope:
  Closes 2 of 5 cycle-38 BACKLOG candidates: (a) Category A 10-test mock_scan_llm POSIX reload-leak (AC1-AC5) and (b) Category B 2-test atomic_text_write POSIX patch class (AC6 strict scope per design Q3). The original "reload-leak class" hypothesis (cycle-19 L2 / cycle-20 L1) was REFUTED by R2 Codex in Step-4 design eval — `kb.config` imports only stdlib (verified at `src/kb/config.py:3-9`), so reloading it cannot cascade to `kb.utils.llm` or `kb.capture`. The actual contamination source is `del sys.modules["kb.capture"]` + reimport in `tests/test_capture.py::TestSymlinkGuard` (line 700-714) which leaves the file's pre-collection bindings (line 20+ `from kb.capture import ...`) holding OLD module function objects whose `__globals__` is the OLD `__dict__` — patching `sys.modules["kb.capture"].call_llm_json` post-reimport doesn't reach the OLD `__dict__` that test functions actually use. AC0 refactors `TestSymlinkGuard` to subprocess so it never touches the parent's `sys.modules`, eliminating the contamination source. AC1 widens `mock_scan_llm` fixture to dual-site patch (`kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json`) as defense-in-depth. AC2 propagates the dual-site pattern to 2 inline `monkeypatch.setattr` sites in `test_capture.py`. AC3+AC4 drop 7 + 3 = 10 `@_REQUIRES_REAL_API_KEY` decorators. AC5 codifies the cycle-38 contract via order-independent assertion (the original sys.modules-deletion replay was full-suite-fragile). AC6 widens both atomic_text_write patches and drops `@_WINDOWS_ONLY` from `test_cleans_up_*` (strict scope per R2 grep table — only test_capture.py:741,754 had the cycle-36 risk pattern). AC9 re-confirms Dependabot drift unchanged (litellm GHSA-r75f / GHSA-v4p8 still not surfaced by pip-audit; expected no-change branch). AC10 deletes 2 resolved cycle-38+ BACKLOG entries; re-pins 2 unresolved Windows-CI candidates + 2 Dependabot-drift entries to cycle-39+; adds new cycle-39+ entry for fold-into-canonical of the new test file (cycle-4 L4 freeze-and-fold). Design Q5 amendment: ruff T20 (flake8-print) added to `pyproject.toml [tool.ruff.lint].select` for probe-print defense. AC7+AC8 (POSIX off-by-one slug + creates_dir) DEFERRED to cycle-39 per design M1 standing pre-auth — investigation requires deeper POSIX shell access; the `@_WINDOWS_ONLY` skipif on the 2 affected `TestWriteItemFiles` tests stays. ZERO new CI dimensions per cycle-36 L1 (windows-latest matrix + GHA spawn investigation re-pinned to cycle-39+).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-38)

#### 2026-04-26 — cycle 37 (POSIX symlink security fix + requirements split)

- Items: 9 AC across 5 file-grouped tasks / 1 src (`src/kb/review/context.py`) + 1 test (`tests/test_phase45_theme3_sanitizers.py`) + 6 NEW requirements files + 1 NEW test (`tests/test_cycle37_requirements_split.py`) + 1 README + 4 cycle-37 decision docs / +TBD commits (2 implementation + 1 doc-update; expected 3 total per Step-5 squash-merge cadence)
- Tests: 3005 → 3012 (+7: 6 cycle-37 requirements-split regression + 1 positive-case `test_qb_symlink_inside_raw_accepted`; full Windows local: 2991 passed + 21 skipped 0 failures)
- Scope:
  Closes 2 of 7 cycle-37 BACKLOG candidates filed at cycle-36 close: (a) production POSIX symlink security gap in `pair_page_with_sources` (cycle-36 ubuntu-probe surfaced; was masked by Windows-only `is_symlink()` check that became dead code after `.resolve()` was called first), and (b) requirements.txt split into runtime + 5 per-extra files mirroring `pyproject.toml [project.optional-dependencies]`. AC1 reorders `is_symlink()` capture to BEFORE `.resolve()` so the existing containment check at `context.py:86-103` (previously dead code on POSIX) actually fires; AC2 drops the cycle-36 `skipif(os.name != "nt")` marker on `test_qb_symlink_outside_raw_rejected`; AC3 adds positive-case `test_qb_symlink_inside_raw_accepted` covering legitimate intra-`raw/` symlinks (target stays within `raw_dir`). AC4-AC8 mirror pyproject extras as 6 new layered `requirements-{runtime,hybrid,augment,formats,eval,dev}.txt` files; AC7 amended at design gate Q3 from "shim" to "UNCHANGED" — `requirements.txt` stays as the 295-line frozen snapshot for backward-compat reproducibility, new files are additive. AC6 propagates cycle-35 L8 floor pin `langchain-openai>=1.1.14` into `requirements-eval.txt` (closes GHSA-r7w7-9xr2-qq2r). AC9 6-assertion regression test `test_cycle37_requirements_split.py` pins file existence + `-r` includes + floor pin + tomllib pyproject cross-check + snapshot-preservation. ZERO new CI dimensions per cycle-36 L1 (windows-latest matrix re-enable + remaining 5 cycle-37 candidates DEFERRED to cycle 38+: GHA-Windows multiprocessing spawn investigation, mock_scan_llm POSIX reload-leak, TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour, Dependabot pip-audit drift on 2 litellm GHSAs).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-37)

#### 2026-04-26 — cycle 36 (test+CI infrastructure hardening)

- Items: 26 designed AC, ~23 effective after Q7=B Area E deferral (AC1-AC13, AC18-AC25; AC14-AC17 + AC26 deferred to cycle 37 per Step-5 Q7=B; AC9 confirmed unchanged after pip-audit live-env audit) / 0 src (`src/kb/` untouched — test+CI infrastructure only) / 9 test-file edits + 2 NEW (`tests/_helpers/api_key.py`, `tests/test_cycle36_ci_hardening.py`) + 1 NEW dir (`tests/_helpers/`) + 4 config files (`.github/workflows/ci.yml`, `pyproject.toml`, `requirements.txt`, `SECURITY.md`) + 8 cycle-36 decision docs + BACKLOG.md / +TBD commits (backfill post-merge per cycle-30 L1; expected ~3 commits in three-commit sequence per Step-5 Q16/Q21 plus doc-update commits)
- Tests: 2995 → 3005 (+10 cycle-36 hardening tests in `tests/test_cycle36_ci_hardening.py`; full Windows local: 2985 passed + 20 skipped no failures; 10 added skips are `requires_real_api_key` markers on developer machine without real key)
- Scope:
  Closes 2 of 3 explicit cycle-36 BACKLOG follow-ups (strict pytest CI gate AC8 +
  cross-OS portability matrix AC11/AC12) + opportunistic CVE recheck (AC18-AC20).
  Area E (requirements split AC14-AC17) deferred to cycle 37 per Step-5 design Q7=B.
  Four-commit sequence on the cycle-36 PR: probe → fix → strict-gate → ubuntu-only
  pivot. Probe ubuntu-latest CI run surfaced 23 failures across 5 fragility classes;
  commit 2 applied marker fixes; commit 3 attempted matrix [ubuntu, windows] with
  strict-gate but windows-latest hit a SECOND hang at threading.py:355 after the
  cycle-23 multiprocessing skipif fired; commit 4 pivots to ubuntu-only single-OS
  strict-gate to close cycle-36 cleanly without more failed CI runs (windows-latest
  matrix re-enable filed as cycle-37 BACKLOG entry per CI-cost-discipline lesson). `pytest-timeout>=2.3`
  added to `[dev]` extras + `requirements.txt` with `[tool.pytest.ini_options]
  timeout = 120` global default to fail fast on hangs (was silent KeyboardInterrupt
  on cycle-23 multiprocessing spawn-bootstrap under GHA 6-hour ceiling).
  `tests/_helpers/api_key.py::requires_real_api_key()` predicate gates SDK-using
  tests on dummy CI key (matched via `sk-ant-dummy-key-` prefix per cycle-36 AC6).
  AC11 anti-Windows + anti-POSIX skipif markers data-driven from probe (AC11 list
  was partly mis-directional in requirements doc per Step-5 Q8 / R1-NEW-1; replaced
  with probe-driven list per Q5=B). AC5 mirror-rebind adds `kb.config.WIKI_DIR`
  patch to cycle-10 quality tests + `kb.mcp.quality.WIKI_DIR` to MCP phase 2 tests
  (cycle-19 L1 snapshot pattern; Windows CI previously masked these via cycle-23
  multiprocessing-hang at #1155). `pip-audit --ignore-vuln` switched from PowerShell
  backtick continuation to bash backslash for cross-OS shell compatibility (regression
  test in `test_cycle34_release_hygiene.py` updated to accept either form).
  SECURITY.md trim: removed parenthetical Dependabot-only `GHSA-r75f-5x8p-qvmc` from
  litellm row to satisfy C10 set-equality test; both that ID and new
  `GHSA-v4p8-mg3p-g94g` (created 2026-04-25T23:37Z) tracked as cycle-37 BACKLOG drift
  entries (pip-audit on live CI install env doesn't emit those IDs as of 2026-04-26
  — workflow `--ignore-vuln` set unchanged at 4 IDs). 5 NEW cycle-37 BACKLOG entries
  filed for deferred investigations: GHA-Windows multiprocessing spawn,
  mock_scan_llm POSIX reload-leak, `test_qb_symlink_outside_raw_rejected` POSIX
  symlink security gap, TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour,
  Dependabot pip-audit drift on 2 litellm GHSAs.
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-36)

#### 2026-04-26 — cycle 35 (Pre-Phase-5 BACKLOG batch + cycle-34 AC4e completion)

- Items: 18 designed AC + AC1b T1b proactive close + AC-Dep1 GitPython bump + AC-Doc1 doc updates = 21 effective / 4 src (`utils/sanitize.py`, `ingest/pipeline.py`, `mcp/core.py`, `requirements.txt`) + 2 NEW test files (`tests/test_cycle35_ingest_index_writers.py`, `tests/test_cycle35_mcp_core_filename_validator.py`) + 4 docs (`docs/architecture/architecture-diagram.html`, `architecture-diagram-detailed.html`, `architecture-diagram.png`, `docs/reference/conventions.md`) + 3 doc-anchor test re-anchors after the cycle-34-followup CLAUDE.md split + 1 ruff format normalization carryover / +TBD commits (backfill post-merge per cycle-30 L1)
- Tests: 2941 → 2995 (+54 passed: 6 new sanitize tests on `test_cycle33_mcp_core_path_leak.py` — including 4 AC1/AC1b/AC3 + 1 R1 Codex AC10 NIT + 2 R1 Sonnet PR-49 negatives — 8 new ingest index-writer tests, 39 new mcp/core filename-validator tests, +1 baseline net adjustment after the doc-anchor re-anchor)
- Scope:
  Closes 6 pre-Phase-5 BACKLOG items (M11 RMW lock + M12 UNC slash-normalize + M13 empty-list +
  M14 backtick-dedup + M15 filename validator parity + M21 architecture v0.11.0 sync) plus
  cycle-34's deferred AC4e diagram + PNG re-render. `_ABS_PATH_PATTERNS` gains TWO new
  alternatives — slash-form Windows UNC long-path `(?://\?/UNC/...)` (T1b) AND URI-guarded
  ordinary slash UNC `(?<!:)(?://...)` (T1) — plus a `(?<![A-Za-z])` lookbehind on the
  drive-letter alternative to prevent URL overmatch (`https://host/path` no longer collapses
  to `<path>` via the `s://` collision; pre-existing behavior since cycle 18 AC13 that no
  prior cycle had caught). `sanitize_error_text` per-path substitution now probes both
  single-backslash AND OSError-doubled-backslash forms of the filename attribute, closing
  the cycle-33 xfail-strict gap directly (XPASS-strict semantic forced marker removal in
  the same commit). `_update_sources_mapping` and `_update_index_batch` RMW windows wrapped
  in `file_lock(target_path)` (cycle-19 discipline; NO wrapper-level lock in
  `_write_index_files` because `file_lock` is `os.O_EXCL` non-reentrant per Step-5 Q7);
  empty-`wiki_pages` early-return at function entry kills the malformed `→ \n` line +
  suppresses the `_sources.md not found` warning (T8); membership + per-line scan switched
  to `escaped_ref` so backtick-bearing source_refs dedup correctly. New shared
  `_validate_filename_slug(filename) -> tuple[str, str | None]` helper rejects NUL byte /
  path separators / `..` / trailing dot or space (Windows trim aliasing) / non-ASCII
  (`[^\x00-\x7F]` blocks homoglyph + RTL-override + zero-width attacks) / over-200-char /
  Windows-reserved (via existing `_is_windows_reserved`); allows leading dot (`.env`) and
  leading dash (`-foo`) per Step-5 Q5. Wired into `_validate_file_inputs` so
  `kb_ingest_content` + `kb_save_source` reach validation parity with `kb_query.save_as`
  for the security-class checks (looser slug-equality contract appropriate to free-form
  names). Architecture diagrams bumped v0.10.0 → v0.11.0 with Playwright PNG re-render
  (closes deferred cycle-34 AC4e); canonical Playwright snippet codified in
  `docs/reference/conventions.md` to prevent a third deferral. Step-11b GitPython 3.1.46 →
  3.1.47 closes Dependabot GHSA-x2qx-6953-8485 + GHSA-rpm5-65cw-6hj4 (zero `import git` in
  `src/kb`; transitive tooling dep only).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-35)

#### 2026-04-26 — cycle 35 post-merge hotfix (CI pip-audit fix)

- Items: 1 / 1 src (`pyproject.toml`) / 1 commit (`cf0f996`)
- Tests: 2995 → 2995 (no test changes; CI pip-audit step now passes)
- Scope:
  Cycle-35 merge-commit CI failed at the `Pip-audit (live env)` step on a
  late-arrival LOW-severity advisory: `langchain-openai 1.1.10
  GHSA-r7w7-9xr2-qq2r` (DNS-rebinding SSRF in image-token-counting helper,
  fix at 1.1.14). The advisory landed DURING cycle 35, AFTER the Step-2
  baseline + Step-11.5 Dependabot read. `requirements.txt` already pinned
  `langchain-openai==1.1.14` (so the local `.venv` was patched), but CI's
  `pip install -e '.[dev,formats,augment,hybrid,eval]'` walks pyproject.toml
  extras instead — and the `[eval]` extra had no floor pin on
  langchain-openai (transitively pulled by ragas), so the CI resolver picked
  1.1.10. One-line fix: add `langchain-openai>=1.1.14` to the `[eval]`
  extra in pyproject.toml. Zero `import langchain_openai` in `src/kb`
  (transitive eval-only dep used by the ragas evaluation harness). CI step-
  level verification (cycle-34 L7) passed: every job step `success | skipped`,
  zero failures. Process miss documented as C35-L8 skill patch in
  `references/cycle-lessons.md`.
- Detail: see commit message for full failure-reproduction trace.

#### 2026-04-25 — cycle 34 (Release hygiene · v0.10.0 → v0.11.0)

- Items: 54 AC delivered (out of 57 designed; AC4e diagram bump DEFERRED to cycle 35 + AC49 boot-lean fix DROPPED at Step 9 with test-anchor retention + AC55 architecture-diagram-version-test DROPPED with the deferred AC4e) / 4 src (`pyproject.toml`, `src/kb/__init__.py`, `src/kb/config.py`, `src/kb/ingest/pipeline.py`) + 2 NEW user-facing files (`SECURITY.md`, `.github/workflows/ci.yml`) + 1 NEW test file (`tests/test_cycle34_release_hygiene.py`) + 4 doc/config files modified (`README.md`, `README.zh-CN.md`, `requirements.txt`, `.gitignore`) + 6 untracked deletions (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`, `docs/repo_review.md`, `docs/repo_review.html`) + 2 NEW review artifacts committed (`docs/reviews/2026-04-25-comprehensive-repo-review.{md,html}`) / +TBD commits (backfill post-merge per cycle-15 L4 + cycle-30 L1)
- Tests: 2923 → 2941 (+18 passed: cycle-34 release-hygiene regressions covering pyproject readme, extras structure, jsonschema runtime dep, version lockstep across pyproject + `__init__.py` + README badge, "No vectors" tagline absent regression, `.pdf` extension removal, scratch-file deletion regression, `.gitignore` patterns present, SECURITY.md required sections, CI workflow YAML structure, save_as= clarification in CLAUDE.md, comprehensive-review presence, kb_save_synthesis absent forward regression, README v0.11.0 badge, pip-audit -r flag, and boot-lean subprocess probe)
- Scope:
  Closes 8 P0/P1 ship-blocker findings from `docs/reviews/2026-04-25-comprehensive-repo-review.md`
  (Findings 1, 2, 3, 5, 6, 7, 9, 20). Packaging metadata aligned with code surface
  (`pyproject.toml.readme = "README.md"`; new `[project.optional-dependencies]` extras
  `hybrid` / `augment` / `formats` / `eval` / `dev` with concrete pin lower-bounds; `jsonschema`
  added to runtime dependencies for cycle-21 cli_backend; version 0.10.0 → 0.11.0 across
  pyproject + `src/kb/__init__.py`). New `SECURITY.md` documents narrow-role acceptance for the
  four open advisories (`diskcache 5.6.3` CVE-2025-69872, `litellm 1.83.0` GHSA-xqmj-j6mv-4862,
  `pip 26.0.1` CVE-2026-3219, `ragas 0.4.3` CVE-2026-6587) with verification grep + unblock
  conditions + per-cycle re-check cadence. New `.github/workflows/ci.yml` provides the first
  automated CI gate (ruff + pytest --collect-only + full pytest + pip check soft-fail +
  pip-audit with documented `--ignore-vuln` + `python -m build && twine check`); workflow
  ships with `permissions: read-all` (T1), `concurrency: cancel-in-progress` (NT5),
  `on: { push: { branches: [main] }, pull_request: {} }` (NT4 cost containment),
  `actions/{checkout,setup-python}@v6` (Step-6 Context7 amendment vs original @v4/@v5),
  and a dedicated `pip install build twine pip-audit` step (NEW-Q13 / AC50). README content
  drift fixes: `> blockquote` tagline at line 5 replaced from "No vectors. No chunking."
  to "Markdown-first; optional hybrid retrieval"; matching bullet at line 17 from
  "Structure, not chunks." to "Structure first, optional vectors."; PDF row removed from
  Supported File Formats with sentence directing at markitdown/docling; tests-2850 badge
  → tests-passing-brightgreen (drift surface eliminated per Q6); v0.10.0 → v0.11.0 badge;
  Quick Start expanded with extras-aware install paths. `src/kb/config.py` removes `.pdf`
  from `SUPPORTED_SOURCE_EXTENSIONS` (Finding 7); `src/kb/ingest/pipeline.py` updates the
  binary-rejection message at lines 1261-1265 to enumerate supported extensions for better
  UX, and the now-stale comment at line 1198. Six untracked scratch/superseded files
  deleted (filesystem `rm`, not `git rm`, per NEW-Q19); the comprehensive review
  committed at the new `docs/reviews/` convention. `README.zh-CN.md` gains a 1-line
  "English canonical, may lag" note (Q8 + R1 AC23.5). CLAUDE.md state-line + test-count
  + Latest cycle summary updated; new Release-artifacts pointer added. `BACKLOG.md` adds
  5 cycle-34 follow-up entries (cycle-35 `pip check` resolver-conflict unblock, cycle-35
  architecture-diagram v0.11.0 + PNG re-render, cycle-N+1 if requested real PDF extraction,
  cycle-N+1 if requested `KB_DISABLE_VECTORS` runtime flag, cycle-36 `requirements.txt`
  per-extra split). The 4 narrow-role CVE BACKLOG entries STAY (no upstream patch
  installable; SECURITY.md documents acceptance). Step-9 DESIGN-AMENDs: AC49 production
  fix DROPPED after primary-session probe confirmed `kb.cli` already does NOT pull in
  `kb.lint.fetcher`/`httpx`/`trafilatura` at module-load (R2 NT1 premise was stale);
  AC56 boot-lean test retained as forward-protection regression per cycle-15 L2.
  AC4e architecture-diagram bump deferred per design-gate fallback (NEW-Q15 option B).
- Detail: [history archive](CHANGELOG-history.md#2026-04-25--cycle-34--release-hygiene)

#### 2026-04-25 — cycle 33

- Items: 11 AC / 2 src (`mcp/core.py`, `ingest/pipeline.py`) + 2 new test files / 8 commits (6 feat+docs+fix on branch + 1 merge + 1 self-review)
- Tests: 2901 → 2923 (+21 passed including R1 mkdir-failure + R2 lazy-import-failure regressions; +1 xfailed for the Q8 ordinary-UNC residual)
- Scope:
  Closes BACKLOG `mcp/core.py:762,881` MEDIUM (cycle-32 threat T11) —
  AC1/AC2/AC3 wrap raw `OSError write_err` interpolation in pre-computed
  `sanitized_err = _sanitize_error_str(write_err, file_path)` at the
  paired `logger.warning` + `Error[partial]:` return for both
  `kb_ingest_content` (`core.py:748-768`) and `kb_save_source`
  (`core.py:868-893`); single binding ensures log + return cannot drift
  apart. AC4 same-class peer at `kb_query.save_as` (`core.py:279-285`)
  upgrades BOTH the previously-asymmetric `logger.warning(... %s, exc)`
  AND the return string to use `_sanitize_error_str(exc, target)` for
  symmetric path-attribute redaction depth (matches AC1/AC2). AC5
  regression suite at `tests/test_cycle33_mcp_core_path_leak.py` —
  15 tests covering Windows-drive-letter + POSIX shapes for all 3 sites,
  5-case parametrised `sanitize_error_text` OSError-shape unit suite
  (3-arg / no-filename / filename=None / filename2 / args[1] path),
  plus 3 UNC/long-path tests. AC6 adds "## Idempotency" docstring
  paragraphs to `_update_sources_mapping` + `_update_index_batch`
  documenting (a) safe-on-crash-then-reingest contract, (b) merge-on-
  new-pages contract, (c) explicit "Concurrent calls may race"
  serial-only disclaimer. AC7+AC8 pin both contracts behaviorally via
  `tests/test_cycle33_ingest_index_idempotency.py` — 5 tests with
  `MagicMock(side_effect=atomic_text_write)` spy + call_count assertions
  (1 for dedup branches, 2 for merge branch, 0 for missing-file
  early-out at `pipeline.py:773-775`). AC9 deletes the closed
  `mcp/core.py:762,881` BACKLOG entry. AC10 narrows the
  `ingest/pipeline.py` BACKLOG entry from "duplicate-on-reingest"
  (closed) to "RMW-concurrency residual" (still open — the serial
  dedup is now contract+test pinned but concurrent-ingest race remains
  unfixed). AC11 files three new MINOR BACKLOG entries (R1-08 empty
  wiki_pages, R1-10 backtick source_ref, R1-11 weaker filename
  validation) and one new MEDIUM (Q8 — `sanitize.py` UNC slash-
  normalize gap, the spawn cost of closing AC1+AC2). One Q8 test marked
  `pytest.mark.xfail(strict=True)` per cycle-16 L3 REPL probe — when
  the helper is fixed, removing the marker forces the strict-pass flip.
  Step-2 CVE baseline showed 4 existing advisories (diskcache, ragas,
  pip, litellm) all deferred per existing BACKLOG mitigation; Step-11
  PR-CVE diff returns empty (zero new dependencies introduced — no
  imports added beyond the already-imported `_sanitize_error_str`
  helper). R1 Opus design-eval (4.9/5 avg, PROCEED) + R1 Codex (5
  MAJOR + 6 MINOR, APPROVE-WITH-FIXES) → Step 5 decision gate folded
  in 12 question outcomes via 7 AC amendments before Step 9.
  Revert-fail discipline (cycle-24 L4) verified — `git stash` on
  `src/kb/mcp/core.py` produces 6 of 7 integration-test failures.
- Detail: [history archive](CHANGELOG-history.md#2026-04-25-cycle-33)

#### 2026-04-25 — cycle 32

- Items: 8 AC / 2 src (`cli.py`, `utils/io.py`) + 1 new test file / 10 commits (9 feat+docs+fix + 1 self-review)
- Tests: 2882 → 2901 (+19; Step 14 R1 Codex MAJOR 2 added stagger-integration pin)
- Scope:
  Closes CLI ↔ MCP parity category (b) — AC1/AC2 add `compile-scan`
  thin-wrapper over `kb_compile_scan` and AC4/AC5 add
  `ingest-content` over `kb_ingest_content` (both via the cycle
  27+ function-local-import pattern; `--incremental/--no-incremental`
  boolean flag pair matches cycle 15 `kb publish` precedent; Click
  `click.Path(exists=True, file_okay=False)` for `--wiki-dir`;
  Click `click.File("r", lazy=False, encoding="utf-8")` for
  `--content-file` + `--extraction-json-file` with native `-` stdin
  support per Context7-verified Click 8.3 semantics). AC3 widens
  `_is_mcp_error_response` tuple to include `"Error["` prefix,
  closing a silent-exit-0 bug where `kb_ingest_content`'s
  post-create OSError path (`Error[partial]: write to ... failed`
  at `mcp/core.py:762`) would have routed to stdout + exit 0 under
  the cycle-31 three-tuple; docstring updated with the full
  emitter map. AC6/AC7 add `utils/io.py` fair-queue stagger
  mitigation — module-level `_LOCK_WAITERS` counter guarded by
  `threading.Lock`, incremented via `_take_waiter_slot()` (0-based
  position snapshot) on entry to `file_lock` retry loop and
  decremented via `_release_waiter_slot()` in the outermost
  `finally` (C3 symmetry across success / TimeoutError /
  KeyboardInterrupt); first-sleep stagger is
  `position * _FAIR_QUEUE_STAGGER_MS / 1000` clamped to
  `LOCK_POLL_INTERVAL=50ms` (C11 prevents double-compounding with
  exponential backoff); position=0 → zero stagger so uncontended
  N=1 acquire sees no latency change; `_release_waiter_slot`
  emits `logger.warning` on underflow (C14, post-R1 Opus AMEND)
  instead of silently clamping to zero so counter drift surfaces
  to operators. AC8 doc sync updates CLI count 22 → 24 and
  deletes the BACKLOG fair-queue entry (lines 125-126) since AC6
  resolves it as a mitigation. Step-2 CVE baseline showed 2 open
  no-upstream-fix advisories (diskcache, ragas); Step-11 PR-CVE
  diff surfaced 3 mid-cycle arrivals per cycle-22 L4: litellm
  GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc (patched at 1.83.7
  but blocked by click<8.2 transitive — narrow-role exception
  documented in BACKLOG since zero runtime imports in `src/kb/`),
  python-dotenv CVE-2026-28684 (fixed via 1.1.1 → 1.2.2 already
  pinned in requirements.txt), pip CVE-2026-3219 (no upstream fix
  yet — tooling-only narrow-role). R1 Opus AMEND verdict (AC5
  add --use-api test, AC6 observable-warning on underflow, AC8
  explicit T11 BACKLOG filing); R2 Codex design-eval stopped
  past 12 min hang (cycle-20 L4) — primary-session manual
  verify caught `core.py:535` misread of `MAX_INGEST_CONTENT_CHARS*4`
  as a JSON-overhead ratio (actually UTF-8 bytes-per-char
  upper bound). Step 5 Opus decision gate hung past 10 min;
  primary-session synthesis per cycle-20 L4 fallback. Step 8
  Codex plan-gate hung past 8 min; primary-session self-review
  per cycle-21 L1 inline-resolve (all conditions grep-verifiable,
  no code-exploration gaps).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-32-2026-04-25)

#### 2026-04-25 — cycle 31

- Items: 8 AC / 1 src (`cli.py`) + 1 new test file / 9 commits (post-merge backfill per cycle-30 L1)
- Tests: 2850 → 2882 (+32)
- Scope:
  Continues cycle-27/30 CLI ↔ MCP parity — AC1-AC3 add
  `read-page` / `affected-pages` / `lint-deep` thin-wrappers
  over the three page_id-input MCP tools (`kb_read_page`,
  `kb_affected_pages`, `kb_lint_deep`). These tools emit
  heterogeneous error-prefix shapes (`"Error:"` colon-form,
  `"Error <verb>..."` space-form runtime-exception shapes, and
  the unique `"Page not found:"` logical-miss from `kb_read_page`),
  so AC4 introduces a shared `_is_mcp_error_response(output)`
  discriminator near `_error_exit` that classifies by first-line
  prefix only against the three shapes (Q1; first-line split
  prevents misfire on page bodies containing `Error:` on line 2;
  empty / blank-first-line outputs stay exit-0 to preserve MCP
  parity for zero-length page bodies). AC5 pins body-spy tests
  per subcommand (patching the OWNER module `kb.mcp.browse` /
  `kb.mcp.quality` — NOT `kb.cli` — because function-local
  imports resolve at call time per cycle-30 L2). AC6 adds
  traversal-boundary tests (`".."` → validator colon-form error)
  PLUS non-colon boundary tests per subcommand (`Page not found:`
  for read-page; forced `build_backlinks` / `build_fidelity_context`
  exceptions for affected-pages / lint-deep) — revert-divergent
  by construction: the tests flip `exit_code` from 1 to 0 if the
  discriminator reverts to `startswith("Error:")`. Q3 parity
  tests exercise both channels (direct MCP call + CLI invocation)
  with strict stream semantics (`stdout == mcp_output + "\n"` on
  success, `stderr == mcp_output + "\n"` + exit 1 on error;
  `CliRunner()` alone suffices on Click 8.3+ since `mix_stderr`
  was removed in 8.2). AC8 closes a pre-existing silent-failure
  bug latent since cycles 27 (`stats`) and 30 (`reliability-map`,
  `lint-consistency`): all three legacy wrappers wrap MCP tools
  that also emit non-colon runtime-error shapes, so AC8
  retrofits them to `_is_mcp_error_response` (one-line swap each
  plus 3 regression tests). T6 boot-lean pinned by subprocess
  probe asserting `import kb.cli` doesn't transitively pull
  `kb.mcp.browse` / `kb.mcp.quality`. AC7 BACKLOG hygiene —
  remove cluster (b) from the CLI↔MCP parity bullet; narrow
  "~12 remaining" to "~9 remaining" (7 write-path + 2 ingest/
  compile variants). Step-2 CVE baseline + Step-11 branch diff
  show identical 2 open no-upstream-fix CVEs (diskcache + ragas)
  — Step 11.5 no-op. R1 Opus APPROVE-WITH-AMENDS; R2 Codex AMEND
  (discovered the pre-existing silent-failure bug — scope
  expanded to AC8 via Step-5 Q4 Option A); Step 5 APPROVE; Step 8
  plan-gate REJECT resolved inline per cycle-21 L1.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-31-2026-04-25)

#### 2026-04-25 — cycle 30

- Items: 7 AC / 2 src + 2 new test files / 12 commits
- Tests: 2826 → 2850 (+24)
- Scope:
  Pre-Phase-5 backlog hygiene — AC1 `_audit_token` caps
  `block["error"]` at 500 chars via `kb.utils.text.truncate`
  (truthiness-guarded: `None`/empty skips the cap and keeps the
  bare `"cleared"`/`"unknown"` token; R2-A2 amendment) so a
  pathological `OSError.__str__()` on Windows can't bloat
  `wiki/log.md` or `kb rebuild-indexes` CLI stdout. AC2-AC6
  extend cycle-27's CLI ↔ MCP parity with 5 read-only
  subcommands — `graph-viz` (`--max-nodes` help text documents
  "1-500; 0 rejected" per R1 Opus amendment), `verdict-trends`,
  `detect-drift`, `reliability-map` (zero args; "No feedback
  recorded yet" exits 0), `lint-consistency` (`--page-ids`
  forwarded raw; no `--wiki-dir` since the MCP tool signature
  omits it). All 5 wrappers use the cycle-27 thin-wrapper
  pattern (function-local import + forward args raw +
  `"Error:"`-prefix contract + `_error_exit(exc)` wrap). AC7
  BACKLOG hygiene — delete cycle-29 audit-cap MEDIUM entry +
  narrow CLI↔MCP parity from "~14 remaining" to "~12 remaining"
  (R2-A3 arithmetic correction + `kb_save_synthesis` non-tool
  call-out); skip no-op CVE re-verify (diskcache + ragas
  identical cycle-29 baseline, same-day). R2 Codex stalled
  ~14min; primary-session R2 fallback per cycle-20 L4 then
  R2 findings folded in via DESIGN-AMEND.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-30-2026-04-25)

#### 2026-04-24 — cycle 29

- Items: 5 AC / 3 src + 2 new test files / 6 commits
- Tests: 2809 → 2826 (+17)
- Scope:
  Backlog-by-file hygiene cycle. AC1 `_audit_token(block)` helper in
  `compile/compiler.py` replaces the inline audit ternary so a partial
  vector clear (main `unlink()` succeeded + sibling `.tmp` unlink failed)
  renders `vector=cleared (warn: tmp: <msg>)` instead of swallowing the
  error tail; mirrored to `kb rebuild-indexes` CLI stdout via function-
  local import in `cli.py` (cycle-23 AC4 boot-lean preserved); Q3
  embedded-newline regression pins the `append_wiki_log` sanitizer
  contract. AC2 `_validate_path_under_project_root(path, field_name)`
  helper applies the dual-anchor `PROJECT_ROOT` containment (literal-abs
  + `.resolve()` target both under root) to `hash_manifest` + `vector_db`
  overrides of `rebuild_indexes`; void-return helper (cycle-23 L2) with
  explicit empty-path reject (cycle-19 L3); wiki_dir block refactored to
  use the same helper so all 3 sites share one contract. AC3 architectural
  carve-out comment above `CAPTURES_DIR = RAW_DIR / "captures"` (5 lines,
  mirrors CLAUDE.md §raw/ language) + deletes stale `config.py:40-53`
  BACKLOG bullet (Q13 expansion — BACKLOG lifecycle). AC4 deletes stale
  `_PROMPT_TEMPLATE inline string` BACKLOG bullet (shipped cycle-19 AC15
  via lazy `_get_prompt_template()`). AC5 deletes stale Phase 4.5 HIGH #6
  cold-load bullet ("0.81s + 67 MB RSS delta") — shipped cycle-26 AC1-AC5
  warm-load + cycle-26/28 observability; HIGH-Deferred summary with the
  true residual (dim-mismatch AUTO-rebuild) survives. Step-11 T1 PARTIAL
  (unbounded `OSError.__str__()` → `wiki/log.md` + CLI stdout) filed as
  new MEDIUM BACKLOG entry per cycle-12 L3. Dep-CVE baseline 2026-04-24:
  diskcache + ragas both `fix_versions: []`, unchanged; PR-introduced
  diff empty.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-29-2026-04-24)

#### 2026-04-24 — cycle 28

- Items: 9 AC / 2 src + 1 new test file / 7 commits
- Tests: 2801 → 2809 (+8)
- Scope:
  First-query observability completion — `VectorIndex._ensure_conn`
  sqlite-vec extension load and `BM25Index.__init__` corpus indexing
  (closes HIGH-Deferred sub-item (b), cycle-26 Q16 follow-up). AC1/AC2/AC3:
  `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS=0.3` module constant +
  `_sqlite_vec_loads_seen` counter (exact, inside `_conn_lock`) +
  `get_sqlite_vec_load_count()` getter; INFO log always on successful
  extension load + WARNING above 0.3s; post-success ordering (NO
  `finally:` wraps the log/counter — defended by
  `test_sqlite_vec_load_no_info_on_failure_path`). AC4/AC5: lock-free
  `_bm25_builds_seen` counter (aggregates `engine.py:110` wiki +
  `engine.py:794` raw call sites — "constructor executions, NOT distinct
  cache insertions" per Q11) + `get_bm25_build_count()` getter; INFO
  log on every `BM25Index.__init__` including empty-corpus (no WARN
  threshold — corpus-size variance defeats a fixed threshold). AC6:
  8 regression tests. AC7: BACKLOG hygiene — narrow HIGH-Deferred entry
  (sub-item b landed), delete MEDIUM AC17-drop rationale line (duplicate
  of CHANGELOG-history cycle-13 AC2), delete resolved LOW cycle-27
  commit-tally entry. AC8: CHANGELOG format-guide commit-count rule
  codified (self-referential +1 per cycle-26 L1 skill patch). AC9:
  no-op CVE re-verify, matches cycle-26 baseline (diskcache + ragas
  still no upstream fix).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-28-2026-04-24)

#### 2026-04-24 — cycle 27

- Items: 7 AC / 2 src + 1 new test file / 3 commits
- Tests: 2790 → 2801 (+11)
- Scope:
  CLI ↔ MCP parity — 4 new read-only CLI subcommands (`kb search`,
  `kb stats`, `kb list-pages`, `kb list-sources`) wrapping existing MCP
  browse tools with function-local imports (AC1/AC2/AC3/AC4 — preserves
  cycle-23 AC4 boot-lean contract). AC1b extracts `_format_search_results`
  helper from `kb_search` body so CLI reuses identical formatter without
  duplication. AC5: 7 regression tests (4 `--help` smoke + empty-query
  non-zero-exit + 2 helper semantics). AC6 narrows BACKLOG CLI↔MCP parity
  entry (18 → 14 remaining tools). AC7 skip-on-no-diff CVE re-verify
  (pip-audit matches cycle-26 baseline, same-day noise avoidance).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-27-2026-04-24)

#### 2026-04-24 — cycle 26

- Items: 8 AC (+AC2b) / 2 src + 1 new test file + 1 extended cycle-23 test / 7 commits
- Tests: 2782 → 2790 (+8)
- Scope:
  Vector-model cold-load observability — new `maybe_warm_load_vector_model(wiki_dir)`
  daemon-thread warm-load hook wired into `kb.mcp.__init__.main()` after tool
  registration, before stdio loop (AC1/AC2); boot-lean allowlist extension pins
  function-local import contract (AC2b); `_get_model()` instrumented with
  `time.perf_counter` — INFO log always on cold-load + WARNING above
  `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS=0.3s` (AC3); module-level
  `_vector_model_cold_loads_seen` counter + `get_vector_model_cold_load_count()`
  getter, exact counts inside `_model_lock` (AC4 — intentional asymmetry
  vs cycle-25 lock-free `_dim_mismatches_seen`, documented in getter docstring);
  seven regression tests including subprocess sys.modules probe + exception-
  swallow pin (AC5); BACKLOG hygiene — delete stale multiprocessing file_lock
  entry (AC6 — resolved by cycle-23 AC7), skip no-op CVE re-stamp (AC7 —
  pip-audit matches cycle-25 baseline), narrow HIGH-Deferred vector-index
  lifecycle entry + add Q16 follow-up (AC8).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-26-2026-04-24)

#### 2026-04-24 — cycle 25

- Items: 10 AC / 2 src + 3 new test files / 6 commits
- Tests: 2768 → 2782 (+14)
- Scope:
  `rebuild_indexes` also unlinks `<vec_db>.tmp` sibling (AC1/AC2 —
  cycle-24 R2 Codex follow-up); vector-index dim-mismatch warning now
  includes operator remediation command + module-level observability
  counter (AC3/AC4/AC5 — HIGH-Deferred sub-item 3 narrow-scope shipped,
  auto-rebuild remains deferred); `compile_wiki` emits `in_progress:{hash}`
  pre-markers before each `ingest_source`, stale-marker entry scan on
  next invocation warns per-source, full-mode prune exempts in_progress
  values (AC6/AC7/AC8 + CONDITION 13 — MEDIUM M2 narrow observability
  variant); BACKLOG + diskcache/ragas CVE 2026-04-24 re-verify (AC9/AC10).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-25-2026-04-24)

#### 2026-04-23 — cycle 24

- Items: 15 AC / 4 src + 5 new test files / 9 commits
- Tests: 2743 → 2768 (+25)
- Scope:
  Evidence-trail inline render at first write + StorageError on update-path
  evidence failure (AC1/AC2); `append_evidence_trail` sentinel search
  section-span-limited against attacker-planted body sentinels (AC14/AC15);
  vector-index atomic rebuild via `<vec_db>.tmp` + `os.replace` with
  cache-pop+close before replace and crash-cleanup (AC5/AC6/AC7/AC8);
  `file_lock` exponential backoff across all 3 polling sites with
  `LOCK_POLL_INTERVAL` as CAP (AC9/AC10); BACKLOG cleanup +
  diskcache/ragas CVE re-verification (AC11/AC12/AC13).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-24-2026-04-23)

#### 2026-04-23 — cycle 23

- Items: 8 AC / 6 src + 4 new tests / 6 commits
- Tests: 2725 → 2743 (+18)
- Scope:
  MCP boot-leanness via PEP-562 lazy shim (cycle-19 AC15 contract preserved),
  `rebuild_indexes` helper + `kb rebuild-indexes` CLI for clean-slate recompiles,
  hermetic ingest→query→lint E2E coverage, and cross-process `file_lock`
  regression (Phase 4.5 HIGH-Deferred).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-23-2026-04-23)

#### 2026-04-22 — cycle 22

- Items: 14 AC / 3 src + 2 new tests / 11 commits
- Tests: 2720 → 2725 (+5; 1 Windows-skip)
- Scope:
  Pre-Phase-5 backlog hardening: wiki-path ingest guard, universal extraction grounding clause,
  behavioural prompt test rewrite, stale BACKLOG cleanup, and lxml CVE pin bump.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-22-2026-04-22)

#### 2026-04-21 — cycle 21

- Items: 30 AC / 4 src / 1 commit
- Tests: 2697 → 2710 (+13)
- Scope:
  CLI subprocess backend for 8 local AI tools, with env-var routing, JSON extraction, per-backend
  concurrency limits, secret redaction, and Anthropic path compatibility.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-21-2026-04-21)

#### 2026-04-21 — cycle 20

- Items: 21 AC / 10 src / 13 commits
- Tests: 2639 → 2697 (+58)
- Scope:
  Error taxonomy, slug-collision O_EXCL hardening, locked page updates, stale-refine sweep/list
  tools, CLI/MCP refine surfaces, and Windows tilde-path regression coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-20-2026-04-21)

#### 2026-04-21 — cycle 19

- Items: 23 AC / 6 src / 9 commits
- Tests: 2592 → 2639 (+47)
- Scope:
  Batch wikilink injection, manifest-key consistency, refine two-phase writes, stale-pending
  visibility, MCP monkeypatch migration, and reload-leak fixes.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-19-2026-04-21)

#### 2026-04-21 — cycle 18

- Items: 16 AC / 5 src / 6 commits
- Tests: 2548 → 2592 (+44)
- Scope:
  Structured ingest audit log, locked wikilink injection, log rotation under lock, UNC sanitization,
  index-file helper, HASH_MANIFEST test redirection, and e2e workflow coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-18-2026-04-21)

#### 2026-04-20 — cycle 17

- Items: 16 AC / 11 src / 14 commits
- Tests: 2464 → 2548 (+84)
- Scope:
  manifest lock symmetry, capture two-pass, lint augment resume, shared run-id validator, MCP lazy
  imports (narrowed), thin-tool coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-17-2026-04-20)

#### 2026-04-20 — cycle 16

- Items: 24 AC / 8 src / 14 commits
- Tests: 2334 → 2464 (+130)
- Scope:
  enrichment targets, query rephrasings, duplicate-slug + inline-callout lint, kb_query `save_as`,
  per-page siblings + sitemap publish
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-16-2026-04-20)

#### 2026-04-20 — cycle 15

- Items: 26 AC / 6 src / 7 commits
- Tests: 2245 → 2334 (+89)
- Scope:
  authored-by boost, source volatility, per-source decay, incremental publish, lint decay/status
  wiring
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-15-2026-04-20)

#### 2026-04-20 — cycle 14

- Items: 21 AC / 9 src / 8 commits
- Tests: 2140 → 2235 (+95)
- Scope:
  Epistemic-Integrity 2.0 vocabularies, coverage-confidence refusal gate, `kb publish` module
  (/llms.txt, /llms-full.txt, /graph.jsonld), status ranking boost
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-14-2026-04-20)

#### 2026-04-20 — cycle 13

- Items: 8 AC / 5 src / 7 commits
- Tests: 2119 → 2131 (+12)
- Scope:
  frontmatter migration to cached loader, CLI boot `sweep_orphan_tmp`, `run_augment` raw_dir
  derivation
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-13-2026-04-20)

#### 2026-04-19 — cycle 12

- Items: 17 AC / 13 src / 11 commits
- Tests: 2089 → 2118 (+29)
- Scope:
  conftest fixture, io sweep, `KB_PROJECT_ROOT`, LRU frontmatter cache, `kb-mcp` console script
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-12-2026-04-19)

#### 2026-04-19 — cycle 11

- Items: 14 AC / 14 src / 13 commits
- Tests: 2041 → 2081 (+40)
- Scope:
  ingest coercion, comparison/synthesis reject, page-helper relocation, CLI import smoke,
  stale-result edges
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-11-2026-04-19)

#### 2026-04-18 — cycle 10

- Items: 14 AC / 10 src
- Tests: 2004 → 2041 (+37)
- Scope:
  MCP `_validate_wiki_dir` rollout, `kb_affected_pages` warnings, `VECTOR_MIN_SIMILARITY` floor,
  capture hardening
- Detail: [history archive](CHANGELOG-history.md#backlog-by-file-cycle-10-2026-04-18)

#### 2026-04-18 — cycle 9

- Items: 30 AC / 14 src
- Tests: 1949 → 2003 (+54)
- Scope:
  wiki_dir isolation across query/MCP, LLM redaction, env-example docs, lazy ingest export
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-9-2026-04-18)

#### 2026-04-18 — cycle 8

- Items: 30 AC / 19 src
- Tests: 1919 → 1949 (+30)
- Scope:
  model validators, LLM telemetry, PageRank → RRF list, contradictions idempotency, pip toolchain
  CVE patch
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-8-2026-04-18)

#### 2026-04-18 — cycle 7

- Items: 30 AC / 22 src
- Tests: 1868 → 1919 (+51)
- Scope:
  `_safe_call` helper, MCP error-path sanitization, Evidence Trail convention, many
  lint/query/ingest refinements
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-7-2026-04-18)

#### 2026-04-18 — cycle 6

- Items: 15 AC / 14 src
- Tests: 1836 → 1868 (+32)
- Scope:
  PageRank cache, vector-index reuse, CLI `--verbose`, hybrid rrf tuple storage, graph
  `include_centrality` opt-in
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-6-2026-04-18)

#### 2026-04-18 — cycle 5 redo

- Items: 6 AC / 6 src
- Tests: 1821 → 1836 (+15)
- Scope:
  pipeline retrofit for Steps 2/5 artifacts; citation format symmetry, page-id SSOT,
  purpose-sentinel coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-5-redo-hardening-2026-04-18)

#### 2026-04-18 — cycle 5

- Items: 14 AC / 13 src
- Tests: 1811 → 1820 (+9)
- Scope:
  `wrap_purpose` sentinel, pytest markers, verdicts/config consolidation, `_validate_page_id`
  control-char reject
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-5-2026-04-18)

#### 2026-04-18 — PR #17 concurrency

- Items: 3 files
- Tests: 1810 → 1811 (+1)
- Scope:
  `_VERDICTS_WRITE_LOCK` fix + capture docstring clarity; CHANGELOG split into active vs history
- Detail: [history archive](CHANGELOG-history.md#concurrency-fix--docs-tidy-pr-17-2026-04-18)

#### 2026-04-17 — cycle 4

- Items: 22 AC / 16 src
- Tests: 1754 → 1810 (+56)
- Scope:
  `_rel()` path-leak sweep, `<prior_turn>` sentinel sanitizer, kb_read_page cap, rewriter CJK gate,
  BM25 postings index
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-4-2026-04-17)

#### 2026-04-17 — cycle 3

- Items: 24 AC / 16 src
- Tests: 1727 → 1754 (+27)
- Scope:
  `LLMError.kind` taxonomy, vector dim guard + lock, stale markers in context, hybrid catch-degrade,
  inverted-postings consistency
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-3-2026-04-17)

#### 2026-04-17 — cycle 2

- Items: 30 AC / 19 src
- Tests: 1697 → 1727 (+30)
- Scope:
  hashing CRLF normalization, file_lock hardening, rrf metadata merge, extraction schema deepcopy
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-2-2026-04-17)

#### 2026-04-17 — cycle 1

- Items: 38 AC / 18 src
- Tests: → 1697
- Scope:
  pipeline wiki/raw dir plumbing, augment rate/manifest scoping, capture secret patterns, 3-round PR
  review pattern established
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-1-2026-04-17)

#### 2026-04-17 — HIGH cycle 2

- Items: 22 / 16 src
- Tests: → 1645
- Scope:
  frontmatter regex cap, orphan-graph copy, semantic inverted index, trends UTC-aware timestamps
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-2-2026-04-17)

#### 2026-04-16 — HIGH cycle 1

- Items: 22 / multi
- Tests: → baseline
- Scope:
  RMW locks across refiner/evidence/wiki_log, hybrid vector-index lifecycle, error-tag categories
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-1-2026-04-16)

#### 2026-04-16 — CRITICAL docs-sync

- Items: 2
- Tests: 1546 → 1552
- Scope:
  version-string alignment + `scripts/verify_docs.py` drift check
- Detail: [history archive](CHANGELOG-history.md#phase-45--critical-cycle-1-docs-sync-2026-04-16)

> Older released-version history is also archived in [CHANGELOG-history.md](CHANGELOG-history.md).

---
