"""
Supabase JWT verification for FastAPI.
Extracts user_id from the Supabase access token sent as Bearer header.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from app.config import settings

_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    """Verify and decode a Supabase JWT."""
    return jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — returns the decoded JWT payload.
    Raises 401 if missing/invalid.
    Key fields: sub (user id), email, user_metadata.
    """
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = _decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return payload


async def optional_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict | None:
    """Same as get_current_user but returns None instead of 401."""
    if not creds:
        return None
    try:
        return _decode_token(creds.credentials)
    except JWTError:
        return None
