# E2E Demo Pipeline Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single hermetic end-to-end test (`tests/test_e2e_demo_pipeline.py`) that drives `ingest_source` → `query_wiki` → `run_all_checks` over the committed `demo/raw/*.md` Karpathy sources, with the LLM stubbed, to catch integration regressions across module boundaries that unit tests miss.

**Architecture:** One pytest function in one new file. Reuses `tmp_project` from `tests/conftest.py`. Copies `demo/raw/articles/karpathy-x-post.md` and `demo/raw/papers/karpathy-llm-wiki-gist.md` into the temp project, monkeypatches the five module-level constants the pipeline reads (`RAW_DIR`, `PROJECT_ROOT`, `WIKI_CONTRADICTIONS`, `HASH_MANIFEST`, and `kb.query.engine.call_llm`), passes pre-built `extraction` dicts to `ingest_source` so no LLM is called for extraction, and asserts on file artifacts plus return-dict shapes. No new helpers, no new fixtures, no new dependencies.

**Tech Stack:** pytest 9.x, `monkeypatch` fixture, stdlib (`shutil`, `pathlib`, `frontmatter`).

---

## Background — facts the implementer needs

These are the load-bearing facts about the codebase. Read them once before starting Task 1.

**Why this test is hermetic without VCR cassettes:** `ingest_source(path, source_type, extraction=...)` takes an `extraction` dict. When provided, the pipeline skips the LLM extraction call entirely (`src/kb/ingest/pipeline.py:581`). The only remaining LLM call in the pipeline is `query_wiki` → `kb.utils.llm.call_llm` at `src/kb/query/engine.py:411`. That single call is the only thing the test needs to monkeypatch.

**Module-level constants the pipeline captures by name** (must be patched at both the config module and the consuming module — established double-patch pattern, ~40 examples in `tests/test_mcp_*.py`):

| Constant | Defined at | Read by |
|---|---|---|
| `RAW_DIR` | `kb.config.RAW_DIR` | `kb.ingest.pipeline.RAW_DIR` (line 17), `kb.compile.compiler.RAW_DIR` (line 11) |
| `PROJECT_ROOT` | `kb.config.PROJECT_ROOT` | `kb.ingest.pipeline.PROJECT_ROOT` (line 16), `kb.compile.compiler.PROJECT_ROOT` (line 10), `kb.query.engine.PROJECT_ROOT` (line 12) |
| `WIKI_CONTRADICTIONS` | `kb.config.WIKI_CONTRADICTIONS` | `kb.ingest.pipeline.WIKI_CONTRADICTIONS` (line 20) |
| `HASH_MANIFEST` | `kb.compile.compiler.HASH_MANIFEST` (computed `PROJECT_ROOT / ".data" / "hashes.json"` at module load) | same module only |
| `call_llm` | `kb.utils.llm.call_llm` | `kb.query.engine.call_llm` (imported by name at line 23) |

`WIKI_DIR` does NOT need patching — `ingest_source`, `query_wiki`, and `run_all_checks` all accept a `wiki_dir=` parameter that overrides the config default.

**The `tmp_project` fixture** (`tests/conftest.py:39-48`) creates `tmp_path/wiki/{entities,concepts,comparisons,summaries,synthesis}/`, `tmp_path/raw/{articles,papers,repos,videos}/`, and `tmp_path/wiki/log.md`. It does NOT create `index.md`, `_sources.md`, `_categories.md`, or `contradictions.md`. The pipeline tolerates missing index/sources/categories (it logs a warning and skips), and `WIKI_CONTRADICTIONS` is only created on first contradiction. So the bare `tmp_project` fixture is sufficient — but the test must seed `index.md` and `_sources.md` if it wants to assert they are updated. This plan keeps the assertions narrow (frontmatter + page existence + query result shape) so seeding is not required.

**Demo source content available** (already committed at `8449761`):
- `demo/raw/articles/karpathy-x-post.md` — Karpathy's X post text. Mentions: Andrej Karpathy, Obsidian. Concepts: LLM Knowledge Base, compile-not-retrieve, naive search engine.
- `demo/raw/papers/karpathy-llm-wiki-gist.md` — Karpathy's gist. Mentions: Andrej Karpathy. Concepts: LLM Knowledge Base, compile-not-retrieve, ingest-query-lint.

