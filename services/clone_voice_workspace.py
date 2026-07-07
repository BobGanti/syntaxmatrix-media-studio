from __future__ import annotations

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

DEMO_WORKSPACES = [
    {
        "workspaceId": "mock_user_001",
        "label": "Client A / Workspace 001",
    },
    {
        "workspaceId": "mock_user_002",
        "label": "Client B / Workspace 002",
    },
]

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
    return ""


def require_gender(value: str | None) -> str:
    gender = normalize_gender(value)
    if gender not in {"M", "F"}:
        raise ValueError("Voice gender is required. Choose Male (M) or Female (F).")
    return gender


def display_name_from_voice_id(voice_id: str) -> str:
    text = safe_slug(voice_id, "voice")
    parts = [part for part in re.split(r"[_-]+", text) if part]

    removable = {
        "m", "male", "f", "female",
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
    return ""


def voice_label(display_name: str, gender: str) -> str:
    gender = normalize_gender(gender)
    if gender in {"M", "F"}:
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



def list_demo_workspaces() -> list[dict[str, str]]:
    """Return demo workspaces used to verify tenant/client isolation."""
    rows: list[dict[str, str]] = []

    for row in DEMO_WORKSPACES:
        workspace_id = safe_slug(row.get("workspaceId"), MOCK_WORKSPACE_ID)

        # Ensure the workspace directories exist before the client switches to them.
        get_workspace(workspace_id)

        rows.append({
            "workspaceId": workspace_id,
            "label": row.get("label") or workspace_id,
        })

    return rows


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
    gender = require_gender(gender or existing.get("gender"))

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



def delete_workspace_voice(paths: WorkspacePaths, voice_id: str) -> dict[str, Any]:
    voice_id = safe_slug(voice_id)
    deleted: list[str] = []

    candidates: list[pathlib.Path] = [
        stable_parameter_path(paths, voice_id),
        legacy_parameter_path(paths, voice_id),
        stable_preview_path(paths, voice_id),
        metadata_path(paths, voice_id),
    ]

    for pattern in [
        f"{voice_id}_preview.*",
        f"{voice_id}.*",
    ]:
        for path in paths.voice_previews_dir.glob(pattern):
            candidates.append(path)

    unique: dict[str, pathlib.Path] = {}

    for path in candidates:
        unique[str(path.resolve())] = path

    for path in unique.values():
        if path.exists():
            deleted.append(relative_to_root(path))
            path.unlink()

    return {
        "ok": True,
        "voiceId": voice_id,
        "deleted": deleted,
        "deletedCount": len(deleted),
    }
