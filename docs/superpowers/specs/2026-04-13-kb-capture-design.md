# Design: `kb_capture` MCP tool

**Date:** 2026-04-13
**Phase:** 5 — Ambient Capture & Session Integration
**Leverage tier:** HIGH
**Effort estimate:** Medium (~400 LOC in one module + 1 test file + 1 YAML template + MCP registration)
**Source inspiration:** sage-wiki `wiki_capture` (BACKLOG.md line 94)

---

## 1. Overview

`kb_capture` is a new MCP tool that accepts up to 50KB of unstructured text — chat logs, scratch notes, or LLM session transcripts — and atomizes it into discrete knowledge items written to `raw/captures/<slug>.md`. The tool fills the gap that `kb_ingest_content` (which expects already-structured content) and `kb_save_source` (which just dumps bytes to disk) cannot: turning messy conversational input into reusable atomic sources that flow through the existing ingest pipeline.

**Unified use case (the input shape is heterogeneous):**
- Mid-session bookmarks — "capture these 3 decisions we just made"
- Batch notes dumps — paste a daily log or meeting transcript and extract the signal
- Cross-LLM imports — paste a ChatGPT / Gemini session and surface the insights

The scan-tier LLM acts as an **atomizer**, not an author: it identifies knowledge-item boundaries in the input and returns verbatim spans with structured metadata. Each item becomes its own first-class raw source that the agent can then ingest with `kb_ingest` on a per-file basis.

---

## 2. Locked design decisions

These six decisions were settled during brainstorming and are now load-bearing for the rest of this doc:

| # | Decision | Rationale |
|---|---|---|
| 1 | **Single feature scope** — one MCP tool, no bundled sibling features | Fits a single feature-dev cycle. Proves the capture workflow end-to-end before layering on `.llmwikiignore`, session hooks, or auto-ingest. |
| 2 | **Atomic N-files output** — one `raw/captures/<slug>.md` per extracted item | Matches existing `raw/` philosophy (one file = one source). `kb_ingest` already handles atomic dedup and cascade. Context preserved via `captured_alongside` metadata, not a wrapper file. |
| 3 | **Hybrid content model** — LLM-structured frontmatter + verbatim body | Preserves raw/ immutability (body is source text; LLM output lives only in frontmatter metadata). Enables rich querying via typed metadata without introducing a rewrite layer. |
| 4 | **Pure save — no auto-ingest chain** | Matches `kb_compile_scan` → `kb_ingest` pattern. Agent gets the review moment before committing to the wiki. Avoids partial-failure ambiguity when N items ingest sequentially. |
| 5 | **Minimal `kind` vocabulary** — `decision | discovery | correction | gotcha` | Small auditable enum reduces force-fit pressure on the LLM. Items that don't fit become noise, tracked via `filtered_out_count`. Extend later if real usage shows gaps. |
| 6 | **Scanner + reject at boundary** — regex secret scan before any LLM call | Zero-secret-to-API guarantee. Prevents accidental commit of credentials to `raw/captures/` and git history. Composes with future `.llmwikiignore` (path-level filter). |

---

## 3. Module layout & public API

**New file:** `src/kb/capture.py` (single module; matches project convention for ~400 LOC features like `kb.graph`, `kb.evolve`, `kb.compile`).

```python
# src/kb/capture.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class CaptureItem:
    slug: str
    path: Path              # absolute path to raw/captures/<slug>.md
    title: str
    kind: str               # one of CAPTURE_KINDS
    body_chars: int         # for display; body itself lives on disk

@dataclass(frozen=True)
class CaptureResult:
    items: list[CaptureItem]
    filtered_out_count: int        # LLM noise filter + body-verbatim rejections (summed)
    rejected_reason: str | None    # all-or-nothing boundary rejection (no items written)
    provenance: str                # resolved provenance (always set, never empty)

def capture_items(content: str, provenance: str | None = None) -> CaptureResult:
    """Extract discrete knowledge items from messy text; write each to raw/captures/."""
```

**Internal structure:**

