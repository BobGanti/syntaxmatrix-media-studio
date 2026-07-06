#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
APP="$ROOT/frontend/app.js"
CSS="$ROOT/frontend/styles.css"
SERVER="$ROOT/app.py"

if [ ! -f "$APP" ] || [ ! -f "$CSS" ] || [ ! -f "$SERVER" ]; then
  echo "ERROR: Run this from the AlibabaMedia project root, or pass the project path as the first argument." >&2
  echo "Expected files:" >&2
  echo "  $APP" >&2
  echo "  $CSS" >&2
  echo "  $SERVER" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$APP" "$APP.bak.edit-slots-$STAMP"
cp "$CSS" "$CSS.bak.edit-slots-$STAMP"
cp "$SERVER" "$SERVER.bak.edit-slots-$STAMP"

python - "$APP" "$CSS" "$SERVER" <<'PY'
from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])
server_path = Path(sys.argv[3])

app = app_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")
server = server_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------
# frontend/app.js: ordered image slots and removable/reloadable previews
# ---------------------------------------------------------------------
if "let pendingImageSlotIndex" not in app:
    app = app.replace(
        "let selectedImages = [];\nlet selectedVoiceFile = null;",
        "let selectedImages = [null, null, null];\nlet pendingImageSlotIndex = null;\nlet selectedVoiceFile = null;",
        1,
    )

app = app.replace("selectedImages = [];", "resetSelectedImages();")

