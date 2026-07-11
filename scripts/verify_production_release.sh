#!/usr/bin/env bash
set -euo pipefail

GCP_PROJECT_ID="${GCP_PROJECT_ID:-syntaxmatrix-media-prod-2026}"
GCP_REGION="${GCP_REGION:-europe-west1}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-syntaxmatrix-media-studio}"
SCHEMA_JOB="${SCHEMA_JOB:-syntaxmatrix-media-schema-init}"

gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --format='yaml(status.latestReadyRevisionName,status.url,spec.template.metadata.annotations,spec.template.spec.timeoutSeconds,spec.template.spec.containers[0].image,spec.template.spec.containers[0].env)'

gcloud run jobs executions list \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --job="$SCHEMA_JOB" \
  --limit=1 \
  --format='table(name,status.conditions[0].type,status.conditions[0].status,status.completionTime)'
