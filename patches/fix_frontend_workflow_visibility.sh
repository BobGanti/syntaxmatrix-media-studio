#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"
CSS="$ROOT/frontend/styles.css"

if [ ! -f "$APP" ] || [ ! -f "$CSS" ]; then
  echo "ERROR: Run this from the AlibabaMedia project root, or pass the project path as the first argument." >&2
  echo "Expected files:" >&2
  echo "  $APP" >&2
  echo "  $CSS" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.workflow-ui-$STAMP"
cp "$CSS" "$CSS.bak.workflow-ui-$STAMP"

python - "$APP" "$CSS" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])

app = app_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

visibility_css = """
/* Workflow visibility guard: hidden must win over component display rules. */
[hidden],
.is-hidden {
  display: none !important;
}

.workflow-notice {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--brand) 10%, var(--surface-muted));
  padding: 1rem;
  display: grid;
  gap: 0.35rem;
}

.workflow-notice strong,
.workflow-notice p {
  margin: 0;
}

.workflow-notice p {
  color: var(--muted);
  line-height: 1.45;
}
""".strip()

if "Workflow visibility guard" not in css:
    css = css.replace(
        "* {\n  box-sizing: border-box;\n}",
        "* {\n  box-sizing: border-box;\n}\n\n" + visibility_css,
        1,
    )

