# Cycle 35 — Step 7 Implementation Plan

Date: 2026-04-26
Drafted in: primary session (per cycle-14 L1 — ≥15 ACs + full context + grep-verified code locations)
Sizing per cycle-13 L2: each task < 30 LoC code + < 100 LoC tests + stdlib-only APIs → primary-session implementation; reserve Codex dispatch for Task 4 PNG re-render IF Playwright invocation has unexpected failure modes.

Total: 6 tasks (4 file-grouped commits + 1 dep-bump + 1 doc-update). 21 effective ACs (AC1-AC18 + AC1b + AC-Dep1 + AC-Doc1).

---

## TASK 1 — `utils/sanitize.py` + cycle-33 xfail removal + AC3 expansion

**Files:**
- `src/kb/utils/sanitize.py` (modify `_ABS_PATH_PATTERNS` lines 11-19)
- `tests/test_cycle33_mcp_core_path_leak.py` (remove xfail decorator at lines 477-486; expand `TestSanitizeErrorTextUNCAndLongPath` class with 3 new test methods)

**Change:**
1. Insert TWO new alternatives in `_ABS_PATH_PATTERNS` AFTER the existing backslash UNC alternative (line 17), BEFORE the POSIX absolute alternative (line 18):
   - Slash-UNC long-path: `r"|(?://\?/UNC/[^\s'\"?]+/[^\s'\"]+(?:/[^\s'\"]*)?)"`
   - URI-guarded ordinary slash-UNC: `r"|(?<!:)(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)"`
2. Add inline comment citing T1 + T1b + cycle-35 AC1.
3. Remove `@pytest.mark.xfail(strict=True, reason=...)` decorator at `test_windows_ordinary_unc_filename_redacts` (line 477). Keep the test body unchanged — strict=True semantic forces marker removal as soon as the underlying test passes.
4. ADD three new test methods to `TestSanitizeErrorTextUNCAndLongPath`:
   - `test_forward_slash_unc_redacts_via_extended_pattern` (positive): `OSError(errno.EACCES, "Access is denied", r"\\corp.example.com\share$\evidence\secret.md")` → assert `corp.example.com` / `share$` / `secret.md` absent from `sanitize_error_text` output.
   - `test_url_not_overmatched_by_uri_guard` (negative): `sanitize_text("see https://example.com/path for details")` → assert input returned unchanged (verifies `(?<!:)` lookbehind protects URLs).
   - `test_double_slash_comment_not_overmatched` (negative): `sanitize_text("// comment text\n// more comments")` → assert input returned unchanged (verifies the host-segment requirement requires `/` after).
   - `test_slash_unc_long_path_redacts` (positive): `sanitize_text("//?/UNC/server/share/x.md")` → asserts `server` / `share` / `x.md` absent (T1b verification).

**Test:**
```python
# Existing strict-xfail test now PASSES under strict=True semantic → marker MUST be removed.
# New positive test:
def test_forward_slash_unc_redacts_via_extended_pattern(self):
    out = sanitize_error_text(
        OSError(errno.EACCES, "Access is denied", r"\\corp.example.com\share$\evidence\secret.md")
    )
    assert "corp.example.com" not in out
    assert "share$" not in out
    assert "secret.md" not in out

# Cycle-24 L4 dual-anchor: ALSO write a revert-fail test for the URI guard.
def test_url_not_overmatched_by_uri_guard(self):
    inp = "see https://example.com/path for details"
    assert sanitize_text(inp) == inp  # Must stay verbatim
```

**Criteria:** AC1, AC1b, AC2, AC3 (per Step 5 final design).

**Threat:** T1 (UNC slash bypass) + T1b (slash UNC long-path).

**Self-check before commit:**
- `rg "_ABS_PATH_PATTERNS" src/kb/utils/sanitize.py` — confirm the two new alternatives present in correct order.
- `pytest tests/test_cycle33_mcp_core_path_leak.py::TestSanitizeErrorTextUNCAndLongPath -v` — all tests pass; xfail marker GONE.
- Mental revert AC1: `sanitize_text("//corp.example.com/share$/secret.md")` returns input unchanged → `test_forward_slash_unc_redacts_via_extended_pattern` FAILS. `sanitize_text("https://example.com/path")` would be redacted (no lookbehind) → `test_url_not_overmatched_by_uri_guard` FAILS.