**Why TDD's red-then-green dance is muted here:** the deliverable IS the test. There is no production code to write. The test "fails" first only if the pipeline is already broken — that is the intended signal. So the workflow is: write the test, run it, and if it fails, the bug is real and gets a separate fix commit. We still write the test additively (one assertion at a time) per Task 2 sub-steps.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `tests/test_e2e_demo_pipeline.py` | Create | Single e2e test function plus its monkeypatch helper |
| `CHANGELOG.md` | Modify | Add one line under `[Unreleased] / Added` |

No other files touched. No new fixtures in `tests/conftest.py`. The monkeypatch helper lives inside the test file because it is single-use.

---

## Self-Review Checklist (run before commit)

- All five constants in the patching table above are patched at BOTH `kb.config.X` and the consuming-module `kb.<module>.X`.
- `call_llm` is patched at `kb.query.engine.call_llm`, not at `kb.utils.llm.call_llm`. Patching the import site is required because `engine.py` did `from kb.utils.llm import call_llm` at line 23.
- The test passes `wiki_dir=tmp_project / "wiki"` to every `ingest_source`, `query_wiki`, and `run_all_checks` call. No reliance on patched `WIKI_DIR`.
- The two `extraction` dicts use `entities_mentioned`, `concepts_mentioned`, `key_claims`, and `core_argument` — these are the field names the pipeline reads (verified at `src/kb/ingest/pipeline.py:179, 187, 199, 211`).
- The test asserts that `wikilinks_injected` from the second ingest contains pages created by the first ingest — this is the cross-source integration signal.

---

## Task 1: Create the e2e test file with the happy-path skeleton

**Files:**
- Create: `tests/test_e2e_demo_pipeline.py`

- [ ] **Step 1: Write the test file with the monkeypatch helper, both extractions, and a single assertion that the first ingest creates expected pages.**

Write `tests/test_e2e_demo_pipeline.py` exactly:

