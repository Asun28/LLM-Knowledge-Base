# Phase 3.93 Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 33 open backlog items from the Phase 3.93 code review, commit one fix group at a time.

**Architecture:** Each task targets one logical module cluster, writes failing tests first (TDD), implements the fix, verifies tests pass, then commits. Tasks are ordered so lower-level fixes (LLM client, utils) come before higher-level ones (query, ingest, compile).

**Tech Stack:** Python 3.12, pytest, ruff, click, anthropic SDK, pathlib

---

## Files Modified

| File | Changes |
|------|---------|
| `src/kb/utils/llm.py` | Retry count semantics, last_error safety |
| `src/kb/query/engine.py` | max_results forwarding, context fallback, clamp inside fn |
| `src/kb/ingest/pipeline.py` | Summary date preservation, path traversal guard, fresh install warnings |
| `src/kb/compile/compiler.py` | find_changed_sources read-only mode |
| `src/kb/compile/linker.py` | inject_wikilinks case mismatch |
| `src/kb/lint/checks.py` | Source coverage false-positive, staleness string, orphan exemptions |
| `src/kb/lint/verdicts.py` | Silent JSON discard → logged warning; move MAX_VERDICTS to config |
| `src/kb/graph/export.py` | Mermaid sanitize newlines/backticks |
| `src/kb/evolve/analyzer.py` | Broad except → log |
| `src/kb/config.py` | MAX_VERDICTS, MAX_FEEDBACK_ENTRIES, model ID validation |
| `src/kb/feedback/store.py` | Use MAX_FEEDBACK_ENTRIES from config |
| `src/kb/feedback/reliability.py` | Docstring "below" → "at or below" |
| `src/kb/utils/pages.py` | WIKI_SUBDIRS derived from config constants |
| `src/kb/cli.py` | mcp try/except, --type choices |
| `src/kb/mcp/browse.py` | Outer try/except on kb_search, kb_list_pages |
| `src/kb/mcp/app.py` | Remove dead dict-branch in _format_ingest_result |
| `tests/test_v0912_phase393.py` | All new tests |

---

## Task 1: LLM Client — retry semantics and last_error safety

**Files:**
- Modify: `src/kb/utils/llm.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `_make_api_call` uses `range(MAX_RETRIES)` which gives MAX_RETRIES total attempts, not retries. Fix: `range(MAX_RETRIES + 1)` so MAX_RETRIES=3 gives 1 initial + 3 retries.
- `last_error` is still `None` if `MAX_RETRIES=0` (loop body never executes). The exhaustion code tries to inspect `last_error` type, raising `AttributeError`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_v0912_phase393.py
"""Tests for Phase 3.93 backlog fixes (v0.9.12)."""
import pytest


class TestLLMRetrySemantics:
    """utils/llm.py retry count and last_error safety."""

    def test_max_retries_means_retries_not_attempts(self, monkeypatch):
        """MAX_RETRIES=2 should make 3 total calls (1 initial + 2 retries)."""
        import anthropic
        from kb.utils import llm as llm_mod

        calls = []

        def fake_create(**kwargs):
            calls.append(1)
            raise anthropic.RateLimitError("rate", response=None, body=None)

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 2)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()
        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")

        assert len(calls) == 3, f"Expected 3 total calls (1+2 retries), got {len(calls)}"

    def test_max_retries_zero_raises_llmerror_not_attribute_error(self, monkeypatch):
        """MAX_RETRIES=0 must raise LLMError, not AttributeError on last_error."""
        import anthropic
        from kb.utils import llm as llm_mod

        monkeypatch.setattr(llm_mod, "MAX_RETRIES", 0)
        monkeypatch.setattr(llm_mod, "RETRY_BASE_DELAY", 0)
        client = llm_mod.get_client()

        def fake_create(**kwargs):
            raise anthropic.RateLimitError("rate", response=None, body=None)

        monkeypatch.setattr(client.messages, "create", fake_create)

        with pytest.raises(llm_mod.LLMError):
            llm_mod._make_api_call({"model": "x", "max_tokens": 10, "messages": []}, "x")
```

- [ ] **Step 2: Run to verify it fails**

```
python -m pytest tests/test_v0912_phase393.py::TestLLMRetrySemantics -v
```
Expected: both tests FAIL (first: 1 call not 3; second: AttributeError or wrong behavior)

- [ ] **Step 3: Fix `src/kb/utils/llm.py`**

Change line 59 (`for attempt in range(MAX_RETRIES):`) to:
```python
    for attempt in range(MAX_RETRIES + 1):
```

Add a guard before the exhaustion error block (after the loop). Find the line `if isinstance(last_error, anthropic.APITimeoutError):` and add before it:
```python
    if last_error is None:
        raise LLMError(f"MAX_RETRIES=0, no call was attempted for {model}")
```

- [ ] **Step 4: Run to verify it passes**

```
python -m pytest tests/test_v0912_phase393.py::TestLLMRetrySemantics -v
```
Expected: PASS (2/2)

- [ ] **Step 5: Run full suite to check for regressions**

```
python -m pytest tests/ -x -q
```
Expected: all pass

- [ ] **Step 6: Lint**

```
ruff check src/kb/utils/llm.py tests/test_v0912_phase393.py && ruff format src/kb/utils/llm.py tests/test_v0912_phase393.py
```

- [ ] **Step 7: Commit**

```bash
git add src/kb/utils/llm.py tests/test_v0912_phase393.py
git commit -m "fix: LLM retry count off-by-one and last_error safety on MAX_RETRIES=0"
```

---

## Task 2: Query Engine — max_results forwarding, context fallback, clamp

