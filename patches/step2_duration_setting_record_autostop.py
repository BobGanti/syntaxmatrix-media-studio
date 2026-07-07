from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()

CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
SERVICES = ROOT / "services"
AUDIO_POLICY = SERVICES / "clone_voice_audio_policy.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [CONTROLLER, HTML, JS, SERVICES]

missing = [str(path) for path in required if not path.exists()]
if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CONTROLLER, AUDIO_POLICY, HTML, JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step2-duration-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

AUDIO_POLICY.write_text(r'''from __future__ import annotations

import json
import os
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "clone_voice_settings.json"

DEFAULT_MAX_VOICE_SOURCE_SECONDS = 35


def _safe_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def get_max_voice_source_seconds() -> int:
    """Admin-set maximum voice source/preview duration.

    Current priority:
      1. config/clone_voice_settings.json
      2. environment variable CLONE_VOICE_MAX_SOURCE_SECONDS
      3. default 35
    """
    env_value = os.getenv("CLONE_VOICE_MAX_SOURCE_SECONDS")

    if env_value:
        return _safe_int(env_value, DEFAULT_MAX_VOICE_SOURCE_SECONDS)

    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _safe_int(data.get("max_voice_source_seconds"), DEFAULT_MAX_VOICE_SOURCE_SECONDS)
        except Exception as exc:
            print("[clone_voice_audio_policy] Could not read config:", repr(exc), flush=True)

    return DEFAULT_MAX_VOICE_SOURCE_SECONDS


def ensure_default_settings_file() -> pathlib.Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "max_voice_source_seconds": DEFAULT_MAX_VOICE_SOURCE_SECONDS
                },
                indent=2
            ),
            encoding="utf-8",
        )

    return CONFIG_PATH


def settings_payload() -> dict:
    path = ensure_default_settings_file()

    return {
        "maxVoiceSourceSeconds": get_max_voice_source_seconds(),
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
    }
''', encoding="utf-8")

controller_text = CONTROLLER.read_text(encoding="utf-8")

if "from services.clone_voice_audio_policy import settings_payload" not in controller_text:
    anchor = "from flask import jsonify, request, send_from_directory\n"
    if anchor not in controller_text:
        print("ERROR: Could not find Flask import anchor in controller.")
        raise SystemExit(1)

    controller_text = controller_text.replace(
        anchor,
        anchor + "from services.clone_voice_audio_policy import settings_payload\n",
        1,
    )

if 'endpoint="clone_voice_settings"' not in controller_text:
    anchor = "def register_clone_voice_routes(app):\n"
    if anchor not in controller_text:
        print("ERROR: Could not find register_clone_voice_routes in controller.")
        raise SystemExit(1)

    settings_route = '''def register_clone_voice_routes(app):
    if "clone_voice_settings" not in app.view_functions:
        @app.get("/api/clone-voice/settings", endpoint="clone_voice_settings")
        def clone_voice_settings():
            payload = settings_payload()
            print("[clone_voice_controller] Settings:", payload, flush=True)
            return jsonify({"ok": True, **payload})

'''

    controller_text = controller_text.replace(anchor, settings_route, 1)

CONTROLLER.write_text(controller_text, encoding="utf-8")

html_text = HTML.read_text(encoding="utf-8")

html_text = html_text.replace(
    '<script src="/clone_voice/client.js?v=stable-naming-1"></script>',
    '<script src="/clone_voice/client.js?v=duration-step2"></script>',
)

HTML.write_text(html_text, encoding="utf-8")

js_text = JS.read_text(encoding="utf-8")

if "let maxVoiceSourceSeconds = 35;" not in js_text:
    js_text = js_text.replace(
        'const WORKSPACE_ID = "mock_user_001";',
        'const WORKSPACE_ID = "mock_user_001";\n\n  let maxVoiceSourceSeconds = 35;',
        1,
    )

if "let recordingAutoStopTimer = null;" not in js_text:
    js_text = js_text.replace(
        'let recordedFilename = "";',
        'let recordedFilename = "";\n  let recordingAutoStopTimer = null;\n  let recordingStartedAt = 0;',
        1,
    )

if "async function loadCloneVoiceSettings()" not in js_text:
    insert_after = '''tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));'''

    settings_loader = r'''

  async function loadCloneVoiceSettings() {
    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load Clone Voice settings");
      }

      maxVoiceSourceSeconds = Number(data.maxVoiceSourceSeconds || 35);

      console.log("[Clone Voice] maxVoiceSourceSeconds:", maxVoiceSourceSeconds);

      if (recordingStatus) {
        recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
      }
    } catch (error) {
      console.warn("[Clone Voice] settings load failed; using default 35 seconds:", error);
      maxVoiceSourceSeconds = 35;
    }
  }

  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }
  }

  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();

    recordingStartedAt = Date.now();

    recordingAutoStopTimer = setTimeout(() => {
      console.log(`[Clone Voice] auto-stopping recording at ${maxVoiceSourceSeconds} seconds`);

      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }
'''

    if insert_after not in js_text:
        print("ERROR: Could not find JS insertion point after tabs listener.")
        raise SystemExit(1)

    js_text = js_text.replace(insert_after, insert_after + settings_loader, 1)

# Patch startRecording to start timer and show max D.
old_start_status = 'recordingStatus.textContent = "Speak clearly. Click Stop recording when done.";'
new_start_status = 'recordingStatus.textContent = `Speak clearly. Recording will auto-stop at ${maxVoiceSourceSeconds} seconds.`;\n      startRecordingAutoStopTimer();'

if old_start_status in js_text:
    js_text = js_text.replace(old_start_status, new_start_status, 1)

# Patch stopRecording to clear timer.
old_stop_start = '''  async function stopRecording() {
    try {'''
new_stop_start = '''  async function stopRecording() {
    clearRecordingAutoStopTimer();

    try {'''

if old_stop_start in js_text and "async function stopRecording() {\n    clearRecordingAutoStopTimer();" not in js_text:
    js_text = js_text.replace(old_stop_start, new_stop_start, 1)

# Patch discardRecording to clear timer.
old_discard_start = '''  function discardRecording() {
    recordedBlob = null;'''
new_discard_start = '''  function discardRecording() {
    clearRecordingAutoStopTimer();

    recordedBlob = null;'''

if old_discard_start in js_text and "function discardRecording() {\n    clearRecordingAutoStopTimer();" not in js_text:
    js_text = js_text.replace(old_discard_start, new_discard_start, 1)

# Call settings loader before setMode.
if "loadCloneVoiceSettings();" not in js_text:
    js_text = js_text.replace(
        'setMode("upload");',
        'loadCloneVoiceSettings();\n  setMode("upload");',
        1,
    )

JS.write_text(js_text, encoding="utf-8")

py_compile.compile(str(AUDIO_POLICY), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 2 COMPLETE: duration setting + recording auto-stop.")
print()
print("Created:")
print("  services/clone_voice_audio_policy.py")
print("  config/clone_voice_settings.json will be created automatically")
print()
print("New route:")
print("  GET /api/clone-voice/settings")
print()
print("Default setting:")
print("  max_voice_source_seconds = 35")
print()
print("Recording now auto-stops at D seconds.")
print("Upload trimming is NOT added yet. That is Step 3.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?duration-step2=1")
