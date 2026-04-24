# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

> **High-level index.** Keep this file brief and newest first. Each cycle gets compact Items / Tests / Scope / Detail fields and points to the full archive in [CHANGELOG-history.md](CHANGELOG-history.md).
> Cross-reference: [BACKLOG.md](BACKLOG.md) tracks open work; resolved items are deleted from BACKLOG once shipped here.

<!-- Entry rule — newest first; keep this file brief and move details to CHANGELOG-history.md.
#### YYYY-MM-DD — cycle N
- Items: <N> AC / <M> src / <K> commits
- Tests: A → B (+Δ)
- Scope:
  <one-sentence scope only>
- Detail: [history archive](CHANGELOG-history.md#<anchor>)

Commit-count convention (codified cycle 28 AC8 per cycle-26 L1 skill patch):
on the feature-branch squash-merge flow, the reported <K> equals pre-doc-update
branch commits + 1 for the landing doc-update that contains this changelog
line (self-referential). If R1/R2 PR review triggers fix commits, increment
<K> atomically with each fix commit and re-check `git log --oneline main..HEAD`
before push.
-->

## [Unreleased]

### Quick Reference

Newest first. `CHANGELOG.md` is the compact index; full detail lives in [CHANGELOG-history.md](CHANGELOG-history.md).

#### 2026-04-25 — cycle 32

- Items: 8 AC / 2 src (`cli.py`, `utils/io.py`) + 1 new test file / +TBD commits (post-merge backfill per cycle-30 L1)
- Tests: 2882 → 2901 (+19; Step 14 R1 Codex MAJOR 2 added stagger-integration pin)
- Scope:
  Closes CLI ↔ MCP parity category (b) — AC1/AC2 add `compile-scan`
  thin-wrapper over `kb_compile_scan` and AC4/AC5 add
  `ingest-content` over `kb_ingest_content` (both via the cycle
  27+ function-local-import pattern; `--incremental/--no-incremental`
  boolean flag pair matches cycle 15 `kb publish` precedent; Click
  `click.Path(exists=True, file_okay=False)` for `--wiki-dir`;
  Click `click.File("r", lazy=False, encoding="utf-8")` for
  `--content-file` + `--extraction-json-file` with native `-` stdin
  support per Context7-verified Click 8.3 semantics). AC3 widens
  `_is_mcp_error_response` tuple to include `"Error["` prefix,
  closing a silent-exit-0 bug where `kb_ingest_content`'s
  post-create OSError path (`Error[partial]: write to ... failed`
  at `mcp/core.py:762`) would have routed to stdout + exit 0 under
  the cycle-31 three-tuple; docstring updated with the full
  emitter map. AC6/AC7 add `utils/io.py` fair-queue stagger
  mitigation — module-level `_LOCK_WAITERS` counter guarded by
  `threading.Lock`, incremented via `_take_waiter_slot()` (0-based
  position snapshot) on entry to `file_lock` retry loop and
  decremented via `_release_waiter_slot()` in the outermost
  `finally` (C3 symmetry across success / TimeoutError /
  KeyboardInterrupt); first-sleep stagger is
  `position * _FAIR_QUEUE_STAGGER_MS / 1000` clamped to
  `LOCK_POLL_INTERVAL=50ms` (C11 prevents double-compounding with
  exponential backoff); position=0 → zero stagger so uncontended
  N=1 acquire sees no latency change; `_release_waiter_slot`
  emits `logger.warning` on underflow (C14, post-R1 Opus AMEND)
  instead of silently clamping to zero so counter drift surfaces
  to operators. AC8 doc sync updates CLI count 22 → 24 and
  deletes the BACKLOG fair-queue entry (lines 125-126) since AC6
  resolves it as a mitigation. Step-2 CVE baseline showed 2 open
  no-upstream-fix advisories (diskcache, ragas); Step-11 PR-CVE
  diff surfaced 3 mid-cycle arrivals per cycle-22 L4: litellm
  GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc (patched at 1.83.7
  but blocked by click<8.2 transitive — narrow-role exception
  documented in BACKLOG since zero runtime imports in `src/kb/`),
  python-dotenv CVE-2026-28684 (fixed via 1.1.1 → 1.2.2 already
  pinned in requirements.txt), pip CVE-2026-3219 (no upstream fix
  yet — tooling-only narrow-role). R1 Opus AMEND verdict (AC5
  add --use-api test, AC6 observable-warning on underflow, AC8
  explicit T11 BACKLOG filing); R2 Codex design-eval stopped
  past 12 min hang (cycle-20 L4) — primary-session manual
  verify caught `core.py:535` misread of `MAX_INGEST_CONTENT_CHARS*4`
  as a JSON-overhead ratio (actually UTF-8 bytes-per-char
  upper bound). Step 5 Opus decision gate hung past 10 min;
  primary-session synthesis per cycle-20 L4 fallback. Step 8
  Codex plan-gate hung past 8 min; primary-session self-review
  per cycle-21 L1 inline-resolve (all conditions grep-verifiable,
  no code-exploration gaps).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-32-2026-04-25)

