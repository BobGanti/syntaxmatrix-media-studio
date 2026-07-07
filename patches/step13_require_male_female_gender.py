from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()

WORKSPACE = ROOT / "services" / "clone_voice_workspace.py"
SYSTEM = ROOT / "services" / "clone_voice_system.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"

CLIENT_HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CLIENT_JS = ROOT / "frontend" / "clone_voice" / "client.js"

ADMIN_HTML = ROOT / "frontend" / "clone_voice" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "clone_voice" / "admin.js"

required = [WORKSPACE, SYSTEM, CONTROLLER, CLIENT_HTML, CLIENT_JS, ADMIN_HTML, ADMIN_JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Required files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step13-gender-required-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# workspace service: M/F only, no U.
# -------------------------------------------------------------------
workspace = WORKSPACE.read_text(encoding="utf-8")

workspace = re.sub(
    r'''def normalize_gender\(value: str \| None\) -> str:[\s\S]*?\n\n\ndef display_name_from_voice_id''',
    r'''def normalize_gender(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE"}:
        return "M"
    if text in {"F", "FEMALE"}:
        return "F"
    return ""


def require_gender(value: str | None) -> str:
    gender = normalize_gender(value)
    if gender not in {"M", "F"}:
        raise ValueError("Voice gender is required. Choose Male (M) or Female (F).")
    return gender


def display_name_from_voice_id''',
    workspace,
    count=1,
)

workspace = workspace.replace(
    '        "m", "male", "f", "female", "u", "unknown",',
    '        "m", "male", "f", "female",',
)

workspace = re.sub(
    r'''def infer_gender_from_voice_id\(voice_id: str\) -> str:[\s\S]*?\n\n\ndef voice_label''',
    r'''def infer_gender_from_voice_id(voice_id: str) -> str:
    parts = [part.upper() for part in re.split(r"[_-]+", str(voice_id or "")) if part]
    if "M" in parts or "MALE" in parts:
        return "M"
    if "F" in parts or "FEMALE" in parts:
        return "F"
    return ""


def voice_label''',
    workspace,
    count=1,
)

workspace = re.sub(
    r'''def voice_label\(display_name: str, gender: str\) -> str:[\s\S]*?\n\n\ndef get_workspace''',
    r'''def voice_label(display_name: str, gender: str) -> str:
    gender = normalize_gender(gender)
    if gender in {"M", "F"}:
        return f"{display_name} ({gender})"
    return display_name


def get_workspace''',
    workspace,
    count=1,
)

# In save_voice_metadata, require M/F.
workspace = workspace.replace(
    '''    gender = normalize_gender(gender or existing.get("gender"))''',
    '''    gender = require_gender(gender or existing.get("gender"))''',
)

# Remove U from default metadata records.
workspace = workspace.replace('"gender": gender,', '"gender": gender,')
workspace = workspace.replace('normalize_gender(metadata.get("gender"))', 'normalize_gender(metadata.get("gender"))')

# Skip invalid legacy/no-gender voices in list output.
if "if gender not in {\"M\", \"F\"}:" not in workspace:
    workspace = workspace.replace(
        '''        metadata = load_voice_metadata(paths, voice_id)
        preview_path = stable_preview_path(paths, voice_id)
        preview_url = workspace_voice_preview_url(paths, preview_path) if preview_path.exists() else ""

        rows.append({
            "voiceId": voice_id,
            "displayName": metadata.get("displayName") or display_name_from_voice_id(voice_id),
            "gender": normalize_gender(metadata.get("gender")),
            "label": metadata.get("label") or voice_label(metadata.get("displayName") or display_name_from_voice_id(voice_id), metadata.get("gender")),
''',
        '''        metadata = load_voice_metadata(paths, voice_id)
        gender = normalize_gender(metadata.get("gender"))

        if gender not in {"M", "F"}:
            print("[clone_voice_workspace] Skipping saved voice with missing gender:", voice_id, flush=True)
            continue

        preview_path = stable_preview_path(paths, voice_id)
        preview_url = workspace_voice_preview_url(paths, preview_path) if preview_path.exists() else ""

        display_name = metadata.get("displayName") or display_name_from_voice_id(voice_id)

        rows.append({
            "voiceId": voice_id,
            "displayName": display_name,
            "gender": gender,
            "label": voice_label(display_name, gender),
''',
        1,
    )

WORKSPACE.write_text(workspace, encoding="utf-8")

# -------------------------------------------------------------------
# system service: M/F only for system voice creation and listing.
# -------------------------------------------------------------------
system = SYSTEM.read_text(encoding="utf-8")

if "require_gender" not in system:
    system = system.replace(
        '''    normalize_gender,
    relative_to_root,''',
        '''    normalize_gender,
    require_gender,
    relative_to_root,''',
        1,
    )

system = system.replace(
    '''    gender = normalize_gender(gender)''',
    '''    gender = require_gender(gender)''',
)

# Skip old system voices without M/F.
if "Skipping system voice with missing gender" not in system:
    system = system.replace(
        '''        payload = _system_voice_payload(voice_id, param_path)
        payload["_mtime"] = param_path.stat().st_mtime if param_path.exists() else 0
        rows.append(payload)''',
        '''        payload = _system_voice_payload(voice_id, param_path)

        if payload.get("gender") not in {"M", "F"}:
            print("[clone_voice_system] Skipping system voice with missing gender:", voice_id, flush=True)
            continue

        payload["_mtime"] = param_path.stat().st_mtime if param_path.exists() else 0
        rows.append(payload)''',
        1,
    )

SYSTEM.write_text(system, encoding="utf-8")

# -------------------------------------------------------------------
# controller: reject missing gender when creating client/system voices.
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

# Add backend guard after gender normalization in create workspace voice.
controller = controller.replace(
    '''            gender = normalize_gender(request.form.get("gender"))

            print("\\n" + "=" * 100, flush=True)''',
    '''            gender = normalize_gender(request.form.get("gender"))

            if gender not in {"M", "F"}:
                return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

            print("\\n" + "=" * 100, flush=True)''',
    1,
)

# Add backend guard to legacy from-source route too if present.
controller = controller.replace(
    '''            gender = normalize_gender(request.form.get("gender"))

            _print_received_source(prompt, title, audio_file, source_mode)''',
    '''            gender = normalize_gender(request.form.get("gender"))

            if gender not in {"M", "F"}:
                return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

            _print_received_source(prompt, title, audio_file, source_mode)''',
    1,
)

# Add backend guard to system voice admin route.
controller = controller.replace(
    '''            gender = request.form.get("gender", "U")
            replace_raw = str(request.form.get("replace", "")).strip().lower()''',
    '''            gender = normalize_gender(request.form.get("gender"))

            if gender not in {"M", "F"}:
                return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

            replace_raw = str(request.form.get("replace", "")).strip().lower()''',
    1,
)

CONTROLLER.write_text(controller, encoding="utf-8")

# -------------------------------------------------------------------
# client HTML: no U option. Gender required.
# -------------------------------------------------------------------
client_html = CLIENT_HTML.read_text(encoding="utf-8")

client_html = client_html.replace(
    '''<select id="voiceGender">
              <option value="U">Unspecified (U)</option>
              <option value="M">Male (M)</option>
              <option value="F">Female (F)</option>
            </select>''',
    '''<select id="voiceGender" required>
              <option value="">Choose gender</option>
              <option value="M">Male (M)</option>
              <option value="F">Female (F)</option>
            </select>''',
)

client_html = client_html.replace(
    '''<option value="U">Unspecified voices</option>''',
    "",
)

client_html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=gender-required-1',
    client_html,
)

