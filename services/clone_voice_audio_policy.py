from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess


ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "clone_voice_settings.json"

DEFAULT_MAX_VOICE_SOURCE_SECONDS = 20
MIN_MAX_VOICE_SOURCE_SECONDS = 5
MAX_MAX_VOICE_SOURCE_SECONDS = 120


def _safe_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            return fallback
        return parsed
    except Exception:
        return fallback


def _clamp_duration(value: int) -> int:
    return max(MIN_MAX_VOICE_SOURCE_SECONDS, min(MAX_MAX_VOICE_SOURCE_SECONDS, int(value)))


def ensure_default_settings_file() -> pathlib.Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "max_voice_source_seconds": DEFAULT_MAX_VOICE_SOURCE_SECONDS
                },
                indent=2
            ),
            encoding="utf-8",
        )

    return CONFIG_PATH


def _read_settings() -> dict:
    ensure_default_settings_file()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print("[clone_voice_audio_policy] Could not read config:", repr(exc), flush=True)

    return {
        "max_voice_source_seconds": DEFAULT_MAX_VOICE_SOURCE_SECONDS
    }


def _write_settings(data: dict) -> pathlib.Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CONFIG_PATH


def get_max_voice_source_seconds() -> int:
    env_value = os.getenv("CLONE_VOICE_MAX_SOURCE_SECONDS")

    if env_value:
        return _clamp_duration(_safe_int(env_value, DEFAULT_MAX_VOICE_SOURCE_SECONDS))

    data = _read_settings()

    return _clamp_duration(_safe_int(data.get("max_voice_source_seconds"), DEFAULT_MAX_VOICE_SOURCE_SECONDS))


def set_max_voice_source_seconds(value: int) -> dict:
    duration = _clamp_duration(_safe_int(value, DEFAULT_MAX_VOICE_SOURCE_SECONDS))
    data = _read_settings()
    data["max_voice_source_seconds"] = duration
    path = _write_settings(data)

    return {
        "maxVoiceSourceSeconds": duration,
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
        "minSeconds": MIN_MAX_VOICE_SOURCE_SECONDS,
        "maxSeconds": MAX_MAX_VOICE_SOURCE_SECONDS,
    }


def settings_payload() -> dict:
    path = ensure_default_settings_file()

    return {
        "maxVoiceSourceSeconds": get_max_voice_source_seconds(),
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
        "minSeconds": MIN_MAX_VOICE_SOURCE_SECONDS,
        "maxSeconds": MAX_MAX_VOICE_SOURCE_SECONDS,
    }


def _ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY", "").strip()

    if configured:
        return configured

    found = shutil.which("ffmpeg")

    if not found:
        raise RuntimeError(
            "ffmpeg is required for Clone Voice audio duration limiting and volume normalization. "
            "Install ffmpeg or set FFMPEG_BINARY."
        )

    return found


def _run_ffmpeg(command: list[str], label: str) -> None:
    print(f"[clone_voice_audio_policy] {label}:", " ".join(command), flush=True)

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if len(stderr) > 1200:
            stderr = stderr[-1200:]
        raise RuntimeError(f"{label} failed: {stderr}")


def limit_audio_to_max_seconds(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    max_seconds: int | None = None,
) -> pathlib.Path:
    max_seconds = int(max_seconds or get_max_voice_source_seconds())

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        _ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-t",
        str(max_seconds),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        str(output_path),
    ]

    _run_ffmpeg(command, f"limit source audio to {max_seconds}s")

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Duration-limited audio was not created: {output_path}")

    return output_path


def normalize_generated_audio_file(audio_path: pathlib.Path) -> pathlib.Path:
    if not audio_path.exists():
        raise FileNotFoundError(f"Generated audio not found for normalization: {audio_path}")

    tmp_path = audio_path.with_name(audio_path.stem + "_normalized" + audio_path.suffix)

    command = [
        _ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(tmp_path),
    ]

    _run_ffmpeg(command, "normalize generated narration volume")

    if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        raise RuntimeError(f"Normalized narration was not created: {tmp_path}")

    tmp_path.replace(audio_path)

    return audio_path



NARRATION_SPEED_OPTIONS = {
    "slower": {
        "key": "slower",
        "label": "Slower",
        "multiplier": 0.80,
    },
    "slow": {
        "key": "slow",
        "label": "Slow",
        "multiplier": 0.90,
    },
    "normal": {
        "key": "normal",
        "label": "Normal",
        "multiplier": 1.00,
    },
    "fast": {
        "key": "fast",
        "label": "Fast",
        "multiplier": 1.10,
    },
    "faster": {
        "key": "faster",
        "label": "Faster",
        "multiplier": 1.20,
    },
}


def normalize_narration_speed_key(value) -> str:
    key = str(value or "normal").strip().lower()

    aliases = {
        "0.8": "slower",
        "0.80": "slower",
        "0.8x": "slower",
        "0.80x": "slower",
        "slower": "slower",

        "0.9": "slow",
        "0.90": "slow",
        "0.9x": "slow",
        "0.90x": "slow",
        "slow": "slow",

        "1": "normal",
        "1.0": "normal",
        "1.00": "normal",
        "1x": "normal",
        "1.0x": "normal",
        "1.00x": "normal",
        "normal": "normal",

        "1.1": "fast",
        "1.10": "fast",
        "1.1x": "fast",
        "1.10x": "fast",
        "fast": "fast",

        "1.2": "faster",
        "1.20": "faster",
        "1.2x": "faster",
        "1.20x": "faster",
        "faster": "faster",
    }

    return aliases.get(key, "normal")


def narration_speed_payload(value) -> dict:
    key = normalize_narration_speed_key(value)
    option = NARRATION_SPEED_OPTIONS[key]

    return {
        "key": option["key"],
        "label": option["label"],
        "multiplier": float(option["multiplier"]),
        "display": f'{option["label"]} ({float(option["multiplier"]):.2f}x)',
    }


def apply_narration_speed_to_file(audio_path: pathlib.Path, speed_value) -> pathlib.Path:
    """Apply user-selected narration speed to the final narration only.

    Voice parameters and standard voice previews are not changed.
    """
    speed = narration_speed_payload(speed_value)
    multiplier = float(speed["multiplier"])

    if abs(multiplier - 1.0) < 0.001:
        print("[clone_voice_audio_policy] Narration speed is normal. No speed adjustment.", flush=True)
        return audio_path

    if not audio_path.exists():
        raise FileNotFoundError(f"Generated audio not found for speed adjustment: {audio_path}")

    tmp_path = audio_path.with_name(audio_path.stem + f"_speed_{speed['key']}" + audio_path.suffix)

    command = [
        _ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-filter:a",
        f"atempo={multiplier:.2f}",
        str(tmp_path),
    ]

    _run_ffmpeg(command, f"apply narration speed {speed['display']}")

    if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        raise RuntimeError(f"Speed-adjusted narration was not created: {tmp_path}")

    tmp_path.replace(audio_path)

    return audio_path
