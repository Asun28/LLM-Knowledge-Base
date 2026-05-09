# Cycle 73 — Design Eval R1 (Opus, architecture/contracts/scope)

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**Pipeline:** dev-mimo-opus (Step 4, Round 1 / Opus)
**Reviewer focus:** architecture, contracts, scope, threat-model coverage, same-class peers, test plan adequacy
**Inputs:**
- `2026-05-09-cycle-73-requirements.md` (6 ACs)
- `2026-05-09-cycle-73-threat-model.md` (T1-T11 STRIDE walk)
- `2026-05-09-cycle-73-brainstorm.md` (2-3 approaches per AC)

---

## Pre-score symbol verification (per cycle-15 L1)

Every cited symbol grep-verified against the current branch HEAD before any AC was scored:

| Symbol | Cited file:line | Reality | Status |
|---|---|---|---|
| `def build_completeness_context` | `src/kb/lint/semantic.py:466` | `src/kb/lint/semantic.py:466` | EXISTS |
| `def _cap_page_content` | `src/kb/lint/semantic.py:37` (cycle-72 site) | `src/kb/lint/semantic.py:37` | EXISTS |
| `_CAP_TRUNCATION_MARKER` (used by AC01 marker reservation) | `src/kb/lint/semantic.py:34` | `src/kb/lint/semantic.py:34` | EXISTS |
| `def wrap_wiki_context` | `src/kb/utils/text.py` | `src/kb/utils/text.py:355` | EXISTS |
| `_FENCE_OVERHEAD` (constant) | `src/kb/utils/text.py` | `src/kb/utils/text.py:386` | EXISTS |
| `def _render_sources` (with `*, budget=` kwarg) | `src/kb/lint/semantic.py:70` | `src/kb/lint/semantic.py:70-112` (signature has `*, budget: int \| None = None`) | EXISTS |
| `def add_verdict` | `src/kb/lint/verdicts.py` | `src/kb/lint/verdicts.py:125` | EXISTS |
| `def load_verdicts` | `src/kb/lint/verdicts.py` | `src/kb/lint/verdicts.py:61` | EXISTS |
| `VERDICTS_PATH` constant | `src/kb/config.py` | `src/kb/config.py:302` | EXISTS |
| `MAX_VERDICTS` | `src/kb/config.py:566` | `src/kb/config.py:566` | EXISTS |
| `MAX_NOTES_LEN` | `src/kb/config.py:572` | `src/kb/config.py:572` | EXISTS |
| `MAX_ISSUE_DESCRIPTION_LEN` | `src/kb/lint/verdicts.py:28` | `src/kb/lint/verdicts.py:28` | EXISTS (LOCAL to verdicts.py — NOT in `kb.config`) |
| `QUERY_CONTEXT_MAX_CHARS` | `src/kb/config.py:503` | `src/kb/config.py:503` | EXISTS |
| `_call_llm_json` (orchestrator call site) | `orchestrator.py:394` | `orchestrator.py:394-398` | EXISTS (multi-line call; AC03 wrap target is the result of this expression) |
| `_build_pre_extract_prompt` | `orchestrator.py` | `orchestrator.py:22` (defn) + `:395` (call) | EXISTS |
| `class ValidationError` | `src/kb/errors.py` | `src/kb/errors.py:52` (`KBError` subclass) | EXISTS |
| `_build_summary_content` | (per AC05 snapshot subject) | `src/kb/ingest/pipeline.py:408` (NOT in `compile/compiler.py` as the brainstorm doc claims) | EXISTS — SEMANTIC-MISMATCH on file path: brainstorm Approach A says `_build_summary_content` is in `compile/compiler.py`, but it actually lives in `src/kb/ingest/pipeline.py:408`. Snapshot subject still valid; just the brainstorm comment is wrong. |
| `manifest.advance(stub_id, "failed", payload={"reason": ...})` pattern | `orchestrator.py:402, 422, 362, ...` | confirmed at L362, L402, L422 — all use string-prefix encoding inside `payload["reason"]`, NOT a separate `outcome` field; AC04 must match this convention | EXISTS |
| `_PROPOSER_SCHEMA` / `_RELEVANCE_SCHEMA` (proposer-side scan-tier callers) | `src/kb/lint/augment/proposer.py:91, 168` | `proposer.py:91, 168` | EXISTS — SAME-CLASS PEERS to orchestrator.py:394 (see Analysis under AC03) |

