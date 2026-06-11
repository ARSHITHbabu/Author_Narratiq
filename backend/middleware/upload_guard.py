"""
Upload size guard for NarratIQ AI.

Provides a single enforce_upload_size() function that checks the
Content-Length header BEFORE the request body is read into memory.
If the declared size exceeds the configured limit, UploadTooLargeError
is raised immediately, preventing large malicious uploads from exhausting
server RAM.

A second byte-level check after file.read() is always performed as a
defense-in-depth measure for clients that omit the Content-Length header.

Usage in a router:
    from fastapi import Request
    from middleware.upload_guard import enforce_upload_size
    from exceptions import UploadTooLargeError

    @router.post("/upload")
    async def upload(request: Request, file: UploadFile = File(...), ...):
        enforce_upload_size(request, limit_mb=settings.max_ocr_upload_mb)
        content = await file.read()
        actual_mb = len(content) / (1024 * 1024)
        if actual_mb > settings.max_ocr_upload_mb:
            raise UploadTooLargeError(limit_mb=settings.max_ocr_upload_mb, actual_mb=actual_mb)
        ...
"""

import logging

from fastapi import Request

from exceptions import UploadTooLargeError

logger = logging.getLogger(__name__)


def enforce_upload_size(request: Request, limit_mb: int) -> None:
    """
    Check Content-Length header against limit_mb before reading the body.
    Raises UploadTooLargeError if the declared content length exceeds the limit.
    No-op if Content-Length header is absent (caller must do byte-level check after read).
    """
    cl_header = request.headers.get("content-length")
    if cl_header:
        try:
            declared_bytes = int(cl_header)
        except ValueError:
            logger.warning("Invalid Content-Length header: %r — skipping pre-check", cl_header)
            return
        limit_bytes = limit_mb * 1024 * 1024
        if declared_bytes > limit_bytes:
            logger.warning(
                "Upload rejected via Content-Length: declared=%d bytes, limit=%d MB",
                declared_bytes,
                limit_mb,
            )
            raise UploadTooLargeError(limit_mb=limit_mb)
