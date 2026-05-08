"""Authentication endpoints.

Routes
------
POST /api/v1/auth/login        — username+password → access+refresh tokens (+ httpOnly cookies)
POST /api/v1/auth/refresh      — refresh token (cookie or body) → new tokens
POST /api/v1/auth/logout       — clears httpOnly auth cookies
GET  /api/v1/auth/me           — returns current user profile
POST /api/v1/auth/register     — create a new user (disabled by default; set REGISTRATION_OPEN=true)
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User

router = APIRouter()
settings = get_settings()

# auto_error=False so the dependency returns None instead of 401 when no Bearer is present —
# allows falling back to the httpOnly cookie path.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Schemas ────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(default="")


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """Write access and refresh tokens as httpOnly, SameSite=Lax cookies."""
    common = dict(httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite)
    response.set_cookie(
        key="aq_access",
        value=access,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        **common,
    )
    # Refresh token cookie is scoped to the /api/v1/auth path to limit exposure.
    response.set_cookie(
        key="aq_refresh",
        value=refresh,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/v1/auth",
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("aq_access", path="/")
    response.delete_cookie("aq_refresh", path="/api/v1/auth")


# ── Dependencies ───────────────────────────────────────────────────────────────

async def get_current_user(
    bearer_token: str | None = Depends(oauth2_scheme),
    aq_access: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: authenticates via Bearer token OR httpOnly cookie."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = bearer_token or aq_access
    if not token:
        raise credentials_exc
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exc
        username: str = payload.get("sub", "")
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username + password.

    Returns JWT tokens in the response body AND sets httpOnly cookies.
    Rate-limited to 10 attempts per minute per IP.
    """
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    # Constant-time failure: always verify even when user is None to prevent timing attacks.
    dummy_hash = "$2b$12$invalidhashplaceholder000000000000000000000000000000000000"
    password_ok = verify_password(form.password, user.hashed_password if user else dummy_hash)

    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access = create_access_token(user.username)
    refresh = create_refresh_token(user.username)
    _set_auth_cookies(response, access, refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    body: RefreshRequest | None = None,
    aq_refresh: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    Accepts the refresh token from the httpOnly cookie (browser flow) or the
    request body (API client flow).
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    token = (body.refresh_token if body else None) or aq_refresh
    if not token:
        raise credentials_exc
    try:
        payload = decode_refresh_token(token)
        if payload.get("type") != "refresh":
            raise credentials_exc
        username: str = payload.get("sub", "")
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exc

    access = create_access_token(user.username)
    new_refresh = create_refresh_token(user.username)
    _set_auth_cookies(response, access, new_refresh)
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear server-side auth cookies and instruct the client to discard tokens."""
    _clear_auth_cookies(response)
    return {"detail": "logged_out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user account.

    Disabled by default (returns 403). Enable by setting REGISTRATION_OPEN=true in the
    environment (for initial bootstrap only — disable again once the first superuser exists).
    """
    if not settings.registration_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled. Contact an administrator.",
        )

    existing = await db.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already registered")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
