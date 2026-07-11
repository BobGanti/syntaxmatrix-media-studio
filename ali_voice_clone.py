from __future__ import annotations

import base64
import mimetypes
import os
import pathlib
import re
import secrets
import time
from typing import Any

import requests


DEFAULT_TARGET_MODEL = "qwen3-tts-vc-2026-01-22"
ENROLLMENT_MODEL = "qwen-voice-enrollment"
DEFAULT_TIMEOUT_SECONDS = 180


class AlibabaVoiceError(RuntimeError):
    """Safe provider error that never includes credentials."""


def _clean(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _api_key(explicit: str | None = None) -> str:
    value = _clean(
        explicit
        or os.getenv("SINGAPORE_API_KEY")
        or os.getenv("ALIBABA_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
    )
    if not value:
        raise AlibabaVoiceError("Alibaba voice API key is not configured.")
    return value


def _workspace_id() -> str:
    value = _clean(
        os.getenv("SINGAPORE_WORKSPACE_ID")
        or os.getenv("ALIBABA_WORKSPACE_ID")
    )
    if not value:
        raise AlibabaVoiceError("Alibaba voice workspace ID is not configured.")
    return value


def _api_root() -> str:
    configured = _clean(os.getenv("SINGAPORE_API_BASE_URL") or os.getenv("ALIBABA_API_BASE_URL"))
    if configured:
        return configured.rstrip("/")
    return f"https://{_workspace_id()}.ap-southeast-1.maas.aliyuncs.com/api/v1"


def _enrollment_url() -> str:
    configured = _clean(os.getenv("ALIBABA_VOICE_ENROLLMENT_URL"))
    if configured:
        return configured
    return f"{_api_root()}/services/audio/tts/customization"


def _safe_preferred_name(raw: str | None) -> str:
    """Return a provider-safe, collision-resistant name no longer than 16 chars."""
    base = pathlib.Path(_clean(raw, "smxvoice")).stem
    base = re.sub(r"[^A-Za-z0-9_]", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "smxvoice"
    if not base[0].isalpha():
        base = "v_" + base
    suffix = f"{int(time.time()) % 100000:05d}{secrets.token_hex(1)}"
    max_base = max(1, 16 - len(suffix) - 1)
    return f"{base[:max_base]}_{suffix}"[:16]


def _mime_type(path: pathlib.Path, explicit: str | None = None) -> str:
    value = _clean(explicit)
    if value:
        return value.split(";", 1)[0].strip()
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "audio/wav"


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        request_id = response.headers.get("x-request-id") or response.headers.get("x-dashscope-request-id") or ""
        detail = f" Request ID: {request_id}." if request_id else ""
        raise AlibabaVoiceError(
            f"Alibaba voice service returned HTTP {response.status_code} with an invalid response.{detail}"
        ) from exc

    if not isinstance(data, dict):
        raise AlibabaVoiceError("Alibaba voice service returned an unexpected response.")
    return data


def _provider_error(data: dict[str, Any], status_code: int) -> AlibabaVoiceError:
    request_id = _clean(data.get("request_id") or data.get("requestId"))
    code = _clean(data.get("code") or data.get("error_code"))
    message = _clean(data.get("message") or data.get("error_message"), "Voice provider request failed.")
    pieces = [f"Alibaba voice request failed (HTTP {status_code})"]
    if code:
        pieces.append(f"code={code}")
    pieces.append(message)
    if request_id:
        pieces.append(f"requestId={request_id}")
    return AlibabaVoiceError("; ".join(pieces))


def create_voice(
    audio_path: str,
    *,
    target_model: str = DEFAULT_TARGET_MODEL,
    preferred_name: str | None = None,
    audio_mime_type: str | None = None,
    api_key: str | None = None,
) -> str:
    """Create an Alibaba voice identity and return its provider voice ID."""
    path = pathlib.Path(audio_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Voice source file was not found: {path.name}")

    audio_bytes = path.read_bytes()
    if not audio_bytes:
        raise AlibabaVoiceError("Voice source file is empty.")

    mime = _mime_type(path, audio_mime_type)
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    payload = {
        "model": ENROLLMENT_MODEL,
        "input": {
            "action": "create",
            "target_model": _clean(target_model, DEFAULT_TARGET_MODEL),
            "preferred_name": _safe_preferred_name(preferred_name or path.stem),
            "audio": {"data": f"data:{mime};base64,{encoded}"},
        },
    }

    try:
        response = requests.post(
            _enrollment_url(),
            headers={
                "Authorization": f"Bearer {_api_key(api_key)}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise AlibabaVoiceError(f"Could not reach Alibaba voice service: {exc}") from exc

    data = _json_response(response)
    if not response.ok:
        raise _provider_error(data, response.status_code)

    output = data.get("output")
    voice_id = _clean(output.get("voice") if isinstance(output, dict) else "")
    if not voice_id:
        raise _provider_error(data, response.status_code)
    return voice_id


def clone_voice(
    *,
    api_key: str,
    model: str,
    voice: str,
    text: str,
    stream: bool = False,
):
    """Generate speech using a previously enrolled provider voice identity."""
    voice = _clean(voice)
    text = _clean(text)
    if not voice:
        raise AlibabaVoiceError("A provider voice identity is required.")
    if not text:
        raise AlibabaVoiceError("Narration text is required.")

    try:
        import dashscope  # type: ignore
    except Exception as exc:
        raise AlibabaVoiceError("The dashscope package is not installed.") from exc

    try:
        return dashscope.MultiModalConversation.call(
            api_key=_api_key(api_key),
            model=_clean(model, DEFAULT_TARGET_MODEL),
            text=text,
            voice=voice,
            stream=bool(stream),
        )
    except Exception as exc:
        raise AlibabaVoiceError(f"Alibaba narration generation failed: {exc}") from exc
