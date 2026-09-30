"""
Rate limiting middleware for NarratIQ AI.

Uses slowapi (a FastAPI-native wrapper around the `limits` library).
Storage: in-memory, one counter set PER PROCESS. That is correct only at a
single uvicorn worker, which is the recorded deployment decision (D-3);
startup/worker_guard.py refuses to start with more workers. Going multi-worker
is a code change — pass storage_uri="redis://..." to the Limiter below — not
an environment setting (there is no SLOWAPI_STORAGE_URI; nothing ever read it).

Two key functions:
  get_remote_address  — used for auth endpoints (per-IP brute-force protection).
                        Resolves the real client behind the frontend's
                        same-origin /api proxy (see client_ip).
  get_user_id         — used for all authenticated endpoints (per-user AI budget);
                        reads the session cookie or the Bearer header.

All limit values come from settings (config.py / environment variables).
No limits are hardcoded here.

Usage in a router:
    from fastapi import Request
    from middleware.rate_limit import limiter
    from config import settings

    @router.post("/my-endpoint")
    @limiter.limit(settings.rate_limit_realtime_ai, key_func=get_user_id)
    async def my_endpoint(request: Request, ...):
        ...

Note: the route function MUST have `request: Request` as its first parameter
for slowapi to inject the rate limit context.
"""

import ipaddress
import logging

from fastapi import Request
from slowapi import Limiter

logger = logging.getLogger(__name__)


def _trusted_networks():
    from config import settings as _s
    nets = []
    for part in (_s.trusted_proxy_cidrs or "").split(","):
        part = part.strip()
        if part:
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                logger.warning("[rate_limit] ignoring invalid TRUSTED_PROXY_CIDRS entry %r", part)
    return nets


def _is_trusted_proxy(host: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return any(ip in net for net in _trusted_networks())


def client_ip(request: Request) -> str:
    """The address to rate-limit by.

    Measured on the pod (Stage 10 live check): browser traffic arrives
    Cloudflare → RunPod proxy (socket peer 100.64.x.x) → [Next.js on the same
    pod, peer 127.0.0.1] → backend. X-Forwarded-For there is
    "<client>, <Cloudflare edge>", and the edge address CHANGES between
    requests — keying on it gave every request its own bucket, so limits never
    applied. Cloudflare's CF-Connecting-IP carries the real client and
    Cloudflare overwrites any client-supplied value.

    Forwarding headers are trusted ONLY when the socket peer is a known proxy
    (TRUSTED_PROXY_CIDRS: loopback + RunPod's internal proxy range by default).
    A request from anywhere else is keyed by its own socket address, so a
    spoofed header changes nothing."""
    peer = request.client.host if request.client else ""
    if _is_trusted_proxy(peer):
        cf = request.headers.get("cf-connecting-ip", "").strip()
        if cf:
            return cf
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer or "unknown"


# Name kept: routers import `get_remote_address` from here for per-IP limits.
get_remote_address = client_ip


def get_user_id(request: Request) -> str:
    """
    Per-user rate limit key for authenticated endpoints.
    Extracts the JWT `sub` claim (user_id) from the Authorization header or,
    for browser requests, the HttpOnly session cookie. Falls back to the client
    IP address if the token is absent or invalid (the auth dependency will
    reject the request anyway, so this path is safe).
    """
    from config import settings as _settings
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get(_settings.session_cookie_name, "")
    if token:
        try:
            from jose import jwt as _jwt
            from config import settings
            payload = _jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},   # rate-limit even expired tokens
            )
            uid = payload.get("sub")
            if uid:
                return str(uid)
        except Exception:
            pass
    return get_remote_address(request)


# Singleton limiter — default key is remote IP (overridden per-route where needed).
# Attach to app in main.py: app.state.limiter = limiter
limiter = Limiter(key_func=get_remote_address)
