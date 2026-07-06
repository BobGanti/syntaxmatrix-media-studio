from pathlib import Path
import re
import py_compile
from datetime import datetime

ROOT = Path('.').resolve()
FRONTEND = ROOT / 'frontend'
CLIENT_HTML = FRONTEND / 'voice_clone_client.html'
CLIENT_JS = FRONTEND / 'voice_clone_client.js'
VOICE_CSS = FRONTEND / 'voice_clone.css'
INDEX = FRONTEND / 'index.html'
README = ROOT / 'README.md'
CONTROLLER = ROOT / 'controllers' / 'voice_clone_controller.py'

required = [FRONTEND, CLIENT_HTML, CLIENT_JS, VOICE_CSS, CONTROLLER]
missing = [str(path) for path in required if not path.exists()]
if missing:
    print('ERROR: Run this from the project root. Missing:')
    for item in missing:
        print(' -', item)
    raise SystemExit(1)

stamp = datetime.now().strftime('%Y%m%d%H%M%S')
for path in [CLIENT_HTML, CLIENT_JS, VOICE_CSS, INDEX, README, CONTROLLER]:
    if path.exists():
        backup = path.with_name(path.name + f'.bak.voice-flow-{stamp}')
        backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
        print('Backup:', backup)

CLIENT_HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SyntaxMatrix Voice Narration</title>
  <link rel="stylesheet" href="/styles.css" />
  <link rel="stylesheet" href="/voice_clone.css" />
</head>
<body class="feature-page voice-client-page">
  <main class="feature-shell">
    <header class="feature-header">
      <a class="feature-back" href="/">← Studio</a>
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Voice Narration</h1>
      <p>Create or choose a voice identity, then generate narration from your script.</p>
    </header>

    <section class="feature-grid voice-client-grid">
      <form id="voiceCloneForm" class="feature-card voice-client-card" enctype="multipart/form-data">
        <div class="section-heading compact">
          <p class="eyebrow">Client workflow</p>
          <h2>Create narration</h2>
          <p>Uploaded and recorded voices must first be saved as a voice identity. You can reuse saved voices later.</p>
        </div>

        <input id="voiceModel" name="model" type="hidden" value="qwen3-tts-vc-2026-01-22" />

        <section class="voice-source-section">
          <div class="voice-source-header">
            <div>
              <p class="eyebrow">Voice source</p>
              <h3>Choose or create a voice identity</h3>
            </div>
            <button class="secondary-button slim" id="reloadClientProfiles" type="button">Refresh my voices</button>
          </div>

          <div class="voice-source-tabs" role="tablist" aria-label="Voice source options">
            <button class="voice-source-tab active" type="button" data-source-mode="upload">Upload audio</button>
            <button class="voice-source-tab" type="button" data-source-mode="record">Record my voice</button>
            <button class="voice-source-tab" type="button" data-source-mode="saved">My saved voices</button>
            <button class="voice-source-tab" type="button" data-source-mode="preview">System preview voices</button>
          </div>

          <div class="voice-source-panel" data-source-panel="upload">
            <label class="upload-drop-lite">
              <span>Upload a voice sample</span>
              <input id="voiceAudio" name="audio" type="file" accept="audio/*" />
              <small>Choose a clean WAV, MP3, M4A, OGG or WEBM file.</small>
            </label>
            <p id="uploadFileName" class="muted-line">No audio selected yet.</p>
            <button class="primary-button" id="createUploadProfile" type="button">Create voice identity from upload</button>
          </div>

          <div class="voice-source-panel" data-source-panel="record" hidden>
            <div class="recorder-card">
              <strong id="recordingStatus">Recorder ready</strong>
              <span id="recordingHelp">Record a clean voice sample, then save it as a reusable voice identity.</span>
              <div class="recorder-actions">
                <button class="secondary-button" id="startRecording" type="button">Start recording</button>
                <button class="secondary-button" id="stopRecording" type="button" disabled>Stop</button>
                <button class="secondary-button" id="discardRecording" type="button" disabled>Discard</button>
              </div>
              <audio id="recordedPreview" controls hidden></audio>
              <button class="primary-button" id="createRecordedProfile" type="button" disabled>Create voice identity from recording</button>
            </div>
          </div>

          <div class="voice-source-panel" data-source-panel="saved" hidden>
            <div class="preview-voice-toolbar">
              <p class="muted-line">Voices you created from uploaded or recorded audio are private to this browser workspace.</p>
              <button class="secondary-button" id="refreshSavedVoices" type="button">Refresh</button>
            </div>
            <div id="clientVoiceList" class="compact-voice-list">Loading your saved voices…</div>
          </div>

          <div class="voice-source-panel" data-source-panel="preview" hidden>
            <div class="preview-voice-toolbar">
              <p class="muted-line">System voices are approved preview voices. They are shared presets.</p>
              <div class="toolbar-actions">
                <button class="secondary-button" id="refreshPreviewVoices" type="button">Refresh</button>
                <button class="secondary-button" id="closePreviewVoices" type="button">Close list</button>
              </div>
            </div>
            <div id="previewVoiceList" class="compact-voice-list">Loading preview voices…</div>
          </div>

          <div id="selectedVoiceBox" class="selected-voice-box" hidden>
            <span>Selected voice</span>
            <strong id="selectedVoiceName">None</strong>
          </div>
        </section>

        <label>
          <span>Narration text</span>
          <textarea id="voicePrompt" name="prompt" rows="9" required placeholder="Paste the narration script here..."></textarea>
        </label>

        <div class="form-actions">
          <button class="secondary-button" type="reset">Reset</button>
          <button class="primary-button" id="voiceSubmit" type="submit">Generate narration</button>
        </div>
      </form>

      <aside class="feature-card result-card-lite" aria-live="polite">
        <div class="section-heading compact">
          <p class="eyebrow">Output</p>
          <h2 id="voiceResultTitle">No narration yet</h2>
          <p id="voiceResultStatus">Create or choose a voice identity, then submit your narration script.</p>
        </div>
        <div id="voiceResultPreview" class="voice-result-preview"></div>
        <dl id="voiceResultMeta" class="result-meta"></dl>
      </aside>
    </section>
  </main>

  <div class="toast-region" id="toastRegion" aria-live="polite" aria-atomic="true"></div>
  <script src="/voice_clone_client.js?v=voice-flow" defer></script>
