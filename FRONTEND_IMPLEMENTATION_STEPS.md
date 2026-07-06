# Frontend implementation steps

## Step 1 — Preserve the Alibaba generation scripts

The existing Python scripts were kept in place. The frontend was added as a separate `frontend/` layer so the model experiments remain untouched.

## Step 2 — Add an enterprise studio shell

The new shell includes:

- Sidebar navigation
- Mobile hamburger menu
- Hero/status area
- KPI cards
- Creation console
- Live output preview
- Generation history
- Model registry
- Backend settings

## Step 3 — Add workflow-specific forms

The creation console supports five workflows:

1. Text to Image
2. Edit to Image
3. Text to Video
4. Image to Video
5. Voice Clone

Each workflow swaps the model list, required media inputs, output options and validation rules.

## Step 4 — Add a backend adapter contract

The frontend calls JSON endpoints configured in the Settings section. The default base URL is:

```text
http://127.0.0.1:5055
```

The defaults are intentionally editable because your current zip contains direct Python scripts rather than a web API server.

## Step 5 — Add local history and previews

Generation jobs are stored in browser local storage. When the backend returns an `imageUrl`, `videoUrl`, `audioUrl`, `assetUrl` or `url`, the asset is previewed automatically.

## Step 6 — Make the UI production-friendly

The UI includes responsive breakpoints, accessible labels, form validation, safe error handling, toast notifications, dark/light themes and no external frontend dependencies.

## Step 7 — Run the frontend

```bash
cd frontend
python -m http.server 5173
```

Open:

```text
http://127.0.0.1:5173
```

## Step 8 — Connect the backend

Expose your Alibaba generation functions behind HTTP endpoints, then set those endpoint paths in the frontend Settings panel. The frontend is already ready to submit requests.
