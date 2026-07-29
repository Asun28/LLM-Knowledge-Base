# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. **Detailed reference material lives in [`docs/reference/`](docs/reference/README.md)** — this file is the slim index. See the [Detailed Documentation](#detailed-documentation) table below for the full map.

## Quick Reference

- **State:** v0.12.0 · 3580 tests across 240 test files (cycle-88 added `tests/test_cycle88_rollback_reporting.py` [+15] — barrier-failure reporting in `refine_page`, all-or-nothing rollback indeterminacy in `capture.py`, and Windows junction/hardlink coverage for the evidence-stat; see the Rollback-and-durability reporting bullet. Cycle-87 added `tests/test_cycle87_durability_containment.py` [+24] — Windows rename-durability barrier (`durable_replace`), the two bare-`os.replace` peers routed through it, and the evidence-stat no-follow fix; see the Atomic-write durability and Evidence-resolvability bullets. Cycle-86 added `src/kb/lint/checks/evidence_resolvable.py` + `tests/test_cycle86_validation_ordering.py` [+62] — evidence-resolvability lint check, `allowed_values` value-domain gate at the tier boundary, ingest human-log ordering, and parent-dir fsync; see the Evidence-resolvability, Tier-boundary verifier, and Atomic-write durability bullets. Cycle-81 added `src/kb/utils/page_lock.py` + `tests/test_cycle81_page_lock.py` [+24] — reentrant per-page lock closing the Phase 4.5 HIGH R5 release-then-reacquire window; see the Per-page write lock bullet. Cycle-80 folded the v0915 task02/04/05/07 batch — 4 files, 51 tests — into 5 canonical receivers [`test_ingest`/`test_query`/`test_bm25`/`test_graph`/`test_refiner`], versioned `test_v0*`/`test_phase4_audit` files 24 → 20; cycle-78 folded the complete v0916 + v0917 series — 12 files, 96 tests — into 16 canonical receivers; cycle-77 folded the 5 remaining `test_v0100x` files into canonical receivers) (Windows local; ubuntu-latest CI strict-gated since cycle 36; windows-latest CI matrix deferred to cycle-53+ per cycle-36 L1 CI-cost discipline + cycle-39..74 carry-over). Cycle-74 adds `tests/test_cycle74_tier_boundary_hardening.py` (+24: 22 positive + 2 xfail-strict) and `src/kb/lint/augment/tier_boundary.py` (validator extraction); see the Tier-boundary verifier bullet. Cycle-73 counts at branch HEAD post-Step-9 (+~42 net tests over cycle-72 across 5 new cycle-73 test files: `tests/test_cycle73_completeness_wrap.py` (AC01 6 lock-ins + 2 xfail), `test_cycle73_prompt_version.py` (AC02 8 lock-ins + 2 xfail), `test_cycle73_tier_boundary.py` (AC03+AC04 14 lock-ins + 1 xfail), `test_cycle73_snapshots.py` (AC05 3 tests + 1 .ambr), `test_cycle73_backlog_hygiene.py` (AC06 4 doc-grep assertions); cycle-73 modifies 4 `src/kb/` files: `lint/semantic.py` AC01 + `lint/verdicts.py` AC02 + `lint/augment/orchestrator.py` AC03+AC04 + `errors.py` AC04 new `TierBoundaryError` plus `kb/config.py` AC02 new `CURRENT_PROMPT_VERSION` constant). Shipped → `CHANGELOG.md` (index) + `CHANGELOG-history.md` (per-cycle detail). Open → `BACKLOG.md`.
- **Always `.venv`** — activate before `pytest`, `kb`, `pip`. Never global Python.
- **Test fixtures** — under cycle 64 AC1, an autouse `_autouse_kb_path_sandbox` fixture redirects `kb.config.WIKI_*` / `RAW_*` / `PROJECT_ROOT` to per-test `tmp_path` for EVERY test by default. Tests that genuinely need the real repo paths request `real_project_root` and run pytest with `--use-real-paths`. Explicit `tmp_kb_env` (alias `kb_sandbox`) keeps the cycle-12+ patch+mkdir contract for the 230+ existing call sites. Never write real `wiki/` or `raw/`. `tmp_kb_env` already redirects `HASH_MANIFEST` — don't also monkeypatch it.
- **Graph cache** (cycle 64 AC9) — `kb.graph.cache.get_graph(wiki_dir, *, pages=None)` is the canonical entry for lint-pass graph lookup. Pages-supplying callers BYPASS the cache. Mutators (`ingest_source`, `refine_page`, `compile_wiki`) call `invalidate(wiki_dir)` post-success. Use attribute-lookup form (`kb.graph.cache.get_graph(...)`) per cycle-18 L1 to avoid snapshot-binding hazards.
- **Auto-rebuild + auto-publish** (cycle 64 AC6/AC14 + cycle 67 AC04/AC06) — `VectorIndex.query()` triggers `rebuild_vector_index` on dim-mismatch (kill-switch `KB_DISABLE_VECTOR_AUTO_REBUILD=1`); `compile_wiki` post-success calls `auto_publish_after_compile` to emit `_publish/{llms,llms-full,graph,sitemap}.{txt,jsonld,xml}` (kill-switch `KB_DISABLE_COMPILE_AUTO_PUBLISH=1`). **Cycle 67 AC04** — `KB_STRICT_PUBLISH=1` re-raises auto_publish failures instead of swallowing (default off; back-compat). **Cycle 67 AC06** — `KB_DISABLE_VECTORS=1` runtime kill-switch for hybrid search vector branch (BM25-only fallback). All env vars read at CALL TIME per cycle-19 L2 reload-leak hazard with truthy variants `{1,true,yes}` (case-insensitive).
- **Per-page write lock** (cycle 81 AC01-AC05) — `kb.utils.page_lock.page_lock(path, timeout=None)` is the canonical lock for wiki-page read→modify→write spans. Reentrant per (thread, page): the OUTERMOST acquisition delegates to `kb.utils.io.file_lock`, a nested same-thread same-page acquisition is a no-op. Depth lives in `threading.local()` keyed by `os.path.normcase(os.path.abspath(path))`, so cross-thread and cross-process exclusion are unchanged — `file_lock` itself stays non-reentrant and remains correct for non-page targets (manifest, log, contradictions, verdicts). **5 call sites**: `ingest/evidence.py:append_evidence_trail`, `ingest/pipeline.py:_update_existing_page_body`, `ingest/pipeline.py:_update_existing_page` (outer lock spanning body-write + evidence-append — this is the fix; pre-cycle-81 the lock was released and re-acquired between them), `compile/linker.py:inject_wikilinks{,_batch}`, and `review/refiner.py:refine_page` (cycle 82 — local named `page_lock_cm`, NOT `page_lock`, which would shadow the helper; manual `__enter__`/`__exit__` retained because the span has early returns; page-then-history order preserved). FW-1: when spying on locks in tests, patch `linker.page_lock` / `refiner.page_lock` for page acquisitions and `refiner.file_lock` for the history acquisition — the linker no longer holds a `file_lock` reference at all.
- **CLI subprocess** (cycle 68 AC01) — `kb.utils.cli_backend.call_cli` refactored to use `subprocess.Popen` with 2 daemon reader threads + separate stdin write thread; caps stdout at `MAX_CLI_STDOUT_BYTES` and stderr at `MAX_CLI_STDERR_BYTES` (64 KB); platform-aware terminate→kill grace (2.0s POSIX / 0.5s Windows). FW-1: never use `proc.communicate(input=...)` — stdin must be written on a separate thread.
- **Patch the owner module** for the four MCP-migrated callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`) — not `kb.mcp.core.*`.
- **Path safety** — `_validate_page_id` at MCP boundary (WIKI_DIR-anchored, with AC6/AC7/AC8 Windows-illegal-char + segment-aware `..` rejection); library calls use `_validate_path_under_project_root(path, field_name)` which re-raises as `ValidationError`. Cycle 65 AC9 added `kb.utils.path_safety._assert_under_project_root(path, field_name, *, require_exists, require_dir, dual_anchor, allow_symlinks)` as the dual-anchor primitive. Cycle 65 AC10 added `_open_no_follow(path)` + `_close_no_follow_fd(fd)` for `rebuild_indexes` TOCTOU mitigation (POSIX `O_NOFOLLOW` primary, Windows `is_symlink` defensive). See [docs/reference/error-handling.md](docs/reference/error-handling.md) for the full contract.
- **Config call-time accessors** (cycle 65 AC1-AC3 + cycle 67 AC01) — `kb.config.get_project_root()` resolves env (`KB_PROJECT_ROOT`) > monkeypatched binding (`kb.config.PROJECT_ROOT`) > heuristic at CALL time per cycle-19 L2 reload-leak. `get_model_tier(tier)` accessor for `MODEL_TIERS`. **Cycle 67 AC01** — `MODEL_TIERS` is now a `_ModelTiersView(collections.abc.Mapping)` instance: bracket access (`MODEL_TIERS["scan"]`) delegates to `get_model_tier()` so reads happen at CALL TIME (was import-time-captured dict pre-cycle-67). All Mapping methods (`.keys()`, `.values()`, `.items()`, `dict(view)`, `==` content compare) work env-dynamically. `get_allowed_domains()` reads `KB_AUGMENT_ALLOWED_DOMAINS` first (KB_-prefixed) then unprefixed `AUGMENT_ALLOWED_DOMAINS` for back-compat. PEP 562 `__getattr__` shim re-routes `kb.config.AUGMENT_ALLOWED_DOMAINS` → `get_allowed_domains()`.
- **MCP error boundary** (cycle 65 AC21) — `kb.mcp._error_boundary._mcp_error_boundary` decorator wraps every `@mcp.tool()` in `mcp/{core,ingest,quality}.py` with `try/except → return f"Error: {sanitize_error_text(exc)}"` for uniform sanitization. NOT applied to `mcp/{browse,compile,health}.py` per OOS-3 (these have their own error handling).
- **Wiki-context boundary fence** (cycle 70 AC11 + cycle 71 AC01-AC04 + cycle 72 AC01-AC05 + cycle 73 AC01) — `kb.utils.text.wrap_wiki_context(text)` wraps wiki content with `<wiki_context>...</wiki_context>` tags + system-prompt-style assertion before LLM injection. Mirrors the cycle-7 AC23 `wrap_purpose` pattern. Empty input short-circuits to `""` (T4); literal `</wiki_context>` substrings escaped to `</wiki-context>` (T3). **13 in-scope sites** (cycle 70: 2 + cycle 71: 4 + cycle 72: 6 + cycle 73: 1): cycle-70 `query/engine.py:1063` (synthesis prompt combined context) + `mcp/core.py:417-432` (Claude Code mode response); cycle-71 `mcp/browse.py:_format_search_results` (kb_search per-snippet + R2-F1 title) + `mcp/browse.py:kb_read_page` (body wrap + R2 char-cap reservation, footer-before-wrap order) + `lint/semantic.py:build_fidelity_context` (single fence Q2 A1 around page+sources, with `_render_sources(...,*,budget=...)` plumb + R2-F2 `sanitize_extraction_field(source['path'])`) + `lint/augment/proposer.py:_relevance_score` (R2-F3 empty-input early-return + wrap on `extracted_text`); cycle-72 `lint/semantic.py:_cap_page_content` (AC01: `paired['page_content']` cap at `QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD` before assembly in `build_fidelity_context`) + `review/context.py:build_review_context` (AC02: single outer `wrap_wiki_context` fence covering page body + N sources with markdown sub-headers — replaces cycle-1 H14 `<wiki_page_body>`/`<raw_source_N>` literals) + `review/context.py:build_review_checklist` (AC02a: atomic checklist text update referencing `<wiki_context>` token — T3 InformationDisclosure mitigation) + `lint/augment/orchestrator.py:_build_pre_extract_prompt` (AC03: helper extraction at L368, replaces literal `<untrusted_source>` sentinel) + `lint/augment/proposer.py:_relevance_score` (AC05: `sanitize_extraction_field(stub_title)` BEFORE `!r` repr-quote — keeps `!r` as defense-in-depth); **cycle-73 `lint/semantic.py:build_completeness_context`** (AC01: same-class peer of cycle-72 `build_fidelity_context` — closes cycle-72 §T1 OOS deferral; same `_cap_page_content` + header/body/closing triplet + `_render_sources` budget-plumb pattern; inherits cycle-72 R2 Codex M-1 marker reservation). **AC04 supplement** — `lint/semantic.py:build_consistency_context` per-page wrap_wiki_context fence (Approach A) with new module-level constant `_MAX_CONSISTENCY_WRAPPED_PAGE_CHARS = MAX_CONSISTENCY_PAGE_CONTENT_CHARS - _FENCE_OVERHEAD` (option (b) per design-decision: `kb.config.MAX_CONSISTENCY_PAGE_CONTENT_CHARS` stays at 4096; option (a) modify-in-place would have caused circular import). Callers reserve `_FENCE_OVERHEAD` from any context budget (T5); cycle-71 `kb_read_page` adds `_MAX_TRUNCATION_FOOTER_BYTES=200` reservation so the truncation footer fits within `QUERY_CONTEXT_MAX_CHARS` total. **All 6 cycle-72+/cycle-73+ deferred peers shipped** — 5 in cycle-72 (AC01-AC05) + 1 in cycle-73 (`build_completeness_context` AC01); the 3 cycle-74+ deferred entries (`max_keys` DoS bound, `proposer.py` same-class peer expansion, required-keys enforcement) SHIPPED cycle 74 — see the Tier-boundary verifier bullet.
- **Verdict-store prompt-shape stamp** (cycle 73 AC02) — `kb.config.CURRENT_PROMPT_VERSION = 1` constant; `kb.lint.verdicts.add_verdict` writes `prompt_version: int` field on every new entry; `kb.lint.verdicts.get_prompt_version(entry)` accessor returns 0 for legacy entries (default), defensively returns 0 on non-dict / non-int / bool (forensic safety). `load_verdicts` UNCHANGED — no cache mutation per T7 cache-fidelity invariant. Closes cycle-72 §T7 Repudiation forensic gap. Investigators distinguish: prompt_version=0 → pre-cycle-70 H14 literal-sentinel family; prompt_version=1 → post-cycle-70 wrap_wiki_context family (cycle-71/72/73 expansions all stamp 1).
- **Evidence-resolvability check** (cycle 86 AC01) — `kb.lint.checks.evidence_resolvable.check_evidence_resolvable(wiki_dir=None, raw_dir=None, pages=None) -> list[dict]`, registered in `run_all_checks` directly after `check_source_coverage` (the two are inverse directions of the same page↔raw relation and share the `shared_pages` scan). Asserts every file-shaped `source:` frontmatter entry resolves to a real file under `raw/`. **Severity is split**: a ref that resolves under `raw/` but finds no file is a `warning` (a raw source can legitimately be pruned after ingest — `error` would flip `kb lint`'s exit code repo-wide); a ref that does not resolve under `raw/` at all is an `error` (never legitimate). **Cycle 87 AC03** — the existence check is `_is_regular_file_no_follow(path)` (an `os.lstat` + `S_ISREG` test), NOT `Path.is_file()`: containment is decided against the resolved path, so a separate following stat let a final-component symlink swapped in afterwards redirect it outside `raw/`. DESIGN-AMEND vs the backlog's `_open_no_follow` + `fstat` shape — `lstat` opens nothing, needs no platform branch, and does not misread `ENOENT` as "O_NOFOLLOW unsupported". Closes the FINAL-component swap only; an ancestor-directory swap needs `openat2(RESOLVE_BENEATH)` (Linux 5.6+). **T1**: out-of-tree refs are reported WITHOUT being stat'd — `_resolve_evidence_ref` returns `None` on a containment failure and callers must NOT probe it, otherwise lint output becomes a filesystem-existence oracle over LLM-written frontmatter. `http(s)://` refs are skipped, not flagged. `_EVIDENCE_REFS_PER_PAGE_CAP = 200` bounds per-page work and emits its own `evidence_refs_truncated` notice. FW-1: `run_all_checks` now returns **13** entries in `checks_run`; the enumeration-order pin in `tests/test_lint.py` lists `evidence_resolvable` between `source_coverage` and `wikilink_cycles`.
- **Atomic-write durability** (cycle 86 AC04 + cycle 87 AC01/AC02) — `kb.utils.io.durable_replace(tmp, dest)` is the CANONICAL promote path: it performs the rename AND the platform-appropriate durability barrier. **4 call sites**: `atomic_json_write`, `_atomic_text_write_replace`, `capture.py:_write_item_files`, `query/embeddings.py:rebuild_vector_index` (the last two were bare `os.replace` with no barrier at all until cycle 87 AC02). **POSIX** — `os.replace` then `_fsync_parent_dir(dest.parent)`; `_flush_and_fsync` makes the temp file's CONTENTS durable but not the RENAME (ext4 `data=writeback`, XFS and several network filesystems keep the directory entry in a separate metadata stream). That barrier is best-effort on purpose: it tolerates `_FSYNC_UNSUPPORTED_ERRNOS` with a WARNING but RAISES on genuine storage failure (`EIO`/`ENOSPC`), unlike `_flush_and_fsync` which raises on everything. **Windows** — `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH` via ctypes; `_fsync_parent_dir` is NOT called (it is a documented no-op on `nt`). CPython's `os.replace` passes only `MOVEFILE_REPLACE_EXISTING`, so the pre-cycle-87 claim that it provided rename durability was false. **Two rejected shapes** (both design reviewers, independently): post-replace fsync of the DESTINATION file is durability theatre — `FlushFileBuffers` flushes the file's data and MFT record, not the parent directory index carrying the name — and falling back to `os.replace` on a failed write-through move converts a durability failure into a successful-looking write. **Cycle 87 R1** — `durable_replace` is NOT atomic from the caller's side the way `os.replace` was: the POSIX barrier runs AFTER the rename, so a genuine storage failure there raises with the rename already done. That case raises `kb.utils.io.RenameCompletedBarrierError(OSError)` so all-or-nothing callers can undo it — `capture._write_item_files` unlinks the final on it, or an orphan `<slug>.md` survives a capture reported as `([], error)`. **Two variants, and the split is load-bearing**: `durable_replace` OVERWRITES (tmp→final promotes, where that is the contract); `durable_rename` REFUSES to clobber (`wiki_log.rotate_if_oversized`'s ordinal loop exists to not destroy an existing archive, and the augment consumed-proposal name is unique only to 8 run-id chars). Cycle-87 R1 routed both no-clobber sites onto `durable_replace` and silently swapped their collision semantics; R2 caught it. **6 call sites**: the 4 above plus `lint/augment/orchestrator.py` (proposal consumption — a reverted rename makes `persister.py` write a DUPLICATE raw article, not just re-consume) and `utils/wiki_log.py:rotate_if_oversized`. FW-1: `durable_replace` is the ONLY platform-agnostic promote seam — tests that fault-inject or spy at `Path.replace` / `os.replace` silently observe nothing on Windows. FW-2: `_use_windows_write_through()` is the platform predicate so both branches are testable on one platform; never monkeypatch `os.name` instead, because `pathlib.Path` picks its flavour from it and every `Path(...)` in the call stack then raises `UnsupportedOperation`.
- **Rollback-and-durability reporting** (cycle 88 AC01-AC03) — `RenameCompletedBarrierError` means "the write LANDED but is not durability-guaranteed", so callers must not report it as a failed write. **`review/refiner.py`** catches it BEFORE the broad `except OSError` and records `status: "applied"` + `durable: False` + `durability_error`; `refine_page` returns `durable: False` + `warning` with `updated: True` and NO `error` key. **Catch ordering is load-bearing** — the barrier type subclasses `OSError`, same hazard as `ValueDomainError` before `TierBoundaryError`. `status` ("did it land?") and `durable` ("will it survive power loss?") are deliberately SEPARATE axes, not a fourth status value, so `sweep_stale_pending`'s pending-only logic is untouched; both fields appear ONLY on the not-durable path (absence = no caveat, per the `get_prompt_version` legacy-default convention). **`capture.py`** — `_rollback_finalized` / `_rollback_reservations` RETURN the paths whose unlink failed (they no longer only log), the completed-promote orphan unlink feeds the same list, and `_finish_rollback(captures_dir, survivors, *, attempted)` takes one directory fsync then appends `ROLLBACK_INCOMPLETE_MARKER` naming survivors, so `([], error)` no longer conflates "nothing was written" with "batch state unknown". `attempted`-gating prevents an fsync failure from manufacturing an indeterminacy report for a rollback that deleted nothing. **FW-1: the AC02 barrier is POSIX-only** — `_fsync_parent_dir` no-ops on `nt` and there is no cheap Win32 equivalent (`DeleteFileW` has no write-through flag; `FlushFileBuffers` is unsupported on a directory handle), so do NOT describe the rollback deletions as durable on Windows; the indeterminacy report is the cross-platform half. Residual filed in BACKLOG. **AC03** adds Windows junction (`mklink /J`, no privileges needed unlike symlinks' `WinError 1314`) + hardlink coverage for `_is_regular_file_no_follow`; note a junction left IN PLACE under `raw/` is caught earlier by the containment check as an `error` and never stat'd (T1 no-oracle) — only a post-resolution swap reaches the stat.

