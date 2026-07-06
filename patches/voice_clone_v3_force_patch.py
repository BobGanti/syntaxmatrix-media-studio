from pathlib import Path
import re
import py_compile
from datetime import datetime

ROOT = Path('.').resolve()
FRONTEND = ROOT / 'frontend'
CLIENT_HTML = FRONTEND / 'voice_clone_client.html'
CLIENT_JS = FRONTEND / 'voice_clone_client.js'
VOICE_CSS = FRONTEND / 'voice_clone.css'
CONTROLLER = ROOT / 'controllers' / 'voice_clone_controller.py'

required = [CLIENT_HTML, CLIENT_JS, VOICE_CSS, CONTROLLER]
missing = [str(p) for p in required if not p.exists()]
if missing:
    print('ERROR: Run this from the project root. Missing:')
    for item in missing:
        print(' -', item)
    raise SystemExit(1)

stamp = datetime.now().strftime('%Y%m%d%H%M%S')
for path in [CLIENT_HTML, CLIENT_JS, VOICE_CSS, CONTROLLER]:
    backup = path.with_name(path.name + f'.bak.voice-v3-{stamp}')
    backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    print('Backup:', backup)

CLIENT_HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SyntaxMatrix Voice Narration</title>
  <link rel="stylesheet" href="/styles.css" />
  <link rel="stylesheet" href="/voice_clone.css?v=voice-v3" />