---

## TASK 2 — `ingest/pipeline.py` index-writer file_lock + empty-list + backtick

**Files:**
- `src/kb/ingest/pipeline.py` (modify `_update_sources_mapping` lines 761-806; modify `_update_index_batch` lines 816-857)
- `tests/test_cycle35_ingest_index_writers.py` (NEW)

**Change:**
1. `_update_sources_mapping` (line 761):
   - ADD early-return AFTER docstring + BEFORE `sources_file = ...`: `if not wiki_pages: logger.debug("_update_sources_mapping called with empty wiki_pages — skipping (source_ref=%s)", source_ref); return`.
   - WRAP both write branches in `with file_lock(sources_file):` covering `read_text` + `atomic_text_write`. The `if not sources_file.exists():` check stays OUTSIDE the lock (no point locking a missing file). Re-structure body:
     ```python
     if not sources_file.exists():
         logger.warning("_sources.md not found — skipping source mapping for %s", source_ref)
         return
     with file_lock(sources_file):
         content = sources_file.read_text(encoding="utf-8")
         if f"`{escaped_ref}`" not in content:
             content += entry
             atomic_text_write(content, sources_file)
             return
         lines = content.splitlines(keepends=True)
         for i, line in enumerate(lines):
             if f"`{escaped_ref}`" in line:
                 existing_ids = set(re.findall(r"\[\[([^\]]+)\]\]", line))
                 missing = [p for p in wiki_pages if p not in existing_ids]
                 if missing:
                     extra = ", ".join(f"[[{p}]]" for p in missing)
                     lines[i] = line.rstrip("\n") + f", {extra}\n"
                     atomic_text_write("".join(lines), sources_file)
                 return
     ```
   - Note `escaped_ref` substituted at BOTH the membership check (was line 792 `f"\`{source_ref}\`"`) AND the per-line scan (was line 799 `f"\`{source_ref}\`"`). This is the AC7 fix.
2. `_update_index_batch` (line 816):
   - Keep existing `if not entries: return` early-return at line 831 (already correct).
   - WRAP the read+write in `with file_lock(index_path):` between `if not index_path.exists()` and `if changed: atomic_text_write(...)`:
     ```python
     if not index_path.exists():
         logger.warning("index.md not found — skipping index update for %d entries", len(entries))
         return
     with file_lock(index_path):
         content = index_path.read_text(encoding="utf-8")
         changed = False
         for page_type, slug, title in entries:
             # ... existing per-entry logic
         if changed:
             atomic_text_write(content, index_path)
     ```
3. Confirm NO wrapper-level `file_lock` added in `_write_index_files` (lines 866-890) — Q7 mandates leaving the wrapper unlocked.

**Tests** (`tests/test_cycle35_ingest_index_writers.py` — NEW; uses `tmp_kb_env` and standard `tmp_wiki` fixtures):

