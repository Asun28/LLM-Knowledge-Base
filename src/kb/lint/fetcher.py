"""Augment HTTP fetcher: DNS-rebind-safe transport + content safety rails.

Public API:
- AugmentFetcher: one instance per augment run, pooled connections
- FetchResult: status + content/markdown + reason

Safety properties:
- SafeBackend rejects ANY DNS RR-set containing a private/loopback/link-local
  /reserved IP (defeats DNS rebinding by pre-resolving and validating every
  address before deferring to the parent backend's connect).
- Schemes restricted to http/https.
- Domain allowlist enforced before any network call.
- Stream cap on body bytes; abort mid-download.
- Content-type allowlist.
- Secret scan + boundary marker on extracted text before saving.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpcore
import httpx
import trafilatura
from httpcore._backends.sync import SyncBackend

try:
    from tld import get_fld
except ImportError:  # pragma: no cover - tld is a runtime dep
    get_fld = None

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Shape returned by AugmentFetcher.fetch().

    status:
      "ok"      - content + extracted_markdown populated
      "blocked" - safety rail rejected (reason populated)
      "failed"  - network/HTTP error (reason populated)
    """

    status: Literal["ok", "blocked", "failed"]
    content: str | None
    extracted_markdown: str | None
    content_type: str
    bytes: int
    reason: str | None
    url: str


class SafeBackend(SyncBackend):
    """httpcore NetworkBackend that pre-validates resolved IPs.

    Defeats DNS rebinding by:
    1. Resolving the host once to all addresses.
    2. Rejecting if ANY address in the RR-set is private/loopback/link-local
       /reserved/multicast.
    3. Connecting directly to the validated IP (no second DNS lookup) to close
       the TOCTOU window an attacker with TTL=0 DNS could exploit by returning
       a public IP at check time and a private IP at connect time.

    TLS SNI / cert verification still uses the original hostname because
    httpcore wraps the returned TCP stream with TLS at a higher layer using
    the URL's hostname, not the raw connect address.

    Used in place of the default SyncBackend by SafeTransport.
    """

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: list | None = None,
    ) -> httpcore.NetworkStream:
        # Resolve once and validate every IP in the RR-set. If ANY resolved
        # address is private/reserved we refuse the whole host — we cannot
        # predict which address the stack would pick at connect time.
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise httpcore.ConnectError(f"DNS resolution failed for {host}: {e}") from e

        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise httpcore.ConnectError(
                    f"Blocked private/reserved address {ip} for host {host}"
                )

        if not infos:
            raise httpcore.ConnectError(f"DNS resolution returned no addresses for {host}")

        # Pick the first validated address and connect directly to the IP.
        # This bypasses OS-level re-resolution so a DNS-rebinding attacker
        # cannot swap in a private IP between check and connect.
        family, socktype, proto, _, sockaddr = infos[0]
        ip_str = sockaddr[0]

        source_address = None if local_address is None else (local_address, 0)
        try:
            sock = socket.create_connection(
                (ip_str, port),
                timeout if timeout is not None else 5.0,
                source_address=source_address,
            )
        except OSError as e:
            raise httpcore.ConnectError(
                f"Failed to connect to {host} ({ip_str}:{port}): {e}"
            ) from e

        if socket_options:
            for option in socket_options:
                sock.setsockopt(*option)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Local import: httpcore's internal module layout shifts between
        # versions, and we only need this on the success path.
        from httpcore._backends.sync import SyncStream

        return SyncStream(sock)


class SafeTransport(httpx.HTTPTransport):
    """httpx HTTPTransport that routes through SafeBackend.

    Drop-in replacement for httpx.HTTPTransport(); injects SafeBackend into the
    underlying httpcore.ConnectionPool.
    """

    def __init__(self, *, verify: bool = True, **kwargs):
        super().__init__(verify=verify, **kwargs)
        # httpx 0.28 stores the pool at self._pool; replace its network_backend.
        self._pool._network_backend = SafeBackend()


def build_client(version: str) -> httpx.Client:
    """Build the augment HTTP client with all safety transports + headers.

    Caller is responsible for closing (use as context manager).
    """
    from kb.config import (
        AUGMENT_FETCH_CONNECT_TIMEOUT,
        AUGMENT_FETCH_MAX_REDIRECTS,
        AUGMENT_FETCH_READ_TIMEOUT,
    )

    return httpx.Client(
        transport=SafeTransport(),
        timeout=httpx.Timeout(
            connect=AUGMENT_FETCH_CONNECT_TIMEOUT,
            read=AUGMENT_FETCH_READ_TIMEOUT,
            write=10.0,
            pool=5.0,
        ),
        headers={
            "User-Agent": (
                f"LLM-WikiFlywheel/{version} "
                "(+https://github.com/Asun28/llm-wiki-flywheel)"
            )
        },
        follow_redirects=True,
        max_redirects=AUGMENT_FETCH_MAX_REDIRECTS,
    )


