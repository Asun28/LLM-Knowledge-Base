# Phase 2: Multi-Loop Quality System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 MCP tools, 3 new modules, and 1 agent definition to enable multi-loop lint supervision, actor-critic compile, query feedback, and self-refine workflows.

**Architecture:** Python modules handle I/O, hashing, indexing, and context assembly. Claude Code handles all semantic reasoning and loop control. MCP tools return structured text contexts; they never call the LLM. Foundation modules are independently testable with no API calls.

**Tech Stack:** Python 3.12, pytest, python-frontmatter, networkx (existing deps). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-06-phase2-multi-loop-quality-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/kb/feedback/__init__.py` | Package marker (empty) |
| `src/kb/feedback/store.py` | Query feedback CRUD — load, save, add entries to `.data/query_feedback.json` |
| `src/kb/feedback/reliability.py` | Trust score computation, flagged pages, coverage gaps |
| `src/kb/review/__init__.py` | Package marker (empty) |
| `src/kb/review/context.py` | Page-source pairing utility, review context builder, checklist |
| `src/kb/review/refiner.py` | Page content update with frontmatter preservation, revision history |
| `src/kb/lint/semantic.py` | Fidelity, consistency, completeness context builders for LLM evaluation |
| `tests/test_feedback.py` | Tests for feedback/store.py and feedback/reliability.py |
| `tests/test_review.py` | Tests for review/context.py and review/refiner.py |
| `tests/test_lint_semantic.py` | Tests for lint/semantic.py |
| `tests/test_mcp_phase2.py` | Integration tests for 7 new MCP tools |
| `.claude/agents/wiki-reviewer.md` | Actor-Critic reviewer agent definition |

### Modified files

| File | Change |
|------|--------|
| `src/kb/config.py` | Add Phase 2 path constants and quality thresholds |
| `src/kb/mcp_server.py` | Add 7 new tool functions |
| `tests/conftest.py` | Add `tmp_project` fixture (wiki + raw + log) |
| `CLAUDE.md` | Add Phase 2 workflow documentation |

---

### Task 1: Config and Scaffolding

**Files:**
- Modify: `src/kb/config.py:59` (after `CONFIDENCE_LEVELS`)
- Create: `src/kb/feedback/__init__.py`
- Create: `src/kb/review/__init__.py`
- Modify: `tests/conftest.py:32` (after `tmp_wiki`)

- [ ] **Step 1: Add Phase 2 constants to config.py**

Add at the end of `src/kb/config.py`:

```python
# ── Phase 2: Quality system paths ────────────────────────────
FEEDBACK_PATH = PROJECT_ROOT / ".data" / "query_feedback.json"
REVIEW_MANIFEST_PATH = PROJECT_ROOT / ".data" / "review_manifest.json"
REVIEW_HISTORY_PATH = PROJECT_ROOT / ".data" / "review_history.json"

