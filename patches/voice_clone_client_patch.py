from pathlib import Path
import re
import py_compile
from datetime import datetime

ROOT = Path(".").resolve()
FRONTEND = ROOT / "frontend"
CLIENT_HTML = FRONTEND / "voice_clone_client.html"
CLIENT_JS = FRONTEND / "voice_clone_client.js"
VOICE_CSS = FRONTEND / "voice_clone.css"
INDEX = FRONTEND / "index.html"
README = ROOT / "README.md"
CONTROLLER = ROOT / "controllers" / "voice_clone_controller.py"

required = [FRONTEND, CONTROLLER]
missing = [str(path) for path in required if not path.exists()]

if missing:
    print("ERROR: Run this from the project root. Missing:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")

for path in [CLIENT_HTML, CLIENT_JS, VOICE_CSS, INDEX, README, CONTROLLER]:
    if path.exists():
        backup = path.with_name(path.name + f".bak.voice-client-{stamp}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backup:", backup)

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
      <p>Generate narration from an uploaded voice sample, a browser recording, or an approved preview voice.</p>
    </header>

    <section class="feature-grid voice-client-grid">
      <form id="voiceCloneForm" class="feature-card voice-client-card" enctype="multipart/form-data">
        <div class="section-heading compact">
          <p class="eyebrow">Client workflow</p>
          <h2>Create narration</h2>
          <p>Choose a voice source, paste the narration script, then generate the audio.</p>
        </div>

        <input id="voiceName" name="voiceName" type="hidden" value="" />
        <input id="voiceModel" name="model" type="hidden" value="qwen3-tts-vc-2026-01-22" />

        <section class="voice-source-section">
          <p class="eyebrow">Voice source</p>
          <h3>Choose how the narration voice should be provided</h3>

          <div class="voice-source-tabs">
            <button class="voice-source-tab active" type="button" data-source-mode="upload">Upload audio</button>
            <button class="voice-source-tab" type="button" data-source-mode="record">Record my voice</button>
            <button class="voice-source-tab" type="button" data-source-mode="preview">Choose preview voice</button>
          </div>

          <div class="voice-source-panel" data-source-panel="upload">
            <label class="upload-drop-lite">
              <span>Upload a voice sample</span>
              <input id="voiceAudio" name="audio" type="file" accept="audio/*" />
              <small>Use a clean WAV, MP3, M4A, OGG or WEBM recording.</small>
            </label>
            <p id="uploadFileName" class="muted-line">No audio selected yet.</p>
          </div>

          <div class="voice-source-panel" data-source-panel="record" hidden>
            <div class="recorder-card">
              <strong id="recordingStatus">Recorder ready</strong>
              <span id="recordingHelp">Allow microphone access, record a clean sample, then use it for narration.</span>
              <div class="recorder-actions">
                <button class="secondary-button" id="startRecording" type="button">Start recording</button>
                <button class="secondary-button" id="stopRecording" type="button" disabled>Stop</button>
                <button class="secondary-button" id="discardRecording" type="button" disabled>Discard</button>
              </div>
              <audio id="recordedPreview" controls hidden></audio>
            </div>
          </div>

          <div class="voice-source-panel" data-source-panel="preview" hidden>
            <div class="preview-voice-toolbar">
              <p class="muted-line">Listen to an approved voice and choose one for this narration.</p>
              <button class="secondary-button" id="refreshPreviewVoices" type="button">Refresh voices</button>
            </div>
            <div id="previewVoiceList" class="preview-voice-list">Loading preview voices…</div>
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
          <p id="voiceResultStatus">Choose a voice source and submit your narration script.</p>
        </div>
        <div id="voiceResultPreview" class="voice-result-preview"></div>
        <dl id="voiceResultMeta" class="result-meta"></dl>
      </aside>
    </section>
  </main>

  <div class="toast-region" id="toastRegion" aria-live="polite" aria-atomic="true"></div>
  <script src="/voice_clone_client.js" defer></script>
