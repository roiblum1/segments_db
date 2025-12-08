import os
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.requests import Request
from starlette.responses import Response
import secrets
import logging

logger = logging.getLogger(__name__)

# Environment variables for authentication
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin")

# Session storage (in-memory, simple implementation)
# In production, consider using Redis or database-backed sessions
_sessions: dict[str, dict] = {}

# HTTP Basic Auth security scheme (for simple curl -u username:password)
basic_security = HTTPBasic(auto_error=False)


def create_session() -> str:
    """Create a new session token"""
    session_token = secrets.token_urlsafe(32)
    _sessions[session_token] = {"authenticated": True}
    return session_token


def get_session_token(request: Request) -> Optional[str]:
    """Extract session token from request cookies"""
    return request.cookies.get("session_token")


def validate_session(session_token: Optional[str]) -> bool:
    """Validate if session token is valid and authenticated"""
    if not session_token:
        return False
    session = _sessions.get(session_token)
    return session is not None and session.get("authenticated", False)


def invalidate_session(session_token: Optional[str]):
    """Invalidate a session token"""
    if session_token and session_token in _sessions:
        del _sessions[session_token]


async def get_current_user(
    request: Request,
    basic_credentials: Optional[HTTPBasicCredentials] = Depends(basic_security)
) -> bool:
    """Dependency to get current authenticated user
    
    Checks in order:
    1. Session cookie (for web UI)
    2. HTTP Basic Auth (for simple curl -u username:password)
    """
    # Check session cookie (for web UI)
    session_token = get_session_token(request)
    if validate_session(session_token):
        return True
    
    # Check HTTP Basic Auth (for curl -u username:password)
    if basic_credentials:
        if (basic_credentials.username == AUTH_USERNAME and 
            basic_credentials.password == AUTH_PASSWORD):
            return True
    
    return False


async def require_auth(
    current_user: bool = Depends(get_current_user)
) -> bool:
    """Dependency that requires authentication
    
    Raises HTTPException if user is not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login first."
        )
    return True


def login(username: str, password: str) -> Optional[str]:
    """Authenticate user and create session
    
    Returns session token if credentials are valid, None otherwise
    """
    if username == AUTH_USERNAME and password == AUTH_PASSWORD:
        session_token = create_session()
        logger.info(f"User '{username}' logged in successfully")
        return session_token
    else:
        logger.warning(f"Failed login attempt for username '{username}'")
        return None


def logout(request: Request):
    """Logout user by invalidating session"""
    session_token = get_session_token(request)
    if session_token:
        invalidate_session(session_token)
        logger.info("User logged out")


def check_auth_configured() -> bool:
    """Check if authentication is properly configured"""
    return bool(AUTH_USERNAME and AUTH_PASSWORD)

