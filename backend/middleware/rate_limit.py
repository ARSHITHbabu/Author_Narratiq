"""
Rate limiting middleware for NarratIQ AI.

Uses slowapi (a FastAPI-native wrapper around the `limits` library).
Default backend: in-memory (single-process). Redis-upgradeable by setting
SLOWAPI_STORAGE_URI=redis://... without any code changes.

Two key functions:
  get_remote_address  — used for auth endpoints (per-IP brute-force protection)
  get_user_id         — used for all authenticated endpoints (per-user AI budget)

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

import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_user_id(request: Request) -> str:
    """
    Per-user rate limit key for authenticated endpoints.
    Extracts the JWT `sub` claim (user_id) from the Authorization header.
    Falls back to the client IP address if the token is absent or invalid
    (the auth dependency will reject the request anyway, so this path is safe).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
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
