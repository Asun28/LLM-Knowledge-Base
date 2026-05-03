# Cycle 61 — Brainstorm

For each non-trivial decision: 2-3 alternatives, trade-offs, primary-session recommendation. Step 4 design eval (Opus R1 + DeepSeek R2) will weigh in.

## D1 — AC6 allowlist loader location

**Alternatives:**
- A) Put `_get_duplicate_slug_allowlist()` in `src/kb/config.py` next to `DUPLICATE_SLUG_ALLOWLIST` (same module).
- B) New module `src/kb/lint/allowlist.py` with `load_lint_allowlist(name: str)` parameterized over allowlist names.
- C) New module `src/kb/lint/checks/duplicate_slug.py` (the consumer file) defines a private `_load_allowlist()` next to `_is_allowlisted_pair`.

**Trade-offs:**
- A: minimal churn, one file, follows existing config-as-data pattern. Risk: config.py is already a god-module per BACKLOG MED entry; adding a function feels like the wrong direction.
- B: futureproof for additional allowlists (cycle-25+ "dim_mismatches_seen" counter pattern hints we'll want more). Risk: speculative — over-engineering for one allowlist.
- C: keeps loader local to consumer. Risk: when a 2nd allowlist arrives, refactor cost is one move.

**Recommendation: A.** One allowlist exists today; no concrete signal a 2nd is coming. Per CLAUDE.md "Don't design for hypothetical future requirements." Migrate to (B) when a 2nd allowlist actually lands.

## D2 — AC7 file format + path

**Alternatives:**
- A) `.data/lint_allowlist.json` — stdlib `json.load`, no PyYAML pull. JSON shape: `{"_comment": "...", "duplicate_slugs": [["a", "b"], ...]}`.
- B) `wiki/_lint.yml` — YAML, more comment-friendly (real comments via `#`), co-located with the wiki it constrains. Adds PyYAML hard dependency (already in deps via `python-frontmatter` though).
- C) Keep allowlist hardcoded; reject the BACKLOG entry as YAGNI.

**Trade-offs:**
- A: aligns with existing `.data/hashes.json`, `.data/feedback.jsonl`, `.data/verdicts.jsonl`. `.data/` is gitignored — file would NOT be checked in. **This is wrong** for a curated allowlist; the file MUST be committed. Either move to `.data/` and remove from gitignore, or pick a non-gitignored location.
- B: `wiki/_lint.yml` co-located with the wiki, intuitive for users. YAML supports inline comments (better self-documentation). Schema: `duplicate_slugs:\n  - [a, b]\n  - [c, d]`.
- C: defer altogether. But three pairs already documented in CLAUDE.md + cycle-16 history — operator has felt this pain.

**Recommendation: B (`wiki/_lint.yml`).** PyYAML is already pulled in transitively. Co-location makes the allowlist discoverable to the operator. Inline comments explain WHY each pair is allowlisted (which the in-code frozenset cannot). Failure-open behavior identical to A. **Reject A** because `.data/` is gitignored and the allowlist must be checked in.

## D3 — AC10 short-circuit placement

**Alternatives:**
- A) Top-of-function early return in `hybrid_search`: `if kb.config.KB_DISABLE_VECTORS: return bm25_fn(question, limit)`.
- B) Inside the function, replace `vector_fn` with a no-op lambda when env-var set; let RRF still run with a single list.
- C) Push the env-var check into the BM25-only and vector-only call sites individually.

**Trade-offs:**
- A: clearest call-graph for Step 14 audit. Skips the BM25 expansion path too (fine — expansion is a vector-side optimization). `query_tokens` log line still fires from the early-return path? Need to ensure nothing observability-load-bearing runs after the short-circuit. Does NOT call `expand_fn`.
- B: keeps the same code path; less special-casing. Drawback: still pays the `expand_fn` cost (LLM call) for nothing. RRF over a single list is wasted work but correct.
- C: most invasive; requires changes at multiple sites. Worst.

**Recommendation: A.** Cycle-15 L4 (count-sensitive doc fields) suggests we should also assert at Step 14 that the early-return doesn't break observability counters — confirm `query_tokens` and the per-backend WARNING logs are not load-bearing on the short-circuit path. If they are, log the INFO line explicitly even on short-circuit.

## D4 — T12 MCP audit-tag (`caller="mcp"`)

