from __future__ import annotations

import mimetypes
import os
import pathlib
import uuid
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_OBJECT_ROOT = ROOT / "object_storage"


class ObjectStorageError(RuntimeError):
    pass


class ObjectStorageNotConfigured(ObjectStorageError):
    pass


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def object_storage_backend() -> str:
    backend = _clean(os.getenv("OBJECT_STORAGE_BACKEND"), "local").lower()

    if backend not in {"local", "gcs"}:
        return "local"

    return backend


def _local_object_root() -> pathlib.Path:
    configured = _clean(os.getenv("LOCAL_OBJECT_STORAGE_DIR"))

    if configured:
        path = pathlib.Path(configured)
        if not path.is_absolute():
            path = ROOT / path
        return path

    return DEFAULT_LOCAL_OBJECT_ROOT


def _gcs_bucket_name() -> str:
    return _clean(os.getenv("GCS_BUCKET_NAME"))


def _normalise_key(key: str) -> str:
    key = _clean(key).replace("\\", "/").lstrip("/")

    if not key:
        raise ObjectStorageError("Object key is required.")

    parts = [part for part in key.split("/") if part not in {"", "."}]

    if not parts or any(part == ".." for part in parts):
        raise ObjectStorageError(f"Unsafe object key: {key!r}")

    return "/".join(parts)


def _guess_content_type(key: str, fallback: str = "application/octet-stream") -> str:
    guessed, _encoding = mimetypes.guess_type(key)
    return guessed or fallback


def _load_gcs_storage_module():
    try:
        from google.cloud import storage  # type: ignore

        return storage
    except Exception as exc:
        raise ObjectStorageNotConfigured(
            "google-cloud-storage is not installed. Install it with: pip install google-cloud-storage"
        ) from exc


@dataclass(frozen=True)
class StoredObject:
    backend: str
    key: str
    uri: str
    size: int | None = None
    content_type: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "key": self.key,
            "uri": self.uri,
            "size": self.size,
            "contentType": self.content_type,
        }


class BaseObjectStorage:
    backend_name = "base"

    def save_bytes(self, key: str, data: bytes, *, content_type: str = "") -> StoredObject:
        raise NotImplementedError

    def upload_file(self, key: str, source_path: str | pathlib.Path, *, content_type: str = "") -> StoredObject:
        raise NotImplementedError

    def read_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        raise NotImplementedError


class LocalObjectStorage(BaseObjectStorage):
    backend_name = "local"

    def __init__(self, root: pathlib.Path | None = None):
        self.root = root or _local_object_root()

    def _path_for_key(self, key: str) -> pathlib.Path:
        safe_key = _normalise_key(key)
        path = (self.root / safe_key).resolve()
        root = self.root.resolve()

        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ObjectStorageError(f"Unsafe object key: {key!r}") from exc

        return path

    def save_bytes(self, key: str, data: bytes, *, content_type: str = "") -> StoredObject:
        if not isinstance(data, (bytes, bytearray)):
            raise ObjectStorageError("data must be bytes.")

        safe_key = _normalise_key(key)
        path = self._path_for_key(safe_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))

        return StoredObject(
            backend=self.backend_name,
            key=safe_key,
            uri=f"file://{path}",
            size=len(data),
            content_type=content_type or _guess_content_type(safe_key),
        )

    def upload_file(self, key: str, source_path: str | pathlib.Path, *, content_type: str = "") -> StoredObject:
        source = pathlib.Path(source_path)

        if not source.exists() or not source.is_file():
            raise ObjectStorageError(f"Source file not found: {source}")

        safe_key = _normalise_key(key)
        path = self._path_for_key(safe_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        path.write_bytes(data)

        return StoredObject(
            backend=self.backend_name,
            key=safe_key,
            uri=f"file://{path}",
            size=len(data),
            content_type=content_type or _guess_content_type(safe_key),
        )

    def read_bytes(self, key: str) -> bytes:
        path = self._path_for_key(key)

        if not path.exists():
            raise ObjectStorageError(f"Object not found: {_normalise_key(key)}")

        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for_key(key).exists()

    def delete(self, key: str) -> bool:
        path = self._path_for_key(key)

        if not path.exists():
            return False

        path.unlink()
        return True

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "ready": True,
            "localRoot": str(self.root.relative_to(ROOT)) if self.root.is_relative_to(ROOT) else str(self.root),
            "notes": [
                "Local object storage is for development only.",
                "Production Cloud Run must use OBJECT_STORAGE_BACKEND=gcs.",
            ],
        }