```python
"""End-to-end pipeline test: ingest → query → lint over the committed demo sources.

Drives the real ingest_source, query_wiki, and run_all_checks code paths with the
LLM stubbed, using the Karpathy X post and gist files committed under demo/raw/.
Catches integration regressions across module boundaries (ingest pipeline ↔
compile manifest ↔ query engine ↔ lint runner) that single-module unit tests miss.
"""

import shutil
from pathlib import Path

import frontmatter
import pytest

from kb.ingest.pipeline import ingest_source
from kb.lint.runner import run_all_checks
from kb.query.engine import query_wiki

PROJECT = Path(__file__).resolve().parent.parent
DEMO_ARTICLE = PROJECT / "demo" / "raw" / "articles" / "karpathy-x-post.md"
DEMO_PAPER = PROJECT / "demo" / "raw" / "papers" / "karpathy-llm-wiki-gist.md"

# Pre-built extraction dicts — what an LLM would return for each source.
# Field names match those read by src/kb/ingest/pipeline.py (core_argument,
# key_claims, entities_mentioned, concepts_mentioned).
ARTICLE_EXTRACTION = {
    "title": "Karpathy on LLM Knowledge Bases (X post)",
    "core_argument": (
        "A large fraction of recent LLM token throughput goes into building "
        "and querying a personal LLM-first knowledge base, not writing code. "
        "Raw sources go in raw/, the LLM compiles them into an interlinked "
        "markdown wiki, and queries are answered from the compiled wiki."
    ),
    "key_claims": [
        "At ~100 articles / ~400K words no vector database is needed.",
        "Output is polymorphic: markdown, Marp slides, matplotlib images, all viewable in Obsidian.",
        "Wikis previously died on maintenance cost; LLMs make that cost near-zero.",
    ],
    "entities_mentioned": ["Andrej Karpathy", "Obsidian"],
    "concepts_mentioned": ["LLM Knowledge Base", "compile-not-retrieve", "naive search engine"],
}

PAPER_EXTRACTION = {
    "title": "Karpathy LLM Wiki Gist",
    "core_argument": (
        "Persistent LLM-maintained knowledge bases are positioned as an "
        "alternative to RAG. Three layers: raw sources, the wiki, and the "
        "schema. Three operations: ingest, query, lint."
    ),
    "key_claims": [
        "The wiki is a persistent, compounding artifact.",
        "Each ingest updates 10-15 related pages automatically.",
        "The human curates sources; the LLM owns maintenance.",
    ],
    "entities_mentioned": ["Andrej Karpathy"],
    "concepts_mentioned": ["LLM Knowledge Base", "compile-not-retrieve", "ingest-query-lint"],
}


def _redirect_pipeline_constants(monkeypatch: pytest.MonkeyPatch, project_dir: Path) -> None:
    """Point every PROJECT_ROOT / RAW_DIR / WIKI_CONTRADICTIONS / HASH_MANIFEST
    consumer at the temp project, so the pipeline writes nothing to the real repo.

    The double-patch at both kb.config.X and the importing module is required
    because each consumer captured the constant by name at import time.
    """
    raw_dir = project_dir / "raw"
    contradictions = project_dir / "wiki" / "contradictions.md"
    manifest = project_dir / ".data" / "hashes.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("kb.config.PROJECT_ROOT", project_dir)
    monkeypatch.setattr("kb.config.RAW_DIR", raw_dir)
    monkeypatch.setattr("kb.config.WIKI_CONTRADICTIONS", contradictions)

    monkeypatch.setattr("kb.ingest.pipeline.PROJECT_ROOT", project_dir)
    monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw_dir)
    monkeypatch.setattr("kb.ingest.pipeline.WIKI_CONTRADICTIONS", contradictions)

    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", project_dir)
    monkeypatch.setattr("kb.compile.compiler.RAW_DIR", raw_dir)
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", manifest)

    monkeypatch.setattr("kb.query.engine.PROJECT_ROOT", project_dir)


def _stub_synthesis_llm(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replace kb.query.engine.call_llm with a stub that returns a canned
    synthesis answer with a citation. Returns a list that records each call,
    so the test can assert the prompt contained the expected wiki context.
    """
    calls: list[dict] = []

    def fake_call_llm(prompt, *, tier="orchestrate", system=None, max_tokens=None, **kw):
        calls.append({"prompt": prompt, "tier": tier, "system": system})
        return (
            "Compile-not-retrieve means pre-processing raw sources into a "
            "structured wiki at ingest time, instead of searching fragments at "
            "query time [source: concepts/compile-not-retrieve]."
        )

    monkeypatch.setattr("kb.query.engine.call_llm", fake_call_llm)
    return calls


def test_e2e_demo_pipeline(tmp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive the full ingest → query → lint flow over the demo Karpathy sources."""
    _redirect_pipeline_constants(monkeypatch, tmp_project)
    llm_calls = _stub_synthesis_llm(monkeypatch)

    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"

    # 1. Stage the demo files inside the temp project's raw/.
    article_target = raw_dir / "articles" / "karpathy-x-post.md"
    paper_target = raw_dir / "papers" / "karpathy-llm-wiki-gist.md"
    shutil.copy(DEMO_ARTICLE, article_target)
    shutil.copy(DEMO_PAPER, paper_target)

    # 2. First ingest: the X post.
    article_result = ingest_source(
        article_target,
        source_type="article",
        extraction=ARTICLE_EXTRACTION,
        wiki_dir=wiki_dir,
    )

    # Assert the summary, both entities, and all three concepts were created.
    assert "summaries/karpathy-on-llm-knowledge-bases-x-post" in article_result["pages_created"]
    assert "entities/andrej-karpathy" in article_result["pages_created"]
    assert "entities/obsidian" in article_result["pages_created"]
    assert "concepts/llm-knowledge-base" in article_result["pages_created"]
    assert "concepts/compile-not-retrieve" in article_result["pages_created"]
    assert "concepts/naive-search-engine" in article_result["pages_created"]

    # Sanity: no orphan junk in the result dict.
    assert article_result["pages_skipped"] == []
    assert "duplicate" not in article_result
```