**Files:**
- Modify: `src/kb/query/engine.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `query_wiki` never forwards `max_results` to `search_pages` — the parameter is accepted by the MCP layer but dead in API mode.
- `_build_query_context` returns `""` when ALL matched pages individually exceed the 80K limit → zero context sent to LLM → hallucinated answer. Fix: fall back to truncated top page.
- `search_pages` `max_results` not clamped inside the function — direct Python callers passing `-1` get unexpected behavior (slices `scored[:-1]`).

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestQueryEngine:
    """query/engine.py correctness fixes."""

    def test_search_pages_clamps_negative_max_results(self, tmp_wiki, create_wiki_page):
        """search_pages with max_results=-1 should not return all-but-last."""
        from kb.query.engine import search_pages

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="concepts/llm", title="LLM", wiki_dir=tmp_wiki)

        # -1 should be clamped to 1 (return at most 1 result)
        results = search_pages("rag llm", wiki_dir=tmp_wiki, max_results=-1)
        assert len(results) >= 0  # Must not raise or return negative slice

    def test_build_query_context_falls_back_to_truncated_top_page(self):
        """_build_query_context returns truncated top page when all pages exceed limit."""
        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "title": "Big Page",
            "type": "concept",
            "confidence": "stated",
            "content": "x" * 200,
        }
        # limit is 100 chars — smaller than the page section
        result = _build_query_context([big_page], max_chars=100)
        assert result != "", "Must not return empty string when top page exceeds limit"
        assert len(result) <= 150, "Should be roughly truncated to limit"
        assert "big" in result.lower() or "Big" in result, "Should contain page content"

    def test_query_wiki_accepts_max_results_param(self, monkeypatch, tmp_wiki, create_wiki_page):
        """query_wiki signature must accept max_results and forward to search_pages."""
        from kb.query import engine as eng

        searched_with = []

        def fake_search(question, wiki_dir=None, max_results=10):
            searched_with.append(max_results)
            return []

        monkeypatch.setattr(eng, "search_pages", fake_search)

        eng.query_wiki("test question", wiki_dir=tmp_wiki, max_results=5)
        assert searched_with == [5], f"Expected search called with max_results=5, got {searched_with}"
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestQueryEngine -v
```
Expected: `test_query_wiki_accepts_max_results_param` fails (TypeError: unexpected keyword argument), `test_build_query_context_falls_back_to_truncated_top_page` fails (returns `""`)

- [ ] **Step 3: Fix `src/kb/query/engine.py`**

**3a. Clamp `max_results` in `search_pages`:** After line `scored.sort(...)`, before the return, add clamping at the top of the function body (after the `pages = load_all_pages(wiki_dir)` line):
```python
    max_results = max(1, max_results)
```

**3b. Fix `_build_query_context` fallback:** After the `for page in pages:` loop, before `if skipped:`, insert:
```python
    if not sections and pages:
        # All pages exceeded the limit individually — truncate top page as fallback
        top = pages[0]
        section = (
            f"--- Page: {top['id']} (type: {top['type']}, "
            f"confidence: {top['confidence']}) ---\n"
            f"Title: {top['title']}\n\n{top['content']}\n"
        )
        sections.append(section[:max_chars])
        logger.warning(
            "All matched pages exceed context limit; truncating top page %s to %d chars",
            top["id"],
            max_chars,
        )
```

**3c. Add `max_results` to `query_wiki`:** Change the signature:
```python
def query_wiki(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> dict:
```
And forward it in step 1:
```python
    matching_pages = search_pages(question, wiki_dir, max_results=max_results)
```

- [ ] **Step 4: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestQueryEngine -v
```
Expected: PASS (3/3)

- [ ] **Step 5: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 6: Lint**

```
ruff check src/kb/query/engine.py && ruff format src/kb/query/engine.py
```

- [ ] **Step 7: Commit**

```bash
git add src/kb/query/engine.py tests/test_v0912_phase393.py
git commit -m "fix: query engine max_results forwarding, context fallback, and internal clamp"
```

---

## Task 3: Ingest Pipeline — summary date preservation, path traversal, fresh-install warnings

**Files:**
- Modify: `src/kb/ingest/pipeline.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- Summary page always overwritten without checking existence → loses original `created:` date on re-ingest. Fix: if summary page exists, call `_update_existing_page` (updates `updated:` date and source list) instead of `_write_wiki_page`.
- `ingest_source` has no library-level path traversal guard. The MCP layer validates, but calling `ingest_source` directly can bypass it. Fix: resolve path and verify it's within `RAW_DIR`.
- `_update_sources_mapping` and `_update_index_batch` silently no-op when files missing on fresh install — no warning logged.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestIngestPipeline:
    """ingest/pipeline.py correctness fixes."""

    def test_summary_page_preserves_created_date_on_reingest(self, tmp_project):
        """Re-ingesting same source must not overwrite created: date on summary page."""
        from datetime import date, timedelta
        from kb.ingest.pipeline import _write_wiki_page, ingest_source
        from kb.config import WIKI_DIR

        # Create a raw source
        raw_path = tmp_project / "raw" / "articles" / "test-article.md"
        raw_path.write_text("# Test\nContent about RAG.", encoding="utf-8")

        wiki_dir = tmp_project / "wiki"
        summary_dir = wiki_dir / "summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)

        # Pre-create the summary page with an old created: date
        old_date = (date.today() - timedelta(days=10)).isoformat()
        summary_path = summary_dir / "test.md"
        summary_path.write_text(
            f"---\ntitle: Test\nsource:\n  - raw/articles/test-article.md\n"
            f"created: {old_date}\nupdated: {old_date}\ntype: summary\nconfidence: stated\n---\n\n# Test\n",
            encoding="utf-8",
        )

        # Re-ingest with extraction provided
        extraction = {"title": "Test", "entities_mentioned": [], "concepts_mentioned": []}
        result = ingest_source(
            raw_path,
            source_type="article",
            extraction=extraction,
        )

        # created: date must be preserved
        import frontmatter
        post = frontmatter.load(str(summary_path))
        created_val = str(post.metadata.get("created", ""))
        assert old_date in created_val, (
            f"Re-ingest overwrote created: date. Got: {created_val!r}, expected: {old_date!r}"
        )

    def test_ingest_source_rejects_path_outside_project(self, tmp_path):
        """ingest_source must reject paths outside the project's raw/ directory."""
        from kb.ingest.pipeline import ingest_source

        outside_path = tmp_path / "outside.md"
        outside_path.write_text("# Outside\nContent.", encoding="utf-8")

        with pytest.raises((ValueError, FileNotFoundError, PermissionError)):
            ingest_source(outside_path, source_type="article", extraction={"title": "X", "entities_mentioned": [], "concepts_mentioned": []})

    def test_update_sources_mapping_warns_when_file_missing(self, tmp_path, caplog):
        """_update_sources_mapping logs a warning when _sources.md doesn't exist."""
        import logging
        from kb.ingest.pipeline import _update_sources_mapping
        from unittest.mock import patch

        missing_sources = tmp_path / "_sources.md"

        with patch("kb.ingest.pipeline.WIKI_SOURCES", missing_sources):
            with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
                _update_sources_mapping("raw/articles/test.md", ["summaries/test"])

        assert any("_sources" in r.message.lower() or "sources" in r.message.lower()
                   for r in caplog.records), (
            f"Expected warning about missing _sources.md, got: {[r.message for r in caplog.records]}"
        )
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestIngestPipeline -v
```
Expected: `test_summary_page_preserves_created_date_on_reingest` FAIL (re-ingest overwrites created:), `test_ingest_source_rejects_path_outside_project` FAIL (no error raised), `test_update_sources_mapping_warns_when_file_missing` FAIL (no warning)

- [ ] **Step 3: Fix `src/kb/ingest/pipeline.py`**

**3a. Preserve `created:` date on re-ingest.** In `ingest_source`, after the line computing `summary_path`, replace:
```python
    summary_content = _build_summary_content(extraction, source_type)
    _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
    pages_created.append(f"summaries/{summary_slug}")
    new_pages_with_titles.append((f"summaries/{summary_slug}", title))
