"""Authentication: register, login (strictly rate-limited), token refresh
rotation via HTTP-only cookie, logout, and current-user introspection."""
from __future__ import annotations

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, \
    status
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.middleware.security import limiter
from app.models import (Envelope, LoginRequest, RefreshTokenRecord,
                        TokenPair, UserCreate, UserOut, fail, ok)
from app.utils.logger import get_logger
from app.utils.security import (create_access_token, create_refresh_token,
                                decode_token, get_current_user,
                                hash_password, sha256_of, verify_password)

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "orion_refresh"


def _cookie_kwargs() -> dict:
    from app.config import get_settings
    # Secure stays on by default; disable only for local HTTP development.
    return {"httponly": True, "secure": get_settings().cookie_secure,
            "samesite": "strict", "path": "/api/auth"}


def _issue_pair(response: Response, user) -> Envelope:
    access, _exp = create_access_token(user.id)
    refresh, jti, expires = create_refresh_token(user.id)
    with SessionLocal() as db:
        db.add(RefreshTokenRecord(jti=jti, user_id=user.id,
                                  token_hash=sha256_of(refresh),
                                  expires_at=expires))
        db.commit()
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=7 * 24 * 3600,
                        **_cookie_kwargs())
    return ok(TokenPair(access_token=access,
                        expires_in=15 * 60).model_dump())


@router.post("/register", response_model=None)
def register(payload: UserCreate, response: Response):
    from app.models import User
    try:
        with SessionLocal() as db:
            if db.query(User).filter_by(email=payload.email.lower()).first():
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "Email already registered")
            if db.query(User).filter_by(
                    username=payload.username).first():
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "Username already taken")
            user = User(email=payload.email.lower(),
                        username=payload.username,
                        hashed_password=hash_password(payload.password))
            db.add(user)
            db.commit()
            db.refresh(user)
            log.info("user_registered", user_id=user.id)
            return _issue_pair(response, user)
    except HTTPException:
        raise
    except SQLAlchemyError:
        log.exception("register_db_error")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "An internal error occurred") from None


@router.post("/login", response_model=None)
@limiter.limit("5/minute;30/hour")
def login(request: Request, payload: LoginRequest, response: Response):
    from app.models import User
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=payload.email.lower()).first()
        if user is None or not verify_password(payload.password,
                                               user.hashed_password):
            # Uniform message + timing-safe-ish behaviour: no user enumeration.
            log.warning("login_failed", email_domain=payload.email.split(
                "@")[-1])
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Invalid email or password")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Account disabled")
        log.info("login_success", user_id=user.id)
        return _issue_pair(response, user)


@router.post("/refresh", response_model=None)
def refresh(request: Request, response: Response):
    from app.models import User
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return fail("Missing refresh token")
    with SessionLocal() as db:
        record = db.query(RefreshTokenRecord).filter_by(
            token_hash=sha256_of(token), revoked=False).first()
        if record is None:
            return fail("Invalid refresh token")
        try:
            claims = decode_token(token)
        except pyjwt.InvalidTokenError:
            record.revoked = True
            db.commit()
            return fail("Expired refresh token")
        if claims.get("jti") != record.jti or claims.get("type") != "refresh":
            return fail("Invalid refresh token")
        record.revoked = True  # rotation: single-use refresh tokens
        user = db.get(User, record.user_id)
        if user is None or not user.is_active:
            return fail("Account unavailable")
        db.commit()
        return _issue_pair(response, user)


@router.post("/logout", response_model=None)
def logout(response: Response, user=Depends(get_current_user)):
    with SessionLocal() as db:
        for rec in db.query(RefreshTokenRecord).filter_by(
                user_id=user.id, revoked=False).all():
            rec.revoked = True
        db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return ok({"logged_out": True})


@router.get("/me", response_model=None)
def me(user=Depends(get_current_user)):
    return ok(UserOut.model_validate(user).model_dump(mode="json"))
