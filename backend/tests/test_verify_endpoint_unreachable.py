"""F3 regression: a base-url whose port accepts nobody must fail FAST.

Before the reachability precheck, 17 probes each burned their retry/backoff
against a refused connection until the 90s total_timeout expired, and the run
was then mislabelled ``battery_timeout`` -- slow AND a wrong diagnosis. Now
``verify_endpoint`` opens a bare TCP connection (~5s budget) before the battery
and returns ``endpoint_unreachable`` immediately.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time

import pytest

from app.verify import verify_endpoint


def _free_loopback_port() -> int:
    """Bind 127.0.0.1:0, read the port, and CLOSE it (nothing listens)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_dead_port_returns_endpoint_unreachable_quickly():
    port = _free_loopback_port()
    url = f"http://127.0.0.1:{port}/v1"

    started = time.monotonic()
    report = await asyncio.wait_for(
        verify_endpoint(
            base_url=url,
            claimed_model="qwen2.5-0.5b-instruct",
            api_key="sk-test",
            allow_local=True,
        ),
        timeout=30,
    )
    elapsed = time.monotonic() - started

    err = report.get("error") or {}
    assert err.get("code") == "endpoint_unreachable", json.dumps(report, indent=2)
    assert err.get("code") != "battery_timeout"
    # Connection-refused on loopback returns in ~ms; even worst-case precheck
    # timeout (5s) must stay well under the old 90s battery_timeout.
    assert elapsed < 15.0, f"precheck did not fast-fail: {elapsed:.1f}s"
    assert "Could not connect" in err.get("message", "")


@pytest.mark.asyncio
async def test_reachable_port_still_proceeds_to_battery():
    """Sanity: the precheck must not reject a port that DOES listen.

    Bind a real (if useless) TCP listener and assert we do NOT get
    endpoint_unreachable -- the run must proceed into the battery (whose
    failure mode here is no_observations, not a precheck refusal).
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.listen(1)

    try:
        report = await asyncio.wait_for(
            verify_endpoint(
                base_url=f"http://127.0.0.1:{port}/v1",
                claimed_model="qwen2.5-0.5b-instruct",
                api_key="sk-test",
                allow_local=True,
                total_timeout=15.0,
            ),
            timeout=40,
        )
    finally:
        listener.close()

    err = report.get("error") or {}
    assert err.get("code") != "endpoint_unreachable", (
        "a listening port must pass the precheck"
    )
