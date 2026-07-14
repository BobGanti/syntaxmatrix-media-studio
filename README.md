# SyntaxMatrix Media Studio

<p align="center">
  <strong>Multi-tenant AI voice cloning, narration, billing, and media workflow platform.</strong>
</p>

<p align="center">
  <a href="https://syntaxmatrix-media-studio-gy2hf4qo5q-ew.a.run.app"><strong>Live Application</strong></a>
  ·
  <a href="#demo"><strong>Demo</strong></a>
  ·
  <a href="#architecture"><strong>Architecture</strong></a>
  ·
  <a href="#local-development"><strong>Run Locally</strong></a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-Backend-000000?logo=flask&logoColor=white">
  <img alt="Google Cloud Run" src="https://img.shields.io/badge/Google%20Cloud-Cloud%20Run-4285F4?logo=googlecloud&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white">
  <img alt="Stripe" src="https://img.shields.io/badge/Stripe-Billing-635BFF?logo=stripe&logoColor=white">
  <img alt="Firebase" src="https://img.shields.io/badge/Firebase-Authentication-FFCA28?logo=firebase&logoColor=black">
</p>

<p align="center">
  <img
    src="docs/media/screenshots/01-client-workspace.png"
    alt="SyntaxMatrix Media Studio client workspace"
    width="100%"
  >
</p>

> **Project status:** Active development. The deployed application demonstrates the production architecture, authentication, workspace management, voice workflows, billing controls, and Google Cloud deployment.

---

## Overview

SyntaxMatrix Media Studio is a multi-tenant AI media platform designed for secure voice cloning, text-to-speech narration, reusable system voices, customer workspaces, subscription billing, and extensible image/video generation workflows.

The platform combines a Flask service layer, provider-neutral controllers, Alibaba Cloud voice models, Firebase Authentication, Stripe Billing, PostgreSQL persistence, Google Cloud Storage, and containerized deployment on Google Cloud Run.

The system is designed around separation of concerns:

- The frontend communicates with feature controllers rather than provider SDKs directly.
- Authentication, billing, usage metering, subscriptions, and media operations are isolated into dedicated services.
- Product prices, credit allowances, supplier costs, markup, and plan limits have one canonical configuration source.
- Customer workspaces remain isolated from global system voices and administrative controls.
- External provider identifiers are separated from internal product pricing and entitlement logic.

---

## Product Tour

### 1. Plan selection

Free and paid plans are rendered from the runtime pricing catalogue. The Free plan provides system-voice access and a weekly credit allowance, while paid plans add monthly credits and custom voice-cloning slots.

<p align="center">
  <img
    src="docs/media/screenshots/02-plan-selection.png"
    alt="SyntaxMatrix Media Studio plan selection"
    width="100%"
  >
</p>

### 2. Voice cloning and narration workspace

Customers can work with system voices or create private voice profiles according to their plan entitlement. The workspace supports source recording/upload, reusable voice parameters, previews, and generated narration.

<p align="center">
  <img
    src="docs/media/screenshots/03-voice-cloning-workspace.png"
    alt="Voice cloning and narration workspace"
    width="100%"
  >
</p>

### 3. Billing and usage

The billing experience exposes the active plan, allowance period, credit balance, custom voice-slot entitlement, subscription status, and Stripe customer-management actions.

<p align="center">
  <img
    src="docs/media/screenshots/04-billing-and-usage.png"
    alt="Billing, subscription, and usage dashboard"
    width="100%"
  >
</p>

### 4. Client lifecycle administration

Administrators can search, filter, paginate, archive, and synchronize customer workspaces. Active Stripe subscriptions are protected from deletion until the subscription has been cancelled.

<p align="center">
  <img
    src="docs/media/screenshots/05-admin-client-cleanup.png"
    alt="Administrative client lifecycle dashboard"
    width="100%"
  >
</p>

### 5. Global system voice management

Administrators can configure the source-audio duration policy, create global system voices, preview voices, filter the library, and remove obsolete voice profiles.

<p align="center">
  <img
    src="docs/media/screenshots/06-admin-system-voices.png"
    alt="Administrative system voice management"
    width="100%"
  >
</p>

### 6. Responsive mobile experience

The interface adapts to smaller screens while retaining access to core customer and administrative workflows.

