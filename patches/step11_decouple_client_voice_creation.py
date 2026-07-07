from pathlib import Path
from datetime import datetime
import py_compile
import re

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
    backup = path.with_name(path.name + f".bak.step11-decouple-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

controller = CONTROLLER.read_text(encoding="utf-8")

if 'endpoint="clone_voice_create_workspace_voice"' not in controller:
    marker = '    if "clone_voice_from_source" not in app.view_functions:'

    if marker not in controller:
        print("ERROR: Could not find insertion marker before from-source route.")
        raise SystemExit(1)

    route = r'''
    if "clone_voice_create_workspace_voice" not in app.view_functions:
        @app.post("/api/clone-voice/voices/from-source", endpoint="clone_voice_create_workspace_voice")
        def create_workspace_voice():
            workspace_id = request.form.get("workspaceId", MOCK_WORKSPACE_ID)
            source_mode = request.form.get("sourceMode", "upload").strip().lower()
            audio_file = request.files.get("audio")

            display_name_input = (
                request.form.get("voiceDisplayName", "")
                or request.form.get("displayName", "")
                or request.form.get("voiceName", "")
            ).strip()

            gender = normalize_gender(request.form.get("gender"))

            print("\n" + "=" * 100, flush=True)
            print("[clone_voice_controller] CREATE WORKSPACE VOICE ONLY", flush=True)
            print("workspaceId:", repr(workspace_id), flush=True)
            print("sourceMode:", repr(source_mode), flush=True)
            print("displayName:", repr(display_name_input), flush=True)
            print("gender:", repr(gender), flush=True)
            if audio_file:
                print("audio.filename:", repr(audio_file.filename), flush=True)
                print("audio.mimetype:", repr(audio_file.mimetype), flush=True)
            print("=" * 100 + "\n", flush=True)

            if source_mode not in {"upload", "record"}:
                return _error("Voice creation only supports upload or record source mode", 400)

            if audio_file is None or not audio_file.filename:
                return _error("Missing uploaded or recorded audio file under field name 'audio'", 400)

            is_recording = source_mode == "record"
            workspace = get_workspace(workspace_id)

            raw_source_path = None
            limited_source_path = None

            try:
                if is_recording:
                    voice_id = new_recorded_voice_id()
                else:
                    voice_id = voice_id_from_source_filename(audio_file.filename)

                display_name = display_name_input or display_name_from_voice_id(voice_id)
                preview_path = stable_preview_path(workspace, voice_id)
                max_seconds = get_max_voice_source_seconds()

                raw_source_path = save_source_audio(audio_file, workspace)

                existing_parameter = voice_parameter_exists(workspace, voice_id)
                parameter_created = False
                preview_created = False

                if existing_parameter and not is_recording:
                    print("[clone_voice_controller] Uploaded voice already exists. Reusing parameter:", voice_id, flush=True)
                    voice_parameter, param_path = load_workspace_voice_parameter(workspace, voice_id)
                else:
                    limited_source_path = source_limited_path(workspace, voice_id)

                    limit_audio_to_max_seconds(
                        input_path=raw_source_path,
                        output_path=limited_source_path,
                        max_seconds=max_seconds,
                    )

                    voice_parameter = create_voice_parameter(limited_source_path, "audio/wav")
                    voice_id, param_path = save_voice_parameter(workspace, voice_parameter, voice_id)
                    parameter_created = True

                metadata_before = load_voice_metadata(workspace, voice_id)
                preview_is_standard = (
                    preview_path.exists()
                    and metadata_before.get("previewKind") == "standard_synthesized"
                )

                if is_recording or not preview_is_standard:
                    _generate_standard_preview(voice_parameter, preview_path)
                    preview_created = True
                else:
                    print("[clone_voice_controller] Standard preview already exists. Reusing:", preview_path, flush=True)

                metadata, metadata_path = save_voice_metadata(
                    workspace,
                    voice_id,
                    display_name,
                    gender,
                    source_type="record" if is_recording else "upload",
                    parameter_path=param_path,
                    preview_path=preview_path,
                    parameter_created=parameter_created,
                    preview_created=preview_created,
                )

                return jsonify({
                    "ok": True,
                    "operation": "create_voice",
                    "message": "Voice saved. Select it from My saved voices to generate narration.",
                    "sourceType": "record" if is_recording else "upload",
                    "workspaceId": workspace.workspace_id,
                    "voiceId": voice_id,
                    "displayName": metadata["displayName"],
                    "gender": metadata["gender"],
                    "label": metadata["label"],
                    "voiceParamPath": relative_to_root(param_path),
                    "voicePreviewPath": relative_to_root(preview_path),
                    "voicePreviewUrl": workspace_voice_preview_url(workspace, preview_path),
                    "voiceMetadataPath": relative_to_root(metadata_path),
                    "previewText": STANDARD_VOICE_PREVIEW_TEXT,
                    "parameterCreated": parameter_created,
                    "previewCreated": preview_created,
                    "maxVoiceSourceSeconds": max_seconds,
                    "rawSourceDeleted": True,
                })

            except Exception as exc:
                print("[clone_voice_controller] create workspace voice error:", repr(exc), flush=True)
                return _error(str(exc), 500)

            finally:
                delete_if_exists(raw_source_path)
                delete_if_exists(limited_source_path)

'''

    controller = controller.replace(marker, route + marker, 1)

CONTROLLER.write_text(controller, encoding="utf-8")

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/client.css?v=step11-decouple">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p>Create reusable workspace voices, preview them, then generate narration from a saved or system voice.</p>
      <p class="mini-link"><a href="/admin/clone-voice">Admin settings</a></p>
    </header>

    <form id="cloneVoiceForm" class="card">
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

      <section>
        <h2>1. Create or choose voice</h2>

        <div class="mode-grid">
          <label><input type="radio" name="sourceMode" value="upload" checked> Upload audio</label>
          <label><input type="radio" name="sourceMode" value="record"> Record voice</label>
          <label><input type="radio" name="sourceMode" value="saved"> My saved voices</label>
          <label><input type="radio" name="sourceMode" value="system"> System voices</label>
        </div>

        <div id="uploadPanel" class="source-panel">
          <label>
            Upload voice source
            <input id="audioFile" type="file" accept="audio/*">
          </label>
          <p class="status">Uploaded files are used only to create or reuse a saved voice. Narration is generated later from My saved voices.</p>
        </div>

        <div id="recordPanel" class="source-panel hidden">
          <div class="button-row">
            <button id="startRecordingBtn" type="button">Start recording</button>
            <button id="stopRecordingBtn" type="button" disabled>Stop</button>
            <button id="discardRecordingBtn" type="button" disabled>Discard</button>
          </div>

          <p class="status" id="recordingStatus">Start recording, speak clearly, then stop.</p>
          <div class="record-timer" id="recordingTimer" aria-live="polite">0.0s / 20s</div>

          <div class="mic-meter" id="micMeter" aria-label="Microphone input level">
            <span class="mic-meter-label">Mic signal</span>
            <div class="mic-meter-track">
              <div class="mic-meter-fill" id="micMeterFill"></div>
            </div>
            <span class="mic-meter-value" id="micMeterValue">silent</span>
          </div>

          <p class="status">Each recording creates a new saved voice. Narration is generated later from My saved voices.</p>
        </div>

        <div id="voiceCreatePanel" class="voice-create-grid">
          <label>
            Voice display name
            <input id="voiceDisplayName" type="text" placeholder="Example: Bobga, Ngozi">
          </label>

          <label>
            Voice gender
            <select id="voiceGender">
              <option value="U">Unspecified (U)</option>
              <option value="M">Male (M)</option>
              <option value="F">Female (F)</option>
            </select>
          </label>

          <button id="saveVoiceBtn" type="button">Save voice</button>
        </div>

        <div id="savedPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="savedGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
                <option value="U">Unspecified voices</option>
              </select>
            </label>
            <button id="refreshSavedBtn" type="button">Refresh saved voices</button>
          </div>
          <div id="savedVoicesList" class="voice-list">Loading saved voices...</div>
        </div>

        <div id="systemPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="systemGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
                <option value="U">Unspecified voices</option>
              </select>
            </label>
            <button id="refreshSystemBtn" type="button">Refresh system voices</button>
          </div>
          <div id="systemVoicesList" class="voice-list">Loading system voices...</div>
        </div>
      </section>

      <section>
        <h2>2. Narration</h2>

        <div class="narration-top-grid">
          <label>
            Narration title
            <input id="titleInput" type="text" placeholder="Example: NewAge" required>
          </label>

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
        </div>

        <label>
          Text to narrate
          <textarea id="promptInput" rows="8" placeholder="Paste the narration text here..." required></textarea>
        </label>

        <p class="status">Narration can only be generated from My saved voices or System voices.</p>

        <button id="submitBtn" type="submit">Generate narration</button>
      </section>
    </form>

    <section class="card">
      <h2>Result</h2>
      <audio id="audioPlayer" controls class="hidden"></audio>
      <p><a id="downloadLink" class="hidden" href="#" download>Download narration</a></p>
      <div id="resultBox" class="result-summary">No request sent yet.</div>
    </section>
  </main>

  <script src="/clone_voice/client.js?v=step11-decouple"></script>
</body>
</html>
''', encoding="utf-8")

CSS.write_text(r'''* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 32px;
  font-family: Arial, sans-serif;
  background: #071017;
  color: #e8f1f8;
}

