"""
Structured logging configuration for NarratIQ AI.

Call setup_logging() once from main.py at module import time.
All other modules use:  logger = logging.getLogger(__name__)

Log format is controlled by the LOG_FORMAT env var:
  text  → human-readable (default, dev-friendly)
  json  → machine-readable (production, log aggregators)

Log level is controlled by the LOG_LEVEL env var (default: INFO).

Privacy rules enforced in all log calls:
  - Never log JWT tokens, SECRET_KEY, or passwords
  - Never log chapter content, character backstories, or raw_transcript (author data)
  - IDs are truncated to first 8 chars in log messages
"""

import json
import logging
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level":   record.levelname,
            "module":  record.name,
            "event":   record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """
    Configure the root logger. Call once from main.py before any import
    that might log (to ensure no double-handler from uvicorn's default setup).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any handlers uvicorn or the test runner may have added
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if fmt.lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Silence noisy third-party loggers that are not useful in production
    for noisy in ("uvicorn.access", "httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
