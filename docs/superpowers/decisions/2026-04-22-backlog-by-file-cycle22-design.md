# Cycle 22 — Design Decision Gate

VERDICT: APPROVE-WITH-DECISIONS

Scope (post-R2): Group A (wiki-path guard, AC1-AC4), Group B (grounding
clause, AC5-AC6), Group C (inspect.getsource spy replacement, AC7-AC9),
Group D DROPPED, Group E (regression pins, AC10-AC13), Group F (docs
cleanup, AC14). 14 ACs total.

---

## Q1 — raw-dir guard type symmetry (ValueError vs ValidationError)

### Analysis

The existing `raw_dir` sibling guard at `src/kb/ingest/pipeline.py:1169`
raises bare `ValueError`. That guard was written pre-cycle-20, before
`kb.errors.ValidationError(KBError)` existed as the canonical
input-validation exception. Cycle 20 AC1 introduced the taxonomy
explicitly to give boundary layers (`_error_exit`, MCP tool wrappers)
a single specialised base to catch — `ValidationError` is a subclass
of `KBError` which is a subclass of `Exception`, so any legacy caller
doing `except ValueError` will STILL miss a `ValidationError`. That is
the crux: option (a) is a latent API break for every caller that
wraps `ingest_source` with `except ValueError`, even though the MRO
preserves `isinstance(err, Exception)`. Cycle 20 itself preserved the
old raw-dir guard as `ValueError` precisely because it had not been
scoped into that change's threat model.

Option (b) — ship the new guard as `ValidationError`, accept the
asymmetry — is the lower-blast-radius choice. New code follows the
canonical convention, existing code is unchanged, and a follow-up
cycle can migrate the raw-dir guard under a dedicated design gate
with caller-grep (the kind of Step 11 signature-drift check my
feedback rules require). Option (c) downgrades the NEW guard to
`ValueError` to "match the neighbour," which is exactly the drift
pattern that gave us the `_MAX_PAGE_ID_LEN` divergence in cycle 5 —
matching a bad example institutionalises the bug. The threat T3
(path-leak) is addressed independently by filtering the `wiki_dir`
path out of the exception message regardless of exception class.

### DECIDE: (b) — ship new wiki-path guard with `ValidationError`; document raw-dir asymmetry as a cycle-23 candidate

### RATIONALE: Lower blast radius than (a), follows cycle 20 convention, avoids the "match-the-bug" drift (c). Asymmetry is a documented follow-up, not a regression.

### CONFIDENCE: HIGH

---

## Q2 — AC4 guard ordering vs `source_path.resolve()` (line 1139)

### Analysis

The threat model (T1 symlink bypass, T2 Windows case bypass) both
depend on *resolved* paths. A pre-resolve guard that compares raw
`source_path` to raw `wiki_dir` is defeated by the attacker symlinking
`raw/decoy.md -> wiki/real-page.md`; the pre-resolve check sees a path
under `raw/`, the post-resolve filesystem write lands inside `wiki/`.
The existing raw-dir sibling guard at line 1164-1169 already does the
right thing — it `.resolve()`s the effective raw dir and `normcase`s
both sides. The wiki guard must follow the same pattern and for the
same reason. Option (b) — pre-resolve — is therefore dead on arrival
for the threat model.