def _registered_domain(url: str) -> str | None:
    """Return the eTLD+1 (registered domain) for a URL, or None on failure."""
    if get_fld is None:
        # Fallback: use the netloc verbatim (less accurate but functional).
        return urlparse(url).netloc.lower()
    try:
        return get_fld(url, fix_protocol=True)
    except Exception:
        return None


def _url_is_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    """Return True if URL's host matches ``allowed_domains``.

    Match rule: either the registered domain (eTLD+1) OR the full netloc must
    equal an allowlist entry, OR the netloc must be a subdomain of an allowlist
    entry (e.g., ``en.wikipedia.org`` in the allowlist allows
    ``xx.en.wikipedia.org``). This lets the allowlist use narrow entries like
    ``en.wikipedia.org`` without requiring eTLD+1 matching, and still accepts
    ``arxiv.org`` directly.

    Shared between the fetcher's allowlist gate and the orchestrator's URL
    proposer filter so both make the same decision for a given URL.
    """
    try:
        netloc = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return False
    if not netloc:
        return False
    # Strip userinfo/port
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.rsplit(":", 1)[0]
    rd = _registered_domain(url)
    rd_lower = rd.lower() if rd else None
    for d in allowed_domains:
        dl = d.lower()
        if netloc == dl or netloc.endswith("." + dl):
            return True
        if rd_lower and rd_lower == dl:
            return True
    return False


def _strip_code_for_scan(text: str) -> str:
    """Strip fenced code blocks + inline code spans for secret scanning purposes only.

    The original text is preserved for output; this helper returns a code-stripped
    *view* used solely as input to regex sweeps. Documentation pages (e.g.,
    Wikipedia IAM articles) often contain example AKIA-prefix strings inside
    code fences - we don't want to reject the whole fetch over that.
    """
    # Strip fenced code blocks (``` ... ```)
    no_fenced = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Strip inline code spans (`...`)
    no_inline = re.sub(r"`[^`\n]+`", "", no_fenced)
    return no_inline


def _secret_scan(text: str) -> tuple[str, str] | None:
    """Return (label, matched_snippet) on first hit, None if clean."""
    from kb.capture import _CAPTURE_SECRET_PATTERNS

    code_stripped = _strip_code_for_scan(text)
    for label, pattern in _CAPTURE_SECRET_PATTERNS:
        m = pattern.search(code_stripped)
        if m:
            return label, m.group(0)[:80]
    return None


