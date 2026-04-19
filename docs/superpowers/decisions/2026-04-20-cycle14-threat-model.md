# Cycle 14 — Threat Model

**Date:** 2026-04-20
**Source:** Opus subagent (Step 2)
**Baseline:** Dependabot 0 open alerts; pip-audit 1 vuln (diskcache CVE-2025-69872, no fix available, pre-existing MEDIUM).

## Analysis

**Trust boundaries crossed by cycle 14.** Three new and one re-crossed old:

1. `kb publish` CLI subcommand (AC21) accepts `--out-dir PATH` from operator shell and writes three files into it.
2. `kb.compile.publish` (AC20) reads wiki page bodies (including LLM-extracted titles, source_refs, `[!augmented]`-marked `confidence: speculative` content) and emits them into three structured formats for external LLM crawlers. Wiki content becomes an explicit output trust boundary for the first time.
3. Coverage-gate advisory (AC5) introduces a new user-visible string that may reflect the question verbatim.
4. Re-crossed: the augment write-back boundary (AC16/AC18) — frontmatter-preserving save wrapper migrates three sites while the `Post` still holds attacker-plantable metadata (fetched URL, stub_id).

**Data classifications and regression risks.** `llms-full.txt` exposes full page bodies including `confidence: speculative`, `belief_state: retracted`/`contradicted`, and `[!augmented]` stubs. Existing invariants at risk of regression: (a) cycle-7 R1 M3 key-order lesson — `sort_keys=False` must be threaded; (b) path-traversal guards don't cover the new `kb publish --out-dir`; (c) atomic-write ordering contract must be preserved in the new wrapper; (d) `_flag_stale_results` timezone-aware comparison shouldn't regress via the new decay helper.

**Novel attack vectors.** JSON-LD `title` / `url` / `citation` arrays built from LLM-extracted content; plain-text `llms.txt` one-line-per-page contract defeated by embedded newlines in titles; symbolic-link / path-part escape in `_infer_source_type`; substring-match stale-decay bypass (`arxiv.org.attacker.com`).

## Threat items

### T1: `kb publish --out-dir` path traversal / arbitrary write

- **Surface:** `src/kb/cli.py::publish` + `src/kb/compile/publish.py::build_*` (AC21)
- **Vector:** operator invokes `kb publish --out-dir ../../../Windows/Temp` or `--out-dir /etc`. Builders call `atomic_text_write` which `mkdir(parents=True)` + writes.
- **Impact:** arbitrary-file write; overwrites system files.
- **Mitigation:** validate `--out-dir` in CLI — resolve, require `is_relative_to(PROJECT_ROOT)` OR require pre-existing directory. Reject UNC / `..` / absolute outside project root with Click `UsageError`. Mirror `_validate_wiki_dir` pattern.
- **Verification:** grep `publish.py` + `cli.py` for `resolve()` + `is_relative_to`; test `--out-dir=/tmp/outside-root` → `UsageError`.

### T2: `llms.txt` / `llms-full.txt` leak of retracted/contradicted/speculative content

- **Surface:** `src/kb/compile/publish.py::build_llms_txt` / `build_llms_full_txt` / `build_graph_jsonld` (AC20)
- **Vector:** AC1 introduces `belief_state: retracted`; AC20 enumerates pages with no belief/confidence filter. Pages explicitly marked `belief_state: retracted` / `contradicted` or `confidence: speculative` (augment auto-ingest sets this) are published to external crawlers.
- **Impact:** retracted claims propagate to external LLM training corpora. `belief_state` semantics defeated.
- **Mitigation:** skip pages whose frontmatter has `belief_state in {"retracted", "contradicted"}` OR `confidence == "speculative"`. Emit `[!excluded]` count footer. Document filter rule in AC20 docstring.
- **Verification:** test with tmp wiki containing one `belief_state: retracted` + one `confidence: speculative` — neither appears in any of the three outputs.

### T3: JSON / JSON-LD injection via untrusted titles / source_refs

