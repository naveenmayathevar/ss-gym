"""
app/services/cache.py

Redis cache service for SS Gym.
- Connects via REDIS_URL environment variable
- Gracefully falls back to no-cache if Redis is unavailable
- All cache keys are prefixed with 'ssgym:' to avoid collisions
"""
import json
import logging
import os

import redis

logger = logging.getLogger(__name__)

# ── Cache key constants ────────────────────────────────────────────────────────
CACHE_KEY_CLASS_LIST    = "ssgym:classes:list"          # Full class list
CACHE_KEY_CLASS_DETAIL  = "ssgym:classes:{id}"          # Single class detail
CACHE_KEY_CLASS_CAPACITY = "ssgym:classes:{id}:capacity" # Spots remaining

# TTL (seconds)
TTL_CLASS_LIST    = 300   # 5 minutes
TTL_CLASS_DETAIL  = 300
TTL_CLASS_CAPACITY = 60   # 1 minute — capacity changes more often


def _get_client() -> redis.Redis | None:
    """
    Build a Redis client from REDIS_URL.
    Returns None (and logs a warning) if the URL is missing or Redis is down.
    This is the fallback: the app keeps working, just without caching.
    """
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()          # Fail fast if Redis is unreachable
        return client
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — running without cache.", exc)
        return None


# Module-level client — created once when the module is first imported
_client: redis.Redis | None = _get_client()


def _redis() -> redis.Redis | None:
    """Return the shared client (or None if Redis is down)."""
    return _client


# ── Low-level helpers ──────────────────────────────────────────────────────────

def get(key: str):
    """
    Fetch a JSON-encoded value from Redis.
    Returns the decoded Python object, or None on miss / error.
    """
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("Cache GET failed for key '%s': %s", key, exc)
        return None


def set(key: str, value, ttl: int = 300) -> bool:
    """
    Store a JSON-encoded value in Redis with a TTL.
    Returns True on success, False on error / Redis unavailable.
    """
    r = _redis()
    if r is None:
        return False
    try:
        r.setex(key, ttl, json.dumps(value))
        return True
    except Exception as exc:
        logger.warning("Cache SET failed for key '%s': %s", key, exc)
        return False


def delete(*keys: str) -> bool:
    """
    Delete one or more keys from Redis.
    Returns True on success, False on error / Redis unavailable.
    """
    r = _redis()
    if r is None:
        return False
    try:
        r.delete(*keys)
        return True
    except Exception as exc:
        logger.warning("Cache DELETE failed for keys %s: %s", keys, exc)
        return False


def delete_pattern(pattern: str) -> bool:
    """
    Delete all keys matching a glob pattern (e.g. 'ssgym:classes:*').
    Uses SCAN to avoid blocking Redis on large datasets.
    """
    r = _redis()
    if r is None:
        return False
    try:
        keys = list(r.scan_iter(pattern))
        if keys:
            r.delete(*keys)
        return True
    except Exception as exc:
        logger.warning("Cache DELETE pattern '%s' failed: %s", pattern, exc)
        return False


# ── High-level cache operations ────────────────────────────────────────────────

def get_class_list():
    """Return cached class list, or None on miss."""
    return get(CACHE_KEY_CLASS_LIST)


def set_class_list(data: list) -> bool:
    """Cache the full class list."""
    return set(CACHE_KEY_CLASS_LIST, data, TTL_CLASS_LIST)


def get_class_detail(class_id: int):
    """Return cached detail for a single class, or None on miss."""
    return get(CACHE_KEY_CLASS_DETAIL.format(id=class_id))


def set_class_detail(class_id: int, data: dict) -> bool:
    """Cache detail for a single class."""
    return set(CACHE_KEY_CLASS_DETAIL.format(id=class_id), data, TTL_CLASS_DETAIL)


def get_class_capacity(class_id: int):
    """Return cached spots-remaining for a class, or None on miss."""
    return get(CACHE_KEY_CLASS_CAPACITY.format(id=class_id))


def set_class_capacity(class_id: int, spots_left: int) -> bool:
    """Cache spots-remaining for a class."""
    return set(CACHE_KEY_CLASS_CAPACITY.format(id=class_id), spots_left, TTL_CLASS_CAPACITY)


def invalidate_class_cache(class_id: int | None = None) -> None:
    """
    Invalidate class-related cache entries.

    - Always clears the class list (it changed).
    - If class_id is given, also clears that class's detail and capacity.
    - Call this after: add class, delete class, book class, cancel booking.
    """
    delete(CACHE_KEY_CLASS_LIST)

    if class_id is not None:
        delete(
            CACHE_KEY_CLASS_DETAIL.format(id=class_id),
            CACHE_KEY_CLASS_CAPACITY.format(id=class_id),
        )

    logger.debug("Cache invalidated (class_id=%s)", class_id)