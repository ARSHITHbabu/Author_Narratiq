"""
PinContentStore — the ONLY code that reads or writes pin content
(Phase 3 spec §11.3; definition of done §46 item 10: "No SQL reads
ai_generation_pins.content outside PinContentStore").

Routers and services never touch AiGenerationPin.content directly; they call
get_pin_store().get(pin) / .put(pin, text). That single seam is what lets pin
content move to object storage later (spec §14, triggers §16.3) as a config
change plus a backfill, with no router, schema or API change.

Only the "db" backend exists. Unknown backends fail fast when the store is
first requested, not silently at the first pin write.
"""
from __future__ import annotations

import hashlib
from typing import Protocol, Sequence


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class PinContentStore(Protocol):
    def put(self, pin, content: str) -> None: ...
    def get(self, pin) -> str: ...
    def delete_many(self, pins: Sequence) -> int: ...


class DbPinStore:
    """Phase 3 default. Content lives inline in ai_generation_pins.content."""

    name = "db"

    def put(self, pin, content: str) -> None:
        pin.content = content
        pin.content_uri = None
        pin.content_sha256 = sha256_text(content)
        pin.content_bytes = len(content.encode("utf-8"))
        pin.word_count = len(content.split())

    def get(self, pin) -> str:
        return pin.content or ""

    def delete_many(self, pins: Sequence) -> int:
        # Rows are deleted by the caller's session; inline content goes with
        # them. An object backend would delete its blobs here.
        return len(pins)


_SUPPORTED = {"db": DbPinStore}
_store: PinContentStore | None = None


def get_pin_store() -> PinContentStore:
    """Lazy module singleton (same pattern as middleware/concurrency.py)."""
    global _store
    if _store is None:
        from config import settings
        backend = settings.pin_storage_backend
        if backend not in _SUPPORTED:
            raise RuntimeError(
                f"PIN_STORAGE_BACKEND={backend!r} is not implemented. "
                f"Supported: {', '.join(sorted(_SUPPORTED))}. "
                "The object-storage backend is specified (Phase 3 spec §14) but deferred."
            )
        _store = _SUPPORTED[backend]()
    return _store
