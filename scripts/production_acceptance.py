from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.headers: dict[str, str] = {}

    def json(self):
        return self._payload


class FakeRepository:
    backend_name = "postgres"

    def __init__(self):
        self.workspace_voices: dict[tuple[str, str], dict[str, Any]] = {}
        self.system_voices: dict[str, dict[str, Any]] = {}

    def get_workspace_voice(self, workspace_id, voice_id):
        row = self.workspace_voices.get((workspace_id, voice_id))
        return dict(row) if row else None

    def list_workspace_voices(self, workspace_id):
        return [
            dict(row)
            for (stored_workspace_id, _), row in self.workspace_voices.items()
            if stored_workspace_id == workspace_id and row.get("status", "active") == "active"
        ]

    def upsert_workspace_voice(self, workspace_id, voice_id, record):
        row = dict(record)
        row.update({"workspaceId": workspace_id, "voiceId": voice_id})
        self.workspace_voices[(workspace_id, voice_id)] = row
        return dict(row)

    def delete_workspace_voice(self, workspace_id, voice_id):
        return self.workspace_voices.pop((workspace_id, voice_id), None) is not None

    def get_system_voice(self, voice_id):
        row = self.system_voices.get(voice_id)
        return dict(row) if row else None

    def list_system_voices(self):
        return [dict(row) for row in self.system_voices.values() if row.get("status", "active") == "active"]

    def upsert_system_voice(self, voice_id, record):
        row = dict(record)
        row["voiceId"] = voice_id
        self.system_voices[voice_id] = row
        return dict(row)

    def delete_system_voice(self, voice_id):
        return self.system_voices.pop(voice_id, None) is not None


class FakeObjectStorage:
    backend_name = "memory"

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, key, source_path, *, content_type=""):
        from services.object_storage import StoredObject
        data = pathlib.Path(source_path).read_bytes()
        self.objects[key] = data
        return StoredObject("memory", key, f"memory://{key}", len(data), content_type)

    def read_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        return self.objects.pop(key, None) is not None


def check_provider_contract() -> None:
    import ali_voice_clone

    with tempfile.TemporaryDirectory() as temp_dir:
        source = pathlib.Path(temp_dir) / "Bobga.wav"
        source.write_bytes(b"RIFF-test-wave")
        captured: dict[str, Any] = {}

        def fake_post(url, *, headers, json, timeout):
            captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse({"output": {"voice": "provider_voice_123"}})

        env = {
            "SINGAPORE_API_KEY": "test-secret-not-printed",
            "SINGAPORE_WORKSPACE_ID": "workspace-test",
        }
        with patch.dict(os.environ, env, clear=False), patch("ali_voice_clone.requests.post", fake_post):
            voice_id = ali_voice_clone.create_voice(
                str(source),
                target_model="qwen3-tts-vc-2026-01-22",
                preferred_name="Bobga Voice",
                audio_mime_type="audio/wav",
            )

        assert voice_id == "provider_voice_123"
        assert captured["url"].endswith("/services/audio/tts/customization")
        assert captured["headers"]["Authorization"].startswith("Bearer ")
        payload = captured["json"]
        assert payload["model"] == "qwen-voice-enrollment"
        assert payload["input"]["action"] == "create"
        assert payload["input"]["audio"]["data"].startswith("data:audio/wav;base64,")
        preferred = payload["input"]["preferred_name"]
        assert len(preferred) <= 16
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", preferred)