Summary: every load-bearing symbol exists and is at or near the cited line. **One SEMANTIC-MISMATCH** — `_build_summary_content` lives in `kb.ingest.pipeline` not `kb.compile.compiler`; cosmetic, doesn't change AC05 viability. **One UNSTATED-ASSUMPTION** — manifest entries use `payload["reason"]` string-prefix encoding; no separate `outcome` enum field exists; AC04 must encode `tier_boundary_rejected` as a `payload["reason"]` prefix per existing convention (which the threat-model § T9 correctly anticipates but requirements §AC04 conflates with "outcome" terminology — see CONDITION-AC04-1).

---

## Analysis and scoring

### AC01 — `build_completeness_context` cap + wrap_wiki_context fence

#### Analysis

The recommended Approach A (mirror cycle-72 AC01 in `build_fidelity_context`) is the right shape. The threat model maps T1 (Tampering — attacker-planted `</wiki_context>` closer in `paired["page_content"]`) onto `wrap_wiki_context`, and T2 (InformationDisclosure via uncapped tail truncation) onto `_cap_page_content` + `_render_sources(budget=…)`. Both helpers already exist (verified above) and already encode the cycle-72 R2 Codex M-1 cap-math invariant (the `text[: max_chars - len(_CAP_TRUNCATION_MARKER)] + marker` form at semantic.py:54). The cycle-72 AC01 docstring on `_cap_page_content` (lines 37-51) ALREADY anticipates AC01 with the explicit comment "`build_completeness_context` is deferred to cycle-73+ per threat-model §T1". Reusing the helper inherits the L8 (cap-math marker reservation) lesson without re-deriving it.

The same-class peer enumeration (cycle-16 L1) flags two related sites: (a) `build_fidelity_context` (cycle-72 AC01 — already shipped), (b) `build_consistency_context` (cycle-72 AC04 — already shipped, per-page wrap with `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS`), and (c) `build_completeness_context` (this AC). Together they form the complete trio. The current `build_completeness_context` body at semantic.py:474-496 is structurally identical to the pre-cycle-72 `build_fidelity_context` body (same `lines = [header, "## Wiki Page", paired["page_content"], "---", _render_sources(...)]` shape), so the diff IS a near-direct paste of the cycle-72 AC01 split-into-(header, body, closing)-triplet pattern shown at lines 137-177. The brainstorm doc Approach C (no helper, inline) is rightly rejected — the duplicated `_cap_page_content + wrap_wiki_context` pattern is well-isolated to two call sites and a future cycle-74 `_assemble_wrapped_context` helper would be premature now. Approach B (helper extraction NOW) carries the cycle-72 AC01 site as collateral refactor blast radius — not Tier-2 appropriate.

The test plan (`test_completeness_context_includes_single_fence` + xfail-strict mutation control) is behavioural (asserts the assembled string contains exactly one open + close + escapes a planted closer to the hyphen variant). This satisfies cycle-11 L1 / `feedback_test_behavior_over_signature` because the assertion exercises `wrap_wiki_context` end-to-end on real input, NOT `inspect.getsource` on the function body. The mutation control (identity-monkeypatching `_cap_page_content` OR `wrap_wiki_context` causes the lock-in test to FAIL) proves both invariants are load-bearing — this is exactly the post-cycle-69 `inspect-source-tests-are-signature-only` lesson.

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC01 | A — mirror cycle-72 AC01 split-into-(header, body, closing)-triplet pattern; reuse `_cap_page_content` + `wrap_wiki_context`; pass `budget=QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` to `_render_sources` | **5** (ship-as-is) | None |

---

### AC02 — Verdict-store prompt-shape version stamp

#### Analysis

The recommended Approach A (accessor-not-mutation) correctly targets threat-model T7 (Tampering — read-side back-fill mutation destroys forensic ground truth). The trust-boundary description is precise: `_VERDICTS_CACHE` returns a SHALLOW COPY of the cached list (`return list(cached[2])` at verdicts.py:108), but the entries inside are NOT deep-copied. Approach B (mutation) would corrupt the cache through these shared dict references AND the next `save_verdicts` would write the back-fill back to disk — write-amplification + ground-truth loss. Approach C (one-shot migration) carries the `feedback_migration_breaks_negatives` lesson (one-shot load-time migrations break `K not in D` tests). Approach A is the only path that preserves the threat-model T7 invariant.