- **Surface:** `src/kb/compile/publish.py::build_graph_jsonld` + `build_llms_txt` (AC20)
- **Vector:** page `title` / `source` contain arbitrary Unicode, quotes, newlines, bidi marks. F-string JSON assembly breaks on `"], "malicious": true, "filler": [`. Plain-text one-line-per-page contract broken by embedded newlines.
- **Impact:** downstream JSON-LD consumers ingest attacker fields; broken JSON breaks every consumer silently; `llms.txt` forges new page entries.
- **Mitigation:** use `json.dump(obj, f, ensure_ascii=False)` with fully-constructed Python dict — never f-string-assemble JSON. For `llms.txt`, collapse embedded newlines in titles and apply `yaml_sanitize`.
- **Verification:** grep `build_graph_jsonld` for `json.dump` (required) and absence of `f'"` or `.format(` inside the function. Test with title containing `"`, `\n`, `\u2028`, `]`, `},{` — output still parses with `json.loads`.

### T4: `save_page_frontmatter` must preserve atomic-write + key-order contract

- **Surface:** `src/kb/utils/pages.py::save_page_frontmatter` (AC16), consumers in `src/kb/lint/augment.py` (AC18)
- **Vector:** wrapper uses `path.write_text(frontmatter.dumps(post))` instead of `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)` — two regressions: non-atomic write (SIGINT/AV-hold corruption); alphabetical key reorder (cycle-7 R1 M3 lesson; corrupts Evidence Trail sentinel).
- **Impact:** data corruption on crash; diff noise masks real frontmatter tampering.
- **Mitigation:** implementation must call `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)` — both knobs required. Wrapper is the single enforcement point.
- **Verification:** `Read` the wrapper; must contain `sort_keys=False` + `atomic_text_write`. Test `tests/test_cycle14_save_frontmatter.py` must assert key insertion order across ≥3 non-alphabetical keys. Post-AC18 grep of `lint/augment.py` for `frontmatter.dumps(` → every hit must be inside `save_page_frontmatter` call.

### T5: Coverage-confidence advisory echoes question — XSS / prompt-injection

- **Surface:** `src/kb/query/engine.py::query_wiki` result `advisory` field (AC5)
- **Vector:** natural impl `advisory = f"Coverage low; try rephrasing '{question}'"`. If later rendered in `query.formats.html` without escaping, stored XSS vector. Question may contain prompt-injection that bleeds into subsequent `use_api=True` calls.
- **Impact:** HTML adapter emits unescaped `<script>`; downstream prompt-reuse smuggles LLM instructions.
- **Mitigation:** build advisory with fixed string that does NOT include user's question verbatim. If must echo, pre-sanitize via `yaml_sanitize` and cap to 200 chars.
- **Verification:** grep `query/engine.py` for advisory assembly — must not interpolate `question` raw; or must pre-sanitize. Test: question = `<script>alert(1)</script>` → advisory contains no raw `<script>`.

### T6: `decay_days_for` substring matcher — domain-spoofing stale-bypass

- **Surface:** `src/kb/config.py::decay_days_for` (AC11)
- **Vector:** AC11 says "substring / suffix match". Naive substring treats `arxiv.org.attacker.com` and `github.com-phish.net` as long-decay domains. Attacker-authored page with source_ref `https://arxiv.org.evil.example/` gets 1095-day arxiv decay instead of 90-day default.
- **Impact:** stale or poisoned pages pass freshness checks; outrank fresh legitimate content.
- **Mitigation:** `urllib.parse.urlparse(ref).hostname`, then require exact hostname OR `host.endswith("." + key)`. Never plain substring.
- **Verification:** tests: `arxiv.org.evil.com/x` → default; `arxiv.org/x` → arxiv; `sub.arxiv.org/x` → arxiv. Grep helper for `urlparse` + `endswith("." +`.

### T7: `_infer_source_type` — path-part escape to unexpected source type

- **Surface:** `src/kb/ingest/pipeline.py::_infer_source_type` (AC14)
- **Vector:** AC14 "checks the first path-part matching keys, scanned in order". Path `raw/other/capture/foo.md` (nested `capture` subdir) might infer `capture` despite living under non-captures parent. Symlinks could point a path at `raw/articles/...` while the file is outside RAW_DIR — bypasses `relative_to(RAW_DIR)` check.
- **Impact:** wrong extraction template applied; template-hash manifest corrupted; potential path-traversal.
- **Mitigation:** check only immediate parent directory name (`path.parent.name`), not every path-part. Preserve existing `relative_to(RAW_DIR.resolve())` check — don't move it after `_infer_source_type`. Explicit `source_type` wins.
- **Verification:** grep `_infer_source_type` for `path.parent.name` (not `path.parts`). Test case: `raw/articles/captures/foo.md` → `"article"` (parent=`articles`, not `captures`).

