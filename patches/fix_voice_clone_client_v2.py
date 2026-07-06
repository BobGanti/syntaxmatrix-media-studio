from pathlib import Path
import re
import py_compile
from datetime import datetime

ROOT = Path(".").resolve()
FRONTEND = ROOT / "frontend"
CLIENT_JS = FRONTEND / "voice_clone_client.js"
VOICE_CSS = FRONTEND / "voice_clone.css"
INDEX = FRONTEND / "index.html"
README = ROOT / "README.md"
CONTROLLER = ROOT / "controllers" / "voice_clone_controller.py"

required = [CLIENT_JS, VOICE_CSS, CONTROLLER]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Run this from the project root. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CLIENT_JS, VOICE_CSS, INDEX, README, CONTROLLER]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.voice-v2-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

CLIENT_JS.write_text(r'''(function () {
  const form = document.querySelector('#voiceCloneForm');
  const submit = document.querySelector('#voiceSubmit');
  const title = document.querySelector('#voiceResultTitle');
  const status = document.querySelector('#voiceResultStatus');
  const preview = document.querySelector('#voiceResultPreview');
  const meta = document.querySelector('#voiceResultMeta');
  const toastRegion = document.querySelector('#toastRegion');

  const voiceNameInput = document.querySelector('#voiceName');
  const voiceModelInput = document.querySelector('#voiceModel');
  const voiceAudioInput = document.querySelector('#voiceAudio');
  const uploadFileName = document.querySelector('#uploadFileName');

  const tabs = [...document.querySelectorAll('[data-source-mode]')];
  const panels = [...document.querySelectorAll('[data-source-panel]')];
  const previewVoiceList = document.querySelector('#previewVoiceList');
  const refreshPreviewVoices = document.querySelector('#refreshPreviewVoices');

  const startRecordingButton = document.querySelector('#startRecording');
  const stopRecordingButton = document.querySelector('#stopRecording');
  const discardRecordingButton = document.querySelector('#discardRecording');
  const recordingStatus = document.querySelector('#recordingStatus');
  const recordingHelp = document.querySelector('#recordingHelp');
  const recordedPreview = document.querySelector('#recordedPreview');

  let sourceMode = 'upload';
  let selectedPreviewVoice = null;

  let audioContext = null;
  let micStream = null;
  let micSource = null;
  let recorderNode = null;
  let recordingBuffers = [];
  let recordingSampleRate = 44100;
  let recordedBlob = null;
  let recordedFileName = '';

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

  function makeClientVoiceName(prefix) {
    const stamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
    return `${prefix}_${stamp}`;
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

    if (mode === 'upload') {
      voiceNameInput.value = makeClientVoiceName('client_upload');
    }

    if (mode === 'record') {
      voiceNameInput.value = makeClientVoiceName('client_recording');
    }

    if (mode === 'preview') {
      loadPreviewVoices();
    }
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
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  }

  function encodeWav(floatSamples, sampleRate) {
    const bytesPerSample = 2;
    const channelCount = 1;
    const dataLength = floatSamples.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, channelCount, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * channelCount * bytesPerSample, true);
    view.setUint16(32, channelCount * bytesPerSample, true);
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

      recorderNode.onaudioprocess = event => {
        const input = event.inputBuffer.getChannelData(0);
        recordingBuffers.push(new Float32Array(input));
      };

      micSource.connect(recorderNode);
      recorderNode.connect(audioContext.destination);

      startRecordingButton.disabled = true;
      stopRecordingButton.disabled = false;
      discardRecordingButton.disabled = true;

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

      if (micSource) {
        micSource.disconnect();
      }

      if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
      }

      if (audioContext) {
        await audioContext.close();
      }

      const merged = flattenBuffers(recordingBuffers);
      const wavBuffer = encodeWav(merged, recordingSampleRate);

      recordedBlob = new Blob([wavBuffer], { type: 'audio/wav' });
      recordedFileName = `${makeClientVoiceName('client_recording')}.wav`;

      recordedPreview.src = URL.createObjectURL(recordedBlob);
      recordedPreview.hidden = false;

      voiceNameInput.value = recordedFileName.replace(/\.[^.]+$/, '');

      recordingStatus.textContent = 'Recording ready';
      recordingHelp.textContent = 'This WAV recording will be uploaded as the source voice.';

      startRecordingButton.disabled = false;
      stopRecordingButton.disabled = true;
      discardRecordingButton.disabled = false;
    } catch (error) {
      toast('Recording failed', error.message || 'Could not create WAV recording.');
      console.error(error);
    }
  }

  function discardRecording() {
    recordedBlob = null;
    recordingBuffers = [];
    recordedFileName = '';

    if (recordedPreview.src) {
      URL.revokeObjectURL(recordedPreview.src);
    }

    recordedPreview.removeAttribute('src');
    recordedPreview.hidden = true;

    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
    discardRecordingButton.disabled = true;

    recordingStatus.textContent = 'Recorder ready';
    recordingHelp.textContent = 'Record a new voice sample before generating narration.';
    voiceNameInput.value = makeClientVoiceName('client_recording');
  }

  function playPreviewVoice(url, button) {
    if (!url) {
      toast('No preview audio', 'This voice does not have a preview file yet.');
      return;
    }

    document.querySelectorAll('.voice-preview-play.playing').forEach(btn => {
      btn.classList.remove('playing');
      btn.textContent = '▶';
    });

    const audio = new Audio(url);
    button.classList.add('playing');
    button.textContent = '■';

    audio.addEventListener('ended', () => {
      button.classList.remove('playing');
      button.textContent = '▶';
    });

    audio.addEventListener('error', () => {
      button.classList.remove('playing');
      button.textContent = '▶';
      toast('Preview failed', 'The preview audio could not be played.');
    });

    audio.play().catch(error => {
      button.classList.remove('playing');
      button.textContent = '▶';
      toast('Preview blocked', error.message || 'Browser blocked audio playback.');
    });
  }

  async function loadPreviewVoices() {
    previewVoiceList.innerHTML = '<p class="muted-line">Loading preview voices…</p>';

    try {
      const response = await fetch('/api/voice-clone/previews');
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

      const voices = Array.isArray(data.voices) ? data.voices : [];

      if (!voices.length) {
        previewVoiceList.innerHTML = '<p class="muted-line">No preview voices are available yet.</p>';
        return;
      }

      previewVoiceList.innerHTML = voices.map((voice, index) => `
        <article class="preview-voice-row ${selectedPreviewVoice?.voiceName === voice.voiceName ? 'selected' : ''}">
          <button class="voice-preview-play" type="button" data-preview-index="${index}" aria-label="Play ${escapeHtml(voice.displayName || voice.voiceName)}">▶</button>
          <button class="voice-preview-name" type="button" data-choose-index="${index}">
            ${escapeHtml(voice.displayName || voice.voiceName)}
          </button>
          <button class="voice-preview-use" type="button" data-choose-index="${index}">
            ${selectedPreviewVoice?.voiceName === voice.voiceName ? 'Selected' : 'Use'}
          </button>
        </article>
      `).join('');

      previewVoiceList.querySelectorAll('[data-preview-index]').forEach(button => {
        button.addEventListener('click', event => {
          event.preventDefault();
          const voice = voices[Number(button.dataset.previewIndex)];
          playPreviewVoice(voice?.previewUrl, button);
        });
      });

      previewVoiceList.querySelectorAll('[data-choose-index]').forEach(button => {
        button.addEventListener('click', event => {
          event.preventDefault();
          const voice = voices[Number(button.dataset.chooseIndex)];
          if (!voice) return;

          selectedPreviewVoice = voice;
          voiceNameInput.value = voice.voiceName;

          toast('Preview voice selected', voice.displayName || voice.voiceName);
          loadPreviewVoices();
        });
      });
    } catch (error) {
      previewVoiceList.innerHTML = `<p class="muted-line">Could not load preview voices: ${escapeHtml(error.message || error)}</p>`;
      console.error(error);
    }
  }

  function buildFormData() {
    const prompt = String(document.querySelector('#voicePrompt')?.value || '').trim();

    if (!prompt) {
      toast('Narration text required', 'Paste the script before submitting.');
      return null;
    }

    const formData = new FormData();
    formData.append('prompt', prompt);
    formData.append('model', voiceModelInput.value || 'qwen3-tts-vc-2026-01-22');
    formData.append('sourceMode', sourceMode);

    if (sourceMode === 'upload') {
      const file = voiceAudioInput.files?.[0];

      if (!file) {
        toast('Voice sample required', 'Choose an audio file first.');
        return null;
      }

      formData.append('voiceName', voiceNameInput.value || makeClientVoiceName('client_upload'));
      formData.append('audio', file, file.name);
      return formData;
    }

    if (sourceMode === 'record') {
      if (!recordedBlob) {
        toast('Recording required', 'Record your voice first.');
        return null;
      }

      formData.append('voiceName', voiceNameInput.value || makeClientVoiceName('client_recording'));
      formData.append('audio', recordedBlob, recordedFileName || 'client_recording.wav');
      return formData;
    }

    if (sourceMode === 'preview') {
      if (!selectedPreviewVoice) {
        toast('Preview voice required', 'Choose one preview voice first.');
        return null;
      }

      formData.append('voiceName', selectedPreviewVoice.voiceName);
      formData.append('selectedPreviewVoice', selectedPreviewVoice.voiceName);
      return formData;
    }

    toast('Voice source required', 'Choose upload, record, or preview voice.');
    return null;
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
        </div>
      `;

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
      <div><dt>Source</dt><dd>${escapeHtml(sourceMode)}</dd></div>
      <div><dt>Output</dt><dd>${escapeHtml(data.clonePath || assetUrl || '—')}</dd></div>
    `;
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => setSourceMode(tab.dataset.sourceMode));
  });

  refreshPreviewVoices?.addEventListener('click', loadPreviewVoices);

  voiceAudioInput?.addEventListener('change', () => {
    const file = voiceAudioInput.files?.[0];

    if (file) {
      uploadFileName.textContent = `${file.name} is ready.`;
      voiceNameInput.value = file.name.replace(/\.[^.]+$/, '');
    } else {
      uploadFileName.textContent = 'No audio selected yet.';
    }
  });

  startRecordingButton?.addEventListener('click', startRecording);
  stopRecordingButton?.addEventListener('click', stopRecording);
  discardRecordingButton?.addEventListener('click', discardRecording);

  form?.addEventListener('reset', () => {
    window.setTimeout(() => {
      selectedPreviewVoice = null;
      discardRecording();
      if (voiceAudioInput) voiceAudioInput.value = '';
      uploadFileName.textContent = 'No audio selected yet.';
      preview.innerHTML = '';
      meta.innerHTML = '';
      title.textContent = 'No narration yet';
      status.textContent = 'Choose a voice source and submit your narration script.';
      setSourceMode('upload');
    }, 0);
  });

  form?.addEventListener('submit', async event => {
    event.preventDefault();

    const formData = buildFormData();
    if (!formData) return;

    submit.disabled = true;
    submit.textContent = 'Generating narration…';
    title.textContent = 'Generating narration…';
    status.textContent = 'Submitting to the Voice Clone controller.';
    preview.innerHTML = '<span>Working…</span>';

    try {
      const response = await fetch('/api/media/voice-clone', {
        method: 'POST',
        body: formData
      });

      const text = await response.text();

      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { message: text };
      }

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP ${response.status}`);
      }

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
})();
''', encoding="utf-8")

