"""kb.capture — atomize messy text into discrete raw/captures/<slug>.md files.

Public API: capture_items(content, provenance) → CaptureResult
MCP tool wrapper: see kb.mcp.core.kb_capture.

Spec: docs/superpowers/specs/2026-04-13-kb-capture-design.md
"""

import base64
import binascii
import re
import threading
import time
from collections import deque
from urllib.parse import unquote

from kb.config import CAPTURE_MAX_BYTES, CAPTURE_MAX_CALLS_PER_HOUR

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
    # URL-encoded: if content has 2+ percent-encoded triplets, unquote it.
    if len(re.findall(r"%[0-9A-Fa-f]{2}", content)) >= 2:
        try:
            parts.append(unquote(content))
        except (ValueError, UnicodeDecodeError):
            pass
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
