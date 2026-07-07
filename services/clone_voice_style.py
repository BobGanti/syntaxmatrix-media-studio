from __future__ import annotations

import importlib
import pathlib
from typing import Any


NARRATION_STYLE_OPTIONS = {
    "natural": {
        "key": "natural",
        "label": "Natural",
        "display": "Natural",
        "providerStyle": None,
    },
    "clear_presenter": {
        "key": "clear_presenter",
        "label": "Clear / Presenter",
        "display": "Clear / Presenter",
        "providerStyle": "clear_presenter",
    },
    "dramatic": {
        "key": "dramatic",
        "label": "Dramatic",
        "display": "Dramatic",
        "providerStyle": "dramatic",
    },
    "calm": {
        "key": "calm",
        "label": "Calm",
        "display": "Calm",
        "providerStyle": "calm",
    },
    "energetic": {
        "key": "energetic",
        "label": "Energetic",
        "display": "Energetic",
        "providerStyle": "energetic",
    },
}


def normalize_narration_style_key(value: Any) -> str:
    key = str(value or "natural").strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "natural": "natural",
        "default": "natural",
        "normal": "natural",

        "clear": "clear_presenter",
        "presenter": "clear_presenter",
        "clear_presenter": "clear_presenter",
        "clear/presenter": "clear_presenter",
        "clear__presenter": "clear_presenter",

        "dramatic": "dramatic",
        "drama": "dramatic",

        "calm": "calm",
        "soft": "calm",

        "energetic": "energetic",
        "energy": "energetic",
        "lively": "energetic",
    }

    return aliases.get(key, "natural")


def narration_style_payload(value: Any) -> dict[str, Any]:
    key = normalize_narration_style_key(value)
    option = NARRATION_STYLE_OPTIONS[key]

    return {
        "key": option["key"],
        "label": option["label"],
        "display": option["display"],
        "providerStyle": option["providerStyle"],
    }


def _base_provider_generate(voice_parameter: str, prompt: str, output_path: pathlib.Path) -> None:
    provider = importlib.import_module("services.clone_voice_provider")
    provider.generate_narration_to_file(voice_parameter, prompt, output_path)


def _provider_style_hook():
    provider = importlib.import_module("services.clone_voice_provider")

    for name in [
        "generate_narration_to_file_with_style",
        "generate_narration_to_file_with_options",
    ]:
        candidate = getattr(provider, name, None)

        if callable(candidate):
            return candidate

    return None


def generate_narration_to_file_with_style(
    voice_parameter: str,
    prompt: str,
    output_path: pathlib.Path,
    style_value: Any = "natural",
) -> dict[str, Any]:
    """Generate narration with a provider-safe style boundary.

    This function deliberately does not prepend style instructions into `prompt`,
    because those instructions could be spoken by the TTS provider.

    If the provider exposes a real style/options hook, we use it.
    Otherwise we generate normal narration and honestly report styleApplied=False
    for non-natural styles.
    """
    style = narration_style_payload(style_value)
    style_key = style["key"]

    if style_key == "natural":
        _base_provider_generate(voice_parameter, prompt, output_path)

        return {
            **style,
            "styleApplied": True,
            "styleReason": "natural_provider_default",
        }

    hook = _provider_style_hook()

    if hook:
        try:
            hook(
                voice_parameter=voice_parameter,
                prompt=prompt,
                output_path=output_path,
                style_key=style_key,
                style_payload=style,
            )
        except TypeError:
            hook(voice_parameter, prompt, output_path, style)

        return {
            **style,
            "styleApplied": True,
            "styleReason": "provider_style_hook",
        }

    _base_provider_generate(voice_parameter, prompt, output_path)

    return {
        **style,
        "styleApplied": False,
        "styleReason": "provider_does_not_support_style_control",
    }
