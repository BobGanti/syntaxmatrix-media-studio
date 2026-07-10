Stage 1: GCP project and billing
Stage 2: APIs
Stage 3: service account and bucket
Stage 4: Dockerfile
Stage 5: build container locally
Stage 6: run container locally
Stage 7: build image with Cloud Build
Stage 8: deploy to Cloud Run
Stage 9: configure env vars and secrets
Stage 10: smoke test Cloud Run URL

# Put these in Secret Manager
SINGAPORE_API_KEY = Alibaba/DashScope API key name used by app.py and clone_voice_provider.py
STRIPE_SECRET_KEY = Stripe API secret key
STRIPE_WEBHOOK_SECRET = Stripe webhook secret, after you create the Cloud Run webhook endpoint
DATABASE_URL = later, when Cloud SQL is added

# Normal Cloud Run env vars:
SINGAPORE_WORKSPACE_ID
OBJECT_STORAGE_BACKEND=gcs
GCS_BUCKET_NAME
BILLING_PROVIDER=stripe
APP_PUBLIC_URL
PERSISTENCE_BACKEND=json   for now
ALIBABA_MEDIA_DRY_RUN=0
ALIBABA_MEDIA_MAX_UPLOAD_MB=80
FLASK_DEBUG=0