Same-class peer scan (cycle-16 L1): `kb.lint.feedback_store` is the same-class peer (also a JSON list-of-dicts persisted via `atomic_json_write`). Cycle-73 doesn't add `prompt_version` there, but the `prompt_version` semantics are specific to LLM-verdict provenance (which `feedback_store` does record but at a different forensic granularity — query-feedback events not lint-verdicts). I'd accept skipping `feedback_store` from this cycle — but flag CONDITION-AC02-1: the requirements doc should acknowledge `feedback_store` is intentionally excluded so the cycle-73 forensics scope is bounded.

Architectural concerns: cycle-19 L1 monkeypatch enumeration — the test plan #2 (`test_load_verdicts_legacy_entry_default_zero`) needs to construct a fixture verdict-file WITHOUT the `prompt_version` key. The cleanest path is to (a) write a list-of-dicts to a tmp `VERDICTS_PATH` directly via `atomic_json_write` bypassing `add_verdict`, then (b) call `load_verdicts(path)` and assert `"prompt_version" not in entry` AND `get_prompt_version(entry) == 0`. This is behavioural (exercises the read path), not signature-only. Test #3 (`test_get_prompt_version_handles_non_dict_inputs`) is also behavioural (asserts `get_prompt_version(None) == 0` etc.). Both pass the cycle-11 L1 / `feedback_test_behavior_over_signature` test. The mutation controls (xfail-strict — monkeypatching `CURRENT_PROMPT_VERSION` to 0 OR `get_prompt_version` to identity-999) exercise production code paths.

Q5 (prompt_version=1 vs 2): the requirements doc lean is `1` (= "post-cycle-70 wrap_wiki_context family, treating cycle-71/72/73 expansions as same family"). I AGREE. Bumping to N=2 per cycle is a slippery slope toward a pseudo-git-rev tag, which is what the on-disk `timestamp` already provides. The forensic semantics "did this verdict come from the wrap_wiki_context family or the cycle-1 H14 literal-sentinel family?" is binary; that's what `prompt_version` should encode. Future structural prompt revisions (e.g., a hypothetical cycle-80 "wrap_wiki_context_v2 with ##-sub-headers") can bump to 2.

Q1 (mutability semantics): accessor wins per T7 analysis above. The requirements doc lean is correct.

UNSTATED-ASSUMPTION-AC02-1: the `kb.lint.augment.persister` (which writes verdicts via `add_verdict` directly OR indirectly through `kb_save_lint_verdict`) is the OWNER MODULE for the write path. The requirements correctly target `add_verdict` — but if any production code path bypasses `add_verdict` and constructs the verdict dict by hand + calls `save_verdicts`, that path will not get the stamp. CONDITION-AC02-2: Step-9 should grep for `save_verdicts(verdicts` call sites; any direct-construction site needs the stamp added (or routed through `add_verdict`). I see no direct construction site in the orchestrator (it imports `add_verdict` at L373) but a Step-9 caller-grep checkpoint per `feedback_signature_drift_verify` is warranted.

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC02 | A — accessor `get_prompt_version` returns `entry.get("prompt_version", 0) if isinstance(entry, dict) else 0`; write-side `add_verdict` adds key; NO cache mutation; NO migration; `CURRENT_PROMPT_VERSION = 1` in `kb.config` | **5** (ship-as-is) | CONDITION-AC02-2: Step-9 caller-grep for direct `save_verdicts(verdicts...` callers that bypass `add_verdict` and would not get the stamp. |

---

### AC03 — Tier-boundary verifier helper `_validate_tier_boundary`

#### Analysis

The recommended Approach A (explicit `expected_keys` param, `max_depth=4`, `max_string_len=4096`) is the correct shape and addresses T4 (EscalationOfPrivilege), T5 (Spoofing — LLM-fabricated `expected_keys`), and T6 (DenialOfService — pathological depth). Approach B (helper accepts `schema` directly) leaks JSONSchema internals (`$ref`, allOf/oneOf, etc.) into the helper — bad encapsulation. Approach C (pluggable validator interface) is over-engineering for one call site; cycle-72 R1 Sonnet design eval would reject on simplify discipline.

