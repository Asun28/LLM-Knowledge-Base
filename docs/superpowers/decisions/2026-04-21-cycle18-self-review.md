# Cycle 18 — Step 16 Self-Review

**Date:** 2026-04-21
**Merged PR:** [#32](https://github.com/Asun28/llm-wiki-flywheel/pull/32) — 11 commits, 2548 → 2592 collected (+44 tests, 2587 passing).
**Scope:** 16 ACs across 5 files — ingest observability (`.data/ingest_log.jsonl` + `request_id` correlation), `inject_wikilinks` per-page TOCTOU lock, wiki_log rotate-in-lock + generic `rotate_if_oversized`, `sanitize_text` + UNC coverage, `_write_index_files` helper, `tmp_kb_env` HASH_MANIFEST redirection, 3-scenario e2e workflow test.

## Scorecard (Steps 1–15)

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | Clean 16 ACs; cycle-17 deferrals cleanly mapped. |
| 2 — Threat model + CVE baseline | yes | NO — infra fallback | Threat-model Opus subagent surfaced 3 critical findings (AC14/AC15 symbol drift, sanitize_error_text shape mismatch, atomic_text_write JSONL trap) — all valuable. CVE baseline: 0 Dependabot, 1 pip-audit (diskcache, no patch). `pip-audit` failed at first under Windows venv-resolver conflict (`requests==2.33.0`), fell back to `--disable-pip` against installed venv. |
| 3 — Brainstorming | yes | yes | 7 design decisions (D1-D7) + 12 open questions enumerated in-session per feature-dev autonomous-mode. |
| 4 — Design eval R1 Opus + R2 Codex parallel | yes | yes | R1 Opus: 2 BLOCKERs + 3 MAJORs (AC7 TOCTOU, AC11 missing failure-emission path, AC3 vague target, AC15 symbol drift, AC16 mock-reach invariant). R2 Codex: 4 BLOCKERs + 4 MAJORs (independent try/except, UNC gap, writer mechanics, vacuous-test risks). Symbol-verification gate worked — caught real AC drift. |
| 5 — Design decision gate | yes | yes | 21 open questions resolved autonomously by Opus subagent. APPROVE-WITH-AMENDMENTS on 12 ACs. All design decisions embedded reviewer findings. |
| 6 — Context7 verification | SKIPPED | n/a | Pure stdlib + internal code — no external library API to verify. |
| 7 — Plan (primary session) | yes | yes | 16 ACs grouped into 6 task clusters (batch-by-file). Cycle-14 L1 heuristic applied: primary-session drafting for ≥15 AC cycles with full context. |
| 8 — Plan gate | yes | NO — 2 amendments | Codex plan-gate REJECTed with 2 amendments: (a) TASK 1 HASH_MANIFEST routing (config-attribute loop would raise AttributeError — needs separate patch); (b) TASK 5 `dict(outcome)` wholesale copy violates field-allowlist → needs explicit scalar-key construction. Both applied inline. |
| 9 — Implementation (TDD) | yes | NO — 2 mid-course corrections | (a) cycle-2 `TestInjectWikilinksSingleFrontmatterMatch` test expectation bumped from ≤1 to ≤2 per page × title — legitimate behavioural change from AC7's peek + under-lock re-read. (b) Full-suite test ordering bug: `_emit_ingest_jsonl` writing to real PROJECT_ROOT in some orderings because module-level `PROJECT_ROOT` binding wasn't patched; fixed by dynamic lookup via `kb.config` at call time. Both closed in-cycle. |
| 10 — CI hard gate | yes | yes | 2585 pass / 7 skip / ruff clean / format clean after TASK 6. |
| 11 — Security verify | yes | NO — Codex initially API-errored | Codex first attempt returned `API Error: Unable to connect to API (ConnectionRefused)` — codex CLI was mid-update. Dispatched Sonnet fallback + Codex retry in parallel when user confirmed codex was available again. Codex APPROVE (all 10 threats IMPLEMENTED); Sonnet-fallback surfaced 1 LOW gap (T9 position-pin used `re.search` not anchored match) — closed in-cycle via test tightening commit `68637e7`. |
| 11.5 — Existing-CVE patch | SKIPPED | n/a | Only diskcache `CVE-2025-69872` exists; no patched upstream; already in BACKLOG per threat model §9. |
| 12 — Doc update | yes | yes | CHANGELOG cycle-18 entry added (Quick Reference + Cycle Summaries); BACKLOG cycle-18 candidates deleted (3 carried to cycle-19); CLAUDE.md test counts updated to 2585/2592. |
| 13 — Branch finalise + PR | yes | yes | PR #32 opened with full review trail, test plan, commit graph. |
| 14 — PR review rounds | yes | NO — 3 rounds (mandatory per 4/4 triggers) | R1 Codex REQUEST-CHANGES (1 BLOCKER + 1 MAJOR: try/except boundary + success-emission location). R1 Sonnet APPROVE-WITH-NITS (2 MAJORs: byte-slice truncation + comment clarity; 6 informational). R1-fix commit `cb420bb` + `5271121` closed all 3 substantive findings + added 2 regression tests. R2 Codex APPROVE. R3 Sonnet APPROVE (1 LOW theoretical double-emit under KeyboardInterrupt, non-blocking per Q8 best-effort contract). |
| 15 — Merge + cleanup | yes | yes | PR #32 merged at 2026-04-21T00:23:44Z (fdfc663). Local branch deleted. 0 post-merge Dependabot alerts. |

**Summary**: 11 of 15 steps first-try-pass; 4 steps had structural iteration (plan-gate amendments, impl ordering bugs, Codex infra glitch, PR review rounds). All iterations resolved in-cycle without scope expansion.

## Lessons learned (extracting skill patches)

### L1 — Dynamic module-attribute lookup for test-ordering resilience

**What happened:** Full-suite test run found `_emit_ingest_jsonl` writing to REAL `PROJECT_ROOT/.data/ingest_log.jsonl` instead of `tmp_kb_env / .data / ingest_log.jsonl` in some orderings. Root cause: `from kb.config import PROJECT_ROOT` at module top creates `kb.ingest.pipeline.PROJECT_ROOT`; `tmp_kb_env` patches `kb.config.PROJECT_ROOT` + mirror-rebinds `kb.*`, but mirror-rebind only fires if current binding `==` original. Some earlier test in the full run left `pipeline.PROJECT_ROOT` desynced (or triggered lazy-import timing where the mirror didn't catch it). Fixed by switching `_emit_ingest_jsonl` to read `PROJECT_ROOT` dynamically via `import kb.config; kb.config.PROJECT_ROOT` at call time.

**Root cause lens:** `from X import Y` at module scope creates a snapshot-binding; monkeypatch on `X.Y` does NOT update the snapshot. The `tmp_kb_env` mirror-rebind loop is a workaround that sometimes misses under ordering variations. For NEW helpers that read cross-module state, prefer `import module; module.ATTR` over `from module import ATTR`.

**Skill patch (feature-dev Red Flags):**

> "My helper uses `from kb.config import PROJECT_ROOT` at module top" → **Snapshot-binding hazard in tests.** `from X import Y` captures Y's current value; `monkeypatch.setattr(X, "Y", tmp)` updates `X.Y` but NOT `kb.caller.Y`. `tmp_kb_env` mirror-rebinds to compensate but misses under ordering variations (lazy imports, sys.modules state left by earlier tests). Rule: for NEW helpers reading PROJECT_ROOT / WIKI_DIR / RAW_DIR at call time, prefer `import kb.config; kb.config.PROJECT_ROOT` — the attribute lookup hits the patched value regardless of snapshot freshness. Existing `from X import Y` patterns that work today should NOT be refactored proactively — only fix if a test-ordering bug surfaces. Self-check before commit: any new function writing to a path derived from `PROJECT_ROOT` → use dynamic lookup.

### L2 — Split-body refactor with telemetry envelope requires explicit boundary contract

**What happened:** R1 Codex MAJOR caught that `stage="success"` was emitted inside `_run_ingest_body` (which was split out of `ingest_source` for clean try/except scoping). The intention was "body runs, then success emitted" — which is what a linear reader would assume. But the contract the design-gate set was "all 4 stage emissions at the ingest_source boundary," so `_run_ingest_body` should be PURE body with telemetry emitted by the CALLER.

**Root cause lens:** When splitting a function for exception-handling clarity, the caller-owned telemetry MUST be emitted by the caller, not by the new helper. Even if the code logically runs in the same order, the semantic boundary "helper can be called without telemetry" vs "helper always emits" matters for reuse + reviewer comprehension.

**Skill patch (feature-dev Step 9):**

> **Telemetry envelope boundary rule (cycle-18 L2).** When splitting a function body into a `_run_inner_body` helper to get a clean try/except scope around it, the caller-owned telemetry/audit emissions (start/success/failure log rows, metrics, span ends) MUST stay in the CALLER, not move into the new helper. The helper is "pure worker"; the caller is "envelope." Self-check: after splitting, grep the new helper for the telemetry symbols (`_emit_X`, `logger.info("Success"`, span.set_status(OK)`); if any remain in the helper, refactor to return status + have the caller emit. This keeps the helper reusable from other call sites that want a different envelope (e.g. batch loops that batch-emit at the outer scope).

### L3 — Pre-body exception paths outside try/except create orphan telemetry rows

**What happened:** R1 Codex BLOCKER caught that the try/except wrapping `_run_ingest_body` didn't cover `extract_from_source` or `_pre_validate_extraction` at pipeline.py:1072-1074, which run AFTER `stage="start"` is emitted. Extraction/validation exceptions produced orphan `start` rows with no terminal emission. Fix: move the try/except to start immediately AFTER `stage="start"` emission, wrapping ALL subsequent code (extraction + validation + duplicate check + body).

**Skill patch (feature-dev Step 9):**

> **Telemetry try/except boundary rule (cycle-18 L3).** When a function emits `stage="start"` early and relies on a later try/except to emit `stage="failure"` on exceptions, audit EVERY line between the start emission and the try block. Any operation that can raise (extraction, validation, ID reservation, option parsing, hash computation) before the try is an "orphan-row" risk. Rule: the try block should start ON THE LINE AFTER the start emission, no intermediate code. If some pre-start work MUST happen between start and the body (rare), emit start INSIDE the try AFTER that work, then wrap the body. Self-check: grep the diff for `_emit_X("start"` — the next non-comment line should be `try:`.

### L4 — Byte vs char truncation under PIPE_BUF bound

**What happened:** R1 Sonnet M1 caught that `sanitize_text(err)[:2048]` counts Unicode CODE POINTS, not UTF-8 bytes. A 2048-char CJK error string serializes to ~6144 UTF-8 bytes, blowing past PIPE_BUF atomicity (threat T7). Fix: `.encode("utf-8")[:2048].decode("utf-8", errors="ignore")`.

**Skill patch (feature-dev Red Flags):**

> "Truncate `error_summary` to 2KB → use `str[:2048]`" → **Python string slice counts code points, not bytes.** A 2048-char CJK or emoji string encodes to ~6144 UTF-8 bytes and can overflow PIPE_BUF atomicity bounds (typically 4096 bytes on Linux, lower on BSD). Rule: when a length cap is meant to bound BYTES (PIPE_BUF atomicity, disk-budget-per-record, network-frame), use `.encode("utf-8")[:N].decode("utf-8", errors="ignore")` — NOT `s[:N]`. `errors="ignore"` drops any partial trailing byte sequence; `errors="replace"` would insert U+FFFD and re-violate the bound. If the cap is meant to bound DISPLAY length (UI truncation), char slicing is correct but `len(s.encode("utf-8"))` should be asserted in tests anyway. Self-check before commit: any new truncation where the comment says "N bytes" and the code does `s[:N]` → refactor.

## Metrics

- Step count: 15 of 15 executed (Step 6 + Step 11.5 documented skips).
- First-try-pass steps: 11 of 15.
- Total commits: 11 (6 TASK commits + 1 T9 test tightening + 1 docs + 2 R1-fix + 1 chore cleanup).
- New tests: +44 (2548 → 2592 collected; 2587 passing + 7 skipped).
- New test files: 6 (`test_cycle18_conftest`, `test_cycle18_wiki_log`, `test_cycle18_sanitize`, `test_cycle18_linker_lock`, `test_cycle18_ingest_observability`, `test_workflow_e2e`).
- PR review rounds: R1 Codex + R1 Sonnet parallel → R1 fix → R2 Codex → R3 Sonnet (4/4 triggers fired).
- Design-gate questions resolved: 21.
- Deferred ACs filed to BACKLOG cycle-19: 3 (MCP monkeypatch migration, `inject_wikilinks_batch`, HASH_MANIFEST explicit-patch cleanup).
- CVE drift post-merge: 0.

## Cycle termination

Cycle 18 is COMPLETE. PR #32 merged at 2026-04-21T00:23:44Z (fdfc663); local branch deleted; 0 post-merge Dependabot alerts; 4 skill lessons captured (L1-L4).
