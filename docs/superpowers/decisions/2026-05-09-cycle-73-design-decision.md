# Cycle 73 — Step 5 Design Decision Gate

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**Pipeline:** dev-mimo-opus (May 2026 trial — fourteenth)
**Gate:** Step 5 (decision/freeze)
**Inputs:**
- `2026-05-09-cycle-73-requirements.md` (6 ACs)
- `2026-05-09-cycle-73-threat-model.md` (T1-T11 STRIDE)
- `2026-05-09-cycle-73-brainstorm.md` (2-3 approaches per AC)
- `2026-05-09-cycle-73-design-eval-R1-opus.md` (Opus, 9 conditions)
- `2026-05-09-cycle-73-design-eval-R2-deepseek.md` (DeepSeek, 4 findings)

**Bias:** lower blast radius wins (reversible > irreversible, internal > public, opt-in > always-on).
**Standing instruction:** `feedback_auto_approve` — Opus subagent gates substitute for human gates. NO ESCALATE.

---

## 1. VERDICT

**APPROVE-WITH-CONDITIONS.**

All 6 ACs are architecturally sound, threat-model-complete (T1-T9 mitigated; T8/T10/T11 explicitly accepted), and consistent with the cycle-72 chain-of-refinement. R1 raised 9 CONDITIONs (none architectural blockers; all call-site discipline / terminology / test-shape clarifications). R2 raised 4 FINDINGs (1 already-specified, 1 deferred to cycle-74+, 1 Step-9 design choice, 1 same-class-peer planning). One requirements-doc fact (AC05 scope) is invalidated by primary-session grep — pivoted below.

No BLOCKERs. No back-to-Step-1. Ship plan after Step 5 freezes the conditions resolved here + 1 AC05 pivot.

---

## 2. DECISIONS (table)

Per question / condition / finding: `OPTIONS → ARGUE → DECIDE → RATIONALE → CONFIDENCE`.

### Q1 — `prompt_version` mutability semantics (accessor vs read-side back-fill vs migration)

**OPTIONS:** (A) accessor-not-mutation; (B) read-side back-fill (mutating `_VERDICTS_CACHE` entries); (C) one-shot load-time migration rewriting the file.

**Analysis:**

The threat-model §T7 (Tampering — corruption of forensic on-disk state) is the controlling constraint. `_VERDICTS_CACHE` returns a SHALLOW copy of the cached list (`return list(cached[2])` at `verdicts.py:108`); the entries inside are NOT deep-copied. If Approach B back-fills `entry["prompt_version"] = 0` on the dict references inside the cache, the next `save_verdicts(...)` call serialises the mutated list — the back-fill bleeds onto disk. A 2026-01 verdict that was genuinely written without a `prompt_version` key would silently gain a `0`, and a forensic investigator can no longer distinguish "key was absent" from "key was zero by design". This is exactly the ground-truth-loss attack class.

Approach C (one-shot migration) carries the `feedback_migration_breaks_negatives` lesson — load-time migrations have broken legacy `K not in D` tests in past cycles, and the write-on-read pattern adds partial-write corruption risk for a defense-in-depth need that never actually requires schema uniformity. The accessor-only approach (A) preserves the on-disk-vs-in-memory equivalence absolutely: cache contents byte-for-byte mirror the JSON file. The "discipline burden" objection (callers must use `get_prompt_version` not `entry["prompt_version"]`) is hollow because no caller currently reads the field — the field is brand-new — so the burden materialises only on new code that can adopt the accessor at point-of-introduction.

**DECIDE:** Approach **A — accessor-not-mutation**. `get_prompt_version(entry)` returns `entry.get("prompt_version", 0) if isinstance(entry, dict) else 0`. `load_verdicts` UNCHANGED.

**RATIONALE:** Threat-model T7 demands cache fidelity; accessor preserves it; mutation cannot. **CONFIDENCE: HIGH.**

---

### Q2 — `_validate_tier_boundary` schema-derivation (explicit `expected_keys` only vs `schema=` shortcut vs both)

**OPTIONS:** (A) explicit `expected_keys: frozenset[str]` only; (B) `schema: dict` only; (C) both kwargs accepted.

**Analysis:**

Threat-model §T5 (Spoofing — LLM-fabricated `expected_keys`) names the key risk: a naive `expected_keys=frozenset(scan_output.keys())` self-validating loop hollows out the entire defense. The mitigation is to anchor `expected_keys` against a non-LLM source — i.e., the local Python `_build_schema_cached("article")` builder. That anchor must be visible at the call site so Step-14 grep can verify (`grep -n "expected_keys=" orchestrator.py | grep -v "schema\['properties'\]\|schema\.get"` returns zero rogue derivations). Approach A puts the anchor at the call site explicitly. Approach B (`schema=` only) hides JSONSchema internals (`$ref` resolution, `allOf`/`oneOf`/`anyOf` shapes) inside the helper — leakage of validation concerns into the helper that the helper shouldn't own.

Approach C ("accept both") is the requirements-lean but fails KISS — two kwargs multiply test variants (well-formed×explicit, well-formed×schema-derived, extra-key×explicit, extra-key×schema-derived, …) and create call-site ambiguity (which one wins if both passed?). The cycle-72 R2 Codex review pattern would flag this on simplify-discipline grounds. R1 Opus explicitly rejected the "both" lean and recommended A; the brainstorm Approach A also recommends A; the threat-model §T5 implicitly assumes A. Three-doc consensus + KISS = pick A.

**DECIDE:** Approach **A — explicit `expected_keys` only, NO `schema=` shortcut**.

**RATIONALE:** T5 defense visible at call site; KISS; trivial 1-line `_expected_keys_from_schema(schema)` refactor possible in cycle-74+ if 3+ sites appear. **CONFIDENCE: HIGH.**

---

### Q3 — `max_depth=4` and `max_string_len=4096` defaults

**OPTIONS:** (i) 4 / 4096 (lean); (ii) 8 / unbounded; (iii) 2 / 1024.

**Analysis:**

The threat-model §T6 (DenialOfService) is the constraint: pathological JSON depth or oversize strings exhaust memory or trigger `RecursionError`. The calibration must match the legitimate-traffic upper bound. Real-world extraction schemas top at depth 3 — root dict → field name → list-of-dicts → leaf dict. A depth bound of 4 has 1 level of slack, which absorbs minor schema evolution (e.g., per-claim confidence scoring as a sub-dict) without code change. Going to depth 8 is permissive enough to admit JSON-bombs (`{"a": {"a": {"a": ...}}}`) at moderate severity; depth 2 is too tight — legitimate `key_claims: [{"claim": "X", "evidence": [...]}]` already pushes 3.

