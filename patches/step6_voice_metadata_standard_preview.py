from pathlib import Path
from datetime import datetime
import py_compile

ROOT = Path(".").resolve()

WORKSPACE = ROOT / "services" / "clone_voice_workspace.py"
SYSTEM = ROOT / "services" / "clone_voice_system.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [WORKSPACE.parent, SYSTEM.parent, CONTROLLER.parent, HTML.parent]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice structure not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [WORKSPACE, SYSTEM, CONTROLLER, HTML, CSS, JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step6-metadata-preview-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

WORKSPACE.write_text(r'''from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any

from werkzeug.datastructures import FileStorage


ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT / "workspaces"
MOCK_WORKSPACE_ID = "mock_user_001"

STANDARD_VOICE_PREVIEW_TEXT = (
    "Hello, this is a preview of this voice. "
    "I can read your narration clearly, naturally, and consistently."
)


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_id: str
    root: pathlib.Path
    tmp_source_audio_dir: pathlib.Path
    voice_params_dir: pathlib.Path
    voice_previews_dir: pathlib.Path
    voice_metadata_dir: pathlib.Path
    generated_audio_dir: pathlib.Path


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S")


def safe_slug(value: str, fallback: str = "voice") -> str:
    text = pathlib.Path(str(value or "")).stem.strip()
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text or fallback


def normalize_gender(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE"}:
        return "M"
    if text in {"F", "FEMALE"}:
        return "F"
    return "U"


def display_name_from_voice_id(voice_id: str) -> str:
    text = safe_slug(voice_id, "voice")
    parts = [part for part in re.split(r"[_-]+", text) if part]

    removable = {
        "m", "male", "f", "female", "u", "unknown",
        "wav", "mp3", "m4a", "webm", "ogg", "aac", "flac",
        "parameter", "preview",
    }

    clean_parts = [part for part in parts if part.lower() not in removable]

    if not clean_parts:
        clean_parts = parts or ["Voice"]

    if clean_parts[:2] == ["recorded", "voice"]:
        return "Recorded Voice " + " ".join(clean_parts[2:]) if len(clean_parts) > 2 else "Recorded Voice"

    return " ".join(part[:1].upper() + part[1:] for part in clean_parts)


def infer_gender_from_voice_id(voice_id: str) -> str:
    parts = [part.upper() for part in re.split(r"[_-]+", str(voice_id or "")) if part]
    if "M" in parts or "MALE" in parts:
        return "M"
    if "F" in parts or "FEMALE" in parts:
        return "F"
    return "U"


def voice_label(display_name: str, gender: str) -> str:
    gender = normalize_gender(gender)
    if gender in {"M", "F", "U"}:
        return f"{display_name} ({gender})"
    return display_name


def get_workspace(workspace_id: str | None = None) -> WorkspacePaths:
    workspace_id = safe_slug(workspace_id or MOCK_WORKSPACE_ID, MOCK_WORKSPACE_ID)
    root = WORKSPACES_DIR / workspace_id

    paths = WorkspacePaths(
        workspace_id=workspace_id,
        root=root,
        tmp_source_audio_dir=root / "tmp" / "source_audio",
        voice_params_dir=root / "voice_params",
        voice_previews_dir=root / "voice_previews",
        voice_metadata_dir=root / "voice_metadata",
        generated_audio_dir=root / "generated_audio",
    )

    for directory in [
        paths.tmp_source_audio_dir,
        paths.voice_params_dir,
        paths.voice_previews_dir,
        paths.voice_metadata_dir,
        paths.generated_audio_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    return paths


def relative_to_root(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def voice_id_from_source_filename(filename: str) -> str:
    return safe_slug(filename, "uploaded_voice")


def new_recorded_voice_id() -> str:
    return f"recorded_voice_{now_stamp()}"


def stable_parameter_path(paths: WorkspacePaths, voice_id: str) -> pathlib.Path:
    return paths.voice_params_dir / f"{safe_slug(voice_id)}_parameter.txt"


def legacy_parameter_path(paths: WorkspacePaths, voice_id: str) -> pathlib.Path:
    return paths.voice_params_dir / f"{safe_slug(voice_id)}.txt"


def stable_preview_path(paths: WorkspacePaths, voice_id: str, source_filename: str | None = None) -> pathlib.Path:
    return paths.voice_previews_dir / f"{safe_slug(voice_id)}_preview.wav"


def source_limited_path(paths: WorkspacePaths, voice_id: str) -> pathlib.Path:
    return paths.tmp_source_audio_dir / f"{safe_slug(voice_id)}_limited_{now_stamp()}.wav"


def metadata_path(paths: WorkspacePaths, voice_id: str) -> pathlib.Path:
    return paths.voice_metadata_dir / f"{safe_slug(voice_id)}.json"


def generated_audio_path(paths: WorkspacePaths, title: str) -> pathlib.Path:
    title_slug = safe_slug(title, "narration")
    return paths.generated_audio_dir / f"{title_slug}_{now_stamp()}.wav"


def workspace_generated_audio_url(paths: WorkspacePaths, output_path: pathlib.Path) -> str:
    return f"/media/workspaces/{paths.workspace_id}/generated_audio/{output_path.name}"


def workspace_voice_preview_url(paths: WorkspacePaths, preview_path: pathlib.Path) -> str:
    return f"/media/workspaces/{paths.workspace_id}/voice_previews/{preview_path.name}"


def save_source_audio(file_storage: FileStorage, paths: WorkspacePaths) -> pathlib.Path:
    original_name = file_storage.filename or "source_audio.wav"
    suffix = pathlib.Path(original_name).suffix or ".wav"
    target = paths.tmp_source_audio_dir / f"{safe_slug(original_name, 'source_audio')}_{now_stamp()}{suffix}"
    file_storage.save(target)
    return target


def delete_if_exists(path: pathlib.Path | None) -> None:
    if not path:
        return
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        print("[clone_voice_workspace] Could not delete:", path, repr(exc), flush=True)


def voice_parameter_exists(paths: WorkspacePaths, voice_id: str) -> bool:
    return stable_parameter_path(paths, voice_id).exists() or legacy_parameter_path(paths, voice_id).exists()


def save_voice_parameter(paths: WorkspacePaths, voice_parameter: str, voice_id: str) -> tuple[str, pathlib.Path]:
    voice_id = safe_slug(voice_id)
    path = stable_parameter_path(paths, voice_id)
    path.write_text(str(voice_parameter), encoding="utf-8")
    return voice_id, path


def load_workspace_voice_parameter(paths: WorkspacePaths, voice_id: str) -> tuple[str, pathlib.Path]:
    voice_id = safe_slug(voice_id)

    candidates = [
        stable_parameter_path(paths, voice_id),
        legacy_parameter_path(paths, voice_id),
    ]

    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8").strip(), path

    raise FileNotFoundError(f"Voice parameter not found for voiceId={voice_id}")


def load_voice_metadata(paths: WorkspacePaths, voice_id: str) -> dict[str, Any]:
    path = metadata_path(paths, voice_id)

    if not path.exists():
        gender = infer_gender_from_voice_id(voice_id)
        display_name = display_name_from_voice_id(voice_id)

        return {
            "voiceId": safe_slug(voice_id),
            "displayName": display_name,
            "gender": gender,
            "label": voice_label(display_name, gender),
            "previewText": STANDARD_VOICE_PREVIEW_TEXT,
            "previewKind": "unknown",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            voice_id = data.get("voiceId") or voice_id
            display_name = data.get("displayName") or display_name_from_voice_id(voice_id)
            gender = normalize_gender(data.get("gender") or infer_gender_from_voice_id(voice_id))
            data["voiceId"] = safe_slug(voice_id)
            data["displayName"] = display_name
            data["gender"] = gender
            data["label"] = voice_label(display_name, gender)
            data.setdefault("previewText", STANDARD_VOICE_PREVIEW_TEXT)
            return data
    except Exception as exc:
        print("[clone_voice_workspace] Could not read metadata:", path, repr(exc), flush=True)

    gender = infer_gender_from_voice_id(voice_id)
    display_name = display_name_from_voice_id(voice_id)

    return {
        "voiceId": safe_slug(voice_id),
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "unknown",
    }


def save_voice_metadata(
    paths: WorkspacePaths,
    voice_id: str,
    display_name: str | None,
    gender: str | None,
    *,
    source_type: str,
    parameter_path: pathlib.Path,
    preview_path: pathlib.Path,
    parameter_created: bool,
    preview_created: bool,
) -> tuple[dict[str, Any], pathlib.Path]:
    voice_id = safe_slug(voice_id)
    existing = load_voice_metadata(paths, voice_id)

    display_name = (display_name or existing.get("displayName") or display_name_from_voice_id(voice_id)).strip()
    gender = normalize_gender(gender or existing.get("gender"))

    metadata = {
        **existing,
        "voiceId": voice_id,
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "sourceType": source_type,
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "standard_synthesized",
        "parameterPath": relative_to_root(parameter_path),
        "previewPath": relative_to_root(preview_path),
        "parameterCreated": bool(parameter_created),
        "previewCreated": bool(preview_created),
        "updatedAt": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    path = metadata_path(paths, voice_id)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata, path


def _voice_id_from_param_path(path: pathlib.Path) -> str:
    stem = path.stem
    if stem.endswith("_parameter"):
        stem = stem[:-len("_parameter")]
    return safe_slug(stem)


def list_workspace_voice_parameters(paths: WorkspacePaths) -> list[dict[str, Any]]:
    files = []

    for path in paths.voice_params_dir.glob("*.txt"):
        files.append(path)

    unique: dict[str, pathlib.Path] = {}

    for path in files:
        voice_id = _voice_id_from_param_path(path)
        preferred = stable_parameter_path(paths, voice_id)

        if voice_id not in unique:
            unique[voice_id] = path

        if path == preferred:
            unique[voice_id] = path

    rows = []

    for voice_id, param_path in unique.items():
        metadata = load_voice_metadata(paths, voice_id)
        preview_path = stable_preview_path(paths, voice_id)
        preview_url = workspace_voice_preview_url(paths, preview_path) if preview_path.exists() else ""

        rows.append({
            "voiceId": voice_id,
            "displayName": metadata.get("displayName") or display_name_from_voice_id(voice_id),
            "gender": normalize_gender(metadata.get("gender")),
            "label": metadata.get("label") or voice_label(metadata.get("displayName") or display_name_from_voice_id(voice_id), metadata.get("gender")),
            "previewUrl": preview_url,
            "previewText": metadata.get("previewText") or STANDARD_VOICE_PREVIEW_TEXT,
            "previewKind": metadata.get("previewKind") or "unknown",
            "parameterPath": relative_to_root(param_path),
            "previewPath": relative_to_root(preview_path) if preview_path.exists() else "",
            "updatedAt": metadata.get("updatedAt") or "",
            "mtime": param_path.stat().st_mtime if param_path.exists() else 0,
        })

    rows.sort(key=lambda row: row.get("mtime", 0), reverse=True)

    for row in rows:
        row.pop("mtime", None)

    return rows
''', encoding="utf-8")

