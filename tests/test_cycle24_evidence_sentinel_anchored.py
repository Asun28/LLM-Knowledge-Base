"""Cycle 24 AC14/AC15 — sentinel-anchor hardening for `append_evidence_trail`.

Regression tests that the sentinel search is section-span-limited. Attacker-planted
``<!-- evidence-trail:begin -->`` substrings in the page body, frontmatter, or
other sections MUST NOT hijack future evidence appends. Divergent-fail harness:
each test must fail if `append_evidence_trail` is reverted to the pre-cycle-24
whole-file `str.index(SENTINEL)` behaviour.

Closes threat T5 + CONDITION 9 + CONDITION 10 from
`docs/superpowers/decisions/2026-04-23-cycle24-design.md`.
"""

from __future__ import annotations

from kb.ingest.evidence import SENTINEL, append_evidence_trail


def _seed_page(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_body_planted_sentinel_before_real_header_ignored(tmp_path):
    """AC15 scenario 1 — attacker plants SENTINEL literal before the real section.

    The real ``## Evidence Trail`` section comes later with its own legitimate
    sentinel. The new entry MUST land under the real sentinel, inside the real
    section, not after the attacker-planted one.
    """
    page = tmp_path / "page.md"
    body = (
        "---\ntitle: page\n---\n\n"
        "# Body\n\n"
        f"Attacker note: {SENTINEL} planted this in body.\n\n"
        "## Evidence Trail\n"
        f"{SENTINEL}\n"
        "- 2026-01-01 | raw/old.md | Prior entry\n"
    )
    _seed_page(page, body)

    append_evidence_trail(page, "raw/new.md", "Added new source", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    # Structural: find real section span and assert new entry is inside it.
    # The real section starts at "## Evidence Trail" and extends to EOF.
    ev_header = result.index("## Evidence Trail")
    real_section = result[ev_header:]
    assert "2026-04-23 | raw/new.md | Added new source" in real_section, (
        "New entry must land inside the real ## Evidence Trail section"
    )
    # Attacker note + its sentinel remain in body unchanged.
    assert f"Attacker note: {SENTINEL} planted this in body." in result[:ev_header], (
        "Body-planted sentinel must remain in body untouched"
    )
    # The NEW entry must NOT appear in the body before the real section.
    assert "2026-04-23 | raw/new.md" not in result[:ev_header], (
        "New entry must not land in body where attacker sentinel is"
    )


def test_body_planted_sentinel_under_other_section_ignored(tmp_path):
    """AC15 scenario 2 — sentinel planted inside `## References` section.

    A ``## References`` section BEFORE the real ``## Evidence Trail`` contains
    the sentinel literal. The new entry must land in the real Evidence Trail
    section, not in References.
    """
    page = tmp_path / "page.md"
    body = (
        "# Body\n\n"
        "## References\n\n"
        f"- See {SENTINEL} for details (literal).\n\n"
        "## Evidence Trail\n"
        f"{SENTINEL}\n"
        "- 2026-01-01 | raw/old.md | Prior entry\n"
    )
    _seed_page(page, body)

    append_evidence_trail(page, "raw/new.md", "Added from references", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    references_section = result[result.index("## References") : result.index("## Evidence Trail")]
    evidence_section = result[result.index("## Evidence Trail") :]

    assert "2026-04-23 | raw/new.md | Added from references" in evidence_section, (
        "New entry must land in Evidence Trail section"
    )
    assert "2026-04-23 | raw/new.md" not in references_section, (
        "New entry must not land in References section"
    )


def test_crlf_header_with_trailing_whitespace_matched(tmp_path):
    """AC15 scenario 3 — CRLF line endings + trailing whitespace in header.

    Real-world Windows-authored pages can have ``## Evidence Trail  \\r\\n``
    (trailing spaces + CRLF). The regex must still match.
    """
    page = tmp_path / "page.md"
    body = (
        "# Body\r\n\r\n## Evidence Trail  \r\n"
        f"{SENTINEL}\r\n"
        "- 2026-01-01 | raw/old.md | Prior entry\r\n"
    )
    page.write_bytes(body.encode("utf-8"))

    append_evidence_trail(page, "raw/new.md", "CRLF test", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    assert "2026-04-23 | raw/new.md | CRLF test" in result, (
        "Entry must land even with CRLF + trailing-whitespace header"
    )


def test_sentinel_only_no_header_creates_fresh_section(tmp_path):
    """AC15 scenario 4 — attacker plants sentinel but no real header exists.

    A body sentinel without a matching ``## Evidence Trail`` header is purely
    an attacker forgery. `append_evidence_trail` MUST ignore it and create a
    fresh section at EOF with a new sentinel; the body sentinel stays as
    dead markdown. PR #38 R1 Sonnet MAJOR M2: strengthened to be divergent-fail
    against AC14 revert — the pre-cycle-24 `content.index(SENTINEL)` would
    insert the new entry immediately after the attacker-planted body sentinel
    instead of creating a fresh section. We assert on the entry's POSITION
    relative to the attacker sentinel so revert flips the assertion.
    """
    page = tmp_path / "page.md"
    attacker_line = f"Attacker says: {SENTINEL} here is forged content."
    body = f"# Body\n\n{attacker_line}\n"
    _seed_page(page, body)

    append_evidence_trail(page, "raw/new.md", "Attacker-ignore", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    # Body sentinel unchanged.
    assert attacker_line in result, "Attacker-planted body sentinel must remain untouched"
    # Fresh Evidence Trail section created at EOF.
    assert "## Evidence Trail" in result, "Fresh Evidence Trail section created"
    ev_idx = result.index("## Evidence Trail")
    ev_section = result[ev_idx:]
    assert SENTINEL in ev_section, "Fresh section has its own sentinel"
    assert "2026-04-23 | raw/new.md | Attacker-ignore" in ev_section, (
        "New entry lands in fresh section"
    )
    # Count sentinels — should be exactly 2 now: attacker's + fresh-section's.
    assert result.count(SENTINEL) == 2, (
        "Body sentinel + fresh section sentinel = 2; no extra re-planting"
    )

    # Divergent-fail (PR #38 R1 Sonnet MAJOR M2): the new entry line MUST come
    # AFTER the real `## Evidence Trail` header (i.e. inside the fresh section),
    # not before it. A revert to pre-cycle-24 `str.index(SENTINEL)` on a page
    # with body-planted sentinel would insert the entry AT THE BODY SENTINEL
    # position, which is BEFORE any header. Asserting relative position defeats
    # that revert.
    entry_pos = result.index("2026-04-23 | raw/new.md | Attacker-ignore")
    header_pos = result.index("## Evidence Trail")
    assert entry_pos > header_pos, (
        f"New entry (at {entry_pos}) must come AFTER the real section header "
        f"(at {header_pos}); pre-cycle-24 revert would place it at the attacker "
        f"sentinel position which is BEFORE any header."
    )
    attacker_sentinel_pos = result.index(attacker_line)
    assert entry_pos > attacker_sentinel_pos, (
        "New entry must land after the attacker sentinel line in the file, not next to it"
    )


def test_fenced_code_block_header_does_not_hijack(tmp_path):
    """PR #38 R1 Sonnet BLOCKER B1 — `## Evidence Trail` inside a fenced code
    block must NOT be detected as the real section header.

    Without the fence-masking fix in `_mask_fenced_blocks`, the header regex
    finds the code-block header first and plants the sentinel INSIDE the
    fenced block. The new entry then appears inside the code example, not in
    the real Evidence Trail section.
    """
    page = tmp_path / "page.md"
    body = (
        "# Body\n\n"
        "Example in docs:\n\n"
        "```markdown\n"
        "## Evidence Trail\n"
        "- 2000-01-01 | raw/doc.md | example\n"
        "```\n\n"
        "## Evidence Trail\n"
        f"{SENTINEL}\n"
        "- 2026-01-01 | raw/old.md | Prior real entry\n"
    )
    _seed_page(page, body)

    append_evidence_trail(page, "raw/new.md", "Fenced header test", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    # Locate the REAL section (after the closing ``` fence).
    closing_fence_pos = result.index("```\n\n## Evidence Trail")
    real_section_start = result.index("## Evidence Trail", closing_fence_pos)
    real_section = result[real_section_start:]
    assert "2026-04-23 | raw/new.md | Fenced header test" in real_section, (
        "New entry MUST land in the real section AFTER the fence, not inside it"
    )
    # Anti-assertion: the new entry must NOT appear inside the fenced block.
    fenced_block_start = result.index("```markdown")
    fenced_block_end = result.index("```\n\n## Evidence Trail")
    fenced_span = result[fenced_block_start:fenced_block_end]
    assert "2026-04-23 | raw/new.md" not in fenced_span, (
        "New entry must NOT be injected inside a fenced code example — the "
        "BLOCKER B1 revert (removing _mask_fenced_blocks) would trigger this."
    )


def test_tilde_fence_and_four_backtick_fence_respected(tmp_path):
    """PR #38 R2 Codex MAJOR — `_mask_fenced_blocks` must handle both tilde
    fences (`~~~`) and 4+ backtick fences (`` ```` ``) per CommonMark spec.
    Without these variants the simple 3-backtick regex lets an attacker
    embed `## Evidence Trail` inside a tilde block to bypass the mask.
    """
    page = tmp_path / "page.md"
    body = (
        "# Body\n\n"
        "Example with tilde fence:\n\n"
        "~~~markdown\n"
        "## Evidence Trail\n"
        "- 2000-01-01 | raw/tilde.md | fake\n"
        "~~~\n\n"
        "Example with 4-backtick fence containing a 3-backtick block:\n\n"
        "````text\n"
        "## Evidence Trail\n"
        "```\n"
        "## Evidence Trail\n"
        "```\n"
        "````\n\n"
        "## Evidence Trail\n"
        f"{SENTINEL}\n"
        "- 2026-01-01 | raw/old.md | Prior real entry\n"
    )
    _seed_page(page, body)

    append_evidence_trail(page, "raw/new.md", "Fence variants", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    # The new entry MUST land in the real section at EOF, not in either fenced block.
    real_header_pos = result.rindex("## Evidence Trail")
    real_section = result[real_header_pos:]
    assert "2026-04-23 | raw/new.md | Fence variants" in real_section, (
        "New entry must land in real section after both fence variants"
    )
    # Neither fenced block should contain the new entry.
    tilde_start = result.index("~~~markdown")
    tilde_end = result.index("~~~\n\n", tilde_start)
    assert "2026-04-23 | raw/new.md" not in result[tilde_start:tilde_end], (
        "Tilde fence must mask correctly — entry must NOT appear inside it"
    )
    four_backtick_start = result.index("````text")
    four_backtick_end = result.index("````\n\n", four_backtick_start)
    assert "2026-04-23 | raw/new.md" not in result[four_backtick_start:four_backtick_end], (
        "4-backtick fence must mask correctly — entry must NOT appear inside it"
    )


def test_header_only_no_sentinel_plants_sentinel(tmp_path):
    """Legacy pre-cycle-1 H12 page: header exists but no sentinel inside.

    Sentinel-migration path: on first append, plant sentinel at header end
    and insert entry (preserves existing cycle-1 H12 behaviour).
    """
    page = tmp_path / "page.md"
    body = (
        "# Body\n\n## Evidence Trail\n"
        "- 2026-01-01 | raw/old.md | Legacy entry (no sentinel in original page)\n"
    )
    _seed_page(page, body)
    assert SENTINEL not in body

    append_evidence_trail(page, "raw/new.md", "Migration path", entry_date="2026-04-23")

    result = page.read_text(encoding="utf-8")
    assert SENTINEL in result, "Sentinel migrated to header-end"
    # Sentinel is now immediately after the header.
    ev_header_end = result.index("## Evidence Trail\n") + len("## Evidence Trail\n")
    assert result[ev_header_end:].startswith(SENTINEL), "Sentinel planted right after header"
    assert "2026-04-23 | raw/new.md | Migration path" in result