</body>
</html>
''', encoding="utf-8")

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
  let mediaStream = null;
  let mediaRecorder = null;
  let recordedChunks = [];
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
    tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.sourceMode === mode));
    panels.forEach(panel => { panel.hidden = panel.dataset.sourcePanel !== mode; });
    if (mode === 'upload') voiceNameInput.value = makeClientVoiceName('client_upload');
    if (mode === 'record') voiceNameInput.value = makeClientVoiceName('client_recording');
    if (mode === 'preview') loadPreviewVoices();
  }

  async function loadPreviewVoices() {
    previewVoiceList.innerHTML = 'Loading preview voices…';

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
        <article class="preview-voice-card ${selectedPreviewVoice?.voiceName === voice.voiceName ? 'selected' : ''}">
          <div class="preview-voice-copy">
            <strong>${escapeHtml(voice.displayName || voice.voiceName)}</strong>
            <span>${escapeHtml(voice.description || 'Approved SyntaxMatrix narration voice')}</span>
          </div>
          ${voice.previewUrl ? `<audio src="${escapeHtml(voice.previewUrl)}" controls preload="none"></audio>` : '<span class="muted-line">No preview audio</span>'}
          <button class="secondary-button choose-preview-voice" type="button" data-voice-index="${index}">
            ${selectedPreviewVoice?.voiceName === voice.voiceName ? 'Selected' : 'Choose this voice'}
          </button>
        </article>
      `).join('');

      previewVoiceList.querySelectorAll('.choose-preview-voice').forEach(button => {
        button.addEventListener('click', () => {
          selectedPreviewVoice = voices[Number(button.dataset.voiceIndex)];
          if (!selectedPreviewVoice) return;
          voiceNameInput.value = selectedPreviewVoice.voiceName;
          toast('Preview voice selected', selectedPreviewVoice.displayName || selectedPreviewVoice.voiceName);
          loadPreviewVoices();
        });
      });
    } catch (error) {
      previewVoiceList.innerHTML = `<p class="muted-line">Could not load preview voices: ${escapeHtml(error.message || error)}</p>`;
      console.error(error);
    }
  }

  function recorderMimeType() {
    const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
    return options.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
  }

  async function startRecording() {
    try {
      recordedBlob = null;
      recordedChunks = [];

      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = recorderMimeType();
      mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);

      mediaRecorder.addEventListener('dataavailable', event => {
        if (event.data && event.data.size) recordedChunks.push(event.data);
      });

      mediaRecorder.addEventListener('stop', () => {
        recordedBlob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        const ext = recordedBlob.type.includes('ogg') ? 'ogg' : 'webm';
        recordedFileName = `${makeClientVoiceName('client_recording')}.${ext}`;

        recordedPreview.src = URL.createObjectURL(recordedBlob);
        recordedPreview.hidden = false;

        voiceNameInput.value = recordedFileName.replace(/\.[^.]+$/, '');
        recordingStatus.textContent = 'Recording ready';
        recordingHelp.textContent = 'This recording will be used as the source voice.';
        discardRecordingButton.disabled = false;

        mediaStream?.getTracks().forEach(track => track.stop());
      });

      mediaRecorder.start();

      startRecordingButton.disabled = true;
      stopRecordingButton.disabled = false;
      discardRecordingButton.disabled = true;
      recordingStatus.textContent = 'Recording…';
      recordingHelp.textContent = 'Speak clearly. Click Stop when ready.';
    } catch (error) {
      toast('Recorder unavailable', error.message || 'Could not access microphone.');
      console.error(error);
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
  }

  function discardRecording() {
    recordedBlob = null;
    recordedChunks = [];
    recordedFileName = '';

    if (recordedPreview.src) URL.revokeObjectURL(recordedPreview.src);

    recordedPreview.removeAttribute('src');
    recordedPreview.hidden = true;
    discardRecordingButton.disabled = true;
    recordingStatus.textContent = 'Recorder ready';
    recordingHelp.textContent = 'Record a new voice sample before generating narration.';
    voiceNameInput.value = makeClientVoiceName('client_recording');
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

    if (sourceMode === 'upload') {
      const file = voiceAudioInput.files?.[0];

      if (!file) {
        toast('Voice sample required', 'Upload audio, record your voice, or choose a preview voice.');
        return null;
      }

      formData.append('voiceName', voiceNameInput.value || makeClientVoiceName('client_upload'));
      formData.append('audio', file, file.name);
    }

    if (sourceMode === 'record') {
      if (!recordedBlob) {
        toast('Recording required', 'Record your voice first.');
        return null;
      }

      formData.append('voiceName', voiceNameInput.value || makeClientVoiceName('client_recording'));
      formData.append('audio', recordedBlob, recordedFileName || 'client_recording.webm');
    }

    if (sourceMode === 'preview') {
      if (!selectedPreviewVoice) {
        toast('Preview voice required', 'Choose one preview voice.');
        return null;
      }

      formData.append('voiceName', selectedPreviewVoice.voiceName);
      formData.append('selectedPreviewVoice', selectedPreviewVoice.voiceName);
    }

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

  tabs.forEach(tab => tab.addEventListener('click', () => setSourceMode(tab.dataset.sourceMode)));
  refreshPreviewVoices?.addEventListener('click', loadPreviewVoices);

  voiceAudioInput?.addEventListener('change', () => {
    const file = voiceAudioInput.files?.[0];
    uploadFileName.textContent = file ? `${file.name} is ready.` : 'No audio selected yet.';
    if (file) voiceNameInput.value = file.name.replace(/\.[^.]+$/, '');
  });

  startRecordingButton?.addEventListener('click', startRecording);
  stopRecordingButton?.addEventListener('click', stopRecording);
  discardRecordingButton?.addEventListener('click', discardRecording);

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

if not VOICE_CSS.exists():
    VOICE_CSS.write_text("", encoding="utf-8")

css = VOICE_CSS.read_text(encoding="utf-8")
css = re.sub(
    r"\n/\* VOICE_CLIENT_PUBLIC_PATCH_START \*/[\s\S]*?/\* VOICE_CLIENT_PUBLIC_PATCH_END \*/\n?",
    "\n",
    css,
)

css += r'''

