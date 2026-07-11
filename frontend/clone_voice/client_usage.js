(() => {
  "use strict";

  const CARD_ID = "smxClientUsageCard";
  const REFRESH_DELAY_MS = 900;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normaliseNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function formatCredits(value) {
    const number = normaliseNumber(value);

    if (number === null) return "Unlimited";

    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: number % 1 === 0 ? 0 : 1
    }).format(number);
  }

  function elementText(element) {
    return String(element?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function findWorkspaceSelect() {
    const selects = Array.from(document.querySelectorAll("select"));

    let best = null;
    let bestScore = -1;

    for (const select of selects) {
      const idText = [
        select.id,
        select.name,
        select.className,
        select.getAttribute("aria-label")
      ].join(" ").toLowerCase();

      const optionText = Array.from(select.options || [])
        .map((option) => `${option.value} ${option.textContent}`)
        .join(" ")
        .toLowerCase();

      const nearbyText = elementText(select.closest("section, article, fieldset, div")).toLowerCase();

      let score = 0;

      if (idText.includes("workspace")) score += 10;
      if (optionText.includes("mock_user")) score += 10;
      if (optionText.includes("workspace")) score += 8;
      if (optionText.includes("client")) score += 4;
      if (nearbyText.includes("active workspace")) score += 6;
      if (nearbyText.includes("workspace")) score += 3;

      if (score > bestScore) {
        best = select;
        bestScore = score;
      }
    }

    return best;
  }

  function looksLikePanel(element) {
    if (!element || element === document.body || element === document.documentElement) return false;

    const style = window.getComputedStyle(element);
    const className = String(element.className || "").toLowerCase();

    const hasBorder =
      parseFloat(style.borderTopWidth || "0") > 0 ||
      parseFloat(style.borderBottomWidth || "0") > 0 ||
      parseFloat(style.borderLeftWidth || "0") > 0 ||
      parseFloat(style.borderRightWidth || "0") > 0;

    const hasPanelClass =
      className.includes("card") ||
      className.includes("panel") ||
      className.includes("step") ||
      className.includes("section");

    return element.offsetWidth >= 260 && (hasBorder || hasPanelClass || ["SECTION", "ARTICLE", "FIELDSET"].includes(element.tagName));
  }

  function isWrongLargeContainer(element) {
    const text = elementText(element).toLowerCase();

    return (
      text.includes("create voice") ||
      text.includes("choose voice") ||
      text.includes("generate narration") ||
      text.includes("result")
    );
  }

  function findWorkspacePanel() {
    const select = findWorkspaceSelect();

    if (!select) return null;

    let current = select;
    let best = null;

    while (current && current !== document.body && current !== document.documentElement) {
      const text = elementText(current).toLowerCase();

      if (text.includes("workspace") && !isWrongLargeContainer(current) && looksLikePanel(current)) {
        best = current;
      }

      current = current.parentElement;
    }

    return best;
  }

  function findCreateVoicePanel() {
    const candidates = Array.from(document.querySelectorAll("section, article, fieldset, div"));

    for (const candidate of candidates) {
      if (candidate.id === CARD_ID) continue;

      const text = elementText(candidate).toLowerCase();

      if (!text.includes("create voice")) continue;
      if (text.includes("choose voice") || text.includes("generate narration")) continue;
      if (!looksLikePanel(candidate)) continue;

      return candidate;
    }

    return null;
  }

  function mountCard(card) {
    if (card.parentElement) {
      card.remove();
    }

    const workspacePanel = findWorkspacePanel();

    if (workspacePanel && workspacePanel.parentElement) {
      workspacePanel.insertAdjacentElement("afterend", card);
      return;
    }

    const createVoicePanel = findCreateVoicePanel();

    if (createVoicePanel && createVoicePanel.parentElement) {
      createVoicePanel.parentElement.insertBefore(card, createVoicePanel);
      return;
    }

    const main = document.querySelector("main") || document.body;
    main.prepend(card);
  }

  function createCard() {
    let card = document.getElementById(CARD_ID);

    if (!card) {
      card = document.createElement("section");
      card.id = CARD_ID;
      card.className = "smx-usage-card";
      card.innerHTML = `
        <div class="smx-usage-inner">
          <div class="smx-usage-top">
            <div>
              <div class="smx-usage-kicker">Usage & Plan</div>
              <h2 class="smx-usage-title">Loading subscription usage...</h2>
              <p class="smx-usage-subtitle">Your monthly generation credits and subscription status.</p>
            </div>
            <div class="smx-usage-pill">Checking</div>
          </div>

          <div class="smx-usage-grid">
            <div class="smx-usage-stat">
              <div class="smx-usage-label">Plan</div>
              <div class="smx-usage-value" data-usage-plan data-plan-key="">—</div>
            </div>
            <div class="smx-usage-stat">
              <div class="smx-usage-label">Used this month</div>
              <div class="smx-usage-value" data-usage-used>—</div>
            </div>
            <div class="smx-usage-stat">
              <div class="smx-usage-label">Remaining</div>
              <div class="smx-usage-value" data-usage-remaining>—</div>
            </div>
          </div>

          <div class="smx-usage-meter" aria-label="Monthly credit usage">
            <div class="smx-usage-meter-fill"></div>
          </div>

          <div class="smx-usage-message">Checking your available usage credits...</div>

          <div class="smx-usage-actions">
            <button type="button" class="smx-usage-refresh">Refresh usage</button>
            <button type="button" class="smx-billing-manage">Manage billing</button>
            <button type="button" class="smx-billing-upgrade">Upgrade plan</button>
          </div>
        </div>
      `;

      card.querySelector(".smx-usage-refresh")?.addEventListener("click", () => {
        refreshUsage({ force: true });
      });

      card.querySelector(".smx-billing-manage")?.addEventListener("click", openBillingPortal);
      card.querySelector(".smx-billing-upgrade")?.addEventListener("click", openUpgradeCheckout);
    }

    mountCard(card);
    return card;
  }

  function currentWorkspaceId() {
    const select = findWorkspaceSelect();

    if (select && select.value) return select.value;

    const active = document.querySelector("[data-workspace-id], [data-workspaceid]");

    if (active) {
      return active.getAttribute("data-workspace-id") || active.getAttribute("data-workspaceid") || "";
    }

    return "";
  }

  function statusClass(payload) {
    const status = String(payload?.subscription?.status || "").toLowerCase();
    const quota = String(payload?.usage?.quotaState || "").toLowerCase();

    if (!payload?.allowed || ["past_due", "canceled", "cancelled", "unpaid", "incomplete", "incomplete_expired", "paused"].includes(status)) {
      return "blocked";
    }

    if (quota === "exceeded") return "blocked";

    const used = normaliseNumber(payload?.usage?.usedCredits) || 0;
    const limit = normaliseNumber(payload?.usage?.monthlyCreditLimit);

    if (limit && limit > 0 && used / limit >= 0.8) {
      return "warn";
    }

    return "";
  }

  function renderUsage(payload) {
    const card = createCard();

    card.classList.remove("smx-usage-loading");

    const subscription = payload.subscription || {};
    const usage = payload.usage || {};

    const planLabel = subscription.planLabel || subscription.plan || subscription.planKey || "Starter";
    const planKey = subscription.planKey || subscription.plan || "starter";
    const status = subscription.status || "active";
    const used = normaliseNumber(usage.usedCredits) || 0;
    const limit = normaliseNumber(usage.monthlyCreditLimit);
    const remaining = usage.remainingCredits;
    const allowed = payload.allowed !== false;

    const cls = statusClass(payload);

    const title = card.querySelector(".smx-usage-title");
    const subtitle = card.querySelector(".smx-usage-subtitle");
    const pill = card.querySelector(".smx-usage-pill");
    const plan = card.querySelector("[data-usage-plan]");
    const usedNode = card.querySelector("[data-usage-used]");
    const remainingNode = card.querySelector("[data-usage-remaining]");
    const meterFill = card.querySelector(".smx-usage-meter-fill");
    const message = card.querySelector(".smx-usage-message");

    if (title) title.textContent = `${planLabel} plan`;
    if (subtitle) subtitle.textContent = "Monthly generation credits for this workspace.";

    if (pill) {
      pill.className = `smx-usage-pill ${cls}`.trim();
      pill.textContent = status;
    }

    if (plan) {
      plan.textContent = planLabel;
      plan.dataset.planKey = planKey;
    }

    if (usedNode) {
      usedNode.textContent = limit === null ? `${formatCredits(used)} used` : `${formatCredits(used)} / ${formatCredits(limit)}`;
    }

    if (remainingNode) {
      remainingNode.textContent = formatCredits(remaining);
    }

    let percent = 0;

    if (limit && limit > 0) {
      percent = Math.min(100, Math.max(0, (used / limit) * 100));
    }

    if (meterFill) {
      meterFill.className = `smx-usage-meter-fill ${cls}`.trim();
      meterFill.style.width = limit === null ? "100%" : `${percent}%`;
    }

    if (message) {
      if (allowed) {
        const quotaText = limit === null
          ? "This workspace has unlimited monthly usage credits."
          : `${formatCredits(remaining)} credits remaining this month.`;

        message.innerHTML = `<strong>Ready.</strong> ${escapeHtml(quotaText)}`;
      } else {
        message.innerHTML = `<strong>Action blocked.</strong> ${escapeHtml(payload.message || "Please update billing to continue.")}`;
      }
    }
  }

  function renderUsageError(error) {
    const card = createCard();

    card.classList.remove("smx-usage-loading");

    const title = card.querySelector(".smx-usage-title");
    const pill = card.querySelector(".smx-usage-pill");
    const message = card.querySelector(".smx-usage-message");

    if (title) title.textContent = "Usage unavailable";

    if (pill) {
      pill.className = "smx-usage-pill warn";
      pill.textContent = "Check";
    }

    if (message) {
      message.innerHTML = `<strong>Could not load usage.</strong> ${escapeHtml(error.message || String(error))}`;
    }
  }

  function nextUpgradePlan(currentPlan) {
    const plan = String(currentPlan || "starter").toLowerCase();

    if (plan.includes("starter")) return "pro";
    if (plan.includes("pro")) return "business";
    if (plan.includes("business")) return "enterprise";

    return "pro";
  }

  async function openBillingPortal() {
    const card = createCard();
    const workspaceId = currentWorkspaceId();
    const message = card.querySelector(".smx-usage-message");
    const manageButton = card.querySelector(".smx-billing-manage");

    if (manageButton) {
      manageButton.disabled = true;
      manageButton.textContent = "Opening...";
    }

    try {
      const response = await fetch("/api/billing/portal/stripe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ workspaceId })
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.ok === false) {
        throw new Error(data.message || data.error || "Could not open billing portal");
      }

      if (data.portalUrl) {
        window.open(data.portalUrl, "_blank", "noopener,noreferrer");
      }

      if (message) {
        message.innerHTML = "<strong>Billing portal opened.</strong> Return here after making billing changes.";
      }
    } catch (error) {
      if (message) {
        message.innerHTML = `<strong>Billing portal unavailable.</strong> ${escapeHtml(error.message || String(error))}`;
      }
    } finally {
      if (manageButton) {
        manageButton.disabled = false;
        manageButton.textContent = "Manage billing";
      }

      scheduleRefresh();
    }
  }

  async function openUpgradeCheckout() {
    const card = createCard();
    const workspaceId = currentWorkspaceId();
    const message = card.querySelector(".smx-usage-message");
    const upgradeButton = card.querySelector(".smx-billing-upgrade");
    const planNode = card.querySelector("[data-usage-plan]");
    const currentPlan = planNode?.dataset?.planKey || planNode?.textContent || "starter";
    const planKey = nextUpgradePlan(currentPlan);

    if (upgradeButton) {
      upgradeButton.disabled = true;
      upgradeButton.textContent = "Opening...";
    }

    try {
      const portalStatusResponse = await fetch(`/api/billing/portal/stripe/status?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`, {
        cache: "no-store"
      });

      const portalStatus = await portalStatusResponse.json().catch(() => ({}));

      if (portalStatus.ok && portalStatus.hasStripeCustomer) {
        if (message) {
          message.innerHTML = "<strong>Opening billing portal.</strong> Existing subscriptions are managed there to avoid duplicate subscriptions.";
        }

        await openBillingPortal();
        return;
      }

      if (planKey === "enterprise") {
        if (message) {
          message.innerHTML = "<strong>Enterprise plan.</strong> Please contact the account team for enterprise billing.";
        }
        return;
      }

      const response = await fetch("/api/billing/checkout/stripe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          workspaceId,
          planKey
        })
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.ok === false) {
        throw new Error(data.message || data.error || "Could not open Stripe Checkout");
      }

      if (data.checkoutUrl) {
        window.open(data.checkoutUrl, "_blank", "noopener,noreferrer");
      }

      if (message) {
        message.innerHTML = `<strong>Checkout opened.</strong> Complete checkout to move this workspace to ${escapeHtml(data.planLabel || planKey)}.`;
      }
    } catch (error) {
      if (message) {
        message.innerHTML = `<strong>Billing action unavailable.</strong> ${escapeHtml(error.message || String(error))}`;
      }
    } finally {
      if (upgradeButton) {
        upgradeButton.disabled = false;
        upgradeButton.textContent = "Upgrade plan";
      }

      scheduleRefresh();
    }
  }


  let refreshTimer = null;
  let inFlight = null;

  async function refreshUsage({ force = false } = {}) {
    const card = createCard();

    if (inFlight && !force) return inFlight;

    card.classList.add("smx-usage-loading");

    const workspaceId = currentWorkspaceId();
    if (!workspaceId) {
      card.classList.remove("smx-usage-loading");
      return null;
    }
    const url = `/api/billing/entitlement?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`;

    inFlight = fetch(url, {
      cache: "no-store"
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));

        if (!response.ok || data.ok === false) {
          throw new Error(data.message || data.error || `Usage request failed: ${response.status}`);
        }

        renderUsage(data);
      })
      .catch(renderUsageError)
      .finally(() => {
        inFlight = null;
      });

    return inFlight;
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => refreshUsage({ force: true }), REFRESH_DELAY_MS);
  }

  function attachWorkspaceListener() {
    const select = findWorkspaceSelect();

    if (!select || select.dataset.smxUsageListener === "1") return;

    select.dataset.smxUsageListener = "1";
    select.addEventListener("change", () => refreshUsage({ force: true }));
  }

  function patchFetchForUsageRefresh() {
    if (window.__smxUsageFetchPatched) return;
    window.__smxUsageFetchPatched = true;

    const originalFetch = window.fetch;

    window.fetch = async (...args) => {
      const response = await originalFetch(...args);

      try {
        const requestUrl = String(args[0]?.url || args[0] || "");

        if (
          requestUrl.includes("/api/clone-voice/from-saved") ||
          requestUrl.includes("/api/clone-voice/from-system") ||
          requestUrl.includes("/api/clone-voice/voices/from-source") ||
          requestUrl.includes("/api/clone-voice/source-uploads/workspace/complete") ||
          requestUrl.includes("/api/clone-voice/source-uploads/workspace/replace") ||
          (requestUrl.includes("/api/clone-voice/my-voices/") && requestUrl.includes("/replace-source"))
        ) {
          scheduleRefresh();
        }
      } catch (_error) {
        // Refresh hook must never break product actions.
      }

      return response;
    };
  }

  function init() {
    createCard();
    attachWorkspaceListener();
    patchFetchForUsageRefresh();
    refreshUsage({ force: true });

    setInterval(() => {
      attachWorkspaceListener();

      const card = document.getElementById(CARD_ID);
      const workspacePanel = findWorkspacePanel();

      if (card && workspacePanel && card.parentElement === workspacePanel) {
        mountCard(card);
      }
    }, 1500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
