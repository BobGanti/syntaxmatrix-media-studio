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
    print("ERROR: Client frontend files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step12-ui-cleanup-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

# -------------------------------------------------------------------
# HTML cleanup:
# - remove Admin settings link from client
# - remove long workspace metadata text
# - add section classes for better colored panels
# -------------------------------------------------------------------
html = HTML.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<p class="mini-link"><a href="/admin/clone-voice">Admin settings</a></p>',
    "",
    html,
    count=1,
)

html = re.sub(
    r'\s*<p class="status" id="workspaceStatus">[\s\S]*?</p>',
    "",
    html,
    count=1,
)

html = html.replace(
    '<section>\n        <h2>1. Create or choose voice</h2>',
    '<section class="voice-flow-panel">\n        <h2>1. Create or choose voice</h2>',
    1,
)

html = html.replace(
    '<section>\n        <h2>2. Narration</h2>',
    '<section class="narration-flow-panel">\n        <h2>2. Narration</h2>',
    1,
)

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=ui-cleanup-icons-colors-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=ui-cleanup-icons-colors-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

# -------------------------------------------------------------------
# JS cleanup:
# - workspaceStatus may no longer exist
# - no "Standard preview sentence" text on voice cards
# - icon-only preview/delete buttons
# -------------------------------------------------------------------
js = JS.read_text(encoding="utf-8")

js = js.replace(
    '''    workspaceStatus.textContent = `Active workspace: ${label}. Saved voices, previews, metadata, and generated narrations are isolated to ${activeWorkspaceId}. System voices remain global.`;''',
    '''    if (workspaceStatus) {
      workspaceStatus.textContent = `Active workspace: ${label}`;
    }''',
)

js = js.replace(
    '''      const previewButton = voice.previewUrl
        ? `<button class="preview-btn" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}">Preview</button>`
        : `<span class="voice-card-meta">No preview</span>`;''',
    '''      const previewButton = voice.previewUrl
        ? `<button class="icon-btn icon-btn-play" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}" aria-label="Play voice preview" title="Play preview">
             <span aria-hidden="true">▶</span>
           </button>`
        : `<span class="voice-card-empty"></span>`;''',
)

js = js.replace(
    '''      const deleteButton = isSavedVoiceList
        ? `<button class="preview-btn delete-voice-btn" type="button" data-delete-saved-voice-id="${escapeHtml(voice.voiceId)}" data-delete-saved-voice-label="${escapeHtml(voice.label || voice.displayName || voice.voiceId)}">Delete</button>`
        : "";''',
    '''      const deleteButton = isSavedVoiceList
        ? `<button class="icon-btn icon-btn-delete" type="button" data-delete-saved-voice-id="${escapeHtml(voice.voiceId)}" data-delete-saved-voice-label="${escapeHtml(voice.label || voice.displayName || voice.voiceId)}" aria-label="Delete saved voice" title="Delete voice">
             <span aria-hidden="true">🗑</span>
           </button>`
        : "";''',
)

js = js.replace(
    '''          <span>
            <span class="voice-card-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</span>
            <span class="voice-card-meta">Standard preview sentence</span>
          </span>''',
    '''          <span>
            <span class="voice-card-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</span>
          </span>''',
)

JS.write_text(js, encoding="utf-8")

# -------------------------------------------------------------------
# CSS cleanup:
# - color panels
# - icon buttons
# - less monotonous client surface
# -------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8")

if ".voice-flow-panel" not in css:
    css += r'''

/* Step 12: client UI polish */

.hero {
  background:
    radial-gradient(circle at 12% 20%, rgba(158, 232, 220, 0.18), transparent 30%),
    radial-gradient(circle at 90% 10%, rgba(130, 168, 255, 0.16), transparent 32%),
    #111b24;
}

.workspace-section {
  border-color: rgba(158, 232, 220, 0.35);
  background:
    linear-gradient(135deg, rgba(158, 232, 220, 0.10), rgba(130, 168, 255, 0.05)),
    #071017;
}

.voice-flow-panel,
.narration-flow-panel {
  border: 1px solid #33414c;
  border-radius: 18px;
  padding: 18px;
  margin: 18px 0;
}

.voice-flow-panel {
  background:
    linear-gradient(135deg, rgba(158, 232, 220, 0.08), rgba(7, 16, 23, 0.9)),
    #071017;
  border-color: rgba(158, 232, 220, 0.28);
}

.narration-flow-panel {
  background:
    linear-gradient(135deg, rgba(130, 168, 255, 0.09), rgba(7, 16, 23, 0.92)),
    #071017;
  border-color: rgba(130, 168, 255, 0.30);
}

.mode-grid label:nth-child(1) {
  border-color: rgba(158, 232, 220, 0.35);
}

.mode-grid label:nth-child(2) {
  border-color: rgba(255, 209, 102, 0.35);
}

.mode-grid label:nth-child(3) {
  border-color: rgba(130, 168, 255, 0.38);
}

.mode-grid label:nth-child(4) {
  border-color: rgba(212, 167, 255, 0.38);
}

.voice-create-grid {
  background:
    linear-gradient(135deg, rgba(255, 209, 102, 0.08), rgba(7, 16, 23, 0.96)),
    #071017;
  border-color: rgba(255, 209, 102, 0.28);
}

.voice-card {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.035), rgba(7, 16, 23, 0.96)),
    #071017;
  border-color: rgba(130, 168, 255, 0.22);
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}

.voice-card:hover {
  transform: translateY(-1px);
  border-color: rgba(158, 232, 220, 0.45);
  background:
    linear-gradient(135deg, rgba(158, 232, 220, 0.075), rgba(7, 16, 23, 0.96)),
    #071017;
}

.voice-card-title {
  font-size: 1.05rem;
}

.voice-card-empty {
  min-width: 44px;
  min-height: 44px;
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
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
}

.icon-btn-play {
  background: linear-gradient(135deg, #9ee8dc, #82a8ff);
  color: #06130f;
}

.icon-btn-delete {
  background: linear-gradient(135deg, #ffb3b3, #ff7676);
  color: #2b0505;
}

.icon-btn:hover {
  filter: brightness(1.06);
  transform: translateY(-1px);
}

.result-summary {
  background:
    linear-gradient(135deg, rgba(158, 232, 220, 0.07), rgba(2, 7, 11, 0.96)),
    #02070b;
}

@media (max-width: 900px) {
  .voice-flow-panel,
  .narration-flow-panel {
    padding: 14px;
  }

  .icon-btn {
    width: 100%;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

print()
print("STEP 12 COMPLETE: client UI cleanup.")
print()
print("Changed:")
print("  Removed Admin settings link from client page")
print("  Removed workspace metadata text from client page")
print("  Removed Standard preview sentence text from voice cards")
print("  Preview/Delete are now icon buttons")
print("  Added colored visual separation to panels")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?ui-cleanup=1")
