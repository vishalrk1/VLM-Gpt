import redis.asyncio as redis
from functools import lru_cache
from app.config import settings

@lru_cache()
def get_redis_pool():
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )