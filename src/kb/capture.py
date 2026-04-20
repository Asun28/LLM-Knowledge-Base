"""kb.capture — atomize messy text into discrete raw/captures/<slug>.md files.

Public API: capture_items(content, provenance) → CaptureResult
MCP tool wrapper: see kb.mcp.core.kb_capture.

Spec: docs/superpowers/specs/2026-04-13-kb-capture-design.md
"""

import base64
import logging
import os
import re
import secrets as _secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

import yaml

from kb.config import (
    CAPTURE_KINDS,
    CAPTURE_MAX_BYTES,
    CAPTURE_MAX_CALLS_PER_HOUR,
    CAPTURE_MAX_ITEMS,
    CAPTURES_DIR,
    PROJECT_ROOT,
    TEMPLATES_DIR,
)
from kb.utils.io import atomic_text_write
from kb.utils.llm import call_llm_json
from kb.utils.text import slugify, yaml_sanitize

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 600_000
_SLUG_COLLISION_CEILING = 10000

assert CAPTURE_MAX_BYTES <= MAX_PROMPT_CHARS, "CAPTURE_MAX_BYTES must not exceed MAX_PROMPT_CHARS"

# === Rate limit (spec §4 step 4, §8) ===
# Per-process token-bucket sliding window. threading.Lock makes the
# check-then-act (len(deque) ≥ LIMIT, then append now) atomic under
# concurrent FastMCP tool calls. Project precedent: kb.utils.llm:26,
# kb.review.refiner:13.
_rate_limit_lock = threading.Lock()
_rate_limit_window: deque[float] = deque()


