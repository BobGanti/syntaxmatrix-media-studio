from pathlib import Path
from datetime import datetime
import re
import py_compile
import shutil
import subprocess

ROOT = Path(".").resolve()

CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
JS = ROOT / "frontend" / "clone_voice" / "client.js"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"

required = [CONTROLLER, JS, HTML]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Required files missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step15b-fix-generate-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# 1. Backend repair: make narration style variable explicit in saved/system routes.
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

# Make sure import exists.
if "from services.clone_voice_style import generate_narration_to_file_with_style" not in controller:
    controller = controller.replace(
        "from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file",
        "from services.clone_voice_provider import create_voice_parameter, generate_narration_to_file\nfrom services.clone_voice_style import generate_narration_to_file_with_style",
        1,
    )

# Make sure _generate_and_normalize has the correct signature/body.
controller = re.sub(
    r'''def _generate_and_normalize\(voice_parameter: str, prompt: str, workspace, title: str(?:, narration_speed="normal")?(?:, narration_style="natural")?\):[\s\S]*?return output_path, asset_url(?:, speed_info)?(?:, style_info)?''',
    r'''def _generate_and_normalize(voice_parameter: str, prompt: str, workspace, title: str, narration_speed="normal", narration_style="natural"):
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

    return output_path, asset_url, speed_info, style_info''',
    controller,
    count=1,
)

# Ensure saved/system routes define narration_style right after narration_speed.
controller = controller.replace(
    '''            narration_speed = request.form.get("narrationSpeed", "normal").strip()
            narration_style = request.form.get("narrationStyle", "natural").strip()
            narration_style = request.form.get("narrationStyle", "natural").strip()''',
    '''            narration_speed = request.form.get("narrationSpeed", "normal").strip()
            narration_style = request.form.get("narrationStyle", "natural").strip()''',
)

controller = re.sub(
    r'''(workspace_id = request\.form\.get\("workspaceId", MOCK_WORKSPACE_ID\)\n\s+narration_speed = request\.form\.get\("narrationSpeed", "normal"\)\.strip\(\))(?!\n\s+narration_style)''',
    r'''\1
            narration_style = request.form.get("narrationStyle", "natural").strip()''',
    controller,
)

# Ensure all narration calls unpack four values.
controller = controller.replace(
    "output_path, asset_url, speed_info = _generate_and_normalize(",
    "output_path, asset_url, speed_info, style_info = _generate_and_normalize(",
)

# Ensure saved/system calls pass narration_style.
controller = controller.replace(
    "workspace, title, narration_speed)",
    "workspace, title, narration_speed, narration_style)",
)

# Avoid double replacement.
controller = controller.replace(
    "workspace, title, narration_speed, narration_style, narration_style)",
    "workspace, title, narration_speed, narration_style)",
)

# Ensure response contains style fields wherever speed fields exist.
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

# -------------------------------------------------------------------
# 2. Frontend repair: make Generate button explicitly trigger form request.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

# Ensure narrationStyle const exists.
if 'const narrationStyle = $("#narrationStyle");' not in js:
    js = js.replace(
        'const narrationSpeed = $("#narrationSpeed");',
        '''const narrationSpeed = $("#narrationSpeed");
  const narrationStyle = $("#narrationStyle");''',
        1,
    )

# Ensure style is appended.
if 'formData.append("narrationStyle"' not in js:
    js = js.replace(
        'formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");',
        '''formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");
    formData.append("narrationStyle", narrationStyle ? narrationStyle.value : "natural");''',
        1,
    )

# Add a click fallback in case submit binding is missed by browser/form quirks.
if 'submitBtn.addEventListener("click", handleGenerateButtonClick);' not in js:
    insert_before = '  form.addEventListener("submit", submitForm);'

    if insert_before not in js:
        print("ERROR: Could not find form submit listener in client.js.")
        raise SystemExit(1)

    fallback = r'''  function handleGenerateButtonClick(event) {
    event.preventDefault();
    submitForm(event);
  }

  submitBtn.addEventListener("click", handleGenerateButtonClick);

'''

    js = js.replace(insert_before, fallback + insert_before, 1)

# Make submitForm robust if called from click fallback.
js = js.replace(
    '''  async function submitForm(event) {
    event.preventDefault();''',
    '''  async function submitForm(event) {
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }''',
    1,
)

JS.write_text(js, encoding="utf-8")

# -------------------------------------------------------------------
# 3. Cache bust HTML.
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")
html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=fix-generate-button-1',
    html,
)
HTML.write_text(html, encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)

node = shutil.which("node")
if node:
    result = subprocess.run(
        [node, "--check", str(JS)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit("ERROR: client.js failed node --check")

print()
print("STEP 15B COMPLETE: Generate narration button repaired.")
print()
print("Fixed:")
print("  frontend submit/click wiring")
print("  narrationStyle form payload")
print("  backend narration style variable handling")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?fix-generate-button=1")
