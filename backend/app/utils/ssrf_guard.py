"""SSRF guard for outbound requests initiated by the API.

Every server-side outbound request targets a caller-supplied ``base_url``.
Without restrictions an attacker could point the server at internal services
(cloud metadata at 169.254.169.254, loopback admin ports, RFC1918 hosts).
This module enforces, before any request is sent:

* only ``http``/``https`` schemes;
* the host must not be (or resolve to) a loopback / private / link-local /
  reserved / unspecified address. DNS is resolved here so that hostnames
  pointing at internal IPs (a common DNS-rebinding / name-based bypass) are
  blocked too.

Error messages are intentionally generic: they never leak the resolved
internal address back to the caller.
"""
import ipaddress
import logging
import socket

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is an address we must never proxy to."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> fail closed
    return (
        ip.is_loopback        # 127.0.0.0/8, ::1
        or ip.is_private      # 10/8, 172.16/12, 192.168/16, fc00::/7, ...
        or ip.is_link_local   # 169.254.0.0/16, fe80::/10
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified  # 0.0.0.0, ::
    )


def validate_public_url(url: str) -> httpx.URL:
    """Parse *url*, enforce http(s) and a public target.

    Raises ``ValueError`` with a generic, safe message on any violation.
    The caller is responsible for turning that into an HTTP 400.
    """
    try:
        parsed = httpx.URL(url)
    except Exception as exc:  # malformed URL
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("Only http:// and https:// URLs are allowed")

    host = parsed.host
    if not host:
        raise ValueError("URL must include a host")

    # Resolve the hostname and check every A/AAAA record. This blocks both
    # raw internal IP literals and hostnames that resolve to internal IPs.
    try:
        addr_infos = socket.getaddrinfo(host, parsed.port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise ValueError("Unable to resolve URL host") from exc

    for info in addr_infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            logger.warning("Blocked outbound request to host=%s (resolves to %s)", host, ip_str)
            raise ValueError("Target is not a public internet address")

    return parsed


def require_public_url(url: str) -> httpx.URL:
    """validate_public_url, raising HTTP 400 on violation (FastAPI helper)."""
    try:
        return validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
