#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"
CSS="$ROOT/frontend/styles.css"
SERVER="$ROOT/app.py"

if [ ! -f "$APP" ] || [ ! -f "$CSS" ] || [ ! -f "$SERVER" ]; then
  echo "ERROR: Run this from the Flask project root where app.py and frontend/ exist." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.asset-actions-$STAMP"
cp "$CSS" "$CSS.bak.asset-actions-$STAMP"
cp "$SERVER" "$SERVER.bak.asset-actions-$STAMP"

python - "$APP" "$CSS" "$SERVER" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])
server_path = Path(sys.argv[3])

app_js = app_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")
server = server_path.read_text(encoding="utf-8")

server = server.replace(
    "from flask import Flask, jsonify, request, send_from_directory",
    "from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context",
    1,
)

route = r'''
@app.route("/api/download-asset", methods=["GET"])
def download_asset():
    """Download a generated asset from a local path or remote Alibaba URL."""
    asset_url = (request.args.get("url") or "").strip()
    requested_name = secure_filename(request.args.get("filename") or "")

    if not asset_url:
        return _json_error("Missing asset URL.", 400)

    from urllib.parse import urlparse, unquote

    parsed = urlparse(asset_url)

    def choose_filename(content_type: str = "") -> str:
        if requested_name:
            return requested_name
        guessed = secure_filename(unquote(pathlib.PurePosixPath(parsed.path).name or ""))
        if guessed:
            return guessed
        ext = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
        return f"alibaba_generated_asset{ext}"

    local_path = asset_url.lstrip("/")
    if not parsed.scheme and local_path.startswith("uploads/"):
        rel = local_path[len("uploads/"):]
        return send_from_directory(UPLOADS_DIR, rel, as_attachment=True, download_name=choose_filename())

    if not parsed.scheme and local_path.startswith("generated/"):
        rel = local_path[len("generated/"):]
        return send_from_directory(GENERATED_DIR, rel, as_attachment=True, download_name=choose_filename())

    if parsed.scheme not in {"http", "https"}:
        return _json_error("Only http(s), uploads/, and generated/ asset URLs can be downloaded.", 400)

    try:
        import requests  # type: ignore
        remote = requests.get(
            asset_url,
            stream=True,
            timeout=(10, 180),
            headers={"User-Agent": "AlibabaMediaStudio/1.0"},
        )
    except Exception as exc:
        return _json_error(f"Could not reach generated asset URL: {exc}", 502)

    if remote.status_code >= 400:
        details = ""
        try:
            details = remote.text[:500]
        except Exception:
            pass
        remote.close()
        return _json_error(f"Generated asset URL returned HTTP {remote.status_code}.", 502, details=details)

    content_type = remote.headers.get("Content-Type") or "application/octet-stream"
    download_name = choose_filename(content_type)

    def generate():
        try:
            for chunk in remote.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk
        finally:
            remote.close()

    headers = {
        "Content-Type": content_type,
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Cache-Control": "no-store",
    }

    if remote.headers.get("Content-Length"):
        headers["Content-Length"] = remote.headers["Content-Length"]

    return Response(stream_with_context(generate()), headers=headers)

'''

if "def download_asset():" not in server:
    marker = '@app.route("/uploads/<path:filename>")'
    if marker not in server:
        raise SystemExit("Could not find location to insert /api/download-asset route in app.py")
    server = server.replace(marker, route + marker, 1)

app_js = re.sub(
    r"\n// BEGIN_ASSET_ACTIONS_PATCH[\s\S]*?// END_ASSET_ACTIONS_PATCH\n?",
    "\n",
    app_js,
)

