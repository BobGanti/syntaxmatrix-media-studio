# SyntaxMatrix Media Studio — Enterprise Cloud SQL Reproduction Guide

Document name: `docs/ENTERPRISE_CLOUD_SQL_REPRODUCTION_GUIDE.md`

Deployment profile: `enterprise_cloud_sql`

This document explains the clean enterprise deployment checkpoint for SyntaxMatrix Media Studio, how to reproduce it as a new project, and how to redeploy when updates are made.

It intentionally omits the failed/rogue development routes that caused confusion.

---

## 1. What This Project Is

SyntaxMatrix Media Studio is a workspace-based AI media application for:

- user registration and sign-in
- workspace creation
- Free and paid subscription plans
- Stripe checkout
- usage credits
- system voices
- private saved/custom voices for paid users
- narration generation
- GCS-backed media storage
- PostgreSQL-backed durable business data

The completed enterprise deployment is:

- Cloud Run for the Flask application
- Cloud SQL PostgreSQL for durable structured data
- Google Cloud Storage for uploaded/generated media
- Firebase Auth for user identity
- Stripe for paid subscriptions
- Secret Manager for production secrets

---

## 2. Deployment Profiles

There are now two intended deployment profiles.

### 2.1 Enterprise Profile — Current Checkpoint

Profile name:

`enterprise_cloud_sql`

Architecture:

Cloud Run app + Cloud SQL PostgreSQL + GCS + Firebase Auth + Stripe.

This is for larger companies or enterprise customers who prefer fully managed GCP database infrastructure.

### 2.2 Startup Profile — Next Stage

Profile name:

`startup_neon`

Architecture:

Cloud Run app + Neon Serverless PostgreSQL + GCS + Firebase Auth + Stripe.

This will be the lower-cost default for your own startup.

Important: do not use embedded PostgreSQL inside Cloud Run for production customer/billing/workspace data.

---

## 3. Current Enterprise GCP Resources

Current production resource names used during this deployment stage:

- GCP project: `syntaxmatrix-media-prod-2026`
- Region: `europe-west1`
- Cloud Run service: `syntaxmatrix-media-studio`
- Artifact Registry repo: `syntaxmatrix-media`
- Image name: `syntaxmatrix-media-studio`

Useful environment variables:

`GCP_PROJECT_ID=syntaxmatrix-media-prod-2026`

`GCP_REGION=europe-west1`

`CLOUD_RUN_SERVICE=syntaxmatrix-media-studio`

`AR_REPO=syntaxmatrix-media`

`IMAGE_NAME=syntaxmatrix-media-studio`

Get the live URL:

`gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --format='value(status.url)'`

---

## 4. Important Browser Routes

Auth page:

`/auth`

Plan page:

`/plans?workspaceId=<workspaceId>`

Customer workspace:

`/tasks/clone-voice?workspaceId=<workspaceId>`

Stripe success return should go back to:

`/tasks/clone-voice?workspaceId=<workspaceId>&billing=success`

---

## 5. Important API Routes

Plan catalogue:

`GET /api/billing/plans`

Workspace entitlement:

`GET /api/billing/entitlement?workspaceId=<workspaceId>`

Stripe checkout:

`POST /api/billing/checkout/stripe`

Stripe webhook:

`POST /api/billing/webhook/stripe`

Voice and narration routes are registered through:

`controllers/clone_voice_controller.py`

---

## 6. Final Plan Rules

### Free Plan

- key: `free`
- price: €0
- credits: 10 weekly credits
- reset: Monday 00:00 UTC
- rollover: no
- system voices only: yes
- custom voice slots: 0

Free users must not see:

- Create Voice
- My saved voices
- private voice upload
- private voice recording
- private saved voice list

Free users may use:

- system voices
- narration within weekly credit limit

### Starter

- price: €9/month
- monthly credits: 1,000
- custom voice slots: 1

### Pro

- price: €29/month
- monthly credits: 5,000
- custom voice slots: 3

### Business

- price: €99/month
- monthly credits: 20,000
- custom voice slots: 10

---

## 7. Pricing and Credits

Supplier cost assumptions:

- voice clone enrollment: $0.01 per successful cloned voice
- preview TTS: $0.115 per 10,000 characters
- narration TTS: $0.115 per 10,000 characters

