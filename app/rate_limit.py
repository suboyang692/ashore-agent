"""Redis-backed fixed-window rate limiting with in-process fallback."""
import time

from app import cache
from app.config import RATE_LIMIT_ENABLED


def check(scope: str, subject: str, limit: int, window: int = 60) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    if not RATE_LIMIT_ENABLED or limit <= 0:
        return True, 0
    now = int(time.time())
    bucket = now // window
    key = f"ashore:rl:{scope}:{subject}:{bucket}"
    client = cache.backend()
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, window + 1)
    retry_after = max(window - (now % window), 1)
    return count <= limit, retry_after
