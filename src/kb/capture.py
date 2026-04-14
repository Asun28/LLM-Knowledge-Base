"""kb.capture — atomize messy text into discrete raw/captures/<slug>.md files.

Public API: capture_items(content, provenance) → CaptureResult
MCP tool wrapper: see kb.mcp.core.kb_capture.

Spec: docs/superpowers/specs/2026-04-13-kb-capture-design.md
"""

import base64
import binascii
import os
import re
import secrets as _secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import yaml

from kb.config import (
    CAPTURE_KINDS,
    CAPTURE_MAX_BYTES,
    CAPTURE_MAX_CALLS_PER_HOUR,
    CAPTURE_MAX_ITEMS,
    CAPTURES_DIR,
    PROJECT_ROOT,
)
from kb.utils.io import atomic_text_write
from kb.utils.llm import call_llm_json
from kb.utils.text import slugify, yaml_sanitize

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
    """
    with _rate_limit_lock:
        now = time.time()
        cutoff = now - 3600
        while _rate_limit_window and _rate_limit_window[0] < cutoff:
            _rate_limit_window.popleft()
        if len(_rate_limit_window) >= CAPTURE_MAX_CALLS_PER_HOUR:
            oldest = _rate_limit_window[0]
            retry_after = int(oldest + 3600 - now) + 1
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
    raw_bytes = len(content.encode("utf-8"))
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
# Tuples are (label, compiled-regex). Order matters only for first-match wins;
# more specific patterns are listed before more general ones (e.g. sk-proj-
# before sk-).
_CAPTURE_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS access key (temporary)", re.compile(r"ASIA[0-9A-Z]{16}")),
    (
        "AWS secret access key (env-var)",
        re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*[A-Za-z0-9/+=]{40}"),
    ),
    ("OpenAI key (project)", re.compile(r"sk-proj-[a-zA-Z0-9_-]{20,}")),
    ("Anthropic key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("OpenAI key (legacy)", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("GitHub PAT (long form)", re.compile(r"github_pat_[a-zA-Z0-9_]{82}")),
    ("GitHub PAT", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    ("Slack token", re.compile(r"xox[baprse]-[0-9a-zA-Z-]{10,}")),
    (
        "Bearer token",
        # Require 20+ chars AND at least one digit/dot/underscore/slash/plus/eq
        # in the payload, so benign prose like "bearer responsibility-for-all"
        # (pure word chars + hyphens) doesn't trip the scanner.
        re.compile(
            r"(?i)bearer\s+(?=[A-Za-z0-9._~+/=-]*[0-9._/+=])[A-Za-z0-9._~+/=-]{20,}"
        ),
    ),
    (
        "JWT",
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("GCP OAuth access token", re.compile(r"ya29\.[0-9A-Za-z_-]+")),
    ("GCP service account JSON", re.compile(r'"type"\s*:\s*"service_account"')),
    ("Stripe live key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
    ("Stripe live restricted key", re.compile(r"rk_live_[0-9a-zA-Z]{24,}")),
    ("HuggingFace token", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("Twilio Account SID", re.compile(r"AC[a-f0-9]{32}")),
    ("Twilio Auth Token (SK form)", re.compile(r"SK[a-f0-9]{32}")),
    ("npm token", re.compile(r"npm_[A-Za-z0-9]{36}")),
    (
        "HTTP Basic Authorization header",
        re.compile(r"(?i)Authorization:\s*Basic\s+[A-Za-z0-9+/=]+"),
    ),
    (
        "env-var assignment",
        re.compile(
            r"(?im)^\s*(API_KEY|SECRET_KEY|SECRET|PASSWORD|PASSWD|TOKEN|"
            r"AUTH_TOKEN|ACCESS_TOKEN|DATABASE_URL|DB_PASS|PRIVATE_KEY)"
            r"\s*=\s*\S+"
        ),
    ),
    (
        "DB connection string with password",
        re.compile(
            r"(?i)(postgres|postgresql|mysql|mongodb(\+srv)?|redis|amqp)://"
            r"[^\s:@]+:[^\s@]+@"
        ),
    ),
    (
        "Private key block",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ),
]


def _normalize_for_scan(content: str) -> str:
    """Build a normalized view: append b64-decoded ASCII candidates and URL-decoded runs.

    The original content is kept; this function returns a SUPERSET that's only used for
    secret-pattern matching. The decoded fragments give the regex sweep a chance to
    catch trivially-encoded secrets without losing the original content.
    """
    parts: list[str] = [content]
    # Base64 candidates: at least 16 chars of [A-Za-z0-9+/=].
    for m in re.finditer(r"[A-Za-z0-9+/=]{16,}", content):
        try:
            decoded = base64.b64decode(m.group(0), validate=True)
            text = decoded.decode("ascii")
            parts.append(text)
        except (ValueError, binascii.Error, UnicodeDecodeError):
            continue
    # URL-encoded runs: 3+ adjacent percent-encoded triplets.
    # Only decode the matched run (not the whole content) — keeps the normalized
    # view tight and avoids false positives on content with scattered %XX chars.
    for m in re.finditer(r"(?:%[0-9A-Fa-f]{2}){3,}", content):
        try:
            parts.append(unquote(m.group(0)))
        except (ValueError, UnicodeDecodeError):
            continue
    return "\n".join(parts)


def _scan_for_secrets(content: str) -> tuple[str, str] | None:
    """Sweep content + normalized view for secret patterns.

    Returns (label, location) on first match, else None.
    location is "line N" for plain matches, "via encoded form" for normalization matches.
    """
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        m = pattern.search(content)
        if m:
            line_no = content[: m.start()].count("\n") + 1
            return label, f"line {line_no}"

    normalized = _normalize_for_scan(content)
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        if pattern.search(normalized):
            return label, "via encoded form"

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
                    "body": {"type": "string", "minLength": 1},
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


_PROMPT_TEMPLATE = """You are atomizing messy text into discrete knowledge items.

