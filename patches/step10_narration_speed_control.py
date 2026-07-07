from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()

AUDIO_POLICY = ROOT / "services" / "clone_voice_audio_policy.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [AUDIO_POLICY, CONTROLLER, HTML, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step10-speed-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# Audio policy: add narration speed post-processing.
# -------------------------------------------------------------------
audio_policy = AUDIO_POLICY.read_text(encoding="utf-8")

if "NARRATION_SPEED_OPTIONS" not in audio_policy:
    audio_policy += r'''


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
'''

AUDIO_POLICY.write_text(audio_policy, encoding="utf-8")

# -------------------------------------------------------------------
# Controller: accept speed and apply to final narration only.
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

if "apply_narration_speed_to_file" not in controller:
    controller = controller.replace(
        "normalize_generated_audio_file,\n",
        "normalize_generated_audio_file,\n    apply_narration_speed_to_file,\n    narration_speed_payload,\n",
        1,
    )

controller = re.sub(
    r'''def _generate_and_normalize\(voice_parameter: str, prompt: str, workspace, title: str\):[\s\S]*?return output_path, asset_url''',
    r'''def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str, narration_speed="normal"):
    output_path = generated_audio_path(workspace, title)
    generate_narration_to_file(voice_parameter, prompt, output_path)

    speed_info = narration_speed_payload(narration_speed)
    apply_narration_speed_to_file(output_path, speed_info["key"])

    normalize_generated_audio_file(output_path)
    asset_url = workspace_generated_audio_url(workspace, output_path)

    return output_path, asset_url, speed_info''',
    controller,
    count=1,
)

if 'narration_speed = request.form.get("narrationSpeed", "normal").strip()' not in controller:
    controller = controller.replace(
        '''            source_mode = request.form.get("sourceMode", "upload").strip().lower()
            audio_file = request.files.get("audio")''',
        '''            source_mode = request.form.get("sourceMode", "upload").strip().lower()
            narration_speed = request.form.get("narrationSpeed", "normal").strip()
            audio_file = request.files.get("audio")''',
        1,
    )

# Add speed to saved/system routes.
controller = controller.replace(
    '''            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)

            if not title:''',
    '''            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            narration_speed = request.form.get("narrationSpeed", "normal").strip()

            if not title:''',
    2,
)

controller = controller.replace(
    '''output_path, asset_url = _generate_and_normalize(voice_parameter, prompt, workspace, title)''',
    '''output_path, asset_url, speed_info = _generate_and_normalize(voice_parameter, prompt, workspace, title, narration_speed)''',
)

controller = controller.replace(
    '''                    "volumeNormalized": True,
                })''',
    '''                    "volumeNormalized": True,
                    "narrationSpeed": speed_info["key"],
                    "narrationSpeedLabel": speed_info["label"],
                    "narrationSpeedMultiplier": speed_info["multiplier"],
                    "narrationSpeedDisplay": speed_info["display"],
                })''',
)

CONTROLLER.write_text(controller, encoding="utf-8")

# -------------------------------------------------------------------
# Client HTML: add narration speed selector.
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")

if 'id="narrationSpeed"' not in html:
    speed_html = r'''
        <label>
          Narration speed
          <select id="narrationSpeed">
            <option value="slower">Slower (0.80x)</option>
            <option value="slow">Slow (0.90x)</option>
            <option value="normal" selected>Normal (1.00x)</option>
            <option value="fast">Fast (1.10x)</option>
            <option value="faster">Faster (1.20x)</option>
          </select>
        </label>
'''

    html = html.replace(
        '''        <label>
          Text to narrate''',
        speed_html + '''
        <label>
          Text to narrate''',
        1,
    )

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=narration-speed-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=narration-speed-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

# -------------------------------------------------------------------
# Client JS: send narration speed and show it in result card.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

if 'const narrationSpeed = $("#narrationSpeed");' not in js:
    js = js.replace(
        'const promptInput = $("#promptInput");',
        '''const promptInput = $("#promptInput");
  const narrationSpeed = $("#narrationSpeed");''',
        1,
    )

if '["Speed", data.narrationSpeedDisplay ||' not in js:
    js = js.replace(
        '["Source", data.sourceType || ""],',
        '''["Source", data.sourceType || ""],
      ["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],''',
        1,
    )

if 'formData.append("narrationSpeed"' not in js:
    js = js.replace(
        'formData.append("sourceMode", mode);',
        '''formData.append("sourceMode", mode);
    formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");''',
        1,
    )

JS.write_text(js, encoding="utf-8")

py_compile.compile(str(AUDIO_POLICY), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 10 COMPLETE: Narration speed control added.")
print()
print("Speed options:")
print("  Slower  0.80x")
print("  Slow    0.90x")
print("  Normal  1.00x")
print("  Fast    1.10x")
print("  Faster  1.20x")
print()
print("Applied only to final narration.")
print("Voice parameters and standard previews are unchanged.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?narration-speed=1")
