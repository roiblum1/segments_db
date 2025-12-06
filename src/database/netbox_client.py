"""
NetBox Client Management

Handles NetBox API client initialization, thread pool executors, and utility functions.
"""

import logging
import pynetbox
from typing import Optional, Callable, Any, Tuple
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


@lru_cache(maxsize=1)
def get_netbox_read_executor():
    """Thread pool for read operations (GET requests) - 30 workers for high concurrency"""
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=30,
        thread_name_prefix="netbox_read_"
    )


@lru_cache(maxsize=1)
def get_netbox_write_executor():
    """Thread pool for write operations (POST/PUT/DELETE) - 20 workers"""
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
        _netbox_client = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
        _netbox_client.http_session.verify = NETBOX_SSL_VERIFY

    return _netbox_client


def close_netbox_client():
    """Close NetBox client connection"""
    global _netbox_client
    if _netbox_client is not None:
        _netbox_client = None


def log_netbox_timing(operation_name: str):
    """Decorator to log slow NetBox operations only (>2s)"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                # Only log slow operations (>2s)
                if elapsed > 2000:
                    logger.warning(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}")
                raise

        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                if elapsed > 2000:
                    logger.warning(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}")
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


async def run_netbox_get(get_operation: Callable, operation_name: str) -> Any:
    """Run a NetBox GET operation (read)"""
    loop = asyncio.get_event_loop()
    executor = get_netbox_read_executor()
    
    start = time.time()
    try:
        result = await loop.run_in_executor(executor, get_operation)
        elapsed = (time.time() - start) * 1000
        # Only log slow operations
        if elapsed > 2000:
            logger.warning(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
        return result
    except Exception as e:
        logger.error(f"NETBOX FAILED: {operation_name} - {e}")
        raise


async def run_netbox_write(write_operation: Callable, operation_name: str) -> Any:
    """Run a NetBox write operation (POST/PUT/DELETE)"""
    loop = asyncio.get_event_loop()
    executor = get_netbox_write_executor()
    
    start = time.time()
    try:
        result = await loop.run_in_executor(executor, write_operation)
        elapsed = (time.time() - start) * 1000
        # Only log slow operations
        if elapsed > 2000:
            logger.warning(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
        return result
    except Exception as e:
        logger.error(f"NETBOX FAILED: {operation_name} - {e}")
        raise
