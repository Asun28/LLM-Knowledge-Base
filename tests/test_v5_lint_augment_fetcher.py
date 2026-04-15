"""SafeTransport DNS-rebinding tests + basic FetchResult shape + fetch behavior."""
import socket
from unittest.mock import patch

import httpcore
import httpx
import pytest


def test_safe_backend_blocks_loopback():
    from kb.lint.fetcher import SafeBackend
    backend = SafeBackend()
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(httpcore.ConnectError, match="private/reserved"):
            backend.connect_tcp("evil.example.com", 80, timeout=1.0)


def test_safe_backend_blocks_aws_metadata():
    from kb.lint.fetcher import SafeBackend
    backend = SafeBackend()
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(httpcore.ConnectError, match="private/reserved"):
            backend.connect_tcp("metadata.local", 80, timeout=1.0)


def test_safe_backend_blocks_private_ranges():
    from kb.lint.fetcher import SafeBackend
    backend = SafeBackend()
    for private_ip in ("10.0.0.1", "172.16.5.5", "192.168.1.1"):
        fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (private_ip, 80))]
        with patch("socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(httpcore.ConnectError):
                backend.connect_tcp("internal.example.com", 80, timeout=1.0)


def test_safe_backend_rejects_when_any_resolved_ip_is_private():
    """DNS-rebinding defense: even one private IP in the RR-set is enough to reject."""
    from kb.lint.fetcher import SafeBackend
    backend = SafeBackend()
    fake_infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80)),       # public
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80)),  # PRIVATE
    ]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(httpcore.ConnectError, match="private/reserved"):
            backend.connect_tcp("rebind.example.com", 80, timeout=1.0)


def test_safe_backend_dns_failure_raises_connect_error():
    from kb.lint.fetcher import SafeBackend
    backend = SafeBackend()
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("nodename nor servname provided")):
        with pytest.raises(httpcore.ConnectError, match="DNS resolution failed"):
            backend.connect_tcp("nonexistent.invalid", 80, timeout=1.0)


def test_fetch_result_dataclass_shape():
    from kb.lint.fetcher import FetchResult
    r = FetchResult(
        status="ok",
        content="hi",
        extracted_markdown="hi",
        content_type="text/html",
        bytes=2,
        reason=None,
        url="https://x.test",
    )
    assert r.status == "ok"
    assert r.content == "hi"
    assert r.url == "https://x.test"
    # Failed shape
    f = FetchResult(
        status="blocked",
        content=None,
        extracted_markdown=None,
        content_type="",
        bytes=0,
        reason="private IP",
        url="https://internal",
    )
    assert f.status == "blocked"
    assert f.reason == "private IP"


def _build_fetcher(allowed: tuple[str, ...] = ("example.com",)):
    from kb.lint.fetcher import AugmentFetcher
    return AugmentFetcher(allowed_domains=allowed, version="0.10.0")


def test_fetch_rejects_non_http_scheme():
    f = _build_fetcher()
    r = f.fetch("file:///etc/passwd")
    assert r.status == "blocked"
    assert "scheme" in r.reason.lower()


def test_fetch_rejects_non_allowlisted_domain():
    f = _build_fetcher(allowed=("en.wikipedia.org",))
    r = f.fetch("https://attacker.example/page")
    assert r.status == "blocked"
    assert "domain" in r.reason.lower()


def test_fetch_rejects_oversize_via_content_length(httpx_mock):
    from kb.config import AUGMENT_FETCH_MAX_BYTES
    httpx_mock.add_response(
        url="https://example.com/big",
        headers={
            "content-length": str(AUGMENT_FETCH_MAX_BYTES + 1),
            "content-type": "text/html",
        },
        content=b"<html>tiny</html>",
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/big")
    assert r.status == "blocked"
    assert "content-length" in r.reason.lower() or "size" in r.reason.lower()


def test_fetch_rejects_disallowed_content_type(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/x.exe",
        headers={"content-type": "application/octet-stream"},
        content=b"\x00\x01\x02",
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/x.exe")
    assert r.status == "blocked"
    assert "content-type" in r.reason.lower()


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_fetch_too_many_redirects(httpx_mock):
    # Build a redirect chain longer than max_redirects (10)
    for i in range(15):
        httpx_mock.add_response(
            url=f"https://example.com/r{i}",
            status_code=302,
            headers={"location": f"https://example.com/r{i + 1}"},
        )
    f = _build_fetcher()
    r = f.fetch("https://example.com/r0")
    assert r.status == "failed"
    assert "redirect" in r.reason.lower()


def test_fetch_redirects_to_off_allowlist_rejected(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/r",
        status_code=302,
        headers={"location": "https://attacker.example/page"},
    )
    httpx_mock.add_response(
        url="https://attacker.example/page",
        headers={"content-type": "text/html"},
        content=b"<html><body>evil</body></html>",
    )
    f = _build_fetcher(allowed=("example.com",))
    r = f.fetch("https://example.com/r")
    # httpx itself follows; our post-fetch URL check should catch
    assert r.status == "blocked"
    assert "domain" in r.reason.lower()


def test_fetch_happy_path_html(httpx_mock):
    html = (
        b"<html><body><article><h1>Title</h1>"
        b"<p>Real content here.</p></article></body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/page",
        headers={"content-type": "text/html; charset=utf-8"},
        content=html,
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/page")
    assert r.status == "ok"
    assert r.bytes == len(html)
    assert "Real content here." in r.extracted_markdown
