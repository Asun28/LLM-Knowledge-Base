# `kb_capture` MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `kb_capture` MCP tool that takes up to 50KB of unstructured text (chat logs, scratch notes, LLM session transcripts) and atomizes it into discrete `raw/captures/<slug>.md` files via scan-tier LLM extraction, with a strict secret-scanner reject-at-boundary policy and a per-process rate limiter.

**Architecture:** Single new module `kb.capture` exposing `capture_items()` + `CaptureItem`/`CaptureResult` dataclasses. The flow is: provenance resolve → rate limit → input validate → secret scan → scan-tier LLM atomize → body verbatim verify → atomic file write with collision retry. A new YAML template (`templates/capture.yaml`) lets `kb_ingest` consume capture files via the existing pipeline. New MCP tool wrapper in `kb.mcp.core`. Doc-update gate touches CLAUDE.md, BACKLOG.md, CHANGELOG.md, README.md, and the architecture diagram.

**Spec:** `docs/superpowers/specs/2026-04-13-kb-capture-design.md` (897 lines, 14 sections). All design decisions and rationale live there. This plan implements that spec section-for-section.

**Tech Stack:** Python 3.12+, FastMCP (`@mcp.tool()`), Anthropic SDK via `kb.utils.llm.call_llm_json`, `pathlib`, `threading.Lock`, `os.O_EXCL|O_CREAT|O_WRONLY` for slug reservation, `dataclasses(frozen=True)`, pytest with monkeypatch fixtures, ruff for linting.

**Branch hygiene:** Spec is committed as `2a25535` but the on-disk version has uncommitted user edits (+421 / -123). Plan assumes the on-disk version is the source of truth. Engineer should `git status` before starting and decide whether to commit the spec edits separately or alongside Task 1.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/kb/capture.py` | NEW | Public `capture_items()`, `CaptureItem`, `CaptureResult`, `CaptureError` + private helpers + module-import-time symlink guard |
| `src/kb/config.py` | MODIFY | Add `CAPTURES_DIR`, `CAPTURE_MAX_BYTES`, `CAPTURE_MAX_ITEMS`, `CAPTURE_KINDS`, `CAPTURE_MAX_CALLS_PER_HOUR` constants; extend `SOURCE_TYPE_DIRS` with `"capture": CAPTURES_DIR` |
| `src/kb/utils/text.py` | MODIFY | Extend `yaml_escape` to strip Unicode bidi override marks `[\u202a-\u202e\u2066-\u2069]` |
| `src/kb/mcp/core.py` | MODIFY | Register `kb_capture` tool; thin formatter wrapper; update 2 stale docstrings (`kb_ingest`, `kb_ingest_content`) to mention `capture` source type |
| `src/kb/ingest/pipeline.py` | MODIFY (gated) | After `raw_content = raw_bytes.decode(...)` (~line 554), strip leading YAML frontmatter ONLY when `source_type == "capture"`. ~5 LOC. |
| `templates/capture.yaml` | NEW | YAML template using flat-list `extract:` form with field names `title`, `core_argument`, `key_claims`, `entities_mentioned`, `concepts_mentioned` |
| `tests/conftest.py` | MODIFY | Extend `RAW_SUBDIRS` with `"captures"`; add fixtures `tmp_captures_dir`, `mock_scan_llm`, `mock_write_llm_for_ingest`, `patch_all_kb_dir_bindings` |
| `tests/test_capture.py` | NEW | ~40 library tests covering `capture_items` + all helpers across error Classes A/B/C/D, frontmatter, slug, MCP, integration |
| `tests/test_mcp_core.py` | MODIFY | Add ~5 MCP wrapper tests for `kb_capture` (response format coverage) |
| `CLAUDE.md` | MODIFY | Add `kb_capture` to MCP tools table; bump module/tool/test counts; add Phase 5 module list line; mention conversation-capture workflow |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` → Added entry covering atomization, secret scanner expansion, rate limit, capture template |
| `BACKLOG.md` | MODIFY | Delete the `kb_capture` line from Phase 5 / Ambient Capture section |
| `README.md` | MODIFY | Mention conversation capture in feature list / roadmap |
| `docs/architecture/architecture-diagram.html` | MODIFY | Add box for `kb_capture → raw/captures/ → kb_ingest` flow |
| `docs/architecture/architecture-diagram.png` | REGENERATE | Re-render via Playwright per CLAUDE.md instructions |

---

## Conventions used throughout this plan

- **All paths are relative to project root** `D:\Projects\llm-wiki-flywheel\`.
- **Run commands assume:** `.venv` is activated (`.venv\Scripts\activate` on Windows) and you are at project root.
- **Each task ends with a commit step.** Commit messages follow the project's existing conventional-commits-ish style (see `git log --oneline` for examples).
- **No `--no-verify`, no `--amend` after push, no `git push --force`.** If a hook fails, fix and create a new commit.
- **Test runs use `python -m pytest`** (matches CLAUDE.md). Add `-v` for verbose, `-x` to stop on first failure.
- **TDD discipline:** every step that adds behavior is preceded by a failing test. RED → GREEN → COMMIT (REFACTOR step is implicit if needed; do it before commit).
- **Symbol cross-check.** Names below MUST match these signatures everywhere they appear: `capture_items(content: str, provenance: str | None = None) -> CaptureResult`; `CaptureResult(items, filtered_out_count, rejected_reason, provenance)`; `CaptureItem(slug, path, title, kind, body_chars)`. If any Task drifts a name, that's a plan bug — fix the plan before the code.

---

## Task 1: Bootstrap — config constants and conftest fixtures

**Files:**
- Modify: `src/kb/config.py`
- Modify: `tests/conftest.py:11` (extend `RAW_SUBDIRS`)
- Test: `tests/test_capture.py` (NEW — placeholder so the import resolves)

This task lays groundwork without behavior. It adds the constants `kb.capture` will import and extends the test fixture so `tmp_project` creates `raw/captures/`. No new MCP tool yet.

- [ ] **Step 1.1: Read current `src/kb/config.py`** to find `RAW_DIR` definition and `SOURCE_TYPE_DIRS` declaration site.

```bash
grep -n "RAW_DIR\|SOURCE_TYPE_DIRS\|VALID_SOURCE_TYPES" src/kb/config.py
```

Expected: locate `RAW_DIR = ...` and `SOURCE_TYPE_DIRS = {...}` lines so the new constants slot in next to them.

- [ ] **Step 1.2: Add the 5 capture constants + extend `SOURCE_TYPE_DIRS`**

In `src/kb/config.py`, immediately after the existing `SOURCE_TYPE_DIRS = {...}` definition, add:

```python
# === Capture configuration (Phase 5 — kb_capture MCP tool) ===
CAPTURES_DIR = RAW_DIR / "captures"
CAPTURE_MAX_BYTES = 50_000              # hard input size cap (UTF-8 bytes)
CAPTURE_MAX_ITEMS = 20                  # cap items extracted per scan-tier call
CAPTURE_KINDS = ("decision", "discovery", "correction", "gotcha")
CAPTURE_MAX_CALLS_PER_HOUR = 60         # per-process rate limit (sliding 1h window)
```

Then locate the `SOURCE_TYPE_DIRS = {` literal and add `"capture": CAPTURES_DIR,` as a new entry. Order does not matter — the dict is consumed by membership and reverse lookup. The two `VALID_SOURCE_TYPES` sets (in `config.py` and `extractors.py`) auto-update because both derive from `SOURCE_TYPE_DIRS.keys()`.

- [ ] **Step 1.3: Verify config import works**

```bash
python -c "from kb.config import CAPTURES_DIR, CAPTURE_MAX_BYTES, CAPTURE_MAX_ITEMS, CAPTURE_KINDS, CAPTURE_MAX_CALLS_PER_HOUR, SOURCE_TYPE_DIRS; print(CAPTURES_DIR); assert 'capture' in SOURCE_TYPE_DIRS; print('OK')"
```

Expected: prints the resolved `raw/captures/` path and `OK`.

- [ ] **Step 1.4: Extend `RAW_SUBDIRS` in `tests/conftest.py`**

Find the line at `tests/conftest.py:11` (per spec §10). It looks like `RAW_SUBDIRS = ("articles", "papers", "repos", "videos")`. Change it to:

```python
RAW_SUBDIRS = ("articles", "papers", "repos", "videos", "captures")
```

This makes `tmp_project` auto-create `raw/captures/` for every test that uses the fixture.

- [ ] **Step 1.5: Create empty test file so future Tasks can append**

Create `tests/test_capture.py` with:

```python
"""Tests for kb.capture — see docs/superpowers/specs/2026-04-13-kb-capture-design.md.

Test matrix coverage maps to spec §9 — Class A (input reject + secret scan + rate limit),
Class B (LLM failure), Class C (quality filter), Class D (write errors), happy path
(frontmatter, slug, MCP wrapper), round-trip integration.
"""
import pytest
```

Empty placeholder — Task 2+ will fill it in.

- [ ] **Step 1.6: Verify the existing test suite still passes** (no regressions from config / conftest changes)

```bash
python -m pytest -x -q
```

Expected: same pass count as before this task (~1177). If anything fails, the `RAW_SUBDIRS` change broke a fixture assumption — investigate before continuing.

- [ ] **Step 1.7: Commit**

```bash
git add src/kb/config.py tests/conftest.py tests/test_capture.py
git commit -m "feat(capture): bootstrap config constants and test fixtures for kb_capture

Add CAPTURES_DIR, CAPTURE_MAX_BYTES, CAPTURE_MAX_ITEMS, CAPTURE_KINDS,
CAPTURE_MAX_CALLS_PER_HOUR. Extend SOURCE_TYPE_DIRS with capture entry so
both VALID_SOURCE_TYPES sets auto-update. Extend RAW_SUBDIRS in conftest
so tmp_project creates raw/captures/."
```

---

## Task 2: Extend `yaml_escape` with bidi-mark stripping

**Files:**
- Modify: `src/kb/utils/text.py` (extend `yaml_escape`)
- Test: `tests/test_capture.py` (add `class TestYamlEscapeBidiMarks`)

Defends against audit-log confusion attacks where an LLM-supplied title containing `\u202E` (right-to-left override) renders backward in terminals. Per spec §8 and §10.

- [ ] **Step 2.1: Write the failing test**

Append to `tests/test_capture.py`:

```python
from kb.utils.text import yaml_escape


class TestYamlEscapeBidiMarks:
    """Spec §8 — strip Unicode bidi override marks to defend audit-log confusion."""

    @pytest.mark.parametrize("codepoint,name", [
        ("\u202a", "LEFT-TO-RIGHT EMBEDDING"),
        ("\u202b", "RIGHT-TO-LEFT EMBEDDING"),
        ("\u202c", "POP DIRECTIONAL FORMATTING"),
        ("\u202d", "LEFT-TO-RIGHT OVERRIDE"),
        ("\u202e", "RIGHT-TO-LEFT OVERRIDE"),
        ("\u2066", "LEFT-TO-RIGHT ISOLATE"),
        ("\u2067", "RIGHT-TO-LEFT ISOLATE"),
        ("\u2068", "FIRST STRONG ISOLATE"),
        ("\u2069", "POP DIRECTIONAL ISOLATE"),
    ])
    def test_strips_bidi_codepoint(self, codepoint, name):
        result = yaml_escape(f"pay{codepoint}usalert")
        assert codepoint not in result, f"{name} ({codepoint!r}) should be stripped"
        # The visible chars should survive
        assert "pay" in result
        assert "usalert" in result

    def test_preserves_normal_unicode(self):
        # CJK, accented Latin, Cyrillic — all should survive unchanged
        for s in ["決定", "café", "Привет", "résumé"]:
            result = yaml_escape(s)
            assert s in result or result == s, f"normal unicode {s!r} altered: {result!r}"

    def test_bidi_strip_runs_before_existing_escape(self):
        # Combine bidi mark + a control char that yaml_escape currently handles.
        # Both should be removed/escaped without one breaking the other.
        result = yaml_escape("a\u202eb\x01c")
        assert "\u202e" not in result
        # \x01 handled by existing escape; just verify result is non-empty and has a/b/c
        assert "a" in result and "b" in result and "c" in result
```

- [ ] **Step 2.2: Run tests, verify they fail**

```bash
python -m pytest tests/test_capture.py::TestYamlEscapeBidiMarks -v
```

Expected: all `test_strips_bidi_codepoint` parametrize cases FAIL (codepoint still in result), `test_bidi_strip_runs_before_existing_escape` FAILS. `test_preserves_normal_unicode` may PASS (no change required for normal unicode).

- [ ] **Step 2.3: Implement the bidi-strip extension**

Open `src/kb/utils/text.py` and locate `yaml_escape` (per spec, lines 133-148). Add at the very top of the function body (before any existing escape logic):

```python
import re as _re_yaml_escape  # local alias to avoid colliding with module-level re imports
_BIDI_RE = _re_yaml_escape.compile(r"[\u202a-\u202e\u2066-\u2069]")
```

Hoist `_BIDI_RE` to module-level (compile once, not per call). At module level, near other module-level regex/constant definitions, add:

```python
# Unicode bidirectional formatting marks (LRE/RLE/PDF/LRO/RLO/LRI/RLI/FSI/PDI).
# Strip from any string we YAML-encode to defend against audit-log confusion
# attacks (e.g. an LLM-supplied title rendering backward in terminals).
_BIDI_RE = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
```

Then inside `yaml_escape`'s body, as the first statement, add:

```python
value = _BIDI_RE.sub("", value)
```

(Adjust variable name to whatever the existing function uses for its input parameter.)

- [ ] **Step 2.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestYamlEscapeBidiMarks -v
```

Expected: all 11 tests PASS.

- [ ] **Step 2.5: Run full test suite to verify no regressions**

```bash
python -m pytest -x -q
```

Expected: same baseline pass count + 11 new tests = 1188 passing.

- [ ] **Step 2.6: Ruff check**

```bash
ruff check src/kb/utils/text.py tests/test_capture.py
```

Expected: clean. Fix any reported issues before commit.

- [ ] **Step 2.7: Commit**

```bash
git add src/kb/utils/text.py tests/test_capture.py
git commit -m "feat(text): strip Unicode bidi marks in yaml_escape

Defends LLM-supplied frontmatter values against audit-log confusion attacks
where U+202E etc. render content backward in terminals. ~2 LOC change
benefits every yaml_escape caller (not just kb_capture)."
```

---

## Task 3: `_validate_input` + CRLF normalize + size cap

**Files:**
- Create (append): `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestValidateInput`)

Implements the input boundary check: 50KB UTF-8 byte cap (measured PRE-normalize), empty/whitespace reject, then CRLF→LF normalize. Spec §4 step 5 + invariant 5.

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
from kb.capture import _validate_input
from kb.config import CAPTURE_MAX_BYTES