SYSTEM.write_text(r'''from __future__ import annotations

import json
import pathlib
from typing import Any

from services.clone_voice_workspace import (
    ROOT,
    STANDARD_VOICE_PREVIEW_TEXT,
    display_name_from_voice_id,
    infer_gender_from_voice_id,
    normalize_gender,
    relative_to_root,
    safe_slug,
    voice_label,
)


SYSTEM_VOICES_DIR = ROOT / "voices"
SYSTEM_PARAMS_DIR = SYSTEM_VOICES_DIR / "params"
SYSTEM_PREVIEWS_DIR = SYSTEM_VOICES_DIR / "previews"
SYSTEM_METADATA_DIR = SYSTEM_VOICES_DIR / "metadata"


def _voice_id_from_param_path(path: pathlib.Path) -> str:
    stem = path.stem
    if stem.endswith("_parameter"):
        stem = stem[:-len("_parameter")]
    return safe_slug(stem)


def _metadata_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_METADATA_DIR / f"{safe_slug(voice_id)}.json"


def _load_system_metadata(voice_id: str) -> dict[str, Any]:
    path = _metadata_path(voice_id)

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                display_name = data.get("displayName") or display_name_from_voice_id(voice_id)
                gender = normalize_gender(data.get("gender") or infer_gender_from_voice_id(voice_id))

                data["voiceId"] = safe_slug(voice_id)
                data["displayName"] = display_name
                data["gender"] = gender
                data["label"] = voice_label(display_name, gender)
                data.setdefault("previewText", STANDARD_VOICE_PREVIEW_TEXT)
                data.setdefault("previewKind", "standard_synthesized")
                return data
        except Exception as exc:
            print("[clone_voice_system] Could not read metadata:", path, repr(exc), flush=True)

    gender = infer_gender_from_voice_id(voice_id)
    display_name = display_name_from_voice_id(voice_id)

    return {
        "voiceId": safe_slug(voice_id),
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "unknown",
    }


def _find_param_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    candidates = [
        SYSTEM_PARAMS_DIR / f"{voice_id}_parameter.txt",
        SYSTEM_PARAMS_DIR / f"{voice_id}.txt",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def _find_preview_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    first = SYSTEM_PREVIEWS_DIR / f"{voice_id}_preview.wav"

    if first.exists():
        return first

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}_preview.*"):
        return path

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}.*"):
        return path

    return None


def list_system_voices_payload() -> list[dict[str, Any]]:
    SYSTEM_PARAMS_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_METADATA_DIR.mkdir(parents=True, exist_ok=True)

    rows = []

    for param_path in sorted(SYSTEM_PARAMS_DIR.glob("*.txt")):
        voice_id = _voice_id_from_param_path(param_path)
        metadata = _load_system_metadata(voice_id)
        preview_path = _find_preview_path(voice_id)

        rows.append({
            "voiceId": voice_id,
            "displayName": metadata.get("displayName") or display_name_from_voice_id(voice_id),
            "gender": normalize_gender(metadata.get("gender")),
            "label": metadata.get("label") or voice_label(metadata.get("displayName") or display_name_from_voice_id(voice_id), metadata.get("gender")),
            "previewUrl": f"/media/voices/previews/{preview_path.name}" if preview_path else "",
            "previewText": metadata.get("previewText") or STANDARD_VOICE_PREVIEW_TEXT,
            "previewKind": metadata.get("previewKind") or "unknown",
            "parameterPath": relative_to_root(param_path),
            "previewPath": relative_to_root(preview_path) if preview_path else "",
        })

    return rows


def load_system_voice_parameter(voice_id: str) -> tuple[str, pathlib.Path]:
    path = _find_param_path(voice_id)

    if not path:
        raise FileNotFoundError(f"System voice parameter not found for voiceId={voice_id}")

    return path.read_text(encoding="utf-8").strip(), path
''', encoding="utf-8")

