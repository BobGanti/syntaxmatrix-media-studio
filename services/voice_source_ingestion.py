from __future__ import annotations

import pathlib
import re
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any

from werkzeug.utils import secure_filename

from services.clone_voice_audio_policy import max_raw_upload_bytes
from services.object_storage import (
    ObjectStorageError,
    get_object_storage,
    object_storage_backend,
)


_ALLOWED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".webm", ".mp4"
}


class VoiceSourceUploadError(ValueError):
    status_code = 400


class VoiceSourceUploadTooLarge(VoiceSourceUploadError):
    status_code = 413


class VoiceSourceUploadNotReady(VoiceSourceUploadError):
    status_code = 409


@dataclass(frozen=True)
class UploadedVoiceSource:
    object_key: str
    original_filename: str
    content_type: str
    size_bytes: int


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_filename(filename: str) -> str:
    candidate = secure_filename(pathlib.Path(_clean(filename, "voice_source.wav")).name)
    if not candidate:
        candidate = "voice_source.wav"
    suffix = pathlib.Path(candidate).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise VoiceSourceUploadError(
            "Unsupported voice-source file type. Supported extensions: "
            + ", ".join(sorted(_ALLOWED_EXTENSIONS))
        )
    return candidate


def _safe_workspace_id(workspace_id: str) -> str:
    value = _clean(workspace_id)
    if not value or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise VoiceSourceUploadError("A valid workspaceId is required.")
    return value


def _validate_size(size_bytes: Any) -> int:
    try:
        parsed = int(size_bytes)
    except Exception as exc:
        raise VoiceSourceUploadError("sizeBytes must be an integer.") from exc
    if parsed <= 0:
        raise VoiceSourceUploadError("The selected audio file is empty.")
    maximum = max_raw_upload_bytes()
    if parsed > maximum:
        raise VoiceSourceUploadTooLarge(
            f"The raw voice source is {parsed / (1024 * 1024):.1f} MB. "
            f"The configured raw-upload safety limit is {maximum / (1024 * 1024):.0f} MB."
        )
    return parsed


def workspace_temporary_prefix(workspace_id: str) -> str:
    return f"temporary/voice_sources/workspaces/{_safe_workspace_id(workspace_id)}/"


def system_temporary_prefix() -> str:
    return "temporary/voice_sources/system/"


def create_workspace_upload_session(
    *,
    workspace_id: str,
    filename: str,
    content_type: str,
    size_bytes: Any,
    origin: str,
    user_id: str,
    purpose: str = "create",
) -> dict[str, Any]:
    workspace_id = _safe_workspace_id(workspace_id)
    filename = _safe_filename(filename)
    size_bytes = _validate_size(size_bytes)
    content_type = _clean(content_type, "application/octet-stream")

    if object_storage_backend() != "gcs":
        raise VoiceSourceUploadError(
            "Direct large-file ingestion requires OBJECT_STORAGE_BACKEND=gcs."
        )

    key = f"{workspace_temporary_prefix(workspace_id)}{uuid.uuid4().hex}/{filename}"
    storage = get_object_storage()
    upload_url = storage.create_resumable_upload_session(
        key,
        content_type=content_type,
        size=size_bytes,
        origin=_clean(origin),
        metadata={
            "syntaxmatrix-purpose": _clean(purpose, "create"),
            "syntaxmatrix-workspace-id": workspace_id,
            "syntaxmatrix-user-id": _clean(user_id),
            "syntaxmatrix-original-filename": filename,
        },
    )
    return {
        "ok": True,
        "uploadMode": "gcs_resumable",
        "method": "PUT",
        "uploadUrl": upload_url,
        "objectKey": key,
        "workspaceId": workspace_id,
        "originalFilename": filename,
        "contentType": content_type,
        "sizeBytes": size_bytes,
    }


def create_system_upload_session(
    *,
    filename: str,
    content_type: str,
    size_bytes: Any,
    origin: str,
    user_id: str,
) -> dict[str, Any]:
    filename = _safe_filename(filename)
    size_bytes = _validate_size(size_bytes)
    content_type = _clean(content_type, "application/octet-stream")

    if object_storage_backend() != "gcs":
        raise VoiceSourceUploadError(
            "Direct large-file ingestion requires OBJECT_STORAGE_BACKEND=gcs."
        )

    key = f"{system_temporary_prefix()}{uuid.uuid4().hex}/{filename}"
    storage = get_object_storage()
    upload_url = storage.create_resumable_upload_session(
        key,
        content_type=content_type,
        size=size_bytes,
        origin=_clean(origin),
        metadata={
            "syntaxmatrix-purpose": "system_voice",
            "syntaxmatrix-user-id": _clean(user_id),
            "syntaxmatrix-original-filename": filename,
        },
    )
    return {
        "ok": True,
        "uploadMode": "gcs_resumable",
        "method": "PUT",
        "uploadUrl": upload_url,
        "objectKey": key,
        "originalFilename": filename,
        "contentType": content_type,
        "sizeBytes": size_bytes,
    }


def _validate_key_prefix(object_key: str, expected_prefix: str) -> str:
    key = _clean(object_key).replace("\\", "/").lstrip("/")
    if not key.startswith(expected_prefix) or ".." in key.split("/"):
        raise VoiceSourceUploadError("The uploaded object does not belong to the requested voice-source scope.")
    return key


def download_completed_upload(
    *,
    object_key: str,
    expected_prefix: str,
    original_filename: str,
    expected_size_bytes: Any | None = None,
) -> tuple[UploadedVoiceSource, pathlib.Path, tempfile.TemporaryDirectory[str]]:
    key = _validate_key_prefix(object_key, expected_prefix)
    filename = _safe_filename(original_filename)
    storage = get_object_storage()

    try:
        metadata = storage.metadata(key)
    except Exception as exc:
        raise VoiceSourceUploadNotReady(
            "The direct upload is not complete or the temporary object is unavailable."
        ) from exc

    actual_size = int(metadata.size or 0)
    if actual_size <= 0:
        raise VoiceSourceUploadNotReady("The uploaded voice-source object is empty.")

    maximum = max_raw_upload_bytes()
    if actual_size > maximum:
        storage.delete(key)
        raise VoiceSourceUploadTooLarge(
            f"The uploaded source is {actual_size / (1024 * 1024):.1f} MB and exceeds "
            f"the configured raw-upload limit of {maximum / (1024 * 1024):.0f} MB."
        )

    if expected_size_bytes not in {None, ""}:
        expected_size = _validate_size(expected_size_bytes)
        if actual_size != expected_size:
            raise VoiceSourceUploadNotReady(
                f"The completed object size ({actual_size} bytes) does not match the selected file "
                f"size ({expected_size} bytes)."
            )

    temp_dir = tempfile.TemporaryDirectory(prefix="smx_voice_source_")
    local_path = pathlib.Path(temp_dir.name) / filename
    storage.download_to_file(key, local_path)

    return (
        UploadedVoiceSource(
            object_key=key,
            original_filename=filename,
            content_type=metadata.content_type or "application/octet-stream",
            size_bytes=actual_size,
        ),
        local_path,
        temp_dir,
    )


def delete_temporary_upload(object_key: str) -> bool:
    try:
        return bool(get_object_storage().delete(object_key))
    except ObjectStorageError:
        return False
