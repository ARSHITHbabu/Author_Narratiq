"""
Built-in error tracking and live operational counters (Stage 10, task 10.2,
decision S10-C — no external error-tracking service).

Two parts:

1. Error records (`error_events`). Unhandled backend exceptions and frontend
   error reports are stored scrubbed and de-duplicated. What a record can hold
   is limited BY CONSTRUCTION, not by hoping callers are careful:
     * route = the route TEMPLATE ("/api/stories/{story_id}/…"), never a path;
     * stack = frame locations only ("file.py:120 in fn") — no source lines,
       no locals, no exception message inside the stack;
     * message = the exception message after scrub(): quoted text, emails,
       tokens, key=value secrets and ids removed, then capped at
       MESSAGE_MAX_WORDS words, so a manuscript sentence cannot be carried in;
     * no user id, no request body, no headers.
   Recording never raises: a failure to record is logged and dropped.

2. Rolling counters (process memory; D-3 single worker). Per-minute buckets
   over the last hour for requests, 5xx, AI-unavailable (503), truncated AI
   output (422 ai_response_truncated) and client errors. Parse/degraded
   outcomes come from services.ai_service.parser_metrics(). Exposed through
   /api/ops/metrics for the pod watchdog.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MESSAGE_MAX_WORDS = 12
MESSAGE_MAX_CHARS = 300
STACK_MAX_FRAMES = 25
STACK_MAX_CHARS = 4000
DEDUP_WINDOW = timedelta(hours=24)

_QUOTED = re.compile(r"""(['"“‘`])(?:(?!\1).){1,}?\1""", re.S)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*")
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")
_SECRET_KV = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie|session)\b\s*[:=]\s*\S+")
_URL_CRED = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b[0-9a-f]{24,}\b", re.I)


def scrub(text: str | None) -> str:
    """Remove anything that could be author content, personal data or a secret.
    Deliberately lossy: an error record needs the SHAPE of a failure, never
    its data."""
    if not text:
        return ""
    s = str(text)
    s = _URL_CRED.sub("://<credentials>@", s)
    s = _JWT.sub("<token>", s)
    s = _BEARER.sub("Bearer <token>", s)
    s = _SECRET_KV.sub(lambda m: f"{m.group(1)}=<redacted>", s)
    s = _EMAIL.sub("<email>", s)
    s = _QUOTED.sub("<text>", s)
    s = _UUID.sub("<id>", s)
    s = _HEX.sub("<hex>", s)
    s = " ".join(s.split())
    words = s.split(" ")
    if len(words) > MESSAGE_MAX_WORDS:
        s = " ".join(words[:MESSAGE_MAX_WORDS]) + " …[truncated]"
    return s[:MESSAGE_MAX_CHARS]


def stack_locations(exc: BaseException | None) -> str:
    """'path:line in function' per frame, innermost last. No source text, no
    message, no locals — only where the failure happened."""
    if exc is None or exc.__traceback__ is None:
        return ""
    frames = traceback.extract_tb(exc.__traceback__)[-STACK_MAX_FRAMES:]
    lines = []
    for f in frames:
        path = f.filename
        for marker in ("/backend/", "/site-packages/", "/dist-packages/"):
            if marker in path:
                path = path.split(marker, 1)[1]
                break
        lines.append(f"{path}:{f.lineno} in {f.name}")
    return "\n".join(lines)[-STACK_MAX_CHARS:]


def fingerprint(source: str, kind: str, route: str | None, anchor: str) -> str:
    return hashlib.sha256(f"{source}|{kind}|{route or ''}|{anchor}".encode()).hexdigest()


def record_event(*, source: str, kind: str, route: str | None = None, method: str | None = None,
                 status_code: int | None = None, request_id: str | None = None,
                 message: str | None = None, stack: str | None = None) -> bool:
    """Store (or count) one scrubbed error. Returns False — never raises — on failure."""
    from database import SessionLocal
    from models import ErrorEvent

    kind = scrub(kind)[:120] or "Error"
    route = (route or "")[:300] or None
    msg = scrub(message)
    stack = (stack or "")[-STACK_MAX_CHARS:] or None
    # Anchor on the innermost frame (or the message shape) so the same fault
    # from different requests lands on one row.
    anchor = stack.splitlines()[-1] if stack else msg
    fp = fingerprint(source, kind, route, anchor)
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        row = (db.query(ErrorEvent)
                 .filter(ErrorEvent.fingerprint == fp, ErrorEvent.last_seen >= now - DEDUP_WINDOW)
                 .order_by(ErrorEvent.last_seen.desc()).first())
        if row is not None:
            row.occurrences = (row.occurrences or 1) + 1
            row.last_seen = now
            row.request_id = request_id
            row.status_code = status_code
        else:
            db.add(ErrorEvent(source=source, kind=kind, route=route, method=method,
                              status_code=status_code, request_id=request_id, message=msg or None,
                              stack=stack, fingerprint=fp, first_seen=now, last_seen=now))
        db.commit()
        return True
    except Exception as exc:                          # noqa: BLE001 — tracking must never break a request
        db.rollback()
        logger.warning("[error_tracking] could not record an error event: %s", type(exc).__name__)
        return False
    finally:
        db.close()


def prune_events(retention_days: int, max_rows: int) -> int:
    """Drop records older than the retention window, then the oldest beyond
    the row cap. Returns rows removed. Never raises."""
    from database import SessionLocal
    from models import ErrorEvent

    db = SessionLocal()
    removed = 0
    try:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        removed += db.query(ErrorEvent).filter(ErrorEvent.last_seen < cutoff).delete(synchronize_session=False)
        total = db.query(ErrorEvent).count()
        if total > max_rows:
            old = (db.query(ErrorEvent.event_id).order_by(ErrorEvent.last_seen.asc())
                     .limit(total - max_rows).all())
            ids = [r.event_id for r in old]
            removed += db.query(ErrorEvent).filter(ErrorEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    except Exception as exc:                          # noqa: BLE001
        db.rollback()
        logger.warning("[error_tracking] prune failed: %s", type(exc).__name__)
    finally:
        db.close()
    return removed


# ── Rolling counters ─────────────────────────────────────────────────────────

COUNTERS = ("requests", "server_errors", "ai_unavailable", "ai_truncated", "client_errors")


class RollingCounters:
    """Per-minute buckets for the last `horizon_minutes` minutes."""

    def __init__(self, horizon_minutes: int = 60, clock=time.time):
        self.horizon = horizon_minutes
        self.clock = clock
        self._buckets: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._lock = threading.Lock()
        self.started_at = clock()

    def incr(self, name: str, n: int = 1) -> None:
        minute = int(self.clock() // 60)
        with self._lock:
            self._buckets[minute][name] += n
            floor = minute - self.horizon
            for m in [m for m in self._buckets if m <= floor]:
                del self._buckets[m]

    def window(self, minutes: int) -> dict[str, int]:
        now_minute = int(self.clock() // 60)
        out = {c: 0 for c in COUNTERS}
        with self._lock:
            for m, counts in self._buckets.items():
                if m > now_minute - minutes:
                    for k, v in counts.items():
                        out[k] = out.get(k, 0) + v
        return out


counters = RollingCounters()
