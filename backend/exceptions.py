"""
NarratIQ custom exceptions.

These are raised by internal code and caught by global exception handlers
registered in main.py. Keeping them here prevents circular imports — this
module must import nothing from the NarratIQ codebase.
"""


class AIServiceUnavailableError(Exception):
    """
    Raised when vLLM is overloaded, unreachable, or returns a 5xx error.
    Caught by the global handler in main.py → returns HTTP 503 with Retry-After.
    Also caught inside background task functions to update job status to 'failed'.
    """

    def __init__(self, message: str = "AI services temporarily unavailable", retry_after: int = 30):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class UploadTooLargeError(Exception):
    """
    Raised when an uploaded file exceeds the configured size limit.
    Caught by the global handler in main.py → returns HTTP 413.
    """

    def __init__(self, limit_mb: int, actual_mb: float | None = None):
        msg = f"File too large. Maximum allowed size is {limit_mb} MB."
        if actual_mb is not None:
            msg = f"File too large ({actual_mb:.1f} MB). Maximum allowed size is {limit_mb} MB."
        super().__init__(msg)
        self.message = msg
        self.limit_mb = limit_mb
        self.actual_mb = actual_mb