### T8: JSON-LD `url` field leaks absolute filesystem paths

- **Surface:** `src/kb/compile/publish.py::build_graph_jsonld` (AC20)
- **Vector:** builder emits `url: /absolute/user/path/wiki/concepts/rag.md` or `D:\...\wiki\...\.md` — leaks user's home/drive layout to every LLM crawler. `file:///home/user/...` leaks userinfo.
- **Impact:** information disclosure; user's filesystem layout becomes public.
- **Mitigation:** emit `url` as wiki-relative POSIX path (`concepts/rag.md`) via `page_path.relative_to(wiki_dir).as_posix()`. Never absolute, never `file://`.
- **Verification:** test: tmp wiki under `/tmp/wiki-abc123`; grep output for `/tmp/wiki-abc123` → absent. Grep builder for `relative_to(wiki_dir).as_posix()` (required).

### T9: AC23 status boost on attacker-controlled frontmatter

- **Surface:** `src/kb/query/engine.py` ranking (AC23)
- **Vector:** +5% boost on `status in (mature, evergreen)`. Attacker lands PR with `status: mature` on poisoned page — or LLM-extracted frontmatter accidentally sets it — ranks poisoned page above legit ones. AC gates on "field present AND valid value" but not on trusted authorship.
- **Impact:** trivial ranking manipulation via one frontmatter line.
- **Mitigation:** document explicit decision — either (a) co-gate: require `authored_by in ("human", "hybrid")` for the boost, OR (b) accept the risk and document that LLM-set `mature` honors the boost (trust the pipeline), OR (c) require validation by `validate_frontmatter` at page-load time.
- **Verification:** grep the ranking path for the gating decision; AC24 test case covers `status: mature` + various `authored_by` combinations.

### T10: AC18 migration leaves one call-site un-migrated

- **Surface:** `src/kb/lint/augment.py::_record_verdict_gap_callout` / `_mark_page_augmented` / `_record_attempt` (AC18)
- **Vector:** grep-miss leaves one site on `frontmatter.dumps(post)` (no `sort_keys=False`) or `path.write_text(...)`. Cycle-13 AC6 comments say "DO NOT migrate to load_page_frontmatter" — reader may over-extend to "don't migrate the WRITE either".
- **Impact:** half-migrated call-sites reintroduce key reordering and non-atomic writes.
- **Mitigation:** AC18 tests exercise each of the three sites through `run_augment` and assert (a) key order preserved and (b) `.tmp` sibling cleaned up (atomic-write proof).
- **Verification:** single grep: `frontmatter\.dumps\(` in `lint/augment.py` — every hit inside a `save_page_frontmatter` call. Single grep: `sort_keys` in `lint/augment.py` — zero literal hits (knob lives in wrapper).

## AC amendments required (for Step 5 decision gate)

- **AC20** — amend to explicitly filter `belief_state in {retracted, contradicted}` and `confidence: speculative` from all three builders (T2).
- **AC11** — change "substring / suffix match" to "exact hostname OR dot-boundary suffix match against `urlparse(ref).hostname`" (T6).
- **AC21** — add `--out-dir` containment requirement: resolved path must be inside `PROJECT_ROOT`, OR must already exist as operator-created directory; reject `..`, UNC, absolute outside project root (T1).
- **AC20** — JSON-LD `url` field must be relative to wiki_dir, POSIX-style, no `file://` (T8).
- **AC5** — advisory must NOT echo user question verbatim (or must pre-sanitize + truncate) (T5).
- **AC14** — `_infer_source_type` must check immediate parent only (`path.parent.name`), not every path-part (T7).

## Baseline summary

- **Dependabot:** 0 open alerts (N open alerts: S sev=high 0, M sev=medium 0, L sev=low 0).
- **pip-audit:** 1 vuln (diskcache 5.6.3 CVE-2025-69872, no fix available, pre-existing BACKLOG MEDIUM informational — out of scope).
- Cycle 14 adds no new third-party dependencies → Class B PR-introduced CVE diff should be empty at Step 11.