def check_durable_workspace_voice() -> None:
    import services.clone_voice_workspace as workspace_service
    import services.object_storage as object_storage

    repository = FakeRepository()
    storage = FakeObjectStorage()

    with tempfile.TemporaryDirectory() as temp_dir:
        old_root = workspace_service.WORKSPACES_DIR
        workspace_service.WORKSPACES_DIR = pathlib.Path(temp_dir) / "workspaces"
        try:
            with patch.object(workspace_service, "get_persistence_repository", lambda: repository), patch.object(
                object_storage, "get_object_storage", lambda: storage
            ):
                paths = workspace_service.get_workspace("ws_fb_test")
                parameter_path = workspace_service.stable_parameter_path(paths, "bobga")
                preview_path = workspace_service.stable_preview_path(paths, "bobga")
                parameter_path.write_text("provider_voice_123", encoding="utf-8")
                preview_path.write_bytes(b"RIFF-preview")

                workspace_service.save_voice_metadata(
                    paths,
                    "bobga",
                    "Bobga",
                    "M",
                    source_type="upload",
                    parameter_path=parameter_path,
                    preview_path=preview_path,
                    parameter_created=True,
                    preview_created=True,
                )

                parameter_path.unlink()
                preview_path.unlink()
                metadata_path = workspace_service.metadata_path(paths, "bobga")
                if metadata_path.exists():
                    metadata_path.unlink()

                voices = workspace_service.list_workspace_voice_parameters(paths)
                assert len(voices) == 1
                assert voices[0]["voiceId"] == "bobga"
                assert voices[0]["previewUrl"].endswith("/bobga_preview.wav")

                provider_id, hydrated_path = workspace_service.load_workspace_voice_parameter(paths, "bobga")
                assert provider_id == "provider_voice_123"
                assert hydrated_path.exists()
                assert storage.exists("workspaces/ws_fb_test/voice_previews/bobga_preview.wav")
        finally:
            workspace_service.WORKSPACES_DIR = old_root


def check_durable_system_voice_catalog() -> None:
    import services.clone_voice_system as system_service
    import services.object_storage as object_storage

    repository = FakeRepository()
    storage = FakeObjectStorage()

    with tempfile.TemporaryDirectory() as temp_dir:
        base = pathlib.Path(temp_dir) / "voices"
        attrs = {
            "SYSTEM_VOICES_DIR": system_service.SYSTEM_VOICES_DIR,
            "SYSTEM_PARAMS_DIR": system_service.SYSTEM_PARAMS_DIR,
            "SYSTEM_PREVIEWS_DIR": system_service.SYSTEM_PREVIEWS_DIR,
            "SYSTEM_METADATA_DIR": system_service.SYSTEM_METADATA_DIR,
            "SYSTEM_TMP_DIR": system_service.SYSTEM_TMP_DIR,
        }
        system_service.SYSTEM_VOICES_DIR = base
        system_service.SYSTEM_PARAMS_DIR = base / "params"
        system_service.SYSTEM_PREVIEWS_DIR = base / "previews"
        system_service.SYSTEM_METADATA_DIR = base / "metadata"
        system_service.SYSTEM_TMP_DIR = base / "tmp" / "source_audio"
        try:
            with patch.object(system_service, "get_persistence_repository", lambda: repository), patch.object(
                object_storage, "get_object_storage", lambda: storage
            ):
                system_service.ensure_system_dirs()
                parameter_path = system_service.system_parameter_path("narrator")
                preview_path = system_service.system_preview_path("narrator")
                parameter_path.write_text("provider_system_voice", encoding="utf-8")
                preview_path.write_bytes(b"RIFF-system-preview")
                system_service._save_system_metadata(
                    "narrator",
                    "Narrator",
                    "F",
                    parameter_path=parameter_path,
                    preview_path=preview_path,
                )
                parameter_path.unlink()
                preview_path.unlink()
                local_meta = system_service.system_metadata_path("narrator")
                if local_meta.exists():
                    local_meta.unlink()

                voices = system_service.list_system_voices_payload()
                assert len(voices) == 1
                assert voices[0]["voiceId"] == "narrator"
                assert voices[0]["previewUrl"].endswith("/narrator_preview.wav")
                provider_id, hydrated = system_service.load_system_voice_parameter("narrator")
                assert provider_id == "provider_system_voice"
                assert hydrated.exists()
                assert storage.exists("system_voices/previews/narrator_preview.wav")
        finally:
            for name, value in attrs.items():
                setattr(system_service, name, value)


