from __future__ import annotations

import mimetypes
import os
import pathlib
from typing import Any

import requests


DEFAULT_MODEL = "qwen3-tts-vc-2026-01-22"


def _credentials() -> tuple[str, str]:
    api_key = os.getenv("SINGAPORE_API_KEY") or os.getenv("ALIBABA_API_KEY") or ""
    workspace_id = os.getenv("SINGAPORE_WORKSPACE_ID") or os.getenv("ALIBABA_WORKSPACE_ID") or ""
    if not api_key or not workspace_id:
        raise RuntimeError("Missing SINGAPORE_API_KEY or SINGAPORE_WORKSPACE_ID in .env")
    return api_key, workspace_id


def create_voice_parameter(source_audio_path: pathlib.Path, audio_mime_type: str | None = None) -> str:
    import ali_voice_clone as voice_feature

    mime = audio_mime_type or mimetypes.guess_type(source_audio_path.name)[0] or "audio/mpeg"

    print("[clone_voice_provider] Creating voice parameter from:", source_audio_path, flush=True)
    print("[clone_voice_provider] audio_mime_type:", mime, flush=True)

    return voice_feature.create_voice(
        str(source_audio_path),
        target_model=DEFAULT_MODEL,
        audio_mime_type=mime,
    )


def _extract_audio_url(response: Any) -> str | None:
    try:
        output = response.get("output", {})
        audio = output.get("audio", {})
        return audio.get("url")
    except Exception:
        return None


def generate_narration_to_file(voice_parameter: str, prompt: str, output_path: pathlib.Path) -> None:
    import dashscope
    import ali_voice_clone as voice_feature

    api_key, workspace_id = _credentials()
    dashscope.base_http_api_url = f"https://{workspace_id}.ap-southeast-1.maas.aliyuncs.com/api/v1"

    print("[clone_voice_provider] Generating narration", flush=True)

    response = voice_feature.clone_voice(
        api_key=api_key,
        model=DEFAULT_MODEL,
        voice=voice_parameter,
        text=prompt,
        stream=False,
    )

    audio_url = _extract_audio_url(response)
    if not audio_url:
        raise RuntimeError("Provider response did not include output.audio.url")

    remote = requests.get(audio_url, timeout=180)
    remote.raise_for_status()
    output_path.write_bytes(remote.content)
