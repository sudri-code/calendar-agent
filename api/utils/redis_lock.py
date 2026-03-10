import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis

from api.config import settings


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@asynccontextmanager
async def redis_lock(key: str, timeout: int = 30, retry_interval: float = 0.1, max_retries: int = 100) -> AsyncGenerator[None, None]:
    """Distributed Redis lock using SET NX EX pattern."""
    redis = _get_redis()
    lock_key = f"lock:{key}"
    acquired = False
    retries = 0

    try:
        while retries < max_retries:
            acquired = await redis.set(lock_key, "1", nx=True, ex=timeout)
            if acquired:
                break
            retries += 1
            await asyncio.sleep(retry_interval)

        if not acquired:
            raise TimeoutError(f"Could not acquire lock for {key} after {max_retries} retries")

        yield
    finally:
        if acquired:
            await redis.delete(lock_key)
        await redis.aclose()
