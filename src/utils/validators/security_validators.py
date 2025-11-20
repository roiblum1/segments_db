"""Security validators to prevent injection attacks and malicious input.

Handles XSS prevention, script injection detection, path traversal prevention,
and input sanitization.
"""

import logging
import re
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class SecurityValidators:
    """Validators for security-related concerns"""

    @staticmethod
    def sanitize_input(input_str: str, max_length: int = 500) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not input_str:
            return input_str

        # Remove null bytes
        sanitized = input_str.replace('\x00', '')

        # Trim to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # Remove leading/trailing whitespace
        sanitized = sanitized.strip()

        return sanitized

    @staticmethod
    def validate_no_script_injection(text: str, field_name: str = "field") -> None:
        """
        Validate that text doesn't contain script injection patterns
        Protects against XSS when data is displayed in web UI
        """
        if not text:
            return

        # Check for common script injection patterns
        dangerous_patterns = [
            r'<script',
            r'javascript:',
            r'onerror=',
            r'onload=',
            r'onclick=',
            r'<iframe',
            r'<embed',
            r'<object',
            r'eval\(',
            r'expression\(',
        ]

        text_lower = text.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"Potential script injection detected in {field_name}: {pattern}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_name}' contains potentially dangerous content: {pattern}"
                )

        logger.debug(f"Script injection validation passed for {field_name}")

    @staticmethod
    def validate_no_path_traversal(filename: str) -> None:
        """
        Validate filename doesn't contain path traversal attempts
        Prevents accessing files outside intended directory
        """
        if not filename:
            return

        # Check for path traversal patterns
        dangerous_patterns = [
            '..',      # Parent directory
            '~',       # Home directory
            '/',       # Absolute path (at start)
            '\\',      # Windows path separator
        ]

        for pattern in dangerous_patterns:
            if pattern in filename:
                logger.warning(f"Path traversal attempt detected in filename: {filename}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid filename: contains dangerous pattern '{pattern}'"
                )

        # Additional checks
        if filename.startswith('/') or filename.startswith('\\'):
            raise HTTPException(
                status_code=400,
                detail="Filename cannot be an absolute path"
            )

        logger.debug(f"Path traversal validation passed for: {filename}")

    @staticmethod
    def validate_rate_limit_data(request_count: int, time_window_seconds: int, max_requests: int = 100) -> None:
        """
        Helper to validate rate limiting (not enforcing, just validating params)
        Actual rate limiting should be done at API gateway level
        """
        if request_count < 0:
            raise HTTPException(status_code=400, detail="Request count cannot be negative")

        if time_window_seconds <= 0:
            raise HTTPException(status_code=400, detail="Time window must be positive")

        if request_count > max_requests:
            logger.warning(f"Rate limit exceeded: {request_count} requests in {time_window_seconds}s")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {request_count} requests in {time_window_seconds} seconds. Maximum: {max_requests}"
            )