client_html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=gender-required-1',
    client_html,
)

CLIENT_HTML.write_text(client_html, encoding="utf-8")

# -------------------------------------------------------------------
# client JS: validate M/F before saving voice. Remove U defaults/filter.
# -------------------------------------------------------------------
client_js = CLIENT_JS.read_text(encoding="utf-8")

client_js = client_js.replace('String(voice.gender || "U").toUpperCase()', 'String(voice.gender || "").toUpperCase()')
client_js = client_js.replace('formData.append("gender", voiceGender.value || "U");', 'formData.append("gender", voiceGender.value);')

if 'function requireSelectedGender()' not in client_js:
    client_js = client_js.replace(
        '''  async function saveClientVoice() {''',
        r'''  function requireSelectedGender() {
    const gender = voiceGender.value;

    if (gender !== "M" && gender !== "F") {
      alert("Choose voice gender: Male (M) or Female (F).");
      voiceGender.focus();
      return "";
    }

    return gender;
  }

  async function saveClientVoice() {''',
        1,
    )

client_js = client_js.replace(
    '''    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("sourceMode", mode);
    formData.append("voiceDisplayName", voiceDisplayName.value.trim());
    formData.append("gender", voiceGender.value);''',
    '''    const selectedGender = requireSelectedGender();

    if (!selectedGender) {
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("sourceMode", mode);
    formData.append("voiceDisplayName", voiceDisplayName.value.trim());
    formData.append("gender", selectedGender);''',
    1,
)