</body>
</html>
''', encoding='utf-8')

CLIENT_JS.write_text(r'''(function () {
  const form = document.querySelector('#voiceCloneForm');
  const submit = document.querySelector('#voiceSubmit');
  const title = document.querySelector('#voiceResultTitle');
  const status = document.querySelector('#voiceResultStatus');
  const preview = document.querySelector('#voiceResultPreview');
  const meta = document.querySelector('#voiceResultMeta');
  const toastRegion = document.querySelector('#toastRegion');

  const voiceModelInput = document.querySelector('#voiceModel');
  const voiceAudioInput = document.querySelector('#voiceAudio');
  const uploadFileName = document.querySelector('#uploadFileName');
  const createUploadProfileButton = document.querySelector('#createUploadProfile');
  const createRecordedProfileButton = document.querySelector('#createRecordedProfile');

  const tabs = [...document.querySelectorAll('[data-source-mode]')];
  const panels = [...document.querySelectorAll('[data-source-panel]')];
  const previewVoiceList = document.querySelector('#previewVoiceList');
  const clientVoiceList = document.querySelector('#clientVoiceList');
  const refreshPreviewVoices = document.querySelector('#refreshPreviewVoices');
  const closePreviewVoices = document.querySelector('#closePreviewVoices');
  const refreshSavedVoices = document.querySelector('#refreshSavedVoices');
  const reloadClientProfiles = document.querySelector('#reloadClientProfiles');

  const selectedVoiceBox = document.querySelector('#selectedVoiceBox');
  const selectedVoiceName = document.querySelector('#selectedVoiceName');

  const startRecordingButton = document.querySelector('#startRecording');
  const stopRecordingButton = document.querySelector('#stopRecording');
  const discardRecordingButton = document.querySelector('#discardRecording');
  const recordingStatus = document.querySelector('#recordingStatus');
  const recordingHelp = document.querySelector('#recordingHelp');
  const recordedPreview = document.querySelector('#recordedPreview');

  const CLIENT_ID_KEY = 'syntaxmatrix-media-client-id';

  let sourceMode = 'upload';
  let selectedVoice = null;
  let previewAudio = null;

  let audioContext = null;
  let micStream = null;
  let micSource = null;
  let recorderNode = null;
  let recordingBuffers = [];
  let recordingSampleRate = 44100;
  let recordedBlob = null;
  let recordedFileName = '';

  function clientId() {
    let value = localStorage.getItem(CLIENT_ID_KEY);
    if (!value) {
      value = `client_${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)}`;
      localStorage.setItem(CLIENT_ID_KEY, value);
    }
    return value;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function toast(headline, detail) {
    if (!toastRegion) return;
    const note = document.createElement('div');
    note.className = 'toast';
    note.innerHTML = `<strong>${escapeHtml(headline)}</strong><span>${escapeHtml(detail || '')}</span>`;
    toastRegion.appendChild(note);
    window.setTimeout(() => note.remove(), 4600);
  }

  function setButtonBusy(button, busy, busyText, readyText) {
    if (!button) return;
    button.disabled = busy;
    button.textContent = busy ? busyText : readyText;
  }

  function makeDisplayName(prefix, filename) {
    const raw = (filename || prefix || 'Voice').replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
    return raw || prefix;
  }

  function selectVoice(voice) {
    selectedVoice = voice;
    if (!voice) {
      selectedVoiceBox.hidden = true;
      selectedVoiceName.textContent = 'None';
      return;
    }
    selectedVoiceBox.hidden = false;
    selectedVoiceName.textContent = voice.displayName || voice.name || voice.profileId || voice.voiceName || 'Selected voice';
  }

  function setSourceMode(mode) {
    sourceMode = mode;

    tabs.forEach(tab => {
      const active = tab.dataset.sourceMode === mode;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
    });

    panels.forEach(panel => {
      panel.hidden = panel.dataset.sourcePanel !== mode;
    });

    if (previewAudio) {
      previewAudio.pause();
      previewAudio = null;
    }

    if (mode === 'saved') loadClientProfiles();
    if (mode === 'preview') loadPreviewVoices();
  }

  function flattenBuffers(buffers) {
    const totalLength = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
    const result = new Float32Array(totalLength);
    let offset = 0;
    buffers.forEach(buffer => {
      result.set(buffer, offset);
      offset += buffer.length;
    });
    return result;
  }

  function writeString(view, offset, value) {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  }

  function encodeWav(floatSamples, sampleRate) {
    const bytesPerSample = 2;
    const dataLength = floatSamples.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * bytesPerSample, true);
    view.setUint16(32, bytesPerSample, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, dataLength, true);
    let offset = 44;
    for (let i = 0; i < floatSamples.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, floatSamples[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
    return buffer;
  }

  async function startRecording() {
    try {
      recordedBlob = null;
      recordingBuffers = [];
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      recordingSampleRate = audioContext.sampleRate;
      micSource = audioContext.createMediaStreamSource(micStream);
      recorderNode = audioContext.createScriptProcessor(4096, 1, 1);
      recorderNode.onaudioprocess = event => recordingBuffers.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      micSource.connect(recorderNode);
      recorderNode.connect(audioContext.destination);
      startRecordingButton.disabled = true;
      stopRecordingButton.disabled = false;
      discardRecordingButton.disabled = true;
      createRecordedProfileButton.disabled = true;
      recordingStatus.textContent = 'Recording…';
      recordingHelp.textContent = 'Speak clearly. Click Stop when your sample is ready.';
    } catch (error) {
      toast('Recorder unavailable', error.message || 'Could not access microphone.');
      console.error(error);
    }
  }

  async function stopRecording() {
    try {
      if (recorderNode) {
        recorderNode.disconnect();
        recorderNode.onaudioprocess = null;
      }
      if (micSource) micSource.disconnect();
      if (micStream) micStream.getTracks().forEach(track => track.stop());
      if (audioContext) await audioContext.close();
      const merged = flattenBuffers(recordingBuffers);
      const wavBuffer = encodeWav(merged, recordingSampleRate);
      recordedBlob = new Blob([wavBuffer], { type: 'audio/wav' });
      recordedFileName = `recorded_voice_${Date.now()}.wav`;
      recordedPreview.src = URL.createObjectURL(recordedBlob);
      recordedPreview.hidden = false;
      recordingStatus.textContent = 'Recording ready';
      recordingHelp.textContent = 'Now click “Create voice identity from recording” before generating narration.';
      startRecordingButton.disabled = false;
      stopRecordingButton.disabled = true;
      discardRecordingButton.disabled = false;
      createRecordedProfileButton.disabled = false;
    } catch (error) {
      toast('Recording failed', error.message || 'Could not create WAV recording.');
      console.error(error);
    }
  }

  function discardRecording() {
    recordedBlob = null;
    recordingBuffers = [];
    recordedFileName = '';
    if (recordedPreview.src) URL.revokeObjectURL(recordedPreview.src);
    recordedPreview.removeAttribute('src');
    recordedPreview.hidden = true;
    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
    discardRecordingButton.disabled = true;
    createRecordedProfileButton.disabled = true;
    recordingStatus.textContent = 'Recorder ready';
    recordingHelp.textContent = 'Record a new voice sample before creating a voice identity.';
  }

  async function createProfileFromFile(file, displayName, sourceType, button) {
    if (!file) {
      toast('Audio required', 'Choose or record an audio sample first.');
      return;
    }

    const formData = new FormData();
    formData.append('clientId', clientId());
    formData.append('displayName', displayName || makeDisplayName('My voice', file.name));
    formData.append('sourceType', sourceType);
    formData.append('model', voiceModelInput.value || 'qwen3-tts-vc-2026-01-22');
    formData.append('audio', file, file.name || `${sourceType}.wav`);

    setButtonBusy(button, true, 'Creating voice identity…', button?.dataset.readyText || 'Create voice identity');
    title.textContent = 'Creating voice identity…';
    status.textContent = 'Saving the source voice in your workspace before narration generation.';

    try {
      const response = await fetch('/api/voice-clone/profile', { method: 'POST', body: formData });
      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      selectVoice({ type: 'client', ...data.profile });
      await loadClientProfiles(false);
      title.textContent = 'Voice identity ready';
      status.textContent = 'Now paste narration text and click Generate narration.';
      toast('Voice identity created', data.profile?.displayName || 'Your voice is ready.');
      setSourceMode('saved');
    } catch (error) {
      title.textContent = 'Voice identity failed';
      status.textContent = error.message || 'Could not create voice identity.';
      toast('Voice identity failed', error.message || 'Could not create voice identity.');
      console.error(error);
    } finally {
      setButtonBusy(button, false, '', button?.dataset.readyText || 'Create voice identity');
    }
  }

  function renderVoiceRows(container, voices, type) {
    if (!voices.length) {
      container.innerHTML = '<p class="muted-line">No voices available yet.</p>';
      return;
    }

    container.innerHTML = voices.map((voice, index) => {
      const selected = selectedVoice && selectedVoice.type === type && (selectedVoice.profileId || selectedVoice.voiceName) === (voice.profileId || voice.voiceName);
      return `
        <article class="preview-voice-row ${selected ? 'selected' : ''}">
          <button class="voice-preview-play" type="button" data-play-index="${index}" aria-label="Play ${escapeHtml(voice.displayName || voice.voiceName)}">▶</button>
          <button class="voice-preview-name" type="button" data-choose-index="${index}">${escapeHtml(voice.displayName || voice.voiceName || voice.profileId)}</button>
          <button class="voice-preview-use" type="button" data-choose-index="${index}">${selected ? 'Selected' : 'Use'}</button>
        </article>`;
    }).join('');

    container.querySelectorAll('[data-play-index]').forEach(button => {
      button.addEventListener('click', event => {
        event.preventDefault();
        const voice = voices[Number(button.dataset.playIndex)];
        playVoicePreview(voice?.previewUrl || voice?.sourceUrl, button);
      });
    });

    container.querySelectorAll('[data-choose-index]').forEach(button => {
      button.addEventListener('click', event => {
        event.preventDefault();
        const voice = voices[Number(button.dataset.chooseIndex)];
        if (!voice) return;
        selectVoice({ type, ...voice });
        renderVoiceRows(container, voices, type);
        toast('Voice selected', voice.displayName || voice.voiceName || 'Selected voice');
      });
    });
  }

  function playVoicePreview(url, button) {
    if (!url) {
      toast('No preview audio', 'This voice does not have preview audio yet.');
      return;
    }
    if (previewAudio) previewAudio.pause();
    document.querySelectorAll('.voice-preview-play.playing').forEach(btn => {
      btn.classList.remove('playing');
      btn.textContent = '▶';
    });
    previewAudio = new Audio(url);
    button.classList.add('playing');
    button.textContent = '■';
    previewAudio.addEventListener('ended', () => {
      button.classList.remove('playing');
      button.textContent = '▶';
    });
    previewAudio.addEventListener('error', () => {
      button.classList.remove('playing');
      button.textContent = '▶';
      toast('Preview failed', 'The audio could not be played.');
    });
    previewAudio.play().catch(error => {
      button.classList.remove('playing');
      button.textContent = '▶';
      toast('Preview blocked', error.message || 'Browser blocked audio playback.');
    });
  }

  async function loadClientProfiles(showLoading = true) {
    if (showLoading) clientVoiceList.innerHTML = '<p class="muted-line">Loading your saved voices…</p>';
    try {
      const response = await fetch(`/api/voice-clone/client-profiles?clientId=${encodeURIComponent(clientId())}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      renderVoiceRows(clientVoiceList, Array.isArray(data.profiles) ? data.profiles : [], 'client');
    } catch (error) {
      clientVoiceList.innerHTML = `<p class="muted-line">Could not load saved voices: ${escapeHtml(error.message || error)}</p>`;
      console.error(error);
    }
  }

  async function loadPreviewVoices() {
    previewVoiceList.innerHTML = '<p class="muted-line">Loading preview voices…</p>';
    try {
      const response = await fetch('/api/voice-clone/previews');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      renderVoiceRows(previewVoiceList, Array.isArray(data.voices) ? data.voices : [], 'system');
    } catch (error) {
      previewVoiceList.innerHTML = `<p class="muted-line">Could not load preview voices: ${escapeHtml(error.message || error)}</p>`;
      console.error(error);
    }
  }

  function buildGenerationFormData() {
    const prompt = String(document.querySelector('#voicePrompt')?.value || '').trim();
    if (!prompt) {
      toast('Narration text required', 'Paste the script before submitting.');
      return null;
    }
    if (!selectedVoice) {
      toast('Voice identity required', 'Create or choose a voice identity before generating narration.');
      return null;
    }
    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('model', voiceModelInput.value || 'qwen3-tts-vc-2026-01-22');
    formData.append('clientId', clientId());
    if (selectedVoice.type === 'client') formData.append('clientProfileId', selectedVoice.profileId);
    if (selectedVoice.type === 'system') formData.append('selectedPreviewVoice', selectedVoice.voiceName);
    return formData;
  }

  function renderSuccess(data) {
    const assetUrl = data.assetUrl || data.audioUrl;
    title.textContent = 'Narration ready';
    status.textContent = 'The generated audio is ready.';
    if (assetUrl) {
      const safeUrl = escapeHtml(assetUrl);
      preview.innerHTML = `
        <audio src="${safeUrl}" controls></audio>
        <div class="asset-lite-actions">
          <a class="asset-lite-button primary" href="${safeUrl}" download>Download</a>
          <button class="asset-lite-button" type="button" id="copyVoiceUrl">Copy URL</button>
        </div>`;
      document.querySelector('#copyVoiceUrl')?.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(new URL(assetUrl, window.location.href).href);
          toast('URL copied', 'The audio URL is now on your clipboard.');
        } catch {
          window.prompt('Copy audio URL:', assetUrl);
        }
      });
    } else {
      preview.innerHTML = '<p>No audio URL was returned.</p>';
    }
    meta.innerHTML = `
      <div><dt>Voice</dt><dd>${escapeHtml(selectedVoice?.displayName || selectedVoice?.voiceName || '—')}</dd></div>
      <div><dt>Output</dt><dd>${escapeHtml(data.clonePath || assetUrl || '—')}</dd></div>`;
  }

  tabs.forEach(tab => tab.addEventListener('click', () => setSourceMode(tab.dataset.sourceMode)));
  closePreviewVoices?.addEventListener('click', () => setSourceMode('saved'));
  refreshPreviewVoices?.addEventListener('click', loadPreviewVoices);
  refreshSavedVoices?.addEventListener('click', () => loadClientProfiles(true));
  reloadClientProfiles?.addEventListener('click', () => loadClientProfiles(true));

  voiceAudioInput?.addEventListener('change', () => {
    const file = voiceAudioInput.files?.[0];
    uploadFileName.textContent = file ? `${file.name} is ready. Click “Create voice identity from upload”.` : 'No audio selected yet.';
  });

  createUploadProfileButton?.addEventListener('click', () => {
    const file = voiceAudioInput.files?.[0];
    createUploadProfileButton.dataset.readyText = 'Create voice identity from upload';
    createProfileFromFile(file, makeDisplayName('Uploaded voice', file?.name), 'upload', createUploadProfileButton);
  });

  createRecordedProfileButton?.addEventListener('click', () => {
    if (!recordedBlob) {
      toast('Recording required', 'Record your voice first.');
      return;
    }
    const file = new File([recordedBlob], recordedFileName || 'recorded_voice.wav', { type: 'audio/wav' });
    createRecordedProfileButton.dataset.readyText = 'Create voice identity from recording';
    createProfileFromFile(file, 'Recorded voice', 'record', createRecordedProfileButton);
  });

  startRecordingButton?.addEventListener('click', startRecording);
  stopRecordingButton?.addEventListener('click', stopRecording);
  discardRecordingButton?.addEventListener('click', discardRecording);

  form?.addEventListener('reset', () => {
    window.setTimeout(() => {
      selectVoice(null);
      discardRecording();
      if (voiceAudioInput) voiceAudioInput.value = '';
      uploadFileName.textContent = 'No audio selected yet.';
      preview.innerHTML = '';
      meta.innerHTML = '';
      title.textContent = 'No narration yet';
      status.textContent = 'Create or choose a voice identity, then submit your narration script.';
      setSourceMode('upload');
    }, 0);
  });

  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const formData = buildGenerationFormData();
    if (!formData) return;
    submit.disabled = true;
    submit.textContent = 'Generating narration…';
    title.textContent = 'Generating narration…';
    status.textContent = 'Submitting selected voice identity to the Voice Clone controller.';
    preview.innerHTML = '<span>Working…</span>';
    try {
      const response = await fetch('/api/media/voice-clone', { method: 'POST', body: formData });
      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      renderSuccess(data);
      toast('Narration complete', 'The generated audio is ready.');
    } catch (error) {
      title.textContent = 'Narration failed';
      status.textContent = error.message || 'Request failed.';
      preview.innerHTML = '';
      toast('Narration failed', error.message || 'Request failed.');
      console.error(error);
    } finally {
      submit.disabled = false;
      submit.textContent = 'Generate narration';
    }
  });

  setSourceMode('upload');
  loadClientProfiles(false);
})();
''', encoding='utf-8')

css = VOICE_CSS.read_text(encoding='utf-8')
css = re.sub(r"\n/\* VOICE_CLIENT_FLOW_PATCH_START \*/[\s\S]*?/\* VOICE_CLIENT_FLOW_PATCH_END \*/\n?", "\n", css)
css += r'''

/* VOICE_CLIENT_FLOW_PATCH_START */
[hidden], .voice-source-panel[hidden] { display: none !important; }
.voice-client-grid { grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr); }
.voice-source-section, .recorder-card, .upload-drop-lite, .selected-voice-box {
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12)); border-radius: 1rem; background: var(--surface-muted, #f8fafc);
}
.voice-source-section { padding: 1rem; display: grid; gap: 0.9rem; }
.voice-source-header, .preview-voice-toolbar, .recorder-actions, .toolbar-actions {
  display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; justify-content: space-between;
}
.voice-source-header h3 { margin: .2rem 0 0; }
.voice-source-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.6rem; }
.voice-source-tab {
  min-height: 2.75rem; border-radius: 999px; border: 1px solid var(--line, rgba(15,23,42,.12)); background: var(--surface, #fff);
  color: var(--text, #111827); font-weight: 850; cursor: pointer;
}
.voice-source-tab.active { border-color: transparent; background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6)); color: #06130f; }
.voice-source-panel { display: grid; gap: .75rem; }
.upload-drop-lite, .recorder-card { padding: 1rem; display: grid; gap: .75rem; }
.muted-line { color: var(--muted, #667085); line-height: 1.45; margin: 0; }
.recorder-card audio, .voice-result-preview audio { width: 100%; }
.selected-voice-box { padding: .85rem 1rem; display: grid; gap: .2rem; }
.selected-voice-box span { color: var(--muted, #667085); font-size: .85rem; }
.compact-voice-list { display: grid; gap: .55rem; }
.preview-voice-row {
  display: grid; grid-template-columns: 2.4rem minmax(0, 1fr) auto; align-items: center; gap: .65rem; padding: .65rem;
  border: 1px solid var(--line, rgba(15,23,42,.12)); border-radius: 999px; background: var(--surface-muted, #f8fafc);
}
.preview-voice-row.selected { outline: 3px solid color-mix(in srgb, var(--brand, #13b981) 35%, transparent); }
.voice-preview-play, .voice-preview-name, .voice-preview-use { border: 0; cursor: pointer; font-weight: 850; }
.voice-preview-play { width: 2.1rem; height: 2.1rem; border-radius: 999px; display: grid; place-items: center; background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6)); color: #06130f; }
.voice-preview-play.playing { background: var(--surface, #fff); color: var(--text, #111827); border: 1px solid var(--line, rgba(15,23,42,.12)); }
.voice-preview-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; text-align: left; white-space: nowrap; background: transparent; color: var(--text, #111827); }
.voice-preview-use { border-radius: 999px; padding: .55rem .85rem; background: var(--surface, #fff); color: var(--text, #111827); border: 1px solid var(--line, rgba(15,23,42,.12)); }
.asset-lite-actions { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: .8rem; }
.asset-lite-button { min-height: 2.55rem; border-radius: 999px; border: 1px solid var(--line, rgba(15,23,42,.12)); background: var(--surface, #fff); color: var(--text, #111827); padding: .68rem 1rem; font-weight: 800; text-decoration: none; cursor: pointer; }
.asset-lite-button.primary { border-color: transparent; background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6)); color: #06130f; }
.secondary-button.slim { min-height: 2.35rem; padding: .5rem .8rem; }
@media (max-width: 1000px) { .voice-client-grid, .voice-source-tabs { grid-template-columns: 1fr; } .preview-voice-row { grid-template-columns: 2.4rem minmax(0, 1fr); border-radius: 1rem; } .voice-preview-use { grid-column: 1 / -1; width: 100%; } }
/* VOICE_CLIENT_FLOW_PATCH_END */
'''
VOICE_CSS.write_text(css, encoding='utf-8')

controller = CONTROLLER.read_text(encoding='utf-8')
start = controller.index('def voice_clone_api_impl():')
end = controller.index('\ndef voice_clone_admin_state():')
new_controller_block = r'''def _client_safe_id(raw: str) -> str:
    import re as _re
    cleaned = _re.sub(r"[^A-Za-z0-9_]", "_", raw or "").strip("_")
    return cleaned[:80] or "guest"


CLIENT_WORKSPACES_DIR = VOICES_DIR / "client_workspaces"
CLIENT_WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def _client_workspace(client_id: str) -> pathlib.Path:
    workspace = CLIENT_WORKSPACES_DIR / _client_safe_id(client_id)
    for name in ("sources", "params", "clones"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return workspace


def _client_manifest_path(client_id: str) -> pathlib.Path:
    return _client_workspace(client_id) / "profiles.json"


def _read_client_profiles(client_id: str) -> list[dict[str, Any]]:
    path = _client_manifest_path(client_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_client_profiles(client_id: str, profiles: list[dict[str, Any]]) -> None:
    _client_manifest_path(client_id).write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def _provider_preferred_name(raw: str) -> str:
    import re as _re
    base = _re.sub(r"[^A-Za-z0-9_]", "_", raw or "").strip("_")
    base = _re.sub(r"_+", "_", base)
    if not base:
        base = "smxvoice"
    if not base[0].isalpha():
        base = "smx_" + base
    base = base[:24]
    return f"{base}_{_timestamp()}"[:48]


def _save_client_uploaded_voice(file: FileStorage, client_id: str, preferred_name: str) -> pathlib.Path:
    workspace = _client_workspace(client_id)
    mime_type = file.mimetype or "audio/wav"
    ext = pathlib.Path(secure_filename(file.filename or "")).suffix or _safe_ext(mime_type, ".wav")
    stem = _provider_preferred_name(preferred_name)
    target = workspace / "sources" / f"{stem}{ext}"
    file.save(target)
    return target


def _load_voice_feature():
    api_key, workspace_id = _require_credentials()
    import dashscope  # type: ignore
    import ali_voice_clone as voice_feature
    voice_feature.ALIBABA_API_KEY = api_key
    voice_feature.WORKSPACE_ID = workspace_id
    dashscope.base_http_api_url = _provider_base_url()
    return api_key, voice_feature


def _profile_from_manifest(client_id: str, profile_id: str) -> Optional[dict[str, Any]]:
    for profile in _read_client_profiles(client_id):
        if profile.get("profileId") == profile_id:
            return profile
    return None


def _system_preview_profiles() -> list[dict[str, Any]]:
    voices: list[dict[str, Any]] = []
    params = sorted(VOICE_PARAMS_DIR.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    for param in params:
        preview_path = None
        for ext in ("wav", "mp3", "m4a", "ogg", "webm"):
            for candidate in (VOICE_PREVIEWS_DIR / f"{param.stem}_preview.{ext}", VOICE_PREVIEWS_DIR / f"{param.stem}.{ext}"):
                if candidate.exists() and candidate.is_file():
                    preview_path = candidate
                    break
            if preview_path:
                break
        display_name = param.stem.replace("_", " ").replace("-", " ").strip().title() or param.stem
        voices.append({
            "voiceName": param.stem,
            "displayName": display_name,
            "previewUrl": _public_voice_url(preview_path) if preview_path else None,
        })
    return voices


def voice_clone_client_previews():
    return jsonify({"ok": True, "voices": _system_preview_profiles()})


def voice_clone_client_profiles():
    client_id = request.args.get("clientId") or request.form.get("clientId") or "guest"
    return jsonify({"ok": True, "clientId": _client_safe_id(client_id), "profiles": _read_client_profiles(client_id)})


def voice_clone_create_profile_api():
    client_id = request.form.get("clientId") or "guest"
    display_name = (request.form.get("displayName") or request.form.get("voiceName") or "My voice").strip() or "My voice"
    source_type = (request.form.get("sourceType") or "upload").strip() or "upload"
    target_model = (request.form.get("model") or DEFAULT_TARGET_MODEL).strip() or DEFAULT_TARGET_MODEL
    audio_file = request.files.get("audio") or request.files.get("voice") or request.files.get("voiceFile")
    if not audio_file or not audio_file.filename:
        return _json_error("Upload or record an audio sample before creating a voice identity.", 400)

    try:
        source_path = _save_client_uploaded_voice(audio_file, client_id, display_name)
        provider_name = _provider_preferred_name(display_name)
        if _dry_run():
            voice_parameter = f"dryrun_voice_{provider_name}"
        else:
            _api_key_value, voice_feature = _load_voice_feature()
            voice_parameter = voice_feature.create_voice(
                str(source_path),
                target_model=target_model,
                preferred_name=provider_name,
                audio_mime_type=audio_file.mimetype or mimetypes.guess_type(source_path.name)[0] or "audio/wav",
            )

        workspace = _client_workspace(client_id)
        profile_id = provider_name
        param_path = workspace / "params" / f"{profile_id}.txt"
        param_path.write_text(voice_parameter, encoding="utf-8")

        profile = {
            "profileId": profile_id,
            "displayName": display_name,
            "sourceType": source_type,
            "sourcePath": _relative(source_path),
            "sourceUrl": _public_voice_url(source_path),
            "voiceParamPath": _relative(param_path),
            "createdAt": datetime.now().isoformat(),
        }
        profiles = [p for p in _read_client_profiles(client_id) if p.get("profileId") != profile_id]
        profiles.insert(0, profile)
        _write_client_profiles(client_id, profiles)
        return jsonify({"ok": True, "profile": profile})
    except Exception as exc:
        traceback.print_exc()
        return _json_error(str(exc), 500)


def voice_clone_api_impl():
    """Generate narration from an existing voice identity.

    Uploaded/recorded audio should first call /api/voice-clone/profile. This endpoint
    uses a saved client profile or a system preview voice to synthesize narration.
    """
    prompt = (request.form.get("prompt") or request.form.get("text") or "").strip()
    if not prompt and request.is_json:
        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or data.get("text") or "").strip()
    if not prompt:
        return _json_error("Narration text is required.", 400)

    client_id = request.form.get("clientId") or "guest"
    target_model = (request.form.get("model") or DEFAULT_TARGET_MODEL).strip() or DEFAULT_TARGET_MODEL
    client_profile_id = (request.form.get("clientProfileId") or request.form.get("profileId") or "").strip()
    selected_preview_voice = (request.form.get("selectedPreviewVoice") or request.form.get("previewVoice") or "").strip()

    try:
        source_path = None
        if client_profile_id:
            profile = _profile_from_manifest(client_id, client_profile_id)
            if not profile:
                return _json_error("The selected client voice identity was not found. Create or reselect the voice.", 400)
            param_path = ROOT / profile["voiceParamPath"]
            preferred_name = profile.get("displayName") or profile.get("profileId") or DEFAULT_VOICE_NAME
        elif selected_preview_voice:
            safe_preview = _safe_stem(selected_preview_voice, DEFAULT_VOICE_NAME)
            param_path = VOICE_PARAMS_DIR / f"{safe_preview}.txt"
            preferred_name = safe_preview
            if not param_path.exists():
                return _json_error("The selected preview voice was not found.", 400)
        else:
            # Backward-compatible fallback: if an old client sends raw audio here,
            # create a client identity first, then use it for this generation.
            audio_file = request.files.get("audio") or request.files.get("voice") or request.files.get("voiceFile")
            if audio_file and audio_file.filename:
                request.form = request.form.copy()  # type: ignore[attr-defined]
                display_name = request.form.get("displayName") or request.form.get("voiceName") or audio_file.filename
                source_path = _save_client_uploaded_voice(audio_file, client_id, display_name)
                provider_name = _provider_preferred_name(display_name)
                _api_key_value, voice_feature = _load_voice_feature()
                voice_parameter = voice_feature.create_voice(
                    str(source_path),
                    target_model=target_model,
                    preferred_name=provider_name,
                    audio_mime_type=audio_file.mimetype or mimetypes.guess_type(source_path.name)[0] or "audio/wav",
                )
                workspace = _client_workspace(client_id)
                param_path = workspace / "params" / f"{provider_name}.txt"
                param_path.write_text(voice_parameter, encoding="utf-8")
                preferred_name = display_name
            else:
                return _json_error("Create or choose a voice identity before generating narration.", 400)

        if not param_path.exists():
            return _json_error("The selected voice identity file is missing.", 400)

        if _dry_run():
            return jsonify({"ok": True, "dryRun": True, "message": "Narration request accepted.", "voiceParamPath": _relative(param_path)})

        api_key, voice_feature = _load_voice_feature()
        voice_parameter = voice_feature.load_voice_from_disk(str(param_path))
        response = voice_feature.clone_voice(api_key=api_key, model=target_model, voice=voice_parameter, text=prompt, stream=False)
        remote_audio_url = _extract_audio_url(response)
        if not remote_audio_url:
            return _json_error("Voice generation completed but no audio URL was returned.", 502, raw=_safe_response(response))

        clone_path = _download_generated_audio(remote_audio_url, preferred_name)
        local_url = _public_voice_url(clone_path)
        return jsonify({
            "ok": True,
            "audioUrl": local_url,
            "assetUrl": local_url,
            "remoteAudioUrl": remote_audio_url,
            "sourcePath": _relative(source_path) if source_path else None,
            "voiceParamPath": _relative(param_path),
            "clonePath": _relative(clone_path),
            "controller": "voice_clone_controller",
            "raw": _safe_response(response),
        })
    except Exception as exc:
        traceback.print_exc()
        return _json_error(str(exc), 500)
'''
controller = controller[:start] + new_controller_block + controller[end+1:]
# replace register function
start = controller.index('def register_voice_clone_routes(app):')
new_register = r'''def register_voice_clone_routes(app):
    """Register Voice Clone client/admin views and APIs."""

    @app.route("/voice-clone", methods=["GET"])
    @app.route("/tasks/voice-clone", methods=["GET"])
    def voice_clone_client_view():
        return send_from_directory(FRONTEND_DIR, "voice_clone_client.html")

    @app.route("/admin/voice-clone", methods=["GET"])
    def voice_clone_admin_view():
        return send_from_directory(FRONTEND_DIR, "voice_clone_admin.html")

    @app.route("/api/voice-clone/previews", methods=["GET"])
    def voice_clone_previews_api():
        return voice_clone_client_previews()

    @app.route("/api/voice-clone/client-profiles", methods=["GET"])
    def voice_clone_client_profiles_api():
        return voice_clone_client_profiles()

    @app.route("/api/voice-clone/profile", methods=["POST"])
    def voice_clone_create_profile_route():
        return voice_clone_create_profile_api()

    @app.route("/api/admin/voice-clone", methods=["GET"])
    def voice_clone_admin_api():
        return voice_clone_admin_state()

    @app.route("/media/voices/<path:filename>", methods=["GET"])
    def voice_clone_media(filename: str):
        return send_from_directory(VOICES_DIR, filename)
'''
controller = controller[:start] + new_register
CONTROLLER.write_text(controller, encoding='utf-8')
py_compile.compile(str(CONTROLLER), doraise=True)

for path in [INDEX, README]:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    text = text.replace('Alibaba Media Studio', 'SyntaxMatrix Media Studio')
    text = text.replace('AlibabaMedia', 'SyntaxMatrixMedia')
    text = text.replace('Alibaba', 'provider')
    text = text.replace('>AM<', '>SM<')
    text = re.sub(r'\n\s*<a[^>]+href=["\']/admin/voice-clone["\'][\s\S]*?</a>\s*', '\n', text, flags=re.I)
    path.write_text(text, encoding='utf-8')

print('\nVoice Clone workflow patch complete.')
print('Restart Flask with: python app.py')
print('Open: http://127.0.0.1:5055/tasks/voice-clone?v=voice-flow')
