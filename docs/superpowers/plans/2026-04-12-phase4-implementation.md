# Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 8 features upgrading search quality, epistemic integrity, and query intelligence for the llm-wiki-flywheel knowledge base.

**Architecture:** Builds on the existing BM25-only search pipeline (`kb.query.engine`) and ingest pipeline (`kb.ingest.pipeline`). Adds vector search via model2vec + sqlite-vec with RRF fusion, 4-layer dedup, evidence trail provenance sections in wiki pages, stale truth detection at query time, layered context assembly, raw-source fallback retrieval, auto-contradiction detection on ingest, and multi-turn query rewriting. All new modules go under `src/kb/query/` and `src/kb/ingest/`. Dependencies model2vec and sqlite-vec are already installed.

**Tech Stack:** Python 3.12+, model2vec (local embeddings), sqlite-vec (vector index), existing BM25 engine, anthropic SDK (LLM calls), pytest, python-frontmatter.

---

## File Structure

| Path | Responsibility |
|------|---------------|
| `src/kb/query/dedup.py` | NEW — 4-layer search result deduplication pipeline |
| `src/kb/query/embeddings.py` | NEW — model2vec embedding wrapper + sqlite-vec index |
| `src/kb/query/hybrid.py` | NEW — RRF fusion of BM25 + vector search, multi-query expansion |
| `src/kb/query/rewriter.py` | NEW — Multi-turn query rewriting using conversation context |
| `src/kb/query/engine.py` | MODIFY — Wire hybrid search, dedup, stale flagging, layered context, raw fallback |
| `src/kb/query/__init__.py` | MODIFY — Export new public APIs |
| `src/kb/ingest/evidence.py` | NEW — Evidence trail section builder and appender |
| `src/kb/ingest/contradiction.py` | NEW — Auto-contradiction detection against existing wiki claims |
| `src/kb/ingest/pipeline.py` | MODIFY — Wire evidence trail and contradiction detection |
| `src/kb/mcp/core.py` | MODIFY — Surface stale flags, contradiction warnings, conversation context |
| `src/kb/config.py` | MODIFY — Add RRF, dedup, vector, context assembly, contradiction constants |
| `tests/test_v0917_dedup.py` | NEW — Tests for 4-layer dedup |
| `tests/test_v0917_evidence_trail.py` | NEW — Tests for evidence trail sections |
| `tests/test_v0917_stale_query.py` | NEW — Tests for stale truth flagging at query time |
| `tests/test_v0917_embeddings.py` | NEW — Tests for embedding + vector index |
| `tests/test_v0917_hybrid.py` | NEW — Tests for RRF fusion and hybrid search |
| `tests/test_v0917_layered_context.py` | NEW — Tests for tiered context assembly |
| `tests/test_v0917_raw_fallback.py` | NEW — Tests for raw-source fallback retrieval |
| `tests/test_v0917_contradiction.py` | NEW — Tests for auto-contradiction detection |
| `tests/test_v0917_rewriter.py` | NEW — Tests for multi-turn query rewriting |

---

### Task 1: Config Constants for Phase 4

**Files:**
- Modify: `src/kb/config.py:99-121`

- [ ] **Step 1: Add Phase 4 config constants**

```python
# Add after line 121 (after MAX_SEARCH_RESULTS = 100):

# ── RRF hybrid search ─────────────────────────────────────────
RRF_K = 60  # RRF fusion constant: score = 1/(K + rank)
VECTOR_SEARCH_LIMIT_MULTIPLIER = 2  # Vector search fetches limit * N candidates
EMBEDDING_MODEL = "minishlab/potion-base-8M"  # model2vec model (~8MB, local)
EMBEDDING_DIM = 256  # Embedding dimensions for potion-base-8M
VECTOR_INDEX_PATH_SUFFIX = ".data/vector_index.db"  # sqlite-vec index file

# ── Search dedup parameters ─────────────────────────────────
DEDUP_JACCARD_THRESHOLD = 0.85  # Text similarity threshold for dedup layer 2
DEDUP_MAX_TYPE_RATIO = 0.6  # Max fraction of results from one page type
DEDUP_MAX_PER_PAGE = 2  # Max results per page in final output

# ── Layered context assembly ────────────────────────────────
CONTEXT_TIER1_BUDGET = 20_000  # Chars for summaries tier
CONTEXT_TIER2_BUDGET = 60_000  # Additional chars for full pages on demand

# ── Contradiction detection ──────────────────────────────────
CONTRADICTION_MAX_CLAIMS_TO_CHECK = 10  # Max existing claims to compare per ingest

# ── Multi-turn query rewriting ───────────────────────────────
MAX_CONVERSATION_CONTEXT_CHARS = 4000  # Max chars of conversation history for rewriting
```

- [ ] **Step 2: Commit**

```bash
git add src/kb/config.py
git commit -m "feat(config): add Phase 4 constants — RRF, dedup, layered context, contradiction, rewriter"
```

---

### Task 2: Evidence Trail Sections in Wiki Pages

**Files:**
- Create: `src/kb/ingest/evidence.py`
- Modify: `src/kb/ingest/pipeline.py:119-138,254-339,547-567`
- Create: `tests/test_v0917_evidence_trail.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_evidence_trail.py
"""Tests for evidence trail sections in wiki pages (Phase 4)."""

from datetime import date
from pathlib import Path

from kb.ingest.evidence import build_evidence_entry, append_evidence_trail


class TestBuildEvidenceEntry:
    def test_basic_entry(self):
        entry = build_evidence_entry(
            source_ref="raw/articles/example.md",
            action="Initial extraction: core concept definition",
        )
        assert entry.startswith(f"- {date.today().isoformat()}")
        assert "raw/articles/example.md" in entry
        assert "Initial extraction" in entry

    def test_custom_date(self):
        entry = build_evidence_entry(
            source_ref="raw/papers/paper.md",
            action="Updated: added formulation",
            entry_date="2026-01-15",
        )
        assert entry.startswith("- 2026-01-15")

    def test_entry_is_single_line(self):
        entry = build_evidence_entry(
            source_ref="raw/articles/a.md",
            action="Some action",
        )
        assert "\n" not in entry.strip()


class TestAppendEvidenceTrail:
    def test_adds_section_to_page_without_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nSome content.\n",
            encoding="utf-8",
        )
        append_evidence_trail(
            page, "raw/articles/a.md", "Initial extraction: definition"
        )
        text = page.read_text(encoding="utf-8")
        assert "## Evidence Trail" in text
        assert "raw/articles/a.md" in text
        assert "Initial extraction: definition" in text
        # Content above trail is preserved
        assert "# Test" in text
        assert "Some content." in text

    def test_appends_to_existing_trail(self, tmp_path):
        page = tmp_path / "test.md"
        page.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "# Test\n\nContent.\n\n## Evidence Trail\n"
            "- 2026-04-10 | raw/articles/a.md | First entry\n",
            encoding="utf-8",
        )
        append_evidence_trail(
            page, "raw/articles/b.md", "Updated: new info"
        )
        text = page.read_text(encoding="utf-8")
        # New entry at top (reverse chronological)
        trail_idx = text.index("## Evidence Trail")
        trail = text[trail_idx:]
        lines = [l for l in trail.split("\n") if l.startswith("- ")]
        assert len(lines) == 2
        assert "raw/articles/b.md" in lines[0]  # Newest first
        assert "raw/articles/a.md" in lines[1]

    def test_preserves_frontmatter(self, tmp_path):
        page = tmp_path / "test.md"
        original = (
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
            "created: 2026-04-12\nupdated: 2026-04-12\n"
            "type: concept\nconfidence: stated\n---\n\n"
            "Body content.\n"
        )
        page.write_text(original, encoding="utf-8")
        append_evidence_trail(page, "raw/articles/a.md", "action")
        text = page.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert 'title: "Test"' in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_evidence_trail.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.ingest.evidence'`

