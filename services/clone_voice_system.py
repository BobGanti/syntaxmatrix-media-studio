from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any

from werkzeug.datastructures import FileStorage

from services.clone_voice_audio_policy import (
    prepare_voice_source_audio,
    normalize_generated_audio_file,
)
from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.persistence_repository import get_persistence_repository
from services.clone_voice_workspace import (
    ROOT,
    STANDARD_VOICE_PREVIEW_TEXT,
    delete_if_exists,
    display_name_from_voice_id,
    infer_gender_from_voice_id,
    normalize_gender,
    require_gender,
    relative_to_root,
    safe_slug,
    voice_label,
)


SYSTEM_VOICES_DIR = ROOT / "voices"
SYSTEM_PARAMS_DIR = SYSTEM_VOICES_DIR / "params"
SYSTEM_PREVIEWS_DIR = SYSTEM_VOICES_DIR / "previews"
SYSTEM_METADATA_DIR = SYSTEM_VOICES_DIR / "metadata"
SYSTEM_TMP_DIR = SYSTEM_VOICES_DIR / "tmp" / "source_audio"


def _system_repository():
    return get_persistence_repository()


def _durable_system_catalog_enabled() -> bool:
    return _system_repository().backend_name == "postgres"


def _system_preview_object_key(preview_path: pathlib.Path) -> str:
    from services.object_storage import object_key_for_system_voice_preview
    return object_key_for_system_voice_preview(preview_path.name)


def _mirror_system_preview(preview_path: pathlib.Path) -> str:
    from services.object_storage import get_object_storage
    key = _system_preview_object_key(preview_path)
    get_object_storage().upload_file(key, preview_path, content_type="audio/wav")
    return key


def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S")


