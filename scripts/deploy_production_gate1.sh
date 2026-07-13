#!/usr/bin/env bash
set -euo pipefail

# SyntaxMatrix Media Studio — consolidated paid production deployment.
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
echo "Service will remain publicly reachable behind Firebase application authentication."

gcloud config set project "$GCP_PROJECT_ID" >/dev/null

# PAID_PLAN_RUNTIME_CATALOG
# Read existing live recurring Price IDs without displaying them.
STRIPE_PRICE_STARTER="$(
python - <<'PY_STARTER_PRICE'
import json
from pathlib import Path

path = Path("billing/stripe_price_map.json")
data = json.loads(path.read_text(encoding="utf-8"))

assert data.get("stripeMode") == "live", (
    "billing/stripe_price_map.json is not live mode"
)

value = str(
    data.get("plans", {})
    .get("starter", {})
    .get("priceId", "")
)

assert value.startswith("price_"), (
    "Live Starter Price ID is missing"
)

print(value)
PY_STARTER_PRICE
)"

STRIPE_PRICE_PRO="$(
python - <<'PY_PRO_PRICE'
import json
from pathlib import Path

data = json.loads(
    Path("billing/stripe_price_map.json")
    .read_text(encoding="utf-8")
)

value = str(
    data.get("plans", {})
    .get("pro", {})
    .get("priceId", "")
)

assert value.startswith("price_"), (
    "Live Pro Price ID is missing"
)

print(value)
PY_PRO_PRICE
)"

STRIPE_PRICE_BUSINESS="$(
python - <<'PY_BUSINESS_PRICE'
import json
from pathlib import Path

data = json.loads(
    Path("billing/stripe_price_map.json")
    .read_text(encoding="utf-8")
)

value = str(
    data.get("plans", {})
    .get("business", {})
    .get("priceId", "")
)

assert value.startswith("price_"), (
    "Live Business Price ID is missing"
)

print(value)
PY_BUSINESS_PRICE
)"

echo "Live Stripe catalogue: validated"

# Local contract gates must pass before any build starts.
python -m compileall -q .
python -m scripts.gate1_acceptance
python -m scripts.production_acceptance
python -m scripts.paid_launch_acceptance
python -m scripts.pricing_free_plan_acceptance

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
  --update-env-vars="PERSISTENCE_BACKEND=postgres,OBJECT_STORAGE_BACKEND=gcs,GCS_BUCKET_NAME=${GCS_BUCKET_NAME},FLASK_DEBUG=0,STRIPE_PRICE_STARTER=${STRIPE_PRICE_STARTER},STRIPE_PRICE_PRO=${STRIPE_PRICE_PRO},STRIPE_PRICE_BUSINESS=${STRIPE_PRICE_BUSINESS}" \
  --timeout=900


# Preserve public reachability for customers and Stripe. Application routes
# remain protected by Firebase and workspace/admin authorisation.
gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --no-invoker-iam-check

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
echo "DEPLOYMENT COMPLETED — paid production service is publicly reachable."
echo "Start the proxy in PowerShell:"
echo "gcloud run services proxy ${CLOUD_RUN_SERVICE} --region ${GCP_REGION} --port=9091"