For string length, `MAX_ISSUE_DESCRIPTION_LEN=4000` (verdicts.py:28) is the established peer cap; `4096` is its near-neighbour. A 96-char gap absorbs minor formatting (timestamps, IDs) without budget collapse. Going to unbounded eliminates the defense; 1024 is too tight (page-summary fields legitimately reach 2-3 KB).

R2 DeepSeek raised F-2 (no `max_keys` limit) and F-3 (missing-key validation scope) as adjacent concerns. F-2 is correctly DEFERRED to cycle-74+ (a separate DoS bound — `max_keys=500`); F-3 is a Step-9 implementer choice (cycle-73 helper rejects EXTRA keys; missing-key handling stays in downstream `.get()` consumers).

**DECIDE:** **option (i) — `max_depth=4`, `max_string_len=4096`**.

**RATIONALE:** Matches existing schema depth + `MAX_ISSUE_DESCRIPTION_LEN` peer; cycle-74+ can raise if needed. **CONFIDENCE: HIGH.**

---

### Q4 — Snapshot subjects pair selection (OBSOLETED — see AC05-pivot below)

**OPTIONS:** (A) `_render_sources` + `_build_summary_content`; (B) plus `kb publish --format graph` JSON-LD; (C) just `_render_sources`.

**Analysis:**

This question is INVALIDATED by primary-session grep. BACKLOG.md lines 79-80 list 6 deferred snapshot subjects, but `git grep` confirms FIVE are already pinned in committed tests:
- `_build_summary_content` — `tests/test_cycle70_snapshots.py:136` AC06 ✓
- `kb publish --format graph` JSON-LD = `build_graph_jsonld` — `tests/test_cycle70_snapshots.py` AC08 ✓
- `auto_publish_after_compile`'s llms-full.txt = `build_llms_full_txt` — `tests/test_cycle70_snapshots.py` AC07 ✓
- `build_extraction_prompt` — `tests/test_cycle69_snapshots.py:47` AC13 ✓
- `_render_sources` — `tests/test_cycle69_snapshots.py:149` AC15 ✓

Only `contradictions append` (`_persist_contradictions` at `src/kb/ingest/pipeline.py:183`) is genuinely pending. Q4 as posed picks among already-shipped subjects — picking either A, B, or C would create duplicate snapshot tests that lock in the same subject twice. The right move is to pivot AC05 to the genuinely-pending subject.

See **AC05-pivot** row below for the resolution.

**DECIDE:** Q4 SUPERSEDED. AC05 pivots to `_persist_contradictions` (single subject); AC06 extends to also clean the stale BACKLOG line 79-80.

**RATIONALE:** Five of six BACKLOG-listed subjects already shipped; only `_persist_contradictions` genuinely pending. **CONFIDENCE: HIGH.**

---

### Q5 — `prompt_version` value: 1 vs 2

**OPTIONS:** (A) `1` for "post-cycle-70 wrap_wiki_context family"; (B) `2` for "post-cycle-71 expansions"; (C) per-cycle bump (`70`, `71`, `72`, `73`).

**Analysis:**

The forensic semantics that matter to investigators are coarse-grained: "did this verdict come from the cycle-1 H14 literal-sentinel family (`<wiki_page_body>` / `<raw_source_N>` / `<untrusted_source>`) OR from the cycle-70+ `<wiki_context>` fenced family?". This is a binary distinction and that's what `prompt_version` should encode. Bumping to N=2 per cycle is a slippery slope toward a pseudo-git-rev tag — and the on-disk `timestamp` field already provides that resolution at higher granularity. The accessor returns `0` for legacy entries (= "pre-cycle-73 unknown"), and the timestamp + CHANGELOG-history.md cycle anchors are how investigators narrow further.

A future structural revision (e.g., a hypothetical cycle-80 "wrap_wiki_context_v2 with `##` sub-headers and explicit role markers") could justifiably bump to 2. Cycle-71 / 72 / 73 are all non-structural expansions of the same wrap call — they add new SITES, not new SHAPES — so they should all stamp 1.

**DECIDE:** Approach **A — `CURRENT_PROMPT_VERSION = 1`**.

**RATIONALE:** Forensic semantics are binary (literal-sentinel vs wrap-family); cycle-71/72/73 are site-expansions of the same shape; cycle-80+ structural revision would justifiably bump to 2. **CONFIDENCE: HIGH.**

---

### Q6 — Cycle-72 L8 cap-math invariant reuse in completeness path

**OPTIONS:** (A) reuse `_cap_page_content` as-is (inherits L8 fix); (B) re-derive cap math inline; (C) extract a NEW per-context-builder cap helper.

**Analysis:**

`_cap_page_content` at `semantic.py:37-56` already implements the cycle-72 R2 Codex M-1 cap-math fix (`text[: max_chars - len(_CAP_TRUNCATION_MARKER)] + marker`). Reusing the helper inherits the fix without re-deriving it. Approach B (inline re-derivation) reintroduces the L8 hazard at every new call site — exactly the failure cycle-72 R2 caught. Approach C (per-context-builder helper) is over-engineered — there are at most 3 context builders (fidelity, completeness, consistency) and they all share identical cap requirements.

R2 DeepSeek confirmed this in Category 5 (cycle-72 lessons): "M-1 (Codex fix): `max_chars - len(marker)` is used for slicing. PASS." R1 Opus also confirmed: "Cycle-72 lessons L1+L8 already encoded in `_cap_page_content`; reusing the helper inherits both." Two independent reviewers agree.

**DECIDE:** Approach **A — reuse `_cap_page_content` as-is**.

**RATIONALE:** Inherits cycle-72 R2 Codex M-1 fix at semantic.py:54 without re-derivation. **CONFIDENCE: HIGH.**

---

### Q7 — AC04 distinctness encoding (outcome enum vs sub-key vs exception class vs string-prefix)

**OPTIONS:** (A) outcome enum value; (B) sub-key on existing `payload`; (C) new exception class `TierBoundaryError`; (D) string-prefix on `payload["reason"]`.

**Analysis:**

