# Cycle 14 — Security Verification (Step 11)

**Date:** 2026-04-20
**Verifier:** Codex Step 11 subagent → PARTIAL; all gaps closed in follow-up commit.
**CVE diff (Step 11b):** Class B (PR-introduced) empty — only `diskcache==5.6.3 CVE-2025-69872` present in both baseline and branch. No new deps shipped.

## Threat verification (post-fix)

| # | Item | Status | Evidence |
|---|------|--------|----------|
| T1 | `kb publish --out-dir` containment | IMPLEMENTED | `src/kb/cli.py::publish` — explicit `..` traversal check + `Path.is_relative_to(PROJECT_ROOT)` + `is_dir()` pre-exist fallback + UNC rejection. Test `test_nonexistent_outside_project_rejected` asserts UsageError. |
| T2 | Epistemic filter (retracted/contradicted/speculative) | IMPLEMENTED | `src/kb/compile/publish.py::_partition_pages` + `_EXCLUDED_BELIEF_STATES` + `_EXCLUDED_CONFIDENCE`. All three builders (`build_llms_txt`, `build_llms_full_txt`, `build_graph_jsonld`) call `_partition_pages`. Tests cover all three filter paths. |
| T3 | JSON-LD uses json.dump, no f-strings in body | IMPLEMENTED | `build_graph_jsonld` uses `json.dump(document, fh, ensure_ascii=False, indent=2)`. f-string removed from `disambiguatingDescription` assembly (string concatenation used). Grep contract: zero `f'"` or `.format(` hits in function body. |
| T4 | save_page_frontmatter wrapper: atomic + sort_keys=False | IMPLEMENTED | `src/kb/utils/pages.py::save_page_frontmatter` single line: `atomic_text_write(frontmatter.dumps(post, sort_keys=False), path)`. 8 tests cover key-order preservation, body verbatim, list-order, atomic-write proof. |
| T5 | Advisory no-echo of user question | IMPLEMENTED | `src/kb/query/engine.py` — advisory assembled from `coverage_confidence` + `QUERY_COVERAGE_CONFIDENCE_THRESHOLD` only; no `question` interpolation. Test `test_advisory_excludes_malicious_question` asserts `<script>` absent. |
| T6 | decay_days_for dot-boundary match | IMPLEMENTED | `src/kb/config.py::decay_days_for` — `urlparse` → `hostname` → IDNA encode → `host == key or host.endswith("." + key)`. No plain substring. Tests cover `arxiv.org.evil.com`, IDN punycode, port/userinfo. |
| T7 | AC13-15 dropped | N/A | Existing `detect_source_type` at `src/kb/ingest/pipeline.py:288-301` already resolves symlinks, checks containment, uses `rel.parts[0]`. Confirmed via Step 5 design gate. |
| T8 | JSON-LD url is relative POSIX | IMPLEMENTED | `build_graph_jsonld` uses `page_path.relative_to(wiki_dir).as_posix()`. Test `test_url_is_relative_posix` asserts `url == "concepts/a.md"` and absent of absolute path leak. |
| T9 | Status boost validate_frontmatter gate | IMPLEMENTED | `src/kb/query/engine.py::_apply_status_boost` — reconstructs metadata dict, calls `validate_frontmatter(post)`, skips boost on non-empty error list. Tests cover invalid status, invalid confidence, invalid type, empty source list. |
| T10 | Zero bare frontmatter.dumps in augment.py | IMPLEMENTED | `grep -nE "frontmatter\.dumps\(|sort_keys" src/kb/lint/augment.py` → 0 hits. `sort_keys` removed from comments; the wrapper is the sole enforcement point. |

## CVE diff

- **Baseline (main @ d4b227b):** 1 vuln — `diskcache 5.6.3 CVE-2025-69872` (no fix available, pre-existing BACKLOG MEDIUM informational).
- **Branch HEAD (f37d1f2):** 1 vuln — same.
- **Class B (PR-introduced):** empty.
- **Dependabot alerts:** 0 open (baseline unchanged).

Cycle 14 adds no new third-party dependencies — expected and confirmed.

## Other findings

- **Publish builders use `out_path.write_text(...)`, not `atomic_text_write`.** Low-severity crash-safety gap; added as a cycle-15 BACKLOG entry rather than an in-scope fix. Publish is a read-only operation from the wiki's perspective; the only partial-write risk is on the output artifacts, which can be safely re-generated.
- **Comment/docstring hygiene:** `SOURCE_DECAY_DAYS` comment + `decay_days_for` docstring both updated to describe "exact-or-dot-suffix" instead of the earlier "substring" wording. No runtime effect; prevents future regression via comment-reading drift.

## Verdict

**IMPLEMENTED** — all T1-T10 items pass after the three follow-up fixes (T1 explicit traversal check, T3 f-string removal in `disambiguatingDescription`, T10 comment sanitation). Proceed to Step 12 doc update.
