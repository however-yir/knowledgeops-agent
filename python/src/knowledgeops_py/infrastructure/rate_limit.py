from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(slots=True)
class RedisTokenBucket:
    url: str
    capacity: int

    async def allow(self, key: str) -> bool:
        client = redis.Redis.from_url(self.url, decode_responses=True)
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
        finally:
            await client.aclose()


def now_millis() -> int:
    import time

    return int(time.time() * 1000)
