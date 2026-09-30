"""
Which browser origins are NarratIQ's own pages (Stage 9 S2; Stage 10 10.7).

One definition, used by CORS (main.py), the CSRF check (middleware/csrf.py)
and the voice WebSocket handshake (routers/voice_agent.py).
"""
from __future__ import annotations

import os
import re

from config import settings


def runpod_origin_regex() -> str | None:
    """Stage 9 (S2): trust only THIS pod's proxy hosts, not every RunPod pod.
    Previously `https://.*\\.proxy\\.runpod\\.net` admitted any tenant's pod."""
    pod_id = (os.environ.get("RUNPOD_POD_ID") or "").strip()
    if not pod_id or pod_id == "local":
        return None
    return rf"https://{re.escape(pod_id)}-\d+\.proxy\.runpod\.net"


def origin_allowed(origin: str) -> bool:
    if origin in settings.cors_origins:
        return True
    rx = runpod_origin_regex()
    return bool(rx and re.fullmatch(rx, origin))
