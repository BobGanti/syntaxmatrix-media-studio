from __future__ import annotations

from flask import jsonify, request, send_from_directory

from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_system import SYSTEM_PREVIEWS_DIR, list_system_voices_payload, load_system_voice_parameter
from services.clone_voice_workspace import (
    MOCK_WORKSPACE_ID,
    delete_if_exists,
    generated_audio_path,
    get_workspace,
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
