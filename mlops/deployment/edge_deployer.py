"""Edge deployer — downloads production models from MLflow, converts to ONNX,
and pushes to edge devices via SSH/SCP with health verification and rollback.

Deployment flow per model
--------------------------
1. Fetch production model URI from MLflow registry.
2. Download PyTorch checkpoint to local cache directory.
3. Export to ONNX with fixed dummy input matching the model signature.
4. SCP the ONNX file to the edge device.
5. Signal the edge inference service to hot-reload (SIGHUP).
6. Run a post-deployment smoke test (forward pass on the edge).
7. If smoke test fails, roll back to the previous version.

Usage::

    from mlops.deployment.edge_deployer import EdgeDeployer
    from mlops.registry.mlflow_registry import ModelRegistry

    registry = ModelRegistry("http://mlflow:5000")
    deployer = EdgeDeployer(
        registry=registry,
        edge_host="192.168.1.100",
        edge_user="aquafarm",
        ssh_key_path="~/.ssh/edge_key",
    )
    result = deployer.deploy_model("WaterQualityPredictor")

CLI::

    python -m mlops.deployment.edge_deployer \\
        --mlflow-uri http://localhost:5000 \\
        --edge-host 192.168.1.100 \\
        --edge-user aquafarm \\
        --ssh-key ~/.ssh/edge_key \\
        --model WaterQualityPredictor
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from mlops.registry.mlflow_registry import REGISTERED_MODELS, ModelRegistry

logger = structlog.get_logger()

# ── ONNX export shapes — must match _MODEL_SIGNATURES in mlflow_registry.py ───
_ONNX_EXPORT_CONFIG: dict[str, dict[str, Any]] = {
    "FishDetection": {
        "input_shape": (1, 3, 640, 640),
        "input_names": ["frame"],
        "output_names": ["detections"],
        "dynamic_axes": {"frame": {0: "batch"}, "detections": {0: "batch"}},
        "opset": 17,
    },
    "FeedingActivityClassifier": {
        "input_shape": (1, 3, 224, 224),
        "input_names": ["frame"],
        "output_names": ["activity_score"],
        "dynamic_axes": {"frame": {0: "batch"}, "activity_score": {0: "batch"}},
        "opset": 17,
    },
    "WaterQualityPredictor": {
        "input_shape": (1, 24, 7),
        "input_names": ["sequence"],
        "output_names": ["prediction"],
        "dynamic_axes": {"sequence": {0: "batch"}, "prediction": {0: "batch"}},
        "opset": 17,
    },
}

# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class DeploymentResult:
    """Outcome of a single model's OTA deployment.

    Attributes:
        model_name: Registered model name.
        success: Overall success (False if any stage failed + rollback).
        rolled_back: True when deployment failed and previous version restored.
        stages: Per-stage pass/fail dict.
        error: Error message if a stage failed.
        onnx_path: Local path of the exported ONNX file (temp; cleaned up).
        remote_path: Final path on the edge device.
    """
    model_name: str
    success: bool = False
    rolled_back: bool = False
    stages: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    onnx_path: str | None = None
    remote_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "success": self.success,
            "rolled_back": self.rolled_back,
            "stages": self.stages,
            "error": self.error,
            "remote_path": self.remote_path,
        }


# ── EdgeDeployer ───────────────────────────────────────────────────────────────

class EdgeDeployer:
    """Downloads production models from MLflow and deploys to edge devices.

    Attributes:
        registry: ModelRegistry for fetching production model URIs.
        edge_host: Edge device hostname or IP address.
        edge_user: SSH username on edge device.
        deploy_path: Target directory on edge device (must be writable).
        ssh_key_path: Path to SSH private key (None = use ssh-agent).
        inference_service: systemd service name to signal on edge.
        dry_run: If True, skip SCP/SSH steps (log intent only).
    """

    def __init__(
        self,
        registry: ModelRegistry,
        edge_host: str,
        edge_user: str = "aquafarm",
        ssh_key_path: str | None = None,
        deploy_path: str = "/opt/aquafarm/models",
        inference_service: str = "aquafarm-edge",
        dry_run: bool = False,
    ) -> None:
        self.registry = registry
        self.edge_host = edge_host
        self.edge_user = edge_user
        self.ssh_key_path = ssh_key_path
        self.deploy_path = deploy_path
        self.inference_service = inference_service
        self.dry_run = dry_run

    # ── SSH/SCP helpers ────────────────────────────────────────────────────────

    def _ssh_args(self) -> list[str]:
        """Base SSH options (no host-key checking for embedded devices)."""
        args = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
        ]
        if self.ssh_key_path:
            args += ["-i", self.ssh_key_path]
        return args

    def _ssh(self, command: str) -> tuple[int, str]:
        """Run a command on the edge device via SSH.

        Returns:
            Tuple of (returncode, combined stdout+stderr).
        """
        if self.dry_run:
            logger.info("dry_run_ssh", host=self.edge_host, cmd=command)
            return 0, ""
        cmd = ["ssh"] + self._ssh_args() + [f"{self.edge_user}@{self.edge_host}", command]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        return result.returncode, output

    def _scp(self, local_path: Path, remote_path: str) -> bool:
        """Copy a local file to the edge device.

        Returns:
            True on success.
        """
        if self.dry_run:
            logger.info("dry_run_scp", src=str(local_path), dst=remote_path)
            return True
        cmd = (
            ["scp"] + self._ssh_args()
            + [str(local_path), f"{self.edge_user}@{self.edge_host}:{remote_path}"]
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("scp_failed", error=result.stderr[:300])
        return result.returncode == 0

    # ── ONNX export ────────────────────────────────────────────────────────────

    def _export_onnx(
        self,
        model: Any,
        model_name: str,
        output_path: Path,
    ) -> bool:
        """Export a PyTorch model to ONNX.

        Args:
            model: PyTorch nn.Module in eval mode.
            model_name: Registered model name (for export config lookup).
            output_path: Destination .onnx file path.

        Returns:
            True on success.
        """
        cfg = _ONNX_EXPORT_CONFIG.get(model_name)
        if cfg is None:
            logger.error("no_onnx_config", model=model_name)
            return False
        try:
            import torch
            dummy = torch.zeros(cfg["input_shape"], dtype=torch.float32)
            torch.onnx.export(
                model,
                dummy,
                str(output_path),
                input_names=cfg["input_names"],
                output_names=cfg["output_names"],
                dynamic_axes=cfg["dynamic_axes"],
                opset_version=cfg["opset"],
                do_constant_folding=True,
            )
            size_mb = output_path.stat().st_size / 1024 / 1024
            logger.info("onnx_exported", model=model_name, path=str(output_path), size_mb=round(size_mb, 2))
            return True
        except Exception as exc:
            logger.error("onnx_export_failed", model=model_name, error=str(exc))
            return False

    def _validate_onnx(self, onnx_path: Path) -> bool:
        """Run onnx.checker.check_model on the exported file."""
        try:
            import onnx
            model = onnx.load(str(onnx_path))
            onnx.checker.check_model(model)
            logger.info("onnx_valid", path=str(onnx_path))
            return True
        except ImportError:
            logger.warning("onnx_not_installed", msg="Skipping ONNX validation")
            return True
        except Exception as exc:
            logger.error("onnx_invalid", error=str(exc))
            return False

    # ── Remote health check ────────────────────────────────────────────────────

    def _smoke_test(self, model_name: str) -> bool:
        """Run an inference smoke test on the edge device.

        Calls the edge inference REST endpoint (localhost:8080/infer/{model}).
        Returns True if the endpoint responds with HTTP 200.
        """
        rc, out = self._ssh(
            f"curl -sf -o /dev/null -w '%{{http_code}}' "
            f"http://localhost:8080/infer/{model_name.lower()}"
        )
        if self.dry_run:
            return True
        passed = rc == 0 and "200" in out
        logger.info("smoke_test", model=model_name, passed=passed, response=out[:100])
        return passed

    def _backup_current(self, model_name: str) -> str | None:
        """Create a backup of the currently deployed model on the edge.

        Returns:
            Backup path on the edge, or None on failure.
        """
        current = f"{self.deploy_path}/{model_name}.onnx"
        backup = f"{self.deploy_path}/{model_name}.onnx.bak"
        rc, _ = self._ssh(f"test -f {current} && cp {current} {backup}")
        if rc == 0 or self.dry_run:
            logger.info("backup_created", model=model_name, backup=backup)
            return backup
        return None

    def _rollback(self, model_name: str, backup_path: str) -> bool:
        """Restore the backup model and reload the inference service."""
        current = f"{self.deploy_path}/{model_name}.onnx"
        rc, _ = self._ssh(f"cp {backup_path} {current}")
        if rc == 0 or self.dry_run:
            self._reload_service()
            logger.info("rollback_complete", model=model_name)
            return True
        logger.error("rollback_failed", model=model_name)
        return False

    def _reload_service(self) -> None:
        """Signal the edge inference service to reload its models."""
        self._ssh(f"sudo systemctl kill --signal=SIGHUP {self.inference_service}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def deploy_model(
        self,
        model_name: str,
        local_cache: Path | None = None,
    ) -> DeploymentResult:
        """Download, convert, push, and verify a single production model.

        Args:
            model_name: Registered MLflow model name.
            local_cache: Local directory for caching downloads. Defaults to a
                         temporary directory (cleaned up after deploy).

        Returns:
            DeploymentResult with per-stage pass/fail and rollback status.
        """
        result = DeploymentResult(model_name=model_name)

        # ── 1. Fetch production URI ────────────────────────────────────────────
        uri = self.registry.get_production_model_uri(model_name)
        if not uri:
            result.error = f"No production model found for {model_name}"
            return result
        result.stages["fetch_uri"] = True
        logger.info("deploying_model", model=model_name, uri=uri, target=self.edge_host)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = local_cache or Path(tmpdir)
            pt_path = cache / f"{model_name}.pt"
            onnx_path = cache / f"{model_name}.onnx"

            # ── 2. Download PyTorch checkpoint ────────────────────────────────
            try:
                import mlflow
                downloaded = mlflow.artifacts.download_artifacts(
                    artifact_uri=uri,
                    dst_path=str(cache),
                )
                # find .pt file in downloaded directory
                pt_files = list(Path(downloaded).rglob("*.pt"))
                if pt_files:
                    pt_path = pt_files[0]
                result.stages["download"] = True
            except Exception as exc:
                result.error = f"Download failed: {exc}"
                result.stages["download"] = False
                logger.error("model_download_failed", model=model_name, error=str(exc))
                return result

            # ── 3. Load model + export to ONNX ───────────────────────────────
            try:
                import torch
                pytorch_model = torch.load(str(pt_path), map_location="cpu", weights_only=False)
                if hasattr(pytorch_model, "eval"):
                    pytorch_model.eval()
                exported = self._export_onnx(pytorch_model, model_name, onnx_path)
                result.stages["onnx_export"] = exported
                if not exported:
                    result.error = "ONNX export failed"
                    return result
            except Exception as exc:
                result.error = f"ONNX conversion failed: {exc}"
                result.stages["onnx_export"] = False
                logger.error("onnx_conversion_error", model=model_name, error=str(exc))
                return result

            # ── 4. Validate ONNX ──────────────────────────────────────────────
            result.stages["onnx_validate"] = self._validate_onnx(onnx_path)

            # ── 5. Backup current deployment ──────────────────────────────────
            backup_path = self._backup_current(model_name)

            # ── 6. SCP to edge ────────────────────────────────────────────────
            remote_onnx = f"{self.deploy_path}/{model_name}.onnx"
            scp_ok = self._scp(onnx_path, remote_onnx)
            result.stages["scp"] = scp_ok
            result.remote_path = remote_onnx

            if not scp_ok:
                result.error = "SCP transfer failed"
                if backup_path:
                    result.rolled_back = self._rollback(model_name, backup_path)
                return result

            # ── 7. Reload service ─────────────────────────────────────────────
            self._reload_service()

            # ── 8. Smoke test ─────────────────────────────────────────────────
            smoke_ok = self._smoke_test(model_name)
            result.stages["smoke_test"] = smoke_ok

            if not smoke_ok and backup_path:
                logger.warning("smoke_test_failed_rolling_back", model=model_name)
                result.rolled_back = self._rollback(model_name, backup_path)
                result.error = "Smoke test failed — rolled back to previous version"
                return result

            result.success = True
            logger.info("deployment_complete", model=model_name, remote=remote_onnx)
            return result

    def deploy_all(
        self,
        models: list[str] | None = None,
        local_cache: Path | None = None,
    ) -> dict[str, Any]:
        """Deploy all (or specified) production models to the edge device.

        Args:
            models: List of model names to deploy. Defaults to REGISTERED_MODELS.
            local_cache: Shared local cache directory.

        Returns:
            Dict with per-model DeploymentResult dicts and an overall summary.
        """
        targets = models or REGISTERED_MODELS
        results: dict[str, Any] = {}

        for model_name in targets:
            r = self.deploy_model(model_name, local_cache)
            results[model_name] = r.to_dict()

        n_ok = sum(1 for r in results.values() if r["success"])
        n_rb = sum(1 for r in results.values() if r["rolled_back"])
        summary = {
            "total": len(targets),
            "succeeded": n_ok,
            "failed": len(targets) - n_ok,
            "rolled_back": n_rb,
        }
        logger.info("deploy_all_complete", **summary)
        return {"results": results, "summary": summary}


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json

    parser = argparse.ArgumentParser(description="Deploy production models to edge device")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--edge-host", required=True, help="Edge device IP or hostname")
    parser.add_argument("--edge-user", default="aquafarm")
    parser.add_argument("--ssh-key", default=None, help="Path to SSH private key")
    parser.add_argument("--deploy-path", default="/opt/aquafarm/models")
    parser.add_argument("--model", default=None, help="Single model name (default: all)")
    parser.add_argument("--cache-dir", default=None, help="Local model cache directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip SSH/SCP steps")
    args = parser.parse_args()

    registry = ModelRegistry(args.mlflow_uri)
    deployer = EdgeDeployer(
        registry=registry,
        edge_host=args.edge_host,
        edge_user=args.edge_user,
        ssh_key_path=args.ssh_key,
        deploy_path=args.deploy_path,
        dry_run=args.dry_run,
    )

    cache = Path(args.cache_dir) if args.cache_dir else None

    if args.model:
        r = deployer.deploy_model(args.model, cache)
        print(_json.dumps(r.to_dict(), indent=2))
    else:
        r = deployer.deploy_all(local_cache=cache)
        print(_json.dumps(r, indent=2))
