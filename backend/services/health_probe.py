"""
Live dependency probe for /api/health (Stage 10, task 10.2).

Before Stage 10, `/api/health` reported the vLLM state recorded ONCE at
startup: if vLLM died later, health still said "ready" (degraded mode —
every AI call returning 503 — was invisible), and if vLLM came up after the
backend, health said "unavailable" until a backend restart.

The probe calls vLLM's own /health with a short timeout and caches the answer
for `vllm_probe_ttl_seconds`, so frequent health polling never turns into
load on vLLM. It never raises.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from config import settings

_cache: dict = {"at": 0.0, "ok": None}
_lock = asyncio.Lock()


async def vllm_ready(force: bool = False) -> bool:
    now = time.monotonic()
    if not force and _cache["ok"] is not None and now - _cache["at"] < settings.vllm_probe_ttl_seconds:
        return _cache["ok"]
    async with _lock:
        now = time.monotonic()
        if not force and _cache["ok"] is not None and now - _cache["at"] < settings.vllm_probe_ttl_seconds:
            return _cache["ok"]
        try:
            async with httpx.AsyncClient(timeout=settings.vllm_probe_timeout_seconds) as client:
                r = await client.get(settings.vllm_health_url)
                ok = r.status_code == 200
        except Exception:                               # noqa: BLE001 — unreachable is an answer, not an error
            ok = False
        _cache.update(at=time.monotonic(), ok=ok)
        return ok


def reset_cache() -> None:
    _cache.update(at=0.0, ok=None)
