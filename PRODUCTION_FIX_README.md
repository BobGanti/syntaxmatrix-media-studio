# SyntaxMatrix Media Studio — Consolidated Production Fix

This package replaces the incremental deployment patches with one coherent production correction for Firebase tenancy, Cloud SQL persistence, GCS media storage, Alibaba voice creation, and the Clone Voice browser workflow.

## What was actually wrong

The uploaded project revealed several independent production defects behind the repeated deployment failures:

1. `services/clone_voice_provider.py` imported `ali_voice_clone`, but the module was absent from the project and therefore absent from the Docker image.
2. Firebase customers, workspaces, memberships, subscriptions and usage had been moved toward PostgreSQL, but saved voice identities were still kept in Cloud Run's local filesystem.
3. System voice identities were also local-only.
4. Voice preview audio was mirrored to GCS, but the corresponding provider voice ID was not durably catalogued. A preview file alone cannot generate future narration.
5. The browser called `response.json()` unconditionally. Any HTML response from a proxy, timeout, missing route or platform error became the unhelpful `Unexpected token '<'` message.
6. The SPA catch-all could serve `index.html` for an unknown API GET route.
7. Saved-voice previews could re-use the visible Result audio player, even though that player is reserved for generated narration.
8. The Gunicorn request timeout was only 300 seconds for a workflow that performs enrollment, preview synthesis, audio normalisation, GCS upload and database persistence.

## Production changes in this package

### Provider integration

- Added the missing `ali_voice_clone.py` implementation.
- Added provider-safe enrolment payload construction for WAV and other supported MIME types.
- Added credential and workspace validation without logging secret values.
- Added safe provider error reporting with HTTP status and request ID where available.
- Preserved the existing Qwen narration-generation call path.

### Durable data

- Added PostgreSQL `workspace_voices` table.
- Added PostgreSQL `system_voices` table.
- Added JSON equivalents for local development only.
- Added repository methods to list, load, upsert and delete workspace and system voices.
- Saved provider voice IDs now survive Cloud Run restarts and instance changes.
- Workspace and system preview audio remains in GCS.
- Local parameter files are treated as temporary caches and can be reconstructed from PostgreSQL.

### Browser and API reliability

- Added a safe API response parser that reports the HTTP status and readable server message when JSON is not returned.
- Removed mock-workspace fallback when production workspace discovery fails.
- Prevented API and protected-media paths from falling through to the SPA HTML page.
- Converted API HTTP exceptions to JSON while preserving their status codes.
- Kept the Result audio player exclusively for generated narration.
- Increased Gunicorn and Cloud Run request timeout to 900 seconds.

### Deployment hygiene

- Added a production `.dockerignore` that removes secrets, local media, temporary files, mock runtime records and backups while retaining pricing configuration.
- Added one consolidated deployment script.
- Added one production acceptance test script.
- The Cloud Run service remains private after deployment.

## Tests completed on this package

The following checks pass:

```text
Python compilation
Existing Gate 1 tenancy/persistence acceptance
Alibaba enrolment payload contract with mocked transport
Workspace voice durability after local-file deletion
System voice durability after local-file deletion
Flask multipart Save Voice route
API JSON 404 contract
Frontend JavaScript syntax
Preview/Result-player separation
PostgreSQL schema presence
Deployment-package checks
```

Run them locally from the project root:

```bash
python -m compileall -q .
python -m scripts.gate1_acceptance
python -m scripts.production_acceptance
```

These are local contract and integration tests with mocked external provider transport. The package has not been allowed to use your real Alibaba key, Cloud SQL password, Firebase tokens or Stripe credentials.

## One deployment process

### 1. Back up the current project

Keep the current folder unchanged until the final private acceptance test passes. Extract this package as a separate project folder in VS Code.

Do not copy `.env` into source control. Your existing Cloud Run secrets and normal environment variables remain on the service because the deployment script uses `--update-secrets` and `--update-env-vars` rather than replacing unrelated configuration.

### 2. Activate the local virtual environment

From Git Bash in the corrected project root:

```bash
source .venv/Scripts/activate
```

Then run:

```bash
python -m scripts.gate1_acceptance
python -m scripts.production_acceptance
```

Both commands must finish with `PASSED`.

### 3. Deploy once

```bash
bash scripts/deploy_production_gate1.sh
```

The script performs this fixed sequence:

```text
local acceptance gates
→ one Cloud Build image
→ one idempotent schema job
→ one private Cloud Run deployment
→ deployment verification
```

It uses these established resources by default:

```text
Project: syntaxmatrix-media-prod-2026
Region: europe-west1
Service: syntaxmatrix-media-studio
Cloud SQL: syntaxmatrix-media-postgres
Database URL secret: smx_database_url_vault
GCS bucket: syntaxmatrix-media-prod-2026-syntaxmatrix-media
Image tag: gate1-final-voice-durability-001
```

No secret value is printed by the script.

### 4. Start the private proxy

In PowerShell:

```powershell
gcloud run services proxy syntaxmatrix-media-studio --region europe-west1 --port=9091
```

Open:

```text
http://localhost:9091/tasks/clone-voice
```

Use `Ctrl+F5` once after the new revision is ready.

## Final private acceptance test

Perform this single workflow:

```text
1. Log in as user A.
2. Save a WAV voice.
3. Confirm it appears under My saved voices.
4. Play its preview from the icon; no Result player should appear.
5. Generate narration; the Result player should appear.
6. Log out and log back in; the saved voice must remain.
7. Log in as user B; user A's voice must not appear.
8. Save user B's voice and confirm isolation.
9. Log in as admin; both real workspaces must appear and mock workspaces must not.
10. Add or inspect a system voice and confirm clients can see it after a new revision/restart.
```

## Existing saved voices

Real `ws_fb_...` voice identities created before this correction may have their preview audio in GCS but their provider voice IDs were written only to an old Cloud Run container filesystem. A preview file does not contain that provider identity. Such a voice must be recreated once after this deployment unless its original provider ID can be recovered from an old container or independent backup.

After recreation, the provider ID is stored in PostgreSQL and the preview is stored in GCS, so future revisions no longer lose the voice.

## Rollback

The deployment script does not make the service public. If final acceptance fails, route traffic back to the prior known-good Cloud Run revision from the Google Cloud console or with `gcloud run services update-traffic`. Do not delete Cloud SQL or GCS; they contain the durable production records.

## Completion status

```text
Final Gate 1 — code and local acceptance complete
Final Gate 1 — live private acceptance pending deployment by the account owner
Final Gate 2 — billing/security final verification follows only after Gate 1 live acceptance
Final Gate 3 — release/public-access closure follows only after Gate 2
```