asset_actions_js = r'''

// BEGIN_ASSET_ACTIONS_PATCH
function makeAssetFilename(job) {
  try {
    const url = new URL(job.assetUrl, window.location.href);
    const last = decodeURIComponent(url.pathname.split('/').filter(Boolean).pop() || '');
    if (last && last.includes('.')) return last;
  } catch {}

  const extByType = { image: 'png', video: 'mp4', audio: 'mp3' };
  const ext = extByType[job.outputType] || 'bin';
  const workflow = (job.workflow || job.workflowLabel || 'asset')
    .toString()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'asset';

  return `${workflow}-${job.id || Date.now()}.${ext}`;
}

function assetDownloadUrl(job) {
  const base = state?.settings?.apiBaseUrl || window.location.origin;
  const query = new URLSearchParams({
    url: job.assetUrl,
    filename: makeAssetFilename(job)
  });

  return joinUrl(base, `/api/download-asset?${query.toString()}`);
}

function renderResultActions(job) {
  if (!job?.assetUrl) return '';

  const openUrl = escapeAttribute(job.assetUrl);
  const downloadUrl = escapeAttribute(assetDownloadUrl(job));
  const copyUrl = escapeAttribute(job.assetUrl);

  return `
    <div class="result-actions" aria-label="Generated asset actions">
      <a class="asset-action primary" href="${openUrl}" target="_blank" rel="noopener noreferrer">Open full asset</a>
      <a class="asset-action" href="${downloadUrl}">Download</a>
      <button class="asset-action" type="button" data-copy-asset-url="${copyUrl}">Copy URL</button>
    </div>
  `;
}

function renderResultPreview(job) {
  if (job.status === 'running') return '<span>Submitting request to Flask…</span>';

  if (!job.assetUrl) {
    const msg = job.message || 'No asset URL returned yet.';
    return `<span>${escapeHtml(msg)}</span>`;
  }

  const url = escapeAttribute(job.assetUrl);
  const actions = renderResultActions(job);

  if (job.outputType === 'image') {
    return `
      <div class="result-media-stack">
        <div class="result-media-shell">
          <img src="${url}" alt="Generated image" onerror="this.closest('.result-media-shell')?.classList.add('preview-error')" />
          <p class="preview-error-message">Preview could not load inside the browser. Use Open full asset or Download.</p>
        </div>
        ${actions}
      </div>
    `;
  }

  if (job.outputType === 'video') {
    return `
      <div class="result-media-stack">
        <div class="result-media-shell">
          <video src="${url}" controls playsinline onerror="this.closest('.result-media-shell')?.classList.add('preview-error')"></video>
          <p class="preview-error-message">Video preview could not load inside the browser. Use Open full asset or Download.</p>
        </div>
        ${actions}
      </div>
    `;
  }

  if (job.outputType === 'audio') {
    return `
      <div class="result-media-stack">
        <audio src="${url}" controls></audio>
        ${actions}
      </div>
    `;
  }

  return `
    <div class="result-media-stack">
      <a href="${url}" target="_blank" rel="noopener noreferrer">Open generated asset</a>
      ${actions}
    </div>
  `;
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-copy-asset-url]');
  if (!button) return;

  event.preventDefault();
  const assetUrl = button.dataset.copyAssetUrl || '';

  try {
    await navigator.clipboard.writeText(assetUrl);
    toast('Asset URL copied', 'The generated asset URL is now on your clipboard.');
  } catch {
    window.prompt('Copy generated asset URL:', assetUrl);
  }
});
// END_ASSET_ACTIONS_PATCH
'''

app_js = app_js.rstrip() + asset_actions_js + "\n"

css = re.sub(
    r"\n/\* BEGIN_ASSET_ACTIONS_PATCH \*/[\s\S]*?/\* END_ASSET_ACTIONS_PATCH \*/\n?",
    "\n",
    css,
)

asset_actions_css = r'''

/* BEGIN_ASSET_ACTIONS_PATCH */
.result-media-stack {
  width: 100%;
  display: grid;
  gap: 0.85rem;
  justify-items: center;
}

.result-media-shell {
  width: 100%;
  display: grid;
  place-items: center;
  gap: 0.65rem;
}

.preview-error-message {
  display: none;
  margin: 0;
  color: var(--muted-strong);
  line-height: 1.45;
}

.result-media-shell.preview-error .preview-error-message {
  display: block;
}

.result-media-shell.preview-error img,
.result-media-shell.preview-error video {
  display: none;
}

.result-actions {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  justify-content: center;
}

.asset-action {
  min-height: 2.65rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  padding: 0.72rem 1rem;
  text-decoration: none;
  font-weight: 850;
  cursor: pointer;
}

.asset-action.primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
  color: #071512;
}

.asset-action:hover {
  transform: translateY(-1px);
}

@media (max-width: 560px) {
  .result-actions,
  .asset-action {
    width: 100%;
  }
}
/* END_ASSET_ACTIONS_PATCH */
'''

css = css.rstrip() + asset_actions_css + "\n"

app_path.write_text(app_js, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
server_path.write_text(server, encoding="utf-8")
PY

echo "Patch complete. Added Open / Download / Copy URL controls."
echo "Changed:"
echo "  app.py"
echo "  frontend/app.js"
echo "  frontend/styles.css"
echo
echo "Restart with: python app.py"
