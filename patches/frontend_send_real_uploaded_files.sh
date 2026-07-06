#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"

if [ ! -f "$APP" ]; then
  echo "ERROR: Run from the project root where frontend/app.js exists." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.real-file-upload-$STAMP"

python - "$APP" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
app = app_path.read_text(encoding="utf-8")

if "REAL_FILE_UPLOAD_PATCH" in app:
    print("Real file upload patch already present; leaving frontend/app.js unchanged.")
    app_path.write_text(app, encoding="utf-8")
    raise SystemExit(0)

# 1. Add constants near the top.
marker = "const STORAGE_KEY = 'alibaba-media-studio-state-v1';"
replacement = """const STORAGE_KEY = 'alibaba-media-studio-state-v1';

// REAL_FILE_UPLOAD_PATCH
// The backend should receive uploaded files as real multipart files.
// If your Flask backend uses request.files.getlist("image"), keep this as "image".
// If your backend expects "images", change this single value to "images".
const IMAGE_UPLOAD_FIELD_NAME = 'image';
const VOICE_UPLOAD_FIELD_NAME = 'audio';
"""
if marker not in app:
    raise SystemExit("Could not find STORAGE_KEY marker in frontend/app.js")

app = app.replace(marker, replacement, 1)

# 2. Replace image payload conversion: do not convert images to base64.
old_image_block = """  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && imageFiles.length) {
    payload.images = await Promise.all(imageFiles.map(fileToDataUrl));
    payload.imageNames = imageFiles.map(file => file.name);
    payload.imageLabels = imageFiles.map((_, index) => `Image ${index + 1}`);
    payload.imageUrl = payload.images[0];
  }"""

new_image_block = """  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && imageFiles.length) {
    // Keep actual browser File objects.
    // They will be sent as multipart/form-data in callBackend().
    payload.imageFiles = imageFiles;
    payload.imageNames = imageFiles.map(file => file.name);
    payload.imageLabels = imageFiles.map((_, index) => `Image ${index + 1}`);
  }"""

if old_image_block not in app:
    raise SystemExit("Could not find image base64 payload block. Your app.js may be different.")

app = app.replace(old_image_block, new_image_block, 1)

# 3. Replace voice payload conversion: keep actual audio File object too.
old_voice_block = """  if (selectedVoiceFile) {
    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';
    payload.audio = await fileToDataUrl(selectedVoiceFile);
    payload.audioName = selectedVoiceFile.name;
  }"""

new_voice_block = """  if (activeWorkflow === 'voiceClone' && selectedVoiceFile) {
    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';
    payload.audioFile = selectedVoiceFile;
    payload.audioName = selectedVoiceFile.name;
  }"""

if old_voice_block in app:
    app = app.replace(old_voice_block, new_voice_block, 1)

# 4. Add helper that converts payload to FormData only when files exist.
helper = r'''
function payloadHasFiles(payload) {
  return Boolean(
    payload?.imageFiles?.length ||
    payload?.audioFile instanceof File
  );
}

function appendValueToFormData(formData, key, value) {
  if (value === undefined || value === null) return;

  if (Array.isArray(value)) {
    formData.append(key, JSON.stringify(value));
    return;
  }

  if (typeof value === 'object') {
    formData.append(key, JSON.stringify(value));
    return;
  }

  formData.append(key, String(value));
}

function buildMultipartFormData(payload) {
  const formData = new FormData();

  Object.entries(payload).forEach(([key, value]) => {
    if (key === 'imageFiles' || key === 'audioFile') return;
    appendValueToFormData(formData, key, value);
  });

  if (payload.imageFiles?.length) {
    payload.imageFiles.forEach((file, index) => {
      // Important:
      // These are appended in the exact slot order:
      // first file = Image 1, second file = Image 2, third file = Image 3.
      formData.append(IMAGE_UPLOAD_FIELD_NAME, file, file.name);
      formData.append('imageOrder', String(index + 1));
    });
  }

  if (payload.audioFile instanceof File) {
    formData.append(VOICE_UPLOAD_FIELD_NAME, payload.audioFile, payload.audioFile.name);
  }

  return formData;
}

'''

if "function payloadHasFiles(payload)" not in app:
    app = app.replace("async function callBackend(endpointKey, payload) {", helper + "\nasync function callBackend(endpointKey, payload) {", 1)

# 5. Replace callBackend to use multipart when files are present.
old_call_backend = r'''async function callBackend(endpointKey, payload) {
  const url = joinUrl(state.settings.apiBaseUrl, getEndpoint(endpointKey));
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }

  if (!response.ok) {
    const reason = data?.message || data?.error || `HTTP ${response.status}`;
    throw new Error(reason);
  }

  return data;
}'''

new_call_backend = r'''async function callBackend(endpointKey, payload) {
  const url = joinUrl(state.settings.apiBaseUrl, getEndpoint(endpointKey));

  const hasFiles = payloadHasFiles(payload);

  const fetchOptions = hasFiles
    ? {
        method: 'POST',
        // Do NOT manually set Content-Type for FormData.
        // The browser must add the multipart boundary itself.
        body: buildMultipartFormData(payload)
      }
    : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      };

  const response = await fetch(url, fetchOptions);

  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }

  if (!response.ok) {
    const reason = data?.message || data?.error || `HTTP ${response.status}`;
    throw new Error(reason);
  }

  return data;
}'''

if old_call_backend not in app:
    raise SystemExit("Could not find callBackend() block to replace.")

app = app.replace(old_call_backend, new_call_backend, 1)

app_path.write_text(app, encoding="utf-8")
PY

echo "Frontend real file upload patch complete."
echo "Changed only:"
echo "  frontend/app.js"
echo
echo "Backup saved as:"
echo "  frontend/app.js.bak.real-file-upload-$STAMP"
echo
echo "Restart:"
echo "  python app.py"
