"""
Error Handling Utilities and Resilience Patterns

This module provides robust error handling for NetBox API calls,
network failures, and other edge cases.
"""

import logging
import asyncio
from typing import Callable, Any, Optional
from functools import wraps
from fastapi import HTTPException
import requests
from pynetbox.core.query import RequestError

logger = logging.getLogger(__name__)


class NetBoxAPIError(Exception):
    """Custom exception for NetBox API errors"""
    def __init__(self, message: str, status_code: int = None, original_error: Exception = None):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(self.message)


class NetworkTimeoutError(Exception):
    """Custom exception for network timeouts"""
    pass


class ConcurrentModificationError(Exception):
    """Custom exception for concurrent modification conflicts"""
    pass


def retry_on_network_error(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator to retry function on network errors with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for exponential backoff

    Usage:
        @retry_on_network_error(max_retries=3, delay=1.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.RequestException,
                        NetworkTimeoutError) as e:

                    last_exception = e

                    if attempt < max_retries:
                        logger.warning(
                            f"Network error in {func.__name__} (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Network error in {func.__name__} failed after {max_retries} retries: {e}"
                        )

                except Exception as e:
                    # Don't retry on non-network errors
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise

            # If we get here, all retries failed
            raise NetworkTimeoutError(
                f"Operation failed after {max_retries} retries: {str(last_exception)}"
            )

        return wrapper
    return decorator


def handle_netbox_errors(func: Callable):
    """
    Decorator to handle NetBox API errors and convert them to appropriate HTTP exceptions

    Usage:
        @handle_netbox_errors
        async def create_prefix(...):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except RequestError as e:
            # NetBox API returned an error
            error_msg = str(e)
            status_code = 500

            # Extract status code from error if possible
            if hasattr(e, 'req') and hasattr(e.req, 'status_code'):
                status_code = e.req.status_code

            # Parse common NetBox errors
            if '404' in error_msg or 'not found' in error_msg.lower():
                status_code = 404
                detail = "Resource not found in NetBox"
            elif '403' in error_msg or 'forbidden' in error_msg.lower():
                status_code = 403
                detail = "Access denied to NetBox resource. Check API token permissions."
            elif '401' in error_msg or 'unauthorized' in error_msg.lower():
                status_code = 401
                detail = "NetBox authentication failed. Check API token."
            elif '400' in error_msg or 'bad request' in error_msg.lower():
                status_code = 400
                detail = f"Invalid request to NetBox: {error_msg}"
            elif 'timeout' in error_msg.lower():
                status_code = 504
                detail = "NetBox API request timed out"
            else:
                detail = f"NetBox API error: {error_msg}"

            logger.error(f"NetBox API error in {func.__name__}: {detail}")
            raise HTTPException(status_code=status_code, detail=detail)

        except (requests.exceptions.ConnectionError, NetworkTimeoutError) as e:
            logger.error(f"Network error connecting to NetBox in {func.__name__}: {e}")
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to NetBox. Please check network connectivity."
            )

        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout connecting to NetBox in {func.__name__}: {e}")
            raise HTTPException(
                status_code=504,
                detail="NetBox API request timed out. Please try again."
            )

        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )

    return wrapper


def validate_netbox_response(response: Any, resource_type: str = "resource") -> Any:
    """
    Validate that NetBox API response is not None and contains expected data

    Args:
        response: Response from NetBox API
        resource_type: Type of resource for error message

    Returns:
        The response if valid

    Raises:
        HTTPException: If response is invalid
    """
    if response is None:
        logger.error(f"NetBox returned None for {resource_type}")
        raise HTTPException(
            status_code=404,
            detail=f"{resource_type.capitalize()} not found in NetBox"
        )

    return response


def handle_concurrent_modification():
    """
    Context manager to handle concurrent modification detection

    Usage:
        with handle_concurrent_modification():
            # Read data
            original_version = data['version']
            # Modify data
            # Update with version check
            if current_version != original_version:
                raise ConcurrentModificationError()
    """
    class ConcurrentModificationHandler:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type == ConcurrentModificationError:
                logger.warning("Concurrent modification detected")
                raise HTTPException(
                    status_code=409,
                    detail="Resource was modified by another request. Please refresh and try again."
                )
            return False

    return ConcurrentModificationHandler()


def log_slow_operations(threshold_seconds: float = 2.0):
    """
    Decorator to log operations that take longer than threshold

    Args:
        threshold_seconds: Time threshold in seconds

    Usage:
        @log_slow_operations(threshold_seconds=2.0)
        async def slow_operation():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import time
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                return result

            finally:
                elapsed_time = time.time() - start_time
                if elapsed_time > threshold_seconds:
                    logger.warning(
                        f"Slow operation detected: {func.__name__} took {elapsed_time:.2f}s "
                        f"(threshold: {threshold_seconds}s)"
                    )

        return wrapper
    return decorator


def safe_int_conversion(value: Any, field_name: str = "value", min_val: int = None, max_val: int = None) -> int:
    """
    Safely convert value to integer with validation

    Args:
        value: Value to convert
        field_name: Name of field for error messages
        min_val: Minimum allowed value (optional)
        max_val: Maximum allowed value (optional)

    Returns:
        Integer value

    Raises:
        HTTPException: If conversion fails or value out of range
    """
    try:
        int_val = int(value)

        if min_val is not None and int_val < min_val:
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} must be at least {min_val}, got {int_val}"
            )

        if max_val is not None and int_val > max_val:
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} must be at most {max_val}, got {int_val}"
            )

        return int_val

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid integer, got '{value}'"
        )


