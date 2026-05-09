# Cycle 73 — STRIDE Threat Model: completeness wrap + verdict prompt-version stamp + tier-boundary verifier

**Date:** 2026-05-09
**Branch:** `feat/cycle-73`
**Pipeline:** dev-mimo-opus (May 2026 trial — fourteenth)
**Scope:** AC01..AC06 in-scope code changes (completeness wrap + verdict prompt-version stamp + tier-boundary verifier + manifest outcome distinctness + 2 syrupy snapshot subjects + BACKLOG hygiene)
**Methodology:** STRIDE per-AC walk; T-class enumeration with mitigation status + grep-test verify-step.
**Predecessor:** cycle 72 threat model (`docs/superpowers/decisions/2026-05-09-cycle-72-threat-model.md`) — T7 (Repudiation) + T8 (EscalationOfPrivilege) deferred citing AC02 + AC03 of cycle 73 as the resolving cycle.

---

## 1. Trust boundaries

The cycle-73 diff crosses four trust boundaries. Each is a layer in the existing architecture; the cycle adds defense-in-depth at the boundary, not a new boundary.

1. **`untrusted-content-on-disk` → `in-memory-string` → `prompt-template-interpolation` → `LLM-call-payload`** (AC01).
   - Source asset: `paired["page_content"]` — a wiki page body previously extracted by an LLM scan-tier from raw URL content + possibly edited by a `refine_page` LLM-write call.
   - Boundary action: `pair_page_with_sources` (file-system read at `WIKI_DIR/`) → `lines.append(paired["page_content"])` → `\n`.join → completeness-check LLM call (Claude Code mode at `mcp/quality.py` callers).
   - Pre-cycle-73 defense at this boundary: NONE on the page side. `_render_sources` budget covered the source side only. (Same pre-cycle-71 gap that cycle-71 AC03 + cycle-72 AC01 closed for `build_fidelity_context`.)
   - Cycle-73 AC01 layers the cycle-72 `_cap_page_content` + `wrap_wiki_context` defense on top. Strictly additive; no defense replaced.

2. **`scan-tier-LLM-output` → `orchestrate-tier-side-effect`** (AC03 + AC04).
   - Source asset: `proposer_mod._call_llm_json(...)` return value — a `dict` constructed from JSON parse of an LLM completion. The LLM is the `MODEL_TIERS["scan"]` model (Haiku, low-reasoning).
   - Boundary action: `orchestrator.py:394-398` returns `extraction` dict → flows into `ingest_source(..., extraction=extraction, ...)` at `orchestrator.py:411` → orchestrate-tier writers (`kb_create_page`-class) consume.
   - Pre-cycle-73 defense: first-pass schema validation INSIDE `_call_llm_json` (the LLM was instructed to return JSON; the schema constrains extraction fields). NO independent re-gate at the orchestrate-tier consumption point. The boundary exists conceptually (per `MODEL_TIERS` doc) but is not enforced in code.
   - Cycle-73 AC03 inserts `_validate_tier_boundary(extraction, expected_keys=...)` between line 398 and line 411. Strictly additive; the existing schema validation still runs.

