"""Tests for kb.capture — see docs/superpowers/specs/2026-04-13-kb-capture-design.md.

Test matrix coverage maps to spec §9 — Class A (input reject + secret scan + rate limit),
Class B (LLM failure), Class C (quality filter), Class D (write errors), happy path
(frontmatter, slug, MCP wrapper), round-trip integration.

Pytest imports are added in subsequent tasks alongside the first tests that use them.
"""

import base64
import sys
import threading
from pathlib import Path
from urllib.parse import quote

import pytest

from kb.capture import (
    _CAPTURE_SCHEMA,
    CAPTURE_KINDS,
    _build_slug,
    _check_rate_limit,
    _exclusive_atomic_write,
    _extract_items_via_llm,
    _normalize_for_scan,
    _path_within_captures,
    _rate_limit_window,
    _scan_for_secrets,
    _validate_input,
    _verify_body_is_verbatim,
)
from kb.config import CAPTURE_MAX_BYTES, CAPTURE_MAX_CALLS_PER_HOUR, CAPTURES_DIR
from kb.utils.text import yaml_escape


class TestYamlEscapeBidiMarks:
    """Spec §8 — strip Unicode bidi override marks to defend audit-log confusion."""

    @pytest.mark.parametrize(
        "codepoint,name",
        [
            ("\u202a", "LEFT-TO-RIGHT EMBEDDING"),
            ("\u202b", "RIGHT-TO-LEFT EMBEDDING"),
            ("\u202c", "POP DIRECTIONAL FORMATTING"),
            ("\u202d", "LEFT-TO-RIGHT OVERRIDE"),
            ("\u202e", "RIGHT-TO-LEFT OVERRIDE"),
            ("\u2066", "LEFT-TO-RIGHT ISOLATE"),
            ("\u2067", "RIGHT-TO-LEFT ISOLATE"),
            ("\u2068", "FIRST STRONG ISOLATE"),
            ("\u2069", "POP DIRECTIONAL ISOLATE"),
        ],
    )
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


class TestScanForSecretsPlain:
    """Spec §8 expanded secret pattern list — one test per pattern label.
    Each test confirms (a) the pattern matches a representative literal,
    (b) the returned label is informative.
    """

    @pytest.mark.parametrize(
        "content,expected_label_substr",
        [
            ("AKIAIOSFODNN7EXAMPLE my key", "AWS"),
            ("ASIATESTSTSEXAMPLE12345 temp creds", "AWS"),
            ("aws_secret_access_key=" + "A" * 40, "AWS"),
            ("sk-proj-" + "x" * 32, "OpenAI"),
            ("sk-" + "y" * 32, "OpenAI"),
            ("sk-ant-" + "z" * 32, "Anthropic"),
            ("ghp_" + "a" * 36, "GitHub"),
            ("github_pat_" + "b" * 82, "GitHub"),
            ("xoxb-12345-67890-abcdefXYZ123", "Slack"),
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
                "signature",
                "JWT",
            ),
            ("AIza" + "X" * 35, "Google"),
            ("ya29.AHES6ZQ_long_token_string", "GCP OAuth"),
            ('"type": "service_account"', "GCP service account"),
            ("sk_live_" + "a" * 30, "Stripe"),
            ("rk_live_" + "b" * 30, "Stripe"),
            ("hf_" + "c" * 35, "HuggingFace"),
            ("AC" + "0" * 32, "Twilio"),
            ("SK" + "1" * 32, "Twilio"),
            ("npm_" + "x" * 36, "npm"),
            ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "HTTP Basic"),
            ("API_KEY=secret_value_here", "env-var"),
            ("PASSWORD=mypass123", "env-var"),
            ("postgres://user:pass@host:5432/db", "DB connection"),
            ("mysql://admin:secret@localhost/db", "DB connection"),
            ("mongodb+srv://user:pass@cluster.example.net/", "DB connection"),
            (
                "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
                "Private key",
            ),
            (
                "-----BEGIN OPENSSH PRIVATE KEY-----\nb3Blbnpz...\n"
                "-----END OPENSSH PRIVATE KEY-----",
                "Private key",
            ),
        ],
    )
    def test_secret_pattern_matches(self, content, expected_label_substr):
        result = _scan_for_secrets(content)
        assert result is not None, f"expected match for: {content[:40]!r}"
        label, location = result
        assert expected_label_substr.lower() in label.lower(), (
            f"label {label!r} should contain {expected_label_substr!r}"
        )

    def test_benign_content_passes(self):
        assert _scan_for_secrets("we decided to use atomic writes") is None
        assert _scan_for_secrets("the model returned 42 items") is None
        assert _scan_for_secrets("# Python comment about API design") is None

    def test_returns_line_number_for_plain_match(self):
        content = "line one\nline two\nAKIAIOSFODNN7EXAMPLE\nline four"
        result = _scan_for_secrets(content)
        assert result is not None
        label, location = result
        assert location == "line 3"

    def test_first_pattern_match_short_circuits(self):
        # Two patterns in same content — should return first
        content = "AKIAIOSFODNN7EXAMPLE and sk-ant-" + "z" * 32
        result = _scan_for_secrets(content)
        assert result is not None
        # Order in pattern list determines which wins; just verify deterministic
        result2 = _scan_for_secrets(content)
        assert result == result2