def _check_rate_limit() -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds).

    Sliding 1-hour window of timestamps. Trims expired entries on each call.
    On overflow, returns (False, seconds-until-oldest-expires).

    Per-process only. Separate MCP server and CLI processes each enforce the
    limit independently; total across processes can exceed CAPTURE_MAX_CALLS_PER_HOUR.
    TODO(v2): persist via .data/capture_rate.json + atomic_json_write under
    file_lock for system-wide enforcement.
    For a true system-wide limit, persist the deque via
    `.data/capture_rate.json` + `atomic_json_write` under a `file_lock`.
    """
    with _rate_limit_lock:
        now = time.time()
        cutoff = now - 3600
        while _rate_limit_window and _rate_limit_window[0] < cutoff:
            _rate_limit_window.popleft()
        if len(_rate_limit_window) >= CAPTURE_MAX_CALLS_PER_HOUR:
            oldest = _rate_limit_window[0]
            # max(1, ...) avoids ≤0 retry_after under frozen-clock test fixtures
            retry_after = max(1, int(oldest + 3600 - now) + 1)
            return False, retry_after
        _rate_limit_window.append(now)
        return True, 0


def _validate_input(content: str) -> tuple[str | None, str]:
    """Validate raw input and return (normalized_content_or_None, error_msg).

    Spec §4 step 5 + invariant 5: size check uses RAW UTF-8 bytes BEFORE
    CRLF normalization, then normalizes \\r\\n → \\n in-place. All downstream
    steps (secret scan, LLM extract, verbatim verify) see the LF-normalized form.

    Returns:
        (normalized, "") on success
        (None, error_msg) on rejection
    """
    # ASCII fast-path avoids a full encode() allocation for the common case
    raw_bytes = len(content) if content.isascii() else len(content.encode("utf-8"))
    if raw_bytes > CAPTURE_MAX_BYTES:
        return None, (
            f"Error: content exceeds {CAPTURE_MAX_BYTES} bytes (got {raw_bytes}). "
            f"Split into chunks and retry."
        )
    normalized = content.replace("\r\n", "\n")
    if not normalized.strip():
        return None, "Error: content is empty. Nothing to capture."
    return normalized, ""


# === Secret scanner (spec §8 expanded pattern list) ===


class _SecretPattern(NamedTuple):
    label: str
    pattern: re.Pattern[str]


# Order matters only for first-match wins;
# more specific patterns are listed before more general ones (e.g. sk-proj-
# before sk-).
_CAPTURE_SECRET_PATTERNS: list[_SecretPattern] = [
    _SecretPattern(label="AWS access key", pattern=re.compile(r"AKIA[0-9A-Z]{16}")),
    _SecretPattern(label="AWS access key (temporary)", pattern=re.compile(r"ASIA[0-9A-Z]{16}")),
    _SecretPattern(
        label="AWS secret access key (env-var)",
        pattern=re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+=]{40}"),
    ),
    _SecretPattern(label="OpenAI key (project)", pattern=re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}")),
    _SecretPattern(label="Anthropic key", pattern=re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    _SecretPattern(label="OpenAI key (legacy)", pattern=re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    _SecretPattern(
        label="GitHub PAT (long form)",
        pattern=re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
    ),
    _SecretPattern(label="GitHub PAT", pattern=re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    _SecretPattern(label="Slack token", pattern=re.compile(r"xox[baprse]-[0-9a-zA-Z-]{10,}")),
    _SecretPattern(
        label="Bearer token",
        # Require 20+ chars AND at least one digit/dot/underscore/slash/plus/eq
        # in the payload, so benign prose like "bearer responsibility-for-all"
        # (pure word chars + hyphens) doesn't trip the scanner.
        pattern=re.compile(
            r"(?i)bearer\s+(?=[A-Za-z0-9._~+/=-]*[0-9._/+=])"
            r"[A-Za-z0-9._~+/=-]{20,}"
        ),
    ),
    _SecretPattern(
        label="JWT",
        pattern=re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    _SecretPattern(label="Google API key", pattern=re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    _SecretPattern(label="GCP OAuth access token", pattern=re.compile(r"ya29\.[0-9A-Za-z_-]{20,}")),
    _SecretPattern(
        label="GCP service account JSON",
        pattern=re.compile(r'"type"\s*:\s*"service_account"'),
    ),
    _SecretPattern(label="Stripe live key", pattern=re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
    _SecretPattern(
        label="Stripe live restricted key",
        pattern=re.compile(r"rk_live_[0-9a-zA-Z]{24,}"),
    ),
    _SecretPattern(label="HuggingFace token", pattern=re.compile(r"hf_[A-Za-z0-9]{30,}")),
    _SecretPattern(label="Twilio Account SID", pattern=re.compile(r"AC[a-f0-9]{32}")),
    _SecretPattern(label="Twilio Auth Token (SK form)", pattern=re.compile(r"SK[a-f0-9]{32}")),
    _SecretPattern(label="npm token", pattern=re.compile(r"npm_[A-Za-z0-9]{36}")),
    _SecretPattern(
        label="HTTP Basic Authorization header",
        pattern=re.compile(r"(?i)Authorization:\s*Basic\s+[A-Za-z0-9+/=]+"),
    ),
    _SecretPattern(
        # A6 (Phase 5 kb-capture LOW): opaque Bearer tokens (OAuth2, Azure AD,
        # GCP, non-JWT session tokens). Require 16+ chars so short demo Bearer
        # doesn't false-positive; JWT Bearer is still caught by the JWT pattern.
        label="HTTP Bearer Authorization header",
        pattern=re.compile(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9+/=._~-]{16,}"),
    ),
    _SecretPattern(
        # A4 (Phase 5 kb-capture MED + 2× LOW merged): broaden to catch suffix
        # variants (ANTHROPIC_API_KEY, DJANGO_SECRET_KEY, GH_TOKEN, APP_SECRET,
        # ACCESS_KEY, ENCRYPTION_KEY) and optional shell `export ` prefix.
        # Prefix group is optional so bare `API_KEY=…` still matches.
        #
        # PR review round 1 (Codex M-NEW-2): original `['\"]?\S{8,}` stopped
        # at the first whitespace, so quoted values with spaces like
        # `SECRET="has spaces but is still a long secret"` bypassed the
        # scanner. Updated pattern accepts either 8+ non-space chars OR a
        # quote-wrapped run of 8+ chars including spaces (but no closing
        # line). Closing quote may be the same or absent.
        label="env-var assignment",
        pattern=re.compile(
            r"(?im)^\s*(?:export\s+)?"
            r"(?:[A-Z][A-Z0-9_]*_)?"  # OPTIONAL prefix like ANTHROPIC_, DJANGO_
            r"(API_KEY|SECRET_KEY|SECRET|PASSWORD|PASSWD|TOKEN|AUTH_TOKEN|"
            r"ACCESS_TOKEN|ACCESS_KEY|DATABASE_URL|DB_PASS|PRIVATE_KEY|"
            r"ENCRYPTION_KEY|API_SECRET)"
            r"\s*=\s*"
            r"(?:['\"][^\n'\"]{8,}['\"]?|\S{8,})"
        ),
    ),
    _SecretPattern(
        label="DB connection string with password",
        pattern=re.compile(
            r"(?i)(postgres|postgresql|mysql|mongodb(\+srv)?|redis|amqp)://"
            r"[^\s:@]+:[^\s@]+@"
        ),
    ),
    _SecretPattern(
        label="Private key block",
        pattern=re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ),
    _SecretPattern(
        label="PostgreSQL DSN with password",
        pattern=re.compile(r"(?i)postgresql://[^:\s]+:[^@\s]{6,}@"),
    ),
    _SecretPattern(
        label="npm registry _authToken",
        pattern=re.compile(r"(?i)//[a-z0-9._-]+/?:_authToken=[A-Za-z0-9+/=_-]{20,}"),
    ),
]


def _normalize_for_scan(content: str) -> list[tuple[str, str]]:
    """Build decoded secret-scan candidates with encoding labels.

    The original content is scanned separately. These decoded fragments give
    the regex sweep a chance to catch trivially-encoded secrets without losing
    the original content.

    Cost note: decoded candidates peak at ~0.76× input size (~38KB at the 50KB cap).
    Base64 scan: O(input_size / 17) ≈ 2,941 candidates max (16-char minimum match).
    URL-decode scan: O(input_size / 10) ≈ 5,000 candidates max (9-char minimum: %XX×3).
    Both bounds are load-bearing on CAPTURE_MAX_BYTES — review before raising that.
    """
    parts: list[tuple[str, str]] = []
    # Base64 candidates: at least 16 chars of [A-Za-z0-9+/=].
    for m in re.finditer(r"[A-Za-z0-9+/=]{16,}", content):
        try:
            decoded = base64.b64decode(m.group(0), validate=True)
            text = decoded.decode("ascii")
            parts.append((text, "base64"))
        except Exception as exc:
            logger.debug("normalize: decoder skipped segment due to %s", exc)
            continue
    # URL-encoded runs: 3+ adjacent percent-encoded triplets.
    # Only decode the matched run (not the whole content) — keeps the normalized
    # view tight and avoids false positives on content with scattered %XX chars.
    # urllib.parse.unquote uses errors='replace' internally and never raises.
    for m in re.finditer(r"(?:%[0-9A-Fa-f]{2}){3,}", content):
        parts.append((unquote(m.group(0)), "URL-encoded"))
    return parts


def _scan_for_secrets(content: str) -> tuple[str, str] | None:
    """Sweep content + normalized view for secret patterns.

    Returns (label, location) on first match, else None.
    location is "line N" for plain matches, "via <encoding>" for normalization matches.
    """
    for secret_pattern in _CAPTURE_SECRET_PATTERNS:
        m = secret_pattern.pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return secret_pattern.label, f"line {line_no}"

    for decoded_text, encoding_label in _normalize_for_scan(content):
        for secret_pattern in _CAPTURE_SECRET_PATTERNS:
            if secret_pattern.pattern.search(decoded_text):
                return secret_pattern.label, f"via {encoding_label}"

    return None


# === Scan-tier LLM contract (spec §4) ===
_CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "maxItems": CAPTURE_MAX_ITEMS,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 100},
                    "kind": {"enum": list(CAPTURE_KINDS)},
                    # A2 (Phase 5 kb-capture LOW): cap body at 2000 chars so a
                    # faithful LLM return cannot echo back the entire 50KB input
                    # as one item's body, defeating the atomization purpose.
                    "body": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "one_line_summary": {"type": "string", "maxLength": 200},
                    "confidence": {"enum": ["stated", "inferred", "speculative"]},
                },
                "required": ["title", "kind", "body", "one_line_summary", "confidence"],
            },
        },
        "filtered_out_count": {"type": "integer", "minimum": 0},
    },
    "required": ["items", "filtered_out_count"],
}


# Cycle 17 AC9 — prompt text moved to templates/capture_prompt.txt.
# This is distinct from templates/*.yaml JSON-Schema extraction templates
# loaded via `load_template(source_type)`; the capture prompt is a
# format-string with named placeholders (max_items, boundary_start, content,
# boundary_end) rather than a JSON-Schema `extract:` mapping. Hardcoded
# filename keeps the loader path caller-inaccessible (threat T11).
_PROMPT_TEMPLATE = (TEMPLATES_DIR / "capture_prompt.txt").read_text(encoding="utf-8")


_FENCE_END_RE = re.compile(r"-{2,}\s*END\s+INPUT\s*-{2,}", re.IGNORECASE)
_FENCE_START_RE = re.compile(r"(?<!END\s)-{2,}\s*INPUT\s*-{2,}", re.IGNORECASE)


def _escape_prompt_fences(content: str) -> str:
    """Neutralize fence markers embedded in user content to prevent prompt injection.

    Regex-based so whitespace variations ('---  END INPUT ---'), case variations
    ('--- end input ---'), and dash-count variations ('----- END INPUT -----')
    are all rewritten. Verbatim verification (_verify_body_is_verbatim) still
    uses the ORIGINAL normalized content, so an LLM echoing an unescaped fence
    back as a body span fails the check and is dropped.
    """
    content = _FENCE_END_RE.sub("--- END INPUT (escaped) ---", content)
    content = _FENCE_START_RE.sub("--- INPUT (escaped) ---", content)
    return content


def _extract_items_via_llm(content: str) -> dict:
    """Call scan-tier LLM with forced-JSON schema. Raises LLMError on retry exhaustion.

    AC21 R1 M1: runtime pre-flight on the assembled prompt length. The
    module-level `assert CAPTURE_MAX_BYTES <= MAX_PROMPT_CHARS` at import
    time disappears under `python -O`, and a legitimately-sized content
    combined with a larger-than-expected template could still slip past.
    An explicit runtime check closes that gap regardless of optimization
    level.
    """
    safe_content = _escape_prompt_fences(content)
    for _attempt in range(3):
        boundary = _secrets.token_hex(16)
        boundary_start = f"<<<INPUT-{boundary}>>>"
        boundary_end = f"<<<END-INPUT-{boundary}>>>"
        if (
            boundary not in safe_content
            and boundary_start not in safe_content
            and boundary_end not in safe_content
        ):
            break
    else:
        raise ValueError("boundary collision after 3 retries — input may be adversarial")

    prompt = _PROMPT_TEMPLATE.format(
        max_items=CAPTURE_MAX_ITEMS,
        boundary_start=boundary_start,
        boundary_end=boundary_end,
        content=safe_content,
    )
    if len(prompt) > MAX_PROMPT_CHARS:
        raise CaptureError(
            f"capture prompt too long ({len(prompt)} chars > {MAX_PROMPT_CHARS} max); "
            f"CAPTURE_MAX_BYTES={CAPTURE_MAX_BYTES} should prevent this — file a bug"
        )
    return call_llm_json(prompt, tier="scan", schema=_CAPTURE_SCHEMA)


def _verify_body_is_verbatim(items: list[dict], content: str) -> tuple[list[dict], int]:
    """Drop items whose body is whitespace-only or not a verbatim substring of content.

    Spec §4 step 8 + invariant 2. Defends raw/ immutability against LLM rewording
    AND traps the schema gap where minLength:1 permits "   " bodies (which would
    write 0-byte content files).
    """
    kept: list[dict] = []
    dropped = 0
    for item in items:
        body = item.get("body")
        # Defensive: if the schema layer ever regresses and lets a non-string
        # body through, drop THAT item rather than crashing the whole batch.
        if not isinstance(body, str):
            dropped += 1
            continue
        body_stripped = body.strip()
        if not body_stripped:
            dropped += 1
            continue
        if body_stripped not in content:
            dropped += 1
            continue
        item["body"] = body_stripped
        kept.append(item)
    return kept, dropped


def _build_slug(kind: str, title: str, existing: set[str]) -> str:
    """Spec §5: kind prefix + slugify + 80-char cap + numeric collision suffix.

    Falls back to bare kind if slugify produces empty string (e.g. all-unicode title
    stripped by re.ASCII flag in kb.utils.text.slugify).
    """
    base = slugify(f"{kind}-{title}")[:80]
    if not base:
        base = kind
    if base not in existing:
        return base
    ceiling = _SLUG_COLLISION_CEILING
    for n in range(2, ceiling + 2):
        suffix = f"-{n}"
        trimmed = base[: 80 - len(suffix)].rstrip("-") or kind[: 80 - len(suffix)]
        candidate = f"{trimmed}{suffix}"
        if candidate not in existing:
            return candidate
    raise RuntimeError(f"slug collision ceiling exhausted for {kind}/{base}; {ceiling} attempts")


def _is_path_within_captures(path: Path, base_dir: Path | None = None) -> bool:
    """Belt-and-suspenders: refuse any resolved path outside base_dir.

    Relies on base_dir itself being inside PROJECT_ROOT — enforced by the
    module-import-time assertion at the end of this module (which resolves
    CAPTURES_DIR only; a caller-supplied base_dir outside PROJECT_ROOT is
    resolved here for each check).

    A5 (Phase 5 kb-capture MED): when base_dir is None and equals the global
    CAPTURES_DIR, fall through to the pre-resolved module-level constant to
    avoid the stat+readlink syscalls of Path.resolve() on every call.
    """
    if base_dir is None:
        resolved_base = _CAPTURES_DIR_RESOLVED
    else:
        try:
            resolved_base = base_dir.resolve()
        except OSError as e:
            logger.warning("Path resolve failed for base_dir %s: %s", base_dir, e)
            return False
    try:
        path.resolve().relative_to(resolved_base)
        return True
    except ValueError:
        return False
    except OSError as e:
        # ELOOP on symlink cycles, EACCES on unreadable parents, etc.
        # Log so operators can diagnose filesystem/permission issues rather
        # than confusing them with the generic "slug escapes CAPTURES_DIR"
        # message the caller surfaces. Still fails closed per MCP convention.
        logger.warning("Path resolve failed for %s during capture guard: %s", path, e)
        return False


def _exclusive_atomic_write(path: Path, content: str) -> None:
    """Atomic create-or-fail. Raises FileExistsError if path already exists.

    Combines O_EXCL (race-safe slug reservation) with temp-file-then-rename
    (no half-written file on crash). Cleans up its empty reservation on any
    failure of the inner atomic_text_write, including BaseException
    (KeyboardInterrupt, SystemExit).
    """
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
    try:
        atomic_text_write(content, path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _resolve_provenance(provenance: str | None) -> str:
    """Resolve user-supplied provenance to a final string. Always returns non-empty.

    Spec §4 step 3 — runs FIRST so CaptureResult.provenance is populated in every
    return path (including hard rejects).

    - None / "" / slugifies-to-empty → "capture-<ISO>-<4hex>"
    - Else → "<slugify(label)[:80]>-<ISO>"

    ISO format uses '-' instead of ':' for filesystem safety on Windows.
    """
    iso = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    if not provenance or not provenance.strip():
        return f"capture-{iso}-{_secrets.token_hex(2)}"
    slugged = slugify(provenance)[:80]
    if not slugged:
        return f"capture-{iso}-{_secrets.token_hex(2)}"
    return f"{slugged}-{iso}"


def _render_markdown(
    item: dict,
    captured_alongside: list[str],
    provenance: str,
    captured_at: str,
) -> str:
    """Render one capture item to the markdown form (spec §5).

    Field order is preserved for predictable diffs (sort_keys=False).
    yaml_sanitize strips bidi marks + control chars; yaml.dump then handles
    escaping. (Using yaml_escape here would double-escape backslashes/quotes.)

    A1 (Phase 5 kb-capture R3 MEDIUM): removed dead `slug` param — it was
    accepted but never referenced in the function body, so the R2 proposal
    to re-render on slug retry was a no-op. See spec for two-pass write
    design rationale (deferred to v2).
    """
    fm = {
        "title": yaml_sanitize(item["title"]),
        "kind": item["kind"],
        "confidence": item["confidence"],
        "one_line_summary": yaml_sanitize(item["one_line_summary"]),
        "captured_at": captured_at,
        "captured_from": provenance,
        "captured_alongside": list(captured_alongside),
        "source": "mcp-capture",
    }
    fm_yaml = yaml.dump(
        fm,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    body = item["body"]
    if not body.endswith("\n"):
        body = body + "\n"
    return f"---\n{fm_yaml}---\n\n{body}"


@dataclass(frozen=True)
class CaptureItem:
    slug: str
    path: Path
    title: str
    kind: str
    body_chars: int


class CaptureError(Exception):
    """Raised by capture helpers on unrecoverable internal errors."""


def _scan_existing_slugs(captures_dir: Path) -> set[str]:
    """Return the set of slug stems (no `.md` suffix) already on disk."""
    with os.scandir(captures_dir) as it:
        return {entry.name[:-3] for entry in it if entry.is_file() and entry.name.endswith(".md")}


def _reserve_hidden_temp(item: dict, existing: set[str], captures_dir: Path) -> tuple[str, Path]:
    """Reserve a hidden-temp `.{slug}.reserving` file atomically via O_EXCL.

    Cycle 17 AC10 / design gate Q9 — hidden-temp suffix (leading dot,
    `.reserving` ext) prevents concurrent `kb_ingest` scanning `*.md` from
    picking up the reservation as a legitimate capture. Retries up to 10 times
    on `FileExistsError` with `_build_slug`-computed alternate.
    """
    for _attempt in range(10):
        slug = _build_slug(item["kind"], item["title"], existing)
        temp_path = captures_dir / f".{slug}.reserving"
        if not _is_path_within_captures(temp_path, base_dir=captures_dir):
            raise CaptureError(f"slug escapes captures dir: {slug!r}")
        try:
            fd = os.open(str(temp_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return slug, temp_path
        except FileExistsError:
            existing = _scan_existing_slugs(captures_dir)
            existing.add(slug)
            continue
    raise CaptureError(f"slug retry exhausted for {item['title']!r}")


def _rollback_reservations(reservations: list[tuple[str, Path, dict]]) -> None:
    """Unlink every hidden-temp file in `reservations`. Best-effort."""
    for _slug, temp_path, _item in reservations:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Reservation rollback failed for %s: %s", temp_path, e)


def _rollback_finalized(written: list[CaptureItem]) -> None:
    """Unlink every finalized `.md` file in `written`. Best-effort.

    Cycle 17 AC10 all-or-nothing semantics: on Phase-3 mid-batch failure, the
    batch is treated as a whole. Callers receive `(written=[], error_msg)`.
    """
    for item in written:
        try:
            item.path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Finalized-file rollback failed for %s: %s", item.path, e)


def _write_item_files(
    items: list[dict],
    provenance: str,
    captured_at: str,
    *,
    captures_dir: Path | None = None,
) -> tuple[list[CaptureItem], str | None]:
    """All-or-nothing two-pass write — cycle 17 AC10 (was the v1 partial-commit bug).

    Spec §4 step 9 + §7 Class D.

    **Phase 1 (reserve):** for each item, reserve a hidden-temp file
    ``.{slug}.reserving`` atomically via `O_EXCL`. `_build_slug` retries on
    cross-process collision. On any Phase-1 failure, every previously-reserved
    temp is unlinked and the call returns ``([], error_msg)`` — no orphaned
    reservations remain.

    **Phase 2 (alongside):** compute ``captured_alongside[i]`` from the
    **finalised** Phase-1 slugs (NOT the pre-reservation guesses). Closes the
    original bug where alongside refs froze before Phase-C reassignment.

    **Phase 3 (commit):** render markdown per item, write to the temp path,
    then ``os.replace(temp, final)`` to atomically promote ``.reserving`` →
    ``<slug>.md``. On any Phase-3 failure, finalised ``.md`` files AND
    remaining ``.reserving`` temps are ALL unlinked; the call returns
    ``([], error_msg)``.

    Keyword-only ``captures_dir`` override lets unit tests pick a sandbox
    directory without monkeypatching the module-level ``CAPTURES_DIR``.
    """
    if not items:
        return [], None

    _captures_dir = captures_dir if captures_dir is not None else CAPTURES_DIR
    _captures_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1 — reserve all N hidden-temp files.
    existing = _scan_existing_slugs(_captures_dir)
    reservations: list[tuple[str, Path, dict]] = []
    try:
        for item in items:
            slug, temp_path = _reserve_hidden_temp(item, existing, _captures_dir)
            existing.add(slug)
            reservations.append((slug, temp_path, item))
    except CaptureError as e:
        _rollback_reservations(reservations)
        return [], f"Error: {e}"
    except OSError as e:
        _rollback_reservations(reservations)
        return [], f"Error: reservation failed: {e}"

    finalized_slugs = [slug for slug, _path, _item in reservations]

    # Phase 2 — compute captured_alongside from FINALISED slugs. O(N²) is safe
    # at CAPTURE_MAX_ITEMS=20; revisit above ~500.
    alongside_for: list[list[str]] = [
        [s for j, s in enumerate(finalized_slugs) if j != i] for i in range(len(reservations))
    ]

    # Phase 3 — write real content then atomic-rename temp → final.
    written: list[CaptureItem] = []
    try:
        for i, (slug, temp_path, item) in enumerate(reservations):
            markdown = _render_markdown(
                item=item,
                captured_alongside=alongside_for[i],
                provenance=provenance,
                captured_at=captured_at,
            )
            final_path = _captures_dir / f"{slug}.md"
            if not _is_path_within_captures(final_path, base_dir=_captures_dir):
                _rollback_finalized(written)
                _rollback_reservations(reservations[i:])
                return [], f"Error: slug escapes captures dir: {slug!r}"
            temp_path.write_text(markdown, encoding="utf-8")
            os.replace(temp_path, final_path)
            written.append(
                CaptureItem(
                    slug=slug,
                    path=final_path,
                    title=item["title"],
                    kind=item["kind"],
                    body_chars=len(item["body"]),
                )
            )
    except OSError as e:
        _rollback_finalized(written)
        _rollback_reservations(reservations[len(written) :])
        return [], f"Error: write failed on item {len(written)}: {e}"

    return written, None


@dataclass(frozen=True)
class CaptureResult:
    """Result from capture_items.

    Written item files include `captured_at` as submission time (UTC ISO-8601) —
    close to the moment kb_capture was invoked, NOT to LLM completion.
    """

    items: list[CaptureItem]
    filtered_out_count: int
    rejected_reason: str | None
    provenance: str


def capture_items(
    content: str,
    provenance: str | None = None,
    *,
    captures_dir: Path | None = None,
) -> CaptureResult:
    """Atomize messy text into discrete raw/captures/<slug>.md files.

    Public API. See spec §3-§4 for the data flow.

    Args:
        content: up to CAPTURE_MAX_BYTES (50KB) of UTF-8 text. Hard reject above.
        provenance: optional grouping label. None / "" → auto-generated.

    Returns:
        CaptureResult with `provenance` always populated. On hard reject, `items=[]`
        and `rejected_reason` is set. On success, `items` lists each written file.
        On partial write failure, `items` contains the successfully written items
        and `rejected_reason` describes the failure.

    Raises:
        LLMError if the scan-tier API exhausts retries.
    """
    # Step 3: resolve provenance FIRST so all return paths carry it
    resolved_prov = _resolve_provenance(provenance)
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 5: validate input (size pre-normalize + empty + CRLF normalize)
    # Runs BEFORE the rate-limit check — these checks cost zero LLM tokens, so
    # rejecting on them shouldn't burn the caller's hourly budget (prevents
    # accidental self-DoS when spamming oversize/empty payloads).
    normalized, err = _validate_input(content)
    if err:
        return CaptureResult(
            items=[], filtered_out_count=0, rejected_reason=err, provenance=resolved_prov
        )
    # _validate_input's contract: err == "" implies normalized is str, not None.
    # Explicit runtime check (not `assert`) so the narrowing survives `python -O`.
    if normalized is None:
        return CaptureResult(
            items=[],
            filtered_out_count=0,
            rejected_reason="Error: internal validation inconsistency.",
            provenance=resolved_prov,
        )

    # Step 6: secret scan (on normalized form per invariant 5) — also pre-budget.
    secret = _scan_for_secrets(normalized)
    if secret is not None:
        label, location = secret
        return CaptureResult(
            items=[],
            filtered_out_count=0,
            rejected_reason=(
                f"Error: secret pattern detected at {location} ({label}). "
                f"No items written. Redact and retry."
            ),
            provenance=resolved_prov,
        )

    # Step 4 (moved): rate limit — checked AFTER cheap rejects so they don't
    # consume the hourly LLM budget.
    allowed, retry_after = _check_rate_limit()
    if not allowed:
        return CaptureResult(
            items=[],
            filtered_out_count=0,
            rejected_reason=(
                f"Error: rate limit ({CAPTURE_MAX_CALLS_PER_HOUR} calls/hour) "
                f"exceeded. Try again in {retry_after} seconds."
            ),
            provenance=resolved_prov,
        )

    # Step 7: scan-tier extraction (raises LLMError on failure)
    response = _extract_items_via_llm(normalized)
    raw_items = response["items"]
    llm_filtered = response["filtered_out_count"]

    # Step 8: body verbatim verify
    kept, body_dropped = _verify_body_is_verbatim(raw_items, normalized)

    # Step 9: write files
    written, write_error = _write_item_files(
        kept, resolved_prov, captured_at, captures_dir=captures_dir
    )

    return CaptureResult(
        items=written,
        filtered_out_count=llm_filtered + body_dropped,
        rejected_reason=write_error,  # None on full success, str on partial-failure
        provenance=resolved_prov,
    )


# === Module-import-time symlink guard (spec §5, §8) ===
# If raw/captures/ is a symlink escaping PROJECT_ROOT, refuse to load the
# module at all rather than fail open in _is_path_within_captures at runtime.
# A symlinked CAPTURES_DIR planted via some other primitive would resolve
# to the symlink target on BOTH sides of the relative_to() call, silently
# passing the path-within check. This assertion closes that gap.
# Explicit runtime check (not `assert`) so the guard fires under `python -O`
# which strips asserts. Security checks must never be optimizable away.
# Wrap .resolve() calls in try/except OSError so mount failures (offline
# network drive, unreadable parent) surface as RuntimeError instead of
# crashing module import with an opaque OSError traceback.
try:
    _captures_resolved = CAPTURES_DIR.resolve()
    _project_resolved = PROJECT_ROOT.resolve()
except OSError as e:
    raise RuntimeError(
        f"SECURITY: Could not resolve CAPTURES_DIR or PROJECT_ROOT (mount failure?): {e}"
    ) from e

if not _captures_resolved.is_relative_to(_project_resolved):
    raise RuntimeError(
        f"SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT — refusing to load. "
        f"CAPTURES_DIR={_captures_resolved}, PROJECT_ROOT={_project_resolved}"
    )

# A5 (Phase 5 kb-capture MED): public alias for the already-resolved
# CAPTURES_DIR. _is_path_within_captures uses this cached value when base_dir=None
# to avoid stat+readlink syscalls on every call.
_CAPTURES_DIR_RESOLVED: Path = _captures_resolved