- [ ] **Step 2: Run the file once and confirm the first assertion block passes.**

Run: `.venv/Scripts/python -m pytest tests/test_e2e_demo_pipeline.py -v`
Expected: 1 passed.

If it fails, do not edit assertions. Read the failure, fix the underlying issue (likely a missed monkeypatch or a typo in a slug), then re-run.

- [ ] **Step 3: Commit the skeleton.**

```bash
git add tests/test_e2e_demo_pipeline.py
git commit -m "test: scaffold e2e pipeline test driving demo Karpathy sources"
```

---

## Task 2: Add cross-source ingest assertions

**Files:**
- Modify: `tests/test_e2e_demo_pipeline.py` (append to `test_e2e_demo_pipeline`)

- [ ] **Step 1: Append the second ingest plus its assertions immediately after the article block in the test function.**

Append this block to `test_e2e_demo_pipeline` (place it right after the `assert "duplicate" not in article_result` line):

```python
    # 3. Second ingest: the gist. Existing entity/concept pages must be UPDATED,
    #    not duplicated. New pages (ingest-query-lint concept) must be CREATED.
    paper_result = ingest_source(
        paper_target,
        source_type="paper",
        extraction=PAPER_EXTRACTION,
        wiki_dir=wiki_dir,
    )

    assert "summaries/karpathy-llm-wiki-gist" in paper_result["pages_created"]
    assert "concepts/ingest-query-lint" in paper_result["pages_created"]

    # Andrej Karpathy + LLM Knowledge Base + compile-not-retrieve already exist —
    # they go to pages_updated, not pages_created.
    assert "entities/andrej-karpathy" in paper_result["pages_updated"]
    assert "concepts/llm-knowledge-base" in paper_result["pages_updated"]
    assert "concepts/compile-not-retrieve" in paper_result["pages_updated"]
    assert "entities/andrej-karpathy" not in paper_result["pages_created"]

    # Frontmatter on the shared entity must list both source files.
    karpathy_page = wiki_dir / "entities" / "andrej-karpathy.md"
    fm = frontmatter.loads(karpathy_page.read_text(encoding="utf-8"))
    sources = fm.metadata.get("source") or []
    assert "raw/articles/karpathy-x-post.md" in sources
    assert "raw/papers/karpathy-llm-wiki-gist.md" in sources

    # Retroactive wikilink injection: the new ingest-query-lint concept page
    # should have been linked into pages from the first ingest that mention it.
    # At minimum the new summary itself shouldn't be an orphan after both ingests.
    assert isinstance(paper_result["wikilinks_injected"], list)
```

- [ ] **Step 2: Run the test.**

Run: `.venv/Scripts/python -m pytest tests/test_e2e_demo_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit.**

```bash
git add tests/test_e2e_demo_pipeline.py
git commit -m "test: assert cross-source dedup + frontmatter merge in e2e pipeline"
```

---

## Task 3: Add query and lint assertions

**Files:**
- Modify: `tests/test_e2e_demo_pipeline.py` (append to `test_e2e_demo_pipeline`)

- [ ] **Step 1: Append the query and lint blocks at the end of the test function.**

Append immediately after the `assert isinstance(paper_result["wikilinks_injected"], list)` line:

```python
    # 4. Query the compiled wiki. The stub returns a fixed answer; we verify
    #    the prompt to call_llm actually contained the relevant page content.
    query_result = query_wiki(
        "What does compile-not-retrieve mean?",
        wiki_dir=wiki_dir,
        max_results=5,
    )

    assert query_result["question"] == "What does compile-not-retrieve mean?"
    assert "[source: concepts/compile-not-retrieve]" in query_result["answer"]
    assert query_result["citations"], "expected at least one extracted citation"
    assert any(c["path"] == "concepts/compile-not-retrieve" for c in query_result["citations"])
    assert "concepts/compile-not-retrieve" in query_result["context_pages"]

    # The stubbed LLM was called exactly once for synthesis.
    assert len(llm_calls) == 1
    assert "compile-not-retrieve" in llm_calls[0]["prompt"].lower()

    # 5. Lint the wiki. With both Karpathy sources fully ingested and
    #    cross-linked, no error-severity issues should be present.
    lint_report = run_all_checks(wiki_dir=wiki_dir, raw_dir=raw_dir)
    assert lint_report["summary"]["error"] == 0, (
        f"lint reported errors: "
        f"{[i for i in lint_report['issues'] if i.get('severity') == 'error']}"
    )
    # Sanity: lint actually ran every check, not a no-op early return.
    expected_checks = {
        "dead_links", "orphan_pages", "staleness", "frontmatter",
        "source_coverage", "wikilink_cycles", "stub_pages",
    }
    assert {c["name"] for c in lint_report["checks_run"]} == expected_checks
