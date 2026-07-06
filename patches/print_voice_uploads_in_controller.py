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
backup = CONTROLLER.with_name(CONTROLLER.name + f".bak.print-uploads-{stamp}")
text = CONTROLLER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

debug_block = r'''
    # SMX_PRINT_UPLOADED_VOICE_FILES_START
    print("\n" + "=" * 100, flush=True)
    print("[SYNTAXMATRIX VOICE CONTROLLER] voice_clone_create_profile_api RECEIVED REQUEST", flush=True)
    print("request.method:", request.method, flush=True)
    print("request.path:", request.path, flush=True)
    print("request.content_type:", request.content_type, flush=True)

    print("FORM KEYS:", list(request.form.keys()), flush=True)
    for _key in request.form.keys():
        print(f"  form[{_key!r}] = {request.form.getlist(_key)!r}", flush=True)

    print("FILE KEYS:", list(request.files.keys()), flush=True)
    for _field_name, _files in request.files.lists():
        print(f"  files field {_field_name!r}: count={len(_files)}", flush=True)
        for _index, _file in enumerate(_files):
            try:
                _pos = _file.stream.tell()
                _file.stream.seek(0, 2)
                _size = _file.stream.tell()
                _file.stream.seek(_pos)
            except Exception as _exc:
                _size = f"unknown: {_exc!r}"

            print(
                f"    file[{_index}] "
                f"field={_field_name!r} "
                f"filename={_file.filename!r} "
                f"mimetype={_file.mimetype!r} "
                f"content_type={_file.content_type!r} "
                f"size={_size}",
                flush=True,
            )

    print("=" * 100 + "\n", flush=True)
    # SMX_PRINT_UPLOADED_VOICE_FILES_END
'''

if "SMX_PRINT_UPLOADED_VOICE_FILES_START" in text:
    print("Debug print block already exists. No change made.")
else:
    pattern = r"(def\s+voice_clone_create_profile_api\s*\([^)]*\)\s*:\s*\n)"
    match = re.search(pattern, text)

    if not match:
        print("ERROR: Could not find def voice_clone_create_profile_api(...):")
        raise SystemExit(1)

    insert_at = match.end()
    text = text[:insert_at] + debug_block + text[insert_at:]

    CONTROLLER.write_text(text, encoding="utf-8")
    py_compile.compile(str(CONTROLLER), doraise=True)

    print("Inserted upload-file debug print into voice_clone_create_profile_api().")

print()
print("Now restart Flask:")
print("  python app.py")
print()
print("Then upload audio and click Generate narration.")
print("You should see FILE KEYS and filename/mimetype/size printed in the Flask terminal.")