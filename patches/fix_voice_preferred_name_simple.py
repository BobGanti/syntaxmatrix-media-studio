from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()
CONTROLLER = ROOT / "controllers" / "voice_clone_controller.py"

if not CONTROLLER.exists():
    print("ERROR: controllers/voice_clone_controller.py not found. Run from project root.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
backup = CONTROLLER.with_name(CONTROLLER.name + f".bak.preferred-name-simple-{stamp}")
text = CONTROLLER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

helper = r'''

def _provider_safe_preferred_name() -> str:
    """Safe provider enrollment name.

    Do not send uploaded filenames, browser labels, or client-generated names
    as provider preferred_name. The working local script uses the default
    safe name, so keep provider enrollment stable.
    """
    return "smxVoice"
'''

if "def _provider_safe_preferred_name()" not in text:
    # Put helper before the create profile function if possible.
    marker = "\ndef voice_clone_create_profile_api("
    if marker in text:
        text = text.replace(marker, helper + marker, 1)
    else:
        # Fallback: put it before route registration.
        marker = "\ndef register_voice_clone_routes("
        if marker in text:
            text = text.replace(marker, helper + marker, 1)
        else:
            text += helper

start_marker = "def voice_clone_create_profile_api("
start = text.find(start_marker)

if start == -1:
    print("ERROR: Could not find def voice_clone_create_profile_api(")
    print("Open controllers/voice_clone_controller.py and tell me the function name around the failing create_voice call.")
    raise SystemExit(1)

next_def = text.find("\ndef ", start + 1)
if next_def == -1:
    next_def = len(text)

before = text[:start]
body = text[start:next_def]
after = text[next_def:]

count = len(re.findall(r"preferred_name\s*=\s*preferred_name\s*,", body))

if count == 0:
    print("ERROR: Found voice_clone_create_profile_api(), but did not find:")
    print("  preferred_name=preferred_name,")
    print()
    print("Search result hints:")
    for match in re.finditer(r"preferred_name\s*=", body):
        line_start = body.rfind("\n", 0, match.start()) + 1
        line_end = body.find("\n", match.end())
        print(" ", body[line_start:line_end])
    raise SystemExit(1)

body = re.sub(
    r"preferred_name\s*=\s*preferred_name\s*,",
    "preferred_name=_provider_safe_preferred_name(),",
    body,
)

text = before + body + after

CONTROLLER.write_text(text, encoding="utf-8")
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("Preferred-name simple fix applied.")
print(f"Replaced {count} occurrence(s) inside voice_clone_create_profile_api().")
print()
print("Now restart Flask:")
print("  python app.py")
print()
print("Then test Upload audio again.")
print()
print("Expected result:")
print("  create_voice receives preferred_name='smxVoice'")
print("  a .txt voice parameter file should be created after provider success")