## Verdict

APPROVE-WITH-REVISIONS.

The cycle is directionally sound, but Step 7 must revise several ACs before implementation. The highest-risk problems are factual drift around `_validate_wiki_dir`, a production integration gap for vector filtering, raw `_safe_call` error exposure, and ingest manifest cleanup if validation fails after reservation.

## Blockers

1. **AC3-AC6 / AC18-AC21: `_validate_wiki_dir` does not match the requirements' security or error contract.** Current source is `src/kb/mcp/app.py:187-200`, returning `tuple[Path | None, str | None]`, but it only requires absolute, existing, directory paths. It does **not** enforce `PROJECT_ROOT` containment. Migrating `kb_stats` and `kb_verdict_trends` from their current `relative_to(PROJECT_ROOT.resolve())` checks at `src/kb/mcp/browse.py:327-328` and `src/kb/mcp/health.py:196-197` to the helper would broaden access to any absolute existing directory. Also, helper errors are shaped as `"Error: wiki_dir ..."` or `"Invalid wiki_dir: ..."`, not `"Error: Invalid wiki_dir — ..."`. Step 7 must either harden the helper and update existing callers knowingly, or stop claiming it preserves project-root containment.

2. **AC8 / AC22-AC23: filtering `kb.query.hybrid.hybrid_search()` may not affect production search.** `src/kb/query/engine.py:145-211` does not call `hybrid_search`; it calls local `bm25_search`, local `vector_search`, then `rrf_fusion` directly. Unit tests against `hybrid_search()` can pass while `kb_search` / `kb_query` still surface low-sim vector results. Step 7 must add the threshold to `search_pages.vector_search()` or refactor `search_pages()` through `hybrid_search()`, with an integration test at `search_pages()` or MCP level.

3. **AC1 / AC15: `_safe_call` currently leaks raw exception text.** `src/kb/lint/_safe_call.py:44-46` formats `{exc}` directly. If `kb_refine_page` appends `[warn] {err}` as written, OSError paths, absolute filenames, or token-bearing SDK messages can leak to MCP clients. The non-AC note says sanitize in the caller, but AC1's concrete snippet does not. Step 7 must explicitly route `err` through `_sanitize_error_str` or add an optional sanitizer to `_safe_call`; do not create a second unsynchronized `_safe_call` implementation.

4. **AC12-AC13 / AC26: validation failure can leave a stale manifest reservation.** `ingest_source()` reserves the hash manifest before extraction rendering at `src/kb/ingest/pipeline.py:859-889`; `_build_summary_content()` is called later at `src/kb/ingest/pipeline.py:942`. If `_coerce_str_field()` raises there, AC26's "no half-written summary" may pass, but the source hash can remain reserved, causing future duplicate false positives. Step 7 needs cleanup/rollback around post-reservation validation failures, or it must perform all extraction field validation before `_check_and_reserve_manifest()`.

5. **Brainstorm commit shape conflicts with requirements.** The brainstorm separates AC14 `CLAUDE.md` raw/captures docs into commit 8, but requirements non-AC detail #4 says AC14 must land in the same commit as AC10/AC11. AC9 also requires a CLAUDE.md note, while brainstorm commit 5 lists only `compiler.py`. Commit 3 is a deliberate two-file wiki_dir cluster; that is a violation of strict file-grouped memory unless the plan gate explicitly grants the documented exception or splits it into browse/health commits.

## Majors

1. **Factual vector-score claim: public `score` is similarity, raw `VectorIndex.query()` is distance.** `src/kb/query/embeddings.py:360-404` returns `(page_id, distance)` ordered lower-is-better. `src/kb/query/engine.py:143` converts this to `1.0 / (1.0 + dist)`, so AC8's `score >= 0.3` direction is correct **only for the dicts returned by `vector_search()` / test `vector_fn`**, not for `VectorIndex.query()` directly. Requirements should state this boundary.

2. **AC25 timestamp test is too tight and likely flaky/impossible.** `captured_at` is formatted to whole seconds (`"%Y-%m-%dT%H:%M:%SZ"`), so asserting within 100 ms of a wall-clock pre-call is not stable. Freeze or monkeypatch `datetime.now(UTC)` at two distinct instants, or assert ordering using second-level tolerance.

3. **AC10 boundary implementation should use the existing alias deliberately.** `capture.py` imports `secrets as _secrets` at `src/kb/capture.py:11`; `_resolve_provenance()` already uses `_secrets.token_hex()`. AC10 says `secrets.token_hex(16)`. Either use `_secrets.token_hex(16)` and test by monkeypatching `kb.capture._secrets.token_hex`, or rename the import intentionally. Also test collision retry exhaustion, not only the happy prompt.