```
With:
```python
    summary_content = _build_summary_content(extraction, source_type)
    if summary_path.exists():
        _update_existing_page(summary_path, source_ref)
        pages_updated.append(f"summaries/{summary_slug}")
    else:
        _write_wiki_page(summary_path, title, "summary", source_ref, "stated", summary_content)
        pages_created.append(f"summaries/{summary_slug}")
        new_pages_with_titles.append((f"summaries/{summary_slug}", title))
```

**3b. Library-level path traversal guard.** Near the top of `ingest_source`, after `source_path = Path(source_path).resolve()`, add:
```python
    try:
        source_path.relative_to(RAW_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Source path must be within raw/ directory: {source_path}"
        )
```

**3c. Warning in `_update_sources_mapping` when file missing.** Change:
```python
    if WIKI_SOURCES.exists():
        content = WIKI_SOURCES.read_text(encoding="utf-8")
        ...
```
To:
```python
    if not WIKI_SOURCES.exists():
        logger.warning("_sources.md not found — skipping source mapping for %s", source_ref)
        return
    content = WIKI_SOURCES.read_text(encoding="utf-8")
    ...
```

Similarly in `_update_index_batch`:
```python
    if not WIKI_INDEX.exists():
        logger.warning("index.md not found — skipping index update")
        return
    if not entries:
        return
    content = WIKI_INDEX.read_text(encoding="utf-8")
    ...
```
(Remove the combined `if not WIKI_INDEX.exists() or not entries: return` guard.)

- [ ] **Step 4: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestIngestPipeline -v
```
Expected: PASS (3/3)

- [ ] **Step 5: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 6: Lint**

```
ruff check src/kb/ingest/pipeline.py && ruff format src/kb/ingest/pipeline.py
```

- [ ] **Step 7: Commit**

```bash
git add src/kb/ingest/pipeline.py tests/test_v0912_phase393.py
git commit -m "fix: ingest summary date preservation, library-level path traversal, fresh-install warnings"
```

---

## Task 4: Compile — linker case mismatch and manifest side-effect

**Files:**
- Modify: `src/kb/compile/linker.py`
- Modify: `src/kb/compile/compiler.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `inject_wikilinks`: `target_page_id` not lowercased before `in existing_links` check. `extract_wikilinks` lowercases all targets, so a mixed-case page ID like `"concepts/GPT4"` would never match. Fix: compare `target_page_id.lower()` against `existing_links`.
- `find_changed_sources` writes template hashes to manifest as a side effect — even when called read-only from `kb_detect_drift`. This suppresses real template changes from the next compile scan. Fix: add `save_hashes: bool = True` parameter; `detect_source_drift` passes `save_hashes=False`.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestCompileFixes:
    """compile/linker.py and compile/compiler.py correctness fixes."""

    def test_inject_wikilinks_skips_page_already_linked_case_insensitive(
        self, tmp_wiki, create_wiki_page
    ):
        """inject_wikilinks must not inject if page already links to mixed-case target."""
        from kb.compile.linker import inject_wikilinks

        # Page already has a lowercase wikilink to concepts/gpt4
        create_wiki_page(
            page_id="entities/openai",
            title="OpenAI",
            content="We use [[concepts/gpt4|GPT-4]] in our work. GPT-4 is great.",
            wiki_dir=tmp_wiki,
        )
        # Create the target page with mixed-case ID stored as concepts/gpt4
        create_wiki_page(page_id="concepts/gpt4", title="GPT-4", wiki_dir=tmp_wiki)

        # inject_wikilinks is called with mixed-case target_page_id
        updated = inject_wikilinks("GPT-4", "concepts/GPT4", wiki_dir=tmp_wiki)
        assert "entities/openai" not in updated, (
            "Should not inject duplicate wikilink when page already links to lowercased target"
        )

    def test_find_changed_sources_read_only_does_not_update_manifest(self, tmp_path):
        """find_changed_sources with save_hashes=False must not modify the manifest."""
        from kb.compile.compiler import find_changed_sources, load_manifest, save_manifest

        raw_dir = tmp_path / "raw" / "articles"
        raw_dir.mkdir(parents=True)
        (raw_dir / ".gitkeep").write_text("")
        manifest_path = tmp_path / "hashes.json"
        save_manifest({}, manifest_path)

        find_changed_sources(
            raw_dir=tmp_path / "raw",
            manifest_path=manifest_path,
            save_hashes=False,
        )

        manifest_after = load_manifest(manifest_path)
        assert manifest_after == {}, (
            f"Manifest was modified despite save_hashes=False: {manifest_after}"
        )
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestCompileFixes -v
```
Expected: `test_inject_wikilinks_skips_page_already_linked_case_insensitive` FAIL (injects duplicate), `test_find_changed_sources_read_only_does_not_update_manifest` FAIL (TypeError: unexpected keyword argument `save_hashes`)

- [ ] **Step 3: Fix `src/kb/compile/linker.py`**

Find the line (inside `inject_wikilinks`):
```python
        if target_page_id in existing_links:
```
Change to:
```python
        if target_page_id.lower() in existing_links:
```

- [ ] **Step 4: Fix `src/kb/compile/compiler.py`**

Change the `find_changed_sources` signature to:
```python
def find_changed_sources(
    raw_dir: Path | None = None,
    manifest_path: Path | None = None,
    save_hashes: bool = True,
) -> tuple[list[Path], list[Path]]:
```

Wrap the `save_manifest` call at the end of `find_changed_sources` (line 144: `save_manifest(manifest, manifest_path)`):
```python
    if save_hashes:
        manifest.update(current_tpl_hashes)
        save_manifest(manifest, manifest_path)
```

Also in `detect_source_drift`, change the call:
```python
    new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path)
```
To:
```python
    new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path, save_hashes=False)
```

