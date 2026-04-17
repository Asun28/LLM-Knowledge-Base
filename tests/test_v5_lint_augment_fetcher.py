"""SafeTransport DNS-rebinding tests + basic FetchResult shape + fetch behavior."""

import socket
from unittest.mock import patch

import httpcore
import pytest


@pytest.fixture(autouse=True)
def _auto_mock_robots(request):
    """Pre-register a permissive robots.txt for every httpx_mock test.

    AugmentFetcher.fetch hits `/robots.txt` first when respect_robots=True,
    so tests that only care about downstream behavior (allowlists, size cap,
    content-type, secret scan) need a default robots response or they fail
    teardown with 'request not expected'. Tests that explicitly exercise
    robots.txt register their own mock BEFORE this fixture runs (via
    @pytest.mark.skip_default_robots), so this fixture is skipped there.
    """
    if "httpx_mock" not in request.fixturenames:
        yield
        return
    if request.node.get_closest_marker("skip_default_robots"):
        yield
        return
    mock = request.getfixturevalue("httpx_mock")
    # Permissive robots for the host 'example.com' (used by most tests)
    # with is_optional=True so tests that don't hit it don't fail teardown.
    mock.add_response(
        url="https://example.com/robots.txt",
        content=b"User-agent: *\nAllow: /\n",
        headers={"content-type": "text/plain"},
        is_optional=True,
        is_reusable=True,
    )
    yield


def test_safe_transport_version_guard_accepts_current_httpx():
    """With the pinned httpx 0.28.x line the import does not raise, and
    the SafeBackend installs on HTTPTransport._pool._network_backend."""
    import httpx

    from kb.lint.fetcher import SafeBackend, SafeTransport

    assert httpx.__version__.startswith("0.28."), (
        f"test env drifted off httpx 0.28.x: {httpx.__version__}"
    )
    t = SafeTransport()
    assert isinstance(t._pool._network_backend, SafeBackend)


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


def test_safe_backend_blocks_unspecified_ipv4():
    """0.0.0.0 is unspecified (not covered by is_private/is_loopback/is_reserved
    on all Python versions). Must still be rejected."""
    from kb.lint.fetcher import SafeBackend

    backend = SafeBackend()
    fake_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", 80))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(httpcore.ConnectError, match="private/reserved"):
            backend.connect_tcp("any.example.com", 80, timeout=1.0)


def test_safe_backend_blocks_unspecified_ipv6():
    """:: is unspecified IPv6. Must still be rejected."""
    from kb.lint.fetcher import SafeBackend

    backend = SafeBackend()
    fake_infos = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::", 80, 0, 0))]
    with patch("socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(httpcore.ConnectError, match="private/reserved"):
            backend.connect_tcp("any6.example.com", 80, timeout=1.0)


def test_safe_backend_rejects_when_any_resolved_ip_is_private():
    """DNS-rebinding defense: even one private IP in the RR-set is enough to reject."""
    from kb.lint.fetcher import SafeBackend

    backend = SafeBackend()
    fake_infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80)),  # public
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


def test_safe_backend_connects_by_ip_closes_dns_rebind_window():
    """Connect with the already-validated IP, not the hostname.

    Regression guard for the DNS rebinding TOCTOU: attacker DNS with TTL=0
    can return 8.8.8.8 on the pre-flight getaddrinfo (passes the private-IP
    check) and then 127.0.0.1 on the OS connect's second resolution. If
    SafeBackend deferred to a hostname-based connect, the kernel would
    re-resolve and use the private IP. Instead we bind directly to the
    validated address so no second resolution happens.
    """
    from kb.lint.fetcher import SafeBackend

    backend = SafeBackend()
    # First call: pre-flight resolution returns a PUBLIC IP.
    # Second call (if any): returns a PRIVATE IP — would be exploited.
    public_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))]
    private_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
    getaddrinfo_calls: list[tuple] = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        getaddrinfo_calls.append((host, port))
        # Return public on first call, private on any later calls
        return public_infos if len(getaddrinfo_calls) == 1 else private_infos

    class _FakeSocket:
        def setsockopt(self, *_a, **_kw):
            return None

        def close(self):
            return None

    created_with: list[tuple] = []

    def fake_create_connection(address, *args, **kwargs):
        created_with.append(address)
        return _FakeSocket()

    # Also stub SyncStream so we don't touch the real one (its ctor asserts socket)
    class _FakeStream:
        def __init__(self, sock):
            self.sock = sock

    with (
        patch("socket.getaddrinfo", side_effect=fake_getaddrinfo),
        patch("socket.create_connection", side_effect=fake_create_connection),
        patch("httpcore._backends.sync.SyncStream", _FakeStream),
    ):
        backend.connect_tcp("rebind.example.com", 80, timeout=1.0)

    # The socket must be opened against the IP STRING, not the hostname.
    # If we re-resolved at OS connect, the kernel's second getaddrinfo would
    # have returned the private IP.
    assert len(created_with) == 1
    address = created_with[0]
    assert address[0] == "8.8.8.8", f"expected connect-by-IP '8.8.8.8', got {address[0]!r}"
    # Exactly one resolution — no second lookup the attacker could flip.
    assert len(getaddrinfo_calls) == 1


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


