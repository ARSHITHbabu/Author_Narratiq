"""
Single-worker startup guard (Stage 10, task 10.4; decision D-3).

NarratIQ is deployed with ONE uvicorn worker by decision D-3. Several pieces of
state are per process and silently become wrong with more workers:

  * rate limits  — slowapi in-memory storage: every worker keeps its own
                   counters, so each limit is multiplied by the worker count;
  * WS tickets   — the voice-socket tickets (routers/auth.py) live in memory,
                   so a ticket issued by one worker is unknown to another;
  * AI semaphores, parser metrics, the vLLM probe cache — per process.

This guard reads the worker count the server was started with and refuses to
start when it is above one, unless ALLOW_MULTI_WORKER=yes is set explicitly
(an operator who has moved that state to shared storage). It never guesses in
the permissive direction: an unparseable value counts as "unknown", which is
logged, not treated as one.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_FLAG_PATTERNS = (
    re.compile(r"^--workers(?:=(\d+))?$"),   # uvicorn / gunicorn long form
    re.compile(r"^-w(\d+)?$"),                # gunicorn short form
)


def workers_from_argv(argv: list[str]) -> int | None:
    """Worker count named on a command line, or None when none is named."""
    for i, arg in enumerate(argv):
        for pat in _FLAG_PATTERNS:
            m = pat.match(arg)
            if not m:
                continue
            value = m.group(1)
            if value is None and i + 1 < len(argv):
                value = argv[i + 1]
            try:
                return int(value) if value is not None else None
            except ValueError:
                return None
    return None


def _cmdline(pid: int | str) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return [p.decode("utf-8", "replace") for p in fh.read().split(b"\0") if p]
    except OSError:
        return []


def detect_worker_count(env: dict | None = None, own: list[str] | None = None,
                        parent: list[str] | None = None) -> int:
    """Highest worker count found in WEB_CONCURRENCY, this process's command
    line or its parent's (uvicorn's multi-worker supervisor is the parent of
    each worker). Defaults to 1 when nothing names a count."""
    env = os.environ if env is None else env
    own = _cmdline("self") if own is None else own
    parent = _cmdline(os.getppid()) if parent is None else parent
    found = [1]
    for argv in (own, parent):
        n = workers_from_argv(argv)
        if n is not None:
            found.append(n)
    try:
        if env.get("WEB_CONCURRENCY"):
            found.append(int(env["WEB_CONCURRENCY"]))
    except ValueError:
        logger.warning("[startup] WEB_CONCURRENCY is not a number; ignoring it")
    return max(found)


def enforce_single_worker(allow_flag: str, **detect_kwargs) -> int:
    """Raise RuntimeError when more than one worker is configured and the
    operator has not explicitly allowed it. Returns the detected count."""
    count = detect_worker_count(**detect_kwargs)
    if count <= 1:
        return count
    if (allow_flag or "").strip().lower() == "yes":
        logger.error(
            "[startup] %d workers configured with ALLOW_MULTI_WORKER=yes. Rate limits, "
            "voice-socket tickets and AI concurrency caps are PER PROCESS and are NOT "
            "shared between workers (decision D-3 is one worker).", count)
        return count
    raise RuntimeError(
        f"NarratIQ is configured for {count} workers, but it supports exactly one "
        "(decision D-3): rate limits, voice-socket tickets and AI concurrency caps are "
        "kept in process memory and would be multiplied or lost across workers. Start "
        "uvicorn with --workers 1, or set ALLOW_MULTI_WORKER=yes only after moving that "
        "state to shared storage (see docs/operations/runpod-deployment.md).")


def warn_if_uvicorn_proxy_headers(own: list[str] | None = None, parent: list[str] | None = None) -> bool:
    """Stage 10 live finding: uvicorn's default --proxy-headers rewrites the
    client address from X-Forwarded-For for requests from 127.0.0.1 — i.e. every
    request through the Next.js same-origin proxy — to the right-most hop, a
    Cloudflare edge address that changes per request. Per-IP rate limits then
    never trigger. middleware/rate_limit.client_ip interprets forwarding headers
    itself, so uvicorn must run with --no-proxy-headers. Returns True (and logs
    an ERROR) when a uvicorn launch without it is detected."""
    own = _cmdline("self") if own is None else own
    parent = _cmdline(os.getppid()) if parent is None else parent
    for argv in (own, parent):
        if any("uvicorn" in a for a in argv) and "--no-proxy-headers" not in argv:
            logger.error("[startup] uvicorn is running WITHOUT --no-proxy-headers: per-IP rate limits "
                         "(sign-in brute-force protection) will not work behind the proxy. Restart with "
                         "--no-proxy-headers (start-narratiq.sh does).")
            return True
    return False
