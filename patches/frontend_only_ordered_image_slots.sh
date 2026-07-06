#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"
CSS="$ROOT/frontend/styles.css"

if [ ! -f "$APP" ] || [ ! -f "$CSS" ]; then
  echo "ERROR: Run from the project root where frontend/app.js and frontend/styles.css exist." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.frontend-image-slots-$STAMP"
cp "$CSS" "$CSS.bak.frontend-image-slots-$STAMP"

python - "$APP" "$CSS" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])

app = app_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

# ---------- frontend/app.js only ----------
if "frontend-only ordered image slots" in app:
    print("frontend image slots patch already present; leaving app.js unchanged")
else:
    app = app.replace(
        "let selectedImages = [];\nlet selectedVoiceFile = null;",
        "let selectedImages = [null, null, null];\nlet pendingImageSlotIndex = null;\nlet selectedVoiceFile = null;",
        1,
    )

    helpers = r'''
// frontend-only ordered image slots: Image 1 / Image 2 / Image 3
function imageSlotLimit(workflow = activeWorkflow) {
  if (workflow === 'editToImage') return 3;
  if (workflow === 'imageToVideo') return 1;
  return 0;
}

function ensureImageSlots() {
  if (!Array.isArray(selectedImages)) {
    selectedImages = [null, null, null];
    return;
  }

  const compactFiles = selectedImages.filter(file => file instanceof File);
  selectedImages = [compactFiles[0] || null, compactFiles[1] || null, compactFiles[2] || null];
}

function resetSelectedImageSlots() {
  selectedImages = [null, null, null];
  pendingImageSlotIndex = null;
  if (els.imageFiles) els.imageFiles.value = '';
  renderImagePreviews();
}

function selectedImageEntries() {
  ensureImageSlots();
  return selectedImages
    .slice(0, imageSlotLimit())
    .map((file, slotIndex) => ({ file, slotIndex }))
    .filter(entry => entry.file instanceof File);
}

function selectedImageFiles() {
  return selectedImageEntries().map(entry => entry.file);
}

function hasImageSlotGap() {
  ensureImageSlots();
  const limit = imageSlotLimit();
  let foundEmptyBeforeFilled = false;

  for (let index = 0; index < limit; index += 1) {
    if (!selectedImages[index]) {
      foundEmptyBeforeFilled = true;
    } else if (foundEmptyBeforeFilled) {
      return true;
    }
  }

  return false;
}

function addImagesToSlots(fileList, preferredSlot = null) {
  ensureImageSlots();
  const limit = imageSlotLimit();
  if (!limit) return;

  const incoming = [...fileList].filter(file => file?.type?.startsWith('image/'));
  if (!incoming.length) return;

  let added = 0;
  const queue = incoming.slice();

  if (Number.isInteger(preferredSlot) && preferredSlot >= 0 && preferredSlot < limit && queue.length) {
    selectedImages[preferredSlot] = queue.shift();
    added += 1;
  }

  for (const file of queue) {
    const emptyIndex = selectedImages.slice(0, limit).findIndex(existing => !existing);
    if (emptyIndex === -1) break;
    selectedImages[emptyIndex] = file;
    added += 1;
  }

  if (incoming.length > added) {
    toast('Image limit applied', limit === 3
      ? 'Edit → Image accepts three ordered slots: Image 1, Image 2 and Image 3.'
      : 'Image → Video accepts one source image.');
  }

  renderImagePreviews();
}

function removeImageSlot(slotIndex) {
  ensureImageSlots();
  if (slotIndex < 0 || slotIndex > 2) return;
  selectedImages[slotIndex] = null;
  renderImagePreviews();
}

function openImageSlotPicker(slotIndex) {
  pendingImageSlotIndex = slotIndex;
  els.imageFiles?.click();
}

function configureImageUploadForWorkflow(workflow = activeWorkflow) {
  ensureImageSlots();
  const limit = imageSlotLimit(workflow);

  if (els.imageFiles) {
    els.imageFiles.multiple = workflow === 'editToImage';
    els.imageFiles.disabled = limit === 0;
  }

  const title = els.imageUploadPanel?.querySelector('.field-title');
  const help = els.imageUploadPanel?.querySelector('p');
  const dropStrong = els.imageUploadPanel?.querySelector('.dropzone strong');
  const dropHint = els.imageUploadPanel?.querySelector('.dropzone span');

  if (workflow === 'editToImage') {
    if (title) title.textContent = 'Ordered reference images';
    if (help) help.textContent = 'Load Image 1, Image 2 and Image 3 in the same order your prompt refers to them.';
    if (dropStrong) dropStrong.textContent = 'Browse or drop images into ordered slots';
    if (dropHint) dropHint.textContent = 'Maximum 3. The backend receives them in Image 1 → Image 2 → Image 3 order.';
  } else if (workflow === 'imageToVideo') {
    if (title) title.textContent = 'Source image';
    if (help) help.textContent = 'Load the single image Alibaba should animate.';
    if (dropStrong) dropStrong.textContent = 'Browse or drop source image';
    if (dropHint) dropHint.textContent = 'One PNG, JPG or WEBP image.';
  }

  renderImagePreviews();
}
'''

    app = app.replace("function bindEvents() {", helpers + "\nfunction bindEvents() {", 1)

    app, count = re.subn(
        r"  els\.imageFiles\.addEventListener\('change', async event => \{.*?\n  \}\);\n\n  els\.voiceFile\.addEventListener",
        "  els.imageFiles.addEventListener('change', event => {\n"
        "    const files = event.target.files ? [...event.target.files] : [];\n"
        "    const targetSlot = Number.isInteger(pendingImageSlotIndex) ? pendingImageSlotIndex : null;\n"
        "    addImagesToSlots(files, targetSlot);\n"
        "    pendingImageSlotIndex = null;\n"
        "    event.target.value = '';\n"
        "  });\n\n"
        "  els.imagePreviewStrip?.addEventListener('click', event => {\n"
        "    const removeButton = event.target.closest('[data-remove-image-slot]');\n"
        "    if (removeButton) {\n"
        "      event.preventDefault();\n"
        "      event.stopPropagation();\n"
        "      removeImageSlot(Number(removeButton.dataset.removeImageSlot));\n"
        "      return;\n"
        "    }\n\n"
        "    const chooseButton = event.target.closest('[data-choose-image-slot]');\n"
        "    if (chooseButton) {\n"
        "      event.preventDefault();\n"
        "      event.stopPropagation();\n"
        "      openImageSlotPicker(Number(chooseButton.dataset.chooseImageSlot));\n"
        "    }\n"
        "  });\n\n"
        "  els.voiceFile.addEventListener",
        app,
        count=1,
        flags=re.S,
    )

    if count != 1:
        raise SystemExit("Could not replace the image file change handler in frontend/app.js")

    if "configureImageUploadForWorkflow(workflow);" not in app:
        if "els.imageUploadPanel.hidden = !needsImages;" in app:
            app = app.replace(
                "els.imageUploadPanel.hidden = !needsImages;",
                "els.imageUploadPanel.hidden = !needsImages;\n  configureImageUploadForWorkflow(workflow);",
                1,
            )
        elif "els.imageUploadPanel.hidden = !ui.showImages;" in app:
            app = app.replace(
                "els.imageUploadPanel.hidden = !ui.showImages;",
                "els.imageUploadPanel.hidden = !ui.showImages;\n  configureImageUploadForWorkflow(workflow);",
                1,
            )
        else:
            raise SystemExit("Could not find imageUploadPanel visibility line in setWorkflow()")

    app = app.replace(
        "window.setTimeout(() => setWorkflow(activeWorkflow), 0);",
        "window.setTimeout(() => {\n      resetSelectedImageSlots();\n      setWorkflow(activeWorkflow);\n    }, 0);",
        1,
    )

    app = app.replace(
        "  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && selectedImages.length === 0) {\n"
        "    toast('Reference image required', 'Upload at least one image for this workflow.');\n"
        "    return null;\n"
        "  }",
        "  const imageFiles = selectedImageFiles();\n\n"
        "  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && imageFiles.length === 0) {\n"
        "    toast('Reference image required', 'Upload at least one image for this workflow.');\n"
        "    return null;\n"
        "  }\n\n"
        "  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && hasImageSlotGap()) {\n"
        "    toast('Fix image order', 'Do not leave an empty slot before a later image. Replace the missing Image slot so the prompt references match the upload order.');\n"
        "    return null;\n"
        "  }",
        1,
    )

    image_payload_replacement = (
        "  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && imageFiles.length) {\n"
        "    payload.images = await Promise.all(imageFiles.map(fileToDataUrl));\n"
        "    payload.imageNames = imageFiles.map(file => file.name);\n"
        "    payload.imageLabels = imageFiles.map((_, index) => `Image ${index + 1}`);\n"
        "    payload.imageUrl = payload.images[0];\n"
        "  }"
    )

    app, count = re.subn(
        r"  if \((?:\(activeWorkflow === 'editToImage' \|\| activeWorkflow === 'imageToVideo'\) && )?selectedImages\.length\) \{\n"
        r"    payload\.images = await Promise\.all\(selectedImages\.map\(fileToDataUrl\)\);\n"
        r"    payload\.imageNames = selectedImages\.map\(file => file\.name\);\n"
        r"    payload\.imageUrl = payload\.images\[0\];\n"
        r"  \}",
        image_payload_replacement,
        app,
        count=1,
    )

    if count != 1:
        raise SystemExit("Could not replace image payload assembly in frontend/app.js")

    app = app.replace(
        "  if (selectedVoiceFile) {\n",
        "  if (activeWorkflow === 'voiceClone' && selectedVoiceFile) {\n",
        1,
    )

    render_fn = r'''function renderImagePreviews() {
  if (!els.imagePreviewStrip) return;

  ensureImageSlots();
  const limit = imageSlotLimit();
  els.imagePreviewStrip.innerHTML = '';
  els.imagePreviewStrip.classList.toggle('ordered-image-slots', limit > 0);

  if (!limit) return;

  for (let index = 0; index < limit; index += 1) {
    const file = selectedImages[index];

    const tile = document.createElement('article');
    tile.className = `preview-tile ordered-slot${file ? ' has-file' : ' is-empty'}`;

    const badge = document.createElement('span');
    badge.className = 'slot-badge';
    badge.textContent = `Image ${index + 1}`;
    tile.appendChild(badge);

    if (file) {
      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'slot-remove-button';
      removeButton.dataset.removeImageSlot = String(index);
      removeButton.setAttribute('aria-label', `Remove Image ${index + 1}`);
      removeButton.textContent = '×';
      tile.appendChild(removeButton);

      const img = document.createElement('img');
      img.alt = `Image ${index + 1}: ${file.name}`;
      img.src = URL.createObjectURL(file);
      img.onload = () => URL.revokeObjectURL(img.src);
      tile.appendChild(img);

      const meta = document.createElement('div');
      meta.className = 'slot-meta';
      meta.innerHTML = `<strong>${escapeHtml(file.name)}</strong><span>${Math.max(1, Math.round(file.size / 1024))} KB</span>`;
      tile.appendChild(meta);

      const replaceButton = document.createElement('button');
      replaceButton.type = 'button';
      replaceButton.className = 'slot-replace-button';
      replaceButton.dataset.chooseImageSlot = String(index);
      replaceButton.textContent = `Replace Image ${index + 1}`;
      tile.appendChild(replaceButton);
    } else {
      const loadButton = document.createElement('button');
      loadButton.type = 'button';
      loadButton.className = 'slot-load-button';
      loadButton.dataset.chooseImageSlot = String(index);
      loadButton.innerHTML = `<strong>Load Image ${index + 1}</strong><span>This is the file your prompt should call Image ${index + 1}</span>`;
      tile.appendChild(loadButton);
    }

    els.imagePreviewStrip.appendChild(tile);
  }
}'''

    app, count = re.subn(
        r"function renderImagePreviews\(\) \{.*?\n\}",
        render_fn,
        app,
        count=1,
        flags=re.S,
    )

    if count != 1:
        raise SystemExit("Could not replace renderImagePreviews() in frontend/app.js")