slot_patch = r'''


/* Ordered Alibaba edit-image slots patch.
   Keeps UI labels and Alibaba content order aligned:
   slot 0 => Image 1, slot 1 => Image 2, slot 2 => Image 3. */
function imageSlotLimit() {
  if (activeWorkflow === 'editToImage') return 3;
  if (activeWorkflow === 'imageToVideo') return 1;
  return 0;
}

function resetSelectedImages() {
  selectedImages = [null, null, null];
  pendingImageSlotIndex = null;
}

function normalizeImageSlots() {
  if (!Array.isArray(selectedImages)) {
    resetSelectedImages();
    return;
  }

  const files = selectedImages.filter(file => file instanceof File);
  selectedImages = [null, null, null];
  files.slice(0, 3).forEach((file, index) => {
    selectedImages[index] = file;
  });
}

function selectedImageEntries() {
  normalizeImageSlots();
  const limit = imageSlotLimit();
  return selectedImages
    .slice(0, limit)
    .map((file, index) => ({ file, index }))
    .filter(entry => entry.file instanceof File);
}

function selectedImageFiles() {
  return selectedImageEntries().map(entry => entry.file);
}

function hasImageSlotGap() {
  normalizeImageSlots();
  const limit = imageSlotLimit();
  let seenEmpty = false;

  for (let index = 0; index < limit; index += 1) {
    if (!selectedImages[index]) {
      seenEmpty = true;
    } else if (seenEmpty) {
      return true;
    }
  }

  return false;
}

function addImageFilesToSlots(files, preferredSlot = null) {
  normalizeImageSlots();
  const limit = imageSlotLimit();
  if (!limit) return;

  const incoming = [...files].filter(file => file && file.type && file.type.startsWith('image/'));
  if (!incoming.length) return;

  let added = 0;
  let queue = incoming.slice();

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
    toast('Image limit applied', activeWorkflow === 'editToImage'
      ? 'Edit → Image accepts a maximum of three ordered images: Image 1, Image 2 and Image 3.'
      : 'Image → Video accepts one source image.');
  }

  renderImagePreviews();
}

function removeImageAtSlot(index) {
  normalizeImageSlots();
  if (index < 0 || index >= 3) return;

  selectedImages[index] = null;
  renderImagePreviews();
  toast(`Image ${index + 1} removed`, `Load another file into Image ${index + 1} before submitting if your prompt refers to it.`);
}

function chooseImageSlot(index) {
  pendingImageSlotIndex = index;
  if (els.imageFiles) els.imageFiles.click();
}

function initOrderedImageSlots() {
  if (!els.imageFiles || els.imageFiles.dataset.orderedSlotsBound === 'true') return;
  els.imageFiles.dataset.orderedSlotsBound = 'true';

  // Capture phase prevents the original loose-list change handler from replacing the slots.
  els.imageFiles.addEventListener('change', event => {
    event.stopImmediatePropagation();

    const files = event.target.files ? [...event.target.files] : [];
    const targetSlot = Number.isInteger(pendingImageSlotIndex) ? pendingImageSlotIndex : null;

    addImageFilesToSlots(files, targetSlot);

    pendingImageSlotIndex = null;
    event.target.value = '';
  }, true);

  els.imagePreviewStrip?.addEventListener('click', event => {
    const removeButton = event.target.closest('[data-remove-image-slot]');
    if (removeButton) {
      event.preventDefault();
      event.stopPropagation();
      removeImageAtSlot(Number(removeButton.dataset.removeImageSlot));
      return;
    }

    const chooseButton = event.target.closest('[data-choose-image-slot]');
    if (chooseButton) {
      event.preventDefault();
      chooseImageSlot(Number(chooseButton.dataset.chooseImageSlot));
    }
  });

  renderImagePreviews();
}

function renderImagePreviews() {
  if (!els.imagePreviewStrip) return;

  normalizeImageSlots();

  const limit = imageSlotLimit();
  els.imagePreviewStrip.innerHTML = '';

  if (!limit) return;

  for (let index = 0; index < limit; index += 1) {
    const file = selectedImages[index];

    const tile = document.createElement('article');
    tile.className = `preview-tile image-slot ${file ? 'has-file' : 'empty-slot'}`;
    tile.dataset.slot = String(index);

    const label = document.createElement('div');
    label.className = 'image-slot-label';
    label.textContent = `Image ${index + 1}`;
    tile.appendChild(label);

    if (file) {
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'image-slot-remove';
      remove.dataset.removeImageSlot = String(index);
      remove.setAttribute('aria-label', `Remove Image ${index + 1}`);
      remove.textContent = '×';
      tile.appendChild(remove);

      const img = document.createElement('img');
      img.alt = `Image ${index + 1}: ${file.name}`;
      img.src = URL.createObjectURL(file);
      img.onload = () => URL.revokeObjectURL(img.src);
      tile.appendChild(img);

      const meta = document.createElement('div');
      meta.className = 'image-slot-meta';
      meta.innerHTML = `<strong>${escapeHtml(file.name)}</strong><span>${Math.max(1, Math.round(file.size / 1024))} KB</span>`;
      tile.appendChild(meta);

      const replace = document.createElement('button');
      replace.type = 'button';
      replace.className = 'secondary image-slot-replace';
      replace.dataset.chooseImageSlot = String(index);
      replace.textContent = `Replace Image ${index + 1}`;
      tile.appendChild(replace);
    } else {
      const empty = document.createElement('button');
      empty.type = 'button';
      empty.className = 'image-slot-empty-button';
      empty.dataset.chooseImageSlot = String(index);
      empty.innerHTML = `<strong>Load Image ${index + 1}</strong><span>Used as Image ${index + 1} in your prompt</span>`;
      tile.appendChild(empty);
    }

    els.imagePreviewStrip.appendChild(tile);
  }
}

async function buildPayload() {
  const prompt = els.promptInput.value.trim();

  if (!prompt) {
    toast('Prompt required', 'Add a creative brief before generating an asset.');
    els.promptInput.focus();
    return null;
  }

  const imageEntries = selectedImageEntries();

  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && imageEntries.length === 0) {
    toast('Reference image required', 'Upload at least one image for this workflow.');
    return null;
  }

  if ((activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') && hasImageSlotGap()) {
    toast('Image order needs attention', 'Do not leave a gap before a later image. Replace the missing slot so Image 1, Image 2 and Image 3 match the order in your prompt.');
    return null;
  }

  if (activeWorkflow === 'voiceClone' && !selectedVoiceFile) {
    toast('Audio source required', 'Upload a clean voice sample before generating a cloned voice asset.');
    return null;
  }

  const payload = {
    workflow: activeWorkflow,
    model: els.modelSelect.value,
    prompt,
    quality: els.qualitySelect?.value,
    watermark: Boolean(els.watermarkInput?.checked),
    promptExtend: Boolean(els.promptExtendInput?.checked),
    negativePrompt: els.negativePromptInput?.value.trim() || ''
  };

  if (activeWorkflow === 'textToImage' || activeWorkflow === 'editToImage') {
    payload.size = els.sizeSelect.value;
  }

  if (activeWorkflow === 'textToVideo' || activeWorkflow === 'imageToVideo') {
    payload.resolution = els.resolutionSelect.value;
    payload.duration = Number(els.durationSelect.value);
  }

  const seed = els.seedInput?.value.trim();
  if (seed) payload.seed = Number(seed);

  if (activeWorkflow === 'editToImage' || activeWorkflow === 'imageToVideo') {
    payload.images = await Promise.all(imageEntries.map(entry => fileToDataUrl(entry.file)));
    payload.imageNames = imageEntries.map(entry => entry.file.name);
    payload.imageLabels = imageEntries.map(entry => `Image ${entry.index + 1}`);
    payload.imageSlots = imageEntries.map(entry => entry.index + 1);
    payload.imageUrl = payload.images[0];
  }

  if (activeWorkflow === 'voiceClone' && selectedVoiceFile) {
    payload.voiceName = els.voiceNameInput.value.trim() || 'smxVoice';
    payload.audio = await fileToDataUrl(selectedVoiceFile);
    payload.audioName = selectedVoiceFile.name;
  }

  return payload;
}

initOrderedImageSlots();
'''

