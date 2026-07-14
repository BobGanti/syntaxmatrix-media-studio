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

// >>> SMX_ADMIN_CLEANUP_STANDALONE_V1 >>>
(function smxAdminCleanupStandaloneV1() {
  const ROOT_ID = "smxAdminClientCleanupStandalone";
  const STYLE_ID = "smx-admin-cleanup-standalone-style-v1";

  const state = {
    clients: [],
    query: "",
    filter: "all",
    pageSize: 25,
    page: 1,
    loading: false,
    error: "",
    searchTimer: null,
  };

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function lower(value) {
    return String(value ?? "").toLowerCase().trim();
  }

  function truthy(value) {
    return value === true || String(value ?? "").toLowerCase() === "true";
  }

  async function authHeaders(json) {
    const headers = json ? {"Content-Type": "application/json"} : {};

    try {
      const compatUser =
        window.firebase &&
        window.firebase.auth &&
        window.firebase.auth().currentUser;

      if (compatUser && compatUser.getIdToken) {
        headers.Authorization = `Bearer ${await compatUser.getIdToken()}`;
      }
    } catch (_) {
      // Backend cookie session is still used via credentials: include.
    }

    return headers;
  }

  async function apiJson(url, options = {}) {
    const method = options.method || "GET";
    const hasBody = Object.prototype.hasOwnProperty.call(options, "body");

    const res = await fetch(url, {
      method,
      credentials: "include",
      cache: "no-store",
      headers: await authHeaders(hasBody),
      body: hasBody ? JSON.stringify(options.body || {}) : undefined,
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok || data.ok === false) {
      throw new Error(data.message || data.error || `Request failed: ${res.status}`);
    }

    return data;
  }

  function injectStyle() {
    const old = document.getElementById(STYLE_ID);
    if (old) old.remove();

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${ROOT_ID},
      #${ROOT_ID} *,
      #${ROOT_ID} *::before,
      #${ROOT_ID} *::after {
        box-sizing: border-box;
      }

      #${ROOT_ID} {
        width: min(1360px, calc(100vw - 48px));
        max-width: calc(100vw - 48px);
        margin: 28px auto 36px;
        color: #f4fbff;
        font-family: inherit;
      }

      #${ROOT_ID} .smx-cleanup-shell {
        width: 100%;
        overflow: hidden;
        border: 1px solid rgba(139, 213, 255, 0.2);
        border-radius: 26px;
        background: rgba(4, 15, 28, 0.82);
        padding: 28px;
      }

      #${ROOT_ID} .smx-cleanup-head {
        display: grid;
        grid-template-columns: minmax(280px, 1fr) max-content;
        gap: 18px;
        align-items: start;
        margin-bottom: 18px;
      }

      #${ROOT_ID} .smx-kicker {
        margin: 0 0 8px;
        color: #8df7ee;
        font-weight: 900;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 14px;
      }

      #${ROOT_ID} h1 {
        margin: 0 0 10px;
        line-height: 0.96;
        font-size: clamp(38px, 4vw, 62px);
      }

      #${ROOT_ID} .smx-subtitle {
        margin: 0;
        max-width: 760px;
        color: #c9dcf2;
        font-size: 18px;
        line-height: 1.45;
      }

      #${ROOT_ID} .smx-btn {
        border: 0;
        border-radius: 999px;
        min-height: 44px;
        padding: 12px 20px;
        background: linear-gradient(135deg, #9df2e8, #8bb9ff);
        color: #06111d;
        font-weight: 900;
        font-size: 16px;
        cursor: pointer;
        white-space: nowrap;
      }

      #${ROOT_ID} .smx-btn.secondary {
        background: rgba(255,255,255,.055);
        color: #d9eaff;
        border: 1px solid rgba(139,213,255,.16);
      }

      #${ROOT_ID} .smx-btn.danger {
        background: linear-gradient(135deg, #ffadbd, #ff7b85);
        color: #111827;
      }

      #${ROOT_ID} .smx-btn.blocked {
        background: rgba(255, 150, 170, 0.42);
        color: #111827;
        cursor: not-allowed;
      }

      #${ROOT_ID} .smx-btn:disabled {
        opacity: .6;
        cursor: not-allowed;
      }

      #${ROOT_ID} .smx-stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 18px 0;
      }

      #${ROOT_ID} .smx-stat {
        min-width: 0;
        border: 1px solid rgba(139,213,255,.18);
        border-radius: 18px;
        background: rgba(255,255,255,.035);
        padding: 16px;
      }

      #${ROOT_ID} .smx-stat-label {
        color: #b6cdeb;
        font-size: 13px;
        font-weight: 900;
        letter-spacing: .08em;
        text-transform: uppercase;
      }

      #${ROOT_ID} .smx-stat-value {
        margin-top: 8px;
        font-size: 30px;
        font-weight: 900;
      }

      #${ROOT_ID} .smx-toolbar {
        display: grid;
        grid-template-columns: minmax(280px, 1fr) 210px 180px 140px;
        gap: 12px;
        align-items: center;
        margin-bottom: 16px;
      }

      #${ROOT_ID} input,
      #${ROOT_ID} select {
        width: 100%;
        min-width: 0;
        min-height: 44px;
        border-radius: 16px;
        border: 1px solid rgba(139,213,255,.18);
        background: rgba(2, 10, 19, .92);
        color: #f4fbff;
        padding: 0 14px;
        font: inherit;
        font-weight: 800;
      }

      #${ROOT_ID} input::placeholder {
        color: #93a9c4;
      }

      #${ROOT_ID} .smx-table-wrap {
        width: 100%;
        max-width: 100%;
        overflow-x: auto;
        overflow-y: visible;
        border: 1px solid rgba(139,213,255,.14);
        border-radius: 18px;
      }

      #${ROOT_ID} table {
        width: 100%;
        min-width: 1080px;
        border-collapse: collapse;
      }

      #${ROOT_ID} th,
      #${ROOT_ID} td {
        padding: 14px;
        text-align: left;
        white-space: nowrap;
        border-bottom: 1px solid rgba(139,213,255,.12);
        vertical-align: middle;
      }

      #${ROOT_ID} th {
        color: #9beeff;
        font-size: 13px;
        letter-spacing: .05em;
        text-transform: uppercase;
      }

      #${ROOT_ID} tr:last-child td {
        border-bottom: 0;
      }

      #${ROOT_ID} td:last-child,
      #${ROOT_ID} th:last-child {
        position: sticky;
        right: 0;
        background: #06111d;
        box-shadow: -10px 0 18px rgba(0,0,0,.28);
        z-index: 2;
      }

      #${ROOT_ID} th:last-child {
        z-index: 3;
      }

      #${ROOT_ID} .smx-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 6px 12px;
        font-weight: 900;
        font-size: 13px;
        color: #06111d;
        background: #a9f5bf;
      }

      #${ROOT_ID} .smx-badge.info {
        background: #a8efff;
      }

      #${ROOT_ID} .smx-small {
        color: #8fb0d3;
        font-size: 13px;
      }

      #${ROOT_ID} .smx-actions {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: flex-end;
      }

      #${ROOT_ID} .smx-pagination {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
        margin: 14px 0 0;
        color: #bcd3ee;
      }

      #${ROOT_ID} .smx-page-buttons {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      #${ROOT_ID} .smx-manual {
        margin-top: 24px;
        padding-top: 22px;
        border-top: 1px solid rgba(139,213,255,.14);
      }

      #${ROOT_ID} .smx-manual h2 {
        margin: 0 0 8px;
        font-size: 24px;
      }

      #${ROOT_ID} .smx-manual p {
        margin: 0 0 14px;
        color: #c9dcf2;
        line-height: 1.45;
      }

      #${ROOT_ID} .smx-manual-form {
        display: grid;
        grid-template-columns: minmax(220px, .8fr) minmax(320px, 1.2fr) 150px;
        gap: 12px;
        align-items: center;
      }

      #${ROOT_ID} .smx-message {
        padding: 18px;
        border: 1px solid rgba(139,213,255,.16);
        border-radius: 16px;
        color: #c9dcf2;
      }

      #${ROOT_ID} .smx-message.error {
        color: #ffb7c3;
        border-color: rgba(255,140,160,.32);
      }

      @media (max-width: 820px) {
        #${ROOT_ID} {
          width: calc(100vw - 24px);
          max-width: calc(100vw - 24px);
          margin: 18px auto 28px;
        }

        #${ROOT_ID} .smx-cleanup-shell {
          padding: 18px;
        }

        #${ROOT_ID} .smx-cleanup-head,
        #${ROOT_ID} .smx-stats,
        #${ROOT_ID} .smx-toolbar,
        #${ROOT_ID} .smx-manual-form {
          grid-template-columns: 1fr;
        }

        #${ROOT_ID} .smx-btn {
          width: 100%;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function ensureRoot() {
    let root = document.getElementById(ROOT_ID);

    if (!root) {
      root = document.createElement("section");
      root.id = ROOT_ID;

      const target =
        document.querySelector("main") ||
        document.querySelector(".admin-page") ||
        document.body;

      if (target === document.body) {
        document.body.insertBefore(root, document.body.firstChild);
      } else {
        target.insertBefore(root, target.firstChild);
      }
    }

    return root;
  }

  function normalizeClient(client) {
    return {
      workspaceId: client.workspaceId || client.workspace_id || "",
      workspaceLabel: client.workspaceLabel || client.workspace_label || client.name || client.workspaceId || "Workspace",
      billingEmail: client.billingEmail || client.billing_email || client.email || "",
      planKey: lower(client.planKey || client.plan_key || client.plan || "free") || "free",
      subscriptionStatus: lower(client.subscriptionStatus || client.subscription_status || client.status || "active") || "active",
      provider: lower(client.provider || "internal") || "internal",
      memberCount: Number(client.memberCount ?? client.member_count ?? 0) || 0,
      stripeSubscriptionId: client.stripeSubscriptionId || client.stripe_subscription_id || client.subscriptionId || "",
      activeStripeSubscription: truthy(client.activeStripeSubscription) || lower(client.provider) === "stripe",
      duplicateEmail: truthy(client.duplicateEmail),
    };
  }

  function filteredClients() {
    const query = lower(state.query);

    return state.clients.filter((client) => {
      if (state.filter === "free" && client.planKey !== "free") return false;
      if (state.filter === "paid" && client.planKey === "free") return false;
      if (state.filter === "duplicates" && !client.duplicateEmail) return false;

      if (!query) return true;

      const blob = [
        client.workspaceId,
        client.workspaceLabel,
        client.billingEmail,
        client.planKey,
        client.subscriptionStatus,
        client.provider,
        client.stripeSubscriptionId,
      ].join(" ").toLowerCase();

      return blob.includes(query);
    });
  }

  function statsHtml() {
    const active = state.clients.filter((c) => c.subscriptionStatus !== "archived").length;
    const duplicates = state.clients.filter((c) => c.duplicateEmail).length;
    const free = state.clients.filter((c) => c.planKey === "free").length;
    const paid = state.clients.filter((c) => c.planKey !== "free").length;

    return `
      <div class="smx-stats">
        <div class="smx-stat"><div class="smx-stat-label">Active clients</div><div class="smx-stat-value">${active}</div></div>
        <div class="smx-stat"><div class="smx-stat-label">Duplicate emails</div><div class="smx-stat-value">${duplicates}</div></div>
        <div class="smx-stat"><div class="smx-stat-label">Free</div><div class="smx-stat-value">${free}</div></div>
        <div class="smx-stat"><div class="smx-stat-label">Paid / legacy</div><div class="smx-stat-value">${paid}</div></div>
      </div>
    `;
  }

  function toolbarHtml() {
    return `
      <div class="smx-toolbar">
        <input id="smxCleanupSearch" placeholder="Search email, workspace, plan, provider..." value="${esc(state.query)}">
        <select id="smxCleanupFilter">
          <option value="all" ${state.filter === "all" ? "selected" : ""}>All active</option>
          <option value="free" ${state.filter === "free" ? "selected" : ""}>Free</option>
          <option value="paid" ${state.filter === "paid" ? "selected" : ""}>Paid / legacy</option>
          <option value="duplicates" ${state.filter === "duplicates" ? "selected" : ""}>Duplicates</option>
        </select>
        <select id="smxCleanupPageSize">
          ${[10, 25, 50, 100].map((size) => `<option value="${size}" ${state.pageSize === size ? "selected" : ""}>${size} / page</option>`).join("")}
        </select>
        <button type="button" class="smx-btn" id="smxCleanupRefresh">Refresh</button>
      </div>
    `;
  }

  function tableHtml(rows) {
    if (state.loading) {
      return `<div class="smx-message">Loading clients...</div>`;
    }

    if (state.error) {
      return `<div class="smx-message error">${esc(state.error)}</div>`;
    }

    if (!rows.length) {
      return `<div class="smx-message">No clients match the current filter.</div>`;
    }

    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    state.page = Math.min(Math.max(1, state.page), totalPages);

    const start = (state.page - 1) * state.pageSize;
    const visible = rows.slice(start, start + state.pageSize);

    const body = visible.map((client) => {
      const stripeText = client.stripeSubscriptionId || "—";
      const deleteDisabled = client.activeStripeSubscription;
      const deleteLabel = deleteDisabled ? "Blocked" : "Delete";
      const deleteClass = deleteDisabled ? "smx-btn blocked" : "smx-btn danger";

      return `
        <tr>
          <td>
            <strong>${esc(client.workspaceLabel)}</strong><br>
            <span class="smx-small">${esc(client.workspaceId)}</span>
          </td>
          <td>
            <strong>${esc(client.billingEmail || "—")}</strong>
            ${client.duplicateEmail ? `<br><span class="smx-small" style="color:#ffdc7a;font-weight:900;">Duplicate email</span>` : ""}
          </td>
          <td><span class="smx-badge">${esc(client.planKey)}</span></td>
          <td><span class="smx-badge info">${esc(client.subscriptionStatus)}</span></td>
          <td>${esc(client.provider)}</td>
          <td>${esc(client.memberCount)}</td>
          <td><span class="smx-small">${esc(stripeText)}</span></td>
          <td>
            <div class="smx-actions">
              <button type="button" class="${deleteClass}" ${deleteDisabled ? "disabled" : ""} data-cleanup-delete="${esc(client.workspaceId)}">${deleteLabel}</button>
              <button type="button" class="smx-btn secondary" data-cleanup-sync="${esc(client.workspaceId)}">Sync</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    return `
      <div class="smx-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Workspace</th>
              <th>Email</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Provider</th>
              <th>Members</th>
              <th>Stripe subscription</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <div class="smx-pagination">
        <span>Showing <strong>${rows.length ? start + 1 : 0}</strong>–<strong>${Math.min(start + visible.length, rows.length)}</strong> of <strong>${rows.length}</strong> filtered clients</span>
        <div class="smx-page-buttons">
          <button type="button" class="smx-btn secondary" id="smxCleanupPrev" ${state.page <= 1 ? "disabled" : ""}>Prev</button>
          <span>Page <strong>${state.page}</strong> of <strong>${totalPages}</strong></span>
          <button type="button" class="smx-btn secondary" id="smxCleanupNext" ${state.page >= totalPages ? "disabled" : ""}>Next</button>
        </div>
      </div>
    `;
  }

  function shellHtml() {
    const rows = filteredClients();

    return `
      <div class="smx-cleanup-shell">
        <div class="smx-cleanup-head">
          <div>
            <p class="smx-kicker">SyntaxMatrix Admin</p>
            <h1>Client Cleanup</h1>
            <p class="smx-subtitle">Use search, filters and pagination to manage client workspaces without crowding the page.</p>
          </div>
          <button type="button" class="smx-btn" id="smxCleanupTopRefresh">Refresh</button>
        </div>

        ${statsHtml()}
        ${toolbarHtml()}
        <div id="smxCleanupTableRegion">${tableHtml(rows)}</div>

        <div class="smx-manual">
          <h2>Manual Stripe reconcile</h2>
          <p>Use this when Stripe payment succeeded but the local workspace plan did not update. Paste cs_, sub_, pi_, or cus_.</p>
          <div class="smx-manual-form">
            <input id="smxCleanupReconcileWorkspaceId" placeholder="Workspace ID">
            <input id="smxCleanupReconcileStripeId" placeholder="Stripe ID: cs_, sub_, pi_, or cus_...">
            <button type="button" class="smx-btn" id="smxCleanupReconcileBtn">Reconcile</button>
          </div>
        </div>
      </div>
    `;
  }

  function render(options = {}) {
    injectStyle();

    const root = ensureRoot();
    root.innerHTML = shellHtml();

    bind(root);

    if (options.focusSearch) {
      const input = root.querySelector("#smxCleanupSearch");
      if (input) {
        input.focus();
        const pos = Math.min(options.cursorPosition ?? input.value.length, input.value.length);
        try { input.setSelectionRange(pos, pos); } catch (_) {}
      }
    }
  }

  async function loadClients() {
    state.loading = true;
    state.error = "";
    render();

    try {
      const payload = await apiJson(`/api/admin/client-lifecycle?t=${Date.now()}`);
      state.clients = (payload.clients || []).map(normalizeClient);
      state.page = 1;
      state.error = "";
    } catch (error) {
      state.error = error.message || String(error);
    } finally {
      state.loading = false;
      render();
    }
  }

  function bind(root) {
    root.querySelector("#smxCleanupTopRefresh")?.addEventListener("click", loadClients);
    root.querySelector("#smxCleanupRefresh")?.addEventListener("click", loadClients);

    root.querySelector("#smxCleanupSearch")?.addEventListener("input", (event) => {
      state.query = event.target.value || "";
      state.page = 1;

      const cursorPosition =
        typeof event.target.selectionStart === "number"
          ? event.target.selectionStart
          : state.query.length;

      if (state.searchTimer) clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => render({focusSearch: true, cursorPosition}), 120);
    });

    root.querySelector("#smxCleanupFilter")?.addEventListener("change", (event) => {
      state.filter = event.target.value || "all";
      state.page = 1;
      render();
    });

    root.querySelector("#smxCleanupPageSize")?.addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value || 25) || 25;
      state.page = 1;
      render();
    });

    root.querySelector("#smxCleanupPrev")?.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      render();
    });

    root.querySelector("#smxCleanupNext")?.addEventListener("click", () => {
      state.page += 1;
      render();
    });

    root.querySelectorAll("[data-cleanup-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        const workspaceId = button.getAttribute("data-cleanup-delete") || "";

        if (!workspaceId) return;

        if (!window.confirm(`Delete/archive this client workspace?\n\n${workspaceId}\n\nThis is a soft delete.`)) {
          return;
        }

        button.disabled = true;
        button.textContent = "Deleting...";

        try {
          await apiJson(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/archive`, {
            method: "POST",
            body: {reason: "admin_client_cleanup"},
          });
          await loadClients();
        } catch (error) {
          alert(error.message || String(error));
          button.disabled = false;
          button.textContent = "Delete";
        }
      });
    });

    root.querySelectorAll("[data-cleanup-sync]").forEach((button) => {
      button.addEventListener("click", async () => {
        const workspaceId = button.getAttribute("data-cleanup-sync") || "";

        if (!workspaceId) return;

        button.disabled = true;
        button.textContent = "Syncing...";

        try {
          await apiJson("/api/admin/billing/sync", {
            method: "POST",
            body: {workspaceId},
          });
          await loadClients();
        } catch (error) {
          alert(error.message || String(error));
          button.disabled = false;
          button.textContent = "Sync";
        }
      });
    });

    root.querySelector("#smxCleanupReconcileBtn")?.addEventListener("click", async () => {
      const workspaceId = root.querySelector("#smxCleanupReconcileWorkspaceId")?.value?.trim() || "";
      const stripeId = root.querySelector("#smxCleanupReconcileStripeId")?.value?.trim() || "";

      if (!workspaceId || !stripeId) {
        alert("Workspace ID and Stripe ID are required. Use cs_, sub_, pi_, or cus_.");
        return;
      }

      const button = root.querySelector("#smxCleanupReconcileBtn");
      button.disabled = true;
      button.textContent = "Reconciling...";

      try {
        await apiJson("/api/admin/billing/sync", {
          method: "POST",
          body: {workspaceId, stripeId},
        });
        await loadClients();
      } catch (error) {
        alert(error.message || String(error));
        button.disabled = false;
        button.textContent = "Reconcile";
      }
    });
  }

  function boot() {
    injectStyle();
    ensureRoot();
    loadClients();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(boot, 500));
  } else {
    setTimeout(boot, 500);
  }

  window.SMX_RENDER_ADMIN_CLIENT_CLEANUP_STANDALONE = loadClients;
})();
// <<< SMX_ADMIN_CLEANUP_STANDALONE_V1 <<<