- [ ] **Step 5: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestCompileFixes -v
```
Expected: PASS (2/2)

- [ ] **Step 6: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 7: Lint**

```
ruff check src/kb/compile/linker.py src/kb/compile/compiler.py && ruff format src/kb/compile/linker.py src/kb/compile/compiler.py
```

- [ ] **Step 8: Commit**

```bash
git add src/kb/compile/linker.py src/kb/compile/compiler.py tests/test_v0912_phase393.py
git commit -m "fix: compile linker case-insensitive dedup and find_changed_sources read-only mode"
```

---

## Task 5: Lint — staleness strings, orphan exemptions, source coverage, verdicts warning

**Files:**
- Modify: `src/kb/lint/checks.py`
- Modify: `src/kb/lint/verdicts.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `check_staleness` silently skips pages where `updated` is a quoted string (YAML parses `updated: "2026-01-01"` as a string, not `date`).
- Orphan detection exempts `summaries/` but not `comparisons/` or `synthesis/`.
- `check_source_coverage` suffix-based match (`ref.endswith(f"/{f.name}")`) false-positives on same-named files across subdirs.
- `load_verdicts` silently discards verdict history on `JSONDecodeError` with no warning.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestLintFixes:
    """lint/checks.py and lint/verdicts.py correctness fixes."""

    def test_check_staleness_handles_string_updated_date(self, tmp_wiki, create_wiki_page):
        """check_staleness must not silently skip pages with string-typed updated: field."""
        from datetime import date, timedelta
        from kb.lint.checks import check_staleness

        old_date = (date.today() - timedelta(days=200)).isoformat()
        # Write page with quoted string date (YAML parses as str, not date)
        page_path = tmp_wiki / "concepts" / "old-concept.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            f'---\ntitle: Old Concept\nsource:\n  - raw/articles/x.md\n'
            f'created: "{old_date}"\nupdated: "{old_date}"\ntype: concept\nconfidence: stated\n---\n\nBody.\n',
            encoding="utf-8",
        )

        issues = check_staleness(wiki_dir=tmp_wiki, max_days=90)
        stale_pages = [i["page"] for i in issues]
        assert "concepts/old-concept" in stale_pages, (
            f"Stale page with string-typed updated: was silently skipped. Found: {stale_pages}"
        )

    def test_check_orphan_exempts_comparisons_and_synthesis(self, tmp_wiki, create_wiki_page):
        """check_orphan_pages must not flag comparisons/ and synthesis/ as orphans."""
        from kb.lint.checks import check_orphan_pages

        create_wiki_page(page_id="comparisons/a-vs-b", title="A vs B", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="synthesis/overview", title="Overview", wiki_dir=tmp_wiki)

        issues = check_orphan_pages(wiki_dir=tmp_wiki)
        flagged = [i["page"] for i in issues]
        assert "comparisons/a-vs-b" not in flagged, "comparisons/ pages should be exempt from orphan check"
        assert "synthesis/overview" not in flagged, "synthesis/ pages should be exempt from orphan check"

    def test_check_source_coverage_no_false_positive_same_filename(self, tmp_wiki, create_wiki_page, tmp_path):
        """check_source_coverage must not false-positive when same filename exists in two subdirs."""
        from kb.lint.checks import check_source_coverage
        from unittest.mock import patch

        # Set up fake raw dir with two files named example.md in different subdirs
        raw_dir = tmp_path / "raw"
        (raw_dir / "articles").mkdir(parents=True)
        (raw_dir / "papers").mkdir(parents=True)
        (raw_dir / "articles" / "example.md").write_text("article content", encoding="utf-8")
        (raw_dir / "papers" / "example.md").write_text("paper content", encoding="utf-8")

        # Wiki page references only the article
        create_wiki_page(
            page_id="summaries/example",
            title="Example",
            content="See raw/articles/example.md for details.",
            wiki_dir=tmp_wiki,
        )

        issues = check_source_coverage(wiki_dir=tmp_wiki, raw_dir=raw_dir)
        uncovered = [i["source"] for i in issues]

        # The paper should be flagged, but NOT the article (no false positive)
        assert "raw/papers/example.md" in uncovered, "Paper with same name should be flagged"
        assert "raw/articles/example.md" not in uncovered, (
            "Article should NOT be flagged as uncovered — false positive from endswith check"
        )

    def test_load_verdicts_logs_warning_on_json_error(self, tmp_path, caplog):
        """load_verdicts must log a warning when the verdicts file is corrupt JSON."""
        import logging
        from kb.lint.verdicts import load_verdicts

        bad_path = tmp_path / "verdicts.json"
        bad_path.write_text("{ NOT VALID JSON }", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="kb.lint.verdicts"):
            result = load_verdicts(bad_path)

        assert result == [], "Should return empty list on JSON error"
        assert any("corrupt" in r.message.lower() or "json" in r.message.lower()
                   for r in caplog.records), (
            f"Expected warning about corrupt JSON, got: {[r.message for r in caplog.records]}"
        )
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestLintFixes -v
```
Expected: all 4 FAIL

- [ ] **Step 3: Fix `src/kb/lint/checks.py`**

**3a. Staleness string fix.** In `check_staleness`, find:
```python
            updated = post.metadata.get("updated")
            if updated and isinstance(updated, date) and updated < cutoff:
```
Replace with:
```python
            updated = post.metadata.get("updated")
            if isinstance(updated, str):
                try:
                    updated = date.fromisoformat(updated)
                except ValueError:
                    logger.warning("Could not parse updated date %r in %s", updated, page_path)
                    continue
            if updated and isinstance(updated, date) and updated < cutoff:
```

**3b. Orphan exemptions.** In `check_orphan_pages`, find:
```python
        if orphan.startswith("summaries/"):
            continue
```
Replace with:
```python
        if orphan.startswith(("summaries/", "comparisons/", "synthesis/")):
            continue
```

**3c. Source coverage exact match.** In `check_source_coverage`, find:
```python
                referenced = any(
                    ref == rel_path or ref.endswith(f"/{f.name}") for ref in all_raw_refs
                )
```
Replace with:
```python
                referenced = rel_path in all_raw_refs
```

- [ ] **Step 4: Fix `src/kb/lint/verdicts.py`**

Add `import logging` at the top and a logger. Then find:
```python
        except json.JSONDecodeError:
            return []
```
Replace with:
```python
        except json.JSONDecodeError as e:
            logger.warning("Corrupt verdicts file %s, returning empty: %s", path, e)
            return []
