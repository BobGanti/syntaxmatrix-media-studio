from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
APP = ROOT / "app.py"
FRONTEND = ROOT / "frontend"
VOICE_HTML = FRONTEND / "voice_clone_client.html"
INDEX_HTML = FRONTEND / "index.html"
DEBUG_JS = FRONTEND / "voice_payload_debug.js"

if not APP.exists():
    print("ERROR: app.py not found. Run this from the project root.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [APP, VOICE_HTML, INDEX_HTML, DEBUG_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.voice-debug-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

# -----------------------------
# Frontend debug script
# -----------------------------
DEBUG_JS.write_text(r'''(function () {
  const PATCH_NAME = 'SyntaxMatrix voice payload debug';

  function activeMode() {
    const active = document.querySelector('[data-source-mode].active');
    return active?.dataset?.sourceMode || 'unknown';
  }

  function selectedFiles() {
    return [...document.querySelectorAll('input[type="file"]')].map(input => ({
      id: input.id || '',
      name: input.name || '',
      fileCount: input.files ? input.files.length : 0,
      files: input.files ? [...input.files].map(file => ({
        filename: file.name,
        type: file.type,
        size: file.size
      })) : []
    }));
  }

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form || form.id !== 'voiceCloneForm') return;

    const prompt = document.querySelector('#voicePrompt')?.value || '';
    const voiceName = document.querySelector('#voiceName')?.value || '';
    const model = document.querySelector('#voiceModel')?.value || '';

    console.group('[SyntaxMatrix] Voice form submit debug');
    console.log('sourceMode:', activeMode());
    console.log('promptLength:', prompt.length);
    console.log('voiceName hidden value:', voiceName);
    console.log('model hidden value:', model);
    console.table(selectedFiles());
    console.groupEnd();
  }, true);

  document.addEventListener('change', event => {
    const input = event.target;
    if (!input || input.type !== 'file') return;

    console.group('[SyntaxMatrix] Voice file selected');
    console.log('input id:', input.id);
    console.log('input name:', input.name);
    console.table([...input.files].map(file => ({
      filename: file.name,
      type: file.type,
      size: file.size
    })));
    console.groupEnd();
  }, true);

  console.log(`[${PATCH_NAME}] active`);
})();
''', encoding="utf-8")


def inject_script(path: Path) -> None:
    if not path.exists():
        return

    html = path.read_text(encoding="utf-8")

    html = re.sub(
        r'\n?\s*<script[^>]+src=["\']/?voice_payload_debug\.js(?:\?[^"\']*)?["\'][^>]*></script>\s*',
        "\n",
        html,
        flags=re.I,
    )

    script = f'<script src="/voice_payload_debug.js?v={stamp}" defer></script>'

    if re.search(r"</body>", html, flags=re.I):
        html = re.sub(r"</body>", script + "\n</body>", html, count=1, flags=re.I)
    else:
        html = html.rstrip() + "\n" + script + "\n"

    path.write_text(html, encoding="utf-8")
    print("Injected debug JS into:", path)


inject_script(VOICE_HTML)
inject_script(INDEX_HTML)

# -----------------------------
# Backend request debug
# -----------------------------
app_text = APP.read_text(encoding="utf-8")

debug_block = r'''
# SMX_VOICE_PAYLOAD_DEBUG_START
@app.before_request
def _smx_debug_voice_payload():
    """Print exactly what the Voice Clone frontend sends to Flask."""
    try:
        debug_paths = {
            "/api/media/voice-clone",
            "/api/voice-clone/profile",
            "/api/voice-clone/previews",
            "/api/voice-clone/client-profiles",
        }

        if request.path not in debug_paths:
            return None

        print("\n" + "=" * 90, flush=True)
        print("[SyntaxMatrix Voice Debug] INCOMING REQUEST", flush=True)
        print("path:", request.path, flush=True)
        print("method:", request.method, flush=True)
        print("content_type:", request.content_type, flush=True)
        print("is_json:", request.is_json, flush=True)

        if request.is_json:
            data = request.get_json(silent=True) or {}
            print("json_keys:", list(data.keys()), flush=True)
            for key, value in data.items():
                safe_value = str(value)
                if len(safe_value) > 250:
                    safe_value = safe_value[:250] + "...[truncated]"
                print(f"json[{key!r}] = {safe_value!r}", flush=True)
        else:
            print("form_keys:", list(request.form.keys()), flush=True)
            for key in request.form:
                values = request.form.getlist(key)
                safe_values = []
                for value in values:
                    safe = str(value)
                    if len(safe) > 250:
                        safe = safe[:250] + "...[truncated]"
                    safe_values.append(safe)
                print(f"form[{key!r}] = {safe_values!r}", flush=True)

            print("file_keys:", list(request.files.keys()), flush=True)
            for key, files in request.files.lists():
                print(f"files field {key!r}: count={len(files)}", flush=True)

                for index, file_obj in enumerate(files):
                    size = "unknown"
                    try:
                        pos = file_obj.stream.tell()
                        file_obj.stream.seek(0, 2)
                        size = file_obj.stream.tell()
                        file_obj.stream.seek(pos)
                    except Exception:
                        pass

                    print(
                        f"  file[{index}] field={key!r} "
                        f"filename={file_obj.filename!r} "
                        f"mimetype={file_obj.mimetype!r} "
                        f"size={size}",
                        flush=True,
                    )

        mode_value = (
            request.form.get("MODE")
            or request.form.get("mode")
            or request.form.get("sourceMode")
            or None
        )
        print("resolved frontend mode:", repr(mode_value), flush=True)
        print("=" * 90 + "\n", flush=True)

    except Exception as exc:
        print("[SyntaxMatrix Voice Debug] FAILED:", repr(exc), flush=True)

    return None
# SMX_VOICE_PAYLOAD_DEBUG_END
'''

if "SMX_VOICE_PAYLOAD_DEBUG_START" not in app_text:
    marker = 'app.config["MAX_CONTENT_LENGTH"]'
    pos = app_text.find(marker)

    if pos == -1:
        raise SystemExit("Could not find Flask app config section in app.py.")

    line_end = app_text.find("\n", pos)
    app_text = app_text[:line_end + 1] + "\n" + debug_block + "\n" + app_text[line_end + 1:]

    APP.write_text(app_text, encoding="utf-8")
    print("Injected backend voice payload debug into app.py")
else:
    print("Backend debug block already exists in app.py")

print()
print("Voice payload debug patch complete.")
print("Restart Flask with: python app.py")
print("Then open: http://127.0.0.1:5055/tasks/voice-clone?v=debug")
print()
print("When you choose an audio file and click Generate narration, check the Flask terminal.")
print("We need to see file_keys and whether the audio file arrives under field name 'audio'.")