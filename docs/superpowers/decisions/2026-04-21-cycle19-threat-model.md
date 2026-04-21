# Cycle 19 Threat Model

**Date:** 2026-04-21
**Sibling docs:** `2026-04-21-cycle19-requirements.md`
**Baselines:** `/tmp/cycle-19-alerts-baseline.json` + `/tmp/cycle-19-cve-baseline.json`

## Analysis

Trust boundaries enumerated per cluster. Page titles entering `inject_wikilinks_batch` originate from LLM-extracted JSON (ingest/pipeline.py `extraction["title"]`) — semi-trusted. Raw source files in `raw/` are human-curated but may contain adversarial content (e.g. an ingested phishing article whose title contains control characters or regex anti-patterns). The alternation regex used by the batch helper is compiled from `re.escape(title)` for each title in the batch, so regex metacharacters cannot escape the literal match; the residual risks are (a) alternation size (ReDoS by volume), (b) null-byte collision with the existing `_mask_code_blocks` placeholder scheme at `linker.py:60-67` which uses `\x00{prefix}{n}\x00` as a mask sentinel, and (c) log injection of title text into `wiki/log.md`. Log injection is already mitigated at the `append_wiki_log` boundary (`utils/wiki_log.py:89-100` — ZWSP prefix on `#/-/>/!` and `[[...]]` neutralization), so the new batch log line inherits that defense for free as long as it calls `append_wiki_log(operation, message, ...)` rather than writing the log file directly. The null-byte placeholder risk is mitigated by the existing per-call UUID prefix (`prefix = uuid.uuid4().hex[:8]`) which guarantees a title containing `\x00<anything>\x00` cannot collide with a valid placeholder unless the title also contains the per-call random hex — negligible.

Cluster B's lock-order flip (history FIRST, page SECOND) is the subtlest change. Today only `refine_page` touches the history-path lock, so there is no existing caller holding history-lock and then requesting page-lock — the deadlock risk is null in the current call graph. The real concern is liveness: holding `file_lock(history_path)` across the entire page-write window serializes every concurrent refine across the wiki (history is a single JSON file, not per-page), amplifying tail latency on a concurrent-refine workload. Severity is LOW because (i) refine is not a hot path and (ii) the window is bounded by `atomic_text_write` which is milliseconds. Cluster C's `manifest_key=` kwarg is the most security-relevant new surface: a caller that passes an attacker-derived string (e.g. `"../../../etc/passwd"`) writes that key into the JSON manifest dict. The manifest key is never used as a filesystem path (it is a dict key only — lookups use `manifest.get(key)`), so the worst-case is manifest pollution / cache-poisoning of `find_changed_sources`, not RCE. But AC12 must document `manifest_key` as "opaque string, not a path" and preferably validate that trusted callers pass `_canonical_rel_path`-derived keys. Cluster D is test-code-only (T-N/A) and Cluster E's log-injection surface is closed by the existing `append_wiki_log` sanitizer.

## Summary

**5 threats identified: 0 critical, 1 high, 3 medium, 1 low.**
CVE baseline: `/tmp/cycle-19-alerts-baseline.json` + `/tmp/cycle-19-cve-baseline.json`.

## Threats

### T1 — Batch-alternation ReDoS via unbounded title count
**Severity:** HIGH
**Trust boundary crossed:** LLM-extracted title (semi-trusted) → regex alternation in `inject_wikilinks_batch`
**Attacker:** A compromised / prompt-injected ingest extraction produces hundreds of long titles in a single batch. Without chunking, the alternation `re.compile` cost and per-page scan cost scale linearly with batch size and pathological titles can push this into worst-case backtracking.
**Mitigation (required):** AC4 — enforce `MAX_INJECT_TITLES_PER_BATCH = 200` in `kb.config` and split larger batches into sequential chunks of 200 in the batch helper. Each title MUST pass through `re.escape` before alternation. The per-title regex MUST use the existing `\b`-aware left/right anchors from `inject_wikilinks` (linker.py:199-207) unchanged.
**Verification (step 11):**
- `grep -n "MAX_INJECT_TITLES_PER_BATCH" src/kb/config.py src/kb/compile/linker.py` → constant defined + referenced.
- `grep -n "re.escape" src/kb/compile/linker.py` → every title path escaped.
- T-4 regression: 250 titles → two chunk rounds, all 250 processed.
- Revert-check (cycle-11 L1 gate): removing the chunk loop makes T-4 fail with a single-chunk observation.

