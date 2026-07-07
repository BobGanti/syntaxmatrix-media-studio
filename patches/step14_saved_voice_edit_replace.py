from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()

CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [CONTROLLER, HTML, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Required files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step14-edit-replace-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# Controller: add update metadata and replace source routes.
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

if 'endpoint="clone_voice_update_my_voice"' not in controller:
    marker = '    if "clone_voice_from_source" not in app.view_functions:'

    if marker not in controller:
        print("ERROR: Could not find insertion marker before from-source route.")
        raise SystemExit(1)

    routes = r'''
    if "clone_voice_update_my_voice" not in app.view_functions:
        @app.patch("/api/clone-voice/my-voices/<voice_id>", endpoint="clone_voice_update_my_voice")
        def update_my_voice(voice_id: str):
            data = request.get_json(silent=True) or request.form
            workspace_id = (
                request.args.get("workspaceId")
                or data.get("workspaceId")
                or MOCK_WORKSPACE_ID
            )

            try:
                workspace = get_workspace(workspace_id)

                # Ensure voice exists.
                _, param_path = load_workspace_voice_parameter(workspace, voice_id)
                existing = load_voice_metadata(workspace, voice_id)

                display_name = (
                    data.get("displayName")
                    or data.get("voiceDisplayName")
                    or existing.get("displayName")
                    or display_name_from_voice_id(voice_id)
                ).strip()

                gender = normalize_gender(data.get("gender") or existing.get("gender"))

                if gender not in {"M", "F"}:
                    return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

                preview_path = stable_preview_path(workspace, voice_id)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type=existing.get("sourceType") or "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=bool(existing.get("parameterCreated")),
                    preview_created=bool(existing.get("previewCreated")),
                )

                payload = {
                    "ok": True,
                    "operation": "update_voice_metadata",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(preview_path) if preview_path.exists() else "",
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path) if preview_path.exists() else "",
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "message": "Saved voice details updated.",
                }

                print("[clone_voice_controller] Saved voice metadata updated:", payload, flush=True)

                return jsonify(payload)

            except Exception as exc:
                print("[clone_voice_controller] update saved voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

    if "clone_voice_replace_my_voice_source" not in app.view_functions:
        @app.post("/api/clone-voice/my-voices/<voice_id>/replace-source", endpoint="clone_voice_replace_my_voice_source")
        def replace_my_voice_source(voice_id: str):
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            audio_file = request.files.get("audio")

            if audio_file is None or not audio_file.filename:
                return _error("Missing replacement audio file under field name 'audio'", 400)

            workspace = get_workspace(workspace_id)
            raw_source_path = None
            limited_source_path = None

            try:
                # Ensure voice exists before replacing.
                _, old_param_path = load_workspace_voice_parameter(workspace, voice_id)
                existing = load_voice_metadata(workspace, voice_id)

                display_name = (
                    request.form.get("displayName", "")
                    or request.form.get("voiceDisplayName", "")
                    or existing.get("displayName")
                    or display_name_from_voice_id(voice_id)
                ).strip()

                gender = normalize_gender(request.form.get("gender") or existing.get("gender"))

                if gender not in {"M", "F"}:
                    return _error("Voice gender is required. Choose Male (M) or Female (F).", 400)

                max_seconds = get_max_voice_source_seconds()
                raw_source_path = save_source_audio(audio_file, workspace)
                limited_source_path = source_limited_path(workspace, voice_id)

                limit_audio_to_max_seconds(
                    input_path=raw_source_path,
                    output_path=limited_source_path,
                    max_seconds=max_seconds,
                )

                voice_parameter = create_voice_parameter(limited_source_path, "audio/wav")
                voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)

                preview_path = stable_preview_path(workspace, voice_id)
                _generate_standard_preview(voice_parameter, preview_path)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type=existing.get("sourceType") or "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=True,
                    preview_created=True,
                )

                payload = {
                    "ok": True,
                    "operation": "replace_voice_source",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "oldVoiceParamPath": relative_to_root(old_param_path),
                    "voicePreviewPath": relative_to_root(preview_path),
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "maxVoiceSourceSeconds": max_seconds,
                    "parameterCreated": True,
                    "previewCreated": True,
                    "message": "Saved voice source replaced. Parameter and standard preview rebuilt.",
                }

                print("[clone_voice_controller] Saved voice source replaced:", payload, flush=True)

                return jsonify(payload)

            except Exception as exc:
                print("[clone_voice_controller] replace saved voice source error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                delete_if_exists(raw_source_path)
                delete_if_exists(limited_source_path)

'''

    controller = controller.replace(marker, routes + marker, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

# -------------------------------------------------------------------
# HTML: add manage panel under My saved voices.
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")

if 'id="savedVoiceManagePanel"' not in html:
    manage_panel = r'''
          <div id="savedVoiceManagePanel" class="voice-manage-panel hidden">
            <h3>Manage selected voice</h3>

            <div class="voice-manage-grid">
              <label>
                Display name
                <input id="editSavedVoiceDisplayName" type="text" placeholder="Voice display name">
              </label>

              <label>
                Gender
                <select id="editSavedVoiceGender">
                  <option value="M">Male (M)</option>
                  <option value="F">Female (F)</option>
                </select>
              </label>

              <button id="saveSavedVoiceMetaBtn" type="button">Save details</button>
            </div>

            <div class="voice-replace-grid">
              <label>
                Replace source audio
                <input id="replaceSavedVoiceAudio" type="file" accept="audio/*">
              </label>

              <button id="replaceSavedVoiceSourceBtn" type="button">Replace source</button>
            </div>

            <p class="status">Editing details keeps the current parameter and preview. Replacing source rebuilds both.</p>
          </div>
'''

    html = html.replace(
        '<div id="savedVoicesList" class="voice-list">Loading saved voices...</div>',
        '<div id="savedVoicesList" class="voice-list">Loading saved voices...</div>' + manage_panel,
        1,
    )

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=saved-voice-edit-replace-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=saved-voice-edit-replace-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

# -------------------------------------------------------------------
# CSS: manage panel styling.
# -------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8")

if ".voice-manage-panel" not in css:
    css += r'''

/* Step 14: saved voice edit / replace */

.voice-manage-panel {
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid rgba(255, 209, 102, 0.35);
  border-radius: 16px;
  background:
    linear-gradient(135deg, rgba(255, 209, 102, 0.08), rgba(7, 16, 23, 0.96)),
    #071017;
}

.voice-manage-panel h3 {
  margin: 0;
}

.voice-manage-grid,
.voice-replace-grid {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) 180px auto;
  gap: 14px;
  align-items: end;
}

.voice-replace-grid {
  grid-template-columns: minmax(220px, 1fr) auto;
}

@media (max-width: 900px) {
  .voice-manage-grid,
  .voice-replace-grid {
    grid-template-columns: 1fr;
  }

  .voice-manage-panel button {
    width: 100%;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

# -------------------------------------------------------------------
# JS: manage selected saved voice.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

if 'const savedVoiceManagePanel = $("#savedVoiceManagePanel");' not in js:
    js = js.replace(
        'const savedVoicesList = $("#savedVoicesList");',
        '''const savedVoicesList = $("#savedVoicesList");
  const savedVoiceManagePanel = $("#savedVoiceManagePanel");
  const editSavedVoiceDisplayName = $("#editSavedVoiceDisplayName");
  const editSavedVoiceGender = $("#editSavedVoiceGender");
  const saveSavedVoiceMetaBtn = $("#saveSavedVoiceMetaBtn");
  const replaceSavedVoiceAudio = $("#replaceSavedVoiceAudio");
  const replaceSavedVoiceSourceBtn = $("#replaceSavedVoiceSourceBtn");''',
        1,
    )

if "function selectedSavedVoice()" not in js:
    marker = '  async function deleteSavedVoice(voiceId, label) {'

    if marker not in js:
        print("ERROR: Could not find insertion point before deleteSavedVoice.")
        raise SystemExit(1)

    helpers = r'''  function selectedSavedVoice() {
    const voiceId = selectedVoiceId("savedVoiceId");
    if (!voiceId) return null;
    return savedVoices.find((voice) => voice.voiceId === voiceId) || null;
  }

  function updateSavedVoiceEditor() {
    if (!savedVoiceManagePanel) return;

    const voice = selectedSavedVoice();

    if (!voice) {
      savedVoiceManagePanel.classList.add("hidden");
      return;
    }

    savedVoiceManagePanel.classList.remove("hidden");
    editSavedVoiceDisplayName.value = voice.displayName || "";
    editSavedVoiceGender.value = voice.gender || "M";
    replaceSavedVoiceAudio.value = "";
  }

  async function saveSelectedSavedVoiceMetadata() {
    const voice = selectedSavedVoice();

    if (!voice) {
      alert("Choose a saved voice first.");
      return;
    }

    const displayName = editSavedVoiceDisplayName.value.trim();
    const gender = editSavedVoiceGender.value;

    if (!displayName) {
      alert("Enter a display name.");
      editSavedVoiceDisplayName.focus();
      return;
    }

    if (gender !== "M" && gender !== "F") {
      alert("Choose Male (M) or Female (F).");
      editSavedVoiceGender.focus();
      return;
    }

    saveSavedVoiceMetaBtn.disabled = true;
    saveSavedVoiceMetaBtn.textContent = "Saving...";
    resultBox.textContent = "Saving voice details...";

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voice.voiceId)}?workspaceId=${encodeURIComponent(activeWorkspaceId)}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            workspaceId: activeWorkspaceId,
            displayName,
            gender
          })
        }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not update voice details");
      }

      resultBox.innerHTML = `
        <strong>Saved voice updated.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(data.label || data.displayName || data.voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Parameter</div>
            <div class="result-value">Kept existing</div>
          </div>
          <div class="result-row">
            <div class="result-label">Preview</div>
            <div class="result-value">Kept existing</div>
          </div>
        </div>
      `;

      pendingSelectSavedVoiceId = data.voiceId || voice.voiceId;
      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      saveSavedVoiceMetaBtn.disabled = false;
      saveSavedVoiceMetaBtn.textContent = "Save details";
    }
  }

  async function replaceSelectedSavedVoiceSource() {
    const voice = selectedSavedVoice();

    if (!voice) {
      alert("Choose a saved voice first.");
      return;
    }

    const file = replaceSavedVoiceAudio.files[0];

    if (!file) {
      alert("Choose replacement audio first.");
      replaceSavedVoiceAudio.focus();
      return;
    }

    const displayName = editSavedVoiceDisplayName.value.trim() || voice.displayName || voice.voiceId;
    const gender = editSavedVoiceGender.value || voice.gender;

    if (gender !== "M" && gender !== "F") {
      alert("Choose Male (M) or Female (F).");
      editSavedVoiceGender.focus();
      return;
    }

    const ok = confirm(`Replace source for ${voice.label || voice.voiceId}? This rebuilds its parameter and preview.`);

    if (!ok) return;

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("displayName", displayName);
    formData.append("gender", gender);
    formData.append("audio", file, file.name);

    replaceSavedVoiceSourceBtn.disabled = true;
    replaceSavedVoiceSourceBtn.textContent = "Replacing...";
    resultBox.textContent = "Replacing voice source and rebuilding standard preview...";

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voice.voiceId)}/replace-source`,
        {
          method: "POST",
          body: formData
        }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not replace voice source");
      }

      resultBox.innerHTML = `
        <strong>Voice source replaced.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(data.label || data.displayName || data.voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Parameter</div>
            <div class="result-value">Rebuilt</div>
          </div>
          <div class="result-row">
            <div class="result-label">Preview</div>
            <div class="result-value">Rebuilt</div>
          </div>
        </div>
      `;

      if (data.voicePreviewUrl) {
        audioPlayer.src = `${data.voicePreviewUrl}${data.voicePreviewUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");
      }

      pendingSelectSavedVoiceId = data.voiceId || voice.voiceId;
      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      replaceSavedVoiceSourceBtn.disabled = false;
      replaceSavedVoiceSourceBtn.textContent = "Replace source";
    }
  }

