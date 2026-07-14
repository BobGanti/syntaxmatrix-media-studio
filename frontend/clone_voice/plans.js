(() => {
  "use strict";

  const SELECTABLE_PLAN_KEYS = ["free", "starter", "pro", "business"];
  const PAID_PLAN_KEYS = ["starter", "pro", "business"];

  function isSelectablePlanKey(planKey) {
    return ["free","starter","pro","business"].includes(planKey);
  }

  const FALLBACK_PLANS = [];
const SMX_PLAN_CATALOGUE_REQUIRED = true;

  function workspaceId() {
    const params = new URLSearchParams(window.location.search);
    return params.get("workspaceId") || params.get("workspace") || params.get("ws") || "";
  }

  function workspaceUrl() {
    const ws = workspaceId();
    return ws ? `/tasks/clone-voice?workspaceId=${encodeURIComponent(ws)}` : "/tasks/clone-voice";
  }

  function injectStyles() {
    let style = document.querySelector("#smx-plans-renderer-style");

    if (!style) {
      style = document.createElement("style");
      style.id = "smx-plans-renderer-style";
      document.head.appendChild(style);
    }

    style.textContent = `
      html,
      body {
        overflow-x: hidden !important;
      }

      .smx-loading-plan-block {
        display: none !important;
      }

      #smxPlansRenderedRoot {
        width: 100%;
        max-width: 1180px;
        margin: 32px auto 0;
        padding: 0 24px 96px;
        box-sizing: border-box;
        clear: both;
      }

      .smx-plan-notice {
        width: min(760px, 100%);
        margin: 0 auto 24px;
        padding: 14px 18px;
        border: 1px solid rgba(124, 165, 255, 0.35);
        border-radius: 14px;
        text-align: center;
        color: #d8e8ff;
        background: rgba(13, 30, 48, 0.72);
        box-sizing: border-box;
        line-height: 1.45;
      }

      .smx-plan-grid {
        width: 100%;
        margin: 0 auto;
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 24px;
        align-items: stretch;
        justify-content: center;
        box-sizing: border-box;
      }

      .smx-plan-card {
        width: 100%;
        min-width: 0;
        min-height: 292px;
        background: rgba(15, 36, 55, 0.94);
        border: 1px solid rgba(124, 165, 255, 0.38);
        border-radius: 18px;
        padding: 24px;
        box-shadow: 0 24px 72px rgba(0, 0, 0, 0.28);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-sizing: border-box;
      }

      .smx-plan-card[data-plan-key="pro"] {
        border-color: rgba(139, 126, 255, 0.95);
        box-shadow: 0 0 0 1px rgba(139, 126, 255, 0.22), 0 28px 90px rgba(91, 88, 255, 0.28);
      }

      .smx-plan-label {
        font-size: 1rem;
        font-weight: 950;
        margin-bottom: 18px;
      }

      .smx-plan-price {
        font-size: clamp(1.8rem, 3vw, 2.25rem);
        font-weight: 950;
        margin-bottom: 12px;
        white-space: nowrap;
      }

      .smx-plan-billing {
        font-size: 0.82rem;
        opacity: 0.82;
        margin-left: 2px;
      }

      .smx-plan-feature {
        color: #8fffe4;
        font-weight: 950;
        line-height: 1.45;
        margin: 4px 0;
      }

      .smx-plan-description {
        margin-top: 20px;
        line-height: 1.55;
        color: #c8ddff;
      }

      .smx-plan-button {
        width: 100%;
        border: 0;
        border-radius: 12px;
        margin-top: 28px;
        padding: 14px 16px;
        cursor: pointer;
        font-weight: 950;
        color: #fff;
        background: #737cff;
      }

      .smx-plan-button:hover {
        transform: translateY(-1px);
        filter: brightness(1.08);
      }

      .smx-plan-button:disabled {
        cursor: wait;
        opacity: 0.72;
      }

      @media (max-width: 980px) {
        #smxPlansRenderedRoot {
          max-width: 760px;
        }

        .smx-plan-grid {
          grid-template-columns: 1fr;
        }
      }
    `;
  }

  function removeOldLoadingBlocks() {
    const nodes = Array.from(document.querySelectorAll("div, section, article"));

    for (const node of nodes) {
      const text = String(node.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();

      if (text === "loading available plans..." || text.includes("loading available plans")) {
        node.classList.add("smx-loading-plan-block");
        node.style.display = "none";
      }
    }
  }

  function renderedRoot() {
    removeOldLoadingBlocks();

    let root = document.querySelector("#smxPlansRenderedRoot");

    if (root) {
      return root;
    }

    root = document.createElement("section");
    root.id = "smxPlansRenderedRoot";

    const loadingNode = Array.from(document.querySelectorAll(".smx-loading-plan-block"))[0];

    if (loadingNode && loadingNode.parentElement) {
      loadingNode.insertAdjacentElement("afterend", root);
      return root;
    }

    const main = document.querySelector("main") || document.body;
    const returnLink = Array.from(document.querySelectorAll("a")).find((a) => {
      return String(a.textContent || "").toLowerCase().includes("return to workspace");
    });

    if (returnLink && returnLink.parentElement && main.contains(returnLink.parentElement)) {
      returnLink.parentElement.insertAdjacentElement("beforebegin", root);
    } else {
      main.appendChild(root);
    }

    return root;
  }

  function normalizePlan(raw) {
    if (!raw || typeof raw !== "object") return null;

    const key = String(raw.key || raw.planKey || "").toLowerCase();

    if (!isSelectablePlanKey(key)) return null;

    const fallback = FALLBACK_PLANS.find((item) => item.key === key) || {};
    const monthlyPrice = raw.monthlyPrice !== undefined && raw.monthlyPrice !== null ? Number(raw.monthlyPrice) : null;

    const price =
      key === "free"
        ? "Free"
        : monthlyPrice !== null && Number.isFinite(monthlyPrice)
          ? `€${monthlyPrice.toFixed(2)}`
          : fallback.price;

    const monthlyCredits = raw.monthlyCredits;
    const weeklyCredits = raw.weeklyCredits;
    const cloneSlots = raw.cloneSlots ?? raw.maxCustomVoices;

    return {
      key,
      label: raw.label || fallback.label,
      price,
      billing: key === "free" ? "" : "/month",
      credits:
        key === "free"
          ? `${weeklyCredits || 10} credits reset weekly`
          : `${Number(monthlyCredits || 0).toLocaleString()} monthly credits`,
      voices:
        key === "free"
          ? "System voices only"
          : `${Number(cloneSlots || 0).toLocaleString()} custom voice slot${Number(cloneSlots || 0) === 1 ? "" : "s"}`,
      description: raw.description || fallback.description,
      button: fallback.button
    };
  }

  function normalizePlans(payload) {
    const candidates = [];

    if (Array.isArray(payload)) candidates.push(...payload);
    if (Array.isArray(payload?.plans)) candidates.push(...payload.plans);

    if (payload?.plans && !Array.isArray(payload.plans) && typeof payload.plans === "object") {
      candidates.push(...Object.values(payload.plans));
    }

    const byKey = new Map();

    for (const raw of candidates) {
      const plan = normalizePlan(raw);
      if (plan) byKey.set(plan.key, plan);
    }

    for (const fallback of FALLBACK_PLANS) {
      if (!byKey.has(fallback.key)) {
        byKey.set(fallback.key, fallback);
      }
    }

    return SELECTABLE_PLAN_KEYS.map((key) => byKey.get(key)).filter(Boolean);
  }

  function renderPlans(plans) {
    injectStyles();
    removeOldLoadingBlocks();

    const root = renderedRoot();
    root.innerHTML = "";

    const notice = document.createElement("div");
    notice.className = "smx-plan-notice";
    notice.textContent = "Choose Free for system voices and a weekly allowance, or select a paid plan for custom voice cloning.";
    root.appendChild(notice);

    const grid = document.createElement("div");
    grid.className = "smx-plan-grid";
    root.appendChild(grid);

    for (const plan of plans) {
      const card = document.createElement("article");
      card.className = "smx-plan-card";
      card.dataset.planKey = plan.key;

      card.innerHTML = `
        <div>
          <div class="smx-plan-label"></div>
          <div class="smx-plan-price"></div>
          <div class="smx-plan-feature smx-plan-credits"></div>
          <div class="smx-plan-feature smx-plan-voices"></div>
          <p class="smx-plan-description"></p>
        </div>
        <button type="button" class="smx-plan-button"></button>
      `;

      card.querySelector(".smx-plan-label").textContent = plan.label;
      card.querySelector(".smx-plan-price").innerHTML = `${plan.price}<span class="smx-plan-billing">${plan.billing || ""}</span>`;
      card.querySelector(".smx-plan-credits").textContent = plan.credits;
      card.querySelector(".smx-plan-voices").textContent = plan.voices;
      card.querySelector(".smx-plan-description").textContent = plan.description;

      const button = card.querySelector(".smx-plan-button");
      button.textContent = plan.button;
      button.disabled = false;
      button.dataset.planKey = plan.key;

      button.addEventListener("click", (event) => {
        event.preventDefault();

        if (plan.key === "free") {
          continueWithFree(button);
          return;
        }

        startPaidCheckout(plan.key, button);
      });

      grid.appendChild(card);
    }
  }

  async function fetchPlans() {
    const endpoints = [
      "/api/billing/plans",
      "/api/billing/catalog",
      "/api/billing/plan-catalog"
    ];

    for (const endpoint of endpoints) {
      try {
        const response = await fetch(`${endpoint}?t=${Date.now()}`, {
          credentials: "same-origin",
          cache: "no-store",
          headers: { "Accept": "application/json" }
        });

        if (!response.ok) continue;

        const payload = await response.json();
        const plans = normalizePlans(payload);

        if (plans.length >= 4) return plans;
      } catch (_) {
        // Use fallback below.
      }
    }

    return FALLBACK_PLANS;
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(payload)
    });

    let body = null;

    try {
      body = await response.json();
    } catch (_) {
      body = { text: await response.text().catch(() => "") };
    }

    if (!response.ok || body?.ok === false || body?.error) {
      throw new Error(body?.error || body?.message || body?.text || `${response.status} ${response.statusText}`);
    }

    return body;
  }

  function checkoutUrl(payload) {
    return (
      payload?.url ||
      payload?.checkoutUrl ||
      payload?.checkout_url ||
      payload?.sessionUrl ||
      payload?.session_url ||
      payload?.data?.url ||
      payload?.data?.checkoutUrl ||
      ""
    );
  }

  function setBusy(button, busy, text) {
    if (!button) return;

    if (busy) {
      button.dataset.originalText = button.textContent || "";
      button.textContent = text || "Opening checkout...";
      button.disabled = true;
    } else {
      button.disabled = false;
      button.textContent = button.dataset.originalText || button.textContent || "";
    }
  }

  async function continueWithFree(button) {
    const ws = workspaceId();

    setBusy(button, true, "Opening workspace...");

    const payload = {
      planKey: "free",
      plan: "free",
      workspaceId: ws,
      workspace_id: ws
    };

    const endpoints = [
      "/api/billing/select-free-plan",
      "/api/billing/free-plan",
      "/api/billing/activate-free-plan"
    ];

    for (const endpoint of endpoints) {
      try {
        await postJson(endpoint, payload);
        break;
      } catch (_) {
        // Free may already be active.
      }
    }

    window.location.href = workspaceUrl();
  }

  async function startPaidCheckout(planKey, button) {
    if (!PAID_PLAN_KEYS.includes(planKey)) return;

    const ws = workspaceId();

    if (!ws) {
      alert("Workspace is missing. Return to the workspace and choose a plan again.");
      return;
    }

    // >>> SMX_STRIPE_RETURN_STORAGE >>>
    try {
      window.localStorage.setItem("smxStripeReturnWorkspaceId", ws);
      window.sessionStorage.setItem("smxStripeReturnWorkspaceId", ws);
    } catch (_) {
      // Ignore storage failures.
    }
    // <<< SMX_STRIPE_RETURN_STORAGE <<<

    const payload = {
      planKey,
      plan: planKey,
      workspaceId: ws,
      workspace_id: ws,
      successUrl: `${window.location.origin}${workspaceUrl()}?billing=success`,
      cancelUrl: window.location.href
    };

    const endpoints = [
      "/api/billing/checkout/stripe",
      "/api/billing/checkout/session",
      "/api/billing/create-checkout-session",
      "/api/billing/checkout",
      "/api/stripe/create-checkout-session"
    ];

    const errors = [];

    setBusy(button, true, "Opening checkout...");

    try {
      for (const endpoint of endpoints) {
        try {
          const result = await postJson(endpoint, payload);
          const url = checkoutUrl(result);

          if (url) {
            window.location.href = url;
            return;
          }

          errors.push(`${endpoint}: no Stripe URL returned`);
        } catch (error) {
          errors.push(`${endpoint}: ${error.message}`);
        }
      }

      console.error("Stripe checkout failed:", errors);
      alert("Checkout could not be started. Stripe checkout endpoint did not return a checkout URL.");
    } finally {
      setBusy(button, false);
    }
  }

  async function boot() {
    renderPlans(FALLBACK_PLANS);

    const plans = await fetchPlans();
    renderPlans(plans);
  }

  document.addEventListener("DOMContentLoaded", boot);

  setTimeout(() => {
    removeOldLoadingBlocks();

    if (!document.querySelector("#smxPlansRenderedRoot .smx-plan-card")) {
      renderPlans(FALLBACK_PLANS);
    }
  }, 400);
})();