- **Tier-boundary verifier** (cycle 73 AC03+AC04 + cycle 74 AC01-AC03 + cycle 86 AC02) — `kb.lint.augment.tier_boundary._validate_tier_boundary(scan_output, *, expected_keys, required_keys=frozenset(), allowed_values=None, max_depth=4, max_string_len=4096, max_keys=500) -> dict` re-gates scan-tier `_call_llm_json` outputs BEFORE orchestrate-tier consumption (rejects: non-dict root, root/nested dicts > 500 keys [cycle 74 AC01], extra keys not in expected_keys, missing required_keys [cycle 74 AC03], strings > 4096 chars, nesting > depth 4, unsupported value types). Cycle 74 AC02 moved the implementation into the leaf module `tier_boundary.py` (orchestrator imports proposer at module level → proposer couldn't import back); `orchestrator.py` re-exports both `_validate_tier_boundary` + `_TBV_ALLOWED_VALUE_TYPES` so the cycle-73 monkeypatch surface is unchanged. **4 call sites**: `orchestrator.py` auto_ingest pre-extract (cycle 73) + `proposer.py` `_propose_urls` / `_relevance_score` (cycle 74 AC02, fail-closed abstain / 0.0 with `tier_boundary_rejected:` marker) + `capture.py` `_extract_items_via_llm` (cycle 74 R1 Codex M-1, LOUD rejection — TierBoundaryError propagates; lazy import required: module-level would cycle `kb.capture → augment.__init__ → proposer → kb.lint.fetcher → kb.capture`). Anti-spoofing (T5): `expected_keys`/`required_keys` MUST be derived from local schema via `frozenset(schema['properties'].keys())` / `frozenset(schema.get('required', []))` — NEVER from `scan_output.keys()`. `kb.errors.TierBoundaryError(ValidationError)` exception subclasses `ValidationError` so legacy `except ValidationError` still catches; split-catch records distinct manifest reason `"tier_boundary_rejected: ..."` for forensic distinctness. **Cycle 86 AC02 adds the VALUE domain** — `allowed_values: Mapping[str, frozenset] | None` rejects out-of-vocabulary values on ROOT-LEVEL keys via the new `kb.errors.ValueDomainError(TierBoundaryError)` subclass, recording the distinct reason `"action_not_in_vocabulary: ..."`. Previously `{"action": "exfiltrate"}` passed (legal keys, legal shape) and each call site re-implemented the enum check by hand. **Catch ordering is load-bearing**: `except ValueDomainError` MUST precede `except TierBoundaryError`, or the subclass is swallowed by the parent and the forensic split collapses. The same T5 anti-spoofing rule applies — derive the set from the LOCAL schema (`frozenset(schema['properties'][key]['enum'])`, as `proposer._ACTION_VOCABULARY` does), NEVER from `scan_output`. A key in `allowed_values` but absent from `scan_output` is NOT a rejection (that is `required_keys`' job). Scope is root-level keys only; `capture.py`'s nested `items[].kind` / `confidence` enums are a documented BACKLOG scope-out. Closes cycle-72 §T8 EscalationOfPrivilege blast-radius gap; all 3 cycle-74+ deferred entries (max_keys R2 F-2, proposer peers R1 C2, required-keys R2 F-3) SHIPPED cycle 74.
- **Evidence Trail** — reverse-chronological, sentinel-guarded; sentinel is machine-maintained.
- **Release artifacts** — `SECURITY.md` (narrow-role CVE acceptance + disclosure path) + `.github/workflows/ci.yml` (ruff + pytest [strict, cycle 36] + pip-audit + build gate on ubuntu-latest; windows matrix deferred to cycle 37).
- **Doc update checklist** on push — see §Automation at bottom.

