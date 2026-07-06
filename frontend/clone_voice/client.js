(() => {
  const $ = (selector) => document.querySelector(selector);

  const tabs = [...document.querySelectorAll(".tab[data-mode]")];
  const panels = {
    upload: $("#uploadPanel"),
    record: $("#recordPanel"),
    system: $("#systemPanel"),
  };

  const form = $("#cloneVoiceForm");
  const audioInput = $("#audioInput");
  const uploadStatus = $("#uploadStatus");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const startRecordingBtn = $("#startRecording");
  const stopRecordingBtn = $("#stopRecording");
  const discardRecordingBtn = $("#discardRecording");
  const recordingTitle = $("#recordingTitle");
  const recordingStatus = $("#recordingStatus");
  const recordedPreview = $("#recordedPreview");

  const toggleSystemVoicesBtn = $("#toggleSystemVoices");
  const systemVoiceList = $("#systemVoiceList");

  const resultTitle = $("#resultTitle");
  const audioResult = $("#audioResult");
  const resultBox = $("#resultBox");

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
    tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.mode === mode));
    Object.entries(panels).forEach(([key, panel]) => { panel.hidden = key !== mode; });
    if (mode !== "system") stopPreview();
    console.log("[Clone Voice] sourceMode:", sourceMode);
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));

  audioInput.addEventListener("change", () => {
    const file = audioInput.files[0] || null;
    uploadStatus.textContent = file ? `${file.name} is ready.` : "No uploaded file selected.";
    console.log("[Clone Voice] upload selected:", file ? { name: file.name, type: file.type, size: file.size } : null);
  });

  function stopPreview() {
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.currentTime = 0;
    }
    previewAudio = null;
    previewIndex = null;
    document.querySelectorAll("[data-play-index]").forEach((button) => {
      button.textContent = "▶";
      button.title = "Play preview";
      button.setAttribute("aria-label", "Play preview");
    });
  }

  function setSystemListOpen(open) {
    systemVoiceList.hidden = !open;
    toggleSystemVoicesBtn.textContent = open ? "Close system voices" : "Show system voices";
    if (!open) stopPreview();
  }

  function renderSystemVoices() {
    if (!systemVoices.length) {
      systemVoiceList.innerHTML = `<p class="status">No system voices found. Add .txt files to voices/params/.</p>`;
      return;
    }

    systemVoiceList.innerHTML = systemVoices.map((voice, index) => {
      const selected = selectedSystemVoice && selectedSystemVoice.voiceId === voice.voiceId;
      const name = voice.displayName || voice.voiceId;
      return `
        <div class="system-row ${selected ? "selected" : ""}">
          <div class="system-name">${escapeHtml(name)}</div>
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
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();
      console.log("[Clone Voice] system voices response:", data);
      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not load system voices");
      systemVoices = Array.isArray(data.voices) ? data.voices : [];
      systemVoicesLoaded = true;
      renderSystemVoices();
    } catch (error) {
      console.error("[Clone Voice] system voices failed:", error);
      systemVoiceList.innerHTML = `<p class="status">${escapeHtml(error.message || String(error))}</p>`;
    }
  }

  toggleSystemVoicesBtn.addEventListener("click", async () => {
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

  systemVoiceList.addEventListener("click", async (event) => {
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
      playButton.textContent = "■";
      playButton.title = "Stop preview";
      playButton.setAttribute("aria-label", "Stop preview");
      previewAudio.addEventListener("ended", stopPreview);
      previewAudio.addEventListener("error", stopPreview);

      try { await previewAudio.play(); }
      catch (error) { console.error("[Clone Voice] preview failed:", error); stopPreview(); }
      return;
    }

    if (useButton) {
      const index = Number(useButton.dataset.useIndex);
      selectedSystemVoice = systemVoices[index] || null;
      console.log("[Clone Voice] selected system voice:", selectedSystemVoice);
      renderSystemVoices();
    }
  });

  function flattenBuffers(buffers) {
    const totalLength = buffers.reduce((sum, buffer) => sum + buffer.length, 0);
    const result = new Float32Array(totalLength);
    let offset = 0;
    buffers.forEach((buffer) => { result.set(buffer, offset); offset += buffer.length; });
    return result;
  }

  function writeString(view, offset, value) {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
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
      recorderNode.onaudioprocess = (event) => recordingBuffers.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      micSource.connect(recorderNode);
      recorderNode.connect(audioContext.destination);
      startRecordingBtn.disabled = true;
      stopRecordingBtn.disabled = false;
      discardRecordingBtn.disabled = true;
      recordingTitle.textContent = "Recording...";
      recordingStatus.textContent = "Speak clearly. Click Stop recording when done.";
    } catch (error) {
      console.error("[Clone Voice] recorder failed:", error);
      alert(error.message || "Could not access microphone.");
    }
  }

  async function stopRecording() {
    try {
      if (recorderNode) { recorderNode.disconnect(); recorderNode.onaudioprocess = null; }
      if (micSource) micSource.disconnect();
      if (micStream) micStream.getTracks().forEach((track) => track.stop());
      if (audioContext) await audioContext.close();
      const merged = flattenBuffers(recordingBuffers);
      if (!merged.length) throw new Error("No recorded audio was captured.");
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
      console.error("[Clone Voice] stop recording failed:", error);
      alert(error.message || "Could not finish recording.");
    }
  }

  function discardRecording() {
    recordedBlob = null;
    recordedFilename = "";
    recordingBuffers = [];
    if (recordedPreview.src) URL.revokeObjectURL(recordedPreview.src);
    recordedPreview.removeAttribute("src");
    recordedPreview.hidden = true;
    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
    discardRecordingBtn.disabled = true;
    recordingTitle.textContent = "Recorder ready";
    recordingStatus.textContent = "Start recording, speak clearly, then stop.";
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
    } else {
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
    return fetch("/api/clone-voice/from-source", { method: "POST", body: formData });
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
    return fetch("/api/clone-voice/from-system", { method: "POST", body: formData });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt) { alert("Paste narration text first."); return; }
    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";
    resultTitle.textContent = "Generating narration";
    audioResult.innerHTML = "";
    resultBox.textContent = "Working... Check Flask terminal for logs.";
    try {
      const response = sourceMode === "system" ? await submitSystem(prompt) : await submitUploadOrRecord(prompt);
      if (!response) return;
      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
      console.log("[Clone Voice] backend response:", data);
      resultBox.textContent = JSON.stringify(data, null, 2);
      if (!response.ok || !data.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
      resultTitle.textContent = "Narration ready";
      const url = data.assetUrl || data.audioUrl;
      if (url) {
        audioResult.innerHTML = `<audio src="${url}" controls></audio><div class="download-actions"><a href="${url}" download>Download</a></div>`;
      }
    } catch (error) {
      console.error("[Clone Voice] generation failed:", error);
      resultTitle.textContent = "Narration failed";
      resultBox.textContent = error.message || String(error);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Generate narration";
    }
  });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
  }

  setMode("upload");
  console.log("[Clone Voice] clean client loaded");
})();
