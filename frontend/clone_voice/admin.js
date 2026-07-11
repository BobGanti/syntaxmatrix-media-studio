(() => {
  const $ = (selector) => document.querySelector(selector);

  const durationForm = $("#durationForm");
  const durationInput = $("#durationInput");
  const saveDurationBtn = $("#saveDurationBtn");
  const durationStatusBox = $("#durationStatusBox");

  const systemVoiceForm = $("#systemVoiceForm");
  const systemVoiceAudio = $("#systemVoiceAudio");
  const systemVoiceDisplayName = $("#systemVoiceDisplayName");
  const systemVoiceGender = $("#systemVoiceGender");
  const replaceSystemVoice = $("#replaceSystemVoice");
  const saveSystemVoiceBtn = $("#saveSystemVoiceBtn");
  const systemVoiceStatusBox = $("#systemVoiceStatusBox");

  const systemVoiceFilter = $("#systemVoiceFilter");
  const refreshSystemVoicesBtn = $("#refreshSystemVoicesBtn");
  const systemVoicesList = $("#systemVoicesList");
  const systemPreviewPlayer = $("#systemPreviewPlayer");

  let systemVoices = [];

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
    if (!raw.trim()) return {};
    try {
      return JSON.parse(raw);
    } catch (_error) {
      const plain = raw.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 240);
      throw new Error(`Server returned HTTP ${response.status} ${response.statusText || ""} instead of JSON${plain ? `: ${plain}` : ""}`.trim());
    }
  }

  async function createSystemUploadSession(file) {
    const response = await fetch("/api/clone-voice/source-uploads/system/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name || "system_voice.wav",
        contentType: file.type || "application/octet-stream",
        sizeBytes: file.size
      })
    });
    const data = await parseApiResponse(response);
    if (!response.ok || !data.ok || !data.uploadUrl || !data.objectKey) {
      throw new Error(data.message || data.error || "Could not create a system-voice upload session");
    }
    return data;
  }

  async function putSystemVoiceFile(session, file) {
    const response = await fetch(session.uploadUrl, {
      method: session.method || "PUT",
      headers: { "Content-Type": session.contentType || file.type || "application/octet-stream" },
      body: file,
      credentials: "omit",
      cache: "no-store"
    });
    if (!response.ok) {
      const detail = (await response.text().catch(() => "")).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 240);
      throw new Error(`Direct storage upload failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
  }

  function durationStatus(data, message) {
    const rawDurationLimit = Number(data.maxRawSourceSeconds || 0);
    durationStatusBox.innerHTML = `
      <strong>${escapeHtml(message)}</strong><br>
      Target D: ${escapeHtml(data.maxVoiceSourceSeconds)} seconds<br>
      Automatic backend trimming: ${data.autoTrimVoiceSource === false ? "Disabled" : "Enabled"}<br>
      Raw upload safety limit: ${escapeHtml(data.maxRawUploadMb)} MB<br>
      Raw duration safety limit: ${rawDurationLimit > 0 ? `${rawDurationLimit} seconds` : "Disabled"}<br>
      Config: ${escapeHtml(data.configPath)}
    `;
  }

  async function loadDurationSettings() {
    durationStatusBox.textContent = "Loading setting...";

    try {
      const response = await fetch(`/api/clone-voice/settings?t=${Date.now()}`, { cache: "no-store" });
      const data = await parseApiResponse(response);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not load settings");
      }

      durationInput.removeAttribute("min");
      durationInput.removeAttribute("max");
      durationInput.value = data.maxVoiceSourceSeconds || 20;
      durationStatus(data, "Setting loaded.");
    } catch (error) {
      durationStatusBox.textContent = error.message || String(error);
    }
  }

  async function saveDuration(event) {
    event.preventDefault();

    saveDurationBtn.disabled = true;
    saveDurationBtn.textContent = "Saving...";

    try {
      const response = await fetch("/api/clone-voice/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ maxVoiceSourceSeconds: Number(durationInput.value) })
      });

      const data = await parseApiResponse(response);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not save settings");
      }

      durationInput.value = data.maxVoiceSourceSeconds;
      durationStatus(data, "Setting saved.");
    } catch (error) {
      durationStatusBox.textContent = error.message || String(error);
    } finally {
      saveDurationBtn.disabled = false;
      saveDurationBtn.textContent = "Save duration";
    }
  }

  function filteredSystemVoices() {
    const filter = systemVoiceFilter.value;
    if (!filter) return systemVoices;
    return systemVoices.filter((voice) => String(voice.gender || "").toUpperCase() === filter);
  }

  function renderSystemVoices() {
    const rows = filteredSystemVoices();

    if (!rows.length) {
      systemVoicesList.innerHTML = `<p class="status">No system voices found for this filter.</p>`;
      return;
    }

    systemVoicesList.innerHTML = rows.map((voice) => {
      const previewButton = voice.previewUrl
        ? `<button class="secondary" type="button" data-preview-url="${escapeHtml(voice.previewUrl)}">▶</button>`
        : `<button class="secondary" type="button" disabled>No preview</button>`;

      return `
        <div class="voice-card">
          <div>
            <div class="voice-title">${escapeHtml(voice.label || voice.displayName || voice.voiceId)}</div>
            <div class="voice-meta">${escapeHtml(voice.parameterPath || "")}</div>
          </div>
          ${previewButton}
          <button class="danger" type="button" data-delete-voice-id="${escapeHtml(voice.voiceId)}" data-delete-label="${escapeHtml(voice.label || voice.voiceId)}">🗑</button>
        </div>
      `;
    }).join("");
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
      renderSystemVoices();
    } catch (error) {
      systemVoicesList.textContent = error.message || String(error);
    }
  }

  function systemVoiceStatus(data, message) {
    systemVoiceStatusBox.innerHTML = `
      <strong>${escapeHtml(message)}</strong><br>
      Voice: ${escapeHtml(data.label || data.displayName || data.voiceId || "")}<br>
      Gender: ${escapeHtml(data.gender || "")}<br>
      ${data.replaced ? "Existing voice replaced." : "New system voice created."}
    `;
  }

  async function saveSystemVoice(event) {
    event.preventDefault();

    const file = systemVoiceAudio.files[0];
    const displayName = systemVoiceDisplayName.value.trim();
    if (!file) return alert("Choose a system voice source audio file.");
    if (!displayName) return alert("Enter a display name.");
    if (systemVoiceGender.value !== "M" && systemVoiceGender.value !== "F") {
      systemVoiceGender.focus();
      return alert("Choose system voice gender: Male (M) or Female (F).");
    }

    saveSystemVoiceBtn.disabled = true;
    saveSystemVoiceBtn.textContent = "Creating...";
    systemVoiceStatusBox.textContent = "Uploading system voice source directly to secure storage...";

    try {
      const session = await createSystemUploadSession(file);
      await putSystemVoiceFile(session, file);
      systemVoiceStatusBox.textContent = "Upload complete. The backend is checking duration, trimming to D when required, and creating the standard preview...";
      const response = await fetch("/api/clone-voice/source-uploads/system/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objectKey: session.objectKey,
          originalFilename: file.name,
          sizeBytes: file.size,
          displayName,
          gender: systemVoiceGender.value,
          replace: replaceSystemVoice.checked
        })
      });
      const data = await parseApiResponse(response);
      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not create system voice");
      systemVoiceStatus(data, data.replaced ? "System voice replaced." : "System voice created.");
      systemVoiceAudio.value = "";
      await loadSystemVoices();
    } catch (error) {
      systemVoiceStatusBox.textContent = error.message || String(error);
    } finally {
      saveSystemVoiceBtn.disabled = false;
      saveSystemVoiceBtn.textContent = "Create system voice";
    }
  }

  async function playPreview(url) {
    if (!url) return;

    systemPreviewPlayer.classList.remove("hidden");
    systemPreviewPlayer.src = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
    await systemPreviewPlayer.play().catch(() => {});
  }

  async function deleteSystemVoice(voiceId, label) {
    const ok = confirm(`Delete system voice: ${label || voiceId}?`);
    if (!ok) return;

    systemVoiceStatusBox.textContent = `Deleting ${label || voiceId}...`;

    try {
      const response = await fetch(`/api/clone-voice/system-voices/${encodeURIComponent(voiceId)}`, {
        method: "DELETE"
      });

      const data = await parseApiResponse(response);

      if (!response.ok || !data.ok) {
        throw new Error(data.message || data.error || "Could not delete system voice");
      }

      systemVoiceStatusBox.innerHTML = `
        <strong>System voice deleted.</strong><br>
        Deleted files: ${escapeHtml(data.deletedCount || 0)}
      `;

      await loadSystemVoices();
    } catch (error) {
      systemVoiceStatusBox.textContent = error.message || String(error);
    }
  }

  durationForm.addEventListener("submit", saveDuration);
  systemVoiceForm.addEventListener("submit", saveSystemVoice);
  refreshSystemVoicesBtn.addEventListener("click", loadSystemVoices);
  systemVoiceFilter.addEventListener("change", renderSystemVoices);

  document.addEventListener("click", (event) => {
    const previewButton = event.target.closest("[data-preview-url]");
    if (previewButton) {
      event.preventDefault();
      playPreview(previewButton.getAttribute("data-preview-url"));
      return;
    }

    const deleteButton = event.target.closest("[data-delete-voice-id]");
    if (deleteButton) {
      event.preventDefault();
      deleteSystemVoice(
        deleteButton.getAttribute("data-delete-voice-id"),
        deleteButton.getAttribute("data-delete-label")
      );
    }
  });

  loadDurationSettings();
  loadSystemVoices();
})();