# ---------- frontend/styles.css only ----------
if "frontend-only ordered image slots" not in css:
    css += r'''

/* frontend-only ordered image slots */
[hidden],
.is-hidden {
  display: none !important;
}

.preview-strip.ordered-image-slots {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
}

.preview-tile.ordered-slot {
  position: relative;
  width: 100%;
  min-height: 13rem;
  height: auto;
  border-radius: 1rem;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--surface);
  padding: 0.75rem;
  display: grid;
  gap: 0.55rem;
  align-content: start;
}

.slot-badge {
  width: max-content;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface-strong);
  color: var(--text);
  padding: 0.28rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.preview-tile.ordered-slot img {
  width: 100%;
  height: auto;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 0.75rem;
  border: 1px solid var(--line);
}

.slot-remove-button {
  position: absolute;
  top: 0.55rem;
  right: 0.55rem;
  z-index: 3;
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--bg-soft);
  color: var(--text);
  display: grid;
  place-items: center;
  padding: 0;
  font-size: 1.2rem;
  line-height: 1;
}

.slot-remove-button:hover,
.slot-replace-button:hover,
.slot-load-button:hover {
  transform: translateY(-1px);
}

.slot-meta {
  display: grid;
  gap: 0.15rem;
  min-width: 0;
}

.slot-meta strong,
.slot-meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slot-meta strong {
  color: var(--text);
  font-size: 0.86rem;
}

.slot-meta span {
  color: var(--muted);
  font-size: 0.78rem;
}

.slot-replace-button,
.slot-load-button {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 0.8rem;
  background: var(--surface-muted);
  color: var(--text);
  padding: 0.75rem;
}

.slot-load-button {
  min-height: 9.5rem;
  border-style: dashed;
  border-color: color-mix(in srgb, var(--brand) 55%, var(--line));
  background: color-mix(in srgb, var(--brand) 9%, transparent);
  display: grid;
  place-items: center;
  gap: 0.25rem;
  text-align: center;
}

.slot-load-button span {
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.35;
}

@media (max-width: 860px) {
  .preview-strip.ordered-image-slots {
    grid-template-columns: 1fr;
  }
}
'''

app_path.write_text(app, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
PY

echo "Frontend-only image slot patch complete."
echo "Changed only:"
echo "  frontend/app.js"
echo "  frontend/styles.css"
echo "Backups were saved beside those files."
echo "Restart with: python app.py"
