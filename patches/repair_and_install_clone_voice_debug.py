from pathlib import Path
from datetime import datetime
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

if not APP.exists() or not CONTROLLERS.exists() or not FRONTEND.exists():
    print("ERROR: Run this from the project root where app.py, controllers/, and frontend/ exist.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [APP, NEW_CONTROLLER, VOICE_HTML, INDEX_HTML, DEBUG_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.clone-debug-repair-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

# -------------------------------------------------------------------
# 1. Create brand-new debug-only controller.
# -------------------------------------------------------------------
NEW_CONTROLLER.write_text(r'''from __future__ import annotations

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
    @app.route("/api/clone-voice/debug-submit", methods=["POST"])
    def clone_voice_debug_submit():
        # EXACT CONTRACT:
        # frontend sends:
        #   prompt: pasted narration text
        #   audio: uploaded audio file
        prompt = request.form.get("prompt", "")

        print("\n" + "=" * 100, flush=True)
        print("[SYNTAXMATRIX CLONE VOICE DEBUG CONTROLLER]", flush=True)
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

        if not request.files:
            print("  NO FILES RECEIVED", flush=True)

        for field_name, uploaded_files in request.files.lists():
            print(f"  FIELD {field_name!r}: {len(uploaded_files)} file(s)", flush=True)

            for index, uploaded in enumerate(uploaded_files, start=1):
                size = _file_size(uploaded)
                first = _first_bytes(uploaded)

                print(f"    FILE {index}", flush=True)
                print(f"      field: {field_name!r}", flush=True)
                print(f"      filename: {uploaded.filename!r}", flush=True)
                print(f"      mimetype: {uploaded.mimetype!r}", flush=True)
                print(f"      content_type: {uploaded.content_type!r}", flush=True)
                print(f"      size_bytes: {size}", flush=True)
                print(f"      first_16_bytes: {first}", flush=True)

                files_summary.append({
                    "field": field_name,
                    "filename": uploaded.filename,
                    "mimetype": uploaded.mimetype,
                    "content_type": uploaded.content_type,
                    "size_bytes": size,
                    "first_16_bytes": first,
                })

        print("=" * 100 + "\n", flush=True)

        return jsonify({
            "ok": True,
            "controller": "clone_voice_controller",
            "message": "Received by brand-new debug controller. Check Flask terminal.",
            "promptLength": len(prompt),
            "promptPreview": prompt[:500],
            "formKeys": list(request.form.keys()),
            "fileKeys": list(request.files.keys()),
            "files": files_summary,
        })
''', encoding="utf-8")

py_compile.compile(str(NEW_CONTROLLER), doraise=True)

# -------------------------------------------------------------------
# 2. Create frontend debug client. Upload tab only.
# -------------------------------------------------------------------
DEBUG_JS.write_text(r'''(function () {
  const PATCH_NAME = 'clone_voice_debug_client_v2';

  function activeMode() {
    const active = document.querySelector('[data-source-mode].active');
    return active?.dataset?.sourceMode || 'upload';
  }

  function getPrompt() {
    return String(document.querySelector('#voicePrompt')?.value || '').trim();
  }

  function getAudioFile() {
    const input =
      document.querySelector('#voiceAudio') ||
      document.querySelector('input[type="file"][name="audio"]') ||
      document.querySelector('input[type="file"]');

    return input?.files?.[0] || null;
  }

  function setBusy(isBusy) {
    const button =
      document.querySelector('#voiceSubmit') ||
      [...document.querySelectorAll('button')].find(btn =>
        /generate narration/i.test(btn.textContent || '')
      );

    if (!button) return;
    button.disabled = isBusy;
    button.textContent = isBusy ? 'Sending debug request…' : 'Generate narration';
  }

  function renderDebugResponse(data) {
    const title = document.querySelector('#voiceResultTitle');
    const status = document.querySelector('#voiceResultStatus');
    const preview = document.querySelector('#voiceResultPreview');
    const meta = document.querySelector('#voiceResultMeta');

    if (title) title.textContent = 'Debug request received';
    if (status) status.textContent = 'The new clone_voice_controller received the upload. Check Flask terminal.';

    if (preview) {
      preview.innerHTML = `<pre style="white-space:pre-wrap;max-height:360px;overflow:auto;">${JSON.stringify(data, null, 2)}</pre>`;
    }

    if (meta) {
      meta.innerHTML = `
        <div><dt>Controller</dt><dd>/api/clone-voice/debug-submit</dd></div>
        <div><dt>File keys</dt><dd>${Array.isArray(data.fileKeys) ? data.fileKeys.join(', ') : ''}</dd></div>
      `;
    }
  }

  async function sendUploadToDebugController(event) {
    if (activeMode() !== 'upload') return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const prompt = getPrompt();
    const file = getAudioFile();

    console.group('[SyntaxMatrix Clone Voice Debug] FRONTEND SENDING');
    console.log('endpoint:', '/api/clone-voice/debug-submit');
    console.log('prompt field:', 'prompt');
    console.log('promptLength:', prompt.length);
    console.log('audio field:', 'audio');
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();

    if (!prompt) {
      alert('Paste narration text first.');
      return;
    }

    if (!file) {
      alert('Choose an audio file first.');
      return;
    }

    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('audio', file, file.name);

    try {
      setBusy(true);

      const response = await fetch('/api/clone-voice/debug-submit', {
        method: 'POST',
        body: formData,
      });

      const text = await response.text();
      let data;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      console.log('[SyntaxMatrix Clone Voice Debug] BACKEND RESPONSE:', data);

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

      renderDebugResponse(data);
    } catch (error) {
      console.error('[SyntaxMatrix Clone Voice Debug] FAILED:', error);
      alert(error.message || String(error));
    } finally {
      setBusy(false);
    }
  }

  function intercept(event) {
    const isSubmit = event.type === 'submit' && event.target?.id === 'voiceCloneForm';
    const clickedGenerate = Boolean(event.target.closest?.('#voiceSubmit, button[type="submit"]'));

    if (!isSubmit && !clickedGenerate) return;

    sendUploadToDebugController(event);
  }

  document.addEventListener('submit', intercept, true);
  document.addEventListener('click', intercept, true);

  document.addEventListener('change', event => {
    const input = event.target;
    if (!input || input.type !== 'file') return;

    const file = input.files?.[0] || null;

    console.group('[SyntaxMatrix Clone Voice Debug] FILE CHOSEN');
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
    const file = getAudioFile();
    const prompt = getPrompt();

    console.group('[SyntaxMatrix Clone Voice Debug] MANUAL CHECK');
    console.log('activeMode:', activeMode());
    console.log('promptLength:', prompt.length);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();

    return {
      activeMode: activeMode(),
      promptLength: prompt.length,
      fileExists: Boolean(file),
      filename: file?.name || null,
      type: file?.type || null,
      size: file?.size || null,
      endpoint: '/api/clone-voice/debug-submit',
    };
  };

  console.log(`[${PATCH_NAME}] active. Upload audio is routed to brand-new debug controller.`);
})();
''', encoding="utf-8")

# -------------------------------------------------------------------
# 3. Inject debug script into frontend pages.
# -------------------------------------------------------------------
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
    print("Injected:", path)

inject_script(VOICE_HTML)
inject_script(INDEX_HTML)

# -------------------------------------------------------------------
# 4. Repair app.py from previous bad insertion and register new controller safely.
# -------------------------------------------------------------------
app_text = APP.read_text(encoding="utf-8")

# Remove any previous broken inserted lines wherever they landed.
app_text = re.sub(
    r'^\s*from controllers\.clone_voice_controller import register_clone_voice_routes\s*\n',
    '',
    app_text,
    flags=re.M,
)

app_text = re.sub(
    r'^\s*# SyntaxMatrix new clone voice debug controller\s*\n\s*register_clone_voice_routes\(app\)\s*\n',
    '',
    app_text,
    flags=re.M,
)

app_text = re.sub(
    r'^\s*register_clone_voice_routes\(app\)\s*\n',
    '',
    app_text,
    flags=re.M,
)

register_block = r'''
# SMX_CLONE_VOICE_DEBUG_CONTROLLER_START
from controllers.clone_voice_controller import register_clone_voice_routes as _smx_register_clone_voice_routes
_smx_register_clone_voice_routes(app)
# SMX_CLONE_VOICE_DEBUG_CONTROLLER_END

'''

# Remove old block if present.
app_text = re.sub(
    r'\n?# SMX_CLONE_VOICE_DEBUG_CONTROLLER_START[\s\S]*?# SMX_CLONE_VOICE_DEBUG_CONTROLLER_END\n?',
    '\n',
    app_text,
)

# Insert before Flask app.run guard.
marker1 = '\nif __name__ == "__main__":'
marker2 = "\nif __name__ == '__main__':"

if marker1 in app_text:
    app_text = app_text.replace(marker1, "\n" + register_block + marker1, 1)
elif marker2 in app_text:
    app_text = app_text.replace(marker2, "\n" + register_block + marker2, 1)
else:
    app_text = app_text.rstrip() + "\n\n" + register_block

APP.write_text(app_text, encoding="utf-8")

py_compile.compile(str(APP), doraise=True)

print()
print("REPAIR COMPLETE.")
print("Brand-new clone_voice_controller is installed.")
print()
print("Endpoint:")
print("  POST /api/clone-voice/debug-submit")
print()
print("Contract:")
print("  request.form['prompt']")
print("  request.files['audio']")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/voice-clone?v=clone-debug-v2")
print()
print("Upload audio, paste text, click Generate narration.")
print("The Flask terminal must print the uploaded file details.")
