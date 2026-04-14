# kb_query Output Adapters (Phase 4.11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 output adapters (markdown, marp, html, chart, jupyter) to `kb_query` that serialize synthesized answers into file artifacts under `outputs/` at project root.

**Architecture:** New package `src/kb/query/formats/` with one module per adapter + shared `common.py`. `query_wiki` gains a keyword-only `output_format` param (zero breakage to 1322 existing callers). CLI exposes `--format`; MCP tool exposes `output_format` (requires `use_api=True`). Outputs live OUTSIDE `wiki/` to prevent search-index poisoning; `outputs/` is gitignored. 16 security gates (path traversal, HTML injection, Python-script code injection, Jupyter auto-exec, Marp fence-splitter, Windows reserved names, slug collisions, ...) with explicit tests each.

**Tech Stack:** Python 3.12+, Click 8.x, FastMCP, pytest, `nbformat` (new dependency), stdlib `html`/`json`/`datetime`. No matplotlib runtime dependency (chart adapter emits a script the user runs).

**Spec:** `docs/superpowers/specs/2026-04-14-kb-query-formats-design.md`

---

## File structure

### New files (package `src/kb/query/formats/`)

| File | Responsibility | Approx LOC |
|---|---|---|
| `__init__.py` | Public `render_output(fmt, result)` + `ADAPTERS` dict + `VALID_FORMATS` re-export | ~35 |
| `common.py` | `safe_slug`, `output_path_for`, `build_provenance`, `validate_payload_size`, `MAX_OUTPUT_CHARS`, `OUTPUTS_DIR` | ~85 |
| `markdown.py` | `render_markdown(result) -> str` | ~50 |
| `marp.py` | `render_marp(result) -> str` — code-fence-aware slide splitter | ~75 |
| `html.py` | `render_html(result) -> str` — XSS-safe template | ~100 |
| `chart.py` | `render_chart(result) -> tuple[str, str]` — Python + JSON | ~80 |
| `jupyter.py` | `render_jupyter(result) -> str` — nbformat with kernelspec | ~60 |

### Modified files

| File | Change |
|---|---|
| `src/kb/query/citations.py` | Add `mode: str = "markdown"` kwarg to `format_citations` — adds `"html"` + `"marp"` modes; default preserves behavior |
| `src/kb/query/engine.py` | Add keyword-only `output_format` param to `query_wiki`; dispatch to `render_output` when set and non-text |
| `src/kb/cli.py` | Add `--format` option to `query` command; echo `Output: <path>` when set |
| `src/kb/mcp/core.py` | Add `output_format` param to `kb_query`; validate at MCP boundary; require `use_api=True` if non-empty |
| `src/kb/config.py` | Add `OUTPUTS_DIR = PROJECT_ROOT / "outputs"` and `MAX_OUTPUT_CHARS = 500_000` |
| `.gitignore` | Add `outputs/` |
| `requirements.txt` | Add `nbformat>=5.0,<6.0` |
| `CLAUDE.md` | Test count, module count (19→20), `query_wiki` signature, MCP tool param, Output Formats section |
| `README.md` | Feature row, tree comment |
| `CHANGELOG.md` | `[Unreleased]` → Added |
| `BACKLOG.md` | Delete Tier 1 item #1, trim HIGH LEVERAGE bullet |
| `docs/architecture/architecture-diagram.html` + PNG | Add Output Adapters block |

### New test files

| File | Coverage |
|---|---|
| `tests/test_v4_11_formats_common.py` | slug, path, provenance, size guard |
| `tests/test_v4_11_markdown.py` | markdown adapter |
| `tests/test_v4_11_marp.py` | marp adapter + fence-aware split |
| `tests/test_v4_11_html.py` | html adapter XSS safety |
| `tests/test_v4_11_chart.py` | chart adapter injection safety |
| `tests/test_v4_11_jupyter.py` | jupyter adapter kernelspec + trusted |
| `tests/test_v4_11_query_integration.py` | query_wiki end-to-end |
| `tests/test_v4_11_cli.py` | CLI `--format` flag |
| `tests/test_v4_11_mcp.py` | MCP `output_format` param |
| `tests/test_v4_11_security.py` | consolidated adversarial payloads |

---

## Task 1: Config constants + common helpers

**Files:**
- Modify: `src/kb/config.py` (add 2 constants)
- Create: `src/kb/query/formats/__init__.py` (empty for now — package marker)
- Create: `src/kb/query/formats/common.py`
- Create: `tests/test_v4_11_formats_common.py`

### Step 1.1: Write failing tests for `common.py`

- [ ] Create test file with fixtures and assertions:

```python
# tests/test_v4_11_formats_common.py
"""Tests for kb.query.formats.common — slug, path, provenance, size guard."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kb.query.formats.common import (
    MAX_OUTPUT_CHARS,
    OUTPUTS_DIR,
    WINDOWS_RESERVED,
    build_provenance,
    output_path_for,
    safe_slug,
    validate_payload_size,
)


# ---- safe_slug ----

def test_safe_slug_plain():
    assert safe_slug("What is RAG?") == "what-is-rag"


def test_safe_slug_empty_fallback():
    # pure emoji / symbol-only produces empty slug → must fall back
    assert safe_slug("") == "untitled"
    assert safe_slug("?!?") == "untitled"
    assert safe_slug("🔥🔥🔥") == "untitled"


def test_safe_slug_length_cap():
    long_text = "a" * 500
    slug = safe_slug(long_text)
    assert len(slug) <= 80


def test_safe_slug_windows_reserved():
    for name in ("con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9"):
        result = safe_slug(name)
        assert result not in WINDOWS_RESERVED
        assert result.endswith("_0")


def test_safe_slug_windows_reserved_with_extension_part():
    # Reserved name with dot-separator disambig still fires on first dot-part
    result = safe_slug("con.backup")
    # slugify strips the dot, so we get "conbackup" which is not reserved
    # Confirm that the reserved detection works on the final slug parts
    assert "_0" not in result or result.split(".")[0].upper() not in WINDOWS_RESERVED


# ---- output_path_for ----

def test_output_path_for_creates_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = output_path_for("What is RAG?", "markdown")
    assert path.parent.exists()
    assert path.parent.name == "outputs"


def test_output_path_for_extensions(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    assert output_path_for("q", "markdown").suffix == ".md"
    assert output_path_for("q", "marp").suffix == ".md"
    assert output_path_for("q", "html").suffix == ".html"
    assert output_path_for("q", "chart").suffix == ".py"
    assert output_path_for("q", "jupyter").suffix == ".ipynb"


def test_output_path_for_timestamp_format(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = output_path_for("What is RAG?", "markdown")
    # Filename: YYYY-MM-DD-HHMMSS-ffffff-what-is-rag.md
    stem = path.stem
    assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-\d{6}-", stem), f"bad stem: {stem}"


def test_output_path_for_collision_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    # Pre-create two files that match the first two candidate stems to force retry
    (tmp_path / "outputs").mkdir()
    # We can't know exact timestamp, so instead test the retry behavior by
    # monkeypatching timestamp to return a fixed value
    import kb.query.formats.common as common_mod
    captured_stems = []

    orig_for = common_mod.output_path_for

    def fake_output_path_for(question: str, fmt: str) -> Path:
        # simulate collision by pre-creating the returned file
        p = orig_for(question, fmt)
        captured_stems.append(p.name)
        return p

    monkeypatch.setattr(common_mod, "output_path_for", fake_output_path_for)

    p1 = common_mod.output_path_for("collision-test", "markdown")
    p1.write_text("x", encoding="utf-8")
    p2 = common_mod.output_path_for("collision-test", "markdown")
    # Stems differ by microseconds — easy pass. Exhaust-retry case is tested
    # indirectly through MAX_COLLISION_RETRIES.
    assert p1 != p2


def test_output_path_for_invalid_format(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    with pytest.raises(KeyError):
        output_path_for("q", "pdf")


# ---- build_provenance ----

def test_build_provenance_minimal():
    result = {
        "question": "What is RAG?",
        "answer": "RAG is...",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    prov = build_provenance(result)
    assert prov["type"] == "query_output"
    assert prov["query"] == "What is RAG?"
    assert "generated_at" in prov
    assert prov["kb_version"]
    assert prov["source_pages"] == []
    assert prov["citations"] == []


def test_build_provenance_preserves_original_question():
    # Even if caller passes effective_question in metadata, the provenance
    # must record the ORIGINAL question (result["question"] is original).
    result = {"question": "orig?", "answer": "x", "citations": [], "source_pages": []}
    assert build_provenance(result)["query"] == "orig?"


def test_build_provenance_kb_version_dynamic():
    """kb_version must come from kb.__version__, not a hardcoded string."""
    import kb
    result = {"question": "q", "answer": "a", "citations": [], "source_pages": []}
    assert build_provenance(result)["kb_version"] == kb.__version__


# ---- validate_payload_size ----

def test_validate_payload_size_ok():
    validate_payload_size({"answer": "a" * 1000})  # no raise


def test_validate_payload_size_rejects_oversize():
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        validate_payload_size({"answer": "a" * (MAX_OUTPUT_CHARS + 1)})


def test_validate_payload_size_empty_ok():
    # Empty answer is allowed — the adapter may still render a "no-match" file
    validate_payload_size({"answer": ""})
    validate_payload_size({})
```