def safe_list_access(lst: list, index: int, default: Any = None) -> Any:
    """
    Safely access list element with bounds checking

    Args:
        lst: List to access
        index: Index to access
        default: Default value if index out of bounds

    Returns:
        Element at index or default value
    """
    try:
        return lst[index]
    except (IndexError, TypeError):
        return default


def safe_dict_access(dct: dict, key: str, default: Any = None, required: bool = False) -> Any:
    """
    Safely access dictionary key with optional requirement

    Args:
        dct: Dictionary to access
        key: Key to access
        default: Default value if key missing
        required: If True, raise error if key missing

    Returns:
        Value at key or default

    Raises:
        HTTPException: If required key is missing
    """
    if key not in dct and required:
        raise HTTPException(
            status_code=400,
            detail=f"Required field '{key}' is missing"
        )

    return dct.get(key, default)


def chunk_list(lst: list, chunk_size: int):
    """
    Split list into chunks for batch processing

    Args:
        lst: List to chunk
        chunk_size: Size of each chunk

    Yields:
        Chunks of the list
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


async def batch_process_with_retry(
    items: list,
    process_func: Callable,
    batch_size: int = 10,
    max_retries: int = 3
) -> list:
    """
    Process items in batches with retry logic

    Args:
        items: List of items to process
        process_func: Async function to process each item
        batch_size: Number of items per batch
        max_retries: Maximum retries per item

    Returns:
        List of results
    """
    results = []

    for batch in chunk_list(items, batch_size):
        batch_results = []

        for item in batch:
            for attempt in range(max_retries + 1):
                try:
                    result = await process_func(item)
                    batch_results.append(result)
                    break

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"Batch processing error (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(0.5 * (attempt + 1))
                    else:
                        logger.error(f"Batch processing failed for item after {max_retries} retries: {e}")
                        batch_results.append({"error": str(e), "item": item})

        results.extend(batch_results)

    return results


def netbox_operation(operation_name: str, threshold_ms: int = 1000, max_retries: int = 3):
    """
    Combined decorator for NetBox operations that applies all standard patterns:
    - Error handling and conversion to HTTP exceptions
    - Retry logic with exponential backoff
    - Operation timing with performance logging

    This decorator combines @handle_netbox_errors, @retry_on_network_error,
    and @log_operation_timing to reduce repetitive decorator stacking.

    Args:
        operation_name: Name of the operation for logging
        threshold_ms: Performance threshold in milliseconds (default: 1000ms)
        max_retries: Maximum number of retry attempts (default: 3)

    Usage:
        @netbox_operation("create_segment", threshold_ms=2000, max_retries=3)
        async def create_segment(segment_data):
            # Your code here
            pass

    Example - Before:
        @staticmethod
        @handle_netbox_errors
        @retry_on_network_error(max_retries=3)
        @log_operation_timing("create_segment", threshold_ms=2000)
        async def create_segment(segment: Segment):
            ...

    Example - After:
        @staticmethod
        @netbox_operation("create_segment", threshold_ms=2000, max_retries=3)
        async def create_segment(segment: Segment):
            ...
    """
    from ..utils.logging_decorators import log_operation_timing

    def decorator(func: Callable) -> Callable:
        # Apply decorators in correct order (innermost to outermost):
        # 1. Log timing (innermost - measures actual function execution)
        # 2. Retry logic (middle - retries on failure)
        # 3. Error handling (outermost - converts all errors to HTTP exceptions)
        decorated_func = log_operation_timing(operation_name, threshold_ms=threshold_ms)(func)
        decorated_func = retry_on_network_error(max_retries=max_retries)(decorated_func)
        decorated_func = handle_netbox_errors(decorated_func)
        return decorated_func

    return decorator