css = VOICE_CSS.read_text(encoding="utf-8")

css = re.sub(
    r"\n/\* VOICE_CLIENT_V2_PATCH_START \*/[\s\S]*?/\* VOICE_CLIENT_V2_PATCH_END \*/\n?",
    "\n",
    css,
)

css += r'''

/* VOICE_CLIENT_V2_PATCH_START */
[hidden],
.voice-source-panel[hidden] {
  display: none !important;
}

.voice-client-grid {
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
}

.voice-source-section,
.recorder-card,
.upload-drop-lite {
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
  border-radius: 1rem;
  background: var(--surface-muted, #f8fafc);
}

.voice-source-section {
  padding: 1rem;
  display: grid;
  gap: 0.9rem;
}

.voice-source-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.6rem;
}

.voice-source-tab {
  min-height: 2.75rem;
  border-radius: 999px;
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
  background: var(--surface, #fff);
  color: var(--text, #111827);
  font-weight: 850;
  cursor: pointer;
}

.voice-source-tab.active {
  border-color: transparent;
  background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6));
  color: #06130f;
}

.voice-source-panel {
  display: grid;
  gap: 0.75rem;
}

.upload-drop-lite,
.recorder-card {
  padding: 1rem;
  display: grid;
  gap: 0.75rem;
}

.muted-line {
  color: var(--muted, #667085);
  line-height: 1.45;
  margin: 0;
}

.recorder-actions,
.preview-voice-toolbar {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
}

.recorder-card audio,
.voice-result-preview audio {
  width: 100%;
}

.preview-voice-list {
  display: grid;
  gap: 0.55rem;
}

.preview-voice-row {
  display: grid;
  grid-template-columns: 2.4rem minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.65rem;
  padding: 0.65rem;
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
  border-radius: 999px;
  background: var(--surface-muted, #f8fafc);
}

.preview-voice-row.selected {
  outline: 3px solid color-mix(in srgb, var(--brand, #13b981) 35%, transparent);
  border-color: color-mix(in srgb, var(--brand, #13b981) 50%, var(--line, rgba(15, 23, 42, 0.12)));
}

.voice-preview-play,
.voice-preview-name,
.voice-preview-use {
  border: 0;
  cursor: pointer;
  font-weight: 850;
}

.voice-preview-play {
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6));
  color: #06130f;
}

.voice-preview-play.playing {
  background: var(--surface, #fff);
  color: var(--text, #111827);
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
}

.voice-preview-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  white-space: nowrap;
  background: transparent;
  color: var(--text, #111827);
}

.voice-preview-use {
  border-radius: 999px;
  padding: 0.55rem 0.85rem;
  background: var(--surface, #fff);
  color: var(--text, #111827);
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
}

.preview-voice-row.selected .voice-preview-use {
  background: color-mix(in srgb, var(--brand, #13b981) 14%, var(--surface, #fff));
}

.asset-lite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.8rem;
}

.asset-lite-button {
  min-height: 2.55rem;
  border-radius: 999px;
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
  background: var(--surface, #fff);
  color: var(--text, #111827);
  padding: 0.68rem 1rem;
  font-weight: 800;
  text-decoration: none;
  cursor: pointer;
}

.asset-lite-button.primary {
  border-color: transparent;
  background: linear-gradient(135deg, var(--brand, #13b981), var(--brand-2, #3b82f6));
  color: #06130f;
}

@media (max-width: 900px) {
  .voice-client-grid,
  .voice-source-tabs {
    grid-template-columns: 1fr;
  }

  .preview-voice-row {
    grid-template-columns: 2.4rem minmax(0, 1fr);
    border-radius: 1rem;
  }

  .voice-preview-use {
    grid-column: 1 / -1;
    width: 100%;
  }
}
/* VOICE_CLIENT_V2_PATCH_END */
'''

