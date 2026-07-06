(function () {
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
