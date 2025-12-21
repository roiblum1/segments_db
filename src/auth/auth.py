import os
import json
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.requests import Request
from starlette.responses import Response
import secrets
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Environment variables for authentication
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin")

# Session storage file path (persistent across restarts)
SESSION_FILE = Path("data/sessions.json")
SESSION_FILE.parent.mkdir(exist_ok=True)

# Session TTL (time to live) - sessions expire after 7 days of inactivity
SESSION_TTL_DAYS = 7

# Session storage (loaded from file, persists across restarts)
_sessions: dict[str, dict] = {}

# HTTP Basic Auth security scheme (for simple curl -u username:password)
basic_security = HTTPBasic(auto_error=False)


def _load_sessions() -> None:
    """Load sessions from file on startup"""
    global _sessions
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, 'r') as f:
                loaded_sessions = json.load(f)

                # Clean up expired sessions while loading
                now = datetime.now(timezone.utc)
                _sessions = {}
                expired_count = 0

                for token, session_data in loaded_sessions.items():
                    # Parse expiry time
                    expires_at_str = session_data.get("expires_at")
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)

                        # Only keep sessions that haven't expired
                        if expires_at > now:
                            _sessions[token] = session_data
                        else:
                            expired_count += 1

                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired sessions on startup")
                    _save_sessions()  # Save cleaned sessions

                logger.info(f"Loaded {len(_sessions)} active sessions from {SESSION_FILE}")
        else:
            logger.info("No existing session file found, starting with empty sessions")
            _sessions = {}
    except Exception as e:
        logger.error(f"Failed to load sessions from file: {e}")
        _sessions = {}


def _save_sessions() -> None:
    """Save sessions to file for persistence"""
    try:
        with open(SESSION_FILE, 'w') as f:
            json.dump(_sessions, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save sessions to file: {e}")


def create_session() -> str:
    """Create a new session token with expiry time"""
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)

    _sessions[session_token] = {
        "authenticated": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat()
    }

    _save_sessions()  # Persist to file
    return session_token


def get_session_token(request: Request) -> Optional[str]:
    """Extract session token from request cookies"""
    return request.cookies.get("session_token")


def validate_session(session_token: Optional[str]) -> bool:
    """Validate if session token is valid and not expired"""
    if not session_token:
        return False

    session = _sessions.get(session_token)
    if not session or not session.get("authenticated", False):
        return False

    # Check expiry
    expires_at_str = session.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        now = datetime.now(timezone.utc)

        if expires_at <= now:
            # Session expired, remove it
            logger.info(f"Session expired, removing")
            invalidate_session(session_token)
            return False

        # Session is valid, extend expiry (rolling window)
        new_expiry = now + timedelta(days=SESSION_TTL_DAYS)
        session["expires_at"] = new_expiry.isoformat()
        _save_sessions()  # Persist updated expiry

    return True


def invalidate_session(session_token: Optional[str]):
    """Invalidate a session token"""
    if session_token and session_token in _sessions:
        del _sessions[session_token]
        _save_sessions()  # Persist to file


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


def init_sessions() -> None:
    """Initialize session storage - load from file on startup"""
    _load_sessions()
    logger.info(f"Session storage initialized with {len(_sessions)} active sessions")