Launch defaults:

- retail markup: 100%
- 1 credit = $0.005 retail usage value

Derived examples:

- clone only: 4 credits
- standard preview: 1 credit
- clone plus preview: 5 credits
- 10,000 narration characters: 46 credits

---

## 8. Key Source Files

App entry:

`app.py`

Customer workspace UI:

`frontend/clone_voice/client.html`

`frontend/clone_voice/client.js`

`frontend/clone_voice/client_usage.js`

Voice controller:

`controllers/clone_voice_controller.py`

Plan page:

`frontend/clone_voice/plans.html`

`frontend/clone_voice/plans.js`

Auth page:

`frontend/clone_voice/auth.html`

`frontend/clone_voice/auth.css`

`frontend/clone_voice/auth.js`

`frontend/clone_voice/auth_bootstrap.js`

Billing and Stripe:

`services/billing_pricing.py`

`services/billing_usage.py`

`services/subscription_enforcement.py`

`services/stripe_checkout.py`

`services/stripe_webhooks.py`

`services/stripe_customer_portal.py`

Plan configuration:

`billing/pricing_config.json`

Stripe paid price map:

`billing/stripe_price_map.json`

---

## 9. Runtime State Files

These local JSON files are fallback/runtime state and must not ship with fake records:

`billing/customers.json`

`billing/memberships.json`

`billing/workspaces.json`

`billing/workspace_subscriptions.json`

`billing/stripe_processed_events.json`

`billing/stripe_webhook_events.jsonl`

Clean source state should be:

- customers: `[]`
- memberships: `[]`
- workspaces: `[]`
- workspace_subscriptions: `{}`
- stripe_processed_events: `[]`
- stripe_webhook_events: empty file

Do not allow these terms in source runtime files:

- `mock_user_`
- `cust_mock_`
- `dev_admin`
- `dev_client_`
- `firebase_test_user`
- `stage9`
- `example.test`
- `cs_test_`
- old Stripe test event IDs

---

## 10. Free Plan Is Not a Stripe Plan

Free is an internal application plan.

Therefore:

`billing/pricing_config.json`

contains Free, Starter, Pro, Business and Enterprise app plan definitions.

`billing/stripe_price_map.json`

contains only paid Stripe checkout plans.

Correct Stripe mode:

`stripeMode: live`

Free must not appear as a Stripe checkout price.

---

## 11. New User Registration Rule

A newly registered user must default to Free.

Expected new workspace subscription:

- planKey: `free`
- status: `active`
- provider: `internal` or local equivalent
- weekly credits: 10
- system voices only: true
- custom voice slots: 0

The user must not be automatically placed on Starter.

---

## 12. Stripe Return Rule

When a logged-in user starts checkout:

`/plans?workspaceId=<workspaceId>`

Stripe must return to:

`/tasks/clone-voice?workspaceId=<workspaceId>&billing=success`

The user should not be forced to sign in again after Stripe.

Firebase auth persistence should use local persistence in the browser.

---

## 13. Reproducing as a New Enterprise Project

### Step 1 — Clone

`git clone <repo-url> syntaxmatrix-media-studio`

`cd syntaxmatrix-media-studio`

### Step 2 — Configure GCP

Set:

`GCP_PROJECT_ID`

`GCP_REGION`

`CLOUD_RUN_SERVICE`

`AR_REPO`

`IMAGE_NAME`

Enable APIs:

- Cloud Run
- Cloud Build
- Artifact Registry
- Cloud SQL Admin
- Secret Manager
- Cloud Storage

### Step 3 — Create Artifact Registry

Create a Docker repository in the selected region.

### Step 4 — Create GCS Bucket

Create a bucket for uploaded and generated media.

### Step 5 — Create Cloud SQL PostgreSQL

Create:

- PostgreSQL instance
- app database
- app database user
- password secret
- Cloud SQL connection name secret

### Step 6 — Create Secrets

Required production secrets include:

- Stripe secret key
- Stripe webhook secret
- Firebase project values
- Cloud SQL connection name
- database name
- database user
- database password
- GCS bucket name
- Alibaba/DashScope credentials

### Step 7 — Configure Stripe

In Stripe live mode:

- create subscription product
- create Starter, Pro and Business monthly prices
- add price IDs to `billing/stripe_price_map.json`
- create webhook endpoint at `/api/billing/webhook/stripe`

Webhook events:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted
- invoice.payment_succeeded
- invoice.payment_failed

### Step 8 — Configure Firebase Auth

Enable:

- Email/password auth
- authorized Cloud Run domain
- web app configuration

---

## 14. Validate Before Deployment

Run focused validation only:

`python -m scripts.pricing_core_stage1_acceptance`

`python -m scripts.pricing_free_plan_acceptance`

`python -m scripts.paid_plan_runtime_catalog_acceptance`

`python -m scripts.paid_launch_acceptance`

Compile important Python files:

`python -m py_compile app.py controllers/clone_voice_controller.py services/billing_pricing.py services/billing_usage.py services/subscription_enforcement.py services/stripe_checkout.py services/stripe_webhooks.py`

Check important JS files:

`node --check frontend/clone_voice/auth.js`

`node --check frontend/clone_voice/auth_bootstrap.js`

`node --check frontend/clone_voice/client.js`

`node --check frontend/clone_voice/client_usage.js`

`node --check frontend/clone_voice/plans.js`

`node --check frontend/clone_voice/billing.js`

Do not run old broad provider-contract tests when the change is only billing, auth, plans or UI.

---

## 15. Enterprise Deployment Command

Use this pattern:

`IMAGE_TAG="enterprise-cloud-sql-$(date +%Y%m%d-%H%M%S)"`

`IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"`

Build:

`gcloud builds submit . --project="$GCP_PROJECT_ID" --tag="$IMAGE_URI"`

Deploy:

`gcloud run services update "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --image="$IMAGE_URI" --no-invoker-iam-check`

Describe:

`gcloud run services describe "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --format='table(status.latestReadyRevisionName,status.traffic.revisionName,status.traffic.percent,status.url)'`

---

## 16. Smoke Test After Deployment

### Auth

Open `/auth`.

Confirm:

- sign in form visible
- create account form visible
- confirm password visible on registration
- reset password visible
- remember me visible
- password eye icon works

### Registration

Register a new user.

Confirm:

- new workspace created
- user defaults to Free
- user is not forced into Starter
- no payment required for Free

### Free Workspace

Open `/tasks/clone-voice?workspaceId=<workspaceId>`.

Confirm:

- usage loads automatically
- Free shown immediately
- 10 weekly credits shown
- System voices visible
- My saved voices hidden
- Create Voice hidden

### Plan Page

Open `/plans?workspaceId=<workspaceId>`.

Confirm:

- Free card visible
- Starter card visible
- Pro card visible
- Business card visible
- no Loading stuck state
- no Unavailable buttons
- cards aligned

### Stripe

Click Starter.

Confirm:

- Stripe Checkout opens
- after payment, user returns to workspace
- user remains signed in
- plan updates to Starter
- Create Voice appears
- My saved voices appears

---

## 17. Redeploying After Updates

For every update:

1. Patch locally.
2. Run focused validations.
3. Build a new image.
4. Update Cloud Run service to that image.
5. Smoke test auth, plans, Free user, paid checkout and workspace.

Do not patch unrelated provider files while fixing billing/UI/auth.

---

## 18. Rollback

List revisions:

`gcloud run revisions list --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --service="$CLOUD_RUN_SERVICE"`

Rollback traffic:

`gcloud run services update-traffic "$CLOUD_RUN_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --to-revisions="<REVISION_NAME>=100"`

---

## 19. Git Checkpoint

After this enterprise stage is accepted:

`git add .`

`git commit -m "Finalize enterprise Cloud SQL deployment profile"`

`git tag enterprise-cloud-sql-checkpoint-20260713`

`git push origin main`

`git push origin enterprise-cloud-sql-checkpoint-20260713`

This checkpoint marks the completed enterprise Cloud SQL deployment before starting the startup Neon profile.

---

## 20. Next Stage

Next stage:

`startup_neon`

Bounded scope:

- add deployment profile config
- add `DATABASE_URL` PostgreSQL connection support
- keep Cloud SQL path untouched
- add startup Neon deploy script
- add startup Neon documentation
- validate both profiles

The enterprise profile must remain available for bigger companies.
