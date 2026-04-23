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
-->

## [Unreleased]

### Quick Reference

Newest first. `CHANGELOG.md` is the compact index; full detail lives in [CHANGELOG-history.md](CHANGELOG-history.md).

#### 2026-04-24 — cycle 26

- Items: 8 AC (+AC2b) / 2 src + 1 new test file + 1 extended cycle-23 test / 6 commits
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