```
capture_items(content, provenance)
├── _validate_input(content)           # size cap, empty check, CRLF normalize
├── _scan_for_secrets(content)         # regex sweep → reject-at-boundary on match
├── _resolve_provenance(provenance)    # auto-fill if None/empty
├── _extract_items_via_llm(content)    # scan-tier call_llm_json
├── _verify_body_is_verbatim(items)    # drop items whose body was reworded
├── _write_item_files(items, prov)     # slug + collision + atomic write
└── returns CaptureResult
```

**New config constants** (`src/kb/config.py`):

```python
CAPTURES_DIR = RAW_DIR / "captures"
CAPTURE_MAX_BYTES = 50_000               # hard input size cap (UTF-8 bytes)
CAPTURE_MAX_ITEMS = 20                    # cap items extracted per call
CAPTURE_KINDS = ("decision", "discovery", "correction", "gotcha")
```

`_CAPTURE_SECRET_PATTERNS` lives inside `capture.py` as a module-private tuple — it's implementation detail, not operator-tunable.

**MCP tool registration** (`src/kb/mcp/core.py`):

```python
@mcp.tool()
def kb_capture(
    content: str,
    provenance: str | None = None,
) -> str:
    """Extract discrete knowledge items from messy text and write each to raw/captures/."""
```

The wrapper calls `capture_items()`, then formats the `CaptureResult` into a plain-text MCP response. See §7 for response format.

**Public API surface:**

| Caller | Entry point |
|---|---|
| MCP client (Claude Code) | `kb_capture` tool |
| Python tests / library use | `from kb.capture import capture_items, CaptureResult, CaptureItem` |
| CLI | Deferred — add `kb capture <file>` only if real usage demands it |

---

## 4. Data flow (happy path)

```
1. MCP client → kb_capture(content, provenance)
2. MCP wrapper → capture_items(content, provenance)
3. _validate_input(content)
       • len(content.encode('utf-8')) ≤ CAPTURE_MAX_BYTES
       • content.strip() != ''
       • normalize \r\n → \n in-place
4. _scan_for_secrets(content)
       • regex sweep per _CAPTURE_SECRET_PATTERNS
       • on match → return CaptureResult(items=[], rejected_reason=...) and stop
5. _resolve_provenance(provenance)
       • None / '' / slugifies-to-empty  →  f"capture-{ISO8601}-{4hex}"
       • else                              →  slugify(provenance)[:80] + f"-{ISO8601}"
6. _extract_items_via_llm(content) → Anthropic API (scan tier, Haiku 4.5)
       • call_llm_json(prompt, tier="scan", schema=_CAPTURE_SCHEMA)
       • schema enforces kind ∈ CAPTURE_KINDS, ≤ CAPTURE_MAX_ITEMS
       • raises LLMError on failure (propagates; MCP layer formats)
7. _verify_body_is_verbatim(items, content)
       • for each item: if item["body"].strip() not in content → drop, increment filter count
       • defensive against LLM rewording
8. _write_item_files(items, provenance) → filesystem
       • CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
       • existing = {p.stem for p in CAPTURES_DIR.iterdir() if p.suffix == ".md"}
       • for each item:
           slug = _build_slug(kind, title, existing)  # collision-safe
           existing.add(slug)
       • once all slugs resolved, compute captured_alongside = all slugs
       • for each item:
           markdown = _render_markdown(item, captured_alongside, provenance)
           Path(CAPTURES_DIR / f"{slug}.md").open('x').write(markdown)  # exclusive create
9. return CaptureResult(items=[...], filtered_out_count=N,
                        rejected_reason=None, provenance=resolved_prov)
```

### Scan-tier LLM prompt (shape; final wording to be finalized in implementation)

```
You are atomizing messy text into discrete knowledge items.

Input: up to 50KB of conversation logs, scratch notes, or chat transcripts.
Output: JSON matching the schema — a list of items, each with:
  - title (max 100 chars, imperative phrase)
  - kind: one of "decision" | "discovery" | "correction" | "gotcha"
  - body (verbatim span from the input — DO NOT reword, summarize, or rewrite)
  - one_line_summary (max 200 chars, your words, for frontmatter display)
  - confidence: "stated" | "inferred" | "speculative"

Keep an item only if it is:
  - a specific decision (something the user or team settled on)
  - a specific discovery (a new fact learned from evidence)
  - a correction (something previously believed that turned out wrong)
  - a gotcha (a pitfall or non-obvious constraint worth remembering)

Filter as noise:
  - pleasantries, apologies, meta-talk about the chat itself
  - half-finished thoughts or unresolved questions (unless the question IS the gotcha)
  - duplicates of items already in your list
  - off-topic tangents
  - retried / corrected-in-place content (keep only the final form)

Cap the output at 20 items. Also report `filtered_out_count`: the number of
candidate items you rejected as noise.
```

