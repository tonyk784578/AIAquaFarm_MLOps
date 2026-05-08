"""Extended API integration tests.

Covers:
  - Auth: login, refresh, /me, register, 401/403 cases
  - Alert lifecycle: create → list → resolve
  - Admin RBAC: superuser-only routes return 403 for regular users
  - Monitoring: /tanks, /feeding/latest (mocked DB)

All tests use an in-process SQLite database so no Docker stack is required.
Redis is stubbed out with a simple mock to avoid network dependency.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import create_app
from app.models.alert import Alert
from app.models.user import User

# ── In-memory SQLite engine ────────────────────────────────────────────────────

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(_TEST_DB_URL, echo=False)
_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def _create_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_tables() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
async def db_tables() -> AsyncGenerator[None, None]:
    await _create_tables()
    yield
    await _drop_tables()


@pytest.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _Session() as session:
        yield session
        await session.rollback()


@pytest.fixture()
def mock_redis() -> MagicMock:
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    return redis


@pytest.fixture()
async def app_client(db: AsyncSession, mock_redis: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with DB and Redis overrides injected."""
    from app.db.redis import get_redis

    test_app = create_app()

    # Override DB dependency
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    # Override Redis dependency
    async def override_get_redis() -> AsyncGenerator[MagicMock, None]:
        yield mock_redis

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client

    test_app.dependency_overrides.clear()


