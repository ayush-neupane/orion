"""JWT issuance/verification and password hashing.

- Access tokens: 15 min, bearer header.
- Refresh tokens: random JTI, stored hashed server-side, revocable.
- Passwords: bcrypt with per-call salt. (passlib is intentionally avoided:
  it is unmaintained and breaks against bcrypt>=4.1.)
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

settings = get_settings()
_bearer = HTTPBearer(auto_error=False)

ALG = settings.algorithm


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "type": "access",
               "exp": expires, "iat": datetime.now(timezone.utc)}
    token = jwt.encode(payload, settings.secret_key, algorithm=ALG)
    return token, expires


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The raw refresh JWT embeds a JTI so
    the server can revoke individual sessions."""
    jti = uuid.uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days)
    payload = {"sub": str(user_id), "type": "refresh", "jti": jti,
               "exp": expires, "iat": datetime.now(timezone.utc)}
    token = jwt.encode(payload, settings.secret_key, algorithm=ALG)
    return token, jti, expires


def sha256_of(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def decode_token(token: str) -> dict:
    """Raises jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALG])


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    from app.database import SessionLocal
    from app.models import User

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Not authenticated")
    try:
        claims = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Invalid token") from exc
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    user_id = int(claims.get("sub", 0))
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "User not found or inactive")
        return user
