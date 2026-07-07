from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()

STYLE = ROOT / "services" / "clone_voice_style.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [CONTROLLER, HTML, CSS, JS, STYLE.parent]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Required files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [STYLE, CONTROLLER, HTML, CSS, JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.step15-style-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

STYLE.write_text(r'''from __future__ import annotations

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
''', encoding="utf-8")

controller = CONTROLLER.read_text(encoding="utf-8")

if "from services.clone_voice_style import generate_narration_to_file_with_style" not in controller:
    controller = controller.replace(
        "from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file",
        '''from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file
from services.clone_voice_style import generate_narration_to_file_with_style''',
        1,
    )

pattern = re.compile(
    r'''def _generate_and_normalize\(voice_parameter: str, prompt: str, workspace, title: str, narration_speed="normal"\):[\s\S]*?return output_path, asset_url, speed_info''',
    re.MULTILINE,
)

replacement = r'''def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str, narration_speed="normal", narration_style="natural"):
    output_path = generated_audio_path(workspace, title)

    style_info = generate_narration_to_file_with_style(
        voice_parameter,
        prompt,
        output_path,
        narration_style,
    )

    speed_info = narration_speed_payload(narration_speed)
    apply_narration_speed_to_file(output_path, speed_info["key"])

    normalize_generated_audio_file(output_path)
    asset_url = workspace_generated_audio_url(workspace, output_path)

    return output_path, asset_url, speed_info, style_info'''

controller, count = pattern.subn(replacement, controller, count=1)

if count != 1 and "style_info = generate_narration_to_file_with_style" not in controller:
    print("ERROR: Could not patch _generate_and_normalize.")
    raise SystemExit(1)

if 'narration_style = request.form.get("narrationStyle", "natural").strip()' not in controller:
    controller = controller.replace(
        'narration_speed = request.form.get("narrationSpeed", "normal").strip()\n',
        'narration_speed = request.form.get("narrationSpeed", "normal").strip()\n            narration_style = request.form.get("narrationStyle", "natural").strip()\n',
    )

controller = controller.replace(
    'output_path, asset_url, speed_info = _generate_and_normalize(',
    'output_path, asset_url, speed_info, style_info = _generate_and_normalize(',
)

controller = controller.replace(
    ', narration_speed)',
    ', narration_speed, narration_style)',
)

if '"narrationStyle": style_info["key"]' not in controller:
    controller = controller.replace(
        '''                    "narrationSpeedDisplay": speed_info["display"],''',
        '''                    "narrationSpeedDisplay": speed_info["display"],
                    "narrationStyle": style_info["key"],
                    "narrationStyleLabel": style_info["label"],
                    "narrationStyleDisplay": style_info["display"],
                    "narrationStyleApplied": style_info["styleApplied"],
                    "narrationStyleReason": style_info["styleReason"],''',
    )

CONTROLLER.write_text(controller, encoding="utf-8")

html = HTML.read_text(encoding="utf-8")

if 'id="narrationStyle"' not in html:
    style_html = r'''
          <label>
            Delivery style
            <select id="narrationStyle">
              <option value="natural" selected>Natural</option>
              <option value="clear_presenter">Clear / Presenter</option>
              <option value="dramatic">Dramatic</option>
              <option value="calm">Calm</option>
              <option value="energetic">Energetic</option>
            </select>
          </label>
'''

    html = re.sub(
        r'''(\s*<label>\s*Narration speed\s*<select id="narrationSpeed">[\s\S]*?</select>\s*</label>)''',
        r'\1' + style_html,
        html,
        count=1,
    )

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=narration-style-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=narration-style-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")

if "Step 15: narration style" not in css:
    css += r'''

/* Step 15: narration style selector */

.narration-top-grid {
  grid-template-columns: minmax(220px, 1fr) 190px 230px;
}

@media (max-width: 900px) {
  .narration-top-grid {
    grid-template-columns: 1fr;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

js = JS.read_text(encoding="utf-8")

if 'const narrationStyle = $("#narrationStyle");' not in js:
    js = js.replace(
        'const narrationSpeed = $("#narrationSpeed");',
        '''const narrationSpeed = $("#narrationSpeed");
  const narrationStyle = $("#narrationStyle");''',
        1,
    )

if "const styleDisplay =" not in js:
    js = js.replace(
        '''  function renderFriendlyResult(data) {
    const rows = [''',
        '''  function renderFriendlyResult(data) {
    const styleDisplay = data.narrationStyleDisplay || data.narrationStyleLabel || "";
    const styleText = (
      data.narrationStyleApplied === false && data.narrationStyle !== "natural"
    )
      ? `${styleDisplay} requested — provider style control unavailable`
      : styleDisplay;

    const rows = [''',
        1,
    )

if '["Delivery style", styleText],' not in js:
    js = js.replace(
        '["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],',
        '''["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],
      ["Delivery style", styleText],''',
        1,
    )

if 'formData.append("narrationStyle"' not in js:
    js = js.replace(
        'formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");',
        '''formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");
    formData.append("narrationStyle", narrationStyle ? narrationStyle.value : "natural");''',
        1,
    )

JS.write_text(js, encoding="utf-8")

py_compile.compile(str(STYLE), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 15 COMPLETE: provider-safe narration style added.")
print()
print("Styles:")
print("  Natural")
print("  Clear / Presenter")
print("  Dramatic")
print("  Calm")
print("  Energetic")
print()
print("Safety rule:")
print("  Style instructions are NOT injected into spoken narration text.")
print()
print("If the provider does not expose a style hook:")
print("  narrationStyleApplied = false")
print("  narrationStyleReason = provider_does_not_support_style_control")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?narration-style=1")
