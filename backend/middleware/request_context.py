"""
Request id + response counting (Stage 10, task 10.2).

Pure ASGI. For every HTTP request it:
  * assigns a request id (a sane incoming X-Request-ID is kept, otherwise a
    fresh one), exposes it to log records through a context variable and
    returns it in the X-Request-ID response header, so an author-reported
    failure can be matched to its log lines and error record;
  * counts the response into services.error_tracking.counters (requests,
    5xx, AI-unavailable 503s, truncated-AI 422s).

It reads no bodies and records no paths — only status codes.
"""
from __future__ import annotations

import contextvars
import logging
import re
import uuid

from services.error_tracking import counters

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_SANE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdLogFilter(logging.Filter):
    """Adds `request_id` to every log record (JSON formatter emits it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _SANE_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        scope.setdefault("state", {})["request_id"] = rid
        status_holder = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            code = status_holder["code"]
            path = scope.get("path", "")
            if path.startswith("/api/") and path != "/api/health":
                counters.incr("requests")
                if code >= 500:
                    counters.incr("server_errors")
                # ai_unavailable / ai_truncated are counted by their exception
                # handlers in main.py, where the cause is known exactly.
            request_id_var.reset(token)
