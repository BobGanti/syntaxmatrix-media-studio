(() => {
  "use strict";
  const status = document.getElementById("plansStatus");
  const grid = document.getElementById("plansGrid");

  function esc(value) { return String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
  function setStatus(message, kind = "") { status.textContent = message; status.className = `status ${kind}`.trim(); }
  function money(value, currency) { return new Intl.NumberFormat(undefined,{style:"currency",currency:currency || "EUR",maximumFractionDigits:2}).format(Number(value || 0)); }

  async function waitForWorkspace() {
    if (window.SyntaxMatrixAuthReady) await window.SyntaxMatrixAuthReady;
    for (let i = 0; i < 80; i += 1) {
      const id = window.SyntaxMatrixWorkspace?.defaultWorkspaceId || window.SyntaxMatrixWorkspace?.workspaces?.[0]?.workspaceId || "";
      if (id) return id;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("Could not determine your workspace.");
  }

  async function beginCheckout(workspaceId, planKey, button) {
    button.disabled = true; button.textContent = "Opening secure checkout...";
    try {
      const portalResponse = await fetch(`/api/billing/portal/stripe/status?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`, {cache:"no-store"});
      const portal = await portalResponse.json().catch(() => ({}));
      if (portal.ok && portal.hasStripeCustomer) {
        const response = await fetch("/api/billing/portal/stripe", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({workspaceId})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok || !data.portalUrl) throw new Error(data.message || data.error || "Could not open billing portal.");
        window.location.assign(data.portalUrl);
        return;
      }

      const response = await fetch("/api/billing/checkout/stripe", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({workspaceId,planKey})});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok || !data.checkoutUrl) throw new Error(data.message || data.error || "Could not open Stripe Checkout.");
      window.location.assign(data.checkoutUrl);
    } catch (error) {
      setStatus(error.message || String(error), "error");
      button.disabled = false; button.textContent = "Choose this plan";
    }
  }

  async function waitForPayment(workspaceId) {
    setStatus("Payment completed. Confirming your subscription...", "success");
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const response = await fetch(`/api/billing/entitlement?workspaceId=${encodeURIComponent(workspaceId)}&t=${Date.now()}`, {cache:"no-store"});
      const data = await response.json().catch(() => ({}));
      const currentStatus = String(data?.subscription?.status || "").toLowerCase();
      if (response.ok && data.ok && ["active","trialing"].includes(currentStatus)) {
        setStatus("Subscription active. Opening your workspace...", "success");
        window.setTimeout(() => window.location.assign("/tasks/clone-voice"), 800);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    setStatus("Payment was received, but subscription activation is still processing. Refresh this page in a moment.", "error");
  }

  async function init() {
    try {
      const workspaceId = await waitForWorkspace();
      const response = await fetch(`/api/billing/plans?t=${Date.now()}`, {cache:"no-store"});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.message || data.error || "Could not load plans.");
      const plans = (
        Array.isArray(data.plans)
          ? data.plans
          : []
      ).filter((plan) => {
        const key = String(
          plan?.key || ""
        ).toLowerCase();

        return (
          ["starter", "pro", "business"].includes(key)
          && Number(plan?.monthlyPrice || 0) > 0
        );
      });

      grid.innerHTML = plans.map((plan,index) => `
        <article class="plan-card ${index === 1 ? "featured" : ""}">
          <div class="plan-name">${esc(plan.label)}</div>
          <div class="plan-price">${esc(money(plan.monthlyPrice,data.currency))}<small>/month</small></div>
          <div class="plan-credits">${esc(Number(plan.monthlyCredits || 0).toLocaleString())} monthly credits</div>
          <p class="plan-description">${esc(plan.description || "")}</p>
          <button type="button" data-plan-key="${esc(plan.key)}" ${plan.available ? "" : "disabled"}>${plan.available ? "Choose this plan" : "Unavailable"}</button>
        </article>`).join("");
      grid.querySelectorAll("[data-plan-key]").forEach((button) => button.addEventListener("click", () => beginCheckout(workspaceId, button.dataset.planKey, button)));
      setStatus("Select the plan that suits your expected monthly usage.");
      const params = new URLSearchParams(window.location.search);
      if (params.get("checkout") === "success") await waitForPayment(workspaceId);
      if (params.get("checkout") === "cancelled") setStatus("Checkout was cancelled. No subscription change was made.", "error");
    } catch (error) { setStatus(error.message || String(error), "error"); }
  }
  init();
})();
