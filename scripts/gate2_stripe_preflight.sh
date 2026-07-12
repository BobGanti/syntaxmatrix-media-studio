#!/usr/bin/env bash
set -uo pipefail

GCP_PROJECT_ID="${GCP_PROJECT_ID:-syntaxmatrix-media-prod-2026}"
GCP_REGION="${GCP_REGION:-europe-west1}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-syntaxmatrix-media-studio}"

SERVICE_JSON="reports/gate2_cloud_run_service.json"
REFS_JSON="reports/gate2_stripe_refs.json"

FAILURES=0

pass() {
  echo "PASS — $1"
}

fail() {
  echo "FAIL — $1"
  FAILURES=$((FAILURES + 1))
}

echo "Gate 2A — Stripe test-mode preflight"
echo "===================================="

gcloud config set project "$GCP_PROJECT_ID" >/dev/null

if ! gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --format=json > "$SERVICE_JSON"
then
  fail "Cloud Run service could not be read"
  exit 1
fi

pass "Cloud Run service found"

python - "$SERVICE_JSON" "$REFS_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

service_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

service = json.loads(service_path.read_text(encoding="utf-8"))

containers = (
    service.get("spec", {})
    .get("template", {})
    .get("spec", {})
    .get("containers", [])
)

environment = {}

if containers:
    for row in containers[0].get("env", []):
        name = str(row.get("name") or "").strip()

        if not name:
            continue

        if "value" in row:
            environment[name] = {
                "kind": "value",
                "value": str(row.get("value") or ""),
            }
            continue

        secret_ref = (
            row.get("valueFrom", {})
            .get("secretKeyRef", {})
        )

        environment[name] = {
            "kind": "secret",
            "secret": str(secret_ref.get("name") or ""),
            "version": str(secret_ref.get("key") or "latest"),
        }

result = {
    "persistenceBackend": environment.get(
        "PERSISTENCE_BACKEND", {}
    ).get("value", ""),
    "billingProvider": environment.get(
        "BILLING_PROVIDER", {}
    ).get("value", ""),
    "appPublicUrl": environment.get(
        "APP_PUBLIC_URL", {}
    ).get("value", ""),
    "stripeSecretRef": environment.get(
        "STRIPE_SECRET_KEY", {}
    ).get("secret", ""),
    "stripeWebhookSecretRef": environment.get(
        "STRIPE_WEBHOOK_SECRET", {}
    ).get("secret", ""),
}

output_path.write_text(
    json.dumps(result, indent=2),
    encoding="utf-8",
)
PY

read_ref() {
  python - "$REFS_JSON" "$1" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get(sys.argv[2], ""))
PY
}

PERSISTENCE_BACKEND="$(read_ref persistenceBackend)"
BILLING_PROVIDER="$(read_ref billingProvider)"
APP_PUBLIC_URL="$(read_ref appPublicUrl)"
STRIPE_SECRET_REF="$(read_ref stripeSecretRef)"
STRIPE_WEBHOOK_SECRET_REF="$(read_ref stripeWebhookSecretRef)"

if [[ "$PERSISTENCE_BACKEND" == "postgres" ]]; then
  pass "PERSISTENCE_BACKEND is postgres"
else
  fail "PERSISTENCE_BACKEND is not postgres"
fi

if [[ "$BILLING_PROVIDER" == "stripe" ]]; then
  pass "BILLING_PROVIDER is stripe"
else
  fail "BILLING_PROVIDER is not stripe"
fi

if [[ "$APP_PUBLIC_URL" == https://* ]]; then
  pass "APP_PUBLIC_URL is an HTTPS URL"
else
  fail "APP_PUBLIC_URL is missing or is not HTTPS"
fi

if [[ -n "$STRIPE_SECRET_REF" ]]; then
  pass "STRIPE_SECRET_KEY uses Secret Manager"

  STRIPE_MODE="$(
    gcloud secrets versions access latest \
      --secret="$STRIPE_SECRET_REF" \
      --project="$GCP_PROJECT_ID" 2>/dev/null |
    python -c '
import sys
value = sys.stdin.read().strip()

if value.startswith("sk_test_"):
    print("test")
elif value.startswith("sk_live_"):
    print("live")
else:
    print("unknown")
'
  )"

  if [[ "$STRIPE_MODE" == "test" ]]; then
    pass "Stripe API key is test mode"
  else
    fail "Stripe API key is not a valid test key"
  fi
else
  fail "STRIPE_SECRET_KEY has no Secret Manager reference"
fi

if [[ -n "$STRIPE_WEBHOOK_SECRET_REF" ]]; then
  pass "STRIPE_WEBHOOK_SECRET uses Secret Manager"

  WEBHOOK_SECRET_STATUS="$(
    gcloud secrets versions access latest \
      --secret="$STRIPE_WEBHOOK_SECRET_REF" \
      --project="$GCP_PROJECT_ID" 2>/dev/null |
    python -c '
import sys
value = sys.stdin.read().strip()
print("valid" if value.startswith("whsec_") else "invalid")
'
  )"

  if [[ "$WEBHOOK_SECRET_STATUS" == "valid" ]]; then
    pass "Stripe webhook signing secret has the expected format"
  else
    fail "Stripe webhook signing secret is invalid"
  fi
else
  fail "STRIPE_WEBHOOK_SECRET has no Secret Manager reference"
fi

if python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

price_map_path = Path("billing/stripe_price_map.json")
pricing_path = Path("billing/pricing_config.json")

if not price_map_path.exists():
    raise SystemExit("billing/stripe_price_map.json is missing")

if not pricing_path.exists():
    raise SystemExit("billing/pricing_config.json is missing")

price_map = json.loads(price_map_path.read_text(encoding="utf-8"))
pricing = json.loads(pricing_path.read_text(encoding="utf-8"))

if price_map.get("stripeMode") != "test":
    raise SystemExit("Local Stripe price map is not test mode")

plans = price_map.get("plans")

if not isinstance(plans, dict):
    raise SystemExit("Stripe price map has no plans")

for plan_key in ("starter", "pro", "business"):
    record = plans.get(plan_key)

    if not isinstance(record, dict):
        raise SystemExit(f"Missing Stripe price: {plan_key}")

    if not str(record.get("priceId") or "").startswith("price_"):
        raise SystemExit(f"Invalid Stripe price ID: {plan_key}")

    if record.get("active") is not True:
        raise SystemExit(f"Inactive Stripe price: {plan_key}")

configured = {
    str(row.get("key")): row
    for row in pricing.get("plans", [])
    if isinstance(row, dict)
}

for plan_key in ("starter", "pro", "business"):
    expected = round(
        float(configured[plan_key]["monthlyPrice"]) * 100
    )
    actual = int(plans[plan_key]["unitAmount"])

    if actual != expected:
        raise SystemExit(
            f"Price mismatch for {plan_key}: "
            f"expected {expected}, found {actual}"
        )

print("Local test catalog verified")
PY
then
  pass "Local Stripe test price catalog is valid"
else
  fail "Local Stripe test price catalog is invalid"
fi

echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "GATE 2A STRIPE PREFLIGHT: PASSED"
  exit 0
fi

echo "GATE 2A STRIPE PREFLIGHT: FAILED (${FAILURES} checks)"
exit 1