The three input docs disagree: brainstorm recommends C (TierBoundaryError subclass); requirements §AC04 says A (outcome enum value); threat-model §T9 specifies D (string-prefix). R1 grep verification at `orchestrator.py:362, 402, 422` confirms every existing `manifest.advance(stub_id, "failed", payload={"reason": "..."})` uses string-prefix encoding inside `payload["reason"]`, NOT a top-level `outcome` field. The "outcome" terminology in requirements §AC04 is misleading — it's a positional state arg (`"failed"`, `"abstained"`, …), not a distinct payload field.

Approach C (TierBoundaryError subclass) fails simplify-discipline: the existing catch is `except Exception as e: msg = f"pre-extract failed: {type(e).__name__}: {e}"` — splitting into `except ValidationError as e: ... except Exception as e: ...` requires zero new exception class because `type(e).__name__` is already `"ValidationError"`. Adding a subclass would force an extra import + class definition + propagation surface for no functional gain. Approach B (sub-key) is forensically less distinct — greppers must read a sub-key rather than scan the reason prefix, breaking the cycle-23 R1 BLOCKER discipline.

Approach D (string-prefix `payload["reason"]=f"tier_boundary_rejected: {e}"`) matches existing project convention (cf. `blocked_by_allowlist:` at L261, `rate limited (retry Xs)` at L278). One-line catch-block edit, forensically distinct, no new symbols. Three of the four reviewers' implicit-or-explicit recommendation converges here when terminology is clarified.

**DECIDE:** Approach **D — `payload["reason"]=f"tier_boundary_rejected: {e}"` string-prefix; split-catch with `except ValidationError as e:` BEFORE generic `except Exception as e:`**.

**RATIONALE:** Matches existing `manifest.advance(...)` convention; no new exception class; forensically distinct; KISS. **CONFIDENCE: HIGH.**

---

### R1-C1 (AC02-2) — Step-9 caller-grep checkpoint for direct `save_verdicts(verdicts...` callers

**OPTIONS:** (A) MANDATORY checkpoint in Step 9; (B) defer to Step 11 PR review; (C) skip — assume `add_verdict` is the only writer.

**Analysis:**

Per `feedback_signature_drift_verify`, refactoring existing function signatures requires a Step-9 caller-grep checkpoint. AC02 doesn't refactor `add_verdict`'s signature, but it adds a NEW invariant ("every entry written via `add_verdict` is stamped"). If a production code path bypasses `add_verdict` and constructs verdict dicts directly + calls `save_verdicts(verdicts)`, that path silently violates the invariant — and the AC02 lock-in test would still pass because it tests the `add_verdict` path. R1 Opus correctly flagged this as CONDITION-AC02-2.

The grep is cheap (one rg invocation; ~10 seconds), the cost of a missed direct-writer is high (silent invariant violation surviving merge), so MANDATORY is the right answer.

**DECIDE:** Approach **A — MANDATORY Step-9 checkpoint**. `grep -rn "save_verdicts(verdicts" src/` runs and produces ZERO direct callers OR all found callers are routed through `add_verdict`.

**RATIONALE:** Cheap check + high cost-of-miss. **CONFIDENCE: HIGH.**

---

### R1-C2 (AC03-1) — Same-class peers `proposer.py:91, :168`

**OPTIONS:** (A) DEFER to cycle-74+ with BACKLOG entries; (B) expand AC03 to wrap all 3 sites this cycle; (C) skip — narrow to L394 only without BACKLOG entry.

**Analysis:**

Per cycle-16 L1 same-class peer rule, R1 Opus correctly enumerated `proposer.py:91` (`_PROPOSER_SCHEMA`) and `proposer.py:168` (`_RELEVANCE_SCHEMA`) as peers of `orchestrator.py:394` — all three are scan-tier `_call_llm_json` sites whose output flows into orchestrate-tier consumers. Approach B (expand this cycle) raises test count from ~5 to ~9 and call-site count from 1 to 3, which still fits Tier 2 — but the helper's design and threat-model coverage stay identical, so the marginal Tier-2-relevant value is small while blast radius doubles. Approach C (skip without BACKLOG) violates cycle-23 R1 BLOCKER discipline (deferred peers must be discoverable via BACKLOG grep with `cycle-N+1 if requested` token).

Approach A (DEFER + BACKLOG) is the lower-blast-radius path: cycle-73 nails the orchestrator site as the proof-of-concept; cycle-74+ planner sees the 2 deferred entries via BACKLOG grep. This matches the bias "lower blast radius wins" and the cycle-72 carry-over pattern (each cycle ships ONE new defense-class site + defers same-class peers if scope-tight).

**DECIDE:** Approach **A — DEFER with 2 BACKLOG entries** containing `cycle-N+1 if requested` token.

**RATIONALE:** Cycle-72 carry-over pattern; lower blast radius; cycle-23 R1 BLOCKER discipline preserved. **CONFIDENCE: HIGH.**

---

### R1-C3 (AC03-2) — Q2 single-param confirmation

Confirmed as Q2 resolution above. `_validate_tier_boundary(scan_output: dict, *, expected_keys: frozenset[str], max_depth: int = 4, max_string_len: int = 4096) -> dict` — NO `schema=` kwarg.

**DECIDE:** Confirmed. **CONFIDENCE: HIGH.**

---

### R1-C4 (AC03-3) — Manifest-write ordering

**OPTIONS:** (A) Validator BEFORE L408 `extracted` manifest write; (B) Validator AFTER L408; (C) Validator inside `_call_llm_json` as a wrapper.

**Analysis:**

If the validator runs AFTER L408 `manifest.advance(stub_id, "extracted", ...)`, the forensic trail records "extracted" for a record that was actually rejected — the manifest claims success when the record never reached the orchestrator's persister. This is a manifest-vs-reality skew that breaks audit. If the validator runs BEFORE L408 and rejects, no `extracted` entry is written; the trail goes directly `proposed → failed` (which is the truthful state — the LLM output never reached extraction-acceptable state). If the validator is wrapped INSIDE `_call_llm_json`, the boundary becomes invisible at the call site — defeating R1's same-class peer enumeration (you can't grep for `_validate_tier_boundary` at the call site if it's embedded in a generic wrapper).

R1's CONDITION-AC03-3 specifies BEFORE L408 explicitly; threat-model §T4 corroborates ("inserted between line 398 and line 411"). Two-doc agreement on Approach A.

**DECIDE:** Approach **A — Validator BETWEEN L398 (LLM-call return) and L408 (`extracted` manifest write)**. On rejection, L408 is bypassed; AC04 emits `failed` with `tier_boundary_rejected:` reason.