@pytest.fixture()
async def regular_user(db: AsyncSession) -> User:
    user = User(
        username="testuser",
        email="testuser@example.com",
        hashed_password=hash_password("password123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.fixture()
async def superuser(db: AsyncSession) -> User:
    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("adminpass123"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.fixture()
def user_token(regular_user: User) -> str:
    return create_access_token(regular_user.username)


@pytest.fixture()
def superuser_token(superuser: User) -> str:
    return create_access_token(superuser.username)


@pytest.fixture()
def auth_headers(user_token: str) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture()
def superuser_headers(superuser_token: str) -> dict:
    return {"Authorization": f"Bearer {superuser_token}"}


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _make_alert(
    db: AsyncSession,
    tank_id: str = "TANK-01",
    severity: str = "warning",
    is_active: bool = True,
) -> Alert:
    alert = Alert(
        tank_id=tank_id,
        severity=severity,
        category="water_quality",
        title="Test alert",
        message="pH out of range",
        is_active=is_active,
        created_at=datetime.now(tz=UTC),
        source="system",
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


# ── Auth tests ─────────────────────────────────────────────────────────────────

class TestAuth:
    async def test_login_success(
        self, app_client: AsyncClient, regular_user: User
    ) -> None:
        resp = await app_client.post(
            "/api/v1/auth/login",
            data={"username": "testuser", "password": "password123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(
        self, app_client: AsyncClient, regular_user: User
    ) -> None:
        resp = await app_client.post(
            "/api/v1/auth/login",
            data={"username": "testuser", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_user(self, app_client: AsyncClient) -> None:
        resp = await app_client.post(
            "/api/v1/auth/login",
            data={"username": "ghost", "password": "nopass"},
        )
        assert resp.status_code == 401

    async def test_me_returns_profile(
        self, app_client: AsyncClient, regular_user: User, auth_headers: dict
    ) -> None:
        resp = await app_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert body["is_superuser"] is False

    async def test_me_without_token_returns_401(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_with_invalid_token_returns_401(
        self, app_client: AsyncClient
    ) -> None:
        resp = await app_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401

    async def test_logout_returns_200(self, app_client: AsyncClient) -> None:
        resp = await app_client.post("/api/v1/auth/logout")
        assert resp.status_code == 200

    async def test_refresh_token(
        self, app_client: AsyncClient, regular_user: User
    ) -> None:
        from app.core.security import create_refresh_token

        refresh = create_refresh_token(regular_user.username)
        resp = await app_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_with_access_token_rejected(
        self, app_client: AsyncClient, user_token: str
    ) -> None:
        resp = await app_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": user_token}
        )
        assert resp.status_code == 401

    async def test_register_creates_user(self, app_client: AsyncClient) -> None:
        resp = await app_client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "securepass1",
                "full_name": "New User",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "newuser"
        assert body["is_active"] is True

    async def test_register_duplicate_username_returns_409(
        self, app_client: AsyncClient, regular_user: User
    ) -> None:
        resp = await app_client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "other@example.com",
                "password": "securepass2",
            },
        )
        assert resp.status_code == 409


# ── Alert lifecycle tests ──────────────────────────────────────────────────────

class TestAlertLifecycle:
    async def test_create_alert(
        self, app_client: AsyncClient, mock_redis: MagicMock
    ) -> None:
        resp = await app_client.post(
            "/api/v1/alerts/",
            json={
                "tank_id": "TANK-01",
                "severity": "critical",
                "category": "water_quality",
                "title": "High ammonia",
                "message": "Ammonia exceeded 2.0 mg/L",
                "source": "water_quality_ai",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["tank_id"] == "TANK-01"
        assert body["severity"] == "critical"
        assert body["is_active"] is True

    async def test_create_alert_publishes_to_redis(
        self, app_client: AsyncClient, mock_redis: MagicMock
    ) -> None:
        mock_redis.publish.reset_mock()
        await app_client.post(
            "/api/v1/alerts/",
            json={
                "tank_id": "TANK-02",
                "severity": "warning",
                "category": "feeding",
                "title": "Low activity",
                "message": "Feeding activity score below threshold",
                "source": "feeding_ai",
            },
        )
        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args.args
        assert channel == "events:alerts"
        data = json.loads(payload)
        assert data["type"] == "alert"
        assert data["tank_id"] == "TANK-02"
        assert "data" in data

    async def test_list_alerts_active_only(
        self, app_client: AsyncClient, db: AsyncSession
    ) -> None:
        await _make_alert(db, tank_id="TANK-LIST-01", is_active=True)
        await _make_alert(db, tank_id="TANK-LIST-01", is_active=False)

        resp = await app_client.get(
            "/api/v1/alerts/", params={"tank_id": "TANK-LIST-01", "active_only": True}
        )
        assert resp.status_code == 200
        alerts = resp.json()
        assert all(a["is_active"] for a in alerts)
        assert len(alerts) == 1

    async def test_list_alerts_all(
        self, app_client: AsyncClient, db: AsyncSession
    ) -> None:
        await _make_alert(db, tank_id="TANK-LIST-02", is_active=True)
        await _make_alert(db, tank_id="TANK-LIST-02", is_active=False)

        resp = await app_client.get(
            "/api/v1/alerts/",
            params={"tank_id": "TANK-LIST-02", "active_only": False},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_resolve_alert(
        self, app_client: AsyncClient, db: AsyncSession
    ) -> None:
        alert = await _make_alert(db, tank_id="TANK-RESOLVE")
        resp = await app_client.patch(
            f"/api/v1/alerts/{alert.id}/resolve",
            json={"resolution_notes": "Fixed manually", "resolved_by": "operator"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False
        assert body["resolution_notes"] == "Fixed manually"
        assert body["resolved_by"] == "operator"
        assert body["resolved_at"] is not None

    async def test_resolve_nonexistent_alert_returns_404(
        self, app_client: AsyncClient
    ) -> None:
        resp = await app_client.patch(
            "/api/v1/alerts/999999/resolve",
            json={"resolution_notes": "N/A"},
        )
        assert resp.status_code == 404


# ── Admin RBAC tests ───────────────────────────────────────────────────────────

class TestAdminRBAC:
    async def test_list_users_requires_superuser(
        self, app_client: AsyncClient, auth_headers: dict
    ) -> None:
        resp = await app_client.get("/api/v1/admin/users", headers=auth_headers)
        assert resp.status_code == 403

    async def test_list_users_unauthenticated_returns_401(
        self, app_client: AsyncClient
    ) -> None:
        resp = await app_client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    async def test_superuser_can_list_users(
        self,
        app_client: AsyncClient,
        superuser_headers: dict,
        superuser: User,
    ) -> None:
        resp = await app_client.get("/api/v1/admin/users", headers=superuser_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_user_requires_superuser(
        self, app_client: AsyncClient, auth_headers: dict
    ) -> None:
        resp = await app_client.post(
            "/api/v1/admin/users",
            json={
                "username": "shouldfail",
                "email": "fail@example.com",
                "password": "pass1234",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_superuser_can_create_user(
        self, app_client: AsyncClient, superuser_headers: dict, superuser: User
    ) -> None:
        resp = await app_client.post(
            "/api/v1/admin/users",
            json={
                "username": "adminmade",
                "email": "adminmade@example.com",
                "password": "securepass9",
                "is_superuser": False,
            },
            headers=superuser_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "adminmade"

    async def test_update_user_requires_superuser(
        self, app_client: AsyncClient, auth_headers: dict, regular_user: User
    ) -> None:
        resp = await app_client.patch(
            f"/api/v1/admin/users/{regular_user.id}",
            json={"full_name": "Hacked"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_superuser_can_deactivate_user(
        self,
        app_client: AsyncClient,
        superuser_headers: dict,
        superuser: User,
        db: AsyncSession,
    ) -> None:
        # Create a target user to deactivate
        target = User(
            username="tobedeleted",
            email="tobedeleted@example.com",
            hashed_password=hash_password("pass1234"),
            is_active=True,
            is_superuser=False,
        )
        db.add(target)
        await db.flush()
        await db.refresh(target)

        resp = await app_client.delete(
            f"/api/v1/admin/users/{target.id}", headers=superuser_headers
        )
        assert resp.status_code == 204

    async def test_superuser_cannot_deactivate_self(
        self,
        app_client: AsyncClient,
        superuser_headers: dict,
        superuser: User,
    ) -> None:
        resp = await app_client.delete(
            f"/api/v1/admin/users/{superuser.id}", headers=superuser_headers
        )
        assert resp.status_code == 400


# ── Monitoring endpoint tests ──────────────────────────────────────────────────

class TestMonitoringEndpoints:
    async def test_list_tanks_returns_list(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/v1/dashboard/tanks")
        assert resp.status_code == 200
        tanks = resp.json()
        assert isinstance(tanks, list)
        assert len(tanks) > 0
        first = tanks[0]
        assert "tank_id" in first
        assert "name" in first
        assert "status" in first

    async def test_list_tanks_all_online(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/v1/dashboard/tanks")
        tanks = resp.json()
        assert all(t["status"] == "online" for t in tanks)

    async def test_feeding_latest_empty(self, app_client: AsyncClient) -> None:
        resp = await app_client.get(
            "/api/v1/monitoring/feeding/latest",
            params={"tank_id": "TANK-EMPTY-99"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_alerts_list_returns_json(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/api/v1/alerts/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