<p align="center">
  <img
    src="docs/media/screenshots/07-mobile-experience.png"
    alt="SyntaxMatrix Media Studio mobile experience"
    width="430"
  >
</p>

---

## Demo

[![Watch the SyntaxMatrix Media Studio demo](docs/media/demo/demo-thumbnail.png)](docs/media/demo/syntaxmatrix-media-studio-demo.mp4)

The demonstration should cover:

1. Creating or signing in to an account.
2. Reviewing the Free, Starter, Pro, and Business plans.
3. Entering the customer workspace.
4. Selecting a system voice.
5. Uploading or recording source audio for a private voice.
6. Generating a voice preview or narration.
7. Reviewing billing, credits, and plan entitlements.
8. Showing the administrator client-cleanup and system-voice tools.
9. Demonstrating the deployed Cloud Run application.

---

## Key Capabilities

### AI voice workflows

- Voice-source recording and file upload.
- Reusable private voice parameters.
- Global system voices available across customer workspaces.
- Fixed-text voice previews for consistent quality comparison.
- Text-to-speech narration generation.
- Provider-neutral controller and service boundaries.
- Extensible model mapping for image, video, audio, and script-processing tasks.

### Multi-tenant product controls

- Isolated customer workspaces.
- Workspace membership and customer records.
- Free and paid plan entitlements.
- Custom voice-slot enforcement.
- Usage-credit accounting.
- Weekly and monthly allowance periods.
- Administrative customer lifecycle controls.
- Protection against deleting workspaces with active paid subscriptions.

### Authentication and authorization

- Firebase Authentication.
- Registration and sign-in workflows.
- Password reset support.
- Configurable session persistence.
- Server-protected administrative routes.
- Admin email and claim validation.
- Backend session and Firebase token support.

### Billing and subscriptions

- Stripe Checkout.
- Stripe webhook processing.
- Stripe customer portal.
- Subscription and payment reconciliation.
- Checkout-return plan activation.
- Workspace-level entitlement refresh.
- Provider-ID mapping separated from business pricing.
- Manual administrative reconciliation as a recovery mechanism.

### Production infrastructure

- Docker containerization.
- Google Cloud Run deployment.
- Google Artifact Registry.
- PostgreSQL persistence through Cloud SQL.
- Google Cloud Storage for media assets.
- Firebase Authentication.
- Stripe Billing.
- Environment-based secrets and runtime configuration.

---

## Single-Source Pricing Architecture

Business pricing is defined in one place:

```text
billing/pricing_config.json
```

This file owns:

- Plan prices.
- Currency.
- Weekly and monthly credit allowances.
- Custom voice-slot limits.
- Credit reset periods.
- Supplier costs.
- Retail markup.
- Retail credit value.
- Usage-event pricing rules.

The runtime pricing authority is:

```text
services/billing_pricing.py
```

Stripe provider identifiers are stored separately:

```text
billing/stripe_price_map.json
```

The Stripe mapping contains provider IDs only. It does not duplicate prices, credits, supplier rates, or entitlement limits.

```mermaid
flowchart LR
    A[billing/pricing_config.json] --> B[services/billing_pricing.py]
    B --> C[Plans API]
    B --> D[Usage metering]
    B --> E[Subscription enforcement]
    B --> F[Stripe checkout]
    B --> G[Stripe reconciliation]
    H[billing/stripe_price_map.json] --> F
    H --> G
```

A validation script prevents commercial values from being reintroduced into frontend or unrelated backend files:

```bash
python -m scripts.pricing_single_source_validation
```

---

## Architecture

```mermaid
flowchart TB
    U[Customer or Administrator] --> UI[Web UI]
    UI --> API[Flask Application API]

    API --> AUTH[Authentication and Session Services]
    API --> WS[Workspace and Membership Services]
    API --> BILL[Billing, Pricing and Entitlement Services]
    API --> MEDIA[Voice and Media Controllers]
    API --> ADMIN[Administrative Lifecycle Services]

    AUTH --> FIREBASE[Firebase Authentication]
    BILL --> STRIPE[Stripe Billing]
    WS --> DB[(PostgreSQL / Cloud SQL)]
    BILL --> DB
    ADMIN --> DB

    MEDIA --> ALIBABA[Alibaba Cloud Voice and Media Models]
    MEDIA --> GCS[Google Cloud Storage]

    API --> RUN[Google Cloud Run]
    RUN --> AR[Artifact Registry]
```

