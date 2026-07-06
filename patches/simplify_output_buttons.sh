#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
ACTIONS="$ROOT/frontend/asset_actions.js"
CSS="$ROOT/frontend/styles.css"

if [ ! -f "$ACTIONS" ] || [ ! -f "$CSS" ]; then
  echo "ERROR: Run this from the project root where frontend/asset_actions.js and frontend/styles.css exist." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
cp "$ACTIONS" "$ACTIONS.bak.simplify-buttons-$STAMP"
cp "$CSS" "$CSS.bak.simplify-buttons-$STAMP"

cat > "$ACTIONS" <<'JS'
(function () {
  const PATCH_NAME = 'simple-output-buttons';

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

  function createDownloadLink(url, filename) {
    const link = document.createElement('a');
    link.className = 'asset-lite-button primary';
    link.href = url;
    link.download = filename;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Download';

    link.addEventListener('click', event => {
      event.stopPropagation();
    }, true);

    return link;
  }

  function createCopyButton(url) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'asset-lite-button';
    button.textContent = 'Copy URL';

    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      copyUrl(url);
    }, true);

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

    bar.appendChild(createDownloadLink(src, filename));
    bar.appendChild(createCopyButton(src));

    const wrappingLink = media.closest('a');
    const parent = wrappingLink?.parentElement || media.parentElement;
    if (!parent) return;

    if (parent.querySelector(':scope > [data-asset-lite-actions="true"]')) return;

    if (wrappingLink) {
      wrappingLink.insertAdjacentElement('afterend', bar);
    } else {
      media.insertAdjacentElement('afterend', bar);
    }
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
  console.log(`[${PATCH_NAME}] Download + Copy URL buttons active`);
})();
JS

python - "$CSS" <<'PY'
from pathlib import Path
import re
import sys

css_path = Path(sys.argv[1])
css = css_path.read_text(encoding="utf-8")

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
  position: relative;
  z-index: 5;
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

css_path.write_text(css, encoding="utf-8")
PY

echo "Simplified output buttons."
echo
echo "Now shown:"
echo "  Download"
echo "  Copy URL"
echo
echo "Removed:"
echo "  Open full asset"
echo
echo "Changed only:"
echo "  frontend/asset_actions.js"
echo "  frontend/styles.css"
echo
echo "Restart Flask:"
echo "  python app.py"