# ── Phase 2: Quality thresholds ──────────────────────────────
LOW_TRUST_THRESHOLD = 0.4
SELF_REFINE_MAX_ROUNDS = 2
LINT_MAX_ROUNDS = 3
MAX_CONSISTENCY_GROUP_SIZE = 5
```

- [ ] **Step 2: Create empty package __init__.py files**

Create `src/kb/feedback/__init__.py` (empty file).
Create `src/kb/review/__init__.py` (empty file).

- [ ] **Step 3: Add tmp_project fixture to conftest.py**

Add at the end of `tests/conftest.py`:

```python
@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with wiki/, raw/, and log.md."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / subdir).mkdir(parents=True)
    for subdir in ("articles", "papers", "repos", "videos"):
        (raw / subdir).mkdir(parents=True)
    (wiki / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return tmp_path
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `python -m pytest tests/ -q`
Expected: `78 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kb/config.py src/kb/feedback/__init__.py src/kb/review/__init__.py tests/conftest.py
git commit -m "feat: Phase 2 scaffolding — config constants, package dirs, test fixture"
```

---

### Task 2: Feedback Store

**Files:**
- Create: `src/kb/feedback/store.py`
- Create: `tests/test_feedback.py` (first half — store tests)

- [ ] **Step 1: Write failing tests for feedback store**

Create `tests/test_feedback.py`:

```python
"""Tests for the feedback module (store + reliability)."""

import json
from pathlib import Path

from kb.feedback.store import add_feedback_entry, load_feedback, save_feedback


# ── Store tests ───────────────────────────────────────────────


def test_load_feedback_empty(tmp_path):
    """load_feedback returns default structure when file doesn't exist."""
    path = tmp_path / "feedback.json"
    data = load_feedback(path)
    assert data == {"entries": [], "page_scores": {}}


def test_save_and_load_feedback(tmp_path):
    """Round-trip: save then load preserves data."""
    path = tmp_path / "feedback.json"
    data = {"entries": [{"question": "test"}], "page_scores": {}}
    save_feedback(data, path)
    loaded = load_feedback(path)
    assert loaded == data


def test_load_feedback_corrupted(tmp_path):
    """load_feedback returns default structure for corrupted JSON."""
    path = tmp_path / "feedback.json"
    path.write_text("not json{{{", encoding="utf-8")
    data = load_feedback(path)
    assert data == {"entries": [], "page_scores": {}}


def test_add_feedback_entry_useful(tmp_path):
    """add_feedback_entry with 'useful' rating boosts trust score."""
    path = tmp_path / "feedback.json"
    entry = add_feedback_entry(
        "What is RAG?", "useful", ["concepts/rag"], path=path
    )
    assert entry["rating"] == "useful"
    data = load_feedback(path)
    assert len(data["entries"]) == 1
    scores = data["page_scores"]["concepts/rag"]
    assert scores["useful"] == 1
    assert scores["wrong"] == 0
    # trust = (1 + 1) / (1 + 2) = 0.6667
    assert abs(scores["trust"] - 0.6667) < 0.001


def test_add_feedback_entry_wrong(tmp_path):
    """add_feedback_entry with 'wrong' rating lowers trust score."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("What is RAG?", "wrong", ["concepts/rag"], path=path)
    data = load_feedback(path)
    scores = data["page_scores"]["concepts/rag"]
    assert scores["wrong"] == 1
    # trust = (0 + 1) / (1 + 2) = 0.3333
    assert abs(scores["trust"] - 0.3333) < 0.001


def test_add_feedback_entry_multiple(tmp_path):
    """Multiple feedback entries accumulate correctly."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    add_feedback_entry("Q2", "useful", ["concepts/rag"], path=path)
    add_feedback_entry("Q3", "wrong", ["concepts/rag"], path=path)
    data = load_feedback(path)
    assert len(data["entries"]) == 3
    scores = data["page_scores"]["concepts/rag"]
    assert scores["useful"] == 2
    assert scores["wrong"] == 1
    # trust = (2 + 1) / (3 + 2) = 0.6
    assert abs(scores["trust"] - 0.6) < 0.001


def test_add_feedback_entry_invalid_rating(tmp_path):
    """add_feedback_entry raises ValueError for invalid rating."""
    path = tmp_path / "feedback.json"
    import pytest

    with pytest.raises(ValueError, match="Invalid rating"):
        add_feedback_entry("Q1", "bad_rating", ["concepts/rag"], path=path)


def test_add_feedback_entry_multiple_pages(tmp_path):
    """add_feedback_entry updates scores for all cited pages."""
    path = tmp_path / "feedback.json"
    add_feedback_entry(
        "Q1", "useful", ["concepts/rag", "entities/openai"], path=path
    )
    data = load_feedback(path)
    assert "concepts/rag" in data["page_scores"]
    assert "entities/openai" in data["page_scores"]
    assert data["page_scores"]["concepts/rag"]["useful"] == 1
    assert data["page_scores"]["entities/openai"]["useful"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_feedback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.feedback.store'`

- [ ] **Step 3: Implement feedback store**

Create `src/kb/feedback/store.py`:

```python
"""Query feedback storage — load, save, add entries to JSON."""

import json
from datetime import datetime
from pathlib import Path

from kb.config import FEEDBACK_PATH


def _default_feedback() -> dict:
    """Return empty feedback structure."""
    return {"entries": [], "page_scores": {}}


def load_feedback(path: Path | None = None) -> dict:
    """Load feedback data from JSON file.

    Returns default structure if file is missing or corrupted.
    """
    path = path or FEEDBACK_PATH
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return _default_feedback()
    return _default_feedback()


def save_feedback(data: dict, path: Path | None = None) -> None:
    """Save feedback data to JSON file."""
    path = path or FEEDBACK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_feedback_entry(
    question: str,
    rating: str,
    cited_pages: list[str],
    notes: str = "",
    path: Path | None = None,
) -> dict:
    """Add a feedback entry and update page trust scores.

    Args:
        question: The query that was asked.
        rating: One of 'useful', 'wrong', 'incomplete'.
        cited_pages: Page IDs cited in the answer.
        notes: Optional notes about what was wrong/missing.
        path: Path to feedback JSON file.

    Returns:
        The created entry dict.

    Raises:
        ValueError: If rating is not valid.
    """
    if rating not in ("useful", "wrong", "incomplete"):
        raise ValueError(
            f"Invalid rating: {rating}. Must be 'useful', 'wrong', or 'incomplete'"
        )

    data = load_feedback(path)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "rating": rating,
        "cited_pages": cited_pages,
        "notes": notes,
    }
    data["entries"].append(entry)

    # Update page scores with Bayesian smoothing
    for page_id in cited_pages:
        if page_id not in data["page_scores"]:
            data["page_scores"][page_id] = {
                "useful": 0, "wrong": 0, "incomplete": 0, "trust": 0.5,
            }
        scores = data["page_scores"][page_id]
        scores[rating] += 1
        total = scores["useful"] + scores["wrong"] + scores["incomplete"]
        scores["trust"] = round((scores["useful"] + 1) / (total + 2), 4)

    save_feedback(data, path)
    return entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_feedback.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kb/feedback/store.py tests/test_feedback.py
git commit -m "feat: feedback store — CRUD for query feedback with Bayesian trust scoring"
```

---

### Task 3: Feedback Reliability

**Files:**
- Create: `src/kb/feedback/reliability.py`
- Modify: `tests/test_feedback.py` (append reliability tests)

- [ ] **Step 1: Append failing tests for reliability**

Add to the end of `tests/test_feedback.py`:

```python
from kb.feedback.reliability import (
    compute_trust_scores,
    get_coverage_gaps,
    get_flagged_pages,
)


# ── Reliability tests ─────────────────────────────────────────


def test_compute_trust_scores_empty(tmp_path):
    """compute_trust_scores returns empty dict when no feedback exists."""
    path = tmp_path / "feedback.json"
    assert compute_trust_scores(path) == {}


def test_compute_trust_scores(tmp_path):
    """compute_trust_scores returns page scores from feedback."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    scores = compute_trust_scores(path)
    assert "concepts/rag" in scores
    assert scores["concepts/rag"]["useful"] == 1


def test_get_flagged_pages(tmp_path):
    """get_flagged_pages returns pages below trust threshold."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "wrong", ["concepts/rag"], path=path)
    # trust = (0+1)/(1+2) = 0.333 < 0.4 threshold
    flagged = get_flagged_pages(path)
    assert "concepts/rag" in flagged


def test_get_flagged_pages_empty(tmp_path):
    """get_flagged_pages returns empty list when no pages are flagged."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    # trust = (1+1)/(1+2) = 0.667 > 0.4
    flagged = get_flagged_pages(path)
    assert flagged == []


def test_get_coverage_gaps(tmp_path):
    """get_coverage_gaps returns questions with 'incomplete' rating."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    add_feedback_entry(
        "Q2", "incomplete", ["concepts/llm"], notes="Missing fine-tuning info", path=path
    )
    gaps = get_coverage_gaps(path)
    assert len(gaps) == 1
    assert gaps[0]["question"] == "Q2"
    assert gaps[0]["notes"] == "Missing fine-tuning info"


def test_get_coverage_gaps_empty(tmp_path):
    """get_coverage_gaps returns empty list when no incomplete ratings."""
    path = tmp_path / "feedback.json"
    add_feedback_entry("Q1", "useful", ["concepts/rag"], path=path)
    assert get_coverage_gaps(path) == []
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/test_feedback.py::test_compute_trust_scores_empty -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.feedback.reliability'`

- [ ] **Step 3: Implement reliability module**

Create `src/kb/feedback/reliability.py`:

```python
"""Trust score computation, flagged pages, coverage gaps."""

from pathlib import Path

from kb.config import LOW_TRUST_THRESHOLD
from kb.feedback.store import load_feedback


def compute_trust_scores(path: Path | None = None) -> dict[str, dict]:
    """Compute trust scores for all pages with feedback.

    Returns:
        Dict mapping page_id to score dict {useful, wrong, incomplete, trust}.
    """
    data = load_feedback(path)
    return data.get("page_scores", {})


def get_flagged_pages(
    path: Path | None = None, threshold: float | None = None
) -> list[str]:
    """Get page IDs with trust score below threshold.

    Args:
        path: Path to feedback JSON.
        threshold: Trust threshold (default: LOW_TRUST_THRESHOLD from config).

    Returns:
        Sorted list of page IDs below the threshold.
    """
    threshold = threshold if threshold is not None else LOW_TRUST_THRESHOLD
    scores = compute_trust_scores(path)
    return sorted(pid for pid, s in scores.items() if s.get("trust", 0.5) < threshold)


def get_coverage_gaps(path: Path | None = None) -> list[dict]:
    """Get questions where the answer was rated 'incomplete'.

    Returns:
        List of dicts with 'question' and 'notes' keys.
    """
    data = load_feedback(path)
    return [
        {"question": e["question"], "notes": e.get("notes", "")}
        for e in data.get("entries", [])
        if e.get("rating") == "incomplete"
    ]
```

- [ ] **Step 4: Run all feedback tests**

Run: `python -m pytest tests/test_feedback.py -v`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kb/feedback/reliability.py tests/test_feedback.py
git commit -m "feat: feedback reliability — trust scores, flagged pages, coverage gaps"
```

---

### Task 4: Review Context

**Files:**
- Create: `src/kb/review/context.py`
- Create: `tests/test_review.py`

- [ ] **Step 1: Write failing tests for review context**

Create `tests/test_review.py`:

```python
"""Tests for the review module (context + refiner)."""

from datetime import date
from pathlib import Path

from kb.review.context import (
    build_review_checklist,
    build_review_context,
    pair_page_with_sources,
)


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\ntitle: \"{title}\"\nsource:\n  - {source_ref}\n"
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(raw_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = raw_dir / source_ref.removeprefix("raw/")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


# ── pair_page_with_sources ────────────────────────────────────


def test_pair_page_with_sources(tmp_project):
    """pair_page_with_sources returns page content and source content."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Full RAG article content here.")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert result["page_id"] == "concepts/rag"
    assert "RAG is retrieval." in result["page_content"]
    assert len(result["source_contents"]) == 1
    assert result["source_contents"][0]["content"] == "Full RAG article content here."


def test_pair_page_with_sources_missing_source(tmp_project):
    """pair_page_with_sources handles missing source files gracefully."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/missing.md")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert result["source_contents"][0]["content"] is None
    assert "error" in result["source_contents"][0]


def test_pair_page_with_sources_page_not_found(tmp_project):
    """pair_page_with_sources returns error for non-existent page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    result = pair_page_with_sources("concepts/nonexistent", wiki_dir, raw_dir)
    assert "error" in result


def test_pair_page_with_sources_multiple_sources(tmp_project):
    """pair_page_with_sources handles pages with multiple sources."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    page_path = wiki_dir / "concepts" / "rag.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\ntitle: \"RAG\"\nsource:\n  - raw/articles/rag1.md\n"
        "  - raw/articles/rag2.md\ncreated: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\nRAG content."
    )
    page_path.write_text(fm, encoding="utf-8")
    _create_source(raw_dir, "raw/articles/rag1.md", "Source 1.")
    _create_source(raw_dir, "raw/articles/rag2.md", "Source 2.")

    result = pair_page_with_sources("concepts/rag", wiki_dir, raw_dir)
    assert len(result["source_contents"]) == 2


