"""Evidence trail — append-only provenance sections in wiki pages."""

import logging
import re
from datetime import date
from pathlib import Path

from kb.utils.io import atomic_text_write, file_lock

logger = logging.getLogger(__name__)

# H12 fix (Phase 4.5 HIGH): Sentinel that anchors evidence trail entries.
# FIRST-match heuristic: when upgrading a pre-sentinel page, place the sentinel
# at the end of the FIRST ## Evidence Trail section found (not LAST — attacker-planted
# forgeries land later in the body).
SENTINEL = "<!-- evidence-trail:begin -->"


def _neutralize_pipe(value: str) -> str:
    """Item 28 (cycle 2): backtick-wrap values containing `|` so the pipe is
    unambiguous inside the evidence-trail table-like row format.
    """
    if "|" in value:
        return f"`{value}`"
    return value


def build_evidence_entry(
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> str:
    """Build a single evidence trail entry line (byte-clean stored form).

    Format: - YYYY-MM-DD | source_ref | action

    Cycle 2 PR review R1 MAJOR: the stored entry MUST stay byte-for-byte
    compatible with pre-cycle-2 evidence trails. Backtick-wrapping for
    pipe-containing values moves to `format_evidence_entry` (RENDER layer),
    which is now the single consumer used by `append_evidence_trail`.
    """
    d = entry_date or date.today().isoformat()
    return f"- {d} | {source_ref} | {action}"


def format_evidence_entry(date_str: str, source: str, summary: str) -> str:
    """Render an evidence trail line with backtick-escaped pipes (item 28).

    Cycle 2 PR review R3 MAJOR: signature restored to the original positional
    contract `(date_str, source, summary)` — callers that predated cycle 2
    (or internal call sites matching the high-cycle1 plan) keep working; only
    the internal pipe-escape behaviour changes. This is the render form that
    `append_evidence_trail` persists. The escape is applied render-time only —
    callers building the entry purely for logical comparison should use
    `build_evidence_entry` to preserve the raw string.
    """
    return f"- {date_str} | {_neutralize_pipe(source)} | {_neutralize_pipe(summary)}"


def render_initial_evidence_trail(
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> str:
    """Render the initial ``## Evidence Trail`` section for a new page.

    Cycle 24 AC1 — used by ``_write_wiki_page`` to emit the trail INLINE in the
    first write, eliminating the two-write race between page body and subsequent
    ``append_evidence_trail``. Reuses ``format_evidence_entry`` for pipe
    neutralization so the rendered string stays byte-compatible with the
    append-time render path.
    """
    d = entry_date or date.today().isoformat()
    entry = format_evidence_entry(d, source_ref, action)
    return f"\n## Evidence Trail\n{SENTINEL}\n{entry}\n"


# Cycle 24 AC14 — header regex tolerates CRLF and trailing whitespace (existing
# lint convention for section headers). ``re.MULTILINE`` anchors ``^`` to line
# starts; the pattern matches the HEADER LINE ending including the newline so
# ``match.end()`` points to the first byte of the section body.
_EVIDENCE_TRAIL_HEADER_RE = re.compile(r"^## Evidence Trail[ \t]*\r?\n", re.MULTILINE)
# Any subsequent ``^## `` heading terminates the Evidence Trail section span.
_NEXT_H2_RE = re.compile(r"^## ", re.MULTILINE)
# Cycle 24 PR #38 R1 Sonnet BLOCKER B1 — match fenced code blocks (``` ... ```)
# so the header regex above does not mis-match a literal `## Evidence Trail`
# line INSIDE a fenced code example in the page body. ``re.DOTALL`` lets ``.``
# span newlines; non-greedy ``.*?`` stops at the first closing fence.
_FENCED_CODE_RE = re.compile(r"^```[^\n]*\n.*?^```[^\n]*$", re.MULTILINE | re.DOTALL)


def _mask_fenced_blocks(content: str) -> str:
    """Replace fenced-code-block contents with spaces of equal length so regex
    searches over the RESULT find headers only in prose — not inside fenced
    examples. Preserves byte offsets so ``match.start()`` / ``match.end()``
    computed against the masked string are valid positions in the ORIGINAL
    ``content``. Fenced-block bytes become spaces (except newlines, which are
    preserved to keep line-number semantics of ``re.MULTILINE`` anchors).
    """

    def _blank(match: re.Match) -> str:
        text = match.group(0)
        # Replace every non-newline char with a space; keep newlines so `^` / `$`
        # multiline anchors still hit legitimate line boundaries.
        return "".join("\n" if ch == "\n" else " " for ch in text)

    return _FENCED_CODE_RE.sub(_blank, content)


def append_evidence_trail(
    page_path: Path,
    source_ref: str,
    action: str,
    entry_date: str | None = None,
) -> None:
    """Append an evidence trail entry to a wiki page.

    Cycle 24 AC14 — sentinel search is SPAN-LIMITED within the ``## Evidence
    Trail`` section (from the header to the next ``^## `` heading or EOF). An
    attacker-planted ``<!-- evidence-trail:begin -->`` substring in the page
    body, frontmatter, or any other section is IGNORED by construction — only
    sentinels that fall inside the real section span are honoured.

    Fallback matrix:

    - Header present + sentinel inside section span → insert after sentinel
      (existing cycle-1 H12 behaviour).
    - Header present + no sentinel inside section span → plant sentinel at
      header end + insert entry (sentinel-migration for pre-cycle-1 pages).
    - No header at all → create fresh ``## Evidence Trail`` section at EOF
      with sentinel + entry. A body sentinel without a real header is treated
      as attacker-planted noise and left intact in the body; it is NOT used
      as an anchor.

    H12 fix (Phase 4.5 HIGH) + cycle 24 AC14 together: the sentinel anchors
    reverse-chronological inserts WITHIN the Evidence Trail section; no
    forgery elsewhere in the file can hijack future appends.
    """
    # H2 fix (Phase 4.5 HIGH): lock the page file for the entire read→modify→write window
    # so concurrent append_evidence_trail calls on the same page don't lose entries.
    with file_lock(page_path):
        content = page_path.read_text(encoding="utf-8")
        d = entry_date or date.today().isoformat()
        entry = format_evidence_entry(d, source_ref, action)

        # Cycle 24 PR #38 R1 Sonnet BLOCKER B1 — mask fenced code blocks before
        # regex matching so a literal `## Evidence Trail` line inside a code
        # example does not hijack header detection. `_mask_fenced_blocks`
        # preserves byte offsets so match positions remain valid in the
        # original `content`.
        masked = _mask_fenced_blocks(content)
        header_match = _EVIDENCE_TRAIL_HEADER_RE.search(masked)
        if header_match is not None:
            # Section span = [header_end, next_h2_start) or [header_end, EOF).
            # Both positions computed against `masked` are equally valid in
            # `content` because _mask_fenced_blocks preserves byte offsets.
            section_start = header_match.end()
            tail = masked[section_start:]
            next_h2 = _NEXT_H2_RE.search(tail)
            section_end = section_start + next_h2.start() if next_h2 else len(content)
            span = content[section_start:section_end]

            if SENTINEL in span:
                # Sentinel inside section — insert new entry right after it.
                sentinel_pos = section_start + span.index(SENTINEL)
                after_sentinel = sentinel_pos + len(SENTINEL)
                # Skip the newline immediately after the sentinel (if present).
                if after_sentinel < len(content) and content[after_sentinel] == "\n":
                    after_sentinel += 1
                content = content[:after_sentinel] + entry + "\n" + content[after_sentinel:]
            else:
                # Header present but no sentinel in section — plant sentinel at
                # header end and insert entry (sentinel-migration path for
                # legacy pre-cycle-1 H12 pages).
                content = (
                    content[:section_start]
                    + SENTINEL
                    + "\n"
                    + entry
                    + "\n"
                    + content[section_start:]
                )
        else:
            # No ``## Evidence Trail`` header anywhere — create fresh section
            # at EOF. Any body-planted sentinel is IGNORED by construction: the
            # span-limited search above never reaches it. The attacker-planted
            # bytes remain as dead markdown in the body.
            content = (
                content.rstrip("\n") + "\n\n## Evidence Trail\n" + SENTINEL + "\n" + entry + "\n"
            )

        atomic_text_write(content, page_path)