### Request flow

```mermaid
sequenceDiagram
    actor Customer
    participant UI as Web UI
    participant API as Flask API
    participant Auth as Firebase/Auth Service
    participant Billing as Billing Service
    participant Media as Voice Controller
    participant Provider as Alibaba Model API
    participant Storage as GCS

    Customer->>UI: Sign in and select workspace
    UI->>Auth: Obtain authenticated session
    UI->>API: Request entitlement
    API->>Billing: Resolve plan, credits and voice slots
    Billing-->>UI: Entitlement payload
    Customer->>UI: Upload or record source audio
    UI->>API: Submit voice operation
    API->>Billing: Validate allowance
    API->>Media: Create preview or narration
    Media->>Provider: Invoke configured model
    Provider-->>Media: Generated media
    Media->>Storage: Persist media asset
    Media-->>UI: Return secured result
```

---

## Technology Stack

| Area | Technologies |
|---|---|
| Backend | Python, Flask, REST APIs |
| Frontend | JavaScript, TypeScript, HTML, CSS |
| AI providers | Alibaba Cloud Qwen / DashScope-compatible services |
| Authentication | Firebase Authentication |
| Billing | Stripe Checkout, Webhooks, Customer Portal |
| Database | PostgreSQL, Google Cloud SQL |
| Object storage | Google Cloud Storage |
| Deployment | Docker, Google Cloud Run, Artifact Registry |
| Validation | Python acceptance scripts, syntax checks, pricing guardrails |
| Development environment | VS Code, Git, GitHub, `gcloud` CLI |

---

## Repository Structure

```text
AlibabaMedia/
├── app.py
├── billing/
│   ├── pricing_config.json
│   └── stripe_price_map.json
├── config/
├── controllers/
│   ├── clone_voice_controller.py
│   └── provider-specific media controllers
├── frontend/
│   └── clone_voice/
│       ├── auth.html
│       ├── auth.js
│       ├── client.html
│       ├── client.js
│       ├── plans.html
│       ├── plans.js
│       ├── billing.html
│       ├── billing.js
│       ├── admin.html
│       └── admin.js
├── services/
│   ├── billing_pricing.py
│   ├── billing_usage.py
│   ├── subscription_enforcement.py
│   ├── stripe_checkout.py
│   ├── stripe_webhooks.py
│   ├── customer_workspace.py
│   ├── clone_voice_workspace.py
│   └── admin_client_lifecycle.py
├── scripts/
│   ├── pricing_single_source_validation.py
│   ├── pricing_core_stage1_acceptance.py
│   ├── pricing_free_plan_acceptance.py
│   ├── paid_plan_runtime_catalog_acceptance.py
│   └── paid_launch_acceptance.py
├── docs/
│   └── media/
│       ├── screenshots/
│       └── demo/
├── Dockerfile
└── requirements.txt
```

---

## Local Development

### Prerequisites

- Python 3.11 or newer.
- Git.
- Docker Desktop for containerized development.
- A Firebase project.
- A Stripe account.
- An Alibaba Cloud/DashScope-compatible API profile.
- PostgreSQL for durable workspace, subscription, and billing data.
- Google Cloud credentials when testing GCS or production deployment.

### 1. Clone and enter the repository

Use the HTTPS or SSH clone URL shown in GitHub’s **Code** menu, clone the repository, and enter the project directory:

```bash
cd AlibabaMedia
```

### 2. Create a Python environment

Git Bash on Windows:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file. Never commit secrets.

Representative variables:

```dotenv
FLASK_ENV=development
SECRET_KEY=replace-me

DATABASE_URL=postgresql://user:password@host:5432/database

GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=europe-west1
GCS_BUCKET=your-media-bucket

FIREBASE_PROJECT_ID=your-firebase-project
FIREBASE_API_KEY=replace-me
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com

STRIPE_SECRET_KEY=replace-me
STRIPE_WEBHOOK_SECRET=replace-me
STRIPE_PUBLISHABLE_KEY=replace-me

ADMIN_EMAILS=admin@example.com
SMX_ADMIN_EMAILS=admin@example.com

DASHSCOPE_API_KEY=replace-me
ALIBABA_WORKSPACE_ID=replace-me
```