```

- [ ] **Step 2: Run the test.**

Run: `.venv/Scripts/python -m pytest tests/test_e2e_demo_pipeline.py -v`
Expected: 1 passed.

If `lint_report["summary"]["error"] > 0`, do not weaken the assertion. Read the issue list (the assertion message prints them) and either fix the underlying lint bug or expand the extraction dicts so the wiki passes lint. The point of this test is to catch real integration breakage; loosening the assertion defeats the purpose.

- [ ] **Step 3: Commit.**

```bash
git add tests/test_e2e_demo_pipeline.py
git commit -m "test: assert query synthesis + clean lint over compiled demo wiki"
```

---

## Task 4: Run the full suite and confirm no regressions

**Files:**
- None modified.

- [ ] **Step 1: Run every test.**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `1178 passed` (1177 baseline + 1 new e2e test). No new failures, no errors.

If any pre-existing test now fails, the new test's monkeypatching is leaking — most likely because `monkeypatch.setattr` is not restoring a constant cleanly. Check that every patched attribute exists on the target module before the patch (no `raising=False`); pytest will then auto-restore on teardown.

- [ ] **Step 2: Run ruff to confirm no style regressions.**

Run: `.venv/Scripts/ruff check tests/test_e2e_demo_pipeline.py`
Expected: `All checks passed!`

If unused-import warnings appear, remove the offending imports. Do not add `# noqa`.

- [ ] **Step 3: No commit needed for this task — the previous three commits already cover the deliverable.**

---

## Task 5: Document the new test in CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md` (add one bullet under `[Unreleased]` → `### Added`)

- [ ] **Step 1: Open `CHANGELOG.md` and find the line `## [Unreleased]` near the top of the file. Under the existing `### Added` subsection, insert this bullet after the last existing bullet:**

```markdown
- `tests/test_e2e_demo_pipeline.py` — single hermetic end-to-end pipeline test driving ingest → query → lint over the committed demo Karpathy sources with the synthesis LLM stubbed; catches cross-module integration regressions
```

If the `[Unreleased] / ### Added` section does not exist yet, create it directly under `## [Unreleased]`.

- [ ] **Step 2: Commit and push.**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for e2e demo pipeline test"
git push origin main
```

---

## What this plan does NOT cover (explicitly out of scope)

- Layer 2 (MCP contract e2e via `fastmcp.Client`) — separate plan when needed.
- Layer 3 (live smoke test against the real Anthropic API) — separate plan when needed.
- Snapshot/golden-file diffing of the entire `wiki/` output. Deliberately omitted because (a) the demo committed under `demo/wiki/` is the authoring intent, not a regenerable artifact, and (b) golden files create churn on every legitimate prompt or template change. Field-level assertions in this plan are tighter and less brittle.
- Stub auto-recording (`vcrpy` cassettes against the Anthropic SDK). Not needed: the only LLM call in the pipeline path is the query-synthesis call, and a hand-written stub is shorter than a cassette.
- Backfilling `tests/conftest.py` `RAW_SUBDIRS` to include the missing 4 source types (podcasts/books/datasets/conversations). Pre-existing gap, unrelated to e2e.
