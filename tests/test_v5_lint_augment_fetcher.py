"""SafeTransport DNS-rebinding tests + basic FetchResult shape."""
import socket
from unittest.mock import patch

import httpcore
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