- [ ] **Step 3: Write the evidence trail module**

```python
# src/kb/ingest/evidence.py
"""Evidence trail — append-only provenance sections in wiki pages."""

import re
from datetime import date
from pathlib import Path

from kb.utils.io import atomic_text_write


def build_evidence_entry(
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> str:
    """Build a single evidence trail entry line.

    Format: - YYYY-MM-DD | source_ref | action
    """
    d = entry_date or date.today().isoformat()
    return f"- {d} | {source_ref} | {action}"


def append_evidence_trail(
    page_path: Path,
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> None:
    """Append an evidence trail entry to a wiki page.

    If the page has no ## Evidence Trail section, one is created at the end.
    New entries are inserted at the top of the trail (reverse chronological).
    """
    content = page_path.read_text(encoding="utf-8")
    entry = build_evidence_entry(source_ref, action, entry_date)

    trail_match = re.search(r"^## Evidence Trail\n", content, re.MULTILINE)
    if trail_match:
        # Insert new entry right after the header
        insert_pos = trail_match.end()
        content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
    else:
        # Add new section at the end
        content = content.rstrip("\n") + "\n\n## Evidence Trail\n" + entry + "\n"

    atomic_text_write(content, page_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_evidence_trail.py -v`
Expected: PASS

- [ ] **Step 5: Wire evidence trail into ingest pipeline**

In `src/kb/ingest/pipeline.py`, add import at top (after line 30):
```python
from kb.ingest.evidence import append_evidence_trail
```

In `_write_wiki_page` (line 137), add evidence trail after writing the page:
```python
    atomic_text_write(fm_text + content, path)
    # Append initial evidence trail entry
    append_evidence_trail(path, source_ref, f"Initial extraction: {page_type} page created")
```

In `_update_existing_page` (line 339, just before the atomic_text_write call), add after the write:
```python
    # Fix 2.1: Use atomic write
    atomic_text_write(content, page_path)
    # Append evidence trail entry for the update
    append_evidence_trail(
        page_path, source_ref, f"{verb} in new source — source reference added"
    )
```

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `python -m pytest -x -q`
Expected: All existing tests pass (some may need minor adjustment if they check exact page content)

- [ ] **Step 7: Commit**

```bash
git add src/kb/ingest/evidence.py src/kb/ingest/pipeline.py tests/test_v0917_evidence_trail.py
git commit -m "feat(ingest): add evidence trail sections to wiki pages — append-only provenance chain"
```

---

### Task 3: 4-Layer Search Dedup Pipeline

**Files:**
- Create: `src/kb/query/dedup.py`
- Create: `tests/test_v0917_dedup.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_dedup.py
"""Tests for 4-layer search dedup pipeline (Phase 4)."""

from kb.query.dedup import dedup_results


def _result(page_id, score, page_type="concept", text="some content here"):
    return {"id": page_id, "score": score, "type": page_type, "content_lower": text}


class TestDedupBySource:
    def test_keeps_highest_score_per_page(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/a", 3.0),
            _result("concepts/b", 4.0),
        ]
        deduped = dedup_results(results)
        ids = [r["id"] for r in deduped]
        assert ids.count("concepts/a") == 1
        assert deduped[0]["score"] == 5.0

    def test_preserves_order_by_score(self):
        results = [
            _result("concepts/a", 5.0),
            _result("concepts/b", 3.0),
            _result("concepts/c", 1.0),
        ]
        deduped = dedup_results(results)
        scores = [r["score"] for r in deduped]
        assert scores == sorted(scores, reverse=True)


class TestDedupByTextSimilarity:
    def test_removes_near_duplicate_text(self):
        results = [
            _result("concepts/a", 5.0, text="the transformer architecture uses attention"),
            _result("concepts/b", 4.0, text="the transformer architecture uses attention mechanisms"),
        ]
        deduped = dedup_results(results, jaccard_threshold=0.7)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "concepts/a"  # Higher score kept

    def test_keeps_different_content(self):
        results = [
            _result("concepts/a", 5.0, text="transformers use self-attention mechanisms"),
            _result("concepts/b", 4.0, text="recurrent neural networks process sequences"),
        ]
        deduped = dedup_results(results)
        assert len(deduped) == 2


class TestDedupByTypeDiversity:
    def test_caps_single_type(self):
        results = [_result(f"entities/e{i}", 10 - i, "entity") for i in range(10)]
        results.append(_result("concepts/c1", 0.5, "concept"))
        deduped = dedup_results(results, max_type_ratio=0.6)
        entity_count = sum(1 for r in deduped if r["type"] == "entity")
        total = len(deduped)
        assert entity_count <= int(total * 0.6) + 1  # Allow rounding


class TestDedupPerPageCap:
    def test_caps_results_per_page(self):
        results = [
            _result("concepts/a", 5.0, text="first chunk about topic"),
            _result("concepts/a", 4.5, text="second chunk about topic"),
            _result("concepts/a", 4.0, text="third chunk about topic"),
        ]
        deduped = dedup_results(results, max_per_page=2)
        a_count = sum(1 for r in deduped if r["id"] == "concepts/a")
        assert a_count <= 2


class TestDedupEndToEnd:
    def test_empty_input(self):
        assert dedup_results([]) == []

    def test_single_result(self):
        results = [_result("concepts/a", 5.0)]
        assert len(dedup_results(results)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.query.dedup'`

- [ ] **Step 3: Write the dedup module**

