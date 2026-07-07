from pathlib import Path
from datetime import datetime
import json
import py_compile

ROOT = Path(".").resolve()

CONFIG_DIR = ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "clone_voice_settings.json"
AUDIO_POLICY = ROOT / "services" / "clone_voice_audio_policy.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"

required = [AUDIO_POLICY.parent, CONTROLLER]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CONFIG_FILE, AUDIO_POLICY, CONTROLLER]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step3-accuracy-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE.write_text(
    json.dumps({"max_voice_source_seconds": 20}, indent=2),
    encoding="utf-8",
)

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


def _safe_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def get_max_voice_source_seconds() -> int:
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
    """Create the stable voice preview/source used for voice parameter creation.

    The output file is always limited to D seconds.
    The provider uses this same output file to create the voice parameter.
    """
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
    """Normalize final narration volume so playback is audible and consistent."""
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

CONTROLLER.write_text(r'''from __future__ import annotations

import mimetypes

from flask import jsonify, request, send_from_directory

from services.clone_voice_audio_policy import (
    get_max_voice_source_seconds,
    limit_audio_to_max_seconds,
    normalize_generated_audio_file,
    settings_payload,
)
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
    stable_preview_path,
    voice_id_from_source_filename,
    workspace_generated_audio_url,
)


def _error(message: str, status: int = 500):
    return jsonify({"ok": False, "message": message, "error": message}), status


def _print_received_source(prompt: str, title: str, audio_file) -> None:
    print("\n" + "=" * 100, flush=True)
    print("[clone_voice_controller] FROM SOURCE", flush=True)
    print("FORM KEYS:", list(request.form.keys()), flush=True)
    print("FILE KEYS:", list(request.files.keys()), flush=True)
    print("title:", repr(title), flush=True)
    print("prompt_length:", len(prompt), flush=True)

    if audio_file:
        print("audio.filename:", repr(audio_file.filename), flush=True)
        print("audio.mimetype:", repr(audio_file.mimetype), flush=True)
        print("audio.content_type:", repr(audio_file.content_type), flush=True)
    else:
        print("audio: None", flush=True)

    print("=" * 100 + "\n", flush=True)


def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str):
    output_path = generated_audio_path(workspace, title)
    generate_narration_to_file(voice_parameter, prompt, output_path)
    normalize_generated_audio_file(output_path)
    asset_url = workspace_generated_audio_url(workspace, output_path)
    return output_path, asset_url


def register_clone_voice_routes(app):
    if "clone_voice_settings" not in app.view_functions:
        @app.get("/api/clone-voice/settings", endpoint="clone_voice_settings")
        def clone_voice_settings():
            payload = settings_payload()
            print("[clone_voice_controller] Settings:", payload, flush=True)
            return jsonify({"ok": True, **payload})

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
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            source_mode = request.form.get("sourceMode", "upload")
            audio_file = request.files.get("audio")

            _print_received_source(prompt, title, audio_file)

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if audio_file is None or not audio_file.filename:
                return _error("Missing uploaded audio file under field name 'audio'", 400)

            workspace = get_workspace(workspace_id)
            source_path = None

            try:
                voice_id = voice_id_from_source_filename(audio_file.filename)
                source_path = save_source_audio(audio_file, workspace)

                max_seconds = get_max_voice_source_seconds()
                preview_path = stable_preview_path(workspace, voice_id, audio_file.filename)

                print("[clone_voice_controller] voiceId from source filename:", voice_id, flush=True)
                print("[clone_voice_controller] Temporary raw source saved:", source_path, flush=True)
                print("[clone_voice_controller] Limiting source/preview to seconds:", max_seconds, flush=True)
                print("[clone_voice_controller] Stable preview target:", preview_path, flush=True)

                limited_preview_path = limit_audio_to_max_seconds(
                    input_path=source_path,
                    output_path=preview_path,
                    max_seconds=max_seconds,
                )

                audio_mime_type = mimetypes.guess_type(limited_preview_path.name)[0] or audio_file.mimetype or "audio/wav"

                print("[clone_voice_controller] Rebuilding stable voice parameter from current source", flush=True)
                print("[clone_voice_controller] Voice parameter source:", limited_preview_path, flush=True)

                voice_parameter = create_voice_parameter(limited_preview_path, audio_mime_type)
                voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)

                print("[clone_voice_controller] Stable voice parameter saved/overwritten:", param_path, flush=True)

                output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)

                return jsonify({
                    "ok": True,
                    "sourceType": source_mode,
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(limited_preview_path),
                    "maxVoiceSourceSeconds": max_seconds,
                    "rawSourceDeleted": True,
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                    "narrationTitle": title,
                    "volumeNormalized": True,
                })

            except Exception as exc:
                print("[clone_voice_controller] from-source error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                if source_path is not None:
                    delete_if_exists(source_path)
                    print("[clone_voice_controller] Temporary raw source deleted:", source_path, flush=True)

    if "clone_voice_from_saved" not in app.view_functions:
        @app.post("/api/clone-voice/from-saved", endpoint="clone_voice_from_saved")
        def from_saved():
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] FROM SAVED VOICE", flush=True)
            print("workspaceId:", repr(workspace_id), flush=True)
            print("voiceId:", repr(voice_id), flush=True)
            print("title:", repr(title), flush=True)
            print("prompt_length:", len(prompt), flush=True)
            print("=" * 100 + "\n", flush=True)

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)

                output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)

                return jsonify({
                    "ok": True,
                    "sourceType": "saved",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "voiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                    "narrationTitle": title,
                    "volumeNormalized": True,
                })

            except Exception as exc:
                print("[clone_voice_controller] from-saved error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_from_system" not in app.view_functions:
        @app.post("/api/clone-voice/from-system", endpoint="clone_voice_from_system")
        def from_system():
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] FROM SYSTEM", flush=True)
            print("voiceId:", repr(voice_id), flush=True)
            print("title:", repr(title), flush=True)
            print("prompt_length:", len(prompt), flush=True)
            print("=" * 100 + "\n", flush=True)

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_system_voice_parameter(voice_id)

                output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)

                return jsonify({
                    "ok": True,
                    "sourceType": "system",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "systemVoiceParamPath": relative_to_root(param_path),
                    "assetUrl": asset_url,
                    "audioUrl": asset_url,
                    "outputPath": relative_to_root(output_path),
                    "narrationTitle": title,
                    "volumeNormalized": True,
                })

            except Exception as exc:
                print("[clone_voice_controller] from-system error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_workspace_audio" not in app.view_functions:
        @app.get("/media/workspaces/<workspace_id>/generated_audio/<path:filename>", endpoint="clone_voice_workspace_audio")
        def workspace_audio(workspace_id: str, filename: str):
            workspace = get_workspace(workspace_id)
            return send_from_directory(workspace.generated_audio_dir, filename)

    if "clone_voice_workspace_preview" not in app.view_functions:
        @app.get("/media/workspaces/<workspace_id>/voice_previews/<path:filename>", endpoint="clone_voice_workspace_preview")
        def workspace_preview(workspace_id: str, filename: str):
            workspace = get_workspace(workspace_id)
            return send_from_directory(workspace.voice_previews_dir, filename)

    if "clone_voice_preview_audio" not in app.view_functions:
        @app.get("/media/voices/previews/<path:filename>", endpoint="clone_voice_preview_audio")
        def preview_audio(filename: str):
            return send_from_directory(SYSTEM_PREVIEWS_DIR, filename)
''', encoding="utf-8")

py_compile.compile(str(AUDIO_POLICY), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 3 COMPLETE.")
print()
print("Changed:")
print("  D is now 20 seconds")
print("  Upload/record source is always limited to D before voice parameter creation")
print("  Upload/record source always rebuilds and overwrites the stable voice parameter")
print("  Generated narration is normalized after download")
print()
print("Stable source identity remains:")
print("  bobga.wav -> bobga_parameter.txt + bobga_preview.wav")
print("  recorded voice -> recorded_voice_parameter.txt + recorded_voice_preview.wav")
print()
print("Requires ffmpeg at runtime for duration limiting and normalization.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?accuracy-step3=1")
