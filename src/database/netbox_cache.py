"""
NetBox Cache Management

This module provides caching functionality for NetBox API responses
to reduce API calls and improve performance. Uses TTL-based caching
with in-flight request tracking to prevent duplicate concurrent fetches.
"""

import logging
import time
from typing import Optional, Any, Dict
import asyncio

logger = logging.getLogger(__name__)

# Simple in-memory cache with TTL
# Optimized caching to reduce NetBox API calls while keeping data reasonably fresh
# Now supports dynamic cache keys (e.g., site_group_{id}) with automatic TTL assignment
_cache: Dict[str, Dict[str, Any]] = {
    "prefixes": {"data": None, "timestamp": 0, "ttl": 600},  # 10 minutes (matches CLAUDE.md spec)
    "vlans": {"data": None, "timestamp": 0, "ttl": 600},  # 10 minutes
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour (rarely changes)
    "vrfs": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour (rarely changes)
    "site_groups": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour (rarely changes)
    "roles": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour (rarely changes)
    "tenants": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour (rarely changes)
}

# Default TTL for dynamic cache keys (e.g., site_group_123, role_data_prefix)
_default_ttl = 600  # 10 minutes

# In-flight request tracking to prevent duplicate concurrent fetches
_inflight_requests: Dict[str, asyncio.Task] = {}


def get_cached(key: str) -> Optional[Any]:
    """Get cached data if still valid"""
    cache_entry = _cache.get(key)
    if cache_entry and cache_entry["data"] is not None:
        age = time.time() - cache_entry["timestamp"]
        if age < cache_entry["ttl"]:
            logger.debug(f"Cache HIT for {key} (age: {age:.1f}s)")
            return cache_entry["data"]
        else:
            logger.debug(f"Cache EXPIRED for {key} (age: {age:.1f}s, TTL: {cache_entry['ttl']}s)")
    return None


def set_cache(key: str, data: Any, ttl: Optional[int] = None) -> None:
    """Store data in cache with timestamp

    Args:
        key: Cache key (supports dynamic keys like 'site_group_123')
        data: Data to cache
        ttl: Optional TTL in seconds (uses default if not specified)
    """
    if key not in _cache:
        # Dynamically create cache entry for new keys (e.g., site_group_{id})
        effective_ttl = ttl if ttl is not None else _default_ttl
        _cache[key] = {"data": None, "timestamp": 0, "ttl": effective_ttl}
        logger.debug(f"Created dynamic cache entry for {key} with TTL={effective_ttl}s")

    _cache[key]["data"] = data
    _cache[key]["timestamp"] = time.time()
    logger.debug(f"Cache SET for {key} ({len(data) if isinstance(data, list) else 'N/A'} items)")


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


def get_inflight_request(key: str) -> Optional[asyncio.Task]:
    """Get an in-flight request task if it exists"""
    return _inflight_requests.get(key)


def set_inflight_request(key: str, task: asyncio.Task) -> None:
    """Set an in-flight request task"""
    _inflight_requests[key] = task


def remove_inflight_request(key: str) -> None:
    """Remove an in-flight request task"""
    _inflight_requests.pop(key, None)

