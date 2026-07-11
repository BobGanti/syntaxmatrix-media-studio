#!/usr/bin/env bash
set -euo pipefail

# SyntaxMatrix Media Studio — consolidated private production deployment.
# This script never reads or prints secret values.

GCP_PROJECT_ID="${GCP_PROJECT_ID:-syntaxmatrix-media-prod-2026}"
GCP_REGION="${GCP_REGION:-europe-west1}"
AR_REPO="${AR_REPO:-syntaxmatrix-media}"
IMAGE_NAME="${IMAGE_NAME:-syntaxmatrix-media-studio}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-syntaxmatrix-media-studio}"
CLOUD_RUN_SERVICE_ACCOUNT_EMAIL="${CLOUD_RUN_SERVICE_ACCOUNT_EMAIL:-syntaxmatrix-media-runner@syntaxmatrix-media-prod-2026.iam.gserviceaccount.com}"
SQL_INSTANCE="${SQL_INSTANCE:-syntaxmatrix-media-postgres}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-smx_database_url_vault}"
SCHEMA_JOB="${SCHEMA_JOB:-syntaxmatrix-media-schema-init}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-syntaxmatrix-media-prod-2026-syntaxmatrix-media}"
IMAGE_TAG="${IMAGE_TAG:-gate1-final-voice-durability-001}"

SQL_CONNECTION_NAME="${GCP_PROJECT_ID}:${GCP_REGION}:${SQL_INSTANCE}"
IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_command gcloud
require_command python

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  echo "No active gcloud account. Run: gcloud auth login" >&2
  exit 1
fi

echo "SyntaxMatrix consolidated deployment"
echo "===================================="
echo "Account: ${ACTIVE_ACCOUNT}"
echo "Project: ${GCP_PROJECT_ID}"
echo "Region: ${GCP_REGION}"
echo "Image: ${IMAGE_URI}"
echo "Service remains private."

gcloud config set project "$GCP_PROJECT_ID" >/dev/null

# Local contract gates must pass before any build starts.
python -m compileall -q .
python -m scripts.gate1_acceptance
python -m scripts.production_acceptance

# One image build.
gcloud builds submit . \
  --project="$GCP_PROJECT_ID" \
  --tag="$IMAGE_URI"

# One schema execution. The SQL is idempotent and creates/updates all required tables.
gcloud run jobs deploy "$SCHEMA_JOB" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --image="$IMAGE_URI" \
  --service-account="$CLOUD_RUN_SERVICE_ACCOUNT_EMAIL" \
  --set-cloudsql-instances="$SQL_CONNECTION_NAME" \
  --set-secrets="DATABASE_URL=${DATABASE_URL_SECRET}:latest" \
  --set-env-vars="PERSISTENCE_BACKEND=postgres" \
  --command="python" \
  --args="scripts/init_postgres_schema.py" \
  --tasks=1 \
  --max-retries=0 \
  --task-timeout=10m \
  --execute-now \
  --wait

# One private service deployment. --update-* preserves all unrelated existing
# Firebase, Alibaba and Stripe configuration on the service.
gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --platform=managed \
  --image="$IMAGE_URI" \
  --service-account="$CLOUD_RUN_SERVICE_ACCOUNT_EMAIL" \
  --add-cloudsql-instances="$SQL_CONNECTION_NAME" \
  --update-secrets="DATABASE_URL=${DATABASE_URL_SECRET}:latest" \
  --update-env-vars="PERSISTENCE_BACKEND=postgres,OBJECT_STORAGE_BACKEND=gcs,GCS_BUCKET_NAME=${GCS_BUCKET_NAME},FLASK_DEBUG=0" \
  --timeout=900 \
  --no-allow-unauthenticated

echo
echo "Deployment verification"
echo "======================="
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --format='table(status.latestReadyRevisionName,status.url)'

gcloud run jobs executions list \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --job="$SCHEMA_JOB" \
  --limit=1 \
  --format='table(name,status.conditions[0].type,status.conditions[0].status,status.completionTime)'

echo
echo "DEPLOYMENT COMPLETED — service is still private."
echo "Start the proxy in PowerShell:"
echo "gcloud run services proxy ${CLOUD_RUN_SERVICE} --region ${GCP_REGION} --port=9091"
