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

// >>> SMX_ADMIN_CLIENT_LIFECYCLE_UI >>>
(() => {
  "use strict";

  // >>> SMX_ADMIN_CLEANUP_AUTH_HOTFIX >>>
  let smxFirebaseConfigPromise = null;

  async function loadFirebaseConfig() {
    if (window.SMX_FIREBASE_CONFIG && window.SMX_FIREBASE_CONFIG.apiKey) {
      return window.SMX_FIREBASE_CONFIG;
    }

    if (window.__FIREBASE_CONFIG__ && window.__FIREBASE_CONFIG__.apiKey) {
      return window.__FIREBASE_CONFIG__;
    }

    if (!smxFirebaseConfigPromise) {
      smxFirebaseConfigPromise = fetch("/api/auth/firebase-config", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Accept": "application/json" }
      })
        .then((response) => response.json())
        .then((payload) => {
          const config = payload.firebaseConfig || payload.config || payload;

          if (!config || !config.apiKey) {
            throw new Error("Firebase config is missing apiKey.");
          }

          window.SMX_FIREBASE_CONFIG = config;
          return config;
        });
    }

    return smxFirebaseConfigPromise;
  }

  async function ensureFirebaseAuth(timeoutMs = 5000) {
    const started = Date.now();

    while (Date.now() - started < timeoutMs) {
      const fb = window.firebase || null;

      if (!fb || typeof fb.auth !== "function") {
        await new Promise((resolve) => setTimeout(resolve, 150));
        continue;
      }

      try {
        if (Array.isArray(fb.apps) && fb.apps.length === 0 && typeof fb.initializeApp === "function") {
          const config = await loadFirebaseConfig();
          fb.initializeApp(config);
        }

        return fb.auth();
      } catch (error) {
        const message = String(error && error.message ? error.message : error);

        if (
          message.includes("no-app") ||
          message.includes("No Firebase App") ||
          message.includes("DEFAULT")
        ) {
          try {
            const config = await loadFirebaseConfig();

            if (typeof fb.initializeApp === "function") {
              fb.initializeApp(config);
              return fb.auth();
            }
          } catch (_) {
            // Keep waiting briefly. The page may still be loading Firebase.
          }
        } else {
          console.warn("[SyntaxMatrix admin] Firebase auth not ready:", error);
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 150));
    }

    return null;
  }

  async function waitForFirebaseUser(timeoutMs = 5000) {
    const auth = await ensureFirebaseAuth(timeoutMs);

    if (!auth) {
      return null;
    }

    if (auth.currentUser && typeof auth.currentUser.getIdToken === "function") {
      return auth.currentUser;
    }

    return await new Promise((resolve) => {
      let done = false;

      const finish = (user) => {
        if (done) return;
        done = true;

        try {
          if (typeof unsubscribe === "function") unsubscribe();
        } catch (_) {
          // ignore
        }

        resolve(user || null);
      };

      let unsubscribe = null;

      try {
        unsubscribe = auth.onAuthStateChanged(
          (user) => finish(user),
          () => finish(null)
        );
      } catch (_) {
        finish(null);
      }

      setTimeout(() => finish(auth.currentUser || null), timeoutMs);
    });
  }

  async function ensureServerAdminSession() {
    const user = await waitForFirebaseUser();

    if (!user || typeof user.getIdToken !== "function") {
      return { ok: false, reason: "firebase_user_not_ready" };
    }

    const idToken = await user.getIdToken(true);

    if (!idToken) {
      return { ok: false, reason: "missing_id_token" };
    }

    const response = await fetch("/api/auth/session", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": `Bearer ${idToken}`
      },
      body: JSON.stringify({
        idToken,
        token: idToken,
        source: "admin_client_cleanup"
      })
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || payload.ok === false) {
      return {
        ok: false,
        reason: payload.error || payload.message || `${response.status} ${response.statusText}`
      };
    }

    return { ok: true, idToken };
  }

  async function authHeaders() {
    try {
      const user = await waitForFirebaseUser(1200);

      if (!user || typeof user.getIdToken !== "function") {
        return {};
      }

      const idToken = await user.getIdToken(false);

      return idToken ? { "Authorization": `Bearer ${idToken}` } : {};
    } catch (_) {
      return {};
    }
  }
  // <<< SMX_ADMIN_CLEANUP_AUTH_HOTFIX >>>

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[ch]));
  }

  function mountRoot() {
    let root = document.querySelector("#smxAdminClientLifecycle");

    if (root) return root;

    root = document.createElement("section");
    root.id = "smxAdminClientLifecycle";
    root.style.cssText = [
      "margin:24px auto",
      "max-width:1180px",
      "padding:18px",
      "border:1px solid rgba(126,163,255,.35)",
      "border-radius:18px",
      "background:rgba(10,24,38,.72)",
      "color:#eaf4ff"
    ].join(";");

    const main = document.querySelector("main") || document.body;
    main.prepend(root);

    return root;
  }

  async function getJson(url, options = {}) {
    const isAdminApi = String(url || "").includes("/api/admin/");
    const existingHeaders = options.headers || {};

    if (isAdminApi) {
      const session = await ensureServerAdminSession();

      if (!session.ok) {
        throw new Error(`Authentication required. Backend session was not created: ${session.reason}`);
      }
    }

    async function fetchOnce() {
      const bearerHeaders = await authHeaders();

      return fetch(url, {
        credentials: "same-origin",
        cache: "no-store",
        ...options,
        headers: {
          "Accept": "application/json",
          ...bearerHeaders,
          ...existingHeaders
        }
      });
    }

    let response = await fetchOnce();
    let payload = await response.json().catch(() => ({}));

    if (isAdminApi && (response.status === 401 || response.status === 403)) {
      const session = await ensureServerAdminSession();

      if (session.ok) {
        response = await fetchOnce();
        payload = await response.json().catch(() => ({}));
      }
    }

    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.message || `${response.status} ${response.statusText}`);
    }

    return payload;
  }

  async function postJson(url, body) {
    return getJson(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(body || {})
    });
  }

  function rowHtml(client) {
    const duplicate = client.duplicateEmail
      ? `<span style="color:#ffdc7a;font-weight:900;">Duplicate email</span>`
      : "";

    const stripeBlock = client.activeStripeSubscription
      ? `<span style="color:#ff9aa8;font-weight:900;">Cancel subscription first</span>`
      : "";

    const archiveButton = client.activeStripeSubscription
      ? `<button type="button" disabled style="opacity:.55;cursor:not-allowed;">Delete</button>`
      : `<button type="button" data-archive-workspace="${esc(client.workspaceId)}">Delete</button>`;

    return `
      <tr>
        <td>
          <strong>${esc(client.workspaceLabel || client.workspaceId)}</strong><br>
          <small>${esc(client.workspaceId)}</small>
        </td>
        <td>
          ${esc(client.billingEmail || "—")}<br>
          ${duplicate}
        </td>
        <td>${esc(client.planKey || "free")}</td>
        <td>${esc(client.subscriptionStatus || "active")}</td>
        <td>${esc(client.provider || "internal")}</td>
        <td>${client.memberCount ?? 0}</td>
        <td>${stripeBlock || "—"}</td>
        <td style="white-space:nowrap;">
          ${archiveButton}
          <button type="button" data-sync-workspace="${esc(client.workspaceId)}">Sync billing</button>
        </td>
      </tr>
    `;
  }

  async function render() {
    const root = mountRoot();

    root.innerHTML = `
      <div style="display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:14px;">
        <div>
          <h2 style="margin:0 0 6px;">Admin Client Cleanup</h2>
          <p style="margin:0;color:#bcd3ee;">Archive old duplicate clients and sync billing after Stripe checkout.</p>
        </div>
        <button type="button" id="smxRefreshClientLifecycle">Refresh</button>
      </div>
      <div id="smxClientLifecycleBody">Loading clients...</div>
    `;

    const body = root.querySelector("#smxClientLifecycleBody");

    try {
      const payload = await getJson(`/api/admin/client-lifecycle?t=${Date.now()}`);
      const clients = payload.clients || [];

      body.innerHTML = `
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="text-align:left;color:#aee9ff;">
              <th>Workspace</th>
              <th>Email</th>
              <th>Plan</th>
              <th>Subscription</th>
              <th>Provider</th>
              <th>Members</th>
              <th>Blocker</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${clients.length ? clients.map(rowHtml).join("") : `<tr><td colspan="8">No active clients found.</td></tr>`}
          </tbody>
        </table>
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(126,163,255,.25);">
          <strong>Manual Stripe reconcile</strong>
          <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:10px;margin-top:10px;">
            <input id="smxReconcileWorkspaceId" placeholder="workspaceId">
            <input id="smxReconcileSessionId" placeholder="Stripe checkout session id, cs_...">
            <button type="button" id="smxReconcileSessionBtn">Reconcile session</button>
          </div>
        </div>
      `;

      root.querySelectorAll("[data-archive-workspace]").forEach((button) => {
        button.addEventListener("click", async () => {
          const workspaceId = button.getAttribute("data-archive-workspace");

          if (!window.confirm(`Delete/archive client workspace ${workspaceId}? This hides it from active admin lists. Active Stripe subscriptions are blocked.`)) {
            return;
          }

          button.disabled = true;
          button.textContent = "Deleting...";

          try {
            await postJson(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/archive`, {
              reason: "admin_duplicate_cleanup"
            });
            await render();
          } catch (error) {
            alert(error.message);
            button.disabled = false;
            button.textContent = "Delete";
          }
        });
      });

      root.querySelectorAll("[data-sync-workspace]").forEach((button) => {
        button.addEventListener("click", async () => {
          const workspaceId = button.getAttribute("data-sync-workspace");

          button.disabled = true;
          button.textContent = "Syncing...";

          try {
            await postJson("/api/admin/billing/sync", { workspaceId });
            await render();
          } catch (error) {
            alert(error.message);
            button.disabled = false;
            button.textContent = "Sync billing";
          }
        });
      });

      const reconcileBtn = root.querySelector("#smxReconcileSessionBtn");

      if (reconcileBtn) {
        reconcileBtn.addEventListener("click", async () => {
          const workspaceId = root.querySelector("#smxReconcileWorkspaceId").value.trim();
          const sessionId = root.querySelector("#smxReconcileSessionId").value.trim();

          if (!workspaceId || !sessionId) {
            alert("workspaceId and checkout session id are required.");
            return;
          }

          reconcileBtn.disabled = true;
          reconcileBtn.textContent = "Reconciling...";

          try {
            await postJson("/api/admin/billing/sync", { workspaceId, stripeId: sessionId });
            await render();
          } catch (error) {
            alert(error.message);
            reconcileBtn.disabled = false;
            reconcileBtn.textContent = "Reconcile session";
          }
        });
      }
    } catch (error) {
      body.innerHTML = `<p style="color:#ff9aa8;">${esc(error.message)}</p>`;
    }

    const refresh = root.querySelector("#smxRefreshClientLifecycle");

    if (refresh) {
      refresh.addEventListener("click", render);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(render, 900);
  });
})();
// <<< SMX_ADMIN_CLIENT_LIFECYCLE_UI <<<
// >>> SMX_ADMIN_CLIENT_CLEANUP_SCALABLE_UI >>>
(() => {
  "use strict";

  const STYLE_ID = "smxAdminClientCleanupScalableStyle";

  const state = {
    clients: [],
    duplicates: {},
    query: "",
    filter: "all",
    page: 1,
    pageSize: 25,
    loading: false,
    searchRenderTimer: null,
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[ch]));
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #smxAdminClientLifecycle {
        width: min(1220px, calc(100vw - 44px)) !important;
        max-width: 1220px !important;
        margin: 32px auto 42px !important;
        padding: 0 !important;
        border: 1px solid rgba(139, 188, 255, .28) !important;
        border-radius: 22px !important;
        background: linear-gradient(135deg, rgba(8, 22, 36, .98), rgba(7, 16, 29, .96)) !important;
        color: #effaff !important;
        box-shadow: 0 24px 70px rgba(0, 0, 0, .24) !important;
        overflow: hidden !important;
      }

      .smx-admin-scale-shell {
        padding: 22px;
      }

      .smx-admin-scale-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 18px;
        margin-bottom: 16px;
      }

      .smx-admin-scale-kicker {
        margin: 0 0 6px;
        color: #9ff7eb;
        letter-spacing: .12em;
        text-transform: uppercase;
        font-size: 12px;
        font-weight: 950;
      }

      .smx-admin-scale-title {
        margin: 0;
        font-size: clamp(26px, 3vw, 38px);
        line-height: 1.04;
        font-weight: 950;
      }

      .smx-admin-scale-subtitle {
        margin: 8px 0 0;
        color: #bad4f0;
        line-height: 1.45;
        max-width: 760px;
      }

      .smx-admin-scale-btn {
        border: 0;
        border-radius: 999px;
        min-height: 38px;
        padding: 9px 14px;
        font-weight: 950;
        cursor: pointer;
        color: #061523;
        background: linear-gradient(135deg, #a3f3ee, #85b7ff);
        white-space: nowrap;
      }

      .smx-admin-scale-btn:hover {
        transform: translateY(-1px);
      }

      .smx-admin-scale-btn:disabled {
        opacity: .45;
        cursor: not-allowed;
        transform: none;
      }

      .smx-admin-scale-danger {
        background: linear-gradient(135deg, #ffd0d7, #ff8fa3);
      }

      .smx-admin-scale-ghost {
        background: rgba(255,255,255,.07);
        color: #dff6ff;
        border: 1px solid rgba(155,205,255,.23);
      }

      .smx-admin-scale-stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin: 14px 0 16px;
      }

      .smx-admin-scale-stat {
        border: 1px solid rgba(151, 201, 255, .21);
        border-radius: 16px;
        padding: 12px 13px;
        background: rgba(255,255,255,.045);
      }

      .smx-admin-scale-stat-label {
        color: #9fb7d4;
        font-size: 11px;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .06em;
      }

      .smx-admin-scale-stat-value {
        margin-top: 5px;
        font-size: 22px;
        font-weight: 950;
      }

      .smx-admin-scale-toolbar {
        display: grid;
        grid-template-columns: minmax(240px, 1.3fr) 160px 140px auto;
        gap: 10px;
        align-items: center;
        margin: 16px 0;
      }

      .smx-admin-scale-input,
      .smx-admin-scale-select {
        min-height: 42px;
        border-radius: 13px;
        border: 1px solid rgba(143, 196, 255, .24);
        background: rgba(2, 10, 19, .82);
        color: #effaff;
        padding: 0 13px;
        outline: none;
        font-weight: 750;
      }

      .smx-admin-scale-input::placeholder {
        color: #829ab5;
      }

      .smx-admin-table-wrap {
        border: 1px solid rgba(145,198,255,.20);
        border-radius: 17px;
        overflow: auto;
        max-height: min(620px, 62vh);
        background: rgba(2,10,19,.45);
      }

      .smx-admin-client-table {
        width: 100%;
        min-width: 980px;
        border-collapse: collapse;
      }

      .smx-admin-client-table thead th {
        position: sticky;
        top: 0;
        z-index: 2;
        background: rgba(7, 18, 31, .98);
        color: #aee9ff;
        text-align: left;
        font-size: 11px;
        letter-spacing: .06em;
        text-transform: uppercase;
        padding: 12px 12px;
        border-bottom: 1px solid rgba(145,198,255,.22);
        white-space: nowrap;
      }

      .smx-admin-client-table tbody td {
        padding: 12px;
        border-bottom: 1px solid rgba(145,198,255,.11);
        vertical-align: middle;
        font-size: 13px;
      }

      .smx-admin-client-table tbody tr:hover {
        background: rgba(126, 190, 255, .06);
      }

      .smx-admin-main-cell strong {
        display: block;
        font-size: 14px;
        color: #f5fbff;
        margin-bottom: 3px;
      }

      .smx-admin-muted {
        color: #93aeca;
        font-size: 12px;
        word-break: break-all;
      }

      .smx-admin-email {
        font-weight: 850;
        color: #effaff;
      }

      .smx-admin-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 5px 8px;
        font-size: 11px;
        line-height: 1;
        font-weight: 950;
        color: #061523;
        background: #b8f6ff;
        white-space: nowrap;
      }

      .smx-admin-badge-plan {
        background: #b9f4ce;
      }

      .smx-admin-badge-warning {
        background: #ffdc7a;
      }

      .smx-admin-badge-danger {
        background: #ff9aa8;
      }

      .smx-admin-row-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        justify-content: flex-end;
      }

      .smx-admin-row-actions .smx-admin-scale-btn {
        min-height: 34px;
        padding: 7px 11px;
        font-size: 12px;
      }

      .smx-admin-scale-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-top: 14px;
        color: #b7cbe3;
        font-size: 13px;
      }

      .smx-admin-page-controls {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .smx-admin-manual-sync {
        margin-top: 18px;
        border-top: 1px solid rgba(145,198,255,.18);
        padding-top: 16px;
      }

      .smx-admin-manual-sync h3 {
        margin: 0 0 5px;
        font-size: 17px;
      }

      .smx-admin-manual-sync p {
        margin: 0 0 12px;
        color: #b7cbe3;
        font-size: 13px;
      }

      .smx-admin-sync-form {
        display: grid;
        grid-template-columns: minmax(180px, .8fr) minmax(260px, 1.4fr) auto;
        gap: 10px;
      }

      .smx-admin-empty,
      .smx-admin-error {
        border: 1px dashed rgba(157,207,255,.32);
        border-radius: 16px;
        padding: 22px;
        color: #c6d9ef;
        text-align: center;
      }

      .smx-admin-error {
        border-style: solid;
        border-color: rgba(255,154,168,.48);
        background: rgba(255,82,112,.08);
        color: #ffd4da;
        text-align: left;
        font-weight: 850;
      }

      @media (max-width: 920px) {
        .smx-admin-scale-head,
        .smx-admin-scale-footer {
          flex-direction: column;
          align-items: stretch;
        }

        .smx-admin-scale-stats,
        .smx-admin-scale-toolbar,
        .smx-admin-sync-form {
          grid-template-columns: 1fr;
        }

        .smx-admin-table-wrap {
          max-height: 70vh;
        }
      }
    `;

    document.head.appendChild(style);
  }

  async function authHeaders() {
    try {
      const fb = window.firebase || null;

      if (!fb || typeof fb.auth !== "function") return {};

      const auth = fb.auth();
      const user = auth.currentUser;

      if (!user || typeof user.getIdToken !== "function") return {};

      const token = await user.getIdToken(false);

      return token ? { "Authorization": `Bearer ${token}` } : {};
    } catch (_) {
      return {};
    }
  }

  async function getJson(url, options = {}) {
    const headers = {
      "Accept": "application/json",
      ...(await authHeaders()),
      ...(options.headers || {})
    };

    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.message || `${response.status} ${response.statusText}`);
    }

    return payload;
  }

  async function postJson(url, body) {
    return getJson(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body || {})
    });
  }

  function mountRoot() {
    let root = document.querySelector("#smxAdminClientLifecycle");

    if (!root) {
      root = document.createElement("section");
      root.id = "smxAdminClientLifecycle";
      const main = document.querySelector("main") || document.body;
      main.prepend(root);
    }

    return root;
  }

  function normalise(value) {
    return String(value || "").toLowerCase().trim();
  }

  function isPaid(client) {
    return normalise(client.planKey) !== "free";
  }

  function filteredClients() {
    const q = normalise(state.query);

    let rows = state.clients.slice();

    if (state.filter === "free") {
      rows = rows.filter((client) => normalise(client.planKey) === "free");
    } else if (state.filter === "paid") {
      rows = rows.filter((client) => normalise(client.planKey) !== "free");
    } else if (state.filter === "duplicates") {
      rows = rows.filter((client) => Boolean(client.duplicateEmail));
    }

    if (q) {
      rows = rows.filter((client) => {
        const haystack = [
          client.workspaceLabel,
          client.workspaceId,
          client.billingEmail,
          client.planKey,
          client.subscriptionStatus,
          client.provider,
          client.stripeSubscriptionId,
          client.customerId
        ].map(normalise).join(" ");

        return haystack.includes(q);
      });
    }

    return rows;
  }

  function stats() {
    const clients = state.clients;
    return {
      total: clients.length,
      duplicates: Object.keys(state.duplicates || {}).length,
      free: clients.filter((client) => normalise(client.planKey) === "free").length,
      paid: clients.filter(isPaid).length,
    };
  }

  function statsHtml() {
    const s = stats();

    return `
      <div class="smx-admin-scale-stats">
        <div class="smx-admin-scale-stat">
          <div class="smx-admin-scale-stat-label">Active clients</div>
          <div class="smx-admin-scale-stat-value">${s.total}</div>
        </div>
        <div class="smx-admin-scale-stat">
          <div class="smx-admin-scale-stat-label">Duplicate emails</div>
          <div class="smx-admin-scale-stat-value">${s.duplicates}</div>
        </div>
        <div class="smx-admin-scale-stat">
          <div class="smx-admin-scale-stat-label">Free</div>
          <div class="smx-admin-scale-stat-value">${s.free}</div>
        </div>
        <div class="smx-admin-scale-stat">
          <div class="smx-admin-scale-stat-label">Paid / legacy</div>
          <div class="smx-admin-scale-stat-value">${s.paid}</div>
        </div>
      </div>
    `;
  }

  function toolbarHtml() {
    return `
      <div class="smx-admin-scale-toolbar">
        <input class="smx-admin-scale-input" id="smxScaleSearch" placeholder="Search email, workspace, plan, provider..." value="${esc(state.query)}">
        <select class="smx-admin-scale-select" id="smxScaleFilter">
          <option value="all" ${state.filter === "all" ? "selected" : ""}>All active</option>
          <option value="free" ${state.filter === "free" ? "selected" : ""}>Free only</option>
          <option value="paid" ${state.filter === "paid" ? "selected" : ""}>Paid / legacy</option>
          <option value="duplicates" ${state.filter === "duplicates" ? "selected" : ""}>Duplicates</option>
        </select>
        <select class="smx-admin-scale-select" id="smxScalePageSize">
          ${[10, 25, 50, 100].map((size) => `
            <option value="${size}" ${state.pageSize === size ? "selected" : ""}>${size} / page</option>
          `).join("")}
        </select>
        <button type="button" class="smx-admin-scale-btn" id="smxScaleRefresh">Refresh</button>
      </div>
    `;
  }

  function rowHtml(client) {
    const duplicate = Boolean(client.duplicateEmail);
    const activeStripe = Boolean(client.activeStripeSubscription);
    const plan = String(client.planKey || "free");
    const status = String(client.subscriptionStatus || "active");

    const deleteButton = activeStripe
      ? `<button type="button" class="smx-admin-scale-btn smx-admin-scale-danger" disabled>Blocked</button>`
      : `<button type="button" class="smx-admin-scale-btn smx-admin-scale-danger" data-scale-archive="${esc(client.workspaceId)}">Delete</button>`;

    return `
      <tr>
        <td class="smx-admin-main-cell">
          <strong>${esc(client.workspaceLabel || "Client workspace")}</strong>
          <div class="smx-admin-muted">${esc(client.workspaceId || "")}</div>
        </td>
        <td>
          <div class="smx-admin-email">${esc(client.billingEmail || "—")}</div>
          ${duplicate ? `<span class="smx-admin-badge smx-admin-badge-warning">Duplicate</span>` : ""}
        </td>
        <td><span class="smx-admin-badge smx-admin-badge-plan">${esc(plan)}</span></td>
        <td><span class="smx-admin-badge">${esc(status)}</span></td>
        <td>${esc(client.provider || "internal")}</td>
        <td>${esc(client.memberCount ?? 0)}</td>
        <td>
          <div class="smx-admin-muted">${esc(client.stripeSubscriptionId || "—")}</div>
        </td>
        <td>
          <div class="smx-admin-row-actions">
            ${deleteButton}
            <button type="button" class="smx-admin-scale-btn smx-admin-scale-ghost" data-scale-sync="${esc(client.workspaceId)}">Sync</button>
          </div>
        </td>
      </tr>
    `;
  }

  function tableHtml(rows) {
    if (!rows.length) {
      return `<div class="smx-admin-empty">No clients match the current filter.</div>`;
    }

    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));

    if (state.page > totalPages) state.page = totalPages;
    if (state.page < 1) state.page = 1;

    const start = (state.page - 1) * state.pageSize;
    const pageRows = rows.slice(start, start + state.pageSize);

    return `
      <div class="smx-admin-table-wrap">
        <table class="smx-admin-client-table">
          <thead>
            <tr>
              <th>Workspace</th>
              <th>Email</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Provider</th>
              <th>Members</th>
              <th>Stripe subscription</th>
              <th style="text-align:right;">Actions</th>
            </tr>
          </thead>
          <tbody>
            ${pageRows.map(rowHtml).join("")}
          </tbody>
        </table>
      </div>

      <div class="smx-admin-scale-footer">
        <div>
          Showing <strong>${rows.length ? start + 1 : 0}</strong>–<strong>${Math.min(start + state.pageSize, rows.length)}</strong>
          of <strong>${rows.length}</strong> filtered clients
        </div>
        <div class="smx-admin-page-controls">
          <button type="button" class="smx-admin-scale-btn smx-admin-scale-ghost" id="smxScalePrev" ${state.page <= 1 ? "disabled" : ""}>Prev</button>
          <span>Page <strong>${state.page}</strong> of <strong>${totalPages}</strong></span>
          <button type="button" class="smx-admin-scale-btn smx-admin-scale-ghost" id="smxScaleNext" ${state.page >= totalPages ? "disabled" : ""}>Next</button>
        </div>
      </div>
    `;
  }

  function shellHtml(bodyHtml) {
    return `
      <div class="smx-admin-scale-shell">
        <div class="smx-admin-scale-head">
          <div>
            <p class="smx-admin-scale-kicker">SyntaxMatrix Admin</p>
            <h2 class="smx-admin-scale-title">Client Cleanup</h2>
            <p class="smx-admin-scale-subtitle">
              Use search, filters and pagination to manage many client workspaces without crowding the page.
            </p>
          </div>
          <button type="button" class="smx-admin-scale-btn" id="smxScaleTopRefresh">Refresh</button>
        </div>

        ${statsHtml()}
        ${toolbarHtml()}
        <div id="smxScaleBody">${bodyHtml}</div>

        <div class="smx-admin-manual-sync">
          <h3>Manual Stripe reconcile</h3>
          <p>Use this when Stripe payment succeeded but the local workspace plan did not update. Paste cs_, sub_, pi_, or cus_. Paste cs_, sub_, pi_, or cus_. Paste cs_, sub_, pi_, or cus_.</p>
          <div class="smx-admin-sync-form">
            <input class="smx-admin-scale-input" id="smxScaleReconcileWorkspaceId" placeholder="Workspace ID">
            <input class="smx-admin-scale-input" id="smxScaleReconcileSessionId" placeholder="Stripe ID: cs_, sub_, pi_, or cus_...">
            <button type="button" class="smx-admin-scale-btn" id="smxScaleReconcileBtn">Reconcile</button>
          </div>
        </div>
      </div>
    `;
  }

  function bindEvents(root) {
    root.querySelector("#smxScaleTopRefresh")?.addEventListener("click", loadAndRender);
    root.querySelector("#smxScaleRefresh")?.addEventListener("click", loadAndRender);

    root.querySelector("#smxScaleSearch")?.addEventListener("input", (event) => {
      state.query = event.target.value || "";
      state.page = 1;

      const cursorPosition =
        typeof event.target.selectionStart === "number"
          ? event.target.selectionStart
          : state.query.length;

      if (state.searchRenderTimer) {
        clearTimeout(state.searchRenderTimer);
      }

      state.searchRenderTimer = setTimeout(() => {
        renderFromState({
          focusSearch: true,
          cursorPosition,
        });
      }, 180);
    });

    root.querySelector("#smxScaleFilter")?.addEventListener("change", (event) => {
      state.filter = event.target.value || "all";
      state.page = 1;
      renderFromState();
    });

    root.querySelector("#smxScalePageSize")?.addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value || 25) || 25;
      state.page = 1;
      renderFromState();
    });

    root.querySelector("#smxScalePrev")?.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      renderFromState();
    });

    root.querySelector("#smxScaleNext")?.addEventListener("click", () => {
      state.page += 1;
      renderFromState();
    });

    root.querySelectorAll("[data-scale-archive]").forEach((button) => {
      button.addEventListener("click", async () => {
        const workspaceId = button.getAttribute("data-scale-archive");

        if (!window.confirm(`Delete/archive this client workspace?\n\n${workspaceId}\n\nThis is a soft delete.`)) {
          return;
        }

        button.disabled = true;
        button.textContent = "Deleting...";

        try {
          await postJson(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}/archive`, {
            reason: "admin_client_cleanup"
          });
          await loadAndRender();
        } catch (error) {
          alert(error.message);
          button.disabled = false;
          button.textContent = "Delete";
        }
      });
    });

    root.querySelectorAll("[data-scale-sync]").forEach((button) => {
      button.addEventListener("click", async () => {
        const workspaceId = button.getAttribute("data-scale-sync");

        button.disabled = true;
        button.textContent = "Syncing...";

        try {
          await postJson("/api/admin/billing/sync", { workspaceId });
          await loadAndRender();
        } catch (error) {
          alert(error.message);
          button.disabled = false;
          button.textContent = "Sync";
        }
      });
    });

    root.querySelector("#smxScaleReconcileBtn")?.addEventListener("click", async () => {
      const workspaceId = root.querySelector("#smxScaleReconcileWorkspaceId")?.value?.trim() || "";
      const sessionId = root.querySelector("#smxScaleReconcileSessionId")?.value?.trim() || "";

      if (!workspaceId || !sessionId) {
        alert("Workspace ID and Stripe ID are required. Use cs_, sub_, pi_, or cus_.");
        return;
      }

      const button = root.querySelector("#smxScaleReconcileBtn");
      button.disabled = true;
      button.textContent = "Reconciling...";

      try {
        await postJson("/api/admin/billing/sync", { workspaceId, stripeId: sessionId });
        await loadAndRender();
      } catch (error) {
        alert(error.message);
        button.disabled = false;
        button.textContent = "Reconcile";
      }
    });
  }

  function renderFromState(options = {}) {
    injectStyle();

    const root = mountRoot();
    const rows = filteredClients();

    root.innerHTML = shellHtml(tableHtml(rows));
    bindEvents(root);

    if (options.focusSearch) {
      const input = root.querySelector("#smxScaleSearch");

      if (input) {
        const pos = Math.min(
          Number.isFinite(options.cursorPosition) ? options.cursorPosition : input.value.length,
          input.value.length
        );

        input.focus();

        try {
          input.setSelectionRange(pos, pos);
        } catch (_) {
          // Some browsers/input types may not support selection range.
        }
      }
    }
  }

  async function loadAndRender() {
    injectStyle();

    const root = mountRoot();
    root.innerHTML = shellHtml(`<div class="smx-admin-empty">Loading clients...</div>`);
    bindEvents(root);

    try {
      const payload = await getJson(`/api/admin/client-lifecycle?t=${Date.now()}`);

      state.clients = payload.clients || [];
      state.duplicates = payload.duplicates || {};
      state.page = 1;

      renderFromState();
    } catch (error) {
      root.innerHTML = shellHtml(`<div class="smx-admin-error">${esc(error.message || error)}</div>`);
      bindEvents(root);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(loadAndRender, 1900);
  });

  window.SMX_RENDER_ADMIN_CLIENT_CLEANUP_SCALABLE = loadAndRender;
})();
// <<< SMX_ADMIN_CLIENT_CLEANUP_SCALABLE_UI <<<
