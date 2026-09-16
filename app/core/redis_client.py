"""Lazy singleton Redis client for the student chat's history cache
(`app/services/historico_cache.py`). Returns `None` when `REDIS_URL` isn't
configured, so the cache layer can treat "no client" the same as "client
unreachable" - both mean "fall back to Postgres" (see RNF6 in
`docs/AGENTS.md`)."""

from functools import lru_cache

import redis

from app.config import get_settings


@lru_cache
def get_redis_cliente() -> redis.Redis | None:
    settings = get_settings()
    if not settings.REDIS_URL:
        return None
    return redis.from_url(settings.REDIS_URL, decode_responses=True)