### 5. Run the application

```bash
python app.py
```

Open the local URL printed by Flask.

### Docker

```bash
docker build -t syntaxmatrix-media-studio .
docker run --rm -p 8080:8080 --env-file .env syntaxmatrix-media-studio
```

---

## Validation

Run the focused production checks before deployment:

```bash
python -m py_compile \
  app.py \
  services/billing_pricing.py \
  services/billing_usage.py \
  services/subscription_enforcement.py \
  services/stripe_checkout.py \
  services/stripe_webhooks.py \
  services/admin_client_lifecycle.py
```

```bash
python -m scripts.pricing_single_source_validation
python -m scripts.pricing_core_stage1_acceptance
python -m scripts.pricing_free_plan_acceptance
python -m scripts.paid_plan_runtime_catalog_acceptance
python -m scripts.paid_launch_acceptance
```

Frontend syntax checks:

```bash
node --check frontend/clone_voice/client.js
node --check frontend/clone_voice/plans.js
node --check frontend/clone_voice/billing.js
node --check frontend/clone_voice/admin.js
```

---

## Production Deployment

The current production profile uses:

- Google Cloud Run.
- Docker containers.
- Google Artifact Registry.
- Google Cloud SQL for PostgreSQL.
- Google Cloud Storage for media assets.
- Firebase Authentication.
- Stripe Billing.

Representative deployment:

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="europe-west1"
export CLOUD_RUN_SERVICE="syntaxmatrix-media-studio"
export AR_REPO="syntaxmatrix-media"
export IMAGE_NAME="syntaxmatrix-media-studio"

IMAGE_TAG="release-$(date +%Y%m%d-%H%M%S)"
IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}"

gcloud builds submit . \
  --project="$GCP_PROJECT_ID" \
  --tag="$IMAGE_URI"

gcloud run services update "$CLOUD_RUN_SERVICE" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --image="$IMAGE_URI"
```

Production secrets should be supplied through Google Cloud Secret Manager or protected Cloud Run environment configuration. Do not commit secrets to the repository.

---

## Security and Data Protection

- Administrative HTML and API routes are protected server-side.
- Firebase identity tokens and backend sessions are validated independently of frontend visibility.
- Workspaces are isolated by customer and membership context.
- System voices are global; customer-created voices remain workspace-private.
- Stripe webhook events are verified and processed idempotently.
- Active paid subscriptions block customer deletion until cancellation.
- Media assets are stored outside the application container.
- Sensitive values are loaded from environment or managed secrets.
- Source audio, voice parameters, previews, and narration outputs follow separate naming and storage policies.

---

## Roadmap

- Complete responsive UI refinement across all customer and admin pages.
- Expand image-to-video and text-to-video production workflows.
- Add richer media-generation observability and job tracking.
- Add automated browser-level end-to-end tests.
- Add subscription upgrade, downgrade, cancellation, and renewal coverage.
- Extend the startup deployment profile to serverless PostgreSQL where appropriate.
- Add provider failover and model-level cost/performance routing.

---

## Media Asset Locations

The README expects the following files:

```text
docs/media/screenshots/01-client-workspace.png
docs/media/screenshots/02-plan-selection.png
docs/media/screenshots/03-voice-cloning-workspace.png
docs/media/screenshots/04-billing-and-usage.png
docs/media/screenshots/05-admin-client-cleanup.png
docs/media/screenshots/06-admin-system-voices.png
docs/media/screenshots/07-mobile-experience.png

docs/media/demo/demo-thumbnail.png
docs/media/demo/syntaxmatrix-media-studio-demo.mp4
```

Recommended screenshot format:

- PNG.
- Desktop screenshots: 1440×900 or larger.
- Mobile screenshot: approximately 390×844 or 430×932.
- Remove browser bookmarks, unrelated tabs, personal email addresses, customer IDs, subscription IDs, and payment information before publishing.
- Use demo/test accounts rather than real customer data.

Recommended video format:

- MP4 with H.264 video and AAC audio.
- 1080p where possible.
- Two to five minutes.
- Remove secrets, tokens, payment details, personal data, and browser password-manager overlays.

---

## License

Copyright © SyntaxMatrix. All rights reserved `LICENSE`.