```python
"""Cycle 35 — _update_sources_mapping + _update_index_batch RMW lock + empty-list + backtick dedup."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from kb.ingest import pipeline


# ---------------- AC8: _update_sources_mapping holds file_lock across RMW ----------------

class TestUpdateSourcesMappingRMWLock:
    def test_holds_file_lock_across_rmw(self, monkeypatch, tmp_path):
        """AC8 — spy on pipeline.file_lock + read_text + atomic_text_write call ordering.

        Cycle-17 L4: stdlib call_args_list ordering, not artificial concurrency injection.
        Revert-fail anchor: removing `with file_lock(sources_file):` drops the file_lock
        spy entirely → assertion fails.
        """
        sources = tmp_path / "_sources.md"
        sources.write_text("- `raw/old.md` → [[e/old]]\n", encoding="utf-8")

        lock_calls: list[Path] = []
        write_calls: list[tuple[str, Path]] = []

        from contextlib import contextmanager

        @contextmanager
        def fake_lock(path):
            lock_calls.append(("acquire", path))
            try:
                yield
            finally:
                lock_calls.append(("release", path))

        def fake_write(content, path):
            write_calls.append((content, path))
            Path(path).write_text(content, encoding="utf-8")

        monkeypatch.setattr(pipeline, "file_lock", fake_lock)
        monkeypatch.setattr(pipeline, "atomic_text_write", fake_write)

        pipeline._update_sources_mapping(
            "raw/articles/new.md", ["e/new"], wiki_dir=tmp_path
        )

        # Lock acquired before write, released after.
        assert lock_calls[0] == ("acquire", sources)
        assert lock_calls[-1] == ("release", sources)
        assert len(write_calls) == 1
        assert write_calls[0][1] == sources


# ---------------- AC9: _update_index_batch holds file_lock across RMW ----------------

class TestUpdateIndexBatchRMWLock:
    def test_holds_file_lock_across_rmw(self, monkeypatch, tmp_path):
        index_path = tmp_path / "index.md"
        # Use one of the section headers from _SECTION_HEADERS (entities subdir)
        index_path.write_text("## Entities\n\n*No pages yet.*\n", encoding="utf-8")

        lock_events: list[tuple[str, Path]] = []
        write_events: list[Path] = []

        from contextlib import contextmanager

        @contextmanager
        def fake_lock(path):
            lock_events.append(("acquire", path))
            try:
                yield
            finally:
                lock_events.append(("release", path))

        def fake_write(content, path):
            write_events.append(Path(path))
            Path(path).write_text(content, encoding="utf-8")

        monkeypatch.setattr(pipeline, "file_lock", fake_lock)
        monkeypatch.setattr(pipeline, "atomic_text_write", fake_write)

        pipeline._update_index_batch(
            [("entity", "new-entity", "New Entity")], wiki_dir=tmp_path
        )

        assert lock_events[0] == ("acquire", index_path)
        assert lock_events[-1] == ("release", index_path)
        assert write_events == [index_path]


# ---------------- AC10: empty wiki_pages skips silently ----------------

class TestUpdateSourcesMappingEmptyList:
    def test_skips_empty_wiki_pages(self, monkeypatch, tmp_path, caplog):
        """AC10 — empty wiki_pages returns silently before sources_file existence check.

        T8 verification: NO `_sources.md not found` warning fires when sources_file
        is absent AND wiki_pages is empty.
        """
        # sources_file deliberately absent (no write_text).
        write_calls = []
        monkeypatch.setattr(
            pipeline, "atomic_text_write",
            lambda content, path: write_calls.append((content, path))
        )

        with caplog.at_level("DEBUG"):
            pipeline._update_sources_mapping(
                "raw/articles/empty.md", [], wiki_dir=tmp_path
            )

        assert write_calls == []
        # T8: no missing-file warning under empty-pages.
        assert not any("not found" in r.message for r in caplog.records)


# ---------------- AC11: backtick in source_ref doesn't double-write ----------------

class TestUpdateSourcesMappingBacktickDedup:
    def test_dedups_backtick_in_source_ref(self, tmp_path):
        """AC11 — backtick-bearing source_ref deduplicates on re-call.

        Cycle-24 L4 dual-anchor:
          - Single-call invariant: escaped form `\\\`raw/has\\\`backtick.md\\\`` on disk after call 1.
          - Two-call invariant: re-call with same source_ref → single line, no duplicate.
        Revert-fail: changing membership/per-line scan back to raw `source_ref` makes
        call 2 not match the escaped form already on disk → second entry appended → 2 lines.
        """
        sources = tmp_path / "_sources.md"
        sources.write_text("# Sources\n\n", encoding="utf-8")
        ref = r"raw/has`backtick.md"

        # Call 1: writes the entry with escaped backtick.
        pipeline._update_sources_mapping(ref, ["e/foo"], wiki_dir=tmp_path)
        content_after_1 = sources.read_text(encoding="utf-8")
        # Single-call invariant: escaped form on disk.
        assert r"`raw/has\`backtick.md`" in content_after_1
        n_entries_1 = content_after_1.count(r"raw/has\`backtick.md")
        assert n_entries_1 == 1

        # Call 2 with identical inputs: dedup branch hits, no second entry.
        pipeline._update_sources_mapping(ref, ["e/foo"], wiki_dir=tmp_path)
        content_after_2 = sources.read_text(encoding="utf-8")
        n_entries_2 = content_after_2.count(r"raw/has\`backtick.md")
        assert n_entries_2 == 1, f"expected 1 line, got {n_entries_2}: {content_after_2!r}"
```

**Criteria:** AC4-AC11.

**Threat:** T2, T3, T4, T5, T8.

**Self-check before commit:**
- `rg "with file_lock\(sources_file\)|with file_lock\(index_path\)" src/kb/ingest/pipeline.py` — confirm both lock sites added.
- `rg "f\"\`\\\\{source_ref\\\\}\`\"" src/kb/ingest/pipeline.py` — ZERO matches inside `_update_sources_mapping` (was 2 before AC7 fix).
- `rg "if not wiki_pages:" src/kb/ingest/pipeline.py` — early-return present.
- Full pytest run: `python -m pytest tests/test_cycle35_ingest_index_writers.py tests/test_cycle33_ingest_index_idempotency.py tests/test_cycle18_ingest_observability.py tests/test_v01008_ingest_pipeline_fixes.py -v` — new tests pass; existing 4 monkeypatch-based tests still pass.

---

## TASK 3 — `mcp/core.py` `_validate_filename_slug` helper + wiring

**Files:**
- `src/kb/mcp/core.py` (add `_validate_filename_slug` helper near `_validate_save_as_slug`; wire into `_validate_file_inputs` at line 167-178)
- `tests/test_cycle35_mcp_core_filename_validator.py` (NEW)

**Change:**
1. Add `_validate_filename_slug` near `_validate_save_as_slug` (around line 188 area):
   ```python
   _FILENAME_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")
   _FILENAME_MAX_LEN = 200  # Matches existing _validate_file_inputs len cap.

   def _validate_filename_slug(filename: str) -> tuple[str, str | None]:
       """Validate a free-form user-supplied filename for kb_ingest_content / kb_save_source.

       Looser than _validate_save_as_slug — does NOT enforce slugify() round-trip
       equality (free-form filenames legitimately differ from their slug form).
       Rejects:
         - NUL byte (POSIX path truncation hazard)
         - Path separators / .. (traversal)
         - Trailing dot/space (Windows trim aliasing — evades _is_windows_reserved)
         - Non-ASCII (homoglyph + RTL-override + zero-width attacks)
         - Windows reserved basenames (CON, PRN, NUL, AUX, COM1-9, LPT1-9)
         - Length > _FILENAME_MAX_LEN
       Allows leading dot (`.env`) and leading dash (`-foo`) — POSIX legitimate.

       Returns (filename, None) on success, ("", error_msg) on failure.
       Mirrors `_validate_save_as_slug` signature for caller-pattern consistency.
       """
       if not isinstance(filename, str):
           return "", "Error: filename must be a string"
       if "\x00" in filename:
           return "", "Error: filename cannot contain NUL byte"
       if "/" in filename or "\\" in filename or ".." in filename:
           return "", "Error: filename cannot contain path separators or .."
       if filename.strip() != filename:
           return "", "Error: filename cannot have leading/trailing whitespace or trailing dot"
       if filename.endswith("."):
           return "", "Error: filename cannot end with a dot (Windows trims silently)"
       if _FILENAME_NON_ASCII_RE.search(filename):
           return "", "Error: filename must be ASCII (homoglyphs / non-ASCII letters rejected)"
       if len(filename) > _FILENAME_MAX_LEN:
           return "", f"Error: filename too long (max {_FILENAME_MAX_LEN} chars)"
       if _is_windows_reserved(filename):
           return "", "Error: filename uses a Windows reserved device name"
       return filename, None
   ```
2. Wire into `_validate_file_inputs` (line 167-178) — placed AFTER existing empty/length checks (per R1 C9 — existing error wording wins ties), BEFORE the content-size check:
   ```python
   def _validate_file_inputs(filename: str, content: str) -> str | None:
       """Validate filename and content size. Returns error string or None if valid."""
       if not filename or not filename.strip():
           return "Error: Filename cannot be empty."
       if len(filename) > 200:
           return "Error: Filename too long (max 200 chars)."
       _, slug_err = _validate_filename_slug(filename)
       if slug_err:
           return slug_err
       if len(content) > MAX_INGEST_CONTENT_CHARS:
           return (
               f"Error: Content too large ({len(content)} chars). "
               f"Maximum: {MAX_INGEST_CONTENT_CHARS} chars."
           )
       return None
   ```

**Tests** (`tests/test_cycle35_mcp_core_filename_validator.py` — NEW):

```python
"""Cycle 35 — _validate_filename_slug + _validate_file_inputs parity for kb_ingest_content / kb_save_source."""

from __future__ import annotations
import pytest

from kb.mcp.core import _validate_filename_slug, _validate_file_inputs


class TestValidateFilenameSlugRejects:
    def test_rejects_nul_byte(self):
        slug, err = _validate_filename_slug("foo\x00.md")
        assert slug == "" and err is not None and "NUL" in err

    def test_rejects_homoglyph_cyrillic(self):
        # U+0430 Cyrillic а — visually identical to ASCII а
        slug, err = _validate_filename_slug("а.md")
        assert slug == "" and err is not None and ("ASCII" in err or "homoglyph" in err)

    @pytest.mark.parametrize("name", ["CON.md", "PRN.txt", "NUL", "AUX", "com1.md", "lpt9.txt"])
    def test_rejects_windows_reserved(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == "" and err is not None and ("reserved" in err or "device" in err)

    @pytest.mark.parametrize("name", ["../escape.md", "foo/bar.md", "foo\\bar.md", "..", "../"])
    def test_rejects_path_separators(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == "" and err is not None and "separator" in err

    @pytest.mark.parametrize("name", ["CON.md.", "trailing-dot.", "trailing-space.md "])
    def test_rejects_trailing_dot_or_space(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == "" and err is not None
        # Either trailing-dot guard OR whitespace guard catches it; both are rejection.

    def test_rejects_oversized(self):
        slug, err = _validate_filename_slug("x" * 201)
        assert slug == "" and err is not None and "too long" in err


class TestValidateFilenameSlugAccepts:
    @pytest.mark.parametrize(
        "name",
        [
            "karpathy-llm-knowledge-bases.md",
            "my_doc.md",
            "file-2026-04-26.md",
            ".env",  # leading dot allowed (POSIX hidden-file convention)
            "-foo.md",  # leading dash allowed (POSIX legitimate)
            "Document_With_Underscores.md",
            "ALLCAPS.MD",
        ],
    )
    def test_accepts_legitimate(self, name):
        slug, err = _validate_filename_slug(name)
        assert err is None, f"unexpected rejection of {name!r}: {err}"
        assert slug == name


class TestValidateFileInputsWiring:
    """AC13 + AC15 — _validate_file_inputs delegates to _validate_filename_slug."""

    def test_rejects_homoglyph_via_wiring(self):
        err = _validate_file_inputs("а.md", "ok")
        assert err is not None and ("ASCII" in err or "homoglyph" in err)

    def test_rejects_path_separator_via_wiring(self):
        err = _validate_file_inputs("../escape.md", "ok")
        assert err is not None and "separator" in err

    def test_rejects_windows_reserved_via_wiring(self):
        err = _validate_file_inputs("CON.md", "ok")
        assert err is not None and ("reserved" in err or "device" in err)

    def test_rejects_nul_via_wiring(self):
        err = _validate_file_inputs("foo\x00.md", "ok")
        assert err is not None and "NUL" in err

    def test_accepts_legitimate(self):
        # Baseline preservation — these passed before cycle 35 too.
        assert _validate_file_inputs("karpathy-llm-knowledge-bases.md", "ok") is None
        assert _validate_file_inputs("my_doc.md", "ok") is None

    def test_existing_empty_check_unchanged(self):
        err = _validate_file_inputs("", "ok")
        assert err is not None and "empty" in err.lower()

    def test_existing_length_check_unchanged(self):
        err = _validate_file_inputs("x" * 250, "ok")
        # Existing check fires at len > 200; should win the tie.
        assert err is not None and "too long" in err.lower()

    def test_existing_content_check_unchanged(self):
        from kb.config import MAX_INGEST_CONTENT_CHARS
        err = _validate_file_inputs("ok.md", "x" * (MAX_INGEST_CONTENT_CHARS + 1))
        assert err is not None and "too large" in err.lower()
```

**Criteria:** AC12, AC13, AC14, AC15.

**Threat:** T6a (NUL), T6b (homoglyph), T6c (Windows-reserved), T6d (path-separator), T6e (no false positives).

**Self-check before commit:**
- `rg "_validate_filename_slug" src/kb tests` — helper exists in core.py + wired in `_validate_file_inputs` + referenced from new test file.
- `pytest tests/test_cycle35_mcp_core_filename_validator.py -v` — all parametrized cases pass.
- Run existing MCP-tool tests: `pytest tests/ -v -k "kb_ingest_content or kb_save_source"` — no false-positive rejection regressions.

---

## TASK 4 — `docs/architecture/` v0.11.0 sync + PNG re-render + conventions.md snippet

**Files:**
- `docs/architecture/architecture-diagram.html` (line 501 v0.10.0 → v0.11.0)
- `docs/architecture/architecture-diagram-detailed.html` (line 398 v0.10.0 → v0.11.0)
- `docs/architecture/architecture-diagram.png` (re-rendered binary)
- `docs/reference/conventions.md` (Architecture Diagram Sync section — add canonical Playwright snippet)

**Change:**
1. Edit line 501 of `architecture-diagram.html`: `v0.10.0` → `v0.11.0`.
2. Edit line 398 of `architecture-diagram-detailed.html`: `v0.10.0` → `v0.11.0`.
3. Re-render `architecture-diagram.png` via Playwright Python (snippet from Step 6 Context7 amendment):
   ```python
   from pathlib import Path
   from playwright.sync_api import sync_playwright

   root = Path.cwd()
   html = (root / "docs/architecture/architecture-diagram.html").resolve()
   png = root / "docs/architecture/architecture-diagram.png"
   with sync_playwright() as p:
       browser = p.chromium.launch()
       context = browser.new_context(
           viewport={"width": 1440, "height": 900},
           device_scale_factor=3,
       )
       page = context.new_page()
       page.goto(html.as_uri(), wait_until="networkidle")
       page.screenshot(path=str(png), full_page=True, type="png")
       browser.close()
   ```
4. Add the snippet to `docs/reference/conventions.md` Architecture Diagram Sync section as a fenced Python code block.

**Test:** No pytest test for the visual PNG (binary diff). Verification is manual + grep:
- `rg "v0\.10\.0" docs/architecture/` — ZERO matches after edit.
- `rg "v0\.11\.0" docs/architecture/architecture-diagram.html docs/architecture/architecture-diagram-detailed.html` — exactly 1 match each.
- File modification time on `architecture-diagram.png` is newer than baseline.
- `python -c "from PIL import Image; print(Image.open('docs/architecture/architecture-diagram.png').size)"` — confirms regenerated; size matches viewport × device_scale_factor.

**Criteria:** AC16, AC17, AC18.

**Threat:** T7 (doc drift).

**Self-check before commit:**
- All three `rg`/`ls` checks above pass.
- Visual review (`start docs/architecture/architecture-diagram.png` on Windows): confirm v0.11.0 visible in the rendered image.

---

## TASK 5 — Step 11b GitPython 3.1.46 → 3.1.47 dep bump

**Files:**
- `requirements.txt` (line 82 `GitPython==3.1.46` → `GitPython>=3.1.47`)

**Change:** Single-line pin bump.

**Test:** No pytest test (dep bumps are CI gate verified).

**Criteria:** AC-Dep1.

**Threat:** T9 (Step-11b opportunistic).

**Self-check before commit:**
- `pip install -U -r requirements.txt` — bumps GitPython to ≥3.1.47.
- `pip-audit --format json | python -c "import sys, json; data=json.load(sys.stdin); gits=[d for d in data['dependencies'] if d['name']=='gitpython']; print(gits)"` — GitPython advisories absent.
- `rg "^\s*(import git\b|from git\b)" src/kb` — ZERO matches (pre-verified at Step 5).
- Full pytest run after upgrade: `python -m pytest -q` — no regressions.

**Commit message:** `fix(deps): patch GitPython 3.1.46 -> 3.1.47 (GHSA-x2qx-6953-8485, GHSA-rpm5-65cw-6hj4)`.

---

## TASK 6 — Step 12 documentation update

**Files:**
- `CHANGELOG.md` (compact entry under [Unreleased] Quick Reference)
- `CHANGELOG-history.md` (full per-cycle detail)
- `BACKLOG.md` (delete resolved items: M11, M12, M13, M14, M15, M21 + cycle-34 follow-up AC4e entry)
- `docs/reference/implementation-status.md` (add cycle 35 entry)

**Change:**
1. CHANGELOG.md — newest-first compact entry covering: 18 ACs across 4 file groups + AC1b (T1b proactive) + AC-Dep1 (GitPython bump) + new tests.
2. CHANGELOG-history.md — full bullet detail per AC.
3. BACKLOG.md — delete M11 (RMW lock now closed), M13 (empty-list closed), M14 (backtick closed), M15 (filename validator parity closed), M21 (architecture v0.11.0 sync closed), M12 (UNC slash-normalize closed). Per-line edits — do NOT collapse phase headers since other items remain.
4. docs/reference/implementation-status.md — add cycle 35 entry under "Latest cycle".

**Test:** N/A.

**Criteria:** AC-Doc1.

**Threat:** N/A (doc work).

**Self-check before commit:**
- Cross-grep: `rg "v0\.10\.0|v0\.11\.0" docs/reference/implementation-status.md CLAUDE.md` — version references consistent.
- Test count cross-check (cycle-15 L4 + cycle-23 L4): `python -m pytest --collect-only 2>&1 | tail -1` returns exact "N tests collected" — update CLAUDE.md state line + CHANGELOG entry to match.
- Commit count: `git log --oneline origin/main..HEAD | wc -l` = N — backfill in CHANGELOG entry post-merge per cycle-30 L1 (use `+TBD` placeholder if before merge).

---

## Inline Step 8 plan-gate self-check

**AC coverage table:**

| AC | Task | Test |
|----|------|------|
| AC1 | TASK 1 | `test_forward_slash_unc_redacts_via_extended_pattern` + 3 negatives |
| AC1b | TASK 1 | `test_slash_unc_long_path_redacts` |
| AC2 | TASK 1 | xfail marker removed; existing test passes |
| AC3 | TASK 1 | 4 new test methods in `TestSanitizeErrorTextUNCAndLongPath` |
| AC4 | TASK 2 | `TestUpdateSourcesMappingRMWLock::test_holds_file_lock_across_rmw` |
| AC5 | TASK 2 | `TestUpdateIndexBatchRMWLock::test_holds_file_lock_across_rmw` |
| AC6 | TASK 2 | `TestUpdateSourcesMappingEmptyList::test_skips_empty_wiki_pages` |
| AC7 | TASK 2 | `TestUpdateSourcesMappingBacktickDedup::test_dedups_backtick_in_source_ref` |
| AC8/AC9/AC10/AC11 | TASK 2 | per-class tests above |
| AC12 | TASK 3 | `TestValidateFilenameSlugRejects` + `TestValidateFilenameSlugAccepts` |
| AC13 | TASK 3 | `TestValidateFileInputsWiring` |
| AC14 | TASK 3 | parametrized cases in `TestValidateFilenameSlugRejects` |
| AC15 | TASK 3 | `TestValidateFilenameSlugAccepts` + `TestValidateFileInputsWiring::test_existing_*` |
| AC16/AC17 | TASK 4 | grep verification |
| AC18 | TASK 4 | manual visual verification + Playwright command in conventions.md |
| AC-Dep1 | TASK 5 | pip-audit post-bump verification |
| AC-Doc1 | TASK 6 | doc-checklist cross-grep |

**Threat coverage table:**

| Threat | Task | Verification |
|--------|------|--------------|
| T1 + T1b | TASK 1 | 4 sanitize tests; revert-fail discipline |
| T2 (sources RMW) | TASK 2 | TestUpdateSourcesMappingRMWLock |
| T3 (index RMW) | TASK 2 | TestUpdateIndexBatchRMWLock |
| T4 (empty wiki_pages) | TASK 2 | TestUpdateSourcesMappingEmptyList + caplog |
| T5 (backtick dedup) | TASK 2 | TestUpdateSourcesMappingBacktickDedup with revert-fail |
| T6a-d (filename validator) | TASK 3 | parametrized rejection cases |
| T6e (no false positive) | TASK 3 | TestValidateFilenameSlugAccepts |
| T7 (doc drift) | TASK 4 | grep + manual visual |
| T8 (warning suppression) | TASK 2 | caplog assertion in TestUpdateSourcesMappingEmptyList |
| T9 (GitPython) | TASK 5 | pip-audit post-bump |

All Step-5 CONDITIONS map to test expectations or self-check greps above. NO ACs uncovered.