'''
    js = js.replace(marker, helpers + marker, 1)

# Ensure editor refreshes after rendering saved list.
if 'if (groupName === "savedVoiceId") updateSavedVoiceEditor();' not in js:
    js = js.replace(
        '''    if (pendingSelectSavedVoiceId && groupName === "savedVoiceId") {
      const input = container.querySelector(`input[value="${CSS.escape(pendingSelectSavedVoiceId)}"]`);
      if (input) {
        input.checked = true;
        pendingSelectSavedVoiceId = "";
      }
    }
  }''',
        '''    if (pendingSelectSavedVoiceId && groupName === "savedVoiceId") {
      const input = container.querySelector(`input[value="${CSS.escape(pendingSelectSavedVoiceId)}"]`);
      if (input) {
        input.checked = true;
        pendingSelectSavedVoiceId = "";
      }
    }

    if (groupName === "savedVoiceId") updateSavedVoiceEditor();
  }''',
        1,
    )

# Add listeners.
if 'saveSavedVoiceMetaBtn.addEventListener("click"' not in js:
    js = js.replace(
        '''  refreshSavedBtn.addEventListener("click", loadSavedVoices);''',
        '''  refreshSavedBtn.addEventListener("click", loadSavedVoices);

  if (saveSavedVoiceMetaBtn) {
    saveSavedVoiceMetaBtn.addEventListener("click", saveSelectedSavedVoiceMetadata);
  }

  if (replaceSavedVoiceSourceBtn) {
    replaceSavedVoiceSourceBtn.addEventListener("click", replaceSelectedSavedVoiceSource);
  }''',
        1,
    )

if 'event.target.matches(\'input[name="savedVoiceId"]\')' not in js:
    js = js.replace(
        '''  document.addEventListener("click", (event) => {''',
        '''  document.addEventListener("change", (event) => {
    if (event.target.matches('input[name="savedVoiceId"]')) {
      updateSavedVoiceEditor();
    }
  });

  document.addEventListener("click", (event) => {''',
        1,
    )

JS.write_text(js, encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 14 COMPLETE: Saved voice edit / replace management added.")
print()
print("Client can now:")
print("  Edit display name")
print("  Edit gender M/F")
print("  Replace source audio")
print()
print("Edit keeps:")
print("  existing voice parameter")
print("  existing standard preview")
print()
print("Replace rebuilds:")
print("  voice parameter")
print("  standard preview")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?saved-voice-edit-replace=1")
