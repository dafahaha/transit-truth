"""P2-1 regression: the verify serve app enforces the shared 1 MiB body cap.

``build_serve_app`` previously had NO request-body size limit: ``/api/verify``
called ``await request.json()`` and buffered whatever the caller sent. On a
public bind (``--allow-public``) an anonymous client could POST a multi-MB JSON
blob to exhaust memory. The shared ``RequestBodyLimitMiddleware`` (declared
Content-Length fast path + chunked streaming guard) is now mounted on the serve
app too; over-cap bodies return 413 before pydantic reads them.

These tests drive the app directly as ASGI so they can feed chunked bodies with
no Content-Length, which the TestClient JSON helper hides.
"""

from __future__ import annotations

import asyncio

from app.utils.body_limit import MAX_BODY_BYTES
from app.verify.serve import build_serve_app

MB = 1024 * 1024


def _drive_serve_asgi(chunks, headers):
    """Drive ``build_serve_app(loopback_only=False)`` as ASGI.

    Feeds *chunks* as ``http.request`` events; no Content-Length is emitted
    unless the caller passes one. Returns ``(status_code, raw_body_bytes)``.
    loopback_only=False because the synthetic peer/Host is not a loopback
    literal; the Host whitelist itself is covered by test_serve.py.
    """
    app = build_serve_app(allow_local=False, loopback_only=False)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/verify",
        "raw_path": b"/api/verify",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": ("203.0.113.9", 50000),
        "server": ("testserver", 80),
    }
    state = {"i": 0}

    async def receive():
        i = state["i"]
        if i < len(chunks):
            state["i"] += 1
            more_body = i < len(chunks) - 1
            return {"type": "http.request", "body": chunks[i], "more_body": more_body}
        return {"type": "http.disconnect"}

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    status = messages[0]["status"]
    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, body


def test_serve_declared_content_length_over_limit_is_413():
    # Fast path: a declared over-cap Content-Length is rejected without reading
    # the body.
    payload = b"{}".ljust(2 * MB, b"x")
    status, _ = _drive_serve_asgi(
        [payload],
        [
            ("content-type", "application/json"),
            ("content-length", str(len(payload))),
        ],
    )
    assert status == 413, f"expected 413 for over-limit Content-Length, got {status}"


def test_serve_chunked_body_without_content_length_is_413():
    # Streaming path: Transfer-Encoding: chunked with NO Content-Length must
    # abort at 1 MiB with 413 (not buffer 2 MiB and return 400/422).
    status, _ = _drive_serve_asgi(
        [b" " * MB, b" " * MB],  # ~2 MiB streamed in two chunks, no CL header
        [("content-type", "application/json")],
    )
    assert status == 413, f"expected 413 for chunked upload, got {status}"


def test_serve_exactly_one_mib_body_is_not_413():
    # Boundary: the cap is inclusive on 1 MiB. Exactly 1 MiB must reach the
    # endpoint (here rejected as invalid JSON -> 400), never be turned away as
    # over-size.
    status, _ = _drive_serve_asgi(
        [b"x" * MAX_BODY_BYTES],  # exactly the cap, not valid JSON
        [("content-type", "application/json")],
    )
    assert status != 413, "exactly 1 MiB must not be treated as over-limit"
    assert status == 400, f"expected invalid_json 400, got {status}"


def test_serve_small_request_is_not_413():
    # The streaming wrapper must not break normal small requests: a valid-size
    # malformed payload reaches the endpoint's own validation (missing_field).
    payload = b'{"base_url":"https://example.com/v1"}'
    status, _ = _drive_serve_asgi(
        [payload],
        [
            ("content-type", "application/json"),
            ("content-length", str(len(payload))),
        ],
    )
    assert status != 413, "small valid-size request must not be body-limited"
    assert status == 400, f"expected missing_field 400, got {status}"


def test_serve_over_limit_cl_rejects_without_reading_body():
    # P3-1: the Content-Length fast path must short-circuit and return 413
    # without invoking the ASGI receive channel at all. A receive that fails
    # loudly proves the body was never read; flipping the fast path to
    # `if False:` makes this test raise (so the branch is pinned).
    app = build_serve_app(allow_local=False, loopback_only=False)
    declared = 2 * MB
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/verify",
        "raw_path": b"/api/verify",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(declared).encode()),
        ],
        "client": ("203.0.113.9", 50000),
        "server": ("testserver", 80),
    }

    async def receive_should_never_be_called():
        raise AssertionError("fast path must not read the request body")

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive_should_never_be_called, send))
    assert messages[0]["status"] == 413
