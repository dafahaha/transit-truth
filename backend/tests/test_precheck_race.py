"""R15 regression: dual-stack dead-port latency must not be N×per-try timeout.

Previously ``_precheck_tcp_reachable`` raced each resolved IP *serially*: on a
dual-stack host IPv6 (4s timeout) then IPv4 (4s timeout) summed to ~8s, and a
public dead port measured ~11s. Now all resolved IPs are raced concurrently, so
wall-clock is capped by a single per-try timeout.
"""

from __future__ import annotations

import asyncio
import socket
import time

import pytest

from app.verify.core import _precheck_tcp_reachable


class _FakeWriter:
    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def _install_two_ips(monkeypatch: pytest.MonkeyPatch, port: int = 443) -> None:
    """Make DNS return one IPv4 and one IPv6 address."""
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(host, _port, proto=0):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.10", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("2001:db8::1", port)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.asyncio
async def test_two_dead_ips_cost_one_timeout_not_two(monkeypatch):
    _install_two_ips(monkeypatch)

    async def hanging_open(host, _port):
        # Longer than the 4s wait_for, so each attempt times out.
        await asyncio.sleep(30)
        raise RuntimeError("unreachable")

    monkeypatch.setattr(asyncio, "open_connection", hanging_open)

    started = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await _precheck_tcp_reachable("example.com", 443, allow_local=True)
    elapsed = time.monotonic() - started

    # Serial would have cost ~8s; racing must cost ~4s.
    assert elapsed < 6.0, f"precheck still serial? elapsed={elapsed:.1f}s"
    assert elapsed > 3.0, f"precheck returned too fast: {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_first_success_returns_and_others_cancelled(monkeypatch):
    _install_two_ips(monkeypatch)
    cancelled: list[str] = []

    async def fake_open(host, _port):
        if host == "203.0.113.10":  # first resolved IP succeeds immediately
            return (None, _FakeWriter())
        try:
            await asyncio.sleep(30)  # second IP would hang
        except asyncio.CancelledError:
            cancelled.append(host)
            raise
        return (None, _FakeWriter())

    monkeypatch.setattr(asyncio, "open_connection", fake_open)

    started = time.monotonic()
    await _precheck_tcp_reachable("example.com", 443, allow_local=True)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"did not return on first success: {elapsed:.1f}s"
    assert cancelled == ["2001:db8::1"], f"pending IP not cancelled: {cancelled}"