**RATIONALE:** Manifest reflects reality, not the validator-bypassed shape. **CONFIDENCE: HIGH.**

---

### R1-C5 (AC03-4) — Spy test must be behavioural

**OPTIONS:** (A) MANDATORY behavioural spy (counter / manifest payload assertion / production state change); (B) `inspect.getsource(orchestrator).contains("_validate_tier_boundary")` signature-only test; (C) skip the wiring test.

**Analysis:**

Per `feedback_inspect_source_tests`, signature-only tests pass after revert — they assert that the symbol exists in the source text, not that the production code path actually invokes it. Cycle-69 lessons + R1 Opus repeatedly flag this hazard. The wiring test must demonstrate that `_validate_tier_boundary` is INVOKED on the production path — concretely, by monkeypatching the validator with a counter-incrementing identity wrapper, calling the orchestrator, and asserting `counter > 0`. Or by asserting the manifest payload contains the validator's rejection reason on a known-rejected input.

Approach B is the cycle-69 anti-pattern; Approach C drops AC03's wiring assurance entirely. Approach A is the only behaviour-grounded option.

**DECIDE:** Approach **A — MANDATORY behavioural spy**. `test_orchestrator_pre_extract_calls_validator` exercises production code path via spy; MUST NOT use `inspect.getsource`.

**RATIONALE:** `feedback_inspect_source_tests` lesson; signature-only tests pass after revert. **CONFIDENCE: HIGH.**

---

### R1-C6 (AC04-1) — Terminology clarification (string-prefix not enum)

Confirmed as Q7 resolution above. CHANGELOG entry uses correct terminology: "manifest payload `reason` prefix `tier_boundary_rejected:`", NOT "outcome enum value".

**DECIDE:** Confirmed. **CONFIDENCE: HIGH.**

---

### R1-C7 (AC04-2) — Split-catch form

Confirmed as Q7 resolution above. `except ValidationError as e: payload["reason"]=f"tier_boundary_rejected: {e}"` THEN `except Exception as e: payload["reason"]=f"pre-extract failed: {type(e).__name__}: {e}"`. ValidationError-first ordering preserved; non-ValidationError keeps `pre-extract failed:` for back-compat with existing forensic grep.

**DECIDE:** Confirmed. **CONFIDENCE: HIGH.**

---

### R1-C8 (AC05-1) — Snapshot fixture pinning

**OPTIONS:** (A) MANDATORY literal pinning (budget value + source bodies + dates); (B) allow env-var derivation; (C) capture default and pin retroactively after first snapshot.

**Analysis:**

Snapshot tests serve as a regression fence — but only if the snapshot is deterministic. If the fixture passes `budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` (a config-derived number), a future config tweak that legitimately changes `QUERY_CONTEXT_MAX_CHARS` invalidates the snapshot for reasons unrelated to the subject under test — false-positive regression noise. Similarly, if `date.today()` flows through to the snapshot (as it does for `_persist_contradictions`), the snapshot drifts daily.

Approach C ("capture once") creates a circular dependency — the first capture defines the truth, and there's no independent fact-of-the-matter to compare against. Approach B leaves the false-positive failure mode in. Approach A pins all derived values to literals, isolating the snapshot to the subject under test only.

**DECIDE:** Approach **A — MANDATORY literal pinning**. Pin `budget=` to literal int; pin `date.today` via `monkeypatch.setattr` to a `FakeDateClass`; pin `contradictions` input to literal entries; pin `page_id` to literal string.

**RATIONALE:** Snapshot determinism requires literal values; config-derived numbers create false-positive failures. **CONFIDENCE: HIGH.**

---

### R1-C9 (AC06-2) — Literal-substring assertion + explicit line deletion

**OPTIONS:** (A) Literal-substring assertion + explicit line deletion (not reformat); (B) regex-loose match; (C) presence-of-token check only.

**Analysis:**

The pass test must catch the case where someone reformats the BACKLOG entry (e.g., changes Markdown bullet style or wraps text differently) but doesn't actually delete it. A regex-loose match could pass on a reformatted-but-still-present entry; a presence-of-token check might pass if the token appears elsewhere in the file. Literal-substring assertion (`"KB_DISABLE_VECTORS=1\` runtime kill-switch (cycle-N+1 if requested)" not in backlog_text`) is precise — it asserts the EXACT phrasing that defined the stale entry is gone.

R1 raised this as CONDITION-AC06-2; it's a narrow but real hazard.

**DECIDE:** Approach **A — literal-substring assertion + explicit line deletion**. Step-11 BACKLOG-grep checkpoint catches reformat-not-delete drift.

**RATIONALE:** Catches reformat-not-delete drift; precision over flexibility for hygiene tests. **CONFIDENCE: HIGH.**

---

### R2-F-1 (AC02 isinstance defensive check)

**OPTIONS:** (A) Already-specified — implementer must not skip; (B) Add an additional explicit `isinstance` check with logging; (C) Skip the defensive check entirely.

**Analysis:**

Test `test_get_prompt_version_handles_non_dict_inputs` is already in the AC02 plan, asserting `get_prompt_version(None) == 0`, `get_prompt_version([]) == 0`, etc. The defensive `isinstance(entry, dict)` check is a 1-line guard inside the accessor body. R2 DeepSeek's F-1 is correctly noted as "already specified — implementer must not skip" — there's no ambiguity, just a discipline reminder.

Approach B (add logging) is over-instrumentation for a defensive guard; Approach C silently violates the test plan.

**DECIDE:** Approach **A — already specified, implementer must not skip**.

**RATIONALE:** Test plan covers it; no design change. **CONFIDENCE: HIGH.**

---

### R2-F-2 (AC03 max_keys DoS bound)

**OPTIONS:** (A) DEFER to cycle-74+ with BACKLOG entry; (B) Add `max_keys=500` this cycle; (C) Skip entirely.

**Analysis:**

R2 DeepSeek noted that a malicious LLM response with 100k keys could exhaust memory. The current AC03 helper rejects EXTRA keys (any key not in `expected_keys`), so a 100k-key response WOULD be rejected at the first extra-key check — but the rejection happens AFTER the dict is fully parsed by JSON, by which point the memory is already allocated. A `max_keys=500` early-rejection bound would short-circuit before full parse.

