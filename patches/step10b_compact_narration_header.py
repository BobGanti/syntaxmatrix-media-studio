from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()

HTML = ROOT / "frontend" / "clone_voice" / "client.html"
CSS = ROOT / "frontend" / "clone_voice" / "client.css"

required = [HTML, CSS]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Client frontend files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step10b-compact-header-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

html = HTML.read_text(encoding="utf-8")

# Remove old voice details panel from the voice-source area.
html = re.sub(
    r'\n\s*<div id="voiceDetailsPanel" class="voice-details">[\s\S]*?</div>\s*',
    '\n',
    html,
    count=1,
)

# Remove old Narration title field from its own full-width row.
html = re.sub(
    r'\n\s*<label>\s*Narration title\s*<input id="titleInput"[\s\S]*?</label>\s*',
    '\n',
    html,
    count=1,
)

# Remove old Narration speed field from its own full-width row.
html = re.sub(
    r'\n\s*<label>\s*Narration speed\s*<select id="narrationSpeed">[\s\S]*?</select>\s*</label>\s*',
    '\n',
    html,
    count=1,
)

compact_row = r'''
        <div class="narration-top-grid">
          <div id="voiceDetailsPanel" class="voice-details-inline">
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
          </div>

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
'''

if 'class="narration-top-grid"' not in html:
    html = html.replace(
        '        <h2>2. Narration</h2>',
        '        <h2>2. Narration</h2>' + compact_row,
        1,
    )

html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=compact-narration-header-1',
    html,
)

html = re.sub(
    r'/clone_voice/client\.js\?v=[^"]+',
    '/clone_voice/client.js?v=compact-narration-header-1',
    html,
)

HTML.write_text(html, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")

if ".narration-top-grid" not in css:
    css += r'''

.narration-top-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) 180px minmax(220px, 1.2fr) 180px;
  gap: 16px;
  align-items: end;
  margin: 8px 0 18px;
}

.voice-details-inline {
  display: contents;
}

.narration-top-grid label {
  margin: 0;
}

@media (max-width: 1100px) {
  .narration-top-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .narration-top-grid {
    grid-template-columns: 1fr;
  }
}
'''

# Neutralize old voice-details grid spacing if still present.
css = css.replace(
    '''.voice-details {
  grid-template-columns: 1fr 220px;
}''',
    '''.voice-details {
  grid-template-columns: 1fr 220px;
}''',
)

CSS.write_text(css, encoding="utf-8")

print()
print("COMPACT NARRATION HEADER COMPLETE.")
print()
print("Now displayed in one horizontal row:")
print("  Voice display name | Voice gender | Narration title | Narration speed")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?compact-header=1")
