"""Data lake storage client — S3-compatible object storage (MinIO / AWS S3).

Provides a unified interface for reading and writing raw data
(camera frames, sensor CSVs, labelled datasets) to an S3 bucket
regardless of whether the backend is local MinIO or cloud S3.

Partition scheme:  s3://{bucket}/raw/{type}/{tank_id}/{date}/
    type: 'camera' | 'sensor' | 'labelled'
    date: YYYY-MM-DD
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


class DataLakeStorage:
    """S3-compatible storage client for the AIAquafarm data lake.

    Attributes:
        bucket: S3 bucket name.
        endpoint_url: Custom endpoint for MinIO (None for AWS).
        _client: boto3 S3 client (initialised lazily on first use).
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._client: Optional[object] = None

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Initialise boto3 S3 client.

        Raises:
            ImportError: If boto3 is not installed.
            botocore.exceptions.ClientError: If credentials are invalid.
        """
        import boto3

        kwargs: dict = {"region_name": self._region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key

        self._client = boto3.client("s3", **kwargs)
        self._ensure_bucket()
        logger.info("data_lake_connected", bucket=self.bucket, endpoint=self.endpoint_url)

    def _ensure_bucket(self) -> None:
        """Create the bucket if it does not exist (idempotent)."""
        import botocore.exceptions

        try:
            self._client.head_bucket(Bucket=self.bucket)  # type: ignore[union-attr]
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=self.bucket)  # type: ignore[union-attr]
                logger.info("bucket_created", bucket=self.bucket)
            else:
                raise

    @property
    def client(self):  # type: ignore[return]
        """Return initialised boto3 client; calls connect() if needed."""
        if self._client is None:
            self.connect()
        return self._client

    # ── Key helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def camera_key(tank_id: str, filename: str, dt: Optional[date] = None) -> str:
        """Build the S3 key for a camera frame."""
        day = (dt or date.today()).isoformat()
        return f"raw/camera/{tank_id}/{day}/{filename}"

    @staticmethod
    def sensor_key(tank_id: str, filename: str, dt: Optional[date] = None) -> str:
        """Build the S3 key for a sensor data file."""
        day = (dt or date.today()).isoformat()
        return f"raw/sensor/{tank_id}/{day}/{filename}"

    @staticmethod
    def model_artifact_key(model_name: str, version: str, filename: str) -> str:
        """Build the S3 key for a model artifact."""
        return f"models/{model_name}/{version}/{filename}"

    # ── Upload / download ──────────────────────────────────────────────────────

    def upload_file(self, local_path: Path, s3_key: str) -> str:
        """Upload a local file to the data lake.

        Args:
            local_path: Local file path.
            s3_key: Destination key in S3.

        Returns:
            S3 URI of the uploaded file.
        """
        self.client.upload_file(str(local_path), self.bucket, s3_key)
        uri = f"s3://{self.bucket}/{s3_key}"
        logger.debug("file_uploaded", uri=uri)
        return uri

    def upload_bytes(
        self,
        data: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload in-memory bytes to the data lake.

        Args:
            data: Raw bytes to upload.
            s3_key: Destination key.
            content_type: MIME type.

        Returns:
            S3 URI.
        """
        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=io.BytesIO(data),
            ContentType=content_type,
        )
        uri = f"s3://{self.bucket}/{s3_key}"
        logger.debug("bytes_uploaded", uri=uri, size=len(data))
        return uri

    def download_file(self, s3_key: str, local_path: Path) -> Path:
        """Download a file from the data lake.

        Args:
            s3_key: Source key in S3.
            local_path: Destination local path.

        Returns:
            Local path of the downloaded file.
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, s3_key, str(local_path))
        logger.debug("file_downloaded", s3_key=s3_key, local=str(local_path))
        return local_path

    def download_bytes(self, s3_key: str) -> bytes:
        """Download an object from the data lake as bytes.

        Args:
            s3_key: Source key in S3.

        Returns:
            Raw bytes of the object.
        """
        obj = self.client.get_object(Bucket=self.bucket, Key=s3_key)
        return obj["Body"].read()

    def list_objects(self, prefix: str) -> list[str]:
        """List all object keys under a prefix (handles pagination).

        Args:
            prefix: S3 key prefix to list.

        Returns:
            List of S3 keys.
        """
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        logger.debug("list_objects", prefix=prefix, count=len(keys))
        return keys

    def delete_object(self, s3_key: str) -> None:
        """Delete a single object from the data lake.

        Args:
            s3_key: Key to delete.
        """
        self.client.delete_object(Bucket=self.bucket, Key=s3_key)
        logger.info("object_deleted", s3_key=s3_key)

    # ── Convenience wrappers ───────────────────────────────────────────────────

    def upload_camera_frame(
        self,
        tank_id: str,
        frame_bytes: bytes,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Upload a JPEG camera frame with auto-generated key.

        Args:
            tank_id: Tank identifier.
            frame_bytes: JPEG encoded frame data.
            timestamp: Capture timestamp; defaults to UTC now.

        Returns:
            S3 URI.
        """
        ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
        filename = f"{tank_id}_{ts}.jpg"
        s3_key = self.camera_key(tank_id, filename)
        return self.upload_bytes(frame_bytes, s3_key, content_type="image/jpeg")

    def upload_sensor_csv(
        self,
        tank_id: str,
        csv_bytes: bytes,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Upload a sensor data CSV to the data lake.

        Args:
            tank_id: Tank identifier.
            csv_bytes: CSV file content.
            timestamp: File timestamp; defaults to UTC now.

        Returns:
            S3 URI.
        """
        ts = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
        filename = f"{tank_id}_{ts}.csv"
        s3_key = self.sensor_key(tank_id, filename)
        return self.upload_bytes(csv_bytes, s3_key, content_type="text/csv")


def from_settings() -> DataLakeStorage:
    """Construct DataLakeStorage from environment variables."""
    import os

    return DataLakeStorage(
        bucket=os.getenv("S3_BUCKET_NAME", "aquafarm-datalake"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        access_key=os.getenv("S3_ACCESS_KEY") or None,
        secret_key=os.getenv("S3_SECRET_KEY") or None,
    )