However, the existing JSON parser (`json.loads` inside `_call_llm_json`) is the actual memory-allocation point, and `_validate_tier_boundary` runs AFTER that parse. Adding `max_keys=500` to `_validate_tier_boundary` doesn't prevent the parse-time allocation; the right place is upstream in `_call_llm_json` itself, which is out-of-scope this cycle. Filing as cycle-74+ BACKLOG keeps cycle-73 scope clean while preserving the planner's discoverability.

Approach C (skip) leaves a known DoS bound unfiled. Approach B adds a defense at the wrong layer.

**DECIDE:** Approach **A — DEFER to cycle-74+** with BACKLOG entry containing `cycle-N+1 if requested` token: "Add `max_keys: int = 500` early-reject default to `_call_llm_json` parse-time guard (cycle-N+1 if requested)".

**RATIONALE:** Right defense at the wrong layer for cycle-73 scope; defer for proper-layer fix. **CONFIDENCE: MEDIUM-HIGH.**

---

### R2-F-3 (AC03 missing-key validation scope)

**OPTIONS:** (A) Helper rejects EXTRA keys only; missing-key handling stays in downstream `.get()` consumers; (B) Helper also rejects missing required keys; (C) Helper silently fills missing keys with defaults.

**Analysis:**

Approach C is dangerous — silent default-filling masks LLM bugs (the LLM omitted `title` and got `""` injected, with no caller-visible signal). Approach B raises the helper's responsibility surface — it now needs a list of "required" keys distinct from "expected" keys, doubling the kwargs and the test matrix.

Approach A is the simpler boundary: cycle-73 helper's job is "reject extension by LLM" (the EoP threat); missing-key handling is a downstream concern handled by the existing `extraction.get("title", "")` pattern that callers already use. R2 DeepSeek's F-3 names this as a Step-9 design choice; the right answer is the smaller surface.

**DECIDE:** Approach **A — Helper rejects EXTRA keys only; missing-key handling stays in downstream `.get()` consumers**.

**RATIONALE:** Smaller surface; downstream `.get()` is the existing pattern; helper job is EoP defense, not schema completion. **CONFIDENCE: HIGH.**

---

### R2-F-4 (Same-class peer scan AC01 / AC03)

**OPTIONS:** (A) DEFER to cycle-74+ planning per AC peer enumeration; (B) Expand both ACs this cycle; (C) Skip planning.

**Analysis:**

For AC01: the cycle-72 + cycle-73 changes complete the trio (`build_fidelity_context` + `build_consistency_context` + `build_completeness_context`). No more same-class peers exist for `wrap_wiki_context` in `lint/semantic.py`. R1 confirmed the trio is closed. So AC01 has no further peers to defer.

For AC03: R1-C2 already enumerated 2 BACKLOG entries (`proposer.py:91, :168`). Approach A is the right action and is already covered by R1-C2 above. R2-F-4's "AC01 + AC03 expansion" framing collapses to "AC03 expansion" which is already DEFER + BACKLOG.

**DECIDE:** Approach **A — DEFER to cycle-74+; covered by R1-C2 BACKLOG entries**.

**RATIONALE:** AC01 trio closed; AC03 peers covered by R1-C2 BACKLOG entries. **CONFIDENCE: HIGH.**

---

### AC05-pivot — Pivot AC05 to `_persist_contradictions`; extend AC06 to clean stale BACKLOG line 79-80

**OPTIONS:** (A) Pivot AC05 → 1 subject (`_persist_contradictions`); extend AC06 to clean both KB_DISABLE_VECTORS line AND stale-snapshot list; (B) Expand AC05 to 2 NEW subjects (`_persist_contradictions` + something else still pending); (C) Drop AC05 entirely; bake cleanup into AC06.

**Analysis:**

Primary-session grep confirmed 5 of 6 BACKLOG-listed deferred subjects are already shipped in committed tests; only `_persist_contradictions` is genuinely pending. Requirements §AC05 picked `_render_sources` + `_build_summary_content` from the BACKLOG list, but those are exactly the already-shipped subjects (cycle-69 AC15 and cycle-70 AC06 respectively).

Approach B forces a search for a "second pending subject" outside the BACKLOG list, which is scope creep without a forensic anchor. Approach C drops the snapshot subject entirely, losing a regression-fence. Approach A is the surgical fix: AC05 ships ONE genuine snapshot subject (`_persist_contradictions`), AC06 cleans both stale BACKLOG sites in one pass, and the documentation accurately reflects what's pending.

The cycle-72 chain-of-refinement also benefits: a cycle that explicitly notes "the BACKLOG drifted; we audited and pruned 5 stale subjects + 1 stale env-var entry" is precisely the BACKLOG-hygiene pattern the project values.

**DECIDE:** Approach **A — Pivot AC05 → `_persist_contradictions` only; extend AC06 to clean both KB_DISABLE_VECTORS line AND stale-snapshot list**.

**RATIONALE:** Primary-session grep proves 5/6 BACKLOG-listed subjects already shipped; pivot is the surgical fix; AC06 extension folds the discovery into the cycle. **CONFIDENCE: HIGH.**

---

## 3. CONDITIONS (Step 7 + Step 9 contract)

Each is a checkbox the plan-gate verifies before code is committed.

### AC01 — `build_completeness_context` cap + wrap

- [ ] **C-AC01-1:** Pattern matches cycle-72 AC01 split-into-(header, body, closing)-triplet exactly (header outside fence, body inside fence, closing outside fence). Single `wrap_wiki_context(...)` call.
- [ ] **C-AC01-2:** `_render_sources(..., budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD)` plumbed to honor fence overhead.
- [ ] **C-AC01-3:** Mutation control xfail-strict: identity-monkeypatching `_cap_page_content` OR `wrap_wiki_context` makes lock-in test FAIL (proves both load-bearing).

### AC02 — Verdict-store prompt-shape stamp

- [ ] **C-AC02-1 (R1-C1):** Step-9 caller-grep `grep -rn "save_verdicts(verdicts" src/` runs and produces ZERO direct callers OR all found callers route through `add_verdict`. Document in Step-11 implementation log.
- [ ] **C-AC02-2 (R2-F-1):** `get_prompt_version` body is `return entry.get("prompt_version", 0) if isinstance(entry, dict) else 0`. Test `test_get_prompt_version_handles_non_dict_inputs` exercises `None`, `[]`, `""`, `0`, `3.14` inputs and asserts `0`.
- [ ] **C-AC02-3 (R1 UNSTATED-AC02-1):** `docs/reference/error-handling.md` notes `kb.lint.feedback_store` is intentionally OOS for `prompt_version` stamping (different forensic granularity).

