(function () {
  const PATCH_NAME = 'clone_voice_debug_client_v2';

  function activeMode() {
    const active = document.querySelector('[data-source-mode].active');
    return active?.dataset?.sourceMode || 'upload';
  }

  function getPrompt() {
    return String(document.querySelector('#voicePrompt')?.value || '').trim();
  }

  function getAudioFile() {
    const input =
      document.querySelector('#voiceAudio') ||
      document.querySelector('input[type="file"][name="audio"]') ||
      document.querySelector('input[type="file"]');

    return input?.files?.[0] || null;
  }

  function setBusy(isBusy) {
    const button =
      document.querySelector('#voiceSubmit') ||
      [...document.querySelectorAll('button')].find(btn =>
        /generate narration/i.test(btn.textContent || '')
      );

    if (!button) return;
    button.disabled = isBusy;
    button.textContent = isBusy ? 'Sending debug request…' : 'Generate narration';
  }

  function renderDebugResponse(data) {
    const title = document.querySelector('#voiceResultTitle');
    const status = document.querySelector('#voiceResultStatus');
    const preview = document.querySelector('#voiceResultPreview');
    const meta = document.querySelector('#voiceResultMeta');

    if (title) title.textContent = 'Debug request received';
    if (status) status.textContent = 'The new clone_voice_controller received the upload. Check Flask terminal.';

    if (preview) {
      preview.innerHTML = `<pre style="white-space:pre-wrap;max-height:360px;overflow:auto;">${JSON.stringify(data, null, 2)}</pre>`;
    }

    if (meta) {
      meta.innerHTML = `
        <div><dt>Controller</dt><dd>/api/clone-voice/debug-submit</dd></div>
        <div><dt>File keys</dt><dd>${Array.isArray(data.fileKeys) ? data.fileKeys.join(', ') : ''}</dd></div>
      `;
    }
  }

  async function sendUploadToDebugController(event) {
    if (activeMode() !== 'upload') return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const prompt = getPrompt();
    const file = getAudioFile();

    console.group('[SyntaxMatrix Clone Voice Debug] FRONTEND SENDING');
    console.log('endpoint:', '/api/clone-voice/debug-submit');
    console.log('prompt field:', 'prompt');
    console.log('promptLength:', prompt.length);
    console.log('audio field:', 'audio');
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();

    if (!prompt) {
      alert('Paste narration text first.');
      return;
    }

    if (!file) {
      alert('Choose an audio file first.');
      return;
    }

    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('audio', file, file.name);

    try {
      setBusy(true);

      const response = await fetch('/api/clone-voice/debug-submit', {
        method: 'POST',
        body: formData,
      });

      const text = await response.text();
      let data;

      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { raw: text };
      }

      console.log('[SyntaxMatrix Clone Voice Debug] BACKEND RESPONSE:', data);

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

      renderDebugResponse(data);
    } catch (error) {
      console.error('[SyntaxMatrix Clone Voice Debug] FAILED:', error);
      alert(error.message || String(error));
    } finally {
      setBusy(false);
    }
  }

  function intercept(event) {
    const isSubmit = event.type === 'submit' && event.target?.id === 'voiceCloneForm';
    const clickedGenerate = Boolean(event.target.closest?.('#voiceSubmit, button[type="submit"]'));

    if (!isSubmit && !clickedGenerate) return;

    sendUploadToDebugController(event);
  }

  document.addEventListener('submit', intercept, true);
  document.addEventListener('click', intercept, true);

  document.addEventListener('change', event => {
    const input = event.target;
    if (!input || input.type !== 'file') return;

    const file = input.files?.[0] || null;

    console.group('[SyntaxMatrix Clone Voice Debug] FILE CHOSEN');
    console.log('input id:', input.id);
    console.log('input name:', input.name);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();
  }, true);

  window.__debugCloneVoiceUpload = function () {
    const file = getAudioFile();
    const prompt = getPrompt();

    console.group('[SyntaxMatrix Clone Voice Debug] MANUAL CHECK');
    console.log('activeMode:', activeMode());
    console.log('promptLength:', prompt.length);
    console.log('file exists:', Boolean(file));

    if (file) {
      console.log('filename:', file.name);
      console.log('type:', file.type);
      console.log('size:', file.size);
    }

    console.groupEnd();

    return {
      activeMode: activeMode(),
      promptLength: prompt.length,
      fileExists: Boolean(file),
      filename: file?.name || null,
      type: file?.type || null,
      size: file?.size || null,
      endpoint: '/api/clone-voice/debug-submit',
    };
  };

  console.log(`[${PATCH_NAME}] active. Upload audio is routed to brand-new debug controller.`);
})();
