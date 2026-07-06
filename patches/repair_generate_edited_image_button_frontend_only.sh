#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"

if [ ! -f "$APP" ]; then
  echo "ERROR: Run this from the project root where frontend/app.js exists." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.repair-edit-button-$STAMP"

python - "$APP" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
app = app_path.read_text(encoding="utf-8")

# Remove old copy of this repair if it exists.
app = re.sub(
    r"\n// BEGIN_FORCE_EDIT_SUBMIT_PATCH[\s\S]*?// END_FORCE_EDIT_SUBMIT_PATCH\n?",
    "\n",
    app,
)

repair = r'''

// BEGIN_FORCE_EDIT_SUBMIT_PATCH
// Frontend-only repair for Edit → Image / Image → Video upload submission.
// Does not touch backend. Sends real files as multipart/form-data using the field name "image".
(function forceMultipartImageSubmitPatch() {
  const PATCH_NAME = 'forceMultipartImageSubmitPatch';

  function log(...args) {
    console.log(`[${PATCH_NAME}]`, ...args);
  }

  function fail(title, detail) {
    console.error(`[${PATCH_NAME}] ${title}`, detail || '');
    if (typeof toast === 'function') {
      toast(title, detail || 'Check the browser console for details.');
    } else {
      alert(`${title}\n${detail || ''}`);
    }
  }

  function currentWorkflow() {
    try {
      if (typeof activeWorkflow !== 'undefined' && activeWorkflow) return activeWorkflow;
      if (typeof state !== 'undefined' && state?.activeWorkflow) return state.activeWorkflow;
    } catch {}
    return document.querySelector('.tab.active')?.dataset?.workflow || 'textToImage';
  }

  function getApiBaseUrl() {
    try {
      if (typeof state !== 'undefined' && state?.settings?.apiBaseUrl) {
        return state.settings.apiBaseUrl.replace(/\/+$/, '');
      }
    } catch {}

    return window.location.origin.replace(/\/+$/, '');
  }

  function endpointFor(workflow) {
    try {
      if (typeof getEndpoint === 'function') {
        return getEndpoint(workflow);
      }
    } catch {}

    const defaults = {
      textToImage: '/api/media/text-to-image',
      editToImage: '/api/media/edit-to-image',
      textToVideo: '/api/media/text-to-video',
      imageToVideo: '/api/media/image-to-video',
      voiceClone: '/api/media/voice-clone'
    };

    return defaults[workflow] || defaults.editToImage;
  }

  function joinApiUrl(base, endpoint) {
    const cleanBase = String(base || '').replace(/\/+$/, '');
    const cleanEndpoint = String(endpoint || '').replace(/^\/+/, '');
    return `${cleanBase}/${cleanEndpoint}`;
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

  function getImageFilesInFrontendOrder() {
    try {
      if (typeof selectedImageFiles === 'function') {
        const files = selectedImageFiles();
        if (Array.isArray(files) && files.length) return files;
      }
    } catch (error) {
      console.warn(`[${PATCH_NAME}] selectedImageFiles() failed`, error);
    }

    try {
      if (typeof selectedImages !== 'undefined' && Array.isArray(selectedImages)) {
        const files = selectedImages.filter(file => file instanceof File);
        if (files.length) return files;
      }
    } catch (error) {
      console.warn(`[${PATCH_NAME}] selectedImages fallback failed`, error);
    }

    const fileInput =
      document.querySelector('input[type="file"][accept*="image"]') ||
      document.querySelector('input[type="file"]');

    return fileInput?.files ? [...fileInput.files] : [];
  }

  function appendOptionalField(formData, key, value) {
    if (value === undefined || value === null || value === '') return;
    formData.append(key, String(value));
  }

  function buildImageFormData(workflow) {
    const prompt = getPromptValue();
    const model = getModelValue();
    const imageFiles = getImageFilesInFrontendOrder();

    if (!prompt) {
      fail('Prompt required', 'Write the edit instruction before generating.');
      return null;
    }

    if (!imageFiles.length) {
      fail('Images required', 'Upload Image 1, Image 2 and Image 3 before generating.');
      return null;
    }

    if (workflow === 'editToImage' && imageFiles.length > 3) {
      fail('Too many images', 'Edit → Image should send a maximum of 3 images.');
      return null;
    }

    const formData = new FormData();

    appendOptionalField(formData, 'workflow', workflow);
    appendOptionalField(formData, 'prompt', prompt);
    appendOptionalField(formData, 'model', model);

    try {
      if (typeof els !== 'undefined') {
        appendOptionalField(formData, 'size', els?.sizeSelect?.value);
        appendOptionalField(formData, 'resolution', els?.resolutionSelect?.value);
        appendOptionalField(formData, 'duration', els?.durationSelect?.value);
        appendOptionalField(formData, 'seed', els?.seedInput?.value?.trim());
        appendOptionalField(formData, 'quality', els?.qualitySelect?.value);
        appendOptionalField(formData, 'negativePrompt', els?.negativePromptInput?.value?.trim());
        appendOptionalField(formData, 'watermark', els?.watermarkInput?.checked ? 'true' : 'false');
        appendOptionalField(formData, 'promptExtend', els?.promptExtendInput?.checked ? 'true' : 'false');
      }
    } catch {}

    imageFiles.forEach((file, index) => {
      // IMPORTANT:
      // Your backend should read these with request.files.getlist("image").
      // Order is preserved:
      // files[0] = Image 1
      // files[1] = Image 2
      // files[2] = Image 3
      formData.append('image', file, file.name);
      formData.append('imageLabel', `Image ${index + 1}`);
      formData.append('imageName', file.name);
    });

    log('Prepared multipart upload:', {
      workflow,
      prompt,
      model,
      imageCount: imageFiles.length,
      imageNames: imageFiles.map(file => file.name)
    });

    return formData;
  }

  async function submitImageWorkflow(event) {
    const workflow = currentWorkflow();

    if (workflow !== 'editToImage' && workflow !== 'imageToVideo') {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const formData = buildImageFormData(workflow);
    if (!formData) return;

    const button =
      (typeof els !== 'undefined' && els?.submitButton) ||
      event.currentTarget ||
      document.querySelector('button[type="submit"]');

    const oldText = button?.textContent;

    try {
      if (button) {
        button.disabled = true;
        button.textContent = workflow === 'editToImage'
          ? 'Generating edited image...'
          : 'Generating video...';
      }

      const url = joinApiUrl(getApiBaseUrl(), endpointFor(workflow));
      log('POST', url);

      const response = await fetch(url, {
        method: 'POST',
        body: formData
      });

      const text = await response.text();

      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { message: text };
      }

      if (!response.ok) {
        throw new Error(data?.message || data?.error || `HTTP ${response.status}: ${text}`);
      }

      log('Backend response:', data);

      if (typeof renderResult === 'function') {
        renderResult(data, { workflow, prompt: getPromptValue(), model: getModelValue() });
      }

      if (typeof toast === 'function') {
        toast('Request sent successfully', 'The backend received the uploaded image files.');
      } else {
        alert('Request sent successfully. The backend received the uploaded image files.');
      }
    } catch (error) {
      fail('Generate edited image failed', error?.message || String(error));
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = oldText || 'Generate edited image';
      }
    }
  }

  function bind() {
    const submitButton =
      (typeof els !== 'undefined' && els?.submitButton) ||
      document.querySelector('button[type="submit"]') ||
      [...document.querySelectorAll('button')].find(btn =>
        /generate/i.test(btn.textContent || '')
      );

    if (!submitButton) {
      console.warn(`[${PATCH_NAME}] No generate button found yet.`);
      return;
    }

    if (submitButton.dataset.forceMultipartPatchBound === 'true') {
      return;
    }

    submitButton.dataset.forceMultipartPatchBound = 'true';

    // Capture phase intentionally runs before the older/broken submit handler.
    submitButton.addEventListener('click', submitImageWorkflow, true);

    const form = submitButton.closest('form');
    if (form && form.dataset.forceMultipartPatchBound !== 'true') {
      form.dataset.forceMultipartPatchBound = 'true';
      form.addEventListener('submit', submitImageWorkflow, true);
    }

    log('Generate button repaired for Edit → Image / Image → Video.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }

  window.__debugAlibabaMediaUpload = function debugAlibabaMediaUpload() {
    const workflow = currentWorkflow();
    const files = getImageFilesInFrontendOrder();

    console.table(files.map((file, index) => ({
      slot: `Image ${index + 1}`,
      name: file.name,
      type: file.type,
      sizeKB: Math.round(file.size / 1024)
    })));

    return {
      workflow,
      prompt: getPromptValue(),
      model: getModelValue(),
      imageCount: files.length,
      imageNames: files.map(file => file.name)
    };
  };
})();
// END_FORCE_EDIT_SUBMIT_PATCH
'''

app = app.rstrip() + "\n" + repair + "\n"
app_path.write_text(app, encoding="utf-8")
PY

echo "Frontend-only button repair applied."
echo "Changed only:"
echo "  frontend/app.js"
echo
echo "Backup saved as:"
echo "  frontend/app.js.bak.repair-edit-button-$STAMP"
echo
echo "Restart:"
echo "  python app.py"
