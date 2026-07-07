from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()

HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
JS = ROOT / "frontend" / "clone_voice" / "client.js"

required = [HTML, CSS, JS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Clean Clone Voice frontend not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.hide-json-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

html = HTML.read_text(encoding="utf-8")

html = re.sub(
    r'<pre id="resultBox">[\s\S]*?</pre>',
    '<div id="resultBox" class="result-summary">No request sent yet.</div>',
    html,
    count=1,
)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=hide-json-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")

if ".result-summary" not in css:
    css += r'''

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

.result-summary .result-grid {
  display: grid;
  gap: 8px;
}

.result-summary .result-row {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 12px;
}

.result-summary .result-label {
  color: #a9bfd3;
  font-weight: 800;
}

.result-summary .result-value {
  overflow-wrap: anywhere;
}

@media (max-width: 720px) {
  .result-summary .result-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

js = JS.read_text(encoding="utf-8")

if "function filenameFromPath" not in js:
    marker = "form.addEventListener(\"submit\", async (event) => {"

    if marker not in js:
        print("ERROR: Could not find submit handler in client.js.")
        raise SystemExit(1)

    helper = r'''function filenameFromPath(value) {
    const text = String(value || "");
    if (!text) return "";
    const parts = text.split("/");
    return parts[parts.length - 1] || text;
  }

  function renderFriendlyResult(data) {
    const sourceType = data.sourceType || "voice";
    const voiceId = data.voiceId || "";
    const outputName = filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl);
    const title = data.narrationTitle || "";
    const maxSeconds = data.maxVoiceSourceSeconds || "";
    const normalized = data.volumeNormalized ? "Yes" : "No";

    const rows = [
      ["Narration", outputName || "Ready"],
      ["Title", title],
      ["Voice", voiceId],
      ["Source", sourceType],
      ["Max voice sample", maxSeconds ? `${maxSeconds} seconds` : ""],
      ["Volume normalized", normalized],
    ].filter((row) => row[1]);

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
      <div class="muted">Raw technical response is kept in the browser console only.</div>
    `;
  }

  '''

    js = js.replace(marker, helper + marker, 1)

js = js.replace(
    "resultBox.textContent = JSON.stringify(data, null, 2);",
    "renderFriendlyResult(data);",
)

js = js.replace(
    'resultBox.textContent = "Working... Check Flask terminal for logs.";',
    'resultBox.textContent = "Generating narration..." ;',
)

JS.write_text(js, encoding="utf-8")

print()
print("STEP 4 COMPLETE: client JSON output hidden.")
print()
print("The client now shows a clean result summary instead of raw JSON.")
print("Raw data remains visible in the browser console for debugging.")
print()
print("Frontend-only files changed:")
print("  frontend/clone_voice/client.html")
print("  frontend/clone_voice/client.css")
print("  frontend/clone_voice/client.js")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?hide-json=1")
