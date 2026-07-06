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
backup = CONTROLLER.with_name(CONTROLLER.name + f".bak.preferred-name-{stamp}")
backup.write_text(CONTROLLER.read_text(encoding="utf-8"), encoding="utf-8")
print("Backup:", backup)

text = CONTROLLER.read_text(encoding="utf-8")

# Add a dedicated provider-safe enrollment name helper.
if "def _provider_safe_preferred_name()" not in text:
    helper = r'''

def _provider_safe_preferred_name() -> str:
    """Provider enrollment preferred_name.

    Do not use browser filenames, client labels, or generated UI names here.
    The working local script calls create_voice(source_path) and therefore uses
    ali_voice_clone.DEFAULT_PREFERRED_NAME, which is "smxVoice".

    The reusable local .txt file can still be saved using the uploaded source
    filename, but the provider enrollment name must stay safe.
    """
    return DEFAULT_VOICE_NAME
'''
    text = text.replace(
        "\ndef _voice_param_path(preferred_name: str, source_path: Optional[pathlib.Path] = None) -> pathlib.Path:",
        helper + "\n\ndef _voice_param_path(preferred_name: str, source_path: Optional[pathlib.Path] = None) -> pathlib.Path:",
        1,
    )

old = '''        if source_path:
            voice_parameter = voice_feature.create_voice(
                str(source_path),
                target_model=target_model,
                preferred_name=preferred_name,
                audio_mime_type=mimetypes.guess_type(source_path.name)[0] or "audio/wav",
            )
            param_path = _voice_param_path(preferred_name, source_path)
            voice_feature.save_voice_to_disk(voice_parameter, str(param_path))
'''

new = '''        if source_path:
            # Important:
            # The uploaded filename/client label is NOT sent as provider preferred_name.
            # Your working local script uses create_voice(source_path), which falls back
            # to the safe default preferred_name "smxVoice".
            enrollment_preferred_name = _provider_safe_preferred_name()

            print("[SyntaxMatrix Voice] Creating voice identity", flush=True)
            print("  source_path:", source_path, flush=True)
            print("  local_param_basis:", preferred_name, flush=True)
            print("  provider_preferred_name:", enrollment_preferred_name, flush=True)
            print("  audio_mime_type:", mimetypes.guess_type(source_path.name)[0] or "audio/wav", flush=True)

            voice_parameter = voice_feature.create_voice(
                str(source_path),
                target_model=target_model,
                preferred_name=enrollment_preferred_name,
                audio_mime_type=mimetypes.guess_type(source_path.name)[0] or "audio/wav",
            )

            # The .txt file is local SyntaxMatrix storage. This can still use the
            # uploaded source filename so you know which client audio created it.
            param_path = _voice_param_path(preferred_name, source_path)
            voice_feature.save_voice_to_disk(voice_parameter, str(param_path))
            print("[SyntaxMatrix Voice] Saved voice parameter:", param_path, flush=True)
'''

if old not in text:
    print("ERROR: Could not find the exact create_voice block to replace.")
    print("Open controllers/voice_clone_controller.py and search for:")
    print("preferred_name=preferred_name")
    raise SystemExit(1)

text = text.replace(old, new, 1)

CONTROLLER.write_text(text, encoding="utf-8")
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("Preferred-name fix applied.")
print("Now restart Flask with: python app.py")
print("Then test Upload audio again.")
print()
print("Expected terminal output should include:")
print("  provider_preferred_name: smxVoice")
print("  Saved voice parameter: ...voices/params/...txt")