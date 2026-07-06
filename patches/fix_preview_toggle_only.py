from pathlib import Path
from datetime import datetime
import re

ROOT = Path(".").resolve()
FRONTEND = ROOT / "frontend"

VOICE_HTML = FRONTEND / "voice_clone_client.html"
INDEX_HTML = FRONTEND / "index.html"
CSS_FILE = FRONTEND / "voice_clone.css"
TOGGLE_JS = FRONTEND / "voice_preview_toggle_fix.js"

required = [FRONTEND, CSS_FILE]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Run this from the project root. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [VOICE_HTML, INDEX_HTML, CSS_FILE, TOGGLE_JS]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.preview-toggle-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

TOGGLE_JS.write_text(r'''(function () {
  const PATCH_NAME = 'voice-preview-toggle-fix-only';

  function findPreviewPanel() {
    return (
      document.querySelector('[data-source-panel="preview"]') ||
      document.querySelector('#previewVoiceList')?.closest('[data-source-panel]') ||
      document.querySelector('#previewVoiceList')?.parentElement
    );
  }

  function findPreviewTab() {
    return (
      document.querySelector('[data-source-mode="preview"]') ||
      [...document.querySelectorAll('button')].find(button =>
        /system preview voices|choose preview voice/i.test(button.textContent || '')
      )
    );
  }

  function isPreviewOpen() {
    const panel = findPreviewPanel();
    if (!panel) return false;
    if (panel.hidden) return false;
    if (panel.dataset.previewForceClosed === 'true') return false;

    const style = window.getComputedStyle(panel);
    return style.display !== 'none' && style.visibility !== 'hidden';
  }

  function closePreviewList() {
    const panel = findPreviewPanel();
    if (!panel) return;

    panel.hidden = true;
    panel.dataset.previewForceClosed = 'true';
    panel.style.display = 'none';
    panel.setAttribute('aria-hidden', 'true');

    const tab = findPreviewTab();
    if (tab) {
      tab.classList.remove('active');
      tab.setAttribute('aria-selected', 'false');
    }

    console.log(`[${PATCH_NAME}] preview list closed`);
  }

  function openPreviewList() {
    const panel = findPreviewPanel();
    if (!panel) return;

    panel.hidden = false;
    delete panel.dataset.previewForceClosed;
    panel.style.display = '';
    panel.setAttribute('aria-hidden', 'false');

    const tab = findPreviewTab();
    if (tab) {
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
    }

    console.log(`[${PATCH_NAME}] preview list opened`);
  }

  document.addEventListener('click', event => {
    const clickable = event.target.closest('button, a, [role="button"]');

    if (clickable) {
      const label = (clickable.textContent || '').trim().toLowerCase();

      if (label === 'close list' || clickable.dataset.closePreviewList === 'true') {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        closePreviewList();
        return;
      }
    }

    const sourceTab = event.target.closest('[data-source-mode]');

    if (!sourceTab) return;

    const mode = sourceTab.dataset.sourceMode;

    if (mode === 'preview') {
      if (isPreviewOpen()) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        closePreviewList();
        return;
      }

      window.setTimeout(openPreviewList, 80);
      return;
    }

    window.setTimeout(closePreviewList, 0);
  }, true);

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && isPreviewOpen()) {
      closePreviewList();
    }
  });

  window.__closeVoicePreviewList = closePreviewList;
  window.__openVoicePreviewList = openPreviewList;

  console.log(`[${PATCH_NAME}] active`);
})();
''', encoding="utf-8")

def inject_script(path: Path) -> None:
    if not path.exists():
        return

    html = path.read_text(encoding="utf-8")

    html = re.sub(
        r'\n?\s*<script[^>]+src=["\']/?voice_preview_toggle_fix\.js(?:\?[^"\']*)?["\'][^>]*></script>\s*',
        '\n',
        html,
        flags=re.I,
    )

    script = f'<script src="/voice_preview_toggle_fix.js?v={stamp}" defer></script>'

    if re.search(r'</body>', html, flags=re.I):
        html = re.sub(r'</body>', script + '\n</body>', html, count=1, flags=re.I)
    else:
        html = html.rstrip() + '\n' + script + '\n'

    path.write_text(html, encoding="utf-8")
    print("Injected:", path)

inject_script(VOICE_HTML)
inject_script(INDEX_HTML)

css = CSS_FILE.read_text(encoding="utf-8")

css = re.sub(
    r'\n/\* PREVIEW_TOGGLE_FIX_ONLY_START \*/[\s\S]*?/\* PREVIEW_TOGGLE_FIX_ONLY_END \*/\n?',
    '\n',
    css,
)

css += r'''

/* PREVIEW_TOGGLE_FIX_ONLY_START */
[hidden],
[data-preview-force-closed="true"],
.voice-source-panel[hidden],
.voice-source-panel[data-preview-force-closed="true"] {
  display: none !important;
}
/* PREVIEW_TOGGLE_FIX_ONLY_END */
'''

CSS_FILE.write_text(css, encoding="utf-8")

print()
print("Preview toggle-only patch complete.")
print("Changed only frontend files:")
print("  frontend/voice_preview_toggle_fix.js")
print("  frontend/voice_clone_client.html, if present")
print("  frontend/index.html, if present")
print("  frontend/voice_clone.css")
print()
print("Restart Flask with: python app.py")
print("Open: http://127.0.0.1:5055/tasks/voice-clone?v=preview-toggle")