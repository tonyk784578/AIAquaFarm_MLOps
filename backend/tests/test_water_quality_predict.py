"""Integration tests for POST /api/v1/water-quality/predict and related endpoints.

Tests use a mock WaterQualityInferenceEngine injected via app.state so no
real database or MLflow server is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from ai_modules.water_quality.model import N_FEATURES, SEQ_LEN
from ai_modules.water_quality.schemas import (
    ForecastPoint,
    ForecastResponse,
    ModelStatusResponse,
    PredictResponse,
)
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.water_quality_service import WaterQualityInferenceEngine

# ── Fixtures ───────────────────────────────────────────────────────────────────

def _mock_engine() -> MagicMock:
    """Return a mock WaterQualityInferenceEngine with is_ready=True."""
    engine = MagicMock(spec=WaterQualityInferenceEngine)
    engine.is_ready = True
    engine.status.return_value = ModelStatusResponse(
        is_loaded=True,
        model_version="test-v1",
        architecture="lstm",
        device="cpu",
        scaler_fitted=True,
        mlflow_uri="mock://",
    )
    return engine


def _mock_predict_response(tank_id: str = "TANK-01") -> PredictResponse:
    now = datetime.now(UTC)
    return PredictResponse(
        tank_id=tank_id,
        predicted_at=now,
        ammonia_ppm=0.12,
        nitrite_ppm=0.03,
        ammonia_confidence=0.91,
        nitrite_confidence=0.88,
        ammonia_ci_lower=0.08,
        ammonia_ci_upper=0.16,
        nitrite_ci_lower=0.02,
        nitrite_ci_upper=0.04,
        ammonia_alert=False,
        nitrite_alert=False,
        model_version="test-v1",
        window_hours=SEQ_LEN,
    )


@pytest.fixture()
def client():
    """TestClient with a mocked inference engine on app.state."""
    application = create_app()
    engine = _mock_engine()
    application.state.wq_engine = engine

    with TestClient(application, raise_server_exceptions=False) as c:
        c.app_state_engine = engine
        yield c


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPredictEndpoint:
    def test_predict_success(self, client: TestClient) -> None:
        """Successful prediction returns 200 with all expected fields."""
        expected = _mock_predict_response()

        with patch(
            "app.services.water_quality_service.WaterQualityService.predict_and_save",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            response = client.post(
                "/api/v1/water-quality/predict",
                json={"tank_id": "TANK-01"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["tank_id"] == "TANK-01"
        assert "ammonia_ppm" in data
        assert "nitrite_ppm" in data
        assert "ammonia_ci_lower" in data
        assert "ammonia_ci_upper" in data
        assert "nitrite_ci_lower" in data
        assert "nitrite_ci_upper" in data
        assert "ammonia_alert" in data
        assert "model_version" in data

    def test_predict_custom_mc_samples(self, client: TestClient) -> None:
        """mc_samples field is accepted and forwarded."""
        expected = _mock_predict_response()

        with patch(
            "app.services.water_quality_service.WaterQualityService.predict_and_save",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_save:
            response = client.post(
                "/api/v1/water-quality/predict",
                json={"tank_id": "TANK-01", "mc_samples": 10},
            )
            mock_save.assert_awaited_once_with("TANK-01", mc_samples=10)

        assert response.status_code == 200

    def test_predict_missing_tank_data_returns_422(self, client: TestClient) -> None:
        """ValueError from service maps to 422."""
        with patch(
            "app.services.water_quality_service.WaterQualityService.predict_and_save",
            new_callable=AsyncMock,
            side_effect=ValueError("No data found for tank 'TANK-99'"),
        ):
            response = client.post(
                "/api/v1/water-quality/predict",
                json={"tank_id": "TANK-99"},
            )

        assert response.status_code == 422
        assert "TANK-99" in response.json()["detail"]

    def test_predict_invalid_mc_samples_rejected(self, client: TestClient) -> None:
        """mc_samples out of range [1, 200] returns 422."""
        response = client.post(
            "/api/v1/water-quality/predict",
            json={"tank_id": "TANK-01", "mc_samples": 0},
        )
        assert response.status_code == 422

    def test_predict_engine_not_initialised(self) -> None:
        """Missing engine on app.state returns 503."""
        app = create_app()
        # Do NOT set app.state.wq_engine
        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.post(
                "/api/v1/water-quality/predict",
                json={"tank_id": "TANK-01"},
            )
        assert response.status_code == 503


class TestForecastEndpoint:
    def test_forecast_returns_6_points(self, client: TestClient) -> None:
        """Forecast endpoint returns exactly 6 hourly ForecastPoints."""
        now = datetime.now(UTC)
        forecast = ForecastResponse(
            tank_id="TANK-01",
            generated_at=now,
            horizon_hours=6,
            forecast=[
                ForecastPoint(
                    timestamp=now,
                    ammonia_ppm=0.1,
                    nitrite_ppm=0.02,
                    ammonia_confidence=0.9,
                    nitrite_confidence=0.85,
                )
                for _ in range(6)
            ],
            model_version="test-v1",
        )
        with patch(
            "app.services.water_quality_service.WaterQualityService.get_6h_forecast",
            new_callable=AsyncMock,
            return_value=forecast,
        ):
            response = client.get("/api/v1/water-quality/forecast/TANK-01")

        assert response.status_code == 200
        data = response.json()
        assert data["tank_id"] == "TANK-01"
        assert data["horizon_hours"] == 6
        assert len(data["forecast"]) == 6

    def test_forecast_missing_data_returns_422(self, client: TestClient) -> None:
        with patch(
            "app.services.water_quality_service.WaterQualityService.get_6h_forecast",
            new_callable=AsyncMock,
            side_effect=ValueError("Insufficient history"),
        ):
            response = client.get("/api/v1/water-quality/forecast/TANK-99")

        assert response.status_code == 422


class TestModelStatusEndpoint:
    def test_model_status_returns_engine_info(self, client: TestClient) -> None:
        response = client.get("/api/v1/water-quality/model-status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_loaded"] is True
        assert data["model_version"] == "test-v1"
        assert data["architecture"] == "lstm"
        assert data["scaler_fitted"] is True


# ── Unit tests for service ────────────────────────────────────────────────────

class TestWaterQualityServiceFetchWindow:
    """Verify feature window assembly from TimescaleDB query results."""

    @pytest.mark.asyncio
    async def test_fetch_window_insufficient_rows(self) -> None:
        """ValueError raised when TimescaleDB returns fewer than SEQ_LEN rows."""
        from app.services.water_quality_service import WaterQualityService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = _mock_engine()
        service = WaterQualityService(mock_db, engine)

        with pytest.raises(ValueError, match="No data found"):
            await service.fetch_feature_window("TANK-01")

    @pytest.mark.asyncio
    async def test_fetch_window_returns_correct_shape(self) -> None:
        """Properly imputed window returns (SEQ_LEN, N_FEATURES) array."""
        import pandas as pd

        from app.services.water_quality_service import WaterQualityService

        timestamps = pd.date_range("2024-01-01", periods=SEQ_LEN, freq="h")
        rows = [
            {
                "bucket": ts,
                "temperature_c": 23.0,
                "ph": 7.2,
                "dissolved_oxygen_mgl": 7.8,
                "turbidity_ntu": 1.5,
                "conductivity_us_cm": 800.0,
                "feeding_amount_kg_24h": 0.5,
                "biomass_kg": 120.0,
                "water_exchange_rate_pct": 5.0,
            }
            for ts in timestamps
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        engine = _mock_engine()
        service = WaterQualityService(mock_db, engine)

        window = await service.fetch_feature_window("TANK-01")
        assert window.shape == (SEQ_LEN, N_FEATURES)
        assert window.dtype == np.float32