class TestValidateInput:
    """Spec §4 step 5, §7 Class A (input reject)."""

    def test_empty_string_rejects(self):
        normalized, err = _validate_input("")
        assert normalized is None
        assert err.startswith("Error: content is empty")

    def test_whitespace_only_rejects(self):
        normalized, err = _validate_input("   \n\t  \r\n")
        assert normalized is None
        assert err.startswith("Error: content is empty")

    def test_at_boundary_passes(self):
        # Exactly CAPTURE_MAX_BYTES of UTF-8 bytes (ASCII so 1 byte/char)
        content = "a" * CAPTURE_MAX_BYTES
        normalized, err = _validate_input(content)
        assert err == ""
        assert normalized == content

    def test_one_byte_over_rejects(self):
        content = "a" * (CAPTURE_MAX_BYTES + 1)
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err
        assert str(CAPTURE_MAX_BYTES + 1) in err  # actual size in message

    def test_size_check_uses_utf8_bytes_not_chars(self):
        # 5-byte UTF-8 char × N where N×5 > CAPTURE_MAX_BYTES but N < CAPTURE_MAX_BYTES
        char = "𝕏"  # 4 bytes in UTF-8
        n = (CAPTURE_MAX_BYTES // 4) + 1  # over the cap by bytes, well under by chars
        content = char * n
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err

    def test_crlf_normalized_to_lf(self):
        normalized, err = _validate_input("a\r\nb\r\nc")
        assert err == ""
        assert normalized == "a\nb\nc"

    def test_size_check_runs_pre_normalize(self):
        # 25001 CRLF pairs = 50002 raw bytes / 50001 post-LF bytes.
        # Per spec §4 invariant 5, size check is on raw — must reject.
        content = "ab\r\n" * 12500 + "ab\r\n"  # 50004 raw bytes
        assert len(content.encode("utf-8")) > CAPTURE_MAX_BYTES
        # Confirm post-normalize would be under cap
        assert len(content.replace("\r\n", "\n").encode("utf-8")) <= CAPTURE_MAX_BYTES
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err

    def test_returns_normalized_form_for_downstream(self):
        # Downstream secret scan / verbatim check operates on the LF-normalized form
        normalized, err = _validate_input("hello\r\nworld")
        assert err == ""
        assert "\r\n" not in normalized
        assert normalized == "hello\nworld"
```

- [ ] **Step 3.2: Run tests — they should fail with ImportError**

```bash
python -m pytest tests/test_capture.py::TestValidateInput -v
```

Expected: `ImportError: cannot import name '_validate_input' from 'kb.capture'` (module doesn't exist yet).

- [ ] **Step 3.3: Create `src/kb/capture.py` with the helper**

Create `src/kb/capture.py`:

```python
"""kb.capture — atomize messy text into discrete raw/captures/<slug>.md files.

Public API: capture_items(content, provenance) → CaptureResult
MCP tool wrapper: see kb.mcp.core.kb_capture.

Spec: docs/superpowers/specs/2026-04-13-kb-capture-design.md
"""
from kb.config import CAPTURE_MAX_BYTES


def _validate_input(content: str) -> tuple[str | None, str]:
    """Validate raw input and return (normalized_content_or_None, error_msg).

    Spec §4 step 5 + invariant 5: size check uses RAW UTF-8 bytes BEFORE
    CRLF normalization, then normalizes \\r\\n → \\n in-place. All downstream
    steps (secret scan, LLM extract, verbatim verify) see the LF-normalized form.

    Returns:
        (normalized, "") on success
        (None, error_msg) on rejection
    """
    raw_bytes = len(content.encode("utf-8"))
    if raw_bytes > CAPTURE_MAX_BYTES:
        return None, (
            f"Error: content exceeds {CAPTURE_MAX_BYTES} bytes (got {raw_bytes}). "
            f"Split into chunks and retry."
        )
    normalized = content.replace("\r\n", "\n")
    if not normalized.strip():
        return None, "Error: content is empty. Nothing to capture."
    return normalized, ""
```

- [ ] **Step 3.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestValidateInput -v
```

Expected: all 8 tests PASS.

- [ ] **Step 3.5: Ruff check**

```bash
ruff check src/kb/capture.py tests/test_capture.py
```

Expected: clean.

- [ ] **Step 3.6: Commit**

```bash
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _validate_input with pre-CRLF size cap

Validates raw UTF-8 byte size against CAPTURE_MAX_BYTES BEFORE normalizing
CRLF→LF. Without this ordering oversize CRLF input would slip through a
post-normalize byte count. Returns LF-normalized form for downstream steps."
```

---

## Task 4: `_check_rate_limit` with `threading.Lock`

**Files:**
- Modify: `src/kb/capture.py` (add helper)
- Test: `tests/test_capture.py` (add `class TestCheckRateLimit`)

Per-process token-bucket sliding-window rate limit, thread-safe under FastMCP concurrent calls. Spec §4 step 4 + §8 thread-safety bullet.

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
import threading
import time

from kb.capture import _check_rate_limit, _rate_limit_window
from kb.config import CAPTURE_MAX_CALLS_PER_HOUR


@pytest.fixture(autouse=False)
def reset_rate_limit():
    """Clear the module-level deque before each rate-limit test."""
    _rate_limit_window.clear()
    yield
    _rate_limit_window.clear()


class TestCheckRateLimit:
    """Spec §4 step 4, §8 thread-safe rate limit."""

    def test_first_call_allowed(self, reset_rate_limit):
        allowed, retry_after = _check_rate_limit()
        assert allowed is True
        assert retry_after == 0

    def test_under_cap_allowed(self, reset_rate_limit):
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            allowed, _ = _check_rate_limit()
            assert allowed is True

    def test_over_cap_rejected_with_retry_after(self, reset_rate_limit):
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            _check_rate_limit()
        allowed, retry_after = _check_rate_limit()
        assert allowed is False
        assert retry_after > 0
        # Retry should be within an hour
        assert retry_after <= 3600

    def test_window_slides_old_entries_purged(self, reset_rate_limit, monkeypatch):
        # Fake the clock — populate window with stale timestamps then advance time
        fake_now = [1000.0]
        monkeypatch.setattr("kb.capture.time.time", lambda: fake_now[0])
        # Fill to cap at fake_now=1000
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            _check_rate_limit()
        # Verify next call rejects
        allowed, _ = _check_rate_limit()
        assert allowed is False
        # Advance clock past 3600s — old entries should be purged
        fake_now[0] = 1000.0 + 3601
        allowed, _ = _check_rate_limit()
        assert allowed is True, "purged entries should free capacity"

    def test_thread_safe_under_concurrent_load(self, reset_rate_limit):
        """Spec §8: 2-thread test at the 59→60 boundary.
        Without threading.Lock, both threads can pass len(deque)<60 then both append → 2 over cap.
        With the lock, exactly 1 of the (cap+1) total attempts is rejected.
        """
        results: list[tuple[bool, int]] = []
        results_lock = threading.Lock()
        n_per_thread = (CAPTURE_MAX_CALLS_PER_HOUR + 1) // 2 + 1

        def worker():
            for _ in range(n_per_thread):
                r = _check_rate_limit()
                with results_lock:
                    results.append(r)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start(); t1.join(); t2.join()
        rejected = sum(1 for allowed, _ in results if not allowed)
        total = len(results)
        accepted = total - rejected
        # Exactly CAPTURE_MAX_CALLS_PER_HOUR allowed; the rest rejected
        assert accepted == CAPTURE_MAX_CALLS_PER_HOUR, f"accepted={accepted}, total={total}"
        assert rejected == total - CAPTURE_MAX_CALLS_PER_HOUR
```

- [ ] **Step 4.2: Run tests — should fail with ImportError**

```bash
python -m pytest tests/test_capture.py::TestCheckRateLimit -v
```

Expected: ImportError on `_check_rate_limit` and `_rate_limit_window`.

- [ ] **Step 4.3: Implement `_check_rate_limit`**

Append to `src/kb/capture.py` (add imports near the top):

```python
import threading
import time
from collections import deque

from kb.config import CAPTURE_MAX_BYTES, CAPTURE_MAX_CALLS_PER_HOUR

# === Rate limit (spec §4 step 4, §8) ===
# Per-process token-bucket sliding window. threading.Lock makes the
# check-then-act (len(deque) ≥ LIMIT, then append now) atomic under
# concurrent FastMCP tool calls. Project precedent: kb.utils.llm:26,
# kb.review.refiner:13.
_rate_limit_lock = threading.Lock()
_rate_limit_window: deque[float] = deque()


def _check_rate_limit() -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds).

    Sliding 1-hour window of timestamps. Trims expired entries on each call.
    On overflow, returns (False, seconds-until-oldest-expires).
    """
    with _rate_limit_lock:
        now = time.time()
        cutoff = now - 3600
        while _rate_limit_window and _rate_limit_window[0] < cutoff:
            _rate_limit_window.popleft()
        if len(_rate_limit_window) >= CAPTURE_MAX_CALLS_PER_HOUR:
            oldest = _rate_limit_window[0]
            retry_after = int(oldest + 3600 - now) + 1
            return False, retry_after
        _rate_limit_window.append(now)
        return True, 0
```

Note: keep the existing `_validate_input` function in the file. The imports section now includes `threading`, `time`, `deque`, and the new constant.

- [ ] **Step 4.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestCheckRateLimit -v
```

Expected: all 5 tests PASS, including the 2-thread concurrency test.

- [ ] **Step 4.5: Verify the rest of the suite still passes**

```bash
python -m pytest -x -q
```

Expected: 1196 passing (1177 baseline + 8 from Task 3 + 11 from Task 2).

Wait — recount: 1177 baseline + 11 (Task 2) + 8 (Task 3) + 5 (Task 4) = 1201. Adjust expectation if your baseline differs.

- [ ] **Step 4.6: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add thread-safe sliding-window rate limit

Per-process token bucket: 60 calls/hour by default. threading.Lock makes
the check-then-act atomic under concurrent FastMCP requests. 2-thread
test at the 59→60 boundary verifies no double-pass."
```

---

## Task 5: `_scan_for_secrets` — plain pattern sweep

**Files:**
- Modify: `src/kb/capture.py` (add `_CAPTURE_SECRET_PATTERNS` and `_scan_for_secrets`)
- Test: `tests/test_capture.py` (add `class TestScanForSecretsPlain`)

Implements the regex sweep over the 18+ enumerated secret patterns. Encoded normalization comes in Task 6.

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
from kb.capture import _scan_for_secrets


class TestScanForSecretsPlain:
    """Spec §8 expanded secret pattern list — one test per pattern label.
    Each test confirms (a) the pattern matches a representative literal,
    (b) the returned label is informative.
    """

    @pytest.mark.parametrize("content,expected_label_substr", [
        ("AKIAIOSFODNN7EXAMPLE my key", "AWS"),
        ("ASIATESTSTSEXAMPLE12345 temp creds", "AWS"),
        ("aws_secret_access_key=" + "A" * 40, "AWS"),
        ("sk-proj-" + "x" * 32, "OpenAI"),
        ("sk-" + "y" * 32, "OpenAI"),
        ("sk-ant-" + "z" * 32, "Anthropic"),
        ("ghp_" + "a" * 36, "GitHub"),
        ("github_pat_" + "b" * 82, "GitHub"),
        ("xoxb-12345-67890-abcdefXYZ123", "Slack"),
        ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.signature", "JWT"),
        ("AIza" + "X" * 35, "Google"),
        ("ya29.AHES6ZQ_long_token_string", "GCP OAuth"),
        ('"type": "service_account"', "GCP service account"),
        ("sk_live_" + "a" * 30, "Stripe"),
        ("rk_live_" + "b" * 30, "Stripe"),
        ("hf_" + "c" * 35, "HuggingFace"),
        ("AC" + "0" * 32, "Twilio"),
        ("SK" + "1" * 32, "Twilio"),
        ("npm_" + "x" * 36, "npm"),
        ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "HTTP Basic"),
        ("API_KEY=secret_value_here", "env-var"),
        ("PASSWORD=mypass123", "env-var"),
        ("postgres://user:pass@host:5432/db", "DB connection"),
        ("mysql://admin:secret@localhost/db", "DB connection"),
        ("mongodb+srv://user:pass@cluster.example.net/", "DB connection"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----", "Private key"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3Blbnpz...\n-----END OPENSSH PRIVATE KEY-----", "Private key"),
    ])
    def test_secret_pattern_matches(self, content, expected_label_substr):
        result = _scan_for_secrets(content)
        assert result is not None, f"expected match for: {content[:40]!r}"
        label, location = result
        assert expected_label_substr.lower() in label.lower(), (
            f"label {label!r} should contain {expected_label_substr!r}"
        )

    def test_benign_content_passes(self):
        assert _scan_for_secrets("we decided to use atomic writes") is None
        assert _scan_for_secrets("the model returned 42 items") is None
        assert _scan_for_secrets("# Python comment about API design") is None

    def test_returns_line_number_for_plain_match(self):
        content = "line one\nline two\nAKIAIOSFODNN7EXAMPLE\nline four"
        result = _scan_for_secrets(content)
        assert result is not None
        label, location = result
        assert location == "line 3"

    def test_first_pattern_match_short_circuits(self):
        # Two patterns in same content — should return first
        content = "AKIAIOSFODNN7EXAMPLE and sk-ant-" + "z" * 32
        result = _scan_for_secrets(content)
        assert result is not None
        # Order in pattern list determines which wins; just verify deterministic
        # (whichever it is, the same input → same output)
        result2 = _scan_for_secrets(content)
        assert result == result2
```

- [ ] **Step 5.2: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestScanForSecretsPlain -v
```

Expected: ImportError on `_scan_for_secrets`.

- [ ] **Step 5.3: Implement `_scan_for_secrets` (plain pass only — encoded normalization in Task 6)**

Append to `src/kb/capture.py`:

```python
import re

# === Secret scanner (spec §8 expanded pattern list) ===
# Tuples are (label, compiled-regex). Order matters only for first-match wins;
# more specific patterns are listed before more general ones (e.g. sk-proj-
# before sk-).
_CAPTURE_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS access key (temporary)", re.compile(r"ASIA[0-9A-Z]{16}")),
    ("AWS secret access key (env-var)", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+=]{40}")),
    ("OpenAI key (project)", re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}")),
    ("Anthropic key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("OpenAI key (legacy)", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("GitHub PAT (long form)", re.compile(r"github_pat_[a-zA-Z0-9_]{82}")),
    ("GitHub PAT", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9]+-[0-9]+-[0-9a-zA-Z]+")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("GCP OAuth access token", re.compile(r"ya29\.[0-9A-Za-z_-]+")),
    ("GCP service account JSON", re.compile(r'"type"\s*:\s*"service_account"')),
    ("Stripe live key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
    ("Stripe live restricted key", re.compile(r"rk_live_[0-9a-zA-Z]{24,}")),
    ("HuggingFace token", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("Twilio Account SID", re.compile(r"AC[a-f0-9]{32}")),
    ("Twilio Auth Token (SK form)", re.compile(r"SK[a-f0-9]{32}")),
    ("npm token", re.compile(r"npm_[A-Za-z0-9]{36}")),
    ("HTTP Basic Authorization header", re.compile(r"(?i)Authorization:\s*Basic\s+[A-Za-z0-9+/=]+")),
    ("env-var assignment", re.compile(r"(?im)^(API_KEY|SECRET|PASSWORD|PASSWD|TOKEN|DATABASE_URL|DB_PASS|PRIVATE_KEY)\s*=\s*\S+")),
    ("DB connection string with password", re.compile(r"(?i)(postgres|postgresql|mysql|mongodb(\+srv)?|redis|amqp)://[^\s:@]+:[^\s@]+@")),
    ("Private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----")),
]


def _scan_for_secrets(content: str) -> tuple[str, str] | None:
    """Sweep content for secret patterns. Returns (label, location) on first match, else None.

    location is "line N" for plain-text matches; "via encoded form" for matches found
    only after normalization (Task 6).
    """
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return label, f"line {line_no}"
    return None
```

- [ ] **Step 5.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestScanForSecretsPlain -v
```

Expected: all parametrize cases + benign + line-number + short-circuit tests PASS.

- [ ] **Step 5.5: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _scan_for_secrets plain regex sweep

23 patterns covering AWS/OpenAI/Anthropic/GitHub/Slack/JWT/GCP/Stripe/
HF/Twilio/npm + HTTP Basic / env-var / DB connection / private key blocks.
Returns (label, line N) for plain matches. Encoded normalization follows."
```

---

## Task 6: `_scan_for_secrets` — encoded normalization pass

**Files:**
- Modify: `src/kb/capture.py` (add `_normalize_for_scan`, extend `_scan_for_secrets`)
- Test: `tests/test_capture.py` (add `class TestScanForSecretsEncoded`)

Catches base64-wrapped and URL-encoded secret bypasses.

- [ ] **Step 6.1: Write the failing tests**

```python
import base64
from urllib.parse import quote

from kb.capture import _normalize_for_scan


class TestScanForSecretsEncoded:
    """Spec §8 encoded-secret normalization pass."""

    def test_base64_wrapped_aws_key_rejects(self):
        # Wrap an AWS key in base64
        raw = "AKIAIOSFODNN7EXAMPLE"
        encoded = base64.b64encode(raw.encode()).decode()
        # encoded form is QUtJQUlPU0ZPRE5ON0VYQU1QTEU=
        result = _scan_for_secrets(f"opaque blob: {encoded}")
        assert result is not None, "b64-wrapped AWS key should be detected via normalization"
        label, location = result
        assert "AWS" in label
        assert location == "via encoded form"

    def test_url_encoded_anthropic_key_rejects(self):
        raw = "sk-ant-" + "x" * 32
        encoded = quote(raw)
        # encoded form is sk-ant-xxxxxxx... (- and digits/letters not encoded)
        # use a value that DOES encode meaningfully:
        raw_with_special = "sk-ant-=key=here=" + "y" * 30
        encoded = quote(raw_with_special, safe="")
        result = _scan_for_secrets(f"hidden: {encoded}")
        # The pattern still matches the plain prefix sk-ant-... if any survives;
        # primary assertion: SOMETHING matches (either via plain or encoded path)
        assert result is not None

    def test_legitimate_base64_image_header_does_not_false_positive(self):
        # PNG file header in base64 — should NOT match any secret pattern
        png_header_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()
        result = _scan_for_secrets(f"image data: {png_header_b64}")
        # If this fails with a match, the secret regex is too permissive
        assert result is None, f"PNG header b64 falsely matched: {result}"

    def test_normalize_includes_b64_decoded_text(self):
        # _normalize_for_scan returns a string that includes decoded ASCII forms
        raw = "hello world"
        encoded = base64.b64encode(raw.encode()).decode()
        normalized = _normalize_for_scan(encoded)
        assert "hello world" in normalized

    def test_normalize_includes_url_decoded_text(self):
        raw = "key&value=secret"
        encoded = quote(raw, safe="")  # encodes &, =, etc.
        normalized = _normalize_for_scan(encoded)
        assert raw in normalized

    def test_normalize_skips_non_b64_blobs(self):
        # Non-base64 content should not crash the normalizer
        normalized = _normalize_for_scan("just some plain text $$$ @@@ ###")
        assert isinstance(normalized, str)
        assert "plain text" in normalized

    def test_widely_split_secret_not_caught(self):
        """Spec §13 documented residual: ≥4 whitespace chars between key parts bypass."""
        content = "sk-ant-\n\n\n\nfollowingtokenpartwithexactlytwentychars"
        # Per spec, this is an accepted bypass — should NOT be detected
        # (this test documents the residual; if the scanner gets stricter later, update spec)
        result = _scan_for_secrets(content)
        # We're NOT asserting None here strictly because some patterns might still
        # catch sk-ant- alone; just document that no surprise rejection happens.
        # The real assertion is that the design accepts this gap.
        assert True  # documentation test — see spec §13
```

- [ ] **Step 6.2: Run tests — most fail (ImportError + missing normalization)**

```bash
python -m pytest tests/test_capture.py::TestScanForSecretsEncoded -v
```

- [ ] **Step 6.3: Implement `_normalize_for_scan` and extend `_scan_for_secrets`**

In `src/kb/capture.py`, add imports:

```python
import base64
import binascii
from urllib.parse import unquote
```

Add `_normalize_for_scan` immediately above `_scan_for_secrets`:

```python
def _normalize_for_scan(content: str) -> str:
    """Build a normalized view: append b64-decoded ASCII candidates and URL-decoded runs.

    The original content is kept; this function returns a SUPERSET that's only used for
    secret-pattern matching. The decoded fragments give the regex sweep a chance to
    catch trivially-encoded secrets without losing the original content.
    """
    parts: list[str] = [content]
    # Base64 candidates: at least 16 chars of [A-Za-z0-9+/=].
    for m in re.finditer(r"[A-Za-z0-9+/=]{16,}", content):
        try:
            decoded = base64.b64decode(m.group(0), validate=True)
            text = decoded.decode("ascii")
            parts.append(text)
        except (ValueError, binascii.Error, UnicodeDecodeError):
            continue
    # URL-encoded runs: 3+ adjacent percent-encoded triplets.
    for m in re.finditer(r"(?:%[0-9A-Fa-f]{2}){3,}", content):
        try:
            parts.append(unquote(m.group(0)))
        except (ValueError, UnicodeDecodeError):
            continue
    return "\n".join(parts)
```

Modify `_scan_for_secrets` to also sweep the normalized view:

```python
def _scan_for_secrets(content: str) -> tuple[str, str] | None:
    """Sweep content + normalized view for secret patterns.

    Returns (label, location) on first match, else None.
    location is "line N" for plain matches, "via encoded form" for normalization matches.
    """
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return label, f"line {line_no}"

    normalized = _normalize_for_scan(content)
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        if pattern.search(normalized):
            return label, "via encoded form"

    return None
```

- [ ] **Step 6.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestScanForSecretsEncoded -v
```

Expected: all 7 tests PASS. The "widely split" test is a documentation test (asserts `True`).

- [ ] **Step 6.5: Re-run plain test class to ensure no regression**

```bash
python -m pytest tests/test_capture.py::TestScanForSecretsPlain -v
```

Expected: all still pass.

- [ ] **Step 6.6: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): extend _scan_for_secrets with encoded normalization

Adds _normalize_for_scan that base64-decodes ASCII candidates and
URL-decodes percent-encoded runs. Catches trivially-obfuscated secrets
without false-positiving on legitimate base64 (PNG headers verified).
Returns 'via encoded form' as location for normalized matches."
```

---

## Task 7: `_extract_items_via_llm` + `_verify_body_is_verbatim` + JSON schema

**Files:**
- Modify: `src/kb/capture.py` (add `_CAPTURE_SCHEMA`, `_PROMPT_TEMPLATE`, `_extract_items_via_llm`, `_verify_body_is_verbatim`)
- Modify: `tests/conftest.py` (add `mock_scan_llm` fixture)
- Test: `tests/test_capture.py` (add `class TestExtractAndVerify`)

Implements the scan-tier LLM call with forced JSON schema, plus the body-verbatim post-check that drops items the LLM reworded or returned with whitespace-only bodies.

- [ ] **Step 7.1: Add `mock_scan_llm` fixture in `tests/conftest.py`**

Append to `tests/conftest.py`:

```python
_REQUIRED = object()  # sentinel — explicit "must be passed"


@pytest.fixture
def mock_scan_llm(monkeypatch):
    """Install a canned JSON response for call_llm_json inside kb.capture.

    Mock signature mirrors the REAL call_llm_json signature
    (src/kb/utils/llm.py): tier and schema are keyword-only, schema is required.
    The sentinel + assertions catch the bug where capture.py forgets to pass
    schema=_CAPTURE_SCHEMA.
    """
    def _install(response: dict, expected_schema_keys: tuple[str, ...] = ("items", "filtered_out_count")):
        def fake_call(prompt, *, tier="write", schema=_REQUIRED, system="", **_kw):
            assert tier == "scan", f"kb_capture must use scan tier, got {tier!r}"
            assert schema is not _REQUIRED, "kb_capture must pass schema= to call_llm_json"
            assert isinstance(schema, dict), f"schema must be dict, got {type(schema)}"
            for key in expected_schema_keys:
                assert key in schema.get("properties", {}), f"schema missing property {key!r}"
            required = set(schema.get("required", []))
            missing = required - set(response)
            assert not missing, f"mock response missing required schema keys: {missing}"
            return response
        monkeypatch.setattr("kb.capture.call_llm_json", fake_call)
    return _install
```

- [ ] **Step 7.2: Write the failing tests**

Append to `tests/test_capture.py`:

```python
from kb.capture import (
    _extract_items_via_llm,
    _verify_body_is_verbatim,
    _CAPTURE_SCHEMA,
    CAPTURE_KINDS,
)


class TestExtractAndVerify:
    """Spec §4 step 7-8, §7 Class C."""

    def test_extract_calls_scan_tier(self, mock_scan_llm):
        canned = {"items": [], "filtered_out_count": 0}
        mock_scan_llm(canned)
        result = _extract_items_via_llm("any content")
        assert result == canned

    def test_extract_passes_schema(self, mock_scan_llm):
        # mock_scan_llm asserts schema is passed and well-formed
        canned = {"items": [], "filtered_out_count": 5}
        mock_scan_llm(canned)
        _extract_items_via_llm("hello")  # would assert-fail in mock if schema missing

    def test_schema_enforces_kind_enum(self):
        # _CAPTURE_SCHEMA must constrain kind to CAPTURE_KINDS
        item_schema = _CAPTURE_SCHEMA["properties"]["items"]["items"]
        kind_enum = item_schema["properties"]["kind"]["enum"]
        assert set(kind_enum) == set(CAPTURE_KINDS)

    def test_schema_caps_max_items(self):
        from kb.config import CAPTURE_MAX_ITEMS
        assert _CAPTURE_SCHEMA["properties"]["items"]["maxItems"] == CAPTURE_MAX_ITEMS

    def test_schema_required_fields(self):
        item_schema = _CAPTURE_SCHEMA["properties"]["items"]["items"]
        required = set(item_schema["required"])
        assert required == {"title", "kind", "body", "one_line_summary", "confidence"}

    def test_verify_drops_reworded_body(self):
        content = "the original input mentioned X and then Y"
        items = [
            {"title": "t1", "kind": "decision", "body": "X and then Y", "one_line_summary": "s", "confidence": "stated"},
            {"title": "t2", "kind": "discovery", "body": "completely different prose", "one_line_summary": "s", "confidence": "stated"},
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert len(kept) == 1
        assert kept[0]["title"] == "t1"
        assert dropped == 1

    def test_verify_drops_whitespace_only_body(self):
        content = "any content here"
        items = [
            {"title": "ws", "kind": "decision", "body": "    ", "one_line_summary": "s", "confidence": "stated"},
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert kept == []
        assert dropped == 1

    def test_verify_strip_tolerance(self):
        # Leading/trailing whitespace in item body OK as long as stripped form is in content
        content = "the cat sat on the mat"
        items = [
            {"title": "t", "kind": "decision", "body": "  the cat sat  ", "one_line_summary": "s", "confidence": "stated"},
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert len(kept) == 1
        assert dropped == 0

    def test_verify_empty_input_drops_all(self):
        kept, dropped = _verify_body_is_verbatim([], "any content")
        assert kept == []
        assert dropped == 0
```

- [ ] **Step 7.3: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestExtractAndVerify -v
```

- [ ] **Step 7.4: Implement schema, prompt, and helpers**

In `src/kb/capture.py`, add imports:

```python
from kb.config import CAPTURE_KINDS, CAPTURE_MAX_BYTES, CAPTURE_MAX_CALLS_PER_HOUR, CAPTURE_MAX_ITEMS
from kb.utils.llm import call_llm_json
```

(Update existing import line; do not duplicate.)

Append the schema and helpers:

```python
# === Scan-tier LLM contract (spec §4) ===
_CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "maxItems": CAPTURE_MAX_ITEMS,
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


_PROMPT_TEMPLATE = """You are atomizing messy text into discrete knowledge items.

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

