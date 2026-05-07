"""Basic API integration tests.

Tests use httpx.AsyncClient with the FastAPI test transport so no
live server or database is required for the smoke tests below.

TODO (Phase 1): Add pytest fixtures for a real test DB (PostgreSQL in Docker).
TODO (Phase 2): Add parametrised tests for all monitoring endpoints.
TODO (Phase 3): Add alert lifecycle tests (create → resolve).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestHealthCheck:
    """Smoke tests for the health-check endpoint."""

    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_body(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "aquafarm-backend"
        assert "version" in body


class TestOpenAPISpec:
    """Verify the auto-generated OpenAPI schema is accessible."""

    async def test_openapi_json(self, client: AsyncClient) -> None:
        response = await client.get("/api/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "AIAquafarm API"

    async def test_docs_endpoint(self, client: AsyncClient) -> None:
        response = await client.get("/api/docs")
        assert response.status_code == 200


class TestDashboardAPI:
    """Dashboard endpoint tests — requires DB; skipped without fixture.

    TODO (Phase 1): Add DB fixture and implement these tests.
    """

    @pytest.mark.skip(reason="Requires DB fixture — implement in Phase 1")
    async def test_dashboard_summary(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/dashboard/summary")
        assert response.status_code == 200
        body = response.json()
        assert "water_quality" in body
        assert "fish_growth" in body
        assert "active_alert_count" in body

    async def test_list_tanks(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/dashboard/tanks")
        assert response.status_code == 200
        tanks = response.json()
        assert isinstance(tanks, list)
