# Conventions
<!-- FORMAT GUIDE
Purpose: Canonical rules for wiki authorship, Evidence Trail, and Architecture Diagram Sync.
- Base Conventions: add a bullet only for a new cross-cutting rule affecting all wiki pages.
- Evidence Trail: document only behavioral invariants a caller must not violate (not API signatures).
- Architecture Diagram Sync: update the Playwright snippet if render parameters change (viewport, scale, format).
-->

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Conventions" section. Pairs with [architecture.md](architecture.md) (Evidence Trail API).

## Base Conventions

- All wiki pages must link claims back to specific `raw/` source files. Unsourced claims should be flagged.
- Use `[[wikilinks]]` for inter-page links within `wiki/`.
- Distinguish stated facts (`source says X`) from inferences (`based on A and B, we infer Y`).
- When updating wiki pages, prefer proposing diffs over full rewrites for auditability.
- Keep `wiki/index.md` under 500 lines — use category groupings, one line per page.
- Always install Python packages into the project `.venv`, never globally.

## Evidence Trail Convention

Every wiki page ingested via `ingest_source` grows an `## Evidence Trail` section whose entries `append_evidence_trail` inserts in **reverse-chronological order** (newest event at the top, immediately after a sentinel marker that identifies the section). The convention is load-bearing:

- **Append-only semantics.** Entries below the section are never rewritten; only new entries are prepended after the sentinel. Compiled truth ABOVE the section is still freely rewritten on re-ingest.
- **Reverse chronology, not bottom-append.** Unlike `wiki/log.md` (which appends at the bottom), the evidence trail reads newest-first so a reviewer scanning a long page immediately sees the most recent provenance event. Tools that parse evidence trails for historical timelines should iterate top-down and stop at the sentinel.
- **Sentinel discipline.** The ingest path writes a sentinel line exactly once per page; subsequent appends slip new entries between the sentinel and the previously-newest row. Hand-editing that removes the sentinel defeats append-ordering on the next ingest — treat the sentinel as machine-maintained.
- **When in doubt, trust the file.** Any manual auditor should read the evidence trail as printed; there is no separate index-of-evidence log to reconcile. The file is the ledger.

## Architecture Diagram Sync (MANDATORY)

Source `docs/architecture/architecture-diagram.html` → rendered PNG sibling → displayed in `README.md`. **Every HTML edit must re-render the PNG and commit it.** Render via headless Playwright at 1440×900 viewport (auto-expanded to content), `device_scale_factor=3`, `full_page=True`, `--type=png`.

Canonical re-render snippet (run from repo root after editing the HTML):

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
        color_scheme="dark",       # see note below
        reduced_motion="reduce",   # see note below
    )
    page = context.new_page()
    page.goto(html.as_uri(), wait_until="networkidle")
    page.wait_for_timeout(600)
    page.screenshot(path=str(png), full_page=True, type="png")
    browser.close()
```

**Both context flags are load-bearing.** Omitting either produces a broken PNG that still renders without raising:

- `reduced_motion="reduce"` — the page's inline script sets `data-animate` on `<html>`, and `html[data-animate] .reveal{opacity:0}` hides every section until an IntersectionObserver scrolls it into view. A `full_page` screenshot never scrolls, so without this flag everything below the fold is captured at opacity 0 and the PNG comes out mostly blank. The page already forces `.reveal` visible under `@media (prefers-reduced-motion:reduce)`, so this uses its own accessibility path instead of patching the DOM.
- `color_scheme="dark"` — the theme script falls back to the system preference, which is light in headless Chromium. Without this the PNG renders dark-on-light while the live site defaults to dark.

After rendering, open the PNG and confirm the stats band and tier chips near the bottom are present and legible. A blank lower half means one of the two flags was dropped.

Requires `playwright` installed in `.venv` plus `python -m playwright install chromium`. Only the non-`-detailed` HTML has a PNG sibling — the `-detailed` variant is HTML-only.
