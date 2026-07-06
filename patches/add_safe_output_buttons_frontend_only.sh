#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
INDEX="$ROOT/frontend/index.html"
CSS="$ROOT/frontend/styles.css"
ACTIONS="$ROOT/frontend/asset_actions.js"

if [ ! -f "$INDEX" ] || [ ! -f "$CSS" ]; then
  echo "ERROR: Run this from the project root where frontend/index.html and frontend/styles.css exist." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$INDEX" "$INDEX.bak.safe-output-buttons-$STAMP"
cp "$CSS" "$CSS.bak.safe-output-buttons-$STAMP"
[ -f "$ACTIONS" ] && cp "$ACTIONS" "$ACTIONS.bak.safe-output-buttons-$STAMP"

cat > "$ACTIONS" <<'JS'
(function () {
  const PATCH_NAME = 'safe-output-buttons';

  function isBadUrl(url) {
    return !url || url.startsWith('data:') || url.startsWith('blob:');
  }

  function absoluteUrl(url) {
    try {
      return new URL(url, window.location.href).href;
    } catch {
      return url;
    }
  }

  function filenameFromUrl(url, fallback) {
    try {
      const parsed = new URL(url, window.location.href);
      const last = decodeURIComponent(parsed.pathname.split('/').filter(Boolean).pop() || '');
      if (last && last.includes('.')) return last;
    } catch {}

    return fallback || 'alibaba-generated-asset.png';
  }

  function isUploadPreview(media) {
    return Boolean(
      media.closest('.preview-strip') ||
      media.closest('.dropzone') ||
      media.closest('.ordered-slot') ||
      media.closest('.image-slot') ||
      media.closest('.upload-panel') ||
      media.closest('[data-upload]') ||
      media.closest('label')
    );
  }

  function isLikelyOutputMedia(media) {
    if (!media || media.dataset.assetButtonsAttached === 'true') return false;

    const src = media.currentSrc || media.src;
    if (isBadUrl(src)) return false;
    if (isUploadPreview(media)) return false;

    const outputArea = media.closest(
      '.live-output, .output, .result, .result-card, .asset-card, .history, .history-card, [class*="output"], [id*="output"], [class*="history"], [id*="history"], [class*="asset"]'
    );

    return Boolean(outputArea);
  }

  async function copyUrl(url) {
    try {
      await navigator.clipboard.writeText(url);
      if (typeof toast === 'function') {
        toast('Asset URL copied', 'The generated asset URL is now on your clipboard.');
      } else {
        alert('Asset URL copied.');
      }
    } catch {
      window.prompt('Copy generated asset URL:', url);
    }
  }

  async function downloadAsset(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener noreferrer';
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function createButton(text, className) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className || 'asset-lite-button';
    button.textContent = text;
    return button;
  }

  function attachButtons(media) {
    if (!isLikelyOutputMedia(media)) return;

    const src = absoluteUrl(media.currentSrc || media.src);
    const filename = filenameFromUrl(src, media.tagName.toLowerCase() === 'video'
      ? 'alibaba-generated-video.mp4'
      : 'alibaba-generated-image.png'
    );

    media.dataset.assetButtonsAttached = 'true';

    const bar = document.createElement('div');
    bar.className = 'asset-lite-actions';
    bar.dataset.assetLiteActions = 'true';

    const open = document.createElement('a');
    open.className = 'asset-lite-button primary';
    open.href = src;
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    open.textContent = 'Open full asset';

    const download = createButton('Download');
    download.addEventListener('click', function () {
      downloadAsset(src, filename);
    });

    const copy = createButton('Copy URL');
    copy.addEventListener('click', function () {
      copyUrl(src);
    });

    bar.appendChild(open);
    bar.appendChild(download);
    bar.appendChild(copy);

    const parent = media.closest('.result-media-shell') || media.parentElement;
    if (!parent) return;

    if (parent.querySelector(':scope > [data-asset-lite-actions="true"]')) return;

    parent.appendChild(bar);
  }

  function scan() {
    document.querySelectorAll('img[src], video[src], audio[src]').forEach(attachButtons);
  }

  let timer = null;
  function scheduleScan() {
    clearTimeout(timer);
    timer = setTimeout(scan, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan);
  } else {
    scan();
  }

  new MutationObserver(scheduleScan).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['src']
  });

  window.__scanAlibabaOutputButtons = scan;
  console.log(`[${PATCH_NAME}] output buttons active`);
})();
JS

python - "$INDEX" "$CSS" "$STAMP" <<'PY'
from pathlib import Path
import re
import sys

index_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])
stamp = sys.argv[3]

html = index_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

# Remove older injected asset_actions.js references.
html = re.sub(
    r'\n?\s*<script[^>]+src=["\']\.?/??asset_actions\.js(?:\?[^"\']*)?["\'][^>]*></script>\s*',
    '\n',
    html,
    flags=re.I,
)

script_tag = f'<script src="./asset_actions.js?v={stamp}" defer></script>'

if '</body>' in html.lower():
    html = re.sub(r'</body>', script_tag + '\n</body>', html, count=1, flags=re.I)
else:
    html = html.rstrip() + '\n' + script_tag + '\n'

css = re.sub(
    r'\n/\* SAFE_OUTPUT_BUTTONS_PATCH_START \*/[\s\S]*?/\* SAFE_OUTPUT_BUTTONS_PATCH_END \*/\n?',
    '\n',
    css,
)

css += r'''

/* SAFE_OUTPUT_BUTTONS_PATCH_START */
.asset-lite-actions {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  justify-content: center;
  margin-top: 0.75rem;
}

.asset-lite-button {
  min-height: 2.55rem;
  border-radius: 999px;
  border: 1px solid var(--line, rgba(0,0,0,0.14));
  background: var(--surface, #ffffff);
  color: var(--text, #111827);
  padding: 0.68rem 1rem;
  font-weight: 800;
  text-decoration: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.asset-lite-button.primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6));
  color: #06130f;
}

.asset-lite-button:hover {
  transform: translateY(-1px);
}

@media (max-width: 560px) {
  .asset-lite-actions,
  .asset-lite-button {
    width: 100%;
  }
}
/* SAFE_OUTPUT_BUTTONS_PATCH_END */
'''

index_path.write_text(html, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
PY

echo "Safe output buttons patch applied."
echo
echo "Changed only:"
echo "  frontend/index.html"
echo "  frontend/styles.css"
echo "  frontend/asset_actions.js"
echo
echo "Did NOT touch:"
echo "  app.py"
echo
echo "Restart Flask:"
echo "  python app.py"
echo
echo "Then open:"
echo "  http://127.0.0.1:5055/?buttons=$STAMP"
