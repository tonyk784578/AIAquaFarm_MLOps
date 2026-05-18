"""Pydantic response models for the MLOps API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelVersionInfo(BaseModel):
    name: str
    version: str
    stage: str
    run_id: str


class RegisteredModel(BaseModel):
    name: str
    production_version: str | None = None
    staging_version: str | None = None
    versions: list[ModelVersionInfo] = Field(default_factory=list)


class RegistryResponse(BaseModel):
    models: list[RegisteredModel]


class AuditEntry(BaseModel):
    ts: str
    kind: str
    model: str
    data: dict[str, Any]


class AuditResponse(BaseModel):
    events: list[AuditEntry]
    count: int


class DriftFeature(BaseModel):
    feature: str
    psi: float
    kl_divergence: float
    status: str


class DriftReport(BaseModel):
    model_name: str
    max_psi: float
    mean_psi: float
    should_retrain: bool
    n_reference: int
    n_current: int
    features: list[DriftFeature] = Field(default_factory=list)


class DriftResponse(BaseModel):
    reports: dict[str, DriftReport]


class RetrainRequest(BaseModel):
    model: str = Field(description="Registered model name to retrain")
    dry_run: bool = False


class PromoteRequest(BaseModel):
    model: str
    run_id: str
    force: bool = False


class DeployRequest(BaseModel):
    model: str | None = Field(default=None, description="None deploys all models")


class ActionResponse(BaseModel):
    ok: bool
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    mlflow_uri: str
    audit_log_path: str
    audit_events: int
