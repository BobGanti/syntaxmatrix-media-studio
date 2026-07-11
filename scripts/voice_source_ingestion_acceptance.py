from __future__ import annotations

import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"passed: {message}")


def main() -> None:
    python_files = [
        ROOT / "services" / "clone_voice_audio_policy.py",
        ROOT / "services" / "object_storage.py",
        ROOT / "services" / "voice_source_ingestion.py",
        ROOT / "services" / "clone_voice_system.py",
        ROOT / "controllers" / "clone_voice_controller.py",
        ROOT / "services" / "subscription_enforcement.py",
    ]
    for path in python_files:
        py_compile.compile(str(path), doraise=True)
    check(True, "Python files compile")

    config = json.loads((ROOT / "config" / "clone_voice_settings.json").read_text(encoding="utf-8"))
    check(config.get("target_voice_source_seconds") == 20, "D is explicit configuration")
    check(config.get("auto_trim_voice_source") is True, "backend auto-trim is enabled")
    check(config.get("max_raw_source_seconds") == 0, "raw source duration cap is disabled by configuration")

    policy_source = (ROOT / "services" / "clone_voice_audio_policy.py").read_text(encoding="utf-8")
    for forbidden in ["DEFAULT_MAX_VOICE_SOURCE_SECONDS", "MIN_MAX_VOICE_SOURCE_SECONDS", "MAX_MAX_VOICE_SOURCE_SECONDS"]:
        check(forbidden not in policy_source, f"hidden hardcode removed: {forbidden}")

    client_source = (ROOT / "frontend" / "clone_voice" / "client.js").read_text(encoding="utf-8")
    admin_source = (ROOT / "frontend" / "clone_voice" / "admin.js").read_text(encoding="utf-8")
    combined = client_source + "\n" + admin_source
    check("source-uploads/workspace/session" in client_source, "client uses direct workspace upload session")
    check("source-uploads/system/session" in admin_source, "admin uses direct system upload session")
    check("file.arrayBuffer" not in combined, "browser does not load whole audio into ArrayBuffer")
    check("OfflineAudioContext" not in combined, "browser does not trim or re-encode audio")

    controller_source = (ROOT / "controllers" / "clone_voice_controller.py").read_text(encoding="utf-8")
    for route in [
        "/api/clone-voice/source-uploads/workspace/session",
        "/api/clone-voice/source-uploads/workspace/complete",
        "/api/clone-voice/source-uploads/workspace/replace",
        "/api/clone-voice/source-uploads/system/session",
        "/api/clone-voice/source-uploads/system/complete",
    ]:
        check(route in controller_source, f"route exists: {route}")

    if shutil.which("node"):
        for path in [ROOT / "frontend" / "clone_voice" / "client.js", ROOT / "frontend" / "clone_voice" / "admin.js"]:
            subprocess.run(["node", "--check", str(path)], check=True)
        check(True, "frontend JavaScript syntax")

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        from services.clone_voice_audio_policy import (
            VoiceSourceDurationError,
            prepare_voice_source_audio,
            voice_source_duration_seconds,
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "source.wav"
            output = temp_path / "trimmed.wav"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-ac", "1", str(source),
            ], check=True)
            os.environ["CLONE_VOICE_MAX_SOURCE_SECONDS"] = "2"
            os.environ["CLONE_VOICE_AUTO_TRIM_SOURCE"] = "1"
            os.environ["CLONE_VOICE_MAX_RAW_SOURCE_SECONDS"] = "0"
            prepared = prepare_voice_source_audio(source, output)
            check(prepared["trimmed"] is True, "backend trims a source longer than D")
            check(voice_source_duration_seconds(pathlib.Path(prepared["path"])) <= 2.1, "trimmed source is at most D")
            os.environ["CLONE_VOICE_AUTO_TRIM_SOURCE"] = "0"
            try:
                prepare_voice_source_audio(source, output)
            except VoiceSourceDurationError:
                check(True, "disabled auto-trim returns a controlled duration error")
            else:
                raise AssertionError("Expected VoiceSourceDurationError")

    print("VOICE SOURCE INGESTION ACCEPTANCE: PASSED")


if __name__ == "__main__":
    main()