#### 2026-04-25 — cycle 31

- Items: 8 AC / 1 src (`cli.py`) + 1 new test file / 9 commits (post-merge backfill per cycle-30 L1)
- Tests: 2850 → 2882 (+32)
- Scope:
  Continues cycle-27/30 CLI ↔ MCP parity — AC1-AC3 add
  `read-page` / `affected-pages` / `lint-deep` thin-wrappers
  over the three page_id-input MCP tools (`kb_read_page`,
  `kb_affected_pages`, `kb_lint_deep`). These tools emit
  heterogeneous error-prefix shapes (`"Error:"` colon-form,
  `"Error <verb>..."` space-form runtime-exception shapes, and
  the unique `"Page not found:"` logical-miss from `kb_read_page`),
  so AC4 introduces a shared `_is_mcp_error_response(output)`
  discriminator near `_error_exit` that classifies by first-line
  prefix only against the three shapes (Q1; first-line split
  prevents misfire on page bodies containing `Error:` on line 2;
  empty / blank-first-line outputs stay exit-0 to preserve MCP
  parity for zero-length page bodies). AC5 pins body-spy tests
  per subcommand (patching the OWNER module `kb.mcp.browse` /
  `kb.mcp.quality` — NOT `kb.cli` — because function-local
  imports resolve at call time per cycle-30 L2). AC6 adds
  traversal-boundary tests (`".."` → validator colon-form error)
  PLUS non-colon boundary tests per subcommand (`Page not found:`
  for read-page; forced `build_backlinks` / `build_fidelity_context`
  exceptions for affected-pages / lint-deep) — revert-divergent
  by construction: the tests flip `exit_code` from 1 to 0 if the
  discriminator reverts to `startswith("Error:")`. Q3 parity
  tests exercise both channels (direct MCP call + CLI invocation)
  with strict stream semantics (`stdout == mcp_output + "\n"` on
  success, `stderr == mcp_output + "\n"` + exit 1 on error;
  `CliRunner()` alone suffices on Click 8.3+ since `mix_stderr`
  was removed in 8.2). AC8 closes a pre-existing silent-failure
  bug latent since cycles 27 (`stats`) and 30 (`reliability-map`,
  `lint-consistency`): all three legacy wrappers wrap MCP tools
  that also emit non-colon runtime-error shapes, so AC8
  retrofits them to `_is_mcp_error_response` (one-line swap each
  plus 3 regression tests). T6 boot-lean pinned by subprocess
  probe asserting `import kb.cli` doesn't transitively pull
  `kb.mcp.browse` / `kb.mcp.quality`. AC7 BACKLOG hygiene —
  remove cluster (b) from the CLI↔MCP parity bullet; narrow
  "~12 remaining" to "~9 remaining" (7 write-path + 2 ingest/
  compile variants). Step-2 CVE baseline + Step-11 branch diff
  show identical 2 open no-upstream-fix CVEs (diskcache + ragas)
  — Step 11.5 no-op. R1 Opus APPROVE-WITH-AMENDS; R2 Codex AMEND
  (discovered the pre-existing silent-failure bug — scope
  expanded to AC8 via Step-5 Q4 Option A); Step 5 APPROVE; Step 8
  plan-gate REJECT resolved inline per cycle-21 L1.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-31-2026-04-25)