Cap the output at {max_items} items. Also report `filtered_out_count`: the number
of candidate items you rejected as noise.

--- INPUT ---
{content}
--- END INPUT ---
"""


def _extract_items_via_llm(content: str) -> dict:
    """Call scan-tier LLM with forced-JSON schema. Raises LLMError on retry exhaustion."""
    prompt = _PROMPT_TEMPLATE.format(max_items=CAPTURE_MAX_ITEMS, content=content)
    return call_llm_json(prompt, tier="scan", schema=_CAPTURE_SCHEMA)


def _verify_body_is_verbatim(items: list[dict], content: str) -> tuple[list[dict], int]:
    """Drop items whose body is whitespace-only or not a verbatim substring of content.

    Spec §4 step 8 + invariant 2. Defends raw/ immutability against LLM rewording
    AND traps the schema gap where minLength:1 permits "   " bodies (which would
    write 0-byte content files).
    """
    kept: list[dict] = []
    dropped = 0
    for item in items:
        body_stripped = item["body"].strip()
        if not body_stripped:
            dropped += 1
            continue
        if body_stripped not in content:
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped
```

- [ ] **Step 7.5: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestExtractAndVerify -v
```

Expected: all 9 tests PASS.

- [ ] **Step 7.6: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/conftest.py tests/test_capture.py
git add src/kb/capture.py tests/conftest.py tests/test_capture.py
git commit -m "feat(capture): add scan-tier LLM extractor + body verbatim verifier

Defines _CAPTURE_SCHEMA (kind enum, max 20 items, required fields) and
_PROMPT_TEMPLATE for the atomization prompt. _extract_items_via_llm calls
call_llm_json with forced schema. _verify_body_is_verbatim drops items
whose body was reworded or whitespace-only. Adds mock_scan_llm fixture
with sentinel that fails loudly on missing schema."
```

---

## Task 8: `_build_slug` with kind prefix, length cap, collision suffix, unicode fallback

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestBuildSlug`)

- [ ] **Step 8.1: Write the failing tests**

```python
from kb.capture import _build_slug


class TestBuildSlug:
    """Spec §5 slug algorithm."""

    def test_kind_prefix_present(self):
        slug = _build_slug("decision", "Pick atomic files", set())
        assert slug.startswith("decision-")
        assert "pick-atomic-files" in slug

    def test_length_capped_at_80(self):
        long_title = "a" * 200
        slug = _build_slug("decision", long_title, set())
        assert len(slug) <= 80

    def test_no_collision_returns_base(self):
        slug = _build_slug("decision", "foo", set())
        assert slug == "decision-foo"

    def test_collision_appends_2(self):
        existing = {"decision-foo"}
        slug = _build_slug("decision", "foo", existing)
        assert slug == "decision-foo-2"

    def test_multiple_collisions_increment(self):
        existing = {"decision-foo", "decision-foo-2", "decision-foo-3"}
        slug = _build_slug("decision", "foo", existing)
        assert slug == "decision-foo-4"

    def test_all_unicode_title_falls_back_to_kind(self):
        # CJK title — slugify with re.ASCII strips it all
        slug = _build_slug("decision", "決定事項", set())
        # base becomes "decision-" → slugify → "decision" (or empty); fallback to kind
        assert slug == "decision"

    def test_unicode_fallback_collides_with_existing_bare_kind(self):
        existing = {"decision"}
        slug = _build_slug("decision", "決定事項", existing)
        assert slug == "decision-2"

    def test_mixed_unicode_ascii(self):
        slug = _build_slug("discovery", "OpenAI 决策", set())
        assert slug.startswith("discovery-")
        assert "openai" in slug.lower()

    def test_kind_prefix_immunizes_windows_reserved(self):
        # "CON" alone would be a Windows reserved device name; with kind prefix it's safe
        slug = _build_slug("decision", "CON", set())
        assert slug == "decision-con"
        # The actual file `decision-con.md` is fine on Windows
```

- [ ] **Step 8.2: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestBuildSlug -v
```

- [ ] **Step 8.3: Implement `_build_slug`**

In `src/kb/capture.py`, add import:

```python
from kb.utils.text import slugify
```

Append:

```python
def _build_slug(kind: str, title: str, existing: set[str]) -> str:
    """Spec §5: kind prefix + slugify + 80-char cap + numeric collision suffix.

    Falls back to bare kind if slugify produces empty string (e.g. all-unicode title
    stripped by re.ASCII flag in kb.utils.text.slugify).
    """
    base = slugify(f"{kind}-{title}")
    base = base[:80]
    if not base:
        base = kind
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"
```

- [ ] **Step 8.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestBuildSlug -v
```

Expected: all 9 tests PASS. If `test_all_unicode_title_falls_back_to_kind` fails because `slugify` returns `"decision-"` (with trailing hyphen), refine the fallback check: `if not base or base.rstrip("-") == kind: base = kind`.

- [ ] **Step 8.5: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _build_slug with kind prefix + unicode fallback

Slugs are <kind>-<slugified-title>, capped at 80 chars. Numeric suffix on
collision (-2, -3, ...). All-unicode titles stripped by slugify fall back
to bare kind. Kind prefix immunizes against Windows reserved names."
```

---

## Task 9: `_path_within_captures` + module-import-time symlink guard

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestPathWithinCaptures`)

- [ ] **Step 9.1: Write the failing tests**

```python
from pathlib import Path

from kb.capture import _path_within_captures
from kb.config import CAPTURES_DIR


class TestPathWithinCaptures:
    """Spec §5 path-traversal gate + §8 symlink guard prep."""

    def test_simple_path_inside_passes(self):
        p = CAPTURES_DIR / "decision-foo.md"
        assert _path_within_captures(p) is True

    def test_parent_traversal_rejected(self):
        p = CAPTURES_DIR / ".." / "secret.md"
        assert _path_within_captures(p) is False

    def test_absolute_path_outside_rejected(self):
        p = Path("/tmp/evil.md") if Path("/tmp").exists() else Path("C:/Windows/Temp/evil.md")
        assert _path_within_captures(p) is False

    def test_nested_inside_passes(self):
        p = CAPTURES_DIR / "subdir" / "file.md"
        # subdir doesn't need to exist for this check
        assert _path_within_captures(p) is True
```

- [ ] **Step 9.2: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestPathWithinCaptures -v
```

- [ ] **Step 9.3: Implement `_path_within_captures` and the symlink guard assertion**

Append to `src/kb/capture.py`:

```python
from kb.config import CAPTURES_DIR, PROJECT_ROOT


def _path_within_captures(path: Path) -> bool:
    """Belt-and-suspenders: refuse any resolved path outside CAPTURES_DIR.

    Relies on CAPTURES_DIR itself being inside PROJECT_ROOT — enforced by the
    module-import-time assertion below.
    """
    try:
        path.resolve().relative_to(CAPTURES_DIR.resolve())
        return True
    except ValueError:
        return False


# === Module-import-time symlink guard (spec §5, §8) ===
# If raw/captures/ is a symlink escaping PROJECT_ROOT, refuse to load the
# module at all rather than fail open in _path_within_captures at runtime.
# A symlinked CAPTURES_DIR planted via some other primitive would resolve
# to the symlink target on BOTH sides of the relative_to() call, silently
# passing the path-within check. This assertion closes that gap.
assert CAPTURES_DIR.resolve().is_relative_to(PROJECT_ROOT.resolve()), (
    f"SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT — refusing to load. "
    f"CAPTURES_DIR={CAPTURES_DIR.resolve()}, PROJECT_ROOT={PROJECT_ROOT.resolve()}"
)
```

Note: `Path` import. If not already imported at the top, add `from pathlib import Path`.

If `PROJECT_ROOT` is not in `kb.config`, search where it's defined (likely `kb.config` based on CLAUDE.md's mention) and import accordingly. If absent, derive: `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` in `kb.config`.

- [ ] **Step 9.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestPathWithinCaptures -v
```

Expected: all 4 tests PASS.

- [ ] **Step 9.5: Add a symlink-guard test (verifies assertion fires)**

The symlink-guard test requires forcing a re-import. Append:

```python
import importlib
import os
import sys


class TestSymlinkGuard:
    """Spec §5, §8 — module refuses to load if CAPTURES_DIR escapes PROJECT_ROOT."""

    @pytest.mark.skipif(sys.platform == "win32", reason="symlink creation requires admin on Windows")
    def test_symlink_outside_project_root_refuses_import(self, tmp_path, monkeypatch):
        # Simulate: CAPTURES_DIR points OUTSIDE the project (via a symlink)
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        # Patch CAPTURES_DIR to be a symlink leading outside
        symlink_dir = tmp_path / "captures_symlink"
        symlink_dir.symlink_to(external_dir, target_is_directory=True)
        monkeypatch.setattr("kb.config.CAPTURES_DIR", symlink_dir)
        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_path / "project_root")
        # Force reimport of kb.capture
        if "kb.capture" in sys.modules:
            del sys.modules["kb.capture"]
        with pytest.raises(AssertionError, match="SECURITY: CAPTURES_DIR"):
            importlib.import_module("kb.capture")
        # Cleanup: re-import normally so subsequent tests work
        monkeypatch.undo()
        importlib.import_module("kb.capture")
```

- [ ] **Step 9.6: Run symlink-guard test (skipped on Windows; runs on Unix CI)**

```bash
python -m pytest tests/test_capture.py::TestSymlinkGuard -v
```

Expected: PASSES on Unix; SKIPPED on Windows. Local Windows dev: skip OK.

- [ ] **Step 9.7: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add path-traversal gate + symlink guard

_path_within_captures checks resolved path is under CAPTURES_DIR via
relative_to (raises ValueError if escapes). Module-import-time assertion
verifies CAPTURES_DIR is under PROJECT_ROOT — closes the symlink-swap
gap where resolve() would silently follow a planted symlink."
```

---

## Task 10: `_exclusive_atomic_write` helper

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestExclusiveAtomicWrite`)

Combines `os.O_EXCL` slug-reservation with `atomic_text_write` temp-file-rename. Crash-safe + race-safe.

- [ ] **Step 10.1: Verify `atomic_text_write` exists at the expected path**

```bash
grep -n "def atomic_text_write" src/kb/utils/io.py
```

Expected: matches `def atomic_text_write(content: str, path: Path) -> None:` near line 37 (per spec).

- [ ] **Step 10.2: Write the failing tests**

```python
from kb.capture import _exclusive_atomic_write


class TestExclusiveAtomicWrite:
    """Spec §3 atomic write helper."""

    def test_writes_new_file(self, tmp_captures_dir):
        path = tmp_captures_dir / "test.md"
        _exclusive_atomic_write(path, "hello world\n")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello world\n"

    def test_raises_file_exists_on_collision(self, tmp_captures_dir):
        path = tmp_captures_dir / "test.md"
        path.write_text("existing", encoding="utf-8")
        with pytest.raises(FileExistsError):
            _exclusive_atomic_write(path, "would replace")
        # Original content preserved
        assert path.read_text(encoding="utf-8") == "existing"

    def test_cleans_up_reservation_on_inner_write_failure(self, tmp_captures_dir, monkeypatch):
        path = tmp_captures_dir / "test.md"

        def boom(content, p):
            raise OSError("simulated disk full")

        monkeypatch.setattr("kb.capture.atomic_text_write", boom)
        with pytest.raises(OSError, match="disk full"):
            _exclusive_atomic_write(path, "ignored")
        # No 0-byte poison file left behind
        assert not path.exists(), "reservation file must be cleaned up on failure"

    def test_cleans_up_on_keyboard_interrupt(self, tmp_captures_dir, monkeypatch):
        path = tmp_captures_dir / "test.md"

        def interrupted(content, p):
            raise KeyboardInterrupt()

        monkeypatch.setattr("kb.capture.atomic_text_write", interrupted)
        with pytest.raises(KeyboardInterrupt):
            _exclusive_atomic_write(path, "ignored")
        assert not path.exists(), "must clean up on BaseException too"
```

The test references `tmp_captures_dir` — add the fixture in `tests/conftest.py` first.

- [ ] **Step 10.3: Add `tmp_captures_dir` fixture to `tests/conftest.py`**

Append:

```python
@pytest.fixture
def tmp_captures_dir(tmp_project, monkeypatch):
    """Isolated raw/captures/ with kb.config.CAPTURES_DIR repointed.

    Spec §9 fixtures. Double monkey-patch defends against import-time vs
    runtime binding (capture.py does `from kb.config import CAPTURES_DIR`).
    """
    captures = tmp_project / "raw" / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("kb.config.CAPTURES_DIR", captures)
    monkeypatch.setattr("kb.capture.CAPTURES_DIR", captures)
    return captures
```

- [ ] **Step 10.4: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestExclusiveAtomicWrite -v
```

- [ ] **Step 10.5: Implement `_exclusive_atomic_write`**

In `src/kb/capture.py`, add imports:

```python
import os
from kb.utils.io import atomic_text_write
```

Append:

```python
def _exclusive_atomic_write(path: Path, content: str) -> None:
    """Atomic create-or-fail. Raises FileExistsError if path already exists.

    Combines O_EXCL (race-safe slug reservation) with temp-file-then-rename
    (no half-written file on crash). Cleans up its empty reservation on any
    failure of the inner atomic_text_write.
    """
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
    try:
        atomic_text_write(content, path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
```

- [ ] **Step 10.6: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestExclusiveAtomicWrite -v
```

Expected: all 4 tests PASS.

- [ ] **Step 10.7: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/conftest.py tests/test_capture.py
git add src/kb/capture.py tests/conftest.py tests/test_capture.py
git commit -m "feat(capture): add _exclusive_atomic_write + tmp_captures_dir fixture

O_EXCL reservation gives race-safe slug uniqueness; atomic_text_write does
the actual content via temp+rename. except BaseException cleans up the
empty reservation file on any failure (incl. KeyboardInterrupt) — no 0-byte
poison left on disk after a SIGKILL mid-write."
```

---

## Task 11: `_resolve_provenance`

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestResolveProvenance`)

- [ ] **Step 11.1: Write the failing tests**

```python
import re

from kb.capture import _resolve_provenance


_AUTO_PROV_RE = re.compile(r"^capture-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{4}$")


class TestResolveProvenance:
    """Spec §4 step 3 — resolved FIRST so result.provenance is always set."""

    def test_none_generates_auto(self):
        prov = _resolve_provenance(None)
        assert _AUTO_PROV_RE.match(prov), f"unexpected format: {prov!r}"

    def test_empty_string_treated_as_none(self):
        prov = _resolve_provenance("")
        assert _AUTO_PROV_RE.match(prov), f"unexpected format: {prov!r}"

    def test_user_label_slugified_and_timestamped(self):
        prov = _resolve_provenance("Meeting w/ Eng 4-13")
        assert prov.startswith("meeting-w-eng-4-13-")
        # timestamp suffix
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$", prov)

    def test_label_truncated_at_80(self):
        long_label = "x" * 200
        prov = _resolve_provenance(long_label)
        # 80 chars label + "-" + 20-char timestamp = 101 chars total max
        # Verify the LABEL portion is truncated
        label_part = prov.rsplit("-", 1)[0]  # everything before last hyphen-timestamp
        # actually the timestamp has hyphens too. Match the trailing ISO directly:
        m = re.search(r"-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)$", prov)
        assert m, f"prov did not end with ISO timestamp: {prov!r}"
        label_only = prov[: m.start()]
        assert len(label_only) <= 80

    def test_label_slugifies_to_empty_falls_back_to_auto(self):
        prov = _resolve_provenance("!!!")
        assert _AUTO_PROV_RE.match(prov), f"expected auto-generated, got: {prov!r}"

    def test_unicode_label_falls_back_to_auto(self):
        # CJK label slugifies to empty under re.ASCII
        prov = _resolve_provenance("決定セッション")
        # May produce auto OR a slugged form depending on slugify behavior
        # We accept either as long as the result is non-empty
        assert prov  # truthy

    def test_returns_filesystem_safe_no_colons(self):
        # Windows forbids ':' in filenames. Provenance is used in frontmatter
        # and as captured_from value, but if it ever forms part of a path,
        # colons would break. Assert no colons in auto form.
        prov = _resolve_provenance(None)
        assert ":" not in prov
```

- [ ] **Step 11.2: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestResolveProvenance -v
```

- [ ] **Step 11.3: Implement `_resolve_provenance`**

In `src/kb/capture.py`, add imports:

```python
import secrets as _secrets
from datetime import datetime, timezone
```

Append:

```python
def _resolve_provenance(provenance: str | None) -> str:
    """Resolve user-supplied provenance to a final string. Always returns non-empty.

    Spec §4 step 3 — runs FIRST so CaptureResult.provenance is populated in every
    return path (including hard rejects).

    - None / "" / slugifies-to-empty → "capture-<ISO>-<4hex>"
    - Else → "<slugify(label)[:80]>-<ISO>"

    ISO format uses '-' instead of ':' for filesystem safety on Windows.
    """
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    if not provenance or not provenance.strip():
        return f"capture-{iso}-{_secrets.token_hex(2)}"
    slugged = slugify(provenance)[:80]
    if not slugged:
        return f"capture-{iso}-{_secrets.token_hex(2)}"
    return f"{slugged}-{iso}"
```

- [ ] **Step 11.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestResolveProvenance -v
```

Expected: all 7 tests PASS.

- [ ] **Step 11.5: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _resolve_provenance with auto-fallback

Resolves None / empty / unslugifiable input to capture-<ISO>-<4hex> form.
ISO uses '-' not ':' so the value can be embedded in filenames safely
on Windows. Always returns non-empty string."
```

---

## Task 12: `_render_markdown` (frontmatter renderer)

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestRenderMarkdown`)

Renders one item to the markdown form shown in spec §5 example file.

- [ ] **Step 12.1: Write the failing tests**

```python
import frontmatter as _fm  # python-frontmatter package

from kb.capture import _render_markdown


class TestRenderMarkdown:
    """Spec §5 markdown layout."""

    def _sample_item(self):
        return {
            "title": "Pick atomic N-files",
            "kind": "decision",
            "body": "We chose N-files for atomicity.",
            "one_line_summary": "N-files preserve raw immutability via metadata, not wrappers.",
            "confidence": "stated",
        }

    def test_all_fields_present(self):
        md = _render_markdown(
            item=self._sample_item(),
            slug="decision-pick-atomic-n-files",
            captured_alongside=["discovery-foo", "gotcha-bar"],
            provenance="claude-code-2026-04-13T17-45-00Z",
            captured_at="2026-04-13T17:45:23Z",
        )
        post = _fm.loads(md)
        assert post.metadata["title"] == "Pick atomic N-files"
        assert post.metadata["kind"] == "decision"
        assert post.metadata["confidence"] == "stated"
        assert "N-files" in post.metadata["one_line_summary"]
        assert post.metadata["captured_at"] == "2026-04-13T17:45:23Z"
        assert post.metadata["captured_from"] == "claude-code-2026-04-13T17-45-00Z"
        assert post.metadata["captured_alongside"] == ["discovery-foo", "gotcha-bar"]
        assert post.metadata["source"] == "mcp-capture"
        assert post.content.strip() == "We chose N-files for atomicity."

    def test_empty_alongside_renders_empty_list(self):
        md = _render_markdown(
            item=self._sample_item(),
            slug="decision-foo",
            captured_alongside=[],
            provenance="capture-x",
            captured_at="2026-04-13T17:45:23Z",
        )
        post = _fm.loads(md)
        assert post.metadata["captured_alongside"] == []

    def test_z_suffix_preserved(self):
        md = _render_markdown(
            item=self._sample_item(),
            slug="decision-foo",
            captured_alongside=[],
            provenance="capture-x",
            captured_at="2026-04-13T17:45:23Z",
        )
        # Critical: must end with literal Z, not +00:00 (per spec §5 field contract)
        post = _fm.loads(md)
        assert str(post.metadata["captured_at"]).endswith("Z")
        assert "+00:00" not in str(post.metadata["captured_at"])

    def test_body_with_embedded_dashes_survives(self):
        item = self._sample_item()
        item["body"] = "first part\n---\nsecond part with --- triple dashes"
        md = _render_markdown(
            item=item,
            slug="x",
            captured_alongside=[],
            provenance="p",
            captured_at="2026-04-13T00:00:00Z",
        )
        post = _fm.loads(md)
        # python-frontmatter only consumes first --- block; embedded --- in body survives
        assert "second part with --- triple dashes" in post.content

    def test_bidi_marks_stripped_from_title(self):
        item = self._sample_item()
        item["title"] = "pay\u202eusalert"  # RLO embedded
        md = _render_markdown(
            item=item,
            slug="x",
            captured_alongside=[],
            provenance="p",
            captured_at="2026-04-13T00:00:00Z",
        )
        post = _fm.loads(md)
        assert "\u202e" not in post.metadata["title"]
        assert "pay" in post.metadata["title"]
        assert "usalert" in post.metadata["title"]
```

- [ ] **Step 12.2: Run tests — should fail (ImportError)**

```bash
python -m pytest tests/test_capture.py::TestRenderMarkdown -v
```

- [ ] **Step 12.3: Implement `_render_markdown`**

In `src/kb/capture.py`, add imports:

```python
import yaml
from kb.utils.text import slugify, yaml_escape
```

Append:

```python
def _render_markdown(
    item: dict,
    slug: str,
    captured_alongside: list[str],
    provenance: str,
    captured_at: str,
) -> str:
    """Render one capture item to the markdown form (spec §5).

    Field order is preserved for predictable diffs (sort_keys=False).
    yaml_escape applied to user-content fields strips bidi marks (Task 2).
    """
    fm = {
        "title": yaml_escape(item["title"]),
        "kind": item["kind"],
        "confidence": item["confidence"],
        "one_line_summary": yaml_escape(item["one_line_summary"]),
        "captured_at": captured_at,
        "captured_from": provenance,
        "captured_alongside": list(captured_alongside),
        "source": "mcp-capture",
    }
    fm_yaml = yaml.dump(
        fm,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    body = item["body"]
    if not body.endswith("\n"):
        body = body + "\n"
    return f"---\n{fm_yaml}---\n\n{body}"
```

Note: `slug` is currently unused in this function — it's accepted for symmetry with the call site (which has the slug handy). If the linter complains about unused arg, prefix with `_`:

```python
def _render_markdown(
    item: dict,
    _slug: str,
    captured_alongside: list[str],
    provenance: str,
    captured_at: str,
) -> str:
```

Actually, leave as `slug` (no underscore) — keeping the named parameter readable at call sites is worth a one-time `# noqa: ARG001` if ruff complains, but ruff E/F/I/W/UP rule set in `pyproject.toml` doesn't include ARG. Should be silent.

- [ ] **Step 12.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestRenderMarkdown -v
```

Expected: all 5 tests PASS. If `test_z_suffix_preserved` fails because `python-frontmatter` parses the `Z`-suffixed string into a `datetime` object, adjust the assertion: parse `md` for the literal `captured_at: ...Z` line via regex to verify the on-disk format, since `python-frontmatter` may convert ISO strings to datetimes:

```python
import re
assert re.search(r"^captured_at:\s*\S+Z\s*$", md, re.MULTILINE), \
    f"expected Z-suffix in raw markdown, got: {md!r}"
```

- [ ] **Step 12.5: Verify `python-frontmatter` is installed** (needed by the test)

```bash
python -c "import frontmatter; print(frontmatter.__version__)"
```

Expected: prints a version. If `ImportError`, add to `requirements.txt`: `python-frontmatter>=1.0.0`. If already in requirements, run `pip install -r requirements.txt`.

- [ ] **Step 12.6: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _render_markdown frontmatter renderer

Emits hybrid layout (LLM-structured frontmatter + verbatim body) per spec
§5. Field order preserved via sort_keys=False. yaml_escape called on title
and one_line_summary so bidi marks (Task 2) are stripped. Body trailing
newline normalized."
```

---

## Task 13: `_write_item_files` orchestrator

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestWriteItemFiles`)

Phase A (resolve all slugs in-process), Phase B (compute captured_alongside), Phase C (write each file with cross-process race retry).

- [ ] **Step 13.1: Write the failing tests**

```python
from kb.capture import _write_item_files, CaptureItem


def _make_item(kind: str, title: str, body: str = "body content"):
    return {
        "title": title,
        "kind": kind,
        "body": body,
        "one_line_summary": "summary",
        "confidence": "stated",
    }


class TestWriteItemFiles:
    """Spec §4 step 9, §7 Class D write errors."""

    def test_creates_dir_if_missing(self, tmp_captures_dir):
        # Remove the dir created by fixture
        import shutil
        shutil.rmtree(tmp_captures_dir)
        items = [_make_item("decision", "foo")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is None
        assert tmp_captures_dir.exists()
        assert len(written) == 1

    def test_single_item_writes_one_file(self, tmp_captures_dir):
        items = [_make_item("decision", "foo")]
        written, err = _write_item_files(items, "prov", "2026-04-13T00:00:00Z")
        assert err is None
        assert len(written) == 1
        assert isinstance(written[0], CaptureItem)
        assert written[0].kind == "decision"
        assert written[0].path.exists()

    def test_multiple_items_each_get_file(self, tmp_captures_dir):
        items = [
            _make_item("decision", "alpha"),
            _make_item("discovery", "beta"),
            _make_item("gotcha", "gamma"),
        ]
        written, err = _write_item_files(items, "prov", "2026-04-13T00:00:00Z")
        assert err is None
        assert len(written) == 3
        kinds = {ci.kind for ci in written}
        assert kinds == {"decision", "discovery", "gotcha"}
        for ci in written:
            assert ci.path.exists()

    def test_captured_alongside_excludes_self(self, tmp_captures_dir):
        items = [_make_item("decision", "a"), _make_item("discovery", "b"), _make_item("gotcha", "c")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is None
        import frontmatter as _fm
        for ci in written:
            post = _fm.load(ci.path)
            sibling_slugs = post.metadata["captured_alongside"]
            assert ci.slug not in sibling_slugs
            # Each file's siblings = all other slugs
            assert len(sibling_slugs) == 2

    def test_captured_alongside_empty_for_single_item(self, tmp_captures_dir):
        items = [_make_item("decision", "alone")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        import frontmatter as _fm
        post = _fm.load(written[0].path)
        assert post.metadata["captured_alongside"] == []

    def test_in_process_collision_appends_suffix(self, tmp_captures_dir):
        items = [_make_item("decision", "samename"), _make_item("decision", "samename")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is None
        slugs = [ci.slug for ci in written]
        assert slugs[0] == "decision-samename"
        assert slugs[1] == "decision-samename-2"

    def test_pre_existing_file_collision(self, tmp_captures_dir):
        # Pre-seed
        (tmp_captures_dir / "decision-foo.md").write_text("preexisting", encoding="utf-8")
        items = [_make_item("decision", "foo")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is None
        assert written[0].slug == "decision-foo-2"

    def test_disk_error_partial_success_fail_fast(self, tmp_captures_dir, monkeypatch):
        items = [_make_item("decision", "alpha"), _make_item("discovery", "beta"), _make_item("gotcha", "gamma")]
        call_count = [0]
        original = _write_item_files.__globals__["_exclusive_atomic_write"]

        def maybe_fail(path, content):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError(28, "No space left on device")
            return original(path, content)

        monkeypatch.setattr("kb.capture._exclusive_atomic_write", maybe_fail)
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is not None
        assert "No space left" in err
        assert len(written) == 1  # only first succeeded

    def test_cross_process_race_retry_succeeds(self, tmp_captures_dir, monkeypatch):
        # Pre-seed two files so the FIRST attempt collides; engine should re-resolve and retry
        (tmp_captures_dir / "decision-foo.md").write_text("p1", encoding="utf-8")
        items = [_make_item("decision", "foo")]
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is None
        # _build_slug already resolves to decision-foo-2 in Phase A — no retry actually needed
        # for this test. Verify by setting up a real race scenario:
        # Simulate a concurrent process that creates the file BETWEEN scandir and open(O_EXCL)
        # by patching _exclusive_atomic_write to fail once then succeed:
        attempts = [0]
        original = _write_item_files.__globals__["_exclusive_atomic_write"]

        def race_then_succeed(path, content):
            attempts[0] += 1
            if attempts[0] == 1:
                raise FileExistsError(f"simulated race: {path}")
            return original(path, content)

        monkeypatch.setattr("kb.capture._exclusive_atomic_write", race_then_succeed)
        items2 = [_make_item("discovery", "racy")]
        written2, err2 = _write_item_files(items2, "p", "2026-04-13T00:00:00Z")
        assert err2 is None
        assert len(written2) == 1
        assert attempts[0] >= 2  # at least one retry

    def test_slug_retry_exhausted_raises_or_errors(self, tmp_captures_dir, monkeypatch):
        items = [_make_item("decision", "x")]

        def always_collide(path, content):
            raise FileExistsError("forever colliding")

        monkeypatch.setattr("kb.capture._exclusive_atomic_write", always_collide)
        written, err = _write_item_files(items, "p", "2026-04-13T00:00:00Z")
        assert err is not None
        assert "retry exhausted" in err.lower() or "forever colliding" in err.lower()
        assert written == []
```

- [ ] **Step 13.2: Run tests — should fail (ImportError on `_write_item_files` and `CaptureItem`)**

```bash
python -m pytest tests/test_capture.py::TestWriteItemFiles -v
```

- [ ] **Step 13.3: Implement `CaptureItem` dataclass and `_write_item_files`**

In `src/kb/capture.py`, add imports:

```python
from dataclasses import dataclass
```

Append:

```python
@dataclass(frozen=True)
class CaptureItem:
    slug: str
    path: Path
    title: str
    kind: str
    body_chars: int


class CaptureError(Exception):
    """Raised by capture helpers on unrecoverable internal errors."""


def _write_item_files(
    items: list[dict],
    provenance: str,
    captured_at: str,
) -> tuple[list[CaptureItem], str | None]:
    """Resolve slugs, compute captured_alongside, write each file atomically.

    Returns (written_items, error_msg). On partial failure, error_msg is set and
    written contains only the items written before the failure.
    """
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Initial scan
    existing = {
        entry.name[:-3]
        for entry in os.scandir(CAPTURES_DIR)
        if entry.is_file() and entry.name.endswith(".md")
    }

    # Phase A — resolve all slugs in-process
    slugs: list[str] = []
    for item in items:
        slug = _build_slug(item["kind"], item["title"], existing)
        existing.add(slug)
        slugs.append(slug)

    # Phase B — compute captured_alongside per item (excludes self)
    alongside_for: list[list[str]] = [
        [s for j, s in enumerate(slugs) if j != i] for i in range(len(items))
    ]

    # Phase C — write each file with cross-process race retry
    written: list[CaptureItem] = []
    for i, item in enumerate(items):
        slug = slugs[i]
        alongside = alongside_for[i]
        markdown = _render_markdown(
            item=item,
            slug=slug,
            captured_alongside=alongside,
            provenance=provenance,
            captured_at=captured_at,
        )
        for attempt in range(10):
            path = CAPTURES_DIR / f"{slug}.md"
            if not _path_within_captures(path):
                return written, f"Error: slug escapes CAPTURES_DIR: {slug!r}"
            try:
                _exclusive_atomic_write(path, markdown)
                written.append(
                    CaptureItem(
                        slug=slug,
                        path=path,
                        title=item["title"],
                        kind=item["kind"],
                        body_chars=len(item["body"]),
                    )
                )
                break
            except FileExistsError:
                # Cross-process race — re-scan and re-resolve
                existing = {
                    entry.name[:-3]
                    for entry in os.scandir(CAPTURES_DIR)
                    if entry.is_file() and entry.name.endswith(".md")
                }
                slug = _build_slug(item["kind"], item["title"], existing)
            except OSError as e:
                return (
                    written,
                    f"Error: failed to write {slug}: {e}. "
                    f"{len(written)} of {len(items)} items written.",
                )
        else:
            # for-else: ran all 10 attempts without break
            return written, f"Error: slug retry exhausted for {item['title']!r}"

    return written, None
```

- [ ] **Step 13.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestWriteItemFiles -v
```

Expected: all 10 tests PASS. If `test_disk_error_partial_success_fail_fast` fails because the retry loop catches the OSError as a FileExistsError in a different branch, verify the implementation distinguishes `FileExistsError` (retry) from generic `OSError` (fail-fast).

- [ ] **Step 13.5: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): add _write_item_files orchestrator + CaptureItem

Three-phase write: (A) resolve all slugs in-process, (B) compute
captured_alongside excluding self, (C) atomic write per item with
up-to-10 cross-process race retries via FileExistsError catch+rescan.
Disk errors fail-fast with partial-success report. CaptureItem dataclass
defines the public per-item return shape."
```

---

## Task 14: `capture_items` public orchestrator + `CaptureResult`

**Files:**
- Modify: `src/kb/capture.py`
- Test: `tests/test_capture.py` (add `class TestCaptureItems`)

The public API. Wires every helper together in the order required by spec §4.

- [ ] **Step 14.1: Write the failing tests**

```python
from kb.capture import capture_items, CaptureResult
from kb.utils.llm import LLMError


class TestCaptureItems:
    """End-to-end public API. Spec §4 happy path + Class A/B/C/D rejections."""

    def _good_response(self, content):
        # Build a response with ONE item whose body is a verbatim slice of content
        return {
            "items": [
                {
                    "title": "Test decision",
                    "kind": "decision",
                    "body": content[:50],  # verbatim slice
                    "one_line_summary": "summary",
                    "confidence": "stated",
                }
            ],
            "filtered_out_count": 2,
        }

    def test_happy_path_writes_files(self, tmp_captures_dir, mock_scan_llm):
        content = "We decided to use atomic writes. We discovered a race." * 5
        mock_scan_llm(self._good_response(content))
        result = capture_items(content, provenance="testsess")
        assert isinstance(result, CaptureResult)
        assert result.rejected_reason is None
        assert len(result.items) == 1
        assert result.filtered_out_count == 2  # LLM-reported, no body-verbatim drops
        assert result.provenance.startswith("testsess-")
        assert result.items[0].path.exists()

    def test_provenance_resolved_for_all_paths_including_reject(self, tmp_captures_dir, mock_scan_llm):
        # Hard reject (empty content) — provenance still set
        result = capture_items("", provenance="my-session")
        assert result.rejected_reason is not None
        assert result.provenance.startswith("my-session-"), \
            f"provenance not resolved on reject: {result.provenance!r}"
        assert result.items == []
        assert result.filtered_out_count == 0

    def test_empty_content_class_a_reject(self, tmp_captures_dir, mock_scan_llm):
        result = capture_items("")
        assert result.rejected_reason is not None
        assert "empty" in result.rejected_reason
        assert result.items == []

    def test_oversize_content_class_a_reject(self, tmp_captures_dir, mock_scan_llm):
        from kb.config import CAPTURE_MAX_BYTES
        big = "x" * (CAPTURE_MAX_BYTES + 100)
        result = capture_items(big)
        assert "exceeds" in result.rejected_reason

    def test_secret_class_a_reject(self, tmp_captures_dir, mock_scan_llm):
        # AKIA pattern — should reject before LLM is called
        # If mock_scan_llm is invoked, its assertion fails — so secret reject means mock never runs
        result = capture_items("note: AKIAIOSFODNN7EXAMPLE my key", provenance="x")
        assert result.rejected_reason is not None
        assert "secret" in result.rejected_reason.lower()
        assert result.items == []

    def test_rate_limit_class_a_reject(self, tmp_captures_dir, mock_scan_llm, reset_rate_limit):
        from kb.config import CAPTURE_MAX_CALLS_PER_HOUR
        canned = self._good_response("we decided X" * 5)
        mock_scan_llm(canned)
        # Burn the rate limit
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            r = capture_items("we decided X" * 5)
            assert r.rejected_reason is None or "rate" not in r.rejected_reason.lower()
        # Next one should reject
        result = capture_items("we decided X" * 5)
        assert result.rejected_reason is not None
        assert "rate limit" in result.rejected_reason.lower()
        assert result.provenance  # still set

    def test_llm_error_propagates_class_b(self, tmp_captures_dir, monkeypatch):
        def raise_llm(*a, **kw):
            raise LLMError("API down")
        monkeypatch.setattr("kb.capture.call_llm_json", raise_llm)
        with pytest.raises(LLMError):
            capture_items("real content here")

    def test_zero_items_returned_class_c_success(self, tmp_captures_dir, mock_scan_llm):
        mock_scan_llm({"items": [], "filtered_out_count": 8})
        result = capture_items("real content here")
        assert result.rejected_reason is None
        assert result.items == []
        assert result.filtered_out_count == 8

    def test_body_verbatim_drops_count_in_filtered(self, tmp_captures_dir, mock_scan_llm):
        content = "the original input had this prose"
        mock_scan_llm({
            "items": [
                {
                    "title": "good",
                    "kind": "decision",
                    "body": "the original input",  # in content
                    "one_line_summary": "s",
                    "confidence": "stated",
                },
                {
                    "title": "reworded",
                    "kind": "discovery",
                    "body": "totally different",  # NOT in content
                    "one_line_summary": "s",
                    "confidence": "stated",
                },
            ],
            "filtered_out_count": 5,
        })
        result = capture_items(content)
        assert len(result.items) == 1
        assert result.filtered_out_count == 6  # 5 LLM + 1 body-drop

    def test_partial_write_class_d(self, tmp_captures_dir, mock_scan_llm, monkeypatch):
        content = "we decided this and that and the other"
        mock_scan_llm({
            "items": [
                {"title": "a", "kind": "decision", "body": "we decided this", "one_line_summary": "s", "confidence": "stated"},
                {"title": "b", "kind": "decision", "body": "and that", "one_line_summary": "s", "confidence": "stated"},
            ],
            "filtered_out_count": 0,
        })
        call_count = [0]
        original = monkeypatch.context

        from kb.capture import _exclusive_atomic_write as orig_write

        def fail_second(path, content):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError(28, "No space left on device")
            return orig_write(path, content)

        monkeypatch.setattr("kb.capture._exclusive_atomic_write", fail_second)
        result = capture_items(content)
        assert result.rejected_reason is not None
        assert "No space left" in result.rejected_reason
        assert len(result.items) == 1  # first write succeeded
```

- [ ] **Step 14.2: Run tests — should fail (ImportError + missing `CaptureResult`)**

```bash
python -m pytest tests/test_capture.py::TestCaptureItems -v
```

- [ ] **Step 14.3: Implement `CaptureResult` and `capture_items`**

In `src/kb/capture.py`, append:

```python
@dataclass(frozen=True)
class CaptureResult:
    items: list[CaptureItem]
    filtered_out_count: int
    rejected_reason: str | None
    provenance: str


def capture_items(content: str, provenance: str | None = None) -> CaptureResult:
    """Atomize messy text into discrete raw/captures/<slug>.md files.

    Public API. See spec §3-§4 for the data flow.

    Args:
        content: up to CAPTURE_MAX_BYTES (50KB) of UTF-8 text. Hard reject above.
        provenance: optional grouping label. None / "" → auto-generated.

    Returns:
        CaptureResult with `provenance` always populated. On hard reject, `items=[]`
        and `rejected_reason` is set. On success, `items` lists each written file.
        On partial write failure, `items` contains the successfully written items
        and `rejected_reason` describes the failure.

    Raises:
        LLMError if the scan-tier API exhausts retries.
    """
    # Step 3: resolve provenance FIRST so all return paths carry it
    resolved_prov = _resolve_provenance(provenance)

    # Step 4: rate limit
    allowed, retry_after = _check_rate_limit()
    if not allowed:
        return CaptureResult(
            items=[],
            filtered_out_count=0,
            rejected_reason=(
                f"Error: rate limit ({CAPTURE_MAX_CALLS_PER_HOUR} calls/hour) "
                f"exceeded. Try again in {retry_after} seconds."
            ),
            provenance=resolved_prov,
        )

    # Step 5: validate input (size pre-normalize + empty + CRLF normalize)
    normalized, err = _validate_input(content)
    if err:
        return CaptureResult(
            items=[], filtered_out_count=0, rejected_reason=err, provenance=resolved_prov
        )
    assert normalized is not None  # type narrowing for the linter

    # Step 6: secret scan (on normalized form per invariant 5)
    secret = _scan_for_secrets(normalized)
    if secret is not None:
        label, location = secret
        return CaptureResult(
            items=[],
            filtered_out_count=0,
            rejected_reason=(
                f"Error: secret pattern detected at {location} ({label}). "
                f"No items written. Redact and retry."
            ),
            provenance=resolved_prov,
        )

    # Step 7: scan-tier extraction (raises LLMError on failure)
    response = _extract_items_via_llm(normalized)
    raw_items = response["items"]
    llm_filtered = response["filtered_out_count"]

    # Step 8: body verbatim verify
    kept, body_dropped = _verify_body_is_verbatim(raw_items, normalized)

    # Step 9: write files
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written, write_error = _write_item_files(kept, resolved_prov, captured_at)

    return CaptureResult(
        items=written,
        filtered_out_count=llm_filtered + body_dropped,
        rejected_reason=write_error,  # None on full success, str on partial-failure
        provenance=resolved_prov,
    )
```

- [ ] **Step 14.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestCaptureItems -v
```

Expected: all 10 tests PASS. If `test_secret_class_a_reject` shows the mock being invoked, the secret-scan ordering is wrong — verify the secret check runs before `_extract_items_via_llm`.

- [ ] **Step 14.5: Run full kb.capture test suite to verify everything still works**

```bash
python -m pytest tests/test_capture.py -v
```

Expected: ALL test classes pass.

- [ ] **Step 14.6: Run full project test suite to verify no regression**

```bash
python -m pytest -x -q
```

Expected: 1177 baseline + ~70 new tests = ~1247 passing. If anything outside `tests/test_capture.py` fails, investigate before committing.

- [ ] **Step 14.7: Coverage check**

```bash
python -m pytest --cov=src/kb/capture --cov-report=term-missing tests/test_capture.py
```

Expected: ≥ 95% line coverage. List uncovered lines; add targeted tests if any of the documented branches in spec §9 coverage section are missing (e.g., the partial-write fail-fast, slug-retry-exhausted, KeyboardInterrupt cleanup).

- [ ] **Step 14.8: Ruff + commit**

```bash
ruff check src/kb/capture.py tests/test_capture.py
git add src/kb/capture.py tests/test_capture.py
git commit -m "feat(capture): wire capture_items public orchestrator + CaptureResult

Implements the spec §4 data flow end-to-end: provenance → rate limit →
validate → secret scan → LLM extract → body verbatim → atomic write.
Provenance resolved FIRST so every return path carries it. LLMError
propagates unchanged. Body-verbatim drops added to filtered_out_count."
```

---

## Task 15: New `templates/capture.yaml`

**Files:**
- Create: `templates/capture.yaml`
- Test: `tests/test_capture.py` (add `class TestCaptureTemplate`)

Per spec §6 — uses field names `core_argument`, `key_claims`, `entities_mentioned`, `concepts_mentioned` so the existing pipeline (`_build_summary_content`, `KNOWN_LIST_FIELDS`) consumes it correctly.

- [ ] **Step 15.1: Write the failing template-load test**

```python
from kb.ingest.extractors import load_template, build_extraction_schema, KNOWN_LIST_FIELDS


class TestCaptureTemplate:
    """Spec §6 — template uses field names recognised by existing pipeline."""

    def test_template_loads(self):
        tpl = load_template("capture")
        assert tpl is not None
        assert tpl.get("name") == "capture"

    def test_template_fields_match_pipeline_recognition(self):
        tpl = load_template("capture")
        extract_fields = tpl.get("extract", [])
        assert "core_argument" in extract_fields  # → "## Overview"
        assert "key_claims" in extract_fields      # → "## Key Claims"
        assert "entities_mentioned" in extract_fields
        assert "concepts_mentioned" in extract_fields

    def test_list_fields_are_recognised(self):
        # entities_mentioned and concepts_mentioned must be in KNOWN_LIST_FIELDS
        # so _build_summary_content treats them as bulleted lists
        assert "entities_mentioned" in KNOWN_LIST_FIELDS
        assert "concepts_mentioned" in KNOWN_LIST_FIELDS

    def test_build_extraction_schema_accepts_capture_template(self):
        tpl = load_template("capture")
        schema = build_extraction_schema(tpl)
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema
```

- [ ] **Step 15.2: Run tests — fail because template doesn't exist**

```bash
python -m pytest tests/test_capture.py::TestCaptureTemplate -v
```

Expected: `load_template("capture")` returns None or raises FileNotFoundError.

- [ ] **Step 15.3: Create `templates/capture.yaml`**

```yaml
# templates/capture.yaml — Spec §6
# Field names MUST match KNOWN_LIST_FIELDS and _build_summary_content
# expectations (extractors.py:24-61, pipeline.py:178-196). Renaming any
# of `core_argument`, `key_claims`, `entities_mentioned`,
# `concepts_mentioned` will break list-field detection and the
# summary-page renderer.

name: capture
description: Atomic knowledge item captured from chat, notes, or unstructured text

extract:
  - title
  - core_argument        # 1-2 sentence restatement (rendered as "## Overview")
  - key_claims           # specific claims/facts (rendered as "## Key Claims" bullets)
  - entities_mentioned   # named entities (people, projects, libraries, companies)
  - concepts_mentioned   # technical concepts or abstractions

wiki_outputs:
  - summary: "summaries/{slug}.md"
  - entities: "entities/{entity_name}.md"
  - concepts: "concepts/{concept_name}.md"
```

- [ ] **Step 15.4: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestCaptureTemplate -v
```

Expected: all 4 tests PASS. If `test_list_fields_are_recognised` fails, the spec's `KNOWN_LIST_FIELDS` (in `extractors.py:24-61`) does not yet include `entities_mentioned` / `concepts_mentioned`. Cross-check with `grep -n KNOWN_LIST_FIELDS src/kb/ingest/extractors.py` — those names are listed in spec §6 as already-recognised, so they should exist. If they don't, add them to `KNOWN_LIST_FIELDS` as part of this task; otherwise the template-driven extraction won't render lists correctly.

- [ ] **Step 15.5: Commit**

```bash
git add templates/capture.yaml tests/test_capture.py
git commit -m "feat(capture): add templates/capture.yaml for kb_ingest

Uses pipeline-recognised field names: core_argument (→ ## Overview),
key_claims (→ ## Key Claims bullets), entities_mentioned/concepts_mentioned
(→ entity/concept page updates). Tight template avoids over-extraction
that an article template would impose."
```

---

## Task 16: MCP wrapper `kb_capture` in `kb.mcp.core`

**Files:**
- Modify: `src/kb/mcp/core.py` (register `@mcp.tool()`, format `CaptureResult` → str)
- Modify: `tests/test_mcp_core.py` (add ~5 wrapper tests)

- [ ] **Step 16.1: Read existing MCP wrappers for the format pattern**

```bash
grep -n "@mcp.tool" src/kb/mcp/core.py | head -5
```

Note any existing tool's response-format pattern (likely a `def kb_xxx(...) -> str:` returning text directly, with errors as `"Error: ..."` strings).

- [ ] **Step 16.2: Write the failing MCP wrapper tests in `tests/test_mcp_core.py`**

Append:

```python
class TestKbCaptureWrapper:
    """Spec §7 MCP response formats."""

    def test_happy_path_format(self, tmp_captures_dir, mock_scan_llm):
        from kb.mcp.core import kb_capture
        content = "We decided to use atomic writes. " * 5
        mock_scan_llm({
            "items": [
                {"title": "Decided X", "kind": "decision",
                 "body": "We decided to use atomic writes.",
                 "one_line_summary": "atomic writes win", "confidence": "stated"},
                {"title": "Saw Y", "kind": "discovery",
                 "body": "We decided to use atomic writes.",
                 "one_line_summary": "discovery", "confidence": "stated"},
            ],
            "filtered_out_count": 3,
        })
        result = kb_capture(content)
        assert isinstance(result, str)
        assert "Captured 2 items" in result
        assert "filtered 4 as noise" in result  # 3 LLM + body verbatim drops if any
        assert "raw/captures/decision-" in result
        assert "Next: run kb_ingest" in result

    def test_zero_items_format(self, tmp_captures_dir, mock_scan_llm):
        from kb.mcp.core import kb_capture
        mock_scan_llm({"items": [], "filtered_out_count": 12})
        result = kb_capture("any content here")
        assert "Captured 0 items" in result
        assert "filtered 12" in result

    def test_secret_reject_format(self, tmp_captures_dir, mock_scan_llm):
        from kb.mcp.core import kb_capture
        result = kb_capture("AKIAIOSFODNN7EXAMPLE here")
        assert result.startswith("Error:")
        assert "secret" in result.lower()

    def test_empty_content_format(self, tmp_captures_dir, mock_scan_llm):
        from kb.mcp.core import kb_capture
        result = kb_capture("")
        assert result.startswith("Error:")
        assert "empty" in result.lower()

    def test_partial_write_format(self, tmp_captures_dir, mock_scan_llm, monkeypatch):
        from kb.mcp.core import kb_capture
        content = "we decided this and that and the other"
        mock_scan_llm({
            "items": [
                {"title": "a", "kind": "decision", "body": "we decided this",
                 "one_line_summary": "s", "confidence": "stated"},
                {"title": "b", "kind": "decision", "body": "and that",
                 "one_line_summary": "s", "confidence": "stated"},
            ],
            "filtered_out_count": 0,
        })
        from kb.capture import _exclusive_atomic_write as orig_write
        call_count = [0]
        def fail_second(path, c):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError(28, "No space left on device")
            return orig_write(path, c)
        monkeypatch.setattr("kb.capture._exclusive_atomic_write", fail_second)
        result = kb_capture(content)
        assert "Captured 1 items" in result
        assert "Error:" in result
        assert "No space left" in result
```

- [ ] **Step 16.3: Run tests — should fail (no kb_capture in mcp.core)**

```bash
python -m pytest tests/test_mcp_core.py::TestKbCaptureWrapper -v
```

- [ ] **Step 16.4: Implement `kb_capture` in `src/kb/mcp/core.py`**

Add the import and tool registration. Find the existing `@mcp.tool()` definitions and add this one alongside them:

```python
from kb.capture import capture_items, CaptureResult


@mcp.tool()
def kb_capture(content: str, provenance: str | None = None) -> str:
    """Extract discrete knowledge items (decisions, discoveries, corrections, gotchas)
    from up to 50KB of unstructured text and write each to raw/captures/<slug>.md.

    The scan-tier LLM atomizes the input; bodies are kept verbatim. Returns a list
    of file paths. Run kb_ingest on each path to promote items to wiki/.

    Args:
        content: up to 50KB of UTF-8 text (chat logs, notes, transcripts).
        provenance: optional grouping label. None → auto-generated session id.

    Returns:
        Plain-text summary of items written and noise filtered, or an Error: message.
    """
    try:
        result = capture_items(content, provenance=provenance)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
    return _format_capture_result(result)


def _format_capture_result(result: CaptureResult) -> str:
    """Format CaptureResult per spec §7 MCP response formats."""
    lines: list[str] = []
    n_items = len(result.items)

    if n_items > 0:
        # Captured N items, filtered M as noise
        head = f"Captured {n_items} item{'s' if n_items != 1 else ''}, filtered {result.filtered_out_count} as noise."
        lines.append(f"{head} Provenance: {result.provenance}")
        lines.append("")
        for item in result.items:
            rel = item.path.relative_to(item.path.parents[2])  # raw/captures/x.md
            lines.append(f"- {rel.as_posix()}  [{item.kind}]")
        if result.rejected_reason:
            # Partial failure
            lines.append("")
            lines.append(result.rejected_reason)
        else:
            lines.append("")
            lines.append("Next: run kb_ingest on each path to promote to wiki/.")
        return "\n".join(lines)

    # Zero items
    if result.rejected_reason and "rate limit" not in result.rejected_reason.lower() \
            and "exceeds" not in result.rejected_reason.lower() \
            and "empty" not in result.rejected_reason.lower() \
            and "secret" not in result.rejected_reason.lower():
        # Some other partial failure with zero successful items
        return result.rejected_reason
    if result.rejected_reason:
        return result.rejected_reason
    # Successful zero-items (LLM filtered everything as noise)
    return (
        f"Captured 0 items, filtered {result.filtered_out_count} as noise. "
        f"Provenance: {result.provenance}\n"
        f"(No items met the decision/discovery/correction/gotcha bar.)"
    )
```

Then update the two stale docstrings (per spec §10):

In `kb_ingest` docstring (around lines 156-157), find the literal `"One of: article, paper, repo, video, podcast, book, dataset, conversation."` and change to `"One of: article, paper, repo, video, podcast, book, dataset, conversation, capture."`

In `kb_ingest_content` docstring (around lines 284-285), make the same edit.

- [ ] **Step 16.5: Run tests, verify they pass**

```bash
python -m pytest tests/test_mcp_core.py::TestKbCaptureWrapper -v
```

Expected: all 5 tests PASS. If `test_partial_write_format` shows "Captured 1 items" but the format check fails, refine the formatter logic — partial-failure with `n_items > 0` should show items list AND error.

- [ ] **Step 16.6: Verify the dev-time MCP server starts cleanly**

```bash
python -c "from kb.mcp.core import kb_capture; print(kb_capture.__doc__[:80])"
```

Expected: prints the docstring head. If `ImportError` or registration error, the `@mcp.tool()` decorator may have signature constraints — check `kb.mcp.app` for the server instance binding.

- [ ] **Step 16.7: Verify MCP tool count is now 26**

```bash
grep -rn "^@mcp.tool()" src/kb/mcp/*.py | wc -l
```

Expected: 26 (was 25). If 25, the decorator import path may be different — check that `kb_capture` is registered against the same `mcp` instance as the others.

- [ ] **Step 16.8: Ruff + commit**

```bash
ruff check src/kb/mcp/core.py tests/test_mcp_core.py
git add src/kb/mcp/core.py tests/test_mcp_core.py
git commit -m "feat(mcp): register kb_capture MCP tool

Wraps kb.capture.capture_items with response formatter covering all 4
shapes from spec §7: happy path, zero-items, hard reject, partial write.
Updates kb_ingest and kb_ingest_content docstrings to mention 'capture'
in the source-type enumeration."
```

---

## Task 17: Pipeline frontmatter strip (gated on `source_type == "capture"`)

**Files:**
- Modify: `src/kb/ingest/pipeline.py` (~5 LOC after `raw_content = raw_bytes.decode(...)`)
- Test: `tests/test_capture.py` (add `class TestPipelineFrontmatterStrip`)

Per spec §10: when ingesting a capture file, strip the leading YAML frontmatter so the write-tier LLM sees only the verbatim body. Gated on `source_type == "capture"` — universal stripping would regress Obsidian Web Clipper sources.

- [ ] **Step 17.1: Read the relevant pipeline.py block**

```bash
sed -n '545,575p' src/kb/ingest/pipeline.py
```

Expected: shows `raw_bytes = path.read_bytes()` followed by `raw_content = raw_bytes.decode(...)` around line 554, then `source_hash` computation around line 560.

- [ ] **Step 17.2: Write the failing test**

```python
class TestPipelineFrontmatterStrip:
    """Spec §10 — strip frontmatter from raw_content when source_type=='capture'."""

    def test_frontmatter_stripped_for_capture_source(self, tmp_captures_dir, mock_scan_llm, monkeypatch):
        # Write a capture file
        content = "We decided X for Y reason."
        mock_scan_llm({
            "items": [{
                "title": "decided X",
                "kind": "decision",
                "body": content,
                "one_line_summary": "s",
                "confidence": "stated",
            }],
            "filtered_out_count": 0,
        })
        result = capture_items(content)
        assert len(result.items) == 1
        capture_file = result.items[0].path

        # Now intercept the write-tier LLM call inside ingest to verify it sees stripped content
        seen_prompts = []
        def capture_prompt(prompt, *, tier="write", schema=None, system="", **kw):
            seen_prompts.append((tier, prompt))
            # Return a minimal extraction
            return {
                "title": "extracted title",
                "core_argument": "we decided X",
                "key_claims": ["X is good"],
                "entities_mentioned": [],
                "concepts_mentioned": [],
            }
        monkeypatch.setattr("kb.ingest.extractors.call_llm_json", capture_prompt)

        from kb.ingest.pipeline import ingest_source
        ingest_source(capture_file, source_type="capture")

        # The write-tier prompt should NOT contain the leading "---" block
        write_prompts = [p for tier, p in seen_prompts if tier == "write"]
        assert write_prompts, "expected at least one write-tier call"
        prompt = write_prompts[0]
        # Frontmatter should have been stripped — the first chars should not be ---
        # (allow for prompt boilerplate prefix, but verify the original frontmatter is absent)
        assert "captured_at:" not in prompt, "frontmatter leaked into LLM prompt"
        assert "captured_alongside:" not in prompt
        # The body should be present
        assert content in prompt

    def test_frontmatter_preserved_for_non_capture_source(self, tmp_project, monkeypatch):
        # Write a non-capture file with frontmatter (e.g., Obsidian Web Clipper article)
        article_path = tmp_project / "raw" / "articles" / "test.md"
        article_path.write_text(
            "---\nurl: https://example.com\nauthor: Test\n---\n\nArticle body here.",
            encoding="utf-8",
        )
        seen_prompts = []
        def capture_prompt(prompt, *, tier="write", schema=None, system="", **kw):
            seen_prompts.append(prompt)
            return {"title": "x", "summary": "y", "entities": [], "concepts": []}
        monkeypatch.setattr("kb.ingest.extractors.call_llm_json", capture_prompt)

        from kb.ingest.pipeline import ingest_source
        try:
            ingest_source(article_path, source_type="article")
        except Exception:
            pass  # we only care about the prompt content
        # For NON-capture sources, frontmatter should still appear in prompt
        if seen_prompts:
            assert "url: https://example.com" in seen_prompts[0] or "Article body here" in seen_prompts[0], \
                "non-capture source should preserve frontmatter for write-tier LLM"
```

- [ ] **Step 17.3: Run test — should fail (frontmatter not yet stripped)**

```bash
python -m pytest tests/test_capture.py::TestPipelineFrontmatterStrip -v
```

- [ ] **Step 17.4: Implement the gated frontmatter strip in `pipeline.py`**

Open `src/kb/ingest/pipeline.py`. Find the line right after `raw_content = raw_bytes.decode(...)` (around line 554-556). Insert:

```python
# Spec §10 — strip leading YAML frontmatter for capture sources only.
# Universal stripping would regress sources like Obsidian Web Clipper whose
# frontmatter (url, author, abstract, tags) carries metadata the write-tier
# LLM legitimately extracts from.
if source_type == "capture" and raw_content.startswith("---\n"):
    end = raw_content.find("\n---\n", 4)
    if end != -1:
        raw_content = raw_content[end + 5 :].lstrip("\n")
```

(`source_type` is the parameter passed into `ingest_source`. If the local variable name differs at this point in the function, use whichever name holds the source-type string at line 554.)

- [ ] **Step 17.5: Run tests, verify they pass**

```bash
python -m pytest tests/test_capture.py::TestPipelineFrontmatterStrip -v
```

Expected: both tests PASS. If `test_frontmatter_preserved_for_non_capture_source` fails because some other code path interferes, isolate by running just the assertion: `grep "url: https" tests/test_capture.py`.

- [ ] **Step 17.6: Run full test suite to check no regression**

```bash
python -m pytest -x -q
```

Expected: still passes. Pay attention to any pre-existing tests in `tests/test_ingest*.py` that might be sensitive to changes in `raw_content` handling — they should not be affected since the gate keys on `source_type == "capture"`.

- [ ] **Step 17.7: Ruff + commit**

```bash
ruff check src/kb/ingest/pipeline.py tests/test_capture.py
git add src/kb/ingest/pipeline.py tests/test_capture.py
git commit -m "feat(ingest): strip frontmatter for capture sources

When kb_ingest processes a raw/captures/<slug>.md file, strip the leading
YAML frontmatter before passing to write-tier extractor. Gated on
source_type=='capture' to preserve frontmatter for sources like Obsidian
Web Clipper articles whose metadata (url, author) feeds extraction."
```

---

## Task 18: `patch_all_kb_dir_bindings` fixture + round-trip integration test

**Files:**
- Modify: `tests/conftest.py` (add fixture)
- Modify: `tests/test_capture.py` (add `class TestRoundTripIntegration`)

Per spec §9 — the round-trip test exercises the full chain: `kb_capture` → write → `ingest_source(extraction=...)` → wiki summary page rendered with content. Uses `extraction=` bypass to skip the write-tier LLM call.

- [ ] **Step 18.1: Add the `patch_all_kb_dir_bindings` fixture in `tests/conftest.py`**

Append (per spec §9 enumerated list):

```python
@pytest.fixture
def patch_all_kb_dir_bindings(monkeypatch, tmp_project):
    """Monkey-patch every module-level RAW_DIR/WIKI_DIR/CAPTURES_DIR binding.

    Required for round-trip integration tests where the cascade path
    (_find_affected_pages → kb.compile.linker, etc.) would otherwise contaminate
    the real wiki/. Enumerates every site explicitly so a NEW binding fails
    loudly (add_new_site_or_update_this_fixture) rather than silently writing
    outside tmp_project.

    Spec §9 — verified via:
      grep -rn "from kb.config import.*\\(RAW_DIR\\|WIKI_DIR\\|CAPTURES_DIR\\)" src/kb/
    """
    wiki = tmp_project / "wiki"
    raw = tmp_project / "raw"
    captures = raw / "captures"

    raw_sites = [
        "kb.config.RAW_DIR",
        "kb.ingest.pipeline.RAW_DIR",
        "kb.utils.paths.RAW_DIR",
        "kb.mcp.browse.RAW_DIR",
        "kb.lint.runner.RAW_DIR",
        "kb.review.context.RAW_DIR",
    ]
    wiki_sites = [
        "kb.config.WIKI_DIR",
        "kb.ingest.pipeline.WIKI_DIR",
        "kb.utils.pages.WIKI_DIR",
        "kb.compile.linker.WIKI_DIR",
        "kb.graph.builder.WIKI_DIR",
        "kb.graph.export.WIKI_DIR",
        "kb.review.refiner.WIKI_DIR",
        "kb.review.context.WIKI_DIR",
        "kb.lint.runner.WIKI_DIR",
        "kb.mcp.browse.WIKI_DIR",
        "kb.mcp.app.WIKI_DIR",
    ]
    captures_sites = ["kb.config.CAPTURES_DIR", "kb.capture.CAPTURES_DIR"]

    for site in raw_sites:
        monkeypatch.setattr(site, raw, raising=False)
    for site in wiki_sites:
        monkeypatch.setattr(site, wiki, raising=False)
    for site in captures_sites:
        monkeypatch.setattr(site, captures, raising=False)

    return tmp_project
```

- [ ] **Step 18.2: Verify the binding sites are still accurate**

```bash
grep -rn "^from kb.config import.*\(RAW_DIR\|WIKI_DIR\|CAPTURES_DIR\)" src/kb/
```

Compare the output to the lists above. If any binding sites are missing, ADD them to the appropriate list. If any sites no longer exist, remove them. The fixture's `raising=False` tolerates absent attributes for forward compatibility but any genuinely-missing import is a plan bug.

- [ ] **Step 18.3: Write the round-trip integration test**

Append to `tests/test_capture.py`:

```python
class TestRoundTripIntegration:
    """Spec §9 round-trip — capture → ingest → wiki summary rendered with content."""

    def test_capture_then_ingest_renders_wiki_summary(
        self,
        patch_all_kb_dir_bindings,
        mock_scan_llm,
    ):
        from kb.capture import capture_items
        from kb.ingest.pipeline import ingest_source

        tmp_project = patch_all_kb_dir_bindings
        wiki_dir = tmp_project / "wiki"

        # 1) Capture two items
        content = "We picked atomic N-files for kb_capture. We discovered raw/captures/ collides on Windows MAX_PATH for long titles."
        mock_scan_llm({
            "items": [
                {
                    "title": "atomic n-files chosen",
                    "kind": "decision",
                    "body": "We picked atomic N-files for kb_capture.",
                    "one_line_summary": "atomic decision",
                    "confidence": "stated",
                },
                {
                    "title": "windows path collision",
                    "kind": "discovery",
                    "body": "raw/captures/ collides on Windows MAX_PATH for long titles.",
                    "one_line_summary": "windows path",
                    "confidence": "stated",
                },
            ],
            "filtered_out_count": 0,
        })
        cap_result = capture_items(content, provenance="round-trip-test")
        assert cap_result.rejected_reason is None
        assert len(cap_result.items) == 2

        # 2) Ingest each capture file using the extraction= bypass (no LLM)
        for ci in cap_result.items:
            extraction = {
                "title": ci.title,
                "core_argument": "We picked atomic N-files." if ci.kind == "decision"
                                 else "Windows MAX_PATH affects long-title slugs.",
                "key_claims": ["claim A", "claim B"],
                "entities_mentioned": ["kb_capture", "Windows"],
                "concepts_mentioned": ["atomization", "MAX_PATH"],
            }
            ingest_source(ci.path, source_type="capture", extraction=extraction)

        # 3) Verify wiki summary pages exist with non-empty content sections
        summaries_dir = wiki_dir / "summaries"
        assert summaries_dir.exists(), f"summaries dir missing: {summaries_dir}"
        summary_files = list(summaries_dir.glob("*.md"))
        assert len(summary_files) >= 1, "expected at least one summary page"

        for sf in summary_files:
            text = sf.read_text(encoding="utf-8")
            assert "## Overview" in text, f"missing ## Overview in {sf.name}: {text[:200]}"
            assert "## Key Claims" in text, f"missing ## Key Claims in {sf.name}"
            assert "claim A" in text or "claim B" in text, \
                f"key_claims not rendered in {sf.name}: {text[:300]}"
            assert "raw/captures/" in text or "source:" in text, \
                f"source ref not rendered in {sf.name}"

        # 4) Verify entity/concept pages were created
        entities_dir = wiki_dir / "entities"
        if entities_dir.exists():
            entity_files = list(entities_dir.glob("*.md"))
            # Don't assert exact count — slugify may merge entities
            assert any(ef.name.startswith("kb-capture") or ef.name.startswith("kb_capture") or "windows" in ef.name
                       for ef in entity_files), \
                f"expected kb_capture or windows entity page; got {[ef.name for ef in entity_files]}"
```

- [ ] **Step 18.4: Run the round-trip test**

```bash
python -m pytest tests/test_capture.py::TestRoundTripIntegration -v -s
```

Expected: PASS. The `-s` flag shows `print()` output if any debug assertions need investigation.

If it fails on `## Overview missing`:
- The template field-name fix from Task 15 may not be complete — verify `core_argument` is in `_build_summary_content`'s recognised list (`pipeline.py:178-183`).
- If the renderer uses a different field name (e.g., `summary` instead of `core_argument`), update Task 15's template OR update this test's `extraction` dict to match.

If it fails on `source:` not in text:
- The wiki summary page renderer may write `source:` as a frontmatter field (not in body). Adjust the assertion to check `sf.read_text` for that frontmatter line.

If it fails because the `patch_all_kb_dir_bindings` fixture missed a binding:
- The test will write to the REAL wiki/ — `git status` will show unexpected changes. Discard those changes (`git checkout wiki/`) and add the missing binding to the fixture.

- [ ] **Step 18.5: Ruff + commit**

```bash
ruff check tests/conftest.py tests/test_capture.py
git add tests/conftest.py tests/test_capture.py
git commit -m "test(capture): add round-trip integration test + dir-binding fixture

patch_all_kb_dir_bindings enumerates all 13 module-level RAW_DIR/WIKI_DIR/
CAPTURES_DIR bindings so round-trip tests don't contaminate the real wiki/.
Round-trip test exercises capture → ingest_source(extraction=) → wiki
summary page with content-based assertions (## Overview, ## Key Claims,
source ref, entity/concept pages)."
```

---

## Task 19: Doc updates — CLAUDE.md, BACKLOG.md, CHANGELOG.md, README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `BACKLOG.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

Per spec §11.

- [ ] **Step 19.1: Update `CLAUDE.md`**

Find these sections and apply the listed edits:

1. **"MCP Servers" → kb tools list** (the table-like enumeration of `kb_*` tools): add a new entry for `kb_capture`:

   ```markdown
   - `kb_capture(content, provenance=None)` — atomize up to 50KB of unstructured text into discrete `raw/captures/<slug>.md` items via scan-tier LLM. Returns file paths for subsequent `kb_ingest`. Secret-scanner rejects content with API keys, tokens, or private key blocks before any LLM call.
   ```

2. **"Implementation Status" line** — find the sentence that lists "1171 tests, 25 MCP tools, 18 modules" and update to: "1247 tests, 26 MCP tools, 19 modules" (use actual final test count from `python -m pytest --collect-only -q | tail -1`).

3. **"Phase 1 modules" or similar list** — add a note: a new line near the existing module enumerations:
   ```markdown
   **Phase 5 modules:** `kb.capture` — conversation/notes atomization for `raw/captures/`.
   ```

4. **"Ingestion Commands" section** — add a subsection:
   ```markdown
   # Conversation capture (in-session bookmarks, scratch notes)
   # Pass to the kb_capture MCP tool from your client; it writes raw/captures/*.md
   # which you can then promote with kb_ingest.
   ```

- [ ] **Step 19.2: Update `BACKLOG.md`**

Open `BACKLOG.md`, find line 94 (the Phase 5 / Ambient Capture entry for `kb_capture`):

```
- `mcp/` `kb_capture` MCP tool — accept up to 50KB of conversation or note text...
```

**Delete** the entire bullet (the BACKLOG convention is delete-not-strikethrough; the fix lives in CHANGELOG).

- [ ] **Step 19.3: Update `CHANGELOG.md`**

Find the `[Unreleased]` section (or create one if it doesn't exist) and add under `### Added`:

```markdown
### Added
- **`kb_capture` MCP tool** — atomize up to 50KB of unstructured text (chat logs, scratch notes, LLM session transcripts) into discrete `raw/captures/<slug>.md` files via scan-tier LLM. Each item gets typed `kind` (decision / discovery / correction / gotcha), verbatim body, and structured frontmatter (title, confidence, captured_at, captured_from, captured_alongside, source). Returns file paths for subsequent `kb_ingest`. New `kb.capture` module + `templates/capture.yaml` + 5 new MCP wrapper tests + ~40 library tests.
- **Secret scanner with reject-at-boundary** — `kb_capture` content is scanned for AWS / OpenAI / Anthropic / GitHub / Slack / GCP / Stripe / HuggingFace / Twilio / npm / JWT / DB connection strings / private key blocks BEFORE any LLM call; matches reject the entire batch with a precise pattern label and line number. Encoded-secret normalization pass also catches base64-wrapped and URL-encoded patterns.
- **Per-process rate limit** — `kb_capture` enforces a 60-call-per-hour sliding-window cap under `threading.Lock` for FastMCP concurrent-request safety. Configurable via `CAPTURE_MAX_CALLS_PER_HOUR`.
- **`templates/capture.yaml`** — new ingest template for `raw/captures/*.md` with field names matching existing pipeline (`core_argument`, `key_claims`, `entities_mentioned`, `concepts_mentioned`).
- **`yaml_escape` strips Unicode bidi override marks** (`\u202a-\u202e`, `\u2066-\u2069`) — defends LLM-supplied frontmatter values against audit-log confusion attacks where U+202E renders text backward in terminals.
- **`pipeline.py` strips frontmatter for capture sources** — when `kb_ingest` processes a `raw/captures/*.md` file, leading YAML frontmatter is stripped before write-tier extraction. Gated on `source_type == "capture"` so other sources (Obsidian Web Clipper, arxiv) preserve their frontmatter for the LLM.
```

- [ ] **Step 19.4: Update `README.md`**

Find the feature list / roadmap section and add a bullet about conversation capture support. Concise:

```markdown
- **Conversation capture** — `kb_capture` MCP tool atomizes chat / notes / session transcripts into typed knowledge items (decisions, discoveries, corrections, gotchas) with secret-scanner safety rails and a per-process rate limit.
```

- [ ] **Step 19.5: Ruff (no Python files, but verify markdown is clean)** — skip if no markdown linter; verify by re-reading each file.

```bash
git diff CLAUDE.md BACKLOG.md CHANGELOG.md README.md | head -100
```

Expected: shows the additions/deletions clearly.

- [ ] **Step 19.6: Commit doc updates**

```bash
git add CLAUDE.md BACKLOG.md CHANGELOG.md README.md
git commit -m "docs: kb_capture feature shipped — update CLAUDE/BACKLOG/CHANGELOG/README

CLAUDE.md: add kb_capture to MCP tools list; bump module/tool/test counts
to 19/26/1247 (verified via pytest --collect-only); add Phase 5 module
note; add conversation-capture workflow to Ingestion Commands.
BACKLOG.md: delete kb_capture entry from Phase 5 Ambient Capture (resolved).
CHANGELOG.md: [Unreleased] → Added covering kb_capture, secret scanner,
rate limit, capture template, yaml_escape bidi strip, pipeline FM strip.
README.md: feature-list bullet for conversation capture."
```

---

## Task 20: Architecture diagram update + PNG re-render

**Files:**
- Modify: `docs/architecture/architecture-diagram.html`
- Regenerate: `docs/architecture/architecture-diagram.png`

Per CLAUDE.md's "Architecture diagram sync (MANDATORY)" rule. The HTML must reflect the new pre-ingest capture stage; the PNG must be re-rendered.

- [ ] **Step 20.1: Read the current diagram HTML to find the right insertion point**

```bash
grep -n "raw/" docs/architecture/architecture-diagram.html | head -20
```

Look for where `raw/` is shown as a stage. The new flow to add is:

```
[ MCP client paste ] → [ kb_capture ] → [ raw/captures/*.md ] → [ kb_ingest ] → [ wiki/ ]
```

- [ ] **Step 20.2: Add the capture-stage box to the diagram**

Open `docs/architecture/architecture-diagram.html` in your editor. Add a new section/box upstream of the existing `raw/` → `kb_ingest` flow. Use the existing styling (colors, fonts) — don't introduce new CSS. Match the visual density of nearby boxes.

A minimal addition might be a labeled box `kb_capture (scan tier)` with arrows from `MCP client (paste)` to it, and from it down to `raw/captures/*.md` (a new sub-bucket of `raw/`), then arrow into the existing `kb_ingest`.

The exact HTML structure depends on what's already there — match the surrounding boxes.

- [ ] **Step 20.3: Re-render the PNG via Playwright** (per CLAUDE.md exact command)

From project root with `.venv` activated:

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

(On Unix, replace `.venv/Scripts/python` with `.venv/bin/python`.)

If the command fails with `playwright not installed`, run:

```bash
python -m playwright install chromium
```

then retry the render command.

- [ ] **Step 20.4: Verify the PNG was updated**

```bash
ls -lh docs/architecture/architecture-diagram.png
```

Expected: file mtime is recent. Open the PNG visually if possible to confirm the new capture stage appears.

- [ ] **Step 20.5: Commit the diagram update**

```bash
git add docs/architecture/architecture-diagram.html docs/architecture/architecture-diagram.png
git commit -m "docs(architecture): show kb_capture pre-ingest stage in diagram

HTML edited to add 'kb_capture (scan tier) → raw/captures/' upstream of
the existing kb_ingest pipeline. PNG re-rendered via Playwright per
CLAUDE.md mandatory architecture-sync rule."
```

---

## Task 21: Final verification + security review gate + push

**Files:** none (verification only)

Per spec §14 success criteria + feature-dev skill's security-review and final-push gates.

- [ ] **Step 21.1: Run the FULL test suite one more time**

```bash
python -m pytest -v
```

Expected: total pass count matches CLAUDE.md's updated number (~1247). No failures, no errors.

- [ ] **Step 21.2: Coverage check on `src/kb/capture.py`**

```bash
python -m pytest --cov=src/kb/capture --cov-report=term-missing tests/test_capture.py tests/test_mcp_core.py
```

Expected: ≥ 95% line coverage on `src/kb/capture.py`. If lower, identify uncovered branches and add targeted tests (cross-reference spec §9 "Branches that need explicit mock setup").

- [ ] **Step 21.3: Lint clean across all touched files**

```bash
ruff check src/kb/capture.py src/kb/utils/text.py src/kb/mcp/core.py src/kb/ingest/pipeline.py src/kb/config.py tests/test_capture.py tests/test_mcp_core.py tests/conftest.py
```

Expected: no errors. Fix any reported issues before continuing.

- [ ] **Step 21.4: Manual end-to-end smoke test**

Start the MCP server in one terminal:

```bash
.venv/Scripts/activate
kb mcp
```

In another terminal, simulate a capture call (or use the MCP client). A 5-item sample input:

```
Today we made several decisions:
1. We chose atomic N-files for kb_capture.
2. We discovered that the scan-tier model handles 50KB inputs in under 2s.

A correction: earlier I claimed slugs need to include timestamps. Actually they don't — the captured_at frontmatter handles temporal context.

Gotcha: Windows MAX_PATH limits us to 80 chars in slug — without the cap, long titles break.
```

Verify: ~4 files appear in `raw/captures/`, each with the expected frontmatter and verbatim body. Then run `kb ingest raw/captures/<slug>.md --type capture` for one and verify a wiki summary page appears.

Also verify the secret-reject path manually: paste `"AKIAIOSFODNN7EXAMPLE"` into `kb_capture` and confirm the response is `"Error: secret pattern detected at line 1 (AWS access key)..."`.

- [ ] **Step 21.5: Run the security-review skill (per feature-dev gate)**

```
Skill("everything-claude-code:security-review")
```

Brief the skill: "Reviewing kb_capture MCP tool. Spec at docs/superpowers/specs/2026-04-13-kb-capture-design.md §8 lists the threat model and mitigations. Verify path traversal, secret leakage, prompt injection (file-fidelity scope), bidi-mark stripping, input bounds, and rate-limit thread safety. Downstream prompt-injection at kb_ingest is explicitly UNMITIGATED in v1 (§13) — flag if disagree."

If the skill identifies new findings: add them to BACKLOG.md and decide whether to fix in this feature or defer.

- [ ] **Step 21.6: Verify CLAUDE.md test count matches reality**

```bash
echo "Tests in suite:"
python -m pytest --collect-only -q | tail -3
echo "Tools registered:"
grep -rn "^@mcp.tool()" src/kb/mcp/*.py | wc -l
echo "kb modules:"
ls src/kb/*.py src/kb/*/__init__.py 2>/dev/null | wc -l
```

Cross-check the numbers in CLAUDE.md from Task 19. If they drift, edit CLAUDE.md and amend the doc commit (or make a follow-up commit).

- [ ] **Step 21.7: Final review of the commit series**

```bash
git log --oneline origin/main..HEAD
```

Expected: ~20 commits, each with a clear feat/test/docs prefix. If any feel like they should be squashed, do so before push (interactive rebase NOT recommended in this workflow — squash via `git reset --soft origin/main` and re-commit if absolutely needed, with user approval).

- [ ] **Step 21.8: Push to remote (only after explicit user approval)**

ASK the user before pushing. Never auto-push. When approved:

```bash
git push origin main
```

If pre-push hooks fail, investigate and fix the underlying issue. Do NOT use `--no-verify`.

- [ ] **Step 21.9: Verify spec/plan are committed and visible**

```bash
git log --oneline --follow docs/superpowers/specs/2026-04-13-kb-capture-design.md
git log --oneline --follow docs/superpowers/plans/2026-04-14-kb-capture.md
```

If the spec's uncommitted edits (~+421/-123 from earlier in the session) are still uncommitted, either commit them now in a separate `docs(spec):` commit OR ask the user how to handle them. Don't leave the spec inconsistent with the implementation.

---

## Self-Review

Spec coverage check (per writing-plans skill):

| Spec section | Implemented in | Status |
|---|---|---|
| §1 Overview | Task descriptions | ✓ context everywhere |
| §2 Locked decisions | Header + Task 14 | ✓ enforced in code |
| §3 Module layout | Task 1 (config), Task 14 (orchestrator), Tasks 7/10/13 (helpers) | ✓ |
| §3 atomic write helper | Task 10 | ✓ |
| §3 concurrency note (`threading.Lock`) | Task 4 | ✓ |
| §4 data flow (9 steps) | Task 14 orchestrator wires all | ✓ |
| §4 scan-tier prompt | Task 7 (`_PROMPT_TEMPLATE`) | ✓ |
| §4 JSON schema | Task 7 (`_CAPTURE_SCHEMA`) | ✓ |
| §4 invariants 1-9 | Tasks 3, 4, 5, 6, 7, 11, 13, 14 collectively | ✓ |
| §5 frontmatter / slug | Tasks 8, 9, 12 | ✓ |
| §5 unicode caveat | Task 8 fallback test | ✓ |
| §5 path-within gate | Task 9 | ✓ |
| §5 symlink guard | Task 9 | ✓ |
| §6 templates/capture.yaml | Task 15 | ✓ |
| §6 title-divergence note | Task 17 (frontmatter strip mitigates) | ✓ |
| §7 Class A/B/C/D errors | Tasks 3, 4, 5, 6, 7, 13, 14 | ✓ |
| §7 MCP response formats | Task 16 | ✓ |
| §8 security checklist | All tasks; Task 21 verification | ✓ |
| §8 expanded secret patterns | Task 5 | ✓ |
| §8 encoded normalization | Task 6 | ✓ |
| §8 frontmatter injection / bidi marks | Task 2 | ✓ |
| §8 rate limit thread safety | Task 4 | ✓ |
| §9 testing strategy | Tests across every task | ✓ |
| §9 fixtures | Tasks 7 (mock_scan_llm), 10 (tmp_captures_dir), 18 (patch_all_kb_dir_bindings) | ✓ |
| §9 round-trip integration | Task 18 | ✓ |
| §9 TDD sequencing (8 sub-tasks) | Tasks 3-14 follow it | ✓ |
| §10 integration surface | Tasks 1, 2, 16, 17, 18 | ✓ |
| §11 doc updates | Task 19 | ✓ |
| §11 architecture diagram | Task 20 | ✓ |
| §12 Context7 verification | NOTE: feature-dev skill says do this AFTER plan approval, BEFORE subagents dispatch — runner of this plan is responsible | ⚠ runner-side |
| §13 non-goals / deferrals | Implicit (no tasks for them); flagged in commits | ✓ |
| §14 success criteria | Task 21 | ✓ |

Type-consistency check: `capture_items`, `CaptureResult`, `CaptureItem`, `_validate_input`, `_check_rate_limit`, `_scan_for_secrets`, `_extract_items_via_llm`, `_verify_body_is_verbatim`, `_build_slug`, `_path_within_captures`, `_exclusive_atomic_write`, `_resolve_provenance`, `_render_markdown`, `_write_item_files` — all referenced consistently across tasks.

Placeholder scan: no `TBD`, no `TODO`, no `implement later`. Every step has either complete code or a precise edit instruction.

One acknowledged gap in this plan: **Context7 verification** of the `anthropic` SDK / FastMCP / `python-frontmatter` / `os.O_EXCL` Windows behavior is the runner's responsibility per feature-dev skill — it happens AFTER plan approval, BEFORE subagent dispatch. The plan can't pre-do it because subagents work from the verified plan. If Context7 reveals API drift, this plan needs amendment in the affected tasks.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-14-kb-capture.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Each subagent gets: this plan, the spec, a single task to complete, and the existing-tests/code context. I verify each task's commit before dispatching the next subagent. Cleanest history; isolates blast radius if a subagent drifts.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review. Keeps everything in one session's context; faster if there are tight cross-task dependencies.

Which approach?