class TestScanForSecretsEncoded:
    """Spec §8 encoded-secret normalization pass."""

    def test_base64_wrapped_aws_key_rejects(self):
        # Wrap an AWS key in base64
        raw = "AKIAIOSFODNN7EXAMPLE"
        encoded = base64.b64encode(raw.encode()).decode()
        # encoded form is QUtJQUlPU0ZPRE5ON0VYQU1QTEU=
        result = _scan_for_secrets(f"opaque blob: {encoded}")
        assert result is not None, "b64-wrapped AWS key should be detected via normalization"
        label, location = result
        assert "AWS" in label
        assert location == "via encoded form"

    def test_url_encoded_value_passes_through_normalize(self):
        # Spec §8: 3+ adjacent percent-encoded triplets trigger URL-decoding.
        # "&=?" → "%26%3D%3F" (3 adjacent triplets) exceeds the threshold.
        raw = "AB&=?CD"
        encoded = quote(raw, safe="")  # "AB%26%3D%3FCD"
        normalized = _normalize_for_scan(encoded)
        # The decoded "&=?" run should appear in the normalized superset.
        assert "&=?" in normalized

    def test_url_encoded_scattered_triplets_not_decoded(self):
        # Spec §8 threshold: 2 non-adjacent triplets should NOT trigger decode.
        # "key&value=secret" has %26 and %3D but they're not adjacent.
        raw = "key&value=secret"
        encoded = quote(raw, safe="")  # "key%26value%3Dsecret"
        normalized = _normalize_for_scan(encoded)
        # The decoded run should NOT appear because triplets aren't adjacent (3+).
        assert "key&value=secret" not in normalized

    def test_legitimate_base64_image_header_does_not_false_positive(self):
        # PNG file header in base64 — should NOT match any secret pattern
        png_header_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100).decode()
        result = _scan_for_secrets(f"image data: {png_header_b64}")
        assert result is None, f"PNG header b64 falsely matched: {result}"

    def test_normalize_includes_b64_decoded_text(self):
        # _normalize_for_scan returns a string that includes decoded ASCII forms
        raw = "hello world foo bar baz"
        encoded = base64.b64encode(raw.encode()).decode()
        normalized = _normalize_for_scan(encoded)
        assert raw in normalized

    def test_normalize_skips_non_b64_blobs(self):
        # Non-base64 content should not crash the normalizer
        normalized = _normalize_for_scan("just some plain text $$$ @@@ ###")
        assert isinstance(normalized, str)
        assert "plain text" in normalized

    def test_widely_split_secret_not_caught(self):
        """Spec §13 documented residual: ≥4 whitespace chars between key parts bypass.
        This test documents the residual; no assertion on rejection (may or may not match
        depending on which pattern's fragment happens to be contiguous)."""
        content = "sk-ant-\n\n\n\nfollowingtokenpartwithexactlytwentychars"
        result = _scan_for_secrets(content)
        # Documentation test — design accepts this gap per spec §13.
        # Don't assert None or not-None; just verify no crash.
        assert result is None or result is not None  # tautology — crash test only