### AC03 — Tier-boundary verifier helper

- [ ] **C-AC03-1 (R1-C2):** BACKLOG.md gains 2 new entries before cycle-73 ships, each containing literal `cycle-N+1 if requested` token:
  - `proposer.py:91` `_PROPOSER_SCHEMA` site — apply `_validate_tier_boundary` (cycle-N+1 if requested)
  - `proposer.py:168` `_RELEVANCE_SCHEMA` site — apply `_validate_tier_boundary` (cycle-N+1 if requested)
- [ ] **C-AC03-2 (R1-C3):** Helper signature is exactly `_validate_tier_boundary(scan_output: dict, *, expected_keys: frozenset[str], max_depth: int = 4, max_string_len: int = 4096) -> dict`. NO `schema=` kwarg.
- [ ] **C-AC03-3 (R1-C4):** Call site in `orchestrator.py` invokes validator BETWEEN L398 (LLM-call return) and L408 (`extracted`-state manifest write). On rejection, L408 is bypassed.
- [ ] **C-AC03-4 (R1-C5):** `test_orchestrator_pre_extract_calls_validator` exercises production code path via spy on side effect. MUST NOT use `inspect.getsource(...) contains "_validate_tier_boundary"`.
- [ ] **C-AC03-5 (R2-F-2):** BACKLOG entry filed: "Add `max_keys: int = 500` early-reject default to `_call_llm_json` parse-time guard (cycle-N+1 if requested)" — DoS bound for pathological 100k-key dicts.
- [ ] **C-AC03-6 (R2-F-3):** Missing-key handling stays in downstream consumer (`extraction.get("title", "")` etc.); cycle-73 helper rejects EXTRA keys only.
- [ ] **C-AC03-7:** `from kb.errors import ValidationError` import added to `orchestrator.py`. Acyclic verified — `kb.errors` imports only `pathlib`.

### AC04 — Manifest outcome distinctness

- [ ] **C-AC04-1 (R1-C6):** Requirements §AC04 wording "new outcome enum value" is corrected — actual encoding is `payload["reason"]=f"tier_boundary_rejected: {e}"` string-prefix. CHANGELOG entry uses correct terminology.
- [ ] **C-AC04-2 (R1-C7):** Catch block at orchestrator.py:399 splits into `except ValidationError as e: payload["reason"]=f"tier_boundary_rejected: {e}"` THEN `except Exception as e: payload["reason"]=f"pre-extract failed: {type(e).__name__}: {e}"`. ValidationError-first ordering verified.
- [ ] **C-AC04-3:** `test_orchestrator_records_tier_rejection_distinctly` asserts `manifest_payload["reason"].startswith("tier_boundary_rejected:")`. Mutation control: monkeypatching the prefix to `"llm_scan_failed:"` makes the test FAIL.

### AC05 (PIVOTED) — Single new snapshot subject `_persist_contradictions`

- [ ] **C-AC05-1 (PIVOT):** AC05 subject is `_persist_contradictions` (`src/kb/ingest/pipeline.py:183`) ONLY. The genuinely-pending entry from BACKLOG line 79-80; the other 5 listed subjects are already shipped in cycles 69-70.
- [ ] **C-AC05-2 (R1-C8):** Snapshot fixture pins literal `date.today` value via `monkeypatch.setattr("kb.ingest.pipeline.date", FakeDateClass)` returning `date(2026, 5, 9)`; pins `contradictions` list to literal entries; pins `page_id` to literal string. NO env-var / config-derived numbers in `.ambr` content.
- [ ] **C-AC05-3:** Test file `tests/test_cycle73_snapshots.py` + `tests/__snapshots__/test_cycle73_snapshots.ambr` created. Subsequent `pytest --snapshot-update` runs leave the snapshot byte-identical (deterministic).

### AC06 (EXTENDED) — BACKLOG hygiene (KB_DISABLE_VECTORS line + stale snapshot list)

- [ ] **C-AC06-1 (R1-C9):** `BACKLOG.md` `KB_DISABLE_VECTORS=1` runtime kill-switch entry deleted exactly (literal substring match), not reformatted.
- [ ] **C-AC06-2 (NEW — primary-session FACT):** `BACKLOG.md` lines 79-80 (snapshot-subjects deferred list) updated to reflect that 5 of 6 listed subjects ALREADY SHIPPED:
  - `_build_summary_content` (cycle-70 AC06) — REMOVE
  - `kb publish --format graph` JSON-LD = `build_graph_jsonld` (cycle-70 AC08) — REMOVE
  - `auto_publish_after_compile`'s llms-full.txt = `build_llms_full_txt` (cycle-70 AC07) — REMOVE
  - `build_extraction_prompt` (cycle-69 AC13) — REMOVE
  - `_render_sources` (cycle-69 AC15) — REMOVE
  - `_persist_contradictions` (cycle-73 AC05) — REMOVE post-merge
- [ ] **C-AC06-3:** `tests/test_cycle73_backlog_hygiene.py::test_kb_disable_vectors_entry_absent` literal-substring assertion. Mutation control: re-adding the line makes test FAIL.
- [ ] **C-AC06-4:** `tests/test_cycle73_backlog_hygiene.py::test_stale_snapshot_subjects_pruned` literal-substring assertion that `BACKLOG.md` does NOT list 5 already-shipped subjects under "deferred snapshot" framing.
- [ ] **C-AC06-5:** `CHANGELOG.md [Unreleased]` Quick Reference entry includes both BACKLOG cleanups (KB_DISABLE_VECTORS line + stale snapshot subjects).

### Cross-AC discipline

- [ ] **C-XAC-1:** Step 11 BACKLOG-grep checkpoint per cycle-23 R1: every "deferred / out of scope / scope-out" line in cycle-73 docs is filed in BACKLOG.md with literal `cycle-N+1 if requested` token. Specifically: AC03 peers (C-AC03-1) + max_keys (C-AC03-5).
- [ ] **C-XAC-2:** Step 9 caller-grep checkpoint per `feedback_signature_drift_verify` for ALL refactored signatures: `add_verdict`, `_render_sources`, `_validate_tier_boundary`, `build_completeness_context` callers grepped.
- [ ] **C-XAC-3:** Ruff format AFTER all Edits per `feedback_ruff_edit_ordering`.

---

## 4. FINAL DECIDED DESIGN — FROZEN at Step 5

### AC01 — `build_completeness_context` cap + wrap_wiki_context fence (FROZEN)

