"""Tests for kb.capture — see docs/superpowers/specs/2026-04-13-kb-capture-design.md.

Test matrix coverage maps to spec §9 — Class A (input reject + secret scan + rate limit),
Class B (LLM failure), Class C (quality filter), Class D (write errors), happy path
(frontmatter, slug, MCP wrapper), round-trip integration.

Pytest imports are added in subsequent tasks alongside the first tests that use them.
"""

import threading

import pytest

from kb.capture import _check_rate_limit, _rate_limit_window, _validate_input
from kb.config import CAPTURE_MAX_BYTES, CAPTURE_MAX_CALLS_PER_HOUR
from kb.utils.text import yaml_escape


class TestYamlEscapeBidiMarks:
    """Spec §8 — strip Unicode bidi override marks to defend audit-log confusion."""

    @pytest.mark.parametrize("codepoint,name", [
        ("\u202a", "LEFT-TO-RIGHT EMBEDDING"),
        ("\u202b", "RIGHT-TO-LEFT EMBEDDING"),
        ("\u202c", "POP DIRECTIONAL FORMATTING"),
        ("\u202d", "LEFT-TO-RIGHT OVERRIDE"),
        ("\u202e", "RIGHT-TO-LEFT OVERRIDE"),
        ("\u2066", "LEFT-TO-RIGHT ISOLATE"),
        ("\u2067", "RIGHT-TO-LEFT ISOLATE"),
        ("\u2068", "FIRST STRONG ISOLATE"),
        ("\u2069", "POP DIRECTIONAL ISOLATE"),
    ])
    def test_strips_bidi_codepoint(self, codepoint, name):
        result = yaml_escape(f"pay{codepoint}usalert")
        assert codepoint not in result, f"{name} ({codepoint!r}) should be stripped"
        # The visible chars should survive
        assert "pay" in result
        assert "usalert" in result

    def test_preserves_normal_unicode(self):
        # CJK, accented Latin, Cyrillic — all should survive unchanged
        for s in ["決定", "café", "Привет", "résumé"]:
            result = yaml_escape(s)
            assert s in result or result == s, f"normal unicode {s!r} altered: {result!r}"

    def test_bidi_and_control_both_stripped(self):
        # Bidi range (U+202A-2069) and control range (\x01-\x1f) are disjoint,
        # so order of stripping does not matter for output. This test verifies
        # both classes are removed in a single yaml_escape call without
        # interference, not the ordering itself.
        result = yaml_escape("a\u202eb\x01c")
        assert "\u202e" not in result
        assert "\x01" not in result
        # The visible chars survive
        assert "a" in result and "b" in result and "c" in result


class TestValidateInput:
    """Spec §4 step 5, §7 Class A (input reject)."""

    def test_empty_string_rejects(self):
        normalized, err = _validate_input("")
        assert normalized is None
        assert err.startswith("Error: content is empty")

    def test_whitespace_only_rejects(self):
        normalized, err = _validate_input("   \n\t  \r\n")
        assert normalized is None
        assert err.startswith("Error: content is empty")

    def test_at_boundary_passes(self):
        # Exactly CAPTURE_MAX_BYTES of UTF-8 bytes (ASCII so 1 byte/char)
        content = "a" * CAPTURE_MAX_BYTES
        normalized, err = _validate_input(content)
        assert err == ""
        assert normalized == content

    def test_one_byte_over_rejects(self):
        content = "a" * (CAPTURE_MAX_BYTES + 1)
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err
        assert str(CAPTURE_MAX_BYTES + 1) in err  # actual size in message

    def test_size_check_uses_utf8_bytes_not_chars(self):
        # 4-byte UTF-8 char × N where N×4 > CAPTURE_MAX_BYTES but N < CAPTURE_MAX_BYTES
        char = "𝕏"  # 4 bytes in UTF-8
        n = (CAPTURE_MAX_BYTES // 4) + 1  # over the cap by bytes, well under by chars
        content = char * n
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err

    def test_crlf_normalized_to_lf(self):
        normalized, err = _validate_input("a\r\nb\r\nc")
        assert err == ""
        assert normalized == "a\nb\nc"

    def test_size_check_runs_pre_normalize(self):
        # 25001 CRLF pairs = 50002 raw bytes / 50001 post-LF bytes.
        # Per spec §4 invariant 5, size check is on raw — must reject.
        content = "ab\r\n" * 12500 + "ab\r\n"  # 50004 raw bytes
        assert len(content.encode("utf-8")) > CAPTURE_MAX_BYTES
        # Confirm post-normalize would be under cap
        assert len(content.replace("\r\n", "\n").encode("utf-8")) <= CAPTURE_MAX_BYTES
        normalized, err = _validate_input(content)
        assert normalized is None
        assert "exceeds" in err

    def test_returns_normalized_form_for_downstream(self):
        # Downstream secret scan / verbatim check operates on the LF-normalized form
        normalized, err = _validate_input("hello\r\nworld")
        assert err == ""
        assert "\r\n" not in normalized
        assert normalized == "hello\nworld"


@pytest.fixture(autouse=False)
def reset_rate_limit():
    """Clear the module-level deque before each rate-limit test."""
    _rate_limit_window.clear()
    yield
    _rate_limit_window.clear()


class TestCheckRateLimit:
    """Spec §4 step 4, §8 thread-safe rate limit."""

    def test_first_call_allowed(self, reset_rate_limit):
        allowed, retry_after = _check_rate_limit()
        assert allowed is True
        assert retry_after == 0

    def test_under_cap_allowed(self, reset_rate_limit):
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            allowed, _ = _check_rate_limit()
            assert allowed is True

    def test_over_cap_rejected_with_retry_after(self, reset_rate_limit):
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            _check_rate_limit()
        allowed, retry_after = _check_rate_limit()
        assert allowed is False
        assert retry_after > 0
        # Retry should be within an hour
        assert retry_after <= 3600

    def test_window_slides_old_entries_purged(self, reset_rate_limit, monkeypatch):
        # Fake the clock — populate window with stale timestamps then advance time
        fake_now = [1000.0]
        monkeypatch.setattr("kb.capture.time.time", lambda: fake_now[0])
        # Fill to cap at fake_now=1000
        for _ in range(CAPTURE_MAX_CALLS_PER_HOUR):
            _check_rate_limit()
        # Verify next call rejects
        allowed, _ = _check_rate_limit()
        assert allowed is False
        # Advance clock past 3600s — old entries should be purged
        fake_now[0] = 1000.0 + 3601
        allowed, _ = _check_rate_limit()
        assert allowed is True, "purged entries should free capacity"

    def test_thread_safe_under_concurrent_load(self, reset_rate_limit):
        """Spec §8: 2-thread test at the 59→60 boundary.
        Without threading.Lock, both threads can pass len(deque)<60 then both append → 2 over cap.
        With the lock, exactly 1 of the (cap+1) total attempts is rejected.
        """
        results: list[tuple[bool, int]] = []
        results_lock = threading.Lock()
        n_per_thread = (CAPTURE_MAX_CALLS_PER_HOUR + 1) // 2 + 1

        def worker():
            for _ in range(n_per_thread):
                r = _check_rate_limit()
                with results_lock:
                    results.append(r)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        rejected = sum(1 for allowed, _ in results if not allowed)
        total = len(results)
        accepted = total - rejected
        # Exactly CAPTURE_MAX_CALLS_PER_HOUR allowed; the rest rejected
        assert accepted == CAPTURE_MAX_CALLS_PER_HOUR, f"accepted={accepted}, total={total}"
        assert rejected == total - CAPTURE_MAX_CALLS_PER_HOUR
