from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()
APP = ROOT / "app.py"
FRONTEND = ROOT / "frontend"
CONTROLLERS = ROOT / "controllers"
VIEWS = ROOT / "views"

HTML = FRONTEND / "clone_voice_debug_print.html"
CONTROLLER = CONTROLLERS / "clone_voice_controller.py"
VIEW = VIEWS / "clone_voice_view.py"
VIEWS_INIT = VIEWS / "__init__.py"

if not APP.exists() or not FRONTEND.exists() or not CONTROLLERS.exists():
    print("ERROR: Run from project root where app.py, frontend/, controllers/ exist.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
VIEWS.mkdir(exist_ok=True)

for path in [APP, HTML, CONTROLLER, VIEW, VIEWS_INIT]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.print-only-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice Upload Print</title>
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
      max-width: 850px;
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
    pre {
      white-space: pre-wrap;
      overflow: auto;
      max-height: 420px;
      background: #02070b;
      border: 1px solid #33414c;
      border-radius: 12px;
      padding: 16px;
    }
    .note {
      color: #9db2c5;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p>SyntaxMatrix Debug</p>
      <h1>Clone Voice: print uploaded file only</h1>
      <p class="note">
        This page does not call the old controller. It does not create voice identity.
        It only sends <strong>prompt</strong> and <strong>audio</strong> to the new print-only controller.
      </p>
    </header>

    <section>
      <form id="cloneVoicePrintForm">
        <label>
          Upload audio file
          <input id="audioInput" name="audio" type="file" accept="audio/*" required>
        </label>

        <label>
          Prompt
          <textarea id="promptInput" name="prompt" required placeholder="Paste narration text here"></textarea>
        </label>

        <button id="submitBtn" type="submit">Send and print upload</button>
      </form>
    </section>

    <section>
      <h2>Response</h2>
      <pre id="resultBox">No request sent yet.</pre>
    </section>
  </main>

  <script>
    const form = document.querySelector("#cloneVoicePrintForm");
    const audioInput = document.querySelector("#audioInput");
    const promptInput = document.querySelector("#promptInput");
    const submitBtn = document.querySelector("#submitBtn");
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
      console.log("endpoint:", "/api/clone-voice/print");
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
        alert("Paste prompt first.");
        return;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("audio", file, file.name);

      submitBtn.disabled = true;
      submitBtn.textContent = "Sending...";
      resultBox.textContent = "Sending to /api/clone-voice/print ...";

      try {
        const response = await fetch("/api/clone-voice/print", {
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

        if (!response.ok) {
          throw new Error(data.message || data.error || "HTTP " + response.status);
        }
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] REQUEST FAILED:", error);
        resultBox.textContent = error.message || String(error);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Send and print upload";
      }
    });
  </script>
</body>
</html>
''', encoding="utf-8")

CONTROLLER.write_text(r'''from __future__ import annotations

import os
from typing import Any

from flask import jsonify, request


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


def register_clone_voice_routes(app):
    if "clone_voice_print_upload" in app.view_functions:
        return

    @app.route("/api/clone-voice/print", methods=["POST"], endpoint="clone_voice_print_upload")
    def clone_voice_print_upload():
        prompt = request.form.get("prompt", "")
        audio_file = request.files.get("audio")

        print("\n" + "=" * 100, flush=True)
        print("[SYNTAXMATRIX CLONE_VOICE_CONTROLLER PRINT ONLY]", flush=True)
        print("PATH:", request.path, flush=True)
        print("METHOD:", request.method, flush=True)
        print("CONTENT_TYPE:", request.content_type, flush=True)

        print("\nFORM", flush=True)
        print("FORM KEYS:", list(request.form.keys()), flush=True)
        print("prompt_length:", len(prompt), flush=True)
        print("prompt_preview:", repr(prompt[:500]), flush=True)
        for key in request.form.keys():
            print(f"  form[{key!r}] = {request.form.getlist(key)!r}", flush=True)

        print("\nFILES", flush=True)
        print("FILE KEYS:", list(request.files.keys()), flush=True)

        files_summary = []

        if audio_file is None:
            print("  request.files.get('audio') = None", flush=True)
        else:
            size = _file_size(audio_file)
            first = _first_bytes(audio_file)

            print("  request.files.get('audio') FOUND", flush=True)
            print("    field: 'audio'", flush=True)
            print(f"    filename: {audio_file.filename!r}", flush=True)
            print(f"    mimetype: {audio_file.mimetype!r}", flush=True)
            print(f"    content_type: {audio_file.content_type!r}", flush=True)
            print(f"    size_bytes: {size}", flush=True)
            print(f"    first_16_bytes: {first}", flush=True)

            files_summary.append({
                "field": "audio",
                "filename": audio_file.filename,
                "mimetype": audio_file.mimetype,
                "content_type": audio_file.content_type,
                "size_bytes": size,
                "first_16_bytes": first,
            })

        print("=" * 100 + "\n", flush=True)

        return jsonify({
            "ok": True,
            "controller": "clone_voice_controller.print_only",
            "promptLength": len(prompt),
            "promptPreview": prompt[:500],
            "formKeys": list(request.form.keys()),
            "fileKeys": list(request.files.keys()),
            "audioReceived": audio_file is not None,
            "files": files_summary,
        })
''', encoding="utf-8")

VIEW.write_text(r'''from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend"


@bp.get("/tasks/clone-voice")
def clone_voice_print_page():
    return send_from_directory(_frontend_dir(), "clone_voice_debug_print.html")


@bp.get("/tasks/voice-clone")
def old_voice_clone_redirect():
    return redirect("/tasks/clone-voice", code=302)
''', encoding="utf-8")

VIEWS_INIT.write_text(r'''from __future__ import annotations


def register_views(app):
    from .clone_voice_view import bp as clone_voice_bp

    if "clone_voice_view" not in app.blueprints:
        app.register_blueprint(clone_voice_bp)
''', encoding="utf-8")

app_text = APP.read_text(encoding="utf-8")

app_text = re.sub(
    r'\n?# SMX_CLONE_VOICE_PRINT_ONLY_START[\s\S]*?# SMX_CLONE_VOICE_PRINT_ONLY_END\n?',
    '\n',
    app_text,
)

block = r'''
# SMX_CLONE_VOICE_PRINT_ONLY_START
from views import register_views as _smx_register_views
_smx_register_views(app)

from controllers.clone_voice_controller import register_clone_voice_routes as _smx_register_clone_voice_routes
_smx_register_clone_voice_routes(app)
# SMX_CLONE_VOICE_PRINT_ONLY_END

'''

marker1 = '\nif __name__ == "__main__":'
marker2 = "\nif __name__ == '__main__':"

if marker1 in app_text:
    app_text = app_text.replace(marker1, "\n" + block + marker1, 1)
elif marker2 in app_text:
    app_text = app_text.replace(marker2, "\n" + block + marker2, 1)
else:
    app_text = app_text.rstrip() + "\n\n" + block

APP.write_text(app_text, encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)
py_compile.compile(str(VIEW), doraise=True)
py_compile.compile(str(VIEWS_INIT), doraise=True)
py_compile.compile(str(APP), doraise=True)

print()
print("PRINT-ONLY clone voice page installed.")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?printonly=1")
print()
print("Backend endpoint:")
print("  POST /api/clone-voice/print")
print()
print("It sends exactly:")
print("  request.form['prompt']")
print("  request.files['audio']")
print()
print("Restart Flask:")
print("  python app.py")
