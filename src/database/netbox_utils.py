"""
NetBox Utility Functions

This module provides common utility functions to reduce code duplication
across NetBox-related modules.
"""

import logging
import asyncio
import time
from typing import Callable, Any, Tuple
from functools import wraps

from .netbox_client import get_netbox_read_executor, get_netbox_write_executor, get_netbox_executor

logger = logging.getLogger(__name__)


def get_executor_setup(executor_type: str = "default") -> Tuple[asyncio.AbstractEventLoop, Any]:
    """
    Get event loop and executor setup (reduces code duplication)
    
    Args:
        executor_type: "read", "write", or "default"
        
    Returns:
        Tuple of (loop, executor)
    """
    loop = asyncio.get_event_loop()
    
    if executor_type == "read":
        executor = get_netbox_read_executor()
    elif executor_type == "write":
        executor = get_netbox_write_executor()
    else:
        executor = get_netbox_executor()
    
    return loop, executor


def log_netbox_timing(elapsed_ms: float, operation_name: str) -> None:
    """
    Log NetBox operation timing with consistent thresholds
    
    Args:
        elapsed_ms: Elapsed time in milliseconds
        operation_name: Name of the operation for logging
    """
    if elapsed_ms > 20000:
        logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation_name} took {elapsed_ms:.0f}ms ({elapsed_ms/1000:.1f}s)")
    elif elapsed_ms > 5000:
        logger.warning(f"⚠️  NETBOX THROTTLED: {operation_name} took {elapsed_ms:.0f}ms ({elapsed_ms/1000:.1f}s)")
    elif elapsed_ms > 2000:
        logger.info(f"⏱️  NETBOX SLOW: {operation_name} took {elapsed_ms:.0f}ms")
    else:
        logger.debug(f"⏱️  NETBOX OK: {operation_name} took {elapsed_ms:.0f}ms")


async def run_netbox_operation(
    operation: Callable,
    operation_name: str,
    executor_type: str = "default"
) -> Any:
    """
    Run a NetBox operation with timing and error handling
    
    Args:
        operation: Callable that performs the NetBox operation
        operation_name: Name for logging
        executor_type: "read", "write", or "default"
        
    Returns:
        Result of the operation
    """
    loop, executor = get_executor_setup(executor_type)
    
    start = time.time()
    try:
        result = await loop.run_in_executor(executor, operation)
        elapsed = (time.time() - start) * 1000
        log_netbox_timing(elapsed, operation_name)
        return result
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}", exc_info=True)
        raise


async def run_netbox_get(
    get_operation: Callable,
    operation_name: str
) -> Any:
    """
    Run a NetBox GET operation (read) with timing
    
    Args:
        get_operation: Callable that performs the NetBox GET operation
        operation_name: Name for logging
        
    Returns:
        Result of the operation
    """
    return await run_netbox_operation(get_operation, operation_name, executor_type="read")


async def run_netbox_write(
    write_operation: Callable,
    operation_name: str
) -> Any:
    """
    Run a NetBox write operation (POST/PUT/DELETE) with timing
    
    Args:
        write_operation: Callable that performs the NetBox write operation
        operation_name: Name for logging
        
    Returns:
        Result of the operation
    """
    return await run_netbox_operation(write_operation, operation_name, executor_type="write")

