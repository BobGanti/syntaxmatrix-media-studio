#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"

if [ ! -f "$APP" ]; then
  echo "ERROR: Run this from the project root where frontend/app.js exists." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.restore-json-upload-$STAMP"

python - "$APP" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
app = app_path.read_text(encoding="utf-8")

# Remove the previous forced multipart button patch.
app = re.sub(
    r"\n// BEGIN_FORCE_EDIT_SUBMIT_PATCH[\s\S]*?// END_FORCE_EDIT_SUBMIT_PATCH\n?",
    "\n",
    app,
)

# Remove older copy of this repair if present.
app = re.sub(
    r"\n// BEGIN_JSON_DATA_URL_UPLOAD_REPAIR[\s\S]*?// END_JSON_DATA_URL_UPLOAD_REPAIR\n?",
    "\n",
    app,
)

repair = r'''

// BEGIN_JSON_DATA_URL_UPLOAD_REPAIR
// Frontend-only repair.
// Uploaded files stay in the browser until Generate is clicked.
// Then the frontend sends JSON:
//   images[0] = Image 1 as data URL
//   images[1] = Image 2 as data URL
//   images[2] = Image 3 as data URL
// This avoids the backend UTF-8 error caused by sending raw multipart bytes.
(function jsonDataUrlUploadRepair() {
  function safeToast(title, message) {
    if (typeof toast === 'function') {
      toast(title, message);
    } else {
      alert(`${title}\n${message || ''}`);
    }
  }

  function currentWorkflow() {
    try {
      if (typeof activeWorkflow !== 'undefined' && activeWorkflow) return activeWorkflow;
      if (typeof state !== 'undefined' && state?.activeWorkflow) return state.activeWorkflow;
    } catch {}
    return document.querySelector('.tab.active')?.dataset?.workflow || 'textToImage';
  }

  function getPromptValue() {
    try {
      if (typeof els !== 'undefined' && els?.promptInput) {
        return els.promptInput.value.trim();
      }
    } catch {}

    return (
      document.querySelector('#prompt')?.value ||
      document.querySelector('#promptInput')?.value ||
      document.querySelector('textarea')?.value ||
      ''
    ).trim();
  }

  function getModelValue() {
    try {
      if (typeof els !== 'undefined' && els?.modelSelect) {
        return els.modelSelect.value;
      }
    } catch {}

    return (
      document.querySelector('#model')?.value ||
      document.querySelector('#modelSelect')?.value ||
      document.querySelector('select[name="model"]')?.value ||
      ''
    );
  }

  function getOrderedImageFiles() {
    try {
      if (typeof selectedImageFiles === 'function') {
        const files = selectedImageFiles();
        if (Array.isArray(files) && files.length) return files;
      }
    } catch {}

    try {
      if (typeof selectedImages !== 'undefined' && Array.isArray(selectedImages)) {
        const files = selectedImages.filter(file => file instanceof File);
        if (files.length) return files;
      }
    } catch {}

    const input =
      document.querySelector('input[type="file"][accept*="image"]') ||
      document.querySelector('input[type="file"]');

    return input?.files ? [...input.files] : [];
  }

  function browserFileToDataUrl(file) {
    if (typeof fileToDataUrl === 'function') {
      return fileToDataUrl(file);
    }

    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('Could not read uploaded file.'));
      reader.readAsDataURL(file);
    });
  }

  function getOptionalUiValue(name) {
    try {
      if (typeof els === 'undefined') return undefined;

      const map = {
        size: els.sizeSelect?.value,
        resolution: els.resolutionSelect?.value,
        duration: els.durationSelect?.value,
        seed: els.seedInput?.value?.trim(),
        quality: els.qualitySelect?.value,
        negativePrompt: els.negativePromptInput?.value?.trim(),
        watermark: els.watermarkInput?.checked,
        promptExtend: els.promptExtendInput?.checked,
        voiceName: els.voiceNameInput?.value?.trim()
      };

      return map[name];
    } catch {
      return undefined;
    }
  }

  buildPayload = async function buildPayload() {
    const workflow = currentWorkflow();
    const prompt = getPromptValue();

    if (!prompt) {
      safeToast('Prompt required', 'Write the generation instruction before clicking Generate.');
      return null;
    }

    const payload = {
      workflow,
      model: getModelValue(),
      prompt,
      quality: getOptionalUiValue('quality'),
      watermark: Boolean(getOptionalUiValue('watermark')),
      promptExtend: Boolean(getOptionalUiValue('promptExtend')),
      negativePrompt: getOptionalUiValue('negativePrompt') || ''
    };

    if (workflow === 'textToImage' || workflow === 'editToImage') {
      payload.size = getOptionalUiValue('size');
    }

    if (workflow === 'textToVideo' || workflow === 'imageToVideo') {
      payload.resolution = getOptionalUiValue('resolution');
      payload.duration = Number(getOptionalUiValue('duration') || 5);
    }

    const seed = getOptionalUiValue('seed');
    if (seed) payload.seed = Number(seed);

    if (workflow === 'editToImage' || workflow === 'imageToVideo') {
      const files = getOrderedImageFiles();

      if (!files.length) {
        safeToast('Images required', 'Upload Image 1, Image 2 and Image 3 before generating.');
        return null;
      }

      if (workflow === 'editToImage' && files.length > 3) {
        safeToast('Too many images', 'Edit → Image accepts a maximum of 3 images.');
        return null;
      }

      payload.images = await Promise.all(files.map(browserFileToDataUrl));
      payload.imageNames = files.map(file => file.name);
      payload.imageLabels = files.map((_, index) => `Image ${index + 1}`);
      payload.imageUrl = payload.images[0];

      console.log('[AlibabaMedia] JSON upload prepared:', {
        workflow,
        imageCount: files.length,
        imageNames: payload.imageNames
      });
    }

    try {
      if (workflow === 'voiceClone' && typeof selectedVoiceFile !== 'undefined' && selectedVoiceFile) {
        payload.voiceName = getOptionalUiValue('voiceName') || 'smxVoice';
        payload.audio = await browserFileToDataUrl(selectedVoiceFile);
        payload.audioName = selectedVoiceFile.name;
      }
    } catch {}

    return payload;
  };

  callBackend = async function callBackend(endpointKey, payload) {
    const apiBaseUrl =
      typeof state !== 'undefined' && state?.settings?.apiBaseUrl
        ? state.settings.apiBaseUrl
        : window.location.origin;

    const endpoint =
      typeof getEndpoint === 'function'
        ? getEndpoint(endpointKey)
        : `/api/media/${String(endpointKey || '').replace(/[A-Z]/g, m => '-' + m.toLowerCase())}`;

    const url =
      typeof joinUrl === 'function'
        ? joinUrl(apiBaseUrl, endpoint)
        : `${String(apiBaseUrl).replace(/\/+$/, '')}/${String(endpoint).replace(/^\/+/, '')}`;

    console.log('[AlibabaMedia] POST JSON:', url);

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
      throw new Error(data?.message || data?.error || `HTTP ${response.status}`);
    }

    return data;
  };

  window.__debugAlibabaMediaUpload = function debugAlibabaMediaUpload() {
    const files = getOrderedImageFiles();

    console.table(files.map((file, index) => ({
      slot: `Image ${index + 1}`,
      name: file.name,
      type: file.type,
      sizeKB: Math.round(file.size / 1024)
    })));

    return {
      workflow: currentWorkflow(),
      prompt: getPromptValue(),
      model: getModelValue(),
      imageCount: files.length,
      imageNames: files.map(file => file.name)
    };
  };

  console.log('[AlibabaMedia] JSON data URL upload repair active.');
})();
// END_JSON_DATA_URL_UPLOAD_REPAIR
'''

app = app.rstrip() + "\n" + repair + "\n"
app_path.write_text(app, encoding="utf-8")
PY

echo "Frontend JSON upload repair applied."
echo "Changed only:"
echo "  frontend/app.js"
echo
echo "Backup saved as:"
echo "  frontend/app.js.bak.restore-json-upload-$STAMP"
echo
echo "Restart:"
echo "  python app.py"