# ── build_review_context ──────────────────────────────────────


def test_build_review_context(tmp_project):
    """build_review_context returns formatted text with checklist."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Full RAG article.")

    context = build_review_context("concepts/rag", wiki_dir, raw_dir)
    assert "Review Context for: concepts/rag" in context
    assert "RAG is retrieval." in context
    assert "Full RAG article." in context
    assert "Review Checklist" in context


def test_build_review_context_not_found(tmp_project):
    """build_review_context returns error string for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_review_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context


def test_build_review_checklist():
    """build_review_checklist returns checklist with all 6 items."""
    checklist = build_review_checklist()
    assert "Source fidelity" in checklist
    assert "Entity/concept accuracy" in checklist
    assert "Wikilink validity" in checklist
    assert "Confidence level" in checklist
    assert "No hallucination" in checklist
    assert "Title accuracy" in checklist
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.review.context'`

- [ ] **Step 3: Implement review context**

Create `src/kb/review/context.py`:

```python
"""Page-source pairing and review context builder."""

from pathlib import Path

import frontmatter

from kb.config import RAW_DIR, WIKI_DIR


def pair_page_with_sources(
    page_id: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> dict:
    """Load a wiki page and all its referenced raw sources.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        wiki_dir: Path to wiki directory.
        raw_dir: Path to raw directory.

    Returns:
        Dict with page_id, page_content, page_metadata, source_contents.
        On error: dict with 'error' key.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    raw_dir = raw_dir or RAW_DIR

    page_path = wiki_dir / f"{page_id}.md"
    if not page_path.exists():
        return {"error": f"Page not found: {page_id}", "page_id": page_id}

    post = frontmatter.load(str(page_path))

    # Get source paths from frontmatter
    sources_meta = post.metadata.get("source", [])
    if isinstance(sources_meta, str):
        sources_meta = [sources_meta]

    source_contents = []
    for source_ref in sources_meta:
        # Resolve: "raw/articles/foo.md" -> raw_dir.parent / "raw/articles/foo.md"
        source_path = raw_dir.parent / source_ref
        if source_path.exists():
            source_contents.append({
                "path": source_ref,
                "content": source_path.read_text(encoding="utf-8"),
            })
        else:
            source_contents.append({
                "path": source_ref,
                "content": None,
                "error": f"Source file not found: {source_ref}",
            })

    return {
        "page_id": page_id,
        "page_content": post.content,
        "page_metadata": dict(post.metadata),
        "source_contents": source_contents,
    }


def build_review_checklist() -> str:
    """Return the review checklist text for quality evaluation."""
    return (
        "## Review Checklist\n\n"
        "Evaluate each item and report findings as JSON:\n\n"
        "1. **Source fidelity**: Does every factual claim trace to a specific source passage?\n"
        "2. **Entity/concept accuracy**: Are entities and concepts correctly identified?\n"
        "3. **Wikilink validity**: Do all [[wikilinks]] resolve to existing pages?\n"
        "4. **Confidence level**: Does the confidence match the evidence strength?\n"
        "5. **No hallucination**: Is there information NOT present in the raw source?\n"
        "6. **Title accuracy**: Does the title accurately reflect the page content?\n\n"
        'Return your review as JSON:\n```json\n'
        '{\n  "verdict": "approve | revise | reject",\n'
        '  "fidelity_score": 0.0,\n'
        '  "issues": [{"severity": "error|warning|info", '
        '"type": "unsourced_claim|missing_info|wrong_confidence|broken_link", '
        '"description": "...", "suggested_fix": "..."}],\n'
        '  "missing_from_source": ["..."],\n'
        '  "suggestions": ["..."]\n}\n```'
    )


def build_review_context(
    page_id: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build a complete review context for a wiki page.

    Returns formatted text with page content, source content, and review checklist.
    Claude Code or the wiki-reviewer agent uses this context to produce a structured review.
    """
    paired = pair_page_with_sources(page_id, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Review Context for: {page_id}\n",
        f"**Type:** {paired['page_metadata'].get('type', 'unknown')}",
        f"**Confidence:** {paired['page_metadata'].get('confidence', 'unknown')}",
        f"**Sources:** {len(paired['source_contents'])} file(s)\n",
        "---\n",
        "## Wiki Page Content\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Raw Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Source file not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(build_review_checklist())

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kb/review/context.py tests/test_review.py
git commit -m "feat: review context — page-source pairing and review checklist builder"
```

---

### Task 5: Review Refiner

**Files:**
- Create: `src/kb/review/refiner.py`
- Modify: `tests/test_review.py` (append refiner tests)

- [ ] **Step 1: Append failing tests for refiner**

Add to the end of `tests/test_review.py`:

```python
from kb.review.refiner import load_review_history, refine_page, save_review_history


# ── refine_page ───────────────────────────────────────────────


def test_refine_page(tmp_project):
    """refine_page updates content while preserving frontmatter."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old content.", "raw/articles/rag.md")

    result = refine_page(
        "concepts/rag", "New improved content.", "Fixed unsourced claim",
        wiki_dir=wiki_dir, history_path=tmp_project / "history.json",
    )
    assert result["updated"] is True

    # Verify content changed but frontmatter preserved
    text = (wiki_dir / "concepts" / "rag.md").read_text(encoding="utf-8")
    assert "New improved content." in text
    assert 'title: "RAG"' in text
    assert f"updated: {date.today().isoformat()}" in text
    assert "Old content." not in text