**File:** `src/kb/lint/semantic.py:466` (`build_completeness_context`).

**Helpers reused (no new helpers):**
- `_cap_page_content(text: str, max_chars: int) -> str` — already at `semantic.py:37`
- `wrap_wiki_context(text: str) -> str` — already at `kb.utils.text:355`
- `_FENCE_OVERHEAD` constant — already at `kb.utils.text:386`
- `_render_sources(..., *, budget: int | None = None)` — already at `semantic.py:70`

**Pattern (mirror of cycle-72 AC01 in `build_fidelity_context`):**

```python
def build_completeness_context(paired: dict) -> str:
    header_lines = [...]  # outside fence
    body_lines = [
        "## Wiki Page",
        _cap_page_content(paired["page_content"], QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD),
        "---",
        _render_sources(paired["source_contents"], budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD),
    ]
    closing_lines = [...]  # outside fence
    return "\n".join(header_lines) + "\n" + wrap_wiki_context("\n".join(body_lines)) + "\n" + "\n".join(closing_lines)
```

**Test class skeleton (`tests/test_cycle73_completeness_wrap.py`):**

```python
class TestCompletenessContextSingleFence:
    def test_completeness_context_includes_single_fence(self): ...
    def test_completeness_context_caps_oversized_page_content(self): ...
    def test_completeness_context_escapes_planted_closer(self): ...

class TestCompletenessContextMutationControl:
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_cap_page_content_identity_patched(self, monkeypatch): ...
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_wrap_wiki_context_identity_patched(self, monkeypatch): ...
```

### AC02 — Verdict-store `prompt_version` stamp (FROZEN)

**Files:**
- `src/kb/config.py` — `CURRENT_PROMPT_VERSION: int = 1`
- `src/kb/lint/verdicts.py` — `add_verdict` write-side stamp + module-level `get_prompt_version` accessor

**Signatures:**

```python
# kb/config.py
CURRENT_PROMPT_VERSION: int = 1  # post-cycle-70 wrap_wiki_context family

# kb/lint/verdicts.py
from kb.config import CURRENT_PROMPT_VERSION

def get_prompt_version(entry: dict) -> int:
    """Read-side accessor with default 0 for pre-cycle-73 entries.

    Cycle 73 AC02 — return 0 for "pre-cycle-73 unknown"; full archaeology
    OOS per requirements §non-goals #3.
    """
    if not isinstance(entry, dict):
        return 0
    return entry.get("prompt_version", 0)

def add_verdict(...):
    ...
    new_entry = {
        "timestamp": ...,
        "page_id": ...,
        "verdict_type": ...,
        "verdict": ...,
        "issues": ...,
        "notes": ...,
        "prompt_version": CURRENT_PROMPT_VERSION,  # NEW
    }
    ...
```

**Read-side contract:** `load_verdicts` UNCHANGED — does NOT mutate cached entries (preserves T7 invariant).

**Test class skeleton (`tests/test_cycle73_prompt_version.py`):**

```python
class TestAddVerdictStampsPromptVersion:
    def test_add_verdict_stamps_current_prompt_version(self, tmp_kb_env): ...
    def test_add_verdict_includes_key_in_atomic_write(self, tmp_kb_env): ...

class TestLoadVerdictsBackCompat:
    def test_load_verdicts_legacy_entry_default_zero(self, tmp_kb_env): ...
    def test_load_verdicts_does_not_mutate_cache(self, tmp_kb_env): ...

class TestGetPromptVersionAccessor:
    def test_get_prompt_version_returns_zero_on_legacy(self): ...
    def test_get_prompt_version_handles_non_dict_inputs(self): ...
    # None, [], "", 0, 3.14 -> all return 0

class TestPromptVersionMutationControl:
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_current_prompt_version_zeroed(self, monkeypatch): ...
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_get_prompt_version_identity_patched(self, monkeypatch): ...
```

### AC03 — Tier-boundary verifier helper (FROZEN)

**File:** `src/kb/lint/augment/orchestrator.py`.

**Signature:**

```python
from kb.errors import ValidationError  # NEW import — acyclic verified

def _validate_tier_boundary(
    scan_output: dict,
    *,
    expected_keys: frozenset[str],
    max_depth: int = 4,
    max_string_len: int = 4096,
) -> dict:
    """Re-gate scan-tier output before orchestrate-tier consumption.

    Defends T4 (EscalationOfPrivilege), T5 (Spoofing), T6 (DenialOfService).
    """
    if not isinstance(scan_output, dict):
        raise ValidationError(
            f"tier-boundary verification failed: not a dict, got {type(scan_output).__name__}"
        )

    extra = set(scan_output.keys()) - expected_keys
    if extra:
        raise ValidationError(
            f"tier-boundary verification failed: unexpected keys {sorted(extra)}"
        )

    def _walk(obj, depth):
        if depth > max_depth:
            raise ValidationError(
                f"tier-boundary verification failed: nesting depth > {max_depth}"
            )
        if isinstance(obj, str):
            if len(obj) > max_string_len:
                raise ValidationError(
                    f"tier-boundary verification failed: string length > {max_string_len}"
                )
        elif isinstance(obj, (int, float, bool, type(None))):
            return
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, depth + 1)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v, depth + 1)
        else:
            raise ValidationError(
                f"tier-boundary verification failed: disallowed type {type(obj).__name__}"
            )

    for v in scan_output.values():
        _walk(v, 1)

    return scan_output
```

**Call site (orchestrator.py BETWEEN L398 and L408):**

```python
extraction = proposer_mod._call_llm_json(
    _build_pre_extract_prompt(raw_content),
    tier="scan",
    schema=schema,
)
# AC03 — tier-boundary re-gate before orchestrate-tier consumption
extraction = _validate_tier_boundary(
    extraction,
    expected_keys=frozenset(schema["properties"].keys()),
)
manifest.advance(stub_id, "extracted", payload={"keys": list(extraction.keys())})
```

**Test class skeleton (`tests/test_cycle73_tier_boundary.py`):**

