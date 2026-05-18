#!/usr/bin/env bash
# Manual Postgres + MLflow backup helper for the docker-compose stack.
#
# Mirrors the k8s CronJob in infra/k8s/postgres/backup-cronjob.yaml — same
# pg_dump format, same S3 key layout. Run with the main stack up:
#
#   make up
#   ./scripts/backup_postgres.sh                  # writes to ./backups/
#   S3_ENDPOINT_URL=http://localhost:9000 \
#   S3_BUCKET_NAME=aquafarm-datalake \
#   ./scripts/backup_postgres.sh --upload          # also uploads to MinIO/S3
#
# Env vars (read from .env when present):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

# Load .env if present (without overriding already-set vars)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-aquafarm}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-aquafarm_secret}"
APP_DB="${POSTGRES_DB:-aquafarm}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
UPLOAD=0

for arg in "$@"; do
  case "$arg" in
    --upload) UPLOAD=1 ;;
    *)        echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$BACKUP_DIR"
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)

if ! docker compose ps --status=running postgres >/dev/null 2>&1; then
  echo "postgres container is not running — run 'make up' first" >&2
  exit 1
fi

for DB in "$APP_DB" "${APP_DB}_mlflow"; do
  OUT="$BACKUP_DIR/${DB}-${TS}.dump"
  echo "[backup] dumping $DB → $OUT"
  docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
    pg_dump --format=custom --no-owner --no-privileges \
            --username="$POSTGRES_USER" "$DB" > "$OUT"
  SIZE=$(du -h "$OUT" | cut -f1)
  echo "[backup]   size=$SIZE"
done

if [[ "$UPLOAD" == "1" ]]; then
  : "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL must be set for --upload}"
  : "${S3_BUCKET_NAME:?S3_BUCKET_NAME must be set for --upload}"
  : "${S3_ACCESS_KEY:?S3_ACCESS_KEY must be set for --upload}"
  : "${S3_SECRET_KEY:?S3_SECRET_KEY must be set for --upload}"

  echo "[backup] uploading to s3://$S3_BUCKET_NAME/backups/postgres/"
  AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
  AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
  docker run --rm --network host -v "$BACKUP_DIR":/data \
    -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
    amazon/aws-cli:2.17.0 \
    s3 cp /data/ "s3://$S3_BUCKET_NAME/backups/postgres/" \
      --recursive --exclude '*' --include "*-${TS}.dump" \
      --endpoint-url "$S3_ENDPOINT_URL"
fi

echo "[backup] done — files under $BACKUP_DIR"
