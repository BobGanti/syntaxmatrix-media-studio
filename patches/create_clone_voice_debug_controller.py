from pathlib import Path
from datetime import datetime
import os
import re
import py_compile

ROOT = Path(".").resolve()
APP = ROOT / "app.py"
CONTROLLERS = ROOT / "controllers"
FRONTEND = ROOT / "frontend"

NEW_CONTROLLER = CONTROLLERS / "clone_voice_controller.py"
VOICE_HTML = FRONTEND / "voice_clone_client.html"
INDEX_HTML = FRONTEND / "index.html"
DEBUG_JS = FRONTEND / "clone_voice_debug_client.js"

required = [APP, CONTROLLERS, FRONTEND]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Run this from the project root. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [APP, NEW_CONTROLLER, VOICE_HTML, INDEX_HTML, DEBUG_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.clone-debug-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

NEW_CONTROLLER.write_text(r'''from __future__ import annotations

import os
from typing import Any

from flask import jsonify, request


def _uploaded_file_size(uploaded_file: Any) -> int | str:
    try:
        pos = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0, os.SEEK_END)
        size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(pos)
        return size
    except Exception as exc:
        return f"unknown: {exc!r}"


def _uploaded_file_first_bytes(uploaded_file: Any, length: int = 16) -> str:
    try:
        pos = uploaded_file.stream.tell()
        first = uploaded_file.stream.read(length)
        uploaded_file.stream.seek(pos)
        return repr(first)
    except Exception as exc:
        return f"unreadable: {exc!r}"


def register_clone_voice_routes(app):
    @app.route("/api/clone-voice/debug-submit", methods=["POST"])
    def clone_voice_debug_submit():
        """Debug-only controller.

        This does not call any provider module.
        This does not create a voice.
        This does not generate narration.

        It only receives the frontend upload + pasted narration text and prints
        exactly what Flask received.
        """

        prompt = (
            request.form.get("prompt")
            or request.form.get("text")
            or request.form.get("narration")
            or ""
        )

        print("\n" + "=" * 100, flush=True)
        print("[SYNTAXMATRIX NEW CLONE VOICE CONTROLLER] RECEIVED FRONTEND REQUEST", flush=True)
        print("PATH:", request.path, flush=True)
        print("METHOD:", request.method, flush=True)
        print("CONTENT_TYPE:", request.content_type, flush=True)
        print("IS_JSON:", request.is_json, flush=True)

        print("\nFORM FIELDS", flush=True)
        print("FORM KEYS:", list(request.form.keys()), flush=True)
        for key in request.form.keys():
            print(f"  {key!r}: {request.form.getlist(key)!r}", flush=True)

        print("\nPROMPT", flush=True)
        print("prompt_length:", len(prompt), flush=True)
        print("prompt_preview:", repr(prompt[:500]), flush=True)

        print("\nMODE FIELDS", flush=True)
        print("MODE:", repr(request.form.get("MODE")), flush=True)
        print("mode:", repr(request.form.get("mode")), flush=True)
        print("sourceMode:", repr(request.form.get("sourceMode")), flush=True)
        print("selectedPreviewVoice:", repr(request.form.get("selectedPreviewVoice")), flush=True)

        print("\nUPLOADED FILES", flush=True)
        print("FILE KEYS:", list(request.files.keys()), flush=True)

        files_summary = []

        if not request.files:
            print("  NO FILES RECEIVED BY FLASK", flush=True)

        for field_name, uploaded_files in request.files.lists():
            print(f"  FIELD {field_name!r}: {len(uploaded_files)} file(s)", flush=True)

            for index, uploaded in enumerate(uploaded_files, start=1):
                size = _uploaded_file_size(uploaded)
                first_bytes = _uploaded_file_first_bytes(uploaded)

                item = {
                    "field": field_name,
                    "index": index,
                    "filename": uploaded.filename,
                    "mimetype": uploaded.mimetype,
                    "content_type": uploaded.content_type,
                    "size_bytes": size,
                    "first_16_bytes": first_bytes,
                }

                files_summary.append(item)

                print(f"    FILE {index}", flush=True)
                print(f"      field: {field_name!r}", flush=True)
                print(f"      filename: {uploaded.filename!r}", flush=True)
                print(f"      mimetype: {uploaded.mimetype!r}", flush=True)
                print(f"      content_type: {uploaded.content_type!r}", flush=True)
                print(f"      size_bytes: {size}", flush=True)
                print(f"      first_16_bytes: {first_bytes}", flush=True)

        print("=" * 100 + "\n", flush=True)

        return jsonify({
            "ok": True,
            "controller": "clone_voice_controller",
            "message": "Debug controller received the frontend request. Check Flask terminal for printed file details.",
            "promptLength": len(prompt),
            "promptPreview": prompt[:500],
            "formKeys": list(request.form.keys()),
            "fileKeys": list(request.files.keys()),
            "files": files_summary,
        })
''', encoding="utf-8")

DEBUG_JS.write_text(r'''(function () {
  const PATCH_NAME = 'clone_voice_debug_client';

  function log(...args) {
    console.log('[SyntaxMatrix CloneVoice Debug]', ...args);
  }

  function activeMode() {
    const active = document.querySelector('[data-source-mode].active');
    return active?.dataset?.sourceMode || 'upload';
  }

  function getPrompt() {
    return String(
      document.querySelector('#voicePrompt')?.value ||
      document.querySelector('textarea[name="prompt"]')?.value ||
      ''
    ).trim();
  }

  function getAudioInput() {
    return (
      document.querySelector('#voiceAudio') ||
      document.querySelector('input[type="file"][name="audio"]') ||
      document.querySelector('input[type="file"]')
    );
  }

  function showResult(data) {
    const title = document.querySelector('#voiceResultTitle');
    const status = document.querySelector('#voiceResultStatus');
    const preview = document.querySelector('#voiceResultPreview');
    const meta = document.querySelector('#voiceResultMeta');

    if (title) title.textContent = 'Debug request received';
    if (status) status.textContent = 'The new clone_voice_controller received the upload. Check the Flask terminal.';

    if (preview) {
      preview.innerHTML = `<pre style="white-space:pre-wrap;max-height:360px;overflow:auto;">${JSON.stringify(data, null, 2)}</pre>`;
    }

    if (meta) {
      meta.innerHTML = `
        <div><dt>Controller</dt><dd>/api/clone-voice/debug-submit</dd></div>
        <div><dt>Files</dt><dd>${Array.isArray(data.files) ? data.files.length : 0}</dd></div>
      `;
    }
  }

  function setBusy(isBusy) {
    const button =
      document.querySelector('#voiceSubmit') ||
      [...document.querySelectorAll('button')].find(btn =>
        /generate narration/i.test(btn.textContent || '')
      );

    if (!button) return;
    button.disabled = isBusy;
    button.textContent = isBusy ? 'Sending to debug controller…' : 'Generate narration';
  }

  function printFrontendDebug(file, prompt) {
    console.group('[SyntaxMatrix CloneVoice Debug] FRONTEND ABOUT TO SEND');
    console.log('endpoint:', '/api/clone-voice/debug-submit');
    console.log('activeMode:', activeMode());
    console.log('promptLength:', prompt.length);
    console.log('MODE:', 'NOT SENT');
    console.log('field name for upload:', 'audio');

    if (file) {
      console.log('file exists:', true);
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    } else {
      console.log('file exists:', false);
    }

    console.groupEnd();
  }

  async function submitToNewDebugController(event) {
    const mode = activeMode();

    if (mode !== 'upload') {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const prompt = getPrompt();
    const input = getAudioInput();
    const file = input?.files?.[0] || null;

    printFrontendDebug(file, prompt);

    if (!prompt) {
      alert('Paste narration text first.');
      return;
    }

    if (!file) {
      alert('Choose an audio file first.');
      return;
    }

    const formData = new FormData();
    formData.append('sourceMode', 'upload');
    formData.append('prompt', prompt);
    formData.append('audio', file, file.name);

    try {
      setBusy(true);

      log('POST /api/clone-voice/debug-submit');
      log('sending file:', {
        field: 'audio',
        filename: file.name,
        type: file.type,
        size: file.size
      });

      const response = await fetch('/api/clone-voice/debug-submit', {
        method: 'POST',
        body: formData
      });

      const text = await response.text();

      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      log('debug controller response:', data);

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

      showResult(data);
    } catch (error) {
      console.error('[SyntaxMatrix CloneVoice Debug] failed:', error);
      alert(error.message || String(error));
    } finally {
      setBusy(false);
    }
  }

  function intercept(event) {
    const isSubmit = event.type === 'submit';
    const clickedGenerate = event.target.closest?.('#voiceSubmit, button[type="submit"]');

    if (!isSubmit && !clickedGenerate) return;

    submitToNewDebugController(event);
  }

  document.addEventListener('submit', intercept, true);
  document.addEventListener('click', intercept, true);

  document.addEventListener('change', event => {
    const input = event.target;

    if (!input || input.type !== 'file') return;

    const file = input.files?.[0];

    console.group('[SyntaxMatrix CloneVoice Debug] FILE CHOSEN');
    console.log('input id:', input.id);
    console.log('input name:', input.name);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();
  }, true);

  window.__debugCloneVoiceUpload = function () {
    const input = getAudioInput();
    const file = input?.files?.[0] || null;
    const prompt = getPrompt();

    printFrontendDebug(file, prompt);

    return {
      activeMode: activeMode(),
      promptLength: prompt.length,
      fileExists: Boolean(file),
      filename: file?.name || null,
      type: file?.type || null,
      size: file?.size || null,
      endpoint: '/api/clone-voice/debug-submit'
    };
  };

  console.log(`[${PATCH_NAME}] active. Upload audio is now routed to the brand-new clone_voice_controller only.`);
})();
''', encoding="utf-8")


def inject_script(path: Path) -> None:
    if not path.exists():
        return

    html = path.read_text(encoding="utf-8")

    html = re.sub(
        r'\n?\s*<script[^>]+src=["\']/?clone_voice_debug_client\.js(?:\?[^"\']*)?["\'][^>]*></script>\s*',
        "\n",
        html,
        flags=re.I,
    )

    script = f'<script src="/clone_voice_debug_client.js?v={stamp}" defer></script>'

    if re.search(r"</body>", html, flags=re.I):
        html = re.sub(r"</body>", script + "\n</body>", html, count=1, flags=re.I)
    else:
        html = html.rstrip() + "\n" + script + "\n"

    path.write_text(html, encoding="utf-8")
    print("Injected debug client into:", path)


inject_script(VOICE_HTML)
inject_script(INDEX_HTML)

app_text = APP.read_text(encoding="utf-8")

if "from controllers.clone_voice_controller import register_clone_voice_routes" not in app_text:
    import_line = "from controllers.clone_voice_controller import register_clone_voice_routes\n"

    # Insert after other imports if possible.
    lines = app_text.splitlines(keepends=True)
    insert_index = 0

    for i, line in enumerate(lines):
      stripped = line.strip()
      if stripped.startswith("import ") or stripped.startswith("from "):
          insert_index = i + 1

    lines.insert(insert_index, import_line)
    app_text = "".join(lines)

if "register_clone_voice_routes(app)" not in app_text:
    register_line = "\n# SyntaxMatrix new clone voice debug controller\nregister_clone_voice_routes(app)\n"

    # Prefer to register before app.run / if __name__.
    marker = '\nif __name__ == "__main__":'
    marker_alt = "\nif __name__ == '__main__':"

    if marker in app_text:
        app_text = app_text.replace(marker, register_line + marker, 1)
    elif marker_alt in app_text:
        app_text = app_text.replace(marker_alt, register_line + marker_alt, 1)
    else:
        app_text += register_line

APP.write_text(app_text, encoding="utf-8")

py_compile.compile(str(NEW_CONTROLLER), doraise=True)
py_compile.compile(str(APP), doraise=True)

print()
print("NEW clone_voice_controller debug route installed.")
print()
print("New endpoint:")
print("  POST /api/clone-voice/debug-submit")
print()
print("Frontend upload audio now routes to the new controller.")
print("It does not use the old voice_clone_controller.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/voice-clone?v=clone-debug")
print()
print("Then upload an audio file, paste text, click Generate narration.")
print("Check Flask terminal for the printed uploaded file.")