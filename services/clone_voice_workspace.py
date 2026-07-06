from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from datetime import datetime

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACES_DIR = ROOT / "workspaces"
MOCK_WORKSPACE_ID = "mock_user_001"


@dataclass(frozen=True)
class WorkspacePaths:
    workspace_id: str
    root: pathlib.Path
    tmp_source_audio_dir: pathlib.Path
    voice_params_dir: pathlib.Path
    generated_audio_dir: pathlib.Path


def sanitize_workspace_id(value: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or MOCK_WORKSPACE_ID).strip())
    return cleaned or MOCK_WORKSPACE_ID


def get_workspace(workspace_id: str | None = None) -> WorkspacePaths:
    safe_id = sanitize_workspace_id(workspace_id)
    root = WORKSPACES_DIR / safe_id
    paths = WorkspacePaths(
        workspace_id=safe_id,
        root=root,
        tmp_source_audio_dir=root / "tmp" / "source_audio",
        voice_params_dir=root / "voice_params",
        generated_audio_dir=root / "generated_audio",
    )
    paths.tmp_source_audio_dir.mkdir(parents=True, exist_ok=True)
    paths.voice_params_dir.mkdir(parents=True, exist_ok=True)
    paths.generated_audio_dir.mkdir(parents=True, exist_ok=True)
    return paths


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def voice_id(prefix: str = "smxvoice") -> str:
    return f"{prefix}_{timestamp()}"


def save_source_audio(file: FileStorage, paths: WorkspacePaths) -> pathlib.Path:
    safe_name = secure_filename(file.filename or "source_audio.wav")
    original = pathlib.Path(safe_name)
    stem = original.stem or "source_audio"
    ext = original.suffix or ".wav"
    target = paths.tmp_source_audio_dir / f"source_{timestamp()}_{stem}{ext}"
    file.save(target)
    return target


def delete_if_exists(path: pathlib.Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        print("[clone_voice_workspace] Could not delete temporary source:", repr(exc), flush=True)


def save_voice_parameter(paths: WorkspacePaths, voice_parameter: str, new_voice_id: str | None = None) -> tuple[str, pathlib.Path]:
    vid = new_voice_id or voice_id()
    param_path = paths.voice_params_dir / f"{vid}.txt"
    param_path.write_text(voice_parameter.strip(), encoding="utf-8")
    return vid, param_path


def generated_audio_path(paths: WorkspacePaths, prefix: str = "narration") -> pathlib.Path:
    return paths.generated_audio_dir / f"{prefix}_{timestamp()}.wav"


def workspace_generated_audio_url(paths: WorkspacePaths, output_path: pathlib.Path) -> str:
    return f"/media/workspaces/{paths.workspace_id}/generated_audio/{output_path.name}"


def relative_to_root(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)).replace(os.sep, "/")