@pytest.mark.skip_default_robots
def test_fetch_accepts_subdomain_allowlist_entry(httpx_mock):
    """Subdomain-aware allowlist: 'en.wikipedia.org' matches a Wikipedia URL.

    Prevents regression of the fetcher/orchestrator mismatch where the orchestrator
    approved `https://en.wikipedia.org/...` (subdomain match against the allowlist)
    but the fetcher rejected it because get_fld() returns 'wikipedia.org' (eTLD+1).
    """
    httpx_mock.add_response(
        url="https://en.wikipedia.org/robots.txt",
        content=b"User-agent: *\nAllow: /\n",
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_response(
        url="https://en.wikipedia.org/wiki/X",
        headers={"content-type": "text/html"},
        content=(
            b"<html><body><article>"
            b"This is a reasonably long Wikipedia article about X so that "
            b"trafilatura keeps it as the main body and returns markdown."
            b"</article></body></html>"
        ),
    )
    f = _build_fetcher(allowed=("en.wikipedia.org",))
    r = f.fetch("https://en.wikipedia.org/wiki/X")
    assert r.status == "ok", f"expected ok, got {r.status}: {r.reason}"


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


def test_fetch_tolerates_malformed_content_length(httpx_mock):
    """Non-integer content-length must not crash; stream cap still enforced."""
    body = (
        b"<html><body><article>"
        b"This article has a malformed content-length header but the body "
        b"itself is well under the streaming cap. The fetch must succeed "
        b"and we fall back to the byte-counting stream gate."
        b"</article></body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/bad-clen",
        headers={
            "content-length": "not-a-number",
            "content-type": "text/html",
        },
        content=body,
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/bad-clen")
    # Must not crash with ValueError; streaming cap honored via actual bytes
    assert r.status == "ok", f"expected ok, got {r.status}: {r.reason}"
    assert r.bytes == len(body)


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


def test_fetch_redirect_to_off_allowlist_domain_blocks_before_request(httpx_mock):
    """SSRF defense: redirect to an off-allowlist host must be blocked BEFORE
    we issue the next request (so no IP/headers leak to the attacker host).

    pytest-httpx fails teardown with 'response was not requested' if we
    register a mock and never hit it — we exploit that here to PROVE the
    fetcher never called the attacker URL.
    """
    # Register the 302 from the allowlisted origin
    httpx_mock.add_response(
        url="https://example.com/r",
        status_code=302,
        headers={"location": "https://attacker.example/page"},
    )
    # Do NOT register attacker.example — if we fetch it, pytest-httpx raises
    # because no mock matches, proving the network request was never issued.
    f = _build_fetcher(allowed=("example.com",))
    r = f.fetch("https://example.com/r")
    assert r.status == "blocked"
    assert "domain" in r.reason.lower()


def test_fetch_follows_same_allowlist_redirect(httpx_mock):
    """Positive: 302 within the same allowlisted host must follow to the
    target, validate, and return ok with the final URL."""
    httpx_mock.add_response(
        url="https://example.com/r",
        status_code=302,
        headers={"location": "https://example.com/p"},
    )
    httpx_mock.add_response(
        url="https://example.com/p",
        headers={"content-type": "text/html"},
        content=(
            b"<html><body><article>"
            b"Destination page after the in-allowlist 302. Enough text "
            b"for trafilatura to treat this as main body content."
            b"</article></body></html>"
        ),
    )
    f = _build_fetcher(allowed=("example.com",))
    r = f.fetch("https://example.com/r")
    assert r.status == "ok", f"expected ok, got {r.status}: {r.reason}"
    assert r.url == "https://example.com/p"


def test_fetch_redirect_to_disallowed_scheme_blocked(httpx_mock):
    """SSRF defense: redirect to file:// / javascript: / data: must be blocked
    with a clear 'scheme' reason."""
    httpx_mock.add_response(
        url="https://example.com/r",
        status_code=302,
        headers={"location": "file:///etc/passwd"},
    )
    f = _build_fetcher(allowed=("example.com",))
    r = f.fetch("https://example.com/r")
    assert r.status == "blocked"
    assert "scheme" in r.reason.lower()


def test_fetch_redirect_without_location_header_fails(httpx_mock):
    """A 3xx without a Location header is server-side broken; return failed
    cleanly rather than hanging or crashing."""
    httpx_mock.add_response(
        url="https://example.com/r",
        status_code=302,
        headers={"content-type": "text/html"},
    )
    f = _build_fetcher(allowed=("example.com",))
    r = f.fetch("https://example.com/r")
    assert r.status == "failed"
    assert "location" in r.reason.lower()


def test_fetch_happy_path_html(httpx_mock):
    html = b"<html><body><article><h1>Title</h1><p>Real content here.</p></article></body></html>"
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


def test_secret_scan_rejects_aws_key_in_prose(httpx_mock):
    # split-string, real-looking pattern — never a committed secret
    aws_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    body = (
        f"<html><body><article>The leaked key is {aws_key} "
        "and it is documented in this article with enough surrounding context "
        "to survive trafilatura's boilerplate stripper.</article></body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/leak",
        headers={"content-type": "text/html"},
        content=body.encode(),
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/leak")
    assert r.status == "blocked"
    assert "secret" in r.reason.lower()


def test_secret_scan_allows_aws_key_in_code_fence(httpx_mock):
    # split, in markdown fence — code-strip should allow this through
    aws_key = "AKIA" + "EXAMPLEEXAMPLEXX"
    body_md = (
        "# IAM tutorial\n\n"
        "Here is a long explanatory paragraph about IAM access keys "
        "so trafilatura has enough text to treat this as the main article "
        "and not strip it as boilerplate noise around a short snippet.\n\n"
        f"```python\nclient = boto3.client(aws_access_key_id='{aws_key}')\n```\n\n"
        "This is documentation. The example above uses a fictitious key."
    )
    body_html = f"<html><body><article>{body_md}</article></body></html>"
    httpx_mock.add_response(
        url="https://example.com/iam-doc",
        headers={"content-type": "text/html"},
        content=body_html.encode(),
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/iam-doc")
    # Code-block-strip should make the AWS-regex sweep miss this
    assert r.status == "ok", f"expected ok but got {r.status}: {r.reason}"


def test_secret_scan_rejects_postgres_dsn(httpx_mock):
    body = (
        b"<html><body><article>"
        b"Use postgresql://admin:supersecret@db.internal.example/mydb to connect. "
        b"This walkthrough explains how to set up the connection pool "
        b"and includes enough narrative for trafilatura to recognize it."
        b"</article></body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/dsn",
        headers={"content-type": "text/html"},
        content=body,
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/dsn")
    assert r.status == "blocked"


def test_secret_scan_rejects_npm_authtoken(httpx_mock):
    token = "abcdefghij" + "0123456789ABCDEFG_-"
    body = (
        "<html><body><article>"
        "Add to .npmrc:\n"
        f"//registry.npmjs.org/:_authToken={token}\n"
        "This enables authenticated npm publish for your package. "
        "The _authToken above is pulled from your npm account settings."
        "</article></body></html>"
    )
    httpx_mock.add_response(
        url="https://example.com/npm",
        headers={"content-type": "text/html"},
        content=body.encode(),
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/npm")
    assert r.status == "blocked"


@pytest.mark.skip_default_robots
def test_robots_allow_proceeds(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        content=b"User-agent: *\nAllow: /\n",
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_response(
        url="https://example.com/page",
        headers={"content-type": "text/html"},
        content=(
            b"<html><body><article>Hello. This article is long enough "
            b"for trafilatura to treat it as body content and extract "
            b"it cleanly for the markdown output.</article></body></html>"
        ),
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/page", respect_robots=True)
    assert r.status == "ok"


@pytest.mark.skip_default_robots
def test_robots_disallow_blocks_when_respected(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        content=b"User-agent: *\nDisallow: /\n",
        headers={"content-type": "text/plain"},
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/page", respect_robots=True)
    assert r.status == "blocked"
    assert "robots" in r.reason.lower()


@pytest.mark.skip_default_robots
def test_robots_unavailable_does_not_block(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://example.com/page",
        headers={"content-type": "text/html"},
        content=(
            b"<html><body><article>Hi there. This is a reasonably long "
            b"article about something that trafilatura will treat as "
            b"the main body of the page.</article></body></html>"
        ),
    )
    f = _build_fetcher()
    r = f.fetch("https://example.com/page", respect_robots=True)
    assert r.status == "ok"
