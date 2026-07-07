from pathlib import Path
from datetime import datetime
import py_compile
import re

ROOT = Path(".").resolve()

WORKSPACE = ROOT / "services" / "clone_voice_workspace.py"
CONTROLLER = ROOT / "controllers" / "clone_voice_controller.py"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [WORKSPACE, CONTROLLER, HTML, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step9-workspace-isolation-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# Workspace service: add two demo workspaces.
# -------------------------------------------------------------------
workspace = WORKSPACE.read_text(encoding="utf-8")

if "DEMO_WORKSPACES" not in workspace:
    workspace = workspace.replace(
        'MOCK_WORKSPACE_ID = "mock_user_001"',
        '''MOCK_WORKSPACE_ID = "mock_user_001"

DEMO_WORKSPACES = [
    {
        "workspaceId": "mock_user_001",
        "label": "Client A / Workspace 001",
    },
    {
        "workspaceId": "mock_user_002",
        "label": "Client B / Workspace 002",
    },
]''',
        1,
    )

if "def list_demo_workspaces(" not in workspace:
    insert_after = '''def get_workspace(workspace_id: str | None = None) -> WorkspacePaths:
    workspace_id = safe_slug(workspace_id or MOCK_WORKSPACE_ID, MOCK_WORKSPACE_ID)
    root = WORKSPACES_DIR / workspace_id

    paths = WorkspacePaths(
        workspace_id=workspace_id,
        root=root,
        tmp_source_audio_dir=root / "tmp" / "source_audio",
        voice_params_dir=root / "voice_params",
        voice_previews_dir=root / "voice_previews",
        voice_metadata_dir=root / "voice_metadata",
        generated_audio_dir=root / "generated_audio",
    )

    for directory in [
        paths.tmp_source_audio_dir,
        paths.voice_params_dir,
        paths.voice_previews_dir,
        paths.voice_metadata_dir,
        paths.generated_audio_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    return paths
'''

    if insert_after not in workspace:
        print("ERROR: Could not find get_workspace block.")
        raise SystemExit(1)

    workspace = workspace.replace(
        insert_after,
        insert_after + r'''


def list_demo_workspaces() -> list[dict[str, str]]:
    """Return demo workspaces used to verify tenant/client isolation."""
    rows: list[dict[str, str]] = []

    for row in DEMO_WORKSPACES:
        workspace_id = safe_slug(row.get("workspaceId"), MOCK_WORKSPACE_ID)

        # Ensure the workspace directories exist before the client switches to them.
        get_workspace(workspace_id)

        rows.append({
            "workspaceId": workspace_id,
            "label": row.get("label") or workspace_id,
        })

    return rows
''',
        1,
    )

WORKSPACE.write_text(workspace, encoding="utf-8")

# -------------------------------------------------------------------
# Controller: expose workspace list.
# -------------------------------------------------------------------
controller = CONTROLLER.read_text(encoding="utf-8")

if "list_demo_workspaces" not in controller:
    controller = controller.replace(
        "list_workspace_voice_parameters,\n",
        "list_workspace_voice_parameters,\n    list_demo_workspaces,\n",
        1,
    )

if 'endpoint="clone_voice_workspaces"' not in controller:
    marker = '    if "clone_voice_system_voices" not in app.view_functions:'

    if marker not in controller:
        print("ERROR: Could not find insertion marker before system voices route.")
        raise SystemExit(1)

    route = r'''
    if "clone_voice_workspaces" not in app.view_functions:
        @app.get("/api/clone-voice/workspaces", endpoint="clone_voice_workspaces")
        def clone_voice_workspaces():
            workspaces = list_demo_workspaces()

            return jsonify({
                "ok": True,
                "defaultWorkspaceId": MOCK_WORKSPACE_ID,
                "workspaces": workspaces,
            })

'''

    controller = controller.replace(marker, route + marker, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

# -------------------------------------------------------------------
# Client HTML: add workspace selector.
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")

if 'id="workspaceSelect"' not in html:
    workspace_section = r'''
      <section class="workspace-section">
        <h2>0. Client workspace</h2>

        <label>
          Active workspace
          <select id="workspaceSelect">
            <option value="mock_user_001">Client A / Workspace 001</option>
            <option value="mock_user_002">Client B / Workspace 002</option>
          </select>
        </label>

        <p class="status" id="workspaceStatus">
          Saved voices, previews, metadata, and generated narrations are scoped to the active workspace.
        </p>
      </section>
'''

    html = html.replace(
        '<form id="cloneVoiceForm" class="card">',
        '<form id="cloneVoiceForm" class="card">' + workspace_section,
        1,
    )

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=workspace-isolation-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=workspace-isolation-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

# -------------------------------------------------------------------
# Client CSS: workspace selector styling.
# -------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8")

if ".workspace-section" not in css:
    css += r'''

.workspace-section {
  display: grid;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #33414c;
  border-radius: 16px;
  background: #071017;
}

.workspace-section h2 {
  margin-bottom: 0;
}

.workspace-section select {
  max-width: 420px;
}
'''

CSS.write_text(css, encoding="utf-8")

# -------------------------------------------------------------------
# Client JS: use selected workspace instead of fixed WORKSPACE_ID.
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

if 'const workspaceSelect = $("#workspaceSelect");' not in js:
    js = js.replace(
        'const form = $("#cloneVoiceForm");',
        '''const form = $("#cloneVoiceForm");
  const workspaceSelect = $("#workspaceSelect");
  const workspaceStatus = $("#workspaceStatus");''',
        1,
    )

if 'let activeWorkspaceId = "mock_user_001";' not in js:
    js = js.replace(
        'const WORKSPACE_ID = "mock_user_001";',
        '''let activeWorkspaceId = "mock_user_001";
  let availableWorkspaces = [];''',
        1,
    )

# Replace remaining fixed workspace references.
js = js.replace("WORKSPACE_ID", "activeWorkspaceId")

if "function setWorkspaceStatus" not in js:
    marker = "  function selectedMode() {"

    if marker not in js:
        print("ERROR: Could not find selectedMode insertion marker.")
        raise SystemExit(1)

    workspace_js = r'''  function setWorkspaceStatus() {
    const label = availableWorkspaces.find((row) => row.workspaceId === activeWorkspaceId)?.label || activeWorkspaceId;

    if (workspaceStatus) {
      workspaceStatus.textContent = `Active workspace: ${label}. Saved voices, previews, metadata, and generated narrations are isolated to ${activeWorkspaceId}. System voices remain global.`;
    }
  }

  function fallbackWorkspaces() {
    return [
      {
        workspaceId: "mock_user_001",
        label: "Client A / Workspace 001",
      },
      {
        workspaceId: "mock_user_002",
        label: "Client B / Workspace 002",
      },
    ];
  }

  function renderWorkspaceOptions() {
    if (!workspaceSelect) return;

    workspaceSelect.innerHTML = availableWorkspaces.map((row) => `
      <option value="${escapeHtml(row.workspaceId)}">${escapeHtml(row.label || row.workspaceId)}</option>
    `).join("");

    workspaceSelect.value = activeWorkspaceId;
  }

  async function loadWorkspaces() {
    try {
      const response = await fetch(`/api/clone-voice/workspaces?t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load workspaces");
      }

      availableWorkspaces = data.workspaces && data.workspaces.length
        ? data.workspaces
        : fallbackWorkspaces();

      activeWorkspaceId = data.defaultWorkspaceId || availableWorkspaces[0].workspaceId || "mock_user_001";
    } catch (error) {
      console.warn("[Clone Voice] Could not load workspace list. Using fallback.", error);
      availableWorkspaces = fallbackWorkspaces();
      activeWorkspaceId = "mock_user_001";
    }

    renderWorkspaceOptions();
    setWorkspaceStatus();
    await loadSavedVoices();
  }

  async function switchWorkspace(workspaceId) {
    activeWorkspaceId = workspaceId || "mock_user_001";
    setWorkspaceStatus();

    savedVoices = [];

    if (savedVoicesList) {
      savedVoicesList.textContent = `Loading saved voices for ${activeWorkspaceId}...`;
    }

    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    resultBox.innerHTML = `
      <strong>Workspace switched.</strong>
      <div class="result-grid">
        <div class="result-row">
          <div class="result-label">Active workspace</div>
          <div class="result-value">${escapeHtml(activeWorkspaceId)}</div>
        </div>
        <div class="result-row">
          <div class="result-label">Isolation check</div>
          <div class="result-value">Saved voices are now loaded only from this workspace.</div>
        </div>
      </div>
    `;

    await loadSavedVoices();
  }

'''

    js = js.replace(marker, workspace_js + marker, 1)

# Add workspace row to result summary.
if '["Workspace", data.workspaceId || activeWorkspaceId],' not in js:
    js = js.replace(
        '["Narration", filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl) || "Ready"],',
        '''["Narration", filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl) || "Ready"],
      ["Workspace", data.workspaceId || activeWorkspaceId],''',
        1,
    )

# Add workspace change listener.
if 'workspaceSelect.addEventListener("change"' not in js:
    marker = '  sourceModeInputs.forEach((input) => {'

    if marker not in js:
        print("ERROR: Could not find event listener marker.")
        raise SystemExit(1)

    js = js.replace(
        marker,
        '''  if (workspaceSelect) {
    workspaceSelect.addEventListener("change", () => {
      switchWorkspace(workspaceSelect.value);
    });
  }

''' + marker,
        1,
    )

# Init: load workspaces instead of directly loading saved voices.
js = js.replace(
    '''  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadSavedVoices();
  loadSystemVoices();
  setMode("upload");''',
    '''  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadWorkspaces();
  loadSystemVoices();
  setMode("upload");''',
)

JS.write_text(js, encoding="utf-8")

py_compile.compile(str(WORKSPACE), doraise=True)
py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 9 COMPLETE: second workspace added for isolation testing.")
print()
print("Workspaces:")
print("  mock_user_001")
print("  mock_user_002")
print()
print("New API:")
print("  GET /api/clone-voice/workspaces")
print()
print("Client now has an Active workspace selector.")
print()
print("Workspace-scoped:")
print("  saved voice parameters")
print("  saved voice previews")
print("  saved voice metadata")
print("  generated narration audio")
print()
print("Global:")
print("  system voices")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?workspace-isolation=1")
