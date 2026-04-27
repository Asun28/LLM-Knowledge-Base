"""Duplicate-slug lint checks."""

from pathlib import Path

from kb.config import DUPLICATE_SLUG_DISTANCE_THRESHOLD
from kb.lint import checks
from kb.utils.pages import page_id, scan_wiki_pages

_DUPLICATE_SLUGS_PAGE_CAP: int = 10_000


def _bounded_edit_distance(a: str, b: str, threshold: int) -> int:
    """Return Levenshtein distance between ``a`` and ``b`` capped at ``threshold + 1``.

    Pure-stdlib two-row dynamic programming with an early exit when the running
    row-minimum exceeds ``threshold`` — returns ``threshold + 1`` in that case
    so callers know the true distance is strictly greater. Used for
    :func:`check_duplicate_slugs` (T6 DoS containment).
    """
    la, lb = len(a), len(b)
    if la == 0:
        return min(lb, threshold + 1)
    if lb == 0:
        return min(la, threshold + 1)
    if abs(la - lb) > threshold:
        return threshold + 1

    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        row_min = curr[0]
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > threshold:
            return threshold + 1
        prev = curr
    return prev[lb]


def _slug_for_duplicate(page: Path, wiki_dir: Path) -> str:
    """Return the canonical slug form for duplicate-slug comparison.

    Per AC10 and T14: full lowered ``page_id`` (subdir retained), with
    underscores normalised to hyphens so ``foo_bar`` and ``foo-bar`` are
    comparable at distance 1.
    """
    pid = page_id(page, wiki_dir)
    return pid.lower().replace("_", "-")


def check_duplicate_slugs(
    wiki_dir: Path | None = None, pages: list[Path] | None = None
) -> list[dict]:
    """Detect near-duplicate page slugs via bounded edit-distance.

    Cycle 16 AC10 / AC13 / T6 / T14.

    For wikis above :data:`_DUPLICATE_SLUGS_PAGE_CAP` pages, returns a single
    skip record rather than running the O(N²) comparison — protects
    ``kb_lint`` from CPU exhaustion on large wikis.

    Length-bucket iteration (Q10/C6): for each slug of length L, compare
    against slugs in buckets ``[L, L+1, ..., L+DUPLICATE_SLUG_DISTANCE_THRESHOLD]``.
    Levenshtein lower bound ``distance >= abs(len(a) - len(b))`` means
    radius 1 would miss distance-2/3 pairs; use full-threshold radius.

    Returns dicts: ``{"slug_a", "slug_b", "distance", "page_a", "page_b"}``.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    if len(pages) > _DUPLICATE_SLUGS_PAGE_CAP:
        return [
            {
                "slug_a": "<skipped>",
                "slug_b": "<skipped>",
                "distance": -1,
                "page_a": "",
                "page_b": "",
                "skipped_reason": (
                    f"wiki too large ({len(pages)} pages > cap {_DUPLICATE_SLUGS_PAGE_CAP})"
                ),
            }
        ]

    slug_entries: list[tuple[str, str]] = []  # (slug, page_id)
    for p in pages:
        try:
            pid = page_id(p, wiki_dir)
        except (OSError, ValueError):
            continue
        slug_entries.append((_slug_for_duplicate(p, wiki_dir), pid))

    # Bucket by slug length.
    buckets: dict[int, list[tuple[str, str]]] = {}
    for entry in slug_entries:
        buckets.setdefault(len(entry[0]), []).append(entry)

    seen_pairs: set[tuple[str, str]] = set()
    issues: list[dict] = []
    for length, bucket in buckets.items():
        # Iterate same-bucket pairs plus above-length buckets up to +threshold.
        candidate_buckets: list[list[tuple[str, str]]] = [bucket]
        for delta in range(1, DUPLICATE_SLUG_DISTANCE_THRESHOLD + 1):
            other = buckets.get(length + delta)
            if other:
                candidate_buckets.append(other)

        for i, (slug_a, pid_a) in enumerate(bucket):
            for cb_idx, cb in enumerate(candidate_buckets):
                start = i + 1 if cb_idx == 0 else 0
                for slug_b, pid_b in cb[start:]:
                    if slug_a == slug_b:
                        continue  # AC10 — distance 0 excluded
                    key = (min(pid_a, pid_b), max(pid_a, pid_b))
                    if key in seen_pairs:
                        continue
                    distance = _bounded_edit_distance(
                        slug_a, slug_b, DUPLICATE_SLUG_DISTANCE_THRESHOLD
                    )
                    if 0 < distance <= DUPLICATE_SLUG_DISTANCE_THRESHOLD:
                        seen_pairs.add(key)
                        issues.append(
                            {
                                "slug_a": slug_a,
                                "slug_b": slug_b,
                                "distance": distance,
                                "page_a": pid_a,
                                "page_b": pid_b,
                            }
                        )
    return issues
