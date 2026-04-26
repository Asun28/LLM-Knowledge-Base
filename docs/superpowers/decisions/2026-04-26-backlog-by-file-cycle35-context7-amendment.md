# Cycle 35 — Step 6 Context7 Amendment

Date: 2026-04-26
Verified library: `/websites/playwright_dev_python`

## Verified

- `sync_playwright()` context manager — confirmed.
- `browser.new_page(viewport=, device_scale_factor=)` — works as documented shortcut (internally creates a context). Equivalent canonical form is `browser.new_context(viewport=, device_scale_factor=).new_page()`.
- `page.goto(url, wait_until="networkidle")` — `wait_until` accepts `"load"`, `"domcontentloaded"`, `"networkidle"`, `"commit"`. `"networkidle"` is correct for a static HTML diagram with no XHR.
- `page.screenshot(path=, full_page=True, type="png")` — all three kwargs are valid per official `class-page` API doc.

## Decision

Keep R2 Q7's snippet but use the canonical `new_context()` + `new_page()` form for clarity (one extra line, zero behavior change). Final snippet for AC18 + `docs/reference/conventions.md`:

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

No design changes; R2 snippet was correct in intent and would work with the shortcut form.