CLIENT_JS.write_text(client_js, encoding="utf-8")

# -------------------------------------------------------------------
# admin HTML/JS: no U option. Gender required.
# -------------------------------------------------------------------
admin_html = ADMIN_HTML.read_text(encoding="utf-8")

admin_html = admin_html.replace(
    '''<select id="systemVoiceGender">
            <option value="U">Unspecified (U)</option>
            <option value="M">Male (M)</option>
            <option value="F">Female (F)</option>
          </select>''',
    '''<select id="systemVoiceGender" required>
            <option value="">Choose gender</option>
            <option value="M">Male (M)</option>
            <option value="F">Female (F)</option>
          </select>''',
)

admin_html = admin_html.replace(
    '''<option value="U">Unspecified voices</option>''',
    "",
)

admin_html = re.sub(
    r'/clone_voice/admin\.js\?v=[^"]+',
    '/clone_voice/admin.js?v=gender-required-1',
    admin_html,
)

admin_html = re.sub(
    r'/clone_voice/admin\.css\?v=[^"]+',
    '/clone_voice/admin.css?v=gender-required-1',
    admin_html,
)

ADMIN_HTML.write_text(admin_html, encoding="utf-8")

admin_js = ADMIN_JS.read_text(encoding="utf-8")

admin_js = admin_js.replace('String(voice.gender || "U").toUpperCase()', 'String(voice.gender || "").toUpperCase()')
admin_js = admin_js.replace('formData.append("gender", systemVoiceGender.value || "U");', 'formData.append("gender", systemVoiceGender.value);')

if 'Choose system voice gender' not in admin_js:
    admin_js = admin_js.replace(
        '''    if (!displayName) {
      alert("Enter a display name.");
      return;
    }

    const formData = new FormData();''',
        '''    if (!displayName) {
      alert("Enter a display name.");
      return;
    }

    if (systemVoiceGender.value !== "M" && systemVoiceGender.value !== "F") {
      alert("Choose system voice gender: Male (M) or Female (F).");
      systemVoiceGender.focus();
      return;
    }

    const formData = new FormData();''',
        1,
    )

ADMIN_JS.write_text(admin_js, encoding="utf-8")

py_compile.compile(str(WORKSPACE), doraise=True)
py_compile.compile(str(SYSTEM), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 13 COMPLETE: gender is now mandatory and M/F only.")
print()
print("Changed:")
print("  Removed Unspecified (U) from client voice creation")
print("  Removed Unspecified (U) from admin system voice creation")
print("  Removed U filters")
print("  Backend rejects missing/invalid gender")
print("  Old no-gender voices are skipped from lists")
print()
print("Allowed genders:")
print("  M = Male")
print("  F = Female")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?gender-required=1")