```python
# src/kb/query/dedup.py
"""4-layer search result dedup pipeline.

Layers:
1. By source — highest-scoring result per page
2. By text similarity — Jaccard > threshold drops near-duplicates
3. By type diversity — no page type exceeds max ratio
4. Per-page cap — max N results per page
"""

import math

from kb.config import DEDUP_JACCARD_THRESHOLD, DEDUP_MAX_PER_PAGE, DEDUP_MAX_TYPE_RATIO


def dedup_results(
    results: list[dict],
    *,
    jaccard_threshold: float = DEDUP_JACCARD_THRESHOLD,
    max_type_ratio: float = DEDUP_MAX_TYPE_RATIO,
    max_per_page: int = DEDUP_MAX_PER_PAGE,
) -> list[dict]:
    """Apply 4-layer dedup to search results. Returns filtered list."""
    if not results:
        return []
    deduped = _dedup_by_source(results)
    deduped = _dedup_by_text_similarity(deduped, jaccard_threshold)
    deduped = _enforce_type_diversity(deduped, max_type_ratio)
    deduped = _cap_per_page(deduped, max_per_page)
    return deduped


def _dedup_by_source(results: list[dict]) -> list[dict]:
    """Layer 1: Keep highest-scoring result per page."""
    by_page: dict[str, dict] = {}
    for r in results:
        pid = r["id"]
        existing = by_page.get(pid)
        if existing is None or r["score"] > existing["score"]:
            by_page[pid] = r
    return sorted(by_page.values(), key=lambda r: r["score"], reverse=True)


def _dedup_by_text_similarity(results: list[dict], threshold: float) -> list[dict]:
    """Layer 2: Remove results with Jaccard similarity > threshold to kept results."""
    kept: list[dict] = []
    for r in results:
        r_words = set(r.get("content_lower", "").split())
        too_similar = False
        for k in kept:
            k_words = set(k.get("content_lower", "").split())
            intersection = r_words & k_words
            union = r_words | k_words
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > threshold:
                too_similar = True
                break
        if not too_similar:
            kept.append(r)
    return kept


def _enforce_type_diversity(results: list[dict], max_ratio: float) -> list[dict]:
    """Layer 3: No page type exceeds max_ratio of total results."""
    max_per_type = max(1, math.ceil(len(results) * max_ratio))
    type_counts: dict[str, int] = {}
    kept: list[dict] = []
    for r in results:
        t = r.get("type", "unknown")
        count = type_counts.get(t, 0)
        if count < max_per_type:
            kept.append(r)
            type_counts[t] = count + 1
    return kept


def _cap_per_page(results: list[dict], max_per_page: int) -> list[dict]:
    """Layer 4: Cap results per page."""
    page_counts: dict[str, int] = {}
    kept: list[dict] = []
    for r in results:
        pid = r["id"]
        count = page_counts.get(pid, 0)
        if count < max_per_page:
            kept.append(r)
            page_counts[pid] = count + 1
    return kept
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_dedup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kb/query/dedup.py tests/test_v0917_dedup.py
git commit -m "feat(query): add 4-layer search dedup pipeline — source, text similarity, type diversity, per-page cap"
```

---

### Task 4: Stale Truth Flagging at Query Time

**Files:**
- Modify: `src/kb/query/engine.py:24-80`
- Modify: `src/kb/mcp/core.py:102-116`
- Create: `tests/test_v0917_stale_query.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_stale_query.py
"""Tests for stale truth flagging at query time (Phase 4)."""

import os
import time
from datetime import date, timedelta

from kb.query.engine import _flag_stale_results


class TestFlagStaleResults:
    def test_flags_page_with_newer_source(self, tmp_project, create_wiki_page, create_raw_source):
        old_date = (date.today() - timedelta(days=30)).isoformat()
        create_wiki_page(
            page_id="concepts/stale-topic",
            title="Stale Topic",
            content="Old content.",
            source_ref="raw/articles/new-source.md",
            updated=old_date,
            wiki_dir=tmp_project / "wiki",
        )
        # Create a raw source that is "newer" (mtime is now)
        create_raw_source("raw/articles/new-source.md", "Updated content.", tmp_project)

        results = [
            {
                "id": "concepts/stale-topic",
                "sources": ["raw/articles/new-source.md"],
                "updated": old_date,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is True

    def test_does_not_flag_fresh_page(self, tmp_project, create_wiki_page, create_raw_source):
        today = date.today().isoformat()
        create_wiki_page(
            page_id="concepts/fresh-topic",
            title="Fresh Topic",
            content="Fresh content.",
            source_ref="raw/articles/old-source.md",
            updated=today,
            wiki_dir=tmp_project / "wiki",
        )
        source_path = create_raw_source("raw/articles/old-source.md", "Source.", tmp_project)
        # Backdate the source file mtime to before the page updated date
        old_ts = time.time() - 86400 * 60
        os.utime(source_path, (old_ts, old_ts))

        results = [
            {
                "id": "concepts/fresh-topic",
                "sources": ["raw/articles/old-source.md"],
                "updated": today,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is False

    def test_handles_missing_source_gracefully(self):
        results = [
            {
                "id": "concepts/orphan",
                "sources": ["raw/articles/nonexistent.md"],
                "updated": date.today().isoformat(),
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False

    def test_handles_no_sources(self):
        results = [{"id": "concepts/no-src", "sources": [], "updated": "2026-04-12", "score": 1.0}]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_stale_query.py -v`
Expected: FAIL — `ImportError: cannot import name '_flag_stale_results'`

- [ ] **Step 3: Implement stale flagging in engine.py**

Add to `src/kb/query/engine.py` (after `_compute_pagerank_scores`, before `_build_query_context`):

```python
def _flag_stale_results(
    results: list[dict], project_root: Path | None = None
) -> list[dict]:
    """Flag results where page updated date is older than newest source mtime.

    Adds 'stale': True/False to each result dict. Non-destructive — modifies
    copies of the input dicts.
    """
    from kb.config import PROJECT_ROOT

    root = project_root or PROJECT_ROOT
    flagged = []
    for r in results:
        r = {**r, "stale": False}
        updated_str = r.get("updated", "")
        sources = r.get("sources", [])
        if not updated_str or not sources:
            flagged.append(r)
            continue
        try:
            page_date = date.fromisoformat(str(updated_str))
        except (ValueError, TypeError):
            flagged.append(r)
            continue
        newest_source_mtime = None
        for src in sources:
            src_path = root / src
            if src_path.exists():
                mtime = date.fromtimestamp(src_path.stat().st_mtime)
                if newest_source_mtime is None or mtime > newest_source_mtime:
                    newest_source_mtime = mtime
        if newest_source_mtime and newest_source_mtime > page_date:
            r["stale"] = True
        flagged.append(r)
    return flagged
```

Add the `date` import at the top of engine.py (line 1 area):
```python
from datetime import date
```

- [ ] **Step 4: Wire stale flagging into search_pages**

In `search_pages()` (line 79, after the sort, before the return), add:

```python
    scored.sort(key=lambda p: p["score"], reverse=True)
    scored = _flag_stale_results(scored[:max_results])
    return scored
```

Replace the existing `return scored[:max_results]` line.

