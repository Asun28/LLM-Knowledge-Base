# Cycle 70 — Threat Model + dep-CVE Baseline

**Date:** 2026-05-08
**Tier:** 2
**Step:** 02

## STRIDE walk-through

Each new attack surface touched by cycle 70 ACs is enumerated. ACs that do not introduce surface (verify-and-delete, doc artifacts) are noted but not modelled.

### AC11 — Wiki-context boundary fence (`<wiki_context>` tags + system-prompt assertion)

| ID | Threat | STRIDE | Mitigation | Residual |
|----|--------|--------|------------|----------|
| T1 | Prompt-injection from ingested raw/ content reaches synthesis LLM as instructions | Tampering | Fence with `<wiki_context>...</wiki_context>` + system-prompt assertion telling the LLM the inside is data, not instructions | Defense-in-depth only; LLM compliance is best-effort. Layered with `ingest/extractors.py:326` untrusted-tag (defense at ingest). |
| T2 | Boundary helper bypassed by future code path that constructs synthesis prompt without going through `wrap_wiki_context()` | Tampering | AC12 lock-in test asserts both call sites use the helper; cycle-70 self-review BACKLOG candidate adds a Phase 4.5 LOW "AST guard test for direct synthesis-prompt context concat" forward-looking item | Future cycle adds AST guard if drift observed. |
| T3 | Attacker crafts content with literal `</wiki_context>` substring inside a wiki page to escape the fence prematurely | Tampering | Helper rejects/escapes literal closing-tag substrings before fencing (e.g., replace `</wiki_context>` in content with a sentinel that the LLM cannot mistake for fence-end). Lock-in test covers this case. | Best-effort string sanitization; no parse-level guarantee. |
| T4 | Empty wiki-context still emits orphan `<wiki_context></wiki_context>` tags, confusing downstream LLM | Information Disclosure (low) | Helper short-circuits when wiki text is empty (returns empty string, no fence). Lock-in test asserts this. | None — covered by AC12. |
| T5 | Length cap interaction: fenced-text exceeds context budget (`QUERY_CONTEXT_MAX_CHARS`); truncation drops closing tag, leaving unfenced suffix | Tampering | Fence adds fixed overhead (~150 chars for tag-pair + assertion); AC11 implementation MUST reserve overhead BEFORE the truncation cap (subtract fence_len from `effective_max` in `_build_query_context`). Lock-in test for truncation-with-fence boundary. | None — engineered into the implementation contract. |

### AC06-AC08 — Snapshot subjects

| ID | Threat | STRIDE | Mitigation | Residual |
|----|--------|--------|------------|----------|
| T6 | Snapshot tests embed wall-clock timestamps / random IDs / nondeterministic dict ordering, breaking on different machines or future runs | Repudiation (test-determinism class) | Each AC enumerates the determinism vectors in its production function and either (a) proves no nondeterminism exists OR (b) monkeypatches / canonicalizes in the test. AC07 + AC08 both go through `incremental=False` to force full rebuild for stable output. AC08 canonicalizes JSON via `sort_keys=True`. | None — test-class only. |
| T7 | Test fixture pages contain content that triggers content-hash branches in production, causing snapshot drift on Python version upgrade (`hashlib` shim differences) | Repudiation | Snapshot tests pin the canonicalized OUTPUT of the function under test, not transient hashes. Where a hash IS in the output, the fixture content is deterministic. | Python-version sensitivity; if `hashlib.sha256` semantics shift cross-version (extremely unlikely), snapshot rebases via `--snapshot-update`. |

### AC09 — cycle-69 AC14 date-contingent edge case audit

| ID | Threat | STRIDE | Mitigation | Residual |
|----|--------|--------|------------|----------|
| T8 | The `_FakeDate` monkeypatch at `tests/test_cycle69_snapshots.py:98` covers `kb.ingest.pipeline.date.today()` but a future call site relocation moves the call to a sibling module (e.g. `kb.ingest._helpers.date.today()`), bypassing the patch | Repudiation | AC09 audit reads ALL `date.today()` / `datetime.now()` call sites across `pipeline.py` and verifies the monkeypatch covers exactly the ones `_persist_contradictions` exercises. If gap found, AC09 expands the patch OR replaces with `freezegun` for module-agnostic freeze. | None this cycle. |