VOICE_CSS.write_text(css, encoding="utf-8")

controller = CONTROLLER.read_text(encoding="utf-8")

if "def voice_clone_client_previews():" not in controller:
    preview_function = r'''

def _client_display_voice_name(stem: str) -> str:
    cleaned = stem.replace("_", " ").replace("-", " ").strip()
    return cleaned.title() or stem


def voice_clone_client_previews():
    """Client-safe list of approved preview voices."""
    voices: list[dict[str, Any]] = []

    params = sorted(
        VOICE_PARAMS_DIR.glob("*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for param in params:
        preview_path = None

        for ext in ("wav", "mp3", "m4a", "ogg", "webm"):
            candidates = [
                VOICE_PREVIEWS_DIR / f"{param.stem}_preview.{ext}",
                VOICE_PREVIEWS_DIR / f"{param.stem}.{ext}",
            ]

            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    preview_path = candidate
                    break

            if preview_path:
                break

        voices.append({
            "voiceName": param.stem,
            "displayName": _client_display_voice_name(param.stem),
            "description": "Approved SyntaxMatrix narration voice",
            "previewUrl": _public_voice_url(preview_path) if preview_path else None,
        })

    return jsonify({"ok": True, "voices": voices})
'''

    if "\ndef register_voice_clone_routes(app):" in controller:
        controller = controller.replace(
            "\ndef register_voice_clone_routes(app):",
            preview_function + "\n\ndef register_voice_clone_routes(app):",
            1,
        )
    else:
        controller += preview_function

