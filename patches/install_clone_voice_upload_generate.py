from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()
CONTROLLERS = ROOT / "controllers"
FRONTEND = ROOT / "frontend"
VIEWS = ROOT / "views"

CONTROLLER = CONTROLLERS / "clone_voice_controller.py"
HTML = FRONTEND / "clone_voice_debug_print.html"
VIEW = VIEWS / "clone_voice_view.py"

if not CONTROLLERS.exists() or not FRONTEND.exists():
    print("ERROR: Run from project root where controllers/ and frontend/ exist.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CONTROLLER, HTML, VIEW]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.clone-upload-generate-{stamp}")
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


def _safe_id(prefix: str = "smxvoice") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}"


def _safe_source_filename(original_name: str) -> str:
    safe = secure_filename(original_name or "source_audio.wav")
    stem = pathlib.Path(safe).stem or "source_audio"
    ext = pathlib.Path(safe).suffix or ".wav"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"source_{stamp}_{stem}{ext}"


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

    # Important:
    # Do NOT pass uploaded filename or client label as preferred_name.
    # The working local script calls create_voice(source_path), which uses the safe default.
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

    print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Generating narration using saved voice parameter", flush=True)

    return voice_feature.clone_voice(
        api_key=api_key,
        model=DEFAULT_MODEL,
        voice=voice_parameter,
        text=prompt,
        stream=False,
    )


def register_clone_voice_routes(app):
    if "clone_voice_create_and_generate" in app.view_functions:
        return

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
        output_dir = workspace_root / GENERATED_AUDIO_DIRNAME

        tmp_source_path = tmp_dir / _safe_source_filename(audio_file.filename)
        voice_id = _safe_id("smxvoice")
        param_path = params_dir / f"{voice_id}.txt"
        output_filename = f"narration_{datetime.now().strftime('%Y%m%d%H%M%S')}.wav"
        output_path = output_dir / output_filename

        try:
            audio_file.save(tmp_source_path)
            print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved temporary source audio:", tmp_source_path, flush=True)

            audio_mime_type = audio_file.mimetype or mimetypes.guess_type(tmp_source_path.name)[0] or "audio/mpeg"

            voice_parameter = _create_voice_param_from_source(tmp_source_path, audio_mime_type)
            param_path.write_text(voice_parameter, encoding="utf-8")
            print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved private voice parameter:", param_path, flush=True)

            response = _generate_narration(voice_parameter, prompt)
            audio_url = _response_audio_url(response)

            if not audio_url:
                return jsonify({
                    "ok": False,
                    "message": "Narration response did not include an audio URL",
                    "voiceId": voice_id,
                    "voiceParamPath": str(param_path.relative_to(ROOT)).replace(os.sep, "/"),
                    "raw": str(response),
                }), 502

            _download_audio(audio_url, output_path)
            print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER] Saved generated narration:", output_path, flush=True)

            asset_url = f"/media/workspaces/{workspace_id}/generated_audio/{output_filename}"

            return jsonify({
                "ok": True,
                "controller": "clone_voice_controller",
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

    @app.route("/media/workspaces/<workspace_id>/generated_audio/<path:filename>", methods=["GET"])
    def clone_voice_workspace_generated_audio(workspace_id: str, filename: str):
        safe_workspace = re.sub(r"[^a-zA-Z0-9_-]+", "_", workspace_id)
        directory = WORKSPACES_DIR / safe_workspace / GENERATED_AUDIO_DIRNAME
        return send_from_directory(directory, filename)
''', encoding="utf-8")

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #071017;
      color: #e8f1f8;
      padding: 32px;
    }
    main {
      max-width: 880px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }
    section {
      border: 1px solid #33414c;
      border-radius: 16px;
      padding: 20px;
      background: #111b24;
    }
    label {
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
      font-weight: 700;
    }
    input, textarea, button {
      font: inherit;
    }
    input[type="file"], textarea {
      border: 1px solid #465662;
      border-radius: 10px;
      padding: 12px;
      background: #202b35;
      color: #fff;
    }
    textarea {
      min-height: 180px;
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
    audio {
      width: 100%;
      margin-top: 12px;
    }
    pre {
      white-space: pre-wrap;
      overflow: auto;
      max-height: 360px;
      background: #02070b;
      border: 1px solid #33414c;
      border-radius: 12px;
      padding: 16px;
    }
    .note {
      color: #9db2c5;
      line-height: 1.5;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .actions a {
      color: #06130f;
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      padding: 12px 18px;
      border-radius: 999px;
      font-weight: 900;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p>SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p class="note">
        Upload audio and paste narration text. The controller creates a private voice parameter, deletes the raw source audio, then generates narration.
      </p>
    </header>

    <section>
      <form id="cloneVoiceForm">
        <label>
          Upload audio file
          <input id="audioInput" name="audio" type="file" accept="audio/*" required>
        </label>

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
    const audioInput = document.querySelector("#audioInput");
    const promptInput = document.querySelector("#promptInput");
    const submitBtn = document.querySelector("#submitBtn");
    const resultTitle = document.querySelector("#resultTitle");
    const audioResult = document.querySelector("#audioResult");
    const resultBox = document.querySelector("#resultBox");

    audioInput.addEventListener("change", () => {
      const file = audioInput.files[0] || null;
      console.group("[SyntaxMatrix Clone Voice] FILE SELECTED");
      console.log("field name:", "audio");
      console.log("file exists:", Boolean(file));
      if (file) {
        console.log("filename:", file.name);
        console.log("type:", file.type);
        console.log("size:", file.size);
      }
      console.groupEnd();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const file = audioInput.files[0] || null;
      const prompt = promptInput.value.trim();

      console.group("[SyntaxMatrix Clone Voice] ABOUT TO SEND");
      console.log("endpoint:", "/api/clone-voice/create-and-generate");
      console.log("prompt field:", "prompt");
      console.log("prompt length:", prompt.length);
      console.log("audio field:", "audio");
      console.log("file exists:", Boolean(file));
      if (file) {
        console.log("filename:", file.name);
        console.log("type:", file.type);
        console.log("size:", file.size);
      }
      console.groupEnd();

      if (!file) {
        alert("Choose an audio file first.");
        return;
      }

      if (!prompt) {
        alert("Paste narration text first.");
        return;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("audio", file, file.name);
      formData.append("workspaceId", "mock_user_001");

      submitBtn.disabled = true;
      submitBtn.textContent = "Generating...";
      resultTitle.textContent = "Generating narration";
      audioResult.innerHTML = "";
      resultBox.textContent = "Working... Check Flask terminal for upload and workspace logs.";

      try {
        const response = await fetch("/api/clone-voice/create-and-generate", {
          method: "POST",
          body: formData
        });

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
  </script>
</body>
</html>
''', encoding="utf-8")

VIEWS.mkdir(exist_ok=True)

VIEW.write_text(r'''from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend"


@bp.get("/tasks/clone-voice")
def clone_voice_page():
    return send_from_directory(_frontend_dir(), "clone_voice_debug_print.html")


@bp.get("/tasks/voice-clone")
def old_voice_clone_redirect():
    return redirect("/tasks/clone-voice", code=302)
''', encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)
py_compile.compile(str(VIEW), doraise=True)

print()
print("Clone Voice upload-to-voice-param-to-narration flow installed.")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?generate=1")
print()
print("Workspace used:")
print("  workspaces/mock_user_001/")
print()
print("Expected saved voice parameter:")
print("  workspaces/mock_user_001/voice_params/*.txt")
print()
print("Temporary raw upload is deleted after processing.")
print()
print("Restart Flask:")
print("  python app.py")