### JSON schema passed to `call_llm_json`

```python
_CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 100},
                    "kind": {"enum": list(CAPTURE_KINDS)},
                    "body": {"type": "string", "minLength": 1},
                    "one_line_summary": {"type": "string", "maxLength": 200},
                    "confidence": {"enum": ["stated", "inferred", "speculative"]},
                },
                "required": ["title", "kind", "body", "one_line_summary", "confidence"],
            },
        },
        "filtered_out_count": {"type": "integer", "minimum": 0},
    },
    "required": ["items", "filtered_out_count"],
}
```

### Flow invariants

1. Secret scan runs **before** LLM call. Zero-secret-to-API guarantee.
2. Body is verbatim-verified **after** LLM call. Protects raw/ immutability even when the LLM misbehaves.
3. Provenance is always set, never empty.
4. `captured_alongside` populated after all slugs resolved (so collision-adjusted slugs appear correctly in siblings).
5. Atomic writes via exclusive-create mode; no half-written files on crash.
6. No retry inside `capture_items`; `call_llm_json`'s 3-retry exponential backoff is the only retry layer.

---

## 5. Per-file markdown layout

### Example file

```markdown
---
title: "Pick atomic N-files for kb_capture output"
kind: decision
confidence: stated
one_line_summary: "Each extracted knowledge item becomes its own raw/captures/<slug>.md; context is carried via captured_alongside metadata rather than a session wrapper file."
captured_at: 2026-04-13T17:45:23Z
captured_from: claude-code-session-2026-04-13T17-45Z
captured_alongside:
  - discovery-firecrawl-returns-null-on-cloudflare-sites
  - correction-tiktoken-not-used-here-use-model2vec
  - gotcha-crlf-breaks-evidence-trail-regex
source: mcp-capture
---

[verbatim span the scan-tier LLM identified as this item's body — may be a single
sentence, a paragraph, or a small code block with surrounding context. Never reworded.]
```

### Field contract

| Field | Source | Purpose |
|---|---|---|
| `title` | LLM | Human-readable identifier; drives slug. Max 100 chars. |
| `kind` | LLM | Typed filter for lint / query / callouts. One of `CAPTURE_KINDS`. |
| `confidence` | LLM | Per-item confidence. Reuses existing wiki confidence enum. |
| `one_line_summary` | LLM | Preview for search/listings. Max 200 chars. The only LLM-authored prose; body is verbatim. |
| `captured_at` | tool (auto) | ISO8601 UTC, `Z` suffix. |
| `captured_from` | tool | Resolved provenance (user-supplied slugified label, or auto `capture-<ISO>-<4hex>`). |
| `captured_alongside` | tool (post-hoc) | Slugs of sibling items from same call. Enables session re-assembly queries. |
| `source` | tool (literal) | `mcp-capture`. Distinguishes from `article`, `paper`, etc. when tools scan `raw/`. |

### Slug algorithm

```python
def _build_slug(kind: str, title: str, existing: set[str]) -> str:
    base = slugify(f"{kind}-{title}")
    base = base[:80]                      # filesystem sanity cap
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
```

- Kind prefix makes `ls raw/captures/` visually useful.
- 80-char cap protects against Windows `MAX_PATH=260`.
- Numeric suffix on collision matches v0.9.0 slug collision pattern.
- `existing` set populated once via `os.scandir` — single disk scan per call.

### Body verbatim check

```python
if item["body"].strip() not in content:
    filtered_out_count += 1
    continue
```

Hard gate: we never write a file whose body is not a verbatim span of the input. `.strip()` tolerates leading/trailing whitespace variance. Conservative bias toward source fidelity — if the LLM normalized internal whitespace, we drop the item. Surfaced via `filtered_out_count`.

### Fields deliberately NOT in frontmatter

