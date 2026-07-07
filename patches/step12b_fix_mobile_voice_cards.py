from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
CSS = ROOT / "frontend" / "clone_voice" / "client.css"
HTML = ROOT / "frontend" / "clone_voice" / "client.html"

required = [CSS, HTML]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Client files not found. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in required:
    backup = path.with_name(path.name + f".bak.step12b-mobile-voice-cards-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print("Backup:", backup)

html = HTML.read_text(encoding="utf-8")
html = re.sub(
    r'/clone_voice/client\.css\?v=[^"]+',
    '/clone_voice/client.css?v=mobile-voice-cards-1',
    html,
)
HTML.write_text(html, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")

css += r'''

/* Step 12b: keep voice action icons compact on mobile */

@media (max-width: 900px) {
  .voice-card {
    grid-template-columns: 24px minmax(0, 1fr) 46px 46px !important;
    gap: 10px !important;
    align-items: center !important;
  }

  .voice-card > input[type="radio"] {
    grid-column: 1;
    grid-row: 1;
    justify-self: center;
  }

  .voice-card > span {
    grid-column: 2;
    grid-row: 1;
    min-width: 0;
  }

  .voice-card-title {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .voice-card .icon-btn {
    width: 46px !important;
    height: 46px !important;
    min-width: 46px !important;
    border-radius: 14px;
    padding: 0;
  }

  .voice-card .icon-btn-play {
    grid-column: 3;
    grid-row: 1;
  }

  .voice-card .icon-btn-delete {
    grid-column: 4;
    grid-row: 1;
  }

  .voice-card-empty {
    display: none;
  }

  .list-toolbar {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .list-toolbar button {
    width: 100%;
  }

  .preview-btn,
  .delete-voice-btn {
    width: auto;
  }
}

@media (max-width: 420px) {
  .voice-card {
    grid-template-columns: 22px minmax(0, 1fr) 42px 42px !important;
    gap: 8px !important;
    padding: 10px !important;
  }

  .voice-card .icon-btn {
    width: 42px !important;
    height: 42px !important;
    min-width: 42px !important;
  }
}
'''

CSS.write_text(css, encoding="utf-8")

print()
print("STEP 12B COMPLETE: mobile voice cards fixed.")
print()
print("Mobile saved voice cards now stay on one line:")
print("  radio | voice name | play icon | bin icon")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?mobile-voice-cards=1")
