# R2 Codex Design Evaluation — Cycle 35 (edge cases)

(Output captured 2026-04-26. Becomes input to Step 5 decision gate.)

## Q1 — Sanitize regex edges
**Verdict:** AMEND
**Evidence:** `src/kb/utils/sanitize.py:11`, `src/kb/utils/sanitize.py:18`, threat-model T1
**Finding:** Proposed slash-UNC pattern matches `//host/share/path` (good) but ALSO matches `https://host/path` (URI overmatch — would redact every URL in logs/wiki content). Misses `//?/UNC/server/share/...`.
**Recommendation:** Add a slash-long-path alternative AND prevent URI overmatch:
- `r"|(?://\?/UNC/[^\s'\"]+/[^\s'\"]+(?:/[^\s'\"]*)?)"`
- `r"|(?<!:)(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)"`

## Q2 — File lock reentrance
**Verdict:** AMEND
**Evidence:** `src/kb/utils/io.py:294,321,355,392`
**Finding:** `file_lock` is `os.O_EXCL` lock-file based, NOT `threading.RLock`. No same-PID reentrance. If a caller already holds `file_lock(sources_file)` and calls a callee that re-acquires it, the callee self-waits until timeout → deadlock.
**Recommendation:** Lock only inside `_update_sources_mapping` and `_update_index_batch`; do NOT add a wrapper-level lock in `_write_index_files`. Document "callers must not hold the same target `file_lock` when invoking these helpers."

## Q3 — Empty list warning
**Verdict:** CONFIRMED-OK
**Evidence:** threat-model T8, `src/kb/ingest/pipeline.py:788`
**Finding:** T8 explicitly requires no missing-file warning when `wiki_pages == []`. Keep the warning for non-empty missing `_sources.md`.

## Q4 — Filename rejection set
**Verdict:** AMEND
**Evidence:** `src/kb/mcp/core.py:66`, `src/kb/mcp/app.py:230`
**Finding:** Reject NUL, `/`, `\`, `..`, non-ASCII, overlength, Windows reserved basenames. `_is_windows_reserved` is already imported — do not reimplement. Leading dot acceptable; trailing dot/space MUST be rejected (Windows trim aliasing).
**Recommendation:** In `_validate_filename_slug`: check `filename.strip() == filename`, ASCII encoding, NUL/separator/`..`, overlength, `_is_windows_reserved(filename)`.

## Q5 — Validator return contract
**Verdict:** AMEND
**Evidence:** `src/kb/mcp/core.py:167,178,695,832`
**Finding:** `_validate_file_inputs` returns `str | None`. Both callers use the string directly. The existing public contract must be preserved.
**Recommendation:** Implement `_validate_filename_slug(...) -> tuple[str, str | None]` (matches `_validate_save_as_slug` style for future-reuse), then inside `_validate_file_inputs`: `_, slug_err = _validate_filename_slug(filename); if slug_err: return slug_err` — public return stays `str | None`.

## Q6 — Xfail removal tests
**Verdict:** AMEND
**Evidence:** `tests/test_cycle33_mcp_core_path_leak.py:477,490`, requirements AC3
**Finding:** AC3's three absence checks prove only one positive case. Under-match and over-match guard tests are absent.
**Recommendation:** Remove the strict xfail and add: (a) positive `sanitize_text("//server/share/path.md")` redacts; (b) negative `sanitize_text("https://example.com/path")` unchanged; (c) negative `sanitize_text("//comment text")` unchanged.

## Q7 — Playwright re-render
**Verdict:** AMEND
**Recommendation:** Use this snippet:
```python
from pathlib import Path
from playwright.sync_api import sync_playwright
root = Path.cwd()
html = (root / "docs/architecture/architecture-diagram.html").resolve()
png = root / "docs/architecture/architecture-diagram.png"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=3)
    page.goto(html.as_uri(), wait_until="networkidle")
    page.screenshot(path=str(png), full_page=True, type="png")
    browser.close()
```

## Q8 — Backtick source-ref dedup
**Verdict:** CONFIRMED-OK
**Finding:** Switching both checks to `escaped_ref` is the correct minimal dedup fix.

## Q9 — Same-class peer scan
**Verdict:** CONFIRMED-OK
**Evidence:** `src/kb/utils/wiki_log.py:149` (already locked), no `_categories.md` writer in pipeline
**Finding:** Scope is correct — no extra peer locks needed.

## Q10 — GitPython bump
**Verdict:** CONFIRMED-OK
**Recommendation:** Verify zero `import git`/`from git` in `src/kb/` via `grep -rnE '^\s*(import git\b|from git\b)' src/kb/`.

## OPEN QUESTIONS (for Step 5)

1. `//?/UNC/...` — fixed in-cycle (R2 view) or deferred T1b (Approach C)?
2. `_validate_filename_slug` — strict ASCII-only or permissive?
3. Backtick source-ref escape — keep current backslash-escape or future migration to double-backtick code spans?
4. Add canonical Playwright command to `docs/reference/conventions.md`?

## CONDITIONS (Step 9 must satisfy)

1. UNC path redacts; URL `https://host/path` and C-comment `//comment text` do NOT redact.
2. Strict xfail removed; replacement tests fail under AC1 revert.
3. `_sources.md` and `index.md` RMW spans each locked WITHOUT nested same-file lock in `_write_index_files`.
4. Empty `wiki_pages` returns silently before `_sources.md` existence check.
5. `_validate_file_inputs` public return type stays `str | None`.
6. `_sources.md` dedup membership and per-line checks use IDENTICAL escaped bytes as the first-write path.
7. Architecture PNG regenerated from `architecture-diagram.html`.
8. GitPython pinned to `3.1.47`; no `import git`/`from git` in `src/kb/`.