def ensure_system_dirs() -> None:
    for directory in [SYSTEM_PARAMS_DIR, SYSTEM_PREVIEWS_DIR, SYSTEM_METADATA_DIR, SYSTEM_TMP_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def _voice_id_from_param_path(path: pathlib.Path) -> str:
    stem = path.stem
    if stem.endswith("_parameter"):
        stem = stem[:-len("_parameter")]
    return safe_slug(stem)


def system_parameter_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PARAMS_DIR / f"{safe_slug(voice_id)}_parameter.txt"


def system_legacy_parameter_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PARAMS_DIR / f"{safe_slug(voice_id)}.txt"


def system_preview_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_PREVIEWS_DIR / f"{safe_slug(voice_id)}_preview.wav"


def system_metadata_path(voice_id: str) -> pathlib.Path:
    return SYSTEM_METADATA_DIR / f"{safe_slug(voice_id)}.json"


def _find_param_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    candidates = [
        system_parameter_path(voice_id),
        system_legacy_parameter_path(voice_id),
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def _find_preview_path(voice_id: str) -> pathlib.Path | None:
    voice_id = safe_slug(voice_id)

    first = system_preview_path(voice_id)

    if first.exists():
        return first

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}_preview.*"):
        return path

    for path in SYSTEM_PREVIEWS_DIR.glob(f"{voice_id}.*"):
        return path

    return None


def _load_system_metadata(voice_id: str) -> dict[str, Any]:
    ensure_system_dirs()
    voice_id = safe_slug(voice_id)

    if _durable_system_catalog_enabled():
        record = _system_repository().get_system_voice(voice_id)
        if record:
            metadata = dict(record.get("metadata")) if isinstance(record.get("metadata"), dict) else {}
            display_name = record.get("displayName") or metadata.get("displayName") or display_name_from_voice_id(voice_id)
            gender = normalize_gender(record.get("gender") or metadata.get("gender"))
            metadata.update({
                "voiceId": voice_id,
                "displayName": display_name,
                "gender": gender,
                "label": voice_label(display_name, gender),
                "previewText": metadata.get("previewText") or STANDARD_VOICE_PREVIEW_TEXT,
                "previewKind": metadata.get("previewKind") or "standard_synthesized",
                "previewObjectKey": record.get("previewObjectKey") or metadata.get("previewObjectKey") or "",
                "updatedAt": record.get("updatedAt") or metadata.get("updatedAt") or "",
            })
            return metadata

    path = system_metadata_path(voice_id)

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


def _save_system_metadata(
    voice_id: str,
    display_name: str,
    gender: str,
    *,
    parameter_path: pathlib.Path,
    preview_path: pathlib.Path,
) -> tuple[dict[str, Any], pathlib.Path]:
    ensure_system_dirs()

    voice_id = safe_slug(voice_id)
    display_name = (display_name or display_name_from_voice_id(voice_id)).strip()
    gender = require_gender(gender)

    metadata = {
        "voiceId": voice_id,
        "displayName": display_name,
        "gender": gender,
        "label": voice_label(display_name, gender),
        "sourceType": "system",
        "previewText": STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": "standard_synthesized",
        "parameterPath": relative_to_root(parameter_path),
        "previewPath": relative_to_root(preview_path),
        "updatedAt": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    path = system_metadata_path(voice_id)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if _durable_system_catalog_enabled():
        preview_key = _mirror_system_preview(preview_path)
        provider_voice_id = parameter_path.read_text(encoding="utf-8").strip()
        metadata["previewObjectKey"] = preview_key
        _system_repository().upsert_system_voice(
            voice_id,
            {
                "providerVoiceId": provider_voice_id,
                "displayName": display_name,
                "gender": gender,
                "previewObjectKey": preview_key,
                "previewContentType": "audio/wav",
                "status": "active",
                "metadata": metadata,
            },
        )

    return metadata, path


def _system_voice_payload(voice_id: str, param_path: pathlib.Path | None = None) -> dict[str, Any]:
    metadata = _load_system_metadata(voice_id)
    param_path = param_path or _find_param_path(voice_id)
    preview_path = _find_preview_path(voice_id)
    preview_object_key = metadata.get("previewObjectKey") or ""
    preview_filename = preview_path.name if preview_path else (pathlib.Path(preview_object_key).name if preview_object_key else "")

    return {
        "voiceId": safe_slug(voice_id),
        "displayName": metadata.get("displayName") or display_name_from_voice_id(voice_id),
        "gender": normalize_gender(metadata.get("gender")),
        "label": metadata.get("label") or voice_label(
            metadata.get("displayName") or display_name_from_voice_id(voice_id),
            metadata.get("gender")
        ),
        "previewUrl": f"/media/voices/previews/{preview_filename}" if preview_filename else "",
        "previewText": metadata.get("previewText") or STANDARD_VOICE_PREVIEW_TEXT,
        "previewKind": metadata.get("previewKind") or "unknown",
        "parameterPath": relative_to_root(param_path) if param_path else "",
        "previewPath": relative_to_root(preview_path) if preview_path else "",
        "updatedAt": metadata.get("updatedAt") or "",
    }


def list_system_voices_payload() -> list[dict[str, Any]]:
    ensure_system_dirs()

    if _durable_system_catalog_enabled():
        rows = []
        for record in _system_repository().list_system_voices():
            voice_id = safe_slug(record.get("voiceId"))
            payload = _system_voice_payload(voice_id)
            if payload.get("gender") in {"M", "F"}:
                rows.append(payload)
        return rows

    unique: dict[str, pathlib.Path] = {}
    for param_path in sorted(SYSTEM_PARAMS_DIR.glob("*.txt")):
        voice_id = _voice_id_from_param_path(param_path)
        preferred = system_parameter_path(voice_id)
        if voice_id not in unique or param_path == preferred:
            unique[voice_id] = param_path

    rows = []
    for voice_id, param_path in unique.items():
        payload = _system_voice_payload(voice_id, param_path)
        if payload.get("gender") not in {"M", "F"}:
            continue
        payload["_mtime"] = param_path.stat().st_mtime if param_path.exists() else 0
        rows.append(payload)
    rows.sort(key=lambda row: row.get("_mtime", 0), reverse=True)
    for row in rows:
        row.pop("_mtime", None)
    return rows


def load_system_voice_parameter(voice_id: str) -> tuple[str, pathlib.Path]:
    ensure_system_dirs()
    voice_id = safe_slug(voice_id)

    if _durable_system_catalog_enabled():
        record = _system_repository().get_system_voice(voice_id)
        if record and record.get("providerVoiceId"):
            path = system_parameter_path(voice_id)
            if not path.exists():
                path.write_text(str(record["providerVoiceId"]), encoding="utf-8")
            return str(record["providerVoiceId"]).strip(), path

    path = _find_param_path(voice_id)

    if not path:
        raise FileNotFoundError(f"System voice parameter not found for voiceId={voice_id}")

    return path.read_text(encoding="utf-8").strip(), path


def save_system_voice_from_path(
    source_path: pathlib.Path,
    *,
    original_filename: str,
    display_name: str,
    gender: str,
    replace: bool = False,
) -> dict[str, Any]:
    ensure_system_dirs()

    source_path = pathlib.Path(source_path)
    if not source_path.exists() or source_path.stat().st_size <= 0:
        raise ValueError("Missing system voice audio source")

    display_name = (display_name or pathlib.Path(original_filename).stem or "System Voice").strip()
    voice_id = safe_slug(display_name, "system_voice")
    gender = require_gender(gender)

    existing_record = _system_repository().get_system_voice(voice_id) if _durable_system_catalog_enabled() else None
    existing_param = _find_param_path(voice_id)

    if (existing_record or existing_param) and not replace:
        raise FileExistsError(
            f"System voice already exists for '{display_name}'. Enable replace to overwrite it."
        )

    limited_source_path = SYSTEM_TMP_DIR / f"{voice_id}_limited_{_now_stamp()}.wav"

    try:
        prepared = prepare_voice_source_audio(
            input_path=source_path,
            output_path=limited_source_path,
        )
        enrollment_path = pathlib.Path(prepared["path"])
        voice_parameter = create_voice_parameter(enrollment_path)

        param_path = system_parameter_path(voice_id)
        preview_path = system_preview_path(voice_id)
        param_path.write_text(str(voice_parameter), encoding="utf-8")

        print("[clone_voice_system] Generating standard system preview:", preview_path, flush=True)
        generate_narration_to_file(voice_parameter, STANDARD_VOICE_PREVIEW_TEXT, preview_path)
        normalize_generated_audio_file(preview_path)

        metadata, metadata_path = _save_system_metadata(
            voice_id,
            display_name,
            gender,
            parameter_path=param_path,
            preview_path=preview_path,
        )

        payload = _system_voice_payload(voice_id, param_path)
        payload.update({
            "ok": True,
            "replaced": bool(existing_record or existing_param),
            "maxVoiceSourceSeconds": prepared["targetSeconds"],
            "sourceDurationSeconds": prepared["durationSeconds"],
            "sourceTrimmed": bool(prepared["trimmed"]),
            "autoTrimVoiceSource": bool(prepared["autoTrimEnabled"]),
            "metadataPath": relative_to_root(metadata_path),
            "previewText": STANDARD_VOICE_PREVIEW_TEXT,
            "metadata": metadata,
        })
        return payload
    finally:
        delete_if_exists(limited_source_path)


def save_system_voice_from_source(
    audio_file: FileStorage,
    *,
    display_name: str,
    gender: str,
    replace: bool = False,
) -> dict[str, Any]:
    """Compatibility path for small local multipart uploads.

    Production browser uploads use GCS resumable ingestion and call
    save_system_voice_from_path after the backend downloads the temporary object.
    """
    ensure_system_dirs()
    if audio_file is None or not audio_file.filename:
        raise ValueError("Missing system voice audio source")

    suffix = pathlib.Path(audio_file.filename).suffix or ".wav"
    raw_source_path = SYSTEM_TMP_DIR / f"system_raw_{_now_stamp()}{suffix}"
    try:
        audio_file.save(raw_source_path)
        return save_system_voice_from_path(
            raw_source_path,
            original_filename=audio_file.filename,
            display_name=display_name,
            gender=gender,
            replace=replace,
        )
    finally:
        delete_if_exists(raw_source_path)

def delete_system_voice(voice_id: str) -> dict[str, Any]:
    ensure_system_dirs()

    voice_id = safe_slug(voice_id)
    deleted: list[str] = []

    if _durable_system_catalog_enabled():
        record = _system_repository().get_system_voice(voice_id)
        if record:
            preview_key = record.get("previewObjectKey") or ""
            if preview_key:
                try:
                    from services.object_storage import get_object_storage
                    if get_object_storage().delete(preview_key):
                        deleted.append(str(preview_key))
                except Exception as exc:
                    print("[clone_voice_system] Could not delete preview object:", repr(exc), flush=True)
            if _system_repository().delete_system_voice(voice_id):
                deleted.append(f"database:system_voices/{voice_id}")

    candidates: list[pathlib.Path | None] = [
        system_parameter_path(voice_id),
        system_legacy_parameter_path(voice_id),
        _find_preview_path(voice_id),
        system_metadata_path(voice_id),
    ]

    for path in candidates:
        if path and path.exists():
            deleted.append(relative_to_root(path))
            path.unlink()

    return {
        "ok": True,
        "voiceId": voice_id,
        "deleted": deleted,
        "deletedCount": len(deleted),
    }