if "Ordered Alibaba edit-image slots patch" not in app:
    app = app.rstrip() + slot_patch + "\n"

app = app.replace(
    "defaultPrompt: 'Make the subjects wear premium white formal outfits and matching white shoes, keeping identity, lighting and realism consistent.'",
    "defaultPrompt: 'Make the person or people from Image 1 wear the outfit from Image 2 and the shoes/accessories from Image 3, preserving identity, realism, lighting and correct gender fitting.'",
)

# ---------------------------------------------------------------------
# frontend/styles.css: visible ordered slots with x button
# ---------------------------------------------------------------------
slot_css = r'''


/* Ordered Edit → Image slots */
[hidden],
.is-hidden {
  display: none !important;
}

.preview-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
}

.preview-tile.image-slot {
  position: relative;
  width: 100%;
  min-height: 13.5rem;
  height: auto;
  border-radius: 1rem;
  overflow: hidden;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--surface-muted) 88%, transparent);
  display: grid;
  align-content: start;
  gap: 0.55rem;
  padding: 0.7rem;
}

.image-slot-label {
  width: max-content;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.28rem 0.55rem;
  color: var(--text);
  background: var(--surface);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.preview-tile.image-slot img {
  width: 100%;
  aspect-ratio: 1 / 1;
  height: auto;
  border-radius: 0.75rem;
  object-fit: cover;
  border: 1px solid var(--line);
}

.image-slot-remove {
  position: absolute;
  top: 0.55rem;
  right: 0.55rem;
  z-index: 2;
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  color: var(--text);
  font-size: 1.25rem;
  line-height: 1;
  display: grid;
  place-items: center;
  padding: 0;
  cursor: pointer;
}

.image-slot-remove:hover {
  transform: translateY(-1px);
}

.image-slot-meta {
  min-width: 0;
  display: grid;
  gap: 0.2rem;
}

.image-slot-meta strong,
.image-slot-meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-slot-meta strong {
  color: var(--text);
  font-size: 0.86rem;
}

.image-slot-meta span {
  color: var(--muted);
  font-size: 0.78rem;
}

.image-slot-replace,
.image-slot-empty-button {
  width: 100%;
}

.image-slot-empty-button {
  min-height: 10.5rem;
  border: 1px dashed color-mix(in srgb, var(--brand) 50%, var(--line));
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--brand) 8%, transparent);
  color: var(--text);
  display: grid;
  place-items: center;
  gap: 0.35rem;
  padding: 1rem;
  cursor: pointer;
  text-align: center;
}

.image-slot-empty-button span {
  color: var(--muted);
  font-size: 0.82rem;
}

@media (max-width: 780px) {
  .preview-strip {
    grid-template-columns: 1fr;
  }
}
'''

if "Ordered Edit → Image slots" not in css:
    css = css.rstrip() + slot_css + "\n"

