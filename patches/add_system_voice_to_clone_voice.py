from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice_debug_print.html"

if not CONTROLLER.exists():
    print("ERROR: controllers/clone_voice_controller.py not found.")
    raise SystemExit(1)

if not HTML.exists():
    print("ERROR: frontend/clone_voice_debug_print.html not found.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CONTROLLER, HTML]:
    backup = path.with_name(path.name + f".bak.system-voice-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

CONTROLLER.write_text(r'''from __future__ import annotations

import mimetypes
import os
import pathlib
import re
from datetime import datetime
from typing import Any

import requests
from flask import jsonify, request, send_from_directory
from werkzeug.utils import secure_filename


ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT / "workspaces"
MOCK_WORKSPACE_ID = "mock_user_001"

VOICE_SOURCE_TMP_DIRNAME = "voice_sources_tmp"
VOICE_PARAMS_DIRNAME = "voice_params"
GENERATED_AUDIO_DIRNAME = "generated_audio"

DEFAULT_MODEL = "qwen3-tts-vc-2026-01-22"


def _workspace_root(workspace_id: str = MOCK_WORKSPACE_ID) -> pathlib.Path:
    root = WORKSPACES_DIR / workspace_id
    (root / VOICE_SOURCE_TMP_DIRNAME).mkdir(parents=True, exist_ok=True)
    (root / VOICE_PARAMS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (root / GENERATED_AUDIO_DIRNAME).mkdir(parents=True, exist_ok=True)
    return root


def _system_voice_dirs() -> list[pathlib.Path]:
    return [
        WORKSPACES_DIR / "system" / VOICE_PARAMS_DIRNAME,
        ROOT / "system_voice_params",
        ROOT / "voices" / "params",
        ROOT / "voice_params",
    ]


def _system_preview_dirs() -> list[pathlib.Path]:
    return [
        WORKSPACES_DIR / "system" / "voice_previews",
        ROOT / "system_voice_previews",
        ROOT / "voices" / "previews",
        ROOT / "voice_previews",
    ]


def _ensure_system_dirs() -> None:
    (WORKSPACES_DIR / "system" / VOICE_PARAMS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (WORKSPACES_DIR / "system" / "voice_previews").mkdir(parents=True, exist_ok=True)


def _safe_id(prefix: str = "smxvoice") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}"


def _safe_source_filename(original_name: str) -> str:
    safe = secure_filename(original_name or "source_audio.wav")
    stem = pathlib.Path(safe).stem or "source_audio"
    ext = pathlib.Path(safe).suffix or ".wav"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"source_{stamp}_{stem}{ext}"


def _display_name(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().title() or stem


def _file_size(uploaded_file: Any) -> int | str:
    try:
        pos = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0, os.SEEK_END)
        size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(pos)
        return size
    except Exception as exc:
        return f"unknown: {exc!r}"


def _first_bytes(uploaded_file: Any, length: int = 16) -> str:
    try:
        pos = uploaded_file.stream.tell()
        data = uploaded_file.stream.read(length)
        uploaded_file.stream.seek(pos)
        return repr(data)
    except Exception as exc:
        return f"unreadable: {exc!r}"


def _print_upload_debug(prompt: str, audio_file: Any) -> None:
    print("\n" + "=" * 100, flush=True)
    print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] UPLOAD RECEIVED", flush=True)
    print("PATH:", request.path, flush=True)
    print("METHOD:", request.method, flush=True)
    print("CONTENT_TYPE:", request.content_type, flush=True)
    print("FORM KEYS:", list(request.form.keys()), flush=True)
    print("FILE KEYS:", list(request.files.keys()), flush=True)
    print("prompt_length:", len(prompt), flush=True)
    print("prompt_preview:", repr(prompt[:500]), flush=True)

    if audio_file is None:
        print("request.files.get('audio') = None", flush=True)
    else:
        print("request.files.get('audio') FOUND", flush=True)
        print("  field: 'audio'", flush=True)
        print("  filename:", repr(audio_file.filename), flush=True)
        print("  mimetype:", repr(audio_file.mimetype), flush=True)
        print("  content_type:", repr(audio_file.content_type), flush=True)
        print("  size_bytes:", _file_size(audio_file), flush=True)
        print("  first_16_bytes:", _first_bytes(audio_file), flush=True)

    print("=" * 100 + "\n", flush=True)


def _response_audio_url(response: Any) -> str | None:
    try:
        output = response.get("output", {})
        audio = output.get("audio", {})
        return audio.get("url")
    except Exception:
        return None


def _download_audio(audio_url: str, output_path: pathlib.Path) -> None:
    response = requests.get(audio_url, timeout=180)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def _create_voice_param_from_source(source_path: pathlib.Path, audio_mime_type: str) -> str:
    import ali_voice_clone as voice_feature

    print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Creating voice parameter from:", source_path, flush=True)
    print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] audio_mime_type:", audio_mime_type, flush=True)

    return voice_feature.create_voice(
        str(source_path),
        target_model=DEFAULT_MODEL,
        audio_mime_type=audio_mime_type or "audio/mpeg",
    )


def _generate_narration(voice_parameter: str, prompt: str) -> Any:
    import dashscope
    import ali_voice_clone as voice_feature

    workspace_id = os.getenv("SINGAPORE_WORKSPACE_ID") or os.getenv("ALIBABA_WORKSPACE_ID") or ""
    api_key = os.getenv("SINGAPORE_API_KEY") or os.getenv("ALIBABA_API_KEY") or ""

    if not workspace_id or not api_key:
        raise RuntimeError("Missing SINGAPORE_API_KEY or SINGAPORE_WORKSPACE_ID in .env")

    dashscope.base_http_api_url = f"https://{workspace_id}.ap-southeast-1.maas.aliyuncs.com/api/v1"

    return voice_feature.clone_voice(
        api_key=api_key,
        model=DEFAULT_MODEL,
        voice=voice_parameter,
        text=prompt,
        stream=False,
    )


def _find_system_voice_param(voice_id: str) -> pathlib.Path | None:
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", voice_id).strip()
    if not safe_id:
        return None

    for folder in _system_voice_dirs():
        candidate = folder / f"{safe_id}.txt"
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def _find_preview_url(voice_id: str) -> str | None:
    for folder in _system_preview_dirs():
        for ext in ("wav", "mp3", "m4a", "ogg", "webm"):
            for name in (f"{voice_id}.{ext}", f"{voice_id}_preview.{ext}"):
                candidate = folder / name
                if candidate.exists() and candidate.is_file():
                    rel = candidate.relative_to(ROOT).as_posix()
                    return f"/media/{rel}"
    return None


def _list_system_voices() -> list[dict[str, str | None]]:
    _ensure_system_dirs()

    voices: dict[str, dict[str, str | None]] = {}

    for folder in _system_voice_dirs():
        if not folder.exists():
            continue

        for param_path in sorted(folder.glob("*.txt")):
            voice_id = param_path.stem
            if voice_id in voices:
                continue

            voices[voice_id] = {
                "voiceId": voice_id,
                "displayName": _display_name(voice_id),
                "previewUrl": _find_preview_url(voice_id),
            }

    return list(voices.values())


def _save_generated_audio_from_response(response: Any, workspace_id: str, prefix: str) -> tuple[str, pathlib.Path]:
    workspace_root = _workspace_root(workspace_id)
    output_dir = workspace_root / GENERATED_AUDIO_DIRNAME
    output_filename = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.wav"
    output_path = output_dir / output_filename

    audio_url = _response_audio_url(response)
    if not audio_url:
        raise RuntimeError("Narration response did not include an audio URL")

    _download_audio(audio_url, output_path)

    asset_url = f"/media/workspaces/{workspace_id}/generated_audio/{output_filename}"
    return asset_url, output_path


def register_clone_voice_routes(app):
    if "clone_voice_create_and_generate" not in app.view_functions:
        @app.route("/api/clone-voice/create-and-generate", methods=["POST"], endpoint="clone_voice_create_and_generate")
        def clone_voice_create_and_generate():
            prompt = request.form.get("prompt", "").strip()
            audio_file = request.files.get("audio")

            _print_upload_debug(prompt, audio_file)

            if not prompt:
                return jsonify({"ok": False, "message": "Missing prompt"}), 400

            if audio_file is None or not audio_file.filename:
                return jsonify({"ok": False, "message": "Missing uploaded audio file under field name 'audio'"}), 400

            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID).strip() or MOCK_WORKSPACE_ID
            workspace_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", workspace_id)

            workspace_root = _workspace_root(workspace_id)
            tmp_dir = workspace_root / VOICE_SOURCE_TMP_DIRNAME
            params_dir = workspace_root / VOICE_PARAMS_DIRNAME

            tmp_source_path = tmp_dir / _safe_source_filename(audio_file.filename)
            voice_id = _safe_id("smxvoice")
            param_path = params_dir / f"{voice_id}.txt"

            try:
                audio_file.save(tmp_source_path)
                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved temporary source audio:", tmp_source_path, flush=True)

                audio_mime_type = audio_file.mimetype or mimetypes.guess_type(tmp_source_path.name)[0] or "audio/mpeg"

                voice_parameter = _create_voice_param_from_source(tmp_source_path, audio_mime_type)
                param_path.write_text(voice_parameter, encoding="utf-8")
                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved private voice parameter:", param_path, flush=True)

                response = _generate_narration(voice_parameter, prompt)
                asset_url, output_path = _save_generated_audio_from_response(response, workspace_id, "narration")

                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved generated narration:", output_path, flush=True)

                return jsonify({
                    "ok": True,
                    "controller": "clone_voice_controller",
                    "sourceType": request.form.get("sourceMode") or "upload",
                    "workspaceId": workspace_id,
                    "voiceId": voice_id,
                    "voiceParamPath": str(param_path.relative_to(ROOT)).replace(os.sep, "/"),
                    "rawSourceDeleted": True,
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": str(output_path.relative_to(ROOT)).replace(os.sep, "/"),
                })

            except Exception as exc:
                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] ERROR:", repr(exc), flush=True)
                return jsonify({
                    "ok": False,
                    "message": str(exc),
                    "controller": "clone_voice_controller",
                }), 500

            finally:
                try:
                    if tmp_source_path.exists():
                        tmp_source_path.unlink()
                        print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Deleted temporary source audio:", tmp_source_path, flush=True)
                except Exception as cleanup_exc:
                    print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Could not delete temporary source audio:", repr(cleanup_exc), flush=True)

    if "clone_voice_system_voices" not in app.view_functions:
        @app.route("/api/clone-voice/system-voices", methods=["GET"], endpoint="clone_voice_system_voices")
        def clone_voice_system_voices():
            voices = _list_system_voices()
            print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] System voices found:", voices, flush=True)
            return jsonify({
                "ok": True,
                "voices": voices,
                "systemFolders": [str(path.relative_to(ROOT)).replace(os.sep, "/") for path in _system_voice_dirs()],
            })

    if "clone_voice_generate_system" not in app.view_functions:
        @app.route("/api/clone-voice/generate-system", methods=["POST"], endpoint="clone_voice_generate_system")
        def clone_voice_generate_system():
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID).strip() or MOCK_WORKSPACE_ID
            workspace_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", workspace_id)

            print("\n" + "=" * 100, flush=True)
            print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] SYSTEM VOICE GENERATE", flush=True)
            print("prompt_length:", len(prompt), flush=True)
            print("voice_id:", repr(voice_id), flush=True)
            print("workspace_id:", workspace_id, flush=True)
            print("=" * 100 + "\n", flush=True)

            if not prompt:
                return jsonify({"ok": False, "message": "Missing prompt"}), 400

            if not voice_id:
                return jsonify({"ok": False, "message": "Missing voiceId"}), 400

            param_path = _find_system_voice_param(voice_id)
            if not param_path:
                return jsonify({"ok": False, "message": f"System voice parameter not found for voiceId: {voice_id}"}), 404

            try:
                voice_parameter = param_path.read_text(encoding="utf-8").strip()
                if not voice_parameter:
                    raise RuntimeError(f"System voice parameter file is empty: {param_path}")

                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Using system voice parameter:", param_path, flush=True)

                response = _generate_narration(voice_parameter, prompt)
                asset_url, output_path = _save_generated_audio_from_response(response, workspace_id, "system_voice_narration")

                return jsonify({
                    "ok": True,
                    "controller": "clone_voice_controller",
                    "sourceType": "system",
                    "workspaceId": workspace_id,
                    "voiceId": voice_id,
                    "systemVoiceParamPath": str(param_path.relative_to(ROOT)).replace(os.sep, "/"),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": str(output_path.relative_to(ROOT)).replace(os.sep, "/"),
                })

            except Exception as exc:
                print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] SYSTEM VOICE ERROR:", repr(exc), flush=True)
                return jsonify({
                    "ok": False,
                    "message": str(exc),
                    "controller": "clone_voice_controller",
                }), 500

    if "clone_voice_workspace_generated_audio" not in app.view_functions:
        @app.route("/media/workspaces/<workspace_id>/generated_audio/<path:filename>", methods=["GET"])
        def clone_voice_workspace_generated_audio(workspace_id: str, filename: str):
            safe_workspace = re.sub(r"[^a-zA-Z0-9_-]+", "_", workspace_id)
            directory = WORKSPACES_DIR / safe_workspace / GENERATED_AUDIO_DIRNAME
            return send_from_directory(directory, filename)

    if "clone_voice_media_file" not in app.view_functions:
        @app.route("/media/<path:filename>", methods=["GET"])
        def clone_voice_media_file(filename: str):
            return send_from_directory(ROOT, filename)
''', encoding="utf-8")

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #071017; color: #e8f1f8; padding: 32px; }
    main { max-width: 920px; margin: 0 auto; display: grid; gap: 20px; }
    section { border: 1px solid #33414c; border-radius: 16px; padding: 20px; background: #111b24; }
    label { display: grid; gap: 8px; margin-bottom: 16px; font-weight: 700; }
    input, textarea, button { font: inherit; }
    input[type="file"], textarea { border: 1px solid #465662; border-radius: 10px; padding: 12px; background: #202b35; color: #fff; }
    textarea { min-height: 180px; }
    button { border: 0; border-radius: 999px; padding: 14px 22px; background: linear-gradient(135deg, #9ee8dc, #82a8ff); color: #06130f; font-weight: 900; cursor: pointer; }
    button.secondary { background: #2c3741; color: #e8f1f8; border: 1px solid #465662; }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    audio { width: 100%; margin-top: 12px; }
    pre { white-space: pre-wrap; overflow: auto; max-height: 360px; background: #02070b; border: 1px solid #33414c; border-radius: 12px; padding: 16px; }
    .note { color: #9db2c5; line-height: 1.5; }
    .tabs { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
    .tab { background: #2c3741; color: #e8f1f8; border: 1px solid #465662; }
    .tab.active { background: linear-gradient(135deg, #9ee8dc, #82a8ff); color: #06130f; }
    .panel[hidden] { display: none !important; }
    .record-card, .system-card { display: grid; gap: 14px; border: 1px solid #33414c; border-radius: 14px; padding: 16px; background: #202b35; margin-bottom: 16px; }
    .record-actions { display: flex; gap: 12px; flex-wrap: wrap; }
    .status { color: #9db2c5; line-height: 1.5; }
    .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
    .actions a { color: #06130f; background: linear-gradient(135deg, #9ee8dc, #82a8ff); padding: 12px 18px; border-radius: 999px; font-weight: 900; text-decoration: none; }
    .system-list { display: grid; gap: 10px; }
    .system-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; border: 1px solid #465662; border-radius: 999px; padding: 10px 12px; background: #101820; }
    .system-row.selected { outline: 3px solid rgba(158,232,220,.35); }
    .system-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 900; }
    .system-actions { display: flex; gap: 8px; align-items: center; }
    @media (max-width: 720px) {
      .system-row { grid-template-columns: 1fr; border-radius: 16px; }
      .system-actions button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p>SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p class="note">
        Upload audio, record your voice, or use a system voice parameter. System voices use existing .txt voice parameter files.
      </p>
    </header>

    <section>
      <div class="tabs">
        <button class="tab active" id="uploadTab" type="button">Upload audio</button>
        <button class="tab" id="recordTab" type="button">Record my voice</button>
        <button class="tab" id="systemTab" type="button">System voice</button>
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
          <div class="record-card">
            <strong id="recordingTitle">Recorder ready</strong>
            <p class="status" id="recordingStatus">Click Start recording, speak clearly, then click Stop. The recording will be sent as a WAV file.</p>

            <div class="record-actions">
              <button class="secondary" id="startRecording" type="button">Start recording</button>
              <button class="secondary" id="stopRecording" type="button" disabled>Stop recording</button>
              <button class="secondary" id="discardRecording" type="button" disabled>Discard recording</button>
            </div>

            <audio id="recordedPreview" controls hidden></audio>
          </div>
        </div>

        <div class="panel" id="systemPanel" hidden>
          <div class="system-card">
            <strong>System voices</strong>
            <p class="status">
              These are reusable system voice parameter .txt files. Put system .txt parameters in:
              <br>workspaces/system/voice_params/
            </p>
            <button class="secondary" id="refreshSystemVoices" type="button">Refresh system voices</button>
            <div id="systemVoiceList" class="system-list">
              <p class="status">Open this tab to load system voices.</p>
            </div>
          </div>
        </div>

        <label>
          Narration text
          <textarea id="promptInput" name="prompt" required placeholder="Paste narration text here"></textarea>
        </label>

        <button id="submitBtn" type="submit">Generate narration</button>
      </form>
    </section>

    <section>
      <h2 id="resultTitle">No narration yet</h2>
      <div id="audioResult"></div>
      <pre id="resultBox">No request sent yet.</pre>
    </section>
  </main>

  <script>
    const form = document.querySelector("#cloneVoiceForm");

    const uploadTab = document.querySelector("#uploadTab");
    const recordTab = document.querySelector("#recordTab");
    const systemTab = document.querySelector("#systemTab");

    const uploadPanel = document.querySelector("#uploadPanel");
    const recordPanel = document.querySelector("#recordPanel");
    const systemPanel = document.querySelector("#systemPanel");

    const audioInput = document.querySelector("#audioInput");
    const uploadStatus = document.querySelector("#uploadStatus");
    const promptInput = document.querySelector("#promptInput");
    const submitBtn = document.querySelector("#submitBtn");

    const startRecordingBtn = document.querySelector("#startRecording");
    const stopRecordingBtn = document.querySelector("#stopRecording");
    const discardRecordingBtn = document.querySelector("#discardRecording");
    const recordingTitle = document.querySelector("#recordingTitle");
    const recordingStatus = document.querySelector("#recordingStatus");
    const recordedPreview = document.querySelector("#recordedPreview");

    const refreshSystemVoicesBtn = document.querySelector("#refreshSystemVoices");
    const systemVoiceList = document.querySelector("#systemVoiceList");

    const resultTitle = document.querySelector("#resultTitle");
    const audioResult = document.querySelector("#audioResult");
    const resultBox = document.querySelector("#resultBox");

    let sourceMode = "upload";
    let selectedSystemVoice = null;
    let systemVoices = [];

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

      uploadTab.classList.toggle("active", mode === "upload");
      recordTab.classList.toggle("active", mode === "record");
      systemTab.classList.toggle("active", mode === "system");

      uploadPanel.hidden = mode !== "upload";
      recordPanel.hidden = mode !== "record";
      systemPanel.hidden = mode !== "system";

      console.log("[SyntaxMatrix Clone Voice] sourceMode:", sourceMode);

      if (mode === "system") {
        loadSystemVoices();
      }
    }

    uploadTab.addEventListener("click", () => setMode("upload"));
    recordTab.addEventListener("click", () => setMode("record"));
    systemTab.addEventListener("click", () => setMode("system"));

    audioInput.addEventListener("change", () => {
      const file = audioInput.files[0] || null;

      uploadStatus.textContent = file
        ? `${file.name} is ready.`
        : "No uploaded file selected.";

      console.group("[SyntaxMatrix Clone Voice] UPLOAD FILE SELECTED");
      console.log("field name:", "audio");
      console.log("file exists:", Boolean(file));
      if (file) {
        console.log("filename:", file.name);
        console.log("type:", file.type);
        console.log("size:", file.size);
      }
      console.groupEnd();
    });

    async function loadSystemVoices() {
      systemVoiceList.innerHTML = "<p class='status'>Loading system voices...</p>";

      try {
        const response = await fetch("/api/clone-voice/system-voices");
        const data = await response.json();

        if (!response.ok || !data.ok) {
          throw new Error(data.message || data.error || "Could not load system voices");
        }

        systemVoices = Array.isArray(data.voices) ? data.voices : [];

        console.log("[SyntaxMatrix Clone Voice] system voices:", systemVoices);

        if (!systemVoices.length) {
          systemVoiceList.innerHTML = `
            <p class="status">
              No system voices found. Add .txt voice parameter files to:
              <br>workspaces/system/voice_params/
            </p>
          `;
          return;
        }

        renderSystemVoices();
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] system voice load failed:", error);
        systemVoiceList.innerHTML = `<p class="status">${error.message || error}</p>`;
      }
    }

    function renderSystemVoices() {
      systemVoiceList.innerHTML = systemVoices.map((voice, index) => `
        <div class="system-row ${selectedSystemVoice?.voiceId === voice.voiceId ? "selected" : ""}">
          <div class="system-name">${voice.displayName || voice.voiceId}</div>
          <div class="system-actions">
            ${voice.previewUrl ? `<button class="secondary" type="button" data-play-system="${index}">Play</button>` : ""}
            <button type="button" data-use-system="${index}">
              ${selectedSystemVoice?.voiceId === voice.voiceId ? "Selected" : "Use"}
            </button>
          </div>
        </div>
      `).join("");

      systemVoiceList.querySelectorAll("[data-use-system]").forEach(button => {
        button.addEventListener("click", () => {
          selectedSystemVoice = systemVoices[Number(button.dataset.useSystem)];
          console.log("[SyntaxMatrix Clone Voice] selected system voice:", selectedSystemVoice);
          renderSystemVoices();
        });
      });

      systemVoiceList.querySelectorAll("[data-play-system]").forEach(button => {
        button.addEventListener("click", () => {
          const voice = systemVoices[Number(button.dataset.playSystem)];
          if (!voice?.previewUrl) return;
          const audio = new Audio(voice.previewUrl);
          audio.play();
        });
      });
    }

    refreshSystemVoicesBtn.addEventListener("click", loadSystemVoices);

    function flattenBuffers(buffers) {
      const totalLength = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
      const result = new Float32Array(totalLength);
      let offset = 0;

      buffers.forEach(buffer => {
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

        recorderNode.onaudioprocess = event => {
          const input = event.inputBuffer.getChannelData(0);
          recordingBuffers.push(new Float32Array(input));
        };

        micSource.connect(recorderNode);
        recorderNode.connect(audioContext.destination);

        startRecordingBtn.disabled = true;
        stopRecordingBtn.disabled = false;
        discardRecordingBtn.disabled = true;

        recordingTitle.textContent = "Recording...";
        recordingStatus.textContent = "Speak clearly. Click Stop recording when done.";
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] recorder failed:", error);
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
        if (micStream) micStream.getTracks().forEach(track => track.stop());
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
        recordingStatus.textContent = `${recordedFilename} is ready and will be sent as the audio file.`;
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] stop recording failed:", error);
        alert(error.message || "Could not finish recording.");
      }
    }

    function discardRecording() {
      recordedBlob = null;
      recordedFilename = "";
      recordingBuffers = [];

      if (recordedPreview.src) URL.revokeObjectURL(recordedPreview.src);

      recordedPreview.removeAttribute("src");
      recordedPreview.hidden = true;

      startRecordingBtn.disabled = false;
      stopRecordingBtn.disabled = true;
      discardRecordingBtn.disabled = true;

      recordingTitle.textContent = "Recorder ready";
      recordingStatus.textContent = "Click Start recording, speak clearly, then click Stop.";
    }

    startRecordingBtn.addEventListener("click", startRecording);
    stopRecordingBtn.addEventListener("click", stopRecording);
    discardRecordingBtn.addEventListener("click", discardRecording);

    async function submitSourceAudio(prompt) {
      let fileOrBlob = null;
      let filename = "";

      if (sourceMode === "upload") {
        fileOrBlob = audioInput.files[0] || null;
        filename = fileOrBlob ? fileOrBlob.name : "";
      }

      if (sourceMode === "record") {
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
      formData.append("workspaceId", "mock_user_001");
      formData.append("sourceMode", sourceMode);

      console.group("[SyntaxMatrix Clone Voice] ABOUT TO SEND SOURCE AUDIO");
      console.log("endpoint:", "/api/clone-voice/create-and-generate");
      console.log("sourceMode:", sourceMode);
      console.log("audio field:", "audio");
      console.log("filename:", filename);
      console.log("type:", fileOrBlob.type);
      console.log("size:", fileOrBlob.size);
      console.groupEnd();

      return fetch("/api/clone-voice/create-and-generate", {
        method: "POST",
        body: formData
      });
    }

    async function submitSystemVoice(prompt) {
      if (!selectedSystemVoice) {
        alert("Choose a system voice first.");
        return null;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("voiceId", selectedSystemVoice.voiceId);
      formData.append("workspaceId", "mock_user_001");

      console.group("[SyntaxMatrix Clone Voice] ABOUT TO SEND SYSTEM VOICE");
      console.log("endpoint:", "/api/clone-voice/generate-system");
      console.log("voiceId:", selectedSystemVoice.voiceId);
      console.log("promptLength:", prompt.length);
      console.groupEnd();

      return fetch("/api/clone-voice/generate-system", {
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
        const response = sourceMode === "system"
          ? await submitSystemVoice(prompt)
          : await submitSourceAudio(prompt);

        if (!response) return;

        const text = await response.text();
        let data;

        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { raw: text };
        }

        console.log("[SyntaxMatrix Clone Voice] BACKEND RESPONSE:", data);
        resultBox.textContent = JSON.stringify(data, null, 2);

        if (!response.ok || !data.ok) {
          throw new Error(data.message || data.error || "HTTP " + response.status);
        }

        resultTitle.textContent = "Narration ready";

        if (data.assetUrl || data.audioUrl) {
          const url = data.assetUrl || data.audioUrl;
          audioResult.innerHTML = `
            <audio src="${url}" controls></audio>
            <div class="actions">
              <a href="${url}" download>Download</a>
            </div>
          `;
        }
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] REQUEST FAILED:", error);
        resultTitle.textContent = "Narration failed";
        resultBox.textContent = error.message || String(error);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate narration";
      }
    });

    setMode("upload");
  </script>
</body>
</html>
''', encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("System voice support added.")
print()
print("System voice parameter folder:")
print("  workspaces/system/voice_params/")
print()
print("Put existing system .txt voice parameter files there if none are found.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?system=1")
