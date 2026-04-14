"""kb.capture — atomize messy text into discrete raw/captures/<slug>.md files.

Public API: capture_items(content, provenance) → CaptureResult
MCP tool wrapper: see kb.mcp.core.kb_capture.

Spec: docs/superpowers/specs/2026-04-13-kb-capture-design.md
"""

import base64
import binascii
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import unquote

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
from kb.utils.text import slugify

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
    ("Slack token", re.compile(r"xox[baprs]-[0-9]+-[0-9]+-[0-9a-zA-Z]+")),
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
            r"(?im)^(API_KEY|SECRET|PASSWORD|PASSWD|TOKEN|"
            r"DATABASE_URL|DB_PASS|PRIVATE_KEY)\s*=\s*\S+"
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


def _extract_items_via_llm(content: str) -> dict:
    """Call scan-tier LLM with forced-JSON schema. Raises LLMError on retry exhaustion."""
    prompt = _PROMPT_TEMPLATE.format(max_items=CAPTURE_MAX_ITEMS, content=content)
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
        body_stripped = item["body"].strip()
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
    base = slugify(f"{kind}-{title}")
    base = base[:80]
    if not base:
        base = kind
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


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


# === Module-import-time symlink guard (spec §5, §8) ===
# If raw/captures/ is a symlink escaping PROJECT_ROOT, refuse to load the
# module at all rather than fail open in _path_within_captures at runtime.
# A symlinked CAPTURES_DIR planted via some other primitive would resolve
# to the symlink target on BOTH sides of the relative_to() call, silently
# passing the path-within check. This assertion closes that gap.
assert CAPTURES_DIR.resolve().is_relative_to(PROJECT_ROOT.resolve()), (
    f"SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT — refusing to load. "
    f"CAPTURES_DIR={CAPTURES_DIR.resolve()}, PROJECT_ROOT={PROJECT_ROOT.resolve()}"
)