// >>> SMX_ADMIN_TABLE_FIT_NO_OVERFLOW >>>
(function smxAdminTableFitNoOverflow() {
  const STYLE_ID = "smx-admin-table-fit-no-overflow-style";

  function injectStyle() {
    const old = document.getElementById(STYLE_ID);
    if (old) old.remove();

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      /* Fix the actual admin cleanup table. No forced desktop/mobile hacks. */
      #smxAdminClientCleanupStandalone,
      .smx-admin-scale-shell {
        max-width: calc(100vw - 48px) !important;
        overflow: hidden !important;
      }

      #smxAdminClientCleanupStandalone .smx-table-wrap,
      .smx-admin-scale-shell #smxScaleBody {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: hidden !important;
        overflow-y: visible !important;
      }

      #smxAdminClientCleanupStandalone table,
      .smx-admin-scale-shell #smxScaleBody table {
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
        table-layout: fixed !important;
        border-collapse: collapse !important;
      }

      #smxAdminClientCleanupStandalone th,
      #smxAdminClientCleanupStandalone td,
      .smx-admin-scale-shell #smxScaleBody th,
      .smx-admin-scale-shell #smxScaleBody td {
        min-width: 0 !important;
        max-width: 1px !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(1),
      #smxAdminClientCleanupStandalone td:nth-child(1),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(1),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(1) {
        width: 18% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(2),
      #smxAdminClientCleanupStandalone td:nth-child(2),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(2),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(2) {
        width: 19% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(3),
      #smxAdminClientCleanupStandalone td:nth-child(3),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(3),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(3) {
        width: 8% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(4),
      #smxAdminClientCleanupStandalone td:nth-child(4),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(4),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(4) {
        width: 8% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(5),
      #smxAdminClientCleanupStandalone td:nth-child(5),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(5),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(5) {
        width: 9% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(6),
      #smxAdminClientCleanupStandalone td:nth-child(6),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(6),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(6) {
        width: 7% !important;
        text-align: center !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(7),
      #smxAdminClientCleanupStandalone td:nth-child(7),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(7),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(7) {
        width: 17% !important;
      }

      #smxAdminClientCleanupStandalone th:nth-child(8),
      #smxAdminClientCleanupStandalone td:nth-child(8),
      .smx-admin-scale-shell #smxScaleBody th:nth-child(8),
      .smx-admin-scale-shell #smxScaleBody td:nth-child(8) {
        width: 14% !important;
        position: static !important;
        right: auto !important;
        box-shadow: none !important;
      }

      #smxAdminClientCleanupStandalone .smx-actions,
      .smx-admin-scale-shell .smx-actions {
        display: flex !important;
        gap: 8px !important;
        justify-content: flex-end !important;
        min-width: 0 !important;
      }

      #smxAdminClientCleanupStandalone .smx-actions button,
      .smx-admin-scale-shell .smx-actions button,
      .smx-admin-scale-shell #smxScaleBody td:last-child button {
        min-width: 74px !important;
        width: auto !important;
        max-width: 92px !important;
        padding-left: 10px !important;
        padding-right: 10px !important;
        font-size: 14px !important;
      }

      #smxAdminClientCleanupStandalone .smx-small,
      .smx-admin-scale-shell .smx-small {
        display: inline-block !important;
        max-width: 100% !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        vertical-align: bottom !important;
      }

      @media (max-width: 900px) {
        #smxAdminClientCleanupStandalone .smx-table-wrap,
        .smx-admin-scale-shell #smxScaleBody {
          overflow-x: auto !important;
        }

        #smxAdminClientCleanupStandalone table,
        .smx-admin-scale-shell #smxScaleBody table {
          min-width: 980px !important;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function applyTitles() {
    const roots = [
      document.getElementById("smxAdminClientCleanupStandalone"),
      document.querySelector(".smx-admin-scale-shell"),
    ].filter(Boolean);

    roots.forEach((root) => {
      root.querySelectorAll("td, th, .smx-small, strong").forEach((node) => {
        const text = (node.textContent || "").trim();
        if (text && !node.getAttribute("title")) {
          node.setAttribute("title", text);
        }
      });
    });
  }

  function apply() {
    injectStyle();
    applyTitles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(apply, 300));
  } else {
    setTimeout(apply, 300);
  }

  setTimeout(apply, 1000);
  setTimeout(apply, 2200);

  const observer = new MutationObserver(() => {
    clearTimeout(window.__smxAdminTableFitTimer);
    window.__smxAdminTableFitTimer = setTimeout(applyTitles, 120);
  });

  observer.observe(document.documentElement, {childList: true, subtree: true});
})();
// <<< SMX_ADMIN_TABLE_FIT_NO_OVERFLOW <<<