// >>> SMX_PLAN_BUTTON_LABEL_FIX >>>
(function smxPlanButtonLabelFix() {
  const STYLE_ID = "smx-plan-button-label-fix-style";

  function textOf(node) {
    return (node && (node.innerText || node.textContent || "") || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      body.smx-plan-button-label-fixed button,
      body.smx-plan-button-label-fixed a[role="button"] {
        color: #06111d !important;
        font-weight: 900 !important;
        text-align: center !important;
      }

      [data-smx-plan-button-fixed="true"] {
        min-height: 42px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding-left: 18px !important;
        padding-right: 18px !important;
        line-height: 1.15 !important;
        white-space: nowrap !important;
      }
    `;

    document.head.appendChild(style);
  }

  function detectPlanKey(card) {
    const text = textOf(card).toLowerCase();

    if (text.includes("business")) return "business";
    if (text.includes("pro")) return "pro";
    if (text.includes("starter")) return "starter";
    if (text.includes("free")) return "free";

    return "";
  }

  function labelForPlan(planKey) {
    if (planKey === "free") return "Continue with Free";
    if (planKey === "starter") return "Choose Starter";
    if (planKey === "pro") return "Choose Pro";
    if (planKey === "business") return "Choose Business";

    return "Choose plan";
  }

  function findPlanCards() {
    const cards = [];

    Array.from(document.querySelectorAll("section, article, div"))
      .forEach((node) => {
        const text = textOf(node).toLowerCase();

        if (
          node.querySelector("button, a") &&
          (
            text.includes("monthly credits") ||
            text.includes("system voices only") ||
            text.includes("custom voice slot")
          ) &&
          (
            text.includes("free") ||
            text.includes("starter") ||
            text.includes("pro") ||
            text.includes("business")
          )
        ) {
          cards.push(node);
        }
      });

    return cards
      .sort((a, b) => textOf(a).length - textOf(b).length)
      .filter((card, index, arr) => {
        return !arr.some((other, otherIndex) => {
          return otherIndex < index && other.contains(card);
        });
      });
  }

  function fixButtons() {
    document.body.classList.add("smx-plan-button-label-fixed");
    injectStyle();

    const cards = findPlanCards();

    cards.forEach((card) => {
      const planKey = detectPlanKey(card);
      const label = labelForPlan(planKey);

      const candidates = Array.from(card.querySelectorAll("button, a"))
        .filter((node) => {
          const visibleWidth = node.getBoundingClientRect().width;
          const visibleHeight = node.getBoundingClientRect().height;
          return visibleWidth > 40 && visibleHeight > 18;
        });

      const button = candidates[candidates.length - 1];

      if (!button) {
        return;
      }

      const current = textOf(button);

      if (!current || current.length < 3 || current === "—") {
        button.textContent = label;
      }

      button.setAttribute("data-smx-plan-button-fixed", "true");
      button.setAttribute("aria-label", label);
      button.title = label;
    });
  }

  function schedule() {
    fixButtons();
    setTimeout(fixButtons, 250);
    setTimeout(fixButtons, 800);
    setTimeout(fixButtons, 1600);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", schedule);
  } else {
    schedule();
  }

  const observer = new MutationObserver(() => {
    window.clearTimeout(window.__smxPlanButtonLabelFixTimer);
    window.__smxPlanButtonLabelFixTimer = window.setTimeout(fixButtons, 120);
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
// <<< SMX_PLAN_BUTTON_LABEL_FIX <<<

// >>> SMX_PLANS_CHECKOUT_RETURN_AUTO_RECONCILE >>>
(function smxPlansCheckoutReturnAutoReconcile() {
  function params() {
    return new URLSearchParams(window.location.search || "");
  }

  function workspaceId() {
    const p = params();
    return p.get("workspaceId") || p.get("workspace_id") || localStorage.getItem("smx_workspace_id") || "";
  }

  function stripeId() {
    const p = params();
    return p.get("session_id") || p.get("sessionId") || p.get("checkout_session_id") || p.get("checkoutSessionId") || p.get("stripeId") || "";
  }

  async function run() {
    const p = params();
    const billing = String(p.get("billing") || "").toLowerCase();
    const sid = stripeId();
    const wid = workspaceId();

    if (!(billing === "success" || sid) || !sid || !wid) {
      return;
    }

    try {
      await fetch("/api/billing/checkout/reconcile", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({workspaceId: wid, stripeId: sid, sessionId: sid}),
      });

      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete("billing");
      cleanUrl.searchParams.delete("session_id");
      cleanUrl.searchParams.delete("sessionId");
      cleanUrl.searchParams.delete("checkout_session_id");
      cleanUrl.searchParams.delete("checkoutSessionId");
      cleanUrl.searchParams.delete("stripeId");
      window.history.replaceState({}, "", cleanUrl.toString());
    } catch (err) {
      console.warn("[SMX] plans checkout return reconcile failed", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
// <<< SMX_PLANS_CHECKOUT_RETURN_AUTO_RECONCILE <<<

