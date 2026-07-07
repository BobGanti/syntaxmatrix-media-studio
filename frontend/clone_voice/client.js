(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const form = $("#cloneVoiceForm");
  const workspaceSelect = $("#workspaceSelect");
  const workspaceStatus = $("#workspaceStatus");

  const sourceModeInputs = $$('input[name="sourceMode"]');

  const uploadPanel = $("#uploadPanel");
  const recordPanel = $("#recordPanel");
  const savedPanel = $("#savedPanel");
  const systemPanel = $("#systemPanel");
  const voiceCreatePanel = $("#voiceCreatePanel");

  const audioFile = $("#audioFile");
  const voiceDisplayName = $("#voiceDisplayName");
  const voiceGender = $("#voiceGender");
  const saveVoiceBtn = $("#saveVoiceBtn");

  const startRecordingBtn = $("#startRecordingBtn");
  const stopRecordingBtn = $("#stopRecordingBtn");
  const discardRecordingBtn = $("#discardRecordingBtn");
  const recordingStatus = $("#recordingStatus");
  const recordingTimer = $("#recordingTimer");

  const micMeter = $("#micMeter");
  const micMeterFill = $("#micMeterFill");
  const micMeterValue = $("#micMeterValue");

  const savedVoicesList = $("#savedVoicesList");
  const savedVoiceManagePanel = $("#savedVoiceManagePanel");
  const editSavedVoiceDisplayName = $("#editSavedVoiceDisplayName");
  const editSavedVoiceGender = $("#editSavedVoiceGender");
  const saveSavedVoiceMetaBtn = $("#saveSavedVoiceMetaBtn");
  const replaceSavedVoiceAudio = $("#replaceSavedVoiceAudio");
  const replaceSavedVoiceSourceBtn = $("#replaceSavedVoiceSourceBtn");
  const systemVoicesList = $("#systemVoicesList");
  const savedGenderFilter = $("#savedGenderFilter");
  const systemGenderFilter = $("#systemGenderFilter");
  const refreshSavedBtn = $("#refreshSavedBtn");
  const refreshSystemBtn = $("#refreshSystemBtn");

  const titleInput = $("#titleInput");
  const narrationSpeed = $("#narrationSpeed");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const audioPlayer = $("#audioPlayer");
  const downloadLink = $("#downloadLink");
  const resultBox = $("#resultBox");

  let activeWorkspaceId = "mock_user_001";
  let availableWorkspaces = [];

  let maxVoiceSourceSeconds = 20;

  let mediaRecorder = null;
  let micStream = null;
  let audioContext = null;
  let micSource = null;
  let recordedChunks = [];
  let recordedBlob = null;
  let recordedFilename = "";

  let recordingAutoStopTimer = null;
  let recordingTicker = null;
  let recordingStartedAt = 0;

  let micAnalyserNode = null;
  let micMeterData = null;
  let micMeterAnimationFrame = null;

  let savedVoices = [];
  let systemVoices = [];
  let pendingSelectSavedVoiceId = "";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function selectedMode() {
    return sourceModeInputs.find((input) => input.checked)?.value || "upload";
  }

  function setMode(mode) {
    uploadPanel.classList.toggle("hidden", mode !== "upload");
    recordPanel.classList.toggle("hidden", mode !== "record");
    savedPanel.classList.toggle("hidden", mode !== "saved");
    systemPanel.classList.toggle("hidden", mode !== "system");
    voiceCreatePanel.classList.toggle("hidden", !(mode === "upload" || mode === "record"));

    if (mode === "saved") loadSavedVoices();
    if (mode === "system") loadSystemVoices();
  }

  function setSelectedMode(mode) {
    const input = sourceModeInputs.find((item) => item.value === mode);
    if (input) input.checked = true;
    setMode(mode);
  }

  function fallbackWorkspaces() {
    return [
      { workspaceId: "mock_user_001", label: "Client A / Workspace 001" },
      { workspaceId: "mock_user_002", label: "Client B / Workspace 002" },
    ];
  }

  function setWorkspaceStatus() {
    const label = availableWorkspaces.find((row) => row.workspaceId === activeWorkspaceId)?.label || activeWorkspaceId;

    if (workspaceStatus) {
      workspaceStatus.textContent = `Active workspace: ${label}`;
    }
  }

  function renderWorkspaceOptions() {
    workspaceSelect.innerHTML = availableWorkspaces.map((row) => `
      <option value="${escapeHtml(row.workspaceId)}">${escapeHtml(row.label || row.workspaceId)}</option>
    `).join("");

    workspaceSelect.value = activeWorkspaceId;
  }

  async function loadWorkspaces() {
    try {
      const response = await fetch(`/api/clone-voice/workspaces?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load workspaces");
      }

      availableWorkspaces = data.workspaces && data.workspaces.length ? data.workspaces : fallbackWorkspaces();
      activeWorkspaceId = data.defaultWorkspaceId || availableWorkspaces[0].workspaceId || "mock_user_001";
    } catch (error) {
      console.warn("[Clone Voice] Could not load workspace list. Using fallback.", error);
      availableWorkspaces = fallbackWorkspaces();
      activeWorkspaceId = "mock_user_001";
    }

    renderWorkspaceOptions();
    setWorkspaceStatus();
    await loadSavedVoices();
  }

  async function switchWorkspace(workspaceId) {
    activeWorkspaceId = workspaceId || "mock_user_001";
    setWorkspaceStatus();

    savedVoices = [];
    savedVoicesList.textContent = `Loading saved voices for ${activeWorkspaceId}...`;

    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    resultBox.innerHTML = `
      <strong>Workspace switched.</strong>
      <div class="result-grid">
        <div class="result-row">
          <div class="result-label">Active workspace</div>
          <div class="result-value">${escapeHtml(activeWorkspaceId)}</div>
        </div>
        <div class="result-row">
          <div class="result-label">Isolation</div>
          <div class="result-value">Saved voices are now loaded only from this workspace.</div>
        </div>
      </div>
    `;

    await loadSavedVoices();
  }

  function filenameFromPath(value) {
    const text = String(value || "");
    if (!text) return "";
    const parts = text.split("/");
    return parts[parts.length - 1] || text;
  }

  function renderFriendlyResult(data) {
    const rows = [
      ["Narration", filenameFromPath(data.outputPath || data.assetUrl || data.audioUrl) || ""],
      ["Workspace", data.workspaceId || activeWorkspaceId],
      ["Title", data.narrationTitle || ""],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Source", data.sourceType || ""],
      ["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],
      ["Volume normalized", data.volumeNormalized ? "Yes" : ""],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Narration generated successfully.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Narration is generated only from a saved voice or a system voice.</div>
    `;
  }

  function renderVoiceSavedResult(data) {
    const rows = [
      ["Workspace", data.workspaceId || activeWorkspaceId],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Source", data.sourceType || ""],
      ["Max voice sample", data.maxVoiceSourceSeconds ? `${data.maxVoiceSourceSeconds} seconds` : ""],
      ["Parameter", data.parameterCreated ? "Created" : "Reused existing"],
      ["Preview", data.previewCreated ? "Created" : "Reused existing"],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Voice saved successfully.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Select this voice from My saved voices to generate narration.</div>
    `;
  }

  async function loadCloneVoiceSettings() {
    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (response.ok && data.ok && data.maxVoiceSourceSeconds) {
        maxVoiceSourceSeconds = Number(data.maxVoiceSourceSeconds) || 20;
      }
    } catch (error) {
      console.warn("[Clone Voice] Could not load settings:", error);
    }

    renderRecordingTimer(0);
    recordingStatus.textContent = `Start recording, speak clearly, then stop. Recording auto-stops at ${maxVoiceSourceSeconds} seconds.`;
  }

  function renderRecordingTimer(elapsedSeconds = 0) {
    const safeElapsed = Math.max(0, Number(elapsedSeconds) || 0);
    const safeMax = Math.max(1, Number(maxVoiceSourceSeconds || 20));
    recordingTimer.textContent = `${safeElapsed.toFixed(1)}s / ${safeMax}s`;
    recordingTimer.setAttribute("title", `${Math.max(0, safeMax - safeElapsed).toFixed(1)} seconds remaining`);
  }

  function clearRecordingTicker() {
    if (recordingTicker) {
      clearInterval(recordingTicker);
      recordingTicker = null;
    }
  }

  function startRecordingTicker() {
    clearRecordingTicker();
    recordingStartedAt = Date.now();
    renderRecordingTimer(0);

    recordingTicker = setInterval(() => {
      const elapsed = (Date.now() - recordingStartedAt) / 1000;
      renderRecordingTimer(Math.min(elapsed, maxVoiceSourceSeconds));
    }, 100);
  }

  function clearRecordingAutoStopTimer() {
    if (recordingAutoStopTimer) {
      clearTimeout(recordingAutoStopTimer);
      recordingAutoStopTimer = null;
    }
    clearRecordingTicker();
  }

  function startRecordingAutoStopTimer() {
    clearRecordingAutoStopTimer();
    startRecordingTicker();

    recordingAutoStopTimer = setTimeout(() => {
      if (!stopRecordingBtn.disabled) {
        stopRecording();
      }
    }, maxVoiceSourceSeconds * 1000);
  }

  function renderMicLevel(level) {
    const safeLevel = Math.max(0, Math.min(1, Number(level) || 0));
    const percent = Math.round(safeLevel * 100);

    micMeterFill.style.width = `${percent}%`;
    micMeter.classList.toggle("is-active", safeLevel > 0.08);
    micMeter.classList.toggle("is-loud", safeLevel > 0.72);

    if (safeLevel < 0.04) {
      micMeterValue.textContent = "silent";
    } else if (safeLevel < 0.18) {
      micMeterValue.textContent = "low";
    } else if (safeLevel < 0.72) {
      micMeterValue.textContent = "good";
    } else {
      micMeterValue.textContent = "loud";
    }
  }

  function stopMicMeter() {
    if (micMeterAnimationFrame) {
      cancelAnimationFrame(micMeterAnimationFrame);
      micMeterAnimationFrame = null;
    }

    try {
      if (micAnalyserNode) micAnalyserNode.disconnect();
    } catch {}

    micAnalyserNode = null;
    micMeterData = null;
    renderMicLevel(0);
  }

  function startMicMeter(sourceNode, ctx) {
    stopMicMeter();

    micAnalyserNode = ctx.createAnalyser();
    micAnalyserNode.fftSize = 2048;
    micAnalyserNode.smoothingTimeConstant = 0.82;
    micMeterData = new Uint8Array(micAnalyserNode.fftSize);

    sourceNode.connect(micAnalyserNode);

    const tick = () => {
      if (!micAnalyserNode || !micMeterData) {
        renderMicLevel(0);
        return;
      }

      micAnalyserNode.getByteTimeDomainData(micMeterData);

      let sumSquares = 0;

      for (let index = 0; index < micMeterData.length; index += 1) {
        const centered = (micMeterData[index] - 128) / 128;
        sumSquares += centered * centered;
      }

      const rms = Math.sqrt(sumSquares / micMeterData.length);
      renderMicLevel(Math.min(1, rms * 4.5));

      micMeterAnimationFrame = requestAnimationFrame(tick);
    };

    tick();
  }

  async function startRecording() {
    try {
      recordedChunks = [];
      recordedBlob = null;
      recordedFilename = "";

      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      micSource = audioContext.createMediaStreamSource(micStream);
      startMicMeter(micSource, audioContext);

      const options = MediaRecorder.isTypeSupported("audio/webm") ? { mimeType: "audio/webm" } : undefined;

      mediaRecorder = new MediaRecorder(micStream, options);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", () => {
        const mimeType = mediaRecorder.mimeType || "audio/webm";
        recordedBlob = new Blob(recordedChunks, { type: mimeType });
        recordedFilename = `recorded_voice_${Date.now()}.webm`;

        recordingStatus.textContent = `Recording ready. Click Save voice to create a reusable saved voice.`;
        discardRecordingBtn.disabled = false;
      });

      mediaRecorder.start();

      startRecordingBtn.disabled = true;
      stopRecordingBtn.disabled = false;
      discardRecordingBtn.disabled = true;
      recordingStatus.textContent = `Recording... auto-stops at ${maxVoiceSourceSeconds} seconds.`;

      startRecordingAutoStopTimer();
    } catch (error) {
      recordingStatus.textContent = error.message || String(error);
      stopMicMeter();
      clearRecordingAutoStopTimer();
    }
  }

  function stopRecording() {
    const elapsedBeforeStop = recordingStartedAt
      ? Math.min((Date.now() - recordingStartedAt) / 1000, maxVoiceSourceSeconds)
      : 0;

    clearRecordingAutoStopTimer();
    renderRecordingTimer(elapsedBeforeStop);
    stopMicMeter();

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    if (audioContext) {
      audioContext.close().catch(() => {});
    }

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
  }

  function discardRecording() {
    stopMicMeter();
    clearRecordingAutoStopTimer();

    recordedChunks = [];
    recordedBlob = null;
    recordedFilename = "";

    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }

    recordingStatus.textContent = "Start recording, speak clearly, then stop.";
    renderRecordingTimer(0);

    startRecordingBtn.disabled = false;
    stopRecordingBtn.disabled = true;
    discardRecordingBtn.disabled = true;
  }

  function filteredVoices(voices, genderFilter) {
    const filter = genderFilter || "";
    if (!filter) return voices;
    return voices.filter((voice) => String(voice.gender || "").toUpperCase() === filter);
  }

  function renderVoiceList(container, voices, groupName, genderFilter) {
    const rows = filteredVoices(voices, genderFilter);
    const isSavedVoiceList = groupName === "savedVoiceId";

    if (!rows.length) {
      container.innerHTML = `<p class="status">No voices found for this filter.</p>`;
      return;
    }

    container.innerHTML = rows.map((voice, index) => {
      const inputId = `${groupName}_${index}`;

      const previewButton = voice.previewUrl
        ? `<button class="icon-btn icon-btn-play" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}" aria-label="Play voice preview" title="Play preview">
             <span aria-hidden="true">▶</span>
           </button>`
        : `<span class="voice-card-empty"></span>`;

      const deleteButton = isSavedVoiceList
        ? `<button class="icon-btn icon-btn-delete" type="button" data-delete-saved-voice-id="${escapeHtml(voice.voiceId)}" data-delete-saved-voice-label="${escapeHtml(voice.label || voice.displayName || voice.voiceId)}" aria-label="Delete saved voice" title="Delete voice">
             <span aria-hidden="true">🗑</span>
           </button>`
        : "";

      return `
        <label class="voice-card" for="${escapeHtml(inputId)}">
          <input id="${escapeHtml(inputId)}" type="radio" name="${escapeHtml(groupName)}" value="${escapeHtml(voice.voiceId)}">
          <span>
            <span class="voice-card-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</span>
          </span>
          ${previewButton}
          ${deleteButton}
        </label>
      `;
    }).join("");

    if (pendingSelectSavedVoiceId && groupName === "savedVoiceId") {
      const input = container.querySelector(`input[value="${CSS.escape(pendingSelectSavedVoiceId)}"]`);
      if (input) {
        input.checked = true;
        pendingSelectSavedVoiceId = "";
      }
    }

    if (groupName === "savedVoiceId") updateSavedVoiceEditor();
  }

  async function loadSavedVoices() {
    savedVoicesList.textContent = `Loading saved voices for ${activeWorkspaceId}...`;

    try {
      const response = await fetch(`/api/clone-voice/my-voices?workspaceId=${encodeURIComponent(activeWorkspaceId)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load saved voices");
      }

      savedVoices = data.voices || [];
      renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
    } catch (error) {
      savedVoicesList.textContent = error.message || String(error);
    }
  }

  async function loadSystemVoices() {
    systemVoicesList.textContent = "Loading system voices...";

    try {
      const response = await fetch(`/api/clone-voice/system-voices?t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load system voices");
      }

      systemVoices = data.voices || [];
      renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
    } catch (error) {
      systemVoicesList.textContent = error.message || String(error);
    }
  }

  function selectedVoiceId(groupName) {
    return document.querySelector(`input[name="${groupName}"]:checked`)?.value || "";
  }

  async function playPreview(url) {
    if (!url) return;

    audioPlayer.classList.remove("hidden");
    audioPlayer.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    await audioPlayer.play().catch(() => {});
  }

  function requireSelectedGender() {
    const gender = voiceGender.value;

    if (gender !== "M" && gender !== "F") {
      alert("Choose voice gender: Male (M) or Female (F).");
      voiceGender.focus();
      return "";
    }

    return gender;
  }

  async function saveClientVoice() {
    const mode = selectedMode();

    if (mode !== "upload" && mode !== "record") {
      alert("Switch to Upload audio or Record voice to save a new voice.");
      return;
    }

    const selectedGender = requireSelectedGender();

    if (!selectedGender) {
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("sourceMode", mode);
    formData.append("voiceDisplayName", voiceDisplayName.value.trim());
    formData.append("gender", selectedGender);

    if (mode === "upload") {
      const file = audioFile.files[0];

      if (!file) {
        alert("Choose an audio file first.");
        return;
      }

      formData.append("audio", file, file.name);
    }

    if (mode === "record") {
      if (!recordedBlob) {
        alert("Record a voice first.");
        return;
      }

      formData.append("audio", recordedBlob, recordedFilename || "recorded_voice.webm");
    }

    saveVoiceBtn.disabled = true;
    saveVoiceBtn.textContent = "Saving voice...";
    resultBox.textContent = "Saving voice and generating standard preview...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      const response = await fetch("/api/clone-voice/voices/from-source", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log("[Clone Voice saved voice response]", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save voice");
      }

      renderVoiceSavedResult(data);

      if (data.voicePreviewUrl) {
        audioPlayer.src = `${data.voicePreviewUrl}${data.voicePreviewUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");
      }

      pendingSelectSavedVoiceId = data.voiceId || "";
      await loadSavedVoices();
      setSelectedMode("saved");
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      saveVoiceBtn.disabled = false;
      saveVoiceBtn.textContent = "Save voice";
    }
  }

  function selectedSavedVoice() {
    const voiceId = selectedVoiceId("savedVoiceId");
    if (!voiceId) return null;
    return savedVoices.find((voice) => voice.voiceId === voiceId) || null;
  }

  function updateSavedVoiceEditor() {
    if (!savedVoiceManagePanel) return;

    const voice = selectedSavedVoice();

    if (!voice) {
      savedVoiceManagePanel.classList.add("hidden");
      return;
    }

    savedVoiceManagePanel.classList.remove("hidden");
    editSavedVoiceDisplayName.value = voice.displayName || "";
    editSavedVoiceGender.value = voice.gender || "M";
    replaceSavedVoiceAudio.value = "";
  }

  async function saveSelectedSavedVoiceMetadata() {
    const voice = selectedSavedVoice();

    if (!voice) {
      alert("Choose a saved voice first.");
      return;
    }

    const displayName = editSavedVoiceDisplayName.value.trim();
    const gender = editSavedVoiceGender.value;

    if (!displayName) {
      alert("Enter a display name.");
      editSavedVoiceDisplayName.focus();
      return;
    }

    if (gender !== "M" && gender !== "F") {
      alert("Choose Male (M) or Female (F).");
      editSavedVoiceGender.focus();
      return;
    }

    saveSavedVoiceMetaBtn.disabled = true;
    saveSavedVoiceMetaBtn.textContent = "Saving...";
    resultBox.textContent = "Saving voice details...";

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voice.voiceId)}?workspaceId=${encodeURIComponent(activeWorkspaceId)}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            workspaceId: activeWorkspaceId,
            displayName,
            gender
          })
        }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not update voice details");
      }

      resultBox.innerHTML = `
        <strong>Saved voice updated.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(data.label || data.displayName || data.voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Parameter</div>
            <div class="result-value">Kept existing</div>
          </div>
          <div class="result-row">
            <div class="result-label">Preview</div>
            <div class="result-value">Kept existing</div>
          </div>
        </div>
      `;

      pendingSelectSavedVoiceId = data.voiceId || voice.voiceId;
      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      saveSavedVoiceMetaBtn.disabled = false;
      saveSavedVoiceMetaBtn.textContent = "Save details";
    }
  }

  async function replaceSelectedSavedVoiceSource() {
    const voice = selectedSavedVoice();

    if (!voice) {
      alert("Choose a saved voice first.");
      return;
    }

    const file = replaceSavedVoiceAudio.files[0];

    if (!file) {
      alert("Choose replacement audio first.");
      replaceSavedVoiceAudio.focus();
      return;
    }

    const displayName = editSavedVoiceDisplayName.value.trim() || voice.displayName || voice.voiceId;
    const gender = editSavedVoiceGender.value || voice.gender;

    if (gender !== "M" && gender !== "F") {
      alert("Choose Male (M) or Female (F).");
      editSavedVoiceGender.focus();
      return;
    }

    const ok = confirm(`Replace source for ${voice.label || voice.voiceId}? This rebuilds its parameter and preview.`);

    if (!ok) return;

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("displayName", displayName);
    formData.append("gender", gender);
    formData.append("audio", file, file.name);

    replaceSavedVoiceSourceBtn.disabled = true;
    replaceSavedVoiceSourceBtn.textContent = "Replacing...";
    resultBox.textContent = "Replacing voice source and rebuilding standard preview...";

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voice.voiceId)}/replace-source`,
        {
          method: "POST",
          body: formData
        }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not replace voice source");
      }

      resultBox.innerHTML = `
        <strong>Voice source replaced.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(data.label || data.displayName || data.voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Parameter</div>
            <div class="result-value">Rebuilt</div>
          </div>
          <div class="result-row">
            <div class="result-label">Preview</div>
            <div class="result-value">Rebuilt</div>
          </div>
        </div>
      `;

      if (data.voicePreviewUrl) {
        audioPlayer.src = `${data.voicePreviewUrl}${data.voicePreviewUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");
      }

      pendingSelectSavedVoiceId = data.voiceId || voice.voiceId;
      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      replaceSavedVoiceSourceBtn.disabled = false;
      replaceSavedVoiceSourceBtn.textContent = "Replace source";
    }
  }

  async function deleteSavedVoice(voiceId, label) {
    const ok = confirm(`Delete saved voice: ${label || voiceId}?`);

    if (!ok) return;

    resultBox.textContent = `Deleting saved voice: ${label || voiceId}...`;

    try {
      const response = await fetch(
        `/api/clone-voice/my-voices/${encodeURIComponent(voiceId)}?workspaceId=${encodeURIComponent(activeWorkspaceId)}`,
        { method: "DELETE" }
      );

      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not delete saved voice");
      }

      resultBox.innerHTML = `
        <strong>Saved voice deleted.</strong>
        <div class="result-grid">
          <div class="result-row">
            <div class="result-label">Voice</div>
            <div class="result-value">${escapeHtml(label || voiceId)}</div>
          </div>
          <div class="result-row">
            <div class="result-label">Deleted files</div>
            <div class="result-value">${escapeHtml(data.deletedCount || 0)}</div>
          </div>
        </div>
      `;

      await loadSavedVoices();
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    }
  }

  async function submitForm(event) {
    event.preventDefault();

    const mode = selectedMode();

    if (mode === "upload" || mode === "record") {
      alert("Save the voice first. Then select it from My saved voices to generate narration.");
      return;
    }

    const title = titleInput.value.trim();
    const prompt = promptInput.value.trim();

    if (!title) {
      alert("Enter a narration title.");
      return;
    }

    if (!prompt) {
      alert("Enter narration text.");
      return;
    }

    const formData = new FormData();
    formData.append("workspaceId", activeWorkspaceId);
    formData.append("title", title);
    formData.append("prompt", prompt);
    formData.append("sourceMode", mode);
    formData.append("narrationSpeed", narrationSpeed ? narrationSpeed.value : "normal");

    let endpoint = "";

    if (mode === "saved") {
      const voiceId = selectedVoiceId("savedVoiceId");

      if (!voiceId) {
        alert("Choose a saved voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-saved";
      formData.append("voiceId", voiceId);
    }

    if (mode === "system") {
      const voiceId = selectedVoiceId("systemVoiceId");

      if (!voiceId) {
        alert("Choose a system voice.");
        return;
      }

      endpoint = "/api/clone-voice/from-system";
      formData.append("voiceId", voiceId);
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";
    resultBox.textContent = "Generating narration...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log("[Clone Voice narration response]", data);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Narration failed");
      }

      const audioUrl = data.audioUrl || data.assetUrl;

      if (audioUrl) {
        audioPlayer.src = `${audioUrl}${audioUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
        audioPlayer.classList.remove("hidden");

        downloadLink.href = audioUrl;
        downloadLink.classList.remove("hidden");
      }

      renderFriendlyResult(data);
    } catch (error) {
      resultBox.textContent = error.message || String(error);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Generate narration";
    }
  }

  sourceModeInputs.forEach((input) => {
    input.addEventListener("change", () => setMode(selectedMode()));
  });

  workspaceSelect.addEventListener("change", () => {
    switchWorkspace(workspaceSelect.value);
  });

  saveVoiceBtn.addEventListener("click", saveClientVoice);

  startRecordingBtn.addEventListener("click", startRecording);
  stopRecordingBtn.addEventListener("click", stopRecording);
  discardRecordingBtn.addEventListener("click", discardRecording);

  refreshSavedBtn.addEventListener("click", loadSavedVoices);

  if (saveSavedVoiceMetaBtn) {
    saveSavedVoiceMetaBtn.addEventListener("click", saveSelectedSavedVoiceMetadata);
  }

  if (replaceSavedVoiceSourceBtn) {
    replaceSavedVoiceSourceBtn.addEventListener("click", replaceSelectedSavedVoiceSource);
  }
  refreshSystemBtn.addEventListener("click", loadSystemVoices);

  savedGenderFilter.addEventListener("change", () => {
    renderVoiceList(savedVoicesList, savedVoices, "savedVoiceId", savedGenderFilter.value);
  });

  systemGenderFilter.addEventListener("change", () => {
    renderVoiceList(systemVoicesList, systemVoices, "systemVoiceId", systemGenderFilter.value);
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches('input[name="savedVoiceId"]')) {
      updateSavedVoiceEditor();
    }
  });

  document.addEventListener("click", (event) => {
    const deleteButton = event.target.closest("[data-delete-saved-voice-id]");

    if (deleteButton) {
      event.preventDefault();
      deleteSavedVoice(
        deleteButton.getAttribute("data-delete-saved-voice-id"),
        deleteButton.getAttribute("data-delete-saved-voice-label")
      );
      return;
    }

    const previewButton = event.target.closest("[data-preview-url]");

    if (previewButton) {
      event.preventDefault();
      playPreview(previewButton.getAttribute("data-preview-url"));
    }
  });

  form.addEventListener("submit", submitForm);

  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadWorkspaces();
  loadSystemVoices();
  setMode("upload");
})();