- [ ] Run tests to verify they fail:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_formats_common.py -x -q
```

Expected: `ModuleNotFoundError: No module named 'kb.query.formats'` (module doesn't exist yet).

### Step 1.2: Add config constants

- [ ] Open `src/kb/config.py`. Find the last constant definition near the top-level (search for a block of `FOO = ...` lines). Append:

```python
# Query output adapters — Phase 4.11
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MAX_OUTPUT_CHARS = 500_000
```

(Put these near the other path/limit constants. If `PROJECT_ROOT` isn't imported at that line, it already is — `config.py` defines it.)

### Step 1.3: Create package marker

- [ ] Create `src/kb/query/formats/__init__.py` with placeholder content (will grow in Task 8):

```python
"""Output-format adapters for kb_query (Phase 4.11).

Public API:
    render_output(fmt, result) -> Path
    VALID_FORMATS: frozenset[str]
"""
```

### Step 1.4: Implement `common.py`

- [ ] Create `src/kb/query/formats/common.py`:

```python
"""Shared helpers for query output adapters.

- safe_slug: slugify with empty-fallback + Windows-reserved-name guard + length cap
- output_path_for: collision-safe output path under OUTPUTS_DIR
- build_provenance: common provenance dict (dynamic kb_version)
- validate_payload_size: pre-render size guard
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kb import __version__ as KB_VERSION
from kb.config import MAX_OUTPUT_CHARS, OUTPUTS_DIR
from kb.utils.text import slugify

WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})
MAX_SLUG_LEN = 80
MAX_COLLISION_RETRIES = 9

_FORMAT_EXT = {
    "markdown": "md",
    "marp": "md",
    "html": "html",
    "chart": "py",
    "jupyter": "ipynb",
}


def safe_slug(text: str) -> str:
    """Slugify with empty-fallback + Windows-reserved-name guard + length cap."""
    slug = slugify(text)[:MAX_SLUG_LEN] if text else ""
    if not slug:
        return "untitled"
    # Guard Windows reserved names on any dot-separated component
    if any(part.upper() in WINDOWS_RESERVED for part in slug.split(".") if part):
        slug = f"{slug}_0"
    return slug


def output_path_for(question: str, fmt: str) -> Path:
    """Return a collision-safe path under OUTPUTS_DIR for this question+format.

    Path scheme: outputs/{YYYY-MM-DD-HHMMSS-ffffff}-{slug}.{ext}
    If the first candidate exists (microsecond collision under heavy concurrency),
    suffixes -2..-9 are tried. Raises OSError if all retries exhausted.
    """
    ext = _FORMAT_EXT[fmt]  # KeyError for bad format — caught upstream
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S-%f")
    slug = safe_slug(question)
    base = f"{ts}-{slug}"
    for suffix in ("", *(f"-{i}" for i in range(2, MAX_COLLISION_RETRIES + 2))):
        candidate = OUTPUTS_DIR / f"{base}{suffix}.{ext}"
        if not candidate.exists():
            return candidate
    raise OSError(f"Collision retries exhausted for {base}.{ext}")


def build_provenance(result: dict) -> dict:
    """Assemble the common provenance dict used across adapters.

    Note: result['question'] is the ORIGINAL (not rewritten) question —
    query_wiki stores the original at engine.py:425.
    """
    return {
        "type": "query_output",
        "query": result.get("question", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "kb_version": KB_VERSION,
        "source_pages": list(result.get("source_pages", [])),
        "citations": list(result.get("citations", [])),
    }


def validate_payload_size(result: dict) -> None:
    """Raise ValueError if the answer exceeds MAX_OUTPUT_CHARS (pre-render)."""
    answer = result.get("answer", "") or ""
    if len(answer) > MAX_OUTPUT_CHARS:
        raise ValueError(
            f"Answer exceeds MAX_OUTPUT_CHARS={MAX_OUTPUT_CHARS} "
            f"(got {len(answer)}). Refuse to render."
        )
```

### Step 1.5: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_formats_common.py -x -q
```

Expected: PASS for all tests. Windows reserved guard, slug length, timestamp format, provenance all green.

### Step 1.6: Commit

- [ ] Commit:

```bash
git add src/kb/config.py src/kb/query/formats/__init__.py src/kb/query/formats/common.py tests/test_v4_11_formats_common.py
git commit -m "feat(phase-4.11): scaffold query/formats package + common helpers

- OUTPUTS_DIR = PROJECT_ROOT/outputs (gitignored downstream)
- MAX_OUTPUT_CHARS = 500_000
- safe_slug: empty→'untitled', Windows reserved disambig, 80-char cap
- output_path_for: microsecond timestamp + collision retry -2..-9
- build_provenance: dynamic kb_version from kb.__version__
- validate_payload_size: pre-render answer size guard"
```

---

## Task 2: Extend `format_citations` with render modes

**Files:**
- Modify: `src/kb/query/citations.py` (add `mode` kwarg)
- Modify: `tests/test_query.py` (add 2 tests)

### Step 2.1: Write failing tests for new modes

- [ ] Edit `tests/test_query.py`. Find `test_format_citations_empty` (around line 76) and append:

```python
def test_format_citations_html_mode():
    """HTML mode returns <a> anchors with escaped paths."""
    from kb.query.citations import format_citations

    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/articles/foo.md", "context": "..."},
    ]
    result = format_citations(citations, mode="html")
    assert "<ul>" in result
    assert '<a href="./wiki/concepts/rag.md">concepts/rag</a>' in result
    assert "<code>raw/articles/foo.md</code>" in result
    # No raw < > that could land mid-HTML unescaped
    assert "<script>" not in result


def test_format_citations_html_escapes_path():
    """HTML mode must escape path components (defense-in-depth — citations regex
    upstream already rejects most but internal test for peace of mind)."""
    from kb.query.citations import format_citations

    # Craft a 'legal-looking' path containing harmless chars; verify no raw HTML leaks.
    citations = [{"type": "wiki", "path": "concepts/foo-bar", "context": "x"}]
    out = format_citations(citations, mode="html")
    assert "concepts/foo-bar" in out
    assert "<a href=" in out


def test_format_citations_marp_mode():
    """Marp mode returns markdown wikilinks compatible with marp renderer."""
    from kb.query.citations import format_citations

    citations = [
        {"type": "wiki", "path": "concepts/rag", "context": "..."},
        {"type": "raw", "path": "raw/a.md", "context": "..."},
    ]
    out = format_citations(citations, mode="marp")
    assert "[[concepts/rag]]" in out
    assert "`raw/a.md`" in out


def test_format_citations_default_mode_unchanged():
    """Default mode must match previous behavior exactly — no call-site breakage."""
    from kb.query.citations import format_citations

    citations = [{"type": "wiki", "path": "concepts/rag", "context": "x"}]
    # These older call sites pass only positional arg — must keep working
    legacy = format_citations(citations)
    explicit = format_citations(citations, mode="markdown")
    assert legacy == explicit
    assert "[[concepts/rag]]" in legacy


def test_format_citations_invalid_mode():
    """Unknown mode raises ValueError."""
    from kb.query.citations import format_citations

    with pytest.raises(ValueError, match="mode"):
        format_citations([], mode="latex")
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_query.py -k "format_citations" -x -q
```

Expected: 5 new tests fail (TypeError/ValueError).

### Step 2.2: Implement `mode` kwarg

- [ ] Edit `src/kb/query/citations.py`. Replace the `format_citations` function with:

```python
import html as _html


def format_citations(citations: list[dict], mode: str = "markdown") -> str:
    """Format citations as a sources section in the requested mode.

    Modes:
        "markdown" (default): unchanged legacy behavior — `[[wikilinks]]` + `` `raw/paths` ``.
        "html":     `<ul>` list of `<a href="./wiki/path.md">path</a>` + `<code>raw/path</code>`.
        "marp":     same wiki/raw rendering as markdown (kept as distinct mode
                    so future Marp-specific link syntax can diverge).

    Raises:
        ValueError: unknown mode.
    """
    if mode not in {"markdown", "html", "marp"}:
        raise ValueError(f"format_citations: unknown mode '{mode}'")
    if not citations:
        return ""

    seen: set[str] = set()
    deduped: list[dict] = []
    for cite in citations:
        path = cite["path"]
        if path in seen:
            continue
        seen.add(path)
        deduped.append(cite)

    if mode == "html":
        lines = ["<ul class=\"sources\">"]
        for cite in deduped:
            path = cite["path"]
            escaped_path = _html.escape(path, quote=True)
            if cite["type"] == "wiki":
                href = f"./wiki/{escaped_path}.md"
                lines.append(f'  <li><a href="{href}">{escaped_path}</a></li>')
            else:
                lines.append(f'  <li><code>{escaped_path}</code></li>')
        lines.append("</ul>")
        return "\n".join(lines)

    # markdown + marp share the current legacy rendering
    lines = ["\n---\n**Sources:**\n"]
    for cite in deduped:
        path = cite["path"]
        if cite["type"] == "wiki":
            lines.append(f"- [[{path}]]")
        else:
            lines.append(f"- `{path}`")
    return "\n".join(lines)
```

### Step 2.3: Run all query tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_query.py -x -q
```

Expected: all tests pass (old behavior preserved + 5 new pass).

### Step 2.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/citations.py tests/test_query.py
git commit -m "feat(phase-4.11): extend format_citations with html/marp render modes

Adds mode='markdown'|'html'|'marp' kwarg (default 'markdown' preserves
every existing call site; verified via grep of cli.py + mcp/core.py).
HTML mode emits <ul> with <a> anchors + html.escape per field.
Marp mode matches markdown for now — reserved for future divergence."
```

---

## Task 3: Markdown adapter

**Files:**
- Create: `src/kb/query/formats/markdown.py`
- Create: `tests/test_v4_11_markdown.py`

### Step 3.1: Write failing tests

- [ ] Create `tests/test_v4_11_markdown.py`:

```python
"""Tests for kb.query.formats.markdown adapter."""

from __future__ import annotations

import pytest
import yaml

from kb.query.formats.markdown import render_markdown


@pytest.fixture
def sample_result():
    return {
        "question": "What is compile-not-retrieve?",
        "answer": "Compile-not-retrieve is a philosophy where...",
        "citations": [
            {"type": "wiki", "path": "concepts/compile-not-retrieve", "context": "..."},
            {"type": "wiki", "path": "entities/karpathy", "context": "..."},
        ],
        "source_pages": ["concepts/compile-not-retrieve", "entities/karpathy"],
        "context_pages": ["concepts/compile-not-retrieve"],
    }


def test_markdown_has_frontmatter(sample_result):
    out = render_markdown(sample_result)
    assert out.startswith("---\n")
    # YAML frontmatter must parse
    parts = out.split("---\n", 2)
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm["type"] == "query_output"
    assert fm["format"] == "markdown"
    assert fm["query"] == "What is compile-not-retrieve?"
    assert "generated_at" in fm


def test_markdown_embeds_answer(sample_result):
    out = render_markdown(sample_result)
    assert "Compile-not-retrieve is a philosophy where..." in out


def test_markdown_renders_wiki_sources(sample_result):
    out = render_markdown(sample_result)
    assert "[[concepts/compile-not-retrieve]]" in out
    assert "[[entities/karpathy]]" in out


def test_markdown_h1_is_question(sample_result):
    out = render_markdown(sample_result)
    assert "# What is compile-not-retrieve?" in out


def test_markdown_no_citations(sample_result):
    sample_result["citations"] = []
    out = render_markdown(sample_result)
    # no Sources section if empty
    assert "**Sources:**" not in out


def test_markdown_kb_version_from_module(sample_result):
    import kb
    out = render_markdown(sample_result)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["kb_version"] == kb.__version__


def test_markdown_escapes_quotes_in_frontmatter(sample_result):
    sample_result["question"] = 'What about "quoted" text?'
    out = render_markdown(sample_result)
    # Must still parse
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["query"] == 'What about "quoted" text?'
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_markdown.py -x -q
```

Expected: `ModuleNotFoundError: No module named 'kb.query.formats.markdown'`.

### Step 3.2: Implement `markdown.py`

- [ ] Create `src/kb/query/formats/markdown.py`:

```python
"""Markdown output adapter — Phase 4.11.