// >>> SMX_ADMIN_CLEANUP_PARENT_WIDTH_FIX >>>
(function smxAdminCleanupParentWidthFix() {
  const STYLE_ID = "smx-admin-cleanup-parent-width-fix-style";

  function injectStyle() {
    const old = document.getElementById(STYLE_ID);
    if (old) old.remove();

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      /*
        The cleanup shell lives inside an existing admin page container.
        It must fit that parent, not calculate width from 100vw.
      */
      .smx-admin-scale-shell,
      #smxAdminClientCleanupStandalone {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        margin-left: 0 !important;
        margin-right: 0 !important;
        overflow: hidden !important;
      }

      .smx-admin-scale-shell {
        padding-left: clamp(18px, 2vw, 28px) !important;
        padding-right: clamp(18px, 2vw, 28px) !important;
      }

      .smx-admin-scale-head {
        width: 100% !important;
        max-width: 100% !important;
        grid-template-columns: minmax(0, 1fr) 132px !important;
      }

      #smxScaleTopRefresh,
      #smxScaleRefresh,
      #smxCleanupTopRefresh,
      #smxCleanupRefresh {
        width: 132px !important;
        max-width: 132px !important;
        min-width: 132px !important;
        padding-left: 10px !important;
        padding-right: 10px !important;
      }

      .smx-admin-scale-toolbar-wrap,
      .smx-admin-scale-toolbar-wrap > *,
      #smxScaleBody,
      .smx-table-wrap {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
      }

      .smx-admin-scale-toolbar-wrap > * {
        grid-template-columns: minmax(220px, 1fr) 190px 160px 132px !important;
      }

      #smxScaleBody table,
      #smxAdminClientCleanupStandalone table {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        table-layout: fixed !important;
      }

      #smxScaleBody th,
      #smxScaleBody td,
      #smxAdminClientCleanupStandalone th,
      #smxAdminClientCleanupStandalone td {
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
      }

      #smxScaleBody th:last-child,
      #smxScaleBody td:last-child,
      #smxAdminClientCleanupStandalone th:last-child,
      #smxAdminClientCleanupStandalone td:last-child {
        width: 150px !important;
        min-width: 150px !important;
        max-width: 150px !important;
        position: static !important;
        right: auto !important;
        box-shadow: none !important;
      }

      #smxScaleBody td:last-child button,
      #smxAdminClientCleanupStandalone td:last-child button {
        min-width: 64px !important;
        max-width: 76px !important;
        padding-left: 8px !important;
        padding-right: 8px !important;
        font-size: 13px !important;
      }

      .smx-admin-manual-sync,
      .smx-admin-sync-form,
      .smx-manual,
      .smx-manual-form {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
      }

      .smx-admin-sync-form,
      .smx-manual-form {
        grid-template-columns: minmax(180px, 0.8fr) minmax(240px, 1.2fr) 132px !important;
      }

      #smxScaleReconcileBtn,
      #smxCleanupReconcileBtn {
        width: 132px !important;
        max-width: 132px !important;
        min-width: 132px !important;
      }

      @media (max-width: 920px) {
        .smx-admin-scale-head,
        .smx-admin-scale-toolbar-wrap > *,
        .smx-admin-sync-form,
        .smx-manual-form {
          grid-template-columns: 1fr !important;
        }

        #smxScaleTopRefresh,
        #smxScaleRefresh,
        #smxCleanupTopRefresh,
        #smxCleanupRefresh,
        #smxScaleReconcileBtn,
        #smxCleanupReconcileBtn {
          width: 100% !important;
          max-width: 100% !important;
          min-width: 0 !important;
        }

        #smxScaleBody,
        .smx-table-wrap {
          overflow-x: auto !important;
        }

        #smxScaleBody table,
        #smxAdminClientCleanupStandalone table {
          min-width: 900px !important;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function applyTitles() {
    document
      .querySelectorAll(".smx-admin-scale-shell td, .smx-admin-scale-shell th, #smxAdminClientCleanupStandalone td, #smxAdminClientCleanupStandalone th")
      .forEach((node) => {
        const txt = (node.textContent || "").trim();
        if (txt && !node.title) node.title = txt;
      });
  }

  function apply() {
    injectStyle();
    applyTitles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(apply, 300));
  } else {
    setTimeout(apply, 300);
  }

  setTimeout(apply, 1000);
  setTimeout(apply, 2200);
})();
// <<< SMX_ADMIN_CLEANUP_PARENT_WIDTH_FIX <<<