CONTROLLER.write_text(r'''from __future__ import annotations

from flask import jsonify, request, send_from_directory

from services.clone_voice_audio_policy import (
    get_max_voice_source_seconds,
    limit_audio_to_max_seconds,
    normalize_generated_audio_file,
    settings_payload,
    set_max_voice_source_seconds,
)
from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_system import SYSTEM_PREVIEWS_DIR, list_system_voices_payload, load_system_voice_parameter
from services.clone_voice_workspace import (
    MOCK_WORKSPACE_ID,
    STANDARD_VOICE_PREVIEW_TEXT,
    delete_if_exists,
    display_name_from_voice_id,
    generated_audio_path,
    get_workspace,
    list_workspace_voice_parameters,
    load_voice_metadata,
    load_workspace_voice_parameter,
    new_recorded_voice_id,
    normalize_gender,
    relative_to_root,
    save_source_audio,
    save_voice_metadata,
    save_voice_parameter,
    source_limited_path,
    stable_preview_path,
    voice_id_from_source_filename,
    voice_parameter_exists,
    workspace_generated_audio_url,
    workspace_voice_preview_url,
)


def _error(message: str, status: int = 500):
    return jsonify({"ok": False, "message": message, "error": message}), status


def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str):
    output_path = generated_audio_path(workspace, title)
    generate_narration_to_file(voice_parameter, prompt, output_path)
    normalize_generated_audio_file(output_path)
    asset_url = workspace_generated_audio_url(workspace, output_path)
    return output_path, asset_url


def _generate_standard_preview(voice_parameter: str, preview_path):
    print("[clone_voice_controller] Generating standard synthesized voice preview:", preview_path, flush=True)
    generate_narration_to_file(voice_parameter, STANDARD_VOICE_PREVIEW_TEXT, preview_path)
    normalize_generated_audio_file(preview_path)


def _print_received_source(prompt: str, title: str, audio_file, source_mode: str) -> None:
    print("\n" + "=" * 100, flush=True)
    print("[clone_voice_controller] FROM SOURCE", flush=True)
    print("sourceMode:", repr(source_mode), flush=True)
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


def register_clone_voice_routes(app):
    if "clone_voice_settings" not in app.view_functions:
        @app.get("/api/clone-voice/settings", endpoint="clone_voice_settings")
        def clone_voice_settings():
            payload = settings_payload()
            print("[clone_voice_controller] Settings:", payload, flush=True)
            return jsonify({"ok": True, **payload})

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
            source_mode = request.form.get("sourceMode", "upload").strip().lower()
            audio_file = request.files.get("audio")

            display_name_input = (
                request.form.get("voiceDisplayName", "")
                or request.form.get("displayName", "")
                or request.form.get("voiceName", "")
            ).strip()

            gender = normalize_gender(request.form.get("gender"))

            _print_received_source(prompt, title, audio_file, source_mode)

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if audio_file is None or not audio_file.filename:
                return _error("Missing uploaded audio file under field name 'audio'", 400)

            is_recording = source_mode == "record"
            workspace = get_workspace(workspace_id)

            raw_source_path = None
            limited_source_path = None

            try:
                if is_recording:
                    voice_id = new_recorded_voice_id()
                else:
                    voice_id = voice_id_from_source_filename(audio_file.filename)

                display_name = display_name_input or display_name_from_voice_id(voice_id)
                preview_path = stable_preview_path(workspace, voice_id)
                max_seconds = get_max_voice_source_seconds()

                raw_source_path = save_source_audio(audio_file, workspace)

                print("[clone_voice_controller] voiceId:", voice_id, flush=True)
                print("[clone_voice_controller] displayName:", display_name, flush=True)
                print("[clone_voice_controller] gender:", gender, flush=True)
                print("[clone_voice_controller] raw source:", raw_source_path, flush=True)
                print("[clone_voice_controller] preview target:", preview_path, flush=True)

                existing_parameter = voice_parameter_exists(workspace, voice_id)

                parameter_created = False
                preview_created = False

                if existing_parameter and not is_recording:
                    print("[clone_voice_controller] Uploaded source parameter already exists. Reusing:", voice_id, flush=True)
                    voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
                else:
                    limited_source_path = source_limited_path(workspace, voice_id)

                    limit_audio_to_max_seconds(
                        input_path=raw_source_path,
                        output_path=limited_source_path,
                        max_seconds=max_seconds,
                    )

                    print("[clone_voice_controller] Creating voice parameter from limited source:", limited_source_path, flush=True)

                    voice_parameter = create_voice_parameter(limited_source_path, "audio/wav")
                    voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)
                    parameter_created = True

                metadata_before = load_voice_metadata(workspace, voice_id)
                preview_is_standard = (
                    preview_path.exists()
                    and metadata_before.get("previewKind") == "standard_synthesized"
                )

                if is_recording or not preview_is_standard:
                    _generate_standard_preview(voice_parameter, preview_path)
                    preview_created = True
                else:
                    print("[clone_voice_controller] Standard preview already exists. Reusing:", preview_path, flush=True)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type="record" if is_recording else "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=parameter_created,
                    preview_created=preview_created,
                )

                output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)

                return jsonify({
                    "ok": True,
                    "sourceType": "record" if is_recording else "upload",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(preview_path),
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "previewText": STANDARD_VOICE_PREVIEW_TEXT,
                    "parameterCreated": parameter_created,
                    "previewCreated": preview_created,
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
                delete_if_exists(raw_source_path)
                delete_if_exists(limited_source_path)

    if "clone_voice_from_saved" not in app.view_functions:
        @app.post("/api/clone-voice/from-saved", endpoint="clone_voice_from_saved")
        def from_saved():
            title = request.form.get("title", "").strip()
            prompt = request.form.get("prompt", "").strip()
            voice_id = request.form.get("voiceId", "").strip()
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            if not title:
                return _error("Missing narration title", 400)

            if not prompt:
                return _error("Missing prompt", 400)

            if not voice_id:
                return _error("Missing voiceId", 400)

            try:
                workspace = get_workspace(workspace_id)
                voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
                metadata = load_voice_metadata(workspace, voice_id)

                output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)

                return jsonify({
                    "ok": True,
                    "sourceType": "saved",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata.get("displayName"),
                    "gender": metadata.get("gender"),
                    "label": metadata.get("label"),
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

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/client.css?v=step6-standard-preview">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p>Create narration from an uploaded voice, a recorded voice, a saved voice, or a system voice.</p>
      <p class="mini-link"><a href="/admin/clone-voice">Admin settings</a></p>
    </header>

    <form id="cloneVoiceForm" class="card">
      <section>
        <h2>1. Choose voice source</h2>

        <div class="mode-grid">
          <label><input type="radio" name="sourceMode" value="upload" checked> Upload audio</label>
          <label><input type="radio" name="sourceMode" value="record"> Record voice</label>
          <label><input type="radio" name="sourceMode" value="saved"> My saved voices</label>
          <label><input type="radio" name="sourceMode" value="system"> System voices</label>
        </div>

        <div id="uploadPanel" class="source-panel">
          <label>
            Upload voice source
            <input id="audioFile" type="file" accept="audio/*">
          </label>
          <p class="status">If the same uploaded filename already has a voice parameter, it will be reused. No duplicate preview will be created.</p>
        </div>

        <div id="recordPanel" class="source-panel hidden">
          <div class="button-row">
            <button id="startRecordingBtn" type="button">Start recording</button>
            <button id="stopRecordingBtn" type="button" disabled>Stop</button>
            <button id="discardRecordingBtn" type="button" disabled>Discard</button>
          </div>

          <p class="status" id="recordingStatus">Start recording, speak clearly, then stop.</p>
          <div class="record-timer" id="recordingTimer" aria-live="polite">0.0s / 20s</div>

          <div class="mic-meter" id="micMeter" aria-label="Microphone input level">
            <span class="mic-meter-label">Mic signal</span>
            <div class="mic-meter-track">
              <div class="mic-meter-fill" id="micMeterFill"></div>
            </div>
            <span class="mic-meter-value" id="micMeterValue">silent</span>
          </div>

          <p class="status">Every recording creates a new voice parameter and a new standard preview.</p>
        </div>

        <div id="voiceDetailsPanel" class="voice-details">
          <label>
            Voice display name
            <input id="voiceDisplayName" type="text" placeholder="Example: Bobga, Ngozi">
          </label>

          <label>
            Voice gender
            <select id="voiceGender">
              <option value="U">Unspecified (U)</option>
              <option value="M">Male (M)</option>
              <option value="F">Female (F)</option>
            </select>
          </label>
        </div>

        <div id="savedPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="savedGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
                <option value="U">Unspecified voices</option>
              </select>
            </label>
            <button id="refreshSavedBtn" type="button">Refresh saved voices</button>
          </div>
          <div id="savedVoicesList" class="voice-list">Loading saved voices...</div>
        </div>

        <div id="systemPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="systemGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
                <option value="U">Unspecified voices</option>
              </select>
            </label>
            <button id="refreshSystemBtn" type="button">Refresh system voices</button>
          </div>
          <div id="systemVoicesList" class="voice-list">Loading system voices...</div>
        </div>
      </section>

      <section>
        <h2>2. Narration</h2>

        <label>
          Narration title
          <input id="titleInput" type="text" placeholder="Example: NewAge" required>
        </label>

        <label>
          Text to narrate
          <textarea id="promptInput" rows="8" placeholder="Paste the narration text here..." required></textarea>
        </label>

        <button id="submitBtn" type="submit">Generate narration</button>
      </section>
    </form>

    <section class="card">
      <h2>Result</h2>
      <audio id="audioPlayer" controls class="hidden"></audio>
      <p><a id="downloadLink" class="hidden" href="#" download>Download narration</a></p>
      <div id="resultBox" class="result-summary">No request sent yet.</div>
    </section>
  </main>

  <script src="/clone_voice/client.js?v=step6-standard-preview"></script>
</body>
</html>
''', encoding="utf-8")