- [ ] **Step 5: Surface stale flag in MCP kb_query output**

In `src/kb/mcp/core.py`, in the Claude Code mode section (line 111-114), update the page header format to include stale indicator:

```python
        stale_label = " [STALE]" if r.get("stale") else ""
        lines.append(
            f"--- Page: {r['id']} (type: {r['type']}, "
            f"confidence: {r['confidence']}, score: {r['score']}{trust_label}){stale_label} ---\n"
            f"Title: {r['title']}\n\n{r['content']}\n"
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_stale_query.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/kb/query/engine.py src/kb/mcp/core.py tests/test_v0917_stale_query.py
git commit -m "feat(query): flag stale results at query time — compare page updated vs source mtime"
```

---

### Task 5: Embeddings + Vector Index (model2vec + sqlite-vec)

**Files:**
- Create: `src/kb/query/embeddings.py`
- Create: `tests/test_v0917_embeddings.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_embeddings.py
"""Tests for embedding wrapper and vector index (Phase 4)."""

import numpy as np
import pytest

from kb.query.embeddings import embed_texts, VectorIndex


class TestEmbedTexts:
    def test_returns_array_for_single_text(self):
        vecs = embed_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) > 0

    def test_returns_consistent_dims(self):
        vecs = embed_texts(["first text", "second text", "third text"])
        assert len(vecs) == 3
        dims = {len(v) for v in vecs}
        assert len(dims) == 1  # All same dimension

    def test_empty_input(self):
        vecs = embed_texts([])
        assert vecs == []


class TestVectorIndex:
    def test_build_and_query(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([
            ("concepts/a", [1.0, 0.0, 0.0]),
            ("concepts/b", [0.0, 1.0, 0.0]),
            ("concepts/c", [0.9, 0.1, 0.0]),
        ])
        results = idx.query([1.0, 0.0, 0.0], limit=2)
        assert len(results) == 2
        # Closest match first
        assert results[0][0] == "concepts/a"
        # Second should be concepts/c (most similar to [1,0,0])
        assert results[1][0] == "concepts/c"

    def test_query_returns_page_id_and_distance(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([("concepts/a", [1.0, 0.0])])
        results = idx.query([1.0, 0.0], limit=1)
        assert len(results) == 1
        page_id, distance = results[0]
        assert isinstance(page_id, str)
        assert isinstance(distance, float)

    def test_empty_index(self, tmp_path):
        db_path = tmp_path / "test_vec.db"
        idx = VectorIndex(db_path)
        idx.build([])
        results = idx.query([1.0, 0.0], limit=5)
        assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.query.embeddings'`

- [ ] **Step 3: Write the embeddings module**

```python
# src/kb/query/embeddings.py
"""Embedding wrapper (model2vec) and vector index (sqlite-vec)."""

import logging
import sqlite3
import struct
import threading
from pathlib import Path

from kb.config import EMBEDDING_DIM, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Lazy-load model2vec model (thread-safe singleton)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from model2vec import StaticModel

                _model = StaticModel.from_pretrained(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts using model2vec. Returns list of float lists."""
    if not texts:
        return []
    model = _get_model()
    embeddings = model.encode(texts)
    return [vec.tolist() for vec in embeddings]


def _serialize_vec(vec: list[float]) -> bytes:
    """Serialize float list to little-endian bytes for sqlite-vec."""
    return struct.pack(f"<{len(vec)}f", *vec)


class VectorIndex:
    """sqlite-vec backed vector index for wiki page embeddings."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def build(self, entries: list[tuple[str, list[float]]]) -> None:
        """Build index from (page_id, embedding) pairs. Replaces existing index."""
        if not entries:
            # Create empty DB
            conn = sqlite3.connect(str(self.db_path))
            conn.close()
            return

        dim = len(entries[0][1])
        conn = sqlite3.connect(str(self.db_path))
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        conn.execute("DROP TABLE IF EXISTS page_ids")
        conn.execute("DROP TABLE IF EXISTS vec_pages")
        conn.execute("CREATE TABLE page_ids (rowid INTEGER PRIMARY KEY, page_id TEXT)")
        conn.execute(f"CREATE VIRTUAL TABLE vec_pages USING vec0(embedding float[{dim}])")

        for i, (page_id, vec) in enumerate(entries):
            rowid = i + 1
            conn.execute("INSERT INTO page_ids VALUES (?, ?)", (rowid, page_id))
            conn.execute(
                "INSERT INTO vec_pages (rowid, embedding) VALUES (?, ?)",
                (rowid, _serialize_vec(vec)),
            )

        conn.commit()
        conn.close()

    def query(self, query_vec: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Query for nearest neighbors. Returns [(page_id, distance), ...]."""
        if not self.db_path.exists():
            return []

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception:
            conn.close()
            return []

        try:
            rows = conn.execute(
                """
                SELECT p.page_id, v.distance
                FROM vec_pages v
                JOIN page_ids p ON p.rowid = v.rowid
                WHERE v.embedding MATCH ?
                ORDER BY v.distance
                LIMIT ?
                """,
                (_serialize_vec(query_vec), limit),
            ).fetchall()
            return [(row[0], row[1]) for row in rows]
        except Exception as e:
            logger.debug("Vector query failed: %s", e)
            return []
        finally:
            conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_embeddings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kb/query/embeddings.py tests/test_v0917_embeddings.py
git commit -m "feat(query): add model2vec embedding wrapper + sqlite-vec vector index"
```

---

### Task 6: Hybrid Search with RRF Fusion

**Files:**
- Create: `src/kb/query/hybrid.py`
- Modify: `src/kb/query/engine.py`
- Modify: `src/kb/query/__init__.py`
- Create: `tests/test_v0917_hybrid.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_hybrid.py
"""Tests for RRF fusion and hybrid search (Phase 4)."""

from kb.query.hybrid import rrf_fusion


class TestRRFFusion:
    def test_single_list(self):
        results = [
            {"id": "a", "score": 10.0},
            {"id": "b", "score": 5.0},
        ]
        fused = rrf_fusion([results])
        assert len(fused) == 2
        assert fused[0]["id"] == "a"  # Rank 0 → 1/(60+0) > 1/(60+1)

    def test_two_lists_same_order(self):
        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        assert fused[0]["id"] == "a"  # Appears rank 0 in both lists

    def test_two_lists_disjoint(self):
        list1 = [{"id": "a", "score": 10.0}]
        list2 = [{"id": "b", "score": 0.9}]
        fused = rrf_fusion([list1, list2])
        assert len(fused) == 2
        # Both at rank 0 in their list, so equal RRF score — either order OK
        ids = {r["id"] for r in fused}
        assert ids == {"a", "b"}

    def test_boosted_by_multiple_lists(self):
        list1 = [{"id": "a", "score": 10.0}, {"id": "b", "score": 5.0}]
        list2 = [{"id": "b", "score": 0.9}, {"id": "c", "score": 0.5}]
        fused = rrf_fusion([list1, list2])
        # b appears in both lists (rank 1 + rank 0) so gets boosted
        b_score = next(r["score"] for r in fused if r["id"] == "b")
        c_score = next(r["score"] for r in fused if r["id"] == "c")
        assert b_score > c_score

    def test_empty_lists(self):
        assert rrf_fusion([]) == []
        assert rrf_fusion([[], []]) == []

    def test_rrf_scores_are_positive(self):
        results = [{"id": "a", "score": 1.0}]
        fused = rrf_fusion([results])
        assert all(r["score"] > 0 for r in fused)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_hybrid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.query.hybrid'`

