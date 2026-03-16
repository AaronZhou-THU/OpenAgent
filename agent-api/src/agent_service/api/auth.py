"""Google OAuth authentication — optional, enabled when GOOGLE_CLIENT_ID is set."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth")

_google_client_id: str | None = None

security = HTTPBearer(auto_error=False)


def set_google_client_id(client_id: str) -> None:
    global _google_client_id
    _google_client_id = client_id or None


def is_auth_enabled() -> bool:
    return bool(_google_client_id)


def _verify_google_token_sync(token: str) -> dict[str, Any]:
    """Verify a Google ID token and return the decoded payload."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    payload = id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        _google_client_id,
    )
    return payload


async def verify_google_token(token: str) -> dict[str, Any]:
    """Verify a Google ID token (runs sync verification in thread)."""
    import asyncio

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _verify_google_token_sync, token)
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any] | None:
    """Dependency: extract and verify Google ID token from Authorization header.

    Returns None if auth is disabled.
    Raises 401 if auth is enabled but token is missing/invalid.
    """
    if not is_auth_enabled():
        return None

    if not credentials:
        raise HTTPException(401, "Not authenticated")

    return await verify_google_token(credentials.credentials)


async def verify_ws_token(token: str | None) -> dict[str, Any] | None:
    """Verify token for WebSocket connections.

    Returns None if auth is disabled.
    Raises ValueError if auth is enabled but token is missing/invalid.
    """
    if not is_auth_enabled():
        return None

    if not token:
        raise ValueError("Not authenticated")

    try:
        return await verify_google_token(token)
    except HTTPException as e:
        raise ValueError(str(e.detail))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@auth_router.get("/config")
async def auth_config():
    """Returns auth configuration for the frontend."""
    return {
        "enabled": is_auth_enabled(),
        "google_client_id": _google_client_id if is_auth_enabled() else None,
    }


@auth_router.get("/me")
async def get_me(user: dict | None = Depends(get_current_user)):
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
    }