#### 2026-04-25 — cycle 30

- Items: 7 AC / 2 src + 2 new test files / 12 commits
- Tests: 2826 → 2850 (+24)
- Scope:
  Pre-Phase-5 backlog hygiene — AC1 `_audit_token` caps
  `block["error"]` at 500 chars via `kb.utils.text.truncate`
  (truthiness-guarded: `None`/empty skips the cap and keeps the
  bare `"cleared"`/`"unknown"` token; R2-A2 amendment) so a
  pathological `OSError.__str__()` on Windows can't bloat
  `wiki/log.md` or `kb rebuild-indexes` CLI stdout. AC2-AC6
  extend cycle-27's CLI ↔ MCP parity with 5 read-only
  subcommands — `graph-viz` (`--max-nodes` help text documents
  "1-500; 0 rejected" per R1 Opus amendment), `verdict-trends`,
  `detect-drift`, `reliability-map` (zero args; "No feedback
  recorded yet" exits 0), `lint-consistency` (`--page-ids`
  forwarded raw; no `--wiki-dir` since the MCP tool signature
  omits it). All 5 wrappers use the cycle-27 thin-wrapper
  pattern (function-local import + forward args raw +
  `"Error:"`-prefix contract + `_error_exit(exc)` wrap). AC7
  BACKLOG hygiene — delete cycle-29 audit-cap MEDIUM entry +
  narrow CLI↔MCP parity from "~14 remaining" to "~12 remaining"
  (R2-A3 arithmetic correction + `kb_save_synthesis` non-tool
  call-out); skip no-op CVE re-verify (diskcache + ragas
  identical cycle-29 baseline, same-day). R2 Codex stalled
  ~14min; primary-session R2 fallback per cycle-20 L4 then
  R2 findings folded in via DESIGN-AMEND.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-30-2026-04-25)

#### 2026-04-24 — cycle 29

- Items: 5 AC / 3 src + 2 new test files / 6 commits
- Tests: 2809 → 2826 (+17)
- Scope:
  Backlog-by-file hygiene cycle. AC1 `_audit_token(block)` helper in
  `compile/compiler.py` replaces the inline audit ternary so a partial
  vector clear (main `unlink()` succeeded + sibling `.tmp` unlink failed)
  renders `vector=cleared (warn: tmp: <msg>)` instead of swallowing the
  error tail; mirrored to `kb rebuild-indexes` CLI stdout via function-
  local import in `cli.py` (cycle-23 AC4 boot-lean preserved); Q3
  embedded-newline regression pins the `append_wiki_log` sanitizer
  contract. AC2 `_validate_path_under_project_root(path, field_name)`
  helper applies the dual-anchor `PROJECT_ROOT` containment (literal-abs
  + `.resolve()` target both under root) to `hash_manifest` + `vector_db`
  overrides of `rebuild_indexes`; void-return helper (cycle-23 L2) with
  explicit empty-path reject (cycle-19 L3); wiki_dir block refactored to
  use the same helper so all 3 sites share one contract. AC3 architectural
  carve-out comment above `CAPTURES_DIR = RAW_DIR / "captures"` (5 lines,
  mirrors CLAUDE.md §raw/ language) + deletes stale `config.py:40-53`
  BACKLOG bullet (Q13 expansion — BACKLOG lifecycle). AC4 deletes stale
  `_PROMPT_TEMPLATE inline string` BACKLOG bullet (shipped cycle-19 AC15
  via lazy `_get_prompt_template()`). AC5 deletes stale Phase 4.5 HIGH #6
  cold-load bullet ("0.81s + 67 MB RSS delta") — shipped cycle-26 AC1-AC5
  warm-load + cycle-26/28 observability; HIGH-Deferred summary with the
  true residual (dim-mismatch AUTO-rebuild) survives. Step-11 T1 PARTIAL
  (unbounded `OSError.__str__()` → `wiki/log.md` + CLI stdout) filed as
  new MEDIUM BACKLOG entry per cycle-12 L3. Dep-CVE baseline 2026-04-24:
  diskcache + ragas both `fix_versions: []`, unchanged; PR-introduced
  diff empty.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-29-2026-04-24)