- No `hash` / `content_hash` — ingest computes from bytes at ingest time.
- No `type:` — that's a wiki-page field, meaningless on raw/ content.
- No `created:` / `updated:` — wiki-page fields; `captured_at` plays the analogous role here.
- No `wiki_pages:` back-reference — populated later by `kb_ingest` on the wiki side.

---

## 6. New template: `templates/capture.yaml`

`kb_ingest` reads YAML templates to drive write-tier extraction. Captures need a dedicated template so `kb_ingest(path, source_type="capture")` works without retrofitting existing templates.

```yaml
# templates/capture.yaml
source_type: capture
description: "Atomic knowledge item captured from chat, notes, or unstructured text."
extract:
  entities:
    description: "Named entities explicitly mentioned (people, projects, libraries, companies)."
    type: list
  concepts:
    description: "Technical concepts or abstractions referenced."
    type: list
  summary:
    description: "1-2 sentence restatement of the captured item, grounded in the body text."
    type: string
  tags:
    description: "2-5 topic tags for categorization."
    type: list
wiki_outputs:
  - summaries/<slug>.md
  - entities/<entity>.md  (per entity)
  - concepts/<concept>.md  (per concept)
```

**Why a dedicated template** (vs. reusing `article.yaml`): captures are already atomic and already have title/kind/summary in frontmatter; an article template would over-extract (authors, pub date, abstract — irrelevant). Tight template = cleaner extraction, fewer wasted tokens, end-to-end flow works immediately.

---

## 7. Error handling

### Class A — hard reject at input boundary (no LLM call, no disk writes)

| Condition | Check | Returned `rejected_reason` |
|---|---|---|
| Empty / whitespace-only content | `_validate_input` | `"Error: content is empty. Nothing to capture."` |
| Content exceeds 50KB UTF-8 bytes | `_validate_input` | `"Error: content exceeds 50000 bytes (got N). Split into chunks and retry."` |
| Secret pattern matched | `_scan_for_secrets` | `"Error: secret pattern detected at line N (<pattern_label>). No items written. Redact and retry."` |

All produce `CaptureResult(items=[], filtered_out_count=0, rejected_reason=<msg>, provenance=<resolved>)`. MCP wrapper surfaces the `rejected_reason`.

### Class B — scan-tier LLM failure

- `call_llm_json` retries 3× with exponential backoff (existing infrastructure).
- After exhaustion, `LLMError` propagates up through `capture_items` unchanged.
- MCP wrapper catches and formats: `"Error: LLM unavailable — try again in a moment."`
- No partial state — secret scan passed, but no files written yet.

### Class C — quality filtering (not an error; success with zero items)

| Outcome | Signal |
|---|---|
| LLM filtered everything as noise | `CaptureResult(items=[], filtered_out_count=N, rejected_reason=None)` |
| All item bodies failed verbatim check | Same as above |
| LLM returned `items: []` explicitly | Same as above |

`filtered_out_count` collapses LLM's own noise count + our body-verbatim rejections into a single number for v1. Breakdown deferred unless real usage demands diagnosis.

### Class D — filesystem write errors

| Condition | Handling |
|---|---|
| `CAPTURES_DIR` doesn't exist | `mkdir(parents=True, exist_ok=True)` at start of `_write_item_files`. Idempotent. |
| Slug collision race (concurrent callers) | `Path.open(mode='x')` (exclusive create). On `FileExistsError`, re-resolve slug with next suffix and retry. Max 10 retries per item. |
| Disk full / permission denied | **Fail fast.** Stop writing further items. Return `CaptureResult` with items-written-so-far in `items`, `rejected_reason` names the error and count. No rollback of successful writes. |

**Why no rollback on Class D:** successfully-written files are valid captures; deleting them destroys good work. Disk errors are rare and indicate systemic problems (full disk, permission misconfiguration) that rollback doesn't fix. Matches project idiom — `kb_ingest` also leaves partial state on LLM errors.

### Edge cases explicitly handled

| Case | Behavior |
|---|---|
| `provenance=""` | Treated as `None` → auto-generate |
| `provenance` slugifies to empty (e.g., `"!!!"`) | Fall back to auto-generated |
| `provenance` > 80 chars | `slugify()[:80]` truncation, then append `-<ISO>` timestamp |
| Content contains CRLF | Normalize `\r\n` → `\n` at `_validate_input` |
| Content contains unicode | `encode('utf-8')` for size cap; `slugify` handles unicode |
| LLM returns `kind` not in enum | `call_llm_json` schema validation rejects; `LLMError` propagates |
| LLM returns duplicate titles | Each becomes a separate file via slug collision suffix |
| Body spans > 10KB | Allowed — 50KB input cap naturally bounds total output |

