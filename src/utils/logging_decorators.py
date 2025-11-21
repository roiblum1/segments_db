"""Logging decorators to reduce verbose logging code.

Provides decorators that automatically handle logging for common patterns,
reducing boilerplate and ensuring consistent logging across the application.
"""

import logging
import time
from functools import wraps
from typing import Callable, Any


def log_operation_timing(operation_name: str = None, threshold_ms: int = 100):
    """Decorator to log operation timing with automatic slow operation warnings.

    Args:
        operation_name: Custom operation name (defaults to function name)
        threshold_ms: Warn if operation takes longer than this (milliseconds)

    Usage:
        @log_operation_timing("find_and_update", threshold_ms=500)
        async def find_one_and_update(...):
            # Function logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        logger = logging.getLogger(func.__module__)
        op_name = operation_name or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000

                if elapsed_ms > threshold_ms:
                    logger.warning(f"⏱️  SLOW: {op_name} took {elapsed_ms:.0f}ms (threshold: {threshold_ms}ms)")
                else:
                    logger.debug(f"⏱️  {op_name} took {elapsed_ms:.0f}ms")

                return result
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.error(f"⏱️  FAILED: {op_name} after {elapsed_ms:.0f}ms - {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000

                if elapsed_ms > threshold_ms:
                    logger.warning(f"⏱️  SLOW: {op_name} took {elapsed_ms:.0f}ms (threshold: {threshold_ms}ms)")
                else:
                    logger.debug(f"⏱️  {op_name} took {elapsed_ms:.0f}ms")

                return result
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.error(f"⏱️  FAILED: {op_name} after {elapsed_ms:.0f}ms - {e}")
                raise

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


__all__ = [
    "log_operation_timing",
]
