from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from knowledgeops_py.domain.ports import OidcStateStore, OidcStateUnavailable

__all__ = ["OidcStateStore", "OidcStateUnavailable", "RedisOidcStateStore"]


@dataclass(slots=True)
class RedisOidcStateStore:
    url: str
    prefix: str = "knowledgeops:oidc"

    async def put(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        client = redis.Redis.from_url(self.url, decode_responses=True)
        try:
            await client.set(self._key(namespace, key), json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
        except RedisError as exc:
            raise OidcStateUnavailable("OIDC state store is unavailable") from exc
        finally:
            await client.aclose()

    async def consume(self, namespace: str, key: str) -> dict[str, Any] | None:
        client = redis.Redis.from_url(self.url, decode_responses=True)
        try:
            raw = await client.getdel(self._key(namespace, key))
        except RedisError as exc:
            raise OidcStateUnavailable("OIDC state store is unavailable") from exc
        finally:
            await client.aclose()
        return json.loads(raw) if raw else None

    def _key(self, namespace: str, key: str) -> str:
        return f"{self.prefix}:{namespace}:{key}"