.shell {
  max-width: 1100px;
  margin: 0 auto;
  display: grid;
  gap: 22px;
}

.hero,
.card {
  border: 1px solid #33414c;
  border-radius: 18px;
  padding: 22px;
  background: #111b24;
}

.eyebrow,
.status,
.mini-link {
  color: #a9bfd3;
  line-height: 1.55;
}

h1,
h2,
p {
  margin-top: 0;
}

a {
  color: #9ee8dc;
  font-weight: 900;
  text-decoration: none;
}

label {
  display: grid;
  gap: 8px;
  font-weight: 800;
}

input,
textarea,
select,
button {
  font: inherit;
}

input[type="text"],
input[type="file"],
textarea,
select {
  width: 100%;
  border: 1px solid #465662;
  border-radius: 12px;
  padding: 12px;
  background: #202b35;
  color: #fff;
}

textarea {
  resize: vertical;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 13px 20px;
  background: linear-gradient(135deg, #9ee8dc, #82a8ff);
  color: #06130f;
  font-weight: 900;
  cursor: pointer;
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.delete-voice-btn {
  background: linear-gradient(135deg, #ffb3b3, #ff7676);
  color: #2b0505;
}

.hidden {
  display: none !important;
}

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

.mode-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0 18px;
}

.mode-grid label {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #33414c;
  border-radius: 14px;
  padding: 12px;
  background: #071017;
}

.source-panel {
  display: grid;
  gap: 14px;
  margin: 16px 0;
}

.voice-create-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.3fr) 180px auto;
  gap: 16px;
  align-items: end;
  margin: 16px 0 22px;
  padding: 16px;
  border: 1px solid #33414c;
  border-radius: 16px;
  background: #071017;
}

