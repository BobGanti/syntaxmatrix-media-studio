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
  const narrationStyle = $("#narrationStyle");
  const promptInput = $("#promptInput");
  const submitBtn = $("#submitBtn");

  const audioPlayer = $("#audioPlayer");
  const downloadLink = $("#downloadLink");
  const resultBox = $("#resultBox");

  let activeWorkspaceId = "";
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


  async function parseApiResponse(response) {
    const raw = await response.text();

    if (!raw.trim()) {
      return {};
    }

    try {
      return JSON.parse(raw);
    } catch (_error) {
      const plainText = raw
        .replace(/<script[\s\S]*?<\/script>/gi, " ")
        .replace(/<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 240);

      const status = `${response.status} ${response.statusText || ""}`.trim();
      const detail = plainText ? `: ${plainText}` : "";
      throw new Error(`Server returned HTTP ${status} instead of JSON${detail}`);
    }
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
      const data = await parseApiResponse(response);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load workspaces");
      }

      availableWorkspaces = Array.isArray(data.workspaces) ? data.workspaces : [];
      if (!availableWorkspaces.length) {
        throw new Error("No active workspace is assigned to this account.");
      }
      activeWorkspaceId = data.defaultWorkspaceId || availableWorkspaces[0].workspaceId;
    } catch (error) {
      console.error("[Clone Voice] Could not load workspace list.", error);
      availableWorkspaces = [];
      activeWorkspaceId = "";
      workspaceSelect.innerHTML = '<option value="">Workspace unavailable</option>';
      workspaceSelect.disabled = true;
      resultBox.textContent = error.message || "Could not load your workspace.";
      return;
    }

    workspaceSelect.disabled = false;
    renderWorkspaceOptions();
    setWorkspaceStatus();
    await loadSavedVoices();
  }

  async function switchWorkspace(workspaceId) {
    activeWorkspaceId = workspaceId || "";
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
    const styleDisplay = data.narrationStyleDisplay || data.narrationStyleLabel || "";
    const rows = [
      ["Title", data.narrationTitle || ""],
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Speed", data.narrationSpeedDisplay || (data.narrationSpeedMultiplier ? `${data.narrationSpeedMultiplier}x` : "")],
      ["Style", styleDisplay],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Narration ready.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderVoiceSavedResult(data) {
    const rows = [
      ["Voice", data.label || data.displayName || data.voiceId || ""],
      ["Gender", data.gender || ""],
    ].filter((row) => row[1] !== "");

    resultBox.innerHTML = `
      <strong>Voice saved.</strong>
      <div class="result-grid">
        ${rows.map(([label, value]) => `
          <div class="result-row">
            <div class="result-label">${escapeHtml(label)}</div>
            <div class="result-value">${escapeHtml(value)}</div>
          </div>
        `).join("")}
      </div>
      <div class="muted">Preview is ready. Select this voice under My saved voices to generate narration.</div>
    `;
  }

  async function loadCloneVoiceSettings() {
    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, { cache: "no-store" });
      const data = await parseApiResponse(response);

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

      const data = await parseApiResponse(response);

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
      const data = await parseApiResponse(response);

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

    let activePreviewAudio = null;
    let activePreviewButton = null;
    let activePreviewObjectUrl = "";
    let activePreviewRequestId = 0;

    function setPreviewButtonState(button, state) {
      if (!button) return;

      const icon = button.querySelector("[aria-hidden='true']");
      button.dataset.previewState = state;
      button.classList.toggle("is-playing", state === "playing");

      if (state === "playing") {
        button.setAttribute("aria-label", "Stop voice preview");
        button.setAttribute("title", "Stop preview");
        if (icon) icon.textContent = "■";
        return;
      }

      if (state === "loading") {
        button.setAttribute("aria-label", "Loading voice preview");
        button.setAttribute("title", "Loading preview");
        if (icon) icon.textContent = "…";
        return;
      }

      button.setAttribute("aria-label", "Play voice preview");
      button.setAttribute("title", "Play preview");
      if (icon) icon.textContent = "▶";
    }

    function stopActivePreview() {
      activePreviewRequestId += 1;

      if (activePreviewAudio) {
        try {
          activePreviewAudio.pause();
          activePreviewAudio.currentTime = 0;
        } catch (error) {
          console.warn("[Clone Voice] Could not stop preview:", error);
        }
      }

      if (activePreviewObjectUrl) {
        URL.revokeObjectURL(activePreviewObjectUrl);
      }

      setPreviewButtonState(activePreviewButton, "idle");

      activePreviewAudio = null;
      activePreviewButton = null;
      activePreviewObjectUrl = "";
    }

    async function playPreview(url, button) {
      if (!url || !button) return;

      if (
        activePreviewButton === button &&
        button.dataset.previewState !== "idle"
      ) {
        stopActivePreview();
        return;
      }

      stopActivePreview();

      const requestId = activePreviewRequestId;
      activePreviewButton = button;
      setPreviewButtonState(button, "loading");

      try {
        const separator = url.includes("?") ? "&" : "?";
        const response = await fetch(
          `${url}${separator}t=${Date.now()}`,
          { cache: "no-store" }
        );

        if (!response.ok) {
          const details = await response.text().catch(() => "");
          throw new Error(
            `Voice preview failed (${response.status}). ${details.slice(0, 160)}`
          );
        }

        const blob = await response.blob();

        if (!blob.size) {
          throw new Error("Voice preview response was empty.");
        }

        if (
          requestId !== activePreviewRequestId ||
          activePreviewButton !== button
        ) {
          return;
        }

        const objectUrl = URL.createObjectURL(blob);
        const audio = new Audio(objectUrl);

        activePreviewObjectUrl = objectUrl;
        activePreviewAudio = audio;

        audio.addEventListener("ended", () => {
          if (activePreviewAudio === audio) {
            stopActivePreview();
          }
        }, { once: true });

        audio.addEventListener("error", () => {
          if (activePreviewAudio === audio) {
            stopActivePreview();
          }
        }, { once: true });

        setPreviewButtonState(button, "playing");
        await audio.play();
      } catch (error) {
        if (requestId === activePreviewRequestId) {
          stopActivePreview();
        }

        console.error("[Clone Voice] Preview playback failed:", error);
        alert(error.message || "Could not play the voice preview.");
      }
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

  async function createDirectUploadSession(endpoint, file, extra = {}) {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name || "voice_source.wav",
        contentType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        ...extra
      })
    });
    const data = await parseApiResponse(response);
    if (!response.ok || !data.ok || !data.uploadUrl || !data.objectKey) {
      throw new Error(data.message || data.error || "Could not create a direct upload session");
    }
    return data;
  }

  async function putFileIntoUploadSession(session, file) {
    const response = await fetch(session.uploadUrl, {
      method: session.method || "PUT",
      headers: {
        "Content-Type": session.contentType || file.type || "application/octet-stream"
      },
      body: file,
      credentials: "omit",
      cache: "no-store"
    });
    if (!response.ok) {
      const detail = (await response.text().catch(() => "")).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 240);
      throw new Error(`Direct storage upload failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
  }

  async function uploadWorkspaceVoiceSource(file, purpose = "create") {
    const session = await createDirectUploadSession(
      "/api/clone-voice/source-uploads/workspace/session",
      file,
      { workspaceId: activeWorkspaceId, purpose }
    );
    await putFileIntoUploadSession(session, file);
    return session;
  }

  async function saveClientVoice() {
    const mode = selectedMode();

    if (mode !== "upload" && mode !== "record") {
      alert("Switch to Upload audio or Record voice to save a new voice.");
      return;
    }

    const selectedGender = requireSelectedGender();
    if (!selectedGender) return;

    saveVoiceBtn.disabled = true;
    saveVoiceBtn.textContent = "Saving voice...";
    audioPlayer.classList.add("hidden");
    downloadLink.classList.add("hidden");

    try {
      let response;

      if (mode === "upload") {
        const file = audioFile.files[0];
        if (!file) throw new Error("Choose an audio file first.");

        resultBox.textContent = "Uploading voice source directly to secure storage...";
        const session = await uploadWorkspaceVoiceSource(file, "create");
        resultBox.textContent = "Upload complete. The backend is checking duration, trimming to D when required, and creating the voice...";

        response = await fetch("/api/clone-voice/source-uploads/workspace/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workspaceId: activeWorkspaceId,
            sourceMode: "upload",
            voiceDisplayName: voiceDisplayName.value.trim(),
            gender: selectedGender,
            objectKey: session.objectKey,
            originalFilename: file.name,
            sizeBytes: file.size
          })
        });
      } else {
        if (!recordedBlob) throw new Error("Record a voice first.");
        const formData = new FormData();
        formData.append("workspaceId", activeWorkspaceId);
        formData.append("sourceMode", "record");
        formData.append("voiceDisplayName", voiceDisplayName.value.trim());
        formData.append("gender", selectedGender);
        formData.append("audio", recordedBlob, recordedFilename || "recorded_voice.webm");
        resultBox.textContent = "Saving recorded voice and generating standard preview...";
        response = await fetch("/api/clone-voice/voices/from-source", { method: "POST", body: formData });
      }

      const data = await parseApiResponse(response);
      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save voice");
      }

      renderVoiceSavedResult(data);
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

      const data = await parseApiResponse(response);

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
    const file = replaceSavedVoiceAudio.files[0];

    if (!voice) {
      alert("Choose a saved voice first.");
      return;
    }
    if (!file) {
      alert("Choose a replacement audio file.");
      return;
    }

    const displayName = editSavedVoiceDisplayName.value.trim() || voice.displayName || voice.voiceId;
    const gender = editSavedVoiceGender.value || voice.gender;
    if (gender !== "M" && gender !== "F") {
      alert("Choose Male (M) or Female (F).");
      return;
    }
    if (!confirm(`Replace source for ${voice.label || voice.voiceId}? This rebuilds its parameter and preview.`)) return;

    replaceSavedVoiceSourceBtn.disabled = true;
    replaceSavedVoiceSourceBtn.textContent = "Replacing...";
    resultBox.textContent = "Uploading replacement source directly to secure storage...";

    try {
      const session = await uploadWorkspaceVoiceSource(file, "replace");
      resultBox.textContent = "Upload complete. The backend is checking duration, trimming to D when required, and rebuilding the voice...";
      const response = await fetch("/api/clone-voice/source-uploads/workspace/replace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspaceId: activeWorkspaceId,
          voiceId: voice.voiceId,
          displayName,
          gender,
          objectKey: session.objectKey,
          originalFilename: file.name,
          sizeBytes: file.size
        })
      });
      const data = await parseApiResponse(response);
      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not replace voice source");

      resultBox.innerHTML = `
        <strong>Voice source replaced.</strong>
        <div class="result-grid">
          <div class="result-row"><div class="result-label">Voice</div><div class="result-value">${escapeHtml(data.label || data.displayName || data.voiceId)}</div></div>
          <div class="result-row"><div class="result-label">Source duration</div><div class="result-value">${Number(data.sourceDurationSeconds || 0).toFixed(1)} seconds</div></div>
          <div class="result-row"><div class="result-label">Trimmed to D</div><div class="result-value">${data.sourceTrimmed ? "Yes" : "No"}</div></div>
        </div>`;
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

      const data = await parseApiResponse(response);

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
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }

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
    formData.append("narrationStyle", narrationStyle ? narrationStyle.value : "natural");

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

      const data = await parseApiResponse(response);
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
      playPreview(
          previewButton.getAttribute("data-preview-url"),
          previewButton
        );
    }
  });

  function handleGenerateButtonClick(event) {
    event.preventDefault();
    submitForm(event);
  }

  submitBtn.addEventListener("click", handleGenerateButtonClick);

  form.addEventListener("submit", submitForm);

  renderMicLevel(0);
  loadCloneVoiceSettings();
  loadWorkspaces();
  loadSystemVoices();
  setMode("upload");
})();
