#!/usr/bin/env bash
set -euo pipefail

GCP_PROJECT_ID="${GCP_PROJECT_ID:-syntaxmatrix-media-prod-2026}"
GCP_REGION="${GCP_REGION:-europe-west1}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-syntaxmatrix-media-studio}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-syntaxmatrix-media-prod-2026-syntaxmatrix-media}"
PROXY_PORT="${PROXY_PORT:-9091}"

SERVICE_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --format='value(status.url)')"
if [[ -z "$SERVICE_URL" ]]; then
  echo "Could not resolve the Cloud Run service URL." >&2
  exit 1
fi

mkdir -p reports
python - "$SERVICE_URL" "$PROXY_PORT" > reports/voice_upload_cors.json <<'PY2'
import json, sys
service_url=sys.argv[1].rstrip('/')
port=sys.argv[2]
print(json.dumps([{
    "origin": [service_url, f"http://localhost:{port}", f"http://127.0.0.1:{port}"],
    "method": ["PUT", "POST", "OPTIONS"],
    "responseHeader": ["Content-Type", "x-goog-resumable"],
    "maxAgeSeconds": 3600,
}], indent=2))
PY2

gcloud storage buckets update "gs://${GCS_BUCKET_NAME}" --project="$GCP_PROJECT_ID" --cors-file="reports/voice_upload_cors.json"
echo "Voice upload CORS configured for:"
echo "  $SERVICE_URL"
echo "  http://localhost:${PROXY_PORT}"
echo "  http://127.0.0.1:${PROXY_PORT}"
