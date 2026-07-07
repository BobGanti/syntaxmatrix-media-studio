from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()

AUDIO_POLICY = ROOT / "services" / "clone_voice_audio_policy.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
VIEW = ROOT / "views" / "clone_voice_view.py"

FRONTEND_DIR = ROOT / "frontend" / "clone_voice"
ADMIN_HTML = FRONTEND_DIR / "admin.html"
ADMIN_CSS = FRONTEND_DIR / "admin.css"
ADMIN_JS = FRONTEND_DIR / "admin.js"

required = [AUDIO_POLICY, CONTROLLER, VIEW, FRONTEND_DIR]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [AUDIO_POLICY, CONTROLLER, VIEW, ADMIN_HTML, ADMIN_CSS, ADMIN_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step5-admin-duration-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

AUDIO_POLICY.write_text(r'''from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess


ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "clone_voice_settings.json"

DEFAULT_MAX_VOICE_SOURCE_SECONDS = 20
MIN_MAX_VOICE_SOURCE_SECONDS = 5
MAX_MAX_VOICE_SOURCE_SECONDS = 120


def _safe_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def _clamp_duration(value: int) -> int:
    return max(MIN_MAX_VOICE_SOURCE_SECONDS, min(MAX_MAX_VOICE_SOURCE_SECONDS, int(value)))


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


def _read_settings() -> dict:
    ensure_default_settings_file()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print("[clone_voice_audio_policy] Could not read config:", repr(exc), flush=True)

    return {
        "max_voice_source_seconds": DEFAULT_MAX_VOICE_SOURCE_SECONDS
    }


def _write_settings(data: dict) -> pathlib.Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CONFIG_PATH


def get_max_voice_source_seconds() -> int:
    env_value = os.getenv("CLONE_VOICE_MAX_SOURCE_SECONDS")

    if env_value:
        return _clamp_duration(_safe_int(env_value, DEFAULT_MAX_VOICE_SOURCE_SECONDS))

    data = _read_settings()

    return _clamp_duration(_safe_int(data.get("max_voice_source_seconds"), DEFAULT_MAX_VOICE_SOURCE_SECONDS))


def set_max_voice_source_seconds(value: int) -> dict:
    duration = _clamp_duration(_safe_int(value, DEFAULT_MAX_VOICE_SOURCE_SECONDS))
    data = _read_settings()
    data["max_voice_source_seconds"] = duration
    path = _write_settings(data)

    return {
        "maxVoiceSourceSeconds": duration,
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
        "minSeconds": MIN_MAX_VOICE_SOURCE_SECONDS,
        "maxSeconds": MAX_MAX_VOICE_SOURCE_SECONDS,
    }


def settings_payload() -> dict:
    path = ensure_default_settings_file()

    return {
        "maxVoiceSourceSeconds": get_max_voice_source_seconds(),
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
        "minSeconds": MIN_MAX_VOICE_SOURCE_SECONDS,
        "maxSeconds": MAX_MAX_VOICE_SOURCE_SECONDS,
    }


def _ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY", "").strip()

    if configured:
        return configured

    found = shutil.which("ffmpeg")

    if not found:
        raise RuntimeError(
            "ffmpeg is required for Clone Voice audio duration limiting and volume normalization. "
            "Install ffmpeg or set FFMPEG_BINARY."
        )

    return found


def _run_ffmpeg(command: list[str], label: str) -> None:
    print(f"[clone_voice_audio_policy] {label}:", " ".join(command), flush=True)

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if len(stderr) > 1200:
            stderr = stderr[-1200:]
        raise RuntimeError(f"{label} failed: {stderr}")


def limit_audio_to_max_seconds(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    max_seconds: int | None = None,
) -> pathlib.Path:
    max_seconds = int(max_seconds or get_max_voice_source_seconds())

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        _ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-t",
        str(max_seconds),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        str(output_path),
    ]

    _run_ffmpeg(command, f"limit source audio to {max_seconds}s")

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Duration-limited audio was not created: {output_path}")

    return output_path


def normalize_generated_audio_file(audio_path: pathlib.Path) -> pathlib.Path:
    if not audio_path.exists():
        raise FileNotFoundError(f"Generated audio not found for normalization: {audio_path}")

    tmp_path = audio_path.with_name(audio_path.stem + "_normalized" + audio_path.suffix)

    command = [
        _ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(tmp_path),
    ]

    _run_ffmpeg(command, "normalize generated narration volume")

    if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        raise RuntimeError(f"Normalized narration was not created: {tmp_path}")

    tmp_path.replace(audio_path)

    return audio_path
''', encoding="utf-8")

controller = CONTROLLER.read_text(encoding="utf-8")

if "set_max_voice_source_seconds" not in controller:
    controller = controller.replace(
        "settings_payload,\n)",
        "settings_payload,\n    set_max_voice_source_seconds,\n)",
        1,
    )

if 'endpoint="clone_voice_update_settings"' not in controller:
    anchor = '''        @app.get("/api/clone-voice/settings", endpoint="clone_voice_settings")
        def clone_voice_settings():
            payload = settings_payload()
            print("[clone_voice_controller] Settings:", payload, flush=True)
            return jsonify({"ok": True, **payload})
'''

    if anchor not in controller:
        print("ERROR: Could not find existing GET settings route in controller.")
        raise SystemExit(1)

    replacement = anchor + r'''
    if "clone_voice_update_settings" not in app.view_functions:
        @app.post("/api/clone-voice/settings", endpoint="clone_voice_update_settings")
        def clone_voice_update_settings():
            data = request.get_json(silent=True) or request.form

            raw_value = (
                data.get("maxVoiceSourceSeconds")
                or data.get("max_voice_source_seconds")
                or data.get("duration")
                or data.get("D")
            )

            if raw_value is None:
                return _error("Missing maxVoiceSourceSeconds", 400)

            try:
                payload = set_max_voice_source_seconds(int(raw_value))
            except Exception as exc:
                return _error(str(exc), 400)

            print("[clone_voice_controller] Updated settings:", payload, flush=True)

            return jsonify({"ok": True, **payload})
'''

    controller = controller.replace(anchor, replacement, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

VIEW.write_text(r'''from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory


bp = Blueprint("clone_voice_view", __name__)


def _clone_voice_frontend_dir() -> Path:
    return Path(current_app.root_path) / "frontend" / "clone_voice"


@bp.get("/tasks/clone-voice")
def clone_voice_page():
    return send_from_directory(_clone_voice_frontend_dir(), "client.html")


@bp.get("/admin/clone-voice")
def clone_voice_admin_page():
    return send_from_directory(_clone_voice_frontend_dir(), "admin.html")


@bp.get("/tasks/voice-clone")
def old_voice_clone_redirect():
    return redirect("/tasks/clone-voice", code=302)
''', encoding="utf-8")

ADMIN_HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clone Voice Admin</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/admin.css?v=admin-duration-1">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Clone Voice Admin</h1>
      <p>Configure limits used by voice upload, recording, preview generation, and backend source limiting.</p>
      <p><a href="/tasks/clone-voice">← Back to Clone Voice</a></p>
    </header>

    <section class="card">
      <h2>Voice source duration</h2>
      <p class="status">
        This controls the maximum seconds allowed for uploaded or recorded voice source audio.
        The client recorder auto-stops at this value, and the backend trims uploaded/recorded source audio to this value before creating the voice parameter.
      </p>

      <form id="durationForm">
        <label>
          Max voice source duration, D seconds
          <input id="durationInput" name="maxVoiceSourceSeconds" type="number" min="5" max="120" step="1" required>
        </label>

        <button id="saveBtn" type="submit">Save setting</button>
      </form>

      <div id="statusBox" class="status-box">Loading setting...</div>
    </section>
  </main>

  <script src="/clone_voice/admin.js?v=admin-duration-1"></script>
</body>
</html>
''', encoding="utf-8")

ADMIN_CSS.write_text(r'''* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, sans-serif; background: #071017; color: #e8f1f8; padding: 32px; }
.shell { max-width: 850px; margin: 0 auto; display: grid; gap: 20px; }
.hero, .card { border: 1px solid #33414c; border-radius: 16px; padding: 20px; background: #111b24; }
.eyebrow, .status, .hero p { color: #a9bfd3; line-height: 1.55; }
a { color: #9ee8dc; font-weight: 900; text-decoration: none; }
h1, h2, p { margin-top: 0; }
label { display: grid; gap: 8px; margin-bottom: 16px; font-weight: 800; }
input, button { font: inherit; }
input[type="number"] { width: 100%; border: 1px solid #465662; border-radius: 12px; padding: 12px; background: #202b35; color: #fff; }
button { border: 0; border-radius: 999px; padding: 14px 22px; background: linear-gradient(135deg, #9ee8dc, #82a8ff); color: #06130f; font-weight: 900; cursor: pointer; }
button:disabled { opacity: .55; cursor: not-allowed; }
.status-box { margin-top: 18px; background: #02070b; border: 1px solid #33414c; border-radius: 12px; padding: 16px; color: #dceaf5; line-height: 1.55; }
.status-box strong { color: #9ee8dc; }
@media (max-width: 720px) { body { padding: 18px; } button { width: 100%; } }
''', encoding="utf-8")

ADMIN_JS.write_text(r'''(() => {
  const form = document.querySelector("#durationForm");
  const durationInput = document.querySelector("#durationInput");
  const saveBtn = document.querySelector("#saveBtn");
  const statusBox = document.querySelector("#statusBox");

  function renderStatus(data, message) {
    statusBox.innerHTML = `
      <strong>${message}</strong><br>
      Current D: ${data.maxVoiceSourceSeconds} seconds<br>
      Allowed range: ${data.minSeconds}–${data.maxSeconds} seconds<br>
      Config: ${data.configPath}
    `;
  }

  async function loadSettings() {
    statusBox.textContent = "Loading setting...";

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

      renderStatus(data, "Setting loaded.");
    } catch (error) {
      statusBox.textContent = error.message || String(error);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const value = Number(durationInput.value);

    if (!Number.isFinite(value) || value <= 0) {
      alert("Enter a valid duration in seconds.");
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    statusBox.textContent = "Saving setting...";

    try {
      const response = await fetch("/api/clone-voice/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          maxVoiceSourceSeconds: value
        })
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save settings");
      }

      durationInput.value = data.maxVoiceSourceSeconds;
      renderStatus(data, "Setting saved.");
    } catch (error) {
      statusBox.textContent = error.message || String(error);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save setting";
    }
  });

  loadSettings();
})();
''', encoding="utf-8")

py_compile.compile(str(AUDIO_POLICY), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)
py_compile.compile(str(VIEW), doraise=True)

print()
print("STEP 5 COMPLETE: Clone Voice Admin duration setting added.")
print()
print("New admin page:")
print("  http://127.0.0.1:5055/admin/clone-voice")
print()
print("Updated API:")
print("  GET  /api/clone-voice/settings")
print("  POST /api/clone-voice/settings")
print()
print("Setting stored in:")
print("  config/clone_voice_settings.json")
print()
print("Restart Flask:")
print("  python app.py")
