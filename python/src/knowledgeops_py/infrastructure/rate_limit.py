from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError


class RateLimitUnavailable(RuntimeError):
    pass


RATE_LIMIT_LUA = """
local key, now, capacity, refill = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + ((now - updated) / 1000) * refill)
if tokens < 1 then
  redis.call('HMSET', key, 'tokens', tokens, 'updated', now)
  redis.call('PEXPIRE', key, math.ceil((capacity / refill) * 2000))
  return 0
end
redis.call('HMSET', key, 'tokens', tokens - 1, 'updated', now)
redis.call('PEXPIRE', key, math.ceil((capacity / refill) * 2000))
return 1
"""

# One client per URL for the whole process: redis.Redis owns a connection
# pool, so sharing it means no fresh TCP connection per request.
_CLIENTS: dict[str, Any] = {}


def shared_client(url: str) -> Any:
    client = _CLIENTS.get(url)
    if client is None:
        client = redis.Redis.from_url(url, decode_responses=True)
        _CLIENTS[url] = client
    return client


@dataclass(slots=True)
class RedisTokenBucket:
    """Token bucket backed by Redis.

    Buckets are cheap value objects; the Redis client (and its connection
    pool) is shared process-wide via :func:`shared_client`. Use
    :func:`shared_token_bucket` in request paths to avoid rebuilding buckets.
    """

    url: str
    capacity: int

    async def allow(self, key: str) -> bool:
        client = shared_client(self.url)
        try:
            result = await client.eval(
                RATE_LIMIT_LUA,
                1,
                f"knowledgeops:rate:{key}",
                str(now_millis()),
                str(self.capacity),
                str(self.capacity / 60),
            )
            return bool(result)
        except RedisError as exc:
            raise RateLimitUnavailable("Redis rate limiter is unavailable") from exc


_BUCKETS: dict[tuple[str, int], RedisTokenBucket] = {}


def shared_token_bucket(url: str, capacity: int) -> RedisTokenBucket:
    """Return the process-wide bucket for a (url, capacity) pair."""
    cache_key = (url, capacity)
    bucket = _BUCKETS.get(cache_key)
    if bucket is None:
        bucket = RedisTokenBucket(url=url, capacity=capacity)
        _BUCKETS[cache_key] = bucket
    return bucket


def now_millis() -> int:
    import time

    return int(time.time() * 1000)