### MCP response formats

**Happy path:**
```
Captured 5 items, filtered 12 as noise. Provenance: <resolved_prov>

- raw/captures/decision-<slug>.md  [decision]
- raw/captures/discovery-<slug>.md  [discovery]
- ...

Next: run kb_ingest on each path to promote to wiki/.
```

**Zero items (valid success):**
```
Captured 0 items, filtered 15 as noise. Provenance: <resolved_prov>
(No items met the decision/discovery/correction/gotcha bar.)
```

**Hard reject:**
```
Error: <rejected_reason>
```

**Partial write failure:**
```
Captured 3 items before disk error. Provenance: <resolved_prov>

- raw/captures/decision-<slug>.md  [decision]
- raw/captures/discovery-<slug>.md  [discovery]
- raw/captures/gotcha-<slug>.md  [gotcha]

Error: failed to write correction-<slug>: [Errno 28] No space left on device. 2 of 5 items not written.
```

---

## 8. Security-gate prep checklist

These items will be verified by the `everything-claude-code:security-review` skill after implementation. Listing them here so the design already covers them:

- [x] **Path traversal** — slugs pass through `slugify()` which strips `/`, `..`, etc. Additional defense: compare `(CAPTURES_DIR / f"{slug}.md").resolve()` to `CAPTURES_DIR.resolve()` — reject if not a sub-path. Same pattern as existing `_validate_page_id`.
- [x] **Secret leakage** — regex scan runs **before** LLM call; match → reject without touching API. Content never lands in API logs or `raw/captures/` files.
- [x] **Prompt injection** — forced tool_use + schema-validated output + verbatim-body check bound attacker capability to "write files with user-supplied content and user-supplied titles (up to 100 chars) into `raw/captures/`" — same blast radius as the user writing those files directly. No privilege escalation.
- [x] **Input bounds** — 50KB byte-level cap; max 20 items per call; max 80-char slugs; max 10 collision retries per slug.
- [x] **No new dependencies** — uses existing `kb.utils.llm.call_llm_json`, `kb.utils.text.slugify`, stdlib `re`, `pathlib`, `datetime`, `secrets` (for 4-hex). No `pip install`. No supply-chain concern.
- [ ] **Rate limiting** — deferred. Per-MCP-call; no ambient rate limit on any MCP tool in this project. `call_llm_json`'s retry handles LLM-side limits. Not a v1 concern.

**Secret scanner regex list (first-cut, tunable in implementation):**

- AWS access key: `AKIA[0-9A-Z]{16}`, `ASIA[0-9A-Z]{16}`
- OpenAI: `sk-proj-[a-zA-Z0-9_-]{20,}`, `sk-[a-zA-Z0-9]{20,}`
- Anthropic: `sk-ant-[a-zA-Z0-9_-]{20,}`
- GitHub PAT: `ghp_[a-zA-Z0-9]{36}`, `github_pat_[a-zA-Z0-9_]{82}`
- Private key blocks: `-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----`
- Generic high-entropy: **skipped for v1** (too many false positives on legitimate base64 content).

Tradeoff accepted: false-positive rejection of legitimate content that looks secret-like (code samples containing fake `sk-...` literals in docs). Mitigation: the error message names the matched pattern and line number so the user can see "oh, that's a docstring example" and edit/escape.

---

## 9. Testing strategy

### Test file

Single new file: `tests/test_capture.py`. Module-named convention (matches `test_graph.py`, `test_evolve.py`). MCP wrapper tests live inline in `tests/test_capture.py` under `class TestMCPWrapper`.

### Fixtures

**Reuse:** `tmp_project(tmp_path)` — isolated wiki/raw root.

**Add new (in `tests/conftest.py`):**

```python
@pytest.fixture
def tmp_captures_dir(tmp_project, monkeypatch):
    """Isolated raw/captures/ directory with kb.config.CAPTURES_DIR repointed."""
    captures = tmp_project / "raw" / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("kb.config.CAPTURES_DIR", captures)
    monkeypatch.setattr("kb.capture.CAPTURES_DIR", captures)
    return captures
```