class AugmentFetcher:
    """One-instance-per-run HTTP fetcher.

    Combines DNS-rebind-safe transport, scheme/domain/content-type allowlists,
    stream-with-size-cap, trafilatura markdown extraction, secret scanning on
    the extracted view, and optional robots.txt enforcement.
    """

    def __init__(self, *, allowed_domains: tuple[str, ...], version: str):
        from kb.config import (
            AUGMENT_CONTENT_TYPES,
            AUGMENT_FETCH_MAX_BYTES,
        )

        self.allowed_domains = tuple(d.lower() for d in allowed_domains)
        self.allowed_content_types = AUGMENT_CONTENT_TYPES
        self.max_bytes = AUGMENT_FETCH_MAX_BYTES
        self._client = build_client(version)
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._ua = (
            f"LLM-WikiFlywheel/{version} "
            "(+https://github.com/Asun28/llm-wiki-flywheel)"
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _check_robots(self, url: str) -> bool:
        """Return True if URL is allowed (or robots.txt unavailable)."""
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._robots_cache:
            rp = self._robots_cache[host_key]
            if rp is None:
                return True
            return rp.can_fetch(self._ua, url)

        robots_url = f"{host_key}/robots.txt"
        # Fetch via our own client (SafeTransport) - pass respect_robots=False
        # to break recursion. Using RobotFileParser.read() would bypass our
        # transport via urllib.request and open an SSRF hole.
        result = self.fetch(robots_url, respect_robots=False)
        if result.status != "ok" or not result.content:
            self._robots_cache[host_key] = None
            return True
        rp = RobotFileParser()
        rp.parse(result.content.splitlines())
        self._robots_cache[host_key] = rp
        return rp.can_fetch(self._ua, url)

    def fetch(self, url: str, *, respect_robots: bool = True) -> FetchResult:
        # 1. Scheme allow-list
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return FetchResult(
                status="blocked",
                content=None,
                extracted_markdown=None,
                content_type="",
                bytes=0,
                reason=f"disallowed scheme: {parsed.scheme}",
                url=url,
            )

        # 2. Domain allow-list (initial URL) — subdomain-aware (see _url_is_allowed)
        if not _url_is_allowed(url, self.allowed_domains):
            return FetchResult(
                status="blocked",
                content=None,
                extracted_markdown=None,
                content_type="",
                bytes=0,
                reason=f"domain not in allowlist: {_registered_domain(url)}",
                url=url,
            )

        # 2.5. robots.txt check (advisory: caller may opt out via respect_robots=False)
        if respect_robots and not self._check_robots(url):
            return FetchResult(
                status="blocked",
                content=None,
                extracted_markdown=None,
                content_type="",
                bytes=0,
                reason=f"blocked by robots.txt for {url}",
                url=url,
            )

        # 3. Stream-fetch with size cap
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()

                # 4. Final URL allow-list (catches redirects to off-allow domains)
                final_url_str = str(response.url)
                if not _url_is_allowed(final_url_str, self.allowed_domains):
                    return FetchResult(
                        status="blocked",
                        content=None,
                        extracted_markdown=None,
                        content_type="",
                        bytes=0,
                        reason=(
                            "redirect target domain not in allowlist: "
                            f"{_registered_domain(final_url_str)}"
                        ),
                        url=final_url_str,
                    )

                # 5. Content-type allow-list
                ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and ctype not in self.allowed_content_types:
                    return FetchResult(
                        status="blocked",
                        content=None,
                        extracted_markdown=None,
                        content_type=ctype,
                        bytes=0,
                        reason=f"disallowed content-type: {ctype}",
                        url=str(response.url),
                    )

                # 6. Size cap (header). Tolerate malformed content-length:
                # an RFC-violating server might send a non-integer value; fall
                # back to unknown (None) and rely on the streaming cap below.
                clen_raw = response.headers.get("content-length")
                clen: int | None
                if clen_raw:
                    try:
                        clen = int(clen_raw)
                    except (TypeError, ValueError):
                        logger.debug(
                            "Ignoring malformed content-length header %r for %s",
                            clen_raw,
                            response.url,
                        )
                        clen = None
                else:
                    clen = None
                if clen is not None and clen > self.max_bytes:
                    return FetchResult(
                        status="blocked",
                        content=None,
                        extracted_markdown=None,
                        content_type=ctype,
                        bytes=clen,
                        reason=f"content-length {clen} exceeds cap {self.max_bytes}",
                        url=str(response.url),
                    )

                # 7. Stream + cap
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(chunk_size=32_768):
                    total += len(chunk)
                    if total > self.max_bytes:
                        return FetchResult(
                            status="blocked",
                            content=None,
                            extracted_markdown=None,
                            content_type=ctype,
                            bytes=total,
                            reason=f"stream exceeded cap {self.max_bytes} bytes",
                            url=str(response.url),
                        )
                    chunks.append(chunk)
                raw = b"".join(chunks)
                final_url = str(response.url)

        except httpx.TooManyRedirects as e:
            return FetchResult(
                status="failed",
                content=None,
                extracted_markdown=None,
                content_type="",
                bytes=0,
                reason=f"too many redirects: {e}",
                url=url,
            )
        except (
            httpx.ConnectError,
            httpx.HTTPStatusError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.TimeoutException,
        ) as e:
            return FetchResult(
                status="failed",
                content=None,
                extracted_markdown=None,
                content_type="",
                bytes=0,
                reason=f"{type(e).__name__}: {e}",
                url=url,
            )

        # 8. Extract to markdown via trafilatura
        try:
            content_str = raw.decode("utf-8", errors="replace")
        except Exception as e:
            return FetchResult(
                status="failed",
                content=None,
                extracted_markdown=None,
                content_type=ctype,
                bytes=total,
                reason=f"decode error: {e}",
                url=url,
            )
        markdown = trafilatura.extract(
            content_str,
            output_format="markdown",
            include_comments=False,
            no_fallback=True,
        )
        if markdown is None or not markdown.strip():
            # Fall back to raw-decoded text for non-HTML or extraction failures
            markdown = content_str

        # 9. Strip HTML comments defensively (trafilatura usually does, but fenced for safety)
        markdown = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)

        # 10. Secret scan on code-stripped view (preserve original markdown)
        leak = _secret_scan(markdown)
        if leak is not None:
            label, snippet = leak
            return FetchResult(
                status="blocked",
                content=None,
                extracted_markdown=None,
                content_type=ctype,
                bytes=total,
                reason=f"secret pattern detected: {label} (snippet: {snippet!r})",
                url=final_url,
            )

        return FetchResult(
            status="ok",
            content=content_str,
            extracted_markdown=markdown,
            content_type=ctype,
            bytes=total,
            reason=None,
            url=final_url,
        )
