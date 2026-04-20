"""Cycle 15 AC6/AC25 — check_authored_by_drift with Evidence Trail span scope.

Tests the T5 false-positive mitigation: `action: ingest` OUTSIDE the
`## Evidence Trail` section must NOT flag the page.
"""

from __future__ import annotations

from pathlib import Path

from kb.lint.checks import check_authored_by_drift


def _write_page(
    wiki_dir: Path,
    pid: str,
    authored_by: str | None,
    body: str,
    page_type: str = "concept",
) -> Path:
    subdir = {
        "summary": "summaries",
        "concept": "concepts",
        "entity": "entities",
    }[page_type]
    path = wiki_dir / subdir / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    ab_line = f"authored_by: {authored_by}\n" if authored_by else ""
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-01-01
updated: 2026-04-20
type: {page_type}
confidence: stated
{ab_line}---
{body}
""",
        encoding="utf-8",
    )
    return path


class TestHumanDrift:
    def test_human_with_in_scope_ingest_flagged(self, tmp_path):
        body = """Intro.

## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: ingest | stated
- 2026-04-01 | raw/articles/foo.md | action: edit | stated
"""
        _write_page(tmp_path, "human-page", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["check"] == "authored_by_drift"
        assert issues[0]["severity"] == "warning"
        assert "human-page" in issues[0]["page"]

    def test_human_with_only_edit_not_flagged(self, tmp_path):
        body = """Intro.

## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: edit | stated
- 2026-04-01 | raw/articles/foo.md | action: refine | stated
"""
        _write_page(tmp_path, "edited-human", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == []

    def test_hybrid_with_in_scope_ingest_not_flagged(self, tmp_path):
        body = """## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: ingest | stated
"""
        _write_page(tmp_path, "hybrid-page", "hybrid", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == []

    def test_llm_with_in_scope_ingest_not_flagged(self, tmp_path):
        body = """## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: ingest | stated
"""
        _write_page(tmp_path, "llm-page", "llm", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == []

    def test_no_authored_by_not_flagged(self, tmp_path):
        body = """## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: ingest | stated
"""
        _write_page(tmp_path, "no-ab", None, body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == []


class TestT5FalsePositiveMitigation:
    """AC25 — regex scope must be the Evidence Trail span, not body-wide."""

    def test_ingest_action_in_code_fence_above_trail_not_flagged(self, tmp_path):
        """T5 — `action: ingest` in a code fence BEFORE the Evidence Trail is NOT flagged."""
        body = """Intro.

Example ingest flow:

```yaml
- date: 2026-04-20
  action: ingest
  source: raw/articles/foo.md
```

## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: edit | stated
"""
        _write_page(tmp_path, "meta-page", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == [], "action: ingest outside Evidence Trail section must not flag"

    def test_ingest_action_in_prose_above_trail_not_flagged(self, tmp_path):
        body = """This page explains how action: ingest writes the summary.

## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: edit | stated
"""
        _write_page(tmp_path, "docs-page", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == []

    def test_page_without_evidence_trail_not_flagged(self, tmp_path):
        """T5 — page lacking `## Evidence Trail` section emits no warning."""
        body = """Human-authored prose with no trail section.

action: ingest mentioned in prose but no trail.
"""
        _write_page(tmp_path, "no-trail", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == [], "absence of trail signal is not a drift event"

    def test_trail_terminator_by_next_h2(self, tmp_path):
        """Regex scope ends at the next `## ` header."""
        body = """## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: edit | stated

## Related

- action: ingest documented elsewhere
"""
        _write_page(tmp_path, "terminated", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert issues == [], (
            "action: ingest in Related section (after trail terminator) must not flag"
        )

    def test_trail_extends_to_eof_when_no_next_h2(self, tmp_path):
        """AC25 — Evidence Trail followed by EOF still scans correctly."""
        body = """## Evidence Trail

- 2026-04-20 | raw/articles/foo.md | action: ingest | stated
"""
        _write_page(tmp_path, "eof-page", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert len(issues) == 1
        assert "eof-page" in issues[0]["page"]


class TestCRLFHandling:
    """AC25 — Windows line endings must not defeat the anchor."""

    def test_crlf_evidence_trail_detected(self, tmp_path):
        """CRLF body with `## Evidence Trail\\r\\n` still matches the anchor."""
        body_lf = "## Evidence Trail\n\n- 2026-04-20 | raw/articles/foo.md | action: ingest\n"
        body_crlf = body_lf.replace("\n", "\r\n")
        path = tmp_path / "concepts" / "crlf-page.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            (
                """---
title: crlf-page
source:
  - raw/articles/x.md
created: 2026-01-01
updated: 2026-04-20
type: concept
confidence: stated
authored_by: human
---
"""
                + body_crlf
            ).encode("utf-8")
        )
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert len(issues) == 1, "CRLF line endings must still match anchor"

    def test_trailing_whitespace_on_header_still_matches(self, tmp_path):
        """R1 MINOR 1 — hand-edited `## Evidence Trail  \\n` (trailing spaces) matches."""
        body = "## Evidence Trail   \n\n- 2026-04-20 | raw/articles/foo.md | action: ingest\n"
        _write_page(tmp_path, "ws-header", "human", body)
        issues = check_authored_by_drift(wiki_dir=tmp_path)
        assert len(issues) == 1, (
            "trailing whitespace on Evidence Trail header must not defeat the anchor"
        )
