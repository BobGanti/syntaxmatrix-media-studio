from __future__ import annotations

import pathlib
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parent.parent
SYSTEM_PARAMS_DIR = ROOT / "voices" / "params"
SYSTEM_PREVIEWS_DIR = ROOT / "voices" / "previews"


@dataclass(frozen=True)
class SystemVoice:
    voice_id: str
    display_name: str
    param_path: pathlib.Path
    preview_path: pathlib.Path | None


def _display_name(voice_id: str) -> str:
    return voice_id.replace("_", " ").replace("-", " ").strip().title() or voice_id


def _find_preview(voice_id: str) -> pathlib.Path | None:
    for ext in ("wav", "mp3", "m4a", "ogg", "webm"):
        for filename in (f"{voice_id}_preview.{ext}", f"{voice_id}.{ext}"):
            candidate = SYSTEM_PREVIEWS_DIR / filename
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def list_system_voices() -> list[SystemVoice]:
    SYSTEM_PARAMS_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEM_PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    voices: list[SystemVoice] = []
    for param_path in sorted(SYSTEM_PARAMS_DIR.glob("*.txt"), key=lambda p: p.name.lower()):
        voice_id = param_path.stem
        voices.append(SystemVoice(
            voice_id=voice_id,
            display_name=_display_name(voice_id),
            param_path=param_path,
            preview_path=_find_preview(voice_id),
        ))
    return voices


def list_system_voices_payload() -> list[dict[str, str | None]]:
    payload: list[dict[str, str | None]] = []
    for voice in list_system_voices():
        payload.append({
            "voiceId": voice.voice_id,
            "displayName": voice.display_name,
            "previewUrl": f"/media/voices/previews/{voice.preview_path.name}" if voice.preview_path else None,
        })
    return payload


def load_system_voice_parameter(voice_id: str) -> tuple[str, pathlib.Path]:
    safe = pathlib.Path(voice_id).name
    param_path = SYSTEM_PARAMS_DIR / f"{safe}.txt"
    if not param_path.exists() or not param_path.is_file():
        raise FileNotFoundError(f"System voice parameter not found: {safe}")
    value = param_path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"System voice parameter file is empty: {param_path}")
    return value, param_path
