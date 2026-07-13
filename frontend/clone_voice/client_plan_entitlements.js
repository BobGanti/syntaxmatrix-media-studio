(() => {
  "use strict";

  function workspaceId() {
    return document.getElementById("workspaceSelect")?.value || "";
  }

  function notice() {
    let node = document.getElementById("smxPlanEntitlementNotice");
    if (!node) {
      node = document.createElement("div");
      node.id = "smxPlanEntitlementNotice";
      node.className = "result-summary";
      const createPanel = document.querySelector(".panel-create");
      createPanel?.insertAdjacentElement("beforebegin", node);
    }
    return node;
  }

  function apply(payload) {
    const features = payload.features || {};
    const freeRestricted = features.systemVoicesOnly === true || features.customVoiceCloning === false;
    const createPanel = document.querySelector(".panel-create");
    const savedMode = document.querySelector('input[name="sourceMode"][value="saved"]')?.closest("label");
    const savedPanel = document.getElementById("savedPanel");
    const systemRadio = document.querySelector('input[name="sourceMode"][value="system"]');
    const node = notice();

    if (createPanel) createPanel.hidden = freeRestricted;
    if (savedMode) savedMode.hidden = freeRestricted;
    if (savedPanel && freeRestricted) savedPanel.classList.add("hidden");

    if (freeRestricted) {
      if (systemRadio && !systemRadio.checked) {
        systemRadio.checked = true;
        systemRadio.dispatchEvent(new Event("change", { bubbles: true }));
      }
      node.hidden = false;
      node.innerHTML = `<strong>Free plan:</strong> system voices only, ${payload.usage?.remainingCredits ?? 0} credits remaining this week. Upgrade to create and use a private cloned voice.`;
    } else {
      if (savedMode) savedMode.hidden = false;
      if (createPanel) createPanel.hidden = false;
      node.hidden = true;
    }
  }

  async function refresh() {
    const id = workspaceId();
    if (!id) return;
    try {
      const response = await fetch(`/api/billing/entitlement?workspaceId=${encodeURIComponent(id)}&t=${Date.now()}`, { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok !== false) apply(data);
    } catch (error) {
      console.warn("[client_plan_entitlements]", error);
    }
  }

  function init() {
    document.getElementById("workspaceSelect")?.addEventListener("change", refresh);
    refresh();
    window.addEventListener("focus", refresh);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