**Alternatives:**
- A) Implement in cycle 61: thread `caller="mcp"` through `kb_rebuild_indexes` to `append_wiki_log`. Requires extending `append_wiki_log` signature (or adding a wrapper). Adds 1 file (`kb/utils/wiki_log.py`) to the cycle's touched-files list.
- B) Defer to next cycle: file BACKLOG MED entry per Step 2 B1 candidate. Currently NOT enforced anywhere — cycle 61 inherits the gap, doesn't introduce it.
- C) Implement at the wrapper level: prepend `[caller=mcp]` token to the audit message via wrapping logic in the MCP tool, NOT modifying `append_wiki_log`. Less invasive but redundant if other MCP tools want the same.

**Trade-offs:**
- A: closes the cycle-20 L3 rule cleanly; future MCP tools inherit. But touches an unrelated file, expanding cycle scope.
- B: respects "minimum scope per cycle" rule; the gap exists today and isn't worse after cycle 61.
- C: mid-ground; works for cycle 61 only, future MCP tools repeat the prepend.

**Recommendation: B (defer to BACKLOG MED).** Cycle 61 is a 21-AC batch already; expanding to fix a pre-existing systemic gap exceeds the scope. The deferred entry is load-bearing per cycle-23 L1 — Step 17 doc-update WILL file the BACKLOG entry. Step 14 verifies T12 status: "audit tag not threaded — BACKLOG B1 filed".

## D5 — T2 sandbox-flag pin in test

**Alternatives:**
- A) Extend `tests/test_cycle21_cli_backend.py::test_call_cli_codex_exec_jsonl_path` (already exists from d7a98b7) to add 2 assertions: `cmd[cmd.index("--sandbox") + 1] == "read-only"` AND `"--skip-git-repo-check" in cmd`. ~3 lines of test code.
- B) Defer to BACKLOG LOW (per Step 2 B3 candidate).
- C) Ignore — d7a98b7 already pins `cmd[1:4] == ["exec", "--json", "--ephemeral"]`, treat that as sufficient.

**Trade-offs:**
- A: trivially small; already in scope (the test file is in d7a98b7). Removes the silent-downgrade window.
- B: minor — BACKLOG entry handles future sweep.
- C: leaves the regression window open; cycle-15 L4 (count-sensitive) and threat-model T2 both flag this.

**Recommendation: A.** ~3 lines, file already in scope, closes a real regression window. Tag the assertion with `# T2: pin sandbox flag` for grep-discoverability.

## D6 — T5 allowlist size cap

**Alternatives:**
- A) Add `MAX_LINT_ALLOWLIST_BYTES = 64_000` cap in cycle 61. Reader checks `Path.stat().st_size` before reading; over-cap → WARNING + fall back.
- B) Defer to BACKLOG LOW (per Step 2 B2 candidate).
- C) Ignore — `wiki/_lint.yml` is curated, not user-input; the threat is theoretical.

**Trade-offs:**
- A: <5 lines, defense in depth. Keeps Step 14 verdict clean.
- B: BACKLOG entry handles it; cycle 61 stays focused.
- C: T5 likelihood is "Very Low"; impact is "Low" (only `kb lint` impacted). Probably fine to skip given the trust boundary.

**Recommendation: A.** Trivial code; the cost of NOT having the cap is unbounded `json.load` time on a corrupted file. AC6 already requires failure-open semantics; the size cap is one extra `if size > MAX: log + fall back` line. Adopt.

## Aggregate impact on AC list

Decisions that change the AC count:
- D2 → AC7 file path changes from `.data/lint_allowlist.json` to `wiki/_lint.yml`; format JSON → YAML. (No AC count change.)
- D5 → adds ~3 lines to existing test (no new AC; absorbed in AC5 verification scope or as a sub-bullet).
- D6 → adds ~5 lines to AC6 loader; absorbed in AC6.

Net: still 21 ACs, same files-touched list except `.data/lint_allowlist.json` → `wiki/_lint.yml`. PyYAML stays a transitive dep (no requirements.txt change).

## Open questions deferred to Step 4 design eval

1. D2 — does YAML add measurable cold-load latency vs JSON? (PyYAML CSafeLoader is fast; probably no.)
2. D3 — does early-return need to log INFO regardless of `caplog.at_level` ordering? (Cycle-15 L4 — implementer must place the log INSIDE the if-branch.)
3. D5 — should the `_MODEL_RE` validator also reject Unicode RTL marks? (Step 2 T-OUT-1 said operator-controlled, accepted. Re-confirm at Step 4.)
4. D6 — `MAX_LINT_ALLOWLIST_BYTES` value: 64KB feels right; cycle 13 used 64KB caps elsewhere. Confirm.