def check_flask_json_contract() -> None:
    os.environ["AUTH_PROVIDER"] = ""
    os.environ["DEV_AUTH_ENABLED"] = "true"
    os.environ["DEV_AUTH_ROLE"] = "admin"
    os.environ["DEV_AUTH_USER_ID"] = "dev_admin"
    os.environ["DEV_AUTH_WORKSPACE_ID"] = "mock_user_001"
    os.environ["PERSISTENCE_BACKEND"] = "json"
    os.environ["OBJECT_STORAGE_BACKEND"] = "local"

    import app as app_module
    import controllers.clone_voice_controller as controller
    import services.clone_voice_workspace as workspace_service

    with tempfile.TemporaryDirectory() as temp_dir:
        old_root = workspace_service.WORKSPACES_DIR
        workspace_service.WORKSPACES_DIR = pathlib.Path(temp_dir) / "workspaces"
        os.environ["LOCAL_OBJECT_STORAGE_DIR"] = str(pathlib.Path(temp_dir) / "objects")

        def fake_prepare(input_path, output_path):
            return {
                "path": pathlib.Path(input_path),
                "durationSeconds": 1.0,
                "targetSeconds": 20,
                "trimmed": False,
                "autoTrimEnabled": True,
            }

        def fake_preview(_voice_parameter, preview_path):
            pathlib.Path(preview_path).write_bytes(b"RIFF-preview")

        headers = {
            "X-Dev-Role": "admin",
            "X-User-Id": "dev_admin",
            "X-Workspace-Id": "mock_user_001",
        }
        try:
            with patch.object(controller, "prepare_voice_source_audio", fake_prepare), patch.object(
                controller, "create_voice_parameter", lambda *_args, **_kwargs: "provider_voice_route"
            ), patch.object(controller, "_generate_standard_preview", fake_preview), patch.object(
                controller, "assert_workspace_can_spend", lambda *_args, **_kwargs: None
            ):
                client = app_module.app.test_client()
                response = client.post(
                    "/api/clone-voice/voices/from-source",
                    data={
                        "workspaceId": "mock_user_001",
                        "sourceMode": "upload",
                        "voiceDisplayName": "Route Voice",
                        "gender": "M",
                        "audio": (io.BytesIO(b"RIFF-route-wave"), "route.wav"),
                    },
                    content_type="multipart/form-data",
                    headers=headers,
                )
                assert response.status_code == 200
                assert response.content_type.startswith("application/json")
                assert response.get_json()["ok"] is True

                missing = client.get("/api/this-route-does-not-exist", headers=headers)
                assert missing.status_code == 404
                assert missing.content_type.startswith("application/json")
                assert missing.get_json()["ok"] is False
        finally:
            workspace_service.WORKSPACES_DIR = old_root


def check_frontend_contract() -> None:
    client_js = (ROOT / "frontend" / "clone_voice" / "client.js").read_text(encoding="utf-8")
    assert "async function parseApiResponse" in client_js
    assert "await response.json()" not in client_js

    save_start = client_js.index("async function saveClientVoice")
    save_end = client_js.index("function selectedSavedVoice", save_start)
    save_block = client_js[save_start:save_end]
    assert "audioPlayer.src" not in save_block

    replace_start = client_js.index("async function replaceSelectedSavedVoiceSource")
    replace_end = client_js.index("async function deleteSavedVoice", replace_start)
    replace_block = client_js[replace_start:replace_end]
    assert "audioPlayer.src" not in replace_block

    narration_start = client_js.index("async function submitForm")
    narration_end = client_js.index('sourceModeInputs.forEach', narration_start)
    narration_block = client_js[narration_start:narration_end]
    assert "audioPlayer.src" in narration_block

    node = subprocess.run(
        ["node", "--check", str(ROOT / "frontend" / "clone_voice" / "client.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    if node.returncode != 0:
        raise AssertionError(node.stderr or node.stdout)


def check_schema_and_package() -> None:
    schema = (ROOT / "sql" / "postgres_schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS workspace_voices" in schema
    assert "CREATE TABLE IF NOT EXISTS system_voices" in schema
    assert (ROOT / "ali_voice_clone.py").exists()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--timeout 900" in dockerfile
    assert (ROOT / ".dockerignore").exists()


def main() -> None:
    checks = [
        ("Alibaba provider contract", check_provider_contract),
        ("Durable workspace voice catalog", check_durable_workspace_voice),
        ("Durable system voice catalog", check_durable_system_voice_catalog),
        ("Flask save-voice JSON contract", check_flask_json_contract),
        ("Frontend response/player contract", check_frontend_contract),
        ("Schema and deployment package", check_schema_and_package),
    ]

    print("SyntaxMatrix production acceptance")
    print("==================================")
    for label, check in checks:
        check()
        print(f"{label}: passed")
    print("Production acceptance: PASSED")


if __name__ == "__main__":
    main()
