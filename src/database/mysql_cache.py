"""
MySQL Cache Manager
Handles caching logic with TTL support
"""
import logging
import time
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

# Cache storage with TTL configuration
_cache: Dict[str, Dict[str, Any]] = {
    "segments": {"data": None, "timestamp": 0, "ttl": 5},  # 5-second TTL
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour TTL
}


def get_cached(key: str) -> Optional[Any]:
    """
    Get cached data if still valid

    Args:
        key: Cache key

    Returns:
        Cached data if valid, None otherwise
    """
    cache_entry = _cache.get(key)

    if cache_entry and cache_entry["data"] is not None:
        age = time.time() - cache_entry["timestamp"]

        if age < cache_entry["ttl"]:
            logger.debug(f"Cache HIT for {key} (age: {age:.1f}s)")
            return cache_entry["data"]
        else:
            logger.debug(
                f"Cache EXPIRED for {key} "
                f"(age: {age:.1f}s, TTL: {cache_entry['ttl']}s)"
            )

    return None


def set_cache(key: str, data: Any) -> None:
    """
    Store data in cache with timestamp

    Args:
        key: Cache key
        data: Data to cache
    """
    if key in _cache:
        _cache[key]["data"] = data
        _cache[key]["timestamp"] = time.time()

        data_size = len(data) if isinstance(data, list) else "N/A"
        logger.debug(f"Cache SET for {key} ({data_size} items)")


def invalidate_cache(key: Optional[str] = None) -> None:
    """
    Invalidate cache entries

    Args:
        key: Specific cache key to invalidate, or None to clear all
    """
    if key:
        if key in _cache:
            _cache[key]["data"] = None
            _cache[key]["timestamp"] = 0
            logger.info(f"Cache INVALIDATED for {key}")
    else:
        for cache_key in _cache:
            _cache[cache_key]["data"] = None
            _cache[cache_key]["timestamp"] = 0
        logger.info("Cache INVALIDATED (all)")


def register_cache_key(key: str, ttl: int) -> None:
    """
    Register a new cache key with TTL

    Args:
        key: Cache key
        ttl: Time-to-live in seconds
    """
    if key not in _cache:
        _cache[key] = {"data": None, "timestamp": 0, "ttl": ttl}
        logger.debug(f"Registered cache key: {key} (TTL: {ttl}s)")


# Cache key constants
class CacheKeys:
    """Cache key constants"""
    SEGMENTS = "segments"
    REDBULL_TENANT_ID = "redbull_tenant_id"