CSS.write_text(r'''* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 32px;
  font-family: Arial, sans-serif;
  background: #071017;
  color: #e8f1f8;
}

.shell {
  max-width: 1050px;
  margin: 0 auto;
  display: grid;
  gap: 22px;
}

.hero,
.card {
  border: 1px solid #33414c;
  border-radius: 18px;
  padding: 22px;
  background: #111b24;
}

.eyebrow,
.status,
.mini-link {
  color: #a9bfd3;
  line-height: 1.55;
}

h1,
h2,
p {
  margin-top: 0;
}

a {
  color: #9ee8dc;
  font-weight: 900;
  text-decoration: none;
}

label {
  display: grid;
  gap: 8px;
  font-weight: 800;
}

input,
textarea,
select,
button {
  font: inherit;
}

input[type="text"],
input[type="file"],
textarea,
select {
  width: 100%;
  border: 1px solid #465662;
  border-radius: 12px;
  padding: 12px;
  background: #202b35;
  color: #fff;
}

textarea {
  resize: vertical;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 13px 20px;
  background: linear-gradient(135deg, #9ee8dc, #82a8ff);
  color: #06130f;
  font-weight: 900;
  cursor: pointer;
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.hidden {
  display: none !important;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0 18px;
}

.mode-grid label {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #33414c;
  border-radius: 14px;
  padding: 12px;
  background: #071017;
}

.source-panel,
.voice-details {
  display: grid;
  gap: 14px;
  margin: 16px 0;
}

.voice-details {
  grid-template-columns: 1fr 220px;
}

.button-row,
.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
}

.list-toolbar label {
  min-width: 220px;
}

.record-timer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-width: 150px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid #465662;
  background: #071017;
  color: #9ee8dc;
  font-weight: 900;
  letter-spacing: .04em;
}

.mic-meter {
  display: grid;
  grid-template-columns: auto minmax(140px, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #465662;
  border-radius: 14px;
  background: #071017;
}

.mic-meter-label,
.mic-meter-value {
  color: #a9bfd3;
  font-size: 0.92rem;
  font-weight: 800;
  white-space: nowrap;
}

.mic-meter-track {
  position: relative;
  width: 100%;
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: #1e2a34;
  border: 1px solid #33414c;
}

.mic-meter-fill {
  width: 0%;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #9ee8dc, #82a8ff);
  transition: width 80ms linear;
}

.mic-meter.is-active .mic-meter-value {
  color: #9ee8dc;
}

.mic-meter.is-loud .mic-meter-fill {
  background: linear-gradient(90deg, #9ee8dc, #ffd166);
}

.voice-list {
  display: grid;
  gap: 10px;
}

.voice-card {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: center;
  border: 1px solid #33414c;
  border-radius: 14px;
  padding: 12px;
  background: #071017;
}

.voice-card-title {
  font-weight: 900;
  color: #e8f1f8;
}

.voice-card-meta {
  color: #a9bfd3;
  font-size: .9rem;
}

.preview-btn {
  padding: 9px 14px;
}

.result-summary {
  display: grid;
  gap: 10px;
  background: #02070b;
  border: 1px solid #33414c;
  border-radius: 12px;
  padding: 16px;
  color: #dceaf5;
  line-height: 1.55;
}

.result-summary strong {
  color: #9ee8dc;
}

.result-summary .muted {
  color: #a9bfd3;
}

.result-grid {
  display: grid;
  gap: 8px;
}

.result-row {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 12px;
}

.result-label {
  color: #a9bfd3;
  font-weight: 800;
}

.result-value {
  overflow-wrap: anywhere;
}

audio {
  width: 100%;
}

@media (max-width: 860px) {
  body {
    padding: 18px;
  }

  .mode-grid,
  .voice-details {
    grid-template-columns: 1fr;
  }

  .voice-card {
    grid-template-columns: 1fr;
  }

  .mic-meter {
    grid-template-columns: 1fr;
  }

  .result-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
''', encoding="utf-8")

