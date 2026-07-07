from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()

WORKSPACE_SERVICE = ROOT / "services" / "clone_voice_workspace.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
JS = ROOT / "frontend" / "clone_voice" / "client.js"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"

required = [WORKSPACE_SERVICE, CONTROLLER, HTML, JS, CSS]
missing = [str(p) for p in required if not p.exists()]

if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.my-saved-voices-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

WORKSPACE_SERVICE.write_text(r'''from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT / "workspaces"
MOCK_WORKSPACE_ID = "mock_user_001"


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_id: str
    root: pathlib.Path
    tmp_source_audio_dir: pathlib.Path
    voice_params_dir: pathlib.Path
    generated_audio_dir: pathlib.Path


def sanitize_workspace_id(value: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or MOCK_WORKSPACE_ID).strip())
    return cleaned or MOCK_WORKSPACE_ID


def get_workspace(workspace_id: str | None = None) -> WorkspacePaths:
    safe_id = sanitize_workspace_id(workspace_id)
    root = WORKSPACES_DIR / safe_id
    paths = WorkspacePaths(
        workspace_id=safe_id,
        root=root,
        tmp_source_audio_dir=root / "tmp" / "source_audio",
        voice_params_dir=root / "voice_params",
        generated_audio_dir=root / "generated_audio",
    )
    paths.tmp_source_audio_dir.mkdir(parents=True, exist_ok=True)
    paths.voice_params_dir.mkdir(parents=True, exist_ok=True)
    paths.generated_audio_dir.mkdir(parents=True, exist_ok=True)
    return paths


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def voice_id(prefix: str = "smxvoice") -> str:
    return f"{prefix}_{timestamp()}"


def display_name_from_voice_id(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title() or value


def save_source_audio(file: FileStorage, paths: WorkspacePaths) -> pathlib.Path:
    safe_name = secure_filename(file.filename or "source_audio.wav")
    original = pathlib.Path(safe_name)
    stem = original.stem or "source_audio"
    ext = original.suffix or ".wav"
    target = paths.tmp_source_audio_dir / f"source_{timestamp()}_{stem}{ext}"
    file.save(target)
    return target


def delete_if_exists(path: pathlib.Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        print("[clone_voice_workspace] Could not delete temporary source:", repr(exc), flush=True)


def save_voice_parameter(paths: WorkspacePaths, voice_parameter: str, new_voice_id: str | None = None) -> tuple[str, pathlib.Path]:
    vid = new_voice_id or voice_id()
    param_path = paths.voice_params_dir / f"{vid}.txt"
    param_path.write_text(voice_parameter.strip(), encoding="utf-8")
    return vid, param_path


def list_workspace_voice_parameters(paths: WorkspacePaths) -> list[dict[str, str]]:
    voices: list[dict[str, str]] = []

    paths.voice_params_dir.mkdir(parents=True, exist_ok=True)

    for param_path in sorted(paths.voice_params_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        voice_id_value = param_path.stem
        voices.append({
            "voiceId": voice_id_value,
            "displayName": display_name_from_voice_id(voice_id_value),
            "voiceParamPath": relative_to_root(param_path),
        })

    return voices


def load_workspace_voice_parameter(paths: WorkspacePaths, requested_voice_id: str) -> tuple[str, pathlib.Path]:
    safe_voice_id = pathlib.Path(requested_voice_id).name.strip()

    if not safe_voice_id:
        raise FileNotFoundError("Missing saved voiceId")

    param_path = paths.voice_params_dir / f"{safe_voice_id}.txt"

    if not param_path.exists() or not param_path.is_file():
        raise FileNotFoundError(f"Saved voice parameter not found: {safe_voice_id}")

    value = param_path.read_text(encoding="utf-8").strip()

    if not value:
        raise RuntimeError(f"Saved voice parameter file is empty: {param_path}")

    return value, param_path


def generated_audio_path(paths: WorkspacePaths, prefix: str = "narration") -> pathlib.Path:
    return paths.generated_audio_dir / f"{prefix}_{timestamp()}.wav"


def workspace_generated_audio_url(paths: WorkspacePaths, output_path: pathlib.Path) -> str:
    return f"/media/workspaces/{paths.workspace_id}/generated_audio/{output_path.name}"


def relative_to_root(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)).replace(os.sep, "/")
''', encoding="utf-8")

