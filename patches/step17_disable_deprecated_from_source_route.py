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
    print("ERROR: Required files not found:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step17-disable-deprecated-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

controller = CONTROLLER.read_text(encoding="utf-8")

pattern = re.compile(
    r'''    if "clone_voice_from_source" not in app\.view_functions:\n[\s\S]*?\n(?=    if "clone_voice_from_saved" not in app\.view_functions:)''',
    re.MULTILINE,
)

replacement = r'''    if "clone_voice_from_source" not in app.view_functions:
        @app.post("/api/clone-voice/from-source", endpoint="clone_voice_from_source")
        def from_source():
            return _error(
                "Deprecated route. Use POST /api/clone-voice/voices/from-source to save a voice, then POST /api/clone-voice/from-saved or /api/clone-voice/from-system to generate narration.",
                410,
            )

'''

controller, count = pattern.subn(replacement, controller, count=1)

if count != 1:
    print("ERROR: Could not find deprecated /api/clone-voice/from-source route block.")
    raise SystemExit(1)

CONTROLLER.write_text(controller, encoding="utf-8")

js = JS.read_text(encoding="utf-8")

if '"/api/clone-voice/from-source"' in js or "'/api/clone-voice/from-source'" in js:
    print("ERROR: frontend still calls deprecated /api/clone-voice/from-source")
    raise SystemExit(1)

html = HTML.read_text(encoding="utf-8")
html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=deprecated-route-disabled-1',
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
print("STEP 17 COMPLETE: deprecated coupled route disabled.")
print()
print("Disabled:")
print("  POST /api/clone-voice/from-source")
print()
print("Active clean routes:")
print("  POST /api/clone-voice/voices/from-source")
print("  POST /api/clone-voice/from-saved")
print("  POST /api/clone-voice/from-system")
print()
print("Old route now returns HTTP 410 Gone with a clear migration message.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?deprecated-route-disabled=1")
