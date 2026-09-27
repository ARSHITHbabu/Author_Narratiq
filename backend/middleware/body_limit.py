"""
Streaming request-body cap for upload routes (Stage 9 security finding S1).

Why this exists: `enforce_upload_size()` in upload_guard.py runs inside the
route handler. For routes that declare `file: UploadFile = File(...)`, FastAPI
has already parsed — and spooled to disk — the whole multipart body before the
handler runs, and a chunked request carries no Content-Length at all. So the
"reject before reading" promise did not hold.

This pure-ASGI middleware enforces the same configured limits at the transport
layer, before any route code or multipart parsing sees the body:

  * declared Content-Length above the limit → 413 at once, body never read;
  * otherwise the body is counted as it streams in, and the moment the running
    total passes the limit the request is cut off and answered with 413.

The 413 body matches the global UploadTooLargeError handler in main.py, so the
frontend shows the same author-facing message either way. The per-route checks
stay in place as defence in depth.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Iterable

from exceptions import UploadTooLargeError

logger = logging.getLogger(__name__)


class _BodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app, rules: Iterable[tuple[str, str, Callable[[], int]]]):
        """rules: (METHOD, path regex, callable returning the limit in MB).
        The limit is read per request so settings overrides in tests apply."""
        self.app = app
        self.rules = [(m.upper(), re.compile(p), f) for m, p, f in rules]

    def _limit_mb(self, method: str, path: str) -> int | None:
        for m, rx, f in self.rules:
            if m == method and rx.fullmatch(path):
                return int(f())
        return None

    @staticmethod
    async def _send_413(send, limit_mb: int) -> None:
        body = json.dumps({
            "error": "upload_too_large",
            "message": UploadTooLargeError(limit_mb=limit_mb).message,
        }).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit_mb = self._limit_mb(scope.get("method", ""), scope.get("path", ""))
        if limit_mb is None:
            return await self.app(scope, receive, send)

        limit_bytes = limit_mb * 1024 * 1024
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit_bytes:
                    logger.warning("[upload_limit] rejected by Content-Length path=%s limit_mb=%d",
                                   scope.get("path"), limit_mb)
                    return await self._send_413(send, limit_mb)
            except ValueError:
                pass  # malformed header: fall through to streaming count

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive():
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit_bytes:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal response_started
            if exceeded:
                return  # whatever the app answers, the author gets the 413
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        except Exception:
            if not exceeded:
                raise
        if exceeded and not response_started:
            logger.warning("[upload_limit] rejected while streaming path=%s limit_mb=%d",
                           scope.get("path"), limit_mb)
            await self._send_413(send, limit_mb)
