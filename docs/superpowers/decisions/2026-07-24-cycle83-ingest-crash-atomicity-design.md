# Cycle 83 — ingest crash-atomicity: design, threat model, decision gate

Date: 2026-07-24
Backlog item: Phase 4.5 HIGH (R2) `ingest/pipeline.py` state-store fan-out
Paired item: Phase 4.5 MEDIUM `compile/compiler.py` `compile_wiki` per-source rollback

> Note: the separate threat-model file produced during this cycle was lost when the
> working tree was reset mid-cycle (see §Process incident). Its substance is folded
> into §Threat model below, reconstructed from the analysis output.

## Problem (verified against source, not backlog prose)

BACKLOG.md described the crash window as "between manifest-write and log-append".
That understates it. Verified order inside `ingest_source`:

1. `_emit_ingest_jsonl("start", ...)`
2. `_check_and_reserve_manifest(source_hash, manifest_ref)` writes
   `manifest[manifest_ref] = source_hash` under `file_lock`. **Pre-commit write —
   it happens before any wiki page exists.**
3. `_run_ingest_body`: summary page, entity/concept pages, index files, Phase-2
   manifest confirmation, `append_wiki_log`, affected pages,
   `inject_wikilinks_batch`, `_persist_contradictions`, `rebuild_vector_index`
4. `_emit_ingest_jsonl("success", ...)`

A crash anywhere in 2..3 left `.data/hashes.json` asserting the source was ingested
while the wiki held zero or partial pages. `find_changed_sources` diffs stored-vs-
current hash, so that source was then skipped **permanently** on every later compile.
`kb compile --full` was the only escape and nothing told the user to run it.

`_check_and_reserve_manifest` additionally swallowed every exception at DEBUG, so a
failed reservation was invisible.

## Entry points

All six `ingest_source` call sites funnel through `_check_and_reserve_manifest`:
`cli.py`, `mcp/ingest.py` (×3), `compiler.py`, `lint/augment/orchestrator.py`
(`auto_ingest` — ingests remote web content). Only the `compiler.py` site was
preceded by a cycle-25 `in_progress:` marker write, so **5 of 6 entry points had no
protection at all**.

## Approaches scored