The threat-model T5 analysis is sharp: a naive `expected_keys=frozenset(scan_output.keys())` self-validating loop hollows out the defense. The proposed call-site discipline (`expected_keys=frozenset(schema['properties'].keys())`) anchors `expected_keys` against the local Python schema builder `_build_schema_cached("article")` (verified at extractors.py:266). `_build_schema_cached` is a pure-Python builder — no LLM input flows into the schema construction. T5 is correctly mitigated.

**SAME-CLASS PEER GAP — major architectural concern.** The grep table flagged TWO additional scan-tier `_call_llm_json` call sites I want the requirements + threat model to acknowledge:
- `src/kb/lint/augment/proposer.py:91` — `_call_llm_json(prompt, tier="scan", schema=_PROPOSER_SCHEMA)` (proposer-side claim/issue extraction)
- `src/kb/lint/augment/proposer.py:168` — `_call_llm_json(prompt, tier="scan", schema=_RELEVANCE_SCHEMA)` (proposer-side relevance scoring)

Both produce dicts that flow into orchestrator-tier consumers (the relevance score gates whether augment runs at all; the proposer JSON drives `kb_save_lint_verdict` writes). Per cycle-16 L1 same-class peer rule, AC03 should justify why these two peers are out of scope, OR include them. Reading the requirements doc, AC03's scope is narrowly framed at `orchestrator.py:394` — but the threat-model T4 talks generally about "scan-tier-LLM-output → orchestrate-tier-side-effect" which would catch all three sites. **CONDITION-AC03-1: Step 5 must explicitly decide:**
- (a) Cycle-73 scope is the L394 site only; file BACKLOG entries for `proposer.py:91` and `:168` peers as cycle-74+ Phase 4.5 LOW deferred (requires `cycle-N+1 if requested` token), OR
- (b) Expand AC03 to wrap all three call sites this cycle (test count rises ~5 → ~9; helper unchanged; only call-site count grows).

I lean (a) for blast-radius/Tier-2 reasons, but the requirements doc must state this explicitly so cycle-74 planners discover the deferred peers via Step-11 BACKLOG grep.

Q2 (`expected_keys` vs `schema=` shortcut): I lean **Q2-A explicit `expected_keys` only** (not "both" as the requirements lean suggests). Two-keyword surfaces multiply test variants and confuse callers; if cycle-74+ sees 3+ call sites, a thin `_expected_keys_from_schema(schema)` helper is a one-liner refactor. KISS. CONDITION-AC03-2: Step 5 picks one (Q2-A explicit-only OR Q2-B both-accepted); brainstorm Approach A says "explicit"; threat-model §T5 also assumes "explicit". No conflict — this is just a lean-confirmation.

Q3 (`max_depth=4`, `max_string_len=4096`): I AGREE. Real-world extraction schemas top out at depth 3 (root → field → list-of-dicts → leaf-dict), so 4 has 1 level of slack. The brainstorm Option (i) is correct. `max_string_len=4096` mirrors `MAX_ISSUE_DESCRIPTION_LEN` from verdicts.py:28 (4000 — close enough; the 96-char gap absorbs minor formatting).

Architectural concerns (cycle-19 L1 / cycle-72 L1 circular-import): adding `_validate_tier_boundary` as module-level helper in `orchestrator.py` introduces NO new import edge — `ValidationError` is already imported transitively via `kb.errors` (`KBError` subclass; `kb.lint.augment.orchestrator` does not currently import `kb.errors`, so AC03 will add `from kb.errors import ValidationError` — a NEW edge to verify is acyclic). Quick check: `kb.errors` imports only `pathlib` (verified) — no cycle risk. Confirmed safe.

UNSTATED-ASSUMPTION-AC03-1: **the `extraction` dict at orchestrator.py:408 is consumed by `manifest.advance(stub_id, "extracted", payload={"keys": list(extraction.keys())})`. If AC03 raises BEFORE this manifest write, fine — but AC03's catch-block ordering matters for the manifest forensic trail.** If `_validate_tier_boundary` is called AFTER L394-398 but BEFORE L408, the L408 `manifest.advance("extracted", ...)` is bypassed and the forensic trail goes from `proposed` → `failed` (skipping `extracted`). This is the intended behavior (the LLM output never reached extraction-acceptable state) — but the requirements doc + threat-model don't explicitly call this out. CONDITION-AC03-3: Step 5 confirms the ordering: `_validate_tier_boundary` between L398 and L408; the L408 `extracted`-state manifest entry is REPLACED by AC04's `failed`-state with `tier_boundary_rejected:` reason.