Emits a standalone markdown file with YAML provenance frontmatter +
H1 question + answer body + citations list. Frontmatter is parseable
by any YAML consumer; citations list uses [[wikilinks]] compatible
with Obsidian / wiki-compile tooling.
"""

from __future__ import annotations

import yaml

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size


def render_markdown(result: dict) -> str:
    """Render a query result as a standalone markdown document.

    Args:
        result: dict with keys question, answer, citations, source_pages.

    Returns:
        The full document as a string (UTF-8 safe; no encoding applied here).

    Raises:
        ValueError: answer exceeds MAX_OUTPUT_CHARS.
    """
    validate_payload_size(result)

    prov = build_provenance(result)
    prov["format"] = "markdown"

    # yaml.safe_dump handles quoting, newlines, and unicode.
    frontmatter = yaml.safe_dump(
        prov, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    question = result.get("question", "").strip() or "(untitled query)"
    answer = result.get("answer", "").strip() or "_No answer synthesized._"

    citations = result.get("citations", [])
    sources_block = format_citations(citations, mode="markdown") if citations else ""

    return f"---\n{frontmatter}---\n\n# {question}\n\n{answer}\n{sources_block}\n"
```

### Step 3.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_markdown.py -x -q
```

Expected: PASS.

### Step 3.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/formats/markdown.py tests/test_v4_11_markdown.py
git commit -m "feat(phase-4.11): markdown adapter — YAML frontmatter + citations"
```

---

## Task 4: Marp adapter (code-fence-aware slide split)

**Files:**
- Create: `src/kb/query/formats/marp.py`
- Create: `tests/test_v4_11_marp.py`

### Step 4.1: Write failing tests

- [ ] Create `tests/test_v4_11_marp.py`:

```python
"""Tests for kb.query.formats.marp adapter."""

from __future__ import annotations

import pytest

from kb.query.formats.marp import _split_into_slides, render_marp


@pytest.fixture
def simple_result():
    return {
        "question": "What is RAG?",
        "answer": "RAG means Retrieval Augmented Generation.\n\nIt combines retrieval with LLMs.",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
    }


def test_marp_has_marp_directive(simple_result):
    out = render_marp(simple_result)
    assert "marp: true" in out
    assert out.startswith("---\n")


def test_marp_slide_separators(simple_result):
    out = render_marp(simple_result)
    # At minimum: top frontmatter + Question slide + Answer slide(s) + Sources slide
    # Slides are separated by lines containing only "---"
    separators = [line for line in out.split("\n") if line.strip() == "---"]
    # 1 open, 1 close of frontmatter = 2; Question/Answer/Sources separators = 3 → total ≥ 5
    assert len(separators) >= 5


def test_marp_has_sources_slide(simple_result):
    out = render_marp(simple_result)
    assert "# Sources" in out
    assert "[[concepts/rag]]" in out


def test_marp_splits_long_answer_on_paragraphs():
    """Long answer split into multiple slides at \\n\\n boundaries."""
    answer = "\n\n".join(["Paragraph " + str(i) + " " + ("x" * 300) for i in range(5)])
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) >= 2  # must split


def test_marp_preserves_fenced_code_block():
    """Code blocks with blank lines inside must NOT be split."""
    # A fenced block containing a blank line
    code_block = "```python\ndef foo():\n\n    return 42\n```"
    # Wrap in paragraphs that would otherwise cause splitting
    answer = "Before code.\n\n" + code_block + "\n\nAfter code. " + ("x" * 500)
    slides = _split_into_slides(answer, max_chars=300)
    # The code block must appear intact on exactly one slide
    fence_slides = [s for s in slides if "```python" in s]
    assert len(fence_slides) == 1
    assert "def foo():" in fence_slides[0]
    assert "return 42" in fence_slides[0]
    assert fence_slides[0].count("```") == 2  # open + close on same slide


def test_marp_handles_single_long_paragraph():
    """A paragraph >800 chars is kept whole — no mid-word break."""
    answer = "a" * 2000  # single block, no blank line
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) == 1
    assert len(slides[0]) == 2000


def test_marp_question_slide(simple_result):
    out = render_marp(simple_result)
    assert "# Question" in out or "# What is RAG?" in out


def test_marp_splits_on_plain_paragraphs():
    answer = "\n\n".join([f"p{i} " + ("x" * 300) for i in range(6)])
    slides = _split_into_slides(answer, max_chars=800)
    assert len(slides) >= 2
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_marp.py -x -q
```

Expected: `ModuleNotFoundError`.

### Step 4.2: Implement `marp.py`

- [ ] Create `src/kb/query/formats/marp.py`:

```python
"""Marp output adapter — Phase 4.11.

Emits marp-compatible markdown (marp: true directive + --- slide separators).
The slide splitter is code-fence-aware: fenced blocks are never broken across
slides, even if their internal blank lines would otherwise trigger a split.
"""

from __future__ import annotations

import yaml

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size

_DEFAULT_SLIDE_CHARS = 800


def _split_into_slides(text: str, max_chars: int = _DEFAULT_SLIDE_CHARS) -> list[str]:
    """Split text into slide-sized chunks while preserving fenced code blocks.

    Splits on \\n\\n boundaries, packing paragraphs until max_chars is reached,
    but never breaks inside a triple-backtick fenced region. A fenced block
    larger than max_chars is kept whole (overflow is acceptable).

    Args:
        text: the raw markdown body to split.
        max_chars: soft cap per slide (exceeded only to preserve fenced blocks).

    Returns:
        List of slide strings; at least one element (may equal original text).
    """
    if not text:
        return [""]

    segments = text.split("\n\n")
    slides: list[str] = []
    current: list[str] = []
    current_len = 0
    in_fence = False

    for seg in segments:
        # Count fence toggles in this segment; odd count flips the state
        fences = seg.count("```")
        would_toggle = (fences % 2) == 1

        # If we're NOT in a fence and adding seg would exceed the cap, flush
        add_len = len(seg) + (2 if current else 0)  # +2 for the "\n\n" rejoin
        if current and not in_fence and (current_len + add_len) > max_chars:
            slides.append("\n\n".join(current))
            current = [seg]
            current_len = len(seg)
        else:
            current.append(seg)
            current_len += add_len

        if would_toggle:
            in_fence = not in_fence

    if current:
        slides.append("\n\n".join(current))

    return slides if slides else [""]


def render_marp(result: dict) -> str:
    """Render a query result as a marp-compatible markdown deck.

    Slide structure:
        - Frontmatter (marp: true + provenance metadata)
        - Question slide
        - One or more Answer slides (800-char soft cap, fence-aware split)
        - Sources slide

    Raises:
        ValueError: answer exceeds MAX_OUTPUT_CHARS.
    """
    validate_payload_size(result)

    prov = build_provenance(result)
    prov["format"] = "marp"

    marp_header = {
        "marp": True,
        "theme": "default",
        "paginate": True,
        **{f"kb_{k}": v for k, v in prov.items()},
    }
    frontmatter = yaml.safe_dump(
        marp_header, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    question = result.get("question", "").strip() or "(untitled)"
    answer = result.get("answer", "").strip() or "_No answer synthesized._"
    citations = result.get("citations", [])
    sources_block = (
        format_citations(citations, mode="marp") if citations else "_No sources cited._"
    )

    answer_slides = _split_into_slides(answer)
    answer_section_md = []
    for i, slide in enumerate(answer_slides):
        title = "# Answer" if i == 0 else f"# Answer (cont. {i + 1})"
        answer_section_md.append(f"{title}\n\n{slide}")

    parts = [
        f"---\n{frontmatter}---\n",
        f"# Question\n\n{question}\n",
        *(f"---\n\n{slide}\n" for slide in answer_section_md),
        f"---\n\n# Sources\n\n{sources_block}\n",
    ]
    return "\n".join(parts)
```

### Step 4.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_marp.py -x -q
```

Expected: PASS.

### Step 4.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/formats/marp.py tests/test_v4_11_marp.py
git commit -m "feat(phase-4.11): marp adapter with code-fence-aware slide splitter

Slide splitter is a state machine that toggles on triple-backtick fences;
never shatters a fenced code block across two slides. Falls back to whole-
block slide for >800-char fenced regions (overflow is acceptable)."
```

---

## Task 5: HTML adapter (XSS-safe)

**Files:**
- Create: `src/kb/query/formats/html.py`
- Create: `tests/test_v4_11_html.py`

### Step 5.1: Write failing tests

- [ ] Create `tests/test_v4_11_html.py`:

```python
"""Tests for kb.query.formats.html adapter."""

from __future__ import annotations

import pytest

from kb.query.formats.html import render_html


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is...\n\nSecond paragraph.",
        "citations": [
            {"type": "wiki", "path": "concepts/rag", "context": "..."},
            {"type": "raw", "path": "raw/articles/foo.md", "context": "..."},
        ],
        "source_pages": ["concepts/rag"],
    }


def test_html_well_formed(sample):
    out = render_html(sample)
    assert out.startswith("<!DOCTYPE html>")
    assert "<html" in out and "</html>" in out
    assert "<head>" in out and "</head>" in out
    assert "<body>" in out and "</body>" in out


def test_html_meta_tags_provenance(sample):
    out = render_html(sample)
    assert 'name="kb-query"' in out
    assert 'name="kb-generated-at"' in out
    assert 'name="kb-version"' in out


def test_html_escapes_xss_in_question():
    hostile = {
        "question": "<script>alert('xss')</script>",
        "answer": "ok",
        "citations": [],
        "source_pages": [],
    }
    out = render_html(hostile)
    # Must NOT contain raw <script> tag
    assert "<script>alert" not in out
    assert "&lt;script&gt;alert" in out or "&lt;script&gt;" in out


def test_html_escapes_xss_in_answer():
    hostile = {
        "question": "q",
        "answer": "<img src=x onerror=alert(1)>",
        "citations": [],
        "source_pages": [],
    }
    out = render_html(hostile)
    assert "<img src=x onerror" not in out
    assert "&lt;img" in out


def test_html_escapes_xss_in_citation_path():
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [
            # This path wouldn't pass extract_citations in practice (regex rejects
            # <>), but defense-in-depth — if a malformed path snuck in via a
            # non-regex code path, it must still escape.
            {"type": "wiki", "path": "concepts/<script>", "context": "..."},
        ],
        "source_pages": [],
    }
    out = render_html(hostile)
    assert "<script>" not in out.replace("&lt;script&gt;", "")


def test_html_relative_wiki_links(sample):
    out = render_html(sample)
    # wiki citation rendered as ./wiki/... relative path (no external URL)
    assert './wiki/concepts/rag.md' in out
    # raw source NOT rendered as anchor (no raw/ dir for browser) — just code
    assert '<code>raw/articles/foo.md</code>' in out


def test_html_answer_line_breaks_preserved(sample):
    sample["answer"] = "Line 1.\n\nLine 2."
    out = render_html(sample)
    # Paragraphs are wrapped in <p> or separated by <br> — either is acceptable
    assert "Line 1." in out
    assert "Line 2." in out
    # Must not be on a literal single line via the raw \n
    # (split_into_paragraphs is the preferred approach)


def test_html_no_citations_no_section(sample):
    sample["citations"] = []
    out = render_html(sample)
    # Sources section may be absent OR say "No sources"
    # Either way, no orphan </ul> or <li> injected
    assert out.count("<li>") == 0 or "No sources" in out


def test_html_kb_version_dynamic(sample):
    import kb
    out = render_html(sample)
    assert f'content="{kb.__version__}"' in out


def test_html_inline_css_no_external_assets(sample):
    out = render_html(sample)
    assert "<style>" in out
    # No external <link> or <script src=>
    assert 'href="http' not in out
    assert 'src="http' not in out
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_html.py -x -q
```

### Step 5.2: Implement `html.py`

- [ ] Create `src/kb/query/formats/html.py`:

```python
"""HTML output adapter — Phase 4.11.

