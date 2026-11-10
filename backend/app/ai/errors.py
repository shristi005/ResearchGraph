"""Error types shared by every provider. Messages are safe to show to end users (no keys, no stack traces)."""

RATE_LIMIT = "rate_limit"            # HTTP 429 / quota exhausted  -> fallback, no same-provider retry
TRANSIENT = "transient"              # 5xx, timeout, connection    -> limited retry, then fallback
AUTH = "auth"                        # 401/403, missing/invalid key-> fallback, provider disabled for a while
MODEL_UNAVAILABLE = "model_unavailable"  # 404 / unknown model     -> fallback
BAD_REQUEST = "bad_request"          # 400/422 (our fault)         -> NEVER sent to the other provider
MALFORMED = "malformed"              # 200 but unusable body       -> one fallback attempt


class AIError(Exception):
    """Base class; str(exc) is safe to display."""


class AIUnavailable(AIError):
    """Neither provider could serve the request right now (quota, outage, missing config)."""


class AIConfigError(AIUnavailable):
    """No provider is configured (no API keys)."""


class ProviderError(AIError):
    def __init__(self, provider: str, kind: str, message: str, retry_after: float | None = None, status: int | None = None):
        super().__init__(message)
        self.provider, self.kind, self.retry_after, self.status = provider, kind, retry_after, status


def classify_status(status: int) -> str:
    if status == 429:
        return RATE_LIMIT
    if status in (401, 403):
        return AUTH
    if status == 404:
        return MODEL_UNAVAILABLE
    if status in (400, 413, 422):
        return BAD_REQUEST
    if status >= 500 or status in (408, 409):
        return TRANSIENT
    return BAD_REQUEST