```python
class TestValidateTierBoundary:
    def test_accepts_well_formed(self): ...
    def test_rejects_non_dict(self): ...
    def test_rejects_extra_key(self): ...
    def test_rejects_oversize_string_at_4097(self): ...
    def test_accepts_string_at_4096(self): ...
    def test_rejects_deep_nesting_at_5(self): ...
    def test_accepts_nesting_at_4(self): ...
    def test_rejects_disallowed_type(self): ...

class TestOrchestratorWiring:
    def test_orchestrator_pre_extract_calls_validator(self, monkeypatch):
        # Spy via monkeypatch — count receipts
        ...
    def test_orchestrator_extra_key_caught(self, monkeypatch): ...

class TestTierBoundaryMutationControl:
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_validator_identity_patched(self, monkeypatch): ...
```

### AC04 — Manifest outcome distinctness (FROZEN)

**File:** `src/kb/lint/augment/orchestrator.py` (catch-block at L399+).

**Pattern (split-catch, ValidationError first):**

```python
try:
    extraction = proposer_mod._call_llm_json(...)
    extraction = _validate_tier_boundary(extraction, expected_keys=...)
    manifest.advance(stub_id, "extracted", payload={"keys": list(extraction.keys())})
except ValidationError as e:
    msg = f"tier_boundary_rejected: {e}"
    manifest.advance(stub_id, "failed", payload={"reason": msg})
    logger.warning("pre-extract %s: %s", stub_id, msg)
    continue
except Exception as e:
    msg = f"pre-extract failed: {type(e).__name__}: {e}"
    manifest.advance(stub_id, "failed", payload={"reason": msg})
    logger.warning("pre-extract %s: %s", stub_id, msg)
    continue
```

**Test class skeleton (same file as AC03):**

```python
class TestManifestOutcomeDistinctness:
    def test_orchestrator_records_tier_rejection_distinctly(self, monkeypatch):
        # Force _validate_tier_boundary to raise; assert manifest payload["reason"].startswith("tier_boundary_rejected:")
        ...
    def test_orchestrator_non_validation_keeps_legacy_prefix(self, monkeypatch):
        # Force _call_llm_json to raise generic Exception; assert payload["reason"].startswith("pre-extract failed:")
        ...

class TestManifestPrefixMutationControl:
    @pytest.mark.xfail(strict=True)
    def test_xfail_when_prefix_demoted(self, monkeypatch): ...
```

### AC05 (PIVOTED) — Single new snapshot subject `_persist_contradictions` (FROZEN)

**Subject:** `src/kb/ingest/pipeline.py:183` (`_persist_contradictions`).

**Files created:**
- `tests/test_cycle73_snapshots.py`
- `tests/__snapshots__/test_cycle73_snapshots.ambr`

**Determinism strategy:**
- Monkeypatch `kb.ingest.pipeline.date` to `FakeDateClass` returning `date(2026, 5, 9)` so `date.today()` is pinned.
- Pin `contradictions` input list to literal entries.
- Pin `page_id` to literal string `"test-contradictions"`.
- Pin `wiki_dir` to `tmp_path` (via existing `tmp_kb_env` fixture).

**Test class skeleton:**

```python
class TestPersistContradictionsSnapshot:
    def test_persist_contradictions_snapshot(self, snapshot, tmp_kb_env, monkeypatch):
        # Pin date.today
        class FakeDate:
            @classmethod
            def today(cls): return date(2026, 5, 9)
        monkeypatch.setattr("kb.ingest.pipeline.date", FakeDate)

        contradictions = [
            {"page_id": "alpha", "claim": "X is true", "source": "raw/a.md"},
            {"page_id": "beta", "claim": "X is false", "source": "raw/b.md"},
        ]
        result = _persist_contradictions(contradictions, page_id="test-contradictions")
        assert result == snapshot
```

**Mutation control:** None — snapshot diff IS the lock-in (per cycle-64 AC8 trust model).

### AC06 (EXTENDED) — BACKLOG hygiene (FROZEN)

**File:** `BACKLOG.md` (TWO line-deletions + line-rewrite).

**Deletion 1 (line ~88):** `KB_DISABLE_VECTORS=1` runtime kill-switch entry — already shipped in cycle 67 AC06.

**Rewrite (lines 79-80):** Replace stale "6 deferred snapshot subjects" list with single-entry "1 deferred snapshot subject: `_persist_contradictions`" — and remove that one entry post-cycle-73-merge.

**Test class skeleton (`tests/test_cycle73_backlog_hygiene.py`):**

```python
class TestBacklogStaleEntries:
    def test_kb_disable_vectors_entry_absent(self):
        backlog_text = Path("BACKLOG.md").read_text(encoding="utf-8")
        assert "KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested)" not in backlog_text

    def test_stale_snapshot_subjects_pruned(self):
        backlog_text = Path("BACKLOG.md").read_text(encoding="utf-8")
        # The 5 already-shipped subjects must NOT be listed as deferred
        for shipped_subject in [
            "_build_summary_content",   # cycle-70 AC06
            "build_graph_jsonld",        # cycle-70 AC08
            "build_llms_full_txt",       # cycle-70 AC07
            "build_extraction_prompt",   # cycle-69 AC13
        ]:
            # Guard against the literal "deferred snapshot subject" framing
            assert f"deferred snapshot subject: {shipped_subject}" not in backlog_text
```

**CHANGELOG entry:**

```
- BACKLOG hygiene: deleted KB_DISABLE_VECTORS=1 entry (already shipped cycle 67 AC06);
  pruned stale "6 deferred snapshot subjects" list — 5 of 6 already shipped in cycles 69-70.
```

---

## 5. Lessons applied to Step 5 (per cycle-72 self-review)

- **L1 (circular-import surface):** AC02 places `CURRENT_PROMPT_VERSION` in `kb.config` (leaf module — verified by R2 DeepSeek). AC03 imports `kb.errors` into `orchestrator.py` (NEW edge — `kb.errors` imports only `pathlib`, acyclic confirmed).
- **L3 (mimocoding-rescue Bash/Read/Grep/Glob only):** Step 9 implementation primary-session; mimocoding-rescue advises only.
- **L4 (sandbox blocks subagent Write):** Step 20 R1/R2 review-file shells pre-created primary-session-side.
- **L7 (count assertions for multi-page fixtures):** AC02 multi-entry fixture asserts COUNT and per-key presence.
- **L8 (cap-math marker reservation):** AC01 reuses cycle-72 `_cap_page_content` which already reserves marker length per cycle-72 R2 Codex M-1 fix.

---

## Verdict (final)

**APPROVE-WITH-CONDITIONS.** 14 conditions enumerated above + 1 AC05 scope pivot. All resolvable at Step 7 (plan) and Step 9 (implement). No back-to-Step-1. No ESCALATE. Proceed to Step 6.
