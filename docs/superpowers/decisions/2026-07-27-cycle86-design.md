# Cycle 86 — validation & ordering correctness

Date: 2026-07-27 · Branch: `fix/cycle-86-validation-ordering`

## Problem

Five items traced to `BACKLOG.md`: two Phase-5 HIGH-LEVERAGE "Low effort" entries
from the nashsu/llm_wiki + TencentDB review (2026-07-25), two Phase-4.5 MEDIUM
defects from the cycle-83 audit, and one stale backlog entry that cycle 84
already closed.

## Non-goals

- No new LLM call sites, no new dependencies, no schema-vocabulary expansion.
- No graph-traversal work (the third 2026-07-25 HIGH-LEVERAGE item, `query/hybrid.py`
  bounded hop expansion, is Medium effort and stays open for a later cycle).
- No rollback of wiki-side writes (the still-open half of the Phase-4.5 HIGH
  state-store fan-out entry) — that needs its own design.

## Acceptance criteria

| AC | Deliverable | Backlog source |
|---|---|---|
| AC01 | `lint/checks/evidence_resolvable.py` + runner registration: every `source:` frontmatter entry must resolve to a file under `raw/`; dangling entries become findings naming page + ref | Phase 5 HIGH LEVERAGE (Low) |
| AC02 | `_validate_tier_boundary(allowed_values=...)` value-domain check + `ValueDomainError` + proposer wiring with `action_not_in_vocabulary:` reason | Phase 5 HIGH LEVERAGE (Low) |
| AC03 | `ingest/pipeline.py`: human `wiki/log.md` success line moves after the manifest commit; post-commit interruption no longer emits `stage=failure` | Phase 4.5 MEDIUM |
| AC04 | `utils/io.py`: fsync the parent directory after `os.replace` so the rename itself is durable | Phase 4.5 MEDIUM |
| AC05 | Delete the stale `load_manifest` value-check backlog entry (shipped cycle 84) | backlog hygiene |

## Grep verification (C15-L1 — every symbol confirmed before scoring)

| Symbol | Location | Verdict |
|---|---|---|
| `check_dead_links` | `lint/checks/dead_links.py:10` | EXISTS — shape to mirror |
| `check_source_coverage` | `lint/checks/consistency.py:18` | EXISTS — reverse direction; reuse its `normalize_sources` parse |
| `normalize_sources` | `utils/pages.py:94` | EXISTS — handles str/list/None + non-string items |
| `_validate_tier_boundary` | `lint/augment/tier_boundary.py:47` | EXISTS — key-domain params only, no value domain |
| `_PROPOSER_SCHEMA["properties"]["action"]["enum"]` | `lint/augment/proposer.py:46` | EXISTS — `["propose", "abstain"]` |
| hand-rolled re-check | `lint/augment/proposer.py:122-123` | EXISTS — `if action != "propose"` |
| `append_wiki_log("ingest", ...)` | `ingest/pipeline.py:1843` | EXISTS — inside `_run_ingest_body` step 7 |
| `_commit_ingest_manifest` | called at `ingest/pipeline.py:1603` | EXISTS — after body returns |
| `atomic_json_write` | `utils/io.py:174` | EXISTS — fsyncs file (`:195`), not parent dir |
| `load_manifest` value guard | `compile/compiler.py:185` | **ALREADY SHIPPED (cycle 84)** → AC05 is a deletion, not a fix |

### AC05 evidence — all five `compiler.py` manifest read sites are guarded

| Line | Expression | Guard |
|---|---|---|
| 185 | `not isinstance(stored, str)` | the guard itself (cycle 84) |
| 205 | `stored.startswith("failed:")` | unreachable for non-str — `elif` after line 185 |
| 218 | `str(v).startswith("in_progress:")` | `str()` coercion |
| 230 | `stored_hash != current_hash` | plain `!=`, type-agnostic |
| 460, 588 | `str(v).startswith("in_progress:")` | `str()` coercion |

