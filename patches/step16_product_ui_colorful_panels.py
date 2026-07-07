from pathlib import Path
from datetime import datetime
import re
import shutil
import subprocess

ROOT = Path(".").resolve()

HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [HTML, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Required client files not found:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step16-product-ui-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/clone_voice/client.css?v=product-ui-panels-1">
</head>
<body>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">SyntaxMatrix Media Studio</p>
        <h1>Clone Voice</h1>
        <p>Create reusable voices, preview them, and generate narration from saved or system voices.</p>
      </div>
    </header>

    <form id="cloneVoiceForm" class="product-flow">
      <section class="product-panel panel-workspace">
        <div class="panel-heading">
          <span class="panel-number">1</span>
          <div>
            <h2>Workspace</h2>
            <p>Select the client workspace for saved voices and narrations.</p>
          </div>
        </div>

        <div class="compact-row one">
          <label>
            Active workspace
            <select id="workspaceSelect">
              <option value="mock_user_001">Client A / Workspace 001</option>
              <option value="mock_user_002">Client B / Workspace 002</option>
            </select>
          </label>
        </div>

        <p id="workspaceStatus" class="hidden"></p>
      </section>

      <section class="product-panel panel-create">
        <div class="panel-heading">
          <span class="panel-number">2</span>
          <div>
            <h2>Create Voice</h2>
            <p>Upload or record a source, then save it as a reusable voice.</p>
          </div>
        </div>

        <div class="mode-grid create-mode-grid">
          <label><input type="radio" name="sourceMode" value="upload" checked> Upload audio</label>
          <label><input type="radio" name="sourceMode" value="record"> Record voice</label>
        </div>

        <div id="uploadPanel" class="source-panel">
          <label>
            Upload voice source
            <input id="audioFile" type="file" accept="audio/*">
          </label>
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
        </div>

        <div id="voiceCreatePanel" class="voice-create-grid">
          <label>
            Voice display name
            <input id="voiceDisplayName" type="text" placeholder="Example: Bobga, Ngozi">
          </label>

          <label>
            Voice gender
            <select id="voiceGender" required>
              <option value="">Choose gender</option>
              <option value="M">Male (M)</option>
              <option value="F">Female (F)</option>
            </select>
          </label>

          <button id="saveVoiceBtn" type="button">Save voice</button>
        </div>
      </section>

      <section class="product-panel panel-choose">
        <div class="panel-heading">
          <span class="panel-number">3</span>
          <div>
            <h2>Choose Voice</h2>
            <p>Select a saved workspace voice or a system voice for narration.</p>
          </div>
        </div>

        <div class="mode-grid choose-mode-grid">
          <label><input type="radio" name="sourceMode" value="saved"> My saved voices</label>
          <label><input type="radio" name="sourceMode" value="system"> System voices</label>
        </div>

        <div id="savedPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="savedGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
              </select>
            </label>
            <button id="refreshSavedBtn" type="button">Refresh</button>
          </div>

          <div id="savedVoicesList" class="voice-list">Loading saved voices...</div>

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
          </div>
        </div>

        <div id="systemPanel" class="source-panel hidden">
          <div class="list-toolbar">
            <label>
              Filter
              <select id="systemGenderFilter">
                <option value="">All voices</option>
                <option value="M">Male voices</option>
                <option value="F">Female voices</option>
              </select>
            </label>
            <button id="refreshSystemBtn" type="button">Refresh</button>
          </div>

          <div id="systemVoicesList" class="voice-list">Loading system voices...</div>
        </div>
      </section>

      <section class="product-panel panel-narration">
        <div class="panel-heading">
          <span class="panel-number">4</span>
          <div>
            <h2>Generate Narration</h2>
            <p>Use the selected voice to generate the final narration audio.</p>
          </div>
        </div>

        <div class="narration-top-grid">
          <label>
            Narration title
            <input id="titleInput" type="text" placeholder="Example: ProductIntro" required>
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

          <label>
            Delivery style
            <select id="narrationStyle">
              <option value="natural" selected>Natural</option>
              <option value="clear_presenter">Clear / Presenter</option>
              <option value="dramatic">Dramatic</option>
              <option value="calm">Calm</option>
              <option value="energetic">Energetic</option>
            </select>
          </label>
        </div>

        <label>
          Text to narrate
          <textarea id="promptInput" rows="8" placeholder="Paste the narration text here..." required></textarea>
        </label>

        <button id="submitBtn" class="primary-cta" type="submit">Generate narration</button>
      </section>
    </form>

    <section class="product-panel panel-result">
      <div class="panel-heading">
        <span class="panel-number">✓</span>
        <div>
          <h2>Result</h2>
          <p>Your voice preview or generated narration appears here.</p>
        </div>
      </div>

      <audio id="audioPlayer" controls class="hidden"></audio>
      <p><a id="downloadLink" class="download-link hidden" href="#" download>Download narration</a></p>
      <div id="resultBox" class="result-summary">No request sent yet.</div>
    </section>
  </main>

  <script src="/clone_voice/client.js?v=product-ui-panels-1"></script>
</body>
</html>
''', encoding="utf-8")

CSS.write_text(r'''* { box-sizing: border-box; }

:root {
  --bg: #061019;
  --surface: #0d1824;
  --surface-2: #111f2c;
  --border: rgba(255, 255, 255, 0.12);
  --text: #edf7ff;
  --muted: #a9bfd3;
  --teal: #9ee8dc;
  --blue: #82a8ff;
  --amber: #ffd166;
  --pink: #ff9fc1;
  --purple: #d4a7ff;
  --green: #9ef0b8;
  --danger: #ff7676;
}

body {
  margin: 0;
  padding: 32px;
  font-family: Arial, sans-serif;
  background:
    radial-gradient(circle at 10% 0%, rgba(158, 232, 220, .14), transparent 30%),
    radial-gradient(circle at 90% 10%, rgba(130, 168, 255, .12), transparent 34%),
    radial-gradient(circle at 50% 100%, rgba(212, 167, 255, .10), transparent 32%),
    var(--bg);
  color: var(--text);
}

.shell {
  max-width: 1120px;
  margin: 0 auto;
  display: grid;
  gap: 22px;
}

.hero,
.product-panel {
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 22px;
  background: rgba(13, 24, 36, .92);
  box-shadow: 0 24px 70px rgba(0, 0, 0, .25);
}

.hero {
  display: grid;
  gap: 8px;
  background:
    linear-gradient(135deg, rgba(158, 232, 220, .18), rgba(130, 168, 255, .12)),
    rgba(13, 24, 36, .94);
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--teal);
  font-weight: 900;
  letter-spacing: .06em;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: clamp(2rem, 4vw, 3.4rem);
}

