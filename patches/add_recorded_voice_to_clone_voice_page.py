from pathlib import Path
from datetime import datetime

ROOT = Path(".").resolve()
HTML = ROOT / "frontend" / "clone_voice_debug_print.html"

if not HTML.exists():
    print("ERROR: frontend/clone_voice_debug_print.html not found. Run from project root.")
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d%H%M%S")
backup = HTML.with_name(HTML.name + f".bak.record-voice-{stamp}")
backup.write_text(HTML.read_text(encoding="utf-8"), encoding="utf-8")
print("Backup:", backup)

HTML.write_text(r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SyntaxMatrix Clone Voice</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #071017;
      color: #e8f1f8;
      padding: 32px;
    }
    main {
      max-width: 920px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }
    section {
      border: 1px solid #33414c;
      border-radius: 16px;
      padding: 20px;
      background: #111b24;
    }
    label {
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
      font-weight: 700;
    }
    input, textarea, button {
      font: inherit;
    }
    input[type="file"], textarea {
      border: 1px solid #465662;
      border-radius: 10px;
      padding: 12px;
      background: #202b35;
      color: #fff;
    }
    textarea {
      min-height: 180px;
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
    .note {
      color: #9db2c5;
      line-height: 1.5;
    }
    .tabs {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }
    .tab {
      background: #2c3741;
      color: #e8f1f8;
      border: 1px solid #465662;
    }
    .tab.active {
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      color: #06130f;
    }
    .panel[hidden] {
      display: none !important;
    }
    .record-card {
      display: grid;
      gap: 14px;
      border: 1px solid #33414c;
      border-radius: 14px;
      padding: 16px;
      background: #202b35;
      margin-bottom: 16px;
    }
    .record-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .status {
      color: #9db2c5;
      line-height: 1.5;
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .actions a {
      color: #06130f;
      background: linear-gradient(135deg, #9ee8dc, #82a8ff);
      padding: 12px 18px;
      border-radius: 999px;
      font-weight: 900;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <p>SyntaxMatrix Media Studio</p>
      <h1>Clone Voice</h1>
      <p class="note">
        Upload an audio file or record your voice. The controller creates a private voice parameter, deletes the raw source audio, then generates narration.
      </p>
    </header>

    <section>
      <div class="tabs">
        <button class="tab active" id="uploadTab" type="button">Upload audio</button>
        <button class="tab" id="recordTab" type="button">Record my voice</button>
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
          <div class="record-card">
            <strong id="recordingTitle">Recorder ready</strong>
            <p class="status" id="recordingStatus">Click Start recording, speak clearly, then click Stop. The recording will be sent as a WAV file.</p>

            <div class="record-actions">
              <button class="secondary" id="startRecording" type="button">Start recording</button>
              <button class="secondary" id="stopRecording" type="button" disabled>Stop recording</button>
              <button class="secondary" id="discardRecording" type="button" disabled>Discard recording</button>
            </div>

            <audio id="recordedPreview" controls hidden></audio>
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
    const form = document.querySelector("#cloneVoiceForm");

    const uploadTab = document.querySelector("#uploadTab");
    const recordTab = document.querySelector("#recordTab");
    const uploadPanel = document.querySelector("#uploadPanel");
    const recordPanel = document.querySelector("#recordPanel");

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

    const resultTitle = document.querySelector("#resultTitle");
    const audioResult = document.querySelector("#audioResult");
    const resultBox = document.querySelector("#resultBox");

    let sourceMode = "upload";

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

      uploadPanel.hidden = mode !== "upload";
      recordPanel.hidden = mode !== "record";

      console.log("[SyntaxMatrix Clone Voice] sourceMode:", sourceMode);
    }

    uploadTab.addEventListener("click", () => setMode("upload"));
    recordTab.addEventListener("click", () => setMode("record"));

    audioInput.addEventListener("change", () => {
      const file = audioInput.files[0] || null;

      uploadStatus.textContent = file
        ? `${file.name} is ready.`
        : "No uploaded file selected.";

      console.group("[SyntaxMatrix Clone Voice] UPLOAD FILE SELECTED");
      console.log("field name:", "audio");
      console.log("file exists:", Boolean(file));
      if (file) {
        console.log("filename:", file.name);
        console.log("type:", file.type);
        console.log("size:", file.size);
      }
      console.groupEnd();
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

        console.log("[SyntaxMatrix Clone Voice] recording started");
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
        recordingStatus.textContent = `${recordedFilename} is ready and will be sent as the audio file.`;

        console.group("[SyntaxMatrix Clone Voice] RECORDED WAV READY");
        console.log("field name:", "audio");
        console.log("filename:", recordedFilename);
        console.log("type:", recordedBlob.type);
        console.log("size:", recordedBlob.size);
        console.groupEnd();
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

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const prompt = promptInput.value.trim();

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

      console.group("[SyntaxMatrix Clone Voice] ABOUT TO SEND");
      console.log("endpoint:", "/api/clone-voice/create-and-generate");
      console.log("sourceMode:", sourceMode);
      console.log("prompt field:", "prompt");
      console.log("prompt length:", prompt.length);
      console.log("audio field:", "audio");
      console.log("file/blob exists:", Boolean(fileOrBlob));
      if (fileOrBlob) {
        console.log("filename:", filename);
        console.log("type:", fileOrBlob.type);
        console.log("size:", fileOrBlob.size);
      }
      console.groupEnd();

      if (!fileOrBlob) {
        alert(sourceMode === "record" ? "Record your voice first." : "Choose an audio file first.");
        return;
      }

      if (!prompt) {
        alert("Paste narration text first.");
        return;
      }

      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("audio", fileOrBlob, filename);
      formData.append("workspaceId", "mock_user_001");
      formData.append("sourceMode", sourceMode);

      submitBtn.disabled = true;
      submitBtn.textContent = "Generating...";
      resultTitle.textContent = "Generating narration";
      audioResult.innerHTML = "";
      resultBox.textContent = "Working... Check Flask terminal for upload and workspace logs.";

      try {
        const response = await fetch("/api/clone-voice/create-and-generate", {
          method: "POST",
          body: formData
        });

        const text = await response.text();
        let data;

        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { raw: text };
        }

        console.log("[SyntaxMatrix Clone Voice] BACKEND RESPONSE:", data);
        resultBox.textContent = JSON.stringify(data, null, 2);

        if (!response.ok || !data.ok) {
          throw new Error(data.message || data.error || "HTTP " + response.status);
        }

        resultTitle.textContent = "Narration ready";

        if (data.assetUrl || data.audioUrl) {
          const url = data.assetUrl || data.audioUrl;
          audioResult.innerHTML = `
            <audio src="${url}" controls></audio>
            <div class="actions">
              <a href="${url}" download>Download</a>
            </div>
          `;
        }
      } catch (error) {
        console.error("[SyntaxMatrix Clone Voice] REQUEST FAILED:", error);
        resultTitle.textContent = "Narration failed";
        resultBox.textContent = error.message || String(error);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate narration";
      }
    });

    setMode("upload");
  </script>
</body>
</html>
''', encoding="utf-8")

print()
print("Recorded voice support added to Clone Voice page.")
print("No backend/controller changes were made.")
print()
print("Restart Flask:")
print("  python app.py")
print()
print("Open:")
print("  http://127.0.0.1:5055/tasks/clone-voice?record=1")