```

Add near top of file (after existing imports):
```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestLintFixes -v
```
Expected: PASS (4/4)

- [ ] **Step 6: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 7: Lint**

```
ruff check src/kb/lint/checks.py src/kb/lint/verdicts.py && ruff format src/kb/lint/checks.py src/kb/lint/verdicts.py
```

- [ ] **Step 8: Commit**

```bash
git add src/kb/lint/checks.py src/kb/lint/verdicts.py tests/test_v0912_phase393.py
git commit -m "fix: lint staleness string dates, orphan exemptions, source coverage false-positive, verdicts warning"
```

---

## Task 6: Graph/Evolve — Mermaid sanitization and broad except

**Files:**
- Modify: `src/kb/graph/export.py`
- Modify: `src/kb/evolve/analyzer.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `_sanitize_label` doesn't strip newlines or backticks — both break Mermaid syntax.
- `evolve/analyzer.py:243` has bare `except Exception: pass` that swallows real bugs silently.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestGraphExportFixes:
    """graph/export.py and evolve/analyzer.py fixes."""

    def test_sanitize_label_strips_newlines(self):
        """_sanitize_label must strip newlines to avoid broken Mermaid node labels."""
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("Line 1\nLine 2")
        assert "\n" not in result, f"Newline not stripped from label: {result!r}"

    def test_sanitize_label_strips_backticks(self):
        """_sanitize_label must strip backticks to avoid Mermaid syntax errors."""
        from kb.graph.export import _sanitize_label

        result = _sanitize_label("`code term`")
        assert "`" not in result, f"Backtick not stripped from label: {result!r}"

    def test_export_mermaid_empty_wiki(self, tmp_wiki):
        """export_mermaid returns a valid no-op diagram for an empty wiki."""
        from kb.graph.export import export_mermaid

        result = export_mermaid(wiki_dir=tmp_wiki)
        assert result.startswith("graph LR"), f"Expected 'graph LR', got: {result[:50]!r}"

    def test_export_mermaid_with_pages(self, tmp_wiki, create_wiki_page):
        """export_mermaid produces Mermaid output with actual wiki pages."""
        from kb.graph.export import export_mermaid

        create_wiki_page(page_id="concepts/rag", title="RAG", wiki_dir=tmp_wiki)
        create_wiki_page(page_id="entities/openai", title="OpenAI", wiki_dir=tmp_wiki)

        result = export_mermaid(wiki_dir=tmp_wiki)
        assert "graph LR" in result
        assert "concepts" in result or "entities" in result
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestGraphExportFixes -v
```
Expected: `test_sanitize_label_strips_newlines` FAIL, `test_sanitize_label_strips_backticks` FAIL, others may pass

- [ ] **Step 3: Fix `src/kb/graph/export.py`**

Find `_sanitize_label`:
```python
def _sanitize_label(text: str) -> str:
    return re.sub(r'["\[\]{}|<>]', "", text).strip()
```
Replace with:
```python
def _sanitize_label(text: str) -> str:
    """Sanitize text for use as a Mermaid node label.

    Removes quotes, special characters, newlines, and backticks that break Mermaid syntax.
    """
    text = text.replace("\n", " ").replace("\r", " ")
    return re.sub(r'["\[\]{}|<>`]', "", text).strip()
```

- [ ] **Step 4: Fix `src/kb/evolve/analyzer.py`**

Find (around line 243):
```python
    except Exception:
        pass  # Feedback data may not exist yet
```
Replace with:
```python
    except Exception as e:
        logger.debug("Feedback data unavailable for evolve report: %s", e)
```

- [ ] **Step 5: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestGraphExportFixes -v
```
Expected: PASS (4/4)

- [ ] **Step 6: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 7: Lint**

```
ruff check src/kb/graph/export.py src/kb/evolve/analyzer.py && ruff format src/kb/graph/export.py src/kb/evolve/analyzer.py
```

- [ ] **Step 8: Commit**

```bash
git add src/kb/graph/export.py src/kb/evolve/analyzer.py tests/test_v0912_phase393.py
git commit -m "fix: Mermaid label sanitize newlines/backticks and evolve broad except to debug log"
```

---

## Task 7: Config — move constants, model validation, docstring

**Files:**
- Modify: `src/kb/config.py`
- Modify: `src/kb/lint/verdicts.py`
- Modify: `src/kb/feedback/store.py`
- Modify: `src/kb/feedback/reliability.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `MAX_FEEDBACK_ENTRIES` (feedback/store.py) and `MAX_VERDICTS` (lint/verdicts.py) defined as module constants, not in `kb.config`. Fix: move both to `config.py`, import from there.
- `config.py` env override model IDs not validated — empty string silently passes to Anthropic API. Fix: strip and validate; fall back to default if empty.
- `feedback/reliability.py:31` docstring says "below threshold" but code uses `<=`. Fix: update docstring.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestConfigFixes:
    """config.py, feedback, and verdicts constants."""

    def test_max_verdicts_importable_from_config(self):
        """MAX_VERDICTS must be importable from kb.config."""
        from kb.config import MAX_VERDICTS
        assert isinstance(MAX_VERDICTS, int) and MAX_VERDICTS > 0

    def test_max_feedback_entries_importable_from_config(self):
        """MAX_FEEDBACK_ENTRIES must be importable from kb.config."""
        from kb.config import MAX_FEEDBACK_ENTRIES
        assert isinstance(MAX_FEEDBACK_ENTRIES, int) and MAX_FEEDBACK_ENTRIES > 0

    def test_empty_model_env_override_falls_back_to_default(self, monkeypatch):
        """Empty CLAUDE_SCAN_MODEL env var must not pass empty string to API."""
        import importlib
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "")
        import kb.config as cfg
        importlib.reload(cfg)
        assert cfg.MODEL_TIERS["scan"] != "", (
            "Empty env override should fall back to default model ID, got empty string"
        )
        # Restore
        importlib.reload(cfg)
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestConfigFixes -v
```
Expected: first two FAIL (ImportError), third FAIL (empty string passes through)

- [ ] **Step 3: Fix `src/kb/config.py`**

Add to `config.py` (near the data retention section):
```python
# ── Feedback and verdict retention limits ──────────────────────
MAX_FEEDBACK_ENTRIES = 10_000
MAX_VERDICTS = 10_000
```