# ---------------------------------------------------------------------
# app.py: save uploaded images and pass them to Alibaba as {"image": "..."}
# ---------------------------------------------------------------------
helper = r'''

def _safe_upload_filename(preferred_name: str, prefix: str, ext: str) -> str:
    stem = pathlib.Path(preferred_name or prefix).stem
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("_")
    cleaned = cleaned or prefix

    if not ext.startswith("."):
        ext = f".{ext}"

    return f"{prefix}_{int(time.time() * 1000)}_{cleaned}{ext}"


def _save_data_url_upload(data_url: str, subdir: str, preferred_name: str, prefix: str) -> str:
    """Save a browser data URL under uploads/<subdir>/ and return a root-relative path.

    Alibaba MultiModalConversation examples can use local root-relative image paths,
    e.g. {"image": "uploads/images/input1.png"}. This converts frontend base64
    uploads into that exact shape while preserving Image 1 / 2 / 3 order.
    """
    raw, mime = _data_url_to_bytes(data_url)
    preferred_ext = pathlib.Path(preferred_name or "").suffix
    ext = preferred_ext or _safe_ext(mime, ".png")

    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / _safe_upload_filename(preferred_name, prefix, ext)
    target_file.write_bytes(raw)

    return str(target_file.relative_to(ROOT)).replace(os.sep, "/")
'''

if "def _save_data_url_upload" not in server:
    server = server.replace(
        "def _messages_from_prompt(prompt: str) -> list[dict[str, Any]]:",
        helper + "\n\ndef _messages_from_prompt(prompt: str) -> list[dict[str, Any]]:",
        1,
    )

new_generate_edit = r'''def generate_edit_to_image(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    dashscope, MultiModalConversation, _ = _require_dashscope()
    api_key, _, base_url = _env_config()
    dashscope.base_http_api_url = base_url

    prompt = (payload.get("prompt") or "").strip()
    images = payload.get("images") or []
    image_names = payload.get("imageNames") or []

    if not prompt:
        return _json_error("Prompt is required.", 400)
    if not images:
        return _json_error("At least one reference image is required.", 400)
    if len(images) > 3:
        return _json_error("Alibaba image editing accepts a maximum of three images.", 400)

    saved_image_paths: list[str] = []

    for index, image in enumerate(images[:3], start=1):
        if not isinstance(image, str) or not image.strip():
            return _json_error(f"Image {index} is invalid.", 400)

        if image.startswith("data:"):
            preferred_name = image_names[index - 1] if index - 1 < len(image_names) else f"image_{index}.png"
            saved_path = _save_data_url_upload(
                image,
                subdir="images",
                preferred_name=preferred_name,
                prefix=f"image{index}",
            )
            saved_image_paths.append(saved_path)
        else:
            # Allows advanced/local callers to pass paths or URLs directly.
            saved_image_paths.append(image)

    # IMPORTANT: Alibaba sees Image 1, Image 2, Image 3 by content order.
    # Do not sort, rename, or merge this list. The final text instruction comes last.
    content = [{"image": image_path} for image_path in saved_image_paths]
    content.append({"text": prompt})

    messages = [{"role": "user", "content": content}]

    response = MultiModalConversation.call(
        api_key=api_key,
        model=payload.get("model") or "qwen-image-edit-plus-2025-12-15",
        messages=messages,
        result_format="message",
        stream=False,
        watermark=bool(payload.get("watermark", False)),
        negative_prompt=payload.get("negativePrompt") or "",
    )

    if getattr(response, "status_code", None) != HTTPStatus.OK and getattr(response, "status_code", None) != 200:
        return _json_error(
            getattr(response, "message", "Alibaba edit-to-image request failed."),
            502,
            details=str(response),
        )

    output_content = response["output"]["choices"][0]["message"]["content"]
    image_urls = [item.get("image") for item in output_content if isinstance(item, dict) and item.get("image")]
    image_url = image_urls[0] if image_urls else None

    return 200, {
        "ok": True,
        "imageUrl": image_url,
        "assetUrl": image_url,
        "images": image_urls,
        "inputImages": saved_image_paths,
        "requestMessages": messages,
        "raw": _safe_response(response),
    }

'''

server, count = re.subn(
    r"def generate_edit_to_image\(payload: Dict\[str, Any\]\) -> Tuple\[int, Dict\[str, Any\]\]:\n.*?\ndef _video_size_from_payload",
    new_generate_edit + "def _video_size_from_payload",
    server,
    count=1,
    flags=re.S,
)

if count != 1:
    raise SystemExit("Could not replace generate_edit_to_image() in app.py. The function structure may have changed.")

app_path.write_text(app, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
server_path.write_text(server, encoding="utf-8")
PY

echo "Patch complete. Edit → Image now uses ordered Image 1 / Image 2 / Image 3 slots."
echo "Backups created beside app.js, styles.css, and app.py."
echo "Restart: python app.py"