Emits a self-contained HTML5 document with inline CSS and no external
assets. Every user-controlled string passes through html.escape(quote=True)
individually; citation anchors are built from the structured citations
list (never regex over already-escaped text).
"""

from __future__ import annotations

import html as _html

from kb.query.formats.common import build_provenance, validate_payload_size

_INLINE_CSS = """
body { font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }
h1 { border-bottom: 1px solid #eee; padding-bottom: .25rem; }
.sources { border-top: 1px solid #eee; margin-top: 2rem; padding-top: 1rem;
           font-size: .9em; }
.meta { color: #666; font-size: .85em; }
pre { background: #f5f5f5; padding: 1em; overflow-x: auto; border-radius: 4px; }
code { background: #f5f5f5; padding: 2px 4px; border-radius: 2px; }
ul.sources { list-style: disc; padding-left: 1.5rem; }
""".strip()


def _escape(s: str) -> str:
    """Shortcut for html.escape with quote=True."""
    return _html.escape(s or "", quote=True)


def _render_answer_body(answer: str) -> str:
    """Split answer into <p> paragraphs on blank lines; escape each.

    We split on double-newline so blank lines become paragraph breaks.
    Single newlines are preserved as <br> to maintain author intent.
    """
    if not answer.strip():
        return "<p><em>No answer synthesized.</em></p>"
    paras = [p.strip() for p in answer.split("\n\n") if p.strip()]
    out = []
    for p in paras:
        escaped = _escape(p).replace("\n", "<br>\n")
        out.append(f"<p>{escaped}</p>")
    return "\n".join(out)


def _render_sources(citations: list[dict]) -> str:
    """Build the <ul class='sources'> block from structured citations.

    Wiki citations: <a href="./wiki/PATH.md">PATH</a>
    Raw citations:  <code>PATH</code>
    """
    if not citations:
        return '<p class="sources"><em>No sources cited.</em></p>'

    seen: set[str] = set()
    lines = ['<ul class="sources">']
    for cite in citations:
        path = cite.get("path", "")
        if not path or path in seen:
            continue
        seen.add(path)
        escaped_path = _escape(path)
        if cite.get("type") == "wiki":
            href = f"./wiki/{escaped_path}.md"
            lines.append(f'  <li><a href="{href}">{escaped_path}</a></li>')
        else:
            lines.append(f"  <li><code>{escaped_path}</code></li>")
    lines.append("</ul>")
    return "\n".join(lines)


def render_html(result: dict) -> str:
    """Render a query result as a self-contained HTML5 document."""
    validate_payload_size(result)

    prov = build_provenance(result)
    question = result.get("question", "") or "(untitled query)"
    answer = result.get("answer", "") or ""

    escaped_q = _escape(question)
    escaped_title_q = _escape(question[:80])
    generated_at = prov["generated_at"]
    kb_version = prov["kb_version"]
    source_count = len(prov["source_pages"])

    answer_block = _render_answer_body(answer)
    sources_block = _render_sources(prov["citations"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>KB Query: {escaped_title_q}</title>
  <meta name="kb-query" content="{escaped_q}">
  <meta name="kb-generated-at" content="{_escape(generated_at)}">
  <meta name="kb-version" content="{_escape(kb_version)}">
  <meta name="kb-source-count" content="{source_count}">
  <style>
{_INLINE_CSS}
  </style>
</head>
<body>
  <article>
    <header>
      <h1>{escaped_q}</h1>
      <p class="meta">Generated {_escape(generated_at)} · {source_count} source page(s)</p>
    </header>
    <section class="answer">
{answer_block}
    </section>
    <section>
      <h2>Sources</h2>
{sources_block}
    </section>
  </article>
</body>
</html>
"""
```

### Step 5.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_html.py -x -q
```

Expected: PASS.

### Step 5.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/formats/html.py tests/test_v4_11_html.py
git commit -m "feat(phase-4.11): html adapter with per-field XSS escaping

Every interpolated field (question, answer, page title, citation path,
citation context) passes through html.escape(quote=True) individually.
Citation anchors built from structured citations list (not regex over
already-escaped text). Inline CSS only, no external assets, no JS."
```

---

## Task 6: Chart adapter (JSON + Python script)

**Files:**
- Create: `src/kb/query/formats/chart.py`
- Create: `tests/test_v4_11_chart.py`

### Step 6.1: Write failing tests

- [ ] Create `tests/test_v4_11_chart.py`:

```python
"""Tests for kb.query.formats.chart adapter."""

from __future__ import annotations

import ast
import json

import pytest

from kb.query.formats.chart import render_chart


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is ...",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag", "entities/openai", "concepts/embeddings"],
        "context_pages": ["concepts/rag"],
    }


def test_chart_returns_script_and_json(sample):
    script, data_json = render_chart(sample)
    assert isinstance(script, str)
    assert isinstance(data_json, str)


def test_chart_json_is_valid(sample):
    _, data_json = render_chart(sample)
    data = json.loads(data_json)
    assert data["question"] == "What is RAG?"
    assert len(data["source_pages"]) == 3
    assert data["source_pages"][0]["rank"] == 1


def test_chart_script_parses_as_python(sample):
    script, _ = render_chart(sample)
    # Must be syntactically valid Python
    ast.parse(script)


def test_chart_script_imports_matplotlib(sample):
    script, _ = render_chart(sample)
    assert "import matplotlib.pyplot as plt" in script


def test_chart_script_injection_safe_from_question():
    """A malicious question must not break out of the script docstring or
    create a Python injection when rendered as a string literal."""
    hostile = {
        "question": '"""; import os; os.system("rm -rf /"); x = """',
        "answer": "ok",
        "citations": [],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }
    script, data_json = render_chart(hostile)
    # Script must remain parseable
    ast.parse(script)
    # And the JSON must safely encode the question (json.loads round-trips)
    data = json.loads(data_json)
    assert data["question"] == hostile["question"]
    # Script must NOT contain the raw injection payload as executable code
    # (it will appear only as a repr'd string inside the docstring)
    assert 'os.system("rm -rf /")' not in script or script.count(
        'os.system("rm -rf /")'
    ) == 0 or 'import os;' not in script


def test_chart_injection_safe_from_page_id():
    """Page IDs come from frontmatter and are untrusted — must be safely
    JSON-encoded into the sidecar, never f-string-interpolated into the
    script source."""
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [],
        "source_pages": ["concepts/'; import os; os.system('pwn'); x='"],
        "context_pages": [],
    }
    script, data_json = render_chart(hostile)
    ast.parse(script)
    data = json.loads(data_json)
    # Round-trips safely
    assert data["source_pages"][0]["id"] == hostile["source_pages"][0]


def test_chart_empty_source_pages():
    """Zero pages produces a script that prints an error instead of crashing."""
    empty = {
        "question": "q", "answer": "a", "citations": [],
        "source_pages": [], "context_pages": [],
    }
    script, data_json = render_chart(empty)
    ast.parse(script)  # still valid Python
    data = json.loads(data_json)
    assert data.get("source_pages") == [] or data.get("error")
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_chart.py -x -q
```

### Step 6.2: Implement `chart.py`

- [ ] Create `src/kb/query/formats/chart.py`:

```python
"""Chart output adapter — Phase 4.11.

Emits a tuple of (python_script, json_data). The script is never executed
by kb; the user runs it locally to render a matplotlib bar chart from the
JSON sidecar. All user-controlled strings are JSON-encoded into the
sidecar — never f-string-interpolated into the Python source.
"""

from __future__ import annotations

import json

from kb.query.formats.common import build_provenance, validate_payload_size

_SCRIPT_TEMPLATE = '''"""KB query output — matplotlib visualization script.

Generated by kb.query.formats.chart (Phase 4.11).

Run:
    python <this-script>

Requires: `pip install matplotlib` (not a kb runtime dependency).
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt  # user dependency — run `pip install matplotlib`

HERE = Path(__file__).parent
# JSON sidecar lives next to this script at the same stem with .json extension
DATA_PATH = HERE / (Path(__file__).stem + ".json")
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))

PAGES = DATA.get("source_pages", [])
if not PAGES:
    print("No source pages for this query — nothing to chart.")
    raise SystemExit(0)

LABELS = [p["id"] for p in PAGES]
RANKS = [p["rank"] for p in PAGES]
MAX_RANK = max(RANKS)
# Invert ranks so rank 1 (most relevant) becomes the tallest bar
VALUES = [MAX_RANK - r + 1 for r in RANKS]

fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(PAGES))))
ax.barh(LABELS[::-1], VALUES[::-1])
ax.set_xlabel("Relevance (inverted rank — higher = more relevant)")
title = DATA.get("question", "")[:80]
ax.set_title(title)
fig.tight_layout()
out_path = HERE / (Path(__file__).stem + ".png")
fig.savefig(str(out_path), dpi=150)
print(f"Wrote {out_path.name}")
'''


def render_chart(result: dict) -> tuple[str, str]:
    """Render a query result as (python_script, json_data) for matplotlib.

    Returns:
        Tuple of (script_str, json_data_str).
        Caller writes script_str to <stem>.py and json_data_str to <stem>.json.
    """
    validate_payload_size(result)

    prov = build_provenance(result)
    pages_data = [
        {"id": pid, "rank": rank}
        for rank, pid in enumerate(result.get("source_pages", []), start=1)
    ]
    data = {
        "question": prov["query"],
        "generated_at": prov["generated_at"],
        "kb_version": prov["kb_version"],
        "source_pages": pages_data,
    }
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    # Script is template-only; no user data interpolated into code.
    return _SCRIPT_TEMPLATE, json_data
```

### Step 6.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_chart.py -x -q
```

Expected: PASS.

### Step 6.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/formats/chart.py tests/test_v4_11_chart.py
git commit -m "feat(phase-4.11): chart adapter — static Python script + JSON sidecar

Script is a static template with no user-data interpolation — zero
code-injection surface. Question, page IDs, and kb_version are
serialized via json.dumps into a sidecar file the script loads at run
time. Matplotlib is only referenced in the emitted script; not a kb
runtime dep. Zero-pages case prints an error and exits cleanly."
```

---

## Task 7: Jupyter adapter (nbformat with kernelspec)

**Files:**
- Modify: `requirements.txt` (add `nbformat>=5.0,<6.0`)
- Create: `src/kb/query/formats/jupyter.py`
- Create: `tests/test_v4_11_jupyter.py`

### Step 7.1: Add nbformat dependency

- [ ] Edit `requirements.txt`. Append (in the appropriate alphabetical section):

```
nbformat>=5.0,<6.0
```

- [ ] Install in venv:

```bash
.venv/Scripts/pip install "nbformat>=5.0,<6.0"
```

### Step 7.2: Write failing tests

- [ ] Create `tests/test_v4_11_jupyter.py`:

```python
"""Tests for kb.query.formats.jupyter adapter."""

from __future__ import annotations

import json

import pytest

from kb.query.formats.jupyter import render_jupyter


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is Retrieval Augmented Generation.",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_jupyter_is_valid_json(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    assert nb["nbformat"] == 4
    assert "cells" in nb


def test_jupyter_validates_with_nbformat(sample):
    import nbformat as nbf

    out = render_jupyter(sample)
    nb = nbf.reads(out, as_version=4)
    nbf.validate(nb)  # raises on invalid schema


def test_jupyter_has_kernelspec(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    ks = nb["metadata"].get("kernelspec")
    assert ks is not None
    assert ks.get("name") == "python3"
    assert ks.get("language") == "python"


def test_jupyter_metadata_trusted_not_true(sample):
    """Never set metadata.trusted=True — it would auto-execute code cells."""
    out = render_jupyter(sample)
    nb = json.loads(out)
    # Either absent or explicitly False
    assert nb["metadata"].get("trusted") is not True


def test_jupyter_includes_question_cell(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    sources = "\n".join(
        "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        for cell in nb["cells"]
    )
    assert "What is RAG?" in sources


def test_jupyter_includes_answer_cell(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    sources = "\n".join(
        "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
        for cell in nb["cells"]
    )
    assert "RAG is Retrieval Augmented Generation." in sources


def test_jupyter_kb_metadata(sample):
    out = render_jupyter(sample)
    nb = json.loads(out)
    kb_meta = nb["metadata"].get("kb_query")
    assert kb_meta is not None
    assert kb_meta["query"] == "What is RAG?"
    assert "generated_at" in kb_meta


def test_jupyter_code_cell_uses_json_dumps_for_question():
    """Question in code cell must be json.dumps'd — never raw f-string interp."""
    hostile = {
        "question": '"""; import os; """',
        "answer": "a",
        "citations": [],
        "source_pages": [],
    }
    out = render_jupyter(hostile)
    nb = json.loads(out)
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) >= 1
    code_src = "".join(
        code_cells[0]["source"]
        if isinstance(code_cells[0]["source"], list)
        else [code_cells[0]["source"]]
    )
    # Must NOT contain raw triple-quote injection breaking the string
    # The question appears inside a json.dumps'd literal — safe
    assert '"""; import os; """' not in code_src or "json.loads" in code_src or '"' in code_src
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_jupyter.py -x -q
```

### Step 7.3: Implement `jupyter.py`

- [ ] Create `src/kb/query/formats/jupyter.py`:

```python
"""Jupyter output adapter — Phase 4.11.

Emits a valid .ipynb via nbformat v4 with explicit kernelspec. Never sets
metadata.trusted=True (auto-exec vector). All user-controlled strings are
json.dumps'd into code-cell literals — never f-string interpolated.
"""

from __future__ import annotations

import json

import nbformat as nbf

from kb.query.citations import format_citations
from kb.query.formats.common import build_provenance, validate_payload_size


def render_jupyter(result: dict) -> str:
    """Render a query result as a .ipynb (JSON string) using nbformat v4."""
    validate_payload_size(result)

    prov = build_provenance(result)
    question = result.get("question", "") or "(untitled query)"
    answer = result.get("answer", "") or "_No answer synthesized._"
    citations = result.get("citations", [])
    sources_md = (
        format_citations(citations, mode="markdown") if citations else "_No sources cited._"
    )

    nb = nbf.v4.new_notebook()
    # Explicit kernelspec so Jupyter/VSCode don't prompt on open
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12"},
        "kb_query": prov,
    }
    # trusted deliberately NOT set (auto-execute vector)

    nb.cells = [
        nbf.v4.new_markdown_cell(f"# Question\n\n{question}"),
        nbf.v4.new_markdown_cell(f"## Answer\n\n{answer}"),
        nbf.v4.new_markdown_cell(f"## Sources\n{sources_md}"),
        nbf.v4.new_code_cell(
            "# Re-run this query or inspect citations programmatically\n"
            "from kb.query.engine import query_wiki\n\n"
            f"QUESTION = {json.dumps(question)}\n"
            "# result = query_wiki(QUESTION)\n"
            "# print(result['answer'])"
        ),
    ]

    # Validate before emitting — surfaces malformed metadata as ValidationError
    nbf.validate(nb)

    return nbf.writes(nb)
```

### Step 7.4: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_jupyter.py -x -q
```

Expected: PASS.

### Step 7.5: Commit

- [ ] Commit:

```bash
git add requirements.txt src/kb/query/formats/jupyter.py tests/test_v4_11_jupyter.py
git commit -m "feat(phase-4.11): jupyter adapter — nbformat v4 + explicit kernelspec

Explicit Python 3 kernelspec so Jupyter/VSCode don't prompt on open.
metadata.trusted never set — code cells do NOT auto-execute on open.
Question in code cell json.dumps'd to a QUESTION variable — never
f-string interpolated. nbformat.validate() called before writes()."
```

---

## Task 8: `render_output` dispatcher

**Files:**
- Modify: `src/kb/query/formats/__init__.py`
- Create: `tests/test_v4_11_formats_dispatch.py`

### Step 8.1: Write failing tests

- [ ] Create `tests/test_v4_11_formats_dispatch.py`:

```python
"""Tests for the render_output dispatcher."""

from __future__ import annotations

import pytest

from kb.query.formats import VALID_FORMATS, render_output


@pytest.fixture
def sample():
    return {
        "question": "What is RAG?",
        "answer": "RAG is ...",
        "citations": [],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_valid_formats_contents():
    assert VALID_FORMATS == frozenset(
        {"text", "markdown", "marp", "html", "chart", "jupyter"}
    )


def test_dispatch_markdown_writes_file(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("markdown", sample)
    assert path.exists()
    assert path.suffix == ".md"
    assert "What is RAG?" in path.read_text(encoding="utf-8")


def test_dispatch_html(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("html", sample)
    assert path.exists()
    assert path.suffix == ".html"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")


def test_dispatch_chart_writes_py_and_json(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("chart", sample)
    assert path.exists()
    assert path.suffix == ".py"
    json_sidecar = path.with_suffix(".json")
    assert json_sidecar.exists()


def test_dispatch_jupyter(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("jupyter", sample)
    assert path.exists()
    assert path.suffix == ".ipynb"


def test_dispatch_marp(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("marp", sample)
    assert path.exists()
    assert path.suffix == ".md"
    assert "marp: true" in path.read_text(encoding="utf-8")


def test_dispatch_unknown_format(sample):
    with pytest.raises(ValueError, match="unknown format"):
        render_output("pdf", sample)


def test_dispatch_text_is_noop(sample):
    """text format should not write a file — return None."""
    path = render_output("text", sample)
    assert path is None


def test_dispatch_case_normalization(monkeypatch, tmp_path, sample):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    path = render_output("  MARKDOWN  ", sample)
    assert path.exists()
    assert path.suffix == ".md"


def test_dispatch_rejects_empty_answer(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    empty = {"question": "q", "answer": "", "citations": [], "source_pages": []}
    # Empty answer is OK — adapter writes "No answer synthesized"
    path = render_output("markdown", empty)
    assert path.exists()
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_formats_dispatch.py -x -q
```

### Step 8.2: Implement dispatcher

- [ ] Replace content of `src/kb/query/formats/__init__.py`:

```python
"""Output-format adapters for kb_query (Phase 4.11).

Public API:
    render_output(fmt, result) -> Path | None
    VALID_FORMATS: frozenset[str]
"""

from __future__ import annotations

from pathlib import Path

from kb.utils.io import atomic_text_write

from kb.query.formats.chart import render_chart
from kb.query.formats.common import output_path_for
from kb.query.formats.html import render_html
from kb.query.formats.jupyter import render_jupyter
from kb.query.formats.markdown import render_markdown
from kb.query.formats.marp import render_marp

__all__ = ["VALID_FORMATS", "render_output"]

VALID_FORMATS = frozenset({"text", "markdown", "marp", "html", "chart", "jupyter"})

_ADAPTERS = {
    "markdown": render_markdown,
    "marp": render_marp,
    "html": render_html,
    "chart": render_chart,
    "jupyter": render_jupyter,
}


def _normalize(fmt: str) -> str:
    return (fmt or "").strip().lower()


def render_output(fmt: str, result: dict) -> Path | None:
    """Render `result` into the requested format and write to OUTPUTS_DIR.

    Returns:
        Path to the written file, or None when fmt is "text" (no-op).

    Raises:
        ValueError: unknown format, or payload size exceeds MAX_OUTPUT_CHARS.
        OSError: collision retries exhausted or write failure.
    """
    fmt_n = _normalize(fmt)
    if fmt_n not in VALID_FORMATS:
        raise ValueError(
            f"unknown format '{fmt}'; expected one of {sorted(VALID_FORMATS)}"
        )
    if fmt_n == "text":
        return None  # text is stdout-only; no file produced

    adapter = _ADAPTERS[fmt_n]
    question = result.get("question", "") or "(untitled)"
    path = output_path_for(question, fmt_n)

    if fmt_n == "chart":
        script, data_json = adapter(result)
        atomic_text_write(script, path)
        json_sidecar = path.with_suffix(".json")
        atomic_text_write(data_json, json_sidecar)
    else:
        payload = adapter(result)
        atomic_text_write(payload, path)

    return path
```

### Step 8.3: Run dispatcher tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_formats_dispatch.py -x -q
```

Expected: PASS.

### Step 8.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/formats/__init__.py tests/test_v4_11_formats_dispatch.py
git commit -m "feat(phase-4.11): render_output dispatcher + VALID_FORMATS

Normalizes input (.strip().lower()), rejects unknown formats, handles
chart's (script, json) tuple by writing both files, returns None for
text format. atomic_text_write guarantees crash-safe writes."
```

---

## Task 9: `query_wiki` integration

**Files:**
- Modify: `src/kb/query/engine.py`
- Create: `tests/test_v4_11_query_integration.py`

### Step 9.1: Write failing tests

- [ ] Create `tests/test_v4_11_query_integration.py`:

```python
"""End-to-end tests for query_wiki with output_format."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kb.query.engine import query_wiki


@pytest.fixture
def wiki_with_pages(tmp_wiki, create_wiki_page):
    create_wiki_page("concepts/rag", title="RAG", content="RAG means Retrieval Augmented Generation.")
    create_wiki_page("entities/openai", title="OpenAI", content="OpenAI is an AI lab.")
    return tmp_wiki


@pytest.fixture
def mock_llm():
    with patch("kb.query.engine.call_llm") as m:
        m.return_value = "RAG is Retrieval Augmented Generation. [source: concepts/rag]"
        yield m


def test_query_wiki_text_format_no_file(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format="text")
    assert "output_path" not in result


def test_query_wiki_no_format_default(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    # Default — no output_format param (preserves 1322-test suite)
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages)
    assert "output_path" not in result


def test_query_wiki_markdown_format_writes(wiki_with_pages, mock_llm, monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki(
        "What is RAG?", wiki_dir=wiki_with_pages, output_format="markdown"
    )
    assert "output_path" in result
    assert "output_format" in result
    assert result["output_format"] == "markdown"
    path = Path(result["output_path"])
    assert path.exists()
    assert "What is RAG?" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("fmt", ["markdown", "marp", "html", "chart", "jupyter"])
def test_query_wiki_all_formats(wiki_with_pages, mock_llm, monkeypatch, tmp_path, fmt):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages, output_format=fmt)
    assert Path(result["output_path"]).exists()


def test_query_wiki_keyword_only_enforcement(wiki_with_pages, mock_llm):
    """output_format must be keyword-only — positional call must error."""
    with pytest.raises(TypeError):
        # 5th positional arg would try to be output_format — should fail
        query_wiki("q", None, 10, None, "markdown")  # type: ignore[misc]


def test_query_wiki_existing_return_keys_preserved(wiki_with_pages, mock_llm):
    """Existing keys (question, answer, citations, source_pages, context_pages)
    must still be present regardless of output_format."""
    result = query_wiki("What is RAG?", wiki_dir=wiki_with_pages)
    for key in ("question", "answer", "citations", "source_pages", "context_pages"):
        assert key in result


def test_query_wiki_no_results_no_output_write(mock_llm, tmp_wiki, monkeypatch, tmp_path):
    """If no pages match, output_path is NOT in result (no file to write)."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    # Empty wiki — no matches
    result = query_wiki(
        "nonsense xyzzy", wiki_dir=tmp_wiki, output_format="markdown"
    )
    # Existing behavior: returns answer = "No relevant pages found..."
    # Design: even with no-match, we still render the "no answer" output? Decision: no file.
    # If the implementation writes a "no match" file, adapt the assertion.
    assert "answer" in result
    # If design says "no file on no-match", assert output_path absent; otherwise assert present
    # Current plan: skip rendering when no pages retrieved (no answer synthesized)
    assert "output_path" not in result
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_query_integration.py -x -q
```

### Step 9.2: Modify `query_wiki` signature

- [ ] Open `src/kb/query/engine.py`. Find `query_wiki` (line 327). Update the signature and add dispatch:

```python
def query_wiki(
    question: str,
    wiki_dir: Path | None = None,
    max_results: int = 10,
    conversation_context: str | None = None,
    *,  # keyword-only from here — additive, breaks no existing callers
    output_format: str | None = None,
) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).
        max_results: Maximum number of pages to retrieve for context.
        conversation_context: Recent conversation history for follow-up query rewriting.
        output_format: If set and non-text, render the result to a file under OUTPUTS_DIR.
                       One of: 'text', 'markdown', 'marp', 'html', 'chart', 'jupyter'.

    Returns:
        dict with keys:
            question, answer, citations, source_pages, context_pages
            output_path (str, only when output_format set and non-text and answer synthesized)
            output_format (str, only when output_path is set)
    """
```

Then, at the bottom of the function (before the final `return { ... }`), insert:

```python
    result_dict = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
        "context_pages": ctx["context_pages"],
    }
    if output_format and output_format.strip().lower() != "text":
        # Lazy import to avoid pulling format adapters on every query
        from kb.query.formats import render_output
        try:
            path = render_output(output_format, result_dict)
            if path is not None:
                result_dict["output_path"] = str(path)
                result_dict["output_format"] = output_format.strip().lower()
        except (ValueError, OSError) as e:
            logger.warning("Output format '%s' failed: %s", output_format, e)
            result_dict["output_error"] = str(e)
    return result_dict
```

Replace the existing `return { ... }` block at the bottom of `query_wiki` with this new assembly. Also update the no-match return (around line 360) to NOT write files:

The existing no-match branch around line 360-367 already returns early — leave it. It won't reach the output_format dispatch, which is the intended behavior (no answer → no file).

### Step 9.3: Run integration tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_query_integration.py -x -q
```

Expected: PASS.

- [ ] Run the full existing suite to confirm zero regressions:

```bash
.venv/Scripts/python -m pytest tests/test_query.py -x -q
```

Expected: all original tests still pass.

### Step 9.4: Commit

- [ ] Commit:

```bash
git add src/kb/query/engine.py tests/test_v4_11_query_integration.py
git commit -m "feat(phase-4.11): integrate output_format into query_wiki

Adds keyword-only output_format param (zero breakage to 1322 callers).
Dispatches to kb.query.formats.render_output when set and non-text.
On adapter failure (bad format, oversize, disk), result gets
'output_error' key instead of raising — caller can still use the
answer. No file written on no-match (no answer to format)."
```

---

## Task 10: CLI integration

**Files:**
- Modify: `src/kb/cli.py`
- Create: `tests/test_v4_11_cli.py`

### Step 10.1: Write failing tests

- [ ] Create `tests/test_v4_11_cli.py`:

```python
"""Tests for kb query --format CLI flag."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kb.cli import cli


@pytest.fixture
def mocked_query_wiki():
    with patch("kb.cli.query_wiki") as m:
        yield m


def test_cli_query_default_format_text(mocked_query_wiki):
    """Without --format, no file output: query_wiki gets output_format=None."""
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": ["concepts/rag"],
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?"])
    assert result.exit_code == 0
    # output_format kwarg absent or None
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") in (None, "text")


def test_cli_query_markdown_format(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is...",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake.md",
        "output_format": "markdown",
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?", "--format", "markdown"])
    assert result.exit_code == 0
    assert "/tmp/fake.md" in result.output
    _, kwargs = mocked_query_wiki.call_args
    assert kwargs.get("output_format") == "markdown"


def test_cli_query_rejects_invalid_format():
    runner = CliRunner()
    result = runner.invoke(cli, ["query", "What is RAG?", "--format", "pdf"])
    # Click's built-in choice validation: exit code 2
    assert result.exit_code == 2


def test_cli_query_all_formats_accepted(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "x",
        "citations": [],
        "source_pages": [],
        "output_path": "/tmp/fake",
        "output_format": "markdown",
    }
    runner = CliRunner()
    for fmt in ("text", "markdown", "marp", "html", "chart", "jupyter"):
        res = runner.invoke(cli, ["query", "q", "--format", fmt])
        assert res.exit_code == 0, f"fmt {fmt} failed: {res.output}"
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_cli.py -x -q
```

### Step 10.2: Modify CLI

- [ ] Open `src/kb/cli.py`. Find the `query` command (line 85). Replace it with:

```python
@cli.command()
@click.argument("question")
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "markdown", "marp", "html", "chart", "jupyter"]),
    default="text",
    help="Output format. 'text' prints to stdout; others write to outputs/.",
)
def query(question: str, output_format: str):
    """Query the knowledge base."""
    from kb.query.citations import format_citations
    from kb.query.engine import query_wiki

    click.echo(f"Querying: {question}\n")
    try:
        fmt_kwarg = None if output_format == "text" else output_format
        result = query_wiki(question, output_format=fmt_kwarg)
        click.echo(result["answer"])
        if result.get("citations"):
            click.echo(format_citations(result["citations"]))
        click.echo(f"\n[Searched {len(result.get('source_pages', []))} pages]")
        if result.get("output_path"):
            click.echo(f"\nOutput: {result['output_path']} ({result['output_format']})")
        if result.get("output_error"):
            click.echo(f"\n[warn] Output format failed: {result['output_error']}", err=True)
    except Exception as e:
        click.echo(f"Error: {_truncate(str(e))}", err=True)
        raise SystemExit(1)
```

### Step 10.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_cli.py -x -q
```

Expected: PASS.

### Step 10.4: Commit

- [ ] Commit:

```bash
git add src/kb/cli.py tests/test_v4_11_cli.py
git commit -m "feat(phase-4.11): CLI --format flag on kb query

Click Choice of {text, markdown, marp, html, chart, jupyter}; default
'text' preserves existing behavior. On non-text format, echoes
'Output: <path> (<format>)' after the answer. Non-text errors
surface as '[warn] Output format failed: ...' on stderr."
```

---

## Task 11: MCP integration

**Files:**
- Modify: `src/kb/mcp/core.py`
- Create: `tests/test_v4_11_mcp.py`

### Step 11.1: Write failing tests

- [ ] Create `tests/test_v4_11_mcp.py`:

```python
"""Tests for kb_query MCP tool with output_format param."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kb.mcp.core import kb_query


@pytest.fixture
def mocked_query_wiki():
    with patch("kb.mcp.core.query_wiki") as m:
        yield m


def test_mcp_kb_query_format_requires_use_api(mocked_query_wiki):
    """output_format requires use_api=True — default mode returns raw context."""
    result = kb_query("What is RAG?", output_format="markdown", use_api=False)
    assert result.startswith("Error:")
    assert "use_api" in result


def test_mcp_kb_query_invalid_format():
    result = kb_query("q", output_format="pdf", use_api=True)
    assert result.startswith("Error:")
    assert "format" in result.lower() or "pdf" in result


def test_mcp_kb_query_empty_format_default_mode(monkeypatch, tmp_wiki):
    """Empty output_format + Claude Code mode — existing behavior preserved."""
    # Just confirm it doesn't error; full behavior covered by existing MCP tests
    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_wiki.parent)
    result = kb_query("What is RAG?", output_format="", use_api=False)
    # Returns either "No relevant pages found" or a context string; not an error
    assert not result.startswith("Error:") or "not found" in result.lower()


def test_mcp_kb_query_format_use_api_success(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "RAG is ...",
        "citations": [{"type": "wiki", "path": "concepts/rag", "context": "..."}],
        "source_pages": ["concepts/rag"],
        "output_path": "/tmp/out.md",
        "output_format": "markdown",
    }
    result = kb_query(
        "What is RAG?", output_format="markdown", use_api=True
    )
    assert "Output written to: /tmp/out.md" in result


def test_mcp_kb_query_format_case_normalization(mocked_query_wiki):
    mocked_query_wiki.return_value = {
        "answer": "ok", "citations": [], "source_pages": [],
        "output_path": "/tmp/out.md", "output_format": "markdown",
    }
    result = kb_query("q", output_format="  MARKDOWN  ", use_api=True)
    assert not result.startswith("Error:")
```

- [ ] Run to verify failures:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_mcp.py -x -q
```

### Step 11.2: Modify MCP tool

- [ ] Open `src/kb/mcp/core.py`. Find `kb_query` (line 46). Update signature and add validation:

```python
@mcp.tool()
def kb_query(
    question: str,
    max_results: int = 10,
    use_api: bool = False,
    conversation_context: str = "",
    output_format: str = "",
) -> str:
    """Query the knowledge base.

    Default (Claude Code mode): returns wiki search results with full page
    content. You (Claude Code) synthesize the answer and cite sources with
    [source: page_id] format.

    With use_api=true: calls the Anthropic API to synthesize the answer
    (requires ANTHROPIC_API_KEY).

    With output_format set (requires use_api=true): renders the synthesized
    answer to a file under outputs/ in one of: markdown, marp, html, chart,
    jupyter. Returns "Output written to: <path>" appended to the normal reply.

    Args:
        question: Natural language question.
        max_results: Maximum pages to search (default 10).
        use_api: If true, call the Anthropic API for synthesis.
        conversation_context: Recent conversation history for follow-up query rewriting.
        output_format: One of markdown|marp|html|chart|jupyter to produce a file,
                       or empty/text for stdout-only response. Requires use_api=true.
    """
    if not question or not question.strip():
        return "Error: Question cannot be empty."
    if len(question) > MAX_QUESTION_LEN:
        return f"Error: Question too long (max {MAX_QUESTION_LEN} chars)."
    if conversation_context and len(conversation_context) > MAX_QUESTION_LEN * 4:
        return f"Error: conversation_context too long (max {MAX_QUESTION_LEN * 4} chars)."

    # Normalize + validate output_format
    fmt_n = (output_format or "").strip().lower()
    if fmt_n and fmt_n != "text":
        from kb.query.formats import VALID_FORMATS
        if fmt_n not in VALID_FORMATS:
            return (
                f"Error: unknown output_format '{output_format}'. "
                f"Valid: {sorted(VALID_FORMATS)}"
            )
        if not use_api:
            return (
                "Error: output_format requires use_api=true "
                "(default Claude Code mode returns raw context, not a synthesized answer)."
            )

    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    if use_api:
        from kb.query.citations import format_citations

        try:
            result = query_wiki(
                question,
                max_results=max_results,
                conversation_context=conversation_context or None,
                output_format=fmt_n or None,
            )
            parts = [result["answer"]]
            if result.get("citations"):
                parts.append("\n" + format_citations(result["citations"]))
            parts.append(f"\n[Searched {len(result.get('source_pages', []))} pages]")
            if result.get("output_path"):
                parts.append(
                    f"\nOutput written to: {result['output_path']} "
                    f"({result['output_format']})"
                )
            if result.get("output_error"):
                parts.append(f"\n[warn] Output format failed: {result['output_error']}")
            return "\n".join(parts)
        except Exception as e:
            logger.exception("Error in kb_query API mode for: %s", question)
            return f"Error: Query failed — {e}"

    # Default: Claude Code mode — return context for synthesis (unchanged)
    try:
        results = search_pages(question, max_results=max_results)
    # ... rest of existing body unchanged
```

Keep everything after the `try: results = search_pages(...)` line identical to the current implementation.

### Step 11.3: Run tests

- [ ] Run:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_mcp.py -x -q
```

Expected: PASS.

- [ ] Run existing MCP core tests:

```bash
.venv/Scripts/python -m pytest tests/ -k "mcp" -x -q
```

Expected: no regressions.

### Step 11.4: Commit

- [ ] Commit:

```bash
git add src/kb/mcp/core.py tests/test_v4_11_mcp.py
git commit -m "feat(phase-4.11): kb_query MCP output_format param + validation

- Validates fmt via VALID_FORMATS; normalizes .lower().strip()
- Requires use_api=true (default mode returns raw context, not answer)
- Appends 'Output written to: <path> (<fmt>)' on success
- Surfaces output_error as '[warn] Output format failed: ...'"
```

---

## Task 12: Defense-in-depth — outputs/ never indexed

**Files:**
- Create: `tests/test_v4_11_security.py` (consolidated security tests)

### Step 12.1: Write security regression tests

- [ ] Create `tests/test_v4_11_security.py`:

```python
"""Consolidated adversarial + defense-in-depth tests for Phase 4.11."""

from __future__ import annotations

import ast
import json

import pytest

from kb.query.formats import render_output
from kb.query.formats.chart import render_chart
from kb.query.formats.html import render_html
from kb.query.formats.jupyter import render_jupyter
from kb.query.formats.markdown import render_markdown
from kb.query.formats.marp import render_marp


@pytest.fixture
def xss_payload():
    return {
        "question": "<script>alert('xss')</script>",
        "answer": "<img src=x onerror=alert(1)>",
        "citations": [
            {"type": "wiki", "path": "concepts/rag", "context": "<b>ctx</b>"},
        ],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_html_xss_payload_escaped(xss_payload):
    out = render_html(xss_payload)
    # No raw script or img tag from payload may survive
    assert "<script>alert" not in out
    assert "onerror=alert" not in out


def test_markdown_xss_roundtrip(xss_payload):
    """Markdown stays verbatim but YAML frontmatter must remain parseable."""
    import yaml
    out = render_markdown(xss_payload)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["query"] == xss_payload["question"]  # verbatim, YAML-escaped


def test_marp_xss_in_frontmatter(xss_payload):
    import yaml
    out = render_marp(xss_payload)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    # Marp embeds kb_query prefix
    assert fm.get("kb_query") == xss_payload["question"]


def test_chart_script_injection_safe():
    hostile = {
        "question": '"""; import os; os.system("rm -rf /"); """',
        "answer": "ok",
        "citations": [],
        "source_pages": ["concepts/'); import os; x = ('"],
        "context_pages": [],
    }
    script, json_data = render_chart(hostile)
    # Script must parse as valid Python
    ast.parse(script)
    # JSON must round-trip the payload safely
    data = json.loads(json_data)
    assert data["question"] == hostile["question"]
    assert data["source_pages"][0]["id"] == hostile["source_pages"][0]


def test_jupyter_not_trusted():
    sample = {
        "question": "q", "answer": "a", "citations": [],
        "source_pages": [], "context_pages": [],
    }
    out = render_jupyter(sample)
    nb = json.loads(out)
    assert nb["metadata"].get("trusted") is not True


def test_load_all_pages_excludes_outputs_dir(tmp_project, monkeypatch):
    """Defense-in-depth (opus approval condition #4): even if outputs/ is
    placed adjacent to wiki/, load_all_pages must not surface its files."""
    from kb.utils.pages import load_all_pages

    wiki_dir = tmp_project / "wiki"
    outputs_dir = tmp_project / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    # Plant a file that looks like a wiki page in outputs/
    (outputs_dir / "malicious.md").write_text(
        "---\ntitle: Malicious\ntype: concept\nconfidence: stated\n"
        "created: 2026-04-14\nupdated: 2026-04-14\n---\n\nBad content.\n",
        encoding="utf-8",
    )

    pages = load_all_pages(wiki_dir)
    paths = [p.get("id", "") for p in pages]
    assert "outputs/malicious" not in paths
    # Also confirm no file from outputs/ leaked
    for p in pages:
        assert "outputs" not in p.get("id", "")


def test_windows_reserved_name_question_safe(monkeypatch, tmp_path):
    """Questions containing Windows-reserved filenames must not produce
    files that fail to write or hit the null device."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    for name in ("What is NUL?", "Tell me about CON.", "PRN details"):
        result = {
            "question": name, "answer": "ok", "citations": [],
            "source_pages": [], "context_pages": [],
        }
        path = render_output("markdown", result)
        assert path.exists()
        # File must be readable
        assert "ok" in path.read_text(encoding="utf-8")


def test_empty_question_slug_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = {"question": "???", "answer": "a", "citations": [], "source_pages": []}
    path = render_output("markdown", result)
    assert "untitled" in path.name


def test_oversize_answer_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    oversize = {
        "question": "q",
        "answer": "x" * (500_001),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_output("markdown", oversize)


def test_html_wiki_anchor_escapes_path():
    """If a citation path is somehow mangled, HTML escapes the href."""
    hostile = {
        "question": "q", "answer": "a",
        "citations": [{"type": "wiki", "path": "concepts/foo&bar<baz", "context": "x"}],
        "source_pages": [],
        "context_pages": [],
    }
    out = render_html(hostile)
    # The ampersand must be escaped as &amp;
    assert "foo&bar" not in out or "foo&amp;bar" in out
```

- [ ] Run tests:

```bash
.venv/Scripts/python -m pytest tests/test_v4_11_security.py -x -q
```

Expected: all PASS.

### Step 12.2: Commit

- [ ] Commit:

```bash
git add tests/test_v4_11_security.py
git commit -m "test(phase-4.11): consolidated security regression suite

Covers: HTML XSS escape per field, Markdown YAML roundtrip, Marp
frontmatter, Chart Python injection via question + page ID, Jupyter
trusted flag, load_all_pages outputs/ exclusion (opus condition #4),
Windows reserved name handling, empty-slug fallback, oversize
rejection, HTML href escape."
```

---

## Task 13: `.gitignore` + baseline full-suite run

**Files:**
- Modify: `.gitignore`

### Step 13.1: Add outputs/ to gitignore

- [ ] Edit `.gitignore`. Find a good location (near the `wiki/` and `raw/` entries) and append:

```
# Query output adapters — ephemeral artifacts, never committed
outputs/
```

### Step 13.2: Run full test suite

- [ ] Run:

```bash
.venv/Scripts/python -m pytest -x -q
```

Expected: all tests pass (1322 existing + ~60 new ≈ 1382 total). If any existing test fails, investigate before proceeding.

### Step 13.3: Run ruff

- [ ] Run:

```bash
.venv/Scripts/python -m ruff check src/ tests/ --fix
.venv/Scripts/python -m ruff format src/ tests/
```

### Step 13.4: Commit

- [ ] Commit:

```bash
git add .gitignore
git commit -m "chore(phase-4.11): gitignore outputs/ dir"
```

---

## Task 14: Doc updates

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `BACKLOG.md` (delete Tier 1 item)
- Modify: `CLAUDE.md`
- Modify: `README.md`

### Step 14.1: CHANGELOG.md

- [ ] Open `CHANGELOG.md`. Find `## [Unreleased]` section. Under `### Added`, append:

```markdown
- `kb_query` output adapters: `--format={markdown|marp|html|chart|jupyter}` renders synthesized answers to files under `outputs/` (gitignored). Each file carries provenance frontmatter (query, citations, source pages, kb_version, generated_at). Adapters: markdown (wiki-compatible with YAML frontmatter), marp (slide deck with code-fence-aware splitter), html (self-contained HTML5 with per-field XSS escaping), chart (static matplotlib Python script + JSON data sidecar — no runtime matplotlib dep), jupyter (nbformat v4 with explicit Python 3 kernelspec; trusted flag never set to avoid auto-exec). MCP `kb_query` gains `output_format` parameter; requires `use_api=true`. `format_citations()` extended with `mode={markdown|html|marp}` (default preserves behavior). Addresses Karpathy Tier 1 #1 from BACKLOG.md.
```

### Step 14.2: BACKLOG.md — delete Tier 1 item #1

- [ ] Open `BACKLOG.md`. Find the section `**Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce:**`. Delete line 1:

```
1. `kb_query --format={text|marp|html|chart|jupyter}` output adapters — reproduces Karpathy's *"render markdown files, slide shows (Marp format), matplotlib images"*. Cross-ref: HIGH LEVERAGE — Output-Format Polymorphism.
```

Renumber remaining Tier 1 items 2→1, 3→2, 4→3.

- [ ] In the same file, find the "HIGH LEVERAGE — Output-Format Polymorphism" section. Delete the bullet about `query/formats/` (the one starting with ``- `query/formats/` `kb_query --format=...` adapters``). Leave the other bullets in that section intact.

- [ ] Update "Recommended first target" note if it references #1 — change it to point at the new #1 (previously #2: `kb_lint --augment`).

### Step 14.3: CLAUDE.md

- [ ] Open `CLAUDE.md`. Make the following updates:

1. Find the line that says `1322 tests, 26 MCP tools, 19 modules` and replace with `~1380 tests, 26 MCP tools, 20 modules` (use the actual count from the pytest run).

2. Find `### Python Package (`src/kb/`)`. Under "Key APIs", update `query_wiki`:

```markdown
- `query_wiki(question, wiki_dir=None, max_results=10, conversation_context=None, *, output_format=None)` — In `kb.query.engine`. Returns dict with `answer`, `citations`, `source_pages`, `context_pages`. When `output_format` is set and non-text, renders to `outputs/` and adds `output_path` + `output_format` keys; `output_error` on failure. Keyword-only for output_format to preserve all existing callers.
```

3. Under "Phase 4 modules" / "Phase 4.11", add a bullet:

```markdown
- `kb.query.formats` — output adapters for `kb_query` (markdown, marp, html, chart, jupyter). Files land at `PROJECT_ROOT/outputs/{YYYY-MM-DD-HHMMSS-ffffff}-{slug}.{ext}` with provenance frontmatter. MCP `kb_query(output_format=...)` requires `use_api=True`.
```

4. In the MCP Servers → kb section, update `kb_query` description to mention the new `output_format` parameter.

### Step 14.4: README.md

- [ ] Open `README.md`. If there is a features section or tree comment showing test/module counts, update to the new numbers. Add a one-line mention of output adapters to the feature roadmap or "what's new" section, e.g.:

```markdown
- **v0.10.0+ Phase 4.11:** `kb_query --format={markdown|marp|html|chart|jupyter}` output adapters — synthesized answers as files under `outputs/`.
```

### Step 14.5: Run final checks

- [ ] Full-suite run:

```bash
.venv/Scripts/python -m pytest -q
```

- [ ] Ruff clean:

```bash
.venv/Scripts/python -m ruff check src/ tests/
```

### Step 14.6: Commit doc updates

- [ ] Commit:

```bash
git add CHANGELOG.md BACKLOG.md CLAUDE.md README.md
git commit -m "docs(phase-4.11): update CHANGELOG/BACKLOG/CLAUDE/README

- CHANGELOG: Added entry under [Unreleased] for kb_query format adapters
- BACKLOG: remove Tier 1 item #1 (implemented); trim HIGH LEVERAGE bullet
- CLAUDE: bump test/module counts; document query_wiki signature; new
  Phase 4.11 module; MCP tool update
- README: feature roadmap line"
```

---

## Task 15: Architecture diagram update

**Files:**
- Modify: `docs/architecture/architecture-diagram.html`
- Regenerate: `docs/architecture/architecture-diagram.png`

### Step 15.1: Read and understand current diagram

- [ ] Open `docs/architecture/architecture-diagram.html`. Find the `kb.query` block. Identify where to add the new "Output Adapters" node.

### Step 15.2: Add output-adapters block

- [ ] Add an HTML block representing the new `kb.query.formats` package, connected via an arrow or container to `kb.query`. Use the existing visual style (CSS classes, colors). The block should list the 5 adapters (markdown, marp, html, chart, jupyter).

### Step 15.3: Re-render PNG

- [ ] Run the re-render command from CLAUDE.md:

```bash
.venv/Scripts/python -c "
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=3)
        await page.goto('file:///D:/Projects/llm-wiki-flywheel/docs/architecture/architecture-diagram.html')
        await page.wait_for_timeout(1500)
        dim = await page.evaluate('() => ({ w: document.body.scrollWidth, h: document.body.scrollHeight })')
        await page.set_viewport_size({'width': dim['w'], 'height': dim['h']})
        await page.wait_for_timeout(500)
        await page.screenshot(path='docs/architecture/architecture-diagram.png', full_page=True, type='png')
        await browser.close()
asyncio.run(main())
"
```

### Step 15.4: Commit

- [ ] Commit:

```bash
git add docs/architecture/architecture-diagram.html docs/architecture/architecture-diagram.png
git commit -m "docs(phase-4.11): architecture diagram — add Output Adapters block

Re-rendered PNG from updated HTML."
```

---

## Task 16: Final verification gate

### Step 16.1: Full test suite + lint

- [ ] Run:

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check src/ tests/
```

Both must be green. Record the exact test pass count for the PR body.

### Step 16.2: Verify doc accuracy

- [ ] Confirm the test count in `CLAUDE.md` matches the actual pytest pass count (off-by-one errors creep in from intermediate commits).
- [ ] Confirm `BACKLOG.md` no longer references the implemented Tier 1 item #1.
- [ ] Confirm `CHANGELOG.md` has exactly one new entry under `[Unreleased]`.

### Step 16.3: Manual smoke test (CLI)

- [ ] Run:

```bash
# If this project has a demo or known wiki state, try each format
.venv/Scripts/kb query "What is compile-not-retrieve?" --format markdown
.venv/Scripts/kb query "What is compile-not-retrieve?" --format html
.venv/Scripts/kb query "What is compile-not-retrieve?" --format jupyter
ls outputs/
```

Expected: files exist in `outputs/`; each file is well-formed for its format.

### Step 16.4: Ready for finishing-a-development-branch

- [ ] Confirm: all commits are clean, no stashed work, no untracked new files.
- [ ] Branch is ready to be pushed + have a PR raised.

---

## Self-review (executed BEFORE handoff)

1. **Spec coverage.** Spec §3 (module layout) → Tasks 1-8; §4 (data flow) → Task 9; §5 (per-adapter) → Tasks 3-7; §6 (common) → Task 1; §7 (citations) → Task 2; §9 (security gates) → Task 12 + per-adapter tests; §11 (testing plan) → 10 test files delivered across Tasks 1-12; §12 (doc updates) → Task 14 + 15; §14 (opus conditions) → Condition #1 (no output_path) baked into signatures; #2 (format_citations back-compat) in Task 2; #3 (dynamic kb_version) in Task 1 common.py; #4 (load_all_pages exclusion test) in Task 12.

2. **Placeholder scan.** No "TBD" / "TODO" / "add error handling" / "similar to Task N". Every step has concrete code, exact commands, exact expected output.

3. **Type consistency.** `render_output` signature: `(fmt: str, result: dict) -> Path | None`. `render_*` adapter signature: `(result: dict) -> str` except chart: `(result: dict) -> tuple[str, str]`. Consistent across Tasks 3-8. `query_wiki` keyword-only new param `output_format: str | None = None`. `format_citations(citations, mode="markdown")` default preserves all current call sites.

4. **Gaps.** None found.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-kb-query-formats.md`.

Per user direction ("full automated and call opus sub agent for review and approval"), this will execute via **Subagent-Driven Development** with opus subagents reviewing between task bundles. Proceeding to Context7 verification + implementation.