Backlog text claims "the `compiler.py` read sites remain unguarded" — false as of
cycle 84. Delete per the BACKLOG lifecycle.

## Threat model

| # | STRIDE | Threat | Mitigation | Verified at |
|---|---|---|---|---|
| T1 | InformationDisclosure | AC01 stats paths taken from LLM-written frontmatter; `Path.exists()` on `../../../etc/shadow` is a filesystem oracle | Resolve + containment-check under `raw_dir` BEFORE any stat. Out-of-tree refs become a finding and are **never probed** | AC01 test: traversal ref yields finding, `Path.exists` spy never called |
| T2 | DoS | A page with 10^5 `source:` entries makes lint quadratic | `_EVIDENCE_REFS_PER_PAGE_CAP = 200`, mirroring `_CALLOUTS_PER_PAGE_CAP` | AC01 test: capped page emits exactly one `evidence_refs_truncated` notice |
| T3 | EscalationOfPrivilege | LLM returns `{"action": "exfiltrate"}`; boundary passes it; orchestrate tier acts on it | `allowed_values` rejects at the boundary; caller fails closed to `abstain` | AC02 xfail-strict negative test |
| T4 | Spoofing | Vocabulary derived from `scan_output` self-validates (cycle-73 T5 carry-over) | Enum derived from the LOCAL `_PROPOSER_SCHEMA` only | AC02 test asserts the frozenset against the schema literal |
| T5 | Repudiation | `wiki/log.md` shows `Ingested ...` for an ingest the manifest never recorded; or `stage=failure` for an already-committed ingest | Human log moves after `_commit_ingest_manifest`; `committed` flag suppresses the failure row | AC03 tests, both directions |
| T6 | Tampering | Power loss right after `os.replace` reverts the rename on some filesystems | fsync the parent directory on POSIX | AC04 test spies the dir-fsync call |
| T7 | DoS (self-inflicted) | Directory fsync raises `EINVAL` on some network mounts, so every write starts failing | Best-effort: log WARNING, swallow `OSError`. The file-content fsync (which *does* raise) remains the load-bearing guarantee | AC04 test: raising dir-fsync does not fail the write |

Dep-CVE baseline (Step 2): `.data/cycle-86/cve-baseline.json` — 10 vulnerable deps,
all Class A (pre-existing on `main`). This cycle touches no dependency manifest,
so the Step-14 PR-introduced diff must be empty.

## Decisions

**Q1 — Where does AC01's path resolution anchor?**
DECIDED: entries are project-root-relative (`raw/articles/x.md`, per the frontmatter
template). Strip a leading `raw/` and resolve the remainder under `raw_dir`; entries
without the prefix resolve under `raw_dir` directly. This keeps the check working
under the `tmp_kb_env` sandbox where `raw_dir` is a tmp path.
RATIONALE: `make_source_ref` produces exactly this `raw/`-prefixed shape, so the
check is the inverse of the writer.

**Q2 — What does AC01 do with `http(s)://` source entries?**
DECIDED: skip them, no finding. URL-sourced pages are legitimate; the check's
contract is "*file* refs resolve", not "every ref is a file".
RATIONALE: flagging URLs would make the check unusable on any augmented page and
would train operators to ignore it.

**Q3 — Should `allowed_values` support nested paths (`items[].kind`)?**
DECIDED: **No — root-level keys only.**
ARGUE FOR: `capture.py:280,286` has nested `kind` / `confidence` enums that a
root-level map cannot reach, so the class is not fully closed.
ARGUE AGAINST: supporting it means inventing a path mini-language inside a security
validator — new parsing surface, new failure modes, and exactly the speculative
generality Step 10 `/simplify` exists to strip. The nested enums are already
enforced by `_call_llm_json`'s jsonschema pass, and `confidence` gets a second
check downstream via `validate_frontmatter`.
DECIDED: root-level only; `capture.py`'s nested enums are a **deliberate
out-of-scope same-class peer** (cycle-16 L1) and get a BACKLOG entry per
cycle-23 L3 (a promised deferral without a filed entry is a review BLOCKER).
CONFIDENCE: high — lower blast radius, and the backlog item is specifically about
the *action* vocabulary.