// >>> SMX_MOBILE_SYSTEM_VOICE_LIST_GLOBAL_V3 >>>
(function smxMobileSystemVoiceListGlobalV3() {
  const STYLE_ID = "smx-mobile-system-voice-list-global-v3-style";
  const VOICE_NAME_RE = /\b[A-Za-z0-9][A-Za-z0-9 _.'-]{1,48}\s+\([MF]\)\b/;

  function textOf(node) {
    return (node && (node.innerText || node.textContent || "") || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function injectStyle() {
    const old = document.getElementById(STYLE_ID);
    if (old) old.remove();

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      @media (max-width: 820px) {
        [data-smx-system-voice-card-v3="true"] {
          display: grid !important;
          grid-template-columns: minmax(0, 1fr) 46px 46px !important;
          gap: 10px !important;
          align-items: center !important;
          padding: 12px 14px !important;
          min-height: 72px !important;
          height: auto !important;
        }

        [data-smx-system-voice-flatten-v3="true"] {
          display: contents !important;
        }

        [data-smx-system-voice-name-v3="true"] {
          grid-column: 1 !important;
          grid-row: 1 !important;
          min-width: 0 !important;
          max-width: 100% !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
          white-space: nowrap !important;
          font-size: 20px !important;
          line-height: 1.15 !important;
          margin: 0 !important;
          padding: 0 !important;
        }

        [data-smx-system-voice-play-v3="true"],
        [data-smx-system-voice-delete-v3="true"] {
          width: 46px !important;
          height: 46px !important;
          min-width: 46px !important;
          min-height: 46px !important;
          max-width: 46px !important;
          max-height: 46px !important;
          padding: 0 !important;
          margin: 0 !important;
          border-radius: 999px !important;
          display: inline-flex !important;
          align-items: center !important;
          justify-content: center !important;
          overflow: hidden !important;
          font-size: 0 !important;
          line-height: 0 !important;
        }

        [data-smx-system-voice-play-v3="true"] {
          grid-column: 2 !important;
          grid-row: 1 !important;
        }

        [data-smx-system-voice-delete-v3="true"] {
          grid-column: 3 !important;
          grid-row: 1 !important;
        }

        [data-smx-system-voice-play-v3="true"]::before {
          content: "▶" !important;
          font-size: 18px !important;
          line-height: 1 !important;
        }

        [data-smx-system-voice-delete-v3="true"]::before {
          content: "🗑" !important;
          font-size: 17px !important;
          line-height: 1 !important;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function isLikelyVoiceCard(node) {
    const text = textOf(node);

    if (!VOICE_NAME_RE.test(text)) return false;
    if (text.includes("System voices")) return false;
    if (text.includes("Create system voice")) return false;
    if (text.includes("Refresh system voices")) return false;
    if (text.includes("No system voice request")) return false;
    if (text.includes("Voice source duration")) return false;
    if (text.includes("Manual Stripe reconcile")) return false;

    const buttons = node.querySelectorAll("button");

    if (buttons.length < 2 || buttons.length > 4) return false;

    const rect = node.getBoundingClientRect();

    if (rect.width < 220 || rect.height < 60) return false;

    return true;
  }

  function findVoiceCards() {
    const candidates = Array.from(document.querySelectorAll("div, li, article"))
      .filter(isLikelyVoiceCard)
      .sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        return (textOf(a).length - textOf(b).length) || (ar.height - br.height);
      });

    const selected = [];

    candidates.forEach((node) => {
      if (selected.some((existing) => existing.contains(node) || node.contains(existing))) {
        return;
      }

      selected.push(node);
    });

    return selected;
  }

  function findNameNode(card) {
    return Array.from(card.querySelectorAll("h1,h2,h3,h4,strong,b,span,div"))
      .filter((node) => {
        const text = textOf(node);
        return VOICE_NAME_RE.test(text) && text.length <= 70;
      })
      .sort((a, b) => textOf(a).length - textOf(b).length)[0] || null;
  }

  function classifyButtons(card) {
    const buttons = Array.from(card.querySelectorAll("button"));

    const deleteBtn =
      buttons.find((button) => {
        const raw = `${textOf(button)} ${button.getAttribute("aria-label") || ""} ${button.title || ""}`.toLowerCase();
        return raw.includes("delete") || raw.includes("remove") || raw.includes("trash") || raw.includes("🗑");
      }) || buttons[buttons.length - 1] || null;

    const playBtn =
      buttons.find((button) => button !== deleteBtn) || buttons[0] || null;

    return {playBtn, deleteBtn};
  }

  function flattenParents(card, nodes) {
    nodes.forEach((node) => {
      let parent = node && node.parentElement;

      while (parent && parent !== card) {
        parent.setAttribute("data-smx-system-voice-flatten-v3", "true");
        parent = parent.parentElement;
      }
    });
  }

  function markCards() {
    findVoiceCards().forEach((card) => {
      const nameNode = findNameNode(card);
      const {playBtn, deleteBtn} = classifyButtons(card);

      if (!nameNode || !playBtn || !deleteBtn) return;

      card.setAttribute("data-smx-system-voice-card-v3", "true");

      nameNode.setAttribute("data-smx-system-voice-name-v3", "true");
      nameNode.title = textOf(nameNode);

      playBtn.setAttribute("data-smx-system-voice-play-v3", "true");
      playBtn.setAttribute("aria-label", playBtn.getAttribute("aria-label") || "Play preview");
      playBtn.title = playBtn.title || "Play preview";

      deleteBtn.setAttribute("data-smx-system-voice-delete-v3", "true");
      deleteBtn.setAttribute("aria-label", deleteBtn.getAttribute("aria-label") || "Delete voice");
      deleteBtn.title = deleteBtn.title || "Delete voice";

      flattenParents(card, [nameNode, playBtn, deleteBtn]);
    });
  }

  function apply() {
    injectStyle();
    markCards();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(apply, 300));
  } else {
    setTimeout(apply, 300);
  }

  setTimeout(apply, 900);
  setTimeout(apply, 1800);
  setTimeout(apply, 3200);

  const observer = new MutationObserver(() => {
    clearTimeout(window.__smxMobileSystemVoiceListGlobalV3Timer);
    window.__smxMobileSystemVoiceListGlobalV3Timer = setTimeout(apply, 120);
  });

  observer.observe(document.documentElement, {childList: true, subtree: true});
})();
// <<< SMX_MOBILE_SYSTEM_VOICE_LIST_GLOBAL_V3 <<<