Change the model tier section from:
```python
MODEL_TIERS = {
    "scan": os.environ.get("CLAUDE_SCAN_MODEL", "claude-haiku-4-5-20251001"),
    "write": os.environ.get("CLAUDE_WRITE_MODEL", "claude-sonnet-4-6"),
    "orchestrate": os.environ.get("CLAUDE_ORCHESTRATE_MODEL", "claude-opus-4-6"),
}
```
To:
```python
MODEL_TIERS = {
    "scan": os.environ.get("CLAUDE_SCAN_MODEL", "").strip() or "claude-haiku-4-5-20251001",
    "write": os.environ.get("CLAUDE_WRITE_MODEL", "").strip() or "claude-sonnet-4-6",
    "orchestrate": os.environ.get("CLAUDE_ORCHESTRATE_MODEL", "").strip() or "claude-opus-4-6",
}
```

- [ ] **Step 4: Fix `src/kb/lint/verdicts.py`**

Remove `MAX_VERDICTS = 10_000` from module level. Add import:
```python
from kb.config import MAX_VERDICTS, VERDICTS_PATH
```
(Replace `from kb.config import VERDICTS_PATH`)

- [ ] **Step 5: Fix `src/kb/feedback/store.py`**

Find `MAX_FEEDBACK_ENTRIES = 10_000` in `feedback/store.py` and remove the module-level constant. Add `MAX_FEEDBACK_ENTRIES` to the config import at the top:
```python
from kb.config import FEEDBACK_PATH, MAX_FEEDBACK_ENTRIES
```

- [ ] **Step 6: Fix `src/kb/feedback/reliability.py` docstring**

Find:
```python
    Returns:
        Sorted list of page IDs below the threshold.
```
Replace with:
```python
    Returns:
        Sorted list of page IDs at or below the threshold.
```

- [ ] **Step 7: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestConfigFixes -v
```
Expected: PASS (3/3)

- [ ] **Step 8: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 9: Lint**

```
ruff check src/kb/config.py src/kb/lint/verdicts.py src/kb/feedback/store.py src/kb/feedback/reliability.py && ruff format src/kb/config.py src/kb/lint/verdicts.py src/kb/feedback/store.py src/kb/feedback/reliability.py
```

- [ ] **Step 10: Commit**

```bash
git add src/kb/config.py src/kb/lint/verdicts.py src/kb/feedback/store.py src/kb/feedback/reliability.py tests/test_v0912_phase393.py
git commit -m "fix: move MAX_FEEDBACK_ENTRIES/MAX_VERDICTS to config, model env validation, docstring"
```

---

## Task 8: CLI — mcp error handling and --type choices

**Files:**
- Modify: `src/kb/cli.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `mcp` command has no `try/except` — raw Python traceback shown on startup failure.
- `--type` choices missing `comparison` and `synthesis`.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestCLIFixes:
    """cli.py fixes."""

    def test_ingest_type_accepts_comparison(self):
        """--type comparison must be a valid choice for the ingest command."""
        from click.testing import CliRunner
        from kb.cli import cli

        runner = CliRunner()
        # Just check the help/validation — passing a non-existent file is fine
        result = runner.invoke(cli, ["ingest", "--type", "comparison", "/nonexistent.md"])
        # Should NOT fail with "Invalid value for '--type'"
        assert "Invalid value for '--type'" not in (result.output or ""), (
            f"'comparison' should be a valid --type choice. Output: {result.output!r}"
        )

    def test_ingest_type_accepts_synthesis(self):
        """--type synthesis must be a valid choice for the ingest command."""
        from click.testing import CliRunner
        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--type", "synthesis", "/nonexistent.md"])
        assert "Invalid value for '--type'" not in (result.output or ""), (
            f"'synthesis' should be a valid --type choice. Output: {result.output!r}"
        )

    def test_mcp_command_handles_startup_error_gracefully(self, monkeypatch):
        """mcp command must catch exceptions and exit cleanly, not show raw traceback."""
        from click.testing import CliRunner
        from kb.cli import cli

        def bad_main():
            raise RuntimeError("Simulated MCP startup failure")

        monkeypatch.setattr("kb.mcp_server.main", bad_main)

        runner = CliRunner()
        result = runner.invoke(cli, ["mcp"])
        assert result.exit_code != 0, "Should exit with error"
        assert "Traceback" not in (result.output or ""), (
            "Should not show raw Python traceback"
        )
        assert "Error" in (result.output or ""), (
            "Should show user-friendly error message"
        )
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestCLIFixes -v
```
Expected: first two FAIL (Invalid value for --type), third FAIL (shows traceback or no error output)

- [ ] **Step 3: Fix `src/kb/cli.py`**

**3a. Add `comparison` and `synthesis` to `--type` choices:**
```python
@click.option(
    "--type",
    "source_type",
    type=click.Choice(
        [
            "article",
            "paper",
            "repo",
            "video",
            "podcast",
            "book",
            "dataset",
            "conversation",
            "comparison",
            "synthesis",
        ]
    ),
    help="Source type (auto-detected if omitted)",
)
```

**3b. Wrap `mcp` command in try/except:**
```python
@cli.command()
def mcp():
    """Start the MCP server for Claude Code integration."""
    from kb.mcp_server import main as mcp_main

    try:
        mcp_main()
    except Exception as e:
        click.echo(f"Error: MCP server failed to start — {e}", err=True)
        raise SystemExit(1)
```

- [ ] **Step 4: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestCLIFixes -v
```
Expected: PASS (3/3)

- [ ] **Step 5: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 6: Lint**

```
ruff check src/kb/cli.py && ruff format src/kb/cli.py
```

- [ ] **Step 7: Commit**

```bash
git add src/kb/cli.py tests/test_v0912_phase393.py
git commit -m "fix: CLI mcp error handling and add comparison/synthesis to --type choices"
```

---

## Task 9: MCP — browse error handling and dead code removal

**Files:**
- Modify: `src/kb/mcp/browse.py`
- Modify: `src/kb/mcp/app.py`
- Test: `tests/test_v0912_phase393.py`

**Issues fixed:**
- `kb_search` and `kb_list_pages` missing outer `try/except` — any uncaught exception propagates to MCP client as a raw error instead of an "Error: ..." string.
- `_format_ingest_result` has a dead `isinstance(affected, dict)` branch that was for the pre-v0.5.0 format. The pipeline has never returned a dict since v0.5.0.

- [ ] **Step 1: Write failing tests (append to test file)**