new_set_workflow = r'''function setWorkflow(workflow, options = {}) {
  if (!MODEL_REGISTRY[workflow]) workflow = 'textToImage';

  activeWorkflow = workflow;
  const config = MODEL_REGISTRY[workflow];

  const ui = {
    textToImage: {
      promptLabel: 'Image prompt',
      promptPlaceholder: 'Describe the image you want to generate. No upload is required for Text → Image.',
      noticeTitle: 'Text → Image',
      noticeBody: 'This mode only needs a prompt, model, image size and optional seed. The image upload area is hidden because no source image is required.',
      showImages: false,
      showVoice: false,
      showSize: true,
      showVideo: false,
      showSeed: true,
      showQuality: true,
      showAdvanced: true,
      showPromptChips: true,
      submitLabel: 'Generate image'
    },
    editToImage: {
      promptLabel: 'Edit instruction',
      promptPlaceholder: 'Describe exactly how the uploaded image should be edited.',
      noticeTitle: 'Edit → Image',
      noticeBody: 'This mode requires one to three reference images plus an edit instruction. Video controls are hidden.',
      showImages: true,
      showVoice: false,
      showSize: true,
      showVideo: false,
      showSeed: true,
      showQuality: true,
      showAdvanced: true,
      showPromptChips: false,
      submitLabel: 'Generate edited image'
    },
    textToVideo: {
      promptLabel: 'Video prompt',
      promptPlaceholder: 'Describe the scene, camera movement, visual style and motion. No image upload is required for Text → Video.',
      noticeTitle: 'Text → Video',
      noticeBody: 'This mode only needs a video prompt, model, resolution and duration. Image upload and image-size controls are hidden.',
      showImages: false,
      showVoice: false,
      showSize: false,
      showVideo: true,
      showSeed: true,
      showQuality: true,
      showAdvanced: true,
      showPromptChips: true,
      submitLabel: 'Generate video'
    },
    imageToVideo: {
      promptLabel: 'Animation instruction',
      promptPlaceholder: 'Describe how the uploaded image should move or animate.',
      noticeTitle: 'Image → Video',
      noticeBody: 'This mode requires a source image plus animation instructions. Image-size controls are hidden because the output is video.',
      showImages: true,
      showVoice: false,
      showSize: false,
      showVideo: true,
      showSeed: true,
      showQuality: true,
      showAdvanced: true,
      showPromptChips: false,
      submitLabel: 'Animate image'
    },
    voiceClone: {
      promptLabel: 'Voice script / narration text',
      promptPlaceholder: 'Write the narration text that the cloned voice should speak.',
      noticeTitle: 'Voice Clone',
      noticeBody: 'This mode only needs a voice name, clean source audio and narration text. Image and video controls are hidden.',
      showImages: false,
      showVoice: true,
      showSize: false,
      showVideo: false,
      showSeed: false,
      showQuality: false,
      showAdvanced: false,
      showPromptChips: false,
      submitLabel: 'Generate voice asset'
    }
  }[workflow];

  state.activeWorkflow = workflow;
  saveState();

  els.tabs.forEach(tab => {
    const isActive = tab.dataset.workflow === workflow;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
  });

  els.modelSelect.innerHTML = config.models
    .map(model => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
    .join('');

  if (!options.preservePrompt || !els.promptInput.value.trim()) {
    els.promptInput.value = config.defaultPrompt;
  }

  const promptLabel = document.querySelector('#promptGroup > span');
  if (promptLabel) promptLabel.textContent = ui.promptLabel;
  els.promptInput.placeholder = ui.promptPlaceholder;

  let notice = document.querySelector('#workflowNotice');
  if (!notice) {
    notice = document.createElement('div');
    notice.id = 'workflowNotice';
    notice.className = 'workflow-notice';
    const tabs = document.querySelector('.tabs');
    tabs?.insertAdjacentElement('afterend', notice);
  }

  notice.innerHTML = `<strong>${escapeHtml(ui.noticeTitle)}</strong><p>${escapeHtml(ui.noticeBody)}</p>`;

  const fields = {
    size: document.querySelector('[data-field="size"]'),
    resolution: document.querySelector('[data-field="resolution"]'),
    duration: document.querySelector('[data-field="duration"]'),
    seed: document.querySelector('[data-field="seed"]')
  };

  if (fields.size) fields.size.hidden = !ui.showSize;
  if (fields.resolution) fields.resolution.hidden = !ui.showVideo;
  if (fields.duration) fields.duration.hidden = !ui.showVideo;
  if (fields.seed) fields.seed.hidden = !ui.showSeed;

  const mediaOptions = document.querySelector('#mediaOptions');
  if (mediaOptions) mediaOptions.hidden = !(ui.showSize || ui.showVideo || ui.showSeed);

  const qualityGroup = els.qualitySelect?.closest('label');
  if (qualityGroup) qualityGroup.hidden = !ui.showQuality;

  const promptToolbar = document.querySelector('.prompt-toolbar');
  if (promptToolbar) promptToolbar.hidden = !ui.showPromptChips;

  const advancedPanel = els.advancedToggle?.closest('.advanced-panel');
  if (advancedPanel) advancedPanel.hidden = !ui.showAdvanced;

  if (!ui.showAdvanced && els.advancedContent) {
    els.advancedContent.hidden = true;
    els.advancedToggle?.setAttribute('aria-expanded', 'false');
    if (els.advancedToggle) els.advancedToggle.textContent = 'Show advanced controls';
  }

  els.imageUploadPanel.hidden = !ui.showImages;
  els.voiceUploadPanel.hidden = !ui.showVoice;

  if (els.imageFiles) {
    els.imageFiles.required = ui.showImages;
    els.imageFiles.disabled = !ui.showImages;
    els.imageFiles.multiple = workflow === 'editToImage';
  }

  if (els.voiceFile) {
    els.voiceFile.required = ui.showVoice;
    els.voiceFile.disabled = !ui.showVoice;
  }

  const imageTitle = els.imageUploadPanel?.querySelector('.field-title');
  const imageHelp = els.imageUploadPanel?.querySelector('p');
  const imageDropHint = els.imageUploadPanel?.querySelector('.dropzone span');

  if (imageTitle) imageTitle.textContent = workflow === 'imageToVideo' ? 'Source image' : 'Reference images';

  if (imageHelp) {
    imageHelp.textContent = workflow === 'imageToVideo'
      ? 'Upload the image Alibaba should animate into a video.'
      : 'Upload one to three source images for Alibaba image editing.';
  }

  if (imageDropHint) {
    imageDropHint.textContent = workflow === 'imageToVideo'
      ? 'PNG, JPG or WEBP. One source image is recommended.'
      : 'PNG, JPG or WEBP. Maximum 3 for edit-to-image.';
  }

  if (!ui.showImages) {
    selectedImages = [];
    if (els.imageFiles) els.imageFiles.value = '';
    renderImagePreviews();
  }

  if (!ui.showVoice) {
    selectedVoiceFile = null;
    if (els.voiceFile) els.voiceFile.value = '';
  }

  els.submitButton.textContent = ui.submitLabel;
  toast(config.label, WORKFLOW_DESCRIPTIONS[workflow]);
}'''

app, count = re.subn(
    r"function setWorkflow\(workflow, options = \{\}\) \{.*?\n\}\n\nasync function submitGeneration",
    new_set_workflow + "\n\nasync function submitGeneration",
    app,
    count=1,
    flags=re.S,
)

if count != 1:
    raise SystemExit("Could not replace setWorkflow(). The app.js structure may have changed.")

app = app.replace(
    "if (selectedImages.length) {\n    payload.images = await Promise.all(selectedImages.map(fileToDataUrl));",
    "if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && selectedImages.length) {\n    payload.images = await Promise.all(selectedImages.map(fileToDataUrl));",
)

app = app.replace(
    "if (selectedVoiceFile) {\n    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';",
    "if (activeWorkflow === 'voiceClone' && selectedVoiceFile) {\n    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';",
)

app_path.write_text(app, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
PY

echo "Frontend workflow visibility patched."
echo "Backups created beside app.js and styles.css."
echo "Restart with: python app.py"
