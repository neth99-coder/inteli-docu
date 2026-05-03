import json

from redis import Redis

from app.config import get_settings

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def enqueue_job(payload: dict) -> None:
    settings = get_settings()
    get_redis().rpush(settings.queue_name, json.dumps(payload))


def dequeue_job(timeout_seconds: int = 5) -> dict | None:
    settings = get_settings()
    result = get_redis().blpop(settings.queue_name, timeout=timeout_seconds)
    if not result:
        return None

    _queue_name, payload = result
    return json.loads(payload)

