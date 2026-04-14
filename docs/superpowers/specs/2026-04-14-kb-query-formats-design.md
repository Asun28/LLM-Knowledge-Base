# Design: `kb_query --format={markdown|marp|html|chart|jupyter}` output adapters

**Date:** 2026-04-14
**Phase:** 4.11 — Output-Format Polymorphism (Karpathy Tier 1 #1)
**Leverage tier:** HIGH
**Effort estimate:** Medium (~900 LOC total — see §10 for the per-file breakdown)
**Source inspiration:** Karpathy's tweet (Apr 2, 2026): *"render markdown files, slide shows (Marp format), matplotlib images"*; Fabian Williams + JupyterBook replies.
**Baseline counts (verified 2026-04-14):** 1322 tests across 92 test files, 26 `@mcp.tool()` decorators (`browse=5, core=7, health=5, quality=9`), 19 `kb` modules. Spec increments: +~50 tests → ~1372, +6 test files → 98, +0 tools (param added to `kb_query`), +1 module (`kb.query.formats` package) → 20.

---

## 1. Overview

`kb_query --format={markdown|marp|html|chart|jupyter}` converts query answers into durable, provenance-tagged file artifacts. The adapters give the wiki system the same "output polymorphism" surface as the source inspiration: a synthesized answer can leave the session as a slide deck, a web page, a plot script, or an executable notebook instead of only terminal text. Files land under `outputs/` at project root (gitignored) with self-describing frontmatter linking back to the query, citations, and contributing pages.

**Scope — what ships:** five adapters (markdown / marp / html / chart / jupyter), integration into `query_wiki`, `kb.cli.query`, and `kb.mcp.core.kb_query`, default-only output path scheme, YAML/HTML/JSON/ipynb provenance headers, security gates for path traversal, HTML injection, Python code-injection in emitted scripts, and Jupyter auto-exec.

**Scope — what is deferred (see §13 YAGNI scope-outs):** custom `output_path` override, in-process PNG generation (matplotlib runtime dep), PDF/PPTX export, server-side Marp render, retention policy, `kb_lint` awareness.

---

## 2. Locked design decisions

Seven decisions were settled during the 3-round adversarial design eval (1 opus + 2 sonnet) and the final opus approval gate; they are load-bearing for the rest of this doc:

| # | Decision | Rationale |
|---|---|---|
| 1 | **Five adapters, not four** — markdown is added alongside marp/html/chart/jupyter | Karpathy's tweet names "markdown files" first. A plain markdown adapter is the base case that marp specializes; without it, saving an answer as a wiki-compatible page requires a marp sidestep. |
| 2 | **Outputs at `PROJECT_ROOT / "outputs/"`, NOT under `wiki/outputs/`** | `load_all_pages()` iterates wiki subdirs; any `wiki/outputs/` content would feed back into future query contexts — closed poisoning loop. Outputs are ephemeral artifacts, not curated knowledge. Gitignored. |
| 3 | **No `output_path` override day-one** | YAGNI. The default path scheme `outputs/{YYYY-MM-DD-HHMMSS-ffffff}-{slug}.{ext}` is deterministic and auditable. Removing the override eliminates the Windows drive-letter / symlink / allowlist attack surface entirely. |
| 4 | **`output_format` requires a synthesized answer** | `query_wiki` synthesizes an answer via `call_llm`; MCP default "Claude Code mode" returns raw wiki context for the host LLM. Adapters can't render what doesn't exist — so the MCP tool requires `use_api=True` when `output_format` is non-empty; CLI always synthesizes so no gate is needed. |
| 5 | **Chart = data JSON + runnable Python script, no in-process PNG** | Removes matplotlib runtime dep from the critical path, avoids MCP event-loop blocking on slow `savefig`, and eliminates an in-process image-generation attack surface. User runs the emitted script locally to render. |
| 6 | **Plain functions + dict dispatch, not Protocol/ABC** | Five stateless render functions need no protocol scaffolding. A `Protocol` buys type hints at the cost of ~100 LOC of plumbing. YAGNI until a 6th external adapter arrives. |
| 7 | **Keyword-only new params on `query_wiki`** | Adding `*, output_format=None` after existing positional params breaks zero existing call sites across the 1322-test suite. |

---

## 3. Module layout & public API

**New package:** `src/kb/query/formats/` (chose package over single file because the 5 adapters each own distinct escaping / serialization rules; each reads cleanly as its own file).

```
src/kb/query/formats/
  __init__.py        # ADAPTERS registry; public render_output(format, result) -> Path
  common.py          # helpers shared across adapters: safe_slug, output_path_for, build_provenance, MAX_OUTPUT_CHARS guard
  markdown.py        # render_markdown(result) -> str
  marp.py            # render_marp(result) -> str  (code-fence-aware slide splitter)
  html.py            # render_html(result) -> str
  chart.py           # render_chart(result) -> tuple[str, str]  (script, json_data)
  jupyter.py         # render_jupyter(result) -> str  (JSON-encoded ipynb)
```

**Public API — what other modules import:**

```python
# src/kb/query/formats/__init__.py
from pathlib import Path
from typing import Any

VALID_FORMATS = frozenset({"text", "markdown", "marp", "html", "chart", "jupyter"})

def render_output(output_format: str, result: dict[str, Any]) -> Path:
    """Render a query result to disk in the requested format.

    Args:
        output_format: one of VALID_FORMATS (case/whitespace normalized upstream).
        result: dict with keys 'question', 'answer', 'citations',
                'source_pages', 'context_pages' (as returned by query_wiki).

    Returns:
        Absolute path to the written file (or the .py file for 'chart'; the
        JSON sidecar is at the same stem with .json extension).

    Raises:
        ValueError: unknown format, empty question, answer exceeds MAX_OUTPUT_CHARS.
        OSError: write failed (disk, permissions).
    """
```

**Internal call order inside `render_output`:**

```
render_output(fmt, result)
├── _normalize_format(fmt)               # .lower().strip() + VALID_FORMATS check
├── _validate_result(result)             # answer non-empty + len(answer) ≤ MAX_OUTPUT_CHARS
├── path = output_path_for(result["question"], fmt)
│   ├── safe_slug(question)              # slugify + empty-fallback + Windows-reserved guard + length cap 80
│   ├── timestamp()                      # YYYY-MM-DD-HHMMSS-ffffff (microsecond)
│   └── collision retry (-2, -3, ...-9)  # atomic path-taken check + rename
├── adapter_fn = ADAPTERS[fmt]
├── payload = adapter_fn(result)         # str for md/marp/html/jupyter; (str, str) for chart
├── atomic_text_write(path, payload)     # for chart: atomic_text_write for .py + .json sibling
└── return path
```

**CLI integration:**

```python
# src/kb/cli.py
@cli.command()
@click.argument("question")
@click.option("--format", "output_format",
              type=click.Choice(["text", "markdown", "marp", "html", "chart", "jupyter"]),
              default="text",
              help="Output format. 'text' prints to stdout; others write to outputs/.")
def query(question: str, output_format: str):
    ...
    result = query_wiki(question, output_format=output_format if output_format != "text" else None)
    if result.get("output_path"):
        click.echo(f"Output: {result['output_path']}")
```

**MCP integration:**

```python
# src/kb/mcp/core.py  (inside kb_query)
@mcp.tool()
def kb_query(question: str, max_results: int = 10, use_api: bool = False,
             conversation_context: str = "", output_format: str = "") -> str:
    ...
    if output_format:
        if output_format not in VALID_FORMATS:
            return f"Error: unknown format '{output_format}'. Valid: {sorted(VALID_FORMATS)}"
        if not use_api:
            return ("Error: output_format requires use_api=true "
                    "(default Claude Code mode returns raw context, not a synthesized answer).")
        # then call query_wiki(..., output_format=output_format) and
        # append "Output written to: {path}" to the return string.
```

**`query_wiki` integration:**

```python
# src/kb/query/engine.py
def query_wiki(
    question: str,
    wiki_dir: Path | None = None,
    max_results: int = 10,
    conversation_context: str | None = None,
    *,  # keyword-only from here — additive, breaks no existing callers
    output_format: str | None = None,
) -> dict:
    ...  # existing body unchanged
    result = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
        "context_pages": ctx["context_pages"],
    }
    if output_format and output_format != "text":
        from kb.query.formats import render_output
        path = render_output(output_format, result)
        result["output_path"] = str(path)
        result["output_format"] = output_format
    return result
```

---

## 4. Data flow

1. User issues `kb query "Q" --format marp` (CLI) **or** MCP client calls `kb_query("Q", use_api=true, output_format="marp")`.
2. `query_wiki` runs its existing pipeline unchanged: search → hybrid/RRF → context build → `call_llm` → `extract_citations`.
3. Result dict is assembled. If `output_format` was set AND is not "text", `render_output(fmt, result)` dispatches to the adapter.
4. Adapter serializes the result and returns the payload (str for 4 of 5 adapters; the chart adapter returns `(py_source, json_data)`).
5. `_write_outputs` writes the payload atomically via `atomic_text_write`. For chart, writes both `.py` and `.json` sidecar.
6. Path is stamped into `result["output_path"]`, returned to caller.
7. CLI echoes `Output: <path>`; MCP appends `Output written to: <path>` to the tool return string.

---

## 5. Per-adapter specification

### 5.1 `markdown.py`

Emits a standalone markdown file with query provenance frontmatter and the answer body.

```markdown
---
type: query_output
format: markdown
query: "What is compile-not-retrieve?"
generated_at: 2026-04-14T15:30:22.123456Z
kb_version: 0.10.0
source_pages:
  - concepts/compile-not-retrieve
  - entities/karpathy
citations:
  - type: wiki
    path: concepts/compile-not-retrieve
  - type: wiki
    path: entities/karpathy
---

# What is compile-not-retrieve?

{answer body, preserved verbatim from LLM synthesis}

---
**Sources:**

- [[concepts/compile-not-retrieve]]
- [[entities/karpathy]]
```

Notes:
- Citations section built via `format_citations(result["citations"], mode="markdown")` (existing format, default).
- `kb_version` read dynamically from `kb.__version__` (opus approval condition #3).
- YAML values pass through `yaml_escape()` — existing utility.

### 5.2 `marp.py`

Marp-compatible markdown: YAML `marp: true` directive + `---` slide separators. Splits the answer into slides using a **code-fence-aware** state machine — never shatters fenced code blocks or GFM tables mid-slide.

```markdown
---
marp: true
theme: default
paginate: true
kb_query: "Q"
kb_generated_at: 2026-04-14T15:30:22.123456Z
---

# Question

What is compile-not-retrieve?

---

# Answer

{first \n\n-split section — under 800 chars OR containing a full fenced block}

---

# Answer (cont.)

{next slide}

---

# Sources

- [[concepts/compile-not-retrieve]]
- [[entities/karpathy]]
```

**Slide-splitting algorithm:**
```
segments = split(answer, "\n\n")
slides = []
current = ""
in_fence = False
for seg in segments:
    # Count triple-backtick fences in seg; flip state per fence
    fences_in_seg = count("```", seg)
    if fences_in_seg % 2 == 1:
        in_fence = not in_fence
    # If adding seg would exceed 800 chars AND we're not mid-fence, flush
    if len(current) + len(seg) > 800 and current and not in_fence:
        slides.append(current)
        current = seg
    else:
        current = f"{current}\n\n{seg}" if current else seg
slides.append(current)
```

Guard: if the answer contains a fenced block >800 chars, the block stays on one slide (may overflow the deck theme, acceptable — Marp handles overflow with scrolling).

### 5.3 `html.py`

Self-contained HTML5 document. Inline CSS, no external assets, no JS.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>KB Query: {escaped_question_truncated}</title>
  <meta name="kb-query" content="{escaped_question}">
  <meta name="kb-generated-at" content="2026-04-14T15:30:22.123456Z">
  <meta name="kb-version" content="0.10.0">
  <style>
    body { font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
    h1 { border-bottom: 1px solid #eee; padding-bottom: .25rem; }
    .sources { border-top: 1px solid #eee; margin-top: 2rem; padding-top: 1rem; font-size: .9em; }
    .meta { color: #666; font-size: .85em; }
    pre { background: #f5f5f5; padding: 1em; overflow-x: auto; border-radius: 4px; }
    code { background: #f5f5f5; padding: 2px 4px; border-radius: 2px; }
  </style>
</head>
<body>
  <article>
    <header>
      <h1>{escaped_question}</h1>
      <p class="meta">Generated 2026-04-14 15:30:22 UTC · {len(source_pages)} source pages</p>
    </header>
    <section class="answer">
      {escaped_answer_with_line_breaks_as_<br>}
    </section>
    <section class="sources">
      <h2>Sources</h2>
      <ul>
        <li><a href="{wiki_url(cite.path)}">{escaped_cite_path}</a></li>
        ...
      </ul>
    </section>
  </article>
</body>
</html>
```

**Security details:**
- Every interpolated field passes through `html.escape(..., quote=True)` individually — question, answer, page title, citation path, citation context.
- Citation anchors built from the structured `citations` list, never regex over the already-escaped answer text.
- `wiki_url(path)` returns `"./"` + escaped path — relative links only; no external URLs.
- No user-controllable content lands inside `<script>`, `<style>`, or attribute values beyond `href` / `content`, and `href` is always a locally-escaped relative path.

### 5.4 `chart.py`

Emits two files — a JSON sidecar with the data and a runnable Python matplotlib script. The script is never executed by kb; the user runs it to render a plot.

`outputs/{ts}-{slug}.json`:
```json
{
  "question": "What is compile-not-retrieve?",
  "generated_at": "2026-04-14T15:30:22.123456Z",
  "kb_version": "0.10.0",
  "source_pages": [
    {"id": "concepts/compile-not-retrieve", "rank": 1},
    {"id": "entities/karpathy", "rank": 2}
  ]
}
```

`outputs/{ts}-{slug}.py`:
```python
"""KB query output — matplotlib visualization script.

Query: What is compile-not-retrieve?
Generated: 2026-04-14T15:30:22.123456Z
KB version: 0.10.0

Run:
    python "outputs/2026-04-14-153022-123456-what-is-compile-not-retrieve.py"
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt  # requires `pip install matplotlib`

HERE = Path(__file__).parent
DATA = json.loads((HERE / __file__.replace(".py", ".json")).read_text(encoding="utf-8"))

PAGES = DATA["source_pages"]
LABELS = [p["id"] for p in PAGES]
RANKS = [p["rank"] for p in PAGES]

fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(PAGES))))
ax.barh(LABELS[::-1], [max(RANKS) - r + 1 for r in RANKS[::-1]])
ax.set_xlabel("Retrieval rank (inverted — higher = more relevant)")
ax.set_title(DATA["question"][:80])
fig.tight_layout()
fig.savefig(str(HERE / Path(__file__).with_suffix(".png").name), dpi=150)
print(f"Wrote {Path(__file__).with_suffix('.png').name}")
```

**Security details:**
- The question string is serialized via `json.dumps(question)` into the JSON file — never f-string-interpolated into the Python source.
- Page IDs likewise come only from the JSON file; the Python script does not contain any user-controlled string literals.
- Matplotlib is NOT imported by kb itself — the `import matplotlib.pyplot as plt` lives in the emitted script, run only by the user.
- The docstring header contains the question; it is run through `repr()` before interpolation into the Python triple-quoted string to escape embedded `"""` sequences.
- Guard: if `result["source_pages"]` is empty, adapter returns an error-laden JSON (`{"error": "no matching pages"}`) and a minimal script that prints the error — no empty-axes matplotlib crash.

### 5.5 `jupyter.py`

Uses the `nbformat` library to build a valid `.ipynb` with explicit kernelspec. Never sets `metadata.trusted = True` (auto-exec vector).

```python
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"},
    "kb_query": {
        "query": question,  # nbformat JSON-encodes safely
        "generated_at": iso_timestamp(),
        "kb_version": kb.__version__,
        "source_pages": source_pages,
    },
}
nb.cells = [
    nbf.v4.new_markdown_cell(f"# Question\n\n{question}"),
    nbf.v4.new_markdown_cell(f"## Answer\n\n{answer}"),
    nbf.v4.new_markdown_cell(f"## Sources\n\n{format_citations(citations, mode='markdown')}"),
    nbf.v4.new_code_cell(
        "# Re-run this query or inspect citations programmatically\n"
        "from kb.query.engine import query_wiki\n"
        f"# result = query_wiki({json.dumps(question)})\n"
        "# print(result['answer'])"
    ),
]
nbf.validate(nb)  # raises on malformed metadata
return nbf.writes(nb)
```

**Security details:**
- `nb.metadata.trusted` is never set; defaults to False — opening the notebook does NOT auto-execute code cells.
- All user-controlled strings pass through `json.dumps(question)` in the code cell literal.
- `nbformat.validate()` is invoked before serialization; any malformed metadata surfaces as `ValidationError` to the caller rather than writing a broken file.

---

## 6. Shared helpers in `common.py`

```python
# src/kb/query/formats/common.py
from datetime import datetime, timezone
from pathlib import Path
import re

from kb import __version__ as KB_VERSION
from kb.config import PROJECT_ROOT
from kb.utils.io import atomic_text_write
from kb.utils.text import slugify

MAX_OUTPUT_CHARS = 500_000
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})
MAX_SLUG_LEN = 80
MAX_COLLISION_RETRIES = 9

def safe_slug(text: str) -> str:
    """Slugify with empty-fallback + Windows-reserved-name guard + length cap."""
    slug = slugify(text)[:MAX_SLUG_LEN] if text else ""
    if not slug:
        slug = "untitled"
    # Guard Windows reserved names (case-insensitive; any of the slug's dot-separated parts)
    parts = slug.split(".")
    if any(part.upper() in WINDOWS_RESERVED for part in parts):
        slug = f"{slug}_0"
    return slug

def output_path_for(question: str, fmt: str) -> Path:
    """Deterministic collision-safe path: outputs/{ts}-{slug}.{ext}."""
    ext = {"markdown": "md", "marp": "md", "html": "html",
           "chart": "py", "jupyter": "ipynb"}[fmt]
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S-%f")
    base = f"{ts}-{safe_slug(question)}"
    for suffix in ("", *[f"-{i}" for i in range(2, MAX_COLLISION_RETRIES + 2)]):
        candidate = OUTPUTS_DIR / f"{base}{suffix}.{ext}"
        if not candidate.exists():
            return candidate
    raise OSError(f"Collision retries exhausted for {base}.{ext}")

def build_provenance(result: dict) -> dict:
    """Build the common provenance dict used across adapters."""
    return {
        "type": "query_output",
        "query": result["question"],   # ORIGINAL (not effective_question)
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "kb_version": KB_VERSION,
        "source_pages": result.get("source_pages", []),
        "citations": result.get("citations", []),
    }

def validate_payload_size(result: dict) -> None:
    if len(result.get("answer", "")) > MAX_OUTPUT_CHARS:
        raise ValueError(
            f"Answer exceeds MAX_OUTPUT_CHARS={MAX_OUTPUT_CHARS} "
            f"(got {len(result['answer'])}). Refuse to render."
        )
```

---

## 7. Citation rendering extension

**Current:** `format_citations(citations) -> str` returns markdown list only.

**Extended:** `format_citations(citations, mode="markdown") -> str` gains a `mode` kwarg. New modes:

- `"markdown"` (default — preserves current behavior)
- `"html"` — returns an `<ul>` block with `<a href="./wiki/{path}.md">{escaped_path}</a>` entries, all fields escaped.
- `"marp"` — returns `[[wikilinks]]` compatible with Marp's markdown renderer (same as markdown for now; kept as a separate mode so future Marp-specific link syntax can diverge).

Default preserves call sites at `cli.py:96` and `mcp/core.py:87` — zero breakage (opus approval condition #2).

---

## 8. Provenance frontmatter schema (common shape)

All 5 adapters embed the same provenance fields, encoded in format-appropriate syntax:

| Field | Value source | Markdown | Marp | HTML | Chart | Jupyter |
|---|---|---|---|---|---|---|
| `type` | `"query_output"` | YAML | YAML | `<meta>` | docstring/JSON | `nb.metadata.kb_query` |
| `query` | `result["question"]` (ORIGINAL, not rewritten) | YAML | YAML | `<meta>` + `<title>` | JSON | metadata |
| `format` | adapter name | YAML | YAML | `<meta>` | JSON | metadata |
| `generated_at` | `datetime.now(UTC).isoformat(timespec="microseconds")` | YAML | YAML | `<meta>` | JSON | metadata |
| `kb_version` | `kb.__version__` (DYNAMIC — opus condition #3) | YAML | YAML | `<meta>` | JSON + docstring | metadata |
| `source_pages` | `result["source_pages"]` | YAML list | YAML list | `<meta name=kb-sources>` | JSON | metadata |
| `citations` | `result["citations"]` | YAML list of dicts | (omitted — link section suffices) | Sources `<ul>` | JSON | Sources markdown cell |

---

## 9. Security gates (consolidated)

| Threat | Mitigation | Verified by |
|---|---|---|
| Path traversal via `output_path` | No override supported day-one; default path only | `test_v4_11_formats_common::test_no_override_param` (signature check) |
| Slug collision → silent overwrite | Microsecond timestamp + retry loop to `-9` | `test_safe_slug_collision` |
| Empty slug (emoji-only question) | Fallback to `"untitled"` | `test_safe_slug_empty_fallback` |
| Windows reserved filenames | Disambiguator `_0` suffix | `test_safe_slug_windows_reserved` |
| HTML injection in answer/question/page-title | Per-field `html.escape(quote=True)` | `test_html_xss_payload_escaped` |
| Citation anchors — regex-over-escaped mismatch | Structured citation list → anchors; never regex | `test_html_citation_from_structured_list` |
| Marp code-fence split | State-machine with `in_fence` toggle | `test_marp_preserves_fenced_code` |
| Jupyter auto-exec | `metadata.trusted` never set; defaults False | `test_jupyter_not_trusted` |
| Chart script code-injection via question | `json.dumps` into JSON sidecar; `repr()` in docstring | `test_chart_script_injection_safe` |
| Wiki index poisoning via outputs/ | `OUTPUTS_DIR = PROJECT_ROOT / "outputs"` (not wiki/); `load_all_pages` only scans `wiki_dir` subdirs | `test_outputs_not_in_load_all_pages` (opus condition #4) |
| Unbounded output size | `MAX_OUTPUT_CHARS=500_000` pre-render check on answer | `test_rejects_oversize_answer` |
| Bad format parameter | `VALID_FORMATS` enum + `.lower().strip()` at CLI + MCP entry | `test_format_param_validation` |
| Claude-Code-mode silent no-op | MCP error when `output_format` + `use_api=False` | `test_mcp_requires_use_api` |
| Format vs override combo | `--output` is not accepted (no override day-one) | `test_cli_no_output_flag` |
| HTML-escape on wikilinks `[[...]]` | Wikilinks rendered as escaped `<a>` anchors; literal `[[]]` stays in markdown/marp | `test_html_renders_wikilinks_as_anchors` |

---

## 10. File breakdown

| File | Type | LOC | Tests |
|---|---|---|---|
| `src/kb/query/formats/__init__.py` | new | ~35 | — |
| `src/kb/query/formats/common.py` | new | ~85 | `test_v4_11_formats_common.py` (~15 tests) |
| `src/kb/query/formats/markdown.py` | new | ~50 | `test_v4_11_markdown.py` (~6 tests) |
| `src/kb/query/formats/marp.py` | new | ~75 | `test_v4_11_marp.py` (~8 tests) |
| `src/kb/query/formats/html.py` | new | ~100 | `test_v4_11_html.py` (~10 tests) |
| `src/kb/query/formats/chart.py` | new | ~80 | `test_v4_11_chart.py` (~6 tests) |
| `src/kb/query/formats/jupyter.py` | new | ~60 | `test_v4_11_jupyter.py` (~6 tests) |
| `src/kb/query/citations.py` | modified | +15 (mode kwarg) | test_query.py (existing pass) + 2 new |
| `src/kb/query/engine.py` | modified | +8 (kwarg + dispatch) | `test_v4_11_query_integration.py` (~4 tests) |
| `src/kb/cli.py` | modified | +6 (flag + dispatch) | `test_v4_11_cli.py` (~4 tests) |
| `src/kb/mcp/core.py` | modified | +15 (param + validation) | `test_v4_11_mcp.py` (~5 tests) |
| `.gitignore` | modified | +2 | — |
| `requirements.txt` | modified | +1 (`nbformat`) | — |
| **Totals** | — | **~870 LOC** | **~66 tests** |

Dependency addition: `nbformat >= 5.0, <6.0` (pure Python, MIT license, actively maintained, zero CVEs in 5.x). matplotlib is NOT added — only the emitted chart script mentions it, and the user installs it if they want to run the script.

---

## 11. Testing plan (full)

**New test files** (all use existing `tmp_path` / `tmp_wiki` / mocked `call_llm`):

1. `tests/test_v4_11_formats_common.py` — slug + path builder + provenance + size guards
2. `tests/test_v4_11_markdown.py` — frontmatter + body + citation list
3. `tests/test_v4_11_marp.py` — slide split, code-fence preservation, YAML directive
4. `tests/test_v4_11_html.py` — XSS payload escape per field, relative links, meta tags
5. `tests/test_v4_11_chart.py` — JSON sidecar well-formed, Python script parses (use `ast.parse`), injection-safe
6. `tests/test_v4_11_jupyter.py` — nbformat.validate passes, trusted never True, kernelspec present
7. `tests/test_v4_11_query_integration.py` — `query_wiki(..., output_format=...)` end-to-end per format
8. `tests/test_v4_11_cli.py` — `kb query --format` dispatches correctly
9. `tests/test_v4_11_mcp.py` — `kb_query(output_format=..., use_api=True)`; `use_api=False` errors
10. `tests/test_v4_11_security.py` — consolidated adversarial payloads from §9

Plus 2 new tests in `tests/test_query.py` covering `format_citations(..., mode=...)` back-compat.

**Target totals:** 1322 existing + ~50 new ≈ 1370-1375 tests across 98 test files.

---

## 12. Doc update checklist (gate §8 in feature-dev)

- `CHANGELOG.md` → `[Unreleased]` → Added entry
- `BACKLOG.md` → DELETE Tier 1 item #1; trim HIGH LEVERAGE — Output-Format Polymorphism bullet
- `CLAUDE.md` → bump test count to ~1370, module count 19→20; update `query_wiki` signature; new MCP tool row for `output_format` param; new "Output Formats" subsection after "Query"
- `README.md` → feature-table row; mention `outputs/` folder in tree comment
- `docs/architecture/architecture-diagram.html` → add "Output Adapters" block hanging off kb.query; re-render PNG
- `.gitignore` → `outputs/`
- This spec committed to `docs/superpowers/specs/`

---

## 13. YAGNI scope-outs (explicit)

| Cut | Reason | Path back |
|---|---|---|
| `output_path` caller-supplied override | Removes Windows drive / symlink / allowlist attack surface; no user has asked | BACKLOG entry if someone requests |
| In-process matplotlib PNG | Dependency burden; blocks MCP event loop; attack surface of image libs | User runs emitted script |
| Marp CLI server-side render | Marp is external tooling — user's choice | User installs `@marp-team/marp-cli` |
| PDF / PPTX / DOCX | Per-format library dep, heavier than nbformat | BACKLOG entry if demanded |
| Retention policy / cleanup | Low traffic today; policy is a sweep, not a blocker | BACKLOG entry |
| `kb_lint` awareness of outputs/ | Gitignored + separate dir; not wiki content | BACKLOG entry |
| `text` format with `--output`/override | No override exists day-one; moot | — |
| Coverage-confidence refusal gate | Orthogonal feature (Tier 2 #7) | BACKLOG |

---

## 14. Opus-approval conditions (bake into implementation)

From the final opus approval-gate review:

1. **`output_path` doc inconsistency** — signature is `*, output_format=None` ONLY (no `output_path` kwarg). Covered by locked decision #3.
2. **`format_citations` back-compat** — default `mode="markdown"` preserves every existing call site. Verified via grep; test added.
3. **`kb_version` dynamic** — read from `kb.__version__` in `common.build_provenance()`, not hardcoded. Covered in §6.
4. **Defense-in-depth `load_all_pages` exclusion** — add explicit regression test asserting `load_all_pages(wiki_dir)` does not surface files under `{project_root}/outputs/` even when OUTPUTS_DIR is placed adjacent to WIKI_DIR. See test plan §11.

All four conditions are in §6, §7, §9, and §11 of this spec; implementation plan (next phase) tracks each as a discrete task.

---

## 15. Open questions — none

Every round-1/2/3 finding is either addressed in sections 2-14 above or explicitly deferred in §13 with a path back. Ready for writing-plans.