/* VOICE_CLIENT_PUBLIC_PATCH_START */
.voice-client-grid { grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr); }

.voice-source-section,
.recorder-card,
.preview-voice-card,
.upload-drop-lite {
  border: 1px solid var(--line, rgba(15, 23, 42, 0.12));
  border-radius: 1rem;
  background: var(--surface-muted, #f8fafc);
}

.voice-source-section { padding: 1rem; display: grid; gap: 0.9rem; }
.voice-source-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }

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

.voice-source-panel { display: grid; gap: 0.75rem; }
.upload-drop-lite, .recorder-card, .preview-voice-card { padding: 1rem; display: grid; gap: 0.75rem; }
.muted-line { color: var(--muted, #667085); line-height: 1.45; margin: 0; }

.recorder-actions,
.preview-voice-toolbar {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
}

.recorder-card audio,
.preview-voice-card audio,
.voice-result-preview audio { width: 100%; }

.preview-voice-list { display: grid; gap: 0.75rem; }
.preview-voice-card.selected { outline: 3px solid color-mix(in srgb, var(--brand, #13b981) 35%, transparent); }
.preview-voice-copy { display: grid; gap: 0.2rem; }
.preview-voice-copy span { color: var(--muted, #667085); font-size: 0.9rem; }

.asset-lite-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.8rem; }

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
  .voice-source-tabs { grid-template-columns: 1fr; }
}
/* VOICE_CLIENT_PUBLIC_PATCH_END */
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
print("Voice Clone client patch complete.")
print("Now restart Flask with: python app.py")
print("Open: http://127.0.0.1:5055/tasks/voice-clone")