4. **AC10 test wording contradicts requirements' defense-in-depth clause.** AC10 says the existing `_escape_prompt_fences` regex machinery stays. AC24 says the prompt must not contain the legacy `"--- INPUT ---"` literal. That is fine for the template fence, but tests must not fail merely because escaped user content contains `"--- INPUT (escaped) ---"` or related defense-in-depth text.

5. **AC2 / AC16 Windows skip is underspecified.** The plan only skips on `sys.platform == "win32"`, but default macOS filesystems can also be case-insensitive, and Windows can be configured case-sensitive per directory. Use a runtime capability check by attempting to create both names in a temp dir, then skip if the FS cannot represent both.

6. **AC3-AC6 migration has caller-shape edge cases.** Requirements alternately say return `f"Error: {err}"` and expect `"Error: Invalid wiki_dir — "`. Since current `_validate_wiki_dir()` already returns `"Error: ..."`, naive wrapping creates `"Error: Error: ..."`. Lock the exact helper/caller contract before tests.

7. **AC12-AC13 scope leaves known non-string read sites.** The limited `_build_summary_content()` scope is acceptable, but `_extract_entity_context()` still calls `val.lower()` on extraction fields at `src/kb/ingest/pipeline.py:413-415`. Step 7 should state this remains out of scope and ensure new validation does not give a false sense that all extraction field reads are safe.

8. **AC18 valid override may fail under the current helper unless fixtures use absolute paths.** `_validate_wiki_dir()` rejects relative paths at `src/kb/mcp/app.py:194-195`. Tests must pass absolute `tmp_project / "wiki"` strings and should include CRLF/unicode/space-containing temp path coverage only if the fixtures can support it.

9. **Threat model is stale against the requirements doc.** It says "33 ACs across 16 files" and discusses wiki_log and kb_search ACs that the requirements explicitly dropped as stale. Treat it as background, not a source of AC numbering or plan tasks, until reconciled.

10. **Perf impact is small if implemented at the right layer.** Filtering vector results is O(number of vector hits per query variant), bounded by `limit * VECTOR_SEARCH_LIMIT_MULTIPLIER * (1 + MAX_QUERY_EXPANSIONS)`. That is negligible compared with embedding and sqlite-vec I/O. The real perf risk is duplicating filtering in both `hybrid_search()` and `search_pages()` inconsistently.

## Nits

1. AC1 says `backlinks_map, err = _safe_call(...)` but the current local variable is `backlinks`; keep naming aligned with the map/list distinction.

2. AC8's debug log should include both dropped and kept counts if operators are expected to tune `VECTOR_MIN_SIMILARITY`.

3. AC12 says "If `IngestError` is not yet defined" but grep found no `IngestError` in `src/` or `tests/`. Requirements should directly choose `ValueError` or add a real ingest error class.

4. AC28 is large for a housekeeping AC. Split verification wording for CHANGELOG, BACKLOG, and CLAUDE.md so Step 12 does not become a vague doc sweep.

5. Error examples use an em dash in `"Error: Invalid wiki_dir — "`. Existing code uses both colon and em dash styles. Standardize before adding tests.

## Factual conflicts vs requirements doc

1. `_validate_wiki_dir` is at `src/kb/mcp/app.py:187` and returns `tuple[Path | None, str | None]`, as claimed. But it does **not** return the claimed error shape, does **not** reject absolute-outside-project paths, and does **not** preserve the `PROJECT_ROOT.relative_to()` containment currently present in `kb_stats` and `kb_verdict_trends`.

2. `_safe_call` is at `src/kb/lint/_safe_call.py:20` and returns `(result, None)` or `(fallback, "<label>_error: <type>: <msg>")`. It is stateless and safe to invoke repeatedly only in the narrow helper sense; it will execute `fn()` each time, so it is not idempotent for side-effecting thunks. It also does not sanitize errors.

3. `VectorIndex.query()` returns distance, lower-is-better, from sqlite-vec (`src/kb/query/embeddings.py:360-404`). The concrete production `vector_search()` converts distance to a similarity-like score via `1.0 / (1.0 + dist)` (`src/kb/query/engine.py:143`). Therefore AC8's threshold direction is not factually wrong, but only if applied after that conversion.

4. Requirements say "hybrid_search in query/hybrid.py has no cosine-similarity floor" and treat that as the production no-results fix. Current production `search_pages()` bypasses that function, so the stated implementation target is incomplete.

5. The brainstorm's 8-code-commit shape does not fully match the file-grouped memory or the requirements' same-commit documentation constraints. Commit 3 is an explicit cluster exception, not a pure file-grouped commit.

6. Tests that are mostly grep/source-shape based: AC9 and AC14 are documentation-only/source-docstring checks, so source inspection is acceptable there; AC22-AC23 are behavioral but target the wrong integration layer; AC25 as written can fail for timing precision rather than behavior. No Windows-specific skip is needed beyond AC16, but AC16 should be filesystem-capability based rather than Windows-only.
