"""
CSRF protection for cookie-authenticated requests (Stage 10, task 10.7).

With the session in a cookie, the browser attaches it automatically — so a
state-changing request must also prove it came from NarratIQ's own pages.
Double-submit token: the backend sets a readable `narratiq_csrf` cookie at
sign-in; the frontend copies it into the `X-CSRF-Token` header. Another site
can make the browser send the cookie but cannot read it, so it cannot produce
the matching header. SameSite=Lax on both cookies is a second layer; an Origin
check is a third.

Enforced only when the request is cookie-authenticated:
  * a request with an Authorization header is not ambient (a browser never
    adds one on its own), so it is not checked;
  * a request with no session cookie has no session to abuse.

Pure ASGI (no BaseHTTPMiddleware), so streaming and upload bodies pass through
untouched.
"""
from __future__ import annotations

import hmac
import json
import re
from http.cookies import SimpleCookie
from typing import Callable, Iterable

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

# Sign-in creates the session, so it cannot carry a token yet. Sign-out must
# ALWAYS work, even for a browser that lost its CSRF cookie; the worst a forged
# sign-out can do is end a session (and SameSite=Lax already keeps the cookie
# off cross-site POSTs). Client error reports carry no authority (they only
# record a scrubbed error).
_EXEMPT = {"/api/auth/login", "/api/auth/register", "/api/auth/logout", "/api/client-errors"}


def _refuse(message: str):
    body = json.dumps({"error": "csrf_failed", "message": message, "detail": message}).encode()
    return [
        {"type": "http.response.start", "status": 403,
         "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]},
        {"type": "http.response.body", "body": body},
    ]


class CSRFMiddleware:
    def __init__(self, app, *, session_cookie: str, csrf_cookie: str, header_name: str,
                 allowed_origins: Callable[[], Iterable[str]], allowed_origin_regex: Callable[[], str | None]):
        self.app = app
        self.session_cookie = session_cookie
        self.csrf_cookie = csrf_cookie
        self.header = header_name.lower().encode()
        self.allowed_origins = allowed_origins
        self.allowed_origin_regex = allowed_origin_regex

    def _origin_ok(self, origin: str) -> bool:
        if origin in set(self.allowed_origins()):
            return True
        rx = self.allowed_origin_regex()
        return bool(rx and re.fullmatch(rx, origin))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in _UNSAFE:
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not path.startswith("/api/") or path.rstrip("/") in _EXEMPT:
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if b"authorization" in headers:
            return await self.app(scope, receive, send)
        jar = SimpleCookie()
        try:
            jar.load(headers.get(b"cookie", b"").decode("latin-1"))
        except Exception:                                   # noqa: BLE001 — malformed cookie header
            jar = SimpleCookie()
        if self.session_cookie not in jar:
            return await self.app(scope, receive, send)

        origin = headers.get(b"origin", b"").decode("latin-1")
        if origin and origin != "null" and not self._origin_ok(origin):
            for msg in _refuse("This request did not come from NarratIQ, so it was blocked. "
                               "Nothing was changed."):
                await send(msg)
            return

        sent = headers.get(self.header, b"").decode("latin-1")
        expected = jar[self.csrf_cookie].value if self.csrf_cookie in jar else ""
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            for msg in _refuse("Your session's security check did not match, so nothing was changed. "
                               "Reload the page and try again."):
                await send(msg)
            return
        return await self.app(scope, receive, send)
