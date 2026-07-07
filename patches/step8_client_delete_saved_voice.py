from pathlib import Path
from datetime import datetime
import re
import py_compile

ROOT = Path(".").resolve()

WORKSPACE = ROOT / "services" / "clone_voice_workspace.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [WORKSPACE, CONTROLLER, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step8-delete-saved-voice-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# Workspace service: delete saved voice parameter + preview + metadata.
# -------------------------------------------------------------------
workspace = WORKSPACE.read_text(encoding="utf-8")

if "def delete_workspace_voice(" not in workspace:
    workspace += r'''


def delete_workspace_voice(paths: WorkspacePaths, voice_id: str) -> dict[str, Any]:
    voice_id = safe_slug(voice_id)
    deleted: list[str] = []

    candidates: list[pathlib.Path] = [
        stable_parameter_path(paths, voice_id),
        legacy_parameter_path(paths, voice_id),
        stable_preview_path(paths, voice_id),
        metadata_path(paths, voice_id),
    ]

    for pattern in [
        f"{voice_id}_preview.*",
        f"{voice_id}.*",
    ]:
        for path in paths.voice_previews_dir.glob(pattern):
            candidates.append(path)

    unique: dict[str, pathlib.Path] = {}

    for path in candidates:
        unique[str(path.resolve())] = path

    for path in unique.values():
        if path.exists():
            deleted.append(relative_to_root(path))
            path.unlink()

    return {
        "ok": True,
        "voiceId": voice_id,
        "deleted": deleted,
        "deletedCount": len(deleted),
    }
'''

WORKSPACE.write_text(workspace, encoding="utf-8")

# -------------------------------------------------------------------
# Controller: add DELETE /api/clone-voice/my-voices/<voice_id>
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

if "delete_workspace_voice" not in controller:
    controller = controller.replace(
        "delete_if_exists,\n",
        "delete_if_exists,\n    delete_workspace_voice,\n",
        1,
    )

if 'endpoint="clone_voice_delete_my_voice"' not in controller:
    marker = '    if "clone_voice_from_source" not in app.view_functions:'

    if marker not in controller:
        print("ERROR: Could not find insertion point before from-source route.")
        raise SystemExit(1)

    route = r'''
    if "clone_voice_delete_my_voice" not in app.view_functions:
        @app.delete("/api/clone-voice/my-voices/<voice_id>", endpoint="clone_voice_delete_my_voice")
        def delete_my_voice(voice_id: str):
            data = request.get_json(silent=True) or {}
            workspace_id = (
                request.args.get("workspaceId")
                or data.get("workspaceId")
                or MOCK_WORKSPACE_ID
            )

            try:
                workspace = get_workspace(workspace_id)
                payload = delete_workspace_voice(workspace, voice_id)

                print("[clone_voice_controller] Saved voice deleted:", payload, flush=True)

                return jsonify({
                    **payload,
                    "workspaceId": workspace.workspace_id,
                })

            except Exception as exc:
                print("[clone_voice_controller] delete saved voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

'''

    controller = controller.replace(marker, route + marker, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

# -------------------------------------------------------------------
# Client CSS: button style for delete action.
# -------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8")

if ".delete-voice-btn" not in css:
    css += r'''

.delete-voice-btn {
  background: linear-gradient(135deg, #ffb3b3, #ff7676);
  color: #2b0505;
}

.voice-card {
  grid-template-columns: auto 1fr auto auto;
}

@media (max-width: 860px) {
  .voice-card {
    grid-template-columns: 1fr;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

# -------------------------------------------------------------------
# Client JS: add Delete button for My saved voices only.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

render_pattern = re.compile(
    r'  function renderVoiceList\(container, voices, groupName, genderFilter\) \{[\s\S]*?\n  \}\n\n  async function loadSavedVoices\(\) \{',
    re.MULTILINE,
)

render_replacement = r'''  function renderVoiceList(container, voices, groupName, genderFilter) {
    const rows = filteredVoices(voices, genderFilter);
    const isSavedVoiceList = groupName === "savedVoiceId";

    if (!rows.length) {
      container.innerHTML = `<p class="status">No voices found for this filter.</p>`;
      return;
    }

    container.innerHTML = rows.map((voice, index) => {
      const inputId = `${groupName}_${index}`;

      const previewButton = voice.previewUrl
        ? `<button class="preview-btn" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}">Preview</button>`
        : `<span class="voice-card-meta">No preview</span>`;

      const deleteButton = isSavedVoiceList
        ? `<button class="preview-btn delete-voice-btn" type="button" data-delete-saved-voice-id="${escapeHtml(voice.voiceId)}" data-delete-saved-voice-label="${escapeHtml(voice.label || voice.displayName || voice.voiceId)}">Delete</button>`
        : "";

      return `
        <label class="voice-card" for="${escapeHtml(inputId)}">
          <input id="${escapeHtml(inputId)}" type="radio" name="${escapeHtml(groupName)}" value="${escapeHtml(voice.voiceId)}">
          <span>
            <span class="voice-card-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</span>
            <span class="voice-card-meta">Standard preview sentence</span>
          </span>
          ${previewButton}
          ${deleteButton}
        </label>
      `;
    }).join("");
  }

  async function deleteSavedVoice(voiceId, label) {
    const ok = confirm(`Delete saved voice: ${label || voiceId}?`);

    if (!ok) return;

    resultBox.textContent = `Deleting saved voice: ${label || voiceId}...`;

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voiceId)}?workspaceId=${encodeURIComponent(WORKSPACE_ID)}`,
        {
          method: "DELETE"
        }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not delete saved voice");
      }

      resultBox.innerHTML = `
        <strong>Saved voice deleted.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(label || voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Deleted files</div>
            <div class="result-value">${escapeHtml(data.deletedCount || 0)}</div>
          </div>
        </div>
      `;

      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    }
  }

  async function loadSavedVoices() {'''

if render_pattern.search(js):
    js = render_pattern.sub(render_replacement, js, count=1)
elif "async function deleteSavedVoice(" not in js:
    print("ERROR: Could not replace renderVoiceList in client.js.")
    raise SystemExit(1)

old_click = r'''  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-preview-url]");
    if (!button) return;
    event.preventDefault();
    playPreview(button.getAttribute("data-preview-url"));
  });'''

new_click = r'''  document.addEventListener("click", (event) => {
    const deleteButton = event.target.closest("[data-delete-saved-voice-id]");

    if (deleteButton) {
      event.preventDefault();
      deleteSavedVoice(
        deleteButton.getAttribute("data-delete-saved-voice-id"),
        deleteButton.getAttribute("data-delete-saved-voice-label")
      );
      return;
    }

    const previewButton = event.target.closest("[data-preview-url]");

    if (previewButton) {
      event.preventDefault();
      playPreview(previewButton.getAttribute("data-preview-url"));
    }
  });'''

if old_click in js:
    js = js.replace(old_click, new_click, 1)
elif "[data-delete-saved-voice-id]" not in js:
    print("ERROR: Could not replace document click handler in client.js.")
    raise SystemExit(1)

JS.write_text(js, encoding="utf-8")

py_compile.compile(str(WORKSPACE), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 8 COMPLETE: Client can delete saved voices.")
print()
print("Added:")
print("  DELETE /api/clone-voice/my-voices/<voice_id>")
print("  Delete button in My saved voices list")
print()
print("Deletes:")
print("  saved voice parameter")
print("  saved standard preview")
print("  saved metadata")
print()
print("Does not delete:")
print("  generated narration audio files")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?delete-saved-voice=1")