#### 2026-04-24 — cycle 28

- Items: 9 AC / 2 src + 1 new test file / 7 commits
- Tests: 2801 → 2809 (+8)
- Scope:
  First-query observability completion — `VectorIndex._ensure_conn`
  sqlite-vec extension load and `BM25Index.__init__` corpus indexing
  (closes HIGH-Deferred sub-item (b), cycle-26 Q16 follow-up). AC1/AC2/AC3:
  `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS=0.3` module constant +
  `_sqlite_vec_loads_seen` counter (exact, inside `_conn_lock`) +
  `get_sqlite_vec_load_count()` getter; INFO log always on successful
  extension load + WARNING above 0.3s; post-success ordering (NO
  `finally:` wraps the log/counter — defended by
  `test_sqlite_vec_load_no_info_on_failure_path`). AC4/AC5: lock-free
  `_bm25_builds_seen` counter (aggregates `engine.py:110` wiki +
  `engine.py:794` raw call sites — "constructor executions, NOT distinct
  cache insertions" per Q11) + `get_bm25_build_count()` getter; INFO
  log on every `BM25Index.__init__` including empty-corpus (no WARN
  threshold — corpus-size variance defeats a fixed threshold). AC6:
  8 regression tests. AC7: BACKLOG hygiene — narrow HIGH-Deferred entry
  (sub-item b landed), delete MEDIUM AC17-drop rationale line (duplicate
  of CHANGELOG-history cycle-13 AC2), delete resolved LOW cycle-27
  commit-tally entry. AC8: CHANGELOG format-guide commit-count rule
  codified (self-referential +1 per cycle-26 L1 skill patch). AC9:
  no-op CVE re-verify, matches cycle-26 baseline (diskcache + ragas
  still no upstream fix).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-28-2026-04-24)

#### 2026-04-24 — cycle 27

- Items: 7 AC / 2 src + 1 new test file / 3 commits
- Tests: 2790 → 2801 (+11)
- Scope:
  CLI ↔ MCP parity — 4 new read-only CLI subcommands (`kb search`,
  `kb stats`, `kb list-pages`, `kb list-sources`) wrapping existing MCP
  browse tools with function-local imports (AC1/AC2/AC3/AC4 — preserves
  cycle-23 AC4 boot-lean contract). AC1b extracts `_format_search_results`
  helper from `kb_search` body so CLI reuses identical formatter without
  duplication. AC5: 7 regression tests (4 `--help` smoke + empty-query
  non-zero-exit + 2 helper semantics). AC6 narrows BACKLOG CLI↔MCP parity
  entry (18 → 14 remaining tools). AC7 skip-on-no-diff CVE re-verify
  (pip-audit matches cycle-26 baseline, same-day noise avoidance).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-27-2026-04-24)

#### 2026-04-24 — cycle 26

