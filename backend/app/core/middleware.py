"""Bound request bodies and attach non-sensitive request diagnostics/security headers."""

import logging
import time
import uuid

from starlette.responses import JSONResponse

logger = logging.getLogger("trackonomics.requests")


class RequestGuard:
    def __init__(self, app, max_bytes: int = 8192):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        status = 500

        async def secured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        async def reject(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, secured_send)

        if scope["method"] in {"POST", "PUT", "PATCH"}:
            headers = dict(scope.get("headers", []))
            try:
                declared = int(headers.get(b"content-length", b"0"))
                if declared < 0:
                    raise ValueError
            except ValueError:
                await reject(400, "Invalid Content-Length")
                return
            if declared > self.max_bytes:
                await reject(413, "Request body too large")
                return
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_bytes:
                    await reject(413, "Request body too large")
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            receiver = replay
        else:
            receiver = receive
        try:
            await self.app(scope, receiver, secured_send)
        finally:
            # Deliberately omit query strings, headers, bodies and credentials.
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id,
                scope["method"],
                scope["path"],
                status,
                (time.monotonic() - started) * 1000,
            )
