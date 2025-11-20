"""Logging decorators to reduce verbose logging code.

Provides decorators that automatically handle logging for common patterns,
reducing boilerplate and ensuring consistent logging across the application.
"""

import logging
import time
from functools import wraps
from typing import Callable, Any


def log_function_call(operation_name: str = None, level: str = "debug"):
    """Decorator to log function entry and exit.

    Args:
        operation_name: Custom operation name (defaults to function name)
        level: Logging level ("debug", "info", "warning", "error")

    Usage:
        @log_function_call("Processing segment")
        async def process_segment(segment_id):
            # Function logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        log_func = getattr(logging.getLogger(func.__module__), level)
        op_name = operation_name or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            log_func(f"Starting: {op_name}")
            try:
                result = await func(*args, **kwargs)
                log_func(f"Completed: {op_name}")
                return result
            except Exception as e:
                logging.getLogger(func.__module__).error(f"Failed: {op_name} - {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            log_func(f"Starting: {op_name}")
            try:
                result = func(*args, **kwargs)
                log_func(f"Completed: {op_name}")
                return result
            except Exception as e:
                logging.getLogger(func.__module__).error(f"Failed: {op_name} - {e}")
                raise

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


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


def log_validation(validation_name: str = None):
    """Decorator to automatically log validation success/failure.

    Args:
        validation_name: Custom validation name (defaults to function name)

    Usage:
        @log_validation("site validation")
        def validate_site(site: str):
            if site not in SITES:
                raise HTTPException(...)
    """
    def decorator(func: Callable) -> Callable:
        logger = logging.getLogger(func.__module__)
        val_name = validation_name or func.__name__.replace('validate_', '').replace('_', ' ')

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"✓ {val_name} passed")
                return result
            except Exception as e:
                logger.debug(f"✗ {val_name} failed: {str(e)}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                logger.debug(f"✓ {val_name} passed")
                return result
            except Exception as e:
                logger.debug(f"✗ {val_name} failed: {str(e)}")
                raise

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_database_operation(operation_type: str = None):
    """Decorator to log database operations (CRUD).

    Args:
        operation_type: Type of operation (create, read, update, delete)

    Usage:
        @log_database_operation("create")
        async def create_segment(segment_data):
            # Function logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        logger = logging.getLogger(func.__module__)
        op_type = operation_type or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.info(f"Database operation: {op_type}")
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000
                logger.info(f"Database operation completed: {op_type} ({elapsed_ms:.0f}ms)")
                return result
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.error(f"Database operation failed: {op_type} after {elapsed_ms:.0f}ms - {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.info(f"Database operation: {op_type}")
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000
                logger.info(f"Database operation completed: {op_type} ({elapsed_ms:.0f}ms)")
                return result
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.error(f"Database operation failed: {op_type} after {elapsed_ms:.0f}ms - {e}")
                raise

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


__all__ = [
    "log_function_call",
    "log_operation_timing",
    "log_validation",
    "log_database_operation",
]