| Criterion | (A) marker into `ingest_source` | (B) `.data/ingest_locks/` receipts | (B') JSONL oracle |
|---|---|---|---|
| Blast radius | 5 | 1 | 2 |
| Backcompat with on-disk `hashes.json` | 5 (no format change) | 1 | 1 |
| Interaction with non-reentrant `file_lock` | 5 (no new lock) | 2 (lock-order inversion risk vs cycle-81 `page_lock`) | 4 |
| Fixes all 6 entry points | 5 | 5 | 5 |
| Unbounded-growth risk | 5 | 1 (orphan per crash, no GC) | 3 |
| Non-vacuous test difficulty | 4 | 1 | 2 |
| **Actually closes the defect?** | **YES** | **NO** | **NO** |

(B) and (B') fail on the last row, which is decisive: a receipt file records that a
crash happened but leaves `manifest[K] = H` intact, so `find_changed_sources` still
skips the source forever. (B) is not an alternative to (A) — it is (A) plus a second
durable store, and the second store is the part that grows without bound.

`.data/ingest_log.jsonl` is not a viable oracle: it is rotated
(`rotate_if_oversized`), best-effort (`OSError` swallowed at the writer), and has
**zero readers** anywhere in `src/`.

Supporting fact: `content_hash(path)` and `hash_bytes(bytes)` are the same function
over the same file (`utils/hashing.py` — both normalize newlines then
`sha256().hexdigest()[:32]`). So `compile_wiki`'s `pre_hash` and `ingest_source`'s
`source_hash` are byte-identical: under (A) the two marker writes produce the same
string at the same key. No collision; the second write is a content no-op.

**Selected: (A).** The manifest value namespace is already a tagged union — several
sites special-case `in_progress:` and the change diff already branches on `failed:`.
(A) widens the producer set of a format that shipped in cycle 25.

## Decision gate

### D1. What counts as "claiming" content for duplicate detection — REVISED MID-CYCLE

The two gates disagreed. The architecture eval said do NOT prefix-strip before the
duplicate comparison; threat model T8 said DO strip. I initially decided **not** to
strip, reasoning that severity was asymmetric (a stale marker suppressing a different
file = silent data loss; a missed dedup = a merge).

**The full-suite gate overturned that.** `tests/test_ingest.py::test_duplicate_content_concurrent_ingest`
— a dedicated Phase 4.5 Q_A regression test asserting that exactly one of two threads
ingesting identical content reports `duplicate: True` — failed, because
`"in_progress:H" != "H"` defeated the comparison. The dedup guarantee is shipped,
tested, and load-bearing; the architecture eval reasoned about it abstractly and was
wrong about the cost.

**DECIDED: a three-way split**, encoded in the new `_claims_content` helper. Neither
gate proposed it; it falls out of taking both objections seriously.

| Manifest value | Meaning | Claims content? |
|---|---|---|
| `{hash}` | ingest COMPLETED, pages exist | yes (unchanged) |
| `in_progress:{hash}` | ingest ACTIVE (or hard-killed mid-run) | **yes** |
| `failed:{hash}` | ingest raised and was handled, **no pages written** | **no** |

Both halves are load-bearing and each has a regression test:

- `in_progress:` must claim, or two threads ingesting distinct files with identical
  content both pass the duplicate check and both write pages — reopening the Q_A RMW
  race.
- `failed:` must not claim, or a prior failed attempt that produced no pages
  suppresses a genuinely different source and leaves that content in no page at all —
  the same data-loss class this cycle closes.

**Accepted residual:** a hard-killed ingest leaves `in_progress:` behind, and a stale
marker does claim, so a different file with identical content is skipped until the
crashed source is retried. This self-heals — a marker never equals the current hash,
so `find_changed_sources` re-selects the crashed source on the next compile and its
pages get written. Distinguishing live from stale needs process-liveness data that
threat T13 forbids encoding in the marker string. Filed to BACKLOG as T8.

CONFIDENCE: high — both directions are now pinned by tests, and the previously
unexamined direction was caught by an existing test rather than by argument.

### D2. Marker value format
`f"in_progress:{source_hash}"` — identical to the `compile_wiki` producer. No second
prefix, no dict payload (T13: `stored.startswith` must keep working in every version
that reads the manifest). Plain string only.

### D3. Exception-path downgrade — load-bearing
`ingest_source`'s `except BaseException` downgrades the marker to
`f"failed:{source_hash}"` under `file_lock` before re-raising, mirroring
`compiler.py`. Wrapped in its own try/except so a rollback failure can never replace
the caller's exception.

Without it, every ordinary ingest error would leave an `in_progress:` marker and the
cycle-25 stale-marker warning would degrade into noise operators ignore. It is also
what makes D1's split meaningful: the two prefixes must actually correspond to
"handled" vs "hard kill" for `_claims_content` to be correct.

### D4. Observability
`_check_and_reserve_manifest`'s swallow-all goes `logger.debug` → `logger.warning`
(threat T2). NOT escalated to `raise` this cycle — that changes `compile_wiki`'s error
accounting and is a separate, harder-to-revert change (threat T18: making reservation
failure fatal by default turns degradation into outage).

### D5. Signature stability
`_check_and_reserve_manifest` keeps its `bool` return and parameter list — its
docstring states tests call it directly. "Reservation attempted" is tracked with a
local flag in `ingest_source`, sentinel-initialised before the `try` per C33-L2 so an
exception raised before the reservation point cannot turn a real ingest error into a
`NameError`.

### D6. Locking
The marker is written inside the **existing** `file_lock` acquisition. No new lock, no
new target, no new entry in the documented lock order
(`page < history < contradictions < log < manifest`). Threat T10 closed by construction.

### D7. Forward/backward compatibility
Absence of a marker means "assume complete" (threat T14) — upgrading must not force a
full LLM re-ingest of existing repos. Old manifests read identically by new code. New
manifests read by older code still work: a marker `!= hash`, so the source is
re-selected as changed, which is the desired behaviour.

## Threat model (condensed)

| # | STRIDE | Item | Status |
|---|---|---|---|
| T1 | Tampering / DoS | Pre-commit hash write indistinguishable from a completed ingest → permanent silent skip | **CLOSED** (D1/D2) |
| T2 | Repudiation | Reservation failures swallowed at DEBUG | **CLOSED** (D4) |
| T3 | DoS / EoP | Planted `hashes.json.lock` with a live PID disables dedup and atomicity | out of scope |
| T4 | DoS | `load_manifest` has no type check; `stored.startswith` raises on a crafted non-string value | **partially closed** — `_claims_content` returns False on non-strings; `compiler.py` read sites still unguarded → BACKLOG |
| T5 | Tampering | Planting a correct hash for a never-ingested source forces a permanent skip | residual, cannot close |
| T6 | DoS | Marker entries are prune-exempt, i.e. immortal; warning enumerates every key | → BACKLOG |
| T8 | Tampering | Marker defeats the duplicate check | **CLOSED** (D1 split) |
| T10 | DoS | A new lock path would deadlock against the non-reentrant manifest lock | **CLOSED** by construction (D6) |
| T11 | Tampering | Promote/rollback failing partway must leave a marker, never a bare hash | **CLOSED** (D3) |
| T12 | Tampering | `atomic_json_write` fsyncs the temp file but not the parent dir | → BACKLOG |
| T13 | Fwd-compat | Marker must stay a plain prefixed string, not a dict | **CLOSED** (D2) |
| T14 | DoS (cost) | Absence of a marker must mean "assume complete" | **CLOSED** (D7) |
| T16 | Info disclosure | New log lines must use `manifest_ref`, not absolute paths | **CLOSED** — downgrade warning logs `manifest_ref` only |
| T17 | Spoofing | Marker payload must never derive from LLM `extraction` output | **CLOSED** — payload is `hash_bytes(raw_bytes)` |
| T18 | DoS | Making reservation failure fatal turns degradation into outage | **CLOSED** (D4 declines to raise) |

Out of scope, with reason: parent-dir fsync (touches every atomic write; durability ≠
crash-atomicity); rolling back wiki page writes (irreversible, pages may hold human
edits); escalating manifest-write failure to CRITICAL (depends on D4 landing first;
stacking makes a revert ambiguous); auto-deleting stale markers (races a live compile,
cycle-25 Q10 decision stands); HMAC-signing the manifest (an attacker who writes
`.data/` writes `src/` too).

## Explicitly NOT in this cycle

- No `.data/ingest_locks/` receipt directory. Unbounded orphans, new lock target, and
  it does not fix the permanent skip.
- No JSONL reader or recovery pass.
- Not removing the Phase-1 reservation — would reopen the Q_A race.
- Not fixing the Phase-2 `manifest_path` divergence → BACKLOG.
- Not rolling back wiki-side page writes (Phase 4.5 MEDIUM (a)).
- Not escalating manifest-write failure to CRITICAL (Phase 4.5 MEDIUM (b)).
- No `KB_DISABLE_*` kill-switch — the project's kill-switch convention guards *added*
  behaviour that can fail; this is a correctness fix whose "off" state reinstates
  silent data loss.

## Scope addition found during implementation

`find_changed_sources` resolved the manifest default for `load_manifest` /
`save_manifest` but passed the raw `manifest_path` to `file_lock`, so `None` raised
`AttributeError: 'NoneType' object has no attribute 'with_suffix'` and killed the
scan. Reachable from the `kb_compile_scan` MCP tool on any call omitting `wiki_dir`.
`compile_wiki` was unaffected — it resolves the default earlier — which is why no
existing test caught it. Fixed in-cycle with its own regression test: it is a hard
crash, one line, and sits in the same manifest-RMW code path this cycle touches.

## Process incident (for the Step-24 retrospective)

Mid-cycle the working tree was reset: the new test file, both design docs, both src
edits, and the BACKLOG edits all vanished while a Codex subagent dispatched with write
access was operating in the same working tree. Nothing had been committed yet, so git
could not recover any of it; the work was reconstructed from conversation context.

Lessons: (1) commit after the green phase, not after the doc pass — an uncommitted
working tree is the only unrecoverable state in git; (2) do not dispatch a
write-capable agent into the same working tree as in-flight uncommitted edits (a
worktree per C42-L4, or dispatch read-only); (3) the surviving `__pycache__` `.pyc`
was the artifact that confirmed the files had really existed, which is worth checking
before concluding a tool lied about writing them.

## BACKLOG items filed

1. Phase-2 confirmation hardcodes `HASH_MANIFEST`, ignoring the caller's
   `manifest_path`. Harmless in production; silently divergent in tests, and it makes
   any `manifest_path=`-passing regression test vacuous.
2. T8 — liveness-aware duplicate detection so a stale `in_progress:` stops claiming.
3. T4 — `load_manifest` value type check at the `compiler.py` read sites.
4. T6 — `in_progress:` entries are immortal (prune-exempt); needs aging + a capped
   warning list.
5. T12 — `atomic_json_write` parent-directory fsync.