The test plan is mostly behavioural — `test_validate_tier_boundary_accepts_well_formed`, `_rejects_extra_key`, `_rejects_oversize_string`, `_rejects_deep_nesting` all exercise the helper end-to-end. `test_orchestrator_pre_extract_calls_validator` is a spy/integration test — must verify it asserts on a side effect (e.g., spy counter, manifest payload) NOT `inspect.getsource(orchestrator)` containing the literal `_validate_tier_boundary` token. CONDITION-AC03-4: confirm this test exercises the production code path; if implemented as `assert "_validate_tier_boundary" in inspect.getsource(...)` it would pass even after revert per `feedback_inspect_source_tests`.

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC03 | A — module-level helper in `orchestrator.py`; explicit `expected_keys` (no `schema=` shortcut); `max_depth=4`, `max_string_len=4096`; raise `ValidationError("tier-boundary verification failed: <reason>")` | **4** (ship-with-conditions) | CONDITION-AC03-1 (same-class peers `proposer.py:91, 168`); CONDITION-AC03-2 (Q2 single-param); CONDITION-AC03-3 (manifest-write ordering); CONDITION-AC03-4 (spy test must be behavioural). |

---

### AC04 — Manifest outcome distinctness `tier_boundary_rejected`

#### Analysis

The brainstorm doc lists three approaches: (A) outcome enum string, (B) sub-key on existing reason, (C) distinct exception class `TierBoundaryError`. The brainstorm recommends **C** (distinct exception class + outcome string). The requirements lean is "**A** — new enum value `tier_boundary_rejected`". The threat model §T9 explicitly states the *implementation choice*: "catch `ValidationError` SEPARATELY from generic `Exception` at L399 and emit `payload={'reason': f'tier_boundary_rejected: {e}'}` directly".

So we have **inconsistency between the three docs** on AC04:
- Brainstorm: Approach C (TierBoundaryError subclass).
- Requirements: Approach A (outcome string only; no new exception class).
- Threat model: Approach A (catch `ValidationError` directly; no new class).

I AGREE with requirements + threat-model (Approach A), against the brainstorm. Reasons:

1. **Manifest payload schema**: every existing `manifest.advance(stub_id, "failed", payload={"reason": "..."})` call site at L362, L402, L422 uses string-prefix encoding inside `payload["reason"]`, NOT a top-level `outcome` field. The state name (`"failed"`, `"abstained"`, etc.) is the second positional arg. So the "new outcome enum value" framing in requirements §AC04 is partially miscommunicated — it should be "new `payload['reason']` prefix `tier_boundary_rejected:`", which IS what the threat-model §T9 specifies. **CONDITION-AC04-1: Step 5 should clarify the encoding terminology — the `manifest.advance(stub_id, "failed", payload={"reason": "tier_boundary_rejected: <reason>"})` form is the actual implementation, not a separate enum field.**

2. **Approach C (TierBoundaryError subclass) is over-engineered**: the catch block already runs as `except Exception as e: msg = f"pre-extract failed: {type(e).__name__}: {e}"`. Splitting into `except ValidationError as e: ... except Exception as e: ...` requires two branches but no new exception class; the `type(e).__name__` is already `"ValidationError"`. A `TierBoundaryError(ValidationError)` adds an import + class definition + propagation surface for marginal benefit. KISS. The brainstorm Approach C is wrong on Tier-2 simplify-discipline.

3. **String-prefix encoding** is the existing project convention (cycle-23 R1 BLOCKER lesson + the `blocked_by_allowlist:` prefix at L261 + `rate limited (retry Xs)` at L278). AC04 should follow precedent.

The Q7 lean ("NEW enum value `tier_boundary_rejected` for forensic distinctness; same audit-row schema otherwise") IS the right answer — but the words "enum value" are misleading; it's a `payload["reason"]` prefix. Treat Q7 as resolved with this clarification.

Test plan: `test_orchestrator_records_tier_rejection_distinctly` — when AC03 raises, manifest entry's `reason` payload starts with the literal `"tier_boundary_rejected:"`. Behavioural; the mutation control (xfail-strict — flipping the prefix to `llm_scan_failed:` makes the test FAIL) exercises the production catch block. cycle-11 L1 / behavioural-test compliance verified.