h2 {
  margin-bottom: 4px;
}

h3 {
  margin-bottom: 8px;
}

p,
.status {
  color: var(--muted);
  line-height: 1.55;
}

a {
  color: var(--teal);
  font-weight: 900;
  text-decoration: none;
}

.product-flow {
  display: grid;
  gap: 22px;
}

.panel-heading {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  margin-bottom: 18px;
}

.panel-number {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  color: #071017;
  font-weight: 1000;
  background: linear-gradient(135deg, var(--teal), var(--blue));
}

.panel-workspace {
  background:
    linear-gradient(135deg, rgba(158, 232, 220, .16), rgba(7, 16, 25, .95)),
    var(--surface);
  border-color: rgba(158, 232, 220, .30);
}

.panel-create {
  background:
    linear-gradient(135deg, rgba(255, 209, 102, .15), rgba(7, 16, 25, .96)),
    var(--surface);
  border-color: rgba(255, 209, 102, .30);
}

.panel-create .panel-number {
  background: linear-gradient(135deg, var(--amber), var(--teal));
}

.panel-choose {
  background:
    linear-gradient(135deg, rgba(212, 167, 255, .15), rgba(7, 16, 25, .96)),
    var(--surface);
  border-color: rgba(212, 167, 255, .30);
}

.panel-choose .panel-number {
  background: linear-gradient(135deg, var(--purple), var(--blue));
}

.panel-narration {
  background:
    linear-gradient(135deg, rgba(130, 168, 255, .16), rgba(7, 16, 25, .96)),
    var(--surface);
  border-color: rgba(130, 168, 255, .30);
}

.panel-narration .panel-number {
  background: linear-gradient(135deg, var(--blue), var(--pink));
}

.panel-result {
  background:
    linear-gradient(135deg, rgba(158, 240, 184, .13), rgba(7, 16, 25, .96)),
    var(--surface);
  border-color: rgba(158, 240, 184, .28);
}