## Detailed Documentation

Detail moved out of this file lives in [`docs/reference/`](docs/reference/README.md). When you add cycle-level history, a new convention, or a new API, edit the relevant file there (it is the source of truth for its topic) and update this index only when a topic / file / heading itself changes. Per-topic depth lives in `docs/reference/`; CLAUDE.md stays slim.

| Topic | File |
|---|---|
| Architecture — 3-layer content, 5-ops cycle, Python package APIs, wiki index files | [docs/reference/architecture.md](docs/reference/architecture.md) |
| Module map — per-module breakdown of `src/kb/` | [docs/reference/module-map.md](docs/reference/module-map.md) |
| Implementation status — compact cycle history index (cycle 65) | [docs/reference/implementation-status.md](docs/reference/implementation-status.md) |
| Testing — pytest layout + fixture rules | [docs/reference/testing.md](docs/reference/testing.md) |
| Error handling conventions | [docs/reference/error-handling.md](docs/reference/error-handling.md) |
| Phase 2 workflows — Standard / Thorough Ingest, Deep Lint, Query | [docs/reference/workflows.md](docs/reference/workflows.md) |
| Conventions — base rules, Evidence Trail, Architecture Diagram Sync | [docs/reference/conventions.md](docs/reference/conventions.md) |
| MCP servers — kb tool catalogue + memory / arxiv / sqlite | [docs/reference/mcp-servers.md](docs/reference/mcp-servers.md) |
| Ingestion commands — web / PDF / video → markdown | [docs/reference/ingestion-commands.md](docs/reference/ingestion-commands.md) |
| Opus 4.7 behaviour notes + extraction templates | [docs/reference/opus-47-notes.md](docs/reference/opus-47-notes.md) |

