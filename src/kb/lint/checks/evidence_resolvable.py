"""Evidence-resolvability lint check.

Cycle 86 AC01. Asserts the invariant that every abstraction level carries a
resolvable pointer down to raw evidence: for each wiki page, every file-shaped
``source:`` frontmatter entry must resolve to a file that actually exists under
``raw/``.

This is the raw-source-side peer of ``dead_links.py``, which only covers
``[[wikilink]]`` targets — i.e. links BETWEEN pages. It is also the reverse
direction of ``consistency.py::check_source_coverage``, which finds raw files no
page references; this check finds page references with no raw file. A page can
pass both of those today while its entire provenance chain dangles.

Source: TencentDB-Agent-Memory README_CN, which states the invariant as
"no summary is an irreversible black box". The project already follows that
convention by hand; this check makes lint enforce it.
"""

from __future__ import annotations

import logging
import ntpath
import os
import stat
from pathlib import Path

import frontmatter

from kb.lint import checks
from kb.utils.pages import normalize_sources, scan_wiki_pages

logger = logging.getLogger(__name__)

# Bound the per-page work (threat T2). A page carrying more than this many
# source refs is already pathological — the cap keeps one malformed or
# adversarial page from dominating a lint run, and the truncation is reported
# rather than silent so the operator can see coverage was cut short. Sized to
# match the existing `_CALLOUTS_PER_PAGE_CAP` family in `inline_callouts.py`.
_EVIDENCE_REFS_PER_PAGE_CAP = 200

# Refs with these schemes are legitimately not files. URL-sourced pages are a
# supported shape (the augment path writes them), so flagging them would make
# the check unusable on any augmented page and train operators to ignore it.
_URL_SCHEMES = ("http://", "https://")


def _resolve_evidence_ref(ref: str, raw_dir: Path) -> Path | None:
    """Map a frontmatter ``source:`` ref onto a concrete path under ``raw_dir``.

    Returns the resolved path, or ``None`` if the ref does not land inside
    ``raw_dir``.

    The containment check is a security boundary, not a convenience (threat T1).
    Frontmatter is LLM-written, so a ref is attacker-influenceable content; a ref
    of ``../../../../etc/shadow`` would turn this check into a filesystem
    existence oracle, reporting through lint output whether arbitrary host paths
    exist. Callers MUST treat a ``None`` return as "report it, do not probe it"
    and never stat the path themselves.

    Absolute refs are handled by the same check rather than a separate branch:
    ``Path("raw") / "/etc/shadow"`` evaluates to ``/etc/shadow`` (pathlib
    discards the left operand when the right is absolute), which then fails
    ``is_relative_to`` and returns ``None``.
    """
    rel = ref.replace("\\", "/").strip()

    # LEXICAL rejection, before any filesystem call. `Path.resolve()` is itself
    # filesystem access — it stats and follows links — and on Windows resolving
    # a UNC ref such as `\\attacker.invalid\share\probe` can initiate SMB/DNS/
    # authentication traffic. Doing that and only THEN checking containment
    # would defeat the T1 boundary before the check ever ran: the probe is the
    # payload. So anything that could anchor outside `raw_dir` is rejected on
    # the string alone.
    #
    # (Backslashes are already normalised to `/` above, so a UNC path arrives
    # here as `//host/share`.)
    if rel.startswith("//") or rel.startswith("/") or ntpath.splitdrive(rel)[0]:
        return None

    # `make_source_ref` writes refs project-root-relative with a `raw/` prefix,
    # so strip it before re-anchoring under the caller's raw_dir. This is what
    # keeps the check working under the tmp_path sandbox, where raw_dir is not
    # literally named "raw".
    if rel.startswith("raw/"):
        rel = rel[len("raw/") :]
    if not rel:
        return None
    # Re-check after the prefix strip: `raw//host/share` becomes `/host/share`,
    # which is absolute again.
    if rel.startswith("/") or ntpath.splitdrive(rel)[0]:
        return None
    try:
        resolved = (raw_dir / rel).resolve()
        raw_resolved = raw_dir.resolve()
    except OSError as e:
        # Path resolution itself can fail on malformed refs (embedded NUL,
        # over-long components, Windows-illegal characters). Treat as
        # unresolvable rather than crashing the lint run.
        logger.debug("Could not resolve evidence ref %r: %s", ref, e)
        return None
    if not resolved.is_relative_to(raw_resolved):
        return None
    return resolved