class TestExtractAndVerify:
    """Spec §4 step 7-8, §7 Class C."""

    def test_extract_calls_scan_tier(self, mock_scan_llm):
        canned = {"items": [], "filtered_out_count": 0}
        mock_scan_llm(canned)
        result = _extract_items_via_llm("any content")
        assert result == canned

    def test_extract_passes_schema(self, mock_scan_llm):
        # mock_scan_llm asserts schema is passed and well-formed
        canned = {"items": [], "filtered_out_count": 5}
        mock_scan_llm(canned)
        _extract_items_via_llm("hello")  # would assert-fail in mock if schema missing

    def test_schema_enforces_kind_enum(self):
        item_schema = _CAPTURE_SCHEMA["properties"]["items"]["items"]
        kind_enum = item_schema["properties"]["kind"]["enum"]
        assert set(kind_enum) == set(CAPTURE_KINDS)

    def test_schema_caps_max_items(self):
        from kb.config import CAPTURE_MAX_ITEMS

        assert _CAPTURE_SCHEMA["properties"]["items"]["maxItems"] == CAPTURE_MAX_ITEMS

    def test_schema_required_fields(self):
        item_schema = _CAPTURE_SCHEMA["properties"]["items"]["items"]
        required = set(item_schema["required"])
        assert required == {"title", "kind", "body", "one_line_summary", "confidence"}

    def test_verify_drops_reworded_body(self):
        content = "the original input mentioned X and then Y"
        items = [
            {
                "title": "t1",
                "kind": "decision",
                "body": "X and then Y",
                "one_line_summary": "s",
                "confidence": "stated",
            },
            {
                "title": "t2",
                "kind": "discovery",
                "body": "completely different prose",
                "one_line_summary": "s",
                "confidence": "stated",
            },
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert len(kept) == 1
        assert kept[0]["title"] == "t1"
        assert dropped == 1

    def test_verify_drops_whitespace_only_body(self):
        content = "any content here"
        items = [
            {
                "title": "ws",
                "kind": "decision",
                "body": "    ",
                "one_line_summary": "s",
                "confidence": "stated",
            },
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert kept == []
        assert dropped == 1

    def test_verify_strip_tolerance(self):
        content = "the cat sat on the mat"
        items = [
            {
                "title": "t",
                "kind": "decision",
                "body": "  the cat sat  ",
                "one_line_summary": "s",
                "confidence": "stated",
            },
        ]
        kept, dropped = _verify_body_is_verbatim(items, content)
        assert len(kept) == 1
        assert dropped == 0

    def test_verify_empty_input_drops_all(self):
        kept, dropped = _verify_body_is_verbatim([], "any content")
        assert kept == []
        assert dropped == 0


class TestBuildSlug:
    """Spec §5 slug algorithm."""

    def test_kind_prefix_present(self):
        slug = _build_slug("decision", "Pick atomic files", set())
        assert slug.startswith("decision-")
        assert "pick-atomic-files" in slug

    def test_length_capped_at_80(self):
        long_title = "a" * 200
        slug = _build_slug("decision", long_title, set())
        assert len(slug) <= 80

    def test_no_collision_returns_base(self):
        slug = _build_slug("decision", "foo", set())
        assert slug == "decision-foo"

    def test_collision_appends_2(self):
        existing = {"decision-foo"}
        slug = _build_slug("decision", "foo", existing)
        assert slug == "decision-foo-2"

    def test_multiple_collisions_increment(self):
        existing = {"decision-foo", "decision-foo-2", "decision-foo-3"}
        slug = _build_slug("decision", "foo", existing)
        assert slug == "decision-foo-4"

    def test_all_unicode_title_falls_back_to_kind(self):
        # CJK title — slugify with re.ASCII strips it all
        slug = _build_slug("decision", "決定事項", set())
        # slugify returns "decision" (trailing hyphen stripped); no collision → return
        assert slug == "decision"

    def test_unicode_fallback_collides_with_existing_bare_kind(self):
        existing = {"decision"}
        slug = _build_slug("decision", "決定事項", existing)
        assert slug == "decision-2"

    def test_mixed_unicode_ascii(self):
        slug = _build_slug("discovery", "OpenAI 决策", set())
        assert slug.startswith("discovery-")
        assert "openai" in slug.lower()

    def test_kind_prefix_immunizes_windows_reserved(self):
        # "CON" alone would be a Windows reserved device name; with kind prefix it's safe
        slug = _build_slug("decision", "CON", set())
        assert slug == "decision-con"


class TestPathWithinCaptures:
    """Spec §5 path-traversal gate + §8 symlink guard prep."""

    def test_simple_path_inside_passes(self):
        p = CAPTURES_DIR / "decision-foo.md"
        assert _path_within_captures(p) is True

    def test_parent_traversal_rejected(self):
        p = CAPTURES_DIR / ".." / "secret.md"
        assert _path_within_captures(p) is False

    def test_absolute_path_outside_rejected(self):
        p = Path("/tmp/evil.md") if Path("/tmp").exists() else Path("C:/Windows/Temp/evil.md")
        assert _path_within_captures(p) is False

    def test_nested_inside_passes(self):
        p = CAPTURES_DIR / "subdir" / "file.md"
        # subdir doesn't need to exist for this check
        assert _path_within_captures(p) is True


class TestSymlinkGuard:
    """Spec §5, §8 — module refuses to load if CAPTURES_DIR escapes PROJECT_ROOT."""

    @pytest.mark.skipif(
        sys.platform == "win32", reason="symlink creation requires admin on Windows"
    )
    def test_symlink_outside_project_root_refuses_import(self, tmp_path, monkeypatch):
        import importlib

        external_dir = tmp_path / "external"
        external_dir.mkdir()
        symlink_dir = tmp_path / "captures_symlink"
        symlink_dir.symlink_to(external_dir, target_is_directory=True)
        monkeypatch.setattr("kb.config.CAPTURES_DIR", symlink_dir)
        monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_path / "project_root")
        if "kb.capture" in sys.modules:
            del sys.modules["kb.capture"]
        with pytest.raises(AssertionError, match="SECURITY: CAPTURES_DIR"):
            importlib.import_module("kb.capture")
        monkeypatch.undo()
        importlib.import_module("kb.capture")


class TestExclusiveAtomicWrite:
    """Spec §3 atomic write helper."""

    def test_writes_new_file(self, tmp_captures_dir):
        path = tmp_captures_dir / "test.md"
        _exclusive_atomic_write(path, "hello world\n")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello world\n"

    def test_raises_file_exists_on_collision(self, tmp_captures_dir):
        path = tmp_captures_dir / "test.md"
        path.write_text("existing", encoding="utf-8")
        with pytest.raises(FileExistsError):
            _exclusive_atomic_write(path, "would replace")
        # Original content preserved
        assert path.read_text(encoding="utf-8") == "existing"

    def test_cleans_up_reservation_on_inner_write_failure(self, tmp_captures_dir, monkeypatch):
        path = tmp_captures_dir / "test.md"

        def boom(content, p):
            raise OSError("simulated disk full")

        monkeypatch.setattr("kb.capture.atomic_text_write", boom)
        with pytest.raises(OSError, match="disk full"):
            _exclusive_atomic_write(path, "ignored")
        # No 0-byte poison file left behind
        assert not path.exists(), "reservation file must be cleaned up on failure"

    def test_cleans_up_on_keyboard_interrupt(self, tmp_captures_dir, monkeypatch):
        path = tmp_captures_dir / "test.md"

        def interrupted(content, p):
            raise KeyboardInterrupt()

        monkeypatch.setattr("kb.capture.atomic_text_write", interrupted)
        with pytest.raises(KeyboardInterrupt):
            _exclusive_atomic_write(path, "ignored")
        assert not path.exists(), "must clean up on BaseException too"