Double monkey-patch is defensive against import-time vs. runtime binding. Matches existing handling of `WIKI_DIR`.

**Update `tmp_project`** (one-line change): create `raw/captures/` alongside existing 4 raw subdirs. Forward-compatible with other tests that may later touch captures.

### Mock strategy

```python
@pytest.fixture
def mock_scan_llm(monkeypatch):
    """Installs a canned JSON response for call_llm_json in capture.py."""
    def _install(response: dict):
        def fake_call(prompt, tier="write", schema=None):
            assert tier == "scan", f"kb_capture must use scan tier, got {tier}"
            return response
        monkeypatch.setattr("kb.capture.call_llm_json", fake_call)
    return _install
```

Thin, self-documenting. Per project feedback memory: test failures? Check mocks first. This mock's behavior is obvious at a glance.

### Test matrix (~30 tests)

| Group | Tests |
|---|---|
| **Class A — input reject** | empty, whitespace-only, oversize, at-boundary (50000 exactly), CRLF normalized |
| **Class A — secret scan** | AWS / OpenAI / Anthropic / GitHub / private key each reject; benign passes; false-positive-like still rejects (conservative bias documented) |
| **Class B — LLM failure** | `LLMError` propagates |
| **Class C — quality filter** | zero items returned = success, body-reworded-drop, filter-count-sums |
| **Class D — write errors** | dir-created-if-missing, slug collision suffix, multiple collisions, same-call duplicate titles, partial-write fail-fast |
| **Happy path — frontmatter** | all fields present, `captured_alongside` includes siblings, auto provenance format, user provenance slugified, provenance truncated at 80, body verbatim on disk |
| **Slug generation** | kind prefix, length cap 80, unicode handling |
| **MCP wrapper** | happy path formatted, zero-items formatted, rejection formatted, partial-write formatted |

### Not tested

- Live Anthropic API call — matches project convention; manual during post-implementation verification.
- Scan-tier prompt wording — implementation detail; tests assert behavior and schema, not prompt text.
- Concurrent-process race — exclusive create protects same-process; true multi-process is out of scope.
- Performance / load — inherently low-throughput tool.

### Coverage target

~95%+ line coverage on `src/kb/capture.py`. Verify with `pytest --cov=src/kb/capture tests/test_capture.py`.

### TDD sequencing for `writing-plans`

Six sub-tasks, each RED → GREEN → REFACTOR:

1. `_validate_input` (empty, whitespace, size cap, CRLF)
2. `_scan_for_secrets` (all 5 secret classes, benign pass)
3. `_extract_items_via_llm` + `_verify_body_is_verbatim` (schema, mock LLM, body drops)
4. `_build_slug` (kind prefix, cap, collision, unicode)
5. `_write_item_files` (frontmatter rendering, captured_alongside, atomic write, partial-failure)
6. `kb_capture` MCP wrapper (four response formats)

Implementation flows module-bottom-up (utilities first, orchestrator last) so each RED can fail meaningfully.

---

## 10. Integration surface changes

Beyond the new `capture.py` module, four small edits:

| File | Change | LOC |
|---|---|---|
| `src/kb/config.py` | Add `CAPTURES_DIR`, `CAPTURE_MAX_BYTES`, `CAPTURE_MAX_ITEMS`, `CAPTURE_KINDS` | ~5 |
| `src/kb/mcp/core.py` | Register `kb_capture` tool + thin formatter wrapper | ~30 |
| `templates/capture.yaml` | New YAML template (see §6) | ~15 |
| `tests/conftest.py` | New `tmp_captures_dir` fixture; update `tmp_project` to include captures/ | ~10 |

Plus:

| File | Change | LOC |
|---|---|---|
| `src/kb/capture.py` | New module | ~400 |
| `tests/test_capture.py` | New test file (~30 tests) | ~500 |

**Total surface:** ~960 LOC across 6 files.

---

## 11. Documentation updates (for the doc-update gate)

Per feature-dev skill's doc-update gate, these updates are required before the final commit:

