from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "clone_voice_settings.json"


class VoiceSourcePolicyError(ValueError):
    status_code = 422


class VoiceSourceDurationError(VoiceSourcePolicyError):
    def __init__(self, actual_seconds: float, target_seconds: int):
        self.actual_seconds = float(actual_seconds)
        self.target_seconds = int(target_seconds)
        super().__init__(
            f"Voice source is {self.actual_seconds:.1f} seconds. "
            f"The configured target D is {self.target_seconds} seconds and automatic trimming is disabled. "
            "Trim the source externally or enable automatic trimming."
        )


class VoiceSourceSafetyLimitError(VoiceSourcePolicyError):
    def __init__(self, actual_seconds: float, max_seconds: int):
        self.actual_seconds = float(actual_seconds)
        self.max_seconds = int(max_seconds)
        super().__init__(
            f"Voice source is {self.actual_seconds:.1f} seconds and exceeds the configured raw-source "
            f"safety limit of {self.max_seconds} seconds."
        )


def _safe_int(value: Any, *, name: str, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return parsed


def _safe_bool(value: Any, fallback: bool) -> bool:
    if value is None:
        return fallback
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return fallback


def ensure_default_settings_file() -> pathlib.Path:
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            "Missing config/clone_voice_settings.json. The voice-source duration and upload policy "
            "must be configured explicitly; hidden Python duration bounds are not used."
        )
    return CONFIG_PATH


def _read_settings() -> dict[str, Any]:
    ensure_default_settings_file()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read {CONFIG_PATH}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("config/clone_voice_settings.json must contain a JSON object.")
    return data


def _write_settings(data: dict[str, Any]) -> pathlib.Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return CONFIG_PATH


def voice_source_policy() -> dict[str, Any]:
    data = _read_settings()

    configured_target = data.get("target_voice_source_seconds")
    if configured_target is None:
        configured_target = data.get("max_voice_source_seconds")

    env_target = os.getenv("CLONE_VOICE_MAX_SOURCE_SECONDS")
    target_seconds = _safe_int(
        env_target if env_target not in {None, ""} else configured_target,
        name="target_voice_source_seconds",
    )

    env_auto_trim = os.getenv("CLONE_VOICE_AUTO_TRIM_SOURCE")
    auto_trim = _safe_bool(
        env_auto_trim if env_auto_trim is not None else data.get("auto_trim_voice_source"),
        True,
    )

    env_max_mb = os.getenv("CLONE_VOICE_MAX_RAW_UPLOAD_MB")
    max_raw_upload_mb = _safe_int(
        env_max_mb if env_max_mb not in {None, ""} else data.get("max_raw_upload_mb"),
        name="max_raw_upload_mb",
    )

    env_raw_seconds = os.getenv("CLONE_VOICE_MAX_RAW_SOURCE_SECONDS")
    max_raw_source_seconds = _safe_int(
        env_raw_seconds if env_raw_seconds not in {None, ""} else data.get("max_raw_source_seconds", 0),
        name="max_raw_source_seconds",
        allow_zero=True,
    )

    return {
        "targetVoiceSourceSeconds": target_seconds,
        "autoTrimVoiceSource": auto_trim,
        "maxRawUploadMb": max_raw_upload_mb,
        "maxRawUploadBytes": max_raw_upload_mb * 1024 * 1024,
        "maxRawSourceSeconds": max_raw_source_seconds,
    }


def get_max_voice_source_seconds() -> int:
    return int(voice_source_policy()["targetVoiceSourceSeconds"])


def auto_trim_voice_source_enabled() -> bool:
    return bool(voice_source_policy()["autoTrimVoiceSource"])


def max_raw_upload_bytes() -> int:
    return int(voice_source_policy()["maxRawUploadBytes"])


def set_max_voice_source_seconds(value: int) -> dict[str, Any]:
    duration = _safe_int(value, name="target_voice_source_seconds")
    data = _read_settings()
    data["target_voice_source_seconds"] = duration
    data.pop("max_voice_source_seconds", None)
    path = _write_settings(data)
    return {
        **voice_source_policy(),
        "maxVoiceSourceSeconds": duration,
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
    }


def settings_payload() -> dict[str, Any]:
    path = ensure_default_settings_file()
    policy = voice_source_policy()
    return {
        **policy,
        "maxVoiceSourceSeconds": policy["targetVoiceSourceSeconds"],
        "configPath": str(path.relative_to(ROOT)).replace("\\", "/"),
    }


def _ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg is required. Install ffmpeg or set FFMPEG_BINARY.")
    return found


def _ffprobe_binary() -> str:
    configured = os.getenv("FFPROBE_BINARY", "").strip()
    if configured:
        return configured
    found = shutil.which("ffprobe")
    if not found:
        raise RuntimeError("ffprobe is required. Install ffmpeg/ffprobe or set FFPROBE_BINARY.")
    return found


def _run_ffmpeg(command: list[str], label: str) -> None:
    print(f"[clone_voice_audio_policy] {label}:", " ".join(command), flush=True)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        if len(stderr) > 1200:
            stderr = stderr[-1200:]
        raise RuntimeError(f"{label} failed: {stderr}")


def voice_source_duration_seconds(audio_path: pathlib.Path) -> float:
    audio_path = pathlib.Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Voice source not found: {audio_path}")
    result = subprocess.run(
        [
            _ffprobe_binary(), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Could not inspect voice source duration: {detail}")
    try:
        return max(0.0, float((result.stdout or "0").strip()))
    except Exception as exc:
        raise RuntimeError("Could not parse voice source duration.") from exc


def limit_audio_to_max_seconds(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    max_seconds: int | None = None,
) -> pathlib.Path:
    max_seconds = int(max_seconds or get_max_voice_source_seconds())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path), "-t", str(max_seconds), "-map", "0:a:0",
        "-vn", "-ac", "1", str(output_path),
    ]
    _run_ffmpeg(command, f"limit source audio to {max_seconds}s")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Duration-limited audio was not created: {output_path}")
    return output_path


def prepare_voice_source_audio(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
) -> dict[str, Any]:
    policy = voice_source_policy()
    duration = voice_source_duration_seconds(input_path)
    target = int(policy["targetVoiceSourceSeconds"])
    raw_limit = int(policy["maxRawSourceSeconds"])

    if raw_limit > 0 and duration > raw_limit + 0.05:
        raise VoiceSourceSafetyLimitError(duration, raw_limit)

    if duration <= target + 0.05:
        return {
            "path": pathlib.Path(input_path),
            "durationSeconds": duration,
            "targetSeconds": target,
            "trimmed": False,
            "autoTrimEnabled": bool(policy["autoTrimVoiceSource"]),
        }

    if not policy["autoTrimVoiceSource"]:
        raise VoiceSourceDurationError(duration, target)

    limited = limit_audio_to_max_seconds(input_path, output_path, target)
    return {
        "path": limited,
        "durationSeconds": duration,
        "targetSeconds": target,
        "trimmed": True,
        "autoTrimEnabled": True,
    }


def normalize_generated_audio_file(audio_path: pathlib.Path) -> pathlib.Path:
    if not audio_path.exists():
        raise FileNotFoundError(f"Generated audio not found for normalization: {audio_path}")
    tmp_path = audio_path.with_name(audio_path.stem + "_normalized" + audio_path.suffix)
    command = [
        _ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(audio_path), "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(tmp_path),
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