### T2 — Null-byte title smuggling past code-mask placeholder
**Severity:** MEDIUM
**Trust boundary crossed:** LLM-extracted title → `_mask_code_blocks` placeholder scheme (`linker.py:60-67` uses `\x00{prefix}{n}\x00`).
**Attacker:** A title containing `\x00<8-hex>\x00` could in principle collide with an active placeholder, letting a wikilink-injection write smuggle into a code block.
**Mitigation (required):** AC1 — `inject_wikilinks_batch` MUST reuse `_mask_code_blocks` / `_unmask_code_blocks` unchanged (per-call UUID prefix already mitigates collisions). In addition, AC1 SHOULD positively reject titles containing `\x00` via a `title.replace("\x00", "")` sanitization step at the entry of the batch helper — the title is then also safe for the log line and the regex.
**Verification (step 11):**
- T-1 variant: pass a title `"A\x00deadbeef\x00B"`; assert the batch helper processes it without crashing AND that a code block containing `A...B` is not overwritten.
- `grep -n "replace.*\\\\x00\\|\\\\x00.*replace" src/kb/compile/linker.py` → sanitizer present.

### T3 — Manifest-key injection via opaque `manifest_key=` kwarg
**Severity:** MEDIUM
**Trust boundary crossed:** `ingest_source(manifest_key=...)` kwarg → JSON dict key in `.data/hashes.json`.
**Attacker:** A future caller (plugin, MCP extension) passes a caller-controlled string that was not canonicalized by `_canonical_rel_path`. The string becomes a JSON object key — not a filesystem path — so the worst-case is manifest corruption / cache-poisoning that makes `find_changed_sources` re-extract or skip incorrectly. Not RCE, but an integrity/availability threat.
**Mitigation (required):** AC12 — document in the `ingest_source` docstring that `manifest_key` is an opaque string produced by `manifest_key_for` and MUST NOT be trusted input. AC11 — expose `manifest_key_for` as the single public way to compute keys. AC13 — `compile_wiki` MUST call `manifest_key_for(source, raw_dir)` and thread the result through; no other caller passes the kwarg. Kwarg is keyword-only (Q6 default: yes).
**Verification (step 11):**
- `grep -n "manifest_key=" src/kb/ingest/pipeline.py src/kb/compile/compiler.py` → only `compile_wiki` passes it; `ingest_source` accepts it keyword-only.
- T-12 / T-13 regression + a NEW T3 unit test: call `ingest_source(manifest_key="../../etc/passwd")` and assert the manifest stores the string literally without any filesystem access under that path.

### T4 — Refine two-phase write history-lock liveness regression
**Severity:** MEDIUM
**Trust boundary crossed:** Cross-process concurrent `refine_page` calls → global `file_lock(history_path)`.
**Attacker:** N/A — this is a self-inflicted liveness risk, not an external threat. Reordering locks to history-FIRST means the history lock is held across the entire page-write window, serializing every concurrent refine across the wiki.
**Mitigation (required):** AC8/AC9/AC10 — the pending → applied flip MUST remain inside the history-lock (AC9 mandates this for crash-safety audit). Document in the `refine_page` docstring that (a) lock order is `history_path FIRST, page_path SECOND` and (b) callers should NOT hold either lock before invoking `refine_page`. AC10's test MUST record lock-acquisition order via mocked `file_lock` context managers to prove ordering.
**Verification (step 11):**
- T-10 regression asserts history-lock acquired before page-lock.
- `grep -n "file_lock(history\\|file_lock(resolved_history\\|file_lock(page" src/kb/review/refiner.py` → both acquisitions present in the documented order.
- Docstring grep: `grep -n "lock order\\|history_path FIRST" src/kb/review/refiner.py` → rationale present.