CONTROLLER.write_text(r'''from __future__ import annotations

from flask import jsonify, request, send_from_directory

from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_system import SYSTEM_PREVIEWS_DIR, list_system_voices_payload, load_system_voice_parameter
from services.clone_voice_workspace import (
    MOCK_WORKSPACE_ID,
    delete_if_exists,
    generated_audio_path,
    get_workspace,
    list_workspace_voice_parameters,
    load_workspace_voice_parameter,
    relative_to_root,
    save_source_audio,
    save_voice_parameter,
    workspace_generated_audio_url,
)


def _error(message: str, status: int = 500):
    return jsonify({"ok": False, "message": message, "error": message}), status


def _print_received_source(prompt: str, audio_file) -> None:
    print("\n" + "=" * 100, flush=True)
    print("[clone_voice_controller] FROM SOURCE", flush=True)
    print("FORM KEYS:", list(request.form.keys()), flush=True)
    print("FILE KEYS:", list(request.files.keys()), flush=True)
    print("prompt_length:", len(prompt), flush=True)

    if audio_file:
        print("audio.filename:", repr(audio_file.filename), flush=True)
        print("audio.mimetype:", repr(audio_file.mimetype), flush=True)
        print("audio.content_type:", repr(audio_file.content_type), flush=True)
    else:
        print("audio: None", flush=True)

    print("=" * 100 + "\n", flush=True)


def register_clone_voice_routes(app):
    if "clone_voice_system_voices" not in app.view_functions:
        @app.get("/api/clone-voice/system-voices", endpoint="clone_voice_system_voices")
        def system_voices():
            voices = list_system_voices_payload()
            print("[clone_voice_controller] System voices:", voices, flush=True)
            return jsonify({"ok": True, "voices": voices})

    if "clone_voice_my_voices" not in app.view_functions:
        @app.get("/api/clone-voice/my-voices", endpoint="clone_voice_my_voices")
        def my_voices():
            workspace_id = request.args.get("workspaceId", MOCK_WORKSPACE_ID)
            workspace = get_workspace(workspace_id)
            voices = list_workspace_voice_parameters(workspace)

            print("[clone_voice_controller] My saved voices:", voices, flush=True)

            return jsonify({
                "ok": True,
                "workspaceId": workspace.workspace_id,
                "voices": voices,
            })

    if "clone_voice_from_source" not in app.view_functions:
        @app.post("/api/clone-voice/from-source", endpoint="clone_voice_from_source")
        def from_source():
            prompt = request.form.get("prompt", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            source_mode = request.form.get("sourceMode", "upload")
            audio_file = request.files.get("audio")

            _print_received_source(prompt, audio_file)

            if not prompt:
                return _error("Missing prompt", 400)

            if audio_file is None or not audio_file.filename:
                return _error("Missing uploaded audio file under field name 'audio'", 400)

            workspace = get_workspace(workspace_id)
            source_path = None

            try:
                source_path = save_source_audio(audio_file, workspace)
                print("[clone_voice_controller] Temporary source saved:", source_path, flush=True)

                voice_parameter = create_voice_parameter(source_path, audio_file.mimetype)
                voice_id, param_path = save_voice_parameter(workspace, voice_parameter)
                print("[clone_voice_controller] Private voice parameter saved:", param_path, flush=True)

                output_path = generated_audio_path(workspace, "narration")
                generate_narration_to_file(voice_parameter, prompt, output_path)
                asset_url = workspace_generated_audio_url(workspace, output_path)

                return jsonify({
                    "ok": True,
                    "sourceType": source_mode,
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "voiceParamPath": relative_to_root(param_path),
                    "rawSourceDeleted": True,
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                })

            except Exception as exc:
                print("[clone_voice_controller] from-source error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                if source_path is not None:
                    delete_if_exists(source_path)
                    print("[clone_voice_controller] Temporary source deleted:", source_path, flush=True)

    if "clone_voice_from_saved" not in app.view_functions:
        @app.post("/api/clone-voice/from-saved", endpoint="clone_voice_from_saved")
        def from_saved():
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] FROM SAVED VOICE", flush=True)
            print("workspaceId:", repr(workspace_id), flush=True)
            print("voiceId:", repr(voice_id), flush=True)
            print("prompt_length:", len(prompt), flush=True)
            print("=" * 100 + "\n", flush=True)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)

                output_path = generated_audio_path(workspace, "saved_voice_narration")
                generate_narration_to_file(voice_parameter, prompt, output_path)
                asset_url = workspace_generated_audio_url(workspace, output_path)

                return jsonify({
                    "ok": True,
                    "sourceType": "saved",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "voiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                })

            except Exception as exc:
                print("[clone_voice_controller] from-saved error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_from_system" not in app.view_functions:
        @app.post("/api/clone-voice/from-system", endpoint="clone_voice_from_system")
        def from_system():
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] FROM SYSTEM", flush=True)
            print("voiceId:", repr(voice_id), flush=True)
            print("prompt_length:", len(prompt), flush=True)
            print("=" * 100 + "\n", flush=True)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_system_voice_parameter(voice_id)

                output_path = generated_audio_path(workspace, "system_voice_narration")
                generate_narration_to_file(voice_parameter, prompt, output_path)
                asset_url = workspace_generated_audio_url(workspace, output_path)

                return jsonify({
                    "ok": True,
                    "sourceType": "system",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "systemVoiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                })

            except Exception as exc:
                print("[clone_voice_controller] from-system error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_workspace_audio" not in app.view_functions:
        @app.get("/media/workspaces/<workspace_id>/generated_audio/<path:filename>", endpoint="clone_voice_workspace_audio")
        def workspace_audio(workspace_id: str, filename: str):
            workspace = get_workspace(workspace_id)
            return send_from_directory(workspace.generated_audio_dir, filename)

    if "clone_voice_preview_audio" not in app.view_functions:
        @app.get("/media/voices/previews/<path:filename>", endpoint="clone_voice_preview_audio")
        def preview_audio(filename: str):
            return send_from_directory(SYSTEM_PREVIEWS_DIR, filename)
''', encoding="utf-8")

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/client.css?v=saved1">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p>Upload audio, record your voice, reuse your saved private voices, or generate narration from a system voice.</p>
    </header>

    <section class="card">
      <div class="tabs" role="tablist" aria-label="Voice source">
        <button class="tab active" id="uploadTab" type="button" data-mode="upload">Upload audio</button>
        <button class="tab" id="recordTab" type="button" data-mode="record">Record my voice</button>
        <button class="tab" id="savedTab" type="button" data-mode="saved">My saved voices</button>
        <button class="tab" id="systemTab" type="button" data-mode="system">System voice</button>
      </div>

      <form id="cloneVoiceForm">
        <div class="panel" id="uploadPanel">
          <label>
            Upload audio file
            <input id="audioInput" name="audio" type="file" accept="audio/*">
          </label>
          <p class="status" id="uploadStatus">No uploaded file selected.</p>
        </div>

        <div class="panel" id="recordPanel" hidden>
          <div class="inner-card">
            <h3 id="recordingTitle">Recorder ready</h3>
            <p class="status" id="recordingStatus">Start recording, speak clearly, then stop. The recording will be sent as a WAV file.</p>
            <div class="row-actions">
              <button class="secondary" id="startRecording" type="button">Start recording</button>
              <button class="secondary" id="stopRecording" type="button" disabled>Stop recording</button>
              <button class="secondary" id="discardRecording" type="button" disabled>Discard recording</button>
            </div>
            <audio id="recordedPreview" controls hidden></audio>
          </div>
        </div>

        <div class="panel" id="savedPanel" hidden>
          <div class="inner-card">
            <h3>My saved voices</h3>
            <p class="status">Private reusable voice parameters are loaded from <code>workspaces/mock_user_001/voice_params/</code>.</p>
            <button class="secondary wide" id="toggleSavedVoices" type="button">Show my saved voices</button>
            <div id="savedVoiceList" class="voice-list" hidden></div>
          </div>
        </div>

        <div class="panel" id="systemPanel" hidden>
          <div class="inner-card">
            <h3>System voices</h3>
            <p class="status">Reusable system voice parameters are loaded from <code>voices/params/</code>. Preview audio is loaded from <code>voices/previews/</code>.</p>
            <button class="secondary wide" id="toggleSystemVoices" type="button">Show system voices</button>
            <div id="systemVoiceList" class="voice-list" hidden></div>
          </div>
        </div>

        <label>
          Narration text
          <textarea id="promptInput" name="prompt" required placeholder="Paste narration text here"></textarea>
        </label>

        <button id="submitBtn" type="submit">Generate narration</button>
      </form>
    </section>

    <section class="card">
      <h2 id="resultTitle">No narration yet</h2>
      <div id="audioResult"></div>
      <pre id="resultBox">No request sent yet.</pre>
    </section>
  </main>

  <script src="/clone_voice/client.js?v=saved1"></script>