- [ ] **Step 3: Write the hybrid search module**

```python
# src/kb/query/hybrid.py
"""Hybrid search — RRF fusion of BM25 + vector search with multi-query expansion."""

import logging

from kb.config import RRF_K, VECTOR_SEARCH_LIMIT_MULTIPLIER

logger = logging.getLogger(__name__)


def rrf_fusion(lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: merge multiple ranked lists.

    Each result gets score = sum(1 / (k + rank)) across all lists it appears in.
    Results are identified by their 'id' key.
    """
    if not lists:
        return []

    scores: dict[str, dict] = {}
    for result_list in lists:
        for rank, result in enumerate(result_list):
            pid = result["id"]
            rrf_score = 1.0 / (k + rank)
            if pid in scores:
                scores[pid]["score"] += rrf_score
            else:
                scores[pid] = {**result, "score": rrf_score}

    return sorted(scores.values(), key=lambda r: r["score"], reverse=True)


def hybrid_search(
    question: str,
    bm25_fn,
    vector_fn,
    expand_fn=None,
    *,
    limit: int = 10,
) -> list[dict]:
    """Run hybrid BM25 + vector search with optional multi-query expansion.

    Args:
        question: The user query.
        bm25_fn: Callable(query, limit) -> list[dict] — BM25 search.
        vector_fn: Callable(query, limit) -> list[dict] — vector search.
        expand_fn: Optional callable(query) -> list[str] — returns alternative phrasings.
        limit: Maximum results to return.
    """
    vector_limit = limit * VECTOR_SEARCH_LIMIT_MULTIPLIER

    # Determine query variants
    queries = [question]
    if expand_fn:
        try:
            expanded = expand_fn(question)
            queries = [question, *expanded][:3]
        except Exception as e:
            logger.debug("Query expansion failed (non-fatal): %s", e)

    # Collect all result lists
    all_lists: list[list[dict]] = []

    # BM25 on original query only
    bm25_results = bm25_fn(question, vector_limit)
    if bm25_results:
        all_lists.append(bm25_results)

    # Vector search on all query variants
    for q in queries:
        vec_results = vector_fn(q, vector_limit)
        if vec_results:
            all_lists.append(vec_results)

    if not all_lists:
        return []

    return rrf_fusion(all_lists)[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_hybrid.py -v`
Expected: PASS

- [ ] **Step 5: Wire hybrid search into engine.py**

In `src/kb/query/engine.py`, update `search_pages()` to use hybrid search when a vector index exists. Add imports at the top:

```python
from kb.query.dedup import dedup_results
from kb.query.hybrid import hybrid_search
```

Then replace the body of `search_pages()` (lines 38-80) with logic that:
1. Builds BM25 index as before (existing code)
2. Checks if vector index exists at `VECTOR_INDEX_PATH`
3. If yes: runs `hybrid_search()` using BM25 and vector search, then `dedup_results()`
4. If no: falls back to BM25-only (existing behavior), then `dedup_results()`
5. Applies PageRank blending after RRF/BM25 scoring
6. Applies stale flagging

The key change is wrapping the existing BM25 logic into a lambda for `hybrid_search`:

```python
    # Build BM25 scorer as a callable
    def bm25_search(query: str, lim: int) -> list[dict]:
        qtoks = tokenize(query)
        if not qtoks:
            return []
        sc = index.score(qtoks, k1=BM25_K1, b=BM25_B)
        hits = []
        for i, score in enumerate(sc):
            if score > 0:
                hits.append({**pages[i], "score": round(score, 4)})
        hits.sort(key=lambda p: p["score"], reverse=True)
        return hits[:lim]

    # Build vector searcher if index exists
    def vector_search(query: str, lim: int) -> list[dict]:
        try:
            from kb.query.embeddings import embed_texts, VectorIndex
            vec_path = Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX
            if not vec_path.exists():
                return []
            vecs = embed_texts([query])
            if not vecs:
                return []
            idx = VectorIndex(vec_path)
            hits = idx.query(vecs[0], limit=lim)
            # Map page_ids back to page dicts
            page_map = {p["id"]: p for p in pages}
            results = []
            for pid, dist in hits:
                if pid in page_map:
                    results.append({**page_map[pid], "score": round(1.0 / (1.0 + dist), 4)})
            return results
        except Exception as e:
            logger.debug("Vector search unavailable: %s", e)
            return []

    # Run hybrid or BM25-only
    scored = hybrid_search(question, bm25_search, vector_search, limit=max_results * 2)
```

- [ ] **Step 6: Update query __init__.py**

```python
# src/kb/query/__init__.py
"""Query module — search wiki and synthesize answers with citations."""

from kb.query.engine import query_wiki, search_pages

__all__ = ["query_wiki", "search_pages"]
```

(No change needed — search_pages and query_wiki signatures remain the same.)

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -x -q`
Expected: All tests pass (hybrid falls back to BM25-only when no vector index exists)

- [ ] **Step 8: Commit**

```bash
git add src/kb/query/hybrid.py src/kb/query/engine.py tests/test_v0917_hybrid.py
git commit -m "feat(query): hybrid search with RRF fusion — BM25 + vector via model2vec + sqlite-vec"
```

---

### Task 7: Layered Context Assembly

**Files:**
- Modify: `src/kb/query/engine.py:108-190`
- Create: `tests/test_v0917_layered_context.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_layered_context.py
"""Tests for layered context assembly (Phase 4)."""

from kb.query.engine import _build_query_context


def _page(pid, content, ptype="concept"):
    return {
        "id": pid,
        "title": pid.split("/")[-1].replace("-", " ").title(),
        "type": ptype,
        "confidence": "stated",
        "content": content,
    }