## Working Principles

*(Adapted from [Karpathy's LLM coding observations](https://x.com/karpathy/status/2015883857489522876). Bias toward caution over speed on non-trivial work. For a one-line typo fix, use judgment.)*

**Think Before Coding.** Don't assume. Don't hide confusion. Surface tradeoffs.
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

**Goal-Driven Execution.** Transform imperative tasks into verifiable goals:
- "Fix the bug" → *"Write a failing test that reproduces it, then make it pass."*
- "Add validation" → *"Write tests for invalid inputs, then make them pass."*
- "Refactor X" → *"Ensure tests pass before and after."*
- For multi-step work, state the plan as `[step] → verify: [check]` — then loop.

**Two tests before declaring done:**
1. *Every changed line should trace directly to the request.* Drop drive-by edits.
2. *Would a senior engineer say this is overcomplicated?* If yes, simplify.

## Project

LLM Knowledge Base — a personal, LLM-maintained knowledge wiki inspired by [Karpathy's LLM Knowledge Bases pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The system compiles raw sources into structured, interlinked markdown rather than using RAG/vector retrieval.

**Philosophy:** Human curates sources and approves decisions; LLM handles all compilation, querying, maintenance, and coding.

## Development Commands

```bash
# Activate venv (ALWAYS use project .venv, never global Python)
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Environment setup
cp .env.example .env          # then fill in:
# ANTHROPIC_API_KEY (optional for Claude Code/MCP mode; required for direct API-backed flows), FIRECRAWL_API_KEY (optional), OPENAI_API_KEY (optional)
# Optional: override project root detection
export KB_PROJECT_ROOT=/path/to/your/kb    # heuristic + walk-up fallback if unset

# Install deps + editable package (enables `kb` CLI command)
# NOTE: `pip install -e .` must be run before `kb` CLI or `from kb import ...` works outside pytest
pip install -r requirements.txt && pip install -e .

# Run all tests
python -m pytest

# Run single test
python -m pytest tests/test_models.py::test_extract_wikilinks -v

# Lint, auto-fix, & format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/

# CLI (after pip install -e .)
kb --version
kb ingest raw/articles/example.md --type article
kb compile [--full]
kb query "What is compile-not-retrieve?"
kb lint [--fix]
kb evolve
kb publish [--out-dir PATH] [--format llms|llms-full|graph|all] [--incremental/--no-incremental]   # /llms.txt + /llms-full.txt + /graph.jsonld
kb rebuild-indexes [--wiki-dir PATH] [--yes]   # wipe manifest + vector DB + LRU caches
kb mcp                        # Start MCP server for Claude Code

# Playwright browser (needed by crawl4ai)
python -m playwright install chromium
```

Ruff config: line length 100, Python 3.12+, rules E/F/I/W/UP (see `pyproject.toml`).

## Model Tiering

| Tier | Model ID | Env Override | Use |
|---|---|---|---|
| `scan` | `claude-haiku-4-5` | `CLAUDE_SCAN_MODEL` | Index reads, link checks, file diffs — mechanical, low-reasoning |
| `write` | `claude-sonnet-5` | `CLAUDE_WRITE_MODEL` | Article writing, extraction, summaries — quality at reasonable cost |
| `orchestrate` | `claude-opus-4-8` | `CLAUDE_ORCHESTRATE_MODEL` | Orchestration, query answering, verification — highest reasoning |

For Opus 4.7 behaviour notes (CoT scaffolding, instruction following, parallel tool calls, 1M context) and the 10 extraction templates, see [docs/reference/opus-47-notes.md](docs/reference/opus-47-notes.md).

## Wiki Page Frontmatter Template

```yaml
---
title: "Page Title"
source:
  - "raw/articles/source-file.md"
created: 2026-04-05
updated: 2026-04-05
type: entity | concept | comparison | synthesis | summary
confidence: stated | inferred | speculative
# Cycle 14 AC1/AC2/AC23 — optional epistemic-integrity fields; absent is valid.
# belief_state: confirmed | uncertain | contradicted | stale | retracted
# authored_by: human | llm | hybrid
# status: seed | developing | mature | evergreen
---
```

**Optional epistemic fields (cycles 14-15):** `belief_state` is the cross-source aggregate (orthogonal to per-source `confidence`); `authored_by` formalises human vs LLM authorship; `status` tracks the page lifecycle. Query engine applies a +5% `STATUS_RANKING_BOOST` to pages with `status in (mature, evergreen)` and a mild `AUTHORED_BY_BOOST` to `authored_by: human|hybrid` when full metadata passes `validate_frontmatter`. Publish outputs (`kb publish`) skip pages with `belief_state in {retracted, contradicted}` OR `confidence == speculative`.

## Implementation History & Roadmap

- **Shipped:** see `CHANGELOG.md` (brief compact index, newest first — compact Items / Tests / Scope / Detail per cycle) and `CHANGELOG-history.md` (full per-cycle bullet-level archive). Format: [Keep a Changelog](https://keepachangelog.com/).
- **Open work:** see `BACKLOG.md` — severity levels CRITICAL → LOW, grouped by file. Resolved items are deleted (brief entry in `CHANGELOG.md`, detail in `CHANGELOG-history.md`); resolved phases collapse to a one-liner under "Resolved Phases".
- **Roadmap (Phase 5 deferred + Phase 6 cut):** see `BACKLOG.md` §"Phase 5 — Community followup proposals" and §"Phase 6 candidates". Includes the 2026-04-13 Karpathy-gist re-evaluation ("RECOMMENDED NEXT SPRINT") and all deferred features (inline claim tags, URL-aware ingest, semantic chunking, typed graph relations, autonomous research loop, etc.).
- **Latest-cycle notes:** see [docs/reference/implementation-status.md](docs/reference/implementation-status.md).

## Automation

No auto-commit hooks. Doc updates and commits are done manually when ready to push.

### BACKLOG.md lifecycle
Resolved items are **deleted** from `BACKLOG.md` (brief entry added to `CHANGELOG.md [Unreleased]` Quick Reference; full detail added to `CHANGELOG-history.md`). When all items in a phase section are resolved, the section collapses to a one-liner under "Resolved Phases" (e.g., `- **Phase 3.92** — all items resolved in v0.9.11`). This keeps the backlog focused on open work only.

### Doc update checklist (before push)
When asked to update docs, review `git diff` and update as needed:
- `CHANGELOG.md` — add compact Items / Tests / Scope / Detail entry under `[Unreleased]` Quick Reference (newest first)
- `CHANGELOG-history.md` — add full per-cycle bullet-level detail (newest first)
- `BACKLOG.md` — **delete** resolved items (never strikethrough); collapse empty phase sections
- `CLAUDE.md` — update Quick Reference numbers (version, tests, tools), Model Tiering table, frontmatter template, Detailed Documentation index. Detail edits go in the matching [docs/reference/](docs/reference/README.md) file.
- `docs/reference/*.md` — source of truth for each topic. Update the relevant file when content within a section changes (architecture, error handling, mcp-servers, etc.).
- `README.md` — update if user-facing features or setup changed
- `docs/architecture/architecture-diagram.html` + re-render PNG if architecture changed

All tools are auto-approved for this project (permissions in `settings.local.json`).