</body>
</html>
''', encoding="utf-8")

CSS.write_text(r'''* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, sans-serif; background: #071017; color: #e8f1f8; padding: 32px; }
.shell { max-width: 980px; margin: 0 auto; display: grid; gap: 20px; }
.hero, .card { border: 1px solid #33414c; border-radius: 16px; padding: 20px; background: #111b24; }
.eyebrow, .status, .hero p { color: #a9bfd3; line-height: 1.55; }
h1, h2, h3, p { margin-top: 0; }
label { display: grid; gap: 8px; margin-bottom: 16px; font-weight: 800; }
input, textarea, button { font: inherit; }
input[type="file"], textarea { width: 100%; border: 1px solid #465662; border-radius: 12px; padding: 12px; background: #202b35; color: #fff; }
textarea { min-height: 190px; resize: vertical; }
button { border: 0; border-radius: 999px; padding: 14px 22px; background: linear-gradient(135deg, #9ee8dc, #82a8ff); color: #06130f; font-weight: 900; cursor: pointer; }
button.secondary { background: #2c3741; color: #e8f1f8; border: 1px solid #465662; }
button:disabled { opacity: .55; cursor: not-allowed; }
.tabs { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.tab { background: #2c3741; color: #e8f1f8; border: 1px solid #465662; min-width: 180px; }
.tab.active { background: linear-gradient(135deg, #9ee8dc, #82a8ff); color: #06130f; }
.panel[hidden], .voice-list[hidden] { display: none !important; }
.inner-card { display: grid; gap: 14px; border: 1px solid #33414c; border-radius: 14px; padding: 16px; background: #202b35; margin-bottom: 16px; }
.row-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.voice-list { display: grid; gap: 10px; margin-top: 16px; }
.voice-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; border: 1px solid #465662; border-radius: 999px; padding: 10px 12px 10px 18px; background: #101820; }
.voice-row.selected { outline: 3px solid rgba(158,232,220,.35); }
.voice-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 900; letter-spacing: .02em; }
.voice-actions { display: flex; gap: 8px; align-items: center; }
.icon-button { width: 58px; min-width: 58px; padding-left: 0; padding-right: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 20px; line-height: 1; }
.wide { width: 100%; }
audio { width: 100%; margin-top: 12px; }
pre { white-space: pre-wrap; overflow: auto; max-height: 360px; background: #02070b; border: 1px solid #33414c; border-radius: 12px; padding: 16px; }
.download-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.download-actions a { color: #06130f; background: linear-gradient(135deg, #9ee8dc, #82a8ff); padding: 12px 18px; border-radius: 999px; font-weight: 900; text-decoration: none; }
code { color: #9ee8dc; }
@media (max-width: 720px) {
  body { padding: 18px; }
  .tab { width: 100%; }
  .voice-row { grid-template-columns: 1fr; border-radius: 16px; }
  .voice-actions button { width: 100%; }
  .icon-button { width: 100%; }
}
''', encoding="utf-8")

JS.write_text(r'''(() => {
  const $ = (selector) => document.querySelector(selector);

  const WORKSPACE_ID = "mock_user_001";

  const tabs = [...document.querySelectorAll(".tab[data-mode]")];
  const panels = {
    upload: $("#uploadPanel"),
    record: $("#recordPanel"),
    saved: $("#savedPanel"),
    system: $("#systemPanel"),
  };

  const form = $("#cloneVoiceForm");
  const audioInput = $("#audioInput");
  const uploadStatus = $("#uploadStatus");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const startRecordingBtn = $("#startRecording");
  const stopRecordingBtn = $("#stopRecording");
  const discardRecordingBtn = $("#discardRecording");
  const recordingTitle = $("#recordingTitle");
  const recordingStatus = $("#recordingStatus");
  const recordedPreview = $("#recordedPreview");

  const toggleSavedVoicesBtn = $("#toggleSavedVoices");
  const savedVoiceList = $("#savedVoiceList");

  const toggleSystemVoicesBtn = $("#toggleSystemVoices");
  const systemVoiceList = $("#systemVoiceList");

  const resultTitle = $("#resultTitle");
  const audioResult = $("#audioResult");
  const resultBox = $("#resultBox");

  let sourceMode = "upload";

  let savedVoices = [];
  let selectedSavedVoice = null;
  let savedVoicesLoaded = false;

  let systemVoices = [];
  let selectedSystemVoice = null;
  let systemVoicesLoaded = false;
  let previewAudio = null;
  let previewIndex = null;

  let audioContext = null;
  let micStream = null;
  let micSource = null;
  let recorderNode = null;
  let recordingBuffers = [];
  let recordingSampleRate = 44100;
  let recordedBlob = null;
  let recordedFilename = "";

  function setMode(mode) {
    sourceMode = mode;

    tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.mode === mode));
    Object.entries(panels).forEach(([key, panel]) => { panel.hidden = key !== mode; });

    if (mode !== "system") stopPreview();

    console.log("[Clone Voice] sourceMode:", sourceMode);
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));

  audioInput.addEventListener("change", () => {
    const file = audioInput.files[0] || null;
    uploadStatus.textContent = file ? `${file.name} is ready.` : "No uploaded file selected.";
    console.log("[Clone Voice] upload selected:", file ? { name: file.name, type: file.type, size: file.size } : null);
  });

  function setVoiceListOpen(listEl, toggleBtn, open, openText, closeText) {
    listEl.hidden = !open;
    toggleBtn.textContent = open ? closeText : openText;
  }

  function renderSimpleVoiceList({ listEl, voices, selectedVoice, type }) {
    if (!voices.length) {
      listEl.innerHTML = `<p class="status">No voices found.</p>`;
      return;
    }

    listEl.innerHTML = voices.map((voice, index) => {
      const selected = selectedVoice && selectedVoice.voiceId === voice.voiceId;
      const name = voice.displayName || voice.voiceId;

      const previewButton = type === "system" && voice.previewUrl
        ? `<button class="secondary icon-button" type="button" data-system-play-index="${index}" title="Play preview" aria-label="Play preview">▶</button>`
        : "";

      return `
        <div class="voice-row ${selected ? "selected" : ""}">
          <div class="voice-name">${escapeHtml(name)}</div>
          <div class="voice-actions">
            ${previewButton}
            <button type="button" data-${type}-use-index="${index}">${selected ? "Selected" : "Use"}</button>
          </div>
        </div>
      `;
    }).join("");
  }

  async function loadSavedVoices() {
    setVoiceListOpen(savedVoiceList, toggleSavedVoicesBtn, true, "Show my saved voices", "Close my saved voices");
    savedVoiceList.innerHTML = `<p class="status">Loading my saved voices...</p>`;

    try {
      const response = await fetch(`/api/clone-voice/my-voices?workspaceId=${encodeURIComponent(WORKSPACE_ID)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      console.log("[Clone Voice] my voices response:", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load saved voices");
      }

      savedVoices = Array.isArray(data.voices) ? data.voices : [];
      savedVoicesLoaded = true;

      if (!savedVoices.length) {
        savedVoiceList.innerHTML = `<p class="status">No private voices found yet. Upload or record a voice first.</p>`;
        return;
      }

      renderSimpleVoiceList({
        listEl: savedVoiceList,
        voices: savedVoices,
        selectedVoice: selectedSavedVoice,
        type: "saved"
      });
    } catch (error) {
      console.error("[Clone Voice] my voices failed:", error);
      savedVoiceList.innerHTML = `<p class="status">${escapeHtml(error.message || String(error))}</p>`;
    }
  }

  toggleSavedVoicesBtn.addEventListener("click", async () => {
    if (!savedVoiceList.hidden) {
      setVoiceListOpen(savedVoiceList, toggleSavedVoicesBtn, false, "Show my saved voices", "Close my saved voices");
      return;
    }

    if (!savedVoicesLoaded) {
      await loadSavedVoices();
      return;
    }

    setVoiceListOpen(savedVoiceList, toggleSavedVoicesBtn, true, "Show my saved voices", "Close my saved voices");
    renderSimpleVoiceList({
      listEl: savedVoiceList,
      voices: savedVoices,
      selectedVoice: selectedSavedVoice,
      type: "saved"
    });
  });

  savedVoiceList.addEventListener("click", (event) => {
    const useButton = event.target.closest("[data-saved-use-index]");

    if (!useButton) return;

    const index = Number(useButton.dataset.savedUseIndex);
    selectedSavedVoice = savedVoices[index] || null;

    console.log("[Clone Voice] selected saved voice:", selectedSavedVoice);

    renderSimpleVoiceList({
      listEl: savedVoiceList,
      voices: savedVoices,
      selectedVoice: selectedSavedVoice,
      type: "saved"
    });
  });

  function stopPreview() {
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.currentTime = 0;
    }

    previewAudio = null;
    previewIndex = null;

    document.querySelectorAll("[data-system-play-index]").forEach((button) => {
      button.textContent = "▶";
      button.title = "Play preview";
      button.setAttribute("aria-label", "Play preview");
    });
  }

  function renderSystemVoices() {
    if (!systemVoices.length) {
      systemVoiceList.innerHTML = `<p class="status">No system voices found. Add .txt files to voices/params/.</p>`;
      return;
    }

    renderSimpleVoiceList({
      listEl: systemVoiceList,
      voices: systemVoices,
      selectedVoice: selectedSystemVoice,
      type: "system"
    });
  }

  async function loadSystemVoices() {
    setVoiceListOpen(systemVoiceList, toggleSystemVoicesBtn, true, "Show system voices", "Close system voices");
    systemVoiceList.innerHTML = `<p class="status">Loading system voices...</p>`;

    try {
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      console.log("[Clone Voice] system voices response:", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      systemVoices = Array.isArray(data.voices) ? data.voices : [];
      systemVoicesLoaded = true;
      renderSystemVoices();
    } catch (error) {
      console.error("[Clone Voice] system voices failed:", error);
      systemVoiceList.innerHTML = `<p class="status">${escapeHtml(error.message || String(error))}</p>`;
    }
  }

  toggleSystemVoicesBtn.addEventListener("click", async () => {
    if (!systemVoiceList.hidden) {
      setVoiceListOpen(systemVoiceList, toggleSystemVoicesBtn, false, "Show system voices", "Close system voices");
      stopPreview();
      return;
    }

    if (!systemVoicesLoaded) {
      await loadSystemVoices();
      return;
    }

    setVoiceListOpen(systemVoiceList, toggleSystemVoicesBtn, true, "Show system voices", "Close system voices");
    renderSystemVoices();
  });

  systemVoiceList.addEventListener("click", async (event) => {
    const playButton = event.target.closest("[data-system-play-index]");
    const useButton = event.target.closest("[data-system-use-index]");

    if (playButton) {
      const index = Number(playButton.dataset.systemPlayIndex);
      const voice = systemVoices[index];

      if (!voice || !voice.previewUrl) return;

      if (previewIndex === index && previewAudio && !previewAudio.paused) {
        stopPreview();
        return;
      }

      stopPreview();

      previewIndex = index;
      previewAudio = new Audio(voice.previewUrl);

      playButton.textContent = "■";
      playButton.title = "Stop preview";
      playButton.setAttribute("aria-label", "Stop preview");

      previewAudio.addEventListener("ended", stopPreview);
      previewAudio.addEventListener("error", stopPreview);

      try {
        await previewAudio.play();
      } catch (error) {
        console.error("[Clone Voice] preview failed:", error);
        stopPreview();
      }

      return;
    }

    if (useButton) {
      const index = Number(useButton.dataset.systemUseIndex);
      selectedSystemVoice = systemVoices[index] || null;

      console.log("[Clone Voice] selected system voice:", selectedSystemVoice);

      renderSystemVoices();
    }
  });

  function flattenBuffers(buffers) {
    const totalLength = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
    const result = new Float32Array(totalLength);
    let offset = 0;

    buffers.forEach((buffer) => {
      result.set(buffer, offset);
      offset += buffer.length;
    });

    return result;
  }

  function writeString(view, offset, value) {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  }

  function encodeWav(floatSamples, sampleRate) {
    const bytesPerSample = 2;
    const channelCount = 1;
    const dataLength = floatSamples.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, channelCount, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * channelCount * bytesPerSample, true);
    view.setUint16(32, channelCount * bytesPerSample, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, "data");
    view.setUint32(40, dataLength, true);

    let offset = 44;

    for (let i = 0; i < floatSamples.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, floatSamples[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }

    return buffer;
  }

  async function startRecording() {
    try {
      recordedBlob = null;
      recordingBuffers = [];

      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      recordingSampleRate = audioContext.sampleRate;

      micSource = audioContext.createMediaStreamSource(micStream);
      recorderNode = audioContext.createScriptProcessor(4096, 1, 1);

      recorderNode.onaudioprocess = (event) => {
        recordingBuffers.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };

      micSource.connect(recorderNode);
      recorderNode.connect(audioContext.destination);

      startRecordingBtn.disabled = true;
      stopRecordingBtn.disabled = false;
      discardRecordingBtn.disabled = true;

      recordingTitle.textContent = "Recording...";
      recordingStatus.textContent = "Speak clearly. Click Stop recording when done.";
    } catch (error) {
      console.error("[Clone Voice] recorder failed:", error);
      alert(error.message || "Could not access microphone.");
    }
  }

  async function stopRecording() {
    try {
      if (recorderNode) {
        recorderNode.disconnect();
        recorderNode.onaudioprocess = null;
      }

      if (micSource) micSource.disconnect();
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      if (audioContext) await audioContext.close();

      const merged = flattenBuffers(recordingBuffers);

      if (!merged.length) {
        throw new Error("No recorded audio was captured.");
      }

      const wavBuffer = encodeWav(merged, recordingSampleRate);

      recordedBlob = new Blob([wavBuffer], { type: "audio/wav" });
      recordedFilename = `recorded_voice_${Date.now()}.wav`;

      recordedPreview.src = URL.createObjectURL(recordedBlob);
      recordedPreview.hidden = false;

      startRecordingBtn.disabled = false;
      stopRecordingBtn.disabled = true;
      discardRecordingBtn.disabled = false;

      recordingTitle.textContent = "Recording ready";
      recordingStatus.textContent = `${recordedFilename} is ready.`;
    } catch (error) {
      console.error("[Clone Voice] stop recording failed:", error);
      alert(error.message || "Could not finish recording.");
    }
  }

  function discardRecording() {
    recordedBlob = null;
    recordedFilename = "";
    recordingBuffers = [];

    if (recordedPreview.src) {
      URL.revokeObjectURL(recordedPreview.src);
    }

    recordedPreview.removeAttribute("src");
    recordedPreview.hidden = true;

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
    discardRecordingBtn.disabled = true;

    recordingTitle.textContent = "Recorder ready";
    recordingStatus.textContent = "Start recording, speak clearly, then stop.";
  }

  startRecordingBtn.addEventListener("click", startRecording);
  stopRecordingBtn.addEventListener("click", stopRecording);
  discardRecordingBtn.addEventListener("click", discardRecording);

  async function submitUploadOrRecord(prompt) {
    let fileOrBlob = null;
    let filename = "";

    if (sourceMode === "upload") {
      fileOrBlob = audioInput.files[0] || null;
      filename = fileOrBlob ? fileOrBlob.name : "";
    } else {
      fileOrBlob = recordedBlob;
      filename = recordedFilename || `recorded_voice_${Date.now()}.wav`;
    }

    if (!fileOrBlob) {
      alert(sourceMode === "record" ? "Record your voice first." : "Choose an audio file first.");
      return null;
    }

    const formData = new FormData();
    formData.append("prompt", prompt);
    formData.append("audio", fileOrBlob, filename);
    formData.append("workspaceId", WORKSPACE_ID);
    formData.append("sourceMode", sourceMode);

    return fetch("/api/clone-voice/from-source", {
      method: "POST",
      body: formData
    });
  }

  async function submitSaved(prompt) {
    if (!selectedSavedVoice) {
      alert("Choose one of your saved voices first.");
      return null;
    }

    const formData = new FormData();
    formData.append("prompt", prompt);
    formData.append("voiceId", selectedSavedVoice.voiceId);
    formData.append("workspaceId", WORKSPACE_ID);

    return fetch("/api/clone-voice/from-saved", {
      method: "POST",
      body: formData
    });
  }

  async function submitSystem(prompt) {
    if (!selectedSystemVoice) {
      alert("Choose a system voice first.");
      return null;
    }

    const formData = new FormData();
    formData.append("prompt", prompt);
    formData.append("voiceId", selectedSystemVoice.voiceId);
    formData.append("workspaceId", WORKSPACE_ID);

    return fetch("/api/clone-voice/from-system", {
      method: "POST",
      body: formData
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const prompt = promptInput.value.trim();

    if (!prompt) {
      alert("Paste narration text first.");
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";
    resultTitle.textContent = "Generating narration";
    audioResult.innerHTML = "";
    resultBox.textContent = "Working... Check Flask terminal for logs.";

    try {
      let response = null;

      if (sourceMode === "upload" || sourceMode === "record") {
        response = await submitUploadOrRecord(prompt);
      }

      if (sourceMode === "saved") {
        response = await submitSaved(prompt);
      }

      if (sourceMode === "system") {
        response = await submitSystem(prompt);
      }

      if (!response) return;

      const text = await response.text();

      let data;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      console.log("[Clone Voice] backend response:", data);

      resultBox.textContent = JSON.stringify(data, null, 2);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

      resultTitle.textContent = "Narration ready";

      const url = data.assetUrl || data.audioUrl;

      if (url) {
        audioResult.innerHTML = `
          <audio src="${url}" controls></audio>
          <div class="download-actions">
            <a href="${url}" download>Download</a>
          </div>
        `;
      }

      if ((sourceMode === "upload" || sourceMode === "record") && data.voiceId) {
        savedVoicesLoaded = false;
      }
    } catch (error) {
      console.error("[Clone Voice] generation failed:", error);
      resultTitle.textContent = "Narration failed";
      resultBox.textContent = error.message || String(error);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Generate narration";
    }
  });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[char]));
  }

  setMode("upload");

  console.log("[Clone Voice] clean client with saved voices loaded");
})();
''', encoding="utf-8")

py_compile.compile(str(WORKSPACE_SERVICE), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("My Saved Voices added to clean Clone Voice.")
print()
print("New routes:")
print("  GET  /api/clone-voice/my-voices")
print("  POST /api/clone-voice/from-saved")
print()
print("Saved voice folder:")
print("  workspaces/mock_user_001/voice_params/")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?saved=1")