| Document | Section | Update |
|---|---|---|
| `CLAUDE.md` | "MCP Servers" → kb tools list | Add `kb_capture(content, provenance)` entry |
| `CLAUDE.md` | "Implementation Status" → module/tool counts | `19 modules` (was 18), `26 MCP tools` (was 25) |
| `CLAUDE.md` | Add "Phase 5 modules" line (or append to existing Phase 2 list) | Mention new `kb.capture` module alongside Phase 1 / Phase 2 module listings |
| `CLAUDE.md` | "Ingestion Commands" section | New subsection or note about conversation capture workflow |
| `CHANGELOG.md` | `[Unreleased]` → Added | Entry describing `kb_capture` tool, atomization model, secret scanner |
| `BACKLOG.md` | Phase 5 / Ambient Capture | **Delete** the `kb_capture` entry (line 94) — resolved |
| `README.md` | Feature list / roadmap | Mention conversation-capture support |
| `docs/architecture/architecture-diagram.html` | New pre-ingest capture stage | Add box for `kb_capture → raw/captures/ → kb_ingest` flow + re-render PNG |

**Architecture diagram is mandatory** per CLAUDE.md's architecture sync rule.

---

## 12. Open questions for the plan phase (Context7 verification)

The following need Context7 verification before subagent dispatch:

| Topic | Why we need current docs |
|---|---|
| `anthropic` SDK `tool_use` forced-output pattern used by `call_llm_json` | Schema format may have changed; v1.x → v2.x breaking change possible |
| `slugify()` — whether `kb.utils.text.slugify` handles unicode as this design assumes | Implementation detail; verify current behavior matches expectation |
| MCP tool registration via `@mcp.tool()` in `kb.mcp.core` | Ensure decorator signature matches current FastMCP / mcp-python-sdk release |
| `pathlib.Path.open('x')` exclusive-create behavior on Windows | Windows filesystem semantics around exclusive create can surprise — verify behavior matches Unix expectation |

None of these are blocking; all are "confirm current behavior before writing code" checks the planning phase handles.

---

## 13. Non-goals / explicit deferrals

- **Auto-ingest chaining.** `kb_capture` does not invoke `kb_ingest`. Agent loops manually.
- **Dedup against existing captures.** Content-hash dedup is `kb_ingest`'s job; capturing identical content twice writes twice, second ingest reports duplicate.
- **Streaming / chunking for inputs over 50KB.** Hard reject; agent must split.
- **LLM-based prompt-injection detection.** Regex secret scan + forced tool_use + verbatim-body check provide adequate defense.
- **CLI surface (`kb capture <file>`).** Add only if real usage demands it.
- **`filtered_out_count` breakdown** (LLM noise vs body-verbatim rejections). Single number in v1; split if diagnostics demand.
- **`.llmwikiignore` path filter** — separate BACKLOG item; composes with this one but ships independently.
- **Session-JSONL auto-ingest** — separate BACKLOG item under Ambient Capture pillar.
- **`captured_alongside` consistency under concurrent-process race.** If a concurrent `kb_capture` call writes a slug our in-memory `existing` set didn't know about, our write of that slug raises `FileExistsError`, we re-resolve to the next suffix — but siblings already written may list the original (now-taken) slug in their `captured_alongside`. Accepted as v1 limitation: single-user tool, rare race, worst case is one stale entry in a session-reassembly query. A two-phase reserve-then-write protocol would fix it but is overkill for the risk.

---

## 14. Success criteria

The feature is considered complete when all of the following hold:

1. All ~30 tests in `tests/test_capture.py` pass.
2. `pytest --cov=src/kb/capture` shows ≥ 95% line coverage.
3. `ruff check src/kb/capture.py tests/test_capture.py` is clean.
4. Manual end-to-end: call `kb_capture` with a 5-item sample conversation → verify N files in `raw/captures/` with correct frontmatter → call `kb_ingest` on each → verify wiki pages generated.
5. Security review gate passes (`everything-claude-code:security-review`) — all §8 items verified, no new findings.
6. Doc-update gate closed — all §11 edits landed; architecture diagram PNG re-rendered.
7. Test count in `CLAUDE.md` bumped from 1171 → ~1201 (+30 for `test_capture.py`).
8. Commit pushed to `main`; BACKLOG.md `kb_capture` entry deleted; CHANGELOG.md `[Unreleased]` entry added.
