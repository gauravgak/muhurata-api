"""
ratelimit.py — a tiny in-process token-bucket limiter.

Per worker, in memory. At this app's scale (~10k users total, tens of
concurrent requests) that is enough to stop a single abusive IP from
filling the leads table or burning LLM spend. Cloudflare in front does
the coarse, cross-worker limiting; this is the fine backstop on the
write/cost endpoints.

Not durable, not shared between workers, resets on redeploy — all fine
for its job. If you ever need global limits, move the buckets to Postgres
or Redis behind the same allow() call.
"""

import threading
import time

from fastapi import HTTPException, Request

_buckets: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()
_MAX_KEYS = 50_000


def allow(key: str, per_minute: float, burst: float | None = None) -> bool:
    """True if this call is within budget for `key`."""
    burst = burst if burst is not None else per_minute
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(key, (burst, now))
        tokens = min(burst, tokens + (now - last) * (per_minute / 60.0))
        if tokens < 1.0:
            _buckets[key] = (tokens, now)
            return False
        if len(_buckets) > _MAX_KEYS:
            _buckets.clear()
        _buckets[key] = (tokens - 1.0, now)
        return True


def client_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def limiter(name: str, per_minute: float, burst: float | None = None):
    """Build a FastAPI dependency that rate-limits by client IP."""
    def dep(request: Request):
        if not allow(f"{name}:{client_ip(request)}", per_minute, burst):
            raise HTTPException(
                429,
                "You're going a little fast — please wait a minute and try again.",
            )
    return dep