### AC10 — `test_prune_base_uses_canonical_rel_path` C41-L1 upgrade

| ID | Threat | STRIDE | Mitigation | Residual |
|----|--------|--------|------------|----------|
| T9 | New stub-and-spy test does not actually exercise both `compile_wiki(mode="full")` AND `detect_source_drift`; one branch is dead | Repudiation (vacuous test) | Per cycle-21 L1: parametrize over both call sites; assert spy count >= 1 from EACH branch (use `spy.call_args_list` filtered by stack frame OR separate spy per branch). Lock-in: revert the helper-call at site-1 -> test fails. Revert at site-2 -> test fails. | None. |

### Carry-over threats (cycle 69 -> cycle 70)

| ID | Threat | STRIDE | Mitigation | Residual |
|----|--------|--------|------------|----------|
| T10 | BACKLOG.md entries deleted in cycle-70 AC01-AC04 are silently re-introduced in cycle-71 by stale-context drift | Repudiation | AC05 lock-in test adds the deleted-entry signature strings to the cycle-68 lock-in pattern; CI fails if BACKLOG re-grows the same string. | None — pattern proven across cycle 68/69. |

## Mitigations summary (Step 14 verification checklist)

Step 14 must verify each:

1. **T1 mitigation present**: `wrap_wiki_context()` returns string containing both fence and assertion.
2. **T2 lock-in present**: AC12 (b) asserts both call sites use the helper.
3. **T3 escape present**: implementation rejects/escapes `</wiki_context>` substring inside wiki content.
4. **T4 short-circuit present**: empty wiki-context returns empty string (no orphan fence).
5. **T5 budget reservation present**: `effective_max - fence_overhead` in `_build_query_context` truncation logic.
6. **T6 determinism**: each snapshot test enumerates vectors in its docstring.
7. **T7 hash stability**: any hash in fixture output uses content-deterministic input.
8. **T8 date-coverage**: AC09 audit produces a written verdict — covered OR gap-fix shipped.
9. **T9 spy completeness**: AC10 test asserts both branches (full mode + drift detect) hit the helper.
10. **T10 lock-in coverage**: AC05 covers all 4 deleted entries.

## Open security followups (forward-looking, not cycle-70 ACs)

These are noted for cycle-71+ BACKLOG addition but NOT implemented in cycle 70:

- **F1** — AST guard test that forbids direct synthesis-prompt context concat outside the `wrap_wiki_context()` helper. Pattern: AST walk of `kb.query.engine` + `kb.mcp.core` for any string literal containing `--- Page:` that is NOT wrapped in `wrap_wiki_context()` call. Add to BACKLOG Phase 4.5 LOW post-merge.

## dep-CVE baseline snapshot

**Source:** `D:/Projects/llm-wiki-flywheel/.venv/Scripts/pip-audit.exe --format json -o .data/cycle-70/cve-baseline.json`
**Date:** 2026-05-08 22:08
**Total deps audited:** 323

| Package | Version | CVE | Severity | Decision |
|---------|---------|-----|----------|----------|
| diskcache | 5.6.3 | CVE-2025-69872 / GHSA-w8v5-vhqr-4h9v | HIGH (pickle-deserialization RCE) | **Risk-accept** — KB never reads diskcache from untrusted directory; cache lives under `.venv/` user-owned. No upstream patched version published. Re-check at next cycle's Step-02. Rationale unchanged from cycle 68 AC10 + cycle 69 baseline. |

**0 PR-introduced CVEs at Step 02 baseline** (no dependency changes proposed in cycle 70 ACs; httpx pin already shipped cycle 68 AC09).

**Dependabot baseline at Step 02:** 0 open alerts (`gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts --jq '[.[]|select(.state==\"open\")]'` -> `[]`).

**Step 11 PR-CVE diff target:** snapshot will be re-run at Step 11; diff vs `.data/cycle-70/cve-baseline.json`. Expected diff = empty (no dep changes).

## Approval

Step 02 self-approved by primary session (Opus). Subagent dispatch deferred per cycle-67 telemetry (24-min Opus subagent latency; primary-session sufficient for <=16-AC + 1-helper module + 0-dep-change cycle). CVE baseline captured. Threat model enumerates 10 threats across 5 ACs with explicit Step-14 verification checklist. Proceeding to Step 03 (brainstorming).
