"""Redis-backed fixed-window rate limiting."""

from typing import Protocol

import redis.asyncio as redis


class RateLimiter(Protocol):
    """Interface for route request rate limiters."""

    async def allows(self, client_ip: str) -> bool:
        """Return whether another route request is allowed for this client."""


class RedisRateLimiter:
    """Limit route calculations per IP with an atomic Redis counter."""

    def __init__(self, redis_url: str, limit: int = 60) -> None:
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._limit = limit

    async def allows(self, client_ip: str) -> bool:
        """Consume one request from the current one-minute window."""
        key = f"rate:routes:{client_ip}"
        count = await self._client.eval(
            "local count = redis.call('INCR', KEYS[1]); "
            "if count == 1 then redis.call('EXPIRE', KEYS[1], 60); end; return count",
            1,
            key,
        )
        return int(count) <= self._limit