if '@app.route("/api/voice-clone/previews"' not in controller and "@app.route('/api/voice-clone/previews'" not in controller:
    route_block = r'''
    @app.route('/api/voice-clone/previews', methods=['GET'])
    def voice_clone_previews_api():
        return voice_clone_client_previews()

'''

    admin_marker = '    @app.route("/api/admin/voice-clone", methods=["GET"])'
    media_marker = '    @app.route("/media/voices/<path:filename>", methods=["GET"])'

    if admin_marker in controller:
        controller = controller.replace(admin_marker, route_block + admin_marker, 1)
    elif media_marker in controller:
        controller = controller.replace(media_marker, route_block + media_marker, 1)
    else:
        raise SystemExit("Could not insert /api/voice-clone/previews route. Check register_voice_clone_routes().")

CONTROLLER.write_text(controller, encoding="utf-8")
py_compile.compile(str(CONTROLLER), doraise=True)

for path in [INDEX, README]:
    if not path.exists():
        continue

    text = path.read_text(encoding="utf-8")
    text = text.replace("Alibaba Media Studio", "SyntaxMatrix Media Studio")
    text = text.replace("AlibabaMedia", "SyntaxMatrixMedia")
    text = text.replace("Alibaba", "provider")
    text = text.replace(">AM<", ">SM<")
    text = re.sub(
        r'\n\s*<a[^>]+href=["\']/admin/voice-clone["\'][\s\S]*?</a>\s*',
        "\n",
        text,
        flags=re.I,
    )
    path.write_text(text, encoding="utf-8")

print()
print("Voice Clone client v2 patch complete.")
print("Now restart Flask with: python app.py")
print("Open: http://127.0.0.1:5055/tasks/voice-clone")