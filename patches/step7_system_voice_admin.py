from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()

SYSTEM = ROOT / "services" / "clone_voice_system.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"

ADMIN_HTML = ROOT / "frontend" / "clone_voice" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "clone_voice" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "clone_voice" / "admin.js"

required = [SYSTEM, CONTROLLER, ADMIN_HTML.parent]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [SYSTEM, CONTROLLER, ADMIN_HTML, ADMIN_CSS, ADMIN_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step7-system-admin-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

SYSTEM.write_text(r'''from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any

from werkzeug.datastructures import FileStorage

from services.clone_voice_audio_policy import (
    get_max_voice_source_seconds,
    limit_audio_to_max_seconds,
    normalize_generated_audio_file,
)
from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_workspace import (
    ROOT,
    STANDARD_VOICE_PREVIEW_TEXT,
    delete_if_exists,
    display_name_from_voice_id,
    infer_gender_from_voice_id,
    normalize_gender,
    relative_to_root,
    safe_slug,
    voice_label,
)


SYSTEM_VOICES_DIR = ROOT / "voices"
SYSTEM_PARAMS_DIR = SYSTEM_VOICES_DIR / "params"
SYSTEM_PREVIEWS_DIR = SYSTEM_VOICES_DIR / "previews"
SYSTEM_METADATA_DIR = SYSTEM_VOICES_DIR / "metadata"
SYSTEM_TMP_DIR = SYSTEM_VOICES_DIR / "tmp" / "source_audio"


def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S")


def ensure_system_dirs() -> None:
    for directory in [SYSTEM_PARAMS_DIR, SYSTEM_PREVIEWS_DIR, SYSTEM_METADATA_DIR, SYSTEM_TMP_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def _voice_id_from_param_path(path: pathlib.Path) -> str:
    stem = path.stem
    if stem.endswith("_parameter"):
        stem = stem[:-len("_parameter")]
    return safe_slug(stem)


def system_parameter_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PARAMS_DIR / f"{safe_slug(voice_id)}_parameter.txt"


def system_legacy_parameter_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PARAMS_DIR / f"{safe_slug(voice_id)}.txt"


def system_preview_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PREVIEWS_DIR / f"{safe_slug(voice_id)}_preview.wav"


def system_metadata_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_METADATA_DIR / f"{safe_slug(voice_id)}.json"


def _find_param_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    candidates = [
        system_parameter_path(voice_id),
        system_legacy_parameter_path(voice_id),
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def _find_preview_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    first = system_preview_path(voice_id)

    if first.exists():
        return first

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}_preview.*"):
        return path

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}.*"):
        return path

    return None


def _load_system_metadata(voice_id: str) -> dict[str, Any]:
    ensure_system_dirs()

    path = system_metadata_path(voice_id)

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                display_name = data.get("displayName") or display_name_from_voice_id(voice_id)
                gender = normalize_gender(data.get("gender") or infer_gender_from_voice_id(voice_id))

                data["voiceId"] = safe_slug(voice_id)
                data["displayName"] = display_name
                data["gender"] = gender
                data["label"] = voice_label(display_name, gender)
                data.setdefault("previewText", STANDARD_VOICE_PREVIEW_TEXT)
                data.setdefault("previewKind", "standard_synthesized")
                return data
        except Exception as exc:
            print("[clone_voice_system] Could not read metadata:", path, repr(exc), flush=True)

    gender = infer_gender_from_voice_id(voice_id)
    display_name = display_name_from_voice_id(voice_id)

    return {
        "voiceId": safe_slug(voice_id),
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "unknown",
    }


def _save_system_metadata(
    voice_id: str,
    display_name: str,
    gender: str,
    *,
    parameter_path: pathlib.Path,
    preview_path: pathlib.Path,
) -> tuple[dict[str, Any], pathlib.Path]:
    ensure_system_dirs()

    voice_id = safe_slug(voice_id)
    display_name = (display_name or display_name_from_voice_id(voice_id)).strip()
    gender = normalize_gender(gender)

    metadata = {
        "voiceId": voice_id,
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "sourceType": "system",
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "standard_synthesized",
        "parameterPath": relative_to_root(parameter_path),
        "previewPath": relative_to_root(preview_path),
        "updatedAt": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    path = system_metadata_path(voice_id)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata, path


def _system_voice_payload(voice_id: str, param_path: pathlib.Path | None = None) -> dict[str, Any]:
    metadata = _load_system_metadata(voice_id)
    param_path = param_path or _find_param_path(voice_id)
    preview_path = _find_preview_path(voice_id)

    return {
        "voiceId": safe_slug(voice_id),
        "displayName": metadata.get("displayName") or display_name_from_voice_id(voice_id),
        "gender": normalize_gender(metadata.get("gender")),
        "label": metadata.get("label") or voice_label(
            metadata.get("displayName") or display_name_from_voice_id(voice_id),
            metadata.get("gender")
        ),
        "previewUrl": f"/media/voices/previews/{preview_path.name}" if preview_path else "",
        "previewText": metadata.get("previewText") or STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": metadata.get("previewKind") or "unknown",
        "parameterPath": relative_to_root(param_path) if param_path else "",
        "previewPath": relative_to_root(preview_path) if preview_path else "",
        "updatedAt": metadata.get("updatedAt") or "",
    }


def list_system_voices_payload() -> list[dict[str, Any]]:
    ensure_system_dirs()

    unique: dict[str, pathlib.Path] = {}

    for param_path in sorted(SYSTEM_PARAMS_DIR.glob("*.txt")):
        voice_id = _voice_id_from_param_path(param_path)
        preferred = system_parameter_path(voice_id)

        if voice_id not in unique:
            unique[voice_id] = param_path

        if param_path == preferred:
            unique[voice_id] = param_path

    rows = []

    for voice_id, param_path in unique.items():
        payload = _system_voice_payload(voice_id, param_path)
        payload["_mtime"] = param_path.stat().st_mtime if param_path.exists() else 0
        rows.append(payload)

    rows.sort(key=lambda row: row.get("_mtime", 0), reverse=True)

    for row in rows:
        row.pop("_mtime", None)

    return rows


def load_system_voice_parameter(voice_id: str) -> tuple[str, pathlib.Path]:
    ensure_system_dirs()

    path = _find_param_path(voice_id)

    if not path:
        raise FileNotFoundError(f"System voice parameter not found for voiceId={voice_id}")

    return path.read_text(encoding="utf-8").strip(), path


def save_system_voice_from_source(
    audio_file: FileStorage,
    *,
    display_name: str,
    gender: str,
    replace: bool = False,
) -> dict[str, Any]:
    ensure_system_dirs()

    if audio_file is None or not audio_file.filename:
        raise ValueError("Missing system voice audio source")

    display_name = (display_name or pathlib.Path(audio_file.filename).stem or "System Voice").strip()
    voice_id = safe_slug(display_name, "system_voice")
    gender = normalize_gender(gender)

    existing_param = _find_param_path(voice_id)

    if existing_param and not replace:
        raise FileExistsError(
            f"System voice already exists for '{display_name}'. Enable replace to overwrite it."
        )

    raw_source_path = None
    limited_source_path = None

    try:
        suffix = pathlib.Path(audio_file.filename).suffix or ".wav"
        raw_source_path = SYSTEM_TMP_DIR / f"{voice_id}_raw_{_now_stamp()}{suffix}"
        limited_source_path = SYSTEM_TMP_DIR / f"{voice_id}_limited_{_now_stamp()}.wav"

        audio_file.save(raw_source_path)

        max_seconds = get_max_voice_source_seconds()

        limit_audio_to_max_seconds(
            input_path=raw_source_path,
            output_path=limited_source_path,
            max_seconds=max_seconds,
        )

        voice_parameter = create_voice_parameter(limited_source_path, "audio/wav")

        param_path = system_parameter_path(voice_id)
        preview_path = system_preview_path(voice_id)

        param_path.write_text(str(voice_parameter), encoding="utf-8")

        print("[clone_voice_system] Generating standard system preview:", preview_path, flush=True)
        generate_narration_to_file(voice_parameter, STANDARD_VOICE_PREVIEW_TEXT, preview_path)
        normalize_generated_audio_file(preview_path)

        metadata, metadata_path = _save_system_metadata(
            voice_id,
            display_name,
            gender,
            parameter_path=param_path,
            preview_path=preview_path,
        )

        payload = _system_voice_payload(voice_id, param_path)
        payload.update({
            "ok": True,
            "replaced": bool(existing_param),
            "maxVoiceSourceSeconds": max_seconds,
            "metadataPath": relative_to_root(metadata_path),
            "previewText": STANDARD_VOICE_PREVIEW_TEXT,
            "metadata": metadata,
        })

        return payload

    finally:
        delete_if_exists(raw_source_path)
        delete_if_exists(limited_source_path)


def delete_system_voice(voice_id: str) -> dict[str, Any]:
    ensure_system_dirs()

    voice_id = safe_slug(voice_id)
    deleted: list[str] = []

    candidates: list[pathlib.Path | None] = [
        system_parameter_path(voice_id),
        system_legacy_parameter_path(voice_id),
        _find_preview_path(voice_id),
        system_metadata_path(voice_id),
    ]

    for path in candidates:
        if path and path.exists():
            deleted.append(relative_to_root(path))
            path.unlink()

    return {
        "ok": True,
        "voiceId": voice_id,
        "deleted": deleted,
        "deletedCount": len(deleted),
    }
''', encoding="utf-8")

controller = CONTROLLER.read_text(encoding="utf-8")

old_import = "from services.clone_voice_system import SYSTEM_PREVIEWS_DIR, list_system_voices_payload, load_system_voice_parameter"
new_import = '''from services.clone_voice_system import (
    SYSTEM_PREVIEWS_DIR,
    delete_system_voice,
    list_system_voices_payload,
    load_system_voice_parameter,
    save_system_voice_from_source,
)'''

if old_import in controller:
    controller = controller.replace(old_import, new_import, 1)
elif "save_system_voice_from_source" not in controller:
    print("ERROR: Could not find clone_voice_system import in controller.")
    raise SystemExit(1)

if 'endpoint="clone_voice_create_system_voice"' not in controller:
    marker = '    if "clone_voice_my_voices" not in app.view_functions:'
    if marker not in controller:
        print("ERROR: Could not find insertion marker before my voices route.")
        raise SystemExit(1)

    block = r'''
    if "clone_voice_create_system_voice" not in app.view_functions:
        @app.post("/api/clone-voice/system-voices", endpoint="clone_voice_create_system_voice")
        def create_system_voice():
            audio_file = request.files.get("audio")
            display_name = (
                request.form.get("displayName", "")
                or request.form.get("voiceDisplayName", "")
                or request.form.get("voiceName", "")
            ).strip()
            gender = request.form.get("gender", "U")
            replace_raw = str(request.form.get("replace", "")).strip().lower()
            replace = replace_raw in {"1", "true", "yes", "on", "replace"}

            if audio_file is None or not audio_file.filename:
                return _error("Missing system voice audio source", 400)

            try:
                payload = save_system_voice_from_source(
                    audio_file,
                    display_name=display_name,
                    gender=gender,
                    replace=replace,
                )

                print("[clone_voice_controller] System voice saved:", payload, flush=True)

                return jsonify(payload)

            except FileExistsError as exc:
                return _error(str(exc), 409)

            except Exception as exc:
                print("[clone_voice_controller] create system voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_delete_system_voice" not in app.view_functions:
        @app.delete("/api/clone-voice/system-voices/<voice_id>", endpoint="clone_voice_delete_system_voice")
        def remove_system_voice(voice_id: str):
            try:
                payload = delete_system_voice(voice_id)
                print("[clone_voice_controller] System voice deleted:", payload, flush=True)
                return jsonify(payload)

            except Exception as exc:
                print("[clone_voice_controller] delete system voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

'''

    controller = controller.replace(marker, block + marker, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

ADMIN_HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clone Voice Admin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/admin.css?v=system-admin-1">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Clone Voice Admin</h1>
      <p>Configure Clone Voice limits and manage system voices.</p>
      <p><a href="/tasks/clone-voice">← Back to Clone Voice</a></p>
    </header>

    <section class="card">
      <h2>Voice source duration</h2>
      <p class="status">
        D controls the maximum seconds allowed for uploaded or recorded voice source audio.
        The client recorder auto-stops at this value, and the backend trims source audio to this value before creating the voice parameter.
      </p>

      <form id="durationForm" class="form-grid">
        <label>
          Max voice source duration, D seconds
          <input id="durationInput" name="maxVoiceSourceSeconds" type="number" min="5" max="120" step="1" required>
        </label>

        <button id="saveDurationBtn" type="submit">Save duration</button>
      </form>

      <div id="durationStatusBox" class="status-box">Loading setting...</div>
    </section>

    <section class="card">
      <h2>System voices</h2>
      <p class="status">
        Upload a system voice source, set its display name and gender, then the system creates a stable voice parameter and a standard synthesized preview.
      </p>

      <form id="systemVoiceForm" class="system-form">
        <label>
          System voice source audio
          <input id="systemVoiceAudio" type="file" accept="audio/*" required>
        </label>

        <label>
          Display name
          <input id="systemVoiceDisplayName" type="text" placeholder="Example: Bobga, Ngozi" required>
        </label>

        <label>
          Gender
          <select id="systemVoiceGender">
            <option value="U">Unspecified (U)</option>
            <option value="M">Male (M)</option>
            <option value="F">Female (F)</option>
          </select>
        </label>

        <label class="check-row">
          <input id="replaceSystemVoice" type="checkbox">
          Replace existing voice with same display name
        </label>

        <button id="saveSystemVoiceBtn" type="submit">Create system voice</button>
      </form>

      <div id="systemVoiceStatusBox" class="status-box">No system voice request sent yet.</div>

      <div class="list-toolbar">
        <label>
          Filter
          <select id="systemVoiceFilter">
            <option value="">All voices</option>
            <option value="M">Male voices</option>
            <option value="F">Female voices</option>
            <option value="U">Unspecified voices</option>
          </select>
        </label>

        <button id="refreshSystemVoicesBtn" type="button">Refresh system voices</button>
      </div>

      <audio id="systemPreviewPlayer" controls class="hidden"></audio>

      <div id="systemVoicesList" class="voice-list">Loading system voices...</div>
    </section>
  </main>

  <script src="/clone_voice/admin.js?v=system-admin-1"></script>
</body>
</html>
''', encoding="utf-8")

ADMIN_CSS.write_text(r'''* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: Arial, sans-serif;
  background: #071017;
  color: #e8f1f8;
  padding: 32px;
}

.shell {
  max-width: 1000px;
  margin: 0 auto;
  display: grid;
  gap: 20px;
}

.hero,
.card {
  border: 1px solid #33414c;
  border-radius: 16px;
  padding: 20px;
  background: #111b24;
}

.eyebrow,
.status,
.hero p {
  color: #a9bfd3;
  line-height: 1.55;
}

a {
  color: #9ee8dc;
  font-weight: 900;
  text-decoration: none;
}

h1,
h2,
p {
  margin-top: 0;
}

label {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  font-weight: 800;
}

input,
select,
button {
  font: inherit;
}

input[type="number"],
input[type="text"],
input[type="file"],
select {
  width: 100%;
  border: 1px solid #465662;
  border-radius: 12px;
  padding: 12px;
  background: #202b35;
  color: #fff;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 14px 22px;
  background: linear-gradient(135deg, #9ee8dc, #82a8ff);
  color: #06130f;
  font-weight: 900;
  cursor: pointer;
}

button.danger {
  background: linear-gradient(135deg, #ffb3b3, #ff7676);
}

button.secondary {
  background: #202b35;
  color: #e8f1f8;
  border: 1px solid #465662;
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
}

.system-form {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) 170px;
  gap: 14px;
  align-items: end;
}

.check-row {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #a9bfd3;
}

.check-row input {
  width: auto;
}

.status-box {
  margin: 16px 0;
  background: #02070b;
  border: 1px solid #33414c;
  border-radius: 12px;
  padding: 16px;
  color: #dceaf5;
  line-height: 1.55;
}

.status-box strong {
  color: #9ee8dc;
}

.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  margin: 18px 0;
}

.list-toolbar label {
  min-width: 240px;
  margin: 0;
}

.voice-list {
  display: grid;
  gap: 12px;
}

.voice-card {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  align-items: center;
  border: 1px solid #33414c;
  border-radius: 14px;
  padding: 14px;
  background: #071017;
}

.voice-title {
  font-weight: 900;
  color: #e8f1f8;
}

.voice-meta {
  margin-top: 5px;
  color: #a9bfd3;
  font-size: .92rem;
  overflow-wrap: anywhere;
}

.hidden {
  display: none !important;
}

audio {
  width: 100%;
  margin: 12px 0;
}

@media (max-width: 820px) {
  body {
    padding: 18px;
  }

  .form-grid,
  .system-form,
  .voice-card {
    grid-template-columns: 1fr;
  }

  button {
    width: 100%;
  }
}
''', encoding="utf-8")

ADMIN_JS.write_text(r'''(() => {
  const $ = (selector) => document.querySelector(selector);

  const durationForm = $("#durationForm");
  const durationInput = $("#durationInput");
  const saveDurationBtn = $("#saveDurationBtn");
  const durationStatusBox = $("#durationStatusBox");

  const systemVoiceForm = $("#systemVoiceForm");
  const systemVoiceAudio = $("#systemVoiceAudio");
  const systemVoiceDisplayName = $("#systemVoiceDisplayName");
  const systemVoiceGender = $("#systemVoiceGender");
  const replaceSystemVoice = $("#replaceSystemVoice");
  const saveSystemVoiceBtn = $("#saveSystemVoiceBtn");
  const systemVoiceStatusBox = $("#systemVoiceStatusBox");

  const systemVoiceFilter = $("#systemVoiceFilter");
  const refreshSystemVoicesBtn = $("#refreshSystemVoicesBtn");
  const systemVoicesList = $("#systemVoicesList");
  const systemPreviewPlayer = $("#systemPreviewPlayer");

  let systemVoices = [];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function durationStatus(data, message) {
    durationStatusBox.innerHTML = `
      <strong>${escapeHtml(message)}</strong><br>
      Current D: ${escapeHtml(data.maxVoiceSourceSeconds)} seconds<br>
      Allowed range: ${escapeHtml(data.minSeconds)}–${escapeHtml(data.maxSeconds)} seconds<br>
      Config: ${escapeHtml(data.configPath)}
    `;
  }

  async function loadDurationSettings() {
    durationStatusBox.textContent = "Loading setting...";

    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load settings");
      }

      durationInput.min = data.minSeconds || 5;
      durationInput.max = data.maxSeconds || 120;
      durationInput.value = data.maxVoiceSourceSeconds || 20;

      durationStatus(data, "Setting loaded.");
    } catch (error) {
      durationStatusBox.textContent = error.message || String(error);
    }
  }

  async function saveDuration(event) {
    event.preventDefault();

    saveDurationBtn.disabled = true;
    saveDurationBtn.textContent = "Saving...";
    durationStatusBox.textContent = "Saving setting...";

    try {
      const response = await fetch("/api/clone-voice/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          maxVoiceSourceSeconds: Number(durationInput.value)
        })
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save settings");
      }

      durationInput.value = data.maxVoiceSourceSeconds;
      durationStatus(data, "Setting saved.");
    } catch (error) {
      durationStatusBox.textContent = error.message || String(error);
    } finally {
      saveDurationBtn.disabled = false;
      saveDurationBtn.textContent = "Save duration";
    }
  }

  function filteredSystemVoices() {
    const filter = systemVoiceFilter.value;
    if (!filter) return systemVoices;
    return systemVoices.filter((voice) => String(voice.gender || "U").toUpperCase() === filter);
  }

  function renderSystemVoices() {
    const rows = filteredSystemVoices();

    if (!rows.length) {
      systemVoicesList.innerHTML = `<p class="status">No system voices found for this filter.</p>`;
      return;
    }

    systemVoicesList.innerHTML = rows.map((voice) => {
      const previewButton = voice.previewUrl
        ? `<button class="secondary" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}">Preview</button>`
        : `<button class="secondary" type="button" disabled>No preview</button>`;

      return `
        <div class="voice-card">
          <div>
            <div class="voice-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</div>
            <div class="voice-meta">Preview: standard synthesized sentence</div>
            <div class="voice-meta">${escapeHtml(voice.parameterPath || "")}</div>
          </div>
          ${previewButton}
          <button class="danger" type="button" data-delete-voice-id="${escapeHtml(voice.voiceId)}" data-delete-label="${escapeHtml(voice.label || voice.voiceId)}">Delete</button>
        </div>
      `;
    }).join("");
  }

  async function loadSystemVoices() {
    systemVoicesList.textContent = "Loading system voices...";

    try {
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      systemVoices = data.voices || [];
      renderSystemVoices();
    } catch (error) {
      systemVoicesList.textContent = error.message || String(error);
    }
  }

  function systemVoiceStatus(data, message) {
    systemVoiceStatusBox.innerHTML = `
      <strong>${escapeHtml(message)}</strong><br>
      Voice: ${escapeHtml(data.label || data.displayName || data.voiceId || "")}<br>
      Gender: ${escapeHtml(data.gender || "")}<br>
      Preview: standard synthesized sentence<br>
      ${data.replaced ? "Existing voice replaced." : "New system voice created."}
    `;
  }

  async function saveSystemVoice(event) {
    event.preventDefault();

    const file = systemVoiceAudio.files[0];
    const displayName = systemVoiceDisplayName.value.trim();

    if (!file) {
      alert("Choose a system voice source audio file.");
      return;
    }

    if (!displayName) {
      alert("Enter a display name.");
      return;
    }

    const formData = new FormData();
    formData.append("audio", file, file.name);
    formData.append("displayName", displayName);
    formData.append("gender", systemVoiceGender.value || "U");
    formData.append("replace", replaceSystemVoice.checked ? "true" : "false");

    saveSystemVoiceBtn.disabled = true;
    saveSystemVoiceBtn.textContent = "Creating...";
    systemVoiceStatusBox.textContent = "Creating system voice parameter and standard preview...";

    try {
      const response = await fetch("/api/clone-voice/system-voices", {
        method: "POST",
        body: formData
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not create system voice");
      }

      systemVoiceStatus(data, data.replaced ? "System voice replaced." : "System voice created.");
      systemVoiceAudio.value = "";
      await loadSystemVoices();
    } catch (error) {
      systemVoiceStatusBox.textContent = error.message || String(error);
    } finally {
      saveSystemVoiceBtn.disabled = false;
      saveSystemVoiceBtn.textContent = "Create system voice";
    }
  }

  async function playPreview(url) {
    if (!url) return;

    systemPreviewPlayer.classList.remove("hidden");
    systemPreviewPlayer.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    await systemPreviewPlayer.play().catch(() => {});
  }

  async function deleteSystemVoice(voiceId, label) {
    const ok = confirm(`Delete system voice: ${label || voiceId}?`);

    if (!ok) return;

    systemVoiceStatusBox.textContent = `Deleting ${label || voiceId}...`;

    try {
      const response = await fetch(`/api/clone-voice/system-voices/${encodeURIComponent(voiceId)}`, {
        method: "DELETE"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not delete system voice");
      }

      systemVoiceStatusBox.innerHTML = `
        <strong>System voice deleted.</strong><br>
        Deleted files: ${escapeHtml(data.deletedCount || 0)}
      `;

      await loadSystemVoices();
    } catch (error) {
      systemVoiceStatusBox.textContent = error.message || String(error);
    }
  }

  durationForm.addEventListener("submit", saveDuration);
  systemVoiceForm.addEventListener("submit", saveSystemVoice);
  refreshSystemVoicesBtn.addEventListener("click", loadSystemVoices);
  systemVoiceFilter.addEventListener("change", renderSystemVoices);

  document.addEventListener("click", (event) => {
    const previewButton = event.target.closest("[data-preview-url]");
    if (previewButton) {
      event.preventDefault();
      playPreview(previewButton.getAttribute("data-preview-url"));
      return;
    }

    const deleteButton = event.target.closest("[data-delete-voice-id]");
    if (deleteButton) {
      event.preventDefault();
      deleteSystemVoice(
        deleteButton.getAttribute("data-delete-voice-id"),
        deleteButton.getAttribute("data-delete-label")
      );
    }
  });

  loadDurationSettings();
  loadSystemVoices();
})();
''', encoding="utf-8")

py_compile.compile(str(SYSTEM), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 7 COMPLETE: System Voice Admin Management added.")
print()
print("Admin page:")
print("  http://127.0.0.1:5055/admin/clone-voice")
print()
print("New API:")
print("  POST   /api/clone-voice/system-voices")
print("  DELETE /api/clone-voice/system-voices/<voice_id>")
print()
print("System voice storage:")
print("  voices/params/<voiceId>_parameter.txt")
print("  voices/previews/<voiceId>_preview.wav")
print("  voices/metadata/<voiceId>.json")
print()
print("Restart Flask:")
print("  python app.py")
