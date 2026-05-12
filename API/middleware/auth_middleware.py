"""Auth middleware — FastAPI dependencies for JWT-protected routes."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from utils.jwt_helper import decode_token

security = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(creds.credentials)
        return {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "role": payload.get("role"),
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_roles(*roles: str):
    """Dependency factory: ensures user has one of the given roles."""
    def _inner(user: dict = Depends(get_current_user)) -> dict:
        if roles and user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _inner
