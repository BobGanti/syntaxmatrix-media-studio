from pathlib import Path
from datetime import datetime

ROOT = Path(".").resolve()
HTML = ROOT / "frontend" / "clone_voice_debug_print.html"

if not HTML.exists():
    print("ERROR: frontend/clone_voice_debug_print.html not found.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
backup = HTML.with_name(HTML.name + f".bak.clean-rebuild-{stamp}")
backup.write_text(HTML.read_text(encoding="utf-8"), encoding="utf-8")
print("Backup:", backup)

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #071017;
      color: #e8f1f8;
      padding: 32px;
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }
    section, header {
      border: 1px solid #33414c;
      border-radius: 16px;
      padding: 20px;
      background: #111b24;
    }
    header p, .status {
      color: #a9bfd3;
      line-height: 1.55;
    }
    h1, h2, h3, p { margin-top: 0; }
    label {
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
      font-weight: 800;
    }
    input, textarea, button {
      font: inherit;
    }
    input[type="file"], textarea {
      width: 100%;
      border: 1px solid #465662;
      border-radius: 12px;
      padding: 12px;
      background: #202b35;
      color: #fff;
    }
    textarea {
      min-height: 190px;
      resize: vertical;
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 14px 22px;
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      color: #06130f;
      font-weight: 900;
      cursor: pointer;
    }
    button.secondary {
      background: #2c3741;
      color: #e8f1f8;
      border: 1px solid #465662;
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .tabs {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }
    .tab {
      background: #2c3741;
      color: #e8f1f8;
      border: 1px solid #465662;
      min-width: 180px;
    }
    .tab.active {
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      color: #06130f;
    }
    .panel[hidden], #systemVoiceList[hidden] {
      display: none !important;
    }
    .card {
      display: grid;
      gap: 14px;
      border: 1px solid #33414c;
      border-radius: 14px;
      padding: 16px;
      background: #202b35;
      margin-bottom: 16px;
    }
    .row-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .system-list {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }
    .system-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 12px;
      border: 1px solid #465662;
      border-radius: 999px;
      padding: 10px 12px 10px 18px;
      background: #101820;
    }
    .system-row.selected {
      outline: 3px solid rgba(158,232,220,.35);
    }
    .system-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 900;
      letter-spacing: .02em;
    }
    .system-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .icon-button {
      width: 58px;
      min-width: 58px;
      padding-left: 0;
      padding-right: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      line-height: 1;
    }
    audio {
      width: 100%;
      margin-top: 12px;
    }
    pre {
      white-space: pre-wrap;
      overflow: auto;
      max-height: 360px;
      background: #02070b;
      border: 1px solid #33414c;
      border-radius: 12px;
      padding: 16px;
    }
    .download-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .download-actions a {
      color: #06130f;
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      padding: 12px 18px;
      border-radius: 999px;
      font-weight: 900;
      text-decoration: none;
    }
    @media (max-width: 720px) {
      body { padding: 18px; }
      .tab { width: 100%; }
      .system-row { grid-template-columns: 1fr; border-radius: 16px; }
      .system-actions button { width: 100%; }
      .icon-button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p>SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p>
        Upload audio, record your voice, or use an existing system voice parameter.
      </p>
    </header>

    <section>
      <div class="tabs">
        <button class="tab active" id="uploadTab" type="button">Upload audio</button>
        <button class="tab" id="recordTab" type="button">Record my voice</button>
        <button class="tab" id="systemTab" type="button">System voice</button>
      </div>

      <form id="cloneVoiceForm">
        <div class="panel" id="uploadPanel">
          <label>
            Upload audio file
            <input id="audioInput" name="audio" type="file" accept="audio/*">
          </label>
          <p class="status" id="uploadStatus">No uploaded file selected.</p>
        </div>

        <div class="panel" id="recordPanel" hidden>
          <div class="card">
            <h3 id="recordingTitle">Recorder ready</h3>
            <p class="status" id="recordingStatus">
              Click Start recording, speak clearly, then click Stop. The recording will be sent as a WAV file.
            </p>
            <div class="row-actions">
              <button class="secondary" id="startRecording" type="button">Start recording</button>
              <button class="secondary" id="stopRecording" type="button" disabled>Stop recording</button>
              <button class="secondary" id="discardRecording" type="button" disabled>Discard recording</button>
            </div>
            <audio id="recordedPreview" controls hidden></audio>
          </div>
        </div>

        <div class="panel" id="systemPanel" hidden>
          <div class="card">
            <h3>System voices</h3>
            <p class="status">
              Reusable system voice parameter files are loaded from:
              <br>workspaces/system/voice_params/
            </p>

            <button class="secondary" id="toggleSystemVoices" type="button">Show system voices</button>

            <div id="systemVoiceList" class="system-list" hidden></div>
          </div>
        </div>

        <label>
          Narration text
          <textarea id="promptInput" name="prompt" required placeholder="Paste narration text here"></textarea>
        </label>

        <button id="submitBtn" type="submit">Generate narration</button>
      </form>
    </section>

    <section>
      <h2 id="resultTitle">No narration yet</h2>
      <div id="audioResult"></div>
      <pre id="resultBox">No request sent yet.</pre>
    </section>
  </main>

  <script>
    const uploadTab = document.querySelector("#uploadTab");
    const recordTab = document.querySelector("#recordTab");
    const systemTab = document.querySelector("#systemTab");

    const uploadPanel = document.querySelector("#uploadPanel");
    const recordPanel = document.querySelector("#recordPanel");
    const systemPanel = document.querySelector("#systemPanel");

    const form = document.querySelector("#cloneVoiceForm");
    const audioInput = document.querySelector("#audioInput");
    const uploadStatus = document.querySelector("#uploadStatus");
    const promptInput = document.querySelector("#promptInput");
    const submitBtn = document.querySelector("#submitBtn");

    const startRecordingBtn = document.querySelector("#startRecording");
    const stopRecordingBtn = document.querySelector("#stopRecording");
    const discardRecordingBtn = document.querySelector("#discardRecording");
    const recordingTitle = document.querySelector("#recordingTitle");
    const recordingStatus = document.querySelector("#recordingStatus");
    const recordedPreview = document.querySelector("#recordedPreview");

    const toggleSystemVoices = document.querySelector("#toggleSystemVoices");
    const systemVoiceList = document.querySelector("#systemVoiceList");

    const resultTitle = document.querySelector("#resultTitle");
    const audioResult = document.querySelector("#audioResult");
    const resultBox = document.querySelector("#resultBox");

    let sourceMode = "upload";

    let systemVoices = [];
    let selectedSystemVoice = null;
    let systemVoicesLoaded = false;
    let previewAudio = null;
    let previewIndex = null;

    let audioContext = null;
    let micStream = null;
    let micSource = null;
    let recorderNode = null;
    let recordingBuffers = [];
    let recordingSampleRate = 44100;
    let recordedBlob = null;
    let recordedFilename = "";

    function setMode(mode) {
      sourceMode = mode;

      uploadTab.classList.toggle("active", mode === "upload");
      recordTab.classList.toggle("active", mode === "record");
      systemTab.classList.toggle("active", mode === "system");

      uploadPanel.hidden = mode !== "upload";
      recordPanel.hidden = mode !== "record";
      systemPanel.hidden = mode !== "system";

      console.log("[SyntaxMatrix Clone Voice] mode:", sourceMode);

      if (mode !== "system") {
        stopPreview();
      }
    }

    uploadTab.addEventListener("click", () => setMode("upload"));
    recordTab.addEventListener("click", () => setMode("record"));
    systemTab.addEventListener("click", () => setMode("system"));

    audioInput.addEventListener("change", () => {
      const file = audioInput.files[0] || null;
      uploadStatus.textContent = file ? `${file.name} is ready.` : "No uploaded file selected.";

      console.group("[SyntaxMatrix Clone Voice] upload file selected");
      console.log("field:", "audio");
      console.log("exists:", Boolean(file));
      if (file) {
        console.log("filename:", file.name);
        console.log("type:", file.type);
        console.log("size:", file.size);
      }
      console.groupEnd();
    });

    function stopPreview() {
      if (previewAudio) {
        previewAudio.pause();
        previewAudio.currentTime = 0;
      }

      previewAudio = null;
      previewIndex = null;

      document.querySelectorAll("[data-play-index]").forEach(button => {
        button.innerHTML = "▶";
        button.title = "Play preview";
        button.setAttribute("aria-label", "Play preview");
      });
    }

    function setSystemListOpen(open) {
      systemVoiceList.hidden = !open;
      toggleSystemVoices.textContent = open ? "Close system voices" : "Show system voices";

      if (!open) {
        stopPreview();
      }
    }

    function renderSystemVoices() {
      if (!systemVoices.length) {
        systemVoiceList.innerHTML = `
          <p class="status">
            No system voices found.
            Add .txt files to workspaces/system/voice_params/
          </p>
        `;
        return;
      }

      systemVoiceList.innerHTML = systemVoices.map((voice, index) => {
        const selected = selectedSystemVoice && selectedSystemVoice.voiceId === voice.voiceId;
        const name = voice.displayName || voice.voiceId;

        return `
          <div class="system-row ${selected ? "selected" : ""}">
            <div class="system-name">${name}</div>
            <div class="system-actions">
              ${voice.previewUrl ? `<button class="secondary icon-button" type="button" data-play-index="${index}" title="Play preview" aria-label="Play preview">▶</button>` : ""}
              <button type="button" data-use-index="${index}">${selected ? "Selected" : "Use"}</button>
            </div>
          </div>
        `;
      }).join("");
    }

    async function loadSystemVoices() {
      setSystemListOpen(true);
      systemVoiceList.innerHTML = `<p class="status">Loading system voices...</p>`;

      try {
        const response = await fetch("/api/clone-voice/system-voices?t=" + Date.now(), {
          cache: "no-store"
        });

        const data = await response.json();

        console.log("[SyntaxMatrix Clone Voice] system voices response:", data);

        if (!response.ok || !data.ok) {
          throw new Error(data.message || data.error || "Could not load system voices");
        }

        systemVoices = Array.isArray(data.voices) ? data.voices : [];
        systemVoicesLoaded = true;

        renderSystemVoices();
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] system voices failed:", error);
        systemVoiceList.innerHTML = `<p class="status">${error.message || String(error)}</p>`;
      }
    }

    toggleSystemVoices.addEventListener("click", async () => {
      if (!systemVoiceList.hidden) {
        setSystemListOpen(false);
        return;
      }

      if (!systemVoicesLoaded) {
        await loadSystemVoices();
        return;
      }

      setSystemListOpen(true);
      renderSystemVoices();
    });

    systemVoiceList.addEventListener("click", async event => {
      const playButton = event.target.closest("[data-play-index]");
      const useButton = event.target.closest("[data-use-index]");

      if (playButton) {
        const index = Number(playButton.dataset.playIndex);
        const voice = systemVoices[index];

        if (!voice || !voice.previewUrl) return;

        if (previewIndex === index && previewAudio && !previewAudio.paused) {
          stopPreview();
          return;
        }

        stopPreview();

        previewIndex = index;
        previewAudio = new Audio(voice.previewUrl);

        playButton.innerHTML = "■";
        playButton.title = "Stop preview";
        playButton.setAttribute("aria-label", "Stop preview");

        previewAudio.addEventListener("ended", stopPreview);
        previewAudio.addEventListener("error", stopPreview);

        try {
          await previewAudio.play();
        } catch (error) {
          console.error("[SyntaxMatrix Clone Voice] preview failed:", error);
          stopPreview();
        }

        return;
      }

      if (useButton) {
        const index = Number(useButton.dataset.useIndex);
        selectedSystemVoice = systemVoices[index] || null;

        console.log("[SyntaxMatrix Clone Voice] selected system voice:", selectedSystemVoice);

        renderSystemVoices();
      }
    });

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

      writeString(view, 0, "RIFF");
      view.setUint32(4, 36 + dataLength, true);
      writeString(view, 8, "WAVE");
      writeString(view, 12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, channelCount, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * channelCount * bytesPerSample, true);
      view.setUint16(32, channelCount * bytesPerSample, true);
      view.setUint16(34, 16, true);
      writeString(view, 36, "data");
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

        startRecordingBtn.disabled = true;
        stopRecordingBtn.disabled = false;
        discardRecordingBtn.disabled = true;

        recordingTitle.textContent = "Recording...";
        recordingStatus.textContent = "Speak clearly. Click Stop recording when done.";
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] recorder failed:", error);
        alert(error.message || "Could not access microphone.");
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

        if (!merged.length) {
          throw new Error("No recorded audio was captured.");
        }

        const wavBuffer = encodeWav(merged, recordingSampleRate);
        recordedBlob = new Blob([wavBuffer], { type: "audio/wav" });
        recordedFilename = `recorded_voice_${Date.now()}.wav`;

        recordedPreview.src = URL.createObjectURL(recordedBlob);
        recordedPreview.hidden = false;

        startRecordingBtn.disabled = false;
        stopRecordingBtn.disabled = true;
        discardRecordingBtn.disabled = false;

        recordingTitle.textContent = "Recording ready";
        recordingStatus.textContent = `${recordedFilename} is ready.`;
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] stop recording failed:", error);
        alert(error.message || "Could not finish recording.");
      }
    }

    function discardRecording() {
      recordedBlob = null;
      recordedFilename = "";
      recordingBuffers = [];

      if (recordedPreview.src) {
        URL.revokeObjectURL(recordedPreview.src);
      }

      recordedPreview.removeAttribute("src");
      recordedPreview.hidden = true;

      startRecordingBtn.disabled = false;
      stopRecordingBtn.disabled = true;
      discardRecordingBtn.disabled = true;

      recordingTitle.textContent = "Recorder ready";
      recordingStatus.textContent = "Click Start recording, speak clearly, then click Stop.";
    }

    startRecordingBtn.addEventListener("click", startRecording);
    stopRecordingBtn.addEventListener("click", stopRecording);
    discardRecordingBtn.addEventListener("click", discardRecording);

    async function submitUploadOrRecord(prompt) {
      let fileOrBlob = null;
      let filename = "";

      if (sourceMode === "upload") {
        fileOrBlob = audioInput.files[0] || null;
        filename = fileOrBlob ? fileOrBlob.name : "";
      }

      if (sourceMode === "record") {
        fileOrBlob = recordedBlob;
        filename = recordedFilename || `recorded_voice_${Date.now()}.wav`;
      }

      if (!fileOrBlob) {
        alert(sourceMode === "record" ? "Record your voice first." : "Choose an audio file first.");
        return null;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("audio", fileOrBlob, filename);
      formData.append("workspaceId", "mock_user_001");
      formData.append("sourceMode", sourceMode);

      return fetch("/api/clone-voice/create-and-generate", {
        method: "POST",
        body: formData
      });
    }

    async function submitSystem(prompt) {
      if (!selectedSystemVoice) {
        alert("Choose a system voice first.");
        return null;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("voiceId", selectedSystemVoice.voiceId);
      formData.append("workspaceId", "mock_user_001");

      return fetch("/api/clone-voice/generate-system", {
        method: "POST",
        body: formData
      });
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();

      const prompt = promptInput.value.trim();

      if (!prompt) {
        alert("Paste narration text first.");
        return;
      }

      submitBtn.disabled = true;
      submitBtn.textContent = "Generating...";
      resultTitle.textContent = "Generating narration";
      audioResult.innerHTML = "";
      resultBox.textContent = "Working... Check Flask terminal for logs.";

      try {
        const response = sourceMode === "system"
          ? await submitSystem(prompt)
          : await submitUploadOrRecord(prompt);

        if (!response) return;

        const text = await response.text();
        let data;

        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { raw: text };
        }

        console.log("[SyntaxMatrix Clone Voice] backend response:", data);
        resultBox.textContent = JSON.stringify(data, null, 2);

        if (!response.ok || !data.ok) {
          throw new Error(data.message || data.error || "HTTP " + response.status);
        }

        resultTitle.textContent = "Narration ready";

        const url = data.assetUrl || data.audioUrl;

        if (url) {
          audioResult.innerHTML = `
            <audio src="${url}" controls></audio>
            <div class="download-actions">
              <a href="${url}" download>Download</a>
            </div>
          `;
        }
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] generation failed:", error);
        resultTitle.textContent = "Narration failed";
        resultBox.textContent = error.message || String(error);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate narration";
      }
    });

    setMode("upload");

    console.log("[SyntaxMatrix Clone Voice] clean page loaded");
  </script>
</body>
</html>
''', encoding="utf-8")

print()
print("Clean Clone Voice page rebuilt.")
print("This removed the broken injected scripts from the page.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open with cache-bust:")
print("  http://127.0.0.1:5055/tasks/clone-voice?clean-rebuild=1")
