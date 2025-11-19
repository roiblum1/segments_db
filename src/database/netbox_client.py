"""
NetBox Client Management

This module handles NetBox API client initialization, thread pool executors,
and timing decorators for monitoring API performance.
"""

import logging
import pynetbox
from typing import Optional
import asyncio
import time
import concurrent.futures
from functools import lru_cache, wraps
import urllib3

from ..config.settings import NETBOX_URL, NETBOX_TOKEN, NETBOX_SSL_VERIFY

logger = logging.getLogger(__name__)

# Suppress InsecureRequestWarning when SSL verification is disabled
if not NETBOX_SSL_VERIFY:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global NetBox API client
_netbox_client: Optional[pynetbox.api] = None


def log_netbox_timing(operation_name: str):
    """
    Decorator to log the exact time a NetBox API call takes.
    This measures PURE NetBox response time at the HTTP level.
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                if elapsed > 20000:
                    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 5000:
                    logger.warning(f"⚠️  NETBOX THROTTLED: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 2000:
                    logger.info(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                else:
                    logger.debug(f"NETBOX OK: {operation_name} took {elapsed:.0f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}", exc_info=True)
                raise

        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                if elapsed > 20000:
                    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 5000:
                    logger.warning(f"⚠️  NETBOX THROTTLED: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 2000:
                    logger.info(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                else:
                    logger.debug(f"NETBOX OK: {operation_name} took {elapsed:.0f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}", exc_info=True)
                raise

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


@lru_cache(maxsize=1)
def get_netbox_read_executor():
    """Thread pool for read operations (GET requests)

    Read operations are typically fast (<500ms) and frequent.
    Uses 30 workers for high concurrency.
    """
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=30,
        thread_name_prefix="netbox_read_"
    )


@lru_cache(maxsize=1)
def get_netbox_write_executor():
    """Thread pool for write operations (POST/PUT/DELETE)

    Write operations can be slow (seconds) and should not block reads.
    Uses 20 workers to prevent overwhelming NetBox.
    """
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=20,
        thread_name_prefix="netbox_write_"
    )


@lru_cache(maxsize=1)
def get_netbox_executor():
    """Default executor - uses read pool for backward compatibility"""
    return get_netbox_read_executor()


def get_netbox_client() -> pynetbox.api:
    """Get or create the NetBox API client"""
    global _netbox_client

    if _netbox_client is None:
        logger.info(f"Initializing NetBox client: {NETBOX_URL}")
        _netbox_client = pynetbox.api(
            NETBOX_URL,
            token=NETBOX_TOKEN
        )
        _netbox_client.http_session.verify = NETBOX_SSL_VERIFY

    return _netbox_client


def close_netbox_client():
    """Close NetBox client connection"""
    global _netbox_client
    if _netbox_client is not None:
        logger.info("Closing NetBox client connection")
        _netbox_client = None