def _is_regular_file_no_follow(path: Path) -> bool:
    """Report whether ``path`` is a regular file, without following a symlink.

    Cycle 87 AC03 (cycle-86 Codex review MINOR). ``_resolve_evidence_ref`` decides
    containment against a resolved path, and the existence check then ran as a
    separate ``Path.is_file()``. Between the two, replacing the final component
    under ``raw/`` with a link to somewhere outside it made the stat follow the
    link, so lint output became a filesystem-existence oracle for host paths —
    the same T1 boundary the containment check exists to hold.

    ``os.lstat`` closes that: it never follows a final-component symlink, so the
    answer describes the entry the containment check accepted rather than
    whatever it was swapped for. This deviates from the BACKLOG's suggested
    ``_open_no_follow`` + ``fstat`` shape (DESIGN-AMEND) for three reasons —
    ``lstat`` opens nothing, so it has no descriptor to leak and no side effects
    on FIFOs or device nodes; it needs no platform branch; and
    ``_open_no_follow`` misreads a plain ``ENOENT`` as "O_NOFOLLOW unsupported"
    and emits a spurious once-per-process warning, which a lint check that
    routinely meets missing files would fire constantly.

    Honest scope: this closes the FINAL-component swap. Swapping an ANCESTOR
    directory is not closed, because both this and the ``O_NOFOLLOW`` shape
    re-walk the ancestors; only ``openat2(RESOLVE_BENEATH)`` would, and that is
    Linux-5.6+ only. The residual leak stays a boolean, and it still requires
    local write access to ``raw/``.
    """
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except (OSError, ValueError):
        # Missing, unreadable, or a malformed path (embedded NUL) — all of which
        # mean "no resolvable evidence file here", not a lint-run crash.
        return False


def check_evidence_resolvable(
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find ``source:`` frontmatter entries that do not resolve to a real file.

    Args:
        wiki_dir: Path to wiki directory.
        raw_dir: Path to raw directory.
        pages: Pre-scanned page paths (shared by the runner across checks to
            avoid re-walking the wiki tree per check).

    Returns:
        List of dicts: {check, severity, page, source, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    raw_dir = raw_dir or checks.RAW_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    issues: list[dict] = []
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read page %s: %s", page_path, e)
            continue
        try:
            post = frontmatter.loads(content)
        except Exception as e:  # noqa: BLE001 — malformed YAML is check_frontmatter's job
            logger.debug("Skipping unparseable frontmatter in %s: %s", page_path, e)
            continue

        page_label = (
            str(page_path.relative_to(wiki_dir)).replace("\\", "/")
            if page_path.is_relative_to(wiki_dir)
            else str(page_path)
        )
        refs = normalize_sources(post.metadata.get("source"))

        if len(refs) > _EVIDENCE_REFS_PER_PAGE_CAP:
            issues.append(
                {
                    "check": "evidence_refs_truncated",
                    "severity": "warning",
                    "page": page_label,
                    "source": "",
                    "message": (
                        f"{page_label} declares {len(refs)} source refs; only the "
                        f"first {_EVIDENCE_REFS_PER_PAGE_CAP} were checked"
                    ),
                }
            )
            refs = refs[:_EVIDENCE_REFS_PER_PAGE_CAP]

        for ref in refs:
            if ref.lower().startswith(_URL_SCHEMES):
                continue
            resolved = _resolve_evidence_ref(ref, raw_dir)
            if resolved is None:
                # Deliberately NOT stat'd — see _resolve_evidence_ref (T1).
                # `error`, unlike the missing-file case below: no legitimate
                # workflow writes a source ref that points outside raw/. This
                # is either corruption or an injection attempt, so it should
                # fail the lint run rather than accumulate as a warning.
                issues.append(
                    {
                        "check": "evidence_unresolvable",
                        "severity": "error",
                        "page": page_label,
                        "source": ref,
                        "message": (
                            f"Source ref does not point inside raw/: {ref!r} "
                            f"(declared by {page_label})"
                        ),
                    }
                )
                continue
            if not _is_regular_file_no_follow(resolved):
                # `warning`, not `error` — deliberately weaker than the escape
                # case above. A raw source can legitimately be pruned, archived,
                # or moved after ingest, so a missing file is a hygiene signal
                # the operator judges rather than a hard failure. `error` here
                # would flip `kb lint`'s exit code on every repo that has ever
                # cleaned up a raw file. See the cycle-86 design DESIGN-AMEND.
                issues.append(
                    {
                        "check": "evidence_unresolvable",
                        "severity": "warning",
                        "page": page_label,
                        "source": ref,
                        "message": (
                            f"Source ref does not resolve to a file: {ref!r} "
                            f"(declared by {page_label})"
                        ),
                    }
                )

    return issues