3. **`verdict-store-on-disk` → `in-memory-list` → `forensic-reader`** (AC02).
   - Source asset: `kb.config.VERDICTS_PATH` JSON file (a `list[dict]`) + the in-process `_VERDICTS_CACHE` dict.
   - Boundary action: `add_verdict` writes a new `dict` entry; `load_verdicts` reads + caches the JSON list; downstream `kb_verdict_trends` / `get_page_verdicts` / forensic CLI readers consume.
   - Pre-cycle-73 defense: per-issue `MAX_ISSUE_DESCRIPTION_LEN` cap (cycle 4 #12), `MAX_NOTES_LEN` cap, `MAX_VERDICTS` retention floor, atomic JSON write, mtime-keyed cache invalidation, page_id traversal/null-byte rejection.
   - Cycle-73 AC02 adds a `prompt_version: int` write-side stamp + read-side `get_prompt_version(entry) -> int` accessor with default `0`. NO cache mutation at read; on-disk fidelity preserved.

4. **`BACKLOG.md` → `developer-tooling-grep` → `cycle-planning-input`** (AC06).
   - Source asset: `BACKLOG.md` text. Forensically open-work signal for cycle planners.
   - Boundary action: planners grep BACKLOG for "cycle-N+1" / "deferred" tokens to seed the next cycle.
   - Pre-cycle-73 defense: manual hygiene (cycle-23 R1 BLOCKER discipline — every "deferred / out of scope" line should be filed against BACKLOG).
   - Cycle-73 AC06 deletes the now-stale `KB_DISABLE_VECTORS=1` entry (already shipped in cycle 67 AC06). Strictly hygiene; no behavior change.

---

## 2. Data classification

| Data flow | Source | Trust class | Cycle-73 AC | New defense |
|---|---|---|---|---|
| `paired["page_content"]` (wiki page body) | `WIKI_DIR/` markdown read via `pair_page_with_sources` | UNTRUSTED (LLM-extracted content; may carry attacker-planted markdown from raw/) | AC01 | `_cap_page_content` + `wrap_wiki_context` at `semantic.py:466` |
| `paired["source_contents"][*]["content"]` (raw source bodies) | `raw/` markdown read via `pair_page_with_sources` | UNTRUSTED (URL-fetched body, may include attacker prose) | AC01 (transitively — `_render_sources(..., budget=...)` plumb) | Budget reservation honors `_FENCE_OVERHEAD` |
| Scan-tier LLM JSON response (`extraction` dict) | `proposer_mod._call_llm_json(tier="scan", schema=...)` | UNTRUSTED (LLM output crossing tier boundary) | AC03 | `_validate_tier_boundary` keys + depth + length + type re-gate |
| Verdict store JSON file (`list[dict]`) | `VERDICTS_PATH` on-disk | TRUSTED (own-process write); FORENSIC-READ scope | AC02 | `prompt_version: int` write-side stamp + `get_prompt_version` read accessor |
| Manifest `payload["reason"]` string | Orchestrator failure-mode write | TRUSTED (own-process write); FORENSIC-READ scope | AC04 | Distinct `tier_boundary_rejected` reason prefix |
| Snapshot fixture inputs (`_render_sources` + `_build_summary_content` outputs) | Test fixture (synthetic) | TRUSTED (test code) | AC05 | `.ambr` snapshot diff lock-in (no defense, test-only) |
| `BACKLOG.md` text | Repo doc | TRUSTED (committed by maintainer) | AC06 | None (doc hygiene only) |

No PII, no credentials, no PHI, no PCI in any cycle-73 data flow. All wiki + verdict data is local, single-user, file-based.

---

## 3. Authentication / authorization

**N/A — confirmed.**

The repository is a single-user, file-based knowledge base running on the maintainer's local machine (Windows/Unix). There is no multi-user model, no auth boundary, no IAM, no session tokens, no RBAC. Local file-system permissions are the only access-control surface, and they are out of scope for cycle 73 (no new file written by the user; all changes are in-process or to the existing on-disk verdict JSON which the maintainer already owns).

The MCP server (`kb.mcp.*`) accepts Claude Code's stdio bridge; Claude Code itself runs as the user. There is no remote attack surface introduced by this cycle.

---

## 4. Logging / audit

Each AC's defense path emits log/audit data; format and persistence below.

| AC | Defense fires | Logger / sink | Format | Persistence |
|---|---|---|---|---|
| AC01 | Page body exceeds `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` | (silent — same as cycle-72 `_cap_page_content`) | Truncation marker `\n…[truncated for context budget]` appended in-band | NONE — marker visible in assembled prompt only |
| AC02 (write-side) | Every `add_verdict` call | `VERDICTS_PATH` JSON file | New entry includes `"prompt_version": CURRENT_PROMPT_VERSION` (=`1`) | PERSISTENT — `atomic_json_write`, retained ≤ `MAX_VERDICTS` |
| AC02 (read-side) | Forensic reader calls `get_prompt_version(entry)` on legacy entry | (silent — pure function) | Returns `0` for missing key (= "pre-cycle-73 unknown") | NONE — caller-driven |
| AC03 | `_validate_tier_boundary` raises `ValidationError` | `logger` (`kb.lint.augment.orchestrator`) via existing `except Exception` block | `f"pre-extract failed: ValidationError: tier-boundary verification failed: <reason>"` | TRANSIENT log line + manifest payload entry |
| AC04 | AC03 raises | Manifest JSONL via `manifest.advance(stub_id, "failed", payload={"reason": "tier_boundary_rejected: <reason>"})` | Distinct `tier_boundary_rejected:` reason-prefix matched by forensic grep | PERSISTENT — manifest JSONL on disk |
| AC05 | N/A — snapshot test only | Test runner stdout | `.ambr` diff in pytest output | NONE (tests don't run in prod) |
| AC06 | N/A — doc-only | NONE | NONE | NONE |

**Forensic grep contract:** `grep -E '"reason": "tier_boundary_rejected:' <manifest.jsonl>` discovers AC04 events distinctly from `llm_scan_failed:` peers.

---

## 5. Threats

T-class enumeration. Each threat: `T<N>: <name> | mitigation status | acceptance criteria | grep-test command`.

### T1 — Tampering: LLM-injected `</wiki_context>` closer in completeness-check page body

- **STRIDE class:** Tampering (alteration of LLM-call semantics).
- **Asset:** Completeness-check LLM verdict integrity (the lint pipeline's gap-detection score).
- **Threat:** A wiki page body containing the literal substring `</wiki_context>` reaches `build_completeness_context`. Pre-cycle-73, `paired["page_content"]` is appended unfenced at `semantic.py:485` (now-target of AC01). With AC01 applied but `_escape_wiki_context_close` bypassed, the attacker-planted closer would terminate the new wrap fence early, freeing subsequent text to be interpreted as instructions.
- **Mitigation status:** IN-SCOPE — AC01.
- **AC reference:** AC01 — wraps `paired["page_content"]` in `wrap_wiki_context(...)` which (a) calls `_escape_wiki_context_close` to rewrite attacker-planted `</wiki_context>` → `</wiki-context>` (hyphen variant cannot match the underscore-fence) (b) emits the `_WIKI_CONTEXT_ASSERTION` system-prompt-style sentence reminding the LLM that fenced content is data not instructions. Sibling defense to cycle-72 AC01 (`build_fidelity_context`).
- **Acceptance criteria:** `tests/test_cycle73_completeness_wrap.py::test_completeness_context_includes_single_fence` asserts assembled output contains exactly one `<wiki_context>` open tag, exactly one `</wiki_context>` close tag, and that an attacker-planted `</wiki_context>` substring inside `paired["page_content"]` is escaped (substring-count of `</wiki_context>` literal == 1, not 2).
- **Grep-test command:**
  ```
  grep -n 'wrap_wiki_context' src/kb/lint/semantic.py
  ```
  Must show ≥3 hits (cycle-71 fidelity AC03 + cycle-72 AC04 consistency + cycle-73 AC01 completeness).

### T2 — InformationDisclosure: oversized completeness page bypasses cap → unbounded prompt → LLM error message leak

- **STRIDE class:** InformationDisclosure (via uncapped tail truncation that strips closing instructions and any sanitized post-fence boundaries; LLM error-cap response may echo verbatim partial prompt).
- **Asset:** Completeness-check pipeline confidentiality + per-call cost predictability.
- **Threat:** Pre-cycle-73, a wiki page body of ~1 MB (e.g., a malformed extraction that included raw HTML) is concatenated unconditionally into the completeness prompt. With AC01's wrap added but cap NOT applied, the wrap stays open at the head but the LLM API hard-cap truncates from the tail — losing the closing fence + the closing instructions ("List any key claims..."). Result: the LLM receives a truncated request, may emit a verbose error message echoing the head of the prompt back (information disclosure of any sensitive prefix; cost unpredictability since token-cap-hit billing applies). Even when the LLM responds normally, the assembled prompt now exceeds `QUERY_CONTEXT_MAX_CHARS`, defeating the budget reservation.
- **Mitigation status:** IN-SCOPE — AC01.
- **AC reference:** AC01 — caps `paired["page_content"]` at `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` characters BEFORE assembly with the marker `\n…[truncated for context budget]`. The wrap's `_FENCE_OVERHEAD` reservation is honored by construction. Cycle-72 AC01 R2 Codex M-1 fix (reserve marker length within `max_chars`) is reused via the same `_cap_page_content` helper.
- **Acceptance criteria:** `tests/test_cycle73_completeness_wrap.py::test_completeness_context_caps_oversized_page_content` — input page of ~`QUERY_CONTEXT_MAX_CHARS * 2` produces output where `len(paired_section) ≤ QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` AND truncation marker is present.
- **Grep-test command:**
  ```
  grep -n '_cap_page_content\|QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD' src/kb/lint/semantic.py
  ```
  Must show ≥2 hits — both `build_fidelity_context` (cycle-72 AC01) and `build_completeness_context` (cycle-73 AC01).

### T3 — Repudiation: verdict-store entry has no prompt-shape stamp → forensic readers cannot reconstruct prompt at time-of-incident

- **STRIDE class:** Repudiation.
- **Asset:** Lint-pipeline forensics — ability to reconstruct what prompt shape an LLM call used at time-of-incident.
- **Threat:** Pre-cycle-73 verdict-store entries record `timestamp / page_id / verdict_type / verdict / issues / notes` but NOT which prompt-shape produced the verdict. An investigator looking at a verdict from before/after the cycle-70/71/72 `wrap_wiki_context` family migration cannot tell whether the LLM was called with the cycle-1 H14 literal-sentinel prompts (`<wiki_page_body>` / `<raw_source_N>` / `<untrusted_source>`) or the cycle-70+ `<wiki_context>` fenced prompts. This is the cycle-72 §T7 deferred forensic gap.
- **Mitigation status:** IN-SCOPE — AC02.
- **AC reference:** AC02 — `kb.config.CURRENT_PROMPT_VERSION = 1` constant (post-cycle-70 fence shape, treating the cycle-71/72/73 expansions as the same family per Q5). `add_verdict` writes `"prompt_version": CURRENT_PROMPT_VERSION` into every new entry. `load_verdicts` adds module-level `get_prompt_version(entry: dict) -> int` accessor with default `0` (= "pre-cycle-73 unknown"). Read-side back-fill is via accessor (NOT cache mutation) per Q1 lean. Strictly additive — read-side back-compat with pre-cycle-73 entries.
- **Acceptance criteria:** (1) `tests/test_cycle73_prompt_version.py::test_add_verdict_stamps_current_prompt_version` — fresh entry has `prompt_version == CURRENT_PROMPT_VERSION`. (2) `test_load_verdicts_legacy_entry_default_zero` — entry without the key reports `get_prompt_version(entry) == 0`. (3) `test_get_prompt_version_handles_non_dict_inputs` — returns `0` on `None`/`list`/`str` defensively.
- **Grep-test command:**
  ```
  grep -n 'CURRENT_PROMPT_VERSION\|get_prompt_version\|prompt_version' src/kb/lint/verdicts.py src/kb/config.py
  ```
  Must show: `CURRENT_PROMPT_VERSION` defined in `config.py`, `prompt_version` written in `add_verdict`, `get_prompt_version` defined in `verdicts.py`.

### T4 — EscalationOfPrivilege: scan-tier JSON propose orchestrate-tier side effects via attacker-controlled extra keys / oversized values

- **STRIDE class:** EscalationOfPrivilege (transitive — scan tier triggers orchestrate-tier side effects).
- **Asset:** Tier separation (`MODEL_TIERS["scan"]` vs `MODEL_TIERS["orchestrate"]`) — the scan tier should never directly trigger orchestrate-tier-only actions. The `kb_create_page`-class downstream calls (via `ingest_source`) are orchestrate-tier-equivalent because they write content to `WIKI_DIR/`.
- **Threat:** Cycle-72 reduced *probability* of successful prompt injection in `_call_llm_json(tier="scan")` via `wrap_wiki_context` but did NOT bound the *blast radius*. A successful injection (or a buggy/hallucinated LLM response) at `orchestrator.py:394-398` can return a JSON dict that includes attacker-chosen extra keys (e.g., `"side_effects": [{"action": "kb_create_page", ...}]`) OR oversized values (a 1 MB title) that flow into `ingest_source(..., extraction=extraction, ...)` at L411. The downstream consumer's existing schema validation accepts the shape; extra keys are silently ignored OR (worse) consumed by future schema evolutions without re-gate. This is the cycle-72 §T8 deferred blast-radius gap.
- **Mitigation status:** IN-SCOPE — AC03 + AC04.
- **AC reference:** AC03 — `_validate_tier_boundary(scan_output, *, expected_keys, max_depth=4, max_string_len=4096)` re-gate inserted between `_call_llm_json` (L394-398) and `ingest_source` (L411). Rejects: (1) non-dict scan_output (2) any key not in `expected_keys` (derived from `schema['properties'].keys()`, NOT from LLM output — defends against T5 spoofing) (3) any string value > `max_string_len` (4) any nested structure deeper than `max_depth` (5) any value not in `str | int | float | bool | None | list | dict` (rejects custom classes if Pydantic is bypassed). On rejection: raises `ValidationError`. AC04 — the existing `except Exception` at L399+ catches the new `ValidationError` and persists `manifest.advance(stub_id, "failed", payload={"reason": "tier_boundary_rejected: <reason>"})` distinctly from `llm_scan_failed`.
- **Acceptance criteria:** (1) `test_validate_tier_boundary_accepts_well_formed`. (2) `test_validate_tier_boundary_rejects_extra_key` (LLM-injected key raises). (3) `test_validate_tier_boundary_rejects_oversize_string` (5000-char value). (4) `test_validate_tier_boundary_rejects_deep_nesting` (6-level dict). (5) `test_orchestrator_pre_extract_calls_validator` (spy confirms call). (6) `test_orchestrator_records_tier_rejection_distinctly` (manifest reason starts with `tier_boundary_rejected:`).
- **Grep-test command:**
  ```
  grep -n '_validate_tier_boundary\|tier_boundary_rejected' src/kb/lint/augment/orchestrator.py
  ```
  Must show: helper definition (≥1 hit), call site at L≈398 (≥1 hit), manifest reason string `tier_boundary_rejected` (≥1 hit).

### T5 — Spoofing: LLM-fabricated `expected_keys` list bypasses re-gate

- **STRIDE class:** Spoofing (LLM impersonates schema authority).
- **Asset:** Tier-boundary re-gate integrity (AC03's `expected_keys` parameter must be authoritative, not LLM-derived).
- **Threat:** A naive AC03 implementation might derive `expected_keys` from the LLM response itself (e.g., `expected_keys = frozenset(scan_output.keys())`). Such a self-validating loop accepts any LLM-emitted shape — equivalent to no re-gate. The threat is *internal* (implementer mistake) more than external (attacker), but the impact is the same: the AC03 defense is hollowed out.
- **Mitigation status:** IN-SCOPE — AC03 (via design constraint on call site).
- **AC reference:** AC03 — caller at `orchestrator.py:398` derives `expected_keys=frozenset(schema['properties'].keys())` from the same `schema` object passed to `_call_llm_json`. The schema is built by `_build_schema_cached("article")` (a fixed local Python definition, not LLM-derived). Per Q2 lean — `expected_keys` is the primary parameter; the helper accepts both `expected_keys=...` and `schema=...` shortcuts but the caller passes the explicit frozenset. The schema's authority is anchored at `kb.ingest.extractors._build_schema_cached`, which is a pure-Python builder.
- **Acceptance criteria:** Step-14 grep verifies the call site passes `frozenset(schema['properties'].keys())` (NOT `frozenset(extraction.keys())` or similar self-deriving form). Test `test_orchestrator_pre_extract_calls_validator` includes a regression assertion: when the LLM emits `extraction = {"foo": 1}` and `schema = {"properties": {"title": ..., "url": ...}}`, AC03 rejects because `"foo"` is not in `schema['properties'].keys()` (NOT because `"foo"` is missing from `extraction.keys()`).
- **Grep-test command:**
  ```
  grep -n 'expected_keys=' src/kb/lint/augment/orchestrator.py
  ```
  Must show the call site sources from `schema['properties'].keys()` (or `schema=schema` shortcut), NOT from LLM-output `.keys()`. Negative-grep:
  ```
  grep -n 'expected_keys=frozenset(extraction.keys())' src/kb/lint/augment/orchestrator.py
  ```
  Must return ZERO hits.

### T6 — DenialOfService: pathological JSON depth in scan-tier output → orchestrator stack overflow

- **STRIDE class:** DenialOfService.
- **Asset:** Augment-pipeline availability.
- **Threat:** A malicious or buggy LLM response returns deeply-nested JSON (e.g., `{"a": {"a": {"a": ... 1000 levels ...}}}`). Downstream processing inside `ingest_source` and the orchestrate-tier persisters may use recursive traversal (e.g., for nested-frontmatter normalization or graph extraction). Python default recursion limit is 1000; a 1000-deep dict + 50 frames of internal traversal triggers `RecursionError`. The orchestrator's `except Exception` catches this BUT the manifest entry just says `pre-extract failed: RecursionError`, and the operator cannot tell whether the LLM itself was buggy or whether they should re-fetch the URL. Worse, in-process state may be partially written before the recursion-error unwinds. Even at lower depths (e.g., 100), the manifest payload size balloons because the LLM-emitted JSON contains 100 levels of dict — multiplying disk-write cost.
- **Mitigation status:** IN-SCOPE — AC03.
- **AC reference:** AC03 — `max_depth=4` parameter rejects any nested structure deeper than 4 levels. Mirrors typical extraction schema depth (top-level keys + list-of-dicts for source_links + nested confidence-per-claim is at most 3 levels). Per Q3 lean — `max_depth=4` is calibrated against `MAX_ISSUE_DESCRIPTION_LEN` peers + observed extraction depth.
- **Acceptance criteria:** `test_validate_tier_boundary_rejects_deep_nesting` — 6-level-deep dict raises `ValidationError("...max_depth=4...")`. Negative-control: 4-level-deep dict passes through unchanged (boundary inclusivity verified).
- **Grep-test command:**
  ```
  grep -n 'max_depth' src/kb/lint/augment/orchestrator.py
  ```
  Must show `max_depth: int = 4` in the helper signature and a depth-tracking traversal loop.

### T7 — Tampering: verdict-store back-fill mutates cached entries → forensic ground-truth loss

- **STRIDE class:** Tampering (corruption of forensic on-disk state).
- **Asset:** Verdict-store on-disk fidelity. Forensic readers must see the entry exactly as `add_verdict` wrote it; any read-time mutation destroys provenance.
- **Threat:** A naive AC02 read-side implementation might back-fill missing `prompt_version` keys *into* `_VERDICTS_CACHE` entries OR worse, into the on-disk JSON. Either path tampers with what was written: a 2026-01 verdict (genuinely pre-cycle-70) gets `prompt_version: 0` injected, and a forensic reader cannot distinguish "key was absent" from "key was zero by design". Worse, if the in-memory cached list is mutated, `load_verdicts` returns the mutated list to subsequent readers, and the next `save_verdicts` (which uses `atomic_json_write` of the cached list) persists the mutation — destroying ground truth.
- **Mitigation status:** IN-SCOPE — AC02 (design-level — accessor not mutation).
- **AC reference:** AC02 — Q1 design choice: read-side back-fill is via `get_prompt_version(entry: dict) -> int` accessor (`return entry.get("prompt_version", 0) if isinstance(entry, dict) else 0`), NOT cache mutation. The cached list returned by `load_verdicts` contains entries with the key absent (matching on-disk state); only the accessor's return value reflects the default. The existing `load_verdicts` shallow-copy (`return list(cached[2])`) is preserved; the entries inside are NOT deep-copied because no mutation is needed. Strictly additive.
- **Acceptance criteria:** `tests/test_cycle73_prompt_version.py::test_load_verdicts_legacy_entry_default_zero` asserts `"prompt_version" not in entry` AND `get_prompt_version(entry) == 0` — i.e., the key is absent on the entry but the accessor returns the default. Mutation-control xfail-strict: monkeypatching `get_prompt_version` to identity (`lambda e: 999`) makes the legacy-entry default test FAIL — proves default-0 is load-bearing AND the accessor is the only path.
- **Grep-test command:**
  ```
  grep -n 'entry\["prompt_version"\] = \|entry.setdefault.*prompt_version' src/kb/lint/verdicts.py
  ```
  Must return ZERO hits — confirms NO read-side mutation. Positive-grep:
  ```
  grep -n 'def get_prompt_version' src/kb/lint/verdicts.py
  ```
  Must return exactly 1 hit.

### T8 — InformationDisclosure: `prompt_version=0` legacy entries leak old prompt-shape fingerprint to forensic readers (ACCEPTED)

- **STRIDE class:** InformationDisclosure.
- **Asset:** Forensic reader's mental-model accuracy.
- **Threat:** Once AC02 ships, a forensic reader sees three entry classes: (a) `prompt_version: 1` entries (post-cycle-73), (b) entries where the key is absent (pre-cycle-73, `get_prompt_version` returns `0`), (c) future `prompt_version: N` entries when the prompt-shape evolves further. Class (b)'s `0` value conflates several distinct historical states: cycle-1 H14 literal sentinels, cycle-70 first wrap, cycle-71 expansion, cycle-72 expansion. A forensic reader who sees `prompt_version=0` cannot reconstruct exactly which prompt was used — they can only narrow to "pre-cycle-73 unknown".
- **Mitigation status:** ACCEPTED — documented, NOT fixed.
- **Rationale:** Back-filling actual prompt shapes for pre-cycle-73 verdicts is OUT OF SCOPE per requirements §"Non-goals" #3: *"NOT auditing pre-cycle-70 verdicts and back-filling actual prompt shapes."* The `0` value semantically means "pre-cycle-73 unknown", which is precisely correct — investigators must use the verdict's `timestamp` field cross-referenced against `CHANGELOG-history.md` cycle-1/cycle-70/cycle-71/cycle-72 anchors to narrow further. This is acceptable because: (1) the gap exists ONLY for verdicts written before this cycle and is fixed-set (no new pre-cycle-73 entries can appear after AC02 ships); (2) the `timestamp` cross-reference path is documented; (3) the alternative (full archaeology of git history per page) would require its own cycle-scale design.
- **Acceptance criteria:** `docs/reference/error-handling.md` (or `docs/reference/architecture.md`) documents the `prompt_version` semantics: `0` = pre-cycle-73 unknown, `1` = post-cycle-70 wrap_wiki_context family. A `# noqa` or comment on `get_prompt_version` records the accepted gap explicitly: `# Cycle 73 AC02 — return 0 for "pre-cycle-73 unknown"; full archaeology OOS per requirements §non-goals #3`.
- **Grep-test command:**
  ```
  grep -rn 'pre-cycle-73 unknown' src/kb/lint/verdicts.py docs/reference/
  ```
  Must return ≥1 hit (the documentation/comment anchor).

### T9 — Repudiation/InformationDisclosure: AC04 manifest reason-prefix not distinct → forensic confusion (sub-threat of T4)

- **STRIDE class:** Repudiation.
- **Asset:** Manifest forensic distinguishability.
- **Threat:** If AC04 reuses the existing `pre-extract failed: <ExceptionClass>: <message>` format for both LLM-call failures (`HTTPStatusError`, `JSONDecodeError`, etc.) AND the new `ValidationError` from AC03, a forensic reader cannot distinguish "LLM API was unreachable" (transient — retry candidate) from "LLM emitted attacker-crafted output rejected by AC03" (security event — escalate). They look identical in the manifest grep.
- **Mitigation status:** IN-SCOPE — AC04.
- **AC reference:** AC04 — the AC03 `ValidationError` re-raise carries the literal prefix `"tier-boundary verification failed: <reason>"`. The orchestrator's `except Exception as e:` block formats `msg = f"pre-extract failed: {type(e).__name__}: {e}"`. For the `ValidationError` path, this produces `"pre-extract failed: ValidationError: tier-boundary verification failed: <reason>"`. The DESIGN CONSTRAINT for AC04 is that the manifest payload reason MUST start with the literal string `tier_boundary_rejected:` (note the underscore — that's the manifest-level outcome enum, distinct from the ValidationError message which uses hyphens). Implementation choice: catch `ValidationError` SEPARATELY from generic `Exception` at L399 and emit `payload={"reason": f"tier_boundary_rejected: {e}"}` directly (cleaner than text-substring matching).
- **Acceptance criteria:** `test_orchestrator_records_tier_rejection_distinctly` — when AC03 raises, manifest entry's `reason` payload starts with the literal string `"tier_boundary_rejected:"`. Mutation-control: monkeypatching the reason-prefix to `"llm_scan_failed:"` makes the test FAIL.
- **Grep-test command:**
  ```
  grep -n 'tier_boundary_rejected' src/kb/lint/augment/orchestrator.py
  ```
  Must return ≥1 hit at the AC04 manifest-write site.

### T10 — Spoofing: snapshot fixture forgery (OUT OF SCOPE)

- **STRIDE class:** Spoofing.
- **Asset:** AC05 snapshot-test integrity.
- **Threat:** A subsequent commit could `pytest --snapshot-update` to silently regenerate `.ambr` files, masking a regression in `_render_sources` or `_build_summary_content`. The snapshot-update mechanism itself is a developer-trusted operation; if a malicious developer commits an updated snapshot alongside a regression, code review must catch it.
- **Mitigation status:** OUT OF SCOPE.
- **Rationale:** Snapshot integrity is enforced by code review + git diff visibility, not by runtime defense. The `.ambr` file is committed alongside the source change, so any unexpected diff in `tests/__snapshots__/test_cycle73_snapshots.ambr` is visible in the PR. This is the same trust model as cycle-64 AC8 snapshots and is consistent across the project. No new defense is appropriate at the cycle-73 scope.
- **No deferred BACKLOG entry needed** — this is the existing accepted trust model for snapshot tests.

### T11 — Tampering: AC06 BACKLOG hygiene introduces stale doc claim (OUT OF SCOPE)

- **STRIDE class:** Tampering.
- **Asset:** BACKLOG.md doc-truth integrity.
- **Threat:** Deleting the `KB_DISABLE_VECTORS=1` entry could leak the misimpression that no `KB_DISABLE_VECTORS` runtime control exists. CLAUDE.md Quick Reference already documents the cycle 67 AC06 ship; the BACKLOG line is purely a stale residual.
- **Mitigation status:** OUT OF SCOPE.
- **Rationale:** AC06's pass-test (`test_kb_disable_vectors_entry_absent`) explicitly asserts the BACKLOG line is absent; CLAUDE.md Quick Reference §"Auto-rebuild + auto-publish" already documents `KB_DISABLE_VECTORS=1` as a shipped feature. No information loss.

---

## 6. Step 14 verification checklist

Concrete grep/Bash/Python checks proving each in-scope T<N> is implemented. Runnable from the repo root.

```
# T1 — completeness wrap_wiki_context fence
grep -n 'wrap_wiki_context' src/kb/lint/semantic.py | wc -l   # expect >=3 (cycle-71 fidelity + cycle-72 consistency + cycle-73 completeness)
grep -n 'def build_completeness_context' src/kb/lint/semantic.py   # must exist
python -c "from kb.lint.semantic import build_completeness_context; print('OK')"

# T1 + T2 — completeness page-content cap
grep -n '_cap_page_content' src/kb/lint/semantic.py | wc -l   # expect >=2 (cycle-72 fidelity call + cycle-73 completeness call)
grep -n 'QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD' src/kb/lint/semantic.py | wc -l   # expect >=2
python -c "from kb.lint.semantic import _cap_page_content, _CAP_TRUNCATION_MARKER; assert _cap_page_content('x'*100, 50).endswith(_CAP_TRUNCATION_MARKER); print('OK')"

# T2 — _render_sources budget plumb in completeness path
grep -n -A 3 'def build_completeness_context' src/kb/lint/semantic.py | grep '_render_sources.*budget='   # expect >=1

# T3 — verdict prompt-version stamp
grep -n 'CURRENT_PROMPT_VERSION' src/kb/config.py   # expect 1 (definition)
grep -n 'CURRENT_PROMPT_VERSION\|prompt_version' src/kb/lint/verdicts.py   # expect >=3 hits (write site + accessor + import)
grep -n 'def get_prompt_version' src/kb/lint/verdicts.py   # expect exactly 1
python -c "from kb.config import CURRENT_PROMPT_VERSION; assert CURRENT_PROMPT_VERSION == 1; print('OK')"
python -c "from kb.lint.verdicts import get_prompt_version; assert get_prompt_version({}) == 0 and get_prompt_version(None) == 0; print('OK')"

# T4 — tier-boundary verifier helper
grep -n 'def _validate_tier_boundary' src/kb/lint/augment/orchestrator.py   # expect 1
grep -n 'max_depth: int = 4' src/kb/lint/augment/orchestrator.py   # expect >=1 (signature)
grep -n 'max_string_len: int = 4096' src/kb/lint/augment/orchestrator.py   # expect >=1

# T4 — tier-boundary verifier call site
grep -n -B 1 -A 5 '_call_llm_json' src/kb/lint/augment/orchestrator.py | grep '_validate_tier_boundary'   # expect >=1
python -c "from kb.lint.augment.orchestrator import _validate_tier_boundary; \
    _validate_tier_boundary({'a': 1}, expected_keys=frozenset({'a'})); \
    e = None; \
    try:\n        _validate_tier_boundary({'a': 1, 'b': 2}, expected_keys=frozenset({'a'}))\n    except Exception as exc:\n        e = exc\n    assert e is not None and 'tier-boundary' in str(e); print('OK')"

# T5 — schema-derived expected_keys (NOT LLM-derived)
grep -n 'expected_keys=frozenset(extraction.keys())' src/kb/lint/augment/orchestrator.py   # MUST return 0 hits
grep -n "expected_keys=" src/kb/lint/augment/orchestrator.py   # at least 1 hit; manually confirm value is from schema

# T6 — depth bound rejection
python -c "from kb.lint.augment.orchestrator import _validate_tier_boundary; \
    deep = {'a': {'a': {'a': {'a': {'a': {'a': 'x'}}}}}}; \
    e = None; \
    try:\n        _validate_tier_boundary(deep, expected_keys=frozenset({'a'}))\n    except Exception as exc:\n        e = exc\n    assert e is not None; print('OK')"

# T7 — no read-side cache mutation
grep -n 'entry\[.prompt_version.\] = \|setdefault.*prompt_version' src/kb/lint/verdicts.py   # MUST return 0 hits

# T9 — distinct manifest outcome string
grep -n 'tier_boundary_rejected' src/kb/lint/augment/orchestrator.py   # expect >=1 (AC04 manifest reason write)

# T8 — accepted gap documented
grep -rn 'pre-cycle-73 unknown\|prompt_version.*0.*unknown' src/kb/lint/verdicts.py docs/reference/   # expect >=1

# AC06 — stale BACKLOG entry deleted
grep -n 'KB_DISABLE_VECTORS=1.*runtime kill-switch.*cycle-N+1' BACKLOG.md   # MUST return 0 hits

# AC05 — snapshot subjects exist
ls tests/test_cycle73_snapshots.py tests/__snapshots__/test_cycle73_snapshots.ambr   # both files must exist
python -m pytest tests/test_cycle73_snapshots.py -v   # must pass

# Cross-AC — full pytest sweep
python -m pytest tests/test_cycle73_completeness_wrap.py tests/test_cycle73_prompt_version.py \
    tests/test_cycle73_tier_boundary.py tests/test_cycle73_snapshots.py tests/test_cycle73_backlog_hygiene.py -v
```

---

## Mitigations matrix

| T-id | STRIDE | Status | AC | Owner module | Verify-step (Step-14 grep) |
|------|--------|--------|----|--------------|----------------------------|
| T1 | Tampering | IN-SCOPE | AC01 | `src/kb/lint/semantic.py:466` (`build_completeness_context`) | `grep -n 'wrap_wiki_context' src/kb/lint/semantic.py` >=3 hits |
| T2 | InformationDisclosure | IN-SCOPE | AC01 | `src/kb/lint/semantic.py:466` (`_cap_page_content` reuse) | `grep -n 'QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD' src/kb/lint/semantic.py` >=2 hits |
| T3 | Repudiation | IN-SCOPE | AC02 | `src/kb/lint/verdicts.py` + `src/kb/config.py` | `grep -n 'CURRENT_PROMPT_VERSION' src/kb/config.py` =1; `grep -n 'def get_prompt_version' src/kb/lint/verdicts.py` =1 |
| T4 | EscalationOfPrivilege | IN-SCOPE | AC03 + AC04 | `src/kb/lint/augment/orchestrator.py` | `grep -n 'def _validate_tier_boundary' src/kb/lint/augment/orchestrator.py` =1 |
| T5 | Spoofing | IN-SCOPE | AC03 (call-site discipline) | `src/kb/lint/augment/orchestrator.py:398` | Negative-grep `expected_keys=frozenset(extraction.keys())` =0 |
| T6 | DenialOfService | IN-SCOPE | AC03 (`max_depth=4`) | `src/kb/lint/augment/orchestrator.py` | `grep -n 'max_depth: int = 4' src/kb/lint/augment/orchestrator.py` >=1 |
| T7 | Tampering | IN-SCOPE | AC02 (accessor not mutation) | `src/kb/lint/verdicts.py` | Negative-grep `entry["prompt_version"] = ` =0 |
| T8 | InformationDisclosure | ACCEPTED — documented | AC02 (semantic note) | `src/kb/lint/verdicts.py` + `docs/reference/` | `grep -rn 'pre-cycle-73 unknown' src/kb/ docs/reference/` >=1 |
| T9 | Repudiation (sub-T4) | IN-SCOPE | AC04 | `src/kb/lint/augment/orchestrator.py` | `grep -n 'tier_boundary_rejected' src/kb/lint/augment/orchestrator.py` >=1 |
| T10 | Spoofing (snapshot forgery) | OUT OF SCOPE | (existing trust model) | (test code) | Code review + git diff |
| T11 | Tampering (BACKLOG hygiene) | OUT OF SCOPE | AC06 (delete only) | `BACKLOG.md` | `grep -n 'KB_DISABLE_VECTORS=1.*cycle-N+1' BACKLOG.md` =0 |

---

## Deferred / out-of-scope

Per cycle-23 R1 BLOCKER (threat-model deferred-promise text is load-bearing): the Step-11 prompt grep BACKLOG.md for every "deferred / out of scope / scope-out" line. The following entries should be filed against `BACKLOG.md` post-cycle-73:

- **T8 (accepted gap, no-fix):** documented inline + in `docs/reference/error-handling.md`. NO BACKLOG entry filed — the gap is bounded (only pre-cycle-73 verdicts) and the work-around (timestamp cross-reference) is in-place. If a future cycle wants full archaeology, the requirements doc should propose it independently.
- **T10 (snapshot fixture forgery):** existing trust model; no BACKLOG entry needed. The cycle-64 AC8 + cycle-73 AC05 snapshots share the same code-review-as-defense posture.
- **`build_consistency_context` cap-math under `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS` rename to `kb.config`:** OUT OF SCOPE — cycle-72 AC04 placed the constant module-locally to avoid the `config → utils.text → utils.__init__ → utils.pages → config` circular import. Cycle-73 does not unblock this (no new edge added). File a BACKLOG entry post-cycle-73 under Phase 4.5 LOW: *"Move `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS` constant from `lint/semantic.py` to `kb.config` once the circular-import refactor is in scope (cycle-N+1 if requested)."*
- **Verdict prompt-version archaeology for pre-cycle-73 entries:** OUT OF SCOPE per requirements §non-goals #3. If cycle-N+1 wants this: walk `git log` per page_id, cross-reference against `CHANGELOG-history.md` cycle anchors, write a one-shot `kb verdict-archaeology` CLI subcommand. Not a recurring need; defer until requested.

All deferred items will be discoverable by Step-11's BACKLOG grep via the literal token `cycle-N+1 if requested`.

---

## Verdict

THREAT-MODEL: APPROVE.

All eight in-scope STRIDE threat classes (T1-T7 + T9) are mitigated by AC01-AC04. Two threats (T8 + T10) are explicitly accepted with documented rationale. AC05 (snapshot subjects) and AC06 (BACKLOG hygiene) are scoped as test-foundation and doc-hygiene respectively — no new threat surface. The cycle-72 deferred T7 (Repudiation) and T8 (EoP) gaps are now closed by AC02 and AC03+AC04 respectively, completing the chain-of-refinement.
