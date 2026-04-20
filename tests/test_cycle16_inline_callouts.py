"""Cycle 16 AC11 + AC12 + T5 + T12 — inline callout parser + check.

Behavioural regressions on `parse_inline_callouts` and
`check_inline_callouts`. Direct import; no source-scan assertions.
"""

from pathlib import Path

from kb.lint.checks import (
    _CALLOUT_BODY_CHAR_CAP,
    _CALLOUTS_CROSS_PAGE_CAP,
    _CALLOUTS_PER_PAGE_CAP,
    check_inline_callouts,
    parse_inline_callouts,
)


def _write_body(wiki_dir: Path, page_id: str, body: str) -> Path:
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{page_id}"\n'
        'source: ["raw/articles/x.md"]\n'
        "created: 2026-04-01\n"
        "updated: 2026-04-01\n"
        "type: concept\n"
        "confidence: stated\n"
        f"---\n\n{body}",
        encoding="utf-8",
    )
    return path


class TestParseInlineCallouts:
    def test_all_four_markers_recognised(self) -> None:
        content = (
            "body line 1\n"
            "> [!contradiction] C1\n"
            "> [!gap] G1\n"
            "> [!stale] S1\n"
            "> [!key-insight] K1\n"
            "body line 6\n"
        )
        out = parse_inline_callouts(content)
        markers = [c["marker"] for c in out]
        assert markers == ["contradiction", "gap", "stale", "key-insight"]

    def test_case_insensitive_marker_match(self) -> None:
        content = "> [!Gap] capitalised\n> [!CONTRADICTION] shouty\n"
        out = parse_inline_callouts(content)
        assert [c["marker"] for c in out] == ["gap", "contradiction"]

    def test_unclosed_bracket_not_matched(self) -> None:
        # No closing `]` — must NOT match.
        content = "> [!gap missing close bracket\n"
        out = parse_inline_callouts(content)
        assert out == []

    def test_line_numbers_are_1_based(self) -> None:
        content = "line 1\nline 2\n> [!gap] here\n"
        out = parse_inline_callouts(content)
        assert out[0]["line"] == 3

    def test_mid_line_callout_not_matched(self) -> None:
        # `> [!gap]` must anchor at the start of a line (`^`).
        content = "prefix > [!gap] would-be-mid-line\n"
        out = parse_inline_callouts(content)
        assert out == []

    def test_body_over_1mb_returns_empty(self) -> None:
        """T5 — page body exceeding 1 M codepoints returns [] (DoS bound)."""
        huge = "x" * (_CALLOUT_BODY_CHAR_CAP + 1)
        body = f"> [!gap] should-be-skipped\n{huge}"
        out = parse_inline_callouts(body)
        assert out == []

    def test_500_match_per_page_truncation(self) -> None:
        """T12 — per-page cap 500 + truncation sentinel."""
        content = "\n".join(f"> [!gap] item {i}" for i in range(_CALLOUTS_PER_PAGE_CAP + 50))
        out = parse_inline_callouts(content)
        assert len(out) == _CALLOUTS_PER_PAGE_CAP + 1
        assert out[-1]["marker"] == "__truncated__"

    def test_empty_content_returns_empty(self) -> None:
        assert parse_inline_callouts("") == []

    def test_text_field_contains_full_matched_line(self) -> None:
        content = "> [!gap] explanation of gap\n"
        out = parse_inline_callouts(content)
        assert out[0]["text"] == "> [!gap] explanation of gap"


class TestCheckInlineCallouts:
    def test_aggregates_across_pages(self, tmp_wiki) -> None:
        _write_body(tmp_wiki, "concepts/a", "> [!gap] first\nbody\n")
        _write_body(tmp_wiki, "concepts/b", "> [!stale] second\n")
        out = check_inline_callouts(tmp_wiki)
        markers = sorted(c["marker"] for c in out)
        assert markers == ["gap", "stale"]
        assert {c["page_id"] for c in out} == {"concepts/a", "concepts/b"}

    def test_skips_unreadable_pages(self, tmp_wiki, monkeypatch, caplog) -> None:
        """Consistent with other checks — log and skip on read failure."""
        _write_body(tmp_wiki, "concepts/ok", "> [!gap] ok\n")
        from kb.lint import checks

        orig_read = Path.read_text

        def _raise(self, *a, **k):
            if self.name == "ok.md":
                raise OSError("simulated bad read")
            return orig_read(self, *a, **k)

        monkeypatch.setattr(Path, "read_text", _raise)
        out = checks.check_inline_callouts(tmp_wiki)
        # No exception; returns [] because the only page failed to read.
        assert out == []

    def test_empty_wiki_returns_empty(self, tmp_wiki) -> None:
        assert check_inline_callouts(tmp_wiki) == []

    def test_cross_page_cap_enforced(self, tmp_wiki, monkeypatch) -> None:
        """T12 cross-page cap — once exceeded, return with truncation record."""
        _write_body(tmp_wiki, "concepts/a", "no callouts here\n")

        # Monkeypatch parse_inline_callouts to return > 10K callouts per page
        from kb.lint import checks

        def _fake_parse(content: str) -> list[dict]:
            return [{"marker": "gap", "line": i, "text": "> [!gap] x"} for i in range(50_000)]

        monkeypatch.setattr(checks, "parse_inline_callouts", _fake_parse)
        out = checks.check_inline_callouts(tmp_wiki)
        assert len(out) == _CALLOUTS_CROSS_PAGE_CAP + 1
        assert out[-1]["marker"] == "__truncated__"