JS.write_text(r'''(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const form = $("#cloneVoiceForm");
  const sourceModeInputs = $$('input[name="sourceMode"]');

  const uploadPanel = $("#uploadPanel");
  const recordPanel = $("#recordPanel");
  const savedPanel = $("#savedPanel");
  const systemPanel = $("#systemPanel");
  const voiceDetailsPanel = $("#voiceDetailsPanel");

  const audioFile = $("#audioFile");
  const voiceDisplayName = $("#voiceDisplayName");
  const voiceGender = $("#voiceGender");

  const startRecordingBtn = $("#startRecordingBtn");
  const stopRecordingBtn = $("#stopRecordingBtn");
  const discardRecordingBtn = $("#discardRecordingBtn");
  const recordingStatus = $("#recordingStatus");
  const recordingTimer = $("#recordingTimer");

  const micMeter = $("#micMeter");
  const micMeterFill = $("#micMeterFill");
  const micMeterValue = $("#micMeterValue");

  const savedVoicesList = $("#savedVoicesList");
  const systemVoicesList = $("#systemVoicesList");
  const savedGenderFilter = $("#savedGenderFilter");
  const systemGenderFilter = $("#systemGenderFilter");
  const refreshSavedBtn = $("#refreshSavedBtn");
  const refreshSystemBtn = $("#refreshSystemBtn");

  const titleInput = $("#titleInput");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const audioPlayer = $("#audioPlayer");
  const downloadLink = $("#downloadLink");
  const resultBox = $("#resultBox");

  const WORKSPACE_ID = "mock_user_001";

  let maxVoiceSourceSeconds = 20;

  let mediaRecorder = null;
  let micStream = null;
  let audioContext = null;
  let micSource = null;
  let recordedChunks = [];
  let recordedBlob = null;
  let recordedFilename = "";

  let recordingAutoStopTimer = null;
  let recordingTicker = null;
  let recordingStartedAt = 0;

  let micAnalyserNode = null;
  let micMeterData = null;
  let micMeterAnimationFrame = null;

  let savedVoices = [];
  let systemVoices = [];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function selectedMode() {
    return sourceModeInputs.find((input) => input.checked)?.value || "upload";
  }

  function setMode(mode) {
    uploadPanel.classList.toggle("hidden", mode !== "upload");
    recordPanel.classList.toggle("hidden", mode !== "record");
    savedPanel.classList.toggle("hidden", mode !== "saved");
    systemPanel.classList.toggle("hidden", mode !== "system");
    voiceDetailsPanel.classList.toggle("hidden", !(mode === "upload" || mode === "record"));

    if (mode === "saved") loadSavedVoices();
    if (mode === "system") loadSystemVoices();
  }

  function filenameFromPath(value) {
    const text = String(value || "");
    if (!text) return "";
    const parts = text.split("/");
    return parts[parts.length - 1] || text;
  }

  function renderFriendlyResult(data) {
    const rows = [
      ["Narration", filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl) || "Ready"],
      ["Title", data.narrationTitle || ""],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Source", data.sourceType || ""],
      ["Max voice sample", data.maxVoiceSourceSeconds ? `${data.maxVoiceSourceSeconds} seconds` : ""],
      ["Parameter created", typeof data.parameterCreated === "boolean" ? (data.parameterCreated ? "Yes" : "No, reused existing") : ""],
      ["Preview created", typeof data.previewCreated === "boolean" ? (data.previewCreated ? "Yes" : "No, reused existing") : ""],
      ["Volume normalized", data.volumeNormalized ? "Yes" : ""],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Narration generated successfully.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Voice previews use the standard preview sentence, not the uploaded or recorded source text.</div>
    `;
  }

  async function loadCloneVoiceSettings() {
    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (response.ok && data.ok && data.maxVoiceSourceSeconds) {
        maxVoiceSourceSeconds = Number(data.maxVoiceSourceSeconds) || 20;
      }
    } catch (error) {
      console.warn("[Clone Voice] Could not load settings:", error);
    }

    renderRecordingTimer(0);
    recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
  }

  function renderRecordingTimer(elapsedSeconds = 0) {
    const safeElapsed = Math.max(0, Number(elapsedSeconds) || 0);
    const safeMax = Math.max(1, Number(maxVoiceSourceSeconds || 20));
    recordingTimer.textContent = `${safeElapsed.toFixed(1)}s / ${safeMax}s`;
    recordingTimer.setAttribute("title", `${Math.max(0, safeMax - safeElapsed).toFixed(1)} seconds remaining`);
  }

  function clearRecordingTicker() {
    if (recordingTicker) {
      clearInterval(recordingTicker);
      recordingTicker = null;
    }
  }

  function startRecordingTicker() {
    clearRecordingTicker();
    recordingStartedAt = Date.now();
    renderRecordingTimer(0);

    recordingTicker = setInterval(() => {
      const elapsed = (Date.now() - recordingStartedAt) / 1000;
      renderRecordingTimer(Math.min(elapsed, maxVoiceSourceSeconds));
    }, 100);
  }

  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }
    clearRecordingTicker();
  }

  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();
    startRecordingTicker();

    recordingAutoStopTimer = setTimeout(() => {
      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }

  function renderMicLevel(level) {
    const safeLevel = Math.max(0, Math.min(1, Number(level) || 0));
    const percent = Math.round(safeLevel * 100);

    micMeterFill.style.width = `${percent}%`;
    micMeter.classList.toggle("is-active", safeLevel > 0.08);
    micMeter.classList.toggle("is-loud", safeLevel > 0.72);

    if (safeLevel < 0.04) {
      micMeterValue.textContent = "silent";
    } else if (safeLevel < 0.18) {
      micMeterValue.textContent = "low";
    } else if (safeLevel < 0.72) {
      micMeterValue.textContent = "good";
    } else {
      micMeterValue.textContent = "loud";
    }
  }

  function stopMicMeter() {
    if (micMeterAnimationFrame) {
      cancelAnimationFrame(micMeterAnimationFrame);
      micMeterAnimationFrame = null;
    }

    try {
      if (micAnalyserNode) micAnalyserNode.disconnect();
    } catch {}

    micAnalyserNode = null;
    micMeterData = null;
    renderMicLevel(0);
  }

  function startMicMeter(sourceNode, ctx) {
    stopMicMeter();

    micAnalyserNode = ctx.createAnalyser();
    micAnalyserNode.fftSize = 2048;
    micAnalyserNode.smoothingTimeConstant = 0.82;
    micMeterData = new Uint8Array(micAnalyserNode.fftSize);

    sourceNode.connect(micAnalyserNode);

    const tick = () => {
      if (!micAnalyserNode || !micMeterData) {
        renderMicLevel(0);
        return;
      }

      micAnalyserNode.getByteTimeDomainData(micMeterData);

      let sumSquares = 0;

      for (let index = 0; index < micMeterData.length; index += 1) {
        const centered = (micMeterData[index] - 128) / 128;
        sumSquares += centered * centered;
      }

      const rms = Math.sqrt(sumSquares / micMeterData.length);
      renderMicLevel(Math.min(1, rms * 4.5));

      micMeterAnimationFrame = requestAnimationFrame(tick);
    };

    tick();
  }

  async function startRecording() {
    try {
      recordedChunks = [];
      recordedBlob = null;
      recordedFilename = "";

      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new AudioContext();
      micSource = audioContext.createMediaStreamSource(micStream);
      startMicMeter(micSource, audioContext);

      const options = MediaRecorder.isTypeSupported("audio/webm")
        ? { mimeType: "audio/webm" }
        : undefined;

      mediaRecorder = new MediaRecorder(micStream, options);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", () => {
        const mimeType = mediaRecorder.mimeType || "audio/webm";
        recordedBlob = new Blob(recordedChunks, { type: mimeType });
        recordedFilename = `recorded_voice_${Date.now()}.webm`;

        recordingStatus.textContent = `Recording ready: ${recordedFilename}`;
        discardRecordingBtn.disabled = false;
      });

      mediaRecorder.start();

      startRecordingBtn.disabled = true;
      stopRecordingBtn.disabled = false;
      discardRecordingBtn.disabled = true;
      recordingStatus.textContent = `Recording... auto-stops at ${maxVoiceSourceSeconds} seconds.`;

      startRecordingAutoStopTimer();
    } catch (error) {
      recordingStatus.textContent = error.message || String(error);
      stopMicMeter();
      clearRecordingAutoStopTimer();
    }
  }

  function stopRecording() {
    const elapsedBeforeStop = recordingStartedAt
      ? Math.min((Date.now() - recordingStartedAt) / 1000, maxVoiceSourceSeconds)
      : 0;

    clearRecordingAutoStopTimer();
    renderRecordingTimer(elapsedBeforeStop);
    stopMicMeter();

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    if (audioContext) {
      audioContext.close().catch(() => {});
    }

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
  }

  function discardRecording() {
    stopMicMeter();
    clearRecordingAutoStopTimer();

    recordedChunks = [];
    recordedBlob = null;
    recordedFilename = "";

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    recordingStatus.textContent = "Start recording, speak clearly, then stop.";
    renderRecordingTimer(0);

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
    discardRecordingBtn.disabled = true;
  }

  function filteredVoices(voices, genderFilter) {
    const filter = genderFilter || "";
    if (!filter) return voices;
    return voices.filter((voice) => String(voice.gender || "U").toUpperCase() === filter);
  }

  function renderVoiceList(container, voices, groupName, genderFilter) {
    const rows = filteredVoices(voices, genderFilter);

    if (!rows.length) {
      container.innerHTML = `<p class="status">No voices found for this filter.</p>`;
      return;
    }

    container.innerHTML = rows.map((voice, index) => {
      const inputId = `${groupName}_${index}`;
      const previewButton = voice.previewUrl
        ? `<button class="preview-btn" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}">Preview</button>`
        : `<span class="voice-card-meta">No preview</span>`;

      return `
        <label class="voice-card" for="${escapeHtml(inputId)}">
          <input id="${escapeHtml(inputId)}" type="radio" name="${escapeHtml(groupName)}" value="${escapeHtml(voice.voiceId)}">
          <span>
            <span class="voice-card-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</span>
            <span class="voice-card-meta">Standard preview sentence</span>
          </span>
          ${previewButton}
        </label>
      `;
    }).join("");
  }

  async function loadSavedVoices() {
    savedVoicesList.textContent = "Loading saved voices...";

    try {
      const response = await fetch(`/api/clone-voice/my-voices?workspaceId=${encodeURIComponent(WORKSPACE_ID)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load saved voices");
      }

      savedVoices = data.voices || [];
      renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
    } catch (error) {
      savedVoicesList.textContent = error.message || String(error);
    }
  }

  async function loadSystemVoices() {
    systemVoicesList.textContent = "Loading system voices...";

    try {
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      systemVoices = data.voices || [];
      renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
    } catch (error) {
      systemVoicesList.textContent = error.message || String(error);
    }
  }

  function selectedVoiceId(groupName) {
    return document.querySelector(`input[name="${groupName}"]:checked`)?.value || "";
  }

  async function playPreview(url) {
    if (!url) return;

    audioPlayer.classList.remove("hidden");
    audioPlayer.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    await audioPlayer.play().catch(() => {});
  }

  async function submitForm(event) {
    event.preventDefault();

    const mode = selectedMode();
    const title = titleInput.value.trim();
    const prompt = promptInput.value.trim();

    if (!title) {
      alert("Enter a narration title.");
      return;
    }

    if (!prompt) {
      alert("Enter narration text.");
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", WORKSPACE_ID);
    formData.append("title", title);
    formData.append("prompt", prompt);
    formData.append("sourceMode", mode);

    let endpoint = "/api/clone-voice/from-source";

    if (mode === "upload") {
      const file = audioFile.files[0];

      if (!file) {
        alert("Choose an audio file.");
        return;
      }

      formData.append("audio", file, file.name);
      formData.append("voiceDisplayName", voiceDisplayName.value.trim());
      formData.append("gender", voiceGender.value);
    }

    if (mode === "record") {
      if (!recordedBlob) {
        alert("Record a voice first.");
        return;
      }

      formData.append("audio", recordedBlob, recordedFilename || "recorded_voice.webm");
      formData.append("voiceDisplayName", voiceDisplayName.value.trim());
      formData.append("gender", voiceGender.value);
    }

    if (mode === "saved") {
      const voiceId = selectedVoiceId("savedVoiceId");

      if (!voiceId) {
        alert("Choose a saved voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-saved";
      formData.append("voiceId", voiceId);
    }

    if (mode === "system") {
      const voiceId = selectedVoiceId("systemVoiceId");

      if (!voiceId) {
        alert("Choose a system voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-system";
      formData.append("voiceId", voiceId);
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";
    resultBox.textContent = "Generating narration...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log("[Clone Voice response]", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Narration failed");
      }

      const audioUrl = data.audioUrl || data.assetUrl;

      if (audioUrl) {
        audioPlayer.src = `${audioUrl}${audioUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");

        downloadLink.href = audioUrl;
        downloadLink.classList.remove("hidden");
      }

      renderFriendlyResult(data);

      if (mode === "upload" || mode === "record") {
        await loadSavedVoices();
      }
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Generate narration";
    }
  }

  sourceModeInputs.forEach((input) => {
    input.addEventListener("change", () => setMode(selectedMode()));
  });

  startRecordingBtn.addEventListener("click", startRecording);
  stopRecordingBtn.addEventListener("click", stopRecording);
  discardRecordingBtn.addEventListener("click", discardRecording);

  refreshSavedBtn.addEventListener("click", loadSavedVoices);
  refreshSystemBtn.addEventListener("click", loadSystemVoices);

  savedGenderFilter.addEventListener("change", () => {
    renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
  });

  systemGenderFilter.addEventListener("change", () => {
    renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-preview-url]");
    if (!button) return;
    event.preventDefault();
    playPreview(button.getAttribute("data-preview-url"));
  });

  form.addEventListener("submit", submitForm);

  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadSavedVoices();
  loadSystemVoices();
  setMode("upload");
})();
''', encoding="utf-8")

py_compile.compile(str(WORKSPACE), doraise=True)
py_compile.compile(str(SYSTEM), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 6 COMPLETE: voice metadata + standard synthesized previews.")
print()
print("Implemented:")
print("  Uploaded file source reuses existing parameter and existing standard preview.")
print("  Each recorded audio gets a fresh voiceId, parameter, and preview.")
print("  Preview is generated from one fixed preview sentence.")
print("  Voice metadata now stores displayName and gender.")
print("  Client displays voices as Bobga (M), Ngozi (F), etc.")
print("  Client can filter saved/system voices by gender.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?step6-standard-preview=1")