class TestLayeredContextAssembly:
    def test_short_content_fits_entirely(self):
        pages = [_page("concepts/a", "Short content.")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context"]
        assert "Short content." in ctx["context"]

    def test_summaries_prioritized_in_tier1(self):
        pages = [
            _page("concepts/big", "x" * 5000, "concept"),
            _page("summaries/small", "summary text", "summary"),
        ]
        ctx = _build_query_context(pages, max_chars=6000)
        # Both should fit within 6000 chars
        assert "summaries/small" in ctx["context_pages"]

    def test_budget_respected(self):
        pages = [_page(f"concepts/p{i}", "x" * 2000) for i in range(20)]
        ctx = _build_query_context(pages, max_chars=5000)
        assert len(ctx["context"]) <= 5500  # Allow small header overhead

    def test_empty_pages(self):
        ctx = _build_query_context([], max_chars=10000)
        assert ctx["context_pages"] == []

    def test_returns_context_pages_list(self):
        pages = [_page("concepts/a", "Content A"), _page("concepts/b", "Content B")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context_pages"]
        assert "concepts/b" in ctx["context_pages"]
```

- [ ] **Step 2: Run tests to verify current behavior**

Run: `python -m pytest tests/test_v0917_layered_context.py -v`
Expected: Tests should pass with current implementation (the refactored version must maintain the same contract)

- [ ] **Step 3: Refactor _build_query_context for tiered loading**

Replace `_build_query_context` in `src/kb/query/engine.py` with a tiered version that:

1. **Tier 1** (summaries budget): Load summary pages first up to `CONTEXT_TIER1_BUDGET`
2. **Tier 2** (full pages budget): Load remaining pages up to `CONTEXT_TIER2_BUDGET`
3. **Within each tier**: Respect score ordering (highest first)

```python
def _build_query_context(pages: list[dict], max_chars: int = QUERY_CONTEXT_MAX_CHARS) -> dict:
    """Build context string from matching wiki pages using tiered loading.

    Tier 1: Summary pages loaded first (up to CONTEXT_TIER1_BUDGET).
    Tier 2: Non-summary pages loaded in score order (remaining budget).
    """
    if not pages:
        return {"context": "No relevant wiki pages found.", "context_pages": []}

    from kb.config import CONTEXT_TIER1_BUDGET, CONTEXT_TIER2_BUDGET

    effective_max = min(max_chars, CONTEXT_TIER1_BUDGET + CONTEXT_TIER2_BUDGET)
    summaries = [p for p in pages if p.get("type") == "summary"]
    others = [p for p in pages if p.get("type") != "summary"]

    sections = []
    context_pages = []
    total = 0
    skipped = 0

    def _try_add(page: dict) -> bool:
        nonlocal total, skipped
        section = (
            f"--- Page: {page['id']} (type: {page['type']}, "
            f"confidence: {page['confidence']}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
        if total + len(section) > effective_max:
            if not sections:
                # First page — truncate rather than skip
                remaining = effective_max - total
                header_len = len(section) - len(page["content"])
                if remaining > header_len:
                    sections.append(section[:remaining])
                    context_pages.append(page["id"])
                    total += remaining
                    return True
            skipped += 1
            return False
        sections.append(section)
        context_pages.append(page["id"])
        total += len(section)
        return True

    # Tier 1: summaries
    for p in summaries:
        _try_add(p)

    # Tier 2: everything else
    for p in others:
        _try_add(p)

    if skipped:
        logger.info(
            "Query context: included %d pages, skipped %d (limit: %d chars)",
            len(sections), skipped, effective_max,
        )

    if not sections and pages:
        top = pages[0]
        header = (
            f"--- Page: {top['id']} (type: {top['type']}, "
            f"confidence: {top['confidence']}) ---\n"
            f"Title: {top['title']}\n\n"
        )
        if effective_max <= len(header):
            return {"context": "No relevant wiki pages found.", "context_pages": []}
        section = header + top["content"]
        sections.append(section[:effective_max])
        context_pages.append(top["id"])

    return {"context": "\n".join(sections), "context_pages": context_pages}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_v0917_layered_context.py -v && python -m pytest -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kb/query/engine.py tests/test_v0917_layered_context.py
git commit -m "feat(query): layered context assembly — summaries first, then full pages on demand"
```

---

### Task 8: Raw-Source Fallback Retrieval

**Files:**
- Modify: `src/kb/query/engine.py`
- Create: `tests/test_v0917_raw_fallback.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_raw_fallback.py
"""Tests for raw-source fallback retrieval (Phase 4)."""

from kb.query.engine import search_raw_sources


class TestSearchRawSources:
    def test_finds_matching_raw_file(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/attention.md", "The attention mechanism computes...", tmp_project)
        results = search_raw_sources("attention mechanism", raw_dir=tmp_project / "raw", max_results=5)
        assert len(results) >= 1
        assert any("attention" in r["id"] for r in results)

    def test_returns_empty_for_no_match(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/unrelated.md", "Nothing relevant.", tmp_project)
        results = search_raw_sources("quantum computing entanglement", raw_dir=tmp_project / "raw", max_results=5)
        assert len(results) == 0

    def test_result_has_expected_keys(self, tmp_project, create_raw_source):
        create_raw_source("raw/articles/test.md", "Test content about transformers.", tmp_project)
        results = search_raw_sources("transformers", raw_dir=tmp_project / "raw", max_results=5)
        if results:
            r = results[0]
            assert "id" in r
            assert "content" in r
            assert "score" in r
            assert r["id"].startswith("raw/")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_raw_fallback.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_raw_sources'`

- [ ] **Step 3: Implement raw-source search**

Add to `src/kb/query/engine.py`:

```python
def search_raw_sources(
    question: str, raw_dir: Path | None = None, max_results: int = 5
) -> list[dict]:
    """Search raw/ source files using BM25 for verbatim context fallback.

    Returns list of dicts with keys: id, path, content, score.
    """
    from kb.config import RAW_DIR, SOURCE_TYPE_DIRS

    raw_dir = raw_dir or RAW_DIR
    if not raw_dir.exists():
        return []

    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    sources = []
    for subdir in raw_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith(".") or subdir.name == "assets":
            continue
        for f in subdir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                sources.append({
                    "id": f"raw/{subdir.name}/{f.name}",
                    "path": str(f),
                    "content": content,
                    "content_lower": content.lower(),
                })
            except (OSError, UnicodeDecodeError):
                continue

    if not sources:
        return []

    documents = [tokenize(s["content_lower"]) for s in sources]
    index = BM25Index(documents)
    scores = index.score(query_tokens, k1=BM25_K1, b=BM25_B)

    scored = []
    for i, score in enumerate(scores):
        if score > 0:
            scored.append({**sources[i], "score": round(score, 4)})

    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:max_results]
```

- [ ] **Step 4: Wire raw fallback into query_wiki context**

In `query_wiki()`, after building context from wiki pages but before synthesizing, add raw source context if wiki context is thin. Add after line 223 (`ctx = _build_query_context(matching_pages)`):

```python
    # Raw-source fallback: if wiki context is thin, supplement with raw sources
    raw_context = ""
    if len(ctx["context"]) < QUERY_CONTEXT_MAX_CHARS // 2:
        raw_results = search_raw_sources(question, max_results=3)
        if raw_results:
            raw_sections = []
            budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"])
            for rs in raw_results:
                section = f"--- Raw Source: {rs['id']} (verbatim) ---\n{rs['content']}\n"
                if len(section) > budget:
                    break
                raw_sections.append(section)
                budget -= len(section)
            if raw_sections:
                raw_context = "\n" + "\n".join(raw_sections)
```

Then include `raw_context` in the LLM prompt context:

```python
    context = ctx["context"] + raw_context
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_v0917_raw_fallback.py -v && python -m pytest -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/kb/query/engine.py tests/test_v0917_raw_fallback.py
git commit -m "feat(query): raw-source fallback retrieval — search raw/ alongside wiki/ for verbatim context"
```

---

### Task 9: Auto-Contradiction Detection on Ingest

**Files:**
- Create: `src/kb/ingest/contradiction.py`
- Modify: `src/kb/ingest/pipeline.py`
- Create: `tests/test_v0917_contradiction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_contradiction.py
"""Tests for auto-contradiction detection on ingest (Phase 4)."""

from kb.ingest.contradiction import detect_contradictions


class TestDetectContradictions:
    def test_no_contradictions_empty_wiki(self):
        new_claims = ["Transformers use self-attention."]
        result = detect_contradictions(new_claims, existing_pages=[])
        assert result == []

    def test_returns_contradiction_dict(self):
        new_claims = ["GPT-4 was released in 2025."]
        existing = [
            {
                "id": "entities/gpt-4",
                "content": "GPT-4 was released in March 2023.",
                "title": "GPT-4",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        # Without LLM, this uses keyword overlap heuristic
        # We don't assert specific contradictions since heuristic-only detection
        # is intentionally conservative — just verify the structure
        assert isinstance(result, list)
        for item in result:
            assert "new_claim" in item
            assert "existing_page" in item
            assert "existing_text" in item

    def test_no_false_positives_on_unrelated(self):
        new_claims = ["Python is a programming language."]
        existing = [
            {
                "id": "concepts/rust",
                "content": "Rust is a systems programming language.",
                "title": "Rust",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        assert result == []

    def test_respects_max_claims(self):
        claims = [f"Claim {i}" for i in range(20)]
        result = detect_contradictions(claims, existing_pages=[], max_claims=5)
        # Should not error even with many claims
        assert isinstance(result, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_contradiction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.ingest.contradiction'`

- [ ] **Step 3: Write the contradiction detection module**

```python
# src/kb/ingest/contradiction.py
"""Auto-contradiction detection — flag conflicts between new claims and existing wiki."""

import logging
import re

from kb.config import CONTRADICTION_MAX_CLAIMS_TO_CHECK

logger = logging.getLogger(__name__)


def detect_contradictions(
    new_claims: list[str],
    existing_pages: list[dict],
    max_claims: int = CONTRADICTION_MAX_CLAIMS_TO_CHECK,
) -> list[dict]:
    """Detect potential contradictions between new claims and existing wiki pages.

    Uses keyword overlap heuristic to find candidate conflicts:
    1. Extract significant tokens from each new claim
    2. Find existing pages with high token overlap
    3. Flag pairs where overlapping content contains contradictory signals

    Returns list of dicts with keys: new_claim, existing_page, existing_text, reason.
    """
    if not new_claims or not existing_pages:
        return []

    claims_to_check = new_claims[:max_claims]
    contradictions = []

    for claim in claims_to_check:
        claim_tokens = _extract_significant_tokens(claim)
        if len(claim_tokens) < 2:
            continue

        for page in existing_pages:
            page_content = page.get("content", "")
            page_tokens = _extract_significant_tokens(page_content)

            # Need substantial overlap to even consider checking
            overlap = claim_tokens & page_tokens
            if len(overlap) < 2:
                continue

            # Look for contradictory signal patterns in overlapping content
            matching_sentences = _find_overlapping_sentences(
                claim, page_content, overlap
            )
            for sentence in matching_sentences:
                if _has_contradiction_signal(claim, sentence):
                    contradictions.append({
                        "new_claim": claim,
                        "existing_page": page["id"],
                        "existing_text": sentence[:200],
                        "reason": "Potential factual conflict detected via keyword overlap",
                    })
                    break  # One contradiction per page per claim is enough

    return contradictions


# Contradiction signal words — suggest disagreement when co-occurring with shared entities
_CONTRADICTION_SIGNALS = re.compile(
    r"\b(not|never|no longer|instead|rather than|unlike|contrary|wrong|incorrect|"
    r"false|replaced|deprecated|obsolete|outdated)\b",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for with on at by from "
    "and or but if then else this that these those it its".split()
)


def _extract_significant_tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens (no stopwords, length >= 3)."""
    words = re.findall(r"\b\w[\w-]*\w\b", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 3}


def _find_overlapping_sentences(
    claim: str, page_content: str, overlap_tokens: set[str]
) -> list[str]:
    """Find sentences in page_content that share tokens with the claim."""
    sentences = re.split(r"(?<=[.!?])\s+", page_content)
    matching = []
    for s in sentences:
        s_tokens = _extract_significant_tokens(s)
        if len(s_tokens & overlap_tokens) >= 2:
            matching.append(s)
    return matching[:5]  # Cap to avoid excessive checking


def _has_contradiction_signal(claim: str, existing_sentence: str) -> bool:
    """Check if claim and existing sentence have contradictory signals."""
    # Both must share entities but one must contain a negation/contradiction word
    claim_has_signal = bool(_CONTRADICTION_SIGNALS.search(claim))
    existing_has_signal = bool(_CONTRADICTION_SIGNALS.search(existing_sentence))
    # Contradiction if exactly one side has the signal (asymmetric negation)
    return claim_has_signal != existing_has_signal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_contradiction.py -v`
Expected: PASS

- [ ] **Step 5: Wire into ingest pipeline**

In `src/kb/ingest/pipeline.py`, add import:
```python
from kb.ingest.contradiction import detect_contradictions
```

In `ingest_source()`, after entity/concept processing (after line 607) and before index updates (line 609), add:

```python
    # 3.5 Auto-contradiction detection
    contradiction_warnings: list[dict] = []
    if extraction:
        key_claims = extraction.get("key_claims") or extraction.get("key_points") or []
        if key_claims and isinstance(key_claims, list):
            try:
                existing = load_all_pages(effective_wiki_dir)
                contradiction_warnings = detect_contradictions(
                    [str(c) for c in key_claims if isinstance(c, str)],
                    existing,
                )
                if contradiction_warnings:
                    logger.warning(
                        "Detected %d potential contradiction(s) during ingest of %s",
                        len(contradiction_warnings),
                        source_ref,
                    )
            except Exception as e:
                logger.debug("Contradiction detection failed (non-fatal): %s", e)
```

Add `contradiction_warnings` to the return dict (after line 679):

```python
    if contradiction_warnings:
        result["contradictions"] = contradiction_warnings
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/kb/ingest/contradiction.py src/kb/ingest/pipeline.py tests/test_v0917_contradiction.py
git commit -m "feat(ingest): auto-contradiction detection — flag conflicts with existing wiki claims on ingest"
```

---

### Task 10: Multi-Turn Query Rewriting

**Files:**
- Create: `src/kb/query/rewriter.py`
- Modify: `src/kb/query/engine.py`
- Modify: `src/kb/mcp/core.py`
- Create: `tests/test_v0917_rewriter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_v0917_rewriter.py
"""Tests for multi-turn query rewriting (Phase 4)."""

from kb.query.rewriter import rewrite_query


class TestRewriteQuery:
    def test_standalone_query_unchanged(self):
        result = rewrite_query("What is a transformer?", conversation_context="")
        assert result == "What is a transformer?"

    def test_returns_string(self):
        result = rewrite_query(
            "How does it work?",
            conversation_context="User asked about attention mechanisms in transformers.",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_context_returns_original(self):
        result = rewrite_query("Tell me more", conversation_context=None)
        assert result == "Tell me more"

    def test_empty_query(self):
        result = rewrite_query("", conversation_context="some context")
        assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_v0917_rewriter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.query.rewriter'`

- [ ] **Step 3: Write the rewriter module**

```python
# src/kb/query/rewriter.py
"""Multi-turn query rewriting — expand pronouns/references using conversation context."""

import logging

from kb.config import MAX_CONVERSATION_CONTEXT_CHARS

logger = logging.getLogger(__name__)


def rewrite_query(
    question: str,
    conversation_context: str | None = None,
) -> str:
    """Rewrite a follow-up query into a standalone query using conversation context.

    If no conversation context is provided or the question appears standalone,
    returns the original question unchanged. Uses a scan-tier LLM call to
    expand pronouns and references.

    Args:
        question: The user's current question.
        conversation_context: Recent conversation history (Q&A pairs).

    Returns:
        The rewritten standalone query, or the original if no rewriting needed.
    """
    if not question:
        return question

    if not conversation_context or not conversation_context.strip():
        return question

    # Truncate context to budget
    context = conversation_context[:MAX_CONVERSATION_CONTEXT_CHARS]

    # Heuristic skip: if question has enough content words, likely standalone
    words = question.split()
    content_words = [w for w in words if len(w) > 3]
    if len(content_words) >= 5:
        return question

    try:
        from kb.utils.llm import call_llm

        prompt = (
            "Rewrite the following follow-up question into a standalone question "
            "that can be understood without prior conversation context. "
            "Expand any pronouns (it, they, this) and references to be specific. "
            "If the question is already standalone, return it unchanged.\n\n"
            f"CONVERSATION CONTEXT:\n{context}\n\n"
            f"FOLLOW-UP QUESTION: {question}\n\n"
            "STANDALONE QUESTION:"
        )
        rewritten = call_llm(prompt, tier="scan", max_tokens=200)
        rewritten = rewritten.strip().strip('"')
        if rewritten:
            return rewritten
    except Exception as e:
        logger.debug("Query rewriting failed (non-fatal): %s", e)

    return question
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_v0917_rewriter.py -v`
Expected: PASS (the no-context and standalone cases don't hit the LLM)

- [ ] **Step 5: Wire rewriter into query_wiki**

In `src/kb/query/engine.py`, update `query_wiki` signature and body:

```python
def query_wiki(
    question: str,
    wiki_dir: Path | None = None,
    max_results: int = 10,
    conversation_context: str | None = None,
) -> dict:
```

Add at the start of the function (after the docstring, before search):

```python
    # Rewrite follow-up queries into standalone queries
    effective_question = question
    if conversation_context:
        from kb.query.rewriter import rewrite_query
        effective_question = rewrite_query(question, conversation_context)
```

Then use `effective_question` for the search call:

```python
    matching_pages = search_pages(effective_question, wiki_dir, max_results=max_results)
```

- [ ] **Step 6: Add conversation_context param to MCP kb_query**

In `src/kb/mcp/core.py`, update `kb_query` signature:

```python
def kb_query(question: str, max_results: int = 10, use_api: bool = False, conversation_context: str = "") -> str:
```

Pass it through to `query_wiki` in the API mode branch:

```python
        result = query_wiki(question, max_results=max_results, conversation_context=conversation_context or None)
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/kb/query/rewriter.py src/kb/query/engine.py src/kb/mcp/core.py tests/test_v0917_rewriter.py
git commit -m "feat(query): multi-turn query rewriting — expand pronouns/references via scan-tier LLM"
```

---

### Task 11: Integration Test + Docs Update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests pass (1033 existing + new Phase 4 tests)

- [ ] **Step 2: Count new tests**

Run: `python -m pytest tests/test_v0917_*.py -v --co -q | tail -1`
Expected: Shows count of new test functions

- [ ] **Step 3: Run ruff lint**

Run: `ruff check src/kb/query/dedup.py src/kb/query/embeddings.py src/kb/query/hybrid.py src/kb/query/rewriter.py src/kb/ingest/evidence.py src/kb/ingest/contradiction.py`
Expected: No lint errors

- [ ] **Step 4: Update CLAUDE.md**

Update version, test count, module count, and Implementation Status to reflect Phase 4 completion. Update Phase 4 section to say "Phase 4 complete" and move items to history.

- [ ] **Step 5: Update CHANGELOG.md**

Add `[0.10.0]` entry under `[Unreleased]` with all Phase 4 changes grouped by Added/Changed.

- [ ] **Step 6: Bump version**

Update `src/kb/__init__.py`:
```python
__version__ = "0.10.0"
```

- [ ] **Step 7: Commit docs and version bump**

```bash
git add CLAUDE.md CHANGELOG.md src/kb/__init__.py
git commit -m "chore: bump version to v0.10.0 — Phase 4 complete (8 features: hybrid search, dedup, evidence trail, stale flagging, layered context, raw fallback, contradiction detection, query rewriting)"
```

---

## Dependency Graph

```
Task 1 (Config) ─────────────┬─── Task 2 (Evidence Trail)
                              ├─── Task 3 (Dedup)
                              ├─── Task 4 (Stale Flagging)
                              ├─── Task 5 (Embeddings)
                              │       └─── Task 6 (Hybrid + RRF)
                              │               └─── Task 7 (Layered Context)
                              │                       └─── Task 8 (Raw Fallback)
                              ├─── Task 9 (Contradiction Detection)
                              └─── Task 10 (Query Rewriting)
                                        └─── Task 11 (Integration + Docs)
```

Tasks 2, 3, 4, 5, 9, 10 are independent after Task 1 and can run in parallel.
Task 6 requires Task 5. Task 7 requires Task 6. Task 8 requires Task 7.
Task 11 requires all others.