Input: up to 50KB of conversation logs, scratch notes, or chat transcripts.
Output: JSON matching the schema — a list of items, each with:
  - title (max 100 chars, imperative phrase)
  - kind: one of "decision" | "discovery" | "correction" | "gotcha"
  - body (verbatim span from the input — DO NOT reword, summarize, or rewrite)
  - one_line_summary (max 200 chars, your words, for frontmatter display)
  - confidence: "stated" | "inferred" | "speculative"

Keep an item only if it is:
  - a specific decision (something the user or team settled on)
  - a specific discovery (a new fact learned from evidence)
  - a correction (something previously believed that turned out wrong)
  - a gotcha (a pitfall or non-obvious constraint worth remembering)

Filter as noise:
  - pleasantries, apologies, meta-talk about the chat itself
  - half-finished thoughts or unresolved questions (unless the question IS the gotcha)
  - duplicates of items already in your list
  - off-topic tangents
  - retried / corrected-in-place content (keep only the final form)

Cap the output at {max_items} items. Also report `filtered_out_count`: the number
of candidate items you rejected as noise.

--- INPUT ---
{content}
--- END INPUT ---
"""


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
    """Call scan-tier LLM with forced-JSON schema. Raises LLMError on retry exhaustion."""
    safe_content = _escape_prompt_fences(content)
    prompt = _PROMPT_TEMPLATE.format(max_items=CAPTURE_MAX_ITEMS, content=safe_content)
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
    n = 2
    while True:
        suffix = f"-{n}"
        trimmed = base[: 80 - len(suffix)].rstrip("-") or kind[: 80 - len(suffix)]
        candidate = f"{trimmed}{suffix}"
        if candidate not in existing:
            return candidate
        n += 1


def _path_within_captures(path: Path) -> bool:
    """Belt-and-suspenders: refuse any resolved path outside CAPTURES_DIR.

    Relies on CAPTURES_DIR itself being inside PROJECT_ROOT — enforced by the
    module-import-time assertion at the end of this module.
    """
    try:
        path.resolve().relative_to(CAPTURES_DIR.resolve())
        return True
    except ValueError:
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
    slug: str,
    captured_alongside: list[str],
    provenance: str,
    captured_at: str,
) -> str:
    """Render one capture item to the markdown form (spec §5).

    Field order is preserved for predictable diffs (sort_keys=False).
    yaml_sanitize strips bidi marks + control chars; yaml.dump then handles
    escaping. (Using yaml_escape here would double-escape backslashes/quotes.)
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