- Items: 8 AC (+AC2b) / 2 src + 1 new test file + 1 extended cycle-23 test / 7 commits
- Tests: 2782 → 2790 (+8)
- Scope:
  Vector-model cold-load observability — new `maybe_warm_load_vector_model(wiki_dir)`
  daemon-thread warm-load hook wired into `kb.mcp.__init__.main()` after tool
  registration, before stdio loop (AC1/AC2); boot-lean allowlist extension pins
  function-local import contract (AC2b); `_get_model()` instrumented with
  `time.perf_counter` — INFO log always on cold-load + WARNING above
  `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS=0.3s` (AC3); module-level
  `_vector_model_cold_loads_seen` counter + `get_vector_model_cold_load_count()`
  getter, exact counts inside `_model_lock` (AC4 — intentional asymmetry
  vs cycle-25 lock-free `_dim_mismatches_seen`, documented in getter docstring);
  seven regression tests including subprocess sys.modules probe + exception-
  swallow pin (AC5); BACKLOG hygiene — delete stale multiprocessing file_lock
  entry (AC6 — resolved by cycle-23 AC7), skip no-op CVE re-stamp (AC7 —
  pip-audit matches cycle-25 baseline), narrow HIGH-Deferred vector-index
  lifecycle entry + add Q16 follow-up (AC8).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-26-2026-04-24)

#### 2026-04-24 — cycle 25

- Items: 10 AC / 2 src + 3 new test files / 6 commits
- Tests: 2768 → 2782 (+14)
- Scope:
  `rebuild_indexes` also unlinks `<vec_db>.tmp` sibling (AC1/AC2 —
  cycle-24 R2 Codex follow-up); vector-index dim-mismatch warning now
  includes operator remediation command + module-level observability
  counter (AC3/AC4/AC5 — HIGH-Deferred sub-item 3 narrow-scope shipped,
  auto-rebuild remains deferred); `compile_wiki` emits `in_progress:{hash}`
  pre-markers before each `ingest_source`, stale-marker entry scan on
  next invocation warns per-source, full-mode prune exempts in_progress
  values (AC6/AC7/AC8 + CONDITION 13 — MEDIUM M2 narrow observability
  variant); BACKLOG + diskcache/ragas CVE 2026-04-24 re-verify (AC9/AC10).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-25-2026-04-24)

#### 2026-04-23 — cycle 24

- Items: 15 AC / 4 src + 5 new test files / 9 commits
- Tests: 2743 → 2768 (+25)
- Scope:
  Evidence-trail inline render at first write + StorageError on update-path
  evidence failure (AC1/AC2); `append_evidence_trail` sentinel search
  section-span-limited against attacker-planted body sentinels (AC14/AC15);
  vector-index atomic rebuild via `<vec_db>.tmp` + `os.replace` with
  cache-pop+close before replace and crash-cleanup (AC5/AC6/AC7/AC8);
  `file_lock` exponential backoff across all 3 polling sites with
  `LOCK_POLL_INTERVAL` as CAP (AC9/AC10); BACKLOG cleanup +
  diskcache/ragas CVE re-verification (AC11/AC12/AC13).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-24-2026-04-23)

#### 2026-04-23 — cycle 23

- Items: 8 AC / 6 src + 4 new tests / 6 commits
- Tests: 2725 → 2743 (+18)
- Scope:
  MCP boot-leanness via PEP-562 lazy shim (cycle-19 AC15 contract preserved),
  `rebuild_indexes` helper + `kb rebuild-indexes` CLI for clean-slate recompiles,
  hermetic ingest→query→lint E2E coverage, and cross-process `file_lock`
  regression (Phase 4.5 HIGH-Deferred).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-23-2026-04-23)

#### 2026-04-22 — cycle 22

- Items: 14 AC / 3 src + 2 new tests / 11 commits
- Tests: 2720 → 2725 (+5; 1 Windows-skip)
- Scope:
  Pre-Phase-5 backlog hardening: wiki-path ingest guard, universal extraction grounding clause,
  behavioural prompt test rewrite, stale BACKLOG cleanup, and lxml CVE pin bump.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-22-2026-04-22)

#### 2026-04-21 — cycle 21

- Items: 30 AC / 4 src / 1 commit
- Tests: 2697 → 2710 (+13)
- Scope:
  CLI subprocess backend for 8 local AI tools, with env-var routing, JSON extraction, per-backend
  concurrency limits, secret redaction, and Anthropic path compatibility.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-21-2026-04-21)

#### 2026-04-21 — cycle 20