</head>
<body class="feature-page voice-client-page voice-v3-active">
  <main class="feature-shell">
    <header class="feature-header">
      <a class="feature-back" href="/">← Studio</a>
      <p class="eyebrow">SyntaxMatrix Media Studio</p>
      <h1>Voice Narration</h1>
      <p>Create or choose a voice identity, then generate narration from your script.</p>
      <p class="voice-build-marker">VOICE FLOW V3 ACTIVE</p>
    </header>

    <section class="feature-grid voice-client-grid">
      <form id="voiceCloneForm" class="feature-card voice-client-card" enctype="multipart/form-data">
        <div class="section-heading compact">
          <p class="eyebrow">Client workflow</p>
          <h2>Create narration</h2>
          <p>Uploaded and recorded voices must first be saved as a private voice identity. System preview voices are shared presets.</p>
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
              <span id="recordingHelp">Record a clean voice sample, then save it as a reusable private voice identity.</span>
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
              <p class="muted-line">Voices created from your uploaded or recorded audio are private to this browser workspace.</p>
              <button class="secondary-button" id="refreshSavedVoices" type="button">Refresh</button>
            </div>
            <div id="clientVoiceList" class="compact-voice-list">Loading your saved voices…</div>
          </div>

          <div class="voice-source-panel" data-source-panel="preview" hidden>
            <div class="preview-voice-toolbar">
              <p class="muted-line">System preview voices are approved shared presets.</p>
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
  <script src="/voice_clone_client.js?v=voice-v3" defer></script>
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

  function stopPreviewAudio() {
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.currentTime = 0;
      previewAudio = null;
    }
    document.querySelectorAll('.voice-preview-play.playing').forEach(btn => {
      btn.classList.remove('playing');
      btn.textContent = '▶';
    });
  }

  function setPanelVisibility(panel, visible) {
    panel.hidden = !visible;
    panel.style.display = visible ? 'grid' : 'none';
    panel.classList.toggle('is-active', visible);
  }

  function setSourceMode(mode) {
    sourceMode = mode;
    stopPreviewAudio();

    tabs.forEach(tab => {
      const active = tab.dataset.sourceMode === mode;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
    });

    panels.forEach(panel => setPanelVisibility(panel, panel.dataset.sourcePanel === mode));

    if (mode !== 'preview' && previewVoiceList) previewVoiceList.innerHTML = '';
    if (mode === 'saved') loadClientProfiles();
    if (mode === 'preview') loadPreviewVoices();
  }

  function markSelectedVoice(voice) {
    selectedVoice = voice;
    if (!voice) {
      selectedVoiceBox.hidden = true;
      selectedVoiceBox.style.display = 'none';
      selectedVoiceName.textContent = 'None';
      return;
    }
    selectedVoiceBox.hidden = false;
    selectedVoiceBox.style.display = 'grid';
    selectedVoiceName.textContent = voice.displayName || voice.name || voice.voiceName || voice.id;
  }

  function flattenBuffers(buffers) {
    const total = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
    const result = new Float32Array(total);
    let offset = 0;
    buffers.forEach(buffer => { result.set(buffer, offset); offset += buffer.length; });
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
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
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
      if (recorderNode) { recorderNode.disconnect(); recorderNode.onaudioprocess = null; }
      if (micSource) micSource.disconnect();
      if (micStream) micStream.getTracks().forEach(track => track.stop());
      if (audioContext) await audioContext.close();
      const wavBuffer = encodeWav(flattenBuffers(recordingBuffers), recordingSampleRate);
      recordedBlob = new Blob([wavBuffer], { type: 'audio/wav' });
      recordedFileName = `client_recording_${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}.wav`;
      recordedPreview.src = URL.createObjectURL(recordedBlob);
      recordedPreview.hidden = false;
      createRecordedProfileButton.disabled = false;
      startRecordingButton.disabled = false;
      stopRecordingButton.disabled = true;
      discardRecordingButton.disabled = false;
      recordingStatus.textContent = 'Recording ready';
      recordingHelp.textContent = 'Click Create voice identity from recording before generating narration.';
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
    createRecordedProfileButton.disabled = true;
    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
    discardRecordingButton.disabled = true;
    recordingStatus.textContent = 'Recorder ready';
    recordingHelp.textContent = 'Record a new voice sample before creating a voice identity.';
  }

  async function createVoiceProfileFromFile(file, filename) {
    const formData = new FormData();
    formData.append('clientId', clientId());
    formData.append('model', voiceModelInput.value || 'qwen3-tts-vc-2026-01-22');
    formData.append('displayName', filename.replace(/\.[^.]+$/, ''));
    formData.append('audio', file, filename);

    const response = await fetch('/api/voice-clone/profile', { method: 'POST', body: formData });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
    if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
    return data.profile;
  }

  async function handleCreateUploadProfile() {
    const file = voiceAudioInput.files?.[0];
    if (!file) { toast('Choose audio first', 'Select an audio file before creating a voice identity.'); return; }
    createUploadProfileButton.disabled = true;
    createUploadProfileButton.textContent = 'Creating voice identity…';
    try {
      const profile = await createVoiceProfileFromFile(file, file.name);
      markSelectedVoice({ ...profile, kind: 'client' });
      toast('Voice identity created', `${profile.displayName || profile.id} is selected for narration.`);
      await loadClientProfiles();
      setSourceMode('saved');
    } catch (error) {
      toast('Voice identity failed', error.message || 'Could not create voice identity.');
      console.error(error);
    } finally {
      createUploadProfileButton.disabled = false;
      createUploadProfileButton.textContent = 'Create voice identity from upload';
    }
  }

  async function handleCreateRecordedProfile() {
    if (!recordedBlob) { toast('Record first', 'Record and stop before creating a voice identity.'); return; }
    createRecordedProfileButton.disabled = true;
    createRecordedProfileButton.textContent = 'Creating voice identity…';
    try {
      const file = new File([recordedBlob], recordedFileName || 'client_recording.wav', { type: 'audio/wav' });
      const profile = await createVoiceProfileFromFile(file, file.name);
      markSelectedVoice({ ...profile, kind: 'client' });
      toast('Voice identity created', `${profile.displayName || profile.id} is selected for narration.`);
      await loadClientProfiles();
      setSourceMode('saved');
    } catch (error) {
      toast('Voice identity failed', error.message || 'Could not create voice identity.');
      console.error(error);
    } finally {
      createRecordedProfileButton.disabled = false;
      createRecordedProfileButton.textContent = 'Create voice identity from recording';
    }
  }

  function compactVoiceRow(voice, kind, index) {
    const selected = selectedVoice && selectedVoice.kind === kind && (selectedVoice.id || selectedVoice.voiceName) === (voice.id || voice.voiceName);
    const playButton = voice.previewUrl ? `<button class="voice-preview-play" type="button" data-play-kind="${kind}" data-play-index="${index}">▶</button>` : `<span class="voice-preview-play disabled">–</span>`;
    return `
      <article class="preview-voice-row ${selected ? 'selected' : ''}">
        ${playButton}
        <button class="voice-preview-name" type="button" data-use-kind="${kind}" data-use-index="${index}">${escapeHtml(voice.displayName || voice.name || voice.voiceName || voice.id)}</button>
        <button class="voice-preview-use" type="button" data-use-kind="${kind}" data-use-index="${index}">${selected ? 'Selected' : 'Use'}</button>
      </article>`;
  }

  let lastClientProfiles = [];
  let lastPreviewVoices = [];

  async function loadClientProfiles() {
    if (!clientVoiceList) return;
    clientVoiceList.innerHTML = '<p class="muted-line">Loading your saved voices…</p>';
    try {
      const response = await fetch(`/api/voice-clone/client-profiles?clientId=${encodeURIComponent(clientId())}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      lastClientProfiles = Array.isArray(data.profiles) ? data.profiles : [];
      if (!lastClientProfiles.length) {
        clientVoiceList.innerHTML = '<p class="muted-line">No saved voices yet. Upload or record audio, then create a voice identity.</p>';
        return;
      }
      clientVoiceList.innerHTML = lastClientProfiles.map((voice, index) => compactVoiceRow(voice, 'client', index)).join('');
      bindVoiceListButtons(clientVoiceList, lastClientProfiles, 'client');
    } catch (error) {
      clientVoiceList.innerHTML = `<p class="muted-line">Could not load saved voices: ${escapeHtml(error.message || error)}</p>`;
    }
  }

  async function loadPreviewVoices() {
    if (!previewVoiceList) return;
    previewVoiceList.innerHTML = '<p class="muted-line">Loading system preview voices…</p>';
    try {
      const response = await fetch('/api/voice-clone/previews');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      lastPreviewVoices = Array.isArray(data.voices) ? data.voices : [];
      if (!lastPreviewVoices.length) {
        previewVoiceList.innerHTML = '<p class="muted-line">No system preview voices are available yet.</p>';
        return;
      }
      previewVoiceList.innerHTML = lastPreviewVoices.map((voice, index) => compactVoiceRow(voice, 'preview', index)).join('');
      bindVoiceListButtons(previewVoiceList, lastPreviewVoices, 'preview');
    } catch (error) {
      previewVoiceList.innerHTML = `<p class="muted-line">Could not load preview voices: ${escapeHtml(error.message || error)}</p>`;
    }
  }

  function bindVoiceListButtons(container, voices, kind) {
    container.querySelectorAll('[data-use-kind]').forEach(button => {
      button.addEventListener('click', () => {
        const voice = voices[Number(button.dataset.useIndex)];
        if (!voice) return;
        markSelectedVoice({ ...voice, kind });
        if (kind === 'client') loadClientProfiles(); else loadPreviewVoices();
      });
    });
    container.querySelectorAll('[data-play-kind]').forEach(button => {
      button.addEventListener('click', () => {
        const voice = voices[Number(button.dataset.playIndex)];
        playPreviewVoice(voice?.previewUrl, button);
      });
    });
  }

  function playPreviewVoice(url, button) {
    if (!url) { toast('No preview audio', 'This voice has no preview audio yet.'); return; }
    stopPreviewAudio();
    previewAudio = new Audio(url);
    button.classList.add('playing');
    button.textContent = '■';
    previewAudio.addEventListener('ended', stopPreviewAudio);
    previewAudio.addEventListener('error', () => { stopPreviewAudio(); toast('Preview failed', 'Could not play this preview.'); });
    previewAudio.play().catch(error => { stopPreviewAudio(); toast('Preview blocked', error.message || 'Browser blocked audio playback.'); });
  }

  function buildNarrationPayload() {
    const prompt = String(document.querySelector('#voicePrompt')?.value || '').trim();
    if (!prompt) { toast('Narration text required', 'Paste the script before generating.'); return null; }
    if (!selectedVoice) { toast('Voice required', 'Create or choose a voice identity first.'); return null; }
    const formData = new FormData();
    formData.append('clientId', clientId());
    formData.append('prompt', prompt);
    formData.append('model', voiceModelInput.value || 'qwen3-tts-vc-2026-01-22');
    formData.append('sourceMode', selectedVoice.kind);
    if (selectedVoice.kind === 'client') formData.append('clientProfileId', selectedVoice.id);
    if (selectedVoice.kind === 'preview') formData.append('selectedPreviewVoice', selectedVoice.voiceName);
    return formData;
  }

  function renderSuccess(data) {
    const assetUrl = data.assetUrl || data.audioUrl;
    title.textContent = 'Narration ready';
    status.textContent = 'The generated audio is ready.';
    if (assetUrl) {
      const safeUrl = escapeHtml(assetUrl);
      preview.innerHTML = `<audio src="${safeUrl}" controls></audio><div class="asset-lite-actions"><a class="asset-lite-button primary" href="${safeUrl}" download>Download</a><button class="asset-lite-button" type="button" id="copyVoiceUrl">Copy URL</button></div>`;
      document.querySelector('#copyVoiceUrl')?.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(new URL(assetUrl, window.location.href).href); toast('URL copied', 'The audio URL is now on your clipboard.'); }
        catch { window.prompt('Copy audio URL:', assetUrl); }
      });
    } else {
      preview.innerHTML = '<p>No audio URL was returned.</p>';
    }
    meta.innerHTML = `<div><dt>Voice</dt><dd>${escapeHtml(selectedVoice?.displayName || selectedVoice?.name || selectedVoice?.voiceName || '—')}</dd></div><div><dt>Output</dt><dd>${escapeHtml(data.clonePath || assetUrl || '—')}</dd></div>`;
  }

  tabs.forEach(tab => tab.addEventListener('click', () => setSourceMode(tab.dataset.sourceMode)));
  closePreviewVoices?.addEventListener('click', () => setSourceMode('upload'));
  refreshPreviewVoices?.addEventListener('click', loadPreviewVoices);
  refreshSavedVoices?.addEventListener('click', loadClientProfiles);
  reloadClientProfiles?.addEventListener('click', () => { setSourceMode('saved'); loadClientProfiles(); });
  createUploadProfileButton?.addEventListener('click', handleCreateUploadProfile);
  createRecordedProfileButton?.addEventListener('click', handleCreateRecordedProfile);
  startRecordingButton?.addEventListener('click', startRecording);
  stopRecordingButton?.addEventListener('click', stopRecording);
  discardRecordingButton?.addEventListener('click', discardRecording);

  voiceAudioInput?.addEventListener('change', () => {
    const file = voiceAudioInput.files?.[0];
    uploadFileName.textContent = file ? `${file.name} is ready. Click Create voice identity from upload.` : 'No audio selected yet.';
  });

  form?.addEventListener('reset', () => {
    window.setTimeout(() => {
      stopPreviewAudio();
      selectedVoice = null;
      markSelectedVoice(null);
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
    const formData = buildNarrationPayload();
    if (!formData) return;
    submit.disabled = true;
    submit.textContent = 'Generating narration…';
    title.textContent = 'Generating narration…';
    status.textContent = 'Submitting selected voice identity to the controller.';
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
  loadClientProfiles();
})();
''', encoding='utf-8')

css = VOICE_CSS.read_text(encoding='utf-8')
css = re.sub(r"\n/\* VOICE_FLOW_V3_START \*/[\s\S]*?/\* VOICE_FLOW_V3_END \*/\n?", "\n", css)
css += r'''

/* VOICE_FLOW_V3_START */
[hidden], .voice-source-panel[hidden] { display: none !important; }
.voice-build-marker { display: inline-flex; width: max-content; border: 1px solid rgba(34,197,94,.45); color: #bbf7d0; background: rgba(34,197,94,.12); border-radius: 999px; padding: .35rem .65rem; font-size: .75rem; font-weight: 900; letter-spacing: .08em; }
.voice-client-grid { grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr); }
.voice-source-section,.recorder-card,.upload-drop-lite{border:1px solid var(--line,rgba(15,23,42,.12));border-radius:1rem;background:var(--surface-muted,#f8fafc)}
.voice-source-section{padding:1rem;display:grid;gap:.9rem}.voice-source-header{display:flex;justify-content:space-between;gap:.75rem;align-items:center;flex-wrap:wrap}.voice-source-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}.voice-source-tab{min-height:2.75rem;border-radius:999px;border:1px solid var(--line,rgba(15,23,42,.12));background:var(--surface,#fff);color:var(--text,#111827);font-weight:850;cursor:pointer}.voice-source-tab.active{border-color:transparent;background:linear-gradient(135deg,var(--brand,#13b981),var(--brand-2,#3b82f6));color:#06130f}.voice-source-panel{display:grid;gap:.75rem}.upload-drop-lite,.recorder-card{padding:1rem;display:grid;gap:.75rem}.muted-line{color:var(--muted,#667085);line-height:1.45;margin:0}.recorder-actions,.preview-voice-toolbar,.toolbar-actions{display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;justify-content:space-between}.recorder-card audio,.voice-result-preview audio{width:100%}.compact-voice-list{display:grid;gap:.55rem}.preview-voice-row{display:grid;grid-template-columns:2.4rem minmax(0,1fr) auto;align-items:center;gap:.65rem;padding:.65rem;border:1px solid var(--line,rgba(15,23,42,.12));border-radius:999px;background:var(--surface-muted,#f8fafc)}.preview-voice-row.selected{outline:3px solid color-mix(in srgb,var(--brand,#13b981) 35%,transparent)}.voice-preview-play,.voice-preview-name,.voice-preview-use{border:0;cursor:pointer;font-weight:850}.voice-preview-play{width:2.1rem;height:2.1rem;border-radius:999px;display:grid;place-items:center;background:linear-gradient(135deg,var(--brand,#13b981),var(--brand-2,#3b82f6));color:#06130f}.voice-preview-play.disabled{opacity:.45;background:var(--surface,#fff)}.voice-preview-play.playing{background:var(--surface,#fff);color:var(--text,#111827);border:1px solid var(--line,rgba(15,23,42,.12))}.voice-preview-name{min-width:0;overflow:hidden;text-overflow:ellipsis;text-align:left;white-space:nowrap;background:transparent;color:var(--text,#111827)}.voice-preview-use{border-radius:999px;padding:.55rem .85rem;background:var(--surface,#fff);color:var(--text,#111827);border:1px solid var(--line,rgba(15,23,42,.12))}.selected-voice-box{border:1px solid color-mix(in srgb,var(--brand,#13b981) 45%,var(--line,rgba(15,23,42,.12)));background:color-mix(in srgb,var(--brand,#13b981) 10%,var(--surface,#fff));border-radius:1rem;padding:.8rem;display:grid;gap:.2rem}.selected-voice-box span{color:var(--muted,#667085);font-size:.82rem}.asset-lite-actions{display:flex;flex-wrap:wrap;gap:.6rem;margin-top:.8rem}.asset-lite-button{min-height:2.55rem;border-radius:999px;border:1px solid var(--line,rgba(15,23,42,.12));background:var(--surface,#fff);color:var(--text,#111827);padding:.68rem 1rem;font-weight:800;text-decoration:none;cursor:pointer}.asset-lite-button.primary{border-color:transparent;background:linear-gradient(135deg,var(--brand,#13b981),var(--brand-2,#3b82f6));color:#06130f}@media(max-width:900px){.voice-client-grid,.voice-source-tabs{grid-template-columns:1fr}.preview-voice-row{grid-template-columns:2.4rem minmax(0,1fr);border-radius:1rem}.voice-preview-use{grid-column:1/-1;width:100%}}
/* VOICE_FLOW_V3_END */
'''
VOICE_CSS.write_text(css, encoding='utf-8')

controller = CONTROLLER.read_text(encoding='utf-8')

inject_marker = '# VOICE_FLOW_V3_CONTROLLER_START'
if inject_marker not in controller:
    helper = r'''

# VOICE_FLOW_V3_CONTROLLER_START
def _client_id() -> str:
    value = (request.form.get('clientId') or request.args.get('clientId') or 'default_client').strip()
    value = secure_filename(value).replace('-', '_') or 'default_client'
    return value[:80]


def _client_dir(client_id: str) -> pathlib.Path:
    path = VOICES_DIR / 'client_profiles' / _client_id_from_value(client_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client_id_from_value(value: str) -> str:
    return (secure_filename(value or 'default_client').replace('-', '_') or 'default_client')[:80]


def _provider_safe_voice_name() -> str:
    # Provider rejected earlier free-text values. Keep this short, lowercase, and alphanumeric.
    import random
    suffix = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(6))
    return f"smxv{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"


def _client_profile_path(client_id: str, profile_id: str) -> pathlib.Path:
    return _client_dir(client_id) / f"{_safe_stem(profile_id, 'voice_profile')}.json"


def _read_client_profile(client_id: str, profile_id: str) -> Optional[dict[str, Any]]:
    path = _client_profile_path(client_id, profile_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _list_client_profiles_raw(client_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    directory = _client_dir(client_id)
    for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            profile = json.loads(path.read_text(encoding='utf-8'))
            profile.pop('voiceParameter', None)
            items.append(profile)
        except Exception:
            continue
    return items


def voice_clone_client_profiles_api():
    return jsonify({'ok': True, 'profiles': _list_client_profiles_raw(_client_id())})


def _display_voice_name(stem: str) -> str:
    cleaned = stem.replace('_', ' ').replace('-', ' ').strip()
    return cleaned.title() or stem


def voice_clone_client_previews():
    voices: list[dict[str, Any]] = []
    params = sorted(VOICE_PARAMS_DIR.glob('*.txt'), key=lambda path: path.stat().st_mtime, reverse=True)
    for param in params:
        preview_path = None
        for ext in ('wav', 'mp3', 'm4a', 'ogg', 'webm'):
            for candidate in (VOICE_PREVIEWS_DIR / f'{param.stem}_preview.{ext}', VOICE_PREVIEWS_DIR / f'{param.stem}.{ext}'):
                if candidate.exists() and candidate.is_file():
                    preview_path = candidate
                    break
            if preview_path:
                break
        voices.append({
            'voiceName': param.stem,
            'displayName': _display_voice_name(param.stem),
            'previewUrl': _public_voice_url(preview_path) if preview_path else None,
        })
    return jsonify({'ok': True, 'voices': voices})


def voice_clone_create_profile_api():
    audio_file = request.files.get('audio') or request.files.get('voice') or request.files.get('voiceFile')
    if not audio_file or not audio_file.filename:
        return _json_error('Upload or record audio before creating a voice identity.', 400)

    client_id = _client_id()
    display_name = (request.form.get('displayName') or pathlib.Path(audio_file.filename).stem or 'My voice').strip()
    target_model = (request.form.get('model') or DEFAULT_TARGET_MODEL).strip() or DEFAULT_TARGET_MODEL
    provider_name = _provider_safe_voice_name()
    source_path: Optional[pathlib.Path] = None

    try:
        source_path = _save_uploaded_voice(audio_file, provider_name)

        if _dry_run():
            voice_parameter = f'dryrun_voice_{provider_name}'
        else:
            api_key, workspace_id_value = _require_credentials()
            import dashscope  # type: ignore
            import ali_voice_clone as voice_feature
            voice_feature.ALIBABA_API_KEY = api_key
            voice_feature.WORKSPACE_ID = workspace_id_value
            dashscope.base_http_api_url = _provider_base_url()
            voice_parameter = voice_feature.create_voice(
                str(source_path),
                target_model=target_model,
                preferred_name=provider_name,
                audio_mime_type=audio_file.mimetype or mimetypes.guess_type(source_path.name)[0] or 'audio/wav',
            )

        profile_id = provider_name
        profile = {
            'id': profile_id,
            'displayName': display_name,
            'providerName': provider_name,
            'voiceParameter': voice_parameter,
            'sourcePath': _relative(source_path),
            'createdAt': datetime.now().isoformat(),
            'kind': 'client',
        }
        profile_path = _client_profile_path(client_id, profile_id)
        profile_path.write_text(json.dumps(profile, indent=2), encoding='utf-8')

        public_profile = dict(profile)
        public_profile.pop('voiceParameter', None)
        return jsonify({'ok': True, 'profile': public_profile})
    except Exception as exc:
        traceback.print_exc()
        return _json_error(str(exc), 500)


def _voice_parameter_from_selected_request() -> tuple[str, str, Optional[pathlib.Path]]:
    client_profile_id = (request.form.get('clientProfileId') or '').strip()
    selected_preview = (request.form.get('selectedPreviewVoice') or '').strip()
    preferred_name = DEFAULT_VOICE_NAME
    param_path: Optional[pathlib.Path] = None

    if client_profile_id:
        profile = _read_client_profile(_client_id(), client_profile_id)
        if not profile:
            raise FileNotFoundError('Selected client voice identity was not found. Recreate it or refresh My saved voices.')
        return profile['voiceParameter'], profile.get('providerName') or profile['id'], None

    if selected_preview:
        param_path = VOICE_PARAMS_DIR / f'{_safe_stem(selected_preview, DEFAULT_VOICE_NAME)}.txt'
        if not param_path.exists():
            found = _find_existing_voice_param(selected_preview)
            if not found:
                raise FileNotFoundError('Selected preview voice was not found.')
            param_path = found
        return param_path.read_text(encoding='utf-8').strip(), param_path.stem, param_path

    preferred_name = (request.form.get('voiceName') or request.form.get('preferredName') or DEFAULT_VOICE_NAME).strip() or DEFAULT_VOICE_NAME
    found = _find_existing_voice_param(preferred_name)
    if not found:
        raise FileNotFoundError('Create or choose a voice identity before generating narration.')
    return found.read_text(encoding='utf-8').strip(), found.stem, found


def voice_clone_api_impl_v3():
    prompt = (request.form.get('prompt') or request.form.get('text') or '').strip()
    if not prompt:
        return _json_error('Narration text is required.', 400)
    target_model = (request.form.get('model') or DEFAULT_TARGET_MODEL).strip() or DEFAULT_TARGET_MODEL
    try:
        if _dry_run():
            return jsonify({'ok': True, 'dryRun': True, 'message': 'Narration request accepted.', 'controller': 'voice_clone_controller'})
        api_key, workspace_id_value = _require_credentials()
        import dashscope  # type: ignore
        import ali_voice_clone as voice_feature
        voice_feature.ALIBABA_API_KEY = api_key
        voice_feature.WORKSPACE_ID = workspace_id_value
        dashscope.base_http_api_url = _provider_base_url()
        voice_parameter, preferred_name, param_path = _voice_parameter_from_selected_request()
        response = voice_feature.clone_voice(api_key=api_key, model=target_model, voice=voice_parameter, text=prompt, stream=False)
        remote_audio_url = _extract_audio_url(response)
        if not remote_audio_url:
            return _json_error('Voice generation completed but no audio URL was returned.', 502, raw=_safe_response(response))
        clone_path = _download_generated_audio(remote_audio_url, preferred_name)
        local_url = _public_voice_url(clone_path)
        return jsonify({
            'ok': True,
            'audioUrl': local_url,
            'assetUrl': local_url,
            'remoteAudioUrl': remote_audio_url,
            'voiceParamPath': _relative(param_path) if param_path else None,
            'clonePath': _relative(clone_path),
            'controller': 'voice_clone_controller',
            'raw': _safe_response(response),
        })
    except Exception as exc:
        traceback.print_exc()
        return _json_error(str(exc), 500)

# Replace the older one-step implementation with the two-step v3 implementation.
voice_clone_api_impl = voice_clone_api_impl_v3
# VOICE_FLOW_V3_CONTROLLER_END
'''
    controller = controller.replace('\ndef register_voice_clone_routes(app):', helper + '\n\ndef register_voice_clone_routes(app):', 1)

# Insert v3 API routes inside register_voice_clone_routes if missing.
if "api/voice-clone/profile" not in controller:
    route_block = r'''
    @app.route('/api/voice-clone/profile', methods=['POST'])
    def voice_clone_profile_api():
        return voice_clone_create_profile_api()

    @app.route('/api/voice-clone/client-profiles', methods=['GET'])
    def voice_clone_profiles_api():
        return voice_clone_client_profiles_api()

    @app.route('/api/voice-clone/previews', methods=['GET'])
    def voice_clone_previews_api():
        return voice_clone_client_previews()

'''
    marker = '    @app.route("/api/admin/voice-clone", methods=["GET"])'
    if marker in controller:
        controller = controller.replace(marker, route_block + marker, 1)
    else:
        raise SystemExit('Could not insert v3 voice routes. Could not find admin API route marker.')

CONTROLLER.write_text(controller, encoding='utf-8')
py_compile.compile(str(CONTROLLER), doraise=True)

print('\nVOICE FLOW V3 PATCH APPLIED')
print('Restart Flask: python app.py')
print('Open: http://127.0.0.1:5055/tasks/voice-clone?v=voice-v3')
print('You MUST see the badge: VOICE FLOW V3 ACTIVE')