.panel-result .panel-number {
  background: linear-gradient(135deg, var(--green), var(--teal));
}

label {
  display: grid;
  gap: 8px;
  color: var(--text);
  font-weight: 900;
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
  border: 1px solid rgba(255, 255, 255, .14);
  border-radius: 16px;
  padding: 13px 14px;
  background: rgba(7, 16, 23, .72);
  color: #fff;
  outline: none;
}

input[type="text"]:focus,
textarea:focus,
select:focus {
  border-color: rgba(158, 232, 220, .72);
  box-shadow: 0 0 0 3px rgba(158, 232, 220, .12);
}

textarea {
  resize: vertical;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 13px 20px;
  background: linear-gradient(135deg, var(--teal), var(--blue));
  color: #06130f;
  font-weight: 1000;
  cursor: pointer;
}

button:hover {
  filter: brightness(1.05);
  transform: translateY(-1px);
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
  transform: none;
}

.primary-cta {
  margin-top: 16px;
  width: fit-content;
  min-width: 230px;
  background: linear-gradient(135deg, var(--blue), var(--pink));
  color: white;
}

.hidden {
  display: none !important;
}

.compact-row.one {
  max-width: 460px;
}

.mode-grid {
  display: grid;
  gap: 12px;
  margin: 14px 0 18px;
}

.create-mode-grid,
.choose-mode-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mode-grid label {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid rgba(255, 255, 255, .13);
  border-radius: 18px;
  padding: 13px 14px;
  background: rgba(7, 16, 23, .56);
  cursor: pointer;
}

.mode-grid label:hover {
  border-color: rgba(158, 232, 220, .42);
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
  margin-top: 18px;
  padding: 16px;
  border: 1px solid rgba(255, 209, 102, .28);
  border-radius: 20px;
  background: rgba(7, 16, 23, .52);
}

.narration-top-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 190px 230px;
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
  border: 1px solid rgba(158, 232, 220, .35);
  background: rgba(7, 16, 23, .76);
  color: var(--teal);
  font-weight: 1000;
  letter-spacing: .04em;
}

.mic-meter {
  display: grid;
  grid-template-columns: auto minmax(140px, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, .13);
  border-radius: 16px;
  background: rgba(7, 16, 23, .62);
}

.mic-meter-label,
.mic-meter-value {
  color: var(--muted);
  font-size: .92rem;
  font-weight: 900;
  white-space: nowrap;
}

.mic-meter-track {
  position: relative;
  width: 100%;
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: #1e2a34;
  border: 1px solid rgba(255, 255, 255, .12);
}

.mic-meter-fill {
  width: 0%;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--teal), var(--blue));
  transition: width 80ms linear;
}

.mic-meter.is-active .mic-meter-value {
  color: var(--teal);
}

.mic-meter.is-loud .mic-meter-fill {
  background: linear-gradient(90deg, var(--teal), var(--amber));
}

.voice-list {
  display: grid;
  gap: 10px;
}

.voice-card {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 52px 52px;
  gap: 12px;
  align-items: center;
  border: 1px solid rgba(130, 168, 255, .24);
  border-radius: 18px;
  padding: 12px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, .05), rgba(7, 16, 23, .88)),
    rgba(7, 16, 23, .64);
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}

.voice-card:hover {
  transform: translateY(-1px);
  border-color: rgba(158, 232, 220, .48);
}

.voice-card > input[type="radio"] {
  justify-self: center;
}