- Items: 21 AC / 10 src / 13 commits
- Tests: 2639 → 2697 (+58)
- Scope:
  Error taxonomy, slug-collision O_EXCL hardening, locked page updates, stale-refine sweep/list
  tools, CLI/MCP refine surfaces, and Windows tilde-path regression coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-20-2026-04-21)

#### 2026-04-21 — cycle 19

- Items: 23 AC / 6 src / 9 commits
- Tests: 2592 → 2639 (+47)
- Scope:
  Batch wikilink injection, manifest-key consistency, refine two-phase writes, stale-pending
  visibility, MCP monkeypatch migration, and reload-leak fixes.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-19-2026-04-21)

#### 2026-04-21 — cycle 18

- Items: 16 AC / 5 src / 6 commits
- Tests: 2548 → 2592 (+44)
- Scope:
  Structured ingest audit log, locked wikilink injection, log rotation under lock, UNC sanitization,
  index-file helper, HASH_MANIFEST test redirection, and e2e workflow coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-18-2026-04-21)

#### 2026-04-20 — cycle 17

- Items: 16 AC / 11 src / 14 commits
- Tests: 2464 → 2548 (+84)
- Scope:
  manifest lock symmetry, capture two-pass, lint augment resume, shared run-id validator, MCP lazy
  imports (narrowed), thin-tool coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-17-2026-04-20)

#### 2026-04-20 — cycle 16

- Items: 24 AC / 8 src / 14 commits
- Tests: 2334 → 2464 (+130)
- Scope:
  enrichment targets, query rephrasings, duplicate-slug + inline-callout lint, kb_query `save_as`,
  per-page siblings + sitemap publish
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-16-2026-04-20)

#### 2026-04-20 — cycle 15

- Items: 26 AC / 6 src / 7 commits
- Tests: 2245 → 2334 (+89)
- Scope:
  authored-by boost, source volatility, per-source decay, incremental publish, lint decay/status
  wiring
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-15-2026-04-20)

#### 2026-04-20 — cycle 14

- Items: 21 AC / 9 src / 8 commits
- Tests: 2140 → 2235 (+95)
- Scope:
  Epistemic-Integrity 2.0 vocabularies, coverage-confidence refusal gate, `kb publish` module
  (/llms.txt, /llms-full.txt, /graph.jsonld), status ranking boost
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-14-2026-04-20)

#### 2026-04-20 — cycle 13

- Items: 8 AC / 5 src / 7 commits
- Tests: 2119 → 2131 (+12)
- Scope:
  frontmatter migration to cached loader, CLI boot `sweep_orphan_tmp`, `run_augment` raw_dir
  derivation
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-13-2026-04-20)

#### 2026-04-19 — cycle 12

- Items: 17 AC / 13 src / 11 commits
- Tests: 2089 → 2118 (+29)
- Scope:
  conftest fixture, io sweep, `KB_PROJECT_ROOT`, LRU frontmatter cache, `kb-mcp` console script
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-12-2026-04-19)

#### 2026-04-19 — cycle 11

- Items: 14 AC / 14 src / 13 commits
- Tests: 2041 → 2081 (+40)
- Scope:
  ingest coercion, comparison/synthesis reject, page-helper relocation, CLI import smoke,
  stale-result edges
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-11-2026-04-19)

#### 2026-04-18 — cycle 10

- Items: 14 AC / 10 src
- Tests: 2004 → 2041 (+37)
- Scope:
  MCP `_validate_wiki_dir` rollout, `kb_affected_pages` warnings, `VECTOR_MIN_SIMILARITY` floor,
  capture hardening
- Detail: [history archive](CHANGELOG-history.md#backlog-by-file-cycle-10-2026-04-18)

#### 2026-04-18 — cycle 9

- Items: 30 AC / 14 src
- Tests: 1949 → 2003 (+54)
- Scope:
  wiki_dir isolation across query/MCP, LLM redaction, env-example docs, lazy ingest export
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-9-2026-04-18)

#### 2026-04-18 — cycle 8