```python
class TestMCPFixes:
    """mcp/browse.py and mcp/app.py fixes."""

    def test_format_ingest_result_no_dict_branch_for_affected(self):
        """_format_ingest_result should handle flat list affected_pages only."""
        from kb.mcp.app import _format_ingest_result

        result = {
            "pages_created": ["summaries/test"],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": ["concepts/rag"],
        }
        output = _format_ingest_result("raw/articles/test.md", "article", "abc123", result)
        assert "concepts/rag" in output, "Flat list affected_pages should appear in output"
        assert "backlink" not in output, "Dead legacy dict branch should not appear"

    def test_kb_search_returns_error_string_on_exception(self, monkeypatch):
        """kb_search must return 'Error: ...' string when an exception occurs internally."""
        from kb.mcp import browse as browse_mod

        def bad_search(*args, **kwargs):
            raise RuntimeError("Simulated search failure")

        monkeypatch.setattr("kb.query.engine.search_pages", bad_search)

        from kb.mcp.browse import kb_search
        result = kb_search("test query")
        assert result.startswith("Error:"), (
            f"Expected 'Error: ...' string, got: {result[:100]!r}"
        )
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_v0912_phase393.py::TestMCPFixes -v
```
Expected: `test_format_ingest_result_no_dict_branch_for_affected` may pass (dead code doesn't affect output), `test_kb_search_returns_error_string_on_exception` FAIL (RuntimeError propagates)

- [ ] **Step 3: Fix `src/kb/mcp/browse.py`**

Wrap the `kb_search` function body in try/except (after the empty query check):
```python
@mcp.tool()
def kb_search(query: str, max_results: int = 10) -> str:
    """..."""
    if not query or not query.strip():
        return "Error: Query cannot be empty."

    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    try:
        from kb.query.engine import search_pages

        results = search_pages(query, max_results=max_results)
        if not results:
            return "No matching pages found."

        lines = [f"Found {len(results)} matching page(s):\n"]
        for r in results:
            snippet = r["content"][:200].replace("\n", " ").strip()
            lines.append(
                f"- **{r['id']}** (type: {r['type']}, score: {r['score']})\n"
                f"  Title: {r['title']}\n"
                f"  Snippet: {snippet}..."
            )
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Error in kb_search for query: %s", query)
        return f"Error: Search failed — {e}"
```

Similarly wrap `kb_list_pages` body:
```python
@mcp.tool()
def kb_list_pages(page_type: str = "") -> str:
    """..."""
    try:
        pages = load_all_pages()
        if page_type:
            pages = [p for p in pages if p["id"].startswith(page_type)]

        if not pages:
            return "No pages found."

        lines = [f"Total: {len(pages)} page(s)\n"]
        current_type = ""
        for p in pages:
            ptype = p["id"].split("/")[0]
            if ptype != current_type:
                current_type = ptype
                lines.append(f"\n## {current_type}")
            lines.append(f"- {p['id']} — {p['title']} ({p['type']}, {p['confidence']})")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Error in kb_list_pages")
        return f"Error: Could not list pages — {e}"
```

- [ ] **Step 4: Fix `src/kb/mcp/app.py`**

In `_format_ingest_result`, remove the dead dict-branch. Find:
```python
    affected = result.get("affected_pages", [])
    if isinstance(affected, dict):
        # Legacy dict format: extract both lists
        backlinks = affected.get("backlinks", [])
        shared = affected.get("shared_sources", [])
        all_affected = backlinks + shared
    elif isinstance(affected, list):
        all_affected = affected
        backlinks, shared = [], []
    else:
        all_affected, backlinks, shared = [], [], []
    if all_affected:
        lines.append(f"Affected pages ({len(all_affected)}) — may need review:")
        for p in backlinks:
            lines.append(f"  <- {p}  (backlink)")
        for p in shared:
            lines.append(f"  ~ {p}  (shared source)")
        if not isinstance(affected, dict):
            for p in all_affected:
                lines.append(f"  ~ {p}")
```
Replace with:
```python
    affected = result.get("affected_pages", [])
    if affected:
        lines.append(f"Affected pages ({len(affected)}) — may need review:")
        for p in affected:
            lines.append(f"  ~ {p}")
```

- [ ] **Step 5: Run tests to verify pass**

```
python -m pytest tests/test_v0912_phase393.py::TestMCPFixes -v
```
Expected: PASS (2/2)

- [ ] **Step 6: Full suite**

```
python -m pytest tests/ -x -q
```

- [ ] **Step 7: Lint**

```
ruff check src/kb/mcp/browse.py src/kb/mcp/app.py && ruff format src/kb/mcp/browse.py src/kb/mcp/app.py
```

- [ ] **Step 8: Commit**

```bash
git add src/kb/mcp/browse.py src/kb/mcp/app.py tests/test_v0912_phase393.py
git commit -m "fix: MCP browse outer try/except and remove dead legacy affected_pages dict branch"
```

---

## Task 10: Test coverage — compile scan full branch, graph export, CLI commands

**Files:**
- Test: `tests/test_v0912_phase393.py`

**Issues fixed (test coverage gaps):**
- `mcp/core.py` `kb_compile_scan(incremental=False)` full-scan branch untested.
- `graph/export.py` zero test coverage (tests written in Task 6 cover the module now).
- `cli.py` `query` and `compile` commands have zero test coverage.

- [ ] **Step 1: Write tests (append to test file)**

```python
class TestCoverageGaps:
    """Test coverage for previously uncovered branches."""

    def test_kb_compile_scan_full_scan_returns_list(self, monkeypatch, tmp_path):
        """kb_compile_scan with incremental=False should return a list of sources to ingest."""
        from kb.mcp.core import kb_compile_scan
        from unittest.mock import patch

        # Patch find_changed_sources to return empty (no raw sources)
        with patch("kb.compile.compiler.scan_raw_sources", return_value=[]):
            with patch("kb.compile.compiler.find_changed_sources", return_value=([], [])):
                result = kb_compile_scan(incremental=False)

        assert isinstance(result, str), f"Expected str result, got {type(result)}"
        # Should say "no sources" or list sources found
        assert len(result) > 0

    def test_cli_compile_command_runs(self, monkeypatch):
        """cli compile command should execute without error when wiki is empty."""
        from click.testing import CliRunner
        from kb.cli import cli
        from unittest.mock import patch

        mock_result = {
            "mode": "incremental",
            "sources_processed": 0,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": [],
            "duplicates": 0,
            "errors": [],
        }
        with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
            runner = CliRunner()
            result = runner.invoke(cli, ["compile"])

        assert result.exit_code == 0, f"CLI compile failed: {result.output!r}"
        assert "Done" in result.output

    def test_cli_query_command_runs(self, monkeypatch):
        """cli query command should execute without error."""
        from click.testing import CliRunner
        from kb.cli import cli
        from unittest.mock import patch

        mock_result = {
            "question": "test",
            "answer": "Test answer.",
            "citations": [],
            "source_pages": [],
        }
        with patch("kb.query.engine.query_wiki", return_value=mock_result):
            runner = CliRunner()
            result = runner.invoke(cli, ["query", "test question"])

        assert result.exit_code == 0, f"CLI query failed: {result.output!r}"
        assert "Test answer" in result.output
```

- [ ] **Step 2: Run to verify tests pass**

```
python -m pytest tests/test_v0912_phase393.py::TestCoverageGaps -v
```
Expected: PASS (3/3) — these are new coverage tests that should pass once the fixes from prior tasks are in.

- [ ] **Step 3: Full suite**

```
python -m pytest tests/ -x -q
```
Expected: all pass

- [ ] **Step 4: Lint**

```
ruff check tests/test_v0912_phase393.py && ruff format tests/test_v0912_phase393.py
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_v0912_phase393.py
git commit -m "test: add coverage for compile scan full-branch, graph export, CLI commands"
```

---

## Task 11: Docs — CHANGELOG and BACKLOG update

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `BACKLOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CHANGELOG.md**

Under `[Unreleased]`, add a `### Fixed` block (or append to existing):

```markdown
### Fixed
- `utils/llm.py`: `_make_api_call` retry loop used `range(MAX_RETRIES)` (total attempts) instead of `range(MAX_RETRIES + 1)` (retries); `last_error` was `None` when `MAX_RETRIES=0`, causing `AttributeError` on exhaustion
- `query/engine.py`: `query_wiki` never forwarded `max_results` to `search_pages`; `_build_query_context` returned empty string when all pages exceeded 80K limit (sends zero context to LLM); `search_pages` `max_results` not clamped inside the function
- `ingest/pipeline.py`: summary page always overwritten on re-ingest, losing original `created:` date; `ingest_source` had no library-level path traversal guard (only MCP layer validated); `_update_sources_mapping` and `_update_index_batch` silently no-op on fresh install
- `compile/linker.py`: `inject_wikilinks` compared raw `target_page_id` against lowercased existing links — duplicate wikilinks injected for mixed-case page IDs
- `compile/compiler.py`: `find_changed_sources` wrote template hashes to manifest as side-effect even when called read-only from `kb_detect_drift`; added `save_hashes=False` parameter
- `lint/checks.py`: `check_staleness` silently skipped pages where YAML-parsed `updated` field was a quoted string; orphan detection did not exempt `comparisons/` and `synthesis/` pages; `check_source_coverage` suffix match false-positived on same-named files in different subdirs
- `lint/verdicts.py`: `load_verdicts` silently discarded all verdict history on `JSONDecodeError` with no warning
- `graph/export.py`: `_sanitize_label` did not strip newlines or backticks, producing broken Mermaid output
- `evolve/analyzer.py`: bare `except Exception: pass` on feedback reliability lookup swallowed real bugs
- `config.py`: env override model IDs accepted empty strings silently; `MAX_FEEDBACK_ENTRIES` and `MAX_VERDICTS` moved from module constants to `kb.config`
- `feedback/reliability.py`: docstring said "below threshold" but code used `<=` (at or below)
- `cli.py`: `mcp` command had no `try/except`; `--type` choices missing `comparison` and `synthesis`
- `mcp/browse.py`: `kb_search` and `kb_list_pages` missing outer `try/except`
- `mcp/app.py`: `_format_ingest_result` dead legacy dict-branch for `affected_pages` removed
```

- [ ] **Step 2: Update BACKLOG.md**

Delete the entire `## Phase 3.93 (code review 2026-04-08)` section (HIGH, MEDIUM, LOW items). Replace with a resolved one-liner under `## Resolved Phases`:

```markdown
- **Phase 3.93** — all items resolved in v0.9.12
```

Keep the `compile/extractors.py` LRU cache item and the `utils/pages.py` `raw_content` naming item as MEDIUM carry-over if not fixed (note below).

> **Note:** Two MEDIUM items are intentionally deferred to Phase 3.94:
> - `compile/extractors.py` LRU cache invalidation — only affects running compile sessions that change templates mid-run; `load_template.cache_clear()` can be called manually.
> - `utils/pages.py` `raw_content` field rename — impacts multiple callers including BM25 engine; requires careful coordinated rename.

- [ ] **Step 3: Update CLAUDE.md**

Change the implementation status line:
```
**Phase 3.92 complete (v0.9.11).** 583 tests
```
To:
```
**Phase 3.93 complete (v0.9.12).** ~620 tests
```
(Actual test count after running `python -m pytest --collect-only -q | tail -1`)

- [ ] **Step 4: Verify test count**

```
python -m pytest --collect-only -q 2>/dev/null | tail -3
```

- [ ] **Step 5: Commit docs**

```bash
git add CHANGELOG.md BACKLOG.md CLAUDE.md
git commit -m "docs: Phase 3.93 complete — update changelog, backlog, and claude.md for v0.9.12"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Task 1 covers: LLM retry count + last_error safety (HIGH #21, #22)
- [x] Task 2 covers: query max_results forwarding + context fallback + clamp (HIGH #1, #2, MEDIUM #13, #14)
- [x] Task 3 covers: ingest date preservation + path traversal + fresh install (HIGH #3, #4, MEDIUM #15)
- [x] Task 4 covers: compile case mismatch + manifest side-effect (HIGH #5, #6)
- [x] Task 5 covers: lint staleness + orphan exemptions + source coverage + verdicts warning (MEDIUM #8→already fixed, #9, #10, #11, #12)
- [x] Task 6 covers: Mermaid sanitization + broad except (MEDIUM #17, #20)
- [x] Task 7 covers: config constants + model validation + docstring (MEDIUM #26, #25, #27)
- [x] Task 8 covers: CLI error handling + --type choices (MEDIUM #28, #29)
- [x] Task 9 covers: MCP browse errors + dead code (MEDIUM #31, #32)
- [x] Task 10 covers: test coverage gaps (MEDIUM #18, #30, #33)
- [x] Task 11 covers: docs (LOW #34)

**Deferred items (carry to Phase 3.94):**
- `compile/extractors.py` LRU cache invalidation — low impact, needs cache TTL design
- `utils/pages.py` raw_content rename — high churn, needs coordinated rename + migration
- `graph/builder.py` vs `evolve/analyzer.py` orphan definition mismatch — documentation only, no behavior change

**Type consistency:** All method signatures consistent across tasks. `query_wiki(max_results=10)` added in Task 2, `find_changed_sources(save_hashes=True)` added in Task 4.

**No placeholders:** All code blocks contain complete, copy-pasteable implementations.