.narration-top-grid {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 200px;
  gap: 16px;
  align-items: end;
  margin: 8px 0 18px;
}

.button-row,
.list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
}

.list-toolbar label {
  min-width: 220px;
}

.record-timer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-width: 150px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid #465662;
  background: #071017;
  color: #9ee8dc;
  font-weight: 900;
  letter-spacing: .04em;
}

.mic-meter {
  display: grid;
  grid-template-columns: auto minmax(140px, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #465662;
  border-radius: 14px;
  background: #071017;
}

.mic-meter-label,
.mic-meter-value {
  color: #a9bfd3;
  font-size: 0.92rem;
  font-weight: 800;
  white-space: nowrap;
}

.mic-meter-track {
  position: relative;
  width: 100%;
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: #1e2a34;
  border: 1px solid #33414c;
}

.mic-meter-fill {
  width: 0%;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #9ee8dc, #82a8ff);
  transition: width 80ms linear;
}

.mic-meter.is-active .mic-meter-value {
  color: #9ee8dc;
}

.mic-meter.is-loud .mic-meter-fill {
  background: linear-gradient(90deg, #9ee8dc, #ffd166);
}

.voice-list {
  display: grid;
  gap: 10px;
}

.voice-card {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 12px;
  align-items: center;
  border: 1px solid #33414c;
  border-radius: 14px;
  padding: 12px;
  background: #071017;
}

.voice-card-title {
  display: block;
  font-weight: 900;
  color: #e8f1f8;
}

.voice-card-meta {
  display: block;
  color: #a9bfd3;
  font-size: .9rem;
  margin-top: 4px;
}

.preview-btn {
  padding: 9px 14px;
}

.result-summary {
  display: grid;
  gap: 10px;
  background: #02070b;
  border: 1px solid #33414c;
  border-radius: 12px;
  padding: 16px;
  color: #dceaf5;
  line-height: 1.55;
}

.result-summary strong {
  color: #9ee8dc;
}

.result-summary .muted {
  color: #a9bfd3;
}

.result-grid {
  display: grid;
  gap: 8px;
}

.result-row {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr);
  gap: 12px;
}

.result-label {
  color: #a9bfd3;
  font-weight: 800;
}

.result-value {
  overflow-wrap: anywhere;
}

audio {
  width: 100%;
}

@media (max-width: 900px) {
  body {
    padding: 18px;
  }

  .mode-grid,
  .voice-create-grid,
  .narration-top-grid,
  .voice-card {
    grid-template-columns: 1fr;
  }

  .mic-meter {
    grid-template-columns: 1fr;
  }

  .result-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  button {
    width: 100%;
  }
}
''', encoding="utf-8")

JS.write_text(r'''(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const form = $("#cloneVoiceForm");
  const workspaceSelect = $("#workspaceSelect");
  const workspaceStatus = $("#workspaceStatus");

  const sourceModeInputs = $$('input[name="sourceMode"]');

  const uploadPanel = $("#uploadPanel");
  const recordPanel = $("#recordPanel");
  const savedPanel = $("#savedPanel");
  const systemPanel = $("#systemPanel");
  const voiceCreatePanel = $("#voiceCreatePanel");

  const audioFile = $("#audioFile");
  const voiceDisplayName = $("#voiceDisplayName");
  const voiceGender = $("#voiceGender");
  const saveVoiceBtn = $("#saveVoiceBtn");

  const startRecordingBtn = $("#startRecordingBtn");
  const stopRecordingBtn = $("#stopRecordingBtn");
  const discardRecordingBtn = $("#discardRecordingBtn");
  const recordingStatus = $("#recordingStatus");
  const recordingTimer = $("#recordingTimer");

  const micMeter = $("#micMeter");
  const micMeterFill = $("#micMeterFill");
  const micMeterValue = $("#micMeterValue");

  const savedVoicesList = $("#savedVoicesList");
  const systemVoicesList = $("#systemVoicesList");
  const savedGenderFilter = $("#savedGenderFilter");
  const systemGenderFilter = $("#systemGenderFilter");
  const refreshSavedBtn = $("#refreshSavedBtn");
  const refreshSystemBtn = $("#refreshSystemBtn");

  const titleInput = $("#titleInput");
  const narrationSpeed = $("#narrationSpeed");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const audioPlayer = $("#audioPlayer");
  const downloadLink = $("#downloadLink");
  const resultBox = $("#resultBox");

  let activeWorkspaceId = "mock_user_001";
  let availableWorkspaces = [];

  let maxVoiceSourceSeconds = 20;

  let mediaRecorder = null;
  let micStream = null;
  let audioContext = null;
  let micSource = null;
  let recordedChunks = [];
  let recordedBlob = null;
  let recordedFilename = "";

  let recordingAutoStopTimer = null;
  let recordingTicker = null;
  let recordingStartedAt = 0;

  let micAnalyserNode = null;
  let micMeterData = null;
  let micMeterAnimationFrame = null;

  let savedVoices = [];
  let systemVoices = [];
  let pendingSelectSavedVoiceId = "";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function selectedMode() {
    return sourceModeInputs.find((input) => input.checked)?.value || "upload";
  }

  function setMode(mode) {
    uploadPanel.classList.toggle("hidden", mode !== "upload");
    recordPanel.classList.toggle("hidden", mode !== "record");
    savedPanel.classList.toggle("hidden", mode !== "saved");
    systemPanel.classList.toggle("hidden", mode !== "system");
    voiceCreatePanel.classList.toggle("hidden", !(mode === "upload" || mode === "record"));

    if (mode === "saved") loadSavedVoices();
    if (mode === "system") loadSystemVoices();
  }

  function setSelectedMode(mode) {
    const input = sourceModeInputs.find((item) => item.value === mode);
    if (input) input.checked = true;
    setMode(mode);
  }

  function fallbackWorkspaces() {
    return [
      { workspaceId: "mock_user_001", label: "Client A / Workspace 001" },
      { workspaceId: "mock_user_002", label: "Client B / Workspace 002" },
    ];
  }

  function setWorkspaceStatus() {
    const label = availableWorkspaces.find((row) => row.workspaceId === activeWorkspaceId)?.label || activeWorkspaceId;

    workspaceStatus.textContent = `Active workspace: ${label}. Saved voices, previews, metadata, and generated narrations are isolated to ${activeWorkspaceId}. System voices remain global.`;
  }

  function renderWorkspaceOptions() {
    workspaceSelect.innerHTML = availableWorkspaces.map((row) => `
      <option value="${escapeHtml(row.workspaceId)}">${escapeHtml(row.label || row.workspaceId)}</option>
    `).join("");

    workspaceSelect.value = activeWorkspaceId;
  }

  async function loadWorkspaces() {
    try {
      const response = await fetch(`/api/clone-voice/workspaces?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load workspaces");
      }

      availableWorkspaces = data.workspaces && data.workspaces.length ? data.workspaces : fallbackWorkspaces();
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
    savedVoicesList.textContent = `Loading saved voices for ${activeWorkspaceId}...`;

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
          <div class="result-label">Isolation</div>
          <div class="result-value">Saved voices are now loaded only from this workspace.</div>
        </div>
      </div>
    `;

    await loadSavedVoices();
  }

  function filenameFromPath(value) {
    const text = String(value || "");
    if (!text) return "";
    const parts = text.split("/");
    return parts[parts.length - 1] || text;
  }

  function renderFriendlyResult(data) {
    const rows = [
      ["Narration", filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl) || ""],
      ["Workspace", data.workspaceId || activeWorkspaceId],
      ["Title", data.narrationTitle || ""],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Source", data.sourceType || ""],
      ["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],
      ["Volume normalized", data.volumeNormalized ? "Yes" : ""],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Narration generated successfully.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Narration is generated only from a saved voice or a system voice.</div>
    `;
  }

  function renderVoiceSavedResult(data) {
    const rows = [
      ["Workspace", data.workspaceId || activeWorkspaceId],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Source", data.sourceType || ""],
      ["Max voice sample", data.maxVoiceSourceSeconds ? `${data.maxVoiceSourceSeconds} seconds` : ""],
      ["Parameter", data.parameterCreated ? "Created" : "Reused existing"],
      ["Preview", data.previewCreated ? "Created" : "Reused existing"],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Voice saved successfully.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Select this voice from My saved voices to generate narration.</div>
    `;
  }

  async function loadCloneVoiceSettings() {
    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (response.ok && data.ok && data.maxVoiceSourceSeconds) {
        maxVoiceSourceSeconds = Number(data.maxVoiceSourceSeconds) || 20;
      }
    } catch (error) {
      console.warn("[Clone Voice] Could not load settings:", error);
    }

    renderRecordingTimer(0);
    recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
  }

  function renderRecordingTimer(elapsedSeconds = 0) {
    const safeElapsed = Math.max(0, Number(elapsedSeconds) || 0);
    const safeMax = Math.max(1, Number(maxVoiceSourceSeconds || 20));
    recordingTimer.textContent = `${safeElapsed.toFixed(1)}s / ${safeMax}s`;
    recordingTimer.setAttribute("title", `${Math.max(0, safeMax - safeElapsed).toFixed(1)} seconds remaining`);
  }

  function clearRecordingTicker() {
    if (recordingTicker) {
      clearInterval(recordingTicker);
      recordingTicker = null;
    }
  }

  function startRecordingTicker() {
    clearRecordingTicker();
    recordingStartedAt = Date.now();
    renderRecordingTimer(0);

    recordingTicker = setInterval(() => {
      const elapsed = (Date.now() - recordingStartedAt) / 1000;
      renderRecordingTimer(Math.min(elapsed, maxVoiceSourceSeconds));
    }, 100);
  }

  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }
    clearRecordingTicker();
  }

  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();
    startRecordingTicker();

    recordingAutoStopTimer = setTimeout(() => {
      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }

  function renderMicLevel(level) {
    const safeLevel = Math.max(0, Math.min(1, Number(level) || 0));
    const percent = Math.round(safeLevel * 100);

    micMeterFill.style.width = `${percent}%`;
    micMeter.classList.toggle("is-active", safeLevel > 0.08);
    micMeter.classList.toggle("is-loud", safeLevel > 0.72);

    if (safeLevel < 0.04) {
      micMeterValue.textContent = "silent";
    } else if (safeLevel < 0.18) {
      micMeterValue.textContent = "low";
    } else if (safeLevel < 0.72) {
      micMeterValue.textContent = "good";
    } else {
      micMeterValue.textContent = "loud";
    }
  }

  function stopMicMeter() {
    if (micMeterAnimationFrame) {
      cancelAnimationFrame(micMeterAnimationFrame);
      micMeterAnimationFrame = null;
    }

    try {
      if (micAnalyserNode) micAnalyserNode.disconnect();
    } catch {}

    micAnalyserNode = null;
    micMeterData = null;
    renderMicLevel(0);
  }

  function startMicMeter(sourceNode, ctx) {
    stopMicMeter();

    micAnalyserNode = ctx.createAnalyser();
    micAnalyserNode.fftSize = 2048;
    micAnalyserNode.smoothingTimeConstant = 0.82;
    micMeterData = new Uint8Array(micAnalyserNode.fftSize);

    sourceNode.connect(micAnalyserNode);

    const tick = () => {
      if (!micAnalyserNode || !micMeterData) {
        renderMicLevel(0);
        return;
      }

      micAnalyserNode.getByteTimeDomainData(micMeterData);

      let sumSquares = 0;

      for (let index = 0; index < micMeterData.length; index += 1) {
        const centered = (micMeterData[index] - 128) / 128;
        sumSquares += centered * centered;
      }

      const rms = Math.sqrt(sumSquares / micMeterData.length);
      renderMicLevel(Math.min(1, rms * 4.5));

      micMeterAnimationFrame = requestAnimationFrame(tick);
    };

    tick();
  }

  async function startRecording() {
    try {
      recordedChunks = [];
      recordedBlob = null;
      recordedFilename = "";

      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      micSource = audioContext.createMediaStreamSource(micStream);
      startMicMeter(micSource, audioContext);

      const options = MediaRecorder.isTypeSupported("audio/webm") ? { mimeType: "audio/webm" } : undefined;

      mediaRecorder = new MediaRecorder(micStream, options);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", () => {
        const mimeType = mediaRecorder.mimeType || "audio/webm";
        recordedBlob = new Blob(recordedChunks, { type: mimeType });
        recordedFilename = `recorded_voice_${Date.now()}.webm`;

        recordingStatus.textContent = `Recording ready. Click Save voice to create a reusable saved voice.`;
        discardRecordingBtn.disabled = false;
      });

      mediaRecorder.start();

      startRecordingBtn.disabled = true;
      stopRecordingBtn.disabled = false;
      discardRecordingBtn.disabled = true;
      recordingStatus.textContent = `Recording... auto-stops at ${maxVoiceSourceSeconds} seconds.`;

      startRecordingAutoStopTimer();
    } catch (error) {
      recordingStatus.textContent = error.message || String(error);
      stopMicMeter();
      clearRecordingAutoStopTimer();
    }
  }

  function stopRecording() {
    const elapsedBeforeStop = recordingStartedAt
      ? Math.min((Date.now() - recordingStartedAt) / 1000, maxVoiceSourceSeconds)
      : 0;

    clearRecordingAutoStopTimer();
    renderRecordingTimer(elapsedBeforeStop);
    stopMicMeter();

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    if (audioContext) {
      audioContext.close().catch(() => {});
    }

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
  }

  function discardRecording() {
    stopMicMeter();
    clearRecordingAutoStopTimer();

    recordedChunks = [];
    recordedBlob = null;
    recordedFilename = "";

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    recordingStatus.textContent = "Start recording, speak clearly, then stop.";
    renderRecordingTimer(0);

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
    discardRecordingBtn.disabled = true;
  }

  function filteredVoices(voices, genderFilter) {
    const filter = genderFilter || "";
    if (!filter) return voices;
    return voices.filter((voice) => String(voice.gender || "U").toUpperCase() === filter);
  }

  function renderVoiceList(container, voices, groupName, genderFilter) {
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

    if (pendingSelectSavedVoiceId && groupName === "savedVoiceId") {
      const input = container.querySelector(`input[value="${CSS.escape(pendingSelectSavedVoiceId)}"]`);
      if (input) {
        input.checked = true;
        pendingSelectSavedVoiceId = "";
      }
    }
  }

  async function loadSavedVoices() {
    savedVoicesList.textContent = `Loading saved voices for ${activeWorkspaceId}...`;

    try {
      const response = await fetch(`/api/clone-voice/my-voices?workspaceId=${encodeURIComponent(activeWorkspaceId)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load saved voices");
      }

      savedVoices = data.voices || [];
      renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
    } catch (error) {
      savedVoicesList.textContent = error.message || String(error);
    }
  }

  async function loadSystemVoices() {
    systemVoicesList.textContent = "Loading system voices...";

    try {
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      systemVoices = data.voices || [];
      renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
    } catch (error) {
      systemVoicesList.textContent = error.message || String(error);
    }
  }

  function selectedVoiceId(groupName) {
    return document.querySelector(`input[name="${groupName}"]:checked`)?.value || "";
  }

  async function playPreview(url) {
    if (!url) return;

    audioPlayer.classList.remove("hidden");
    audioPlayer.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    await audioPlayer.play().catch(() => {});
  }

  async function saveClientVoice() {
    const mode = selectedMode();

    if (mode !== "upload" && mode !== "record") {
      alert("Switch to Upload audio or Record voice to save a new voice.");
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("sourceMode", mode);
    formData.append("voiceDisplayName", voiceDisplayName.value.trim());
    formData.append("gender", voiceGender.value || "U");

    if (mode === "upload") {
      const file = audioFile.files[0];

      if (!file) {
        alert("Choose an audio file first.");
        return;
      }

      formData.append("audio", file, file.name);
    }

    if (mode === "record") {
      if (!recordedBlob) {
        alert("Record a voice first.");
        return;
      }

      formData.append("audio", recordedBlob, recordedFilename || "recorded_voice.webm");
    }

    saveVoiceBtn.disabled = true;
    saveVoiceBtn.textContent = "Saving voice...";
    resultBox.textContent = "Saving voice and generating standard preview...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      const response = await fetch("/api/clone-voice/voices/from-source", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log("[Clone Voice saved voice response]", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save voice");
      }

      renderVoiceSavedResult(data);

      if (data.voicePreviewUrl) {
        audioPlayer.src = `${data.voicePreviewUrl}${data.voicePreviewUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");
      }

      pendingSelectSavedVoiceId = data.voiceId || "";
      await loadSavedVoices();
      setSelectedMode("saved");
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      saveVoiceBtn.disabled = false;
      saveVoiceBtn.textContent = "Save voice";
    }
  }

  async function deleteSavedVoice(voiceId, label) {
    const ok = confirm(`Delete saved voice: ${label || voiceId}?`);

    if (!ok) return;

    resultBox.textContent = `Deleting saved voice: ${label || voiceId}...`;

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voiceId)}?workspaceId=${encodeURIComponent(activeWorkspaceId)}`,
        { method: "DELETE" }
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

  async function submitForm(event) {
    event.preventDefault();

    const mode = selectedMode();

    if (mode === "upload" || mode === "record") {
      alert("Save the voice first. Then select it from My saved voices to generate narration.");
      return;
    }

    const title = titleInput.value.trim();
    const prompt = promptInput.value.trim();

    if (!title) {
      alert("Enter a narration title.");
      return;
    }

    if (!prompt) {
      alert("Enter narration text.");
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("title", title);
    formData.append("prompt", prompt);
    formData.append("sourceMode", mode);
    formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");

    let endpoint = "";

    if (mode === "saved") {
      const voiceId = selectedVoiceId("savedVoiceId");

      if (!voiceId) {
        alert("Choose a saved voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-saved";
      formData.append("voiceId", voiceId);
    }

    if (mode === "system") {
      const voiceId = selectedVoiceId("systemVoiceId");

      if (!voiceId) {
        alert("Choose a system voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-system";
      formData.append("voiceId", voiceId);
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";
    resultBox.textContent = "Generating narration...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log("[Clone Voice narration response]", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Narration failed");
      }

      const audioUrl = data.audioUrl || data.assetUrl;

      if (audioUrl) {
        audioPlayer.src = `${audioUrl}${audioUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");

        downloadLink.href = audioUrl;
        downloadLink.classList.remove("hidden");
      }

      renderFriendlyResult(data);
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Generate narration";
    }
  }

  sourceModeInputs.forEach((input) => {
    input.addEventListener("change", () => setMode(selectedMode()));
  });

  workspaceSelect.addEventListener("change", () => {
    switchWorkspace(workspaceSelect.value);
  });

  saveVoiceBtn.addEventListener("click", saveClientVoice);

  startRecordingBtn.addEventListener("click", startRecording);
  stopRecordingBtn.addEventListener("click", stopRecording);
  discardRecordingBtn.addEventListener("click", discardRecording);

  refreshSavedBtn.addEventListener("click", loadSavedVoices);
  refreshSystemBtn.addEventListener("click", loadSystemVoices);

  savedGenderFilter.addEventListener("change", () => {
    renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
  });

  systemGenderFilter.addEventListener("change", () => {
    renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
  });

  document.addEventListener("click", (event) => {
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
  });

  form.addEventListener("submit", submitForm);

  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadWorkspaces();
  loadSystemVoices();
  setMode("upload");
})();
''', encoding="utf-8")

py_compile.compile(str(CONTROLLER), doraise=True)

print()
print("STEP 11 COMPLETE: client voice creation is decoupled from narration.")
print()
print("New client flow:")
print("  Upload / Record -> Save voice only")
print("  My saved voices / System voices -> Generate narration")
print()
print("New API:")
print("  POST /api/clone-voice/voices/from-source")
print()
print("Existing narration APIs remain:")
print("  POST /api/clone-voice/from-saved")
print("  POST /api/clone-voice/from-system")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?step11-decouple=1")