- Items: 30 AC / 19 src
- Tests: 1919 → 1949 (+30)
- Scope:
  model validators, LLM telemetry, PageRank → RRF list, contradictions idempotency, pip toolchain
  CVE patch
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-8-2026-04-18)

#### 2026-04-18 — cycle 7

- Items: 30 AC / 22 src
- Tests: 1868 → 1919 (+51)
- Scope:
  `_safe_call` helper, MCP error-path sanitization, Evidence Trail convention, many
  lint/query/ingest refinements
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-7-2026-04-18)

#### 2026-04-18 — cycle 6

- Items: 15 AC / 14 src
- Tests: 1836 → 1868 (+32)
- Scope:
  PageRank cache, vector-index reuse, CLI `--verbose`, hybrid rrf tuple storage, graph
  `include_centrality` opt-in
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-6-2026-04-18)

#### 2026-04-18 — cycle 5 redo

- Items: 6 AC / 6 src
- Tests: 1821 → 1836 (+15)
- Scope:
  pipeline retrofit for Steps 2/5 artifacts; citation format symmetry, page-id SSOT,
  purpose-sentinel coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-5-redo-hardening-2026-04-18)

#### 2026-04-18 — cycle 5

- Items: 14 AC / 13 src
- Tests: 1811 → 1820 (+9)
- Scope:
  `wrap_purpose` sentinel, pytest markers, verdicts/config consolidation, `_validate_page_id`
  control-char reject
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-5-2026-04-18)

#### 2026-04-18 — PR #17 concurrency

- Items: 3 files
- Tests: 1810 → 1811 (+1)
- Scope:
  `_VERDICTS_WRITE_LOCK` fix + capture docstring clarity; CHANGELOG split into active vs history
- Detail: [history archive](CHANGELOG-history.md#concurrency-fix--docs-tidy-pr-17-2026-04-18)

#### 2026-04-17 — cycle 4

- Items: 22 AC / 16 src
- Tests: 1754 → 1810 (+56)
- Scope:
  `_rel()` path-leak sweep, `<prior_turn>` sentinel sanitizer, kb_read_page cap, rewriter CJK gate,
  BM25 postings index
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-4-2026-04-17)

#### 2026-04-17 — cycle 3

- Items: 24 AC / 16 src
- Tests: 1727 → 1754 (+27)
- Scope:
  `LLMError.kind` taxonomy, vector dim guard + lock, stale markers in context, hybrid catch-degrade,
  inverted-postings consistency
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-3-2026-04-17)

#### 2026-04-17 — cycle 2

- Items: 30 AC / 19 src
- Tests: 1697 → 1727 (+30)
- Scope:
  hashing CRLF normalization, file_lock hardening, rrf metadata merge, extraction schema deepcopy
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-2-2026-04-17)

#### 2026-04-17 — cycle 1

- Items: 38 AC / 18 src
- Tests: → 1697
- Scope:
  pipeline wiki/raw dir plumbing, augment rate/manifest scoping, capture secret patterns, 3-round PR
  review pattern established
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-1-2026-04-17)

#### 2026-04-17 — HIGH cycle 2

- Items: 22 / 16 src
- Tests: → 1645
- Scope:
  frontmatter regex cap, orphan-graph copy, semantic inverted index, trends UTC-aware timestamps
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-2-2026-04-17)

#### 2026-04-16 — HIGH cycle 1

- Items: 22 / multi
- Tests: → baseline
- Scope:
  RMW locks across refiner/evidence/wiki_log, hybrid vector-index lifecycle, error-tag categories
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-1-2026-04-16)

#### 2026-04-16 — CRITICAL docs-sync

- Items: 2
- Tests: 1546 → 1552
- Scope:
  version-string alignment + `scripts/verify_docs.py` drift check
- Detail: [history archive](CHANGELOG-history.md#phase-45--critical-cycle-1-docs-sync-2026-04-16)

> Older released-version history is also archived in [CHANGELOG-history.md](CHANGELOG-history.md).

---
