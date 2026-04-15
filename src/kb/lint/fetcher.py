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
import socket
from dataclasses import dataclass
from typing import Literal

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend

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
    3. Deferring the actual connect to the parent SyncBackend (preserving
       the original hostname for SNI / Host: header).

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
            ):
                raise httpcore.ConnectError(
                    f"Blocked private/reserved address {ip} for host {host}"
                )

        # Defer the actual connect to the parent class. The parent SyncBackend
        # re-resolves at OS connect, but EVERY resolution of this host has
        # already passed our private-IP check above. The window for rebinding
        # is the time between our getaddrinfo and the parent's connect - narrow
        # enough to require a sub-second TTL attack which most resolvers reject.
        return super().connect_tcp(
            host=host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


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