Option (a) — guard goes AFTER `source_path.resolve()` (line 1139)
AND AFTER `effective_wiki_dir = ...` (line 1208) — is the only one
that correctly addresses T1+T2. Placement: between line 1208 and the
existing `_emit_ingest_jsonl("start", ...)` at line 1222. Placing it
BEFORE the start-log emission also fixes T4 (orphan start-log row):
if the guard rejects, no JSONL row is emitted, so the `start` /
`failure` pair is atomic. If we placed the guard AFTER the start-log
emit, we'd need to wrap it in the outer try to convert the raise into
a `stage="failure"` row — correct but strictly more code. Pre-emit
placement is simpler and strictly safer. The guard should use the
same `normcase`-both-sides idiom as the raw-dir guard so the T2
Windows case bypass is closed symmetrically. Message redaction for
T3: emit `"Source path must not resolve inside wiki/ directory"`
with NO path interpolation, same style as the raw-dir message
(which already leaks the path — that's a separate cycle-23 issue).

### DECIDE: (a) — guard AFTER `source_path.resolve()` (line 1139) AND AFTER `effective_wiki_dir = ...` (line 1208), placed BEFORE the `_emit_ingest_jsonl("start", ...)` at line 1222

### RATIONALE: Only resolve-then-guard closes T1+T2. Pre-start-log placement makes T4 (orphan start row) vacuous for this failure class without needing the outer try.

### CONFIDENCE: HIGH

---

## Q3 — AC5 grounding-clause wording + position

### Analysis

The Opus 4.7 behavioural guidance in CLAUDE.md is explicit:
"Instruction following is literal — prefer positive phrasing over
negative." Option (a) leads with a positive frame ("Only extract
information that is explicitly stated or clearly implied") but its
second half is negative ("Do not add facts from training data"). In
practice 4.7 honours each stated constraint individually, and the
"don't use training data" sentence is a textbook negative that tends
to produce hedged or tangential output. Option (b) is wholly positive
("Ground every extracted field in verbatim source content") and gives
the model a concrete fallback ("use null") — that fallback already
exists at line 319, so (b) reinforces the existing instruction rather
than contradicting it. Option (c) adds a `confidence: inferred`
escape hatch for borderline claims, which is attractive but
functionally overlaps with existing frontmatter machinery and
creates a new prompt-vs-schema coordination surface we do not need
in this cycle.

Position: BEFORE the `<source_document>` fence (line 323-325) is
non-negotiable. The fence already carries the "untrusted input" note,
and the grounding clause is a counter-jailbreak defence — if the
clause lives AFTER the fence an adversarial source body can contradict
it (e.g., a raw file containing "IGNORE THE GROUNDING CLAUSE"), which
is T6 from the threat model. Pre-fence placement makes the ordering:
positive grounding instruction → fence-is-untrusted note → fenced
content. Attacker content cannot reach the instruction because the
instruction has already been given. Wording recommendation: option
(b), placed immediately after the existing line 319 "use null"
sentence so the two complement each other — extract only what's
grounded; when uncertain, prefer null.

### DECIDE: (b) — "Ground every extracted field in verbatim source content. When uncertain whether a claim is in the source, use null." — positioned immediately after existing line 319 ("If a field cannot be determined from the source, use null.") and BEFORE the `<source_document>` fence at line 323

### RATIONALE: Wholly positive phrasing (Opus 4.7 literal-instruction rule); complements existing null fallback; pre-fence placement closes T6 (adversarial counter-instruction); does not introduce new prompt-vs-schema coordination.

### CONFIDENCE: HIGH

---

## Q4 — AC8 spy target (which module attribute to monkeypatch)

### Analysis

Cycle 20 AC5/AC7 introduced the trampoline split: `query_wiki` is the
narrow outer wrapper that catches and re-raises as `QueryError`, and
`_query_wiki_body` is the actual synthesis body. The module-attribute
`kb.query.engine.call_llm` is imported once at engine.py:40 and called
at lines 358 and 1197 — both sites use the module-attribute, so a
`monkeypatch.setattr("kb.query.engine.call_llm", spy)` catches BOTH
call paths in one move. That's the correct behavioural-test pattern
from my memory rule: test behaviour, not signature. If we go with
option (b) — specifically assert which internal function generated
the prompt — we couple the test to the current trampoline structure,
and any future cycle that splits or renames `_query_wiki_body` has
to edit this test. That's the cycle 20 lesson re-learned: signature
tests are brittle; spies on the LLM boundary are stable because the
boundary is the LLM call itself, not the call site.

Option (a) — monkeypatch `kb.query.engine.call_llm`, assert spy was
called with the grounding clause text present in the prompt — is
the stable choice. The spy captures the prompt argument, inspects
it for the grounding clause verbatim (or a stable anchor phrase
like "verbatim source content"), and asserts presence. This pattern
also verifies real production flow: the test reaches the synthesis
prompt via a real `query_wiki()` call that goes through the
trampoline unmodified. My feedback rule "inspect-source tests are
signature-only" (2026-04-20) applies here: the cycle-5-redo tests
used `inspect.getsource(engine.query_wiki) + inspect.getsource(
engine._query_wiki_body)`, which still passes after a revert because
`inspect.getsource` reads the file, not the runtime behaviour. The
cycle 22 AC7-AC9 replacement MUST exercise the real code path.

### DECIDE: (a) — monkeypatch `kb.query.engine.call_llm` (module attribute), assert the spy was called with the grounding clause text in the prompt argument

### RATIONALE: Behaviour-over-signature (memory rule feedback_test_behavior_over_signature + feedback_inspect_source_tests); catches BOTH call sites; survives future trampoline refactors; patches at the LLM boundary which is the stable seam.

### CONFIDENCE: HIGH

---

## Q5 — AC14 stale-BACKLOG evidence sufficiency

### Analysis

The two items under review are the Phase 4.5 MEDIUM "thin MCP tool
coverage" backlog item and an item citing
`test_cycle17_ac14_query_wiki_threads_purpose_to_synthesis_prompt`.
The second one is a function inside
`tests/test_v0p5_purpose.py:97`, not a top-level file. A backlog
item that cites a non-existent FILE is stale on its face — if the
FUNCTION covers the behaviour, the intent is satisfied. Evidence
sufficiency for deletion requires three conditions: (1) a specific
test actually exercises the intended code path, (2) the test is
behavioural (not `inspect.getsource`), (3) the test currently passes
in the full suite. The function in `test_v0p5_purpose.py:97` threads
`purpose` through `query_wiki` and asserts it reaches the synthesis
prompt — that IS a behavioural test, and it's in the current 2720
collection, so conditions (1)-(3) are met. BACKLOG cleanup of that
item is safe.

The Phase 4.5 "thin MCP tool coverage" item is a broader claim about
the MCP surface. `tests/test_cycle17_mcp_tool_coverage.py` explicitly
covers the 4 MCP tools called out in R1, so by construction the
evidence is direct — the test file IS the specific remediation. The
general risk pattern here is BACKLOG re-add (T11): someone finds
ONE uncovered MCP tool later and re-files the same item. Mitigation:
when the BACKLOG item is deleted in AC14, the CHANGELOG entry should
cite the specific test file that closed it so future readers have a
breadcrumb. If a fresh gap surfaces later the new BACKLOG item names
the new gap specifically, not the general coverage claim. This is
consistent with my BACKLOG.md lifecycle rule: resolved items deleted,
fix recorded in CHANGELOG. Both deletions qualify.

### DECIDE: (YES to both) — existing function coverage (test_v0p5_purpose.py:97) AND existing file coverage (test_cycle17_mcp_tool_coverage.py) are sufficient evidence to delete both BACKLOG items; CHANGELOG entry must cite the specific test path

### RATIONALE: Both items satisfy the 3-condition sufficiency rule (specific, behavioural, currently passing). CHANGELOG breadcrumb mitigates T11 re-add risk.

### CONFIDENCE: HIGH

---

## Q6 — AC14 CLAUDE.md test-count reconciliation

### Analysis

CLAUDE.md carries two divergent counts: line 33 (Implementation
Status) says "2710 passed + 8 skipped (cycle 21; 2718 collected)"
and line 180 (Testing section) says "2689 passed + 8 skipped; 2697
collected" (cycle 20 context). Current actual collection is 2720
(verified via `pytest --collect-only`). Cycle 20 L2 lesson flagged
exactly this class of issue — documentation drift where two sections
in the same file disagree. My memory rule `feedback_migration_breaks_
negatives` and the broader "docs sync" pattern require atomic fixes:
if we touch one count we touch both. Option (b), updating only the
Implementation Status line, institutionalises the drift by leaving
the Testing section stale — exactly the failure mode we are trying
to avoid in cycle 22. Option (a) updates both atomically to the
cycle-22 post-implementation count.

The exact post-implementation count depends on how many new tests
cycle 22 adds. Group C is a REPLACEMENT (delete 1, add N>=1), Group
E adds 4 regression pins, Group F is doc-only. Conservative estimate:
cycle 22 adds roughly 4-6 net tests (Group E pins plus any delta
from the Group C spy replacement vs the deleted inspect.getsource
test). Step 09 implementers should run `pytest --collect-only` AFTER
all code changes land and plug the exact count into BOTH CLAUDE.md
lines as well as the CHANGELOG Quick Reference table. A secondary
condition: the implementer should grep for any other location that
cites a test count (CHANGELOG entries, README, docs/architecture)
and update those in the same commit to prevent drift-by-omission.

### DECIDE: (a) — update BOTH CLAUDE.md locations (line 33 Implementation Status AND line 180 Testing section) atomically to the cycle-22 post-implementation count; also sync CHANGELOG Quick Reference table

### RATIONALE: Cycle 20 L2 explicitly flagged this drift pattern. Atomic update prevents the "fix one, leave the other stale" re-occurrence.

### CONFIDENCE: HIGH

---

## CONDITIONS (Step 09 must satisfy)

1. **AC3/AC4 guard placement**: wiki-path guard raises
   `kb.errors.ValidationError` (imported from `kb.errors`, not bare
   `ValueError`); guard is placed AFTER both `source_path.resolve()`
   (line 1139) and `effective_wiki_dir = ...` (line 1208), and BEFORE
   the `_emit_ingest_jsonl("start", ...)` call (line 1222). Guard
   uses `os.path.normcase` on both sides of the comparison, matching
   the raw-dir sibling guard at line 1164-1165. Exception message
   must NOT interpolate the path (T3 mitigation).

2. **AC5 grounding-clause wording**: exact clause "Ground every
   extracted field in verbatim source content. When uncertain whether
   a claim is in the source, use null." inserted in
   `build_extraction_prompt` at `src/kb/ingest/extractors.py`,
   positioned immediately after the existing line 319 null-fallback
   sentence and BEFORE the `<source_document>` fence at line 323.
   Step 09 must verify clause ordering with a one-line Grep:
   `clause_idx < fence_idx` in the generated prompt body.

3. **AC8 spy target**: the replacement test in
   `tests/test_cycle5_hardening.py` MUST use
   `monkeypatch.setattr("kb.query.engine.call_llm", spy)` and
   assert the spy was called with the grounding clause text (or a
   stable anchor phrase) in the prompt argument. Any use of
   `inspect.getsource(...)` to verify prompt content is forbidden
   (memory rule `feedback_inspect_source_tests`). The old
   `inspect.getsource` test MUST be deleted, not commented out.

4. **AC14 BACKLOG deletions**: each of the 10 deleted items MUST
   have a corresponding CHANGELOG entry citing the specific test
   file (or test function) that closed it. No silent deletions.
   Resolved Phases section in BACKLOG.md gets a one-liner if a
   whole phase section collapses to empty after deletion.

5. **AC14 CLAUDE.md atomic update**: BOTH line 33 (Implementation
   Status) and line 180 (Testing section) updated to the same
   cycle-22 post-implementation count. Step 09 must run
   `.venv/Scripts/python -m pytest --collect-only -q | tail -3`
   AFTER all code changes land, then plug that exact number into
   both lines plus the CHANGELOG Quick Reference table in the same
   commit. Also grep for "2689", "2697", "2710", "2718", "2720"
   across docs/ to catch ancillary drift.

6. **AC4 start-log orphan ordering**: Step 09 must add a test in
   the new Group E file that simulates a wiki-path-resolved source
   and verifies `.data/ingest_log.jsonl` contains ZERO rows for
   that request (T4 regression pin — no orphan `start` row).

7. **Caller-grep checkpoint**: because AC3 introduces a new
   exception class at a boundary, Step 11 must grep for existing
   `except ValueError` callers of `ingest_source` (CLI, MCP tools,
   tests) to confirm none rely on catching this specific failure
   mode via `ValueError`. Any caller that does must be widened to
   `except (ValueError, ValidationError)` in the same cycle or
   the raise class downgraded. Per cycle 20 lesson
   `feedback_signature_drift_verify`.

8. **Co-author trailer policy**: PR commits MUST NOT include the
   `Co-Authored-By: Claude` trailer (memory rule
   `feedback_no_coauthor`). Step 13 commit command must use a raw
   HEREDOC without trailer.

9. **venv discipline**: any new dependency (none expected in
   cycle 22 scope) installs via `.venv/Scripts/pip`, never
   system Python (memory rule `feedback_venv`).

---

## FINAL DECIDED DESIGN

**Cycle 22 — pre-Phase-5 backlog hardening (14 ACs across 5 file
groups).**

*Group A — wiki-path guard (AC1-AC4), `src/kb/ingest/pipeline.py`.*
`ingest_source` gains a defence-in-depth guard that rejects any
`source_path` which, after `.resolve()`, lands inside the effective
wiki directory. The guard is placed between the existing
`effective_wiki_dir = ...` assignment (line 1208) and the
`_emit_ingest_jsonl("start", ...)` call (line 1222). It uses
`os.path.normcase` on both sides (T2 Windows-case bypass closed) and
compares resolved paths (T1 symlink bypass closed). On mismatch it
raises `kb.errors.ValidationError` with a path-free message (T3
mitigated). Placing the guard before the start-log emit means a
rejected ingest produces NO orphan JSONL row (T4 mitigated). The
existing raw-dir sibling guard remains `ValueError` for back-compat;
a cycle-23 follow-up migrates it under its own design gate.

*Group B — grounding clause (AC5-AC6), `src/kb/ingest/extractors.py`.*
`build_extraction_prompt` gains one new sentence immediately after
the existing line 319 null-fallback: "Ground every extracted field
in verbatim source content. When uncertain whether a claim is in
the source, use null." Wholly positive phrasing (Opus 4.7 rule),
pre-fence placement so adversarial source content cannot counter-
instruct (T6). T5 (advisory-only) is accepted as a known limitation;
schema-level enforcement is a Phase 5 candidate.

*Group C — inspect.getsource replacement (AC7-AC9),
`tests/test_cycle5_hardening.py`.* The existing
`test_synthesis_prompt_uses_wikilink_citation_format` (uses
`inspect.getsource`) is DELETED and replaced with a behavioural test
that monkeypatches `kb.query.engine.call_llm` with a spy, calls
`query_wiki` with a minimal wiki fixture, and asserts the spy was
called with the canonical `[[page_id]]` instruction substring in the
prompt argument. Catches BOTH call sites at lines 358 and 1197
without coupling to `query_wiki` vs `_query_wiki_body` split. T8
(vacuous-test revert) closed; T9 (wrong monkeypatch target) closed
by patching the module attribute which is the single import point.

*Group D — DROPPED.* `tests/test_cycle17_mcp_tool_coverage.py`
already covers the 4 MCP tools identified in R1; no new work
required.

*Group E — regression pins (AC10-AC13),
`tests/test_cycle22_wiki_guard_grounding.py` (new).* Four pins:
(AC10) `source_path` under `wiki/` raises `ValidationError` and
emits ZERO ingest-log rows; (AC11) symlink `raw/decoy.md ->
wiki/real.md` is caught by post-resolve guard; (AC12) Windows
mixed-case `WIKI/real.md` caught via normcase; (AC13) grounding
clause appears BEFORE `<source_document>` fence in generated prompt
(clause_idx < fence_idx).

*Group F — docs cleanup (AC14).* Delete 10 verified-resolved items
from `BACKLOG.md`, each with a CHANGELOG entry citing the specific
closing test. Update CLAUDE.md lines 33 AND 180 to the cycle-22
post-implementation test count (run `pytest --collect-only` after
all code lands). Sync CHANGELOG Quick Reference table. Grep for
stale "2689 / 2697 / 2710 / 2718" counts anywhere in docs/ and
update atomically.

**Test-count reconciliation pathway**: Step 09 implements Groups A-E,
runs `.venv/Scripts/python -m pytest --collect-only -q | tail -3`,
records the exact number (estimated 2723-2725), plugs it into both
CLAUDE.md locations and CHANGELOG in Step 12 docs pass, then Step 13
commit includes all changes under one atomic commit (no trailer).

**Blast radius**: 1 source file (pipeline.py), 1 source file
(extractors.py), 1 test file modified (test_cycle5_hardening.py),
1 test file added (test_cycle22_wiki_guard_grounding.py), 3 doc
files (BACKLOG.md, CHANGELOG.md, CLAUDE.md). No public API breaks
for callers who catch `KBError` or `Exception`; `except ValueError`
callers of `ingest_source` retain the raw-dir guard path unchanged
(the new wiki-path guard is a new failure mode, not a migration).
Opt-in scope: the grounding clause is advisory-in-prompt, not
hard-enforced, so it cannot regress extractions for sources that
already ground correctly. Reversibility: each AC has a clean revert
(the guard is an `if` block; the grounding sentence is a string
addition; the test is a net-new or targeted-replacement).