class GcsObjectStorage(BaseObjectStorage):
    backend_name = "gcs"

    def __init__(self, bucket_name: str | None = None):
        self.bucket_name = _clean(bucket_name or _gcs_bucket_name())

        if not self.bucket_name:
            raise ObjectStorageNotConfigured("GCS_BUCKET_NAME is not configured.")

        storage = _load_gcs_storage_module()
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _blob(self, key: str):
        return self.bucket.blob(_normalise_key(key))

    def save_bytes(self, key: str, data: bytes, *, content_type: str = "") -> StoredObject:
        if not isinstance(data, (bytes, bytearray)):
            raise ObjectStorageError("data must be bytes.")

        safe_key = _normalise_key(key)
        content_type = content_type or _guess_content_type(safe_key)
        blob = self._blob(safe_key)
        blob.upload_from_string(bytes(data), content_type=content_type)

        return StoredObject(
            backend=self.backend_name,
            key=safe_key,
            uri=f"gs://{self.bucket_name}/{safe_key}",
            size=len(data),
            content_type=content_type,
        )

    def upload_file(self, key: str, source_path: str | pathlib.Path, *, content_type: str = "") -> StoredObject:
        source = pathlib.Path(source_path)

        if not source.exists() or not source.is_file():
            raise ObjectStorageError(f"Source file not found: {source}")

        safe_key = _normalise_key(key)
        content_type = content_type or _guess_content_type(safe_key)
        blob = self._blob(safe_key)
        blob.upload_from_filename(str(source), content_type=content_type)

        return StoredObject(
            backend=self.backend_name,
            key=safe_key,
            uri=f"gs://{self.bucket_name}/{safe_key}",
            size=source.stat().st_size,
            content_type=content_type,
        )

    def read_bytes(self, key: str) -> bytes:
        return self._blob(key).download_as_bytes()

    def exists(self, key: str) -> bool:
        return bool(self._blob(key).exists())

    def delete(self, key: str) -> bool:
        blob = self._blob(key)

        if not blob.exists():
            return False

        blob.delete()
        return True

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "ready": True,
            "bucket": self.bucket_name,
            "bucketUri": f"gs://{self.bucket_name}",
            "notes": [
                "Cloud Storage is configured for production object storage.",
                "Cloud Run service account must have permission to read/write this bucket.",
            ],
        }


def get_object_storage() -> BaseObjectStorage:
    backend = object_storage_backend()

    if backend == "gcs":
        return GcsObjectStorage()

    return LocalObjectStorage()


def object_storage_status_payload() -> dict[str, Any]:
    backend = object_storage_backend()
    gcs_driver = {
        "installed": False,
        "package": "google-cloud-storage",
        "install": "pip install google-cloud-storage",
    }

    try:
        storage = _load_gcs_storage_module()
        gcs_driver = {
            "installed": True,
            "package": "google-cloud-storage",
            "version": getattr(storage, "__version__", ""),
        }
    except Exception as exc:
        gcs_driver["error"] = str(exc)

    try:
        storage_impl = get_object_storage()
        impl_status = storage_impl.status()
        ready = bool(impl_status.get("ready"))
        error = ""
    except Exception as exc:
        impl_status = {}
        ready = False
        error = str(exc)

    return {
        "backend": backend,
        "ready": ready,
        "cloudRunReady": backend == "gcs" and ready,
        "gcsBucketConfigured": bool(_gcs_bucket_name()),
        "gcsDriver": gcs_driver,
        "localObjectRoot": str(_local_object_root().relative_to(ROOT)) if _local_object_root().is_relative_to(ROOT) else str(_local_object_root()),
        "implementation": impl_status,
        "error": error,
        "requiredProductionEnv": {
            "OBJECT_STORAGE_BACKEND": "gcs",
            "GCS_BUCKET_NAME": "your-production-bucket-name",
        },
    }


def object_key_for_voice_source(workspace_id: str, filename: str) -> str:
    return _normalise_key(f"workspaces/{workspace_id}/voice_sources/{filename}")


def object_key_for_voice_preview(workspace_id: str, filename: str) -> str:
    return _normalise_key(f"workspaces/{workspace_id}/voice_previews/{filename}")


def object_key_for_generated_audio(workspace_id: str, filename: str) -> str:
    return _normalise_key(f"workspaces/{workspace_id}/generated_audio/{filename}")


def new_object_filename(suffix: str = "") -> str:
    suffix = _clean(suffix)

    if suffix and not suffix.startswith("."):
        suffix = "." + suffix

    return f"{uuid.uuid4().hex}{suffix}"
