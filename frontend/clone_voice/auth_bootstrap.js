(() => {
  if (window.__SYNTAXMATRIX_AUTH_BOOTSTRAPPED__) {
    return;
  }

  window.__SYNTAXMATRIX_AUTH_BOOTSTRAPPED__ = true;

  const originalFetch = window.fetch.bind(window);
  let authReadyPromise = null;
  let cachedToken = "";
  let cachedTokenAt = 0;

  function isAuthPage() {
    return window.location.pathname === "/auth" || window.location.pathname === "/auth/";
  }


  async function clearServerSession() {
    try {
      await originalFetch("/api/auth/session", { method: "DELETE", cache: "no-store" });
    } catch (error) {
      console.warn("[SyntaxMatrix auth] Could not clear server session:", error);
    }
  }

  function authRedirect() {
    const next = encodeURIComponent(window.location.pathname + window.location.search + window.location.hash);
    window.location.assign(`/auth?next=${next}`);
  }

  function shouldAttachAuth(input) {
    const rawUrl = typeof input === "string" ? input : input && input.url ? input.url : "";
    if (!rawUrl) {
      return false;
    }

    const url = new URL(rawUrl, window.location.origin);

    if (url.origin !== window.location.origin) {
      return false;
    }

    if (url.pathname === "/api/auth/firebase-config") {
      return false;
    }

    return url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/workspaces/");
  }

  async function loadFirebaseConfig() {
    const response = await originalFetch(`/api/auth/firebase-config?t=${Date.now()}`, {
      cache: "no-store"
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.error || "Firebase configuration is not available.");
    }

    return payload.firebaseConfig;
  }

  async function waitForUser(auth) {
    return new Promise((resolve) => {
      const unsubscribe = auth.onAuthStateChanged((user) => {
        unsubscribe();
        resolve(user);
      });
    });
  }



  function clearLegacyMockWorkspaceState() {
    const legacyValues = [
      "mock_user_001",
      "mock_user_002",
      "dev_admin",
      "dev_client_001",
      "dev_client_002"
    ];

    function valueLooksLegacy(value) {
      const text = String(value || "");
      return legacyValues.some((legacy) => text.includes(legacy));
    }

    for (const storage of [window.localStorage, window.sessionStorage]) {
      if (!storage) {
        continue;
      }

      const keysToRemove = [];

      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        if (!key) {
          continue;
        }

        let value = "";
        try {
          value = storage.getItem(key) || "";
        } catch (error) {
          value = "";
        }

        if (valueLooksLegacy(key) || valueLooksLegacy(value)) {
          keysToRemove.push(key);
        }
      }

      for (const key of keysToRemove) {
        try {
          storage.removeItem(key);
          console.info("[SyntaxMatrix auth] Removed legacy workspace state:", key);
        } catch (error) {
          console.warn("[SyntaxMatrix auth] Could not remove legacy workspace state:", key, error);
        }
      }
    }
  }

  async function ensureFirebaseWorkspaceSelected(user) {
    const token = await user.getIdToken(false);

    const response = await originalFetch(`/api/clone-voice/workspaces?t=${Date.now()}`, {
      cache: "no-store",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.error || "Could not load your workspace.");
    }

    const rows = Array.isArray(payload.workspaces) ? payload.workspaces : [];
    const selected =
      payload.defaultWorkspaceId ||
      (rows[0] && rows[0].workspaceId) ||
      "";

    if (!selected || selected.startsWith("mock_user_")) {
      throw new Error("A valid Firebase workspace was not selected.");
    }

    window.SyntaxMatrixWorkspace = {
      defaultWorkspaceId: selected,
      workspaces: rows
    };

    return payload;
  }

  async function bootstrapAccountForUser(user) {
    const token = await user.getIdToken(false);

    const response = await originalFetch("/api/account/bootstrap", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({})
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.error || "Could not prepare account workspace.");
    }

    return payload;
  }

  async function initialiseAuth() {
    if (!window.firebase || !window.firebase.auth) {
      throw new Error("Firebase browser SDK failed to load.");
    }

    const config = await loadFirebaseConfig();

    if (!window.firebase.apps.length) {
      window.firebase.initializeApp(config);
    }

    const auth = window.firebase.auth();

    // >>> SMX_BOOTSTRAP_LOCAL_PERSISTENCE_FOR_STRIPE_RETURN >>>
    // Protected pages must preserve the logged-in Firebase user across Stripe redirects.
    try {
      await auth.setPersistence(window.firebase.auth.Auth.Persistence.LOCAL);
    } catch (error) {
      console.warn("[SyntaxMatrix auth] Could not set local Firebase persistence:", error);
    }
    // <<< SMX_BOOTSTRAP_LOCAL_PERSISTENCE_FOR_STRIPE_RETURN <<<
    const user = await waitForUser(auth);

    if (!user) {
      if (!isAuthPage()) {
        authRedirect();
      }
      throw new Error("Authentication required.");
    }

    clearLegacyMockWorkspaceState();
    await bootstrapAccountForUser(user);
    await ensureFirebaseWorkspaceSelected(user);

    window.SyntaxMatrixAuth = {
      auth,
      getUser: () => auth.currentUser,
      getIdToken: async (forceRefresh = false) => {
        const current = auth.currentUser;
        if (!current) {
          authRedirect();
          throw new Error("Authentication required.");
        }
        return current.getIdToken(forceRefresh);
      },
      signOut: async () => {
        await clearServerSession();
        await auth.signOut();
        authRedirect();
      }
    };

    injectAccountBadge(auth);
    installAuthenticatedMediaResolver(auth);

    auth.onAuthStateChanged((current) => {
      if (!current && !isAuthPage()) {
        authRedirect();
      }
    });

    return auth;
  }


  function installAuthenticatedMediaResolver(auth) {
    const protectedPrefix = "/media/workspaces/";
    const objectUrls = new Map();

    function isProtectedMediaUrl(value) {
      if (!value || String(value).startsWith("blob:")) {
        return false;
      }

      try {
        const url = new URL(value, window.location.origin);
        return url.origin === window.location.origin && url.pathname.startsWith(protectedPrefix);
      } catch (error) {
        return false;
      }
    }

    async function resolveProtectedMediaElement(element, attrName) {
      const originalUrl = element.getAttribute(attrName);

      if (!isProtectedMediaUrl(originalUrl)) {
        return;
      }

      const currentKey = `${attrName}:${originalUrl}`;

      if (element.dataset.smxResolvedMediaKey === currentKey) {
        return;
      }

      element.dataset.smxResolvedMediaKey = currentKey;

      try {
        const user = auth.currentUser;

        if (!user) {
          throw new Error("Authentication required for media playback.");
        }

        const token = await user.getIdToken(false);
        const absoluteUrl = new URL(originalUrl, window.location.origin).toString();

        let objectUrl = objectUrls.get(absoluteUrl);

        if (!objectUrl) {
          const response = await originalFetch(absoluteUrl, {
            cache: "no-store",
            headers: {
              "Authorization": `Bearer ${token}`
            }
          });

          if (!response.ok) {
            const text = await response.text().catch(() => "");
            throw new Error(`Protected media fetch failed: ${response.status} ${text.slice(0, 180)}`);
          }

          const blob = await response.blob();

          if (!blob.size) {
            throw new Error("Protected media response was empty.");
          }

          objectUrl = URL.createObjectURL(blob);
          objectUrls.set(absoluteUrl, objectUrl);
        }

        element.dataset.smxOriginalMediaUrl = originalUrl;
        element.setAttribute(attrName, objectUrl);

        if (element.tagName === "A") {
          const existingDownload = element.getAttribute("download");
          if (!existingDownload) {
            const fileName = originalUrl.split("/").pop() || "syntaxmatrix-audio.wav";
            element.setAttribute("download", fileName);
          }
        }

        if (element.tagName === "AUDIO" || element.tagName === "VIDEO") {
          element.load();
        }

        console.info("[SyntaxMatrix auth] Protected media resolved:", originalUrl);
      } catch (error) {
        console.error("[SyntaxMatrix auth] Could not resolve protected media:", originalUrl, error);
      }
    }

    function scanProtectedMedia() {
      const mediaElements = [
        ...document.querySelectorAll("audio[src], video[src], source[src]")
      ];

      for (const element of mediaElements) {
        resolveProtectedMediaElement(element, "src");
      }

      const downloadLinks = [
        ...document.querySelectorAll("a[href]")
      ];

      for (const element of downloadLinks) {
        resolveProtectedMediaElement(element, "href");
      }
    }

    const observer = new MutationObserver(() => {
      scanProtectedMedia();
    });

    function start() {
      scanProtectedMedia();

      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["src", "href"]
      });

      window.setInterval(scanProtectedMedia, 1500);
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
  }


  function injectAccountBadge(auth) {
    if (document.getElementById("smxAuthBadge")) {
      return;
    }

    const user = auth.currentUser;
    if (!user) {
      return;
    }

    const badge = document.createElement("div");
    badge.id = "smxAuthBadge";
    badge.style.position = "fixed";
    badge.style.right = "16px";
    badge.style.bottom = "16px";
    badge.style.zIndex = "99999";
    badge.style.display = "flex";
    badge.style.alignItems = "center";
    badge.style.gap = "10px";
    badge.style.padding = "10px 12px";
    badge.style.borderRadius = "999px";
    badge.style.background = "rgba(7, 17, 31, 0.90)";
    badge.style.color = "#eef5ff";
    badge.style.boxShadow = "0 14px 34px rgba(0,0,0,0.26)";
    badge.style.fontFamily = "Inter, system-ui, sans-serif";
    badge.style.fontSize = "13px";

    const label = document.createElement("span");
    label.textContent = user.email || "Signed in";
    label.style.maxWidth = "220px";
    label.style.overflow = "hidden";
    label.style.textOverflow = "ellipsis";
    label.style.whiteSpace = "nowrap";

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Sign out";
    button.style.border = "0";
    button.style.borderRadius = "999px";
    button.style.padding = "7px 10px";
    button.style.cursor = "pointer";
    button.style.fontWeight = "800";
    button.style.background = "#eef5ff";
    button.style.color = "#07111f";

    button.addEventListener("click", async () => {
      await clearServerSession();
      await auth.signOut();
      authRedirect();
    });

    badge.appendChild(label);
    badge.appendChild(button);

    if (document.body) {
      document.body.appendChild(badge);
    } else {
      window.addEventListener("DOMContentLoaded", () => document.body.appendChild(badge), { once: true });
    }
  }

  authReadyPromise = initialiseAuth();
  window.SyntaxMatrixAuthReady = authReadyPromise;

  window.fetch = async function syntaxMatrixAuthenticatedFetch(input, init = {}) {
    if (!shouldAttachAuth(input)) {
      return originalFetch(input, init);
    }

    await authReadyPromise;

    const now = Date.now();
    const auth = window.SyntaxMatrixAuth && window.SyntaxMatrixAuth.auth;
    const user = auth && auth.currentUser;

    if (!user) {
      authRedirect();
      throw new Error("Authentication required.");
    }

    if (!cachedToken || now - cachedTokenAt > 45 * 60 * 1000) {
      cachedToken = await user.getIdToken(false);
      cachedTokenAt = now;
    }

    const headers = new Headers(init && init.headers ? init.headers : {});

    if (!headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${cachedToken}`);
    }

    return originalFetch(input, {
      ...init,
      headers
    });
  };
})();
