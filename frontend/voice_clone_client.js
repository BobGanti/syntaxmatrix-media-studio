(function () {
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