**Q4 — Does AC04 extend to `_atomic_text_write_replace`?**
DECIDED: **Yes, include it.** Identical shape (`Path(tmp_path).replace(path)` at
`io.py:223`), identical durability class (wiki pages, `log.md`), one-line addition.
RATIONALE: C31-L2 — default INCLUDE same-class peers when the change is a one-liner.
Excluding it would leave the more frequently written surface unprotected while
hardening the rarer one.

**Q5 — Should the AC04 dir-fsync raise like `_flush_and_fsync` does?**
DECIDED: no — log WARNING and swallow `OSError`.
RATIONALE: `_flush_and_fsync` guards content integrity (a half-written file is
corruption). The dir fsync guards only rename *durability*, whose failure mode is a
re-ingest, not corruption. Making it fatal would convert currently-working writes
into hard failures on filesystems that reject directory fsync. Reversible beats
irreversible.

**Q6 — Where exactly does the AC03 human log go?**
DECIDED: after `_commit_ingest_manifest`, and after the `stage=success` JSONL
emission.
RATIONALE: JSONL is the authoritative correlation surface; emitting it first
minimises the window in which a durable ingest has no terminal machine record. The
human log is best-effort and already swallows `OSError`.

## DESIGN-AMEND (raised at Step 9, resolved before Step 10)

**AC01 severity is split, not uniform.** The original AC text said only
"unresolvable entries become a lint finding" and I implemented every finding as
`severity: "error"`. Running the existing suite showed why that is wrong:
`test_v5_lint_augment_cli.py::test_cli_lint_augment_propose_default` began
failing because its fixture page declares `source: raw/articles/test.md` without
creating the file, and an `error` flips `kb lint`'s exit code to 1.

The fixture is not the problem — it is a faithful sample of the real situation.
A raw source can legitimately be pruned, archived, or moved after ingest, so a
missing file is a hygiene signal the operator should judge, not a hard failure
that breaks every `kb lint` invocation on an existing repo. Introducing a NEW
check that flips exit codes repo-wide is exactly the always-on, high-blast-radius
change the design-gate bias rejects.

But the two failure modes are not the same class:

| Case | Severity | Why |
|---|---|---|
| Ref resolves under `raw/` but no file is there | `warning` | Legitimately reachable state (pruned/moved source). Surfaced, non-blocking; operator decides. |
| Ref does not resolve under `raw/` at all | `error` | Never legitimate. Either corruption or an injection attempt (T1). No valid workflow produces it. |
| Per-page ref cap exceeded | `warning` | Coverage notice, not a defect. |

DECIDED: ship the split. It satisfies the AC (both cases still produce a finding
naming the page and the dangling ref) while keeping the blast radius
proportionate to what each case actually means. Escalating the `warning` case to
`error` later is a one-line change once repos are clean; starting at `error` and
retreating would be the irreversible direction.

## CONDITIONS (Step 9 must satisfy)

1. AC01 must **not** call `.exists()` / `.stat()` on any ref that fails the
   containment check — the test asserts this with a spy, not by inspecting source.
2. AC02's enum must be read from `_PROPOSER_SCHEMA`, never from the response; the
   negative test must be `xfail-strict` so it fails loudly if it starts passing.
3. AC02 removes the now-dead `if action != "propose"` branch — and the removal is
   covered by a test that reaches `_propose_urls` with an invented action.
4. AC03 must add **both** halves: the reorder AND the `committed` flag. (C19-L2:
   dual-mechanism ACs get split into separate deliverables or one silently ships.)
5. AC04 applies to **both** `atomic_json_write` and `_atomic_text_write_replace`.
6. Every regression test must fail against a revert of its production change
   (C16-L2 / C24-L4). Verify by stubbing the production helper to a no-op.
