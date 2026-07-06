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

    return fallback || 'syntaxmatrix-generated-asset.png';
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
      ? 'syntaxmatrix-generated-video.mp4'
      : 'syntaxmatrix-generated-image.png'
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

  window.__scanSyntaxMatrixOutputButtons = scan;
  console.log(`[${PATCH_NAME}] Download + Copy URL buttons active`);
})();
