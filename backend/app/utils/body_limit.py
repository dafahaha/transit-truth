"""Hard request-body size cap shared by every HTTP entry point.

Both the legacy ``app.main`` audit platform and the local ``verify`` serve app
must reject oversized bodies before they are buffered into memory. A declared
``Content-Length`` over the cap is rejected on the fast path without reading a
single byte; a chunked request (``Transfer-Encoding: chunked``, no
``Content-Length``) is counted while streaming and aborted the moment the
cumulative body exceeds the cap. Over-cap requests get a clean ``413`` instead
of being fully buffered and then rejected as malformed JSON (``422``).
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

# Hard cap on request body size (N3 / R3-1). 1 MiB is far above any legitimate
# audit / verify payload. The cap is *inclusive*: exactly 1 MiB is accepted,
# anything larger (>= 1 MiB + 1 byte) is rejected with 413.
MAX_BODY_BYTES = 1 * 1024 * 1024


class _RequestBodyTooLarge(Exception):
    """Internal signal raised by the counting receive once the body exceeds the cap."""


class RequestBodyLimitMiddleware:
    """ASGI middleware enforcing a hard request-body cap.

    The previous implementation only inspected the ``Content-Length`` header,
    so a chunked request (``Transfer-Encoding: chunked``, no ``Content-Length``)
    bypassed the cap entirely: uvicorn streamed the body and FastAPI buffered the
    whole thing into memory before pydantic validation (a single 2 MB chunked
    upload returned 422, not 413). We now wrap the ASGI ``receive`` channel and
    count bytes across every ``http.request`` chunk (honouring ``more_body``),
    aborting the moment the cumulative body exceeds the cap. Both the declared
    ``Content-Length`` path (rejected without reading) and the chunked path
    (counted while streaming) are covered.
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _too_large() -> JSONResponse:
        return JSONResponse(
            status_code=413, content={"detail": "Request body too large"}
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: a declared, over-cap length lets us reject without reading
        # a single byte of the body.
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    await self._too_large()(scope, receive, send)
                    return
            except ValueError:
                pass  # malformed length header; the streaming guard below still applies

        received = 0
        over = False

        async def limited_receive():
            nonlocal received, over
            event = await receive()
            if event["type"] == "http.request":
                chunk = event.get("body", b"") or b""
                received += len(chunk)
                if received > MAX_BODY_BYTES:
                    # Stop before this chunk reaches downstream: abort the body
                    # read. We can't let the exception propagate as-is — FastAPI
                    # turns any body-read error into a generic 400 — so we flag
                    # the overflow, swallow whatever response downstream then
                    # emits, and send our own authoritative 413 below. At most
                    # ~MAX_BODY_BYTES (+ one TCP chunk) ever lands in memory.
                    over = True
                    raise _RequestBodyTooLarge()
            return event

        async def limited_send(message):
            # Once the body overflowed, downstream will produce an error
            # response (a 400 from FastAPI's body parser); drop it entirely so
            # we can reply with a clean 413 instead.
            if over:
                return
            await send(message)

        await self.app(scope, limited_receive, limited_send)
        if over:
            await self._too_large()(scope, receive, send)
