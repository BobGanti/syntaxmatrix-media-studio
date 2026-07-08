from __future__ import annotations

import pathlib
from typing import Any

from services.clone_voice_workspace import DEMO_WORKSPACES, get_workspace, relative_to_root
from services.object_storage import (
    get_object_storage,
    object_key_for_generated_audio,
    object_key_for_voice_preview,
    object_storage_status_payload,
)


ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_OBJECT_ROOT = ROOT / "object_storage"


def _safe_exists_in_storage(key: str) -> bool:
    try:
        return bool(get_object_storage().exists(key))
    except Exception:
        return False


def _local_object_storage_files() -> list[str]:
    if not LOCAL_OBJECT_ROOT.exists():
        return []

    return [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in LOCAL_OBJECT_ROOT.rglob("*")
        if path.is_file()
    ]


def _workspace_ids() -> list[str]:
    ids = []

    for row in DEMO_WORKSPACES:
        workspace_id = str(row.get("workspaceId") or "").strip()
        if workspace_id:
            ids.append(workspace_id)

    return sorted(set(ids))


def _audit_workspace(workspace_id: str) -> dict[str, Any]:
    workspace = get_workspace(workspace_id)

    generated_local = [
        path
        for path in workspace.generated_audio_dir.glob("*")
        if path.is_file()
    ]

    previews_local = [
        path
        for path in workspace.voice_previews_dir.glob("*")
        if path.is_file()
    ]

    generated_rows = []
    preview_rows = []

    for path in generated_local:
        key = object_key_for_generated_audio(workspace.workspace_id, path.name)
        generated_rows.append({
            "filename": path.name,
            "localPath": relative_to_root(path),
            "objectKey": key,
            "mirrored": _safe_exists_in_storage(key),
        })

    for path in previews_local:
        key = object_key_for_voice_preview(workspace.workspace_id, path.name)
        preview_rows.append({
            "filename": path.name,
            "localPath": relative_to_root(path),
            "objectKey": key,
            "mirrored": _safe_exists_in_storage(key),
        })

    missing_generated = [row for row in generated_rows if not row["mirrored"]]
    missing_previews = [row for row in preview_rows if not row["mirrored"]]

    return {
        "workspaceId": workspace.workspace_id,
        "local": {
            "generatedAudioCount": len(generated_rows),
            "voicePreviewCount": len(preview_rows),
        },
        "mirrors": {
            "generatedAudioMirrored": len(generated_rows) - len(missing_generated),
            "voicePreviewsMirrored": len(preview_rows) - len(missing_previews),
            "missingGeneratedAudio": missing_generated[:20],
            "missingVoicePreviews": missing_previews[:20],
        },
        "samples": {
            "generatedAudio": generated_rows[:10],
            "voicePreviews": preview_rows[:10],
        },
    }


def object_storage_media_audit_payload() -> dict[str, Any]:
    storage_status = object_storage_status_payload()
    local_files = _local_object_storage_files()
    workspace_audits = [_audit_workspace(workspace_id) for workspace_id in _workspace_ids()]

    total_generated = sum(row["local"]["generatedAudioCount"] for row in workspace_audits)
    total_previews = sum(row["local"]["voicePreviewCount"] for row in workspace_audits)
    total_missing_generated = sum(len(row["mirrors"]["missingGeneratedAudio"]) for row in workspace_audits)
    total_missing_previews = sum(len(row["mirrors"]["missingVoicePreviews"]) for row in workspace_audits)

    return {
        "storage": storage_status,
        "localObjectStorage": {
            "root": "object_storage",
            "fileCount": len(local_files),
            "sampleFiles": local_files[:30],
        },
        "summary": {
            "workspaceCount": len(workspace_audits),
            "generatedAudioLocalCount": total_generated,
            "voicePreviewLocalCount": total_previews,
            "missingGeneratedAudioMirrors": total_missing_generated,
            "missingVoicePreviewMirrors": total_missing_previews,
            "allWorkspaceMediaMirrored": total_missing_generated == 0 and total_missing_previews == 0,
        },
        "workspaces": workspace_audits,
    }
