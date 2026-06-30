import os
import json
import redis
from typing import Any, Optional

_redis_client: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        host = os.getenv('REDIS_HOST', 'localhost')
        port = int(os.getenv('REDIS_PORT', '6389'))
        _redis_client = redis.Redis(host=host, port=port, decode_responses=True)
    return _redis_client

def redis_set_json(key: str, data: Any, ttl: int = 300) -> None:
    """Store JSON data in Redis with TTL (default 5 min)."""
    try:
        get_redis().setex(key, ttl, json.dumps(data))
    except Exception:
        pass

def redis_get_json(key: str, default: Any = None) -> Any:
    """Get JSON data from Redis."""
    try:
        val = get_redis().get(key)
        if val:
            return json.loads(val)
        return default
    except Exception:
        return default