UNSTATED-ASSUMPTION-AC04-1: **the existing `except Exception as e:` at orchestrator.py:399 will catch `ValidationError` because `ValidationError(KBError(Exception))`**. If AC04 wants the prefix to be `tier_boundary_rejected:` ONLY for `ValidationError` (and stay `pre-extract failed: <ExceptionClass>: <msg>` for other exceptions), the catch block must split into `except ValidationError as e: ... except Exception as e: ...`. The threat-model §T9 specifies this explicitly; the requirements §AC04 is silent. CONDITION-AC04-2: Step 5 mandates the split-catch form so non-`ValidationError` exceptions still get the cycle-72-equivalent `pre-extract failed: ...` reason (preserves back-compat with existing forensic grep that doesn't yet know about `tier_boundary_rejected:`).

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC04 | A — split `except ValidationError as e: payload["reason"]=f"tier_boundary_rejected: {e}"` from `except Exception as e: payload["reason"]=f"pre-extract failed: {type(e).__name__}: {e}"`; NO new exception class | **4** (ship-with-conditions) | CONDITION-AC04-1 (terminology clarification — string-prefix not enum); CONDITION-AC04-2 (split-catch form mandated). |

---

### AC05 — Two new syrupy snapshot subjects

#### Analysis

The recommended Approach A (`_render_sources` + `_build_summary_content`) is fine. Symbol verification confirmed `_build_summary_content` lives at `src/kb/ingest/pipeline.py:408` (NOT `compile/compiler.py` as the brainstorm doc says — minor cosmetic mismatch). The two subjects are well-chosen: `_render_sources` is plumbed via AC01 (regression bait — any AC01 implementation bug surfaces immediately in the snapshot diff); `_build_summary_content` is untouched by cycle-73 (regression-fence integrity check — proves snapshots catch invariants outside the diff scope).

Determinism concern: `_render_sources` reads from `paired["source_contents"]` which contains real source bodies. The snapshot fixture must use synthetic content (a multi-source list with deterministic strings) AND the budget parameter must be pinned to a literal value (NOT a `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` reference that may shift as `_WIKI_CONTEXT_ASSERTION` evolves). CONDITION-AC05-1: snapshot fixtures pin `budget=` and the source bodies to literal values; no env-var or config-derived numbers in the snapshot.

`_build_summary_content` takes `(extraction: dict, source_type: str)`. The fixture should construct a synthetic `extraction` dict with `title`, `authors` (list), `core_argument`, `key_claims` (list), `entities_mentioned`, `concepts_mentioned` — all the branches at lines 410-481. The wikilink rendering (`[[entities/{slug}|{safe_name}]]`) is deterministic given a fixed `slugify` + sentinel filter; same for `wikilink_display_escape`. No timestamps, no SHAs, no UUIDs — fully deterministic.

UNSTATED-ASSUMPTION-AC05-1: `slugify` and `wikilink_display_escape` are pure functions; `_is_untitled_sentinel` uses an exact 6-hex sentinel pattern. If any of these helpers change in cycle-74+, the AC05 snapshots will need regeneration — which is exactly the point (snapshot acts as a regression fence). No issue; just naming the contract.

Q4 lean (`_render_sources` + `_build_summary_content`): I AGREE. The graph JSON-LD subject is brittle (timestamps), per the brainstorm Approach B con. Stick with the two-subject pair.

The test design (no mutation control needed — "snapshot-based regression IS the lock-in") is correct per the existing cycle-64 AC8 trust model. T10 (snapshot fixture forgery) is correctly classed OUT-OF-SCOPE per existing project posture.

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC05 | A — `_render_sources` + `_build_summary_content` snapshots in `tests/test_cycle73_snapshots.py` + `tests/__snapshots__/test_cycle73_snapshots.ambr` | **4** (ship-with-conditions) | CONDITION-AC05-1 (snapshot fixtures pin literal budget + literal source bodies — no env/config derivations). Cosmetic note: brainstorm Approach A says `_build_summary_content` is in `compile/compiler.py`; actually `kb.ingest.pipeline:408` (immaterial; subject is the same). |

---

### AC06 — BACKLOG hygiene: delete stale `KB_DISABLE_VECTORS` entry

#### Analysis

Trivial doc-only change. Verified the stale BACKLOG.md entry exists at `BACKLOG.md:88` ("`kb.query.hybrid` `KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested) — …"). Verified CLAUDE.md Quick Reference §"Auto-rebuild + auto-publish" already documents `KB_DISABLE_VECTORS=1` as cycle 67 AC06 shipped. Approach A (delete only the stale entry) is the right surgical scope. Approach B (full BACKLOG audit) is its own cycle. Approach C (defer) leaves a known-stale entry visible.

The pass test (`test_kb_disable_vectors_entry_absent` — `BACKLOG.md` does NOT contain the literal string `"KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested)"`) is grep-style behavioural. Mutation control: the test FAILS if the entry is re-added — a structural cycle-23 R1 BLOCKER discipline guard.

Same-class peer scan: the brainstorm doc rightly notes "another full sweep this cycle is over-budget". I AGREE — but flag CONDITION-AC06-1: the cycle-73 self-review (Step 24) should add a one-line lesson capturing "BACKLOG audit-pass should run every Nth cycle as a separate cycle, not bundled into feature cycles". This stays out of cycle-73 scope but seeds cycle-74+ planning.

UNSTATED-ASSUMPTION-AC06-1: the test asserts the EXACT literal string. If the BACKLOG entry is reformatted (e.g., Markdown bullet style) before deletion, the test would still pass on the deletion. CONDITION-AC06-2: ensure the assertion is precise (literal substring) AND the deletion is the explicit BACKLOG line (not just a reformat). The Step-11 BACKLOG-grep checkpoint per cycle-23 R1 catches this.

| AC | Approach (recommended) | Score (1-5) | Open questions |
|---|---|---|---|
| AC06 | A — delete only the explicitly-known-stale `KB_DISABLE_VECTORS=1 runtime kill-switch (cycle-N+1 if requested)` line at BACKLOG.md:88; one-line CHANGELOG entry | **5** (ship-as-is) | CONDITION-AC06-2 (literal-substring assertion + explicit line deletion, not reformat). |

---

## Summary scoring table

| AC | Recommended approach | Score | Conditions count |
|---|---|---|---|
| AC01 | A — mirror cycle-72 AC01 split-into-(header, body, closing) | **5** | 0 |
| AC02 | A — accessor `get_prompt_version`, no mutation, `CURRENT_PROMPT_VERSION=1` | **5** | 1 (Step-9 caller-grep) |
| AC03 | A — explicit `expected_keys`, `max_depth=4`, `max_string_len=4096` | **4** | 4 (peers / Q2 / ordering / spy-test) |
| AC04 | A — `payload["reason"]=f"tier_boundary_rejected: {e}"`, split-catch, no new exception class | **4** | 2 (terminology / split-catch) |
| AC05 | A — two snapshot subjects, deterministic fixtures | **4** | 1 (literal-pin) |
| AC06 | A — delete stale BACKLOG entry, one-line CHANGELOG | **5** | 1 (literal-substring assertion) |

**Aggregate:** 4.5/5 weighted. No AC scored ≤3. No BLOCKERs. 9 conditions enumerated for Step 5 resolution.

---

## Open question resolution (per requirements §"Open questions for Step 4 design eval")

- **Q1 — `prompt_version` mutability semantics.** RESOLVED → accessor (per T7 analysis; mutation tampers with on-disk fidelity).
- **Q2 — `_validate_tier_boundary` schema-derivation strategy.** RESOLVED → explicit `expected_keys` only (single param; KISS; T5 defense visible at call site). Reject the "both" lean; if a future cycle has 3+ call sites, a `_expected_keys_from_schema(schema)` one-liner refactor is trivial.
- **Q3 — `max_depth=4`, `max_string_len=4096` defaults.** RESOLVED → 4 / 4096 (matches existing schema depth + `MAX_ISSUE_DESCRIPTION_LEN` peer).
- **Q4 — Snapshot subjects pair selection.** RESOLVED → `_render_sources` + `_build_summary_content` (regression-bait + regression-fence pair).
- **Q5 — `prompt_version` value (1 vs 2).** RESOLVED → `1` (post-cycle-70 wrap_wiki_context family is the same family; cycle-71/72/73 expansions all stamp 1).
- **Q6 — Cycle-72 L8 cap-math invariant in completeness path.** RESOLVED → yes, reusing `_cap_page_content` inherits the cycle-72 R2 Codex M-1 fix at semantic.py:54.
- **Q7 — AC04 outcome-string vs sub-key vs exception-class distinction.** RESOLVED → string-prefix on `payload["reason"]` (NOT outcome enum, NOT new exception class). Terminology in requirements §AC04 ("new outcome enum value") is misleading; the actual encoding is a `payload["reason"]` prefix. See CONDITION-AC04-1.

---

## CONDITIONS for Step 5 decision gate

Numbered for Step-5 traceability. Each MUST be resolved before Step 6/9 implementation begins.

1. **CONDITION-AC02-2** — Step-9 caller-grep checkpoint: `grep -rn "save_verdicts(verdicts" src/` to find any direct callers that bypass `add_verdict`. If found, route through `add_verdict` OR add explicit `prompt_version` injection. (Per `feedback_signature_drift_verify`.)

2. **CONDITION-AC03-1** — same-class peer disposition: cycle-73 scope is `orchestrator.py:394` only? File BACKLOG entries for `proposer.py:91` (`_PROPOSER_SCHEMA`) and `proposer.py:168` (`_RELEVANCE_SCHEMA`) as cycle-74+ Phase 4.5 LOW deferred items with the literal token `cycle-N+1 if requested`. Per cycle-16 L1, deferred peers must be discoverable.

3. **CONDITION-AC03-2** — Q2 single-param: `_validate_tier_boundary` accepts ONLY `expected_keys=...`, NOT a `schema=` shortcut. Brainstorm Approach A confirmed.

4. **CONDITION-AC03-3** — manifest-write ordering: `_validate_tier_boundary` is invoked between orchestrator.py:398 (LLM call return) and L408 (extracted-state manifest entry). On rejection, the L408 entry is bypassed; AC04 emits `failed`-state with `tier_boundary_rejected:` reason instead.

5. **CONDITION-AC03-4** — `test_orchestrator_pre_extract_calls_validator` MUST assert a side effect (spy counter, manifest payload, or behavioural state change), NOT `inspect.getsource(orchestrator) contains "_validate_tier_boundary"`. Per cycle-11 L1 + `feedback_inspect_source_tests`.

6. **CONDITION-AC04-1** — terminology clarification: requirements §AC04 says "new outcome enum value `tier_boundary_rejected`"; actual implementation is `payload["reason"]=f"tier_boundary_rejected: {e}"` string-prefix per existing `manifest.advance(...)` convention at L362, L402, L422. No top-level enum field exists.

7. **CONDITION-AC04-2** — split-catch form: `except ValidationError as e: ... except Exception as e: ...` at orchestrator.py:399. `ValidationError` path emits `tier_boundary_rejected:` prefix; generic-`Exception` path keeps `pre-extract failed: <ExceptionClass>: <msg>` for back-compat with existing forensic grep.

8. **CONDITION-AC05-1** — snapshot fixtures pin `budget=<literal>` and source body strings to LITERAL values; no env-var / config-derived numbers in `.ambr` content (those would invalidate the snapshot on `QUERY_CONTEXT_MAX_CHARS` config-tweaks).

9. **CONDITION-AC06-2** — `test_kb_disable_vectors_entry_absent` asserts the EXACT literal substring; deletion is the explicit BACKLOG.md line, not a reformat. Step-11 BACKLOG-grep checkpoint catches drift.

10. **(Non-blocking) UNSTATED-ASSUMPTION-AC02-1** — `kb.lint.feedback_store` is intentionally OUT-OF-SCOPE for `prompt_version` stamping (different forensic granularity). Step-12 docs (`docs/reference/error-handling.md`) should briefly note this so cycle-74 planners don't re-discover the gap.

---

## Verdict

**APPROVE-WITH-CONDITIONS.**

All 6 ACs are architecturally sound and align with the threat-model T1-T9 mitigations. No BLOCKERs. The 9 enumerated CONDITIONs are non-architectural (call-site disposition, terminology, ordering, test-shape, fixture literality) — Step 5 should resolve them via short doc-edit + Step-9 implementer notes. Two ACs (AC01, AC02, AC06) are ship-as-is at score 5; three ACs (AC03, AC04, AC05) need the conditions above before Step 9 implementation. The cycle-72 chain-of-refinement (T7 Repudiation, T8 EoP) is correctly closed by AC02 and AC03+AC04 respectively. The cycle-73 self-review (Step 24) should fold CONDITION-AC03-1's same-class-peer enumeration into cycle-74+ planning.

No back-to-step-1 reasons. No score below 4. Proceed to Step 5 (decision gate) with the 9 conditions for resolution.