def _write_item_files(
    items: list[dict],
    provenance: str,
    captured_at: str,
) -> tuple[list[CaptureItem], str | None]:
    """Resolve slugs, compute captured_alongside, write each file atomically.

    Spec §4 step 9 + §7 Class D.

    Returns (written_items, error_msg). On partial failure, error_msg is set and
    `written` contains only the items written before the failure. Accepted v1
    limitation: captured_alongside refs resolved in Phase B may become stale if
    a cross-process race forces a slug change in Phase C.
    """
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Initial scan — use context manager to release Windows dir handle promptly
    with os.scandir(CAPTURES_DIR) as it:
        existing = {
            entry.name[:-3]
            for entry in it
            if entry.is_file() and entry.name.endswith(".md")
        }

    # Phase A — resolve all slugs in-process
    slugs: list[str] = []
    for item in items:
        slug = _build_slug(item["kind"], item["title"], existing)
        existing.add(slug)
        slugs.append(slug)

    # Phase B — compute captured_alongside per item (excludes self)
    alongside_for: list[list[str]] = [
        [s for j, s in enumerate(slugs) if j != i] for i in range(len(items))
    ]

    # Phase C — write each file with cross-process race retry
    written: list[CaptureItem] = []
    for i, item in enumerate(items):
        slug = slugs[i]
        alongside = alongside_for[i]
        markdown = _render_markdown(
            item=item,
            slug=slug,
            captured_alongside=alongside,
            provenance=provenance,
            captured_at=captured_at,
        )
        success = False
        for _attempt in range(10):
            path = CAPTURES_DIR / f"{slug}.md"
            if not _path_within_captures(path):
                return written, f"Error: slug escapes CAPTURES_DIR: {slug!r}"
            try:
                _exclusive_atomic_write(path, markdown)
                written.append(
                    CaptureItem(
                        slug=slug,
                        path=path,
                        title=item["title"],
                        kind=item["kind"],
                        body_chars=len(item["body"]),
                    )
                )
                success = True
                break
            except FileExistsError:
                # Cross-process race — re-scan and re-resolve (context-managed)
                with os.scandir(CAPTURES_DIR) as it:
                    existing = {
                        entry.name[:-3]
                        for entry in it
                        if entry.is_file() and entry.name.endswith(".md")
                    }
                slug = _build_slug(item["kind"], item["title"], existing)
            except OSError as e:
                return (
                    written,
                    f"Error: failed to write {slug}: {e}. "
                    f"{len(written)} of {len(items)} items written.",
                )
        if not success:
            return written, f"Error: slug retry exhausted for {item['title']!r}"

    return written, None


@dataclass(frozen=True)
class CaptureResult:
    items: list[CaptureItem]
    filtered_out_count: int
    rejected_reason: str | None
    provenance: str


def capture_items(content: str, provenance: str | None = None) -> CaptureResult:
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
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    written, write_error = _write_item_files(kept, resolved_prov, captured_at)

    return CaptureResult(
        items=written,
        filtered_out_count=llm_filtered + body_dropped,
        rejected_reason=write_error,  # None on full success, str on partial-failure
        provenance=resolved_prov,
    )


# === Module-import-time symlink guard (spec §5, §8) ===
# If raw/captures/ is a symlink escaping PROJECT_ROOT, refuse to load the
# module at all rather than fail open in _path_within_captures at runtime.
# A symlinked CAPTURES_DIR planted via some other primitive would resolve
# to the symlink target on BOTH sides of the relative_to() call, silently
# passing the path-within check. This assertion closes that gap.
# Explicit runtime check (not `assert`) so the guard fires under `python -O`
# which strips asserts. Security checks must never be optimizable away.
if not CAPTURES_DIR.resolve().is_relative_to(PROJECT_ROOT.resolve()):
    raise RuntimeError(
        f"SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT — refusing to load. "
        f"CAPTURES_DIR={CAPTURES_DIR.resolve()}, PROJECT_ROOT={PROJECT_ROOT.resolve()}"
    )