def test_refine_page_preserves_frontmatter_format(tmp_project):
    """refine_page preserves exact frontmatter key order and formatting."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag", "New.", "test",
        wiki_dir=wiki_dir, history_path=tmp_project / "history.json",
    )
    text = (wiki_dir / "concepts" / "rag.md").read_text(encoding="utf-8")
    # Frontmatter should still have source field intact
    assert "raw/articles/rag.md" in text
    assert "type: concept" in text
    assert "confidence: stated" in text


def test_refine_page_logs_to_wiki_log(tmp_project):
    """refine_page appends entry to wiki/log.md."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag", "New.", "Fixed claim",
        wiki_dir=wiki_dir, history_path=tmp_project / "history.json",
    )
    log = (wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "refine" in log
    assert "concepts/rag" in log
    assert "Fixed claim" in log


def test_refine_page_saves_review_history(tmp_project):
    """refine_page appends to review history JSON."""
    wiki_dir = tmp_project / "wiki"
    history_path = tmp_project / "history.json"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    refine_page(
        "concepts/rag", "New.", "Fixed claim",
        wiki_dir=wiki_dir, history_path=history_path,
    )
    history = load_review_history(history_path)
    assert len(history) == 1
    assert history[0]["page_id"] == "concepts/rag"
    assert history[0]["revision_notes"] == "Fixed claim"


def test_refine_page_not_found(tmp_project):
    """refine_page returns error for non-existent page."""
    wiki_dir = tmp_project / "wiki"
    result = refine_page(
        "concepts/nonexistent", "Content.", "notes",
        wiki_dir=wiki_dir, history_path=tmp_project / "history.json",
    )
    assert "error" in result


# ── Review history ────────────────────────────────────────────


def test_load_review_history_empty(tmp_path):
    """load_review_history returns empty list when file doesn't exist."""
    assert load_review_history(tmp_path / "history.json") == []


def test_save_and_load_review_history(tmp_path):
    """Round-trip: save then load review history."""
    history_path = tmp_path / "history.json"
    history = [{"page_id": "concepts/rag", "revision_notes": "test"}]
    save_review_history(history, history_path)
    loaded = load_review_history(history_path)
    assert loaded == history
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/test_review.py::test_refine_page -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.review.refiner'`

- [ ] **Step 3: Implement refiner**

Create `src/kb/review/refiner.py`:

```python
"""Page refinement — update content preserving frontmatter, log revisions."""

import json
import re
from datetime import date, datetime
from pathlib import Path

from kb.config import REVIEW_HISTORY_PATH, WIKI_DIR


def load_review_history(path: Path | None = None) -> list[dict]:
    """Load revision history from JSON file."""
    path = path or REVIEW_HISTORY_PATH
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_review_history(history: list[dict], path: Path | None = None) -> None:
    """Save revision history to JSON file."""
    path = path or REVIEW_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def refine_page(
    page_id: str,
    updated_content: str,
    revision_notes: str = "",
    wiki_dir: Path | None = None,
    history_path: Path | None = None,
) -> dict:
    """Update a wiki page's content while preserving frontmatter.

    Args:
        page_id: Wiki page ID (e.g., 'concepts/rag').
        updated_content: New markdown body (replaces everything after frontmatter).
        revision_notes: What changed and why.
        wiki_dir: Path to wiki directory.
        history_path: Path to review history JSON.

    Returns:
        Dict with page_id, updated, revision_notes. On error: dict with 'error' key.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    page_path = wiki_dir / f"{page_id}.md"

    if not page_path.exists():
        return {"error": f"Page not found: {page_id}"}

    text = page_path.read_text(encoding="utf-8")

    # Split frontmatter from content: ---\n<fm>\n---\n<body>
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"error": f"Invalid frontmatter format in {page_id}"}

    frontmatter_text = parts[1]

    # Update the 'updated' date in frontmatter
    today = date.today().isoformat()
    frontmatter_text = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}", f"updated: {today}", frontmatter_text
    )

    # Reconstruct page
    new_text = f"---{frontmatter_text}---\n\n{updated_content}\n"
    page_path.write_text(new_text, encoding="utf-8")

    # Append to review history
    history = load_review_history(history_path)
    history.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "page_id": page_id,
        "revision_notes": revision_notes,
    })
    save_review_history(history, history_path)

    # Append to wiki/log.md
    log_path = wiki_dir / "log.md"
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8")
        entry = f"- {today} | refine | Refined {page_id}: {revision_notes}\n"
        log_content += entry
        log_path.write_text(log_content, encoding="utf-8")

    return {
        "page_id": page_id,
        "updated": True,
        "revision_notes": revision_notes,
    }
```

- [ ] **Step 4: Run all review tests**

Run: `python -m pytest tests/test_review.py -v`
Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kb/review/refiner.py tests/test_review.py
git commit -m "feat: review refiner — page update with frontmatter preservation and audit trail"
```

---

### Task 6: Lint Semantic Checks

**Files:**
- Create: `src/kb/lint/semantic.py`
- Create: `tests/test_lint_semantic.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_lint_semantic.py`:

```python
"""Tests for semantic lint checks (fidelity, consistency, completeness contexts)."""

from pathlib import Path

from kb.lint.semantic import (
    build_completeness_context,
    build_consistency_context,
    build_fidelity_context,
)


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\ntitle: \"{title}\"\nsource:\n  - {source_ref}\n"
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(raw_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = raw_dir / source_ref.removeprefix("raw/")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


# ── Fidelity context ──────────────────────────────────────────


def test_build_fidelity_context(tmp_project):
    """build_fidelity_context returns page + source side by side."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG uses retrieval.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "RAG full article text.")

    context = build_fidelity_context("concepts/rag", wiki_dir, raw_dir)
    assert "Source Fidelity Check" in context
    assert "RAG uses retrieval." in context
    assert "RAG full article text." in context
    assert "Traced" in context
    assert "Unsourced" in context


def test_build_fidelity_context_missing_page(tmp_project):
    """build_fidelity_context returns error for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_fidelity_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context


# ── Consistency context ───────────────────────────────────────


def test_build_consistency_context_explicit(tmp_project):
    """build_consistency_context with explicit page IDs returns grouped content."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/rag.md")
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    context = build_consistency_context(["concepts/rag", "concepts/llm"], wiki_dir)
    assert "Cross-Page Consistency Check" in context
    assert "RAG content." in context
    assert "LLM content." in context


def test_build_consistency_context_auto_shared_sources(tmp_project):
    """build_consistency_context auto-selects pages sharing sources."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    # Two pages sharing the same source
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/shared.md")
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/shared.md")
    _create_source(raw_dir, "raw/articles/shared.md", "Shared source.")

    context = build_consistency_context(wiki_dir=wiki_dir, raw_dir=raw_dir)
    assert "Group" in context
    # Both pages should appear in at least one group
    assert "concepts/rag" in context or "concepts/llm" in context


def test_build_consistency_context_empty(tmp_project):
    """build_consistency_context with no groups returns informative message."""
    wiki_dir = tmp_project / "wiki"
    # Single page, no groups possible
    _create_page(
        wiki_dir, "concepts/rag", "RAG", "Content with unique words only.",
        "raw/articles/unique1.md",
    )

    context = build_consistency_context(wiki_dir=wiki_dir)
    assert "No page groups found" in context or "Group" in context


def test_build_consistency_context_auto_wikilinks(tmp_project):
    """build_consistency_context groups pages connected by wikilinks."""
    wiki_dir = tmp_project / "wiki"
    _create_page(
        wiki_dir, "concepts/rag", "RAG",
        "RAG uses [[concepts/llm]] models.", "raw/articles/rag.md",
    )
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    context = build_consistency_context(wiki_dir=wiki_dir)
    assert "Group" in context


# ── Completeness context ──────────────────────────────────────


def test_build_completeness_context(tmp_project):
    """build_completeness_context returns source alongside page for comparison."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Short summary.", "raw/articles/rag.md")
    _create_source(raw_dir, "raw/articles/rag.md", "Long detailed source with many claims.")

    context = build_completeness_context("concepts/rag", wiki_dir, raw_dir)
    assert "Completeness Check" in context
    assert "Short summary." in context
    assert "Long detailed source" in context
    assert "NOT represented" in context


def test_build_completeness_context_missing_page(tmp_project):
    """build_completeness_context returns error for missing page."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    context = build_completeness_context("concepts/nonexistent", wiki_dir, raw_dir)
    assert "Error:" in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_lint_semantic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kb.lint.semantic'`

- [ ] **Step 3: Implement semantic lint checks**

Create `src/kb/lint/semantic.py`:

```python
"""Semantic lint checks — build contexts for LLM-powered quality evaluation."""

from pathlib import Path

import frontmatter

from kb.config import MAX_CONSISTENCY_GROUP_SIZE, RAW_DIR, WIKI_DIR
from kb.graph.builder import build_graph, page_id, scan_wiki_pages
from kb.review.context import pair_page_with_sources


def build_fidelity_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build source fidelity check context: page content paired with source content.

    Returns formatted text for Claude Code to evaluate whether each claim
    in the wiki page traces to a specific passage in the raw source(s).
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Source Fidelity Check: {page_id_str}\n",
        "Evaluate whether each factual claim in the wiki page can be traced "
        "to a specific passage in the raw source(s).\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(
        "For each factual claim in the wiki page, identify whether it is:\n"
        "- **Traced**: directly supported by a passage in the source\n"
        "- **Inferred**: reasonably deduced from the source but not stated\n"
        "- **Unsourced**: not found in the source material\n"
    )

    return "\n".join(lines)


def _group_by_shared_sources(wiki_dir: Path) -> list[list[str]]:
    """Group pages that share raw sources (from frontmatter source: fields)."""
    pages = scan_wiki_pages(wiki_dir)
    source_to_pages: dict[str, list[str]] = {}

    for page_path in pages:
        try:
            post = frontmatter.load(str(page_path))
            pid = page_id(page_path, wiki_dir)
            sources = post.metadata.get("source", [])
            if isinstance(sources, str):
                sources = [sources]
            for src in sources:
                source_to_pages.setdefault(src, []).append(pid)
        except Exception:
            continue

    return [pids for pids in source_to_pages.values() if len(pids) >= 2]


def _group_by_wikilinks(wiki_dir: Path) -> list[list[str]]:
    """Group pages connected by wikilinks (direct neighbors in the graph)."""
    graph = build_graph(wiki_dir)
    groups = []
    seen: set[str] = set()

    for node in graph.nodes():
        if node in seen:
            continue
        neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
        # Only keep neighbors that exist as graph nodes
        existing_neighbors = {n for n in neighbors if graph.has_node(n)}
        if existing_neighbors:
            group = sorted(existing_neighbors | {node})
            groups.append(group)
            seen.update(group)

    return [g for g in groups if len(g) >= 2]


def _group_by_term_overlap(wiki_dir: Path) -> list[list[str]]:
    """Group pages with high term overlap (>= 3 shared significant terms)."""
    pages = scan_wiki_pages(wiki_dir)
    page_terms: dict[str, set[str]] = {}

    for page_path in pages:
        content = page_path.read_text(encoding="utf-8").lower()
        pid = page_id(page_path, wiki_dir)
        words = {w.strip(".,!?()[]{}\"'") for w in content.split() if len(w) > 4}
        page_terms[pid] = words

    groups = []
    page_ids_list = list(page_terms.keys())
    seen_pairs: set[tuple[str, str]] = set()

    for i, pid_a in enumerate(page_ids_list):
        for pid_b in page_ids_list[i + 1 :]:
            pair = (pid_a, pid_b)
            if pair in seen_pairs:
                continue
            shared = page_terms[pid_a] & page_terms[pid_b]
            if len(shared) >= 3:
                groups.append(sorted([pid_a, pid_b]))
                seen_pairs.add(pair)

    return groups


def build_consistency_context(
    page_ids: list[str] | None = None,
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
) -> str:
    """Build cross-page consistency check context.

    If page_ids is provided, uses them as a single group.
    Otherwise, auto-selects groups using shared sources and wikilinks.

    Returns formatted text for Claude Code to check for contradictions.
    """
    wiki_dir = wiki_dir or WIKI_DIR

    if page_ids:
        groups = [page_ids[:MAX_CONSISTENCY_GROUP_SIZE]]
    else:
        # Auto-select using three strategies (priority order per spec)
        all_groups: list[list[str]] = []
        all_groups.extend(_group_by_shared_sources(wiki_dir))
        all_groups.extend(_group_by_wikilinks(wiki_dir))
        all_groups.extend(_group_by_term_overlap(wiki_dir))

        # Deduplicate by sorted tuple
        seen: set[tuple[str, ...]] = set()
        groups = []
        for group in all_groups:
            key = tuple(sorted(group))
            if key not in seen:
                seen.add(key)
                groups.append(list(key)[:MAX_CONSISTENCY_GROUP_SIZE])

    if not groups:
        return "No page groups found for consistency checking."

    lines = [
        "# Cross-Page Consistency Check\n",
        f"Found {len(groups)} group(s) of related pages to check for contradictions.\n",
        "For each group, identify any claims that contradict each other.\n",
    ]

    for gi, group in enumerate(groups, 1):
        lines.append(f"## Group {gi} ({len(group)} pages)\n")
        for pid in group:
            page_path = wiki_dir / f"{pid}.md"
            if page_path.exists():
                content = page_path.read_text(encoding="utf-8")
                lines.append(f"### {pid}\n")
                lines.append(content)
                lines.append("\n---\n")

    return "\n".join(lines)


def build_completeness_context(
    page_id_str: str, wiki_dir: Path | None = None, raw_dir: Path | None = None
) -> str:
    """Build completeness check context: source alongside page for gap detection.

    Returns formatted text for Claude Code to identify key claims from the
    source that are NOT represented in the wiki page.
    """
    paired = pair_page_with_sources(page_id_str, wiki_dir, raw_dir)

    if "error" in paired and "page_content" not in paired:
        return f"Error: {paired['error']}"

    lines = [
        f"# Completeness Check: {page_id_str}\n",
        "Evaluate whether key claims from the raw source(s) are represented "
        "in the wiki page. Identify important omissions.\n",
        "---\n",
        "## Wiki Page\n",
        paired["page_content"],
        "\n---\n",
    ]

    for i, source in enumerate(paired["source_contents"], 1):
        lines.append(f"## Source {i}: {source['path']}\n")
        if source.get("content"):
            lines.append(source["content"])
        else:
            lines.append(f"*Not available: {source.get('error', 'unknown')}*")
        lines.append("\n---\n")

    lines.append(
        "List any key claims, facts, or arguments from the source(s) that are "
        "NOT represented in the wiki page.\n"
    )

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lint_semantic.py -v`
Expected: `9 passed`

- [ ] **Step 5: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -q`
Expected: `115 passed` (78 original + 14 feedback + 15 review + 9 lint_semantic - 1 overlap)

- [ ] **Step 6: Commit**

```bash
git add src/kb/lint/semantic.py tests/test_lint_semantic.py
git commit -m "feat: semantic lint — fidelity, consistency, completeness context builders"
```

---

### Task 7: MCP Tools (7 new tools)

**Files:**
- Modify: `src/kb/mcp_server.py` (add 7 tool functions)
- Create: `tests/test_mcp_phase2.py`

- [ ] **Step 1: Write failing tests for new MCP tools**

Create `tests/test_mcp_phase2.py`:

```python
"""Integration tests for Phase 2 MCP tools."""

from datetime import date
from pathlib import Path

from kb.mcp_server import (
    kb_affected_pages,
    kb_lint_consistency,
    kb_lint_deep,
    kb_query_feedback,
    kb_refine_page,
    kb_reliability_map,
    kb_review_page,
)


def _create_page(wiki_dir: Path, page_id: str, title: str, content: str, source_ref: str) -> None:
    """Helper to create a wiki page with frontmatter."""
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\ntitle: \"{title}\"\nsource:\n  - {source_ref}\n"
        f"created: 2026-04-06\nupdated: 2026-04-06\ntype: concept\n"
        f"confidence: stated\n---\n\n"
    )
    page_path.write_text(fm + content, encoding="utf-8")


def _create_source(project_dir: Path, source_ref: str, content: str) -> None:
    """Helper to create a raw source file."""
    source_path = project_dir / source_ref
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(content, encoding="utf-8")


# Note: MCP tool functions use global WIKI_DIR/RAW_DIR from config.
# For integration tests, we test the underlying modules directly
# since MCP tools are thin wrappers. These tests verify the wrappers
# format output correctly.

# ── kb_query_feedback ─────────────────────────────────────────


def test_kb_query_feedback_useful(tmp_path, monkeypatch):
    """kb_query_feedback records useful rating."""
    monkeypatch.setattr("kb.mcp_server.FEEDBACK_PATH_OVERRIDE", tmp_path / "fb.json", raising=False)
    # Test the underlying function directly
    from kb.feedback.store import add_feedback_entry

    entry = add_feedback_entry("What is RAG?", "useful", ["concepts/rag"], path=tmp_path / "fb.json")
    assert entry["rating"] == "useful"


def test_kb_query_feedback_invalid_rating(tmp_path):
    """Invalid rating raises ValueError."""
    import pytest

    from kb.feedback.store import add_feedback_entry

    with pytest.raises(ValueError):
        add_feedback_entry("Q", "bad", ["concepts/rag"], path=tmp_path / "fb.json")


# ── kb_reliability_map ────────────────────────────────────────


def test_kb_reliability_map_empty(tmp_path):
    """reliability returns empty when no feedback."""
    from kb.feedback.reliability import compute_trust_scores

    scores = compute_trust_scores(tmp_path / "fb.json")
    assert scores == {}


# ── kb_review_page ────────────────────────────────────────────


def test_kb_review_page_integration(tmp_project):
    """kb_review_page returns context with checklist."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG is retrieval.", "raw/articles/rag.md")
    _create_source(tmp_project, "raw/articles/rag.md", "Full article.")

    from kb.review.context import build_review_context

    context = build_review_context("concepts/rag", wiki_dir, raw_dir)
    assert "Review Checklist" in context
    assert "RAG is retrieval." in context


# ── kb_refine_page ────────────────────────────────────────────


def test_kb_refine_page_integration(tmp_project):
    """kb_refine_page updates page and logs."""
    wiki_dir = tmp_project / "wiki"
    _create_page(wiki_dir, "concepts/rag", "RAG", "Old.", "raw/articles/rag.md")

    from kb.review.refiner import refine_page

    result = refine_page(
        "concepts/rag", "New content.", "Fixed claims",
        wiki_dir=wiki_dir, history_path=tmp_project / "history.json",
    )
    assert result["updated"] is True
    log = (wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "concepts/rag" in log


# ── kb_lint_deep ──────────────────────────────────────────────


def test_kb_lint_deep_integration(tmp_project):
    """kb_lint_deep returns fidelity check context."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    _create_page(wiki_dir, "concepts/rag", "RAG", "RAG content.", "raw/articles/rag.md")
    _create_source(tmp_project, "raw/articles/rag.md", "Source text.")

    from kb.lint.semantic import build_fidelity_context

    context = build_fidelity_context("concepts/rag", wiki_dir, raw_dir)
    assert "Source Fidelity Check" in context


# ── kb_affected_pages ─────────────────────────────────────────


def test_kb_affected_pages_with_backlinks(tmp_project):
    """kb_affected_pages finds pages that link to the given page."""
    wiki_dir = tmp_project / "wiki"
    _create_page(
        wiki_dir, "concepts/rag", "RAG",
        "Uses [[concepts/llm]] for generation.", "raw/articles/rag.md",
    )
    _create_page(wiki_dir, "concepts/llm", "LLM", "LLM content.", "raw/articles/llm.md")

    from kb.compile.linker import build_backlinks

    backlinks = build_backlinks(wiki_dir)
    assert "concepts/llm" in backlinks
    assert "concepts/rag" in backlinks["concepts/llm"]
```

- [ ] **Step 2: Run tests to verify they pass (these test foundation modules directly)**

Run: `python -m pytest tests/test_mcp_phase2.py -v`
Expected: `7 passed`

- [ ] **Step 3: Add 7 new tool functions to mcp_server.py**

Add the following before `def main():` in `src/kb/mcp_server.py`:

```python
# ── Phase 2: Quality Tools ──────────────────────────────────────────


@mcp.tool()
def kb_review_page(page_id: str) -> str:
    """Review a wiki page — returns page content, raw sources, and review checklist.

    The tool returns raw context (text). You (Claude Code) or a wiki-reviewer
    sub-agent evaluate the context and produce a structured JSON review.

    Args:
        page_id: Page to review (e.g., 'concepts/rag').
    """
    from kb.review.context import build_review_context

    return build_review_context(page_id)


@mcp.tool()
def kb_refine_page(page_id: str, updated_content: str, revision_notes: str = "") -> str:
    """Update a wiki page's content while preserving frontmatter.

    Used after review or self-critique to apply improvements.
    Logs to wiki/log.md and .data/review_history.json.

    Args:
        page_id: Page to update (e.g., 'concepts/rag').
        updated_content: New markdown body (frontmatter preserved automatically).
        revision_notes: What changed and why.
    """
    from kb.review.refiner import refine_page

    result = refine_page(page_id, updated_content, revision_notes)
    if "error" in result:
        return f"Error: {result['error']}"

    # Include affected pages in response
    from kb.compile.linker import build_backlinks

    backlinks = build_backlinks()
    affected = backlinks.get(page_id, [])

    lines = [
        f"Refined: {page_id}",
        f"Notes: {revision_notes}",
    ]
    if affected:
        lines.append(f"Affected pages ({len(affected)} — may need review):")
        for p in affected:
            lines.append(f"  - {p}")
    return "\n".join(lines)


@mcp.tool()
def kb_lint_deep(page_id: str) -> str:
    """Deep lint a single page — returns page + raw sources side-by-side
    for source fidelity evaluation.

    You (Claude Code) evaluate whether each claim traces to the source.

    Args:
        page_id: Page to check (e.g., 'concepts/rag').
    """
    from kb.lint.semantic import build_fidelity_context

    return build_fidelity_context(page_id)


@mcp.tool()
def kb_lint_consistency(page_ids: str = "") -> str:
    """Cross-page consistency check — returns related pages grouped for
    contradiction detection.

    Pass comma-separated page IDs, or leave empty to auto-select
    pages most likely to conflict (shared sources, wikilink neighbors).

    Args:
        page_ids: Comma-separated page IDs (e.g., 'concepts/rag,concepts/llm').
                  Empty = auto-select groups.
    """
    from kb.lint.semantic import build_consistency_context

    ids = [p.strip() for p in page_ids.split(",") if p.strip()] if page_ids else None
    return build_consistency_context(ids)


@mcp.tool()
def kb_query_feedback(
    question: str, rating: str, cited_pages: str = "", notes: str = ""
) -> str:
    """Record feedback on a query answer to improve wiki reliability.

    Args:
        question: The question that was asked.
        rating: 'useful', 'wrong', or 'incomplete'.
        cited_pages: Comma-separated page IDs cited in the answer.
        notes: What was wrong or missing.
    """
    from kb.feedback.store import add_feedback_entry

    pages = [p.strip() for p in cited_pages.split(",") if p.strip()]
    try:
        entry = add_feedback_entry(question, rating, pages, notes)
    except ValueError as e:
        return f"Error: {e}"

    action = {
        "useful": "Trust scores boosted for cited pages.",
        "wrong": "Cited pages flagged for priority re-lint.",
        "incomplete": "Coverage gap logged for kb_evolve.",
    }
    return f"Feedback recorded: {rating}\n{action.get(rating, '')}"


@mcp.tool()
def kb_reliability_map() -> str:
    """Show page trust scores based on query feedback history.

    Pages cited in successful queries score higher.
    Pages cited in wrong answers score lower and are flagged for re-lint.
    """
    from kb.feedback.reliability import compute_trust_scores, get_flagged_pages

    scores = compute_trust_scores()
    if not scores:
        return "No feedback recorded yet. Use kb_query_feedback after queries."

    sorted_pages = sorted(scores.items(), key=lambda x: x[1].get("trust", 0.5), reverse=True)
    flagged = set(get_flagged_pages())

    lines = ["# Page Reliability Map\n"]
    for pid, s in sorted_pages:
        flag = " **[FLAGGED]**" if pid in flagged else ""
        lines.append(
            f"- {pid}: trust={s['trust']:.2f} "
            f"(useful={s['useful']}, wrong={s['wrong']}, incomplete={s['incomplete']}){flag}"
        )

    if flagged:
        lines.append(f"\n**{len(flagged)} page(s) flagged** (trust < 0.4). Run kb_lint_deep on these.")

    return "\n".join(lines)


@mcp.tool()
def kb_affected_pages(page_id: str) -> str:
    """Find pages affected when this page changes.

    Returns pages that link TO this page (backlinks) and pages
    that share the same raw sources. Use after updating a page
    to decide whether related pages need review.

    Args:
        page_id: Page that was changed (e.g., 'concepts/rag').
    """
    import frontmatter as fm

    from kb.compile.linker import build_backlinks
    from kb.graph.builder import scan_wiki_pages

    backlinks_map = build_backlinks()
    back = backlinks_map.get(page_id, [])

    # Find pages sharing same sources
    page_path = WIKI_DIR / f"{page_id}.md"
    shared_source_pages: list[str] = []
    if page_path.exists():
        post = fm.load(str(page_path))
        page_sources = post.metadata.get("source", [])
        if isinstance(page_sources, str):
            page_sources = [page_sources]

        # Scan all pages for matching sources
        for other_path in scan_wiki_pages():
            try:
                other_post = fm.load(str(other_path))
                other_id = str(other_path.relative_to(WIKI_DIR)).replace("\\", "/").removesuffix(".md")
                if other_id == page_id:
                    continue
                other_sources = other_post.metadata.get("source", [])
                if isinstance(other_sources, str):
                    other_sources = [other_sources]
                if set(page_sources) & set(other_sources):
                    shared_source_pages.append(other_id)
            except Exception:
                continue

    all_affected = sorted(set(back + shared_source_pages))

    if not all_affected:
        return f"No pages are affected by changes to {page_id}."

    lines = [
        f"# Pages Affected by Changes to {page_id}\n",
        f"**Total:** {len(all_affected)} page(s)\n",
    ]

    if back:
        lines.append(f"## Backlinks ({len(back)} pages link to this page)")
        for p in back:
            lines.append(f"  - {p}")

    if shared_source_pages:
        lines.append(f"\n## Shared Sources ({len(shared_source_pages)} pages share raw sources)")
        for p in shared_source_pages:
            lines.append(f"  - {p}")

    lines.append("\nReview these pages if the changes affect shared claims or definitions.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -q`
Expected: All tests pass (78 original + ~37 new)

- [ ] **Step 5: Commit**

```bash
git add src/kb/mcp_server.py tests/test_mcp_phase2.py
git commit -m "feat: 7 new MCP tools — review, refine, lint deep/consistency, feedback, reliability, affected pages"
```

---

### Task 8: Wiki Reviewer Agent Definition

**Files:**
- Create: `.claude/agents/wiki-reviewer.md`

- [ ] **Step 1: Create the wiki-reviewer agent**

Create `.claude/agents/wiki-reviewer.md`:

```markdown
---
name: wiki-reviewer
description: Independent wiki page quality reviewer (Critic role in Actor-Critic pattern). Evaluates pages strictly against raw source material.
model: sonnet
---

You are an independent quality reviewer for the LLM Knowledge Base wiki. Your role is the **Critic** in an Actor-Critic compile pattern. You evaluate wiki pages strictly against their raw source material.

## Your Mission

You have NO knowledge of why or how pages were created. You evaluate only what you see: the wiki page vs. its raw source(s). Your job is to find problems, not to approve work.

## Available Tools

- `kb_review_page(page_id)` — Returns page content + raw source content + review checklist
- `kb_read_page(page_id)` — Read any wiki page
- `kb_search(query)` — Search wiki pages by keyword
- `kb_list_pages()` — List all wiki pages (verify wikilink targets exist)

## Workflow

For each page_id you're given:

1. Call `kb_review_page(page_id)` to get the review context
2. Read the wiki page content carefully
3. Read the raw source(s) carefully
4. Evaluate each checklist item:
   - **Source fidelity**: Can every factual claim be traced to a specific source passage?
   - **Entity/concept accuracy**: Are names and descriptions correct?
   - **Wikilink validity**: Call `kb_list_pages()` to verify targets exist
   - **Confidence level**: Does `stated` vs `inferred` vs `speculative` match the evidence?
   - **No hallucination**: Any info in the page NOT in the source?
   - **Title accuracy**: Does the title reflect the content?
5. Return your review as structured JSON

## Output Format

```json
{
  "verdict": "approve | revise | reject",
  "fidelity_score": 0.85,
  "issues": [
    {
      "severity": "error | warning | info",
      "type": "unsourced_claim | missing_info | wrong_confidence | broken_link",
      "description": "Specific description of the issue",
      "location": "Section or content reference",
      "suggested_fix": "What should change"
    }
  ],
  "missing_from_source": ["Key points from the source not in the wiki page"],
  "suggestions": ["Improvements that would strengthen the page"]
}
```

## Rules

- Never approve a page just because it looks reasonable
- Every factual claim must trace to a specific passage in the source
- Flag `confidence: stated` claims that are actually inferences
- Flag missing key information from the source
- You are READ-ONLY: you cannot edit pages, only report findings
- Be specific: quote the problematic text and the source passage (or lack thereof)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/wiki-reviewer.md
git commit -m "feat: wiki-reviewer agent definition for Actor-Critic compile"
```

---

### Task 9: Integration Enhancements (Phase 2d)

**Files:**
- Modify: `src/kb/mcp_server.py` (enhance kb_query, kb_lint, kb_evolve with feedback data)

- [ ] **Step 1: Enhance kb_query with trust scores**

In `src/kb/mcp_server.py`, modify the `kb_query` function's Claude Code mode (the `else` branch starting at line ~219). After building the search results, merge trust scores:

Find the section in `kb_query` that builds the lines list for Claude Code mode and replace it:

```python
    # Default: Claude Code mode — return context for synthesis
    from kb.query.engine import search_pages

    results = search_pages(question, max_results=max_results)
    if not results:
        return (
            "No relevant wiki pages found for this question. "
            "The knowledge base may not have content on this topic yet."
        )

    # Merge trust scores from feedback (fail-safe)
    try:
        from kb.feedback.reliability import compute_trust_scores

        scores = compute_trust_scores()
        for r in results:
            trust_data = scores.get(r["id"], {})
            r["trust"] = trust_data.get("trust", 0.5)
    except Exception:
        for r in results:
            r["trust"] = 0.5

    lines = [
        f"# Query Context for: {question}\n",
        f"Found {len(results)} relevant page(s). "
        "Synthesize an answer using this context. "
        "Cite sources with [source: page_id] format.\n",
    ]
    for r in results:
        trust_label = f", trust: {r['trust']:.2f}" if r.get("trust", 0.5) != 0.5 else ""
        lines.append(
            f"--- Page: {r['id']} (type: {r['type']}, "
            f"confidence: {r['confidence']}, score: {r['score']}{trust_label}) ---\n"
            f"Title: {r['title']}\n\n{r['content']}\n"
        )
    return "\n".join(lines)
```

- [ ] **Step 2: Enhance kb_lint with flagged pages section**

In `src/kb/mcp_server.py`, modify the `kb_lint` function to append feedback-flagged pages:

```python
@mcp.tool()
def kb_lint() -> str:
    """Run health checks on the wiki. Reports dead links, orphans, staleness, etc."""
    from kb.lint.runner import format_report, run_all_checks

    report = run_all_checks()
    result = format_report(report)

    # Append feedback-flagged pages (fail-safe)
    try:
        from kb.feedback.reliability import get_flagged_pages

        flagged = get_flagged_pages()
        if flagged:
            result += (
                "\n## Low-Trust Pages (from query feedback)\n\n"
                f"{len(flagged)} page(s) with trust score below threshold:\n"
            )
            for p in flagged:
                result += f"- {p} — run `kb_lint_deep(\"{p}\")` for fidelity check\n"
    except Exception:
        pass

    return result
```

- [ ] **Step 3: Enhance kb_evolve with coverage gaps from feedback**

In `src/kb/mcp_server.py`, modify the `kb_evolve` function to append feedback-driven gaps:

```python
@mcp.tool()
def kb_evolve() -> str:
    """Analyze knowledge gaps and suggest new connections, pages, and sources."""
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    report = generate_evolution_report()
    result = format_evolution_report(report)

    # Append coverage gaps from query feedback (fail-safe)
    try:
        from kb.feedback.reliability import get_coverage_gaps

        gaps = get_coverage_gaps()
        if gaps:
            result += (
                "\n## Coverage Gaps (from query feedback)\n\n"
                f"{len(gaps)} query/queries returned incomplete answers:\n"
            )
            for g in gaps:
                notes = f" — {g['notes']}" if g["notes"] else ""
                result += f"- \"{g['question']}\"{notes}\n"
    except Exception:
        pass

    return result
```

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/kb/mcp_server.py
git commit -m "feat: Phase 2d integration — trust scores in queries, flagged pages in lint, gaps in evolve"
```

---

### Task 10: CLAUDE.md Updates and Cleanup

**Files:**
- Modify: `CLAUDE.md`
- Modify: `src/kb/__init__.py` (version bump)

- [ ] **Step 1: Add Phase 2 workflow documentation to CLAUDE.md**

Append before `## Conventions` in `CLAUDE.md`:

```markdown
## Phase 2 Workflows

### Standard Ingest (with Self-Refine)
1. `kb_ingest(path)` — get extraction prompt
2. Extract JSON — `kb_ingest(path, extraction_json)`
3. For each created page: `kb_review_page(page_id)` — self-critique
4. If issues: `kb_refine_page(page_id, updated_content)` (max 2 rounds)

### Thorough Ingest (with Actor-Critic)
1-4. Same as Standard Ingest
5. Spawn wiki-reviewer agent with created page_ids
6. Review findings — fix or accept
7. `kb_affected_pages` — flag related pages

### Deep Lint
1. `kb_lint()` — mechanical report
2. For errors: `kb_lint_deep(page_id)` — evaluate fidelity
3. Fix issues via `kb_refine_page`
4. `kb_lint_consistency()` — contradiction check
5. Re-run `kb_lint()` to verify (max 3 rounds)

### Query with Feedback
1. `kb_query(question)` — synthesize answer
2. After user reaction: `kb_query_feedback(question, rating, pages)`

### Phase 2 MCP Tools
| Tool | Purpose |
|------|---------|
| `kb_review_page(page_id)` | Page + sources + checklist for quality review |
| `kb_refine_page(page_id, content, notes)` | Update page preserving frontmatter |
| `kb_lint_deep(page_id)` | Source fidelity check context |
| `kb_lint_consistency(page_ids)` | Cross-page contradiction check |
| `kb_query_feedback(question, rating, pages, notes)` | Record query success/failure |
| `kb_reliability_map()` | Page trust scores from feedback |
| `kb_affected_pages(page_id)` | Pages affected by a change |
```

- [ ] **Step 2: Bump version**

In `src/kb/__init__.py`, change:
```python
__version__ = "0.4.0"
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (78 original + ~37 new = ~115+ total)

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md src/kb/__init__.py
git commit -m "docs: Phase 2 workflow documentation and version bump to v0.4.0"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `python -m pytest tests/ -v` — all ~115+ tests pass
- [ ] `ruff check src/ tests/` — no lint errors
- [ ] `ruff format src/ tests/` — code formatted
- [ ] 7 new MCP tools visible when running `kb mcp`
- [ ] `.claude/agents/wiki-reviewer.md` exists
- [ ] `CLAUDE.md` has Phase 2 workflow section
- [ ] `src/kb/__init__.py` shows `__version__ = "0.4.0"`
- [ ] No imports of `langgraph`, `dspy`, or `langchain` in new code
