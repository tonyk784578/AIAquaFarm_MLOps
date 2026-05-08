"""Shared FastAPI dependencies — auth, RBAC, service-to-service key."""

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.user import User

_settings = get_settings()

# Optional Bearer extractor — returns None instead of raising 401 when absent.
_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def require_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that restricts access to superusers only."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


async def require_auth_or_service(
    bearer_token: str | None = Depends(_oauth2_optional),
    aq_access: str | None = Cookie(default=None),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Allow either a valid user JWT or the internal service API key.

    Browser clients authenticate via the httpOnly 'aq_access' cookie or a Bearer token.
    Internal services (LangGraph agents) authenticate by sending:
        X-Service-Key: <INTERNAL_API_KEY>
    """
    if _settings.internal_api_key and x_service_key == _settings.internal_api_key:
        return
    # Falls through to JWT validation; raises 401 if neither credential is valid.
    await get_current_user(bearer_token, aq_access, db)