.voice-card-title {
  display: block;
  font-size: 1.05rem;
  font-weight: 1000;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.voice-card-meta {
  display: none;
}

.voice-card-empty {
  min-width: 52px;
  min-height: 52px;
}

.icon-btn {
  width: 52px;
  height: 52px;
  display: inline-grid;
  place-items: center;
  border-radius: 18px;
  padding: 0;
  font-size: 1.25rem;
  line-height: 1;
  border: 1px solid transparent;
  box-shadow: 0 10px 24px rgba(0, 0, 0, .22);
}

.icon-btn-play {
  background: linear-gradient(135deg, var(--teal), var(--blue));
  color: #06130f;
}

.icon-btn-delete {
  background: linear-gradient(135deg, #ffb3b3, var(--danger));
  color: #2b0505;
}

.voice-manage-panel {
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid rgba(255, 209, 102, .35);
  border-radius: 20px;
  background:
    linear-gradient(135deg, rgba(255, 209, 102, .10), rgba(7, 16, 23, .90)),
    rgba(7, 16, 23, .65);
}

.voice-manage-grid,
.voice-replace-grid {
  display: grid;
  gap: 14px;
  align-items: end;
}

.voice-manage-grid {
  grid-template-columns: minmax(200px, 1fr) 180px auto;
}

.voice-replace-grid {
  grid-template-columns: minmax(220px, 1fr) auto;
}

.result-summary {
  display: grid;
  gap: 10px;
  background: rgba(7, 16, 23, .68);
  border: 1px solid rgba(158, 240, 184, .24);
  border-radius: 18px;
  padding: 16px;
  color: #dceaf5;
  line-height: 1.55;
}

.result-summary strong {
  color: var(--green);
}

.result-summary .muted {
  color: var(--muted);
}

.result-grid {
  display: grid;
  gap: 8px;
}

.result-row {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 12px;
}

.result-label {
  color: var(--muted);
  font-weight: 900;
}

.result-value {
  overflow-wrap: anywhere;
}

audio {
  width: 100%;
  margin-bottom: 12px;
}

.download-link {
  display: inline-flex;
  width: fit-content;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(158, 240, 184, .12);
  border: 1px solid rgba(158, 240, 184, .25);
}

@media (max-width: 900px) {
  body {
    padding: 16px;
  }

  .hero,
  .product-panel {
    border-radius: 20px;
    padding: 16px;
  }

  .panel-heading {
    grid-template-columns: 42px minmax(0, 1fr);
  }

  .panel-number {
    width: 42px;
    height: 42px;
    border-radius: 14px;
  }

  .create-mode-grid,
  .choose-mode-grid,
  .voice-create-grid,
  .narration-top-grid,
  .voice-manage-grid,
  .voice-replace-grid {
    grid-template-columns: 1fr;
  }

  .list-toolbar {
    display: grid;
    grid-template-columns: 1fr;
  }

  .list-toolbar button,
  .voice-create-grid button,
  .voice-manage-panel button,
  .primary-cta {
    width: 100%;
  }

  .mic-meter {
    grid-template-columns: 1fr;
  }

  .voice-card {
    grid-template-columns: 22px minmax(0, 1fr) 44px 44px;
    gap: 8px;
    padding: 10px;
  }

  .voice-card .icon-btn {
    width: 44px;
    height: 44px;
    min-width: 44px;
    border-radius: 14px;
  }

  .voice-card-empty {
    display: none;
  }

  .result-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}

@media (max-width: 420px) {
  .voice-card {
    grid-template-columns: 20px minmax(0, 1fr) 40px 40px;
  }

  .voice-card .icon-btn {
    width: 40px;
    height: 40px;
    min-width: 40px;
  }
}
''', encoding="utf-8")

js = JS.read_text(encoding="utf-8")

# Keep result summaries client-friendly and remove developer metadata.
js = re.sub(
    r'''  function renderFriendlyResult\(data\) \{[\s\S]*?\n  \}\n\n  function renderVoiceSavedResult''',
    r'''  function renderFriendlyResult(data) {
    const styleDisplay = data.narrationStyleDisplay || data.narrationStyleLabel || "";
    const rows = [
      ["Title", data.narrationTitle || ""],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],
      ["Style", styleDisplay],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Narration ready.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderVoiceSavedResult''',
    js,
    count=1,
)

js = re.sub(
    r'''  function renderVoiceSavedResult\(data\) \{[\s\S]*?\n  \}\n\n  async function loadCloneVoiceSettings''',
    r'''  function renderVoiceSavedResult(data) {
    const rows = [
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Gender", data.gender || ""],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Voice saved.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Preview is ready. Select this voice under My saved voices to generate narration.</div>
    `;
  }

  async function loadCloneVoiceSettings''',
    js,
    count=1,
)

JS.write_text(js, encoding="utf-8")

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
print("STEP 16 COMPLETE: product UI with colorful panels.")
print()
print("Changed:")
print("  Reorganized client into Workspace / Create Voice / Choose Voice / Generate Narration")
print("  Added colorful panel styling")
print("  Kept mobile voice rows compact with play/bin icons on the same line")
print("  Removed developer metadata from main result summaries")
print()
print("No backend files were changed.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?product-ui-panels=1")