### T5 — Log injection via malicious page titles in batch wiki_log entry
**Severity:** LOW
**Trust boundary crossed:** LLM-extracted title → `append_wiki_log` → `wiki/log.md`.
**Attacker:** A title containing newlines, `[[wikilink]]` syntax, or leading `#`/`-`/`>`/`!` Markdown markers could corrupt `wiki/log.md` readability or smuggle live wikilinks into the audit log.
**Mitigation (required):** AC20 — the single `inject_wikilinks_batch` log line MUST route through `append_wiki_log(operation, message, log_path)` (NOT a direct `log_path.write_text`) so the existing `_escape_markdown_prefix` sanitizer (`utils/wiki_log.py:89-100`) neutralizes `#/-/>/!` prefixes, collapses newlines/tabs/pipes, and ZWSP-inserts `[[`/`]]` brackets.
**Verification (step 11):**
- `grep -n "append_wiki_log\\|log_path.write" src/kb/ingest/pipeline.py` → batch log site uses `append_wiki_log`.
- T-20 regression: pass a title `"# Evil [[page]]"`; assert the log.md line contains the ZWSP-escaped form.

## AC → threat mapping

| AC | threats addressed |
|----|-------------------|
| AC1 (`inject_wikilinks_batch` signature) | T2 |
| AC2 (single-pass read amplification) | (perf only — no threat) |
| AC3 (at-most-one wikilink per page) | (correctness only) |
| AC4 (`MAX_INJECT_TITLES_PER_BATCH=200`) | T1 |
| AC5 (no-lock fast path) | (perf only) |
| AC6 (pipeline switches to batch call) | T1, T2, T5 (inherits all batch-helper mitigations) |
| AC7 (`pages=` kwarg) | (perf only) |
| AC8 (pending → applied status field) | T4 (audit visibility) |
| AC9 (pending flip inside history-lock) | T4 |
| AC10 (history FIRST, page SECOND) | T4 |
| AC11 (`manifest_key_for` public alias) | T3 |
| AC12 (`manifest_key=` keyword-only) | T3 |
| AC13 (`compile_wiki` threads canonical key) | T3 |
| AC14 (prune base consistency) | (correctness only — T3-adjacent) |
| AC15/AC16 (MCP monkeypatch migration) | T-N/A (test-only) |
| AC17/AC18 (HASH_MANIFEST patch cleanup) | T-N/A (test-only) |
| AC19 (batch e2e lock-count test) | (perf regression gate) |
| AC20 (single batch log line via `append_wiki_log`) | T5 |

## Step 11 security-verify checklist (copy-into-plan)

1. Run `/tmp/cycle-19-alerts-baseline.json` / `/tmp/cycle-19-cve-baseline.json` diff after cycle-19 dep bumps (Dependabot four-gate model).
2. `grep MAX_INJECT_TITLES_PER_BATCH src/kb/config.py src/kb/compile/linker.py` — constant defined + referenced (T1).
3. `grep re.escape src/kb/compile/linker.py` — every title alternation path escaped (T1).
4. `grep '\\x00' src/kb/compile/linker.py` — title null-byte sanitizer in `inject_wikilinks_batch` entry (T2).
5. `grep 'manifest_key=' src/kb/ingest/pipeline.py src/kb/compile/compiler.py` — keyword-only, threaded from `compile_wiki` only (T3).
6. `grep 'file_lock(resolved_history\\|file_lock(page' src/kb/review/refiner.py` — ordered history → page (T4).
7. `grep 'lock order\\|history_path FIRST' src/kb/review/refiner.py` — docstring rationale present (T4).
8. `grep append_wiki_log src/kb/ingest/pipeline.py` — batch log site uses sanitized appender, not raw write (T5).
9. Run full suite: 2585 → 2585+N pass (no regression).
10. Run T-3 / T-12 / T-13 / T-20 / T-10 regression tests individually and confirm revert-to-pre-cycle-19 makes each fail (cycle-11 L1 vacuous-test gate).
